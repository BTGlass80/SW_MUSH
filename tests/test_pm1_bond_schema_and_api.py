# -*- coding: utf-8 -*-
"""
tests/test_pm1_bond_schema_and_api.py — P-M.1 Padawan-Master bond
foundation layer (May 19, 2026).

P-M.1 ships the Database foundation for the Padawan-Master system
per ``padawan_master_system_design_v1.md`` §4.3:

  - Schema v28: ``master_padawan_bond`` table + two indexes
  - DB API: create_bond, get_bond, get_active_bond_for_padawan,
    get_active_bonds_for_master, dissolve_bond, knight_bond,
    fall_bond, record_trial_passed

Commands (+master, +padawan, +teach, +spar, etc.), narrative
memory cross-writing, and the Trials engine are P-M.2 and beyond.
This drop is the substrate they all build on.

Why ship it now: schema migrations are best landed in their own
drop, before consumer code attaches dependencies. Shipping P-M.1
in isolation means P-M.2 can iterate freely on commands without
touching the schema.

Test sections
=============

  1. TestSchemaVersionBump         — version is 28
  2. TestBondTableShape            — CREATE TABLE produced the
                                     expected columns + types
  3. TestBondIndexes               — both indexes exist
  4. TestCreateBond                — happy path
  5. TestCreateBondInvariants      — Padawan-at-most-one-active rule
  6. TestGetActiveBondForPadawan   — returns active, None otherwise
  7. TestGetActiveBondsForMaster   — returns list (plural by design)
  8. TestDissolveBond              — happy path + idempotency
  9. TestKnightBond                — happy path + trials_passed
 10. TestFallBond                  — happy path
 11. TestRecordTrialPassed         — append + idempotent + malformed
 12. TestForeignKeyCascade         — DELETE characters cascades
                                     to bond rows
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


async def _fresh_db():
    """Initialize a clean in-memory DB at SCHEMA_VERSION."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_two_chars(db) -> tuple[int, int]:
    """Create two characters in the DB. Returns (master_id,
    padawan_id). Both are bare-minimum rows — just enough to act
    as FK targets for the bond."""
    # accounts table needs at least one row before characters can
    # FK to it.
    await db._db.execute(
        """INSERT INTO accounts (username, password_hash, email)
           VALUES ('test', 'hash', 'test@example.com')"""
    )
    cur = await db._db.execute(
        """INSERT INTO characters (account_id, name, species)
           VALUES (1, 'Master Kira', 'Human')"""
    )
    master_id = cur.lastrowid
    cur = await db._db.execute(
        """INSERT INTO characters (account_id, name, species)
           VALUES (1, 'Padawan Sela', 'Human')"""
    )
    padawan_id = cur.lastrowid
    await db._db.commit()
    return master_id, padawan_id


# ═════════════════════════════════════════════════════════════════════
# 1. Schema version bumped
# ═════════════════════════════════════════════════════════════════════


class TestSchemaVersionBump(unittest.TestCase):

    def test_schema_version_is_28(self):
        # Relaxed to >= 28 (originally == 28) to allow future
        # migrations to bump without breaking this test. The P-M.1
        # contract is "v28 introduced the bond table"; later
        # migrations may co-exist. P-M.2 (May 20 2026) bumped to
        # v29 to add characters.master_cap. If you're bumping past
        # 29, also confirm the bond schema is still intact via the
        # TestBondTableShape tests below.
        from db.database import SCHEMA_VERSION
        self.assertGreaterEqual(SCHEMA_VERSION, 28)

    def test_migration_28_registered(self):
        from db.database import MIGRATIONS
        self.assertIn(28, MIGRATIONS)
        # Migration should contain the CREATE TABLE + 2 indexes.
        self.assertEqual(len(MIGRATIONS[28]), 3)


# ═════════════════════════════════════════════════════════════════════
# 2. Bond table shape
# ═════════════════════════════════════════════════════════════════════


