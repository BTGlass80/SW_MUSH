# -*- coding: utf-8 -*-
"""
tests/test_faction_payroll_break_continue_2026_07_03.py

Regression for the faction payroll treasury-depletion bug in
engine/organizations.py::faction_payroll_tick.

Members are paid ``ORDER BY rank_level DESC`` (get_org_members: highest
rank / biggest stipend first). When the treasury could not afford a
high-rank member's stipend, the loop did ``break`` — which stopped
paying EVERY remaining (lower-rank, cheaper) member, even though the
treasury still held more than enough for their smaller stipends. The fix
is ``continue``: skip the member you can't afford and keep paying the
ones you can. The ``treasury - org_paid < stipend`` guard still bounds
total disbursement to the treasury, so the fix never overdraws — it only
stops starving affordable lower ranks.

Sections
========
  1. TestLowerRankNotStarved    — the core regression: a treasury that
                                  can't cover the top rank still pays the
                                  affordable lower rank (pre-fix: 0).
  2. TestNeverOverdrawsTreasury — total disbursed never exceeds treasury;
                                  a middle stipend is packed in, a too-big
                                  tail is skipped.
  3. TestAllPaidWhenAffordable  — no regression: treasury covering all
                                  members pays everyone.
  4. TestSourceUsesContinue     — guard: the depletion branch is a
                                  ``continue``, not a ``break``.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import sys
import unittest
from pathlib import Path

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


async def _make_char(db, *, name, credits=0):
    acct_cur = await db._db.execute(
        "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
        (f"acct_{name.lower()}_{id(name)}", "x"),
    )
    await db._db.commit()
    account_id = acct_cur.lastrowid
    attrs = json.dumps({"strength": "3D", "perception": "3D"})
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(name, account_id, room_id, attributes, skills, inventory, "
        " credits, wound_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, account_id, 1, attrs, "{}", '{"items":[]}', credits, 0),
    )
    await db._db.commit()
    return cur.lastrowid


async def _make_faction(db, *, treasury):
    org_cur = await db._db.execute(
        "INSERT INTO organizations "
        "(code, name, org_type, treasury, properties) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test_faction", "Test Faction", "faction", treasury, "{}"),
    )
    await db._db.commit()
    return org_cur.lastrowid


async def _add_member(db, org_id, char_id, *, rank_level, standing="good"):
    await db._db.execute(
        "INSERT INTO org_memberships "
        "(char_id, org_id, rank_level, standing) "
        "VALUES (?, ?, ?, ?)",
        (char_id, org_id, rank_level, standing),
    )
    await db._db.commit()


async def _treasury(db, org_id):
    rows = await db._db.execute_fetchall(
        "SELECT treasury FROM organizations WHERE id = ?", (org_id,)
    )
    return int(rows[0]["treasury"])


async def _credits(db, char_id):
    row = await db.get_character(char_id)
    return int(row["credits"])


def _seed_stipends(mapping):
    """Set STIPEND_TABLE[('test_faction', rank)] = amount for each pair."""
    from engine.organizations import STIPEND_TABLE
    for rank, amount in mapping.items():
        STIPEND_TABLE[("test_faction", rank)] = amount


def _clear_stipends(ranks):
    from engine.organizations import STIPEND_TABLE
    for rank in ranks:
        STIPEND_TABLE.pop(("test_faction", rank), None)


# ──────────────────────────────────────────────────────────────────────
# 1. Lower rank must not be starved by an unaffordable higher rank
# ──────────────────────────────────────────────────────────────────────

class TestLowerRankNotStarved(unittest.TestCase):

    def test_affordable_low_rank_paid_despite_unaffordable_high_rank(self):
        from engine.organizations import faction_payroll_tick

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, treasury=120)
            # rank 5 stipend 500 (unaffordable), rank 1 stipend 50 (fits)
            high = await _make_char(db, name="HighRank")
            low = await _make_char(db, name="LowRank")
            await _add_member(db, org_id, high, rank_level=5)
            await _add_member(db, org_id, low, rank_level=1)
            _seed_stipends({5: 500, 1: 50})
            try:
                total = await faction_payroll_tick(db)
                # The low-rank member's 50cr stipend the treasury can
                # easily cover MUST be paid (pre-fix: break -> 0).
                self.assertEqual(await _credits(db, low), 50)
                # The high-rank member stays unpaid (couldn't afford it).
                self.assertEqual(await _credits(db, high), 0)
                # Only the low-rank stipend was disbursed / debited.
                self.assertEqual(total, 50)
                self.assertEqual(await _treasury(db, org_id), 120 - 50)
            finally:
                _clear_stipends([5, 1])
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 2. Never overdraws the treasury
# ──────────────────────────────────────────────────────────────────────

class TestNeverOverdrawsTreasury(unittest.TestCase):

    def test_middle_stipend_packed_tail_skipped_within_budget(self):
        from engine.organizations import faction_payroll_tick

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, treasury=120)
            # ranks 5/3/1 -> 500 / 100 / 50. Only rank 3 (100) fits after
            # rank 5 (500) is skipped; rank 1 (50) then no longer fits
            # (120-100=20 < 50).
            r5 = await _make_char(db, name="R5")
            r3 = await _make_char(db, name="R3")
            r1 = await _make_char(db, name="R1")
            await _add_member(db, org_id, r5, rank_level=5)
            await _add_member(db, org_id, r3, rank_level=3)
            await _add_member(db, org_id, r1, rank_level=1)
            _seed_stipends({5: 500, 3: 100, 1: 50})
            try:
                total = await faction_payroll_tick(db)
                self.assertEqual(await _credits(db, r5), 0)
                self.assertEqual(await _credits(db, r3), 100)
                self.assertEqual(await _credits(db, r1), 0)
                # Total disbursed never exceeds the treasury.
                self.assertEqual(total, 100)
                self.assertLessEqual(total, 120)
                self.assertEqual(await _treasury(db, org_id), 120 - 100)
            finally:
                _clear_stipends([5, 3, 1])
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 3. No regression: everyone paid when the treasury can afford all
# ──────────────────────────────────────────────────────────────────────

class TestAllPaidWhenAffordable(unittest.TestCase):

    def test_full_treasury_pays_every_member(self):
        from engine.organizations import faction_payroll_tick

        async def go():
            db = await _fresh_db()
            org_id = await _make_faction(db, treasury=1000)
            high = await _make_char(db, name="HighA")
            low = await _make_char(db, name="LowA")
            await _add_member(db, org_id, high, rank_level=5)
            await _add_member(db, org_id, low, rank_level=1)
            _seed_stipends({5: 500, 1: 50})
            try:
                total = await faction_payroll_tick(db)
                self.assertEqual(await _credits(db, high), 500)
                self.assertEqual(await _credits(db, low), 50)
                self.assertEqual(total, 550)
                self.assertEqual(await _treasury(db, org_id), 1000 - 550)
            finally:
                _clear_stipends([5, 1])
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 4. Source guard: the depletion branch is a continue, not a break
# ──────────────────────────────────────────────────────────────────────

class TestSourceUsesContinue(unittest.TestCase):

    def test_treasury_depletion_branch_continues(self):
        from engine.organizations import faction_payroll_tick
        src = inspect.getsource(faction_payroll_tick)
        # The depletion guard must not short-circuit the whole loop.
        self.assertIn("treasury - org_paid < stipend", src)
        # No bare `break` on the treasury-depletion line.
        guard = re.search(
            r"if treasury - org_paid < stipend:\s*\n(?:\s*#.*\n)*\s*(\w+)",
            src,
        )
        self.assertIsNotNone(guard, "depletion guard not found in source")
        self.assertEqual(guard.group(1), "continue")
        self.assertNotIn(
            "break  # Treasury depleted", src,
            "the starving `break` must be gone",
        )


if __name__ == "__main__":
    unittest.main()
