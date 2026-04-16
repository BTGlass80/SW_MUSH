# -*- coding: utf-8 -*-
"""
engine/room_states.py — Dynamic Room State Descriptions for SW_MUSH.

Rooms can have transient state flags stored in properties JSON under
"room_states". Each state maps to an atmospheric description overlay
that's appended when a player looks at the room.

States are set by:
  - Director AI events (imperial_crackdown, rebel_propaganda, etc.)
  - Territory claims (faction_presence)
  - Environmental conditions (set via @roomstate)
  - World events (trade_boom, sandstorm, etc.)

Design source: competitive_analysis_feature_mining_v1.md §C
"""

from __future__ import annotations
import json
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Predefined State Descriptions ─────────────────────────────────────────────

STATE_DESCRIPTIONS: dict[str, str] = {
    # Director events
    "imperial_crackdown": (
        "Stormtrooper patrols are more frequent than usual. Citizens "
        "hurry past with their eyes down. Checkpoints have been set up "
        "at major intersections."
    ),
    "rebel_propaganda": (
        "Crude anti-Imperial slogans have been scrawled on the walls. "
        "Rebel Alliance symbols are scratched into doorframes. Someone "
        "is watching from the shadows."
    ),
    "trade_boom": (
        "The market is busier than usual. Merchants are hawking their "
        "wares with extra enthusiasm and prices seem inflated."
    ),
    "bounty_surge": (
        "Bounty hunters congregate in small groups, comparing datapads "
        "and checking weapons. Someone important has a price on their head."
    ),
    "sandstorm": (
        "Sand whips through the air in stinging gusts. Visibility is "
        "poor and every surface is coated in grit. Most sensible beings "
        "have taken shelter."
    ),
    "pirate_alert": (
        "Warning beacons flash amber. Reports of pirate activity in "
        "the surrounding space lanes have put the port on edge."
    ),
    "merchant_arrival": (
        "A traveling merchant has set up a temporary stall, their wares "
        "displayed under a weathered tarp. Locals crowd around for a look."
    ),

    # Territory / faction presence
    "imperial_control": (
        "Imperial banners hang from the walls. Stormtrooper boots echo "
        "on the duracrete. Order is maintained with visible force."
    ),
    "rebel_presence": (
        "Rebel Alliance markings are discreetly visible — a scratched "
        "starbird here, a coded signal there. The resistance has a "
        "foothold here."
    ),
    "hutt_territory": (
        "Hutt Cartel enforcers lounge in doorways, watching everyone "
        "who passes. This area operates by the Hutts' rules."
    ),
    "guild_territory": (
        "Guild insignia are posted at the entrance. This area is under "
        "professional management — follow the rules or face consequences."
    ),

    # Environmental / atmospheric
    "power_outage": (
        "The lights flicker and dim. Emergency lighting casts everything "
        "in a harsh red glow. Something is wrong with the power grid."
    ),
    "celebration": (
        "Festive decorations hang from every surface. Music drifts "
        "through the air and the mood is unusually cheerful."
    ),
    "lockdown": (
        "Blast doors have been sealed. Armed guards control all access "
        "points. No one enters or leaves without authorization."
    ),
    "abandoned": (
        "This area has been evacuated. Personal effects are scattered "
        "about — whoever was here left in a hurry. Dust is beginning "
        "to settle over everything."
    ),
}


# ── Room State Access ─────────────────────────────────────────────────────────

def get_room_states(room: dict) -> dict:
    """Extract room_states dict from room properties.

    Returns {state_key: {"set_at": float, "set_by": str, "custom_text": str}}
    """
    try:
        props = room.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)
        return props.get("room_states", {})
    except Exception:
        return {}


