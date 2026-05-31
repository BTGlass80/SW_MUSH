# -*- coding: utf-8 -*-
"""
tests/test_syn1a_region_ownership.py — SYN.1.a (May 24 2026).

Pins the new region-ownership surfaces in engine/territory.py shipped
by the SYN.1.a "data-only first half" drop of the Contestable
Wilderness pivot. Per ``contestable_wilderness_design_v2.md`` §3.1.

This drop adds new surfaces *additively* alongside the legacy
``claim_room`` / ``unclaim_room`` / ``is_room_claimed_by`` block. The
old surfaces continue working — SYN.1.b retargets the six known
consumers (per SYN.0 Finding 2) and deletes the legacy block.

Test sections
─────────────
  1. TestSchema                    — ensure_region_ownership_schema
  2. TestRegionIntrospection       — landmark + zone helpers
  3. TestOwnershipQueries          — get/list/is_region_owned_by
  4. TestClaimRegion               — validation chain + happy path
  5. TestUnclaimRegion             — release flow
  6. TestGarrisonSpawn             — NPC spawning at landmarks
  7. TestGarrisonDismiss           — full removal
  8. TestTickRegionMaintenance     — weekly upkeep + lapse paths
  9. TestTickRegionPassiveYield    — daily yield to owners
 10. TestEnsureSchemaIntegration   — wired into ensure_territory_schema
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    """Run a coroutine to completion in a fresh event loop.

    Uses ``asyncio.new_event_loop().run_until_complete`` — the
    ``asyncio.get_event_loop()`` pattern broke in Python 3.14 (see
    BugFix5 / 2026-05-24).
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────
# In-memory DB stand-in
# ──────────────────────────────────────────────────────────────────────
#
# Borrows the _MiniDB / _SyncAsyncSqlite pattern from
# tests/test_pg1_death_a_engine_consumers.py. We delegate to a real
# in-memory sqlite3 to exercise the actual SQL paths in
# engine/territory.py without standing up a full Database.

