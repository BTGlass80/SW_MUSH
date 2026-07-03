# -*- coding: utf-8 -*-
"""
tests/test_vendor_droid_concurrency_2026_07_02.py — launch-critical
credit-integrity + item-duplication regression (2026-07-02 break-it pass).

ROOT CAUSE (fixed in engine/vendor_droids.py): ``sell_to_droid``,
``buy_from_droid``, and ``collect_escrow`` each mutated a vendor droid's
shared JSON ``data`` blob (stock quantities, buy-order ``qty_filled`` /
``escrow_deposited``, ``escrow_credits``) via a read -> await(credits/
inventory mutation) -> write-back sequence with NO per-object lock. Two
concurrent operations against the SAME droid (two players, or one
operator's two accounts) could both pass their availability/affordability
check against the same stale read and both write — a lost update.

Confirmed pre-fix failures:
  #1 sell_to_droid — two concurrent ``sell <resource> to <shop>`` against a
     buy order funded for exactly 1 unit BOTH succeeded and BOTH got paid,
     minting credits against a single escrow deposit.
  #2 buy_from_droid — two concurrent ``buy <item> from <shop>`` against a
     stock slot of quantity=1 BOTH succeeded, duplicating the item while
     the droid's escrow/total_sales reflected only one sale.

FIX: a module-level per-droid ``asyncio.Lock`` (``_get_droid_lock``) now
wraps the critical section (data read through the final write-back) of
all three functions, serializing concurrent operations on the SAME droid
only. This suite drives the REAL player-facing command path (``buy ...
from <shop>`` / ``sell ... to <shop>``) through two independent, real
per-session game-loop tasks (``tests/harness.py``) fired concurrently via
``asyncio.gather`` — the same mechanism the break-it pass used to
originally reproduce both races — and asserts the two invariants now
hold:

  * Exactly one of the two concurrent operations succeeds; the other is
    cleanly refused (no traceback, no silent double-success).
  * Total payout never exceeds escrow / stock never goes negative, and
    ``qty_filled`` / ``escrow_credits`` / ``total_sales`` are consistent
    with the single completed transaction.

A third (bonus) class exercises the same lock on ``collect_escrow``
directly (two concurrent collects on one droid can't double-pay), since
the same read/await/write-back shape was fixed there too.

Run: python -m pytest tests/test_vendor_droid_concurrency_2026_07_02.py
"""
from __future__ import annotations

import asyncio
import json

from engine.vendor_droids import _dump_data, _load_data


# ── Seed helpers (raw INSERT — bypass purchase/place/post-order flows so
#    each test seeds exactly the racy state described in the bug report,
#    mirroring tests/smoke/scenarios/economy_extended.py's pattern) ────────

async def _seed_droid_with_stock(h, *, owner_id: int, room_id: int,
                                  item_key: str, item_name: str,
                                  price: int, qty: int,
                                  shop_name: str) -> int:
    """Place a vendor droid (gn4, no Bargain/faction modifiers) with one
    stocked slot and return its object id."""
    data = {
        "tier_key":  "gn4",
        "shop_name": shop_name,
        "shop_desc": "Concurrency regression droid.",
        "inventory": [{
            "slot":      1,
            "item_key":  item_key,
            "item_name": item_name,
            "price":     price,
            "quantity":  qty,
            "quality":   60,
            "crafter":   "",
            "listed_at": 0,
        }],
        "escrow_credits": 0,
        "buy_orders":     [],
        "total_sales":    0,
    }
    cursor = await h.db._db.execute(
        "INSERT INTO objects (type, owner_id, room_id, name, data) "
        "VALUES (?, ?, ?, ?, ?)",
        ("vendor_droid", owner_id, room_id, "GN-4 Vendor Droid",
         _dump_data(data)),
    )
    await h.db._db.commit()
    return cursor.lastrowid


async def _seed_droid_with_buy_order(h, *, owner_id: int, room_id: int,
                                      resource_type: str, min_quality: int,
                                      qty_wanted: int, price_per: int,
                                      shop_name: str) -> int:
    """Place a vendor droid (gn12, buy-orders enabled) with a single
    active buy order and return its object id."""
    data = {
        "tier_key":  "gn12",
        "shop_name": shop_name,
        "shop_desc": "Concurrency regression droid.",
        "inventory": [],
        "escrow_credits": 0,
        "buy_orders": [{
            "id":               1,
            "resource_type":    resource_type,
            "min_quality":      min_quality,
            "qty_wanted":       qty_wanted,
            "qty_filled":       0,
            "price_per":        price_per,
            "escrow_deposited": qty_wanted * price_per,
            "active":           True,
        }],
        "total_sales": 0,
    }
    cursor = await h.db._db.execute(
        "INSERT INTO objects (type, owner_id, room_id, name, data) "
        "VALUES (?, ?, ?, ?, ?)",
        ("vendor_droid", owner_id, room_id, "GN-12 Commerce Droid",
         _dump_data(data)),
    )
    await h.db._db.commit()
    return cursor.lastrowid


