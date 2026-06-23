"""tests/test_t319_chain_reward_telemetry.py — T3.19 telemetry for the tutorial
chain reward pipeline (engine/chain_rewards.py).

The credit legs already ride the ``credit_flow`` ledger (adjust_credits tags
``chain_step_reward`` / ``chain_reward``), but those rows can't be rejoined
offline into an onboarding funnel: they carry no chain identity, no item/rep
breadth, and — the load-bearing NPE metric — they never reveal a *graduation*
(chain completion) when it awards zero credits. This drop adds ONE fail-open
``chain_reward`` event (phase ``step`` | ``graduation``, mirroring the
``objective`` funnel) so the offline funnel can measure how much credit/item/rep
flow the onboarding pipeline injects per chain AND how many players complete each
chain (count(step) vs count(graduation) per chain_id).

This suite drives the REAL ``apply_step_rewards`` / ``apply_graduation_rewards``
against a recording stub DB and proves: a reward-bearing step emits exactly one
``step`` event with the right envelope; an empty-reward step (the common case)
emits NOTHING (no spam); a graduation ALWAYS emits one ``graduation`` event even
at zero credits; the event re-links to the ledger leg; and — the load-bearing
contract — a broken sink NEVER disturbs the reward delivery it observes.

Run: python -m pytest tests/test_t319_chain_reward_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import telemetry  # noqa: E402
from engine.chain_rewards import (  # noqa: E402
    apply_step_rewards, apply_graduation_rewards,
)

REPO = Path(PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _events(ev_type="chain_reward"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _StubDB:
    """Records the chain reward pipeline's ledger + inventory + save writes."""

    def __init__(self):
        self.credit_log = []     # (cid, delta, source)
        self.granted = []        # (cid, item dict)
        self.saved = []          # (cid, kwargs)

    async def adjust_credits(self, cid, delta, source):
        self.credit_log.append((cid, delta, source))
        return 1000 + delta

    async def add_to_inventory(self, cid, item):
        self.granted.append((cid, item))

    async def save_character(self, cid, **kw):
        self.saved.append((cid, kw))


def _char(credits=1000):
    return {"id": 7, "credits": credits, "chargen_notes": "{}"}


class ChainRewardTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()

    def tearDown(self):
        telemetry.reset()

    # ── step: a reward-bearing step emits exactly one event ───────────────────
    def test_step_with_credits_emits_one_event(self):
        db = _StubDB()
        step = SimpleNamespace(step=3, reward={"credits": 250})
        _run(apply_step_rewards(db, _char(), step, "republic_soldier"))
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["phase"], "step")
        self.assertEqual(e["chain_id"], "republic_soldier")
        self.assertEqual(e["step"], 3)
        self.assertEqual(e["char_id"], 7)
        self.assertEqual(e["credits"], 250)
        self.assertEqual(e["items"], 0)
        self.assertEqual(e["rep"], 0)

    def test_step_event_matches_ledger_leg(self):
        db = _StubDB()
        step = SimpleNamespace(step=1, reward={"credits": 500})
        _run(apply_step_rewards(db, _char(), step, "spacer_quest"))
        e = _events()[0]
        credit = [c for c in db.credit_log
                  if c == (7, 500, "chain_step_reward")]
        self.assertEqual(len(credit), 1)
        self.assertEqual(e["credits"], credit[0][1])

    def test_step_with_only_items_emits(self):
        db = _StubDB()
        step = SimpleNamespace(step=2, reward={"items": ["datapad", "commlink"]})
        _run(apply_step_rewards(db, _char(), step, "merc_path"))
        e = _events()[0]
        self.assertEqual(e["phase"], "step")
        self.assertEqual(e["items"], 2)
        self.assertEqual(e["credits"], 0)

    # ── empty-reward step is the common case → MUST NOT spam ──────────────────
    def test_empty_reward_step_emits_nothing(self):
        db = _StubDB()
        step = SimpleNamespace(step=4, reward={})
        _run(apply_step_rewards(db, _char(), step, "republic_soldier"))
        self.assertEqual(len(_events()), 0)

    def test_none_step_emits_nothing(self):
        db = _StubDB()
        _run(apply_step_rewards(db, _char(), None, "republic_soldier"))
        self.assertEqual(len(_events()), 0)

    # ── graduation: ALWAYS one event, even at zero credits ────────────────────
    def test_graduation_always_emits_even_zero_credits(self):
        db = _StubDB()
        grad = SimpleNamespace(credits=0, faction_rep={}, items=[],
                               achievements=[], follow_up_hint="")
        _run(apply_graduation_rewards(db, _char(), {}, grad,
                                      "republic_soldier", "Republic Soldier"))
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["phase"], "graduation")
        self.assertEqual(e["chain_id"], "republic_soldier")
        self.assertEqual(e["chain_label"], "Republic Soldier")
        self.assertEqual(e["credits"], 0)

    def test_graduation_full_reward_profile(self):
        db = _StubDB()
        grad = SimpleNamespace(
            credits=1500, faction_rep={},
            items=["dc15_blaster_rifle", "republic_armor"],
            achievements=["zzz_fake_grad_ach"],   # not in catalog → fallback only
            follow_up_hint="Report to the barracks.")
        _run(apply_graduation_rewards(db, _char(), {}, grad,
                                      "republic_soldier", "Republic Soldier"))
        e = _events()[0]
        self.assertEqual(e["credits"], 1500)
        self.assertEqual(e["items"], 2)
        self.assertEqual(e["achievements"], 1)
        self.assertEqual(e["rep"], 0)
        self.assertEqual(e["errors"], 0)

    def test_graduation_event_matches_ledger_leg(self):
        db = _StubDB()
        grad = SimpleNamespace(credits=1500, faction_rep={}, items=[],
                               achievements=[], follow_up_hint="")
        _run(apply_graduation_rewards(db, _char(), {}, grad, "merc_path"))
        e = _events()[0]
        credit = [c for c in db.credit_log if c == (7, 1500, "chain_reward")]
        self.assertEqual(len(credit), 1)
        self.assertEqual(e["credits"], credit[0][1])

    # ── load-bearing: a broken sink never disturbs reward delivery ────────────
    def test_step_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB()
        step = SimpleNamespace(step=1, reward={"credits": 200})
        with mock.patch.object(telemetry, "emit", _boom):
            _run(apply_step_rewards(db, _char(), step, "republic_soldier"))
        # No crash; the credit award still landed.
        self.assertIn((7, 200, "chain_step_reward"), db.credit_log)

    def test_graduation_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB()
        grad = SimpleNamespace(credits=800, faction_rep={}, items=[],
                               achievements=[], follow_up_hint="")
        with mock.patch.object(telemetry, "emit", _boom):
            _run(apply_graduation_rewards(db, _char(), {}, grad,
                                          "republic_soldier"))
        # The credit award + chargen_notes save still happened.
        self.assertIn((7, 800, "chain_reward"), db.credit_log)
        self.assertEqual(len(db.saved), 1)

    # ── both seams wired (source pins) ────────────────────────────────────────
    def test_both_seams_call_emit(self):
        src = (REPO / "engine" / "chain_rewards.py").read_text(encoding="utf-8")
        self.assertIn('_tele_emit("chain_reward", {\n                "phase": "step"', src)
        self.assertIn('_tele_emit("chain_reward", {\n            "phase": "graduation"', src)


if __name__ == "__main__":
    unittest.main()
