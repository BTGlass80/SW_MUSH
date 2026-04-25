"""
Starship Engine -- Star Wars D6 Revised & Expanded

Ship data loading, instance management, and space combat resolution.

R&E Space Combat (Chapter 10):
  - Starfighter scale vs Capital scale (6D difference)
  - Piloting: opposed Maneuverability rolls for positioning
  - Attack: Gunnery + Fire Control vs target's piloting
  - Damage: weapon damage vs Hull + Shields
  - Ion damage: disables systems rather than destroying hull
  - Range: Close/Short/Medium/Long/Extreme with difficulty modifiers
  - Fire arcs: front/rear/turret restrict which weapons can fire
  - Maneuvering: pilot actions to close/open range, speed advantage

Damage Control (adapted from Star Warriors Section 17):
  - Crew action: repair a damaged system mid-combat
  - Uses Technical + repair skill vs difficulty per system type
  - Systems track three states: working / damaged / destroyed
  - Destroyed systems are permanent -- no further repair possible
  - Hull patching reduces hull_damage incrementally
  - One repair attempt per system per round
"""
import logging
import os
import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

import yaml

from engine.dice import (
    DicePool, roll_d6_pool, opposed_roll,
    apply_multi_action_penalty, apply_wound_penalty,
)

log = logging.getLogger(__name__)


# -- Scale system (R&E p101) --
SCALE_STARFIGHTER = 0
SCALE_CAPITAL = 6


# -- Space Range Bands --
# R&E p101: range modifies attack difficulty

class SpaceRange(IntEnum):
    """Range bands for space combat with difficulty modifiers."""
    CLOSE = 0       # Point-blank dogfight range, +0 difficulty
    SHORT = 5       # Short range, +5 difficulty
    MEDIUM = 10     # Medium range, +10 difficulty
    LONG = 15       # Long range, +15 difficulty
    EXTREME = 25    # Extreme range, +25 difficulty
    OUT_OF_RANGE = 99

    @property
    def label(self) -> str:
        return {
            0: "Close", 5: "Short", 10: "Medium",
            15: "Long", 25: "Extreme", 99: "Out of Range",
        }[self.value]


# -- Relative Position (for fire arcs) --

class RelativePosition:
    """Where a target is relative to your ship."""
    FRONT = "front"
    REAR = "rear"
    FLANK = "flank"


def can_weapon_fire(weapon_arc: str, relative_pos: str) -> bool:
    """Check if a weapon's fire arc can reach the target's relative position."""
    arc = weapon_arc.lower()
    if "turret" in arc:
        return True  # Turrets fire in all directions
    if relative_pos == RelativePosition.FRONT:
        return "front" in arc or "all" in arc
    if relative_pos == RelativePosition.REAR:
        return "rear" in arc or "all" in arc
    if relative_pos == RelativePosition.FLANK:
        return "turret" in arc or "left" in arc or "right" in arc or "all" in arc
    return "front" in arc  # Default: front-facing


# -- Space Grid --
# Tracks pairwise range and relative position between all ships in a sector

# ── Evade Resolution ─────────────────────────────────────────────────────────

@dataclass
class EvadeResult:
    """Result of an evasive maneuver attempt."""
    success: bool = False
    roll_total: int = 0
    difficulty: int = 0
    all_tails_broken: bool = False
    narrative: str = ""


def resolve_evade(
    pilot_skill: DicePool,
    maneuverability: DicePool,
    engine_state: str = "working",
    num_actions: int = 1,
) -> EvadeResult:
    """
    Resolve an evasive maneuver roll (Persistent Tailing / Priority B).

    The pilot throws the ship into violent evasive maneuvers, attempting to
    break ALL tail locks simultaneously.  Uses pilot skill + ship maneuverability
    vs a Moderate (10) base difficulty.

    Engine damage modifiers (Star Warriors Section 17 adaptation):
      - 'damaged'   → +5 difficulty
      - 'destroyed' → impossible; auto-fail with flavour narrative

    On success, all position pairs involving this ship are reset to FRONT by
    the caller (EvadeCommand reads all_tails_broken and clears the SpaceGrid).
    """
    result = EvadeResult()

    # Destroyed engines: cannot maneuver at all
    if engine_state == "destroyed":
        result.narrative = (
            "  Engines destroyed — evasive maneuvers impossible! "
            "You're a sitting duck."
        )
        return result

    # Build difficulty
    base_diff = 10
    engine_penalty = 5 if engine_state == "damaged" else 0
    result.difficulty = base_diff + engine_penalty

    # Build pilot pool: skill + ship maneuverability
    pool = DicePool(
        pilot_skill.dice + maneuverability.dice,
        pilot_skill.pips + maneuverability.pips,
    )
    pool = apply_multi_action_penalty(pool, num_actions)

    roll = roll_d6_pool(pool)
    result.roll_total = roll.total

    engine_note = " (damaged engines +5)" if engine_penalty else ""
    diff_display = f"{result.difficulty}{engine_note}"

    if roll.total >= result.difficulty:
        result.success = True
        result.all_tails_broken = True
        result.narrative = (
            f"  Evasive maneuvers successful! All pursuit positions broken. "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )
    else:
        result.narrative = (
            f"  Evasive maneuvers failed — still being tailed! "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )

    return result


