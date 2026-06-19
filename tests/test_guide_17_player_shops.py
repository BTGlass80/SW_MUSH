"""Guard: Guide_17 Player Shops teaches commands that actually RESOLVE against
the live registry, and its vendor-droid numbers match the engine.

The Opus-owned guides quality pass.  Guide_17 drifted from HEAD on a dense set
of command-surface and mechanical claims that the green suite never saw (the
convention invariant guards the registry, not guide prose).  This pass corrected:

* **`bargain <slot>` was a phantom command.**  There is no `bargain` command at
  all — the haggle is applied AUTOMATICALLY inside the customer's `buy`, and only
  on Tier 2+ droids (``engine.vendor_droids.buy_from_droid`` runs the Bargain
  check only ``if b_dice > 0 or b_pips > 0``).  A Tier 1 droid never haggles; it
  sells at the listed price.
* **The bargain discount cap is 10%, not the prose's "10-25%."**  The opposed
  Bargain roll maps ±2% per 4 points of margin, capped ±10%
  (``engine.skill_checks.resolve_bargain_check``).
* **Customer buy syntax is ``buy <slot#> from <shop name>``** (or item name), with
  NO quantity argument — not ``buy <slot> [quantity]``.
* **Buy-order fulfilment is ``sell <resource> to <shop name>``** (resource name,
  automatic quantity) — not ``sell <qty> to <shop>``.
* **Posting a buy order is ``shop order <resource> <min_quality> <qty> <price_per>``**
  (four args, resources only) — not ``shop order <item> <max_price> [qty]``.  The
  old ``shop order metal 50 100`` example would not even parse.
* **No "max 5 simultaneous orders" cap exists.**  ``post_buy_order`` enforces no
  count cap; escrow (full ``qty × price_per`` locked up front) is the real limiter.
* **Tier upgrade is ``shop upgrade <tier>`` in place** (inventory preserved, price
  difference charged: 3,000 / 7,000 / 10,000 cr) — not "buy a new droid and sell
  the old one back."
* The recurring **relisting fee** (1% of slot value, min 10 cr, listings idle >30
  days) was undocumented and is now in §4/§9/§14.

This test pins each correction against the live engine so a future retune that
desyncs the guide fails loudly here instead of silently misleading players.
"""
import inspect
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_17_Player_Shops.md")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def reg():
    # Reuse the canonical full-registry builder (mirrors GameServer.__init__).
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_shopreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Every command Guide_17 teaches must resolve against HEAD ──────────────────
_TAUGHT_FORMS = [
    "shop",        # owner umbrella (shop buy/place/recall/name/desc/stock/...)
    "browse",      # customer: list/inspect room droids
    "+shop",       # owner dashboard
    "market",      # market search <planet|all>
    "buy",         # customer: buy <slot#> from <shop>
    "sell",        # customer: sell <resource> to <shop>
    "@shop",       # admin
]


class TestGuideCommandsResolve:
    @pytest.mark.parametrize("form", _TAUGHT_FORMS)
    def test_form_resolves(self, reg, form):
        assert reg.get(form) is not None, (
            f"Guide_17 teaches {form!r} but it no longer resolves against the "
            f"live registry"
        )

    def test_bargain_is_not_a_command(self, reg):
        """The phantom must stay dead: there is no `bargain` command — the
        haggle is automatic inside `buy`."""
        assert reg.get("bargain") is None, (
            "`bargain` resolved to a command — Guide_17 (and this test) assume "
            "the haggle is automatic inside `buy`, with no `bargain` command"
        )


# ── The phantom `bargain` command must not reappear in the prose ──────────────
class TestNoBargainCommandPhantom:
    def test_no_backticked_bargain_command(self, guide_text):
        # `bargain <slot>` / `bargain <anything>` as an imperative is the phantom.
        assert not re.search(r"`bargain\s+<", guide_text), (
            "Guide_17 must not teach a `bargain <...>` command — haggling is "
            "automatic on `buy` (Tier 2+ only)"
        )

    def test_guide_states_haggle_is_automatic(self, guide_text):
        assert "no separate `bargain` command" in guide_text or \
               "no `bargain` command" in guide_text, (
            "Guide_17 should explicitly tell players there is no bargain command"
        )

    def test_no_10_to_25_pct_claim(self, guide_text):
        for bad in ("10-25%", "10–25%", "25% off", "25%."):
            assert bad not in guide_text, (
                f"Guide_17 must not claim a {bad!r} haggle — the cap is 10%"
            )


