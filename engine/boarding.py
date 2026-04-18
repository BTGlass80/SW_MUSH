# -*- coding: utf-8 -*-
"""
engine/boarding.py — Ship-to-Ship Boarding Link System

Creates temporary walkable exits between two ships in space,
enabling ground combat aboard a boarded vessel. Per WEG R&E,
boarding requires the target to be tractor-held (or consenting)
and at Close range.

Lifecycle:
  1. Initiator calls `boardship <contact#>` from pilot/copilot station
  2. System validates: same zone, Close range, tractor-held or speed 0
  3. Temporary exits created between bridge rooms (bidirectional)
  4. Players can walk between ships using the exits
  5. Either ship can sever the link (`boardship release`)
  6. Link auto-severs on: hyperspace jump, tractor release, ship destruction

Boarding link state stored in ship systems JSON:
  boarding_linked_to: int   — ship_id of the linked ship (0 = none)
  boarding_exit_ids: list   — [exit_id_a_to_b, exit_id_b_to_a]

Cleanup:
  - On server boot: sweep for stale boarding exits (startup_cleanup)
  - On hyperspace: sever link (HyperspaceCommand cleanup block)
  - On tractor release: sever link
  - On ship destruction: sever link
"""

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Direction names for the temporary exits
BOARDING_EXIT_DIR_TO = "boarding_link"
BOARDING_EXIT_DIR_FROM = "boarding_link_back"
BOARDING_EXIT_NAME_TO = "Boarding Link"
BOARDING_EXIT_NAME_FROM = "Boarding Link (Return)"


