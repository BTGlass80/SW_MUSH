# -*- coding: utf-8 -*-
"""
tests/test_grind_breadth_wilderness.py

Wilderness Grind Breadth drop validation (2026-06-25).

Five regions, five new creatures (bantha, preying_makthier, svaper,
syndicate_enforcer, drain_lurker) and 14 new pool entries spread across
dune_sea.yaml, tatooine_jundland.yaml, ey_akh.yaml, and
coruscant_underworld.yaml (uscru_fringe_brokers entries land here).

Contracts enforced:

  1. CREATURES: all new ids parse in npcs_creatures.yaml with the correct
     char_sheet wrapper (attributes/skills/move nested under char_sheet).
     Non-intelligent creatures carry KNO/MEC/TEC = 0D. Each has
     natural_attack, description, and source.

  2. ENCOUNTER RESOLUTION (anti-phantom): every new pool entry whose
     payload.npc_template is a new id resolves via
     engine.creature_library.get_creature (the runtime spawn bridge path).
     A miss = narrative fires, nothing spawns.

  3. ENCOUNTER PRESENCE: all expected new encounter ids exist in the
     correct region pool.

  4. PAYLOAD SHAPE: every new hostile/non_hostile entry with a template
     has its npc_template nested under payload (not at top level).

  5. ERA-CLEANNESS (B3): new creature descriptions + encounter narratives
     contain no banned GCW-era strings.

  6. NO-ORPHAN: each new creature is referenced by at least one live
     encounter across the touched regions.

  7. CONSTRICTION FIDELITY: preying_makthier special_attack.restraint
     hold_damage must be '1D' (COTG §2.3 exact value; NOT 'STR+1D').

  8. HIGH-DAMAGE GATING: hostile entries with certain creature ids that
     are mid-tier threats must carry min_band >= 2.
"""

import os
import sys
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import yaml  # noqa: E402

CREATURES_FILE = os.path.join(PROJECT_ROOT, "data", "npcs_creatures.yaml")
WILD_DIR = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness"
)

DUNE_SEA = os.path.join(WILD_DIR, "dune_sea.yaml")
JUNDLAND = os.path.join(WILD_DIR, "tatooine_jundland.yaml")
EY_AKH = os.path.join(WILD_DIR, "ey_akh.yaml")
UNDERWORLD = os.path.join(WILD_DIR, "coruscant_underworld.yaml")

NEW_CREATURE_IDS = {
    "bantha",
    "preying_makthier",
    "svaper",
    "syndicate_enforcer",
    "drain_lurker",
}

# Encounters that must exist after the drop, keyed by region file path.
EXPECTED_ENCOUNTERS = {
    DUNE_SEA: {"tusken_bantha_herd", "oasis_predator_stalk"},
    JUNDLAND: {"gornt_jundland_herd", "stalker_lizard_jundland", "arqet_canyon_ambush"},
    EY_AKH: {"preying_makthier_crater", "dune_fringe_shredder_bats", "ebon_shore_bone_field"},
    UNDERWORLD: {
        "svaper_escape", "makthier_dive", "rubble_voroos",
        "uscru_syndicate_muscle", "drain_lurker_ambush", "uscru_back_alley_mugging",
    },
}

# Encounters that MUST have min_band >= 2 (mid-tier hostiles).
MIN_BAND_REQUIRED = {
    "oasis_predator_stalk": 2,
    "arqet_canyon_ambush": 2,
    "preying_makthier_crater": 2,
    "svaper_escape": 2,
    "makthier_dive": 2,
    "rubble_voroos": 2,
}

B3_BANNED = (
    "imperial", "empire", "stormtrooper", "death star",
    "rebel alliance", "tie fighter", "tie pilot",
)


