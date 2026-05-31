# -*- coding: utf-8 -*-
"""
tests/test_pg2_pc_bounty_session1.py — PG.2.bounty session 1
(May 20 2026).

Per progression_gates_and_consequences_design_v1.md §4 and the
locked PG.2 session 1 design calls. Ships the player surface:
  +pcbounty post / cancel / board / status

Builds on the v18 schema (pc_bounties, bounty_cooldowns,
bh_insurance_debt) + the v30 contributors_json sidecar.

Test sections
=============

  1. TestSchemaV30Migration             — contributors_json shipped
  2. TestPostingFeeHelper               — _posting_fee math
  3. TestCancelRefundHelper             — _cancel_refund_total math
  4. TestProportionalRefunds            — _proportional_refunds math
  5. TestPostPcBountyHappyPath          — DB post + sidecar
  6. TestStackPcBountyAppends           — stack adds to sidecar
  7. TestCancelPcBountySnapshot         — cancel returns snapshot
  8. TestCooldownGet+Set                — cooldown round-trip
  9. TestBountyPostCommandHappyPath     — full post flow + mail
 10. TestBountyPostMinBoundary          — < 1000 cr rejected
 11. TestBountyPostMaxBoundary          — > 50000 cr rejected
 12. TestBountyPostSelfRejected         — self-target rejected
 13. TestBountyPostMissingReasonRej     — empty reason rejected
 14. TestBountyPostInsufficientCredits  — broke poster rejected
 15. TestBountyPostExistingOutgoing     — one outgoing per poster
 16. TestBountyPostStackPath            — second poster stacks
 17. TestBountyPostStackOwnRejected     — primary can't double-up
 18. TestBountyPostCooldown             — cooldown enforced
 19. TestBountyCancelHappyPath          — primary cancels, refunds
 20. TestBountyCancelRefundsStack       — secondaries refunded
 21. TestBountyCancelNoActiveOutgoing   — nothing to cancel msg
 22. TestBountyCancelSetsCooldown       — post-cancel cooldown set
 23. TestBountyBoardRequiresBhGuild     — non-BH rejected
 24. TestBountyBoardListsActive         — board renders bounties
 25. TestBountyStatusBothSides          — outgoing+incoming shown
 26. TestRegistration                   — +pcbounty registers
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ─── shared fixtures ──────────────────────────────────────────────────────


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_chars(db, names: list, *, faction: str = "") -> dict:
    """Create chars w/ optional faction. Returns {name: dict}."""
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
               VALUES (1, ?, 'Human', 1, 100000, ?)""",
            (n, faction),
        )
        out[n] = cur.lastrowid
    await db._db.commit()
    chars = {}
    for n, cid in out.items():
        chars[n] = await db.get_character(cid)
    return chars


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": 0, "is_builder": 0}
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
# 1. Schema v30 migration
# ═════════════════════════════════════════════════════════════════════


class TestSchemaV30Migration(unittest.TestCase):

    def test_schema_version_at_least_30(self):
        from db.database import SCHEMA_VERSION
        self.assertGreaterEqual(SCHEMA_VERSION, 30)

    def test_migration_30_present(self):
        from db.database import MIGRATIONS
        self.assertIn(30, MIGRATIONS)
        joined = " ".join(MIGRATIONS[30])
        self.assertIn("contributors_json", joined)
        self.assertIn("pc_bounties", joined)

    def test_contributors_json_default_empty(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="test", fee=500,
                duration_seconds=86400,
            )
            row = await db.get_pc_bounty(bid)
            contributors = json.loads(row["contributors_json"])
            self.assertEqual(len(contributors), 1)
            self.assertEqual(contributors[0]["poster_id"],
                             chars["P"]["id"])
            self.assertEqual(contributors[0]["amount"], 5000)
            self.assertEqual(contributors[0]["fee"], 500)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 2. _posting_fee helper math
# ═════════════════════════════════════════════════════════════════════


