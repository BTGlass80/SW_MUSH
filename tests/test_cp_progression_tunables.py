# -*- coding: utf-8 -*-
"""tests/test_cp_progression_tunables.py — T3.19 config breadth (CP faucet).

The WRITE-side complement to the CP-income telemetry sweep: the
``@balance progression`` board OBSERVES the tick economy (cp_income by source +
weekly-cap pressure, paired with the cp_spend sink); this drop lets an operator
TUNE it without a code edit by externalizing the CP progression faucet's nine
reward/cap levers to ``data/tunables.yaml`` under ``cp.*``, read at the use site
via the live accessors in ``engine/cp_engine.py``.

Coverage:
  * the accessors — default fallback, override, negative clamp (ticks_per_cp
    clamps to >= 1 not 0, since it is the tick→CP DIVISOR), null + bad-value
    fallback, float→int coercion;
  * the overrides flow through the REAL award paths (scene / kudos / passive /
    _award_ticks conversion + cap), and a 0/negative ticks_per_cp can never
    raise ZeroDivisionError on a real award;
  * behaviour-identical to today when the YAML is unset;
  * drift pins — the shipped YAML carries the nine keys at the in-code defaults,
    the accessors read via get_tunable, and every decision site (engine +
    the cp_commands display + the session HUD) calls the accessors, not the
    frozen constants.

Pure unit tests: in-memory stub DBs, no disk, no network.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
REPO = Path(PROJECT_ROOT)

from engine import cp_engine as cp  # noqa: E402
from engine import tunables  # noqa: E402
from engine import telemetry  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# The nine externalized levers: tunable key → in-code constant name.
_KEYS = {
    "cp.ticks_per_cp": "TICKS_PER_CP",
    "cp.weekly_cap_ticks": "WEEKLY_CAP_TICKS",
    "cp.passive_ticks_per_day": "PASSIVE_TICKS_PER_DAY",
    "cp.scene_min_poses": "SCENE_MIN_POSES",
    "cp.scene_ticks_per_pose": "SCENE_TICKS_PER_POSE",
    "cp.scene_max_ticks": "SCENE_MAX_TICKS",
    "cp.kudos_ticks": "KUDOS_TICKS",
    "cp.kudos_per_week": "KUDOS_PER_WEEK",
    "cp.ai_max_ticks_per_eval": "AI_MAX_TICKS_PER_EVAL",
}

# tunable key → accessor function (same order as _KEYS).
_ACCESSORS = {
    "cp.ticks_per_cp": cp.ticks_per_cp,
    "cp.weekly_cap_ticks": cp.weekly_cap_ticks,
    "cp.passive_ticks_per_day": cp.passive_ticks_per_day,
    "cp.scene_min_poses": cp.scene_min_poses,
    "cp.scene_ticks_per_pose": cp.scene_ticks_per_pose,
    "cp.scene_max_ticks": cp.scene_max_ticks,
    "cp.kudos_ticks": cp.kudos_ticks,
    "cp.kudos_per_week": cp.kudos_per_week,
    "cp.ai_max_ticks_per_eval": cp.ai_max_ticks_per_eval,
}


class _CpDB:
    """In-memory cp_ticks + character_points + kudos log so the real award
    paths run end-to-end with no DB."""

    def __init__(self, *, ticks_total=0, ticks_this_week=0, week_start_ts=0):
        self.row = {
            "ticks_total": ticks_total,
            "ticks_this_week": ticks_this_week,
            "week_start_ts": week_start_ts,
            "cap_hit_streak": 0,
            "last_passive_ts": 0,
            "last_scene_ts": 0,
        }
        self.cp = 0
        self.kudos_records: list = []
        self._kudos_received = 0
        self._last_given: dict = {}

    async def cp_get_row(self, char_id):
        return dict(self.row)

    async def cp_ensure_row(self, char_id):
        pass

    async def cp_update_row(self, char_id, **updates):
        self.row.update(updates)

    async def cp_add_character_points(self, char_id, cp_amount):
        self.cp += cp_amount

    async def get_character(self, char_id):
        return {"character_points": self.cp}

    async def kudos_last_given(self, giver_id, target_id):
        return self._last_given.get((giver_id, target_id))

    async def kudos_count_received_this_week(self, target_id):
        return self._kudos_received

    async def kudos_log(self, giver_id, target_id, ticks, now):
        self.kudos_records.append((giver_id, target_id, ticks, now))
        self._last_given[(giver_id, target_id)] = now


# ══════════════════════════════════════════════════════════════════════════
# 1. The accessors — value logic in isolation
# ══════════════════════════════════════════════════════════════════════════
class CpProgressionTunableAccessors(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        for key, accessor in _ACCESSORS.items():
            self.assertEqual(accessor(), getattr(cp, _KEYS[key]),
                             f"{key} default mismatch")

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "cp.ticks_per_cp": 150,
            "cp.weekly_cap_ticks": 500,
            "cp.passive_ticks_per_day": 20,
            "cp.scene_min_poses": 2,
            "cp.scene_ticks_per_pose": 5,
            "cp.scene_max_ticks": 80,
            "cp.kudos_ticks": 50,
            "cp.kudos_per_week": 5,
            "cp.ai_max_ticks_per_eval": 25,
        })
        self.assertEqual(cp.ticks_per_cp(), 150)
        self.assertEqual(cp.weekly_cap_ticks(), 500)
        self.assertEqual(cp.passive_ticks_per_day(), 20)
        self.assertEqual(cp.scene_min_poses(), 2)
        self.assertEqual(cp.scene_ticks_per_pose(), 5)
        self.assertEqual(cp.scene_max_ticks(), 80)
        self.assertEqual(cp.kudos_ticks(), 50)
        self.assertEqual(cp.kudos_per_week(), 5)
        self.assertEqual(cp.ai_max_ticks_per_eval(), 25)

    def test_magnitudes_clamp_negative_to_zero(self):
        # A fat-fingered negative income/cap lever can never become a tick DEBIT.
        for key in ("cp.weekly_cap_ticks", "cp.passive_ticks_per_day",
                    "cp.scene_min_poses", "cp.scene_ticks_per_pose",
                    "cp.scene_max_ticks", "cp.kudos_ticks", "cp.kudos_per_week",
                    "cp.ai_max_ticks_per_eval"):
            tunables._TUNABLES[key] = -10
            self.assertEqual(_ACCESSORS[key](), 0, f"{key} should clamp to 0")
            tunables.reset_tunables()

    def test_ticks_per_cp_clamps_to_one_not_zero(self):
        # ticks_per_cp is the tick→CP DIVISOR — a 0 or negative must floor to 1,
        # never 0 (ZeroDivisionError on the next award).
        for bad in (0, -50):
            tunables._TUNABLES["cp.ticks_per_cp"] = bad
            self.assertEqual(cp.ticks_per_cp(), 1, f"ticks_per_cp({bad}) -> 1")
            tunables.reset_tunables()

    def test_present_but_null_falls_back_to_default(self):
        # `cp.kudos_ticks:` with no value parses to None → in-code default.
        tunables._TUNABLES["cp.kudos_ticks"] = None
        self.assertEqual(cp.kudos_ticks(), cp.KUDOS_TICKS)

    def test_bad_value_falls_back_to_default(self):
        tunables._TUNABLES["cp.weekly_cap_ticks"] = "lots"
        self.assertEqual(cp.weekly_cap_ticks(), cp.WEEKLY_CAP_TICKS)

    def test_float_value_coerces_to_int(self):
        tunables._TUNABLES["cp.scene_max_ticks"] = 72.9
        self.assertEqual(cp.scene_max_ticks(), 72)


# ══════════════════════════════════════════════════════════════════════════
# 2. The overrides flow through the REAL award paths
# ══════════════════════════════════════════════════════════════════════════
class CpProgressionTunableEndToEnd(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    def test_scene_ticks_per_pose_override_changes_award(self):
        # 8 poses, min 3 → 5 bonus poses. Default 2/pose = 10 ticks.
        db = _CpDB()
        out = _run(cp.get_cp_engine().award_scene_bonus(db, 7, 8))
        self.assertEqual(out["ticks"], 10)
        # Override to 4/pose → 20 ticks for the same scene.
        db2 = _CpDB()
        tunables._TUNABLES["cp.scene_ticks_per_pose"] = 4
        out2 = _run(cp.get_cp_engine().award_scene_bonus(db2, 7, 8))
        self.assertEqual(out2["ticks"], 20)

    def test_scene_max_ticks_override_caps_award(self):
        # 100 poses would be 97*2=194 ticks, but scene_max caps it.
        db = _CpDB()
        out = _run(cp.get_cp_engine().award_scene_bonus(db, 7, 100))
        self.assertEqual(out["ticks"], cp.SCENE_MAX_TICKS)   # 60
        db2 = _CpDB()
        tunables._TUNABLES["cp.scene_max_ticks"] = 30
        out2 = _run(cp.get_cp_engine().award_scene_bonus(db2, 7, 100))
        self.assertEqual(out2["ticks"], 30)

    def test_scene_min_poses_override_gates_eligibility(self):
        # 2 poses with default min 3 → too short.
        db = _CpDB()
        out = _run(cp.get_cp_engine().award_scene_bonus(db, 7, 2))
        self.assertEqual(out["ticks"], 0)
        # Lower the bar to 1 → now 2 poses qualifies (1 bonus pose * 2 = 2).
        db2 = _CpDB()
        tunables._TUNABLES["cp.scene_min_poses"] = 1
        out2 = _run(cp.get_cp_engine().award_scene_bonus(db2, 7, 2))
        self.assertEqual(out2["ticks"], 2)

    def test_kudos_ticks_override_changes_award(self):
        db = _CpDB()
        out = _run(cp.get_cp_engine().award_kudos(db, 1, 2))
        self.assertEqual(out["ticks_awarded"], cp.KUDOS_TICKS)   # 35
        db2 = _CpDB()
        tunables._TUNABLES["cp.kudos_ticks"] = 50
        out2 = _run(cp.get_cp_engine().award_kudos(db2, 1, 2))
        self.assertEqual(out2["ticks_awarded"], 50)

    def test_kudos_per_week_override_gates_cap(self):
        db = _CpDB()
        db._kudos_received = 3      # already at the default weekly kudos cap
        out = _run(cp.get_cp_engine().award_kudos(db, 1, 2))
        self.assertFalse(out["success"])    # capped at default 3
        # Raise the cap to 5 → a 4th kudos now lands.
        db2 = _CpDB()
        db2._kudos_received = 3
        tunables._TUNABLES["cp.kudos_per_week"] = 5
        out2 = _run(cp.get_cp_engine().award_kudos(db2, 1, 2))
        self.assertTrue(out2["success"])

    def test_weekly_cap_override_caps_award_earlier(self):
        # ticks_this_week 95, award 35 kudos. Default cap 400 → full 35 lands.
        db = _CpDB(ticks_this_week=95, week_start_ts=1000.0)
        out = _run(cp.get_cp_engine().award_kudos(db, 1, 2))
        self.assertEqual(out["ticks_awarded"], 35)
        # Lower the cap to 100 → only 5 ticks fit before the cap.
        db2 = _CpDB(ticks_this_week=95, week_start_ts=1000.0)
        tunables._TUNABLES["cp.weekly_cap_ticks"] = 100
        out2 = _run(cp.get_cp_engine().award_kudos(db2, 1, 2))
        self.assertEqual(out2["ticks_awarded"], 5)

    def test_ticks_per_cp_override_changes_conversion(self):
        # 49 banked + 1 award. Default 200 → no CP. Override 50 → crosses to 1 CP.
        db = _CpDB(ticks_total=49)
        _run(cp._award_ticks(db, 7, 1, "passive", now=1000.0))
        self.assertEqual(db.cp, 0)
        db2 = _CpDB(ticks_total=49)
        tunables._TUNABLES["cp.ticks_per_cp"] = 50
        _run(cp._award_ticks(db2, 7, 1, "passive", now=1000.0))
        self.assertEqual(db2.cp, 1)

    def test_zero_ticks_per_cp_never_divides_by_zero(self):
        # The whole point of the >= 1 clamp: a misconfigured 0 must not crash
        # a real award (the tick→CP conversion divides by ticks_per_cp).
        tunables._TUNABLES["cp.ticks_per_cp"] = 0
        db = _CpDB(ticks_total=10)
        try:
            _run(cp._award_ticks(db, 7, 5, "scene", now=1000.0))
        except ZeroDivisionError:  # pragma: no cover
            self.fail("ticks_per_cp=0 caused a ZeroDivisionError on award")
        self.assertEqual(db.row["ticks_total"], 15)   # award still landed

    def test_passive_ticks_per_day_override(self):
        db = _CpDB()
        _run(cp.get_cp_engine()._maybe_award_passive(db, 7, now=10 ** 9))
        self.assertEqual(db.row["ticks_this_week"], cp.PASSIVE_TICKS_PER_DAY)  # 10
        db2 = _CpDB()
        tunables._TUNABLES["cp.passive_ticks_per_day"] = 25
        _run(cp.get_cp_engine()._maybe_award_passive(db2, 7, now=10 ** 9))
        self.assertEqual(db2.row["ticks_this_week"], 25)

    def test_behaviour_identical_when_unset(self):
        # No tunables loaded → the exact legacy numbers on the live paths.
        self.assertEqual(
            _run(cp.get_cp_engine().award_scene_bonus(_CpDB(), 7, 8))["ticks"], 10)
        self.assertEqual(
            _run(cp.get_cp_engine().award_kudos(_CpDB(), 1, 2))["ticks_awarded"], 35)
        db = _CpDB(ticks_total=199)
        _run(cp._award_ticks(db, 7, 1, "passive", now=1000.0))
        self.assertEqual(db.cp, 1)   # 200-tick boundary still converts


# ══════════════════════════════════════════════════════════════════════════
# 3. Drift pins — shipped YAML + use-site contract
# ══════════════════════════════════════════════════════════════════════════
class CpProgressionTunableShipped(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_keys_at_in_code_defaults(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for key, const in _KEYS.items():
            self.assertEqual(
                tunables.get_tunable(key, -1), getattr(cp, const),
                f"{key} drifted from {const}")

    def test_keys_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        for key in _KEYS:
            self.assertIn(f"{key}:", ty)

    def test_engine_reads_at_use_site(self):
        src = (REPO / "engine" / "cp_engine.py").read_text(encoding="utf-8")
        # Each lever is bound to its tunable key through the shared accessor
        # helper, which itself reads via get_tunable (read on call, not frozen
        # at import → an operator edit takes effect on the next load).
        self.assertIn("get_tunable(key", src)
        for key in _KEYS:
            self.assertIn(f'_cp_tunable("{key}"', src)
        # The decision sites call the accessors, not the frozen constants.
        for fn in ("ticks_per_cp()", "weekly_cap_ticks()",
                   "passive_ticks_per_day()", "scene_min_poses()",
                   "scene_ticks_per_pose()", "scene_max_ticks()",
                   "kudos_ticks()", "kudos_per_week()",
                   "ai_max_ticks_per_eval()"):
            self.assertIn(fn, src)

    def test_display_consumers_read_live_value(self):
        # The cpstatus text + the web HUD sidebar must show the live tunable
        # value, not a frozen import (else display lies after an operator tune).
        cmds = (REPO / "parser" / "cp_commands.py").read_text(encoding="utf-8")
        self.assertIn("ticks_per_cp()", cmds)
        self.assertIn("kudos_per_week()", cmds)
        sess = (REPO / "server" / "session.py").read_text(encoding="utf-8")
        self.assertIn("ticks_per_cp()", sess)
        self.assertIn("weekly_cap_ticks()", sess)


if __name__ == "__main__":
    unittest.main()