def _load_creatures():
    with open(CREATURES_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {n["id"]: n for n in (data.get("npcs") or [])}


def _load_region_raw(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pool_entries(raw):
    """Return list of pool entries from a region YAML dict."""
    enc = raw.get("encounters") or {}
    return enc.get("pool") or []


def _pool_by_id(raw):
    return {e["id"]: e for e in _pool_entries(raw)}


class TestNewCreaturesSchema(unittest.TestCase):
    """Contract 1: new creature blocks parse with correct schema."""

    def setUp(self):
        self.lib = _load_creatures()

    def test_all_new_ids_present(self):
        missing = NEW_CREATURE_IDS - set(self.lib)
        self.assertEqual(missing, set(), f"new creature ids missing: {missing}")

    def test_char_sheet_wrapper_present(self):
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None:
                continue
            self.assertIn(
                "char_sheet", c,
                f"{cid}: missing 'char_sheet' wrapper (attributes must be nested under char_sheet)",
            )
            cs = c["char_sheet"]
            self.assertIn("attributes", cs, f"{cid}.char_sheet missing 'attributes'")
            self.assertIn("skills", cs, f"{cid}.char_sheet missing 'skills'")
            self.assertIn("move", cs, f"{cid}.char_sheet missing 'move'")
            self.assertIn("force_points", cs, f"{cid}.char_sheet missing 'force_points'")
            self.assertIn("character_points", cs, f"{cid}.char_sheet missing 'character_points'")
            self.assertIn("dark_side_points", cs, f"{cid}.char_sheet missing 'dark_side_points'")

    def test_required_attributes_present(self):
        required_attrs = {
            "dexterity", "perception", "strength",
            "knowledge", "mechanical", "technical",
        }
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None:
                continue
            attrs = ((c.get("char_sheet") or {}).get("attributes") or {})
            missing = required_attrs - set(attrs)
            self.assertEqual(missing, set(), f"{cid} missing attribute keys: {missing}")

    def test_non_intelligent_have_zero_kmt(self):
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None or c.get("intelligent"):
                continue
            attrs = (c.get("char_sheet") or {}).get("attributes") or {}
            for a in ("knowledge", "mechanical", "technical"):
                self.assertEqual(
                    attrs.get(a), "0D",
                    f"{cid}.{a} must be '0D' for a non-intelligent creature (got {attrs.get(a)!r})",
                )

    def test_skills_is_dict(self):
        """Skills must be a MAP (str->str), not a list of {skill,dice} objects."""
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None:
                continue
            skills = (c.get("char_sheet") or {}).get("skills") or {}
            self.assertIsInstance(
                skills, dict,
                f"{cid}.char_sheet.skills must be a dict (skill->dice), not a list",
            )

    def test_have_natural_attack_description_source(self):
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None:
                continue
            self.assertIn("natural_attack", c, f"{cid} missing natural_attack")
            self.assertTrue(
                (c.get("natural_attack") or {}).get("damage"),
                f"{cid}.natural_attack.damage is empty",
            )
            self.assertTrue(c.get("description"), f"{cid} missing description")
            self.assertTrue(c.get("source"), f"{cid} missing source")


class TestNewCreaturesRuntimeResolve(unittest.TestCase):
    """Contract 2: runtime resolver finds all new creatures."""

    def test_get_creature_resolves_all_new_ids(self):
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)
        missing = [
            cid for cid in NEW_CREATURE_IDS
            if CL.get_creature(cid) is None
        ]
        self.assertEqual(
            missing, [],
            f"creature_library.get_creature returned None for: {missing}",
        )

    def test_natural_attack_resolves_to_usable_damage(self):
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)
        broken = []
        for cid in NEW_CREATURE_IDS:
            c = CL.get_creature(cid)
            if c is None:
                continue
            atk = CL.resolve_natural_attack(c)
            if not str(atk.get("damage") or "").strip():
                broken.append(cid)
        self.assertEqual(
            broken, [],
            f"creature(s) resolve but produce no natural-attack damage: {broken}",
        )


class TestEncounterPresence(unittest.TestCase):
    """Contract 3: all new encounter ids exist in the correct region pools."""

    def test_dune_sea_new_encounters_present(self):
        raw = _load_region_raw(DUNE_SEA)
        pool = _pool_by_id(raw)
        for eid in EXPECTED_ENCOUNTERS[DUNE_SEA]:
            self.assertIn(eid, pool, f"dune_sea.yaml missing encounter id: {eid}")

    def test_jundland_new_encounters_present(self):
        raw = _load_region_raw(JUNDLAND)
        pool = _pool_by_id(raw)
        for eid in EXPECTED_ENCOUNTERS[JUNDLAND]:
            self.assertIn(eid, pool, f"tatooine_jundland.yaml missing encounter id: {eid}")

    def test_ey_akh_new_encounters_present(self):
        raw = _load_region_raw(EY_AKH)
        pool = _pool_by_id(raw)
        for eid in EXPECTED_ENCOUNTERS[EY_AKH]:
            self.assertIn(eid, pool, f"ey_akh.yaml missing encounter id: {eid}")

    def test_underworld_new_encounters_present(self):
        raw = _load_region_raw(UNDERWORLD)
        pool = _pool_by_id(raw)
        for eid in EXPECTED_ENCOUNTERS[UNDERWORLD]:
            self.assertIn(eid, pool, f"coruscant_underworld.yaml missing encounter id: {eid}")


