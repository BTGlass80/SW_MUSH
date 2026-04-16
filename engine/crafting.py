"""
engine/crafting.py — SW_MUSH Crafting Engine (Phase 3, SWG-Lite)

Resource model, schematic loader, assembly and experimentation resolver.

Design decisions:
  - Resources stored in character['inventory'] JSON blob as a list of ResourceStack dicts.
  - Known schematics stored in character['attributes']['schematics'] as a list of keys.
  - ALL skill checks go through engine.skill_checks.perform_skill_check — never direct dice.
  - Quality range 1–100 (float). Stacks merge when same type AND quality within 5 pts.
  - Consumables are placed directly in the character's equipped/carrying items via items.py.

Resource types: metal, chemical, organic, energy, composite, rare

Experimentation (Cracken's Jury-Rigging, Session 24):
  After crafting, the player can 'experiment' on their *equipped* weapon to tune
  a stat axis (damage, accuracy, durability). Each experiment adds a breakdown die
  that is rolled on every combat use — risk of malfunction. Designed from WEG40046.
"""

import os
import json
import math
import random
import logging
import yaml
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOURCE_TYPES = {"metal", "chemical", "organic", "energy", "composite", "rare"}

# Quality thresholds → item stat effects (applied at craft time)
QUALITY_TIERS = [
    (90, dict(condition=100, max_condition=160, stat_bonus="moderate")),
    (80, dict(condition=100, max_condition=140, stat_bonus="minor")),
    (60, dict(condition=100, max_condition=120, stat_bonus=None)),
    (40, dict(condition=100, max_condition=100, stat_bonus=None)),
    (0,  dict(condition=60,  max_condition=60,  stat_bonus=None)),
]

# Skill margin → quality multiplier (applied after base quality from components)
# Margin ≥ 0: 1.0–1.3 scaled linearly. Critical = ×1.5 (×2.0 on experiment crit).
QUALITY_MULT_BASE = 1.0
QUALITY_MULT_MAX  = 1.3
QUALITY_MULT_CRIT = 1.5
QUALITY_MULT_EXP_CRIT = 2.0   # experiment critical
QUALITY_PARTIAL   = 0.5        # partial success (margin ≥ −4)

STACK_MERGE_TOLERANCE = 5.0    # quality points within which stacks merge

SCHEMATICS_YAML = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "schematics.yaml"
)

# ---------------------------------------------------------------------------
# Experimentation Parameters (Cracken's Jury-Rigging — WEG40046)
# ---------------------------------------------------------------------------
#
# Per-category defaults. Individual schematics can override in their YAML
# via an `experiment_params` block.
#
# Difficulty formula:  schematic.difficulty + 5 + (escalation × prior_experiments)
# Cracken's canon: +1D = Moderate(15), +2D = Difficult(20), +3D = Very Difficult(25)
#                  → that's a +5 step per tier, hence escalation = 5.
#
# breakdown_type maps to Cracken's 4 categories:
#   "lethal"     — weapons  (1: explode, 2: break, 3: jam, 4-6: fine)
#   "non_lethal" — equipment (1: break, 2: jam, 3-6: fine)
#   "vehicle"    — ship parts (1: shutdown, 2: degrade, 3-6: fine)
#   "no_dice"    — special devices (duration-limited)