class _SyncAsyncSqlite:
    """aiosqlite-compatible adapter over stdlib sqlite3."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        self._conn.execute(sql, params)
        return None

    async def execute_fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    async def commit(self):
        self._conn.commit()


class _MiniDB:
    """Minimal Database-API surface for SYN.1.a tests.

    Implements the small subset of the ``db.database.Database`` API
    consumed by the new region-ownership functions in
    ``engine/territory.py``:

      * ``fetchall`` / ``execute`` / ``commit``  (raw SQL pass-through)
      * ``get_organization`` / ``get_membership`` / ``adjust_org_treasury``
      * ``create_npc`` / ``get_room``

    The methods are intentionally thin — just enough surface to drive
    the production code through its full validation chain.
    """

    def __init__(self):
        self._db = _SyncAsyncSqlite()
        cur = self._db._conn
        cur.executescript("""
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY,
                name TEXT,
                zone_id INTEGER,
                wilderness_region_id TEXT
            );
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT,
                treasury INTEGER DEFAULT 0
            );
            CREATE TABLE memberships (
                char_id INTEGER NOT NULL,
                org_id INTEGER NOT NULL,
                rank_level INTEGER DEFAULT 1,
                PRIMARY KEY (char_id, org_id)
            );
            CREATE TABLE npcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                room_id INTEGER,
                species TEXT,
                description TEXT,
                char_sheet_json TEXT DEFAULT '{}',
                ai_config_json TEXT DEFAULT '{}'
            );
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name TEXT,
                properties TEXT DEFAULT '{"security":"lawless"}'
            );
            CREATE TABLE territory_influence (
                zone_id INTEGER NOT NULL,
                org_code TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                last_activity REAL NOT NULL DEFAULT 0,
                last_presence REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (zone_id, org_code)
            );
        """)
        self._db._conn.commit()

    # ── raw SQL pass-through ───────────────────────────────────────
    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

    # ── ORM-style helpers ──────────────────────────────────────────
    async def get_organization(self, org_code):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM organizations WHERE code = ?", (org_code,)
        )
        return dict(rows[0]) if rows else None

    async def get_membership(self, char_id, org_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM memberships WHERE char_id = ? AND org_id = ?",
            (char_id, org_id),
        )
        return dict(rows[0]) if rows else None

    async def adjust_org_treasury(self, org_id, delta):
        rows = await self._db.execute_fetchall(
            "SELECT treasury FROM organizations WHERE id = ?", (org_id,)
        )
        current = int(rows[0]["treasury"]) if rows else 0
        new_balance = current + int(delta)
        await self._db.execute(
            "UPDATE organizations SET treasury = ? WHERE id = ?",
            (new_balance, org_id),
        )
        await self._db.commit()
        return new_balance

    async def get_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (room_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_zone(self, zone_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,)
        )
        return dict(rows[0]) if rows else None

    async def create_npc(self, name, room_id, species="Human",
                          description="", char_sheet_json="{}",
                          ai_config_json="{}"):
        cur = self._db._conn.execute(
            """INSERT INTO npcs (name, room_id, species, description,
                                 char_sheet_json, ai_config_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, room_id, species, description, char_sheet_json, ai_config_json),
        )
        self._db._conn.commit()
        return cur.lastrowid

    # ── Seed helpers (test-only) ──────────────────────────────────
    def seed_org(self, *, org_id, code, treasury=100_000, name=None):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name, treasury) "
            "VALUES (?, ?, ?, ?)",
            (org_id, code, name or code.title(), treasury),
        )
        self._db._conn.commit()

    def seed_membership(self, *, char_id, org_id, rank_level=3):
        self._db._conn.execute(
            "INSERT INTO memberships (char_id, org_id, rank_level) "
            "VALUES (?, ?, ?)",
            (char_id, org_id, rank_level),
        )
        self._db._conn.commit()

    def seed_zone(self, *, zone_id, name, declared_security="lawless"):
        # Production zones store security in a JSON `properties` column,
        # not a top-level column (see engine/territory.py::get_zone_security
        # which reads props["security"]).
        props_json = json.dumps({"security": declared_security})
        self._db._conn.execute(
            "INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
            (zone_id, name, props_json),
        )
        self._db._conn.commit()

    def seed_room(self, *, room_id, name, zone_id=None,
                  wilderness_region_id=None):
        self._db._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) "
            "VALUES (?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id),
        )
        self._db._conn.commit()

    def seed_region_landmarks(self, *, slug, zone_id, count, start_room_id=100):
        """Create ``count`` landmark rooms tagged with the region slug."""
        for i in range(count):
            self.seed_room(
                room_id=start_room_id + i,
                name=f"{slug} landmark #{i + 1}",
                zone_id=zone_id,
                wilderness_region_id=slug,
            )

    def seed_influence(self, *, zone_id, org_code, score):
        self._db._conn.execute(
            "INSERT INTO territory_influence "
            "(zone_id, org_code, score, last_activity, last_presence) "
            "VALUES (?, ?, ?, ?, ?)",
            (zone_id, org_code, score, time.time(), time.time()),
        )
        self._db._conn.commit()

    def org_treasury(self, org_id):
        rows = self._db._conn.execute(
            "SELECT treasury FROM organizations WHERE id = ?", (org_id,)
        ).fetchall()
        return int(rows[0][0]) if rows else 0

    def count(self, table):
        rows = self._db._conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchall()
        return int(rows[0][0])


def _make_db():
    """Build a stocked _MiniDB with the standard test fixture:

      * Org #10 'hutt_cartel' with 100_000 cr treasury
      * Char 1 is rank-5 member of hutt_cartel
      * Char 2 is rank-1 member (insufficient rank for claim)
      * Zone 50 'jundland_wastes' lawless
      * 8 landmark rooms tagged with wilderness_region_id =
        'tatooine_dune_sea', all in zone 50
      * Hutt influence in zone 50: 60 (above Foothold threshold of 50)
    """
    db = _MiniDB()
    db.seed_org(org_id=10, code="hutt_cartel", treasury=100_000)
    db.seed_membership(char_id=1, org_id=10, rank_level=5)
    db.seed_membership(char_id=2, org_id=10, rank_level=1)
    db.seed_zone(zone_id=50, name="Jundland Wastes",
                 declared_security="lawless")
    db.seed_region_landmarks(
        slug="tatooine_dune_sea", zone_id=50, count=8, start_room_id=100,
    )
    db.seed_influence(zone_id=50, org_code="hutt_cartel", score=60)
    # Ensure region tables exist for tests that don't call schema setup
    from engine.territory import ensure_region_ownership_schema
    _run(ensure_region_ownership_schema(db))
    return db


