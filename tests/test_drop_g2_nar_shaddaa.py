# -*- coding: utf-8 -*-
"""
tests/test_drop_g2_nar_shaddaa.py — Drop G2 Nar Shaddaa Lower Levels roster.

Drop G2 (May 2026) completes Drop G per
`cw_content_gap_design_v1_1_decisions.md` Stage 4. Adds NPCs to the
17 Nar Shaddaa rooms G1 didn't cover: Hutt Emissary Tower (Lobby +
Audience Chamber), Spice Den, Fighting Pits, The Grid, 5 Warrens
sub-rooms, Undercity (Market + Depths), Enforcer Alley, Weapons
Cache, Upper Dock Observation, Promenade Corporate Tower.

Per architecture v39 §3.2 priority #1 (CW.NPCS track), this is
content-only — no engine changes.

Test sections:
  1. TestRosterFile                  — file exists, YAML parses
  2. TestRequiredFieldsPresent       — schema conformance
  3. TestRoomReferencesResolve       — rooms exist on Nar Shaddaa
  4. TestFactionCodes                — valid CW org codes
  5. TestQ1CanonicalCharacterPolicy  — no canonical Hutts/hunters
  6. TestEraConsistency              — mid-war framing
  7. TestEraManifestRef              — wired into era.yaml
  8. TestGrekAnchored                — FDtS Grek present with proper
                                        debt-transfer dialogue
  9. TestDragoFramedAsAbsent         — Drago the Hutt is canonical-
                                        reference, off-screen
 10. TestZoneCoverage                — all 17 G2-target zones covered
 11. TestSchemaMatchesVelaNireeReference
 12. TestStatBlockSanity
 13. TestSpeciesDiversity
 14. TestDocstringMarker
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
DROP_G2_YAML = os.path.join(CW_DIR, "npcs_drop_g2_nar_shaddaa_lower.yaml")


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


def _nar_shaddaa_room_names():
    d = _load_yaml(os.path.join(CW_DIR, "planets", "nar_shaddaa.yaml")) or {}
    return {r["name"] for r in (d.get("rooms") or []) if isinstance(r, dict) and r.get("name")}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Roster file
# ─────────────────────────────────────────────────────────────────────────────

class TestRosterFile(unittest.TestCase):

    def test_file_exists(self):
        self.assertTrue(os.path.exists(DROP_G2_YAML))

    def test_yaml_parses(self):
        d = _load_yaml(DROP_G2_YAML)
        self.assertIsInstance(d, dict)
        self.assertEqual(d.get("schema_version"), 1)

    def test_npc_count_in_target_range(self):
        """G2 target is ~25 NPCs."""
        d = _load_yaml(DROP_G2_YAML)
        npcs = d.get("npcs", [])
        self.assertGreaterEqual(len(npcs), 18,
                                f"G2 should have ~23 NPCs (got {len(npcs)})")
        self.assertLessEqual(len(npcs), 30,
                             f"G2 over scope (got {len(npcs)})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Required fields
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldsPresent(unittest.TestCase):

    REQUIRED = ("name", "room", "species", "description", "char_sheet", "ai_config")

    def test_all_npcs_have_required_fields(self):
        d = _load_yaml(DROP_G2_YAML)
        missing = []
        for i, n in enumerate(d.get("npcs", [])):
            for field in self.REQUIRED:
                if field not in n:
                    missing.append((n.get("name", f"#{i}"), field))
        self.assertEqual(missing, [], f"Missing fields: {missing}")

    def test_names_unique(self):
        d = _load_yaml(DROP_G2_YAML)
        names = [n["name"] for n in d.get("npcs", [])]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicates: {sorted(names)}")

    def test_no_collision_with_g1(self):
        """G2 names must not duplicate G1 names."""
        g1 = _load_yaml(os.path.join(CW_DIR, "npcs_drop_g1_nar_shaddaa_topside.yaml"))
        g2 = _load_yaml(DROP_G2_YAML)
        g1_names = {n["name"] for n in g1.get("npcs", [])}
        g2_names = {n["name"] for n in g2.get("npcs", [])}
        overlap = g1_names & g2_names
        self.assertEqual(overlap, set(),
                         f"G1/G2 name collisions: {overlap}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Room references
# ─────────────────────────────────────────────────────────────────────────────

class TestRoomReferencesResolve(unittest.TestCase):

    def test_all_rooms_exist_in_cw_world(self):
        d = _load_yaml(DROP_G2_YAML)
        cw_rooms = _all_cw_room_names()
        unresolved = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in cw_rooms]
        self.assertEqual(
            unresolved, [],
            f"Unresolved rooms:\n  " +
            "\n  ".join(f"{n} @ {r}" for n, r in unresolved)
        )

    def test_all_rooms_are_on_nar_shaddaa(self):
        d = _load_yaml(DROP_G2_YAML)
        ns_rooms = _nar_shaddaa_room_names()
        off_planet = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in ns_rooms]
        self.assertEqual(off_planet, [],
                         f"NPCs not on Nar Shaddaa: {off_planet}")

    def test_rooms_complement_g1(self):
        """G2 should target rooms G1 didn't cover."""
        g1 = _load_yaml(os.path.join(CW_DIR, "npcs_drop_g1_nar_shaddaa_topside.yaml"))
        g2 = _load_yaml(DROP_G2_YAML)
        g1_rooms = {n["room"] for n in g1.get("npcs", [])}
        g2_rooms = {n["room"] for n in g2.get("npcs", [])}
        # G2 should mostly add new room coverage
        new_in_g2 = g2_rooms - g1_rooms
        self.assertGreaterEqual(
            len(new_in_g2), 10,
            f"G2 should add ≥10 new rooms beyond G1; added {len(new_in_g2)}"
        )


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
        d = _load_yaml(DROP_G2_YAML)
        bad = [(n["name"], n["ai_config"]["faction"])
               for n in d.get("npcs", [])
               if n["ai_config"].get("faction")
               and n["ai_config"]["faction"] not in self.VALID_CODES]
        self.assertEqual(bad, [], f"Bad factions: {bad}")

    def test_hutt_tower_npcs_are_cartel(self):
        """All Hutt Emissary Tower NPCs should be hutt_cartel."""
        d = _load_yaml(DROP_G2_YAML)
        bad = []
        for n in d.get("npcs", []):
            if "Hutt Emissary Tower" in n["room"]:
                fac = n["ai_config"]["faction"]
                if fac != "hutt_cartel":
                    bad.append((n["name"], fac))
        self.assertEqual(bad, [],
                         f"Hutt Tower NPCs not hutt_cartel: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Q1 canonical-character policy
# ─────────────────────────────────────────────────────────────────────────────

class TestQ1CanonicalCharacterPolicy(unittest.TestCase):

    CANONICAL_FORBIDDEN = {
        # Canonical CW Hutts
        "Jabba", "Jabba Desilijic Tiure", "Ziro", "Ziro the Hutt",
        "Gardulla", "Gardulla the Hutt", "Rotta", "Bib Fortuna",
        # Canonical CW bounty hunters
        "Hondo Ohnaka", "Cad Bane", "Aurra Sing", "Boba Fett",
        "Sugi", "Embo", "Latts Razzi", "Bossk", "Greedo",
        "Dengar", "IG-88",
        # Canonical Black Sun
        "Xizor", "Prince Xizor",
        # Canonical Council/Senate
        "Yoda", "Mace Windu", "Anakin Skywalker", "Obi-Wan Kenobi",
        "Padmé Amidala", "Bail Organa", "Mon Mothma",
        "Captain Rex", "Commander Cody",
    }

    def test_no_canonical_named_npcs(self):
        d = _load_yaml(DROP_G2_YAML)
        violations = []
        for n in d.get("npcs", []):
            name = n["name"]
            for forbidden in self.CANONICAL_FORBIDDEN:
                if re.search(r"\b" + re.escape(forbidden) + r"\b", name):
                    violations.append((name, forbidden))
        self.assertEqual(violations, [],
                         f"Canonical figures in roster: {violations}")

    def test_canonical_mentions_framed_as_absent(self):
        d = _load_yaml(DROP_G2_YAML)
        framed = {"Jabba", "Ziro", "Hondo", "Cad Bane",
                  "Bossk", "Xizor", "Yoda"}
        absence_markers = (
            "off-world", "absent", "not here", "in the field",
            "elsewhere", "rumor", "doesn't comment", "won't comment",
            "canonical-reference", "canonical reference",
            "currently", "last", "recently", "off-screen",
        )
        violations = []
        for n in d.get("npcs", []):
            text = (n.get("description", "") + " "
                    + str(n.get("ai_config", {}).get("personality", ""))
                    + " "
                    + " ".join(n.get("ai_config", {}).get("knowledge", []) or []))
            for fname in framed:
                if fname.lower() in text.lower():
                    if not any(m.lower() in text.lower() for m in absence_markers):
                        violations.append((n["name"], fname))
        self.assertEqual(violations, [],
                         f"Canonical mentions without absence framing: {violations}")


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
        d = _load_yaml(DROP_G2_YAML)
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

    def test_era_yaml_includes_drop_g2(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        self.assertIn("npcs_drop_g2_nar_shaddaa_lower.yaml", npcs_refs)

    def test_pre_existing_npc_files_still_referenced(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        for f in ("npcs_cw_additions.yaml", "npcs_cw_replacements.yaml",
                  "npcs_drop_h_combat.yaml", "npcs_drop_c1_coruscant.yaml",
                  "npcs_drop_def_civilians.yaml",
                  "npcs_drop_g1_nar_shaddaa_topside.yaml"):
            self.assertIn(f, npcs_refs,
                          f"Pre-existing ref {f!r} dropped")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Grek anchored with FDtS routing
# ─────────────────────────────────────────────────────────────────────────────

class TestGrekAnchored(unittest.TestCase):
    """Grek is the FDtS loanshark fixer (Drago the Hutt's enforcer face).
    Per gg6_tramp_freighters_extraction_v1.md §8.3, Grek is grounded in
    the Yerkys ne Dago archetype with stats reduced 1D throughout."""

    def test_grek_present(self):
        d = _load_yaml(DROP_G2_YAML)
        names = {n["name"] for n in d.get("npcs", [])}
        self.assertIn("Grek", names, "Grek must be present (FDtS anchor)")

    def test_grek_at_audience_chamber(self):
        d = _load_yaml(DROP_G2_YAML)
        grek = next(n for n in d["npcs"] if n["name"] == "Grek")
        self.assertEqual(grek["room"],
                         "Nar Shaddaa - Hutt Emissary Tower - Audience Chamber",
                         "Grek should be in Borka the Hutt's Audience Chamber")

    def test_grek_is_twilek(self):
        """Per J1 §8.3, Grek inherits Yerkys ne Dago's species (Twi'lek)."""
        d = _load_yaml(DROP_G2_YAML)
        grek = next(n for n in d["npcs"] if n["name"] == "Grek")
        self.assertEqual(grek["species"], "Twi'lek")

    def test_grek_has_debt_transfer_response(self):
        """Per FDtS Phase 5, when player buys the Mynock, the Drago debt
        transfers to the player and Grek delivers the welcome line."""
        d = _load_yaml(DROP_G2_YAML)
        grek = next(n for n in d["npcs"] if n["name"] == "Grek")
        dr = grek["ai_config"].get("directed_responses", {})
        self.assertIn("debt_transferred", dr,
                      "Grek should have debt_transferred directed response")

    def test_grek_stats_reduced_from_yerkys_baseline(self):
        """Per J1 §8.3, Grek's stats are Yerkys ne Dago reduced 1D.
        Yerkys baseline KNO is 4D; Grek's should be 3D. Yerkys MEC is
        2D+2; Grek's should be 1D+2. Verify the 1D reduction landed."""
        d = _load_yaml(DROP_G2_YAML)
        grek = next(n for n in d["npcs"] if n["name"] == "Grek")
        attrs = grek["char_sheet"]["attributes"]
        # KNO: Yerkys 4D → Grek 3D
        self.assertEqual(attrs["knowledge"], "3D",
                         f"Grek KNO should be 3D (Yerkys 4D - 1D); got {attrs['knowledge']}")
        # MEC: Yerkys 2D+2 → Grek 1D+2
        self.assertEqual(attrs["mechanical"], "1D+2",
                         f"Grek MEC should be 1D+2 (Yerkys 2D+2 - 1D); got {attrs['mechanical']}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Drago framed as absent
# ─────────────────────────────────────────────────────────────────────────────

class TestDragoFramedAsAbsent(unittest.TestCase):
    """Drago the Hutt is the FDtS loanshark proper but per Q1 he does
    not appear as an Ollama-driven NPC. Borka the Hutt represents
    Drago's interests on Nar Shaddaa. Any mention of Drago must be
    framed as canonical-reference / off-screen."""

    def test_no_drago_npc(self):
        d = _load_yaml(DROP_G2_YAML)
        names = {n["name"] for n in d.get("npcs", [])}
        for n in names:
            self.assertNotIn("Drago", n,
                             f"Drago should not appear as an NPC; found {n!r}")

    def test_drago_mentions_have_absence_framing(self):
        d = _load_yaml(DROP_G2_YAML)
        absence_markers = (
            "canonical-reference", "off-world", "off-screen",
            "off world", "off screen", "not here", "absent",
            "remains", "estate",
        )
        violations = []
        for n in d.get("npcs", []):
            text = (n.get("description", "") + " "
                    + str(n.get("ai_config", {}).get("personality", ""))
                    + " "
                    + " ".join(n.get("ai_config", {}).get("knowledge", []) or []))
            if "Drago" in text:
                if not any(m.lower() in text.lower() for m in absence_markers):
                    violations.append(n["name"])
        self.assertEqual(violations, [],
                         f"Drago mentions without absence framing: {violations}")

    def test_borka_the_hutt_present(self):
        """The Hutt face on Nar Shaddaa is Borka, not Drago."""
        d = _load_yaml(DROP_G2_YAML)
        names = {n["name"] for n in d.get("npcs", [])}
        borka_present = any("Borka" in n for n in names)
        self.assertTrue(borka_present,
                        "Borka the Hutt should be the Hutt face in the Audience Chamber")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Zone coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestZoneCoverage(unittest.TestCase):
    """G2 should cover the 17 Nar Shaddaa rooms G1 didn't."""

    EXPECTED_ZONES = {
        "Hutt Emissary Tower",
        "Spice Den",
        "Fighting Pits",
        "The Grid",
        "Warrens",
        "Undercity",
        "Enforcer Alley",
        "Weapons Cache",
        "Upper Dock Observation",
        "Promenade - Corporate Tower",
    }

    def test_all_zones_have_npcs(self):
        d = _load_yaml(DROP_G2_YAML)
        rooms = {n["room"] for n in d.get("npcs", [])}
        missing = []
        for zone in self.EXPECTED_ZONES:
            if not any(zone in r for r in rooms):
                missing.append(zone)
        self.assertEqual(missing, [],
                         f"Zones missing NPCs: {missing}")

    def test_warrens_has_multiple_sub_rooms(self):
        """The Warrens has 5 sub-rooms; G2 should populate most."""
        d = _load_yaml(DROP_G2_YAML)
        warrens_rooms = {n["room"] for n in d["npcs"]
                         if "Warrens" in n["room"]}
        self.assertGreaterEqual(len(warrens_rooms), 4,
                                f"Warrens should have ≥4 sub-rooms populated: {warrens_rooms}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. Schema conformance
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
        d = _load_yaml(DROP_G2_YAML)
        violations = []
        for n in d.get("npcs", []):
            ai = n.get("ai_config", {})
            for field in self.AI_CONFIG_REQUIRED:
                if field not in ai:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"AI config schema: {violations}")

    def test_char_sheet_canonical_fields(self):
        d = _load_yaml(DROP_G2_YAML)
        violations = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {})
            for field in self.CHAR_SHEET_REQUIRED:
                if field not in cs:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"Char sheet schema: {violations}")

    def test_fallback_lines_nonempty(self):
        d = _load_yaml(DROP_G2_YAML)
        bad = [(n["name"], len(n.get("ai_config", {}).get("fallback_lines", [])))
               for n in d.get("npcs", [])
               if len(n.get("ai_config", {}).get("fallback_lines", [])) < 3]
        self.assertEqual(bad, [], f"<3 fallback lines: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. Stat-block sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestStatBlockSanity(unittest.TestCase):

    def test_attribute_codes_look_like_d_codes(self):
        DCODE = re.compile(r"^\d+D(\+[12])?$")
        d = _load_yaml(DROP_G2_YAML)
        violations = []
        for n in d.get("npcs", []):
            attrs = n.get("char_sheet", {}).get("attributes", {})
            for stat, val in attrs.items():
                if not DCODE.match(str(val)):
                    violations.append((n["name"], stat, val))
        self.assertEqual(violations, [], f"Bad D-codes: {violations}")

    def test_dsp_constraints(self):
        """Most G2 NPCs have DSP=0 or 1 (corruption-coded fixers,
        chamberlain, enforcer captain, corporate liaison). Anything
        higher is a flag."""
        d = _load_yaml(DROP_G2_YAML)
        violations = []
        for n in d.get("npcs", []):
            dsp = n.get("char_sheet", {}).get("dark_side_points", 0)
            if dsp > 1:
                violations.append((n["name"], dsp))
        self.assertEqual(violations, [], f"DSP > 1: {violations}")

    def test_trandoshans_have_correct_move(self):
        """Trandoshans canonically have move 11."""
        d = _load_yaml(DROP_G2_YAML)
        bad = []
        for n in d.get("npcs", []):
            if n.get("species") == "Trandoshan":
                move = n.get("char_sheet", {}).get("move")
                if move != 11:
                    bad.append((n["name"], move))
        self.assertEqual(bad, [], f"Trandoshans without move 11: {bad}")

    def test_hutts_have_low_move(self):
        """Hutts have move 2 due to their slug-like locomotion."""
        d = _load_yaml(DROP_G2_YAML)
        bad = []
        for n in d.get("npcs", []):
            if n.get("species") == "Hutt":
                move = n.get("char_sheet", {}).get("move")
                if move > 4:
                    bad.append((n["name"], move))
        self.assertEqual(bad, [],
                         f"Hutts with too-high move: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 13. Species diversity
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeciesDiversity(unittest.TestCase):

    def test_at_least_eight_species(self):
        d = _load_yaml(DROP_G2_YAML)
        species = set(n.get("species") for n in d.get("npcs", []))
        self.assertGreaterEqual(
            len(species), 8,
            f"Lower-levels Nar Shaddaa should have ≥8 species; got {sorted(species)}"
        )

    def test_hutt_present(self):
        """Borka the Hutt is the planet's Hutt face. There should be ≥1 Hutt."""
        d = _load_yaml(DROP_G2_YAML)
        hutts = [n for n in d["npcs"] if n.get("species") == "Hutt"]
        self.assertGreaterEqual(len(hutts), 1, "Should have ≥1 Hutt NPC")

    def test_no_species_dominates(self):
        """Even Humans shouldn't be more than 65% of the roster."""
        d = _load_yaml(DROP_G2_YAML)
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
# 14. Source-level marker
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):

    def test_yaml_self_documents(self):
        with open(DROP_G2_YAML, "r", encoding="utf-8") as f:
            src = f.read()
        for marker in ("Drop G2", "Nar Shaddaa", "Q1", "Grek",
                       "Hutt Emissary Tower", "Warrens"):
            self.assertIn(marker, src,
                          f"YAML header should mention {marker!r}")


if __name__ == "__main__":
    unittest.main()