async def create_boarding_link(
    initiator_ship: dict,
    target_ship: dict,
    db,
    session_mgr=None,
) -> tuple[bool, str]:
    """
    Create a boarding link between two ships.

    Requirements:
      - Both ships have bridge rooms
      - Target is tractor-held by initiator, OR target speed == 0
      - Ships are at Close range on the SpaceGrid

    Returns (success, message).
    """
    from engine.starships import get_space_grid, SpaceRange

    init_id = initiator_ship["id"]
    targ_id = target_ship["id"]

    # ── Validate bridge rooms ──
    init_bridge = initiator_ship.get("bridge_room_id")
    targ_bridge = target_ship.get("bridge_room_id")
    if not init_bridge or not targ_bridge:
        return False, "One or both ships have no accessible interior."

    # ── Check not already linked ──
    init_sys = _get_systems(initiator_ship)
    targ_sys = _get_systems(target_ship)
    if init_sys.get("boarding_linked_to"):
        return False, (
            "Your ship already has an active boarding link. "
            "Use \033[1;37mboardship release\033[0m to sever it first."
        )
    if targ_sys.get("boarding_linked_to"):
        return False, "The target ship already has an active boarding link."

    # ── Check tractor hold or stationary target ──
    targ_held_by = targ_sys.get("tractor_held_by", 0)
    init_holding = init_sys.get("tractor_holding", 0)

    tractor_valid = (targ_held_by == init_id and init_holding == targ_id)
    # Also allow if target is speed 0 (stationary/disabled)
    target_speed = target_ship.get("speed", 0)
    target_stationary = (target_speed == 0)
    # Check if target is docked (docked ships can be boarded via the normal board command)
    if target_ship.get("docked_at"):
        return False, (
            "That ship is docked at a landing bay. "
            "Use \033[1;37mboard\033[0m at the docking bay instead."
        )
    if initiator_ship.get("docked_at"):
        return False, "You cannot initiate a boarding link while docked."

    if not tractor_valid and not target_stationary:
        return False, (
            "Target must be held in your tractor beam or stationary (speed 0). "
            "Lock a tractor beam on the target first, or wait for them to stop."
        )

    # ── Check range — must be Close ──
    grid = get_space_grid()
    rng = grid.get_range(init_id, targ_id)
    if rng != SpaceRange.CLOSE:
        range_name = rng.name.replace("_", " ").title()
        return False, (
            f"Target is at {range_name} range. "
            f"Must be at Close range to establish a boarding link. "
            f"Use \033[1;37mclose\033[0m maneuver to close distance."
        )

    # ── Create temporary bidirectional exits ──
    try:
        exit_a = await db.create_exit(
            init_bridge, targ_bridge,
            BOARDING_EXIT_DIR_TO,
            f"Boarding Link → {target_ship.get('name', 'Target Ship')}",
        )
        exit_b = await db.create_exit(
            targ_bridge, init_bridge,
            BOARDING_EXIT_DIR_FROM,
            f"Boarding Link → {initiator_ship.get('name', 'Your Ship')}",
        )
    except Exception:
        log.warning("Failed to create boarding link exits", exc_info=True)
        return False, "Failed to create boarding link (database error)."

    # ── Store link state in both ships' systems ──
    init_sys["boarding_linked_to"] = targ_id
    init_sys["boarding_exit_ids"] = [exit_a, exit_b]
    init_sys["boarding_target_name"] = target_ship.get("name", "Unknown")
    targ_sys["boarding_linked_to"] = init_id
    targ_sys["boarding_exit_ids"] = [exit_b, exit_a]
    targ_sys["boarding_target_name"] = initiator_ship.get("name", "Unknown")

    await db.update_ship(init_id, systems=json.dumps(init_sys))
    await db.update_ship(targ_id, systems=json.dumps(targ_sys))

    log.info(
        "[boarding] Link established: ship %d ↔ ship %d (exits %d, %d)",
        init_id, targ_id, exit_a, exit_b,
    )

    # ── pose_event: notify rooms on both bridges ──
    if session_mgr:
        _emit_boarding_sys(
            session_mgr, initiator_ship.get("bridge_room_id"),
            f"Boarding link established with {target_ship.get('name', 'target')}!",
        )
        _emit_boarding_sys(
            session_mgr, target_ship.get("bridge_room_id"),
            f"Boarding link established — {initiator_ship.get('name', 'unknown')} "
            f"has locked on!",
        )

    return True, (
        f"\033[1;32mBoarding link established with "
        f"{target_ship.get('name', 'target')}!\033[0m\n"
        f"  Type '\033[1;37m{BOARDING_EXIT_DIR_TO}\033[0m' to board, "
        f"or '\033[1;37mboardship release\033[0m' to sever the link."
    )


