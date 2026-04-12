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
PRICE_SOURCE = 0.50
PRICE_NORMAL = 1.00
PRICE_DEMAND = 2.00


# ── Price calculation ─────────────────────────────────────────────────────────

def get_planet_price(good: TradeGood, planet: str) -> int:
    """
    Return base price per ton of good at planet.
    Source planets: 50%, demand planets: 200%, others: 100%.
    """
    if planet in good.source:
        mult = PRICE_SOURCE
    elif planet in good.demand:
        mult = PRICE_DEMAND
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

# Default per-good cap per refresh. Tuned so a YT-1300 (~100 tons cargo)
# cannot fill its hold on a single-planet stop — forces route hopping,
# forces players to actually travel the galaxy.
DEFAULT_MAX_UNITS_PER_REFRESH = 15
MAX_UNITS_PER_REFRESH = {
    "luxury_goods": 10,   # tightest cap: the worst offender in the exploit
    "spice":        10,
    "weapons":      10,
    "medical":      20,
    "foodstuffs":   30,   # loosest: bulk/cheap/legal
    "textiles":     25,
    "machinery":    15,
    "raw_ore":      25,
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
