# -*- coding: utf-8 -*-
"""
tests/test_qa_housing_credit_integrity_2026_06_21.py — QA break-it sweep #3
(2026-06-21): the credit-integrity bug class found in shops/crafting on
2026-06-20 also lived in ``engine/housing.py``, plus a sell_shopfront
double-accounting CRASH.

Three blockers + one high, all confirmed in-harness by the break-it campaign:

  * ``rent_room`` / ``purchase_home`` / ``purchase_shopfront`` checked the
    STALE session-cache balance, then created the rooms+exits BEFORE the
    debit, and debited with no ``allow_negative=False``. A live DB drain
    between session-load and the call drove the true balance negative
    (-549 / -4999 / -14999 observed) while the home was still created.
    Fix: debit FIRST against the live DB with ``allow_negative=False``;
    on ``None`` (over-draw refused) abort with no rooms created.

  * ``sell_shopfront`` used the wrong exit columns
    (``from_room`` / ``to_room`` — the real columns are
    ``from_room_id`` / ``to_room_id``). The ``OperationalError`` was
    swallowed by ``except: pass``, the rooms survived, and the *unwrapped*
    ``DELETE FROM player_housing`` then crashed on the FK — AFTER the 50%
    refund had already been paid. Net: the player kept BOTH the refund and
    the property. Fix: structural teardown via the canonical
    ``delete_room`` (correct columns, cascades exits), refund applied LAST
    so a mid-teardown failure can't double-pay.

Behavioral coverage drives the live engine for the two trickiest blockers
(rent_room negative-balance prevention; sell_shopfront round-trip with a
single refund). The two deep buy paths (purchase_home / purchase_shopfront,
which sit behind rep-gate / tier4-provider lots) plus the crafting
buyresources sibling are pinned with structural source guards.

Run: python -m pytest tests/test_qa_housing_credit_integrity_2026_06_21.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import housing  # noqa: E402


async def _make_lot(harness, *, planet="tatooine", label="Test Lot",
                    security="contested", max_homes=5):
    """Create a lobby room + a housing_lots row, return (lot_id, room_id)."""
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


# ── rent_room: the most common housing action, a confirmed blocker ────────────
class TestRentRoomCreditIntegrity:

    async def test_overdraw_is_refused_no_negative_no_orphan(self, harness):
        """Cache says affordable, the live DB can't cover it → the rent is
        refused atomically: balance stays put (never negative) and NO room is
        created."""
        lot_id, _ = await _make_lot(harness, label="RentRefuse Lot")
        s = await harness.login_as("RentRefuse", credits=5000)
        cid = s.character["id"]

        # Drain the DB balance out from under the cached 5000.
        await harness.db.execute(
            "UPDATE characters SET credits = 1 WHERE id = ?", (cid,))
        await harness.db.commit()

        before = await harness.get_credits(cid)
        char = dict(s.character)          # carries the STALE cached 5000
        result = await housing.rent_room(harness.db, char, lot_id)

        assert result["ok"] is False, "overdrawn rent must be refused"
        after = await harness.get_credits(cid)
        assert after == before == 1, (
            f"refused rent must not move credits (got {before} -> {after}); "
            f"the pre-fix bug drove it to -549")
        assert after >= 0, "balance must never be driven negative"
        # No orphan housing record created for the refused rent.
        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?", (cid,))
        assert not rows, "a refused rent must not create a housing record"

    async def test_happy_path_debits_exactly(self, harness):
        """With real funds the rent succeeds and debits exactly
        deposit + first week."""
        lot_id, _ = await _make_lot(harness, label="RentOK Lot")
        s = await harness.login_as("RentOK", credits=5000)
        cid = s.character["id"]
        cost = housing.TIER1_DEPOSIT + housing.TIER1_WEEKLY_RENT

        char = dict(s.character)
        result = await housing.rent_room(harness.db, char, lot_id)
        assert result["ok"] is True, result.get("msg")
        after = await harness.get_credits(cid)
        assert after == 5000 - cost, f"expected {5000 - cost}, got {after}"


# ── sell_shopfront: the crash + double-accounting blocker ─────────────────────
class TestSellShopfrontTeardown:

    async def _build_shopfront(self, harness, cid, *, purchase_price=14000):
        """Construct a Tier-4 shopfront record + rooms directly (bypasses the
        tier4-provider lot gate), mirroring purchase_shopfront's structure."""
        lot_room = await harness.db.create_room(
            name="SF Lobby", desc_short="street", desc_long="street",
            zone_id=None, properties="{}")
        shop_room = await harness.db.create_room(
            name="SF Shop", desc_short="shop", desc_long="shop",
            zone_id=None, properties=json.dumps({"is_shopfront": True}))
        priv_room = await harness.db.create_room(
            name="SF Private", desc_short="back", desc_long="back",
            zone_id=None, properties=json.dumps({"private": True}))
        # Exits both ways, exactly as purchase_shopfront wires them.
        ein = await harness.db.create_exit(lot_room, shop_room, "northwest", "Shop")
        eout = await harness.db.create_exit(shop_room, lot_room, "out", "Street")
        await harness.db.create_exit(shop_room, priv_room, "northwest", "Private")
        await harness.db.create_exit(priv_room, shop_room, "out", "Shop")

        room_ids = [shop_room, priv_room]
        import time as _t
        cur = await harness.db.execute(
            """INSERT INTO player_housing
               (char_id, tier, housing_type, entry_room_id, room_ids,
                purchase_price, door_direction, exit_id_in, exit_id_out,
                created_at)
               VALUES (?, 4, 'shopfront', ?, ?, ?, 'northwest', ?, ?, ?)""",
            (cid, lot_room, json.dumps(room_ids), purchase_price,
             ein, eout, _t.time()),
        )
        hid = cur.lastrowid
        for rid in room_ids:
            await harness.db.execute(
                "UPDATE rooms SET housing_id = ? WHERE id = ?", (hid, rid))
        await harness.db.commit()
        return hid, lot_room, room_ids

    async def test_roundtrip_no_crash_single_refund(self, harness):
        """sell_shopfront must NOT raise (the FK crash), must refund exactly
        once, and must actually delete the rooms + housing record."""
        s = await harness.login_as("SellSF", credits=100)
        cid = s.character["id"]
        hid, lot_room, room_ids = await self._build_shopfront(
            harness, cid, purchase_price=14000)

        char = dict(s.character)
        # Must not raise — the pre-fix wrong-column DELETE crashed here.
        result = await housing.sell_shopfront(harness.db, char)
        assert result["ok"] is True, result.get("msg")

        # Refund applied exactly ONCE (50% of 14000 = 7000).
        after = await harness.get_credits(cid)
        assert after == 100 + 7000, (
            f"expected single 7000cr refund (107 -> 7100), got {after}")

        # Property is actually gone (no double-keep).
        hrows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE id = ?", (hid,))
        assert not hrows, "housing record must be deleted on sale"
        for rid in room_ids:
            assert await harness.db.get_room(rid) is None, (
                f"shopfront room {rid} must be deleted on sale")

        # Exactly one refund ledger entry (no double-accounting in the log).
        led = await harness.db.fetchall(
            "SELECT COUNT(*) AS n FROM credit_log "
            "WHERE char_id = ? AND source = 'shopfront_refund'", (cid,))
        assert led[0]["n"] == 1, "exactly one shopfront_refund ledger row"


