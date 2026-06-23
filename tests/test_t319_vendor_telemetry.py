"""tests/test_t319_vendor_telemetry.py — T3.19 telemetry for the player-vendor
marketplace loop (engine/vendor_droids.py).

The credit legs already ride ``credit_flow`` (adjust_credits tags
``vendor_purchase`` on a buy, ``vendor_buy_order_payout`` on a buy-order fill)
and ``log_shop_transaction`` keeps a per-droid ledger — but neither rejoins the
player↔player vendor economy into a single offline stream tagged with the
price-modifier deltas (the Tier 2+ Bargain win, the faction-rep discount/markup,
the listing fee, the city tax) that decide whether a listing actually moved.
This drop adds ONE fail-open, sample-tunable ``vendor_txn`` event at the two
success seams: ``buy_from_droid`` (phase ``buy``) and ``sell_to_droid``
(phase ``sell`` = a Tier 3 buy-order fill).

This suite drives the REAL ``buy_from_droid`` / ``sell_to_droid`` against a
recording stub DB and proves: exactly one ``vendor_txn`` per completed trade
with the right phase + envelope; every non-completing path (own-droid, no stock,
unknown item, insufficient credits, no matching order) emits nothing; the
``telemetry.vendor_sample`` tunable is honoured; the price-modifier ``base_price``
delta + fee + city_tax are captured; and — the load-bearing contract — a broken
sink NEVER disturbs the completed trade it observes.

Run: python -m pytest tests/test_t319_vendor_telemetry.py
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
from engine import vendor_droids  # noqa: E402
from engine.vendor_droids import (  # noqa: E402
    buy_from_droid, sell_to_droid, _emit_vendor_telemetry,
)

REPO = Path(PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _events(ev_type="vendor_txn"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _StubDB:
    """Records the trade's ledger + object/inventory writes.

    Models just enough of the Database surface for ``buy_from_droid`` /
    ``sell_to_droid`` to run their happy path: get_object, get_character,
    adjust_credits, save_character, update_object, log_shop_transaction.
    """

    def __init__(self, *, obj, owner_faction="independent",
                 adjust_returns_none=False):
        self._obj = obj
        self._owner_faction = owner_faction
        self._adjust_returns_none = adjust_returns_none
        self.credit_log = []          # (cid, delta, source)
        self.shop_txns = []           # log_shop_transaction kwargs
        self.saved = []               # (cid, kwargs)
        self.updated = []             # (oid, data)

    async def get_object(self, oid):
        return self._obj

    async def get_character(self, cid):
        # The droid owner — independent by default so no faction shop modifier
        # and no crafting_sale rep hook fire (keeps the happy path branch-free).
        return {"id": cid, "faction_id": self._owner_faction}

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((cid, delta, source))
        if self._adjust_returns_none and allow_negative is False:
            return None
        return 100_000 + delta

    async def save_character(self, cid, **kwargs):
        self.saved.append((cid, kwargs))

    async def update_object(self, oid, **kwargs):
        self.updated.append((oid, kwargs))

    async def log_shop_transaction(self, **kwargs):
        self.shop_txns.append(kwargs)


def _buy_obj(owner_id=99, room_id=1):
    """A Tier 1 (gn4) droid with one stocked item, owned by owner_id."""
    data = {
        "tier": 1,
        "tier_key": "gn4",
        "shop_name": "Test Shop",
        "inventory": [{
            "slot": 1, "item_key": "blaster_pistol", "item_name": "DL-18",
            "quality": 78, "quantity": 2, "price": 500, "crafter": "Voss",
        }],
        "escrow_credits": 0,
    }
    return {"id": 1, "owner_id": owner_id, "room_id": room_id,
            "name": "GN-4", "data": data}


def _sell_obj(owner_id=99, room_id=1):
    """A Tier 3 droid with one open buy order for durasteel."""
    data = {
        "tier": 3,
        "tier_key": "gn12",
        "shop_name": "Test Shop",
        "inventory": [],
        "buy_orders": [{
            "order_id": 1, "active": True, "resource_type": "durasteel",
            "qty_wanted": 5, "qty_filled": 0, "min_quality": 0,
            "price_per": 100, "escrow_deposited": 500,
        }],
    }
    return {"id": 1, "owner_id": owner_id, "room_id": room_id,
            "name": "GN-12", "data": data}


def _buyer(cid=7, credits=100_000):
    return {"id": cid, "credits": credits, "inventory": "{}"}


def _seller_with_durasteel(cid=7, credits=1_000, qty=3, quality=50):
    inv = json.dumps({"resources": [
        {"type": "durasteel", "quality": quality, "quantity": qty},
    ]})
    return {"id": cid, "credits": credits, "inventory": inv}


class VendorTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()
        # City tax is a no-op in the base path: room is in no city.
        self._city = mock.patch(
            "engine.player_cities.apply_city_tax",
            new=mock.AsyncMock(return_value=(0, None, None)),
        )
        self._city.start()

    def tearDown(self):
        self._city.stop()
        telemetry.reset()
        tunables.reset_tunables()

    # ── buy: one event, the marketplace sink + modifier legs ──────────────────
    def test_buy_emits_one_event(self):
        db = _StubDB(obj=_buy_obj())
        ok, _msg = _run(buy_from_droid(_buyer(), 1, "1", db))
        self.assertTrue(ok)
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["phase"], "buy")
        self.assertEqual(e["char_id"], 7)
        self.assertEqual(e["seller_id"], 99)
        self.assertEqual(e["droid_id"], 1)
        self.assertEqual(e["item_key"], "blaster_pistol")
        self.assertEqual(e["item_name"], "DL-18")
        self.assertEqual(e["quality"], 78)
        self.assertEqual(e["price"], 500)       # gn4: no bargain/faction shift
        self.assertEqual(e["qty"], 1)
        self.assertEqual(e["fee"], 10)          # max(1, int(500 * 0.02))
        self.assertEqual(e["tier"], 1)
        # No price modifier → base_price collapses out; no city → no city_tax.
        self.assertNotIn("base_price", e)
        self.assertNotIn("city_tax", e)

    def test_buy_event_matches_ledger_leg(self):
        db = _StubDB(obj=_buy_obj())
        _run(buy_from_droid(_buyer(), 1, "1", db))
        e = _events()[0]
        debit = [c for c in db.credit_log
                 if c == (7, -500, "vendor_purchase")]
        self.assertEqual(len(debit), 1)
        # The single event re-links the price to the ledger leg.
        self.assertEqual(e["price"], -debit[0][1])

    def test_buy_by_item_name_also_emits(self):
        db = _StubDB(obj=_buy_obj())
        ok, _ = _run(buy_from_droid(_buyer(), 1, "DL-18", db))
        self.assertTrue(ok)
        self.assertEqual(len(_events()), 1)

    def test_buy_captures_city_tax(self):
        # A taxed room: the city carves its slice out of the seller net; the
        # event records it so the seller's take is derivable offline.
        with mock.patch("engine.player_cities.apply_city_tax",
                        new=mock.AsyncMock(return_value=(7, 1, "Mos Eisley"))):
            db = _StubDB(obj=_buy_obj())
            ok, _ = _run(buy_from_droid(_buyer(), 1, "1", db))
        self.assertTrue(ok)
        e = _events()[0]
        self.assertEqual(e["city_tax"], 7)

    # ── sell: one event, the buy-order payout faucet ──────────────────────────
    def test_sell_emits_one_event(self):
        db = _StubDB(obj=_sell_obj())
        ok, _msg = _run(sell_to_droid(_seller_with_durasteel(), 1,
                                      "durasteel", 2, db))
        self.assertTrue(ok)
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["phase"], "sell")
        self.assertEqual(e["char_id"], 7)       # the acting player = seller
        self.assertEqual(e["seller_id"], 99)    # the order owner = buyer
        self.assertEqual(e["droid_id"], 1)
        self.assertEqual(e["item_key"], "durasteel")
        self.assertEqual(e["qty"], 2)
        self.assertEqual(e["price"], 200)       # 2 * price_per(100)
        self.assertEqual(e["tier"], 3)
        self.assertNotIn("base_price", e)

    def test_sell_event_matches_ledger_leg(self):
        db = _StubDB(obj=_sell_obj())
        _run(sell_to_droid(_seller_with_durasteel(), 1, "durasteel", 2, db))
        e = _events()[0]
        credit = [c for c in db.credit_log
                  if c == (7, 200, "vendor_buy_order_payout")]
        self.assertEqual(len(credit), 1)
        self.assertEqual(e["price"], credit[0][1])

    # ── non-completing paths emit nothing ─────────────────────────────────────
    def test_buy_own_droid_no_emit(self):
        db = _StubDB(obj=_buy_obj(owner_id=7))   # buyer owns the droid
        ok, _ = _run(buy_from_droid(_buyer(cid=7), 1, "1", db))
        self.assertFalse(ok)
        self.assertEqual(len(_events()), 0)

    def test_buy_unknown_item_no_emit(self):
        db = _StubDB(obj=_buy_obj())
        ok, _ = _run(buy_from_droid(_buyer(), 1, "nonesuch", db))
        self.assertFalse(ok)
        self.assertEqual(len(_events()), 0)

    def test_buy_insufficient_credits_no_emit(self):
        db = _StubDB(obj=_buy_obj())
        ok, _ = _run(buy_from_droid(_buyer(credits=100), 1, "1", db))
        self.assertFalse(ok)
        self.assertEqual(len(_events()), 0)

    def test_buy_abort_on_adjust_none_no_emit(self):
        # allow_negative=False refuses the debit (stale cache / race) → the buy
        # never completes, so no vendor_txn even though we reached the chokepoint.
        db = _StubDB(obj=_buy_obj(), adjust_returns_none=True)
        ok, _ = _run(buy_from_droid(_buyer(), 1, "1", db))
        self.assertFalse(ok)
        self.assertEqual(len(_events()), 0)

    def test_sell_no_matching_order_no_emit(self):
        db = _StubDB(obj=_sell_obj())
        ok, _ = _run(sell_to_droid(_seller_with_durasteel(), 1,
                                   "plasteel", 2, db))   # no order for plasteel
        self.assertFalse(ok)
        self.assertEqual(len(_events()), 0)

    def test_sell_own_droid_no_emit(self):
        db = _StubDB(obj=_sell_obj(owner_id=7))
        ok, _ = _run(sell_to_droid(_seller_with_durasteel(cid=7), 1,
                                   "durasteel", 2, db))
        self.assertFalse(ok)
        self.assertEqual(len(_events()), 0)

    # ── sampling honours the tunable, mutation still lands ─────────────────────
    def test_sample_zero_suppresses_event_not_the_buy(self):
        tunables._TUNABLES["telemetry.vendor_sample"] = 0.0
        db = _StubDB(obj=_buy_obj())
        ok, _ = _run(buy_from_droid(_buyer(), 1, "1", db))
        self.assertTrue(ok)
        self.assertEqual(len(_events()), 0)
        # The trade still debited the buyer despite no telemetry.
        self.assertIn((7, -500, "vendor_purchase"), db.credit_log)

    def test_sample_default_captures(self):
        db = _StubDB(obj=_buy_obj())
        _run(buy_from_droid(_buyer(), 1, "1", db))
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the trade ──────────────────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db = _StubDB(obj=_buy_obj())
        with mock.patch.object(telemetry, "emit", _boom):
            ok, _ = _run(buy_from_droid(_buyer(), 1, "1", db))
        # No crash; the trade resolved and the ledger leg was written.
        self.assertTrue(ok)
        self.assertIn((7, -500, "vendor_purchase"), db.credit_log)

    # ── helper unit: field schema + the base_price modifier delta ─────────────
    def test_helper_buy_schema(self):
        _emit_vendor_telemetry(
            "buy", 7, seller_id=99, droid_id=1, item_key="blaster_pistol",
            item_name="DL-18", quality=78, price=450, base_price=500,
            qty=1, fee=9, city_tax=5, tier=2)
        e = _events()[0]
        self.assertEqual(e["phase"], "buy")
        self.assertEqual(e["price"], 450)
        self.assertEqual(e["base_price"], 500)   # modifier delta surfaced
        self.assertEqual(e["fee"], 9)
        self.assertEqual(e["city_tax"], 5)
        self.assertEqual(e["tier"], 2)

    def test_helper_omits_base_price_when_equal(self):
        # base_price == price means no bargain/faction shift → drop it.
        _emit_vendor_telemetry("buy", 7, price=500, base_price=500)
        self.assertNotIn("base_price", _events()[0])

    def test_helper_omits_zero_fee_and_tax(self):
        _emit_vendor_telemetry("sell", 7, price=200, fee=0, city_tax=0)
        e = _events()[0]
        self.assertNotIn("fee", e)
        self.assertNotIn("city_tax", e)

    def test_helper_coerces_none_id(self):
        _emit_vendor_telemetry("buy", None, price=0)
        self.assertIn("char_id", _events()[0])

    # ── both seams wired + tunable registered (source pins) ───────────────────
    def test_both_seams_call_helper(self):
        src = (REPO / "engine" / "vendor_droids.py").read_text(encoding="utf-8")
        self.assertIn('_emit_vendor_telemetry(\n        "buy"', src)
        self.assertIn('_emit_vendor_telemetry(\n        "sell"', src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.vendor_sample:", ty)


if __name__ == "__main__":
    unittest.main()
