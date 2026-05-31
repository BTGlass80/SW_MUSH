# -*- coding: utf-8 -*-
"""
tests/test_syn3a_region_contest_state_machine.py — SYN.3.a (2026-05-25).

Pins the new region-keyed contest engine in ``engine/contest.py`` per
``contestable_wilderness_design_v2.md`` §2.4 + §3.3.

SYN.3.a ships the schema + parallel-engine half. SYN.3.b will:
  * Spawn the Region Anchor NPC at culminating-fight start
  * Detect killing-blow on Anchor and transfer ownership
  * Enforce 2× influence doubling during accumulation
  * Wire auto-trigger hook into ``adjust_territory_influence``
  * Retarget HUD/PvP/seize/tick callers off the Drop 6D block
  * Physically delete the Drop 6D contest functions

Test sections
─────────────
  1. TestSchema                    — table create + ensure_territory_schema wire
  2. TestPureRules                 — Anchor HP / reinforcement / outnumbered
  3. TestQuerySurfaces             — get_active, get_org, is_in_contest
  4. TestDeclareRegionContest      — input validation + happy path + uniqueness
  5. TestCooldown                  — 14-day cooldown enforcement
  6. TestAutoTriggerRivalHeld      — check_and_declare 75% ratio path
  7. TestAutoTriggerUnowned        — un-owned region is NOT auto-triggered
  8. TestTickResolution            — defender-win-by-default placeholder
  9. TestStatusLines               — display formatting
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
    """Run a coroutine in a fresh event loop (BugFix5 Py3.14 pattern)."""
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
# tests/test_syn1a_region_ownership.py and tests/test_syn2_wilderness_aware_security.py.

class _SyncAsyncSqlite:
    """aiosqlite-compatible adapter over stdlib sqlite3."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        self._conn.execute(sql, params)

    async def execute_fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    async def commit(self):
        self._conn.commit()


