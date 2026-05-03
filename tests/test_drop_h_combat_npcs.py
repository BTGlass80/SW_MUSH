# -*- coding: utf-8 -*-
"""
tests/test_drop_h_combat_npcs.py — Drop H combat-NPC roster verification.

Drop H (May 2026) is the first wave of CW combat infrastructure per
`cw_content_gap_design_v1.md` and `cw_content_gap_design_v1_1_decisions.md`.
It authors `data/worlds/clone_wars/npcs_drop_h_combat.yaml` with 12
NPC instances spanning six template archetypes:

  - B1 Battle Droid          (4 instances on Geonosis)
  - B2 Super Battle Droid    (1 instance on Geonosis)
  - Geonosian Warrior        (2 instances on Geonosis)
  - Clone Trooper (line)     (3 instances: Coruscant, Kamino, Kuat)
  - Republic Commando        (1 instance on Kamino)
  - Droideka                 (1 instance on Kuat)

Per architecture v39 §3.2 priority #1 (CW.NPCS track), Drop H is
content-only — no engine changes, no DB schema changes, no command
additions. The roster file is wired into CW `era.yaml` via
`content_refs.npcs`.

Test sections:
  1. TestRosterFile                — file exists; YAML parses; right shape
  2. TestRequiredFieldsPresent     — every NPC has the canonical schema
  3. TestRoomReferencesResolve     — every room is a real CW room
  4. TestFactionCodes              — every faction is a valid CW org code
  5. TestStatBlockSanity           — droids have 0 force, char_sheets parse
  6. TestEraManifestRef            — npcs_drop_h_combat.yaml is in era.yaml
  7. TestPlanetCoverage            — at least 4 distinct planets covered
  8. TestArchetypeCounts           — the 6 archetypes are all present
  9. TestSchemaMatchesVelaNireeReference — fields conform to canonical
                                            CW NPC schema
 10. TestDocstringMarker           — source-level guard
"""
from __future__ import annotations

import os
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CW_DIR = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
DROP_H_YAML = os.path.join(CW_DIR, "npcs_drop_h_combat.yaml")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_cw_room_names():
    """Walk every planet YAML in CW and collect every room name."""
    names = set()
    era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
    refs = era.get("content_refs", {}) or {}
    planet_files = refs.get("planets", []) or []
    for entry in planet_files:
        if isinstance(entry, str):
            p = os.path.join(CW_DIR, entry)
            if os.path.exists(p):
                d = _load_yaml(p) or {}
                for r in (d.get("rooms") or []):
                    if isinstance(r, dict) and r.get("name"):
                        names.add(r["name"])
    return names


# ─────────────────────────────────────────────────────────────────────────────
# 1. Roster file present and well-formed
# ─────────────────────────────────────────────────────────────────────────────

