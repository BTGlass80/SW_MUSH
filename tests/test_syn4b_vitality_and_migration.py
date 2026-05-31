# -*- coding: utf-8 -*-
"""
tests/test_syn4b_vitality_and_migration.py — SYN.4b (2026-05-25).

Pins the city vitality mechanic + the one-shot SYN.4 migration that
dissolves pre-pivot city-map cities with a 75% refund. Per
``contestable_wilderness_design_v2.md`` §2.9.2 + §2.9.4.

Test sections
─────────────
  1. TestComputeVitalityThreshold   — pure-rule HQ-tier → count
  2. TestComputeVitalityState        — pure-rule state machine
  3. TestEffectiveTaxRateCap         — pure-rule tax cap reduction
  4. TestCountActiveCitizens         — DB-touching counter
  5. TestTickCityVitality            — full tick path + state transitions
  6. TestSyn4MigrationHappyPath      — dissolution + refund + rooms cleared
  7. TestSyn4MigrationIdempotency    — second run no-op + marker stable
  8. TestSyn4MigrationScope          — only city-map cities; wilderness skipped
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
# Minimal DB stand-in shared with SYN.4a — duplicated rather than
# imported to keep test isolation simple.
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
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                last_login REAL DEFAULT 0
            );
            CREATE TABLE player_cities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                name_lower TEXT NOT NULL,
                org_id INTEGER NOT NULL,
                hq_id INTEGER NOT NULL,
                zone_id INTEGER,
                wilderness_region_id TEXT,
                founded_at REAL NOT NULL,
                founder_id INTEGER NOT NULL,
                mayor_id INTEGER NOT NULL,
                tax_rate REAL NOT NULL DEFAULT 0.0,
                rate_cap REAL NOT NULL DEFAULT 0.10,
                state TEXT NOT NULL DEFAULT 'active',
                grace_started_at REAL DEFAULT 0,
                week_start_ts REAL NOT NULL,
                hq_tier TEXT NOT NULL DEFAULT 'outpost',
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
        """)
        self._db._conn.commit()

    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

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

    # Seed helpers
    def seed_org(self, *, org_id, code, treasury=0):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name, treasury) "
            "VALUES (?, ?, ?, ?)",
            (org_id, code, code.title(), treasury))
        self._db._conn.commit()

    def seed_char(self, *, char_id, last_login=None):
        if last_login is None:
            last_login = time.time()
        self._db._conn.execute(
            "INSERT INTO characters (id, name, last_login) VALUES (?, ?, ?)",
            (char_id, f"Char{char_id}", last_login))
        self._db._conn.commit()

    def seed_membership(self, *, char_id, org_id, rank_level=1):
        self._db._conn.execute(
            "INSERT INTO memberships (char_id, org_id, rank_level) "
            "VALUES (?, ?, ?)",
            (char_id, org_id, rank_level))
        self._db._conn.commit()

    def seed_city(self, *, city_id, name, org_id, hq_tier="outpost",
                   wilderness_region_id=None,
                   state="active", rate_cap=0.10,
                   vitality_state="active",
                   vitality_below_since=None):
        now = time.time()
        self._db._conn.execute(
            "INSERT INTO player_cities "
            "(id, name, name_lower, org_id, hq_id, "
            " wilderness_region_id, founded_at, founder_id, mayor_id, "
            " week_start_ts, hq_tier, state, rate_cap, "
            " vitality_state, vitality_below_since) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (city_id, name, name.lower(), org_id, 1,
             wilderness_region_id, now, 1, 1, now, hq_tier,
             state, rate_cap, vitality_state, vitality_below_since))
        self._db._conn.commit()

    def seed_city_room(self, *, city_id, room_id, is_center=0):
        now = time.time()
        self._db._conn.execute(
            "INSERT INTO player_city_rooms "
            "(city_id, room_id, is_center, claimed_at) VALUES "
            "(?, ?, ?, ?)",
            (city_id, room_id, is_center, now))
        self._db._conn.commit()


