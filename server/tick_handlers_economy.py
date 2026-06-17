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

from engine.json_safe import load_ship_systems
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
        sys = load_ship_systems(ship)
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
    from engine.vendor_droids import tick_auto_recall, tick_listing_fees
    await tick_auto_recall(ctx.db, ctx.session_mgr)
    # Recurring relist fee on long-standing listings (audit v2 §2.7).
    await tick_listing_fees(ctx.db, ctx.session_mgr)


async def housing_rent_tick(ctx: TickContext) -> None:
    """Housing rent collection. Every 604800 ticks (~1 week)."""
    from engine.housing import tick_housing_rent
    await tick_housing_rent(ctx.db, ctx.session_mgr)


async def hq_maintenance_tick(ctx: TickContext) -> None:
    """Org HQ maintenance from treasury. Every 604800 ticks (~1 week)."""
    from engine.housing import tick_hq_maintenance
    await tick_hq_maintenance(ctx.db, ctx.session_mgr)


async def city_revenue_rollover_tick(ctx: TickContext) -> None:
    """Player Cities Phase 4: zero revenue_week on each city whose
    week boundary has elapsed. Every 86400 ticks (~1 day) so per-city
    boundaries roll at most ~1 day late. The actual rollover is
    per-city (week_start_ts is checked individually); design §5.3."""
    from engine.player_cities import tick_city_revenue_rollover
    await tick_city_revenue_rollover(ctx.db)


async def city_maintenance_tick(ctx: TickContext) -> None:
    """Player Cities Phase 6 (May 23 2026): weekly maintenance debit
    + 4-week grace state machine. Per design §8.1 + §8.2.

    Every 604800 ticks (~1 week). Per-city anchor is
    `maint_paid_until`, so cities whose week hasn't yet elapsed are
    skipped this pass.

    Drives the active → grace → dissolved state machine. Mails the
    Mayor + Founder on grace-state transitions (best-effort).
    Does NOT charge HQ base maintenance (that's
    engine.housing.tick_hq_maintenance's job).
    """
    from engine.player_cities import tick_city_maintenance
    await tick_city_maintenance(ctx.db, ctx.session_mgr)


async def city_vitality_tick(ctx: TickContext) -> None:
    """SYN.4 (2026-05-25): City vitality state machine.

    Per ``contestable_wilderness_design_v2.md`` §2.9.4. Hourly tick
    (every 3600 ticks). For each active city, counts citizens whose
    last_login is within the 7-day active window and compares against
    the HQ-tier threshold (1 for outpost, 3 for chapter house, 5 for
    fortress). Drives the active → reduced → dormant state machine:
    dropping below threshold marks the city 'reduced'; staying below
    for 14+ days transitions to 'dormant'. Recovery is immediate when
    the count rises back to threshold.

    Effects:
      * Tax cap drops to 50% of HQ-tier baseline while reduced/dormant.
        (Enforced at tax-set time via effective_tax_rate_cap().)
      * Expansion is blocked while reduced/dormant.
        (Enforced in claim_landmark_for_city.)
      * Dormant tag visible in look output (wired in display surfaces).

    Dormant state is a "reminder, not a death sentence" — small
    playerbases need recovery room. Cities don't dissolve on
    inactivity here.
    """
    from engine.player_cities import tick_city_vitality
    await tick_city_vitality(ctx.db, ctx.session_mgr)


async def territory_presence_tick(ctx: TickContext) -> None:
    """Territory presence accumulation. Every 3600 ticks (~1 hour)."""
    from engine.territory import tick_territory_presence
    await tick_territory_presence(ctx.db, ctx.session_mgr)


async def territory_decay_tick(ctx: TickContext) -> None:
    """Territory influence decay. Every 86400 ticks (~1 day)."""
    from engine.territory import tick_territory_decay
    await tick_territory_decay(ctx.db)


