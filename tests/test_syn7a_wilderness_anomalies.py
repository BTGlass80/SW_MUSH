# -*- coding: utf-8 -*-
"""
tests/test_syn7a_wilderness_anomalies.py — SYN.7.a (2026-05-25).

Pins:
  * engine/wilderness_anomalies.py (new) — module-level transient
    state, 5 CW-correct Tier 1 templates, spawn-cadence engine,
    skill-check-based resolution.
  * parser/anomaly_commands.py (new) — AnomaliesCommand,
    InvestigateCommand.
  * server/tick_handlers_economy.py — wilderness_anomaly_tick wrapper.
  * server/game_server.py — scheduler registration + parser
    registration.

Test sections
─────────────
  1. TestTemplateCatalog         — 5 templates, required fields,
                                    CW-correct flavor (no "Imperial")
  2. TestPureHelpers             — _format_news, _sample_credits,
                                    _pick_better_skill, _pick_template
  3. TestPruneExpiredRegion      — expired removed, fresh kept
  4. TestSpawnAnomalyForRegion   — basic spawn, cap, low-roll,
                                    force=True, anchor room fallback
  5. TestTickFlow                — multiple regions, stats dict
  6. TestGetAnomaliesForRegion   — lists active, excludes
                                    expired/resolved
  7. TestResolveAnomalyFailures  — no room, no region, not found,
                                    wrong room, already resolved
  8. TestResolveAnomalySuccess   — credits + resources + influence
                                    awarded; anomaly marked resolved
  9. TestResolveAnomalyFailedSkill — partial reward, anomaly still
                                     resolved (one-shot semantics)
 10. TestStateIsolation          — region A vs B; reset helper
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
# In-memory DB stand-in (mirrors SYN.6.c pattern + adds zone_security
# helpers; supports influence-adjust via the existing territory module)
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

    # ── SYN.7.a.fix: NPC CRUD for combat-resolution tests ─────────────
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

    async def update_npc(self, npc_id, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [npc_id]
        self._db._conn.execute(
            f"UPDATE npcs SET {cols} WHERE id = ?", params)
        self._db._conn.commit()

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
        "attributes": json.dumps({"survival": "3D", "technical": "3D",
                                    "medicine": "3D", "knowledge": "3D",
                                    "blaster": "3D"}),
        "skills": json.dumps(skills),
        "inventory": json.dumps({}),
    }


class _AnomalyTestCase(unittest.TestCase):
    """Base class that resets module state between tests."""

    def setUp(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        _reset_state_for_tests()


# ──────────────────────────────────────────────────────────────────────
# 1. TestTemplateCatalog
# ──────────────────────────────────────────────────────────────────────

class TestTemplateCatalog(_AnomalyTestCase):
    """The 5 Tier 1 templates have the right shape + are CW-correct."""

    def test_ten_templates_present(self):
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        expected = {
            # Dune Sea
            "stranded_clone_scout", "salvage_cache",
            "wounded_animal", "tusken_party",
            "crashed_cis_probe",
            # Coruscant Underworld (SYN.7.a.fix)
            "black_sun_courier", "factory_cache", "maze_rogue",
            "cis_sleeper_cell", "bounty_hunter_rival",
        }
        self.assertEqual(set(TIER1_TEMPLATES.keys()), expected)

    def test_every_template_has_required_fields(self):
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        # SYN.7.a.fix: every template MUST declare regions + resolution
        # and the news_text + display_name + descriptions.
        required_universal = (
            "regions", "resolution",
            "display_name", "short_desc", "long_desc",
            "success_reward", "fail_reward", "news_text",
        )
        for key, tmpl in TIER1_TEMPLATES.items():
            for field in required_universal:
                self.assertIn(field, tmpl, f"{key} missing {field}")
            # Resolution-mode-specific required fields
            if tmpl["resolution"] == "skill":
                self.assertIn("primary_skill", tmpl,
                              f"{key} (skill) missing primary_skill")
            elif tmpl["resolution"] == "combat":
                self.assertIn("combat_npcs", tmpl,
                              f"{key} (combat) missing combat_npcs")
                self.assertGreater(
                    len(tmpl["combat_npcs"]), 0,
                    f"{key} (combat) has empty combat_npcs",
                )
            else:
                self.fail(f"{key}: unknown resolution {tmpl['resolution']!r}")

    def test_success_reward_structure(self):
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        for key, tmpl in TIER1_TEMPLATES.items():
            r = tmpl["success_reward"]
            self.assertIn("credits", r)
            self.assertIn("resources", r)
            self.assertIn("influence", r)
            # credits is a (min, max) tuple
            self.assertEqual(len(r["credits"]), 2)
            # resources is a list of tuples
            self.assertIsInstance(r["resources"], list)
            # influence is +5 across all Tier 1
            from engine.wilderness_anomalies import TIER1_INFLUENCE_DELTA
            self.assertEqual(r["influence"], TIER1_INFLUENCE_DELTA)

    def test_cw_correct_no_imperial(self):
        """No GCW residue in template flavor strings."""
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        forbidden_substrings = ["imperial", "empire", "stormtrooper",
                                "imperial_patrol", "tie fighter"]
        for key, tmpl in TIER1_TEMPLATES.items():
            blob = " ".join([
                tmpl.get("display_name", ""),
                tmpl.get("short_desc", ""),
                tmpl.get("long_desc", ""),
                tmpl.get("news_text", ""),
            ]).lower()
            for forbidden in forbidden_substrings:
                self.assertNotIn(
                    forbidden, blob,
                    f"{key} contains GCW-era token {forbidden!r}",
                )

    def test_clone_scout_is_republic_flavored(self):
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        tmpl = TIER1_TEMPLATES["stranded_clone_scout"]
        text = (tmpl["long_desc"] + tmpl["news_text"]).lower()
        self.assertIn("republic", text)
        self.assertIn("clone", text)

    def test_cis_probe_is_separatist_flavored(self):
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        tmpl = TIER1_TEMPLATES["crashed_cis_probe"]
        text = (tmpl["long_desc"] + tmpl["news_text"]).lower()
        self.assertTrue("cis" in text or "separatist" in text
                        or "confederate" in text)

    def test_resource_types_in_rewards_are_valid(self):
        """All resource types in template rewards are in
        engine.crafting.RESOURCE_TYPES."""
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        from engine.crafting import RESOURCE_TYPES
        for key, tmpl in TIER1_TEMPLATES.items():
            for shape in ("success_reward", "fail_reward"):
                for (rtype, qty, qual) in tmpl[shape].get("resources", []):
                    self.assertIn(
                        rtype, RESOURCE_TYPES,
                        f"{key}/{shape} has bad resource type {rtype!r}",
                    )


# ──────────────────────────────────────────────────────────────────────
# 2. TestPureHelpers
# ──────────────────────────────────────────────────────────────────────

class TestPureHelpers(_AnomalyTestCase):
    """Module-internal pure helpers."""

    def test_format_news_substitutes_region(self):
        from engine.wilderness_anomalies import _format_news
        out = _format_news("stranded_clone_scout", "tatooine_dune_sea")
        self.assertIn("Tatooine Dune Sea", out)

    def test_format_news_unknown_template_safe(self):
        from engine.wilderness_anomalies import _format_news
        # Unknown template falls back to generic line
        out = _format_news("nonexistent", "r1")
        self.assertIn("R1", out)

    def test_sample_credits_in_band(self):
        from engine.wilderness_anomalies import _sample_credits
        rng = random.Random(0)
        for _ in range(20):
            v = _sample_credits(rng, (100, 200))
            self.assertGreaterEqual(v, 100)
            self.assertLessEqual(v, 200)

    def test_sample_credits_zero_band(self):
        from engine.wilderness_anomalies import _sample_credits
        self.assertEqual(_sample_credits(random.Random(), (0, 0)), 0)

    def test_pick_template_returns_known_key(self):
        from engine.wilderness_anomalies import (
            _pick_template, TIER1_TEMPLATES,
        )
        rng = random.Random(0)
        # SYN.7.a.fix: with a real region tag, only matching templates
        # can be returned. Dune Sea templates are the original 5.
        dune_keys = {k for k, v in TIER1_TEMPLATES.items()
                     if "dune_sea" in v["regions"]}
        for _ in range(20):
            picked = _pick_template(rng, region_slug="dune_sea")
            self.assertIn(picked, dune_keys)
        # Coruscant Underworld templates are disjoint.
        coru_keys = {k for k, v in TIER1_TEMPLATES.items()
                     if "coruscant_underworld" in v["regions"]}
        for _ in range(20):
            picked = _pick_template(rng, region_slug="coruscant_underworld")
            self.assertIn(picked, coru_keys)
        # Region with no templates returns None.
        self.assertIsNone(_pick_template(rng, region_slug="nonexistent_region"))

    def test_pick_better_skill_trained_primary(self):
        from engine.wilderness_anomalies import _pick_better_skill
        char = {"skills": json.dumps({"medicine": "5D"})}
        self.assertEqual(
            _pick_better_skill(char, "medicine", "survival"),
            "medicine",
        )

    def test_pick_better_skill_falls_back_secondary(self):
        from engine.wilderness_anomalies import _pick_better_skill
        char = {"skills": json.dumps({"survival": "5D"})}
        self.assertEqual(
            _pick_better_skill(char, "medicine", "survival"),
            "survival",
        )

    def test_pick_better_skill_no_trained_returns_primary(self):
        from engine.wilderness_anomalies import _pick_better_skill
        char = {"skills": json.dumps({})}
        self.assertEqual(
            _pick_better_skill(char, "medicine", "survival"),
            "medicine",
        )

    def test_pick_better_skill_no_secondary(self):
        from engine.wilderness_anomalies import _pick_better_skill
        char = {"skills": json.dumps({})}
        self.assertEqual(
            _pick_better_skill(char, "medicine", None),
            "medicine",
        )


# ──────────────────────────────────────────────────────────────────────
# 3. TestPruneExpiredRegion
# ──────────────────────────────────────────────────────────────────────

class TestPruneExpiredRegion(_AnomalyTestCase):
    """Expired anomalies are pruned; fresh ones kept."""

    def test_fresh_anomaly_kept(self):
        from engine.wilderness_anomalies import (
            _anomalies, _prune_expired_region, WildernessAnomaly,
        )
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key="stranded_clone_scout",
            anchor_room_id=10,
            spawned_at=now, expiry=now + 600,  # 10 min from now
        )
        _anomalies["r1"] = [a]
        removed = _prune_expired_region("r1", now)
        self.assertEqual(removed, 0)
        self.assertEqual(len(_anomalies["r1"]), 1)

    def test_expired_anomaly_removed(self):
        from engine.wilderness_anomalies import (
            _anomalies, _prune_expired_region, WildernessAnomaly,
        )
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key="stranded_clone_scout",
            anchor_room_id=10,
            spawned_at=now - 7200, expiry=now - 60,  # expired 1 min ago
        )
        _anomalies["r1"] = [a]
        removed = _prune_expired_region("r1", now)
        self.assertEqual(removed, 1)
        self.assertEqual(len(_anomalies["r1"]), 0)

    def test_prune_mixed_region(self):
        from engine.wilderness_anomalies import (
            _anomalies, _prune_expired_region, WildernessAnomaly,
        )
        now = time.time()
        fresh = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key="stranded_clone_scout",
            anchor_room_id=10,
            expiry=now + 600,
        )
        stale = WildernessAnomaly(
            id=2, region_slug="r1", zone_id=1,
            template_key="salvage_cache",
            anchor_room_id=11,
            expiry=now - 100,
        )
        _anomalies["r1"] = [fresh, stale]
        removed = _prune_expired_region("r1", now)
        self.assertEqual(removed, 1)
        self.assertEqual(len(_anomalies["r1"]), 1)
        self.assertEqual(_anomalies["r1"][0].id, 1)


# ──────────────────────────────────────────────────────────────────────
# 4. TestSpawnAnomalyForRegion
# ──────────────────────────────────────────────────────────────────────

class TestSpawnAnomalyForRegion(_AnomalyTestCase):

    def _bootstrap_region(self, mdb, region="dune_sea", room_ids=(10, 11)):
        mdb.seed_zone(zone_id=1)
        for rid in room_ids:
            mdb.seed_room(room_id=rid, zone_id=1,
                          wilderness_region_id=region)
        return mdb

    def test_basic_spawn_force(self):
        from engine.wilderness_anomalies import spawn_anomaly_for_region
        mdb = self._bootstrap_region(_MiniDB())
        a = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(0), force=True,
        ))
        self.assertIsNotNone(a)
        self.assertEqual(a.region_slug, "dune_sea")
        # SYN.7.a.fix: template must be one of the 5 dune_sea-tagged
        # templates, not a Coruscant one.
        self.assertIn(a.template_key,
                      ["stranded_clone_scout", "salvage_cache",
                       "wounded_animal", "tusken_party",
                       "crashed_cis_probe"])
        self.assertIn(a.anchor_room_id, [10, 11])

    def test_cap_respected(self):
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, MAX_PER_REGION,
        )
        mdb = self._bootstrap_region(_MiniDB())
        results = []
        for _ in range(MAX_PER_REGION + 2):
            r = _run(spawn_anomaly_for_region(
                mdb, "dune_sea", rng=random.Random(_), force=True,
            ))
            results.append(r)
        non_none = [r for r in results if r is not None]
        # Cap at MAX_PER_REGION
        self.assertEqual(len(non_none), MAX_PER_REGION)

    def test_low_roll_no_spawn(self):
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, SPAWN_CHANCE_PER_TICK,
        )
        mdb = self._bootstrap_region(_MiniDB())

        # Build an RNG that returns a value above SPAWN_CHANCE_PER_TICK
        class _HighRoll:
            def random(self): return 0.99
            def choice(self, seq): return seq[0]
            def randint(self, lo, hi): return lo

        a = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=_HighRoll(), force=False,
        ))
        self.assertIsNone(a)

    def test_no_rooms_no_spawn(self):
        from engine.wilderness_anomalies import spawn_anomaly_for_region
        mdb = _MiniDB()
        # No rooms at all (and an unknown region — should still be
        # None either way)
        a = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(0), force=True,
        ))
        self.assertIsNone(a)


# ──────────────────────────────────────────────────────────────────────
# 5. TestTickFlow
# ──────────────────────────────────────────────────────────────────────

class TestTickFlow(_AnomalyTestCase):

    def test_tick_returns_stats(self):
        from engine.wilderness_anomalies import tick_wilderness_anomalies
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        # SYN.7.a.fix: use a real region slug so _pick_template can
        # actually return a template.
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="dune_sea")
        mdb.seed_room(room_id=11, zone_id=1, wilderness_region_id="dune_sea")

        class _AlwaysSpawn:
            def random(self): return 0.0
            def choice(self, seq): return seq[0]
            def randint(self, lo, hi): return lo

        stats = _run(tick_wilderness_anomalies(
            mdb, None, rng=_AlwaysSpawn(),
        ))
        self.assertIn("pruned", stats)
        self.assertIn("spawned", stats)
        self.assertEqual(stats["spawned"], 1)

    def test_tick_with_no_wilderness_rooms(self):
        from engine.wilderness_anomalies import tick_wilderness_anomalies
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id=None)
        stats = _run(tick_wilderness_anomalies(mdb, None))
        self.assertEqual(stats["spawned"], 0)


# ──────────────────────────────────────────────────────────────────────
# 6. TestGetAnomaliesForRegion
# ──────────────────────────────────────────────────────────────────────

class TestGetAnomaliesForRegion(_AnomalyTestCase):

    def test_empty_region(self):
        from engine.wilderness_anomalies import get_anomalies_for_region
        self.assertEqual(get_anomalies_for_region("nonexistent"), [])

    def test_active_anomaly_listed(self):
        from engine.wilderness_anomalies import (
            _anomalies, get_anomalies_for_region, WildernessAnomaly,
        )
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key="stranded_clone_scout",
            anchor_room_id=10,
            expiry=now + 600,
        )
        _anomalies["r1"] = [a]
        out = get_anomalies_for_region("r1", now=now)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, 1)

    def test_resolved_anomaly_excluded(self):
        from engine.wilderness_anomalies import (
            _anomalies, get_anomalies_for_region, WildernessAnomaly,
        )
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key="stranded_clone_scout",
            anchor_room_id=10,
            expiry=now + 600,
            resolved=True,
        )
        _anomalies["r1"] = [a]
        out = get_anomalies_for_region("r1", now=now)
        self.assertEqual(out, [])


# ──────────────────────────────────────────────────────────────────────
# 7. TestResolveAnomalyFailures
# ──────────────────────────────────────────────────────────────────────

class TestResolveAnomalyFailures(_AnomalyTestCase):

    def test_no_room_id(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb = _MiniDB()
        char = _make_char(char_id=1, room_id=None)
        char["room_id"] = None
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertFalse(out["ok"])

    def test_room_not_in_wilderness(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        # City-map room, no wilderness_region_id
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id=None)
        char = _make_char(char_id=1, room_id=10)
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertFalse(out["ok"])
        self.assertIn("wilderness", out["msg"].lower())

    def test_anomaly_not_found(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="r1")
        char = _make_char(char_id=1, room_id=10)
        out = _run(resolve_anomaly(mdb, char, 999))
        self.assertFalse(out["ok"])
        self.assertIn("999", out["msg"])

    def test_wrong_room_rejection(self):
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, resolve_anomaly,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="dune_sea")
        mdb.seed_room(room_id=11, zone_id=1, wilderness_region_id="dune_sea")
        a = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(0), force=True,
        ))
        # Char at room 11, anomaly at (likely) room 10 or 11; force
        # the mismatch
        if a.anchor_room_id == 10:
            other_room = 11
        else:
            other_room = 10
        char = _make_char(char_id=1, room_id=other_room)
        out = _run(resolve_anomaly(mdb, char, a.id))
        self.assertFalse(out["ok"])
        self.assertIn("site", out["msg"].lower())

    def test_already_resolved(self):
        from engine.wilderness_anomalies import (
            _anomalies, resolve_anomaly, WildernessAnomaly,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="r1")
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key="stranded_clone_scout",
            anchor_room_id=10,
            expiry=now + 600,
            resolved=True,
            resolved_by=99,
        )
        _anomalies["r1"] = [a]
        char = _make_char(char_id=1, room_id=10)
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertFalse(out["ok"])
        self.assertIn("already", out["msg"].lower())


# ──────────────────────────────────────────────────────────────────────
# 8. TestResolveAnomalySuccess
# ──────────────────────────────────────────────────────────────────────

class TestResolveAnomalySuccess(_AnomalyTestCase):

    def _setup_with_anomaly(self, *, template_key="stranded_clone_scout",
                            faction_id="republic"):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="r1")
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key=template_key,
            anchor_room_id=10,
            expiry=now + 600,
        )
        _anomalies["r1"] = [a]
        char = _make_char(char_id=1, room_id=10, faction_id=faction_id,
                          skills={"medicine": "12D",
                                   "survival": "12D",
                                   "technical": "12D",
                                   "knowledge": "12D",
                                   "blaster": "12D"})
        # Seed the char row so the ledger chokepoint (db.adjust_credits,
        # Drop 1) has a row to update. _make_char only builds the in-memory
        # dict; the migrated reward path now writes credits through the DB,
        # so an unseeded char would leave credits at 0 (same-connection
        # visibility means no explicit commit is needed here).
        mdb._db._conn.execute(
            "INSERT INTO characters (id, credits, faction_id) VALUES (?, ?, ?)",
            (char["id"], char.get("credits", 0), faction_id))
        return mdb, char, a

    def test_high_skill_succeeds_with_credits(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_with_anomaly()
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertTrue(out["success"])
        self.assertGreater(out["credits"], 0)
        # Char credits updated
        self.assertEqual(char["credits"], out["credits"])

    def test_resources_granted(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_with_anomaly()
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["success"])
        # Template has 2 resource stacks for stranded_clone_scout
        self.assertGreater(len(out["resources"]), 0)
        # Inventory updated
        inv = json.loads(char["inventory"])
        self.assertGreater(len(inv.get("resources", [])), 0)

    def test_anomaly_marked_resolved(self):
        from engine.wilderness_anomalies import (
            resolve_anomaly, get_anomalies_for_region,
        )
        mdb, char, a = self._setup_with_anomaly()
        _run(resolve_anomaly(mdb, char, 1))
        # Anomaly should now be excluded from get_anomalies_for_region
        active = get_anomalies_for_region("r1")
        self.assertEqual(active, [])
        # Underlying object has resolved=True
        self.assertTrue(a.resolved)
        self.assertEqual(a.resolved_by, 1)
        self.assertEqual(a.resolved_faction, "republic")

    def test_independent_char_no_influence(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_with_anomaly(faction_id="independent")
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["success"])
        # Independent char gets no influence even on success
        self.assertEqual(out["influence"], 0)

    def test_faction_char_gets_influence(self):
        from engine.wilderness_anomalies import (
            resolve_anomaly, TIER1_INFLUENCE_DELTA,
        )
        mdb, char, a = self._setup_with_anomaly(faction_id="hutts")
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["success"])
        self.assertEqual(out["influence"], TIER1_INFLUENCE_DELTA)


# ──────────────────────────────────────────────────────────────────────
# 9. TestResolveAnomalyFailedSkill
# ──────────────────────────────────────────────────────────────────────

class TestResolveAnomalyFailedSkill(_AnomalyTestCase):

    def test_failed_skill_still_resolves(self):
        """Anomaly is one-shot. Failed skill check still consumes it
        (player gets the fail_reward, not nothing)."""
        from engine.wilderness_anomalies import (
            _anomalies, resolve_anomaly, WildernessAnomaly,
            get_anomalies_for_region,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="r1")
        now = time.time()
        # Salvage_cache fail_reward: 30-80cr + 1 metal q30
        a = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key="salvage_cache",
            anchor_room_id=10,
            expiry=now + 600,
        )
        _anomalies["r1"] = [a]
        # 1D technical, 1D survival — likely fails DC 13
        char = _make_char(char_id=1, room_id=10,
                          skills={"technical": "1D", "survival": "1D"})
        # Force a specific seed pattern for determinism — even with
        # Wild Die, 1D vs DC 13 mostly fails. If the seed happens to
        # produce success, we still pin the "resolved" state which
        # is what matters.
        random.seed(0)
        out = _run(resolve_anomaly(mdb, char, 1))
        # Either way: ok=True, anomaly marked resolved
        self.assertTrue(out["ok"])
        self.assertTrue(a.resolved)
        # And anomaly is gone from active list
        active = get_anomalies_for_region("r1")
        self.assertEqual(active, [])


# ──────────────────────────────────────────────────────────────────────
# 10. TestStateIsolation
# ──────────────────────────────────────────────────────────────────────

class TestStateIsolation(_AnomalyTestCase):

    def test_region_isolation(self):
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, get_anomalies_for_region,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        # SYN.7.a.fix: use two real regions (Dune Sea + Coruscant
        # Underworld) so _pick_template can find templates for both.
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="dune_sea")
        mdb.seed_room(room_id=20, zone_id=1,
                      wilderness_region_id="coruscant_underworld")
        a1 = _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(0), force=True,
        ))
        a2 = _run(spawn_anomaly_for_region(
            mdb, "coruscant_underworld", rng=random.Random(1), force=True,
        ))
        self.assertIsNotNone(a1)
        self.assertIsNotNone(a2)
        self.assertEqual(len(get_anomalies_for_region("dune_sea")), 1)
        self.assertEqual(len(get_anomalies_for_region("coruscant_underworld")), 1)

    def test_reset_helper(self):
        from engine.wilderness_anomalies import (
            spawn_anomaly_for_region, get_anomalies_for_region,
            _reset_state_for_tests,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="dune_sea")
        _run(spawn_anomaly_for_region(
            mdb, "dune_sea", rng=random.Random(0), force=True,
        ))
        self.assertEqual(len(get_anomalies_for_region("dune_sea")), 1)
        _reset_state_for_tests()
        self.assertEqual(len(get_anomalies_for_region("dune_sea")), 0)


# ══════════════════════════════════════════════════════════════════════
# SYN.7.a.fix sections — region filtering + combat resolution + cleanup
# ══════════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────────────
# 11. TestCoruscantTemplates — CW-correct flavor + structure
# ──────────────────────────────────────────────────────────────────────

class TestCoruscantTemplates(_AnomalyTestCase):
    """The 5 Coruscant Underworld templates are CW-correct and
    structurally sound."""

    CORU_KEYS = {"black_sun_courier", "factory_cache", "maze_rogue",
                 "cis_sleeper_cell", "bounty_hunter_rival"}

    def test_coruscant_templates_present(self):
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        for k in self.CORU_KEYS:
            self.assertIn(k, TIER1_TEMPLATES)

    def test_coruscant_templates_tagged_coruscant_only(self):
        """No Coruscant template leaks into Dune Sea (and vice versa)."""
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        for k in self.CORU_KEYS:
            regions = TIER1_TEMPLATES[k]["regions"]
            self.assertIn("coruscant_underworld", regions,
                          f"{k} not tagged for coruscant_underworld")
            self.assertNotIn("dune_sea", regions,
                             f"{k} leaked into dune_sea")

    def test_coruscant_templates_cw_correct(self):
        """No GCW residue in Coruscant template flavor strings."""
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        forbidden = ["imperial", "empire", "stormtrooper",
                     "imperial_patrol", "tie fighter"]
        for k in self.CORU_KEYS:
            tmpl = TIER1_TEMPLATES[k]
            blob = " ".join([
                tmpl.get("display_name", ""),
                tmpl.get("short_desc", ""),
                tmpl.get("long_desc", ""),
                tmpl.get("news_text", ""),
            ]).lower()
            for tok in forbidden:
                self.assertNotIn(
                    tok, blob,
                    f"{k} contains GCW-era token {tok!r}",
                )

    def test_coruscant_combat_templates_have_archetypes(self):
        """Combat-resolution Coruscant templates name real archetypes."""
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        from engine.npc_generator import ARCHETYPES
        for k in self.CORU_KEYS:
            tmpl = TIER1_TEMPLATES[k]
            if tmpl["resolution"] != "combat":
                continue
            for spec in tmpl["combat_npcs"]:
                self.assertIn(
                    spec["archetype"], ARCHETYPES,
                    f"{k}: archetype {spec['archetype']!r} is unknown",
                )

    def test_dune_sea_combat_templates_have_archetypes(self):
        """Same check for the Dune Sea combat templates (wounded_animal,
        tusken_party) that flipped skill→combat in SYN.7.a.fix."""
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        from engine.npc_generator import ARCHETYPES
        for k in ("wounded_animal", "tusken_party"):
            tmpl = TIER1_TEMPLATES[k]
            self.assertEqual(tmpl["resolution"], "combat",
                             f"{k} should be combat-resolution now")
            for spec in tmpl["combat_npcs"]:
                self.assertIn(
                    spec["archetype"], ARCHETYPES,
                    f"{k}: archetype {spec['archetype']!r} is unknown",
                )


# ──────────────────────────────────────────────────────────────────────
# 12. TestRegionFiltering — _pick_template respects regions tag
# ──────────────────────────────────────────────────────────────────────

class TestRegionFiltering(_AnomalyTestCase):
    """Templates only spawn in their tagged regions."""

    def test_dune_sea_never_picks_coruscant_template(self):
        from engine.wilderness_anomalies import (
            _pick_template, TIER1_TEMPLATES,
        )
        coru_keys = {k for k, v in TIER1_TEMPLATES.items()
                     if "coruscant_underworld" in v["regions"]}
        rng = random.Random(0)
        for _ in range(200):
            picked = _pick_template(rng, region_slug="dune_sea")
            self.assertNotIn(picked, coru_keys)

    def test_coruscant_never_picks_dune_sea_template(self):
        from engine.wilderness_anomalies import (
            _pick_template, TIER1_TEMPLATES,
        )
        dune_keys = {k for k, v in TIER1_TEMPLATES.items()
                     if "dune_sea" in v["regions"]}
        rng = random.Random(0)
        for _ in range(200):
            picked = _pick_template(rng, region_slug="coruscant_underworld")
            self.assertNotIn(picked, dune_keys)

    def test_unknown_region_returns_none(self):
        from engine.wilderness_anomalies import _pick_template
        self.assertIsNone(
            _pick_template(random.Random(0), region_slug="endor_forest")
        )

    def test_spawn_for_unknown_region_returns_none(self):
        """spawn_anomaly_for_region in an unknown region returns None
        (graceful — log at info, don't crash)."""
        from engine.wilderness_anomalies import spawn_anomaly_for_region
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="endor_forest")
        a = _run(spawn_anomaly_for_region(
            mdb, "endor_forest", rng=random.Random(0), force=True,
        ))
        self.assertIsNone(a)

    def test_known_region_template_coverage(self):
        """Every region in known_wilderness_regions has at least one
        compatible template. Guards against the gap that SYN.7.a.fix
        was created to close."""
        from engine.wilderness_anomalies import TIER1_TEMPLATES
        known = ["dune_sea", "coruscant_underworld"]
        for region in known:
            matches = [k for k, v in TIER1_TEMPLATES.items()
                       if region in v["regions"]]
            self.assertGreater(
                len(matches), 0,
                f"region {region!r} has no compatible templates",
            )


