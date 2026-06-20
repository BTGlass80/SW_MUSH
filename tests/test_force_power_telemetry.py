# -*- coding: utf-8 -*-
"""tests/test_force_power_telemetry.py — Force-power funnel telemetry (QA funnel-bypass family).

The QA playthrough (2026-06-19) flagged ``engine/force_powers.resolve_force_power``
as bypassing the out-of-combat dice funnel: it rolls via the canonical dice
engine (``roll_d6_pool``) but emitted no telemetry, so Force usage was invisible
to the T3.19 sink that captures every other skill check.

Force powers deliberately do NOT route through ``perform_skill_check`` — three
resolution rules forbid it (combination powers roll the *weakest* of several
skills; Force rolls are explicitly buff/morale-aura EXEMPT; the wound penalty
is applied in ``resolve_force_power`` but ``perform_skill_check`` has no wound
stage). The funnel's one missing piece was therefore observability, closed by a
direct ``telemetry.emit("force_power", ...)`` at the resolution chokepoint with
the same fail-open + sample-tunable posture as the ``skill_check`` emitter.

These tests assert the emit fires with the right envelope, is sample-gated, and
that the dice math itself is unchanged (no buff applied).
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.dice import DicePool  # noqa: E402
from engine.character import WoundLevel  # noqa: E402
from engine.force_powers import resolve_force_power  # noqa: E402


# ── Fixtures ───────────────────────────────────────────────────────────────
class _Wound:
    display_name = "Wounded"


class _Actor:
    """Minimal Character-shaped stand-in for the Force user.

    resolve_force_power only touches: id, name, dark_side_points,
    wound_level.penalty_dice, and get_attribute() for a simple/dark power
    that triggers no fall check (DSP < 6) and no PC-target mind resist.
    """

    def __init__(self, char_id=7, dsp=0, **skills):
        self.id = char_id
        self.name = "Test Jedi"
        self.dark_side_points = dsp
        self.wound_level = WoundLevel.HEALTHY
        self._skills = skills

    def get_attribute(self, name):
        return self._skills.get(name, DicePool(0, 0))


class _Target:
    def __init__(self, **attrs):
        self.name = "Test Target"
        self._attrs = attrs

    def get_attribute(self, name):
        return self._attrs.get(name, DicePool(2, 0))

    def apply_wound(self, dmg):
        return _Wound()


def _events(ev_type=None):
    from engine import telemetry
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    if ev_type is not None:
        recs = [r for r in recs if r["ev"] == ev_type]
    return recs


class _TelemetryCase(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        self._tmp = tempfile.TemporaryDirectory()
        telemetry.reset()
        telemetry.configure(path=os.path.join(self._tmp.name, "e.jsonl"),
                            enabled=True)

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()
        self._tmp.cleanup()


# ── Tests ──────────────────────────────────────────────────────────────────
class TestForcePowerTelemetry(_TelemetryCase):
    def test_simple_power_emits_one_force_power_event(self):
        actor = _Actor(char_id=7, control=DicePool(4, 0))
        r = resolve_force_power("control_pain", actor, skill_reg=None)
        evs = _events("force_power")
        self.assertEqual(len(evs), 1, "exactly one force_power event per resolve")
        e = evs[0]
        self.assertEqual(e["char_id"], 7)
        self.assertEqual(e["power"], "control_pain")
        self.assertEqual(e["skills"], "control")
        self.assertFalse(e["dark_side"])
        # envelope mirrors the result the parser/tests see
        self.assertEqual(e["roll"], r.roll)
        self.assertEqual(e["difficulty"], r.difficulty)
        self.assertEqual(e["margin"], r.margin)
        self.assertEqual(e["success"], r.success)
        self.assertEqual(e["dsp_gained"], r.dsp_gained)
        self.assertFalse(e["fall_check"])

    def test_dark_power_marks_dark_side_and_dsp(self):
        # injure_kill is dark_side=True; DSP starts at 0 so the +1 award
        # stays under DSP_FALL_THRESHOLD (no fall check → no skill_reg needed).
        actor = _Actor(char_id=9, dsp=0, alter=DicePool(5, 0))
        target = _Target(strength=DicePool(3, 0))
        r = resolve_force_power("injure_kill", actor, skill_reg=None,
                                target_char=target)
        e = _events("force_power")[0]
        self.assertEqual(e["char_id"], 9)
        self.assertEqual(e["power"], "injure_kill")
        self.assertTrue(e["dark_side"])
        self.assertEqual(e["dsp_gained"], r.dsp_gained)
        self.assertGreaterEqual(e["dsp_gained"], 1)

    def test_sample_zero_suppresses_emit(self):
        from engine import tunables
        tunables._TUNABLES = {"telemetry.force_power_sample": 0.0}
        try:
            actor = _Actor(control=DicePool(3, 0))
            resolve_force_power("control_pain", actor, skill_reg=None)
            self.assertEqual(len(_events("force_power")), 0,
                             "sample=0 must sample the event out")
        finally:
            tunables.reset_tunables()

    def test_emit_is_fail_open(self):
        # An emit that blows up must never break power resolution. Force a
        # broken sink and confirm resolve_force_power still returns a result.
        from engine import telemetry
        sink = telemetry.get_sink()
        orig = sink.emit
        sink.emit = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            actor = _Actor(control=DicePool(3, 0))
            r = resolve_force_power("control_pain", actor, skill_reg=None)
            self.assertIsNotNone(r)
            self.assertEqual(r.power.key, "control_pain")
        finally:
            sink.emit = orig

    def test_unknown_power_does_not_emit(self):
        actor = _Actor(control=DicePool(3, 0))
        resolve_force_power("not_a_real_power", actor, skill_reg=None)
        self.assertEqual(len(_events("force_power")), 0,
                         "the early unknown-power return path emits nothing")


if __name__ == "__main__":
    unittest.main()
