"""tests/test_t319_commissary_telemetry.py — T3.19 telemetry for the faction
commissary requisition loop (engine/commissary.py).

The credit legs already ride ``credit_flow`` (adjust_credits tags
``commissary_purchase`` / ``commissary_purchase_refund`` / ``commissary_sellback``),
but those ledger rows can't be rejoined offline into a per-item buy→sellback
round trip, carry no faction or item identity, and never reveal the rank gate a
purchase cleared. This drop adds ONE fail-open, sample-tunable ``commissary_txn``
event at the two success seams: ``purchase_commissary`` (phase ``buy``, the sink
+ the rank it cleared) and ``sell_commissary`` (phase ``sell``, the refund
faucet).

This suite drives the REAL ``purchase_commissary`` / ``sell_commissary`` against
a recording stub DB and proves: exactly one ``commissary_txn`` per completed
requisition with the right phase + envelope; every non-completing path (failed
buy: insufficient / unknown / rank-locked / refunded-grant; failed sell:
not-owned) emits nothing; the ``telemetry.commissary_sample`` tunable is
honoured; and — the load-bearing contract — a broken sink NEVER disturbs the
completed requisition it observes.

Run: python -m pytest tests/test_t319_commissary_telemetry.py
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
from engine.commissary import (  # noqa: E402
    purchase_commissary, sell_commissary, _emit_commissary_telemetry,
)

REPO = Path(PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _events(ev_type="commissary_txn"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _StubDB:
    """Records the requisition's ledger + inventory writes."""

    def __init__(self, *, inventory=None, fail_grant=False,
                 adjust_returns_none=False):
        self.credit_log = []     # (cid, delta, source)
        self.granted = []        # item dicts
        self.removed = []        # (cid, key)
        self._inventory = inventory or []
        self._fail_grant = fail_grant
        self._adjust_returns_none = adjust_returns_none

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((cid, delta, source))
        if self._adjust_returns_none and allow_negative is False:
            return None
        return 100_000 + delta

    async def add_to_inventory(self, cid, item):
        if self._fail_grant:
            raise RuntimeError("grant boom")
        self.granted.append(item)

    async def get_inventory(self, cid):
        return list(self._inventory)

    async def remove_from_inventory(self, cid, key):
        self.removed.append((cid, key))
        return True


def _issued_item():
    """A faction-issued commissary item, eligible for sellback."""
    return {
        "key": "dc17_pistol", "name": "DC-17 Hand Blaster",
        "faction_issued": True, "faction_code": "republic",
        "requisition_cost": 500,
    }


class CommissaryTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    def _char(self, credits=100_000):
        return {"id": 5, "credits": credits}

    # ── buy: one event, the sink + the rank gate ──────────────────────────────
    def test_buy_emits_one_event(self):
        db = _StubDB()
        res = _run(purchase_commissary(db, self._char(), "republic", 1,
                                       "dc17_pistol"))
        self.assertTrue(res["ok"])
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["phase"], "buy")
        self.assertEqual(e["char_id"], 5)
        self.assertEqual(e["faction"], "republic")
        self.assertEqual(e["item_key"], "dc17_pistol")
        self.assertEqual(e["item_name"], "DC-17 Hand Blaster")
        self.assertEqual(e["cost"], 500)        # the sink amount
        self.assertEqual(e["rank_level"], 1)    # the gate it cleared
        # A sell-only field never appears on a buy event.
        self.assertNotIn("refund", e)

    def test_buy_event_matches_ledger_leg(self):
        db = _StubDB()
        _run(purchase_commissary(db, self._char(), "republic", 1, "dc17_pistol"))
        e = _events()[0]
        debit = [c for c in db.credit_log if c == (5, -500, "commissary_purchase")]
        self.assertEqual(len(debit), 1)
        # The single event re-links the sink amount to the ledger leg.
        self.assertEqual(e["cost"], -debit[0][1])

    def test_buy_faction_case_normalized(self):
        # CIS commissary requisition (case-insensitive) — faction lower-cased
        # in the record. civilian_gear is real CIS rank-1 stock.
        db = _StubDB()
        res = _run(purchase_commissary(db, self._char(), "CIS", 1,
                                       "civilian_gear"))
        self.assertTrue(res["ok"])
        self.assertEqual(_events()[0]["faction"], "cis")

    # ── sell: one event, the refund faucet ────────────────────────────────────
    def test_sell_emits_one_event(self):
        db = _StubDB(inventory=[_issued_item()])
        res = _run(sell_commissary(db, self._char(), "republic", "dc17_pistol"))
        self.assertTrue(res["ok"])
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["phase"], "sell")
        self.assertEqual(e["char_id"], 5)
        self.assertEqual(e["faction"], "republic")
        self.assertEqual(e["item_key"], "dc17_pistol")
        self.assertEqual(e["item_name"], "DC-17 Hand Blaster")
        self.assertEqual(e["refund"], 250)      # 50% of the 500 requisition cost
        # A buy-only field never appears on a sell event.
        self.assertNotIn("cost", e)
        self.assertNotIn("rank_level", e)

    def test_sell_event_matches_ledger_leg(self):
        db = _StubDB(inventory=[_issued_item()])
        _run(sell_commissary(db, self._char(), "republic", "dc17_pistol"))
        e = _events()[0]
        credit = [c for c in db.credit_log if c == (5, 250, "commissary_sellback")]
        self.assertEqual(len(credit), 1)
        self.assertEqual(e["refund"], credit[0][1])

    # ── non-completing paths emit nothing ─────────────────────────────────────
    def test_insufficient_buy_no_emit(self):
        db = _StubDB()
        res = _run(purchase_commissary(db, self._char(credits=499), "republic",
                                       1, "dc17_pistol"))   # dc17_pistol is 500
        self.assertFalse(res["ok"])
        self.assertEqual(len(_events()), 0)

    def test_unknown_buy_no_emit(self):
        db = _StubDB()
        res = _run(purchase_commissary(db, self._char(), "republic", 5, "nope"))
        self.assertFalse(res["ok"])
        self.assertEqual(len(_events()), 0)

    def test_rank_locked_buy_no_emit(self):
        db = _StubDB()
        res = _run(purchase_commissary(db, self._char(), "republic", 0,
                                       "dc15_blaster_rifle"))   # min_rank 1
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "rank_locked")
        self.assertEqual(len(_events()), 0)

    def test_refunded_grant_no_emit(self):
        # Grant fails after the debit → refund fires, requisition fails: the
        # buy never completed, so no commissary_txn.
        db = _StubDB(fail_grant=True)
        res = _run(purchase_commissary(db, self._char(), "republic", 1,
                                       "dc17_pistol"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "grant_failed")
        self.assertEqual(len(_events()), 0)

    def test_sell_not_owned_no_emit(self):
        db = _StubDB(inventory=[])   # nothing to sell
        res = _run(sell_commissary(db, self._char(), "republic", "dc17_pistol"))
        self.assertFalse(res["ok"])
        self.assertEqual(len(_events()), 0)

    # ── sampling honours the tunable, mutation still lands ─────────────────────
    def test_sample_zero_suppresses_event_not_the_buy(self):
        tunables._TUNABLES["telemetry.commissary_sample"] = 0.0
        db = _StubDB()
        res = _run(purchase_commissary(db, self._char(), "republic", 1,
                                       "dc17_pistol"))
        self.assertTrue(res["ok"])
        self.assertEqual(len(_events()), 0)
        # The requisition still debited + granted despite no telemetry.
        self.assertIn((5, -500, "commissary_purchase"), db.credit_log)
        self.assertEqual(len(db.granted), 1)

    def test_sample_default_captures(self):
        db = _StubDB()
        _run(purchase_commissary(db, self._char(), "republic", 1, "dc17_pistol"))
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the requisition ────────────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB()
        with mock.patch.object(telemetry, "emit", _boom):
            res = _run(purchase_commissary(db, self._char(), "republic", 1,
                                           "dc17_pistol"))
        # No crash; the requisition resolved and the ledger + grant were written.
        self.assertTrue(res["ok"])
        self.assertIn((5, -500, "commissary_purchase"), db.credit_log)
        self.assertEqual(len(db.granted), 1)

    # ── helper unit: field schema per phase ───────────────────────────────────
    def test_helper_buy_schema(self):
        _emit_commissary_telemetry(
            "buy", 5, "Republic", item_key="dc17_pistol",
            item_name="DC-17 Hand Blaster", cost=500, rank_level=1)
        e = _events()[0]
        self.assertEqual(e["phase"], "buy")
        self.assertEqual(e["faction"], "republic")   # normalized
        self.assertEqual(e["cost"], 500)
        self.assertEqual(e["rank_level"], 1)
        self.assertNotIn("refund", e)

    def test_helper_sell_schema(self):
        _emit_commissary_telemetry(
            "sell", 5, "republic", item_key="dc17_pistol",
            item_name="DC-17 Hand Blaster", refund=250)
        e = _events()[0]
        self.assertEqual(e["phase"], "sell")
        self.assertEqual(e["refund"], 250)
        self.assertNotIn("cost", e)
        self.assertNotIn("rank_level", e)

    def test_helper_coerces_none_id(self):
        # Fail-open coercion: a None id never raises (lands unchanged, str-safe).
        _emit_commissary_telemetry("buy", None, "republic", cost=0)
        e = _events()[0]
        self.assertIn("char_id", e)

    def test_helper_buy_omits_rank_when_none(self):
        _emit_commissary_telemetry("buy", 5, "republic", cost=500)
        e = _events()[0]
        self.assertNotIn("rank_level", e)

    # ── both seams wired + tunable registered (source pins) ───────────────────
    def test_both_seams_call_helper(self):
        src = (REPO / "engine" / "commissary.py").read_text(encoding="utf-8")
        self.assertIn('_emit_commissary_telemetry(\n        "buy"', src)
        self.assertIn('_emit_commissary_telemetry(\n        "sell"', src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.commissary_sample:", ty)


if __name__ == "__main__":
    unittest.main()