class SpaceGrid:
    """
    Manages spatial relationships between ships in space.

    Each pair of ships has:
      - range: SpaceRange (Close through Extreme)
      - relative_position: where the target is from the attacker's perspective

    Pilot maneuvers change these via opposed piloting rolls.
    Speed advantage: faster ship gets +1D per point of speed difference.
    """

    def __init__(self):
        # {(min_id, max_id): SpaceRange}
        self._ranges: dict[tuple[int, int], SpaceRange] = {}
        # {(attacker_id, target_id): RelativePosition}
        self._positions: dict[tuple[int, int], str] = {}
        # {ship_id: speed} for speed advantage calculations
        self._speeds: dict[int, int] = {}
        # {ship_id: int} — evasive maneuver bonus added to attacker difficulty this round
        # Consumed (zeroed) when first attack resolves against this ship
        self._maneuver_bonuses: dict[int, int] = {}
        # {(attacker_ship_id, target_ship_id): int} — targeting lock-on bonus (max +3D)
        # Consumed when fire resolves against the locked target
        self._lockon_bonuses: dict[tuple[int, int], int] = {}

    def add_ship(self, ship_id: int, speed: int, default_range: SpaceRange = SpaceRange.LONG):
        """Add a ship to the grid. New ships start at Long range from everyone."""
        self._speeds[ship_id] = speed
        for existing_id in list(self._speeds.keys()):
            if existing_id != ship_id:
                key = (min(ship_id, existing_id), max(ship_id, existing_id))
                if key not in self._ranges:
                    self._ranges[key] = default_range
                    # Random initial facing
                    self._positions[(ship_id, existing_id)] = RelativePosition.FRONT
                    self._positions[(existing_id, ship_id)] = RelativePosition.FRONT

    def remove_ship(self, ship_id: int):
        """Remove a ship from the grid."""
        self._speeds.pop(ship_id, None)
        to_remove = [k for k in self._ranges if ship_id in k]
        for k in to_remove:
            del self._ranges[k]
        to_remove_pos = [k for k in self._positions if ship_id in k]
        for k in to_remove_pos:
            del self._positions[k]
        # Clear any lock-on bonuses involving this ship
        to_remove_lock = [k for k in self._lockon_bonuses if ship_id in k]
        for k in to_remove_lock:
            del self._lockon_bonuses[k]

    def get_range(self, id_a: int, id_b: int) -> SpaceRange:
        key = (min(id_a, id_b), max(id_a, id_b))
        return self._ranges.get(key, SpaceRange.LONG)

    def set_range(self, id_a: int, id_b: int, rng: SpaceRange):
        key = (min(id_a, id_b), max(id_a, id_b))
        self._ranges[key] = rng

    def get_position(self, attacker_id: int, target_id: int) -> str:
        """Get where the target is relative to the attacker."""
        return self._positions.get(
            (attacker_id, target_id), RelativePosition.FRONT
        )

    def set_position(self, attacker_id: int, target_id: int, pos: str):
        self._positions[(attacker_id, target_id)] = pos

    def get_speed(self, ship_id: int) -> int:
        return self._speeds.get(ship_id, 5)

    def set_maneuver_bonus(self, ship_id: int, bonus: int):
        """Set an evasive maneuver difficulty bonus for this ship for the current round."""
        self._maneuver_bonuses[ship_id] = bonus

    def get_and_consume_maneuver_bonus(self, ship_id: int) -> int:
        """Return the maneuver bonus for this ship and zero it (one-shot per round)."""
        return self._maneuver_bonuses.pop(ship_id, 0)

    # ── Targeting Lock-On ──

    def add_lockon(self, attacker_ship_id: int, target_ship_id: int) -> int:
        """Increment lock-on bonus for attacker→target pair. Max +3D. Returns new total."""
        key = (attacker_ship_id, target_ship_id)
        current = self._lockon_bonuses.get(key, 0)
        new_val = min(current + 1, 3)
        self._lockon_bonuses[key] = new_val
        return new_val

    def get_and_consume_lockon(self, attacker_ship_id: int, target_ship_id: int) -> int:
        """Return lock-on bonus for attacker→target and consume it (one-shot)."""
        return self._lockon_bonuses.pop((attacker_ship_id, target_ship_id), 0)

    def get_lockon(self, attacker_ship_id: int, target_ship_id: int) -> int:
        """Peek at current lock-on bonus without consuming."""
        return self._lockon_bonuses.get((attacker_ship_id, target_ship_id), 0)

    def clear_lockon_by_target(self, target_ship_id: int):
        """Clear ALL lock-on bonuses aimed at this target (called on evasive maneuver)."""
        to_remove = [k for k in self._lockon_bonuses if k[1] == target_ship_id]
        for k in to_remove:
            del self._lockon_bonuses[k]

    def clear_lockon_by_attacker(self, attacker_ship_id: int):
        """Clear all lock-on bonuses FROM this attacker (called when switching targets)."""
        to_remove = [k for k in self._lockon_bonuses if k[0] == attacker_ship_id]
        for k in to_remove:
            del self._lockon_bonuses[k]

    def resolve_maneuver(
        self,
        pilot_id: int,
        pilot_skill: DicePool,
        pilot_maneuverability: DicePool,
        pilot_speed: int,
        target_id: int,
        target_pilot_skill: DicePool,
        target_maneuverability: DicePool,
        target_speed: int,
        action: str,  # "close", "flee", "tail", "outmaneuver"
    ) -> tuple[bool, str]:
        """
        Resolve a pilot maneuver via opposed piloting rolls.

        Speed advantage: +1D per point of speed difference to the faster ship.

        Actions:
          close: reduce range by one band
          flee:  increase range by one band
          tail:  get behind target (change relative position to REAR)
          outmaneuver: force target to lose their position advantage

        Returns (success, narrative)
        """
        # Build pilot pools
        pool_a = DicePool(
            pilot_skill.dice + pilot_maneuverability.dice,
            pilot_skill.pips + pilot_maneuverability.pips,
        )
        pool_b = DicePool(
            target_pilot_skill.dice + target_maneuverability.dice,
            target_pilot_skill.pips + target_maneuverability.pips,
        )

        # Speed advantage
        speed_diff = pilot_speed - target_speed
        if speed_diff > 0:
            pool_a = DicePool(pool_a.dice + speed_diff, pool_a.pips)
        elif speed_diff < 0:
            pool_b = DicePool(pool_b.dice + abs(speed_diff), pool_b.pips)

        result = opposed_roll(pool_a, pool_b)
        current_range = self.get_range(pilot_id, target_id)

        if action == "close":
            if not result.attacker_wins:
                return False, (
                    f"Failed to close range! "
                    f"(Pilot: {result.attacker_roll.total} "
                    f"vs Evade: {result.defender_roll.total}) "
                    f"Range remains {current_range.label}."
                )
            # Reduce range by one band
            new_range = self._closer_range(current_range)
            self.set_range(pilot_id, target_id, new_range)
            return True, (
                f"Closing in! Range shifts from {current_range.label} to "
                f"{new_range.label}. "
                f"(Pilot: {result.attacker_roll.total} "
                f"vs Evade: {result.defender_roll.total})"
            )

        elif action == "flee":
            if not result.attacker_wins:
                return False, (
                    f"Failed to break away! "
                    f"(Pilot: {result.attacker_roll.total} "
                    f"vs Pursuit: {result.defender_roll.total}) "
                    f"Range remains {current_range.label}."
                )
            new_range = self._farther_range(current_range)
            self.set_range(pilot_id, target_id, new_range)
            if new_range == SpaceRange.OUT_OF_RANGE:
                return True, (
                    f"Escaped to hyperspace range! "
                    f"(Pilot: {result.attacker_roll.total} "
                    f"vs Pursuit: {result.defender_roll.total})"
                )
            return True, (
                f"Breaking away! Range shifts from {current_range.label} to "
                f"{new_range.label}. "
                f"(Pilot: {result.attacker_roll.total} "
                f"vs Pursuit: {result.defender_roll.total})"
            )

        elif action == "tail":
            if not result.attacker_wins:
                return False, (
                    f"Failed to get on their tail! "
                    f"(Pilot: {result.attacker_roll.total} "
                    f"vs Evade: {result.defender_roll.total})"
                )
            # You're behind them: target is in YOUR front arc, you're in THEIR rear
            self.set_position(pilot_id, target_id, RelativePosition.FRONT)
            self.set_position(target_id, pilot_id, RelativePosition.REAR)
            return True, (
                f"Got on their tail! Target is in your forward arc, "
                f"you're behind them -- their rear weapons only! "
                f"(Pilot: {result.attacker_roll.total} "
                f"vs Evade: {result.defender_roll.total})"
            )

        elif action == "outmaneuver":
            if not result.attacker_wins:
                return False, (
                    f"Failed to outmaneuver! "
                    f"(Pilot: {result.attacker_roll.total} "
                    f"vs Evade: {result.defender_roll.total})"
                )
            # Reset to neutral frontal engagement
            self.set_position(pilot_id, target_id, RelativePosition.FRONT)
            self.set_position(target_id, pilot_id, RelativePosition.FRONT)
            return True, (
                f"Outmaneuvered! Engagement reset to head-on. "
                f"(Pilot: {result.attacker_roll.total} "
                f"vs Evade: {result.defender_roll.total})"
            )

        return False, "Unknown maneuver."

    @staticmethod
    def _closer_range(current: SpaceRange) -> SpaceRange:
        order = [SpaceRange.CLOSE, SpaceRange.SHORT, SpaceRange.MEDIUM,
                 SpaceRange.LONG, SpaceRange.EXTREME]
        idx = order.index(current) if current in order else 3
        return order[max(0, idx - 1)]

    @staticmethod
    def _farther_range(current: SpaceRange) -> SpaceRange:
        order = [SpaceRange.CLOSE, SpaceRange.SHORT, SpaceRange.MEDIUM,
                 SpaceRange.LONG, SpaceRange.EXTREME, SpaceRange.OUT_OF_RANGE]
        idx = order.index(current) if current in order else 3
        return order[min(len(order) - 1, idx + 1)]

    def format_tactical(self, ship_id: int) -> list[str]:
        """Format tactical display for a ship -- ranges and positions to all contacts."""
        lines = []
        for other_id in self._speeds:
            if other_id == ship_id:
                continue
            rng = self.get_range(ship_id, other_id)
            pos = self.get_position(ship_id, other_id)
            their_pos = self.get_position(other_id, ship_id)
            lines.append(
                f"    Ship #{other_id}: {rng.label} range, "
                f"target at your {pos}, you at their {their_pos}"
            )
        return lines


# Module-level space grid (one per server for now)
_space_grid: Optional[SpaceGrid] = None

def get_space_grid() -> SpaceGrid:
    global _space_grid
    if _space_grid is None:
        _space_grid = SpaceGrid()
    return _space_grid


@dataclass
class ShipWeapon:
    """A weapon mount on a ship."""
    name: str
    fire_arc: str          # "front", "rear", "turret", etc.
    damage: str            # Dice string e.g. "5D"
    fire_control: str      # Dice string e.g. "2D"
    skill: str = "starship_gunnery"
    ammo: int = -1         # -1 = unlimited
    ion: bool = False      # Ion weapons disable, don't destroy
    tractor: bool = False  # Tractor beams


@dataclass
class ShipTemplate:
    """Ship template loaded from YAML."""
    key: str
    name: str
    nickname: str = ""
    scale: str = "starfighter"
    hull: str = "4D"
    shields: str = "0D"
    speed: int = 5
    maneuverability: str = "1D"
    crew: int = 1
    passengers: int = 0
    cargo: int = 0
    consumables: str = ""
    hyperdrive: int = 0
    hyperdrive_backup: int = 0
    cost: int = 0
    weapons: list[ShipWeapon] = field(default_factory=list)
    mod_slots: int = 3       # Number of available modification slots (Drop 12)
    reactor_power: int = 10  # Total reactor power budget (Drop 15)

    @property
    def scale_value(self) -> int:
        return SCALE_CAPITAL if self.scale == "capital" else SCALE_STARFIGHTER


