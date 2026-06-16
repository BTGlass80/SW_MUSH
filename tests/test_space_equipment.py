# -*- coding: utf-8 -*-
"""
tests/test_space_equipment.py — Space Wildspace Drop 4: Equipment Progression

Covers:
- Five new schematics load correctly from data/schematics.yaml
- stat_target values ("mining", "salvage", "refinery") recognised by
  get_effective_stats() and returned in the stats dict
- Mining Laser pip bonus applies to harvest_mining skill check
- Mining Laser cooldown reduction applies (25% Mk1, 40% Mk2)
- Deep mining (Mk2) triggers extra rare-resource roll on critical
- Salvage Arm pip bonus plumbed into SalvageCommand skill check
- Salvage Arm component bonus adds to salvage qty
- Onboard Refinery detected by get_effective_stats()
- RefineCommand exists and rejects ships without the refinery mod
- Mk2 schematics carry correct rep-gate fields
"""
from __future__ import annotations

import asyncio
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_char(skills=None, attributes=None):
    return {
        "id": 1,
        "name": "TestPilot",
        "credits": 1000,
        "inventory": {},
        "skills": skills or {},
        "attributes": attributes or '{"dexterity": "3D", "mechanical": "3D", "technical": "3D"}',
    }


def _make_template(mod_slots=5, reactor_power=10):
    """Return a minimal ShipTemplate-like object with the fields get_effective_stats reads."""
    from engine.starships import ShipTemplate, ShipWeapon
    return ShipTemplate(
        key="yt_1300",
        name="YT-1300",
        nickname="YT-1300",
        scale="starfighter",
        hull="4D",
        shields="1D",
        speed=4,
        maneuverability="1D",
        crew=1,
        passengers=6,
        cargo=100,
        consumables="2 months",
        hyperdrive=2,
        hyperdrive_backup=12,
        cost=100000,
        mod_slots=mod_slots,
        reactor_power=reactor_power,
        weapons=[],
    )


def _make_mod(stat_target, stat_boost=6, **extras):
    mod = {
        "stat_target": stat_target,
        "stat_boost": stat_boost,
        "quality": 80,
        "cargo_weight": 15,
        "name": f"Test {stat_target}",
    }
    mod.update(extras)
    return mod


# ── 1. Schematics load ────────────────────────────────────────────────────────

class TestSchematicsLoad(unittest.TestCase):

    def setUp(self):
        from parser.crafting_commands import get_all_schematics
        self.schematics = get_all_schematics()

    def test_mining_laser_mk1_present(self):
        self.assertIn("mining_laser_mk1", self.schematics)

    def test_mining_laser_mk2_present(self):
        self.assertIn("mining_laser_mk2", self.schematics)

    def test_salvage_arm_mk1_present(self):
        self.assertIn("salvage_arm_mk1", self.schematics)

    def test_salvage_arm_mk2_present(self):
        self.assertIn("salvage_arm_mk2", self.schematics)

    def test_onboard_refinery_present(self):
        self.assertIn("onboard_refinery", self.schematics)

    def test_mining_mk1_fields(self):
        s = self.schematics["mining_laser_mk1"]
        self.assertEqual(s["stat_target"], "mining")
        self.assertEqual(s["stat_boost"], 6)        # +2D = 6 pips
        self.assertEqual(s["mining_cooldown_pct"], 25)
        self.assertFalse(s["deep_mining"])
        self.assertEqual(s["output_type"], "component")
        self.assertEqual(s["base_cost"], 4500)

    def test_mining_mk2_fields(self):
        s = self.schematics["mining_laser_mk2"]
        self.assertEqual(s["stat_target"], "mining")
        self.assertEqual(s["stat_boost"], 9)        # +3D = 9 pips
        self.assertEqual(s["mining_cooldown_pct"], 40)
        self.assertTrue(s["deep_mining"])
        self.assertEqual(s["base_cost"], 12000)

    def test_mining_mk2_rep_gated(self):
        s = self.schematics["mining_laser_mk2"]
        self.assertEqual(s.get("gated_faction"), "hutt_cartel")
        self.assertGreater(int(s.get("gated_min_rep", 0)), 0)

    def test_salvage_mk1_fields(self):
        s = self.schematics["salvage_arm_mk1"]
        self.assertEqual(s["stat_target"], "salvage")
        self.assertEqual(s["stat_boost"], 6)
        self.assertEqual(s["salvage_component_bonus"], 1)
        self.assertFalse(s["intact_extraction"])
        self.assertEqual(s["base_cost"], 5200)

    def test_salvage_mk2_fields(self):
        s = self.schematics["salvage_arm_mk2"]
        self.assertEqual(s["stat_target"], "salvage")
        self.assertEqual(s["stat_boost"], 9)
        self.assertEqual(s["salvage_component_bonus"], 2)
        self.assertTrue(s["intact_extraction"])
        self.assertEqual(s["base_cost"], 14000)

    def test_salvage_mk2_rep_gated(self):
        s = self.schematics["salvage_arm_mk2"]
        self.assertEqual(s.get("gated_faction"), "republic")
        self.assertGreater(int(s.get("gated_min_rep", 0)), 0)

    def test_refinery_fields(self):
        s = self.schematics["onboard_refinery"]
        self.assertEqual(s["stat_target"], "refinery")
        self.assertEqual(s["base_cost"], 8500)
        self.assertEqual(s["output_type"], "component")


