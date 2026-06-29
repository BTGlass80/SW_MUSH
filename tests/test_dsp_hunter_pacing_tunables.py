# -*- coding: utf-8 -*-
"""tests/test_dsp_hunter_pacing_tunables.py — T3.19 config breadth for the
deterministic Dark-Side bounty-hunter pursuit pacing (engine/dsp_hunter.py).

The DSP-hunter PACING model — how fast a pursuit closes (the per-DSP-tier
`_STEP_MARKED/_STEP_HUNTED/_STEP_DARKEST` advance) and where the dread escalates
(`_CLOSING_AT/_IMMINENT_AT/_AT_HEELS_AT` stage boundaries + the `PROGRESS_MAX`
ceiling) — were hardcoded module constants. The pursuit is the "soft consequence
for the dark path": once a Force-user crosses the DSP wanted threshold a named
hunter closes in over ticks, and the only escape is to atone back under the
threshold. An operator could OBSERVE the hunt (the BH-board notoriety suffix) but
could not TUNE its pace without a code edit + redeploy. This drop externalizes the
pacing model to data/tunables.yaml under ``dsp_hunter.*`` and reads it at the USE
SITE through live accessors, closing the observe→tune loop. It is the last of the
loop prompt's Phase-2 safe-lane domains (communal / smuggling / bounty / hazards /
dsp_hunter) and the prestige-domain sibling of the hazards pacing drop — there is
no SINK lever here (defeating or atoning past the hunter is the only resolution; no
credits move).

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), an override flows through the REAL deciders (step_for_dsp /
advance_progress / pursuit_stage), magnitudes clamp safely (steps/boundaries >= 0,
the ceiling >= 1) so a fat-fingered tunable can never crash the deterministic tick,
present-but-null + non-numeric values fall back to the in-code default, the DSP
tier bands (4/6/9) stay single-sourced (NOT tunable), the shipped data/tunables.yaml
carries every key at its in-code default (a drift pin), and the tick-driver escape
reconcile resets a slipped quarry to the *tuned* imminent boundary (not the frozen
constant).

Run: python -m pytest tests/test_dsp_hunter_pacing_tunables.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import dsp_hunter as H  # noqa: E402
from engine import tunables  # noqa: E402

REPO = PROJECT_ROOT


# ── Step accessors (per-DSP-tier closing speed) ───────────────────────────


class StepAccessors(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(H._step_marked(), H._STEP_MARKED)
        self.assertEqual(H._step_hunted(), H._STEP_HUNTED)
        self.assertEqual(H._step_darkest(), H._STEP_DARKEST)

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "dsp_hunter.step_marked": 2,
            "dsp_hunter.step_hunted": 4,
            "dsp_hunter.step_darkest": 25,
        })
        self.assertEqual(H._step_marked(), 2)
        self.assertEqual(H._step_hunted(), 4)
        self.assertEqual(H._step_darkest(), 25)

    def test_negative_clamps_to_zero(self):
        tunables._TUNABLES["dsp_hunter.step_marked"] = -5
        self.assertEqual(H._step_marked(), 0)

    def test_present_but_null_falls_back(self):
        tunables._TUNABLES["dsp_hunter.step_darkest"] = None
        self.assertEqual(H._step_darkest(), H._STEP_DARKEST)

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["dsp_hunter.step_hunted"] = "fast"
        self.assertEqual(H._step_hunted(), H._STEP_HUNTED)

    def test_float_truncates_to_int(self):
        tunables._TUNABLES["dsp_hunter.step_marked"] = 7.9
        self.assertEqual(H._step_marked(), 7)


# ── Stage-boundary + ceiling accessors ────────────────────────────────────


class BoundaryAccessors(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(H.closing_at(), H._CLOSING_AT)
        self.assertEqual(H.imminent_at(), H._IMMINENT_AT)
        self.assertEqual(H.at_heels_at(), H._AT_HEELS_AT)
        self.assertEqual(H.progress_max(), H.PROGRESS_MAX)

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "dsp_hunter.stage_closing": 25,
            "dsp_hunter.stage_imminent": 60,
            "dsp_hunter.stage_at_heels": 90,
            "dsp_hunter.progress_max": 90,
        })
        self.assertEqual(H.closing_at(), 25)
        self.assertEqual(H.imminent_at(), 60)
        self.assertEqual(H.at_heels_at(), 90)
        self.assertEqual(H.progress_max(), 90)

    def test_boundary_negative_clamps_to_zero(self):
        tunables._TUNABLES["dsp_hunter.stage_closing"] = -10
        self.assertEqual(H.closing_at(), 0)

    def test_progress_max_clamps_to_one(self):
        # A ceiling of 0 (or negative) would collapse the whole scale → clamp >= 1.
        tunables._TUNABLES["dsp_hunter.progress_max"] = 0
        self.assertEqual(H.progress_max(), 1)
        tunables._TUNABLES["dsp_hunter.progress_max"] = -50
        self.assertEqual(H.progress_max(), 1)

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["dsp_hunter.stage_imminent"] = "soon"
        self.assertEqual(H.imminent_at(), H._IMMINENT_AT)

    def test_present_but_null_falls_back(self):
        tunables._TUNABLES["dsp_hunter.progress_max"] = None
        self.assertEqual(H.progress_max(), H.PROGRESS_MAX)


# ── End-to-end through the real deciders ──────────────────────────────────


class StepForDspEndToEnd(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_tier_routing_unchanged_with_overrides(self):
        # The 4/6/9 tier cutoffs are NOT tunable; only the magnitudes are.
        tunables._TUNABLES.update({
            "dsp_hunter.step_marked": 1,
            "dsp_hunter.step_hunted": 2,
            "dsp_hunter.step_darkest": 3,
        })
        self.assertEqual(H.step_for_dsp(4), 1)   # Marked
        self.assertEqual(H.step_for_dsp(5), 1)
        self.assertEqual(H.step_for_dsp(6), 2)   # Hunted
        self.assertEqual(H.step_for_dsp(8), 2)
        self.assertEqual(H.step_for_dsp(9), 3)   # Darkest
        self.assertEqual(H.step_for_dsp(99), 3)

    def test_defaults_behaviour_identical(self):
        self.assertEqual(H.step_for_dsp(4), H._STEP_MARKED)
        self.assertEqual(H.step_for_dsp(6), H._STEP_HUNTED)
        self.assertEqual(H.step_for_dsp(9), H._STEP_DARKEST)


class AdvanceProgressEndToEnd(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_override_advances_by_tuned_step(self):
        tunables._TUNABLES["dsp_hunter.step_hunted"] = 3
        self.assertEqual(H.advance_progress(0, 6), 3)

    def test_clamps_to_tuned_ceiling(self):
        tunables._TUNABLES["dsp_hunter.progress_max"] = 50
        # 48 + darkest(14) = 62 → clamped to the tuned ceiling 50, not 100.
        self.assertEqual(H.advance_progress(48, 9), 50)
        self.assertEqual(H.advance_progress(50, 9), 50)

    def test_zero_step_does_not_advance_or_raise(self):
        tunables._TUNABLES["dsp_hunter.step_marked"] = -100  # clamps to 0
        self.assertEqual(H.advance_progress(20, 4), 20)

    def test_defaults_behaviour_identical(self):
        self.assertEqual(H.advance_progress(0, 4), H._STEP_MARKED)
        self.assertEqual(H.advance_progress(H.PROGRESS_MAX - 1, 9), H.PROGRESS_MAX)
        self.assertEqual(H.advance_progress(-5, 4), 0)


class PursuitStageEndToEnd(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_tuned_boundaries_move_the_stages(self):
        tunables._TUNABLES.update({
            "dsp_hunter.stage_closing": 20,
            "dsp_hunter.stage_imminent": 50,
            "dsp_hunter.stage_at_heels": 80,
        })
        self.assertEqual(H.pursuit_stage(19), H.STAGE_TRACKING)
        self.assertEqual(H.pursuit_stage(20), H.STAGE_CLOSING)
        self.assertEqual(H.pursuit_stage(49), H.STAGE_CLOSING)
        self.assertEqual(H.pursuit_stage(50), H.STAGE_IMMINENT)
        self.assertEqual(H.pursuit_stage(79), H.STAGE_IMMINENT)
        self.assertEqual(H.pursuit_stage(80), H.STAGE_AT_HEELS)

    def test_defaults_behaviour_identical(self):
        self.assertEqual(H.pursuit_stage(0), H.STAGE_TRACKING)
        self.assertEqual(H.pursuit_stage(H._CLOSING_AT), H.STAGE_CLOSING)
        self.assertEqual(H.pursuit_stage(H._IMMINENT_AT), H.STAGE_IMMINENT)
        self.assertEqual(H.pursuit_stage(H._AT_HEELS_AT), H.STAGE_AT_HEELS)


# ── Shipped-YAML drift pins ───────────────────────────────────────────────


class ShippedYaml(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_every_key_at_in_code_default(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        self.assertEqual(tunables.get_tunable("dsp_hunter.step_marked", -1),
                         H._STEP_MARKED)
        self.assertEqual(tunables.get_tunable("dsp_hunter.step_hunted", -1),
                         H._STEP_HUNTED)
        self.assertEqual(tunables.get_tunable("dsp_hunter.step_darkest", -1),
                         H._STEP_DARKEST)
        self.assertEqual(tunables.get_tunable("dsp_hunter.progress_max", -1),
                         H.PROGRESS_MAX)
        self.assertEqual(tunables.get_tunable("dsp_hunter.stage_closing", -1),
                         H._CLOSING_AT)
        self.assertEqual(tunables.get_tunable("dsp_hunter.stage_imminent", -1),
                         H._IMMINENT_AT)
        self.assertEqual(tunables.get_tunable("dsp_hunter.stage_at_heels", -1),
                         H._AT_HEELS_AT)

    def test_shipped_yaml_is_behaviour_identical(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        self.assertEqual(H._step_marked(), H._STEP_MARKED)
        self.assertEqual(H._step_hunted(), H._STEP_HUNTED)
        self.assertEqual(H._step_darkest(), H._STEP_DARKEST)
        self.assertEqual(H.progress_max(), H.PROGRESS_MAX)
        self.assertEqual(H.closing_at(), H._CLOSING_AT)
        self.assertEqual(H.imminent_at(), H._IMMINENT_AT)
        self.assertEqual(H.at_heels_at(), H._AT_HEELS_AT)

    def test_keys_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        for key in ("dsp_hunter.step_marked", "dsp_hunter.step_hunted",
                    "dsp_hunter.step_darkest", "dsp_hunter.progress_max",
                    "dsp_hunter.stage_closing", "dsp_hunter.stage_imminent",
                    "dsp_hunter.stage_at_heels"):
            self.assertIn(f"{key}:", ty)

    def test_accessors_read_at_use_site(self):
        src = (REPO / "engine" / "dsp_hunter.py").read_text(encoding="utf-8")
        self.assertIn('get_tunable("dsp_hunter.step_marked"', src)
        self.assertIn('get_tunable("dsp_hunter.step_darkest"', src)
        self.assertIn('get_tunable("dsp_hunter.progress_max"', src)
        self.assertIn('get_tunable("dsp_hunter.stage_imminent"', src)
        # The deciders route through the accessors, not the raw constants —
        # guard against a regression that re-freezes them at import.
        self.assertIn("return _step_darkest()", src)
        self.assertIn("ceiling = progress_max()", src)
        self.assertIn("if p >= imminent_at():", src)

    def test_tick_driver_uses_tuned_imminent_boundary(self):
        # The escape reconcile (a slipped quarry) must reset to the TUNED
        # imminent boundary, not the frozen H._IMMINENT_AT constant — else an
        # operator who raises stage_imminent would see the reset drift.
        src = (REPO / "server" / "tick_handlers_progression.py").read_text(
            encoding="utf-8")
        self.assertIn("H.imminent_at()", src)
        self.assertNotIn("H._IMMINENT_AT", src)


# ── Tier bands stay single-sourced (NOT externalized) ─────────────────────


class TierBandsNotTunable(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_dsp_tier_cutoffs_ignore_any_tunable(self):
        # There is intentionally no dsp_hunter.tier_* key; the 4/6/9 cutoffs are
        # single-sourced with bounty_board's notoriety tiers. Even if an operator
        # invented such a key, routing is unaffected.
        tunables._TUNABLES["dsp_hunter.tier_hunted"] = 3
        self.assertEqual(H.step_for_dsp(6), H._STEP_HUNTED)  # still Hunted at 6
        self.assertEqual(H.step_for_dsp(5), H._STEP_MARKED)  # still Marked at 5


if __name__ == "__main__":
    unittest.main()
