# -*- coding: utf-8 -*-
"""
tests/test_syn5_espionage_as_influence.py — SYN.5 (2026-05-25).

Pins:
  * engine/intel_handlers.py (new) — quality heuristic, reward
    sampling, handler NPC resolution, handover entry point.
  * engine/territory.py — on_npc_kill / on_mission_complete /
    on_pvp_kill retargeted to wilderness-only influence per
    contestable_wilderness_design_v2.md §2.7.

Test sections
─────────────
  1. TestExtractMentionedRegions    — pure helper
  2. TestEvaluateIntelQuality       — heuristic boundaries
  3. TestSampleIntelReward          — tier-bounded RNG
  4. TestHandlerNpcResolution       — _is_handler_npc + find_handler_in_room
  5. TestHandoverIntelHappyPath     — successful redemption
  6. TestHandoverIntelRejections    — each error branch
  7. TestInfluenceHooksRetarget     — on_npc_kill / mission / pvp
                                      wilderness gate
  8. TestConstantsAndShape          — module-level invariants
"""
from __future__ import annotations

import asyncio
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
# In-memory DB stand-in
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
            CREATE TABLE memberships (
                char_id INTEGER NOT NULL,
                org_id INTEGER NOT NULL,
                rank_level INTEGER DEFAULT 1,
                PRIMARY KEY (char_id, org_id)
            );
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                attributes TEXT DEFAULT '{}',
                credits INTEGER DEFAULT 0
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
            CREATE TABLE region_garrison (
                region_slug TEXT NOT NULL,
                npc_id INTEGER NOT NULL,
                PRIMARY KEY (region_slug, npc_id)
            );
        """)
        self._db._conn.commit()

    # raw SQL
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

    async def get_npc(self, npc_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE id = ?", (npc_id,))
        return dict(rows[0]) if rows else None

    async def get_character(self, char_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE id = ?", (char_id,))
        return dict(rows[0]) if rows else None

    async def get_organization(self, org_code):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM organizations WHERE code = ?", (org_code,))
        return dict(rows[0]) if rows else None

    async def adjust_credits(self, char_id, delta, source, **kwargs):
        # Drop-1 ledger chokepoint shim: mirror Database.adjust_credits
        # enough for tests (atomic increment + return new balance).
        # char_id == 0 is a system faucet/sink with no row to touch.
        if char_id == 0:
            return 0
        await self._db.execute(
            "UPDATE characters SET credits = credits + ? WHERE id = ?",
            (delta, char_id))
        await self._db.commit()
        rows = await self._db.execute_fetchall(
            "SELECT credits FROM characters WHERE id = ?", (char_id,))
        return int(rows[0]["credits"]) if rows else 0

    async def save_character(self, char_id, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        params = list(kwargs.values()) + [char_id]
        await self._db.execute(
            f"UPDATE characters SET {cols} WHERE id = ?", params)
        await self._db.commit()

    # Seeds
    def seed_org(self, *, org_id, code, treasury=0):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name, treasury) "
            "VALUES (?, ?, ?, ?)",
            (org_id, code, code.title(), treasury))
        self._db._conn.commit()

    def seed_zone(self, *, zone_id=1, name="Tatooine"):
        self._db._conn.execute(
            "INSERT INTO zones (id, name) VALUES (?, ?)", (zone_id, name))
        self._db._conn.commit()

    def seed_room(self, *, room_id, zone_id=None, wilderness_region_id=None,
                   name="Room"):
        self._db._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) "
            "VALUES (?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id))
        self._db._conn.commit()

    def seed_handler(self, *, npc_id, room_id, faction, name=None):
        ai = json.dumps({"is_intel_handler": True, "faction": faction})
        self._db._conn.execute(
            "INSERT INTO npcs (id, name, room_id, ai_config_json) "
            "VALUES (?, ?, ?, ?)",
            (npc_id, name or f"Handler-{faction}", room_id, ai))
        self._db._conn.commit()

    def seed_character(self, *, char_id, faction="independent",
                        room_id=1, attributes=None, credits=0):
        if attributes is None:
            attributes = {}
        self._db._conn.execute(
            "INSERT INTO characters (id, name, attributes, credits) "
            "VALUES (?, ?, ?, ?)",
            (char_id, f"Char{char_id}", json.dumps(attributes), credits))
        self._db._conn.commit()


# ──────────────────────────────────────────────────────────────────────
# 1. TestExtractMentionedRegions (pure helper)
# ──────────────────────────────────────────────────────────────────────

class TestExtractMentionedRegions(unittest.TestCase):
    def test_no_text_returns_empty(self):
        from engine.intel_handlers import _extract_mentioned_regions
        self.assertEqual(_extract_mentioned_regions("", {"dune_sea"}), [])

    def test_no_known_regions_returns_empty(self):
        from engine.intel_handlers import _extract_mentioned_regions
        self.assertEqual(
            _extract_mentioned_regions("the dune sea is hot", set()),
            [])

    def test_exact_slug_match(self):
        from engine.intel_handlers import _extract_mentioned_regions
        self.assertEqual(
            _extract_mentioned_regions(
                "report from dune_sea", {"dune_sea", "swamp"}),
            ["dune_sea"])

    def test_spaced_form_match(self):
        from engine.intel_handlers import _extract_mentioned_regions
        self.assertEqual(
            _extract_mentioned_regions(
                "I saw movement in the Dune Sea last night.",
                {"dune_sea"}),
            ["dune_sea"])

    def test_multiple_mentions_first_order(self):
        from engine.intel_handlers import _extract_mentioned_regions
        # known set is unordered; the result preserves first-mention
        # order from the text.
        result = _extract_mentioned_regions(
            "First the Dune Sea, then the Coruscant Underworld",
            {"dune_sea", "coruscant_underworld"})
        self.assertEqual(result[0], "dune_sea")
        self.assertEqual(result[1], "coruscant_underworld")

    def test_unrelated_word_does_not_match(self):
        """'sea' alone shouldn't match 'dune_sea'."""
        from engine.intel_handlers import _extract_mentioned_regions
        self.assertEqual(
            _extract_mentioned_regions(
                "I saw a sea of sand.", {"dune_sea"}),
            [])