# ──────────────────────────────────────────────────────────────────────
# 1. TestComputeVitalityThreshold (pure rule)
# ──────────────────────────────────────────────────────────────────────

class TestComputeVitalityThreshold(unittest.TestCase):
    def test_outpost(self):
        from engine.player_cities import compute_vitality_threshold
        self.assertEqual(compute_vitality_threshold("outpost"), 1)

    def test_chapter_house(self):
        from engine.player_cities import compute_vitality_threshold
        self.assertEqual(compute_vitality_threshold("chapter_house"), 3)

    def test_fortress(self):
        from engine.player_cities import compute_vitality_threshold
        self.assertEqual(compute_vitality_threshold("fortress"), 5)

    def test_unknown_tier_defaults_to_one(self):
        from engine.player_cities import compute_vitality_threshold
        self.assertEqual(compute_vitality_threshold("nonexistent"), 1)


# ──────────────────────────────────────────────────────────────────────
# 2. TestComputeVitalityState (pure rule, state machine)
# ──────────────────────────────────────────────────────────────────────

class TestComputeVitalityState(unittest.TestCase):
    """The 4-branch state machine in pure-rule form."""

    def test_at_or_above_threshold_active_no_below_since(self):
        from engine.player_cities import compute_vitality_state
        state, since = compute_vitality_state(
            active_count=3, threshold=3, below_since=None, now=1000.0)
        self.assertEqual(state, "active")
        self.assertIsNone(since)

    def test_at_or_above_clears_below_since(self):
        """Recovery: count rises back to threshold → below_since cleared."""
        from engine.player_cities import compute_vitality_state
        state, since = compute_vitality_state(
            active_count=5, threshold=3, below_since=500.0, now=1000.0)
        self.assertEqual(state, "active")
        self.assertIsNone(since)

    def test_below_threshold_first_drop_records_now(self):
        from engine.player_cities import compute_vitality_state
        state, since = compute_vitality_state(
            active_count=2, threshold=3, below_since=None, now=1000.0)
        self.assertEqual(state, "reduced")
        self.assertEqual(since, 1000.0)

    def test_below_threshold_under_14d_grace_preserved(self):
        from engine.player_cities import (
            compute_vitality_state, CITY_VITALITY_DORMANT_GRACE_SECS,
        )
        # Stayed below for 13 days → still 'reduced', below_since preserved
        below = 1000.0
        now = below + CITY_VITALITY_DORMANT_GRACE_SECS - 86400
        state, since = compute_vitality_state(
            active_count=2, threshold=3, below_since=below, now=now)
        self.assertEqual(state, "reduced")
        self.assertEqual(since, below)

    def test_below_threshold_exactly_14d_transitions_to_dormant(self):
        from engine.player_cities import (
            compute_vitality_state, CITY_VITALITY_DORMANT_GRACE_SECS,
        )
        below = 1000.0
        now = below + CITY_VITALITY_DORMANT_GRACE_SECS
        state, since = compute_vitality_state(
            active_count=2, threshold=3, below_since=below, now=now)
        self.assertEqual(state, "dormant")
        # below_since preserved so re-entries keep their full history
        self.assertEqual(since, below)

    def test_below_threshold_past_14d_remains_dormant(self):
        from engine.player_cities import (
            compute_vitality_state, CITY_VITALITY_DORMANT_GRACE_SECS,
        )
        below = 1000.0
        now = below + CITY_VITALITY_DORMANT_GRACE_SECS + 100_000
        state, since = compute_vitality_state(
            active_count=0, threshold=3, below_since=below, now=now)
        self.assertEqual(state, "dormant")
        self.assertEqual(since, below)


# ──────────────────────────────────────────────────────────────────────
# 3. TestEffectiveTaxRateCap (pure rule)
# ──────────────────────────────────────────────────────────────────────

