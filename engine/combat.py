# -*- coding: utf-8 -*-
"""
D6 Personal Combat Engine (R&E 2nd Edition Faithful).

Manages combat state, initiative, action declaration/resolution,
attack vs defense, damage vs soak, and wound application.

Combat flow per round:
  1. Initiative: all combatants roll Perception
  2. Declaration: each combatant declares actions
  3. Resolution: actions resolve in initiative order
  4. Cleanup: stunned timers tick, fleeing characters exit

Key R&E mechanics implemented:
  - Melee vs ranged defense distinction (parry vs dodge)
  - Lightsaber skill used for both attack AND parry (GMH p126)
  - Full dodge/parry: entire round dedicated to defense, adds to
    difficulty for ALL incoming attacks (R&E p61)
  - Normal dodge/parry: counts as an action, player chooses whether
    to use roll or keep original difficulties (R&E p61)
  - Brawling parry vs melee parry with appropriate modifiers:
    * Unarmed vs armed attacker: +10 to attacker's roll (R&E p58)
    * Armed parry vs unarmed attacker: +5 to parry roll (R&E p58)

All rolls use the D6 dice engine. This module is pure logic - no I/O.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from engine.dice import (
    DicePool, roll_d6_pool, difficulty_check, opposed_roll,
    apply_multi_action_penalty, apply_wound_penalty,
    roll_cp_dice, apply_force_point,
)
from engine.character import Character, SkillRegistry, ATTRIBUTE_NAMES, WoundLevel
from engine.weapons import RangeBand, WeaponData, get_weapon_registry

log = logging.getLogger(__name__)


# ── Skill Classification ──
# Per R&E: dodge defends against ranged attacks; melee parry / brawling
# parry / lightsaber defends against melee attacks.

RANGED_SKILLS = {
    "blaster", "bowcaster", "firearms", "blaster artillery",
    "bows", "grenade", "missile weapons", "vehicle blasters",
}

MELEE_SKILLS = {
    "melee combat", "brawling", "lightsaber",
}

# Skills that serve as BOTH attack and parry (per GMH p126 ruling)
SELF_PARRY_SKILLS = {
    "lightsaber",  # "The lightsaber skill is used for attacks and parries"
}


def is_ranged_skill(skill: str) -> bool:
    """Check if a combat skill is ranged (uses dodge for defense)."""
    return skill.lower() in RANGED_SKILLS


def is_melee_skill(skill: str) -> bool:
    """Check if a combat skill is melee (uses parry for defense)."""
    return skill.lower() in MELEE_SKILLS


def get_defense_skill(attack_skill: str, defender: Character,
                      skill_reg: SkillRegistry) -> tuple[str, DicePool]:
    """
    Determine the appropriate defensive skill pool for a defender
    based on what type of attack is incoming.

    Returns (skill_name, pool).

    R&E rules:
      - Ranged attacks -> dodge
      - Melee weapon attacks -> melee parry (or lightsaber if wielding one)
      - Brawling attacks -> brawling parry
    """
    atk = attack_skill.lower()

    if atk in RANGED_SKILLS:
        return "dodge", defender.get_skill_pool("dodge", skill_reg)

    if atk == "brawling":
        return "brawling parry", defender.get_skill_pool("brawling parry", skill_reg)

    if atk == "lightsaber":
        # Defender can parry with lightsaber if they have one, else melee parry
        ls_pool = defender.get_skill_pool("lightsaber", skill_reg)
        mp_pool = defender.get_skill_pool("melee parry", skill_reg)
        if ls_pool.total_pips() > mp_pool.total_pips():
            return "lightsaber", ls_pool
        return "melee parry", mp_pool

    # Default melee: melee parry, but check if defender has lightsaber
    # (a Jedi can parry any melee attack with their lightsaber)
    if atk in ("melee combat",) or atk in MELEE_SKILLS:
        ls_pool = defender.get_skill_pool("lightsaber", skill_reg)
        mp_pool = defender.get_skill_pool("melee parry", skill_reg)
        if ls_pool.total_pips() > mp_pool.total_pips():
            return "lightsaber", ls_pool
        return "melee parry", mp_pool

    # Unknown skill type - fall back to dodge
    return "dodge", defender.get_skill_pool("dodge", skill_reg)


# ── Action Types ──

class ActionType(Enum):
    ATTACK = auto()
    DODGE = auto()        # Normal dodge (counts as action, multi-action penalty)
    FULL_DODGE = auto()   # Full dodge (whole round, adds to all difficulties)
    PARRY = auto()        # Normal parry (counts as action)
    FULL_PARRY = auto()   # Full parry (whole round)
    AIM = auto()
    FLEE = auto()
    COVER = auto()        # Take cover (costs action, uses room's cover_max)
    USE_ITEM = auto()
    FORCE_POWER = auto()
    OTHER = auto()


# ── Cover System (R&E p60) ──
# Cover levels and their dice bonus added to difficulty
# Also defines protection Strength if shot hits cover

COVER_NONE = 0
COVER_QUARTER = 1    # +1D to difficulty
COVER_HALF = 2       # +2D to difficulty
COVER_THREE_QUARTER = 3  # +3D to difficulty
COVER_FULL = 4       # Can't be hit directly; must destroy cover first

COVER_DICE = {
    0: 0,   # no cover
    1: 1,   # +1D
    2: 2,   # +2D
    3: 3,   # +3D
    4: 0,   # Full cover = can't be targeted
}

COVER_NAMES = {
    0: "None",
    1: "1/4 Cover",
    2: "1/2 Cover",
    3: "3/4 Cover",
    4: "Full Cover",
}

# Room property key for max cover available
# Set by builders via @set #room = cover_max:<level>
# e.g. properties: {"cover_max": 2}  means 1/2 cover available


@dataclass
class CombatAction:
    """A declared action for one round."""
    action_type: ActionType
    skill: str = ""           # Skill used (blaster, dodge, melee combat, etc.)
    target_id: int = 0        # Target combatant ID (for attacks)
    weapon_damage: str = ""   # Weapon damage dice (e.g. "4D")
    weapon_key: str = ""      # Key into WeaponRegistry (e.g. "blaster_pistol")
    cp_spend: int = 0         # Character Points to spend on this action
    description: str = ""     # Flavor text


@dataclass
class ActionResult:
    """Result of resolving one action."""
    actor_id: int
    action: CombatAction
    success: bool = False
    roll_display: str = ""      # What the actor rolled
    defense_display: str = ""   # What the defender rolled (if applicable)
    damage_display: str = ""    # Damage roll (if hit)
    soak_display: str = ""      # Soak roll (if hit)
    wound_inflicted: str = ""   # Wound level name (if any)
    margin: int = 0
    narrative: str = ""         # Human-readable summary


# ── Combatant State ──

@dataclass
class Combatant:
    """Tracks a character's state within a combat instance."""
    id: int                      # Character DB id
    name: str = ""
    is_npc: bool = False
    initiative: int = 0
    actions: list[CombatAction] = field(default_factory=list)
    aim_bonus: int = 0           # Accumulated aim dice (max +3D)
    is_fleeing: bool = False
    has_acted: bool = False
    force_point_active: bool = False  # R&E p52: doubles all dice this round
    cover_level: int = 0         # 0=none, 1=quarter, 2=half, 3=three_quarter, 4=full

    # Cached character data for the combat
    char: Optional[Character] = None


