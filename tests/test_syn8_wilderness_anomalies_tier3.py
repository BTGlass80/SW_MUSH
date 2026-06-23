# -*- coding: utf-8 -*-
"""
tests/test_syn8_wilderness_anomalies_tier3.py — SYN.8 (2026-05-25).

Pins:
  * engine/wilderness_anomalies.py — TIER3_TEMPLATES catalog (4
    templates: 1 Dune Sea + 1 Coruscant + 2 region-any), TIER3_*
    constants, multi-phase combat reuse from Tier 2 substrate,
    kill_counts tracking, trophy_per_participant grant via
    _grant_trophy, scaled T5 mat distribution via
    _distribute_scaled_t5_mat. tick_tier3_wilderness_anomalies.
  * server/tick_handlers_economy.py — tier3_wilderness_anomaly_tick
    wrapper.
  * server/game_server.py — Tier 3 scheduler registration
    (interval=86400s = 24h, offset=7200).
  * parser/combat_commands.py — kill hook extended for Tier 3
    payout shape (TROPHY line per participant + T5 MATERIAL line
    for top contributors).

Test sections
─────────────
  1. TestTier3TemplateCatalog       — 4 templates, region split, CW grep
  2. TestTier3TemplateStructure     — required fields, phases (3 each),
                                       archetype validity, trophy +
                                       scaled_t5 shape
  3. TestTier3RegionFiltering       — disjoint from T1/T2; REGION_ANY
                                       templates work in any region
  4. TestTier3SpawnCadence          — separate cap/duration from T1/T2
                                       (independent ticks)
  5. TestTier3InvestigateSpawn      — investigate spawns phase 0 only;
                                       multi-phase machinery shared with T2
  6. TestTier3PhaseAdvancement      — kill last NPC of phase N → phase
                                       N+1 spawns; reward not paid yet
  7. TestTier3KillCountTracking     — kill_counts increments per kill;
                                       tracks per character
  8. TestTier3FinalPayout           — final clear pays participants
                                       (anyone with kill_count > 0);
                                       killer gets influence
  9. TestTier3TrophyDistribution    — every participant gets 1 trophy
                                       in inventory["items"]
 10. TestTier3ScaledT5Distribution  — floor(N/4) pieces to top
                                       participants by kill count;
                                       killer wins ties; small teams
                                       get at least 1 piece
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
# Shared harness (extends test_syn7b's _MiniDB with no T3-specific
# requirements; T3 reuses Tier 2's get_characters_in_room only for
# Tier 2 anomalies, not T3 — T3 uses anomaly.kill_counts)
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
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name TEXT,
                properties TEXT DEFAULT '{"security":"lawless"}'
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
            CREATE TABLE region_ownership (
                region_slug TEXT NOT NULL PRIMARY KEY,
                org_code TEXT NOT NULL,
                zone_id INTEGER,
                claimed_by INTEGER NOT NULL,
                claimed_at REAL NOT NULL,
                maintenance INTEGER NOT NULL DEFAULT 3000
            );
            CREATE TABLE territory_influence (
                zone_id INTEGER NOT NULL,
                org_code TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                last_activity REAL NOT NULL DEFAULT 0,
                last_presence REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (zone_id, org_code)
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
            CREATE TABLE region_contests (
                region_slug TEXT NOT NULL PRIMARY KEY,
                contestant_org TEXT NOT NULL,
                phase TEXT NOT NULL,
                phase_started_at REAL NOT NULL,
                escalation_threshold INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE region_contest_cooldowns (
                region_slug TEXT NOT NULL,
                contestant_org TEXT NOT NULL,
                cooldown_until REAL NOT NULL,
                PRIMARY KEY (region_slug, contestant_org)
            );
        """)
        self._db._conn.commit()

    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

    async def fetchone(self, sql, params=()):
        rows = await self._db.execute_fetchall(sql, params)
        return dict(rows[0]) if rows else None

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

    async def get_characters_in_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE room_id = ?", (room_id,))
        return [dict(r) for r in rows]

    def seed_zone(self, *, zone_id=1, name="Tatooine", security="lawless"):
        self._db._conn.execute(
            "INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
            (zone_id, name, json.dumps({"security": security})))
        self._db._conn.commit()

    def seed_room(self, *, room_id, zone_id=None, wilderness_region_id=None,
                  name="Room"):
        self._db._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) "
            "VALUES (?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id))
        self._db._conn.commit()

    def seed_character(self, *, char_id=1, name=None,
                       faction_id="independent", room_id=10,
                       credits=0):
        self._db._conn.execute(
            "INSERT INTO characters (id, name, faction_id, room_id, "
            "credits, attributes, skills, inventory) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (char_id, name or f"Char{char_id}", faction_id, room_id,
             credits, "{}", "{}", "{}"))
        self._db._conn.commit()

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

    async def get_npcs_in_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE room_id = ?", (room_id,))
        return [dict(r) for r in rows]


