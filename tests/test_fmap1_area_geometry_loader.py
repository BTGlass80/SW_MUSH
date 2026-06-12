# -*- coding: utf-8 -*-
"""
tests/test_fmap1_area_geometry_loader.py — F.MAP.1 area_loader tests.

Verifies that:

  1. The Mos Eisley fixture loads cleanly and round-trips into a
     dict shape that matches the design contract one-for-one (room
     count, district count, exit_path count, label count, landmark
     count).
  2. The Coruscant Senate fixture (the palette-swap demo) also loads
     cleanly — proving the loader isn't Mos-Eisley-specific.
  3. discover_area_keys() finds both authored fixtures.
  4. The validator rejects each of the structural failure modes
     enumerated in engine/area_loader.py::_validate_area_geometry —
     so authoring slips fail loudly at load time, not at render
     time in the browser.
  5. The dataclass shape matches the JS prototype's AreaGeometry
     keys exactly (no drift between server and client contracts).
  6. Specific authoring rules from the design handoff README's
     "Recent fixes" section are enforced, especially the
     landmarks-co-located-with-rooms rule (must have min_zoom >= 2).

These are loader-only tests — no network, no DB, no browser.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

# Path setup so this test file runs both via `pytest tests/` and standalone.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.area_loader import (  # noqa: E402
    AreaGeometry,
    AreaGeometryLoadError,
    District,
    ExitPath,
    Landmark,
    MapBounds,
    MapLabel,
    MapRoom,
    discover_area_keys,
    load_area_geometry,
)


MAPS_DIR = ROOT / "data" / "worlds" / "clone_wars" / "maps"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _write_yaml(d: dict, dirpath: Path) -> Path:
    """Write a temporary AreaGeometry YAML for negative-path tests."""
    p = dirpath / "tmp.yaml"
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
    return p


def _minimal_valid_geom() -> dict:
    """The smallest possible valid AreaGeometry — used as a baseline
    that negative-path tests mutate one field at a time."""
    return {
        "schema_version": 1,
        "area_key": "test.tmp",
        "display_name": "TEST",
        "planet": "TEST",
        "era": "test",
        "default_terrain": "sand",
        "palette": "tatooine",
        "bounds": {"x_min": 0.0, "y_min": 0.0,
                   "x_max": 4.0, "y_max": 4.0},
        "districts": [{
            "id": "d1", "name": "TESTDIST",
            "polygon": [[0.0, 0.0], [4.0, 0.0],
                        [4.0, 4.0], [0.0, 4.0]],
            "label_anchor": [3.5, 3.5],
            "rotation": 0,
        }],
        "rooms": [
            {"id": 1, "name": "A", "zone": "d1", "x": 1.0, "y": 1.0,
             "w": 0.5, "h": 0.5, "style": "civic", "symbol": "§"},
            {"id": 2, "name": "B", "zone": "d1", "x": 3.0, "y": 1.0,
             "w": 0.5, "h": 0.5, "style": "civic", "symbol": "§"},
        ],
        "exits": [[1, 2]],
        "exit_paths": {
            "1-2": {"kind": "street",
                    "path": [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]],
                    "width": 0.30},
        },
        "labels": [
            {"text": "STREET", "kind": "street", "path_id": "1-2",
             "t": 0.5, "size": 8, "min_zoom": 1, "max_zoom": 2},
        ],
        "landmarks": [
            {"id": "lm", "icon": "beacon", "name": "Beacon",
             "pos": [2.0, 3.0], "min_zoom": 1, "max_zoom": 3},
        ],
    }


# ── Section 1 — Mos Eisley fixture loads and matches the design contract ───


class TestMosEisleyFixtureLoads(unittest.TestCase):
    """The Mos Eisley YAML must load without error and produce
    counts that match design_handoff_datapad_map/reference/data/mos-eisley.js
    one-for-one. If this test fails, somebody touched the YAML and broke
    parity with the JS prototype."""

    def setUp(self):
        self.geom = load_area_geometry("tatooine.mos_eisley")

    def test_top_level_metadata(self):
        self.assertEqual(self.geom.area_key, "tatooine.mos_eisley")
        self.assertEqual(self.geom.display_name, "MOS EISLEY")
        self.assertEqual(self.geom.planet, "TATOOINE")
        self.assertEqual(self.geom.palette, "tatooine")
        self.assertEqual(self.geom.schema_version, 1)
        self.assertEqual(self.geom.default_terrain, "sand")

    def test_bounds_match_prototype(self):
        # Rebased for the v51 hybrid-raster relayout (mos_eisley_substrate.png):
        # room positions were re-laid to the painted substrate, widening bounds.
        b = self.geom.bounds
        self.assertEqual((b.x_min, b.y_min, b.x_max, b.y_max),
                         (0.88, -3.26, 13.73, 9.03))

    def test_room_count_matches_prototype(self):
        # mos-eisley.js authors exactly 53 rooms.
        self.assertEqual(len(self.geom.rooms), 53)

    def test_district_count_matches_prototype(self):
        # 7 districts: spaceport, market, cantina, civic,
        # outskirts, jundland, dune_sea.
        self.assertEqual(len(self.geom.districts), 7)
        ids = {d.id for d in self.geom.districts}
        self.assertEqual(ids, {"spaceport", "market", "cantina", "civic",
                               "outskirts", "jundland", "dune_sea"})

    def test_exit_path_count_matches_prototype(self):
        # Rebased for the v51 substrate relayout: with a substrate_image, the
        # client skips the procedural street layer (streets are baked into the
        # painting), so Mos Eisley no longer authors named exit_paths.
        self.assertEqual(len(self.geom.exit_paths), 0)

    def test_label_count_matches_prototype(self):
        # Rebased for the v51 substrate relayout: street labels are baked into
        # the painting, leaving only the 2 flavor labels as SVG overlays.
        self.assertEqual(len(self.geom.labels), 2)
        kinds = [l.kind for l in self.geom.labels]
        self.assertEqual(kinds.count("street"), 0)
        self.assertEqual(kinds.count("flavor"), 2)

    def test_landmark_count_matches_prototype(self):
        # 9 landmarks: dowager, jabba_th, chalmun, bay94, despot,
        # kraytgrave, jabba_p, sarlacc, beacon
        self.assertEqual(len(self.geom.landmarks), 9)
        ids = {lm.id for lm in self.geom.landmarks}
        self.assertEqual(ids, {"dowager", "jabba_th", "chalmun", "bay94",
                               "despot", "kraytgrave", "jabba_p", "sarlacc",
                               "beacon"})

    def test_hidden_exit_authored(self):
        # mos-eisley.js has exactly one hidden exit (52 → 48).
        hidden = [e for e in self.geom.exits
                  if isinstance(e, dict) and e.get("hidden")]
        self.assertEqual(len(hidden), 1)
        self.assertEqual({hidden[0]["from"], hidden[0]["to"]}, {52, 48})

    def test_landmarks_at_room_coords_have_min_zoom_2(self):
        """Per README "Recent fixes" #1 — landmarks that share a room's
        coords must have min_zoom >= 2 to avoid double-stamping at tier-1.
        The validator catches violations; this test asserts the fixture
        is authored cleanly."""
        room_coords = {(round(r.x, 4), round(r.y, 4)) for r in self.geom.rooms}
        for lm in self.geom.landmarks:
            coord = (round(lm.pos[0], 4), round(lm.pos[1], 4))
            if coord in room_coords:
                self.assertGreaterEqual(
                    lm.min_zoom, 2,
                    f"landmark {lm.id!r} at {coord} shares coords with a "
                    f"room but has min_zoom={lm.min_zoom}; must be >= 2",
                )


# ── Section 2 — Coruscant Senate fixture (palette swap demo) ────────────────


class TestSenateFixtureLoads(unittest.TestCase):
    """Loading a SECOND area validates the loader isn't accidentally
    Mos-Eisley-specific. Per architecture v41 §3.6 step 6 of the impl
    order: 'port one more area to validate the data shape isn't
    Mos-Eisley-specific.'"""

    def setUp(self):
        self.geom = load_area_geometry("coruscant.senate_district")

    def test_senate_loads_with_coruscant_palette(self):
        self.assertEqual(self.geom.area_key, "coruscant.senate_district")
        self.assertEqual(self.geom.palette, "senate_district")
        self.assertEqual(self.geom.planet, "CORUSCANT")

    def test_senate_has_some_rooms_and_districts(self):
        self.assertGreater(len(self.geom.rooms), 0)
        self.assertGreater(len(self.geom.districts), 0)

    def test_senate_room_ids_dont_collide_with_mos_eisley(self):
        """Different areas use disjoint id ranges. Mos Eisley uses 0–53;
        Senate uses 100–124. If this drifts the renderer is fine but
        the live wire-up gets confused (server uses room.id as the
        cross-area key)."""
        mos = load_area_geometry("tatooine.mos_eisley")
        mos_ids = {r.id for r in mos.rooms}
        sen_ids = {r.id for r in self.geom.rooms}
        self.assertEqual(mos_ids & sen_ids, set(),
                         "Mos Eisley and Senate room ids overlap")