class TestEffectiveTaxRateCap(unittest.TestCase):
    def test_active_returns_base_cap(self):
        from engine.player_cities import effective_tax_rate_cap
        city = {"rate_cap": 0.10, "vitality_state": "active"}
        self.assertAlmostEqual(effective_tax_rate_cap(city), 0.10)

    def test_reduced_halves_base_cap(self):
        from engine.player_cities import effective_tax_rate_cap
        city = {"rate_cap": 0.10, "vitality_state": "reduced"}
        self.assertAlmostEqual(effective_tax_rate_cap(city), 0.05)

    def test_dormant_halves_base_cap(self):
        from engine.player_cities import effective_tax_rate_cap
        city = {"rate_cap": 0.08, "vitality_state": "dormant"}
        self.assertAlmostEqual(effective_tax_rate_cap(city), 0.04)

    def test_missing_rate_cap_defaults_to_10pct(self):
        from engine.player_cities import effective_tax_rate_cap
        city = {"vitality_state": "active"}
        self.assertAlmostEqual(effective_tax_rate_cap(city), 0.10)

    def test_missing_vitality_state_defaults_to_active(self):
        from engine.player_cities import effective_tax_rate_cap
        city = {"rate_cap": 0.10}
        self.assertAlmostEqual(effective_tax_rate_cap(city), 0.10)


# ──────────────────────────────────────────────────────────────────────
# 4. TestCountActiveCitizens (DB-touching counter)
# ──────────────────────────────────────────────────────────────────────

class TestCountActiveCitizens(unittest.TestCase):
    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_city(city_id=1, name="Citadel", org_id=1)

    def test_no_members(self):
        from engine.player_cities import count_active_citizens
        self.assertEqual(_run(count_active_citizens(self.mdb, 1)), 0)

    def test_one_active_member(self):
        from engine.player_cities import count_active_citizens
        self.mdb.seed_char(char_id=10, last_login=time.time())
        self.mdb.seed_membership(char_id=10, org_id=1)
        self.assertEqual(_run(count_active_citizens(self.mdb, 1)), 1)

    def test_old_login_excluded(self):
        """A member whose last_login is older than 7 days doesn't
        count as active."""
        from engine.player_cities import (
            count_active_citizens, CITY_VITALITY_ACTIVE_WINDOW_SECS,
        )
        stale_login = time.time() - CITY_VITALITY_ACTIVE_WINDOW_SECS - 10
        self.mdb.seed_char(char_id=10, last_login=stale_login)
        self.mdb.seed_membership(char_id=10, org_id=1)
        self.assertEqual(_run(count_active_citizens(self.mdb, 1)), 0)

    def test_mixed_active_and_inactive(self):
        from engine.player_cities import (
            count_active_citizens, CITY_VITALITY_ACTIVE_WINDOW_SECS,
        )
        now = time.time()
        for cid in (10, 11, 12):  # active
            self.mdb.seed_char(char_id=cid, last_login=now)
            self.mdb.seed_membership(char_id=cid, org_id=1)
        for cid in (20, 21):  # inactive
            self.mdb.seed_char(
                char_id=cid,
                last_login=now - CITY_VITALITY_ACTIVE_WINDOW_SECS - 10)
            self.mdb.seed_membership(char_id=cid, org_id=1)
        self.assertEqual(_run(count_active_citizens(self.mdb, 1)), 3)

    def test_missing_last_login_treated_as_zero(self):
        """Characters with no last_login still count via COALESCE(0)
        but always fail the active-window check."""
        from engine.player_cities import count_active_citizens
        self.mdb._db._conn.execute(
            "INSERT INTO characters (id, name) VALUES (99, 'NoLogin')")
        self.mdb._db._conn.commit()
        self.mdb.seed_membership(char_id=99, org_id=1)
        self.assertEqual(_run(count_active_citizens(self.mdb, 1)), 0)

    def test_nonexistent_city_returns_zero(self):
        from engine.player_cities import count_active_citizens
        self.assertEqual(_run(count_active_citizens(self.mdb, 999)), 0)


# ──────────────────────────────────────────────────────────────────────
# 5. TestTickCityVitality (full tick path)
# ──────────────────────────────────────────────────────────────────────

