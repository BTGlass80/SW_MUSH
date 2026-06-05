# -*- coding: utf-8 -*-
"""
engine/ship_repair.py — the spacedock yard-repair sink.

Closes Economy Audit **F2** (`SW_MUSH_Economy_Audit_FINAL.md` R2/B5;
`economy_audit_v2.md` §1.3 priority #3): *ship repair is free, so the rich have
no high-tier drain.* The audit calls this "the single largest gap in the sink
architecture and the lever that keeps the high-tier economy from inflating."

The design, reconciled across both audit docs:

- **`damcon` field-repair stays FREE.** It is the in-combat skill moment — a
  successful Technical roll patches a *damaged* system or hull at no cost. We do
  not touch it. (Integrated report B5: "keep `damcon` free"; v2 §1.3.)
- A paid **spacedock** service (this module) does the two things `damcon`
  cannot, for credits routed through the ledger chokepoint:
    1. Restores **destroyed** systems — `damcon` explicitly refuses these
       ("DESTROYED -- needs spacedock"); the yard is that spacedock.
    2. Fully restores hull + any remaining *damaged* systems, so a player can
       pay to skip the field-repair grind.

**Pricing** is a fraction of *hull value* (the single-sourced
`ShipTemplate.cost`, exactly what the Kuat brokerage prices off), so the fee
scales with the asset — a 1.5 M-cr cruiser's destroyed hyperdrive bites the
whale, a starter freighter's does not. It is dominated by **destroyed-system**
fees (the part `damcon` can't help with); *damaged* systems and hull cost less
because `damcon` is the free alternative. A full restore of a badly-wrecked ship
lands in the audit's ~5–8 % / 5–15 %-per-system band.

This module is **pure** (no DB, no I/O) so the pricing math and the apply step
are unit-testable in isolation. The parser command (`SpacedockCommand` in
``parser/space_commands.py``) is the thin wrapper that gates on "docked",
debits via ``adjust_credits(..., "ship_repair")``, and persists the result.
"""

from __future__ import annotations

from engine.starships import REPAIRABLE_SYSTEMS, get_system_state

# ── Tunables (first-cuts; ratify against live `@economy` ledger data) ────────
# All percentages are of the hull's base cost (ShipTemplate.cost).
YARD_DESTROYED_PCT: float = 0.06   # per DESTROYED system — the load-bearing fee
YARD_DAMAGED_PCT:   float = 0.01   # per DAMAGED system — modest; damcon does these free
YARD_HULL_PCT:      float = 0.03   # × hull-damage fraction (full-breach restore ≈ 3%)
YARD_MIN_FEE:       int   = 50     # floor so even a trivial yard job is never free

# The hull is tracked separately as a `hull_damage` integer, NOT as a key in the
# ship systems JSON, so the per-system fees apply to the non-hull systems only.
SYSTEM_KEYS: tuple[str, ...] = tuple(s for s in REPAIRABLE_SYSTEMS if s != "hull")


def quote_yard_repair(
    template_cost: int,
    systems: dict,
    hull_damage: int,
    hull_max: int,
) -> dict:
    """Price a *full* yard restoration of a ship.

    Args:
        template_cost: the hull's base cost (``ShipTemplate.cost``); the value
            the fee is a fraction of. A non-positive cost yields the floor fee
            (a hull with no listed value still costs something to patch).
        systems: the ship's parsed systems dict (states: working/damaged/destroyed).
        hull_damage: current hull-damage points.
        hull_max: the ship's total hull pips (for the damage fraction).

    Returns:
        dict with::
            destroyed:    list[str]  systems needing the yard (damcon can't)
            damaged:      list[str]  systems damcon could field-repair for free
            hull_damage:  int
            hull_max:     int
            cost:         int        total credits to fully restore (0 if nothing to do)
            needs_repair: bool
    """
    destroyed = [s for s in SYSTEM_KEYS if get_system_state(systems, s) == "destroyed"]
    damaged = [s for s in SYSTEM_KEYS if get_system_state(systems, s) == "damaged"]

    hd = max(0, int(hull_damage or 0))
    hull_frac = (hd / hull_max) if hull_max and hull_max > 0 else 0.0
    hull_frac = min(1.0, hull_frac)  # a hull can be "destroyed" past max; cap the fee fraction

    needs_repair = bool(destroyed or damaged or hd > 0)

    base = max(0, int(template_cost or 0))
    raw = (
        len(destroyed) * YARD_DESTROYED_PCT
        + len(damaged) * YARD_DAMAGED_PCT
        + hull_frac * YARD_HULL_PCT
    ) * base

    if not needs_repair:
        cost = 0
    else:
        cost = max(int(round(raw)), YARD_MIN_FEE)

    return {
        "destroyed": destroyed,
        "damaged": damaged,
        "hull_damage": hd,
        "hull_max": int(hull_max or 0),
        "cost": cost,
        "needs_repair": needs_repair,
    }


def apply_yard_repair(systems: dict) -> dict:
    """Return a NEW systems dict with every non-hull system set to working.

    The caller persists this alongside ``hull_damage=0``. The input dict is not
    mutated (so a failed DB write can't leave a half-repaired in-memory ship).
    """
    new = dict(systems or {})
    for s in SYSTEM_KEYS:
        if get_system_state(new, s) != "working":
            new[s] = True
    return new
