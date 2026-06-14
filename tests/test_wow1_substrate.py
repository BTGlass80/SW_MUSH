# -*- coding: utf-8 -*-
"""
tests/test_wow1_substrate.py — Weight of War Drop 1 substrate.

Per weight_of_war_design_v1.md §4 (accrual triggers + caps), §5
(decay), §6 (narrative tiers + descriptors), §7.1 + §7.2
(mechanical modifiers), §8 (schema), §14 (admin-override
acceptance criterion).

Drop 1 ships the substrate: schema migration v35 + the engine
module engine/weight_of_war.py. No combat hooks, no commands, no
tick handler, no integration. This test file pins the substrate's
contract so subsequent drops (commands in Drop 2, hooks in Drop 3)
can wire against a stable surface.

Test sections
=============

Schema (db/database.py):
   1. TestSchemaVersionBumped         — SCHEMA_VERSION == 35
   2. TestMigrationV35Present         — MIGRATIONS[35] exists with
                                        the expected statement count
   3. TestMigrationV35AppliesCleanly  — Apply v35 to a fresh DB;
                                        columns + table + index land
   4. TestMigrationV35Idempotent      — Re-applying the column adds
                                        raises "duplicate column", not
                                        a different error (the boot
                                        path catches and skips)
   5. TestAllowlistContainsWOWColumns — _CHARACTER_WRITABLE_COLUMNS
                                        contains all three columns

Engine constants + tier mapping (engine/weight_of_war.py):
   6. TestRangeConstants              — WEIGHT_MIN/MAX/etc. match
                                        design §4.4
   7. TestWeightTiersContiguous       — WEIGHT_TIERS covers
                                        [0, WEIGHT_MAX] with no gaps
                                        or overlaps
   8. TestGetTier                     — boundary values at 0/20/21/
                                        50/51/100/101/150/151/200
                                        per design §6
   9. TestGetDescriptor               — descriptors match design §6
                                        table
  10. TestClampingPublicSurface       — out-of-range values clamp
                                        rather than raise (callers'
                                        confidence)

Mechanical modifiers (design §7.1 + §7.2):
  11. TestDspResistanceModifier       — 0/+2/+5/+10 by tier
  12. TestExtraDspOnFailedResist      — 1 at Weight ≥ 151, 0 below
  13. TestFpAwardMultiplier           — 1.00/0.75/0.50/0.25 by tier
  14. TestFpAwardAfterWeight          — multiplier × base + floor of 1

Char-dict reads:
  15. TestGetWeightDefensive          — missing column → 0; non-int
                                        → 0; clamp into range
  16. TestConvenienceDictHelpers      — get_tier_for_char, etc.

DB reads:
  17. TestGetWeightDb                 — reads stored value; clamps
  18. TestGetEventsOrder              — most recent first; LIMIT
                                        honored
  19. TestWeeklyAccrualTotal          — sums positive deltas in
                                        window; excludes decays;
                                        excludes events older than
                                        the window

Accrual (design §4.4 caps):
  20. TestAccrueWeightHappyPath       — positive delta + log + total
  21. TestAccrueRejectsNonPositive    — delta ≤ 0 raises ValueError
  22. TestAccrueClampsSingleEvent     — +999 becomes +25
                                        (MAX_SINGLE_EVENT)
  23. TestAccrueEnforcesWeeklyCap     — once the rolling-week sum
                                        hits +40, no new event logs
  24. TestAccrueTrimsToHeadroom       — partial fit: cap at 35
                                        already, +10 trigger →
                                        applies +5 only
  25. TestAccrueRespectsHardCap       — at 199, +25 trigger lands
                                        +1 to reach 200
  26. TestAccrueAtHardCapNoOp         — at 200, any trigger is a
                                        silent no-op (returns 0,
                                        no event log)
  27. TestAccrueStampsLastAccrualAt   — weight_last_accrual_at
                                        updated on accrual

Decay (design §5):
  28. TestDecayWeightHappyPath        — magnitude applied; log
                                        negative
  29. TestDecayRejectsNonPositive     — magnitude ≤ 0 raises
                                        ValueError
  30. TestDecayClampsToFloor          — at 5, -10 → goes to 0,
                                        actual=5
  31. TestDecayAtFloorNoOp            — at 0, any decay is a silent
                                        no-op
  32. TestDecayStampsLastDecayAt      — weight_last_decay_at updated

Admin override (design §14):
  33. TestSetWeightAdmin              — bypasses caps; clamps;
                                        logs admin_adjust
  34. TestSetWeightAdminRequiresNote  — empty admin_note → ValueError
  35. TestSetWeightAdminNoOp          — already at target → no event
  36. TestSetWeightAdminUsesCorrectStamp — up = accrual_at;
                                        down = decay_at
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    """Run *coro* to completion in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────
# In-memory DB harness
# ─────────────────────────────────────────────────────────────────────
#
# engine/weight_of_war.py talks to a Database via three proxy methods:
#   - db.fetchone(sql, params)
#   - db.fetchall(sql, params)
#   - db.execute(sql, params)
# We provide a thin async wrapper over stdlib sqlite3, plus bootstrap
# the schema chunks our module touches (characters table with the v35
# columns, plus the events table).

