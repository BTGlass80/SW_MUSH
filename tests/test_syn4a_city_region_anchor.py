# -*- coding: utf-8 -*-
"""
tests/test_syn4a_city_region_anchor.py — SYN.4a (2026-05-25).

Pins the new region-anchored founding + expansion surfaces in
``engine/player_cities.py``, shipped in the combined SYN.4 drop per
``contestable_wilderness_design_v2.md`` §2.9.1 + §3.4.

Companion to ``tests/test_syn4b_vitality_and_migration.py`` (vitality
state machine + one-shot dissolution migration).

Test sections
─────────────
  1. TestFoundCityInRegion      — happy path + each validation rejection
  2. TestRegionEligibility      — owned-by-self / rival / un-owned + foothold
  3. TestClaimLandmarkForCity   — landmark adjacency, region membership,
                                  size cap, vitality block, contiguity
  4. TestConstantsAndShape      — constants + module-level invariants
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
    """Run a coroutine in a fresh event loop (BugFix5 Py3.14 pattern)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────
# In-memory DB stand-in — covers the surfaces SYN.4 needs.
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
    """In-memory DB with the surfaces SYN.4 cares about.

    Tables created:
      rooms, exits, zones, organizations, memberships, characters,
      player_housing, player_cities, player_city_rooms,
      region_ownership, territory_influence, region_garrison,
      region_contests (for is_region_in_active_contest no-op)
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
            CREATE TABLE exits (
                from_room_id INTEGER NOT NULL,
                to_room_id   INTEGER NOT NULL,
                direction    TEXT
            );
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name TEXT,
                properties TEXT DEFAULT '{"security":"lawless"}'
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
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                last_login REAL DEFAULT 0
            );
            CREATE TABLE player_housing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                char_id INTEGER DEFAULT 0,
                tier INTEGER NOT NULL DEFAULT 1,
                housing_type TEXT NOT NULL DEFAULT 'rented_room',
                entry_room_id INTEGER,
                room_ids TEXT NOT NULL DEFAULT '[]',
                storage_max INTEGER NOT NULL DEFAULT 20,
                faction_code TEXT
            );
            CREATE TABLE player_cities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                name_lower TEXT NOT NULL,
                org_id INTEGER NOT NULL,
                hq_id INTEGER NOT NULL,
                zone_id INTEGER,
                is_wilderness INTEGER NOT NULL DEFAULT 0,
                wilderness_region_id TEXT,
                wilderness_x INTEGER,
                wilderness_y INTEGER,
                is_hidden INTEGER NOT NULL DEFAULT 0,
                search_difficulty INTEGER DEFAULT 20,
                visibility_factions TEXT DEFAULT '[]',
                founded_at REAL NOT NULL,
                founder_id INTEGER NOT NULL,
                mayor_id INTEGER NOT NULL,
                tax_rate REAL NOT NULL DEFAULT 0.0,
                rate_cap REAL NOT NULL DEFAULT 0.10,
                motd TEXT DEFAULT '',
                state TEXT NOT NULL DEFAULT 'active',
                grace_started_at REAL DEFAULT 0,
                revenue_total INTEGER DEFAULT 0,
                revenue_week INTEGER DEFAULT 0,
                week_start_ts REAL NOT NULL,
                hq_tier TEXT NOT NULL DEFAULT 'outpost',
                maint_paid_until REAL NOT NULL DEFAULT 0,
                vitality_state TEXT NOT NULL DEFAULT 'active',
                vitality_below_since REAL DEFAULT NULL
            );
            CREATE TABLE player_city_rooms (
                city_id INTEGER NOT NULL,
                room_id INTEGER NOT NULL,
                is_center INTEGER NOT NULL DEFAULT 0,
                citizen_only INTEGER NOT NULL DEFAULT 0,
                claimed_at REAL NOT NULL,
                PRIMARY KEY (city_id, room_id)
            );
            CREATE TABLE region_ownership (
                region_slug   TEXT    NOT NULL PRIMARY KEY,
                org_code      TEXT    NOT NULL,
                zone_id       INTEGER,
                claimed_by    INTEGER NOT NULL,
                claimed_at    REAL    NOT NULL,
                maintenance   INTEGER NOT NULL DEFAULT 3000
            );
            CREATE TABLE territory_influence (
                zone_id INTEGER NOT NULL,
                org_code TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                last_activity REAL NOT NULL DEFAULT 0,
                last_presence REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (zone_id, org_code)
            );
            CREATE TABLE region_garrison (
                region_slug TEXT    NOT NULL,
                npc_id      INTEGER NOT NULL,
                PRIMARY KEY (region_slug, npc_id)
            );
        """)
        self._db._conn.commit()

    # raw SQL pass-through
    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

    # ORM helpers
    async def get_organization(self, org_code):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM organizations WHERE code = ?", (org_code,))
        return dict(rows[0]) if rows else None

    async def get_membership(self, char_id, org_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM memberships WHERE char_id = ? AND org_id = ?",
            (char_id, org_id))
        return dict(rows[0]) if rows else None

    async def adjust_org_treasury(self, org_id, delta):
        rows = await self._db.execute_fetchall(
            "SELECT treasury FROM organizations WHERE id = ?", (org_id,))
        cur = int(rows[0]["treasury"]) if rows else 0
        new_balance = cur + int(delta)
        await self._db.execute(
            "UPDATE organizations SET treasury = ? WHERE id = ?",
            (new_balance, org_id))
        await self._db.commit()
        return new_balance

    async def get_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (room_id,))
        return dict(rows[0]) if rows else None

    async def get_zone(self, zone_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,))
        return dict(rows[0]) if rows else None

    # Seed helpers
    def seed_org(self, *, org_id, code, treasury=500_000):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name, treasury) "
            "VALUES (?, ?, ?, ?)",
            (org_id, code, code.title(), treasury))
        self._db._conn.commit()

    def seed_character(self, *, char_id, name="Hero", last_login=None):
        if last_login is None:
            last_login = time.time()
        self._db._conn.execute(
            "INSERT INTO characters (id, name, last_login) VALUES (?, ?, ?)",
            (char_id, name, last_login))
        self._db._conn.commit()

    def seed_membership(self, *, char_id, org_id, rank_level=5):
        self._db._conn.execute(
            "INSERT INTO memberships (char_id, org_id, rank_level) "
            "VALUES (?, ?, ?)",
            (char_id, org_id, rank_level))
        self._db._conn.commit()

    def seed_zone(self, *, zone_id, name, declared_security="contested"):
        props = json.dumps({"security": declared_security})
        self._db._conn.execute(
            "INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
            (zone_id, name, props))
        self._db._conn.commit()

    def seed_hq(self, *, hq_id, org_code, tier=5, storage_max=100,
                room_ids=None, entry_room_id=None):
        if room_ids is None:
            room_ids = [9001, 9002]
        self._db._conn.execute(
            "INSERT INTO player_housing "
            "(id, faction_code, housing_type, tier, storage_max, "
            " room_ids, entry_room_id) "
            "VALUES (?, ?, 'org_hq', ?, ?, ?, ?)",
            (hq_id, org_code, tier, storage_max,
             json.dumps(room_ids),
             entry_room_id or room_ids[0]))
        # Make sure the HQ rooms exist
        for rid in room_ids:
            self._db._conn.execute(
                "INSERT OR IGNORE INTO rooms (id, name) VALUES (?, ?)",
                (rid, f"HQ room #{rid}"))
        if entry_room_id and entry_room_id not in room_ids:
            self._db._conn.execute(
                "INSERT OR IGNORE INTO rooms (id, name) VALUES (?, ?)",
                (entry_room_id, f"HQ entry"))
        self._db._conn.commit()

    def seed_region(self, *, slug, zone_id, owner_org_code=None,
                    landmark_count=3, start_room_id=100,
                    chain_exits=True):
        """Create a wilderness region with landmark rooms.

        chain_exits=True wires each landmark to the next via a north
        exit (and reverse south), so the contiguity check has something
        to find.
        """
        for i in range(landmark_count):
            self._db._conn.execute(
                "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) "
                "VALUES (?, ?, ?, ?)",
                (start_room_id + i, f"{slug} #{i+1}",
                 zone_id, slug))
            if chain_exits and i > 0:
                # north: prev → this
                self._db._conn.execute(
                    "INSERT INTO exits (from_room_id, to_room_id, direction) "
                    "VALUES (?, ?, 'north')",
                    (start_room_id + i - 1, start_room_id + i))
                # south: this → prev (reverse)
                self._db._conn.execute(
                    "INSERT INTO exits (from_room_id, to_room_id, direction) "
                    "VALUES (?, ?, 'south')",
                    (start_room_id + i, start_room_id + i - 1))
        if owner_org_code:
            self._db._conn.execute(
                "INSERT INTO region_ownership "
                "(region_slug, org_code, zone_id, claimed_by, claimed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (slug, owner_org_code, zone_id, 1, time.time()))
        self._db._conn.commit()

    def seed_influence(self, *, zone_id, org_code, score):
        now = time.time()
        self._db._conn.execute(
            "INSERT INTO territory_influence "
            "(zone_id, org_code, score, last_activity, last_presence) "
            "VALUES (?, ?, ?, ?, ?)",
            (zone_id, org_code, score, now, now))
        self._db._conn.commit()

    def seed_hq_entry_exit_to_landmark(self, *, hq_entry_room_id,
                                         landmark_room_id):
        """Wire an exit from the HQ entry room to a region landmark
        so contiguity can find a connection."""
        self._db._conn.execute(
            "INSERT INTO exits (from_room_id, to_room_id, direction) "
            "VALUES (?, ?, 'out')",
            (hq_entry_room_id, landmark_room_id))
        self._db._conn.execute(
            "INSERT INTO exits (from_room_id, to_room_id, direction) "
            "VALUES (?, ?, 'in')",
            (landmark_room_id, hq_entry_room_id))
        self._db._conn.commit()


# ──────────────────────────────────────────────────────────────────────
# 1. TestFoundCityInRegion
# ──────────────────────────────────────────────────────────────────────

class TestFoundCityInRegion(unittest.TestCase):
    """Happy path + each validation rejection for the new founding."""

    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_org(org_id=1, code="hutt_cartel", treasury=500_000)
        self.mdb.seed_character(char_id=1, name="Boss")
        self.mdb.seed_membership(char_id=1, org_id=1, rank_level=5)
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_hq(hq_id=1, org_code="hutt_cartel",
                          room_ids=[9001, 9002], entry_room_id=9001)
        self.mdb.seed_region(slug="dune_sea", zone_id=1,
                              owner_org_code="hutt_cartel")
        self.char = {"id": 1, "name": "Boss", "faction_id": "hutt_cartel"}

    def test_happy_path_owned_region(self):
        from engine.player_cities import found_city_in_region
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Dune Citadel", "dune_sea"))
        self.assertTrue(ok, msg=msg)
        # Verify row inserted with wilderness_region_id set
        rows = _run(self.mdb.fetchall(
            "SELECT wilderness_region_id, hq_tier, state, vitality_state "
            "FROM player_cities WHERE name = ?",
            ("Dune Citadel",)))
        self.assertEqual(rows[0]["wilderness_region_id"], "dune_sea")
        self.assertEqual(rows[0]["state"], "active")
        self.assertEqual(rows[0]["vitality_state"], "active")

    def test_rejects_independent_faction(self):
        from engine.player_cities import found_city_in_region
        char = {"id": 1, "name": "Hero", "faction_id": "independent"}
        ok, msg = _run(found_city_in_region(
            self.mdb, char, "Loner Town", "dune_sea"))
        self.assertFalse(ok)
        self.assertIn("not a member", msg.lower())

    def test_rejects_low_rank(self):
        from engine.player_cities import found_city_in_region
        # Demote char to rank 4
        _run(self.mdb.execute(
            "UPDATE memberships SET rank_level = 4 WHERE char_id = 1"))
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Mid-Rank Mansion", "dune_sea"))
        self.assertFalse(ok)
        self.assertIn("rank", msg.lower())

    def test_rejects_duplicate_name(self):
        from engine.player_cities import found_city_in_region
        ok, _ = _run(found_city_in_region(
            self.mdb, self.char, "Dune Citadel", "dune_sea"))
        self.assertTrue(ok)
        # Try again with same name but different org
        self.mdb.seed_org(org_id=2, code="cis", treasury=500_000)
        self.mdb.seed_character(char_id=2, name="Other")
        self.mdb.seed_membership(char_id=2, org_id=2, rank_level=5)
        self.mdb.seed_hq(hq_id=2, org_code="cis",
                          room_ids=[8001, 8002], entry_room_id=8001)
        self.mdb.seed_region(slug="other_region", zone_id=1,
                              owner_org_code="cis",
                              start_room_id=200)
        other_char = {"id": 2, "faction_id": "cis"}
        ok2, msg2 = _run(found_city_in_region(
            self.mdb, other_char, "Dune Citadel", "other_region"))
        self.assertFalse(ok2)
        self.assertIn("already exists", msg2.lower())

    def test_rejects_no_hq(self):
        from engine.player_cities import found_city_in_region
        # Wipe HQ row
        _run(self.mdb.execute(
            "DELETE FROM player_housing WHERE faction_code = 'hutt_cartel'"))
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "No HQ City", "dune_sea"))
        self.assertFalse(ok)
        self.assertIn("hq", msg.lower())

    def test_rejects_unknown_region(self):
        from engine.player_cities import found_city_in_region
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Phantom City", "nonexistent_slug"))
        self.assertFalse(ok)
        self.assertIn("not a recognized wilderness region", msg.lower())

    def test_rejects_org_with_existing_city(self):
        from engine.player_cities import found_city_in_region
        ok, _ = _run(found_city_in_region(
            self.mdb, self.char, "First City", "dune_sea"))
        self.assertTrue(ok)
        # Same org, same flow - even with a different region
        self.mdb.seed_region(slug="other_region", zone_id=1,
                              owner_org_code="hutt_cartel",
                              start_room_id=200)
        ok2, msg2 = _run(found_city_in_region(
            self.mdb, self.char, "Second City", "other_region"))
        self.assertFalse(ok2)
        self.assertIn("already has a city", msg2.lower())

    def test_rejects_insufficient_treasury(self):
        from engine.player_cities import found_city_in_region
        # 100cr is way under the outpost cost (25,000)
        _run(self.mdb.execute(
            "UPDATE organizations SET treasury = 100 WHERE code = 'hutt_cartel'"))
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Broke City", "dune_sea"))
        self.assertFalse(ok)
        self.assertIn("insufficient", msg.lower())

    def test_debits_treasury_on_success(self):
        from engine.player_cities import (
            found_city_in_region, FOUNDING_COSTS,
        )
        ok, _ = _run(found_city_in_region(
            self.mdb, self.char, "Cost Center", "dune_sea"))
        self.assertTrue(ok)
        rows = _run(self.mdb.fetchall(
            "SELECT treasury FROM organizations WHERE code = 'hutt_cartel'"))
        # 500_000 - 25_000 (outpost cost from storage_max=100)
        self.assertEqual(rows[0]["treasury"],
                          500_000 - FOUNDING_COSTS["outpost"])

    def test_anchors_hq_rooms_as_city_center(self):
        from engine.player_cities import found_city_in_region
        ok, _ = _run(found_city_in_region(
            self.mdb, self.char, "HQ Anchor Test", "dune_sea"))
        self.assertTrue(ok)
        rows = _run(self.mdb.fetchall(
            "SELECT room_id, is_center FROM player_city_rooms "
            "WHERE is_center = 1"))
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["room_id"] for r in rows}, {9001, 9002})