# ──────────────────────────────────────────────────────────────────────
# 2. TestEvaluateIntelQuality
# ──────────────────────────────────────────────────────────────────────

class TestEvaluateIntelQuality(unittest.TestCase):
    def _report(self, *, lines, created_at=None):
        if created_at is None:
            created_at = time.time()
        return {
            "id": 1,
            "title": "T",
            "lines": lines,
            "sealed": True,
            "created_at": created_at,
            "expires_at": created_at + 7 * 86400,
            "author": "Author",
        }

    def test_empty_report_low(self):
        from engine.intel_handlers import evaluate_intel_quality
        out = evaluate_intel_quality(None, set())
        self.assertEqual(out["quality"], "low")

    def test_vague_short_report_is_low(self):
        from engine.intel_handlers import evaluate_intel_quality
        report = self._report(lines=["something happened"])
        out = evaluate_intel_quality(report, {"dune_sea"})
        self.assertEqual(out["quality"], "low")
        self.assertIsNone(out["region_slug"])

    def test_specific_recent_report_is_high(self):
        """5 lines + region + recency + proper noun → high."""
        from engine.intel_handlers import evaluate_intel_quality
        report = self._report(lines=[
            "Major Tarkin Garrison spotted at dune_sea outpost.",
            "Two AT-AT walkers, four squads of stormtroopers.",
            "Commander Vren is leading the operation personally.",
            "They moved north from dune_sea at 0300 hours.",
            "Supply convoy expected within 48 hours.",
        ])
        out = evaluate_intel_quality(report, {"dune_sea"})
        self.assertEqual(out["quality"], "high",
                          msg=f"Score was {out['score']}")
        self.assertEqual(out["region_slug"], "dune_sea")

    def test_medium_substance(self):
        from engine.intel_handlers import evaluate_intel_quality
        report = self._report(lines=[
            "Activity in dune_sea outpost.",
            "Multiple guards posted.",
        ])
        out = evaluate_intel_quality(report, {"dune_sea"})
        # 2 lines + 1 region mention = 4 ⇒ medium
        self.assertEqual(out["quality"], "medium")
        self.assertEqual(out["region_slug"], "dune_sea")

    def test_stale_report_penalized(self):
        from engine.intel_handlers import evaluate_intel_quality
        # Created 5 days ago — past the 3-day stale window
        old = time.time() - 5 * 86400
        report = self._report(
            lines=["something something dune_sea"],
            created_at=old)
        out = evaluate_intel_quality(report, {"dune_sea"})
        # 1 line + 2 region + 0 (no freshness) - 1 (stale) = 2 ⇒ low
        self.assertEqual(out["quality"], "low")

    def test_no_region_means_no_region_slug(self):
        from engine.intel_handlers import evaluate_intel_quality
        report = self._report(lines=[
            "Big stuff happening.", "Lots of activity.",
            "More chatter.", "Even more.", "Final line."])
        out = evaluate_intel_quality(report, {"dune_sea"})
        self.assertIsNone(out["region_slug"])

    def test_score_is_clamped_at_zero(self):
        """Aggressively-stale empty report stays score ≥ 0."""
        from engine.intel_handlers import evaluate_intel_quality
        old = time.time() - 30 * 86400
        report = self._report(lines=[], created_at=old)
        out = evaluate_intel_quality(report, {"dune_sea"})
        self.assertGreaterEqual(out["score"], 0)
        self.assertEqual(out["quality"], "low")