def get_state_descriptions(room: dict) -> list[str]:
    """Return list of atmospheric description lines for active states.

    Used by LookCommand to append state overlays after the base description.
    """
    states = get_room_states(room)
    if not states:
        return []

    lines = []
    for key, state_data in states.items():
        # Custom text overrides predefined
        if isinstance(state_data, dict):
            custom = state_data.get("custom_text", "")
        elif isinstance(state_data, str):
            custom = state_data
        else:
            custom = ""

        text = custom or STATE_DESCRIPTIONS.get(key, "")
        if text:
            lines.append(text)

    return lines


async def set_room_state(
    db, room_id: int, state_key: str,
    custom_text: str = "", set_by: str = "system",
) -> dict:
    """Add or update a state on a room. Returns {ok, msg}."""
    room = await db.get_room(room_id)
    if not room:
        return {"ok": False, "msg": "Room not found."}

    try:
        props = room.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)

        states = props.setdefault("room_states", {})
        states[state_key] = {
            "set_at": time.time(),
            "set_by": set_by,
            "custom_text": custom_text,
        }

        await db.execute(
            "UPDATE rooms SET properties = ? WHERE id = ?",
            (json.dumps(props), room_id),
        )
        await db.commit()

        display = STATE_DESCRIPTIONS.get(state_key, state_key)
        return {"ok": True, "msg": f"State '{state_key}' set on room #{room_id}."}
    except Exception as e:
        return {"ok": False, "msg": f"Failed: {e}"}


async def clear_room_state(db, room_id: int, state_key: str) -> dict:
    """Remove a specific state from a room."""
    room = await db.get_room(room_id)
    if not room:
        return {"ok": False, "msg": "Room not found."}

    try:
        props = room.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)

        states = props.get("room_states", {})
        if state_key not in states:
            return {"ok": False, "msg": f"State '{state_key}' not set on this room."}

        del states[state_key]
        if not states:
            props.pop("room_states", None)

        await db.execute(
            "UPDATE rooms SET properties = ? WHERE id = ?",
            (json.dumps(props), room_id),
        )
        await db.commit()
        return {"ok": True, "msg": f"State '{state_key}' cleared from room #{room_id}."}
    except Exception as e:
        return {"ok": False, "msg": f"Failed: {e}"}


async def clear_all_states(db, room_id: int) -> dict:
    """Remove all states from a room."""
    room = await db.get_room(room_id)
    if not room:
        return {"ok": False, "msg": "Room not found."}

    try:
        props = room.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)

        if "room_states" not in props:
            return {"ok": False, "msg": "No states set on this room."}

        count = len(props["room_states"])
        del props["room_states"]

        await db.execute(
            "UPDATE rooms SET properties = ? WHERE id = ?",
            (json.dumps(props), room_id),
        )
        await db.commit()
        return {"ok": True, "msg": f"Cleared {count} state(s) from room #{room_id}."}
    except Exception as e:
        return {"ok": False, "msg": f"Failed: {e}"}


async def set_zone_state(
    db, zone_id: int, state_key: str,
    custom_text: str = "", set_by: str = "director",
) -> int:
    """Apply a state to all rooms in a zone. Returns count of rooms updated."""
    try:
        rows = await db.fetchall(
            "SELECT id FROM rooms WHERE zone_id = ?", (zone_id,)
        )
        count = 0
        for row in rows:
            result = await set_room_state(
                db, row["id"], state_key,
                custom_text=custom_text, set_by=set_by,
            )
            if result["ok"]:
                count += 1
        return count
    except Exception as e:
        log.warning("[room_states] set_zone_state failed: %s", e)
        return 0


async def clear_zone_state(db, zone_id: int, state_key: str) -> int:
    """Remove a state from all rooms in a zone. Returns count cleared."""
    try:
        rows = await db.fetchall(
            "SELECT id FROM rooms WHERE zone_id = ?", (zone_id,)
        )
        count = 0
        for row in rows:
            result = await clear_room_state(db, row["id"], state_key)
            if result["ok"]:
                count += 1
        return count
    except Exception as e:
        log.warning("[room_states] clear_zone_state failed: %s", e)
        return 0
