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
        # Gundark Drop E (2026-06-11): the anti_theft_alarm schematic
        # existed with NO consumer — this is its loop. max_uses: 1, so
        # with the consume-on-mitigation mechanic it defeats exactly one
        # pickpocket attempt and is spent.
        "mitigation_items": ["anti_theft_alarm"],
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


# Lane E2b (Secrets of Tatooine §3): time-of-day grading for the extreme_heat
# hazard — worst under the noon suns ("day"), eased after dark ("night"). Steps
# are -1D-band (3 pips); the caller floors the result. Pure + table-driven so it
# is unit-testable independent of the skill-check randomness.
_EXTREME_HEAT_TOD_MOD = {"day": 3, "dusk": 0, "night": -4}


def _extreme_heat_time_mod(time_of_day: str) -> int:
    """Difficulty modifier for extreme_heat by clock band (day hotter, night eased).
    Unknown/None -> 0 (no-op)."""
    return _EXTREME_HEAT_TOD_MOD.get((time_of_day or "").strip().lower(), 0)


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
    """Check if character has any mitigation item in inventory or equipment.

    CRAFT.P0.5: the old code iterated the raw inventory top-level — under
    the current dict format ({"items": [...], "resources": [...]}) that
    iterated the KEY STRINGS, so survival gear never mitigated anything.
    It also read char["equipped_weapon"]/["worn_armor"], which are not row
    columns (those live in the equipment JSON) — both checks were dead.
    """
    if not mitigation_items:
        return False
    try:
        inv = char.get("inventory", "[]")
        if isinstance(inv, str):
            inv = json.loads(inv) if inv else {}
        # Tolerate both shapes: dict format carries the list under "items".
        items = inv.get("items", []) if isinstance(inv, dict) else (
            inv if isinstance(inv, list) else [])
        for item in items:
            key = item.get("key", "") if isinstance(item, dict) else str(item)
            if key.lower() in mitigation_items:
                return True
        # Equipped weapon / worn armor (canonical per-slot read)
        from engine.items import equipment_keys
        keys = equipment_keys(char.get("equipment", "{}"))
        if keys["weapon"] and keys["weapon"].lower() in mitigation_items:
            return True
        if keys["armor"] and keys["armor"].lower() in mitigation_items:
            return True
    except Exception as _e:
        log.debug("silent except in engine/hazards.py:_has_mitigation: %s",
                  _e, exc_info=True)
    return False


def _find_mitigation_item(char: dict, mitigation_items: list[str]):
    """Locate the FIRST mitigation match. Returns (source, item) where
    source is "inventory" (item = the carried dict) or "equipment"
    (item = the slot key string), or (None, None).

    Mirrors _has_mitigation's search order exactly — the two must agree
    or a player could pass the presence check and dodge the consume.
    """
    if not mitigation_items:
        return None, None
    mitigation_items = [m.lower() for m in mitigation_items]
    try:
        # Same source + shape tolerance as _has_mitigation: the char
        # row's inventory JSON ({"items": [...]} dict format, or a bare
        # legacy list). The two functions MUST agree or a player could
        # pass the presence check and dodge the consume.
        inv = char.get("inventory", "[]")
        if isinstance(inv, str):
            inv = json.loads(inv) if inv else {}
        items = inv.get("items", []) if isinstance(inv, dict) else (
            inv if isinstance(inv, list) else [])
        for item in items:
            key = item.get("key", "") if isinstance(item, dict) else str(item)
            if key.lower() in mitigation_items:
                return "inventory", item
    except Exception as _e:
        log.debug("silent except in _find_mitigation_item inv: %s",
                  _e, exc_info=True)
    try:
        from engine.items import equipment_keys
        keys = equipment_keys(char.get("equipment", "{}"))
        if keys["weapon"] and keys["weapon"].lower() in mitigation_items:
            return "equipment", keys["weapon"]
        if keys["armor"] and keys["armor"].lower() in mitigation_items:
            return "equipment", keys["armor"]
    except Exception as _e:
        log.debug("silent except in _find_mitigation_item eq: %s",
                  _e, exc_info=True)
    return None, None


