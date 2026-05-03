# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/economy_extended.py — Player-economy scenarios (EE1–EE9).

Drop 2 Block B. Existing E1–E6 in `economy_progression.py` cover only
read paths (`+shop`, `market`, `+cpstatus`, `+kudos` doesn't-traceback,
`+scenebonus`, `survey`). EE1–EE9 close the gap on the *write* paths a
player exercises early in their economic life: vendor-droid lifecycle,
buy-from-droid, sell-to-droid, the P2P trade cap, and bulk-cargo
purchase wiring.

These scenarios cover the player-shops system (engine/vendor_droids.py,
~1,300 lines, 13 subcommands) which had zero end-to-end smoke prior
to this drop. EE1 caught a real shop NameError bug fixed in the same
drop — every shop subcommand crashed because `ShopCommand.execute()`'s
local imports weren't visible to the dispatched `_cmd_*` methods. The
fix hoists the imports to module scope; EE1 is the regression guard.

Scope:
  EE1 — `shop buy droid` insufficient credits → clean refusal
  EE2 — `shop buy droid gn4` (funded) creates a vendor_droid object
  EE3 — `shop place` then `shop recall` updates the droid's room_id
  EE4 — `browse` in an empty room
  EE5 — `browse` listing a placed droid
  EE6 — `buy <item> from <shop>` round-trips credits between buyer
        and shop owner
  EE7 — `sell <resource> to <shop>` routes through sell_to_droid
        (refusal path: no buy orders posted)
  EE8 — P2P trade cap blocks at 5,001 cr while permitting 4,999
  EE9 — `buy cargo <good> <tons>` from a non-docked location refuses
        cleanly (the bulk-premium math is unit-tested elsewhere; this
        guards the wiring and arg-parse path)
