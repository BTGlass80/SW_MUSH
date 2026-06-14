# -*- coding: utf-8 -*-
"""
tests/test_diff1_threat_band.py — DIFF.1 threat-band engine axis.

Per difficulty_tiers_design_v1.md. Covers the ThreatBand enum, the
get_effective_threat resolver (zone-inheritance via get_room_property),
the player-facing display helpers, the frontier≠lawless validator, and
the reward multiplier. Also pins that the live CW world loads clean with
the new validation (default = SETTLED everywhere, zero behavior change
until DIFF.2 labels zones).
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.threat_band import (
    ThreatBand, DEFAULT_BAND, get_effective_threat,
    threat_label, threat_name, threat_blurb, threat_color_code,
    frontier_lawless_conflict, reward_multiplier,
)


def _run(coro):
    """Run a coroutine to completion in a fresh event loop. Used by the
    unittest.TestCase-style resolver tests (this file mixes sync
    unittest cases with one async resolver group)."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────────────────────────────
# Enum + parsing
# ──────────────────────────────────────────────────────────────────────

class TestThreatBandEnum(unittest.TestCase):

    def test_four_bands_with_ratings_1_to_4(self):
        self.assertEqual(ThreatBand.FRONTIER.rating, 1)
        self.assertEqual(ThreatBand.SETTLED.rating, 2)
        self.assertEqual(ThreatBand.CONTESTED_MARCHES.rating, 3)
        self.assertEqual(ThreatBand.WILDS.rating, 4)

    def test_ratings_are_ordered(self):
        bands = [ThreatBand.FRONTIER, ThreatBand.SETTLED,
                 ThreatBand.CONTESTED_MARCHES, ThreatBand.WILDS]
        ratings = [b.rating for b in bands]
        self.assertEqual(ratings, sorted(ratings))
        self.assertEqual(len(set(ratings)), 4)

    def test_from_key_parses_canonical(self):
        self.assertEqual(ThreatBand.from_key("frontier"),
                         ThreatBand.FRONTIER)
        self.assertEqual(ThreatBand.from_key("CONTESTED_MARCHES"),
                         ThreatBand.CONTESTED_MARCHES)
        self.assertEqual(ThreatBand.from_key("  Wilds  "),
                         ThreatBand.WILDS)

    def test_from_key_empty_or_unknown_is_none(self):
        self.assertIsNone(ThreatBand.from_key(""))
        self.assertIsNone(ThreatBand.from_key(None))
        self.assertIsNone(ThreatBand.from_key("bogus_band"))

    def test_default_band_is_settled(self):
        self.assertEqual(DEFAULT_BAND, ThreatBand.SETTLED)


# ──────────────────────────────────────────────────────────────────────
# Resolver (zone inheritance via get_room_property)
# ──────────────────────────────────────────────────────────────────────

class _FakeDB:
    """Minimal stand-in: get_room_property returns a configured value."""
    def __init__(self, value=None, raises=False):
        self._value = value
        self._raises = raises

    async def get_room_property(self, room_id, prop_name, default=None):
        assert prop_name == "threat_band"
        if self._raises:
            raise RuntimeError("simulated DB failure")
        return self._value


class TestGetEffectiveThreat(unittest.TestCase):

    def test_resolves_set_band(self):
        db = _FakeDB(value="wilds")
        self.assertEqual(_run(get_effective_threat(5, db)),
                         ThreatBand.WILDS)

    def test_unset_resolves_default(self):
        db = _FakeDB(value=None)
        self.assertEqual(_run(get_effective_threat(5, db)),
                         DEFAULT_BAND)

    def test_unknown_value_resolves_default(self):
        db = _FakeDB(value="not_a_real_band")
        self.assertEqual(_run(get_effective_threat(5, db)),
                         DEFAULT_BAND)

    def test_db_failure_resolves_default_not_raises(self):
        db = _FakeDB(raises=True)
        # Failure-tolerant: a difficulty read must never break look/move.
        self.assertEqual(_run(get_effective_threat(5, db)),
                         DEFAULT_BAND)


# ──────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────

