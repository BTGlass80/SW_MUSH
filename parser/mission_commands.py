# -*- coding: utf-8 -*-
"""
parser/mission_commands.py  --  Mission Board Commands
SW_MUSH  |  Economy Phase 2

Implements the four player-facing mission commands:
  missions  -- view the board
  accept    -- take a mission
  mission   -- view active mission
  complete  -- collect reward
  abandon   -- return mission to board

Register via: register_mission_commands(registry)
Called from game_server.py alongside the other register_*() calls.
"""

import json
import logging
import time

from server import ansi
from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


# ── Shared helper ──────────────────────────────────────────────────────────────

async def _get_board_and_rooms(db):
    """Return (board, rooms) -- loading board from DB if needed."""
    from engine.missions import get_mission_board
    board = get_mission_board()
    # Pull room list for destination matching (used during refresh)
    try:
        rooms = await db.get_all_rooms() if hasattr(db, "get_all_rooms") else []
    except Exception:
        rooms = []
    await board.ensure_loaded(db, rooms)
    return board, rooms


# ── Commands ───────────────────────────────────────────────────────────────────

class MissionsCommand(BaseCommand):
    key = "+missions"
    aliases = ["missions", "mb", "jobs", "+jobs", "+mb"]
    help_text = (
        "Browse available missions for credits.\n"
        "\n"
        "WORKFLOW:\n"
        "  +missions      -- browse available jobs\n"
        "  accept <id>    -- take a mission\n"
        "  +mission       -- check active mission\n"
        "  complete       -- turn in at destination\n"
        "  abandon        -- give up (returns to board)"
    )
    usage = "missions"

    async def execute(self, ctx: CommandContext):
        board, rooms = await _get_board_and_rooms(ctx.db)

        available = board.available_missions()

        from engine.missions import format_board
        for line in format_board(available):
            await ctx.session.send_line(line)


class AcceptMissionCommand(BaseCommand):
    key = "accept"
    aliases = ["takejob"]
    help_text = "Accept a mission from the board. One active mission at a time."
    usage = "accept <mission-id>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("  Usage: accept <mission-id>")
            await ctx.session.send_line("  Type 'missions' to see available jobs.")
            return

        char = ctx.session.character
        char_id = str(char["id"])

        # Check for existing active mission
        active_row = await ctx.db.get_character_active_mission(char_id)
        if active_row:
            try:
                active_data = json.loads(active_row["data"])
                active_dest = active_data.get("destination", "unknown")
            except Exception:
                active_dest = "unknown"
            await ctx.session.send_line(
                f"  You already have an active mission (destination: {active_dest}).")
            await ctx.session.send_line(
                "  Type 'mission' to see it, or 'abandon' to drop it first.")
            return

        mission_id = ctx.args.strip().lower()
        board, rooms = await _get_board_and_rooms(ctx.db)

        # Fuzzy match: allow partial id
        target = board.get(mission_id)
        if not target:
            # Try prefix match
            for mid, m in board._missions.items():
                if mid.startswith(mission_id):
                    target = m
                    break

        if not target:
            await ctx.session.send_line(
                f"  No mission '{mission_id}' on the board.")
            await ctx.session.send_line("  Type 'missions' to see available jobs.")
            return

        from engine.missions import MissionStatus
        if target.status != MissionStatus.AVAILABLE:
            await ctx.session.send_line(
                f"  That mission is no longer available.")
            return

        accepted = await board.accept(target.id, char_id, ctx.db)
        if not accepted:
            await ctx.session.send_line(
                "  That mission was just taken. Try another.")
            return

        await ctx.session.send_line(
            ansi.success(f"  Mission accepted: {accepted.title}"))
        await ctx.session.send_line(
            f"  {ansi.BOLD}Objective:{ansi.RESET} {accepted.objective}")
        await ctx.session.send_line(
            f"  {ansi.BOLD}Destination:{ansi.RESET} {accepted.destination}")
        await ctx.session.send_line(
            f"  {ansi.BOLD}Reward:{ansi.RESET} {accepted.reward:,} credits on completion.")
        await ctx.session.send_line(
            f"  Type 'mission' to review. 'complete' when you reach the destination.")

        # Space mission post-accept setup (Drop 14)
        from engine.missions import SPACE_MISSION_TYPES, MissionType
        if accepted.mission_type in SPACE_MISSION_TYPES:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}[SPACE MISSION]{ansi.RESET} "
                f"You need a ship and must be in the target zone to complete this.")
            if accepted.mission_type == MissionType.ESCORT:
                # Spawn escort NPC trader at the origin zone
                try:
                    from engine.npc_space_traffic import (
                        get_traffic_manager, TrafficArchetype,
                    )
                    tm = get_traffic_manager()
                    escort_ts = await tm._spawn(
                        ctx.db, ctx.session_mgr,
                        archetype=TrafficArchetype.TRADER,
                    )
                    if escort_ts:
                        # Override spawn zone to mission origin
                        origin = accepted.mission_data.get("origin_zone", "")
                        if origin:
                            escort_ts.current_zone = origin
                        accepted.mission_data["escort_ship_id"] = escort_ts.ship_id
                        accepted.mission_data["escort_ship_name"] = escort_ts.display_name
                        # Re-save mission with escort ID
                        from engine.missions import get_mission_board
                        board2 = get_mission_board()
                        if accepted.id in board2._missions:
                            board2._missions[accepted.id].mission_data = accepted.mission_data
                        await ctx.db.save_mission(accepted)
                        await ctx.session.send_line(
                            f"  Escort vessel {ansi.BOLD}{escort_ts.display_name}{ansi.RESET} "
                            f"is waiting at {origin.replace('_', ' ').title()}.")
                except Exception as _e:
                    log.warning("[missions] escort spawn failed: %s", _e)