# ── Combat Instance ──

class CombatPhase(Enum):
    INITIATIVE = auto()
    DECLARATION = auto()
    RESOLUTION = auto()
    CLEANUP = auto()
    ENDED = auto()


@dataclass
class CombatEvent:
    """A log entry for combat narration."""
    text: str
    targets: list[int] = field(default_factory=list)  # Character IDs who should see this


class CombatInstance:
    """
    Manages one combat encounter in a room.

    Usage:
        combat = CombatInstance(room_id, skill_reg)
        combat.add_combatant(char_obj)
        events = combat.roll_initiative()
        # Players declare actions...
        combat.declare_action(char_id, action)
        # When all declared:
        events = combat.resolve_round()
    """

    def __init__(self, room_id: int, skill_reg: SkillRegistry,
                 default_range: RangeBand = RangeBand.SHORT,
                 cover_max: int = COVER_NONE):
        self.room_id = room_id
        self.skill_reg = skill_reg
        self.round_num = 0
        self.phase = CombatPhase.INITIATIVE
        self.combatants: dict[int, Combatant] = {}
        self.initiative_order: list[int] = []
        self.events: list[CombatEvent] = []
        # Range tracking: default band for all pairs, overridable per-pair
        self.default_range = default_range
        self._range_overrides: dict[tuple[int, int], RangeBand] = {}
        # Cover: max level available in this room (set by builder)
        self.cover_max = cover_max

    def set_range(self, id_a: int, id_b: int, band: RangeBand):
        """Set the range band between two combatants."""
        key = (min(id_a, id_b), max(id_a, id_b))
        self._range_overrides[key] = band

    def get_range(self, id_a: int, id_b: int) -> RangeBand:
        """Get the range band between two combatants."""
        key = (min(id_a, id_b), max(id_a, id_b))
        return self._range_overrides.get(key, self.default_range)

    def add_combatant(self, char: Character) -> Combatant:
        """Add a character to combat."""
        c = Combatant(
            id=char.id,
            name=char.name,
            char=char,
        )
        self.combatants[char.id] = c
        return c

    def remove_combatant(self, char_id: int):
        """Remove a character from combat."""
        self.combatants.pop(char_id, None)
        self.initiative_order = [i for i in self.initiative_order if i != char_id]

    def get_combatant(self, char_id: int) -> Optional[Combatant]:
        return self.combatants.get(char_id)

    @property
    def active_combatants(self) -> list[Combatant]:
        return [c for c in self.combatants.values()
                if c.char and c.char.wound_level.can_act and not c.is_fleeing]

    @property
    def is_over(self) -> bool:
        """Combat ends when 0 or 1 active combatants remain."""
        return len(self.active_combatants) <= 1

    # ── Initiative ──

    def roll_initiative(self) -> list[CombatEvent]:
        """Roll initiative for all combatants. Returns narration events."""
        self.round_num += 1
        self.phase = CombatPhase.DECLARATION
        events = []
        events.append(CombatEvent(
            text=f"--- COMBAT ROUND {self.round_num} ---"
        ))

        for c in self.combatants.values():
            if not c.char or not c.char.wound_level.can_act:
                c.initiative = 0
                continue

            pool = c.char.get_skill_pool("perception", self.skill_reg)
            pool = apply_wound_penalty(pool, c.char.wound_level.penalty_dice)
            result = roll_d6_pool(pool)
            c.initiative = result.total
            c.actions = []
            c.has_acted = False

            events.append(CombatEvent(
                text=f"  {c.name} rolls initiative: {result.display()}",
                targets=[c.id],
            ))

        # Sort by initiative (highest first)
        self.initiative_order = sorted(
            self.combatants.keys(),
            key=lambda cid: self.combatants[cid].initiative,
            reverse=True,
        )

        order_text = ", ".join(
            f"{self.combatants[cid].name}({self.combatants[cid].initiative})"
            for cid in self.initiative_order
            if self.combatants[cid].char and self.combatants[cid].char.wound_level.can_act
        )
        events.append(CombatEvent(text=f"  Order: {order_text}"))

        return events

    # ── Declaration ──

    def declare_force_point(self, char_id: int) -> Optional[str]:
        """
        Declare Force Point usage for this round.
        Per R&E p52: doubles all die codes for the round.
        Must be declared during declaration phase.
        Cannot be used same round as Character Points.

        Returns error string or None on success.
        """
        c = self.combatants.get(char_id)
        if not c:
            return "Not in combat."
        if not c.char:
            return "No character data."
        if c.char.force_points <= 0:
            return "You have no Force Points to spend."
        if c.force_point_active:
            return "Force Point already declared this round."
        # Check for CP usage on any declared action
        if any(a.cp_spend > 0 for a in c.actions):
            return "Cannot use a Force Point in the same round as Character Points."

        c.force_point_active = True
        c.char.force_points -= 1
        return None

    def declare_action(self, char_id: int, action: CombatAction) -> Optional[str]:
        """
        Declare an action for a combatant.
        Returns an error string if invalid, None on success.

        R&E validation:
          - Full dodge/parry: must be the ONLY action (no other actions allowed)
          - Can't mix full dodge and full parry
          - Declared dodge is an action even if nobody shoots at you (GMH p126)
          - Can't spend CP and FP in the same round (R&E p55)
          - Must have enough CP to spend
        """
        c = self.combatants.get(char_id)
        if not c:
            return "Not in combat."
        if not c.char or not c.char.wound_level.can_act:
            return "You can't act in your current condition."

        # Full dodge/parry restrictions
        is_full = action.action_type in (ActionType.FULL_DODGE, ActionType.FULL_PARRY)
        has_full = any(
            a.action_type in (ActionType.FULL_DODGE, ActionType.FULL_PARRY)
            for a in c.actions
        )

        if is_full and c.actions:
            return "Full dodge/parry must be your only action this round."
        if has_full:
            return "You've declared a full defense -- no other actions this round."

        # CP/FP mutual exclusion (R&E p55)
        if action.cp_spend > 0:
            if c.force_point_active:
                return "Cannot spend Character Points in the same round as a Force Point."
            if action.cp_spend > c.char.character_points:
                return f"Not enough Character Points (have {c.char.character_points}, want {action.cp_spend})."

        c.actions.append(action)
        return None

    def clear_actions(self, char_id: int):
        """Clear all declared actions for a combatant."""
        c = self.combatants.get(char_id)
        if c:
            c.actions = []

    def all_declared(self) -> bool:
        """Check if all active combatants have declared at least one action."""
        for c in self.active_combatants:
            if not c.actions:
                return False
        return True

    def undeclared_combatants(self) -> list[Combatant]:
        """Get combatants who haven't declared yet."""
        return [c for c in self.active_combatants if not c.actions]

    # ── Resolution ──

    def resolve_round(self) -> list[CombatEvent]:
        """
        Resolve all declared actions in initiative order.
        Returns narration events.
        """
        self.phase = CombatPhase.RESOLUTION
        events = []

        for char_id in self.initiative_order:
            c = self.combatants.get(char_id)
            if not c or not c.char or not c.char.wound_level.can_act:
                continue
            if c.is_fleeing:
                continue

            num_actions = len(c.actions)
            if num_actions == 0:
                continue

            for action in c.actions:
                result = self._resolve_action(c, action, num_actions)
                events.append(CombatEvent(
                    text=result.narrative,
                    targets=list(self.combatants.keys()),
                ))

            c.has_acted = True

        # Cleanup phase
        cleanup_events = self._cleanup()
        events.extend(cleanup_events)

        # Check if combat is over
        if self.is_over:
            events.append(CombatEvent(text="--- COMBAT ENDED ---"))
            self.phase = CombatPhase.ENDED
        else:
            self.phase = CombatPhase.INITIATIVE

        return events

    def _resolve_action(self, actor: Combatant, action: CombatAction,
                        num_actions: int) -> ActionResult:
        """Resolve a single action."""
        if action.action_type == ActionType.ATTACK:
            return self._resolve_attack(actor, action, num_actions)
        elif action.action_type in (ActionType.DODGE, ActionType.FULL_DODGE):
            return self._resolve_dodge(actor, action, num_actions)
        elif action.action_type in (ActionType.PARRY, ActionType.FULL_PARRY):
            return self._resolve_parry(actor, action, num_actions)
        elif action.action_type == ActionType.AIM:
            return self._resolve_aim(actor, action)
        elif action.action_type == ActionType.FLEE:
            return self._resolve_flee(actor, action, num_actions)
        elif action.action_type == ActionType.COVER:
            return self._resolve_cover(actor, action)
        else:
            return ActionResult(
                actor_id=actor.id, action=action,
                narrative=f"  {actor.name} does something.",
            )

    def _resolve_attack(self, actor: Combatant, action: CombatAction,
                        num_actions: int) -> ActionResult:
        """
        Resolve an attack per R&E 2nd Edition rules.

        RANGED attacks (R&E p58-59):
          1. Base difficulty = weapon range band (PB:5, Short:10, Med:15, Long:20)
          2. If defender declared dodge: roll dodge, ADD to difficulty
          3. Attacker rolls skill vs total difficulty -> difficulty_check
          This is NOT an opposed roll.

        MELEE attacks:
          Opposed roll: attacker skill vs parry/brawling parry/lightsaber
          Lightsaber skill serves as both attack and parry (GMH p126)

        R&E melee modifiers:
          - Unarmed defender vs armed attacker: +10 to attacker (R&E p58)
          - Armed defender vs unarmed attacker: +5 to parry roll (R&E p58)
        """
        target_c = self.combatants.get(action.target_id)
        if not target_c or not target_c.char:
            return ActionResult(
                actor_id=actor.id, action=action,
                narrative=f"  {actor.name} attacks... but the target is gone.",
            )

        char = actor.char
        target = target_c.char
        atk_skill = action.skill.lower()
        ranged = is_ranged_skill(atk_skill)
        melee = is_melee_skill(atk_skill)

        # Build attacker's pool
        attack_pool = char.get_skill_pool(action.skill, self.skill_reg)
        attack_pool = apply_wound_penalty(attack_pool, char.wound_level.penalty_dice)
        attack_pool = apply_multi_action_penalty(attack_pool, num_actions)

        # Force Point: double all dice (R&E p52)
        if actor.force_point_active:
            attack_pool = apply_force_point(attack_pool)

        # Add aim bonus
        if actor.aim_bonus > 0:
            attack_pool = DicePool(attack_pool.dice + actor.aim_bonus, attack_pool.pips)
            actor.aim_bonus = 0

        # ── Find defender's defensive action ──
        defense_action = None
        if target_c.actions:
            for a in target_c.actions:
                if ranged and a.action_type in (
                    ActionType.DODGE, ActionType.FULL_DODGE
                ):
                    defense_action = a
                    break
                elif melee and a.action_type in (
                    ActionType.PARRY, ActionType.FULL_PARRY
                ):
                    defense_action = a
                    break

        # ═══════════════════════════════════════
        # RANGED ATTACK -- Difficulty-based (R&E)
        # ═══════════════════════════════════════
        if ranged:
            return self._resolve_ranged_attack(
                actor, target_c, action, attack_pool, defense_action, num_actions
            )

        # ═══════════════════════════════════════
        # MELEE ATTACK -- Opposed roll
        # ═══════════════════════════════════════
        return self._resolve_melee_attack(
            actor, target_c, action, attack_pool, defense_action, num_actions
        )

    def _resolve_ranged_attack(
        self, actor: Combatant, target_c: Combatant,
        action: CombatAction, attack_pool: DicePool,
        defense_action: Optional[CombatAction], num_actions: int,
    ) -> ActionResult:
        """
        Ranged attack resolution per R&E p58-60.

        1. Base difficulty from weapon range band
        2. Dodge roll ADDS to difficulty (not opposed)
        3. Cover ADDS dice to difficulty (R&E p60)
        4. Attacker rolls vs total difficulty
        5. Attacking from cover degrades cover to 1/4
        """
        target = target_c.char

        # Determine range band and base difficulty
        range_band = self.get_range(actor.id, target_c.id)
        base_difficulty = int(range_band)  # 5/10/15/20
        range_label = range_band.label

        if range_band == RangeBand.OUT_OF_RANGE:
            return ActionResult(
                actor_id=actor.id, action=action, success=False,
                narrative=(
                    f"  {actor.name} attacks {target_c.name} with {action.skill} "
                    f"-- target is OUT OF RANGE!"
                ),
            )

        # Full cover check -- can't be targeted directly
        if target_c.cover_level >= COVER_FULL:
            return ActionResult(
                actor_id=actor.id, action=action, success=False,
                narrative=(
                    f"  {actor.name} fires at {target_c.name} but they're in "
                    f"FULL COVER -- must eliminate cover first!"
                ),
            )

        # Attacking from cover degrades it to 1/4 (peeking out)
        if actor.cover_level > COVER_QUARTER:
            actor.cover_level = COVER_QUARTER

        # Calculate dodge bonus
        dodge_bonus = 0
        dodge_text = ""
        if defense_action:
            is_full = defense_action.action_type == ActionType.FULL_DODGE
            dodge_pool = target.get_skill_pool("dodge", self.skill_reg)
            dodge_pool = apply_wound_penalty(dodge_pool, target.wound_level.penalty_dice)
            if not is_full:
                dodge_pool = apply_multi_action_penalty(dodge_pool, len(target_c.actions))

            # Force Point doubles dodge too
            if target_c.force_point_active:
                dodge_pool = apply_force_point(dodge_pool)

            dodge_roll = roll_d6_pool(dodge_pool)
            dodge_bonus = dodge_roll.total
            dodge_text = f" + Dodge {dodge_bonus}"

        # Calculate cover bonus (R&E p60)
        cover_bonus = 0
        cover_text = ""
        if target_c.cover_level > 0:
            cover_dice = COVER_DICE.get(target_c.cover_level, 0)
            if cover_dice > 0:
                cover_roll = roll_d6_pool(DicePool(cover_dice, 0))
                cover_bonus = cover_roll.total
                cover_text = f" + Cover({COVER_NAMES[target_c.cover_level]}) {cover_bonus}"

        total_difficulty = base_difficulty + dodge_bonus + cover_bonus

        # Roll attack vs difficulty
        attack_roll = roll_d6_pool(attack_pool)
        attack_total = attack_roll.total

        # Character Point spending (R&E p55)
        cp_text = ""
        if action.cp_spend > 0 and actor.char:
            cp_bonus, cp_rolls = roll_cp_dice(action.cp_spend)
            attack_total += cp_bonus
            actor.char.character_points -= action.cp_spend
            cp_text = f" +CP({'+'.join(str(r) for r in cp_rolls)}={cp_bonus})"

        hit = attack_total >= total_difficulty

        diff_display = f"{range_label}({base_difficulty}){dodge_text}{cover_text} = {total_difficulty}"

        if not hit:
            return ActionResult(
                actor_id=actor.id, action=action, success=False,
                roll_display=attack_roll.display(),
                defense_display=diff_display,
                margin=total_difficulty - attack_total,
                narrative=(
                    f"  {actor.name} fires at {target_c.name} with {action.skill} "
                    f"and MISSES! "
                    f"(Roll: {attack_total}{cp_text} vs Diff: {diff_display})"
                    f"{' [FORCE POINT]' if actor.force_point_active else ''}"
                ),
            )

        # ── HIT! Damage vs soak ──
        return self._apply_damage(
            actor, target_c, action, attack_total, diff_display, cp_text
        )

    def _resolve_melee_attack(
        self, actor: Combatant, target_c: Combatant,
        action: CombatAction, attack_pool: DicePool,
        defense_action: Optional[CombatAction], num_actions: int,
    ) -> ActionResult:
        """
        Melee attack resolution -- opposed roll per R&E.
        Attacker skill vs parry/brawling parry/lightsaber.
        """
        target = target_c.char
        atk_skill = action.skill.lower()

        # Build defense pool
        def_skill_name = ""
        def_pool = DicePool(0, 0)
        melee_modifier = 0

        if defense_action:
            is_full = defense_action.action_type == ActionType.FULL_PARRY
            def_skill_name, def_pool = get_defense_skill(
                atk_skill, target, self.skill_reg
            )
            def_pool = apply_wound_penalty(def_pool, target.wound_level.penalty_dice)
            if not is_full:
                def_pool = apply_multi_action_penalty(def_pool, len(target_c.actions))

            # R&E melee modifiers
            atk_is_armed = atk_skill in ("melee combat", "lightsaber")
            def_is_armed = def_skill_name in ("melee parry", "lightsaber")

            if not def_is_armed and atk_is_armed:
                melee_modifier = 10  # +10 to attacker vs unarmed defender
            elif def_is_armed and atk_skill == "brawling":
                def_pool = DicePool(def_pool.dice, def_pool.pips + 5)  # +5 to armed parry vs unarmed
        else:
            def_pool = target.get_attribute("dexterity")

        if melee_modifier > 0:
            attack_pool = DicePool(attack_pool.dice, attack_pool.pips + melee_modifier)

        result = opposed_roll(attack_pool, def_pool)
        def_label = def_skill_name.title() if def_skill_name else "DEX"

        # Character Point spending (R&E p55): add dice after seeing roll
        attack_total = result.attacker_roll.total
        cp_text = ""
        if action.cp_spend > 0 and actor.char:
            cp_bonus, cp_rolls = roll_cp_dice(action.cp_spend)
            attack_total += cp_bonus
            actor.char.character_points -= action.cp_spend
            cp_text = f" +CP({'+'.join(str(r) for r in cp_rolls)}={cp_bonus})"

        attacker_wins = attack_total > result.defender_roll.total

        if not attacker_wins:
            return ActionResult(
                actor_id=actor.id, action=action, success=False,
                roll_display=result.attacker_roll.display(),
                defense_display=result.defender_roll.display(),
                margin=result.defender_roll.total - attack_total,
                narrative=(
                    f"  {actor.name} strikes at {target_c.name} with {action.skill} "
                    f"and MISSES! "
                    f"(Attack: {attack_total}{cp_text} vs "
                    f"{def_label}: {result.defender_roll.total})"
                    f"{' [FORCE POINT]' if actor.force_point_active else ''}"
                ),
            )

        # ── HIT! ──
        return self._apply_damage(
            actor, target_c, action,
            attack_total,
            f"{def_label}: {result.defender_roll.total}",
            cp_text,
        )

    def _apply_damage(
        self, actor: Combatant, target_c: Combatant,
        action: CombatAction, attack_total: int, defense_display: str,
        cp_text: str = "",
    ) -> ActionResult:
        """Common damage/soak resolution for both ranged and melee hits."""
        target = target_c.char

        # Parse damage - handle STR+XD notation for melee weapons
        damage_str = action.weapon_damage or "3D"
        if damage_str.upper().startswith("STR"):
            # Melee: STR+2D means attacker's Strength + bonus dice
            str_pool = actor.char.get_attribute("strength")
            # Force Point: double STR but NOT weapon bonus (R&E p52)
            if actor.force_point_active:
                str_pool = apply_force_point(str_pool)
            bonus_str = damage_str.upper().replace("STR", "").strip()
            if bonus_str.startswith("+"):
                bonus_str = bonus_str[1:]
            if bonus_str:
                bonus_pool = DicePool.parse(bonus_str)
                damage_pool = DicePool(
                    str_pool.dice + bonus_pool.dice,
                    str_pool.pips + bonus_pool.pips,
                )
            else:
                damage_pool = str_pool
        else:
            damage_pool = DicePool.parse(damage_str)
            # Force Point: double weapon damage for ranged
            if actor.force_point_active:
                damage_pool = apply_force_point(damage_pool)

        soak_pool = target.get_attribute("strength")

        damage_roll = roll_d6_pool(damage_pool)
        soak_roll = roll_d6_pool(soak_pool)
        damage_margin = damage_roll.total - soak_roll.total

        wound = target.apply_wound(damage_margin)
        wound_text = wound.display_name if damage_margin > 0 else "No Damage"

        verb = "fires at" if is_ranged_skill(action.skill) else "strikes"
        fp_tag = " [FORCE POINT]" if actor.force_point_active else ""
        narrative = (
            f"  {actor.name} {verb} {target_c.name} with {action.skill} "
            f"and HITS! "
            f"(Roll: {attack_total}{cp_text} vs {defense_display}) "
            f"Damage: {damage_roll.total} vs Soak: {soak_roll.total} "
            f"-> {wound_text}{fp_tag}"
        )

        if not target.wound_level.can_act:
            narrative += f" -- {target_c.name} is {wound.display_name}!"

        return ActionResult(
            actor_id=actor.id, action=action, success=True,
            roll_display=str(attack_total),
            defense_display=defense_display,
            damage_display=damage_roll.display(),
            soak_display=soak_roll.display(),
            wound_inflicted=wound_text,
            margin=damage_margin,
            narrative=narrative,
        )

    def _resolve_dodge(self, actor: Combatant, action: CombatAction,
                       num_actions: int) -> ActionResult:
        """Dodge is passive - it's applied when attacked. Just note it."""
        if action.action_type == ActionType.FULL_DODGE:
            return ActionResult(
                actor_id=actor.id, action=action,
                narrative=f"  {actor.name} is doing a FULL dodge this round (no other actions).",
            )
        return ActionResult(
            actor_id=actor.id, action=action,
            narrative=f"  {actor.name} is dodging this round.",
        )

    def _resolve_parry(self, actor: Combatant, action: CombatAction,
                       num_actions: int) -> ActionResult:
        """Parry is passive - it's applied when attacked in melee. Just note it."""
        # Determine what skill they're parrying with
        skill_name = action.skill or "melee parry"

        # If they have lightsaber skill and it's higher, note that
        if not action.skill:
            ls_pool = actor.char.get_skill_pool("lightsaber", self.skill_reg)
            mp_pool = actor.char.get_skill_pool("melee parry", self.skill_reg)
            bp_pool = actor.char.get_skill_pool("brawling parry", self.skill_reg)
            if ls_pool.total_pips() > mp_pool.total_pips() and ls_pool.total_pips() > bp_pool.total_pips():
                skill_name = "lightsaber"
            elif mp_pool.total_pips() >= bp_pool.total_pips():
                skill_name = "melee parry"
            else:
                skill_name = "brawling parry"

        if action.action_type == ActionType.FULL_PARRY:
            return ActionResult(
                actor_id=actor.id, action=action,
                narrative=f"  {actor.name} is doing a FULL parry with {skill_name} this round.",
            )
        return ActionResult(
            actor_id=actor.id, action=action,
            narrative=f"  {actor.name} is parrying with {skill_name} this round.",
        )

    def _resolve_aim(self, actor: Combatant, action: CombatAction) -> ActionResult:
        """Aim grants +1D to next attack (max +3D over multiple rounds)."""
        actor.aim_bonus = min(actor.aim_bonus + 1, 3)
        return ActionResult(
            actor_id=actor.id, action=action,
            narrative=f"  {actor.name} takes aim... (+{actor.aim_bonus}D to next attack)",
        )

    def _resolve_cover(self, actor: Combatant, action: CombatAction) -> ActionResult:
        """
        Take cover. Per R&E p60:
          - Cover level limited by room's cover_max
          - Attacking from cover reduces cover to 1/4 (peeking out)
          - Full cover: can't be hit directly, but also can't attack

        Cover persists across rounds until the combatant attacks or moves.
        """
        requested = COVER_HALF  # default
        # The action description may contain a requested level
        if action.description:
            desc = action.description.lower()
            if "full" in desc:
                requested = COVER_FULL
            elif "3/4" in desc or "three" in desc:
                requested = COVER_THREE_QUARTER
            elif "1/2" in desc or "half" in desc:
                requested = COVER_HALF
            elif "1/4" in desc or "quarter" in desc:
                requested = COVER_QUARTER

        # Clamp to room's maximum
        actual = min(requested, self.cover_max)

        if actual <= 0:
            return ActionResult(
                actor_id=actor.id, action=action,
                narrative=f"  {actor.name} looks for cover but there's nothing to hide behind!",
            )

        actor.cover_level = actual
        return ActionResult(
            actor_id=actor.id, action=action,
            narrative=(
                f"  {actor.name} takes {COVER_NAMES[actual]}! "
                f"(+{COVER_DICE.get(actual, 0)}D to ranged difficulty)"
            ),
        )

    def _resolve_flee(self, actor: Combatant, action: CombatAction,
                      num_actions: int) -> ActionResult:
        """Attempt to flee. Opposed roll vs highest-initiative enemy."""
        # Find the highest-initiative opponent
        opponents = [c for c in self.active_combatants if c.id != actor.id]
        if not opponents:
            actor.is_fleeing = True
            return ActionResult(
                actor_id=actor.id, action=action, success=True,
                narrative=f"  {actor.name} flees combat!",
            )

        blocker = max(opponents, key=lambda c: c.initiative)

        flee_pool = actor.char.get_skill_pool("running", self.skill_reg)
        flee_pool = apply_wound_penalty(flee_pool, actor.char.wound_level.penalty_dice)
        flee_pool = apply_multi_action_penalty(flee_pool, num_actions)

        block_pool = blocker.char.get_skill_pool("running", self.skill_reg)
        block_pool = apply_wound_penalty(block_pool, blocker.char.wound_level.penalty_dice)

        result = opposed_roll(flee_pool, block_pool)

        if result.attacker_wins:
            actor.is_fleeing = True
            return ActionResult(
                actor_id=actor.id, action=action, success=True,
                roll_display=result.attacker_roll.display(),
                narrative=f"  {actor.name} escapes from combat! ({result.attacker_roll.total} vs {result.defender_roll.total})",
            )
        else:
            return ActionResult(
                actor_id=actor.id, action=action, success=False,
                roll_display=result.attacker_roll.display(),
                narrative=f"  {actor.name} tries to flee but {blocker.name} blocks the escape! ({result.attacker_roll.total} vs {result.defender_roll.total})",
            )

    def _cleanup(self) -> list[CombatEvent]:
        """
        End-of-round cleanup per R&E 2nd Edition.

        - Force Point flag resets
        - Stun timers tick (-1D penalty for 2 rounds per R&E p59)
        - Mortally wounded death roll: roll 2D each round,
          die if roll < rounds_MW (R&E p59)
        - Fled combatants removed
        """
        events = []

        # Reset Force Point flag (only lasts one round)
        for c in self.combatants.values():
            if c.force_point_active:
                c.force_point_active = False

        # Tick stun timers (R&E p59: -1D for rest of round + next round)
        for c in self.combatants.values():
            if c.char and c.char.stun_rounds > 0:
                c.char.stun_rounds -= 1
                if c.char.stun_rounds <= 0:
                    # Stun penalty expired
                    if c.char.wound_level == WoundLevel.STUNNED:
                        c.char.wound_level = WoundLevel.HEALTHY
                        c.char.stun_count = 0
                        events.append(CombatEvent(
                            text=f"  {c.name} shakes off the stun."
                        ))

        # Mortally wounded death rolls (R&E p59)
        for c in list(self.combatants.values()):
            if c.char and c.char.wound_level == WoundLevel.MORTALLY_WOUNDED:
                c.char.mortally_wounded_rounds += 1
                rounds_mw = c.char.mortally_wounded_rounds
                death_roll = roll_d6_pool(DicePool(2, 0))
                if death_roll.total < rounds_mw:
                    c.char.wound_level = WoundLevel.DEAD
                    events.append(CombatEvent(
                        text=(
                            f"  {c.name} succumbs to mortal wounds! "
                            f"(Death roll: {death_roll.total} < {rounds_mw} rounds) "
                            f"-- {c.name} is DEAD."
                        ),
                    ))
                else:
                    events.append(CombatEvent(
                        text=(
                            f"  {c.name} clings to life... "
                            f"(Death roll: {death_roll.total} vs {rounds_mw} rounds)"
                        ),
                    ))

        # Remove fled combatants
        fled = [c for c in self.combatants.values() if c.is_fleeing]
        for c in fled:
            events.append(CombatEvent(text=f"  {c.name} has fled the area."))
            self.remove_combatant(c.id)

        return events

    def get_status(self) -> list[str]:
        """Get a status summary of all combatants."""
        lines = [f"--- Combat Round {self.round_num} ---"]
        for cid in self.initiative_order:
            c = self.combatants.get(cid)
            if not c:
                continue
            wound_str = ""
            if c.char and c.char.wound_level > WoundLevel.HEALTHY:
                wound_str = f" [{c.char.wound_level.display_name}]"
            declared = "READY" if c.actions else "waiting..."
            aim_str = f" (aiming +{c.aim_bonus}D)" if c.aim_bonus > 0 else ""
            fp_str = " [FP!]" if c.force_point_active else ""
            cover_str = f" [{COVER_NAMES[c.cover_level]}]" if c.cover_level > 0 else ""
            cp_str = ""
            if c.char:
                cp_str = f" CP:{c.char.character_points} FP:{c.char.force_points}"
            lines.append(
                f"  {c.name:20s} Init:{c.initiative:3d}{wound_str}{cover_str}{aim_str}{fp_str}{cp_str}  {declared}"
            )
        return lines