class TestTickCityVitality(unittest.TestCase):
    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_org(org_id=1, code="hutt_cartel")

    def test_active_city_stays_active(self):
        from engine.player_cities import tick_city_vitality
        self.mdb.seed_city(city_id=1, name="Active", org_id=1,
                            hq_tier="outpost")
        self.mdb.seed_char(char_id=10, last_login=time.time())
        self.mdb.seed_membership(char_id=10, org_id=1)
        _run(tick_city_vitality(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT vitality_state, vitality_below_since "
            "FROM player_cities WHERE id = 1"))
        self.assertEqual(rows[0]["vitality_state"], "active")
        self.assertIsNone(rows[0]["vitality_below_since"])

    def test_drops_to_reduced_when_empty(self):
        from engine.player_cities import tick_city_vitality
        self.mdb.seed_city(city_id=1, name="Ghost", org_id=1,
                            hq_tier="outpost")
        # No active members → 0 < 1 (outpost threshold)
        _run(tick_city_vitality(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT vitality_state, vitality_below_since "
            "FROM player_cities WHERE id = 1"))
        self.assertEqual(rows[0]["vitality_state"], "reduced")
        self.assertIsNotNone(rows[0]["vitality_below_since"])

    def test_dormant_after_14_days_under(self):
        from engine.player_cities import (
            tick_city_vitality, CITY_VITALITY_DORMANT_GRACE_SECS,
        )
        # City has been below threshold for 14+ days
        old_below = time.time() - CITY_VITALITY_DORMANT_GRACE_SECS - 100
        self.mdb.seed_city(
            city_id=1, name="Forgotten", org_id=1,
            hq_tier="outpost",
            vitality_state="reduced",
            vitality_below_since=old_below)
        _run(tick_city_vitality(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT vitality_state, vitality_below_since "
            "FROM player_cities WHERE id = 1"))
        self.assertEqual(rows[0]["vitality_state"], "dormant")
        # below_since preserved
        self.assertAlmostEqual(
            rows[0]["vitality_below_since"], old_below, delta=1.0)

    def test_dormant_recovers_to_active_on_activity(self):
        from engine.player_cities import tick_city_vitality
        # Dormant city
        self.mdb.seed_city(
            city_id=1, name="Comeback", org_id=1,
            hq_tier="outpost",
            vitality_state="dormant",
            vitality_below_since=time.time() - 30 * 86400)
        # Now add an active member
        self.mdb.seed_char(char_id=10, last_login=time.time())
        self.mdb.seed_membership(char_id=10, org_id=1)
        _run(tick_city_vitality(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT vitality_state, vitality_below_since "
            "FROM player_cities WHERE id = 1"))
        self.assertEqual(rows[0]["vitality_state"], "active")
        self.assertIsNone(rows[0]["vitality_below_since"])

    def test_dissolved_cities_skipped(self):
        from engine.player_cities import tick_city_vitality
        self.mdb.seed_city(city_id=1, name="Dead", org_id=1,
                            state="dissolved")
        # No members, but the tick should not even look at it
        _run(tick_city_vitality(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT vitality_state FROM player_cities WHERE id = 1"))
        # State unchanged (still default 'active' from seed, since
        # the tick filters WHERE state = 'active')
        self.assertEqual(rows[0]["vitality_state"], "active")

    def test_chapter_house_threshold(self):
        """Chapter House needs 3+ active citizens."""
        from engine.player_cities import tick_city_vitality
        self.mdb.seed_city(
            city_id=1, name="ChapterTest", org_id=1,
            hq_tier="chapter_house")
        # 2 members — under threshold of 3
        for cid in (10, 11):
            self.mdb.seed_char(char_id=cid, last_login=time.time())
            self.mdb.seed_membership(char_id=cid, org_id=1)
        _run(tick_city_vitality(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT vitality_state FROM player_cities WHERE id = 1"))
        self.assertEqual(rows[0]["vitality_state"], "reduced")


# ──────────────────────────────────────────────────────────────────────
# 6. TestSyn4MigrationHappyPath
# ──────────────────────────────────────────────────────────────────────

class TestSyn4MigrationHappyPath(unittest.TestCase):
    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_org(org_id=1, code="hutt_cartel", treasury=0)
        self.mdb.seed_org(org_id=2, code="cis", treasury=10_000)

    def test_dissolves_city_map_city_with_75pct_refund(self):
        from engine.player_cities import (
            syn4_migrate_dissolve_city_map_cities, FOUNDING_COSTS,
        )
        # Legacy city-map city: wilderness_region_id=NULL
        self.mdb.seed_city(city_id=1, name="Old City",
                            org_id=1, hq_tier="outpost",
                            wilderness_region_id=None)
        self.mdb.seed_city_room(city_id=1, room_id=9001, is_center=1)
        self.mdb.seed_city_room(city_id=1, room_id=9002, is_center=1)
        result = _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        self.assertTrue(result["ran"])
        self.assertEqual(result["dissolved_count"], 1)
        expected_refund = int(FOUNDING_COSTS["outpost"] * 0.75)
        self.assertEqual(result["total_refunded"], expected_refund)
        # Treasury credited
        rows = _run(self.mdb.fetchall(
            "SELECT treasury FROM organizations WHERE code = 'hutt_cartel'"))
        self.assertEqual(rows[0]["treasury"], expected_refund)
        # City marked dissolved
        rows = _run(self.mdb.fetchall(
            "SELECT state FROM player_cities WHERE id = 1"))
        self.assertEqual(rows[0]["state"], "dissolved")
        # Rooms dropped
        rows = _run(self.mdb.fetchall(
            "SELECT room_id FROM player_city_rooms WHERE city_id = 1"))
        self.assertEqual(len(rows), 0)

    def test_dissolves_multiple_cities(self):
        from engine.player_cities import syn4_migrate_dissolve_city_map_cities
        self.mdb.seed_city(city_id=1, name="A", org_id=1,
                            hq_tier="outpost", wilderness_region_id=None)
        self.mdb.seed_city(city_id=2, name="B", org_id=2,
                            hq_tier="fortress", wilderness_region_id=None)
        # Different orgs so no "duplicate city per org" check
        # The legacy schema allows multiple cities per org if they were
        # founded before the unique constraint was added; we test that
        # the migration handles them all.
        result = _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        self.assertEqual(result["dissolved_count"], 2)

    def test_refund_amounts_per_tier(self):
        from engine.player_cities import (
            syn4_migrate_dissolve_city_map_cities, FOUNDING_COSTS,
        )
        self.mdb.seed_city(city_id=1, name="Outpost A", org_id=1,
                            hq_tier="outpost", wilderness_region_id=None)
        self.mdb.seed_city(city_id=2, name="Fortress B", org_id=2,
                            hq_tier="fortress", wilderness_region_id=None)
        result = _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        refunds = {c["name"]: c["refund"] for c in result["cities"]}
        self.assertEqual(refunds["Outpost A"],
                          int(FOUNDING_COSTS["outpost"] * 0.75))
        self.assertEqual(refunds["Fortress B"],
                          int(FOUNDING_COSTS["fortress"] * 0.75))

    def test_dissolution_records_grace_started_at(self):
        from engine.player_cities import syn4_migrate_dissolve_city_map_cities
        self.mdb.seed_city(city_id=1, name="X", org_id=1,
                            hq_tier="outpost", wilderness_region_id=None)
        _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        rows = _run(self.mdb.fetchall(
            "SELECT state, grace_started_at FROM player_cities "
            "WHERE id = 1"))
        self.assertEqual(rows[0]["state"], "dissolved")
        # grace_started_at set to now (within the last few seconds)
        self.assertGreater(rows[0]["grace_started_at"], time.time() - 10)


# ──────────────────────────────────────────────────────────────────────
# 7. TestSyn4MigrationIdempotency
# ──────────────────────────────────────────────────────────────────────

class TestSyn4MigrationIdempotency(unittest.TestCase):
    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_org(org_id=1, code="hutt_cartel", treasury=0)
        self.mdb.seed_city(city_id=1, name="Old", org_id=1,
                            hq_tier="outpost", wilderness_region_id=None)

    def test_second_run_is_noop(self):
        from engine.player_cities import syn4_migrate_dissolve_city_map_cities
        first = _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        self.assertTrue(first["ran"])
        # Second run sees the marker; no work to do
        second = _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        self.assertFalse(second["ran"])
        self.assertEqual(second["dissolved_count"], 0)

    def test_marker_recorded_after_run(self):
        from engine.player_cities import (
            syn4_migrate_dissolve_city_map_cities, SYN4_MIGRATION_KEY,
        )
        _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        rows = _run(self.mdb.fetchall(
            "SELECT value FROM syn_migration_state WHERE key = ?",
            (SYN4_MIGRATION_KEY,)))
        self.assertEqual(len(rows), 1)
        self.assertIn("cities_dissolved", rows[0]["value"])

    def test_treasury_not_double_credited(self):
        from engine.player_cities import syn4_migrate_dissolve_city_map_cities
        _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        rows1 = _run(self.mdb.fetchall(
            "SELECT treasury FROM organizations WHERE code = 'hutt_cartel'"))
        first_balance = rows1[0]["treasury"]
        _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        rows2 = _run(self.mdb.fetchall(
            "SELECT treasury FROM organizations WHERE code = 'hutt_cartel'"))
        self.assertEqual(rows2[0]["treasury"], first_balance)


# ──────────────────────────────────────────────────────────────────────
# 8. TestSyn4MigrationScope
# ──────────────────────────────────────────────────────────────────────

class TestSyn4MigrationScope(unittest.TestCase):
    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_org(org_id=1, code="hutt_cartel", treasury=0)
        self.mdb.seed_org(org_id=2, code="cis", treasury=0)

    def test_skips_wilderness_anchored_cities(self):
        from engine.player_cities import syn4_migrate_dissolve_city_map_cities
        # Region-anchored city: should NOT be dissolved
        self.mdb.seed_city(city_id=1, name="Modern", org_id=1,
                            hq_tier="outpost",
                            wilderness_region_id="dune_sea")
        # Legacy city: should be dissolved
        self.mdb.seed_city(city_id=2, name="Legacy", org_id=2,
                            hq_tier="outpost",
                            wilderness_region_id=None)
        result = _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        self.assertEqual(result["dissolved_count"], 1)
        # Modern city unchanged
        rows = _run(self.mdb.fetchall(
            "SELECT state FROM player_cities WHERE id = 1"))
        self.assertEqual(rows[0]["state"], "active")
        # Legacy city dissolved
        rows = _run(self.mdb.fetchall(
            "SELECT state FROM player_cities WHERE id = 2"))
        self.assertEqual(rows[0]["state"], "dissolved")

    def test_skips_already_dissolved_cities(self):
        from engine.player_cities import syn4_migrate_dissolve_city_map_cities
        self.mdb.seed_city(city_id=1, name="AlreadyGone", org_id=1,
                            hq_tier="outpost",
                            wilderness_region_id=None,
                            state="dissolved")
        result = _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        self.assertEqual(result["dissolved_count"], 0)

    def test_skips_empty_string_region_id(self):
        """Some legacy fixtures may have '' instead of NULL for
        wilderness_region_id. The migration treats both as 'no
        wilderness anchor' and dissolves them."""
        from engine.player_cities import syn4_migrate_dissolve_city_map_cities
        self.mdb.seed_city(city_id=1, name="EmptyString", org_id=1,
                            hq_tier="outpost",
                            wilderness_region_id="")
        result = _run(syn4_migrate_dissolve_city_map_cities(self.mdb))
        self.assertEqual(result["dissolved_count"], 1)


if __name__ == "__main__":
    unittest.main()
