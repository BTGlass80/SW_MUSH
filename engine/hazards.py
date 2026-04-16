# -*- coding: utf-8 -*-
"""
engine/hazards.py — Environmental Hazard System for SW_MUSH.

Rooms tagged with hazards apply periodic debuffs to characters present.
Uses the buff/debuff handler (engine/buffs.py) for effect application.

Design source: competitive_analysis_feature_designs_v1.md §E

Hazards are stored in room properties JSON under "environment_hazard":
  {"type": "extreme_heat", "severity": 2, "difficulty": 12}

The hazard tick runs every 300 seconds (5 minutes). For each occupied
room with a hazard, characters are checked: skill vs. difficulty.
Failure applies a debuff. Mitigation items in inventory skip the check.

Hazard types map to predefined configurations; severity scales the
difficulty and debuff strength.
"""

from __future__ import annotations
import json
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Hazard Definitions ────────────────────────────────────────────────────────

HAZARD_TYPES: dict[str, dict] = {
    "extreme_heat": {
        "display_name": "Extreme Heat",
        "skill": "stamina",
        "base_difficulty": 10,
        "buff_type": "dehydration",
        "mitigation_items": ["water_canteen", "cooling_unit"],
        "warning_text": (
            "The twin suns beat down mercilessly. Your mouth is parched, "
            "your skin burning. Without water, you won't last much longer."
        ),
        "fail_text": (
            "The heat overwhelms you. Your vision swims and your legs buckle."
        ),
        "pass_text": (
            "You push through the heat, drawing on your reserves. "
            "You're still standing — for now."
        ),
        "environments": ["desert_wilderness", "desert_fringe", "barren"],
    },
    "toxic_atmosphere": {
        "display_name": "Toxic Atmosphere",
        "skill": "stamina",
        "base_difficulty": 12,
        "buff_type": "toxic_exposure",
        "mitigation_items": ["breath_mask"],
        "warning_text": (
            "The air burns your lungs with every breath. Chemical "
            "particulates sting your eyes. You need a breath mask."
        ),
        "fail_text": (
            "You double over coughing. The toxins are taking their toll."
        ),
        "pass_text": (
            "You hold your breath and push through. The air is foul "
            "but you manage."
        ),
        "environments": ["deep_underground", "underground"],
    },
    "urban_danger": {
        "display_name": "Urban Danger",
        "skill": "perception",
        "base_difficulty": 10,
        "buff_type": None,  # Special: credit theft, not a buff
        "mitigation_items": [],
        "warning_text": (
            "You feel eyes on you from the shadows. This neighborhood "
            "has a reputation for a reason."
        ),
        "fail_text": (
            "A quick hand dips into your pocket before you can react."
        ),
        "pass_text": (
            "You spot the pickpocket before they get close and give "
            "them a look that sends them scurrying."
        ),
        "environments": ["urban_slum", "subterranean"],
    },
    "radiation": {
        "display_name": "Radiation",
        "skill": "stamina",
        "base_difficulty": 15,
        "buff_type": "toxic_exposure",  # Reuses toxic debuff
        "mitigation_items": ["radiation_suit"],
        "warning_text": (
            "Your datapad's radiation counter clicks faster. The "
            "background radiation here is dangerously high."
        ),
        "fail_text": (
            "Nausea washes over you. The radiation is affecting you."
        ),
        "pass_text": (
            "You minimize your exposure. Still dangerous, but you're "
            "holding up."
        ),
        "environments": [],  # Only manually tagged rooms
    },
}

# Per-character hazard check timestamps: {(char_id, room_id): last_check_time}
_hazard_timers: dict[tuple[int, int], float] = {}

# Check interval in seconds (5 minutes)
HAZARD_CHECK_INTERVAL = 300


# ── Hazard Resolution ─────────────────────────────────────────────────────────

