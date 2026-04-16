"""
Economy, mission, board, and territory tick handlers.

Ported from the inline blocks in game_server._game_tick_loop as part of
the review-fixes refactor (design doc §3.2, review fix v2).

Handler summary:
  space_mission_patrol_tick  — every tick; advances patrol mission counters
  board_housekeeping_tick    — every tick; ensures mission/bounty/smuggling
                               boards are loaded and expired entries pruned
  ambient_events_tick        — every tick; room flavour events
  world_events_tick          — every tick; world event lifecycle
  director_tick              — every tick; Director AI
  cp_engine_tick             — every tick; CP progression
  crew_wages_tick            — every WAGE_TICK_INTERVAL ticks (~4h)
  faction_payroll_tick       — every 86400 ticks (~1 day)
  vendor_recall_tick         — every 86400 ticks (~1 day, offset 1)
  housing_rent_tick          — every 604800 ticks (~1 week, offset 432000)
  territory_presence_tick    — every 3600 ticks (~1h, offset 1800)
  territory_decay_tick       — every 86400 ticks (~1 day, offset 43200)
  territory_claim_tick       — every 604800 ticks (~1 week, offset 518400)
  territory_resources_tick   — every 86400 ticks (~1 day, offset 64800)
  territory_contests_tick    — every 3600 ticks (~1h, offset 2700)

Registration: see GameServer.__init__ in server/game_server.py.
"""
from __future__ import annotations

import json
import logging

from server.tick_scheduler import TickContext

log = logging.getLogger(__name__)


async def npc_space_crew_tick(ctx: TickContext) -> None:
    """NPC crew auto-actions for all ships in space with NPC crew assigned.

    Only fires combat logic when enemies are in sensor range, so it's cheap
    in empty space. Passes ctx.ships_in_space to avoid an extra DB fetch.

    Ported from the inline block in _game_tick_loop (review fix v3).
    """
    from engine.npc_space_crew import tick_npc_space_combat
    await tick_npc_space_combat(ctx.db, ctx.session_mgr,
                                ships_in_space=ctx.ships_in_space)


async def npc_space_traffic_tick(ctx: TickContext) -> None:
    """NPC space traffic: spawn, move, despawn, bounty hunter respawns.

    Ported from the inline block in _game_tick_loop (review fix v3).
    """
    from engine.npc_space_traffic import get_traffic_manager
    await get_traffic_manager().tick(ctx.db, ctx.session_mgr)


async def space_mission_patrol_tick(ctx: TickContext) -> None:
    """Advance patrol mission tick counters for ships in their target zone.

    Uses ctx.ships_in_space — no extra DB fetch.
    Ported from _game_tick_loop (review fix v2).
    """
    from engine.missions import (
        get_mission_board, MissionType, MissionStatus, SPACE_MISSION_TYPES
    )
    board = get_mission_board()

    for ship in ctx.ships_in_space:
        if ship.get("docked_at"):
            continue
        sys = json.loads(ship.get("systems") or "{}")
        zone = sys.get("current_zone", "")
        if not zone:
            continue

        # Resolve pilot char_id from crew blob
        try:
            crew = json.loads(ship.get("crew") or "{}")
            pilot_id = str(crew.get("pilot", ""))
        except Exception:
            log.warning("patrol tick: bad crew JSON on ship %s", ship.get("id"), exc_info=True)
            continue
        if not pilot_id:
            continue

        for mission in list(board._missions.values()):
            if (mission.accepted_by != pilot_id
                    or mission.status != MissionStatus.ACCEPTED
                    or mission.mission_type not in SPACE_MISSION_TYPES):
                continue
            md = mission.mission_data or {}
            if mission.mission_type != MissionType.PATROL:
                continue
            if zone != md.get("target_zone", ""):
                continue

            md["patrol_ticks_done"] = md.get("patrol_ticks_done", 0) + 1
            mission.mission_data = md
            done = md["patrol_ticks_done"]
            req = md.get("patrol_ticks_required", 120)
            bridge = ship.get("bridge_room_id")
            if not bridge:
                continue
            if done == req // 2:
                await ctx.session_mgr.broadcast_to_room(
                    bridge,
                    "  [PATROL] Halfway through patrol. Hold position.",
                )
            elif done >= req:
                await ctx.session_mgr.broadcast_to_room(
                    bridge,
                    "  [PATROL] Patrol complete! Type 'complete' to turn in.",
                )


