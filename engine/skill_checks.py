# -*- coding: utf-8 -*-
"""
engine/skill_checks.py  --  Out-of-combat skill check helpers
SW_MUSH  |  Economy Phase 2

Centralised helpers for non-combat skill checks used across
the mission, bounty, and smuggling systems.

Design principles:
  - Every check uses the character's actual skill pool (attribute + bonus)
  - Untrained use is allowed — you roll the raw attribute
  - Results produce: success/fail, margin, narrative flavour
  - Partial success possible on a near-miss (margin >= -4)
  - Wild Die applies (exploding 6, mishap on 1)

Difficulty scale (WEG D6 R&E p82):
  Very Easy   6
  Easy        8  (also floor for trivial tasks)
  Moderate   11
  Difficult  16
  Very Diff  21
  Heroic     26+
"""
import logging
import random
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class SkillCheckResult:
    roll: int           # Raw total including Wild Die
    difficulty: int
    success: bool       # roll >= difficulty
    margin: int         # roll - difficulty (negative = failure margin)
    critical_success: bool  # Wild Die exploded at least once AND succeeded
    fumble: bool        # Wild Die came up 1 (mishap)
    skill_used: str
    pool_str: str       # e.g. "4D+2"


def _pool_to_str(dice: int, pips: int) -> str:
    if pips == 0:
        return f"{dice}D"
    return f"{dice}D+{pips}"


def _roll_wild_die_pool(dice: int, pips: int) -> tuple[int, bool, bool]:
    """
    Roll a WEG D6 pool with Wild Die.
    Returns (total, critical_success, fumble).
    The last die is the Wild Die.
    """
    if dice <= 0:
        # Attribute-less character: 2D default floor
        dice = 2
        pips = 0

    # Regular dice
    regular = sum(random.randint(1, 6) for _ in range(max(0, dice - 1)))

    # Wild Die
    wild = random.randint(1, 6)
    fumble = (wild == 1)
    exploded = False

    if wild == 6:
        exploded = True
        while True:
            extra = random.randint(1, 6)
            wild += extra
            if extra != 6:
                break

    if fumble:
        # Mishap: subtract highest regular die result (min 0)
        # Simple approximation: subtract Wild Die result (just 1)
        total = max(0, regular + pips)
    else:
        total = regular + wild + pips

    return total, (exploded and not fumble), fumble


def perform_skill_check(
    char: dict,
    skill_name: str,
    difficulty: int,
    skill_registry=None,
) -> SkillCheckResult:
    """
    Perform a skill check for a character dict.

    Args:
        char: Character dict from session (has 'attributes', 'skills' keys).
        skill_name: Lowercase skill name e.g. "con", "search", "blaster".
        difficulty: Target number.
        skill_registry: SkillRegistry instance (loaded lazily if None).

    Returns:
        SkillCheckResult
    """
    # Lazy-load skill registry
    if skill_registry is None:
        try:
            from engine.character import SkillRegistry
            skill_registry = SkillRegistry()
            skill_registry.load_default()
        except Exception:
            skill_registry = None

    # Parse character's skill pool
    dice, pips = _get_skill_pool(char, skill_name, skill_registry)
    pool_str = _pool_to_str(dice, pips)

    total, crit, fumble = _roll_wild_die_pool(dice, pips)
    success = total >= difficulty
    margin = total - difficulty

    return SkillCheckResult(
        roll=total,
        difficulty=difficulty,
        success=success,
        margin=margin,
        critical_success=crit and success,
        fumble=fumble,
        skill_used=skill_name,
        pool_str=pool_str,
    )


