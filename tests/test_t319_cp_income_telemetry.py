# -*- coding: utf-8 -*-
"""tests/test_t319_cp_income_telemetry.py — T3.19 CP-income-funnel emitters.

The telemetry BREADTH pass (progression catalog): a single ``cp_income`` event
emitted at every Character-Point faucet, tagged by ``source``, so one offline
funnel captures the whole CP economy — per-source income share, the tick→CP
conversion rate, and weekly-cap pressure:

  * ``CPEngine._award_ticks``             → source="passive"/"scene"/"kudos"/"ai_eval"
  * ``CPEngine.award_milestone_cp``       → source="milestone"
  * ``achievements._complete_achievement``→ source="achievement"
  * ``+spar`` padawan training            → source="padawan_training"

The contract (Brian, telemetry_purpose_clarified): emit is non-blocking
(buffer only), fail-open (a telemetry break NEVER disturbs the CP award it
observes), and records a real grant only after the DB mutation lands. These
tests drive the real engine paths with no-op / in-memory stub DBs and drain
the module-singleton sink — nothing is written to disk.
"""
import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _events():
    """Drain the singleton sink and return only the cp_income records."""
    from engine import telemetry
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r.get("ev") == "cp_income"]


# ══════════════════════════════════════════════════════════════════════════
# 1. The emit_cp_income helper — schema, coercion, None-drop, fail-open
# ══════════════════════════════════════════════════════════════════════════
class TestEmitCpIncomeHelper(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        telemetry.reset()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_envelope_and_core_fields(self):
        from engine.telemetry import emit_cp_income
        emit_cp_income("kudos", 7, cp_gained=1, ticks=35,
                       ticks_this_week=70, at_cap=False)
        recs = _events()
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["ev"], "cp_income")
        self.assertEqual(r["source"], "kudos")
        self.assertEqual(r["char_id"], 7)
        self.assertEqual(r["cp_gained"], 1)
        self.assertEqual(r["ticks"], 35)
        self.assertEqual(r["ticks_this_week"], 70)
        self.assertFalse(r["at_cap"])

    def test_char_id_coerced_to_int(self):
        from engine.telemetry import emit_cp_income
        emit_cp_income("milestone", "42", cp_gained=50)
        self.assertEqual(_events()[0]["char_id"], 42)

    def test_ticks_this_week_none_dropped(self):
        # Direct-CP sources bypass the tick cap → ticks_this_week omitted.
        from engine.telemetry import emit_cp_income
        emit_cp_income("milestone", 1, cp_gained=50)
        r = _events()[0]
        self.assertNotIn("ticks_this_week", r)
        self.assertEqual(r["ticks"], 0)         # default for direct-CP

    def test_none_extra_fields_dropped(self):
        from engine.telemetry import emit_cp_income
        emit_cp_income("milestone", 1, cp_gained=10, reason=None,
                       ach_key="first_blood")
        r = _events()[0]
        self.assertNotIn("reason", r)
        self.assertEqual(r["ach_key"], "first_blood")

    def test_at_cap_coerced_bool(self):
        from engine.telemetry import emit_cp_income
        emit_cp_income("scene", 1, ticks=60, ticks_this_week=400, at_cap=1)
        self.assertIs(_events()[0]["at_cap"], True)

    def test_helper_never_raises_on_bad_extra(self):
        from engine.telemetry import emit_cp_income
        try:
            emit_cp_income("kudos", 1, cp_gained=0, weird=object())
        except Exception as e:  # pragma: no cover
            self.fail(f"emit_cp_income raised: {e}")

    def test_uncoercible_char_id_kept_not_raised(self):
        from engine.telemetry import emit_cp_income
        emit_cp_income("ai_eval", ["x"], ticks=5, ticks_this_week=5)
        self.assertEqual(_events()[0]["char_id"], ["x"])

    def test_sample_zero_suppresses(self):
        # telemetry.cp_income_sample=0 drops every event (knob works).
        from engine import tunables
        from engine.telemetry import emit_cp_income
        tunables._TUNABLES["telemetry.cp_income_sample"] = 0.0
        try:
            emit_cp_income("passive", 1, ticks=10, ticks_this_week=10)
            self.assertEqual(_events(), [])
        finally:
            tunables.reset_tunables()


# ══════════════════════════════════════════════════════════════════════════
# 2. CPEngine tick economy — _award_ticks chokepoint
# ══════════════════════════════════════════════════════════════════════════
class _TickDB:
    """In-memory cp_ticks + character_points so _award_ticks runs for real."""
    def __init__(self):
        self.row = {
            "ticks_total": 0, "ticks_this_week": 0, "week_start_ts": 0,
            "cap_hit_streak": 0,
        }
        self.cp = 0

    async def cp_get_row(self, char_id):
        return dict(self.row)

    async def cp_ensure_row(self, char_id):
        pass

    async def cp_update_row(self, char_id, **updates):
        self.row.update(updates)

    async def cp_add_character_points(self, char_id, cp):
        self.cp += cp

    async def get_character(self, char_id):
        return {"character_points": self.cp}