class _AsyncSqlite:
    """Minimal async wrapper exposing only the proxy methods used by
    engine/weight_of_war.py."""

    def __init__(self):
        import sqlite3
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")

    async def execute(self, sql, params=()):
        self._conn.execute(sql, params)
        self._conn.commit()
        return None

    async def fetchone(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        return row  # sqlite3.Row supports [] indexing

    async def fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    # Convenience for setup
    def raw_exec(self, sql, params=()):
        self._conn.execute(sql, params)
        self._conn.commit()


def _new_db(initial_weight: int = 0, char_id: int = 1) -> "_AsyncSqlite":
    """Construct a fresh harness DB with just enough schema for our
    engine module. Mirrors the v35 migration's column/table/index
    layout exactly — including the production schema's character PK
    name (``id``, not ``char_id``). The `char_id` parameter is the
    function argument name (we keep it for caller readability), but
    it maps to the ``id`` column in the schema."""
    db = _AsyncSqlite()
    db.raw_exec("""
        CREATE TABLE characters (
            id                     INTEGER PRIMARY KEY,
            name                   TEXT,
            weight_of_war          INTEGER NOT NULL DEFAULT 0,
            weight_last_decay_at   REAL,
            weight_last_accrual_at REAL
        )
    """)
    db.raw_exec("""
        CREATE TABLE weight_of_war_events (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id        INTEGER NOT NULL,
            event_at       REAL    NOT NULL,
            delta          INTEGER NOT NULL,
            trigger_type   TEXT    NOT NULL,
            description    TEXT
        )
    """)
    db.raw_exec("CREATE INDEX idx_wow_char ON "
                "weight_of_war_events(char_id, event_at DESC)")
    db.raw_exec("INSERT INTO characters (id, name, weight_of_war) "
                "VALUES (?, ?, ?)",
                (char_id, "TestPC", initial_weight))
    return db


# ═════════════════════════════════════════════════════════════════════
# Schema tests
# ═════════════════════════════════════════════════════════════════════

class TestSchemaVersionBumped(unittest.TestCase):
    def test_schema_version_is_35(self):
        # WoW.1 introduced its migration at v35. SCHEMA_VERSION advances on
        # every later migration, so assert >= 35 rather than pinning the
        # exact value (TestMigrationV35Present below pins the v35 migration
        # itself, which is the durable guard).
        from db.database import SCHEMA_VERSION
        self.assertGreaterEqual(SCHEMA_VERSION, 35)


class TestMigrationV35Present(unittest.TestCase):
    def test_v35_key_exists(self):
        from db.database import MIGRATIONS
        self.assertIn(35, MIGRATIONS)

    def test_v35_statement_count(self):
        from db.database import MIGRATIONS
        # 3 ALTER + 1 CREATE TABLE + 1 CREATE INDEX = 5 statements
        self.assertEqual(len(MIGRATIONS[35]), 5)


@pytest.mark.slow  # heavy: migration
class TestMigrationV35AppliesCleanly(unittest.TestCase):
    """Apply migrations 2..35 to a fresh DB and verify the v35
    surface lands."""

    def _apply_all(self, db_path):
        async def run():
            import aiosqlite
            from db.database import MIGRATIONS, SCHEMA_SQL
            conn = await aiosqlite.connect(db_path)
            conn.row_factory = aiosqlite.Row
            await conn.executescript(SCHEMA_SQL)
            for v in sorted(MIGRATIONS.keys()):
                for stmt in MIGRATIONS[v]:
                    try:
                        await conn.execute(stmt)
                    except Exception as e:
                        if "duplicate column" in str(e).lower():
                            continue
                        raise
            await conn.commit()

            async with conn.execute(
                "PRAGMA table_info(characters)"
            ) as cur:
                cols = {r["name"] async for r in cur}
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cur:
                tables = {r["name"] async for r in cur}
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ) as cur:
                indexes = {r["name"] async for r in cur}

            await conn.close()
            return cols, tables, indexes

        return _run(run())

    def test_columns_table_index_present(self):
        tmp = tempfile.mktemp(suffix=".sqlite")
        try:
            cols, tables, indexes = self._apply_all(tmp)
            for col in ("weight_of_war", "weight_last_decay_at",
                        "weight_last_accrual_at"):
                self.assertIn(col, cols, f"missing column {col}")
            self.assertIn("weight_of_war_events", tables)
            self.assertIn("idx_wow_char", indexes)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


@pytest.mark.slow  # heavy: migration
class TestMigrationV35Idempotent(unittest.TestCase):
    """Re-applying v35 should fail with 'duplicate column' (a known-
    benign error the _run_migrations loop already catches), not with
    a different error."""

    def test_duplicate_column_caught(self):
        from db.database import MIGRATIONS
        stmts = MIGRATIONS[35]
        # The three ALTER statements should be the first three.
        alters = [s for s in stmts if s.lstrip().upper().startswith(
            "ALTER")]
        self.assertEqual(len(alters), 3,
                         f"Expected 3 ALTER statements, got {len(alters)}")

        async def run():
            import aiosqlite
            from db.database import MIGRATIONS, SCHEMA_SQL
            tmp = tempfile.mktemp(suffix=".sqlite")
            try:
                conn = await aiosqlite.connect(tmp)
                await conn.executescript(SCHEMA_SQL)
                for v in sorted(MIGRATIONS.keys()):
                    for stmt in MIGRATIONS[v]:
                        try:
                            await conn.execute(stmt)
                        except Exception as e:
                            if "duplicate column" in str(e).lower():
                                continue
                            raise
                # Re-run v35 ALTERs — should all hit 'duplicate column'
                hits = 0
                for stmt in alters:
                    try:
                        await conn.execute(stmt)
                    except Exception as e:
                        self.assertIn(
                            "duplicate column", str(e).lower(),
                            f"Unexpected error on re-apply: {e!r}")
                        hits += 1
                self.assertEqual(hits, 3,
                                 "All 3 ALTERs should have raised "
                                 "'duplicate column' on re-apply")
                await conn.close()
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)

        _run(run())


