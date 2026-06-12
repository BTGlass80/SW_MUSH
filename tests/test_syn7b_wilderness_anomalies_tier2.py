# -*- coding: utf-8 -*-
"""
tests/test_syn7b_wilderness_anomalies_tier2.py — SYN.7.b (2026-05-25).

Pins:
  * engine/wilderness_anomalies.py — TIER2_TEMPLATES catalog (5
    templates: 3 Dune Sea + 2 Coruscant Underworld), TIER2_*
    constants, multi-phase combat resolution via new helpers
    (_spawn_combat_npcs, _advance_to_next_phase), multi-player
    Tier 2 payout via _payout_combat_anomaly, named loot grants
    via _grant_named_loot, tick_tier2_wilderness_anomalies.
  * server/tick_handlers_economy.py — tier2_wilderness_anomaly_tick
    wrapper.
  * server/game_server.py — Tier 2 scheduler registration (interval
    21600s = 6h, offset 3300).
  * parser/combat_commands.py — kill hook extended for Tier 2
    payout shape (per-participant lines + named-loot line).

Test sections
─────────────
  1. TestTier2TemplateCatalog       — 5 templates, region split, CW grep
  2. TestTier2TemplateStructure     — required fields, phase shape,
                                       archetype validity, named_loot
                                       shape
  3. TestTier2RegionFiltering       — Dune Sea never picks Coruscant
                                       template and vice versa
  4. TestTier2SpawnCadence          — separate caps + chance + duration
                                       from Tier 1 (independent ticks)
  5. TestTier2InvestigateSpawn      — investigate spawns phase 0 only
  6. TestTier2PhaseAdvancement      — kill last NPC of phase N → phase
                                       N+1 spawns; reward not paid yet
  7. TestTier2FinalPhasePayout      — last phase clears → all room
                                       occupants get credits/resources;
                                       killer gets influence + named loot
  8. TestTier2NamedLoot             — resource named loot adds to
                                       crafting resources; item named
                                       loot adds to inventory items list
  9. TestTier2MultiParticipant      — 2 chars in room, both get split
                                       credits; only killer gets influence
                                       and named loot
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
# Shared harness (mirrors test_syn7a_wilderness_anomalies.py, with
# get_characters_in_room added for Tier 2 multi-participant payouts)
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
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT,
                treasury INTEGER DEFAULT 0
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
        """SYN.7.b: commit hook for adjust_territory_influence."""
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

    # SYN.7.b: Tier 2 multi-participant payouts need to find all
    # characters in the anchor room.
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
                  name="Room", properties=None):
        props_json = json.dumps(properties) if properties else None
        self._db._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id, "
            "properties) VALUES (?, ?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id, props_json))
        self._db._conn.commit()

    def seed_character(self, *, char_id=1, name=None,
                       faction_id="independent", room_id=10,
                       credits=0, skills=None, inventory=None):
        if skills is None:
            skills = {}
        if inventory is None:
            inventory = {}
        self._db._conn.execute(
            "INSERT INTO characters (id, name, faction_id, room_id, "
            "credits, attributes, skills, inventory) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (char_id, name or f"Char{char_id}", faction_id, room_id,
             credits, json.dumps({"survival": "3D"}),
             json.dumps(skills), json.dumps(inventory)))
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


def _make_char(*, char_id=1, faction_id="independent",
               room_id=10, skills=None):
    if skills is None:
        skills = {}
    return {
        "id": char_id,
        "name": f"Char{char_id}",
        "faction_id": faction_id,
        "room_id": room_id,
        "credits": 0,
        "attributes": json.dumps({"survival": "3D", "blaster": "3D"}),
        "skills": json.dumps(skills),
        "inventory": json.dumps({}),
    }


class _Tier2TestCase(unittest.TestCase):
    """Base class that resets module state between tests."""
    def setUp(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        _reset_state_for_tests()


# ══════════════════════════════════════════════════════════════════════
# 1. TestTier2TemplateCatalog — presence, region split, CW grep
# ══════════════════════════════════════════════════════════════════════

class TestTier2TemplateCatalog(_Tier2TestCase):

    EXPECTED_KEYS = {
        # Dune Sea (3)
        "downed_republic_acclamator",
        "hutt_smuggling_convoy",
        "cis_commando_deployment",
        # Coruscant Underworld (2 — region parity per SYN.7.a.fix)
        "maze_predator_outbreak",
        "coruscant_gang_war",
    }

    def test_five_t2_templates_present(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        self.assertEqual(set(TIER2_TEMPLATES.keys()), self.EXPECTED_KEYS)

    def test_dune_sea_t2_templates(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        dune = {k for k, v in TIER2_TEMPLATES.items()
                if "dune_sea" in v["regions"]}
        self.assertEqual(dune, {
            "downed_republic_acclamator",
            "hutt_smuggling_convoy",
            "cis_commando_deployment",
        })

    def test_coruscant_t2_templates(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        coru = {k for k, v in TIER2_TEMPLATES.items()
                if "coruscant_underworld" in v["regions"]}
        self.assertEqual(coru, {
            "maze_predator_outbreak",
            "coruscant_gang_war",
        })

    def test_t2_templates_cw_correct(self):
        """No GCW residue. The original design doc says 'Imperial
        corvette stranded' — this drop ships it as
        'downed_republic_acclamator' explicitly per the CW pivot."""
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        forbidden = ["imperial", "empire", "stormtrooper",
                     "imperial_patrol", "tie fighter", "tie/ln"]
        for key, tmpl in TIER2_TEMPLATES.items():
            blob_parts = [
                tmpl.get("display_name", ""),
                tmpl.get("short_desc", ""),
                tmpl.get("long_desc", ""),
                tmpl.get("news_text", ""),
            ]
            # Include phase intros + npc spec descriptions
            for phase in tmpl.get("phases", []) or []:
                blob_parts.append(phase.get("name", ""))
                blob_parts.append(phase.get("intro", ""))
                for npc in phase.get("combat_npcs", []) or []:
                    blob_parts.append(npc.get("personality", ""))
                    blob_parts.append(npc.get("species", ""))
            blob = " ".join(blob_parts).lower()
            for tok in forbidden:
                self.assertNotIn(
                    tok, blob,
                    f"{key} contains GCW-era token {tok!r}",
                )

    def test_t2_templates_all_tagged_tier_2(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        for key, tmpl in TIER2_TEMPLATES.items():
            self.assertEqual(
                tmpl.get("tier"), 2,
                f"{key} missing tier:2 tag",
            )

    def test_t2_templates_all_combat_resolution(self):
        """Tier 2 is always combat — there are no skill-check
        Tier 2 templates."""
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        for key, tmpl in TIER2_TEMPLATES.items():
            self.assertEqual(
                tmpl.get("resolution"), "combat",
                f"{key} is not combat-resolution",
            )


# ══════════════════════════════════════════════════════════════════════
# 2. TestTier2TemplateStructure — phases, archetypes, named_loot
# ══════════════════════════════════════════════════════════════════════

class TestTier2TemplateStructure(_Tier2TestCase):

    def test_every_t2_template_has_required_fields(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        required = (
            "tier", "regions", "resolution",
            "display_name", "short_desc", "long_desc",
            "phases", "success_reward", "news_text",
        )
        for key, tmpl in TIER2_TEMPLATES.items():
            for field in required:
                self.assertIn(field, tmpl, f"{key} missing {field}")

    def test_phases_are_well_formed(self):
        """Each phase has a name, intro, and non-empty combat_npcs."""
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        for key, tmpl in TIER2_TEMPLATES.items():
            phases = tmpl["phases"]
            self.assertGreaterEqual(
                len(phases), 2,
                f"{key} has fewer than 2 phases (Tier 2 needs multi-phase)",
            )
            for i, phase in enumerate(phases):
                self.assertIn("combat_npcs", phase,
                              f"{key} phase {i} missing combat_npcs")
                self.assertGreater(
                    len(phase["combat_npcs"]), 0,
                    f"{key} phase {i} has empty combat_npcs",
                )
                self.assertIn("name", phase,
                              f"{key} phase {i} missing name")
                self.assertIn("intro", phase,
                              f"{key} phase {i} missing intro")

    def test_phase_archetypes_are_valid(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        from engine.npc_generator import ARCHETYPES
        for key, tmpl in TIER2_TEMPLATES.items():
            for i, phase in enumerate(tmpl["phases"]):
                for spec in phase["combat_npcs"]:
                    self.assertIn(
                        spec["archetype"], ARCHETYPES,
                        f"{key} phase {i}: archetype "
                        f"{spec['archetype']!r} is unknown",
                    )

    def test_named_loot_shape(self):
        """Templates with named_loot have a well-formed shape."""
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        for key, tmpl in TIER2_TEMPLATES.items():
            loot = tmpl.get("named_loot")
            if loot is None:
                continue
            self.assertIn("type", loot, f"{key} named_loot missing type")
            self.assertIn(loot["type"], ("resource", "item"),
                          f"{key} bad named_loot type {loot['type']!r}")
            self.assertIn("key", loot, f"{key} named_loot missing key")
            if loot["type"] == "item":
                self.assertIn("name", loot,
                              f"{key} item-type named_loot missing name")

    def test_acclamator_drops_weapons_capacitor(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        loot = TIER2_TEMPLATES["downed_republic_acclamator"]["named_loot"]
        self.assertEqual(loot["type"], "resource")
        self.assertEqual(loot["key"], "weapons_capacitor_core")

    def test_convoy_drops_weapons_capacitor(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        loot = TIER2_TEMPLATES["hutt_smuggling_convoy"]["named_loot"]
        self.assertEqual(loot["type"], "resource")
        self.assertEqual(loot["key"], "weapons_capacitor_core")

    def test_maze_outbreak_drops_composite_chitin(self):
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        loot = TIER2_TEMPLATES["maze_predator_outbreak"]["named_loot"]
        self.assertEqual(loot["type"], "resource")
        self.assertEqual(loot["key"], "composite_chitin")

    def test_t5_drop_resources_in_resource_types(self):
        """The two T5 named-loot resources must be valid resource types."""
        from engine.crafting import RESOURCE_TYPES
        self.assertIn("weapons_capacitor_core", RESOURCE_TYPES)
        self.assertIn("composite_chitin", RESOURCE_TYPES)

    def test_t2_success_reward_bands_higher_than_tier1(self):
        """Tier 2 base credits should exceed Tier 1 — at least one
        T2 template should pay credits at the high end significantly
        above the T1 max."""
        from engine.wilderness_anomalies import (
            TIER1_TEMPLATES, TIER2_TEMPLATES,
        )
        t1_max = max(
            tmpl.get("success_reward", {}).get("credits", (0, 0))[1]
            for tmpl in TIER1_TEMPLATES.values()
        )
        t2_max = max(
            tmpl.get("success_reward", {}).get("credits", (0, 0))[1]
            for tmpl in TIER2_TEMPLATES.values()
        )
        self.assertGreater(
            t2_max, t1_max,
            "Tier 2 credit ceiling should exceed Tier 1",
        )

    def test_t2_influence_delta_is_in_design_band(self):
        """Influence delta should be in the 15-25 band per design §2.8."""
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        for key, tmpl in TIER2_TEMPLATES.items():
            inf = tmpl["success_reward"].get("influence", 0)
            self.assertGreaterEqual(
                inf, 15,
                f"{key} influence {inf} below design floor (15)",
            )
            self.assertLessEqual(
                inf, 25,
                f"{key} influence {inf} above design ceiling (25)",
            )


# ══════════════════════════════════════════════════════════════════════
# 3. TestTier2RegionFiltering — region tag enforcement for Tier 2
# ══════════════════════════════════════════════════════════════════════

class TestTier2RegionFiltering(_Tier2TestCase):

    def test_pick_template_tier2_dune_sea(self):
        from engine.wilderness_anomalies import _pick_template
        rng = random.Random(0)
        dune_t2_keys = {"downed_republic_acclamator",
                        "hutt_smuggling_convoy",
                        "cis_commando_deployment"}
        for _ in range(100):
            picked = _pick_template(rng, region_slug="dune_sea", tier=2)
            self.assertIn(picked, dune_t2_keys)

    def test_pick_template_tier2_coruscant(self):
        from engine.wilderness_anomalies import _pick_template
        rng = random.Random(0)
        coru_t2_keys = {"maze_predator_outbreak", "coruscant_gang_war"}
        for _ in range(100):
            picked = _pick_template(
                rng, region_slug="coruscant_underworld", tier=2,
            )
            self.assertIn(picked, coru_t2_keys)

    def test_pick_template_tier1_does_not_pick_t2(self):
        """tier=1 (default) selects only from Tier 1 templates."""
        from engine.wilderness_anomalies import (
            _pick_template, TIER2_TEMPLATES,
        )
        rng = random.Random(0)
        t2_keys = set(TIER2_TEMPLATES.keys())
        for _ in range(100):
            picked = _pick_template(rng, region_slug="dune_sea", tier=1)
            self.assertNotIn(picked, t2_keys)

    def test_pick_template_tier2_does_not_pick_t1(self):
        """tier=2 selects only from Tier 2 templates."""
        from engine.wilderness_anomalies import (
            _pick_template, TIER1_TEMPLATES,
        )
        rng = random.Random(0)
        t1_keys = set(TIER1_TEMPLATES.keys())
        for _ in range(100):
            picked = _pick_template(rng, region_slug="dune_sea", tier=2)
            self.assertNotIn(picked, t1_keys)

    def test_pick_template_tier2_unknown_region_returns_none(self):
        from engine.wilderness_anomalies import _pick_template
        self.assertIsNone(
            _pick_template(random.Random(0),
                           region_slug="endor_forest", tier=2),
        )


# ══════════════════════════════════════════════════════════════════════
# 4. TestTier2SpawnCadence — independent caps + duration from Tier 1
# ══════════════════════════════════════════════════════════════════════

class TestTier2SpawnCadence(_Tier2TestCase):

    def test_spawn_tier2_uses_tier2_duration(self):
        """A Tier 2 anomaly expires after TIER2_DURATION_SECS, not
        TIER1_DURATION_SECS."""
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, TIER2_DURATION_SECS,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")
        now = time.time()
        a = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(0),
            now=now, force=True, tier=2,
        ))
        self.assertIsNotNone(a)
        self.assertEqual(a.tier, 2)
        # Expires approximately TIER2_DURATION_SECS from now.
        self.assertAlmostEqual(
            a.expiry - now, TIER2_DURATION_SECS, delta=2,
        )

    def test_tier2_cap_independent_of_tier1(self):
        """A region can hold both Tier 1 anomalies AND a Tier 2
        anomaly simultaneously."""
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, get_anomalies_for_region,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")
        # Spawn a Tier 1 anomaly.
        a1 = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(0), force=True, tier=1,
        ))
        self.assertIsNotNone(a1)
        self.assertEqual(a1.tier, 1)
        # Spawn a Tier 2 anomaly in the same region.
        a2 = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(1), force=True, tier=2,
        ))
        self.assertIsNotNone(a2)
        self.assertEqual(a2.tier, 2)
        # Both active in the region.
        active = get_anomalies_for_region("dune_sea")
        self.assertEqual(len(active), 2)

    def test_tier2_per_region_cap_is_one(self):
        """TIER2_MAX_PER_REGION = 1. A second Tier 2 spawn while
        one is active is blocked."""
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, TIER2_MAX_PER_REGION,
        )
        self.assertEqual(TIER2_MAX_PER_REGION, 1)
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")
        first = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(0), force=True, tier=2,
        ))
        self.assertIsNotNone(first)
        # Second attempt should be capped.
        second = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(1), force=True, tier=2,
        ))
        self.assertIsNone(second)

    def test_tier2_tick_dispatches_tier2_spawns(self):
        """tick_tier2_wilderness_anomalies routes through the Tier 2
        path and only spawns Tier 2 anomalies."""
        from engine.wilderness_anomalies import (
            tick_tier2_wilderness_anomalies,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")

        class _AlwaysSpawn:
            def random(self): return 0.0
            def choice(self, seq): return seq[0]
            def randint(self, lo, hi): return lo

        stats = _run(tick_tier2_wilderness_anomalies(
            mdb, None, rng=_AlwaysSpawn(),
        ))
        self.assertEqual(stats["spawned"], 1)
        # Verify the spawned anomaly is Tier 2.
        from engine.wilderness_anomalies import _anomalies
        anomalies = _anomalies.get("dune_sea", [])
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].tier, 2)


# ══════════════════════════════════════════════════════════════════════
# 5. TestTier2InvestigateSpawn — investigate spawns ONLY phase 0
# ══════════════════════════════════════════════════════════════════════

class TestTier2InvestigateSpawn(_Tier2TestCase):

    def _setup_t2_anomaly(self, *, template_key="hutt_smuggling_convoy",
                          faction_id="independent", room_id=10):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER2_DURATION_SECS,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=room_id, zone_id=1,
                      wilderness_region_id="dune_sea")
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="dune_sea", zone_id=1,
            template_key=template_key, anchor_room_id=room_id,
            tier=2,
            expiry=now + TIER2_DURATION_SECS,
        )
        _anomalies["dune_sea"] = [a]
        char = _make_char(char_id=1, room_id=room_id, faction_id=faction_id)
        return mdb, char, a

    def test_t2_investigate_spawns_only_phase_0(self):
        """A Tier 2 investigation spawns only the FIRST phase's
        NPCs, not all phases at once."""
        from engine.wilderness_anomalies import (
            resolve_anomaly, TIER2_TEMPLATES,
        )
        mdb, char, a = self._setup_t2_anomaly(
            template_key="hutt_smuggling_convoy",
        )
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "combat")
        self.assertEqual(out["tier"], 2)
        self.assertEqual(out["phase"], 1)
        # hutt_smuggling_convoy has 2 phases.
        tmpl = TIER2_TEMPLATES["hutt_smuggling_convoy"]
        self.assertEqual(out["total_phases"], len(tmpl["phases"]))
        # Phase 1 (index 0) has 2 NPCs.
        expected_phase0_count = len(tmpl["phases"][0]["combat_npcs"])
        self.assertEqual(len(out["spawned_npc_ids"]),
                         expected_phase0_count)
        # NPCs in room match what we said we'd spawn.
        npcs_in_room = _run(mdb.get_npcs_in_room(10))
        self.assertEqual(len(npcs_in_room), expected_phase0_count)
        # All tagged as anomaly targets.
        for npc in npcs_in_room:
            cfg = json.loads(npc["ai_config_json"])
            self.assertTrue(cfg.get("is_anomaly_target"))
            self.assertEqual(cfg.get("anomaly_id"), 1)

    def test_t2_investigate_records_phase(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_t2_anomaly(
            template_key="cis_commando_deployment",
        )
        _run(resolve_anomaly(mdb, char, 1))
        self.assertEqual(a.current_phase, 0)
        self.assertEqual(a.tier, 2)

    def test_t2_investigate_does_not_pay_immediately(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_t2_anomaly(
            template_key="hutt_smuggling_convoy",
        )
        starting_credits = char["credits"]
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["credits"], 0)
        self.assertEqual(char["credits"], starting_credits)
        self.assertFalse(a.resolved)


# ══════════════════════════════════════════════════════════════════════
# 6. TestTier2PhaseAdvancement — kill last NPC of phase N → phase N+1
# ══════════════════════════════════════════════════════════════════════

class TestTier2PhaseAdvancement(_Tier2TestCase):

    def _engage(self, template_key="hutt_smuggling_convoy",
                faction_id="independent", room_id=10):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER2_DURATION_SECS,
            resolve_anomaly,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=room_id, zone_id=1,
                      wilderness_region_id="dune_sea")
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="dune_sea", zone_id=1,
            template_key=template_key, anchor_room_id=room_id,
            tier=2,
            expiry=now + TIER2_DURATION_SECS,
        )
        _anomalies["dune_sea"] = [a]
        # Persist char to mini-DB so payout step works later.
        mdb.seed_character(char_id=1, faction_id=faction_id,
                           room_id=room_id, credits=0)
        char = _make_char(char_id=1, room_id=room_id, faction_id=faction_id)
        _run(resolve_anomaly(mdb, char, 1))
        return mdb, char, a

    def test_killing_last_npc_of_phase0_advances_to_phase1(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a = self._engage(template_key="hutt_smuggling_convoy")
        # hutt_smuggling_convoy phase 0 has 2 NPCs.
        self.assertEqual(len(a.spawned_npc_ids), 2)
        phase0_ids = list(a.spawned_npc_ids)
        # Kill first of phase 0 — no advancement (still 1 hostile).
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=phase0_ids[0],
            rng=random.Random(0),
        ))
        self.assertIsNone(payout)
        self.assertEqual(a.current_phase, 0)
        # Kill second of phase 0 — phase 1 should spawn.
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=phase0_ids[1],
            rng=random.Random(0),
        ))
        self.assertIsNone(payout)  # No payout yet — phase 1 is live.
        self.assertEqual(a.current_phase, 1)
        # New NPCs spawned for phase 1.
        self.assertTrue(len(a.spawned_npc_ids) > 0)
        # They are NOT the phase 0 NPCs.
        for npc_id in a.spawned_npc_ids:
            self.assertNotIn(npc_id, phase0_ids)

    def test_phase_advancement_spawns_correct_npc_count(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward, TIER2_TEMPLATES,
        )
        mdb, char, a = self._engage(template_key="hutt_smuggling_convoy")
        phase0_ids = list(a.spawned_npc_ids)
        for nid in phase0_ids:
            _run(award_combat_anomaly_reward(
                mdb, killer_char_id=1, npc_id=nid, rng=random.Random(0),
            ))
        # Phase 1 should have the count declared in the template.
        expected_phase1_count = len(
            TIER2_TEMPLATES["hutt_smuggling_convoy"]["phases"][1]["combat_npcs"]
        )
        self.assertEqual(len(a.spawned_npc_ids), expected_phase1_count)

    def test_phase_advancement_resets_npc_list(self):
        """spawned_npc_ids is replaced when advancing, not appended to."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a = self._engage(template_key="hutt_smuggling_convoy")
        for nid in list(a.spawned_npc_ids):
            _run(award_combat_anomaly_reward(
                mdb, killer_char_id=1, npc_id=nid, rng=random.Random(0),
            ))
        # No leftover phase-0 NPCs.
        npc_rows = [_run(mdb.get_npc(nid)) for nid in a.spawned_npc_ids]
        for row in npc_rows:
            self.assertIsNotNone(row)
            cfg = json.loads(row["ai_config_json"])
            self.assertTrue(cfg.get("is_anomaly_target"))


