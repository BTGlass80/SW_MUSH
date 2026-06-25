# -*- coding: utf-8 -*-
"""
tests/test_ux_drop1_affordances_session.py — UX Drop 1 engine producers.

Covers the server-side surface of the clickable-affordances drop:

  1. get_combat dead-hook fix — `_hud_room_contents` now reads the REAL combat
     registry (`parser.combat_commands._active_combats` keyed by
     `_combat_key_for`) instead of the never-existent `engine.combat.get_combat`
     symbol, so `hud["in_combat"]` reflects an actual active combat.
  2. Bounty cross-check — an NPC that is the CALLER'S OWN claimed bounty target
     gets `is_bounty_target=True` and a `claim` action; a non-target NPC and a
     contract claimed by a DIFFERENT character do not.
  3. Guide-protect — `_classify_npc_role` returns `quest` for a quest-giver /
     guide marker, and a non-hostile NPC whose NAME merely contains a guard
     keyword is NOT classed `guard` (so it gets no attack affordance), while a
     hostile/aggressive guard-keyword NPC still classes `guard`.
  4. `_npc_actions` never offers `attack` for a `quest` role.

Uses Session.__new__ + a FakeDB (no real SQLite), mirroring
tests/test_fmap6_session_contacts.py.
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.session import (  # noqa: E402
    Protocol,
    Session,
    _classify_npc_role,
    _npc_actions,
)


def _run(coro):
    return asyncio.run(coro)


# ── Fakes ───────────────────────────────────────────────────────────────────


class FakeDB:
    """Minimal db stub for _hud_room_contents."""

    def __init__(self, npcs: list):
        self._npcs = npcs

    async def get_npcs_in_room(self, room_id):
        return [dict(n) for n in self._npcs if n.get("room_id") == room_id]

    async def get_objects_in_room(self, room_id, obj_type=None):
        return []  # no vendor droids in these fixtures


def _npc(npc_id: int, name: str, room_id: int = 100, **ai):
    return {
        "id": npc_id,
        "name": name,
        "room_id": room_id,
        "ai_config_json": json.dumps(ai),
    }


def _make_session(char_id: int = 1, room_id: int = 100):
    s = Session.__new__(Session)
    s.protocol = Protocol.WEBSOCKET
    s.character = {"id": char_id, "name": "Hunter", "room_id": room_id}
    s.id = 9001
    return s


async def _build_hud(session, db, *, security="contested", session_mgr=None):
    hud: dict = {}
    await session._hud_room_contents(
        hud, db, session.character["room_id"], {}, security, session_mgr
    )
    return hud


# ── 1. get_combat dead-hook fix ─────────────────────────────────────────────


class TestInCombatFlag(unittest.TestCase):
    def setUp(self):
        from parser import combat_commands
        self.cc = combat_commands
        self.cc._active_combats.clear()

    def tearDown(self):
        self.cc._active_combats.clear()

    def test_in_combat_false_when_no_active_combat(self):
        s = _make_session()
        db = FakeDB([_npc(2, "Tusken Raider", hostile=True)])
        hud = _run(_build_hud(s, db))
        self.assertIn("in_combat", hud)
        self.assertFalse(hud["in_combat"])

    def test_in_combat_true_with_active_combat(self):
        s = _make_session(char_id=1)
        db = FakeDB([_npc(2, "Tusken Raider", hostile=True)])
        # Seed a REAL live fight for this char's key. The producer reads
        # `not _combat_finished(combat)`, which requires two mutually-hostile
        # active combatants (an NPC + a PC). active_combatants further requires
        # c.char.can_act_now() True and not c.is_fleeing.
        combat = self.cc._get_or_create_combat(s.character)

        class _FakeChar:
            def can_act_now(self_inner):  # noqa: N805
                return True

        def _combatant(cid, is_npc):
            c = type("FakeCombatant", (), {})()
            c.id = cid
            c.is_npc = is_npc
            c.is_fleeing = False
            c.char = _FakeChar()
            return c

        combat.combatants[2] = _combatant(2, True)   # the Tusken (NPC)
        combat.combatants[1] = _combatant(1, False)  # the player (PC)
        hud = _run(_build_hud(s, db))
        self.assertTrue(hud["in_combat"])

    def test_in_combat_false_when_only_one_combatant(self):
        # A decided fight (last hostile down → only the PC active) is NOT a live
        # fight: _combat_finished is True, so no stale FLEE affordance.
        s = _make_session(char_id=1)
        db = FakeDB([_npc(2, "Tusken Raider", hostile=True)])
        combat = self.cc._get_or_create_combat(s.character)

        class _FakeChar:
            def can_act_now(self_inner):  # noqa: N805
                return True

        lone = type("FakeCombatant", (), {})()
        lone.id = 1
        lone.is_npc = False
        lone.is_fleeing = False
        lone.char = _FakeChar()
        combat.combatants[1] = lone
        hud = _run(_build_hud(s, db))
        self.assertFalse(hud["in_combat"])


# ── 2. Bounty cross-check ───────────────────────────────────────────────────


class TestBountyTarget(unittest.TestCase):
    def setUp(self):
        from engine import bounty_board
        from parser import combat_commands
        self.bb = bounty_board
        self.bb.reset_bounty_board()
        combat_commands._active_combats.clear()

    def tearDown(self):
        self.bb.reset_bounty_board()

    def _seed_contract(self, *, npc_id: int, claimed_by: str):
        from engine.bounty_board import (
            BountyContract,
            BountyStatus,
            BountyTier,
            get_bounty_board,
        )
        board = get_bounty_board()
        c = BountyContract(
            id=f"c_{npc_id}",
            tier=BountyTier.AVERAGE,
            target_name="Wanted Thug",
            target_species="Human",
            target_archetype="thug",
            crime_description="theft",
            posting_org="bhg",
            tip="seen near the cantina",
            reward=1500,
            reward_alive_bonus=200,
            target_npc_id=npc_id,
            target_room_id=100,
            status=BountyStatus.CLAIMED,
            claimed_by=claimed_by,
        )
        board._contracts[c.id] = c
        return c

    def test_own_target_flagged_and_gets_claim(self):
        s = _make_session(char_id=1)
        self._seed_contract(npc_id=2, claimed_by="1")
        db = FakeDB([_npc(2, "Wanted Thug", hostile=True)])
        hud = _run(_build_hud(s, db))
        npc = hud["room_contents"]["npcs"][0]
        self.assertTrue(npc["is_bounty_target"])
        self.assertIn("claim", npc["actions"])

    def test_non_target_npc_not_flagged(self):
        s = _make_session(char_id=1)
        self._seed_contract(npc_id=2, claimed_by="1")
        # NPC 3 is NOT the target — no contract references it.
        db = FakeDB([_npc(3, "Random Bystander", hostile=True)])
        hud = _run(_build_hud(s, db))
        npc = hud["room_contents"]["npcs"][0]
        self.assertFalse(npc["is_bounty_target"])
        self.assertNotIn("claim", npc["actions"])

    def test_other_hunters_contract_not_flagged(self):
        s = _make_session(char_id=1)
        # The contract on NPC 2 is claimed by a DIFFERENT character ("99").
        self._seed_contract(npc_id=2, claimed_by="99")
        db = FakeDB([_npc(2, "Wanted Thug", hostile=True)])
        hud = _run(_build_hud(s, db))
        npc = hud["room_contents"]["npcs"][0]
        self.assertFalse(npc["is_bounty_target"])
        self.assertNotIn("claim", npc["actions"])


# ── 3. Guide-protect ────────────────────────────────────────────────────────


class TestGuideProtect(unittest.TestCase):
    def test_quest_giver_marker_classifies_quest(self):
        self.assertEqual(
            _classify_npc_role(_npc(2, "Major Tarrn", quest_giver=True)), "quest"
        )

    def test_guide_marker_classifies_quest(self):
        self.assertEqual(
            _classify_npc_role(_npc(2, "Kessa the Guide", guide=True)), "quest"
        )

    def test_role_field_quest_classifies_quest(self):
        n = _npc(2, "Sergeant Drix")
        n["ai_config_json"] = json.dumps({"role": "quest"})
        self.assertEqual(_classify_npc_role(n), "quest")

    def test_peaceful_guard_keyword_name_not_guard(self):
        # A non-hostile NPC whose NAME reads like a guard (keyword) but has no
        # aggressive combat signal must NOT be classed guard (no attack button).
        n = _npc(2, "Sergeant Trooper Recruiter")  # contains 'trooper'
        self.assertNotEqual(_classify_npc_role(n), "guard")
        self.assertEqual(_classify_npc_role(n), "neutral")

    def test_hostile_guard_keyword_name_still_guard(self):
        n = _npc(2, "Patrol Trooper", combat_behavior="aggressive")
        self.assertEqual(_classify_npc_role(n), "guard")

    def test_quest_marker_beats_hostile_keyword_name(self):
        # Even a guard-keyword name + a quest marker → quest (protected).
        self.assertEqual(
            _classify_npc_role(_npc(2, "Soldier Briefing Officer", quest_giver=True)),
            "quest",
        )


# ── 4. _npc_actions quest role ──────────────────────────────────────────────


class TestQuestActions(unittest.TestCase):
    def test_quest_role_never_offers_attack(self):
        actions = _npc_actions("quest", hostile=False, in_combat=False,
                               security_level="lawless")
        self.assertIn("talk", actions)
        self.assertNotIn("attack", actions)

    def test_quest_role_attack_suppressed_even_in_lawless(self):
        # Contrast: a 'neutral' role DOES get attack in lawless (unchanged).
        neutral = _npc_actions("neutral", hostile=False, in_combat=False,
                               security_level="lawless")
        self.assertIn("attack", neutral)
        quest = _npc_actions("quest", hostile=False, in_combat=False,
                             security_level="lawless")
        self.assertNotIn("attack", quest)


if __name__ == "__main__":
    unittest.main()
