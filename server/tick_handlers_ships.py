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
            # Best-effort hook — never block hyperspace arrival because the
            # achievements layer choked, but DO leave a breadcrumb so silent
            # failures are visible in production logs (S38 silent-except
            # invariant).
            log.warning("hyperspace arrival achievement hook failed",
                        exc_info=True)

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
    from engine.npc_space_traffic import ZONES
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
            spawn_anomalies_for_zone(zone_id, zone.type.value)


# ──────────────────────────────────────────────────────────────────────────
# Texture encounters — atmospheric "something is happening" events fired
# during transit. Low-stakes (mechanical glitches, cargo shifting,
# navigation drift) but they fill the long quiet stretches of hyperspace
# and sublight transit with something for the bridge crew to react to.
# Probability scales by zone security so quiet Core lanes feel safe and
# Outer Rim lanes feel eventful.
# Tested by tests/test_session38.py::TestTextureEncounterTick.
# ──────────────────────────────────────────────────────────────────────────

# Encounter type pool with relative weights. Mechanical events are the
# bread and butter; atmospheric events are flavour-only and stay rare.
_TEXTURE_TYPES = ["mechanical", "cargo", "navigation", "atmospheric"]
_TEXTURE_WEIGHTS = [10, 8, 6, 4]

# Per-tick trigger probability by zone security. Tuned so an active
# transit produces ~1 encounter per 3 minutes in lawless space and ~1
# per ~17 minutes in secured space at a 1 Hz tick rate.
_TEXTURE_PROB_BY_SECURITY = {
    "secured":  0.001,
    "neutral":  0.005,
    "lawless":  0.010,
}
_TEXTURE_BASE_PROB = 0.005

# Planet → security tier. Used to derive a zone's security from its
# planet attribute. Zones whose planet is unset / unknown fall back to
# "neutral".
_PLANET_SECURITY = {
    "corellia":     "secured",   # CEC + CorSec
    "tatooine":     "lawless",   # Outer Rim, no central authority
    "kessel":       "lawless",   # Smuggler haven, Maw approach
    "nar_shaddaa":  "lawless",   # Hutt territory, Smuggler's Moon
}


def _texture_trigger_probability(zone_id: str) -> float:
    """Resolve per-tick texture-encounter probability for ``zone_id``.

    Returns the base probability if the zone or its planet can't be
    located, so a misconfigured zone never hard-zeros the feature.
    """
    try:
        from engine.npc_space_traffic import ZONES
        zone = ZONES.get(zone_id)
        if not zone:
            return _TEXTURE_BASE_PROB
        sec = _PLANET_SECURITY.get(zone.planet, "neutral")
        return _TEXTURE_PROB_BY_SECURITY.get(sec, _TEXTURE_BASE_PROB)
    except Exception:
        return _TEXTURE_BASE_PROB


async def texture_encounter_tick(ctx: TickContext) -> None:
    """Random low-stakes texture encounters during transit.

    Fires for ships in sublight or hyperspace transit when at least one
    bridge crew member is logged in. Per-tick probability scales by zone
    security. The encounter type is weighted toward mechanical events;
    atmospheric ones stay rare so they keep their flavour weight.
    """
    for ship in ctx.ships_in_space:
        if ship.get("docked_at"):
            continue
        sys = _safe_json_loads(ship.get("systems"), default={}) or {}
        # Only fire during transit — stationary ships don't encounter
        # texture events. (Hazards and combat use their own ticks.)
        if not (sys.get("sublight_transit") or sys.get("in_hyperspace")):
            continue

        bridge = ship.get("bridge_room_id")
        if not bridge:
            continue

        sessions = ctx.session_mgr.sessions_in_room(bridge) or []
        # No-op if nobody on the bridge has a character — the encounter
        # has nobody to react to it.
        if not any(getattr(s, "character", None) for s in sessions):
            continue

        zone_id = sys.get("current_zone", "")
        prob = _texture_trigger_probability(zone_id)
        if random.random() >= prob:
            continue

        encounter_type = random.choices(
            _TEXTURE_TYPES, weights=_TEXTURE_WEIGHTS,
        )[0]

        try:
            from engine.space_encounters import get_encounter_manager
            mgr = get_encounter_manager()
            await mgr.create_encounter(
                encounter_type=encounter_type,
                ship_id=ship["id"],
                zone=zone_id,
            )
        except Exception:
            log.warning(
                "[texture] encounter creation failed for ship %s in %s",
                ship.get("id"), zone_id, exc_info=True,
            )
