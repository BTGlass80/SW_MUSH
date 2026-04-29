"""
NPC Generator -- Universe Standard (GM Handbook 2nd Edition).

Generates balanced NPC stat blocks using the official WEG dice
budget system from the Gamemaster Handbook, Chapter 4.

Universe Standard skill levels:
  1D  Below Human average
  2D  Human average for attributes and many skills
  3D  Average level of training
  4D  Professional level
  5D  Above average expertise
  6D  Among the best in a region
  7D  Among the best on a planet
  8D  Among the best in several systems
  9D  One of the best in a sector
  10D One of the best in a region
  12D+ Among the best in the galaxy

Character experience tiers (total dice incl. attrs + skills + FP/CP equiv):
  Average:  ≤20D
  Novice:   ≤35D  (beginning PCs are 26D: 18D attrs + 7D skills + 1 FP)
  Veteran:  36-75D
  Superior: 76-150D
"""
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.dice import DicePool
from engine.character import ATTRIBUTE_NAMES


class NPCTier(Enum):
    """Experience tier per GM Handbook Universe Standard."""
    EXTRA = "extra"          # Walk-on, minimal stats (≤15D total)
    AVERAGE = "average"      # Truly average, 1-2 adventures (≤20D)
    NOVICE = "novice"        # Slightly above avg, ~beginning PC (≤35D)
    VETERAN = "veteran"      # Experienced, good at key skills (36-75D)
    SUPERIOR = "superior"    # Formidable, major challenge (76-150D)


@dataclass
class NPCArchetype:
    """Defines how dice are distributed for a character concept."""
    name: str
    # Primary attributes get higher baseline; secondary get lower
    primary_attrs: list[str]      # Get highest dice
    secondary_attrs: list[str]    # Get medium dice
    # Skills to emphasize (will get extra dice)
    primary_skills: list[str]
    secondary_skills: list[str]
    # Optional flavor
    move: int = 10
    force_sensitive: bool = False


# -- Pre-built Archetypes --
# Based on the character templates and NPC examples from the rulebooks

