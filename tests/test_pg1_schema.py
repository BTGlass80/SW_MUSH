# -*- coding: utf-8 -*-
"""
tests/test_pg1_schema.py — Progression Gates Phase 1 schema verification.

PG.1.schema (May 2026) is the first sub-drop of CW.GATES per
architecture v39 §3.3. It bumps SCHEMA_VERSION from 17 to 18 and
introduces the persistent state for three coupled systems from
``progression_gates_and_consequences_design_v1.md``:

  - Jedi gating (50-hour playtime gate + Village trial state machine):
    9 columns added to characters
  - Death penalty (post-respawn Wounded debuff + corpse retrieval):
    2 columns added to characters; new corpses table
  - PC bounty system (PC-posted bounties + BH insurance debt):
    3 new tables (pc_bounties, bounty_cooldowns, bh_insurance_debt)

This drop is schema-only: no engine code consumes the new columns
yet. PG.1.death will wire the wound_state / corpse columns; PG.2.bounty
will wire the bounty tables; PG.3.gates will wire the Jedi gating
columns. PG.1.schema is shippable on its own because (a) it's
strictly additive, (b) all defaults are pre-feature-safe, and
(c) no players exist yet so no data backfill is needed.

Test sections:
  1. TestSchemaVersionBump        — version is 18, migration registered
  2. TestCharacterColumnsAdded    — 11 new columns present with right defaults
  3. TestCorpseTable              — corpses table shape + indexes
  4. TestPCBountyTable            — pc_bounties shape + indexes + state
                                    enum lifecycle
  5. TestBountyCooldownTable      — composite PK enforced
  6. TestBHInsuranceDebtTable     — char_id PK enforced
  7. TestLegacyColumnsUntouched   — characters.bounty + wound_level
                                    survive the migration unchanged
  8. TestMigrationFromOldDB       — applying migration 18 against a
                                    schema_version 17 DB lands cleanly
  9. TestForeignKeysFire          — FK constraints on the new tables
                                    actually enforce
 10. TestDocstringMarker          — source-level guard
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    """Run an async coroutine in a fresh event loop."""
    return asyncio.run(coro)


async def _fresh_db():
    """Initialize a clean in-memory DB at the latest schema version."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _columns_of(db, table):
    """Return {column_name: column_info_dict} for a table via PRAGMA."""
    rows = await db._db.execute_fetchall(f"PRAGMA table_info({table})")
    return {r["name"]: dict(r) for r in rows}


async def _indexes_of(db, table):
    """Return list of index names on a table."""
    rows = await db._db.execute_fetchall(f"PRAGMA index_list({table})")
    return [r["name"] for r in rows]