class TestPostingFeeHelper(unittest.TestCase):

    def test_round_numbers(self):
        from parser.pc_bounty_commands import _posting_fee
        self.assertEqual(_posting_fee(1000), 100)
        self.assertEqual(_posting_fee(10000), 1000)
        self.assertEqual(_posting_fee(50000), 5000)

    def test_non_round_rounds_up(self):
        from parser.pc_bounty_commands import _posting_fee
        # 1234 * 10% = 123.4 → 124
        self.assertEqual(_posting_fee(1234), 124)


# ═════════════════════════════════════════════════════════════════════
# 3. _cancel_refund_total helper
# ═════════════════════════════════════════════════════════════════════


class TestCancelRefundHelper(unittest.TestCase):

    def test_round_numbers(self):
        from parser.pc_bounty_commands import _cancel_refund_total
        # 10000 * 25% fee = 2500; refund = 7500
        self.assertEqual(_cancel_refund_total(10000), 7500)

    def test_fee_rounds_up_refund_rounds_down(self):
        from parser.pc_bounty_commands import _cancel_refund_total
        # 1234 * 25% = 308.5 → 309; refund = 925
        self.assertEqual(_cancel_refund_total(1234), 925)


# ═════════════════════════════════════════════════════════════════════
# 4. Proportional refunds
# ═════════════════════════════════════════════════════════════════════


class TestProportionalRefunds(unittest.TestCase):

    def test_single_contributor_gets_full_pool(self):
        from parser.pc_bounty_commands import _proportional_refunds
        contributors = [
            {"poster_id": 1, "amount": 10000, "fee": 1000,
             "added_at": 100.0},
        ]
        out = _proportional_refunds(contributors, refund_pool=7500)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["poster_id"], 1)
        self.assertEqual(out[0]["refund"], 7500)

    def test_equal_stakes_split_evenly(self):
        from parser.pc_bounty_commands import _proportional_refunds
        contributors = [
            {"poster_id": 1, "amount": 5000, "fee": 500,
             "added_at": 100.0},
            {"poster_id": 2, "amount": 5000, "fee": 500,
             "added_at": 200.0},
        ]
        out = _proportional_refunds(contributors, refund_pool=7500)
        # Primary gets remainder (7500 - 3750 = 3750)
        # Secondary gets 7500 * 5000/10000 = 3750
        self.assertEqual(out[0]["refund"], 3750)
        self.assertEqual(out[1]["refund"], 3750)
        self.assertEqual(
            sum(e["refund"] for e in out), 7500
        )

    def test_unequal_stakes_split_proportional(self):
        from parser.pc_bounty_commands import _proportional_refunds
        # Primary stake 10000; secondary 5000. Pool 11250 (75% of 15000)
        contributors = [
            {"poster_id": 1, "amount": 10000, "fee": 1000,
             "added_at": 100.0},
            {"poster_id": 2, "amount": 5000, "fee": 500,
             "added_at": 200.0},
        ]
        out = _proportional_refunds(contributors, refund_pool=11250)
        # Secondary: 11250 * 5000/15000 = 3750
        # Primary: 11250 - 3750 = 7500
        self.assertEqual(out[1]["refund"], 3750)
        self.assertEqual(out[0]["refund"], 7500)
        self.assertEqual(
            sum(e["refund"] for e in out), 11250
        )

    def test_rounding_residue_to_primary(self):
        """100/3 split — primary absorbs the remainder."""
        from parser.pc_bounty_commands import _proportional_refunds
        contributors = [
            {"poster_id": 1, "amount": 333, "fee": 0,
             "added_at": 100.0},
            {"poster_id": 2, "amount": 333, "fee": 0,
             "added_at": 200.0},
            {"poster_id": 3, "amount": 333, "fee": 0,
             "added_at": 300.0},
        ]
        # Pool 100; equal stakes; each 100/999=0 with integer math.
        # Actually: 100 * 333 // 999 = 33 for each secondary.
        # Total distributed to secondaries: 66; primary gets 34.
        out = _proportional_refunds(contributors, refund_pool=100)
        self.assertEqual(out[0]["refund"], 34)
        self.assertEqual(out[1]["refund"], 33)
        self.assertEqual(out[2]["refund"], 33)
        self.assertEqual(
            sum(e["refund"] for e in out), 100
        )


