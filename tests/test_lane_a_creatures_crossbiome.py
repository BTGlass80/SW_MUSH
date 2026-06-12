# -*- coding: utf-8 -*-
"""
tests/test_lane_a_creatures_crossbiome.py — Sourcebook Enrichment Lane A, Phase A
(cross-biome wildcards). Companion to the Tatooine and Coruscant tests.

These creatures (voroos, shredder_bat, wrix, winged_xendrite) span BOTH live
regions, so the contract is checked over the UNION of the dune_sea and
coruscant_underworld pools. The Slimy Nonakara needs a water tile neither live
region has, so it is lore-only and must NOT be in the library.

Validated against the REAL loaders (wilderness_loader + world_loader.load_lore).
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

CREATURE_FILE = os.path.join(PROJECT_ROOT, "data", "npcs_creatures.yaml")
WILD = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness")
DUNE_SEA = os.path.join(WILD, "dune_sea.yaml")
FORCE_RESONANT = os.path.join(WILD, "force_resonant_landmarks.yaml")
UNDERWORLD = os.path.join(WILD, "coruscant_underworld.yaml")

CROSSBIOME_IDS = {"voroos", "shredder_bat", "wrix", "winged_xendrite"}
# Where each is wired (union across both regions).
DUNE_SEA_ENCOUNTERS = {"voroos_ambush", "wrix_pack", "shredder_bat_swarm"}
UNDERWORLD_ENCOUNTERS = {"shredder_bat_roost", "xendrite_cloud"}
SPECIES_TITLES = {"The Voroos", "Shredder Bats", "The Wrix",
                  "Winged Xendrites", "The Slimy Nonakara"}


def _load_creatures():
    with open(CREATURE_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _region(path, force_resonant=None):
    from engine.wilderness_loader import load_wilderness_region
    rep = load_wilderness_region(path, force_resonant_path=force_resonant)
    assert rep.ok, f"region {os.path.basename(path)} failed to load: {rep.errors[:3]}"
    return rep.region


def _referenced_union():
    refs = set()
    for region in (_region(DUNE_SEA, FORCE_RESONANT), _region(UNDERWORLD)):
        for e in region.encounter_pool.entries:
            t = (e.payload or {}).get("npc_template")
            if t:
                refs.add(t)
    return refs


class TestCrossbiomeLibrary(unittest.TestCase):
    def test_crossbiome_creatures_well_formed(self):
        by_id = {n["id"]: n for n in _load_creatures()["npcs"]}
        for cid in CROSSBIOME_IDS:
            self.assertIn(cid, by_id, f"missing cross-biome creature {cid!r}")
            n = by_id[cid]
            attrs = n["char_sheet"]["attributes"]
            for a in ("knowledge", "mechanical", "technical"):
                self.assertEqual(attrs[a], "0D", f"{cid}.{a}")
            self.assertIn("natural_attack", n, f"{cid} natural_attack")
            self.assertTrue(n.get("description"), f"{cid} description")

    def test_nonakara_is_lore_only(self):
        # No live water tile exists, so Slimy Nonakara has no encounter and must
        # NOT be in the library (or the no-orphan contract would demand one).
        ids = {n["id"] for n in _load_creatures()["npcs"]}
        self.assertNotIn("slimy_nonakara", ids)


class TestCrossbiomeEncounters(unittest.TestCase):
    def test_dune_sea_encounters_present(self):
        ids = {e.id for e in _region(DUNE_SEA, FORCE_RESONANT).encounter_pool.entries}
        for eid in DUNE_SEA_ENCOUNTERS:
            self.assertIn(eid, ids, f"{eid} missing from dune_sea pool")

    def test_underworld_encounters_present(self):
        ids = {e.id for e in _region(UNDERWORLD).encounter_pool.entries}
        for eid in UNDERWORLD_ENCOUNTERS:
            self.assertIn(eid, ids, f"{eid} missing from underworld pool")

    def test_no_orphan_crossbiome_creatures(self):
        """Every cross-biome creature is referenced in at least one live region."""
        referenced = _referenced_union()
        orphans = CROSSBIOME_IDS - referenced
        self.assertEqual(
            orphans, set(),
            f"cross-biome creatures with no live encounter (phantom risk): {orphans}",
        )

    def test_templates_resolve_to_library(self):
        lib_ids = {n["id"] for n in _load_creatures()["npcs"]}
        for path, fr in ((DUNE_SEA, FORCE_RESONANT), (UNDERWORLD, None)):
            for e in _region(path, fr).encounter_pool.entries:
                tmpl = (e.payload or {}).get("npc_template")
                if tmpl in CROSSBIOME_IDS:
                    self.assertIn(tmpl, lib_ids,
                                  f"{e.id} references {tmpl!r} not in the library")


class TestCrossbiomeLore(unittest.TestCase):
    def _corpus(self):
        from pathlib import Path
        from engine.world_loader import load_era_manifest, load_lore
        return load_lore(load_era_manifest(
            Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars"))

    def test_lore_loads_without_errors(self):
        c = self._corpus()
        self.assertEqual(c.report.errors, [],
                         f"lore.yaml validation errors: {c.report.errors[:3]}")

    def test_species_entries_present(self):
        by_title = {e.title: e for e in self._corpus().entries}
        for t in SPECIES_TITLES:
            self.assertIn(t, by_title, f"missing species lore entry {t!r}")
            self.assertEqual(by_title[t].category, "species", f"{t} category")


if __name__ == "__main__":
    unittest.main()