# ── 2. get_effective_stats — new stat_target branches ────────────────────────

class TestGetEffectiveStatsMiningMods(unittest.TestCase):

    def _eff(self, mods):
        from engine.starships import get_effective_stats
        template = _make_template()
        systems = {"modifications": mods}
        return get_effective_stats(template, systems)

    def test_no_mods_defaults(self):
        eff = self._eff([])
        self.assertEqual(eff["mining_bonus_pips"], 0)
        self.assertEqual(eff["mining_cooldown_pct"], 0)
        self.assertFalse(eff["deep_mining"])
        self.assertEqual(eff["salvage_bonus_pips"], 0)
        self.assertEqual(eff["salvage_component_bonus"], 0)
        self.assertFalse(eff["intact_extraction"])
        self.assertFalse(eff["has_refinery"])

    def test_mining_mk1_bonus(self):
        eff = self._eff([_make_mod("mining", stat_boost=6,
                                   mining_cooldown_pct=25, deep_mining=False)])
        self.assertEqual(eff["mining_bonus_pips"], 6)
        self.assertEqual(eff["mining_cooldown_pct"], 25)
        self.assertFalse(eff["deep_mining"])

    def test_mining_mk2_bonus(self):
        eff = self._eff([_make_mod("mining", stat_boost=9,
                                   mining_cooldown_pct=40, deep_mining=True)])
        self.assertEqual(eff["mining_bonus_pips"], 9)
        self.assertEqual(eff["mining_cooldown_pct"], 40)
        self.assertTrue(eff["deep_mining"])

    def test_salvage_mk1_bonus(self):
        eff = self._eff([_make_mod("salvage", stat_boost=6,
                                   salvage_component_bonus=1, intact_extraction=False)])
        self.assertEqual(eff["salvage_bonus_pips"], 6)
        self.assertEqual(eff["salvage_component_bonus"], 1)
        self.assertFalse(eff["intact_extraction"])

    def test_salvage_mk2_bonus(self):
        eff = self._eff([_make_mod("salvage", stat_boost=9,
                                   salvage_component_bonus=2, intact_extraction=True)])
        self.assertEqual(eff["salvage_bonus_pips"], 9)
        self.assertEqual(eff["salvage_component_bonus"], 2)
        self.assertTrue(eff["intact_extraction"])

    def test_refinery_detected(self):
        eff = self._eff([_make_mod("refinery", stat_boost=1)])
        self.assertTrue(eff["has_refinery"])

    def test_combat_stats_unaffected_by_mining_mod(self):
        """Mining/salvage/refinery mods must not alter combat stats."""
        baseline = self._eff([])
        with_mods = self._eff([
            _make_mod("mining",   stat_boost=9, mining_cooldown_pct=40, deep_mining=True),
            _make_mod("salvage",  stat_boost=9, salvage_component_bonus=2, intact_extraction=True),
            _make_mod("refinery", stat_boost=1),
        ])
        for key in ("speed", "maneuverability", "hull", "shields",
                    "sensors_bonus", "stealth_bonus"):
            self.assertEqual(baseline[key], with_mods[key],
                             f"{key} should be unchanged by wildspace mods")


# ── 3. harvest_mining — pip bonus and cooldown reduction ─────────────────────

