# -*- coding: utf-8 -*-
"""
engine/zone_tones.py — Narrative Tone Per Zone for SW_MUSH.

Loads zone-specific narrative tone strings from data/zones.yaml and
provides a lookup function used by:
  - NPC brain (npc_brain.py) — injected as ATMOSPHERE in system prompt
  - Director AI (director.py) — injected into faction turn prompts

Tones are matched to database zones by the `name_match` field in
zones.yaml, which is prefix-matched against the zone name (case-insensitive).

Design source: competitive_analysis_feature_designs_v1.md §D
"""

import logging
import os

log = logging.getLogger(__name__)

# Module-level cache — loaded once on first call
_tone_data: list[dict] | None = None
_zone_cache: dict[int, str] = {}  # zone_id → tone string


def _load_tones() -> list[dict]:
    """Load zone tone definitions from data/zones.yaml."""
    global _tone_data
    if _tone_data is not None:
        return _tone_data

    try:
        import yaml
    except ImportError:
        log.warning("[zone_tones] PyYAML not available — zone tones disabled.")
        _tone_data = []
        return _tone_data

    yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "zones.yaml",
    )

    if not os.path.exists(yaml_path):
        log.info("[zone_tones] data/zones.yaml not found — no zone tones.")
        _tone_data = []
        return _tone_data

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        zones = raw.get("zones", {})
        entries = []
        for key, cfg in zones.items():
            name_match = (cfg.get("name_match") or key).lower().strip()
            tone = (cfg.get("narrative_tone") or "").strip()
            if tone:
                entries.append({
                    "key": key,
                    "name_match": name_match,
                    "tone": tone,
                })
        _tone_data = entries
        log.info("[zone_tones] Loaded %d zone tones from zones.yaml", len(entries))
    except Exception as e:
        log.warning("[zone_tones] Failed to load zones.yaml: %s", e)
        _tone_data = []

    return _tone_data


def get_zone_tone_by_name(zone_name: str) -> str:
    """Look up narrative tone by zone name (case-insensitive prefix match).

    Args:
        zone_name: The zone name from the database.

    Returns:
        Narrative tone string, or empty string if no match.
    """
    if not zone_name:
        return ""
    tones = _load_tones()
    name_lower = zone_name.lower().strip()
    for entry in tones:
        if name_lower.startswith(entry["name_match"]) or entry["name_match"] in name_lower:
            return entry["tone"]
    return ""


async def get_zone_tone(db, room_id: int) -> str:
    """Look up narrative tone for a room's zone via database.

    Checks the zone_id cache first, then falls back to DB lookup.

    Args:
        db: Database instance.
        room_id: Room ID to look up.

    Returns:
        Narrative tone string, or empty string if no match.
    """
    # Check cache
    room = await db.get_room(room_id)
    if not room:
        return ""

    zone_id = room.get("zone_id")
    if not zone_id:
        return ""

    if zone_id in _zone_cache:
        return _zone_cache[zone_id]

    # Look up zone name from DB
    zone = await db.get_zone(zone_id)
    if not zone:
        _zone_cache[zone_id] = ""
        return ""

    zone_name = zone.get("name", "")
    tone = get_zone_tone_by_name(zone_name)
    _zone_cache[zone_id] = tone
    return tone


def get_all_tones() -> dict[str, str]:
    """Return all zone tones as {key: tone} for Director AI bulk injection."""
    tones = _load_tones()
    return {entry["key"]: entry["tone"] for entry in tones}


def clear_cache() -> None:
    """Clear the zone_id → tone cache (for testing or after zone edits)."""
    global _zone_cache
    _zone_cache = {}
