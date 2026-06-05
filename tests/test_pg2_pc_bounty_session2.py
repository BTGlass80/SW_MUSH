# -*- coding: utf-8 -*-
"""
tests/test_pg2_pc_bounty_session2.py — PG.2.bounty session 2
(May 21 2026).

Builds on PG.2 session 1 (post/cancel/board/status). Adds:

  Combat: Combatant.last_attacker_id field + _apply_damage stamps
  Death:  on_pc_death fires insurance + fulfillment when BH kill
  DB:     claim/release/fulfill/void/expire/revert + insurance
          debt CRUD + tick query methods (10 new methods)
  Parser: +pcbounty claim/release/pay/debt (4 player subcommands)
  Admin:  @pcbounty void/review/fulfill (3 admin subcommands)
  Tick:   run_pc_bounty_expiry_tick (engine) + pc_bounty_expiry_tick
          (server tick handler wrapper)

Test sections
=============

  1. TestLastAttackerIdField        — Combatant has the field
  2. TestApplyDamageStampsAttacker  — _apply_damage sets it
  3. TestClaimDbMethod              — claim flips state
  4. TestReleaseDbMethod            — release reverts to active
  5. TestFulfillDbMethod            — fulfill flips + snapshot
  6. TestVoidDbMethod               — void flips + snapshot
  7. TestExpireDbMethod             — expire flips + snapshot
  8. TestRevertExpiredClaim         — revert frees stale claim
  9. TestListExpiredActive          — tick query: 30d-elapsed actives
 10. TestListExpiredClaims          — tick query: 7d-elapsed claims
 11. TestInsuranceDebtCrud          — get/add/pay round-trip
 12. TestPayInsuranceFullClear      — paying ≥ debt deletes row
 13. TestFireInsuranceNoBh          — no-op when killer not BH
 14. TestFireInsuranceNoBounty      — no-op when no active bounty
 15. TestFireInsuranceHappy         — hit + payout + fulfill
 16. TestFireInsurancePartialDebt   — shortfall accrues as debt
 17. TestClaimCommandHappy          — +pcbounty claim works
 18. TestClaimCommandRequiresBh     — non-BH rejected
 19. TestClaimCommandSelfRejected   — can't claim against self
 20. TestReleaseCommandHappy        — +pcbounty release works
 21. TestReleaseCommandWrongBh      — non-claiming BH rejected
 22. TestDebtCommandShowsDebt       — +pcbounty debt renders
 23. TestPayCommandHappy            — +pcbounty pay clears debt
 24. TestPayCommandPartial          — partial pay leaves remainder
 25. TestAdminVoidRefundsFully      — @pcbounty void: full refund
 26. TestAdminReviewRenders         — @pcbounty review shape
 27. TestAdminFulfillPayout         — @pcbounty fulfill pays BH
 28. TestExpiryTickExpires30Day     — tick expires + refunds stake
 29. TestExpiryTickRevertsClaim     — tick reverts 7d-elapsed claim
 30. TestRegistrationAdminCmd       — @pcbounty registered
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ─── shared fixtures (mirror session 1's pattern) ─────────────────────────


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_chars(db, names: list, *, faction: str = "",
                      credits: int = 100000) -> dict:
    await db._db.execute(
        """INSERT OR IGNORE INTO accounts
           (username, password_hash, email)
           VALUES ('test', 'hash', 't@e.com')"""
    )
    out = {}
    for n in names:
        cur = await db._db.execute(
            """INSERT INTO characters
               (account_id, name, species, room_id, credits,
                faction_id)
               VALUES (1, ?, 'Human', 1, ?, ?)""",
            (n, credits, faction),
        )
        out[n] = cur.lastrowid
    await db._db.commit()
    chars = {}
    for n, cid in out.items():
        chars[n] = await db.get_character(cid)
    return chars


class _FakeSession:
    def __init__(self, character=None, *, admin=False):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": 1 if admin else 0,
                        "is_builder": 0}
        self.sent: list = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    def find_by_character(self, char_id):
        return None


def _ctx_for(session, db, command: str, args: str):
    from parser.commands import CommandContext
    return CommandContext(
        session=session, raw_input=f"{command} {args}".strip(),
        command=command, args=args,
        args_list=args.split() if args else [],
        db=db, session_mgr=_FakeSessionManager(),
    )


# ═════════════════════════════════════════════════════════════════════
# 1. Combatant.last_attacker_id field exists
# ═════════════════════════════════════════════════════════════════════


class TestLastAttackerIdField(unittest.TestCase):

    def test_default_none(self):
        from engine.combat import Combatant
        c = Combatant(id=1, name="X")
        self.assertIsNone(c.last_attacker_id)

    def test_settable(self):
        from engine.combat import Combatant
        c = Combatant(id=1, name="X")
        c.last_attacker_id = 42
        self.assertEqual(c.last_attacker_id, 42)


# ═════════════════════════════════════════════════════════════════════
# 2. _apply_damage stamps last_attacker_id
# ═════════════════════════════════════════════════════════════════════


class TestApplyDamageStampsAttacker(unittest.TestCase):
    """Source-level check: _apply_damage contains the stamping
    code. The full damage resolution path is unit-tested elsewhere;
    here we pin the byte to catch regressions where someone
    removes the stamping line."""

    def test_apply_damage_contains_stamping(self):
        src = (PROJECT_ROOT / "engine" / "combat.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "target_c.last_attacker_id = actor.id",
            src,
            "_apply_damage should stamp last_attacker_id on hit",
        )


# ═════════════════════════════════════════════════════════════════════
# 3-8. DB state-flip methods
# ═════════════════════════════════════════════════════════════════════


class TestClaimDbMethod(unittest.TestCase):

    def test_claim_flips_state_records_bh(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "BH"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            ok = await db.claim_pc_bounty(
                bounty_id=bid, bh_char_id=chars["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            self.assertTrue(ok)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "claimed")
            self.assertEqual(row["claimed_by"], chars["BH"]["id"])
            self.assertGreater(row["claimed_at"], 0)
        _run(_check())

    def test_claim_on_non_active_fails(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "BH"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.cancel_pc_bounty(bid)
            ok = await db.claim_pc_bounty(
                bounty_id=bid, bh_char_id=chars["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            self.assertFalse(ok)
        _run(_check())


class TestReleaseDbMethod(unittest.TestCase):

    def test_release_reverts_to_active(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "BH"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.claim_pc_bounty(
                bounty_id=bid, bh_char_id=chars["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            ok = await db.release_pc_bounty(bid)
            self.assertTrue(ok)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "active")
            self.assertIsNone(row["claimed_by"])
            self.assertEqual(row["claimed_at"], 0)
        _run(_check())


class TestFulfillDbMethod(unittest.TestCase):

    def test_fulfill_returns_snapshot_flips_state(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "BH"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.claim_pc_bounty(
                bounty_id=bid, bh_char_id=chars["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            snap = await db.fulfill_pc_bounty(
                bounty_id=bid, bh_char_id=chars["BH"]["id"],
            )
            self.assertIsNotNone(snap)
            self.assertEqual(snap["amount"], 5000)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "fulfilled")
            self.assertGreater(row["resolved_at"], 0)
        _run(_check())

    def test_fulfill_active_stamps_bh(self):
        """Active (no claim) → fulfilled with BH stamping."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "BH"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            snap = await db.fulfill_pc_bounty(
                bounty_id=bid, bh_char_id=chars["BH"]["id"],
            )
            self.assertIsNotNone(snap)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "fulfilled")
            self.assertEqual(row["claimed_by"], chars["BH"]["id"])
        _run(_check())


