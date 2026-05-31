# -*- coding: utf-8 -*-
"""
tests/test_drop_f8c2a_chain_anchors.py — F.8.c.2.a chain anchor NPCs.

F.8.c.2.a (May 4 2026) is the content prerequisite for F.8.c.2.b
(event-hook wiring) and F.8.c.2.c (graduation teleport). Per the
F.8.c.1 handoff §"Does NOT" list and ROADMAP_RECONCILIATION_MAY04.md.

The seven unlocked CW tutorial chains in
`data/worlds/clone_wars/tutorials/chains.yaml` reference 20 distinct
NPCs by name in their `step.npc` and `step.completion.npc` fields.
None of these NPCs existed at HEAD before this drop. Without them,
chain steps that gate on `talk_to_npc` completion type would never
fire — the engine would search the room for an NPC named (e.g.)
'Major Tarrn' and find nothing.

This drop authors the 20 NPCs as a single roster file
(`npcs_drop_f8c2a_chain_anchors.yaml`), wired into the era manifest
(`era.yaml::content_refs.npcs`), and validated by this test file.

Test sections:
  1. TestRosterFile                       — file exists, YAML parses
  2. TestRequiredFieldsPresent            — schema conformance
  3. TestChainNPCCoverage                 — every chain NPC ref resolves
  4. TestRoomReferencesResolve            — anchor rooms exist
  5. TestFactionCodes                     — valid CW faction codes
  6. TestQ1CanonicalCharacterPolicy       — no canonical figures as
                                            NPC names; off-screen
                                            mentions have absence framing
  7. TestEraConsistency                   — no post-Order-66 leakage
  8. TestEraManifestRef                   — wired into era.yaml
  9. TestNoCollisionsWithOtherDrops       — no name dup with prior CW drops
 10. TestStatBlockSanity                  — all dice strings parse;
                                            all char_sheet fields present
 11. TestSpeciesDiversity                 — non-trivial species spread
 12. TestChainAnchorRoomMatch             — each NPC's room matches the
                                            chain step's `location` slug
                                            via the slug→name index
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
DROP_YAML = os.path.join(CW_DIR, "npcs_drop_f8c2a_chain_anchors.yaml")
ERA_YAML = os.path.join(CW_DIR, "era.yaml")
CHAINS_YAML = os.path.join(CW_DIR, "tutorials", "chains.yaml")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_cw_rooms():
    """Map of slug → display name across all known CW room sources
    (planets + tutorials/rooms.yaml). Wilderness landmarks are NOT
    included here because no chain anchor NPC in F.8.c.2.a anchors at
    a wilderness landmark; if a future drop adds one, this helper
    will need to grow."""
    out = {}  # slug → name
    for fp in sorted(_iter_room_yamls()):
        d = _load_yaml(fp) or {}
        if not isinstance(d, dict):
            continue
        for r in (d.get("rooms") or []):
            if isinstance(r, dict) and r.get("slug") and r.get("name"):
                out[r["slug"]] = r["name"]
    return out


def _iter_room_yamls():
    planets_dir = os.path.join(CW_DIR, "planets")
    if os.path.isdir(planets_dir):
        for f in sorted(os.listdir(planets_dir)):
            if f.endswith(".yaml"):
                yield os.path.join(planets_dir, f)
    tut_rooms = os.path.join(CW_DIR, "tutorials", "rooms.yaml")
    if os.path.exists(tut_rooms):
        yield tut_rooms


def _all_cw_room_names():
    """All known CW room display names."""
    return set(_all_cw_rooms().values())


def _chain_npcs():
    """Map of NPC name → set of (chain_id, anchor_slug) pairs from
    the unlocked tutorial chains."""
    out = {}
    chains = _load_yaml(CHAINS_YAML)
    for c in chains.get("chains", []):
        if c.get("locked"):
            continue
        cid = c.get("chain_id", "?")
        for step in c.get("steps") or []:
            loc = step.get("location")
            for key in ("npc",):
                npc = step.get(key)
                if npc and npc != "(none)" and loc:
                    out.setdefault(npc, set()).add((cid, loc))
            comp = step.get("completion") or {}
            if isinstance(comp, dict):
                npc = comp.get("npc")
                if npc and npc != "(none)" and loc:
                    out.setdefault(npc, set()).add((cid, loc))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 1. Roster file
# ─────────────────────────────────────────────────────────────────────────────

class TestRosterFile(unittest.TestCase):

    def test_file_exists(self):
        self.assertTrue(os.path.exists(DROP_YAML),
                        f"F.8.c.2.a roster file missing: {DROP_YAML}")

    def test_yaml_parses(self):
        d = _load_yaml(DROP_YAML)
        self.assertIsInstance(d, dict)
        self.assertEqual(d.get("schema_version"), 1)

    def test_npc_count_is_20(self):
        """F.8.c.2.a target is exactly 20 — one per distinct chain
        NPC reference. If this number changes, either the chains
        added/removed an NPC reference (update this test) or the
        roster is out of sync (fix the roster)."""
        d = _load_yaml(DROP_YAML)
        npcs = d.get("npcs", [])
        self.assertEqual(len(npcs), 20,
                         f"F.8.c.2.a expects 20 NPCs (got {len(npcs)})")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Required fields
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldsPresent(unittest.TestCase):

    REQUIRED = ("name", "room", "species", "description",
                "char_sheet", "ai_config")
    REQUIRED_CHARSHEET = ("attributes", "skills", "weapon", "move",
                          "force_points", "character_points",
                          "dark_side_points")
    REQUIRED_ATTRS = ("dexterity", "knowledge", "mechanical",
                      "perception", "strength", "technical")
    REQUIRED_AICONFIG = ("personality", "knowledge", "faction",
                         "dialogue_style", "hostile",
                         "combat_behavior", "fallback_lines")

    def test_all_npcs_have_required_top_fields(self):
        d = _load_yaml(DROP_YAML)
        missing = []
        for i, n in enumerate(d.get("npcs", [])):
            for field in self.REQUIRED:
                if field not in n:
                    missing.append((n.get("name", f"#{i}"), field))
        self.assertEqual(missing, [],
                         f"Missing top-level fields: {missing}")

    def test_all_npcs_have_required_charsheet_fields(self):
        d = _load_yaml(DROP_YAML)
        missing = []
        for n in d.get("npcs", []):
            cs = n.get("char_sheet", {}) or {}
            for f in self.REQUIRED_CHARSHEET:
                if f not in cs:
                    missing.append((n["name"], f))
        self.assertEqual(missing, [],
                         f"Missing char_sheet fields: {missing}")

    def test_all_attrs_present(self):
        d = _load_yaml(DROP_YAML)
        missing = []
        for n in d.get("npcs", []):
            attrs = (n.get("char_sheet", {}) or {}).get("attributes", {}) or {}
            for f in self.REQUIRED_ATTRS:
                if f not in attrs:
                    missing.append((n["name"], f))
        self.assertEqual(missing, [],
                         f"Missing attribute fields: {missing}")

    def test_all_aiconfig_fields_present(self):
        d = _load_yaml(DROP_YAML)
        missing = []
        for n in d.get("npcs", []):
            ai = n.get("ai_config", {}) or {}
            for f in self.REQUIRED_AICONFIG:
                if f not in ai:
                    missing.append((n["name"], f))
        self.assertEqual(missing, [],
                         f"Missing ai_config fields: {missing}")

    def test_names_unique(self):
        d = _load_yaml(DROP_YAML)
        names = [n["name"] for n in d.get("npcs", [])]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicate names: {sorted(names)}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Chain NPC coverage — the load-bearing test for F.8.c.2.a
# ─────────────────────────────────────────────────────────────────────────────

class TestChainNPCCoverage(unittest.TestCase):
    """Every NPC referenced by an unlocked chain step must exist in
    this roster. F.8.c.2.b's event-hook wiring will fail at runtime
    for any step whose NPC is missing; this test catches that
    statically."""

    def test_every_chain_npc_is_authored(self):
        chain_npcs = _chain_npcs()
        d = _load_yaml(DROP_YAML)
        authored = {n["name"] for n in d.get("npcs", [])}
        missing = sorted(set(chain_npcs) - authored)
        self.assertEqual(missing, [],
            f"Chain steps reference NPCs that don't exist in this roster: "
            f"{missing}. Either add them to F.8.c.2.a or update the chain.")

    def test_no_extra_npcs(self):
        """Conversely: the roster shouldn't carry NPCs that no chain
        step references. Future content drops may legitimately add
        atmospheric NPCs that aren't chain anchors — those belong in
        a different roster file (npcs_drop_*.yaml). This roster's
        identity is "the chain anchors and only the chain anchors."""
        chain_npcs = _chain_npcs()
        d = _load_yaml(DROP_YAML)
        authored = {n["name"] for n in d.get("npcs", [])}
        extras = sorted(authored - set(chain_npcs))
        self.assertEqual(extras, [],
            f"Roster contains NPCs that aren't referenced by any chain "
            f"step: {extras}. Move atmospheric NPCs to a different roster.")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Room references