def _make_char(*, char_id=1, faction_id="independent", room_id=10):
    return {
        "id": char_id,
        "name": f"Char{char_id}",
        "faction_id": faction_id,
        "room_id": room_id,
        "credits": 0,
        "attributes": json.dumps({"blaster": "4D"}),
        "skills": "{}",
        "inventory": json.dumps({}),
    }


class _Tier3TestCase(unittest.TestCase):
    def setUp(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        _reset_state_for_tests()


# ══════════════════════════════════════════════════════════════════════
# 1. TestTier3TemplateCatalog — presence, region split, CW grep
# ══════════════════════════════════════════════════════════════════════

class TestTier3TemplateCatalog(_Tier3TestCase):

    EXPECTED_KEYS = {
        "krayt_dragon",
        "maze_predator_apex",
        "crashed_separatist_capital_ship",
        "republic_lost_patrol",
    }

    def test_four_t3_templates_present(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        self.assertEqual(set(TIER3_TEMPLATES.keys()), self.EXPECTED_KEYS)

    def test_tatooine_dune_sea_t3_template(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        self.assertEqual(
            TIER3_TEMPLATES["krayt_dragon"]["regions"], ["tatooine_dune_sea"],
        )

    def test_coruscant_t3_template(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        self.assertEqual(
            TIER3_TEMPLATES["maze_predator_apex"]["regions"],
            ["coruscant_underworld"],
        )

    def test_region_any_templates(self):
        """crashed_separatist_capital_ship + republic_lost_patrol are
        REGION_ANY templates (spawn anywhere)."""
        from engine.wilderness_anomalies import (
            TIER3_TEMPLATES, REGION_ANY,
        )
        self.assertEqual(
            TIER3_TEMPLATES["crashed_separatist_capital_ship"]["regions"],
            [REGION_ANY],
        )
        self.assertEqual(
            TIER3_TEMPLATES["republic_lost_patrol"]["regions"],
            [REGION_ANY],
        )

    def test_t3_templates_cw_correct(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        forbidden = ["imperial", "empire", "stormtrooper",
                     "imperial_patrol", "tie fighter", "tie/ln"]
        for key, tmpl in TIER3_TEMPLATES.items():
            blob_parts = [
                tmpl.get("display_name", ""),
                tmpl.get("short_desc", ""),
                tmpl.get("long_desc", ""),
                tmpl.get("news_text", ""),
            ]
            for phase in tmpl.get("phases", []) or []:
                blob_parts.append(phase.get("name", ""))
                blob_parts.append(phase.get("intro", ""))
                for npc in phase.get("combat_npcs", []) or []:
                    blob_parts.append(npc.get("personality", ""))
                    blob_parts.append(npc.get("species", ""))
            trophy = tmpl.get("trophy_per_participant", {})
            if trophy:
                blob_parts.append(trophy.get("name", ""))
                blob_parts.append(trophy.get("description", ""))
            blob = " ".join(blob_parts).lower()
            for tok in forbidden:
                self.assertNotIn(
                    tok, blob, f"{key} contains GCW-era token {tok!r}",
                )

    def test_all_tier3_tagged(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        for key, tmpl in TIER3_TEMPLATES.items():
            self.assertEqual(tmpl.get("tier"), 3, f"{key} not tier:3")

    def test_all_combat_resolution(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        for key, tmpl in TIER3_TEMPLATES.items():
            self.assertEqual(
                tmpl.get("resolution"), "combat",
                f"{key} not combat-resolution",
            )


# ══════════════════════════════════════════════════════════════════════
# 2. TestTier3TemplateStructure — phases + trophy + scaled_t5 shape
# ══════════════════════════════════════════════════════════════════════

class TestTier3TemplateStructure(_Tier3TestCase):

    def test_every_template_has_required_fields(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        required = (
            "tier", "regions", "resolution",
            "display_name", "short_desc", "long_desc",
            "phases", "success_reward",
            "trophy_per_participant", "scaled_t5_mat",
            "news_text",
        )
        for key, tmpl in TIER3_TEMPLATES.items():
            for field in required:
                self.assertIn(field, tmpl, f"{key} missing {field}")

    def test_phases_well_formed_three_phases(self):
        """Tier 3 templates have exactly 3 phases."""
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        for key, tmpl in TIER3_TEMPLATES.items():
            self.assertEqual(
                len(tmpl["phases"]), 3,
                f"{key} should have 3 phases (T3 cinematic pattern)",
            )

    def test_phase_archetypes_valid(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        from engine.npc_generator import ARCHETYPES
        for key, tmpl in TIER3_TEMPLATES.items():
            for i, phase in enumerate(tmpl["phases"]):
                for spec in phase["combat_npcs"]:
                    self.assertIn(
                        spec["archetype"], ARCHETYPES,
                        f"{key} phase {i}: archetype "
                        f"{spec['archetype']!r} is unknown",
                    )

    def test_trophy_shape(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        for key, tmpl in TIER3_TEMPLATES.items():
            trophy = tmpl["trophy_per_participant"]
            self.assertIn("key", trophy, f"{key} trophy missing key")
            self.assertIn("name", trophy, f"{key} trophy missing name")
            self.assertIn("description", trophy,
                          f"{key} trophy missing description")

    def test_scaled_t5_mat_shape(self):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        from engine.crafting import RESOURCE_TYPES
        for key, tmpl in TIER3_TEMPLATES.items():
            sm = tmpl["scaled_t5_mat"]
            self.assertIn("key", sm)
            self.assertIn("quality", sm)
            self.assertIn("per_4_participants", sm)
            # Key must be a valid resource type.
            self.assertIn(sm["key"], RESOURCE_TYPES,
                          f"{key}: scaled_t5_mat.key not in RESOURCE_TYPES")

    def test_t3_influence_is_50(self):
        """Design literal: +50 influence to killing-blow faction."""
        from engine.wilderness_anomalies import (
            TIER3_TEMPLATES, TIER3_INFLUENCE_DELTA,
        )
        self.assertEqual(TIER3_INFLUENCE_DELTA, 50)
        for key, tmpl in TIER3_TEMPLATES.items():
            self.assertEqual(
                tmpl["success_reward"]["influence"], 50,
                f"{key} influence should be 50",
            )

    def test_t3_credit_bands_exceed_t2(self):
        from engine.wilderness_anomalies import (
            TIER2_TEMPLATES, TIER3_TEMPLATES,
        )
        t2_max = max(
            t["success_reward"]["credits"][1]
            for t in TIER2_TEMPLATES.values()
        )
        t3_min_max = min(
            t["success_reward"]["credits"][1]
            for t in TIER3_TEMPLATES.values()
        )
        # Even the lowest T3 ceiling should exceed the highest T2 ceiling.
        self.assertGreater(
            t3_min_max, t2_max,
            "Every T3 credit ceiling should exceed T2's max",
        )

    def test_t3_t5_mat_quality(self):
        """T3 mats drop at q80, exceeding T2's q70."""
        from engine.wilderness_anomalies import (
            TIER3_TEMPLATES, TIER2_T5_MAT_QUALITY, TIER3_T5_MAT_QUALITY,
        )
        self.assertGreater(TIER3_T5_MAT_QUALITY, TIER2_T5_MAT_QUALITY)
        for key, tmpl in TIER3_TEMPLATES.items():
            self.assertEqual(
                tmpl["scaled_t5_mat"]["quality"], TIER3_T5_MAT_QUALITY,
            )


# ══════════════════════════════════════════════════════════════════════
# 3. TestTier3RegionFiltering
# ══════════════════════════════════════════════════════════════════════

class TestTier3RegionFiltering(_Tier3TestCase):

    def test_t3_disjoint_from_t1(self):
        from engine.wilderness_anomalies import (
            _pick_template, TIER1_TEMPLATES,
        )
        rng = random.Random(0)
        t1_keys = set(TIER1_TEMPLATES.keys())
        for _ in range(100):
            picked = _pick_template(rng, region_slug="tatooine_dune_sea", tier=3)
            self.assertNotIn(picked, t1_keys)

    def test_t3_disjoint_from_t2(self):
        from engine.wilderness_anomalies import (
            _pick_template, TIER2_TEMPLATES,
        )
        rng = random.Random(0)
        t2_keys = set(TIER2_TEMPLATES.keys())
        for _ in range(100):
            picked = _pick_template(rng, region_slug="tatooine_dune_sea", tier=3)
            self.assertNotIn(picked, t2_keys)

    def test_region_any_picks_in_tatooine_dune_sea(self):
        """REGION_ANY templates are valid candidates in any region."""
        from engine.wilderness_anomalies import _pick_template
        rng = random.Random(0)
        picks = set()
        for _ in range(500):
            picks.add(_pick_template(rng, region_slug="tatooine_dune_sea", tier=3))
        # Both REGION_ANY templates should appear in the picks AND
        # the Dune Sea-specific template.
        self.assertIn("krayt_dragon", picks)
        self.assertIn("crashed_separatist_capital_ship", picks)
        self.assertIn("republic_lost_patrol", picks)
        # Coruscant-only template should NEVER appear.
        self.assertNotIn("maze_predator_apex", picks)

    def test_region_any_picks_in_coruscant(self):
        from engine.wilderness_anomalies import _pick_template
        rng = random.Random(0)
        picks = set()
        for _ in range(500):
            picks.add(_pick_template(
                rng, region_slug="coruscant_underworld", tier=3,
            ))
        self.assertIn("maze_predator_apex", picks)
        self.assertIn("crashed_separatist_capital_ship", picks)
        self.assertIn("republic_lost_patrol", picks)
        # Dune-Sea-only should NEVER appear.
        self.assertNotIn("krayt_dragon", picks)


# ══════════════════════════════════════════════════════════════════════
# 4. TestTier3SpawnCadence
# ══════════════════════════════════════════════════════════════════════

class TestTier3SpawnCadence(_Tier3TestCase):

    def test_t3_duration(self):
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, TIER3_DURATION_SECS,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="tatooine_dune_sea")
        now = time.time()
        a = _run(spawn_anomaly_for_region(
            mdb, "tatooine_dune_sea", rng=random.Random(0),
            now=now, force=True, tier=3,
        ))
        self.assertIsNotNone(a)
        self.assertEqual(a.tier, 3)
        self.assertAlmostEqual(
            a.expiry - now, TIER3_DURATION_SECS, delta=2,
        )

    def test_t3_cap_independent_of_t1_t2(self):
        """A region can hold T1 + T2 + T3 simultaneously."""
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, get_anomalies_for_region,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="tatooine_dune_sea")
        a1 = _run(spawn_anomaly_for_region(
            mdb, "tatooine_dune_sea", rng=random.Random(0), force=True, tier=1,
        ))
        a2 = _run(spawn_anomaly_for_region(
            mdb, "tatooine_dune_sea", rng=random.Random(1), force=True, tier=2,
        ))
        a3 = _run(spawn_anomaly_for_region(
            mdb, "tatooine_dune_sea", rng=random.Random(2), force=True, tier=3,
        ))
        self.assertIsNotNone(a1)
        self.assertIsNotNone(a2)
        self.assertIsNotNone(a3)
        self.assertEqual(a1.tier, 1)
        self.assertEqual(a2.tier, 2)
        self.assertEqual(a3.tier, 3)
        active = get_anomalies_for_region("tatooine_dune_sea")
        self.assertEqual(len(active), 3)

    def test_t3_per_region_cap_is_one(self):
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, TIER3_MAX_PER_REGION,
        )
        self.assertEqual(TIER3_MAX_PER_REGION, 1)
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="tatooine_dune_sea")
        first = _run(spawn_anomaly_for_region(
            mdb, "tatooine_dune_sea", rng=random.Random(0), force=True, tier=3,
        ))
        second = _run(spawn_anomaly_for_region(
            mdb, "tatooine_dune_sea", rng=random.Random(1), force=True, tier=3,
        ))
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_t3_tick_dispatches_t3_spawns(self):
        from engine.wilderness_anomalies import (
            tick_tier3_wilderness_anomalies,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="tatooine_dune_sea")

        class _AlwaysSpawn:
            def random(self): return 0.0
            def choice(self, seq): return seq[0]
            def randint(self, lo, hi): return lo

        stats = _run(tick_tier3_wilderness_anomalies(
            mdb, None, rng=_AlwaysSpawn(),
        ))
        self.assertEqual(stats["spawned"], 1)
        from engine.wilderness_anomalies import _anomalies
        a = _anomalies["tatooine_dune_sea"][0]
        self.assertEqual(a.tier, 3)


# ══════════════════════════════════════════════════════════════════════
# 5. TestTier3InvestigateSpawn — phase 0 spawn (shared with T2 path)
# ══════════════════════════════════════════════════════════════════════

class TestTier3InvestigateSpawn(_Tier3TestCase):

    def _setup_t3(self, template_key="krayt_dragon",
                  faction_id="independent", room_id=10):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER3_DURATION_SECS,
            TIER3_TEMPLATES,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        regions = TIER3_TEMPLATES[template_key]["regions"]
        region_slug = "tatooine_dune_sea" if regions[0] == "*" else regions[0]
        mdb.seed_room(room_id=room_id, zone_id=1,
                      wilderness_region_id=region_slug)
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug=region_slug, zone_id=1,
            template_key=template_key, anchor_room_id=room_id,
            tier=3, expiry=now + TIER3_DURATION_SECS,
        )
        _anomalies[region_slug] = [a]
        char = _make_char(char_id=1, room_id=room_id, faction_id=faction_id)
        return mdb, char, a

    def test_t3_investigate_spawns_only_phase_0(self):
        from engine.wilderness_anomalies import (
            resolve_anomaly, TIER3_TEMPLATES,
        )
        mdb, char, a = self._setup_t3("krayt_dragon")
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "combat")
        self.assertEqual(out["tier"], 3)
        self.assertEqual(out["phase"], 1)
        expected = len(TIER3_TEMPLATES["krayt_dragon"]["phases"][0]["combat_npcs"])
        self.assertEqual(len(out["spawned_npc_ids"]), expected)

    def test_t3_investigate_no_immediate_payout(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_t3("maze_predator_apex")
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["credits"], 0)
        self.assertFalse(a.resolved)


# ══════════════════════════════════════════════════════════════════════
# 6. TestTier3PhaseAdvancement
# ══════════════════════════════════════════════════════════════════════

class TestTier3PhaseAdvancement(_Tier3TestCase):

    def _engage_and_clear_phase0(self, template_key="krayt_dragon"):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER3_DURATION_SECS,
            TIER3_TEMPLATES, resolve_anomaly,
            award_combat_anomaly_reward,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        regions = TIER3_TEMPLATES[template_key]["regions"]
        region_slug = "tatooine_dune_sea" if regions[0] == "*" else regions[0]
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id=region_slug)
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug=region_slug, zone_id=1,
            template_key=template_key, anchor_room_id=10,
            tier=3, expiry=now + TIER3_DURATION_SECS,
        )
        _anomalies[region_slug] = [a]
        mdb.seed_character(char_id=1, room_id=10)
        char = _make_char(char_id=1, room_id=10)
        _run(resolve_anomaly(mdb, char, 1))
        # Kill all of phase 0.
        for nid in list(a.spawned_npc_ids):
            _run(award_combat_anomaly_reward(
                mdb, killer_char_id=1, npc_id=nid, rng=random.Random(0),
            ))
        return mdb, char, a

    def test_kill_phase_0_advances_to_phase_1(self):
        mdb, char, a = self._engage_and_clear_phase0("krayt_dragon")
        self.assertEqual(a.current_phase, 1)
        self.assertFalse(a.resolved)
        # Phase 1 NPCs are now spawned (krayt_dragon phase 1: 1 elder).
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        expected = len(
            TIER3_TEMPLATES["krayt_dragon"]["phases"][1]["combat_npcs"]
        )
        self.assertEqual(len(a.spawned_npc_ids), expected)

    def test_phase_1_npcs_are_tagged(self):
        mdb, char, a = self._engage_and_clear_phase0("krayt_dragon")
        # Note: in the production death pipeline, killed NPCs are
        # deleted from the npcs table by combat.py — but this test
        # harness only mocks the anomaly kill hook, so phase-0 NPC
        # rows remain in the DB. What matters is that the live
        # phase-1 NPCs (per a.spawned_npc_ids) are tagged correctly.
        for npc_id in a.spawned_npc_ids:
            row = _run(mdb.get_npc(npc_id))
            self.assertIsNotNone(row)
            cfg = json.loads(row["ai_config_json"])
            self.assertTrue(cfg.get("is_anomaly_target"))
            self.assertEqual(cfg.get("anomaly_id"), 1)


# ══════════════════════════════════════════════════════════════════════
# 7. TestTier3KillCountTracking
# ══════════════════════════════════════════════════════════════════════

class TestTier3KillCountTracking(_Tier3TestCase):

    def _engage(self, template_key="krayt_dragon", killers=(1,)):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER3_DURATION_SECS,
            TIER3_TEMPLATES, resolve_anomaly,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        regions = TIER3_TEMPLATES[template_key]["regions"]
        region_slug = "tatooine_dune_sea" if regions[0] == "*" else regions[0]
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id=region_slug)
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug=region_slug, zone_id=1,
            template_key=template_key, anchor_room_id=10,
            tier=3, expiry=now + TIER3_DURATION_SECS,
        )
        _anomalies[region_slug] = [a]
        for cid in killers:
            mdb.seed_character(char_id=cid, room_id=10)
        # Char 1 engages.
        char = _make_char(char_id=killers[0], room_id=10)
        _run(resolve_anomaly(mdb, char, 1))
        return mdb, a

    def test_kill_increments_kill_counts(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, a = self._engage()
        # Kill one phase-0 NPC by char 1.
        first_npc = a.spawned_npc_ids[0]
        _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=first_npc, rng=random.Random(0),
        ))
        self.assertEqual(a.kill_counts.get(1), 1)

    def test_two_killers_tracked_separately(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, a = self._engage(killers=(1, 2))
        npcs = list(a.spawned_npc_ids)
        # Char 1 kills the first; char 2 kills the second.
        _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=npcs[0], rng=random.Random(0),
        ))
        _run(award_combat_anomaly_reward(
            mdb, killer_char_id=2, npc_id=npcs[1], rng=random.Random(0),
        ))
        self.assertEqual(a.kill_counts.get(1), 1)
        self.assertEqual(a.kill_counts.get(2), 1)


