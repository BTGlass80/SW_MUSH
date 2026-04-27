# -*- coding: utf-8 -*-
"""
Space commands -- ship operations, crew stations, flight, and combat.

32 commands: crew stations, cooperation, combat, navigation, economy.
"""
import json
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.npc_space_traffic import get_orbit_zone_for_room, get_traffic_manager
from engine.starships import (
    get_ship_registry, format_ship_status, resolve_space_attack,
    get_space_grid, SpaceRange, RelativePosition, can_weapon_fire,
    ShipInstance, SCALE_STARFIGHTER, SCALE_CAPITAL,
    REPAIRABLE_SYSTEMS, REPAIR_DIFFICULTIES,
    get_system_state, get_repair_skill_name, get_weapon_repair_skill,
    resolve_damage_control, get_effective_stats,
)
from engine.dice import DicePool
from server import ansi

# Achievement hooks (graceful-drop)
async def _ach_space_hook(db, char_id, event, session=None):
    try:
        from engine.achievements import check_achievement
        await check_achievement(db, char_id, event, session=session)
    except Exception as _e:
        log.debug("silent except in parser/space_commands.py:27: %s", _e, exc_info=True)


log = logging.getLogger(__name__)


async def _get_ship_for_player(ctx):
    room_id = ctx.session.character["room_id"]
    return await ctx.db.get_ship_by_bridge(room_id)

def _get_crew(ship):
    crew = ship.get("crew", "{}")
    if isinstance(crew, str):
        try: crew = json.loads(crew)
        except Exception: return {}
    crew = crew or {}
    # Auto-migrate old gunners list → gunner_stations dict
    if "gunners" in crew and "gunner_stations" not in crew:
        stations = {}
        for i, gid in enumerate(crew["gunners"]):
            stations[str(i)] = gid
        crew["gunner_stations"] = stations
        del crew["gunners"]
    return crew

def _get_systems(ship):
    systems = ship.get("systems", "{}")
    if isinstance(systems, str):
        try:
            return json.loads(systems)
        except Exception:
            log.warning("parse_systems failed for ship %s", ship.get("id"), exc_info=True)
            return {}
    return systems or {}


def _get_effective_for_ship(ship: dict) -> dict | None:
    """Return get_effective_stats() result for a ship, or None on error.

    Used by combat, maneuvering, and HUD code so that mods, power
    allocation, and captain's orders actually affect gameplay.
    """
    reg = get_ship_registry()
    template = reg.get(ship.get("template", ""))
    if not template:
        return None
    systems = _get_systems(ship)
    return get_effective_stats(template, systems)


# ── Space HUD: build_space_state() + broadcast_space_state() ─────────────────
# Drop 8 — Phase 4a

async def build_space_state(ship: dict, char_id: int, db, session_mgr) -> dict:
    """
    Assemble the full space_state JSON payload for a WebSocket client.
    Called after any space command and on tick-based transit arrivals.
    """
    from engine.starships import (
        get_ship_registry, get_space_grid, DicePool,
        get_system_state, SCALE_CAPITAL,
    )
    from engine.npc_space_traffic import ZONES, get_traffic_manager
    from engine.space_anomalies import get_anomalies_for_zone
    from engine.starships import is_silent_running

    reg     = get_ship_registry()
    grid    = get_space_grid()
    systems = _get_systems(ship)
    crew    = _get_crew(ship)
    tmpl    = reg.get(ship.get("template", ""))

    # ── Location ─────────────────────────────────────────────────────────────
    zone_id   = systems.get("current_zone", "")
    zone_obj  = ZONES.get(zone_id)
    zone_name = zone_obj.name        if zone_obj else zone_id.replace("_", " ").title()
    zone_type = zone_obj.type.value  if zone_obj else "deep_space"
    zone_desc = zone_obj.desc        if zone_obj else ""
    zone_planet = zone_obj.planet    if zone_obj else None
    zone_hazards = dict(zone_obj.hazards) if zone_obj else {}

    # Zone security level (Drop 0: space security zones)
    from engine.npc_space_traffic import get_space_security
    zone_security = get_space_security(zone_id) if zone_id else "lawless"

    adjacent_zones = []
    if zone_obj:
        for adj_id in (zone_obj.adjacent or []):
            adj = ZONES.get(adj_id)
            if adj:
                adjacent_zones.append({
                    "id": adj_id,
                    "name": adj.name,
                    "type": adj.type.value,
                    "security": get_space_security(adj_id),
                })

    # ── Hull & shields ────────────────────────────────────────────────────────
    # Use effective stats so mods, power allocation, and orders are reflected
    eff = get_effective_stats(tmpl, systems) if tmpl else None
    hull_pool    = DicePool.parse(eff["hull"])    if eff else (DicePool.parse(tmpl.hull) if tmpl else DicePool(4, 0))
    shield_pool  = DicePool.parse(eff["shields"]) if eff else (DicePool.parse(tmpl.shields) if tmpl else DicePool(0, 0))
    hull_max     = hull_pool.total_pips()
    hull_damage  = systems.get("hull_damage", ship.get("hull_damage", 0))
    hull_current = max(0, hull_max - hull_damage)

    # Hull condition label
    frac = hull_damage / max(hull_max, 1)
    if   frac <= 0:     hull_condition = "Pristine"
    elif frac < 0.25:   hull_condition = "Light Damage"
    elif frac < 0.5:    hull_condition = "Moderate Damage"
    elif frac < 0.75:   hull_condition = "Heavy Damage"
    elif frac < 1.0:    hull_condition = "Critical Damage"
    else:               hull_condition = "Destroyed"

    shield_total = str(shield_pool)
    shield_arcs  = {
        "front": systems.get("shield_dice_front", shield_pool.dice),
        "rear":  systems.get("shield_dice_rear", 0),
        "left":  0,
        "right": 0,
        # Drop E (F9): pool capacity so the client can render {cur}D/{max}D
        # per arc. R&E shields are a single pool that may be allocated/shifted
        # between arcs, so each arc's effective max == the ship's total dice
        # pool. Pips are surfaced separately for ships with non-integer dice
        # (e.g., 1D+2 starfighter shields).
        "pool_dice": shield_pool.dice,
        "pool_pips": shield_pool.pips,
    }

    # ── Speed ─────────────────────────────────────────────────────────────────
    speed = grid.get_speed(ship["id"]) if not ship.get("docked_at") else 0

    # ── System states ─────────────────────────────────────────────────────────
    damaged_systems = systems.get("systems_damaged", [])
    sys_states = {}
    for sname in ("engines", "weapons", "shields", "hyperdrive", "sensors", "life_support"):
        sys_states[sname] = sname not in damaged_systems

    # ── Crew roster ───────────────────────────────────────────────────────────
    my_station = None
    crew_out   = {}

    async def _char_stub(cid):
        if not cid:
            return None
        try:
            c = await db.get_character(cid)
            if c:
                return {"id": c["id"], "name": c["name"], "is_npc": bool(c.get("is_npc"))}
        except Exception:
            log.warning("_char_stub: unhandled exception", exc_info=True)
            pass
        return {"id": cid, "name": f"Crew#{cid}", "is_npc": False}

    pilot_id    = crew.get("pilot", 0)
    copilot_id  = crew.get("copilot", 0)
    engineer_id = crew.get("engineer", 0)
    navigator_id= crew.get("navigator", 0)
    commander_id= crew.get("commander", 0)
    sensors_id  = crew.get("sensors", 0)

    crew_out["pilot"]     = await _char_stub(pilot_id)
    crew_out["copilot"]   = await _char_stub(copilot_id)
    crew_out["engineer"]  = await _char_stub(engineer_id)
    crew_out["navigator"] = await _char_stub(navigator_id)
    crew_out["commander"] = await _char_stub(commander_id)
    crew_out["sensors"]   = await _char_stub(sensors_id)

    # Determine requesting char's station
    for station, sid in [
        ("pilot", pilot_id), ("copilot", copilot_id),
        ("engineer", engineer_id), ("navigator", navigator_id),
        ("commander", commander_id), ("sensors", sensors_id),
    ]:
        if sid == char_id:
            my_station = station
            break

    # Gunner stations
    gunner_stations_raw = crew.get("gunner_stations", {})
    gunner_out = {}
    weapons_list = []
    # Effective weapon fire control from mods + power + orders
    eff_wfc = eff.get("weapon_fc", {}) if eff else {}
    if tmpl:
        for i, wpn in enumerate(tmpl.weapons):
            gid = gunner_stations_raw.get(str(i), 0)
            gunner_stub = await _char_stub(gid)
            gunner_out[str(i)] = gunner_stub
            if gid == char_id:
                my_station = "gunner"
            # Apply effective fire control bonus from mods/power/orders
            fc_display = wpn.fire_control
            fc_extra = eff_wfc.get(i, eff_wfc.get(-1, 0)) if eff_wfc else 0
            if isinstance(fc_extra, int) and fc_extra > 0:
                base_fc = DicePool.parse(wpn.fire_control)
                boosted = DicePool(base_fc.dice, base_fc.pips + fc_extra)
                # Normalise pips → dice
                boosted = DicePool(boosted.dice + boosted.pips // 3,
                                   boosted.pips % 3)
                fc_display = str(boosted)
            weapons_list.append({
                "index":       i,
                "name":        wpn.name,
                "damage":      wpn.damage,
                "fire_control":fc_display,
                "arc":         wpn.fire_arc,
                "ion":         getattr(wpn, "ion", False),
                "tractor":     getattr(wpn, "tractor", False),
                "manned_by":   gunner_stub["name"] if gunner_stub else None,
            })
    crew_out["gunner_stations"] = gunner_out

    # ── Contacts (nearby ships in same zone) ──────────────────────────────────
    contacts = []
    seen_ids = {ship["id"]}  # Skip self
    traffic_mgr = get_traffic_manager()

    # Player/DB ships in space (same source as ScanCommand uses)
    try:
        db_ships = await db.get_ships_in_space()
        for s in db_ships:
            if s["id"] in seen_ids:
                continue
            # Check same zone BEFORE adding to seen_ids.
            # NPC traffic ships exist in DB with docked_at=None but store
            # zone="" — the traffic manager holds their real zone in memory.
            # Adding them to seen_ids here would block the traffic manager
            # loop from adding them as contacts, emptying the radar.
            s_sys = s.get("systems", "{}")
            if isinstance(s_sys, str):
                try: s_sys = json.loads(s_sys)
                except Exception: s_sys = {}
            s_zone = s_sys.get("current_zone", "")
            if s_zone != zone_id:
                continue
            seen_ids.add(s["id"])
            # Get range/position from grid (may not be registered)
            try:
                rng = grid.get_range(ship["id"], s["id"])
                rng_str = rng.name.lower() if rng else "long"
            except Exception:
                rng_str = "long"
            try:
                pos = grid.get_relative_position(ship["id"], s["id"])
                pos_str = pos.name.lower() if pos else "front"
            except Exception:
                pos_str = "front"
            s_tmpl = reg.get(s.get("template", ""))
            # D-client.3 (F11): derive hull condition for the target panel.
            # Strings exactly match CONDITION_COLORS keys in the client.
            cond = ""
            if s_tmpl:
                try:
                    hull_pool = DicePool.parse(s_tmpl.hull)
                    total_pips = hull_pool.total_pips()
                    dmg = s.get("hull_damage", 0) or 0
                    frac = dmg / max(total_pips, 1)
                    if   frac <= 0:    cond = "Pristine"
                    elif frac < 0.25:  cond = "Light Damage"
                    elif frac < 0.5:   cond = "Moderate Damage"
                    elif frac < 0.75:  cond = "Heavy Damage"
                    elif frac < 1.0:   cond = "Critical Damage"
                    else:              cond = "Destroyed"
                except Exception:
                    cond = ""
            contacts.append({
                "ship_id":   s["id"],
                "name":      s.get("name", f"Ship #{s['id']}"),
                "ship_class":s_tmpl.name if s_tmpl else s.get("template", ""),
                "range":     rng_str,
                "position":  pos_str,
                "is_npc":    False,
                "is_player": True,
                "hostile":   False,
                "archetype": "",
                "condition": cond,
            })
    except Exception as e:
        log.warning("build_space_state: DB ship contacts failed: %s", e)

    # NPC traffic ships in same zone
    try:
        traffic_ships = traffic_mgr.get_zone_ships(zone_id)
        for ts in traffic_ships:
            if ts.ship_id in seen_ids:
                continue
            seen_ids.add(ts.ship_id)
            try:
                rng = grid.get_range(ship["id"], ts.ship_id)
                rng_str = rng.name.lower() if rng else "long"
            except Exception:
                rng_str = "long"
            try:
                pos = grid.get_relative_position(ship["id"], ts.ship_id)
                pos_str = pos.name.lower() if pos else "front"
            except Exception:
                pos_str = "front"
            archetype = getattr(ts, "archetype", "")
            if hasattr(archetype, "value"):
                archetype = archetype.value
            hostile = archetype in ("imperial_patrol", "pirate", "bounty_hunter")
            contacts.append({
                "ship_id":   ts.ship_id,
                "name":      ts.sensors_name(),   # respects transponder spoofing
                "ship_class":ts.display_name,     # TrafficShip has no .template field
                "range":     rng_str,
                "position":  pos_str,
                "is_npc":    True,
                "is_player": False,
                "hostile":   hostile,
                "archetype": archetype,
                # D-client.3 (F11): traffic ships don't track hull damage
                # in the traffic system — they're abstract until pulled
                # into combat (which materializes a ShipInstance). Until
                # then their condition is always Pristine.
                "condition": "Pristine",
            })
    except Exception as e:
        log.warning("build_space_state: NPC traffic contacts failed: %s", e)

    # ── Transit state ─────────────────────────────────────────────────────────
    in_hyperspace        = bool(systems.get("in_hyperspace"))
    hyperspace_dest      = systems.get("hyperspace_dest_name") or systems.get("hyperspace_dest")
    hyperspace_ticks_rem = systems.get("hyperspace_ticks_remaining", 0)
    hyperspace_eta       = hyperspace_ticks_rem  # 1 tick ≈ 1 second
    # Pct complete — needs the original total ticks. Emits None (null) when
    # the total wasn't recorded (legacy jumps from before this field shipped)
    # so the client can render an indeterminate progress state rather than
    # "stuck at 0%". New jumps always have the total.
    hyperspace_total = systems.get("hyperspace_ticks_total", 0) or 0
    if in_hyperspace and hyperspace_total > 0:
        hyperspace_pct = round(
            (1.0 - (hyperspace_ticks_rem / hyperspace_total)) * 100
        )
        hyperspace_pct = max(0, min(100, hyperspace_pct))
    else:
        hyperspace_pct = None

    in_sublight    = bool(systems.get("sublight_transit"))
    transit_dest   = systems.get("sublight_dest", "")
    transit_ticks  = systems.get("sublight_ticks_remaining", 0)

    # ── Target lock — derived from active lockon registry. Surfaces the
    # strongest lock-on this ship has against any contact in this zone.
    # The lockon registry stores (attacker_ship_id, target_ship_id) -> bonus
    # dice (max +2D per R&E). We pick the highest bonus entry where the
    # target is among our current contacts.
    target_lock = None
    try:
        lockons = grid._lockon_bonuses if hasattr(grid, "_lockon_bonuses") else {}
        contact_index = {c.get("ship_id"): c for c in contacts}
        best = None  # (target_id, bonus_dice)
        for (atk, tgt), bonus in lockons.items():
            if atk != ship["id"]:
                continue
            if tgt not in contact_index:
                continue
            if best is None or bonus > best[1]:
                best = (tgt, bonus)
        if best is not None:
            tgt_contact = contact_index[best[0]]
            target_lock = {
                "ship_id":    best[0],
                "name":       tgt_contact.get("name", "Unknown"),
                "ship_class": tgt_contact.get("ship_class", ""),
                "range":      tgt_contact.get("range", "long"),
                "position":   tgt_contact.get("position", "front"),
                "hostile":    tgt_contact.get("hostile", False),
                "bonus_dice": best[1],
                # D-client.3 (F11): plumb condition from contact dict.
                # Empty string when no condition data available.
                "condition":  tgt_contact.get("condition", ""),
            }
    except Exception:
        log.debug("target_lock: derivation failed", exc_info=True)

    # ── Anomalies (visible to this crew) ─────────────────────────────────────
    anomalies_out = []
    try:
        for a in get_anomalies_for_zone(zone_id):
            if a.resolution > 0:
                pct = a.resolution_pct()
                anomalies_out.append({
                    "id":         a.id,
                    "resolution": pct,
                    "resolved":   a.resolution >= a.scans_needed,
                    "type_hint":  a.display_name if a.resolution >= a.scans_needed else "Unknown",
                    "is_wreck":   a.is_wreck,
                })
    except Exception:
        log.warning("_char_stub: unhandled exception", exc_info=True)
        pass

    # ── Station-aware quick buttons ───────────────────────────────────────────
    _STATION_BUTTONS = {
        "pilot":     ["status", "scan", "course", "evade", "close", "flee", "hyperspace", "land"],
        "gunner":    ["status", "fire", "lockon", "scan"],
        "copilot":   ["status", "scan", "course", "assist"],
        "engineer":  ["status", "damcon", "+ship/repair"],
        "navigator": ["status", "scan", "hyperspace"],
        "sensors":   ["status", "scan", "deepscan"],
        "commander": ["status", "scan", "coordinate"],
        None:        ["status", "scan", "crew", "board", "pilot", "gunner"],
    }
    station_buttons = _STATION_BUTTONS.get(my_station, _STATION_BUTTONS[None])

    # ── Assemble payload ──────────────────────────────────────────────────────
    active = not bool(ship.get("docked_at"))
    return {
        "active":           active,
        "ship_name":        ship.get("name", "Unknown"),
        "ship_class":       tmpl.name if tmpl else ship.get("template", ""),
        "ship_category":    tmpl.key if tmpl else "light_freighter",
        "ship_id":          ship["id"],

        "zone_id":          zone_id,
        "zone_name":        zone_name,
        "zone_type":        zone_type,
        "zone_desc":        zone_desc,
        "zone_planet":      zone_planet,
        "adjacent_zones":   adjacent_zones,
        "zone_security":    zone_security,
        "zone_hazards":     zone_hazards,

        "hull_current":     hull_current,
        "hull_max":         hull_max,
        "hull_condition":   hull_condition,
        "shield_total":     shield_total,
        "shield_arcs":      shield_arcs,
        "speed":            speed,
        "maneuverability":  tmpl.maneuverability if tmpl else "1D",
        "scale":            tmpl.scale if tmpl else "starfighter",

        "systems":          sys_states,
        "ion_penalty":      systems.get("ion_penalty", 0),
        "controls_frozen":  bool(systems.get("controls_frozen")),
        "tractor_held_by":  systems.get("tractor_held_by_name"),
        "tractor_holding":  systems.get("tractor_holding_name"),
        "tractor_held":     bool(systems.get("tractor_held_by", 0)),
        "boarding_linked_to": systems.get("boarding_linked_to", 0),
        "boarding_target_name": systems.get("boarding_target_name", ""),
        "boarding_party_active": bool(systems.get("boarding_party_active")),

        "my_station":       my_station,
        "crew":             crew_out,
        "weapons":          weapons_list,

        "in_hyperspace":        in_hyperspace,
        "hyperspace_dest":      hyperspace_dest,
        "hyperspace_eta":       hyperspace_eta,
        "hyperspace_pct":       hyperspace_pct,
        "in_sublight_transit":  in_sublight,
        "transit_dest":         transit_dest,
        "transit_eta":          transit_ticks,

        "contacts":         contacts,
        "target_lock":      target_lock,
        "anomalies":        anomalies_out,
        "station_buttons":  station_buttons,
        "power_state":      (eff or {}).get("power_state", {}),
        "reactor_power":    tmpl.reactor_power if tmpl else 10,
        "silent_running":   is_silent_running(systems) if tmpl else False,
        "active_order":     systems.get("active_order"),
        "order_flags":      (eff or {}).get("order_flags", {}),
        "stealth_bonus":    (eff or {}).get("stealth_bonus", 0),
        "false_transponder":(eff or {}).get("false_transponder"),

        # Active encounter (Drop 1: space encounters)
        "encounter":        _get_encounter_state(ship["id"]),
    }


def _get_encounter_state(ship_id: int) -> dict | None:
    """Return encounter summary for HUD, or None if no active encounter."""
    try:
        from engine.space_encounters import get_encounter_manager
        mgr = get_encounter_manager()
        enc = mgr.get_encounter(ship_id)
        if enc is None:
            return None
        return {
            "id": enc.id,
            "type": enc.encounter_type,
            "state": enc.state,
            "phase": enc.phase,
            "has_choices": bool(enc.choices and not enc.chosen_key),
            "chosen": enc.chosen_key,
            "deadline_secs": int(enc.time_remaining()),
            "outcome": enc.outcome,
        }
    except Exception:
        return None


async def broadcast_space_state(ship: dict, db, session_mgr) -> None:
    """
    Send space_state JSON to all WebSocket sessions aboard the ship's bridge.
    Safe to call from any command or tick — silently drops on any error.
    Telnet sessions in the same room receive nothing (send_json is a no-op for them).
    """
    bridge_room = ship.get("bridge_room_id")
    if not bridge_room:
        return
    try:
        sessions = session_mgr.sessions_in_room(bridge_room)
    except Exception:
        log.warning("broadcast_space_state: unhandled exception", exc_info=True)
        return

    for sess in sessions:
        try:
            char_id = sess.character["id"] if sess.character else 0
            payload = await build_space_state(ship, char_id, db, session_mgr)
            await sess.send_json("space_state", payload)
        except Exception as e:
            log.warning("broadcast_space_state failed for %s: %s", sess, e)



async def _resolve_target_ship(ctx, ship: dict) -> "Optional[dict]":
    """
    Resolve a target ship name (from ctx.args) for any space combat command.

    Searches:
      1. DB ships in space by name (handles player ships)
      2. Traffic manager ships in same zone by sensors_name()
         (handles "Unregistered fighter", "Unknown freighter" etc.)

    Returns the DB ship dict, or None if not found.
    If multiple traffic ships share the same sensor name, sends an
    ambiguity message to the session and returns the sentinel value False
    so callers can distinguish "not found" from "ambiguous".
    """
    from engine.npc_space_traffic import get_traffic_manager as _gtm2
    target_name = ctx.args.strip().lower()
    my_zone = _get_systems(ship).get("current_zone", "")

    # 1. DB ships
    for s in await ctx.db.get_ships_in_space():
        if s["id"] == ship["id"]:
            continue
        sn = s["name"].lower()
        if sn == target_name or sn.startswith(target_name):
            return s

    # 2. Traffic manager ships in same zone by sensors_name()
    zone_ships = _gtm2().get_zone_ships(my_zone)
    matches = [
        ts for ts in zone_ships
        if ts.sensors_name().lower() == target_name
        or ts.sensors_name().lower().startswith(target_name)
    ]
    if len(matches) > 1:
        await ctx.session.send_line(
            f"  {len(matches)} ships matching '{ctx.args}' in sensor range. "
            f"Use 'lockon <name>' then 'fire', or be more specific."
        )
        return False  # sentinel: ambiguous
    if matches:
        return await ctx.db.get_ship(matches[0].ship_id)

    return None


class ShipsCommand(BaseCommand):
    key = "+ships"
    aliases = ["ships", "shiplist"]
    help_text = "List available ship types. (Shortcut for +ship/list)"
    usage = "+ships"
    async def execute(self, ctx):
        ctx.switches = ["list"]
        await ShipCommand().execute(ctx)


class ShipInfoCommand(BaseCommand):
    key = "+shipinfo"
    aliases = ["shipinfo", "si"]
    help_text = "View ship type stats. (Shortcut for +ship/info)"
    usage = "+shipinfo <name>"
    async def execute(self, ctx):
        ctx.switches = ["info"]
        await ShipCommand().execute(ctx)


class BoardCommand(BaseCommand):
    key = "board"
    # Historic "gunnery" alias removed (S57) — it was a collision with
    # GunnerCommand.aliases, and "gunnery" is naturally an alias for
    # "gunner", not for boarding an NPC ship.
    aliases = []
    help_text = "Board a ship docked in this bay."
    usage = "board [ship name]"
    async def execute(self, ctx):
        char = ctx.session.character
        room_id = char["room_id"]
        ships = await ctx.db.get_ships_docked_at(room_id)
        if not ctx.args:
            if not ships:
                await ctx.session.send_line("  No ships docked here.")
                return
            await ctx.session.send_line("  Ships docked here:")
            reg = get_ship_registry()
            for s in ships:
                t = reg.get(s["template"])
                tname = t.name if t else s["template"]
                await ctx.session.send_line(f"    {ansi.BRIGHT_CYAN}{s['name']}{ansi.RESET} ({tname})")
            await ctx.session.send_line("  Usage: board <ship name>")
            return
        search = ctx.args.strip().lower()
        ship = None
        for s in ships:
            if s["name"].lower() == search or s["name"].lower().startswith(search):
                ship = s
                break
        if not ship:
            await ctx.session.send_line(f"  No ship named '{ctx.args}' docked here.")
            return
        bridge_id = ship["bridge_room_id"]
        if not bridge_id:
            await ctx.session.send_line("  That ship has no accessible interior.")
            return
        old_room = char["room_id"]
        char["room_id"] = bridge_id
        await ctx.db.save_character(char["id"], room_id=bridge_id)
        await ctx.session_mgr.broadcast_to_room(
            old_room, f"  {ansi.player_name(char['name'])} boards the {ship['name']}.",
            exclude=ctx.session)
        await ctx.session.send_line(ansi.success(f"  You board the {ship['name']}."))
        from parser.builtin_commands import LookCommand
        look_ctx = CommandContext(session=ctx.session, raw_input="look", command="look",
            args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr)
        await LookCommand().execute(look_ctx)


class DisembarkCommand(BaseCommand):
    key = "disembark"
    aliases = ["deboard", "leave_ship"]
    help_text = "Leave the ship, returning to the docking bay."
    usage = "disembark"
    async def execute(self, ctx):
        char = ctx.session.character
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if not ship["docked_at"]:
            await ctx.session.send_line("  The ship is in space! You can't disembark.")
            return
        crew = _get_crew(ship)
        char_id = char["id"]
        changed = False
        if crew.get("pilot") == char_id:
            crew["pilot"] = None
            changed = True
        gunners = crew.get("gunners", [])
        if char_id in gunners:
            gunners.remove(char_id)
            changed = True
        if changed:
            await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        char["room_id"] = ship["docked_at"]
        await ctx.db.save_character(char["id"], room_id=ship["docked_at"])
        await ctx.session.send_line(ansi.success(f"  You disembark from the {ship['name']}."))
        from parser.builtin_commands import LookCommand
        look_ctx = CommandContext(session=ctx.session, raw_input="look", command="look",
            args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr)
        await LookCommand().execute(look_ctx)


