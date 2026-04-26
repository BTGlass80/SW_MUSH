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
from server import ansi as _ansi

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
    stun_mode: bool = False   # v22: weapon set to stun — caps result at unconscious
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
    you_narrative: str = ""     # Per-session variant for the target (◆ YOU got hit)
    targets: list = None        # Character IDs of targets (for per-session delivery)


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

    # v22 audit #8: dodge rolled once per round, cached here.
    # None = not yet rolled this round.  Cleared at round start.
    dodge_roll_cached: Optional[int] = None

    # v22 audit #12: defender pre-declares CP to spend on soak.
    # If hit, these CP dice are added to the soak roll.
    # If not hit, CP are not spent.  Max 5 per R&E.
    soak_cp: int = 0

    # Cached character data for the combat
    char: Optional[Character] = None


# ── Combat Instance ──

def _wound_color(wound_text: str) -> str:
    """Return ANSI-colored wound outcome string."""
    wl = wound_text.lower()
    if wl == "no damage":
        return _ansi.color(wound_text, _ansi.DIM)
    if wl == "stunned":
        return _ansi.color(wound_text, _ansi.YELLOW)
    if wl == "wounded":
        return _ansi.color(wound_text, _ansi.BRIGHT_YELLOW)
    if wl == "wounded twice":
        return _ansi.BOLD + _ansi.color(wound_text, _ansi.BRIGHT_YELLOW) + _ansi.RESET
    if wl == "incapacitated":
        return _ansi.color(wound_text, _ansi.BRIGHT_RED)
    if wl in ("mortally wounded", "dead"):
        return _ansi.BOLD + _ansi.color(wound_text, _ansi.BRIGHT_RED) + _ansi.RESET
    return wound_text


# ── Narrative variety pools ──────────────────────────────────────────────

_VERB_POOLS: dict[str, list[str]] = {
    # ranged
    "blaster":          ["fires at", "shoots at", "blasts at", "takes a shot at"],
    "bowcaster":        ["fires at", "looses a bolt at", "shoots at"],
    "firearms":         ["fires at", "shoots at", "squeezes off a shot at"],
    "blaster artillery":["fires at", "unleashes a barrage at"],
    "missile weapons":  ["fires a missile at", "launches at"],
    "grenade":          ["hurls a grenade at", "lobs at"],
    # melee
    "melee combat":     ["swings at", "slashes at", "thrusts at", "jabs at"],
    "brawling":         ["punches at", "throws a fist at", "swings at", "lunges at"],
    "lightsaber":       ["slashes at", "swings at", "lunges at", "strikes at"],
}
_VERB_RANGED_DEFAULT = ["fires at", "shoots at"]
_VERB_MELEE_DEFAULT  = ["swings at", "strikes at"]

_MISS_FLAVOR_CLOSE = [
    "barely misses!", "the shot goes just wide!",
    "grazes the air!", "skims past!",
]
_MISS_FLAVOR_WIDE = [
    "misses wildly!", "the shot sails well past!",
    "goes wide by a mile!", "fails to connect!",
]
_MISS_FLAVOR_MELEE_CLOSE = [
    "barely misses!", "the strike glances off!",
    "almost connects!", "scrapes past!",
]
_MISS_FLAVOR_MELEE_WIDE = [
    "misses badly!", "the blow falls short!",
    "swings wide!", "fails to connect!",
]

_WOUND_DRAMA: dict[str, list[str]] = {
    "wounded twice":    [
        "staggers, struggling to stay on their feet.",
        "is badly hurt — still fighting but barely.",
        "grits through the pain and keeps going.",
    ],
    "incapacitated":    [
        "collapses, unable to continue.",
        "goes down hard.",
        "is out of the fight.",
    ],
    "mortally wounded": [
        "crumples, clinging to life by a thread.",
        "falls — it does not look good.",
        "is mortally wounded and fading fast.",
    ],
}


def _pick_verb(skill: str, seed: int) -> str:
    """Pick an attack verb for a skill, seeded for reproducibility."""
    pool = _VERB_POOLS.get(skill.lower())
    if pool is None:
        pool = _VERB_RANGED_DEFAULT if is_ranged_skill(skill) else _VERB_MELEE_DEFAULT
    return pool[seed % len(pool)]


def _miss_flavor(margin: int, ranged: bool) -> str:
    """Return a short miss descriptor based on how badly the roll missed."""
    if ranged:
        pool = _MISS_FLAVOR_CLOSE if margin <= 3 else _MISS_FLAVOR_WIDE
    else:
        pool = _MISS_FLAVOR_MELEE_CLOSE if margin <= 3 else _MISS_FLAVOR_MELEE_WIDE
    return pool[margin % len(pool)]


