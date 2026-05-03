# -*- coding: utf-8 -*-
"""
tests/test_drop_def_civilians.py — Drops D + E + F (batched) civilian rosters.

Drops D + E + F (May 2026) are the sparse-density civilian rosters
for Kamino, Geonosis, and Kuat per
`cw_content_gap_design_v1_1_decisions.md` Stage 4. Batched into a
single file because each individually is small (~9 NPCs) and they
share the same authoring pattern (~0.3 NPCs/room sparse civilians
per Q6 density target). Together with Drop H's combat templates,
this brings all six CW player-facing planets to a baseline-populated
state — only Nar Shaddaa (Drop G) remains at 0 NPCs after this drop.

Per architecture v39 §3.2 priority #1 (CW.NPCS track), this is
content-only — no engine changes, no DB schema changes, no
command additions. The roster file is wired into CW `era.yaml`
via `content_refs.npcs`.

Test sections:
  1. TestRosterFile                  — file exists, YAML parses, right shape
  2. TestRequiredFieldsPresent       — every NPC has the canonical schema
  3. TestRoomReferencesResolve       — every room is a real CW room
  4. TestPlanetCoverage              — all three planets covered
  5. TestFactionCodes                — every faction is a valid CW org code
  6. TestQ1CanonicalCharacterPolicy  — no canonical figures
                                        (no Lama Su / Taun We /
                                        Poggle / Wat Tambor / Gunray /
                                        canonical House principals)
  7. TestEraConsistency              — no post-Order-66 leaks (Q2)
  8. TestEraManifestRef              — wired into era.yaml
  9. TestSchemaMatchesVelaNireeReference — fields conform
 10. TestStatBlockSanity             — droids, force-points, attribute codes
 11. TestSpeciesDiversity            — at least 5 species across the batch
 12. TestDocstringMarker             — source-level guard
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
DROP_DEF_YAML = os.path.join(CW_DIR, "npcs_drop_def_civilians.yaml")


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


def _planet_of(room_name):
    for p in ("Kamino", "Geonosis", "Kuat"):
        if p in room_name:
            return p
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Roster file present + well-formed
# ─────────────────────────────────────────────────────────────────────────────

class TestRosterFile(unittest.TestCase):

    def test_file_exists(self):
        self.assertTrue(os.path.exists(DROP_DEF_YAML),
                        f"Drop D+E+F roster missing at {DROP_DEF_YAML}")

    def test_yaml_parses(self):
        d = _load_yaml(DROP_DEF_YAML)
        self.assertIsInstance(d, dict)
        self.assertEqual(d.get("schema_version"), 1)

    def test_npc_count_in_target_range(self):
        """Drop D+E+F target is ~27 NPCs (~9 each)."""
        d = _load_yaml(DROP_DEF_YAML)
        npcs = d.get("npcs", [])
        self.assertGreaterEqual(len(npcs), 20,
                                f"D+E+F batch should have ~27 NPCs (got {len(npcs)})")
        self.assertLessEqual(len(npcs), 33,
                             f"D+E+F over scope (got {len(npcs)})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Required fields
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldsPresent(unittest.TestCase):

    REQUIRED = ("name", "room", "species", "description", "char_sheet", "ai_config")

    def test_all_npcs_have_required_fields(self):
        d = _load_yaml(DROP_DEF_YAML)
        missing = []
        for i, n in enumerate(d.get("npcs", [])):
            for field in self.REQUIRED:
                if field not in n:
                    missing.append((n.get("name", f"#{i}"), field))
        self.assertEqual(missing, [],
                         f"Missing fields: {missing}")

    def test_names_unique(self):
        d = _load_yaml(DROP_DEF_YAML)
        names = [n["name"] for n in d.get("npcs", [])]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicates: {sorted(names)}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Room references
# ─────────────────────────────────────────────────────────────────────────────

class TestRoomReferencesResolve(unittest.TestCase):

    def test_all_rooms_exist_in_cw_world(self):
        d = _load_yaml(DROP_DEF_YAML)
        cw_rooms = _all_cw_room_names()
        unresolved = []
        for n in d.get("npcs", []):
            if n["room"] not in cw_rooms:
                unresolved.append((n["name"], n["room"]))
        self.assertEqual(
            unresolved, [],
            f"NPCs reference non-existent CW rooms:\n  " +
            "\n  ".join(f"{name} @ {room}" for name, room in unresolved)
        )

    def test_all_rooms_are_on_def_planets(self):
        """All NPCs in this batch are on Kamino, Geonosis, or Kuat."""
        d = _load_yaml(DROP_DEF_YAML)
        off_planet = []
        for n in d.get("npcs", []):
            if _planet_of(n["room"]) is None:
                off_planet.append((n["name"], n["room"]))
        self.assertEqual(off_planet, [],
                         f"NPCs not on Kamino/Geonosis/Kuat: {off_planet}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Planet coverage — each of D/E/F has NPCs
# ─────────────────────────────────────────────────────────────────────────────

class TestPlanetCoverage(unittest.TestCase):

    def test_kamino_has_multiple_npcs(self):
        d = _load_yaml(DROP_DEF_YAML)
        kamino_npcs = [n for n in d["npcs"] if _planet_of(n["room"]) == "Kamino"]
        self.assertGreaterEqual(len(kamino_npcs), 7,
                                f"Drop D (Kamino): {len(kamino_npcs)} NPCs")

    def test_geonosis_has_multiple_npcs(self):
        d = _load_yaml(DROP_DEF_YAML)
        geo_npcs = [n for n in d["npcs"] if _planet_of(n["room"]) == "Geonosis"]
        self.assertGreaterEqual(len(geo_npcs), 7,
                                f"Drop E (Geonosis): {len(geo_npcs)} NPCs")

    def test_kuat_has_multiple_npcs(self):
        d = _load_yaml(DROP_DEF_YAML)
        kuat_npcs = [n for n in d["npcs"] if _planet_of(n["room"]) == "Kuat"]
        self.assertGreaterEqual(len(kuat_npcs), 7,
                                f"Drop F (Kuat): {len(kuat_npcs)} NPCs")


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
        d = _load_yaml(DROP_DEF_YAML)
        bad = []
        for n in d.get("npcs", []):
            fac = n.get("ai_config", {}).get("faction", "")
            if fac and fac not in self.VALID_CODES:
                bad.append((n["name"], fac))
        self.assertEqual(bad, [], f"Bad factions: {bad}")

    def test_geonosis_has_cis_npcs(self):
        """Geonosis is the CIS heartland — should have cis-coded NPCs."""
        d = _load_yaml(DROP_DEF_YAML)
        geo_cis = [n for n in d["npcs"]
                   if _planet_of(n["room"]) == "Geonosis"
                   and n["ai_config"]["faction"] == "cis"]
        self.assertGreaterEqual(len(geo_cis), 2,
                                f"Geonosis should have ≥2 CIS NPCs: {len(geo_cis)}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Q1 — No canonical figures
# ─────────────────────────────────────────────────────────────────────────────

class TestQ1CanonicalCharacterPolicy(unittest.TestCase):
    """Per cw_content_gap_design_v1_1_decisions.md Q1 (EXTREMELY
    RESTRICTED), no canonical CW figures appear in this open-world
    roster."""

    CANONICAL_KAMINO_FORBIDDEN = {
        "Lama Su", "Taun We", "Nala Se", "Jango Fett",
        "Boba Fett", "Sifo-Dyas", "Shaak Ti",
    }

    CANONICAL_GEONOSIS_FORBIDDEN = {
        "Poggle", "Poggle the Lesser",
        "Wat Tambor", "Nute Gunray", "San Hill",
        "Shu Mai", "Passel Argente", "Rush Clovis",
        "Mina Bonteri", "Dooku", "Count Dooku",
        "Asajj Ventress", "Grievous", "General Grievous",
    }

    CANONICAL_KUAT_FORBIDDEN = {
        # Canonical House Andrim/Purkis principals — leaving room for
        # non-canonical members of the families
        "Kuat of Kuat", "Brigadier Kuat",
    }

    OTHER_FORBIDDEN = {
        # Other Q1-restricted figures from architecture v39 / cw_content_gap
        "Yoda", "Mace Windu", "Obi-Wan Kenobi", "Anakin Skywalker",
        "Plo Koon", "Ki-Adi-Mundi", "Kit Fisto",
        "Cad Bane", "Hondo Ohnaka",
        "Captain Rex", "Commander Cody", "Commander Wolffe",
        "Commander Fox", "99", "Maintenance Clone 99",
    }

    @property
    def all_forbidden(self):
        return (self.CANONICAL_KAMINO_FORBIDDEN
                | self.CANONICAL_GEONOSIS_FORBIDDEN
                | self.CANONICAL_KUAT_FORBIDDEN
                | self.OTHER_FORBIDDEN)

    def test_no_canonical_named_npcs(self):
        d = _load_yaml(DROP_DEF_YAML)
        violations = []
        for n in d.get("npcs", []):
            name = n["name"]
            for forbidden in self.all_forbidden:
                if re.search(r"\b" + re.escape(forbidden) + r"\b", name):
                    violations.append((name, forbidden))
        self.assertEqual(
            violations, [],
            f"Q1 policy violation — canonical figures in roster: {violations}"
        )

    def test_canonical_mentions_framed_as_absent(self):
        """Mentions of canonical figures in description/personality/knowledge
        text must be framed as absent/off-screen, not present-in-scene."""
        d = _load_yaml(DROP_DEF_YAML)
        framed = {"Lama Su", "Taun We", "Poggle", "Wat Tambor",
                  "Nute Gunray", "Mina Bonteri", "Dooku", "Sidious",
                  "Maintenance Clone 99"}
        absence_markers = (
            "off-world", "off world", "absent", "not here",
            "in the field", "deployed", "rarely", "doesn't comment",
            "won't comment", "won't share", "off-screen", "off screen",
            "canonical-reference", "canonical reference",
            "currently", "last", "recently", "killed",
            "(canonical", "rumor",
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
        self.assertEqual(
            violations, [],
            f"NPCs mention canonical figures without absence framing: {violations}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Q2 — era consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestEraConsistency(unittest.TestCase):

    POST_ORDER_66_LEAKS = (
        "Galactic Empire", "Imperial Senate", "Imperial Stormtrooper",
        "Vader", "Darth Vader", "Tarkin", "Krennic",
        "Rebellion", "Rebel Alliance", "post-war",
        "after the war", "Imperial occupation",
    )

    def test_no_post_order_66_references(self):
        d = _load_yaml(DROP_DEF_YAML)
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

    def test_era_yaml_includes_drop_def(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        self.assertIn("npcs_drop_def_civilians.yaml", npcs_refs)

    def test_pre_existing_npc_files_still_referenced(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        for f in ("npcs_cw_additions.yaml", "npcs_cw_replacements.yaml",
                  "npcs_drop_h_combat.yaml", "npcs_drop_c1_coruscant.yaml"):
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
        d = _load_yaml(DROP_DEF_YAML)
        violations = []
        for n in d.get("npcs", []):
            ai = n.get("ai_config", {})
            for field in self.AI_CONFIG_REQUIRED:
                if field not in ai:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"AI config schema: {violations}")

    def test_char_sheet_canonical_fields(self):
        d = _load_yaml(DROP_DEF_YAML)
        violations = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {})
            for field in self.CHAR_SHEET_REQUIRED:
                if field not in cs:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"Char sheet schema: {violations}")

    def test_fallback_lines_nonempty(self):
        d = _load_yaml(DROP_DEF_YAML)
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
        d = _load_yaml(DROP_DEF_YAML)
        violations = []
        for n in d.get("npcs", []):
            attrs = n.get("char_sheet", {}).get("attributes", {})
            for stat, val in attrs.items():
                if not DCODE.match(str(val)):
                    violations.append((n["name"], stat, val))
        self.assertEqual(violations, [], f"Bad D-codes: {violations}")

    def test_no_excessive_dark_side_points(self):
        """Civilian NPCs should mostly have DSP=0; the lobbyist-equivalent
        types may have DSP=1 (Naam, Kkal-rrt). DSP > 1 is a flag."""
        d = _load_yaml(DROP_DEF_YAML)
        violations = []
        for n in d.get("npcs", []):
            dsp = n.get("char_sheet", {}).get("dark_side_points", 0)
            if dsp > 1:
                violations.append((n["name"], dsp))
        self.assertEqual(violations, [], f"DSP > 1 in civilian roster: {violations}")

    def test_kaminoans_have_correct_move(self):
        """Kaminoans canonically have move 12 (longer stride, taller species)."""
        d = _load_yaml(DROP_DEF_YAML)
        bad = []
        for n in d.get("npcs", []):
            if n.get("species") == "Kaminoan":
                move = n.get("char_sheet", {}).get("move")
                if move != 12:
                    bad.append((n["name"], move))
        self.assertEqual(bad, [],
                         f"Kaminoans without move 12: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. Species diversity
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeciesDiversity(unittest.TestCase):
    """The three planets together should show meaningful species
    diversity — not just humans."""

    def test_at_least_five_species(self):
        d = _load_yaml(DROP_DEF_YAML)
        species = set(n.get("species") for n in d.get("npcs", []))
        self.assertGreaterEqual(
            len(species), 5,
            f"D+E+F should have ≥5 species; got {sorted(species)}"
        )

    def test_kaminoans_present_on_kamino(self):
        d = _load_yaml(DROP_DEF_YAML)
        kaminoans = [n for n in d["npcs"]
                     if n.get("species") == "Kaminoan"
                     and _planet_of(n["room"]) == "Kamino"]
        self.assertGreaterEqual(len(kaminoans), 2,
                                f"Kamino should have Kaminoans: {len(kaminoans)}")

    def test_geonosians_present_on_geonosis(self):
        d = _load_yaml(DROP_DEF_YAML)
        geos = [n for n in d["npcs"]
                if n.get("species") == "Geonosian"
                and _planet_of(n["room"]) == "Geonosis"]
        self.assertGreaterEqual(len(geos), 1,
                                f"Geonosis should have Geonosian civilians: {len(geos)}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. Source-level marker
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):

    def test_yaml_self_documents(self):
        with open(DROP_DEF_YAML, "r", encoding="utf-8") as f:
            src = f.read()
        for marker in ("Drop D", "Drop E", "Drop F", "Kamino",
                       "Geonosis", "Kuat", "Q1", "EXTREMELY RESTRICTED"):
            self.assertIn(marker, src,
                          f"YAML header should mention {marker!r}")


if __name__ == "__main__":
    unittest.main()
