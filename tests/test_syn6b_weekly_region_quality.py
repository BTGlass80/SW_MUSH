# -*- coding: utf-8 -*-
"""
tests/test_syn6b_weekly_region_quality.py — SYN.6.b (2026-05-25).

Pins:
  * engine/region_quality.py (new) — pure helpers (_iso_year_week,
    _compute_weekly_multiplier, _outlook_summary), the DB-touching
    roll_region_quality / get_region_quality_for / get_outlook, and
    the idempotent weekly tick.
  * engine/harvest.py — compute_harvest_payout per-type-dict
    consumption (SYN.6.a back-compat with float still works).
  * parser/faction_commands.py — `faction resource_outlook`
    subcommand (smoke; full UI test deferred — protocol-shape tests
    only here).

Test sections
─────────────
  1. TestIsoYearWeek                   — Monday anchor, ISO format
  2. TestComputeWeeklyMultiplier       — range, rounding, RNG determinism
  3. TestOutlookSummary                — best/worst, tie-breaking
  4. TestSchemaBootstrap               — ensure_region_quality_schema
                                          idempotent + creates table
  5. TestRollRegionQuality             — fresh roll, idempotence within
                                          week, fresh roll next week,
                                          all RESOURCE_TYPES covered
  6. TestGetRegionQualityFor           — baseline before roll, post-roll
                                          values, missing-table fail-soft
  7. TestTickWeeklyRegionQuality       — iterates rooms, idempotent on
                                          re-run, count of rolled regions
  8. TestHarvestPayoutDictQuality      — per-type quality applied to
                                          per-type stacks (the core
                                          payoff)
  9. TestGetOutlook                    — unfiltered + org-filtered
 10. TestHarvestSeamWired               — _get_region_quality returns
                                          actual rolled values when
                                          table is populated
"""
from __future__ import annotations

