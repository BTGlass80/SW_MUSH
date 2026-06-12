# -*- coding: utf-8 -*-
"""
tests/test_coruscant_underworld_buildout.py — drop 18.

Pins the Coruscant Underworld region build-out: 12 secondary landmarks
added across the four 40x40 quadrants (NW industrial overflow, NE
smuggler reaches, SW deep warren, SE Maze fringe), one disjoint-quadrant
include file each, coordinate-placed (no adjacency) to match the existing
8 design-doc anchors.

These tests load the REAL region YAML (not a synthetic fixture) so they
guard:
  * the region still loads with zero errors after the 4 new includes,
  * the 12 new landmarks are present at their exact assigned coordinates,
  * coordinates stay unique and in-bounds across the whole region,
  * the new content is era-clean (B3) and uses only the established
    landmark-property vocabulary (no invented/phantom property keys).
"""
from __future__ import annotations

import os
import re
import unittest

from engine.wilderness_loader import load_wilderness_region

_WILD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "worlds", "clone_wars", "wilderness",
)
_REGION = os.path.join(_WILD_DIR, "coruscant_underworld.yaml")
_FRP = os.path.join(_WILD_DIR, "force_resonant_landmarks.yaml")

# The 12 build-out landmarks and their assigned (collision-free) coords.
_NEW = {
    # NW — industrial overflow
    "nw_tier_seven_warehouse_row": (6, 7),
    "nw_overflow_thoroughfare_market": (14, 11),
    "nw_sublevel_pump_station_nine": (10, 18),
    # NE — smuggler reaches
    "ne_derelict_loading_docks": (34, 9),
    "ne_contraband_transfer_point": (27, 13),
    "ne_stripped_cargo_lift_hub": (37, 3),
    # SW — the deep warren
    "sw_ancient_pipe_market": (4, 28),
    "sw_foundation_stratum_museum": (15, 25),
    "sw_null_gallery": (9, 34),
    # SE — the Maze fringe
    "se_collapse_gallery": (33, 30),
    "se_sublevel_shriek_dark": (29, 36),
    "se_last_ward_marker": (37, 23),
}

# Property keys established by the existing anchors (force_resonant is the
# shrine's; build-out landmarks must NOT use it). The build-out must not
# invent new property keys — unknown keys are unconsumed phantom data.
_ALLOWED_PROP_KEYS = {
    "wilderness_landmark", "ambient_disabled", "director_managed",
    "faction_anchor", "gameplay_role", "hostile_default", "threat_tier",
    "npc_cluster", "job_board", "structural_hazard", "low_level_warning",
    "cartography_unstable", "transit_node",
}

_BANNED = re.compile(
    r"\b(imperial|empire|stormtrooper|tie fighter|death star|x-wing|"
    r"rebel alliance)\b",
    re.IGNORECASE,
)


def _load():
    return load_wilderness_region(_REGION, force_resonant_path=_FRP)


class TestRegionLoadsClean(unittest.TestCase):
    def test_zero_errors(self):
        rep = _load()
        self.assertEqual(rep.errors, [], f"loader errors: {rep.errors}")
        self.assertIsNotNone(rep.region)

    def test_total_landmark_count(self):
        """8 design-doc anchors + 12 build-out = 20."""
        rep = _load()
        self.assertEqual(len(rep.region.landmarks), 20)

    def test_coords_and_ids_unique(self):
        rep = _load()
        coords = [l.coordinates for l in rep.region.landmarks]
        ids = [l.id for l in rep.region.landmarks]
        self.assertEqual(len(set(coords)), len(coords), "duplicate coords")
        self.assertEqual(len(set(ids)), len(ids), "duplicate ids")


class TestBuildoutLandmarks(unittest.TestCase):
    def test_all_twelve_present_at_assigned_coords(self):
        rep = _load()
        by_id = {l.id: l for l in rep.region.landmarks}
        for lid, coord in _NEW.items():
            self.assertIn(lid, by_id, f"missing build-out landmark {lid}")
            self.assertEqual(
                tuple(by_id[lid].coordinates), coord,
                f"{lid} at {by_id[lid].coordinates}, expected {coord}")

    def test_coords_in_bounds(self):
        rep = _load()
        for lid, (x, y) in _NEW.items():
            self.assertTrue(0 <= x < 40 and 0 <= y < 40,
                            f"{lid} coord ({x},{y}) out of 40x40 grid")

    def test_no_invented_property_keys(self):
        rep = _load()
        by_id = {l.id: l for l in rep.region.landmarks}
        for lid in _NEW:
            keys = set(by_id[lid].properties.keys())
            bad = keys - _ALLOWED_PROP_KEYS
            self.assertFalse(
                bad, f"{lid} uses unknown property key(s): {sorted(bad)}")

    def test_buildout_not_force_resonant(self):
        """force_resonant is the shrine's flag; build-out is mundane."""
        rep = _load()
        by_id = {l.id: l for l in rep.region.landmarks}
        for lid in _NEW:
            self.assertNotIn("force_resonant", by_id[lid].properties,
                             f"{lid} wrongly flagged force_resonant")

    def test_buildout_landmarks_have_descriptions(self):
        rep = _load()
        by_id = {l.id: l for l in rep.region.landmarks}
        for lid in _NEW:
            lm = by_id[lid]
            self.assertTrue(lm.description.strip(), f"{lid} empty description")
            self.assertTrue(lm.ambient_lines, f"{lid} no ambient_lines")


class TestEraCleanliness(unittest.TestCase):
    def test_buildout_production_strings_era_clean(self):
        """Era-cleanness governs PRODUCTION strings (what reaches a
        player), not authoring comments — per CLAUDE.md B3, "Comments
        and era-mapping keys are exempt." So scan the loaded landmark
        fields (name/short_desc/description/ambient_lines), which are
        exactly the strings the engine surfaces, rather than raw file
        text (which includes the authors' own B3-documentation comments
        that legitimately name the banned terms to describe avoidance).
        """
        rep = _load()
        by_id = {l.id: l for l in rep.region.landmarks}
        for lid in _NEW:
            lm = by_id[lid]
            blob = " ".join([
                lm.name or "", lm.short_desc or "", lm.description or "",
                " ".join(lm.ambient_lines or []),
            ])
            m = _BANNED.search(blob)
            self.assertIsNone(
                m, f"{lid} production string contains banned era term: "
                   f"{m.group(0) if m else ''}")


if __name__ == "__main__":
    unittest.main()
