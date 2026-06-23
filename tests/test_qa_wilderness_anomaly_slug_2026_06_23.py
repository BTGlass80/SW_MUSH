# -*- coding: utf-8 -*-
"""
tests/test_qa_wilderness_anomaly_slug_2026_06_23.py — QA break-it regression
(wilderness sweep, 2026-06-23).

[SWALLOW, BLOCKER-class] The entire Tatooine wilderness anomaly system was
silently dead. The anomaly templates tagged the bare region slug "dune_sea", but
the wilderness YAML (data/worlds/clone_wars/wilderness/dune_sea.yaml) declares
`slug: tatooine_dune_sea`, so the DB stores wilderness_region_id =
"tatooine_dune_sea". `_pick_template(region_slug="tatooine_dune_sea")` therefore
matched NONE of the Tatooine T1/T2/T3 templates, and `anomalies` always showed
"No active anomalies" in the Tatooine wilderness. (coruscant_underworld worked
because its templates match its own full slug.)

Fix: the Tatooine templates now tag "tatooine_dune_sea" (the DB slug). Changing
the YAML slug instead would violate the additive-only world-data invariant.
"""
from __future__ import annotations

import random
import unittest
from pathlib import Path

from engine.wilderness_anomalies import _pick_template, _reset_state_for_tests

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "engine" / "wilderness_anomalies.py").read_text(encoding="utf-8")


class TestTatooineAnomalySlug(unittest.TestCase):
    def setUp(self):
        _reset_state_for_tests()

    def test_full_slug_matches_tatooine_tier1(self):
        key = _pick_template(random.Random(42),
                             region_slug="tatooine_dune_sea", tier=1)
        self.assertIsNotNone(
            key, "Tatooine dune_sea T1 anomaly template must match the DB slug "
                 "'tatooine_dune_sea'")

    def test_full_slug_matches_tatooine_tier2(self):
        key = _pick_template(random.Random(7),
                             region_slug="tatooine_dune_sea", tier=2)
        self.assertIsNotNone(key, "Tatooine T2 anomaly template must match")

    def test_bare_dune_sea_slug_no_longer_used(self):
        self.assertNotIn('["dune_sea"]', SRC,
                          "no anomaly template may still tag the bare 'dune_sea' "
                          "slug (the DB uses 'tatooine_dune_sea')")

    def test_coruscant_underworld_still_matches(self):
        key = _pick_template(random.Random(3),
                             region_slug="coruscant_underworld", tier=1)
        self.assertIsNotNone(key, "coruscant_underworld must still match (regression)")


if __name__ == "__main__":
    unittest.main()
