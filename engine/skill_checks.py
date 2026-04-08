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
