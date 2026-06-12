# -*- coding: utf-8 -*-
"""
tests/test_lane_a_phase_b_spawner.py

Lane A **Phase B** (T2.WENC.b) — the encounter→spawner bridge that turns the
faithful creature library into live, faithfully-statted encounters.

These run against the REAL loaders/builders + the REAL combat weapon path
(engine.character.Character + engine.npc_combat_ai._get_npc_weapon), and the
spawn bridge against a fake db that records create_npc calls. The live
spawn+combat (db.create_npc + the combat loop) is the Windows gate; the pure
substance — the faithful natural-attack resolver, the sheet/ai builders, the
_get_npc_weapon enhancement, and the bridge's spawn logic — is pinned here.
"""
from __future__ import annotations

import asyncio
import json
import unittest

from engine import creature_library as CL


# ═══════════════════════════════════════════════════════════════════════════
# 1. Faithful natural-attack resolver
# ═══════════════════════════════════════════════════════════════════════════

class TestNaturalAttackResolver(unittest.TestCase):

    def setUp(self):
        self.lib = CL.load_creature_library()

    def _dmg(self, cid):
        return CL.resolve_natural_attack(self.lib[cid])

    def test_library_loaded(self):
        self.assertGreaterEqual(len(self.lib), 14)
        self.assertIn("worrt", self.lib)
        self.assertIn("stalker_lizard", self.lib)

    def test_absolute_form(self):
        r = self._dmg("worrt")              # "1D"
        self.assertEqual(r["damage"], "1D")
        self.assertFalse(r["special"])
        self.assertEqual(r["skill"], "brawling")

    def test_str_plus_dice(self):
        self.assertEqual(self._dmg("hitcher_crab")["damage"], "2D")   # STR1D + "STR+1D"
        self.assertEqual(self._dmg("wrix")["damage"], "4D")           # STR3D + "STR+1D"

    def test_str_plus_dice_and_pips(self):
        self.assertEqual(self._dmg("stalker_lizard")["damage"], "5D+2")  # STR3D + "STR+2D+2"
        self.assertEqual(self._dmg("yeomet")["damage"], "3D+1")          # STR1D+1 + "STR+2D"

    def test_pip_normalization(self):
        # magus STR 1D+1 + "STR+2"  -> 1D + 3 pips -> normalizes to 2D
        self.assertEqual(self._dmg("magus")["damage"], "2D")
        # borcatu STR 1D+2 + "STR+2" -> 1D + 4 pips -> 2D+1
        self.assertEqual(self._dmg("borcatu")["damage"], "2D+1")

    def test_str_only(self):
        # winged_xendrite "STR (negligible..)" -> bare STR (1D), not special-fallback
        self.assertEqual(self._dmg("winged_xendrite")["damage"], "1D")

    def test_leading_clean_then_rider_is_faithful_and_flagged(self):
        # voroos "STR+1D, then grasp" -> faithful 7D (STR 6D) AND special-flagged
        r = self._dmg("voroos")
        self.assertEqual(r["damage"], "7D")
        self.assertTrue(r["special"])

    def test_special_prose_falls_back_to_bare_str(self):
        # poison / grapple / multi-round riders can't be a damage number yet:
        # base damage = bare STR, special True (flavor carries the rider).
        for cid, str_dmg in (("spor_crawler", "0D+2"),  # "Poison 5D"
                             ("glim_worm", "1D"),        # "opposed (..)"
                             ("somago", "3D+1")):        # "+3D/round.."
            r = self._dmg(cid)
            self.assertEqual(r["damage"], str_dmg, cid)
            self.assertTrue(r["special"], cid)

    def test_every_creature_resolves_nonempty(self):
        for cid, c in self.lib.items():
            r = CL.resolve_natural_attack(c)
            self.assertTrue(r["damage"], cid)
            self.assertRegex(r["damage"], r"^\d+D(\+\d+)?$", cid)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Spawn-ready builders
# ═══════════════════════════════════════════════════════════════════════════