async def territory_claim_tick(ctx: TickContext) -> None:
    """Region maintenance tick (weekly upkeep). Every 604800 ticks (~1 week).

    SYN.1.b (2026-05-24): retargeted from the per-room
    ``tick_claim_maintenance`` to the region-scope
    ``tick_region_maintenance``. The tick *name* (territory_claim_tick)
    is preserved so the scheduler registration in server/game_server.py
    doesn't need to change. The legacy ``tick_claim_maintenance``
    function is stubbed to a no-op as part of the SYN.1.b retirement —
    calling it is harmless but accomplishes nothing.
    """
    from engine.territory import tick_region_maintenance
    await tick_region_maintenance(ctx.db, ctx.session_mgr)


async def debt_payment_tick(ctx: TickContext) -> None:
    """Hutt debt auto-payment. Every 604800 ticks (~1 week)."""
    try:
        from engine.debt import process_all_debts
        await process_all_debts(ctx.db, ctx.session_mgr)
    except Exception:
        import logging as _log
        _log.getLogger(__name__).warning("Debt payment tick failed", exc_info=True)


async def territory_resources_tick(ctx: TickContext) -> None:
    """Region passive yield tick (daily). Every 86400 ticks (~1 day).

    SYN.1.b (2026-05-24): retargeted from per-room
    ``tick_resource_nodes`` to the region-scope
    ``tick_region_passive_yield``. Active harvest (the larger income
    lever) ships in SYN.6 — this tick is the passive baseline only.
    Tick name preserved for scheduler stability.
    """
    from engine.territory import tick_region_passive_yield
    await tick_region_passive_yield(ctx.db, ctx.session_mgr)


async def region_quality_weekly_tick(ctx: TickContext) -> None:
    """SYN.6.b (2026-05-25): weekly per-region per-resource-type quality
    variance roll. Per ``contestable_wilderness_design_v2.md`` §2.5.5.

    Runs hourly with per-region-per-week idempotence (ISO year-week
    anchor). Only the first call in a new ISO week actually rolls;
    subsequent calls within the same week no-op cheaply.

    Crafters consume the outputs via SYN.6.a's harvest mechanic
    (``engine.harvest.compute_harvest_payout`` accepts per-type
    quality dicts) and via the ``faction resource_outlook`` parser
    surface.

    Hourly cadence + idempotence anchor matches the
    ``city_maintenance_tick`` pattern — simpler than trying to
    arrange a cron-style Monday-midnight fire on an interval-based
    scheduler.
    """
    from engine.region_quality import tick_weekly_region_quality
    await tick_weekly_region_quality(ctx.db, ctx.session_mgr)


async def wilderness_anomaly_tick(ctx: TickContext) -> None:
    """SYN.7.a (2026-05-25): wilderness anomaly spawn + expiry tick.
    Per ``contestable_wilderness_design_v2.md`` §2.8.

    Runs every CADENCE_TICK_INTERVAL seconds (1 hour). Per-region
    per-tick spawn-chance is 0.4 → expected interval between spawns
    of ~2.5h, matching the design's "every 2-3 hours per region"
    Tier 1 cadence.

    Anomalies are module-level transient state — restart wipes
    everything. Matches the engine.space_anomalies pattern.

    Broadcasts a news line on each spawn (best-effort) via
    session_mgr.broadcast.
    """
    from engine.wilderness_anomalies import tick_wilderness_anomalies
    await tick_wilderness_anomalies(ctx.db, ctx.session_mgr)


async def tier2_wilderness_anomaly_tick(ctx: TickContext) -> None:
    """SYN.7.b (2026-05-25): Tier 2 wilderness anomaly spawn tick.
    Per ``contestable_wilderness_design_v2.md`` §2.8 Tier 2.

    Runs every TIER2_CADENCE_TICK_INTERVAL seconds (6 hours). Per-region
    per-tick spawn-chance is 0.20 → expected interval between spawns
    of ~30h, matching the design's "every 24-48 hours per region"
    Tier 2 cadence.

    Tier 2 anomalies are multi-phase combat encounters with 2-3
    waves of increasingly difficult NPCs. They drop T5 materials
    (weapons_capacitor_core, composite_chitin) and named loot to
    the killing-blow player. Credits/resources are split among all
    characters in the anchor room at final clear.

    Module-level transient state — restart wipes (same as Tier 1).
    """
    from engine.wilderness_anomalies import tick_tier2_wilderness_anomalies
    await tick_tier2_wilderness_anomalies(ctx.db, ctx.session_mgr)