# ── Section 3 — discover_area_keys ──────────────────────────────────────────


class TestDiscoverAreaKeys(unittest.TestCase):

    def test_discover_finds_both_authored_fixtures(self):
        keys = discover_area_keys()
        self.assertIn("tatooine.mos_eisley", keys)
        self.assertIn("coruscant.senate_district", keys)

    def test_discover_returns_sorted(self):
        keys = discover_area_keys()
        self.assertEqual(keys, sorted(keys))

    def test_discover_skips_missing_dir(self):
        # Point at a nonexistent worlds_root: should return [], not raise
        keys = discover_area_keys(worlds_root=Path("/nonexistent/path"))
        self.assertEqual(keys, [])


# ── Section 4 — Validator rejects each enumerated failure mode ──────────────


class TestValidatorRejectsBadFixtures(unittest.TestCase):
    """One test per failure mode the validator catches. Each test
    starts from the minimal-valid baseline and mutates ONE field
    so a regression in the validator surfaces precisely."""

    def setUp(self):
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmpdir_obj.name)
        # Set up data/worlds/clone_wars/maps/ shape under tmpdir
        (self.tmpdir / "clone_wars" / "maps").mkdir(parents=True)

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def _write_and_load(self, geom_dict, name="tmp"):
        # Write into the tmpdir's clone_wars/maps/<name>.yaml
        path = self.tmpdir / "clone_wars" / "maps" / f"{name}.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(geom_dict, f, sort_keys=False, allow_unicode=True)
        return load_area_geometry(f"test.{name}", era="clone_wars",
                                  worlds_root=self.tmpdir)

    def test_baseline_loads(self):
        # The minimal-valid baseline must load — otherwise the negative
        # tests below are testing nothing useful.
        geom = self._write_and_load(_minimal_valid_geom())
        self.assertEqual(len(geom.rooms), 2)

    def test_unsupported_schema_version_rejected(self):
        bad = _minimal_valid_geom()
        bad["schema_version"] = 99
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "unsupported schema_version"):
            self._write_and_load(bad)

    def test_missing_required_field_rejected(self):
        bad = _minimal_valid_geom()
        del bad["bounds"]
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "missing required field 'bounds'"):
            self._write_and_load(bad)

    def test_invalid_bounds_rejected(self):
        bad = _minimal_valid_geom()
        bad["bounds"]["x_max"] = bad["bounds"]["x_min"]  # x_min == x_max
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "x_min .* must be < x_max"):
            self._write_and_load(bad)

    def test_duplicate_room_id_rejected(self):
        bad = _minimal_valid_geom()
        bad["rooms"].append({
            "id": 1,  # duplicate of room 1
            "name": "DUPE", "zone": "d1",
            "x": 2.0, "y": 2.0, "w": 0.5, "h": 0.5,
            "style": "civic", "symbol": "§",
        })
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "duplicate id 1"):
            self._write_and_load(bad)

    def test_duplicate_district_id_rejected(self):
        bad = _minimal_valid_geom()
        bad["districts"].append({
            "id": "d1",  # duplicate
            "name": "OTHER",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
            "label_anchor": [0.5, 0.5],
        })
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "duplicate id 'd1'"):
            self._write_and_load(bad)

    def test_room_zone_must_be_in_districts(self):
        bad = _minimal_valid_geom()
        bad["rooms"][0]["zone"] = "nonexistent_district"
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "zone 'nonexistent_district' not in districts"):
            self._write_and_load(bad)

    def test_invalid_path_kind_rejected(self):
        bad = _minimal_valid_geom()
        bad["exit_paths"]["1-2"]["kind"] = "freeway"  # not in pathStyle
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "kind 'freeway' not in"):
            self._write_and_load(bad)

    def test_exit_path_key_format_validated(self):
        bad = _minimal_valid_geom()
        # Replace key '1-2' with invalid 'one-two'
        bad["exit_paths"] = {"one-two": bad["exit_paths"]["1-2"]}
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "key must match"):
            self._write_and_load(bad)

    def test_landmark_at_room_coords_must_have_min_zoom_2(self):
        """The double-stamping bug from README "Recent fixes" #1.
        Landmark at (1.0, 1.0) shares coords with room id 1 — must
        have min_zoom >= 2 or the validator rejects it."""
        bad = _minimal_valid_geom()
        bad["landmarks"][0]["pos"] = [1.0, 1.0]   # collides with room 1
        bad["landmarks"][0]["min_zoom"] = 1       # too low
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "shares coords with room"):
            self._write_and_load(bad)

    def test_label_path_id_must_resolve(self):
        bad = _minimal_valid_geom()
        bad["labels"][0]["path_id"] = "99-99"  # no such exit_path
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "path_id '99-99' not in exit_paths"):
            self._write_and_load(bad)

    def test_label_must_have_exactly_one_anchor(self):
        bad = _minimal_valid_geom()
        # Set both path_id AND pos — ambiguous
        bad["labels"][0]["pos"] = [2.0, 2.0]
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "exactly one of path_id/between/pos"):
            self._write_and_load(bad)

    def test_invalid_landmark_icon_rejected(self):
        bad = _minimal_valid_geom()
        bad["landmarks"][0]["icon"] = "spaceship"  # not in LM_GLYPHS
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "icon 'spaceship' not in"):
            self._write_and_load(bad)

    def test_missing_yaml_file_raises(self):
        # No file written — load should raise with the expected message
        with self.assertRaisesRegex(AreaGeometryLoadError,
                                    "AreaGeometry YAML not found"):
            load_area_geometry("test.does_not_exist", era="clone_wars",
                               worlds_root=self.tmpdir)