async def _consume_mitigation_use(char: dict, item: dict, db,
                                  session=None) -> None:
    """Gundark Drop E (2026-06-11): mitigation gear with max_uses > 0
    spends a use each time it actually averts a hazard; at zero it is
    removed with a message. Until this drop, `uses` landed on crafted
    gear and NOTHING decremented it — radiation_suit's max_uses: 10 and
    anti_theft_alarm's max_uses: 1 were decorative.

    Durable gear (max_uses absent or 0) is untouched. Equipment-slot
    matches are ItemInstances without uses semantics — treated as
    durable (the caller passes inventory dicts only). Fail-open: a db
    hiccup must never punish the player mid-hazard.
    """
    try:
        if not isinstance(item, dict):
            return
        max_uses = int(item.get("max_uses", 0) or 0)
        if max_uses <= 0:
            return  # durable
        uses = int(item.get("uses", max_uses) or 0)
        new_uses = max(0, uses - 1)
        key = item.get("key", "")
        name = item.get("name", key)

        # DB mirror (source of truth across sessions)
        await db.remove_from_inventory(char["id"], key)
        if new_uses > 0:
            mutated = dict(item)
            mutated["uses"] = new_uses
            await db.add_to_inventory(char["id"], mutated)

        # Session-dict sync: the hazard tick passes the LIVE session
        # character dict and re-reads char["inventory"] on every check —
        # without this rewrite a spent item would keep mitigating until
        # relog (db.add/remove only touch the row, never the dict).
        try:
            inv = char.get("inventory", "[]")
            if isinstance(inv, str):
                inv = json.loads(inv) if inv else {}
            if isinstance(inv, dict):
                items = inv.get("items", [])
            elif isinstance(inv, list):
                items = inv
                inv = {"items": items}
            else:
                items = []
                inv = {"items": items}
            for i, it in enumerate(items):
                if isinstance(it, dict) and it.get("key") == key:
                    if new_uses > 0:
                        items[i] = dict(it)
                        items[i]["uses"] = new_uses
                    else:
                        items.pop(i)
                    break
            char["inventory"] = json.dumps(inv)
        except Exception as _e:
            log.debug("consume_mitigation dict-sync failed: %s",
                      _e, exc_info=True)

        if new_uses > 0:
            note = f"[{name}] {new_uses}/{max_uses} uses remain."
        else:
            note = (f"[{name}] is spent and falls apart — "
                    f"craft or buy a replacement.")
        if session:
            from engine.pose_events import make_system_event
            await session.send_json("pose_event", make_system_event(note))
    except Exception as _e:
        log.debug("silent except in _consume_mitigation_use: %s",
                  _e, exc_info=True)


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
    # The stored difficulty (set_room_hazard / _check_wilderness_hazard) is
    # ALREADY severity-scaled (base + (severity-1)*3); use it as-is. Only the
    # defensive fallback to the raw base needs the one-time scaling. The old
    # `difficulty += (severity-1)*3` re-applied it, so a severity-3 hazard hit
    # DC 22 instead of the intended 16. (QA hazards 2026-06-23.)
    if "difficulty" in hazard_cfg:
        difficulty = hazard_cfg["difficulty"]
    else:
        difficulty = template["base_difficulty"] + (severity - 1) * 3

    # Lane E2b (Secrets of Tatooine §3): the desert heat-and-thirst hazard is
    # graded by the twin-sun clock — at its worst under the noon suns, eased
    # after dark. Applies ONLY to extreme_heat; the band comes from the room's
    # time-of-day (authored override -> global day cycle, so wilderness tiles get
    # the live day/night swing). No-op-safe and floored at the Very-Easy band so
    # night relief never drives the check negative.
    if hazard_type == "extreme_heat":
        try:
            from engine.world_time import resolve_time_of_day
            _rprops = room.get("properties", "{}")
            if isinstance(_rprops, str):
                _rprops = json.loads(_rprops)
            if not isinstance(_rprops, dict):
                _rprops = {}
            _tod = resolve_time_of_day(_rprops)
            difficulty = max(5, difficulty + _extreme_heat_time_mod(_tod))
        except Exception as _e:
            log.debug("silent except in engine/hazards.py extreme_heat tod mod: %s",
                      _e, exc_info=True)

    # Check mitigation — Gundark Drop E: gear with max_uses now SPENDS a
    # use when it actually averts the hazard (inventory dicts only;
    # equipment-slot and legacy string matches are durable by shape).
    _mit_src, _mit_item = _find_mitigation_item(
        char, template["mitigation_items"])
    if _mit_src is not None:
        if _mit_src == "inventory" and isinstance(_mit_item, dict):
            await _consume_mitigation_use(char, _mit_item, db, session)
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
        # Drop B: emit as typed pose_event (sys-event banner). Telnet
        # falls back to plain text via send_json. Drops ANSI from the
        # WebSocket payload — the client themes by event_type.
        if session:
            from engine.pose_events import make_system_event
            text = f"[{template['display_name']}] {template['pass_text']}"
            await session.send_json("pose_event", make_system_event(text))
        return {"checked": True, "passed": True, "msg": template["pass_text"]}
    else:
        # Failed — apply debuff or credit theft
        # Drop B: warning + consequence both emit as sys-event banners.
        if session:
            from engine.pose_events import make_system_event
            warning_text = f"[{template['display_name']}] {template['warning_text']}"
            await session.send_json(
                "pose_event", make_system_event(warning_text)
            )
            await session.send_json(
                "pose_event", make_system_event(template["fail_text"])
            )

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
                        await db.adjust_credits(char_id, -stolen, "hazard_theft")
                    except Exception as _e:
                        log.debug("silent except in engine/hazards.py:259: %s", _e, exc_info=True)
                if session:
                    # Drop B: pickpocket narrative as desc-inline (no
                    # attribution — the pickpocket is anonymous flavor).
                    from engine.pose_events import make_ambient_event
                    await session.send_json(
                        "pose_event",
                        make_ambient_event(
                            f"You lost {stolen:,} credits to a pickpocket!"
                        ),
                    )

        return {"checked": True, "passed": False, "msg": template["fail_text"]}


