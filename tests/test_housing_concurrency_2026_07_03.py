# -*- coding: utf-8 -*-
"""
tests/test_housing_concurrency_2026_07_03.py — housing-concurrency-locks
drop (2026-07-03): two proven check-then-act races, the same class the
vendor-droid fix (engine/vendor_droids.py ``_droid_locks`` /
``_get_droid_lock``) already closed for the player-vendor marketplace.

  Bug 3 [engine.housing.sell_home / checkout_room]: ``sell_home`` reads the
    active home (``resolve_active_home``), then calls ``checkout_room``,
    which itself reads the home again, awaits an item return + deposit
    refund + several room/table deletes, and only THEN deletes the
    ``player_housing`` row -- with no lock anywhere in that span. Two
    concurrent ``sell_home`` calls for the SAME character both pass the
    "you own a home" check before either DELETE lands, so both run the full
    sale and the 50%-of-purchase-price refund is minted twice for one home.
    FIX: a per-CHARACTER ``asyncio.Lock`` (``_get_home_txn_lock``) now wraps
    ``checkout_room``'s critical section (its own ``resolve_active_home``
    read through the ``DELETE FROM player_housing``). Because ``checkout_room``
    is the single chokepoint every teardown path routes through (sell_home,
    player-facing checkout, ``@housing evict``, rent-default foreclosure),
    locking it there closes the race for all of them: a second concurrent
    call re-reads the POST-delete state (no housing found) once it acquires
    the lock, and ``sell_home``'s ``if not result["ok"]: return result``
    refuses it before it ever reaches the refund credit.

  Bug 4 [engine.housing.purchase_home / rent_room / purchase_shopfront /
    purchase_hq]: each checks ``lot["current_homes"] >= lot["max_homes"]``
    and, many awaits later (credit debit, room/exit creation, INSERT),
    increments ``housing_lots.current_homes`` -- two unguarded statements
    with a wide window between them. Two players racing the last slot on
    the SAME lot both pass the stale check and the lot oversells
    (``current_homes`` ends up > ``max_homes``). FIX: a per-LOT
    ``asyncio.Lock`` (``_get_lot_lock``) now wraps the whole
    check-through-increment span in all four purchase/rent paths.

Both locks are keyed (per-character / per-lot), so unrelated characters and
unrelated lots never contend -- pinned by
``TestIndependentLotsAndCharsDoNotSerialize`` below.

Run: python -m pytest tests/test_housing_concurrency_2026_07_03.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import housing  # noqa: E402


async def _make_lot(harness, *, planet="tatooine", label="Test Lot",
                     security="contested", max_homes=5):
    """Create a lobby room + an ad hoc housing_lots row. Mirrors the pattern
    used across the existing housing test files (e.g.
    tests/test_housing_teardown_completeness_2026_07_03.py)."""
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


async def _current_homes(harness, lot_id):
    rows = await harness.db.fetchall(
        "SELECT current_homes FROM housing_lots WHERE id = ?", (lot_id,))
    return rows[0]["current_homes"]


# ── Bug 3: concurrent `housing sell` must mint exactly one refund ─────────

class TestSellHomeConcurrency:
    async def test_two_concurrent_sells_pay_refund_exactly_once(self, harness):
        lot_id, _ = await _make_lot(harness, label="SellRaceLot", max_homes=5)
        s = await harness.login_as("SellRaceOwner", credits=200_000)
        char = dict(s.character)
        buy = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert buy["ok"], buy
        pre_credits = await harness.get_credits(char["id"])

        # Two independent char-dict snapshots of the SAME character --
        # simulating two concurrent requests for one player, mirroring the
        # vendor-droid collect_escrow concurrency pin
        # (tests/test_vendor_droid_concurrency_2026_07_02.py).
        char_a = await harness.get_char(char["id"])
        char_b = await harness.get_char(char["id"])

        result_a, result_b = await asyncio.gather(
            housing.sell_home(harness.db, char_a),
            housing.sell_home(harness.db, char_b),
        )

        oks = [result_a["ok"], result_b["ok"]]
        assert sum(oks) == 1, (
            f"Exactly one sell_home call must succeed (double refund "
            f"otherwise): A={result_a!r} B={result_b!r}"
        )
        # The loser is refused cleanly (no traceback, no silent second sale).
        loser = result_b if oks[0] else result_a
        assert loser["ok"] is False

        # The 50%-of-5000cr purchase-price refund (2500cr) is paid EXACTLY
        # once -- the pre-fix bug minted it twice.
        final_credits = await harness.get_credits(char["id"])
        assert final_credits == pre_credits + 2500, (
            f"Refund must be paid exactly once (2500cr); got delta "
            f"{final_credits - pre_credits} (pre={pre_credits}, "
            f"final={final_credits})"
        )

        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?", (char["id"],))
        assert rows == [], "the home must be torn down exactly once"

        assert await _current_homes(harness, lot_id) == 0, (
            "lot slot must be freed exactly once, not double-decremented"
        )


# ── Bug 4: concurrent `housing buy` must not oversell a 1-slot lot ────────

class TestPurchaseHomeLotConcurrency:
    async def test_two_buyers_race_the_last_slot_exactly_one_wins(self, harness):
        lot_id, _ = await _make_lot(harness, label="OneSlotLot", max_homes=1)
        s_a = await harness.login_as("LotRaceBuyerA", credits=200_000)
        s_b = await harness.login_as("LotRaceBuyerB", credits=200_000)
        char_a = dict(s_a.character)
        char_b = dict(s_b.character)

        result_a, result_b = await asyncio.gather(
            housing.purchase_home(harness.db, char_a, lot_id, "small"),
            housing.purchase_home(harness.db, char_b, lot_id, "small"),
        )

        oks = [result_a["ok"], result_b["ok"]]
        assert sum(oks) == 1, (
            f"Exactly one buyer must win the 1-slot lot race (oversell "
            f"otherwise): A={result_a!r} B={result_b!r}"
        )

        assert await _current_homes(harness, lot_id) == 1, (
            "current_homes must never exceed max_homes=1"
        )

        rows = await harness.db.fetchall(
            "SELECT COUNT(*) AS cnt FROM player_housing WHERE tier = 3 "
            "AND char_id IN (?, ?)",
            (char_a["id"], char_b["id"]),
        )
        assert rows[0]["cnt"] == 1, (
            "exactly one player_housing row must exist for this race"
        )

        # The loser was refused BEFORE the credit debit (the lock guards the
        # capacity check itself), so their balance is untouched.
        winner_id = char_a["id"] if oks[0] else char_b["id"]
        loser_id = char_b["id"] if oks[0] else char_a["id"]
        assert await harness.get_credits(winner_id) == 200_000 - 5_000
        assert await harness.get_credits(loser_id) == 200_000


# ── Independence pin: unrelated lots / unrelated chars never serialize ────

class TestIndependentLotsAndCharsDoNotSerialize:
    async def test_two_buys_on_two_different_lots_both_succeed(self, harness):
        lot_x, _ = await _make_lot(harness, label="IndepLotX", max_homes=1)
        lot_y, _ = await _make_lot(harness, label="IndepLotY", max_homes=1)
        s_a = await harness.login_as("IndepBuyerA", credits=200_000)
        s_b = await harness.login_as("IndepBuyerB", credits=200_000)
        char_a = dict(s_a.character)
        char_b = dict(s_b.character)

        result_a, result_b = await asyncio.gather(
            housing.purchase_home(harness.db, char_a, lot_x, "small"),
            housing.purchase_home(harness.db, char_b, lot_y, "small"),
        )

        assert result_a["ok"] is True, result_a
        assert result_b["ok"] is True, result_b
        assert await _current_homes(harness, lot_x) == 1
        assert await _current_homes(harness, lot_y) == 1

    async def test_two_different_chars_selling_their_own_homes_both_succeed(
        self, harness,
    ):
        lot_id, _ = await _make_lot(harness, label="IndepSellLot", max_homes=5)
        s_a = await harness.login_as("IndepSellerA", credits=200_000)
        s_b = await harness.login_as("IndepSellerB", credits=200_000)
        char_a = dict(s_a.character)
        char_b = dict(s_b.character)

        buy_a = await housing.purchase_home(harness.db, char_a, lot_id, "small")
        buy_b = await housing.purchase_home(harness.db, char_b, lot_id, "small")
        assert buy_a["ok"], buy_a
        assert buy_b["ok"], buy_b

        reload_a = await harness.get_char(char_a["id"])
        reload_b = await harness.get_char(char_b["id"])

        sell_a, sell_b = await asyncio.gather(
            housing.sell_home(harness.db, reload_a),
            housing.sell_home(harness.db, reload_b),
        )

        assert sell_a["ok"] is True, sell_a
        assert sell_b["ok"] is True, sell_b
        assert await _current_homes(harness, lot_id) == 0
