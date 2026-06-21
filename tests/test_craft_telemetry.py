"""tests/test_craft_telemetry.py — T3.19 telemetry for the crafting lane.

Crafting completion was the last dark safe-lane production funnel. The credit
SINK (``schematic_tuition``) already rides ``credit_flow`` and the skill roll
rides ``skill_check``, but the per-schematic success/partial/fumble + quality
distribution — the direct signal for tuning the ``QUALITY_MULT_*`` knobs and
per-schematic difficulty — was unobserved. This drop adds ONE fail-open
``craft`` emitter at the engine chokepoint (``engine.crafting.resolve_craft``,
now a thin wrapper over ``_resolve_craft_impl``); this suite proves it fires
once per resolve for EVERY outcome branch (success / partial / full-failure /
fumble), mirrors the schematic + skill-check fields the offline analysis
needs, and — the load-bearing contract — never disturbs the craft when
telemetry breaks.

Run: python3 -m pytest tests/test_craft_telemetry.py
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import telemetry  # noqa: E402
from engine.crafting import resolve_craft  # noqa: E402


# A schematic with EMPTY components: average_component_quality → 50.0 and
# consume_components is a no-op, so resolve_craft needs no inventory setup.
def _schematic(**over):
    s = {
        "key": "blaster_pistol_basic",
        "name": "Blaster Pistol (Basic)",
        "output_key": "blaster_pistol",
        "skill_required": "blaster_repair",
        "difficulty": 12,
        "components": [],
    }
    s.update(over)
    return s


def _char(cid=42):
    return {"id": cid, "name": "Tester", "inventory": {}}


def _result(success=True, fumble=False, margin=3, critical_success=False):
    return SimpleNamespace(
        success=success, fumble=fumble, margin=margin,
        critical_success=critical_success,
    )


def _events(ev_type=None):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    if ev_type is not None:
        recs = [r for r in recs if r["ev"] == ev_type]
    return recs


class CraftTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()

    def tearDown(self):
        telemetry.reset()

    # ── one emit per resolve, every branch ─────────────────────────────────
    def test_success_emits_one_craft_event(self):
        out = resolve_craft(_char(), _schematic(), _result(success=True, margin=5))
        self.assertTrue(out["success"])
        self.assertFalse(out["partial"])
        evs = _events("craft")
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertTrue(e["success"])
        self.assertFalse(e["partial"])
        self.assertFalse(e["fumble"])
        self.assertGreater(e["quality"], 0.0)

    def test_partial_emits_partial_flag(self):
        # not success, margin >= -4 → partial path
        out = resolve_craft(_char(), _schematic(),
                            _result(success=False, margin=-2))
        self.assertTrue(out["partial"])
        e = _events("craft")[0]
        self.assertTrue(e["partial"])
        self.assertTrue(e["success"])   # partial returns success=True (lower quality)
        self.assertFalse(e["fumble"])
        self.assertGreater(e["quality"], 0.0)

    def test_full_failure_emits_no_success(self):
        # not success, margin < -4, no fumble → clean failure (no consumption)
        out = resolve_craft(_char(), _schematic(),
                            _result(success=False, margin=-7))
        self.assertFalse(out["success"])
        e = _events("craft")[0]
        self.assertFalse(e["success"])
        self.assertFalse(e["partial"])
        self.assertFalse(e["fumble"])
        self.assertEqual(e["quality"], 0.0)

    def test_fumble_emits_fumble_flag(self):
        out = resolve_craft(_char(), _schematic(),
                            _result(success=False, fumble=True, margin=-1))
        self.assertTrue(out["fumble"])
        e = _events("craft")[0]
        self.assertTrue(e["fumble"])
        self.assertFalse(e["success"])
        self.assertEqual(e["quality"], 0.0)

    # ── envelope mirrors the schematic + skill-check ───────────────────────
    def test_envelope_mirrors_schematic_and_roll(self):
        sch = _schematic(key="vibroblade_standard", output_key="vibroblade",
                         skill_required="melee_combat", difficulty=14)
        resolve_craft(_char(cid=99), sch,
                      _result(success=True, margin=8, critical_success=True))
        e = _events("craft")[0]
        self.assertEqual(e["char_id"], 99)
        self.assertEqual(e["schematic"], "vibroblade_standard")
        self.assertEqual(e["output_key"], "vibroblade")
        self.assertEqual(e["skill"], "melee_combat")
        self.assertEqual(e["difficulty"], 14)
        self.assertEqual(e["margin"], 8)
        self.assertTrue(e["critical"])
        self.assertFalse(e["experiment"])

    def test_experiment_flag_threads_through(self):
        resolve_craft(_char(), _schematic(),
                      _result(success=True, margin=2), experiment=True)
        e = _events("craft")[0]
        self.assertTrue(e["experiment"])

    # ── exactly one emit per call (no double counting) ─────────────────────
    def test_two_resolves_two_events(self):
        resolve_craft(_char(), _schematic(), _result())
        resolve_craft(_char(), _schematic(), _result())
        self.assertEqual(len(_events("craft")), 2)

    # ── load-bearing: a broken sink never disturbs the craft ───────────────
    def test_fail_open_when_emit_raises(self):
        orig = telemetry.emit

        def _boom(*a, **k):
            raise RuntimeError("sink down")

        telemetry.emit = _boom
        try:
            out = resolve_craft(_char(), _schematic(),
                                _result(success=True, margin=4))
        finally:
            telemetry.emit = orig
        # The craft still resolved correctly despite the telemetry break.
        self.assertTrue(out["success"])
        self.assertGreater(out["quality"], 0.0)

    def test_disabled_sink_suppresses_but_still_crafts(self):
        telemetry.configure(enabled=False)
        out = resolve_craft(_char(), _schematic(), _result(success=True))
        self.assertTrue(out["success"])
        self.assertEqual(len(_events("craft")), 0)

    # ── value sanity: success quality reflects the margin multiplier ───────
    def test_quality_scales_with_margin(self):
        resolve_craft(_char(), _schematic(), _result(success=True, margin=0))
        low = _events("craft")[0]["quality"]
        telemetry.reset()
        resolve_craft(_char(), _schematic(), _result(success=True, margin=10))
        high = _events("craft")[0]["quality"]
        self.assertGreater(high, low)


if __name__ == "__main__":
    unittest.main()