ARCHETYPES: dict[str, NPCArchetype] = {
    "stormtrooper": NPCArchetype(
        name="Stormtrooper",
        primary_attrs=["dexterity", "strength"],
        secondary_attrs=["perception", "mechanical"],
        primary_skills=["blaster", "brawling", "dodge"],
        secondary_skills=["melee combat", "search", "stamina"],
    ),
    "scout_trooper": NPCArchetype(
        name="Scout Trooper",
        primary_attrs=["dexterity", "mechanical"],
        secondary_attrs=["perception", "strength"],
        primary_skills=["blaster", "vehicle blasters", "repulsorlift operation"],
        secondary_skills=["dodge", "search", "sneak", "survival"],
    ),
    "imperial_officer": NPCArchetype(
        name="Imperial Officer",
        primary_attrs=["knowledge", "perception"],
        secondary_attrs=["dexterity", "mechanical"],
        primary_skills=["bureaucracy", "command", "tactics"],
        secondary_skills=["blaster", "intimidation", "planetary systems", "willpower"],
    ),
    "bounty_hunter": NPCArchetype(
        name="Bounty Hunter",
        primary_attrs=["dexterity", "perception"],
        secondary_attrs=["strength", "knowledge"],
        primary_skills=["blaster", "dodge", "search", "sneak", "investigation"],
        secondary_skills=["brawling", "melee combat", "intimidation",
                          "streetwise", "tracking", "starfighter piloting"],
    ),
    "smuggler": NPCArchetype(
        name="Smuggler",
        primary_attrs=["dexterity", "mechanical"],
        secondary_attrs=["perception", "technical"],
        primary_skills=["blaster", "dodge", "space transports",
                        "starship gunnery", "astrogation"],
        secondary_skills=["con", "bargain", "streetwise", "sneak",
                          "space transports repair", "hide"],
    ),
    "pilot": NPCArchetype(
        name="Pilot",
        primary_attrs=["mechanical", "dexterity"],
        secondary_attrs=["perception", "technical"],
        primary_skills=["starfighter piloting", "starship gunnery",
                        "space transports", "astrogation", "sensors"],
        secondary_skills=["dodge", "blaster", "starship shields",
                          "starfighter repair"],
    ),
    "mechanic": NPCArchetype(
        name="Mechanic",
        primary_attrs=["technical", "mechanical"],
        secondary_attrs=["knowledge", "strength"],
        primary_skills=["space transports repair", "starfighter repair",
                        "droid repair", "repulsorlift repair"],
        secondary_skills=["computer programming/repair", "first aid",
                          "blaster", "space transports"],
    ),
    "thug": NPCArchetype(
        name="Thug",
        primary_attrs=["strength", "dexterity"],
        secondary_attrs=["perception"],
        primary_skills=["brawling", "melee combat", "intimidation"],
        secondary_skills=["blaster", "dodge", "streetwise", "stamina"],
    ),
    "merchant": NPCArchetype(
        name="Merchant",
        primary_attrs=["perception", "knowledge"],
        secondary_attrs=["technical", "mechanical"],
        primary_skills=["bargain", "con", "persuasion", "value"],
        secondary_skills=["alien species", "bureaucracy", "languages",
                          "planetary systems"],
    ),
    "medic": NPCArchetype(
        name="Medic",
        primary_attrs=["technical", "knowledge"],
        secondary_attrs=["perception", "dexterity"],
        primary_skills=["first aid", "medicine", "alien species"],
        secondary_skills=["dodge", "search", "scholar", "computer programming/repair"],
    ),
    "scout": NPCArchetype(
        name="Scout",
        primary_attrs=["mechanical", "knowledge"],
        secondary_attrs=["perception", "dexterity"],
        primary_skills=["astrogation", "sensors", "planetary systems",
                        "survival", "space transports"],
        secondary_skills=["dodge", "blaster", "search", "sneak",
                          "repulsorlift operation"],
    ),
    "jedi": NPCArchetype(
        name="Jedi",
        primary_attrs=["dexterity", "perception"],
        secondary_attrs=["knowledge", "strength"],
        primary_skills=["lightsaber", "dodge", "running"],
        secondary_skills=["melee parry", "search", "persuasion",
                          "willpower", "scholar"],
        force_sensitive=True,
    ),
    "dark_jedi": NPCArchetype(
        name="Dark Jedi",
        primary_attrs=["dexterity", "perception"],
        secondary_attrs=["knowledge", "strength"],
        primary_skills=["lightsaber", "dodge", "intimidation"],
        secondary_skills=["melee combat", "willpower", "command"],
        force_sensitive=True,
    ),
    "noble": NPCArchetype(
        name="Noble / Diplomat",
        primary_attrs=["perception", "knowledge"],
        secondary_attrs=["dexterity", "mechanical"],
        primary_skills=["command", "persuasion", "bureaucracy", "languages"],
        secondary_skills=["bargain", "alien species", "willpower",
                          "blaster", "dodge"],
    ),
    "creature": NPCArchetype(
        name="Creature",
        primary_attrs=["strength", "dexterity", "perception"],
        secondary_attrs=[],
        primary_skills=["brawling"],
        secondary_skills=["sneak", "search", "running", "stamina"],
    ),
    # ── B.1.g (Apr 29 2026) — CW archetypes ──────────────────────────
    # Per Brian's Apr 29 directive: "the CW pivot needs to be complete."
    # CW analogues for the four GCW Imperial-spec archetypes plus a
    # B1 battle droid (CIS) and Jedi Knight (Jedi Order) round out the
    # roster. Skill loadouts mirror the GCW counterparts so per-tier
    # NPC generation produces sensible CW NPCs for spawning, fugitive
    # rolls, and CW bounty boards.
    "clone_trooper": NPCArchetype(
        name="Clone Trooper",
        primary_attrs=["dexterity", "strength"],
        secondary_attrs=["perception", "mechanical"],
        primary_skills=["blaster", "brawling", "dodge"],
        secondary_skills=["melee combat", "search", "stamina", "tactics"],
    ),
    "arc_trooper": NPCArchetype(
        name="ARC Trooper",
        primary_attrs=["dexterity", "perception"],
        secondary_attrs=["strength", "knowledge"],
        primary_skills=["blaster", "dodge", "sneak", "tactics"],
        secondary_skills=["melee combat", "search", "command", "demolitions",
                          "stamina"],
    ),
    "republic_officer": NPCArchetype(
        name="Republic Officer",
        primary_attrs=["knowledge", "perception"],
        secondary_attrs=["dexterity", "mechanical"],
        primary_skills=["bureaucracy", "command", "tactics"],
        secondary_skills=["blaster", "intimidation", "planetary systems",
                          "willpower"],
    ),
    "b1_battle_droid": NPCArchetype(
        name="B1 Battle Droid",
        primary_attrs=["dexterity"],
        secondary_attrs=["strength", "perception"],
        primary_skills=["blaster", "dodge"],
        secondary_skills=["search", "melee combat"],
    ),
    "jedi_knight": NPCArchetype(
        name="Jedi Knight",
        primary_attrs=["perception", "dexterity"],
        secondary_attrs=["knowledge", "strength"],
        primary_skills=["lightsaber", "dodge", "control", "sense", "alter"],
        secondary_skills=["melee combat", "willpower", "command",
                          "alien species"],
        force_sensitive=True,
    ),
}


# -- Tier Budget Tables --
# These define attribute ranges and skill dice by tier.
# Attribute dice = total pips across 6 attributes.
# Skill dice = total extra pips in skills above attribute.

