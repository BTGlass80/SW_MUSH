# -*- coding: utf-8 -*-
"""tests/test_director_fidelity_slice2.py — adaptive-spend governor slice 2.

director_scope_and_adaptive_spend_v1.md §5 + Brian decisions E/F/G: the manual
`@director fidelity` cadence override (DirectorAI.set_manual_fidelity) and the
LLM `recommend_fidelity` advisory (DirectorAI._set_recommend_fidelity), both
surfaced through governor_state(). In-memory (restart -> auto); spend stays
bounded by the ClaudeProvider circuit breaker regardless of the pinned tier.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestManualFidelity(unittest.TestCase):
    def test_pin_valid_tier_applies_interval(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        ok, msg = d.set_manual_fidelity("high")
        self.assertTrue(ok)
        self.assertEqual(d._manual_fidelity, "high")
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["high"])
        self.assertIn("HIGH", msg.upper())

    def test_max_is_allowed_manual_only_tier(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        ok, msg = d.set_manual_fidelity("max")
        self.assertTrue(ok)
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["max"])

    def test_auto_clears_the_pin(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d.set_manual_fidelity("eco")
        self.assertEqual(d._manual_fidelity, "eco")
        ok, msg = d.set_manual_fidelity("auto")
        self.assertTrue(ok)
        self.assertIsNone(d._manual_fidelity)

    def test_none_clears_the_pin(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d.set_manual_fidelity("high")
        ok, _ = d.set_manual_fidelity(None)
        self.assertTrue(ok)
        self.assertIsNone(d._manual_fidelity)

    def test_invalid_tier_rejected_no_state_change(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        before_interval = d._turn_interval
        ok, msg = d.set_manual_fidelity("ludicrous")
        self.assertFalse(ok)
        self.assertIsNone(d._manual_fidelity)        # unchanged
        self.assertEqual(d._turn_interval, before_interval)
        self.assertIn("ludicrous", msg)

    def test_case_insensitive(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        ok, _ = d.set_manual_fidelity("HIGH")
        self.assertTrue(ok)
        self.assertEqual(d._manual_fidelity, "high")

    def test_uppercase_auto_clears(self):
        # The clear-path must normalize case (code-review finding 2).
        from engine.director import DirectorAI
        d = DirectorAI()
        d.set_manual_fidelity("high")
        ok, _ = d.set_manual_fidelity("AUTO")
        self.assertTrue(ok)
        self.assertIsNone(d._manual_fidelity)

    def test_off_and_whitespace_clear(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d.set_manual_fidelity("high")
        ok, _ = d.set_manual_fidelity("  OFF  ")
        self.assertTrue(ok)
        self.assertIsNone(d._manual_fidelity)


class TestSkipPathRespectsPin(unittest.TestCase):
    """An empty-server skip must not demote a manual pin to eco (finding 1).
    The skip branch of _governed_turn uses neither db nor session_mgr."""

    def test_skip_preserves_manual_pin(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        d.set_manual_fidelity("high")
        _run(d._governed_turn(None, None, online=0, now=10000.0))  # empty -> skip
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["high"])
        self.assertEqual(d._manual_fidelity, "high")

    def test_skip_relaxes_to_eco_when_auto(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        d._turn_interval = FIDELITY_INTERVALS["high"]  # was fast, but auto-mode
        _run(d._governed_turn(None, None, online=0, now=10000.0))  # empty -> skip
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["eco"])

    def test_governor_state_reflects_pin(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d.set_manual_fidelity("eco")
        gs = d.governor_state()
        self.assertEqual(gs["manual_fidelity"], "eco")
        self.assertEqual(gs["tier"], "eco")


class TestRecommendFidelity(unittest.TestCase):
    def test_valid_string_advisory_stored(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d._set_recommend_fidelity("high")
        self.assertEqual(d._last_recommend_fidelity, {"tier": "high", "reason": ""})

    def test_dict_advisory_with_reason(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d._set_recommend_fidelity({"tier": "max", "reason": "kyber cornered"})
        self.assertEqual(d._last_recommend_fidelity,
                         {"tier": "max", "reason": "kyber cornered"})

    def test_invalid_tier_clears_advisory(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d._set_recommend_fidelity("high")           # set one
        d._set_recommend_fidelity("nonsense")        # a turn that doesn't recommend
        self.assertIsNone(d._last_recommend_fidelity)

    def test_none_clears_advisory(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d._set_recommend_fidelity("eco")
        d._set_recommend_fidelity(None)
        self.assertIsNone(d._last_recommend_fidelity)

    def test_advisory_is_surfaced_in_governor_state(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        self.assertIsNone(d.governor_state()["recommend_fidelity"])  # default
        d._set_recommend_fidelity({"tier": "high", "reason": "8 players"})
        self.assertEqual(d.governor_state()["recommend_fidelity"]["tier"], "high")

    def test_reason_is_capped(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d._set_recommend_fidelity({"tier": "high", "reason": "x" * 500})
        self.assertLessEqual(len(d._last_recommend_fidelity["reason"]), 200)


class TestSlice2DoesNotAutoAct(unittest.TestCase):
    """The advisory is admin-facing only — it must never move the live cadence."""
    def test_advisory_does_not_change_turn_interval(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        before = d._turn_interval
        d._set_recommend_fidelity({"tier": "max", "reason": "burst"})
        self.assertEqual(d._turn_interval, before)        # untouched
        self.assertIsNone(d._manual_fidelity)              # still auto


if __name__ == "__main__":
    unittest.main()