def get_room_hazard(room: dict) -> Optional[dict]:
    """Extract hazard config from room properties. Returns None if no hazard."""
    try:
        props = room.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)
        hazard = props.get("environment_hazard")
        if not hazard or not isinstance(hazard, dict):
            return None
        if hazard.get("type") not in HAZARD_TYPES:
            return None
        return hazard
    except Exception:
        return None


def _should_check(char_id: int, room_id: int) -> bool:
    """Return True if enough time has passed since last hazard check."""
    key = (char_id, room_id)
    last = _hazard_timers.get(key, 0)
    return (time.time() - last) >= HAZARD_CHECK_INTERVAL


def _mark_checked(char_id: int, room_id: int) -> None:
    """Record that a hazard check was performed."""
    _hazard_timers[(char_id, room_id)] = time.time()


def _has_mitigation(char: dict, mitigation_items: list[str]) -> bool:
    """Check if character has any mitigation item in inventory or equipment."""
    if not mitigation_items:
        return False
    try:
        inv = char.get("inventory", "[]")
        if isinstance(inv, str):
            inv = json.loads(inv)
        equipped = char.get("equipped_weapon", "")
        # Check inventory item keys
        for item in inv:
            key = item.get("key", "") if isinstance(item, dict) else str(item)
            if key.lower() in mitigation_items:
                return True
        # Check equipped
        if equipped and equipped.lower() in mitigation_items:
            return True
        # Check worn armor
        armor = char.get("worn_armor", "")
        if armor and armor.lower() in mitigation_items:
            return True
    except Exception as _e:
        log.debug("silent except in engine/hazards.py:169: %s", _e, exc_info=True)
    return False


