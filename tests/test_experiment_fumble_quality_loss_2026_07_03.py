# -*- coding: utf-8 -*-
"""tests/test_experiment_fumble_quality_loss_2026_07_03.py

Regression for the inverted experiment quality-loss penalty.

`ExperimentCommand` (weapon modification, engine/crafting + parser/
crafting_commands) routes ANY fumble to the breakdown path via
``result.fumble`` — and a WEG fumble (Wild Die = 1) can co-occur with a NET
SUCCESS: once the pool is large enough to clear the difficulty after the
complication penalty (Wild Die -> 0 AND highest normal die removed, see
engine/dice.roll_d6_pool), ``fumble is True`` while ``margin >= 0``.

In that region ``resolve_experiment_failure`` returns ``"quality_loss"``
(its ``margin > -5`` guard), and the old handler computed
``loss = abs(result.margin) * 2`` — using the POSITIVE success margin as a
failure magnitude. That inverted the penalty: a *stronger* roll on a fumble
destroyed *more* quality (margin +8 -> 16 points lost; margin +2 -> 4 lost),
and it scaled with how well the crafter rolled.

The fix funnels every quality-loss magnitude through
``engine.crafting.experiment_quality_loss(margin)``, which clamps the basis
at 0 so the loss tracks the FAILURE margin only. Genuine failures
(margin < 0) are byte-identical to before; a fumble-with-success now costs
zero quality (routing unchanged — no new weapon destruction).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SW_ERA", "clone_wars")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.crafting import (  # noqa: E402
    experiment_quality_loss,
    resolve_experiment_failure,
)


class TestExperimentQualityLoss(unittest.TestCase):
    def test_genuine_failure_unchanged(self):
        # Negative margins are real failures — the loss must be identical to
        # the pre-fix formula (abs(margin) * 2).
        for margin in range(-1, -13, -1):
            self.assertEqual(
                experiment_quality_loss(margin),
                abs(margin) * 2,
                f"failure margin {margin} loss changed",
            )

    def test_fumble_with_success_costs_no_quality(self):
        # The bug region: fumble True but margin >= 0 (net success after the
        # complication penalty). No failure -> no quality damage.
        for margin in range(0, 13):
            self.assertEqual(
                experiment_quality_loss(margin), 0,
                f"non-negative margin {margin} should cost 0 quality",
            )

    def test_penalty_is_never_inverted(self):
        # The core invariant: a BETTER roll (higher margin) must never cost
        # MORE quality. loss(margin) is monotonically non-increasing.
        margins = list(range(-12, 13))
        losses = [experiment_quality_loss(m) for m in margins]
        for i in range(1, len(losses)):
            self.assertLessEqual(
                losses[i], losses[i - 1],
                f"loss rose from margin {margins[i-1]} to {margins[i]} "
                f"({losses[i-1]} -> {losses[i]}) — penalty is inverted",
            )

    def test_old_inverted_behavior_is_gone(self):
        # Pin the exact former defect: a strong fumble+success roll no longer
        # inflicts abs(positive-margin) * 2 quality damage.
        strong_success_margin = 8
        self.assertEqual(
            experiment_quality_loss(strong_success_margin), 0)
        self.assertNotEqual(
            experiment_quality_loss(strong_success_margin),
            abs(strong_success_margin) * 2,  # the old (buggy) value: 16
        )

    def test_quality_loss_outcome_reachable_for_fumble_success(self):
        # Confirms the outcome that feeds the clamped loss: a fumble that met
        # the difficulty (margin > -5) resolves to "quality_loss", so the
        # handler's quality-loss branch is the live path for this region.
        self.assertEqual(
            resolve_experiment_failure(4, "lethal"), "quality_loss")
        self.assertEqual(
            resolve_experiment_failure(0, "lethal"), "quality_loss")
        # And a catastrophic miss still rolls the breakdown table (never
        # "quality_loss").
        self.assertNotEqual(
            resolve_experiment_failure(-8, "vehicle"), "quality_loss")


if __name__ == "__main__":
    unittest.main()