class PilotCommand(BaseCommand):
    key = "pilot"
    aliases = []
    help_text = "Take the pilot seat."
    usage = "pilot"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("pilot") == char_id:
            await ctx.session.send_line("  You're already the pilot.")
            return
        if crew.get("pilot"):
            await ctx.session.send_line("  The pilot seat is occupied.")
            return
        crew["pilot"] = char_id
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session.send_line(ansi.success("  You take the pilot seat. Controls are live."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes the pilot seat.",
            exclude=ctx.session)


class GunnerCommand(BaseCommand):
    key = "gunner"
    aliases = ["gunnery"]
    help_text = (
        "Take a gunner station. On multi-weapon ships, specify\n"
        "which weapon station by number or name.\n"
        "\n"
        "EXAMPLES:\n"
        "  gunner          -- take the first open weapon station\n"
        "  gunner 3        -- take weapon station #3\n"
        "  gunner turbo    -- take the station matching 'turbo'"
    )
    usage = "gunner [station# | weapon name]"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template or not template.weapons:
            await ctx.session.send_line("  This ship has no weapon stations.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        stations = crew.get("gunner_stations", {})
        # Already stationed?
        for idx_s, gid in stations.items():
            if gid == char_id:
                wname = template.weapons[int(idx_s)].name if int(idx_s) < len(template.weapons) else "?"
                await ctx.session.send_line(
                    f"  You're already at station #{int(idx_s)+1}: {wname}. "
                    f"Type 'vacate' first to switch.")
                return
        # Determine which station to take
        target_idx = None
        if ctx.args:
            arg = ctx.args.strip()
            # Try numeric
            try:
                n = int(arg)
                if 1 <= n <= len(template.weapons):
                    target_idx = n - 1
                else:
                    await ctx.session.send_line(
                        f"  Station #{n} doesn't exist. "
                        f"This ship has {len(template.weapons)} weapon(s).")
                    return
            except ValueError:
                # Try name match
                arg_lower = arg.lower()
                for i, w in enumerate(template.weapons):
                    if arg_lower in w.name.lower():
                        target_idx = i
                        break
                if target_idx is None:
                    await ctx.session.send_line(
                        f"  No weapon matching '{arg}'. Use '+shipstatus' to see weapons.")
                    return
        else:
            # Auto-assign: first unoccupied station
            for i in range(len(template.weapons)):
                if str(i) not in stations:
                    target_idx = i
                    break
            if target_idx is None:
                await ctx.session.send_line("  All weapon stations are occupied.")
                return
        # Check if target station is occupied
        if str(target_idx) in stations:
            occupant_id = stations[str(target_idx)]
            occ = await ctx.db.get_character(occupant_id)
            occ_name = occ["name"] if occ else f"#{occupant_id}"
            await ctx.session.send_line(
                f"  Station #{target_idx+1} is occupied by {occ_name}.")
            return
        # Assign
        stations[str(target_idx)] = char_id
        crew["gunner_stations"] = stations
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        weapon = template.weapons[target_idx]
        await ctx.session.send_line(ansi.success(
            f"  You man gunner station #{target_idx+1}: "
            f"{weapon.name} ({weapon.damage} damage, {weapon.fire_arc} arc)"))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes gunner station "
            f"#{target_idx+1}: {weapon.name}.",
            exclude=ctx.session)


class CopilotCommand(BaseCommand):
    key = "copilot"
    aliases = ["copiloting"]
    help_text = "Take the copilot seat. Adds +1D to pilot's maneuver and fire control rolls."
    usage = "copilot"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("copilot") == char_id:
            await ctx.session.send_line("  You're already the copilot.")
            return
        if crew.get("copilot"):
            await ctx.session.send_line("  The copilot seat is occupied.")
            return
        crew["copilot"] = char_id
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session.send_line(ansi.success(
            "  You take the copilot seat. Assisting with navigation and fire control."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes the copilot seat.",
            exclude=ctx.session)


class EngineerCommand(BaseCommand):
    key = "engineer"
    aliases = ["eng"]
    help_text = "Take the engineer station. Enables damage control and power management."
    usage = "engineer"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("engineer") == char_id:
            await ctx.session.send_line("  You're already at the engineer station.")
            return
        if crew.get("engineer"):
            await ctx.session.send_line("  The engineer station is occupied.")
            return
        crew["engineer"] = char_id
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session.send_line(ansi.success(
            "  You take the engineer station. Systems and damage control at your fingertips."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes the engineer station.",
            exclude=ctx.session)


class NavigatorCommand(BaseCommand):
    key = "navigator"
    aliases = ["nav"]
    help_text = "Take the navigator station. Provides astrogation support for hyperspace jumps."
    usage = "navigator"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("navigator") == char_id:
            await ctx.session.send_line("  You're already the navigator.")
            return
        if crew.get("navigator"):
            await ctx.session.send_line("  The navigator seat is occupied.")
            return
        crew["navigator"] = char_id
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session.send_line(ansi.success(
            "  You take the navigator station. Star charts online."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes the navigator station.",
            exclude=ctx.session)


class CommanderCommand(BaseCommand):
    key = "commander"
    aliases = ["command", "captain"]
    help_text = "Take the commander seat. Enables the 'coordinate' action to boost crew rolls."
    usage = "commander"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("commander") == char_id:
            await ctx.session.send_line("  You're already in command.")
            return
        if crew.get("commander"):
            await ctx.session.send_line("  The commander seat is occupied.")
            return
        crew["commander"] = char_id
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session.send_line(ansi.success(
            "  You take command. Your crew looks to you for leadership."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes command of the ship.",
            exclude=ctx.session)


class SensorsCommand(BaseCommand):
    key = "sensors"
    aliases = ["sensor"]
    help_text = "Take the sensors station. Enhances scan results with detailed readouts."
    usage = "sensors"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("sensors") == char_id:
            await ctx.session.send_line("  You're already at the sensors station.")
            return
        if crew.get("sensors"):
            await ctx.session.send_line("  The sensors station is occupied.")
            return
        crew["sensors"] = char_id
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session.send_line(ansi.success(
            "  You take the sensors station. Passive and active arrays online."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes the sensors station.",
            exclude=ctx.session)


# ── Station names for vacate/display ──
_SINGLE_STATIONS = ["pilot", "copilot", "engineer", "navigator", "commander", "sensors"]


class VacateCommand(BaseCommand):
    key = "vacate"
    aliases = ["unstation"]
    help_text = "Leave your current crew station."
    usage = "vacate"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        left = None
        # Check single-seat stations
        for station in _SINGLE_STATIONS:
            if crew.get(station) == char_id:
                crew[station] = None
                left = station
                break
        # Check gunner stations
        if not left:
            stations = crew.get("gunner_stations", {})
            for idx_s, gid in list(stations.items()):
                if gid == char_id:
                    del stations[idx_s]
                    crew["gunner_stations"] = stations
                    left = f"gunner #{int(idx_s)+1}"
                    break
        if not left:
            await ctx.session.send_line("  You're not at any crew station.")
            return
        if left == "commander":
            _v_sys = _get_systems(ship)
            if _v_sys.get("active_order"):
                _v_sys.pop("active_order", None)
                await ctx.db.update_ship(ship["id"], systems=json.dumps(_v_sys))
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session.send_line(ansi.success(
            f"  You step away from the {left} station."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} vacates the {left} station.",
            exclude=ctx.session)


class AssistCommand(BaseCommand):
    key = "assist"
    aliases = []
    help_text = (
        "Assist another crew member with their next action. "
        "Uses your relevant skill to add a bonus die to their roll."
    )
    usage = "assist <station>  (e.g. assist pilot, assist gunner)"
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: assist <station>  (pilot, gunner, engineer)")
            return
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        # Must be at a station to assist
        at_station = False
        for s in _SINGLE_STATIONS:
            if crew.get(s) == char_id:
                at_station = s
                break
        if not at_station:
            gunners = crew.get("gunners", [])
            if char_id in gunners:
                at_station = "gunner"
        if not at_station:
            await ctx.session.send_line("  You must be at a crew station to assist.")
            return
        target = ctx.args.strip().lower()
        # Validate target station has someone
        if target == "gunner":
            gunners = crew.get("gunners", [])
            if not gunners:
                await ctx.session.send_line("  No one is at a gunner station.")
                return
        elif target in _SINGLE_STATIONS:
            if not crew.get(target):
                await ctx.session.send_line(f"  No one is at the {target} station.")
                return
            if crew[target] == char_id:
                await ctx.session.send_line("  You can't assist yourself.")
                return
        else:
            await ctx.session.send_line(
                f"  Unknown station '{target}'. Options: "
                f"{', '.join(_SINGLE_STATIONS + ['gunner'])}")
            return
        # Record the assist in the crew JSON for the next action to pick up
        assists = crew.get("_assists", {})
        assists[target] = {
            "from": at_station,
            "char_id": char_id,
            "name": ctx.session.character["name"],
        }
        crew["_assists"] = assists
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[CREW]{ansi.RESET} "
            f"{ctx.session.character['name']} assists the {target}! (+1D to next roll)")


class CoordinateCommand(BaseCommand):
    key = "coordinate"
    aliases = ["coord"]
    help_text = (
        "Commander action: rally the crew. Makes a command skill check; "
        "success gives all crew +1 to their next roll this round."
    )
    usage = "coordinate"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("commander") != char_id:
            await ctx.session.send_line("  Only the commander can coordinate the crew.")
            return
        # Command skill check via centralised engine
        from engine.skill_checks import resolve_coordinate_check
        result = resolve_coordinate_check(ctx.session.character, difficulty=12)

        if result["success"]:
            # Record coordination bonus (+2 on crit, +1 normal)
            crew["_coord_bonus"] = 2 if result["critical"] else 1
            crew["_coordinated"] = True
            await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
            color = ansi.BRIGHT_GREEN
        elif result["fumble"]:
            # Fumble: -1 penalty
            crew["_coord_bonus"] = -1
            crew["_coordinated"] = True
            await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
            color = ansi.BRIGHT_RED
        else:
            color = ansi.BRIGHT_YELLOW

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {color}[COMMAND]{ansi.RESET} "
            f"{ctx.session.character['name']}: {result['message']}")


class ShipRepairCommand(BaseCommand):
    key = "+shiprepair"
    aliases = ["shiprepair", "srepair"]
    help_text = "Engineer repair action. (Shortcut for +ship/repair)"
    usage = "+shiprepair <s>"
    async def execute(self, ctx):
        ctx.switches = ["repair"]
        await ShipCommand().execute(ctx)


class MyShipsCommand(BaseCommand):
    key = "+myships"
    aliases = ["myships", "ownedships"]
    help_text = "List your ships. (Shortcut for +ship/mine)"
    usage = "+myships"
    async def execute(self, ctx):
        ctx.switches = ["mine"]
        await ShipCommand().execute(ctx)


class LaunchCommand(BaseCommand):
    key = "launch"
    aliases = ["takeoff"]
    help_text = "Launch from docking bay (pilot only). Costs fuel credits."
    usage = "launch"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if not ship["docked_at"]:
            await ctx.session.send_line("  Already in space!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can launch. Type 'pilot' first.")
            return
        systems = _get_systems(ship)
        if not systems.get("engines", True):
            await ctx.session.send_line("  Engines are damaged! Cannot launch.")
            return
        # Fuel cost: 50cr base, scaled by ship speed
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        speed = template.speed if template else 5
        fuel_cost = 50 + (speed * 10)
        char = ctx.session.character
        credits = char.get("credits", 0)
        if credits < fuel_cost:
            await ctx.session.send_line(
                f"  Not enough credits for fuel! Need {fuel_cost:,}cr, have {credits:,}cr.")
            return
        char["credits"] = credits - fuel_cost
        await ctx.db.save_character(char["id"], credits=char["credits"])
        bay_id = ship["docked_at"]
        bay = await ctx.db.get_room(bay_id)
        bay_name = bay["name"] if bay else "the docking bay"
        await ctx.db.update_ship(ship["id"], docked_at=None)
        get_space_grid().add_ship(ship["id"], speed)
        # Traffic: assign current_zone on launch
        import json as _tj
        _tsys = _tj.loads(ship.get("systems") or "{}")
        _troom = await ctx.db.get_room(bay_id)
        _troom_name = _troom["name"] if _troom else ""
        _tsys["current_zone"] = get_orbit_zone_for_room(_troom_name)
        await ctx.db.update_ship(ship["id"], systems=_tj.dumps(_tsys))
        await ctx.session_mgr.broadcast_to_room(
            bay_id, f"  The {ship['name']} lifts off with a roar of engines!")
        # Patrol encounter check for active smuggling jobs
        try:
            from parser.smuggling_commands import check_patrol_on_launch
            await check_patrol_on_launch(ctx)
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            ansi.success(
                f"  {ship['name']} launches from {bay_name}! "
                f"(Fuel: {fuel_cost:,}cr) You are now in space."))
        # Space HUD update
        try:
            ship = await ctx.db.get_ship_by_bridge(ship["bridge_room_id"])
            if ship:
                await broadcast_space_state(ship, ctx.db, ctx.session_mgr)
        except Exception as e:
            log.warning("LaunchCommand space_state broadcast failed: %s", e)
        # Spacer quest: launched
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(ctx.session, ctx.db, "space_action", action="launch")
        except Exception as _e:
            log.debug("silent except in parser/space_commands.py:1089: %s", _e, exc_info=True)


class LandCommand(BaseCommand):
    key = "land"
    aliases = ["dock"]
    help_text = "Land at a docking bay (pilot only). Docking fee applies."
    usage = "land"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Already docked!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can land.")
            return
        # Planet-aware bay lookup: find docking bay for the planet we're orbiting
        _land_planet = None
        try:
            import json as _lj2
            _land_sys = _lj2.loads(ship.get("systems") or "{}")
            _land_zone_id = _land_sys.get("current_zone", "")
            from engine.npc_space_traffic import ZONES as _LZONES
            _land_zone = _LZONES.get(_land_zone_id)
            if _land_zone and _land_zone.planet:
                _land_planet = _land_zone.planet
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        # Search for planet-specific bay, fall back to any "Docking Bay"
        _BAY_SEARCH = {
            "tatooine": "Docking Bay",
            "nar_shaddaa": "Nar Shaddaa - Docking",
            "kessel": "Kessel - Spaceport",
            "corellia": "Coronet City - Starport Docking",
        }
        _bay_query = _BAY_SEARCH.get(_land_planet, "Docking Bay")
        rooms = await ctx.db.find_rooms(_bay_query)
        if not rooms and _land_planet:
            # Fallback: try generic search
            rooms = await ctx.db.find_rooms("Docking Bay")
        if not rooms:
            await ctx.session.send_line("  No docking bays found!")
            return
        bay = rooms[0]
        # Docking fee: 25cr base (per R&E GG7), modified by zone alert level
        docking_fee = 25
        try:
            from engine.director import get_director, AlertLevel
            _alert = get_director().get_alert_level('spaceport')
            if _alert == AlertLevel.LOCKDOWN:
                docking_fee = int(docking_fee * 1.5)  # +50% imperial surcharge
            elif _alert == AlertLevel.LAX:
                docking_fee = int(docking_fee * 0.75)  # -25% low security
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        char = ctx.session.character
        credits = char.get("credits", 0)
        if credits < docking_fee:
            await ctx.session.send_line(
                f"  Not enough credits for docking fee! Need {docking_fee}cr.")
            return
        char["credits"] = credits - docking_fee
        await ctx.db.save_character(char["id"], credits=char["credits"])
        try:
            await ctx.db.log_credit(char["id"], -docking_fee, "docking_fee",
                                     char["credits"])
        except Exception as _e:
            log.debug("silent except in parser/space_commands.py:1162: %s", _e, exc_info=True)
        await ctx.db.update_ship(ship["id"], docked_at=bay["id"])
        get_space_grid().remove_ship(ship["id"])
        # Traffic: clear current_zone on land
        import json as _lj
        _lsys = _lj.loads(ship.get("systems") or "{}")
        _lsys.pop("current_zone", None)
        await ctx.db.update_ship(ship["id"], systems=_lj.dumps(_lsys))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            ansi.success(
                f"  {ship['name']} docks at {bay['name']}. "
                f"(Docking fee: {docking_fee}cr)"))
        await ctx.session_mgr.broadcast_to_room(
            bay["id"], f"  The {ship['name']} settles onto the landing pad.")
        # Space HUD: send inactive state so client reverts to ground mode
        try:
            ship_refreshed = await ctx.db.get_ship_by_bridge(ship["bridge_room_id"])
            if ship_refreshed:
                await broadcast_space_state(ship_refreshed, ctx.db, ctx.session_mgr)
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        # ── Customs check (Drop 18) ─────────────────────────────────────────
        # Imperial presence at Tatooine orbit and Corellia
        _IMPERIAL_PLANETS = {"tatooine", "corellia"}
        if _land_planet in _IMPERIAL_PLANETS:
            await _run_customs_check(ctx, ship, _land_planet)

        # Ship's log: planet landed
        if _land_planet:
            try:
                from engine.ships_log import log_event as _log_ev
                char = ctx.session.character
                _milestones = await _log_ev(ctx.db, char, "planets_landed", _land_planet)
                for _ms in _milestones:
                    await ctx.session.send_line(
                        f"  {ansi.BRIGHT_GREEN}[SHIP LOG]{ansi.RESET} "
                        f"{_ms['msg']}  "
                        + (f"+{_ms['cp']} CP" if _ms.get('cp') else "")
                        + (f"  Title: {ansi.BRIGHT_YELLOW}{_ms['title']}{ansi.RESET}"
                           if _ms.get('title') else "")
                    )
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass

        # Discovery quest: fire first-visit trigger for this planet
        if _land_planet and _land_planet != "tatooine":
            try:
                from engine.tutorial_v2 import on_planet_land
                await on_planet_land(ctx.session, ctx.db, _land_planet)
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass
        # Profession chain: planet arrival trigger
        if _land_planet:
            try:
                from engine.tutorial_v2 import check_profession_chains
                await check_profession_chains(
                    ctx.session, ctx.db,
                    f"planet_land_{_land_planet}",
                )
                # Smuggler's Run step 5 completion: docked on Nar Shaddaa
                if _land_planet == "nar_shaddaa":
                    await check_profession_chains(
                        ctx.session, ctx.db, "docked_nar_shaddaa"
                    )
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass
        # Spacer quest: landed
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(
                ctx.session, ctx.db, "space_action",
                action="land", planet=_land_planet or "",
            )
        except Exception as _e:
            log.debug("silent except in parser/space_commands.py:1242: %s", _e, exc_info=True)


class ShipCommand(BaseCommand):
    # S57a — expanded umbrella: absorbs aliases from sibling classes
    # (ShipsCommand, MyShipsCommand, ShipInfoCommand, ShipRepairCommand,
    # ShipNameCommand). The sibling classes remain registered at their
    # bare keys for backward compatibility, but the umbrella now owns
    # every alias route.
    key = "+ship"
    aliases = [
        # Original ship-status aliases
        "ship", "+shipstatus", "shipstatus", "ss", "+ss",
        # From ShipsCommand (key=+ships) — ship catalog
        "ships", "shiplist", "+ships",
        # From MyShipsCommand (key=+myships) — owned fleet
        "myships", "ownedships", "+myships",
        # From ShipInfoCommand (key=+shipinfo) — template specs
        "shipinfo", "si", "+shipinfo",
        # From ShipRepairCommand (key=+shiprepair) — engineer repair
        "shiprepair", "srepair", "+shiprepair",
        # From ShipNameCommand (key=shipname) — rename owned ship
        "shipname", "+shipname",
    ]
    help_text = (
        "Your ship's status, info, and management.\n"
        "\n"
        "SWITCHES:\n"
        "  /status         -- tactical status of your ship (default)\n"
        "  /info           -- template specs for a ship type\n"
        "  /list           -- list all available ship types\n"
        "  /mine           -- list ships you own\n"
        "  /rename <name>  -- rename your owned ship (S57a)\n"
        "  /repair         -- repair a damaged system (engineer)\n"
        "  /mods           -- view installed ship modifications\n"
        "  /install <item> -- install a crafted ship component\n"
        "  /uninstall <#>  -- remove a mod by slot number\n"
        "  /log            -- view ship's log and milestones\n"
        "  /quirks         -- view installed ship quirks\n"
        "\n"
        "EXAMPLES:\n"
        "  +ship              -- your ship's status\n"
        "  +ship/info x-wing  -- X-Wing stats\n"
        "  +ship/list         -- browse ship catalog\n"
        "  +ship/mine         -- your fleet\n"
        "  +ship/rename Millennium Falcon  -- rename your ship\n"
        "  +ship/mods         -- installed modifications\n"
        "  +ship/install Engine Booster (Basic)\n"
        "  +ship/uninstall 0  -- remove mod in slot 0"
    )
    usage = "+ship [/status|/info|/list|/mine|/rename|/repair|/mods|/install|/uninstall]"
    valid_switches = ["status", "info", "list", "mine", "rename",
                      "repair", "mods", "install", "uninstall",
                      "log", "quirks"]

    async def execute(self, ctx):
        if "list" in ctx.switches:
            return await self._show_list(ctx)
        if "info" in ctx.switches:
            return await self._show_info(ctx)
        if "mine" in ctx.switches:
            return await self._show_mine(ctx)
        if "rename" in ctx.switches:
            # S57a — delegate to ShipNameCommand which owns the logic.
            return await ShipNameCommand().execute(ctx)
        if "repair" in ctx.switches:
            return await self._show_repair(ctx)
        if "mods" in ctx.switches:
            return await self._show_mods(ctx)
        if "install" in ctx.switches:
            return await self._install_mod(ctx)
        if "uninstall" in ctx.switches:
            return await self._uninstall_mod(ctx)
        if "log" in ctx.switches:
            return await self._show_log(ctx)
        if "quirks" in ctx.switches:
            return await self._show_quirks(ctx)
        # Default: status
        return await self._show_status(ctx)

    async def _show_status(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return
        instance = ShipInstance(
            id=ship["id"], template_key=ship["template"],
            name=ship["name"], hull_damage=ship.get("hull_damage", 0))
        systems = _get_systems(ship)
        instance.systems_damaged = [k for k, v in systems.items()
                                    if isinstance(v, bool) and not v]
        await ctx.session.send_line(ansi.header(f"=== {ship['name']} ==="))
        for line in format_ship_status(template, instance):
            await ctx.session.send_line(line)
        crew = _get_crew(ship)
        await ctx.session.send_line("")
        pilot_id = crew.get("pilot")
        if pilot_id:
            pilot = await ctx.db.get_character(pilot_id)
            await ctx.session.send_line(f"  Pilot: {pilot['name'] if pilot else f'#{pilot_id}'}")
        else:
            await ctx.session.send_line(f"  Pilot: {ansi.DIM}(empty){ansi.RESET}")
        # Other single stations
        for station in ["copilot", "engineer", "navigator", "commander", "sensors"]:
            sid = crew.get(station)
            if sid:
                sc = await ctx.db.get_character(sid)
                await ctx.session.send_line(
                    f"  {station.title()}: {sc['name'] if sc else f'#{sid}'}")
        # Weapons — show effective fire control from mods/power/orders
        stations = crew.get("gunner_stations", {})
        status_eff = _get_effective_for_ship(ship) or {}
        status_wfc = status_eff.get("weapon_fc", {})
        if template.weapons:
            await ctx.session.send_line(f"  {ansi.BOLD}Weapons:{ansi.RESET}")
            for i, w in enumerate(template.weapons):
                gid = stations.get(str(i))
                if gid:
                    g = await ctx.db.get_character(gid)
                    crew_str = f"[{g['name'] if g else f'#{gid}'}]"
                else:
                    crew_str = f"{ansi.DIM}[empty]{ansi.RESET}"
                flags = ""
                if w.tractor:
                    flags += f"  {ansi.BRIGHT_YELLOW}TRACTOR{ansi.RESET}"
                if w.ion:
                    flags += f"  {ansi.BRIGHT_BLUE}ION{ansi.RESET}"
                # Effective fire control
                fc_display = w.fire_control
                fc_extra = status_wfc.get(i, status_wfc.get(-1, 0)) if status_wfc else 0
                if isinstance(fc_extra, int) and fc_extra > 0 and fc_extra != -99:
                    base_fc = DicePool.parse(w.fire_control)
                    boosted = DicePool(base_fc.dice + (base_fc.pips + fc_extra) // 3,
                                       (base_fc.pips + fc_extra) % 3)
                    fc_display = f"{ansi.BRIGHT_GREEN}{boosted}{ansi.RESET}"
                await ctx.session.send_line(
                    f"    {i+1}. {crew_str:14s} {w.name:30s} "
                    f"{w.damage:>5s}  FC:{fc_display}  {w.fire_arc}{flags}")
        # Ion/tractor status
        if systems.get("ion_penalty", 0) > 0:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_BLUE}[ION]{ansi.RESET} "
                f"Controls ionized: -{systems['ion_penalty']}D penalty")
        if systems.get("controls_frozen"):
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[FROZEN]{ansi.RESET} "
                f"Controls frozen — no actions possible!")
        if systems.get("tractor_held_by"):
            holder = await ctx.db.get_ship(systems["tractor_held_by"])
            hname = holder["name"] if holder else "unknown"
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[TRACTOR]{ansi.RESET} "
                f"Held by {hname} — type 'resist' to break free")
        if systems.get("tractor_holding"):
            held = await ctx.db.get_ship(systems["tractor_holding"])
            hname = held["name"] if held else "unknown"
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}[TRACTOR]{ansi.RESET} "
                f"Holding {hname} in tractor beam")
        if systems.get("boarding_linked_to"):
            linked = await ctx.db.get_ship(systems["boarding_linked_to"])
            lname = linked["name"] if linked else "unknown"
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[BOARDING]{ansi.RESET} "
                f"Linked to {lname} — type 'boarding_link' to cross")
        # Location
        if ship["docked_at"]:
            bay = await ctx.db.get_room(ship["docked_at"])
            await ctx.session.send_line(
                f"\n  Location: Docked at {bay['name'] if bay else '?'}")
        else:
            await ctx.session.send_line(f"\n  Location: In space")
            grid = get_space_grid()
            tac = grid.format_tactical(ship["id"])
            if tac:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_CYAN}Tactical:{ansi.RESET}")
                for line in tac:
                    await ctx.session.send_line(line)
        await ctx.session.send_line("")

    # ── Modification commands (Drop 12) ─────────────────────────────────────

    async def _show_mods(self, ctx):
        """Show installed modifications on the player's current ship."""
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return
        systems = _get_systems(ship)
        from engine.starships import format_mods_display
        for line in format_mods_display(template, systems):
            await ctx.session.send_line(line)

    async def _install_mod(self, ctx):
        """Install a crafted ship component from inventory. (+ship/install <item name>)"""
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if not ship.get("docked_at"):
            await ctx.session.send_line(
                "  Ship must be docked to install modifications. Land first.")
            return

        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return

        item_name = (ctx.args or "").strip()
        if not item_name:
            await ctx.session.send_line(
                "  Usage: +ship/install <component name>\n"
                "  Use 'inventory' to see your items.")
            return

        # Find matching component in character inventory
        char = ctx.session.character
        char_id = char["id"]
        try:
            inv_raw = char.get("inventory", "[]")
            import json as _j
            inv = _j.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        except Exception:
            inv = []

        component = None
        comp_idx = -1
        for idx, item in enumerate(inv):
            if not isinstance(item, dict):
                continue
            if item.get("type") != "ship_component":
                continue
            if (item_name.lower() in item.get("name", "").lower() or
                    item_name.lower() in item.get("key", "").lower()):
                component = item
                comp_idx = idx
                break

        if not component:
            await ctx.session.send_line(
                f"  No ship component matching '{item_name}' in your inventory.\n"
                f"  Use 'inventory' to see your items. Components must be crafted first.")
            return

        systems = _get_systems(ship)
        mods = systems.get("modifications", [])

        # Check mod slot availability
        if len(mods) >= template.mod_slots:
            await ctx.session.send_line(
                f"  No mod slots available. This ship has {template.mod_slots} slot(s), "
                f"all occupied. Use +ship/uninstall <#> to free a slot.")
            return

        # Cargo capacity check
        from engine.starships import get_effective_stats as _ges
        effective = _ges(template, systems)
        cargo_remaining = template.cargo - effective["cargo_used_by_mods"]
        cargo_weight = component.get("cargo_weight", 10)
        if cargo_weight > cargo_remaining:
            await ctx.session.send_line(
                f"  Insufficient cargo capacity. Component requires {cargo_weight}t, "
                f"only {cargo_remaining}t available after existing mods.")
            return

        # Max stat boost check
        stat_target = component.get("stat_target", "")
        stat_boost  = component.get("stat_boost", 1)
        quality     = component.get("quality", 80)
        from engine.starships import _quality_factor, _pip_count, _MOD_MAX_SPEED, _MOD_MAX_PIPS
        factor      = _quality_factor(quality)
        eff_boost   = max(1, round(stat_boost * factor))

        if stat_target == "speed":
            current_boost = effective["speed"] - template.speed
            if current_boost + eff_boost > _MOD_MAX_SPEED:
                await ctx.session.send_line(
                    f"  Speed already at maximum modification (+{_MOD_MAX_SPEED}). "
                    f"Cannot install.")
                return
        elif stat_target in _MOD_MAX_PIPS:
            base_pips = _pip_count(getattr(template, stat_target, "0D"))
            curr_pips = _pip_count(effective.get(stat_target, getattr(template, stat_target, "0D")))
            if curr_pips - base_pips + eff_boost > _MOD_MAX_PIPS[stat_target]:
                await ctx.session.send_line(
                    f"  {stat_target.title()} already at maximum modification boost. "
                    f"Cannot install.")
                return

        # Installation skill check
        install_difficulty = max(5, component.get("craft_difficulty", 16) - 4)
        from engine.skill_checks import perform_skill_check
        from engine.character import SkillRegistry
        skill_reg = SkillRegistry()
        skill_reg.load_default()
        from engine.starships import get_repair_skill_name, get_weapon_repair_skill
        if stat_target == "fire_control":
            repair_skill = get_weapon_repair_skill(template.scale)
        else:
            repair_skill = get_repair_skill_name(template.scale)
        try:
            result = perform_skill_check(char, repair_skill, install_difficulty, skill_reg)
        except Exception:
            result = None

        if result is not None and result.fumble:
            # Fumble: component quality drops one tier
            new_quality = max(0, quality - 20)
            component["quality"] = new_quality
            inv[comp_idx] = component
            char["inventory"] = _j.dumps(inv)
            await ctx.db.save_character(char_id, inventory=char["inventory"])
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[FUMBLE]{ansi.RESET} Installation catastrophically failed! "
                f"Component quality degraded to {new_quality}%.\n"
                f"  (Roll: {result.roll} vs {install_difficulty})")
            return

        if result is not None and not result.success:
            await ctx.session.send_line(
                f"  Installation failed. The component doesn't seat properly.\n"
                f"  (Roll: {result.roll} vs {install_difficulty}) — Try again.")
            return

        # Success: add mod, remove from inventory
        roll_str = f"Roll: {result.roll} vs {install_difficulty}" if result else "auto"
        mod_entry = {
            "slot":           len(mods),
            "component_key":  component.get("key", "unknown"),
            "component_name": component.get("name", item_name),
            "quality":        quality,
            "stat_target":    stat_target,
            "stat_boost":     stat_boost,
            "cargo_weight":   cargo_weight,
            "craft_difficulty": component.get("craft_difficulty", 16),
            "installed_by":   char.get("name", "Unknown"),
            "weapon_slot":    component.get("weapon_slot", None),
        }
        mods.append(mod_entry)
        systems["modifications"] = mods
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))

        # Remove from inventory
        inv.pop(comp_idx)
        char["inventory"] = _j.dumps(inv)
        await ctx.db.save_character(char_id, inventory=char["inventory"])

        await ctx.session.send_line(
            ansi.success(
                f"  {component.get('name', item_name)} installed successfully! "
                f"({roll_str})"
            )
        )
        await ctx.session.send_line(
            f"  +{eff_boost} {stat_target} effective boost applied. "
            f"Slots used: {len(mods)}/{template.mod_slots}.")

        # Quirk roll: 25% chance on success, 50% on failed install (not reached here)
        import random as _qr
        quirk_chance = 0.25
        if _qr.random() < quirk_chance:
            from engine.starships import roll_quirk
            existing_quirk_keys = [q["key"] for q in mods if "key" in q]
            quirk = roll_quirk(existing_quirk_keys)
            if quirk:
                _qsys = _get_systems(ship)
                _qsys.setdefault("quirks", []).append(quirk)
                await ctx.db.update_ship(ship["id"], systems=json.dumps(_qsys))
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_YELLOW}[QUIRK]{ansi.RESET} "
                    f"The modification introduced a quirk: {quirk['desc']}"
                )

    async def _uninstall_mod(self, ctx):
        """Remove a mod by slot index. (+ship/uninstall <slot#>)"""
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if not ship.get("docked_at"):
            await ctx.session.send_line(
                "  Ship must be docked to remove modifications. Land first.")
            return

        slot_str = (ctx.args or "").strip()
        if not slot_str.isdigit():
            await ctx.session.send_line(
                "  Usage: +ship/uninstall <slot number>\n"
                "  Use +ship/mods to see slot numbers.")
            return

        slot_idx = int(slot_str)
        systems = _get_systems(ship)
        mods = systems.get("modifications", [])

        if slot_idx < 0 or slot_idx >= len(mods):
            await ctx.session.send_line(
                f"  No mod in slot {slot_idx}. "
                f"Valid slots: 0–{len(mods)-1}.")
            return

        removed = mods.pop(slot_idx)
        # Re-index remaining mods
        for i, m in enumerate(mods):
            m["slot"] = i
        systems["modifications"] = mods
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))

        # Return component to inventory
        char = ctx.session.character
        char_id = char["id"]
        try:
            inv_raw = char.get("inventory", "[]")
            import json as _j2
            inv = _j2.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        except Exception:
            inv = []

        returned_item = {
            "type":             "ship_component",
            "key":              removed.get("component_key", "unknown"),
            "name":             removed.get("component_name", "Component"),
            "quality":          removed.get("quality", 80),
            "stat_target":      removed.get("stat_target", ""),
            "stat_boost":       removed.get("stat_boost", 1),
            "cargo_weight":     removed.get("cargo_weight", 10),
            "craft_difficulty": removed.get("craft_difficulty", 16),
        }
        inv.append(returned_item)
        char["inventory"] = _j2.dumps(inv)
        await ctx.db.save_character(char_id, inventory=char["inventory"])

        await ctx.session.send_line(
            ansi.success(
                f"  {removed.get('component_name', 'Component')} uninstalled. "
                f"Returned to your inventory."
            )
        )
        await ctx.session.send_line(
            f"  Slots remaining: {template.mod_slots - len(mods)}/{template.mod_slots}."
            if (reg := get_ship_registry()) and (t := reg.get(ship["template"]))
            else ""
        )

    async def _show_log(self, ctx):
        from engine.ships_log import get_ships_log, format_ships_log
        char = ctx.session.character
        ships_log = get_ships_log(char)
        lines = format_ships_log(ships_log)
        for line in lines:
            await ctx.session.send_line(line)

    async def _show_quirks(self, ctx):
        from engine.starships import format_quirks_display
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        systems = _get_systems(ship)
        lines = format_quirks_display(systems)
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_CYAN}Ship Quirks — {ship['name']}{ansi.RESET}"
        )
        for line in lines:
            await ctx.session.send_line(line)

    async def _show_list(self, ctx):
        reg = get_ship_registry()
        await ctx.session.send_line(
            f"  {ansi.BOLD}{'Ship':30s} {'Scale':12s} {'Speed':>5s} "
            f"{'Hull':>5s} {'Shields':>7s} {'Hyper':>5s}{ansi.RESET}")
        await ctx.session.send_line(
            f"  {'-'*30} {'-'*12} {'-'*5} {'-'*5} {'-'*7} {'-'*5}")
        for t in sorted(reg.all_templates(), key=lambda x: (x.scale, -x.speed)):
            hyper = f"x{t.hyperdrive}" if t.hyperdrive else "None"
            await ctx.session.send_line(
                f"  {t.name:30s} {t.scale:12s} {t.speed:>5d} "
                f"{t.hull:>5s} {t.shields:>7s} {hyper:>5s}")
        await ctx.session.send_line(
            f"\n  {ansi.DIM}{reg.count} types. "
            f"'+ship/info <name>' for details.{ansi.RESET}")

    async def _show_info(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("  Usage: +ship/info <ship name>")
            return
        reg = get_ship_registry()
        template = reg.find_by_name(ctx.args.strip())
        if not template:
            await ctx.session.send_line(
                f"  Unknown ship: '{ctx.args}'. Try '+ship/list'.")
            return
        await ctx.session.send_line(ansi.header(f"=== {template.name} ==="))
        for line in format_ship_status(template):
            await ctx.session.send_line(line)
        await ctx.session.send_line(
            f"\n  {ansi.DIM}Cost: {template.cost:,} credits{ansi.RESET}\n")

    async def _show_mine(self, ctx):
        char_id = ctx.session.character["id"]
        ships = await ctx.db.get_ships_owned_by(char_id)
        if not ships:
            await ctx.session.send_line("  You don't own any ships.")
            return
        reg = get_ship_registry()
        await ctx.session.send_line(f"  {ansi.BOLD}Your Ships:{ansi.RESET}")
        for s in ships:
            template = reg.get(s["template"])
            tname = template.name if template else s["template"]
            loc = "in space"
            if s["docked_at"]:
                bay = await ctx.db.get_room(s["docked_at"])
                loc = f"docked at {bay['name']}" if bay else "docked"
            hull_dmg = s.get("hull_damage", 0)
            dmg_str = (f"  {ansi.BRIGHT_RED}[{hull_dmg} hull damage]"
                       f"{ansi.RESET}") if hull_dmg else ""
            await ctx.session.send_line(
                f"    {s['name']} ({tname}) -- {loc}{dmg_str}")
        await ctx.session.send_line("")

    async def _show_repair(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("engineer") != char_id:
            await ctx.session.send_line(
                "  Only the engineer can repair. "
                "Take the station with 'engineer' first.")
            return
        damcon = DamConCommand()
        await damcon.execute(ctx)


class ScanCommand(BaseCommand):
    key = "scan"
    aliases = []
    help_text = "Scan for nearby ships -- shows range and position."
    usage = "scan"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Scanners work in space. Launch first.")
            return
        systems = _get_systems(ship)
        player_zone = systems.get("current_zone", "")
        reg = get_ship_registry()
        grid = get_space_grid()
        char = ctx.session.character
        crew = _get_crew(ship)

        # ── Sensors skill check ───────────────────────────────────────────────
        # Sensors station operator gets +2D bonus.
        # Difficulty 8 (Easy) — space signals are loud, but reading them takes skill.
        from engine.skill_checks import perform_skill_check
        from engine.character import SkillRegistry, Character, DicePool
        _SCAN_DIFFICULTY = 8
        # Zone hazard: asteroid density degrades sensors
        try:
            from engine.npc_space_traffic import ZONES as _SCANZONES
            _scan_zone = _SCANZONES.get(systems.get("current_zone", ""))
            if _scan_zone and _scan_zone.hazards.get("sensor_penalty"):
                _SCAN_DIFFICULTY += _scan_zone.hazards["sensor_penalty"]
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        try:
            char_obj = Character.from_db_dict(char)
            sr = SkillRegistry()
            sr.load_default()
            base_pool = char_obj.get_skill_pool("sensors", sr)
            # Station bonus: +2D if sitting at sensors
            # Stealth bonus: target ship harder to detect (sensor_mask, silent running)
            _scan_diff = _SCAN_DIFFICULTY
            _scan_target = _get_systems(ship)  # ship is the scanning ship
            # Scan all ships in zone and apply per-target stealth

            if crew.get("sensors") == char["id"]:
                bonus = DicePool(2, 0)
                boosted = base_pool + bonus
                # Temporarily write boosted pool into char for perform_skill_check
                import json as _json
                _skills = _json.loads(char.get("skills", "{}"))
                _orig = _skills.get("sensors")
                _skills["sensors"] = str(boosted)
                char["skills"] = _json.dumps(_skills)
                scan_result = perform_skill_check(char, "sensors", _SCAN_DIFFICULTY, sr)
                # Restore
                if _orig is None:
                    _skills.pop("sensors", None)
                else:
                    _skills["sensors"] = _orig
                char["skills"] = _json.dumps(_skills)
            else:
                scan_result = perform_skill_check(char, "sensors", _SCAN_DIFFICULTY, sr)
        except Exception:
            scan_result = None  # Graceful-drop: show full scan on error

        # Determine info tier from result
        # fumble -> nothing; fail -> basic; success -> standard; crit -> deep
        if scan_result is None:
            scan_tier = "success"   # error fallback
        elif scan_result.fumble:
            scan_tier = "fumble"
        elif not scan_result.success:
            scan_tier = "fail"
        elif scan_result.critical_success:
            scan_tier = "critical"
        else:
            scan_tier = "success"

        # Show skill roll feedback to the scanner
        if scan_result is not None:
            tier_label = {
                "fumble":   f"{ansi.BRIGHT_RED}SENSOR FAILURE{ansi.RESET}",
                "fail":     f"{ansi.DIM}Basic read{ansi.RESET}",
                "success":  f"{ansi.BRIGHT_CYAN}Standard sweep{ansi.RESET}",
                "critical": f"{ansi.BRIGHT_GREEN}Deep scan{ansi.RESET}",
            }[scan_tier]
            station_note = " [+2D station]" if crew.get("sensors") == char["id"] else ""
            await ctx.session.send_line(
                f"  {ansi.DIM}[Sensors: {scan_result.pool_str} vs {_SCAN_DIFFICULTY} "
                f"— roll {scan_result.roll}]{ansi.RESET}  {tier_label}{station_note}"
            )

        if scan_tier == "fumble":
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}=== Sensor Scan ==={ansi.RESET}"
            )
            if player_zone:
                await ctx.session.send_line(f"  {ansi.DIM}Zone: {player_zone}{ansi.RESET}")
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}Sensor array offline — interference or calibration error.{ansi.RESET}"
            )
            await ctx.session.send_line("")
            return

        others = [s for s in await ctx.db.get_ships_in_space() if s["id"] != ship["id"]]
        await ctx.session.send_line(f"  {ansi.BRIGHT_CYAN}=== Sensor Scan ==={ansi.RESET}")
        if player_zone:
            await ctx.session.send_line(
                f"  {ansi.DIM}Zone: {player_zone}{ansi.RESET}")
        any_contacts = False
        scan_seen_ids = {ship["id"]}  # track to avoid double-listing traffic ships
        for s in others:
            # Zone filter: only show ships in same zone (or all if zone unknown)
            if player_zone:
                s_sys = s.get("systems", "{}")
                if isinstance(s_sys, str):
                    try: s_sys = json.loads(s_sys)
                    except Exception: s_sys = {}
                s_zone = s_sys.get("current_zone", "")
                if s_zone and s_zone != player_zone:
                    continue
                if not s_zone:
                    # Zone empty in DB — this is likely a traffic ship managed
                    # in memory. Skip it here; the traffic manager loop below
                    # will show it with the correct NPC label.
                    continue
            scan_seen_ids.add(s["id"])
            t = reg.get(s["template"])
            tname = t.name if t else s["template"]
            rng = grid.get_range(ship["id"], s["id"])
            pos = grid.get_position(ship["id"], s["id"])
            dmg = s.get("hull_damage", 0)
            if scan_tier == "fail":
                # Basic: name + range only
                await ctx.session.send_line(
                    f"  Contact: {ansi.BRIGHT_WHITE}{s['name']}{ansi.RESET} — "
                    f"Range: {rng.label}")
            elif scan_tier == "critical":
                # Deep: full data + hull % + cargo flag
                hull_pct = max(0, 100 - dmg * 10)
                status = f"Hull {hull_pct}%" if dmg > 0 else "Undamaged"
                sys_json = s.get("systems", "{}")
                try:
                    import json as _j; _sys = _j.loads(sys_json) if isinstance(sys_json, str) else sys_json
                except Exception:
                    _sys = {}
                cargo_flag = ""
                if _sys.get("smuggling_job"):
                    cargo_flag = f"  {ansi.BRIGHT_YELLOW}[CARGO ANOMALY DETECTED]{ansi.RESET}"
                await ctx.session.send_line(
                    f"  Contact: {ansi.BRIGHT_WHITE}{s['name']}{ansi.RESET} ({tname})")
                await ctx.session.send_line(
                    f"    Range: {rng.label}  Position: {pos}  Status: {status}{cargo_flag}")
            else:
                # Standard: name, type, range, position, status
                status = "Active" if dmg == 0 else f"Damaged ({dmg} hits)"
                await ctx.session.send_line(
                    f"  Contact: {ansi.BRIGHT_WHITE}{s['name']}{ansi.RESET} ({tname})")
                await ctx.session.send_line(
                    f"    Range: {rng.label}  Position: {pos}  Status: {status}")
            any_contacts = True
        # ── NPC Traffic ships in same zone ────────────────────────────────────
        if player_zone:
            traffic_ships = get_traffic_manager().get_zone_ships(player_zone)
            for ts in traffic_ships:
                if ts.ship_id in scan_seen_ids:
                    continue  # Already shown via DB ships loop
                scan_seen_ids.add(ts.ship_id)
                if scan_tier == "fail":
                    await ctx.session.send_line(
                        f"  Contact: {ansi.BRIGHT_WHITE}{ts.sensors_name()}{ansi.RESET} "
                        f"— Range: local zone")
                elif scan_tier == "critical":
                    archetype_label = ts.archetype.value.title()
                    cargo_flag = ""
                    if ts.archetype.value.lower() == "smuggler":
                        cargo_flag = f"  {ansi.BRIGHT_YELLOW}[IRREGULAR POWER SIGNATURE]{ansi.RESET}"
                    await ctx.session.send_line(
                        f"  Contact: {ansi.BRIGHT_WHITE}{ts.sensors_name()}{ansi.RESET} "
                        f"[NPC {archetype_label}]{cargo_flag}")
                    await ctx.session.send_line(
                        f"    Zone: {player_zone}  Transponder: {ts.transponder_type}"
                        f"  Captain: {ts.captain_name}")
                else:
                    await ctx.session.send_line(
                        f"  Contact: {ansi.BRIGHT_WHITE}{ts.sensors_name()}{ansi.RESET} "
                        f"[NPC {ts.archetype.value.title()}]")
                    await ctx.session.send_line(
                        f"    Zone: {player_zone}  Transponder: {ts.transponder_type}"
                        f"  Captain: {ts.captain_name}")
                any_contacts = True
        if not any_contacts:
            await ctx.session.send_line("  No other ships detected.")
        await ctx.session.send_line("")

        # Update space HUD (populates radar with contacts)
        try:
            await broadcast_space_state(ship, ctx.db, ctx.session_mgr)
        except Exception:
            log.warning("ScanCommand: broadcast_space_state failed", exc_info=True)


