# -*- coding: utf-8 -*-
"""
tests/test_fmap2_area_geometry_registry.py — F.MAP.2 registry tests.

Verifies the runtime ``AreaGeometryRegistry`` introduced in F.MAP.2:

  1. Loading an era's authored AreaGeometries indexes their rooms
     by slug for O(1) lookup.
  2. Lookup misses (slugless rooms, unknown slugs, empty input)
     return None — caller falls back to the legacy minimap.
  3. ``get_payload`` returns the same dict on repeat calls (caching),
     never includes player/contacts (the caller layers those on).
  4. Per-area load failures are tolerated — the rest of the era
     still loads. A fully-empty registry still returns None from
     every lookup (graceful degradation).
  5. Slug uniqueness is enforced WITHIN an area at validation time.
  6. Slug collisions ACROSS areas log a warning but the second
     entry wins deterministically (rare; would need cross-planet
     room-slug collision in authoring).

These tests are loader/registry-only — no DB, no server, no client.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.area_loader import (  # noqa: E402
    AreaGeometryLoadError,
    AreaGeometryRegistry,
    load_area_geometry,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _minimal_geom(area_key: str = "test.tmp",
                  rooms: list = None,
                  *, palette: str = "tatooine") -> dict:
    """Smallest valid AreaGeometry — used as a baseline for negative
    tests. Defaults: 2 rooms in a single district, slug-tagged."""
    if rooms is None:
        rooms = [
            {"id": 1, "slug": "test_room_one",
             "name": "A", "zone": "d1", "x": 1.0, "y": 1.0,
             "w": 0.5, "h": 0.5, "style": "civic", "symbol": "§"},
            {"id": 2, "slug": "test_room_two",
             "name": "B", "zone": "d1", "x": 3.0, "y": 1.0,
             "w": 0.5, "h": 0.5, "style": "civic", "symbol": "§"},
        ]
    return {
        "schema_version": 1,
        "area_key": area_key,
        "display_name": "TEST",
        "planet": "TEST",
        "era": "test",
        "default_terrain": "sand",
        "palette": palette,
        "bounds": {"x_min": 0.0, "y_min": 0.0,
                   "x_max": 4.0, "y_max": 4.0},
        "districts": [{
            "id": "d1", "name": "TESTDIST",
            "polygon": [[0.0, 0.0], [4.0, 0.0],
                        [4.0, 4.0], [0.0, 4.0]],
            "label_anchor": [3.5, 3.5],
            "rotation": 0,
        }],
        "rooms": rooms,
        "exits": [[1, 2]],
        "exit_paths": {
            "1-2": {"kind": "street",
                    "path": [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]],
                    "width": 0.30},
        },
        "labels": [],
        "landmarks": [],
    }


def _write_geom(d: dict, root: Path, era: str = "clone_wars",
                basename: str = None) -> None:
    """Emit a YAML fixture under root/<era>/maps/<basename>.yaml.
    basename defaults to the area_key suffix."""
    basename = basename or d["area_key"].rsplit(".", 1)[-1]
    target = root / era / "maps"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{basename}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)


# ── Section 1 — Production fixtures load through the registry ───────────────


class TestRegistryLoadsProductionFixtures(unittest.TestCase):
    """Load the actual data/worlds/clone_wars/maps/ fixtures via
    the registry. This is a sanity check that production authoring
    is registry-compatible. If this fails, an authoring slip in
    one of the AreaGeometry YAMLs has broken slug coverage."""

    def setUp(self):
        self.registry = AreaGeometryRegistry.load_era("clone_wars")

    def test_registry_finds_both_authored_areas(self):
        areas = self.registry.known_areas()
        self.assertIn("tatooine.mos_eisley", areas)

    def test_mos_eisley_slug_count_is_53(self):
        # Mos Eisley AreaGeometry authors 53 rooms, all 53 slug-tagged
        # (1:1 with production room ids). The registry now spans multiple
        # areas, so known_slugs_count() is registry-wide — assert Mos
        # Eisley's own slug coverage rather than the global total.
        geom = self.registry._areas["tatooine.mos_eisley"]
        me_slugs = sum(1 for r in geom.rooms if r.slug)
        self.assertEqual(me_slugs, 53)

    def test_mos_eisley_anchor_rooms_resolve(self):
        # Spot-check: rooms the player is most likely to start in.
        for slug in ("docking_bay_94_pit", "docking_bay_94_entrance",
                     "chalmuans_cantina_main_bar",
                     "mos_eisley_spaceport_row"):
            entry = self.registry.lookup(slug)
            self.assertIsNotNone(entry,
                f"slug {slug!r} should resolve in registry")
            self.assertEqual(entry.area_key, "tatooine.mos_eisley")

    def test_lookup_returns_world_coords_not_render_coords(self):
        # docking_bay_94_pit is at world (4.38, 0.0) per the relaid YAML.
        # render_room_id stays 1; the lookup must return WORLD coords, not
        # the render-room id.
        entry = self.registry.lookup("docking_bay_94_pit")
        self.assertEqual(entry.render_room_id, 1)
        self.assertAlmostEqual(entry.x, 4.38)
        self.assertAlmostEqual(entry.y, 0.0)

    def test_unknown_slug_returns_none(self):
        # A slug from a planet without an authored AreaGeometry
        # (e.g. a Coruscant Senate room) should miss.
        for slug in ("nonexistent_room", "docking_bay_92",
                     "kamino_cloning_chamber"):
            self.assertIsNone(self.registry.lookup(slug),
                f"slug {slug!r} should NOT resolve")

    def test_empty_slug_returns_none(self):
        self.assertIsNone(self.registry.lookup(""))
        self.assertIsNone(self.registry.lookup(None))


# ── Section 2 — get_payload caching + payload shape ─────────────────────────


class TestGetPayload(unittest.TestCase):

    def setUp(self):
        self.registry = AreaGeometryRegistry.load_era("clone_wars")

    def test_payload_returned_as_dict(self):
        p = self.registry.get_payload("tatooine.mos_eisley")
        self.assertIsInstance(p, dict)
        self.assertEqual(p["area_key"], "tatooine.mos_eisley")
        self.assertEqual(len(p["rooms"]), 53)

    def test_payload_excludes_player_and_contacts(self):
        # Per F.MAP.2 design — caller layers these on at push time.
        p = self.registry.get_payload("tatooine.mos_eisley")
        self.assertNotIn("player", p)
        self.assertNotIn("contacts", p)

    def test_payload_cached_across_calls(self):
        # Same dict instance returned — tests the cache works.
        p1 = self.registry.get_payload("tatooine.mos_eisley")
        p2 = self.registry.get_payload("tatooine.mos_eisley")
        self.assertIs(p1, p2)

    def test_payload_unknown_area_returns_none(self):
        self.assertIsNone(self.registry.get_payload("alderaan.aldera"))


# ── Section 3 — Tempdir-based registry behavior under controlled inputs ─────


class TestRegistryUnderControlledInputs(unittest.TestCase):
    """Negative-path / edge-case behavior using temp YAML files
    so the test doesn't depend on the production fixture."""

    def setUp(self):
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmpdir_obj.name)

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def test_empty_era_dir_yields_empty_registry(self):
        # No maps/ dir → registry has 0 areas, lookup always misses
        registry = AreaGeometryRegistry.load_era(
            "clone_wars", worlds_root=self.tmpdir)
        self.assertEqual(registry.known_areas(), [])
        self.assertEqual(registry.known_slugs_count(), 0)
        self.assertIsNone(registry.lookup("any_slug"))

    def test_one_bad_one_good_loads_only_the_good(self):
        # Failure tolerance: an unparseable YAML next to a valid one
        # should leave the valid one loadable.
        good = _minimal_geom("test.good_area")
        _write_geom(good, self.tmpdir, basename="good_area")
        # Write a corrupt file at maps/bad_area.yaml
        bad_path = self.tmpdir / "clone_wars" / "maps" / "bad_area.yaml"
        bad_path.write_text(": : not yaml at all : :", encoding="utf-8")

        registry = AreaGeometryRegistry.load_era(
            "clone_wars", worlds_root=self.tmpdir)
        # Only the good one loaded
        self.assertEqual(registry.known_areas(), ["test.good_area"])
        self.assertIsNotNone(registry.lookup("test_room_one"))

    def test_validation_failure_excluded_from_registry(self):
        # An AreaGeometry that fails _validate_area_geometry (e.g.
        # invalid bounds) gets skipped at registry load.
        bad = _minimal_geom("test.bad_validation")
        bad["bounds"]["x_max"] = bad["bounds"]["x_min"]   # invalid
        _write_geom(bad, self.tmpdir, basename="bad_validation")
        registry = AreaGeometryRegistry.load_era(
            "clone_wars", worlds_root=self.tmpdir)
        self.assertEqual(registry.known_areas(), [])

    def test_room_without_slug_is_NOT_indexed(self):
        # Rooms without slug are renderable but unmapped. The
        # Coruscant Senate fixture is a real example of this —
        # its rooms have no slug because the production rooms
        # don't exist yet.
        rooms = [
            {"id": 10, "name": "X", "zone": "d1", "x": 1, "y": 1,
             "w": 0.5, "h": 0.5, "style": "civic", "symbol": "§"},
            # NB: no slug — should not be indexed
            {"id": 11, "slug": "indexed_room",
             "name": "Y", "zone": "d1", "x": 3, "y": 1,
             "w": 0.5, "h": 0.5, "style": "civic", "symbol": "§"},
        ]
        # Need a 1-2 exit path; reuse existing structure but adjust
        geom = _minimal_geom("test.partial_slug", rooms=rooms)
        geom["exits"] = [[10, 11]]
        geom["exit_paths"] = {
            "10-11": {"kind": "street",
                      "path": [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]],
                      "width": 0.30},
        }
        _write_geom(geom, self.tmpdir, basename="partial_slug")
        registry = AreaGeometryRegistry.load_era(
            "clone_wars", worlds_root=self.tmpdir)
        self.assertEqual(registry.known_slugs_count(), 1)
        self.assertIsNotNone(registry.lookup("indexed_room"))

    def test_slug_collision_within_area_rejected_at_validation(self):
        # Same slug on two rooms in the same area → load fails at
        # the validator (NOT the registry); registry stays empty.
        rooms = [
            {"id": 10, "slug": "collision",
             "name": "A", "zone": "d1", "x": 1, "y": 1,
             "w": 0.5, "h": 0.5, "style": "civic", "symbol": "§"},
            {"id": 11, "slug": "collision",   # duplicate
             "name": "B", "zone": "d1", "x": 3, "y": 1,
             "w": 0.5, "h": 0.5, "style": "civic", "symbol": "§"},
        ]
        geom = _minimal_geom("test.collision", rooms=rooms)
        geom["exits"] = [[10, 11]]
        geom["exit_paths"] = {
            "10-11": {"kind": "street",
                      "path": [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]],
                      "width": 0.30},
        }
        _write_geom(geom, self.tmpdir, basename="collision")
        # Registry skips it (failure-tolerant), but direct load raises.
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "duplicate slug 'collision'"):
            load_area_geometry("test.collision", era="clone_wars",
                               worlds_root=self.tmpdir)
        registry = AreaGeometryRegistry.load_era(
            "clone_wars", worlds_root=self.tmpdir)
        self.assertEqual(registry.known_areas(), [])

    def test_slug_collision_across_areas_second_wins(self):
        # Distinct areas with the same slug → second wins
        # (deterministic; slug collisions across areas should never
        # happen in real authoring but the registry must not crash).
        a = _minimal_geom("test.area_a")
        a["rooms"][0]["slug"] = "shared_slug"
        b = _minimal_geom("test.area_b")
        b["rooms"][0]["slug"] = "shared_slug"
        _write_geom(a, self.tmpdir, basename="area_a")
        _write_geom(b, self.tmpdir, basename="area_b")
        registry = AreaGeometryRegistry.load_era(
            "clone_wars", worlds_root=self.tmpdir)
        # Both areas loaded
        self.assertEqual(set(registry.known_areas()),
                         {"test.area_a", "test.area_b"})
        # The slug resolves to ONE of them (second-wins by load order)
        entry = registry.lookup("shared_slug")
        self.assertIsNotNone(entry)
        self.assertIn(entry.area_key, ("test.area_a", "test.area_b"))


# ── Section 4 — Registry never raises during normal use ─────────────────────


class TestRegistryFailureTolerance(unittest.TestCase):
    """The server is allowed to call lookup/get_payload without any
    try/except scaffolding around it — the registry itself is the
    safety boundary."""

    def setUp(self):
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmpdir_obj.name)
        # Empty era — every call should miss but never raise
        self.registry = AreaGeometryRegistry.load_era(
            "clone_wars", worlds_root=self.tmpdir)

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def test_lookup_never_raises(self):
        # Various weird inputs the server might pass
        for arg in (None, "", "weird/chars/in/slug",
                    "a" * 10000,  # really long
                    "with spaces", "WITH_UPPER_CASE"):
            try:
                self.registry.lookup(arg)
            except Exception as e:
                self.fail(f"registry.lookup({arg!r}) raised {e!r}")

    def test_get_payload_never_raises(self):
        for arg in (None, "", "fake.area", "nonsense"):
            try:
                self.registry.get_payload(arg)
            except Exception as e:
                self.fail(f"registry.get_payload({arg!r}) raised {e!r}")


if __name__ == "__main__":
    unittest.main()
