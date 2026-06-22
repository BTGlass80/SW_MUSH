# -*- coding: utf-8 -*-
"""
tests/test_drop_mob_grind_geonosis_ey_akh.py

Verifies the Geonosis E'Y-Akh wilderness hostile-mob grind batch
(data/worlds/clone_wars/npcs_drop_mob_grind_geonosis_ey_akh.yaml).

All six NPCs must satisfy engine/hunting_rewards.is_huntable_mob():
  - ai_config.hostile = true
  - none of the special-reward markers present

These NPCs target WILDERNESS LANDMARK rooms (coordinate-based; not
planet-YAML rooms) defined in data/worlds/clone_wars/wilderness/ey_akh.yaml.
TestRoomsExist therefore scans wilderness YAML landmark names.

The file uses the `wilderness_npcs:` top-level key and is registered under
content_refs.wilderness_npcs (not content_refs.npcs) in era.yaml.

Test sections:
  1. TestYamlParses         — file exists and loads correctly
  2. TestAllHostile         — every NPC has hostile: true
  3. TestNoSpecialMarkers   — none of the huntable-exclusion flags set
  4. TestHuntableGate       — is_huntable_mob() returns True for each
  5. TestEraClean           — no Imperial/Empire/Rebel/TIE strings
  6. TestRoomsExist         — every room name resolves in wilderness YAMLs
  7. TestEraManifestRef     — file is wired into era.yaml wilderness_npcs
  8. TestWeaponKeysValid    — non-empty weapon keys exist in data/weapons.yaml
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
MOB_FILE = os.path.join(CW_DIR, "npcs_drop_mob_grind_geonosis_ey_akh.yaml")
ERA_FILE = os.path.join(CW_DIR, "era.yaml")
WEAPONS_FILE = os.path.join(PROJECT_ROOT, "data", "weapons.yaml")
WILDERNESS_DIR = os.path.join(CW_DIR, "wilderness")

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


def _all_wilderness_room_names():
    """
    Walk every wilderness YAML in the clone_wars wilderness directory
    and collect landmark names.  E'Y-Akh mob NPCs are placed in
    wilderness landmark rooms resolved at runtime via
    _resolve_wilderness_room_id (DB lookup by name).
    """
    names = set()
    if os.path.isdir(WILDERNESS_DIR):
        for fn in os.listdir(WILDERNESS_DIR):
            if not fn.endswith(".yaml"):
                continue
            full = os.path.join(WILDERNESS_DIR, fn)
            try:
                data = _load_yaml(full)
            except Exception:
                continue
            for lm in (data.get("landmarks") or []):
                lname = lm.get("name")
                if lname:
                    names.add(lname)
    return names


class TestYamlParses(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(os.path.exists(MOB_FILE), f"Missing: {MOB_FILE}")

    def test_loads_wilderness_npcs_key(self):
        data = _load_yaml(MOB_FILE)
        self.assertIn(
            "wilderness_npcs", data,
            "E'Y-Akh mob file must use top-level 'wilderness_npcs:' key "
            "(not 'npcs:') so the wilderness loader resolves rooms via DB",
        )
        self.assertIsInstance(data["wilderness_npcs"], list)

    def test_six_npcs(self):
        data = _load_yaml(MOB_FILE)
        self.assertGreaterEqual(
            len(data["wilderness_npcs"]), 6,
            "Expected at least 6 hostile mobs",
        )


class TestAllHostile(unittest.TestCase):
    def test_hostile_true_on_every_npc(self):
        data = _load_yaml(MOB_FILE)
        for npc in data["wilderness_npcs"]:
            ai = npc.get("ai_config", {})
            self.assertTrue(
                ai.get("hostile") is True,
                f"NPC '{npc.get('name')}' must have ai_config.hostile = true",
            )


class TestNoSpecialMarkers(unittest.TestCase):
    def test_no_exclusion_flags(self):
        data = _load_yaml(MOB_FILE)
        for npc in data["wilderness_npcs"]:
            ai = npc.get("ai_config", {})
            for marker in _SPECIAL_MARKERS:
                self.assertFalse(
                    ai.get(marker),
                    f"NPC '{npc.get('name')}' must NOT have {marker}",
                )


class TestHuntableGate(unittest.TestCase):
    def test_is_huntable_mob_returns_true(self):
        from engine.hunting_rewards import is_huntable_mob

        data = _load_yaml(MOB_FILE)
        for npc in data["wilderness_npcs"]:
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
                banned,
                non_comment,
                f"Era-banned string '{banned}' found in mob file",
            )


class TestRoomsExist(unittest.TestCase):
    def test_all_rooms_in_wilderness_yaml(self):
        """
        Every room name in the file must match a wilderness landmark name.
        These NPCs are placed via _resolve_wilderness_room_id (DB lookup
        on wilderness_region_id IS NOT NULL rooms), not the planet YAML bundle.
        """
        data = _load_yaml(MOB_FILE)
        known_rooms = _all_wilderness_room_names()
        for npc in data["wilderness_npcs"]:
            room = npc.get("room", "")
            self.assertIn(
                room,
                known_rooms,
                f"NPC '{npc.get('name')}' room '{room}' not found in "
                f"any wilderness YAML landmark name",
            )


class TestEraManifestRef(unittest.TestCase):
    def test_file_in_wilderness_npcs(self):
        """
        The file must be referenced under content_refs.wilderness_npcs
        (not content_refs.npcs) in era.yaml so the wilderness loader
        resolves its room names via DB instead of the planet YAML bundle.
        """
        era = _load_yaml(ERA_FILE)
        refs = (era.get("content_refs") or {}).get("wilderness_npcs", [])
        ref_name = "npcs_drop_mob_grind_geonosis_ey_akh.yaml"
        self.assertTrue(
            any(ref_name in str(r) for r in refs),
            f"'{ref_name}' not found in era.yaml content_refs.wilderness_npcs",
        )

    def test_file_not_in_npcs(self):
        """
        The file must NOT be in content_refs.npcs — that path cannot
        resolve wilderness landmark rooms and would fallback to Market Row.
        """
        era = _load_yaml(ERA_FILE)
        refs = (era.get("content_refs") or {}).get("npcs", [])
        ref_name = "npcs_drop_mob_grind_geonosis_ey_akh.yaml"
        self.assertFalse(
            any(ref_name in str(r) for r in refs),
            f"'{ref_name}' found in content_refs.npcs — must be in wilderness_npcs",
        )


class TestWeaponKeysValid(unittest.TestCase):
    def test_non_empty_weapons_exist_in_registry(self):
        weapons_data = _load_yaml(WEAPONS_FILE)
        weapon_keys = set(weapons_data.keys()) if isinstance(weapons_data, dict) else set()

        data = _load_yaml(MOB_FILE)
        for npc in data["wilderness_npcs"]:
            weapon = (npc.get("char_sheet") or {}).get("weapon", "")
            if weapon and weapon not in ("", "none"):
                self.assertIn(
                    weapon,
                    weapon_keys,
                    f"NPC '{npc.get('name')}' weapon '{weapon}' not in data/weapons.yaml",
                )


if __name__ == "__main__":
    unittest.main()
