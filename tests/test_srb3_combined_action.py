# -*- coding: utf-8 -*-
"""
tests/test_srb3_combined_action.py — SRB.3 (May 22 2026).

Support Role Buffs v1, session 3 — Combined-action / Command-bonus.

Per `support_role_buffs_design_v1.md` §4, ships:

  Engine: engine/combined_actions.py (LeadOffer dataclass +
          in-memory state + create/get/join/consume/cancel API).
          engine/skill_checks.perform_skill_check() extended with
          optional lead_bonus / auto_consume_lead kwargs.
  Parser: parser/lead_commands.py with LeadCommand (+lead) and
          JoinLeadCommand (+joinlead). Registered via
          register_lead_commands.

Per design §4.2: **no schema.** State is per-process in-memory.

Test sections
=============

  1. TestConfigConstants            — pip/dice mapping is canonical
  2. TestLeadOfferDataclass         — is_expired / has_capacity / bonus_dice_str
  3. TestCreateLeadOffer            — happy path + reject re-lead
  4. TestCreateLeadOfferInvalidDiff — None on bad difficulty
  5. TestGetLeadOfferFor            — leader + follower lookup
  6. TestJoinLead                   — happy path + idempotent + cap + self
  7. TestJoinLeadExpired            — expired offer gets reaped
  8. TestConsumeLeadBonus           — single-use + removes offer
  9. TestConsumeNoOffer             — returns 0
 10. TestCancelLeadOffer            — removes
 11. TestReapExpired                — bulk cleanup
 12. TestSkillCheckLeadBonusExplicit — explicit pips applied
 13. TestSkillCheckAutoConsume     — auto-lookup consumes offer
 14. TestSkillCheckSuppressConsume — auto_consume_lead=False
 15. TestSkillCheckLeadBonusZero   — explicit 0 → no boost
 16. TestSkillCheckBonusFloor      — bonus stacks with buff modifier
 17. TestParseLeadArgs             — '+lead X for A B' parser
 18. TestParseDifficultySwitch     — /diff= validation
 19. TestRegistration              — commands exist + registered
 20. TestLeadCommandFailedRoll     — failed Command roll → no offer
 21. TestLeadCommandSuccess        — success → offer staged
 22. TestLeadCommandRoomMismatch   — follower outside room rejected
 23. TestLeadCommandRejectsSelf    — leader can't follow themselves
 24. TestJoinLeadCommandHappy      — explicit name path
 25. TestJoinLeadCommandAuto       — bare +joinlead with 1 room offer
 26. TestJoinLeadCommandAmbiguous  — 2+ offers → asks for name
 27. TestJoinLeadCommandNoOffer    — bare +joinlead with no offers
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.slow  # heavy: per-test in-memory DB + full migration chain


def _run(coro):
    return asyncio.run(coro)


# ─── shared fixtures ──────────────────────────────────────────────────────


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_char(db, *, name="Leader1", room_id=1):
    acct_cur = await db._db.execute(
        "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
        (f"acct_{name.lower()}_{id(name)}", "x"),
    )
    await db._db.commit()
    account_id = acct_cur.lastrowid

    attrs = json.dumps({
        "strength": "3D", "dexterity": "3D", "knowledge": "3D",
        "perception": "3D", "mechanical": "3D", "technical": "3D",
    })
    skills = json.dumps({"command": "5D"})  # Strong command for leader rolls

    cur = await db._db.execute(
        "INSERT INTO characters "
        "(name, account_id, room_id, attributes, skills, inventory, "
        " credits, wound_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, account_id, room_id, attrs, skills, '{"items":[]}', 0, 0),
    )
    await db._db.commit()
    cid = cur.lastrowid
    row = await db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (cid,)
    )
    return dict(row[0])


def _reset_state():
    """Wipe in-memory combined-actions state between tests."""
    from engine.combined_actions import _reset_for_test
    _reset_for_test()


# ──────────────────────────────────────────────────────────────────────
# 1. Config constants
# ──────────────────────────────────────────────────────────────────────

class TestConfigConstants(unittest.TestCase):

    def test_difficulty_mapping_matches_R_and_E(self):
        from engine.combined_actions import DIFFICULTY_TO_BONUS_PIPS
        self.assertEqual(DIFFICULTY_TO_BONUS_PIPS[10], 3)   # +1D
        self.assertEqual(DIFFICULTY_TO_BONUS_PIPS[15], 6)   # +2D
        self.assertEqual(DIFFICULTY_TO_BONUS_PIPS[20], 9)   # +3D
        # Only these three tiers
        self.assertEqual(set(DIFFICULTY_TO_BONUS_PIPS.keys()), {10, 15, 20})

    def test_standard_difficulties_sorted(self):
        from engine.combined_actions import STANDARD_DIFFICULTIES
        self.assertEqual(STANDARD_DIFFICULTIES, [10, 15, 20])

    def test_max_followers_is_five(self):
        from engine.combined_actions import MAX_FOLLOWERS_PER_LEAD
        self.assertEqual(MAX_FOLLOWERS_PER_LEAD, 5)

    def test_offer_duration_is_sixty_seconds(self):
        from engine.combined_actions import LEAD_OFFER_DURATION_SECS
        self.assertEqual(LEAD_OFFER_DURATION_SECS, 60)


# ──────────────────────────────────────────────────────────────────────
# 2. LeadOffer dataclass
# ──────────────────────────────────────────────────────────────────────

class TestLeadOfferDataclass(unittest.TestCase):

    def test_is_expired_after_expiry(self):
        from engine.combined_actions import LeadOffer
        o = LeadOffer(leader_id=1, action="x", difficulty=15,
                       bonus_pips=6, room_id=1,
                       created_at=0.0, expires_at=100.0)
        self.assertFalse(o.is_expired(now=50.0))
        self.assertTrue(o.is_expired(now=100.0))
        self.assertTrue(o.is_expired(now=200.0))

    def test_has_capacity(self):
        from engine.combined_actions import LeadOffer, MAX_FOLLOWERS_PER_LEAD
        o = LeadOffer(leader_id=1, action="x", difficulty=15,
                       bonus_pips=6, room_id=1)
        for i in range(MAX_FOLLOWERS_PER_LEAD):
            self.assertTrue(o.has_capacity())
            o.followers.append(i + 2)
        self.assertFalse(o.has_capacity())

    def test_is_member_includes_leader(self):
        from engine.combined_actions import LeadOffer
        o = LeadOffer(leader_id=1, action="x", difficulty=15,
                       bonus_pips=6, room_id=1, followers=[2, 3])
        self.assertTrue(o.is_member(1))
        self.assertTrue(o.is_member(2))
        self.assertTrue(o.is_member(3))
        self.assertFalse(o.is_member(99))

    def test_bonus_dice_str_formatting(self):
        from engine.combined_actions import LeadOffer
        for pips, want in [(3, "+1D"), (6, "+2D"), (9, "+3D"),
                            (1, "+1 pip"), (2, "+2 pips"),
                            (4, "+1D+1"), (7, "+2D+1")]:
            o = LeadOffer(leader_id=1, action="x", difficulty=10,
                           bonus_pips=pips, room_id=1)
            self.assertEqual(o.bonus_dice_str(), want, f"pips={pips}")


# ──────────────────────────────────────────────────────────────────────
# 3. create_lead_offer
# ──────────────────────────────────────────────────────────────────────

class TestCreateLeadOffer(unittest.TestCase):

    def test_happy_path(self):
        from engine.combined_actions import create_lead_offer
        _reset_state()
        o = create_lead_offer(
            leader_id=1, action="slice the door",
            difficulty=15, room_id=42, now=100.0,
        )
        self.assertIsNotNone(o)
        self.assertEqual(o.leader_id, 1)
        self.assertEqual(o.action, "slice the door")
        self.assertEqual(o.difficulty, 15)
        self.assertEqual(o.bonus_pips, 6)
        self.assertEqual(o.room_id, 42)
        self.assertEqual(o.expires_at, 100.0 + 60)

    def test_second_lead_same_leader_rejected(self):
        from engine.combined_actions import create_lead_offer
        _reset_state()
        o1 = create_lead_offer(leader_id=1, action="a", difficulty=10,
                                 room_id=1, now=100.0)
        self.assertIsNotNone(o1)
        o2 = create_lead_offer(leader_id=1, action="b", difficulty=15,
                                 room_id=1, now=110.0)
        self.assertIsNone(o2,
            "Same leader shouldn't be able to stage a second offer")


class TestCreateLeadOfferInvalidDiff(unittest.TestCase):

    def test_returns_none_for_nonstandard_difficulty(self):
        from engine.combined_actions import create_lead_offer
        _reset_state()
        o = create_lead_offer(leader_id=1, action="x", difficulty=12,
                                room_id=1, now=100.0)
        self.assertIsNone(o)


# ──────────────────────────────────────────────────────────────────────
# 5. get_lead_offer_for
# ──────────────────────────────────────────────────────────────────────

class TestGetLeadOfferFor(unittest.TestCase):

    def test_finds_leader(self):
        from engine.combined_actions import (
            create_lead_offer, get_lead_offer_for, join_lead)
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=100.0)
        offer = get_lead_offer_for(1, now=110.0)
        self.assertIsNotNone(offer)
        self.assertEqual(offer.leader_id, 1)

    def test_finds_follower(self):
        from engine.combined_actions import (
            create_lead_offer, get_lead_offer_for, join_lead)
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=100.0)
        join_lead(follower_id=2, leader_id=1, now=105.0)
        offer = get_lead_offer_for(2, now=110.0)
        self.assertIsNotNone(offer)
        self.assertEqual(offer.leader_id, 1)
        self.assertIn(2, offer.followers)

    def test_no_offer_returns_none(self):
        from engine.combined_actions import get_lead_offer_for
        _reset_state()
        self.assertIsNone(get_lead_offer_for(99, now=time.time()))


# ──────────────────────────────────────────────────────────────────────
# 6. join_lead
# ──────────────────────────────────────────────────────────────────────

class TestJoinLead(unittest.TestCase):

    def test_happy_path(self):
        from engine.combined_actions import create_lead_offer, join_lead
        _reset_state()
        create_lead_offer(leader_id=1, action="slice", difficulty=15,
                            room_id=1, now=100.0)
        ok, msg = join_lead(follower_id=2, leader_id=1, now=110.0)
        self.assertTrue(ok)
        self.assertIn("slice", msg)

    def test_join_no_offer(self):
        from engine.combined_actions import join_lead
        _reset_state()
        ok, _ = join_lead(follower_id=2, leader_id=99, now=100.0)
        self.assertFalse(ok)

    def test_idempotent(self):
        """Joining twice is idempotent (returns True with friendly msg)."""
        from engine.combined_actions import create_lead_offer, join_lead
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=100.0)
        ok1, _ = join_lead(follower_id=2, leader_id=1, now=110.0)
        ok2, msg2 = join_lead(follower_id=2, leader_id=1, now=120.0)
        self.assertTrue(ok1 and ok2)
        self.assertIn("already", msg2.lower())

    def test_leader_cant_follow_self(self):
        from engine.combined_actions import create_lead_offer, join_lead
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=100.0)
        ok, _ = join_lead(follower_id=1, leader_id=1, now=110.0)
        self.assertFalse(ok)

    def test_capacity_rejection(self):
        from engine.combined_actions import (
            create_lead_offer, join_lead, MAX_FOLLOWERS_PER_LEAD)
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=100.0)
        for i in range(MAX_FOLLOWERS_PER_LEAD):
            ok, _ = join_lead(follower_id=2 + i, leader_id=1, now=110.0)
            self.assertTrue(ok, f"follower {i}")
        # One more should fail
        ok, msg = join_lead(follower_id=99, leader_id=1, now=110.0)
        self.assertFalse(ok)
        self.assertIn("maximum", msg.lower())


class TestJoinLeadExpired(unittest.TestCase):

    def test_join_expired_returns_false_and_reaps(self):
        from engine.combined_actions import (
            create_lead_offer, join_lead, get_lead_offer_for)
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=100.0)
        # Try to join WAY after expiry
        ok, msg = join_lead(follower_id=2, leader_id=1, now=10000.0)
        self.assertFalse(ok)
        self.assertIn("expired", msg.lower())
        # Offer should be gone
        self.assertIsNone(get_lead_offer_for(1, now=10001.0))


# ──────────────────────────────────────────────────────────────────────
# 8-9. consume_lead_bonus
# ──────────────────────────────────────────────────────────────────────

class TestConsumeLeadBonus(unittest.TestCase):

    def test_consume_returns_pips_and_removes(self):
        from engine.combined_actions import (
            create_lead_offer, consume_lead_bonus, get_lead_offer_for)
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=20,
                            room_id=1, now=100.0)
        pips = consume_lead_bonus(1, now=110.0)
        self.assertEqual(pips, 9)  # +3D for Difficult
        # Offer is removed
        self.assertIsNone(get_lead_offer_for(1, now=120.0))

    def test_consume_follower_also_works(self):
        from engine.combined_actions import (
            create_lead_offer, join_lead, consume_lead_bonus,
            get_lead_offer_for)
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=100.0)
        join_lead(follower_id=2, leader_id=1, now=105.0)
        pips = consume_lead_bonus(2, now=110.0)
        self.assertEqual(pips, 6)
        # Offer is gone for everyone
        self.assertIsNone(get_lead_offer_for(1, now=120.0))
        self.assertIsNone(get_lead_offer_for(2, now=120.0))


class TestConsumeNoOffer(unittest.TestCase):

    def test_no_offer_returns_zero(self):
        from engine.combined_actions import consume_lead_bonus
        _reset_state()
        self.assertEqual(consume_lead_bonus(99), 0)


# ──────────────────────────────────────────────────────────────────────
# 10. cancel_lead_offer
# ──────────────────────────────────────────────────────────────────────

class TestCancelLeadOffer(unittest.TestCase):

    def test_cancel_removes(self):
        from engine.combined_actions import (
            create_lead_offer, cancel_lead_offer, get_lead_offer_for)
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=100.0)
        self.assertTrue(cancel_lead_offer(1))
        self.assertIsNone(get_lead_offer_for(1, now=110.0))

    def test_cancel_missing_returns_false(self):
        from engine.combined_actions import cancel_lead_offer
        _reset_state()
        self.assertFalse(cancel_lead_offer(99))


# ──────────────────────────────────────────────────────────────────────
# 11. reap_expired
# ──────────────────────────────────────────────────────────────────────

class TestReapExpired(unittest.TestCase):

    def test_reap_only_expired(self):
        from engine.combined_actions import (
            create_lead_offer, reap_expired, get_all_offers_for_test)
        _reset_state()
        create_lead_offer(leader_id=1, action="a", difficulty=10,
                            room_id=1, now=10.0)  # expires 70
        create_lead_offer(leader_id=2, action="b", difficulty=15,
                            room_id=1, now=100.0)  # expires 160
        n = reap_expired(now=80.0)
        self.assertEqual(n, 1)
        offers = get_all_offers_for_test()
        self.assertIn(2, offers)
        self.assertNotIn(1, offers)


# ──────────────────────────────────────────────────────────────────────
# 12-16. skill_checks integration
# ──────────────────────────────────────────────────────────────────────

class TestSkillCheckLeadBonusExplicit(unittest.TestCase):

    def test_explicit_pips_modifies_pool(self):
        """An explicit lead_bonus=6 adds +2D to the pool (verified by pool_str).

        WEG D6 stacking: skill ADDS to attribute. We use a clean 2D attribute
        plus a 2D skill so the base pool is 4D, then +6 pips = +2D = 6D.
        """
        from engine.skill_checks import perform_skill_check
        _reset_state()
        # Perception 2D + Command 2D = 4D base
        char = {"id": 1,
                "attributes": '{"perception": "2D"}',
                "skills": '{"command": "2D"}'}
        r0 = perform_skill_check(char, "command", 1, lead_bonus=0)
        r1 = perform_skill_check(char, "command", 1, lead_bonus=6)
        self.assertEqual(r0.pool_str, "4D")
        self.assertEqual(r1.pool_str, "6D")


class TestSkillCheckAutoConsume(unittest.TestCase):

    def test_auto_consume_when_lead_exists(self):
        """With auto_consume_lead=True (default), perform_skill_check
        looks up + consumes any active offer for the character."""
        from engine.combined_actions import create_lead_offer, get_lead_offer_for
        from engine.skill_checks import perform_skill_check
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=time.time())
        char = {"id": 1,
                "attributes": '{"perception": "2D"}',
                "skills": '{"command": "2D"}'}
        result = perform_skill_check(char, "command", 1)
        # 4D base + 2D bonus = 6D
        self.assertEqual(result.pool_str, "6D")
        # Offer was consumed
        self.assertIsNone(get_lead_offer_for(1))


class TestSkillCheckSuppressConsume(unittest.TestCase):

    def test_suppress_with_auto_consume_false(self):
        from engine.combined_actions import create_lead_offer, get_lead_offer_for
        from engine.skill_checks import perform_skill_check
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=time.time())
        char = {"id": 1,
                "attributes": '{"perception": "2D"}',
                "skills": '{"command": "2D"}'}
        result = perform_skill_check(char, "command", 1,
                                       auto_consume_lead=False)
        self.assertEqual(result.pool_str, "4D")  # No bonus
        self.assertIsNotNone(get_lead_offer_for(1))


class TestSkillCheckLeadBonusZero(unittest.TestCase):

    def test_explicit_zero_does_not_auto_consume(self):
        from engine.combined_actions import create_lead_offer, get_lead_offer_for
        from engine.skill_checks import perform_skill_check
        _reset_state()
        create_lead_offer(leader_id=1, action="x", difficulty=15,
                            room_id=1, now=time.time())
        char = {"id": 1,
                "attributes": '{"perception": "2D"}',
                "skills": '{"command": "2D"}'}
        result = perform_skill_check(char, "command", 1, lead_bonus=0)
        self.assertEqual(result.pool_str, "4D")
        self.assertIsNotNone(get_lead_offer_for(1))


class TestSkillCheckBonusFloor(unittest.TestCase):

    def test_lead_bonus_does_not_below_one_die(self):
        """Even if buff + lead would total negative, floor is 1D (3 pips)."""
        from engine.skill_checks import perform_skill_check
        _reset_state()
        char = {"id": 1,
                "attributes": '{"perception": "2D"}',
                "skills": '{"command": "2D"}'}
        result = perform_skill_check(char, "command", 1, lead_bonus=-99)
        self.assertEqual(result.pool_str, "1D")


# ──────────────────────────────────────────────────────────────────────
# 17-18. Argument parsing
# ──────────────────────────────────────────────────────────────────────

class TestParseLeadArgs(unittest.TestCase):

    def test_simple(self):
        from parser.lead_commands import _parse_lead_args
        action, followers, err = _parse_lead_args("slice the door for Padawan")
        self.assertIsNone(err)
        self.assertEqual(action, "slice the door")
        self.assertEqual(followers, ["Padawan"])

    def test_multiple_followers(self):
        from parser.lead_commands import _parse_lead_args
        action, followers, err = _parse_lead_args(
            "breach for Alice Bob Charlie"
        )
        self.assertIsNone(err)
        self.assertEqual(action, "breach")
        self.assertEqual(followers, ["Alice", "Bob", "Charlie"])

    def test_comma_separated(self):
        from parser.lead_commands import _parse_lead_args
        action, followers, err = _parse_lead_args(
            "breach for Alice, Bob, Charlie"
        )
        self.assertIsNone(err)
        self.assertEqual(followers, ["Alice", "Bob", "Charlie"])

    def test_no_for_token(self):
        from parser.lead_commands import _parse_lead_args
        _, _, err = _parse_lead_args("slice the door")
        self.assertIsNotNone(err)
        self.assertIn("Usage", err)

    def test_empty(self):
        from parser.lead_commands import _parse_lead_args
        _, _, err = _parse_lead_args("")
        self.assertIsNotNone(err)

    def test_no_followers(self):
        from parser.lead_commands import _parse_lead_args
        _, _, err = _parse_lead_args("breach for ")
        self.assertIsNotNone(err)

    def test_too_many_followers(self):
        from parser.lead_commands import _parse_lead_args
        _, _, err = _parse_lead_args(
            "breach for A B C D E F G"  # 7 followers > 5 max
        )
        self.assertIsNotNone(err)
        self.assertIn("Maximum", err)


class TestParseDifficultySwitch(unittest.TestCase):

    def test_default_is_moderate(self):
        from parser.lead_commands import _parse_difficulty_switch
        d, err = _parse_difficulty_switch([])
        self.assertEqual(d, 15)
        self.assertIsNone(err)

    def test_valid_difficulty(self):
        from parser.lead_commands import _parse_difficulty_switch
        for d_in in (10, 15, 20):
            d, err = _parse_difficulty_switch([f"diff={d_in}"])
            self.assertEqual(d, d_in)
            self.assertIsNone(err)

    def test_invalid_number(self):
        from parser.lead_commands import _parse_difficulty_switch
        _, err = _parse_difficulty_switch(["diff=12"])
        self.assertIsNotNone(err)
        self.assertIn("must be one of", err)

    def test_garbage_value(self):
        from parser.lead_commands import _parse_difficulty_switch
        _, err = _parse_difficulty_switch(["diff=banthapoodoo"])
        self.assertIsNotNone(err)


# ──────────────────────────────────────────────────────────────────────
# 19. Registration
# ──────────────────────────────────────────────────────────────────────

class TestRegistration(unittest.TestCase):

    def test_commands_exist(self):
        from parser.lead_commands import (
            LeadCommand, JoinLeadCommand, register_lead_commands,
        )
        self.assertEqual(LeadCommand().key, "+lead")
        self.assertEqual(JoinLeadCommand().key, "+joinlead")

    def test_register_wires_into_registry(self):
        from parser.commands import CommandRegistry
        from parser.lead_commands import register_lead_commands
        reg = CommandRegistry()
        register_lead_commands(reg)
        # Lookup by command key
        self.assertIsNotNone(reg.get("+lead"))
        self.assertIsNotNone(reg.get("+joinlead"))

    def test_registered_in_game_server(self):
        gs_path = PROJECT_ROOT / "server" / "game_server.py"
        text = gs_path.read_text(encoding="utf-8")
        self.assertIn("register_lead_commands", text)
        self.assertIn("from parser.lead_commands import register_lead_commands", text)


# ──────────────────────────────────────────────────────────────────────
# 20-23. LeadCommand execution paths
# ──────────────────────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self, character=None):
        self.is_in_game = True
        self.account = {"username": "Player", "is_admin": 0}
        self.character = character
        self.sent: list[str] = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)

    def all_text(self) -> str:
        return "\n".join(self.sent)


class _FakeSessionMgr:
    def __init__(self):
        self.broadcasts: list[tuple[int, str]] = []
        self._sessions_in_room: dict[int, list] = {}

    async def broadcast_to_room(self, room_id, msg, exclude=None,
                                  source_char=None):
        self.broadcasts.append((room_id, msg))

    def sessions_in_room(self, room_id, source_char=None):
        return list(self._sessions_in_room.get(room_id, []))


def _make_ctx(*, db, session, session_mgr, raw_input="",
               command="+lead", args="", switches=None):
    """Build a CommandContext for execution tests."""
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=raw_input,
        command=command,
        args=args,
        args_list=args.split(),
        switches=switches or [],
        db=db,
        session_mgr=session_mgr,
    )


class TestLeadCommandFailedRoll(unittest.TestCase):

    def test_failed_command_roll_no_offer(self):
        from parser.lead_commands import LeadCommand
        from engine.combined_actions import get_lead_offer_for
        async def go():
            _reset_state()
            db = await _fresh_db()
            leader = await _make_char(db, name="Leader", room_id=1)
            follower = await _make_char(db, name="Padawan", room_id=1)
            # Tank the leader's skill so the roll fails reliably:
            # use an explicit lead_bonus path test is the proper way to
            # be deterministic; here we patch perform_skill_check.
            from unittest.mock import patch
            sess = _FakeSession(character=leader)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              args="slice for Padawan",
                              switches=["diff=15"])
            with patch(
                "parser.lead_commands.perform_skill_check"
            ) as mock_pc:
                from engine.skill_checks import SkillCheckResult
                mock_pc.return_value = SkillCheckResult(
                    roll=8, difficulty=15, success=False, margin=-7,
                    critical_success=False, fumble=False,
                    skill_used="command", pool_str="5D",
                )
                await LeadCommand().execute(ctx)
            # No offer staged on failure
            self.assertIsNone(get_lead_offer_for(leader["id"]))
            self.assertIn("fail", sess.all_text().lower())
        _run(go())


class TestLeadCommandSuccess(unittest.TestCase):

    def test_successful_command_roll_stages_offer(self):
        from parser.lead_commands import LeadCommand
        from engine.combined_actions import get_lead_offer_for
        async def go():
            _reset_state()
            db = await _fresh_db()
            leader = await _make_char(db, name="Leader", room_id=1)
            follower = await _make_char(db, name="Padawan", room_id=1)
            sess = _FakeSession(character=leader)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              args="slice for Padawan",
                              switches=["diff=15"])
            from unittest.mock import patch
            with patch(
                "parser.lead_commands.perform_skill_check"
            ) as mock_pc:
                from engine.skill_checks import SkillCheckResult
                mock_pc.return_value = SkillCheckResult(
                    roll=18, difficulty=15, success=True, margin=3,
                    critical_success=False, fumble=False,
                    skill_used="command", pool_str="5D",
                )
                await LeadCommand().execute(ctx)
            offer = get_lead_offer_for(leader["id"])
            self.assertIsNotNone(offer)
            self.assertEqual(offer.action, "slice")
            self.assertEqual(offer.bonus_pips, 6)
        _run(go())


class TestLeadCommandRoomMismatch(unittest.TestCase):

    def test_follower_in_different_room_rejected(self):
        from parser.lead_commands import LeadCommand
        from engine.combined_actions import get_lead_offer_for
        async def go():
            _reset_state()
            db = await _fresh_db()
            leader = await _make_char(db, name="Leader", room_id=1)
            distant = await _make_char(db, name="Distant", room_id=99)
            sess = _FakeSession(character=leader)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              args="slice for Distant",
                              switches=["diff=15"])
            await LeadCommand().execute(ctx)
            self.assertIsNone(get_lead_offer_for(leader["id"]))
            self.assertIn("not in this room", sess.all_text().lower())
        _run(go())


class TestLeadCommandRejectsSelf(unittest.TestCase):

    def test_cannot_name_self_as_follower(self):
        from parser.lead_commands import LeadCommand
        from engine.combined_actions import get_lead_offer_for
        async def go():
            _reset_state()
            db = await _fresh_db()
            leader = await _make_char(db, name="Leader", room_id=1)
            sess = _FakeSession(character=leader)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              args="slice for Leader",
                              switches=["diff=15"])
            await LeadCommand().execute(ctx)
            self.assertIsNone(get_lead_offer_for(leader["id"]))
            self.assertIn(
                "follow your own", sess.all_text().lower()
            )
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 24-27. JoinLeadCommand execution paths
# ──────────────────────────────────────────────────────────────────────


class TestJoinLeadCommandHappy(unittest.TestCase):

    def test_join_by_explicit_leader_name(self):
        from parser.lead_commands import JoinLeadCommand
        from engine.combined_actions import (
            create_lead_offer, get_lead_offer_for)
        async def go():
            _reset_state()
            db = await _fresh_db()
            leader = await _make_char(db, name="Leader", room_id=1)
            follower = await _make_char(db, name="Padawan", room_id=1)
            create_lead_offer(
                leader_id=leader["id"], action="slice",
                difficulty=15, room_id=1, now=time.time(),
            )
            sess = _FakeSession(character=follower)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+joinlead",
                              args="Leader")
            await JoinLeadCommand().execute(ctx)
            offer = get_lead_offer_for(leader["id"])
            self.assertIn(follower["id"], offer.followers)
        _run(go())


class TestJoinLeadCommandAuto(unittest.TestCase):

    def test_bare_joinlead_with_single_room_offer(self):
        from parser.lead_commands import JoinLeadCommand
        from engine.combined_actions import (
            create_lead_offer, get_lead_offer_for)
        async def go():
            _reset_state()
            db = await _fresh_db()
            leader = await _make_char(db, name="Leader", room_id=1)
            follower = await _make_char(db, name="Padawan", room_id=1)
            create_lead_offer(
                leader_id=leader["id"], action="slice",
                difficulty=15, room_id=1, now=time.time(),
            )
            sess = _FakeSession(character=follower)
            mgr = _FakeSessionMgr()
            # Populate the room-scanner: leader session is in room 1
            leader_sess = _FakeSession(character=leader)
            mgr._sessions_in_room[1] = [leader_sess]
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+joinlead",
                              args="")
            await JoinLeadCommand().execute(ctx)
            offer = get_lead_offer_for(leader["id"])
            self.assertIn(follower["id"], offer.followers)
        _run(go())


class TestJoinLeadCommandAmbiguous(unittest.TestCase):

    def test_two_leads_asks_for_name(self):
        from parser.lead_commands import JoinLeadCommand
        from engine.combined_actions import create_lead_offer
        async def go():
            _reset_state()
            db = await _fresh_db()
            leader_a = await _make_char(db, name="LeaderA", room_id=1)
            leader_b = await _make_char(db, name="LeaderB", room_id=1)
            follower = await _make_char(db, name="Padawan", room_id=1)
            create_lead_offer(
                leader_id=leader_a["id"], action="slice",
                difficulty=15, room_id=1, now=time.time(),
            )
            create_lead_offer(
                leader_id=leader_b["id"], action="breach",
                difficulty=15, room_id=1, now=time.time(),
            )
            sess = _FakeSession(character=follower)
            mgr = _FakeSessionMgr()
            la_sess = _FakeSession(character=leader_a)
            lb_sess = _FakeSession(character=leader_b)
            mgr._sessions_in_room[1] = [la_sess, lb_sess]
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+joinlead",
                              args="")
            await JoinLeadCommand().execute(ctx)
            self.assertIn("multiple leads", sess.all_text().lower())
        _run(go())


class TestJoinLeadCommandNoOffer(unittest.TestCase):

    def test_bare_joinlead_no_offers(self):
        from parser.lead_commands import JoinLeadCommand
        async def go():
            _reset_state()
            db = await _fresh_db()
            follower = await _make_char(db, name="Padawan", room_id=1)
            sess = _FakeSession(character=follower)
            mgr = _FakeSessionMgr()
            mgr._sessions_in_room[1] = []
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+joinlead",
                              args="")
            await JoinLeadCommand().execute(ctx)
            self.assertIn("no active leads", sess.all_text().lower())
        _run(go())


if __name__ == "__main__":
    unittest.main()
