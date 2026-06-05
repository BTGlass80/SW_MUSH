# -*- coding: utf-8 -*-
"""
tests/test_syn9_player_buildings.py — SYN.9 (2026-05-25).

Pins:
  * engine/buildings.py (new) — schema, 5 categories, construct +
    demolish + evict flow, residence storage, garrison NPC spawn,
    24h tick + 2-day eviction notice tick, 4 effect-lookup helpers,
    rebuild discount.
  * parser/player_building_commands.py (new) — +building dispatch
    with 7 subcommands.
  * server/tick_handlers_economy.py — building_construction_tick
    wrapper.
  * server/game_server.py — ensure_schema call + scheduler
    registration (interval=300s = 5min) + parser command
    registration.

Test sections
─────────────
  1. TestBuildingCategories       — 5 categories, required fields,
                                     cost positive, material lists,
                                     effect summary
  2. TestSchema                   — ensure_schema idempotent,
                                     buildings table + indexes
  3. TestSlotCapacity             — landmark→2, non-landmark→0,
                                     force_resonant→0, explicit override,
                                     0-5 valid range
  4. TestConstructValidation      — unknown category, no slot,
                                     not landmark, no city, low rank,
                                     missing materials, missing credits
  5. TestConstructSuccess         — credits + materials deducted,
                                     building row created with
                                     under_construction status,
                                     completion_ts set, rebuild discount
  6. TestDemolish                 — owner demolishes, 25% refund,
                                     wrong owner rejected, demolish
                                     under_construction (no refund)
  7. TestEvict                    — mayor evicts, 2-day notice set,
                                     non-mayor rejected, double-evict
                                     rejected
  8. TestConstructionTick         — under_construction →
                                     operational at 24h; evict-notice
                                     expiry → evicted; garrison NPCs
                                     spawn at completion; idempotent
                                     when nothing ready
  9. TestEffectLookupHelpers      — crafting_station bonus,
                                     cultural_hall lookup, commerce_stall
                                     lookup, residence-for-owner lookup
 10. TestResidenceStorage         — store + take item, owner-only,
                                     50-item cap, wrong building type
                                     rejected
 11. TestRebuildDiscount          — same-owner same-category same-room
                                     after demolish → 10% discount;
                                     different-owner → no discount
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────
# In-memory DB stand-in. Provides rooms, characters, organizations,
# org_memberships, player_cities, player_city_rooms, npcs tables.
# Buildings ensure_schema() creates the buildings table at setUp.
# ──────────────────────────────────────────────────────────────────────

class _SyncAsyncSqlite:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    async def execute_fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    async def commit(self):
        self._conn.commit()


class _MiniDB:
    def __init__(self):
        self._db = _SyncAsyncSqlite()
        cur = self._db._conn
        cur.executescript("""
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY,
                name TEXT,
                zone_id INTEGER,
                wilderness_region_id TEXT,
                properties TEXT
            );
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                attributes TEXT DEFAULT '{}',
                skills TEXT DEFAULT '{}',
                credits INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '{}',
                faction_id TEXT DEFAULT 'independent',
                room_id INTEGER
            );
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT
            );
            CREATE TABLE org_memberships (
                char_id INTEGER NOT NULL,
                org_id INTEGER NOT NULL,
                rank_level INTEGER NOT NULL DEFAULT 0,
                joined_at REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (char_id, org_id)
            );
            CREATE TABLE player_cities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                org_id INTEGER NOT NULL,
                hq_id INTEGER NOT NULL,
                zone_id INTEGER,
                is_wilderness INTEGER DEFAULT 1,
                wilderness_region_id TEXT,
                founded_at REAL NOT NULL DEFAULT 0,
                founder_id INTEGER NOT NULL DEFAULT 0,
                mayor_id INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'active',
                week_start_ts REAL NOT NULL DEFAULT 0,
                hq_tier TEXT NOT NULL DEFAULT 'outpost'
            );
            CREATE TABLE player_city_rooms (
                city_id INTEGER NOT NULL,
                room_id INTEGER NOT NULL,
                is_center INTEGER NOT NULL DEFAULT 0,
                citizen_only INTEGER NOT NULL DEFAULT 0,
                claimed_at REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (city_id, room_id)
            );
            CREATE TABLE npcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                room_id INTEGER,
                species TEXT DEFAULT 'Human',
                description TEXT DEFAULT '',
                char_sheet_json TEXT DEFAULT '{}',
                ai_config_json TEXT DEFAULT '{}'
            );
        """)
        self._db._conn.commit()

    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

    async def get_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (room_id,))
        return dict(rows[0]) if rows else None

    async def get_character(self, char_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE id = ?", (char_id,))
        return dict(rows[0]) if rows else None

    async def save_character(self, char_id, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        params = list(kwargs.values()) + [char_id]
        await self._db.execute(
            f"UPDATE characters SET {cols} WHERE id = ?", params)
        await self._db.commit()

    async def adjust_credits(self, char_id, delta, source, *, allow_negative=True):
        # Mirrors Database.adjust_credits: char_id==0 is a system faucet/sink
        # (no row), else an atomic credits += delta returning the new balance.
        if char_id == 0:
            return 0
        rows = await self._db.execute_fetchall(
            "SELECT credits FROM characters WHERE id = ?", (char_id,))
        if not rows:
            return None
        cur = int(rows[0]["credits"] or 0)
        if delta < 0 and not allow_negative and cur + delta < 0:
            return None
        await self._db.execute(
            "UPDATE characters SET credits = credits + ? WHERE id = ?",
            (delta, char_id))
        await self._db.commit()
        rows = await self._db.execute_fetchall(
            "SELECT credits FROM characters WHERE id = ?", (char_id,))
        return int(rows[0]["credits"] or 0)

    async def get_membership(self, char_id, org_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM org_memberships "
            "WHERE char_id = ? AND org_id = ?",
            (char_id, org_id),
        )
        return dict(rows[0]) if rows else None

    async def create_npc(self, name, room_id, species="Human",
                         description="", char_sheet_json="{}",
                         ai_config_json="{}"):
        cur = self._db._conn.execute(
            "INSERT INTO npcs (name, room_id, species, description, "
            "char_sheet_json, ai_config_json) VALUES (?, ?, ?, ?, ?, ?)",
            (name, room_id, species, description, char_sheet_json,
             ai_config_json))
        self._db._conn.commit()
        return cur.lastrowid

    async def get_npc(self, npc_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE id = ?", (npc_id,))
        return dict(rows[0]) if rows else None

    async def delete_npc(self, npc_id):
        self._db._conn.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
        self._db._conn.commit()
        return True

    def seed_room(self, *, room_id, zone_id=1,
                  wilderness_region_id="dune_sea",
                  properties=None):
        props_json = json.dumps(properties) if properties else None
        self._db._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id, "
            "properties) VALUES (?, ?, ?, ?, ?)",
            (room_id, f"Room {room_id}", zone_id, wilderness_region_id,
             props_json))
        self._db._conn.commit()

    def seed_character(self, *, char_id=1, name=None,
                       faction_id="republic", room_id=10,
                       credits=20000, inventory=None):
        if inventory is None:
            inventory = {}
        self._db._conn.execute(
            "INSERT INTO characters (id, name, faction_id, room_id, "
            "credits, attributes, skills, inventory) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (char_id, name or f"Char{char_id}", faction_id, room_id,
             credits, "{}", "{}", json.dumps(inventory)))
        self._db._conn.commit()

    def seed_org(self, *, org_id=1, code="republic", name="Republic"):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name) "
            "VALUES (?, ?, ?)", (org_id, code, name))
        self._db._conn.commit()

    def seed_membership(self, *, char_id=1, org_id=1, rank_level=3):
        self._db._conn.execute(
            "INSERT INTO org_memberships "
            "(char_id, org_id, rank_level, joined_at) "
            "VALUES (?, ?, ?, 0)",
            (char_id, org_id, rank_level))
        self._db._conn.commit()

    def seed_city(self, *, city_id=1, org_id=1, hq_id=10,
                  mayor_id=1, founder_id=1, name="Testopolis",
                  room_ids=None):
        self._db._conn.execute(
            "INSERT INTO player_cities "
            "(id, name, org_id, hq_id, mayor_id, founder_id, state, "
            " is_wilderness, wilderness_region_id) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', 1, 'dune_sea')",
            (city_id, name, org_id, hq_id, mayor_id, founder_id))
        if room_ids:
            for r in room_ids:
                self._db._conn.execute(
                    "INSERT INTO player_city_rooms "
                    "(city_id, room_id, is_center, citizen_only, claimed_at) "
                    "VALUES (?, ?, 0, 0, 0)",
                    (city_id, r))
        self._db._conn.commit()


def _make_char(*, char_id=1, room_id=10, credits=20000,
               inventory=None):
    if inventory is None:
        inventory = {
            "resources": [
                {"type": "metal", "quantity": 50, "quality": 60.0},
                {"type": "organic", "quantity": 50, "quality": 60.0},
                {"type": "composite", "quantity": 50, "quality": 60.0},
                {"type": "chemical", "quantity": 50, "quality": 60.0},
            ],
            "items": [],
        }
    return {
        "id": char_id,
        "name": f"Char{char_id}",
        "faction_id": "republic",
        "room_id": room_id,
        "credits": credits,
        "attributes": "{}",
        "skills": "{}",
        "inventory": json.dumps(inventory),
    }


def _setup_full(*, char_id=1, room_id=10, city_id=1, org_id=1,
                rank_level=3, mayor_id=None,
                room_properties=None,
                claim_room=True):
    """Standard scaffold: room + org + city + char + membership."""
    if mayor_id is None:
        mayor_id = char_id
    mdb = _MiniDB()
    if room_properties is None:
        room_properties = {"wilderness_landmark": True}
    mdb.seed_room(room_id=room_id, properties=room_properties)
    mdb.seed_org(org_id=org_id, code="republic", name="Republic")
    mdb.seed_membership(char_id=char_id, org_id=org_id,
                        rank_level=rank_level)
    mdb.seed_character(char_id=char_id, room_id=room_id, credits=20000)
    mdb.seed_city(city_id=city_id, org_id=org_id,
                  mayor_id=mayor_id,
                  room_ids=[room_id] if claim_room else None)
    # Run ensure_schema for the buildings table.
    from engine.buildings import ensure_schema
    _run(ensure_schema(mdb))
    return mdb


class _BuildingTestCase(unittest.TestCase):
    """Base class — keeps a `clean import` discipline."""
    pass


# ══════════════════════════════════════════════════════════════════════
# 1. TestBuildingCategories — category catalog shape
# ══════════════════════════════════════════════════════════════════════

class TestBuildingCategories(_BuildingTestCase):

    EXPECTED_KEYS = {
        "residence", "crafting_station", "commerce_stall",
        "garrison_annex", "cultural_hall",
    }

    def test_five_categories_present(self):
        from engine.buildings import BUILDING_CATEGORIES
        self.assertEqual(set(BUILDING_CATEGORIES.keys()),
                         self.EXPECTED_KEYS)

    def test_every_category_has_required_fields(self):
        from engine.buildings import BUILDING_CATEGORIES
        required = ("display_name", "description", "credit_cost",
                    "material_costs", "effect_summary")
        for key, cat in BUILDING_CATEGORIES.items():
            for f in required:
                self.assertIn(f, cat, f"{key} missing {f}")

    def test_credit_costs_positive(self):
        from engine.buildings import BUILDING_CATEGORIES
        for k, c in BUILDING_CATEGORIES.items():
            self.assertGreater(int(c["credit_cost"]), 0)

    def test_material_costs_non_empty(self):
        from engine.buildings import BUILDING_CATEGORIES
        for k, c in BUILDING_CATEGORIES.items():
            self.assertGreater(len(c["material_costs"]), 0)
            for (rtype, qty) in c["material_costs"]:
                self.assertIsInstance(rtype, str)
                self.assertGreater(int(qty), 0)

    def test_residence_has_storage_cap(self):
        from engine.buildings import BUILDING_CATEGORIES
        self.assertIn("storage_cap",
                      BUILDING_CATEGORIES["residence"])
        self.assertEqual(BUILDING_CATEGORIES["residence"]["storage_cap"],
                         50)

    def test_crafting_station_has_bonus_dice(self):
        from engine.buildings import BUILDING_CATEGORIES
        self.assertEqual(
            BUILDING_CATEGORIES["crafting_station"]["skill_bonus_dice"], 1
        )

    def test_garrison_npc_count(self):
        from engine.buildings import BUILDING_CATEGORIES, GARRISON_NPC_COUNT
        self.assertEqual(
            BUILDING_CATEGORIES["garrison_annex"]["npc_count"],
            GARRISON_NPC_COUNT,
        )
        self.assertEqual(GARRISON_NPC_COUNT, 2)

    def test_design_constants(self):
        """Hard-pin to design §2.9.3."""
        from engine.buildings import (
            CONSTRUCTION_TIME_SECS, DEMOLISH_REFUND_PCT,
            REBUILD_DISCOUNT_PCT, EVICT_NOTICE_SECS,
            MIN_RANK_TO_CONSTRUCT,
        )
        self.assertEqual(CONSTRUCTION_TIME_SECS, 24 * 3600)
        self.assertEqual(DEMOLISH_REFUND_PCT, 25)
        self.assertEqual(REBUILD_DISCOUNT_PCT, 10)
        self.assertEqual(EVICT_NOTICE_SECS, 2 * 24 * 3600)
        self.assertEqual(MIN_RANK_TO_CONSTRUCT, 3)


# ══════════════════════════════════════════════════════════════════════
# 2. TestSchema
# ══════════════════════════════════════════════════════════════════════

class TestSchema(_BuildingTestCase):

    def test_ensure_schema_creates_buildings_table(self):
        mdb = _MiniDB()
        from engine.buildings import ensure_schema
        _run(ensure_schema(mdb))
        rows = _run(mdb.fetchall(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='buildings'"))
        self.assertEqual(len(rows), 1)

    def test_ensure_schema_idempotent(self):
        mdb = _MiniDB()
        from engine.buildings import ensure_schema
        _run(ensure_schema(mdb))
        # second call should not raise.
        _run(ensure_schema(mdb))

    def test_ensure_schema_indexes_present(self):
        mdb = _MiniDB()
        from engine.buildings import ensure_schema
        _run(ensure_schema(mdb))
        rows = _run(mdb.fetchall(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name LIKE 'idx_buildings_%'"))
        names = {r["name"] for r in rows}
        self.assertIn("idx_buildings_room", names)
        self.assertIn("idx_buildings_owner", names)
        self.assertIn("idx_buildings_status", names)


# ══════════════════════════════════════════════════════════════════════
# 3. TestSlotCapacity
# ══════════════════════════════════════════════════════════════════════

class TestSlotCapacity(_BuildingTestCase):

    def test_landmark_default_capacity_2(self):
        from engine.buildings import (
            get_slot_capacity, DEFAULT_LANDMARK_SLOT_CAPACITY,
        )
        mdb = _MiniDB()
        mdb.seed_room(room_id=10,
                      properties={"wilderness_landmark": True})
        self.assertEqual(_run(get_slot_capacity(mdb, 10)),
                         DEFAULT_LANDMARK_SLOT_CAPACITY)

    def test_non_landmark_zero_capacity(self):
        from engine.buildings import get_slot_capacity
        mdb = _MiniDB()
        mdb.seed_room(room_id=10, properties={})
        self.assertEqual(_run(get_slot_capacity(mdb, 10)), 0)

    def test_force_resonant_zero_capacity(self):
        from engine.buildings import get_slot_capacity
        mdb = _MiniDB()
        mdb.seed_room(room_id=10,
                      properties={"wilderness_landmark": True,
                                  "force_resonant": True})
        # Force-resonant overrides landmark.
        self.assertEqual(_run(get_slot_capacity(mdb, 10)), 0)

    def test_explicit_override(self):
        from engine.buildings import get_slot_capacity
        mdb = _MiniDB()
        mdb.seed_room(room_id=10,
                      properties={"wilderness_landmark": True,
                                  "building_slot_capacity": 5})
        self.assertEqual(_run(get_slot_capacity(mdb, 10)), 5)

    def test_zero_override_valid(self):
        from engine.buildings import get_slot_capacity
        mdb = _MiniDB()
        mdb.seed_room(room_id=10,
                      properties={"wilderness_landmark": True,
                                  "building_slot_capacity": 0})
        self.assertEqual(_run(get_slot_capacity(mdb, 10)), 0)

    def test_unknown_room_zero_capacity(self):
        from engine.buildings import get_slot_capacity
        mdb = _MiniDB()
        self.assertEqual(_run(get_slot_capacity(mdb, 999)), 0)


# ══════════════════════════════════════════════════════════════════════
# 4. TestConstructValidation — all gating paths
# ══════════════════════════════════════════════════════════════════════

class TestConstructValidation(_BuildingTestCase):

    def test_unknown_category(self):
        from engine.buildings import construct_building
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        result = _run(construct_building(
            mdb, char, "unknown_thing", 10,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("Unknown", result["msg"])

    def test_not_landmark(self):
        from engine.buildings import construct_building
        mdb = _setup_full(room_properties={})
        char = _make_char(char_id=1, room_id=10)
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("cannot host buildings", result["msg"])

    def test_no_city(self):
        from engine.buildings import construct_building
        mdb = _MiniDB()
        mdb.seed_room(room_id=10,
                      properties={"wilderness_landmark": True})
        mdb.seed_org(org_id=1, code="republic", name="Republic")
        mdb.seed_membership(char_id=1, org_id=1, rank_level=3)
        mdb.seed_character(char_id=1, room_id=10, credits=20000)
        from engine.buildings import ensure_schema
        _run(ensure_schema(mdb))
        char = _make_char(char_id=1, room_id=10)
        # No city seeded — get_city_for_room returns None.
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        self.assertFalse(result["ok"])
        # The error msg from buildings is "not part of any city".
        self.assertIn("not part of any city", result["msg"].lower())

    def test_low_rank(self):
        from engine.buildings import construct_building
        mdb = _setup_full(rank_level=1)   # below MIN_RANK_TO_CONSTRUCT=3
        char = _make_char(char_id=1, room_id=10)
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("rank", result["msg"].lower())

    def test_no_membership(self):
        from engine.buildings import construct_building
        mdb = _MiniDB()
        mdb.seed_room(room_id=10,
                      properties={"wilderness_landmark": True})
        mdb.seed_org(org_id=1, code="republic", name="Republic")
        # No membership for char 1.
        mdb.seed_character(char_id=1, room_id=10, credits=20000)
        mdb.seed_city(city_id=1, org_id=1, mayor_id=1,
                      room_ids=[10])
        from engine.buildings import ensure_schema
        _run(ensure_schema(mdb))
        char = _make_char(char_id=1, room_id=10)
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("rank 0", result["msg"].lower())

    def test_no_materials(self):
        from engine.buildings import construct_building
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10,
                          inventory={"resources": []})
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("lack", result["msg"].lower())

    def test_no_credits(self):
        from engine.buildings import construct_building
        mdb = _setup_full()
        # Char with enough materials but no credits.
        char = _make_char(char_id=1, room_id=10, credits=0)
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("credits", result["msg"].lower())


# ══════════════════════════════════════════════════════════════════════
# 5. TestConstructSuccess
# ══════════════════════════════════════════════════════════════════════

class TestConstructSuccess(_BuildingTestCase):

    def test_construct_residence_success(self):
        from engine.buildings import (
            construct_building, BUILDING_CATEGORIES,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10, credits=20000)
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        self.assertTrue(result["ok"], result.get("msg"))
        self.assertIsNotNone(result["building_id"])

    def test_credits_deducted(self):
        from engine.buildings import (
            construct_building, BUILDING_CATEGORIES,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10, credits=20000)
        cost = BUILDING_CATEGORIES["residence"]["credit_cost"]
        _run(construct_building(mdb, char, "residence", 10))
        # Credits debited.
        c2 = _run(mdb.get_character(1))
        self.assertEqual(c2["credits"], 20000 - cost)

    def test_materials_deducted(self):
        from engine.buildings import (
            construct_building, BUILDING_CATEGORIES,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        _run(construct_building(mdb, char, "residence", 10))
        c2 = _run(mdb.get_character(1))
        inv = json.loads(c2["inventory"])
        # residence costs 5 metal + 5 organic. Initial was 50 each.
        resources = inv.get("resources", [])
        # Aggregate qty by type.
        agg = {}
        for r in resources:
            agg[r["type"]] = agg.get(r["type"], 0) + r["quantity"]
        self.assertEqual(agg.get("metal", 0), 45)
        self.assertEqual(agg.get("organic", 0), 45)

    def test_under_construction_status_set(self):
        from engine.buildings import construct_building, get_building
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        bid = result["building_id"]
        b = _run(get_building(mdb, bid))
        self.assertEqual(b["status"], "under_construction")
        self.assertEqual(b["owner_char_id"], 1)
        self.assertEqual(b["category"], "residence")

    def test_completion_ts_24h_future(self):
        from engine.buildings import (
            construct_building, get_building, CONSTRUCTION_TIME_SECS,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        now = time.time()
        result = _run(construct_building(
            mdb, char, "residence", 10, now=now,
        ))
        bid = result["building_id"]
        b = _run(get_building(mdb, bid))
        self.assertAlmostEqual(
            float(b["completion_ts"]) - now,
            CONSTRUCTION_TIME_SECS,
            delta=2,
        )

    def test_slot_consumed_after_construct(self):
        from engine.buildings import (
            construct_building, count_active_slots_used,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        self.assertEqual(_run(count_active_slots_used(mdb, 10)), 0)
        _run(construct_building(mdb, char, "residence", 10))
        self.assertEqual(_run(count_active_slots_used(mdb, 10)), 1)

    def test_slot_cap_enforced(self):
        from engine.buildings import construct_building
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10, credits=200000,
                          inventory={"resources": [
                              {"type": "metal", "quantity": 200,
                               "quality": 60.0},
                              {"type": "organic", "quantity": 200,
                               "quality": 60.0},
                              {"type": "composite", "quantity": 200,
                               "quality": 60.0},
                          ]})
        # Default landmark capacity = 2.
        r1 = _run(construct_building(mdb, char, "residence", 10))
        self.assertTrue(r1["ok"])
        r2 = _run(construct_building(mdb, char, "residence", 10))
        self.assertTrue(r2["ok"])
        # Third should fail.
        r3 = _run(construct_building(mdb, char, "residence", 10))
        self.assertFalse(r3["ok"])
        self.assertIn("no free building slots", r3["msg"].lower())


# ══════════════════════════════════════════════════════════════════════
# 6. TestDemolish
# ══════════════════════════════════════════════════════════════════════

class TestDemolish(_BuildingTestCase):

    def _construct_and_complete(self, mdb, char):
        """Helper: construct + tick to operational."""
        from engine.buildings import (
            construct_building, tick_building_construction,
        )
        now = time.time()
        result = _run(construct_building(
            mdb, char, "residence", 10, now=now,
        ))
        # Advance 25 hours.
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        return result["building_id"]

    def test_owner_demolish_operational_refunds_25pct(self):
        from engine.buildings import demolish_building
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        bid = self._construct_and_complete(mdb, char)
        # Re-read char to get updated state.
        char = _run(mdb.get_character(1))
        # Owner demolishes.
        result = _run(demolish_building(mdb, char, bid))
        self.assertTrue(result["ok"])
        # 25% of (5 metal + 5 organic) = 1.25 → max(1, ...) = 1 each.
        # The refund is per-cost-line.
        refunded = result["refunded"]
        # Both types refunded with at least 1 each.
        types = {t for (t, q) in refunded}
        self.assertIn("metal", types)
        self.assertIn("organic", types)

    def test_non_owner_cannot_demolish(self):
        from engine.buildings import demolish_building
        mdb = _setup_full()
        # char 1 owns; char 2 tries to demolish.
        char = _make_char(char_id=1, room_id=10)
        bid = self._construct_and_complete(mdb, char)
        mdb.seed_character(char_id=2, room_id=10, credits=0)
        char2 = _make_char(char_id=2, room_id=10, credits=0)
        result = _run(demolish_building(mdb, char2, bid))
        self.assertFalse(result["ok"])
        self.assertIn("don't own", result["msg"])

    def test_demolish_under_construction_no_refund(self):
        from engine.buildings import (
            construct_building, demolish_building,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        result = _run(construct_building(
            mdb, char, "residence", 10,
        ))
        bid = result["building_id"]
        # Re-read char and demolish (still under construction).
        char = _run(mdb.get_character(1))
        result = _run(demolish_building(mdb, char, bid))
        self.assertTrue(result["ok"])
        self.assertEqual(result["refunded"], [])

    def test_demolish_unknown_id(self):
        from engine.buildings import demolish_building
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        result = _run(demolish_building(mdb, char, 9999))
        self.assertFalse(result["ok"])

    def test_demolished_slot_freed(self):
        from engine.buildings import (
            demolish_building, construct_building,
            count_active_slots_used,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10, credits=200000,
                          inventory={"resources": [
                              {"type": "metal", "quantity": 200,
                               "quality": 60.0},
                              {"type": "organic", "quantity": 200,
                               "quality": 60.0},
                              {"type": "composite", "quantity": 200,
                               "quality": 60.0},
                          ]})
        # Fill both slots.
        r1 = _run(construct_building(mdb, char, "residence", 10))
        r2 = _run(construct_building(mdb, char, "residence", 10))
        self.assertEqual(_run(count_active_slots_used(mdb, 10)), 2)
        # Demolish r1.
        char = _run(mdb.get_character(1))
        _run(demolish_building(mdb, char, r1["building_id"]))
        self.assertEqual(_run(count_active_slots_used(mdb, 10)), 1)


# ══════════════════════════════════════════════════════════════════════
# 7. TestEvict
# ══════════════════════════════════════════════════════════════════════

class TestEvict(_BuildingTestCase):

    def _make_op_building(self, mdb, owner_char):
        from engine.buildings import (
            construct_building, tick_building_construction,
        )
        now = time.time()
        result = _run(construct_building(
            mdb, owner_char, "residence", 10, now=now,
        ))
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        return result["building_id"]

    def test_mayor_evicts_sets_notice(self):
        from engine.buildings import (
            evict_building, get_building, EVICT_NOTICE_SECS,
        )
        # Mayor is char_id=2; owner is char_id=1.
        mdb = _setup_full(char_id=1, mayor_id=2, rank_level=3)
        # Seed mayor (char_id=2).
        mdb.seed_character(char_id=2, room_id=10, credits=0)
        mdb.seed_membership(char_id=2, org_id=1, rank_level=5)
        char1 = _make_char(char_id=1, room_id=10)
        bid = self._make_op_building(mdb, char1)
        mayor = _run(mdb.get_character(2))
        now = time.time()
        result = _run(evict_building(mdb, mayor, bid, now=now))
        self.assertTrue(result["ok"])
        b = _run(get_building(mdb, bid))
        self.assertIsNotNone(b["evict_after_ts"])
        self.assertAlmostEqual(
            float(b["evict_after_ts"]) - now,
            EVICT_NOTICE_SECS, delta=2,
        )

    def test_non_mayor_cannot_evict(self):
        from engine.buildings import evict_building
        mdb = _setup_full(char_id=1, mayor_id=2, rank_level=3)
        mdb.seed_character(char_id=2, room_id=10, credits=0)
        mdb.seed_character(char_id=3, room_id=10, credits=0)  # not mayor
        mdb.seed_membership(char_id=2, org_id=1, rank_level=5)
        char1 = _make_char(char_id=1, room_id=10)
        bid = self._make_op_building(mdb, char1)
        non_mayor = _run(mdb.get_character(3))
        result = _run(evict_building(mdb, non_mayor, bid))
        self.assertFalse(result["ok"])
        self.assertIn("mayor", result["msg"].lower())

    def test_double_evict_rejected(self):
        from engine.buildings import evict_building
        mdb = _setup_full(char_id=1, mayor_id=2, rank_level=3)
        mdb.seed_character(char_id=2, room_id=10, credits=0)
        mdb.seed_membership(char_id=2, org_id=1, rank_level=5)
        char1 = _make_char(char_id=1, room_id=10)
        bid = self._make_op_building(mdb, char1)
        mayor = _run(mdb.get_character(2))
        # First evict succeeds.
        r1 = _run(evict_building(mdb, mayor, bid))
        self.assertTrue(r1["ok"])
        # Second fails.
        r2 = _run(evict_building(mdb, mayor, bid))
        self.assertFalse(r2["ok"])
        self.assertIn("already under eviction", r2["msg"].lower())


# ══════════════════════════════════════════════════════════════════════
# 8. TestConstructionTick
# ══════════════════════════════════════════════════════════════════════

class TestConstructionTick(_BuildingTestCase):

    def test_tick_completes_at_24h(self):
        from engine.buildings import (
            construct_building, tick_building_construction,
            get_building, CONSTRUCTION_TIME_SECS,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        now = time.time()
        result = _run(construct_building(
            mdb, char, "residence", 10, now=now,
        ))
        bid = result["building_id"]
        # Before 24h: still under construction.
        stats = _run(tick_building_construction(
            mdb, now=now + 23 * 3600,
        ))
        self.assertEqual(stats["completed"], 0)
        b = _run(get_building(mdb, bid))
        self.assertEqual(b["status"], "under_construction")
        # After 24h: operational.
        stats = _run(tick_building_construction(
            mdb, now=now + CONSTRUCTION_TIME_SECS + 1,
        ))
        self.assertEqual(stats["completed"], 1)
        b = _run(get_building(mdb, bid))
        self.assertEqual(b["status"], "operational")

    def test_garrison_spawns_npcs_at_completion(self):
        from engine.buildings import (
            construct_building, tick_building_construction,
            get_building, GARRISON_NPC_COUNT,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10, credits=200000,
                          inventory={"resources": [
                              {"type": "metal", "quantity": 200,
                               "quality": 60.0},
                              {"type": "composite", "quantity": 200,
                               "quality": 60.0},
                              {"type": "chemical", "quantity": 200,
                               "quality": 60.0},
                          ]})
        now = time.time()
        result = _run(construct_building(
            mdb, char, "garrison_annex", 10, now=now,
        ))
        bid = result["building_id"]
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        b = _run(get_building(mdb, bid))
        self.assertEqual(b["status"], "operational")
        npc_ids = json.loads(b["npc_ids_json"])
        self.assertEqual(len(npc_ids), GARRISON_NPC_COUNT)
        # NPCs exist in room.
        for nid in npc_ids:
            row = _run(mdb.get_npc(nid))
            self.assertIsNotNone(row)
            cfg = json.loads(row["ai_config_json"])
            self.assertTrue(cfg.get("is_garrison_npc"))

    def test_evict_notice_expires_to_evicted(self):
        from engine.buildings import (
            construct_building, evict_building,
            tick_building_construction, get_building,
            EVICT_NOTICE_SECS,
        )
        mdb = _setup_full(char_id=1, mayor_id=2)
        mdb.seed_character(char_id=2, room_id=10, credits=0)
        mdb.seed_membership(char_id=2, org_id=1, rank_level=5)
        char1 = _make_char(char_id=1, room_id=10)
        now = time.time()
        result = _run(construct_building(
            mdb, char1, "residence", 10, now=now,
        ))
        bid = result["building_id"]
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        # Mayor evicts.
        mayor = _run(mdb.get_character(2))
        _run(evict_building(mdb, mayor, bid, now=now + 25 * 3600))
        # 2-day notice not yet expired.
        stats = _run(tick_building_construction(
            mdb, now=now + 25 * 3600 + 3600,
        ))
        self.assertEqual(stats["evicted"], 0)
        # After eviction expiry.
        stats = _run(tick_building_construction(
            mdb, now=now + 25 * 3600 + EVICT_NOTICE_SECS + 1,
        ))
        self.assertEqual(stats["evicted"], 1)
        b = _run(get_building(mdb, bid))
        self.assertEqual(b["status"], "evicted")

    def test_evict_cleans_up_garrison_npcs(self):
        from engine.buildings import (
            construct_building, evict_building,
            tick_building_construction, get_building,
            EVICT_NOTICE_SECS,
        )
        mdb = _setup_full(char_id=1, mayor_id=2)
        mdb.seed_character(char_id=2, room_id=10, credits=0)
        mdb.seed_membership(char_id=2, org_id=1, rank_level=5)
        char1 = _make_char(char_id=1, room_id=10, credits=200000,
                           inventory={"resources": [
                               {"type": "metal", "quantity": 200,
                                "quality": 60.0},
                               {"type": "composite", "quantity": 200,
                                "quality": 60.0},
                               {"type": "chemical", "quantity": 200,
                                "quality": 60.0},
                           ]})
        now = time.time()
        result = _run(construct_building(
            mdb, char1, "garrison_annex", 10, now=now,
        ))
        bid = result["building_id"]
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        b = _run(get_building(mdb, bid))
        spawned_npcs = json.loads(b["npc_ids_json"])
        self.assertGreater(len(spawned_npcs), 0)
        mayor = _run(mdb.get_character(2))
        _run(evict_building(mdb, mayor, bid, now=now + 25 * 3600))
        _run(tick_building_construction(
            mdb, now=now + 25 * 3600 + EVICT_NOTICE_SECS + 1,
        ))
        # Garrison NPCs deleted.
        for nid in spawned_npcs:
            row = _run(mdb.get_npc(nid))
            self.assertIsNone(row)

    def test_tick_idempotent_no_pending(self):
        from engine.buildings import tick_building_construction
        mdb = _setup_full()
        stats = _run(tick_building_construction(mdb))
        self.assertEqual(stats["completed"], 0)
        self.assertEqual(stats["evicted"], 0)


# ══════════════════════════════════════════════════════════════════════
# 9. TestEffectLookupHelpers
# ══════════════════════════════════════════════════════════════════════

class TestEffectLookupHelpers(_BuildingTestCase):

    def _complete_building(self, mdb, char, category):
        from engine.buildings import (
            construct_building, tick_building_construction,
        )
        now = time.time()
        result = _run(construct_building(
            mdb, char, category, 10, now=now,
        ))
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        return result["building_id"]

    def test_crafting_station_bonus_returns_1d(self):
        from engine.buildings import get_crafting_station_bonus
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        # No crafting station yet.
        self.assertEqual(
            _run(get_crafting_station_bonus(mdb, char, 10)), 0,
        )
        self._complete_building(mdb, char, "crafting_station")
        # Now +1D.
        self.assertEqual(
            _run(get_crafting_station_bonus(mdb, char, 10)), 1,
        )

    def test_cultural_hall_lookup(self):
        from engine.buildings import get_cultural_hall_in_room
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        self.assertIsNone(_run(get_cultural_hall_in_room(mdb, 10)))
        self._complete_building(mdb, char, "cultural_hall")
        b = _run(get_cultural_hall_in_room(mdb, 10))
        self.assertIsNotNone(b)
        self.assertEqual(b["category"], "cultural_hall")

    def test_commerce_stall_lookup(self):
        from engine.buildings import get_commerce_stall_in_room
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        self.assertIsNone(_run(get_commerce_stall_in_room(mdb, 10)))
        self._complete_building(mdb, char, "commerce_stall")
        b = _run(get_commerce_stall_in_room(mdb, 10))
        self.assertIsNotNone(b)
        self.assertEqual(b["category"], "commerce_stall")

    def test_residence_for_owner_lookup(self):
        from engine.buildings import get_residence_for_owner
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        self.assertIsNone(_run(get_residence_for_owner(mdb, 1, 10)))
        self._complete_building(mdb, char, "residence")
        b = _run(get_residence_for_owner(mdb, 1, 10))
        self.assertIsNotNone(b)
        self.assertEqual(b["category"], "residence")
        # Other char doesn't get it.
        self.assertIsNone(_run(get_residence_for_owner(mdb, 99, 10)))


# ══════════════════════════════════════════════════════════════════════
# 10. TestResidenceStorage
# ══════════════════════════════════════════════════════════════════════

class TestResidenceStorage(_BuildingTestCase):

    def _make_residence(self, mdb, char):
        from engine.buildings import (
            construct_building, tick_building_construction,
        )
        now = time.time()
        result = _run(construct_building(
            mdb, char, "residence", 10, now=now,
        ))
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        return result["building_id"]

    def test_store_item_moves_to_residence(self):
        from engine.buildings import residence_store_item, get_building
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        bid = self._make_residence(mdb, char)
        # Reload char and add an item to inventory.
        c2 = _run(mdb.get_character(1))
        inv = json.loads(c2["inventory"])
        inv.setdefault("items", []).append({
            "name": "Old Datapad", "key": "datapad", "qty": 1,
        })
        c2["inventory"] = json.dumps(inv)
        _run(mdb.save_character(1, inventory=c2["inventory"]))
        c3 = _run(mdb.get_character(1))
        result = _run(residence_store_item(mdb, c3, bid, "datapad"))
        self.assertTrue(result["ok"])
        # Item moved.
        b = _run(get_building(mdb, bid))
        storage = json.loads(b["storage_json"])
        self.assertEqual(len(storage.get("items", [])), 1)
        c4 = _run(mdb.get_character(1))
        items4 = json.loads(c4["inventory"]).get("items", [])
        self.assertEqual(len(items4), 0)

    def test_take_item_moves_back(self):
        from engine.buildings import (
            residence_store_item, residence_take_item,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        bid = self._make_residence(mdb, char)
        # Store then take.
        c2 = _run(mdb.get_character(1))
        inv = json.loads(c2["inventory"])
        inv.setdefault("items", []).append({
            "name": "Old Datapad", "key": "datapad", "qty": 1,
        })
        c2["inventory"] = json.dumps(inv)
        _run(mdb.save_character(1, inventory=c2["inventory"]))
        c3 = _run(mdb.get_character(1))
        _run(residence_store_item(mdb, c3, bid, "datapad"))
        c4 = _run(mdb.get_character(1))
        result = _run(residence_take_item(mdb, c4, bid, "datapad"))
        self.assertTrue(result["ok"])
        c5 = _run(mdb.get_character(1))
        items = json.loads(c5["inventory"]).get("items", [])
        self.assertEqual(len(items), 1)

    def test_non_owner_cannot_store(self):
        from engine.buildings import residence_store_item
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10)
        bid = self._make_residence(mdb, char)
        mdb.seed_character(char_id=2, room_id=10, credits=0)
        char2 = _make_char(char_id=2, room_id=10, credits=0,
                           inventory={"items": [{"name": "Stuff",
                                                "key": "stuff",
                                                "qty": 1}]})
        result = _run(residence_store_item(mdb, char2, bid, "stuff"))
        self.assertFalse(result["ok"])
        self.assertIn("don't own", result["msg"])

    def test_wrong_type_rejected(self):
        from engine.buildings import (
            construct_building, tick_building_construction,
            residence_store_item,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10, credits=200000,
                          inventory={"resources": [
                              {"type": "metal", "quantity": 200,
                               "quality": 60.0},
                              {"type": "composite", "quantity": 200,
                               "quality": 60.0},
                          ]})
        now = time.time()
        result = _run(construct_building(
            mdb, char, "crafting_station", 10, now=now,
        ))
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        bid = result["building_id"]
        char = _run(mdb.get_character(1))
        result = _run(residence_store_item(mdb, char, bid, "x"))
        self.assertFalse(result["ok"])
        self.assertIn("not a residence", result["msg"].lower())


# ══════════════════════════════════════════════════════════════════════
# 11. TestRebuildDiscount
# ══════════════════════════════════════════════════════════════════════

class TestRebuildDiscount(_BuildingTestCase):

    def test_rebuild_discount_applied(self):
        from engine.buildings import (
            construct_building, demolish_building,
            tick_building_construction, BUILDING_CATEGORIES,
            REBUILD_DISCOUNT_PCT,
        )
        mdb = _setup_full()
        char = _make_char(char_id=1, room_id=10, credits=200000,
                          inventory={"resources": [
                              {"type": "metal", "quantity": 200,
                               "quality": 60.0},
                              {"type": "organic", "quantity": 200,
                               "quality": 60.0},
                              {"type": "composite", "quantity": 200,
                               "quality": 60.0},
                          ]})
        # Construct + complete + demolish.
        now = time.time()
        r1 = _run(construct_building(
            mdb, char, "residence", 10, now=now,
        ))
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        char = _run(mdb.get_character(1))
        _run(demolish_building(mdb, char, r1["building_id"]))
        char = _run(mdb.get_character(1))
        # Rebuild — should get discount.
        r2 = _run(construct_building(
            mdb, char, "residence", 10, now=now + 26 * 3600,
        ))
        self.assertTrue(r2["ok"])
        self.assertTrue(r2["rebuild_discount_applied"])
        # Material costs reduced by 10%.
        full_cost = BUILDING_CATEGORIES["residence"]["material_costs"]
        rebate = REBUILD_DISCOUNT_PCT / 100.0
        for (rtype, qty), (rtype2, actual_qty) in zip(
            full_cost, r2["material_costs"],
        ):
            expected = max(1, int(round(qty * (1.0 - rebate))))
            self.assertEqual(actual_qty, expected)
            self.assertEqual(rtype, rtype2)

    def test_different_owner_no_discount(self):
        from engine.buildings import (
            construct_building, demolish_building,
            tick_building_construction,
        )
        # Char 1 constructs + demolishes; char 2 rebuilds.
        mdb = _setup_full(char_id=1)
        # Seed char 2 with same rank.
        mdb.seed_character(char_id=2, room_id=10, credits=20000,
                           inventory={
                               "resources": [
                                   {"type": "metal", "quantity": 50,
                                    "quality": 60.0},
                                   {"type": "organic", "quantity": 50,
                                    "quality": 60.0},
                               ],
                               "items": [],
                           })
        mdb.seed_membership(char_id=2, org_id=1, rank_level=3)
        char1 = _make_char(char_id=1, room_id=10, credits=200000,
                           inventory={"resources": [
                               {"type": "metal", "quantity": 200,
                                "quality": 60.0},
                               {"type": "organic", "quantity": 200,
                                "quality": 60.0},
                           ]})
        now = time.time()
        r1 = _run(construct_building(
            mdb, char1, "residence", 10, now=now,
        ))
        _run(tick_building_construction(mdb, now=now + 25 * 3600))
        char1 = _run(mdb.get_character(1))
        _run(demolish_building(mdb, char1, r1["building_id"]))
        # Char 2 builds. Should NOT get rebuild discount (different owner).
        char2 = _run(mdb.get_character(2))
        r2 = _run(construct_building(
            mdb, char2, "residence", 10, now=now + 26 * 3600,
        ))
        self.assertTrue(r2["ok"])
        self.assertFalse(r2["rebuild_discount_applied"])


if __name__ == "__main__":
    unittest.main()
