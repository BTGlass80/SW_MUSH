# -*- coding: utf-8 -*-
"""
tests/test_world_loader_gcw.py — GCW YAML world sanity checks.

Originally this file gated Pass A (cutover): it verified that the
YAML-extracted GCW world matched the hardcoded literals in
build_mos_eisley.py byte-for-byte. After Pass A shipped without issues,
Pass B deleted those literals (~1530 lines) and the equivalence harness
became meaningless — there is nothing left to compare against. The
parity tests that depended on `source_world.ROOMS / EXITS / ROOM_ZONES /
MAP_COORDS` were removed in Pass B alongside the literals themselves.

What stays here is the YAML-side sanity that doesn't need a comparison
target:
  - load_world_dry_run('gcw') succeeds (no WorldLoadError, 0 errors).
  - Expected zone slug set is present.
  - Map coordinates are populated for every room.
  - Per-planet room counts match design intent.
  - No cross-planet exits.

These are the invariants the live runtime relies on; they catch
regressions in the YAML itself or the loader's parsing pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module")
def gcw_bundle():
    """Loaded GCW world."""
    from engine.world_loader import load_world_dry_run
    return load_world_dry_run("gcw")


# ─────────────────────────────────────────────────────────────────────────────
# Loader smoke
# ─────────────────────────────────────────────────────────────────────────────


class TestLoaderSmoke:
    """The loader must produce a clean, validated bundle for the GCW era."""

    def test_dry_run_returns_bundle(self, gcw_bundle):
        assert gcw_bundle is not None
        assert gcw_bundle.manifest.era_code == "gcw"

    def test_no_validation_errors(self, gcw_bundle):
        assert gcw_bundle.report.errors == [], (
            "GCW world failed validation: " + "; ".join(gcw_bundle.report.errors)
        )

    def test_only_expected_warnings(self, gcw_bundle):
        # `mos_eisley` is a parent zone with no rooms directly assigned
        # (the children — spaceport, cantina, etc — get the rooms).
        # The validator flags zones-with-no-rooms as a warning, which
        # is correct general behavior but expected here.
        unexpected = [
            w for w in gcw_bundle.report.warnings
            if w != "Zone 'mos_eisley' has no rooms."
        ]
        assert unexpected == [], f"Unexpected GCW warnings: {unexpected}"


# ─────────────────────────────────────────────────────────────────────────────
# Zone-level invariants (no source-world comparison needed)
# ─────────────────────────────────────────────────────────────────────────────


class TestZoneShape:
    """The GCW zone slug set is a known, design-anchored constant."""

    def test_zone_count_is_twenty(self, gcw_bundle):
        # 1 Tatooine parent + 7 Tatooine children + wastes + 4 NS + 3 Kessel
        # + 5 Corellia = 20.
        assert len(gcw_bundle.zones) == 20

    def test_zone_slugs_known_set(self, gcw_bundle):
        expected = {
            # Tatooine
            "mos_eisley", "spaceport", "cantina", "market", "civic",
            "residential", "outskirts", "wastes",
            # Nar Shaddaa
            "ns_landing_pad", "ns_promenade", "ns_undercity", "ns_warrens",
            # Kessel
            "kessel_station", "kessel_mines", "kessel_deep_mines",
            # Corellia
            "coronet_port", "coronet_city", "coronet_gov",
            "coronet_industrial", "coronet_old_quarter",
        }
        loaded = set(gcw_bundle.zones.keys())
        assert loaded == expected, (
            f"Zone slug set mismatch.\n"
            f"  missing: {expected - loaded}\n"
            f"  extra:   {loaded - expected}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Map coordinates — every room should have them
# ─────────────────────────────────────────────────────────────────────────────


class TestMapCoordsPopulated:
    def test_sample_anchor_coords_intact(self, gcw_bundle):
        # Spot-check coordinates for well-known anchor rooms. These
        # values are pinned from the GCW YAML; if a future YAML edit
        # accidentally moves them, this surfaces the change.
        anchors = {
            0: (0.15, 0.48),    # Docking Bay 94 - Entrance
            8: (0.45, 0.40),    # Market District (biggest Tatooine hub)
        }
        for room_id, (mx, my) in anchors.items():
            r = gcw_bundle.rooms[room_id]
            assert r.map_x == pytest.approx(mx, abs=1e-6), (
                f"Room {room_id} map_x: expected {mx}, got {r.map_x}"
            )
            assert r.map_y == pytest.approx(my, abs=1e-6), (
                f"Room {room_id} map_y: expected {my}, got {r.map_y}"
            )

    def test_every_room_has_coords(self, gcw_bundle):
        # The GCW YAML is expected to populate map_x/map_y on every
        # room. If a future room is added without coords, surface the
        # gap immediately.
        missing = [
            r.id for r in gcw_bundle.rooms.values()
            if r.map_x is None or r.map_y is None
        ]
        assert not missing, (
            f"GCW rooms missing map coordinates: {missing[:10]}"
            f"{'…' if len(missing) > 10 else ''}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Per-planet sanity: zone-slug binning matches design intent
# ─────────────────────────────────────────────────────────────────────────────


class TestPlanetSplit:
    def test_tatooine_room_count(self, gcw_bundle):
        n = sum(1 for r in gcw_bundle.rooms.values() if r.planet == "tatooine")
        assert n == 54

    def test_nar_shaddaa_room_count(self, gcw_bundle):
        n = sum(1 for r in gcw_bundle.rooms.values() if r.planet == "nar_shaddaa")
        assert n == 30

    def test_kessel_room_count(self, gcw_bundle):
        n = sum(1 for r in gcw_bundle.rooms.values() if r.planet == "kessel")
        assert n == 12

    def test_corellia_room_count(self, gcw_bundle):
        n = sum(1 for r in gcw_bundle.rooms.values() if r.planet == "corellia")
        assert n == 24

    def test_no_cross_planet_exits(self, gcw_bundle):
        # build_mos_eisley.py never had cross-planet exits at runtime
        # (planet hops happen via the docking-bay → starship flow).
        for e in gcw_bundle.exits:
            from_planet = gcw_bundle.rooms[e.from_id].planet
            to_planet = gcw_bundle.rooms[e.to_id].planet
            assert from_planet == to_planet, (
                f"Cross-planet exit: {e.from_id} ({from_planet}) -> "
                f"{e.to_id} ({to_planet})"
            )
