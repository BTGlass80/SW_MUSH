# -*- coding: utf-8 -*-
"""
tests/test_drop_kamino_interiors_ambient.py
Verifies the Kamino interior ambient NPC batch
(data/worlds/clone_wars/npcs_drop_kamino_interiors_ambient.yaml).

Covers:
  1. File exists and YAML parses cleanly
  2. All 4 expected NPCs present by name
  3. Required fields: name, room, species, description, char_sheet, ai_config
  4. All NPCs are non-hostile (ambient, not grind mobs)
  5. No special-reward markers (is_bounty_target / vendor / etc.)
  6. Room references resolve to real Clone Wars rooms
  7. Era-cleanness: no Imperial/Empire/Rebel/TIE in player-facing strings
  8. File is registered in era.yaml content_refs.npcs
  9. Pip-sanity: no ND+3 dice codes (only +0, +1, +2 are valid)
 10. Stat blocks have the six canonical attributes
"""
from __future__ import annotations

import os
import re
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CW_DIR = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
YAML_PATH = os.path.join(CW_DIR, "npcs_drop_kamino_interiors_ambient.yaml")
ERA_PATH = os.path.join(CW_DIR, "era.yaml")

EXPECTED_NPCS = {
    "Kaminoan Attendant Kel Avon",
    "Kaminoan Growth Technician Vel Thun",
    "Clone Trooper CT-2711 'Drift'",
    "Kaminoan Equipment Manager Vas Toru",
}

EXPECTED_ROOMS = {
    "Kaminoan Attendant Kel Avon": "Kamino - Tipoca City Arrivals Hall",
    "Kaminoan Growth Technician Vel Thun": "Kamino - Growth Chambers",
    "Clone Trooper CT-2711 'Drift'": "Kamino - Clone Barracks",
    "Kaminoan Equipment Manager Vas Toru": "Kamino - Clone Equipment Bay",
}

_SPECIAL_REWARD_KEYS = {
    "is_bounty_target", "is_anomaly_target", "is_wilderness_encounter",
    "is_dsp_hunter", "is_intel_handler", "chain_enemy_template", "vendor",
}

_ERA_DIRTY = re.compile(
    r"\b(imperial|empire|rebel alliance|rebel|tie fighter|tie bomber|tie interceptor)\b",
    re.IGNORECASE,
)

_ATTR_KEYS = {"dexterity", "knowledge", "mechanical", "perception", "strength", "technical"}

_DICE_CODE = re.compile(r"^\d+D(\+[12])?$")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_cw_room_names():
    """Walk every planet YAML in CW and collect every room name."""
    names = set()
    era = _load_yaml(ERA_PATH)
    planets_dir = os.path.join(CW_DIR, "planets")
    if os.path.isdir(planets_dir):
        for fname in os.listdir(planets_dir):
            if not fname.endswith(".yaml"):
                continue
            data = _load_yaml(os.path.join(planets_dir, fname))
            for room in data.get("rooms", []):
                if room.get("name"):
                    names.add(room["name"])
    return names