# ──────────────────────────────────────────────────────────────────────
# 3. TestSampleIntelReward
# ──────────────────────────────────────────────────────────────────────

class TestSampleIntelReward(unittest.TestCase):
    def test_low_in_range(self):
        from engine.intel_handlers import (
            sample_intel_reward, INTEL_QUALITY_LOW,
        )
        min_inf, max_inf, min_cr, max_cr = INTEL_QUALITY_LOW
        # Sample many times to check bounds
        rng = random.Random(42)
        for _ in range(50):
            inf, cr = sample_intel_reward("low", rng=rng)
            self.assertGreaterEqual(inf, min_inf)
            self.assertLessEqual(inf, max_inf)
            self.assertGreaterEqual(cr, min_cr)
            self.assertLessEqual(cr, max_cr)

    def test_medium_in_range(self):
        from engine.intel_handlers import (
            sample_intel_reward, INTEL_QUALITY_MEDIUM,
        )
        min_inf, max_inf, min_cr, max_cr = INTEL_QUALITY_MEDIUM
        rng = random.Random(0)
        for _ in range(50):
            inf, cr = sample_intel_reward("medium", rng=rng)
            self.assertGreaterEqual(inf, min_inf)
            self.assertLessEqual(inf, max_inf)
            self.assertGreaterEqual(cr, min_cr)
            self.assertLessEqual(cr, max_cr)

    def test_high_in_range(self):
        from engine.intel_handlers import (
            sample_intel_reward, INTEL_QUALITY_HIGH,
        )
        min_inf, max_inf, min_cr, max_cr = INTEL_QUALITY_HIGH
        rng = random.Random(1)
        for _ in range(50):
            inf, cr = sample_intel_reward("high", rng=rng)
            self.assertGreaterEqual(inf, min_inf)
            self.assertLessEqual(inf, max_inf)
            self.assertGreaterEqual(cr, min_cr)
            self.assertLessEqual(cr, max_cr)

    def test_unknown_quality_falls_back_to_low(self):
        from engine.intel_handlers import (
            sample_intel_reward, INTEL_QUALITY_LOW,
        )
        min_inf, max_inf, _, _ = INTEL_QUALITY_LOW
        rng = random.Random(2)
        inf, cr = sample_intel_reward("garbage", rng=rng)
        self.assertGreaterEqual(inf, min_inf)
        self.assertLessEqual(inf, max_inf)


# ──────────────────────────────────────────────────────────────────────
# 4. TestHandlerNpcResolution
# ──────────────────────────────────────────────────────────────────────

