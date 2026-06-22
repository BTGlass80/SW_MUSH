# -*- coding: utf-8 -*-
"""
tests/test_drop_mob_grind_kuat_city.py

Verifies the Kuat City surface + Ring Transit Hub hostile-mob grind expansion
(data/worlds/clone_wars/npcs_drop_mob_grind_kuat_city.yaml).

All six NPCs must satisfy engine/hunting_rewards.is_huntable_mob():
  - ai_config.hostile = true
  - none of the special-reward markers present

Test sections:
  1. TestYamlParses        — file exists and loads correctly
  2. TestAllHostile        — every NPC has hostile: true
  3. TestNoSpecialMarkers  — none of the huntable-exclusion flags set
  4. TestHuntableGate      — is_huntable_mob() returns True for each
  5. TestEraClean          — no Imperial/Empire/Rebel/TIE strings
  6. TestRoomsExist        — every room name resolves in the CW planet YAMLs
  7. TestEraManifestRef    — file is wired into era.yaml content_refs.npcs
  8. TestWeaponKeysValid   — non-empty weapon keys exist in data/weapons.yaml
"""
from __future__ import annotations

import json
import os
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CW_DIR = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
MOB_FILE = os.path.join(CW_DIR, "npcs_drop_mob_grind_kuat_city.yaml")
ERA_FILE = os.path.join(CW_DIR, "era.yaml")
WEAPONS_FILE = os.path.join(PROJECT_ROOT, "data", "weapons.yaml")

_SPECIAL_MARKERS = (
    "is_bounty_target",
    "is_anomaly_target",
    "is_wilderness_encounter",
    "is_dsp_hunter",
    "is_intel_handler",
    "chain_enemy_template",
    "vendor",
)


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_cw_room_names():
    """Walk every planet YAML in CW and collect every room name."""
    names = set()
    era = _load_yaml(ERA_FILE)
    planet_refs = (era.get("content_refs") or {}).get("planets", [])
    for rel in planet_refs:
        full = os.path.normpath(os.path.join(CW_DIR, rel))
        if not os.path.exists(full):
            continue
        data = _load_yaml(full)
        for room in (data.get("rooms") or []):
            rname = room.get("name")
            if rname:
                names.add(rname)
    return names


class TestYamlParses(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(os.path.exists(MOB_FILE), f"Missing: {MOB_FILE}")

    def test_loads_npcs_key(self):
        data = _load_yaml(MOB_FILE)
        self.assertIn("npcs", data)
        self.assertIsInstance(data["npcs"], list)

    def test_six_npcs(self):
        data = _load_yaml(MOB_FILE)
        self.assertGreaterEqual(len(data["npcs"]), 6, "Expected at least 6 hostile mobs")


class TestAllHostile(unittest.TestCase):
    def test_hostile_true_on_every_npc(self):
        data = _load_yaml(MOB_FILE)
        for npc in data["npcs"]:
            ai = npc.get("ai_config", {})
            self.assertTrue(
                ai.get("hostile") is True,
                f"NPC '{npc.get('name')}' must have ai_config.hostile = true",
            )


class TestNoSpecialMarkers(unittest.TestCase):
    def test_no_exclusion_flags(self):
        data = _load_yaml(MOB_FILE)
        for npc in data["npcs"]:
            ai = npc.get("ai_config", {})
            for marker in _SPECIAL_MARKERS:
                self.assertFalse(
                    ai.get(marker),
                    f"NPC '{npc.get('name')}' must NOT have {marker} (excludes from hunt reward)",
                )


class TestHuntableGate(unittest.TestCase):
    def test_is_huntable_mob_returns_true(self):
        from engine.hunting_rewards import is_huntable_mob

        data = _load_yaml(MOB_FILE)
        for npc in data["npcs"]:
            row = {"ai_config_json": json.dumps(npc.get("ai_config", {}))}
            self.assertTrue(
                is_huntable_mob(row),
                f"is_huntable_mob() returned False for '{npc.get('name')}'",
            )


class TestEraClean(unittest.TestCase):
    _BANNED = ("imperial", " empire", " rebel ", " tie fighter", " tie/")

    def test_no_banned_strings(self):
        with open(MOB_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        non_comment = "\n".join(
            ln for ln in lines if not ln.lstrip().startswith("#")
        ).lower()
        for banned in self._BANNED:
            self.assertNotIn(
                banned, non_comment,
                f"Era violation: '{banned}' found in non-comment content",
            )


class TestRoomsExist(unittest.TestCase):
    def test_all_rooms_resolve(self):
        known = _all_cw_room_names()
        if not known:
            self.skipTest("Could not load CW room names (planet YAMLs missing)")
        data = _load_yaml(MOB_FILE)
        for npc in data["npcs"]:
            room = npc.get("room", "")
            self.assertIn(
                room, known,
                f"NPC '{npc.get('name')}': room '{room}' not found in CW planet YAMLs",
            )


class TestEraManifestRef(unittest.TestCase):
    def test_file_in_era_yaml(self):
        era = _load_yaml(ERA_FILE)
        npcs_refs = (era.get("content_refs") or {}).get("npcs", [])
        ref_name = "npcs_drop_mob_grind_kuat_city.yaml"
        self.assertIn(
            ref_name, npcs_refs,
            f"'{ref_name}' must be listed in era.yaml content_refs.npcs",
        )


class TestWeaponKeysValid(unittest.TestCase):
    def test_weapon_keys_in_weapons_yaml(self):
        weapons = _load_yaml(WEAPONS_FILE)
        valid_keys = set(weapons.keys())
        data = _load_yaml(MOB_FILE)
        for npc in data["npcs"]:
            weapon = (npc.get("char_sheet") or {}).get("weapon", "")
            if weapon:
                self.assertIn(
                    weapon, valid_keys,
                    f"NPC '{npc.get('name')}': weapon key '{weapon}' not in weapons.yaml",
                )


if __name__ == "__main__":
    unittest.main()
