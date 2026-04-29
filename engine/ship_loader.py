# -*- coding: utf-8 -*-
"""
Ship Loader — Reads pre-spawned ship definitions from era YAML.

Loads the list of docked ships at world-build time. Each entry resolves to:
  - a fresh bridge room
  - a ship DB row
  - bidirectional board/disembark exits between bay and bridge

Schema (per data/worlds/<era>/ships.yaml):
    schema_version: 1
    ships:
      - template_key: yt_1300
        name: "Rusty Mynock"
        bay_room: "Docking Bay 94 - Pit Floor"
        bridge_desc: "..."

Usage in build_mos_eisley.py:
    from engine.ship_loader import load_era_ships

    era_dir = "data/worlds/gcw"
    room_name_map = {r.name: r.id for r in bundle.rooms.values()}
    ships = load_era_ships(era_dir, room_name_map)

    for entry in ships:
        bay_idx = entry["bay_room_idx"]
        ...

Returns a list of dicts (not tuples) — keeps the schema extensible if
future eras want fields like initial_hull_damage, registration_id, etc.
"""
import logging
import os
from typing import Optional

import yaml

log = logging.getLogger(__name__)


def load_era_ships(
    era_dir: str,
    room_name_map: dict[str, int],
) -> list[dict]:
    """
    Load the ship roster for an era.

    Reads <era_dir>/era.yaml::content_refs.ships (a single filename, not a
    list — ships don't currently use a replacement protocol the way NPCs do
    with `replaces:`).

    Returns:
        List of dicts with keys:
            template_key (str)
            name (str)
            bay_room (str)         — verbatim from YAML
            bay_room_idx (int)     — resolved yaml_id from room_name_map
            bridge_desc (str)

    Returns [] if the era.yaml has no ships ref or the file is missing.
    Each entry whose `bay_room` doesn't resolve to a room is skipped with
    a warning — better to lose one ship than crash the build.
    """
    era_yaml_path = os.path.join(era_dir, "era.yaml")
    if not os.path.exists(era_yaml_path):
        log.warning("era.yaml not found at %s", era_yaml_path)
        return []

    with open(era_yaml_path, "r", encoding="utf-8") as f:
        era = yaml.safe_load(f) or {}

    refs = era.get("content_refs") or {}
    ships_file = refs.get("ships")
    if not ships_file:
        log.info("No ships file in era.yaml (era_dir=%s)", era_dir)
        return []

    ships_path = os.path.normpath(os.path.join(era_dir, ships_file))
    if not os.path.exists(ships_path):
        log.warning("ships YAML not found at %s", ships_path)
        return []

    with open(ships_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw_entries = data.get("ships") or []
    results: list[dict] = []
    skipped = 0

    for entry in raw_entries:
        try:
            converted = _convert_entry(entry, room_name_map)
            if converted:
                results.append(converted)
        except Exception as exc:
            name = entry.get("name", "<unknown>")
            log.error("Failed to load ship '%s': %s", name, exc)
            skipped += 1

    if skipped:
        log.warning("Skipped %d ship(s) due to errors", skipped)
    log.info("Loaded %d ships from %s", len(results), ships_path)
    return results


def _convert_entry(
    entry: dict,
    room_name_map: dict[str, int],
) -> Optional[dict]:
    """Convert a single YAML ship entry into the build-script-friendly dict."""
    name = (entry.get("name") or "").strip()
    template_key = (entry.get("template_key") or "").strip()
    bay_room = (entry.get("bay_room") or "").strip()
    bridge_desc = entry.get("bridge_desc") or ""

    if not name or not template_key or not bay_room:
        log.warning("Ship entry missing required field(s): %r", entry)
        return None

    # Normalize whitespace in bridge_desc (YAML block scalars often have newlines)
    if isinstance(bridge_desc, str):
        bridge_desc = " ".join(bridge_desc.split())

    bay_idx = room_name_map.get(bay_room)
    if bay_idx is None:
        # Try case-insensitive fallback
        for rn, ri in room_name_map.items():
            if rn.lower() == bay_room.lower():
                bay_idx = ri
                break
    if bay_idx is None:
        log.warning(
            "Ship '%s': bay_room %r not found in room_name_map; skipping",
            name, bay_room,
        )
        return None

    return {
        "template_key": template_key,
        "name": name,
        "bay_room": bay_room,
        "bay_room_idx": bay_idx,
        "bridge_desc": bridge_desc,
    }