class TestAllowlistContainsWOWColumns(unittest.TestCase):
    def test_allowlist_has_all_three(self):
        from db.database import Database
        for col in ("weight_of_war", "weight_last_decay_at",
                    "weight_last_accrual_at"):
            self.assertIn(
                col, Database._CHARACTER_WRITABLE_COLUMNS,
                f"_CHARACTER_WRITABLE_COLUMNS missing {col!r} — "
                f"save_character() would reject writes to it.")


# ═════════════════════════════════════════════════════════════════════
# Engine constants + tier mapping
# ═════════════════════════════════════════════════════════════════════

class TestRangeConstants(unittest.TestCase):
    def test_constants_match_design(self):
        import engine.weight_of_war as wow
        self.assertEqual(wow.WEIGHT_MIN, 0)
        self.assertEqual(wow.WEIGHT_MAX, 200)
        self.assertEqual(wow.MAX_SINGLE_EVENT, 25)
        self.assertEqual(wow.WEEKLY_ACCRUAL_CAP, 40)
        self.assertEqual(wow.WEEKLY_WINDOW_SECONDS, 7 * 24 * 60 * 60)


class TestWeightTiersContiguous(unittest.TestCase):
    """Every integer in [0, WEIGHT_MAX] must map to exactly one tier
    — no gaps, no overlaps."""

    def test_coverage(self):
        import engine.weight_of_war as wow
        seen = [None] * (wow.WEIGHT_MAX + 1)
        for low, high, name, _desc in wow.WEIGHT_TIERS:
            for v in range(low, high + 1):
                self.assertIsNone(
                    seen[v],
                    f"Weight {v} matched by multiple tiers: "
                    f"{seen[v]!r} and {name!r}")
                seen[v] = name
        missing = [i for i, n in enumerate(seen) if n is None]
        self.assertFalse(missing,
                         f"Weight values without a tier: {missing[:10]}")


class TestGetTier(unittest.TestCase):
    EXPECTED = [
        (0,   "at_peace"),
        (20,  "at_peace"),
        (21,  "troubled"),
        (50,  "troubled"),
        (51,  "burdened"),
        (100, "burdened"),
        (101, "strained"),
        (150, "strained"),
        (151, "crushed"),
        (200, "crushed"),
    ]

    def test_boundaries(self):
        from engine.weight_of_war import get_tier
        for w, expected in self.EXPECTED:
            with self.subTest(weight=w):
                self.assertEqual(get_tier(w), expected)


class TestGetDescriptor(unittest.TestCase):
    def test_descriptors_match_design(self):
        from engine.weight_of_war import get_descriptor
        # Design §6 descriptor table — each value lifted verbatim.
        self.assertIn("flowing freely", get_descriptor(0))
        self.assertIn("clouded", get_descriptor(35))
        self.assertIn("hesitate before drawing", get_descriptor(75))
        self.assertIn("dying men", get_descriptor(125))
        self.assertIn("Masters have fallen", get_descriptor(175))


class TestClampingPublicSurface(unittest.TestCase):
    def test_negative_clamps_low(self):
        from engine.weight_of_war import (
            get_tier, get_descriptor, dsp_resistance_modifier,
            fp_award_multiplier,
        )
        self.assertEqual(get_tier(-5), "at_peace")
        self.assertEqual(dsp_resistance_modifier(-100), 0)
        self.assertEqual(fp_award_multiplier(-100), 1.0)
        self.assertIn("flowing freely", get_descriptor(-99))

    def test_over_max_clamps_high(self):
        from engine.weight_of_war import (
            get_tier, get_descriptor, dsp_resistance_modifier,
            fp_award_multiplier,
        )
        self.assertEqual(get_tier(999), "crushed")
        self.assertEqual(dsp_resistance_modifier(999), 10)
        self.assertEqual(fp_award_multiplier(999), 0.25)
        self.assertIn("Masters have fallen", get_descriptor(999))


# ═════════════════════════════════════════════════════════════════════
# Mechanical modifiers
# ═════════════════════════════════════════════════════════════════════

class TestDspResistanceModifier(unittest.TestCase):
    """Design §7.1 willpower-difficulty modifier."""

    EXPECTED = [
        (0,    0),
        (50,   0),
        (51,   2),
        (100,  2),
        (101,  5),
        (150,  5),
        (151, 10),
        (200, 10),
    ]

    def test_by_tier(self):
        from engine.weight_of_war import dsp_resistance_modifier
        for w, expected in self.EXPECTED:
            with self.subTest(weight=w):
                self.assertEqual(dsp_resistance_modifier(w), expected)


class TestExtraDspOnFailedResist(unittest.TestCase):
    def test_only_in_crushed_tier(self):
        from engine.weight_of_war import extra_dsp_on_failed_resist
        self.assertEqual(extra_dsp_on_failed_resist(0), 0)
        self.assertEqual(extra_dsp_on_failed_resist(100), 0)
        self.assertEqual(extra_dsp_on_failed_resist(150), 0)
        self.assertEqual(extra_dsp_on_failed_resist(151), 1)
        self.assertEqual(extra_dsp_on_failed_resist(200), 1)


