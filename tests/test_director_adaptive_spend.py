# -*- coding: utf-8 -*-
"""tests/test_director_adaptive_spend.py — DIRECTOR.adaptive_spend slice 1
(skip-empty-turns + the auto SpendGovernor cadence controller).

Design: director_scope_and_adaptive_spend_v1.md §5 + Brian decisions D/E.
Cadence is the only spend knob; the governor moves _turn_interval within a
budget ceiling and skips the paid turn on an empty server (with a bounded
overnight catch-up). Manual fidelity + the LLM advisory field are slice 2.
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class _Sess:
    def __init__(self, in_game=True):
        self.is_in_game = in_game


class _SessionMgr:
    def __init__(self, n_online=0, n_offline=0):
        self.all = ([_Sess(True)] * n_online) + ([_Sess(False)] * n_offline)


class _BudgetDB:
    """Stub DB whose get_budget_stats reflects a chosen month-to-date spend."""
    def __init__(self, total_input=0, total_output=0):
        self._ti, self._to = total_input, total_output

    async def fetchall(self, sql, params=()):
        return [{"total_input": self._ti, "total_output": self._to,
                 "call_count": 1}]


class TestCountOnline(unittest.TestCase):
    def test_counts_only_in_game(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        self.assertEqual(d._count_online(_SessionMgr(3, 2)), 3)
        self.assertEqual(d._count_online(_SessionMgr(0, 4)), 0)


class TestSkipEmpty(unittest.TestCase):
    def test_busy_server_never_skips(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        skip, _ = d._should_skip_turn(online=3, now=1_000_000.0)
        self.assertFalse(skip)

    def test_empty_server_skips(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d._last_executed_turn_time = 999_000.0  # ran recently
        skip, reason = d._should_skip_turn(online=0, now=1_000_000.0)
        self.assertTrue(skip)
        self.assertIn("skip-empty", reason)

    def test_one_player_skips(self):
        from engine.director import DirectorAI, SKIP_EMPTY_MAX_PLAYERS
        self.assertEqual(SKIP_EMPTY_MAX_PLAYERS, 1)
        d = DirectorAI()
        d._last_executed_turn_time = 999_000.0
        skip, _ = d._should_skip_turn(online=1, now=1_000_000.0)
        self.assertTrue(skip)

    def test_overnight_catchup_fires_once(self):
        from engine.director import (
            DirectorAI, OVERNIGHT_CATCHUP_SECONDS, OVERNIGHT_CATCHUP_LOOKBACK)
        d = DirectorAI()
        now = 1_000_000.0
        # Stale (last real turn well beyond the catch-up gap) but players were
        # seen within the lookback window -> fire one catch-up (do NOT skip).
        d._last_executed_turn_time = now - OVERNIGHT_CATCHUP_SECONDS - 10
        d._last_populated_time = now - (OVERNIGHT_CATCHUP_LOOKBACK // 2)
        skip, reason = d._should_skip_turn(online=0, now=now)
        self.assertFalse(skip)
        self.assertIn("catch-up", reason)

    def test_no_catchup_if_never_populated(self):
        from engine.director import DirectorAI, OVERNIGHT_CATCHUP_SECONDS
        d = DirectorAI()
        now = 1_000_000.0
        d._last_executed_turn_time = now - OVERNIGHT_CATCHUP_SECONDS - 10
        d._last_populated_time = 0.0  # never saw players
        skip, _ = d._should_skip_turn(online=0, now=now)
        self.assertTrue(skip)  # nobody to wake up for


class TestAutoGovernor(unittest.TestCase):
    def test_quiet_drops_to_eco(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        _run(d._apply_governor(_BudgetDB(), online=1))
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["eco"])

    def test_steady_is_standard(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        _run(d._apply_governor(_BudgetDB(), online=2))
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["standard"])

    def test_busy_escalates_to_high_under_budget(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        _run(d._apply_governor(_BudgetDB(total_input=0, total_output=0), online=5))
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["high"])

    def test_budget_guard_blocks_auto_escalation_past_ceiling(self):
        from engine.director import (
            DirectorAI, FIDELITY_INTERVALS, GOVERNOR_AUTO_CEILING_USD)
        d = DirectorAI()
        # Construct a spend already over the $30 auto ceiling: output tokens at
        # $5/MTok -> need > 6,000,000 output tokens for >$30.
        big_out = int((GOVERNOR_AUTO_CEILING_USD / 5.0) * 1_000_000) + 1_000_000
        _run(d._apply_governor(_BudgetDB(total_output=big_out), online=8))
        # Even with 8 players, the guard holds cadence at standard, not high.
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["standard"])
        self.assertIn("budget guard", d._last_fidelity_reason)

    def test_high_roi_digest_escalates(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        d._digest.contraband_sold = 9  # high-ROI proxy
        _run(d._apply_governor(_BudgetDB(), online=2))
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["high"])


class TestManualFidelityPin(unittest.TestCase):
    def test_manual_pins_cadence_and_ignores_heuristic(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        d._manual_fidelity = "max"
        _run(d._apply_governor(_BudgetDB(), online=0))  # would be eco on auto
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["max"])
        self.assertIn("manual", d._last_fidelity_reason)


class TestGovernorState(unittest.TestCase):
    def test_state_reports_tier(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        d._turn_interval = FIDELITY_INTERVALS["high"]
        st = d.governor_state()
        self.assertEqual(st["tier"], "high")
        self.assertEqual(st["interval_seconds"], FIDELITY_INTERVALS["high"])


class TestGovernedTurnSkips(unittest.TestCase):
    def test_governed_turn_skips_empty_without_running(self):
        from engine.director import DirectorAI, FIDELITY_INTERVALS
        d = DirectorAI()
        d._enabled = True
        ran = {"v": False}

        async def _fake_turn(db, sm):
            ran["v"] = True
        d._safe_faction_turn = _fake_turn  # type: ignore

        d._last_executed_turn_time = 999_000.0  # recent -> no catch-up
        _run(d._governed_turn(_BudgetDB(), _SessionMgr(0), online=0, now=1_000_000.0))
        self.assertFalse(ran["v"], "empty server must not run the paid turn")
        self.assertEqual(d._turn_interval, FIDELITY_INTERVALS["eco"])

    def test_governed_turn_runs_when_busy(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d._enabled = True
        ran = {"v": False}

        async def _fake_turn(db, sm):
            ran["v"] = True
        d._safe_faction_turn = _fake_turn  # type: ignore

        now = 1_000_000.0
        _run(d._governed_turn(_BudgetDB(), _SessionMgr(3), online=3, now=now))
        self.assertTrue(ran["v"])
        self.assertEqual(d._last_executed_turn_time, now)


if __name__ == "__main__":
    unittest.main()
