# -*- coding: utf-8 -*-
"""
tests/test_drop_ambient_tatooine_spaceport_civic.py

Static-invariant tests for the Tatooine Spaceport & Civic ambient NPC
batch (data/worlds/clone_wars/npcs_drop_ambient_tatooine_spaceport_civic.yaml).

Nine non-hostile flavor NPCs across nine previously-empty Tatooine rooms:
  Docking Bay 86                         x1  (BX-9T / Droid -- named in room desc)
  Docking Bay 87                         x1  (Drue / Ishi Tib -- named in room desc)
  Docking Bay 92                         x1  (Dom Antyll / Human -- named in room desc)
  Docking Bay 94 - Entrance              x1  (Tova Shenn / Human flim-flam artist)
  Spaceport Customs Office               x1  (Inspector Haddo / Human -- corrupt inspector)
  Spaceport Speeders                     x1  (Kree Nassok / Rodian -- speeder dealer)
  Mos Eisley Street - Government Quarter x1  (Corporal Ferras / Human -- militia patrol)
  Tatooine Militia Headquarters          x1  (Commander Veth Sorn / Human -- militia CO)
  The Cutting Edge Clinic                x1  (Yella / Twi'lek -- clinic assistant)

Verifies:
  1. File exists and YAML parses cleanly
  2. All 9 expected NPCs present by name
  3. Required top-level fields on every NPC
  4. char_sheet has the six canonical attributes and valid dice codes
  5. All NPCs are non-hostile (ambient, not grind mobs)
  6. No special-reward markers
  7. Room references resolve to real Tatooine rooms
  8. Era cleanness -- no Imperial/Empire/Rebel/TIE in player-facing strings
  9. File is registered in era.yaml content_refs.npcs
 10. Fallback lines: >= 3 per NPC
 11. ai_config has all required keys
 12. Dr. Evazan (Q1-prohibited canon figure) is NOT added as an NPC
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
YAML_PATH = os.path.join(CW_DIR, "npcs_drop_ambient_tatooine_spaceport_civic.yaml")
ERA_PATH = os.path.join(CW_DIR, "era.yaml")
TATOOINE_PATH = os.path.join(CW_DIR, "planets", "tatooine.yaml")

EXPECTED_NPC_COUNT = 9

EXPECTED_NPCS = {
    "BX-9T",
    "Drue",
    "Dom Antyll",
    "Tova Shenn",
    "Inspector Haddo",
    "Kree Nassok",
    "Corporal Ferras",
    "Commander Veth Sorn",
    "Yella",
}

EXPECTED_ROOMS = {
    "Docking Bay 86",
    "Docking Bay 87",
    "Docking Bay 92",
    "Docking Bay 94 - Entrance",
    "Spaceport Customs Office",
    "Spaceport Speeders",
    "Mos Eisley Street - Government Quarter",
    "Tatooine Militia Headquarters",
    "The Cutting Edge Clinic",
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


def _tatooine_room_names():
    data = _load_yaml(TATOOINE_PATH)
    return {r["name"] for r in data.get("rooms", [])}


class TestFileBasics(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(os.path.isfile(YAML_PATH), f"Missing: {YAML_PATH}")

    def test_yaml_parses(self):
        data = _load_yaml(YAML_PATH)
        self.assertIsNotNone(data)

    def test_schema_version(self):
        data = _load_yaml(YAML_PATH)
        self.assertEqual(data.get("schema_version"), 1)

    def test_npc_count(self):
        data = _load_yaml(YAML_PATH)
        self.assertEqual(len(data["npcs"]), EXPECTED_NPC_COUNT,
                         f"Expected {EXPECTED_NPC_COUNT} NPCs")


class TestExpectedNPCs(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]
        self.names = {n["name"] for n in self.npcs}

    def test_all_named_npcs_present(self):
        for name in EXPECTED_NPCS:
            self.assertIn(name, self.names, f"Missing expected NPC: {name}")

    def test_no_unexpected_npcs(self):
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

    def test_six_canonical_attributes(self):
        for npc in self.npcs:
            attrs = set(npc.get("char_sheet", {}).get("attributes", {}).keys())
            missing = _ATTR_KEYS - attrs
            self.assertFalse(missing, f"{npc['name']}: missing attributes {missing}")

    def test_no_invalid_pip_values(self):
        """Dice codes must be ND or ND+1 or ND+2 -- never ND+3."""
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

    def test_ai_config_has_required_keys(self):
        required = {"personality", "knowledge", "dialogue_style", "fallback_lines",
                    "hostile", "combat_behavior"}
        for npc in self.npcs:
            ai = npc.get("ai_config", {})
            missing = required - set(ai.keys())
            self.assertFalse(missing, f"{npc['name']}: ai_config missing {missing}")

    def test_fallback_lines_count(self):
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
            self.assertFalse(hostile,
                             f"{npc['name']}: hostile must be false for ambient NPCs")

    def test_no_special_reward_markers(self):
        for npc in self.npcs:
            ai = npc.get("ai_config", {})
            present = _SPECIAL_REWARD_KEYS & set(npc.keys())
            self.assertFalse(present,
                             f"{npc['name']}: unexpected reward markers in top-level: {present}")
            present_ai = _SPECIAL_REWARD_KEYS & set(ai.keys())
            self.assertFalse(present_ai,
                             f"{npc['name']}: unexpected reward markers in ai_config: {present_ai}")


class TestRoomReferences(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]
        self.tatooine_rooms = _tatooine_room_names()

    def test_rooms_resolve_in_tatooine(self):
        for npc in self.npcs:
            room = npc.get("room", "")
            self.assertIn(room, self.tatooine_rooms,
                          f"{npc['name']}: room '{room}' not found in tatooine.yaml")

    def test_rooms_are_expected_target_rooms(self):
        for npc in self.npcs:
            room = npc.get("room", "")
            self.assertIn(room, EXPECTED_ROOMS,
                          f"{npc['name']}: room '{room}' not in expected target set")

    def test_all_target_rooms_covered(self):
        covered = {npc["room"] for npc in self.npcs}
        missing = EXPECTED_ROOMS - covered
        self.assertFalse(missing, f"These target rooms have no NPCs: {missing}")


class TestEraCleanness(unittest.TestCase):
    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]

    def _player_strings(self, npc):
        parts = [npc.get("name", ""), npc.get("description", "")]
        ai = npc.get("ai_config", {})
        parts.append(ai.get("personality", ""))
        parts.append(ai.get("dialogue_style", ""))
        for line in ai.get("fallback_lines", []):
            parts.append(str(line))
        for item in ai.get("knowledge", []):
            parts.append(str(item))
        return " ".join(parts)

    def test_no_era_dirty_strings(self):
        for npc in self.npcs:
            text = self._player_strings(npc)
            match = _ERA_DIRTY.search(text)
            if match:
                self.fail(
                    f"{npc['name']}: era-dirty string '{match.group()}' found"
                )


class TestEraRegistration(unittest.TestCase):
    def test_yaml_in_era_npcs_list(self):
        era = _load_yaml(ERA_PATH)
        npcs_list = era.get("content_refs", {}).get("npcs", [])
        names = []
        for entry in npcs_list:
            if isinstance(entry, str):
                names.append(os.path.basename(entry))
            elif isinstance(entry, dict):
                for v in entry.values():
                    names.append(os.path.basename(str(v)))
        self.assertIn(
            "npcs_drop_ambient_tatooine_spaceport_civic.yaml",
            names,
            "npcs_drop_ambient_tatooine_spaceport_civic.yaml not in era.yaml content_refs.npcs",
        )


class TestQ1Compliance(unittest.TestCase):
    """Guard: Dr. Evazan (canon, Q1-prohibited) must not appear as a named NPC."""

    def setUp(self):
        data = _load_yaml(YAML_PATH)
        self.npcs = data["npcs"]
        self.names = {n["name"] for n in self.npcs}

    def test_dr_evazan_not_present_as_npc(self):
        prohibited = {"Dr. Evazan", "Evazan", "Cornelius"}
        overlap = prohibited & self.names
        self.assertFalse(overlap,
                         f"Q1-prohibited canon figure(s) added as NPC: {overlap}")


if __name__ == "__main__":
    unittest.main()