class TestRosterFile(unittest.TestCase):

    def test_file_exists(self):
        self.assertTrue(
            os.path.exists(DROP_H_YAML),
            f"Drop H roster missing at {DROP_H_YAML}"
        )

    def test_yaml_parses(self):
        d = _load_yaml(DROP_H_YAML)
        self.assertIsInstance(d, dict)
        self.assertEqual(d.get("schema_version"), 1)

    def test_npcs_list_present_and_nonempty(self):
        d = _load_yaml(DROP_H_YAML)
        npcs = d.get("npcs")
        self.assertIsInstance(npcs, list,
                              "npcs must be a YAML list")
        self.assertEqual(len(npcs), 12,
                         f"Drop H scope is 12 NPCs (got {len(npcs)})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Each NPC has the canonical schema
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldsPresent(unittest.TestCase):
    """Every NPC has name, room, species, description, char_sheet, ai_config."""

    REQUIRED = ("name", "room", "species", "description", "char_sheet", "ai_config")

    def test_all_npcs_have_required_fields(self):
        d = _load_yaml(DROP_H_YAML)
        missing = []
        for i, n in enumerate(d.get("npcs", [])):
            for field in self.REQUIRED:
                if field not in n:
                    missing.append((n.get("name", f"#{i}"), field))
        self.assertEqual(missing, [],
                         f"NPCs missing required fields: {missing}")

    def test_names_unique(self):
        d = _load_yaml(DROP_H_YAML)
        names = [n["name"] for n in d.get("npcs", [])]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicate NPC names in Drop H: {sorted(names)}")

    def test_char_sheet_has_attributes_and_skills(self):
        d = _load_yaml(DROP_H_YAML)
        bad = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {})
            if "attributes" not in cs or "skills" not in cs:
                bad.append(n["name"])
        self.assertEqual(bad, [],
                         f"NPCs missing char_sheet.attributes or skills: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Every room reference resolves to a real CW room
# ─────────────────────────────────────────────────────────────────────────────

class TestRoomReferencesResolve(unittest.TestCase):

    def test_all_rooms_exist_in_cw_world(self):
        d = _load_yaml(DROP_H_YAML)
        cw_rooms = _all_cw_room_names()
        unresolved = []
        for n in d.get("npcs", []):
            if n["room"] not in cw_rooms:
                unresolved.append((n["name"], n["room"]))
        self.assertEqual(
            unresolved, [],
            f"NPCs reference rooms missing from CW world data:\n  " +
            "\n  ".join(f"{name} @ {room}" for name, room in unresolved)
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Faction codes are valid
# ─────────────────────────────────────────────────────────────────────────────

class TestFactionCodes(unittest.TestCase):
    """Each NPC's ai_config.faction is a valid CW org code."""

    VALID_CODES = {
        "republic", "cis", "jedi_order", "hutt_cartel",
        "bounty_hunters_guild", "independent", "sith",
        "separatist_council", "neutral", "Neutral",
    }

    def test_factions_in_canonical_set(self):
        d = _load_yaml(DROP_H_YAML)
        bad = []
        for n in d.get("npcs", []):
            fac = n.get("ai_config", {}).get("faction", "")
            if fac and fac not in self.VALID_CODES:
                bad.append((n["name"], fac))
        self.assertEqual(
            bad, [],
            f"NPCs with non-canonical faction codes: {bad}\n"
            f"Valid codes: {sorted(self.VALID_CODES)}"
        )

    def test_combat_npcs_have_a_faction(self):
        """Every Drop H NPC should have an ai_config.faction (combat ones especially)."""
        d = _load_yaml(DROP_H_YAML)
        missing = [n["name"] for n in d.get("npcs", [])
                   if not n.get("ai_config", {}).get("faction")]
        self.assertEqual(missing, [],
                         f"NPCs without faction: {missing}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Stat-block sanity (WEG-fidelity)
# ─────────────────────────────────────────────────────────────────────────────

class TestStatBlockSanity(unittest.TestCase):

    def test_droids_have_zero_force_points(self):
        """Droids cannot use the Force; force_points must be 0."""
        d = _load_yaml(DROP_H_YAML)
        violations = []
        for n in d.get("npcs", []):
            if n.get("species") == "Droid":
                fp = n.get("char_sheet", {}).get("force_points", 0)
                if fp != 0:
                    violations.append((n["name"], fp))
        self.assertEqual(violations, [],
                         f"Droids with non-zero force_points: {violations}")

    def test_droids_have_zero_dark_side_points(self):
        d = _load_yaml(DROP_H_YAML)
        violations = []
        for n in d.get("npcs", []):
            if n.get("species") == "Droid":
                dsp = n.get("char_sheet", {}).get("dark_side_points", 0)
                if dsp != 0:
                    violations.append((n["name"], dsp))
        self.assertEqual(violations, [], f"Droids with DSP: {violations}")

    def test_clones_have_zero_force_points(self):
        """Per WEG D6 + CW canon, clone troopers are not Force-sensitive."""
        d = _load_yaml(DROP_H_YAML)
        violations = []
        for n in d.get("npcs", []):
            name = n.get("name", "")
            # Match generic clones (CT-/CC-/CS-) but the Republic Commando
            # template gets 1 FP (named, elite, distinctive). RC- prefix
            # signals commando — exempt from the no-FP rule.
            if (name.startswith("Clone ") or "CT-" in name or "CC-" in name
                    or "CS-" in name) and "RC-" not in name:
                fp = n.get("char_sheet", {}).get("force_points", 0)
                if fp != 0:
                    violations.append((name, fp))
        self.assertEqual(violations, [],
                         f"Line clones with FP > 0: {violations}")

    def test_attribute_codes_look_like_d_codes(self):
        """Attributes use WEG D-code format like '3D+1'."""
        import re
        DCODE = re.compile(r"^\d+D(\+[12])?$")
        d = _load_yaml(DROP_H_YAML)
        violations = []
        for n in d.get("npcs", []):
            attrs = n.get("char_sheet", {}).get("attributes", {})
            for stat, val in attrs.items():
                if not DCODE.match(str(val)):
                    violations.append((n["name"], stat, val))
        self.assertEqual(
            violations, [],
            f"Attributes don't match WEG D-code format: {violations}"
        )

    def test_move_value_present(self):
        """Every NPC has a move stat (WEG default 10 for human-scale)."""
        d = _load_yaml(DROP_H_YAML)
        violations = []
        for n in d.get("npcs", []):
            move = n.get("char_sheet", {}).get("move")
            if move is None or not isinstance(move, int):
                violations.append((n["name"], move))
        self.assertEqual(violations, [],
                         f"NPCs without integer move: {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. era.yaml references the new file
# ─────────────────────────────────────────────────────────────────────────────

class TestEraManifestRef(unittest.TestCase):

    def test_era_yaml_includes_drop_h(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        self.assertIn(
            "npcs_drop_h_combat.yaml", npcs_refs,
            "CW era.yaml content_refs.npcs must include "
            "npcs_drop_h_combat.yaml so the Drop H roster loads"
        )

    def test_pre_existing_npc_files_still_referenced(self):
        """Drop H must not displace prior NPC files."""
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        for f in ("npcs_cw_additions.yaml", "npcs_cw_replacements.yaml"):
            self.assertIn(
                f, npcs_refs,
                f"Pre-existing NPC ref {f!r} dropped from era.yaml"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Planet coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestPlanetCoverage(unittest.TestCase):

    def test_at_least_four_planets_covered(self):
        """Drop H scope: Geonosis + Coruscant + Kamino + Kuat."""
        d = _load_yaml(DROP_H_YAML)
        rooms = {n["room"] for n in d.get("npcs", [])}
        # Cheap planet detection via room name prefix
        planets = set()
        for r in rooms:
            for p in ("Geonosis", "Coruscant", "Jedi Temple", "Kamino", "Kuat",
                      "Nar Shaddaa", "Tatooine", "Docking Bay"):
                if p in r:
                    planets.add(p)
                    break
        # Jedi Temple counts as Coruscant for coverage purposes
        coruscant_alias = "Coruscant" in planets or "Jedi Temple" in planets
        if coruscant_alias:
            planets.discard("Jedi Temple")
            planets.add("Coruscant")
        self.assertGreaterEqual(
            len(planets), 4,
            f"Drop H should cover ≥4 planets; got {sorted(planets)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 8. All 6 template archetypes present
# ─────────────────────────────────────────────────────────────────────────────

class TestArchetypeCounts(unittest.TestCase):

    def test_all_six_archetypes_present(self):
        """Drop H spec: B1, B2, droideka, clone (line), republic commando, geonosian."""
        d = _load_yaml(DROP_H_YAML)
        archetypes_seen = set()
        for n in d.get("npcs", []):
            name = n.get("name", "").lower()
            species = n.get("species", "")
            if "b1" in name and species == "Droid":
                archetypes_seen.add("b1")
            elif "b2" in name and species == "Droid":
                archetypes_seen.add("b2")
            elif "droideka" in name and species == "Droid":
                archetypes_seen.add("droideka")
            elif "republic commando" in name or "rc-" in name:
                archetypes_seen.add("republic_commando")
            elif "clone" in name and species == "Human":
                archetypes_seen.add("clone_line")
            elif species == "Geonosian":
                archetypes_seen.add("geonosian")
        expected = {"b1", "b2", "droideka", "republic_commando",
                    "clone_line", "geonosian"}
        missing = expected - archetypes_seen
        self.assertEqual(missing, set(),
                         f"Missing archetypes: {missing}; saw {archetypes_seen}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Schema conformance to Vela Niree canonical reference
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaMatchesVelaNireeReference(unittest.TestCase):
    """Per J1 handoff §6.7, Vela Niree is the canonical CW NPC schema reference.

    The mandatory fields every NPC needs are: char_sheet (attributes,
    skills, weapon, move, force_points, character_points, dark_side_points)
    + ai_config (personality, knowledge, faction, dialogue_style, hostile,
    combat_behavior, fallback_lines).
    """

    AI_CONFIG_REQUIRED = (
        "personality", "knowledge", "faction", "dialogue_style",
        "hostile", "combat_behavior", "fallback_lines",
    )
    CHAR_SHEET_REQUIRED = (
        "attributes", "skills", "weapon", "move",
        "force_points", "character_points", "dark_side_points",
    )

    def test_ai_config_canonical_fields(self):
        d = _load_yaml(DROP_H_YAML)
        violations = []
        for n in d.get("npcs", []):
            ai = n.get("ai_config", {})
            for field in self.AI_CONFIG_REQUIRED:
                if field not in ai:
                    violations.append((n["name"], f"ai_config.{field}"))
        self.assertEqual(violations, [],
                         f"AI config schema violations: {violations}")

    def test_char_sheet_canonical_fields(self):
        d = _load_yaml(DROP_H_YAML)
        violations = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {})
            for field in self.CHAR_SHEET_REQUIRED:
                if field not in cs:
                    violations.append((n["name"], f"char_sheet.{field}"))
        self.assertEqual(violations, [],
                         f"Char sheet schema violations: {violations}")

    def test_fallback_lines_nonempty(self):
        d = _load_yaml(DROP_H_YAML)
        bad = []
        for n in d.get("npcs", []):
            lines = n.get("ai_config", {}).get("fallback_lines", [])
            if not lines or len(lines) < 3:
                bad.append((n["name"], len(lines)))
        self.assertEqual(bad, [],
                         f"NPCs with <3 fallback lines: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Source-level marker
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):

    def test_yaml_self_documents(self):
        with open(DROP_H_YAML, "r", encoding="utf-8") as f:
            src = f.read()
        for marker in ("Drop H", "cw_content_gap", "B1", "Republic Commando"):
            self.assertIn(marker, src,
                          f"Drop H YAML header should mention {marker!r}")


if __name__ == "__main__":
    unittest.main()