async def _fk_list(db, table):
    """Return list of FK info dicts for a table."""
    rows = await db._db.execute_fetchall(f"PRAGMA foreign_key_list({table})")
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# 1. SCHEMA_VERSION bumped to 18, migration registered
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaVersionBump(unittest.TestCase):

    def test_schema_version_is_18(self):
        from db.database import SCHEMA_VERSION
        self.assertEqual(SCHEMA_VERSION, 18,
                         "PG.1.schema bumps SCHEMA_VERSION from 17 to 18")

    def test_migration_18_is_registered(self):
        from db.database import MIGRATIONS
        self.assertIn(18, MIGRATIONS,
                      "MIGRATIONS dict must have an entry for v18")
        self.assertGreater(len(MIGRATIONS[18]), 0,
                           "Migration 18 should not be a placeholder")

    def test_fresh_db_records_v18(self):
        async def _check():
            db = await _fresh_db()
            row = await db._db.execute_fetchall(
                "SELECT MAX(version) AS v FROM schema_version"
            )
            self.assertEqual(row[0]["v"], 18)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 2. New character columns present with the right defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestCharacterColumnsAdded(unittest.TestCase):

    EXPECTED = {
        # Jedi gating (9 columns)
        "play_time_seconds":           ("INTEGER", "0"),
        "force_predisposition":        ("REAL",    "0.0"),
        "force_signs_accumulated":     ("INTEGER", "0"),
        "village_act":                 ("INTEGER", "0"),
        "village_act_unlocked_at":     ("REAL",    "0"),
        "village_trial_courage_done":  ("INTEGER", "0"),
        "village_trial_insight_done":  ("INTEGER", "0"),
        "village_trial_flesh_done":    ("INTEGER", "0"),
        "village_trial_last_attempt":  ("REAL",    "0"),
        # Death penalty respawn-Wounded persistence (2 columns)
        "wound_state":                 ("TEXT",    "'healthy'"),
        "wound_clear_at":              ("REAL",    "0"),
    }

    def test_all_expected_columns_present(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "characters")
            missing = [c for c in self.EXPECTED if c not in cols]
            self.assertEqual(missing, [],
                             f"Missing columns: {missing}")
            await db._db.close()
        _run(_check())

    def test_column_types_match(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "characters")
            mismatches = []
            for cname, (expected_type, _) in self.EXPECTED.items():
                actual = cols[cname]["type"]
                if actual.upper() != expected_type.upper():
                    mismatches.append((cname, actual, expected_type))
            self.assertEqual(mismatches, [],
                             f"Type mismatches: {mismatches}")
            await db._db.close()
        _run(_check())

    def test_default_values_match(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "characters")
            mismatches = []
            for cname, (_, expected_default) in self.EXPECTED.items():
                actual = str(cols[cname]["dflt_value"]).strip()
                # Tolerate sqlite normalizing 0 vs '0' vs 0.0
                if actual.replace("'", "") != expected_default.replace("'", ""):
                    # Number tolerance: '0' == '0.0' for our purposes
                    try:
                        if float(actual) == float(expected_default):
                            continue
                    except (ValueError, TypeError):
                        pass
                    mismatches.append((cname, actual, expected_default))
            self.assertEqual(mismatches, [],
                             f"Default mismatches: {mismatches}")
            await db._db.close()
        _run(_check())

    def test_inserting_minimal_account_then_character_uses_defaults(self):
        """End-to-end: a new character has all PG.1 columns at default."""
        async def _check():
            db = await _fresh_db()
            await db._db.execute(
                "INSERT INTO accounts(username, password_hash) VALUES('t1', 'x')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name) VALUES(1, 'Test1')"
            )
            await db._db.commit()
            row = await db._db.execute_fetchall(
                "SELECT play_time_seconds, force_predisposition, "
                "force_signs_accumulated, village_act, "
                "village_act_unlocked_at, village_trial_courage_done, "
                "village_trial_insight_done, village_trial_flesh_done, "
                "village_trial_last_attempt, wound_state, wound_clear_at "
                "FROM characters WHERE name='Test1'"
            )
            r = row[0]
            self.assertEqual(r["play_time_seconds"], 0)
            self.assertEqual(r["force_predisposition"], 0.0)
            self.assertEqual(r["force_signs_accumulated"], 0)
            self.assertEqual(r["village_act"], 0)
            self.assertEqual(r["village_act_unlocked_at"], 0)
            self.assertEqual(r["village_trial_courage_done"], 0)
            self.assertEqual(r["village_trial_insight_done"], 0)
            self.assertEqual(r["village_trial_flesh_done"], 0)
            self.assertEqual(r["village_trial_last_attempt"], 0)
            self.assertEqual(r["wound_state"], "healthy")
            self.assertEqual(r["wound_clear_at"], 0)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 3. corpses table
# ─────────────────────────────────────────────────────────────────────────────

class TestCorpseTable(unittest.TestCase):

    def test_table_exists(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "corpses")
            self.assertGreater(len(cols), 0, "corpses table missing")
            await db._db.close()
        _run(_check())

    def test_required_columns(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "corpses")
            for cname in (
                "id", "char_id", "room_id", "died_at", "decay_at",
                "inventory", "credits", "killer_id", "killer_is_bh",
                "bounty_resolved",
            ):
                self.assertIn(cname, cols, f"corpses missing {cname!r}")
            await db._db.close()
        _run(_check())

    def test_indexes_present(self):
        async def _check():
            db = await _fresh_db()
            idx = await _indexes_of(db, "corpses")
            self.assertIn("idx_corpses_room", idx)
            self.assertIn("idx_corpses_char", idx)
            await db._db.close()
        _run(_check())

    def test_inventory_defaults_to_empty_json_list(self):
        async def _check():
            db = await _fresh_db()
            await db._db.execute(
                "INSERT INTO accounts(username, password_hash) VALUES('a', 'x')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name) VALUES(1, 'Casualty')"
            )
            # Use existing seeded room 1 (Landing Pad)
            await db._db.execute(
                "INSERT INTO corpses(char_id, room_id, died_at, decay_at) "
                "VALUES(1, 1, 1000.0, 8200.0)"
            )
            await db._db.commit()
            row = await db._db.execute_fetchall("SELECT * FROM corpses")
            self.assertEqual(row[0]["inventory"], "[]")
            self.assertEqual(row[0]["credits"], 0)
            self.assertEqual(row[0]["killer_is_bh"], 0)
            self.assertEqual(row[0]["bounty_resolved"], 0)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 4. pc_bounties table — shape + lifecycle states
# ─────────────────────────────────────────────────────────────────────────────

