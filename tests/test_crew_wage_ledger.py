# -*- coding: utf-8 -*-
"""
tests/test_crew_wage_ledger.py -- per-drop test for the crew-wage ledger fix.

Verifies that ``Database.deduct_crew_wages`` routes the recurring wage sink
through ``adjust_credits`` (tag ``"crew_wages"``) rather than writing the
credits column directly via ``save_character``.

Three assertions per the spec:
  (a) Balance is correct after deduction.
  (b) A credit_log entry tagged ``"crew_wages"`` exists for the deducted amount.
  (c) An NPC that cannot be paid is dismissed (affordability behavior unchanged).
"""
import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fresh_db(char_id: int = 1, start_credits: int = 1000):
    """Minimal in-memory Database with characters, credit_log, and npcs tables.

    No foreign-key constraints (SQLite FK enforcement is off by default) so
    the test is hermetic without needing the full schema.
    """
    from db.database import Database
    db = Database(":memory:")
    await db.connect()

    # Minimal characters table — only columns deduct_crew_wages / adjust_credits
    # actually touch.
    await db._db.execute(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)"
    )
    await db._db.execute(
        """CREATE TABLE credit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id     INTEGER NOT NULL,
            delta       INTEGER NOT NULL,
            source      TEXT NOT NULL,
            balance     INTEGER NOT NULL,
            created_at  REAL NOT NULL
        )"""
    )
    # Minimal npcs table matching the real schema columns used by the method.
    await db._db.execute(
        """CREATE TABLE npcs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            room_id          INTEGER,
            hired_by         INTEGER,
            hire_wage        INTEGER DEFAULT 0,
            assigned_ship    INTEGER,
            assigned_station TEXT DEFAULT '',
            hired_at         TEXT DEFAULT ''
        )"""
    )

    await db._db.execute(
        "INSERT INTO characters (id, credits) VALUES (?, ?)",
        (char_id, start_credits),
    )
    await db._db.commit()
    return db


async def _balance(db, char_id: int = 1) -> int:
    rows = await db._db.execute_fetchall(
        "SELECT credits FROM characters WHERE id = ?", (char_id,)
    )
    return int(rows[0]["credits"]) if rows else None


async def _credit_log_rows(db, char_id: int = 1):
    rows = await db._db.execute_fetchall(
        "SELECT char_id, delta, source, balance FROM credit_log "
        "WHERE char_id = ? ORDER BY id",
        (char_id,),
    )
    return [dict(r) for r in (rows or [])]


async def _insert_npc(db, name: str, hired_by: int, wage: int) -> int:
    """Insert a minimal hired NPC and return its id."""
    cursor = await db._db.execute(
        "INSERT INTO npcs (name, hired_by, hire_wage) VALUES (?, ?, ?)",
        (name, hired_by, wage),
    )
    await db._db.commit()
    return cursor.lastrowid


async def _is_dismissed(db, npc_id: int) -> bool:
    """Return True if the NPC's hired_by is NULL (dismissed)."""
    rows = await db._db.execute_fetchall(
        "SELECT hired_by FROM npcs WHERE id = ?", (npc_id,)
    )
    return not rows or rows[0]["hired_by"] is None


# ============================================================================
# Tests
# ============================================================================