async def check_hazard_for_character(
    char: dict, room: dict, db, session=None
) -> Optional[dict]:
    """Run a hazard check for a single character in a hazardous room.

    Returns {checked, passed, msg} or None if no check needed.
    """
    room_id = room.get("id", 0)
    char_id = char.get("id", 0)

    hazard_cfg = get_room_hazard(room)
    if not hazard_cfg:
        return None

    if not _should_check(char_id, room_id):
        return None

    _mark_checked(char_id, room_id)

    hazard_type = hazard_cfg["type"]
    template = HAZARD_TYPES[hazard_type]
    severity = hazard_cfg.get("severity", 1)
    difficulty = hazard_cfg.get("difficulty", template["base_difficulty"])
    # Scale difficulty with severity
    difficulty += (severity - 1) * 3

    # Check mitigation
    if _has_mitigation(char, template["mitigation_items"]):
        return {"checked": True, "passed": True, "msg": "", "mitigated": True}

    # Perform skill check
    from engine.skill_checks import perform_skill_check
    result = perform_skill_check(char, template["skill"], difficulty)

    DIM = "\033[2m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    GREEN = "\033[1;32m"
    RST = "\033[0m"

    if result.success:
        # Passed — atmospheric message only
        msg = f"\n  {DIM}[{template['display_name']}]{RST} {GREEN}{template['pass_text']}{RST}"
        if session:
            await session.send_line(msg)
        return {"checked": True, "passed": True, "msg": template["pass_text"]}
    else:
        # Failed — apply debuff or credit theft
        warning = f"\n  {YELLOW}[{template['display_name']}]{RST} {template['warning_text']}"
        fail = f"  {RED}{template['fail_text']}{RST}"

        if session:
            await session.send_line(warning)
            await session.send_line(fail)

        # Apply effect
        if template["buff_type"]:
            from engine.buffs import add_buff
            buff_result = add_buff(char, template["buff_type"])
            if buff_result.get("ok") and session:
                buff_obj = buff_result.get("buff")
                if buff_obj:
                    name = buff_obj.display_name if hasattr(buff_obj, 'display_name') else template["buff_type"]
                    await session.send_line(
                        f"  {RED}[EFFECT] {name} applied.{RST}"
                    )
            # Persist attributes
            if db:
                try:
                    await db.save_character(
                        char_id, attributes=char.get("attributes", "{}")
                    )
                except Exception as _e:
                    log.debug("silent except in engine/hazards.py:246: %s", _e, exc_info=True)
        elif hazard_type == "urban_danger":
            # Pickpocket — steal credits
            stolen = min(
                int(char.get("credits", 0) * 0.05),  # 5% of credits
                max(50, severity * 100),  # 50-300 cr cap
            )
            if stolen > 0 and char.get("credits", 0) >= stolen:
                char["credits"] = char.get("credits", 0) - stolen
                if db:
                    try:
                        await db.save_character(char_id, credits=char["credits"])
                    except Exception as _e:
                        log.debug("silent except in engine/hazards.py:259: %s", _e, exc_info=True)
                if session:
                    await session.send_line(
                        f"  {RED}You lost {stolen:,} credits to a pickpocket!{RST}"
                    )

        return {"checked": True, "passed": False, "msg": template["fail_text"]}


# ── Tick Handler ──────────────────────────────────────────────────────────────

async def hazard_tick(db, session_mgr) -> None:
    """Check environmental hazards for all online characters.

    Called by tick_handlers_economy every 300 ticks (5 minutes).
    """
    try:
        for s in session_mgr.all:
            if not s.is_in_game or not s.character:
                continue
            char = s.character
            room_id = char.get("room_id")
            if not room_id:
                continue

            # Get room — check for hazard
            room = await db.get_room(room_id)
            if not room:
                continue

            hazard = get_room_hazard(room)
            if not hazard:
                continue

            # Run the check
            try:
                await check_hazard_for_character(char, room, db, session=s)
            except Exception as e:
                log.warning("[hazards] Check failed for char %d: %s",
                            char.get("id", 0), e)
    except Exception as e:
        log.warning("[hazards] hazard_tick failed: %s", e)


# ── Admin Helpers ─────────────────────────────────────────────────────────────

async def set_room_hazard(
    db, room_id: int, hazard_type: str, severity: int = 1
) -> dict:
    """Set or update a hazard on a room. Returns {ok, msg}."""
    if hazard_type not in HAZARD_TYPES:
        valid = ", ".join(HAZARD_TYPES.keys())
        return {"ok": False, "msg": f"Unknown hazard type. Valid: {valid}"}
    if severity < 1 or severity > 5:
        return {"ok": False, "msg": "Severity must be 1-5."}

    room = await db.get_room(room_id)
    if not room:
        return {"ok": False, "msg": "Room not found."}

    try:
        props = room.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)

        template = HAZARD_TYPES[hazard_type]
        props["environment_hazard"] = {
            "type": hazard_type,
            "severity": severity,
            "difficulty": template["base_difficulty"] + (severity - 1) * 3,
        }

        await db.execute(
            "UPDATE rooms SET properties = ? WHERE id = ?",
            (json.dumps(props), room_id),
        )
        await db.commit()
        return {
            "ok": True,
            "msg": f"Hazard '{template['display_name']}' (severity {severity}) "
                   f"set on room #{room_id}.",
        }
    except Exception as e:
        return {"ok": False, "msg": f"Failed: {e}"}


async def clear_room_hazard(db, room_id: int) -> dict:
    """Remove hazard from a room. Returns {ok, msg}."""
    room = await db.get_room(room_id)
    if not room:
        return {"ok": False, "msg": "Room not found."}
    try:
        props = room.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)
        if "environment_hazard" not in props:
            return {"ok": False, "msg": "No hazard set on this room."}
        del props["environment_hazard"]
        await db.execute(
            "UPDATE rooms SET properties = ? WHERE id = ?",
            (json.dumps(props), room_id),
        )
        await db.commit()
        return {"ok": True, "msg": f"Hazard cleared from room #{room_id}."}
    except Exception as e:
        return {"ok": False, "msg": f"Failed: {e}"}
