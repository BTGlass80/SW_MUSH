# -*- coding: utf-8 -*-
"""
tests/test_drop_b_mos_eisley.py — Drop B Mos Eisley CW Additions roster.

Drop B (May 2026) is the smallest remaining CW.NPCS drop per
`cw_content_gap_design_v1_1_decisions.md` Stage 4. Tatooine is
already healthy at 58 NPCs (51 GG7 carryover + 7 Drop A CW
replacements/additions). Drop B is polish — adds CW-specific
flavor NPCs to a small set of intentionally empty rooms that
benefit from era-coupled presence.

Per the Gap B plan: clone patrol cameos, Republic customs
liaison, Hutt enforcers. Six NPCs total across six rooms.

Per architecture v39 §3.2 priority #1 (CW.NPCS track), this is
content-only — no engine changes.

Test sections:
  1. TestRosterFile                  — file exists, YAML parses
  2. TestRequiredFieldsPresent       — schema conformance
  3. TestRoomReferencesResolve       — rooms exist on Tatooine
  4. TestFactionCodes                — valid CW org codes
  5. TestQ1CanonicalCharacterPolicy  — no Jabba, no canonical
                                        Tusken/Mos Eisley figures
  6. TestEraConsistency              — mid-war framing
  7. TestEraManifestRef              — wired into era.yaml
  8. TestCloneNPCsPresent            — clone patrol/customs cameos
  9. TestHuttEnforcerPresent         — Greeshk grounded as the
                                        Townhouse muscle (not Jabba)
 10. TestSchemaMatchesVelaNireeReference
 11. TestStatBlockSanity
 12. TestSpeciesDiversity
 13. TestDocstringMarker
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
DROP_B_YAML = os.path.join(CW_DIR, "npcs_drop_b_mos_eisley.yaml")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_cw_room_names():
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


def _tatooine_room_names():
    d = _load_yaml(os.path.join(CW_DIR, "planets", "tatooine.yaml")) or {}
    return {r["name"] for r in (d.get("rooms") or []) if isinstance(r, dict) and r.get("name")}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Roster file
# ─────────────────────────────────────────────────────────────────────────────

class TestRosterFile(unittest.TestCase):

    def test_file_exists(self):
        self.assertTrue(os.path.exists(DROP_B_YAML))

    def test_yaml_parses(self):
        d = _load_yaml(DROP_B_YAML)
        self.assertIsInstance(d, dict)
        self.assertEqual(d.get("schema_version"), 1)

    def test_npc_count_in_target_range(self):
        """Drop B target is ~5–8 NPCs (smallest CW.NPCS drop)."""
        d = _load_yaml(DROP_B_YAML)
        npcs = d.get("npcs", [])
        self.assertGreaterEqual(len(npcs), 4,
                                f"Drop B should have ~6 NPCs (got {len(npcs)})")
        self.assertLessEqual(len(npcs), 10,
                             f"Drop B over scope (got {len(npcs)})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Required fields
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldsPresent(unittest.TestCase):

    REQUIRED = ("name", "room", "species", "description", "char_sheet", "ai_config")

    def test_all_npcs_have_required_fields(self):
        d = _load_yaml(DROP_B_YAML)
        missing = []
        for i, n in enumerate(d.get("npcs", [])):
            for field in self.REQUIRED:
                if field not in n:
                    missing.append((n.get("name", f"#{i}"), field))
        self.assertEqual(missing, [], f"Missing fields: {missing}")

    def test_names_unique(self):
        d = _load_yaml(DROP_B_YAML)
        names = [n["name"] for n in d.get("npcs", [])]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicates: {sorted(names)}")

    def test_no_collision_with_other_drops(self):
        """Drop B names must not duplicate any earlier CW drop or GG7."""
        b = _load_yaml(DROP_B_YAML)
        b_names = {n["name"] for n in b.get("npcs", [])}
        # Other CW drops
        other_files = [
            "npcs_cw_additions.yaml", "npcs_cw_replacements.yaml",
            "npcs_drop_h_combat.yaml", "npcs_drop_c1_coruscant.yaml",
            "npcs_drop_def_civilians.yaml",
            "npcs_drop_g1_nar_shaddaa_topside.yaml",
            "npcs_drop_g2_nar_shaddaa_lower.yaml",
        ]
        for f in other_files:
            other_path = os.path.join(CW_DIR, f)
            if not os.path.exists(other_path):
                continue
            d = _load_yaml(other_path)
            other_names = {n["name"] for n in d.get("npcs", [])}
            overlap = b_names & other_names
            self.assertEqual(overlap, set(),
                             f"Drop B name collision with {f}: {overlap}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Room references
# ─────────────────────────────────────────────────────────────────────────────

class TestRoomReferencesResolve(unittest.TestCase):

    def test_all_rooms_exist_in_cw_world(self):
        d = _load_yaml(DROP_B_YAML)
        cw_rooms = _all_cw_room_names()
        unresolved = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in cw_rooms]
        self.assertEqual(unresolved, [],
                         f"Unresolved rooms: {unresolved}")

    def test_all_rooms_are_on_tatooine(self):
        d = _load_yaml(DROP_B_YAML)
        ts_rooms = _tatooine_room_names()
        off_planet = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in ts_rooms]
        self.assertEqual(off_planet, [],
                         f"Drop B NPCs not on Tatooine: {off_planet}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Faction codes
# ─────────────────────────────────────────────────────────────────────────────

class TestFactionCodes(unittest.TestCase):

    VALID_CODES = {
        "republic", "cis", "jedi_order", "hutt_cartel",
        "bounty_hunters_guild", "independent", "sith",
        "separatist_council",
    }

    def test_factions_in_canonical_set(self):
        d = _load_yaml(DROP_B_YAML)
        bad = [(n["name"], n["ai_config"]["faction"])
               for n in d.get("npcs", [])
               if n["ai_config"].get("faction")
               and n["ai_config"]["faction"] not in self.VALID_CODES]
        self.assertEqual(bad, [], f"Bad factions: {bad}")

    def test_clone_npcs_are_republic(self):
        d = _load_yaml(DROP_B_YAML)
        bad = []
        for n in d.get("npcs", []):
            # Clone NPCs identifiable by CT- prefix or "Clone" in name
            if "CT-" in n["name"] or "Clone" in n["name"]:
                fac = n["ai_config"]["faction"]
                if fac != "republic":
                    bad.append((n["name"], fac))
        self.assertEqual(bad, [], f"Clone NPCs not faction=republic: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Q1 canonical-character policy
# ─────────────────────────────────────────────────────────────────────────────

class TestQ1CanonicalCharacterPolicy(unittest.TestCase):

    CANONICAL_TATOOINE_FORBIDDEN = {
        # Canonical Tatooine Hutts
        "Jabba", "Jabba Desilijic Tiure", "Bib Fortuna",
        "Salacious Crumb", "Ephant Mon",
        # Canonical Mos Eisley figures
        "Wuher", "Greedo", "Figrin D'an", "Ackmena",
        # Canonical Tatooine inhabitants
        "Owen Lars", "Beru Lars", "Cliegg Lars",
        "Shmi Skywalker", "Watto",
        # Canonical CW bounty hunters
        "Cad Bane", "Aurra Sing", "Boba Fett",
        "Hondo Ohnaka", "Bossk", "Dengar",
        # Canonical clone heroes (CT designations reserved)
        "Captain Rex", "Commander Cody", "Hunter", "Echo",
        "Fives", "Jesse", "99",
    }
    OTHER_FORBIDDEN = {
        "Yoda", "Mace Windu", "Anakin Skywalker", "Obi-Wan Kenobi",
        "Padmé Amidala", "Bail Organa", "Mon Mothma",
    }

    @property
    def all_forbidden(self):
        return self.CANONICAL_TATOOINE_FORBIDDEN | self.OTHER_FORBIDDEN

    def test_no_canonical_named_npcs(self):
        d = _load_yaml(DROP_B_YAML)
        violations = []
        for n in d.get("npcs", []):
            name = n["name"]
            for forbidden in self.all_forbidden:
                if re.search(r"\b" + re.escape(forbidden) + r"\b", name):
                    violations.append((name, forbidden))
        self.assertEqual(violations, [],
                         f"Canonical figures in roster: {violations}")

    def test_jabba_framed_as_absent(self):
        """Jabba is the canonical Hutt Tatooine reference. Any mention
        must be framed as off-screen at his palace at the Dune Sea."""
        d = _load_yaml(DROP_B_YAML)
        absence_markers = (
            "canonical-reference", "off-world", "off-screen",
            "off world", "off screen", "not here", "absent",
            "remains at his palace", "at the palace", "at the Dune Sea",
            "does not visit", "does not come",
        )
        violations = []
        for n in d.get("npcs", []):
            text = (n.get("description", "") + " "
                    + str(n.get("ai_config", {}).get("personality", ""))
                    + " "
                    + " ".join(n.get("ai_config", {}).get("knowledge", []) or []))
            if "Jabba" in text:
                if not any(m.lower() in text.lower() for m in absence_markers):
                    violations.append(n["name"])
        self.assertEqual(violations, [],
                         f"Jabba mentions without absence framing: {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Era consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestEraConsistency(unittest.TestCase):

    POST_ORDER_66_LEAKS = (
        "Galactic Empire", "Imperial Senate", "Imperial Stormtrooper",
        "Vader", "Darth Vader", "Tarkin",
        "Rebellion", "Rebel Alliance", "post-war",
        "after the war", "Imperial occupation",
    )

    def test_no_post_order_66_references(self):
        d = _load_yaml(DROP_B_YAML)
        violations = []
        for n in d.get("npcs", []):
            text = " ".join([
                n.get("description", ""),
                str(n.get("ai_config", {}).get("personality", "")),
                " ".join(n.get("ai_config", {}).get("knowledge", []) or []),
                " ".join(n.get("ai_config", {}).get("fallback_lines", []) or []),
            ])
            for leak in self.POST_ORDER_66_LEAKS:
                if leak.lower() in text.lower():
                    violations.append((n["name"], leak))
        self.assertEqual(violations, [], f"Era leaks: {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. era.yaml ref
# ─────────────────────────────────────────────────────────────────────────────

class TestEraManifestRef(unittest.TestCase):

    def test_era_yaml_includes_drop_b(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        self.assertIn("npcs_drop_b_mos_eisley.yaml", npcs_refs)

    def test_pre_existing_npc_files_still_referenced(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        for f in ("npcs_cw_additions.yaml", "npcs_cw_replacements.yaml",
                  "npcs_drop_h_combat.yaml", "npcs_drop_c1_coruscant.yaml",
                  "npcs_drop_def_civilians.yaml",
                  "npcs_drop_g1_nar_shaddaa_topside.yaml",
                  "npcs_drop_g2_nar_shaddaa_lower.yaml"):
            self.assertIn(f, npcs_refs,
                          f"Pre-existing ref {f!r} dropped")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Clone NPCs present (gap B requires clone patrol/customs cameos)
# ─────────────────────────────────────────────────────────────────────────────

class TestCloneNPCsPresent(unittest.TestCase):

    def test_at_least_two_clones(self):
        """Per Gap B, at least clone patrol + clone customs liaison."""
        d = _load_yaml(DROP_B_YAML)
        clones = [n for n in d.get("npcs", [])
                  if "CT-" in n["name"] or "Clone" in n["name"]]
        self.assertGreaterEqual(len(clones), 2,
                                f"Drop B should have ≥2 clone NPCs: {len(clones)}")

    def test_republic_checkpoint_has_clone(self):
        """The Republic Checkpoint room is the clone customs liaison's
        natural home."""
        d = _load_yaml(DROP_B_YAML)
        checkpoint_npcs = [n for n in d.get("npcs", [])
                           if "Republic Checkpoint" in n["room"]]
        self.assertGreaterEqual(len(checkpoint_npcs), 1,
                                "Republic Checkpoint should have an NPC")
        # The NPC should be a clone
        npc = checkpoint_npcs[0]
        self.assertTrue("CT-" in npc["name"] or "Clone" in npc["name"],
                        f"Republic Checkpoint NPC should be a clone: {npc['name']}")

    def test_clone_designations_non_canonical(self):
        """Clone CT-designations should not match canonical clone heroes
        (CT-7567 = Rex, CC-2224 = Cody, CT-5555 = Fives, etc.)."""
        d = _load_yaml(DROP_B_YAML)
        canonical_designations = {
            "CT-7567", "CC-2224", "CT-5555", "CT-1409", "CT-21-0408",
            "CT-782", "CC-1010", "CC-3636", "CC-5052", "CC-1138",
        }
        violations = []
        for n in d.get("npcs", []):
            name = n["name"]
            for designation in canonical_designations:
                if designation in name:
                    violations.append((name, designation))
        self.assertEqual(violations, [],
                         f"Canonical clone designations: {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Hutt enforcer present (gap B requires Hutt enforcers)
# ─────────────────────────────────────────────────────────────────────────────

class TestHuttEnforcerPresent(unittest.TestCase):

    def test_townhouse_has_enforcer(self):
        """Jabba's Townhouse Main Entrance should have an enforcer."""
        d = _load_yaml(DROP_B_YAML)
        townhouse_npcs = [n for n in d.get("npcs", [])
                          if "Jabba's Townhouse" in n["room"]]
        self.assertGreaterEqual(len(townhouse_npcs), 1,
                                "Jabba's Townhouse should have an NPC")

    def test_townhouse_npc_is_cartel(self):
        d = _load_yaml(DROP_B_YAML)
        townhouse_npcs = [n for n in d.get("npcs", [])
                          if "Jabba's Townhouse" in n["room"]]
        for n in townhouse_npcs:
            self.assertEqual(n["ai_config"]["faction"], "hutt_cartel",
                             f"Townhouse NPC should be hutt_cartel: {n['name']}")

    def test_townhouse_npc_is_not_jabba(self):
        """Per Q1, Jabba does not appear; the Townhouse NPC must be a
        non-canonical lieutenant/enforcer."""
        d = _load_yaml(DROP_B_YAML)
        townhouse_npcs = [n for n in d.get("npcs", [])
                          if "Jabba's Townhouse" in n["room"]]
        for n in townhouse_npcs:
            self.assertNotIn("Jabba", n["name"],
                             f"Townhouse NPC should not be Jabba: {n['name']}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Schema conformance
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaMatchesVelaNireeReference(unittest.TestCase):

    AI_CONFIG_REQUIRED = (
        "personality", "knowledge", "faction", "dialogue_style",
        "hostile", "combat_behavior", "fallback_lines",
    )
    CHAR_SHEET_REQUIRED = (
        "attributes", "skills", "weapon", "move",
        "force_points", "character_points", "dark_side_points",
    )

    def test_ai_config_canonical_fields(self):
        d = _load_yaml(DROP_B_YAML)
        violations = []
        for n in d.get("npcs", []):
            ai = n.get("ai_config", {})
            for field in self.AI_CONFIG_REQUIRED:
                if field not in ai:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"AI config schema: {violations}")

    def test_char_sheet_canonical_fields(self):
        d = _load_yaml(DROP_B_YAML)
        violations = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {})
            for field in self.CHAR_SHEET_REQUIRED:
                if field not in cs:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"Char sheet schema: {violations}")

    def test_fallback_lines_nonempty(self):
        d = _load_yaml(DROP_B_YAML)
        bad = [(n["name"], len(n.get("ai_config", {}).get("fallback_lines", [])))
               for n in d.get("npcs", [])
               if len(n.get("ai_config", {}).get("fallback_lines", [])) < 3]
        self.assertEqual(bad, [], f"<3 fallback lines: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. Stat-block sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestStatBlockSanity(unittest.TestCase):

    def test_attribute_codes_look_like_d_codes(self):
        DCODE = re.compile(r"^\d+D(\+[12])?$")
        d = _load_yaml(DROP_B_YAML)
        violations = []
        for n in d.get("npcs", []):
            attrs = n.get("char_sheet", {}).get("attributes", {})
            for stat, val in attrs.items():
                if not DCODE.match(str(val)):
                    violations.append((n["name"], stat, val))
        self.assertEqual(violations, [], f"Bad D-codes: {violations}")

    def test_dsp_constraints(self):
        """Greeshk has DSP=1 (long enforcer career); others should be 0."""
        d = _load_yaml(DROP_B_YAML)
        violations = []
        for n in d.get("npcs", []):
            dsp = n.get("char_sheet", {}).get("dark_side_points", 0)
            if dsp > 1:
                violations.append((n["name"], dsp))
        self.assertEqual(violations, [], f"DSP > 1: {violations}")

    def test_jawa_has_low_move(self):
        """Jawas are small (~1m) — canonical move 8."""
        d = _load_yaml(DROP_B_YAML)
        bad = []
        for n in d.get("npcs", []):
            if n.get("species") == "Jawa":
                move = n.get("char_sheet", {}).get("move")
                if move > 9:
                    bad.append((n["name"], move))
        self.assertEqual(bad, [], f"Jawas with too-high move: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. Species diversity
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeciesDiversity(unittest.TestCase):

    def test_at_least_three_species(self):
        d = _load_yaml(DROP_B_YAML)
        species = set(n.get("species") for n in d.get("npcs", []))
        self.assertGreaterEqual(
            len(species), 3,
            f"Drop B should have ≥3 species; got {sorted(species)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 13. Source-level marker
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):

    def test_yaml_self_documents(self):
        with open(DROP_B_YAML, "r", encoding="utf-8") as f:
            src = f.read()
        for marker in ("Drop B", "Mos Eisley", "Q1", "Jabba",
                       "canonical-reference", "Republic Checkpoint"):
            self.assertIn(marker, src,
                          f"YAML header should mention {marker!r}")


if __name__ == "__main__":
    unittest.main()