# ── Tick Handler ──────────────────────────────────────────────────────────────

async def hazard_tick(db, session_mgr) -> None:
    """Check environmental hazards for all online characters.

    Called by tick_handlers_economy every 300 ticks (5 minutes).

    Two paths:
      1. Room-based: characters whose ``room_id`` points at a room
         with an ``environment_hazard`` in properties.
      2. Wilderness-based (T2.WENC, May 24 2026): characters with
         ``wilderness_region_slug`` set; the terrain at their
         coordinates may carry an ``ambient_hazard`` that maps to
         a HAZARD_TYPES entry. Terrain hazard strings that don't
         resolve to a known HAZARD_TYPE are inert (no error) so
         aspirational tags ship without immediate consequence.
    """
    try:
        for s in session_mgr.all:
            if not s.is_in_game or not s.character:
                continue
            char = s.character

            # Path 1: wilderness — checked first because wilderness
            # characters share a sentinel room_id; the room hazard
            # path would otherwise look up the sentinel room and
            # find nothing useful.
            try:
                wilderness_hit = await _check_wilderness_hazard(char, db, session=s)
            except Exception as e:
                log.warning(
                    "[hazards] Wilderness check failed for char %d: %s",
                    char.get("id", 0), e,
                )
                wilderness_hit = False
            if wilderness_hit:
                continue  # don't double-process this char on the room path

            # Path 2: room-based
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


async def _check_wilderness_hazard(char: dict, db, session=None) -> bool:
    """Run the hazard check against the character's current wilderness tile.

    Returns True iff we processed a wilderness hazard for this
    character (whether the roll passed or failed) — callers use that
    flag to skip the room-based path so wilderness characters aren't
    double-checked.

    Returns False when:
      - the character isn't in wilderness, or
      - the region can't be loaded, or
      - the terrain at the tile has no ambient hazard, or
      - the terrain's hazard string isn't a known HAZARD_TYPE
        (aspirational tag — inert until the hazard type is defined).

    Design source: wilderness_system_design_v1.md §6.2.
    """
    # Avoid importing the wilderness module at module-load time —
    # keeps hazards.py importable in test fixtures that don't stand
    # up the wilderness loader. Import on first call instead.
    try:
        from engine.wilderness_movement import (
            in_wilderness, get_wilderness_coords, get_or_load_region,
            _terrain_at, _terrain_attr,
        )
    except Exception:
        return False

    if not in_wilderness(char):
        return False
    coords = get_wilderness_coords(char)
    if coords is None:
        return False
    slug, x, y = coords

    region = await get_or_load_region(db, slug)
    if region is None:
        return False

    terrain_name = _terrain_at(region, x, y)
    terrain_cfg = (region.terrains or {}).get(terrain_name)
    if terrain_cfg is None:
        return False

    hazard_type = _terrain_attr(terrain_cfg, "ambient_hazard", "none")
    severity = int(_terrain_attr(terrain_cfg, "hazard_severity", 0))
    if not hazard_type or hazard_type == "none" or severity <= 0:
        return False
    if hazard_type not in HAZARD_TYPES:
        # Aspirational tag (e.g. Coruscant's "structural_collapse",
        # "stale_air", "lethal_environment"). Inert until the matching
        # HAZARD_TYPE ships. Logged at debug to surface during testing
        # without spamming production logs.
        log.debug(
            "[hazards] Wilderness terrain %r has aspirational ambient_hazard "
            "%r (severity %d); inert until HAZARD_TYPE ships.",
            terrain_name, hazard_type, severity,
        )
        return False

    # Synthesise a "room dict" so we can reuse check_hazard_for_character
    # unchanged. The cooldown key is (char_id, room_id), so we use a
    # stable per-region negative pseudo-id to keep wilderness cooldowns
    # separate from any real room cooldowns. Negative numbers are not
    # used by the rooms table (id INTEGER PRIMARY KEY → always > 0).
    template = HAZARD_TYPES[hazard_type]
    pseudo_room_id = _wilderness_pseudo_room_id(slug)
    synthetic_room = {
        "id": pseudo_room_id,
        "properties": json.dumps({
            "environment_hazard": {
                "type": hazard_type,
                "severity": severity,
                "difficulty": template["base_difficulty"] + (severity - 1) * 3,
            },
        }),
    }
    await check_hazard_for_character(char, synthetic_room, db, session=session)
    return True


def _wilderness_pseudo_room_id(slug: str) -> int:
    """Stable negative pseudo-id for a wilderness region's hazard cooldown.

    Cooldown keys are (char_id, room_id). We need a room_id that:
      - is stable across calls within a session (same slug → same id),
      - doesn't collide with real room ids (rooms.id is always > 0),
      - is the same for every tile inside the region (tile-by-tile
        cooldown reset would defeat the hazard pacing — the 5-minute
        cadence is per region, not per step).
    """
    # Negative to avoid colliding with rooms.id. We deliberately do
    # NOT use the region slug for cooldown granularity per-tile.
    h = abs(hash(slug)) % 1_000_000
    return -(h + 1)



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