class TestPayloadShape(unittest.TestCase):
    """Contract 4: npc_template is nested under payload, not top-level."""

    def _check_pool(self, path, expected_ids):
        raw = _load_region_raw(path)
        pool = _pool_by_id(raw)
        for eid in expected_ids:
            e = pool.get(eid)
            if e is None:
                continue
            e_type = e.get("type")
            if e_type not in ("hostile", "non_hostile"):
                continue
            payload = e.get("payload") or {}
            top_template = e.get("npc_template")
            self.assertIsNone(
                top_template,
                f"{eid}: npc_template is at TOP LEVEL (should be nested under payload:)",
            )
            # If payload has a template, it must be a string
            pt = payload.get("npc_template")
            if pt is not None:
                self.assertIsInstance(
                    pt, str,
                    f"{eid}.payload.npc_template must be a string, got {type(pt)}",
                )

    def test_dune_sea_payload_shape(self):
        self._check_pool(DUNE_SEA, EXPECTED_ENCOUNTERS[DUNE_SEA])

    def test_jundland_payload_shape(self):
        self._check_pool(JUNDLAND, EXPECTED_ENCOUNTERS[JUNDLAND])

    def test_ey_akh_payload_shape(self):
        self._check_pool(EY_AKH, EXPECTED_ENCOUNTERS[EY_AKH])

    def test_underworld_payload_shape(self):
        self._check_pool(UNDERWORLD, EXPECTED_ENCOUNTERS[UNDERWORLD])


class TestEraCleanness(unittest.TestCase):
    """Contract 5: no GCW-era strings in new content."""

    def _scan(self, text, context):
        lower = text.lower()
        for token in B3_BANNED:
            self.assertNotIn(
                token, lower,
                f"Era violation in {context}: found '{token}'",
            )

    def test_new_creature_descriptions_era_clean(self):
        lib = _load_creatures()
        for cid in NEW_CREATURE_IDS:
            c = lib.get(cid)
            if c is None:
                continue
            self._scan(c.get("description", ""), f"{cid}.description")
            for sp in (c.get("special") or []):
                self._scan(sp, f"{cid}.special")

    def test_new_encounter_narratives_era_clean(self):
        for path, eids in EXPECTED_ENCOUNTERS.items():
            raw = _load_region_raw(path)
            pool = _pool_by_id(raw)
            for eid in eids:
                e = pool.get(eid)
                if e is None:
                    continue
                self._scan(e.get("narrative", ""), f"{eid}.narrative")


class TestNoOrphanCreatures(unittest.TestCase):
    """Contract 6: each new creature is referenced by at least one live encounter."""

    def test_all_new_creatures_referenced(self):
        all_templates = set()
        for path in EXPECTED_ENCOUNTERS:
            raw = _load_region_raw(path)
            for e in _pool_entries(raw):
                t = (e.get("payload") or {}).get("npc_template")
                if t:
                    all_templates.add(t)
        unreferenced = NEW_CREATURE_IDS - all_templates
        self.assertEqual(
            unreferenced, set(),
            f"new creature(s) added but not referenced by any pool entry: {unreferenced}",
        )


class TestMakthierConstrictionFidelity(unittest.TestCase):
    """Contract 7: preying_makthier constriction is '1D' (COTG §2.3 exact)."""

    def test_constriction_value(self):
        lib = _load_creatures()
        c = lib.get("preying_makthier")
        if c is None:
            self.skipTest("preying_makthier not in library yet")
        sa = c.get("special_attack") or {}
        restraint = sa.get("restraint") or {}
        hold_damage = restraint.get("hold_damage", "")
        self.assertEqual(
            hold_damage, "1D",
            f"preying_makthier constriction hold_damage must be '1D' (COTG §2.3), got {hold_damage!r}. "
            "NOT 'STR+1D' — that inflates the source.",
        )


class TestHighDamageGating(unittest.TestCase):
    """Contract 8: mid-tier hostiles carry min_band >= 2."""

    def _get_pool_by_id_all_regions(self):
        combined = {}
        for path in EXPECTED_ENCOUNTERS:
            raw = _load_region_raw(path)
            combined.update(_pool_by_id(raw))
        return combined

    def test_min_band_gating(self):
        pool = self._get_pool_by_id_all_regions()
        for eid, required_min_band in MIN_BAND_REQUIRED.items():
            e = pool.get(eid)
            if e is None:
                continue
            actual = e.get("min_band") or 1
            self.assertGreaterEqual(
                actual, required_min_band,
                f"{eid}: min_band={actual} is below required {required_min_band} for this threat level",
            )


if __name__ == "__main__":
    unittest.main()
