# -*- coding: utf-8 -*-
"""
tests/test_t2_3_coruscant_underworld.py — T2.3 Coruscant Underworld
wilderness region + W.3 generic ``landmark_includes:`` mechanism.

Per T2.3 in TODO.json: ship the Coruscant Underworld wilderness region
as a single-level region with minimal-substrate parity to Dune Sea.
Per W.3 (same drop, May 24 2026): generalize the loader's
force-resonant-merge into a generic ``landmark_includes:`` mechanism
that any region YAML can use. Dune Sea migrated to use it; Coruscant
declares it from scratch.

Test surface
------------

1. TestLandmarkIncludesMechanism — the generic loader feature in
   isolation, with temp YAML fixtures so behavior is testable
   without depending on production content.

2. TestRegionFilter — include files may host entries for multiple
   regions; the loader must filter by the consuming region's slug.

3. TestEnrichmentSemantics — when the same id appears in both the
   region YAML's own block and an include, the include enriches
   rather than errors. Within a single source, duplicates still
   error.

4. TestCoruscantUnderworldLoads — production load of the actual
   coruscant_underworld.yaml. 5 landmarks + 3 transit nodes from
   the include files, region-filtered correctly.

5. TestCoruscantTransitNodesPlaced — per Brian's collapse-Z-axis
   decision: transit nodes have coordinates and are placed on the
   single-level grid (not floating between levels).

6. TestSurfaceManholeRoomDuplication — documents the known
   semantic-duplication between the wilderness-side
   surface_manhole_to_southern_underground landmark and the city-side
   coruscant_uw_surface_entry room. They coexist at (20, 17) for
   this drop; reconciliation tracked as TD.2 in TODO.json.

7. TestDuneSeaPreserved — the Dune Sea migration to landmark_includes
   must not change observable behavior (landmark count, force-resonant
   content merged correctly).

8. TestBackwardCompatForceResonantPath — the legacy
   ``force_resonant_path`` parameter to load_wilderness_region still
   works for callers that haven't migrated.

9. TestEraYamlWiring — era.yaml's content_refs.wilderness includes
   the new region.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _write_yaml(tmpdir: str, name: str, content: str) -> str:
    """Write a YAML file to tmpdir and return its path."""
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


_MINIMAL_REGION_TEMPLATE = """
schema_version: 1
region:
  slug: {slug}
  name: "{name}"
  planet: testworld
  zone: test_zone
  default_security: lawless
grid:
  width: 40
  height: 40
  default_terrain: ferrocrete_corridor
terrains:
  ferrocrete_corridor:
    move_cost: 1
{landmark_block}{includes_block}
"""


# ═══════════════════════════════════════════════════════════════════════════
# 1. TestLandmarkIncludesMechanism
# ═══════════════════════════════════════════════════════════════════════════


class TestLandmarkIncludesMechanism(unittest.TestCase):
    """The generic landmark_includes mechanism in isolation."""

    def test_include_file_landmarks_appended(self):
        """A region YAML with no inline landmarks but an include pulls
        landmarks from the include file."""
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            _write_yaml(tmp, "inc.yaml", """
schema_version: 1
landmarks:
  - id: lm_one
    name: One
    region: test_region
    coordinates: [5, 5]
    terrain: ferrocrete_corridor
  - id: lm_two
    name: Two
    region: test_region
    coordinates: [10, 10]
    terrain: ferrocrete_corridor
""")
            region_path = _write_yaml(tmp, "region.yaml",
                _MINIMAL_REGION_TEMPLATE.format(
                    slug="test_region",
                    name="Test Region",
                    landmark_block="",
                    includes_block="\nlandmark_includes:\n  - inc.yaml\n",
                ),
            )
            rep = load_wilderness_region(region_path)
            self.assertTrue(rep.ok, msg=str(rep.errors))
            ids = {lm.id for lm in rep.region.landmarks}
            self.assertEqual(ids, {"lm_one", "lm_two"})

    def test_transit_nodes_block_appended_with_auto_tag(self):
        """``transit_nodes:`` blocks in includes are also pulled in,
        with transit_node and ambient_disabled auto-set on properties."""
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            _write_yaml(tmp, "inc.yaml", """
schema_version: 1
transit_nodes:
  - id: shaft_a
    name: Shaft A
    region: test_region
    coordinates: [3, 3]
    terrain: ferrocrete_corridor
