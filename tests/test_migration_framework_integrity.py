# -*- coding: utf-8 -*-
"""tests/test_migration_framework_integrity.py — T3.20 state-preservation.

Migration-framework safety guards (launch_criteria: 'ANY post-launch schema
change has a CLEAR, TESTED path that PRESERVES all players' live game state').
Two layers:

  (1) STATIC framework integrity (pure) — catches the classic silent bug where
      a migration is added but SCHEMA_VERSION isn't bumped, so the migration
      never runs on an existing DB (current_version is already >= it).
  (2) BOOT re-entrancy (real temp-file Database) — the production reboot path
      (initialize() re-run on an already-current, POPULATED DB) is a no-op that
      preserves all seeded state; a fresh DB reaches the current schema version.

NOT asserted (deliberately): re-running EVERY migration on a populated DB. The
data-backfill statements in MIGRATIONS (e.g. the mail_v33 INSERT) are
intentionally once-only — production runs each migration exactly once behind the
schema_version gate, so re-applying them is a non-scenario that would falsely
flag idempotency. The realistic safety property is the reboot no-op, tested below.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestMigrationFrameworkIntegrity(unittest.TestCase):
    """Pure checks over MIGRATIONS + SCHEMA_VERSION — no DB needed."""

    def test_schema_version_matches_max_migration(self):
        # THE drift guard: a migration added without bumping SCHEMA_VERSION
        # never runs on a live DB (its current_version already exceeds it).
        from db.database import SCHEMA_VERSION, MIGRATIONS
        self.assertEqual(
            SCHEMA_VERSION, max(MIGRATIONS),
            "SCHEMA_VERSION must equal the highest migration key, or the newest "
            "migration never runs on existing databases.",
        )

    def test_no_migration_above_schema_version(self):
        from db.database import SCHEMA_VERSION, MIGRATIONS
        orphaned = sorted(k for k in MIGRATIONS if k > SCHEMA_VERSION)
        self.assertEqual(
            orphaned, [],
            f"Migrations {orphaned} sit above SCHEMA_VERSION and would never run.",
        )

    def test_every_migration_is_a_list_of_sql_statements(self):
        # An EMPTY list is valid — a deliberately reserved/skipped version
        # (`_run_migrations` does `if not stmts: continue`). What must hold is
        # that every value is a list and every statement in it is real SQL.
        from db.database import MIGRATIONS
        for ver, stmts in MIGRATIONS.items():
            self.assertIsInstance(stmts, list, f"MIGRATIONS[{ver}] must be a list")
            for s in stmts:
                self.assertIsInstance(s, str, f"MIGRATIONS[{ver}] has a non-str stmt")
                self.assertTrue(s.strip(), f"MIGRATIONS[{ver}] has a blank stmt")

    def test_migration_keys_are_ints_in_range(self):
        from db.database import SCHEMA_VERSION, MIGRATIONS
        for k in MIGRATIONS:
            self.assertIsInstance(k, int, f"migration key {k!r} is not an int")
            self.assertGreaterEqual(k, 1)
            self.assertLessEqual(k, SCHEMA_VERSION)


class TestBootReentrancy(unittest.TestCase):
    """The production reboot path must preserve all live state."""

    def _fresh_db_path(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(path)  # let initialize() create it fresh
        return path

    def _cleanup(self, path):
        for p in (path, path + "-wal", path + "-shm"):
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except OSError:
                pass

    def test_fresh_init_reaches_current_schema_version(self):
        from db.database import Database, SCHEMA_VERSION
        path = self._fresh_db_path()

        async def _go():
            db = Database(path)
            await db.connect()
            try:
                await db.initialize()
                rows = await db.fetchall(
                    "SELECT MAX(version) AS v FROM schema_version")
                return rows[0]["v"]
            finally:
                await db.close()

        try:
            self.assertEqual(_run(_go()), SCHEMA_VERSION)
        finally:
            self._cleanup(path)

    def test_double_init_is_noop_and_preserves_data(self):
        # Seed a populated DB at the current version, then RE-BOOT (the real
        # production path: initialize() runs every startup). The re-boot must
        # not lose data, duplicate the schema_version row, or change the version.
        from db.database import Database, SCHEMA_VERSION
        path = self._fresh_db_path()

        async def _go():
            db = Database(path)
            await db.connect()
            try:
                await db.initialize()
                acct = await db.create_account("migtest_user", "pw")
                cid = await db.create_character(
                    acct, {"name": "MigTestChar", "species": "Twi'lek"})
                await db.initialize()  # second boot on the now-populated DB
                ver = (await db.fetchall(
                    "SELECT MAX(version) AS v FROM schema_version"))[0]["v"]
                char = await db.fetchall(
                    "SELECT name, species FROM characters WHERE id=?", (cid,))
                nrows = (await db.fetchall(
                    "SELECT COUNT(*) AS n FROM schema_version"))[0]["n"]
                return ver, char, nrows
            finally:
                await db.close()

        try:
            ver, char, nrows = _run(_go())
            self.assertEqual(ver, SCHEMA_VERSION)            # still current
            self.assertEqual(len(char), 1)                    # character survived
            self.assertEqual(char[0]["name"], "MigTestChar")  # data intact
            self.assertEqual(char[0]["species"], "Twi'lek")
            self.assertEqual(nrows, 1)                        # no duplicate version row
        finally:
            self._cleanup(path)


if __name__ == "__main__":
    unittest.main()