# ═════════════════════════════════════════════════════════════════════
# 5. post_pc_bounty DB method
# ═════════════════════════════════════════════════════════════════════


class TestPostPcBountyHappyPath(unittest.TestCase):

    def test_post_writes_row_with_sidecar(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=10000, reason="theft", fee=1000,
                duration_seconds=30 * 86400,
            )
            row = await db.get_pc_bounty(bid)
            self.assertIsNotNone(row)
            self.assertEqual(row["amount"], 10000)
            self.assertEqual(row["state"], "active")
            self.assertEqual(row["reason"], "theft")
            # Sidecar populated.
            cs = json.loads(row["contributors_json"])
            self.assertEqual(len(cs), 1)
            self.assertEqual(cs[0]["amount"], 10000)
            self.assertEqual(cs[0]["fee"], 1000)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. stack_pc_bounty appends to sidecar
# ═════════════════════════════════════════════════════════════════════


class TestStackPcBountyAppends(unittest.TestCase):

    def test_stack_increments_amount_and_sidecar(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P1", "P2", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P1"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            ok = await db.stack_pc_bounty(
                bounty_id=bid, poster_id=chars["P2"]["id"],
                amount=3000, fee=300,
            )
            self.assertTrue(ok)
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["amount"], 8000)
            cs = json.loads(row["contributors_json"])
            self.assertEqual(len(cs), 2)
            self.assertEqual(cs[1]["poster_id"], chars["P2"]["id"])
            self.assertEqual(cs[1]["amount"], 3000)
        _run(_check())

    def test_stack_on_resolved_returns_false(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P1", "P2", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P1"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.cancel_pc_bounty(bid)
            ok = await db.stack_pc_bounty(
                bounty_id=bid, poster_id=chars["P2"]["id"],
                amount=3000, fee=300,
            )
            self.assertFalse(ok)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 7. cancel_pc_bounty returns snapshot
# ═════════════════════════════════════════════════════════════════════


class TestCancelPcBountySnapshot(unittest.TestCase):

    def test_cancel_returns_pre_cancel_state(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            snap = await db.cancel_pc_bounty(bid)
            self.assertIsNotNone(snap)
            # Snapshot has the active state (pre-cancel snapshot)
            self.assertEqual(snap["amount"], 5000)
            # Row is now canceled
            row = await db.get_pc_bounty(bid)
            self.assertEqual(row["state"], "canceled")
            self.assertGreater(row["resolved_at"], 0)
        _run(_check())

    def test_cancel_returns_none_if_not_active(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            bid = await db.post_pc_bounty(
                poster_id=chars["P"]["id"],
                target_id=chars["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            await db.cancel_pc_bounty(bid)  # 1st cancel
            snap2 = await db.cancel_pc_bounty(bid)  # 2nd cancel
            self.assertIsNone(snap2)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 8. cooldown round-trip
# ═════════════════════════════════════════════════════════════════════


class TestCooldownGetSet(unittest.TestCase):

    def test_zero_when_unset(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            cd = await db.get_bounty_cooldown(
                chars["P"]["id"], chars["T"]["id"]
            )
            self.assertEqual(cd, 0.0)
        _run(_check())

    def test_set_then_get_roundtrip(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            future = time.time() + 1000
            await db.set_bounty_cooldown(
                chars["P"]["id"], chars["T"]["id"], future
            )
            cd = await db.get_bounty_cooldown(
                chars["P"]["id"], chars["T"]["id"]
            )
            self.assertAlmostEqual(cd, future, delta=0.01)
        _run(_check())

    def test_upsert_replaces(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            await db.set_bounty_cooldown(
                chars["P"]["id"], chars["T"]["id"], 1000.0
            )
            await db.set_bounty_cooldown(
                chars["P"]["id"], chars["T"]["id"], 2000.0
            )
            cd = await db.get_bounty_cooldown(
                chars["P"]["id"], chars["T"]["id"]
            )
            self.assertEqual(cd, 2000.0)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 9. +pcbounty post — happy path
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostCommandHappyPath(unittest.TestCase):

    def test_post_debits_credits_creates_bounty_sends_mail(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Solo", "Greedo"])

            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["Solo"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post Greedo 10000 he shot first")
            )
            joined = "\n".join(sess.sent)
            self.assertIn("Bounty posted", joined)
            # Credits debited: 10000 + 1000 fee = 11000
            reloaded = await db.get_character(chars["Solo"]["id"])
            self.assertEqual(
                int(reloaded["credits"]), 100000 - 11000
            )
            # Bounty exists
            row = await db.get_active_incoming_for_target(
                chars["Greedo"]["id"]
            )
            self.assertIsNotNone(row)
            self.assertEqual(row["amount"], 10000)
            # Mail sent
            mail_rows = await db._db.execute_fetchall(
                "SELECT * FROM mail WHERE sender_id = ?",
                (chars["Solo"]["id"],),
            )
            self.assertEqual(len(mail_rows), 1)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 10. +pcbounty post — min boundary
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostMinBoundary(unittest.TestCase):

    def test_below_min_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T 500 too small")
            )
            self.assertTrue(
                any("Minimum bounty" in l for l in sess.sent)
            )
            # No bounty created
            row = await db.get_active_incoming_for_target(
                chars["T"]["id"]
            )
            self.assertIsNone(row)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 11. +pcbounty post — max boundary
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostMaxBoundary(unittest.TestCase):

    def test_above_max_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T 100000 too big")
            )
            self.assertTrue(
                any("Maximum bounty" in l for l in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 12. +pcbounty post — self-target rejected
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostSelfRejected(unittest.TestCase):

    def test_cannot_bounty_self(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Solo"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["Solo"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post Solo 5000 reason")
            )
            self.assertTrue(
                any("cannot post a bounty on yourself" in l
                    for l in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 13. +pcbounty post — missing reason rejected
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostMissingReasonRej(unittest.TestCase):

    def test_no_reason_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            # Missing reason → usage line shown
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "post T 5000")
            )
            joined = "\n".join(sess.sent)
            self.assertIn("Usage", joined)
            row = await db.get_active_incoming_for_target(
                chars["T"]["id"]
            )
            self.assertIsNone(row)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 14. +pcbounty post — insufficient credits
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostInsufficientCredits(unittest.TestCase):

    def test_broke_poster_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            # Drain poster to 100 credits.
            await db.save_character(chars["P"]["id"], credits=100)
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T 5000 broke")
            )
            self.assertTrue(
                any("don't have enough credits" in l
                    for l in sess.sent)
            )
            # No bounty created.
            row = await db.get_active_incoming_for_target(
                chars["T"]["id"]
            )
            self.assertIsNone(row)
            # No credits taken.
            reloaded = await db.get_character(chars["P"]["id"])
            self.assertEqual(int(reloaded["credits"]), 100)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 15. +pcbounty post — one outgoing per poster
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostExistingOutgoing(unittest.TestCase):

    def test_second_outgoing_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T1", "T2"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            # First bounty.
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T1 5000 one")
            )
            sess.sent.clear()
            # Second outgoing on different target should reject.
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T2 5000 two")
            )
            self.assertTrue(
                any("active outgoing bounty" in l
                    for l in sess.sent)
            )
            row = await db.get_active_incoming_for_target(
                chars["T2"]["id"]
            )
            self.assertIsNone(row)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 16. +pcbounty post — stacking path
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostStackPath(unittest.TestCase):

    def test_second_poster_stacks_on_existing(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P1", "P2", "T"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess1 = _FakeSession(chars["P1"])
            await cmd.execute(
                _ctx_for(sess1, db, "+pcbounty",
                         "post T 5000 primary post")
            )
            sess2 = _FakeSession(chars["P2"])
            await cmd.execute(
                _ctx_for(sess2, db, "+pcbounty",
                         "post T 3000 stacking on")
            )
            joined = "\n".join(sess2.sent)
            self.assertIn("Bounty stacked", joined)
            row = await db.get_active_incoming_for_target(
                chars["T"]["id"]
            )
            self.assertEqual(row["amount"], 8000)
            cs = json.loads(row["contributors_json"])
            self.assertEqual(len(cs), 2)
            # Primary is still P1
            self.assertEqual(row["poster_id"], chars["P1"]["id"])
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 17. +pcbounty post — primary can't stack-on-own
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostStackOwnRejected(unittest.TestCase):

    def test_primary_self_stack_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T 5000 first")
            )
            sess.sent.clear()
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T 3000 second")
            )
            self.assertTrue(
                any("already the primary poster" in l
                    for l in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 18. +pcbounty post — cooldown enforced
# ═════════════════════════════════════════════════════════════════════


class TestBountyPostCooldown(unittest.TestCase):

    def test_cooldown_blocks_repost(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            # Set cooldown 1000s into future.
            await db.set_bounty_cooldown(
                chars["P"]["id"], chars["T"]["id"],
                time.time() + 1000,
            )
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T 5000 try")
            )
            self.assertTrue(
                any("cooldown" in l.lower() for l in sess.sent)
            )
            row = await db.get_active_incoming_for_target(
                chars["T"]["id"]
            )
            self.assertIsNone(row)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 19. +pcbounty cancel — happy path (single contributor)
# ═════════════════════════════════════════════════════════════════════


class TestBountyCancelHappyPath(unittest.TestCase):

    def test_primary_cancel_refunds_75pct(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T 10000 reason")
            )
            # After post: paid 11000; balance 89000.
            sess.sent.clear()
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "cancel")
            )
            reloaded = await db.get_character(chars["P"]["id"])
            # Refund = 7500 (75% of 10000); fee 2500 sunk.
            # Final balance: 89000 + 7500 = 96500
            self.assertEqual(int(reloaded["credits"]), 96500)
            joined = "\n".join(sess.sent)
            self.assertIn("canceled", joined.lower())
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 20. +pcbounty cancel refunds stacked contributors
# ═════════════════════════════════════════════════════════════════════


class TestBountyCancelRefundsStack(unittest.TestCase):

    def test_secondaries_get_proportional_refunds(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P1", "P2", "T"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            # P1 posts 10000 (pays 11000; balance 89000)
            sess1 = _FakeSession(chars["P1"])
            await cmd.execute(
                _ctx_for(sess1, db, "+pcbounty",
                         "post T 10000 r1")
            )
            # P2 stacks 5000 (pays 5500; balance 94500)
            sess2 = _FakeSession(chars["P2"])
            await cmd.execute(
                _ctx_for(sess2, db, "+pcbounty",
                         "post T 5000 r2")
            )
            # P1 cancels. Total escrow 15000; refund pool 11250.
            # Proportional: P1 gets 11250 * 10000/15000 = 7500
            # (primary absorbs rounding); P2 gets 11250 * 5000/15000 = 3750.
            sess1.sent.clear()
            await cmd.execute(
                _ctx_for(sess1, db, "+pcbounty", "cancel")
            )
            p1_reloaded = await db.get_character(chars["P1"]["id"])
            p2_reloaded = await db.get_character(chars["P2"]["id"])
            # P1: 89000 + 7500 = 96500
            self.assertEqual(int(p1_reloaded["credits"]), 96500)
            # P2: 94500 + 3750 = 98250
            self.assertEqual(int(p2_reloaded["credits"]), 98250)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 21. +pcbounty cancel — no active outgoing
# ═════════════════════════════════════════════════════════════════════


class TestBountyCancelNoActiveOutgoing(unittest.TestCase):

    def test_no_outgoing_says_so(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Solo"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["Solo"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "cancel")
            )
            self.assertTrue(
                any("no active outgoing bounty" in l.lower()
                    for l in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 22. +pcbounty cancel sets cooldown
# ═════════════════════════════════════════════════════════════════════


class TestBountyCancelSetsCooldown(unittest.TestCase):

    def test_post_cancel_cooldown_in_place(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["P", "T"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["P"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty",
                         "post T 5000 reason")
            )
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "cancel")
            )
            cd = await db.get_bounty_cooldown(
                chars["P"]["id"], chars["T"]["id"]
            )
            self.assertGreater(cd, time.time() + 86400 * 29)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 23. +pcbounty board — BH Guild gating
# ═════════════════════════════════════════════════════════════════════


class TestBountyBoardRequiresBhGuild(unittest.TestCase):

    def test_non_bh_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Random"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["Random"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "board")
            )
            self.assertTrue(
                any("BH Guild members only" in l for l in sess.sent)
            )
        _run(_check())

    def test_bh_guild_member_sees_board(self):
        async def _check():
            db = await _fresh_db()
            # BH Guild faction.
            bh = await _make_chars(db, ["Bossk"], faction="bh_guild")
            others = await _make_chars(db, ["P", "T"])
            # Post a bounty.
            await db.post_pc_bounty(
                poster_id=others["P"]["id"],
                target_id=others["T"]["id"],
                amount=5000, reason="r", fee=500,
                duration_seconds=86400,
            )
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(bh["Bossk"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "board")
            )
            joined = "\n".join(sess.sent)
            # Board renders the bounty.
            self.assertIn("T", joined)  # target name
            self.assertNotIn("BH Guild members only", joined)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 24. +pcbounty board lists active bounties
# ═════════════════════════════════════════════════════════════════════


class TestBountyBoardListsActive(unittest.TestCase):

    def test_empty_board_shows_empty_msg(self):
        async def _check():
            db = await _fresh_db()
            bh = await _make_chars(db, ["Bossk"], faction="bh_guild")
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(bh["Bossk"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "board")
            )
            self.assertTrue(
                any("No active bounties" in l for l in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 25. +pcbounty status — both sides shown
# ═════════════════════════════════════════════════════════════════════


class TestBountyStatusBothSides(unittest.TestCase):

    def test_outgoing_and_incoming_visible(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["A", "B", "C"])
            # A posts on B.
            await db.post_pc_bounty(
                poster_id=chars["A"]["id"],
                target_id=chars["B"]["id"],
                amount=5000, reason="r1", fee=500,
                duration_seconds=86400,
            )
            # C posts on A.
            await db.post_pc_bounty(
                poster_id=chars["C"]["id"],
                target_id=chars["A"]["id"],
                amount=7000, reason="r2", fee=700,
                duration_seconds=86400,
            )
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["A"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "status")
            )
            joined = "\n".join(sess.sent)
            self.assertIn("Outgoing", joined)
            self.assertIn("Incoming", joined)
            self.assertIn("B", joined)
            self.assertIn("C", joined)
        _run(_check())

    def test_no_bounties_says_so(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Solo"])
            from parser.pc_bounty_commands import BountyCommand
            cmd = BountyCommand()
            sess = _FakeSession(chars["Solo"])
            await cmd.execute(
                _ctx_for(sess, db, "+pcbounty", "status")
            )
            self.assertTrue(
                any("no active outgoing or incoming" in l.lower()
                    for l in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 26. Registration
# ═════════════════════════════════════════════════════════════════════


class TestRegistration(unittest.TestCase):

    def test_pcbounty_registers(self):
        from parser.commands import CommandRegistry
        from parser.pc_bounty_commands import (
            register_pc_bounty_commands,
        )
        reg = CommandRegistry()
        register_pc_bounty_commands(reg)
        self.assertIsNotNone(reg.get("+pcbounty"))


if __name__ == "__main__":
    unittest.main()
