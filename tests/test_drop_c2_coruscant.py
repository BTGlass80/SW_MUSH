# -*- coding: utf-8 -*-
"""
tests/test_drop_c2_coruscant.py — Drop C2 Coruscant Coco Town + Lower City roster.

Drop C2 (May 2026) is the FINAL CW.NPCS content drop per
`cw_content_gap_design_v1_1_decisions.md` Stage 4. Adds NPCs to
Coruscant's Coco Town, Mid-City, Lower City, Underworld, and a
small set of canonical Coruscant landmarks. After C2, the
CW.NPCS track effectively closes.

Per architecture v39 §3.2 priority #1 (CW.NPCS track), this is
content-only — no engine changes.

Test sections:
  1. TestRosterFile                  — file exists, YAML parses
  2. TestRequiredFieldsPresent       — schema conformance
  3. TestRoomReferencesResolve       — rooms exist on Coruscant
  4. TestNoCollisionWithOtherDrops   — no name overlaps with C1 etc.
  5. TestFactionCodes                — valid CW org codes
  6. TestQ1CanonicalCharacterPolicy  — no Dexter, Xizor, etc.
  7. TestEraConsistency              — mid-war framing
  8. TestEraManifestRef              — wired into era.yaml
  9. TestSchemaMatchesVelaNireeReference
 10. TestStatBlockSanity
 11. TestSpeciesDiversity            — Coruscant should be cosmopolitan
 12. TestRefugeeNetworkPresent       — mirrors NS Drop G1/G2 pattern
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
DROP_C2_YAML = os.path.join(CW_DIR, "npcs_drop_c2_coruscant_lower.yaml")


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


def _coruscant_room_names():
    d = _load_yaml(os.path.join(CW_DIR, "planets", "coruscant.yaml")) or {}
    return {r["name"] for r in (d.get("rooms") or []) if isinstance(r, dict) and r.get("name")}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Roster file
# ─────────────────────────────────────────────────────────────────────────────

class TestRosterFile(unittest.TestCase):

    def test_file_exists(self):
        self.assertTrue(os.path.exists(DROP_C2_YAML))

    def test_yaml_parses(self):
        d = _load_yaml(DROP_C2_YAML)
        self.assertIsInstance(d, dict)
        self.assertEqual(d.get("schema_version"), 1)

    def test_npc_count_in_target_range(self):
        """C2 target is ~25 NPCs."""
        d = _load_yaml(DROP_C2_YAML)
        npcs = d.get("npcs", [])
        self.assertGreaterEqual(len(npcs), 18,
                                f"C2 should have ~24 NPCs (got {len(npcs)})")
        self.assertLessEqual(len(npcs), 30,
                             f"C2 over scope (got {len(npcs)})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Required fields
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldsPresent(unittest.TestCase):

    REQUIRED = ("name", "room", "species", "description", "char_sheet", "ai_config")

    def test_all_npcs_have_required_fields(self):
        d = _load_yaml(DROP_C2_YAML)
        missing = []
        for i, n in enumerate(d.get("npcs", [])):
            for field in self.REQUIRED:
                if field not in n:
                    missing.append((n.get("name", f"#{i}"), field))
        self.assertEqual(missing, [], f"Missing fields: {missing}")

    def test_names_unique(self):
        d = _load_yaml(DROP_C2_YAML)
        names = [n["name"] for n in d.get("npcs", [])]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicates: {sorted(names)}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Room references
# ─────────────────────────────────────────────────────────────────────────────

class TestRoomReferencesResolve(unittest.TestCase):

    def test_all_rooms_exist_in_cw_world(self):
        d = _load_yaml(DROP_C2_YAML)
        cw_rooms = _all_cw_room_names()
        unresolved = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in cw_rooms]
        self.assertEqual(unresolved, [],
                         f"Unresolved rooms: {unresolved}")

    def test_all_rooms_are_on_coruscant(self):
        d = _load_yaml(DROP_C2_YAML)
        cor_rooms = _coruscant_room_names()
        off_planet = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in cor_rooms]
        self.assertEqual(off_planet, [],
                         f"C2 NPCs not on Coruscant: {off_planet}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. No collision with other drops
# ─────────────────────────────────────────────────────────────────────────────

class TestNoCollisionWithOtherDrops(unittest.TestCase):

    def test_no_collision_with_c1(self):
        c1 = _load_yaml(os.path.join(CW_DIR, "npcs_drop_c1_coruscant.yaml"))
        c2 = _load_yaml(DROP_C2_YAML)
        c1_names = {n["name"] for n in c1.get("npcs", [])}
        c2_names = {n["name"] for n in c2.get("npcs", [])}
        overlap = c1_names & c2_names
        self.assertEqual(overlap, set(),
                         f"C1/C2 name collisions: {overlap}")

    def test_no_collision_with_c1_rooms(self):
        """C2 should add NEW room coverage, not duplicate C1's rooms."""
        c1 = _load_yaml(os.path.join(CW_DIR, "npcs_drop_c1_coruscant.yaml"))
        c2 = _load_yaml(DROP_C2_YAML)
        c1_rooms = {n["room"] for n in c1.get("npcs", [])}
        c2_rooms = {n["room"] for n in c2.get("npcs", [])}
        overlap = c1_rooms & c2_rooms
        self.assertEqual(overlap, set(),
                         f"C2 reuses C1 rooms (should be new coverage): {overlap}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Faction codes
# ─────────────────────────────────────────────────────────────────────────────

class TestFactionCodes(unittest.TestCase):

    VALID_CODES = {
        "republic", "cis", "jedi_order", "hutt_cartel",
        "bounty_hunters_guild", "independent", "sith",
        "separatist_council",
    }

    def test_factions_in_canonical_set(self):
        d = _load_yaml(DROP_C2_YAML)
        bad = [(n["name"], n["ai_config"]["faction"])
               for n in d.get("npcs", [])
               if n["ai_config"].get("faction")
               and n["ai_config"]["faction"] not in self.VALID_CODES]
        self.assertEqual(bad, [], f"Bad factions: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Q1 canonical-character policy
# ─────────────────────────────────────────────────────────────────────────────

class TestQ1CanonicalCharacterPolicy(unittest.TestCase):

    CANONICAL_FORBIDDEN = {
        # Canonical Coruscant figures
        "Dexter Jettster", "Hermione Bagwa", "Ronet Coorr",
        # Canonical Black Sun
        "Xizor", "Prince Xizor", "Vigo",
        # Canonical Jedi Council and Senate (also covered in C1)
        "Yoda", "Mace Windu", "Obi-Wan Kenobi", "Anakin Skywalker",
        "Plo Koon", "Ki-Adi-Mundi", "Kit Fisto", "Shaak Ti",
        "Jocasta Nu", "Padmé Amidala", "Bail Organa", "Mon Mothma",
        # Canonical clones
        "Captain Rex", "Commander Cody", "Commander Fox",
        # Canonical bounty hunters
        "Cad Bane", "Aurra Sing", "Boba Fett",
    }

    def test_no_canonical_named_npcs(self):
        d = _load_yaml(DROP_C2_YAML)
        violations = []
        for n in d.get("npcs", []):
            name = n["name"]
            for forbidden in self.CANONICAL_FORBIDDEN:
                if re.search(r"\b" + re.escape(forbidden) + r"\b", name):
                    violations.append((name, forbidden))
        self.assertEqual(violations, [],
                         f"Canonical figures in roster: {violations}")

    def test_dexter_framed_as_absent(self):
        """Dexter Jettster is canonical (AOTC, TCW). Must be off-screen."""
        d = _load_yaml(DROP_C2_YAML)
        absence_markers = (
            "off-world", "absent", "not here", "off-screen",
            "canonical-reference", "canonical reference",
            "supply run", "out today", "currently",
        )
        violations = []
        for n in d.get("npcs", []):
            text = (n.get("description", "") + " "
                    + str(n.get("ai_config", {}).get("personality", ""))
                    + " "
                    + " ".join(n.get("ai_config", {}).get("knowledge", []) or []))
            if "Dexter" in text:
                if not any(m.lower() in text.lower() for m in absence_markers):
                    violations.append(n["name"])
        self.assertEqual(violations, [],
                         f"Dexter mentions without absence framing: {violations}")

    def test_xizor_castle_district_not_populated(self):
        """Xizor's Castle District should remain empty (Q1 — Xizor canonical)."""
        d = _load_yaml(DROP_C2_YAML)
        violations = [n["name"] for n in d.get("npcs", [])
                      if "Xizor" in n["room"]]
        self.assertEqual(violations, [],
                         f"NPCs in Xizor's Castle District (should be empty): {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Era consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestEraConsistency(unittest.TestCase):

    POST_ORDER_66_LEAKS = (
        "Galactic Empire", "Imperial Senate", "Imperial Stormtrooper",
        "Vader", "Darth Vader", "Tarkin",
        "Rebellion", "Rebel Alliance", "post-war",
        "after the war", "Imperial occupation",
    )

    def test_no_post_order_66_references(self):
        d = _load_yaml(DROP_C2_YAML)
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
# 8. era.yaml ref
# ─────────────────────────────────────────────────────────────────────────────

class TestEraManifestRef(unittest.TestCase):

    def test_era_yaml_includes_drop_c2(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        self.assertIn("npcs_drop_c2_coruscant_lower.yaml", npcs_refs)

    def test_pre_existing_npc_files_still_referenced(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        for f in ("npcs_cw_additions.yaml", "npcs_cw_replacements.yaml",
                  "npcs_drop_h_combat.yaml", "npcs_drop_c1_coruscant.yaml",
                  "npcs_drop_def_civilians.yaml",
                  "npcs_drop_g1_nar_shaddaa_topside.yaml",
                  "npcs_drop_g2_nar_shaddaa_lower.yaml",
                  "npcs_drop_b_mos_eisley.yaml"):
            self.assertIn(f, npcs_refs,
                          f"Pre-existing ref {f!r} dropped")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Schema conformance
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
        d = _load_yaml(DROP_C2_YAML)
        violations = []
        for n in d.get("npcs", []):
            ai = n.get("ai_config", {})
            for field in self.AI_CONFIG_REQUIRED:
                if field not in ai:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"AI config schema: {violations}")

    def test_char_sheet_canonical_fields(self):
        d = _load_yaml(DROP_C2_YAML)
        violations = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {})
            for field in self.CHAR_SHEET_REQUIRED:
                if field not in cs:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"Char sheet schema: {violations}")

    def test_fallback_lines_nonempty(self):
        d = _load_yaml(DROP_C2_YAML)
        bad = [(n["name"], len(n.get("ai_config", {}).get("fallback_lines", [])))
               for n in d.get("npcs", [])
               if len(n.get("ai_config", {}).get("fallback_lines", [])) < 3]
        self.assertEqual(bad, [], f"<3 fallback lines: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Stat-block sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestStatBlockSanity(unittest.TestCase):

    def test_attribute_codes_look_like_d_codes(self):
        DCODE = re.compile(r"^\d+D(\+[12])?$")
        d = _load_yaml(DROP_C2_YAML)
        violations = []
        for n in d.get("npcs", []):
            attrs = n.get("char_sheet", {}).get("attributes", {})
            for stat, val in attrs.items():
                if not DCODE.match(str(val)):
                    violations.append((n["name"], stat, val))
        self.assertEqual(violations, [], f"Bad D-codes: {violations}")

    def test_dsp_constraints(self):
        d = _load_yaml(DROP_C2_YAML)
        violations = []
        for n in d.get("npcs", []):
            dsp = n.get("char_sheet", {}).get("dark_side_points", 0)
            if dsp > 1:
                violations.append((n["name"], dsp))
        self.assertEqual(violations, [], f"DSP > 1: {violations}")

    def test_quarrens_have_correct_move(self):
        """Quarren canonically have move 8 (slower on land due to physiology)."""
        d = _load_yaml(DROP_C2_YAML)
        bad = []
        for n in d.get("npcs", []):
            if n.get("species") == "Quarren":
                move = n.get("char_sheet", {}).get("move")
                if move != 8:
                    bad.append((n["name"], move))
        self.assertEqual(bad, [], f"Quarren without move 8: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. Species diversity
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeciesDiversity(unittest.TestCase):

    def test_at_least_seven_species(self):
        """Coruscant is canonically cosmopolitan."""
        d = _load_yaml(DROP_C2_YAML)
        species = set(n.get("species") for n in d.get("npcs", []))
        self.assertGreaterEqual(
            len(species), 7,
            f"Coruscant should have ≥7 species; got {sorted(species)}"
        )

    def test_no_species_dominates(self):
        """Even Humans shouldn't be more than 65% of the roster."""
        d = _load_yaml(DROP_C2_YAML)
        npcs = d.get("npcs", [])
        from collections import Counter
        species = Counter(n.get("species") for n in npcs)
        most_common = species.most_common(1)[0]
        ratio = most_common[1] / max(len(npcs), 1)
        self.assertLess(
            ratio, 0.7,
            f"{most_common[0]} dominates ({ratio:.0%})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 12. Refugee network present (mirrors NS Drop G1/G2 pattern)
# ─────────────────────────────────────────────────────────────────────────────

class TestRefugeeNetworkPresent(unittest.TestCase):
    """Per the established pattern across Nar Shaddaa Drop G1/G2,
    the Refugee Sector / Refugee Warren has a coordinator NPC who
    works with a free medical post and a job broker. Coruscant's
    Lower City should have the same structure."""

    def test_refugee_coordinator_present(self):
        d = _load_yaml(DROP_C2_YAML)
        coords = [n for n in d["npcs"]
                  if "Refugee" in n["name"] and "Coordinator" in n["name"]]
        self.assertGreaterEqual(len(coords), 1,
                                "Lower City should have refugee coordinator")

    def test_medical_post_present(self):
        d = _load_yaml(DROP_C2_YAML)
        medical = [n for n in d["npcs"]
                   if "Medical" in n["room"] or "Medical" in n["name"]]
        self.assertGreaterEqual(len(medical), 1,
                                "Lower City should have medical post NPC")


# ─────────────────────────────────────────────────────────────────────────────
# 13. Source-level marker
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):

    def test_yaml_self_documents(self):
        with open(DROP_C2_YAML, "r", encoding="utf-8") as f:
            src = f.read()
        for marker in ("Drop C2", "Coruscant", "Coco Town",
                       "Lower City", "Q1", "Dexter", "FINAL"):
            self.assertIn(marker, src,
                          f"YAML header should mention {marker!r}")


if __name__ == "__main__":
    unittest.main()