class TestAmbientYamlFile(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(os.path.isfile(YAML_PATH), f"Missing: {YAML_PATH}")

    def test_yaml_parses(self):
        data = _load_yaml(YAML_PATH)
        self.assertIsNotNone(data)

    def test_has_npcs_list(self):
        data = _load_yaml(YAML_PATH)
        self.assertIn("npcs", data)
        self.assertIsInstance(data["npcs"], list)

    def test_npc_count(self):
        data = _load_yaml(YAML_PATH)
        self.assertEqual(len(data["npcs"]), 4, "Expected exactly 4 ambient Kamino NPCs")


class TestExpectedNPCsPresent(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]
        self.names = {n["name"] for n in self.npcs}

    def test_all_named_npcs_present(self):
        for name in EXPECTED_NPCS:
            self.assertIn(name, self.names, f"Missing expected NPC: {name}")

    def test_no_extra_unexpected_npcs(self):
        for npc in self.npcs:
            self.assertIn(npc["name"], EXPECTED_NPCS,
                          f"Unexpected NPC: {npc['name']}")


class TestRequiredFields(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]

    def test_required_top_level_fields(self):
        required = {"name", "room", "species", "description", "char_sheet", "ai_config"}
        for npc in self.npcs:
            missing = required - set(npc.keys())
            self.assertFalse(missing, f"{npc.get('name')}: missing {missing}")

    def test_char_sheet_has_attributes_and_skills(self):
        for npc in self.npcs:
            cs = npc.get("char_sheet", {})
            self.assertIn("attributes", cs, f"{npc['name']}: missing char_sheet.attributes")
            self.assertIn("skills", cs, f"{npc['name']}: missing char_sheet.skills")

    def test_ai_config_has_required_keys(self):
        required = {"personality", "knowledge", "dialogue_style", "fallback_lines",
                    "hostile", "combat_behavior"}
        for npc in self.npcs:
            ai = npc.get("ai_config", {})
            missing = required - set(ai.keys())
            self.assertFalse(missing, f"{npc['name']}: ai_config missing {missing}")

    def test_fallback_lines_non_empty(self):
        for npc in self.npcs:
            lines = npc.get("ai_config", {}).get("fallback_lines", [])
            self.assertGreaterEqual(len(lines), 3,
                                    f"{npc['name']}: fewer than 3 fallback_lines")


class TestNonHostileAmbient(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]

    def test_all_npcs_non_hostile(self):
        for npc in self.npcs:
            hostile = npc.get("ai_config", {}).get("hostile", False)
            self.assertFalse(hostile, f"{npc['name']}: hostile must be false for ambient NPCs")

    def test_no_special_reward_markers(self):
        for npc in self.npcs:
            ai = npc.get("ai_config", {})
            present = _SPECIAL_REWARD_KEYS & set(ai.keys())
            self.assertFalse(present,
                             f"{npc['name']}: unexpected reward markers: {present}")


class TestRoomReferences(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]
        self.cw_rooms = _all_cw_room_names()

    def test_rooms_resolve(self):
        for npc in self.npcs:
            room = npc.get("room", "")
            self.assertIn(room, self.cw_rooms,
                          f"{npc['name']}: room '{room}' not found in any CW planet YAML")

    def test_rooms_are_correct_kamino_rooms(self):
        for npc in self.npcs:
            expected_room = EXPECTED_ROOMS.get(npc["name"])
            if expected_room:
                self.assertEqual(npc["room"], expected_room,
                                 f"{npc['name']}: wrong room")


class TestEraCleanness(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]

    def _player_strings(self, npc):
        """All player-visible text fields for an NPC."""
        parts = [
            npc.get("name", ""),
            npc.get("description", ""),
        ]
        ai = npc.get("ai_config", {})
        parts.append(ai.get("personality", ""))
        parts.append(ai.get("dialogue_style", ""))
        for line in ai.get("fallback_lines", []):
            parts.append(line)
        for item in ai.get("knowledge", []):
            parts.append(str(item))
        return " ".join(parts)

    def test_no_era_dirty_strings(self):
        for npc in self.npcs:
            text = self._player_strings(npc)
            match = _ERA_DIRTY.search(text)
            if match:
                self.fail(f"{npc['name']}: era-dirty string '{match.group()}' found")


class TestEraManifestRegistered(unittest.TestCase):
    def test_yaml_in_era_npcs_list(self):
        era = _load_yaml(ERA_PATH)
        npcs_list = era.get("content_refs", {}).get("npcs", [])
        names = [os.path.basename(e) if isinstance(e, str) else "" for e in npcs_list]
        self.assertIn("npcs_drop_kamino_interiors_ambient.yaml", names,
                      "npcs_drop_kamino_interiors_ambient.yaml not in era.yaml content_refs.npcs")


class TestStatSanity(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]

    def test_six_canonical_attributes(self):
        for npc in self.npcs:
            attrs = set(npc.get("char_sheet", {}).get("attributes", {}).keys())
            missing = _ATTR_KEYS - attrs
            self.assertFalse(missing, f"{npc['name']}: missing attributes {missing}")

    def test_no_invalid_pip_values(self):
        """Dice codes must be ND or ND+1 or ND+2 — never ND+3."""
        for npc in self.npcs:
            cs = npc.get("char_sheet", {})
            for section in ("attributes", "skills"):
                for key, val in cs.get(section, {}).items():
                    if not isinstance(val, str):
                        continue
                    self.assertTrue(
                        _DICE_CODE.match(val),
                        f"{npc['name']}.{section}.{key}: invalid dice code '{val}'"
                    )


if __name__ == "__main__":
    unittest.main()
