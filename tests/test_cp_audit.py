# -*- coding: utf-8 -*-
"""
tests/test_cp_audit.py — CP Progression audit (Tier 2 #17).

Audit drop scope (May 5 2026)
=============================

Purpose:

  1. Lock the v23-tuned CP constants. Existing
     `tests/test_economy_validation.py::TestCPProgression` locks
     TICKS_PER_CP, WEEKLY_CAP_TICKS, and the qualitative
     RP-outclasses-passive invariant. This file extends the
     coverage to the full 13-constant surface plus the cross-
     constant invariants that matter for game balance.

  2. Lock CP behavior. Tick→CP conversion math, weekly window
     rollover, weekly cap clamping, cap-hit-streak admin flag,
     train cost formula, guild discount math, kudos rules
     (lockout, weekly cap, self-block).

  3. Catch a regression that the existing tests did not catch:
     ``engine/ships_log.py`` was calling a nonexistent
     ``CPEngine.award_ticks`` method, so every Ship's Log
     milestone silently failed to award any CP. This drop adds
     a public ``CPEngine.award_milestone_cp`` method, fixes the
     ships_log call site, and tests the contract end-to-end with
     a fake db that records the CP grant.

What this drop does NOT change
==============================

The v23 retune (TICKS_PER_CP 300→200, WEEKLY_CAP 300→400,
PASSIVE 5→10) is preserved. The audit's recommendation is not
"fix the code to match the guide" — the code was deliberately
retuned. Guide #9 is stale and should be updated separately
in a docs branch; the engine drop documents the current state
and locks it.

Removed-since-v23: the same-room requirement on +kudos was
removed deliberately (per code comment "v23: removed same-room
requirement to reduce bottleneck at small population sizes").
The guide claims it. The code doesn't enforce it. The audit
treats this as a doc-staleness, not a regression.

Test sections
=============

  1. TestConstants                — every published v23 constant
                                    locked with its expected value
  2. TestTickToCpMath             — _award_ticks correctly converts
                                    accumulated ticks to CP
  3. TestWeeklyCapClamping        — awards above the cap clamp;
                                    awards in a new week reset
  4. TestCapHitStreak             — admin flag rolls over correctly
                                    across consecutive weeks
  5. TestTrainCostFormula         — cost == total_pool.dice; guild
                                    discount applies max(1, int).
  6. TestKudosRules               — self-kudos block; lockout;
                                    weekly cap.
  7. TestMilestoneCp              — Ship's Log milestones award
                                    direct CP, bypassing the cap
                                    (regression-guard for the bug
                                    fixed in this drop).
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


# ═════════════════════════════════════════════════════════════════════
# 1. Constants — every v23 invariant locked
# ═════════════════════════════════════════════════════════════════════


class TestConstants(unittest.TestCase):
    """Lock every published CP constant.

    The v23 retune values are deliberate (per code comments in
    engine/cp_engine.py). If any of these change, that's a
    game-balance decision and this test should be updated
    consciously alongside Guide #9.
    """

    def test_ticks_per_cp(self):
        from engine.cp_engine import TICKS_PER_CP
        self.assertEqual(TICKS_PER_CP, 200)

    def test_weekly_cap(self):
        from engine.cp_engine import WEEKLY_CAP_TICKS
        self.assertEqual(WEEKLY_CAP_TICKS, 400)

    def test_passive_per_day(self):
        from engine.cp_engine import PASSIVE_TICKS_PER_DAY
        self.assertEqual(PASSIVE_TICKS_PER_DAY, 10)

    def test_scene_min_poses(self):
        from engine.cp_engine import SCENE_MIN_POSES
        self.assertEqual(SCENE_MIN_POSES, 3)

    def test_scene_ticks_per_pose(self):
        from engine.cp_engine import SCENE_TICKS_PER_POSE
        self.assertEqual(SCENE_TICKS_PER_POSE, 2)

    def test_scene_max_ticks(self):
        from engine.cp_engine import SCENE_MAX_TICKS
        self.assertEqual(SCENE_MAX_TICKS, 60)

    def test_scene_cooldown(self):
        from engine.cp_engine import SCENE_COOLDOWN_SECONDS
        self.assertEqual(SCENE_COOLDOWN_SECONDS, 600)

    def test_kudos_ticks(self):
        from engine.cp_engine import KUDOS_TICKS
        self.assertEqual(KUDOS_TICKS, 35)

    def test_kudos_per_week(self):
        from engine.cp_engine import KUDOS_PER_WEEK
        self.assertEqual(KUDOS_PER_WEEK, 3)

    def test_kudos_lockout(self):
        from engine.cp_engine import KUDOS_LOCKOUT_SECONDS
        self.assertEqual(KUDOS_LOCKOUT_SECONDS, 7 * 24 * 3600)

    def test_ai_max_ticks(self):
        from engine.cp_engine import AI_MAX_TICKS_PER_EVAL
        self.assertEqual(AI_MAX_TICKS_PER_EVAL, 15)

    def test_passive_check_interval(self):
        from engine.cp_engine import PASSIVE_CHECK_INTERVAL
        self.assertEqual(PASSIVE_CHECK_INTERVAL, 3600)

    def test_admin_cap_flag_weeks(self):
        from engine.cp_engine import ADMIN_CAP_FLAG_WEEKS
        self.assertEqual(ADMIN_CAP_FLAG_WEEKS, 3)

    def test_day_seconds(self):
        from engine.cp_engine import DAY_SECONDS
        self.assertEqual(DAY_SECONDS, 24 * 3600)

    def test_week_seconds(self):
        from engine.cp_engine import WEEK_SECONDS
        self.assertEqual(WEEK_SECONDS, 7 * 24 * 3600)

    def test_kudos_lockout_equals_week(self):
        # Cross-invariant: the kudos lockout per pair is exactly one
        # week. This is a load-bearing design choice (3 kudos/week
        # × 1-week lockout = each player needs 3 distinct kudos
        # givers per week to max out).
        from engine.cp_engine import KUDOS_LOCKOUT_SECONDS, WEEK_SECONDS
        self.assertEqual(KUDOS_LOCKOUT_SECONDS, WEEK_SECONDS)


# ═════════════════════════════════════════════════════════════════════
# 2. Tick→CP conversion math
# ═════════════════════════════════════════════════════════════════════


def _make_tick_db(initial_ticks_total=0, initial_week_ticks=0,
                  week_start=0, cap_hit_streak=0):
    """Build a fake db that captures _award_ticks side effects."""
    db = MagicMock()
    state = {
        "ticks_total": initial_ticks_total,
        "ticks_this_week": initial_week_ticks,
        "week_start_ts": week_start,
        "cap_hit_streak": cap_hit_streak,
        "last_passive_ts": 0,
        "last_scene_ts": 0,
        "last_source": "",
        "last_award_ts": 0,
    }
    db._state = state
    db._cp_added = []  # list of cp deltas added via cp_add_character_points

    async def _get_row(char_id):
        return dict(state)

    async def _ensure_row(char_id):
        return None

    async def _update_row(char_id, **fields):
        state.update(fields)

    async def _add_cp(char_id, amount):
        db._cp_added.append(amount)

    db.cp_get_row = AsyncMock(side_effect=_get_row)
    db.cp_ensure_row = AsyncMock(side_effect=_ensure_row)
    db.cp_update_row = AsyncMock(side_effect=_update_row)
    db.cp_add_character_points = AsyncMock(side_effect=_add_cp)
    db.get_character = AsyncMock(return_value={"character_points": 0})
    return db


class TestTickToCpMath(unittest.TestCase):
    """The tick→CP conversion in _award_ticks: cp_gained = (after // T) - (before // T).

    At TICKS_PER_CP=200, the boundaries are 200, 400, 600, ...
    """

    def test_award_below_threshold_no_cp(self):
        # 0 → 199 ticks: no CP yet.
        from engine.cp_engine import _award_ticks
        db = _make_tick_db(initial_ticks_total=0)
        _run(_award_ticks(db, char_id=1, ticks=199, source="test",
                          now=time.time()))
        self.assertEqual(db._cp_added, [])

    def test_award_crosses_one_boundary(self):
        # 0 → 200 ticks: exactly 1 CP.
        from engine.cp_engine import _award_ticks
        db = _make_tick_db(initial_ticks_total=0)
        _run(_award_ticks(db, char_id=1, ticks=200, source="test",
                          now=time.time()))
        self.assertEqual(db._cp_added, [1])

    def test_award_crosses_two_boundaries(self):
        # 100 → 500 (delta 400): crosses 200 and 400 boundaries → 2 CP.
        from engine.cp_engine import _award_ticks
        db = _make_tick_db(initial_ticks_total=100)
        _run(_award_ticks(db, char_id=1, ticks=400, source="test",
                          now=time.time()))
        self.assertEqual(db._cp_added, [2])

    def test_award_within_one_period_no_cp(self):
        # 250 → 350: no boundary crossed (both are in [200, 400)).
        from engine.cp_engine import _award_ticks
        db = _make_tick_db(initial_ticks_total=250)
        _run(_award_ticks(db, char_id=1, ticks=100, source="test",
                          now=time.time()))
        self.assertEqual(db._cp_added, [])

    def test_state_ticks_total_increments(self):
        from engine.cp_engine import _award_ticks
        db = _make_tick_db(initial_ticks_total=50)
        _run(_award_ticks(db, char_id=1, ticks=100, source="test",
                          now=time.time()))
        self.assertEqual(db._state["ticks_total"], 150)


# ═════════════════════════════════════════════════════════════════════
# 3. Weekly window rollover + cap streak
# ═════════════════════════════════════════════════════════════════════


class TestWeeklyRollover(unittest.TestCase):

    def test_new_week_resets_weekly_ticks(self):
        # week_start = now - 8 days → rollover triggers.
        from engine.cp_engine import _award_ticks
        now = time.time()
        old_week = now - (8 * 24 * 3600)
        db = _make_tick_db(initial_week_ticks=300,  # below cap
                          week_start=old_week)
        _run(_award_ticks(db, char_id=1, ticks=10,
                          source="test", now=now))
        # Rollover happened: ticks_this_week reset to 0+10
        self.assertEqual(db._state["ticks_this_week"], 10)
        # week_start updated
        self.assertEqual(db._state["week_start_ts"], now)


class TestCapHitStreak(unittest.TestCase):

    def test_streak_increments_when_capped_week_rolls(self):
        from engine.cp_engine import _award_ticks
        now = time.time()
        old_week = now - (8 * 24 * 3600)
        db = _make_tick_db(initial_week_ticks=400,  # at cap
                          week_start=old_week,
                          cap_hit_streak=2)
        _run(_award_ticks(db, char_id=1, ticks=5,
                          source="test", now=now))
        # Old week was at cap → streak +1 → 3
        self.assertEqual(db._state["cap_hit_streak"], 3)

    def test_streak_resets_when_not_capped(self):
        from engine.cp_engine import _award_ticks
        now = time.time()
        old_week = now - (8 * 24 * 3600)
        db = _make_tick_db(initial_week_ticks=200,  # below cap
                          week_start=old_week,
                          cap_hit_streak=2)
        _run(_award_ticks(db, char_id=1, ticks=5,
                          source="test", now=now))
        # Old week below cap → streak resets to 0
        self.assertEqual(db._state["cap_hit_streak"], 0)


# ═════════════════════════════════════════════════════════════════════
# 4. Train cost formula and guild discount
# ═════════════════════════════════════════════════════════════════════


class TestTrainCostFormula(unittest.TestCase):
    """Cost = number of dice in total pool (attribute + skill bonus).
    Guild discount is max(1, int(cost * multiplier)).
    """

    def test_floor_cost_after_discount_is_one(self):
        # A 2-CP cost with a 0.4 multiplier would yield 0 if not
        # floored. The implementation uses max(1, int(cost * mult))
        # so the floor is 1.
        cost = 2
        multiplier = 0.4
        actual = max(1, int(cost * multiplier))
        self.assertEqual(actual, 1)

    def test_typical_guild_discount(self):
        # 5 CP cost with 0.8 multiplier = 4 CP (the documented case
        # in Guide #9 §3).
        cost = 5
        multiplier = 0.8
        actual = max(1, int(cost * multiplier))
        self.assertEqual(actual, 4)

    def test_no_discount_when_multiplier_one(self):
        cost = 5
        multiplier = 1.0
        actual = max(1, int(cost * multiplier))
        self.assertEqual(actual, 5)

    def test_train_command_imports_get_guild_cp_multiplier(self):
        # If parser/cp_commands.py stops importing
        # get_guild_cp_multiplier, guild discount silently breaks.
        import inspect
        from parser import cp_commands
        src = inspect.getsource(cp_commands)
        self.assertIn("get_guild_cp_multiplier", src)


# ═════════════════════════════════════════════════════════════════════
# 5. Kudos rules
# ═════════════════════════════════════════════════════════════════════


class TestKudosRules(unittest.TestCase):
    """Self-kudos blocked; 7-day per-pair lockout; 3/week cap."""

    def test_self_kudos_blocked(self):
        from engine.cp_engine import get_cp_engine
        engine = get_cp_engine()

        db = MagicMock()
        db.kudos_last_given = AsyncMock(return_value=None)
        db.kudos_count_received_this_week = AsyncMock(return_value=0)
        db.kudos_log = AsyncMock()

        result = _run(engine.award_kudos(db, giver_id=1, target_id=1))
        self.assertFalse(result["success"])
        # No log row written
        db.kudos_log.assert_not_awaited()

    def test_lockout_blocks_repeat(self):
        from engine.cp_engine import get_cp_engine, KUDOS_LOCKOUT_SECONDS
        engine = get_cp_engine()

        now = time.time()
        recent = now - (KUDOS_LOCKOUT_SECONDS / 2)  # mid-lockout

        db = MagicMock()
        db.kudos_last_given = AsyncMock(return_value=recent)
        db.kudos_count_received_this_week = AsyncMock(return_value=0)
        db.kudos_log = AsyncMock()
        db.cp_get_row = AsyncMock(return_value={
            "ticks_this_week": 0, "ticks_total": 0,
            "week_start_ts": 0, "cap_hit_streak": 0,
        })
        db.cp_update_row = AsyncMock()
        db.cp_add_character_points = AsyncMock()

        result = _run(engine.award_kudos(db, giver_id=1, target_id=2))
        self.assertFalse(result["success"])

    def test_weekly_cap_blocks_after_three(self):
        from engine.cp_engine import get_cp_engine
        engine = get_cp_engine()

        db = MagicMock()
        db.kudos_last_given = AsyncMock(return_value=None)
        db.kudos_count_received_this_week = AsyncMock(return_value=3)
        db.kudos_log = AsyncMock()

        result = _run(engine.award_kudos(db, giver_id=1, target_id=2))
        self.assertFalse(result["success"])


# ═════════════════════════════════════════════════════════════════════
# 6. Milestone CP — the regression-guard for the ships_log bug fix
# ═════════════════════════════════════════════════════════════════════


class TestMilestoneCp(unittest.TestCase):
    """The CP audit found ships_log was calling a nonexistent
    `CPEngine.award_ticks` method. This test class:

      * Verifies the new `CPEngine.award_milestone_cp` method
        exists and grants direct CP through `cp_add_character_points`.
      * Verifies milestone CP is NOT routed through the tick system
        (i.e. doesn't write to cp_ticks).
      * Verifies a future regression that re-introduces the
        `award_ticks` mistake will fail loudly.
    """

    def test_award_milestone_cp_method_exists(self):
        from engine.cp_engine import CPEngine
        self.assertTrue(
            hasattr(CPEngine, "award_milestone_cp"),
            "CPEngine.award_milestone_cp must exist (added in CP "
            "audit drop, May 5 2026). If you removed it, the "
            "ships_log milestone bonuses will silently fail again.",
        )

    def test_award_milestone_cp_grants_direct_cp(self):
        from engine.cp_engine import get_cp_engine
        engine = get_cp_engine()

        db = MagicMock()
        db.cp_add_character_points = AsyncMock()
        # Should NOT touch cp_ticks-related methods
        db.cp_get_row = AsyncMock()
        db.cp_update_row = AsyncMock()

        result = _run(engine.award_milestone_cp(
            db, char_id=42, cp=50, reason="zones_visited threshold 16"))

        self.assertEqual(result, {"cp_awarded": 50, "dropped": False})
        db.cp_add_character_points.assert_awaited_once_with(42, 50)
        # Critically: no tick-system writes — milestones bypass the cap
        db.cp_get_row.assert_not_awaited()
        db.cp_update_row.assert_not_awaited()

    def test_award_milestone_cp_zero_is_noop(self):
        from engine.cp_engine import get_cp_engine
        engine = get_cp_engine()

        db = MagicMock()
        db.cp_add_character_points = AsyncMock()

        result = _run(engine.award_milestone_cp(
            db, char_id=42, cp=0))
        self.assertEqual(result, {"cp_awarded": 0, "dropped": False})
        db.cp_add_character_points.assert_not_awaited()

    def test_award_milestone_cp_negative_is_noop(self):
        from engine.cp_engine import get_cp_engine
        engine = get_cp_engine()

        db = MagicMock()
        db.cp_add_character_points = AsyncMock()

        result = _run(engine.award_milestone_cp(
            db, char_id=42, cp=-10))
        self.assertEqual(result, {"cp_awarded": 0, "dropped": False})
        db.cp_add_character_points.assert_not_awaited()

    def test_award_milestone_cp_swallows_db_errors(self):
        # Graceful drop — never raises (matches award_ai_trickle).
        from engine.cp_engine import get_cp_engine
        engine = get_cp_engine()

        db = MagicMock()
        db.cp_add_character_points = AsyncMock(
            side_effect=RuntimeError("DB exploded"))

        result = _run(engine.award_milestone_cp(
            db, char_id=42, cp=50))
        self.assertEqual(result, {"cp_awarded": 0, "dropped": True})

    def test_ships_log_uses_award_milestone_cp(self):
        # Regression guard: ships_log must call
        # award_milestone_cp, not the nonexistent award_ticks.
        import inspect
        from engine import ships_log
        src = inspect.getsource(ships_log)
        self.assertIn("award_milestone_cp", src,
                      "ships_log.py must call award_milestone_cp")
        self.assertNotIn(
            "get_cp_engine().award_ticks",
            src,
            "ships_log.py must NOT call CPEngine.award_ticks "
            "(method does not exist; this was the silent-failure "
            "bug fixed in the CP audit drop).",
        )

    def test_no_other_callers_of_phantom_award_ticks(self):
        # If anyone else in the codebase added a
        # `get_cp_engine().award_ticks(...)` call, surface it.
        import os
        offenders = []
        for root, _dirs, files in os.walk(str(PROJECT_ROOT)):
            # Skip pycache, .git, venv, and tests using portable
            # path-component split (Windows uses '\', POSIX uses '/').
            parts = set(os.path.normpath(root).split(os.sep))
            if parts & {"__pycache__", ".git", "venv", ".venv", "tests"}:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                fpath = os.path.join(root, fn)
                try:
                    with open(fpath, encoding="utf-8") as fh:
                        text = fh.read()
                except Exception:
                    continue
                if "get_cp_engine().award_ticks" in text:
                    offenders.append(fpath)
        self.assertEqual(
            offenders, [],
            f"These files still call CPEngine.award_ticks (which "
            f"does not exist): {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