class TestDeductCrewWagesLedgerRouting(unittest.TestCase):
    """(a) Balance correct, (b) credit_log entry present with correct tag."""

    def test_balance_correct_after_deduction(self):
        """Paying one NPC deducts exactly the wage from the character's balance."""
        async def go():
            db = await _fresh_db(start_credits=500)
            await _insert_npc(db, "Kix", hired_by=1, wage=100)
            total, departed = await db.deduct_crew_wages(1)
            self.assertEqual(total, 100)
            self.assertEqual(departed, [])
            self.assertEqual(await _balance(db), 400)
        _run(go())

    def test_credit_log_entry_tagged_crew_wages(self):
        """A credit_log entry with tag 'crew_wages' is written for the deduction."""
        async def go():
            db = await _fresh_db(start_credits=500)
            await _insert_npc(db, "Kix", hired_by=1, wage=100)
            await db.deduct_crew_wages(1)
            rows = await _credit_log_rows(db)
            self.assertEqual(len(rows), 1, "Expected exactly one ledger entry")
            entry = rows[0]
            self.assertEqual(entry["source"], "crew_wages",
                             "Recurring wage sink must use tag 'crew_wages'")
            self.assertEqual(entry["delta"], -100,
                             "Ledger delta must be the negated deduction amount")
            self.assertEqual(entry["balance"], 400,
                             "Ledger balance must reflect the post-deduction balance")
        _run(go())

    def test_multiple_npcs_deducted_and_logged_as_one_entry(self):
        """Multiple affordable NPCs: total deducted correctly, one ledger entry."""
        async def go():
            db = await _fresh_db(start_credits=1000)
            await _insert_npc(db, "Kix", hired_by=1, wage=100)
            await _insert_npc(db, "Waxer", hired_by=1, wage=200)
            total, departed = await db.deduct_crew_wages(1)
            self.assertEqual(total, 300)
            self.assertEqual(departed, [])
            self.assertEqual(await _balance(db), 700)
            rows = await _credit_log_rows(db)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["delta"], -300)
            self.assertEqual(rows[0]["source"], "crew_wages")
        _run(go())

    def test_no_log_entry_when_nothing_deducted(self):
        """If no wages are owed (no NPCs), no ledger entry is written."""
        async def go():
            db = await _fresh_db(start_credits=500)
            total, departed = await db.deduct_crew_wages(1)
            self.assertEqual(total, 0)
            self.assertEqual(departed, [])
            rows = await _credit_log_rows(db)
            self.assertEqual(rows, [], "No ledger entry when nothing deducted")
        _run(go())


class TestDeductCrewWagesAffordabilityUnchanged(unittest.TestCase):
    """(c) Unaffordable NPC is still dismissed — affordability behavior unchanged."""

    def test_unaffordable_npc_is_dismissed(self):
        """An NPC whose wage exceeds remaining credits is dismissed (hired_by=NULL)."""
        async def go():
            db = await _fresh_db(start_credits=50)
            npc_id = await _insert_npc(db, "Boil", hired_by=1, wage=100)
            total, departed = await db.deduct_crew_wages(1)
            self.assertEqual(total, 0, "No credits deducted when NPC can't be paid")
            self.assertIn("Boil", departed, "Unaffordable NPC should be in departed list")
            self.assertTrue(await _is_dismissed(db, npc_id),
                            "Unaffordable NPC must be dismissed (hired_by=NULL)")
            # Balance unchanged — no credits deducted.
            self.assertEqual(await _balance(db), 50)
            # No ledger entry since total_deducted == 0.
            rows = await _credit_log_rows(db)
            self.assertEqual(rows, [])
        _run(go())

    def test_mixed_afford_and_unafford(self):
        """Affordable NPC is paid; unaffordable NPC is dismissed; one ledger entry."""
        async def go():
            db = await _fresh_db(start_credits=100)
            paid_id = await _insert_npc(db, "Kix", hired_by=1, wage=100)
            broke_id = await _insert_npc(db, "Hardcase", hired_by=1, wage=500)
            total, departed = await db.deduct_crew_wages(1)
            # After paying Kix (100), balance is 0 — Hardcase (500) can't be paid.
            self.assertEqual(total, 100)
            self.assertIn("Hardcase", departed)
            self.assertNotIn("Kix", departed)
            self.assertEqual(await _balance(db), 0)
            self.assertFalse(await _is_dismissed(db, paid_id),
                             "Affordable NPC should remain hired")
            self.assertTrue(await _is_dismissed(db, broke_id),
                            "Unaffordable NPC must be dismissed")
            rows = await _credit_log_rows(db)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["delta"], -100)
            self.assertEqual(rows[0]["source"], "crew_wages")
        _run(go())


if __name__ == "__main__":
    unittest.main()