def _get_skill_pool(char: dict, skill_name: str, skill_registry) -> tuple[int, int]:
    """
    Extract (dice, pips) for a character's effective skill pool.
    Falls back to raw attribute if skill not trained.
    """
    import json as _json
    key = skill_name.lower()

    # Look up attribute for this skill
    attr_name = _skill_to_attr(key, skill_registry)

    # Parse attributes JSON
    try:
        attrs = _json.loads(char.get("attributes", "{}"))
    except Exception:
        attrs = {}

    attr_pool = _parse_dice_str(attrs.get(attr_name, "2D"))
    attr_dice, attr_pips = attr_pool

    # Parse skills JSON for bonus
    try:
        skills = _json.loads(char.get("skills", "{}"))
    except Exception:
        skills = {}

    bonus_str = skills.get(key)
    if not bonus_str:
        # Untrained: roll raw attribute
        return attr_dice, attr_pips

    bonus_dice, bonus_pips = _parse_dice_str(bonus_str)
    total_pips = (attr_dice * 3 + attr_pips) + (bonus_dice * 3 + bonus_pips)
    return total_pips // 3, total_pips % 3


def _skill_to_attr(skill_name: str, skill_registry) -> str:
    """Get the governing attribute for a skill."""
    if skill_registry:
        try:
            skill_def = skill_registry.get(skill_name)
            if skill_def:
                return skill_def.attribute.lower()
        except Exception:
            pass

    # Hardcoded fallback for common skills
    _FALLBACK = {
        "blaster": "dexterity", "dodge": "dexterity", "melee combat": "dexterity",
        "brawling": "dexterity", "grenade": "dexterity", "melee parry": "dexterity",
        "con": "perception", "persuasion": "perception", "bargain": "perception",
        "search": "perception", "sneak": "dexterity", "hide": "dexterity",
        "streetwise": "knowledge", "survival": "knowledge", "languages": "knowledge",
        "first aid": "technical", "medicine": "technical",
        "computer programming/repair": "technical", "security": "technical",
        "blaster repair": "technical", "space transports repair": "technical",
        "space transports": "mechanical", "starship piloting": "mechanical",
        "astrogation": "mechanical", "repulsorlift operation": "mechanical",
        "stamina": "strength", "lifting": "strength", "brawling parry": "strength",
        "intimidation": "perception", "command": "perception",
        "willpower": "knowledge", "scholar": "knowledge",
        "starfighter repair": "technical", "capital ship repair": "technical",
        "starship weapon repair": "technical",
        "musical instrument": "perception",
    }
    return _FALLBACK.get(skill_name, "perception")


def _parse_dice_str(s: str) -> tuple[int, int]:
    """Parse '3D+2', '4D', '2D+1' etc into (dice, pips)."""
    if not s:
        return 2, 0
    s = s.strip().upper()
    try:
        if "D" in s:
            parts = s.split("D")
            dice = int(parts[0]) if parts[0] else 0
            pip_part = parts[1] if len(parts) > 1 else "0"
            pip_part = pip_part.replace("+", "").strip()
            pips = int(pip_part) if pip_part else 0
            return dice, pips
        else:
            return int(s) // 3, int(s) % 3
    except Exception:
        return 2, 0


# ── Mission completion skill check ────────────────────────────────────────────

# Maps mission type -> (skill_name, partial_pay_fraction)
# partial_pay: what fraction of reward you get on a partial success (margin >= -4)
MISSION_SKILL_MAP = {
    "combat":        ("blaster",                    0.50),
    "smuggling":     ("con",                        0.50),
    "investigation": ("search",                     0.75),
    "social":        ("persuasion",                 0.75),
    "technical":     ("space transports repair",    0.50),
    "medical":       ("first aid",                  0.75),
    "slicing":       ("computer programming/repair",0.50),
    "salvage":       ("search",                     0.75),
    "bounty":        ("streetwise",                 0.50),
    "delivery":      ("stamina",                    1.00),  # easy, always full pay
}

# Difficulty scaling: reward band -> difficulty
def mission_difficulty(reward: int) -> int:
    """Scale difficulty by reward amount."""
    if reward < 300:
        return 8    # Easy
    if reward < 600:
        return 11   # Moderate
    if reward < 1200:
        return 14   # Moderate+
    if reward < 2500:
        return 16   # Difficult
    if reward < 5000:
        return 19   # Very Difficult-
    return 21       # Very Difficult