class TestHandlerNpcResolution(unittest.TestCase):
    def test_non_handler_rejected(self):
        from engine.intel_handlers import _is_handler_npc
        npc = {"ai_config_json": json.dumps({"is_intel_handler": False})}
        self.assertFalse(_is_handler_npc(npc, "rebel"))

    def test_handler_without_faction_accepts_any(self):
        """Independent handler (no faction tag) takes intel from
        anyone."""
        from engine.intel_handlers import _is_handler_npc
        npc = {"ai_config_json": json.dumps({"is_intel_handler": True})}
        self.assertTrue(_is_handler_npc(npc, "rebel"))
        self.assertTrue(_is_handler_npc(npc, "empire"))

    def test_handler_matches_faction(self):
        from engine.intel_handlers import _is_handler_npc
        npc = {"ai_config_json":
                 json.dumps({"is_intel_handler": True, "faction": "rebel"})}
        self.assertTrue(_is_handler_npc(npc, "rebel"))

    def test_handler_rejects_wrong_faction(self):
        from engine.intel_handlers import _is_handler_npc
        npc = {"ai_config_json":
                 json.dumps({"is_intel_handler": True, "faction": "rebel"})}
        self.assertFalse(_is_handler_npc(npc, "empire"))

    def test_independent_string_faction_treated_as_independent(self):
        from engine.intel_handlers import _is_handler_npc
        npc = {"ai_config_json":
                 json.dumps({"is_intel_handler": True,
                              "faction": "independent"})}
        self.assertTrue(_is_handler_npc(npc, "hutt_cartel"))

    def test_find_handler_in_room_hit(self):
        from engine.intel_handlers import find_handler_in_room
        mdb = _MiniDB()
        mdb.seed_room(room_id=50)
        mdb.seed_handler(npc_id=100, room_id=50, faction="hutt_cartel")
        result = _run(find_handler_in_room(mdb, 50, "hutt_cartel"))
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 100)

    def test_find_handler_in_room_no_match(self):
        from engine.intel_handlers import find_handler_in_room
        mdb = _MiniDB()
        mdb.seed_room(room_id=50)
        mdb.seed_handler(npc_id=100, room_id=50, faction="hutt_cartel")
        # CIS char looking for a CIS handler — none in this room
        result = _run(find_handler_in_room(mdb, 50, "cis"))
        self.assertIsNone(result)

    def test_find_handler_in_room_malformed_ai_config_skipped(self):
        from engine.intel_handlers import find_handler_in_room
        mdb = _MiniDB()
        mdb.seed_room(room_id=50)
        # NPC with broken JSON in ai_config_json — should be skipped,
        # not crash
        mdb._db._conn.execute(
            "INSERT INTO npcs (id, name, room_id, ai_config_json) "
            "VALUES (200, 'Broken', 50, 'not json')")
        mdb._db._conn.commit()
        result = _run(find_handler_in_room(mdb, 50, "rebel"))
        self.assertIsNone(result)


# ──────────────────────────────────────────────────────────────────────
# 5. TestHandoverIntelHappyPath
# ──────────────────────────────────────────────────────────────────────