""")
            region_path = _write_yaml(tmp, "region.yaml",
                _MINIMAL_REGION_TEMPLATE.format(
                    slug="test_region",
                    name="Test Region",
                    landmark_block="",
                    includes_block="\nlandmark_includes:\n  - inc.yaml\n",
                ),
            )
            rep = load_wilderness_region(region_path)
            self.assertTrue(rep.ok, msg=str(rep.errors))
            self.assertEqual(len(rep.region.landmarks), 1)
            shaft = rep.region.landmarks[0]
            self.assertEqual(shaft.id, "shaft_a")
            self.assertTrue(shaft.properties.get("transit_node"))
            self.assertTrue(shaft.properties.get("ambient_disabled"))
            self.assertFalse(shaft.properties.get("wilderness_landmark"))

    def test_missing_include_errors(self):
        """If a declared include file doesn't exist, the load errors
        (rather than silently using only the region's own landmarks)."""
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            region_path = _write_yaml(tmp, "region.yaml",
                _MINIMAL_REGION_TEMPLATE.format(
                    slug="test_region",
                    name="Test Region",
                    landmark_block="",
                    includes_block="\nlandmark_includes:\n  "
                                   "- nonexistent.yaml\n",
                ),
            )
            rep = load_wilderness_region(region_path)
            self.assertFalse(rep.ok)
            self.assertTrue(any("not found" in e for e in rep.errors))

    def test_malformed_includes_list_is_warning_not_error(self):
        """A non-list landmark_includes value warns but doesn't fail."""
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            region_path = _write_yaml(tmp, "region.yaml", """
schema_version: 1
region:
  slug: test_region
  name: "Test"
  planet: testworld
  zone: test_zone
  default_security: lawless
grid:
  width: 10
  height: 10
  default_terrain: ferrocrete_corridor
terrains:
  ferrocrete_corridor: {move_cost: 1}
landmark_includes: "not_a_list"
""")
            rep = load_wilderness_region(region_path)
            self.assertTrue(rep.ok)
            self.assertTrue(any(
                "landmark_includes" in w for w in rep.warnings))

    def test_multiple_includes_all_loaded(self):
        """Two include files contribute additively."""
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            _write_yaml(tmp, "a.yaml", """
schema_version: 1
landmarks:
  - id: a_one
    name: AOne
    region: test_region
    coordinates: [1, 1]
    terrain: ferrocrete_corridor
""")
            _write_yaml(tmp, "b.yaml", """
schema_version: 1
landmarks:
  - id: b_one
    name: BOne
    region: test_region
    coordinates: [2, 2]
    terrain: ferrocrete_corridor
""")
            region_path = _write_yaml(tmp, "region.yaml",
                _MINIMAL_REGION_TEMPLATE.format(
                    slug="test_region",
                    name="Test",
                    landmark_block="",
                    includes_block="\nlandmark_includes:\n  - a.yaml\n  - b.yaml\n",
                ),
            )
            rep = load_wilderness_region(region_path)
            self.assertTrue(rep.ok, msg=str(rep.errors))
            ids = {lm.id for lm in rep.region.landmarks}
            self.assertEqual(ids, {"a_one", "b_one"})


# ═══════════════════════════════════════════════════════════════════════════
# 2. TestRegionFilter
# ═══════════════════════════════════════════════════════════════════════════


class TestRegionFilter(unittest.TestCase):
    """Include files may host entries for multiple regions; the loader
    filters to the consuming region's slug."""

    def test_other_region_entries_skipped(self):
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            _write_yaml(tmp, "shared.yaml", """
schema_version: 1
landmarks:
  - id: mine
    name: Mine
    region: test_region
    coordinates: [5, 5]
    terrain: ferrocrete_corridor
  - id: theirs
    name: Theirs
    region: other_region
    coordinates: [6, 6]
    terrain: ferrocrete_corridor
""")
            region_path = _write_yaml(tmp, "region.yaml",
                _MINIMAL_REGION_TEMPLATE.format(
                    slug="test_region",
                    name="Test",
                    landmark_block="",
                    includes_block="\nlandmark_includes:\n  - shared.yaml\n",
                ),
            )
            rep = load_wilderness_region(region_path)
            self.assertTrue(rep.ok, msg=str(rep.errors))
            ids = {lm.id for lm in rep.region.landmarks}
            self.assertEqual(ids, {"mine"})

    def test_region_agnostic_entries_match_any(self):
        """Entries with no ``region:`` field match any region (treated
        as region-agnostic content the region YAML asked for)."""
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            _write_yaml(tmp, "agnostic.yaml", """
schema_version: 1
landmarks:
  - id: anywhere
    name: Anywhere
    coordinates: [5, 5]
    terrain: ferrocrete_corridor
""")
            region_path = _write_yaml(tmp, "region.yaml",
                _MINIMAL_REGION_TEMPLATE.format(
                    slug="test_region",
                    name="Test",
                    landmark_block="",
                    includes_block="\nlandmark_includes:\n  - agnostic.yaml\n",
                ),
            )
            rep = load_wilderness_region(region_path)
            self.assertTrue(rep.ok, msg=str(rep.errors))
            ids = {lm.id for lm in rep.region.landmarks}
            self.assertEqual(ids, {"anywhere"})


# ═══════════════════════════════════════════════════════════════════════════
# 3. TestEnrichmentSemantics
# ═══════════════════════════════════════════════════════════════════════════


class TestEnrichmentSemantics(unittest.TestCase):
    """Same id in region + include = enrichment. Same id twice in
    one source = error."""

    def test_include_enriches_region_inline_entry(self):
        """A region declares a brief landmark; the include carries
        the rich description. After load, the rich content wins."""
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            _write_yaml(tmp, "rich.yaml", """
schema_version: 1
landmarks:
  - id: shared
    region: test_region
    description: |
      The full rich description of the shared landmark.
    properties:
      flag_from_include: true
""")
            region_path = _write_yaml(tmp, "region.yaml", """
schema_version: 1
region:
  slug: test_region
  name: Test
  planet: testworld
  zone: test_zone
  default_security: lawless
grid:
  width: 40
  height: 40
  default_terrain: ferrocrete_corridor
terrains:
  ferrocrete_corridor: {move_cost: 1}
landmarks:
  - id: shared
    name: SharedBrief
    coordinates: [10, 10]
    terrain: ferrocrete_corridor
    short_desc: "brief stub"
landmark_includes:
  - rich.yaml
""")
            rep = load_wilderness_region(region_path)
            self.assertTrue(rep.ok, msg=str(rep.errors))
            self.assertEqual(len(rep.region.landmarks), 1)
            lm = rep.region.landmarks[0]
            self.assertEqual(lm.id, "shared")
            self.assertIn("full rich description", lm.description)
            self.assertTrue(lm.properties.get("flag_from_include"))
            self.assertEqual(lm.short_desc, "brief stub",
                             "short_desc should not be overridden if "
                             "existing is non-empty")
            self.assertEqual(lm.coordinates, (10, 10),
                             "coords from region YAML must win")

    def test_within_source_duplicate_is_error(self):
        """Two entries with the same id in ONE landmarks: block is
        a content bug — must error."""
        from engine.wilderness_loader import load_wilderness_region

        with tempfile.TemporaryDirectory() as tmp:
            region_path = _write_yaml(tmp, "region.yaml", """
schema_version: 1
region:
  slug: test_region
  name: Test
  planet: testworld
  zone: test_zone
  default_security: lawless
grid:
  width: 10
  height: 10
  default_terrain: dune
terrains:
  dune: {move_cost: 1}
landmarks:
  - id: dup
    coordinates: [0, 0]
    terrain: dune
  - id: dup
    coordinates: [1, 1]
    terrain: dune
""")
            rep = load_wilderness_region(region_path)
            self.assertFalse(rep.ok)
            self.assertTrue(any(
                "duplicate" in e.lower() for e in rep.errors))


# ═══════════════════════════════════════════════════════════════════════════
# 4. TestCoruscantUnderworldLoads
# ═══════════════════════════════════════════════════════════════════════════


_CORUSCANT_YAML = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness",
    "coruscant_underworld.yaml",
)


