# -*- coding: utf-8 -*-
"""tests/test_db_backup.py — T3.20 state-preservation (scope_notes d).

Tests for the consistent online DB backup (db/backup.py::backup_database):

  * a backup PRESERVES all data (the seeded character + schema version survive);
  * it works against a LIVE, still-open DB (the online-backup-API property);
  * it refuses to clobber an existing destination unless overwrite=True;
  * a missing source raises FileNotFoundError;
  * the backup is referentially clean per the integrity scanner (db/integrity.py)
    — backup + verify is the state-preservation loop around a migration.
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


def _fresh_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # let the Database create it fresh
    return path


def _scratch_path():
    fd, path = tempfile.mkstemp(suffix=".bak.db")
    os.close(fd)
    return path  # exists (0 bytes) — used for the overwrite-refusal test


def _cleanup(*paths):
    for base in paths:
        for p in (base, base + "-wal", base + "-shm"):
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except OSError:
                pass


class TestDbBackup(unittest.TestCase):
    def test_backup_preserves_data(self):
        from db.database import Database, SCHEMA_VERSION
        from db.backup import backup_database
        src = _fresh_db_path()
        dst = src + ".backup"

        async def _seed():
            db = Database(src)
            await db.connect()
            try:
                await db.initialize()
                acct = await db.create_account("bak_user", "pw")
                await db.create_character(acct, {"name": "BakChar", "species": "Twi'lek"})
                await db.commit()
            finally:
                await db.close()

        async def _read(path):
            db = Database(path)
            await db.connect()
            try:
                ver = (await db.fetchall(
                    "SELECT MAX(version) AS v FROM schema_version"))[0]["v"]
                names = [r["name"] for r in await db.fetchall(
                    "SELECT name FROM characters")]
                return ver, names
            finally:
                await db.close()

        try:
            _run(_seed())
            size = backup_database(src, dst)        # source CLOSED here
            self.assertGreater(size, 0)
            ver, names = _run(_read(dst))
            self.assertEqual(ver, SCHEMA_VERSION)
            self.assertIn("BakChar", names)
        finally:
            _cleanup(src, dst)

    def test_backup_of_live_open_db_succeeds(self):
        # The online-backup property: snapshot a DB while it is STILL connected.
        from db.database import Database
        from db.backup import backup_database
        src = _fresh_db_path()
        dst = src + ".live.backup"

        async def _go():
            db = Database(src)
            await db.connect()
            try:
                await db.initialize()
                acct = await db.create_account("live_user", "pw")
                await db.create_character(acct, {"name": "LiveChar", "species": "Human"})
                await db.commit()
                # back up while `db` is still open (online):
                size = backup_database(src, dst)
                bdb = Database(dst)
                await bdb.connect()
                try:
                    names = [r["name"] for r in await bdb.fetchall(
                        "SELECT name FROM characters")]
                finally:
                    await bdb.close()
                return size, names
            finally:
                await db.close()

        try:
            size, names = _run(_go())
            self.assertGreater(size, 0)
            self.assertIn("LiveChar", names)
        finally:
            _cleanup(src, dst)

    def test_backup_refuses_existing_dest_without_overwrite(self):
        from db.database import Database
        from db.backup import backup_database
        src = _fresh_db_path()
        dst = _scratch_path()  # already exists

        async def _seed():
            db = Database(src)
            await db.connect()
            try:
                await db.initialize()
            finally:
                await db.close()

        try:
            _run(_seed())
            with self.assertRaises(FileExistsError):
                backup_database(src, dst)             # exists, no overwrite
            size = backup_database(src, dst, overwrite=True)  # now allowed
            self.assertGreater(size, 0)
        finally:
            _cleanup(src, dst)

    def test_backup_missing_source_raises(self):
        from db.backup import backup_database
        with self.assertRaises(FileNotFoundError):
            backup_database("/no/such/source.db", "/tmp/whatever.db")

    def test_backup_passes_integrity_scan(self):
        from db.database import Database
        from db.backup import backup_database
        from db.integrity import scan_integrity
        src = _fresh_db_path()
        dst = src + ".scan.backup"

        async def _seed():
            db = Database(src)
            await db.connect()
            try:
                await db.initialize()
                acct = await db.create_account("scan_user", "pw")
                await db.create_character(acct, {"name": "ScanChar", "species": "Rodian"})
                await db.commit()
            finally:
                await db.close()

        async def _scan(path):
            db = Database(path)
            await db.connect()
            try:
                return await scan_integrity(db)
            finally:
                await db.close()

        try:
            _run(_seed())
            backup_database(src, dst)
            report = _run(_scan(dst))
            self.assertTrue(report.ok, f"backup not clean:\n{report.summary()}")
        finally:
            _cleanup(src, dst)


if __name__ == "__main__":
    unittest.main()