async def board_housekeeping_tick(ctx: TickContext) -> None:
    """Ensure mission, bounty, and smuggling boards are loaded and pruned.

    Every tick. Three independent sub-steps; each wrapped so one failure
    doesn't silence the others.
    Ported from _game_tick_loop (review fix v2).
    """
    try:
        from engine.missions import get_mission_board
        board = get_mission_board()
        await board.ensure_loaded(ctx.db)
        await ctx.db.cleanup_expired_missions()
    except Exception:
        log.warning("Mission board housekeeping failed", exc_info=True)

    try:
        from engine.bounty_board import get_bounty_board
        await get_bounty_board().ensure_loaded(ctx.db)
    except Exception:
        log.warning("Bounty board housekeeping failed", exc_info=True)

    try:
        from engine.smuggling import get_smuggling_board
        await get_smuggling_board().ensure_loaded(ctx.db)
    except Exception:
        log.warning("Smuggling board housekeeping failed", exc_info=True)


async def ambient_events_tick(ctx: TickContext) -> None:
    """Fire ambient room events. Every tick."""
    from engine.ambient_events import get_ambient_manager
    await get_ambient_manager().tick(ctx.db, ctx.session_mgr)


async def world_events_tick(ctx: TickContext) -> None:
    """World event lifecycle. Every tick."""
    from engine.world_events import get_world_event_manager
    await get_world_event_manager().tick(ctx.db, ctx.session_mgr)


async def director_tick(ctx: TickContext) -> None:
    """Director AI tick. Every tick."""
    from engine.director import get_director
    await get_director().tick(ctx.db, ctx.session_mgr)


async def cp_engine_tick(ctx: TickContext) -> None:
    """CP progression tick. Every tick."""
    from engine.cp_engine import get_cp_engine
    await get_cp_engine().tick(ctx.db, ctx.session_mgr)


async def crew_wages_tick(ctx: TickContext) -> None:
    """NPC crew wage processing. Interval set from WAGE_TICK_INTERVAL constant."""
    from engine.npc_crew import process_wage_tick
    await process_wage_tick(ctx.db, ctx.session_mgr)


async def faction_payroll_tick(ctx: TickContext) -> None:
    """Faction payroll disbursement. Every 86400 ticks (~1 game-day)."""
    from engine.organizations import faction_payroll_tick as _do_payroll
    paid = await _do_payroll(ctx.db)
    if paid:
        log.info("[orgs] Faction payroll: %dcr disbursed.", paid)


async def vendor_recall_tick(ctx: TickContext) -> None:
    """Vendor droid auto-recall. Every 86400 ticks (~1 game-day)."""
    from engine.vendor_droids import tick_auto_recall
    await tick_auto_recall(ctx.db, ctx.session_mgr)


async def housing_rent_tick(ctx: TickContext) -> None:
    """Housing rent collection. Every 604800 ticks (~1 week)."""
    from engine.housing import tick_housing_rent
    await tick_housing_rent(ctx.db, ctx.session_mgr)


async def hq_maintenance_tick(ctx: TickContext) -> None:
    """Org HQ maintenance from treasury. Every 604800 ticks (~1 week)."""
    from engine.housing import tick_hq_maintenance
    await tick_hq_maintenance(ctx.db, ctx.session_mgr)


async def territory_presence_tick(ctx: TickContext) -> None:
    """Territory presence accumulation. Every 3600 ticks (~1 hour)."""
    from engine.territory import tick_territory_presence
    await tick_territory_presence(ctx.db, ctx.session_mgr)


async def territory_decay_tick(ctx: TickContext) -> None:
    """Territory influence decay. Every 86400 ticks (~1 day)."""
    from engine.territory import tick_territory_decay
    await tick_territory_decay(ctx.db)


async def territory_claim_tick(ctx: TickContext) -> None:
    """Territory claim maintenance (upkeep costs). Every 604800 ticks (~1 week)."""
    from engine.territory import tick_claim_maintenance
    await tick_claim_maintenance(ctx.db, ctx.session_mgr)


async def debt_payment_tick(ctx: TickContext) -> None:
    """Hutt debt auto-payment. Every 604800 ticks (~1 week)."""
    try:
        from engine.debt import process_all_debts
        await process_all_debts(ctx.db, ctx.session_mgr)
    except Exception:
        import logging as _log
        _log.getLogger(__name__).warning("Debt payment tick failed", exc_info=True)


async def territory_resources_tick(ctx: TickContext) -> None:
    """Territory resource node yields. Every 86400 ticks (~1 day)."""
    from engine.territory import tick_resource_nodes
    await tick_resource_nodes(ctx.db, ctx.session_mgr)