class TestFpAwardMultiplier(unittest.TestCase):
    EXPECTED = [
        (0,   1.00),
        (50,  1.00),
        (51,  0.75),
        (100, 0.75),
        (101, 0.50),
        (150, 0.50),
        (151, 0.25),
        (200, 0.25),
    ]

    def test_by_tier(self):
        from engine.weight_of_war import fp_award_multiplier
        for w, expected in self.EXPECTED:
            with self.subTest(weight=w):
                self.assertAlmostEqual(
                    fp_award_multiplier(w), expected, places=4)


class TestFpAwardAfterWeight(unittest.TestCase):
    def test_at_peace_passes_through(self):
        from engine.weight_of_war import fp_award_after_weight
        self.assertEqual(fp_award_after_weight(4, 0), 4)
        self.assertEqual(fp_award_after_weight(1, 20), 1)

    def test_reduced_with_floor(self):
        from engine.weight_of_war import fp_award_after_weight
        # Weight 75 → 0.75 multiplier
        self.assertEqual(fp_award_after_weight(4, 75), 3)   # 3.0 → 3
        self.assertEqual(fp_award_after_weight(2, 75), 1)   # 1.5 → 1
        # Weight 125 → 0.50
        self.assertEqual(fp_award_after_weight(4, 125), 2)
        # Weight 175 → 0.25
        self.assertEqual(fp_award_after_weight(8, 175), 2)  # 2.0
        # Floor applies: 1 * 0.25 = 0.25 → max(1, 0) = 1
        self.assertEqual(fp_award_after_weight(1, 175), 1)

    def test_zero_or_negative_passthrough(self):
        from engine.weight_of_war import fp_award_after_weight
        self.assertEqual(fp_award_after_weight(0, 200), 0)
        self.assertEqual(fp_award_after_weight(-3, 200), -3)


# ═════════════════════════════════════════════════════════════════════
# Char-dict reads
# ═════════════════════════════════════════════════════════════════════

class TestGetWeightDefensive(unittest.TestCase):
    def test_empty_dict(self):
        from engine.weight_of_war import get_weight
        self.assertEqual(get_weight({}), 0)

    def test_null_value(self):
        from engine.weight_of_war import get_weight
        self.assertEqual(get_weight({"weight_of_war": None}), 0)

    def test_present_value(self):
        from engine.weight_of_war import get_weight
        self.assertEqual(get_weight({"weight_of_war": 47}), 47)

    def test_clamps_high(self):
        from engine.weight_of_war import get_weight
        self.assertEqual(get_weight({"weight_of_war": 9999}), 200)

    def test_clamps_low(self):
        from engine.weight_of_war import get_weight
        self.assertEqual(get_weight({"weight_of_war": -10}), 0)

    def test_non_int_returns_zero(self):
        from engine.weight_of_war import get_weight
        self.assertEqual(get_weight({"weight_of_war": "garbage"}), 0)
        self.assertEqual(get_weight({"weight_of_war": [1, 2, 3]}), 0)

    def test_non_dict_returns_zero(self):
        from engine.weight_of_war import get_weight
        self.assertEqual(get_weight(None), 0)
        self.assertEqual(get_weight("a string"), 0)


class TestConvenienceDictHelpers(unittest.TestCase):
    def test_helpers_compose(self):
        from engine.weight_of_war import (
            get_tier_for_char, get_descriptor_for_char,
        )
        self.assertEqual(get_tier_for_char({"weight_of_war": 75}),
                         "burdened")
        self.assertIn("hesitate",
                      get_descriptor_for_char({"weight_of_war": 75}))


# ═════════════════════════════════════════════════════════════════════
# DB reads
# ═════════════════════════════════════════════════════════════════════

class TestGetWeightDb(unittest.TestCase):
    def test_reads_stored_value(self):
        from engine.weight_of_war import get_weight_db
        db = _new_db(initial_weight=42)
        self.assertEqual(_run(get_weight_db(db, 1)), 42)

    def test_missing_char_returns_zero(self):
        from engine.weight_of_war import get_weight_db
        db = _new_db()
        self.assertEqual(_run(get_weight_db(db, 9999)), 0)


class TestGetEventsOrder(unittest.TestCase):
    def test_newest_first(self):
        from engine.weight_of_war import accrue_weight, get_events
        db = _new_db()

        # Use distinct timestamps so ordering is deterministic.
        now = time.time()

        async def populate():
            await accrue_weight(db, 1, 5, "trig_a", "first",
                                now=now)
            await accrue_weight(db, 1, 5, "trig_b", "second",
                                now=now + 10)
            await accrue_weight(db, 1, 5, "trig_c", "third",
                                now=now + 20)

        _run(populate())
        events = _run(get_events(db, 1, limit=10))
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["trigger_type"], "trig_c")
        self.assertEqual(events[1]["trigger_type"], "trig_b")
        self.assertEqual(events[2]["trigger_type"], "trig_a")

    def test_limit_honored(self):
        from engine.weight_of_war import accrue_weight, get_events
        db = _new_db()
        now = time.time()

        async def populate():
            for i in range(5):
                await accrue_weight(db, 1, 3, f"trig_{i}",
                                    now=now + i)

        _run(populate())
        events = _run(get_events(db, 1, limit=2))
        self.assertEqual(len(events), 2)


