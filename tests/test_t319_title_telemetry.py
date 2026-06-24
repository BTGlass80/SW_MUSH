# -*- coding: utf-8 -*-
"""tests/test_t319_title_telemetry.py — T3.19 telemetry for the vanity-title
prestige lifecycle (engine/titles.py).

The purchase debit already rides ``credit_flow`` under the ``vanity_title`` tag
(plus ``vanity_title_refund`` on a failed-and-refunded buy), but those isolated
rows can't be rejoined offline into the *prestige* lifecycle — which of the 8
price tiers actually sell, how purchased prestige compares to earned prestige,
or how much veteran credit the sink soaks up against take-up. This drop adds ONE
fail-open, sample-tunable ``vanity_title`` event at each lifecycle transition:
``purchase`` (the sink — a title bought, tagged with the price-tier index +
owned-count-after) and ``grant`` (an EARNED title awarded for a deed; no credits
move).

The behavioral suite drives the REAL ``purchase_title`` / ``grant_earned_title``
against a recording stub (mirroring tests/test_vanity_titles.py) and proves:
exactly one event per successful transition with the right action + signed
amount + tier; every refusal (unknown / already-owned / insufficient /
concurrent-overdraw / persist-fail-and-refund, and the grant refusals) emits
nothing — never a phantom prestige signal; the ``telemetry.title_sample``
tunable is honoured; and — the load-bearing contract — a broken sink NEVER
disturbs the buy/grant it observes. The helper schema + the seam wiring + the
tunable registration are pinned directly.

Run: python -m pytest tests/test_t319_title_telemetry.py
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

from engine import telemetry  # noqa: E402
from engine import titles  # noqa: E402
from engine import tunables  # noqa: E402
from engine.titles import (  # noqa: E402
    VANITY_TITLES, purchase_title, grant_earned_title,
)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Each test starts with a fresh sink + tunables, and cleans up after."""
    telemetry.reset()
    tunables.reset_tunables()
    yield
    telemetry.reset()
    tunables.reset_tunables()