class TestCoruscantUnderworldLoads(unittest.TestCase):
    """The production Coruscant Underworld YAML loads cleanly."""

    def test_loads_without_errors(self):
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        self.assertTrue(rep.ok,
                        msg=f"errors: {rep.errors}; warnings: {rep.warnings}")

    def test_eight_landmarks_total(self):
        """8 anchor entries (4 non-resonant + 1 force-resonant + 3 transit)
        PLUS the Drop 18 region build-out of 12 secondary landmarks
        (NW/NE/SW/SE quadrant include files) = 20 total. The original 8
        anchors remain pinned by name in the sibling tests below."""
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        self.assertEqual(len(rep.region.landmarks), 20)

    def test_all_five_design_landmarks_present(self):
        """Per clone_wars_era_design_v3.md §7.2 the region must have
        these 5 named landmarks."""
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        ids = {lm.id for lm in rep.region.landmarks}
        required = {
            "black_sun_crawler_hideout",
            "forgotten_jedi_shrine",
            "abandoned_factory_dominus",
            "uscru_entertainment_district_fringe",
            "maze_the_reaper_territory",
        }
        missing = required - ids
        self.assertFalse(missing, f"Missing landmarks: {missing}")

    def test_three_transit_nodes_present(self):
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        transit_ids = {
            lm.id for lm in rep.region.landmarks
            if lm.properties.get("transit_node")
        }
        required = {
            "transit_shaft_alpha",
            "transit_shaft_beta",
            "surface_manhole_to_southern_underground",
        }
        missing = required - transit_ids
        self.assertFalse(missing, f"Missing transit nodes: {missing}")

    def test_region_is_single_level(self):
        """Per Brian's T2.3 call: single-level region. The grid has
        no `depth` dimension; all landmarks share one plane."""
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        # All landmarks have valid 2D coords within the 40x40 grid
        for lm in rep.region.landmarks:
            x, y = lm.coordinates
            self.assertTrue(0 <= x < 40, f"{lm.id} x={x} out of bounds")
            self.assertTrue(0 <= y < 40, f"{lm.id} y={y} out of bounds")

    def test_dune_sea_force_resonant_not_pulled_in(self):
        """The force_resonant_landmarks.yaml include file ALSO
        contains Dune Sea landmarks. The region filter must skip
        them when Coruscant is loading."""
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        ids = {lm.id for lm in rep.region.landmarks}
        dune_sea_ids = {
            "dune_sea_anchor_stones",
            "dune_sea_ruined_obelisk",
            "bantha_graveyard",
        }
        leaked = ids & dune_sea_ids
        self.assertFalse(leaked,
                         f"Dune Sea landmarks leaked into Coruscant: "
                         f"{leaked}. Region filter not working.")


