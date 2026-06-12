# -*- coding: utf-8 -*-
"""
tests/test_lane_a_creatures_coruscant.py — Sourcebook Enrichment Lane A, Phase A
(Coruscant / Nar Shaddaa urban vermin). Companion to the Tatooine test; same
contract, exercised against the REAL loaders.

  1. The five encountered urban creatures (yeomet, borcatu, tymp, spor_crawler,
     somago) are present in data/npcs_creatures.yaml with KNO/MEC/TEC = 0D and a
     natural_attack. (Sensor Star is lore-only — security flavour, no encounter —
     so it is intentionally NOT in the library and NOT in this set.)
  2. coruscant_underworld.yaml loads through engine.wilderness_loader: the five
     vermin encounters parse with live narrative, and the encounter<->library
     contract holds both directions over THIS region's pool:
       (a) each vermin encounter's payload.npc_template resolves to a library id;
       (b) each of the five urban creatures is referenced by >=1 encounter here.
  3. lore.yaml loads with 0 errors and the six urban species entries are present
     (the five creatures + Sensor Stars) with category 'species'.
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
UNDERWORLD = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness",
    "coruscant_underworld.yaml")

# The five urban creatures that have encounters (Sensor Star is lore-only).
URBAN_IDS = {"yeomet", "borcatu", "tymp", "spor_crawler", "somago"}
URBAN_ENCOUNTERS = {"yeomet_swarm", "borcatu_scavenger", "tymp_raid",
                    "spor_crawler_nest", "somago_drop"}
URBAN_SPECIES_TITLES = {"Yeomet Vermin", "The Borcatu", "Spor Crawlers",
                        "Tymps", "The Somago", "Sensor Stars"}


def _load_creatures():
    with open(CREATURE_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestUrbanCreatureLibrary(unittest.TestCase):
    def test_urban_creatures_present_and_well_formed(self):
        d = _load_creatures()
        by_id = {n["id"]: n for n in d["npcs"]}
        for cid in URBAN_IDS:
            self.assertIn(cid, by_id, f"missing urban creature {cid!r}")
            n = by_id[cid]
            attrs = n["char_sheet"]["attributes"]
            for a in ("knowledge", "mechanical", "technical"):
                self.assertEqual(attrs[a], "0D", f"{cid}.{a}")
            self.assertIn("natural_attack", n, f"{cid} natural_attack")
            self.assertTrue(n.get("description"), f"{cid} description")

    def test_sensor_star_is_lore_only(self):
        # Sensor Star does not roam; it must NOT be in the encounter library
        # (or the no-orphan contract below would require an encounter for it).
        ids = {n["id"] for n in _load_creatures()["npcs"]}
        self.assertNotIn("sensor_star", ids)


class TestUrbanEncounterContract(unittest.TestCase):
    def _load_region(self):
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(UNDERWORLD)
        self.assertTrue(rep.ok,
                        f"coruscant_underworld failed to load: {rep.errors[:3]}")
        return rep.region

    def test_urban_encounters_present_with_narrative(self):
        region = self._load_region()
        byid = {e.id: e for e in region.encounter_pool.entries}
        for eid in URBAN_ENCOUNTERS:
            self.assertIn(eid, byid, f"encounter {eid} missing from underworld pool")
            self.assertTrue(byid[eid].narrative.strip(),
                            f"{eid} must have a live narrative")

    def test_template_resolves_to_library(self):
        region = self._load_region()
        lib_ids = {n["id"] for n in _load_creatures()["npcs"]}
        for e in region.encounter_pool.entries:
            tmpl = (e.payload or {}).get("npc_template")
            if tmpl in URBAN_IDS:
                self.assertIn(
                    tmpl, lib_ids,
                    f"encounter {e.id} references npc_template {tmpl!r} "
                    f"not in npcs_creatures.yaml")

    def test_no_orphan_urban_creatures(self):
        """Every urban creature has at least one live underworld encounter."""
        region = self._load_region()
        referenced = {
            (e.payload or {}).get("npc_template")
            for e in region.encounter_pool.entries
        }
        orphans = URBAN_IDS - referenced
        self.assertEqual(
            orphans, set(),
            f"urban creatures with no underworld encounter (phantom risk): {orphans}",
        )


class TestUrbanLoreSeeds(unittest.TestCase):
    def _load_corpus(self):
        from pathlib import Path
        from engine.world_loader import load_era_manifest, load_lore
        m = load_era_manifest(Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars")
        return load_lore(m)

    def test_lore_loads_without_errors(self):
        corpus = self._load_corpus()
        self.assertEqual(
            corpus.report.errors, [],
            f"lore.yaml has validation errors: {corpus.report.errors[:3]}")

    def test_urban_species_entries_present(self):
        corpus = self._load_corpus()
        by_title = {e.title: e for e in corpus.entries}
        for t in URBAN_SPECIES_TITLES:
            self.assertIn(t, by_title, f"missing species lore entry {t!r}")
            self.assertEqual(by_title[t].category, "species", f"{t} category")


if __name__ == "__main__":
    unittest.main()