import asyncio
import datetime
import json
import random
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
# In-memory DB stand-in (mirrors SYN.6.a pattern; adds region_quality
# bootstrap, since ensure_region_quality_schema() creates the table
# itself, the MiniDB just needs the supporting tables.)
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
            CREATE TABLE region_ownership (
                region_slug   TEXT    NOT NULL PRIMARY KEY,
                org_code      TEXT    NOT NULL,
                zone_id       INTEGER,
                claimed_by    INTEGER NOT NULL,
                claimed_at    REAL    NOT NULL,
                maintenance   INTEGER NOT NULL DEFAULT 3000
            );
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                attributes TEXT DEFAULT '{}',
                credits INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '{}'
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
        self.treasury_log: list[tuple[int, int]] = []

    # passthrough
    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

    # ORM
    async def get_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (room_id,))
        return dict(rows[0]) if rows else None

    async def get_organization(self, org_code):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM organizations WHERE code = ?", (org_code,))
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

    async def adjust_org_treasury(self, org_id, delta):
        self.treasury_log.append((org_id, delta))
        self._db._conn.execute(
            "UPDATE organizations SET treasury = treasury + ? "
            "WHERE id = ?",
            (delta, org_id))
        self._db._conn.commit()
        rows = self._db._conn.execute(
            "SELECT treasury FROM organizations WHERE id = ?",
            (org_id,)).fetchall()
        return int(rows[0]["treasury"]) if rows else 0

    # Seeds
    def seed_zone(self, *, zone_id=1, name="Tatooine",
                   security="lawless"):
        props = json.dumps({"security": security})
        self._db._conn.execute(
            "INSERT INTO zones (id, name, properties) "
            "VALUES (?, ?, ?)", (zone_id, name, props))
        self._db._conn.commit()

    def seed_room(self, *, room_id, zone_id=None,
                   wilderness_region_id=None, name="Room"):
        self._db._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, "
            "wilderness_region_id) VALUES (?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id))
        self._db._conn.commit()

    def seed_org(self, *, org_id, code, treasury=0):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name, treasury) "
            "VALUES (?, ?, ?, ?)",
            (org_id, code, code.title(), treasury))
        self._db._conn.commit()

    def seed_region_ownership(self, *, region_slug, org_code, zone_id):
        self._db._conn.execute(
            "INSERT INTO region_ownership (region_slug, org_code, "
            "zone_id, claimed_by, claimed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (region_slug, org_code, zone_id, 1, 0.0))
        self._db._conn.commit()

    def seed_character(self, *, char_id, credits=0, attributes=None,
                       inventory=None):
        if attributes is None:
            attributes = {}
        if inventory is None:
            inventory = {}
        self._db._conn.execute(
            "INSERT INTO characters (id, name, attributes, credits, "
            "inventory) VALUES (?, ?, ?, ?, ?)",
            (char_id, f"Char{char_id}",
             json.dumps(attributes), credits, json.dumps(inventory)))
        self._db._conn.commit()


# Reference timestamps for deterministic ISO year-week math.
# 2026-05-25 is a Monday → week 22 of 2026.
# 2026-05-31 is a Sunday (same week 22).
# 2026-06-01 is a Monday → week 23 of 2026.
TS_MON_W22 = datetime.datetime(2026, 5, 25, 12, 0, 0,
                                tzinfo=datetime.timezone.utc).timestamp()
TS_SUN_W22 = datetime.datetime(2026, 5, 31, 23, 0, 0,
                                tzinfo=datetime.timezone.utc).timestamp()
TS_MON_W23 = datetime.datetime(2026, 6, 1, 0, 30, 0,
                                tzinfo=datetime.timezone.utc).timestamp()


# ──────────────────────────────────────────────────────────────────────
# 1. TestIsoYearWeek
# ──────────────────────────────────────────────────────────────────────

class TestIsoYearWeek(unittest.TestCase):
    """ISO 8601 year-week format + Monday anchor."""

    def test_known_monday(self):
        from engine.region_quality import _iso_year_week
        # 2026-05-25 is Monday week 22 of 2026
        self.assertEqual(_iso_year_week(TS_MON_W22), "2026-W22")

    def test_known_sunday_same_week(self):
        """Sunday is still in the previous week's ISO key."""
        from engine.region_quality import _iso_year_week
        # 2026-05-31 (Sunday) — same ISO week as the prior Monday
        self.assertEqual(_iso_year_week(TS_SUN_W22), "2026-W22")

    def test_next_monday_new_week(self):
        from engine.region_quality import _iso_year_week
        self.assertEqual(_iso_year_week(TS_MON_W23), "2026-W23")

    def test_format_is_yyyy_w_ww(self):
        from engine.region_quality import _iso_year_week
        key = _iso_year_week(TS_MON_W22)
        self.assertRegex(key, r"^\d{4}-W\d{2}$")

    def test_default_uses_current_time(self):
        from engine.region_quality import _iso_year_week
        # Just shape-check; calling without args should still return
        # a well-formed key.
        key = _iso_year_week()
        self.assertRegex(key, r"^\d{4}-W\d{2}$")


# ──────────────────────────────────────────────────────────────────────
# 2. TestComputeWeeklyMultiplier
# ──────────────────────────────────────────────────────────────────────

class TestComputeWeeklyMultiplier(unittest.TestCase):
    """Multiplier sample is in [0.7, 1.3], rounded to 2 decimals."""

    def test_in_range(self):
        from engine.region_quality import (
            _compute_weekly_multiplier, QUALITY_MIN, QUALITY_MAX,
        )
        rng = random.Random(0)
        for _ in range(200):
            m = _compute_weekly_multiplier(rng)
            self.assertGreaterEqual(m, QUALITY_MIN)
            self.assertLessEqual(m, QUALITY_MAX)

    def test_rounded_two_decimals(self):
        from engine.region_quality import _compute_weekly_multiplier
        rng = random.Random(0)
        for _ in range(50):
            m = _compute_weekly_multiplier(rng)
            # round(x, 2) means x*100 is an integer (within float
            # tolerance)
            scaled = m * 100
            self.assertAlmostEqual(scaled, round(scaled), places=6)

    def test_deterministic_with_seeded_rng(self):
        from engine.region_quality import _compute_weekly_multiplier
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        for _ in range(20):
            self.assertEqual(
                _compute_weekly_multiplier(rng1),
                _compute_weekly_multiplier(rng2),
            )

    def test_distribution_covers_band(self):
        """200 samples should span at least the central 60% of the
        band (defensive against an off-by-one in the range)."""
        from engine.region_quality import _compute_weekly_multiplier
        rng = random.Random(0)
        samples = [_compute_weekly_multiplier(rng) for _ in range(200)]
        self.assertLess(min(samples), 0.85)   # saw a low value
        self.assertGreater(max(samples), 1.15)  # saw a high value


# ──────────────────────────────────────────────────────────────────────
# 3. TestOutlookSummary
# ──────────────────────────────────────────────────────────────────────

class TestOutlookSummary(unittest.TestCase):
    """Per-region best/worst extraction with stable tie-breaking."""

    def test_single_region_one_type(self):
        from engine.region_quality import _outlook_summary
        rows = [{"region_slug": "r1", "resource_type": "metal",
                 "quality_multiplier": 1.2}]
        s = _outlook_summary(rows)
        self.assertEqual(s["r1"]["best"], ("metal", 1.2))
        self.assertEqual(s["r1"]["worst"], ("metal", 1.2))

    def test_multiple_types_in_region(self):
        from engine.region_quality import _outlook_summary
        rows = [
            {"region_slug": "r1", "resource_type": "metal",
             "quality_multiplier": 1.3},
            {"region_slug": "r1", "resource_type": "chemical",
             "quality_multiplier": 0.8},
            {"region_slug": "r1", "resource_type": "organic",
             "quality_multiplier": 1.0},
        ]
        s = _outlook_summary(rows)
        self.assertEqual(s["r1"]["best"], ("metal", 1.3))
        self.assertEqual(s["r1"]["worst"], ("chemical", 0.8))

    def test_multiple_regions(self):
        from engine.region_quality import _outlook_summary
        rows = [
            {"region_slug": "r1", "resource_type": "metal",
             "quality_multiplier": 1.3},
            {"region_slug": "r2", "resource_type": "rare",
             "quality_multiplier": 0.9},
        ]
        s = _outlook_summary(rows)
        self.assertIn("r1", s)
        self.assertIn("r2", s)

    def test_tie_broken_alphabetically(self):
        """When two types have equal multiplier, the alphabetically
        earlier type wins 'worst' and the later wins 'best'."""
        from engine.region_quality import _outlook_summary
        rows = [
            {"region_slug": "r1", "resource_type": "chemical",
             "quality_multiplier": 1.0},
            {"region_slug": "r1", "resource_type": "metal",
             "quality_multiplier": 1.0},
        ]
        s = _outlook_summary(rows)
        # Both tie at 1.0; alphabetical sort puts chemical first
        # (worst), metal last (best)
        self.assertEqual(s["r1"]["worst"], ("chemical", 1.0))
        self.assertEqual(s["r1"]["best"], ("metal", 1.0))

    def test_all_field_contains_full_map(self):
        from engine.region_quality import _outlook_summary
        rows = [
            {"region_slug": "r1", "resource_type": "metal",
             "quality_multiplier": 1.3},
            {"region_slug": "r1", "resource_type": "chemical",
             "quality_multiplier": 0.8},
        ]
        s = _outlook_summary(rows)
        self.assertEqual(s["r1"]["all"], {"metal": 1.3, "chemical": 0.8})

    def test_empty_rows_empty_output(self):
        from engine.region_quality import _outlook_summary
        self.assertEqual(_outlook_summary([]), {})


# ──────────────────────────────────────────────────────────────────────
# 4. TestSchemaBootstrap
# ──────────────────────────────────────────────────────────────────────

class TestSchemaBootstrap(unittest.TestCase):
    """ensure_region_quality_schema creates the table idempotently."""

    def test_creates_table(self):
        from engine.region_quality import ensure_region_quality_schema
        mdb = _MiniDB()
        _run(ensure_region_quality_schema(mdb))
        rows = mdb._db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='region_quality'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_idempotent(self):
        from engine.region_quality import ensure_region_quality_schema
        mdb = _MiniDB()
        _run(ensure_region_quality_schema(mdb))
        # Second call should not raise nor duplicate
        _run(ensure_region_quality_schema(mdb))
        rows = mdb._db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='region_quality'"
        ).fetchall()
        self.assertEqual(len(rows), 1)