class ActiveMissionCommand(BaseCommand):
    key = "+mission"
    aliases = ["mission", "myjob", "activemission", "+myjob"]
    help_text = "View your currently active mission."
    usage = "mission"

    async def execute(self, ctx: CommandContext):
        char_id = str(ctx.session.character["id"])

        # Check in-memory board first (faster)
        from engine.missions import get_mission_board, MissionStatus, format_mission_detail
        board = get_mission_board()
        active = None
        for m in board._missions.values():
            if m.accepted_by == char_id and m.status == MissionStatus.ACCEPTED:
                active = m
                break

        # Fallback to DB (e.g. after server restart)
        if not active:
            row = await ctx.db.get_character_active_mission(char_id)
            if row:
                try:
                    data = json.loads(row["data"])
                    from engine.missions import Mission
                    active = Mission.from_dict(data)
                    # Re-register in board memory
                    board._missions[active.id] = active
                except Exception as e:
                    log.warning("Failed to deserialize active mission: %s", e)

        if not active:
            await ctx.session.send_line("  You have no active mission.")
            await ctx.session.send_line("  Type 'missions' to see available jobs.")
            return

        for line in format_mission_detail(active):
            await ctx.session.send_line(line)


async def _complete_space_mission(ctx, active) -> bool:
    # Handle space mission completion checks.
    # Called from CompleteMissionCommand when mission is a space type.
    # Returns True if the mission passes its completion condition and
    # should be resolved; False to deny completion (with message sent).
    # Returns the string "partial" for escort destroyed (partial pay).
    from engine.missions import MissionType
    mtype = active.mission_type
    md = active.mission_data or {}

    # All space missions require the player to be aboard a launched ship
    try:
        from parser.space_commands import _get_ship_for_player
        ship = await _get_ship_for_player(ctx)
    except Exception:
        ship = None

    if not ship or ship.get("docked_at"):
        await ctx.session.send_line(
            f"  {ansi.error('You need to be aboard a launched ship to complete a space mission.')}")
        return False

    import json as _j
    systems = _j.loads(ship.get("systems") or "{}")
    current_zone = systems.get("current_zone", "")
    target_zone  = md.get("target_zone", "")

    if mtype == MissionType.PATROL:
        if current_zone != target_zone:
            await ctx.session.send_line(
                f"  You need to be in {target_zone.replace('_', ' ').title()}. "
                f"Currently in: {current_zone.replace('_', ' ').title() or 'unknown'}.")
            return False
        ticks_done     = md.get("patrol_ticks_done", 0)
        ticks_required = md.get("patrol_ticks_required", 120)
        if ticks_done < ticks_required:
            remaining = ticks_required - ticks_done
            await ctx.session.send_line(
                f"  Patrol not complete. Hold position for {remaining} more seconds.")
            return False
        return True

    elif mtype == MissionType.ESCORT:
        if current_zone != target_zone:
            await ctx.session.send_line(
                f"  Escort not delivered. Reach {target_zone.replace('_', ' ').title()} first.")
            return False
        escort_id = md.get("escort_ship_id")
        if escort_id is not None:
            # Check escort is still alive (still in traffic manager)
            try:
                from engine.npc_space_traffic import get_traffic_manager
                alive = escort_id in get_traffic_manager()._ships
            except Exception:
                alive = True  # graceful-drop: assume alive if can't check
            if not alive:
                # Escort was destroyed — partial pay (25%)
                return "partial"
        return True

    elif mtype == MissionType.INTERCEPT:
        if current_zone != target_zone:
            await ctx.session.send_line(
                f"  Intercept zone is {target_zone.replace('_', ' ').title()}. "
                f"You are not there.")
            return False
        kills_done   = md.get("kills_done", 0)
        kills_needed = md.get("kills_needed", 3)
        if kills_done < kills_needed:
            await ctx.session.send_line(
                f"  Need {kills_needed - kills_done} more kill(s) in this zone. "
                f"({kills_done}/{kills_needed} eliminated)")
            return False
        return True

    elif mtype == MissionType.SURVEY_ZONE:
        if current_zone != target_zone:
            await ctx.session.send_line(
                f"  Survey zone is {target_zone.replace('_', ' ').title()}. Fly there first.")
            return False
        # Check live anomaly state for this zone
        resolved_count = 0
        try:
            from engine.space_anomalies import get_anomalies_for_zone
            for anom in get_anomalies_for_zone(target_zone):
                if getattr(anom, "resolved", False):
                    resolved_count += 1
        except Exception:
            log.warning("_complete_space_mission: unhandled exception", exc_info=True)
            pass
        required = md.get("anomalies_required", 1)
        if resolved_count < required:
            await ctx.session.send_line(
                f"  Need {required} resolved anomaly in {target_zone.replace('_', ' ').title()}. "
                f"Use 'deepscan' and investigate.")
            return False
        return True

    return False


