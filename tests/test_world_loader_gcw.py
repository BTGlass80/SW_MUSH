# -*- coding: utf-8 -*-
"""
tests/test_world_loader_gcw.py — Drop 2 of Priority F.0.

Verifies that the YAML-extracted GCW world (data/worlds/gcw/) is
equivalent to the hardcoded world in build_mos_eisley.py. This is the
regression-proof artifact that gates Drop 3 (DB writer cutover): once
this passes, Drop 3 can replace the hardcoded build_mos_eisley.py
build path with the load_world_dry_run() bundle and trust that the
runtime DB will be byte-equivalent.

What we verify:
  - load_world_dry_run('gcw') succeeds (no WorldLoadError, 0 errors).
  - Room count, exit count, zone count match the source.
  - Every room ID in ROOMS appears in the loaded world with the same
    display name and the same zone assignment as ROOM_ZONES.
  - Every (from, to, forward, reverse) tuple in EXITS is represented
    in the loaded exits list (forward and reverse strings preserved).
  - Every zone slug used by ROOM_ZONES exists as a Zone in the
    loaded world.
  - Map coordinates from MAP_COORDS flow through unchanged for
    a representative sample.

What we deliberately do NOT verify in this drop:
  - PLANET_NPCS extraction (deferred to Drop 2b).
  - HIREABLE_CREW / SHIPS extraction (out of F.0 scope; Drop 3+).
  - Housing lots / test characters (deferred per design v1 §6.3).
  - Properties dict equivalence (we check existence; structural
    diff is Drop 3 work where the DB-write path actually consumes them).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module")
def gcw_bundle():
    """Loaded GCW world — the YAML side of the equivalence."""
    from engine.world_loader import load_world_dry_run
    return load_world_dry_run("gcw")


@pytest.fixture(scope="module")
def source_world():
    """The Python-literal side of the equivalence: build_mos_eisley.

    Returns the imported module object so tests can pull ROOMS / EXITS
    / ROOM_ZONES / ROOM_OVERRIDES directly.
    """
    return importlib.import_module("build_mos_eisley")


# ─────────────────────────────────────────────────────────────────────────────
# Loader smoke
# ─────────────────────────────────────────────────────────────────────────────


class TestLoaderSmoke:
    """Drop 1 of F.0 already covers the loader's parse/validate
    contract for clone_wars; these confirm the GCW dry-run path works
    once Drop 2 has populated the YAML."""

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
# Room / exit / zone equivalence vs build_mos_eisley.py
# ─────────────────────────────────────────────────────────────────────────────


class TestRoomEquivalence:
    def test_room_count(self, gcw_bundle, source_world):
        assert len(gcw_bundle.rooms) == len(source_world.ROOMS)
        assert len(gcw_bundle.rooms) == 120

    def test_every_source_room_id_present(self, gcw_bundle, source_world):
        loaded_ids = set(gcw_bundle.rooms.keys())
        expected_ids = set(range(len(source_world.ROOMS)))
        missing = expected_ids - loaded_ids
        extra = loaded_ids - expected_ids
        assert not missing, f"Missing room IDs: {sorted(missing)[:10]}"
        assert not extra,   f"Unexpected room IDs: {sorted(extra)[:10]}"

    def test_room_names_match_source(self, gcw_bundle, source_world):
        for i, (name, _short, _long) in enumerate(source_world.ROOMS):
            r = gcw_bundle.rooms[i]
            assert r.name == name, (
                f"Room {i} name mismatch: source={name!r}, loaded={r.name!r}"
            )

    def test_room_zones_match_source(self, gcw_bundle, source_world):
        for room_id, zone_slug in source_world.ROOM_ZONES.items():
            r = gcw_bundle.rooms[room_id]
            assert r.zone == zone_slug, (
                f"Room {room_id} zone mismatch: "
                f"source={zone_slug!r}, loaded={r.zone!r}"
            )

    def test_room_slugs_unique(self, gcw_bundle):
        slugs = [r.slug for r in gcw_bundle.rooms.values()]
        assert len(slugs) == len(set(slugs)), (
            "Duplicate room slugs detected: "
            + str([s for s in slugs if slugs.count(s) > 1][:5])
        )

    def test_room_descriptions_preserved(self, gcw_bundle, source_world):
        # `description` (long_desc) goes through a YAML folded scalar
        # which collapses runs of whitespace. Compare on whitespace-
        # collapsed forms so we catch missing-text bugs without
        # tripping on the YAML formatter's choices.
        for i, (_name, _short, long_) in enumerate(source_world.ROOMS):
            loaded = " ".join(gcw_bundle.rooms[i].description.split())
            expected = " ".join(long_.split())
            assert loaded == expected, (
                f"Room {i} description mismatch.\n"
                f"  expected: {expected[:80]!r}…\n"
                f"  loaded:   {loaded[:80]!r}…"
            )

    def test_room_short_desc_preserved(self, gcw_bundle, source_world):
        for i, (_name, short, _long) in enumerate(source_world.ROOMS):
            assert gcw_bundle.rooms[i].short_desc == short, (
                f"Room {i} short_desc mismatch"
            )


class TestExitEquivalence:
    def test_exit_count(self, gcw_bundle, source_world):
        # Each EXIT tuple in source becomes ONE entry in the YAML
        # (carrying both forward and reverse). The loader returns
        # them as a flat list — same count.
        assert len(gcw_bundle.exits) == len(source_world.EXITS)
        assert len(gcw_bundle.exits) == 120

    def test_every_source_exit_present(self, gcw_bundle, source_world):
        loaded = {(e.from_id, e.to_id, e.forward, e.reverse)
                  for e in gcw_bundle.exits}
        expected = set(source_world.EXITS)
        missing = expected - loaded
        extra = loaded - expected
        assert not missing, (
            f"Missing exits ({len(missing)}): " +
            ", ".join(repr(m) for m in list(missing)[:5])
        )
        assert not extra, (
            f"Unexpected exits ({len(extra)}): " +
            ", ".join(repr(m) for m in list(extra)[:5])
        )


class TestZoneEquivalence:
    def test_zone_count_matches_source(self, gcw_bundle, source_world):
        # build_mos_eisley creates 20 zones (1 Tatooine parent + 7
        # Tatooine children + wastes + 4 NS + 3 Kessel + 5 Corellia).
        assert len(gcw_bundle.zones) == 20

    def test_every_room_zone_slug_exists(self, gcw_bundle, source_world):
        for room_id, zone_slug in source_world.ROOM_ZONES.items():
            assert zone_slug in gcw_bundle.zones, (
                f"Room {room_id} references zone {zone_slug!r} which is "
                f"not defined in zones.yaml"
            )

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


class TestMapCoordsPreserved:
    def test_sample_map_coords_flow_through(self, gcw_bundle):
        # Spot-check coordinates for the well-known anchor rooms. The
        # build_mos_eisley source uses normalized 0..1 floats; the
        # loader passes them through as-is (the dataclass field is
        # typed Optional[int] but Python doesn't enforce annotations,
        # and the CW data uses integers in the same field — both
        # work). If we ever decide to coerce/scale, this test surfaces
        # the change.
        # Anchors picked from build_mos_eisley.py MAP_COORDS:
        anchors = {
            0:   (0.15, 0.48),    # Docking Bay 94 - Entrance
            8:   (0.45, 0.40),    # Market District (biggest Tatooine hub)
        }
        for room_id, (mx, my) in anchors.items():
            r = gcw_bundle.rooms[room_id]
            assert r.map_x == pytest.approx(mx, abs=1e-6), (
                f"Room {room_id} map_x: expected {mx}, got {r.map_x}"
            )
            assert r.map_y == pytest.approx(my, abs=1e-6), (
                f"Room {room_id} map_y: expected {my}, got {r.map_y}"
            )

    def test_map_coords_present_for_all_rooms(self, gcw_bundle, source_world):
        # MAP_COORDS in build_mos_eisley.py covers all 120 rooms, so the
        # loaded world should have map_x/map_y populated for every room.
        # If a future world adds rooms without coords, this test will
        # surface the gap.
        # We reuse the extractor's MAP_COORDS parse so the test stays
        # honest about what the source actually claims.
        from tools.extract_gcw_world import _extract_map_coords
        src_text = (REPO_ROOT / "build_mos_eisley.py").read_text(encoding="utf-8")
        coords = _extract_map_coords(src_text)
        for room_id in coords.keys():
            r = gcw_bundle.rooms[room_id]
            assert r.map_x is not None, f"Room {room_id} missing map_x"
            assert r.map_y is not None, f"Room {room_id} missing map_y"


# ─────────────────────────────────────────────────────────────────────────────
# Per-planet sanity: the binning by zone slug should match design intent
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
        # If one ever shows up here, the extractor would have caught
        # it — but we keep this as a regression guard.
        for e in gcw_bundle.exits:
            from_planet = gcw_bundle.rooms[e.from_id].planet
            to_planet = gcw_bundle.rooms[e.to_id].planet
            assert from_planet == to_planet, (
                f"Cross-planet exit: {e.from_id} ({from_planet}) -> "
                f"{e.to_id} ({to_planet})"
            )