class TestPCBountyTable(unittest.TestCase):

    def test_table_exists_with_required_columns(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "pc_bounties")
            for cname in (
                "id", "poster_id", "target_id", "amount", "reason",
                "state", "claimed_by", "claimed_at",
                "posted_at", "expires_at", "resolved_at",
            ):
                self.assertIn(cname, cols, f"pc_bounties missing {cname!r}")
            await db._db.close()
        _run(_check())

    def test_state_default_is_active(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "pc_bounties")
            self.assertIn("active", str(cols["state"]["dflt_value"]))
            await db._db.close()
        _run(_check())

    def test_indexes_present(self):
        async def _check():
            db = await _fresh_db()
            idx = await _indexes_of(db, "pc_bounties")
            self.assertIn("idx_bounties_target", idx)
            self.assertIn("idx_bounties_poster", idx)
            self.assertIn("idx_bounties_state_expiry", idx)
            await db._db.close()
        _run(_check())

    def test_lifecycle_states_storable(self):
        """All five lifecycle states (per design §4.3) are storable."""
        async def _check():
            db = await _fresh_db()
            await db._db.execute(
                "INSERT INTO accounts(username, password_hash) VALUES('p', 'x')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name) VALUES(1, 'Poster')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name) VALUES(1, 'Target')"
            )
            for i, state in enumerate(
                ("active", "claimed", "fulfilled", "expired", "canceled")
            ):
                await db._db.execute(
                    "INSERT INTO pc_bounties("
                    "poster_id, target_id, amount, reason, state, "
                    "posted_at, expires_at) "
                    "VALUES(1, 2, 1000, ?, ?, 100.0, 200.0)",
                    (f"reason {i}", state),
                )
            await db._db.commit()
            rows = await db._db.execute_fetchall(
                "SELECT state FROM pc_bounties ORDER BY id"
            )
            states = [r["state"] for r in rows]
            self.assertEqual(
                states,
                ["active", "claimed", "fulfilled", "expired", "canceled"]
            )
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 5. bounty_cooldowns table — composite PK
# ─────────────────────────────────────────────────────────────────────────────

class TestBountyCooldownTable(unittest.TestCase):

    def test_table_exists(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "bounty_cooldowns")
            for cname in ("poster_id", "target_id", "until"):
                self.assertIn(cname, cols)
            await db._db.close()
        _run(_check())

    def test_composite_primary_key(self):
        """Same (poster, target) cannot be inserted twice."""
        async def _check():
            db = await _fresh_db()
            await db._db.execute(
                "INSERT INTO accounts(username, password_hash) VALUES('a', 'x')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name) VALUES(1, 'A')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name) VALUES(1, 'B')"
            )
            await db._db.execute(
                "INSERT INTO bounty_cooldowns(poster_id, target_id, until) "
                "VALUES(1, 2, 1000.0)"
            )
            with self.assertRaises(Exception):
                await db._db.execute(
                    "INSERT INTO bounty_cooldowns(poster_id, target_id, until) "
                    "VALUES(1, 2, 2000.0)"
                )
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 6. bh_insurance_debt table — char_id PK
# ─────────────────────────────────────────────────────────────────────────────

class TestBHInsuranceDebtTable(unittest.TestCase):

    def test_table_exists(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "bh_insurance_debt")
            for cname in ("char_id", "amount", "incurred_at"):
                self.assertIn(cname, cols)
            await db._db.close()
        _run(_check())

    def test_char_id_is_primary_key(self):
        """One debt row per character; second insert for same char_id fails."""
        async def _check():
            db = await _fresh_db()
            await db._db.execute(
                "INSERT INTO accounts(username, password_hash) VALUES('a', 'x')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name) VALUES(1, 'Debtor')"
            )
            await db._db.execute(
                "INSERT INTO bh_insurance_debt(char_id, amount, incurred_at) "
                "VALUES(1, 500, 100.0)"
            )
            with self.assertRaises(Exception):
                await db._db.execute(
                    "INSERT INTO bh_insurance_debt(char_id, amount, incurred_at) "
                    "VALUES(1, 200, 200.0)"
                )
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 7. Legacy columns are preserved (regression guard)
# ─────────────────────────────────────────────────────────────────────────────