class DeepScanCommand(BaseCommand):
    key = "deepscan"
    aliases = []
    help_text = (
        "Sweep for hidden anomalies in the current zone. "
        "Use 'deepscan <id>' to focus-scan a detected anomaly."
    )
    usage = "deepscan [anomaly id]"

    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Deep-scan requires open space. Launch first.")
            return

        from engine.space_anomalies import (
            get_anomalies_for_zone, spawn_anomalies_for_zone,
            get_anomaly_by_id, advance_scan, get_scan_output,
            check_scan_cooldown, set_scan_cooldown, list_zone_anomalies_text,
        )
        from engine.skill_checks import perform_skill_check
        from engine.character import SkillRegistry, Character, DicePool as _DP
        from engine.npc_space_traffic import ZONES as _DSZONES
        from server import ansi as ha
        import json as _j

        systems  = _get_systems(ship)
        zone_id  = systems.get("current_zone", "")
        char     = ctx.session.character
        char_id  = char["id"]
        crew     = _get_crew(ship)

        # ── Fumble cooldown check ─────────────────────────────────────────
        remaining = check_scan_cooldown(char_id, zone_id)
        if remaining is not None:
            await ctx.session.send_line(
                f"  {ha.BRIGHT_RED}[DEEP SCAN]{ha.RESET} Sensor array still recalibrating after signal scramble. "
                f"({int(remaining)}s remaining)"
            )
            return

        # ── Zone-type lookup (for anomaly spawning) ───────────────────────
        zone_obj  = _DSZONES.get(zone_id)
        zone_type = zone_obj.type.value if zone_obj else "deep_space"

        # ── Skill check: sensors, base diff 15 (Moderate) ────────────────
        _DIFF = 15
        if zone_obj and zone_obj.hazards.get("sensor_penalty"):
            _DIFF += zone_obj.hazards["sensor_penalty"]

        try:
            char_obj  = Character.from_db_dict(char)
            sr        = SkillRegistry()
            sr.load_default()
            base_pool = char_obj.get_skill_pool("sensors", sr)
            if crew.get("sensors") == char_id:
                bonus   = _DP(2, 0)
                boosted = base_pool + bonus
                _sk = _j.loads(char.get("skills", "{}"))
                _orig = _sk.get("sensors")
                _sk["sensors"] = str(boosted)
                char["skills"] = _j.dumps(_sk)
                result = perform_skill_check(char, "sensors", _DIFF, sr)
                if _orig is None:
                    _sk.pop("sensors", None)
                else:
                    _sk["sensors"] = _orig
                char["skills"] = _j.dumps(_sk)
            else:
                result = perform_skill_check(char, "sensors", _DIFF, sr)
        except Exception:
            result = None  # graceful-drop

        fumble   = result.fumble   if result else False
        critical = result.critical if result else False
        success  = (not fumble) and (result is None or result.total >= _DIFF)

        # ── Fumble: scramble signal, apply cooldown ───────────────────────
        if fumble:
            set_scan_cooldown(char_id, zone_id, 60.0)
            await ctx.session.send_line(
                f"  {ha.BRIGHT_RED}[DEEP SCAN]{ha.RESET} "
                "Sensor burst backscatter scrambles the return signal. "
                "Array needs 60 seconds to recalibrate."
            )
            return

        # ── Determine target anomaly ──────────────────────────────────────
        focus_id = None
        if ctx.args:
            try:
                focus_id = int(ctx.args[0])
            except ValueError:
                await ctx.session.send_line("  Usage: deepscan [anomaly id]")
                return

        anomalies = get_anomalies_for_zone(zone_id)

        if focus_id is not None:
            # Focused scan on a specific anomaly
            target = get_anomaly_by_id(zone_id, focus_id)
            if target is None:
                await ctx.session.send_line(
                    f"  {ha.BRIGHT_RED}[DEEP SCAN]{ha.RESET} "
                    f"No anomaly #{focus_id} detected in this zone."
                )
                return
            if not success:
                await ctx.session.send_line(
                    f"  {ha.BRIGHT_YELLOW}[DEEP SCAN]{ha.RESET} "
                    f"Signal too faint to resolve anomaly #{focus_id} further. Try again."
                )
                return
            status = advance_scan(target, critical=critical)
            out    = get_scan_output(target, status, ha)
            await ctx.session.send_line(out)
            return

        # ── Wide scan: look for new anomalies ─────────────────────────────
        if not success:
            await ctx.session.send_line(
                f"  {ha.BRIGHT_YELLOW}[DEEP SCAN]{ha.RESET} "
                "Sensor sweep returns nothing conclusive. Zone looks clear — for now."
            )
            # Still show already-detected anomalies
            sidebar = list_zone_anomalies_text(zone_id, ha)
            if sidebar:
                await ctx.session.send_line(sidebar)
            return

        # Success: try to detect an undetected anomaly (resolution == 0)
        undetected = [a for a in anomalies if a.resolution == 0]
        if undetected:
            target = undetected[0]
            status = advance_scan(target, critical=critical)
            out    = get_scan_output(target, status, ha)
            await ctx.session.send_line(out)
        else:
            # No hidden anomalies; may trigger a fresh spawn
            newly_spawned = spawn_anomalies_for_zone(zone_id, zone_type)
            if newly_spawned:
                status = advance_scan(newly_spawned, critical=critical)
                out    = get_scan_output(newly_spawned, status, ha)
                await ctx.session.send_line(out)
            else:
                await ctx.session.send_line(
                    f"  {ha.BRIGHT_CYAN}[DEEP SCAN]{ha.RESET} "
                    "Sweep complete. No anomalies detected in this sector."
                )

        # Always append sidebar of currently known anomalies
        sidebar = list_zone_anomalies_text(zone_id, ha)
        if sidebar:
            await ctx.session.send_line(sidebar)


