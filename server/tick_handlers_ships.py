"""
Ship tick handlers — ion decay, tractor reel, asteroid collision,
hyperspace arrival.

Ported from the inline blocks in game_server._game_tick_loop as part of
the review-fixes refactor (design doc §3.2). These used to each call
`db.get_ships_in_space()` independently; they now share the list via
TickContext.ships_in_space.
"""
from __future__ import annotations

import json
import logging
import random

from server.tick_scheduler import TickContext

log = logging.getLogger(__name__)


def _safe_json_loads(value, default=None):
    """Parse JSON from a string, returning `default` on malformed input."""
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError) as _e:
        log.warning("Malformed ship systems JSON: %s", _e)
        return default


async def ion_and_tractor_tick(ctx: TickContext) -> None:
    """Decay ion penalties and notify tractor-held ships.

    R&E p.108: ion wears off over ~2 rounds. 99 = full freeze and needs
    a special clear path.
    """
    for ship in ctx.ships_in_space:
        if ship.get("docked_at"):
            continue
        sys = _safe_json_loads(ship.get("systems"), default={}) or {}
        dirty = False

        # ── Ion decay ────────────────────────────────────────────────
        ion = sys.get("ion_penalty", 0)
        if ion and ion != 99:
            sys["ion_penalty"] = max(0, ion - 1)
            if sys["ion_penalty"] == 0:
                sys.pop("controls_frozen", None)
            dirty = True
        elif ion == 99:
            sys["ion_penalty"] = 0
            sys.pop("controls_frozen", None)
            dirty = True

        # ── Tractor auto-reel ────────────────────────────────────────
        held_by = sys.get("tractor_held_by", 0)
        if held_by:
            holder = await ctx.db.get_ship(held_by)
            if holder and holder.get("bridge_room_id"):
                bridge = ship.get("bridge_room_id")
                if bridge:
                    await ctx.session_mgr.broadcast_to_room(
                        bridge,
                        "  [TRACTOR] You are being reeled in. "
                        "Use 'resist' to break free."
                    )
            else:
                # Holder gone — release
                sys["tractor_held_by"] = 0
                dirty = True

        if dirty:
            await ctx.db.update_ship(ship["id"], systems=json.dumps(sys))
            # Keep the shared list in sync for later handlers this tick
            ship["systems"] = json.dumps(sys)


async def sublight_transit_tick(ctx: TickContext) -> None:
    """Advance sublight-transit ships and arrive them at their destination.

    Ported from the inline block in _game_tick_loop. Preserves the
    HUD broadcast on arrival via broadcast_space_state().
    """
    from engine.npc_space_traffic import ZONES
    from server import ansi

    for ship in ctx.ships_in_space:
        if ship.get("docked_at"):
            continue
        sys = _safe_json_loads(ship.get("systems"), default={}) or {}
        if not sys.get("sublight_transit"):
            continue

        ticks_remaining = sys.get("sublight_ticks_remaining", 0)
        if ticks_remaining > 1:
            sys["sublight_ticks_remaining"] = ticks_remaining - 1
            await ctx.db.update_ship(ship["id"], systems=json.dumps(sys))
            ship["systems"] = json.dumps(sys)
            continue

        # ── Arrival ──────────────────────────────────────────────────
        dest_id = sys.get("sublight_dest", "")
        dest_zone = ZONES.get(dest_id)
        dest_name = (dest_zone.name if dest_zone
                     else dest_id.replace("_", " ").title())
        dest_desc = dest_zone.desc if dest_zone else ""

        sys["sublight_transit"] = False
        sys["current_zone"] = dest_id
        sys.pop("sublight_dest", None)
        sys.pop("sublight_ticks_remaining", None)
        await ctx.db.update_ship(ship["id"], systems=json.dumps(sys))
        ship["systems"] = json.dumps(sys)
        ship["current_zone"] = dest_id  # keep shared dict fresh

        bridge = ship.get("bridge_room_id")
        if bridge:
            desc_line = f"\n  {dest_desc}" if dest_desc else ""
            await ctx.session_mgr.broadcast_to_room(
                bridge,
                f"  {ansi.BRIGHT_CYAN}[HELM]{ansi.RESET} "
                f"Arrived: {dest_name}.{desc_line}"
            )
            # Space HUD update on arrival — fetch fresh ship row so the
            # HUD broadcast doesn't use our stale in-memory dict.
            try:
                from parser.space_commands import broadcast_space_state
                fresh = await ctx.db.get_ship_by_bridge(bridge)
                if fresh:
                    await broadcast_space_state(fresh, ctx.db, ctx.session_mgr)
            except Exception:
                log.warning("sublight arrival HUD broadcast failed",
                            exc_info=True)


