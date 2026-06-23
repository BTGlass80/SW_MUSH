# -*- coding: utf-8 -*-
"""
tests/test_fork_event_staged_2026_06_23.py — EVENT staged-scenario fork.

Resolves EVENT.communal_rework_staged_scenarios (Brian: rally was "a counter, not
a scenario"). The Cult of the Hollow Sun is reworked into a 3-STAGE site scenario
(wave combat -> multi-skill objectives -> boss); `rally strike` advances the
current stage via that stage's relevant skills (so playstyle matters), the menace
becomes the failure timer, and clearing all three breaks the cult. Stage state
rides contributions_json["_stage"] (no schema change). Vertical slice: hollow_sun
only; the other cults keep the menace path (the record_strike change is guarded).
The integration (record_strike advances stages for a staged cult) is covered by
the updated tests/test_drop4b_communal_cult.py; this pins the pure stage logic.
"""
from __future__ import annotations

import unittest

from engine import staged_event as SE


class TestStagedRoster(unittest.TestCase):
    def test_hollow_sun_staged_others_not(self):
        self.assertTrue(SE.is_staged("hollow_sun"))
        self.assertFalse(SE.is_staged("ember_court"))
        self.assertEqual(len(SE.stages_for("hollow_sun")), 3)

    def test_stage_kinds_are_combat_skill_boss(self):
        kinds = [s["kind"] for s in SE.stages_for("hollow_sun")]
        self.assertEqual(kinds, [SE.KIND_COMBAT, SE.KIND_SKILL, SE.KIND_BOSS])


class TestProgression(unittest.TestCase):
    def test_successful_strikes_advance_and_clear_a_stage(self):
        st = {"idx": 0, "progress": 0}
        need = SE.stages_for("hollow_sun")[0]["need"]
        for i in range(need - 1):
            st, cleared, allc = SE.advance("hollow_sun", st, True)
            self.assertFalse(cleared)
            self.assertEqual(st["progress"], i + 1)
        st, cleared, allc = SE.advance("hollow_sun", st, True)
        self.assertTrue(cleared)
        self.assertEqual(st["idx"], 1)
        self.assertEqual(st["progress"], 0)
        self.assertFalse(allc)

    def test_a_miss_does_not_advance(self):
        st, cleared, allc = SE.advance("hollow_sun", {"idx": 0, "progress": 2}, False)
        self.assertEqual(st["progress"], 2)
        self.assertFalse(cleared)

    def test_clearing_all_stages_signals_won(self):
        st, allc = {"idx": 0, "progress": 0}, False
        total = sum(s["need"] for s in SE.stages_for("hollow_sun"))
        for _ in range(total):
            st, cleared, allc = SE.advance("hollow_sun", st, True)
        self.assertTrue(allc)
        self.assertGreaterEqual(st["idx"], len(SE.stages_for("hollow_sun")))


class TestStageSkillReward(unittest.TestCase):
    def test_skill_stage_rewards_the_relevant_skill_else_fallback(self):
        tithes = {"idx": 1, "progress": 0}  # the SKILL stage
        # a slicer's security (5D = 15 pips) beats the generic fallback
        self.assertEqual(
            SE.stage_pool_pips("hollow_sun", tithes, {"security": "5D"}, {}, 3), 15)
        # a soldier with no objective skill falls back to the generic pool
        self.assertEqual(
            SE.stage_pool_pips("hollow_sun", tithes, {"blaster": "5D"}, {}, 3), 3)


class TestTrackerAndState(unittest.TestCase):
    def test_tracker_renders_stage_marks_and_current_objective(self):
        text = "\n".join(SE.stage_tracker_lines(
            "the Cult of the Hollow Sun", "hollow_sun", {"idx": 1, "progress": 1}))
        self.assertIn("Stage 1", text)
        self.assertIn("cleared", text)        # stage 1 done
        self.assertIn("Cut the Water Tithes", text)  # stage 2 is current
        self.assertIn("rally strike", text)

    def test_stage_state_roundtrips_through_contribs(self):
        contribs = {}
        SE.set_stage_state(contribs, {"idx": 2, "progress": 3})
        self.assertEqual(SE.get_stage_state(contribs), {"idx": 2, "progress": 3})
        self.assertEqual(SE.get_stage_state({}), {"idx": 0, "progress": 0})


if __name__ == "__main__":
    unittest.main()
