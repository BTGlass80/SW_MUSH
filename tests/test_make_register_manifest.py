"""test_make_register_manifest.py — the Phase 1b manifest generator.

The generator converts a map YAML's authored landmarks into the JSON the
registration tool consumes. The load-bearing invariant: its world→fraction
math must be the EXACT inverse of the tool's fraction→world (fracToWorld),
so a generated manifest re-seeds each pin precisely where it already sits.
If that drifts, every pre-seeded pin lands wrong and the tool stops being
"confirm, don't hunt".
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from tools.make_register_manifest import build_manifest


def _write_map(tmp: Path, place: str, doc: dict) -> None:
    (tmp / "clone_wars" / "maps").mkdir(parents=True, exist_ok=True)
    (tmp / "clone_wars" / "maps" / f"{place}.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _frac_to_world(b: dict, fx: float, fy: float) -> tuple[float, float]:
    # Mirror of the tool's fracToWorld (the thing we must invert).
    return (b["x_min"] + fx * (b["x_max"] - b["x_min"]),
            b["y_max"] - fy * (b["y_max"] - b["y_min"]))


class TestManifestGenerator(unittest.TestCase):
    def setUp(self):
        self.tmp_obj = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmp_obj.name)

    def tearDown(self):
        self.tmp_obj.cleanup()

    def _doc(self):
        return {
            "area_key": "test.place",
            "display_name": "TEST PLACE",
            "palette": "tatooine",
            "substrate_image": "/static/maps/place_substrate.png",
            "bounds": {"x_min": 2.4, "y_min": -0.4, "x_max": 14.8, "y_max": 7.6},
            "landmarks": [
                {"id": "bay94", "icon": "dock", "name": "Docking Bay 94",
                 "pos": [5.6, 4.7], "min_zoom": 2, "max_zoom": 2},
                {"id": "jabba_th", "icon": "hutt", "name": "Jabba's Townhouse",
                 "pos": [6.9, 1.1], "min_zoom": 2, "max_zoom": 2},
                {"id": "jabba_p", "icon": "palace", "name": "Jabba's Palace \u2197",
                 "pos": [8.9, 2.6], "min_zoom": 2, "max_zoom": 3},
            ],
        }

    def test_world_to_frac_is_exact_inverse_of_tool(self):
        _write_map(self.tmp, "place", self._doc())
        m = build_manifest("test.place", era="clone_wars",
                           worlds_root=self.tmp, substrate=None)
        b = m["bounds"]
        by_id = {l["id"]: l for l in m["landmarks"]}
        # Round-trip every landmark back through the tool's fracToWorld.
        for src in self._doc()["landmarks"]:
            lm = by_id[src["id"]]
            wx, wy = _frac_to_world(b, lm["fx"], lm["fy"])
            self.assertAlmostEqual(wx, src["pos"][0], places=2,
                                   msg=f"{src['id']} x drifted")
            self.assertAlmostEqual(wy, src["pos"][1], places=2,
                                   msg=f"{src['id']} y drifted")

    def test_distinctive_flagging(self):
        _write_map(self.tmp, "place", self._doc())
        m = build_manifest("test.place", era="clone_wars",
                           worlds_root=self.tmp, substrate=None)
        by_id = {l["id"]: l for l in m["landmarks"]}
        # dock icon → distinctive
        self.assertTrue(by_id["bay94"]["distinctive"])
        # hutt icon, indistinct dome → not distinctive
        self.assertFalse(by_id["jabba_th"]["distinctive"])
        # off-map arrow (↗ in name) → not distinctive regardless of icon
        self.assertFalse(by_id["jabba_p"]["distinctive"])

    def test_substrate_defaults_from_yaml_then_convention(self):
        # YAML carries substrate_image → used.
        _write_map(self.tmp, "place", self._doc())
        m = build_manifest("test.place", era="clone_wars",
                           worlds_root=self.tmp, substrate=None)
        self.assertEqual(m["substrate"], "/static/maps/place_substrate.png")
        # No substrate_image → conventional guess from place name.
        doc = self._doc()
        del doc["substrate_image"]
        _write_map(self.tmp, "bare", {**doc, "area_key": "test.bare"})
        m2 = build_manifest("test.bare", era="clone_wars",
                            worlds_root=self.tmp, substrate=None)
        self.assertEqual(m2["substrate"], "/static/maps/bare_substrate.png")

    def test_explicit_substrate_override(self):
        _write_map(self.tmp, "place", self._doc())
        m = build_manifest("test.place", era="clone_wars",
                           worlds_root=self.tmp, substrate="/custom/x.png")
        self.assertEqual(m["substrate"], "/custom/x.png")

    def test_manifest_shape_matches_tool_contract(self):
        _write_map(self.tmp, "place", self._doc())
        m = build_manifest("test.place", era="clone_wars",
                           worlds_root=self.tmp, substrate=None)
        # Top-level keys the tool reads.
        for k in ("area_key", "display_name", "substrate", "bounds", "landmarks"):
            self.assertIn(k, m)
        # Each landmark has the fields buildPins/fracToWorld/buildList need.
        for lm in m["landmarks"]:
            for k in ("id", "icon", "name", "distinctive", "fx", "fy",
                      "note", "min_zoom", "max_zoom"):
                self.assertIn(k, lm, f"landmark missing {k}")
            self.assertGreaterEqual(lm["fx"], 0.0)
            self.assertLessEqual(lm["fx"], 1.0)
            self.assertGreaterEqual(lm["fy"], 0.0)
            self.assertLessEqual(lm["fy"], 1.0)

    def test_real_mos_eisley_roundtrips(self):
        # Against the actual shipped map file (not a fixture).
        repo_worlds = Path(__file__).resolve().parent.parent / "data" / "worlds"
        m = build_manifest("tatooine.mos_eisley", era="clone_wars",
                           worlds_root=repo_worlds, substrate=None)
        self.assertEqual(m["substrate"],
                         "/static/maps/mos_eisley_substrate.png")
        self.assertEqual(len(m["landmarks"]), 9)
        # 5 distinctive (dock/ship/wreck/cantina/bones), 4 generic/off-map.
        self.assertEqual(sum(1 for l in m["landmarks"] if l["distinctive"]), 5)


if __name__ == "__main__":
    unittest.main()
