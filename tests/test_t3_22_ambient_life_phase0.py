# -*- coding: utf-8 -*-
"""tests/test_t3_22_ambient_life_phase0.py — Ambient NPC life, Phase 0
(PRE-LAUNCH DB scaffolding). T3.22, 2026-06-13.

Phase 0 is the ONLY part of the ambient-life feature that touches the live
DB, and it does so while it's safe (pre-launch): two new, empty tables read
by NOTHING until the post-launch sim ships. Per
docs/design/ambient_npc_life_design_v1.md §6, Phase 0 ships:

  - Schema v44: npc_ambient_state + npc_ambient_relationship (+ one index),
    in BOTH SCHEMA_SQL (fresh installs) and MIGRATIONS[44] (existing DBs).
  - INERT accessor stubs (ambient_state_get/ensure_row/update/in_room) —
    no callers yet; Phase 1+ uses them.

This test asserts the scaffolding exists and is live-safe; it does NOT
assert any behavior (there is none yet — that's the point).

Sections:
  1. TestSchemaVersionBump      — version >= 44, migration 44 registered
  2. TestAmbientTableShapes     — both tables + columns + the JSON extra blank
  3. TestAmbientIndex           — idx_npc_ambient_room exists
  4. TestMigrationFromV43       — an old (v43) DB upgrades and gains the tables
  5. TestAccessorStubs          — ensure/get/update/in_room round-trip
  6. TestInertness             — no production code reads the tables yet
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
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_npc(db, name="Ambient Test NPC") -> int:
    cur = await db._db.execute(
        "INSERT INTO npcs (name) VALUES (?)", (name,))
    await db._db.commit()
    return cur.lastrowid


async def _make_room(db, name="Test Room") -> int:
    cur = await db._db.execute(
        "INSERT INTO rooms (name) VALUES (?)", (name,))
    await db._db.commit()
    return cur.lastrowid


# ═════════════════════════════════════════════════════════════════════
# 1. Schema version
# ═════════════════════════════════════════════════════════════════════

class TestSchemaVersionBump(unittest.TestCase):

    def test_schema_version_at_least_44(self):
        from db.database import SCHEMA_VERSION
        self.assertGreaterEqual(SCHEMA_VERSION, 44)

    def test_migration_44_registered(self):
        from db.database import MIGRATIONS
        self.assertIn(44, MIGRATIONS)
        # 2 CREATE TABLE + 1 index = 3 statements.
        self.assertEqual(len(MIGRATIONS[44]), 3)


# ═════════════════════════════════════════════════════════════════════
# 2. Table shapes (+ the JSON extra future-proof blank)
# ═════════════════════════════════════════════════════════════════════

class TestAmbientTableShapes(unittest.TestCase):

    def test_npc_ambient_state_columns(self):
        async def _check():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "PRAGMA table_info(npc_ambient_state)")
            cols = {r["name"]: dict(r) for r in rows}
            for c in ("npc_id", "current_goal", "current_room_id",
                      "dest_room_id", "move_started_at", "move_duration",
                      "last_tick_at", "activity", "extra"):
                self.assertIn(c, cols, c)
            # npc_id is the primary key.
            self.assertEqual(cols["npc_id"]["pk"], 1)
            # The JSON future-proof blank defaults to '{}'.
            self.assertEqual(cols["extra"]["dflt_value"], "'{}'")
            await db.close()
        _run(_check())

    def test_npc_ambient_relationship_columns(self):
        async def _check():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "PRAGMA table_info(npc_ambient_relationship)")
            cols = {r["name"]: dict(r) for r in rows}
            for c in ("npc_id_a", "npc_id_b", "affinity", "extra"):
                self.assertIn(c, cols, c)
            self.assertEqual(cols["npc_id_a"]["notnull"], 1)
            self.assertEqual(cols["npc_id_b"]["notnull"], 1)
            self.assertEqual(cols["extra"]["dflt_value"], "'{}'")
            await db.close()
        _run(_check())

    def test_extra_column_holds_json(self):
        # The extra blank actually round-trips JSON (the "blank space" works).
        async def _check():
            db = await _fresh_db()
            npc_id = await _make_npc(db)
            await db._db.execute(
                "INSERT INTO npc_ambient_state (npc_id, extra) VALUES (?, ?)",
                (npc_id, json.dumps({"mood": "content", "ticks": 3})),
            )
            await db._db.commit()
            rows = await db._db.execute_fetchall(
                "SELECT extra FROM npc_ambient_state WHERE npc_id = ?",
                (npc_id,))
            self.assertEqual(json.loads(rows[0]["extra"])["mood"], "content")
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 3. Index
# ═════════════════════════════════════════════════════════════════════

class TestAmbientIndex(unittest.TestCase):

    def test_room_index_exists(self):
        async def _check():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name='idx_npc_ambient_room'")
            self.assertEqual(len(rows), 1)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 4. Migration from an old DB (the live-upgrade path)
# ═════════════════════════════════════════════════════════════════════

class TestMigrationFromV43(unittest.TestCase):

    def test_v43_db_upgrades_and_gains_tables(self):
        # Simulate an existing DB stamped at v43 (before this feature):
        # run migrations and confirm the ambient tables appear. This is the
        # exact path a live pre-launch DB takes.
        async def _check():
            from db.database import Database, SCHEMA_VERSION
            db = Database(":memory:")
            await db.connect()
            # Minimal bootstrap: create the schema_version table + the npcs/
            # rooms tables the FKs reference, then stamp v43 and drop the
            # ambient tables to mimic a pre-v44 DB.
            await db.initialize()  # lands current schema (v44)
            await db._db.execute("DROP TABLE IF EXISTS npc_ambient_state")
            await db._db.execute(
                "DROP TABLE IF EXISTS npc_ambient_relationship")
            await db._db.execute("DELETE FROM schema_version")
            await db._db.execute(
                "INSERT INTO schema_version (version) VALUES (43)")
            await db._db.commit()
            # Now re-run migrations from v43 → SCHEMA_VERSION.
            await db._run_migrations(43)
            # The tables are back.
            for t in ("npc_ambient_state", "npc_ambient_relationship"):
                rows = await db._db.execute_fetchall(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name=?", (t,))
                self.assertEqual(len(rows), 1, t)
            await db.close()
        _run(_check())

    def test_migration_44_idempotent(self):
        # Running migration 44 twice must not error (CREATE TABLE IF NOT
        # EXISTS) — re-run safety for a partially-applied upgrade.
        async def _check():
            db = await _fresh_db()
            await db._run_migrations(43)  # tables already exist from init
            await db._run_migrations(43)  # second pass: no-op, no raise
            rows = await db._db.execute_fetchall(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='npc_ambient_state'")
            self.assertEqual(len(rows), 1)
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 5. Accessor stubs round-trip
# ═════════════════════════════════════════════════════════════════════

class TestAccessorStubs(unittest.TestCase):

    def test_ensure_get_update_roundtrip(self):
        async def _check():
            db = await _fresh_db()
            npc_id = await _make_npc(db)
            # get on a missing row → None.
            self.assertIsNone(await db.ambient_state_get(npc_id))
            # ensure creates a default row.
            await db.ambient_state_ensure_row(npc_id)
            row = await db.ambient_state_get(npc_id)
            self.assertIsNotNone(row)
            self.assertEqual(row["current_goal"], "")
            self.assertEqual(row["extra"], "{}")
            # ensure is idempotent.
            await db.ambient_state_ensure_row(npc_id)
            # update writes allowlisted fields.
            await db.ambient_state_update(
                npc_id, current_goal="socialize", activity="haggling")
            row = await db.ambient_state_get(npc_id)
            self.assertEqual(row["current_goal"], "socialize")
            self.assertEqual(row["activity"], "haggling")
            await db.close()
        _run(_check())

    def test_update_rejects_unknown_column(self):
        async def _check():
            db = await _fresh_db()
            npc_id = await _make_npc(db)
            await db.ambient_state_ensure_row(npc_id)
            # An unknown column is rejected by the allowlist. (The PK npc_id
            # can't even be passed as a field — it's the positional arg — so
            # Python itself blocks PK writes before the allowlist.)
            with self.assertRaises(ValueError):
                await db.ambient_state_update(npc_id, bogus="x")
            with self.assertRaises(ValueError):
                await db.ambient_state_update(npc_id, affinity=5)  # wrong table's col
            await db.close()
        _run(_check())

    def test_update_noop_on_empty_fields(self):
        async def _check():
            db = await _fresh_db()
            npc_id = await _make_npc(db)
            await db.ambient_state_ensure_row(npc_id)
            await db.ambient_state_update(npc_id)  # no fields → no-op, no raise
            await db.close()
        _run(_check())

    def test_in_room_query(self):
        async def _check():
            db = await _fresh_db()
            a = await _make_npc(db, "A")
            b = await _make_npc(db, "B")
            c = await _make_npc(db, "C")
            r1 = await _make_room(db, "Room 1")
            r2 = await _make_room(db, "Room 2")
            await db.ambient_state_ensure_row(a)
            await db.ambient_state_ensure_row(b)
            await db.ambient_state_ensure_row(c)
            await db.ambient_state_update(a, current_room_id=r1)
            await db.ambient_state_update(b, current_room_id=r1)
            await db.ambient_state_update(c, current_room_id=r2)
            in_r1 = await db.ambient_state_in_room(r1)
            self.assertEqual({r["npc_id"] for r in in_r1}, {a, b})
            await db.close()
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. Inertness — the feature is scaffolding only
# ═════════════════════════════════════════════════════════════════════

class TestInertness(unittest.TestCase):

    def test_no_production_reader_of_ambient_tables(self):
        # Phase 0 is INERT: nothing in engine/ parser/ server/ reads the
        # ambient tables yet (the sim is post-launch). Only db/database.py
        # (the accessors) and the tick-free scaffolding may mention them.
        # This guards against accidentally wiring a consumer in Phase 0.
        import re
        roots = ("engine", "parser", "server")
        offenders = []
        for root in roots:
            base = os.path.join(PROJECT_ROOT, root)
            for dirpath, _dirs, files in os.walk(base):
                if "__pycache__" in dirpath:
                    continue
                for fn in files:
                    if not fn.endswith(".py"):
                        continue
                    path = os.path.join(dirpath, fn)
                    with open(path, encoding="utf-8") as fh:
                        txt = fh.read()
                    if ("npc_ambient_state" in txt
                            or "npc_ambient_relationship" in txt
                            or "ambient_state_get" in txt
                            or "ambient_state_in_room" in txt):
                        offenders.append(os.path.relpath(path, PROJECT_ROOT))
        self.assertEqual(
            offenders, [],
            f"Phase 0 must stay inert — found ambient-table references in: "
            f"{offenders}. The sim is POST-LAUNCH (Phase 1+).")


if __name__ == "__main__":
    unittest.main()