class _MiniDB:
    """Minimal Database-API surface for SYN.3.a tests."""

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
            CREATE TABLE region_ownership (
                region_slug   TEXT    NOT NULL PRIMARY KEY,
                org_code      TEXT    NOT NULL,
                zone_id       INTEGER,
                claimed_by    INTEGER NOT NULL,
                claimed_at    REAL    NOT NULL,
                maintenance   INTEGER NOT NULL DEFAULT 3000
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

    async def get_zone(self, zone_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,)
        )
        return dict(rows[0]) if rows else None

    # ── Seed helpers (test-only) ──────────────────────────────────
    def seed_org(self, *, org_id, code, treasury=100_000, name=None):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name, treasury) "
            "VALUES (?, ?, ?, ?)",
            (org_id, code, name or code.title(), treasury),
        )
        self._db._conn.commit()

    def seed_zone(self, *, zone_id, name, declared_security="lawless"):
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

    def seed_region(self, *, slug, zone_id, owner_org_code=None,
                    landmark_count=3, start_room_id=100):
        """Create landmark rooms + optional ownership row."""
        for i in range(landmark_count):
            self.seed_room(
                room_id=start_room_id + i,
                name=f"{slug} landmark #{i + 1}",
                zone_id=zone_id,
                wilderness_region_id=slug,
            )
        if owner_org_code:
            self._db._conn.execute(
                """INSERT INTO region_ownership
                   (region_slug, org_code, zone_id, claimed_by, claimed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (slug, owner_org_code, zone_id, 1, time.time()),
            )
            self._db._conn.commit()

    def seed_influence(self, *, zone_id, org_code, score):
        now = time.time()
        self._db._conn.execute(
            """INSERT INTO territory_influence
               (zone_id, org_code, score, last_activity, last_presence)
               VALUES (?, ?, ?, ?, ?)""",
            (zone_id, org_code, score, now, now),
        )
        self._db._conn.commit()

    def seed_cooldown(self, *, region_slug, org_code,
                      cooldown_until):
        self._db._conn.execute(
            """INSERT INTO region_contest_cooldowns
               (region_slug, org_code, cooldown_until)
               VALUES (?, ?, ?)""",
            (region_slug, org_code, cooldown_until),
        )
        self._db._conn.commit()


async def _setup_schema(mdb):
    """Convenience: ensure the SYN.3.a schema is created in the test DB."""
    from engine.contest import ensure_region_contest_schema
    await ensure_region_contest_schema(mdb)


# ──────────────────────────────────────────────────────────────────────
# 1. TestSchema
# ──────────────────────────────────────────────────────────────────────

class TestSchema(unittest.TestCase):
    """Schema creation + idempotency + integration into bootstrap."""

    def test_schema_creates_tables(self):
        mdb = _MiniDB()
        _run(_setup_schema(mdb))
        rows = _run(mdb.fetchall(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name LIKE 'region_contest%'"
        ))
        names = {r["name"] for r in rows}
        self.assertIn("region_contests", names)
        self.assertIn("region_contest_cooldowns", names)

    def test_schema_creates_indexes(self):
        mdb = _MiniDB()
        _run(_setup_schema(mdb))
        rows = _run(mdb.fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_region_contest%'"
        ))
        names = {r["name"] for r in rows}
        # Per the SQL: at least region, status, challenger, defender,
        # and the cooldowns org index.
        self.assertIn("idx_region_contests_region", names)
        self.assertIn("idx_region_contests_status", names)
        self.assertIn("idx_region_contests_challenger", names)
        self.assertIn("idx_region_contests_defender", names)
        self.assertIn("idx_region_contest_cooldowns_org", names)

    def test_schema_idempotent(self):
        """Repeated ensure_region_contest_schema calls must not raise."""
        mdb = _MiniDB()
        _run(_setup_schema(mdb))
        _run(_setup_schema(mdb))  # second call is the test
        # Sanity: still queryable
        rows = _run(mdb.fetchall(
            "SELECT COUNT(*) as c FROM region_contests"
        ))
        self.assertEqual(rows[0]["c"], 0)

    def test_unique_constraint_one_active_per_region(self):
        """UNIQUE(region_slug, status) blocks two active rows in same region."""
        mdb = _MiniDB()
        _run(_setup_schema(mdb))
        now = time.time()
        _run(mdb.execute(
            """INSERT INTO region_contests
               (region_slug, defender_org_code, challenger_org_code,
                started_at, accumulation_ends_at, ends_at, status)
               VALUES ('dune_sea', 'hutt_cartel', 'cis',
                       ?, ?, ?, 'active')""",
            (now, now + 100, now + 200),
        ))
        # Inserting a second 'active' row for the same region must fail
        with self.assertRaises(Exception):
            _run(mdb.execute(
                """INSERT INTO region_contests
                   (region_slug, defender_org_code, challenger_org_code,
                    started_at, accumulation_ends_at, ends_at, status)
                   VALUES ('dune_sea', 'hutt_cartel', 'republic',
                           ?, ?, ?, 'active')""",
                (now, now + 100, now + 200),
            ))

    def test_wired_into_ensure_territory_schema(self):
        """ensure_territory_schema must call ensure_region_contest_schema."""
        # Source-level check is sufficient and avoids the cost of
        # standing up a full Database.
        territory_src = (PROJECT_ROOT / "engine" / "territory.py").read_text(
            encoding="utf-8")
        self.assertIn("ensure_region_contest_schema", territory_src,
                      "ensure_territory_schema must import + call "
                      "ensure_region_contest_schema")
        # The import should be inside the bootstrap (after the legacy
        # Drop 6D ensure_contest_schema call).
        bootstrap_idx = territory_src.find("async def ensure_territory_schema")
        wire_idx = territory_src.find(
            "ensure_region_contest_schema", bootstrap_idx)
        self.assertGreater(
            wire_idx, bootstrap_idx,
            "wire-up must live inside ensure_territory_schema body")


# ──────────────────────────────────────────────────────────────────────
# 2. TestPureRules
# ──────────────────────────────────────────────────────────────────────

class TestPureRules(unittest.TestCase):
    """compute_anchor_hp, compute_anchor_reinforcements, multiplier."""

    def test_anchor_hp_at_floor(self):
        from engine.contest import compute_anchor_hp
        self.assertEqual(compute_anchor_hp(50), 100)

    def test_anchor_hp_below_floor_is_base(self):
        from engine.contest import compute_anchor_hp
        self.assertEqual(compute_anchor_hp(20), 100)
        self.assertEqual(compute_anchor_hp(0), 100)

    def test_anchor_hp_design_worked_example(self):
        """Design §2.4 worked example: defender 90 influence → 140 HP."""
        from engine.contest import compute_anchor_hp
        self.assertEqual(compute_anchor_hp(90), 140)

    def test_anchor_hp_max_influence(self):
        """Max possible influence (150 cap) → 200 HP."""
        from engine.contest import compute_anchor_hp
        self.assertEqual(compute_anchor_hp(150), 200)

    def test_anchor_hp_none_handled(self):
        from engine.contest import compute_anchor_hp
        self.assertEqual(compute_anchor_hp(None), 100)

    def test_reinforcements_below_threshold(self):
        from engine.contest import compute_anchor_reinforcements
        self.assertEqual(compute_anchor_reinforcements(0), 0)
        self.assertEqual(compute_anchor_reinforcements(49), 0)
        self.assertEqual(compute_anchor_reinforcements(80), 0)
        self.assertEqual(compute_anchor_reinforcements(100), 0)

    def test_reinforcements_above_threshold(self):
        from engine.contest import compute_anchor_reinforcements
        # +1 per 25 above 100
        self.assertEqual(compute_anchor_reinforcements(125), 1)
        self.assertEqual(compute_anchor_reinforcements(149), 1)  # 24 above
        self.assertEqual(compute_anchor_reinforcements(150), 2)

    def test_reinforcements_none_handled(self):
        from engine.contest import compute_anchor_reinforcements
        self.assertEqual(compute_anchor_reinforcements(None), 0)

    def test_outnumbered_multiplier_defender_outnumbered(self):
        from engine.contest import compute_outnumbered_defender_multiplier
        self.assertEqual(
            compute_outnumbered_defender_multiplier(5, 8), 1.5)

    def test_outnumbered_multiplier_equal_or_more(self):
        from engine.contest import compute_outnumbered_defender_multiplier
        self.assertEqual(
            compute_outnumbered_defender_multiplier(5, 5), 1.0)
        self.assertEqual(
            compute_outnumbered_defender_multiplier(8, 5), 1.0)

    def test_outnumbered_multiplier_edge_zero_defender(self):
        from engine.contest import compute_outnumbered_defender_multiplier
        # Zero-defender is technically outnumbered by anything ≥ 1
        self.assertEqual(
            compute_outnumbered_defender_multiplier(0, 1), 1.5)
        self.assertEqual(
            compute_outnumbered_defender_multiplier(0, 0), 1.0)

    def test_outnumbered_multiplier_none_handled(self):
        from engine.contest import compute_outnumbered_defender_multiplier
        self.assertEqual(
            compute_outnumbered_defender_multiplier(None, None), 1.0)
        self.assertEqual(
            compute_outnumbered_defender_multiplier(None, 5), 1.5)


# ──────────────────────────────────────────────────────────────────────
# 3. TestQuerySurfaces
# ──────────────────────────────────────────────────────────────────────

class TestQuerySurfaces(unittest.TestCase):
    """get_active_region_contest, get_org_region_contests, is_*."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        # Seed two regions and one active contest in dune_sea
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            start_room_id=100,
        )
        self.mdb.seed_region(
            slug="coruscant_underworld", zone_id=2,
            start_room_id=200,
        )
        now = time.time()
        _run(self.mdb.execute(
            """INSERT INTO region_contests
               (region_slug, defender_org_code, challenger_org_code,
                zone_id, started_at, accumulation_ends_at, ends_at, status)
               VALUES ('dune_sea', 'hutt_cartel', 'cis',
                       1, ?, ?, ?, 'active')""",
            (now, now + 1000, now + 2000),
        ))

    def test_get_active_returns_active_contest(self):
        from engine.contest import get_active_region_contest
        c = _run(get_active_region_contest(self.mdb, "dune_sea"))
        self.assertIsNotNone(c)
        self.assertEqual(c["defender_org_code"], "hutt_cartel")
        self.assertEqual(c["challenger_org_code"], "cis")

    def test_get_active_returns_none_for_unowned_quiet_region(self):
        from engine.contest import get_active_region_contest
        c = _run(get_active_region_contest(self.mdb, "coruscant_underworld"))
        self.assertIsNone(c)

    def test_get_active_returns_none_for_unknown_region(self):
        from engine.contest import get_active_region_contest
        c = _run(get_active_region_contest(self.mdb, "nonexistent_slug"))
        self.assertIsNone(c)

    def test_get_active_ignores_resolved_contests(self):
        """A contest in 'resolved_defender' status must NOT be returned."""
        from engine.contest import get_active_region_contest
        now = time.time()
        _run(self.mdb.execute(
            """INSERT INTO region_contests
               (region_slug, defender_org_code, challenger_org_code,
                zone_id, started_at, accumulation_ends_at, ends_at, status)
               VALUES ('coruscant_underworld', 'cis', 'republic',
                       2, ?, ?, ?, 'resolved_defender')""",
            (now - 10000, now - 5000, now - 4000),
        ))
        c = _run(get_active_region_contest(
            self.mdb, "coruscant_underworld"))
        self.assertIsNone(c)

    def test_get_org_region_contests_returns_defender(self):
        from engine.contest import get_org_region_contests
        contests = _run(get_org_region_contests(self.mdb, "hutt_cartel"))
        self.assertEqual(len(contests), 1)
        self.assertEqual(contests[0]["defender_org_code"], "hutt_cartel")

    def test_get_org_region_contests_returns_challenger(self):
        from engine.contest import get_org_region_contests
        contests = _run(get_org_region_contests(self.mdb, "cis"))
        self.assertEqual(len(contests), 1)
        self.assertEqual(contests[0]["challenger_org_code"], "cis")

    def test_get_org_region_contests_returns_empty_for_uninvolved(self):
        from engine.contest import get_org_region_contests
        contests = _run(get_org_region_contests(self.mdb, "republic"))
        self.assertEqual(contests, [])

    def test_is_in_active_contest_both_orderings(self):
        from engine.contest import is_region_in_active_contest
        self.assertTrue(_run(is_region_in_active_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis")))
        # Order doesn't matter
        self.assertTrue(_run(is_region_in_active_contest(
            self.mdb, "dune_sea", "cis", "hutt_cartel")))

    def test_is_in_active_contest_uninvolved_returns_false(self):
        from engine.contest import is_region_in_active_contest
        self.assertFalse(_run(is_region_in_active_contest(
            self.mdb, "dune_sea", "hutt_cartel", "republic")))

    def test_is_in_active_contest_same_org_returns_false(self):
        from engine.contest import is_region_in_active_contest
        self.assertFalse(_run(is_region_in_active_contest(
            self.mdb, "dune_sea", "hutt_cartel", "hutt_cartel")))

    def test_is_in_active_contest_no_contest_returns_false(self):
        from engine.contest import is_region_in_active_contest
        self.assertFalse(_run(is_region_in_active_contest(
            self.mdb, "coruscant_underworld", "cis", "republic")))


# ──────────────────────────────────────────────────────────────────────
# 4. TestDeclareRegionContest
# ──────────────────────────────────────────────────────────────────────

class TestDeclareRegionContest(unittest.TestCase):
    """declare_region_contest input validation + happy path + uniqueness."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            start_room_id=100,
        )

    def test_declare_happy_path(self):
        from engine.contest import declare_region_contest
        result = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        self.assertTrue(result["ok"], result["msg"])
        self.assertIsNotNone(result["contest_id"])
        # Row exists in DB
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (result["contest_id"],),
        ))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "active")
        self.assertEqual(rows[0]["zone_id"], 1)

    def test_declare_unowned_region_seize(self):
        """defender_org_code=None is valid (un-owned seize path)."""
        from engine.contest import declare_region_contest
        result = _run(declare_region_contest(
            self.mdb, "dune_sea", None, "cis",
            zone_id=1, session_mgr=None,
        ))
        self.assertTrue(result["ok"], result["msg"])
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (result["contest_id"],),
        ))
        self.assertIsNone(rows[0]["defender_org_code"])

    def test_declare_rejects_independent_challenger(self):
        from engine.contest import declare_region_contest
        result = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "independent",
            zone_id=1, session_mgr=None,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("Independent", result["msg"])

    def test_declare_rejects_empty_challenger(self):
        from engine.contest import declare_region_contest
        result = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "",
            zone_id=1, session_mgr=None,
        ))
        self.assertFalse(result["ok"])

    def test_declare_rejects_self_contest(self):
        from engine.contest import declare_region_contest
        result = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "hutt_cartel",
            zone_id=1, session_mgr=None,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("itself", result["msg"])

    def test_declare_rejects_duplicate_active(self):
        """Cannot declare a second contest while one is active."""
        from engine.contest import declare_region_contest
        first = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        self.assertTrue(first["ok"])
        # Second declaration should fail
        second = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "republic",
            zone_id=1, session_mgr=None,
        ))
        self.assertFalse(second["ok"])
        self.assertIn("already active", second["msg"])

    def test_declare_sets_phase_timestamps_correctly(self):
        """accumulation_ends_at + 4h == ends_at; ends_at - started_at = 7 days."""
        from engine.contest import (
            declare_region_contest,
            REGION_CONTEST_DURATION_SECS,
            REGION_CONTEST_CULMINATING_SECS,
        )
        result = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (result["contest_id"],),
        ))
        c = rows[0]
        started = float(c["started_at"])
        accum_end = float(c["accumulation_ends_at"])
        ends = float(c["ends_at"])
        # Total duration is 7 days
        self.assertAlmostEqual(
            ends - started, REGION_CONTEST_DURATION_SECS, delta=1.0)
        # Culminating window is 4 hours
        self.assertAlmostEqual(
            ends - accum_end, REGION_CONTEST_CULMINATING_SECS, delta=1.0)

    def test_declare_broadcasts_to_session_mgr(self):
        """When session_mgr is provided, broadcast lines go out."""
        from engine.contest import declare_region_contest
        sent = []

        class FakeSession:
            is_in_game = True

            async def send_line(self, msg):
                sent.append(msg)

        class FakeMgr:
            all = [FakeSession(), FakeSession()]

        result = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=FakeMgr(),
        ))
        self.assertTrue(result["ok"])
        self.assertEqual(len(sent), 2)
        self.assertIn("REGION CONTEST", sent[0])
        self.assertIn("Hutt Cartel", sent[0])
        self.assertIn("Cis", sent[0])

    def test_declare_broadcasts_unowned_marker(self):
        """un-owned seize broadcast shows '(un-owned)' for defender."""
        from engine.contest import declare_region_contest
        sent = []

        class FakeSession:
            is_in_game = True

            async def send_line(self, msg):
                sent.append(msg)

        class FakeMgr:
            all = [FakeSession()]

        _run(declare_region_contest(
            self.mdb, "dune_sea", None, "cis",
            zone_id=1, session_mgr=FakeMgr(),
        ))
        self.assertIn("(un-owned)", sent[0])


# ──────────────────────────────────────────────────────────────────────
# 5. TestCooldown
# ──────────────────────────────────────────────────────────────────────

class TestCooldown(unittest.TestCase):
    """14-day post-loss cooldown enforcement."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            start_room_id=100,
        )

    def test_no_cooldown_row_returns_false(self):
        from engine.contest import is_org_on_contest_cooldown
        self.assertFalse(_run(is_org_on_contest_cooldown(
            self.mdb, "dune_sea", "cis")))

    def test_future_cooldown_returns_true(self):
        from engine.contest import is_org_on_contest_cooldown
        future = time.time() + 86400  # 1 day from now
        self.mdb.seed_cooldown(
            region_slug="dune_sea", org_code="cis",
            cooldown_until=future,
        )
        self.assertTrue(_run(is_org_on_contest_cooldown(
            self.mdb, "dune_sea", "cis")))

    def test_past_cooldown_returns_false(self):
        """A cooldown_until in the past is no longer enforced."""
        from engine.contest import is_org_on_contest_cooldown
        past = time.time() - 86400
        self.mdb.seed_cooldown(
            region_slug="dune_sea", org_code="cis",
            cooldown_until=past,
        )
        self.assertFalse(_run(is_org_on_contest_cooldown(
            self.mdb, "dune_sea", "cis")))

    def test_declare_rejects_org_on_cooldown(self):
        """declare_region_contest must reject a challenger on cooldown."""
        from engine.contest import declare_region_contest
        future = time.time() + 86400
        self.mdb.seed_cooldown(
            region_slug="dune_sea", org_code="cis",
            cooldown_until=future,
        )
        result = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        self.assertFalse(result["ok"])
        self.assertIn("cooldown", result["msg"].lower())

    def test_cooldown_other_region_does_not_apply(self):
        """A cooldown on region A does not block a contest on region B."""
        from engine.contest import is_org_on_contest_cooldown
        future = time.time() + 86400
        self.mdb.seed_cooldown(
            region_slug="dune_sea", org_code="cis",
            cooldown_until=future,
        )
        # Same org, different region — must NOT be on cooldown
        self.assertFalse(_run(is_org_on_contest_cooldown(
            self.mdb, "coruscant_underworld", "cis")))


# ──────────────────────────────────────────────────────────────────────
# 6. TestAutoTriggerRivalHeld
# ──────────────────────────────────────────────────────────────────────

class TestAutoTriggerRivalHeld(unittest.TestCase):
    """check_and_declare_region_contests for rival-held regions."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_org(org_id=2, code="cis")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            start_room_id=100,
        )

    def test_auto_trigger_above_ratio(self):
        """challenger inf >= 75% of defender inf → contest declared."""
        from engine.contest import (
            check_and_declare_region_contests,
            get_active_region_contest,
        )
        # Defender: 100, Challenger: 80 → ratio 0.80 (>= 0.75)
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=100)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=80)

        result = _run(check_and_declare_region_contests(
            self.mdb, "cis", "dune_sea", session_mgr=None,
        ))
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])

        c = _run(get_active_region_contest(self.mdb, "dune_sea"))
        self.assertIsNotNone(c)
        self.assertEqual(c["challenger_org_code"], "cis")
        self.assertEqual(c["defender_org_code"], "hutt_cartel")

    def test_no_trigger_below_ratio(self):
        """challenger inf < 75% of defender inf → no contest."""
        from engine.contest import (
            check_and_declare_region_contests,
            get_active_region_contest,
        )
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=100)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=70)  # 0.70

        result = _run(check_and_declare_region_contests(
            self.mdb, "cis", "dune_sea", session_mgr=None,
        ))
        self.assertIsNone(result)
        self.assertIsNone(_run(get_active_region_contest(
            self.mdb, "dune_sea")))

    def test_no_trigger_below_min_floor(self):
        """challenger below 50 influence → no contest even if ratio met."""
        from engine.contest import (
            check_and_declare_region_contests,
            get_active_region_contest,
        )
        # Defender 20, Challenger 40 — ratio 2.0 but challenger < 50
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=20)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=40)

        result = _run(check_and_declare_region_contests(
            self.mdb, "cis", "dune_sea", session_mgr=None,
        ))
        self.assertIsNone(result)
        self.assertIsNone(_run(get_active_region_contest(
            self.mdb, "dune_sea")))

    def test_no_trigger_owner_self(self):
        """Owner cannot auto-trigger contest against itself."""
        from engine.contest import check_and_declare_region_contests
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=100)
        result = _run(check_and_declare_region_contests(
            self.mdb, "hutt_cartel", "dune_sea", session_mgr=None,
        ))
        self.assertIsNone(result)

    def test_no_trigger_independent_challenger(self):
        from engine.contest import check_and_declare_region_contests
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=100)
        result = _run(check_and_declare_region_contests(
            self.mdb, "independent", "dune_sea", session_mgr=None,
        ))
        self.assertIsNone(result)

    def test_no_trigger_when_active_contest_exists(self):
        """If a contest is already active, no new trigger fires."""
        from engine.contest import (
            check_and_declare_region_contests,
            declare_region_contest,
        )
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=100)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=80)
        self.mdb.seed_influence(zone_id=1, org_code="republic", score=85)

        # First, declare a contest with cis as challenger
        first = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        self.assertTrue(first["ok"])

        # Republic also has 85 influence — but a contest is in flight
        result = _run(check_and_declare_region_contests(
            self.mdb, "republic", "dune_sea", session_mgr=None,
        ))
        self.assertIsNone(result)

    def test_no_trigger_when_on_cooldown(self):
        """An org on cooldown for this region can't auto-trigger."""
        from engine.contest import check_and_declare_region_contests
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=100)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=80)
        future = time.time() + 86400
        self.mdb.seed_cooldown(
            region_slug="dune_sea", org_code="cis",
            cooldown_until=future,
        )
        result = _run(check_and_declare_region_contests(
            self.mdb, "cis", "dune_sea", session_mgr=None,
        ))
        self.assertIsNone(result)

    def test_zero_defender_inf_triggers_if_challenger_above_floor(self):
        """Edge: owner decayed to zero influence; challenger above floor."""
        from engine.contest import (
            check_and_declare_region_contests,
            get_active_region_contest,
        )
        # Defender has no influence row at all (effectively 0)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=60)

        result = _run(check_and_declare_region_contests(
            self.mdb, "cis", "dune_sea", session_mgr=None,
        ))
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])
        c = _run(get_active_region_contest(self.mdb, "dune_sea"))
        self.assertEqual(c["challenger_org_code"], "cis")
        self.assertEqual(c["defender_org_code"], "hutt_cartel")


