# -*- coding: utf-8 -*-
"""
tests/test_drop_g1_nar_shaddaa.py — Drop G1 Nar Shaddaa Topside roster.

Drop G1 (May 2026) is the first half of Drop G per
`cw_content_gap_design_v1_1_decisions.md` Stage 4. Drop G is the
largest single CW.NPCS drop (~50 NPCs, the canonical Smuggler's
Moon target density). To keep authoring tractable, G is split:

  G1 (this file): Topside / commercial / FDtS-anchor zones —
                  ~22 NPCs covering 16 rooms
  G2 (future):    Hutt Tower / Warrens / Spice Den / Fighting
                  Pits / Undercity — ~25 NPCs covering 16 rooms

After G2, all 6 player-facing CW planets are populated and the
CW.NPCS track is essentially closed (Drop B Mos Eisley CW additions
and Drop C2 Coruscant Coco Town/Underworld remain as smaller polish
drops).

Per architecture v39 §3.2 priority #1 (CW.NPCS track), this is
content-only — no engine changes, no DB schema changes.

Test sections:
  1. TestRosterFile                  — file exists, YAML parses
  2. TestRequiredFieldsPresent       — schema conformance
  3. TestRoomReferencesResolve       — rooms exist on Nar Shaddaa
  4. TestFactionCodes                — valid CW org codes
  5. TestQ1CanonicalCharacterPolicy  — no canonical hunters/Hutts
  6. TestEraConsistency              — mid-war framing
  7. TestEraManifestRef              — wired into era.yaml
  8. TestFDtSCharactersPresent       — Mak/Zekka/Renna/Doc Myrra
                                        all anchored
  9. TestFDtSDialogueAlignment       — FDtS Step 14 dialogues exist
                                        as directed_responses
 10. TestSchemaMatchesVelaNireeReference
 11. TestStatBlockSanity
 12. TestSpeciesDiversity            — Smuggler's Moon should be
                                        cosmopolitan
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
DROP_G1_YAML = os.path.join(CW_DIR, "npcs_drop_g1_nar_shaddaa_topside.yaml")


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
        self.assertTrue(os.path.exists(DROP_G1_YAML))

    def test_yaml_parses(self):
        d = _load_yaml(DROP_G1_YAML)
        self.assertIsInstance(d, dict)
        self.assertEqual(d.get("schema_version"), 1)

    def test_npc_count_in_target_range(self):
        """G1 target is ~25 NPCs (half of Drop G's ~50)."""
        d = _load_yaml(DROP_G1_YAML)
        npcs = d.get("npcs", [])
        self.assertGreaterEqual(len(npcs), 18,
                                f"G1 should have ~22 NPCs (got {len(npcs)})")
        self.assertLessEqual(len(npcs), 30,
                             f"G1 over scope (got {len(npcs)})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Required fields
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldsPresent(unittest.TestCase):

    REQUIRED = ("name", "room", "species", "description", "char_sheet", "ai_config")

    def test_all_npcs_have_required_fields(self):
        d = _load_yaml(DROP_G1_YAML)
        missing = []
        for i, n in enumerate(d.get("npcs", [])):
            for field in self.REQUIRED:
                if field not in n:
                    missing.append((n.get("name", f"#{i}"), field))
        self.assertEqual(missing, [],
                         f"Missing fields: {missing}")

    def test_names_unique(self):
        d = _load_yaml(DROP_G1_YAML)
        names = [n["name"] for n in d.get("npcs", [])]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicates: {sorted(names)}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Room references
# ─────────────────────────────────────────────────────────────────────────────

class TestRoomReferencesResolve(unittest.TestCase):

    def test_all_rooms_exist_in_cw_world(self):
        d = _load_yaml(DROP_G1_YAML)
        cw_rooms = _all_cw_room_names()
        unresolved = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in cw_rooms]
        self.assertEqual(
            unresolved, [],
            f"Unresolved rooms:\n  " +
            "\n  ".join(f"{n} @ {r}" for n, r in unresolved)
        )

    def test_all_rooms_are_on_nar_shaddaa(self):
        d = _load_yaml(DROP_G1_YAML)
        ns_rooms = _nar_shaddaa_room_names()
        off_planet = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in ns_rooms]
        self.assertEqual(off_planet, [],
                         f"NPCs not on Nar Shaddaa: {off_planet}")


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
        d = _load_yaml(DROP_G1_YAML)
        bad = [(n["name"], n["ai_config"]["faction"])
               for n in d.get("npcs", [])
               if n["ai_config"].get("faction")
               and n["ai_config"]["faction"] not in self.VALID_CODES]
        self.assertEqual(bad, [], f"Bad factions: {bad}")

    def test_hutt_cartel_presence(self):
        """Nar Shaddaa is Cartel-controlled. Should have Cartel-coded NPCs."""
        d = _load_yaml(DROP_G1_YAML)
        cartel = [n for n in d["npcs"]
                  if n["ai_config"]["faction"] == "hutt_cartel"]
        self.assertGreaterEqual(len(cartel), 4,
                                f"Nar Shaddaa should have ≥4 Cartel NPCs: {len(cartel)}")

    def test_independent_majority(self):
        """Smuggler's Moon should have a strong independent contingent."""
        d = _load_yaml(DROP_G1_YAML)
        indie = [n for n in d["npcs"]
                 if n["ai_config"]["faction"] == "independent"]
        self.assertGreaterEqual(len(indie), 8,
                                f"Smuggler's Moon should have ≥8 independents: {len(indie)}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Q1 canonical-character policy
# ─────────────────────────────────────────────────────────────────────────────

class TestQ1CanonicalCharacterPolicy(unittest.TestCase):

    CANONICAL_NAR_SHADDAA_FORBIDDEN = {
        # Canonical CW Hutts who could plausibly be on Nar Shaddaa
        "Jabba", "Jabba Desilijic Tiure", "Ziro", "Ziro the Hutt",
        "Gardulla", "Gardulla the Hutt", "Rotta", "Bib Fortuna",
        # Canonical CW bounty hunters
        "Hondo Ohnaka", "Cad Bane", "Aurra Sing", "Boba Fett",
        "Sugi", "Embo", "Latts Razzi", "Bossk", "Greedo",
        "Dengar", "IG-88", "4-LOM", "Zuckuss",
        # Canonical Black Sun figures
        "Xizor", "Prince Xizor",
    }
    OTHER_FORBIDDEN = {
        "Yoda", "Mace Windu", "Obi-Wan Kenobi", "Anakin Skywalker",
        "Plo Koon", "Ahsoka Tano", "Asajj Ventress", "Dooku",
        "Padmé Amidala", "Bail Organa", "Mon Mothma",
        "Captain Rex", "Commander Cody",
    }

    @property
    def all_forbidden(self):
        return self.CANONICAL_NAR_SHADDAA_FORBIDDEN | self.OTHER_FORBIDDEN

    def test_no_canonical_named_npcs(self):
        d = _load_yaml(DROP_G1_YAML)
        violations = []
        for n in d.get("npcs", []):
            name = n["name"]
            for forbidden in self.all_forbidden:
                if re.search(r"\b" + re.escape(forbidden) + r"\b", name):
                    violations.append((name, forbidden))
        self.assertEqual(violations, [],
                         f"Canonical figures in roster: {violations}")

    def test_canonical_mentions_framed_as_absent(self):
        """Mentions of canonical figures in description/personality/knowledge
        text must be framed as absent/off-screen."""
        d = _load_yaml(DROP_G1_YAML)
        framed = {"Jabba", "Ziro", "Hondo", "Cad Bane", "Aurra Sing",
                  "Boba Fett", "Bossk", "Xizor"}
        absence_markers = (
            "off-world", "absent", "not here", "in the field",
            "elsewhere", "rumor", "doesn't comment", "won't comment",
            "canonical-reference", "canonical reference",
            "currently", "last", "recently",
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
        d = _load_yaml(DROP_G1_YAML)
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

    def test_era_yaml_includes_drop_g1(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        self.assertIn("npcs_drop_g1_nar_shaddaa_topside.yaml", npcs_refs)

    def test_pre_existing_npc_files_still_referenced(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        for f in ("npcs_cw_additions.yaml", "npcs_cw_replacements.yaml",
                  "npcs_drop_h_combat.yaml", "npcs_drop_c1_coruscant.yaml",
                  "npcs_drop_def_civilians.yaml"):
            self.assertIn(f, npcs_refs,
                          f"Pre-existing ref {f!r} dropped")


# ─────────────────────────────────────────────────────────────────────────────
# 8. FDtS character anchors present
# ─────────────────────────────────────────────────────────────────────────────

class TestFDtSCharactersPresent(unittest.TestCase):
    """Per from_dust_to_stars_design_v2_clone_wars.md Step 14, the
    player must be able to find Zekka Thansen, Renna Dox, and
    Doc Myrra on Nar Shaddaa. Mak Torvin is also referenced (the
    quest-giver who sent the player; he lives on Tatooine in the
    FDtS framing but appears on Nar Shaddaa in some Phase 3 steps —
    G1 places him in the Old Corellian Quarter)."""

    def test_mak_torvin_present(self):
        d = _load_yaml(DROP_G1_YAML)
        names = {n["name"] for n in d.get("npcs", [])}
        self.assertIn("Mak Torvin", names,
                      "Mak Torvin must be present (FDtS quest-giver)")

    def test_zekka_thansen_present(self):
        d = _load_yaml(DROP_G1_YAML)
        names = {n["name"] for n in d.get("npcs", [])}
        self.assertIn("Zekka Thansen", names,
                      "Zekka Thansen must be present (FDtS Step 14 anchor)")

    def test_renna_dox_present(self):
        d = _load_yaml(DROP_G1_YAML)
        names = {n["name"] for n in d.get("npcs", [])}
        self.assertIn("Renna Dox", names,
                      "Renna Dox must be present (FDtS Step 14 anchor)")

    def test_doc_myrra_present(self):
        d = _load_yaml(DROP_G1_YAML)
        names = {n["name"] for n in d.get("npcs", [])}
        self.assertIn("Doc Myrra", names,
                      "Doc Myrra must be present (FDtS Step 14 anchor)")


# ─────────────────────────────────────────────────────────────────────────────
# 9. FDtS Step 14 dialogue alignment
# ─────────────────────────────────────────────────────────────────────────────

class TestFDtSDialogueAlignment(unittest.TestCase):
    """The three Step-14 contact NPCs must have directed_responses
    keyed `sent_by_mak` containing the canonical Step-14 line per
    from_dust_to_stars_design_v2_clone_wars.md."""

    def test_zekka_has_sent_by_mak_response(self):
        d = _load_yaml(DROP_G1_YAML)
        zekka = next(n for n in d["npcs"] if n["name"] == "Zekka Thansen")
        dr = zekka.get("ai_config", {}).get("directed_responses", {})
        self.assertIn("sent_by_mak", dr,
                      "Zekka should have a sent_by_mak directed response")
        # Canonical Step 14 line includes the phrase "Mak Torvin sent you"
        text = " ".join(dr["sent_by_mak"])
        self.assertIn("Mak Torvin", text,
                      "Zekka's sent_by_mak should reference Mak Torvin")

    def test_renna_has_sent_by_mak_response(self):
        d = _load_yaml(DROP_G1_YAML)
        renna = next(n for n in d["npcs"] if n["name"] == "Renna Dox")
        dr = renna.get("ai_config", {}).get("directed_responses", {})
        self.assertIn("sent_by_mak", dr)
        text = " ".join(dr["sent_by_mak"])
        # Canonical Step 14 phrase: "his hull patch is ready"
        self.assertIn("hull patch", text,
                      "Renna's sent_by_mak should mention the hull patch")

    def test_doc_myrra_has_sent_by_mak_response(self):
        d = _load_yaml(DROP_G1_YAML)
        myrra = next(n for n in d["npcs"] if n["name"] == "Doc Myrra")
        dr = myrra.get("ai_config", {}).get("directed_responses", {})
        self.assertIn("sent_by_mak", dr)
        text = " ".join(dr["sent_by_mak"])
        # Canonical Step 14 phrase: "any friend of Mak's"
        self.assertIn("friend of Mak", text,
                      "Doc Myrra's sent_by_mak should include 'friend of Mak'")

    def test_mak_has_briefing_response(self):
        """Mak Torvin must have the Step 14 contacts-briefing line for
        when the FDtS engine routes the comlink message to him."""
        d = _load_yaml(DROP_G1_YAML)
        mak = next(n for n in d["npcs"] if n["name"] == "Mak Torvin")
        dr = mak.get("ai_config", {}).get("directed_responses", {})
        self.assertIn("contacts_briefing", dr)
        text = " ".join(dr["contacts_briefing"])
        # Step 14 briefing names all three contacts
        for contact in ("Zekka Thansen", "Renna Dox", "Doc Myrra"):
            self.assertIn(contact, text,
                          f"Mak's briefing should name {contact}")


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
        d = _load_yaml(DROP_G1_YAML)
        violations = []
        for n in d.get("npcs", []):
            ai = n.get("ai_config", {})
            for field in self.AI_CONFIG_REQUIRED:
                if field not in ai:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"AI config schema: {violations}")

    def test_char_sheet_canonical_fields(self):
        d = _load_yaml(DROP_G1_YAML)
        violations = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {})
            for field in self.CHAR_SHEET_REQUIRED:
                if field not in cs:
                    violations.append((n["name"], field))
        self.assertEqual(violations, [], f"Char sheet schema: {violations}")

    def test_fallback_lines_nonempty(self):
        d = _load_yaml(DROP_G1_YAML)
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
        d = _load_yaml(DROP_G1_YAML)
        violations = []
        for n in d.get("npcs", []):
            attrs = n.get("char_sheet", {}).get("attributes", {})
            for stat, val in attrs.items():
                if not DCODE.match(str(val)):
                    violations.append((n["name"], stat, val))
        self.assertEqual(violations, [], f"Bad D-codes: {violations}")

    def test_dsp_constraints(self):
        """Drop G1 shouldn't have DSP > 1 — corruption-coded NPCs (the
        spice broker, the bookers) handle that, and no Drop G1 NPCs
        explicitly have DSP > 0. If something accidentally has high
        DSP it's probably an authoring slip."""
        d = _load_yaml(DROP_G1_YAML)
        violations = []
        for n in d.get("npcs", []):
            dsp = n.get("char_sheet", {}).get("dark_side_points", 0)
            if dsp > 1:
                violations.append((n["name"], dsp))
        self.assertEqual(violations, [], f"DSP > 1: {violations}")

    def test_trandoshans_have_correct_move(self):
        """Trandoshans canonically have move 11 (faster than human)."""
        d = _load_yaml(DROP_G1_YAML)
        bad = []
        for n in d.get("npcs", []):
            if n.get("species") == "Trandoshan":
                move = n.get("char_sheet", {}).get("move")
                if move != 11:
                    bad.append((n["name"], move))
        self.assertEqual(bad, [], f"Trandoshans without move 11: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. Species diversity
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeciesDiversity(unittest.TestCase):
    """The Smuggler's Moon should be cosmopolitan."""

    def test_at_least_six_species(self):
        d = _load_yaml(DROP_G1_YAML)
        species = set(n.get("species") for n in d.get("npcs", []))
        self.assertGreaterEqual(
            len(species), 6,
            f"Nar Shaddaa should have ≥6 species; got {sorted(species)}"
        )

    def test_no_species_dominates(self):
        """Even Humans shouldn't be more than 65% of the roster."""
        d = _load_yaml(DROP_G1_YAML)
        npcs = d.get("npcs", [])
        from collections import Counter
        species = Counter(n.get("species") for n in npcs)
        most_common = species.most_common(1)[0]
        ratio = most_common[1] / max(len(npcs), 1)
        self.assertLess(
            ratio, 0.7,
            f"{most_common[0]} dominates ({ratio:.0%}); roster should be more diverse"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 13. Source-level marker
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):

    def test_yaml_self_documents(self):
        with open(DROP_G1_YAML, "r", encoding="utf-8") as f:
            src = f.read()
        for marker in ("Drop G1", "Nar Shaddaa", "Q1", "FDtS",
                       "Mak Torvin", "Zekka", "Renna", "Doc Myrra"):
            self.assertIn(marker, src,
                          f"YAML header should mention {marker!r}")


if __name__ == "__main__":
    unittest.main()
