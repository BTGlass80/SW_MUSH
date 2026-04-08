"""
Species data loader.

Reads species definitions from YAML files in data/species/.
Provides lookup, listing, and attribute validation for character creation.
"""
import os
import logging
from dataclasses import dataclass, field
from typing import Optional

import yaml

from engine.dice import DicePool

log = logging.getLogger(__name__)


@dataclass
class SpecialAbility:
    """A species-specific ability."""
    name: str = ""
    description: str = ""


@dataclass
class AttributeRange:
    """Min/max for a single attribute."""
    min_pool: DicePool = field(default_factory=lambda: DicePool(2, 0))
    max_pool: DicePool = field(default_factory=lambda: DicePool(4, 0))


@dataclass
class Species:
    """Complete species definition."""
    name: str = ""
    description: str = ""
    homeworld: str = ""
    attributes: dict[str, AttributeRange] = field(default_factory=dict)
    attribute_dice: DicePool = field(default_factory=lambda: DicePool(12, 0))
    skill_dice: DicePool = field(default_factory=lambda: DicePool(7, 0))
    special_abilities: list[SpecialAbility] = field(default_factory=list)
    move: int = 10
    swim: Optional[int] = None
    story_factors: list[str] = field(default_factory=list)

    def validate_attributes(self, attrs: dict[str, DicePool]) -> list[str]:
        """
        Validate a set of attribute allocations against species limits.
        Returns a list of error messages (empty = valid).
        """
        errors = []
        total_pips = 0

        for attr_name in ("dexterity", "knowledge", "mechanical",
                          "perception", "strength", "technical"):
            pool = attrs.get(attr_name)
            if pool is None:
                errors.append(f"Missing attribute: {attr_name}")
                continue

            range_def = self.attributes.get(attr_name)
            if range_def is None:
                continue

            pool_pips = pool.total_pips()
            min_pips = range_def.min_pool.total_pips()
            max_pips = range_def.max_pool.total_pips()

            if pool_pips < min_pips:
                errors.append(
                    f"{attr_name}: {pool} is below minimum {range_def.min_pool} "
                    f"for {self.name}"
                )
            if pool_pips > max_pips:
                errors.append(
                    f"{attr_name}: {pool} exceeds maximum {range_def.max_pool} "
                    f"for {self.name}"
                )

            total_pips += pool_pips

        # Check total allocation
        expected = self.attribute_dice.total_pips()
        if total_pips != expected:
            errors.append(
                f"Total attribute allocation is {total_pips} pips "
                f"(expected {expected} pips / {self.attribute_dice})"
            )

        return errors

    def format_display(self, width: int = 78) -> str:
        """Format species info for in-game display."""
        lines = []
        lines.append(f"=== {self.name} ===")
        lines.append("")

        # Word-wrap description
        import textwrap
        for line in textwrap.wrap(self.description.strip(), width=width - 2):
            lines.append(f"  {line}")
        lines.append("")

        lines.append(f"  Homeworld: {self.homeworld}")
        lines.append(f"  Move: {self.move}" + (f"  Swim: {self.swim}" if self.swim else ""))
        lines.append("")

        lines.append("  Attribute Ranges:")
        for attr_name in ("dexterity", "knowledge", "mechanical",
                          "perception", "strength", "technical"):
            r = self.attributes.get(attr_name)
            if r:
                label = attr_name.capitalize()
                lines.append(f"    {label:15s} {r.min_pool} - {r.max_pool}")
        lines.append("")

        if self.special_abilities:
            lines.append("  Special Abilities:")
            for ability in self.special_abilities:
                lines.append(f"    {ability.name}:")
                for line in textwrap.wrap(ability.description.strip(), width=width - 6):
                    lines.append(f"      {line}")
            lines.append("")

        if self.story_factors:
            lines.append("  Story Factors:")
            for factor in self.story_factors:
                for line in textwrap.wrap(factor.strip(), width=width - 6):
                    lines.append(f"    - {line}")
            lines.append("")

        return "\n".join(lines)


def _parse_species(data: dict) -> Species:
    """Parse a raw YAML dict into a Species object."""
    # Parse attribute ranges
    attrs = {}
    for attr_name, range_data in data.get("attributes", {}).items():
        attrs[attr_name] = AttributeRange(
            min_pool=DicePool.parse(range_data["min"]),
            max_pool=DicePool.parse(range_data["max"]),
        )

    # Parse special abilities
    abilities = []
    for ab_data in data.get("special_abilities", []):
        if isinstance(ab_data, dict):
            abilities.append(SpecialAbility(
                name=ab_data.get("name", ""),
                description=ab_data.get("description", ""),
            ))

    return Species(
        name=data.get("name", "Unknown"),
        description=data.get("description", ""),
        homeworld=data.get("homeworld", "Unknown"),
        attributes=attrs,
        attribute_dice=DicePool.parse(data.get("attribute_dice", "12D")),
        skill_dice=DicePool.parse(data.get("skill_dice", "7D")),
        special_abilities=abilities,
        move=data.get("move", 10),
        swim=data.get("swim"),
        story_factors=data.get("story_factors", []),
    )


class SpeciesRegistry:
    """Loads and stores all species definitions."""

    def __init__(self):
        self._species: dict[str, Species] = {}

    def load_directory(self, path: str):
        """Load all YAML files from a directory."""
        if not os.path.isdir(path):
            log.warning("Species directory not found: %s", path)
            return

        count = 0
        for filename in sorted(os.listdir(path)):
            if filename.endswith((".yaml", ".yml")):
                filepath = os.path.join(path, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    species = _parse_species(data)
                    self._species[species.name.lower()] = species
                    count += 1
                    log.debug("Loaded species: %s", species.name)
                except Exception as e:
                    log.error("Failed to load species from %s: %s", filepath, e)

        log.info("Loaded %d species definitions from %s", count, path)

    def get(self, name: str) -> Optional[Species]:
        """Look up a species by name (case-insensitive)."""
        return self._species.get(name.lower())

    def list_names(self) -> list[str]:
        """Get all species names in sorted order."""
        return sorted(s.name for s in self._species.values())

    def list_all(self) -> list[Species]:
        """Get all species objects."""
        return sorted(self._species.values(), key=lambda s: s.name)

    @property
    def count(self) -> int:
        return len(self._species)