DEFAULT_EXPERIMENT_PARAMS = {
    "weapon": {
        "axes": [
            {
                "axis": "damage",
                "label": "Galven Pattern Upgrade",
                "description": "Increases weapon damage output",
                "boost_per_margin": 0.5,
                "tradeoff_axis": "durability",
                "tradeoff_ratio": 0.3,
            },
            {
                "axis": "accuracy",
                "label": "Beam Calibration",
                "description": "Improves accuracy at the cost of damage",
                "boost_per_margin": 0.4,
                "tradeoff_axis": "damage",
                "tradeoff_ratio": 0.2,
            },
            {
                "axis": "durability",
                "label": "Reinforced Housing",
                "description": "Strengthens the weapon frame (no tradeoff)",
                "boost_per_margin": 0.6,
                "tradeoff_axis": None,
                "tradeoff_ratio": 0.0,
            },
        ],
        "max_experiments": 3,
        "difficulty_escalation": 5,
        "breakdown_type": "lethal",
        "skill_override": None,   # uses schematic skill_required
    },
    "component": {
        "axes": [
            {
                "axis": "power",
                "label": "Power Routing",
                "description": "Increases component output, adds weight",
                "boost_per_margin": 0.3,
                "tradeoff_axis": "weight",
                "tradeoff_ratio": 0.4,
            },
            {
                "axis": "weight",
                "label": "Mass Reduction",
                "description": "Lighter component, less reliable",
                "boost_per_margin": 0.4,
                "tradeoff_axis": "reliability",
                "tradeoff_ratio": 0.3,
            },
            {
                "axis": "reliability",
                "label": "Stress Testing",
                "description": "More reliable component (no tradeoff)",
                "boost_per_margin": 0.5,
                "tradeoff_axis": None,
                "tradeoff_ratio": 0.0,
            },
        ],
        "max_experiments": 2,
        "difficulty_escalation": 5,
        "breakdown_type": "vehicle",
        "skill_override": None,
    },
    "consumable": {
        "axes": [
            {
                "axis": "potency",
                "label": "Concentrated Formula",
                "description": "More potent but fewer uses",
                "boost_per_margin": 0.6,
                "tradeoff_axis": "yield",
                "tradeoff_ratio": 0.5,
            },
            {
                "axis": "yield",
                "label": "Extended Batch",
                "description": "More uses but weaker effect",
                "boost_per_margin": 0.4,
                "tradeoff_axis": "potency",
                "tradeoff_ratio": 0.3,
            },
        ],
        "max_experiments": 2,
        "difficulty_escalation": 3,
        "breakdown_type": "non_lethal",
        "skill_override": None,
    },
    "survival_gear": {
        "axes": [
            {
                "axis": "effectiveness",
                "label": "Enhanced Protection",
                "description": "Better hazard mitigation (no tradeoff)",
                "boost_per_margin": 0.5,
                "tradeoff_axis": None,
                "tradeoff_ratio": 0.0,
            },
        ],
        "max_experiments": 1,
        "difficulty_escalation": 4,
        "breakdown_type": "non_lethal",
        "skill_override": None,
    },
}


def get_experiment_params(schematic: dict) -> dict:
    """
    Return experiment parameters for a schematic.
    Uses schematic-level override if present, else category defaults.
    """
    # Check for schematic-level override first
    override = schematic.get("experiment_params")
    if override:
        return override
    # Fall back to category defaults by output_type
    output_type = schematic.get("output_type", "weapon")
    params = DEFAULT_EXPERIMENT_PARAMS.get(output_type)
    if params:
        return params
    # Ultimate fallback: weapon defaults
    return DEFAULT_EXPERIMENT_PARAMS["weapon"]


def get_experiment_axes(schematic: dict) -> list:
    """Return the list of axis dicts available for a schematic."""
    params = get_experiment_params(schematic)
    return params.get("axes", [])


def get_max_experiments(schematic: dict) -> int:
    """Return max experiment count for a schematic."""
    params = get_experiment_params(schematic)
    return params.get("max_experiments", 3)


def get_experiment_difficulty(schematic: dict, prior_count: int) -> int:
    """
    Calculate experiment difficulty.
    Formula: schematic.difficulty + 5 + (escalation × prior_experiments)
    """
    params = get_experiment_params(schematic)
    base = schematic.get("difficulty", 10)
    escalation = params.get("difficulty_escalation", 5)
    return base + 5 + (escalation * prior_count)


def resolve_experiment_result(
    margin: int,
    axis_def: dict,
    is_critical: bool = False,
) -> dict:
    """
    Calculate the boost and tradeoff from a successful experiment.

    Returns:
        {
            "axis": str, "boost": float,
            "tradeoff": {axis: amount} or None,
            "label": str
        }
    """
    boost_rate = axis_def.get("boost_per_margin", 0.5)
    boost = boost_rate * max(1, margin)
    if is_critical:
        boost *= 2.0

    tradeoff = None
    tradeoff_axis = axis_def.get("tradeoff_axis")
    if tradeoff_axis and not is_critical:
        tradeoff_ratio = axis_def.get("tradeoff_ratio", 0.3)
        tradeoff = {tradeoff_axis: round(-boost * tradeoff_ratio, 2)}

    return {
        "axis": axis_def["axis"],
        "boost": round(boost, 2),
        "tradeoff": tradeoff,
        "label": axis_def.get("label", axis_def["axis"]),
    }


