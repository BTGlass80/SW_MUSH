# -*- coding: utf-8 -*-
"""
tests/test_diff3_encounter_band_eligibility.py — DIFF.3 tiered encounter
eligibility.

Per difficulty_tiers_design_v1.md §6. Pins:
  - EncounterEntry carries min_band/max_band (default 1..4 = everywhere);
  - _filter_pool gates an entry out of a tile whose band rating is
    outside [min_band, max_band];
  - the loader parses + clamps + normalizes the bounds;
  - the authored band bounds are present on the dangerous tier-2 pool
    entries (Coruscant maze_ambush, Dune Sea tusken_war_party).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.wilderness_encounters import EncounterEntry, _filter_pool


def _entry(eid, *, min_band=1, max_band=4, terrains=None):
    return EncounterEntry(
        id=eid, type="hostile", weight=1,
        terrains=terrains or [], min_distance_from_edge=0,
        min_band=min_band, max_band=max_band,
        narrative="x", payload={},
    )


class TestEncounterEntryDefaults(unittest.TestCase):

    def test_default_bounds_are_all_bands(self):
        e = EncounterEntry(id="e", type="hostile")
        self.assertEqual(e.min_band, 1)
        self.assertEqual(e.max_band, 4)


class TestFilterPoolBandGating(unittest.TestCase):

    def _filter(self, entries, rating):
        return _filter_pool(
            entries, terrain="any", distance_from_edge=10,
            char={"id": 1}, db=None, region=None,
            tile_band_rating=rating,
        )

    def test_unbounded_entry_eligible_in_every_band(self):
        e = _entry("everywhere")  # default 1..4
        for rating in (1, 2, 3, 4):
            self.assertIn(e, self._filter([e], rating),
                          f"unbounded entry should fire in band {rating}")

    def test_miniboss_gated_out_of_low_bands(self):
        boss = _entry("miniboss", min_band=3)
        # Frontier (1) and Settled (2) must NOT draw it.
        self.assertNotIn(boss, self._filter([boss], 1))
        self.assertNotIn(boss, self._filter([boss], 2))
        # Contested Marches (3) and Deep Wilds (4) DO.
        self.assertIn(boss, self._filter([boss], 3))
        self.assertIn(boss, self._filter([boss], 4))

    def test_trivial_entry_capped_out_of_high_bands(self):
        trivial = _entry("womp_rat", max_band=2)
        self.assertIn(trivial, self._filter([trivial], 1))
        self.assertIn(trivial, self._filter([trivial], 2))
        # A Deep Wilds tile (4) should not roll the trivial-only entry.
        self.assertNotIn(trivial, self._filter([trivial], 4))

    def test_frontier_tile_draws_only_low_entries(self):
        pool = [_entry("thug"), _entry("ambush", min_band=3),
                _entry("boss", min_band=4)]
        frontier = self._filter(pool, 1)
        ids = {e.id for e in frontier}
        self.assertEqual(ids, {"thug"},
                         "a Frontier tile should draw only the unbounded "
                         "low-tier entry")

    def test_wilds_tile_unlocks_the_boss(self):
        pool = [_entry("thug"), _entry("ambush", min_band=3),
                _entry("boss", min_band=4)]
        wilds = self._filter(pool, 4)
        ids = {e.id for e in wilds}
        self.assertEqual(ids, {"thug", "ambush", "boss"})


class TestLoaderParsesBands(unittest.TestCase):
    """The region encounter-pool loader parses min_band/max_band,
    clamps to [1,4], and normalizes a reversed pair."""

    def _parse_one(self, entry_dict):
        from engine.wilderness_encounters import parse_encounter_pool
        # Minimal region pool block with one terrain so the entry keeps.
        block = {
            "base_chance_per_move": 0.05,
            "pool": [dict(entry_dict, id="x", type="hostile",
                          narrative="n")],
        }

        class _Rep:
            def __init__(self):
                self.warnings = []
                self.errors = []
        rep = _Rep()
        pool = parse_encounter_pool(block, terrains={"any": {}},
                                    report=rep)
        return pool.entries[0] if pool.entries else None, rep

    def test_parses_explicit_bounds(self):
        e, _ = self._parse_one({"min_band": 3, "max_band": 4,
                                "terrains": ["any"]})
        self.assertEqual((e.min_band, e.max_band), (3, 4))

    def test_clamps_out_of_range(self):
        e, _ = self._parse_one({"min_band": 0, "max_band": 9,
                                "terrains": ["any"]})
        self.assertEqual((e.min_band, e.max_band), (1, 4))

    def test_reversed_pair_normalized_to_all(self):
        e, rep = self._parse_one({"min_band": 4, "max_band": 1,
                                  "terrains": ["any"]})
        self.assertEqual((e.min_band, e.max_band), (1, 4))
        self.assertTrue(any("min_band" in w for w in rep.warnings))

    def test_default_when_unset(self):
        e, _ = self._parse_one({"terrains": ["any"]})
        self.assertEqual((e.min_band, e.max_band), (1, 4))


class TestAuthoredBandBoundsPresent(unittest.TestCase):
    """The dangerous tier-2 entries carry the authored min_band: 3 so the
    gating is live in the shipped corpus."""

    def _pool(self, region_file, encounter_id):
        path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" /
                "wilderness" / region_file)
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for e in (data.get("encounters") or {}).get("pool") or []:
            if e.get("id") == encounter_id:
                return e
        return None

    def test_coruscant_maze_ambush_is_band3(self):
        e = self._pool("coruscant_underworld.yaml", "maze_ambush")
        self.assertIsNotNone(e, "maze_ambush encounter missing")
        self.assertEqual(e.get("min_band"), 3)

    def test_dune_sea_tusken_war_party_is_band3(self):
        e = self._pool("dune_sea.yaml", "tusken_war_party")
        self.assertIsNotNone(e, "tusken_war_party encounter missing")
        self.assertEqual(e.get("min_band"), 3)


if __name__ == "__main__":
    unittest.main()
