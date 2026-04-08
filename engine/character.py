# -*- coding: utf-8 -*-
"""
Character model for the D6 system.

Ties together attributes, skills, species, wounds, and Force sensitivity
into a unified Character object. Handles skill resolution (finding the
effective dice pool for any skill check) and serialization to/from the DB.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

import yaml

from engine.dice import DicePool

log = logging.getLogger(__name__)

# ── Constants ──

ATTRIBUTE_NAMES = (
    "dexterity", "knowledge", "mechanical",
    "perception", "strength", "technical",
)


# ── Wound System ──

class WoundLevel(IntEnum):
    """D6 wound levels in ascending severity."""
    HEALTHY = 0
    STUNNED = 1
    WOUNDED = 2
    WOUNDED_TWICE = 3
    INCAPACITATED = 4
    MORTALLY_WOUNDED = 5
    DEAD = 6

    @property
    def penalty_dice(self) -> int:
        """Dice penalty from this wound level."""
        return {
            0: 0, 1: 1, 2: 1, 3: 2, 4: 0, 5: 0, 6: 0
        }.get(self.value, 0)
        # Incap/mortal/dead can't act so penalty is moot

    @property
    def can_act(self) -> bool:
        return self.value <= WoundLevel.WOUNDED_TWICE

    @property
    def display_name(self) -> str:
        return self.name.replace("_", " ").title()

    @classmethod
    def from_damage_margin(cls, margin: int) -> "WoundLevel":
        """Determine wound level from damage-vs-resistance margin."""
        if margin <= 0:
            return cls.HEALTHY
        elif margin <= 3:
            return cls.STUNNED
        elif margin <= 8:
            return cls.WOUNDED
        elif margin <= 12:
            return cls.INCAPACITATED
        elif margin <= 15:
            return cls.MORTALLY_WOUNDED
        else:
            return cls.DEAD


# ── Skill Registry ──

@dataclass
class SkillDef:
    """Definition of a skill from the YAML."""
    name: str
    attribute: str  # parent attribute name
    specializations: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Lowercase lookup key."""
        return self.name.lower()