@dataclass
class TierBudget:
    """Dice budget for a given tier."""
    attr_pips_min: int     # Min total attribute pips
    attr_pips_max: int     # Max total attribute pips
    skill_pips_min: int    # Min total skill pips
    skill_pips_max: int    # Max total skill pips
    max_single_skill: int  # Max pips in any one skill above attribute
    force_points: int = 0
    character_points: int = 0


TIER_BUDGETS: dict[NPCTier, TierBudget] = {
    NPCTier.EXTRA: TierBudget(
        attr_pips_min=30, attr_pips_max=36,  # ~10D-12D in attrs
        skill_pips_min=6, skill_pips_max=12,   # ~2-4D skills
        max_single_skill=6,                     # Max +2D in one skill
        character_points=0,
    ),
    NPCTier.AVERAGE: TierBudget(
        attr_pips_min=33, attr_pips_max=39,  # ~11D-13D
        skill_pips_min=12, skill_pips_max=21,  # ~4-7D skills
        max_single_skill=6,
        character_points=2,
    ),
    NPCTier.NOVICE: TierBudget(
        attr_pips_min=42, attr_pips_max=54,  # ~14D-18D (PC range)
        skill_pips_min=15, skill_pips_max=30,  # ~5-10D skills
        max_single_skill=9,                     # +3D
        force_points=1,
        character_points=5,
    ),
    NPCTier.VETERAN: TierBudget(
        attr_pips_min=48, attr_pips_max=57,  # ~16D-19D
        skill_pips_min=30, skill_pips_max=72,  # ~10-24D skills
        max_single_skill=15,                    # +5D
        force_points=1,
        character_points=10,
    ),
    NPCTier.SUPERIOR: TierBudget(
        attr_pips_min=54, attr_pips_max=63,  # ~18D-21D
        skill_pips_min=60, skill_pips_max=120, # ~20-40D skills
        max_single_skill=21,                    # +7D
        force_points=2,
        character_points=15,
    ),
}