class TestWeeklyAccrualTotal(unittest.TestCase):
    def test_sums_recent_positives(self):
        from engine.weight_of_war import (
            accrue_weight, weekly_accrual_total,
        )
        db = _new_db()
        now = time.time()
        _run(accrue_weight(db, 1, 5, "a", now=now))
        _run(accrue_weight(db, 1, 7, "b", now=now))
        self.assertEqual(
            _run(weekly_accrual_total(db, 1, now=now)), 12)

    def test_excludes_decays(self):
        from engine.weight_of_war import (
            accrue_weight, decay_weight, weekly_accrual_total,
        )
        db = _new_db(initial_weight=20)
        now = time.time()
        _run(accrue_weight(db, 1, 10, "acc", now=now))
        _run(decay_weight(db, 1, 5, "dec", now=now))
        # weekly_accrual_total only counts positive deltas
        self.assertEqual(
            _run(weekly_accrual_total(db, 1, now=now)), 10)

    def test_excludes_old_events(self):
        from engine.weight_of_war import (
            accrue_weight, weekly_accrual_total,
            WEEKLY_WINDOW_SECONDS,
        )
        db = _new_db()
        now = time.time()
        # An event 8 days ago should fall outside the 7-day window
        old = now - WEEKLY_WINDOW_SECONDS - 100
        _run(accrue_weight(db, 1, 15, "old", now=old))
        _run(accrue_weight(db, 1, 5, "new", now=now))
        self.assertEqual(
            _run(weekly_accrual_total(db, 1, now=now)), 5)

    def test_excludes_admin_adjustments(self):
        """Design §14 admin overrides are out-of-band staff actions
        and should not consume the player-protection weekly headroom.
        """
        from engine.weight_of_war import (
            accrue_weight, set_weight_admin, weekly_accrual_total,
        )
        db = _new_db()
        now = time.time()
        _run(set_weight_admin(db, 1, 100, "staff event", now=now))
        _run(accrue_weight(db, 1, 7, "gameplay", now=now))
        # weekly_accrual_total should see only the gameplay accrual,
        # not the +100 admin jump.
        self.assertEqual(
            _run(weekly_accrual_total(db, 1, now=now)), 7)


# ═════════════════════════════════════════════════════════════════════
# Accrual
# ═════════════════════════════════════════════════════════════════════

