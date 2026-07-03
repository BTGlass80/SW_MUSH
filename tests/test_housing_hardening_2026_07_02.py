# -*- coding: utf-8 -*-
"""
tests/test_housing_hardening_2026_07_02.py — housing-engine-hardening drop
(2026-07-02): three precisely-located bugs found by the parallel session
that closed out housing.

  Bug 1 [engine.housing.sell_home]: missing the `housing_lots.current_homes`
    decrement its siblings (sell_shopfront / sell_hq) both do -- every sold
    Tier-3 home permanently consumed a lot slot.

  Bug 2 [engine.housing.checkout_room]: treated an owned `private_residence`
    like a rental, refunding the always-0 `deposit` field and destroying the
    home for nothing. RESOLVED FIX: checkout is for RENTALS only; an owned
    home must go through `housing sell` (real 50%-of-purchase-price refund).
    `checkout_room(..., force=True)` still lets the internal repossession
    paths (sell_home's own teardown, rent-default foreclosure, @housing
    evict) tear an owned home down.

  Bug 3 [engine.housing.rent_room]: carried the pre-multi-home hard
    single-home block ("already have a place to stay... checkout first"),
    which (pre-Bug-2-fix) funneled a rental attempt into the 0cr destruction
    path. Fixed to respect the same MAX_TIER3_TOTAL total-home cap
    purchase_home already uses.

  Bug 4 [engine.housing: rent_room / purchase_home / purchase_hq]: a
    cross-tier lot-ID validation gap -- housing_lots is one flat table
    shared by every tier (no type column), and only purchase_shopfront
    checked the lot's room_id against its own tier's provider corpus.
    rent_room / purchase_home / purchase_hq accepted ANY lot_id, including
    one that belongs to a different tier. Fixed with an exclusion-based
    check (reject only a room_id AFFIRMATIVELY known to belong to a
    *different* tier) so ad hoc/test-fabricated lots that aren't in any
    era's provider corpus are unaffected.

  Bug 5 [engine.housing.get_tier3_listing_lines]: a stale
    "(-50% rent)" / "(-25% rent)" display string for lawless/contested
    Tier-3 lots. purchase_home has never applied any security-based
    discount to weekly_rent (unlike Tier 4's real
    `_TIER4_SECURITY_DISCOUNT`) -- the claim was never backed by a real
    mechanic. Removed.

Run: python -m pytest tests/test_housing_hardening_2026_07_02.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import housing  # noqa: E402

HOUSING_SRC = (PROJECT_ROOT / "engine" / "housing.py").read_text(encoding="utf-8")


async def _make_lot(harness, *, planet="tatooine", label="Test Lot",
                     security="contested", max_homes=5):
    """Create a lobby room + an ad hoc housing_lots row (NOT registered in
    any era's provider corpus), return (lot_id, room_id). Mirrors the
    pattern used across the existing housing test files."""
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


async def _lot_id_for_room(harness, room_id):
    """Resolve the housing_lots PK for a room_id already seeded by
    engine.housing.seed_lots() at harness boot."""
    rows = await harness.db.fetchall(
        "SELECT id FROM housing_lots WHERE room_id = ?", (room_id,)
    )
    assert rows, f"seed_lots must have created a housing_lots row for room {room_id}"
    return rows[0]["id"]


async def _reload_char(harness, char_id):
    rows = await harness.db.fetchall(
        "SELECT * FROM characters WHERE id = ?", (char_id,)
    )
    return dict(rows[0])


# ── Bug 1: sell_home must free the lot slot ────────────────────────────────

class TestBug1SellHomeFreesLotSlot:
    async def test_sold_home_decrements_current_homes(self, harness):
        lot_id, _ = await _make_lot(harness, label="SellLot")
        s = await harness.login_as("SellerHome", credits=200_000)
        char = dict(s.character)

        buy = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert buy["ok"], buy
        occupied = await harness.db.fetchall(
            "SELECT current_homes FROM housing_lots WHERE id = ?", (lot_id,))
        assert occupied[0]["current_homes"] == 1

        char2 = await _reload_char(harness, char["id"])
        sell = await housing.sell_home(harness.db, char2)
        assert sell["ok"], sell

        freed = await harness.db.fetchall(
            "SELECT current_homes FROM housing_lots WHERE id = ?", (lot_id,))
        assert freed[0]["current_homes"] == 0, (
            "sell_home must decrement housing_lots.current_homes like its "
            "siblings sell_shopfront / sell_hq -- otherwise the lot slot "
            "is permanently consumed"
        )

    async def test_lot_is_buyable_again_after_sale(self, harness):
        """The real-world symptom: without the fix, a full lot never frees
        up even after every Tier-3 owner sells."""
        lot_id, _ = await _make_lot(harness, label="ReuseLot", max_homes=1)
        s = await harness.login_as("FirstOwner", credits=200_000)
        char = dict(s.character)
        buy1 = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert buy1["ok"], buy1

        char2 = await _reload_char(harness, char["id"])
        sell = await housing.sell_home(harness.db, char2)
        assert sell["ok"], sell

        s2 = await harness.login_as("SecondOwner", credits=200_000)
        char3 = dict(s2.character)
        buy2 = await housing.purchase_home(harness.db, char3, lot_id, "small")
        assert buy2["ok"], (
            f"lot must be buyable again after the sole owner sold: {buy2.get('msg')}"
        )


# ── Bug 2: checkout refuses an owned home ──────────────────────────────────

class TestBug2CheckoutRefusesOwnedHome:
    async def test_checkout_refuses_and_home_survives(self, harness):
        lot_id, _ = await _make_lot(harness, label="RefuseLot")
        s = await harness.login_as("Refuser", credits=200_000)
        char = dict(s.character)
        buy = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert buy["ok"], buy

        result = await housing.checkout_room(harness.db, char)
        assert result["ok"] is False, (
            "checkout must REFUSE an owned private_residence, not destroy it"
        )
        assert "sell" in result["msg"].lower(), (
            "the refusal must point the player at 'housing sell'"
        )

        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?", (char["id"],))
        assert len(rows) == 1, "the owned home must survive a refused checkout"

    async def test_force_true_still_tears_down_for_internal_callers(self, harness):
        """force=True is how sell_home / rent-default foreclosure / @housing
        evict still repossess an owned home -- only the bare player command
        is refused."""
        lot_id, _ = await _make_lot(harness, label="ForceLot")
        s = await harness.login_as("Forcer", credits=200_000)
        char = dict(s.character)
        buy = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert buy["ok"], buy

        forced = await housing.checkout_room(harness.db, char, force=True)
        assert forced["ok"] is True, forced
        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?", (char["id"],))
        assert rows == [], "force=True must still tear the owned home down"

    async def test_rentals_are_unaffected(self, harness):
        """Rentals/faction-quarters checkout stays exactly as-is."""
        lot_id, _ = await _make_lot(harness, label="RentalUnaffected")
        s = await harness.login_as("RentalCheckout", credits=5_000)
        char = dict(s.character)
        rent = await housing.rent_room(harness.db, char, lot_id)
        assert rent["ok"], rent

        char2 = await _reload_char(harness, char["id"])
        result = await housing.checkout_room(harness.db, char2)
        assert result["ok"] is True, (
            "a plain rented_room checkout must still work with no force flag"
        )


# ── Bug 3: rent_room respects the total-home cap ───────────────────────────

class TestBug3RentRespectsTotalCap:
    async def test_second_home_no_longer_hard_blocked(self, harness):
        lot3_id, _ = await _make_lot(harness, label="CapHome3", planet="tatooine")
        s = await harness.login_as("CapRenter", credits=200_000)
        char = dict(s.character)
        buy = await housing.purchase_home(harness.db, char, lot3_id, "small")
        assert buy["ok"], buy

        lot1_id, _ = await _make_lot(harness, label="CapRent1", planet="tatooine")
        char2 = await _reload_char(harness, char["id"])
        rent = await housing.rent_room(harness.db, char2, lot1_id)
        assert rent["ok"] is True, (
            f"renting a 2nd home while under the cap must succeed: {rent.get('msg')}"
        )

    async def test_one_over_the_cap_is_refused_with_the_new_message(self, harness):
        s = await harness.login_as("CapMaxRenter", credits=50_000)
        char = dict(s.character)
        for i in range(housing.MAX_TIER3_TOTAL):
            lot_id, _ = await _make_lot(harness, label=f"MaxRentLot{i}")
            r = await housing.rent_room(harness.db, char, lot_id)
            assert r["ok"] is True, f"rental {i + 1} should succeed: {r.get('msg')}"

        over_lot_id, _ = await _make_lot(harness, label="OneTooManyRental")
        over = await housing.rent_room(harness.db, char, over_lot_id)
        assert over["ok"] is False
        assert "maximum" in over["msg"].lower(), over["msg"]
        assert "already have a place to stay" not in over["msg"].lower(), (
            "must use the total-cap message, not the stale single-home-block "
            "message that funneled into 'housing checkout'"
        )


# ── Bug 4: cross-tier lot-ID validation ────────────────────────────────────

class TestBug4CrossTierLotValidation:
    async def test_purchase_home_refuses_a_real_tier1_lot_id(self, harness):
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots(era="clone_wars")
        assert t1, "clone_wars era must seed at least one tier-1 lot"
        lot_id = await _lot_id_for_room(harness, t1[0][0])

        s = await harness.login_as("CrossBuyer", credits=200_000)
        char = dict(s.character)
        result = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert result["ok"] is False, (
            "purchase_home must refuse a lot_id that belongs to Tier 1"
        )

    async def test_rent_room_refuses_a_real_tier3_lot_id(self, harness):
        from engine.housing_lots_provider import get_tier3_lots
        t3 = get_tier3_lots(era="clone_wars")
        assert t3, "clone_wars era must seed at least one tier-3 lot"
        lot_id = await _lot_id_for_room(harness, t3[0][0])

        s = await harness.login_as("CrossRenter", credits=50_000)
        char = dict(s.character)
        result = await housing.rent_room(harness.db, char, lot_id)
        assert result["ok"] is False, (
            "rent_room must refuse a lot_id that belongs to Tier 3"
        )
        assert "not a rental location" in result["msg"].lower()

    async def test_purchase_hq_refuses_a_real_tier4_lot_id(self, harness):
        from engine.housing_lots_provider import get_tier4_lots
        t4 = get_tier4_lots(era="clone_wars")
        assert t4, "clone_wars era must seed at least one tier-4 lot"
        lot_id = await _lot_id_for_room(harness, t4[0][0])

        # A real org (leader = this char, funded treasury) so the flow
        # actually reaches the cross-tier check instead of bailing earlier
        # on "org not found" / "can't afford it".
        s = await harness.login_as("HqLeader", credits=0)
        char = dict(s.character)
        org_code = "bug4_test_hq_org"
        await harness.db.execute(
            "INSERT INTO organizations "
            "(code, name, org_type, director_managed, leader_id, "
            " hq_room_id, treasury, properties) "
            "VALUES (?, ?, 'faction', 0, ?, NULL, 500000, '{}')",
            (org_code, "Bug4 Test Org", char["id"]),
        )
        await harness.db.commit()

        result = await housing.purchase_hq(
            harness.db, char, org_code, "outpost", lot_id)
        assert result["ok"] is False, (
            "purchase_hq must refuse a lot_id that belongs to Tier 4"
        )

    def test_ad_hoc_lots_are_unaffected_by_the_cross_tier_guard(self):
        """Structural guard: the cross-tier check must be exclusion-based
        (reject only room_ids AFFIRMATIVELY known to belong to a different
        tier), not inclusion-based -- an inclusion-based check would reject
        every ad hoc/test-fabricated lot used throughout the housing test
        suite (none of them are registered in any era's provider corpus)."""
        for fn_name in ("async def rent_room(", "async def purchase_home(",
                        "async def purchase_hq("):
            i = HOUSING_SRC.index(fn_name)
            j = HOUSING_SRC.index("\nasync def ", i + 1)
            body = HOUSING_SRC[i:j]
            assert "_other_tier_rooms" in body, (
                f"{fn_name} must carry the exclusion-based cross-tier guard"
            )

    async def test_ad_hoc_lot_still_purchasable_regression_guard(self, harness):
        """The concrete regression case: an ad hoc test lot (not in any
        provider corpus) must still be purchasable/rentable after Bug 4's
        fix -- this is what an inclusion-based check would have broken."""
        lot_id, _ = await _make_lot(harness, label="AdHocStillWorks")
        s = await harness.login_as("AdHocBuyer", credits=200_000)
        char = dict(s.character)
        result = await housing.purchase_home(harness.db, char, lot_id, "small")
        assert result["ok"] is True, result


# ── Bug 5: stale Tier-3 rent-discount display string ───────────────────────

class TestBug5StaleDiscountStringRemoved:
    def test_tier3_listing_no_longer_claims_a_rent_discount(self):
        i = HOUSING_SRC.index("async def get_tier3_listing_lines")
        j = HOUSING_SRC.index("\nasync def ", i + 1)
        body = HOUSING_SRC[i:j]
        # Match the actual ANSI-wrapped code literals (the stale strings were
        # "\033[1;33m(-50% rent)\033[0m" / "\033[2m(-25% rent)\033[0m"), not
        # the housing.py comment's own plain-text explanation of the removal.
        assert "\033[1;33m(-50% rent)" not in body, body
        assert "\033[2m(-25% rent)" not in body, body

    async def test_lawless_lot_listing_has_no_discount_suffix(self, harness):
        from engine.housing_lots_provider import get_tier3_lots
        t3 = get_tier3_lots(era="clone_wars")
        assert t3, "clone_wars era must seed at least one tier-3 lot"
        lot_id = await _lot_id_for_room(harness, t3[0][0])
        await harness.db.execute(
            "UPDATE housing_lots SET security = 'lawless' WHERE id = ?", (lot_id,))
        await harness.db.commit()

        s = await harness.login_as("DiscountChecker", credits=10_000)
        char = dict(s.character)
        lines = await housing.get_tier3_listing_lines(harness.db, char)
        text = "\n".join(lines)
        assert "rent)" not in text.lower(), (
            f"listing must not include a stale discount suffix: {text}"
        )
