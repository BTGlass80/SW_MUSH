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
    # Drop 4a (2026-06-04): mind-trick SPLIT.
    #   affect_mind   = the light "Jedi mind trick" — a *suggestion* on
    #                   the weak-minded. Contested by the target's will
    #                   (resolved deterministically vs an NPC; offered to
    #                   a PC who RPs it). NO Dark Side Point. dark_side=False.
    #   dominate_mind = coercion / domination — bending a will against
    #                   itself. Stays dark. dark_side=True (auto DSP).
    # Per Part V / Drop 4 locked decision (a): affect_mind was dark_side=True
    # and is now split so the canonical Jedi suggestion is not self-corrupting.
    "affect_mind": ForcePower(
        key="affect_mind",
        name="Affect Mind (Suggestion)",
        skills=["control", "sense", "alter"],
        base_diff=MODERATE,
        dark_side=False,
        target="target",
        description=(
            "Plant a gentle suggestion in a weak mind — the classic Jedi "
            "mind trick. Roll lowest of Control/Sense/Alter, contested by "
            "the target's will. On an NPC the engine resolves the effect "
            "(distract a guard, pry loose a fact); on a player it is offered "
            "for them to play out. No Dark Side Point."
        ),
    ),
    "dominate_mind": ForcePower(
        key="dominate_mind",
        name="Dominate Mind (Coercion)",
        skills=["control", "sense", "alter"],
        base_diff=DIFFICULT,
        dark_side=True,
        target="target",
        description=(
            "Force a will to break — coercion and domination, not mere "
            "suggestion. Stronger and harder than Affect Mind, it overrides "
            "resistance the suggestion cannot. DARK SIDE: using this power "
            "earns 1 Dark Side Point."
        ),
    ),
    # ── Drop 4a.2 (2026-06-04): further Sense powers (light) ────────────────
    "telepathy": ForcePower(
        key="telepathy",
        name="Telepathy",
        skills=["sense"],
        base_diff=MODERATE,
        target="target",
        description=(
            "Touch another mind with the Force. Between a Master and Padawan "
            "who share an active bond it reaches across any distance and you "
            "feel their condition; otherwise it is a wordless mind-touch "
            "(offered to a player to answer), or a skim of an NPC's surface "
            "thoughts."
        ),
    ),
    "sense_lie": ForcePower(
        key="sense_lie",
        name="Sense Deception",
        skills=["sense"],
        base_diff=MODERATE,
        target="target",
        description=(
            "Weigh another's sincerity against the Force. On a being who is "
            "concealing something you sense the deceit (and may glimpse what "
            "lies beneath); on an honest one you feel their truth. A player "
            "target is offered the read to play out."
        ),
    ),
    "farseeing": ForcePower(
        key="farseeing",
        name="Farseeing",
        skills=["sense"],
        base_diff=DIFFICULT,
        target="self",
        description=(
            "Let the Force show you what it will — a simple portent of danger "
            "near at hand. Difficult, and never precise: the future is always "
            "in motion."
        ),
    ),
    "danger_sense": ForcePower(
        key="danger_sense",
        name="Danger Sense",
        skills=["sense"],
        base_diff=MODERATE,
        target="self",
        description=(
            "Feel a threat an instant before it strikes. In combat you react "
            "first — your next initiative is rerolled, keeping the better. "
            "Out of combat it is an early warning."
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
    # ── Drop 4a (2026-06-04): structured effect signals ───────────────
    # The engine stays pure (no DB / no async). When a social/sense/
    # alter power resolves to a real mechanical outcome, the engine
    # records *what* happened here and the parser (which owns DB +
    # room context) performs the application. effect_kind is one of:
    #   "" | "suggestion" | "domination" | "disarm"
    #   | "life_sense" | "sense_force"
    # effect_payload carries kind-specific detail (e.g. strength tier).
    effect_kind:    str = ""
    effect_payload: dict = field(default_factory=dict)
    disarm:         bool = False   # telekinesis -> parser unequips target weapon


def resolve_force_power(
    power_key: str,
    char: Character,
    skill_reg: SkillRegistry,
    target_char: Optional[Character] = None,
    extra_diff: int = 0,
    *,
    weight_difficulty_mod: int = 0,
    extra_dsp_on_fail: int = 0,
    target_is_npc: bool = False,
) -> ForcePowerResult:
    """
    Resolve a Force power use. Returns a ForcePowerResult.

    Args:
        power_key:    Key from POWERS dict.
        char:         The Force user.
        skill_reg:    Loaded SkillRegistry.
        target_char:  Target character (for targeted powers).
        extra_diff:   Additional difficulty (e.g. range modifier for telekinesis).
        weight_difficulty_mod:  WoW.3c (May 24 2026): added to the
                                fall-check difficulty for Jedi PCs
                                with Weight of War > 50. Caller is
                                responsible for computing this via
                                ``engine.weight_of_war.dsp_resistance_modifier``
                                — keeping the Weight read at the
                                parser-side keeps this engine module
                                free of DB I/O and async concerns.
        extra_dsp_on_fail:      WoW.3c: extra DSP applied on top of
                                the baseline +1 when a fall check
                                fails AND the Jedi has Weight ≥ 151.
                                From ``extra_dsp_on_failed_resist``.
        target_is_npc:          Drop 4a (2026-06-04): when True for a
                                mind power (affect_mind / dominate_mind),
                                the target's resistance is resolved as a
                                real OPPOSED willpower roll (WEG R&E mind
                                influence is opposed, not flat-difficulty;
                                a weak-minded being resists with its low
                                governing attribute and is easily swayed).
                                When False, the difficulty stays the base
                                complexity — used for PC targets, whose
                                outcome the parser OFFERS rather than
                                auto-rolls (player agency). The caller
                                tells us which because only it knows
                                whether the target row is a PC or an NPC.
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

    # ── Drop 4a (2026-06-04): opposed resistance for mind powers ───────────────
    # WEG R&E mind influence is an OPPOSED roll — the target resists with
    # willpower (untrained → its governing attribute, so a weak-minded
    # being resists poorly and is easily swayed). For an NPC the engine
    # rolls that resistance now and the base complexity acts as a floor:
    # the suggestion must clear both the inherent difficulty and the will
    # actively resisting it. For a PC (target_is_npc False) the difficulty
    # stays the base complexity and the parser OFFERS the formed suggestion
    # rather than auto-rolling the other player's mind (agency).
    mind_resist_total = None
    if (target_char is not None and target_is_npc
            and power_key in ("affect_mind", "dominate_mind")):
        resist_pool = target_char.get_skill_pool("willpower", skill_reg)
        resist_roll = roll_d6_pool(resist_pool)
        mind_resist_total = resist_roll.total
        difficulty = max(difficulty, mind_resist_total)

    margin = roll_result.total - difficulty
    success = margin >= 0

    # ── Build base narrative ──────────────────────────────────────────────────
    skill_label = "/".join(s.title() for s in power.skills)
    narrative_parts = [
        f"{power.name}: {skill_label} roll {roll_result.display()} "
        f"vs difficulty {difficulty} → {'SUCCESS' if success else 'FAILURE'}"
    ]
    if mind_resist_total is not None:
        narrative_parts.append(
            f"  ({target_char.name} resists with willpower {mind_resist_total})"
        )

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
        elif power_key == "dominate_mind":
            _resolve_dominate_mind(result, char, target_char, margin, narrative_parts)
        elif power_key == "telepathy":
            _resolve_telepathy(result, char, target_char, margin, narrative_parts)
        elif power_key == "sense_lie":
            _resolve_sense_lie(result, char, target_char, margin, narrative_parts)
        elif power_key == "farseeing":
            _resolve_farseeing(result, char, narrative_parts)
        elif power_key == "danger_sense":
            _resolve_danger_sense(result, char, narrative_parts)
    else:
        narrative_parts.append(
            "The Force slips from your grasp. The power has no effect."
        )

    # Record the opposed resistance roll (if any) so the parser/tests can
    # surface it regardless of success.
    if mind_resist_total is not None:
        result.effect_payload["resist_roll"] = mind_resist_total

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
            # WoW.3c (May 24 2026): the caller passes
            # ``weight_difficulty_mod`` derived from the Jedi's
            # Weight of War via
            # ``engine.weight_of_war.dsp_resistance_modifier``.
            # Defaults to 0 for non-Jedi or low-Weight Jedi, so
            # all existing callers and tests are unaffected. The
            # modifier is added to the standard ``DSP × 3``
            # difficulty inside ``_resolve_fall_check``.
            fall_result = _resolve_fall_check(
                char, skill_reg,
                weight_difficulty_mod=weight_difficulty_mod,
            )
            result.fall_failed = not fall_result
            if not fall_result:
                narrative_parts.append(
                    "  THE DARK SIDE CALLS TO YOU. Your will crumbles. "
                    "You have fallen to the dark side."
                )
                # WoW.3c: at Weight ≥ 151, a failed fall check
                # grants ``extra_dsp_on_fail`` additional DSP on
                # top of the baseline +1 from above. The substrate
                # value comes from
                # ``extra_dsp_on_failed_resist(weight)``.
                if extra_dsp_on_fail > 0:
                    char.dark_side_points += int(extra_dsp_on_fail)
                    result.dsp_gained += int(extra_dsp_on_fail)
                    narrative_parts.append(
                        f"  The Weight of War weighs you down "
                        f"further; the dark side claims another "
                        f"piece of you. (+{int(extra_dsp_on_fail)} DSP)"
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
    """Detect living presences in the room. R&E p114.

    Drop 4a: the engine only confirms success + flavor; the parser owns
    the room/session/NPC context and fills ``targets_felt`` with the real
    list of beings (see effect_kind="life_sense").
    """
    result.effect_kind = "life_sense"
    parts.append(
        "You reach out with your feelings. The living Force flows through all "
        "beings nearby — you sense their presence and emotional state."
    )


def _resolve_sense_force(result: ForcePowerResult, char: Character, parts: list):
    """Detect Force users and dark side presence. R&E p114.

    Drop 4a: effect_kind="sense_force" tells the parser to enumerate the
    real Force-sensitive / dark-tinged beings in the room.
    """
    result.effect_kind = "sense_force"
    parts.append(
        "You open yourself to the currents of the Force. "
        "Force-sensitive beings and echoes of the dark side shimmer "
        "at the edges of your perception."
    )


def _resolve_telekinesis(result: ForcePowerResult, char: Character,
                          target_char: Optional[Character], margin: int, parts: list):
    """Move object or disarm. R&E p116.

    Drop 4a: against a *target* with enough margin, this is a real disarm
    (the parser unequips the target's weapon). margin gates it so a bare
    success can shove without stripping the weapon.
    """
    DISARM_MARGIN = 3  # need to beat the grip, not just touch the object
    if target_char:
        if margin >= DISARM_MARGIN:
            result.disarm = True
            result.effect_kind = "disarm"
            result.effect_payload = {"margin": margin}
            parts.append(
                f"The Force closes around {target_char.name}'s weapon and "
                f"wrenches — their grip fails. (Margin: {margin})"
            )
        else:
            parts.append(
                f"The Force shoves {target_char.name} back a step, but their "
                f"hold doesn't break. (Margin: {margin})"
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


def _strength_tier(margin: int) -> tuple[str, str]:
    """Map a contest margin to a (tier, detail) pair shared by the two
    mind powers."""
    if margin >= 10:
        return "strong", "The suggestion takes firm hold."
    if margin >= 5:
        return "moderate", "The idea takes root, though it may not last."
    return "weak", "A faint impression only — it may be shaken off."


def _resolve_affect_mind(result: ForcePowerResult, char: Character,
                          target_char: Optional[Character], margin: int, parts: list):
    """
    Light suggestion — the Jedi mind trick. R&E p117.

    Drop 4a: no DSP (dark_side=False on the power). The engine confirms the
    contest and records ``effect_kind="suggestion"`` + a strength tier; the
    parser applies the real outcome (distract a guard, pry a fact) for an NPC,
    or *offers* it to a PC target who plays it out (never auto-override).
    """
    if target_char is None:
        parts.append("No target specified.")
        result.success = False
        return
    strength, detail = _strength_tier(margin)
    result.effect_kind = "suggestion"
    result.effect_payload = {"strength": strength, "margin": margin}
    parts.append(
        f"You press a quiet suggestion toward {target_char.name}. "
        f"A {strength} impulse settles over their thoughts. {detail} "
        f"(Margin: {margin})"
    )


def _resolve_dominate_mind(result: ForcePowerResult, char: Character,
                            target_char: Optional[Character], margin: int, parts: list):
    """
    Coercion / domination — the dark counterpart to Affect Mind. R&E p117.
    Always awards 1 DSP (dark_side=True, handled in the caller).

    Drop 4a: ``effect_kind="domination"`` — a forced compliance the parser
    applies more strongly than a suggestion (it can override a will that a
    suggestion cannot, and against an NPC it never merely "may be shaken off").
    """
    if target_char is None:
        parts.append("No target specified.")
        result.success = False
        return
    strength, _ = _strength_tier(margin)
    result.effect_kind = "domination"
    result.effect_payload = {"strength": strength, "margin": margin}
    parts.append(
        f"You seize {target_char.name}'s will and bend it to yours. "
        f"Resistance buckles — they will do as you command. (Margin: {margin})"
    )


# ── Drop 4a.2 (2026-06-04): telepathy / sense-lie / farseeing / danger-sense ──
# All Sense powers (light; dark_side=False). The engine confirms success +
# records effect_kind; the parser performs the DB / combat / bond-aware
# application (mirrors the 4a contract).

def _resolve_telepathy(result: ForcePowerResult, char: Character,
                        target_char: Optional[Character], margin: int, parts: list):
    """Mind-to-mind contact. R&E p115.

    Parser side: between two PCs with an active Master-Padawan bond this is a
    deep communion across distance; otherwise an in-room mind-touch (offered
    to a PC to RP). Against an NPC it skims surface thoughts.
    """
    if target_char is None:
        parts.append("No target specified.")
        result.success = False
        return
    result.effect_kind = "telepathy"
    result.effect_payload = {"margin": margin}
    parts.append(
        f"You reach out toward {target_char.name}'s mind with the Force. "
        f"(Margin: {margin})"
    )


def _resolve_sense_lie(result: ForcePowerResult, char: Character,
                        target_char: Optional[Character], margin: int, parts: list):
    """Sense deception — receptive reading of sincerity. R&E p115.

    Parser side: reveals whether an NPC is concealing something (reads real
    deception / hidden-intent flags); a PC target is offered the read to RP.
    """
    if target_char is None:
        parts.append("No target specified.")
        result.success = False
        return
    result.effect_kind = "sense_lie"
    result.effect_payload = {"margin": margin}
    parts.append(
        f"You weigh the truth of {target_char.name}'s words against the Force. "
        f"(Margin: {margin})"
    )


def _resolve_farseeing(result: ForcePowerResult, char: Character, parts: list):
    """A glimpse beyond the present. R&E p114.

    Parser side: a simple portent tied to real nearby danger (rich, scripted
    visions are tracked for a later wave — G5).
    """
    result.effect_kind = "farseeing"
    parts.append(
        "You still your mind and let the Force show you what it will. "
        "Images rise, half-formed."
    )


def _resolve_danger_sense(result: ForcePowerResult, char: Character, parts: list):
    """Premonition of imminent threat. R&E p114.

    Parser side: in combat this lets the Jedi react first (an initiative
    reroll, keeping the better); out of combat it is an early warning.
    """
    result.effect_kind = "danger_sense"
    parts.append(
        "Your senses sharpen — the Force tugs at the edge of your awareness, "
        "alert to danger before it strikes."
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


def _resolve_fall_check(
    char: Character,
    skill_reg: SkillRegistry,
    weight_difficulty_mod: int = 0,
) -> bool:
    """
    R&E p118: At DSP >= 6, roll Willpower vs (DSP × 3).
    Returns True if the character resists the fall.

    WoW.3c (May 24 2026): ``weight_difficulty_mod`` is added to the
    base ``DSP × 3`` difficulty per ``weight_of_war_design_v1.md``
    §7.1. Values come from
    ``engine.weight_of_war.dsp_resistance_modifier(weight)`` —
    0 / +2 / +5 / +10 by Weight tier. The caller is responsible
    for reading the character's Weight and computing the modifier;
    this function just adds it to the difficulty so the fall-check
    log line cleanly shows the contributing components.
    """
    willpower_pool = char.get_skill_pool("willpower", skill_reg)
    roll = roll_d6_pool(willpower_pool)
    base_difficulty = char.dark_side_points * 3
    difficulty = base_difficulty + int(weight_difficulty_mod or 0)
    success = roll.total >= difficulty
    if weight_difficulty_mod:
        log.info(
            f"[force] fall check {char.name}: willpower "
            f"{roll.total} vs {difficulty} "
            f"(DSP={char.dark_side_points} → base {base_difficulty}, "
            f"+{weight_difficulty_mod} from Weight) "
            f"→ {'RESIST' if success else 'FALL'}"
        )
    else:
        log.info(
            f"[force] fall check {char.name}: willpower {roll.total} "
            f"vs {difficulty} (DSP={char.dark_side_points}) → "
            f"{'RESIST' if success else 'FALL'}"
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