def resolve_experiment_failure(margin: int, breakdown_type: str) -> str:
    """
    Determine what happens on a failed experiment.

    Args:
        margin: negative margin (how badly the check was failed)
        breakdown_type: "lethal", "non_lethal", "vehicle", "no_dice"

    Returns one of:
        "quality_loss"        — item quality degrades (regular failure)
        "fine"                — fumble but got lucky on breakdown table
        "jammed"              — item loses 25% max_condition
        "broken"              — item destroyed, no damage to crafter
        "exploded"            — item destroyed + stun damage to crafter
        "system_shutdown"     — component disabled (vehicle type)
        "degraded"            — component stat reduced (vehicle type)
    """
    # Regular failure (not a fumble): just quality loss
    if margin > -5:
        return "quality_loss"

    # Fumble territory (margin <= -5): roll on breakdown table
    roll = random.randint(1, 6)

    if breakdown_type == "lethal":
        if roll == 1:
            return "exploded"
        elif roll == 2:
            return "broken"
        elif roll == 3:
            return "jammed"
        else:
            return "fine"

    elif breakdown_type == "non_lethal":
        if roll == 1:
            return "broken"
        elif roll == 2:
            return "jammed"
        else:
            return "fine"

    elif breakdown_type == "vehicle":
        if roll == 1:
            return "system_shutdown"
        elif roll == 2:
            return "degraded"
        else:
            return "fine"

    else:
        # no_dice or unknown: non-lethal fallback
        if roll <= 2:
            return "jammed"
        return "fine"


# ---------------------------------------------------------------------------
# Schematic loading (cached singleton)
# ---------------------------------------------------------------------------

_schematics_cache: Optional[dict] = None