# ──────────────────────────────────────────────────────────────────────
# 5. TestRollRegionQuality
# ──────────────────────────────────────────────────────────────────────

class TestRollRegionQuality(unittest.TestCase):
    """Fresh roll, idempotence within a week, new roll next week."""

    def _bootstrap(self):
        from engine.region_quality import ensure_region_quality_schema
        mdb = _MiniDB()
        _run(ensure_region_quality_schema(mdb))
        return mdb

    def test_fresh_roll_writes_all_resource_types(self):
        from engine.region_quality import roll_region_quality
        from engine.crafting import HARVESTABLE_RESOURCE_TYPES as RESOURCE_TYPES
        mdb = self._bootstrap()
        rng = random.Random(1)
        result = _run(roll_region_quality(
            mdb, "tatooine_dune_sea",
            rng=rng, now=TS_MON_W22,
        ))
        self.assertEqual(set(result.keys()), set(RESOURCE_TYPES))
        # All in range
        for v in result.values():
            self.assertGreaterEqual(v, 0.7)
            self.assertLessEqual(v, 1.3)

    def test_idempotent_in_same_week(self):
        """A second call in the same ISO week returns the same values
        and doesn't rewrite."""
        from engine.region_quality import roll_region_quality
        mdb = self._bootstrap()
        first = _run(roll_region_quality(
            mdb, "r1", rng=random.Random(1), now=TS_MON_W22,
        ))
        # A second call later the same week — RNG is different but
        # the function should NOT re-roll
        second = _run(roll_region_quality(
            mdb, "r1", rng=random.Random(99999), now=TS_SUN_W22,
        ))
        self.assertEqual(first, second)

    def test_new_week_re_rolls(self):
        """Across a week boundary, the roll changes."""
        from engine.region_quality import roll_region_quality
        mdb = self._bootstrap()
        first = _run(roll_region_quality(
            mdb, "r1", rng=random.Random(1), now=TS_MON_W22,
        ))
        # Next ISO week — fresh roll
        second = _run(roll_region_quality(
            mdb, "r1", rng=random.Random(2), now=TS_MON_W23,
        ))
        # Different RNG seeds + different week → different values
        self.assertNotEqual(first, second)

    def test_partial_existing_data_completes_roll(self):
        """If some types already have a fresh-week roll but not all,
        the missing ones get rolled and the existing ones keep their
        values."""
        from engine.region_quality import (
            roll_region_quality, _iso_year_week,
        )
        from engine.crafting import HARVESTABLE_RESOURCE_TYPES as RESOURCE_TYPES
        mdb = self._bootstrap()
        # Pre-seed one resource type for this week
        mdb._db._conn.execute(
            "INSERT INTO region_quality "
            "(region_slug, resource_type, quality_multiplier, "
            " rolled_at, roll_year_week) VALUES (?, ?, ?, ?, ?)",
            ("r1", "metal", 1.29, TS_MON_W22,
             _iso_year_week(TS_MON_W22)),
        )
        mdb._db._conn.commit()
        result = _run(roll_region_quality(
            mdb, "r1", rng=random.Random(42), now=TS_MON_W22,
        ))
        # metal preserved
        self.assertEqual(result["metal"], 1.29)
        # other types rolled
        for rtype in RESOURCE_TYPES:
            if rtype == "metal":
                continue
            self.assertGreaterEqual(result[rtype], 0.7)
            self.assertLessEqual(result[rtype], 1.3)


