# -*- coding: utf-8 -*-
"""
tests/test_fork_cp_trickle_2026_06_23.py — CP AI-trickle fork.

Resolves CP.ai_trickle_director_wiring (Brian: "wire it and toggle it with a
command; start dormant but be able to flip it on; knobs to tune AI spend").
engine.cp_engine.award_ai_trickle was built but had ZERO callers. This wires a
real, gated caller -- the @director trickle admin command -- behind a
default-DORMANT runtime toggle, with the spend tunable via cp.ai_trickle_ticks
and clamped by the existing per-eval / weekly caps. (Auto-LLM RP scoring stays a
future flip; the award is a deliberate Director/admin grant, so no metered spend
and the "no AI grades your prose" guide claim still holds.)
"""
from __future__ import annotations

import unittest
from pathlib import Path

import engine.cp_engine as ce

DC_SRC = (Path(__file__).resolve().parent.parent
          / "parser" / "director_commands.py").read_text(encoding="utf-8")


class TestTrickleToggle(unittest.TestCase):
    def tearDown(self):
        ce.set_cp_ai_trickle(False)  # never leak an enabled flag to other tests

    def test_defaults_dormant(self):
        ce.set_cp_ai_trickle(False)
        self.assertFalse(ce.is_cp_ai_trickle_enabled())

    def test_toggle_flips_both_ways(self):
        ce.set_cp_ai_trickle(True)
        self.assertTrue(ce.is_cp_ai_trickle_enabled())
        ce.set_cp_ai_trickle(False)
        self.assertFalse(ce.is_cp_ai_trickle_enabled())


class TestTrickleCommandWiring(unittest.TestCase):
    def test_director_dispatches_trickle(self):
        import parser.director_commands as dc
        self.assertTrue(hasattr(dc.DirectorCommand, "_trickle"))
        self.assertIn('"trickle":   self._trickle', DC_SRC)

    def test_award_is_gated_clamped_and_knob_driven(self):
        body = DC_SRC[DC_SRC.index("async def _trickle"):
                      DC_SRC.index("class EconomyCommand")]
        # dormant gate before any award
        self.assertIn("is_cp_ai_trickle_enabled()", body)
        # wires the real producer
        self.assertIn("award_ai_trickle(", body)
        # clamped by the per-eval cap
        self.assertIn("AI_MAX_TICKS_PER_EVAL", body)
        # spend knob
        self.assertIn('get_tunable("cp.ai_trickle_ticks"', body)


if __name__ == "__main__":
    unittest.main()