class TestBondTableShape(unittest.TestCase):

    def test_table_columns_present(self):
        async def _check():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "PRAGMA table_info(master_padawan_bond)")
            cols = {r["name"]: dict(r) for r in rows}
            self.assertIn("id", cols)
            self.assertIn("master_char_id", cols)
            self.assertIn("padawan_char_id", cols)
            self.assertIn("bond_established_at", cols)
            self.assertIn("bond_status", cols)
            self.assertIn("dissolved_at", cols)
            self.assertIn("dissolved_reason", cols)
            self.assertIn("knight_promotion_at", cols)
            self.assertIn("trials_passed_json", cols)
            # bond_status has a CHECK constraint and NOT NULL.
            self.assertEqual(cols["bond_status"]["notnull"], 1)
            # master and padawan are NOT NULL.
            self.assertEqual(cols["master_char_id"]["notnull"], 1)
            self.assertEqual(cols["padawan_char_id"]["notnull"], 1)
            await db.close()
        _run(_check())

    def test_default_bond_status_is_active(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            # Insert without specifying bond_status; default should
            # take over.
            await db._db.execute(
                """INSERT INTO master_padawan_bond
                   (master_char_id, padawan_char_id)
                   VALUES (?, ?)""",
                (mid, pid),
            )
            await db._db.commit()
            rows = await db._db.execute_fetchall(
                "SELECT bond_status FROM master_padawan_bond")
            self.assertEqual(rows[0]["bond_status"], "active")
            await db.close()
        _run(_check())

    def test_check_constraint_rejects_invalid_status(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            with self.assertRaises(Exception):
                await db._db.execute(
                    """INSERT INTO master_padawan_bond
                       (master_char_id, padawan_char_id, bond_status)
                       VALUES (?, ?, ?)""",
                    (mid, pid, "invalid_status"),
                )
                await db._db.commit()
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 3. Indexes
# ═════════════════════════════════════════════════════════════════════


class TestBondIndexes(unittest.TestCase):

    def test_both_indexes_present(self):
        async def _check():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                """SELECT name FROM sqlite_master
                   WHERE type='index'
                   AND tbl_name='master_padawan_bond'""")
            names = {r["name"] for r in rows}
            self.assertIn("idx_bond_master", names)
            self.assertIn("idx_bond_padawan", names)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 4. create_bond happy path
# ═════════════════════════════════════════════════════════════════════


class TestCreateBond(unittest.TestCase):

    def test_create_bond_returns_id(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            self.assertIsInstance(bond_id, int)
            self.assertGreater(bond_id, 0)
            await db.close()
        _run(_check())

    def test_create_bond_persists_active(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["master_char_id"], mid)
            self.assertEqual(bond["padawan_char_id"], pid)
            self.assertEqual(bond["bond_status"], "active")
            self.assertEqual(bond["trials_passed_json"], "[]")
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 5. Padawan-at-most-one-active invariant
# ═════════════════════════════════════════════════════════════════════


class TestCreateBondInvariants(unittest.TestCase):

    def test_padawan_double_bond_rejected(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            # Make a second master.
            cur = await db._db.execute(
                """INSERT INTO characters (account_id, name, species)
                   VALUES (1, 'Master Two', 'Human')"""
            )
            mid2 = cur.lastrowid
            await db._db.commit()

            await db.create_bond(mid, pid)
            with self.assertRaises(ValueError):
                await db.create_bond(mid2, pid)
            # The first bond should still be active.
            active = await db.get_active_bond_for_padawan(pid)
            self.assertIsNotNone(active)
            self.assertEqual(active["master_char_id"], mid)
            await db.close()
        _run(_check())

    def test_padawan_can_rebond_after_dissolve(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            cur = await db._db.execute(
                """INSERT INTO characters (account_id, name, species)
                   VALUES (1, 'Master Two', 'Human')"""
            )
            mid2 = cur.lastrowid
            await db._db.commit()

            bond1 = await db.create_bond(mid, pid)
            await db.dissolve_bond(bond1, reason="test")
            # Now a new bond should be allowed.
            bond2 = await db.create_bond(mid2, pid)
            self.assertNotEqual(bond1, bond2)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. get_active_bond_for_padawan
# ═════════════════════════════════════════════════════════════════════


class TestGetActiveBondForPadawan(unittest.TestCase):

    def test_returns_active_bond(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            await db.create_bond(mid, pid)
            bond = await db.get_active_bond_for_padawan(pid)
            self.assertIsNotNone(bond)
            self.assertEqual(bond["master_char_id"], mid)
            await db.close()
        _run(_check())

    def test_returns_none_if_no_active_bond(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond = await db.get_active_bond_for_padawan(pid)
            self.assertIsNone(bond)
            await db.close()
        _run(_check())

    def test_returns_none_after_dissolve(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            await db.dissolve_bond(bond_id, reason="test")
            bond = await db.get_active_bond_for_padawan(pid)
            self.assertIsNone(bond)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 7. get_active_bonds_for_master
# ═════════════════════════════════════════════════════════════════════


class TestGetActiveBondsForMaster(unittest.TestCase):

    def test_returns_empty_list_no_bonds(self):
        async def _check():
            db = await _fresh_db()
            mid, _ = await _make_two_chars(db)
            bonds = await db.get_active_bonds_for_master(mid)
            self.assertEqual(bonds, [])
            await db.close()
        _run(_check())

    def test_returns_list_one_active(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            await db.create_bond(mid, pid)
            bonds = await db.get_active_bonds_for_master(mid)
            self.assertEqual(len(bonds), 1)
            self.assertEqual(bonds[0]["padawan_char_id"], pid)
            await db.close()
        _run(_check())

    def test_returns_list_multiple_active(self):
        """Schema and query support multiple active bonds per Master
        (Council-authorized post-launch per design §4.3). The
        per-launch cap of 1 is enforced at the command/UI layer,
        not in the DB API."""
        async def _check():
            db = await _fresh_db()
            mid, pid1 = await _make_two_chars(db)
            cur = await db._db.execute(
                """INSERT INTO characters (account_id, name, species)
                   VALUES (1, 'Padawan Two', 'Human')"""
            )
            pid2 = cur.lastrowid
            await db._db.commit()
            await db.create_bond(mid, pid1)
            await db.create_bond(mid, pid2)
            bonds = await db.get_active_bonds_for_master(mid)
            self.assertEqual(len(bonds), 2)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 8. dissolve_bond
# ═════════════════════════════════════════════════════════════════════


class TestDissolveBond(unittest.TestCase):

    def test_dissolve_active_bond_succeeds(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            ok = await db.dissolve_bond(bond_id, reason="mutual release")
            self.assertTrue(ok)
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "dissolved")
            self.assertEqual(bond["dissolved_reason"], "mutual release")
            self.assertIsNotNone(bond["dissolved_at"])
            await db.close()
        _run(_check())

    def test_dissolve_already_dissolved_is_noop(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            await db.dissolve_bond(bond_id, reason="first")
            # Second call should return False (already dissolved).
            ok = await db.dissolve_bond(bond_id, reason="second")
            self.assertFalse(ok)
            # First reason preserved.
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["dissolved_reason"], "first")
            await db.close()
        _run(_check())

    def test_dissolve_nonexistent_returns_false(self):
        async def _check():
            db = await _fresh_db()
            ok = await db.dissolve_bond(99999, reason="x")
            self.assertFalse(ok)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 9. knight_bond
# ═════════════════════════════════════════════════════════════════════


class TestKnightBond(unittest.TestCase):

    def test_knight_bond_with_trials_list(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            ok = await db.knight_bond(
                bond_id,
                trials_passed=["Skill", "Courage", "Flesh", "Spirit",
                               "Insight"],
            )
            self.assertTrue(ok)
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "knighted")
            self.assertIsNotNone(bond["knight_promotion_at"])
            passed = json.loads(bond["trials_passed_json"])
            self.assertEqual(set(passed), {
                "Skill", "Courage", "Flesh", "Spirit", "Insight"})
            await db.close()
        _run(_check())

    def test_knight_bond_preserves_prior_trials_when_none(self):
        """When trials_passed=None, the existing trials_passed_json
        on the row is preserved. Supports the
        record_trial_passed → knight_bond(trials_passed=None) flow."""
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            await db.record_trial_passed(bond_id, "Skill")
            await db.record_trial_passed(bond_id, "Courage")
            ok = await db.knight_bond(bond_id, trials_passed=None)
            self.assertTrue(ok)
            bond = await db.get_bond(bond_id)
            passed = json.loads(bond["trials_passed_json"])
            self.assertEqual(set(passed), {"Skill", "Courage"})
            await db.close()
        _run(_check())

    def test_knight_non_active_bond_returns_false(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            await db.dissolve_bond(bond_id, reason="test")
            ok = await db.knight_bond(bond_id, trials_passed=["Skill"])
            self.assertFalse(ok)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 10. fall_bond
# ═════════════════════════════════════════════════════════════════════


class TestFallBond(unittest.TestCase):

    def test_fall_active_bond_succeeds(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            ok = await db.fall_bond(bond_id, reason="Killed innocents")
            self.assertTrue(ok)
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "fallen")
            self.assertEqual(bond["dissolved_reason"], "Killed innocents")
            await db.close()
        _run(_check())

    def test_fall_already_dissolved_returns_false(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            await db.dissolve_bond(bond_id, reason="released")
            ok = await db.fall_bond(bond_id, reason="cant fall now")
            self.assertFalse(ok)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 11. record_trial_passed
# ═════════════════════════════════════════════════════════════════════


class TestRecordTrialPassed(unittest.TestCase):

    def test_record_appends(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            ok1 = await db.record_trial_passed(bond_id, "Skill")
            self.assertTrue(ok1)
            ok2 = await db.record_trial_passed(bond_id, "Courage")
            self.assertTrue(ok2)
            bond = await db.get_bond(bond_id)
            self.assertEqual(
                json.loads(bond["trials_passed_json"]),
                ["Skill", "Courage"],
            )
            await db.close()
        _run(_check())

    def test_record_is_idempotent(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            await db.record_trial_passed(bond_id, "Skill")
            ok = await db.record_trial_passed(bond_id, "Skill")
            self.assertFalse(ok, "duplicate Skill should return False")
            bond = await db.get_bond(bond_id)
            self.assertEqual(
                json.loads(bond["trials_passed_json"]),
                ["Skill"],
            )
            await db.close()
        _run(_check())

    def test_record_on_nonexistent_returns_false(self):
        async def _check():
            db = await _fresh_db()
            ok = await db.record_trial_passed(99999, "Skill")
            self.assertFalse(ok)
            await db.close()
        _run(_check())

    def test_record_with_malformed_existing_json(self):
        """If trials_passed_json is somehow malformed at the row
        level (corruption, manual SQL fix), the method recovers
        by treating it as an empty list."""
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            # Corrupt the JSON directly.
            await db._db.execute(
                """UPDATE master_padawan_bond
                   SET trials_passed_json = ?
                   WHERE id = ?""",
                ("{not valid", bond_id),
            )
            await db._db.commit()
            ok = await db.record_trial_passed(bond_id, "Skill")
            self.assertTrue(ok)
            bond = await db.get_bond(bond_id)
            self.assertEqual(
                json.loads(bond["trials_passed_json"]),
                ["Skill"],
            )
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 12. FK cascade (character delete → bond delete)
# ═════════════════════════════════════════════════════════════════════


class TestForeignKeyCascade(unittest.TestCase):

    def test_deleting_master_cascades_to_bond(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            await db._db.execute(
                "DELETE FROM characters WHERE id = ?", (mid,))
            await db._db.commit()
            bond = await db.get_bond(bond_id)
            self.assertIsNone(bond,
                "Bond should be cascade-deleted when master is deleted")
            await db.close()
        _run(_check())

    def test_deleting_padawan_cascades_to_bond(self):
        async def _check():
            db = await _fresh_db()
            mid, pid = await _make_two_chars(db)
            bond_id = await db.create_bond(mid, pid)
            await db._db.execute(
                "DELETE FROM characters WHERE id = ?", (pid,))
            await db._db.commit()
            bond = await db.get_bond(bond_id)
            self.assertIsNone(bond,
                "Bond should be cascade-deleted when padawan is deleted")
            await db.close()
        _run(_check())


if __name__ == "__main__":
    unittest.main()