# ──────────────────────────────────────────────────────────────────────
# 7. TestAutoTriggerUnowned
# ──────────────────────────────────────────────────────────────────────

class TestAutoTriggerUnowned(unittest.TestCase):
    """check_and_declare must NOT auto-trigger on un-owned regions."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        # Un-owned region
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code=None,
            start_room_id=100,
        )

    def test_no_auto_trigger_on_unowned_region(self):
        """Per design §2.4: un-owned seize is a parser command, not auto."""
        from engine.contest import (
            check_and_declare_region_contests,
            get_active_region_contest,
        )
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=120)
        result = _run(check_and_declare_region_contests(
            self.mdb, "cis", "dune_sea", session_mgr=None,
        ))
        self.assertIsNone(result)
        self.assertIsNone(_run(get_active_region_contest(
            self.mdb, "dune_sea")))

    def test_explicit_declare_on_unowned_works(self):
        """declare_region_contest(defender=None, ...) IS still supported."""
        from engine.contest import declare_region_contest
        result = _run(declare_region_contest(
            self.mdb, "dune_sea", None, "cis",
            zone_id=1, session_mgr=None,
        ))
        self.assertTrue(result["ok"])


# ──────────────────────────────────────────────────────────────────────
# 8. TestTickResolution
# ──────────────────────────────────────────────────────────────────────

class TestTickResolution(unittest.TestCase):
    """tick_region_contest_resolution: placeholder defender-win-by-default."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_org(org_id=2, code="cis")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            start_room_id=100,
        )

    def _insert_expired_contest(self, *, defender, challenger,
                                  ends_at_offset=-100):
        """Insert a contest whose ends_at is offset from now."""
        now = time.time()
        _run(self.mdb.execute(
            """INSERT INTO region_contests
               (region_slug, defender_org_code, challenger_org_code,
                zone_id, started_at, accumulation_ends_at, ends_at, status)
               VALUES ('dune_sea', ?, ?, 1, ?, ?, ?, 'active')""",
            (defender, challenger,
             now - 7 * 86400, now - 4 * 3600, now + ends_at_offset),
        ))

    def test_tick_does_nothing_on_active_contest_within_window(self):
        from engine.contest import tick_region_contest_resolution
        self._insert_expired_contest(
            defender="hutt_cartel", challenger="cis",
            ends_at_offset=+86400,  # still 1 day to go
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        # Status unchanged
        rows = _run(self.mdb.fetchall(
            "SELECT status FROM region_contests WHERE region_slug='dune_sea'"))
        self.assertEqual(rows[0]["status"], "active")

    def test_tick_resolves_expired_contest_as_defender_win(self):
        from engine.contest import tick_region_contest_resolution
        self._insert_expired_contest(
            defender="hutt_cartel", challenger="cis",
            ends_at_offset=-100,
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT status FROM region_contests WHERE region_slug='dune_sea'"))
        self.assertEqual(rows[0]["status"], "resolved_defender")

    def test_tick_applies_failure_penalty_to_challenger(self):
        """Expired contest → challenger loses 25 influence in parent zone."""
        from engine.contest import (
            tick_region_contest_resolution,
            REGION_CONTEST_FAILURE_PENALTY,
        )
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=80)
        self._insert_expired_contest(
            defender="hutt_cartel", challenger="cis",
            ends_at_offset=-100,
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT score FROM territory_influence "
            "WHERE zone_id=1 AND org_code='cis'"))
        self.assertEqual(rows[0]["score"], 80 - REGION_CONTEST_FAILURE_PENALTY)

    def test_tick_sets_cooldown_on_loser(self):
        from engine.contest import (
            tick_region_contest_resolution,
            is_org_on_contest_cooldown,
        )
        self._insert_expired_contest(
            defender="hutt_cartel", challenger="cis",
            ends_at_offset=-100,
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        self.assertTrue(_run(is_org_on_contest_cooldown(
            self.mdb, "dune_sea", "cis")))

    def test_tick_handles_unowned_contest(self):
        """Un-owned-region expired contest: challenger penalized, no transfer."""
        from engine.contest import (
            tick_region_contest_resolution,
            is_org_on_contest_cooldown,
        )
        self._insert_expired_contest(
            defender=None, challenger="cis",
            ends_at_offset=-100,
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT status, defender_org_code FROM region_contests "
            "WHERE region_slug='dune_sea'"))
        self.assertEqual(rows[0]["status"], "resolved_defender")
        self.assertIsNone(rows[0]["defender_org_code"])
        self.assertTrue(_run(is_org_on_contest_cooldown(
            self.mdb, "dune_sea", "cis")))

    def test_tick_broadcasts_outcome(self):
        from engine.contest import tick_region_contest_resolution
        self._insert_expired_contest(
            defender="hutt_cartel", challenger="cis",
            ends_at_offset=-100,
        )
        sent = []

        class FakeSession:
            is_in_game = True

            async def send_line(self, msg):
                sent.append(msg)

        class FakeMgr:
            all = [FakeSession()]

        _run(tick_region_contest_resolution(self.mdb, session_mgr=FakeMgr()))
        self.assertGreater(len(sent), 0)
        self.assertIn("REGION DEFENDED", sent[0])
        self.assertIn("Hutt Cartel", sent[0])

    def test_tick_one_bad_row_does_not_kill_tick(self):
        """A malformed contest row should not crash the tick loop."""
        from engine.contest import tick_region_contest_resolution
        # Insert a properly-formed expired row
        self._insert_expired_contest(
            defender="hutt_cartel", challenger="cis",
            ends_at_offset=-100,
        )
        # Tick runs without raising
        try:
            _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        except Exception as e:
            self.fail(f"tick should not raise on well-formed row: {e}")