# ──────────────────────────────────────────────────────────────────────
# 13. TestCombatResolutionSpawn — investigate on a combat anomaly
#     spawns hostile NPCs and does NOT pay reward immediately
# ──────────────────────────────────────────────────────────────────────

class TestCombatResolutionSpawn(_AnomalyTestCase):

    def _setup_combat_anomaly(self, *, template_key="tusken_party",
                              faction_id="independent"):
        """Place a manually-constructed combat anomaly in a wilderness
        room. Returns (mdb, char, anomaly)."""
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="dune_sea", zone_id=1,
            template_key=template_key, anchor_room_id=10,
            expiry=now + 600,
        )
        _anomalies["dune_sea"] = [a]
        char = _make_char(char_id=1, room_id=10, faction_id=faction_id)
        return mdb, char, a

    def test_combat_investigate_spawns_npcs(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_combat_anomaly(
            template_key="tusken_party",
        )
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "combat")
        # Tusken party has 3 hostiles per the template.
        self.assertEqual(len(out["spawned_npc_ids"]), 3)
        # NPCs exist in the room.
        npcs_in_room = _run(mdb.get_npcs_in_room(10))
        self.assertEqual(len(npcs_in_room), 3)
        # Each NPC is tagged with is_anomaly_target + anomaly_id.
        for npc in npcs_in_room:
            cfg = json.loads(npc["ai_config_json"])
            self.assertTrue(cfg.get("is_anomaly_target"))
            self.assertEqual(cfg.get("anomaly_id"), 1)
            self.assertTrue(cfg.get("hostile"))

    def test_combat_investigate_does_not_pay_immediately(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_combat_anomaly(
            template_key="tusken_party",
        )
        starting_credits = char["credits"]
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "combat")
        # No credits awarded yet (must kill the NPCs first).
        self.assertEqual(out["credits"], 0)
        self.assertEqual(char["credits"], starting_credits)
        # Anomaly NOT yet resolved.
        self.assertFalse(a.resolved)

    def test_combat_investigate_records_engagement(self):
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_combat_anomaly(
            template_key="wounded_animal", faction_id="republic",
        )
        _run(resolve_anomaly(mdb, char, 1))
        self.assertEqual(a.engaged_by, 1)
        self.assertEqual(a.engaged_faction, "republic")
        self.assertTrue(len(a.spawned_npc_ids) > 0)

    def test_combat_investigate_twice_does_not_double_spawn(self):
        """If a player already triggered the anomaly, a second
        investigate doesn't spawn a second wave."""
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup_combat_anomaly(
            template_key="tusken_party",
        )
        out1 = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out1["ok"])
        first_spawned = list(a.spawned_npc_ids)
        out2 = _run(resolve_anomaly(mdb, char, 1))
        # Second call is a no-op spawn (already engaged); engine
        # surfaces a friendly message.
        self.assertFalse(out2["ok"])
        self.assertIn("already", out2["msg"].lower())
        # NPC list unchanged.
        self.assertEqual(a.spawned_npc_ids, first_spawned)