async def tier3_wilderness_anomaly_tick(ctx: TickContext) -> None:
    """SYN.8 (2026-05-25): Tier 3 wilderness anomaly spawn tick.
    Per ``contestable_wilderness_design_v2.md`` §2.8 Tier 3.

    Runs every TIER3_CADENCE_TICK_INTERVAL seconds (24 hours).
    Per-region per-tick spawn-chance is 0.10 → expected interval
    between spawns of ~10 days, matching the design's "every 7-14
    days per region" Tier 3 cadence.

    Tier 3 anomalies are world-boss events with 3 phases each. They
    drop unique trophies (one per participant) plus scaled T5
    material pieces (floor(N/4) per design's RotMG lesson).
    Killing-blow faction gets +50 region influence.

    Templates: krayt_dragon (Dune Sea, deep_dune_iron),
    maze_predator_apex (Coruscant Underworld, composite_chitin
    scaled), crashed_separatist_capital_ship (any region,
    weapons_capacitor_core scaled), republic_lost_patrol (any
    region, weapons_capacitor_core scaled).

    Module-level transient state — restart wipes (same as T1 + T2).
    """
    from engine.wilderness_anomalies import tick_tier3_wilderness_anomalies
    await tick_tier3_wilderness_anomalies(ctx.db, ctx.session_mgr)


async def building_construction_tick(ctx: TickContext) -> None:
    """SYN.9 (2026-05-25): Player-constructed building construction tick.
    Per ``contestable_wilderness_design_v2.md`` §2.9.3 + §3.9.

    Runs every 5 minutes. Two responsibilities:
      1. Transition `under_construction` → `operational` when
         completion_ts has elapsed (24h after construction start).
         For garrison_annex buildings, spawn 2 defending NPCs at
         completion.
      2. Transition `operational` with expired eviction notice
         (`evict_after_ts <= now`) to `evicted` status. Removes any
         spawned NPCs.

    Notifies the owner (if online) on both transitions:
      [CONSTRUCTION COMPLETE] on operational transition.
      [EVICTED] on evict transition.
    """
    from engine.buildings import tick_building_construction
    await tick_building_construction(ctx.db, ctx.session_mgr)


async def territory_contests_tick(ctx: TickContext) -> None:
    """Region contest resolution tick (two-phase). Every 3600 ticks (~1 hour).

    SYN.3 (2026-05-25): retargeted from the deleted Drop 6D
    zone-keyed contest-resolution function in ``engine.territory``
    to the SYN.3 ``engine.contest.tick_region_contest_resolution``
    (region-keyed, two-phase: Anchor spawn at accumulation_ends_at,
    defender-win-by-default at ends_at). The tick name is preserved
    for scheduler stability — the scheduler entry in
    ``server/game_server.py`` doesn't need touching.
    """
    from engine.contest import tick_region_contest_resolution
    await tick_region_contest_resolution(ctx.db, ctx.session_mgr)


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
            # Ledger chokepoint (economy audit F1): atomic deduct + credit_log
            # via adjust_credits, replacing the old non-atomic
            # save_character(credits=...) + separate log_credit two-step.
            # allow_negative=False makes affordability the chokepoint's job — a
            # broke owner is refused (returns None) and keeps parking free, as
            # before, with no partial/overdrawn state and no desynced ledger.
            new_credits = await ctx.db.adjust_credits(
                owner_id, -total_fee, "docking_fee", allow_negative=False
            )
            if new_credits is None:
                log.info(
                    "[economy] %s (id=%d) cannot pay %d cr docking fee (%d cr balance)",
                    char.get("name", "?"), owner_id, total_fee, old_credits,
                )
            else:
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
                    log.debug("docking_fee_tick: notify failed for owner %d: %s",
                              owner_id, _e, exc_info=True)
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