@dataclass
class ShipInstance:
    """
    A specific ship in the game world.

    Ships exist as "rooms" you can enter, with a bridge, cargo hold, etc.
    They also exist as objects in space with position and combat state.
    """
    id: int = 0
    template_key: str = ""
    name: str = ""
    owner_id: int = 0             # Character ID of owner
    room_id: int = 0              # Room ID of the bridge/interior
    docked_at: int = 0            # Room ID of docking bay (0 = in space)

    # Combat state
    hull_damage: int = 0          # Damage taken (reduces effective hull)
    shields_up: bool = True
    shield_dice_front: int = 0    # Can redistribute shield dice
    shield_dice_rear: int = 0
    systems_damaged: list[str] = field(default_factory=list)
    # Possible system damage: engines, weapons, shields, hyperdrive, sensors

    # Crew positions
    pilot_id: int = 0
    copilot_id: int = 0
    gunner_ids: list[int] = field(default_factory=list)

    @property
    def is_docked(self) -> bool:
        return self.docked_at > 0

    def hull_condition(self, template: ShipTemplate) -> str:
        """Get hull condition description."""
        hull_pool = DicePool.parse(template.hull)
        total_pips = hull_pool.total_pips()
        damage_fraction = self.hull_damage / max(total_pips, 1)
        if damage_fraction <= 0:
            return "Pristine"
        elif damage_fraction < 0.25:
            return "Light Damage"
        elif damage_fraction < 0.5:
            return "Moderate Damage"
        elif damage_fraction < 0.75:
            return "Heavy Damage"
        elif damage_fraction < 1.0:
            return "Critical Damage"
        else:
            return "Destroyed"


class ShipRegistry:
    """Loads ship templates from YAML."""

    def __init__(self):
        self._templates: dict[str, ShipTemplate] = {}

    def load_file(self, path: str):
        if not os.path.exists(path):
            log.warning("Starship data not found: %s", path)
            return
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            return
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            weapons = []
            for w in entry.get("weapons", []):
                weapons.append(ShipWeapon(
                    name=w.get("name", "Unknown"),
                    fire_arc=w.get("fire_arc", "front"),
                    damage=w.get("damage", "3D"),
                    fire_control=w.get("fire_control", "0D"),
                    skill=w.get("skill", "starship_gunnery"),
                    ammo=w.get("ammo", -1),
                    ion=w.get("ion", False),
                    tractor=w.get("tractor", False),
                ))
            template = ShipTemplate(
                key=key,
                name=entry.get("name", key),
                nickname=entry.get("nickname", ""),
                scale=entry.get("scale", "starfighter"),
                hull=entry.get("hull", "4D"),
                shields=entry.get("shields", "0D"),
                speed=entry.get("speed", 5),
                maneuverability=entry.get("maneuverability", "1D"),
                crew=entry.get("crew", 1),
                passengers=entry.get("passengers", 0),
                cargo=entry.get("cargo", 0),
                consumables=entry.get("consumables", ""),
                hyperdrive=entry.get("hyperdrive", 0),
                hyperdrive_backup=entry.get("hyperdrive_backup", 0),
                cost=entry.get("cost", 0),
                weapons=weapons,
                mod_slots=entry.get("mod_slots", 3),
                reactor_power=entry.get("reactor_power", 10),
            )
            self._templates[key] = template
        log.info("Loaded %d ship templates from %s", len(self._templates), path)

    def get(self, key: str) -> Optional[ShipTemplate]:
        return self._templates.get(key.lower())

    def find_by_name(self, name: str) -> Optional[ShipTemplate]:
        name_lower = name.lower()
        for t in self._templates.values():
            if t.name.lower() == name_lower or t.key == name_lower:
                return t
        for t in self._templates.values():
            if t.nickname and name_lower in t.nickname.lower():
                return t
        for t in self._templates.values():
            if name_lower in t.name.lower() or name_lower in t.key:
                return t
        return None

    def all_templates(self) -> list[ShipTemplate]:
        return list(self._templates.values())

    @property
    def count(self) -> int:
        return len(self._templates)


# Module singleton
_registry: Optional[ShipRegistry] = None


def get_ship_registry() -> ShipRegistry:
    global _registry
    if _registry is None:
        _registry = ShipRegistry()
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        _registry.load_file(os.path.join(data_dir, "starships.yaml"))
    return _registry


# -- Space Combat Resolution --

@dataclass
class SpaceCombatResult:
    """Result of a space combat attack."""
    attacker_ship: str = ""
    target_ship: str = ""
    weapon_name: str = ""
    attack_roll: int = 0
    defense_roll: int = 0
    hit: bool = False
    damage_roll: int = 0
    soak_roll: int = 0
    hull_damage: int = 0
    systems_hit: list[str] = field(default_factory=list)
    ion_disabled: str = ""
    narrative: str = ""