# ──────────────────────────────────────────────────────────────────────
# 14. TestCombatAnomalyReward — award_combat_anomaly_reward fires
#     only when the last hostile dies
# ──────────────────────────────────────────────────────────────────────

class TestCombatAnomalyReward(_AnomalyTestCase):

    def _engage_combat_anomaly(self, *, template_key="wounded_animal",
                               faction_id="republic"):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, resolve_anomaly,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="dune_sea", zone_id=1,
            template_key=template_key, anchor_room_id=10,
            expiry=now + 600,
        )
        _anomalies["dune_sea"] = [a]
        char = _make_char(char_id=1, room_id=10, faction_id=faction_id)
        # Persist char to the mini-DB so award_combat_anomaly_reward
        # can re-fetch it via get_character.
        mdb._db._conn.execute(
            "INSERT INTO characters (id, name, faction_id, credits, "
            "attributes, skills, inventory, room_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (char["id"], char["name"], char["faction_id"],
             char["credits"], char["attributes"], char["skills"],
             char["inventory"], char["room_id"]))
        mdb._db._conn.commit()
        _run(resolve_anomaly(mdb, char, 1))
        return mdb, char, a

    def test_single_npc_kill_pays_reward(self):
        """wounded_animal template has 1 NPC. Killing it pays out."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a = self._engage_combat_anomaly(
            template_key="wounded_animal",
        )
        self.assertEqual(len(a.spawned_npc_ids), 1)
        npc_id = a.spawned_npc_ids[0]
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=npc_id,
            rng=random.Random(0),
        ))
        self.assertIsNotNone(payout)
        self.assertEqual(payout["anomaly_id"], 1)
        self.assertGreater(payout["credits"], 0)
        # Anomaly now resolved.
        self.assertTrue(a.resolved)
        self.assertEqual(a.resolved_by, 1)

    def test_partial_kill_does_not_pay(self):
        """tusken_party has 3 NPCs. Killing 1 of 3 should NOT pay."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a = self._engage_combat_anomaly(
            template_key="tusken_party",
        )
        self.assertEqual(len(a.spawned_npc_ids), 3)
        first = a.spawned_npc_ids[0]
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=first,
            rng=random.Random(0),
        ))
        # No payout yet — 2 hostiles remain.
        self.assertIsNone(payout)
        self.assertFalse(a.resolved)
        self.assertEqual(len(a.spawned_npc_ids), 2)

    def test_final_kill_in_group_pays(self):
        """tusken_party: kill all 3, third kill triggers payout."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a = self._engage_combat_anomaly(
            template_key="tusken_party",
        )
        npc_ids = list(a.spawned_npc_ids)
        rng = random.Random(0)
        # First two kills — no payout.
        for nid in npc_ids[:2]:
            payout = _run(award_combat_anomaly_reward(
                mdb, killer_char_id=1, npc_id=nid, rng=rng,
            ))
            self.assertIsNone(payout)
        # Third kill — payout!
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=npc_ids[2], rng=rng,
        ))
        self.assertIsNotNone(payout)
        self.assertGreater(payout["credits"], 0)
        self.assertTrue(a.resolved)

    def test_payout_grants_faction_influence(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward, TIER1_INFLUENCE_DELTA,
        )
        mdb, char, a = self._engage_combat_anomaly(
            template_key="wounded_animal", faction_id="republic",
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=a.spawned_npc_ids[0],
            rng=random.Random(0),
        ))
        self.assertEqual(payout["influence"], TIER1_INFLUENCE_DELTA)

    def test_independent_killer_no_influence(self):
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char, a = self._engage_combat_anomaly(
            template_key="wounded_animal", faction_id="independent",
        )
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=a.spawned_npc_ids[0],
            rng=random.Random(0),
        ))
        # Influence=0 for independents.
        self.assertEqual(payout["influence"], 0)

    def test_kill_after_expiry_does_not_pay(self):
        """If the anomaly expired (player took 31+ minutes), the kill
        hook should detect the gone anomaly and not pay out."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward, _prune_expired_region,
        )
        mdb, char, a = self._engage_combat_anomaly(
            template_key="wounded_animal",
        )
        # Force the anomaly to expire.
        a.expiry = time.time() - 60
        _prune_expired_region("dune_sea")
        # Now the NPC is killed.
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=a.spawned_npc_ids[0],
            rng=random.Random(0),
        ))
        self.assertIsNone(payout)

    def test_untagged_npc_kill_returns_none(self):
        """An NPC without the is_anomaly_target tag is not an anomaly
        kill — the hook returns None safely."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")
        npc_id = _run(mdb.create_npc(
            name="Random Goon", room_id=10, species="Human",
            char_sheet_json="{}",
            ai_config_json=json.dumps({"hostile": True}),
        ))
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=1, npc_id=npc_id,
            rng=random.Random(0),
        ))
        self.assertIsNone(payout)

    def test_two_player_attribution_last_killer_wins(self):
        """If two players engage, whoever lands the killing blow gets
        the reward (matches bounty board pattern)."""
        from engine.wilderness_anomalies import (
            award_combat_anomaly_reward,
        )
        mdb, char_a, a = self._engage_combat_anomaly(
            template_key="wounded_animal", faction_id="republic",
        )
        # Add a second character (a CIS hunter) to the DB.
        mdb._db._conn.execute(
            "INSERT INTO characters (id, name, faction_id, credits, "
            "attributes, skills, inventory, room_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (2, "CharB", "cis", 0, "{}", "{}", "{}", 10))
        mdb._db._conn.commit()
        # CharB lands the killing blow.
        payout = _run(award_combat_anomaly_reward(
            mdb, killer_char_id=2, npc_id=a.spawned_npc_ids[0],
            rng=random.Random(0),
        ))
        self.assertIsNotNone(payout)
        self.assertEqual(a.resolved_by, 2)
        self.assertEqual(a.resolved_faction, "cis")


# ──────────────────────────────────────────────────────────────────────
# 15. TestExpiredAnomalyNpcCleanup — surviving NPCs from an expired
#     combat anomaly get cleaned up on the next tick
# ──────────────────────────────────────────────────────────────────────

class TestExpiredAnomalyNpcCleanup(_AnomalyTestCase):

    def test_expired_combat_anomaly_cleans_up_npcs(self):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly,
            _prune_expired_region_with_cleanup,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")
        # Create an expired anomaly with a live NPC.
        npc_id = _run(mdb.create_npc(
            name="Old Hostile", room_id=10, species="Human",
            char_sheet_json="{}",
            ai_config_json=json.dumps({
                "is_anomaly_target": True, "anomaly_id": 1,
            }),
        ))
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="dune_sea", zone_id=1,
            template_key="tusken_party", anchor_room_id=10,
            expiry=now - 60,   # expired
        )
        a.spawned_npc_ids = [npc_id]
        _anomalies["dune_sea"] = [a]
        # NPC exists before cleanup.
        self.assertIsNotNone(_run(mdb.get_npc(npc_id)))
        # Cleanup pass.
        removed = _run(_prune_expired_region_with_cleanup(
            mdb, "dune_sea", now,
        ))
        self.assertEqual(removed, 1)
        # NPC is gone.
        self.assertIsNone(_run(mdb.get_npc(npc_id)))

    def test_fresh_combat_anomaly_does_not_clean_up_npcs(self):
        """An anomaly that hasn't expired yet keeps its NPCs."""
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly,
            _prune_expired_region_with_cleanup,
        )
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1,
                      wilderness_region_id="dune_sea")
        npc_id = _run(mdb.create_npc(
            name="Live Hostile", room_id=10, species="Human",
            char_sheet_json="{}",
            ai_config_json=json.dumps({
                "is_anomaly_target": True, "anomaly_id": 1,
            }),
        ))
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="dune_sea", zone_id=1,
            template_key="tusken_party", anchor_room_id=10,
            expiry=now + 600,   # fresh
        )
        a.spawned_npc_ids = [npc_id]
        _anomalies["dune_sea"] = [a]
        _run(_prune_expired_region_with_cleanup(mdb, "dune_sea", now))
        # NPC still alive.
        self.assertIsNotNone(_run(mdb.get_npc(npc_id)))


# ──────────────────────────────────────────────────────────────────────
# 16. TestFindAnomalyGlobally — combat death hook lookup
# ──────────────────────────────────────────────────────────────────────

class TestFindAnomalyGlobally(_AnomalyTestCase):

    def test_finds_anomaly_across_regions(self):
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, find_anomaly_globally,
        )
        now = time.time()
        a = WildernessAnomaly(
            id=42, region_slug="dune_sea", zone_id=1,
            template_key="tusken_party", anchor_room_id=10,
            expiry=now + 600,
        )
        b = WildernessAnomaly(
            id=43, region_slug="coruscant_underworld", zone_id=2,
            template_key="black_sun_courier", anchor_room_id=20,
            expiry=now + 600,
        )
        _anomalies["dune_sea"] = [a]
        _anomalies["coruscant_underworld"] = [b]
        self.assertIs(find_anomaly_globally(42), a)
        self.assertIs(find_anomaly_globally(43), b)

    def test_returns_none_for_missing_id(self):
        from engine.wilderness_anomalies import find_anomaly_globally
        self.assertIsNone(find_anomaly_globally(999))


if __name__ == "__main__":
    unittest.main()
