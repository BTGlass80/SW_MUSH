"""
test_area_loader_substrate.py — AreaGeometry.substrate_image (v51 hybrid lane).

The optional `substrate_image` field carries the path to a pre-painted
raster tile. It must:
  - parse from YAML when present, defaulting to None when absent;
  - appear in to_dict() ONLY when set (procedural areas keep their wire
    shape unchanged — the JS renderer keys off truthiness);
  - round-trip on the real Mos Eisley fixture (which declares one) and be
    absent on the Senate District fixture (which does not).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from engine.area_loader import load_area_geometry


def _minimal_valid_geom() -> dict:
    """Smallest valid AreaGeometry (mirrors the F.MAP.1 baseline). Inlined
    rather than imported so this test doesn't depend on another test
    module's import path under pytest's rootdir."""
    return {
        "schema_version": 1,
        "area_key": "test.tmp",
        "display_name": "TEST",
        "planet": "TEST",
        "era": "test",
        "default_terrain": "sand",
        "palette": "tatooine",
        "bounds": {"x_min": 0.0, "y_min": 0.0, "x_max": 4.0, "y_max": 4.0},
        "districts": [{
            "id": "d1", "name": "TESTDIST",
            "polygon": [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]],
            "label_anchor": [3.5, 3.5], "rotation": 0,
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


class TestSubstrateImageField(unittest.TestCase):
    def setUp(self):
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmpdir_obj.name)
        (self.tmpdir / "clone_wars" / "maps").mkdir(parents=True)

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def _write_and_load(self, geom_dict, name="tmp"):
        path = self.tmpdir / "clone_wars" / "maps" / f"{name}.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(geom_dict, f, sort_keys=False, allow_unicode=True)
        return load_area_geometry(f"test.{name}", era="clone_wars",
                                  worlds_root=self.tmpdir)

    def test_substrate_image_parses_when_present(self):
        geom_dict = _minimal_valid_geom()
        geom_dict["substrate_image"] = "/static/maps/example_substrate.png"
        geom = self._write_and_load(geom_dict)
        self.assertEqual(geom.substrate_image,
                         "/static/maps/example_substrate.png")
        d = geom.to_dict()
        self.assertIn("substrate_image", d)
        self.assertEqual(d["substrate_image"],
                         "/static/maps/example_substrate.png")

    def test_substrate_image_defaults_none_and_is_omitted(self):
        geom = self._write_and_load(_minimal_valid_geom())
        self.assertIsNone(geom.substrate_image)
        # Omitted from the wire dict so procedural areas are unchanged.
        self.assertNotIn("substrate_image", geom.to_dict())

    def test_empty_substrate_image_treated_as_absent(self):
        geom_dict = _minimal_valid_geom()
        geom_dict["substrate_image"] = ""   # falsy → treated as unset
        geom = self._write_and_load(geom_dict)
        self.assertIsNone(geom.substrate_image)
        self.assertNotIn("substrate_image", geom.to_dict())


class TestRealFixtureSubstrate(unittest.TestCase):
    def test_mos_eisley_declares_substrate(self):
        geom = load_area_geometry("tatooine.mos_eisley")
        self.assertEqual(geom.substrate_image,
                         "/static/maps/mos_eisley_substrate.png")
        self.assertEqual(geom.to_dict().get("substrate_image"),
                         "/static/maps/mos_eisley_substrate.png")

    def test_senate_district_declares_substrate(self):
        # The whole CW map set migrated to the v51 hybrid-raster lane, so the
        # Senate District now also carries a substrate path. (The field's
        # optionality is proven independently by TestSubstrateImageField's
        # synthetic no-substrate fixtures above.)
        geom = load_area_geometry("coruscant.senate_district")
        self.assertEqual(geom.substrate_image,
                         "/static/maps/coruscant_senate_substrate.png")
        self.assertEqual(geom.to_dict().get("substrate_image"),
                         "/static/maps/coruscant_senate_substrate.png")


if __name__ == "__main__":
    unittest.main()