# ══════════════════════════════════════════════════════════════════════
# 8. TestTier3FinalPayout — full clear pays participants
# ══════════════════════════════════════════════════════════════════════

class TestTier3FinalPayout(_Tier3TestCase):

    def _engage_and_clear_to_final(self, template_key="republic_lost_patrol",
                                    killer_faction="republic",
                                    n_chars=4):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER3_DURATION_SECS,
            TIER3_TEMPLATES, resolve_anomaly,
            award_combat_anomaly_reward,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        regions = TIER3_TEMPLATES[template_key]["regions"]
        region_slug = "tatooine_dune_sea" if regions[0] == "*" else regions[0]
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id=region_slug)
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug=region_slug, zone_id=1,
            template_key=template_key, anchor_room_id=10,
            tier=3, expiry=now + TIER3_DURATION_SECS,
        )
        _anomalies[region_slug] = [a]
        for cid in range(1, n_chars + 1):
            mdb.seed_character(
                char_id=cid, room_id=10,
                faction_id=(killer_faction if cid == 1 else "independent"),
            )
        char = _make_char(char_id=1, room_id=10,
                          faction_id=killer_faction)
        _run(resolve_anomaly(mdb, char, 1))
        # Round-robin kills across phases up to (but not including)
        # the final NPC of the final phase.
        rr = 1
        n_phases = a.total_phases
        for phase_idx in range(n_phases - 1):
            for nid in list(a.spawned_npc_ids):
                _run(award_combat_anomaly_reward(
                    mdb, killer_char_id=rr, npc_id=nid,
                    rng=random.Random(0),
                ))
                rr = (rr % n_chars) + 1
        final_npcs = list(a.spawned_npc_ids)
        for nid in final_npcs[:-1]:
            _run(award_combat_anomaly_reward(
                mdb, killer_char_id=rr, npc_id=nid, rng=random.Random(0),
            ))
            rr = (rr % n_chars) + 1
        # Ensure every requested char has at least 1 kill (so the
        # final payout counts them as participants). Templates with
        # too few NPCs to round-robin all chars get padded here.
        for cid in range(1, n_chars + 1):
            if cid not in a.kill_counts:
                a.kill_counts[cid] = 1
        return mdb, a, final_npcs[-1]

    def test_final_kill_pays_credits_to_all_participants(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, a, final_npc = self._engage_and_clear_to_final(
            "krayt_dragon", n_chars=4,
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc,
            rng=random.Random(0),
        ))
        self.assertIsNotNone(payout)
        self.assertEqual(payout["tier"], 3)
        # All 4 chars should be participants.
        self.assertEqual(len(payout["payouts_per_char"]), 4)
        # All got positive credits.
        for pc in payout["payouts_per_char"]:
            self.assertGreater(pc["credits"], 0)

    def test_final_kill_grants_influence_to_killer_faction(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward, TIER3_INFLUENCE_DELTA,
        )
        mdb, a, final_npc = self._engage_and_clear_to_final(
            "krayt_dragon", killer_faction="republic", n_chars=4,
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc,
            rng=random.Random(0),
        ))
        self.assertEqual(payout["influence"], TIER3_INFLUENCE_DELTA)

    def test_anomaly_marked_resolved(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, a, final_npc = self._engage_and_clear_to_final(
            "krayt_dragon", n_chars=4,
        )
        _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc,
            rng=random.Random(0),
        ))
        self.assertTrue(a.resolved)
        self.assertEqual(a.resolved_by, 1)