class TestLegacyColumnsUntouched(unittest.TestCase):
    """The legacy bounty (migration 3) and wound_level (base SCHEMA) survive."""

    def test_legacy_bounty_column_still_present(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "characters")
            self.assertIn("bounty", cols,
                          "Legacy characters.bounty column was removed by PG.1")
            self.assertEqual(cols["bounty"]["type"].upper(), "INTEGER")
            await db._db.close()
        _run(_check())

    def test_legacy_wound_level_column_still_present(self):
        async def _check():
            db = await _fresh_db()
            cols = await _columns_of(db, "characters")
            self.assertIn("wound_level", cols)
            self.assertEqual(cols["wound_level"]["type"].upper(), "INTEGER")
            await db._db.close()
        _run(_check())

    def test_legacy_and_new_columns_coexist(self):
        """Both legacy and new wound state can be set on the same character."""
        async def _check():
            db = await _fresh_db()
            await db._db.execute(
                "INSERT INTO accounts(username, password_hash) VALUES('a', 'x')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name, wound_level, wound_state) "
                "VALUES(1, 'Hurt', 2, 'wounded')"
            )
            await db._db.commit()
            row = await db._db.execute_fetchall(
                "SELECT wound_level, wound_state FROM characters WHERE name='Hurt'"
            )
            self.assertEqual(row[0]["wound_level"], 2)
            self.assertEqual(row[0]["wound_state"], "wounded")
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 8. Migration from a v17 DB lands cleanly
# ─────────────────────────────────────────────────────────────────────────────

class TestMigrationFromOldDB(unittest.TestCase):
    """Simulate an existing v17 DB and apply migration 18 to it."""

    def test_migration_18_applies_to_v17_db(self):
        async def _check():
            from db.database import Database, MIGRATIONS
            db = Database(":memory:")
            await db.connect()
            # Simulate a v17 DB by manually applying migrations 1..17
            # via the same SCHEMA_SQL + MIGRATIONS path, but stopping
            # before 18. The cleanest way is to monkeypatch
            # SCHEMA_VERSION temporarily, init, then bump and re-init.
            import db.database as ddmod
            original = ddmod.SCHEMA_VERSION
            try:
                ddmod.SCHEMA_VERSION = 17
                await db.initialize()
                # Confirm we're at v17
                row = await db._db.execute_fetchall(
                    "SELECT MAX(version) AS v FROM schema_version"
                )
                self.assertEqual(row[0]["v"], 17)
                # Confirm new columns are NOT present yet
                cols = await _columns_of(db, "characters")
                self.assertNotIn("play_time_seconds", cols)
                self.assertNotIn("wound_state", cols)
            finally:
                ddmod.SCHEMA_VERSION = original

            # Now bump to 18 and re-initialize. Should apply migration 18.
            await db.initialize()
            row = await db._db.execute_fetchall(
                "SELECT MAX(version) AS v FROM schema_version"
            )
            self.assertEqual(row[0]["v"], 18)
            cols = await _columns_of(db, "characters")
            self.assertIn("play_time_seconds", cols)
            self.assertIn("wound_state", cols)
            self.assertIn("village_act", cols)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 9. Foreign keys actually fire
# ─────────────────────────────────────────────────────────────────────────────

class TestForeignKeysFire(unittest.TestCase):
    """PRAGMA foreign_keys=ON is set in connect(); verify FKs reject bad refs."""

    def test_corpse_with_bad_char_id_rejected(self):
        async def _check():
            db = await _fresh_db()
            # Room 1 is seeded by default; use a clearly-bad char_id
            with self.assertRaises(Exception):
                await db._db.execute(
                    "INSERT INTO corpses(char_id, room_id, died_at, decay_at) "
                    "VALUES(99999, 1, 100.0, 200.0)"
                )
                await db._db.commit()
            await db._db.close()
        _run(_check())

    def test_pc_bounty_with_bad_target_rejected(self):
        async def _check():
            db = await _fresh_db()
            await db._db.execute(
                "INSERT INTO accounts(username, password_hash) VALUES('a', 'x')"
            )
            await db._db.execute(
                "INSERT INTO characters(account_id, name) VALUES(1, 'Poster')"
            )
            with self.assertRaises(Exception):
                await db._db.execute(
                    "INSERT INTO pc_bounties("
                    "poster_id, target_id, amount, reason, "
                    "posted_at, expires_at) "
                    "VALUES(1, 99999, 1000, 'bad', 100.0, 200.0)"
                )
                await db._db.commit()
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 10. Source-level marker
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):
    """database.py mentions PG.1.schema in the migration block."""

    def test_database_module_references_pg1(self):
        path = os.path.join(PROJECT_ROOT, "db", "database.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("PG.1", src,
                      "db/database.py migration 18 should reference PG.1.schema")
        self.assertIn("progression_gates_and_consequences_design_v1.md", src,
                      "Migration 18 should cite the design doc")
        # Spot-check the three coupled systems are mentioned
        for marker in ("Jedi gating", "Death penalty", "PC bounty"):
            self.assertIn(marker, src,
                          f"Migration 18 comments should mention {marker!r}")


if __name__ == "__main__":
    unittest.main()
