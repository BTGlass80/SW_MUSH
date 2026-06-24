# -*- coding: utf-8 -*-
"""tests/test_t319_den_telemetry.py — T3.19 telemetry for the Hutt-cartel
sabacc-den lifecycle (engine/dens.py).

The setup-cost credit leg already rides ``credit_flow`` (adjust_credits tags
``sabacc_den_setup``), and the den *rake* faucet is captured by the sabacc
``gamble`` emitter, but neither rejoins offline into the den *lifecycle* — the
per-org establish→abandon churn or the setup-sink volume. This drop adds ONE
fail-open, sample-tunable ``den`` event at each lifecycle transition: establish
(the 10k setup sink) and abandon (no credits move).

The behavioral suite drives the REAL ``establish_den`` / ``abandon_den`` against
a FakeDB (mirroring tests/test_a5_dens.py) and proves: exactly one event per
successful transition with the right action + signed amount + the org/room
fields; every refusal (and the write-failure refund path) emits nothing — never a
phantom establish/abandon signal; the ``telemetry.den_sample`` tunable is
honoured; and — the load-bearing contract — a broken sink NEVER disturbs the
establish/abandon it observes. The helper schema + the seam wiring are pinned
directly.

Run: python -m pytest tests/test_t319_den_telemetry.py
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

from engine import dens  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from engine.dens import (  # noqa: E402
    establish_den, abandon_den,
    DEN_SETUP_COST, DEN_ESTABLISH_MIN_RANK, DEN_SETUP_SOURCE,
)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Each test starts with a fresh sink + tunables, and cleans up after."""
    telemetry.reset()
    tunables.reset_tunables()
    yield
    telemetry.reset()
    tunables.reset_tunables()