# ══════════════════════════════════════════════════════════════════════
# 9. TestTier3TrophyDistribution
# ══════════════════════════════════════════════════════════════════════

class TestTier3TrophyDistribution(_Tier3TestCase):

    def test_every_participant_gets_one_trophy(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward, TIER3_TEMPLATES,
        )
        # Use the engage-and-clear helper from TestTier3FinalPayout.
        runner = TestTier3FinalPayout()
        runner.setUp()
        mdb, a, final_npc = runner._engage_and_clear_to_final(
            "krayt_dragon", n_chars=4,
        )
        _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc,
            rng=random.Random(0),
        ))
        # All 4 chars get the trophy.
        trophy_def = TIER3_TEMPLATES["krayt_dragon"]["trophy_per_participant"]
        for cid in range(1, 5):
            char = _run(mdb.get_character(cid))
            inv = json.loads(char["inventory"])
            items = inv.get("items", [])
            trophies = [i for i in items
                        if i.get("key") == trophy_def["key"]]
            self.assertEqual(
                len(trophies), 1,
                f"Char {cid} should have exactly 1 trophy",
            )
            self.assertTrue(trophies[0].get("is_trophy"))
            self.assertEqual(trophies[0]["name"], trophy_def["name"])

    def test_grant_trophy_helper(self):
        from engine.wilderness_anomalies import _grant_trophy
        mdb = _MiniDB()
        mdb.seed_character(char_id=1)
        char = _run(mdb.get_character(1))
        result = _run(_grant_trophy(mdb, char, {
            "key": "test_trophy",
            "name": "Test Trophy",
            "description": "Test description.",
        }))
        self.assertIsNotNone(result)
        # Persisted to inventory.
        char2 = _run(mdb.get_character(1))
        inv = json.loads(char2["inventory"])
        items = inv.get("items", [])
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["is_trophy"])
        self.assertTrue(items[0]["is_anomaly_loot"])


