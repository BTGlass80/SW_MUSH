"""
Starship Engine — Star Wars D6 Revised & Expanded

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
  - Destroyed systems are permanent — no further repair possible
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


# ── Scale system (R&E p101) ──
SCALE_STARFIGHTER = 0
SCALE_CAPITAL = 6


# ── Space Range Bands ──
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


# ── Relative Position (for fire arcs) ──

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


# ── Space Grid ──
# Tracks pairwise range and relative position between all ships in a sector

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
                f"you're behind them — their rear weapons only! "
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
        """Format tactical display for a ship — ranges and positions to all contacts."""
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
        with open(path) as f:
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


# ── Space Combat Resolution ──

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

    # Total difficulty: range modifier + defense roll
    range_mod = int(range_band)
    total_difficulty = range_mod + defense_roll.total

    result.attack_roll = attack_roll.total
    result.defense_roll = total_difficulty
    result.hit = attack_roll.total >= total_difficulty

    range_label = range_band.label

    if not result.hit:
        result.narrative = (
            f"  Shot misses at {range_label} range! "
            f"(Attack: {result.attack_roll} vs "
            f"Diff: {range_label}({range_mod}) + Evade({defense_roll.total}) "
            f"= {total_difficulty})"
        )
        return result

    # ── Hit! Roll damage ──
    damage_pool = DicePool.parse(weapon.damage)

    # Scale modifier for damage
    if scale_diff > 0:
        # Starfighter hitting capital: -6D damage (but easier to hit)
        damage_pool = DicePool(max(1, damage_pool.dice - scale_diff), damage_pool.pips)
    elif scale_diff < 0:
        # Capital hitting starfighter: +6D damage (but harder to hit)
        damage_pool = DicePool(damage_pool.dice + abs(scale_diff), damage_pool.pips)

    # Soak: hull + shields
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
        # Ion damage disables systems
        if margin > 0:
            if margin <= 5:
                result.ion_disabled = "controls_ionized"
                result.narrative = (
                    f"  Ion hit! Controls ionized for 1 round. "
                    f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll})"
                )
            elif margin <= 10:
                result.ion_disabled = "dead_in_space"
                result.narrative = (
                    f"  Ion hit! Ship is dead in space! "
                    f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll})"
                )
            else:
                result.ion_disabled = "systems_overloaded"
                result.narrative = (
                    f"  Massive ion hit! All systems overloaded! "
                    f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll})"
                )
        else:
            result.narrative = (
                f"  Ion shot absorbed by hull. "
                f"(Damage: {result.damage_roll} vs Soak: {result.soak_roll})"
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


# ── Damage Control (Star Warriors Section 17, adapted for D6 R&E) ──

# Repairable systems and their base difficulties (R&E Technical skill check)
REPAIR_DIFFICULTIES = {
    "shields":    15,  # Moderate — reroute power, reset breakers
    "sensors":    15,  # Moderate — recalibrate, swap modules
    "engines":    20,  # Difficult — mechanical, dangerous
    "weapons":    20,  # Difficult — realign, replace components
    "hyperdrive": 25,  # Very Difficult — precision calibration
    "hull":       20,  # Difficult — patch breaches under fire
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
    scale_lower = scale.lower()
    if scale_lower == "capital":
        return "capital_ship_repair"
    elif scale_lower in ("starfighter", "fighter"):
        return "starfighter_repair"
    else:
        return "space_transport_repair"


def get_weapon_repair_skill() -> str:
    """Weapon-specific repair uses its own skill."""
    return "starship_weapon_repair"


@dataclass
class DamageControlResult:
    """Result of a damage control attempt."""
    system: str = ""
    success: bool = False
    permanent_failure: bool = False  # System now destroyed, unrepairable
    hull_repaired: int = 0           # Hull damage points restored (hull only)
    roll_total: int = 0
    difficulty: int = 0
    skill_used: str = ""
    narrative: str = ""


def resolve_damage_control(
    repair_skill: DicePool,
    system_name: str,
    current_state: str,
    ship_scale: str = "starfighter",
    in_combat: bool = True,
    num_actions: int = 1,
) -> DamageControlResult:
    """
    Resolve a damage control attempt per Star Warriors Section 17 / R&E.

    Args:
        repair_skill: Technical + repair skill dice pool
        system_name: which system to repair (engines, weapons, shields, etc.)
        current_state: 'damaged' or 'destroyed' (from get_system_state)
        ship_scale: for narrative flavor
        in_combat: if True, +5 difficulty (working under fire)
        num_actions: for multi-action penalty if doing other things this round

    Returns:
        DamageControlResult with success/failure and narrative.
    """
    result = DamageControlResult(system=system_name)

    # Can't repair what isn't broken
    if current_state == "working":
        result.narrative = f"  {system_name.title()} are already operational!"
        return result

    # Can't repair destroyed systems (Star Warriors 17.27)
    if current_state == "destroyed":
        result.narrative = (
            f"  {system_name.title()} are damaged beyond repair. "
            f"You'll need a spacedock for this."
        )
        return result

    # Look up base difficulty
    base_diff = REPAIR_DIFFICULTIES.get(system_name, 20)
    combat_mod = 5 if in_combat else 0
    total_diff = base_diff + combat_mod
    result.difficulty = total_diff

    # Determine skill name for display
    if system_name == "weapons":
        result.skill_used = get_weapon_repair_skill()
    else:
        result.skill_used = get_repair_skill_name(ship_scale)

    # Apply multi-action penalty if repairing while doing other things
    pool = apply_multi_action_penalty(repair_skill, num_actions)

    # Roll it
    roll = roll_d6_pool(pool)
    result.roll_total = roll.total

    margin = roll.total - total_diff

    if margin >= 0:
        # Success!
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
        # Normal failure — can try again next round
        result.narrative = (
            f"  Repair failed — {system_name} still offline. "
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