def _events(ev_type="den"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


# ── FakeDB (mirrors tests/test_a5_dens.py) ────────────────────────────────────
class _FakeDB:
    def __init__(self, *, cantina=True, member_rank=DEN_ESTABLISH_MIN_RANK,
                 existing_den=None, balance=DEN_SETUP_COST, fail_write=False):
        self.cantina = cantina
        self.member_rank = member_rank
        self.existing_den = existing_den
        self.balance = balance
        self.fail_write = fail_write
        self.credit_log = []
        self.inserted = []
        self.deleted = []
        self.org = {"id": 9, "code": "hutt_cartel", "name": "The Hutt Cartel"}
        self._db = self   # so db._db.execute/commit route here

    async def get_room(self, rid):
        return {"id": rid, "zone_id": 1}

    async def get_zone(self, zid):
        return {"name": "Cantina District" if self.cantina else "Central Streets"}

    async def get_organization(self, code):
        return self.org if code == "hutt_cartel" else None

    async def get_membership(self, cid, oid):
        return ({"rank_level": self.member_rank}
                if self.member_rank is not None else None)

    async def fetchall(self, sql, params=()):
        if "WHERE room_id" in sql:
            return [self.existing_den] if self.existing_den else []
        if "WHERE org_id" in sql:
            return [self.existing_den] if self.existing_den else []
        return []

    async def adjust_credits(self, cid, delta, source, **kw):
        self.credit_log.append((cid, delta, source))
        self.balance += delta
        return self.balance

    async def execute(self, sql, params=()):
        if self.fail_write:
            raise RuntimeError("write boom")
        if sql.strip().upper().startswith("INSERT"):
            self.inserted.append(params)
        elif sql.strip().upper().startswith("DELETE"):
            self.deleted.append(params)

    async def commit(self):
        pass


def _char(cid=5, room_id=100, credits=DEN_SETUP_COST):
    return {"id": cid, "room_id": room_id, "credits": credits}


# ── establish: one event, the setup-cost sink ────────────────────────────────
class TestEstablishEmit:
    async def test_establish_emits_setup_sink(self):
        db = _FakeDB()
        res = await establish_den(db, _char())
        assert res["ok"] is True

        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "establish"
        assert e["char_id"] == 5
        assert e["amount"] == -DEN_SETUP_COST        # the sink delta
        assert e["org_id"] == 9
        assert e["org_code"] == "hutt_cartel"
        assert e["room_id"] == 100

    async def test_amount_matches_ledger_leg(self):
        db = _FakeDB()
        await establish_den(db, _char())
        e = _events()[0]
        # The emitted amount equals the sole setup-cost ledger debit.
        legs = [d for (_c, d, src) in db.credit_log if src == DEN_SETUP_SOURCE]
        assert legs == [-DEN_SETUP_COST]
        assert e["amount"] == legs[0]

    @pytest.mark.parametrize("kwargs", [
        {"cantina": False},                              # not_cantina
        {"member_rank": DEN_ESTABLISH_MIN_RANK - 1},     # rank
        {"member_rank": None},                           # not_member
        {"existing_den": {"room_id": 100, "org_id": 9}},  # already_den
        {"balance": DEN_SETUP_COST - 1},                 # insufficient
    ])
    async def test_refused_establish_emits_nothing(self, kwargs):
        bal = kwargs.get("balance", DEN_SETUP_COST)
        db = _FakeDB(**kwargs)
        res = await establish_den(db, _char(credits=bal))
        assert res["ok"] is False
        assert _events() == []          # no phantom establish signal

    async def test_write_failure_refund_emits_nothing(self):
        """A failed den write refunds and returns write_failed BEFORE the emit,
        so a failed establish leaves no telemetry."""
        db = _FakeDB(fail_write=True)
        res = await establish_den(db, _char())
        assert res["ok"] is False
        assert res["reason"] == "write_failed"
        assert _events() == []


# ── abandon: one lifecycle event, no credit movement ─────────────────────────
class TestAbandonEmit:
    async def test_abandon_emits_zero_amount(self):
        db = _FakeDB(existing_den={"room_id": 100, "org_id": 9,
                                   "org_code": "hutt_cartel"})
        res = await abandon_den(db, _char())
        assert res["ok"] is True

        evs = _events()
        assert len(evs) == 1
        e = evs[0]
        assert e["action"] == "abandon"
        assert e["char_id"] == 5
        assert e["amount"] == 0          # no refund — nothing moves
        assert e["org_id"] == 9
        assert e["org_code"] == "hutt_cartel"
        assert e["room_id"] == 100

    @pytest.mark.parametrize("existing_den", [
        None,                                                  # no_den
        {"room_id": 100, "org_id": 999, "org_code": "other"},  # not_yours
    ])
    async def test_refused_abandon_emits_nothing(self, existing_den):
        db = _FakeDB(existing_den=existing_den)
        res = await abandon_den(db, _char())
        assert res["ok"] is False
        assert _events() == []


# ── sampling honours the tunable; the transaction still lands ────────────────
class TestSampling:
    async def test_sample_zero_suppresses_event_not_the_setup(self):
        tunables._TUNABLES["telemetry.den_sample"] = 0.0
        db = _FakeDB()
        res = await establish_den(db, _char())

        assert res["ok"] is True
        assert _events() == []
        # The setup cost still debited + the den still written despite no telemetry.
        assert db.credit_log == [(5, -DEN_SETUP_COST, DEN_SETUP_SOURCE)]
        assert len(db.inserted) == 1


# ── load-bearing: a broken sink never disturbs the den transaction ───────────
class TestFailOpen:
    async def test_emit_raises_establish_still_succeeds(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _FakeDB()
        with mock.patch.object(telemetry, "emit", _boom):
            res = await establish_den(db, _char())

        assert res["ok"] is True          # no crash
        assert db.credit_log == [(5, -DEN_SETUP_COST, DEN_SETUP_SOURCE)]
        assert len(db.inserted) == 1      # the den row still landed


# ── helper unit: field schema + coercion ──────────────────────────────────────
class TestHelperSchema:
    def test_establish_schema(self):
        dens._emit_den("establish", 7, -DEN_SETUP_COST,
                       org_id=9, org_code="hutt_cartel", room_id=100)
        e = _events()[0]
        assert e["action"] == "establish"
        assert e["char_id"] == 7
        assert e["amount"] == -DEN_SETUP_COST
        assert e["org_id"] == 9
        assert e["org_code"] == "hutt_cartel"
        assert e["room_id"] == 100

    def test_str_id_coerced_to_int(self):
        dens._emit_den("establish", "42", -DEN_SETUP_COST)
        assert _events()[0]["char_id"] == 42

    def test_none_id_coerced_safely(self):
        # Fail-open coercion: a None id never raises (lands unchanged).
        dens._emit_den("abandon", None, 0)
        assert "char_id" in _events()[0]

    def test_none_extra_fields_dropped(self):
        dens._emit_den("abandon", 7, 0, org_id=9, org_code=None, room_id=100)
        e = _events()[0]
        assert "org_code" not in e        # None dropped
        assert e["org_id"] == 9
        assert e["room_id"] == 100


# ── source pins: every lifecycle seam routes through the helper ──────────────
class TestSeamWiring:
    @classmethod
    def setup_class(cls):
        cls.src = (PROJECT_ROOT / "engine" / "dens.py").read_text(
            encoding="utf-8")

    @pytest.mark.parametrize("action", ['"establish"', '"abandon"'])
    def test_action_wired(self, action):
        assert f'_emit_den({action}' in self.src, (
            f"dens.py must emit the {action} transition")

    def test_tunable_documented_in_yaml(self):
        ty = (PROJECT_ROOT / "data" / "tunables.yaml").read_text(
            encoding="utf-8")
        assert "telemetry.den_sample:" in ty
