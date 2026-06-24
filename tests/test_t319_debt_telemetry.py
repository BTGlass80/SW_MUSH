"""tests/test_t319_debt_telemetry.py — T3.19 telemetry for the Hutt-debt
payment lifecycle (engine/debt.py).

The weekly auto-debit already rides ``credit_flow`` (adjust_credits tag
``debt_payment``), but those isolated ledger rows can't be rejoined offline into
the debt *lifecycle*: the on-schedule-payment vs missed rate, the
miss → enforcer-escalation rate, and the time-to-payoff distribution. This drop
adds ONE fail-open, sample-tunable ``debt`` event per weekly transition —
``payment`` (a partial payment), ``payoff`` (the final payment that cleared the
principal), and ``missed`` (insufficient credits; the ``escalation`` field tags
warning/enforcer) — emitted at the real ``process_all_debts`` seams.

This suite drives the REAL ``process_all_debts`` against a recording stub DB
and proves: exactly one ``debt`` event per due debtor with the right action +
envelope; the payment sink matches the ledger leg; a debtor with no debt or a
not-yet-due debt emits nothing; the escalation tag tracks the missed count;
events fire even for an OFFLINE debtor (session_mgr=None); the
``telemetry.debt_sample`` tunable is honoured; and — the load-bearing contract —
a broken sink NEVER disturbs the payment it observes.

Run: python -m pytest tests/test_t319_debt_telemetry.py
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
from engine.debt import process_all_debts, _emit_debt  # noqa: E402

REPO = Path(PROJECT_ROOT)

# A due date safely in the past (epoch) and one far in the future (year ~2286).
_DUE_NOW = 0
_DUE_FUTURE = 9_999_999_999


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _events(ev_type="debt"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _StubDB:
    """Records the debt loop's ledger + attribute writes."""

    def __init__(self, rows):
        self._rows = rows
        self.credit_log = []       # (cid, delta, source)
        self.saved = []            # (cid, attributes-json)

    async def fetchall(self, sql, *args):
        return list(self._rows)

    async def save_character(self, char_id, **kwargs):
        self.saved.append((char_id, kwargs.get("attributes")))

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((cid, delta, source))
        return 100_000 + delta


def _row(char_id, credits, debt, *, extra_attrs=None):
    """A dict DB row (B1: all DB reads return plain dicts)."""
    attrs = dict(extra_attrs or {})
    if debt is not None:
        attrs["hutt_debt"] = debt
    return {"id": char_id, "credits": credits, "attributes": json.dumps(attrs)}


def _debt(principal, *, missed=0, due=_DUE_NOW, total_paid=0):
    return {
        "principal": principal,
        "payments_missed": missed,
        "next_payment_due": due,
        "total_paid": total_paid,
    }


class DebtTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    # ── payment: partial vs payoff ────────────────────────────────────────────
    def test_partial_payment_emits_payment(self):
        db = _StubDB([_row(5, 5000, _debt(2000))])
        _run(process_all_debts(db, None))
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["action"], "payment")
        self.assertEqual(e["char_id"], 5)
        self.assertEqual(e["amount"], -500)            # the weekly sink
        self.assertEqual(e["principal_remaining"], 1500)
        self.assertEqual(e["total_paid"], 500)
        # missed-only field never appears on a payment event.
        self.assertNotIn("escalation", e)

    def test_final_payment_emits_payoff(self):
        # principal below the weekly bite → cleared this tick.
        db = _StubDB([_row(7, 5000, _debt(300))])
        _run(process_all_debts(db, None))
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["action"], "payoff")
        self.assertEqual(e["amount"], -300)            # min(500, principal)
        self.assertEqual(e["principal_remaining"], 0)
        self.assertEqual(e["total_paid"], 300)

    def test_payment_event_matches_ledger_leg(self):
        db = _StubDB([_row(5, 5000, _debt(2000))])
        _run(process_all_debts(db, None))
        e = _events()[0]
        debit = [c for c in db.credit_log if c == (5, -500, "debt_payment")]
        self.assertEqual(len(debit), 1)
        # The single event re-links the sink amount to the ledger leg.
        self.assertEqual(e["amount"], debit[0][1])

    # ── missed: escalation tracks the count ───────────────────────────────────
    def test_first_miss_no_escalation(self):
        db = _StubDB([_row(5, 100, _debt(2000, missed=0))])   # < 500 due
        _run(process_all_debts(db, None))
        e = _events()[0]
        self.assertEqual(e["action"], "missed")
        self.assertEqual(e["amount"], 0)               # no credits move
        self.assertEqual(e["payments_missed"], 1)
        self.assertEqual(e["principal_remaining"], 2000)
        self.assertNotIn("escalation", e)              # None dropped

    def test_second_miss_warning(self):
        db = _StubDB([_row(5, 100, _debt(2000, missed=1))])
        _run(process_all_debts(db, None))
        e = _events()[0]
        self.assertEqual(e["action"], "missed")
        self.assertEqual(e["payments_missed"], 2)
        self.assertEqual(e["escalation"], "warning")

    def test_third_miss_enforcer(self):
        db = _StubDB([_row(5, 100, _debt(2000, missed=2))])
        _run(process_all_debts(db, None))
        e = _events()[0]
        self.assertEqual(e["action"], "missed")
        self.assertEqual(e["payments_missed"], 3)
        self.assertEqual(e["escalation"], "enforcer")

    # ── non-emitting paths ────────────────────────────────────────────────────
    def test_no_debt_no_emit(self):
        db = _StubDB([_row(5, 5000, None)])            # no hutt_debt key
        _run(process_all_debts(db, None))
        self.assertEqual(len(_events()), 0)

    def test_zero_principal_no_emit(self):
        db = _StubDB([_row(5, 5000, _debt(0))])        # already paid off
        _run(process_all_debts(db, None))
        self.assertEqual(len(_events()), 0)

    def test_not_due_no_emit(self):
        db = _StubDB([_row(5, 5000, _debt(2000, due=_DUE_FUTURE))])
        _run(process_all_debts(db, None))
        self.assertEqual(len(_events()), 0)

    def test_empty_attrs_no_emit(self):
        db = _StubDB([{"id": 5, "credits": 5000, "attributes": ""}])
        _run(process_all_debts(db, None))
        self.assertEqual(len(_events()), 0)

    # ── offline debtor still recorded (the session-independence contract) ─────
    def test_emits_for_offline_debtor(self):
        # session_mgr=None → no comlink/title, but the lifecycle still records.
        db = _StubDB([_row(9, 5000, _debt(2000))])
        _run(process_all_debts(db, None))
        self.assertEqual(len(_events()), 1)

    # ── sampling honours the tunable, mutation still lands ────────────────────
    def test_sample_zero_suppresses_event_not_the_payment(self):
        tunables._TUNABLES["telemetry.debt_sample"] = 0.0
        db = _StubDB([_row(5, 5000, _debt(2000))])
        _run(process_all_debts(db, None))
        self.assertEqual(len(_events()), 0)
        # The debit still landed despite no telemetry.
        self.assertIn((5, -500, "debt_payment"), db.credit_log)

    def test_sample_default_captures(self):
        db = _StubDB([_row(5, 5000, _debt(2000))])
        _run(process_all_debts(db, None))
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the payment ────────────────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB([_row(5, 5000, _debt(2000))])
        with mock.patch.object(telemetry, "emit", _boom):
            _run(process_all_debts(db, None))
        # No crash; the debit still landed.
        self.assertIn((5, -500, "debt_payment"), db.credit_log)

    # ── helper unit: field schema per action ──────────────────────────────────
    def test_helper_payment_schema(self):
        _emit_debt("payment", 5, -500, principal_remaining=1500, total_paid=500)
        e = _events()[0]
        self.assertEqual(e["action"], "payment")
        self.assertEqual(e["char_id"], 5)
        self.assertEqual(e["amount"], -500)
        self.assertEqual(e["principal_remaining"], 1500)

    def test_helper_drops_none_escalation(self):
        _emit_debt("missed", 5, 0, payments_missed=1, escalation=None)
        e = _events()[0]
        self.assertNotIn("escalation", e)

    def test_helper_coerces_none_id(self):
        # Fail-open coercion: a None id never raises (str-safe, lands present).
        _emit_debt("payment", None, 0)
        self.assertIn("char_id", _events()[0])

    # ── seams wired + tunable registered (source pins) ────────────────────────
    def test_seams_call_helper(self):
        src = (REPO / "engine" / "debt.py").read_text(encoding="utf-8")
        self.assertIn("def _emit_debt(", src)
        self.assertIn('"payoff" if remaining <= 0 else "payment"', src)
        self.assertIn('"missed", char_id, 0,', src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.debt_sample:", ty)


if __name__ == "__main__":
    unittest.main()