async def territory_contests_tick(ctx: TickContext) -> None:
    """Territory contest resolution (expired contests). Every 3600 ticks (~1 hour)."""
    from engine.territory import tick_contest_resolution
    await tick_contest_resolution(ctx.db, ctx.session_mgr)


async def docking_fee_tick(ctx: TickContext) -> None:
    """Daily docking fee: 25 cr/day per docked player-owned ship.

    Economy hardening v23 — passive credit drain prevents indefinite
    free parking and creates incentive to undock or sell unused ships.
    Every 86400 ticks (~1 day), offset 21600 (6h after midnight).
    """
    DOCKING_FEE = 25

    try:
        ships = await ctx.db.get_docked_player_ships()
    except Exception:
        log.warning("docking_fee_tick: get_docked_player_ships failed", exc_info=True)
        return

    if not ships:
        return

    # Group by owner to batch credit deductions
    from collections import defaultdict
    owner_ships = defaultdict(list)
    for s in ships:
        owner_ships[s["owner_id"]].append(s)

    for owner_id, ship_list in owner_ships.items():
        total_fee = DOCKING_FEE * len(ship_list)
        try:
            char = await ctx.db.get_character(owner_id)
            if not char:
                continue
            old_credits = char.get("credits", 0)
            if old_credits >= total_fee:
                new_credits = old_credits - total_fee
                await ctx.db.save_character(owner_id, credits=new_credits)
                try:
                    await ctx.db.log_credit(
                        owner_id, -total_fee, "docking_fee", new_credits
                    )
                except Exception as _e:
                    log.debug("silent except in server/tick_handlers_economy.py:280: %s", _e, exc_info=True)
                # Notify if online
                try:
                    sess = ctx.session_mgr.find_by_character(owner_id)
                    if sess:
                        ship_names = ", ".join(s["name"] for s in ship_list)
                        await sess.send_line(
                            f"  \033[2m[DOCKING FEE]\033[0m {total_fee:,} cr "
                            f"deducted for {len(ship_list)} docked ship(s): "
                            f"{ship_names}. Balance: {new_credits:,} cr."
                        )
                except Exception as _e:
                    log.debug("silent except in server/tick_handlers_economy.py:292: %s", _e, exc_info=True)
            else:
                log.info(
                    "[economy] %s (id=%d) cannot pay %d cr docking fee (%d cr balance)",
                    char.get("name", "?"), owner_id, total_fee, old_credits,
                )
        except Exception:
            log.warning("docking_fee_tick: failed for owner %d", owner_id, exc_info=True)


# ── Idle Queue (Ollama GPU utilization) ──────────────────────────────────────

async def idle_queue_tick(ctx) -> None:
    """Process one idle AI task if Ollama is free. Runs every 30 ticks."""
    queue = getattr(ctx.server, '_idle_queue', None)
    if not queue:
        return
    await queue.try_process_one(ctx.db)


async def bark_seed_tick(ctx) -> None:
    """Periodically re-seed bark generation for populated rooms.

    Runs every 14400 ticks (~4 hours). On each run, queues bark tasks
    for NPCs in rooms with online players whose barks are stale.
    """
    queue = getattr(ctx.server, '_idle_queue', None)
    if not queue:
        return
    try:
        from engine.idle_queue import seed_barks_for_populated_rooms
        await seed_barks_for_populated_rooms(queue, ctx.db, ctx.session_mgr)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "bark_seed_tick failed", exc_info=True
        )


# ── Buff expiry tick ─────────────────────────────────────────────────────────

async def buff_expiry_tick(ctx) -> None:
    """Expire timed buffs on all online characters. Runs every 60 ticks."""
    try:
        from engine.buffs import expire_buffs
        for s in ctx.session_mgr.all:
            if not s.is_in_game or not s.character:
                continue
            expired = expire_buffs(s.character)
            if expired:
                for name in expired:
                    await s.send_line(
                        f"  \033[2m[EFFECT] {name} has worn off.\033[0m"
                    )
                # Persist updated attributes
                try:
                    await ctx.db.save_character(
                        s.character["id"],
                        attributes=s.character.get("attributes", "{}"),
                    )
                except Exception as _e:
                    log.debug("silent except in server/tick_handlers_economy.py:353: %s", _e, exc_info=True)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "buff_expiry_tick failed", exc_info=True
        )


# ── Environmental hazard tick ────────────────────────────────────────────────

async def hazard_tick(ctx) -> None:
    """Check environmental hazards for occupied rooms. Every 300 ticks (~5 min)."""
    try:
        from engine.hazards import hazard_tick as _ht
        await _ht(ctx.db, ctx.session_mgr)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "hazard_tick failed", exc_info=True
        )