class FireCommand(BaseCommand):
    key = "fire"
    aliases = []
    help_text = "Fire your weapon at a target (gunner station, in space). Checks range and fire arc."
    usage = "fire <target ship name>"

    # ── Pipeline orchestrator ────────────────────────────────────────
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: fire <target ship name>")
            return
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Can't fire while docked!")
            return

        # Phase 1: Space security gate
        space_sec = await self._check_space_security(ctx, ship)
        if space_sec is None:
            return  # secured zone — blocked

        # Phase 2: Gunner station + weapon + target-name parsing
        parsed = await self._parse_station_weapon_target(ctx, ship)
        if parsed is None:
            return
        template, weapon, gunner_idx, target_name = parsed

        # Phase 3: Target resolution (DB + traffic)
        target_ship = await self._resolve_target(ctx, ship, target_name)
        if target_ship is None:
            return
        reg = get_ship_registry()
        target_template = reg.get(target_ship["template"])
        if not target_template:
            await ctx.session.send_line("  Target data error.")
            return

        # Phase 4: PvP consent check (contested zones only)
        if not await self._check_pvp_consent(ctx, target_ship, space_sec):
            return

        # Phase 5: Arc check + build combat pools
        pools = await self._build_combat_pools(
            ctx, ship, template, target_ship, target_template,
            weapon, gunner_idx)
        if pools is None:
            return

        # Phase 6: Dispatch by weapon type
        if weapon.tractor:
            await self._handle_tractor_fire(ctx, ship, target_ship, pools)
        else:
            await self._handle_standard_fire(
                ctx, ship, target_ship, target_template, pools)

        # Phase 7: Broadcast HUD updates to both crews
        await self._broadcast_space_hud(ctx, ship, target_ship)

    # ── Phase helpers ────────────────────────────────────────────────

    async def _check_space_security(self, ctx, ship):
        """Return 'secured' | 'contested' | 'lawless' — or None if blocked.

        Design doc §8:
          DOCK zones = secured (no fire)
          ORBIT / HYPERSPACE_LANE = contested (PvP needs consent)
          DEEP_SPACE = lawless (unrestricted)
        """
        from engine.npc_space_traffic import get_space_security
        space_sec = "lawless"  # fail-open default
        try:
            systems_chk = _get_systems(ship)
            zone_id_chk = systems_chk.get("current_zone", "")
            space_sec = get_space_security(zone_id_chk)

            if space_sec == "secured":
                await ctx.session.send_line(
                    "  \033[1;33mPort authority sensors would detect weapons fire "
                    "immediately. You'd be vaporized by the defense grid.\033[0m"
                )
                return None
        except Exception:
            log.warning("_check_space_security: zone lookup failed", exc_info=True)
            # fail-open: allow fire
        return space_sec

    async def _parse_station_weapon_target(self, ctx, ship):
        """Resolve gunner station, parse 'with <weapon>' / trailing N, return
        (template, weapon, gunner_idx, target_name) or None on error."""
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        stations = crew.get("gunner_stations", {})
        my_station = None
        for idx_s, gid in stations.items():
            if gid == char_id:
                my_station = int(idx_s)
                break
        if my_station is None:
            await ctx.session.send_line(
                "  You're not at a gunner station. Type 'gunner' first.")
            return None
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return None

        raw_args = ctx.args.strip()
        weapon_override = None

        # "fire <target> with <weapon>"
        if " with " in raw_args.lower():
            parts = raw_args.lower().rsplit(" with ", 1)
            raw_args = parts[0].strip()
            weapon_search = parts[1].strip()
            for i, w in enumerate(template.weapons):
                if weapon_search in w.name.lower():
                    weapon_override = i
                    break
            if weapon_override is None:
                await ctx.session.send_line(
                    f"  No weapon matching '{weapon_search}'.")
                return None
        # "fire <target> <N>" (trailing number)
        elif raw_args and raw_args.split()[-1].isdigit():
            parts = raw_args.rsplit(None, 1)
            if len(parts) == 2:
                n = int(parts[1])
                if 1 <= n <= len(template.weapons):
                    weapon_override = n - 1
                    raw_args = parts[0].strip()

        # Resolve weapon index with station-occupancy enforcement
        if weapon_override is not None:
            if weapon_override != my_station:
                if (str(weapon_override) in stations
                        and stations[str(weapon_override)] != char_id):
                    occ = await ctx.db.get_character(stations[str(weapon_override)])
                    await ctx.session.send_line(
                        f"  Weapon #{weapon_override+1} is manned by "
                        f"{occ['name'] if occ else '?'}. Use your own station.")
                    return None
            gunner_idx = weapon_override
        else:
            gunner_idx = my_station

        if gunner_idx >= len(template.weapons):
            await ctx.session.send_line("  Weapon station error.")
            return None

        weapon = template.weapons[gunner_idx]
        target_name = raw_args.lower()
        return (template, weapon, gunner_idx, target_name)

    async def _resolve_target(self, ctx, ship, target_name):
        """Find target ship: DB ships first, then traffic manager by sensor name.

        Returns target_ship dict, or None on miss/ambiguity (error already sent).
        """
        # DB ships (player ships + traffic ships stored in DB)
        systems_self = _get_systems(ship)
        my_zone = systems_self.get("current_zone", "")
        for s in await ctx.db.get_ships_in_space():
            if s["id"] == ship["id"]:
                continue
            sname = s["name"].lower()
            if sname == target_name or sname.startswith(target_name):
                return s

        # Traffic manager sensors-name search (handles "Unregistered fighter" etc.)
        from engine.npc_space_traffic import get_traffic_manager as _gtm
        zone_ships = _gtm().get_zone_ships(my_zone)
        matches = [
            ts for ts in zone_ships
            if ts.sensors_name().lower() == target_name
            or ts.sensors_name().lower().startswith(target_name)
        ]
        if len(matches) > 1:
            await ctx.session.send_line(
                f"  {len(matches)} ships matching '{ctx.args}' on scanners. "
                f"Use 'lockon <n>' to designate one, then 'fire'."
            )
            return None
        if matches:
            return await ctx.db.get_ship(matches[0].ship_id)

        await ctx.session.send_line(f"  No ship '{ctx.args}' on scanners.")
        return None

    async def _check_pvp_consent(self, ctx, target_ship, space_sec):
        """Return False and send message if firing on a player ship in a
        contested zone without prior challenge. True otherwise (fail-open)."""
        try:
            target_crew_chk = _get_crew(target_ship)
            target_pilot_id = target_crew_chk.get("pilot")
            target_is_player_ship = False
            if target_pilot_id:
                tp_row = await ctx.db.get_character(target_pilot_id)
                if tp_row and tp_row.get("account_id"):
                    target_is_player_ship = True

            if target_is_player_ship and space_sec == "contested":
                from parser.combat_commands import _pvp_active, _PVP_CHALLENGE_TTL
                import time as _fire_time
                now = _fire_time.time()
                my_id = ctx.session.character["id"]
                their_id = target_pilot_id
                consented = (
                    _pvp_active.get((my_id, their_id), 0) > now - _PVP_CHALLENGE_TTL or
                    _pvp_active.get((their_id, my_id), 0) > now - _PVP_CHALLENGE_TTL
                )
                if not consented:
                    await ctx.session.send_line(
                        f"  \033[1;33mOpening fire on a civilian vessel in patrolled "
                        f"space would bring every patrol in the sector down on you.\033[0m\n"
                        f"  Issue a \033[1;37mchallenge\033[0m on the ground first, or "
                        f"engage them in deep space where no one's watching."
                    )
                    return False
        except Exception:
            log.warning("_check_pvp_consent: check failed", exc_info=True)
            # fail-open — allow fire on exception
        return True

    async def _build_combat_pools(self, ctx, ship, template,
                                  target_ship, target_template,
                                  weapon, gunner_idx):
        """Build the bundle of dice pools and effective values needed for
        attack resolution. Returns dict, or None if arc check fails.

        Keys: rng, rel_pos, gunnery_pool, target_pilot_pool,
              target_shields_pool, eff_target_hull, eff_target_maneuver,
              eff_weapon, target_systems, target_eff
        """
        grid = get_space_grid()
        rng = grid.get_range(ship["id"], target_ship["id"])
        rel_pos = grid.get_position(ship["id"], target_ship["id"])

        # Arc check — short-circuit if weapon can't fire at this position
        if not can_weapon_fire(weapon.fire_arc, rel_pos):
            await ctx.session.send_line(
                f"  {weapon.name} cannot fire at targets to your {rel_pos}! "
                f"(Weapon arc: {weapon.fire_arc})")
            return None

        from engine.character import Character, SkillRegistry
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")

        # Gunnery skill — routed by weapon type
        gunnery_skill = weapon.skill.replace("_", " ") if weapon.skill else "starship gunnery"
        gunnery_pool = char_obj.get_skill_pool(gunnery_skill, sr)

        # Target piloting — routed by target scale
        target_crew = _get_crew(target_ship)
        target_pilot_pool = DicePool(2, 0)
        if target_crew.get("pilot"):
            tp = await ctx.db.get_character(target_crew["pilot"])
            if tp:
                tp_char = Character.from_db_dict(tp)
                tp_pilot_skill = (
                    "capital ship piloting" if target_template.scale == "capital"
                    else "starfighter piloting")
                target_pilot_pool = tp_char.get_skill_pool(tp_pilot_skill, sr)

        # Arc-specific shields — prefer damaged per-arc dice over full template
        target_systems = _get_systems(target_ship)
        target_eff = _get_effective_for_ship(target_ship) or {}
        attacker_eff = _get_effective_for_ship(ship) or {}
        eff_shields_str = target_eff.get("shields", target_template.shields)
        arc_map = {"front": "shield_front", "rear": "shield_rear",
                   "left": "shield_left", "right": "shield_right"}
        arc_key = arc_map.get(rel_pos, "shield_front")
        arc_dice = target_systems.get(arc_key)
        if arc_dice is not None:
            target_shields_pool = DicePool(int(arc_dice), 0)
        else:
            target_shields_pool = DicePool.parse(eff_shields_str)

        eff_target_hull = DicePool.parse(
            target_eff.get("hull", target_template.hull))
        eff_target_maneuver = DicePool.parse(
            target_eff.get("maneuverability", target_template.maneuverability))

        # Effective fire control for attacker weapon
        eff_weapon = weapon
        atk_wfc = attacker_eff.get("weapon_fc", {})
        fc_extra_pips = atk_wfc.get(gunner_idx, atk_wfc.get(-1, 0)) if atk_wfc else 0
        if isinstance(fc_extra_pips, int) and fc_extra_pips > 0 and fc_extra_pips != -99:
            base_fc = DicePool.parse(weapon.fire_control)
            boosted_fc = DicePool(
                base_fc.dice + (base_fc.pips + fc_extra_pips) // 3,
                (base_fc.pips + fc_extra_pips) % 3)
            from copy import copy as _copy
            eff_weapon = _copy(weapon)
            eff_weapon.fire_control = str(boosted_fc)

        return {
            "rng": rng,
            "rel_pos": rel_pos,
            "gunnery_pool": gunnery_pool,
            "target_pilot_pool": target_pilot_pool,
            "target_shields_pool": target_shields_pool,
            "eff_target_hull": eff_target_hull,
            "eff_target_maneuver": eff_target_maneuver,
            "eff_weapon": eff_weapon,
            "weapon": weapon,
            "template": template,
            "target_template": target_template,
            "target_systems": target_systems,
            "target_eff": target_eff,
        }

    async def _handle_tractor_fire(self, ctx, ship, target_ship, pools):
        """Tractor beam resolution + capture side-effects + broadcasts."""
        from engine.starships import resolve_tractor_attack
        weapon = pools["weapon"]
        tresult = resolve_tractor_attack(
            attacker_skill=pools["gunnery_pool"],
            weapon=pools["eff_weapon"],
            attacker_scale=pools["template"].scale_value,
            target_hull=pools["eff_target_hull"],
            target_scale=pools["target_template"].scale_value,
            range_band=pools["rng"],
        )
        if tresult.captured:
            t_sys = _get_systems(target_ship)
            t_sys["tractor_held_by"] = ship["id"]
            await ctx.db.update_ship(target_ship["id"],
                                     systems=json.dumps(t_sys))
            a_sys = _get_systems(ship)
            a_sys["tractor_holding"] = target_ship["id"]
            await ctx.db.update_ship(ship["id"],
                                     systems=json.dumps(a_sys))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[TRACTOR]{ansi.RESET} "
            f"{ctx.session.character['name']} fires {weapon.name} at "
            f"{target_ship['name']}! {tresult.narrative.strip()}")
        if target_ship.get("bridge_room_id"):
            if tresult.captured:
                await ctx.session_mgr.broadcast_to_room(
                    target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_RED}[ALERT]{ansi.RESET} "
                    f"Caught in tractor beam from {ship['name']}! "
                    f"Type 'resist' to break free.")
            elif tresult.hit:
                await ctx.session_mgr.broadcast_to_room(
                    target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_YELLOW}[SENSORS]{ansi.RESET} "
                    f"Tractor beam from {ship['name']} — broke free!")
            else:
                await ctx.session_mgr.broadcast_to_room(
                    target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_YELLOW}[SENSORS]{ansi.RESET} "
                    f"Tractor beam from {ship['name']} — missed!")

    async def _handle_standard_fire(self, ctx, ship, target_ship,
                                    target_template, pools):
        """Standard / ion attack resolution + damage / ion application +
        hit-or-miss broadcasts to both bridges."""
        weapon = pools["weapon"]
        result = resolve_space_attack(
            attacker_skill=pools["gunnery_pool"],
            weapon=pools["eff_weapon"],
            attacker_scale=pools["template"].scale_value,
            target_pilot_skill=pools["target_pilot_pool"],
            target_maneuverability=pools["eff_target_maneuver"],
            target_hull=pools["eff_target_hull"],
            target_shields=pools["target_shields_pool"],
            target_scale=target_template.scale_value,
            range_band=pools["rng"],
            relative_position=pools["rel_pos"],
            attacker_ship_id=ship["id"],
            target_ship_id=target_ship["id"])

        await self._apply_hull_damage(
            ctx, ship, target_ship, target_template, pools, result)
        await self._apply_ion_effect(
            ctx, target_ship, target_template, pools, result)

        # Attacker bridge broadcast
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_RED}[WEAPONS]{ansi.RESET} "
            f"{ctx.session.character['name']} fires {weapon.name} at "
            f"{target_ship['name']}! {result.narrative.strip()}")
        # Target bridge broadcast
        if target_ship.get("bridge_room_id"):
            if result.hit:
                await ctx.session_mgr.broadcast_to_room(
                    target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_RED}[ALERT]{ansi.RESET} "
                    f"Hit by {weapon.name} from {ship['name']}! "
                    f"{result.narrative.strip()}")
            else:
                await ctx.session_mgr.broadcast_to_room(
                    target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_YELLOW}[SENSORS]{ansi.RESET} "
                    f"Incoming fire from {ship['name']} -- missed!")

    async def _apply_hull_damage(self, ctx, ship, target_ship,
                                 target_template, pools, result):
        """Write hull damage + system hits to DB. Handle traffic-ship kills:
        bounty award, salvage wreck spawn, achievement."""
        if result.hull_damage <= 0:
            return
        new_dmg = target_ship.get("hull_damage", 0) + result.hull_damage
        updates = {"hull_damage": new_dmg}
        if result.systems_hit:
            systems = _get_systems(target_ship)
            for s in result.systems_hit:
                systems[s] = False
            updates["systems"] = json.dumps(systems)
        await ctx.db.update_ship(target_ship["id"], **updates)

        # Kill detection — use effective hull
        eff_hull_str = pools["target_eff"].get("hull", target_template.hull)
        try:
            hull_dice = int(eff_hull_str.split("D")[0]) if "D" in eff_hull_str else 3
        except Exception:
            hull_dice = 3
        destroyed_threshold = hull_dice * 6
        if new_dmg < destroyed_threshold:
            return

        traffic_mgr = get_traffic_manager()
        ts = traffic_mgr.get_ship(target_ship["id"])
        if ts is None:
            return

        awarded = await traffic_mgr.handle_traffic_ship_destroyed(
            target_ship["id"], ctx.session.character,
            ctx.db, ctx.session_mgr,
        )
        if awarded:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[BOUNTY]{ansi.RESET} "
                f"Pirate destroyed! You recover {awarded:,} credits from the wreckage."
            )
        # Salvageable wreck anomaly
        try:
            from engine.space_anomalies import add_wreck_anomaly
            wreck_zone = _get_systems(ship).get("current_zone", "")
            if wreck_zone:
                add_wreck_anomaly(wreck_zone,
                                  target_ship.get("name", "Unknown Vessel"))
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_CYAN}[SALVAGE]{ansi.RESET} "
                    f"Wreckage detected. Type 'salvage' to recover components (2 min window)."
                )
        except Exception:
            log.warning("_apply_hull_damage: salvage spawn failed",
                        exc_info=True)
        # Achievement: ship_destroyed
        # FIX: previous version referenced undefined `char` — use session.character
        try:
            from engine.achievements import on_ship_destroyed
            await on_ship_destroyed(
                ctx.db, ctx.session.character["id"], session=ctx.session)
        except Exception as _e:
            log.debug(
                "silent except in _apply_hull_damage (on_ship_destroyed): %s",
                _e, exc_info=True)

    async def _apply_ion_effect(self, ctx, target_ship, target_template,
                                pools, result):
        """Apply ion-weapon effect: controls_dead, ion_penalty stacking,
        controls_frozen threshold check."""
        if not result.ion_disabled or result.ion_disabled == "":
            return
        t_systems = _get_systems(target_ship)
        if result.ion_disabled == "dead":
            t_systems["controls_dead"] = True
            t_systems["ion_penalty"] = 99
        else:
            try:
                ion_count = int(result.ion_disabled)
            except ValueError:
                ion_count = 1
            old_penalty = t_systems.get("ion_penalty", 0)
            t_systems["ion_penalty"] = old_penalty + ion_count
            eff_maneuver_str = pools["target_eff"].get(
                "maneuverability", target_template.maneuverability)
            maneuver_dice = DicePool.parse(eff_maneuver_str).dice
            if (t_systems["ion_penalty"] >= maneuver_dice
                    and maneuver_dice > 0):
                t_systems["controls_frozen"] = True
        await ctx.db.update_ship(target_ship["id"],
                                 systems=json.dumps(t_systems))

    async def _broadcast_space_hud(self, ctx, ship, target_ship):
        """Refresh space HUD for both ships' crews after an exchange."""
        try:
            await broadcast_space_state(ship, ctx.db, ctx.session_mgr)
        except Exception:
            log.warning("_broadcast_space_hud: attacker ship update failed",
                        exc_info=True)
        if target_ship.get("bridge_room_id"):
            try:
                await broadcast_space_state(target_ship, ctx.db,
                                            ctx.session_mgr)
            except Exception:
                log.warning("_broadcast_space_hud: target ship update failed",
                            exc_info=True)


class LockOnCommand(BaseCommand):
    key = "lockon"
    aliases = ["lock", "targetlock"]
    help_text = (
        "Spend a round locking your targeting computer on a target. "
        "+1D to your next fire at that target per round of lock-on, max +3D. "
        "Broken by target evasive maneuvers or switching targets."
    )
    usage = "lockon <target ship name>"

    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: lockon <target ship name>")
            return

        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Can't lock on while docked!")
            return

        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        gunners = crew.get("gunners", [])
        if char_id not in gunners:
            await ctx.session.send_line(
                "  You're not at a gunner station. Type 'gunner' first."
            )
            return

        # Find target ship (DB + traffic manager sensor names)
        target_ship = await _resolve_target_ship(ctx, ship)
        if target_ship is False:
            return  # ambiguous — message already sent
        if not target_ship:
            await ctx.session.send_line(f"  No ship '{ctx.args}' on scanners.")
            return

        # Range check — can't lock on to out-of-range targets
        grid = get_space_grid()
        rng = grid.get_range(ship["id"], target_ship["id"])
        if rng == SpaceRange.OUT_OF_RANGE:
            await ctx.session.send_line("  Target is out of range — cannot lock on.")
            return

        # Apply lock-on (clears any existing lock on a different target)
        grid.clear_lockon_by_attacker(ship["id"])
        new_bonus = grid.add_lockon(ship["id"], target_ship["id"])

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[WEAPONS]{ansi.RESET} "
            f"{ctx.session.character['name']} locks targeting computer on "
            f"{target_ship['name']}... (+{new_bonus}D to next shot)"
        )


class CloseRangeCommand(BaseCommand):
    key = "close"
    aliases = ["approach"]
    help_text = "Close range to a target (pilot only). Opposed piloting roll, speed advantage matters."
    usage = "close <target ship>"
    async def execute(self, ctx):
        await self._maneuver(ctx, "close")

    async def _maneuver(self, ctx, action):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  You're docked!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can maneuver.")
            return
        if not ctx.args:
            await ctx.session.send_line(f"  Usage: {action} <target ship>")
            return
        # Find target ship (DB + traffic manager sensor names)
        target_ship = await _resolve_target_ship(ctx, ship)
        if target_ship is False:
            return  # ambiguous — message already sent
        if not target_ship:
            await ctx.session.send_line(f"  No ship '{ctx.args}' on scanners.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        target_template = reg.get(target_ship["template"])
        if not template or not target_template:
            await ctx.session.send_line("  Ship data error.")
            return
        from engine.character import Character, SkillRegistry
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")
        pilot_pool = char_obj.get_skill_pool("starfighter piloting", sr)
        target_crew = _get_crew(target_ship)
        target_pilot_pool = DicePool(2, 0)
        if target_crew.get("pilot"):
            tp = await ctx.db.get_character(target_crew["pilot"])
            if tp:
                tp_char = Character.from_db_dict(tp)
                target_pilot_pool = tp_char.get_skill_pool("starfighter piloting", sr)
        grid = get_space_grid()
        # Use effective stats for maneuverability and speed
        my_eff = _get_effective_for_ship(ship) or {}
        tgt_eff = _get_effective_for_ship(target_ship) or {}
        success, narrative = grid.resolve_maneuver(
            pilot_id=ship["id"],
            pilot_skill=pilot_pool,
            pilot_maneuverability=DicePool.parse(my_eff.get("maneuverability", template.maneuverability)),
            pilot_speed=my_eff.get("speed", template.speed),
            target_id=target_ship["id"],
            target_pilot_skill=target_pilot_pool,
            target_maneuverability=DicePool.parse(tgt_eff.get("maneuverability", target_template.maneuverability)),
            target_speed=tgt_eff.get("speed", target_template.speed),
            action=action)
        color = ansi.BRIGHT_GREEN if success else ansi.BRIGHT_YELLOW
        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {color}[HELM]{ansi.RESET} {narrative}")
        if target_ship.get("bridge_room_id"):
            if success:
                await ctx.session_mgr.broadcast_to_room(target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_YELLOW}[SENSORS]{ansi.RESET} "
                    f"{ship['name']} is maneuvering! {narrative}")


class FleeShipCommand(BaseCommand):
    key = "fleeship"
    aliases = ["breakaway"]
    help_text = "Increase range from a target (pilot only). Speed advantage matters."
    usage = "fleeship <target ship>"
    async def execute(self, ctx):
        cmd = CloseRangeCommand()
        await cmd._maneuver(ctx, "flee")


class TailCommand(BaseCommand):
    key = "tail"
    aliases = ["getbehind"]
    help_text = "Get behind a target ship (pilot only). Puts you in their rear arc."
    usage = "tail <target ship>"
    async def execute(self, ctx):
        cmd = CloseRangeCommand()
        await cmd._maneuver(ctx, "tail")


class OutmaneuverCommand(BaseCommand):
    key = "outmaneuver"
    aliases = ["shake"]
    help_text = "Shake a pursuer off your tail (pilot only). Resets to head-on engagement."
    usage = "outmaneuver <target ship>"
    async def execute(self, ctx):
        cmd = CloseRangeCommand()
        await cmd._maneuver(ctx, "outmaneuver")


class EvadeCommand(BaseCommand):
    key = "evade"
    aliases = ["evasive"]
    help_text = "Evasive maneuvers -- broadcast to crew (pilot only)."
    usage = "evade"
    async def execute(self, ctx):
        from engine.starships import resolve_evade, roll_hazard_table
        from engine.character import Character, SkillRegistry

        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Can't evade while docked!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can evade.")
            return

        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Unknown ship template.")
            return

        # Build pilot pool — use effective maneuverability
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")
        pilot_pool = char_obj.get_skill_pool("starfighter piloting", sr)
        my_eff = _get_effective_for_ship(ship) or {}
        maneuver_pool = DicePool.parse(my_eff.get("maneuverability", template.maneuverability))

        # Check engine state
        systems = _get_systems(ship)
        engine_state = systems.get("engines", "working")
        if isinstance(engine_state, bool):
            engine_state = "working" if engine_state else "damaged"

        result = resolve_evade(
            pilot_skill=pilot_pool,
            maneuverability=maneuver_pool,
            engine_state=engine_state,
            num_actions=1,
        )

        # Broadcast roll result
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} throws the ship into evasive maneuvers! "
            f"{result.narrative.strip()}"
        )

        if result.all_tails_broken:
            # Reset all position pairs involving this ship
            grid = get_space_grid()
            ship_id = ship["id"]
            partners = list(
                {k[1] for k in grid._positions if k[0] == ship_id}
                | {k[0] for k in grid._positions if k[1] == ship_id}
            )
            for other_id in partners:
                if other_id != ship_id:
                    grid.set_position(ship_id, other_id, RelativePosition.FRONT)
                    grid.set_position(other_id, ship_id, RelativePosition.FRONT)

        elif not result.success and not result.narrative.startswith("  Engines"):
            # Hazard check: miss by 5+ triggers hazard table
            margin = result.difficulty - result.roll_total
            if margin >= 5:
                hazard = roll_hazard_table(systems)
                await ctx.session_mgr.broadcast_to_room(
                    ship["bridge_room_id"],
                    hazard.narrative
                )
                if hazard.systems_damaged or hazard.hull_damage:
                    updates = {}
                    if hazard.hull_damage:
                        updates["hull_damage"] = (
                            ship.get("hull_damage", 0) + hazard.hull_damage
                        )
                    if hazard.systems_damaged:
                        for s in hazard.systems_damaged:
                            systems[s] = "damaged"
                        updates["systems"] = json.dumps(systems)
                    if updates:
                        await ctx.db.update_ship(ship["id"], **updates)


# ── Evasive Maneuver Commands (Priority C) ────────────────────────────────────
#
# Star Warriors maneuver adaptation for D6 R&E:
#   Pilot rolls skill + maneuverability vs fixed difficulty.
#   On success: sets a one-shot bonus on SpaceGrid that raises attacker difficulty
#   for the FIRST attack resolved against this ship this round.
#   Failure = wasted action, no bonus.
#
# Maneuver table (adapted from Star Warriors):
#   jink        difficulty 10  +5 to attacker difficulty   single action
#   barrelroll  difficulty 13  +8 to attacker difficulty   single action, higher risk
#   loop        difficulty 15  +8 + breaks tail lock        double action
#   slip        difficulty 17  +10 + repositions to flank   double action
#
# Engine state modifiers (same as evade):
#   damaged   +5 to difficulty
#   destroyed maneuver impossible