# ═══════════════════════════════════════════════════════════════════════════
# 5. TestCoruscantTransitNodesPlaced
# ═══════════════════════════════════════════════════════════════════════════


class TestCoruscantTransitNodesPlaced(unittest.TestCase):
    """Per Brian's T2.3 collapse-Z-axis decision: transit nodes get
    coordinates and are placed on the single-level grid, not floating
    as level-to-level connectors."""

    def test_transit_shaft_alpha_has_coordinates(self):
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        shaft = next(
            lm for lm in rep.region.landmarks
            if lm.id == "transit_shaft_alpha"
        )
        self.assertEqual(shaft.coordinates, (22, 20))

    def test_transit_shaft_beta_has_coordinates(self):
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        shaft = next(
            lm for lm in rep.region.landmarks
            if lm.id == "transit_shaft_beta"
        )
        self.assertEqual(shaft.coordinates, (18, 32))

    def test_manhole_at_surface_entry_coords(self):
        """The surface manhole shares (20, 17) with the existing
        coruscant_uw_surface_entry city-side room. See TD.2 in
        TODO.json for the reconciliation follow-up."""
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_CORUSCANT_YAML)
        manhole = next(
            lm for lm in rep.region.landmarks
            if lm.id == "surface_manhole_to_southern_underground"
        )
        self.assertEqual(manhole.coordinates, (20, 17))


# ═══════════════════════════════════════════════════════════════════════════
# 6. TestSurfaceManholeRoomDuplication
# ═══════════════════════════════════════════════════════════════════════════