# ══════════════════════════════════════════════════════════════════════
# 7. TestTier2FinalPhasePayout — full clear pays everything
# ══════════════════════════════════════════════════════════════════════

class TestTier2FinalPhasePayout(_Tier2TestCase):

    def _engage_and_clear_to_final(self, template_key,
                                     faction_id="republic",
                                     room_id=10):
        """Engage the anomaly and kill every NPC up to (but not
        including) the very last one of the final phase. Return
        (mdb, char, anomaly, final_npc_id)."""
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER2_DURATION_SECS,
            resolve_anomaly, award_combat_anomaly_reward,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        # Use dune_sea for Dune Sea templates, coruscant_underworld
        # for Coruscant templates.
        from engine.wilderness_anomalies import TIER2_TEMPLATES
        regions = TIER2_TEMPLATES[template_key]["regions"]
        region_slug = regions[0]
        mdb.seed_room(room_id=room_id, zone_id=1,
                      wilderness_region_id=region_slug)
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug=region_slug, zone_id=1,
            template_key=template_key, anchor_room_id=room_id,
            tier=2, expiry=now + TIER2_DURATION_SECS,
        )
        _anomalies[region_slug] = [a]
        mdb.seed_character(char_id=1, faction_id=faction_id,
                           room_id=room_id, credits=0)
        char = _make_char(char_id=1, room_id=room_id,
                          faction_id=faction_id)
        _run(resolve_anomaly(mdb, char, 1))
        # Walk through all phases except the last NPC of the final.
        n_phases = a.total_phases
        for phase_idx in range(n_phases - 1):
            for nid in list(a.spawned_npc_ids):
                _run(award_combat_anomaly_reward(
                    mdb, killer_char_id=1, npc_id=nid,
                    rng=random.Random(0),
                ))
        # Now in the final phase. Kill all but the last NPC.
        final_npcs = list(a.spawned_npc_ids)
        for nid in final_npcs[:-1]:
            _run(award_combat_anomaly_reward(
                mdb, killer_char_id=1, npc_id=nid,
                rng=random.Random(0),
            ))
        return mdb, char, a, final_npcs[-1]

    def test_final_kill_pays_credits(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a, final_npc_id = self._engage_and_clear_to_final(
            "hutt_smuggling_convoy", faction_id="republic",
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        self.assertIsNotNone(payout)
        self.assertEqual(payout["tier"], 2)
        self.assertGreater(payout["credits"], 0)

    def test_final_kill_grants_named_loot_to_killer(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a, final_npc_id = self._engage_and_clear_to_final(
            "hutt_smuggling_convoy",
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        named = payout.get("named_loot")
        self.assertIsNotNone(named)
        self.assertEqual(named["type"], "resource")
        self.assertEqual(named["key"], "weapons_capacitor_core")
        # And it's actually in the killer's inventory.
        killer = _run(mdb.get_character(1))
        inv = json.loads(killer["inventory"])
        resources = inv.get("resources", [])
        weapon_capacitor = [
            r for r in resources
            if r["type"] == "weapons_capacitor_core"
        ]
        self.assertEqual(len(weapon_capacitor), 1)
        self.assertEqual(weapon_capacitor[0]["quantity"], 1)

    def test_final_kill_grants_faction_influence_to_killer(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward, TIER2_INFLUENCE_DELTA,
        )
        mdb, char, a, final_npc_id = self._engage_and_clear_to_final(
            "hutt_smuggling_convoy", faction_id="republic",
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        self.assertEqual(payout["influence"], TIER2_INFLUENCE_DELTA)

    def test_independent_killer_no_influence(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a, final_npc_id = self._engage_and_clear_to_final(
            "hutt_smuggling_convoy", faction_id="independent",
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        self.assertEqual(payout["influence"], 0)

    def test_anomaly_marked_resolved_on_final_clear(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a, final_npc_id = self._engage_and_clear_to_final(
            "hutt_smuggling_convoy",
        )
        self.assertFalse(a.resolved)
        _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        self.assertTrue(a.resolved)
        self.assertEqual(a.resolved_by, 1)


# ══════════════════════════════════════════════════════════════════════
# 8. TestTier2NamedLoot — named loot grants
# ══════════════════════════════════════════════════════════════════════

class TestTier2NamedLoot(_Tier2TestCase):

    def test_grant_resource_named_loot_adds_to_crafting_resources(self):
        from engine.wilderness_anomalies import _grant_named_loot
        mdb = _MiniDB()
        mdb.seed_character(char_id=1, credits=0)
        killer = _run(mdb.get_character(1))
        result = _run(_grant_named_loot(mdb, killer, {
            "type": "resource",
            "key": "weapons_capacitor_core",
            "qty": 1,
            "quality": 70.0,
            "description": "test",
        }))
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "resource")
        # Persisted to inventory.
        killer2 = _run(mdb.get_character(1))
        inv = json.loads(killer2["inventory"])
        resources = inv.get("resources", [])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["type"], "weapons_capacitor_core")
        self.assertEqual(resources[0]["quantity"], 1)
        self.assertEqual(resources[0]["quality"], 70.0)

    def test_grant_item_named_loot_adds_to_inventory_items(self):
        from engine.wilderness_anomalies import _grant_named_loot
        mdb = _MiniDB()
        mdb.seed_character(char_id=1, credits=0)
        killer = _run(mdb.get_character(1))
        result = _run(_grant_named_loot(mdb, killer, {
            "type": "item",
            "key": "tactical_droid_command_module",
            "qty": 1,
            "name": "T-Series Tactical Droid Command Module",
            "description": "Salvaged.",
        }))
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "item")
        # Persisted.
        killer2 = _run(mdb.get_character(1))
        inv = json.loads(killer2["inventory"])
        items = inv.get("items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["key"], "tactical_droid_command_module")
        self.assertEqual(items[0]["name"],
                         "T-Series Tactical Droid Command Module")
        self.assertTrue(items[0]["is_anomaly_loot"])

    def test_grant_unknown_type_returns_none(self):
        from engine.wilderness_anomalies import _grant_named_loot
        mdb = _MiniDB()
        mdb.seed_character(char_id=1)
        killer = _run(mdb.get_character(1))
        result = _run(_grant_named_loot(mdb, killer, {
            "type": "totally_unknown",
            "key": "x",
        }))
        self.assertIsNone(result)


# ══════════════════════════════════════════════════════════════════════
# 9. TestTier2MultiParticipant — multi-character payout split
# ══════════════════════════════════════════════════════════════════════

class TestTier2MultiParticipant(_Tier2TestCase):

    def _engage_2char(self, template_key="hutt_smuggling_convoy",
                      killer_faction="republic",
                      bystander_faction="independent",
                      room_id=10):
        """Set up two characters in the same room, engaged on a T2
        anomaly. Returns (mdb, killer, bystander, anomaly,
        final_npc_id)."""
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER2_DURATION_SECS,
            resolve_anomaly, award_combat_anomaly_reward,
            TIER2_TEMPLATES,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        regions = TIER2_TEMPLATES[template_key]["regions"]
        region_slug = regions[0]
        mdb.seed_room(room_id=room_id, zone_id=1,
                      wilderness_region_id=region_slug)
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug=region_slug, zone_id=1,
            template_key=template_key, anchor_room_id=room_id,
            tier=2, expiry=now + TIER2_DURATION_SECS,
        )
        _anomalies[region_slug] = [a]
        # Two characters in the same room.
        mdb.seed_character(char_id=1, name="Killer",
                           faction_id=killer_faction, room_id=room_id,
                           credits=0)
        mdb.seed_character(char_id=2, name="Bystander",
                           faction_id=bystander_faction, room_id=room_id,
                           credits=0)
        # Use char 1 to engage (the dict-form for resolve_anomaly).
        killer = _make_char(char_id=1, room_id=room_id,
                            faction_id=killer_faction)
        _run(resolve_anomaly(mdb, killer, 1))
        # Walk through all phases up to last NPC of final phase.
        n_phases = a.total_phases
        for phase_idx in range(n_phases - 1):
            for nid in list(a.spawned_npc_ids):
                _run(award_combat_anomaly_reward(
                    mdb, killer_char_id=1, npc_id=nid,
                    rng=random.Random(0),
                ))
        final_npcs = list(a.spawned_npc_ids)
        for nid in final_npcs[:-1]:
            _run(award_combat_anomaly_reward(
                mdb, killer_char_id=1, npc_id=nid,
                rng=random.Random(0),
            ))
        return mdb, killer, a, final_npcs[-1]

    def test_both_chars_get_credits(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, killer, a, final_npc_id = self._engage_2char()
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        self.assertIsNotNone(payout)
        self.assertEqual(len(payout["payouts_per_char"]), 2)
        # Both got the same per-character credit amount.
        creds = [p["credits"] for p in payout["payouts_per_char"]]
        self.assertEqual(creds[0], creds[1])
        self.assertGreater(creds[0], 0)
        # Persisted to DB.
        c1 = _run(mdb.get_character(1))
        c2 = _run(mdb.get_character(2))
        self.assertEqual(c1["credits"], creds[0])
        self.assertEqual(c2["credits"], creds[0])

    def test_only_killer_gets_named_loot(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, killer, a, final_npc_id = self._engage_2char()
        _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        # Killer has the named loot.
        c1 = _run(mdb.get_character(1))
        inv1 = json.loads(c1["inventory"])
        res1 = inv1.get("resources", [])
        wcc = [r for r in res1 if r["type"] == "weapons_capacitor_core"]
        self.assertEqual(len(wcc), 1)
        # Bystander does not.
        c2 = _run(mdb.get_character(2))
        inv2 = json.loads(c2["inventory"])
        res2 = inv2.get("resources", [])
        wcc2 = [r for r in res2 if r["type"] == "weapons_capacitor_core"]
        self.assertEqual(len(wcc2), 0)

    def test_only_killer_faction_gets_influence(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward, TIER2_INFLUENCE_DELTA,
        )
        mdb, killer, a, final_npc_id = self._engage_2char(
            killer_faction="republic",
            bystander_faction="cis",
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        # Influence reported on the payout is the killer's only.
        self.assertEqual(payout["influence"], TIER2_INFLUENCE_DELTA)

    def test_total_credits_split_evenly(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, killer, a, final_npc_id = self._engage_2char()
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=final_npc_id,
            rng=random.Random(0),
        ))
        total = payout["total_credits_pool"]
        per = payout["credits"]
        # 2 participants — per-char should be total // 2.
        self.assertEqual(per, total // 2)


if __name__ == "__main__":
    unittest.main()