class CompleteMissionCommand(BaseCommand):
    key = "complete"
    aliases = ["finishjob", "turnin"]
    help_text = "Complete your active mission and collect the reward. Must be at the destination."
    usage = "complete"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        char_id = str(char["id"])
        current_room = char.get("room_id")

        from engine.missions import get_mission_board, MissionStatus
        board = get_mission_board()

        # Find active mission
        active = None
        for m in board._missions.values():
            if m.accepted_by == char_id and m.status == MissionStatus.ACCEPTED:
                active = m
                break

        # DB fallback
        if not active:
            row = await ctx.db.get_character_active_mission(char_id)
            if row:
                try:
                    from engine.missions import Mission
                    active = Mission.from_dict(json.loads(row["data"]))
                    board._missions[active.id] = active
                except Exception:
                    log.warning("execute: unhandled exception", exc_info=True)
                    pass

        if not active:
            await ctx.session.send_line("  You have no active mission.")
            return

        # Check expiry
        if active.expires_at and time.time() > active.expires_at:
            await board.abandon(active.id, ctx.db)
            await ctx.session.send_line(
                ansi.error("  Your mission has expired and has been returned to the board."))
            return

        # ── Space mission routing (Drop 14) ────────────────────────────────
        from engine.missions import SPACE_MISSION_TYPES
        if active.mission_type in SPACE_MISSION_TYPES:
            space_ok = await _complete_space_mission(ctx, active)
            if space_ok is False:
                return
            partial_escort = (space_ok == "partial")
            completed = await board.complete(active.id, ctx.db)
            if not completed:
                await ctx.session.send_line("  Something went wrong. Try again.")
                return
            base_reward = completed.reward
            if partial_escort:
                earned = max(50, int(base_reward * 0.25))
                await ctx.session.send_line(
                    ansi.success(f"  Escort mission complete — but the freighter was lost."))
                await ctx.session.send_line(
                    f"  Partial payment: {earned:,} credits (25%).")
            else:
                earned = base_reward
                await ctx.session.send_line(
                    ansi.success(f"  Space mission complete: {completed.title}"))
                await ctx.session.send_line(
                    f"  {ansi.BOLD}Reward: +{earned:,} credits{ansi.RESET}  "
                    f"(Balance: {ctx.session.character.get('credits', 0) + earned:,} cr)")
            old_credits = ctx.session.character.get("credits", 0)
            ctx.session.character["credits"] = old_credits + earned
            await ctx.db.save_character(ctx.session.character["id"],
                                        credits=old_credits + earned)
            return

        # ── Ground mission location check ─────────────────────────────────────
        # Check location -- match by room name or room id
        at_destination = False
        if active.destination_room_id:
            at_destination = (str(current_room) == str(active.destination_room_id))
        else:
            # Match by room name
            try:
                room = await ctx.db.get_room(current_room)
                if room:
                    room_name = room.get("name", "")
                    at_destination = (
                        active.destination.lower() in room_name.lower()
                        or room_name.lower() in active.destination.lower()
                    )
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass

        if not at_destination:
            await ctx.session.send_line(
                f"  You're not at the destination: {ansi.BOLD}{active.destination}{ansi.RESET}")
            await ctx.session.send_line(
                "  Travel there and type 'complete' again.")
            return

        # Complete and resolve skill check
        completed = await board.complete(active.id, ctx.db)
        if not completed:
            await ctx.session.send_line(
                "  Something went wrong completing the mission. Try again.")
            return

        from engine.skill_checks import resolve_mission_completion
        check = resolve_mission_completion(
            char,
            completed.mission_type.value,
            completed.reward,
        )

        earned = check["credits_earned"]
        old_credits = char.get("credits", 0)
        new_credits = old_credits + earned
        char["credits"] = new_credits
        await ctx.db.save_character(char["id"], credits=new_credits)

        await ctx.session.send_line(
            ansi.success(f"  Mission complete: {completed.title}"))
        # Skill roll feedback
        result_tag = ""
        if check["critical"]:
            result_tag = f" {ansi.BOLD}[EXCEPTIONAL +20%]{ansi.RESET}"
        elif check["partial"]:
            result_tag = f" {ansi.DIM}[PARTIAL PAY]{ansi.RESET}"
        elif not check["success"]:
            result_tag = f" {ansi.error('[FAILED]') if hasattr(ansi, 'error') else '[FAILED]'}"
        await ctx.session.send_line(
            f"  {ansi.BOLD}Reward: +{earned:,} credits{ansi.RESET}{result_tag}  "
            f"(Balance: {new_credits:,} cr)")
        await ctx.session.send_line(
            f"  Skill: {check['skill'].title()} [{check['pool']}]  "
            f"Roll: {check['roll']} vs Difficulty: {check['difficulty']}")
        await ctx.session.send_line(f"  {check['message']}")
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.DIM}Type 'missions' for your next job.{ansi.RESET}")

        # Immediately replenish the board in the background
        try:
            rooms = await ctx.db.get_all_rooms() if hasattr(ctx.db, "get_all_rooms") else []
            from engine.missions import generate_mission
            new_m = generate_mission(destination_rooms=rooms)
            board._missions[new_m.id] = new_m
            await ctx.db.save_mission(new_m)
            log.debug("[missions] Spawned replacement mission %s", new_m.id)
        except Exception as e:
            log.warning("[missions] Failed to spawn replacement: %s", e)

        log.info(
            "[missions] %s completed %s for %d cr",
            char.get("name"), completed.id, reward,
        )

        # Faction rep: +3 to character's primary faction on mission complete
        try:
            from engine.organizations import REP_GAINS
            faction_id = char.get("faction_id", "independent")
            if faction_id and faction_id != "independent":
                await ctx.db.adjust_rep(
                    char["id"], faction_id, REP_GAINS["complete_faction_mission"]
                )
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        # Narrative: log mission completion
        try:
            from engine.narrative import log_action, ActionType as NT
            await log_action(ctx.db, char["id"], NT.MISSION_COMPLETE,
                             f"Completed mission '{completed.title}' for {reward:,} credits",
                             {"mission_type": completed.mission_type.value, "reward": reward})
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        try:
            from engine.ships_log import log_event as _mlog
            await _mlog(ctx.db, char, "missions_complete")
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        try:
            from engine.tutorial_v2 import check_profession_chains
            await check_profession_chains(
                ctx.session, ctx.db, "mission_complete",
                mission_type=getattr(completed, "mission_type", None),
            )
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        # Territory influence: mission complete in zone
        try:
            from engine.territory import on_mission_complete
            await on_mission_complete(ctx.db, char, char.get("room_id", 0))
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        # Spacer quest: mission complete
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(
                ctx.session, ctx.db, "mission",
                mission_type=getattr(completed, "mission_type", None),
            )
        except Exception:
            pass