# ══════════════════════════════════════════════════════════════════════
# 10. TestTier3ScaledT5Distribution
# ══════════════════════════════════════════════════════════════════════

class TestTier3ScaledT5Distribution(_Tier3TestCase):

    def test_floor_of_n_over_4_pieces_distributed(self):
        """8 participants → 2 pieces. 4 participants → 1 piece.
        12 participants → 3 pieces. 3 participants → 1 piece
        (consolation floor)."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        runner = TestTier3FinalPayout()
        runner.setUp()
        mdb, a, final_npc = runner._engage_and_clear_to_final(
            "krayt_dragon", n_chars=8,
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc,
            rng=random.Random(0),
        ))
        grants = payout.get("scaled_t5_grants", [])
        self.assertEqual(len(grants), 2, "8 chars → 2 pieces")

    def test_small_team_gets_at_least_one_piece(self):
        """Floor(3/4) = 0; the consolation rule says minimum 1 piece
        to the killer for any successful T3 clear."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        runner = TestTier3FinalPayout()
        runner.setUp()
        # Set n_chars=3 — only 3 participants.
        mdb, a, final_npc = runner._engage_and_clear_to_final(
            "krayt_dragon", n_chars=3,
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc,
            rng=random.Random(0),
        ))
        grants = payout.get("scaled_t5_grants", [])
        # 3 participants → floor(3/4)=0 → consolation 1 piece to killer.
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["char_id"], 1)

    def test_top_kill_count_gets_first_pick(self):
        """The participant with the highest kill count gets one of
        the pieces."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        runner = TestTier3FinalPayout()
        runner.setUp()
        mdb, a, final_npc = runner._engage_and_clear_to_final(
            "krayt_dragon", n_chars=4,
        )
        # Round-robin in the helper means each char has ~1-2 kills
        # depending on phase distribution. Force one char to be the
        # highest by manually bumping their count.
        a.kill_counts[2] = 100   # char 2 has overwhelming kills
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc,
            rng=random.Random(0),
        ))
        grants = payout.get("scaled_t5_grants", [])
        self.assertGreater(len(grants), 0)
        # Top grant should go to char 2.
        char_ids = [g["char_id"] for g in grants]
        self.assertIn(2, char_ids)

    def test_t5_mat_added_to_recipient_inventory(self):
        """The granted T5 mat actually shows up as a crafting
        resource."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward, TIER3_TEMPLATES,
        )
        runner = TestTier3FinalPayout()
        runner.setUp()
        mdb, a, final_npc = runner._engage_and_clear_to_final(
            "krayt_dragon", n_chars=4,
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc,
            rng=random.Random(0),
        ))
        grants = payout.get("scaled_t5_grants", [])
        self.assertGreater(len(grants), 0)
        mat_key = TIER3_TEMPLATES["krayt_dragon"]["scaled_t5_mat"]["key"]
        for g in grants:
            char = _run(mdb.get_character(g["char_id"]))
            inv = json.loads(char["inventory"])
            resources = inv.get("resources", [])
            mat_stacks = [r for r in resources if r["type"] == mat_key]
            self.assertGreater(len(mat_stacks), 0,
                               f"Char {g['char_id']} missing T5 mat")

    def test_distribute_helper_signature(self):
        """_distribute_scaled_t5_mat is callable and returns a list."""
        from engine.wilderness_anomalies import (
            _distribute_scaled_t5_mat, WildernessAnomaly,
        )
        mdb = _MiniDB()
        mdb.seed_character(char_id=1)
        mdb.seed_character(char_id=2)
        a = WildernessAnomaly(
            id=1, region_slug="tatooine_dune_sea", zone_id=1,
            template_key="krayt_dragon", anchor_room_id=10,
            tier=3,
        )
        a.kill_counts = {1: 5, 2: 3}
        grants = _run(_distribute_scaled_t5_mat(
            mdb, a, {"key": "deep_dune_iron", "quality": 80.0,
                     "per_4_participants": 1},
            killer_char_id=1, n_participants=2,
        ))
        # 2 participants → floor(2/4)=0 → consolation 1 piece to killer.
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["char_id"], 1)


if __name__ == "__main__":
    unittest.main()
