# -*- coding: utf-8 -*-
"""
tests/test_drop_c1_coruscant.py — Drop C1 Coruscant Senate + Jedi Temple roster.

Drop C1 (May 2026) is the first of two Coruscant roster drops per
`cw_content_gap_design_v1_1_decisions.md` Stage 4. C1 covers the
Senate District + Jedi Temple slice (~half of Coruscant); C2 will
cover Coco Town + Underworld in a future drop. Combined, C1+C2
will populate Coruscant at the Q6 hangout-planet density target
of ~1.4 NPCs/room.

Per architecture v39 §3.2 priority #1 (CW.NPCS track), Drop C1 is
content-only — no engine changes, no DB schema changes, no command
additions. The roster file is wired into CW `era.yaml` via
`content_refs.npcs`.

Test sections:
  1. TestRosterFile                 — file exists, YAML parses, right shape
  2. TestRequiredFieldsPresent      — every NPC has the canonical schema
  3. TestRoomReferencesResolve      — every room is a real Coruscant room
  4. TestFactionCodes               — every faction is a valid CW org code
  5. TestQ1CanonicalCharacterPolicy — no canonical Council members
                                       or Senators present (the
                                       EXTREMELY RESTRICTED rule)
  6. TestEraConsistency             — backstories consistent with
                                       mid-war ~20 BBY (Q2)
  7. TestEraManifestRef             — npcs_drop_c1_coruscant.yaml is in era.yaml
  8. TestSenateAndTempleCoverage    — both districts covered
  9. TestSchemaMatchesVelaNireeReference — fields conform
 10. TestStatBlockSanity            — Force-sensitives have FP, etc.
 11. TestDocstringMarker            — source-level guard
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
DROP_C1_YAML = os.path.join(CW_DIR, "npcs_drop_c1_coruscant.yaml")


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


def _coruscant_room_names():
    d = _load_yaml(os.path.join(CW_DIR, "planets", "coruscant.yaml")) or {}
    return {r["name"] for r in (d.get("rooms") or []) if isinstance(r, dict) and r.get("name")}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Roster file present + well-formed
# ─────────────────────────────────────────────────────────────────────────────

class TestRosterFile(unittest.TestCase):

    def test_file_exists(self):
        self.assertTrue(os.path.exists(DROP_C1_YAML),
                        f"Drop C1 roster missing at {DROP_C1_YAML}")

    def test_yaml_parses(self):
        d = _load_yaml(DROP_C1_YAML)
        self.assertIsInstance(d, dict)
        self.assertEqual(d.get("schema_version"), 1)

    def test_npc_count_in_target_range(self):
        """Drop C1 target is ~25 NPCs (per Stage 4 plan)."""
        d = _load_yaml(DROP_C1_YAML)
        npcs = d.get("npcs", [])
        self.assertGreaterEqual(len(npcs), 20,
                                f"Drop C1 should have ~25 NPCs (got {len(npcs)})")
        self.assertLessEqual(len(npcs), 30,
                             f"Drop C1 over scope (got {len(npcs)})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Each NPC has canonical schema
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldsPresent(unittest.TestCase):

    REQUIRED = ("name", "room", "species", "description", "char_sheet", "ai_config")

    def test_all_npcs_have_required_fields(self):
        d = _load_yaml(DROP_C1_YAML)
        missing = []
        for i, n in enumerate(d.get("npcs", [])):
            for field in self.REQUIRED:
                if field not in n:
                    missing.append((n.get("name", f"#{i}"), field))
        self.assertEqual(missing, [],
                         f"NPCs missing required fields: {missing}")

    def test_names_unique(self):
        d = _load_yaml(DROP_C1_YAML)
        names = [n["name"] for n in d.get("npcs", [])]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicate NPC names: {sorted(names)}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Room references resolve
# ─────────────────────────────────────────────────────────────────────────────

class TestRoomReferencesResolve(unittest.TestCase):

    def test_all_rooms_exist_in_cw_world(self):
        d = _load_yaml(DROP_C1_YAML)
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

    def test_all_rooms_are_on_coruscant(self):
        """C1 NPCs should all be on Coruscant (Senate District or Jedi Temple)."""
        d = _load_yaml(DROP_C1_YAML)
        coruscant_rooms = _coruscant_room_names()
        off_planet = []
        for n in d.get("npcs", []):
            if n["room"] not in coruscant_rooms:
                off_planet.append((n["name"], n["room"]))
        self.assertEqual(off_planet, [],
                         f"C1 NPCs not on Coruscant: {off_planet}")


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
        d = _load_yaml(DROP_C1_YAML)
        bad = []
        for n in d.get("npcs", []):
            fac = n.get("ai_config", {}).get("faction", "")
            if fac and fac not in self.VALID_CODES:
                bad.append((n["name"], fac))
        self.assertEqual(bad, [],
                         f"Non-canonical faction codes: {bad}")

    def test_jedi_temple_npcs_are_jedi_order_faction(self):
        """All Jedi Temple NPCs (incl. civilian Order staff) use jedi_order."""
        d = _load_yaml(DROP_C1_YAML)
        bad = []
        for n in d.get("npcs", []):
            if n["room"].startswith("Jedi Temple"):
                fac = n.get("ai_config", {}).get("faction")
                if fac != "jedi_order":
                    bad.append((n["name"], fac))
        self.assertEqual(bad, [],
                         f"Jedi Temple NPCs not flagged jedi_order: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Q1 — No canonical Council members or Senators (EXTREMELY RESTRICTED)
# ─────────────────────────────────────────────────────────────────────────────

class TestQ1CanonicalCharacterPolicy(unittest.TestCase):
    """Per cw_content_gap_design_v1_1_decisions.md Q1: canonical Jedi Council
    members and canonical Senators NEVER appear as Ollama-driven open-world
    NPCs. They may appear in scripted-only quest-instanced contexts only.

    The list below is the canonical names that must NOT appear as
    NPC names in this open-world roster file.
    """

    CANONICAL_JEDI_FORBIDDEN = {
        # Council members across the war
        "Yoda", "Mace Windu", "Obi-Wan Kenobi", "Anakin Skywalker",
        "Plo Koon", "Ki-Adi-Mundi", "Kit Fisto", "Shaak Ti",
        "Saesee Tiin", "Agen Kolar", "Eeth Koth", "Oppo Rancisis",
        "Even Piell", "Coleman Trebor", "Coleman Kcaj",
        "Stass Allie", "Adi Gallia", "Depa Billaba",
        # Other notable canonical Jedi
        "Aayla Secura", "Luminara Unduli", "Barriss Offee",
        "Quinlan Vos", "Mace", "Yarael Poof", "Pong Krell",
        "Ahsoka Tano", "Asajj Ventress", "Dooku", "Count Dooku",
        # Other Council canonical figures around the war
        "Jocasta Nu",
    }

    CANONICAL_SENATORS_FORBIDDEN = {
        "Padmé Amidala", "Padme Amidala", "Bail Organa",
        "Mon Mothma", "Mina Bonteri", "Onaconda Farr",
        "Riyo Chuchi", "Lott Dod", "Orn Free Taa",
        "Halle Burtoni", "Aang", "Voe Atell",
        "Rush Clovis", "Cham Syndulla", "Mas Amedda",
        "Sheev Palpatine", "Palpatine",
        # Other canonical CW political figures
        "Satine Kryze", "Pre Vizsla",
    }

    OTHER_CANONICAL_FORBIDDEN = {
        # Bounty hunters etc that might tempt cameos
        "Cad Bane", "Hondo Ohnaka", "Boba Fett",
        # Clone canonical heroes that are reserved for quest content
        "Captain Rex", "Commander Cody", "Commander Wolffe",
        "Commander Fox", "Hunter", "Echo", "Fives", "Jesse",
        # Maintenance / training canonical clones
        "99", "Maintenance Clone 99",
    }

    @property
    def all_forbidden(self):
        return (self.CANONICAL_JEDI_FORBIDDEN
                | self.CANONICAL_SENATORS_FORBIDDEN
                | self.OTHER_CANONICAL_FORBIDDEN)

    def test_no_canonical_named_npcs(self):
        """No NPC.name should be a canonical-figure name."""
        d = _load_yaml(DROP_C1_YAML)
        violations = []
        for n in d.get("npcs", []):
            name = n["name"]
            for forbidden in self.all_forbidden:
                # Match as whole-word substring (e.g. "Yoda" must not appear
                # but "Yodalin" would be allowed — none of these appear in
                # practice but the test guards against accidental inclusion).
                if re.search(r"\b" + re.escape(forbidden) + r"\b", name):
                    violations.append((name, forbidden))
        self.assertEqual(
            violations, [],
            f"Q1 policy violation — canonical character cameos in roster:\n"
            f"  {violations}\n"
            f"Per cw_content_gap_design_v1_1_decisions.md Q1, canonical "
            f"figures may only appear in scripted-only quest-instanced "
            f"contexts, never as Ollama-driven open-world NPCs."
        )

    def test_no_canonical_in_descriptions_misleading(self):
        """Descriptions referencing canonical figures must frame them as
        absent / off-screen / out-of-fiction (not as if they're present).
        Heuristic: a description that includes 'Anakin' or 'Yoda' etc.
        should also include 'not here', 'absent', 'off-world', 'in the
        field', 'currently', 'last week', etc. — phrasing that makes
        clear the figure is NOT in scene."""
        d = _load_yaml(DROP_C1_YAML)
        # Names that, if mentioned, must be framed as not-present
        framed = {"Anakin", "Obi-Wan", "Mace", "Yoda", "Padmé", "Padme",
                  "Bail", "Mothma", "Palpatine", "Dooku"}
        absence_markers = (
            "not here", "absent", "off-world", "in the field",
            "deployed", "rarely", "doesn't comment", "won't comment",
            "won't share", "not at the front", "off the floor",
            "doesn't make it", "not down to the floor", "at the front",
            "currently", "last", "doesn't",
        )
        violations = []
        for n in d.get("npcs", []):
            text = (n.get("description", "") + " "
                    + str(n.get("ai_config", {}).get("personality", ""))
                    + " " + str(n.get("ai_config", {}).get("knowledge", "")))
            for fname in framed:
                if fname.lower() in text.lower():
                    if not any(m.lower() in text.lower() for m in absence_markers):
                        violations.append((n["name"], fname))
        self.assertEqual(
            violations, [],
            f"NPCs mention canonical figures without absence framing:\n"
            f"  {violations}\n"
            f"Q1 requires canonical-figure mentions in open-world NPC "
            f"text to be framed as absent/off-screen, not as if the "
            f"figure is present in the room."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Q2 — era consistency (mid-war ~20 BBY)
# ─────────────────────────────────────────────────────────────────────────────

class TestEraConsistency(unittest.TestCase):
    """Mid-war ~20 BBY is the locked era. NPCs must not reference
    post-Order-66 events or pre-Geonosis-only context. Ahsoka left
    the Order at ~20 BBY but the date is ambiguous; we don't test
    on her name alone."""

    POST_ORDER_66_LEAKS = (
        "Empire", "Imperial Senate", "Stormtrooper", "Imperial",
        "Galactic Empire", "Vader", "Darth Vader", "Sith Lord",
        "after the war", "post-war", "Imperial occupation",
        "Imperial garrison", "Imperial Star Destroyer",
        "Tarkin", "Krennic", "Rebellion", "Rebel Alliance",
    )

    PRE_WAR_LEAKS = (
        "Battle of Naboo about to begin",
        "Phantom Menace",
    )

    def test_no_post_order_66_references(self):
        d = _load_yaml(DROP_C1_YAML)
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
                    # Allow "Imperial" only if framed historically
                    # (e.g. "Imperial Customs" was Drop A's previous
                    # GG7 wording). Drop C1 has no Drop A NPCs so any
                    # match is a violation.
                    violations.append((n["name"], leak))
        self.assertEqual(
            violations, [],
            f"NPCs leak post-Order-66 era language:\n  {violations}"
        )

    def test_war_acknowledged_in_some_npcs(self):
        """At least 30% of NPCs should reference the war / mid-war state."""
        d = _load_yaml(DROP_C1_YAML)
        npcs = d.get("npcs", [])
        war_markers = (
            "war", "deployed", "the front", "Outer Rim",
            "Geonosis", "Christophsis", "campaign", "Jabiim",
            "clone trooper", "Republic Navy", "the Council",
            "battle", "casualty", "casualties", "Padawan", "deployment",
        )
        with_war_ref = 0
        for n in npcs:
            text = " ".join([
                n.get("description", ""),
                str(n.get("ai_config", {}).get("personality", "")),
                " ".join(n.get("ai_config", {}).get("knowledge", []) or []),
            ])
            if any(m.lower() in text.lower() for m in war_markers):
                with_war_ref += 1
        ratio = with_war_ref / max(len(npcs), 1)
        self.assertGreaterEqual(
            ratio, 0.3,
            f"Only {ratio:.0%} of C1 NPCs reference the war "
            f"(target: ≥30% per Q2 mid-war framing)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. era.yaml references the new file
# ─────────────────────────────────────────────────────────────────────────────

class TestEraManifestRef(unittest.TestCase):

    def test_era_yaml_includes_drop_c1(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        self.assertIn(
            "npcs_drop_c1_coruscant.yaml", npcs_refs,
            "CW era.yaml content_refs.npcs must include "
            "npcs_drop_c1_coruscant.yaml"
        )

    def test_pre_existing_npc_files_still_referenced(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        npcs_refs = era.get("content_refs", {}).get("npcs", []) or []
        for f in ("npcs_cw_additions.yaml", "npcs_cw_replacements.yaml",
                  "npcs_drop_h_combat.yaml"):
            self.assertIn(f, npcs_refs,
                          f"Pre-existing ref {f!r} dropped from era.yaml")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Senate + Temple coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestSenateAndTempleCoverage(unittest.TestCase):

    def test_senate_district_covered(self):
        d = _load_yaml(DROP_C1_YAML)
        senate_npcs = [n for n in d.get("npcs", [])
                       if "Senate" in n["room"]
                       or "Chancellor" in n["room"]
                       or "Legislative" in n["room"]
                       or "Senatorial" in n["room"]
                       or "Monument" in n["room"]
                       or "Grand Reception" in n["room"]]
        self.assertGreaterEqual(
            len(senate_npcs), 8,
            f"Senate district NPC count too low: {len(senate_npcs)}"
        )

    def test_jedi_temple_covered(self):
        d = _load_yaml(DROP_C1_YAML)
        temple_npcs = [n for n in d.get("npcs", [])
                       if n["room"].startswith("Jedi Temple")]
        self.assertGreaterEqual(
            len(temple_npcs), 8,
            f"Jedi Temple NPC count too low: {len(temple_npcs)}"
        )

    def test_temple_has_a_padawan(self):
        """Temple should feel alive with younger Jedi too."""
        d = _load_yaml(DROP_C1_YAML)
        padawans = [n for n in d.get("npcs", [])
                    if "Padawan" in n["name"]
                    and n["room"].startswith("Jedi Temple")]
        self.assertGreaterEqual(len(padawans), 1)

    def test_temple_has_a_master(self):
        d = _load_yaml(DROP_C1_YAML)
        masters = [n for n in d.get("npcs", [])
                   if "Master" in n["name"]
                   and n["room"].startswith("Jedi Temple")]
        self.assertGreaterEqual(len(masters), 2,
                                "Temple should have ≥2 Masters (battle, healer, etc.)")


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
        d = _load_yaml(DROP_C1_YAML)
        violations = []
        for n in d.get("npcs", []):
            ai = n.get("ai_config", {})
            for field in self.AI_CONFIG_REQUIRED:
                if field not in ai:
                    violations.append((n["name"], f"ai_config.{field}"))
        self.assertEqual(violations, [],
                         f"AI config schema violations: {violations}")

    def test_char_sheet_canonical_fields(self):
        d = _load_yaml(DROP_C1_YAML)
        violations = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {})
            for field in self.CHAR_SHEET_REQUIRED:
                if field not in cs:
                    violations.append((n["name"], f"char_sheet.{field}"))
        self.assertEqual(violations, [],
                         f"Char sheet schema violations: {violations}")

    def test_fallback_lines_nonempty(self):
        d = _load_yaml(DROP_C1_YAML)
        bad = []
        for n in d.get("npcs", []):
            lines = n.get("ai_config", {}).get("fallback_lines", [])
            if not lines or len(lines) < 3:
                bad.append((n["name"], len(lines)))
        self.assertEqual(bad, [],
                         f"NPCs with <3 fallback lines: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Stat-block sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestStatBlockSanity(unittest.TestCase):

    def test_jedi_have_force_points(self):
        """Force-sensitive Jedi NPCs (Knights, Masters, Padawans, Temple
        Guard) should have ≥1 Force Point. Order-affiliated civilians
        (Hangar Tech, Quartermaster, Crèche Caretaker, Recording Clerk)
        may have 0 or low FP."""
        d = _load_yaml(DROP_C1_YAML)
        violations = []
        force_titles = ("Knight", "Master", "Padawan", "Temple Guard",
                        "Battle Master")
        civilian_titles = ("Hangar Tech", "Quartermaster",
                           "Crèche Caretaker", "Recording Clerk")
        for n in d.get("npcs", []):
            name = n["name"]
            if not n["room"].startswith("Jedi Temple"):
                continue
            is_force_user = any(t in name for t in force_titles)
            is_civilian = any(t in name for t in civilian_titles)
            if is_force_user and not is_civilian:
                fp = n.get("char_sheet", {}).get("force_points", 0)
                if fp < 1:
                    violations.append((name, fp))
        self.assertEqual(violations, [],
                         f"Force-sensitive Jedi without FP: {violations}")

    def test_attribute_codes_look_like_d_codes(self):
        DCODE = re.compile(r"^\d+D(\+[12])?$")
        d = _load_yaml(DROP_C1_YAML)
        violations = []
        for n in d.get("npcs", []):
            attrs = n.get("char_sheet", {}).get("attributes", {})
            for stat, val in attrs.items():
                if not DCODE.match(str(val)):
                    violations.append((n["name"], stat, val))
        self.assertEqual(violations, [],
                         f"Attributes don't match WEG D-code: {violations}")

    def test_dark_side_points_zero_or_one_only(self):
        """C1 NPCs should mostly be DSP=0; the lobbyist intentionally has
        DSP=1 (corrupt). Anyone with DSP>1 is a flag."""
        d = _load_yaml(DROP_C1_YAML)
        violations = []
        for n in d.get("npcs", []):
            dsp = n.get("char_sheet", {}).get("dark_side_points", 0)
            if dsp > 1:
                violations.append((n["name"], dsp))
        self.assertEqual(violations, [],
                         f"NPCs with DSP > 1 in C1 roster: {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. Source-level marker
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):

    def test_yaml_self_documents(self):
        with open(DROP_C1_YAML, "r", encoding="utf-8") as f:
            src = f.read()
        for marker in ("Drop C1", "cw_content_gap", "Senate", "Jedi Temple",
                       "Q1", "EXTREMELY RESTRICTED"):
            self.assertIn(marker, src,
                          f"Drop C1 YAML header should mention {marker!r}")


if __name__ == "__main__":
    unittest.main()
