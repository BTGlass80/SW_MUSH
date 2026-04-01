# -*- coding: utf-8 -*-
"""
engine/force_powers.py
Force Powers Engine — WEG D6 Revised & Expanded, Chapter 12

Implements 8 Force powers across Control, Sense, and Alter disciplines.
Each power is a dataclass describing its rules; resolve_force_power()
is the single entry point called by force_commands.py.

Powers implemented:
  Control:
    accelerate_healing  — heal one wound level (Moderate 15)
    control_pain        — ignore wound penalties this scene (Easy 10)
    remain_conscious    — stay up at Incapacitated (Diff 20, once/scene)

  Sense:
    life_sense          — detect living beings in room (Easy 10)
    sense_force         — detect Force users / dark side (Diff 10)

  Alter:
    telekinesis         — move/disarm object (Diff 10 + range mod)

  Control + Sense + Alter (combination):
    affect_mind         — implant suggestion on NPC (Diff 15+) [DSP]

  Alter (dark side):
    injure_kill         — Force-damage a target (opposed Alter vs STR) [DSP]

DSP mechanic (R&E p118):
  - Powers marked dark_side=True automatically award 1 DSP on use.
  - At DSP >= 6, a fall check is triggered: roll Willpower vs (DSP × 3).
    Failure = character falls to the dark side (permanent flag, narrated).

Difficulty reference (R&E p113):
  Very Easy  5  |  Easy  10  |  Moderate  15
  Difficult  20  |  Very Difficult  25  |  Heroic  30+
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Optional

from engine.dice import DicePool, roll_d6_pool, difficulty_check
from engine.character import Character, SkillRegistry, WoundLevel

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DIFFICULTY CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

VERY_EASY   = 5
EASY        = 10
MODERATE    = 15
DIFFICULT   = 20
VERY_DIFF   = 25
HEROIC      = 30

# DSP fall-check threshold (R&E p118)
DSP_FALL_THRESHOLD = 6


# ─────────────────────────────────────────────────────────────────────────────
# POWER DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ForcePower:
    key:         str           # internal name used in commands
    name:        str           # display name
    skills:      list[str]     # required force skills ("control", "sense", "alter")
    base_diff:   int           # base difficulty number
    dark_side:   bool = False  # True = automatically awards 1 DSP
    combat_only: bool = False  # True = only usable in active combat
    target:      str = "self"  # "self" | "room" | "target"
    description: str = ""


POWERS: dict[str, ForcePower] = {
    # ── Control ──────────────────────────────────────────────────────────────
    "accelerate_healing": ForcePower(
        key="accelerate_healing",
        name="Accelerate Healing",
        skills=["control"],
        base_diff=MODERATE,
        target="self",
        description=(
            "Focus the Force inward to speed natural recovery. "
            "On success, heal one wound level immediately. "
            "Can only be used once per day of rest."
        ),
    ),
    "control_pain": ForcePower(
        key="control_pain",
        name="Control Pain",
        skills=["control"],
        base_diff=EASY,
        target="self",
        description=(
            "Shut out pain and ignore wound penalties for the rest of the scene. "
            "Does not heal damage — wounds still apply when the power fades."
        ),
    ),
    "remain_conscious": ForcePower(
        key="remain_conscious",
        name="Remain Conscious",
        skills=["control"],
        base_diff=DIFFICULT,
        target="self",
        description=(
            "Force yourself to stay active despite Incapacitation. "
            "On success, act normally this round despite wound state. "
            "Can only be attempted once per combat."
        ),
    ),
    # ── Sense ─────────────────────────────────────────────────────────────────
    "life_sense": ForcePower(
        key="life_sense",
        name="Life Sense",
        skills=["sense"],
        base_diff=EASY,
        target="room",
        description=(
            "Extend your perception to feel all living presences in the area. "
            "Reveals number and rough emotional state of all beings in the room."
        ),
    ),
    "sense_force": ForcePower(
        key="sense_force",
        name="Sense Force",
        skills=["sense"],
        base_diff=EASY,
        target="room",
        description=(
            "Feel the currents of the Force around you. "
            "Detects Force-sensitive beings and dark side presences in the room."
        ),
    ),
    # ── Alter ─────────────────────────────────────────────────────────────────
    "telekinesis": ForcePower(
        key="telekinesis",
        name="Telekinesis",
        skills=["alter"],
        base_diff=EASY,       # base; +5 per range band beyond touch
        target="target",
        description=(
            "Move objects or creatures with the Force. "
            "Base difficulty 10; +5 per range band beyond arm's reach. "
            "Can disarm opponents (opposed by their Dexterity)."
        ),
    ),
    "injure_kill": ForcePower(
        key="injure_kill",
        name="Injure/Kill",
        skills=["alter"],
        base_diff=EASY,
        dark_side=True,
        combat_only=False,
        target="target",
        description=(
            "Use the Force as a weapon, crushing or striking a target. "
            "Roll Alter vs target's Strength. Margin of success = damage. "
            "DARK SIDE: using this power earns 1 Dark Side Point."
        ),
    ),
    # ── Combination ───────────────────────────────────────────────────────────
    "affect_mind": ForcePower(
        key="affect_mind",
        name="Affect Mind",
        skills=["control", "sense", "alter"],
        base_diff=MODERATE,
        dark_side=True,
        target="target",
        description=(
            "Reach into a being's mind and implant a suggestion or emotion. "
            "Roll lowest of Control/Sense/Alter vs difficulty (Moderate for "
            "simple suggestions; higher for complex commands). "
            "DARK SIDE: using this power earns 1 Dark Side Point."
        ),
    ),
}


def get_power(key: str) -> Optional[ForcePower]:
    """Look up a power by key (case-insensitive, underscore or space)."""
    normalized = key.lower().replace(" ", "_").replace("-", "_")
    return POWERS.get(normalized)


def list_powers_for_char(char: Character) -> list[ForcePower]:
    """Return all powers the character has the force skills to use."""
    available = []
    for power in POWERS.values():
        if all(_has_force_skill(char, s) for s in power.skills):
            available.append(power)
    return available


def _has_force_skill(char: Character, skill: str) -> bool:
    """Return True if the character has at least 1D in the given force skill."""
    pool = char.get_attribute(skill)
    return pool.dice > 0 or pool.pips > 0


# ─────────────────────────────────────────────────────────────────────────────
# POWER RESOLUTION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ForcePowerResult:
    power:        ForcePower
    success:      bool
    roll:         int
    difficulty:   int
    margin:       int              # roll - difficulty (negative on failure)
    narrative:    str
    dsp_gained:   int = 0         # how many DSP awarded this use
    fall_check:   bool = False    # True if a fall-check was triggered
    fall_failed:  bool = False    # True if they failed the fall check
    heal_amount:  int = 0         # wound levels healed (accelerate_healing)
    pain_suppressed: bool = False # True if control_pain succeeded
    targets_felt: list = field(default_factory=list)   # life_sense results
    damage_dealt: int = 0         # injure_kill margin


def resolve_force_power(
    power_key: str,
    char: Character,
    skill_reg: SkillRegistry,
    target_char: Optional[Character] = None,
    extra_diff: int = 0,
) -> ForcePowerResult:
    """
    Resolve a Force power use. Returns a ForcePowerResult.

    Args:
        power_key:    Key from POWERS dict.
        char:         The Force user.
        skill_reg:    Loaded SkillRegistry.
        target_char:  Target character (for targeted powers).
        extra_diff:   Additional difficulty (e.g. range modifier for telekinesis).
    """
    power = get_power(power_key)
    if power is None:
        return ForcePowerResult(
            power=ForcePower("unknown", "Unknown", [], 0),
            success=False, roll=0, difficulty=0, margin=0,
            narrative=f"Unknown Force power: {power_key}",
        )

    # ── Build skill pool ──────────────────────────────────────────────────────
    # For combination powers, use the lowest of the required skills.
    pools = [char.get_attribute(s) for s in power.skills]
    # Pick the weakest pool (fewest total pips)
    skill_pool = min(pools, key=lambda p: p.dice * 3 + p.pips)

    # Apply wound penalty
    from engine.dice import apply_wound_penalty
    wound_penalty = char.wound_level.penalty_dice
    skill_pool = apply_wound_penalty(skill_pool, wound_penalty)

    # ── Roll ──────────────────────────────────────────────────────────────────
    roll_result = roll_d6_pool(skill_pool)
    difficulty = power.base_diff + extra_diff
    margin = roll_result.total - difficulty
    success = margin >= 0

    # ── Build base narrative ──────────────────────────────────────────────────
    skill_label = "/".join(s.title() for s in power.skills)
    narrative_parts = [
        f"{power.name}: {skill_label} roll {roll_result.display()} "
        f"vs difficulty {difficulty} → {'SUCCESS' if success else 'FAILURE'}"
    ]

    result = ForcePowerResult(
        power=power,
        success=success,
        roll=roll_result.total,
        difficulty=difficulty,
        margin=margin,
        narrative="",
    )

    # ── Power-specific effects ────────────────────────────────────────────────
    if success:
        if power_key == "accelerate_healing":
            _resolve_accelerate_healing(result, char, narrative_parts)
        elif power_key == "control_pain":
            _resolve_control_pain(result, char, narrative_parts)
        elif power_key == "remain_conscious":
            _resolve_remain_conscious(result, char, narrative_parts)
        elif power_key == "life_sense":
            _resolve_life_sense(result, char, narrative_parts)
        elif power_key == "sense_force":
            _resolve_sense_force(result, char, narrative_parts)
        elif power_key == "telekinesis":
            _resolve_telekinesis(result, char, target_char, margin, narrative_parts)
        elif power_key == "injure_kill":
            _resolve_injure_kill(result, char, target_char, margin, narrative_parts)
        elif power_key == "affect_mind":
            _resolve_affect_mind(result, char, target_char, margin, narrative_parts)
    else:
        narrative_parts.append(
            "The Force slips from your grasp. The power has no effect."
        )

    # ── DSP award ─────────────────────────────────────────────────────────────
    if power.dark_side:
        result.dsp_gained = 1
        char.dark_side_points += 1
        narrative_parts.append(
            f"  {_dsp_warning(char.dark_side_points)}"
        )
        # Fall check at DSP >= 6
        if char.dark_side_points >= DSP_FALL_THRESHOLD:
            result.fall_check = True
            fall_result = _resolve_fall_check(char, skill_reg)
            result.fall_failed = not fall_result
            if not fall_result:
                narrative_parts.append(
                    "  THE DARK SIDE CALLS TO YOU. Your will crumbles. "
                    "You have fallen to the dark side."
                )
            else:
                narrative_parts.append(
                    "  The dark side pulls at you... but you hold firm. For now."
                )

    result.narrative = "\n".join(narrative_parts)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# INDIVIDUAL POWER RESOLVERS
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_accelerate_healing(result: ForcePowerResult, char: Character, parts: list):
    """Heal one wound level. R&E p113: one use per day of rest."""
    current = char.wound_level.value
    if current <= 0:
        parts.append("You are already fully healed.")
        result.success = False
        return
    # Heal one step
    char.wound_level = WoundLevel(max(0, current - 1))
    result.heal_amount = 1
    parts.append(
        f"You channel the Force inward. Your wounds knit. "
        f"({WoundLevel(current).display_name} → {char.wound_level.display_name})"
    )


def _resolve_control_pain(result: ForcePowerResult, char: Character, parts: list):
    """Suppress wound penalties for the scene. R&E p113."""
    result.pain_suppressed = True
    parts.append(
        "You push the pain aside. Wound penalties are suppressed for this scene. "
        "The damage remains — you simply no longer feel it."
    )


def _resolve_remain_conscious(result: ForcePowerResult, char: Character, parts: list):
    """Stay active at Incapacitated. R&E p113."""
    parts.append(
        "Through sheer Force of will you remain on your feet. "
        "You may act this round despite your wounds. "
        "This will not save you from further damage."
    )


def _resolve_life_sense(result: ForcePowerResult, char: Character, parts: list):
    """Detect living presences in the room. R&E p114."""
    # Caller fills targets_felt from the live session list; engine just narrates.
    result.targets_felt = ["(beings detected — see room context)"]
    parts.append(
        "You reach out with your feelings. The living Force flows through all "
        "beings nearby — you sense their presence and emotional state."
    )


def _resolve_sense_force(result: ForcePowerResult, char: Character, parts: list):
    """Detect Force users and dark side presence. R&E p114."""
    parts.append(
        "You open yourself to the currents of the Force. "
        "Force-sensitive beings and echoes of the dark side shimmer "
        "at the edges of your perception."
    )


def _resolve_telekinesis(result: ForcePowerResult, char: Character,
                          target_char: Optional[Character], margin: int, parts: list):
    """Move object or disarm. R&E p116."""
    if target_char:
        parts.append(
            f"The Force reaches out. {target_char.name} strains against "
            f"the invisible grip. (Margin: {margin})"
        )
    else:
        parts.append(
            f"The object rises, held by the Force. "
            f"You move it with a thought. (Margin: {margin})"
        )


def _resolve_injure_kill(result: ForcePowerResult, char: Character,
                          target_char: Optional[Character], margin: int, parts: list):
    """
    Opposed Alter vs target STR. Margin = effective damage.
    R&E p116. Always awards 1 DSP (handled in caller).
    """
    if target_char is None:
        parts.append("No target specified.")
        result.success = False
        return
    # Opposed: target rolls STR to resist
    target_str = target_char.get_attribute("strength")
    resist_roll = roll_d6_pool(target_str)
    effective_damage = margin - resist_roll.total
    result.damage_dealt = max(0, effective_damage)
    if effective_damage > 0:
        wound = target_char.apply_wound(effective_damage)
        parts.append(
            f"Dark power surges through your hands. "
            f"{target_char.name} convulses! "
            f"(Alter margin {margin} vs STR resist {resist_roll.total} "
            f"= {effective_damage} damage → {wound.display_name})"
        )
    else:
        parts.append(
            f"The dark power strikes but {target_char.name} endures. "
            f"(Alter margin {margin} vs STR resist {resist_roll.total} — resisted)"
        )


def _resolve_affect_mind(result: ForcePowerResult, char: Character,
                          target_char: Optional[Character], margin: int, parts: list):
    """
    Implant suggestion on NPC. R&E p117. Always awards 1 DSP.
    Complexity of suggestion determines effective difficulty.
    """
    if target_char is None:
        parts.append("No target specified.")
        result.success = False
        return
    if margin >= 10:
        strength = "strong"
        detail = "The suggestion takes firm hold."
    elif margin >= 5:
        strength = "moderate"
        detail = "The idea takes root, though the target may resist later."
    else:
        strength = "weak"
        detail = "A faint impression only — the target may shake it off."
    parts.append(
        f"You reach into {target_char.name}'s mind. A {strength} suggestion "
        f"settles over their thoughts. {detail} (Margin: {margin})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# DSP / FALL CHECK
# ─────────────────────────────────────────────────────────────────────────────

def _dsp_warning(dsp: int) -> str:
    """Return a DSP warning appropriate to current count."""
    if dsp >= DSP_FALL_THRESHOLD:
        return (f"[DARK SIDE] You now carry {dsp} Dark Side Points. "
                f"The darkness is consuming you.")
    elif dsp >= 4:
        return (f"[DARK SIDE] You now carry {dsp} Dark Side Points. "
                f"The darkness grows within you.")
    else:
        return f"[DARK SIDE] You gain 1 Dark Side Point. (Total: {dsp})"


def _resolve_fall_check(char: Character, skill_reg: SkillRegistry) -> bool:
    """
    R&E p118: At DSP >= 6, roll Willpower vs (DSP × 3).
    Returns True if the character resists the fall.
    """
    willpower_pool = char.get_skill_pool("willpower", skill_reg)
    roll = roll_d6_pool(willpower_pool)
    difficulty = char.dark_side_points * 3
    success = roll.total >= difficulty
    log.info(
        f"[force] fall check {char.name}: willpower {roll.total} "
        f"vs {difficulty} (DSP={char.dark_side_points}) → {'RESIST' if success else 'FALL'}"
    )
    return success


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def format_power_list(powers: list[ForcePower]) -> list[str]:
    """Format a list of powers for display."""
    lines = []
    for p in powers:
        skills_str = " + ".join(s.title() for s in p.skills)
        dsp_tag = "  [DARK SIDE]" if p.dark_side else ""
        lines.append(
            f"  {p.name:<28s} ({skills_str}, Diff {p.base_diff}){dsp_tag}"
        )
        lines.append(f"    {p.description[:80]}")
    return lines