# ──────────────────────────────────────────────────────────────────────
# 6. TestGetRegionQualityFor
# ──────────────────────────────────────────────────────────────────────

class TestGetRegionQualityFor(unittest.TestCase):
    """Per-type quality lookup; fail-soft to baseline."""

    def test_baseline_before_any_roll(self):
        from engine.region_quality import (
            get_region_quality_for, ensure_region_quality_schema,
        )
        from engine.crafting import HARVESTABLE_RESOURCE_TYPES as RESOURCE_TYPES
        mdb = _MiniDB()
        _run(ensure_region_quality_schema(mdb))
        q = _run(get_region_quality_for(mdb, "never_rolled"))
        self.assertEqual(set(q.keys()), set(RESOURCE_TYPES))
        for v in q.values():
            self.assertEqual(v, 1.0)

    def test_post_roll_values(self):
        from engine.region_quality import (
            roll_region_quality, get_region_quality_for,
            ensure_region_quality_schema,
        )
        mdb = _MiniDB()
        _run(ensure_region_quality_schema(mdb))
        rolled = _run(roll_region_quality(
            mdb, "r1", rng=random.Random(1), now=TS_MON_W22,
        ))
        fetched = _run(get_region_quality_for(mdb, "r1"))
        # Every rolled value present in fetched
        for k, v in rolled.items():
            self.assertEqual(fetched[k], v)

    def test_missing_table_falls_back_to_baseline(self):
        """Without ensure_region_quality_schema being called, the
        lookup should still return a baseline dict (fail-soft)."""
        from engine.region_quality import get_region_quality_for
        from engine.crafting import HARVESTABLE_RESOURCE_TYPES as RESOURCE_TYPES
        mdb = _MiniDB()  # no schema bootstrap
        q = _run(get_region_quality_for(mdb, "any"))
        self.assertEqual(set(q.keys()), set(RESOURCE_TYPES))
        for v in q.values():
            self.assertEqual(v, 1.0)