# ── Tier table numbers must match the live vendor-droid data ──────────────────
class TestTierDataMatchesEngine:
    def test_tier_costs_slots_fees_bargain(self, guide_text):
        from engine.vendor_droids import get_tier

        # (key, cost, slots, fee%, bargain_dice, bargain_pips, buy_orders)
        expected = {
            "gn4":  (2000, 10, 2.0, 0, 0, False),
            "gn7":  (5000, 25, 1.5, 2, 0, False),
            "gn12": (12000, 50, 1.0, 3, 1, True),
        }
        for key, (cost, slots, fee, bd, bp, bo) in expected.items():
            t = get_tier(key)
            assert t is not None, f"vendor tier {key} missing from engine data"
            assert t["cost"] == cost
            assert t["slots"] == slots
            assert float(t["listing_fee_pct"]) == fee
            assert t["bargain_dice"] == bd
            assert t["bargain_pips"] == bp
            assert bool(t["buy_orders"]) is bo

            # Each cost + slot count is cited verbatim in the guide.
            assert f"{cost:,}" in guide_text, (
                f"Guide_17 omits the {key} cost {cost:,} cr"
            )

    def test_buy_orders_are_tier3_only(self, guide_text):
        from engine.vendor_droids import get_tier
        assert get_tier("gn4")["buy_orders"] is False
        assert get_tier("gn7")["buy_orders"] is False
        assert get_tier("gn12")["buy_orders"] is True
        assert "Tier 3" in guide_text and "buy order" in guide_text.lower()


# ── Customer + owner command SYNTAX must match HEAD ───────────────────────────
class TestCommandSyntax:
    def test_buy_from_shop_form(self, guide_text):
        # Real: `buy <slot#> from <shop name>` (no quantity arg).
        assert "buy <slot#> from <shop name>" in guide_text
        # The drifted `buy <slot> [quantity]` must be gone.
        assert "buy <slot> [quantity]" not in guide_text
        assert "buy <slot> [qty]" not in guide_text

    def test_sell_resource_form(self, guide_text):
        # Real: `sell <resource> to <shop name>`.
        assert "sell <resource> to <shop name>" in guide_text or \
               "sell <resource> to <shop>" in guide_text
        assert "sell <quantity> to" not in guide_text
        assert "sell <qty> to" not in guide_text

    def test_shop_order_four_arg_form(self, guide_text):
        # Real: `shop order <resource> <min_quality> <qty> <price_per>`.
        assert "shop order <resource> <min_quality> <qty> <price_per>" in guide_text
        # The drifted 2-3 arg form + its broken example must be gone.
        assert "shop order <item> <max_price>" not in guide_text
        assert "shop order metal 50 100" not in guide_text

    def test_buy_from_droid_takes_no_quantity(self):
        """Pin the fact §5 relies on: buy_from_droid has no quantity param —
        each `buy` purchases a single unit."""
        from engine.vendor_droids import buy_from_droid
        params = inspect.signature(buy_from_droid).parameters
        assert "qty" not in params and "quantity" not in params, (
            "buy_from_droid gained a quantity param — update Guide_17 §5 which "
            "states each buy purchases a single unit"
        )

    def test_buy_routes_on_from_keyword(self):
        """The ` from ` router in BuyCommand is what makes `buy ... from <shop>`
        reach the droid system."""
        from parser import space_commands
        src = inspect.getsource(space_commands.BuyCommand.execute)
        assert '" from "' in src, (
            "BuyCommand no longer routes on ' from ' — re-check Guide_17 §5 buy "
            "syntax"
        )


# ── Bargain mechanic: Tier-gated + 10% cap ────────────────────────────────────
class TestBargainMechanic:
    def test_bargain_only_runs_on_tier2_plus(self):
        """buy_from_droid runs the Bargain check only when the droid has a pool
        (Tier 2+).  Tier 1 (b_dice==0, b_pips==0) sells at the listed price."""
        from engine import vendor_droids
        src = inspect.getsource(vendor_droids.buy_from_droid)
        assert "b_dice > 0 or b_pips > 0" in src, (
            "buy_from_droid's Tier-gate on the Bargain check changed — re-check "
            "Guide_17's claim that Tier 1 droids never haggle"
        )

    def test_discount_cap_is_ten_percent(self):
        """resolve_bargain_check caps the price modifier at ±10%."""
        from engine import skill_checks
        src = inspect.getsource(skill_checks.resolve_bargain_check)
        assert "min(10" in src and "max(-10" in src, (
            "resolve_bargain_check's ±10% cap changed — update Guide_17 §1/§4/§5 "
            "and §14 (Bargain discount cap)"
        )

    def test_guide_cites_ten_percent_cap(self, guide_text):
        assert "capped at 10%" in guide_text or "10% (Tier 2+" in guide_text


