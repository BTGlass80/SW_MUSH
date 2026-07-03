# -*- coding: utf-8 -*-
"""
tests/test_housing_teardown_completeness_2026_07_03.py — housing-teardown-
completeness drop (2026-07-03): two proven, player-reachable bugs found by a
break-it pass on the 2026-07-02 housing-hardening drop's occupancy fix.

  Bug 1 [engine.housing.checkout_room]: the lot-occupancy decrement added by
    the 2026-07-02 drop only fired for ``housing_type == "rented_room"``.
    The OTHER two callers of ``checkout_room(force=True)`` on an owned
    Tier-3 home -- ``@housing evict`` and ``tick_housing_rent``'s
    rent-default foreclosure -- call ``checkout_room`` directly (never
    through ``sell_home``), so they tore the home down but never freed the
    lot: a permanent lot-slot leak. FIX: the decrement now fires in
    ``checkout_room`` for every lot-occupying housing type it tears down
    (gated only on whether ``get_lot_by_room`` finds a backing lot row --
    ``faction_quarters`` has none, so it's naturally a no-op there). The
    duplicate decrement ``sell_home`` added on 2026-07-02 (which ran AFTER
    its own ``checkout_room(force=True)`` call) has been REMOVED so nothing
    double-decrements.

  Bug 2 [engine.housing.sell_shopfront]: resolved its target via
    ``get_housing(db, char_id)`` ("most recent home by id DESC") instead of
    ``resolve_active_home(db, char)`` (the home the player is physically
    standing in) -- but the confirmation prompt one line earlier
    (``_cmd_sell`` in parser/housing_commands.py) used
    ``resolve_active_home`` to show the price. A 2-shopfront owner
    (MAX_TIER4_PER_CHAR=2, different planets) standing in shop A, seeing
    A's price, and confirming would have shop B destroyed instead. FIX:
    ``sell_shopfront`` now resolves via ``resolve_active_home``, exactly
    like ``sell_home`` already does.

Run: python -m pytest tests/test_housing_teardown_completeness_2026_07_03.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import housing  # noqa: E402


class _NoSessions:
    """Minimal session_mgr for tick_housing_rent -- no live sessions, so the
    player-notify send_line path is skipped."""

    def find_by_character(self, char_id):
        return None


async def _make_lot(harness, *, planet="tatooine", label="Test Lot",
                     security="contested", max_homes=5):
    """Create a lobby room + an ad hoc housing_lots row. Mirrors the pattern
    used across the existing housing test files."""
    room_id = await harness.db.create_room(
        name=label, desc_short="A test housing lobby.",
        desc_long="A test housing lobby.", zone_id=None,
        properties=json.dumps({"security": security}),
    )
    cur = await harness.db.execute(
        """INSERT INTO housing_lots
           (room_id, planet, label, security, max_homes, current_homes)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (room_id, planet, label, security, max_homes),
    )
    await harness.db.commit()
    return cur.lastrowid, room_id


async def _reload_char(harness, char_id):
    rows = await harness.db.fetchall(
        "SELECT * FROM characters WHERE id = ?", (char_id,)
    )
    return dict(rows[0])


async def _current_homes(harness, lot_id):
    rows = await harness.db.fetchall(
        "SELECT current_homes FROM housing_lots WHERE id = ?", (lot_id,))
    return rows[0]["current_homes"]