def _char(*, char_id=1, name="Vask"):
    return {"id": char_id, "name": name}


# ──────────────────────────────────────────────────────────────────────
# 1. Schema
# ──────────────────────────────────────────────────────────────────────

class TestSchema(unittest.TestCase):

    def test_schema_creates_region_ownership_table(self):
        from engine.territory import ensure_region_ownership_schema
        db = _MiniDB()
        _run(ensure_region_ownership_schema(db))
        rows = _run(db.fetchall(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='region_ownership'"
        ))
        self.assertEqual(len(rows), 1)

    def test_schema_creates_region_garrison_table(self):
        from engine.territory import ensure_region_ownership_schema
        db = _MiniDB()
        _run(ensure_region_ownership_schema(db))
        rows = _run(db.fetchall(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='region_garrison'"
        ))
        self.assertEqual(len(rows), 1)

    def test_schema_is_idempotent(self):
        """Re-running schema setup doesn't raise or duplicate."""
        from engine.territory import ensure_region_ownership_schema
        db = _MiniDB()
        _run(ensure_region_ownership_schema(db))
        _run(ensure_region_ownership_schema(db))
        _run(ensure_region_ownership_schema(db))
        # Still just the one table of each
        rows = _run(db.fetchall(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name IN "
            "('region_ownership', 'region_garrison')"
        ))
        self.assertEqual(len(rows), 2)


# ──────────────────────────────────────────────────────────────────────
# 2. Region introspection helpers
# ──────────────────────────────────────────────────────────────────────

class TestRegionIntrospection(unittest.TestCase):

    def test_get_region_landmarks_returns_room_ids(self):
        from engine.territory import _get_region_landmarks
        db = _make_db()
        landmarks = _run(_get_region_landmarks(db, "tatooine_dune_sea"))
        self.assertEqual(len(landmarks), 8)
        # All ids in our seed range
        self.assertTrue(all(100 <= rid < 108 for rid in landmarks))

    def test_get_region_landmarks_unknown_region_returns_empty(self):
        from engine.territory import _get_region_landmarks
        db = _make_db()
        landmarks = _run(_get_region_landmarks(db, "no_such_region"))
        self.assertEqual(landmarks, [])

    def test_get_region_zone_derives_from_landmark(self):
        from engine.territory import _get_region_zone
        db = _make_db()
        zone = _run(_get_region_zone(db, "tatooine_dune_sea"))
        self.assertEqual(zone, 50)

    def test_get_region_zone_unknown_region_returns_none(self):
        from engine.territory import _get_region_zone
        db = _make_db()
        zone = _run(_get_region_zone(db, "no_such_region"))
        self.assertIsNone(zone)


# ──────────────────────────────────────────────────────────────────────
# 3. Ownership queries
# ──────────────────────────────────────────────────────────────────────

class TestOwnershipQueries(unittest.TestCase):

    def test_get_region_owner_unowned_returns_none(self):
        from engine.territory import get_region_owner
        db = _make_db()
        owner = _run(get_region_owner(db, "tatooine_dune_sea"))
        self.assertIsNone(owner)

    def test_get_org_regions_empty_initially(self):
        from engine.territory import get_org_regions
        db = _make_db()
        regions = _run(get_org_regions(db, "hutt_cartel"))
        self.assertEqual(regions, [])

    def test_is_region_owned_by_negative_when_unowned(self):
        from engine.territory import is_region_owned_by
        db = _make_db()
        self.assertFalse(
            _run(is_region_owned_by(db, "tatooine_dune_sea", "hutt_cartel"))
        )

    def test_is_region_owned_by_positive_after_claim(self):
        from engine.territory import claim_region, is_region_owned_by
        db = _make_db()
        result = _run(claim_region(db, _char(), "hutt_cartel",
                                    "tatooine_dune_sea"))
        self.assertTrue(result["ok"], result["msg"])
        self.assertTrue(
            _run(is_region_owned_by(db, "tatooine_dune_sea", "hutt_cartel"))
        )

    def test_is_region_owned_by_negative_for_different_org(self):
        from engine.territory import claim_region, is_region_owned_by
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        # Pretend "rebel" also exists for the negative check
        self.assertFalse(
            _run(is_region_owned_by(db, "tatooine_dune_sea", "rebel"))
        )