async def _give_resource(h, char_id: int, resource_type: str,
                          qty: int, quality: int) -> None:
    """Add a resource stack directly to a character's inventory JSON."""
    from engine.items import coerce_inventory
    row = await h.get_char(char_id)
    inv = coerce_inventory(row.get("inventory"))
    inv.setdefault("resources", [])
    inv["resources"].append({
        "type": resource_type, "quantity": qty, "quality": quality,
    })
    await h.db._db.execute(
        "UPDATE characters SET inventory = ? WHERE id = ?",
        (json.dumps(inv), char_id),
    )
    await h.db._db.commit()


# ── #2 buy_from_droid: two concurrent buyers on a qty=1 stock slot ────────

class TestBuyFromDroidConcurrency:
    async def test_two_concurrent_buyers_exactly_one_wins(self, harness):
        owner = await harness.login_as("BFDOwner", room_id=1, credits=0)
        droid_id = await _seed_droid_with_stock(
            harness, owner_id=owner.character["id"], room_id=1,
            item_key="blaster_pistol", item_name="Race Pistol",
            price=500, qty=1, shop_name="Race Shop A",
        )

        buyer_a = await harness.login_as("BFDBuyerA", room_id=1, credits=5000)
        buyer_b = await harness.login_as("BFDBuyerB", room_id=1, credits=5000)

        # Fire both purchases concurrently through the REAL command path —
        # two independent per-session game-loop tasks racing on one droid.
        out_a, out_b = await asyncio.gather(
            harness.cmd(buyer_a, "buy 1 from Race Shop A"),
            harness.cmd(buyer_b, "buy 1 from Race Shop A"),
        )

        assert "traceback" not in out_a.lower(), out_a[:400]
        assert "traceback" not in out_b.lower(), out_b[:400]

        wins = ("you purchase" in out_a.lower(),
                "you purchase" in out_b.lower())
        assert sum(wins) == 1, (
            f"Exactly one buyer must win the qty=1 race (item duplication "
            f"otherwise). A={out_a!r} B={out_b!r}"
        )

        # The loser is refused cleanly, not silently — must reference the
        # stock/availability gate, never a second success.
        loser_out = out_b if wins[0] else out_a
        assert "you purchase" not in loser_out.lower()

        # Exactly one buyer paid 500cr; the other is untouched.
        credits_a = await harness.get_credits(buyer_a.character["id"])
        credits_b = await harness.get_credits(buyer_b.character["id"])
        assert sorted([credits_a, credits_b]) == [4500, 5000], (
            f"Expected one buyer charged (4500) and one untouched (5000); "
            f"got A={credits_a} B={credits_b}"
        )

        # Droid state: stock fully consumed, escrow/total_sales reflect
        # EXACTLY one completed sale (net payout = 500 - 2% listing fee).
        obj = await harness.db.get_object(droid_id)
        data = _load_data(obj)
        stock_remaining = sum(
            s.get("quantity", 0) for s in data.get("inventory", [])
        )
        assert stock_remaining == 0, (
            f"Stock must be fully consumed by the single winning sale: "
            f"{data.get('inventory')!r}"
        )
        assert data.get("escrow_credits") == 490, (
            f"escrow_credits should reflect exactly one 490cr net sale "
            f"(500 - 2% gn4 listing fee); got {data.get('escrow_credits')!r}"
        )
        assert data.get("total_sales") == 1, (
            f"total_sales must be exactly 1, got {data.get('total_sales')!r}"
        )


# ── #1 sell_to_droid: two concurrent sellers filling a 1-unit buy order ───

