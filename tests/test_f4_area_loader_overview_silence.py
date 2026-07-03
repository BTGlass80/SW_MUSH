# -*- coding: utf-8 -*-
"""
tests/test_f4_area_loader_overview_silence.py — F4 boot-noise fix.

Brian's call (quick-decisions drop, 2026-07-03) on
MAP.fable_f4_wilderness_overview_no_areageometry_reconfirmed / TD.FABLE_F4:
`coruscant_underworld` and `tatooine_dune_sea` are wilderness-grid regions
that move landmark-to-landmark and are already served by their own Tier-1b
SPA overview map (data/worlds/clone_wars/maps/<slug>_overview.yaml, consumed
by static/spa/m3_wilderness_overview_data.js) — they were never meant to
have a room-based AreaGeometry. The prior boot-time
"[area_loader] registry: skipping <slug> ... AreaGeometry YAML not found"
WARNING was log noise, not a real failure: SILENCE it (log.debug instead)
for any area whose only backing file is an overview-schema projection,
while a genuinely broken ROOM-based area must still WARNING at boot.

Covers both the real-corpus outcome (no warning for the two live regions,
registry still fully populated) and the isolated-fixture unit contract
(engine.area_loader.load_area_geometry / AreaGeometryRegistry.load_era),
so a regression in either the real data or the loader logic is caught.
"""
from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.area_loader import (  # noqa: E402
    AreaGeometryLoadError,
    AreaGeometryOverviewOnlyError,
    AreaGeometryRegistry,
    load_area_geometry,
)

LOGGER_NAME = "engine.area_loader"


def _write_yaml(d: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)


def _overview_doc(area_key: str) -> dict:
    """Minimal Tier-1b wilderness-overview projection shape (matches
    tools/gen_wilderness_overview.py output: area_key/bounds/terrain_zones/
    routes/landmarks — NO schema_version/rooms/districts/exits)."""
    return {
        "area_key": area_key,
        "display_name": area_key.upper(),
        "bounds": {"x_min": 0, "y_min": 0, "x_max": 700, "y_max": 600},
        "terrain_zones": [],
        "routes": [],
        "landmarks": [],
    }


class TestRealCorpusBootIsSilent(unittest.TestCase):
    """The actual live boot: both wilderness-overview regions must not warn."""

    def test_no_warning_for_wilderness_overview_regions(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            registry = AreaGeometryRegistry.load_era("clone_wars")
        # Confirmed real areas still loaded (registry isn't empty/broken).
        self.assertGreaterEqual(len(registry._areas), 10)
        # Neither wilderness-overview-only region got a room-based entry —
        # they have none authored; they stay on the SPA overview instead.
        self.assertNotIn("coruscant_underworld", registry._areas)
        self.assertNotIn("tatooine_dune_sea", registry._areas)

    def test_wilderness_overview_regions_log_at_debug_not_silence(self):
        # Silenced from WARNING, but still traceable at DEBUG (not a black
        # hole — a real regression in area discovery is still visible).
        with self.assertLogs(LOGGER_NAME, level="DEBUG") as cm:
            AreaGeometryRegistry.load_era("clone_wars")
        joined = "\n".join(cm.output)
        self.assertIn("coruscant_underworld", joined)
        self.assertIn("tatooine_dune_sea", joined)


class TestOverviewOnlyIsolatedFixture(unittest.TestCase):
    """Isolated maps-dir fixtures — general detection, not slug-hardcoded."""

    def setUp(self):
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmpdir_obj.name)
        self.maps_dir = self.tmpdir / "clone_wars" / "maps"
        self.maps_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def test_overview_only_area_skipped_without_warning(self):
        _write_yaml(_overview_doc("wild_region"),
                    self.maps_dir / "wild_region_overview.yaml")
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            registry = AreaGeometryRegistry.load_era(
                "clone_wars", worlds_root=self.tmpdir)
        self.assertNotIn("wild_region", registry._areas)

    def test_genuinely_broken_room_based_area_still_warns(self):
        # area_key present, but no bounds/terrain_zones (not overview-shaped)
        # AND no schema_version/rooms (fails room-based validation too) — a
        # real authoring break, not an expected overview-only region.
        _write_yaml({"area_key": "broken_area", "note": "oops, incomplete"},
                    self.maps_dir / "broken_area.yaml")
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            registry = AreaGeometryRegistry.load_era(
                "clone_wars", worlds_root=self.tmpdir)
        self.assertTrue(
            any("broken_area" in line for line in cm.output),
            f"expected a WARNING naming broken_area, got: {cm.output}")
        self.assertNotIn("broken_area", registry._areas)

    def test_load_area_geometry_raises_overview_only_via_sibling_file(self):
        # <basename>.yaml absent, <basename>_overview.yaml present+overview-
        # shaped: the naming-convention path (the two live regions today).
        _write_yaml(_overview_doc("wild_region"),
                    self.maps_dir / "wild_region_overview.yaml")
        with self.assertRaises(AreaGeometryOverviewOnlyError):
            load_area_geometry("wild_region", "clone_wars",
                                worlds_root=self.tmpdir)

    def test_load_area_geometry_raises_overview_only_at_direct_path_too(self):
        # General detection: even if the overview-shaped content sits AT the
        # exact resolved path (no "_overview" suffix), it's still recognized
        # as overview-only rather than falling through to a validation
        # error — not hardcoded to the naming convention alone.
        _write_yaml(_overview_doc("wild_region"),
                    self.maps_dir / "wild_region.yaml")
        with self.assertRaises(AreaGeometryOverviewOnlyError):
            load_area_geometry("wild_region", "clone_wars",
                                worlds_root=self.tmpdir)

    def test_load_area_geometry_raises_plain_error_with_no_sibling_at_all(self):
        # Genuinely missing, no overview fallback of any kind: must stay a
        # plain AreaGeometryLoadError (still warns upstream in the registry).
        with self.assertRaises(AreaGeometryLoadError) as cm:
            load_area_geometry("nowhere_at_all", "clone_wars",
                                worlds_root=self.tmpdir)
        self.assertNotIsInstance(cm.exception, AreaGeometryOverviewOnlyError)


if __name__ == "__main__":
    unittest.main()
