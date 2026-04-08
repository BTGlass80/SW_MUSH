"""
Weapon data loader and range mechanics.

Per R&E 2nd Edition combat rules:
  - Ranged attacks use weapon range bands to determine BASE DIFFICULTY
  - Dodge ADDS to that difficulty (not opposed roll)
  - Melee attacks use opposed rolls (attacker skill vs parry)

Range Band -> Difficulty:
  Point-blank (< short_min):  Very Easy (5)
  Short:                      Easy (10)
  Medium:                     Moderate (15)
  Long:                       Difficult (20)
  Beyond long:                Out of range (cannot hit)
"""
import os
import yaml
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from engine.dice import DicePool

log = logging.getLogger(__name__)


class RangeBand(IntEnum):
    """Range bands per R&E, mapped to base difficulty numbers."""
    POINT_BLANK = 5    # Very Easy
    SHORT = 10         # Easy
    MEDIUM = 15        # Moderate
    LONG = 20          # Difficult
    OUT_OF_RANGE = 99  # Cannot hit

    @property
    def label(self) -> str:
        return {
            5: "Point-Blank",
            10: "Short",
            15: "Medium",
            20: "Long",
            99: "Out of Range",
        }[self.value]


@dataclass
class WeaponData:
    """Parsed weapon stats from weapons.yaml."""
    key: str
    name: str
    weapon_type: str          # blaster, melee, lightsaber, grenade, bowcaster
    skill: str                # Skill used to fire/wield
    damage: str               # Damage dice string (e.g. "4D", "STR+2D")
    scale: str = "character"
    cost: int = 0
    ammo: int = 0
    stun_capable: bool = False
    notes: str = ""

    # Range data (for ranged weapons only)
    # [point_blank_min, short_max, medium_max, long_max]
    ranges: list[int] = field(default_factory=list)

    # Melee difficulty (for melee weapons)
    melee_difficulty: str = ""  # "easy", "moderate", "difficult"

    # Grenade blast radius data
    blast_radius: list[int] = field(default_factory=list)
    blast_damage: list[str] = field(default_factory=list)

    # Armor fields (for armor items)
    protection_energy: str = ""
    protection_physical: str = ""
    covers: list[str] = field(default_factory=list)
    dexterity_penalty: str = ""

    @property
    def is_ranged(self) -> bool:
        return len(self.ranges) == 4

    @property
    def is_melee(self) -> bool:
        return self.weapon_type in ("melee", "lightsaber")

    @property
    def is_armor(self) -> bool:
        return self.weapon_type == "armor"

    def get_range_band(self, distance_meters: int) -> RangeBand:
        """
        Determine the range band for a given distance.
        Returns the base difficulty number for that band.
        """
        if not self.ranges or len(self.ranges) != 4:
            return RangeBand.SHORT  # Default for weapons without range data

        pb_min, short_max, medium_max, long_max = self.ranges

        if distance_meters < pb_min:
            return RangeBand.POINT_BLANK
        elif distance_meters <= short_max:
            return RangeBand.SHORT
        elif distance_meters <= medium_max:
            return RangeBand.MEDIUM
        elif distance_meters <= long_max:
            return RangeBand.LONG
        else:
            return RangeBand.OUT_OF_RANGE

    def format_ranges(self) -> str:
        """Format range bands for display (e.g. on character sheet)."""
        if not self.ranges or len(self.ranges) != 4:
            return "Melee" if self.is_melee else "N/A"
        pb, s, m, l = self.ranges
        return f"{pb}-{s}/{m}/{l}"

    def format_short(self) -> str:
        """Short display: name, damage, ranges."""
        if self.is_melee:
            return f"{self.name:22s} {self.damage:>8s}  Melee"
        elif self.ranges:
            return (
                f"{self.name:22s} {self.damage:>8s}  "
                f"{self.ranges[1]:>4d}  {self.ranges[2]:>4d}  {self.ranges[3]:>4d}"
            )
        return f"{self.name:22s} {self.damage:>8s}"


class WeaponRegistry:
    """Loads and stores weapon data from YAML."""

    def __init__(self):
        self._weapons: dict[str, WeaponData] = {}

    def load_file(self, path: str):
        """Load weapons from a YAML file."""
        if not os.path.exists(path):
            log.warning("Weapon data file not found: %s", path)
            return

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return

        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            weapon = WeaponData(
                key=key,
                name=entry.get("name", key),
                weapon_type=entry.get("type", "blaster"),
                skill=entry.get("skill", "blaster"),
                damage=entry.get("damage", "3D"),
                scale=entry.get("scale", "character"),
                cost=entry.get("cost", 0),
                ammo=entry.get("ammo", 0),
                stun_capable=entry.get("stun_capable", False),
                notes=entry.get("notes", ""),
                ranges=entry.get("ranges", []),
                melee_difficulty=entry.get("difficulty", ""),
                blast_radius=entry.get("blast_radius", []),
                blast_damage=entry.get("blast_damage", []),
                protection_energy=entry.get("protection_energy", ""),
                protection_physical=entry.get("protection_physical", ""),
                covers=entry.get("covers", []),
                dexterity_penalty=entry.get("dexterity_penalty", ""),
            )
            self._weapons[key] = weapon

        log.info("Loaded %d weapons from %s", len(self._weapons), path)

    def get(self, key: str) -> Optional[WeaponData]:
        """Get weapon by key (e.g. 'blaster_pistol')."""
        return self._weapons.get(key.lower().replace(" ", "_"))

    def find_by_name(self, name: str) -> Optional[WeaponData]:
        """Find weapon by partial name match."""
        name_lower = name.lower()
        # Exact match first
        for w in self._weapons.values():
            if w.name.lower() == name_lower:
                return w
        # Prefix match
        for w in self._weapons.values():
            if w.name.lower().startswith(name_lower):
                return w
        # Contains match
        for w in self._weapons.values():
            if name_lower in w.name.lower():
                return w
        return None

    def all_weapons(self) -> list[WeaponData]:
        """Get all non-armor weapons."""
        return [w for w in self._weapons.values() if not w.is_armor]

    def all_armor(self) -> list[WeaponData]:
        """Get all armor items."""
        return [w for w in self._weapons.values() if w.is_armor]

    def all(self) -> list[WeaponData]:
        """Get everything."""
        return list(self._weapons.values())

    @property
    def count(self) -> int:
        return len(self._weapons)


# -- Module-level convenience --

_default_registry: Optional[WeaponRegistry] = None


def get_weapon_registry() -> WeaponRegistry:
    """Get or create the default weapon registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = WeaponRegistry()
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        weapons_path = os.path.join(data_dir, "weapons.yaml")
        _default_registry.load_file(weapons_path)
    return _default_registry
