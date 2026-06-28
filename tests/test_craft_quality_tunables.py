# -*- coding: utf-8 -*-
"""tests/test_craft_quality_tunables.py — T3.19 config breadth for the craft
outcome quality knobs (engine/crafting.py).

The five produced-item quality levers — QUALITY_MULT_BASE / _MAX / _CRIT /
_EXP_CRIT and QUALITY_PARTIAL — were hardcoded module constants: an operator
could OBSERVE the craft outcome distribution via the ``@balance craft`` telemetry
board (the per-schematic success/partial/fumble + mean produced quality the
``craft`` event carries) but could not TUNE it without a code edit + redeploy.
This drop externalizes the five to data/tunables.yaml under ``craft.*`` and reads
them at the USE SITE through live accessors, closing the observe→tune loop the
craft telemetry opened — the WRITE-side complement that mirrors the grind-reward
externalization (grind.* / engine/hunting_rewards.py).

This suite proves: the accessors default when a key is absent (behaviour-
identical), an override flows through the REAL ``resolve_craft`` quality decision
on every branch (success linear-scale base+max, critical, experiment-critical,
partial near-miss), a fat-fingered negative clamps to 0.0 (and the final quality
stays in [1, 100] — a negative multiplier can never produce an invalid/inverted
quality), a present-but-null / non-numeric value falls back to the default, and
the shipped data/tunables.yaml carries the five keys at their in-code defaults
(a drift pin), read at the use site (not frozen at import).

Run: python -m pytest tests/test_craft_quality_tunables.py
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

os.environ.setdefault("SW_ERA", "clone_wars")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import crafting  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402

REPO = PROJECT_ROOT


def _char():
    # An empty-components schematic keeps base quality at the 50.0 default with
    # no DB / inventory needed (proven by the craft telemetry rollup E2E test).
    return {"id": 7, "name": "Tinker"}


def _schem():
    return {
        "key": "field_medkit", "name": "Field Medkit",
        "output_key": "field_medkit", "skill_required": "first aid",
        "difficulty": 10, "components": [],
    }


def _scr(*, success=True, fumble=False, critical_success=False, margin=5):
    return types.SimpleNamespace(
        success=success, fumble=fumble,
        critical_success=critical_success, margin=margin)


class CraftQualityTunableAccessors(unittest.TestCase):
    """The use-site accessors: default fallback, override, negative clamp, null."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(crafting._quality_mult_base(), crafting.QUALITY_MULT_BASE)
        self.assertEqual(crafting._quality_mult_max(), crafting.QUALITY_MULT_MAX)
        self.assertEqual(crafting._quality_mult_crit(), crafting.QUALITY_MULT_CRIT)
        self.assertEqual(crafting._quality_mult_exp_crit(), crafting.QUALITY_MULT_EXP_CRIT)
        self.assertEqual(crafting._quality_partial(), crafting.QUALITY_PARTIAL)

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "craft.quality_mult_base": 1.1,
            "craft.quality_mult_max": 1.8,
            "craft.quality_mult_crit": 1.7,
            "craft.quality_mult_exp_crit": 2.5,
            "craft.quality_partial": 0.7,
        })
        self.assertEqual(crafting._quality_mult_base(), 1.1)
        self.assertEqual(crafting._quality_mult_max(), 1.8)
        self.assertEqual(crafting._quality_mult_crit(), 1.7)
        self.assertEqual(crafting._quality_mult_exp_crit(), 2.5)
        self.assertEqual(crafting._quality_partial(), 0.7)

    def test_negative_clamps_to_zero(self):
        # A fat-fingered negative multiplier must NOT invert quality.
        tunables._TUNABLES.update({
            "craft.quality_mult_base": -2.0,
            "craft.quality_mult_max": -1.0,
            "craft.quality_mult_crit": -0.5,
            "craft.quality_mult_exp_crit": -3.0,
            "craft.quality_partial": -1.0,
        })
        self.assertEqual(crafting._quality_mult_base(), 0.0)
        self.assertEqual(crafting._quality_mult_max(), 0.0)
        self.assertEqual(crafting._quality_mult_crit(), 0.0)
        self.assertEqual(crafting._quality_mult_exp_crit(), 0.0)
        self.assertEqual(crafting._quality_partial(), 0.0)

    def test_present_but_null_falls_back_to_default(self):
        # get_tunable coerces a None (operator typo: `craft.quality_mult_base:`) → default.
        tunables._TUNABLES["craft.quality_mult_base"] = None
        self.assertEqual(crafting._quality_mult_base(), crafting.QUALITY_MULT_BASE)

    def test_bad_value_falls_back_to_default(self):
        # A non-numeric YAML value can't crash the craft path — _safe_float default.
        tunables._TUNABLES["craft.quality_mult_crit"] = "shiny"
        self.assertEqual(crafting._quality_mult_crit(), crafting.QUALITY_MULT_CRIT)

    def test_int_value_coerces_to_float(self):
        tunables._TUNABLES["craft.quality_mult_max"] = 2
        self.assertEqual(crafting._quality_mult_max(), 2.0)