# ── Section 5 — Dataclass shape parity with JS contract ─────────────────────


class TestDataclassShapeMatchesJSContract(unittest.TestCase):
    """The dict produced by `to_dict()` must contain exactly the keys
    the JS renderer expects (per design_handoff_datapad_map/README.md
    "The AreaGeometry shape"). If a key is renamed/dropped here, the
    client renderer breaks silently."""

    EXPECTED_TOPLEVEL = {
        "schema_version", "area_key", "display_name", "planet", "era",
        "default_terrain", "palette", "bounds",
        "districts", "rooms", "exits", "exit_paths", "labels", "landmarks",
        "player", "contacts",
        # v51 hybrid lane: optional, present here because mos_eisley.yaml
        # now declares a substrate_image. Procedural areas omit it.
        "substrate_image",
    }
    EXPECTED_BOUNDS = {"x_min", "y_min", "x_max", "y_max"}
    EXPECTED_DISTRICT = {"id", "name", "polygon", "label_anchor", "rotation"}
    EXPECTED_ROOM = {"id", "name", "zone", "x", "y", "w", "h", "style", "symbol"}
    EXPECTED_EXIT_PATH = {"kind", "path"}  # width is optional
    EXPECTED_LABEL_BASE = {"text", "kind", "t", "side", "offset",
                           "size", "weight", "min_zoom", "max_zoom"}
    EXPECTED_LANDMARK = {"id", "icon", "name", "pos", "min_zoom", "max_zoom"}

    def setUp(self):
        self.geom = load_area_geometry("tatooine.mos_eisley")
        self.d = self.geom.to_dict(
            include_player=True,
            player={"room_id": 1, "x": 3.9, "y": 6.4},
            contacts=[],
        )

    def test_top_level_keys(self):
        self.assertEqual(set(self.d.keys()), self.EXPECTED_TOPLEVEL)

    def test_bounds_keys(self):
        self.assertEqual(set(self.d["bounds"].keys()), self.EXPECTED_BOUNDS)

    def test_district_keys(self):
        for d in self.d["districts"]:
            self.assertEqual(set(d.keys()), self.EXPECTED_DISTRICT)

    def test_room_keys(self):
        # The set MUST include all canonical keys; slug is optional
        # (added in F.MAP.2 — present on production rooms, absent on
        # purely render-only rooms).
        for r in self.d["rooms"]:
            keys = set(r.keys())
            self.assertTrue(keys.issuperset(self.EXPECTED_ROOM),
                            f"room missing keys: "
                            f"{self.EXPECTED_ROOM - keys}")
            # No unexpected keys
            allowed = self.EXPECTED_ROOM | {"slug"}
            extras = keys - allowed
            self.assertEqual(extras, set(),
                             f"room has unexpected keys: {extras}")

    def test_exit_path_keys(self):
        for k, ep in self.d["exit_paths"].items():
            keys = set(ep.keys())
            # 'width' is optional (subset OR equal)
            self.assertTrue(keys.issuperset(self.EXPECTED_EXIT_PATH),
                            f"exit_path {k!r} missing keys: "
                            f"{self.EXPECTED_EXIT_PATH - keys}")

    def test_label_keys(self):
        for l in self.d["labels"]:
            keys = set(l.keys())
            self.assertTrue(keys.issuperset(self.EXPECTED_LABEL_BASE),
                            f"label missing keys: "
                            f"{self.EXPECTED_LABEL_BASE - keys}")
            # Anchor: exactly one of path_id, between, pos
            anchor_keys = keys & {"path_id", "between", "pos"}
            self.assertEqual(len(anchor_keys), 1,
                             f"label has wrong anchor key set: {anchor_keys}")

    def test_landmark_keys(self):
        for lm in self.d["landmarks"]:
            self.assertEqual(set(lm.keys()), self.EXPECTED_LANDMARK)

    def test_dict_is_json_serializable(self):
        """Whatever we hand back must JSON-encode without going through
        repr() escapes — the wire is JSON, not Python literals."""
        import json
        s = json.dumps(self.d)
        # round-trip
        roundtripped = json.loads(s)
        self.assertEqual(roundtripped["area_key"], "tatooine.mos_eisley")
        self.assertEqual(len(roundtripped["rooms"]), 53)


# ── Section 6 — to_dict without player/contacts produces clean static side ─


class TestToDictWithoutLiveState(unittest.TestCase):
    """Server-side: AreaGeometry as static spec. Player/contacts
    layered in by the caller at push time, NOT by the loader."""

    def setUp(self):
        self.geom = load_area_geometry("tatooine.mos_eisley")

    def test_to_dict_default_excludes_player_and_contacts(self):
        d = self.geom.to_dict()
        self.assertNotIn("player", d)
        self.assertNotIn("contacts", d)

    def test_to_dict_include_player_with_no_args_emits_empty(self):
        d = self.geom.to_dict(include_player=True)
        self.assertEqual(d.get("player"), {})
        self.assertEqual(d.get("contacts"), [])


if __name__ == "__main__":
    unittest.main()