async def _resolve_maneuver_cmd(ctx, maneuver_name: str, base_diff: int,
                                 attacker_bonus: int, breaks_tail: bool,
                                 repositions_flank: bool, num_actions: int):
    """Shared implementation for all evasive maneuver commands."""
    from engine.character import Character, SkillRegistry

    ship = await _get_ship_for_player(ctx)
    if not ship:
        await ctx.session.send_line("  You're not aboard a ship.")
        return
    if ship["docked_at"]:
        await ctx.session.send_line("  Can't maneuver while docked!")
        return
    crew = _get_crew(ship)
    if crew.get("pilot") != ctx.session.character["id"]:
        await ctx.session.send_line("  Only the pilot can execute evasive maneuvers.")
        return

    reg = get_ship_registry()
    template = reg.get(ship["template"])
    if not template:
        await ctx.session.send_line("  Unknown ship template.")
        return

    # Check engine state
    systems = _get_systems(ship)
    engine_state = systems.get("engines", "working")
    if isinstance(engine_state, bool):
        engine_state = "working" if engine_state else "damaged"

    if engine_state == "destroyed":
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_RED}[HELM]{ansi.RESET} Engines destroyed — "
            f"{maneuver_name} impossible!")
        return

    engine_penalty = 5 if engine_state == "damaged" else 0
    total_diff = base_diff + engine_penalty

    # Build pilot pool — use effective maneuverability
    char_obj = Character.from_db_dict(ctx.session.character)
    sr = SkillRegistry()
    sr.load_file("data/skills.yaml")
    pilot_pool = char_obj.get_skill_pool("starfighter piloting", sr)
    my_eff = _get_effective_for_ship(ship) or {}
    maneuver_pool = DicePool.parse(my_eff.get("maneuverability", template.maneuverability))

    from engine.dice import apply_multi_action_penalty, roll_d6_pool
    pool = DicePool(
        pilot_pool.dice + maneuver_pool.dice,
        pilot_pool.pips + maneuver_pool.pips,
    )
    pool = apply_multi_action_penalty(pool, num_actions)

    from engine.dice import roll_d6_pool
    roll = roll_d6_pool(pool)

    engine_note = f" (damaged engines +5)" if engine_penalty else ""
    diff_display = f"{total_diff}{engine_note}"
    name_upper = maneuver_name.upper()
    ship_id = ship["id"]
    grid = get_space_grid()

    if roll.total >= total_diff:
        # Success — set the maneuver bonus on the grid
        grid.set_maneuver_bonus(ship_id, attacker_bonus)

        # Clear all targeting lock-ons aimed at this ship
        grid.clear_lockon_by_target(ship_id)

        # Loop/slip additional effects
        tail_note = ""
        if breaks_tail:
            # Clear all tail locks on this ship
            partners = list({k[1] for k in grid._positions if k[0] == ship_id}
                            | {k[0] for k in grid._positions if k[1] == ship_id})
            for other_id in partners:
                if other_id != ship_id:
                    if grid.get_position(other_id, ship_id) == RelativePosition.FRONT:
                        grid.set_position(other_id, ship_id, RelativePosition.FRONT)
                    grid.set_position(ship_id, other_id, RelativePosition.FRONT)
                    grid.set_position(other_id, ship_id, RelativePosition.FRONT)
            tail_note = " Tail lock broken!"

        flank_note = ""
        if repositions_flank:
            # Reposition this ship to the flank of all current pursuers
            partners = list({k[1] for k in grid._positions if k[0] == ship_id}
                            | {k[0] for k in grid._positions if k[1] == ship_id})
            for other_id in partners:
                if other_id != ship_id:
                    grid.set_position(ship_id, other_id, RelativePosition.FLANK)
                    grid.set_position(other_id, ship_id, RelativePosition.FLANK)
            flank_note = " Slipped to flank position!"

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} executes a {maneuver_name}! "
            f"+{attacker_bonus} to attacker difficulty this round.{tail_note}{flank_note} "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )
    else:
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} attempts a {maneuver_name} — failed! "
            f"Wasted action. "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )
        # Hazard check: miss by 5+ triggers hazard table
        margin = total_diff - roll.total
        if margin >= 5:
            from engine.starships import roll_hazard_table
            systems = _get_systems(ship)
            hazard = roll_hazard_table(systems)
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                hazard.narrative
            )
            if hazard.systems_damaged or hazard.hull_damage:
                updates = {}
                if hazard.hull_damage:
                    updates["hull_damage"] = (
                        ship.get("hull_damage", 0) + hazard.hull_damage
                    )
                if hazard.systems_damaged:
                    for s in hazard.systems_damaged:
                        systems[s] = "damaged"
                    updates["systems"] = json.dumps(systems)
                if updates:
                    await ctx.db.update_ship(ship["id"], **updates)


class JinkCommand(BaseCommand):
    key = "jink"
    aliases = []
    help_text = (
        "Execute a jink maneuver (pilot only). Raises attacker difficulty by +5 "
        "for the next shot against you this round. Difficulty 10."
    )
    usage = "jink"

    async def execute(self, ctx):
        await _resolve_maneuver_cmd(
            ctx,
            maneuver_name="jink",
            base_diff=10,
            attacker_bonus=5,
            breaks_tail=False,
            repositions_flank=False,
            num_actions=1,
        )


class BarrelRollCommand(BaseCommand):
    key = "barrelroll"
    aliases = ["broll"]
    help_text = (
        "Execute a barrel roll (pilot only). Raises attacker difficulty by +8 "
        "for the next shot this round. Difficulty 13."
    )
    usage = "barrelroll"

    async def execute(self, ctx):
        await _resolve_maneuver_cmd(
            ctx,
            maneuver_name="barrel roll",
            base_diff=13,
            attacker_bonus=8,
            breaks_tail=False,
            repositions_flank=False,
            num_actions=1,
        )


class LoopCommand(BaseCommand):
    key = "loop"
    aliases = ["immelmann"]
    help_text = (
        "Execute a full loop (pilot only). Raises attacker difficulty by +8 AND "
        "breaks all tail locks. Double action — costs your pilot's turn. Difficulty 15."
    )
    usage = "loop"

    async def execute(self, ctx):
        await _resolve_maneuver_cmd(
            ctx,
            maneuver_name="loop",
            base_diff=15,
            attacker_bonus=8,
            breaks_tail=True,
            repositions_flank=False,
            num_actions=2,
        )


class SlipCommand(BaseCommand):
    key = "slip"
    aliases = ["sideslip"]
    help_text = (
        "Execute a side-slip (pilot only). Raises attacker difficulty by +10 AND "
        "repositions to their flank. Double action. Difficulty 17."
    )
    usage = "slip"

    async def execute(self, ctx):
        await _resolve_maneuver_cmd(
            ctx,
            maneuver_name="side-slip",
            base_diff=17,
            attacker_bonus=10,
            breaks_tail=False,
            repositions_flank=True,
            num_actions=2,
        )


class CourseCommand(BaseCommand):
    """
    course                  -- show current zone and adjacent zones
    course <zone name>      -- set sublight course for adjacent zone
    course cancel           -- cancel current transit
    """
    key = "course"
    aliases = ["navigate", "setcourse"]
    help_text = (
        "Plot a sublight course to an adjacent zone (pilot only).\n"
        "\n"
        "USAGE:\n"
        "  course              -- show current zone and adjacent zones\n"
        "  course <zone>       -- set course for an adjacent zone\n"
        "  course cancel       -- abort current transit\n"
        "\n"
        "Transit takes 20-30 seconds depending on zone type.\n"
        "Cannot fire weapons or be targeted during transit."
    )
    usage = "course [<zone name> | cancel]"

    async def execute(self, ctx):
        """Orchestrator: validate → dispatch cancel/show/plot-course."""
        ship, systems, zone, arg = await self._validate_helm(ctx)
        if ship is None:
            return

        if arg == "cancel":
            await self._cancel_course(ctx, ship, systems)
            return

        if not arg:
            await self._show_zone_status(ctx, systems, zone)
            return

        if systems.get("sublight_transit"):
            await ctx.session.send_line(
                "  Already in transit. Use 'course cancel' to abort.")
            return

        current_zone_id = systems.get("current_zone", "")
        if not zone:
            await ctx.session.send_line(
                f"  Navigation error — unknown zone '{current_zone_id}'.")
            return

        dest_zone = self._match_destination(zone, arg)
        if not dest_zone:
            await ctx.session.send_line(
                f"  '{ctx.args}' is not an adjacent zone. "
                f"Type 'course' to see options.")
            return

        result, difficulty = self._pilot_check(ctx, dest_zone, systems)
        blocked = await self._announce_pilot_result(
            ctx, ship, result, difficulty)
        if blocked:
            return

        await self._set_transit(ctx, ship, systems, dest_zone, result, difficulty)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _validate_helm(self, ctx):
        """Check ship, pilot seat, hyperspace, ion — return (ship, systems, zone, arg) or (None,)*4."""
        from engine.npc_space_traffic import ZONES

        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return None, None, None, None
        if ship["docked_at"]:
            await ctx.session.send_line("  You're docked. Launch first.")
            return None, None, None, None
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can plot a course.")
            return None, None, None, None

        systems = _get_systems(ship)
        if systems.get("in_hyperspace"):
            await ctx.session.send_line(
                "  Already in hyperspace. Cannot plot sublight course.")
            return None, None, None, None
        if systems.get("controls_frozen"):
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[ION]{ansi.RESET} Controls are ionized — "
                f"helm is frozen!")
            return None, None, None, None

        current_zone_id = systems.get("current_zone", "")
        zone = ZONES.get(current_zone_id)
        arg = (ctx.args or "").strip().lower()
        return ship, systems, zone, arg

    async def _cancel_course(self, ctx, ship, systems):
        """Cancel current sublight transit."""
        from engine.npc_space_traffic import ZONES

        if not systems.get("sublight_transit"):
            await ctx.session.send_line("  No course plotted.")
            return
        dest_id = systems.pop("sublight_dest", "unknown")
        systems.pop("sublight_ticks_remaining", None)
        systems["sublight_transit"] = False
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
        dest_z = ZONES.get(dest_id)
        dest_name = dest_z.name if dest_z else dest_id.replace("_", " ").title()
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"Course to {dest_name} cancelled."
        )

    async def _show_zone_status(self, ctx, systems, zone):
        """Display current zone and adjacent zones."""
        from engine.npc_space_traffic import ZONES

        if not zone:
            current_zone_id = systems.get("current_zone", "")
            await ctx.session.send_line(
                f"  Current position: {current_zone_id or 'unknown'}")
            return
        await ctx.session.send_line(
            f"  {ansi.BOLD}Current Zone:{ansi.RESET} "
            f"{zone.name} [{zone.type.value}]")
        if systems.get("sublight_transit"):
            dest_id = systems.get("sublight_dest", "")
            ticks = systems.get("sublight_ticks_remaining", 0)
            dest_z = ZONES.get(dest_id)
            dname = dest_z.name if dest_z else dest_id.replace("_", " ").title()
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}In transit to:{ansi.RESET} "
                f"{dname} (~{ticks * 10}s remaining)")
        await ctx.session.send_line(
            f"  {ansi.BOLD}Adjacent zones:{ansi.RESET}")
        for adj_id in (zone.adjacent or []):
            adj = ZONES.get(adj_id)
            if adj:
                await ctx.session.send_line(
                    f"    {adj.name} [{adj.type.value}]  — course {adj.id}")

    def _match_destination(self, zone, arg):
        """Match user input to an adjacent zone. Returns zone object or None."""
        from engine.npc_space_traffic import ZONES

        for adj_id in (zone.adjacent or []):
            adj_zone = ZONES.get(adj_id)
            if not adj_zone:
                continue
            if (arg == adj_id
                    or arg in adj_id.replace("_", " ")
                    or arg in adj_zone.name.lower()):
                return adj_zone
        return None

    def _pilot_check(self, ctx, dest_zone, systems):
        """Run piloting skill check. Returns (result, difficulty)."""
        from engine.npc_space_traffic import ZoneType
        from engine.skill_checks import perform_skill_check

        _entry_hazards = dest_zone.hazards or {}
        _nav_mod = _entry_hazards.get("nav_modifier", 0)

        diff_map = {
            ZoneType.DOCK: 12,
            ZoneType.ORBIT: 8,
            ZoneType.DEEP_SPACE: 5,
            ZoneType.HYPERSPACE_LANE: 5,
        }
        difficulty = diff_map.get(dest_zone.type, 8)
        if _nav_mod:
            difficulty += _nav_mod
        ion_penalty = systems.get("ion_penalty", 0)
        if ion_penalty:
            difficulty += ion_penalty

        result = None
        try:
            result = perform_skill_check(
                ctx.session.character, "starfighter piloting", difficulty)
        except Exception:
            log.warning("_pilot_check: skill check failed", exc_info=True)

        return result, difficulty

    async def _announce_pilot_result(self, ctx, ship, result, difficulty):
        """Broadcast fumble/failure. Returns True if course is blocked."""
        if result is not None and result.fumble:
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_RED}[HELM]{ansi.RESET} "
                f"Piloting fumble! (Roll: {result.roll} vs {difficulty}) "
                f"Helm locks up — course aborted.")
            return True
        if result is not None and not result.success:
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
                f"Piloting check failed. (Roll: {result.roll} vs {difficulty}) "
                f"Cannot plot safe transit. Try again.")
            return True
        return False

    async def _set_transit(self, ctx, ship, systems, dest_zone, result, difficulty):
        """Commit transit state and broadcast course confirmation + hazard warnings."""
        from engine.npc_space_traffic import ZoneType

        ticks_map = {
            ZoneType.DOCK: 3,
            ZoneType.ORBIT: 2,
            ZoneType.DEEP_SPACE: 2,
            ZoneType.HYPERSPACE_LANE: 2,
        }
        transit_ticks = ticks_map.get(dest_zone.type, 2)
        if result is not None and result.critical_success:
            transit_ticks = max(1, transit_ticks - 1)

        systems["sublight_transit"] = True
        systems["sublight_dest"] = dest_zone.id
        systems["sublight_ticks_remaining"] = transit_ticks
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))

        roll_str = f"Roll: {result.roll} vs {difficulty}" if result else "auto"
        crit_note = " (critical)" if result and result.critical_success else ""

        _entry_hazards = dest_zone.hazards or {}
        _asteroid_density = _entry_hazards.get("asteroid_density", "")
        hazard_warn = ""
        if _asteroid_density == "heavy":
            hazard_warn = (
                f"\n  {ansi.BRIGHT_RED}[HAZARD]{ansi.RESET} "
                f"WARNING: Heavy asteroid field ahead. "
                f"Collision risk — transit through quickly.")
        elif _asteroid_density == "light":
            hazard_warn = (
                f"\n  {ansi.BRIGHT_YELLOW}[HAZARD]{ansi.RESET} "
                f"Caution: Scattered debris in destination zone.")

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[HELM]{ansi.RESET} "
            f"Course laid in for {dest_zone.name}. ({roll_str}{crit_note})\n"
            f"  Engaging sublight drive. ETA ~{transit_ticks}s."
            f"{hazard_warn}"
        )


class SpawnShipCommand(BaseCommand):
    key = "@spawn"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Spawn a ship in the current docking bay."
    usage = "@spawn <template> <ship name>"
    async def execute(self, ctx):
        if not ctx.args or " " not in ctx.args:
            await ctx.session.send_line("Usage: @spawn <template> <ship name>")
            await ctx.session.send_line("  @spawn yt_1300 Millennium Falcon")
            await ctx.session.send_line("  @spawn x_wing Red Five")
            return
        parts = ctx.args.split(None, 1)
        template_key = parts[0].lower()
        ship_name = parts[1].strip()
        reg = get_ship_registry()
        template = reg.get(template_key) or reg.find_by_name(template_key)
        if not template:
            await ctx.session.send_line(f"  Unknown template: '{template_key}'. Type 'ships'.")
            return
        char = ctx.session.character
        room_id = char["room_id"]
        crew_note = f"A co-pilot station sits to the right. " if template.crew > 1 else ""
        gun_note = f"Gunner stations are visible along the walls. " if len(template.weapons) > 1 else ""
        bridge_id = await ctx.db.create_room(
            f"{ship_name} - Bridge",
            f"The bridge of the {ship_name}.",
            f"The cockpit of this {template.name} hums with instruments. "
            f"The pilot's seat faces a wide transparisteel viewport. "
            f"{crew_note}{gun_note}"
            f"The air recyclers hum steadily.")
        ship_id = await ctx.db.create_ship(
            template=template.key, name=ship_name, owner_id=char["id"],
            bridge_room_id=bridge_id, docked_at=room_id)
        await ctx.session.send_line(ansi.success(
            f"  {ship_name} ({template.name}) spawned as ship #{ship_id}, "
            f"docked here. Bridge: #{bridge_id}."))
        await ctx.session_mgr.broadcast_to_room(room_id,
            f"  The {ship_name} settles onto the landing pad.",
            exclude=ctx.session)


class ShieldsCommand(BaseCommand):
    key = "shields"
    aliases = []
    help_text = (
        "Redistribute shield dice between fire arcs.\n"
        "Difficulty scales with arcs covered (R&E p.109):\n"
        "  1 arc: Easy (10)  |  2 arcs: Moderate (15)\n"
        "  3 arcs: Difficult (20)  |  4 arcs: V.Difficult (25)\n"
        "\n"
        "EXAMPLES:\n"
        "  shields front        -- all dice to front\n"
        "  shields rear         -- all dice to rear\n"
        "  shields even         -- split evenly front/rear\n"
        "  shields 2 1          -- 2D front, 1D rear\n"
        "  shields 1 1 1 0      -- capital: front/rear/left/right\n"
        "  shields off          -- lower shields (-2D hull per R&E)"
    )
    usage = "shields [front|rear|even|off | <F> <R> [<L> <R>]]"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return
        shield_pool = DicePool.parse(template.shields)
        total_dice = shield_pool.dice
        if total_dice <= 0:
            await ctx.session.send_line("  This ship has no shields.")
            return
        is_capital = (template.scale == "capital")
        systems = _get_systems(ship)

        # No args: show current state
        if not ctx.args:
            f = systems.get("shield_front", 0)
            r = systems.get("shield_rear", 0)
            if is_capital:
                le = systems.get("shield_left", 0)
                ri = systems.get("shield_right", 0)
                await ctx.session.send_line(
                    f"  Shields: {total_dice}D total  "
                    f"(F:{f}D  Re:{r}D  L:{le}D  Ri:{ri}D)")
            else:
                await ctx.session.send_line(
                    f"  Shields: {total_dice}D total  "
                    f"(Front: {f}D, Rear: {r}D)")
            return

        arg = ctx.args.strip().lower()
        front = rear = left = right = 0

        # Named shortcuts
        if arg == "front":
            front = total_dice
        elif arg == "rear":
            rear = total_dice
        elif arg == "even":
            front = total_dice // 2 + total_dice % 2
            rear = total_dice // 2
        elif arg == "off":
            systems["shield_front"] = 0
            systems["shield_rear"] = 0
            systems["shield_left"] = 0
            systems["shield_right"] = 0
            systems["shields_up"] = False
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
                f"  {ansi.BRIGHT_CYAN}[SHIELDS]{ansi.RESET} "
                f"Shields lowered! Hull exposed (-2D).")
            return
        else:
            # Numeric args
            parts = ctx.args.split()
            try:
                nums = [int(p) for p in parts]
            except ValueError:
                await ctx.session.send_line("  Values must be numbers or: front/rear/even/off")
                return
            if len(nums) == 2:
                front, rear = nums
            elif len(nums) == 4 and is_capital:
                front, rear, left, right = nums
            elif len(nums) == 4 and not is_capital:
                await ctx.session.send_line(
                    "  Starfighter-scale ships only have front/rear arcs. Use: shields <F> <R>")
                return
            else:
                await ctx.session.send_line(
                    f"  Usage: shields <F> <R>"
                    + (" <L> <R>" if is_capital else "")
                    + f"  (must sum to {total_dice})")
                return

        total_assigned = front + rear + left + right
        if total_assigned != total_dice:
            await ctx.session.send_line(
                f"  Must assign exactly {total_dice}D. "
                f"You assigned {total_assigned}D.")
            return
        if any(v < 0 for v in [front, rear, left, right]):
            await ctx.session.send_line("  Shield values can't be negative.")
            return

        # Count arcs covered for difficulty
        arcs_covered = sum(1 for v in [front, rear, left, right] if v > 0)
        diff_table = {1: 10, 2: 15, 3: 20, 4: 25}
        difficulty = diff_table.get(arcs_covered, 10)

        # Skill roll
        from engine.character import Character, SkillRegistry
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")
        if is_capital:
            skill_name = "capital ship shields"
        else:
            skill_name = "starship shields"
        pool = char_obj.get_skill_pool(skill_name, sr)
        from engine.dice import roll_d6_pool
        roll_result = roll_d6_pool(pool)

        if roll_result.total < difficulty:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}Shield roll failed!{ansi.RESET} "
                f"(Rolled {roll_result.total} vs difficulty {difficulty}) "
                f"Shields stay where they are.")
            return

        # Apply
        systems["shield_front"] = front
        systems["shield_rear"] = rear
        systems["shield_left"] = left
        systems["shield_right"] = right
        systems["shields_up"] = True
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))

        if is_capital and (left > 0 or right > 0):
            dist_str = f"F:{front}D  Re:{rear}D  L:{left}D  Ri:{right}D"
        else:
            dist_str = f"Front {front}D, Rear {rear}D"

        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[SHIELDS]{ansi.RESET} "
            f"Shields set: {dist_str} "
            f"(Roll: {roll_result.total} vs {difficulty})")
        try:
            await broadcast_space_state(ship, ctx.db, ctx.session_mgr)
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass


# ── Hyperspace Locations ──
HYPERSPACE_LOCATIONS = {
    "tatooine": {"name": "Tatooine", "coords": (43, 198)},
    "alderaan": {"name": "Alderaan", "coords": (34, 205)},
    "coruscant": {"name": "Coruscant", "coords": (0, 0)},
    "yavin": {"name": "Yavin IV", "coords": (325, 50)},
    "hoth": {"name": "Hoth", "coords": (295, 160)},
    "bespin": {"name": "Bespin", "coords": (296, 248)},
    "endor": {"name": "Endor", "coords": (260, 335)},
    "kessel": {"name": "Kessel", "coords": (253, 295)},
    "corellia": {"name": "Corellia", "coords": (326, 185)},
    "kashyyyk": {"name": "Kashyyyk", "coords": (260, 175)},
    "naboo": {"name": "Naboo", "coords": (283, 320)},
    "dagobah": {"name": "Dagobah", "coords": (295, 215)},
    "nar_shaddaa": {"name": "Nar Shaddaa", "coords": (100, 70)},
}


class HyperspaceCommand(BaseCommand):
    key = "hyperspace"
    aliases = ["jump", "hyper"]
    help_text = "Jump to hyperspace (pilot only). Requires hyperdrive and astrogation roll."
    usage = "hyperspace <destination>  |  hyperspace list"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Must be in space to jump. Launch first.")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can initiate hyperspace.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template or not template.hyperdrive:
            await ctx.session.send_line("  This ship has no hyperdrive!")
            return
        systems = _get_systems(ship)
        if not systems.get("hyperdrive", True):
            await ctx.session.send_line("  Hyperdrive is damaged! Cannot jump.")
            return
        if not ctx.args or ctx.args.strip().lower() == "list":
            await ctx.session.send_line(f"  {ansi.BOLD}Hyperspace Destinations:{ansi.RESET}")
            for key, loc in sorted(HYPERSPACE_LOCATIONS.items()):
                await ctx.session.send_line(f"    {loc['name']}")
            await ctx.session.send_line(f"\n  Usage: hyperspace <destination>")
            return
        dest_key = ctx.args.strip().lower()
        dest = HYPERSPACE_LOCATIONS.get(dest_key)
        if not dest:
            for k, v in HYPERSPACE_LOCATIONS.items():
                if v["name"].lower().startswith(dest_key) or k.startswith(dest_key):
                    dest = v
                    dest_key = k
                    break
        if not dest:
            await ctx.session.send_line(f"  Unknown destination: '{ctx.args}'. Type 'hyperspace list'.")
            return
        # Fuel cost: 100cr per jump (x2 for backup hyperdrive)
        hdrive = template.hyperdrive if template else 1
        fuel_cost = 100 * hdrive
        char = ctx.session.character
        credits = char.get("credits", 0)
        if credits < fuel_cost:
            await ctx.session.send_line(
                f"  Not enough credits for hyperspace fuel! "
                f"Need {fuel_cost:,}cr, have {credits:,}cr.")
            return
        # ── Astrogation skill check (through skill engine) ───────────────────
        # Navigator at sensors station grants +1D.
        # Fumble = misjump (random zone + hazard table).
        # Critical = clean jump, fuel cost halved.
        from engine.skill_checks import perform_skill_check
        from engine.character import Character, SkillRegistry, DicePool
        difficulty = 10  # Easy for known Outer Rim routes
        # Zone hazard: Maw gravity or asteroid fields raise astrogation difficulty
        try:
            from engine.npc_space_traffic import ZONES as _HYPZONES
            _hyp_zone = _HYPZONES.get(systems.get("current_zone", ""))
            if _hyp_zone and _hyp_zone.hazards.get("nav_modifier"):
                difficulty += _hyp_zone.hazards["nav_modifier"]
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        try:
            char_obj = Character.from_db_dict(char)
            sr = SkillRegistry()
            sr.load_default()
            crew = _get_crew(ship)
            # Navigator bonus: +1D if someone is at sensors station
            if crew.get("sensors"):
                import json as _jj
                _skills = _jj.loads(char.get("skills", "{}"))
                base_pool = char_obj.get_skill_pool("astrogation", sr)
                boosted = base_pool + DicePool(1, 0)
                _orig = _skills.get("astrogation")
                _skills["astrogation"] = str(boosted)
                char["skills"] = _jj.dumps(_skills)
                nav_result = perform_skill_check(char, "astrogation", difficulty, sr)
                if _orig is None:
                    _skills.pop("astrogation", None)
                else:
                    _skills["astrogation"] = _orig
                char["skills"] = _jj.dumps(_skills)
                nav_note = " [+1D navigator]"
            else:
                nav_result = perform_skill_check(char, "astrogation", difficulty, sr)
                nav_note = ""
        except Exception:
            # Graceful fallback: treat as plain success
            nav_result = None
            nav_note = ""

        # ── Fumble: misjump ───────────────────────────────────────────────────
        if nav_result is not None and nav_result.fumble:
            import random as _rnd
            from engine.starships import roll_hazard_table
            from engine.npc_space_traffic import ZONES as _TZ
            misjump_zones = [z for z in _TZ if "deep_space" in z or "orbit" in z]
            misjump_zone = _rnd.choice(misjump_zones) if misjump_zones else "tatooine_deep_space"
            # Charge full fuel for the botched jump
            char["credits"] = credits - fuel_cost
            await ctx.db.save_character(char["id"], credits=char["credits"])
            # Move ship to random zone
            get_space_grid().remove_ship(ship["id"])
            systems["current_zone"] = misjump_zone
            systems["location"] = misjump_zone.split("_")[0]
            # Fire hazard table
            hazard = roll_hazard_table(systems)
            if hazard.hull_damage:
                existing_dmg = ship.get("hull_damage", 0)
                await ctx.db.update_ship(
                    ship["id"], hull_damage=existing_dmg + hazard.hull_damage
                )
            if hazard.systems_damaged:
                for _sys_name in hazard.systems_damaged:
                    systems[_sys_name] = False
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            speed = template.speed if template else 5
            get_space_grid().add_ship(ship["id"], speed)
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_RED}[MISJUMP]{ansi.RESET} "
                f"Astrogation catastrophically failed! "
                f"(Roll: {nav_result.roll} vs {difficulty} — FUMBLE{nav_note})\n"
                f"  Hyperspace vortex tears open — the ship lurches out of control!\n"
                f"  {hazard.narrative}\n"
                f"  Reverting to realspace in unknown region: {misjump_zone}."
            )
            return

        # ── Failure: calculation aborted ──────────────────────────────────────
        if nav_result is not None and not nav_result.success:
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_RED}[NAV]{ansi.RESET} Astrogation calculation failed! "
                f"(Roll: {nav_result.roll} vs {difficulty}{nav_note}) "
                f"Cannot make the jump safely. (Fuel not consumed.)"
            )
            return

        # ── Success or graceful-drop ──────────────────────────────────────────
        # Critical: halve fuel cost
        if nav_result is not None and nav_result.critical_success:
            fuel_cost = max(50, fuel_cost // 2)
        roll_str = f"Roll: {nav_result.roll} vs {difficulty}{nav_note}" if nav_result else "auto"
        crit_note = " (critical — efficient jump!)" if (
            nav_result and nav_result.critical_success) else ""

        # Charge fuel
        char["credits"] = credits - fuel_cost
        await ctx.db.save_character(char["id"], credits=char["credits"])

        # ── Travel time: ticks = hyperdrive_multiplier × 3, clamped 2–12 ──────
        # x1 drive = 3 ticks (~30s), x2 = 6 ticks (~60s), x1/2 = 2 ticks
        hdrive_mult = template.hyperdrive if template and template.hyperdrive else 1
        travel_ticks = max(2, min(12, hdrive_mult * 3))
        if nav_result is not None and nav_result.critical_success:
            travel_ticks = max(2, travel_ticks - 1)  # critical = slightly faster

        # Remove from space grid during transit
        get_space_grid().remove_ship(ship["id"])

        # ── Clean up NPC combat targeting this ship (session 38 fix) ──
        try:
            from engine.npc_space_combat_ai import get_npc_combat_manager
            from engine.space_encounters import get_encounter_manager
            combat_mgr = get_npc_combat_manager()
            enc_mgr = get_encounter_manager()
            # Remove any NPC combatant targeting this ship
            c = combat_mgr.get_combatant_targeting(ship["id"])
            if c:
                get_space_grid().remove_ship(c.npc_ship_id)
                combat_mgr.remove_combatant(c.npc_ship_id)
                await ctx.session_mgr.broadcast_to_room(
                    ship["bridge_room_id"],
                    f"  \033[2m[SENSORS] {c.display_name} breaks off pursuit "
                    f"as you enter hyperspace.\033[0m"
                )
                # Reset the traffic ship state too
                try:
                    from engine.npc_space_traffic import get_traffic_manager, TrafficState
                    ts = get_traffic_manager().get_ship(c.npc_ship_id)
                    if ts:
                        ts.tailing_ship_id = None
                        ts.hail_sent = False
                        ts.enter_state(TrafficState.IDLE, duration=0)
                except Exception:
                    log.debug("hyperspace npc combat cleanup: traffic reset failed",
                              exc_info=True)
            # Resolve any active encounter for this ship
            enc = enc_mgr.get_encounter(ship["id"])
            if enc and enc.state == "active":
                enc_mgr.resolve(enc, outcome="player_fled_hyperspace")
        except Exception:
            log.warning("hyperspace NPC combat/encounter cleanup failed",
                        exc_info=True)

        # ── Sever boarding link if active ──
        try:
            from engine.boarding import get_boarding_link_info, sever_boarding_link
            if get_boarding_link_info(ship):
                ok, msg = await sever_boarding_link(
                    ship, ctx.db, ctx.session_mgr, reason="hyperspace")
                if ok:
                    await ctx.session_mgr.broadcast_to_room(
                        ship["bridge_room_id"],
                        f"  {msg}",
                    )
        except Exception:
            log.warning("hyperspace boarding link cleanup failed", exc_info=True)

        # Mark ship in hyperspace transit
        systems["in_hyperspace"] = True
        systems["hyperspace_dest"] = dest_key
        systems["hyperspace_dest_name"] = dest["name"]
        systems["hyperspace_ticks_remaining"] = travel_ticks
        systems["hyperspace_ticks_total"] = travel_ticks  # for HUD pct
        systems["hyperspace_roll_str"] = roll_str + crit_note
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))

        eta_secs = travel_ticks * 10
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[HYPERSPACE]{ansi.RESET} "
            f"Astrogation plotted. ({roll_str}){crit_note}\n"
            f"  Stars stretch into lines as the {ship['name']} jumps to lightspeed!\n"
            f"  Destination: {dest['name']} — ETA ~{eta_secs}s."
        )
        # Spacer quest: hyperspace jump initiated
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(ctx.session, ctx.db, "space_action", action="hyperspace")
        except Exception as _e:
            log.debug("silent except in parser/space_commands.py:3634: %s", _e, exc_info=True)


