# -*- coding: utf-8 -*-
"""
engine/scars.py — Permanent Scar System for SW_MUSH.

When a character reaches Incapacitated or Mortally Wounded in combat
and survives, they receive a permanent scar entry.  Scars are stored
in the character's attributes JSON and displayed on +sheet.

Scars feed into the PC Narrative Memory pipeline — the nightly Haiku
summarization includes scar descriptions so NPCs can reference them
("I see you've taken some hits.  That chest wound looks recent.").

Design source: competitive_analysis_feature_designs_v1.md §A.7
"""

import json
import logging
import random
import time

log = logging.getLogger(__name__)


# ── Body location tables ──────────────────────────────────────────────────────

_BODY_LOCATIONS = [
    "chest", "left arm", "right arm", "left leg", "right leg",
    "abdomen", "left shoulder", "right shoulder", "back", "left side",
    "right side", "left hand", "right hand", "face", "neck",
]

_RANGED_DESCRIPTIONS = {
    "blaster":    ["Blaster burn across the {loc}", "Blaster wound to the {loc}",
                   "Cauterized blaster scar on the {loc}"],
    "bowcaster":  ["Deep bowcaster bolt wound in the {loc}",
                   "Ragged bowcaster scar across the {loc}"],
    "firearms":   ["Slug wound in the {loc}", "Bullet scar on the {loc}"],
    "grenade":    ["Shrapnel scarring across the {loc}",
                   "Fragmentation wounds on the {loc}"],
    "missile":    ["Blast scarring across the {loc}"],
    "default":    ["Scarred wound on the {loc}", "Old wound across the {loc}"],
}

_MELEE_DESCRIPTIONS = {
    "melee":       ["Deep slash across the {loc}", "Blade scar on the {loc}",
                    "Jagged cut across the {loc}"],
    "lightsaber":  ["Clean lightsaber burn across the {loc}",
                    "Seared lightsaber wound on the {loc}"],
    "brawling":    ["Badly healed fracture in the {loc}",
                    "Blunt trauma scarring on the {loc}"],
    "default":     ["Scarred wound on the {loc}", "Deep scar across the {loc}"],
}


def _generate_description(weapon_type: str, skill: str) -> str:
    """Generate a scar description from weapon type and skill."""
    loc = random.choice(_BODY_LOCATIONS)

    # Determine if ranged or melee
    skill_lower = skill.lower() if skill else ""
    if skill_lower in ("melee combat", "melee parry", "brawling parry",
                        "lightsaber"):
        table = _MELEE_DESCRIPTIONS
        wt = weapon_type.lower() if weapon_type else "default"
        if "lightsaber" in wt or "lightsaber" in skill_lower:
            wt = "lightsaber"
        elif "brawl" in skill_lower:
            wt = "brawling"
        else:
            wt = "melee"
    else:
        table = _RANGED_DESCRIPTIONS
        wt = weapon_type.lower() if weapon_type else "default"
        # Normalize weapon type key
        for key in table:
            if key in wt:
                wt = key
                break
        else:
            wt = "default"

    templates = table.get(wt, table["default"])
    template = random.choice(templates)
    return template.format(loc=loc)


def _parse_attrs(char: dict) -> dict:
    """Parse attributes JSON from character dict."""
    raw = char.get("attributes", "{}") or "{}"
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

def add_scar(char: dict, wound_level: str, weapon_name: str,
             weapon_type: str, skill: str, attacker_name: str,
             location_name: str) -> dict:
    """Add a scar to the character's attributes JSON.

    Args:
        char: Character dict (mutated in place).
        wound_level: "incapacitated" or "mortally_wounded".
        weapon_name: Display name of the weapon (e.g. "Heavy Blaster Pistol").
        weapon_type: Weapon type key (e.g. "blaster", "melee").
        skill: Skill used in the attack (e.g. "blaster", "lightsaber").
        attacker_name: Name of the attacker.
        location_name: Room/area name where it happened.

    Returns:
        The scar dict that was created.
    """
    attrs = _parse_attrs(char)
    if "scars" not in attrs:
        attrs["scars"] = []

    description = _generate_description(weapon_type, skill)

    scar = {
        "date": time.strftime("%Y-%m-%d"),
        "wound_level": wound_level,
        "weapon": weapon_name,
        "attacker": attacker_name,
        "location": location_name,
        "description": description,
    }

    attrs["scars"].append(scar)

    # Cap at 20 scars — oldest get removed
    if len(attrs["scars"]) > 20:
        attrs["scars"] = attrs["scars"][-20:]

    char["attributes"] = json.dumps(attrs)
    return scar


def get_scars(char: dict) -> list[dict]:
    """Return the list of scars from a character's attributes."""
    attrs = _parse_attrs(char)
    return attrs.get("scars", [])


def format_scars_display(char: dict) -> list[str]:
    """Format the scars section for +sheet display.

    Returns a list of ANSI-colored lines.  Returns empty list if no scars.
    """
    scars = get_scars(char)
    if not scars:
        return []

    B = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[1;36m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    RESET = "\033[0m"

    lines = [
        f"{CYAN}{'─' * 78}{RESET}",
        f"  {YELLOW}SCARS{RESET}",
        f"{CYAN}{'─' * 78}{RESET}",
    ]

    for scar in scars:
        wl = scar.get("wound_level", "incapacitated")
        wl_display = wl.replace("_", " ").title()
        if "mortally" in wl.lower():
            wl_color = RED
        else:
            wl_color = YELLOW

        lines.append(
            f"  {B}●{RESET} {scar.get('description', 'Old wound')}"
            f" ({wl_color}{wl_display}{RESET})"
        )
        attacker = scar.get("attacker", "unknown")
        location = scar.get("location", "unknown")
        date = scar.get("date", "")
        lines.append(
            f"    {DIM}From {attacker} on {location} — {date}{RESET}"
        )

    return lines


def format_scars_for_narrative(char: dict) -> str:
    """Format scars as plain text for narrative memory injection.

    This goes into the nightly Haiku summarization prompt so NPCs
    can reference visible scars.
    """
    scars = get_scars(char)
    if not scars:
        return ""

    parts = []
    for scar in scars[-5:]:  # Most recent 5 only
        parts.append(scar.get("description", "old wound"))

    return "Visible scars: " + "; ".join(parts)