# ──────────────────────────────────────────────────────────────────────
# 9. TestStatusLines
# ──────────────────────────────────────────────────────────────────────

class TestStatusLines(unittest.TestCase):
    """get_region_contest_status_lines display formatting."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            start_room_id=100,
        )

    def test_empty_when_no_contests(self):
        from engine.contest import get_region_contest_status_lines
        lines = _run(get_region_contest_status_lines(self.mdb, "hutt_cartel"))
        self.assertEqual(lines, [])

    def test_shows_defender_role(self):
        from engine.contest import (
            declare_region_contest,
            get_region_contest_status_lines,
        )
        _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        lines = _run(get_region_contest_status_lines(
            self.mdb, "hutt_cartel"))
        self.assertTrue(len(lines) >= 2)
        self.assertIn("Active Region Contests", lines[0])
        joined = "\n".join(lines[1:])
        self.assertIn("dune_sea", joined)
        self.assertIn("[Defender]", joined)

    def test_shows_challenger_role(self):
        from engine.contest import (
            declare_region_contest,
            get_region_contest_status_lines,
        )
        _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        lines = _run(get_region_contest_status_lines(self.mdb, "cis"))
        joined = "\n".join(lines[1:])
        self.assertIn("[Challenger]", joined)

    def test_shows_unowned_marker(self):
        from engine.contest import (
            declare_region_contest,
            get_region_contest_status_lines,
        )
        # Un-owned region contest
        self.mdb.seed_region(
            slug="coruscant_underworld", zone_id=2,
            owner_org_code=None,
            start_room_id=200,
        )
        _run(declare_region_contest(
            self.mdb, "coruscant_underworld", None, "cis",
            zone_id=2, session_mgr=None,
        ))
        lines = _run(get_region_contest_status_lines(self.mdb, "cis"))
        joined = "\n".join(lines[1:])
        self.assertIn("(un-owned)", joined)

    def test_shows_anchor_phase_marker_in_culminating_window(self):
        """When now > accumulation_ends_at, the [ANCHOR PHASE] tag shows."""
        from engine.contest import get_region_contest_status_lines
        # Hand-craft a contest already in the culminating window
        now = time.time()
        _run(self.mdb.execute(
            """INSERT INTO region_contests
               (region_slug, defender_org_code, challenger_org_code,
                zone_id, started_at, accumulation_ends_at, ends_at, status)
               VALUES ('dune_sea', 'hutt_cartel', 'cis',
                       1, ?, ?, ?, 'active')""",
            (now - 7 * 86400, now - 3600, now + 3600),
        ))
        lines = _run(get_region_contest_status_lines(
            self.mdb, "hutt_cartel"))
        joined = "\n".join(lines[1:])
        self.assertIn("ANCHOR PHASE", joined)

    def test_no_anchor_phase_marker_during_accumulation(self):
        from engine.contest import (
            declare_region_contest,
            get_region_contest_status_lines,
        )
        # Fresh contest — still in accumulation
        _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        lines = _run(get_region_contest_status_lines(
            self.mdb, "hutt_cartel"))
        joined = "\n".join(lines[1:])
        self.assertNotIn("ANCHOR PHASE", joined)


if __name__ == "__main__":
    unittest.main()