class AbandonMissionCommand(BaseCommand):
    key = "abandon"
    aliases = ["dropmission", "quitjob"]
    help_text = "Abandon your active mission. Returns it to the board with no penalty."
    usage = "abandon"

    async def execute(self, ctx: CommandContext):
        char_id = str(ctx.session.character["id"])

        from engine.missions import get_mission_board, MissionStatus
        board = get_mission_board()

        active = None
        for m in board._missions.values():
            if m.accepted_by == char_id and m.status == MissionStatus.ACCEPTED:
                active = m
                break

        if not active:
            row = await ctx.db.get_character_active_mission(char_id)
            if row:
                try:
                    from engine.missions import Mission
                    active = Mission.from_dict(json.loads(row["data"]))
                    board._missions[active.id] = active
                except Exception:
                    log.warning("execute: unhandled exception", exc_info=True)
                    pass

        if not active:
            await ctx.session.send_line("  You have no active mission to abandon.")
            return

        abandoned = await board.abandon(active.id, ctx.db)
        if not abandoned:
            await ctx.session.send_line("  Failed to abandon mission. Try again.")
            return

        await ctx.session.send_line(
            ansi.success(f"  Mission abandoned: {abandoned.title}"))
        await ctx.session.send_line(
            "  The job has been returned to the board.")
        await ctx.session.send_line(
            f"  {ansi.DIM}Type 'missions' to find a new job.{ansi.RESET}")


# ── Registration ───────────────────────────────────────────────────────────────

def register_mission_commands(registry) -> None:
    """Register all mission commands. Call from game_server.py __init__."""
    for cmd in [
        MissionsCommand(),
        AcceptMissionCommand(),
        ActiveMissionCommand(),
        CompleteMissionCommand(),
        AbandonMissionCommand(),
    ]:
        registry.register(cmd)