class TestHandoverIntelHappyPath(unittest.TestCase):
    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_org(org_id=1, code="hutt_cartel", treasury=0)
        # Region with one landmark room
        self.mdb.seed_room(room_id=100, zone_id=1,
                            wilderness_region_id="dune_sea",
                            name="Dune Sea Landmark")
        # Room where the handover happens (faction HQ city-map room)
        self.mdb.seed_room(room_id=50, zone_id=1, name="Hutt Palace")
        self.mdb.seed_handler(npc_id=999, room_id=50,
                                faction="hutt_cartel",
                                name="Vigo Sethel Vask")
        # Player with one sealed report describing the Dune Sea
        report = {
            "id": 7777,
            "title": "Recon Report",
            "lines": [
                "Republic patrols moving north through dune_sea.",
                "Commander Tarkin Vell leads the column.",
                "Two transports + four AT-RTs.",
                "Encampment near the Bone Wastes.",
                "Estimated arrival at outpost: 6 hours.",
            ],
            "sealed": True,
            "created_at": time.time(),
            "expires_at": time.time() + 7 * 86400,
            "author": "Spy",
        }
        attrs = {"intel_reports": [report]}
        self.mdb.seed_character(
            char_id=1, faction="hutt_cartel", room_id=50,
            attributes=attrs, credits=100)
        self.char = {
            "id": 1, "name": "Spy", "faction_id": "hutt_cartel",
            "room_id": 50, "credits": 100,
            "attributes": json.dumps(attrs),
        }
        self.report_id = 7777

    def test_happy_path_credits_and_influence(self):
        from engine.intel_handlers import handover_intel
        result = _run(handover_intel(
            self.mdb, self.char, 999, self.report_id,
            rng=random.Random(0)))
        self.assertTrue(result["ok"], msg=result.get("msg"))
        self.assertIn(result["quality"], ("low", "medium", "high"))
        self.assertEqual(result["region_slug"], "dune_sea")
        self.assertGreater(result["credits"], 0)
        # Influence was applied to parent zone
        rows = _run(self.mdb.fetchall(
            "SELECT score FROM territory_influence "
            "WHERE zone_id=1 AND org_code='hutt_cartel'"))
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(rows[0]["score"], result["influence"])
        # Character credits were updated
        rows = _run(self.mdb.fetchall(
            "SELECT credits FROM characters WHERE id = 1"))
        self.assertGreater(rows[0]["credits"], 100)

    def test_report_removed_from_holdings(self):
        from engine.intel_handlers import handover_intel
        from engine.espionage import get_intel_reports
        _run(handover_intel(self.mdb, self.char, 999, self.report_id,
                              rng=random.Random(0)))
        remaining = get_intel_reports(self.char)
        self.assertEqual(len(remaining), 0)

    def test_high_quality_yields_high_tier_reward(self):
        """The seeded 5-line + region + recent report should evaluate
        as 'high' quality and produce a reward in the 10-20 inf / 2000-
        5000 cr range."""
        from engine.intel_handlers import (
            handover_intel, INTEL_QUALITY_HIGH,
        )
        result = _run(handover_intel(
            self.mdb, self.char, 999, self.report_id,
            rng=random.Random(7)))
        self.assertEqual(result["quality"], "high")
        min_inf, max_inf, min_cr, max_cr = INTEL_QUALITY_HIGH
        self.assertGreaterEqual(result["credits"], min_cr)
        self.assertLessEqual(result["credits"], max_cr)
        self.assertGreaterEqual(result["influence"], min_inf)
        self.assertLessEqual(result["influence"], max_inf)


# ──────────────────────────────────────────────────────────────────────
# 6. TestHandoverIntelRejections
# ──────────────────────────────────────────────────────────────────────

class TestHandoverIntelRejections(unittest.TestCase):
    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_zone(zone_id=1)
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_org(org_id=2, code="cis")
        self.mdb.seed_room(room_id=50, zone_id=1)
        # Handler for hutt_cartel only
        self.mdb.seed_handler(npc_id=999, room_id=50,
                                faction="hutt_cartel")

    def _sealed_report(self, *, expires_offset=7 * 86400):
        return {
            "id": 1234, "title": "T", "lines": ["a", "b"],
            "sealed": True, "created_at": time.time(),
            "expires_at": time.time() + expires_offset,
            "author": "X",
        }

    def _draft_report(self):
        return {
            "id": 1234, "title": "T", "lines": ["a"],
            "sealed": False, "created_at": time.time(),
            "expires_at": time.time() + 7 * 86400,
            "author": "X",
        }

    def _set_char(self, *, faction, reports=None, room_id=50):
        attrs = {"intel_reports": reports or []}
        return {
            "id": 1, "name": "X", "faction_id": faction,
            "room_id": room_id,
            "attributes": json.dumps(attrs),
            "credits": 0,
        }

    def test_independent_char_rejected(self):
        from engine.intel_handlers import handover_intel
        char = self._set_char(
            faction="independent", reports=[self._sealed_report()])
        self.mdb.seed_character(char_id=1, faction="independent",
                                  attributes={"intel_reports": [self._sealed_report()]})
        result = _run(handover_intel(self.mdb, char, 999, 1234))
        self.assertFalse(result["ok"])
        self.assertIn("faction", result["msg"].lower())

    def test_missing_handler(self):
        from engine.intel_handlers import handover_intel
        char = self._set_char(
            faction="hutt_cartel", reports=[self._sealed_report()])
        self.mdb.seed_character(char_id=1, faction="hutt_cartel")
        result = _run(handover_intel(self.mdb, char, 99999, 1234))
        self.assertFalse(result["ok"])

    def test_wrong_faction_handler(self):
        """CIS char approaching a hutt_cartel handler is rejected."""
        from engine.intel_handlers import handover_intel
        char = self._set_char(
            faction="cis", reports=[self._sealed_report()])
        self.mdb.seed_character(char_id=1, faction="cis")
        result = _run(handover_intel(self.mdb, char, 999, 1234))
        self.assertFalse(result["ok"])
        self.assertIn("faction", result["msg"].lower())

    def test_handler_in_different_room(self):
        from engine.intel_handlers import handover_intel
        char = self._set_char(
            faction="hutt_cartel", reports=[self._sealed_report()],
            room_id=999)  # different room
        self.mdb.seed_character(char_id=1, faction="hutt_cartel")
        result = _run(handover_intel(self.mdb, char, 999, 1234))
        self.assertFalse(result["ok"])
        self.assertIn("here", result["msg"].lower())

    def test_unknown_report_id(self):
        from engine.intel_handlers import handover_intel
        char = self._set_char(
            faction="hutt_cartel", reports=[self._sealed_report()])
        self.mdb.seed_character(char_id=1, faction="hutt_cartel")
        result = _run(handover_intel(self.mdb, char, 999, 99999))
        self.assertFalse(result["ok"])
        self.assertIn("don't have", result["msg"].lower())

    def test_unsealed_draft_rejected(self):
        from engine.intel_handlers import handover_intel
        char = self._set_char(
            faction="hutt_cartel", reports=[self._draft_report()])
        self.mdb.seed_character(char_id=1, faction="hutt_cartel")
        result = _run(handover_intel(self.mdb, char, 999, 1234))
        self.assertFalse(result["ok"])
        self.assertIn("draft", result["msg"].lower())

    def test_expired_report_rejected(self):
        from engine.intel_handlers import handover_intel
        char = self._set_char(
            faction="hutt_cartel",
            reports=[self._sealed_report(expires_offset=-100)])
        self.mdb.seed_character(char_id=1, faction="hutt_cartel")
        result = _run(handover_intel(self.mdb, char, 999, 1234))
        self.assertFalse(result["ok"])
        self.assertIn("expired", result["msg"].lower())