# ──────────────────────────────────────────────────────────────────────
# 4. claim_region — validation chain + happy path
# ──────────────────────────────────────────────────────────────────────

class TestClaimRegion(unittest.TestCase):

    def test_claim_rejects_unknown_org(self):
        from engine.territory import claim_region
        db = _make_db()
        result = _run(claim_region(db, _char(), "no_such_org",
                                    "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("Unknown organization", result["msg"])

    def test_claim_rejects_insufficient_rank(self):
        from engine.territory import claim_region
        db = _make_db()
        # Char 2 is rank 1, below REGION_CLAIM_MIN_RANK
        result = _run(claim_region(db, _char(char_id=2), "hutt_cartel",
                                    "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("rank", result["msg"].lower())

    def test_claim_rejects_unknown_region(self):
        from engine.territory import claim_region
        db = _make_db()
        result = _run(claim_region(db, _char(), "hutt_cartel",
                                    "no_such_region"))
        self.assertFalse(result["ok"])
        self.assertIn("not a known wilderness region", result["msg"])

    def test_claim_rejects_already_owned(self):
        from engine.territory import claim_region
        db = _make_db()
        # Add a second org and have it claim first
        db.seed_org(org_id=11, code="republic", treasury=100_000)
        db.seed_membership(char_id=99, org_id=11, rank_level=5)
        db.seed_influence(zone_id=50, org_code="republic", score=60)
        first = _run(claim_region(db, _char(char_id=99), "republic",
                                   "tatooine_dune_sea"))
        self.assertTrue(first["ok"], first["msg"])
        # Now Hutts try
        result = _run(claim_region(db, _char(), "hutt_cartel",
                                    "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("owned by", result["msg"])

    def test_claim_rejects_own_org_double_claim(self):
        from engine.territory import claim_region
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        result = _run(claim_region(db, _char(), "hutt_cartel",
                                    "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("already owns", result["msg"])

    def test_claim_rejects_insufficient_influence(self):
        from engine.territory import claim_region
        db = _make_db()
        # Drop influence below Foothold (50)
        db._db._conn.execute(
            "UPDATE territory_influence SET score = 10 "
            "WHERE zone_id = 50 AND org_code = 'hutt_cartel'"
        )
        db._db._conn.commit()
        result = _run(claim_region(db, _char(), "hutt_cartel",
                                    "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("Insufficient influence", result["msg"])

    def test_claim_rejects_secured_zone(self):
        from engine.territory import claim_region
        db = _make_db()
        db._db._conn.execute(
            "UPDATE zones SET properties = ? WHERE id = 50",
            (json.dumps({"security": "secured"}),),
        )
        db._db._conn.commit()
        result = _run(claim_region(db, _char(), "hutt_cartel",
                                    "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("Imperial", result["msg"])

    def test_claim_rejects_insufficient_treasury(self):
        from engine.territory import claim_region, REGION_CLAIM_COST
        db = _make_db()
        # Drain treasury to below claim cost
        db._db._conn.execute(
            "UPDATE organizations SET treasury = ? WHERE id = 10",
            (REGION_CLAIM_COST - 1,),
        )
        db._db._conn.commit()
        result = _run(claim_region(db, _char(), "hutt_cartel",
                                    "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("Insufficient treasury", result["msg"])

    def test_claim_happy_path_deducts_treasury(self):
        from engine.territory import claim_region, REGION_CLAIM_COST
        db = _make_db()
        before = db.org_treasury(10)
        result = _run(claim_region(db, _char(), "hutt_cartel",
                                    "tatooine_dune_sea"))
        self.assertTrue(result["ok"], result["msg"])
        after = db.org_treasury(10)
        self.assertEqual(before - after, REGION_CLAIM_COST)

    def test_claim_happy_path_inserts_ownership_row(self):
        from engine.territory import claim_region, get_region_owner
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        owner = _run(get_region_owner(db, "tatooine_dune_sea"))
        self.assertIsNotNone(owner)
        self.assertEqual(owner["region_slug"], "tatooine_dune_sea")
        self.assertEqual(owner["org_code"], "hutt_cartel")
        self.assertEqual(owner["zone_id"], 50)
        self.assertEqual(owner["claimed_by"], 1)

    def test_claim_happy_path_spawns_garrison(self):
        from engine.territory import claim_region, REGION_GARRISON_COUNT
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        # REGION_GARRISON_COUNT NPC rows
        npc_count = db.count("npcs")
        self.assertEqual(npc_count, REGION_GARRISON_COUNT)
        garrison_rows = _run(db.fetchall(
            "SELECT * FROM region_garrison WHERE region_slug = ?",
            ("tatooine_dune_sea",),
        ))
        self.assertEqual(len(garrison_rows), REGION_GARRISON_COUNT)

    def test_claim_happy_path_bumps_influence(self):
        """claim bumps influence +20 (parity with legacy claim_room)."""
        from engine.territory import claim_region
        db = _make_db()
        # Starting influence is 60 per fixture
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        rows = _run(db.fetchall(
            "SELECT score FROM territory_influence "
            "WHERE zone_id = 50 AND org_code = 'hutt_cartel'"
        ))
        self.assertEqual(rows[0]["score"], 80)  # 60 + 20


# ──────────────────────────────────────────────────────────────────────
# 5. unclaim_region — release flow
# ──────────────────────────────────────────────────────────────────────

class TestUnclaimRegion(unittest.TestCase):

    def test_unclaim_rejects_unowned_region(self):
        from engine.territory import unclaim_region
        db = _make_db()
        result = _run(unclaim_region(db, _char(), "hutt_cartel",
                                      "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("doesn't own", result["msg"])

    def test_unclaim_rejects_wrong_org(self):
        from engine.territory import claim_region, unclaim_region
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        # Different org tries to unclaim
        db.seed_org(org_id=11, code="republic", treasury=100_000)
        db.seed_membership(char_id=99, org_id=11, rank_level=5)
        result = _run(unclaim_region(db, _char(char_id=99), "republic",
                                      "tatooine_dune_sea"))
        self.assertFalse(result["ok"])

    def test_unclaim_rejects_insufficient_rank(self):
        from engine.territory import claim_region, unclaim_region
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        # Char 2 is rank 1
        result = _run(unclaim_region(db, _char(char_id=2), "hutt_cartel",
                                      "tatooine_dune_sea"))
        self.assertFalse(result["ok"])
        self.assertIn("rank", result["msg"].lower())

    def test_unclaim_happy_path_deletes_row(self):
        from engine.territory import (
            claim_region, unclaim_region, get_region_owner,
        )
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        result = _run(unclaim_region(db, _char(), "hutt_cartel",
                                      "tatooine_dune_sea"))
        self.assertTrue(result["ok"], result["msg"])
        self.assertIsNone(_run(get_region_owner(db, "tatooine_dune_sea")))

    def test_unclaim_dismisses_garrison(self):
        from engine.territory import claim_region, unclaim_region
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        self.assertGreater(db.count("npcs"), 0)
        _run(unclaim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        # Garrison NPCs deleted, mapping rows cleared
        self.assertEqual(db.count("npcs"), 0)
        garrison_rows = _run(db.fetchall(
            "SELECT * FROM region_garrison WHERE region_slug = ?",
            ("tatooine_dune_sea",),
        ))
        self.assertEqual(garrison_rows, [])


# ──────────────────────────────────────────────────────────────────────
# 6. Garrison spawn
# ──────────────────────────────────────────────────────────────────────

class TestGarrisonSpawn(unittest.TestCase):

    def test_spawn_creates_npcs_in_landmark_rooms(self):
        from engine.territory import (
            spawn_region_garrison, REGION_GARRISON_COUNT,
        )
        db = _make_db()
        result = _run(spawn_region_garrison(db, "hutt_cartel",
                                             "tatooine_dune_sea"))
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["npc_ids"]), REGION_GARRISON_COUNT)
        # All garrison NPCs are in this region's landmark rooms
        landmark_ids = set(range(100, 108))
        rows = _run(db.fetchall("SELECT room_id FROM npcs"))
        for r in rows:
            self.assertIn(r["room_id"], landmark_ids)

    def test_spawn_rejects_region_with_no_landmarks(self):
        from engine.territory import spawn_region_garrison
        db = _make_db()
        result = _run(spawn_region_garrison(db, "hutt_cartel",
                                             "phantom_region"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["npc_ids"], [])

    def test_spawn_is_idempotent(self):
        from engine.territory import (
            spawn_region_garrison, REGION_GARRISON_COUNT,
        )
        db = _make_db()
        first = _run(spawn_region_garrison(db, "hutt_cartel",
                                            "tatooine_dune_sea"))
        second = _run(spawn_region_garrison(db, "hutt_cartel",
                                             "tatooine_dune_sea"))
        # No new NPCs spawned on second call
        self.assertEqual(db.count("npcs"), REGION_GARRISON_COUNT)
        self.assertEqual(sorted(first["npc_ids"]),
                         sorted(second["npc_ids"]))

    def test_spawn_uses_org_template(self):
        """Hutt garrison uses Hutt template (name prefix matches)."""
        from engine.territory import (
            spawn_region_garrison, _GUARD_TEMPLATES,
        )
        db = _make_db()
        _run(spawn_region_garrison(db, "hutt_cartel", "tatooine_dune_sea"))
        expected_prefix = _GUARD_TEMPLATES["hutt_cartel"]["name_prefix"]
        rows = _run(db.fetchall("SELECT name FROM npcs"))
        for r in rows:
            self.assertTrue(
                r["name"].startswith(expected_prefix),
                f"name {r['name']!r} doesn't start with {expected_prefix!r}",
            )


# ──────────────────────────────────────────────────────────────────────
# 7. Garrison dismiss
# ──────────────────────────────────────────────────────────────────────

class TestGarrisonDismiss(unittest.TestCase):

    def test_dismiss_with_no_garrison_is_noop(self):
        from engine.territory import dismiss_region_garrison
        db = _make_db()
        result = _run(dismiss_region_garrison(db, "tatooine_dune_sea"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["removed"], 0)

    def test_dismiss_removes_all_garrison_npcs(self):
        from engine.territory import (
            spawn_region_garrison, dismiss_region_garrison,
            REGION_GARRISON_COUNT,
        )
        db = _make_db()
        _run(spawn_region_garrison(db, "hutt_cartel", "tatooine_dune_sea"))
        result = _run(dismiss_region_garrison(db, "tatooine_dune_sea"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["removed"], REGION_GARRISON_COUNT)
        self.assertEqual(db.count("npcs"), 0)


# ──────────────────────────────────────────────────────────────────────
# 8. tick_region_maintenance
# ──────────────────────────────────────────────────────────────────────

class TestTickRegionMaintenance(unittest.TestCase):

    def _session_mgr(self):
        mgr = MagicMock()
        mgr.all = []
        return mgr

    def test_tick_deducts_full_upkeep_when_solvent(self):
        from engine.territory import (
            claim_region, tick_region_maintenance,
            REGION_WEEKLY_MAINT, REGION_GARRISON_WEEKLY, REGION_CLAIM_COST,
        )
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        before = db.org_treasury(10)
        _run(tick_region_maintenance(db, self._session_mgr()))
        after = db.org_treasury(10)
        self.assertEqual(
            before - after,
            REGION_WEEKLY_MAINT + REGION_GARRISON_WEEKLY,
        )

    def test_tick_dismisses_garrison_when_treasury_below_full(self):
        from engine.territory import (
            claim_region, tick_region_maintenance,
            REGION_WEEKLY_MAINT, REGION_GARRISON_WEEKLY,
        )
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        # Drop treasury to just below full upkeep but above base only
        target = REGION_WEEKLY_MAINT + REGION_GARRISON_WEEKLY - 100
        db._db._conn.execute(
            "UPDATE organizations SET treasury = ? WHERE id = 10",
            (target,),
        )
        db._db._conn.commit()
        _run(tick_region_maintenance(db, self._session_mgr()))
        # Garrison gone
        self.assertEqual(db.count("npcs"), 0)
        # Region still owned (base upkeep paid)
        from engine.territory import get_region_owner
        owner = _run(get_region_owner(db, "tatooine_dune_sea"))
        self.assertIsNotNone(owner)

    def test_tick_lapses_region_when_treasury_empty(self):
        from engine.territory import (
            claim_region, tick_region_maintenance, get_region_owner,
        )
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        # Empty the treasury
        db._db._conn.execute(
            "UPDATE organizations SET treasury = 0 WHERE id = 10"
        )
        db._db._conn.commit()
        _run(tick_region_maintenance(db, self._session_mgr()))
        # Region no longer owned, garrison gone
        self.assertIsNone(_run(get_region_owner(db, "tatooine_dune_sea")))
        self.assertEqual(db.count("npcs"), 0)

    def test_tick_with_no_owned_regions_is_noop(self):
        from engine.territory import tick_region_maintenance
        db = _make_db()
        # No claim — tick should be a quiet no-op
        _run(tick_region_maintenance(db, self._session_mgr()))
        # No exception, no treasury change
        self.assertEqual(db.org_treasury(10), 100_000)


# ──────────────────────────────────────────────────────────────────────
# 9. tick_region_passive_yield
# ──────────────────────────────────────────────────────────────────────

class TestTickRegionPassiveYield(unittest.TestCase):

    def _session_mgr(self):
        mgr = MagicMock()
        mgr.all = []
        return mgr

    def test_passive_yield_pays_owner_in_lawless(self):
        from engine.territory import (
            claim_region, tick_region_passive_yield,
            REGION_PASSIVE_LAWLESS_MIN, REGION_PASSIVE_LAWLESS_MAX,
            REGION_CLAIM_COST,
        )
        db = _make_db()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        treasury_post_claim = db.org_treasury(10)
        _run(tick_region_passive_yield(db, self._session_mgr()))
        delta = db.org_treasury(10) - treasury_post_claim
        self.assertGreaterEqual(delta, REGION_PASSIVE_LAWLESS_MIN)
        self.assertLessEqual(delta, REGION_PASSIVE_LAWLESS_MAX)

    def test_passive_yield_uses_contested_band_for_contested_zone(self):
        from engine.territory import (
            claim_region, tick_region_passive_yield,
            REGION_PASSIVE_CONTESTED_MIN, REGION_PASSIVE_CONTESTED_MAX,
        )
        db = _make_db()
        # Mark zone contested
        db._db._conn.execute(
            "UPDATE zones SET properties = ? WHERE id = 50",
            (json.dumps({"security": "contested"}),),
        )
        db._db._conn.commit()
        _run(claim_region(db, _char(), "hutt_cartel", "tatooine_dune_sea"))
        treasury_post_claim = db.org_treasury(10)
        _run(tick_region_passive_yield(db, self._session_mgr()))
        delta = db.org_treasury(10) - treasury_post_claim
        self.assertGreaterEqual(delta, REGION_PASSIVE_CONTESTED_MIN)
        self.assertLessEqual(delta, REGION_PASSIVE_CONTESTED_MAX)

    def test_passive_yield_skips_unowned_regions(self):
        from engine.territory import tick_region_passive_yield
        db = _make_db()
        before = db.org_treasury(10)
        _run(tick_region_passive_yield(db, self._session_mgr()))
        after = db.org_treasury(10)
        self.assertEqual(before, after)


# ──────────────────────────────────────────────────────────────────────
# 10. ensure_territory_schema integration
# ──────────────────────────────────────────────────────────────────────

class TestEnsureSchemaIntegration(unittest.TestCase):
    """The top-level ensure_territory_schema (called from
    server/game_server.py boot) must transitively call the new
    ensure_region_ownership_schema so SYN.1.a tables land on startup
    without a separate boot wiring change."""

    def test_ensure_territory_schema_creates_region_tables(self):
        from engine.territory import ensure_territory_schema
        db = _MiniDB()
        _run(ensure_territory_schema(db))
        rows = _run(db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('region_ownership', 'region_garrison')"
        ))
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