# ──────────────────────────────────────────────────────────────────────
# 7. TestTickWeeklyRegionQuality
# ──────────────────────────────────────────────────────────────────────

class TestTickWeeklyRegionQuality(unittest.TestCase):
    """Weekly tick iterates rooms, idempotent on re-run within week."""

    def test_rolls_all_distinct_regions(self):
        from engine.region_quality import tick_weekly_region_quality
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1, name="Tatooine")
        mdb.seed_room(room_id=10, zone_id=1,
                       wilderness_region_id="tatooine_dune_sea")
        mdb.seed_room(room_id=11, zone_id=1,
                       wilderness_region_id="tatooine_dune_sea")  # dup
        mdb.seed_room(room_id=20, zone_id=1,
                       wilderness_region_id="tatooine_jundland")
        rolled_count = _run(tick_weekly_region_quality(
            mdb, None, now=TS_MON_W22,
        ))
        # Two distinct regions rolled; the duplicate room doesn't
        # cause a double-roll.
        self.assertEqual(rolled_count, 2)

    def test_idempotent_within_same_week(self):
        from engine.region_quality import tick_weekly_region_quality
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                       wilderness_region_id="r1")
        first = _run(tick_weekly_region_quality(
            mdb, None, now=TS_MON_W22,
        ))
        second = _run(tick_weekly_region_quality(
            mdb, None, now=TS_SUN_W22,
        ))
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)

    def test_rolls_again_next_week(self):
        from engine.region_quality import tick_weekly_region_quality
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                       wilderness_region_id="r1")
        first = _run(tick_weekly_region_quality(
            mdb, None, now=TS_MON_W22,
        ))
        second = _run(tick_weekly_region_quality(
            mdb, None, now=TS_MON_W23,
        ))
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)

    def test_no_wilderness_rooms_no_op(self):
        from engine.region_quality import tick_weekly_region_quality
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        # Only city-map rooms (wilderness_region_id = NULL)
        mdb.seed_room(room_id=10, zone_id=1,
                       wilderness_region_id=None)
        result = _run(tick_weekly_region_quality(
            mdb, None, now=TS_MON_W22,
        ))
        self.assertEqual(result, 0)


# ──────────────────────────────────────────────────────────────────────
# 8. TestHarvestPayoutDictQuality
# ──────────────────────────────────────────────────────────────────────

class TestHarvestPayoutDictQuality(unittest.TestCase):
    """compute_harvest_payout applies per-type quality dict correctly."""

    def test_dict_quality_per_type(self):
        """Different multipliers per resource type yield different
        stack qualities per stack."""
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="dominant",  # 3 metal + 2 chemical + 1 rare
            margin=0,
            quality={"metal": 1.3, "chemical": 0.8, "rare": 1.0},
            is_owner_member=True,
            rng=random.Random(0),
        )
        # 3 stacks, each at a different quality:
        # metal 1.3× → q65; chemical 0.8× → q40; rare 1.0× → q50
        stacks_by_type = {s["type"]: s for s in out["resource_stacks"]}
        self.assertEqual(stacks_by_type["metal"]["quality"], 65.0)
        self.assertEqual(stacks_by_type["chemical"]["quality"], 40.0)
        self.assertEqual(stacks_by_type["rare"]["quality"], 50.0)

    def test_dict_quality_missing_type_defaults_to_one(self):
        """A dict missing a type the yield template needs falls back
        to 1.0× for that type (no KeyError)."""
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="dominant",
            margin=0,
            quality={"metal": 1.3},  # missing chemical, rare
            is_owner_member=True,
            rng=random.Random(0),
        )
        stacks_by_type = {s["type"]: s for s in out["resource_stacks"]}
        self.assertEqual(stacks_by_type["metal"]["quality"], 65.0)
        self.assertEqual(stacks_by_type["chemical"]["quality"], 50.0)
        self.assertEqual(stacks_by_type["rare"]["quality"], 50.0)

    def test_float_quality_backcompat(self):
        """SYN.6.a behavior: a float quality applies uniformly to
        every stack."""
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="dominant",
            margin=0,
            quality=1.3,
            is_owner_member=True,
            rng=random.Random(0),
        )
        for s in out["resource_stacks"]:
            self.assertEqual(s["quality"], 65.0)

    def test_stack_qualities_dict_in_result(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",  # 2 metal + 1 chemical
            margin=0,
            quality={"metal": 1.2, "chemical": 0.9},
            is_owner_member=True,
            rng=random.Random(0),
        )
        self.assertIn("stack_qualities", out)
        self.assertEqual(out["stack_qualities"]["metal"], 60.0)
        self.assertEqual(out["stack_qualities"]["chemical"], 45.0)

    def test_legacy_stack_quality_is_mean_for_dict(self):
        """The legacy single stack_quality field becomes the mean of
        per-type qualities for display purposes."""
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=0,
            quality={"metal": 1.2, "chemical": 0.8},  # 60, 40 → mean 50
            is_owner_member=True,
            rng=random.Random(0),
        )
        self.assertEqual(out["stack_quality"], 50.0)