class CraftQualityTunableEndToEnd(unittest.TestCase):
    """The override flows through the REAL resolve_craft quality decision."""

    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    def test_base_multiplier_override_changes_success_quality(self):
        # margin 0 → multiplier == base; base 50.0 quality. Default 1.0 → 50.0.
        out = crafting.resolve_craft(_char(), _schem(), _scr(margin=0))
        self.assertEqual(out["quality"], 50.0)
        tunables._TUNABLES["craft.quality_mult_base"] = 0.4
        out2 = crafting.resolve_craft(_char(), _schem(), _scr(margin=0))
        self.assertEqual(out2["quality"], 20.0)   # round(50 * 0.4)

    def test_max_multiplier_override_widens_the_spread(self):
        # margin 10 → multiplier == max. Default 1.3 → 65.0.
        out = crafting.resolve_craft(_char(), _schem(), _scr(margin=10))
        self.assertEqual(out["quality"], 65.0)
        tunables._TUNABLES["craft.quality_mult_max"] = 1.6
        out2 = crafting.resolve_craft(_char(), _schem(), _scr(margin=10))
        self.assertEqual(out2["quality"], 80.0)   # round(50 * 1.6)

    def test_crit_multiplier_override(self):
        out = crafting.resolve_craft(
            _char(), _schem(), _scr(critical_success=True), experiment=False)
        self.assertEqual(out["quality"], 75.0)    # 50 * 1.5
        tunables._TUNABLES["craft.quality_mult_crit"] = 1.0
        out2 = crafting.resolve_craft(
            _char(), _schem(), _scr(critical_success=True), experiment=False)
        self.assertEqual(out2["quality"], 50.0)

    def test_exp_crit_multiplier_override(self):
        # Default exp-crit 2.0 → 100.0 (clamped). Override moves it.
        out = crafting.resolve_craft(
            _char(), _schem(), _scr(critical_success=True), experiment=True)
        self.assertEqual(out["quality"], 100.0)
        tunables._TUNABLES["craft.quality_mult_exp_crit"] = 1.0
        out2 = crafting.resolve_craft(
            _char(), _schem(), _scr(critical_success=True), experiment=True)
        self.assertEqual(out2["quality"], 50.0)

    def test_partial_multiplier_override(self):
        # Near-miss: not a success, margin >= -4 → partial branch (base * partial).
        out = crafting.resolve_craft(_char(), _schem(), _scr(success=False, margin=-2))
        self.assertTrue(out["partial"])
        self.assertEqual(out["quality"], 25.0)    # 50 * 0.5
        tunables._TUNABLES["craft.quality_partial"] = 0.8
        out2 = crafting.resolve_craft(_char(), _schem(), _scr(success=False, margin=-2))
        self.assertEqual(out2["quality"], 40.0)   # round(50 * 0.8)

    def test_negative_multiplier_never_produces_invalid_quality(self):
        # base clamps to 0.0 → 50*0 = 0.0, then the use-site [1,100] clamp floors
        # quality to 1.0 — never negative, never an inverted/zeroed craft.
        tunables._TUNABLES["craft.quality_mult_base"] = -5.0
        out = crafting.resolve_craft(_char(), _schem(), _scr(margin=0))
        self.assertTrue(out["success"])
        self.assertEqual(out["quality"], 1.0)

    def test_behaviour_identical_to_defaults_when_unset(self):
        # No tunables loaded → exact legacy numbers on every branch.
        self.assertEqual(
            crafting.resolve_craft(_char(), _schem(), _scr(margin=0))["quality"], 50.0)
        self.assertEqual(
            crafting.resolve_craft(_char(), _schem(), _scr(margin=10))["quality"], 65.0)
        self.assertEqual(
            crafting.resolve_craft(_char(), _schem(),
                                   _scr(success=False, margin=-2))["quality"], 25.0)


class CraftQualityTunableShipped(unittest.TestCase):
    """Drift pins: the shipped YAML carries the five keys at in-code defaults."""

    _KEYS = {
        "craft.quality_mult_base": "QUALITY_MULT_BASE",
        "craft.quality_mult_max": "QUALITY_MULT_MAX",
        "craft.quality_mult_crit": "QUALITY_MULT_CRIT",
        "craft.quality_mult_exp_crit": "QUALITY_MULT_EXP_CRIT",
        "craft.quality_partial": "QUALITY_PARTIAL",
    }

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_keys_at_in_code_defaults(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for key, const in self._KEYS.items():
            self.assertEqual(
                tunables.get_tunable(key, -1.0), getattr(crafting, const),
                f"{key} drifted from {const}")

    def test_keys_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        for key in self._KEYS:
            self.assertIn(f"{key}:", ty)

    def test_accessors_read_at_use_site(self):
        # Guard the use-site contract: the constants are read through get_tunable,
        # not frozen at import (so an operator edit takes effect on reload).
        src = (REPO / "engine" / "crafting.py").read_text(encoding="utf-8")
        for key in self._KEYS:
            self.assertIn(f'get_tunable("{key}"', src)
        # The quality decision must call the accessors, not the raw constants.
        self.assertIn("_quality_mult_exp_crit()", src)
        self.assertIn("_quality_mult_crit()", src)
        self.assertIn("_quality_partial()", src)


if __name__ == "__main__":
    unittest.main()
