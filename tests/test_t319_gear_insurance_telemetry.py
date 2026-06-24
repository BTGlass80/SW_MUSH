# -*- coding: utf-8 -*-
"""tests/test_t319_gear_insurance_telemetry.py — T3.19 telemetry for the
gear-insurance policy lifecycle (engine/gear_insurance.py).

The premium debit already rides ``credit_flow`` per-tag
(``gear_insurance_premium`` / ``gear_insurance_premium_refund``), but those
isolated rows can't be rejoined offline into the policy *lifecycle* — the
buy→cancel voluntary-churn rate or the premium-sink volume against take-up.
This drop adds ONE fail-open, sample-tunable ``gear_insurance`` event at each
lifecycle transition: ``purchase`` (the premium sink) and ``cancel`` (a
voluntary checkout, no credits move — the premium is a pure sink).

The behavioral suite drives the REAL ``purchase_gear_insurance`` /
``cancel_gear_insurance`` against a recording stub (mirroring
tests/test_gear_insurance.py) and proves: exactly one event per successful
transition with the right action + signed amount; every refusal (already
insured / insufficient funds / persist-fail-and-refund / not-insured /
cancel-persist-fail) emits nothing — never a phantom policy signal; the
``telemetry.gear_insurance_sample`` tunable is honoured; and — the load-bearing
contract — a broken sink NEVER disturbs the buy/cancel it observes. The helper
schema + the seam wiring + the tunable registration are pinned directly.

Run: python -m pytest tests/test_t319_gear_insurance_telemetry.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import gear_insurance  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from engine.gear_insurance import (  # noqa: E402
    GEAR_INSURANCE_PREMIUM, PREMIUM_SOURCE, PREMIUM_REFUND_SOURCE,
    purchase_gear_insurance, cancel_gear_insurance,
)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Each test starts with a fresh sink + tunables, and cleans up after."""
    telemetry.reset()
    tunables.reset_tunables()
    yield
    telemetry.reset()
    tunables.reset_tunables()


