# -*- coding: utf-8 -*-
"""
engine/creature_spoils.py — Sourcebook Enrichment Lane A, **Phase C**:
creature loot-on-kill (field-dressing the carcass).

Closes economy-audit v1 #16 ("Loot tables on NPC kills — NOT WIRED") and
delivers the Lane A roadmap §3 Phase-A *item 4* (creature harvest goods),
which Phase A deferred (Phase A shipped the data file + lore + encounter
pools; the harvest path was explicitly recorded as "not yet wired" in the
``harvest:`` block of ``data/npcs_creatures.yaml``). This module is the
consumer that block was authored for.

Design posture (faucet/sink discipline — see economy_audit_v2.md §1.x):
spoils are **resource stacks**, NOT raw credits. They land in the same
``inventory.resources`` list the wilderness *harvest* economy and the
crafting system already use (via ``engine.crafting.add_resource``), so the
new faucet flows straight into an existing sink (crafting consumes
components; the weapon-decay-by-repair treadmill keeps demand alive). No
new credit source is introduced — raw resources have no NPC buyer; they
sell only P2P through escrow-backed vendor-droid buy orders (money supply
untouched) or are consumed by crafting. So spoils add **no inflation
vector** to the freshly-tuned economy.

The one residual risk — resource oversupply depressing the P2P price — is
contained two ways: (1) spoils bias to **organic**, the lowest resource
tier, with chemical reserved for gated sources (the crab's water-sacs and
the DC-10 spor-crawler venom); and (2) spoils quality is **capped at 65**
(``_SPOILS_QUALITY_CEILING``), below ``crafting.T5_MIN_QUALITY`` (75) and
below what the rate-limited, credit-bearing harvest economy can reach. A
hasty field-dressing therefore yields only bulk low/mid-grade stock that
can never feed T5/premium recipes, so even unbounded combat-grinding floods
only the least-sensitive tier and cannot undercut the harvest faucet. This
keeps the Skinner-box "combat rewards you" loop while protecting economy
tuning.

The runtime IO half (the combat-death hook ``on_wild_creature_killed``)
lives in ``engine/wilderness_encounter_runtime.py`` — symmetric with the
creature *spawn* it mirrors; this module stays PURE and unit-testable with
no DB.

Per-creature spoils are entirely **data-driven** via the optional
``harvest:`` block on a creature in ``data/npcs_creatures.yaml``::

    harvest:
      good:       "magus_hide"     # display flavour (shown to the player)
      resource:   "organic"        # OPTIONAL — craftable RESOURCE_TYPE the
                                   #   good maps to. Default "organic".
                                   #   T5 wilderness-only types are rejected
                                   #   (they have their own gated drop
                                   #   sources; a common beast must not
                                   #   devalue them) → falls back to organic.
      yield:      1                # OPTIONAL — base stack quantity. Default 1.
      difficulty: 8                # OPTIONAL — Survival DC to field-dress.
                                   #   Default SPOILS_DIFFICULTY.

A creature with **no** ``harvest`` block yields nothing (and is left
untouched by the death hook). This is the designer's gate: nuisance/swarm
fauna (worrt, shredder bat, spor crawler) stay spoils-free, which makes the
big-predator kills feel rewarding by contrast.
"""
from __future__ import annotations

from typing import Optional

# ── Skill / difficulty ──────────────────────────────────────────────────────
# Field-dressing a downed creature is a Survival task, mirroring the
# wilderness-harvest skill (engine/harvest.py HARVEST_SKILL). The carcass is
# already dead, but doing it cleanly under field conditions is Moderate.
SPOILS_SKILL: str = "survival"
SPOILS_DIFFICULTY: int = 8  # Moderate (harvest uses Easy-Moderate = 6)

# ── Resource mapping ────────────────────────────────────────────────────────
# The T1-T4 era-neutral crafting resource types creature spoils may map to.
# We deliberately EXCLUDE the T5 wilderness-only materials
# (kyber_shard_minor / weapons_capacitor_core / scavenged_republic_tech /
# deep_dune_iron / composite_chitin) — those are gated to specific high-end
# drop sources (force-resonant landmarks, anomaly resolutions, the designated
# Maze-Predator chitin hunt) and must not be acquirable from an ordinary
# desert beast. If a creature's ``harvest.resource`` names a disallowed/unknown
# type, we fall back to the default rather than minting a T5 rare.
_ALLOWED_RESOURCE_TYPES = frozenset({
    "metal", "chemical", "organic", "energy", "composite", "rare",
})
_DEFAULT_RESOURCE: str = "organic"  # hides / meat / sacs are organic matter

# ── Yield scaling (WEG 5-point success bands, like engine/harvest.py) ────────
_BASE_QUALITY: float = 40.0          # quality at an exact-DC (margin 0) success
_QUALITY_PER_MARGIN: float = 3.0     # +3 quality per point of margin
_QUALITY_MIN: float = 1.0

