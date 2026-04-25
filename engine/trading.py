# -*- coding: utf-8 -*-
"""
engine/trading.py — Planetary Trade Goods (Drop 17)

Buy-low-sell-high cargo trading between planets.
Inspired by GG6 Tramp Freighters speculative trade (Ch.4) and
WEG R&E p.127 Bargain-modified price spreads.

Trade goods stored in ship's `cargo` JSON column as:
    [{"good": "raw_ore", "quantity": 50, "purchase_price": 50}, ...]

Planet price tiers:
    SOURCE   — 50%  of base price  (good produced cheaply here)
    NORMAL   — 100% of base price
    DEMAND   — 200% of base price  (good scarce/needed here)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import json
import logging

log = logging.getLogger(__name__)

# ── Trade good definitions ────────────────────────────────────────────────────

@dataclass
class TradeGood:
    key:         str
    name:        str
    base_price:  int          # credits per ton at NORMAL
    description: str
    source:      list[str]    # planet keys — 50% price
    demand:      list[str]    # planet keys — 200% price
    tons_per_unit: int = 1    # minimum buy quantity


TRADE_GOODS: dict[str, TradeGood] = {
    "raw_ore": TradeGood(
        key="raw_ore", name="Raw Ore",
        base_price=100,
        description="Unprocessed mineral ore. Heavy but always in demand at manufacturing hubs.",
        source=["tatooine", "kessel"],
        demand=["corellia"],
    ),
    "foodstuffs": TradeGood(
        key="foodstuffs", name="Foodstuffs",
        base_price=80,
        description="Preserved rations, grain, and packaged food. Essential at mining worlds.",
        source=["corellia"],
        demand=["kessel", "nar_shaddaa"],
    ),
    "manufactured_parts": TradeGood(
        key="manufactured_parts", name="Manufactured Parts",
        base_price=200,
        description="Machine components, repair kits, and fabricated goods.",
        source=["corellia"],
        demand=["tatooine", "nar_shaddaa"],
    ),
    "medical_supplies": TradeGood(
        key="medical_supplies", name="Medical Supplies",
        base_price=150,
        description="Bacta patches, surgical tools, and pharmaceutical supplies.",
        source=["corellia"],
        demand=["kessel", "tatooine"],
    ),
    "spice_legal": TradeGood(
        key="spice_legal", name="Spice (Legal Grade)",
        base_price=300,
        description="Licensed glitterstim in certified quantities. Still profitable.",
        source=["kessel"],
        demand=["nar_shaddaa"],
    ),
    "electronics": TradeGood(
        key="electronics", name="Electronics",
        base_price=250,
        description="Sensor arrays, comlink components, and shipboard systems.",
        source=["corellia"],
        demand=["tatooine"],
    ),
    "luxury_goods": TradeGood(
        key="luxury_goods", name="Luxury Goods",
        base_price=400,
        description="Fine textiles, rare spirits, and Outer Rim curiosities.",
        source=["corellia", "nar_shaddaa"],
        demand=["tatooine"],
    ),
    "weapons_licensed": TradeGood(
        key="weapons_licensed", name="Weapons (Licensed)",
        base_price=350,
        description="Blasters and carbines with valid BoSS documentation.",
        source=["corellia"],
        demand=["nar_shaddaa"],
    ),
}

# Ordered list for display
TRADE_GOOD_LIST = list(TRADE_GOODS.values())

# Price tier multipliers
# v29: Narrowed from 50%/200% (300% margin) to 70%/140% (100% margin).
# GG6 Tramp Freighters (p.78) shows supply/demand price modifiers of
# ±5-10%, not ±50-100%. We use wider spreads for gameplay but the old
# 4:1 ratio was an exploit — 2:1 is still very profitable.
PRICE_SOURCE = 0.70
PRICE_NORMAL = 1.00
PRICE_DEMAND = 1.40


# ── Price calculation ─────────────────────────────────────────────────────────

def get_planet_price(good: TradeGood, planet: str,
                     include_demand_depression: bool = False) -> int:
    """
    Return base price per ton of good at planet.
    Source planets: 70%, demand planets: 140%, others: 100%.

    If include_demand_depression=True, demand planet prices are reduced
    by recent sales volume (DemandPool). Used for sell-side pricing.
    """
    if planet in good.source:
        mult = PRICE_SOURCE
    elif planet in good.demand:
        mult = PRICE_DEMAND
        if include_demand_depression:
            depression = DEMAND_POOL.get_depression(planet, good.key)
            mult = max(PRICE_NORMAL, mult * (1.0 - depression))
    else:
        mult = PRICE_NORMAL
    return max(1, int(good.base_price * mult))


def get_planet_tier(good: TradeGood, planet: str) -> str:
    """Return 'source', 'demand', or 'normal' for this good/planet combo."""
    if planet in good.source:
        return "source"
    if planet in good.demand:
        return "demand"
    return "normal"


def get_market_at_planet(planet: str) -> list[dict]:
    """
    Return full market listing for a planet.
    Each entry: {good, name, base_price, planet_price, tier, description}
    """
    rows = []
    for good in TRADE_GOOD_LIST:
        rows.append({
            "key":          good.key,
            "name":         good.name,
            "base_price":   good.base_price,
            "planet_price": get_planet_price(good, planet),
            "tier":         get_planet_tier(good, planet),
            "description":  good.description,
        })
    # Sort: source first (buying opportunities), then demand, then normal
    tier_order = {"source": 0, "normal": 1, "demand": 2}
    rows.sort(key=lambda r: tier_order[r["tier"]])
    return rows


# ── Supply pool (review fix v1) ──────────────────────────────────────────────
#
# Caps available units of each good on each planet. Pools refill every
# SUPPLY_REFRESH_SECONDS up to MAX_UNITS_PER_REFRESH[good]. Fixes the
# exploit where trade goods could be bought in unlimited quantity and
# generated ~120x the design target income rate. See §6 of the review
# fixes design doc.
#
# Unused supply carries over up to 2x the refill amount so occasional
# traders don't feel rationed; only veteran grinders hit the cap.

import time

SUPPLY_REFRESH_SECONDS = 2700  # 45 minutes
SUPPLY_CARRYOVER_MULT = 2      # pool caps at 2x refill amount

# v29: Caps tightened ~40% from original values. Combined with the
# narrower margins (100% vs 300%), this brings trader income to
# ~6,000-8,000 cr/hr — within the design target of 4,000-8,000.
DEFAULT_MAX_UNITS_PER_REFRESH = 10
MAX_UNITS_PER_REFRESH = {
    "luxury_goods": 6,    # tightest: highest base price
    "spice_legal":  6,
    "weapons_licensed": 8,
    "medical_supplies": 10,
    "electronics":  10,
    "manufactured_parts": 10,
    "foodstuffs":   20,   # loosest: bulk/cheap/legal
    "raw_ore":      15,
}


def _max_units(good_key: str) -> int:
    return MAX_UNITS_PER_REFRESH.get(good_key, DEFAULT_MAX_UNITS_PER_REFRESH)


class SupplyPool:
    """Per-planet, per-good supply tracker. Process-memory only — the pool
    resets on restart, which is fine: it's a rate limiter, not game state.
    """

    def __init__(self) -> None:
        # (planet, good_key) -> (units_remaining, last_refresh_ts)
        self._pools: dict[tuple[str, str], tuple[int, float]] = {}

    def _refreshed(self, planet: str, good_key: str) -> int:
        """Return current units after applying any pending refresh."""
        now = time.time()
        max_units = _max_units(good_key)
        cap = max_units * SUPPLY_CARRYOVER_MULT
        key = (planet, good_key)
        if key not in self._pools:
            # First touch: seed at full supply with current timestamp.
            self._pools[key] = (max_units, now)
            return max_units
        units, last = self._pools[key]
        elapsed = now - last
        if elapsed >= SUPPLY_REFRESH_SECONDS:
            refreshes = int(elapsed // SUPPLY_REFRESH_SECONDS)
            units = min(cap, units + refreshes * max_units)
            last = last + refreshes * SUPPLY_REFRESH_SECONDS
            self._pools[key] = (units, last)
        return units

    def available(self, planet: str, good_key: str) -> int:
        return self._refreshed(planet, good_key)

    def consume(self, planet: str, good_key: str, units: int) -> bool:
        """Try to consume `units`. Returns False if insufficient supply."""
        avail = self._refreshed(planet, good_key)
        if units > avail:
            return False
        key = (planet, good_key)
        _, last = self._pools[key]
        self._pools[key] = (avail - units, last)
        return True

    def seconds_until_refresh(self, planet: str, good_key: str) -> int:
        """Rough countdown used for 'check back later' messaging."""
        key = (planet, good_key)
        if key not in self._pools:
            return 0
        _, last = self._pools[key]
        remaining = SUPPLY_REFRESH_SECONDS - (time.time() - last)
        return max(0, int(remaining))


# Module-level singleton. Import as: `from engine.trading import SUPPLY_POOL`
SUPPLY_POOL = SupplyPool()


# ── Demand depression pool (v29) ─────────────────────────────────────────────
#
# Tracks recent sell volume per planet/good. Selling cargo at a demand
# planet depresses the price — each ton sold in the last DEMAND_WINDOW
# reduces the sell price by DEPRESSION_PER_TON, capped at MAX_DEPRESSION.
# This creates a natural "demand saturation" curve: the first trader to
# arrive gets the best price, subsequent sellers get less until demand
# recovers.

DEMAND_WINDOW_SECONDS = 2700   # 45 minutes (matches supply refresh)
DEPRESSION_PER_TON = 0.005     # 0.5% per ton sold recently
MAX_DEPRESSION = 0.30          # cap at 30% reduction (demand never drops below normal)


class DemandPool:
    """Per-planet, per-good demand depression tracker."""

    def __init__(self) -> None:
        # (planet, good_key) -> list of (timestamp, tons_sold)
        self._sales: dict[tuple[str, str], list[tuple[float, int]]] = {}

    def record_sale(self, planet: str, good_key: str, tons: int) -> None:
        """Record a cargo sale for demand depression calculation."""
        key = (planet, good_key)
        now = time.time()
        if key not in self._sales:
            self._sales[key] = []
        self._sales[key].append((now, tons))

    def _prune(self, key: tuple[str, str]) -> None:
        """Remove sales older than the demand window."""
        cutoff = time.time() - DEMAND_WINDOW_SECONDS
        if key in self._sales:
            self._sales[key] = [
                (ts, t) for ts, t in self._sales[key] if ts > cutoff
            ]

    def get_depression(self, planet: str, good_key: str) -> float:
        """Return price depression factor (0.0 = no depression, 0.30 = max).

        Depression = min(MAX_DEPRESSION, recent_tons × DEPRESSION_PER_TON).
        """
        key = (planet, good_key)
        self._prune(key)
        recent_tons = sum(t for _, t in self._sales.get(key, []))
        return min(MAX_DEPRESSION, recent_tons * DEPRESSION_PER_TON)

    def get_recent_volume(self, planet: str, good_key: str) -> int:
        """Return total tons sold in the current demand window."""
        key = (planet, good_key)
        self._prune(key)
        return sum(t for _, t in self._sales.get(key, []))


DEMAND_POOL = DemandPool()


# ── Volume / bulk-purchase pricing (P3 §3.2.D) ────────────────────────────────
#
# Closes economy_audit_v1.md §3.2.D ("Volume price scaling. Buying 1 ton gets
# posted price. Buying 50 tons increases the effective price per unit (bulk
# premium). This is how commodity markets work — large orders move the price.")
#
# The premium is a function of order-size-relative-to-current-supply, NOT of
# raw quantity. A 50-ton order against a 200-ton supply pool is a small
# 25% slice and pays no premium; the same 50-ton order against a 50-ton
# supply pool is the entire market and pays the maximum premium. This
# matches GG6 Tramp Freighters' "thin market" intuition and means a
# freshly-refreshed planet doesn't punish the first buyer of the cycle.
#
# Pairs naturally with the existing DemandPool sell-side depression: buying
# in bulk at a source pays a premium on the way in, selling in bulk at a
# demand planet hits depression on the way out. Together they create a
# natural ceiling on whale-route profit per round-trip.

VOLUME_PREMIUM_FLOOR_PCT = 0.20   # orders ≤20% of supply: no premium
VOLUME_PREMIUM_CEIL_PCT  = 1.00   # orders ≥100% of supply: max premium
VOLUME_PREMIUM_MAX       = 0.40   # max premium = +40% per ton


def volume_premium(quantity: int, supply_available: int) -> float:
    """
    Bulk-purchase price premium for an order of `quantity` units against a
    market with `supply_available` units currently in stock.

    Returns a multiplicative premium in [0.0, VOLUME_PREMIUM_MAX] applied to
    the base per-ton price. Multiply base_price by (1.0 + premium) to get
    the effective per-ton price the player pays.

    Model: linear ramp.
      - Order fraction (quantity / supply_available) ≤ 0.20  → 0% premium
      - Order fraction ≥ 1.00                                → +40% premium
      - Linear in between

    Returns 0.0 when quantity ≤ 0 or supply_available ≤ 0; the caller's
    supply check is expected to have already rejected impossible orders.

    Examples:
        >>> round(volume_premium(5, 50), 4)    # 10% of supply: floor
        0.0
        >>> round(volume_premium(10, 50), 4)   # 20% of supply: floor edge
        0.0
        >>> round(volume_premium(25, 50), 4)   # 50% of supply: midpoint
        0.15
        >>> round(volume_premium(40, 50), 4)   # 80% of supply
        0.3
        >>> round(volume_premium(50, 50), 4)   # 100% of supply: ceiling
        0.4
        >>> round(volume_premium(60, 50), 4)   # over-supply (caller bug; clamp)
        0.4
        >>> volume_premium(0, 50)              # no order
        0.0
        >>> volume_premium(10, 0)              # empty market
        0.0
    """
    if quantity <= 0 or supply_available <= 0:
        return 0.0
    fraction = quantity / supply_available
    if fraction <= VOLUME_PREMIUM_FLOOR_PCT:
        return 0.0
    if fraction >= VOLUME_PREMIUM_CEIL_PCT:
        return VOLUME_PREMIUM_MAX
    span = VOLUME_PREMIUM_CEIL_PCT - VOLUME_PREMIUM_FLOOR_PCT  # 0.80
    return VOLUME_PREMIUM_MAX * (fraction - VOLUME_PREMIUM_FLOOR_PCT) / span


# ── Cargo hold helpers ────────────────────────────────────────────────────────

def get_ship_cargo(ship: dict) -> list[dict]:
    """Parse and return the ship's cargo list."""
    raw = ship.get("cargo", "[]")
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        log.warning("get_ship_cargo: unhandled exception", exc_info=True)
        return []