class TestVoidDbMethod(unittest.TestCase):

    def test_void_returns_snapshot_flips_state(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="orig", fee=500,
                duration_seconds=86400,
            )
            snap = await db.void_pc_bounty(
                bounty_id=bid, reason="griefing report",
            )
            self.assertIsNotNone(snap)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "canceled")
            # Reason gets " | VOIDED: ..." appended.
            self.assertIn("VOIDED", row["reason"])
            self.assertIn("griefing report", row["reason"])
        _run(_check())


class TestExpireDbMethod(unittest.TestCase):

    def test_expire_active_works(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            snap = await db.expire_pc_bounty(bid)
            self.assertIsNotNone(snap)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "expired")
        _run(_check())

    def test_expire_non_active_fails(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.cancel_pc_bounty(bid)
            snap = await db.expire_pc_bounty(bid)
            self.assertIsNone(snap)
        _run(_check())


class TestRevertExpiredClaim(unittest.TestCase):

    def test_revert_frees_claim_back_to_active(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "BH"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.claim_pc_bounty(
                bounty_id=bid, bh_char_id=chars["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            ok = await db.revert_expired_claim(bid)
            self.assertTrue(ok)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "active")
            self.assertIsNone(row["claimed_by"])
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 9-10. Tick query methods
# ═════════════════════════════════════════════════════════════════════


class TestListExpiredActive(unittest.TestCase):

    def test_returns_only_past_expiry(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T1", "T2"])
            # T1: expires in 1s (already past for tick purposes)
            await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T1"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=-100,  # already expired
            )
            # T2: expires in 30 days
            await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T2"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=30 * 86400,
            )
            expired = await db.list_expired_active_bounties()
            self.assertEqual(len(expired), 1)
            self.assertEqual(
                expired[0]["target_id"], chars["T1"]["id"]
            )
        _run(_check())


class TestListExpiredClaims(unittest.TestCase):

    def test_returns_only_stale_claims(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T1", "T2", "BH"])
            # Both bounties get claimed.
            b1 = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T1"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=30 * 86400,
            )
            b2 = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T2"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=30 * 86400,
            )
            await db.claim_pc_bounty(
                bounty_id=b1, bh_char_id=chars["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            await db.claim_pc_bounty(
                bounty_id=b2, bh_char_id=chars["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            # Manually backdate b1's claimed_at to be stale.
            await db._db.execute(
                "UPDATE pc_bounties SET claimed_at = ? WHERE id = ?",
                (time.time() - 8 * 86400, b1),
            )
            await db._db.commit()
            stale = await db.list_expired_claims(7 * 86400)
            stale_ids = [r["id"] for r in stale]
            self.assertIn(b1, stale_ids)
            self.assertNotIn(b2, stale_ids)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 11-12. Insurance debt CRUD
# ═════════════════════════════════════════════════════════════════════


class TestInsuranceDebtCrud(unittest.TestCase):

    def test_get_zero_when_unset(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            d = await db.get_insurance_debt(chars["X"]["id"])
            self.assertEqual(d, 0)
        _run(_check())

    def test_add_then_get(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            new_total = await db.add_insurance_debt(
                chars["X"]["id"], 500,
            )
            self.assertEqual(new_total, 500)
            d = await db.get_insurance_debt(chars["X"]["id"])
            self.assertEqual(d, 500)
        _run(_check())

    def test_add_sums(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            await db.add_insurance_debt(chars["X"]["id"], 500)
            new = await db.add_insurance_debt(chars["X"]["id"], 300)
            self.assertEqual(new, 800)
        _run(_check())


class TestPayInsuranceFullClear(unittest.TestCase):

    def test_pay_exact_amount_deletes_row(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            await db.add_insurance_debt(chars["X"]["id"], 500)
            rem = await db.pay_insurance_debt(
                chars["X"]["id"], 500,
            )
            self.assertEqual(rem, 0)
            d = await db.get_insurance_debt(chars["X"]["id"])
            self.assertEqual(d, 0)
        _run(_check())

    def test_pay_partial_leaves_remainder(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            await db.add_insurance_debt(chars["X"]["id"], 500)
            rem = await db.pay_insurance_debt(
                chars["X"]["id"], 200,
            )
            self.assertEqual(rem, 300)
        _run(_check())

    def test_pay_more_than_owed_clears(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            await db.add_insurance_debt(chars["X"]["id"], 500)
            rem = await db.pay_insurance_debt(
                chars["X"]["id"], 1000,
            )
            self.assertEqual(rem, 0)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 13-16. _fire_insurance_and_fulfill (engine/death.py)
# ═════════════════════════════════════════════════════════════════════


class TestFireInsuranceNoBh(unittest.TestCase):

    def test_no_op_when_killer_not_bh(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Killer"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000,
                duration_seconds=86400,
            )
            from engine.death import _fire_insurance_and_fulfill
            await _fire_insurance_and_fulfill(
                db, target_id=chars["T"]["id"],
                killer_id=chars["Killer"]["id"],
                killer_is_bh=False,
            )
            # Bounty stays active.
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "active")
            # No debit to target.
            reloaded = await db.get_character(chars["T"]["id"])
            self.assertEqual(int(reloaded["credits"]), 100000)
        _run(_check())


class TestFireInsuranceNoBounty(unittest.TestCase):

    def test_no_op_when_target_not_bountied(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(
                db, ["Target", "BH"], faction="",
            )
            # Reload BH with BH faction.
            await db._db.execute(
                "UPDATE characters SET faction_id = 'bh_guild' "
                "WHERE id = ?", (chars["BH"]["id"],),
            )
            await db._db.commit()
            from engine.death import _fire_insurance_and_fulfill
            await _fire_insurance_and_fulfill(
                db, target_id=chars["Target"]["id"],
                killer_id=chars["BH"]["id"],
                killer_is_bh=True,
            )
            # Target untouched.
            reloaded = await db.get_character(chars["Target"]["id"])
            self.assertEqual(int(reloaded["credits"]), 100000)
        _run(_check())


class TestFireInsuranceHappy(unittest.TestCase):

    def test_bh_kill_fires_insurance_payout_fulfill(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bh_chars = await _make_chars(
                db, ["BH"], faction="bh_guild",
            )
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000,
                duration_seconds=86400,
            )
            from engine.death import (
                _fire_insurance_and_fulfill, INSURANCE_FLAT, INSURANCE_PCT,
            )
            await _fire_insurance_and_fulfill(
                db, target_id=chars["T"]["id"],
                killer_id=bh_chars["BH"]["id"],
                killer_is_bh=True,
            )
            # Drop 2 rescale: hit = INSURANCE_FLAT + ceil(INSURANCE_PCT% of
            # the 10000 bounty), debited from the target.
            hit = INSURANCE_FLAT + (10000 * INSURANCE_PCT + 99) // 100
            t_reloaded = await db.get_character(chars["T"]["id"])
            self.assertEqual(
                int(t_reloaded["credits"]), 100000 - hit
            )
            # BH paid 80% of 10000 = 8000 cr. (Payout split is unchanged by
            # the hit rescale.)
            bh_reloaded = await db.get_character(
                bh_chars["BH"]["id"]
            )
            self.assertEqual(
                int(bh_reloaded["credits"]), 100000 + 8000
            )
            # Bounty fulfilled.
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "fulfilled")
            self.assertEqual(row["claimed_by"], bh_chars["BH"]["id"])
        _run(_check())


class TestFireInsurancePartialDebt(unittest.TestCase):

    def test_shortfall_accrues_as_debt(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P"])
            target_chars = await _make_chars(
                db, ["T"], credits=300,  # short of 1000 hit
            )
            bh_chars = await _make_chars(
                db, ["BH"], faction="bh_guild",
            )
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=target_chars["T"]["id"],
                amount=10000, reason="r", fee=1000,
                duration_seconds=86400,
            )
            from engine.death import (
                _fire_insurance_and_fulfill, INSURANCE_FLAT, INSURANCE_PCT,
            )
            await _fire_insurance_and_fulfill(
                db, target_id=target_chars["T"]["id"],
                killer_id=bh_chars["BH"]["id"],
                killer_is_bh=True,
            )
            # Drop 2 rescale: hit = INSURANCE_FLAT + ceil(INSURANCE_PCT% of
            # the bounty). Target has 300 cash; the shortfall accrues as
            # debt. Derived from the constants so future tuning of the
            # flat/pct keeps this test honest.
            hit = INSURANCE_FLAT + (10000 * INSURANCE_PCT + 99) // 100
            expected_debt = hit - 300
            t_reloaded = await db.get_character(
                target_chars["T"]["id"]
            )
            self.assertEqual(int(t_reloaded["credits"]), 0)
            debt = await db.get_insurance_debt(
                target_chars["T"]["id"]
            )
            self.assertEqual(debt, expected_debt)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 17-19. +pcbounty claim
# ═════════════════════════════════════════════════════════════════════


class TestClaimCommandHappy(unittest.TestCase):

    def test_bh_can_claim(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bh_chars = await _make_chars(
                db, ["BH"], faction="bh_guild",
            )
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(bh_chars["BH"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", f"claim {bid}")
            )
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "claimed")
            self.assertEqual(
                row["claimed_by"], bh_chars["BH"]["id"]
            )
            joined = "\n".join(sess.sent)
            self.assertIn("Bounty claimed", joined)
        _run(_check())


class TestClaimCommandRequiresBh(unittest.TestCase):

    def test_non_bh_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Random"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["Random"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", f"claim {bid}")
            )
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "active")
            self.assertTrue(
                any("BH Guild members" in l for l in sess.sent)
            )
        _run(_check())


class TestClaimCommandSelfRejected(unittest.TestCase):

    def test_cant_claim_against_self(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P"])
            bh = await _make_chars(
                db, ["TargetWhoIsBH"], faction="bh_guild",
            )
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=bh["TargetWhoIsBH"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(bh["TargetWhoIsBH"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", f"claim {bid}")
            )
            self.assertTrue(
                any("yourself" in l.lower() for l in sess.sent)
            )
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "active")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 20-21. +pcbounty release
# ═════════════════════════════════════════════════════════════════════


class TestReleaseCommandHappy(unittest.TestCase):

    def test_claiming_bh_can_release(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bh = await _make_chars(
                db, ["BH"], faction="bh_guild",
            )
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.claim_pc_bounty(
                bounty_id=bid, bh_char_id=bh["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(bh["BH"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", f"release {bid}")
            )
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "active")
        _run(_check())


class TestReleaseCommandWrongBh(unittest.TestCase):

    def test_other_bh_cant_release(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bh = await _make_chars(
                db, ["BH1", "BH2"], faction="bh_guild",
            )
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.claim_pc_bounty(
                bounty_id=bid, bh_char_id=bh["BH1"]["id"],
                timer_seconds=7 * 86400,
            )
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(bh["BH2"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", f"release {bid}")
            )
            self.assertTrue(
                any("not the BH" in l for l in sess.sent)
            )
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "claimed")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 22. +pcbounty debt — render shape
# ═════════════════════════════════════════════════════════════════════


class TestDebtCommandShowsDebt(unittest.TestCase):

    def test_debt_renders_amount(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            await db.add_insurance_debt(chars["X"]["id"], 700)
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["X"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "debt")
            )
            joined = "\n".join(sess.sent)
            import re as _re
            joined_plain = _re.sub(r'\x1b\[[0-9;]*m', '', joined)
            self.assertIn("700", joined_plain)
        _run(_check())

    def test_zero_debt_says_so(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["X"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "debt")
            )
            self.assertTrue(
                any("no insurance debt" in l.lower()
                    for l in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 23-24. +pcbounty pay
# ═════════════════════════════════════════════════════════════════════


class TestPayCommandHappy(unittest.TestCase):

    def test_pay_full_clears_debt(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            await db.add_insurance_debt(chars["X"]["id"], 500)
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["X"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "pay")
            )
            debt = await db.get_insurance_debt(chars["X"]["id"])
            self.assertEqual(debt, 0)
            reloaded = await db.get_character(chars["X"]["id"])
            self.assertEqual(
                int(reloaded["credits"]), 100000 - 500
            )
        _run(_check())


class TestPayCommandPartial(unittest.TestCase):

    def test_partial_pay_leaves_remainder(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["X"])
            await db.add_insurance_debt(chars["X"]["id"], 500)
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["X"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "pay 200")
            )
            debt = await db.get_insurance_debt(chars["X"]["id"])
            self.assertEqual(debt, 300)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 25-27. @pcbounty admin
# ═════════════════════════════════════════════════════════════════════


class TestAdminVoidRefundsFully(unittest.TestCase):

    def test_void_returns_stake_plus_fee_no_cancel_cut(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Staff"])
            from parser.pc_bounty_commands import (
                BountyCommand, AdminBountyCommand,
            )
            cmd = BountyCommand()
            sess_p = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess_p, db, "+pcbounty",
                         "post T 10000 spurious")
            )
            # P paid 11000; balance 89000.
            sess_s = _FakeSession(chars["Staff"], admin=True)
            adm = AdminBountyCommand()
            # Need bounty id.
            row = await db.get_active_incoming_for_target(
                chars["T"]["id"]
            )
            bid = row["id"]
            await adm.execute(
                _ctx_for(sess_s, db, "@pcbounty",
                         f"void {bid} griefing")
            )
            p_reloaded = await db.get_character(chars["P"]["id"])
            # Full refund: stake + fee = 11000; balance back to 100000.
            self.assertEqual(int(p_reloaded["credits"]), 100000)
            row_after = await db.get_pc_bounty(bid)
            self.assertEqual(row_after["state"], "canceled")
            self.assertIn("VOIDED", row_after["reason"])
        _run(_check())


class TestAdminReviewRenders(unittest.TestCase):

    def test_review_shows_contributors(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Staff"])
            from parser.pc_bounty_commands import (
                BountyCommand, AdminBountyCommand,
            )
            cmd = BountyCommand()
            sess_p = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess_p, db, "+pcbounty",
                         "post T 5000 details")
            )
            row = await db.get_active_incoming_for_target(
                chars["T"]["id"]
            )
            bid = row["id"]
            sess_s = _FakeSession(chars["Staff"], admin=True)
            adm = AdminBountyCommand()
            await adm.execute(
                _ctx_for(sess_s, db, "@pcbounty",
                         f"review {bid}")
            )
            joined = "\n".join(sess_s.sent)
            self.assertIn("Bounty", joined)
            self.assertIn("P", joined)
            self.assertIn("T", joined)
            self.assertIn("contributors", joined)
        _run(_check())


class TestAdminFulfillPayout(unittest.TestCase):

    def test_fulfill_pays_bh(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T", "Staff"])
            bh = await _make_chars(
                db, ["BH"], faction="bh_guild",
            )
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000,
                duration_seconds=86400,
            )
            from parser.pc_bounty_commands import AdminBountyCommand
            sess_s = _FakeSession(chars["Staff"], admin=True)
            adm = AdminBountyCommand()
            await adm.execute(
                _ctx_for(sess_s, db, "@pcbounty",
                         f"fulfill {bid} BH")
            )
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "fulfilled")
            # BH paid 80% of 10000 = 8000
            bh_reloaded = await db.get_character(bh["BH"]["id"])
            self.assertEqual(
                int(bh_reloaded["credits"]), 100000 + 8000
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 28-29. Expiry tick
# ═════════════════════════════════════════════════════════════════════


class TestExpiryTickExpires30Day(unittest.TestCase):

    def test_tick_expires_past_window_and_refunds_stake(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            # P paid 11000 (10000 + 1000 fee).
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=10000, reason="r", fee=1000,
                duration_seconds=-100,  # already expired
            )
            # Manually drain P's credits to verify refund.
            await db.save_character(chars["P"]["id"], credits=0)
            from parser.pc_bounty_commands import (
                run_pc_bounty_expiry_tick,
            )
            summary = await run_pc_bounty_expiry_tick(db)
            self.assertEqual(summary["expired"], 1)
            self.assertEqual(summary["refunded_total"], 10000)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "expired")
            # P got back 10000 (stake only; fee was sunk).
            p_reloaded = await db.get_character(chars["P"]["id"])
            self.assertEqual(int(p_reloaded["credits"]), 10000)
        _run(_check())


class TestExpiryTickRevertsClaim(unittest.TestCase):

    def test_tick_reverts_stale_claim(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bh = await _make_chars(
                db, ["BH"], faction="bh_guild",
            )
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=30 * 86400,
            )
            await db.claim_pc_bounty(
                bounty_id=bid, bh_char_id=bh["BH"]["id"],
                timer_seconds=7 * 86400,
            )
            # Backdate claim to make it stale.
            await db._db.execute(
                "UPDATE pc_bounties SET claimed_at = ? WHERE id = ?",
                (time.time() - 8 * 86400, bid),
            )
            await db._db.commit()
            from parser.pc_bounty_commands import (
                run_pc_bounty_expiry_tick,
            )
            summary = await run_pc_bounty_expiry_tick(db)
            self.assertEqual(summary["reverted"], 1)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "active")
            self.assertIsNone(row["claimed_by"])
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 30. Registration smoke for @pcbounty
# ═════════════════════════════════════════════════════════════════════


class TestRegistrationAdminCmd(unittest.TestCase):

    def test_admin_pcbounty_registers(self):
        from parser.commands import CommandRegistry
        from parser.pc_bounty_commands import (
            register_pc_bounty_commands,
        )
        reg = CommandRegistry()
        register_pc_bounty_commands(reg)
        self.assertIsNotNone(reg.get("+pcbounty"))
        self.assertIsNotNone(reg.get("@pcbounty"))


if __name__ == "__main__":
    unittest.main()