class TestAccrueWeightHappyPath(unittest.TestCase):
    def test_applies_delta_and_logs(self):
        from engine.weight_of_war import (
            accrue_weight, get_weight_db, get_events,
        )
        db = _new_db()
        applied = _run(accrue_weight(db, 1, 7, "test_trigger",
                                     "test description"))
        self.assertEqual(applied, 7)
        self.assertEqual(_run(get_weight_db(db, 1)), 7)
        events = _run(get_events(db, 1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["trigger_type"], "test_trigger")
        self.assertEqual(events[0]["delta"], 7)
        self.assertEqual(events[0]["description"], "test description")


class TestAccrueRejectsNonPositive(unittest.TestCase):
    def test_zero_raises(self):
        from engine.weight_of_war import accrue_weight
        db = _new_db()
        with self.assertRaises(ValueError):
            _run(accrue_weight(db, 1, 0, "bad"))

    def test_negative_raises(self):
        from engine.weight_of_war import accrue_weight
        db = _new_db()
        with self.assertRaises(ValueError):
            _run(accrue_weight(db, 1, -5, "bad"))


class TestAccrueClampsSingleEvent(unittest.TestCase):
    """Design §4.4: 'No single event can accrue more than +25.'"""

    def test_999_becomes_25(self):
        from engine.weight_of_war import (
            accrue_weight, get_weight_db, MAX_SINGLE_EVENT,
        )
        db = _new_db()
        applied = _run(accrue_weight(db, 1, 999, "huge"))
        self.assertEqual(applied, MAX_SINGLE_EVENT)
        self.assertEqual(_run(get_weight_db(db, 1)), MAX_SINGLE_EVENT)


class TestAccrueEnforcesWeeklyCap(unittest.TestCase):
    """Design §4.4: '+40 per in-game week ... additional triggers …
    do not add to the numeric score.'"""

    def test_after_40_no_op(self):
        from engine.weight_of_war import (
            accrue_weight, get_weight_db, get_events,
            WEEKLY_ACCRUAL_CAP,
        )
        db = _new_db()
        now = time.time()
        # Push to the weekly cap exactly
        _run(accrue_weight(db, 1, 20, "a", now=now))
        _run(accrue_weight(db, 1, 20, "b", now=now))
        self.assertEqual(_run(get_weight_db(db, 1)),
                         WEEKLY_ACCRUAL_CAP)
        # Next accrual should be a no-op
        applied = _run(accrue_weight(db, 1, 10, "c", now=now))
        self.assertEqual(applied, 0)
        self.assertEqual(_run(get_weight_db(db, 1)),
                         WEEKLY_ACCRUAL_CAP)
        # No event logged for the suppressed trigger
        events = _run(get_events(db, 1))
        self.assertEqual(len(events), 2)


class TestAccrueTrimsToHeadroom(unittest.TestCase):
    """Partial fit: already at +35 within the week, +10 should land
    +5 only (not +10, not 0)."""

    def test_partial_fit(self):
        from engine.weight_of_war import (
            accrue_weight, get_weight_db, WEEKLY_ACCRUAL_CAP,
        )
        db = _new_db()
        now = time.time()
        _run(accrue_weight(db, 1, 25, "first", now=now))
        _run(accrue_weight(db, 1, 10, "second", now=now))  # 35 total
        applied = _run(accrue_weight(db, 1, 10, "trim", now=now))
        self.assertEqual(applied, 5,
                         "Should land only the +5 headroom under "
                         "WEEKLY_ACCRUAL_CAP")
        self.assertEqual(_run(get_weight_db(db, 1)),
                         WEEKLY_ACCRUAL_CAP)


class TestAccrueRespectsHardCap(unittest.TestCase):
    """Design §4.4 hard cap: 200. Past data lets the weight be at 199
    if accrual happened across many weeks, so we use admin override
    for setup."""

    def test_at_199_plus_25_lands_one(self):
        from engine.weight_of_war import (
            accrue_weight, set_weight_admin, get_weight_db,
            WEIGHT_MAX,
        )
        db = _new_db()
        _run(set_weight_admin(db, 1, 199, "test setup"))
        applied = _run(accrue_weight(db, 1, 25, "at_cap"))
        # The single-event clamp gives us +25 to try; the weekly
        # cap (no prior accruals this window) lets all 25 through;
        # then the hard cap [0, 200] trims to +1.
        self.assertEqual(applied, 1)
        self.assertEqual(_run(get_weight_db(db, 1)), WEIGHT_MAX)


class TestAccrueAtHardCapNoOp(unittest.TestCase):
    def test_at_200_no_op(self):
        from engine.weight_of_war import (
            accrue_weight, set_weight_admin, get_weight_db,
            get_events,
        )
        db = _new_db()
        _run(set_weight_admin(db, 1, 200, "test setup"))
        before_events = _run(get_events(db, 1))
        applied = _run(accrue_weight(db, 1, 5, "noop"))
        self.assertEqual(applied, 0)
        self.assertEqual(_run(get_weight_db(db, 1)), 200)
        # No new event log line for the suppressed trigger
        after_events = _run(get_events(db, 1))
        self.assertEqual(len(after_events), len(before_events))


class TestAccrueStampsLastAccrualAt(unittest.TestCase):
    def test_last_accrual_at_updated(self):
        from engine.weight_of_war import accrue_weight
        db = _new_db()
        now = 1_700_000_000.0
        _run(accrue_weight(db, 1, 3, "trig", now=now))
        row = _run(db.fetchone(
            "SELECT weight_last_accrual_at FROM characters "
            "WHERE id = ?", (1,)))
        self.assertEqual(row["weight_last_accrual_at"], now)


# ═════════════════════════════════════════════════════════════════════
# Decay
# ═════════════════════════════════════════════════════════════════════

class TestDecayWeightHappyPath(unittest.TestCase):
    def test_applies_and_logs_negative(self):
        from engine.weight_of_war import (
            decay_weight, get_weight_db, get_events,
        )
        db = _new_db(initial_weight=30)
        applied = _run(decay_weight(db, 1, 5, "meditate"))
        self.assertEqual(applied, 5)
        self.assertEqual(_run(get_weight_db(db, 1)), 25)
        events = _run(get_events(db, 1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["delta"], -5,
                         "Decay events log negative delta to "
                         "distinguish from accrual.")
        self.assertEqual(events[0]["trigger_type"], "meditate")


class TestDecayRejectsNonPositive(unittest.TestCase):
    def test_zero_raises(self):
        from engine.weight_of_war import decay_weight
        db = _new_db(initial_weight=30)
        with self.assertRaises(ValueError):
            _run(decay_weight(db, 1, 0, "bad"))

    def test_negative_raises(self):
        from engine.weight_of_war import decay_weight
        db = _new_db(initial_weight=30)
        with self.assertRaises(ValueError):
            _run(decay_weight(db, 1, -3, "bad"))


class TestDecayClampsToFloor(unittest.TestCase):
    def test_at_5_minus_10_lands_at_zero(self):
        from engine.weight_of_war import (
            decay_weight, get_weight_db,
        )
        db = _new_db(initial_weight=5)
        applied = _run(decay_weight(db, 1, 10, "big_meditate"))
        self.assertEqual(applied, 5,
                         "Should report only the 5 that actually "
                         "decayed, not the full 10.")
        self.assertEqual(_run(get_weight_db(db, 1)), 0)


class TestDecayAtFloorNoOp(unittest.TestCase):
    def test_at_zero_noop(self):
        from engine.weight_of_war import (
            decay_weight, get_weight_db, get_events,
        )
        db = _new_db(initial_weight=0)
        applied = _run(decay_weight(db, 1, 5, "noop_meditate"))
        self.assertEqual(applied, 0)
        self.assertEqual(_run(get_weight_db(db, 1)), 0)
        events = _run(get_events(db, 1))
        self.assertEqual(len(events), 0)


class TestDecayStampsLastDecayAt(unittest.TestCase):
    def test_last_decay_at_updated(self):
        from engine.weight_of_war import decay_weight
        db = _new_db(initial_weight=30)
        now = 1_700_000_000.0
        _run(decay_weight(db, 1, 3, "trig", now=now))
        row = _run(db.fetchone(
            "SELECT weight_last_decay_at FROM characters "
            "WHERE id = ?", (1,)))
        self.assertEqual(row["weight_last_decay_at"], now)


# ═════════════════════════════════════════════════════════════════════
# Admin override
# ═════════════════════════════════════════════════════════════════════

class TestSetWeightAdmin(unittest.TestCase):
    def test_bypasses_caps(self):
        """Admin can jump from 0 to 150 in one call (bypassing both
        single-event and weekly caps)."""
        from engine.weight_of_war import (
            set_weight_admin, get_weight_db,
        )
        db = _new_db()
        result = _run(set_weight_admin(
            db, 1, 150, "staff event: massacre at Ryloth"))
        self.assertEqual(result, 150)
        self.assertEqual(_run(get_weight_db(db, 1)), 150)

    def test_clamps_to_max(self):
        from engine.weight_of_war import (
            set_weight_admin, get_weight_db, WEIGHT_MAX,
        )
        db = _new_db()
        result = _run(set_weight_admin(db, 1, 9999, "staff override"))
        self.assertEqual(result, WEIGHT_MAX)
        self.assertEqual(_run(get_weight_db(db, 1)), WEIGHT_MAX)

    def test_clamps_to_min(self):
        from engine.weight_of_war import (
            set_weight_admin, get_weight_db, WEIGHT_MIN,
        )
        db = _new_db(initial_weight=50)
        result = _run(set_weight_admin(db, 1, -100, "staff override"))
        self.assertEqual(result, WEIGHT_MIN)
        self.assertEqual(_run(get_weight_db(db, 1)), WEIGHT_MIN)

    def test_logs_admin_adjust(self):
        from engine.weight_of_war import (
            set_weight_admin, get_events,
        )
        db = _new_db()
        _run(set_weight_admin(db, 1, 50, "test note"))
        events = _run(get_events(db, 1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["trigger_type"], "admin_adjust")
        self.assertEqual(events[0]["delta"], 50)
        self.assertEqual(events[0]["description"], "test note")


class TestSetWeightAdminRequiresNote(unittest.TestCase):
    def test_empty_note_raises(self):
        from engine.weight_of_war import set_weight_admin
        db = _new_db()
        with self.assertRaises(ValueError):
            _run(set_weight_admin(db, 1, 50, ""))

    def test_whitespace_note_raises(self):
        from engine.weight_of_war import set_weight_admin
        db = _new_db()
        with self.assertRaises(ValueError):
            _run(set_weight_admin(db, 1, 50, "   "))


class TestSetWeightAdminNoOp(unittest.TestCase):
    def test_already_at_target_no_event(self):
        from engine.weight_of_war import (
            set_weight_admin, get_events,
        )
        db = _new_db(initial_weight=42)
        result = _run(set_weight_admin(
            db, 1, 42, "staff confirms"))
        self.assertEqual(result, 42)
        events = _run(get_events(db, 1))
        self.assertEqual(len(events), 0,
                         "No event should log for a no-op admin set.")


class TestSetWeightAdminUsesCorrectStamp(unittest.TestCase):
    def test_admin_up_stamps_accrual(self):
        from engine.weight_of_war import set_weight_admin
        db = _new_db(initial_weight=10)
        now = 1_700_000_000.0
        _run(set_weight_admin(db, 1, 50, "raise", now=now))
        row = _run(db.fetchone(
            "SELECT weight_last_accrual_at, weight_last_decay_at "
            "FROM characters WHERE id = ?", (1,)))
        self.assertEqual(row["weight_last_accrual_at"], now)
        self.assertIsNone(row["weight_last_decay_at"])

    def test_admin_down_stamps_decay(self):
        from engine.weight_of_war import set_weight_admin
        db = _new_db(initial_weight=50)
        now = 1_700_000_000.0
        _run(set_weight_admin(db, 1, 20, "lower", now=now))
        row = _run(db.fetchone(
            "SELECT weight_last_accrual_at, weight_last_decay_at "
            "FROM characters WHERE id = ?", (1,)))
        self.assertEqual(row["weight_last_decay_at"], now)
        self.assertIsNone(row["weight_last_accrual_at"])


# ═════════════════════════════════════════════════════════════════════
# Production-schema integration
# ═════════════════════════════════════════════════════════════════════
#
# The tests above use a hand-rolled `_AsyncSqlite` fixture. That's
# fine for unit-level isolation of the engine module's logic
# (clamping, weekly cap, tier mapping, etc.) — but it lets a real
# class of bug slip through: the fixture's schema can diverge from
# the production schema, and the unit tests will keep passing while
# every production call raises ``OperationalError: no such column``.
#
# This phantom-pattern is "vacuous-fixture": tests pass against a
# fixture that doesn't match production, so they verify nothing
# about whether the module's SQL is actually runnable. The May 23
# WoW.1-fix wave caught one instance of this — the engine module
# wrote ``WHERE char_id = ?`` against ``characters``, but the
# production schema's PK is ``id``. The fixture used ``char_id`` as
# the PK, masking the bug across 58 passing tests.
#
# The remediation is the test class below: run the same operations
# against a real ``Database`` instance (in-memory SQLite, real
# migrations applied, real ``characters`` schema). This is slower
# than the unit fixture but catches column-name and SQL-syntax
# bugs that the fixture cannot.
#
# This class is small — just enough to prove the SQL queries are
# valid against the actual schema. Logic correctness stays in the
# unit tests above.

class _ProductionDbHarness:
    """Initialize a real Database against an in-memory SQLite, apply
    all migrations, seed one test character. Returns the Database
    object plus the seeded character's id."""

    def __init__(self):
        self.db = None
        self.char_id: int = 0

    async def setup(self) -> None:
        from db.database import Database
        self.db = Database(":memory:")
        await self.db.connect()
        await self.db.initialize()
        await self.db._db.execute(
            "INSERT INTO accounts (id, username, password_hash) "
            "VALUES (?, ?, ?)",
            (1, "u", "p"),
        )
        await self.db._db.execute(
            "INSERT INTO characters (id, account_id, name, room_id) "
            "VALUES (?, ?, ?, ?)",
            (42, 1, "RealJedi", 1),
        )
        await self.db._db.commit()
        self.char_id = 42


@pytest.mark.slow  # heavy: migration
class TestProductionSchemaIntegration(unittest.TestCase):
    """Run engine/weight_of_war.py against a real Database.

    Every test here pins the column-naming contract between the
    engine module's SQL and the production ``characters`` table. If
    a future edit changes either side without updating the other,
    these tests fail with the same ``OperationalError`` that
    production would.
    """

    def test_get_weight_db_runs_against_production_schema(self):
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            from engine.weight_of_war import get_weight_db
            w = await get_weight_db(h.db, h.char_id)
            self.assertEqual(w, 0)
        _run(go())

    def test_get_weight_db_missing_char_returns_zero(self):
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            from engine.weight_of_war import get_weight_db
            w = await get_weight_db(h.db, 9999)
            self.assertEqual(w, 0)
        _run(go())

    def test_accrue_weight_runs_against_production_schema(self):
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            from engine.weight_of_war import accrue_weight, get_weight_db
            applied = await accrue_weight(
                h.db, h.char_id, 10, "test", "smoke",
            )
            self.assertEqual(applied, 10)
            self.assertEqual(await get_weight_db(h.db, h.char_id), 10)
        _run(go())

    def test_decay_weight_runs_against_production_schema(self):
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            from engine.weight_of_war import (
                accrue_weight, decay_weight, get_weight_db,
            )
            await accrue_weight(h.db, h.char_id, 20, "test", "")
            applied = await decay_weight(
                h.db, h.char_id, 8, "meditate", "",
            )
            self.assertEqual(applied, 8)
            self.assertEqual(await get_weight_db(h.db, h.char_id), 12)
        _run(go())

    def test_set_weight_admin_runs_against_production_schema(self):
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            from engine.weight_of_war import (
                set_weight_admin, get_weight_db,
            )
            target = await set_weight_admin(
                h.db, h.char_id, 75, "story event",
            )
            self.assertEqual(target, 75)
            self.assertEqual(await get_weight_db(h.db, h.char_id), 75)
        _run(go())

    def test_set_weight_admin_down_path_runs(self):
        """Admin override below current value uses the decay-stamp
        SQL branch; that branch's SQL is separately compiled."""
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            from engine.weight_of_war import (
                accrue_weight, set_weight_admin, get_weight_db,
            )
            await accrue_weight(h.db, h.char_id, 25, "max_first", "")
            target = await set_weight_admin(
                h.db, h.char_id, 5, "lower for arc",
            )
            self.assertEqual(target, 5)
            self.assertEqual(await get_weight_db(h.db, h.char_id), 5)
        _run(go())

    def test_get_events_runs_against_production_schema(self):
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            from engine.weight_of_war import accrue_weight, get_events
            await accrue_weight(h.db, h.char_id, 5, "t1", "first")
            await accrue_weight(h.db, h.char_id, 5, "t2", "second")
            events = await get_events(h.db, h.char_id, limit=10)
            self.assertEqual(len(events), 2)
            # Newest first
            self.assertEqual(events[0]["trigger_type"], "t2")
            self.assertEqual(events[1]["trigger_type"], "t1")
        _run(go())

    def test_weekly_accrual_total_runs(self):
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            from engine.weight_of_war import (
                accrue_weight, weekly_accrual_total,
            )
            await accrue_weight(h.db, h.char_id, 10, "t", "")
            total = await weekly_accrual_total(h.db, h.char_id)
            self.assertEqual(total, 10)
        _run(go())

    def test_save_character_accepts_wow_columns(self):
        """The WoW columns are in _CHARACTER_WRITABLE_COLUMNS so
        save_character(char_id, weight_of_war=N) works. The
        engine module doesn't use save_character today, but admin
        commands and future post-launch staff tooling will."""
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            await h.db.save_character(h.char_id, weight_of_war=33)
            await h.db.save_character(
                h.char_id, weight_last_decay_at=1234.5,
            )
            await h.db.save_character(
                h.char_id, weight_last_accrual_at=2345.6,
            )
            rows = await h.db._db.execute_fetchall(
                "SELECT weight_of_war, weight_last_decay_at, "
                "weight_last_accrual_at FROM characters WHERE id = ?",
                (h.char_id,),
            )
            self.assertEqual(rows[0]["weight_of_war"], 33)
            self.assertEqual(rows[0]["weight_last_decay_at"], 1234.5)
            self.assertEqual(rows[0]["weight_last_accrual_at"], 2345.6)
        _run(go())

    def test_save_character_rejects_wow_typo(self):
        async def go():
            h = _ProductionDbHarness()
            await h.setup()
            with self.assertRaises(ValueError):
                await h.db.save_character(h.char_id, weight_of_warr=99)
            with self.assertRaises(ValueError):
                await h.db.save_character(h.char_id, weight_of_wars=99)
        _run(go())


if __name__ == "__main__":
    unittest.main()
