# -*- coding: utf-8 -*-
"""tests/test_ambient_era_guard.py — era-guard on the ambient dynamic pool.

engine/ambient_events.py::AmbientEventManager.set_dynamic_pool ingests
LLM-generated lines (the Director's `ambient_pool`) and serves them to every
player in a room. The Director filters length/keywords/player-names but NOT
era, so a GCW-era leak could reach players. set_dynamic_pool now drops any
off-era line through the shared engine.era_validator guard (the same boundary
discipline as the Ollama idle-queue tasks).

Constructs a fresh manager per test (not the module singleton) so there's no
cross-test pool leak.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.ambient_events import AmbientEventManager


class TestAmbientDynamicPoolEraGuard(unittest.TestCase):
    def setUp(self):
        self.mgr = AmbientEventManager()

    def _texts(self, zone_key):
        return [ln.text for ln in self.mgr._dynamic_pool.get(zone_key, [])]

    def test_off_era_token_lines_dropped(self):
        self.mgr.set_dynamic_pool({"cantina": [
            "The bartender wipes down a glass and eyes the door.",   # clean
            "Imperial patrols increase near the docks.",             # off-era
            "Stormtroopers shove past a Jawa.",                      # off-era
        ]})
        kept = self._texts("cantina")
        self.assertEqual(len(kept), 1, f"off-era lines not dropped: {kept}")
        self.assertIn("bartender", kept[0])

    def test_canonical_figure_line_dropped(self):
        self.mgr.set_dynamic_pool({"streets": [
            "Anakin Skywalker strides through the crowd.",           # canonical figure
            "Dust devils chase a droid down the lane.",              # clean
        ]})
        kept = self._texts("streets")
        self.assertEqual(kept, ["Dust devils chase a droid down the lane."])

    def test_all_off_era_zone_absent(self):
        # When every line in a zone is off-era, the zone gets no dynamic entry
        # (the static pool still covers it).
        self.mgr.set_dynamic_pool({"government": [
            "The Empire tightens its grip on the sector.",
            "A Rebel cell is rumored to operate nearby.",
        ]})
        self.assertNotIn("government", self.mgr._dynamic_pool)

    def test_clean_lines_preserved(self):
        lines = ["Two suns beat down on the durasteel.",
                 "A bantha lows somewhere past the wall."]
        self.mgr.set_dynamic_pool({"spaceport": lines})
        self.assertEqual(self._texts("spaceport"), lines)

    def test_length_and_command_filters_still_apply(self):
        # The pre-existing length cap is preserved alongside the era guard.
        self.mgr.set_dynamic_pool({"shops": [
            "x" * 200,                          # too long -> dropped
            "A vendor haggles over a power coupling.",  # clean, kept
        ]})
        kept = self._texts("shops")
        self.assertEqual(kept, ["A vendor haggles over a power coupling."])

    def test_empty_clears_pool(self):
        self.mgr.set_dynamic_pool({"cantina": ["A clean ambient line here."]})
        self.assertTrue(self.mgr._dynamic_pool)
        self.mgr.set_dynamic_pool({})
        self.assertEqual(self.mgr._dynamic_pool, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