class TestTickEconomyEmitter(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        telemetry.reset()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_kudos_award_emits_source_and_ticks(self):
        from engine.cp_engine import _award_ticks
        db = _TickDB()
        _run(_award_ticks(db, 7, 35, "kudos", now=1000.0))
        r = _events()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["source"], "kudos")
        self.assertEqual(r[0]["char_id"], 7)
        self.assertEqual(r[0]["ticks"], 35)
        self.assertEqual(r[0]["ticks_this_week"], 35)
        self.assertFalse(r[0]["at_cap"])
        self.assertEqual(r[0]["cp_gained"], 0)   # below 200-tick threshold

    def test_conversion_reports_cp_gained(self):
        # 199 ticks already banked + 1 more crosses the 200-tick → 1 CP.
        from engine.cp_engine import _award_ticks
        db = _TickDB()
        db.row["ticks_total"] = 199
        _run(_award_ticks(db, 7, 1, "passive", now=1000.0,
                          update_passive_ts=True))
        r = _events()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["cp_gained"], 1)
        self.assertEqual(r[0]["source"], "passive")

    def test_at_cap_flag_set_when_week_reaches_cap(self):
        from engine.cp_engine import _award_ticks, WEEKLY_CAP_TICKS
        db = _TickDB()
        db.row["ticks_this_week"] = WEEKLY_CAP_TICKS - 5
        db.row["week_start_ts"] = 1000.0
        _run(_award_ticks(db, 7, 5, "scene", now=1000.0,
                          update_scene_ts=True))
        r = _events()
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["at_cap"])

    def test_telemetry_break_does_not_break_award(self):
        from engine import telemetry
        from engine.cp_engine import _award_ticks
        orig = telemetry.emit_cp_income

        def _boom(*a, **k):
            raise RuntimeError("telemetry down")

        telemetry.emit_cp_income = _boom
        try:
            db = _TickDB()
            _run(_award_ticks(db, 7, 35, "kudos", now=1000.0))
            self.assertEqual(db.row["ticks_total"], 35)  # award still landed
        finally:
            telemetry.emit_cp_income = orig


# ══════════════════════════════════════════════════════════════════════════
# 3. Milestone CP — award_milestone_cp (direct, bypasses the tick cap)
# ══════════════════════════════════════════════════════════════════════════
class _MilestoneDB:
    def __init__(self):
        self.cp = 0

    async def cp_add_character_points(self, char_id, cp):
        self.cp += cp


class TestMilestoneEmitter(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        telemetry.reset()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_milestone_emits_with_reason(self):
        from engine.cp_engine import get_cp_engine
        eng = get_cp_engine()
        out = _run(eng.award_milestone_cp(_MilestoneDB(), 5, 50,
                                          reason="zones_visited"))
        self.assertEqual(out["cp_awarded"], 50)
        r = _events()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["source"], "milestone")
        self.assertEqual(r[0]["char_id"], 5)
        self.assertEqual(r[0]["cp_gained"], 50)
        self.assertEqual(r[0]["reason"], "zones_visited")
        self.assertNotIn("ticks_this_week", r[0])

    def test_zero_cp_no_emit(self):
        from engine.cp_engine import get_cp_engine
        eng = get_cp_engine()
        _run(eng.award_milestone_cp(_MilestoneDB(), 5, 0))
        self.assertEqual(_events(), [])


# ══════════════════════════════════════════════════════════════════════════
# 4. Achievement CP — _complete_achievement (direct grant)
# ══════════════════════════════════════════════════════════════════════════
class _AchDB:
    async def cp_add_character_points(self, char_id, cp):
        pass


class TestAchievementEmitter(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        telemetry.reset()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_achievement_emits_with_key(self):
        import engine.achievements as ach_mod
        # Stub the progress upsert so the test stays about telemetry.
        orig = ach_mod._upsert_progress

        async def _noop(*a, **k):
            pass

        ach_mod._upsert_progress = _noop
        try:
            ach = {"key": "first_kill", "name": "First Blood", "cp_reward": 3}
            _run(ach_mod._complete_achievement(_AchDB(), 9, ach, 1))
        finally:
            ach_mod._upsert_progress = orig
        r = _events()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["source"], "achievement")
        self.assertEqual(r[0]["char_id"], 9)
        self.assertEqual(r[0]["cp_gained"], 3)
        self.assertEqual(r[0]["ach_key"], "first_kill")

    def test_zero_cp_reward_no_emit(self):
        import engine.achievements as ach_mod
        orig = ach_mod._upsert_progress

        async def _noop(*a, **k):
            pass

        ach_mod._upsert_progress = _noop
        try:
            ach = {"key": "freebie", "name": "Freebie", "cp_reward": 0}
            _run(ach_mod._complete_achievement(_AchDB(), 9, ach, 1))
        finally:
            ach_mod._upsert_progress = orig
        self.assertEqual(_events(), [])


if __name__ == "__main__":
    unittest.main()