class SkillRegistry:
    """Loads skill definitions and provides lookup."""

    def __init__(self):
        self._skills: dict[str, SkillDef] = {}       # key -> SkillDef
        self._by_attribute: dict[str, list[str]] = {} # attr -> [skill keys]

    def load_file(self, path: str):
        """Load skills from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        count = 0
        for attr_name, skill_list in data.items():
            attr_name = attr_name.lower()
            self._by_attribute[attr_name] = []
            for entry in skill_list:
                sd = SkillDef(
                    name=entry["name"],
                    attribute=attr_name,
                    specializations=entry.get("specializations", []),
                )
                self._skills[sd.key] = sd
                self._by_attribute[attr_name].append(sd.key)
                count += 1

        log.info("Loaded %d skill definitions from %s", count, path)

    def get(self, name: str) -> Optional[SkillDef]:
        return self._skills.get(name.lower())

    def get_attribute_for(self, skill_name: str) -> Optional[str]:
        sd = self.get(skill_name)
        return sd.attribute if sd else None

    def skills_for_attribute(self, attr: str) -> list[SkillDef]:
        keys = self._by_attribute.get(attr.lower(), [])
        return [self._skills[k] for k in keys]

    def all_skills(self) -> list[SkillDef]:
        return list(self._skills.values())

    @property
    def count(self) -> int:
        return len(self._skills)


# ── Character ──

@dataclass
class Character:
    """
    A player or NPC character with full D6 stats.

    Attributes are stored as DicePool objects.
    Skills are stored as bonus dice ABOVE the parent attribute.
    The effective skill pool = attribute + skill bonus.
    """
    id: int = 0
    account_id: int = 0
    name: str = ""
    species_name: str = "Human"
    template: str = ""

    # Core attributes
    dexterity: DicePool = field(default_factory=lambda: DicePool(3, 0))
    knowledge: DicePool = field(default_factory=lambda: DicePool(3, 0))
    mechanical: DicePool = field(default_factory=lambda: DicePool(3, 0))
    perception: DicePool = field(default_factory=lambda: DicePool(3, 0))
    strength: DicePool = field(default_factory=lambda: DicePool(3, 0))
    technical: DicePool = field(default_factory=lambda: DicePool(3, 0))

    # Skills: {skill_name_lower: DicePool bonus above attribute}
    skills: dict[str, DicePool] = field(default_factory=dict)

    # Specializations: {spec_key: DicePool bonus above skill}
    specializations: dict[str, DicePool] = field(default_factory=dict)

    # Status
    wound_level: WoundLevel = WoundLevel.HEALTHY
    stun_count: int = 0       # Total stuns accumulated (for unconscious threshold)
    stun_rounds: int = 0      # Rounds of -1D stun penalty remaining
    mortally_wounded_rounds: int = 0  # Rounds spent mortally wounded (for death roll)
    character_points: int = 5
    force_points: int = 1
    dark_side_points: int = 0
    credits: int = 1000        # Starting credits
    force_sensitive: bool = False

    # Force attributes (0D if not force-sensitive)
    control: DicePool = field(default_factory=lambda: DicePool(0, 0))
    sense: DicePool = field(default_factory=lambda: DicePool(0, 0))
    alter: DicePool = field(default_factory=lambda: DicePool(0, 0))

    # Location & inventory
    room_id: int = 1
    description: str = ""
    equipped_weapon: str = ""  # weapon key from weapons.yaml (e.g. "blaster_pistol")

    # Movement
    move: int = 10

    def get_attribute(self, name: str) -> DicePool:
        """Get an attribute pool by name."""
        name = name.lower()
        if name in ATTRIBUTE_NAMES:
            return getattr(self, name)
        if name in ("control", "sense", "alter"):
            return getattr(self, name)
        return DicePool(0, 0)

    def set_attribute(self, name: str, pool: DicePool):
        """Set an attribute pool by name."""
        name = name.lower()
        if name in ATTRIBUTE_NAMES or name in ("control", "sense", "alter"):
            setattr(self, name, pool)

    def get_skill_pool(self, skill_name: str, skill_registry: SkillRegistry) -> DicePool:
        """
        Get the effective dice pool for a skill check.

        If the character has dice in the skill, pool = attribute + skill bonus.
        If not, they roll the raw attribute (untrained use).
        """
        key = skill_name.lower()
        skill_def = skill_registry.get(key)
        if skill_def is None:
            return DicePool(0, 0)

        attr_pool = self.get_attribute(skill_def.attribute)
        bonus = self.skills.get(key)
        if bonus:
            return attr_pool + bonus
        return attr_pool

    def get_effective_pool(
        self, skill_name: str, skill_registry: SkillRegistry,
        num_actions: int = 1
    ) -> DicePool:
        """
        Get effective pool after applying wound and multi-action penalties.
        """
        from engine.dice import apply_multi_action_penalty, apply_wound_penalty
        pool = self.get_skill_pool(skill_name, skill_registry)
        pool = apply_wound_penalty(pool, self.wound_level.penalty_dice)
        pool = apply_multi_action_penalty(pool, num_actions)
        return pool

    def add_skill(self, skill_name: str, bonus: DicePool):
        """Set a skill bonus (dice above the parent attribute)."""
        self.skills[skill_name.lower()] = bonus

    def advance_skill(self, skill_name: str, skill_registry: SkillRegistry) -> int:
        """
        Advance a skill by 1 pip. Returns CP cost.
        Cost = current number of dice in the skill.
        If skill is above attribute, cost is doubled.
        """
        key = skill_name.lower()
        skill_def = skill_registry.get(key)
        if not skill_def:
            return 0

        current_bonus = self.skills.get(key, DicePool(0, 0))
        attr_pool = self.get_attribute(skill_def.attribute)
        total_pool = attr_pool + current_bonus

        # Cost = current dice count (doubled if above attribute)
        cost = total_pool.dice
        if current_bonus.dice > 0:
            cost = total_pool.dice  # Above attribute = full cost per die

        # Advance by 1 pip
        new_bonus = DicePool(current_bonus.dice, current_bonus.pips + 1)
        self.skills[key] = new_bonus

        return cost

    def apply_wound(self, margin: int) -> WoundLevel:
        """
        Apply damage from a combat hit per R&E 2nd Edition rules.

        R&E wound stacking:
          Stunned: -1D rest of round + next round. If stun_count equals
            STR dice, character is knocked unconscious 20 minutes.
          Wounded: fall prone, no actions rest of round. -1D until healed.
            Second wound -> Incapacitated.
          Incapacitated: unconscious 100 minutes. Another wound -> MW.
          Mortally Wounded: unconscious, dying. Each round roll 2D;
            if roll < rounds_MW, character dies. Another wound -> Dead.
          Dead: Dead.

        Returns the new wound level.
        """
        incoming = WoundLevel.from_damage_margin(margin)
        if incoming == WoundLevel.HEALTHY:
            return self.wound_level

        if incoming == WoundLevel.STUNNED:
            self.stun_count += 1
            self.stun_rounds = 2  # Rest of current round + next round

            # Check stun knockout: stuns >= STR dice = unconscious (R&E p59)
            str_dice = self.strength.dice
            if str_dice > 0 and self.stun_count >= str_dice:
                self.wound_level = max(self.wound_level, WoundLevel.INCAPACITATED)
                return self.wound_level

            if self.wound_level < WoundLevel.STUNNED:
                self.wound_level = WoundLevel.STUNNED
            return self.wound_level

        if incoming == WoundLevel.WOUNDED:
            if self.wound_level >= WoundLevel.MORTALLY_WOUNDED:
                # Any further damage to mortally wounded = dead
                self.wound_level = WoundLevel.DEAD
            elif self.wound_level >= WoundLevel.INCAPACITATED:
                # Incap + wound -> mortally wounded (R&E p59)
                self.wound_level = WoundLevel.MORTALLY_WOUNDED
            elif self.wound_level >= WoundLevel.WOUNDED:
                # Second wound -> incapacitated (R&E p59)
                self.wound_level = WoundLevel.INCAPACITATED
            else:
                self.wound_level = WoundLevel.WOUNDED
            return self.wound_level

        if incoming == WoundLevel.INCAPACITATED:
            if self.wound_level >= WoundLevel.MORTALLY_WOUNDED:
                # MW + incap -> dead (R&E p59)
                self.wound_level = WoundLevel.DEAD
            elif self.wound_level >= WoundLevel.INCAPACITATED:
                # Incap + incap -> mortally wounded
                self.wound_level = WoundLevel.MORTALLY_WOUNDED
            else:
                self.wound_level = WoundLevel.INCAPACITATED
            return self.wound_level

        if incoming == WoundLevel.MORTALLY_WOUNDED:
            if self.wound_level >= WoundLevel.MORTALLY_WOUNDED:
                self.wound_level = WoundLevel.DEAD
            else:
                self.wound_level = WoundLevel.MORTALLY_WOUNDED
                self.mortally_wounded_rounds = 0
            return self.wound_level

        if incoming == WoundLevel.DEAD:
            self.wound_level = WoundLevel.DEAD
            return self.wound_level

        # Fallback: take the worse level
        if incoming.value > self.wound_level.value:
            self.wound_level = incoming
        return self.wound_level

    # ── Serialization ──

    def to_db_dict(self) -> dict:
        """Serialize to a dict matching the DB schema."""
        attrs = {a: str(self.get_attribute(a)) for a in ATTRIBUTE_NAMES}
        if self.force_sensitive:
            attrs["control"] = str(self.control)
            attrs["sense"] = str(self.sense)
            attrs["alter"] = str(self.alter)

        skills = {k: str(v) for k, v in self.skills.items()}

        equipment = {}
        if self.equipped_weapon:
            equipment["weapon"] = self.equipped_weapon

        return {
            "name": self.name,
            "species": self.species_name,
            "template": self.template,
            "attributes": json.dumps(attrs),
            "skills": json.dumps(skills),
            "wound_level": self.wound_level.value,
            "character_points": self.character_points,
            "force_points": self.force_points,
            "dark_side_points": self.dark_side_points,
            "credits": self.credits,
            "room_id": self.room_id,
            "description": self.description,
            "equipment": json.dumps(equipment),
        }

    @classmethod
    def from_npc_sheet(cls, npc_id: int, sheet: dict) -> "Character":
        """
        Build a Character from an NPC char_sheet_json dict.

        The sheet format matches generate_npc() output:
          {
            "name": "...",
            "species": "Human",
            "attributes": {"dexterity": "3D+1", ...},
            "skills": {"blaster": "2D", ...},  # bonus above attribute
            "force_points": 1,
            "character_points": 5,
            "move": 10,
            "weapon": "blaster_pistol",  # optional weapon key
            "force_sensitive": false,
            "force_skills": {"control": "2D", ...},  # optional
            ...
          }
        """
        char = cls()
        char.id = npc_id
        char.account_id = 0  # NPCs have no account
        char.name = sheet.get("name", f"NPC #{npc_id}")
        char.species_name = sheet.get("species", "Human")
        char.template = sheet.get("template", "")
        char.character_points = sheet.get("character_points", 0)
        char.force_points = sheet.get("force_points", 0)
        char.dark_side_points = sheet.get("dark_side_points", 0)
        char.credits = sheet.get("credits", 0)
        char.move = sheet.get("move", 10)
        char.wound_level = WoundLevel(sheet.get("wound_level", 0))

        # Attributes
        attrs = sheet.get("attributes", {})
        for attr_name in ATTRIBUTE_NAMES:
            if attr_name in attrs:
                char.set_attribute(attr_name, DicePool.parse(attrs[attr_name]))

        # Skills (bonus above attribute)
        skills = sheet.get("skills", {})
        for skill_name, pool_str in skills.items():
            char.skills[skill_name.lower()] = DicePool.parse(str(pool_str))

        # Force
        char.force_sensitive = sheet.get("force_sensitive", False)
        force_skills = sheet.get("force_skills", {})
        for fa in ("control", "sense", "alter"):
            if fa in force_skills:
                char.set_attribute(fa, DicePool.parse(force_skills[fa]))
                char.force_sensitive = True
            elif fa in attrs:
                char.set_attribute(fa, DicePool.parse(attrs[fa]))
                char.force_sensitive = True

        # Weapon
        char.equipped_weapon = sheet.get("weapon", "")

        return char

    @classmethod
    def from_db_dict(cls, data: dict) -> "Character":
        """Deserialize from a DB row dict."""
        char = cls()
        char.id = data.get("id", 0)
        char.account_id = data.get("account_id", 0)
        char.name = data.get("name", "")
        char.species_name = data.get("species", "Human")
        char.template = data.get("template", "")
        char.room_id = data.get("room_id", 1)
        char.description = data.get("description", "")
        char.character_points = data.get("character_points", 5)
        char.force_points = data.get("force_points", 1)
        char.dark_side_points = data.get("dark_side_points", 0)
        char.credits = data.get("credits", 1000)
        char.wound_level = WoundLevel(data.get("wound_level", 0))

        # Parse attributes
        attrs = data.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        for attr_name in ATTRIBUTE_NAMES:
            if attr_name in attrs:
                char.set_attribute(attr_name, DicePool.parse(attrs[attr_name]))
        for force_attr in ("control", "sense", "alter"):
            if force_attr in attrs:
                char.set_attribute(force_attr, DicePool.parse(attrs[force_attr]))
                char.force_sensitive = True

        # Parse skills
        skills = data.get("skills", "{}")
        if isinstance(skills, str):
            skills = json.loads(skills)
        for skill_name, pool_str in skills.items():
            char.skills[skill_name.lower()] = DicePool.parse(pool_str)

        # Parse equipment
        equip = data.get("equipment", "{}")
        if isinstance(equip, str):
            try:
                equip = json.loads(equip)
            except (json.JSONDecodeError, TypeError):
                equip = {}
        if isinstance(equip, dict):
            char.equipped_weapon = equip.get("weapon", "")

        return char

    def format_sheet(self, skill_registry: SkillRegistry, width: int = 78) -> str:
        """Render a full character sheet for display."""
        lines = []
        sep = "=" * width
        lines.append(sep)
        lines.append(f"  {self.name}  |  {self.species_name}  |  {self.template or 'No Template'}")
        lines.append(sep)

        # Wound status
        if self.wound_level > WoundLevel.HEALTHY:
            lines.append(f"  Status: {self.wound_level.display_name} (-{self.wound_level.penalty_dice}D)")
        else:
            lines.append("  Status: Healthy")

        lines.append(f"  CP: {self.character_points}  |  FP: {self.force_points}  |  DSP: {self.dark_side_points}  |  Credits: {self.credits:,}")
        lines.append(f"  Move: {self.move}")
        lines.append("")

        # Attributes and skills
        for attr_name in ATTRIBUTE_NAMES:
            attr_pool = self.get_attribute(attr_name)
            lines.append(f"  {attr_name.upper():15s} {attr_pool}")

            # Skills under this attribute
            skill_defs = skill_registry.skills_for_attribute(attr_name)
            for sd in skill_defs:
                bonus = self.skills.get(sd.key)
                if bonus:
                    total = attr_pool + bonus
                    lines.append(f"    {sd.name:25s} {total}  (+{bonus})")
            lines.append("")

        # Force attributes
        if self.force_sensitive:
            lines.append("  FORCE ATTRIBUTES:")
            lines.append(f"    Control:  {self.control}")
            lines.append(f"    Sense:    {self.sense}")
            lines.append(f"    Alter:    {self.alter}")
            lines.append("")

        lines.append(sep)
        return "\n".join(lines)