class BuyCommand(BaseCommand):
    key = "buy"
    aliases = ["purchase"]
    help_text = "Buy a weapon or item from a shop."
    usage = "buy <weapon name>"
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: buy <weapon name>  or  buy cargo <good> <tons>")
            await ctx.session.send_line("  Type 'weapons' for weapons, 'market' for trade goods.")
            return
        # Route cargo purchases to trade handler
        if ctx.args.strip().lower().startswith("cargo "):
            return await _handle_buy_cargo(ctx)

        # ── Route 'buy <item> from <shop name>' to vendor droid ──
        arg_lower = ctx.args.strip().lower()
        if " from " in arg_lower:
            idx = arg_lower.index(" from ")
            item_part = ctx.args.strip()[:idx].strip()
            shop_part = ctx.args.strip()[idx + 6:].strip()
            if shop_part:
                return await _handle_buy_from_droid(ctx, item_part, shop_part)

        from engine.weapons import get_weapon_registry
        from engine.items import ItemInstance, serialize_equipment
        wr = get_weapon_registry()
        weapon = wr.find_by_name(ctx.args.strip())
        if not weapon:
            await ctx.session.send_line(f"  Unknown item: '{ctx.args}'. Type 'weapons' to see the list.")
            return
        if weapon.is_armor:
            await ctx.session.send_line("  Armor purchases coming soon.")
            return
        base_price = weapon.cost
        if base_price <= 0:
            base_price = 500
        char = ctx.session.character

        # ── Bargain haggle: player vs vendor ──
        npc_dice, npc_pips = 3, 0  # Default generic vendor: 3D Bargain
        try:
            import json as _json
            npcs = await ctx.db.get_npcs_in_room(char["room_id"])
            for npc in npcs:
                sheet = _json.loads(npc.get("char_sheet_json", "{}"))
                npc_skills = sheet.get("skills", {})
                bargain_str = npc_skills.get("bargain", "")
                if bargain_str:
                    from engine.skill_checks import _parse_dice_str
                    npc_dice, npc_pips = _parse_dice_str(bargain_str)
                    break  # Use first vendor NPC with Bargain skill
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        from engine.skill_checks import resolve_bargain_check
        haggle = resolve_bargain_check(
            char, base_price,
            npc_bargain_dice=npc_dice, npc_bargain_pips=npc_pips,
            is_buying=True,
        )
        price = haggle["adjusted_price"]

        # ── Faction rep discount/markup (Drop 4) ──
        faction_msg = ""
        try:
            import json as _json2
            # Detect shop NPC's faction
            npcs2 = await ctx.db.get_npcs_in_room(char["room_id"])
            vendor_faction = ""
            for npc2 in npcs2:
                ai_cfg = npc2.get("ai_config_json", "{}")
                if isinstance(ai_cfg, str):
                    ai_cfg = _json2.loads(ai_cfg) if ai_cfg else {}
                npc_fac = (ai_cfg.get("faction", "") or "").lower()
                # Map faction names to codes
                fac_map = {
                    "imperial": "empire", "empire": "empire",
                    "galactic empire": "empire",
                    "rebel": "rebel", "rebel alliance": "rebel",
                    "hutt": "hutt", "hutt cartel": "hutt",
                    "bounty hunter": "bh_guild", "bounty hunters": "bh_guild",
                    "bounty hunters' guild": "bh_guild",
                }
                vendor_faction = fac_map.get(npc_fac, "")
                if vendor_faction:
                    break

            if vendor_faction:
                from engine.organizations import get_faction_shop_modifier
                allowed, mod, tier_name = await get_faction_shop_modifier(
                    char, vendor_faction, ctx.db)
                if not allowed:
                    await ctx.session.send_line(
                        f"  \033[1;31mThe vendor refuses to serve you.\033[0m "
                        f"Your standing with this faction is {tier_name}. "
                        f"Improve your reputation before shopping here."
                    )
                    return
                if mod != 0.0:
                    faction_adj = int(price * mod)
                    price = max(1, price + faction_adj)
                    if mod < 0:
                        faction_msg = (
                            f"\n  \033[2m[{tier_name} standing: "
                            f"{abs(int(mod*100))}% faction discount]\033[0m"
                        )
                    else:
                        faction_msg = (
                            f"\n  \033[0;31m[{tier_name} standing: "
                            f"+{int(mod*100)}% price markup]\033[0m"
                        )
        except Exception:
            log.warning("execute: faction shop modifier failed", exc_info=True)

        current_credits = char.get("credits", 1000)
        if current_credits < price:
            await ctx.session.send_line(
                f"  Not enough credits! {weapon.name} costs {price:,} credits "
                f"(base {base_price:,}), you have {current_credits:,}.")
            return
        new_credits = current_credits - price
        item = ItemInstance.new_from_vendor(weapon.key)
        char["credits"] = new_credits
        char["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(char["id"], credits=new_credits, equipment=char["equipment"])

        # Show haggle result
        pct = haggle["price_modifier_pct"]
        if pct != 0:
            direction = "discount" if pct < 0 else "markup"
            await ctx.session.send_line(
                f"  {ansi.DIM}Bargain {haggle['player_pool']}:"
                f" {haggle['player_roll']} vs vendor {haggle['npc_pool']}:"
                f" {haggle['npc_roll']}"
                f" → {abs(pct)}% {direction}{ansi.RESET}")
        await ctx.session.send_line(haggle["message"])
        await ctx.session.send_line(
            ansi.success(
                f"  Purchased and equipped {weapon.name} for {price:,} credits. "
                f"({new_credits:,} remaining)")
        )
        if faction_msg:
            await ctx.session.send_line(faction_msg)
        await ctx.session.send_line(f"  Condition: {item.condition_bar}")


class DamConCommand(BaseCommand):
    key = "damcon"
    aliases = ["damagecontrol", "repair"]
    help_text = (
        "Attempt to repair a damaged ship system mid-combat. "
        "Uses Technical + repair skill. Systems: "
        "shields, sensors, engines, weapons, hyperdrive, hull."
    )
    usage = "damcon <system>"

    async def execute(self, ctx):
        # ── Validate: aboard a ship ──
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return

        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return

        systems = _get_systems(ship)

        # ── No argument: show damage report ──
        if not ctx.args:
            damaged = []
            for sys_name in REPAIRABLE_SYSTEMS:
                state = get_system_state(systems, sys_name)
                if state == "damaged":
                    diff = REPAIR_DIFFICULTIES[sys_name]
                    damaged.append(
                        f"    {ansi.BRIGHT_YELLOW}{sys_name:12s}{ansi.RESET} "
                        f"DAMAGED  (Difficulty: {diff})"
                    )
                elif state == "destroyed":
                    damaged.append(
                        f"    {ansi.BRIGHT_RED}{sys_name:12s}{ansi.RESET} "
                        f"DESTROYED -- needs spacedock"
                    )
            hull_dmg = ship.get("hull_damage", 0)
            if hull_dmg > 0:
                diff = REPAIR_DIFFICULTIES["hull"]
                damaged.append(
                    f"    {ansi.BRIGHT_YELLOW}{'hull':12s}{ansi.RESET} "
                    f"{hull_dmg} damage  (Difficulty: {diff})"
                )
            if not damaged:
                await ctx.session.send_line(
                    "  All systems operational. Nothing to repair."
                )
            else:
                await ctx.session.send_line(
                    f"  {ansi.BOLD}Damage Report:{ansi.RESET}"
                )
                for line in damaged:
                    await ctx.session.send_line(line)
                await ctx.session.send_line(
                    f"\n  {ansi.DIM}Usage: damcon <system> to attempt repair{ansi.RESET}"
                )
            return

        # ── Parse system name ──
        target_sys = ctx.args.strip().lower()
        # Allow partial matching
        matched = None
        for sys_name in REPAIRABLE_SYSTEMS:
            if sys_name == target_sys or sys_name.startswith(target_sys):
                matched = sys_name
                break
        if not matched:
            await ctx.session.send_line(
                f"  Unknown system '{ctx.args}'. "
                f"Options: {', '.join(REPAIRABLE_SYSTEMS)}"
            )
            return

        # ── Check system state ──
        if matched == "hull":
            hull_dmg = ship.get("hull_damage", 0)
            if hull_dmg <= 0:
                await ctx.session.send_line("  Hull integrity is fine.")
                return
            current_state = "damaged"
        else:
            current_state = get_system_state(systems, matched)

        if current_state == "working":
            await ctx.session.send_line(
                f"  {matched.title()} are already operational!"
            )
            return

        if current_state == "destroyed":
            await ctx.session.send_line(
                f"  {matched.title()} are damaged beyond repair. "
                f"You'll need a spacedock for this."
            )
            return

        # ── Look up repair skill ──
        if matched == "weapons":
            skill_name = get_weapon_repair_skill(template.scale)
        else:
            skill_name = get_repair_skill_name(template.scale)
        # Normalise underscores for skill lookup
        skill_name = skill_name.replace("_", " ")

        # Difficulty: base + combat penalty
        from engine.starships import REPAIR_DIFFICULTIES as _RD
        base_diff = _RD.get(matched, 20)
        in_combat = not ship["docked_at"]
        effective_diff = base_diff + (5 if in_combat else 0)

        # ── Resolve via centralised skill check engine ──
        from engine.skill_checks import resolve_repair_check
        result = resolve_repair_check(
            ctx.session.character,
            skill_name,
            effective_diff,
            is_hull=(matched == "hull"),
        )

        # ── Apply results to database ──
        if result["success"]:
            if matched == "hull":
                new_dmg = max(0, ship.get("hull_damage", 0) - result["hull_repaired"])
                await ctx.db.update_ship(ship["id"], hull_damage=new_dmg)
            else:
                systems[matched] = True
                await ctx.db.update_ship(
                    ship["id"], systems=json.dumps(systems)
                )
        elif result["catastrophic"]:
            systems[matched] = "destroyed"
            await ctx.db.update_ship(
                ship["id"], systems=json.dumps(systems)
            )

        # ── Broadcast result ──
        if result["success"]:
            color = ansi.BRIGHT_GREEN
            tag = "REPAIR"
        elif result["catastrophic"]:
            color = ansi.BRIGHT_RED
            tag = "REPAIR CRITICAL"
        elif result["partial"]:
            color = ansi.BRIGHT_CYAN
            tag = "REPAIR"
        else:
            color = ansi.BRIGHT_YELLOW
            tag = "REPAIR"

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {color}[{tag}]{ansi.RESET} "
            f"{ctx.session.character['name']} works on {matched}: "
            f"{result['message'].strip()}"
        )
        # From Dust to Stars: damcon hook (Step 19)
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(ctx.session, ctx.db, "use_command", command="damcon")
        except Exception:
            pass  # graceful-drop


class PayCommand(BaseCommand):
    key = "pay"
    aliases = []
    help_text = "Pay a pirate's credit demand to make them stand down."
    usage = "pay <ship name>"
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: pay <ship name>")
            return
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  You're docked — no one is demanding anything.")
            return
        systems = _get_systems(ship)
        zone_id = systems.get("current_zone", "")
        if not zone_id:
            await ctx.session.send_line("  Cannot determine your zone.")
            return
        target_name = ctx.args.strip()
        char = ctx.session.character
        success, msg = await get_traffic_manager().handle_pirate_payment(
            player_session=ctx.session,
            player_char=char,
            target_name=target_name,
            zone_id=zone_id,
            db=ctx.db,
            session_mgr=ctx.session_mgr,
        )
        color = ansi.BRIGHT_GREEN if success else ansi.BRIGHT_RED
        await ctx.session.send_line(f"  {color}{msg}{ansi.RESET}")
        if success:
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_YELLOW}[CREW]{ansi.RESET} "
                f"{char['name']} transfers credits to the pirates.",
                exclude=ctx.session,
            )


class HailCommand(BaseCommand):
    key = "hail"
    aliases = []
    help_text = (
        "Broadcast a hail to all ships in your zone. "
        "Use 'comms <ship> <message>' to reply to a specific ship."
    )
    usage = "hail"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Comms work in space. Launch first.")
            return
        systems = _get_systems(ship)
        zone_id = systems.get("current_zone", "")
        if not zone_id:
            await ctx.session.send_line("  Cannot determine your zone. Try launching again.")
            return
        # Announce the hail to the bridge
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[COMMS OUT]{ansi.RESET} "
            f"{ship['name']} broadcasts: \"Any ships in the area, please respond.\""
        )
        # Let traffic manager handle NPC replies
        replied = await get_traffic_manager().handle_player_hail(
            player_session=ctx.session,
            player_ship_name=ship["name"],
            zone_id=zone_id,
            db=ctx.db,
            session_mgr=ctx.session_mgr,
        )
        if not replied:
            await ctx.session.send_line(
                f"  {ansi.DIM}[COMMS] No reply on open frequencies.{ansi.RESET}"
            )


class CommsCommand(BaseCommand):
    key = "comms"
    aliases = ["comm", "radio"]
    help_text = (
        "Send a comms message to a specific ship. "
        "Usage: comms <ship name> <message>"
    )
    usage = "comms <ship name> <message>"
    async def execute(self, ctx):
        if not ctx.args or " " not in ctx.args.strip():
            await ctx.session.send_line(
                "  Usage: comms <ship name> <message>\n"
                "  Example: comms 'Starlight Wanderer' We mean no harm.\n"
                "  Tip: use 'hail' to broadcast to all ships in your zone."
            )
            return
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Comms work in space. Launch first.")
            return
        systems = _get_systems(ship)
        zone_id = systems.get("current_zone", "")
        if not zone_id:
            await ctx.session.send_line("  Cannot determine your zone. Try launching again.")
            return
        # Split first token (target) from rest (message)
        parts = ctx.args.strip().split(None, 1)
        target_name = parts[0]
        message = parts[1] if len(parts) > 1 else ""
        if not message:
            await ctx.session.send_line("  Usage: comms <ship name> <message>")
            return
        # Echo outgoing to bridge
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[COMMS OUT]{ansi.RESET} "
            f"{ship['name']} → {target_name}: \"{message}\""
        )
        # Try NPC traffic ship first
        handled = await get_traffic_manager().handle_player_comms(
            player_session=ctx.session,
            player_ship_name=ship["name"],
            target_name=target_name,
            message=message,
            zone_id=zone_id,
            db=ctx.db,
            session_mgr=ctx.session_mgr,
        )
        if not handled:
            # Check if target is a player ship in space
            all_ships = await ctx.db.get_ships_in_space()
            target_ship = None
            tname_lower = target_name.lower()
            for s in all_ships:
                if s["id"] != ship["id"] and (
                    s["name"].lower() == tname_lower
                    or s["name"].lower().startswith(tname_lower)
                ):
                    target_ship = s
                    break
            if target_ship and target_ship.get("bridge_room_id"):
                await ctx.session_mgr.broadcast_to_room(
                    target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_CYAN}[COMMS]{ansi.RESET} "
                    f"{ship['name']}: \"{message}\""
                )
                await ctx.session.send_line(
                    f"  {ansi.DIM}[COMMS] Message transmitted to {target_ship['name']}.{ansi.RESET}"
                )
            else:
                await ctx.session.send_line(
                    f"  {ansi.DIM}[COMMS] No response from '{target_name}'. "
                    f"Check ship name or use 'hail' to broadcast.{ansi.RESET}"
                )


class CreditsCommand(BaseCommand):
    key = "+credits"
    aliases = ["credits", "balance", "wallet", "+wallet"]
    help_text = "Check your credit balance."
    usage = "credits"
    async def execute(self, ctx):
        credits = ctx.session.character.get("credits", 1000)
        await ctx.session.send_line(f"  Credits: {credits:,}")


class SetBountyCommand(BaseCommand):
    key = "@setbounty"
    aliases = ["@bounty"]
    help_text = (
        "Admin: set a bounty on a character and spawn a bounty hunter. "
        "Usage: @setbounty <character name>"
    )
    usage = "@setbounty <character name>"
    access_level = AccessLevel.ADMIN

    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: @setbounty <character name>")
            return
        target_name = ctx.args.strip()
        target = await ctx.db.get_character_by_name(target_name)
        if not target:
            await ctx.session.send_line(f"  No active character named '{target_name}' found.")
            return
        # Set bounty flag (integer column added in schema v3)
        try:
            await ctx.db.set_character_bounty(target["id"], 1)
        except Exception as e:
            await ctx.session.send_line(f"  DB error setting bounty: {e}")
            return
        await ctx.session.send_line(
            ansi.success(f"  Bounty set on {target['name']} (id={target['id']}).")
        )
        # Spawn the hunter
        ts = await get_traffic_manager().spawn_bounty_hunter(
            char_id=target["id"],
            db=ctx.db,
            session_mgr=ctx.session_mgr,
            target_name=target["name"],
        )
        if ts:
            await ctx.session.send_line(
                ansi.success(f"  Bounty hunter '{ts.display_name}' spawned.")
            )
        else:
            await ctx.session.send_line(
                "  Hunter on cooldown or spawn failed — will retry automatically."
            )


class ResistTractorCommand(BaseCommand):
    key = "resist"
    aliases = ["breakfree"]
    help_text = (
        "Attempt to break free of a tractor beam (pilot only).\n"
        "Rolls your ship's hull vs the tractor beam's strength.\n"
        "Success breaks free. Failure reels you in and may damage drives.\n"
        "\n"
        "EXAMPLES:\n"
        "  resist    -- contest the tractor beam holding you"
    )
    usage = "resist"

    async def execute(self, ctx):
        from engine.starships import resolve_tractor_resist
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  You're docked, not in a tractor beam.")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can resist a tractor beam.")
            return
        systems = _get_systems(ship)
        held_by = systems.get("tractor_held_by", 0)
        if not held_by:
            await ctx.session.send_line("  You're not caught in a tractor beam.")
            return
        # Get the holding ship's tractor weapon stats
        holder_ship = await ctx.db.get_ship(held_by)
        if not holder_ship:
            # Holder gone — auto-free
            systems["tractor_held_by"] = 0
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            await ctx.session.send_line("  The tractor beam source is gone. You're free!")
            return
        reg = get_ship_registry()
        holder_template = reg.get(holder_ship["template"])
        ship_template = reg.get(ship["template"])
        if not holder_template or not ship_template:
            await ctx.session.send_line("  Data error.")
            return
        # Find the tractor weapon on the holder
        tractor_weapon = None
        for w in holder_template.weapons:
            if w.tractor:
                tractor_weapon = w
                break
        if not tractor_weapon:
            systems["tractor_held_by"] = 0
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            await ctx.session.send_line("  Holder has no tractor beam. You're free!")
            return
        result = resolve_tractor_resist(
            tractor_damage=DicePool.parse(tractor_weapon.damage),
            target_hull=DicePool.parse(ship_template.hull),
            attacker_scale=holder_template.scale_value,
            target_scale=ship_template.scale_value,
        )
        if result.broke_free:
            systems["tractor_held_by"] = 0
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            # Clear holder's tractor_holding
            h_systems = _get_systems(holder_ship)
            if h_systems.get("tractor_holding") == ship["id"]:
                h_systems["tractor_holding"] = 0
                await ctx.db.update_ship(holder_ship["id"],
                                         systems=json.dumps(h_systems))
            # Sever boarding link if active on either ship
            try:
                from engine.boarding import get_boarding_link_info, sever_boarding_link
                if get_boarding_link_info(ship):
                    await sever_boarding_link(
                        ship, ctx.db, ctx.session_mgr, reason="tractor_release")
                elif get_boarding_link_info(holder_ship):
                    await sever_boarding_link(
                        holder_ship, ctx.db, ctx.session_mgr, reason="tractor_release")
            except Exception:
                log.warning("resist tractor: boarding link sever failed", exc_info=True)
        else:
            if result.drive_damage > 0:
                systems["drive_penalty"] = systems.get("drive_penalty", 0) + result.drive_damage
                await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[TRACTOR]{ansi.RESET} "
            f"{ctx.session.character['name']} attempts to break free! "
            f"{result.narrative.strip()}")
        if holder_ship.get("bridge_room_id"):
            if result.broke_free:
                await ctx.session_mgr.broadcast_to_room(holder_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_YELLOW}[TRACTOR]{ansi.RESET} "
                    f"{ship['name']} breaks free of the tractor beam!")
            else:
                await ctx.session_mgr.broadcast_to_room(holder_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_CYAN}[TRACTOR]{ansi.RESET} "
                    f"{ship['name']} struggles but remains captured. "
                    f"{result.narrative.strip()}")




class OrderCommand(BaseCommand):
    """Issue a tactical order as Commander. Requires Command skill check (diff 8).

    Usage:
      order               -- show current order and available orders
      order <number>      -- issue order by number (1-8)
      order cancel        -- cancel current order
    """
    key = "order"
    aliases = ["orders"]
    help_text = "Issue a tactical order (Commander station required)."
    usage = "order [<number> | cancel]"

    async def execute(self, ctx: CommandContext) -> None:
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship.get("docked_at"):
            await ctx.session.send_line("  Cannot issue orders while docked.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("commander") != char_id:
            await ctx.session.send_line(
                "  Only the Commander can issue tactical orders. "
                "Take the commander station first ('commander')."
            )
            return

        from engine.starships import ORDER_DEFINITIONS, ORDER_LIST, get_active_order
        systems = _get_systems(ship)
        active  = get_active_order(systems)
        args    = (ctx.args or "").strip().lower()

        # ── Show status ──────────────────────────────────────────────────────
        if not args:
            if active:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_CYAN}[COMMAND]{ansi.RESET} "
                    f"Active: {ansi.BRIGHT_WHITE}{active['name']}{ansi.RESET}  "
                    f"| {active['bonus']}  | Cost: {active['tradeoff']}"
                )
            else:
                await ctx.session.send_line(
                    f"  {ansi.DIM}No tactical order active.{ansi.RESET}"
                )
            await ctx.session.send_line("")
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_WHITE}Available orders:{ansi.RESET}"
            )
            for o in ORDER_LIST:
                marker = (
                    f" {ansi.BRIGHT_GREEN}[ACTIVE]{ansi.RESET}"
                    if active and active["number"] == o["number"] else ""
                )
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_CYAN}{o['number']}.{ansi.RESET} "
                    f"{ansi.BRIGHT_WHITE}{o['name']:<22}{ansi.RESET}"
                    f"  {o['bonus']:<40}  Cost: {o['tradeoff']}{marker}"
                )
            await ctx.session.send_line(
                f"\n  {ansi.DIM}Use 'order <number>' to issue, "
                f"'order cancel' to stand down.{ansi.RESET}"
            )
            return

        # ── Cancel ───────────────────────────────────────────────────────────
        if args == "cancel":
            if not active:
                await ctx.session.send_line("  No order is active.")
                return
            systems.pop("active_order", None)
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_YELLOW}[COMMAND]{ansi.RESET} "
                f"{ctx.session.character['name']} stands down: {active['name']}."
            )
            return

        # ── Issue by number ──────────────────────────────────────────────────
        if not args.isdigit():
            await ctx.session.send_line(
                "  Usage: order <number>  (1-8)  or  order cancel"
            )
            return

        order_num = int(args)
        target = next((o for o in ORDER_LIST if o["number"] == order_num), None)
        if not target:
            await ctx.session.send_line(
                f"  Unknown order '{order_num}'. Type 'order' to see the list."
            )
            return

        # Command skill check (Easy difficulty 8)
        from engine.skill_checks import perform_skill_check
        from engine.character import SkillRegistry
        sr = SkillRegistry()
        sr.load_default()
        result = perform_skill_check(ctx.session.character, "command", 8, sr)

        if result.fumble:
            import random as _rnd
            chaos = _rnd.choice(ORDER_LIST)
            systems["active_order"] = next(
                k for k, v in ORDER_DEFINITIONS.items()
                if v["number"] == chaos["number"]
            )
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_RED}[COMMAND]{ansi.RESET} "
                f"Order backfires! Crew scrambles to execute: {chaos['name']}! "
                f"(roll: {result.roll} vs 8 — fumble)"
            )
            return

        if not result.success:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[COMMAND]{ansi.RESET} "
                f"Crew hesitates — order not acknowledged. "
                f"(roll: {result.roll} vs 8) Try again."
            )
            return

        # Success
        order_key = next(
            k for k, v in ORDER_DEFINITIONS.items() if v["number"] == order_num
        )
        systems["active_order"] = order_key
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
        crit = " (critical!)" if result.critical_success else ""
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_GREEN}[COMMAND]{ansi.RESET} "
            f"{ctx.session.character['name']}: {target['name'].upper()}{crit}! "
            f"{target['bonus']}. Cost: {target['tradeoff']}."
        )