class TestBuilders(unittest.TestCase):

    def setUp(self):
        self.c = CL.get_creature("stalker_lizard")

    def test_char_sheet_carries_resolved_natural_attack(self):
        sheet = CL.build_creature_char_sheet(self.c)
        self.assertEqual(sheet["weapon"], "")          # no registry weapon
        self.assertEqual(sheet["natural_attack"]["damage"], "5D+2")
        self.assertEqual(sheet["natural_attack"]["skill"], "brawling")
        self.assertIn("attributes", sheet)
        self.assertIn("strength", sheet["attributes"])

    def test_ai_config_hostile_and_ids(self):
        cfg = CL.build_creature_ai_config(self.c, encounter_id="e1", hostile=True)
        self.assertTrue(cfg["hostile"])
        self.assertEqual(cfg["creature_id"], "stalker_lizard")
        self.assertEqual(cfg["encounter_id"], "e1")
        self.assertEqual(cfg["combat_behavior"], "aggressive")
        self.assertEqual(cfg["natural_attack_damage"], "5D+2")

    def test_ai_config_nonhostile_special_note(self):
        spor = CL.get_creature("spor_crawler")   # poison -> special
        cfg = CL.build_creature_ai_config(spor, hostile=False)
        self.assertFalse(cfg["hostile"])
        self.assertIn("natural_attack_note", cfg)   # special flavor carried

    def test_spawn_count(self):
        self.assertEqual(CL.creature_spawn_count(self.c, {"count": 3}), 3)
        # pack_count low end when no explicit count
        self.c_pack = CL.get_creature("glim_worm")  # pack_count [3,4]
        self.assertEqual(CL.creature_spawn_count(self.c_pack, {}), 3)
        # default 1 for a solo creature with no pack
        solo = dict(self.c); solo.pop("pack_count", None)
        self.assertEqual(CL.creature_spawn_count(solo, {}), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Combat path honors the natural attack (the _get_npc_weapon enhancement)
# ═══════════════════════════════════════════════════════════════════════════

class TestCombatWeaponHook(unittest.TestCase):

    def test_get_npc_weapon_uses_natural_attack(self):
        from engine.character import Character
        from engine.npc_combat_ai import _get_npc_weapon
        sheet = CL.build_creature_char_sheet(CL.get_creature("stalker_lizard"))
        char = Character.from_npc_sheet(999, sheet)
        skill, damage, weapon_key = _get_npc_weapon(char)
        self.assertEqual(skill, "brawling")
        self.assertEqual(damage, "5D+2")     # faithful, not bare STR (3D)
        self.assertEqual(weapon_key, "")

    def test_ordinary_npc_unaffected(self):
        # A sheet without natural_attack still falls through to the normal path.
        from engine.character import Character
        from engine.npc_combat_ai import _get_npc_weapon
        sheet = {"name": "Thug",
                 "attributes": {"strength": "3D", "dexterity": "3D"},
                 "skills": {"brawling": "4D"}}
        char = Character.from_npc_sheet(1, sheet)
        self.assertEqual(char.natural_attack_damage, "")
        skill, damage, _ = _get_npc_weapon(char)
        self.assertEqual(skill, "brawling")
        self.assertEqual(damage, "3D")       # bare STR (unchanged behavior)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Spawn bridge (against a fake db)
# ═══════════════════════════════════════════════════════════════════════════

class _Entry:
    """Minimal stand-in for engine.wilderness_encounters.EncounterEntry."""
    def __init__(self, id, type, payload=None):
        self.id = id
        self.type = type
        self.payload = payload or {}


class _FakeDB:
    def __init__(self):
        self.created = []
        self._next = 5000

    async def create_npc(self, *, name, room_id, species, description,
                         char_sheet_json, ai_config_json):
        self._next += 1
        self.created.append({
            "id": self._next, "name": name, "room_id": room_id,
            "species": species, "char_sheet": json.loads(char_sheet_json),
            "ai": json.loads(ai_config_json),
        })
        return self._next


class TestSpawnBridge(unittest.TestCase):

    def _run(self, coro):
        # Py 3.12+/3.14: asyncio.get_event_loop() raises when no loop is
        # set in the thread. Use asyncio.run(), which creates + closes a
        # fresh loop per call (matches the other test harnesses).
        return asyncio.run(coro)

    def test_hostile_spawns_faithful_creatures(self):
        from engine.wilderness_encounter_runtime import spawn_encounter_creatures
        db = _FakeDB()
        entry = _Entry("stalker_ambush", "hostile",
                       {"npc_template": "stalker_lizard", "count": 2})
        ids = self._run(spawn_encounter_creatures(db, entry, room_id=42))
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(db.created), 2)
        # faithful damage made it into the spawned sheet
        self.assertEqual(
            db.created[0]["char_sheet"]["natural_attack"]["damage"], "5D+2")
        self.assertEqual(db.created[0]["room_id"], 42)
        self.assertTrue(db.created[0]["ai"]["hostile"])
        # multi-spawn gets numbered names
        self.assertIn("#", db.created[1]["name"])

    def test_non_hostile_spawns_but_not_aggressive(self):
        from engine.wilderness_encounter_runtime import spawn_encounter_creatures
        db = _FakeDB()
        entry = _Entry("worrt_sighting", "non_hostile",
                       {"npc_template": "worrt", "count": 1})
        ids = self._run(spawn_encounter_creatures(db, entry, room_id=7))
        self.assertEqual(len(ids), 1)
        self.assertFalse(db.created[0]["ai"]["hostile"])
        self.assertEqual(db.created[0]["name"], "Worrt")   # no # when count==1

    def test_no_spawn_for_non_creature_types(self):
        from engine.wilderness_encounter_runtime import spawn_encounter_creatures
        db = _FakeDB()
        for entry in (_Entry("w", "weather", {}),
                      _Entry("a", "anomaly", {"npc_template": "stalker_lizard"}),
                      _Entry("h", "hostile", {}),                 # no template
                      _Entry("h2", "hostile", {"npc_template": "nope"})):  # unknown
            ids = self._run(spawn_encounter_creatures(db, entry, room_id=1))
            self.assertEqual(ids, [], entry.id)
        self.assertEqual(db.created, [])


if __name__ == "__main__":
    unittest.main()