# ─────────────────────────────────────────────────────────────────────────────

class TestRoomReferencesResolve(unittest.TestCase):

    def test_all_rooms_exist_in_cw_world(self):
        d = _load_yaml(DROP_YAML)
        cw_room_names = _all_cw_room_names()
        unresolved = [(n["name"], n["room"]) for n in d.get("npcs", [])
                      if n["room"] not in cw_room_names]
        self.assertEqual(unresolved, [],
                         f"Unresolved rooms: {unresolved}")


class TestChainAnchorRoomMatch(unittest.TestCase):
    """Each NPC's `room:` field must match the display name of at
    least one of the chain step `location` slugs that reference that
    NPC. Catches the bug where the NPC is authored in the right
    physical room but the wrong narrative room (e.g. authored at
    'Tipoca City - Briefing Room' but the chain step expects
    'Coruscant Works - Landing Zone')."""

    def test_npc_room_matches_chain_anchor_slug(self):
        d = _load_yaml(DROP_YAML)
        chain_npcs = _chain_npcs()
        slug_to_name = _all_cw_rooms()

        mismatches = []
        for n in d.get("npcs", []):
            nm = n["name"]
            room = n["room"]
            anchors = chain_npcs.get(nm, set())
            if not anchors:
                continue  # Covered by TestChainNPCCoverage
            anchor_names = set()
            for cid, slug in anchors:
                if slug in slug_to_name:
                    anchor_names.add(slug_to_name[slug])
            if anchor_names and room not in anchor_names:
                mismatches.append((nm, room, sorted(anchor_names)))

        self.assertEqual(mismatches, [],
            f"NPCs anchored at the wrong room (NPC name, NPC's room, "
            f"chain-expected rooms):\n  " +
            "\n  ".join(repr(m) for m in mismatches))


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
        d = _load_yaml(DROP_YAML)
        bad = [(n["name"], n["ai_config"]["faction"])
               for n in d.get("npcs", [])
               if n["ai_config"].get("faction")
               and n["ai_config"]["faction"] not in self.VALID_CODES]
        self.assertEqual(bad, [], f"Bad factions: {bad}")

    def test_clone_anchors_are_republic(self):
        """Clone NPCs (CT-prefix designation) must be Republic-faction."""
        d = _load_yaml(DROP_YAML)
        bad = []
        for n in d.get("npcs", []):
            if "CT-" in n["name"]:
                fac = n["ai_config"].get("faction")
                if fac != "republic":
                    bad.append((n["name"], fac))
        self.assertEqual(bad, [], f"Clone NPCs not Republic-faction: {bad}")

    def test_droid_anchors_are_cis(self):
        """Tactical Droid TQ-89 and Squad-Lead B2-7745 are CIS units."""
        d = _load_yaml(DROP_YAML)
        bad = []
        for n in d.get("npcs", []):
            if any(k in n["name"] for k in ("Tactical Droid", "Squad-Lead B2")):
                fac = n["ai_config"].get("faction")
                if fac != "cis":
                    bad.append((n["name"], fac))
        self.assertEqual(bad, [], f"Droid NPCs not CIS-faction: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Q1 canonical-character policy
# ─────────────────────────────────────────────────────────────────────────────

class TestQ1CanonicalCharacterPolicy(unittest.TestCase):
    """Per Q1, NPCs must not duplicate canonical Star Wars figures.
    Off-screen mentions are allowed only with absence framing — the
    canon figure must be clearly described as not present."""

    CANONICAL_FORBIDDEN = {
        # CW-canonical Jedi
        "Yoda", "Mace Windu", "Anakin Skywalker", "Obi-Wan Kenobi",
        "Qui-Gon Jinn", "Ahsoka", "Plo Koon",
        # CW-canonical Sith / CIS leadership
        "Count Dooku", "General Grievous", "Asajj Ventress",
        "Sidious", "Palpatine",
        # CW Republic political figures
        "Padmé Amidala", "Bail Organa", "Mon Mothma",
        # Canonical Hutts
        "Jabba", "Jabba Desilijic Tiure", "Bib Fortuna",
        "Salacious Crumb",
        # Canonical clone heroes — designations like CT-7567 are
        # generic patterns; the canon NAMES are the constraint
        "Captain Rex", "Commander Cody", "Captain Hunter",
        "Sergeant Echo", "Trooper Fives", "Trooper Jesse",
        # Canonical bounty hunters
        "Cad Bane", "Aurra Sing", "Boba Fett",
        "Hondo Ohnaka", "Bossk", "Dengar",
        # Post-war leakage
        "Vader", "Darth Vader", "Tarkin",
        "Galactic Empire", "Imperial Senate", "Rebel Alliance",
    }

    ABSENCE_MARKERS = (
        "off-screen", "off-stage", "off screen", "off stage",
        "off-world", "off world", "absent", "not here", "not present",
        "remains at", "stays at", "at his palace", "at the palace",
        "at the Dune Sea", "does not visit", "does not come",
        "behind him", "is not present", "next visit",
    )

    def test_no_canonical_named_npcs(self):
        d = _load_yaml(DROP_YAML)
        violations = []
        for n in d.get("npcs", []):
            for forbidden in self.CANONICAL_FORBIDDEN:
                if re.search(r"\b" + re.escape(forbidden) + r"\b",
                             n["name"]):
                    violations.append((n["name"], forbidden))
        self.assertEqual(violations, [],
                         f"Canonical figures in roster: {violations}")

    def test_canonical_mentions_have_absence_framing(self):
        """Where a canonical figure is mentioned in description /
        personality / knowledge, the surrounding text must use one of
        the ABSENCE_MARKERS to make clear they are not present."""
        d = _load_yaml(DROP_YAML)
        violations = []
        for n in d.get("npcs", []):
            text = (
                n.get("description", "") + " " +
                str(n.get("ai_config", {}).get("personality", "")) + " " +
                " ".join(n.get("ai_config", {}).get("knowledge", []) or [])
            )
            for forbidden in self.CANONICAL_FORBIDDEN:
                if re.search(r"\b" + re.escape(forbidden) + r"\b", text):
                    if not any(m.lower() in text.lower()
                               for m in self.ABSENCE_MARKERS):
                        violations.append((n["name"], forbidden))
        self.assertEqual(violations, [],
            f"Canonical mentions without absence framing: {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Era consistency — no post-Order-66 leakage
# ─────────────────────────────────────────────────────────────────────────────

class TestEraConsistency(unittest.TestCase):

    POST_ORDER_66_LEAKS = (
        "Galactic Empire", "Imperial Senate", "Imperial Stormtrooper",
        "Vader", "Darth Vader", "Tarkin",
        "Rebel Alliance", "Rebellion",
        "after the war", "post-war", "Imperial occupation",
        "the Empire",
    )

    def test_no_post_order_66_leakage(self):
        d = _load_yaml(DROP_YAML)
        violations = []
        for n in d.get("npcs", []):
            text = (
                n.get("description", "") + " " +
                str(n.get("ai_config", {}).get("personality", "")) + " " +
                " ".join(n.get("ai_config", {}).get("knowledge", []) or [])
            )
            for leak in self.POST_ORDER_66_LEAKS:
                if re.search(r"\b" + re.escape(leak) + r"\b",
                             text, re.IGNORECASE):
                    violations.append((n["name"], leak))
        self.assertEqual(violations, [],
            f"Post-Order-66 era leakage: {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Era manifest reference
# ─────────────────────────────────────────────────────────────────────────────

class TestEraManifestRef(unittest.TestCase):

    def test_drop_yaml_listed_in_era(self):
        era = _load_yaml(ERA_YAML)
        npc_files = (era.get("content_refs", {}) or {}).get("npcs", []) or []
        self.assertIn("npcs_drop_f8c2a_chain_anchors.yaml", npc_files,
            "F.8.c.2.a roster not registered in era.yaml::content_refs.npcs")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Collision check vs prior CW drops
# ─────────────────────────────────────────────────────────────────────────────

class TestNoCollisionsWithOtherDrops(unittest.TestCase):

    OTHER_NPC_FILES = (
        "npcs_cw_additions.yaml",
        "npcs_cw_replacements.yaml",
        "npcs_drop_h_combat.yaml",
        "npcs_drop_c1_coruscant.yaml",
        "npcs_drop_def_civilians.yaml",
        "npcs_drop_g1_nar_shaddaa_topside.yaml",
        "npcs_drop_g2_nar_shaddaa_lower.yaml",
        "npcs_drop_b_mos_eisley.yaml",
        "npcs_drop_c2_coruscant_lower.yaml",
    )

    def test_no_name_collision(self):
        my = _load_yaml(DROP_YAML)
        my_names = {n["name"] for n in my.get("npcs", [])}
        for f in self.OTHER_NPC_FILES:
            other_path = os.path.join(CW_DIR, f)
            if not os.path.exists(other_path):
                continue
            d = _load_yaml(other_path) or {}
            other_names = {n["name"] for n in d.get("npcs", [])}
            overlap = my_names & other_names
            self.assertEqual(overlap, set(),
                             f"Name collision with {f}: {overlap}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Stat-block sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestStatBlockSanity(unittest.TestCase):

    DICE_RE = re.compile(r"^\d+D(\+\d{1,2})?$")

    def test_all_attribute_dice_strings_parse(self):
        d = _load_yaml(DROP_YAML)
        bad = []
        for n in d.get("npcs", []):
            attrs = n["char_sheet"]["attributes"]
            for k, v in attrs.items():
                if not self.DICE_RE.match(str(v)):
                    bad.append((n["name"], k, v))
        self.assertEqual(bad, [],
            f"Attributes that don't match WEG D6 pattern: {bad}")

    def test_all_skill_dice_strings_parse(self):
        d = _load_yaml(DROP_YAML)
        bad = []
        for n in d.get("npcs", []):
            skills = n["char_sheet"].get("skills", {}) or {}
            for k, v in skills.items():
                if not self.DICE_RE.match(str(v)):
                    bad.append((n["name"], k, v))
        self.assertEqual(bad, [],
            f"Skills that don't match WEG D6 pattern: {bad}")

    def test_force_points_in_range(self):
        d = _load_yaml(DROP_YAML)
        bad = []
        for n in d.get("npcs", []):
            fp = n["char_sheet"].get("force_points", 0)
            if not isinstance(fp, int) or fp < 0 or fp > 5:
                bad.append((n["name"], fp))
        self.assertEqual(bad, [],
            f"Force points outside 0-5 range: {bad}")

    def test_dark_side_points_modest(self):
        """Anchor NPCs aren't supposed to be dark side practitioners.
        Sevra Toryn / Cell Leader Kavin / Tarko Vinn / Hutt Broker
        Vresh / Republic Security Officer Daln may have ≤1 DSP for
        moral-grey characterization. None should be ≥2."""
        d = _load_yaml(DROP_YAML)
        bad = []
        for n in d.get("npcs", []):
            dsp = n["char_sheet"].get("dark_side_points", 0)
            if not isinstance(dsp, int) or dsp < 0 or dsp > 1:
                bad.append((n["name"], dsp))
        self.assertEqual(bad, [],
            f"Dark side points outside 0-1 range for chain anchors: {bad}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. Species diversity
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeciesDiversity(unittest.TestCase):
    """The roster spans seven faction-flavoured chains. Avoid the
    failure mode where every NPC is a Human, which would flatten the
    universe."""

    def test_at_least_three_species(self):
        d = _load_yaml(DROP_YAML)
        species = {n["species"] for n in d.get("npcs", [])}
        self.assertGreaterEqual(len(species), 3,
            f"Roster is too monocultural — only {len(species)} "
            f"species: {species}. Aim for variety appropriate to the "
            f"chain's faction (Mirialan in Republic Intel, Twi'lek/"
            f"Bothan in underworld, Hutt in cartel, Zabrak/Sullustan "
            f"in independent).")


# ─────────────────────────────────────────────────────────────────────────────
# 12. Docstring marker — drop traceability
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):
    """The roster file's leading comments should identify the drop
    so future grep can find it."""

    def test_yaml_header_mentions_drop(self):
        with open(DROP_YAML, "r", encoding="utf-8") as f:
            head = f.read(2048)
        for marker in ("F.8.c.2.a", "Tutorial Chain Anchor", "May 2026"):
            self.assertIn(marker, head,
                f"Drop marker {marker!r} missing from roster header")


if __name__ == "__main__":
    unittest.main()
