# -*- coding: utf-8 -*-
"""tests/test_db_integrity.py — T3.20 state-preservation.

Tests for the live-DB integrity / orphan validator (db/integrity.py, scope_notes
e). The scanner wraps SQLite's own ``PRAGMA integrity_check`` (corruption) and
``PRAGMA foreign_key_check`` (rows orphaned by a missing parent across every
declared FK). Two layers:

  (1) Pure report helpers — ok/summary/describe behave (no DB).
  (2) Real temp-file DB — a freshly initialized + seeded DB is referentially
      CLEAN, and an orphan introduced the way a migration/backup/manual edit can
      (parent dropped while foreign_keys enforcement is OFF) is DETECTED. Read-only
      sanity: the scan does not mutate the data.
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


class TestIntegrityReportHelpers(unittest.TestCase):
    """Pure dataclass behaviour — no DB."""

    def test_empty_report_is_ok(self):
        from db.integrity import IntegrityReport
        r = IntegrityReport()
        self.assertTrue(r.ok)
        self.assertIn("OK", r.summary())

    def test_report_with_orphan_is_not_ok(self):
        from db.integrity import IntegrityReport, OrphanFinding
        r = IntegrityReport(orphans=[OrphanFinding("characters", 5, "accounts", 0)])
        self.assertFalse(r.ok)
        s = r.summary()
        self.assertIn("characters", s)
        self.assertIn("accounts", s)

    def test_report_with_corruption_is_not_ok(self):
        from db.integrity import IntegrityReport
        r = IntegrityReport(corruption=["row 3 missing from index ix_foo"])
        self.assertFalse(r.ok)
        self.assertIn("corruption", r.summary())

    def test_orphan_describe_handles_null_rowid(self):
        from db.integrity import OrphanFinding
        self.assertIn("a row", OrphanFinding("t", None, "p", 0).describe())
        self.assertIn("rowid 7", OrphanFinding("t", 7, "p", 0).describe())


class TestDbIntegrityScanner(unittest.TestCase):
    """The scanner against a real temp-file Database."""

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

    def test_clean_seeded_db_then_orphan_detected(self):
        from db.database import Database
        from db.integrity import scan_integrity
        path = self._fresh_db_path()

        async def _go():
            db = Database(path)
            await db.connect()
            try:
                await db.initialize()
                acct = await db.create_account("integ_user", "pw")
                cid = await db.create_character(
                    acct, {"name": "IntegChar", "species": "Twi'lek"})
                await db.commit()

                before = await scan_integrity(db)

                # Simulate the path the validator exists to catch: drop the parent
                # account while FK enforcement is OFF (as a table-rebuild migration
                # or a restored backup can), orphaning the character's account_id.
                await db._db.execute("PRAGMA foreign_keys=OFF")
                await db.execute_commit("DELETE FROM accounts WHERE id=?", (acct,))

                after = await scan_integrity(db)

                # Read-only sanity: the scan + the (account-only) delete left the
                # character row itself in place.
                n = (await db.fetchall(
                    "SELECT COUNT(*) AS n FROM characters WHERE id=?", (cid,)))[0]["n"]
                return before, after, n
            finally:
                await db.close()

        try:
            before, after, char_n = _run(_go())
        finally:
            self._cleanup(path)

        # A freshly initialized + seeded DB is referentially intact.
        self.assertTrue(before.ok,
                        f"fresh seeded DB should be clean, got:\n{before.summary()}")
        self.assertEqual(before.corruption, [])
        self.assertEqual(before.orphans, [])

        # After orphaning, the scan flags the dangling characters->accounts FK.
        self.assertFalse(after.ok)
        self.assertEqual(after.corruption, [], "expected an orphan, not corruption")
        self.assertTrue(
            any(o.table == "characters" and o.parent_table == "accounts"
                for o in after.orphans),
            f"expected a characters->accounts orphan, got:\n{after.summary()}")
        self.assertEqual(char_n, 1, "the orphaned character row should still exist")

    def test_fresh_db_integrity_check_passes(self):
        from db.database import Database
        from db.integrity import scan_integrity
        path = self._fresh_db_path()

        async def _go():
            db = Database(path)
            await db.connect()
            try:
                await db.initialize()
                return await scan_integrity(db)
            finally:
                await db.close()

        try:
            report = _run(_go())
        finally:
            self._cleanup(path)

        # integrity_check (structural corruption) is clean on any fresh DB.
        self.assertEqual(report.corruption, [],
                         f"fresh DB reported corruption:\n{report.summary()}")


if __name__ == "__main__":
    unittest.main()