def _events(ev_type="vanity_title"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


# ── recording stub (mirrors tests/test_vanity_titles.py) ──────────────────────
class _StubDB:
    def __init__(self, fail_persist=False, debit_returns="auto"):
        self.credit_log = []   # list of (delta, source)
        self.saves = []        # list of field dicts
        self.fail_persist = fail_persist
        self.debit_returns = debit_returns  # "auto" → 1_000_000+delta; else literal

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((delta, source))
        if self.debit_returns != "auto":
            return self.debit_returns
        return 1_000_000 + delta

    async def save_character(self, cid, **fields):
        if self.fail_persist:
            raise RuntimeError("persist boom")
        self.saves.append(fields)


def _char(credits=1_000_000, owned=None):
    return {"id": 7, "credits": credits,
            "vanity_titles": json.dumps(owned or []), "display_title": ""}


_WAYFARER = VANITY_TITLES[0]          # cheapest tier (index 0), cost 2_000
_MAGNATE = next(t for t in VANITY_TITLES if t["key"] == "magnate")  # mid tier


# ── behavioral: one event per successful transition, right action + amount ────
class TestTransitionsEmit:
    async def test_purchase_emits_one_sink_event(self):
        db = _StubDB()
        res = await purchase_title(db, _char(), "wayfarer")

        assert res["ok"] is True
        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "purchase"
        assert e["char_id"] == 7
        assert e["amount"] == -_WAYFARER["cost"]   # the signed prestige sink
        assert e["key"] == "wayfarer"
        assert e["tier"] == 0                       # cheapest price tier
        assert e["owned"] == 1                      # owned count AFTER the buy
        # The sink itself still fired exactly once, as a pure debit.
        assert db.credit_log == [(-_WAYFARER["cost"], "vanity_title")]

    async def test_purchase_tier_index_tracks_price_band(self):
        db = _StubDB()
        await purchase_title(db, _char(), "magnate")
        e = _events()[0]
        expected_tier = next(i for i, t in enumerate(VANITY_TITLES)
                             if t["key"] == "magnate")
        assert e["tier"] == expected_tier
        assert e["amount"] == -_MAGNATE["cost"]

    async def test_purchase_owned_count_reflects_prior_titles(self):
        db = _StubDB()
        # Already owns the cheapest; buying a second lands owned == 2.
        res = await purchase_title(db, _char(owned=["wayfarer"]), "magnate")
        assert res["ok"] is True
        assert _events()[0]["owned"] == 2

    async def test_grant_emits_one_zero_amount_event(self):
        db = _StubDB()
        ok = await grant_earned_title(db, _char(), "hunter")

        assert ok is True
        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "grant"
        assert e["char_id"] == 7
        assert e["amount"] == 0          # an earned deed reward — no credits move
        assert e["key"] == "hunter"
        assert "tier" not in e           # earned titles carry no price tier
        # No credit moved on a grant.
        assert db.credit_log == []


# ── refusals emit nothing: never a phantom prestige signal ────────────────────
class TestRefusalsEmitNothing:
    async def test_unknown_key_emits_nothing(self):
        db = _StubDB()
        res = await purchase_title(db, _char(), "not_a_title")
        assert res["ok"] is False and res["reason"] == "unknown"
        assert db.credit_log == []
        assert _events() == []

    async def test_already_owned_emits_nothing(self):
        db = _StubDB()
        res = await purchase_title(db, _char(owned=["wayfarer"]), "wayfarer")
        assert res["ok"] is False and res["reason"] == "owned"
        assert db.credit_log == []
        assert _events() == []

    async def test_insufficient_funds_emits_nothing(self):
        db = _StubDB()
        res = await purchase_title(db, _char(credits=10), "wayfarer")
        assert res["ok"] is False and res["reason"] == "insufficient"
        assert db.credit_log == []          # never even attempted the debit
        assert _events() == []

    async def test_concurrent_overdraw_emits_nothing(self):
        # allow_negative=False atomic refusal → adjust_credits returns None.
        db = _StubDB(debit_returns=None)
        res = await purchase_title(db, _char(), "wayfarer")
        assert res["ok"] is False and res["reason"] == "insufficient"
        # The debit was attempted (and atomically refused) but no buy landed.
        assert db.credit_log == [(-_WAYFARER["cost"], "vanity_title")]
        assert _events() == []

    async def test_persist_failure_refund_emits_nothing(self):
        db = _StubDB(fail_persist=True)
        res = await purchase_title(db, _char(), "wayfarer")
        assert res["ok"] is False and res["reason"] == "persist_failed"
        # debit + matching refund, but NO lifecycle event (the buy never landed).
        assert db.credit_log == [
            (-_WAYFARER["cost"], "vanity_title"),
            (_WAYFARER["cost"], "vanity_title_refund"),
        ]
        assert _events() == []

    async def test_grant_already_owned_emits_nothing(self):
        db = _StubDB()
        ok = await grant_earned_title(db, _char(owned=["hunter"]), "hunter")
        assert ok is False
        assert _events() == []

    async def test_grant_unknown_key_emits_nothing(self):
        db = _StubDB()
        ok = await grant_earned_title(db, _char(), "not_a_title")
        assert ok is False
        assert _events() == []

    async def test_grant_persist_failure_emits_nothing(self):
        db = _StubDB(fail_persist=True)
        ok = await grant_earned_title(db, _char(), "hunter")
        assert ok is False
        assert _events() == []


# ── sampling honours the tunable; the transaction still lands ─────────────────
class TestSampling:
    async def test_sample_zero_suppresses_event_not_the_purchase(self):
        tunables._TUNABLES["telemetry.title_sample"] = 0.0
        db = _StubDB()
        char = _char()
        res = await purchase_title(db, char, "wayfarer")

        assert res["ok"] is True
        assert _events() == []
        # The cost still debited + the title still owned despite no telemetry.
        assert db.credit_log == [(-_WAYFARER["cost"], "vanity_title")]
        assert "wayfarer" in char["vanity_titles"]
        assert char["display_title"] == _WAYFARER["label"]


# ── load-bearing: a broken sink never disturbs the prestige transaction ───────
class TestFailOpen:
    async def test_emit_raises_purchase_still_succeeds(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB()
        char = _char()
        with mock.patch.object(telemetry, "emit", _boom):
            res = await purchase_title(db, char, "wayfarer")

        assert res["ok"] is True          # no crash
        assert db.credit_log == [(-_WAYFARER["cost"], "vanity_title")]
        assert "wayfarer" in char["vanity_titles"]   # the buy still landed

    async def test_emit_raises_grant_still_succeeds(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB()
        char = _char()
        with mock.patch.object(telemetry, "emit", _boom):
            ok = await grant_earned_title(db, char, "hunter")

        assert ok is True
        assert "hunter" in char["vanity_titles"]


# ── helper unit: field schema + coercion ──────────────────────────────────────
class TestHelperSchema:
    def test_purchase_schema(self):
        titles._emit_title_telemetry(
            "purchase", 7, -2_000, key="wayfarer", tier=0, owned=1)
        e = _events()[0]
        assert e["action"] == "purchase"
        assert e["char_id"] == 7
        assert e["amount"] == -2_000
        assert e["key"] == "wayfarer"
        assert e["tier"] == 0
        assert e["owned"] == 1

    def test_str_id_coerced_to_int(self):
        titles._emit_title_telemetry("purchase", "42", -2_000)
        assert _events()[0]["char_id"] == 42

    def test_none_id_coerced_safely(self):
        # Fail-open coercion: a None id never raises (lands unchanged).
        titles._emit_title_telemetry("grant", None, 0)
        assert "char_id" in _events()[0]

    def test_none_extra_fields_dropped(self):
        titles._emit_title_telemetry("grant", 7, 0, key="hunter", tier=None)
        e = _events()[0]
        assert "tier" not in e             # None dropped
        assert e["key"] == "hunter"
        assert e["action"] == "grant"


# ── source pins: every lifecycle seam routes through the helper ──────────────
class TestSeamWiring:
    @classmethod
    def setup_class(cls):
        cls.src = (PROJECT_ROOT / "engine" / "titles.py").read_text(
            encoding="utf-8")

    @pytest.mark.parametrize("action", ['"purchase"', '"grant"'])
    def test_action_wired(self, action):
        assert f'_emit_title_telemetry({action}' in self.src, (
            f"titles.py must emit the {action} transition")

    def test_event_type_is_vanity_title(self):
        assert '_tele_emit("vanity_title"' in self.src

    def test_tunable_documented_in_yaml(self):
        ty = (PROJECT_ROOT / "data" / "tunables.yaml").read_text(
            encoding="utf-8")
        assert "telemetry.title_sample:" in ty
