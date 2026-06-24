"""tests/test_t319_spacer_quest_telemetry.py — T3.19 telemetry for the
spacer-quest onboarding funnel (engine/spacer_quest.py).

The 30-step "From Dust to Stars" new-player chain already pays a per-step
credit faucet (adjust_credits tag ``spacer_quest``), but those isolated ledger
rows can't be rejoined offline into the *onboarding funnel*: how many players
START the chain vs the last step they reach (the drop-off curve) vs how many
reach grand COMPLETE, plus the per-step pay. This drop adds ONE fail-open,
sample-tunable ``spacer_quest`` event at the real lifecycle seams —
``start`` (``_maybe_start_chain``), ``step`` (``_complete_step`` for steps
1-29), and ``complete`` (step 30) — tagging the macro ``quest_phase`` (1-5),
the credit faucet, and the phase-gate transitions.

This suite drives the REAL ``_maybe_start_chain`` / ``_complete_step`` against
stub session+DB objects and proves: exactly one event per lifecycle transition
with the right ``phase`` + envelope; the credit faucet field matches the step's
reward; ``start`` only fires when the prerequisite is met and the chain isn't
already running; the phase-gate transition is tagged; sampling honours
``telemetry.spacer_quest_sample``; and — the load-bearing contract — a broken
sink NEVER disturbs the quest step it observes.

Run: python -m pytest tests/test_t319_spacer_quest_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from engine import spacer_quest  # noqa: E402
from engine.spacer_quest import (  # noqa: E402
    _emit_spacer_telemetry,
    _maybe_start_chain,
    _complete_step,
    _default_quest_state,
    get_step,
)

REPO = Path(PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _events(ev_type="spacer_quest"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _StubSession:
    def __init__(self, char):
        self.character = char
        self.lines: list = []

    async def send_line(self, text):
        self.lines.append(text)


class _StubDB:
    """Records the quest's ledger + attribute writes."""

    def __init__(self):
        self.credit_log: list = []      # (cid, delta, source)
        self.saved: list = []           # (cid, kwargs)

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((cid, delta, source))
        return 100_000 + delta

    async def save_character(self, char_id, **kwargs):
        self.saved.append((char_id, kwargs))


def _char(cid=5, credits=100_000, attrs=None):
    return {"id": cid, "credits": credits, "attributes": json.dumps(attrs or {})}


class SpacerQuestTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    # ── helper unit: field schema per phase ───────────────────────────────────
    def test_helper_start_schema(self):
        qs = _default_quest_state()
        _emit_spacer_telemetry("start", {"id": 5}, qs)
        e = _events()[0]
        self.assertEqual(e["phase"], "start")
        self.assertEqual(e["char_id"], 5)
        self.assertEqual(e["quest_phase"], 1)
        # start carries no step/credits/title/phase_gate fields.
        for k in ("step", "credits", "title", "phase_gate"):
            self.assertNotIn(k, e)

    def test_helper_step_schema(self):
        qs = _default_quest_state()
        _emit_spacer_telemetry("step", {"id": 9}, qs, step_id=7, credits=250,
                               title=False, phase_gate=True)
        e = _events()[0]
        self.assertEqual(e["phase"], "step")
        self.assertEqual(e["char_id"], 9)
        self.assertEqual(e["step"], 7)
        self.assertEqual(e["credits"], 250)
        self.assertTrue(e["phase_gate"])
        self.assertNotIn("title", e)        # False dropped

    def test_helper_drops_zero_and_false_fields(self):
        qs = _default_quest_state()
        _emit_spacer_telemetry("step", {"id": 1}, qs, step_id=1, credits=0,
                               title=False, phase_gate=False)
        e = _events()[0]
        self.assertEqual(e["step"], 1)
        for k in ("credits", "title", "phase_gate"):
            self.assertNotIn(k, e)

    def test_helper_coerces_none_id(self):
        # Fail-open coercion: a None / missing id never raises.
        _emit_spacer_telemetry("start", None, None)
        e = _events()[0]
        self.assertEqual(e["char_id"], 0)

    # ── start seam: prerequisite + idempotence ────────────────────────────────
    def test_start_emits_when_prereq_met(self):
        char = _char(attrs={"starter_quest": 10})
        sess = _StubSession(char)
        _run(_maybe_start_chain(sess, _StubDB(), "room_enter"))
        evs = _events()
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["phase"], "start")
        self.assertEqual(evs[0]["char_id"], 5)
        # the chain state actually landed.
        self.assertIn("spacer_quest", json.loads(char["attributes"]))

    def test_no_start_without_prereq(self):
        char = _char(attrs={"starter_quest": 3})   # < 10
        _run(_maybe_start_chain(_StubSession(char), _StubDB(), "room_enter"))
        self.assertEqual(len(_events()), 0)

    def test_no_start_when_already_running(self):
        char = _char(attrs={"starter_quest": 10,
                            "spacer_quest": _default_quest_state()})
        _run(_maybe_start_chain(_StubSession(char), _StubDB(), "talk"))
        self.assertEqual(len(_events()), 0)

    def test_no_start_on_wrong_trigger(self):
        char = _char(attrs={"starter_quest": 10})
        _run(_maybe_start_chain(_StubSession(char), _StubDB(), "combat_kill"))
        self.assertEqual(len(_events()), 0)

    # ── step seam: one event per completed step, faucet matches ───────────────
    def test_step1_emits_step_event(self):
        char = _char(attrs={"spacer_quest": _default_quest_state()})
        qs = json.loads(char["attributes"])["spacer_quest"]
        _run(_complete_step(_StubSession(char), _StubDB(), qs, get_step(1)))
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["phase"], "step")
        self.assertEqual(e["step"], 1)
        self.assertEqual(e["credits"], 200)      # step 1 reward faucet

    def test_step_faucet_matches_ledger_leg(self):
        char = _char(attrs={"spacer_quest": _default_quest_state()})
        qs = json.loads(char["attributes"])["spacer_quest"]
        db = _StubDB()
        _run(_complete_step(_StubSession(char), db, qs, get_step(1)))
        e = _events()[0]
        leg = [c for c in db.credit_log if c == (5, 200, "spacer_quest")]
        self.assertEqual(len(leg), 1)
        self.assertEqual(e["credits"], leg[0][1])

    def test_phase_gate_step_tags_transition(self):
        qs = _default_quest_state()
        qs["step"] = 7
        char = _char(attrs={"spacer_quest": qs})
        _run(_complete_step(_StubSession(char), _StubDB(), qs, get_step(7)))
        e = _events()[0]
        self.assertEqual(e["phase"], "step")
        self.assertEqual(e["step"], 7)
        self.assertTrue(e["phase_gate"])
        # quest_phase reflects the POST-advance phase (1 → 2).
        self.assertEqual(e["quest_phase"], 2)

    def test_step30_emits_complete(self):
        qs = _default_quest_state()
        qs["step"] = 30
        qs["phase"] = 5
        char = _char(attrs={"spacer_quest": qs})
        db = _StubDB()
        _run(_complete_step(_StubSession(char), db, qs, get_step(30)))
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["phase"], "complete")
        self.assertEqual(e["step"], 30)
        self.assertEqual(e["credits"], 1000)
        # grand completion awarded +1 CP via save_character.
        cp_saves = [s for s in db.saved if "character_points" in s[1]]
        self.assertTrue(cp_saves)

    # ── sampling honours the tunable, mutation still lands ────────────────────
    def test_sample_zero_suppresses_event_not_the_reward(self):
        tunables._TUNABLES["telemetry.spacer_quest_sample"] = 0.0
        char = _char(attrs={"spacer_quest": _default_quest_state()})
        qs = json.loads(char["attributes"])["spacer_quest"]
        db = _StubDB()
        _run(_complete_step(_StubSession(char), db, qs, get_step(1)))
        self.assertEqual(len(_events()), 0)
        # The faucet still paid out despite no telemetry.
        self.assertIn((5, 200, "spacer_quest"), db.credit_log)

    def test_sample_default_captures(self):
        char = _char(attrs={"spacer_quest": _default_quest_state()})
        qs = json.loads(char["attributes"])["spacer_quest"]
        _run(_complete_step(_StubSession(char), _StubDB(), qs, get_step(1)))
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the step ───────────────────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        char = _char(attrs={"spacer_quest": _default_quest_state()})
        qs = json.loads(char["attributes"])["spacer_quest"]
        db = _StubDB()
        with mock.patch.object(telemetry, "emit", _boom):
            _run(_complete_step(_StubSession(char), db, qs, get_step(1)))
        # No crash; the faucet still paid.
        self.assertIn((5, 200, "spacer_quest"), db.credit_log)

    # ── seams wired + tunable registered (source pins) ────────────────────────
    def test_seams_call_helper(self):
        src = (REPO / "engine" / "spacer_quest.py").read_text(encoding="utf-8")
        self.assertIn("def _emit_spacer_telemetry(", src)
        self.assertIn('_emit_spacer_telemetry("start", char, qs)', src)
        self.assertIn('"complete" if step_id >= 30 else "step"', src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.spacer_quest_sample:", ty)


if __name__ == "__main__":
    unittest.main()