# ──────────────────────────────────────────────────────────────────────
# 9. TestGetOutlook
# ──────────────────────────────────────────────────────────────────────

class TestGetOutlook(unittest.TestCase):
    """Outlook digest, unfiltered + org-filtered."""

    def _setup(self):
        from engine.region_quality import (
            ensure_region_quality_schema, roll_region_quality,
        )
        mdb = _MiniDB()
        _run(ensure_region_quality_schema(mdb))
        mdb.seed_org(org_id=100, code="hutts")
        mdb.seed_org(org_id=101, code="cis")
        mdb.seed_region_ownership(
            region_slug="r1", org_code="hutts", zone_id=1,
        )
        mdb.seed_region_ownership(
            region_slug="r2", org_code="cis", zone_id=1,
        )
        _run(roll_region_quality(
            mdb, "r1", rng=random.Random(1), now=TS_MON_W22,
        ))
        _run(roll_region_quality(
            mdb, "r2", rng=random.Random(2), now=TS_MON_W22,
        ))
        return mdb

    def test_unfiltered_returns_all_regions(self):
        from engine.region_quality import get_outlook
        mdb = self._setup()
        out = _run(get_outlook(mdb, None))
        self.assertIn("r1", out)
        self.assertIn("r2", out)

    def test_org_filtered_returns_only_owned(self):
        from engine.region_quality import get_outlook
        mdb = self._setup()
        out = _run(get_outlook(mdb, "hutts"))
        self.assertIn("r1", out)
        self.assertNotIn("r2", out)

    def test_filter_for_unknown_org_returns_empty(self):
        from engine.region_quality import get_outlook
        mdb = self._setup()
        out = _run(get_outlook(mdb, "nonexistent"))
        self.assertEqual(out, {})


# ──────────────────────────────────────────────────────────────────────
# 10. TestHarvestSeamWired
# ──────────────────────────────────────────────────────────────────────

class TestHarvestSeamWired(unittest.TestCase):
    """engine.harvest._get_region_quality now reads from the
    region_quality table when present."""

    def test_returns_per_type_dict_after_roll(self):
        from engine.harvest import _get_region_quality
        from engine.region_quality import (
            ensure_region_quality_schema, roll_region_quality,
        )
        from engine.crafting import HARVESTABLE_RESOURCE_TYPES as RESOURCE_TYPES
        mdb = _MiniDB()
        _run(ensure_region_quality_schema(mdb))
        _run(roll_region_quality(
            mdb, "r1", rng=random.Random(1), now=TS_MON_W22,
        ))
        q = _run(_get_region_quality(mdb, "r1"))
        # Dict, full RESOURCE_TYPES coverage, all in range
        self.assertIsInstance(q, dict)
        self.assertEqual(set(q.keys()), set(RESOURCE_TYPES))
        for v in q.values():
            self.assertGreaterEqual(v, 0.7)
            self.assertLessEqual(v, 1.3)

    def test_returns_baseline_dict_before_roll(self):
        """A region with no rolls returns the all-baseline dict."""
        from engine.harvest import _get_region_quality
        mdb = _MiniDB()
        q = _run(_get_region_quality(mdb, "never_rolled"))
        # Without schema bootstrap, fail-soft to baseline dict.
        self.assertIsInstance(q, dict)
        for v in q.values():
            self.assertEqual(v, 1.0)


if __name__ == "__main__":
    unittest.main()
