# -*- coding: utf-8 -*-
"""
NPC Loader — Reads NPC definitions from YAML data files.

Loads NPC stat blocks and AI configurations from data/npcs_gg7.yaml
(or any file following the same schema) and converts them into the
tuple format consumed by build_mos_eisley.py.

Usage in build_mos_eisley.py:
    from engine.npc_loader import load_npcs_from_yaml

    room_name_map = {ROOMS[i][0]: i for i in range(len(ROOMS))}
    npcs = load_npcs_from_yaml("data/npcs_gg7.yaml", room_name_map)

    for name, room_idx, species, desc, sheet, ai_cfg in npcs:
        rid = room_ids[room_idx]
        await db.create_npc(
            name=name, room_id=rid, species=species, description=desc,
            char_sheet_json=json.dumps(sheet), ai_config_json=json.dumps(ai_cfg),
        )
"""
import logging
import os
from typing import Optional

import yaml

log = logging.getLogger(__name__)


def load_npcs_from_yaml(
    path: str,
    room_name_map: dict[str, int],
    *,
    fallback_room_idx: int = 8,
) -> list[tuple[str, int, str, str, dict, dict]]:
    """
    Load NPC definitions from a YAML file.

    Args:
        path: Path to the YAML file (e.g. "data/npcs_gg7.yaml").
        room_name_map: Dict mapping room name strings to ROOMS list indices.
                       Example: {"Chalmun's Cantina - Main Room": 13}
        fallback_room_idx: Room index to use if an NPC's room name doesn't
                           match any key in room_name_map. Defaults to 8
                           (Market Row — central, safe fallback).

    Returns:
        List of (name, room_idx, species, description, char_sheet, ai_config)
        tuples, ready for db.create_npc().
    """
    if not os.path.exists(path):
        log.warning("NPC data file not found: %s", path)
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "npcs" not in data:
        log.warning("NPC data file has no 'npcs' key: %s", path)
        return []

    results = []
    skipped = 0

    for entry in data["npcs"]:
        try:
            npc_tuple = _convert_entry(entry, room_name_map, fallback_room_idx)
            if npc_tuple:
                results.append(npc_tuple)
        except Exception as exc:
            name = entry.get("name", "<unknown>")
            log.error("Failed to load NPC '%s': %s", name, exc)
            skipped += 1

    if skipped:
        log.warning("Skipped %d NPC(s) due to errors", skipped)

    log.info("Loaded %d NPCs from %s", len(results), path)
    return results


def _convert_entry(
    entry: dict,
    room_name_map: dict[str, int],
    fallback_room_idx: int,
) -> Optional[tuple[str, int, str, str, dict, dict]]:
    """
    Convert a single YAML NPC entry into a build_mos_eisley tuple.

    Returns:
        (name, room_idx, species, description, char_sheet_dict, ai_config_dict)
        or None if the entry is invalid.
    """
    name = entry.get("name", "").strip()
    if not name:
        log.warning("NPC entry with no name, skipping")
        return None

    species = entry.get("species", "Human")
    description = entry.get("description", "")
    room_name = entry.get("room", "")

    # Resolve room index
    room_idx = room_name_map.get(room_name)
    if room_idx is None:
        # Try partial match (case-insensitive prefix)
        lower_room = room_name.lower()
        for rn, ri in room_name_map.items():
            if rn.lower().startswith(lower_room) or lower_room.startswith(rn.lower()):
                room_idx = ri
                break
    if room_idx is None:
        log.warning(
            "NPC '%s': room '%s' not found, using fallback room %d",
            name, room_name, fallback_room_idx,
        )
        room_idx = fallback_room_idx

    # Build char_sheet dict (matches generate_npc() output format)
    cs = entry.get("char_sheet", {})
    char_sheet = _build_char_sheet(cs, species)

    # Build ai_config dict (matches NPCConfig / _ai() format)
    ai_raw = entry.get("ai_config", {})
    ai_config = _build_ai_config(ai_raw, name)

    return (name, room_idx, species, description, char_sheet, ai_config)


def _build_char_sheet(cs: dict, species: str) -> dict:
    """
    Build a char_sheet_json-compatible dict from YAML data.

    Output matches the format used by Character.from_npc_sheet() and
    the _sheet() helper in build_mos_eisley.py.
    """
    attrs = cs.get("attributes", {})
    sheet = {
        "attributes": {
            "dexterity": attrs.get("dexterity", "2D"),
            "knowledge": attrs.get("knowledge", "2D"),
            "mechanical": attrs.get("mechanical", "2D"),
            "perception": attrs.get("perception", "2D"),
            "strength": attrs.get("strength", "2D"),
            "technical": attrs.get("technical", "2D"),
        },
        "skills": cs.get("skills", {}),
        "weapon": cs.get("weapon", ""),
        "species": species,
        "wound_level": cs.get("wound_level", 0),
        "move": cs.get("move", 10),
        "force_points": cs.get("force_points", 0),
        "character_points": cs.get("character_points", 0),
        "dark_side_points": cs.get("dark_side_points", 0),
    }

    # Optional force fields
    if cs.get("force_sensitive"):
        sheet["force_sensitive"] = True
    if cs.get("force_skills"):
        sheet["force_skills"] = cs["force_skills"]

    return sheet


def _build_ai_config(ai: dict, name: str) -> dict:
    """
    Build an ai_config_json-compatible dict from YAML data.

    Output matches the format used by NPCConfig.to_dict() and
    the _ai() helper in build_mos_eisley.py.
    """
    # Normalize personality (YAML block scalars may have trailing newlines)
    personality = ai.get("personality", "")
    if isinstance(personality, str):
        personality = " ".join(personality.split())

    config = {
        "personality": personality,
        "knowledge": ai.get("knowledge", []),
        "faction": ai.get("faction", "Neutral"),
        "dialogue_style": ai.get("dialogue_style", ""),
        "fallback_lines": ai.get("fallback_lines", []),
        "hostile": ai.get("hostile", False),
        "combat_behavior": ai.get("combat_behavior", "defensive"),
        "model_tier": ai.get("model_tier", 1),
        "temperature": ai.get("temperature", 0.7),
        "max_tokens": ai.get("max_tokens", 120),
    }

    # If no fallback lines, generate generic ones
    if not config["fallback_lines"]:
        config["fallback_lines"] = [
            f"{name} says nothing.",
            f"{name} glances at you briefly.",
        ]

    return config
