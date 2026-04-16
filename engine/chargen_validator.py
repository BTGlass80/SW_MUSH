# -*- coding: utf-8 -*-
"""
Server-side character creation validator.

Validates a complete character build submitted from the web chargen page.
Reuses Species.validate_attributes() logic but operates on raw dicts
rather than stateful CreationEngine objects.

This is the authoritative validator — the client validates for UX,
but the server is the final word.
"""
import logging
import re
from typing import Optional

from engine.dice import DicePool
from engine.character import ATTRIBUTE_NAMES, SkillRegistry
from engine.species import SpeciesRegistry

log = logging.getLogger(__name__)

# WEG R&E rule: at creation, no skill may have more than 2D added
# above its parent attribute.
MAX_SKILL_BONUS_PIPS = 6  # 2D = 6 pips

# Character name constraints
MIN_NAME_LEN = 2
MAX_NAME_LEN = 30
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 '\-\.]+$")

# Forbidden name patterns (case-insensitive)
FORBIDDEN_NAMES = {
    "admin", "administrator", "system", "server", "god", "gm",
    "gamemaster", "staff", "moderator", "mod", "npc", "test",
    "darth vader", "luke skywalker", "han solo", "leia organa",
    "emperor palpatine", "yoda", "chewbacca", "obi-wan kenobi",
    "boba fett", "jabba", "darth maul", "mace windu",
}


def validate_character_name(name: str) -> list[str]:
    """Validate a character name. Returns list of errors."""
    errors = []
    if not name or len(name.strip()) < MIN_NAME_LEN:
        errors.append(f"Name must be at least {MIN_NAME_LEN} characters.")
    elif len(name) > MAX_NAME_LEN:
        errors.append(f"Name must be at most {MAX_NAME_LEN} characters.")
    elif not NAME_PATTERN.match(name):
        errors.append(
            "Name must start with a letter and contain only letters, "
            "numbers, spaces, hyphens, apostrophes, and periods."
        )

    if name and name.strip().lower() in FORBIDDEN_NAMES:
        errors.append("That name is reserved and cannot be used.")

    return errors


def validate_chargen_submission(
    data: dict,
    species_reg: SpeciesRegistry,
    skill_reg: SkillRegistry,
) -> list[str]:
    """
    Validate a complete character creation submission.
    Returns list of error strings (empty = valid).

    Expected data format:
    {
        "species": "Human",
        "attributes": {"dexterity": "3D+1", ...},
        "skills": {"blaster": "1D+1", ...},
        "force_sensitive": false,
        "name": "Kaelin Voss",
        "background": "..."
    }
    """
    errors = []

    # 1. Species exists
    species_name = data.get("species", "")
    species = species_reg.get(species_name) if species_name else None
    if not species:
        errors.append(f"Unknown species: '{species_name}'")
        return errors  # Can't validate further without species

    # 2. Parse and validate attributes
    raw_attrs = data.get("attributes", {})
    if not isinstance(raw_attrs, dict):
        errors.append("Attributes must be a dict of attribute_name: dice_string")
        return errors

    parsed_attrs = {}
    for attr in ATTRIBUTE_NAMES:
        val = raw_attrs.get(attr)
        if val is None:
            errors.append(f"Missing attribute: {attr}")
            continue
        try:
            parsed_attrs[attr] = DicePool.parse(str(val))
        except (ValueError, TypeError):
            errors.append(f"Invalid dice value for {attr}: '{val}'")

    if errors:
        return errors

    # 3. Attribute pips sum to species total
    total_attr_pips = sum(p.total_pips() for p in parsed_attrs.values())
    expected_attr_pips = species.attribute_dice.total_pips()
    if total_attr_pips != expected_attr_pips:
        diff = expected_attr_pips - total_attr_pips
        if diff > 0:
            errors.append(f"Attribute points not fully spent ({diff} pips remaining)")
        else:
            errors.append(f"Attribute points overspent by {-diff} pips")

    # 4. Each attribute within species min/max
    for attr in ATTRIBUTE_NAMES:
        pool = parsed_attrs.get(attr)
        if pool is None:
            continue
        attr_range = species.attributes.get(attr)
        if attr_range is None:
            continue
        if pool.total_pips() < attr_range.min_pool.total_pips():
            errors.append(
                f"{attr.capitalize()}: {pool} is below minimum "
                f"{attr_range.min_pool} for {species.name}"
            )
        if pool.total_pips() > attr_range.max_pool.total_pips():
            errors.append(
                f"{attr.capitalize()}: {pool} exceeds maximum "
                f"{attr_range.max_pool} for {species.name}"
            )

    # 5. Validate skills
    raw_skills = data.get("skills", {})
    if not isinstance(raw_skills, dict):
        errors.append("Skills must be a dict of skill_name: dice_string")
        return errors

    total_skill_pips = 0
    for skill_name, skill_val in raw_skills.items():
        # Check skill exists in registry
        skill_def = skill_reg.get(skill_name)
        if not skill_def:
            errors.append(f"Unknown skill: '{skill_name}'")
            continue

        try:
            bonus = DicePool.parse(str(skill_val))
        except (ValueError, TypeError):
            errors.append(f"Invalid dice value for skill {skill_name}: '{skill_val}'")
            continue

        # Check 2D creation cap
        if bonus.total_pips() > MAX_SKILL_BONUS_PIPS:
            errors.append(
                f"Skill '{skill_name}': bonus {bonus} exceeds creation cap of 2D"
            )

        # Skip zero-pip skills (not actually allocated)
        if bonus.total_pips() > 0:
            total_skill_pips += bonus.total_pips()

    # Check total skill allocation
    max_skill_pips = species.skill_dice.total_pips()
    if total_skill_pips > max_skill_pips:
        over = total_skill_pips - max_skill_pips
        errors.append(f"Skill points overspent by {over} pips")

    # 6. Name validation
    char_name = data.get("name", "")
    errors.extend(validate_character_name(char_name))

    # 7. Force sensitive is boolean
    force_sensitive = data.get("force_sensitive")
    if force_sensitive is not None and not isinstance(force_sensitive, bool):
        errors.append("force_sensitive must be true or false")

    return errors


def validate_account_fields(username: str, password: str) -> list[str]:
    """Validate account creation fields. Returns list of errors."""
    errors = []
    if not username or len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    elif len(username) > 20:
        errors.append("Username must be at most 20 characters.")
    elif not re.match(r"^[A-Za-z0-9_]+$", username):
        errors.append("Username may only contain letters, numbers, and underscores.")

    if not password or len(password) < 6:
        errors.append("Password must be at least 6 characters.")

    return errors