def resolve_mission_completion(
    char: dict,
    mission_type: str,
    reward: int,
    skill_registry=None,
) -> dict:
    """
    Resolve a mission completion skill check.

    Returns:
        {
          "success": bool,
          "partial": bool,      # True if partial pay on near-miss
          "credits_earned": int,
          "roll": int,
          "difficulty": int,
          "skill": str,
          "pool": str,
          "fumble": bool,
          "message": str,       # narrative result line
        }
    """
    skill_name, partial_frac = MISSION_SKILL_MAP.get(
        mission_type.lower(), ("perception", 0.75)
    )
    difficulty = mission_difficulty(reward)

    result = perform_skill_check(char, skill_name, difficulty, skill_registry)

    if result.success:
        credits = reward
        if result.critical_success:
            # Exceptional success: +20% bonus
            credits = int(reward * 1.20)
            msg = (
                f"  Exceptional work. The client is impressed. "
                f"Bonus pay included."
            )
        else:
            msg = f"  Job well done. Payment received."
    elif result.margin >= -4:
        # Partial success: some pay, but not full
        credits = int(reward * partial_frac)
        msg = (
            f"  Close, but not quite. "
            f"Partial payment for the effort."
        )
    else:
        credits = 0
        if result.fumble:
            msg = (
                f"  Things went wrong. The client is not pleased. "
                f"No payment."
            )
        else:
            msg = (
                f"  The job fell through. "
                f"No payment this time."
            )

    return {
        "success": result.success,
        "partial": (not result.success and result.margin >= -4),
        "credits_earned": credits,
        "roll": result.roll,
        "difficulty": difficulty,
        "skill": skill_name,
        "pool": result.pool_str,
        "fumble": result.fumble,
        "critical": result.critical_success,
        "message": msg,
    }


# ── Bargain / Haggle check ───────────────────────────────────────────────────
#
# WEG D6 R&E Bargain Table (Galaxy Guide 6, p77):
# Player and NPC each roll Bargain.  The difference in rolls maps to a
# price modifier.  Simplified for MUSH: each 4 points of margin = ±2%,
# capped at ±10%.  A critical doubles the modifier.  A fumble inverts it.
#
# Usage:
#   from engine.skill_checks import resolve_bargain_check
#   result = resolve_bargain_check(char, npc_bargain_dice=3, npc_bargain_pips=0,
#                                  base_price=500)
#   final_price = result["adjusted_price"]
# ─────────────────────────────────────────────────────────────────────────────