# ── SRB.2 morale-aura expiry (May 22 2026) ──────────────────────────────────
#
# Reaps expired morale_auras rows. Per design §2.1, an aura lasts 30
# minutes from a successful perform or until cleared by performer
# departure / room exit. The look-renderer also filters expired auras
# inline, so this tick is purely a DB-hygiene reaper — there's no
# player-visible delay between expiry and the aura "disappearing."
#
# Cadence: every 60 ticks (1 minute). Light query and even a few
# minutes of delay would be fine, but 1 minute matches the rest of
# the economy tick family.

async def morale_aura_expiry_tick(ctx) -> None:
    """Reap expired morale_auras rows. Runs every 60 ticks (~1 min)."""
    try:
        import time as _time
        reaped = await ctx.db.reap_expired_morale_auras(_time.time())
        if reaped:
            log.debug("morale_aura_expiry_tick reaped %d aura(s)", reaped)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "morale_aura_expiry_tick failed", exc_info=True
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


# ── Proactive credit-velocity alerting (economy audit #17 / R1) ─────────────
#
# economy_audit_v1 #17 shipped the *data* (Database.get_credit_velocity, read
# on demand by `@economy velocity`/`alerts`) but no proactive paging. R1 in
# SW_MUSH_Economy_Audit_FINAL explicitly asked for "velocity alerts." This
# tick closes the gap: each hour it evaluates server-wide net credit flow
# against tunable bands (engine.economy_alerts), and on a breach it records
# the alert (surfaced by `@economy alerts`), logs it, and pages online staff.
#
# Bidirectional on purpose — economy_audit_v2 notes deflation never trips the
# farming detector (positive-delta only), so a wage-heavy server can contract
# silently. The band is on |net|, labelled inflation vs deflation.
#
# Cadence: hourly (interval=3600). The 1h window is the trigger; the 24h
# figure rides along as context. All I/O is best-effort and fails open.

async def page_economy_alert_staff(session_mgr, line: str) -> None:
    """Send a one-line economy alert to every online admin/builder session.

    Best-effort and per-session guarded: a single bad session never aborts
    the page, and a missing session_mgr is a no-op (e.g. headless ticks).
    """
    if session_mgr is None:
        return
    msg = f"\n  \033[1;31m[ECONOMY ALERT]\033[0m {line}"
    for s in (getattr(session_mgr, "all", None) or []):
        try:
            if not getattr(s, "is_in_game", False):
                continue
            ch = getattr(s, "character", None) or {}
            if ch.get("is_admin") or ch.get("is_builder"):
                await s.send_line(msg)
        except Exception:
            # One uncooperative session must not stop the rest of the page.
            continue


async def credit_velocity_alert_tick(ctx) -> None:
    """Hourly server-wide credit-velocity check; pages staff on a band breach.

    Reads the 1h (trigger) and 24h (context) velocity, evaluates the bands in
    engine.economy_alerts, and on a breach records + logs + pages. Entirely
    best-effort: any failure logs and returns without disturbing the tick loop.
    """
    try:
        from engine.economy_alerts import (
            evaluate_velocity_alert, record_alert, format_alert_line,
        )
        v1h = await ctx.db.get_credit_velocity(3600)
        v24h = await ctx.db.get_credit_velocity(86400)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "credit_velocity_alert_tick: velocity fetch failed", exc_info=True
        )
        return

    alert = evaluate_velocity_alert(v1h, v24h)
    if not alert:
        return

    line = format_alert_line(alert)
    try:
        record_alert(alert)
        log.warning("[ECONOMY ALERT] %s", line)
    except Exception:
        log.debug("credit_velocity_alert_tick: record/log failed", exc_info=True)
    try:
        await page_economy_alert_staff(ctx.session_mgr, line)
    except Exception:
        log.debug("credit_velocity_alert_tick: staff page failed", exc_info=True)