class PowerCommand(BaseCommand):
    """
    Manage reactor power allocation. Engineer station required.

    Usage:
      power                    -- show current allocation and budget
      power engines <n>        -- set engines power (0-6)
      power shields <n>        -- set shields power (0-6)
      power weapons <n>        -- set weapons power (0-6)
      power sensors <n>        -- set sensors power (0-4)
      power life_support <n>   -- set life support power (0-2)
      power combat             -- preset: standard combat allocation
      power silent             -- preset: silent running (stealth mode)
      power emergency          -- preset: engines + shields, weapons offline
    """
    key = "power"
    aliases = ["pwr"]
    help_text = "Manage reactor power allocation. Engineer station required."
    usage = "power [system <n> | combat | silent | emergency]"

    async def execute(self, ctx: CommandContext) -> None:
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship.get("docked_at"):
            await ctx.session.send_line("  Power management unavailable while docked.")
            return

        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]

        # Engineer gate
        if crew.get("engineer") != char_id:
            await ctx.session.send_line(
                f"  {ansi.DIM}No one at the engineering console. "
                f"Take the engineer station first ('engineer').{ansi.RESET}"
                if not crew.get("engineer") else
                f"  Only the engineer can manage power allocation."
            )
            return

        from engine.starships import (
            get_ship_registry, POWER_DEFAULTS, POWER_PRESETS,
            get_power_state, get_power_budget_used, is_silent_running,
        )
        reg = get_ship_registry()
        tmpl = reg.get(ship.get("template", ""))
        if not tmpl:
            await ctx.session.send_line("  Ship data error.")
            return

        systems = _get_systems(ship)
        reactor_max = tmpl.reactor_power

        args = (ctx.args or "").strip().lower().split()

        # ── Show current allocation ──────────────────────────────────────────
        if not args:
            ps = get_power_state(systems)
            used = get_power_budget_used(ps)
            remaining = reactor_max - used
            silent = is_silent_running(systems)
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}[ENGINEERING]{ansi.RESET} "
                f"Reactor: {used}/{reactor_max} power"
                + (f"  {ansi.BRIGHT_YELLOW}[SILENT RUNNING]{ansi.RESET}" if silent else "")
            )
            await ctx.session.send_line("")
            sys_order = ["engines", "shields", "weapons", "sensors", "life_support"]
            sys_labels = {
                "engines":      "Engines      ",
                "shields":      "Shields      ",
                "weapons":      "Weapons      ",
                "sensors":      "Sensors      ",
                "life_support": "Life Support ",
            }
            overcharge_notes = {
                "engines": "+1 speed/pt",
                "shields": "+1 pip/pt",
                "weapons": "+1 pip FC/pt",
                "sensors": "+1D scan/pt",
            }
            for s in sys_order:
                cur  = ps[s]
                dflt = POWER_DEFAULTS[s]
                note = ""
                if cur > dflt:
                    note = f"  {ansi.BRIGHT_GREEN}+{cur-dflt} overcharge ({overcharge_notes.get(s,'')}){ansi.RESET}"
                elif cur == 0 and dflt > 0:
                    note = f"  {ansi.RED}OFFLINE{ansi.RESET}"
                bar = "█" * cur + "░" * max(0, dflt - cur)
                color = ansi.BRIGHT_GREEN if cur > dflt else (ansi.RED if cur == 0 and dflt > 0 else ansi.DIM)
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_WHITE}{sys_labels[s]}{ansi.RESET}"
                    f"  {color}{bar}{ansi.RESET}  {cur} pw{note}"
                )
            await ctx.session.send_line("")
            await ctx.session.send_line(
                f"  {ansi.DIM}Budget: {remaining} power free. "
                f"Presets: power combat | power silent | power emergency{ansi.RESET}"
            )
            return

        # ── Presets ──────────────────────────────────────────────────────────
        preset_name = args[0]
        if preset_name in POWER_PRESETS:
            preset = POWER_PRESETS[preset_name]
            total = sum(preset.values())
            if total > reactor_max:
                await ctx.session.send_line(
                    f"  Preset '{preset_name}' requires {total} power "
                    f"but reactor capacity is {reactor_max}."
                )
                return
            systems["power_allocation"] = preset
            await ctx.db.update_ship(ship["id"], systems=import_json().dumps(systems))
            if preset_name == "silent":
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_CYAN}[ENGINEERING]{ansi.RESET} "
                    f"Silent running engaged. Engines at drift speed, shields and weapons offline. "
                    f"Sensor detection difficulty +9."
                )
            elif preset_name == "emergency":
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_YELLOW}[ENGINEERING]{ansi.RESET} "
                    f"Emergency power: engines and shields at maximum. Weapons offline."
                )
            else:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_GREEN}[ENGINEERING]{ansi.RESET} "
                    f"Standard combat allocation restored."
                )
            await _broadcast_space_state_for_ship(ship, ctx.db, ctx.session_mgr)
            return

        # ── Set individual system ─────────────────────────────────────────────
        if len(args) < 2 or not args[1].isdigit():
            await ctx.session.send_line(
                "  Usage: power <s> <value>  or  power <preset>\n"
                "  Systems: engines shields weapons sensors life_support\n"
                "  Presets: combat silent emergency"
            )
            return

        sys_name = args[0]
        if sys_name not in POWER_DEFAULTS:
            await ctx.session.send_line(
                f"  Unknown system '{sys_name}'. "
                f"Valid: engines shields weapons sensors life_support"
            )
            return

        new_val = int(args[1])
        if new_val < 0 or new_val > 8:
            await ctx.session.send_line("  Power value must be 0–8.")
            return

        ps = get_power_state(systems)
        ps[sys_name] = new_val
        new_total = get_power_budget_used(ps)
        if new_total > reactor_max:
            over = new_total - reactor_max
            await ctx.session.send_line(
                f"  Over budget by {over} power (reactor max: {reactor_max}). "
                f"Reduce another system first."
            )
            return

        systems["power_allocation"] = ps
        await ctx.db.update_ship(ship["id"], systems=import_json().dumps(systems))

        dflt = POWER_DEFAULTS[sys_name]
        if new_val == 0 and dflt > 0:
            note = f"{ansi.RED}OFFLINE{ansi.RESET}"
        elif new_val > dflt:
            note = f"{ansi.BRIGHT_GREEN}overcharge +{new_val - dflt}{ansi.RESET}"
        else:
            note = "nominal"
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_CYAN}[ENGINEERING]{ansi.RESET} "
            f"{sys_name.replace('_', ' ').title()} set to {new_val} power. "
            f"Status: {note}. Budget used: {new_total}/{reactor_max}."
        )
        await _broadcast_space_state_for_ship(ship, ctx.db, ctx.session_mgr)


def import_json():
    import json
    return json


async def _broadcast_space_state_for_ship(ship, db, session_mgr):
    """Re-broadcast space state after power change so HUD updates immediately."""
    try:
        from parser.space_commands import broadcast_space_state
        await broadcast_space_state(ship, db, session_mgr)
    except Exception:
        log.warning("_broadcast_space_state_for_ship: unhandled exception", exc_info=True)
        pass


# ── Transponder Codes & Customs (Drop 18) ───────────────────────────────────

# Infraction classes (Platt's Smugglers Guide p.42-43)
_INFRACTION_CLASSES = {
    5: {"name": "Class Five",  "desc": "Safety violation / expired permit",  "fine": (100, 500),    "arrest_chance": 0.0},
    4: {"name": "Class Four",  "desc": "Minor contraband / unlicensed goods","fine": (1000, 5000),  "arrest_chance": 0.05},
    3: {"name": "Class Three", "desc": "Weapons trafficking / restricted",   "fine": (2500, 5000),  "arrest_chance": 0.20},
    2: {"name": "Class Two",   "desc": "False transponder / stolen ship",    "fine": (5000, 10000), "arrest_chance": 0.40},
    1: {"name": "Class One",   "desc": "Espionage / capital crime",          "fine": (0, 0),        "arrest_chance": 1.0},
}

_IMPERIAL_CUSTOMS_PLANETS = {"tatooine", "corellia"}


async def _run_customs_check(ctx, ship, planet: str) -> None:
    """
    Imperial customs inspection on landing at Tatooine or Corellia.
    Checks for:
      - Active smuggling run cargo -> Class 3-4
      - False transponder -> Class 2
      - Sensor mask mod -> suspicious, Con check to avoid deeper scan
    Fine modified by Bargain/Con check (bribery opportunity).
    Graceful-drop: never prevents landing.
    """
    import random as _r
    try:
        char = ctx.session.character
        systems = _get_systems(ship)
        reg = get_ship_registry()
        tmpl = reg.get(ship.get("template", ""))

        # Base customs roll: Perception 3D for customs officer
        from engine.skill_checks import perform_skill_check
        from engine.character import SkillRegistry
        sr = SkillRegistry()
        sr.load_default()

        infraction_class = None
        infraction_reason = ""

        # Check false transponder
        false_tp = systems.get("false_transponder")
        if false_tp:
            # Con check vs customs officer Perception (3D = diff 10)
            con_result = perform_skill_check(char, "con", 10, sr)
            if not con_result.success:
                infraction_class = 2
                infraction_reason = f"False transponder detected ({false_tp['alias']})"
            elif con_result.critical_success:
                await ctx.session.send_line(
                    f"  {ansi.DIM}[CUSTOMS] Credentials checked... cleared. "
                    f"(Critical con roll){ansi.RESET}"
                )
                return
            else:
                await ctx.session.send_line(
                    f"  {ansi.DIM}[CUSTOMS] Credentials checked... cleared.{ansi.RESET}"
                )

        # Check active smuggling run with cargo
        if infraction_class is None:
            try:
                from engine.smuggling import get_smuggling_board
                board = get_smuggling_board()
                job = board.get_active_job(str(char["id"]))
                if job and job.destination_planet:
                    # Customs sniffs the cargo
                    sniff = perform_skill_check(char, "con", 12, sr)
                    if not sniff.success:
                        infraction_class = 3 if job.cargo_tier >= 2 else 4
                        infraction_reason = f"Suspicious cargo: {job.cargo_type}"
            except Exception:
                log.warning("_run_customs_check: unhandled exception", exc_info=True)
                pass

        if infraction_class is None:
            # Routine check — passed
            if _r.random() < 0.3:
                await ctx.session.send_line(
                    f"  {ansi.DIM}[CUSTOMS] Routine inspection. Papers in order.{ansi.RESET}"
                )
            return

        # ── Infraction detected ──────────────────────────────────────────────
        inf = _INFRACTION_CLASSES[infraction_class]
        fine_lo, fine_hi = inf["fine"]
        base_fine = _r.randint(fine_lo, fine_hi)

        await ctx.session.send_line(
            f"  {ansi.BRIGHT_RED}[IMPERIAL CUSTOMS]{ansi.RESET} "
            f"{inf['name']} infraction: {infraction_reason}."
        )

        # Bribery / Bargain check to reduce fine
        from engine.skill_checks import resolve_bargain_check
        haggle = resolve_bargain_check(
            char, base_fine,
            npc_bargain_dice=3, npc_bargain_pips=0,
            is_buying=False,
        )
        final_fine = haggle["adjusted_price"]

        pct = haggle["price_modifier_pct"]
        if pct < 0:
            await ctx.session.send_line(
                f"  {ansi.DIM}[CUSTOMS] A... personal benefit fee. "
                f"Fine reduced to {final_fine:,}cr.{ansi.RESET}"
            )
        else:
            await ctx.session.send_line(
                f"  Fine: {final_fine:,}cr."
            )

        # Deduct fine
        credits = char.get("credits", 0)
        paid = min(credits, final_fine)
        char["credits"] = credits - paid
        await ctx.db.save_character(char["id"], credits=char["credits"])

        if paid < final_fine:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}Insufficient credits — partial payment of {paid:,}cr. "
                f"Ship impound risk elevated.{ansi.RESET}"
            )
        else:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}Fine paid: {paid:,}cr. Balance: {char['credits']:,}cr.{ansi.RESET}"
            )

        # Arrest check (rare)
        if _r.random() < inf["arrest_chance"] * 0.3:  # dampened for playability
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[CUSTOMS] You're being detained for further questioning. "
                f"(Roleplay with staff or wait for release.){ansi.RESET}"
            )

    except Exception:
        pass  # customs never blocks landing


class TransponderCommand(BaseCommand):
    """
    Manage your ship's transponder code.

    Usage:
      transponder              -- show current transponder status
      transponder false <name> -- set false ID (Con check vs scanners)
      transponder reset        -- restore real transponder
    """
    key = "transponder"
    aliases = ["transp"]
    help_text = "Manage ship transponder codes. False ID risks Class Two customs infraction."
    usage = "transponder [false <alias> | reset]"

    async def execute(self, ctx: CommandContext) -> None:
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return

        systems = _get_systems(ship)
        args = (ctx.args or "").strip().lower()

        # ── Show status ──────────────────────────────────────────────────────
        if not args:
            false_tp = systems.get("false_transponder")
            real_name = ship.get("name", "Unknown")
            reg = get_ship_registry()
            tmpl = reg.get(ship.get("template", ""))
            real_type = tmpl.name if tmpl else "Unknown"

            if false_tp:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_YELLOW}[TRANSPONDER]{ansi.RESET} "
                    f"FALSE ID ACTIVE"
                )
                await ctx.session.send_line(
                    f"  Real:  {ansi.BRIGHT_WHITE}{real_name}{ansi.RESET} ({real_type})"
                )
                await ctx.session.send_line(
                    f"  Alias: {ansi.BRIGHT_CYAN}{false_tp['alias']}{ansi.RESET} "
                    f"({false_tp.get('type', 'Unknown')})"
                )
                await ctx.session.send_line(
                    f"  {ansi.DIM}Detected by sensors on failed Con check. "
                    f"Class Two infraction if caught.{ansi.RESET}"
                )
            else:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_GREEN}[TRANSPONDER]{ansi.RESET} "
                    f"Real ID broadcasting: "
                    f"{ansi.BRIGHT_WHITE}{real_name}{ansi.RESET} ({real_type})"
                )
            return

        # ── Reset ────────────────────────────────────────────────────────────
        if args == "reset":
            if not systems.get("false_transponder"):
                await ctx.session.send_line("  No false transponder active.")
                return
            systems.pop("false_transponder", None)
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[TRANSPONDER]{ansi.RESET} "
                f"Real transponder restored."
            )
            return

        # ── Set false transponder ────────────────────────────────────────────
        if args.startswith("false "):
            alias = ctx.args.strip()[6:].strip()
            if not alias:
                await ctx.session.send_line(
                    "  Usage: transponder false <alias name>"
                )
                return

            # Must be docked to set up false ID
            if not ship.get("docked_at"):
                await ctx.session.send_line(
                    "  Must be docked to configure transponder codes."
                )
                return

            # Con or Forgery skill check (Easy 8)
            from engine.skill_checks import perform_skill_check
            from engine.character import SkillRegistry
            sr = SkillRegistry()
            sr.load_default()
            char = ctx.session.character
            # Use whichever is higher: con or forgery
            con_r    = perform_skill_check(char, "con",      8, sr)
            forge_r  = perform_skill_check(char, "forgery",  8, sr)
            result   = con_r if (con_r.roll >= forge_r.roll) else forge_r
            skill_used = "Con" if (con_r.roll >= forge_r.roll) else "Forgery"

            if result.fumble:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_RED}[TRANSPONDER]{ansi.RESET} "
                    f"Setup botched! Local customs flagged the attempt. "
                    f"({skill_used}: {result.roll} vs 8 — fumble)"
                )
                return

            if not result.success:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_YELLOW}[TRANSPONDER]{ansi.RESET} "
                    f"Code didn't take — transponder rejected the sequence. "
                    f"({skill_used}: {result.roll} vs 8) Try again."
                )
                return

            reg = get_ship_registry()
            tmpl = reg.get(ship.get("template", ""))
            systems["false_transponder"] = {
                "alias":   alias,
                "type":    tmpl.name if tmpl else "Unknown Vessel",
                "set_by":  char.get("name", "Unknown"),
            }
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            crit = " (critical — very convincing)" if result.critical_success else ""
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}[TRANSPONDER]{ansi.RESET} "
                f"False ID set: {ansi.BRIGHT_WHITE}{alias}{ansi.RESET}{crit}. "
                f"({skill_used}: {result.roll} vs 8)"
            )
            await ctx.session.send_line(
                f"  {ansi.DIM}Class Two infraction if detected by customs. "
                f"Use 'transponder reset' to restore real ID.{ansi.RESET}"
            )
            return

        await ctx.session.send_line(
            "  Usage: transponder  |  transponder false <name>  |  transponder reset"
        )


class MarketCommand(BaseCommand):
    """
    Show trade good prices at current port. Must be docked.

    Usage:
      market              -- prices at current planet
      market <planet>     -- prices at another planet (for planning)
    """
    key = "market"
    aliases = ["goods", "tradegoods"]
    help_text = "Show trade good prices at current port (must be docked)."
    usage = "market [<planet>]"

    async def execute(self, ctx: CommandContext) -> None:
        from engine.trading import TRADE_GOODS, get_market_at_planet

        args = (ctx.args or "").strip().lower()

        # Determine planet to display
        if args:
            # Manual planet lookup for planning
            planet = args.replace(" ", "_").replace("-", "_")
            # Normalise common aliases
            aliases = {
                "tatooine": "tatooine",
                "nar_shaddaa": "nar_shaddaa",
                "nar shaddaa": "nar_shaddaa",
                "smugglers moon": "nar_shaddaa",
                "kessel": "kessel",
                "corellia": "corellia",
            }
            planet = aliases.get(planet, planet)
            planet_display = planet.replace("_", " ").title()
        else:
            # Current planet from docked ship
            ship = await _get_ship_for_player(ctx)
            if not ship or not ship.get("docked_at"):
                await ctx.session.send_line(
                    "  You must be docked at a port to check local prices. "
                    "Use 'market <planet>' to check another planet's prices."
                )
                return
            systems = _get_systems(ship)
            zone_id = systems.get("current_zone", "")
            from engine.npc_space_traffic import ZONES
            zone_obj = ZONES.get(zone_id)
            planet = zone_obj.planet if zone_obj else None
            if not planet:
                await ctx.session.send_line(
                    "  Cannot determine current planet. "
                    "Use 'market <planet>' to check prices by name."
                )
                return
            planet_display = planet.replace("_", " ").title()

        market = get_market_at_planet(planet)

        # Header
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_CYAN}Trade Market — {planet_display}{ansi.RESET}"
        )
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_WHITE}{'Good':<24} {'Price/ton':>10}  {'Tier':<8}  {'Avail':>6}  Description{ansi.RESET}"
        )
        await ctx.session.send_line("  " + "─" * 80)

        tier_colors = {
            "source": ansi.BRIGHT_GREEN,
            "demand": ansi.BRIGHT_RED,
            "normal": ansi.DIM,
        }
        tier_labels = {
            "source": "SOURCE ↓",
            "demand": "DEMAND ↑",
            "normal": "normal",
        }

        from engine.trading import SUPPLY_POOL, DEMAND_POOL, get_planet_price as _gpp
        for row in market:
            col = tier_colors[row["tier"]]
            tier_str = tier_labels[row["tier"]]
            desc = row["description"][:30] + ("…" if len(row["description"]) > 30 else "")
            avail = SUPPLY_POOL.available(planet, row["key"])
            avail_str = f"{avail}t" if avail > 0 else "OUT"
            avail_col = col if avail > 0 else ansi.DIM

            # For demand goods, show effective sell price with depression
            price_str = f"{row['planet_price']:>8,}cr"
            if row["tier"] == "demand":
                good_obj = TRADE_GOODS.get(row["key"])
                if good_obj:
                    eff_sell = _gpp(good_obj, planet, include_demand_depression=True)
                    if eff_sell < row["planet_price"]:
                        price_str = f"{eff_sell:>8,}cr"
                        depression_pct = int((1 - eff_sell / row["planet_price"]) * 100)
                        desc = f"(-{depression_pct}% demand saturated)"

            await ctx.session.send_line(
                f"  {col}{row['name']:<24}{ansi.RESET}"
                f"  {col}{price_str}{ansi.RESET}"
                f"  {col}{tier_str:<8}{ansi.RESET}"
                f"  {avail_col}{avail_str:>6}{ansi.RESET}"
                f"  {ansi.DIM}{desc}{ansi.RESET}"
            )

        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.DIM}SOURCE = cheap here (buy). DEMAND = scarce here (sell). "
            f"Use 'buy cargo <good> <tons>' / 'sell cargo <good> <tons>'.{ansi.RESET}"
        )

        # Show current hold if docked
        ship = await _get_ship_for_player(ctx)
        if ship:
            from engine.trading import (
                get_ship_cargo, get_cargo_tons, cargo_free, TRADE_GOODS as TG
            )
            from engine.starships import get_ship_registry
            tmpl = get_ship_registry().get(ship.get("template", ""))
            cargo = get_ship_cargo(ship)
            if cargo:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_WHITE}Current hold "
                    f"({get_cargo_tons(ship)}/{(tmpl.cargo if tmpl else '?')}t):{ansi.RESET}"
                )
                for item in cargo:
                    gname = TG[item["good"]].name if item["good"] in TG else item["good"]
                    await ctx.session.send_line(
                        f"    {gname:<24}  {item['quantity']:>4}t  "
                        f"(paid {item['purchase_price']:,}cr/t)"
                    )


async def _handle_buy_from_droid(ctx, item_arg: str, shop_arg: str) -> None:
    """Handle 'buy <item> from <shop name>' — routes to vendor droid system."""
    from engine.vendor_droids import buy_from_droid, find_droid_by_name

    char   = ctx.session.character
    droids = await ctx.db.get_objects_in_room(char["room_id"], "vendor_droid")

    if not droids:
        await ctx.session.send_line(
            "  No vendor droids in this area. "
            "Use 'buy <weapon>' to purchase from NPC vendors."
        )
        return

    droid = find_droid_by_name(droids, shop_arg)
    if not droid:
        await ctx.session.send_line(
            f"  No vendor droid named '{shop_arg}' here. "
            f"Use 'browse' to see available shops."
        )
        return

    ok, msg = await buy_from_droid(
        char, droid["id"], item_arg, ctx.db, ctx.session_mgr
    )
    await ctx.session.send_line(f"  {msg}")