class TestSellToDroidConcurrency:
    async def test_two_concurrent_sellers_payout_never_exceeds_escrow(
        self, harness,
    ):
        owner = await harness.login_as("STDOwner", room_id=1, credits=0)
        droid_id = await _seed_droid_with_buy_order(
            harness, owner_id=owner.character["id"], room_id=1,
            resource_type="metal", min_quality=50,
            qty_wanted=1, price_per=500, shop_name="STDOwner's Shop",
        )

        seller_a = await harness.login_as("STDSellerA", room_id=1, credits=1000)
        seller_b = await harness.login_as("STDSellerB", room_id=1, credits=1000)
        await _give_resource(harness, seller_a.character["id"], "metal", 5, 60)
        await _give_resource(harness, seller_b.character["id"], "metal", 5, 60)
        # Refresh each session's cached character so sell_to_droid sees the
        # resource stack just written (the session dict is otherwise stale
        # from login time — see tests/test_look_examine_inventory.py's
        # identical _seed_items reload pattern).
        seller_a.character = await harness.get_char(seller_a.character["id"])
        seller_b.character = await harness.get_char(seller_b.character["id"])

        out_a, out_b = await asyncio.gather(
            harness.cmd(seller_a, "sell metal to STDOwner's Shop"),
            harness.cmd(seller_b, "sell metal to STDOwner's Shop"),
        )

        assert "traceback" not in out_a.lower(), out_a[:400]
        assert "traceback" not in out_b.lower(), out_b[:400]

        wins = ("sold" in out_a.lower(), "sold" in out_b.lower())
        assert sum(wins) == 1, (
            f"Exactly one seller must win the 1-unit buy-order race "
            f"(minted credits otherwise). A={out_a!r} B={out_b!r}"
        )

        # Exactly one seller got paid 500cr; the other is untouched.
        credits_a = await harness.get_credits(seller_a.character["id"])
        credits_b = await harness.get_credits(seller_b.character["id"])
        assert sorted([credits_a, credits_b]) == [1000, 1500], (
            f"Expected one seller paid (1500) and one untouched (1000); "
            f"got A={credits_a} B={credits_b}"
        )

        # Order ledger internally consistent: exactly 1 unit filled, order
        # closed, and total payout never exceeds the escrow deposited.
        obj = await harness.db.get_object(droid_id)
        data = _load_data(obj)
        order = data["buy_orders"][0]
        assert order["qty_filled"] == 1, (
            f"qty_filled must be exactly 1, got {order['qty_filled']!r}"
        )
        assert order["active"] is False, "order should be closed after 1/1 filled"
        total_payout = order["qty_filled"] * order["price_per"]
        assert total_payout <= order["escrow_deposited"], (
            f"INVARIANT VIOLATED: payout {total_payout} exceeds escrow "
            f"{order['escrow_deposited']}"
        )
        assert total_payout == 500, f"expected exactly one 500cr payout, got {total_payout}"
        assert data.get("total_sales") == 1, (
            f"total_sales must be exactly 1, got {data.get('total_sales')!r}"
        )


# ── Bonus: collect_escrow — two concurrent collects can't double-pay ──────

class TestCollectEscrowConcurrency:
    async def test_two_concurrent_collects_pay_out_escrow_once(self, harness):
        from engine.vendor_droids import collect_escrow

        owner = await harness.login_as("CEOwner", room_id=1, credits=0)
        owner_id = owner.character["id"]
        data = {
            "tier_key": "gn4", "shop_name": "CE Shop", "shop_desc": "",
            "inventory": [], "buy_orders": [],
            "escrow_credits": 1000, "total_sales": 3,
        }
        cursor = await harness.db._db.execute(
            "INSERT INTO objects (type, owner_id, room_id, name, data) "
            "VALUES (?, ?, ?, ?, ?)",
            ("vendor_droid", owner_id, None, "GN-4 Vendor Droid",
             _dump_data(data)),
        )
        await harness.db._db.commit()
        droid_id = cursor.lastrowid

        # Two independent char dicts (simulating one operator's two
        # concurrent sessions/tabs) both call collect_escrow on the SAME
        # droid at the same time via asyncio.gather.
        char_1 = await harness.get_char(owner_id)
        char_2 = await harness.get_char(owner_id)
        results = await asyncio.gather(
            collect_escrow(char_1, droid_id, harness.db),
            collect_escrow(char_2, droid_id, harness.db),
        )

        oks = [ok for ok, _msg in results]
        assert sum(oks) == 1, (
            f"Exactly one collect must succeed (double-payout otherwise): "
            f"{results!r}"
        )

        # The droid's escrow is zeroed exactly once; the owner's real DB
        # balance reflects exactly ONE 1000cr payout, not two.
        obj = await harness.db.get_object(droid_id)
        post_data = _load_data(obj)
        assert post_data.get("escrow_credits") == 0
        final_credits = await harness.get_credits(owner_id)
        assert final_credits == 1000, (
            f"Owner should have received exactly one 1000cr payout; "
            f"got {final_credits}"
        )