# ──────────────────────────────────────────────────────────────────────
# 2. TestRegionEligibility
# ──────────────────────────────────────────────────────────────────────

class TestRegionEligibility(unittest.TestCase):
    """Owned-by-self / rival / un-owned + foothold influence rules."""

    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_org(org_id=1, code="hutt_cartel", treasury=500_000)
        self.mdb.seed_org(org_id=2, code="cis", treasury=500_000)
        self.mdb.seed_character(char_id=1, name="Boss")
        self.mdb.seed_membership(char_id=1, org_id=1, rank_level=5)
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_hq(hq_id=1, org_code="hutt_cartel",
                          room_ids=[9001, 9002], entry_room_id=9001)
        self.char = {"id": 1, "faction_id": "hutt_cartel"}

    def test_owned_by_self_no_influence_check(self):
        """When the founder's org owns the region, no influence
        check is required."""
        from engine.player_cities import found_city_in_region
        # Region owned by hutt_cartel; no seeded influence
        self.mdb.seed_region(slug="dune_sea", zone_id=1,
                              owner_org_code="hutt_cartel")
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Owned-Region City", "dune_sea"))
        self.assertTrue(ok, msg=msg)

    def test_owned_by_rival_rejected(self):
        """Rival owns the region → must contest first."""
        from engine.player_cities import found_city_in_region
        self.mdb.seed_region(slug="dune_sea", zone_id=1,
                              owner_org_code="cis")
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Rival-Region City", "dune_sea"))
        self.assertFalse(ok)
        self.assertIn("contest", msg.lower())

    def test_unowned_requires_foothold(self):
        """Un-owned region needs 50+ influence in parent zone."""
        from engine.player_cities import found_city_in_region
        self.mdb.seed_region(slug="open_region", zone_id=1,
                              owner_org_code=None)
        # No influence seeded
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "No-Influence City", "open_region"))
        self.assertFalse(ok)
        self.assertIn("foothold", msg.lower())

    def test_unowned_with_foothold_succeeds(self):
        from engine.player_cities import found_city_in_region
        self.mdb.seed_region(slug="open_region", zone_id=1,
                              owner_org_code=None)
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel",
                                  score=60)
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Foothold City", "open_region"))
        self.assertTrue(ok, msg=msg)

    def test_unowned_exactly_at_threshold_succeeds(self):
        from engine.player_cities import (
            found_city_in_region, CITY_FOUNDING_MIN_FOOTHOLD,
        )
        self.mdb.seed_region(slug="open_region", zone_id=1,
                              owner_org_code=None)
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel",
                                  score=CITY_FOUNDING_MIN_FOOTHOLD)
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Threshold City", "open_region"))
        self.assertTrue(ok, msg=msg)

    def test_unowned_just_below_threshold_rejected(self):
        from engine.player_cities import (
            found_city_in_region, CITY_FOUNDING_MIN_FOOTHOLD,
        )
        self.mdb.seed_region(slug="open_region", zone_id=1,
                              owner_org_code=None)
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel",
                                  score=CITY_FOUNDING_MIN_FOOTHOLD - 1)
        ok, msg = _run(found_city_in_region(
            self.mdb, self.char, "Almost-Foothold City",
            "open_region"))
        self.assertFalse(ok)
        self.assertIn("foothold", msg.lower())