# ──────────────────────────────────────────────────────────────────────
# 7. TestInfluenceHooksRetarget
# ──────────────────────────────────────────────────────────────────────

class TestInfluenceHooksRetarget(unittest.TestCase):
    """SYN.5 retarget: city-map rooms grant zero influence;
    wilderness rooms grant the design-table delta."""

    def setUp(self):
        self.mdb = _MiniDB()
        self.mdb.seed_zone(zone_id=1)
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        # City-map room (no wilderness_region_id)
        self.mdb.seed_room(room_id=10, zone_id=1, name="Mos Eisley")
        # Wilderness landmark room
        self.mdb.seed_room(room_id=100, zone_id=1,
                            wilderness_region_id="dune_sea",
                            name="Dune Sea Landmark")

    def _zone_influence(self, org_code="hutt_cartel", zone_id=1):
        rows = _run(self.mdb.fetchall(
            "SELECT score FROM territory_influence "
            "WHERE zone_id=? AND org_code=?", (zone_id, org_code)))
        return rows[0]["score"] if rows else 0

    def test_npc_kill_city_room_no_influence(self):
        from engine.territory import on_npc_kill
        char = {"id": 1, "name": "X", "faction_id": "hutt_cartel"}
        _run(on_npc_kill(self.mdb, char, 10))
        self.assertEqual(self._zone_influence(), 0)

    def test_npc_kill_wilderness_grants_influence(self):
        from engine.territory import on_npc_kill, INFLUENCE_NPC_KILL
        char = {"id": 1, "name": "X", "faction_id": "hutt_cartel"}
        _run(on_npc_kill(self.mdb, char, 100))
        self.assertEqual(self._zone_influence(), INFLUENCE_NPC_KILL)

    def test_mission_city_room_no_influence(self):
        from engine.territory import on_mission_complete
        char = {"id": 1, "name": "X", "faction_id": "hutt_cartel"}
        _run(on_mission_complete(self.mdb, char, 10))
        self.assertEqual(self._zone_influence(), 0)

    def test_mission_wilderness_grants_influence(self):
        from engine.territory import (
            on_mission_complete, INFLUENCE_MISSION,
        )
        char = {"id": 1, "name": "X", "faction_id": "hutt_cartel"}
        _run(on_mission_complete(self.mdb, char, 100))
        self.assertEqual(self._zone_influence(), INFLUENCE_MISSION)

    def test_pvp_city_room_no_influence(self):
        from engine.territory import on_pvp_kill
        self.mdb.seed_org(org_id=2, code="cis")
        winner = {"id": 1, "faction_id": "hutt_cartel"}
        loser = {"id": 2, "faction_id": "cis"}
        _run(on_pvp_kill(self.mdb, winner, loser, 10))
        self.assertEqual(self._zone_influence("hutt_cartel"), 0)
        self.assertEqual(self._zone_influence("cis"), 0)

    def test_pvp_wilderness_grants_influence_to_winner(self):
        from engine.territory import on_pvp_kill, INFLUENCE_PVP_WIN
        self.mdb.seed_org(org_id=2, code="cis")
        winner = {"id": 1, "faction_id": "hutt_cartel"}
        loser = {"id": 2, "faction_id": "cis"}
        _run(on_pvp_kill(self.mdb, winner, loser, 100))
        self.assertEqual(self._zone_influence("hutt_cartel"),
                          INFLUENCE_PVP_WIN)

    def test_pvp_wilderness_penalizes_loser(self):
        from engine.territory import on_pvp_kill
        self.mdb.seed_org(org_id=2, code="cis")
        # Seed cis at 50 so the -5 has somewhere to go
        _run(self.mdb.execute(
            "INSERT INTO territory_influence "
            "(zone_id, org_code, score, last_activity, last_presence) "
            "VALUES (1, 'cis', 50, 0, 0)"))
        winner = {"id": 1, "faction_id": "hutt_cartel"}
        loser = {"id": 2, "faction_id": "cis"}
        _run(on_pvp_kill(self.mdb, winner, loser, 100))
        self.assertEqual(self._zone_influence("cis"), 45)

    def test_independent_attacker_npc_kill_skipped(self):
        from engine.territory import on_npc_kill
        char = {"id": 1, "faction_id": "independent"}
        _run(on_npc_kill(self.mdb, char, 100))
        self.assertEqual(self._zone_influence(), 0)

    def test_orphan_zone_id_npc_kill_safe(self):
        """A wilderness room with NULL zone_id is a defensive skip."""
        from engine.territory import on_npc_kill
        self.mdb.seed_room(
            room_id=200, zone_id=None,
            wilderness_region_id="orphan_region")
        char = {"id": 1, "faction_id": "hutt_cartel"}
        _run(on_npc_kill(self.mdb, char, 200))
        self.assertEqual(self._zone_influence(), 0)