async def sever_boarding_link(
    ship: dict,
    db,
    session_mgr=None,
    reason: str = "manual",
) -> tuple[bool, str]:
    """
    Sever an active boarding link from either side.

    Deletes the temporary exits and clears state on both ships.
    Broadcasts notifications to both bridge rooms.

    reason: "manual", "hyperspace", "tractor_release", "destruction"
    """
    sys = _get_systems(ship)
    linked_to = sys.get("boarding_linked_to", 0)
    if not linked_to:
        return False, "Your ship has no active boarding link."

    exit_ids = sys.get("boarding_exit_ids", [])

    # ── Delete temporary exits ──
    for eid in exit_ids:
        try:
            await db.delete_exit(eid)
        except Exception:
            log.warning("[boarding] Failed to delete exit %d", eid, exc_info=True)

    # ── Clear initiator state ──
    sys["boarding_linked_to"] = 0
    sys["boarding_exit_ids"] = []
    sys.pop("boarding_target_name", None)
    await db.update_ship(ship["id"], systems=json.dumps(sys))

    # ── Clear partner state ──
    partner_ship = await db.get_ship(linked_to)
    if partner_ship:
        partner_ship = dict(partner_ship)
        p_sys = _get_systems(partner_ship)
        p_exit_ids = p_sys.get("boarding_exit_ids", [])
        # Clean up any exits from the partner side too (may differ from ours)
        for eid in p_exit_ids:
            if eid not in exit_ids:
                try:
                    await db.delete_exit(eid)
                except Exception:
                    log.warning("[boarding] Failed to delete partner exit %d",
                                eid, exc_info=True)
        p_sys["boarding_linked_to"] = 0
        p_sys["boarding_exit_ids"] = []
        p_sys.pop("boarding_target_name", None)
        await db.update_ship(linked_to, systems=json.dumps(p_sys))

    # ── Evacuate players from the other ship back to their own bridge ──
    # (Players aboard the other ship when link severs get moved back)
    await _evacuate_boarders(ship, partner_ship, db, session_mgr)

    # ── Clean up any boarding party NPCs on either ship ──
    try:
        from engine.encounter_boarding import cleanup_boarding_party
        await cleanup_boarding_party(ship["id"], db)
        if linked_to:
            await cleanup_boarding_party(linked_to, db)
    except Exception:
        log.warning("[boarding] boarding party cleanup failed", exc_info=True)

    reason_msgs = {
        "manual":          "The boarding link has been severed.",
        "hyperspace":      "The boarding link snaps as the ship jumps to hyperspace!",
        "tractor_release": "The boarding link breaks as the tractor beam disengages!",
        "destruction":     "The boarding link is destroyed!",
    }
    msg = reason_msgs.get(reason, "The boarding link has been severed.")

    log.info(
        "[boarding] Link severed: ship %d ↔ ship %d (reason: %s)",
        ship["id"], linked_to, reason,
    )

    # Broadcast to partner bridge
    if session_mgr and partner_ship and partner_ship.get("bridge_room_id"):
        try:
            await session_mgr.broadcast_to_room(
                partner_ship["bridge_room_id"],
                f"  \033[1;31m[BOARDING]\033[0m {msg}",
            )
        except Exception:
            log.warning("[boarding] Failed to broadcast to partner", exc_info=True)
        # pose_event for partner room
        _emit_boarding_sys(session_mgr, partner_ship.get("bridge_room_id"), msg)

    # pose_event for our room
    if session_mgr:
        _emit_boarding_sys(session_mgr, ship.get("bridge_room_id"), msg)

    return True, f"\033[1;31m[BOARDING]\033[0m {msg}"


async def _evacuate_boarders(
    ship_a: dict,
    ship_b: Optional[dict],
    db,
    session_mgr=None,
) -> None:
    """
    When a boarding link severs, move any players who are in the
    other ship's rooms back to their own ship's bridge.

    This prevents players from being stranded in a ship they can't
    exit after the link is severed.
    """
    if not ship_b:
        return

    a_bridge = ship_a.get("bridge_room_id")
    b_bridge = ship_b.get("bridge_room_id")
    if not a_bridge or not b_bridge:
        return

    # Get crew of each ship to determine "home" ship
    a_crew_ids = _get_all_crew_ids(ship_a)
    b_crew_ids = _get_all_crew_ids(ship_b)

    # Find players in ship_b's bridge who are crew of ship_a → move to a_bridge
    try:
        chars_in_b = await db.get_characters_in_room(b_bridge)
        for ch in chars_in_b:
            if ch["id"] in a_crew_ids:
                await db.save_character(ch["id"], room_id=a_bridge)
                if session_mgr:
                    try:
                        await session_mgr.send_to_character(
                            ch["id"],
                            "  \033[1;33m[BOARDING]\033[0m "
                            "You are pulled back to your ship as the link severs!"
                        )
                    except Exception:
                        log.debug("[boarding] send_to_character failed for %d",
                                  ch["id"], exc_info=True)
    except Exception:
        log.warning("[boarding] Failed to evacuate boarders from ship_b", exc_info=True)

    # And vice versa — players in ship_a's bridge who are crew of ship_b
    try:
        chars_in_a = await db.get_characters_in_room(a_bridge)
        for ch in chars_in_a:
            if ch["id"] in b_crew_ids:
                await db.save_character(ch["id"], room_id=b_bridge)
                if session_mgr:
                    try:
                        await session_mgr.send_to_character(
                            ch["id"],
                            "  \033[1;33m[BOARDING]\033[0m "
                            "You are pulled back to your ship as the link severs!"
                        )
                    except Exception:
                        log.debug("[boarding] send_to_character failed for %d",
                                  ch["id"], exc_info=True)
    except Exception:
        log.warning("[boarding] Failed to evacuate boarders from ship_a", exc_info=True)