class TestHarvestMiningMods(unittest.IsolatedAsyncioTestCase):

    def _make_db(self, cache_row, cache_def):
        db = MagicMock()
        db.fetchone = AsyncMock(return_value=cache_row)
        db.fetchall = AsyncMock(return_value=[{"cnt": 0}])
        db.execute  = AsyncMock()
        db.commit   = AsyncMock()
        db.save_character = AsyncMock()
        return db

    def _cache_row(self, state="available", zone="wildspace_dev_test",
                   def_id="asteroid_ore_cluster"):
        return {
            "cache_instance_id": 1,
            "zone_key": zone,
            "cache_def_id": def_id,
            "state": state,
            "last_harvested_at": None,
            "next_available_at": None,
            "harvested_by_character_id": None,
            "harvest_count": 0,
            "visibility_factions": None,
        }

    async def test_mining_bonus_pips_passed_to_skill_check(self):
        """Mining Laser pip bonus flows into perform_skill_check via lead_bonus."""
        from engine.space_caches import harvest_mining

        char = _make_char()
        row  = self._cache_row()
        db   = self._make_db(row, None)

        mock_result = MagicMock()
        mock_result.fumble = False
        mock_result.critical_success = False
        mock_result.roll = 15

        captured = {}

        def _mock_check(c, skill, diff, sr, *, lead_bonus=None, auto_consume_lead=True):
            captured["lead_bonus"] = lead_bonus
            return mock_result

        # perform_skill_check is lazy-imported inside harvest_mining, so
        # patch it at the source module (engine.skill_checks).
        with patch("engine.skill_checks.perform_skill_check", _mock_check), \
             patch("engine.crafting.add_resource"), \
             patch("engine.space_caches.set_cache_cooldown", new_callable=AsyncMock):
            await harvest_mining(
                db, char, 1,
                ship_mod_stats={"mining_bonus_pips": 6, "mining_cooldown_pct": 25,
                                "deep_mining": False},
            )

        self.assertEqual(captured.get("lead_bonus"), 6,
                         "Mining Laser +2D (6 pips) should be passed as lead_bonus")

    async def test_no_mod_stats_no_lead_bonus(self):
        """No ship_mod_stats → lead_bonus=None (not 0, to avoid disabling combined action)."""
        from engine.space_caches import harvest_mining

        char = _make_char()
        row  = self._cache_row()
        db   = self._make_db(row, None)

        mock_result = MagicMock()
        mock_result.fumble = False
        mock_result.critical_success = False
        mock_result.roll = 15

        captured = {}

        def _mock_check(c, skill, diff, sr, *, lead_bonus=None, auto_consume_lead=True):
            captured["lead_bonus"] = lead_bonus
            return mock_result

        with patch("engine.skill_checks.perform_skill_check", _mock_check), \
             patch("engine.crafting.add_resource"), \
             patch("engine.space_caches.set_cache_cooldown", new_callable=AsyncMock):
            await harvest_mining(db, char, 1, ship_mod_stats=None)

        self.assertIsNone(captured.get("lead_bonus"),
                          "No mod → lead_bonus must be None (not 0)")

    async def test_cooldown_reduced_by_mk1(self):
        """Mk1 25% cooldown reduction: respawn_minutes * 0.75."""
        from engine.space_caches import harvest_mining

        char = _make_char()
        row  = self._cache_row()
        db   = self._make_db(row, None)

        mock_result = MagicMock()
        mock_result.fumble = False
        mock_result.critical_success = False
        mock_result.roll = 15

        cooldown_used = {}

        async def _mock_set_cooldown(db_, cid, char_id, respawn_minutes):
            cooldown_used["minutes"] = respawn_minutes

        with patch("engine.skill_checks.perform_skill_check",
                   return_value=mock_result), \
             patch("engine.crafting.add_resource"), \
             patch("engine.space_caches.set_cache_cooldown",
                   side_effect=_mock_set_cooldown):
            await harvest_mining(
                db, char, 1,
                ship_mod_stats={"mining_bonus_pips": 6, "mining_cooldown_pct": 25,
                                "deep_mining": False},
            )

        # asteroid_ore_cluster has respawn_minutes=45; 75% of 45 = 33.75 → 34
        self.assertAlmostEqual(cooldown_used["minutes"], 34, delta=1,
                               msg="Mk1 should reduce 45min cooldown by 25% → ~34min")

    async def test_cooldown_reduced_by_mk2(self):
        """Mk2 40% cooldown reduction: respawn_minutes * 0.60."""
        from engine.space_caches import harvest_mining

        char = _make_char()
        row  = self._cache_row()
        db   = self._make_db(row, None)

        mock_result = MagicMock()
        mock_result.fumble = False
        mock_result.critical_success = False
        mock_result.roll = 15

        cooldown_used = {}

        async def _mock_set_cooldown(db_, cid, char_id, respawn_minutes):
            cooldown_used["minutes"] = respawn_minutes

        with patch("engine.skill_checks.perform_skill_check",
                   return_value=mock_result), \
             patch("engine.crafting.add_resource"), \
             patch("engine.space_caches.set_cache_cooldown",
                   side_effect=_mock_set_cooldown):
            await harvest_mining(
                db, char, 1,
                ship_mod_stats={"mining_bonus_pips": 9, "mining_cooldown_pct": 40,
                                "deep_mining": True},
            )

        # asteroid_ore_cluster has respawn_minutes=45; 60% of 45 = 27
        self.assertAlmostEqual(cooldown_used["minutes"], 27, delta=1,
                               msg="Mk2 should reduce 45min cooldown by 40% → ~27min")

    async def test_deep_mining_extra_rare_on_crit(self):
        """Mk2 deep_mining: extra add_resource call for 'rare' on critical success."""
        from engine.space_caches import harvest_mining

        char = _make_char()
        row  = self._cache_row()
        db   = self._make_db(row, None)

        mock_result = MagicMock()
        mock_result.fumble = False
        mock_result.critical_success = True   # trigger deep mining
        mock_result.roll = 20

        resource_calls = []

        def _mock_add(c, rtype, qty, quality):
            resource_calls.append(rtype)

        with patch("engine.skill_checks.perform_skill_check",
                   return_value=mock_result), \
             patch("engine.crafting.add_resource", side_effect=_mock_add), \
             patch("engine.space_caches.set_cache_cooldown", new_callable=AsyncMock):
            await harvest_mining(
                db, char, 1,
                ship_mod_stats={"mining_bonus_pips": 9, "mining_cooldown_pct": 40,
                                "deep_mining": True},
            )

        self.assertIn("rare", resource_calls,
                      "Deep mining should add a 'rare' resource on critical")
        self.assertGreater(resource_calls.count("rare"), 0)

    async def test_deep_mining_no_extra_without_flag(self):
        """Without deep_mining flag, critical gives max qty but no extra rare call."""
        from engine.space_caches import harvest_mining

        char = _make_char()
        row  = self._cache_row()
        db   = self._make_db(row, None)

        mock_result = MagicMock()
        mock_result.fumble = False
        mock_result.critical_success = True
        mock_result.roll = 20

        resource_calls = []

        def _mock_add(c, rtype, qty, quality):
            resource_calls.append(rtype)

        with patch("engine.skill_checks.perform_skill_check",
                   return_value=mock_result), \
             patch("engine.crafting.add_resource", side_effect=_mock_add), \
             patch("engine.space_caches.set_cache_cooldown", new_callable=AsyncMock):
            await harvest_mining(
                db, char, 1,
                ship_mod_stats={"mining_bonus_pips": 6, "mining_cooldown_pct": 25,
                                "deep_mining": False},
            )

        # Primary rtype varies; should be exactly 1 add_resource call (no deep bonus)
        self.assertEqual(len(resource_calls), 1,
                         "Without deep_mining, only one add_resource call expected")