class TestDisplayHelpers(unittest.TestCase):

    def test_label_contains_uppercase_name_and_ansi(self):
        lbl = threat_label(ThreatBand.CONTESTED_MARCHES)
        self.assertIn("CONTESTED MARCHES", lbl)
        self.assertIn("\033[", lbl)   # ANSI present
        self.assertIn("\033[0m", lbl)  # reset present

    def test_name_is_plain(self):
        self.assertEqual(threat_name(ThreatBand.WILDS), "Deep Wilds")
        self.assertNotIn("\033", threat_name(ThreatBand.WILDS))

    def test_every_band_has_label_name_blurb_color(self):
        for b in ThreatBand:
            self.assertTrue(threat_label(b))
            self.assertTrue(threat_name(b))
            self.assertTrue(threat_blurb(b))
            self.assertTrue(threat_color_code(b).startswith("\033["))


# ──────────────────────────────────────────────────────────────────────
# frontier≠lawless validator
# ──────────────────────────────────────────────────────────────────────

class TestFrontierLawlessConflict(unittest.TestCase):

    def test_frontier_plus_lawless_conflicts(self):
        self.assertTrue(frontier_lawless_conflict("frontier", "lawless"))
        self.assertTrue(frontier_lawless_conflict("FRONTIER", "LAWLESS"))

    def test_frontier_with_other_security_ok(self):
        self.assertFalse(frontier_lawless_conflict("frontier", "secured"))
        self.assertFalse(frontier_lawless_conflict("frontier", "contested"))
        self.assertFalse(frontier_lawless_conflict("frontier", None))

    def test_other_band_with_lawless_ok(self):
        self.assertFalse(frontier_lawless_conflict("wilds", "lawless"))
        self.assertFalse(frontier_lawless_conflict("settled", "lawless"))
        self.assertFalse(frontier_lawless_conflict(None, "lawless"))

    def test_both_empty_ok(self):
        self.assertFalse(frontier_lawless_conflict(None, None))
        self.assertFalse(frontier_lawless_conflict("", ""))


# ──────────────────────────────────────────────────────────────────────
# Reward multiplier
# ──────────────────────────────────────────────────────────────────────

class TestRewardMultiplier(unittest.TestCase):

    def test_multipliers_increase_with_band(self):
        m = [reward_multiplier(b) for b in
             (ThreatBand.FRONTIER, ThreatBand.SETTLED,
              ThreatBand.CONTESTED_MARCHES, ThreatBand.WILDS)]
        self.assertEqual(m, sorted(m))   # monotonic increasing

    def test_settled_is_baseline_1x(self):
        self.assertEqual(reward_multiplier(ThreatBand.SETTLED), 1.0)

    def test_frontier_below_one_wilds_above_one(self):
        self.assertLess(reward_multiplier(ThreatBand.FRONTIER), 1.0)
        self.assertGreater(reward_multiplier(ThreatBand.WILDS), 1.0)


# ──────────────────────────────────────────────────────────────────────
# Live world loads clean with the new validation
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.slow  # heavy: build
class TestWorldLoadsCleanWithValidation(unittest.TestCase):
    """DIFF.1 adds a frontier≠lawless validator to validate_world. The
    live CW world (no threat_band tags yet) must still load with zero
    new errors — proving the axis ships behavior-neutral."""

    def test_cw_world_validates_clean(self):
        from engine.world_loader import (
            load_era_manifest, load_planets, load_zones, validate_world,
        )
        manifest = load_era_manifest(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars")
        zones = load_zones(manifest)
        unresolved: list = []
        rooms, exits = load_planets(manifest, unresolved_report=unresolved)
        report = validate_world(zones, rooms, exits)
        # No frontier/lawless conflicts in the untagged world.
        conflict_errs = [e for e in report.errors
                         if "threat_band=frontier" in e]
        self.assertEqual(
            conflict_errs, [],
            f"Unexpected frontier/lawless conflicts: {conflict_errs}")
        # And the world as a whole still validates with no errors.
        self.assertEqual(
            report.errors, [],
            f"validate_world reported errors: {report.errors[:5]}")


if __name__ == "__main__":
    unittest.main()
