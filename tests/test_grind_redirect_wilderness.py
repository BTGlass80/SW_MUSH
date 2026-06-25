# -*- coding: utf-8 -*-
"""
tests/test_grind_redirect_wilderness.py

GRIND-REDIRECT wilderness content validation (2026-06-24).

Five new creatures (arqet, draagax, keejin, gornt, raen_sovra) and new encounter
pool entries across three regions (ey_akh, dune_sea, coruscant_underworld).

Contracts enforced:

  1. CREATURES: the five new ids parse correctly in npcs_creatures.yaml;
     non-intelligent ones carry KNO/MEC/TEC = 0D; all have natural_attack,
     description, and source.

  2. ENCOUNTER RESOLUTION (anti-phantom): every new pool entry whose
     payload.npc_template is one of the five new ids resolves via the SAME
     runtime resolver (engine.creature_library.get_creature) the spawn bridge
     uses. A miss here = narrative fires, nothing spawns.

  3. ENCOUNTER PRESENCE: each new encounter id exists in the pool of its
     target region.

  4. ERA-CLEANNESS (B3): the new creature descriptions and encounter narratives
     contain no banned GCW-era strings (Imperial/Empire/Rebel/TIE/stormtrooper).

  5. SPOILS WIRING: creatures with a harvest.good block are accepted by
     creature_spoils.creature_has_spoils, and the resource type is in the
     allowed set (no T5 wilderness-only type for a common beast).

  6. NO-ORPHAN: each of the five new creatures is referenced by at least one
     live encounter in the three target regions.
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
WILD_DIR = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness")
EY_AKH = os.path.join(WILD_DIR, "ey_akh.yaml")
DUNE_SEA = os.path.join(WILD_DIR, "dune_sea.yaml")
UNDERWORLD = os.path.join(WILD_DIR, "coruscant_underworld.yaml")
FORCE_RESONANT = os.path.join(WILD_DIR, "force_resonant_landmarks.yaml")

NEW_CREATURE_IDS = {"arqet", "draagax", "keejin", "gornt", "raen_sovra"}

B3_BANNED = (
    "imperial", "empire", "stormtrooper", "death star",
    "rebel alliance", "tie fighter", "tie pilot",
)

# New encounter ids added by this drop, keyed to their region file path.
NEW_ENCOUNTERS_BY_REGION = {
    EY_AKH: {
        "arqet_ambush", "draagax_pack", "keejin_wall_drop",
        "battle_site_debris", "geonosian_scavenger_camp",
    },
    DUNE_SEA: {
        "gornt_herd", "oasis_vaporator_array", "canyon_voroos", "canyon_supply_cache",
    },
    UNDERWORLD: {"raen_sovra_infestation"},
}

# Creatures that should be referenced by the new encounters
NEW_SPAWNING_TEMPLATES = {
    "arqet": EY_AKH,
    "draagax": EY_AKH,
    "keejin": EY_AKH,
    "gornt": DUNE_SEA,
    "raen_sovra": UNDERWORLD,
}


def _load_creatures():
    with open(CREATURES_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {n["id"]: n for n in (data.get("npcs") or [])}


def _load_region_raw(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_region_parsed(path):
    from engine.wilderness_loader import load_wilderness_region
    return load_wilderness_region(path)


class TestNewCreaturesSchema(unittest.TestCase):
    """Contract 1: the five new creatures parse correctly."""

    def setUp(self):
        self.lib = _load_creatures()

    def test_all_new_ids_present(self):
        missing = NEW_CREATURE_IDS - set(self.lib)
        self.assertEqual(missing, set(), f"new creature ids missing from library: {missing}")

    def test_non_intelligent_have_zero_kmt(self):
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None:
                continue
            if c.get("intelligent"):
                continue  # sentient — KMT exemption applies
            attrs = (c.get("char_sheet") or {}).get("attributes") or {}
            for a in ("knowledge", "mechanical", "technical"):
                self.assertEqual(
                    attrs.get(a), "0D",
                    f"{cid}.{a} must be '0D' for a non-intelligent creature",
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

    def test_char_sheet_required_keys(self):
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


class TestNewCreaturesRuntimeResolve(unittest.TestCase):
    """Contract 2: runtime resolver (creature_library) finds all new creatures."""

    def test_get_creature_resolves_all_new_ids(self):
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)
        missing = []
        for cid in NEW_CREATURE_IDS:
            if CL.get_creature(cid) is None:
                missing.append(cid)
        self.assertEqual(
            missing, [],
            f"creature_library.get_creature returned None for: {missing} "
            f"— the encounter fires narrative but spawns nothing",
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


class TestNewEncounterPresence(unittest.TestCase):
    """Contract 3: new encounter ids exist in the target region pools."""

    def _pool_ids(self, path):
        rep = _load_region_parsed(path)
        self.assertTrue(rep.ok, f"region {path} failed to load: {rep.errors[:3]}")
        return {e.id for e in rep.region.encounter_pool.entries}

    def test_ey_akh_new_encounters(self):
        ids = self._pool_ids(EY_AKH)
        expected = NEW_ENCOUNTERS_BY_REGION[EY_AKH]
        missing = expected - ids
        self.assertEqual(missing, set(), f"ey_akh missing new encounter ids: {missing}")

    def test_dune_sea_new_encounters(self):
        ids = self._pool_ids(DUNE_SEA)
        expected = NEW_ENCOUNTERS_BY_REGION[DUNE_SEA]
        missing = expected - ids
        self.assertEqual(missing, set(), f"dune_sea missing new encounter ids: {missing}")

    def test_underworld_new_encounters(self):
        ids = self._pool_ids(UNDERWORLD)
        expected = NEW_ENCOUNTERS_BY_REGION[UNDERWORLD]
        missing = expected - ids
        self.assertEqual(missing, set(), f"coruscant_underworld missing new encounter ids: {missing}")


class TestEraCleanness(unittest.TestCase):
    """Contract 4: new content is B3-clean (no GCW era strings)."""

    def _strings_from_creature(self, c):
        # source is a provenance citation field, not player-facing — exempt per
        # CLAUDE.md ("Comments and era-mapping keys are exempt"). Check only
        # player-visible strings: description, natural_attack name, and specials.
        strings = [
            c.get("description") or "",
            (c.get("natural_attack") or {}).get("name") or "",
        ]
        for s in c.get("special") or []:
            strings.append(str(s))
        return strings

    def test_creature_descriptions_era_clean(self):
        lib = _load_creatures()
        violations = []
        for cid in NEW_CREATURE_IDS:
            c = lib.get(cid)
            if c is None:
                continue
            for s in self._strings_from_creature(c):
                for banned in B3_BANNED:
                    if banned in s.lower():
                        violations.append(f"{cid}: '{banned}' in '{s[:60]}'")
        self.assertEqual(violations, [], f"B3 era violations in new creatures:\n  " +
                         "\n  ".join(violations))

    def test_encounter_narratives_era_clean(self):
        violations = []
        for path, enc_ids in NEW_ENCOUNTERS_BY_REGION.items():
            raw = _load_region_raw(path)
            pool = (raw.get("encounters") or {}).get("pool") or []
            by_id = {e.get("id"): e for e in pool if isinstance(e, dict)}
            for eid in enc_ids:
                e = by_id.get(eid)
                if e is None:
                    continue
                narrative = str(e.get("narrative") or "")
                for banned in B3_BANNED:
                    if banned in narrative.lower():
                        violations.append(f"{eid}: '{banned}' in narrative")
        self.assertEqual(violations, [], "B3 era violations in new encounter narratives:\n  " +
                         "\n  ".join(violations))


class TestSpoilsWiring(unittest.TestCase):
    """Contract 5: creatures with harvest blocks are accepted by creature_spoils."""

    def test_spoils_resource_types_allowed(self):
        from engine.creature_spoils import (
            creature_has_spoils, spoils_resource_type,
            _ALLOWED_RESOURCE_TYPES,
        )
        lib = _load_creatures()
        bad = []
        for cid in NEW_CREATURE_IDS:
            c = lib.get(cid)
            if c is None or not creature_has_spoils(c):
                continue
            rtype = spoils_resource_type(c)
            if rtype not in _ALLOWED_RESOURCE_TYPES:
                bad.append(f"{cid}: resource type {rtype!r} not in allowed set")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_spoils_has_good_string(self):
        from engine.creature_spoils import creature_has_spoils
        lib = _load_creatures()
        # All five new creatures have a harvest block — verify it's usable
        for cid in NEW_CREATURE_IDS:
            c = lib.get(cid)
            if c is None:
                continue
            h = c.get("harvest")
            if h is not None:
                self.assertTrue(
                    creature_has_spoils(c),
                    f"{cid} has a harvest block but creature_has_spoils returned False",
                )
                self.assertTrue(
                    str(h.get("good") or "").strip(),
                    f"{cid}.harvest.good is empty",
                )


class TestNoOrphanCreatures(unittest.TestCase):
    """Contract 6: each new creature is referenced by at least one live encounter."""

    def _all_templates_in_region(self, path):
        rep = _load_region_parsed(path)
        if not rep.ok:
            return set()
        return {
            (e.payload or {}).get("npc_template")
            for e in rep.region.encounter_pool.entries
            if (e.payload or {}).get("npc_template")
        }

    def test_no_orphan_new_creatures(self):
        referenced = set()
        referenced |= self._all_templates_in_region(EY_AKH)
        referenced |= self._all_templates_in_region(DUNE_SEA)
        referenced |= self._all_templates_in_region(UNDERWORLD)
        orphans = NEW_CREATURE_IDS - referenced
        self.assertEqual(
            orphans, set(),
            f"New creatures with no encounter reference (phantom risk): {orphans}",
        )


if __name__ == "__main__":
    unittest.main()
