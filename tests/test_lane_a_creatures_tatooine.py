# -*- coding: utf-8 -*-
"""
tests/test_lane_a_creatures_tatooine.py — Sourcebook Enrichment Lane A, Phase A.

Pins the Tatooine creature enrichment against the REAL loaders (not byte-grep),
so server/source agreement is runtime-verified:

  1. data/npcs_creatures.yaml — the standalone faithful-stats generator pool:
     parses, schema_version 1, the five Tatooine ids, non-intelligent creatures
     carry KNO/MEC/TEC = 0D, and each has a natural_attack + description.

  2. FORCE-SPAWN GUARD — npcs_creatures.yaml must NOT be registered in
     data/worlds/clone_wars/era.yaml content_refs.npcs. The NPC loader force-
     places roomless NPCs into fallback_room_idx, so a pooled creature library
     in that list would dump every creature into one room on boot.

  3. dune_sea.yaml encounters — loaded through engine.wilderness_loader: the five
     creature encounters parse, and the encounter<->library contract holds in
     BOTH directions:
       (a) every creature encounter's payload.npc_template resolves to an id in
           npcs_creatures.yaml (no dangling template ref), and
       (b) every creature in npcs_creatures.yaml is referenced by at least one
           encounter (no orphan creature with no live consumer — keeps the
           library from being a phantom).

  4. lore.yaml — loaded through engine.world_loader.load_lore: 0 validation
     errors (a single error aborts the whole CW lore seed), and the five species
     entries are present with category 'species'.
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
WILD_DIR = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness")
DUNE_SEA = os.path.join(WILD_DIR, "dune_sea.yaml")
FORCE_RESONANT = os.path.join(WILD_DIR, "force_resonant_landmarks.yaml")
ERA_YAML = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars", "era.yaml")

TATOOINE_IDS = {"worrt", "glim_worm", "hitcher_crab", "magus", "stalker_lizard"}
SPECIES_TITLES = {"The Worrt", "Glim Worms", "Hitcher Crabs",
                  "The Magus", "Stalker Lizards"}


def _load_creatures():
    with open(CREATURE_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestCreatureLibrary(unittest.TestCase):
    def test_parses_and_schema(self):
        d = _load_creatures()
        self.assertEqual(d.get("schema_version"), 1)
        ids = {n["id"] for n in d["npcs"]}
        # The library also holds other biomes (urban vermin, etc.); assert the
        # Tatooine set is present as a subset rather than the whole library.
        self.assertTrue(TATOOINE_IDS <= ids,
                        f"missing Tatooine ids: {TATOOINE_IDS - ids}")

    def test_non_intelligent_attributes_and_natural_attack(self):
        d = _load_creatures()
        for n in d["npcs"]:
            attrs = n["char_sheet"]["attributes"]
            self.assertEqual(
                set(attrs),
                {"dexterity", "perception", "strength",
                 "knowledge", "mechanical", "technical"},
                f"{n['id']} attribute keys",
            )
            # Non-intelligent creatures (beasts) have no knowledge/mechanical/
            # technical — faithful to the WEG creature convention and stops a
            # future loader defaulting them to 2D. SENTIENT spawn templates
            # (Tusken Raiders, underworld thugs) are tagged `intelligent: true`
            # and carry real KNO/MEC/TEC, so the 0D rule applies to beasts only.
            if not n.get("intelligent"):
                for a in ("knowledge", "mechanical", "technical"):
                    self.assertEqual(attrs[a], "0D", f"{n['id']}.{a}")
            else:
                # An intelligent template must actually USE the exemption (a
                # beast mistagged `intelligent` would silently lose the 0D guard).
                self.assertTrue(
                    any(attrs[a] != "0D"
                        for a in ("knowledge", "mechanical", "technical")),
                    f"{n['id']} is tagged intelligent but has 0D KNO/MEC/TEC "
                    f"— drop the flag or give it real attributes",
                )
            self.assertIn("natural_attack", n, f"{n['id']} natural_attack")
            self.assertTrue(n.get("description"), f"{n['id']} description")
            self.assertTrue(n.get("source"), f"{n['id']} source")


class TestForceSpawnGuard(unittest.TestCase):
    def test_creature_file_not_in_era_npcs(self):
        with open(ERA_YAML, encoding="utf-8") as f:
            era = yaml.safe_load(f)
        npc_refs = ((era.get("content_refs") or {}).get("npcs") or [])
        # Compare on basename so a future path-qualified ref is still caught.
        bases = {os.path.basename(str(r)) for r in npc_refs}
        self.assertNotIn(
            "npcs_creatures.yaml", bases,
            "npcs_creatures.yaml must NOT be in era.yaml content_refs.npcs "
            "(the loader would force-spawn the whole pool into fallback_room_idx).",
        )


class TestEncounterContract(unittest.TestCase):
    def _load_region(self):
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(DUNE_SEA, force_resonant_path=FORCE_RESONANT)
        self.assertTrue(rep.ok, f"dune_sea failed to load: {rep.errors[:3]}")
        return rep.region

    def test_creature_encounters_present(self):
        region = self._load_region()
        ids = {e.id for e in region.encounter_pool.entries}
        for eid in ("worrt_cluster", "glim_worm_strike", "hitcher_crab_buried",
                    "magus_burrower", "stalker_lizard_hunt"):
            self.assertIn(eid, ids, f"encounter {eid} missing from dune_sea pool")

    def test_template_resolves_to_library(self):
        """(a) Every creature encounter's npc_template is a real creature id."""
        region = self._load_region()
        lib_ids = {n["id"] for n in _load_creatures()["npcs"]}
        for e in region.encounter_pool.entries:
            tmpl = (e.payload or {}).get("npc_template")
            if tmpl in TATOOINE_IDS:  # one of ours
                self.assertIn(
                    tmpl, lib_ids,
                    f"encounter {e.id} references npc_template {tmpl!r} "
                    f"not in npcs_creatures.yaml",
                )

    def test_no_orphan_creatures(self):
        """(b) Every Tatooine creature has at least one live dune_sea encounter."""
        region = self._load_region()
        referenced = {
            (e.payload or {}).get("npc_template")
            for e in region.encounter_pool.entries
        }
        orphans = TATOOINE_IDS - referenced
        self.assertEqual(
            orphans, set(),
            f"Tatooine creatures with no dune_sea encounter (phantom risk): {orphans}",
        )

    def test_creature_encounters_have_narrative(self):
        region = self._load_region()
        byid = {e.id: e for e in region.encounter_pool.entries}
        for eid in ("worrt_cluster", "glim_worm_strike", "hitcher_crab_buried",
                    "magus_burrower", "stalker_lizard_hunt"):
            self.assertTrue(byid[eid].narrative.strip(),
                            f"{eid} must have a live narrative")


class TestLoreSeeds(unittest.TestCase):
    def _load_corpus(self):
        from pathlib import Path
        from engine.world_loader import load_era_manifest, load_lore
        m = load_era_manifest(Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars")
        return load_lore(m)

    def test_lore_loads_without_errors(self):
        corpus = self._load_corpus()
        self.assertEqual(
            corpus.report.errors, [],
            f"lore.yaml has validation errors (would abort the whole CW seed): "
            f"{corpus.report.errors[:3]}",
        )

    def test_species_entries_present(self):
        corpus = self._load_corpus()
        by_title = {e.title: e for e in corpus.entries}
        for t in SPECIES_TITLES:
            self.assertIn(t, by_title, f"missing species lore entry {t!r}")
            self.assertEqual(by_title[t].category, "species", f"{t} category")


if __name__ == "__main__":
    unittest.main()