async def _build_shopfront(harness, cid, *, label_prefix):
    """Construct a Tier-4 shopfront record + rooms directly (bypasses the
    tier4-provider lot gate), mirroring the pattern in
    tests/test_qa_housing_credit_integrity_2026_06_21.py."""
    lot_room = await harness.db.create_room(
        name=f"{label_prefix} Lobby", desc_short="street", desc_long="street",
        zone_id=None, properties="{}")
    shop_room = await harness.db.create_room(
        name=f"{label_prefix} Shop", desc_short="shop", desc_long="shop",
        zone_id=None, properties=json.dumps({"is_shopfront": True}))
    priv_room = await harness.db.create_room(
        name=f"{label_prefix} Private", desc_short="back", desc_long="back",
        zone_id=None, properties=json.dumps({"private": True}))
    ein = await harness.db.create_exit(lot_room, shop_room, "northwest", "Shop")
    eout = await harness.db.create_exit(shop_room, lot_room, "out", "Street")
    await harness.db.create_exit(shop_room, priv_room, "northwest", "Private")
    await harness.db.create_exit(priv_room, shop_room, "out", "Shop")

    room_ids = [shop_room, priv_room]
    cur = await harness.db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids,
            purchase_price, door_direction, exit_id_in, exit_id_out,
            created_at)
           VALUES (?, 4, 'shopfront', ?, ?, ?, 'northwest', ?, ?, ?)""",
        (cid, lot_room, json.dumps(room_ids), 14000, ein, eout, time.time()),
    )
    hid = cur.lastrowid
    for rid in room_ids:
        await harness.db.execute(
            "UPDATE rooms SET housing_id = ? WHERE id = ?", (hid, rid))
    await harness.db.commit()
    return hid, lot_room, room_ids, shop_room


# ── Bug 1: checkout_room's lot decrement covers ALL its teardown callers ──

class TestBug1CheckoutRoomCentralizedDecrement:
    async def test_evict_frees_the_lot_slot(self, harness):
        """@housing evict tears an owned Tier-3 home down via
        checkout_room(force=True) -- it must free the lot too."""
        lot_id, _ = await _make_lot(harness, label="EvictLot", max_homes=5)
        # A second owner on the SAME lot keeps current_homes at 2 so a
        # "went to 1" assertion proves exactly one decrement fired (not
        # zero, and not two clamped to 0 -- see MAX(0, ...) guard).
        s_other = await harness.login_as("EvictOtherOwner", credits=200_000)
        other = dict(s_other.character)
        buy_other = await housing.purchase_home(harness.db, other, lot_id, "small")
        assert buy_other["ok"], buy_other

        s = await harness.login_as("EvictTarget", credits=200_000)
        char = dict(s.character)
        buy = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert buy["ok"], buy
        assert await _current_homes(harness, lot_id) == 2

        target = await _reload_char(harness, char["id"])
        # Mirrors parser/housing_commands.py AdminHousingCommand's evict
        # sub-command: checkout_room(ctx.db, target, force=True).
        result = await housing.checkout_room(harness.db, target, force=True)
        assert result["ok"] is True, result

        assert await _current_homes(harness, lot_id) == 1, (
            "evict must decrement current_homes exactly once "
            "(pre-fix: stayed at 2 -- the lot slot leaked forever)"
        )
        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?", (char["id"],))
        assert rows == [], "evict must still tear the home down"

    async def test_rent_default_foreclosure_frees_the_lot_slot(self, harness):
        """tick_housing_rent's rent-default foreclosure tears an owned
        Tier-3 home down via checkout_room(force=True) -- it must free the
        lot too."""
        lot_id, _ = await _make_lot(harness, label="ForecloseLot", max_homes=5)
        s_other = await harness.login_as("ForecloseOtherOwner", credits=200_000)
        other = dict(s_other.character)
        buy_other = await housing.purchase_home(harness.db, other, lot_id, "small")
        assert buy_other["ok"], buy_other

        s = await harness.login_as("ForecloseTarget", credits=200_000)
        char = dict(s.character)
        buy = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert buy["ok"], buy
        assert await _current_homes(harness, lot_id) == 2

        housing_id = buy["housing_id"]
        # Drive the character broke and the rent clock overdue for
        # TIER1_EVICT_WEEKS - 1 weeks, then let ONE tick push it over the
        # eviction threshold (mirrors the _force_rent_due recipe in
        # tests/test_t319_housing_telemetry.py).
        await harness.db.execute(
            "UPDATE characters SET credits = 0 WHERE id = ?", (char["id"],))
        await harness.db.execute(
            "UPDATE player_housing SET rent_paid_until = 0, rent_overdue = ? "
            "WHERE id = ?",
            (housing.TIER1_EVICT_WEEKS - 1, housing_id),
        )
        await harness.db.commit()

        await housing.tick_housing_rent(harness.db, _NoSessions())

        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE id = ?", (housing_id,))
        assert rows == [], "rent-default foreclosure must tear the home down"
        assert await _current_homes(harness, lot_id) == 1, (
            "rent-default foreclosure must decrement current_homes exactly "
            "once (pre-fix: stayed at 2 -- the lot slot leaked forever)"
        )

    async def test_sell_home_decrements_exactly_once(self, harness):
        """sell_home routes its teardown through checkout_room(force=True),
        which now owns the decrement -- sell_home's own (now-removed)
        decrement must NOT also fire, or a sold home double-decrements."""
        lot_id, _ = await _make_lot(harness, label="SellOnceLot", max_homes=5)
        s_other = await harness.login_as("SellOnceOtherOwner", credits=200_000)
        other = dict(s_other.character)
        buy_other = await housing.purchase_home(harness.db, other, lot_id, "small")
        assert buy_other["ok"], buy_other

        s = await harness.login_as("SellOnceTarget", credits=200_000)
        char = dict(s.character)
        buy = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert buy["ok"], buy
        assert await _current_homes(harness, lot_id) == 2

        char2 = await _reload_char(harness, char["id"])
        sell = await housing.sell_home(harness.db, char2)
        assert sell["ok"], sell

        assert await _current_homes(harness, lot_id) == 1, (
            "sell_home must decrement current_homes EXACTLY ONCE; a stray "
            "double-decrement would leave it at 0 (clamped) instead of 1"
        )

    async def test_rented_room_checkout_still_decrements_once(self, harness):
        """No regression: a plain (non-force) rented_room checkout must
        still free exactly one slot, same as before this drop."""
        lot_id, _ = await _make_lot(harness, label="RentedCheckoutLot", max_homes=5)
        s_other = await harness.login_as("RentedOtherTenant", credits=5_000)
        other = dict(s_other.character)
        rent_other = await housing.rent_room(harness.db, other, lot_id)
        assert rent_other["ok"], rent_other

        s = await harness.login_as("RentedCheckoutTenant", credits=5_000)
        char = dict(s.character)
        rent = await housing.rent_room(harness.db, char, lot_id)
        assert rent["ok"], rent
        assert await _current_homes(harness, lot_id) == 2

        char2 = await _reload_char(harness, char["id"])
        result = await housing.checkout_room(harness.db, char2)
        assert result["ok"] is True, result

        assert await _current_homes(harness, lot_id) == 1, (
            "rented_room checkout must keep decrementing exactly once"
        )


# ── Bug 2: sell_shopfront must resolve the shop the player stood in ───────

class TestBug2SellShopfrontResolvesActiveHome:
    async def test_sells_the_shop_stood_in_not_the_most_recent(self, harness):
        s = await harness.login_as("TwoShopOwner", credits=100)
        cid = s.character["id"]

        # Shop A built FIRST (lower id -- NOT the "most recent").
        hid_a, lot_a, rooms_a, shop_room_a = await _build_shopfront(
            harness, cid, label_prefix="ShopA-Tatooine")
        # Shop B built SECOND (higher id -- get_housing()'s "most recent").
        hid_b, lot_b, rooms_b, shop_room_b = await _build_shopfront(
            harness, cid, label_prefix="ShopB-Coruscant")

        # "Teleport" the player into Shop A's public shop room -- the home
        # resolve_active_home must pick, and the one the confirmation
        # prompt in _cmd_sell would have quoted a price for.
        await harness.db.save_character(cid, room_id=shop_room_a)
        char = await _reload_char(harness, cid)
        assert char["room_id"] == shop_room_a

        result = await housing.sell_shopfront(harness.db, char)
        assert result["ok"] is True, result

        rows_a = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE id = ?", (hid_a,))
        rows_b = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE id = ?", (hid_b,))
        assert rows_a == [], (
            "the shop the player stood in (A) must be the one destroyed "
            "(pre-fix: get_housing() picked the most-recent shop (B) "
            "regardless of where the player stood)"
        )
        assert rows_b != [], "the OTHER shop (B) must survive untouched"

        for rid in rooms_a:
            assert await harness.db.get_room(rid) is None, (
                f"Shop A room {rid} must be deleted"
            )
        for rid in rooms_b:
            assert await harness.db.get_room(rid) is not None, (
                f"Shop B room {rid} must survive"
            )