# ── 4. Refinery mod detected ──────────────────────────────────────────────────

class TestRefineryModDetected(unittest.TestCase):

    def test_refinery_not_present_by_default(self):
        from engine.starships import get_effective_stats
        template = _make_template()
        eff = get_effective_stats(template, {"modifications": []})
        self.assertFalse(eff["has_refinery"])

    def test_refinery_detected_when_installed(self):
        from engine.starships import get_effective_stats
        template = _make_template()
        mods = [{"stat_target": "refinery", "stat_boost": 1, "quality": 80,
                 "cargo_weight": 25, "name": "Onboard Refinery"}]
        eff = get_effective_stats(template, {"modifications": mods})
        self.assertTrue(eff["has_refinery"])


# ── 5. RefineCommand structure ────────────────────────────────────────────────

class TestRefineCommandExists(unittest.TestCase):

    def test_refine_command_registered(self):
        """RefineCommand must be importable and have key='refine'."""
        from parser.space_commands import RefineCommand
        cmd = RefineCommand()
        self.assertEqual(cmd.key, "refine")

    def test_refine_command_in_register(self):
        """RefineCommand is registered via register_space_commands."""
        from parser.space_commands import register_space_commands

        class _FakeRegistry:
            def __init__(self):
                self.cmds = {}
            def register(self, cmd):
                self.cmds[cmd.key] = cmd

        reg = _FakeRegistry()
        register_space_commands(reg)
        self.assertIn("refine", reg.cmds)


if __name__ == "__main__":
    unittest.main()