# ── Structural guards: every housing credit site debits-first, refund-last ────
def _func_body(src, name):
    """Slice an ``async def <name>`` body up to the next top-level def."""
    m = re.search(rf"\nasync def {re.escape(name)}\b", src)
    assert m, f"function {name} not found"
    start = m.start()
    nxt = re.search(r"\nasync def ", src[start + 1:])
    end = start + 1 + nxt.start() if nxt else len(src)
    return src[start:end]


class TestHousingCreditSiteGuards:
    @classmethod
    def setup_class(cls):
        cls.src = (PROJECT_ROOT / "engine" / "housing.py").read_text(
            encoding="utf-8")

    @pytest.mark.parametrize("fn,tag", [
        ("purchase_home", "housing_upgrade"),
        ("purchase_shopfront", "shopfront_purchase"),
        ("rent_room", "housing_purchase"),
    ])
    def test_debit_uses_allow_negative_false(self, fn, tag):
        body = _func_body(self.src, fn)
        assert "allow_negative=False" in body, (
            f"{fn} must debit with allow_negative=False")
        assert "is None:" in body, f"{fn} must abort on the None over-draw"

    @pytest.mark.parametrize("fn", ["purchase_home", "purchase_shopfront",
                                    "rent_room"])
    def test_debit_precedes_room_creation(self, fn):
        """The debit must run BEFORE create_room, so a refused over-draw never
        leaves orphan rooms behind."""
        body = _func_body(self.src, fn)
        debit = body.find("allow_negative=False")
        first_room = body.find("create_room(")
        assert debit != -1 and first_room != -1
        assert debit < first_room, (
            f"{fn}: the credit debit must precede the first create_room")

    def test_sell_shopfront_wrong_columns_are_gone(self):
        body = _func_body(self.src, "sell_shopfront")
        assert "from_room = ?" not in body and "to_room = ?" not in body, (
            "sell_shopfront must not use the non-existent from_room/to_room "
            "columns — the real columns are from_room_id/to_room_id")
        assert "delete_room(" in body, (
            "sell_shopfront must tear rooms down via the canonical delete_room")

    def test_sell_shopfront_refund_is_last(self):
        """The refund must come AFTER the room teardown, so a mid-teardown
        crash can't pay the refund and keep the property."""
        body = _func_body(self.src, "sell_shopfront")
        last_delete = body.rfind("delete_room(")
        refund = body.find("shopfront_refund")
        assert last_delete != -1 and refund != -1
        assert refund > last_delete, (
            "sell_shopfront must apply the refund AFTER deleting the rooms")


class TestCraftingBuyResourcesIntegrity:
    def test_buyresources_uses_allow_negative_false(self):
        src = (PROJECT_ROOT / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8")
        assert "resource_vendor" in src
        # The resource_vendor debit must carry the guard within its call.
        idx = src.find('"resource_vendor"')
        window = src[max(0, idx - 200): idx + 200]
        assert "allow_negative=False" in window, (
            "BuyResourcesCommand resource_vendor debit must use "
            "allow_negative=False (QA 2026-06-21 credit-integrity)")