def resolve_bargain_check(
    char: dict,
    base_price: int,
    npc_bargain_dice: int = 3,
    npc_bargain_pips: int = 0,
    is_buying: bool = True,
    skill_registry=None,
) -> dict:
    """
    Resolve a Bargain opposed roll for buy/sell transactions.

    The player rolls Bargain (or raw Perception if untrained).
    The NPC rolls a fixed Bargain pool.
    Margin maps to price shift: ±2% per 4 points, capped ±10%.
    Critical success: modifier is doubled (up to ±10% cap).
    Fumble: modifier is inverted (player gets worse deal).

    Args:
        char: Player character dict.
        base_price: The base sticker price before haggling.
        npc_bargain_dice: NPC's Bargain skill dice.
        npc_bargain_pips: NPC's Bargain skill pips.
        is_buying: True if player is buying (lower = better for player).
                   False if player is selling (higher = better for player).
        skill_registry: Optional SkillRegistry.

    Returns:
        {
          "adjusted_price": int,
          "price_modifier_pct": int,   # e.g. -4 means 4% cheaper
          "player_roll": int,
          "npc_roll": int,
          "player_pool": str,
          "npc_pool": str,
          "margin": int,               # player_roll - npc_roll
          "critical": bool,
          "fumble": bool,
          "message": str,              # narrative line
        }
    """
    # Player roll
    if skill_registry is None:
        try:
            from engine.character import SkillRegistry
            skill_registry = SkillRegistry()
            skill_registry.load_default()
        except Exception:
            skill_registry = None

    player_dice, player_pips = _get_skill_pool(char, "bargain", skill_registry)
    player_pool_str = _pool_to_str(player_dice, player_pips)

    player_total, player_crit, player_fumble = _roll_wild_die_pool(
        player_dice, player_pips
    )

    # NPC roll (no Wild Die — NPCs use flat rolls for simplicity)
    npc_total = sum(
        random.randint(1, 6) for _ in range(max(1, npc_bargain_dice))
    ) + npc_bargain_pips
    npc_pool_str = _pool_to_str(npc_bargain_dice, npc_bargain_pips)

    # Margin: positive = player wins the haggle
    margin = player_total - npc_total

    # Map margin to price modifier: ±2% per 4 points, capped ±10%
    raw_pct = (margin // 4) * 2  # e.g. margin 8 → +4%, margin -4 → -2%
    raw_pct = max(-10, min(10, raw_pct))

    # Critical doubles the modifier (still capped)
    if player_crit and margin > 0:
        raw_pct = max(-10, min(10, raw_pct * 2))

    # Fumble inverts the modifier (player gets worse deal)
    if player_fumble:
        raw_pct = -abs(raw_pct) if raw_pct >= 0 else abs(raw_pct)
        # Fumble always hurts: minimum -2% swing against player
        if is_buying and raw_pct <= 0:
            raw_pct = 2
        elif not is_buying and raw_pct >= 0:
            raw_pct = -2

    # Apply modifier: for buying, negative % = cheaper (good for player)
    # For selling, positive % = higher sell price (good for player)
    if is_buying:
        # Player wants to pay LESS. If they win, price decreases.
        # raw_pct positive = player wins = price goes DOWN
        modifier = -raw_pct
    else:
        # Player wants to get MORE. If they win, price goes UP.
        # raw_pct positive = player wins = price goes UP
        modifier = raw_pct

    adjusted = max(1, int(base_price * (1 + modifier / 100)))

    # Build narrative
    if modifier < 0:
        # Player pays more (buying) or gets less (selling)
        if is_buying:
            msg = f"  The vendor holds firm. You pay a bit extra."
        else:
            msg = f"  The vendor low-balls you. Not your best deal."
    elif modifier > 0:
        if is_buying:
            msg = f"  You haggle the price down. Nice deal."
        else:
            msg = f"  You talk the vendor up. Good negotiating."
    else:
        msg = f"  Standard price. No advantage either way."

    if player_crit and margin > 0:
        msg = f"  Masterful negotiation! The vendor is impressed."
    if player_fumble:
        msg = f"  Your haggling backfires. The vendor smirks."

    return {
        "adjusted_price": adjusted,
        "price_modifier_pct": modifier,
        "player_roll": player_total,
        "npc_roll": npc_total,
        "player_pool": player_pool_str,
        "npc_pool": npc_pool_str,
        "margin": margin,
        "critical": player_crit,
        "fumble": player_fumble,
        "message": msg,
    }


# ── Ship repair skill check ──────────────────────────────────────────────────
#
# Wraps perform_skill_check for damcon / shiprepair with repair-specific
# outputs: hull_repaired scaled by margin, fumble → catastrophic failure.
#
# Usage:
#   from engine.skill_checks import resolve_repair_check
#   result = resolve_repair_check(char, "space transports repair", difficulty=20)
#   if result["success"]:
#       hull_repaired = result["hull_repaired"]
# ─────────────────────────────────────────────────────────────────────────────

def resolve_repair_check(
    char: dict,
    skill_name: str,
    difficulty: int,
    is_hull: bool = False,
    skill_registry=None,
) -> dict:
    """
    Resolve a ship repair skill check via perform_skill_check.

    Args:
        char: Player character dict.
        skill_name: e.g. "space transports repair", "starfighter repair"
        difficulty: Target number (from REPAIR_DIFFICULTIES + combat penalty).
        is_hull: If True, success restores hull points scaled by margin.
        skill_registry: Optional SkillRegistry.

    Returns:
        {
          "success": bool,
          "partial": bool,          # margin >= -4, system stabilised but not fixed
          "catastrophic": bool,     # fumble or margin <= -9, system destroyed
          "hull_repaired": int,     # 0 for non-hull, 1 normal, 2 on crit
          "roll": int,
          "difficulty": int,
          "margin": int,
          "skill": str,
          "pool": str,
          "critical": bool,
          "fumble": bool,
          "message": str,
        }
    """
    result = perform_skill_check(char, skill_name, difficulty, skill_registry)

    hull_repaired = 0
    catastrophic = False
    partial = False

    if result.success:
        if is_hull:
            hull_repaired = 2 if result.critical_success else 1
            if result.critical_success:
                msg = (
                    f"  Outstanding work! Two hull breaches patched. "
                    f"({result.pool_str}: {result.roll} vs {difficulty})"
                )
            else:
                msg = (
                    f"  Repair successful. Hull breach sealed. "
                    f"({result.pool_str}: {result.roll} vs {difficulty})"
                )
        else:
            if result.critical_success:
                msg = (
                    f"  Expert repair! System restored and running clean. "
                    f"({result.pool_str}: {result.roll} vs {difficulty})"
                )
            else:
                msg = (
                    f"  Repair successful. System back online. "
                    f"({result.pool_str}: {result.roll} vs {difficulty})"
                )
    elif result.fumble or result.margin <= -9:
        # Catastrophic failure — system destroyed beyond repair
        catastrophic = True
        msg = (
            f"  Catastrophic failure! Components fused together — "
            f"needs a spacedock. "
            f"({result.pool_str}: {result.roll} vs {difficulty}, "
            f"margin: {result.margin})"
        )
    elif result.margin >= -4:
        # Near-miss: system not fixed but stabilised (no worsening)
        partial = True
        msg = (
            f"  Almost had it — system stabilised but still offline. "
            f"({result.pool_str}: {result.roll} vs {difficulty})"
        )
    else:
        msg = (
            f"  Repair failed. System remains offline. "
            f"({result.pool_str}: {result.roll} vs {difficulty})"
        )

    return {
        "success": result.success,
        "partial": partial,
        "catastrophic": catastrophic,
        "hull_repaired": hull_repaired,
        "roll": result.roll,
        "difficulty": difficulty,
        "margin": result.margin,
        "skill": skill_name,
        "pool": result.pool_str,
        "critical": result.critical_success,
        "fumble": result.fumble,
        "message": msg,
    }


# ── Coordinate (Command skill) check ────────────────────────────────────────
#
# Used by CoordinateCommand in space_commands.py.
# Simple wrapper so space_commands doesn't roll dice directly.
# ─────────────────────────────────────────────────────────────────────────────

def resolve_coordinate_check(
    char: dict,
    difficulty: int = 12,
    skill_registry=None,
) -> dict:
    """
    Resolve a Command skill check for crew coordination.

    Returns:
        {
          "success": bool,
          "critical": bool,     # crit = +2 bonus to crew instead of +1
          "fumble": bool,       # fumble = -1 penalty to crew
          "roll": int,
          "difficulty": int,
          "pool": str,
          "message": str,
        }
    """
    result = perform_skill_check(char, "command", difficulty, skill_registry)

    if result.success:
        if result.critical_success:
            msg = (
                f"Brilliant coordination! The crew acts as one. "
                f"(Command {result.pool_str}: {result.roll} vs {difficulty}) "
                f"+2 to all crew rolls this round."
            )
        else:
            msg = (
                f"The crew rallies! "
                f"(Command {result.pool_str}: {result.roll} vs {difficulty}) "
                f"+1 to all crew rolls this round."
            )
    else:
        if result.fumble:
            msg = (
                f"Confusing orders! The crew hesitates. "
                f"(Command {result.pool_str}: {result.roll} vs {difficulty}) "
                f"-1 to crew rolls this round."
            )
        else:
            msg = (
                f"The coordination attempt falls flat. "
                f"(Command {result.pool_str}: {result.roll} vs {difficulty})"
            )

    return {
        "success": result.success,
        "critical": result.critical_success,
        "fumble": result.fumble,
        "roll": result.roll,
        "difficulty": difficulty,
        "pool": result.pool_str,
        "message": msg,
    }