def get_cargo_tons(ship: dict) -> int:
    """Total tons of trade goods currently in the cargo hold."""
    return sum(item.get("quantity", 0) for item in get_ship_cargo(ship))


def get_cargo_capacity(ship: dict, template) -> int:
    """
    Available cargo capacity in tons.
    Accounts for mod weight already consumed by ship components.
    """
    if template is None:
        return 0
    base = template.cargo
    # Subtract mod cargo weight
    try:
        from engine.starships import get_effective_stats, get_ship_registry
        systems = json.loads(ship.get("systems") or "{}")
        eff = get_effective_stats(template, systems)
        base -= eff.get("cargo_used_by_mods", 0)
    except Exception:
        log.warning("get_cargo_capacity: unhandled exception", exc_info=True)
        pass
    return max(0, base)


def cargo_free(ship: dict, template) -> int:
    """Tons of free cargo space."""
    return max(0, get_cargo_capacity(ship, template) - get_cargo_tons(ship))


def add_cargo(ship_cargo: list, good_key: str, quantity: int,
              purchase_price: int) -> list:
    """
    Add quantity tons of a trade good to the cargo list.
    Merges with existing entries at the same purchase price.
    Returns updated cargo list.
    """
    for item in ship_cargo:
        if item["good"] == good_key and item["purchase_price"] == purchase_price:
            item["quantity"] += quantity
            return ship_cargo
    ship_cargo.append({
        "good":           good_key,
        "quantity":       quantity,
        "purchase_price": purchase_price,
    })
    return ship_cargo


def remove_cargo(ship_cargo: list, good_key: str,
                 quantity: int) -> tuple[list, int]:
    """
    Remove quantity tons of a good from cargo.
    Returns (updated_cargo, average_purchase_price).
    FIFO: removes from oldest entries first.
    """
    remaining = quantity
    total_cost = 0
    total_removed = 0
    new_cargo = []
    for item in ship_cargo:
        if item["good"] == good_key and remaining > 0:
            take = min(item["quantity"], remaining)
            total_cost += take * item["purchase_price"]
            total_removed += take
            remaining -= take
            if item["quantity"] > take:
                new_item = dict(item)
                new_item["quantity"] -= take
                new_cargo.append(new_item)
        else:
            new_cargo.append(item)
    avg_price = (total_cost // total_removed) if total_removed > 0 else 0
    return new_cargo, avg_price


def cargo_quantity(ship_cargo: list, good_key: str) -> int:
    """Total tons of a specific good in the cargo hold."""
    return sum(
        item["quantity"] for item in ship_cargo if item["good"] == good_key
    )