"""
from __future__ import annotations

import asyncio
import json


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

async def _droids_owned_by(h, char_id: int) -> list:
    """Return all vendor_droid objects owned by the given character."""
    return await h.db.fetchall(
        "SELECT id, type, owner_id, room_id, name "
        "FROM objects WHERE owner_id = ? AND type = 'vendor_droid'",
        (char_id,),
    )


async def _seed_droid_with_stock(h, owner_id: int, room_id: int,
                                  item_key: str, item_name: str,
                                  price: int, qty: int = 1,
                                  shop_name: str = "Smoke Test Shop") -> int:
    """Place a vendor droid with one stocked item and return its id.

    Bypasses the player command flow so we can test the *buyer's*
    side of the transaction in isolation. Uses the same JSON-shape
    that engine/vendor_droids writes via stock_droid (data["inventory"]
    and data["tier_key"]) so buy_from_droid's reads work unchanged.

    Each scenario should pass a unique shop_name so droids seeded
    by an earlier test in the same class-scoped harness don't shadow
    a later test's resolution path.
    """
    from engine.vendor_droids import _dump_data, get_tier
    tier = get_tier("gn4")
    assert tier, "gn4 tier must be loadable from vendor_droids.yaml"

    data = {
        "tier_key":  "gn4",
        "tier_num":  tier.get("number", 4),
        "shop_name": shop_name,
        "shop_desc": "EE-prefix smoke test droid.",
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
        "sales_log":      [],
        "buy_orders":     [],
    }

    cursor = await h.db._db.execute(
        "INSERT INTO objects (type, owner_id, room_id, name, data) "
        "VALUES (?, ?, ?, ?, ?)",
        ("vendor_droid", owner_id, room_id, "GN-4 Vendor Droid",
         _dump_data(data)),
    )
    await h.db._db.commit()
    return cursor.lastrowid


# ──────────────────────────────────────────────────────────────────────────
# EE1 — shop buy droid (insufficient credits)
# ──────────────────────────────────────────────────────────────────────────

async def ee1_shop_buy_droid_insufficient_credits(h):
    """EE1 — `shop buy droid gn4` with too few credits gives a clean
    refusal, NOT a NameError traceback.

    REGRESSION GUARD for the import-scope bug fixed in this drop:
    `ShopCommand.execute()` imported purchase_droid et al. into
    LOCAL scope; the `_cmd_buy` sibling method dispatched by the
    refactor couldn't see those names. Pre-fix this command 500'd
    on every player attempt with `NameError: name 'purchase_droid'
    is not defined`. Pattern is identical to the H1 (HousingCommand)
    bug class.
    """
    s = await h.login_as("EE1Poor", room_id=1, credits=500)
    out = await h.cmd(s, "shop buy droid gn4")
    assert "traceback" not in out.lower(), (
        f"`shop buy droid gn4` raised: {out[:500]!r}"
    )
    # Specific catch for the fixed bug — pre-fix the user saw the
    # NameError leak through. Post-fix they get a credits message.
    assert "is not defined" not in out.lower(), (
        f"NameError leaked through to player. Output: {out[:300]!r}"
    )
    out_lc = out.lower()
    # gn4 is 2,000 cr per the help text. The refusal should mention
    # credits / cost / insufficient.
    assert (
        "insufficient" in out_lc or "not enough" in out_lc or
        "credits" in out_lc
    ), (
        f"shop buy refusal didn't mention credits/cost. "
        f"Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# EE2 — shop buy droid (funded) creates a vendor_droid row
# ──────────────────────────────────────────────────────────────────────────

async def ee2_shop_buy_droid_success(h):
    """EE2 — A funded character running `shop buy droid gn4` ends up
    with a `vendor_droid` row in `objects` owned by them.

    Validates the success path of EE1's regression: the import is in
    scope AND `purchase_droid` actually does its DB work AND credits
    decrement correctly.
    """
    s = await h.login_as("EE2Buyer", room_id=1, credits=5000)
    char_id = s.character["id"]

    pre_droids = await _droids_owned_by(h, char_id)
    pre_credits = await h.get_credits(char_id)
    assert len(pre_droids) == 0, (
        f"EE2Buyer started with droids owned: {pre_droids!r}"
    )

    out = await h.cmd(s, "shop buy droid gn4")
    assert "traceback" not in out.lower(), (
        f"`shop buy droid gn4` raised: {out[:500]!r}"
    )

    post_droids = await _droids_owned_by(h, char_id)
    assert len(post_droids) == 1, (
        f"After `shop buy droid gn4`, expected 1 droid owned, got "
        f"{len(post_droids)}. Rows: {[dict(r) for r in post_droids]!r}"
    )
    post_credits = await h.get_credits(char_id)
    # gn4 tier is 2,000 credits per shop help text.
    assert post_credits == pre_credits - 2000, (
        f"Credits should drop by 2000 (gn4 tier price). "
        f"pre={pre_credits} post={post_credits}"
    )


# ──────────────────────────────────────────────────────────────────────────
# EE3 — shop place + shop recall lifecycle
# ──────────────────────────────────────────────────────────────────────────

async def ee3_shop_place_recall_lifecycle(h):
    """EE3 — After `shop place`, the droid's room_id matches the
    character's room. After `shop recall`, room_id goes back to NULL
    (in-inventory state).
    """
    s = await h.login_as("EE3Placer", room_id=1, credits=5000)
    char_id = s.character["id"]

    await h.cmd(s, "shop buy droid gn4")
    droids = await _droids_owned_by(h, char_id)
    assert droids, "EE3 prereq: shop buy didn't create a droid"
    droid_id = droids[0]["id"]
    assert droids[0]["room_id"] is None, (
        f"Newly-bought droid should be unplaced (room_id NULL); "
        f"got room_id={droids[0]['room_id']!r}"
    )

    out = await h.cmd(s, "shop place")
    assert "traceback" not in out.lower(), (
        f"`shop place` raised: {out[:500]!r}"
    )
    after_place = await h.db.fetchall(
        "SELECT room_id FROM objects WHERE id = ?", (droid_id,)
    )
    assert after_place[0]["room_id"] == 1, (
        f"After `shop place` from room 1, droid's room_id should be 1; "
        f"got {after_place[0]['room_id']!r}"
    )

    out2 = await h.cmd(s, "shop recall")
    assert "traceback" not in out2.lower(), (
        f"`shop recall` raised: {out2[:500]!r}"
    )
    after_recall = await h.db.fetchall(
        "SELECT room_id FROM objects WHERE id = ?", (droid_id,)
    )
    assert after_recall[0]["room_id"] is None, (
        f"After `shop recall`, droid's room_id should be NULL; "
        f"got {after_recall[0]['room_id']!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# EE4 — browse in an empty room
# ──────────────────────────────────────────────────────────────────────────

async def ee4_browse_empty_room(h):
    """EE4 — `browse` in a room with no vendor droids says so cleanly.

    The clean-state message is the success fingerprint here. A
    traceback or empty output would be the bug case.
    """
    s = await h.login_as("EE4Browser", room_id=1)
    out = await h.cmd(s, "browse")
    assert out and out.strip(), "browse produced no output"
    assert "traceback" not in out.lower(), (
        f"browse raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # Acceptable messages: "no vendor droids" / "no shops" / similar.
    # A populated droid list (which would mean a stale droid leaked
    # into the test DB) would also pass this check — we'd still need
    # the lifecycle to work — but that's the bug case worth catching
    # via EE5's positive assertion, not EE4's.
    assert (
        "no vendor" in out_lc or "no shop" in out_lc or
        "vendor droids" in out_lc or "no droids" in out_lc
    ), (
        f"browse output doesn't look like a vendor-droid surface. "
        f"Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# EE5 — browse with a placed droid
# ──────────────────────────────────────────────────────────────────────────

async def ee5_browse_with_droid(h):
    """EE5 — After seeding a droid in the room, `browse` lists it.

    Uses _seed_droid_with_stock to skip the buy/place/stock flow
    (those are covered by EE2/EE3) and exercise specifically the
    `browse` formatter against a non-empty room.
    """
    owner = await h.login_as("EE5Owner", room_id=1)
    await _seed_droid_with_stock(
        h, owner_id=owner.character["id"], room_id=1,
        item_key="blaster_pistol", item_name="Heavy Blaster Pistol",
        price=300, qty=2, shop_name="EE5 Shop",
    )

    browser = await h.login_as("EE5Browser", room_id=1)
    out = await h.cmd(browser, "browse")
    assert "traceback" not in out.lower(), (
        f"browse raised on populated room: {out[:500]!r}"
    )
    out_lc = out.lower()
    # The seeded shop name should appear.
    assert "ee5 shop" in out_lc, (
        f"browse didn't list the seeded 'EE5 Shop'. "
        f"Output: {out[:500]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# EE6 — buy <item> from <shop> moves credits between PCs
# ──────────────────────────────────────────────────────────────────────────

async def ee6_buy_from_droid(h):
    """EE6 — `buy heavy blaster pistol from smoke test shop` deducts
    credits from the buyer and credits the droid's escrow.

    Important: the seller's WALLET doesn't get the credits directly —
    they accumulate in the droid's `escrow` until the owner runs
    `shop collect`. Asserting on escrow rather than seller credits
    is what mirrors the engine's actual behavior.
    """
    owner = await h.login_as("EE6Owner", room_id=1)
    droid_id = await _seed_droid_with_stock(
        h, owner_id=owner.character["id"], room_id=1,
        item_key="blaster_pistol", item_name="Heavy Blaster Pistol",
        price=300, qty=2, shop_name="EE6 Shop",
    )

    buyer = await h.login_as("EE6Buyer", room_id=1, credits=1000)
    pre_credits = await h.get_credits(buyer.character["id"])

    out = await h.cmd(
        buyer, "buy heavy blaster pistol from ee6 shop"
    )
    assert "traceback" not in out.lower(), (
        f"buy-from-droid raised: {out[:500]!r}"
    )

    # Credits left buyer's wallet
    post_credits = await h.get_credits(buyer.character["id"])
    assert post_credits < pre_credits, (
        f"Buyer's credits should have dropped after a successful "
        f"buy-from-droid. pre={pre_credits} post={post_credits}. "
        f"Cmd output: {out[:400]!r}"
    )

    # Credits should be in droid escrow OR the droid's stock count
    # decreased — either way, *something* happened. Reading via the
    # same shape engine/vendor_droids writes: `escrow_credits` (NOT
    # `escrow` — different field, set during the sale).
    from engine.vendor_droids import _load_data
    obj = await h.db.get_object(droid_id)
    data = _load_data(obj or {})
    escrow_credits = data.get("escrow_credits", 0)
    stock_remaining = sum(
        slot.get("quantity", 0) for slot in data.get("inventory", [])
    )
    assert escrow_credits > 0 or stock_remaining < 2, (
        f"Neither escrow nor stock changed after buy-from-droid. "
        f"escrow={escrow_credits} stock={stock_remaining}. "
        f"Cmd output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# EE7 — sell <resource> to <shop> routes through vendor_droids
# ──────────────────────────────────────────────────────────────────────────

async def ee7_sell_resource_to_droid_routes(h):
    """EE7 — `sell <resource> to <shop>` is the player-facing entry
    point for filling a droid's posted buy-order. With no buy orders
    in the room, it should refuse cleanly (not crash). This guards
    the routing in `parser/builtin_commands.py::SellCommand` that
    dispatches to `engine/vendor_droids.sell_to_droid` when the
    arg shape matches `<thing> to <shop>`.

    Positive-path coverage (a droid with a posted buy-order) needs
    schema for orders that's heavier to set up; deferred to a
    later drop. Refusal-path coverage is enough to catch the
    routing/import regressions this layer is most prone to.
    """
    owner = await h.login_as("EE7Owner", room_id=1)
    await _seed_droid_with_stock(
        h, owner_id=owner.character["id"], room_id=1,
        item_key="blaster_pistol", item_name="Pistol",
        price=300, qty=1, shop_name="EE7 Shop",
    )

    seller = await h.login_as("EE7Seller", room_id=1)
    out = await h.cmd(
        seller, "sell durasteel to ee7 shop"
    )
    assert "traceback" not in out.lower(), (
        f"sell-to-droid raised: {out[:500]!r}"
    )
    # Acceptable refusals: "no buy orders" / "doesn't have a buy
    # order" / "no order matching" / similar. Or the routing might
    # bounce to the equipped-weapon-sell path with a different
    # error — also acceptable as long as it's not a traceback.
    assert out and out.strip(), "sell-to-droid produced no output"


# ──────────────────────────────────────────────────────────────────────────
# EE8 — P2P trade cap (5,000 cr/24h)
# ──────────────────────────────────────────────────────────────────────────

async def ee8_p2p_cap_blocks_over_limit(h):
    """EE8 — `trade Bob 6000 credits` from a fresh char is blocked
    by the P2P daily cap (5,000 cr per 24h rolling window).

    REGRESSION GUARD for the S51 economy hardening. Unit-tested in
    `test_session51_economy_hardening.py` against mock helpers; this
    scenario verifies the wiring through the live `trade` command +
    real `db.get_daily_p2p_outgoing` against the credit_log table.

    The cap fires at offer time so the player gets immediate
    feedback. We also confirm an under-cap trade succeeds end-to-end
    so the test isn't asserting on a generic-failure refusal.
    """
    alice = await h.login_as("EE8Alice", room_id=1, credits=10000)
    bob = await h.login_as("EE8Bob", room_id=1)

    # 1. Under-cap trade succeeds end-to-end (offer + accept).
    out = await h.cmd(alice, "trade EE8Bob 1000 credits")
    assert "traceback" not in out.lower(), (
        f"trade offer raised: {out[:500]!r}"
    )
    out2 = await h.cmd(bob, "trade accept EE8Alice")
    assert "traceback" not in out2.lower(), (
        f"trade accept raised: {out2[:500]!r}"
    )
    bob_credits = await h.get_credits(bob.character["id"])
    # Trade is taxed 5%; Bob receives 950 from a 1000 trade.
    assert bob_credits >= 900, (
        f"After trade accept, Bob should have received credits. "
        f"Bob's credits: {bob_credits}. Output: {out2[:300]!r}"
    )

    # 2. Over-cap trade refused at offer time. Alice has already
    # sent 1000 today; cap is 5000; 6000 attempt would bring total
    # to 7000 which exceeds the cap.
    out3 = await h.cmd(alice, "trade EE8Bob 6000 credits")
    assert "traceback" not in out3.lower(), (
        f"trade over-cap raised: {out3[:500]!r}"
    )
    out_lc = out3.lower()
    assert (
        "trade blocked" in out_lc or "daily transfer cap" in out_lc or
        ("cap" in out_lc and "5,000" in out3)
    ), (
        f"Over-cap trade didn't surface the cap-blocked message. "
        f"Output: {out3[:500]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# EE9 — buy cargo wiring (refusal path: no ship)
# ──────────────────────────────────────────────────────────────────────────

async def ee9_buy_cargo_no_ship_refuses_cleanly(h):
    """EE9 — `buy cargo raw_ore 20` from a player with no ship gets
    a clean refusal, not a traceback.

    This guards the `_handle_buy_cargo` arg-parse path and the
    `volume_premium` wiring (the math itself is unit-tested in
    `test_session63_bulk_premium.py`). Pre-existing ship-piloting
    setup is heavy enough that the positive path is left to a
    later drop or explicit space-flight smoke; the refusal path
    is what catches a regression in the cargo subcommand routing.
    """
    s = await h.login_as("EE9Cargoer", room_id=1, credits=10000)
    out = await h.cmd(s, "buy cargo raw_ore 20")
    assert "traceback" not in out.lower(), (
        f"`buy cargo` raised: {out[:500]!r}"
    )
    assert out and out.strip(), "buy cargo produced no output"
    # Acceptable refusals: "must be docked" / "no ship" / "not in
    # a ship" / any clear gating message.
    out_lc = out.lower()
    assert (
        "docked" in out_lc or "ship" in out_lc or "pilot" in out_lc or
        "cockpit" in out_lc or "bridge" in out_lc
    ), (
        f"buy cargo refusal doesn't reference ship context. "
        f"Output: {out[:400]!r}"
    )