def _pips_to_pool(pips: int) -> DicePool:
    return DicePool(pips // 3, pips % 3)


def generate_npc(
    tier: NPCTier | str,
    archetype: str,
    species: str = "Human",
    name: str = "",
) -> dict:
    """
    Generate a balanced NPC stat block.

    Args:
        tier: Experience tier (extra/average/novice/veteran/superior)
        archetype: Character concept key (stormtrooper, smuggler, etc.)
        species: Species name (currently uses Human ranges)
        name: NPC name (optional)

    Returns:
        Dict with attributes, skills, points, etc. suitable for
        storing in the NPC table or converting to a Character object.
    """
    if isinstance(tier, str):
        tier = NPCTier(tier.lower())

    arch = ARCHETYPES.get(archetype.lower())
    if not arch:
        raise ValueError(
            f"Unknown archetype '{archetype}'. "
            f"Available: {', '.join(sorted(ARCHETYPES.keys()))}"
        )

    budget = TIER_BUDGETS[tier]

    # -- Distribute attribute pips --
    total_attr_pips = random.randint(budget.attr_pips_min, budget.attr_pips_max)
    attrs = _distribute_attr_pips(total_attr_pips, arch)

    # -- Distribute skill pips --
    total_skill_pips = random.randint(budget.skill_pips_min, budget.skill_pips_max)
    skills = _distribute_skill_pips(
        total_skill_pips, arch, budget.max_single_skill
    )

    result = {
        "name": name or f"Unnamed {arch.name}",
        "species": species,
        "template": arch.name,
        "tier": tier.value,
        "move": arch.move,
        "force_sensitive": arch.force_sensitive,
        "force_points": budget.force_points,
        "character_points": budget.character_points,
        "dark_side_points": 0,
        "attributes": {k: str(_pips_to_pool(v)) for k, v in attrs.items()},
        "skills": {k: str(_pips_to_pool(v)) for k, v in skills.items() if v > 0},
        "total_dice": (total_attr_pips + total_skill_pips) // 3,
    }

    # Force skills for Force-sensitive NPCs
    if arch.force_sensitive and tier.value in ("veteran", "superior"):
        force_dice = {"control": "0D", "sense": "0D", "alter": "0D"}
        if tier == NPCTier.VETERAN:
            force_dice = {"control": "2D", "sense": "1D+1", "alter": "1D"}
        elif tier == NPCTier.SUPERIOR:
            force_dice = {"control": "4D", "sense": "3D", "alter": "2D+1"}
        result["force_skills"] = force_dice

    return result


def _distribute_attr_pips(
    total_pips: int,
    arch: NPCArchetype,
) -> dict[str, int]:
    """
    Distribute attribute pips weighted by archetype priorities.

    Primary attributes get ~60% more pips than tertiary ones.
    Human min is 6 pips (2D), max is 12 pips (4D).
    """
    # Weight: primary=3, secondary=2, tertiary=1
    weights = {}
    for attr in ATTRIBUTE_NAMES:
        if attr in arch.primary_attrs:
            weights[attr] = 3
        elif attr in arch.secondary_attrs:
            weights[attr] = 2
        else:
            weights[attr] = 1

    total_weight = sum(weights.values())
    attrs = {}

    # Assign base proportional share
    remaining = total_pips
    for attr in ATTRIBUTE_NAMES:
        base = int(total_pips * weights[attr] / total_weight)
        base = max(6, min(12, base))  # Human 2D-4D range
        attrs[attr] = base
        remaining -= base

    # Distribute leftover pips to primary attrs
    for attr in arch.primary_attrs:
        if remaining <= 0:
            break
        add = min(remaining, 12 - attrs[attr])
        attrs[attr] += add
        remaining -= add

    # If still remaining, add to secondary
    for attr in (arch.secondary_attrs or ATTRIBUTE_NAMES):
        if remaining <= 0:
            break
        add = min(remaining, 12 - attrs[attr])
        attrs[attr] += add
        remaining -= add

    return attrs


def _distribute_skill_pips(
    total_pips: int,
    arch: NPCArchetype,
    max_per_skill: int,
) -> dict[str, int]:
    """
    Distribute skill pips weighted by archetype skill priorities.

    Primary skills get more dice; secondary get some; random
    tertiary skills may get a few pips for flavor.
    """
    skills: dict[str, int] = {}
    remaining = total_pips

    # Primary skills get ~60% of budget
    primary_budget = int(total_pips * 0.6)
    if arch.primary_skills:
        per_primary = primary_budget // len(arch.primary_skills)
        for skill in arch.primary_skills:
            pips = min(per_primary + random.randint(-1, 1), max_per_skill)
            pips = max(1, pips)
            skills[skill] = pips
            remaining -= pips

    # Secondary skills get ~30%
    secondary_budget = int(total_pips * 0.3)
    if arch.secondary_skills:
        per_secondary = secondary_budget // len(arch.secondary_skills)
        for skill in arch.secondary_skills:
            if remaining <= 0:
                break
            pips = min(per_secondary + random.randint(-1, 1), max_per_skill)
            pips = max(1, min(pips, remaining))
            skills[skill] = pips
            remaining -= pips

    # Sprinkle remaining across random skills for depth
    if remaining > 0:
        all_skills = list(skills.keys())
        while remaining > 0 and all_skills:
            skill = random.choice(all_skills)
            add = min(random.randint(1, 2), remaining, max_per_skill - skills.get(skill, 0))
            if add > 0:
                skills[skill] = skills.get(skill, 0) + add
                remaining -= add
            else:
                all_skills.remove(skill)

    return skills


def list_archetypes() -> list[str]:
    """Return sorted list of available archetype keys."""
    return sorted(ARCHETYPES.keys())


def get_archetype_info(key: str) -> Optional[NPCArchetype]:
    """Get archetype details, or None if not found."""
    return ARCHETYPES.get(key.lower())


def format_npc_sheet(npc: dict) -> list[str]:
    """Format a generated NPC as a readable stat block."""
    lines = []
    lines.append(f"  Name: {npc['name']}")
    lines.append(f"  Type: {npc.get('template', '?')}  "
                 f"Tier: {npc.get('tier', '?').title()}  "
                 f"Species: {npc.get('species', '?')}")
    lines.append(f"  Total Dice: ~{npc.get('total_dice', '?')}D")
    lines.append("")

    # Attributes and skills
    for attr in ATTRIBUTE_NAMES:
        attr_val = npc["attributes"].get(attr, "2D")
        lines.append(f"  {attr.upper():15s} {attr_val}")
        # Show skills under this attr
        # We'd need the skill registry to know which skills go where,
        # so just list all skills (caller can format with registry)
    lines.append("")

    # All skills
    if npc.get("skills"):
        lines.append("  Skills:")
        for skill, val in sorted(npc["skills"].items()):
            lines.append(f"    {skill:25s} +{val}")

    # Force skills
    if npc.get("force_skills"):
        lines.append("")
        lines.append("  Force Skills:")
        for skill, val in npc["force_skills"].items():
            lines.append(f"    {skill:25s} {val}")

    # Points
    lines.append("")
    fp = npc.get("force_points", 0)
    cp = npc.get("character_points", 0)
    dsp = npc.get("dark_side_points", 0)
    lines.append(f"  Move: {npc.get('move', 10)}  "
                 f"Force Pts: {fp}  Char Pts: {cp}  "
                 f"Dark Side: {dsp}")
    if npc.get("force_sensitive"):
        lines.append("  Force Sensitive: Yes")

    return lines