async def _handle_buy_cargo(ctx) -> None:
    """Handle 'buy cargo <good> <tons>'."""
    from engine.trading import (
        TRADE_GOODS, get_planet_price, get_ship_cargo,
        cargo_free, add_cargo, SUPPLY_POOL, volume_premium,
    )
    from engine.starships import get_ship_registry
    from engine.skill_checks import resolve_bargain_check

    args = ctx.args.strip()[len("cargo "):].strip().lower().split()
    if len(args) < 2:
        await ctx.session.send_line(
            "  Usage: buy cargo <good key> <tons>\n"
            "  Example: buy cargo raw_ore 20\n"
            "  Type 'market' to see available goods and keys."
        )
        return

    # Last arg is quantity, rest is good name/key
    try:
        quantity = int(args[-1])
    except ValueError:
        await ctx.session.send_line("  Quantity must be a number.")
        return
    good_query = " ".join(args[:-1]).replace(" ", "_")

    # Match by key or partial name
    good = TRADE_GOODS.get(good_query)
    if not good:
        good = next(
            (g for g in TRADE_GOODS.values()
             if good_query in g.name.lower().replace(" ", "_")),
            None,
        )
    if not good:
        await ctx.session.send_line(
            f"  Unknown trade good '{good_query}'. Type 'market' to see options."
        )
        return

    if quantity < 1:
        await ctx.session.send_line("  Quantity must be at least 1 ton.")
        return

    ship = await _get_ship_for_player(ctx)
    if not ship or not ship.get("docked_at"):
        await ctx.session.send_line("  You must be docked to buy cargo.")
        return

    tmpl = get_ship_registry().get(ship.get("template", ""))
    free = cargo_free(ship, tmpl)
    if quantity > free:
        await ctx.session.send_line(
            f"  Not enough cargo space. Need {quantity}t, only {free}t free."
        )
        return

    # Get planet price
    systems = _get_systems(ship)
    zone_id = systems.get("current_zone", "")
    from engine.npc_space_traffic import ZONES
    zone_obj = ZONES.get(zone_id)
    planet = zone_obj.planet if zone_obj else ""
    base_price = get_planet_price(good, planet)

    # Supply pool cap (review fix v1) — prevents the unlimited-trade
    # exploit that let a YT-1300 loop generate ~240,000 cr/hr.
    avail = 0
    if planet:
        avail = SUPPLY_POOL.available(planet, good.key)
        if avail <= 0:
            wait = SUPPLY_POOL.seconds_until_refresh(planet, good.key)
            await ctx.session.send_line(
                f"  The {good.name} market on {planet.title()} is picked "
                f"clean. Check back in ~{max(1, wait // 60)} min."
            )
            return
        if quantity > avail:
            await ctx.session.send_line(
                f"  Only {avail}t of {good.name} available on "
                f"{planet.title()} right now. "
                f"(Local supply refills every 45 min.)"
            )
            return

    # Bulk-purchase premium (P3 §3.2.D) — large orders relative to current
    # supply pay more per ton. Applied to the per-ton base price BEFORE
    # the Bargain check so high-Bargain players can negotiate against the
    # market-shifted price but can't completely cancel out the premium.
    premium_pct = volume_premium(quantity, avail) if planet else 0.0
    effective_per_ton = max(1, int(round(base_price * (1.0 + premium_pct))))

    # Bargain check
    char = ctx.session.character
    haggle = resolve_bargain_check(
        char, effective_per_ton * quantity,
        npc_bargain_dice=3, npc_bargain_pips=0,
        is_buying=True,
    )
    total_price = haggle["adjusted_price"]
    per_ton = max(1, total_price // quantity)

    current_credits = char.get("credits", 0)
    if current_credits < total_price:
        await ctx.session.send_line(
            f"  Not enough credits. {quantity}t of {good.name} costs "
            f"{total_price:,}cr, you have {current_credits:,}cr."
        )
        return

    # Commit
    import json as _j
    cargo = get_ship_cargo(ship)
    cargo = add_cargo(cargo, good.key, quantity, per_ton)
    await ctx.db.update_ship(ship["id"], cargo=_j.dumps(cargo))

    char["credits"] = current_credits - total_price
    await ctx.db.save_character(char["id"], credits=char["credits"])
    try:
        await ctx.db.log_credit(char["id"], -total_price, "trade_goods",
                                 char["credits"])
    except Exception as _e:
        log.debug("silent except in parser/space_commands.py:5147: %s", _e, exc_info=True)

    # Drain supply pool AFTER commit so a DB failure doesn't burn
    # supply. (Review fix v1)
    if planet:
        SUPPLY_POOL.consume(planet, good.key, quantity)

    if premium_pct > 0:
        # Round to whole percentage for display so 14.something doesn't surface.
        await ctx.session.send_line(
            f"  {ansi.DIM}Bulk premium: +{int(round(premium_pct * 100))}% "
            f"(large order on thin supply){ansi.RESET}"
        )
    pct = haggle["price_modifier_pct"]
    if pct != 0:
        direction = "discount" if pct < 0 else "markup"
        await ctx.session.send_line(
            f"  {ansi.DIM}Bargain: {abs(pct)}% {direction}{ansi.RESET}"
        )
    await ctx.session.send_line(
        ansi.success(
            f"  Purchased {quantity}t of {good.name} for {total_price:,}cr "
            f"({per_ton:,}cr/t). Hold: "
            f"{get_cargo_tons(ship) + quantity}t used."
        )
    )


class SalvageCommand(BaseCommand):
    key = "salvage"
    aliases = []
    help_text = (
        "Salvage components from a nearby derelict or destroyed ship wreck. "
        "Anyone aboard can attempt this — no station required."
    )
    usage = "salvage"

    # Loot tables: (weight, resource_type, qty_range, quality_range | None for credits)
    _DERELICT_LOOT = [
        (30, "metal",     (3, 8),  (40, 70)),
        (25, "energy",    (2, 5),  (50, 80)),
        (20, "composite", (1, 4),  (45, 75)),
        (15, "rare",      (1, 2),  (60, 90)),
        (10, "credits",   (500, 2000), None),
    ]
    _COMBAT_LOOT = [
        (40, "metal",     (2, 5),  (30, 50)),
        (30, "energy",    (1, 3),  (40, 60)),
        (20, "composite", (1, 2),  (35, 55)),
        (10, "rare",      (1, 1),  (50, 70)),
    ]

    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Salvage operations require open space. Launch first.")
            return

        from engine.space_anomalies import get_anomalies_for_zone, remove_anomaly
        from engine.skill_checks import perform_skill_check
        from engine.character import SkillRegistry, Character
        from engine.crafting import add_resource
        import random as _rnd

        systems  = _get_systems(ship)
        zone_id  = systems.get("current_zone", "")
        char     = ctx.session.character

        # Find a salvageable anomaly in zone (derelict type, resolution >= scans_needed)
        anomalies = get_anomalies_for_zone(zone_id)
        target = None
        for a in anomalies:
            if a.anomaly_type == "derelict" and a.resolution >= a.scans_needed:
                target = a
                break

        if target is None:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[SALVAGE]{ansi.RESET} "
                "No salvageable wreck in range. Use 'deepscan' to locate anomalies first."
            )
            return

        # Skill check: Technical, Easy (diff 8) for derelict, Moderate (diff 15) for wreck
        diff = 15 if target.is_wreck else 8
        diff_label = "Moderate" if target.is_wreck else "Easy"
        try:
            sr     = SkillRegistry()
            sr.load_default()
            result = perform_skill_check(char, "technical", diff, sr)
        except Exception:
            result = None  # graceful-drop → treat as success

        fumble   = result.fumble   if result else False
        critical = result.critical if result else False
        success  = (not fumble) and (result is None or result.total >= diff)

        if fumble:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[SALVAGE]{ansi.RESET} "
                f"Technical check fumbled! Equipment malfunction — salvage attempt failed. "
                f"The wreck may still be accessible."
            )
            return

        if not success:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[SALVAGE]{ansi.RESET} "
                f"Technical check failed ({diff_label}, diff {diff}). "
                f"Couldn't cut through the wreckage. Try again."
            )
            return

        # Choose loot table
        table = self._COMBAT_LOOT if target.is_wreck else self._DERELICT_LOOT
        weights  = [row[0] for row in table]
        loot_row = _rnd.choices(table, weights=weights, k=1)[0]

        _, rtype, qty_range, qual_range = loot_row
        qty = _rnd.randint(*qty_range)

        # Bonus on critical
        if critical:
            qty = max(qty, qty_range[1])  # max quantity on crit

        if rtype == "credits":
            # Credits: pay directly
            credit_amt = _rnd.randint(*qty_range)
            if critical:
                credit_amt = qty_range[1]
            old_credits = char.get("credits", 0)
            char["credits"] = old_credits + credit_amt
            await ctx.db.save_character(char["id"])
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[SALVAGE]{ansi.RESET} "
                f"{'Critical find! ' if critical else ''}"
                f"Recovered {credit_amt:,} credits from the wreckage."
            )
        else:
            quality = float(_rnd.randint(*qual_range))
            summary = add_resource(char, rtype, qty, quality)
            await ctx.db.save_character(char["id"])
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[SALVAGE]{ansi.RESET} "
                f"{'Critical find! ' if critical else ''}"
                f"Recovered: {summary}"
            )

        # Broadcast to bridge crew
        if ship.get("bridge_room_id"):
            await ctx.session_mgr.broadcast_to_room(
                ship["bridge_room_id"],
                f"  {ansi.BRIGHT_CYAN}[SALVAGE]{ansi.RESET} "
                f"{char['name']} strips the wreck and hauls in salvage.",
                exclude_session=ctx.session,
            )

        # Consume the anomaly — it's been salvaged
        remove_anomaly(zone_id, target.id)
        await ctx.session.send_line(
            f"  {ansi.DIM}[SALVAGE]{ansi.RESET} "
            f"Wreck exhausted. Nothing more to recover."
        )


class ShipNameCommand(BaseCommand):
    key = "shipname"
    aliases = ["+shipname"]
    help_text = (
        "Rename your ship. You must be the owner.\n"
        "\n"
        "Usage: shipname <new name>\n"
        "\n"
        "The name must be 2–40 characters and contain only letters,\n"
        "numbers, spaces, hyphens, and apostrophes."
    )
    usage = "shipname <new name>"

    async def execute(self, ctx: CommandContext):
        import re as _re
        char = ctx.session.character
        char_id = str(char["id"])

        if not ctx.args:
            await ctx.session.send_line("  Usage: shipname <new name>")
            return

        new_name = ctx.args.strip()

        # Validate length
        if len(new_name) < 2 or len(new_name) > 40:
            await ctx.session.send_line("  Ship name must be 2–40 characters.")
            return

        # Validate characters
        if not _re.match(r"^[A-Za-z0-9 '\-]+$", new_name):
            await ctx.session.send_line(
                "  Invalid characters. Use letters, numbers, spaces, hyphens, apostrophes."
            )
            return

        # Find a ship this character owns
        try:
            ships = await ctx.db.get_ships_owned_by(int(char_id))
        except Exception:
            ships = []

        if not ships:
            await ctx.session.send_line("  You don't own a ship.")
            return

        # Use the first owned ship (most players only own one)
        ship = ships[0]
        old_name = ship.get("name", "Unknown")

        try:
            await ctx.db.update_ship(ship["id"], name=new_name)
        except Exception as e:
            log.warning("[shipname] update_ship failed: %s", e)
            await ctx.session.send_line("  Failed to save ship name. Try again.")
            return

        await ctx.session.send_line(
            f"  Ship renamed: {old_name} → {new_name}"
        )
        log.info("[shipname] %s renamed ship %s → '%s'",
                 char.get("name"), ship.get("id"), new_name)

        # FDTS hook: shipname command used
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(
                ctx.session, ctx.db, "use_command", command="shipname"
            )
        except Exception:
            log.exception("[shipname] spacer_quest hook failed")


class BoardShipCommand(BaseCommand):
    """Establish or manage a boarding link with another ship in space.

    Usage:
      boardship <contact#>   — establish boarding link with target
      boardship release      — sever the boarding link
      boardship status       — show boarding link status
    """
    key = "boardship"
    aliases = ["boardlink"]
    help_text = (
        "Establish a boarding link with another ship in space.\n"
        "Target must be held in your tractor beam or stationary.\n"
        "Ships must be at Close range.\n"
        "\n"
        "EXAMPLES:\n"
        "  boardship 2         -- link to contact #2\n"
        "  boardship release   -- sever the link\n"
        "  boardship status    -- show link info"
    )
    usage = "boardship <contact#|release|status>"

    async def execute(self, ctx):
        from engine.boarding import (
            create_boarding_link, sever_boarding_link,
            get_boarding_link_info,
        )

        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship.get("docked_at"):
            await ctx.session.send_line("  You're docked. Use 'board' to board docked ships.")
            return

        # Must be pilot or copilot
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("pilot") != char_id and crew.get("copilot") != char_id:
            await ctx.session.send_line(
                "  Only the pilot or copilot can manage boarding links."
            )
            return

        arg = (ctx.args or "").strip().lower()

        # ── boardship status ──
        if arg == "status":
            info = get_boarding_link_info(ship)
            if not info:
                await ctx.session.send_line("  No active boarding link.")
                return
            partner = await ctx.db.get_ship(info["linked_to"])
            partner_name = partner["name"] if partner else "Unknown"
            await ctx.session.send_line(
                f"  \033[1;36m[BOARDING]\033[0m Linked to: "
                f"\033[1;37m{partner_name}\033[0m\n"
                f"  Type 'boarding_link' to cross, "
                f"'boardship release' to sever."
            )
            return

        # ── boardship release ──
        if arg == "release":
            ok, msg = await sever_boarding_link(
                ship, ctx.db, ctx.session_mgr, reason="manual")
            await ctx.session.send_line(f"  {msg}")
            return

        # ── boardship <contact#> ──
        if not arg:
            await ctx.session.send_line(
                "  Usage: boardship <contact#> | boardship release | boardship status\n"
                "  Target must be tractor-held or stationary, at Close range."
            )
            return

        # Parse contact number
        try:
            contact_num = int(arg)
        except ValueError:
            await ctx.session.send_line(
                f"  Unknown argument: '{arg}'. "
                f"Use a contact number, 'release', or 'status'."
            )
            return

        # Resolve contact# to a ship
        target_ship = await _resolve_contact(ctx, ship, contact_num)
        if not target_ship:
            return

        ok, msg = await create_boarding_link(
            ship, target_ship, ctx.db, ctx.session_mgr)
        await ctx.session.send_line(f"  {msg}")

        # Broadcast to target bridge
        if ok and target_ship.get("bridge_room_id"):
            await ctx.session_mgr.broadcast_to_room(
                target_ship["bridge_room_id"],
                f"  \033[1;31m[BOARDING]\033[0m "
                f"{ship.get('name', 'Unknown ship')} has established "
                f"a boarding link with your vessel!\n"
                f"  Type 'boarding_link_back' to cross, "
                f"or 'boardship release' to sever.",
            )


async def _resolve_contact(ctx, ship, contact_num: int):
    """Resolve a contact number from the scan list to a ship dict."""
    systems = _get_systems(ship)
    zone_key = systems.get("current_zone", "")
    if not zone_key:
        await ctx.session.send_line("  Navigation error — no current zone.")
        return None

    from engine.starships import get_space_grid
    grid = get_space_grid()

    # Build contact list the same way ScanCommand does
    all_ships = await ctx.db._db.execute_fetchall(
        "SELECT id, name, template, owner_id, systems, crew "
        "FROM ships WHERE docked_at IS NULL"
    )
    contacts = []
    for s in all_ships:
        s = dict(s)
        s_sys = _get_systems(s)
        if s_sys.get("current_zone") == zone_key and s["id"] != ship["id"]:
            contacts.append(s)

    if contact_num < 1 or contact_num > len(contacts):
        await ctx.session.send_line(
            f"  Invalid contact number: {contact_num}. "
            f"Use 'scan' to see contacts in this zone."
        )
        return None

    return contacts[contact_num - 1]


def register_space_commands(registry):
    """Register all space commands.

    The S57b umbrellas are registered FIRST so their aliases claim the
    bare-word routing before the per-verb classes' keys register. The
    per-verb classes remain registered at their bare keys for
    backward compatibility (same S54–S56 pattern).

    Five umbrellas live here:
      +pilot   — seat-claim + 10 piloting maneuvers
      +gunner  — seat-claim + fire, lockon
      +sensors — seat-claim + scan, deepscan
      +bridge  — commander seat-claim + 11 captain-tier actions
      +ship    — ship admin (expanded in S57a)

    Commands that stay bare (no umbrella) per the design doc:
      launch, land, hyperspace, disembark  — natural RP verbs
      board, boardship, salvage            — situational PvP / boarding
      buy, market, pay, credits            — economy (deferred to
                                             future economy_commands
                                             reorganization)
      copilot, engineer, navigator         — single-action seat claims

    Admin stays at @-prefix:
      @spawn, @setbounty
    """
    # S57b umbrellas — register first so their alias lists claim
    # the bare-word routing. Dispatch tables populate at module-load
    # time.
    umbrella_cmds = [
        PilotStationCommand(),
        GunnerStationCommand(),
        SensorsStationCommand(),
        BridgeCommand(),
    ]
    for cmd in umbrella_cmds:
        registry.register(cmd)

    # Per-verb classes register at their bare keys for backward
    # compatibility. `ShipCommand` is the S57a-expanded umbrella for
    # `+ship` — also registered here (alphabetically earlier in the
    # list to match pre-S57b ordering).
    cmds = [
        ShipsCommand(), ShipInfoCommand(),
        BoardCommand(), DisembarkCommand(),
        PilotCommand(), GunnerCommand(),
        CopilotCommand(), EngineerCommand(),
        NavigatorCommand(), CommanderCommand(),
        SensorsCommand(), VacateCommand(),
        AssistCommand(), CoordinateCommand(),
        ShipRepairCommand(), MyShipsCommand(),
        LaunchCommand(), LandCommand(),
        ShipCommand(), ScanCommand(), DeepScanCommand(), SalvageCommand(),
        MarketCommand(),
        TransponderCommand(),
        OrderCommand(),
        PowerCommand(),
        FireCommand(), EvadeCommand(),
        LockOnCommand(),
        CloseRangeCommand(), FleeShipCommand(),
        TailCommand(), OutmaneuverCommand(),
        ShieldsCommand(), HyperspaceCommand(),
        BuyCommand(), CreditsCommand(),
        DamConCommand(),
        PayCommand(), HailCommand(), CommsCommand(),
        SpawnShipCommand(), SetBountyCommand(),
        ResistTractorCommand(),
        BoardShipCommand(),
        CourseCommand(),
        JinkCommand(), BarrelRollCommand(),
        LoopCommand(), SlipCommand(),
        ShipNameCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)


# ═══════════════════════════════════════════════════════════════════════════
# +pilot — Umbrella for piloting station actions (S57b)
# ═══════════════════════════════════════════════════════════════════════════
#
# NOTE on naming: the legacy `PilotCommand` has key="pilot" (bare verb
# for "take the pilot seat"). The new umbrella uses key="+pilot" and
# is named `PilotStationCommand` to avoid class-name collision. Same
# pattern for +gunner → GunnerStationCommand, +sensors →
# SensorsStationCommand. The +bridge umbrella has no naming conflict
# (no `BridgeCommand` pre-existed) so it's just `BridgeCommand`.

_PILOT_SWITCH_IMPL: dict = {}

_PILOT_ALIAS_TO_SWITCH: dict[str, str] = {
    # Default — take the pilot seat
    "pilot": "claim",
    # Maneuvers
    "evade": "evade", "evasive": "evade",
    "jink": "jink",
    "barrelroll": "barrelroll", "broll": "barrelroll",
    "loop": "loop", "immelmann": "loop",
    "slip": "slip", "sideslip": "slip",
    "tail": "tail", "getbehind": "tail",
    "outmaneuver": "outmaneuver", "shake": "outmaneuver",
    "close": "close", "approach": "close",
    "fleeship": "flee", "breakaway": "flee",
    "course": "course", "navigate": "course", "setcourse": "course",
}


class PilotStationCommand(BaseCommand):
    """`+pilot` umbrella — seat claim + piloting maneuvers.

    Canonical              Bare aliases (still work)
    -------------------    ---------------------------
    +pilot                 pilot (take the pilot seat — default)
    +pilot/claim           pilot (same as default)
    +pilot/evade           evade, evasive
    +pilot/jink            jink
    +pilot/barrelroll      barrelroll, broll
    +pilot/loop            loop, immelmann
    +pilot/slip            slip, sideslip
    +pilot/tail <target>   tail, getbehind
    +pilot/outmaneuver     outmaneuver, shake
    +pilot/close <target>  close, approach
    +pilot/flee            fleeship, breakaway
    +pilot/course <zone>   course, navigate, setcourse

    `+pilot` with no switch takes the pilot seat (preserves existing
    PilotCommand UX). All other switches are piloting actions that
    only work while seated at the pilot station.
    """

    key = "+pilot"
    aliases = [
        # Seat-claim default
        "pilot",
        # Maneuvers (absorbed from per-verb class aliases)
        "evade", "evasive",
        "jink",
        "barrelroll", "broll",
        "loop", "immelmann",
        "slip", "sideslip",
        "tail", "getbehind",
        "outmaneuver", "shake",
        "close", "approach",
        "fleeship", "breakaway",
        "course", "navigate", "setcourse",
    ]
    help_text = (
        "All piloting verbs live under +pilot/<switch>. "
        "Bare verbs (evade, jink, loop, etc.) still work as aliases."
    )
    usage = "+pilot[/switch] [args]  — see 'help +pilot' for all switches"
    valid_switches = [
        "claim", "evade", "jink", "barrelroll", "loop", "slip",
        "tail", "outmaneuver", "close", "flee", "course",
    ]

    async def execute(self, ctx: CommandContext):
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            switch = _PILOT_ALIAS_TO_SWITCH.get(typed, "claim")

        impl = _PILOT_SWITCH_IMPL.get(switch)
        if impl is None:
            await ctx.session.send_line(
                f"  Unknown piloting switch: /{switch}. "
                f"Type 'help +pilot' for the full list."
            )
            return
        await impl.execute(ctx)


def _init_pilot_switch_impl():
    global _PILOT_SWITCH_IMPL
    _PILOT_SWITCH_IMPL = {
        "claim":       PilotCommand(),
        "evade":       EvadeCommand(),
        "jink":        JinkCommand(),
        "barrelroll":  BarrelRollCommand(),
        "loop":        LoopCommand(),
        "slip":        SlipCommand(),
        "tail":        TailCommand(),
        "outmaneuver": OutmaneuverCommand(),
        "close":       CloseRangeCommand(),
        "flee":        FleeShipCommand(),
        "course":      CourseCommand(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# +gunner — Umbrella for gunner station actions (S57b)
# ═══════════════════════════════════════════════════════════════════════════

_GUNNER_SWITCH_IMPL: dict = {}

_GUNNER_ALIAS_TO_SWITCH: dict[str, str] = {
    # Default — take a gunner seat
    "gunner": "claim", "gunnery": "claim",
    # Actions
    "fire": "fire",
    "lockon": "lockon", "lock": "lockon", "targetlock": "lockon",
}


class GunnerStationCommand(BaseCommand):
    """`+gunner` umbrella — seat claim + weapons actions.

    Canonical              Bare aliases (still work)
    -------------------    ---------------------------
    +gunner                gunner, gunnery (take a gunner seat — default)
    +gunner/claim [#]      gunner [#] (same as default, optional station #)
    +gunner/fire <target>  fire
    +gunner/lockon <t>     lockon, lock, targetlock

    `+gunner` with no switch takes a gunner seat (preserves existing
    GunnerCommand UX). `/fire` and `/lockon` are actions from that
    seat. Most ships have one gunner slot; multi-weapon ships accept
    a station number: `+gunner/claim 2`.
    """

    key = "+gunner"
    aliases = [
        "gunner", "gunnery",
        "fire",
        "lockon", "lock", "targetlock",
    ]
    help_text = (
        "All gunner verbs live under +gunner/<switch>. "
        "Bare verbs (gunner, fire, lockon) still work as aliases."
    )
    usage = "+gunner[/switch] [args]  — see 'help +gunner' for all switches"
    valid_switches = ["claim", "fire", "lockon"]

    async def execute(self, ctx: CommandContext):
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            switch = _GUNNER_ALIAS_TO_SWITCH.get(typed, "claim")

        impl = _GUNNER_SWITCH_IMPL.get(switch)
        if impl is None:
            await ctx.session.send_line(
                f"  Unknown gunner switch: /{switch}. "
                f"Type 'help +gunner' for the full list."
            )
            return
        await impl.execute(ctx)


def _init_gunner_switch_impl():
    global _GUNNER_SWITCH_IMPL
    _GUNNER_SWITCH_IMPL = {
        "claim":  GunnerCommand(),
        "fire":   FireCommand(),
        "lockon": LockOnCommand(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# +sensors — Umbrella for sensor station actions (S57b)
# ═══════════════════════════════════════════════════════════════════════════

_SENSORS_SWITCH_IMPL: dict = {}

_SENSORS_ALIAS_TO_SWITCH: dict[str, str] = {
    # Default — take the sensors seat
    "sensors": "claim", "sensor": "claim",
    # Actions
    "scan": "scan",
    "deepscan": "deepscan",
}


class SensorsStationCommand(BaseCommand):
    """`+sensors` umbrella — seat claim + sensor actions.

    Canonical           Bare aliases (still work)
    ----------------    ---------------------------
    +sensors            sensors, sensor (take the sensors seat — default)
    +sensors/claim      sensors (same as default)
    +sensors/scan       scan
    +sensors/deepscan   deepscan

    `+sensors` with no switch takes the sensors seat (preserves
    existing SensorsCommand UX). `/scan` is a passive sweep of the
    current zone; `/deepscan` is active analysis (higher precision,
    attracts attention).
    """

    key = "+sensors"
    aliases = [
        "sensors", "sensor",
        "scan",
        "deepscan",
    ]
    help_text = (
        "All sensor verbs live under +sensors/<switch>. "
        "Bare verbs (sensors, scan, deepscan) still work as aliases."
    )
    usage = "+sensors[/switch] [args]  — see 'help +sensors' for all switches"
    valid_switches = ["claim", "scan", "deepscan"]

    async def execute(self, ctx: CommandContext):
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            switch = _SENSORS_ALIAS_TO_SWITCH.get(typed, "claim")

        impl = _SENSORS_SWITCH_IMPL.get(switch)
        if impl is None:
            await ctx.session.send_line(
                f"  Unknown sensor switch: /{switch}. "
                f"Type 'help +sensors' for the full list."
            )
            return
        await impl.execute(ctx)


def _init_sensors_switch_impl():
    global _SENSORS_SWITCH_IMPL
    _SENSORS_SWITCH_IMPL = {
        "claim":    SensorsCommand(),
        "scan":     ScanCommand(),
        "deepscan": DeepScanCommand(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# +bridge — Umbrella for commander / captain / bridge-tier actions (S57b)
# ═══════════════════════════════════════════════════════════════════════════

_BRIDGE_SWITCH_IMPL: dict = {}

_BRIDGE_ALIAS_TO_SWITCH: dict[str, str] = {
    # Default — take the commander seat
    "commander": "claim", "command": "claim", "captain": "claim",
    # Ship-wide actions
    "order": "order", "orders": "order",
    "hail": "hail",
    "comms": "comms", "comm": "comms", "radio": "comms",
    "shields": "shields",
    "power": "power", "pwr": "power",
    "transponder": "transponder", "transp": "transponder",
    "resist": "resist", "breakfree": "resist",
    "damcon": "damcon", "damagecontrol": "damcon", "repair": "damcon",
    # Management
    "vacate": "vacate", "unstation": "vacate",
    "assist": "assist",
    "coordinate": "coordinate", "coord": "coordinate",
}


class BridgeCommand(BaseCommand):
    """`+bridge` umbrella — commander station + ship-wide actions.

    Canonical                Bare aliases (still work)
    --------------------     ---------------------------
    +bridge                  commander, command, captain (claim seat — default)
    +bridge/claim            commander (same as default)
    +bridge/order <s> <a>    order, orders       — tactical order to crew
    +bridge/hail <target>    hail                — open a channel
    +bridge/comms <chan>     comms, comm, radio  — comms channel management
    +bridge/shields <l>      shields             — raise/lower/distribute
    +bridge/power <alloc>    power, pwr          — power allocation
    +bridge/transponder <s>  transponder, transp — set transponder state
    +bridge/resist           resist, breakfree   — resist a tractor beam
    +bridge/damcon <s>       damcon, damagecontrol, repair — damage control
    +bridge/vacate           vacate, unstation   — leave your station
    +bridge/assist <skill>   assist              — help another roll
    +bridge/coordinate       coordinate, coord   — cross-station coordination

    `+bridge` with no switch claims the commander seat (preserves
    existing CommanderCommand UX). Most switches are ship-wide
    captain decisions (shields, power, hail, transponder). /order
    is the captain's tactical command to crew at other stations
    (distinct from +crew/order which directs hired NPCs).
    """

    key = "+bridge"
    aliases = [
        # Commander seat aliases
        "commander", "command", "captain",
        # Ship-wide actions
        "order", "orders",
        "hail",
        "comms", "comm", "radio",
        "shields",
        "power", "pwr",
        "transponder", "transp",
        "resist", "breakfree",
        "damcon", "damagecontrol", "repair",
        # Management
        "vacate", "unstation",
        "assist",
        "coordinate", "coord",
    ]
    help_text = (
        "All commander / bridge-tier verbs live under +bridge/<switch>. "
        "Bare verbs (commander, hail, shields, power, etc.) still work."
    )
    usage = "+bridge[/switch] [args]  — see 'help +bridge' for all switches"
    valid_switches = [
        "claim", "order", "hail", "comms", "shields", "power",
        "transponder", "resist", "damcon", "vacate", "assist",
        "coordinate",
    ]

    async def execute(self, ctx: CommandContext):
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            switch = _BRIDGE_ALIAS_TO_SWITCH.get(typed, "claim")

        impl = _BRIDGE_SWITCH_IMPL.get(switch)
        if impl is None:
            await ctx.session.send_line(
                f"  Unknown bridge switch: /{switch}. "
                f"Type 'help +bridge' for the full list."
            )
            return
        await impl.execute(ctx)


def _init_bridge_switch_impl():
    global _BRIDGE_SWITCH_IMPL
    _BRIDGE_SWITCH_IMPL = {
        "claim":       CommanderCommand(),
        "order":       OrderCommand(),
        "hail":        HailCommand(),
        "comms":       CommsCommand(),
        "shields":     ShieldsCommand(),
        "power":       PowerCommand(),
        "transponder": TransponderCommand(),
        "resist":      ResistTractorCommand(),
        "damcon":      DamConCommand(),
        "vacate":      VacateCommand(),
        "assist":      AssistCommand(),
        "coordinate":  CoordinateCommand(),
    }


# ── Populate the S57b umbrella switch-dispatch maps ──
# Must happen after all per-verb classes are defined in this module.
_init_pilot_switch_impl()
_init_gunner_switch_impl()
_init_sensors_switch_impl()
_init_bridge_switch_impl()