async def startup_cleanup(db) -> int:
    """
    On server boot, clean up any stale boarding links.

    Deletes boarding_link / boarding_link_back exits and clears
    ship systems state. Returns number of links cleaned.
    """
    cleaned = 0
    try:
        # Find all exits with boarding direction names
        rows = await db._db.execute_fetchall(
            "SELECT id, from_room_id, to_room_id, direction FROM exits "
            "WHERE direction IN (?, ?)",
            (BOARDING_EXIT_DIR_TO, BOARDING_EXIT_DIR_FROM),
        )
        for row in rows:
            await db.delete_exit(row["id"])
            cleaned += 1

        # Clear boarding state from all ships
        ships = await db._db.execute_fetchall(
            "SELECT id, systems FROM ships WHERE systems LIKE '%boarding_linked_to%'"
        )
        for ship_row in ships:
            try:
                sys = json.loads(ship_row["systems"] or "{}")
                if sys.get("boarding_linked_to"):
                    sys["boarding_linked_to"] = 0
                    sys["boarding_exit_ids"] = []
                    await db.update_ship(ship_row["id"], systems=json.dumps(sys))
            except Exception:
                log.warning("[boarding] cleanup: failed for ship %d",
                            ship_row["id"], exc_info=True)

        if cleaned > 0:
            log.info("[boarding] Startup cleanup: removed %d stale boarding exits", cleaned)
    except Exception:
        log.warning("[boarding] Startup cleanup failed", exc_info=True)
    return cleaned


def get_boarding_link_info(ship: dict) -> Optional[dict]:
    """Get boarding link info for a ship, or None if not linked."""
    sys = _get_systems(ship)
    linked_to = sys.get("boarding_linked_to", 0)
    if not linked_to:
        return None
    return {
        "linked_to": linked_to,
        "exit_ids": sys.get("boarding_exit_ids", []),
    }


def _get_systems(ship: dict) -> dict:
    """Parse ship systems JSON."""
    sys = ship.get("systems", "{}")
    if isinstance(sys, str):
        try:
            return json.loads(sys) if sys else {}
        except Exception:
            return {}
    return sys or {}


def _get_all_crew_ids(ship: dict) -> set:
    """Get all crew character IDs from a ship."""
    crew = ship.get("crew", "{}")
    if isinstance(crew, str):
        try:
            crew = json.loads(crew) if crew else {}
        except Exception:
            return set()
    if not crew:
        return set()
    ids = set()
    for key, val in crew.items():
        if key == "gunner_stations" and isinstance(val, dict):
            ids.update(v for v in val.values() if isinstance(v, int))
        elif isinstance(val, int) and val > 0:
            ids.add(val)
    return ids


def _emit_boarding_sys(session_mgr, room_id: Optional[int], text: str) -> None:
    """Fire-and-forget pose_event(sys-event) to a room for boarding narration.

    Wraps the coroutine in a task so callers don't need to await and the
    event loop handles scheduling. Safe to call with room_id=None.
    """
    if not session_mgr or not room_id:
        return
    import asyncio
    for s in session_mgr.sessions_in_room(room_id):
        try:
            asyncio.ensure_future(
                s.send_json("pose_event", {
                    "event_type": "sys-event",
                    "who": "",
                    "text": text,
                })
            )
        except Exception:
            log.debug("[boarding] _emit_boarding_sys failed for session", exc_info=True)