# ──────────────────────────────────────────────────────────────────────
# 3. TestClaimLandmarkForCity
# ──────────────────────────────────────────────────────────────────────

class TestClaimLandmarkForCity(unittest.TestCase):
    """Landmark adjacency + region membership + size cap + vitality block."""

    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_org(org_id=1, code="hutt_cartel", treasury=500_000)
        self.mdb.seed_character(char_id=1, name="Boss")
        self.mdb.seed_membership(char_id=1, org_id=1, rank_level=5)
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_hq(hq_id=1, org_code="hutt_cartel",
                          room_ids=[9001, 9002], entry_room_id=9001)
        # Wilderness region with 5 landmarks at 100..104 chained N/S
        self.mdb.seed_region(slug="dune_sea", zone_id=1,
                              owner_org_code="hutt_cartel",
                              landmark_count=5,
                              start_room_id=100)
        # Wire HQ entry → landmark 100 so contiguity has an anchor
        self.mdb.seed_hq_entry_exit_to_landmark(
            hq_entry_room_id=9001, landmark_room_id=100)

        self.char = {"id": 1, "faction_id": "hutt_cartel"}
        # Found a city
        from engine.player_cities import found_city_in_region
        ok, _ = _run(found_city_in_region(
            self.mdb, self.char, "Dune Citadel", "dune_sea"))
        assert ok
        rows = _run(self.mdb.fetchall(
            "SELECT id FROM player_cities WHERE name = 'Dune Citadel'"))
        self.city_id = rows[0]["id"]

    def test_claim_adjacent_landmark_succeeds(self):
        from engine.player_cities import claim_landmark_for_city
        from engine import jedi_gating as cooldowns
        original = cooldowns.cooldowns_enabled
        cooldowns.cooldowns_enabled = lambda: False
        try:
            # Landmark 100 is adjacent to HQ entry (9001 ←→ 100 wired)
            ok, msg = _run(claim_landmark_for_city(
                self.mdb, self.char, 100))
            self.assertTrue(ok, msg=msg)
            # Now landmark 101 is adjacent to landmark 100 via the chain
            ok2, msg2 = _run(claim_landmark_for_city(
                self.mdb, self.char, 101))
            self.assertTrue(ok2, msg=msg2)
        finally:
            cooldowns.cooldowns_enabled = original

    def test_rejects_non_landmark_room(self):
        """A room that isn't a landmark of the city's region."""
        from engine.player_cities import claim_landmark_for_city
        # Create a room in a different region
        _run(self.mdb.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) "
            "VALUES (500, 'Outsider', 1, 'other_region')"))
        ok, msg = _run(claim_landmark_for_city(
            self.mdb, self.char, 500))
        self.assertFalse(ok)
        self.assertIn("not a landmark", msg.lower())

    def test_rejects_non_adjacent_landmark(self):
        """Skipping past landmark 100 to claim 102 directly should fail."""
        from engine.player_cities import claim_landmark_for_city
        # Landmark 102 is NOT adjacent to HQ entry (only 100 is)
        ok, msg = _run(claim_landmark_for_city(
            self.mdb, self.char, 102))
        self.assertFalse(ok)
        self.assertIn("not adjacent", msg.lower())

    def test_size_cap_enforced(self):
        """Outpost tier caps at 5 expansion rooms."""
        from engine.player_cities import (
            claim_landmark_for_city, MAX_EXPANSION_ROOMS,
        )
        # Disable rate-limit for the test
        from engine import jedi_gating as cooldowns
        original = cooldowns.cooldowns_enabled
        cooldowns.cooldowns_enabled = lambda: False
        try:
            # Outpost cap = 5; we have landmarks 100..104 = 5 rooms
            for rid in (100, 101, 102, 103, 104):
                ok, msg = _run(claim_landmark_for_city(
                    self.mdb, self.char, rid))
                self.assertTrue(ok, msg=f"claim {rid}: {msg}")
            # 6th claim would exceed cap, but only 5 landmarks exist
            # so we'll test with extra landmark
            _run(self.mdb.execute(
                "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) "
                "VALUES (105, 'extra', 1, 'dune_sea')"))
            _run(self.mdb.execute(
                "INSERT INTO exits (from_room_id, to_room_id, direction) "
                "VALUES (104, 105, 'north')"))
            ok6, msg6 = _run(claim_landmark_for_city(
                self.mdb, self.char, 105))
            self.assertFalse(ok6)
            self.assertIn("cap", msg6.lower())
        finally:
            cooldowns.cooldowns_enabled = original

    def test_vitality_reduced_blocks_expansion(self):
        from engine.player_cities import claim_landmark_for_city
        # Manually mark the city's vitality as 'reduced'
        _run(self.mdb.execute(
            "UPDATE player_cities SET vitality_state = 'reduced' WHERE id = ?",
            (self.city_id,)))
        ok, msg = _run(claim_landmark_for_city(
            self.mdb, self.char, 100))
        self.assertFalse(ok)
        self.assertIn("vitality", msg.lower())

    def test_vitality_dormant_blocks_expansion(self):
        from engine.player_cities import claim_landmark_for_city
        _run(self.mdb.execute(
            "UPDATE player_cities SET vitality_state = 'dormant' WHERE id = ?",
            (self.city_id,)))
        ok, msg = _run(claim_landmark_for_city(
            self.mdb, self.char, 100))
        self.assertFalse(ok)
        self.assertIn("vitality", msg.lower())

    def test_rejects_legacy_city_map_city(self):
        """Cities founded via legacy found_city have no
        wilderness_region_id; the new API refuses them."""
        from engine.player_cities import claim_landmark_for_city
        # Force the city to be a legacy city-map city
        _run(self.mdb.execute(
            "UPDATE player_cities SET wilderness_region_id = NULL WHERE id = ?",
            (self.city_id,)))
        ok, msg = _run(claim_landmark_for_city(
            self.mdb, self.char, 100))
        self.assertFalse(ok)
        self.assertIn("not anchored on a wilderness region", msg.lower())