def _load_schematics() -> dict:
    global _schematics_cache
    if _schematics_cache is not None:
        return _schematics_cache
    with open(SCHEMATICS_YAML, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    _schematics_cache = {s["key"]: s for s in raw.get("schematics", [])}
    return _schematics_cache


def get_schematic(key: str) -> Optional[dict]:
    """Return a schematic dict by key, or None."""
    return _load_schematics().get(key)


def get_all_schematics() -> dict:
    """Return the full {key: schematic} mapping."""
    return _load_schematics()


# ---------------------------------------------------------------------------
# Resource stack helpers  (operate on inventory JSON lists)
# ---------------------------------------------------------------------------

def _get_resource_list(char: dict) -> list:
    """Return the mutable resource list from character inventory JSON."""
    inv = char.get("inventory")
    if isinstance(inv, str):
        try:
            inv = json.loads(inv)
        except (json.JSONDecodeError, TypeError):
            inv = {}
    if not isinstance(inv, dict):
        inv = {}
    return inv.setdefault("resources", [])


def _set_resource_list(char: dict, resources: list) -> None:
    """Write back a resource list into character inventory JSON."""
    inv = char.get("inventory")
    if isinstance(inv, str):
        try:
            inv = json.loads(inv)
        except (json.JSONDecodeError, TypeError):
            inv = {}
    if not isinstance(inv, dict):
        inv = {}
    inv["resources"] = resources
    char["inventory"] = json.dumps(inv)


def _find_stack(resources: list, rtype: str, quality: float) -> Optional[int]:
    """Return index of a mergeable stack (same type, quality within tolerance), or None."""
    for i, stack in enumerate(resources):
        if stack.get("type") == rtype:
            q = float(stack.get("quality", 0))
            if abs(q - quality) <= STACK_MERGE_TOLERANCE:
                return i
    return None


def add_resource(char: dict, rtype: str, quantity: int, quality: float) -> str:
    """
    Add resource(s) to a character's inventory, merging into an existing stack
    if one within tolerance exists (quality is averaged, weighted by quantity).
    Returns a summary string.
    """
    if rtype not in RESOURCE_TYPES:
        return f"Unknown resource type: {rtype}"

    quality = round(max(1.0, min(100.0, float(quality))), 1)
    resources = _get_resource_list(char)

    idx = _find_stack(resources, rtype, quality)
    if idx is not None:
        existing = resources[idx]
        old_qty = int(existing.get("quantity", 0))
        old_q   = float(existing.get("quality", quality))
        # Weighted average quality
        new_qty = old_qty + quantity
        new_q   = round((old_q * old_qty + quality * quantity) / new_qty, 1)
        resources[idx]["quantity"] = new_qty
        resources[idx]["quality"]  = new_q
        _set_resource_list(char, resources)
        return (
            f"Added {quantity}x {rtype} (q{quality:.0f}) to existing stack "
            f"[now {new_qty}x q{new_q:.0f}]."
        )
    else:
        resources.append({"type": rtype, "quantity": quantity, "quality": quality})
        _set_resource_list(char, resources)
        return f"Added {quantity}x {rtype} (quality {quality:.0f}) to inventory."


def remove_resource(char: dict, rtype: str, quantity: int, min_quality: float) -> bool:
    """
    Consume `quantity` units of `rtype` with quality >= min_quality.
    Returns True if consumed successfully, False if insufficient stock.
    Partial consumption does NOT occur — check availability first.
    """
    resources = _get_resource_list(char)
    # Collect stacks that qualify, sorted best quality first
    candidates = [
        (i, s) for i, s in enumerate(resources)
        if s.get("type") == rtype and float(s.get("quality", 0)) >= min_quality
    ]
    candidates.sort(key=lambda x: float(x[1].get("quality", 0)), reverse=True)

    total_available = sum(int(c[1].get("quantity", 0)) for c in candidates)
    if total_available < quantity:
        return False

    remaining = quantity
    for idx, stack in candidates:
        if remaining <= 0:
            break
        stack_qty = int(stack.get("quantity", 0))
        take = min(stack_qty, remaining)
        resources[idx]["quantity"] -= take
        remaining -= take

    # Prune empty stacks
    resources = [s for s in resources if int(s.get("quantity", 0)) > 0]
    _set_resource_list(char, resources)
    return True


def check_resources(char: dict, components: list) -> tuple[bool, str]:
    """
    Verify the character has all required components (type, qty, min_quality).
    Returns (ok: bool, message: str).
    """
    resources = _get_resource_list(char)
    missing = []
    for comp in components:
        rtype    = comp["type"]
        required = comp["quantity"]
        min_q    = comp.get("min_quality", 1)
        available = sum(
            int(s.get("quantity", 0))
            for s in resources
            if s.get("type") == rtype and float(s.get("quality", 0)) >= min_q
        )
        if available < required:
            missing.append(
                f"{required - available}x more {rtype} (min quality {min_q})"
            )
    if missing:
        return False, "Missing components: " + "; ".join(missing)
    return True, "OK"


def consume_components(char: dict, components: list) -> None:
    """Consume all listed components from character inventory (call after check_resources)."""
    for comp in components:
        remove_resource(char, comp["type"], comp["quantity"], comp.get("min_quality", 1))


def average_component_quality(char: dict, components: list) -> float:
    """
    Return the average quality of the components that *will* be consumed.
    Uses the best-quality qualifying stacks, matching the removal order.
    """
    resources = _get_resource_list(char)
    total_q  = 0.0
    total_qty = 0
    for comp in components:
        rtype   = comp["type"]
        needed  = comp["quantity"]
        min_q   = comp.get("min_quality", 1)
        stacks  = sorted(
            [s for s in resources
             if s.get("type") == rtype and float(s.get("quality", 0)) >= min_q],
            key=lambda s: float(s.get("quality", 0)), reverse=True
        )
        remaining = needed
        for s in stacks:
            if remaining <= 0:
                break
            take = min(int(s.get("quantity", 0)), remaining)
            total_q   += float(s.get("quality", 0)) * take
            total_qty += take
            remaining -= take
    if total_qty == 0:
        return 50.0
    return total_q / total_qty


# ---------------------------------------------------------------------------
# Quality → item stats
# ---------------------------------------------------------------------------

def quality_to_stats(quality: float) -> dict:
    """
    Return item creation stats for the given quality value:
      condition, max_condition, stat_bonus (None | "minor" | "moderate")
    """
    for threshold, stats in QUALITY_TIERS:
        if quality >= threshold:
            return dict(stats)
    return dict(QUALITY_TIERS[-1][1])


# ---------------------------------------------------------------------------
# Known schematic helpers
# ---------------------------------------------------------------------------

def get_known_schematics(char: dict) -> list:
    """Return list of schematic keys the character knows."""
    attrs = char.get("attributes")
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except (json.JSONDecodeError, TypeError):
            attrs = {}
    if not isinstance(attrs, dict):
        attrs = {}
    return list(attrs.get("schematics", []))


def add_known_schematic(char: dict, schematic_key: str) -> bool:
    """
    Add a schematic key to character's known list.
    Returns True if added, False if already known.
    """
    attrs = char.get("attributes")
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except (json.JSONDecodeError, TypeError):
            attrs = {}
    if not isinstance(attrs, dict):
        attrs = {}
    known = attrs.setdefault("schematics", [])
    if schematic_key in known:
        return False
    known.append(schematic_key)
    char["attributes"] = json.dumps(attrs)
    return True


def can_craft(char: dict, schematic: dict) -> tuple[bool, str]:
    """
    Check if the character can attempt a craft for the given schematic.
    Verifies: schematic is known + resources available.
    Returns (ok, reason_string).
    """
    known = get_known_schematics(char)
    if schematic["key"] not in known:
        return False, f"You don't know the {schematic['name']} schematic."
    ok, msg = check_resources(char, schematic["components"])
    if not ok:
        return False, msg
    return True, "OK"


# ---------------------------------------------------------------------------
# Assembly resolution (craft command)
# ---------------------------------------------------------------------------

def resolve_craft(
    char: dict,
    schematic: dict,
    skill_check_result,   # SkillCheckResult from perform_skill_check
    experiment: bool = False,
) -> dict:
    """
    Resolve a crafting attempt after a skill check has been performed.

    Returns a dict:
        success       bool  — True if item was created
        partial       bool  — True for partial success (lower quality, no crafter name)
        fumble        bool  — True if fumble (materials consumed, nothing produced)
        quality       float — Final item quality (0 if fumble)
        crafter_name  str   — Character name (empty if partial/fumble)
        stats         dict  — quality_to_stats() result
        message       str   — Narrative result
        consume       bool  — Whether to consume components (False only if 0-component edge case)
    """
    result = skill_check_result

    base_quality = average_component_quality(char, schematic["components"])

    # ── Fumble ──────────────────────────────────────────────────
    if result.fumble:
        # Consume materials regardless
        consume_components(char, schematic["components"])
        return {
            "success": False, "partial": False, "fumble": True,
            "quality": 0.0, "crafter_name": "", "stats": {},
            "message": (
                f"*CRACK* Something goes catastrophically wrong during assembly. "
                f"The components are ruined. You have nothing to show for your work."
            ),
            "consume": False,  # already consumed above
        }

    # ── Partial (near-miss: margin >= -4 but not a success) ─────
    if not result.success and result.margin >= -4:
        final_quality = round(base_quality * QUALITY_PARTIAL, 1)
        final_quality = max(1.0, min(100.0, final_quality))
        consume_components(char, schematic["components"])
        stats = quality_to_stats(final_quality)
        return {
            "success": True, "partial": True, "fumble": False,
            "quality": final_quality,
            "crafter_name": "",
            "stats": stats,
            "message": (
                f"You struggle through the assembly. The result is passable but "
                f"not your best work. [{schematic['name']}, quality {final_quality:.0f}]"
            ),
            "consume": False,
        }

    # ── Full failure (margin < -4, no fumble) ───────────────────
    if not result.success:
        return {
            "success": False, "partial": False, "fumble": False,
            "quality": 0.0, "crafter_name": "", "stats": {},
            "message": (
                f"You can't quite get the assembly right this time. "
                f"The components are undamaged — you can try again."
            ),
            "consume": False,
        }

    # ── Success ─────────────────────────────────────────────────
    # Quality multiplier: margin-scaled between 1.0 and 1.3 (or crit values)
    if result.critical_success:
        if experiment:
            multiplier = QUALITY_MULT_EXP_CRIT
            crit_note  = "An extraordinary experimental breakthrough!"
        else:
            multiplier = QUALITY_MULT_CRIT
            crit_note  = "Exceptional craftsmanship!"
    else:
        # Linear scale: margin 0 → 1.0, margin 10+ → 1.3
        multiplier = QUALITY_MULT_BASE + min(result.margin, 10) / 10.0 * (
            QUALITY_MULT_MAX - QUALITY_MULT_BASE
        )
        crit_note = ""

    final_quality = round(base_quality * multiplier, 1)
    final_quality = max(1.0, min(100.0, final_quality))

    char_name = char.get("name", "Unknown")
    stats = quality_to_stats(final_quality)

    stat_note = ""
    if stats.get("stat_bonus") == "minor":
        stat_note = " It carries a minor combat bonus."
    elif stats.get("stat_bonus") == "moderate":
        stat_note = " It bears a significant combat enhancement."

    consume_components(char, schematic["components"])

    tier_desc = _quality_tier_desc(final_quality)

    return {
        "success": True, "partial": False, "fumble": False,
        "quality": final_quality,
        "crafter_name": char_name,
        "stats": stats,
        "message": (
            f"{crit_note} You complete the {schematic['name']}. "
            f"Quality: {final_quality:.0f}/100 ({tier_desc}).{stat_note} "
            f"[Crafted by {char_name}]"
        ),
        "consume": False,
    }


def _quality_tier_desc(quality: float) -> str:
    if quality >= 90:
        return "Masterwork"
    if quality >= 80:
        return "Superior"
    if quality >= 60:
        return "Good"
    if quality >= 40:
        return "Standard"
    return "Poor"


# ---------------------------------------------------------------------------
# Survey zone helper
# ---------------------------------------------------------------------------

# Zone name substrings → resource types available there
# Outdoor zones (Jundland Wastes, outskirts, etc.) → metal + organic
# City zones → chemical + energy (scavenged)
_OUTDOOR_ZONE_KEYWORDS = {"jundland", "wastes", "outskirts", "desert", "mesa", "plains"}
_CITY_ZONE_KEYWORDS    = {"eisley", "market", "cantina", "docking", "district", "palace",
                          "spaceport", "commercial", "civic", "residential"}


def get_survey_resources(zone_name: str, quality: float = 50.0) -> list[dict]:
    """
    Return a list of resource dicts a character finds by surveying in a zone.

    Each dict: {"type": str, "amount": int, "quality": float}
    Outdoor zones yield metal + organic; city zones yield chemical + energy.
    Amount scales with quality: higher quality → more resources.
    """
    import random
    lz = zone_name.lower()
    if any(kw in lz for kw in _OUTDOOR_ZONE_KEYWORDS):
        types = ["metal", "organic"]
    else:
        types = ["chemical", "energy"]

    results = []
    for rtype in types:
        # Base 1-3 units, +1 per 25 quality above 30
        base_amount = random.randint(1, 3)
        quality_bonus = max(0, int((quality - 30) / 25))
        amount = base_amount + quality_bonus
        results.append({
            "type": rtype,
            "amount": amount,
            "quality": round(quality, 1),
        })
    return results


def survey_quality_from_margin(margin: int, is_outdoor: bool = False) -> float:
    """
    Map skill check margin to survey quality.
      Outdoor (Search): base 60–90
      City   (Search): base 30–60
    Higher margin → better quality (linear, capped).
    """
    if is_outdoor:
        base = 60.0
        ceiling = 90.0
    else:
        base = 30.0
        ceiling = 60.0

    # +2 quality per margin point above 0, up to ceiling
    quality = base + max(0, margin) * 2.0
    return round(min(quality, ceiling), 1)