def _events(ev_type="gear_insurance"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


# ── recording stub (mirrors tests/test_gear_insurance.py) ─────────────────────
class _StubDB:
    def __init__(self, fail_persist=False):
        self.credit_log = []   # list of (delta, source)
        self.saves = []        # list of field dicts
        self.fail_persist = fail_persist

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((delta, source))
        return 1_000_000 + delta

    async def save_character(self, cid, **fields):
        if self.fail_persist:
            raise RuntimeError("persist boom")
        self.saves.append(fields)


def _char(credits=1_000_000, insured=0):
    return {"id": 7, "credits": credits, "gear_insured": insured}


# ── behavioral: one event per successful transition, right action + amount ────
class TestTransitionsEmit:
    async def test_purchase_emits_one_sink_event(self):
        db = _StubDB()
        res = await purchase_gear_insurance(db, _char())

        assert res["ok"] is True
        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "purchase"
        assert e["char_id"] == 7
        assert e["amount"] == -GEAR_INSURANCE_PREMIUM   # the premium sink
        assert e["premium"] == GEAR_INSURANCE_PREMIUM
        # The sink itself still fired exactly once.
        assert db.credit_log == [(-GEAR_INSURANCE_PREMIUM, PREMIUM_SOURCE)]

    async def test_cancel_emits_one_zero_amount_event(self):
        db = _StubDB()
        res = await cancel_gear_insurance(db, _char(insured=1))

        assert res["ok"] is True
        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "cancel"
        assert e["char_id"] == 7
        assert e["amount"] == 0          # no refund — the premium is a pure sink
        # No credit moved on a cancel.
        assert db.credit_log == []


# ── refusals emit nothing: never a phantom policy signal ──────────────────────
class TestRefusalsEmitNothing:
    async def test_already_insured_emits_nothing(self):
        db = _StubDB()
        res = await purchase_gear_insurance(db, _char(insured=1))
        assert res["ok"] is False and res["reason"] == "already"
        assert _events() == []

    async def test_insufficient_funds_emits_nothing(self):
        db = _StubDB()
        res = await purchase_gear_insurance(db, _char(credits=10))
        assert res["ok"] is False and res["reason"] == "insufficient"
        assert db.credit_log == []
        assert _events() == []

    async def test_persist_failure_refund_emits_nothing(self):
        db = _StubDB(fail_persist=True)
        res = await purchase_gear_insurance(db, _char())
        assert res["ok"] is False and res["reason"] == "persist_failed"
        # debit + matching refund, but NO lifecycle event (the buy never landed).
        assert db.credit_log == [
            (-GEAR_INSURANCE_PREMIUM, PREMIUM_SOURCE),
            (GEAR_INSURANCE_PREMIUM, PREMIUM_REFUND_SOURCE),
        ]
        assert _events() == []

    async def test_cancel_without_policy_emits_nothing(self):
        db = _StubDB()
        res = await cancel_gear_insurance(db, _char(insured=0))
        assert res["ok"] is False and res["reason"] == "not_insured"
        assert _events() == []

    async def test_cancel_persist_failure_emits_nothing(self):
        db = _StubDB(fail_persist=True)
        res = await cancel_gear_insurance(db, _char(insured=1))
        assert res["ok"] is False and res["reason"] == "persist_failed"
        assert _events() == []


# ── sampling honours the tunable; the transaction still lands ─────────────────
class TestSampling:
    async def test_sample_zero_suppresses_event_not_the_purchase(self):
        tunables._TUNABLES["telemetry.gear_insurance_sample"] = 0.0
        db = _StubDB()
        char = _char()
        res = await purchase_gear_insurance(db, char)

        assert res["ok"] is True
        assert _events() == []
        # The premium still debited + the flag still set despite no telemetry.
        assert db.credit_log == [(-GEAR_INSURANCE_PREMIUM, PREMIUM_SOURCE)]
        assert char["gear_insured"] == 1


# ── load-bearing: a broken sink never disturbs the policy transaction ─────────
class TestFailOpen:
    async def test_emit_raises_purchase_still_succeeds(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB()
        char = _char()
        with mock.patch.object(telemetry, "emit", _boom):
            res = await purchase_gear_insurance(db, char)

        assert res["ok"] is True          # no crash
        assert db.credit_log == [(-GEAR_INSURANCE_PREMIUM, PREMIUM_SOURCE)]
        assert char["gear_insured"] == 1  # the buy still landed

    async def test_emit_raises_cancel_still_succeeds(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB()
        char = _char(insured=1)
        with mock.patch.object(telemetry, "emit", _boom):
            res = await cancel_gear_insurance(db, char)

        assert res["ok"] is True
        assert char["gear_insured"] == 0


# ── helper unit: field schema + coercion ──────────────────────────────────────
class TestHelperSchema:
    def test_purchase_schema(self):
        gear_insurance._emit_gear_insurance(
            "purchase", 7, -GEAR_INSURANCE_PREMIUM, premium=GEAR_INSURANCE_PREMIUM)
        e = _events()[0]
        assert e["action"] == "purchase"
        assert e["char_id"] == 7
        assert e["amount"] == -GEAR_INSURANCE_PREMIUM
        assert e["premium"] == GEAR_INSURANCE_PREMIUM

    def test_str_id_coerced_to_int(self):
        gear_insurance._emit_gear_insurance("purchase", "42", -GEAR_INSURANCE_PREMIUM)
        assert _events()[0]["char_id"] == 42

    def test_none_id_coerced_safely(self):
        # Fail-open coercion: a None id never raises (lands unchanged).
        gear_insurance._emit_gear_insurance("cancel", None, 0)
        assert "char_id" in _events()[0]

    def test_none_extra_fields_dropped(self):
        gear_insurance._emit_gear_insurance("cancel", 7, 0, premium=None)
        e = _events()[0]
        assert "premium" not in e          # None dropped
        assert e["action"] == "cancel"


# ── source pins: every lifecycle seam routes through the helper ──────────────
class TestSeamWiring:
    @classmethod
    def setup_class(cls):
        cls.src = (PROJECT_ROOT / "engine" / "gear_insurance.py").read_text(
            encoding="utf-8")

    @pytest.mark.parametrize("action", ['"purchase"', '"cancel"'])
    def test_action_wired(self, action):
        assert f'_emit_gear_insurance({action}' in self.src, (
            f"gear_insurance.py must emit the {action} transition")

    def test_tunable_documented_in_yaml(self):
        ty = (PROJECT_ROOT / "data" / "tunables.yaml").read_text(
            encoding="utf-8")
        assert "telemetry.gear_insurance_sample:" in ty