# ──────────────────────────────────────────────────────────────────────
# 4. TestConstantsAndShape
# ──────────────────────────────────────────────────────────────────────

class TestConstantsAndShape(unittest.TestCase):
    """Module-level invariants on constants + shape."""

    def test_foothold_threshold_value(self):
        from engine.player_cities import (
            CITY_FOUNDING_MIN_FOOTHOLD, MIN_INFLUENCE_TO_FOUND,
        )
        # Per design §2.9.1 + the alias semantics, these must agree.
        self.assertEqual(CITY_FOUNDING_MIN_FOOTHOLD,
                          MIN_INFLUENCE_TO_FOUND)
        self.assertEqual(CITY_FOUNDING_MIN_FOOTHOLD, 50)

    def test_vitality_thresholds_complete(self):
        from engine.player_cities import (
            CITY_VITALITY_THRESHOLDS, MAX_EXPANSION_ROOMS,
        )
        # Every HQ tier in MAX_EXPANSION_ROOMS must have a vitality
        # threshold (otherwise compute_vitality_threshold falls back
        # to a default and the design's per-tier rules don't apply).
        for tier in MAX_EXPANSION_ROOMS:
            self.assertIn(tier, CITY_VITALITY_THRESHOLDS,
                           f"Missing vitality threshold for {tier!r}")

    def test_vitality_thresholds_match_design(self):
        from engine.player_cities import CITY_VITALITY_THRESHOLDS
        # Per design §2.9.4
        self.assertEqual(CITY_VITALITY_THRESHOLDS["outpost"], 1)
        self.assertEqual(CITY_VITALITY_THRESHOLDS["chapter_house"], 3)
        self.assertEqual(CITY_VITALITY_THRESHOLDS["fortress"], 5)

    def test_migration_refund_ratio(self):
        from engine.player_cities import SYN4_MIGRATION_REFUND_RATIO
        # Per design §2.9.2: "75% refund"
        self.assertAlmostEqual(SYN4_MIGRATION_REFUND_RATIO, 0.75)

    def test_active_window_is_7_days(self):
        from engine.player_cities import (
            CITY_VITALITY_ACTIVE_WINDOW_DAYS,
            CITY_VITALITY_ACTIVE_WINDOW_SECS,
        )
        self.assertEqual(CITY_VITALITY_ACTIVE_WINDOW_DAYS, 7)
        self.assertEqual(CITY_VITALITY_ACTIVE_WINDOW_SECS,
                          7 * 24 * 60 * 60)

    def test_dormant_grace_is_14_days(self):
        from engine.player_cities import (
            CITY_VITALITY_DORMANT_GRACE_DAYS,
            CITY_VITALITY_DORMANT_GRACE_SECS,
        )
        self.assertEqual(CITY_VITALITY_DORMANT_GRACE_DAYS, 14)
        self.assertEqual(CITY_VITALITY_DORMANT_GRACE_SECS,
                          14 * 24 * 60 * 60)

    def test_reduced_tax_multiplier(self):
        from engine.player_cities import (
            CITY_VITALITY_TAX_MULTIPLIER_REDUCED,
        )
        # Per design: "Tax cap drops to 50%"
        self.assertAlmostEqual(CITY_VITALITY_TAX_MULTIPLIER_REDUCED, 0.5)


if __name__ == "__main__":
    unittest.main()