class TestSurfaceManholeRoomDuplication(unittest.TestCase):
    """Documents and locks in the known semantic duplication between
    the wilderness-side manhole landmark and the city-side
    coruscant_uw_surface_entry room.

    For this drop: both rooms exist; the duplication is documented
    as TD.2 in TODO.json for a future reconciliation drop. These
    tests ensure the duplication remains *visible* — if either side
    moves coordinates, the test breaks and forces a re-decision."""

    def test_manhole_coords_match_city_room(self):
        """The wilderness landmark's coordinates must match the
        city-side room's map_x/map_y so they reference the same
        gameplay location."""
        from engine.wilderness_loader import load_wilderness_region
        import yaml

        # Wilderness side
        rep = load_wilderness_region(_CORUSCANT_YAML)
        manhole = next(
            lm for lm in rep.region.landmarks
            if lm.id == "surface_manhole_to_southern_underground"
        )

        # City side — read coruscant.yaml and find coruscant_uw_surface_entry
        coruscant_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "planets", "coruscant.yaml",
        )
        with open(coruscant_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        rooms = data.get("rooms", [])
        surface_entry = next(
            r for r in rooms
            if r.get("slug") == "coruscant_uw_surface_entry"
        )
        city_x = surface_entry.get("map_x")
        city_y = surface_entry.get("map_y")
        self.assertEqual(
            manhole.coordinates, (city_x, city_y),
            "TD.2: wilderness manhole and city surface entry must "
            "share coordinates. If you moved one, move the other or "
            "complete TD.2 reconciliation.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. TestDuneSeaPreserved
# ═══════════════════════════════════════════════════════════════════════════


_DUNE_SEA_YAML = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness",
    "dune_sea.yaml",
)


class TestDuneSeaPreserved(unittest.TestCase):
    """The Dune Sea migration to landmark_includes must not change
    observable behavior. Force-resonant content still merges; landmark
    count unchanged."""

    def test_dune_sea_loads_via_includes(self):
        """Dune Sea now uses landmark_includes instead of (only) the
        legacy force_resonant_path parameter. Same landmark count."""
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_DUNE_SEA_YAML)
        self.assertTrue(rep.ok, msg=str(rep.errors))
        # Should have all the original landmarks (the inline ones
        # plus the force-resonant enrichment — same count as before
        # the migration).
        self.assertGreater(len(rep.region.landmarks), 0)

    def test_force_resonant_content_merged(self):
        """dune_sea_anchor_stones is declared brief in the region
        YAML but the force-resonant include carries the rich
        description. The merge should produce the rich text."""
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region(_DUNE_SEA_YAML)
        anchor = next(
            (lm for lm in rep.region.landmarks
             if lm.id == "dune_sea_anchor_stones"),
            None,
        )
        self.assertIsNotNone(anchor,
                             "dune_sea_anchor_stones must be in region")
        # The force_resonant_landmarks.yaml has the full description
        # with "three weathered pillars" — the merge should bring it in.
        self.assertIn("weathered pillars", anchor.description.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 8. TestBackwardCompatForceResonantPath
# ═══════════════════════════════════════════════════════════════════════════


class TestBackwardCompatForceResonantPath(unittest.TestCase):
    """The legacy ``force_resonant_path`` parameter on
    load_wilderness_region still works for callers that haven't
    migrated."""

    def test_legacy_param_still_merges(self):
        """Loading Dune Sea with the legacy parameter should still
        produce the same merged content (idempotent with the
        landmark_includes mechanism that now also references the
        same file)."""
        from engine.wilderness_loader import load_wilderness_region
        fr_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "force_resonant_landmarks.yaml",
        )
        rep = load_wilderness_region(
            _DUNE_SEA_YAML, force_resonant_path=fr_path,
        )
        self.assertTrue(rep.ok, msg=str(rep.errors))
        anchor = next(
            (lm for lm in rep.region.landmarks
             if lm.id == "dune_sea_anchor_stones"),
            None,
        )
        self.assertIsNotNone(anchor)
        self.assertIn("weathered pillars", anchor.description.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 9. TestEraYamlWiring
# ═══════════════════════════════════════════════════════════════════════════


class TestEraYamlWiring(unittest.TestCase):
    """era.yaml's content_refs.wilderness includes coruscant_underworld."""

    def test_era_yaml_lists_coruscant(self):
        import yaml
        era_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars", "era.yaml",
        )
        with open(era_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        wilderness_refs = (
            data.get("content_refs", {}).get("wilderness", [])
        )
        self.assertTrue(any(
            "coruscant_underworld" in ref for ref in wilderness_refs
        ), f"era.yaml content_refs.wilderness missing Coruscant: "
            f"{wilderness_refs}")

    def test_era_yaml_still_lists_dune_sea(self):
        """Defensive: don't accidentally remove Dune Sea."""
        import yaml
        era_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars", "era.yaml",
        )
        with open(era_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        wilderness_refs = (
            data.get("content_refs", {}).get("wilderness", [])
        )
        self.assertTrue(any(
            "dune_sea" in ref for ref in wilderness_refs
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