def resolve_space_attack(
    attacker_skill: DicePool,
    weapon: ShipWeapon,
    attacker_scale: int,
    target_pilot_skill: DicePool,
    target_maneuverability: DicePool,
    target_hull: DicePool,
    target_shields: DicePool,
    target_scale: int,
    num_actions: int = 1,
    range_band: SpaceRange = SpaceRange.SHORT,
    relative_position: str = RelativePosition.FRONT,
    attacker_ship_id: int = None,
    target_ship_id: int = None,
) -> SpaceCombatResult:
    """
    Resolve one space combat attack per R&E Chapter 10.

    Attack: Gunnery + Fire Control vs (base difficulty from range + evasion bonus)
    Range: adds flat difficulty (Close=+0, Short=+5, Medium=+10, Long=+15, Extreme=+25)
    Fire arc: weapon must be able to reach target's relative position
    Scale modifier: crossing scales adds/subtracts 6D
    Damage: weapon damage vs Hull + Shields
    """
    result = SpaceCombatResult()

    # Fire arc check
    if not can_weapon_fire(weapon.fire_arc, relative_position):
        result.narrative = (
            f"  {weapon.name} cannot fire {relative_position}! "
            f"(Arc: {weapon.fire_arc})"
        )
        return result

    # Out of range check
    if range_band == SpaceRange.OUT_OF_RANGE:
        result.narrative = "  Target is out of weapon range!"
        return result

    # Build attack pool: skill + fire control
    fire_control = DicePool.parse(weapon.fire_control)
    attack_pool = DicePool(
        attacker_skill.dice + fire_control.dice,
        attacker_skill.pips + fire_control.pips,
    )
    attack_pool = apply_multi_action_penalty(attack_pool, num_actions)

    # Tailing bonus: +1D attack when attacker is confirmed on target's tail.
    # Requires both ship IDs so we can verify the symmetric position pair.
    tailing_bonus = False
    if (relative_position == RelativePosition.FRONT
            and attacker_ship_id is not None
            and target_ship_id is not None):
        _grid = get_space_grid()
        if _grid.get_position(target_ship_id, attacker_ship_id) == RelativePosition.REAR:
            attack_pool = DicePool(attack_pool.dice + 1, attack_pool.pips)
            tailing_bonus = True

    # Targeting lock-on bonus: consumed on fire
    lockon_bonus = 0
    if attacker_ship_id is not None and target_ship_id is not None:
        lockon_bonus = get_space_grid().get_and_consume_lockon(attacker_ship_id, target_ship_id)
        if lockon_bonus > 0:
            attack_pool = DicePool(attack_pool.dice + lockon_bonus, attack_pool.pips)

    # Scale modifier for to-hit
    scale_diff = target_scale - attacker_scale
    if scale_diff > 0:
        attack_pool = DicePool(attack_pool.dice + scale_diff, attack_pool.pips)
    elif scale_diff < 0:
        attack_pool = DicePool(max(0, attack_pool.dice + scale_diff), attack_pool.pips)

    # Defense pool: piloting + maneuverability
    defense_pool = DicePool(
        target_pilot_skill.dice + target_maneuverability.dice,
        target_pilot_skill.pips + target_maneuverability.pips,
    )

    # Roll attack and defense
    attack_roll = roll_d6_pool(attack_pool)
    defense_roll = roll_d6_pool(defense_pool)

    # Total difficulty: range modifier + defense roll + evasive maneuver bonus
    range_mod = int(range_band)
    maneuver_bonus = 0
    if target_ship_id is not None:
        maneuver_bonus = get_space_grid().get_and_consume_maneuver_bonus(target_ship_id)
    total_difficulty = range_mod + defense_roll.total + maneuver_bonus

    result.attack_roll = attack_roll.total
    result.defense_roll = total_difficulty
    result.hit = attack_roll.total >= total_difficulty

    range_label = range_band.label

    if not result.hit:
        tail_tag = " [TAIL +1D]" if tailing_bonus else ""
        lock_tag = f" [LOCK +{lockon_bonus}D]" if lockon_bonus else ""
        evade_tag = f" + Evade({maneuver_bonus})" if maneuver_bonus else ""
        result.narrative = (
            f"  Shot misses at {range_label} range!{tail_tag}{lock_tag} "
            f"(Attack: {result.attack_roll} vs "
            f"Diff: {range_label}({range_mod}) + Evade({defense_roll.total})"
            f"{evade_tag} = {total_difficulty})"
        )
        return result

    # -- Hit! Roll damage --
    damage_pool = DicePool.parse(weapon.damage)

    # Scale modifier for damage
    if scale_diff > 0:
        # Starfighter hitting capital: -6D damage (but easier to hit)
        damage_pool = DicePool(max(1, damage_pool.dice - scale_diff), damage_pool.pips)
    elif scale_diff < 0:
        # Capital hitting starfighter: +6D damage (but harder to hit)
        damage_pool = DicePool(damage_pool.dice + abs(scale_diff), damage_pool.pips)

    # Soak: hull + shields (ion bypasses shields per R&E p.110)
    if weapon.ion:
        soak_pool = DicePool(target_hull.dice, target_hull.pips)
    else:
        soak_pool = DicePool(
            target_hull.dice + target_shields.dice,
            target_hull.pips + target_shields.pips,
        )

    damage_roll = roll_d6_pool(damage_pool)
    soak_roll = roll_d6_pool(soak_pool)
    result.damage_roll = damage_roll.total
    result.soak_roll = soak_roll.total

    margin = damage_roll.total - soak_roll.total

    if weapon.ion:
        # Ion damage table per R&E p.110 — ionizes controls, no hull damage
        if margin < 0:
            result.narrative = (
                f"  Ion shot absorbed by hull. "
                f"(Damage: {result.damage_roll} vs Hull: {result.soak_roll})"
            )
        elif margin <= 3:
            result.ion_disabled = "1"
            result.narrative = (
                f"  Ion hit! 1 control ionized (-1D for 2 rounds). "
                f"(Damage: {result.damage_roll} vs Hull: {result.soak_roll})"
            )
        elif margin <= 8:
            result.ion_disabled = "2"
            result.narrative = (
                f"  Ion hit! 2 controls ionized (-2D for 2 rounds). "
                f"(Damage: {result.damage_roll} vs Hull: {result.soak_roll})"
            )
        elif margin <= 12:
            result.ion_disabled = "3"
            result.narrative = (
                f"  Heavy ion hit! 3 controls ionized (-3D for 2 rounds)! "
                f"(Damage: {result.damage_roll} vs Hull: {result.soak_roll})"
            )
        elif margin <= 15:
            result.ion_disabled = "4"
            result.narrative = (
                f"  Massive ion hit! 4 controls ionized (-4D for 2 rounds)! "
                f"(Damage: {result.damage_roll} vs Hull: {result.soak_roll})"
            )
        else:
            result.ion_disabled = "dead"
            result.narrative = (
                f"  Devastating ion blast! Controls DEAD — ship is disabled! "
                f"(Damage: {result.damage_roll} vs Hull: {result.soak_roll})"
            )
    else:
        # Physical damage
        if margin <= 0:
            result.narrative = (
                f"  Hit absorbed by shields/hull. "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll})"
            )
        elif margin <= 5:
            result.hull_damage = 1
            result.systems_hit = ["shields"]
            result.narrative = (
                f"  Light hit! Shields damaged. "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        elif margin <= 10:
            result.hull_damage = 2
            import random
            system = random.choice(["engines", "weapons", "shields", "sensors"])
            result.systems_hit = [system]
            result.narrative = (
                f"  Heavy hit! {system.title()} damaged! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        elif margin <= 15:
            result.hull_damage = 4
            result.systems_hit = ["engines", "weapons"]
            result.narrative = (
                f"  Severe damage! Multiple systems hit! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )
        else:
            result.hull_damage = 99
            result.narrative = (
                f"  DESTROYED! Hull breach! "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll}, "
                f"margin: {margin})"
            )

    return result


# -- Tractor Beam Resolution (R&E p.110-111) --

@dataclass
class TractorResult:
    """Result of a tractor beam attack or resist attempt."""
    hit: bool = False
    captured: bool = False
    reeled_in: int = 0           # space units pulled toward attacker
    drive_damage: int = 0        # Move reduction on target
    broke_free: bool = False
    narrative: str = ""
    attack_roll: int = 0
    difficulty: int = 0
    tractor_roll: int = 0
    hull_roll: int = 0


def resolve_tractor_attack(
    attacker_skill: DicePool,
    weapon: ShipWeapon,
    attacker_scale: int,
    target_hull: DicePool,
    target_scale: int,
    range_band: SpaceRange = SpaceRange.SHORT,
    num_actions: int = 1,
) -> TractorResult:
    """
    Resolve a tractor beam attack per R&E p.110-111.

    To-hit: same as normal attack (gunnery + FC vs range difficulty).
    On hit: tractor "damage" vs target hull (no shields, no scale mod on damage).
    If tractor >= hull: target is captured.
    """
    result = TractorResult()

    # To-hit roll
    fire_control = DicePool.parse(weapon.fire_control)
    attack_pool = DicePool(
        attacker_skill.dice + fire_control.dice,
        attacker_skill.pips + fire_control.pips,
    )
    attack_pool = apply_multi_action_penalty(attack_pool, num_actions)

    range_mod = RANGE_DIFFICULTY.get(range_band, 10)
    attack_result = roll_d6_pool(attack_pool)
    result.attack_roll = attack_result.total
    result.difficulty = range_mod

    if attack_result.total < range_mod:
        result.narrative = (
            f"  Tractor beam misses! "
            f"(Attack: {result.attack_roll} vs Diff: {range_mod})"
        )
        return result

    result.hit = True

    # Tractor "damage" vs hull (no shields, no scale modifier on tractor damage)
    tractor_pool = DicePool.parse(weapon.damage)
    # Scale modifier applies to tractor strength
    scale_diff = target_scale - attacker_scale
    if scale_diff < 0:
        tractor_pool = DicePool(tractor_pool.dice + abs(scale_diff), tractor_pool.pips)

    tractor_roll = roll_d6_pool(tractor_pool)
    hull_roll = roll_d6_pool(target_hull)
    result.tractor_roll = tractor_roll.total
    result.hull_roll = hull_roll.total

    if tractor_roll.total < hull_roll.total:
        result.narrative = (
            f"  Tractor beam hits but target breaks free! "
            f"(Tractor: {result.tractor_roll} vs Hull: {result.hull_roll})"
        )
        return result

    result.captured = True
    result.narrative = (
        f"  Tractor beam locks on! Target captured! "
        f"(Tractor: {result.tractor_roll} vs Hull: {result.hull_roll})"
    )
    return result


def resolve_tractor_resist(
    tractor_damage: DicePool,
    target_hull: DicePool,
    attacker_scale: int,
    target_scale: int,
) -> TractorResult:
    """
    Resolve a captured ship's attempt to break free of a tractor beam.

    Per R&E p.111: tractor damage vs hull. If hull wins, ship breaks free.
    If tractor wins, ship is reeled in and may take drive damage.
    """
    result = TractorResult()

    # Scale modifier on tractor strength
    scale_diff = target_scale - attacker_scale
    effective_tractor = tractor_damage
    if scale_diff < 0:
        effective_tractor = DicePool(
            tractor_damage.dice + abs(scale_diff), tractor_damage.pips)

    tractor_roll = roll_d6_pool(effective_tractor)
    hull_roll = roll_d6_pool(target_hull)
    result.tractor_roll = tractor_roll.total
    result.hull_roll = hull_roll.total

    if hull_roll.total > tractor_roll.total:
        result.broke_free = True
        result.narrative = (
            f"  Breaks free of the tractor beam! "
            f"(Hull: {result.hull_roll} vs Tractor: {result.tractor_roll})"
        )
        return result

    margin = tractor_roll.total - hull_roll.total
    if margin <= 3:
        result.reeled_in = 0
        result.narrative = (
            f"  Struggles against the tractor beam but can't break free. "
            f"(Tractor: {result.tractor_roll} vs Hull: {result.hull_roll})"
        )
    elif margin <= 8:
        result.reeled_in = 1
        result.drive_damage = 1
        result.narrative = (
            f"  Reeled in 1 unit! Drives strained (-1 Move). "
            f"(Tractor: {result.tractor_roll} vs Hull: {result.hull_roll})"
        )
    elif margin <= 12:
        result.reeled_in = 2
        result.drive_damage = 2
        result.narrative = (
            f"  Reeled in 2 units! Drives damaged (-2 Move)! "
            f"(Tractor: {result.tractor_roll} vs Hull: {result.hull_roll})"
        )
    elif margin <= 15:
        result.reeled_in = 3
        result.drive_damage = 3
        result.narrative = (
            f"  Reeled in 3 units! Drives heavily damaged (-3 Move)! "
            f"(Tractor: {result.tractor_roll} vs Hull: {result.hull_roll})"
        )
    else:
        result.reeled_in = 4
        result.drive_damage = 4
        result.narrative = (
            f"  Reeled in 4 units! Drives destroyed (-4 Move)! "
            f"(Tractor: {result.tractor_roll} vs Hull: {result.hull_roll})"
        )

    return result


# -- Hazard Table (Star Warriors Section 7, adapted for D6 R&E) --

@dataclass
class HazardResult:
    """Result of a hazard table roll after a bad maneuver."""
    roll: int = 0                       # 2d6 result
    systems_damaged: list = None        # Systems that become "damaged"
    hull_damage: int = 0                # Direct hull damage points
    narrative: str = ""                 # Broadcast message

    def __post_init__(self):
        if self.systems_damaged is None:
            self.systems_damaged = []

    @property
    def has_effect(self) -> bool:
        return bool(self.systems_damaged) or self.hull_damage > 0


# Hazard table: 2d6 roll -> (primary_system, secondary_system_or_None, hull_damage, flavour)
# Roll 7 is always no effect (Star Warriors 7.38).
# Adapted from Star Warriors Hazard Table rows B-G, columns 2-12.
_HAZARD_TABLE = {
    2:  (["engines"],              "shields",   0, "Control systems surge — multiple failures!"),
    3:  (["shields"],              "engines",   0, "Power coupling overloads!"),
    4:  (["engines"],              "weapons",   0, "Structural stress tears at the drive!"),
    5:  (["shields"],              None,        0, "Shield emitter overloads!"),
    6:  (["engines"],              None,        0, "Gyro destabilizes — handling sluggish!"),
    7:  ([],                       None,        0, "Close call — no serious damage!"),
    8:  (["weapons"],              None,        0, "Fire control feedback — guns offline!"),
    9:  (["sensors"],              None,        0, "Sensor array shaken loose!"),
    10: (["engines"],              "shields",   0, "Drive stutters under the stress!"),
    11: ([],                       None,        1, "Frame stress — hull integrity compromised!"),
    12: (["hyperdrive", "engines"],None,        0, "Critical stress — drive systems hit!"),
}


def roll_hazard_table(systems: dict) -> HazardResult:
    """
    Roll on the Hazard Table (Star Warriors Section 7, adapted).

    Called when a pilot fails an evasive maneuver roll by 5 or more.
    Only damages systems that are currently 'working' — already-damaged
    systems can't be made worse by a hazard (they're already failing).

    Args:
        systems: Current ship systems dict (from DB JSON).

    Returns:
        HazardResult with narrative and damage to apply.
    """
    import random
    roll = random.randint(1, 6) + random.randint(1, 6)

    entry = _HAZARD_TABLE.get(roll, _HAZARD_TABLE[7])
    primary_list, secondary, hull_dmg, flavour = entry

    result = HazardResult(roll=roll, hull_damage=hull_dmg, narrative="")

    # Only damage working systems
    def _is_working(sys_name: str) -> bool:
        val = systems.get(sys_name, True)
        return val is True or val == "working"

    damaged = []
    for sys_name in primary_list:
        if _is_working(sys_name):
            damaged.append(sys_name)

    if secondary and _is_working(secondary):
        damaged.append(secondary)

    result.systems_damaged = damaged

    # Build narrative
    dmg_parts = []
    if damaged:
        dmg_parts.append(f"{', '.join(s.title() for s in damaged)} damaged")
    if hull_dmg:
        dmg_parts.append(f"+{hull_dmg} hull damage")
    if not dmg_parts:
        dmg_parts.append("no systems affected")

    result.narrative = (
        f"  {ansi.BRIGHT_RED}[HAZARD]{ansi.RESET} "
        f"Roll {roll}: {flavour} "
        f"({', '.join(dmg_parts)}.)"
    )

    return result


def format_ship_status(template: ShipTemplate, instance: ShipInstance = None) -> list[str]:
    """Format a ship template/instance as a status display."""
    lines = []
    name = instance.name if instance else template.name
    lines.append(f"  {name}")
    if template.nickname:
        lines.append(f"  ({template.nickname})")
    lines.append(f"  Scale: {template.scale.title()}  "
                 f"Speed: {template.speed}  "
                 f"Maneuverability: {template.maneuverability}")
    lines.append(f"  Hull: {template.hull}  "
                 f"Shields: {template.shields}")
    if instance:
        lines.append(f"  Condition: {instance.hull_condition(template)}")
        if instance.systems_damaged:
            lines.append(f"  Damaged Systems: {', '.join(instance.systems_damaged)}")
    lines.append(f"  Crew: {template.crew}  Passengers: {template.passengers}  "
                 f"Cargo: {template.cargo}t")
    if template.hyperdrive:
        hd = f"x{template.hyperdrive}"
        if template.hyperdrive_backup:
            hd += f" (backup: x{template.hyperdrive_backup})"
        lines.append(f"  Hyperdrive: {hd}")
    else:
        lines.append(f"  Hyperdrive: None")
    lines.append(f"  Consumables: {template.consumables}")

    if template.weapons:
        lines.append(f"  Weapons:")
        for w in template.weapons:
            ammo_str = f" [{w.ammo} shots]" if w.ammo > 0 else ""
            ion_str = " (ION)" if w.ion else ""
            tractor_str = " (TRACTOR)" if w.tractor else ""
            lines.append(
                f"    {w.name:30s} Dmg: {w.damage:>4s}  "
                f"FC: {w.fire_control:>3s}  Arc: {w.fire_arc}"
                f"{ammo_str}{ion_str}{tractor_str}"
            )

    return lines


# -- Damage Control (Star Warriors Section 17, adapted for D6 R&E) --

# Repairable systems and their base difficulties (R&E Technical skill check)
REPAIR_DIFFICULTIES = {
    "shields":    15,  # Moderate -- reroute power, reset breakers
    "sensors":    15,  # Moderate -- recalibrate, swap modules
    "engines":    20,  # Difficult -- mechanical, dangerous
    "weapons":    20,  # Difficult -- realign, replace components
    "hyperdrive": 25,  # Very Difficult -- precision calibration
    "hull":       20,  # Difficult -- patch breaches under fire
}

# All systems that can be damaged (match keys in the ship systems JSON)
REPAIRABLE_SYSTEMS = list(REPAIR_DIFFICULTIES.keys())

# System states in the systems JSON:
#   missing/True  = working
#   False/"damaged" = damaged (repairable)
#   "destroyed"   = permanently damaged (Star Warriors 17.27)


def get_system_state(systems: dict, system_name: str) -> str:
    """Return 'working', 'damaged', or 'destroyed' for a ship system."""
    val = systems.get(system_name, True)
    if val is True or val == "working":
        return "working"
    if val == "destroyed":
        return "destroyed"
    # False or "damaged"
    return "damaged"


def get_repair_skill_name(scale: str) -> str:
    """Return the appropriate Technical repair skill for a ship's scale."""
    if scale == "capital":
        return "capital ship repair"
    return "space transports repair"


def get_weapon_repair_skill(scale: str) -> str:
    """Return the weapon-specific repair skill for a ship's scale."""
    if scale == "capital":
        return "capital ship weapon repair"
    return "starship weapon repair"


# ─────────────────────────────────────────────────────────────────────────────
# Ship Modification Engine  (Drop 12)
# ─────────────────────────────────────────────────────────────────────────────

# Maximum pip boosts per stat (WEG R&E p88-90: max +1D+2 = 5 pips).
# Speed is measured in integer units, hyperdrive as a float multiplier.
_MOD_MAX_PIPS = {
    "maneuverability": 5,
    "hull":            5,
    "shields":         5,
    "fire_control":    5,  # per weapon slot
    "sensors":         3,  # +1D max
}
_MOD_MAX_SPEED      = 2    # +2 speed max
_MOD_MIN_HYPERDRIVE = 0.5  # halved at most


def _pip_count(dice_str: str) -> int:
    """Convert a dice string like '2D+1' to total pips (D=3 pips)."""
    if not dice_str:
        return 0
    s = dice_str.strip().upper()
    dice, pips = 0, 0
    if "D" in s:
        parts = s.split("D")
        try:
            dice = int(parts[0]) if parts[0] else 0
        except ValueError:
            dice = 0
        pip_part = parts[1].replace("+", "").replace(" ", "") if len(parts) > 1 else ""
        try:
            pips = int(pip_part) if pip_part else 0
        except ValueError:
            pips = 0
    else:
        try:
            pips = int(s)
        except ValueError:
            pips = 0
    return dice * 3 + pips


def _pips_to_dice_str(total_pips: int) -> str:
    """Convert total pips back to a dice string like '2D+1'."""
    if total_pips <= 0:
        return "0D"
    d = total_pips // 3
    p = total_pips % 3
    if p == 0:
        return f"{d}D"
    return f"{d}D+{p}"


def _quality_factor(quality: int) -> float:
    """
    Convert component quality to a stat boost multiplier.
    Quality 80+ → 1.0 (full boost)
    Quality 60-79 → 0.75
    Quality <60  → 0.5
    """
    if quality >= 80:
        return 1.0
    if quality >= 60:
        return 0.75
    return 0.5


# ── Power Allocation (Drop 15) ───────────────────────────────────────────────

# Default power draw per system (cost at "normal" operation)
POWER_DEFAULTS: dict[str, int] = {
    "engines":      3,
    "shields":      3,
    "weapons":      2,
    "sensors":      1,
    "life_support": 1,
    "hyperdrive":   0,  # only draws when charging
    "comms":        0,  # only draws when active
}

# Presets: name -> {system: power_level}
POWER_PRESETS: dict[str, dict[str, int]] = {
    "combat":    {"engines": 3, "shields": 3, "weapons": 2, "sensors": 1, "life_support": 1},
    "silent":    {"engines": 1, "shields": 0, "weapons": 0, "sensors": 0, "life_support": 1},
    "emergency": {"engines": 4, "shields": 4, "weapons": 0, "sensors": 0, "life_support": 1},
}

# Power bonus caps per system
POWER_BONUS_CAP: dict[str, int] = {
    "engines": 3,   # +1 speed per extra point, max +3
    "shields": 3,   # +1 pip per extra, max +1D (3 pips)
    "weapons": 3,   # +1 pip FC per extra, max +1D
    "sensors": 2,   # +1D scan per extra, max +2D (6 pips)
}

# Silent running sensor detection difficulty bonus
SILENT_RUNNING_SENSOR_BONUS = 9  # adds to scan difficulty when target is silent


def get_power_state(systems: dict) -> dict[str, int]:
    """
    Return current power allocation from systems dict.
    Falls back to defaults for any missing key.
    """
    stored = systems.get("power_allocation", {})
    if isinstance(stored, str):
        import json as _j
        try:
            stored = _j.loads(stored)
        except Exception:
            stored = {}
    return {sys: stored.get(sys, POWER_DEFAULTS[sys]) for sys in POWER_DEFAULTS}


def get_power_budget_used(power_state: dict[str, int]) -> int:
    """Sum of all current power allocations."""
    return sum(power_state.values())


def is_silent_running(systems: dict) -> bool:
    """True if ship is in silent running mode (matches silent preset)."""
    ps = get_power_state(systems)
    silent = POWER_PRESETS["silent"]
    return all(ps.get(k, 0) == v for k, v in silent.items())


def apply_power_bonuses(
    template: "ShipTemplate",
    systems: dict,
    base_speed: int,
    base_maneuver_pips: int,
    base_shield_pips: int,
    sensors_bonus: int,
    weapon_fc: dict,
) -> tuple[int, int, int, int, dict]:
    """
    Apply power allocation overcharge bonuses on top of mod-derived stats.
    Returns (speed, maneuver_pips, shield_pips, sensors_bonus, weapon_fc).
    All bonuses are relative to the default allocation.
    """
    ps = get_power_state(systems)
    defaults = POWER_DEFAULTS

    # Engines overcharge: each point above default = +1 speed
    eng_extra = max(0, ps["engines"] - defaults["engines"])
    speed = base_speed + min(eng_extra, POWER_BONUS_CAP["engines"])

    # Engines underpower: 0 = halve speed, no maneuvers
    if ps["engines"] == 0:
        speed = max(1, base_speed // 2)

    # Shields overcharge: +1 pip per extra point
    sh_extra = max(0, ps["shields"] - defaults["shields"])
    shield_pips = base_shield_pips + min(sh_extra, POWER_BONUS_CAP["shields"])
    if ps["shields"] == 0:
        shield_pips = 0

    # Weapons overcharge: +1 pip fire control per extra point (all weapons)
    wp_extra = max(0, ps["weapons"] - defaults["weapons"])
    wp_bonus = min(wp_extra, POWER_BONUS_CAP["weapons"])
    if ps["weapons"] == 0:
        # weapons offline — can't fire (flagged via weapon_fc sentinel -99)
        weapon_fc = {k: -99 for k in weapon_fc} if weapon_fc else {-1: -99}
    elif wp_bonus > 0:
        # Apply to all weapon slots present, or add a global sentinel slot -1
        if weapon_fc:
            weapon_fc = {k: v + wp_bonus for k, v in weapon_fc.items()}
        else:
            weapon_fc = {-1: wp_bonus}  # sentinel: all weapons get bonus

    # Sensors overcharge: +1D (3 pips) per extra point
    sens_extra = max(0, ps["sensors"] - defaults["sensors"])
    sensors_bonus = sensors_bonus + min(sens_extra * 3, POWER_BONUS_CAP["sensors"] * 3)
    if ps["sensors"] == 0:
        sensors_bonus = -6  # sentinel: auto-fumble passive, -2D scan

    return speed, base_maneuver_pips, shield_pips, sensors_bonus, weapon_fc

def get_effective_stats(template: "ShipTemplate", systems: dict) -> dict:
    """
    Compute effective ship stats by applying installed modifications.

    Returns a dict with the same keys as ShipTemplate fields that
    can be modified (speed, maneuverability, hull, shields, hyperdrive,
    and per-weapon fire_control overrides).

    Callers should fall back to template values for any key not present.

    Args:
        template: The base ShipTemplate from the registry.
        systems:  The ship's parsed systems JSON dict.

    Returns:
        {
            "speed":            int,
            "maneuverability":  str,   e.g. "2D+1"
            "hull":             str,
            "shields":          str,
            "hyperdrive":       int,   (effective multiplier, min 1 due to int floor)
            "hyperdrive_float": float, (fractional effective multiplier)
            "weapon_fc":        dict[int, str],  # weapon index → effective fire_control
            "sensors_bonus":    int,   # additional sensor pips
            "mods_installed":   int,
            "slots_used":       int,
            "slots_total":      int,
            "cargo_used_by_mods": int, # tons consumed by mods
        }
    """
    mods: list = systems.get("modifications", [])

    # Start from template base values
    speed          = template.speed
    maneuver_pips  = _pip_count(template.maneuverability)
    hull_pips      = _pip_count(template.hull)
    shield_pips    = _pip_count(template.shields)
    hyperdrive_f   = float(template.hyperdrive) if template.hyperdrive else 0.0
    sensors_bonus  = 0
    stealth_bonus  = 0   # difficulty penalty for scanners targeting this ship
    weapon_fc      = {}  # weapon_slot_index → extra pips
    cargo_used     = 0

    for mod in mods:
        if not isinstance(mod, dict):
            continue
        stat_target  = mod.get("stat_target", "")
        stat_boost   = mod.get("stat_boost", 1)    # pips or speed units
        quality      = mod.get("quality", 80)
        cargo_weight = mod.get("cargo_weight", 10)
        weapon_slot  = mod.get("weapon_slot", None)

        effective_boost = max(1, round(stat_boost * _quality_factor(quality)))
        cargo_used += cargo_weight

        if stat_target == "speed":
            speed = min(template.speed + _MOD_MAX_SPEED,
                        speed + effective_boost)

        elif stat_target == "maneuverability":
            cap = _pip_count(template.maneuverability) + _MOD_MAX_PIPS["maneuverability"]
            maneuver_pips = min(cap, maneuver_pips + effective_boost)

        elif stat_target == "hull":
            cap = _pip_count(template.hull) + _MOD_MAX_PIPS["hull"]
            hull_pips = min(cap, hull_pips + effective_boost)

        elif stat_target == "shields":
            cap = _pip_count(template.shields) + _MOD_MAX_PIPS["shields"]
            shield_pips = min(cap, shield_pips + effective_boost)

        elif stat_target == "fire_control":
            slot = int(weapon_slot) if weapon_slot is not None else 0
            current = weapon_fc.get(slot, 0)
            cap = _pip_count(
                template.weapons[slot].fire_control
                if slot < len(template.weapons) else "0D"
            ) + _MOD_MAX_PIPS["fire_control"]
            base_fc = _pip_count(
                template.weapons[slot].fire_control
                if slot < len(template.weapons) else "0D"
            )
            weapon_fc[slot] = min(cap - base_fc, current + effective_boost)

        elif stat_target == "sensors":
            sensors_bonus = min(3, sensors_bonus + effective_boost)

        elif stat_target == "stealth":
            stealth_bonus += effective_boost

        elif stat_target == "hyperdrive" and hyperdrive_f > 0:
            # Boost reduces hyperdrive multiplier (lower = faster)
            # stat_boost stored as pips; each pip = -0.25 multiplier
            reduction = effective_boost * 0.25
            hyperdrive_f = max(_MOD_MIN_HYPERDRIVE, hyperdrive_f - reduction)

    # Clamp maneuverability/hull/shields to base (no negative mods reduce below base)
    maneuver_pips = max(_pip_count(template.maneuverability), maneuver_pips)
    hull_pips     = max(_pip_count(template.hull), hull_pips)
    shield_pips   = max(_pip_count(template.shields), shield_pips)

    # Build weapon_fc strings (extra pips only, applied in combat code)
    weapon_fc_str = {
        slot: _pips_to_dice_str(extra)
        for slot, extra in weapon_fc.items()
        if extra > 0
    }

    # Apply power allocation overcharge bonuses (Drop 15)
    speed, maneuver_pips, shield_pips, sensors_bonus, weapon_fc_str = \
        apply_power_bonuses(
            template, systems,
            speed, maneuver_pips, shield_pips, sensors_bonus, weapon_fc_str,
        )

    # Apply Captain's Order modifiers (Drop 16)
    speed, maneuver_pips, shield_pips, sensors_bonus, weapon_fc_str, order_flags = \
        apply_order_modifiers(
            systems, speed, maneuver_pips, shield_pips,
            sensors_bonus, weapon_fc_str,
        )

    return {
        "speed":              speed,
        "maneuverability":    _pips_to_dice_str(maneuver_pips),
        "hull":               _pips_to_dice_str(hull_pips),
        "shields":            _pips_to_dice_str(shield_pips),
        "hyperdrive":         max(1, int(round(hyperdrive_f))) if hyperdrive_f > 0 else 0,
        "hyperdrive_float":   hyperdrive_f,
        "weapon_fc":          weapon_fc_str,
        "sensors_bonus":      sensors_bonus,
        "mods_installed":     len(mods),
        "slots_used":         len(mods),
        "slots_total":        template.mod_slots,
        "cargo_used_by_mods": cargo_used,
        "power_state":        get_power_state(systems),
        "reactor_power":      template.reactor_power,
        "active_order":       systems.get("active_order"),
        "order_flags":        order_flags,
        "stealth_bonus":      stealth_bonus,
        "false_transponder":  systems.get("false_transponder"),
    }


# ── Captain's Orders (Drop 16) ───────────────────────────────────────────────
#
# Each order: (bonus_desc, tradeoff_desc, stat_deltas_dict)
# stat_deltas keys match get_effective_stats() output keys:
#   speed_delta, maneuver_pip_delta, shield_pip_delta,
#   fc_pip_delta (all weapons), damage_pip_delta (designated weapon only),
#   weapons_offline (bool), sensors_stealth_bonus (int)
#
ORDER_DEFINITIONS: dict[str, dict] = {
    "battle_stations": {
        "name":       "Battle Stations",
        "number":     1,
        "bonus":      "+1D fire control (all gunners)",
        "tradeoff":   "-1D maneuverability",
        "deltas":     {"fc_pip_delta": 3, "maneuver_pip_delta": -3},
    },
    "evasive_pattern": {
        "name":       "Evasive Pattern",
        "number":     2,
        "bonus":      "+2D maneuverability (pilot)",
        "tradeoff":   "-1D fire control (all gunners)",
        "deltas":     {"maneuver_pip_delta": 6, "fc_pip_delta": -3},
    },
    "all_power_forward": {
        "name":       "All Power Forward",
        "number":     3,
        "bonus":      "+2 speed",
        "tradeoff":   "-1D shields, rear weapons offline",
        "deltas":     {"speed_delta": 2, "shield_pip_delta": -3},
        "rear_weapons_offline": True,
    },
    "hold_the_line": {
        "name":       "Hold the Line",
        "number":     4,
        "bonus":      "+2D shields",
        "tradeoff":   "-2 speed (cannot flee)",
        "deltas":     {"shield_pip_delta": 6, "speed_delta": -2},
        "no_flee":    True,
    },
    "silent_running": {
        "name":       "Silent Running",
        "number":     5,
        "bonus":      "+3D sensor stealth vs detection",
        "tradeoff":   "Weapons offline, shields off",
        "deltas":     {"shield_pip_delta": -99, "sensors_stealth_bonus": 9},
        "weapons_offline": True,
    },
    "boarding_action": {
        "name":       "Boarding Action",
        "number":     6,
        "bonus":      "+1D melee/brawl for boarding crew",
        "tradeoff":   "-1D piloting",
        "deltas":     {"maneuver_pip_delta": -3, "boarding_bonus": 3},
    },
    "concentrate_fire": {
        "name":       "Concentrate Fire",
        "number":     7,
        "bonus":      "+2D damage on designated weapon",
        "tradeoff":   "Other weapons cannot fire",
        "deltas":     {"damage_pip_delta": 6},
        "concentrate": True,
    },
    "coordinate": {
        "name":       "Coordinate",
        "number":     8,
        "bonus":      "+1D to all crew checks",
        "tradeoff":   "None",
        "deltas":     {"crew_bonus": 3},
    },
}

# Sorted order list for display
ORDER_LIST = sorted(ORDER_DEFINITIONS.values(), key=lambda o: o["number"])


def get_active_order(systems: dict) -> dict | None:
    """Return the active order dict, or None if no order is set."""
    key = systems.get("active_order")
    if not key:
        return None
    return ORDER_DEFINITIONS.get(key)


def apply_order_modifiers(
    systems: dict,
    speed: int,
    maneuver_pips: int,
    shield_pips: int,
    sensors_bonus: int,
    weapon_fc_str: dict,
) -> tuple[int, int, int, int, dict, dict]:
    """
    Apply active Captain's Order modifiers on top of power-adjusted stats.
    Returns (speed, maneuver_pips, shield_pips, sensors_bonus,
             weapon_fc_str, order_flags).
    order_flags: dict with boolean flags consumed by commands
                 (weapons_offline, rear_weapons_offline, no_flee,
                  concentrate, boarding_bonus, crew_bonus).
    """
    order = get_active_order(systems)
    flags: dict = {}
    if not order:
        return speed, maneuver_pips, shield_pips, sensors_bonus, weapon_fc_str, flags

    d = order.get("deltas", {})

    speed          = max(1, speed          + d.get("speed_delta",          0))
    maneuver_pips  = max(0, maneuver_pips  + d.get("maneuver_pip_delta",   0))
    shield_pips    = max(0, shield_pips    + d.get("shield_pip_delta",     0))
    sensors_bonus  =        sensors_bonus  + d.get("sensors_stealth_bonus", 0)

    fc_delta = d.get("fc_pip_delta", 0)
    if fc_delta != 0:
        if weapon_fc_str:
            weapon_fc_str = {k: v + fc_delta for k, v in weapon_fc_str.items()}
        else:
            weapon_fc_str = {-1: fc_delta}  # sentinel: applies to all slots

    # Pass through boolean flags for commands to check
    for flag in ("weapons_offline", "rear_weapons_offline", "no_flee",
                 "concentrate", "boarding_bonus", "crew_bonus"):
        if order.get(flag) or d.get(flag):
            flags[flag] = order.get(flag) or d.get(flag, True)

    return speed, maneuver_pips, shield_pips, sensors_bonus, weapon_fc_str, flags


# ── Ship Quirks (Drop 19) ────────────────────────────────────────────────────
# Source: Platt's Smugglers Guide p.32 "Starship Quirks"
# Categories: cosmetic (70%), annoying (15%), beneficial (5%),
#             dangerous (5%), endearing (5%)

QUIRK_POOL: list[dict] = [
    # Cosmetic (no mechanical effect)
    {"key": "blinking_light",       "category": "cosmetic",    "effect": None,
     "desc": "An insignificant red light on the command console keeps blinking."},
    {"key": "alien_labels",         "category": "cosmetic",    "effect": None,
     "desc": "Maintenance labels and interior markings are in a strange alien language."},
    {"key": "forward_strobes",      "category": "cosmetic",    "effect": None,
     "desc": "Forward strobe lamps are always lit when the ship is in operation."},
    {"key": "hatches_seal",         "category": "cosmetic",    "effect": None,
     "desc": "All interior hatches seal automatically when the guns are operational."},
    {"key": "hyperspace_groans",    "category": "endearing",   "effect": None,
     "desc": "The ship groans and creaks entering hyperspace, sounds almost alive."},
    {"key": "lumpy_chair",          "category": "cosmetic",    "effect": None,
     "desc": "The pilot's seat padding is lumpy and uncomfortable. Long flights are unpleasant."},
    {"key": "mysterious_squeak",    "category": "cosmetic",    "effect": None,
     "desc": "A mysterious squeaking comes from beneath the deckplates in the bunk cabin."},
    {"key": "engine_rattle",        "category": "cosmetic",    "effect": None,
     "desc": "The sublight engines rattle at speeds above 7. Nothing seems to fix it."},
    {"key": "nav_glitch",           "category": "cosmetic",    "effect": None,
     "desc": "The navicomputer displays Huttese numerals no matter what you set it to."},
    {"key": "landing_lights",       "category": "cosmetic",    "effect": None,
     "desc": "Landing lights flicker once at random intervals. Spooky."},
    # Annoying (-1 pip to relevant skill)
    {"key": "comm_static",          "category": "annoying",    "effect": {"skill": "communications", "pip_mod": -1},
     "desc": "The comm system is plagued with occasional static. -1 pip to Communications."},
    {"key": "sensor_drift",         "category": "annoying",    "effect": {"skill": "sensors", "pip_mod": -1},
     "desc": "Sensor array drifts out of alignment. -1 pip to Sensor checks."},
    {"key": "sluggish_controls",    "category": "annoying",    "effect": {"stat": "speed", "mod": -1},
     "desc": "Controls feel sluggish below speed 5. -1 to effective speed."},
    {"key": "landing_gear_stuck",   "category": "annoying",    "effect": None,
     "desc": "Landing gear refuses to retract until the third try. Adds 30s to launch."},
    # Beneficial
    {"key": "hidden_compartment",   "category": "beneficial",  "effect": {"customs_stealth": 3},
     "desc": "A loose deck plate conceals a hidden compartment. +1D to hiding cargo from customs."},
    {"key": "overclocked_sensors",  "category": "beneficial",  "effect": {"skill": "sensors", "pip_mod": 1},
     "desc": "Previous owner overclocked the sensors. +1 pip to Sensor checks."},
    # Dangerous
    {"key": "weapons_drain_shields","category": "dangerous",   "effect": {"power_drain": 1},
     "desc": "Powering weapons drains energy from shields. Weapons draw +1 extra power."},
    {"key": "hyperdrive_stutter",   "category": "dangerous",   "effect": {"hyperspace_risk": 0.1},
     "desc": "The hyperdrive stutters on 10% of jumps, adding 1D6 minutes to transit time."},
]

# Weighted selection: cosmetic 70%, annoying 15%, beneficial 5%, dangerous 5%, endearing 5%
_QUIRK_WEIGHTS = {
    "cosmetic": 70,
    "annoying": 15,
    "beneficial": 5,
    "dangerous": 5,
    "endearing": 5,
}


def roll_quirk(existing_keys: list[str] | None = None) -> dict | None:
    """
    Randomly select a quirk from the pool.
    Won't duplicate an already-installed quirk.
    Returns None if pool exhausted.
    """
    import random as _r
    existing = set(existing_keys or [])
    available = [q for q in QUIRK_POOL if q["key"] not in existing]
    if not available:
        return None
    # Weighted by category
    weights = [_QUIRK_WEIGHTS.get(q["category"], 5) for q in available]
    return _r.choices(available, weights=weights, k=1)[0]


def get_quirks(systems: dict) -> list[dict]:
    """Return list of installed quirks from ship systems."""
    return systems.get("quirks", [])


def format_quirks_display(systems: dict) -> list[str]:
    """Return ANSI lines for +ship quirks display."""
    quirks = get_quirks(systems)
    if not quirks:
        return ["  No quirks detected. Suspiciously well-behaved ship."]
    lines = []
    cat_colors = {
        "cosmetic":   "[2m",
        "annoying":   "[1;33m",
        "beneficial": "[1;32m",
        "dangerous":  "[1;31m",
        "endearing":  "[0;36m",
    }
    RESET = "[0m"
    for q in quirks:
        col = cat_colors.get(q.get("category", "cosmetic"), "")
        cat = q.get("category", "cosmetic").title()
        desc = q.get("desc", q.get("key", "Unknown"))
        lines.append(f"  {col}[{cat}]{RESET}  {desc}")
    return lines

def format_mods_display(template: "ShipTemplate", systems: dict) -> list:
    """
    Return ANSI-formatted lines for +ship/mods output.
    """
    _BOLD  = "\033[1m"
    _DIM   = "\033[2m"
    _CYAN  = "\033[0;36m"
    _GREEN = "\033[1;32m"
    _RESET = "\033[0m"

    mods: list = systems.get("modifications", [])
    effective = get_effective_stats(template, systems)
    slots_used  = effective["slots_used"]
    slots_total = effective["slots_total"]
    cargo_used  = effective["cargo_used_by_mods"]

    lines = [
        f"{_BOLD}{'=' * 56}{_RESET}",
        f"  {_BOLD}INSTALLED MODIFICATIONS{_RESET}  —  {template.name}",
        f"  {_DIM}Slots: {slots_used}/{slots_total}   "
        f"Cargo consumed: {cargo_used}t{_RESET}",
        f"  {_DIM}{'-' * 54}{_RESET}",
    ]

    if not mods:
        lines.append(f"  {_DIM}No modifications installed.{_RESET}")
    else:
        for i, mod in enumerate(mods):
            if not isinstance(mod, dict):
                continue
            q = mod.get("quality", 0)
            name  = mod.get("component_name", mod.get("component_key", "Unknown"))
            stat  = mod.get("stat_target", "?")
            boost = mod.get("stat_boost", 1)
            cw    = mod.get("cargo_weight", 0)
            inst  = mod.get("installed_by", "?")
            qcolor = _GREEN if q >= 80 else _DIM
            factor = _quality_factor(q)
            eff = max(1, round(boost * factor))
            lines.append(
                f"  [{i}] {_BOLD}{name}{_RESET}  "
                f"{_CYAN}+{eff} {stat}{_RESET}  "
                f"{qcolor}Q:{q}%{_RESET}  "
                f"{_DIM}{cw}t  by {inst}{_RESET}"
            )

    # Show effective stat summary
    lines += [
        f"  {_DIM}{'-' * 54}{_RESET}",
        f"  {_BOLD}Effective Stats:{_RESET}",
        f"    Speed {effective['speed']}  "
        f"Maneuver {effective['maneuverability']}  "
        f"Hull {effective['hull']}  "
        f"Shields {effective['shields']}",
    ]
    if effective["sensors_bonus"] > 0:
        lines.append(f"    Sensors bonus: +{effective['sensors_bonus']} pips")
    if effective["hyperdrive_float"] > 0 and effective["hyperdrive_float"] != template.hyperdrive:
        lines.append(
            f"    Hyperdrive: x{effective['hyperdrive_float']:.2f} "
            f"(base x{template.hyperdrive})"
        )
    lines.append(f"{_BOLD}{'=' * 56}{_RESET}")
    return lines


@dataclass
class DamageControlResult:
    """Result of a damage control attempt."""
    system_name: str = ""
    success: bool = False
    permanent_failure: bool = False
    hull_repaired: int = 0
    roll_total: int = 0
    difficulty: int = 0
    narrative: str = ""


def resolve_damage_control(
    repair_pool: DicePool,
    system_name: str,
    in_combat: bool = False,
    num_actions: int = 1,
) -> DamageControlResult:
    """
    Resolve a damage control attempt per Star Warriors Section 17,
    adapted for R&E dice mechanics.

    Args:
        repair_pool: Character's repair skill dice pool
        system_name: Which system to repair (shields, engines, etc.)
        in_combat: If True, +5 difficulty (working under fire)
        num_actions: How many actions this round (for multi-action penalty)

    Returns:
        DamageControlResult with outcome and narrative.
    """
    result = DamageControlResult(system_name=system_name)

    base_diff = REPAIR_DIFFICULTIES.get(system_name)
    if base_diff is None:
        result.narrative = f"  Unknown system: {system_name}"
        return result

    # Apply penalties
    effective_pool = repair_pool
    if num_actions > 1:
        effective_pool = apply_multi_action_penalty(effective_pool, num_actions)

    total_diff = base_diff
    if in_combat:
        total_diff += 5  # Under fire penalty

    result.difficulty = total_diff

    # Roll
    roll = roll_d6_pool(effective_pool)
    result.roll_total = roll.total

    margin = roll.total - total_diff

    if margin >= 0:
        # Success
        result.success = True
        if system_name == "hull":
            # Hull repair restores 1 point of hull damage
            result.hull_repaired = 1
            result.narrative = (
                f"  Repair successful! You patch a hull breach. "
                f"(Roll: {roll.total} vs Difficulty: {total_diff})"
            )
        else:
            result.narrative = (
                f"  Repair successful! {system_name.title()} back online! "
                f"(Roll: {roll.total} vs Difficulty: {total_diff})"
            )
    elif margin >= -8:
        # Normal failure -- can try again next round
        result.narrative = (
            f"  Repair failed -- {system_name} still offline. "
            f"(Roll: {roll.total} vs Difficulty: {total_diff})"
        )
    else:
        # Catastrophic failure (margin <= -9): permanent damage
        # Star Warriors 17.27: system damaged beyond repair
        result.permanent_failure = True
        result.narrative = (
            f"  Catastrophic failure! {system_name.title()} damaged beyond repair! "
            f"Sparks fly as components fuse together. "
            f"(Roll: {roll.total} vs Difficulty: {total_diff}, margin: {margin})"
        )

    return result