async def asteroid_collision_tick(ctx: TickContext) -> None:
    """Light hull scrape check for ships in heavy asteroid fields.

    Runs every 30 ticks (~30s). Easy piloting check (difficulty 5);
    failure = +1 hull damage with bridge notification.

    Ported from the inline block in _game_tick_loop (review fix v2).
    Uses ctx.ships_in_space — no extra DB fetch.
    """
    from server import ansi
    from engine.npc_space_traffic import ZONES

    for ship in ctx.ships_in_space:
        if ship.get("docked_at"):
            continue
        sys = _safe_json_loads(ship.get("systems"), default={}) or {}
        # Skip transiting ships — they're not stationary in the field
        if sys.get("in_hyperspace") or sys.get("sublight_transit"):
            continue
        zone = ZONES.get(sys.get("current_zone", ""))
        if not zone:
            continue
        density = (zone.hazards or {}).get("asteroid_density", "")
        if density != "heavy":
            continue

        # Easy piloting check: diff 5, use cached pilot dice if available
        pilot_dice = max(1, sys.get("_cached_pilot_dice", 2))
        roll = sum(random.randint(1, 6) for _ in range(pilot_dice))
        if roll >= 5:
            continue  # avoided

        # Collision — light hull scrape
        existing = ship.get("hull_damage", 0)
        await ctx.db.update_ship(ship["id"], hull_damage=existing + 1)
        ship["hull_damage"] = existing + 1  # keep shared dict fresh
        bridge = ship.get("bridge_room_id")
        if bridge:
            await ctx.session_mgr.broadcast_to_room(
                bridge,
                f"  {ansi.BRIGHT_RED}[ASTEROID]{ansi.RESET} "
                f"A chunk of rock scrapes the hull! "
                f"(+1 hull damage) Transit through this zone quickly."
            )


async def hyperspace_arrival_tick(ctx: TickContext) -> None:
    """Advance hyperspace-transiting ships and arrive them at their destination.

    Runs every tick. Decrements the countdown and — on final tick — reverts
    to realspace, re-adds the ship to the space grid, notifies bridge crew,
    broadcasts the space HUD, logs the zone visit, and runs the smuggling
    patrol check.

    Ported from the inline block in _game_tick_loop (review fix v2).
    Uses ctx.ships_in_space — no extra DB fetch.
    """
    from server import ansi
    from engine.npc_space_traffic import ZONES
    from engine.starships import get_ship_registry
    from parser.space_commands import get_space_grid

    for ship in ctx.ships_in_space:
        if ship.get("docked_at"):
            continue
        sys = _safe_json_loads(ship.get("systems"), default={}) or {}
        if not sys.get("in_hyperspace"):
            continue

        ticks = sys.get("hyperspace_ticks_remaining", 0)
        if ticks > 1:
            sys["hyperspace_ticks_remaining"] = ticks - 1
            await ctx.db.update_ship(ship["id"], systems=json.dumps(sys))
            ship["systems"] = json.dumps(sys)
            continue

        # ── Arrival ──────────────────────────────────────────────────────────
        dest_key = sys.get("hyperspace_dest", "tatooine")
        dest_name = sys.get("hyperspace_dest_name", dest_key.title())
        arr_zone = (
            dest_key + "_orbit"
            if (dest_key + "_orbit") in ZONES
            else "tatooine_orbit"
        )

        sys["in_hyperspace"] = False
        sys["current_zone"] = arr_zone
        sys["location"] = dest_key
        sys.pop("hyperspace_dest", None)
        sys.pop("hyperspace_dest_name", None)
        sys.pop("hyperspace_ticks_remaining", None)
        sys.pop("hyperspace_roll_str", None)
        await ctx.db.update_ship(ship["id"], systems=json.dumps(sys))
        ship["systems"] = json.dumps(sys)
        ship["current_zone"] = arr_zone  # keep shared dict fresh

        # Re-add to space grid
        tmpl = get_ship_registry().get(ship["template"])
        spd = tmpl.speed if tmpl else 5
        get_space_grid().add_ship(ship["id"], spd)

        bridge = ship.get("bridge_room_id")
        if not bridge:
            continue

        await ctx.session_mgr.broadcast_to_room(
            bridge,
            f"  {ansi.BRIGHT_CYAN}[HYPERSPACE]{ansi.RESET} "
            f"Reverting to realspace — arriving at {dest_name}.\n"
            f"  The star lines collapse back into points. "
            f"You are in {arr_zone.replace('_', ' ').title()}."
        )

        # Space HUD broadcast on arrival
        try:
            from parser.space_commands import broadcast_space_state
            fresh = await ctx.db.get_ship_by_bridge(bridge)
            if fresh:
                await broadcast_space_state(fresh, ctx.db, ctx.session_mgr)
        except Exception:
            log.warning("hyperspace arrival HUD broadcast failed", exc_info=True)

        # Ship's log: zone visited
        try:
            from engine.ships_log import log_event as _zlog
            for sess in (ctx.session_mgr.sessions_in_room(bridge) or []):
                if sess.character:
                    await _zlog(ctx.db, sess.character, "zones_visited", arr_zone)
        except Exception:
            log.warning("hyperspace arrival zone-log failed", exc_info=True)

        # Achievement: hyperspace_complete
        try:
            from engine.achievements import on_hyperspace_complete
            for sess in (ctx.session_mgr.sessions_in_room(bridge) or []):
                if sess.character:
                    await on_hyperspace_complete(ctx.db, sess.character["id"], session=sess)
        except Exception:
            log.warning("hyperspace arrival achievement hook failed", exc_info=True)

        # Patrol-on-arrival check for smuggling runs
        try:
            from parser.smuggling_commands import check_patrol_on_arrival
            from parser.commands import CommandContext
            for sess in (ctx.session_mgr.sessions_in_room(bridge) or []):
                if not sess.character:
                    continue
                arr_ctx = CommandContext(
                    session=sess,
                    db=ctx.db,
                    session_mgr=ctx.session_mgr,
                    args="",
                )
                await check_patrol_on_arrival(arr_ctx, dest_key)
        except Exception:
            log.warning("hyperspace arrival patrol check failed", exc_info=True)