# ── Buy orders: resources only, escrow up front, no count cap ─────────────────
class TestBuyOrders:
    def test_no_five_order_cap_in_engine(self):
        """post_buy_order enforces NO simultaneous-order count cap — escrow is
        the limiter.  The guide's old 'max 5 orders' was a phantom."""
        from engine import vendor_droids
        src = inspect.getsource(vendor_droids.post_buy_order)
        # No cap token of the shape the phantom implied.
        assert "MAX_ORDERS" not in src
        assert not re.search(r">=\s*5\b", src), (
            "post_buy_order appears to cap order count — re-check Guide_17 §6/§14 "
            "(which now states there is no hard cap, escrow is the limiter)"
        )

    def test_guide_dropped_the_five_cap(self, guide_text):
        assert "Max simultaneous orders per droid: 5" not in guide_text
        assert "Max active buy orders per droid" not in guide_text

    def test_escrow_is_up_front(self):
        """post_buy_order deducts qty×price escrow immediately at post time."""
        from engine import vendor_droids
        src = inspect.getsource(vendor_droids.post_buy_order)
        assert "escrow_needed = qty_wanted * price_per" in src
        assert "vendor_buy_order_escrow" in src
        assert "up front" in _read(GUIDE_PATH) or "up-front" in _read(GUIDE_PATH) \
            or "the moment you post" in _read(GUIDE_PATH)

    def test_buy_orders_are_resource_only(self, guide_text):
        """post_buy_order validates resource_type against crafting RESOURCE_TYPES;
        the guide must not promise buying finished items."""
        from engine import vendor_droids
        src = inspect.getsource(vendor_droids.post_buy_order)
        assert "RESOURCE_TYPES" in src
        assert "crafting resource" in guide_text.lower()


# ── Limits / floor / recall / relist must match engine constants ──────────────
class TestEngineConstants:
    def test_droid_limits(self, guide_text):
        from engine.vendor_droids import (
            MAX_DROIDS_PER_ROOM, MAX_DROIDS_PER_OWNER,
        )
        assert MAX_DROIDS_PER_ROOM == 2
        assert MAX_DROIDS_PER_OWNER == 3
        assert "2 vendor droids per room" in guide_text
        assert "3 vendor droids per owner" in guide_text

    def test_price_floor(self, guide_text):
        from engine.vendor_droids import PRICE_FLOOR_PCT
        assert PRICE_FLOOR_PCT == 0.5
        assert "50%" in guide_text

    def test_recall_timers(self, guide_text):
        from engine.vendor_droids import _WARN_DAYS, _RECALL_DAYS
        assert _WARN_DAYS == 30
        assert _RECALL_DAYS == 60
        assert "30 days" in guide_text
        assert "60 days" in guide_text

    def test_relist_fee_documented(self, guide_text):
        from engine.vendor_droids import (
            _RELIST_FEE_PCT, _RELIST_FEE_MIN, _LISTING_TTL_DAYS,
        )
        assert _RELIST_FEE_PCT == 0.01
        assert _RELIST_FEE_MIN == 10
        assert _LISTING_TTL_DAYS == 30
        # The guide now documents this previously-undocumented sink.
        assert "relist" in guide_text.lower()
        assert "1%" in guide_text
        assert "10 cr" in guide_text

    def test_forbidden_room_types(self, guide_text):
        from engine.vendor_droids import FORBIDDEN_ROOM_TYPES
        assert FORBIDDEN_ROOM_TYPES == frozenset(
            {"ship_interior", "tutorial", "wilderness", "space"}
        )
        # §2 enumerates all four forbidden surfaces + the no_commerce flag.
        for token in ("Ship interiors", "Tutorial", "Wilderness", "Space",
                      "no_commerce"):
            assert token in guide_text, f"Guide_17 §2 omits {token!r}"


# ── Tier upgrade is in-place via `shop upgrade`, not buy-new-and-sellback ──────
class TestUpgradePath:
    def test_upgrade_costs_match_engine(self, guide_text):
        """The UPGRADE_PRICES in shop_commands._cmd_upgrade are 3000/7000/10000."""
        from parser import shop_commands
        src = inspect.getsource(shop_commands.ShopCommand._cmd_upgrade)
        assert "(1, 2): 3000" in src
        assert "(2, 3): 7000" in src
        assert "(1, 3): 10000" in src
        # Guide cites all three.
        assert "3,000 cr" in guide_text
        assert "7,000 cr" in guide_text
        assert "10,000 cr" in guide_text

    def test_no_sellback_prose(self, guide_text):
        assert "sold back" not in guide_text
        assert "sell the old one back" in guide_text  # the explicit correction
        assert "shop upgrade <tier>" in guide_text
