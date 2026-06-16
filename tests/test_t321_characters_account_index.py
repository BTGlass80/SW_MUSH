# -*- coding: utf-8 -*-
"""
tests/test_t321_characters_account_index.py -- T3.21 optimization

Adds a composite index ``idx_characters_account`` on
``characters(account_id, is_active)`` (schema v46).

Before this drop, the account -> characters lookup had no supporting index:

  * ``Database.get_characters(account_id)`` -- run on every login and
    character-selection -- did ``SELECT * FROM characters WHERE account_id = ?
    AND is_active = 1``, a full table scan that grows with every character in
    the game.
  * The accounts<->characters JOINs in builder/mux tooling
    (``parser/building_tier2``, ``parser/mux_commands``) join on
    ``c.account_id`` -- also unindexed.

The composite ``(account_id, is_active)`` index fully covers the get_characters
predicate and serves the ``account_id``-prefix JOINs. This is a pure
performance change -- query results are byte-for-byte identical.

These tests exercise the REAL ``Database`` (full schema + migrations) -- no
mocks of the path under test.
"""
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
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fresh_db():
    """A real Database on :memory: with the full current schema applied."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _index_names(db):
    rows = await db.fetchall(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND tbl_name = 'characters'"
    )
    return {r["name"] for r in rows}


class TestCharactersAccountIndex(unittest.TestCase):
    def test_schema_version_at_least_46(self):
        from db import database
        self.assertGreaterEqual(database.SCHEMA_VERSION, 46)

    def test_index_present_on_fresh_db(self):
        async def go():
            db = await _fresh_db()
            try:
                names = await _index_names(db)
                self.assertIn("idx_characters_account", names)
            finally:
                await db.close()
        _run(go())

    def test_migration_46_recreates_index(self):
        """Simulate an existing pre-v46 DB: drop the index, rerun the
        migration step, and confirm v46 brings it back."""
        async def go():
            db = await _fresh_db()
            try:
                await db.execute("DROP INDEX IF EXISTS idx_characters_account")
                await db.commit()
                self.assertNotIn("idx_characters_account", await _index_names(db))
                # Re-apply migrations as if the DB were at v45.
                await db._run_migrations(45)
                self.assertIn("idx_characters_account", await _index_names(db))
            finally:
                await db.close()
        _run(go())

    def test_migration_is_idempotent(self):
        """CREATE INDEX IF NOT EXISTS -- rerunning the migration must not raise
        on an already-indexed DB."""
        async def go():
            db = await _fresh_db()
            try:
                await db._run_migrations(45)  # index already exists
                await db._run_migrations(45)  # second pass: still fine
                self.assertIn("idx_characters_account", await _index_names(db))
            finally:
                await db.close()
        _run(go())

    def test_get_characters_query_plan_uses_index(self):
        async def go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("planner", "pw123456")
                await db.create_character(acct, {"name": "Planner One"})
                rows = await db.fetchall(
                    "EXPLAIN QUERY PLAN SELECT * FROM characters "
                    "WHERE account_id = ? AND is_active = 1",
                    (acct,),
                )
                plan = " ".join(str(r["detail"]) for r in rows)
                self.assertIn("idx_characters_account", plan)
                # Must be an index SEARCH, not a full SCAN.
                self.assertNotIn("SCAN characters", plan)
            finally:
                await db.close()
        _run(go())

    def test_get_characters_results_unchanged(self):
        """Behavior preservation: filtering by account and is_active still
        returns exactly the active characters for that account."""
        async def go():
            db = await _fresh_db()
            try:
                a1 = await db.create_account("owner1", "pw123456")
                a2 = await db.create_account("owner2", "pw123456")
                c1 = await db.create_character(a1, {"name": "Alpha"})
                await db.create_character(a1, {"name": "Bravo"})
                await db.create_character(a2, {"name": "Charlie"})
                # Soft-delete one of owner1's characters.
                await db.execute(
                    "UPDATE characters SET is_active = 0 WHERE id = ?", (c1,)
                )
                await db.commit()

                got = await db.get_characters(a1)
                names = sorted(c["name"] for c in got)
                self.assertEqual(names, ["Bravo"])

                got2 = await db.get_characters(a2)
                self.assertEqual(sorted(c["name"] for c in got2), ["Charlie"])

                # Empty account -> empty list.
                self.assertEqual(await db.get_characters(99999), [])
            finally:
                await db.close()
        _run(go())


if __name__ == "__main__":
    unittest.main()