# Economy guard (see economy_audit_v2.md faucet/sink discipline): a hasty
# field-dressing yields *bulk, low-to-mid-grade* material — never premium
# stock. We cap spoils quality well below the deliberate wilderness-HARVEST
# economy, which alone reaches the top of the 1..100 band (and is rate-limited
# by a 30-min per-region cooldown AND mints credits). Crucially this ceiling
# sits BELOW ``crafting.T5_MIN_QUALITY`` (75), so creature spoils can *never*
# satisfy a T5 or other high-min_quality recipe — those inputs must still come
# from harvest. The result: spoils flow only into the least-sensitive
# low/mid-grade resource tier, so even unbounded combat-grinding cannot flood
# the premium resource market or undercut the tuned harvest faucet. Spoils mint
# no credits at all (resources sell P2P via escrow-backed vendor-droid buy
# orders, or are consumed by crafting), so they add no inflation vector.
_SPOILS_QUALITY_CEILING: float = 65.0

_MARGIN_PER_EXTRA_UNIT: int = 6      # every 6 pts of margin → +1 stack unit
_MAX_EXTRA_UNITS: int = 2            # cap the margin-driven bonus (1..base+2)


def creature_has_spoils(creature: Optional[dict]) -> bool:
    """True iff the creature carries a non-empty ``harvest`` block with a
    ``good``. This is the gate the death hook checks before doing anything."""
    if not isinstance(creature, dict):
        return False
    h = creature.get("harvest")
    return bool(isinstance(h, dict) and h.get("good"))


def spoils_resource_type(creature: dict) -> str:
    """Resolve the craftable RESOURCE_TYPE a creature's spoils map to.

    Reads ``harvest.resource``; defaults to ``organic``. Any value not in the
    allowed T1-T4 set (including the T5 wilderness-only materials, or a typo)
    falls back to the default — a beast can never mint a gated rare."""
    h = creature.get("harvest") or {}
    rtype = str(h.get("resource") or _DEFAULT_RESOURCE).strip().lower()
    if rtype not in _ALLOWED_RESOURCE_TYPES:
        return _DEFAULT_RESOURCE
    return rtype


def spoils_difficulty(creature: dict) -> int:
    """Survival DC to field-dress this creature. Reads ``harvest.difficulty``;
    defaults to ``SPOILS_DIFFICULTY``."""
    h = creature.get("harvest") or {}
    try:
        diff = int(h.get("difficulty", SPOILS_DIFFICULTY))
    except (TypeError, ValueError):
        return SPOILS_DIFFICULTY
    return diff if diff > 0 else SPOILS_DIFFICULTY


def _base_yield(creature: dict) -> int:
    h = creature.get("harvest") or {}
    try:
        y = int(h.get("yield", 1))
    except (TypeError, ValueError):
        return 1
    return y if y >= 1 else 1


def resolve_spoils(creature: Optional[dict], margin: int) -> Optional[dict]:
    """Compute the resource stack a *successful* field-dressing yields.

    Args:
        creature: the creature library dict (must have a ``harvest`` block).
        margin:   the Survival check margin (roll - DC). Callers invoke this
                  only on success, so ``margin`` is expected >= 0; negatives
                  are clamped to 0 defensively.

    Returns a dict ``{good, resource_type, quantity, quality}`` or ``None`` if
    the creature has no spoils. Quantity scales with margin (WEG 5-point
    bands, capped); quality scales with margin and clamps to 1..100.
    """
    if not creature_has_spoils(creature):
        return None

    m = max(0, int(margin))
    good = str((creature.get("harvest") or {}).get("good"))
    rtype = spoils_resource_type(creature)

    extra = min(m // _MARGIN_PER_EXTRA_UNIT, _MAX_EXTRA_UNITS)
    quantity = _base_yield(creature) + extra

    quality = _BASE_QUALITY + _QUALITY_PER_MARGIN * m
    quality = round(max(_QUALITY_MIN, min(_SPOILS_QUALITY_CEILING, quality)), 1)

    return {
        "good": good,
        "resource_type": rtype,
        "quantity": int(quantity),
        "quality": quality,
    }


def spoils_success_line(killer_name: str, creature_name: str,
                        spoils: dict) -> str:
    """Room/announce line for a successful field-dressing."""
    return (
        f"{killer_name} field-dresses the {creature_name.lower()} and "
        f"recovers {spoils['quantity']}x {spoils['good']} "
        f"(q{int(spoils['quality'])} {spoils['resource_type']})."
    )


def spoils_failure_line(killer_name: str, creature_name: str) -> str:
    """Room/announce line for a botched field-dressing (no usable material)."""
    return (
        f"{killer_name} works over the {creature_name.lower()} but botches "
        f"the field-dressing — nothing usable comes off the carcass."
    )