def _wound_drama(wound_text: str, target_name: str, seed: int) -> str:
    """Return an optional drama beat for severe wounds, or empty string."""
    pool = _WOUND_DRAMA.get(wound_text.lower())
    if not pool:
        return ""
    return f"  {target_name} {pool[seed % len(pool)]}"


class CombatPhase(Enum):
    INITIATIVE = auto()
    DECLARATION = auto()
    RESOLUTION = auto()
    POSING = auto()       # Players writing narrative poses (post-resolution)
    CLEANUP = auto()
    ENDED = auto()


@dataclass
class CombatEvent:
    """A log entry for combat narration."""
    text: str
    targets: list[int] = field(default_factory=list)  # Character IDs who should see this
    you_text: str = ""  # Per-session variant shown to the target (◆ YOU got hit format)


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
                 cover_max: int = COVER_NONE,
                 theatre: str = "ground"):
        # Drop D server-side prereq (Field Kit v2 §6): theatre tags this
        # combat instance as 'ground' or 'space' so the client can pick
        # the correct HUD overlay (amber datapad vs cyan cockpit). Today
        # CombatInstance is only used by parser/combat_commands.py (ground);
        # space resolution lives in parser/space_commands.py with its own
        # space_state payload. Default is 'ground' to match current usage.
        self.room_id = room_id
        self.skill_reg = skill_reg
        self.theatre = theatre
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
        # ── Pose-state tracking (v2 posing system) ──
        # Populated by resolve_round(), keyed by char_id
        self._round_results: dict[int, list[ActionResult]] = {}
        # Populated when posing window opens, keyed by char_id
        # Each value: {"status": "pending"|"ready"|"passed",
        #              "text": str|None, "initiative": int}
        self._pose_state: dict[int, dict] = {}
        # Handle for the async grace-timer task (set by command layer)
        self._grace_timer_handle = None
        # ISO timestamp deadline for pose window (set by command layer)
        self.pose_deadline: Optional[str] = None

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
        """Roll initiative for all combatants. Returns summary events.

        Per-combatant roll details are stored in self._last_initiative_rolls
        for display via the 'combat rolls' command.
        """
        self.round_num += 1
        self.phase = CombatPhase.DECLARATION
        self._last_initiative_rolls = {}  # {name: roll_display_str}
        events = []

        # Round header: compact separator
        sep = _ansi.BOLD + f"  ─── ROUND {self.round_num} ───────────────────────────────────" + _ansi.RESET
        events.append(CombatEvent(text=sep))

        for c in self.combatants.values():
            if not c.char or not c.char.wound_level.can_act:
                c.initiative = 0
                self._last_initiative_rolls[c.name] = "0 (incapacitated)"
                continue

            pool = c.char.get_attribute("perception")
            pool = apply_wound_penalty(pool, c.char.total_penalty_dice)
            result = roll_d6_pool(pool)
            c.initiative = result.total
            c.actions = []
            c.has_acted = False
            c.dodge_roll_cached = None  # v22: clear dodge cache for new round
            c.soak_cp = 0              # v22: clear soak CP for new round
            self._last_initiative_rolls[c.name] = result.display()

        # Sort by initiative (highest first)
        self.initiative_order = sorted(
            self.combatants.keys(),
            key=lambda cid: self.combatants[cid].initiative,
            reverse=True,
        )

        # Single summary line: Name (init) -> Name (init) -> ...
        order_parts = [
            f"{self.combatants[cid].name} ({self.combatants[cid].initiative})"
            for cid in self.initiative_order
            if self.combatants[cid].char and self.combatants[cid].char.wound_level.can_act
        ]
        order_text = f" → ".join(order_parts)
        events.append(CombatEvent(
            text=f"  Turn order: {order_text}"
        ))

        return events

    # ── HUD Serialization ──

    def to_hud_dict(self, viewer_id: int | None = None) -> dict:
        """Serialize combat state for WebSocket clients.

        Args:
            viewer_id: Character ID of the requesting session.
                       Used to populate your_actions / waiting_for
                       from that player's perspective.

        Returns a plain dict safe for json.dumps().
        """
        combatants_data = []
        for cid in self.initiative_order:
            c = self.combatants.get(cid)
            if not c:
                continue
            wound_lvl = c.char.wound_level.value if c.char else 0
            wound_name = c.char.wound_level.display_name if c.char else "unknown"
            action_summary = None
            if c.actions:
                first = c.actions[0]
                if first.action_type == ActionType.ATTACK and first.target_id:
                    tgt = self.combatants.get(first.target_id)
                    tgt_name = tgt.name if tgt else "target"
                    action_summary = f"attack {tgt_name}"
                else:
                    action_summary = first.description or first.action_type.name.lower()
            combatants_data.append({
                "id": cid,
                "name": c.name,
                "is_player": not c.is_npc,
                "wound_level": wound_lvl,
                "wound_name": wound_name,
                "initiative": c.initiative,
                "declared": bool(c.actions),
                "action_summary": action_summary,
                "pose_status": self._pose_state.get(cid, {}).get("status"),
                "cover": c.cover_level,
                "aim_bonus": c.aim_bonus,
                "is_fleeing": c.is_fleeing,
            })

        # Add any combatants not yet in initiative order (new joiners)
        for cid, c in self.combatants.items():
            if cid not in self.initiative_order:
                wound_lvl = c.char.wound_level.value if c.char else 0
                wound_name = c.char.wound_level.display_name if c.char else "unknown"
                combatants_data.append({
                    "id": cid,
                    "name": c.name,
                    "is_player": not c.is_npc,
                    "wound_level": wound_lvl,
                    "wound_name": wound_name,
                    "initiative": 0,
                    "declared": bool(c.actions),
                    "action_summary": None,
                    "cover": c.cover_level,
                    "aim_bonus": c.aim_bonus,
                    "is_fleeing": c.is_fleeing,
                })

        # Viewer-specific fields
        your_actions: list[str] = []
        waiting_for: list[str] = []

        if viewer_id is not None:
            vc = self.combatants.get(viewer_id)
            if vc:
                for a in vc.actions:
                    if a.action_type == ActionType.ATTACK and a.target_id:
                        tgt = self.combatants.get(a.target_id)
                        tgt_name = tgt.name if tgt else "target"
                        skill = a.skill or "blaster"
                        your_actions.append(f"attack {tgt_name} with {skill}")
                    elif a.description:
                        your_actions.append(a.description)
                    else:
                        your_actions.append(a.action_type.name.lower().replace("_", " "))

        for c in self.undeclared_combatants():
            if c.id != viewer_id:
                waiting_for.append(c.name)

        return {
            "active": True,
            "round": self.round_num,
            "phase": self.phase.name.lower(),
            "theatre": self.theatre,
            "combatants": combatants_data,
            "your_actions": your_actions,
            "waiting_for": waiting_for,
            "pose_deadline": self.pose_deadline,
        }

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
            c.dodge_roll_cached = None  # v22: re-declare means re-roll

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

        Side effects:
          - Populates self._round_results with per-combatant ActionResult lists
          - Initialises self._pose_state for the posing window
        """
        self.phase = CombatPhase.RESOLUTION
        events = []
        self._round_results = {}

        # Also track incoming actions per target for briefings
        self._incoming_results: dict[int, list[ActionResult]] = {}

        for char_id in self.initiative_order:
            c = self.combatants.get(char_id)
            if not c or not c.char or not c.char.wound_level.can_act:
                continue
            if c.is_fleeing:
                continue

            num_actions = len(c.actions)
            if num_actions == 0:
                continue

            actor_results = []
            for action in c.actions:
                result = self._resolve_action(c, action, num_actions)
                actor_results.append(result)
                # targets: only the actual hit target sees the ◆ YOU variant.
                # Using all combatants was causing the attacker to see their
                # own strike as "YOU take a hit from yourself".
                hit_targets = result.targets if result.targets else []
                events.append(CombatEvent(
                    text=result.narrative,
                    you_text=result.you_narrative,
                    targets=hit_targets,
                ))
                # Track as incoming for the target
                if action.target_id and action.target_id in self.combatants:
                    self._incoming_results.setdefault(
                        action.target_id, []
                    ).append(result)

            self._round_results[char_id] = actor_results
            c.has_acted = True

        # Cleanup phase
        cleanup_events = self._cleanup()
        events.extend(cleanup_events)

        # Initialise pose state for all active combatants
        self._pose_state = {}
        for c in self.combatants.values():
            if c.char and c.char.wound_level.can_act and not c.is_fleeing:
                self._pose_state[c.id] = {
                    "status": "pending",
                    "text": None,
                    "initiative": c.initiative,
                }

        # Check if combat is over
        if self.is_over:
            events.append(CombatEvent(text="--- COMBAT ENDED ---"))
            self.phase = CombatPhase.ENDED
        else:
            # Don't advance to INITIATIVE yet — command layer drives
            # the posing window before the next round starts
            self.phase = CombatPhase.POSING

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
          2. If defender declared normal dodge: dodge roll REPLACES base difficulty
             If defender declared full dodge: dodge roll ADDS to base difficulty
             Dodge is rolled ONCE per round, cached on Combatant (v22)
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
        attack_pool = apply_wound_penalty(attack_pool, char.total_penalty_dice)
        attack_pool = apply_multi_action_penalty(attack_pool, num_actions)

        # v22: armor Dexterity penalty applies to all combat skills
        armor_dex_pen = char.get_armor_dex_penalty()
        if not armor_dex_pen.is_zero():
            attack_pool = apply_wound_penalty(attack_pool, armor_dex_pen.dice)

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

        # Calculate dodge effect (v22 audit #7, #8)
        #
        # R&E rules:
        #   Normal dodge: dodge roll REPLACES the base difficulty.
        #     "The roll is the attacker's new difficulty number."
        #     A bad roll can make you easier to hit.
        #   Full dodge:   dodge roll ADDS to the base difficulty.
        #     "The character can also add the dodge roll to the
        #      difficulty of being hit."
        #   Both: rolled ONCE, applies to all attacks of that type
        #     for the rest of the round (cached on Combatant).
        #
        dodge_bonus = 0
        dodge_replaces = False  # True for normal dodge (replaces base)
        dodge_text = ""
        if defense_action:
            is_full = defense_action.action_type == ActionType.FULL_DODGE

            # Use cached dodge roll if already rolled this round
            if target_c.dodge_roll_cached is not None:
                dodge_value = target_c.dodge_roll_cached
            else:
                # Roll dodge once for the round
                dodge_pool = target.get_skill_pool("dodge", self.skill_reg)
                dodge_pool = apply_wound_penalty(dodge_pool, target.total_penalty_dice)
                if not is_full:
                    dodge_pool = apply_multi_action_penalty(dodge_pool, len(target_c.actions))

                # v22: armor Dexterity penalty
                armor_dex_pen = target.get_armor_dex_penalty()
                if not armor_dex_pen.is_zero():
                    dodge_pool = apply_wound_penalty(dodge_pool, armor_dex_pen.dice)

                # Force Point doubles dodge too
                if target_c.force_point_active:
                    dodge_pool = apply_force_point(dodge_pool)

                dodge_roll = roll_d6_pool(dodge_pool)
                dodge_value = dodge_roll.total
                target_c.dodge_roll_cached = dodge_value

            if is_full:
                # Full dodge: ADDS to base difficulty
                dodge_bonus = dodge_value
                dodge_text = f" + FullDodge {dodge_value}"
            else:
                # Normal dodge: REPLACES base difficulty
                dodge_replaces = True
                dodge_text = f" → Dodge {dodge_value}"

        # Calculate cover bonus (R&E p60)
        cover_bonus = 0
        cover_text = ""
        if target_c.cover_level > 0:
            cover_dice = COVER_DICE.get(target_c.cover_level, 0)
            if cover_dice > 0:
                cover_roll = roll_d6_pool(DicePool(cover_dice, 0))
                cover_bonus = cover_roll.total
                cover_text = f" + Cover({COVER_NAMES[target_c.cover_level]}) {cover_bonus}"

        # Compute total difficulty
        # Normal dodge: dodge_value REPLACES base_difficulty, then cover adds
        # Full dodge: dodge_bonus ADDS to base_difficulty, then cover adds
        # No dodge: just base_difficulty + cover
        if dodge_replaces:
            total_difficulty = dodge_value + cover_bonus
        else:
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
            _miss_margin = total_difficulty - attack_total
            _rseed = (getattr(self, "round_num", 0) * 31 + actor.id) & 0xFFFF
            _rverb = _pick_verb(action.skill, _rseed)
            fp_tag = " [FORCE POINT]" if actor.force_point_active else ""
            flavor = _miss_flavor(_miss_margin, ranged=True)
            story = (
                _ansi.DIM
                + f"  {actor.name} {_rverb} {target_c.name}"
                + f" with {action.skill} — {flavor}{fp_tag}"
                + _ansi.RESET
            )
            mech = _ansi.color(
                f"    (Roll: {attack_total}{cp_text} vs Diff: {diff_display})",
                _ansi.DIM,
            )
            return ActionResult(
                actor_id=actor.id, action=action, success=False,
                roll_display=attack_roll.display(),
                defense_display=diff_display,
                margin=_miss_margin,
                narrative=story + "\n" + mech,
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
        melee_def_modifier = 0

        if defense_action:
            is_full = defense_action.action_type == ActionType.FULL_PARRY
            def_skill_name, def_pool = get_defense_skill(
                atk_skill, target, self.skill_reg
            )
            def_pool = apply_wound_penalty(def_pool, target.total_penalty_dice)
            if not is_full:
                def_pool = apply_multi_action_penalty(def_pool, len(target_c.actions))

            # v22: armor Dexterity penalty on parry
            armor_dex_pen = target.get_armor_dex_penalty()
            if not armor_dex_pen.is_zero():
                def_pool = apply_wound_penalty(def_pool, armor_dex_pen.dice)

            # R&E melee modifiers — these are FLAT bonuses to the roll
            # total, NOT pips added to the DicePool (which normalizes pips
            # into dice: +10 pips → +3D+1, which is wrong).
            # v22 audit #15 fix.
            atk_is_armed = atk_skill in ("melee combat", "lightsaber")
            def_is_armed = def_skill_name in ("melee parry", "lightsaber")

            if not def_is_armed and atk_is_armed:
                melee_modifier = 10  # +10 flat to attacker vs unarmed defender
            elif def_is_armed and atk_skill == "brawling":
                melee_def_modifier = 5  # +5 flat to armed parry vs unarmed attacker
        else:
            # v22 audit #16: no declared defense → attacker rolls against
            # the weapon's listed difficulty, NOT opposed Dexterity.
            # R&E p82: "Each melee weapon has a different difficulty number."
            def_pool = None  # Signal: use difficulty check, not opposed roll
            _weapon_diff_str = ""
            if action.weapon_key:
                from engine.weapons import get_weapon_registry
                _wr = get_weapon_registry()
                _wpn = _wr.get(action.weapon_key)
                if _wpn:
                    _weapon_diff_str = _wpn.melee_difficulty
            # Map difficulty name to number (R&E canonical)
            _DIFF_MAP = {"very easy": 5, "easy": 10, "moderate": 15,
                         "difficult": 20, "very difficult": 25, "heroic": 30}
            melee_base_difficulty = _DIFF_MAP.get(_weapon_diff_str.lower(), 15)  # default Moderate

        if def_pool is not None:
            # Opposed roll (defender declared parry)
            result = opposed_roll(attack_pool, def_pool)
            def_label = def_skill_name.title() if def_skill_name else "DEX"

            # Apply flat melee modifiers to roll totals (NOT to pools)
            attack_total = result.attacker_roll.total + melee_modifier
            def_total = result.defender_roll.total + melee_def_modifier
        else:
            # Difficulty check (no declared defense)
            from engine.dice import difficulty_check
            check = difficulty_check(attack_pool, melee_base_difficulty)
            def_label = f"Diff({_weapon_diff_str.title() or 'Moderate'})"
            attack_total = check.roll.total
            def_total = melee_base_difficulty
            # Create a fake opposed result for downstream code compatibility
            result = type('OpposedFake', (), {
                'attacker_roll': check.roll,
                'defender_roll': type('FakeRoll', (), {
                    'total': melee_base_difficulty,
                    'display': lambda self: f"[{melee_base_difficulty}]",
                })(),
            })()
        cp_text = ""
        if action.cp_spend > 0 and actor.char:
            cp_bonus, cp_rolls = roll_cp_dice(action.cp_spend)
            attack_total += cp_bonus
            actor.char.character_points -= action.cp_spend
            cp_text = f" +CP({'+'.join(str(r) for r in cp_rolls)}={cp_bonus})"

        attacker_wins = attack_total > def_total

        if not attacker_wins:
            _miss_margin = def_total - attack_total
            _mseed = (getattr(self, "round_num", 0) * 31 + actor.id) & 0xFFFF
            _mverb = _pick_verb(action.skill, _mseed)
            fp_tag = " [FORCE POINT]" if actor.force_point_active else ""
            flavor = _miss_flavor(_miss_margin, ranged=False)
            story = (
                _ansi.DIM
                + f"  {actor.name} {_mverb} {target_c.name}"
                + f" with {action.skill} — {flavor}{fp_tag}"
                + _ansi.RESET
            )
            mech = _ansi.color(
                f"    (Attack: {attack_total}{cp_text} vs"
                f" {def_label}: {def_total})",
                _ansi.DIM,
            )
            return ActionResult(
                actor_id=actor.id, action=action, success=False,
                roll_display=result.attacker_roll.display(),
                defense_display=result.defender_roll.display(),
                margin=_miss_margin,
                narrative=story + "\n" + mech,
            )

        # ── HIT! ──
        return self._apply_damage(
            actor, target_c, action,
            attack_total,
            f"{def_label}: {def_total}",
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
        # v22 audit #9: armor adds to Strength for soak per R&E p83
        is_energy = not damage_str.upper().startswith("STR")  # ranged = energy, melee = physical
        armor_pool = target.get_armor_protection(energy=is_energy)
        if not armor_pool.is_zero():
            soak_pool = soak_pool + armor_pool
        # v22 audit #10: wound penalty applies to soak roll per R&E
        soak_pool = apply_wound_penalty(soak_pool, target.total_penalty_dice)

        damage_roll = roll_d6_pool(damage_pool)
        soak_roll = roll_d6_pool(soak_pool)
        soak_total = soak_roll.total

        # v22 audit #12: defender CP spending on soak per R&E p55
        # "Five to increase a Strength roll to resist damage."
        # CP declared at action time via `dodge cp 3` / `soak 2`.
        # Only spent if actually hit. Dice explode on 6, no mishap on 1.
        soak_cp_text = ""
        if target_c.soak_cp > 0 and target_c.char:
            cp_to_spend = min(target_c.soak_cp, target_c.char.character_points, 5)
            if cp_to_spend > 0:
                from engine.dice import roll_cp_dice
                soak_cp_bonus, soak_cp_rolls = roll_cp_dice(cp_to_spend)
                soak_total += soak_cp_bonus
                target_c.char.character_points -= cp_to_spend
                soak_cp_text = f" +CP({'+'.join(str(r) for r in soak_cp_rolls)}={soak_cp_bonus})"

        damage_margin = damage_roll.total - soak_total

        # v22 audit #11: stun damage routing per R&E p83
        # "Weapons set for stun roll damage normally, but treat any result
        #  more serious than 'stunned' as 'unconscious for 2D minutes.'"
        stun_knocked_out = False
        if action.stun_mode and damage_margin > 3:
            # Margin > 3 would normally be wounded or worse;
            # stun caps it at "unconscious for 2D minutes"
            stun_knocked_out = True
            # Apply as STUNNED wound level but set incapacitated state
            target.apply_wound(1)  # Apply a stun (margin 1 = stunned)
            wound_text = "Stunned — Unconscious!"
        elif damage_margin > 0:
            wound = target.apply_wound(damage_margin)
            wound_text = wound.display_name
        else:
            wound_text = "No Damage"

        # Verb variety seeded on round + actor id for reproducibility
        _seed = (getattr(self, "round_num", 0) * 31 + actor.id) & 0xFFFF
        verb = _pick_verb(action.skill, _seed)
        fp_tag = " [FORCE POINT]" if actor.force_point_active else ""

        # 2-line narrative: story (bold) + mechanics (dim)
        colored_wound = _wound_color(wound_text)
        outcome_tag = "HIT — " + colored_wound + "!"

        story_line = (
            _ansi.BOLD
            + f"  ▸ {actor.name} {verb} {target_c.name}"
            + f" with {action.skill} — {outcome_tag}"
            + fp_tag
            + _ansi.RESET
        )
        mech_line = _ansi.color(
            f"    (Roll: {attack_total}{cp_text} vs {defense_display}"
            f" · Damage {damage_roll.total} vs Soak {soak_total}{soak_cp_text}"
            f" → {wound_text})",
            _ansi.DIM,
        )
        narrative = story_line + "\n" + mech_line

        # Wound escalation drama for severe wounds
        drama = _wound_drama(wound_text, target_c.name, _seed)
        if drama:
            narrative += "\n" + _ansi.color(drama, _ansi.DIM)

        if not target.wound_level.can_act:
            incap_line = (
                _ansi.BOLD + _ansi.BRIGHT_RED
                + f"  {target_c.name} is {wound.display_name.upper()}!"
                + _ansi.RESET
            )
            narrative += "\n" + incap_line

        # Per-session YOU variant — shown only to the target player
        you_story = (
            _ansi.BOLD + _ansi.BRIGHT_RED
            + f"  ◆ YOU take a hit from {actor.name}"
            + f" with {action.skill} — {outcome_tag}"
            + fp_tag
            + _ansi.RESET
        )
        you_narrative = you_story + "\n" + mech_line
        if drama:
            you_narrative += "\n" + _ansi.color(drama, _ansi.DIM)
        if not target.wound_level.can_act:
            you_narrative += "\n" + (
                _ansi.BOLD + _ansi.BRIGHT_RED
                + "  YOU are " + wound.display_name.upper() + "!"
                + _ansi.RESET
            )

        return ActionResult(
            actor_id=actor.id, action=action, success=True,
            roll_display=str(attack_total),
            defense_display=defense_display,
            damage_display=damage_roll.display(),
            soak_display=soak_roll.display(),
            wound_inflicted=wound_text,
            margin=damage_margin,
            narrative=narrative,
            you_narrative=you_narrative,
            targets=[target_c.id],
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
        flee_pool = apply_wound_penalty(flee_pool, actor.char.total_penalty_dice)
        flee_pool = apply_multi_action_penalty(flee_pool, num_actions)

        block_pool = blocker.char.get_skill_pool("running", self.skill_reg)
        block_pool = apply_wound_penalty(block_pool, blocker.char.total_penalty_dice)

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

        # Tick stun timers — v22 audit #13: per-stun expiry
        # Each stun has its own countdown. Remove expired ones individually.
        for c in self.combatants.values():
            if c.char and c.char.stun_timers:
                c.char.stun_timers = [t - 1 for t in c.char.stun_timers]
                expired = c.char.stun_timers.count(0) + sum(1 for t in c.char.stun_timers if t < 0)
                c.char.stun_timers = [t for t in c.char.stun_timers if t > 0]
                if expired > 0 and not c.char.stun_timers:
                    # All stuns expired — clear STUNNED wound level
                    if c.char.wound_level == WoundLevel.STUNNED:
                        c.char.wound_level = WoundLevel.HEALTHY
                        events.append(CombatEvent(
                            text=f"  {c.name} shakes off the stun."
                        ))
                elif expired > 0 and c.char.stun_timers:
                    remaining = len(c.char.stun_timers)
                    events.append(CombatEvent(
                        text=f"  {c.name}'s oldest stun fades ({remaining} stun{'s' if remaining != 1 else ''} still active)."
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

        # Remove dead combatants
        dead = [c for c in self.combatants.values()
                if c.char and c.char.wound_level == WoundLevel.DEAD]
        for c in dead:
            self.remove_combatant(c.id)

        return events

    # ── Pose-State Management (v2 Posing System) ──

    def set_pose_status(self, char_id: int, status: str,
                        text: Optional[str] = None):
        """Set a combatant's pose status.

        Args:
            char_id: Character DB id
            status:  "pending", "ready", or "passed"
            text:    The pose text (custom or auto-generated)
        """
        if char_id in self._pose_state:
            self._pose_state[char_id]["status"] = status
            if text is not None:
                self._pose_state[char_id]["text"] = text

    def get_pending_posers(self) -> list[Combatant]:
        """Return combatants still in 'pending' pose status."""
        result = []
        for cid, state in self._pose_state.items():
            if state["status"] == "pending":
                c = self.combatants.get(cid)
                if c:
                    result.append(c)
        return result

    def get_pending_poser_ids(self) -> list[int]:
        """Return character IDs of combatants still pending."""
        return [cid for cid, s in self._pose_state.items()
                if s["status"] == "pending"]

    def all_poses_in(self) -> bool:
        """True if no combatants are still 'pending'."""
        return all(
            s["status"] != "pending"
            for s in self._pose_state.values()
        )

    def get_sorted_poses(self) -> list[tuple[int, int, str]]:
        """Return (initiative, char_id, text) sorted by initiative desc.

        Used by _flush_action_log() in the command layer to emit the
        cinematic Action Log.
        """
        entries = []
        for cid, state in self._pose_state.items():
            text = state.get("text") or ""
            init = state.get("initiative", 0)
            entries.append((init, cid, text))
        entries.sort(key=lambda e: e[0], reverse=True)
        return entries

    def generate_auto_pose(self, char_id: int) -> str:
        """Generate a FLAVOR_MATRIX auto-pose for a combatant.

        Uses stored _round_results to pick the right verb/margin/wound.
        Falls back to a generic 'hesitates' pose if no results stored.
        """
        from engine.combat_flavor import (
            generate_auto_pose as _gen_pose,
            generate_pass_pose,
            generate_compound_npc_pose,
        )

        c = self.combatants.get(char_id)
        if not c:
            return "Someone acts."

        results = self._round_results.get(char_id, [])
        if not results:
            return generate_pass_pose(c.name)

        # Build one pose fragment per action result
        fragments = []
        for r in results:
            if r.action.action_type == ActionType.ATTACK:
                target_c = self.combatants.get(r.action.target_id)
                target_name = target_c.name if target_c else "the target"
                frag = _gen_pose(
                    char_name=c.name,
                    weapon_skill=r.action.skill,
                    target_name=target_name,
                    margin=r.margin if r.success else -abs(r.margin),
                    wound_result=r.wound_inflicted,
                    round_num=self.round_num,
                    combatant_id=char_id,
                )
                fragments.append(frag)
            elif r.action.action_type in (
                ActionType.DODGE, ActionType.FULL_DODGE
            ):
                fragments.append(f"{c.name} dodges incoming fire.")
            elif r.action.action_type in (
                ActionType.PARRY, ActionType.FULL_PARRY
            ):
                _parry_skill = (r.action.skill or "melee parry").lower()
                _parry_display = {
                    "melee parry": "a melee guard",
                    "brawling parry": "bare hands",
                    "lightsaber": "their lightsaber",
                }.get(_parry_skill, r.action.skill or "melee parry")
                fragments.append(
                    f"{c.name} braces, parrying with {_parry_display}."
                )
            elif r.action.action_type == ActionType.FLEE:
                if r.success:
                    fragments.append(f"{c.name} breaks away and flees!")
                else:
                    fragments.append(f"{c.name} tries to run but can't escape!")
            elif r.action.action_type == ActionType.AIM:
                fragments.append(f"{c.name} takes careful aim.")
            elif r.action.action_type == ActionType.COVER:
                fragments.append(f"{c.name} ducks behind cover.")
            else:
                fragments.append(f"{c.name} hesitates.")

        if len(fragments) == 1:
            return fragments[0]
        return generate_compound_npc_pose(c.name, fragments)

    def build_private_briefing(self, char_id: int) -> str:
        """Build a private briefing string for a player.

        Shows:
          - All of their declared actions and outcomes
          - All incoming actions targeting them
          - A prompt to write their pose

        Returns a multi-line string ready to send to the player session.
        """
        c = self.combatants.get(char_id)
        if not c:
            return ""

        lines = []
        lines.append("=" * 70)
        lines.append(f"{'ROUND ' + str(self.round_num) + ' : PRIVATE BRIEFING':^70}")
        lines.append("=" * 70)
        lines.append("")

        # ── YOUR ACTIONS ──
        my_results = self._round_results.get(char_id, [])
        num_actions = len(c.actions)
        penalty_note = ""
        if num_actions > 1:
            penalty_dice = num_actions - 1
            penalty_note = f" (Multi-Action Penalty: -{penalty_dice}D applied)"

        lines.append(f"▸ YOUR ACTIONS{penalty_note}:")
        if my_results:
            for i, r in enumerate(my_results, 1):
                action = r.action
                atype = action.action_type

                if atype == ActionType.ATTACK:
                    target_c = self.combatants.get(action.target_id)
                    tname = target_c.name if target_c else "target"
                    if r.success:
                        wound_info = r.wound_inflicted or "No Damage"
                        lines.append(
                            f"  {i}. Attack {tname} → "
                            + _ansi.BOLD + "HIT!" + _ansi.RESET
                            + f" (Rolled {r.roll_display} vs {r.defense_display})"
                        )
                        if wound_info != "No Damage":
                            lines.append(
                                f"     Result: Inflicted {wound_info}."
                            )
                        else:
                            lines.append(
                                f"     Result: No damage dealt."
                            )
                    else:
                        lines.append(
                            f"  {i}. Attack {tname} → MISS"
                            f" (Rolled {r.roll_display} vs {r.defense_display})"
                        )

                elif atype in (ActionType.DODGE, ActionType.FULL_DODGE):
                    label = "Full Dodge" if atype == ActionType.FULL_DODGE else "Dodge"
                    lines.append(
                        f"  {i}. {label} → Applied against incoming attacks"
                    )

                elif atype in (ActionType.PARRY, ActionType.FULL_PARRY):
                    label = "Full Parry" if atype == ActionType.FULL_PARRY else "Parry"
                    lines.append(
                        f"  {i}. {label} → Applied against melee attacks"
                    )

                elif atype == ActionType.AIM:
                    lines.append(
                        f"  {i}. Aim → +{c.aim_bonus}D to next attack"
                    )

                elif atype == ActionType.FLEE:
                    if r.success:
                        lines.append(f"  {i}. Flee → SUCCESS")
                    else:
                        lines.append(f"  {i}. Flee → BLOCKED")

                elif atype == ActionType.COVER:
                    lines.append(f"  {i}. Take cover → {action.description}")

                else:
                    lines.append(f"  {i}. {action.description or 'Pass'}")
        else:
            lines.append("  (No actions resolved)")

        # ── INCOMING ACTIONS ──
        incoming = self._incoming_results.get(char_id, [])
        lines.append("")
        lines.append("▸ INCOMING ACTIONS:")
        if incoming:
            for r in incoming:
                attacker_c = self.combatants.get(r.actor_id)
                aname = attacker_c.name if attacker_c else "Someone"
                if r.success:
                    wound = r.wound_inflicted or "No Damage"
                    lines.append(
                        f"  - {aname} attacked you → "
                        + _ansi.BOLD + "HIT" + _ansi.RESET
                    )
                    if wound != "No Damage":
                        lines.append(f"     You take: {wound}")
                else:
                    # Check if our dodge/parry helped
                    lines.append(f"  - {aname} attacked you → MISSED")
        else:
            lines.append("  - No attacks targeted you this round.")

        # ── PROMPT ──
        lines.append("")
        lines.append("-" * 70)

        # Build a hint for what to cover in their pose
        action_types = [a.action_type for a in c.actions]
        action_words = []
        for at in action_types:
            if at == ActionType.ATTACK:
                action_words.append("your attack")
            elif at in (ActionType.DODGE, ActionType.FULL_DODGE):
                action_words.append("your dodge")
            elif at in (ActionType.PARRY, ActionType.FULL_PARRY):
                action_words.append("your parry")
            elif at == ActionType.FLEE:
                action_words.append("your escape attempt")
            elif at == ActionType.AIM:
                action_words.append("taking aim")
            elif at == ActionType.COVER:
                action_words.append("taking cover")
        if action_words:
            hint = " and ".join(action_words)
            lines.append(
                _ansi.combat_msg(f"Write your pose covering {hint}.")
            )
        else:
            lines.append(_ansi.combat_msg("Write your pose for this round."))

        lines.append(
            _ansi.combat_msg(
                "Type 'pass' to use an auto-generated pose."
            )
        )
        lines.append("=" * 70)

        return "\n".join(lines)

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