async def space_anomaly_tick(ctx: TickContext) -> None:
    """Spawn and expire space anomalies in zones occupied by player ships.

    Runs every 300 ticks (~5 min). Uses ctx.ships_in_space to determine
    which zones are active — no extra DB fetch.

    Ported from the inline block in _game_tick_loop (review fix v2).
    """
    from engine.npc_space_traffic import ZONES, get_space_security
    from engine.space_anomalies import spawn_anomalies_for_zone, tick_anomaly_expiry

    active_zones: set[str] = set()
    for ship in ctx.ships_in_space:
        sys_raw = ship.get("systems", "{}")
        try:
            sys = json.loads(sys_raw) if isinstance(sys_raw, str) else sys_raw
        except Exception:
            log.warning("anomaly tick: bad systems JSON on ship %s", ship.get("id"), exc_info=True)
            continue
        zone = sys.get("current_zone")
        if zone:
            active_zones.add(zone)

    for zone_id in active_zones:
        tick_anomaly_expiry(zone_id)
        zone = ZONES.get(zone_id)
        if zone:
            spawn_anomalies_for_zone(zone_id, zone.type.value,
                                     security=get_space_security(zone_id))


async def texture_encounter_tick(ctx: TickContext) -> None:
    """Randomly trigger texture encounters for ships in transit.

    Runs every tick (~1s). For each player ship mid-transit (sublight or
    hyperspace), roll a small chance to spawn a mechanical, cargo, or
    contact encounter. Frequency scales with zone security (lawless = more
    encounters, secured = fewer).

    Space Overhaul v3 — texture auto-trigger (session 38).
    """
    from engine.space_encounters import get_encounter_manager
    from engine.npc_space_traffic import get_space_security

    # Base chance per tick: 0.8% (~1 event per 2 min of transit)
    BASE_CHANCE = 0.008
    SECURITY_MULT = {
        "secured": 0.3,    # Very rare in secured space
        "contested": 1.0,  # Normal
        "lawless": 1.6,    # More frequent in lawless
    }
    TEXTURE_TYPES = ["mechanical", "cargo", "contact"]
    TEXTURE_WEIGHTS = [40, 30, 30]  # mechanical most common

    for ship in ctx.ships_in_space:
        if ship.get("docked_at"):
            continue
        sys = _safe_json_loads(ship.get("systems"), default={}) or {}

        # Only trigger during active transit (sublight or hyperspace)
        in_transit = sys.get("sublight_transit") or sys.get("in_hyperspace")
        if not in_transit:
            continue

        zone_id = sys.get("current_zone", "")
        if not zone_id:
            continue

        bridge = ship.get("bridge_room_id")
        if not bridge:
            continue

        # Must have a player aboard
        sessions = list(ctx.session_mgr.sessions_in_room(bridge) or [])
        if not any(getattr(s, "character", None) for s in sessions):
            continue

        # Scale by zone security
        security = get_space_security(zone_id)
        chance = BASE_CHANCE * SECURITY_MULT.get(security, 1.0)

        if random.random() > chance:
            continue

        # Pick encounter type
        enc_type = random.choices(TEXTURE_TYPES, weights=TEXTURE_WEIGHTS, k=1)[0]

        try:
            mgr = get_encounter_manager()
            await mgr.create_encounter(
                encounter_type=enc_type,
                zone_id=zone_id,
                target_ship_id=ship["id"],
                target_bridge_room=bridge,
                db=ctx.db,
                session_mgr=ctx.session_mgr,
                context={"trigger": "transit_random"},
            )
        except Exception:
            log.warning("texture_encounter_tick: spawn failed", exc_info=True)


async def encounter_tick(ctx: TickContext) -> None:
    """Tick active space encounters and NPC combat AI.

    Runs every tick (~1s). Handles:
      1. Encounter deadline checks and warnings (Drop 1)
      2. NPC combat AI action loop (Drop 3)

    Space Overhaul v3, Drops 1+3.
    """
    from engine.space_encounters import get_encounter_manager
    mgr = get_encounter_manager()
    await mgr.tick(ctx.db, ctx.session_mgr)

    # NPC combat AI tick (Drop 3)
    from engine.npc_space_combat_ai import get_npc_combat_manager
    await get_npc_combat_manager().tick(ctx.db, ctx.session_mgr)
