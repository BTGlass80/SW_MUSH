# -*- coding: utf-8 -*-
"""
tests/test_commissary_sellback.py — ECON.commissary_sellback (2026-06-13).

Faction-issued / commissary gear:
  Piece 1 — ordinary vendors REFUSE to buy it back (npc_refuses_buyback
            now refuses faction_issued) — closes the buy-at-discount /
            resell-on-open-market laundering loop.
  Piece 2 — it sells back ONLY through the issuing commissary
            (`+commissary sell`), at COMMISSARY_SELLBACK_RATE (<=50%) of
            the requisition cost via the metered `commissary_sellback`
            faucet — smaller than the `commissary_purchase` sink that
            created it, so the round trip is a NET LOSS (no laundering).
  Piece 3 — it is BIND-TO-CHANNEL: tradeable among same-faction members
            (redistribution, laundering-neutral) but not to outsiders
            (faction_bound_transfer_blocked).
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Piece 1: vendor refusal extension ────────────────────────────────


class TestVendorRefusesFactionGear(unittest.TestCase):
    def test_refuses_faction_issued_dict(self):
        from engine.items import npc_refuses_buyback
        self.assertTrue(npc_refuses_buyback({"key": "x", "faction_issued": True}))

    def test_allows_ordinary_dict(self):
        from engine.items import npc_refuses_buyback
        self.assertFalse(npc_refuses_buyback({"key": "x"}))

    def test_still_refuses_high_quality_craft(self):
        # The pre-existing crafted-buyback gate must still hold.
        from engine.items import npc_refuses_buyback
        self.assertTrue(npc_refuses_buyback(
            {"key": "x", "crafter": "someone", "quality": 80}))

    def test_allows_low_quality_craft(self):
        from engine.items import npc_refuses_buyback
        self.assertFalse(npc_refuses_buyback(
            {"key": "x", "crafter": "someone", "quality": 10}))

    def test_works_on_instance_like_object(self):
        from engine.items import npc_refuses_buyback
        class _Inst:
            faction_issued = True
            crafter = None
            quality = 0
        self.assertTrue(npc_refuses_buyback(_Inst()))


# ── Piece 3: bind-to-channel transfer gate ───────────────────────────


class TestFactionBoundTransfer(unittest.TestCase):
    def _gear(self, fac="republic"):
        return {"key": "dc17_pistol", "faction_issued": True,
                "faction_code": fac}

    def test_same_faction_allowed(self):
        from engine.items import faction_bound_transfer_blocked
        self.assertFalse(
            faction_bound_transfer_blocked(self._gear("republic"),
                                           "republic", "republic"))

    def test_cross_faction_blocked(self):
        from engine.items import faction_bound_transfer_blocked
        self.assertTrue(
            faction_bound_transfer_blocked(self._gear("republic"),
                                           "republic", "hutt_cartel"))

    def test_outsider_blocked(self):
        from engine.items import faction_bound_transfer_blocked
        self.assertTrue(
            faction_bound_transfer_blocked(self._gear("republic"),
                                           "republic", None))

    def test_non_faction_item_never_blocked(self):
        from engine.items import faction_bound_transfer_blocked
        self.assertFalse(
            faction_bound_transfer_blocked({"key": "x"}, "republic", "hutt_cartel"))

    def test_no_faction_code_falls_back_to_open(self):
        from engine.items import faction_bound_transfer_blocked
        # faction_issued but no faction_code -> can't prove a channel,
        # don't block (the vendor-refusal lock is the laundering guard).
        self.assertFalse(faction_bound_transfer_blocked(
            {"key": "x", "faction_issued": True}, "republic", "hutt_cartel"))


# ── Piece 2: the commissary sellback channel ─────────────────────────


class _SellStubDB:
    """Stub with the inventory + credit surface sell_commissary uses."""
    def __init__(self, inv):
        self._inv = list(inv)
        self.credit_log = []        # (delta, source)
        self.removed = []           # keys
        self.added = []             # restored items

    async def get_inventory(self, cid):
        return list(self._inv)

    async def remove_from_inventory(self, cid, key):
        for i, it in enumerate(self._inv):
            if isinstance(it, dict) and it.get("key") == key:
                self._inv.pop(i)
                self.removed.append(key)
                return True
        return False

    async def add_to_inventory(self, cid, item):
        self.added.append(item)

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((delta, source))
        return 100_000 + delta


class TestCommissarySell(unittest.TestCase):
    def _char(self):
        return {"id": 5, "credits": 100_000}

    def _rep_gear(self, cost=500):
        return {"key": "dc17_pistol", "name": "DC-17 Hand Blaster",
                "faction_issued": True, "faction_code": "republic",
                "commissary": True, "requisition_cost": cost}

    def test_sellback_refunds_half_via_faucet(self):
        from engine.commissary import sell_commissary
        db = _SellStubDB([self._rep_gear(500)])
        res = _run(sell_commissary(db, self._char(), "republic", "dc17_pistol"))
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["refund"], 250)  # 50% of 500
        self.assertEqual(db.removed, ["dc17_pistol"])
        self.assertEqual(db.credit_log, [(250, "commissary_sellback")])

    def test_refund_is_smaller_than_purchase_sink(self):
        # The anti-laundering invariant: refund < what the purchase sink took.
        from engine.commissary import sell_commissary, COMMISSARY_SELLBACK_RATE
        cost = 500
        db = _SellStubDB([self._rep_gear(cost)])
        res = _run(sell_commissary(db, self._char(), "republic", "dc17_pistol"))
        self.assertLess(res["refund"], cost)
        self.assertEqual(res["refund"], int(cost * COMMISSARY_SELLBACK_RATE))

    def test_not_owned(self):
        from engine.commissary import sell_commissary
        db = _SellStubDB([])  # empty inventory
        res = _run(sell_commissary(db, self._char(), "republic", "dc17_pistol"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_owned")
        self.assertEqual(db.credit_log, [])

    def test_wrong_channel_refused(self):
        # A Republic player can't sell Hutt-issued gear at the Republic
        # commissary.
        from engine.commissary import sell_commissary
        hutt_gear = {"key": "x", "name": "Hutt Blaster", "faction_issued": True,
                     "faction_code": "hutt_cartel", "requisition_cost": 400}
        db = _SellStubDB([hutt_gear])
        res = _run(sell_commissary(db, self._char(), "republic", "x"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "wrong_channel")
        self.assertEqual(db.credit_log, [])  # nothing paid, nothing removed
        self.assertEqual(db.removed, [])

    def test_non_faction_item_not_sellable_here(self):
        # A plain (non-faction) item isn't a commissary sellback target.
        from engine.commissary import sell_commissary
        db = _SellStubDB([{"key": "junk", "name": "Junk"}])
        res = _run(sell_commissary(db, self._char(), "republic", "junk"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_owned")

    def test_legacy_item_without_stamped_cost_uses_stock(self):
        # An item issued before requisition_cost was stamped falls back to
        # the current stock price for the refund.
        from engine.commissary import sell_commissary
        legacy = {"key": "dc17_pistol", "name": "DC-17 Hand Blaster",
                  "faction_issued": True, "faction_code": "republic"}
        db = _SellStubDB([legacy])
        res = _run(sell_commissary(db, self._char(), "republic", "dc17_pistol"))
        self.assertTrue(res["ok"], res)
        self.assertGreater(res["refund"], 0)  # resolved from stock (500 -> 250)
        self.assertEqual(res["refund"], 250)

    def test_no_commissary_faction(self):
        from engine.commissary import sell_commissary
        db = _SellStubDB([])
        res = _run(sell_commissary(db, self._char(), "jedi_order", "x"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "no_commissary")


# ── The round trip is a net loss (the whole point) ───────────────────


class TestNoLaunderingLoop(unittest.TestCase):
    def test_buy_then_sellback_nets_a_loss(self):
        from engine.commissary import (
            purchase_commissary, sell_commissary, COMMISSARY_SELLBACK_RATE,
        )

        # Shared stub that records all credit movement across buy + sell.
        class _DB(_SellStubDB):
            async def add_to_inventory(self, cid, item):
                self._inv.append(item)   # buy grants into the same inv

        db = _DB([])
        char = {"id": 7, "credits": 100_000}
        buy = _run(purchase_commissary(db, char, "republic", 1, "dc17_pistol"))
        self.assertTrue(buy["ok"])
        sell = _run(sell_commissary(db, char, "republic", "dc17_pistol"))
        self.assertTrue(sell["ok"], sell)
        # Sum of credit deltas across the round trip is strictly negative.
        net = sum(d for d, _ in db.credit_log)
        self.assertLess(net, 0)
        self.assertEqual(net, -buy["cost"] + sell["refund"])
        self.assertLessEqual(
            sell["refund"], int(buy["cost"] * COMMISSARY_SELLBACK_RATE))


if __name__ == "__main__":
    unittest.main()