# ──────────────────────────────────────────────────────────────────────
# 8. TestConstantsAndShape
# ──────────────────────────────────────────────────────────────────────

class TestConstantsAndShape(unittest.TestCase):
    """Module-level invariants."""

    def test_quality_tier_constants_match_design(self):
        from engine.intel_handlers import (
            INTEL_QUALITY_LOW, INTEL_QUALITY_MEDIUM, INTEL_QUALITY_HIGH,
        )
        # Per design v2 §2.7:
        # Low:    1-3 inf + 200-500 cr
        # Medium: 4-8 inf + 600-1500 cr
        # High:   10-20 inf + 2000-5000 cr
        self.assertEqual(INTEL_QUALITY_LOW,    (1, 3, 200, 500))
        self.assertEqual(INTEL_QUALITY_MEDIUM, (4, 8, 600, 1500))
        self.assertEqual(INTEL_QUALITY_HIGH,   (10, 20, 2000, 5000))

    def test_handler_ai_key(self):
        from engine.intel_handlers import INTEL_HANDLER_AI_KEY
        self.assertEqual(INTEL_HANDLER_AI_KEY, "is_intel_handler")

    def test_module_exports(self):
        from engine import intel_handlers
        for name in ("evaluate_intel_quality",
                     "sample_intel_reward",
                     "find_handler_in_room",
                     "handover_intel",
                     "INTEL_QUALITY_LOW",
                     "INTEL_QUALITY_MEDIUM",
                     "INTEL_QUALITY_HIGH",
                     "INTEL_HANDLER_AI_KEY"):
            self.assertIn(name, intel_handlers.__all__)


if __name__ == "__main__":
    unittest.main()
