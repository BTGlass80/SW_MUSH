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
        active_row = await ctx.db.get_active_mission(char_id)
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
            row = await ctx.db.get_active_mission(char_id)
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
        """Orchestrator: find mission → route space/ground → reward → hooks."""
        from engine.missions import get_mission_board, SPACE_MISSION_TYPES
        board = get_mission_board()

        active = await self._find_active_mission(ctx, board)
        if not active:
            return

        # Space missions have their own completion path
        if active.mission_type in SPACE_MISSION_TYPES:
            await self._complete_space_branch(ctx, board, active)
            return

        # Ground mission: verify location
        if not await self._check_ground_destination(ctx, active):
            return

        # Complete and resolve skill check
        completed = await board.complete(active.id, ctx.db)
        if not completed:
            await ctx.session.send_line(
                "  Something went wrong completing the mission. Try again.")
            return

        earned = await self._resolve_ground_reward(ctx, completed)
        await self._finalize_completion(ctx, board, completed, earned)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _find_active_mission(self, ctx, board):
        """Find the character's active mission from board or DB. Returns mission or None."""
        from engine.missions import MissionStatus
        char = ctx.session.character
        char_id = str(char["id"])

        active = None
        for m in board._missions.values():
            if m.accepted_by == char_id and m.status == MissionStatus.ACCEPTED:
                active = m
                break

        if not active:
            row = await ctx.db.get_active_mission(char_id)
            if row:
                try:
                    from engine.missions import Mission
                    active = Mission.from_dict(json.loads(row["data"]))
                    board._missions[active.id] = active
                except Exception:
                    log.warning("_find_active_mission: failed to load from DB", exc_info=True)

        if not active:
            await ctx.session.send_line("  You have no active mission.")
            return None

        if active.expires_at and time.time() > active.expires_at:
            await board.abandon(active.id, ctx.db)
            await ctx.session.send_line(
                ansi.error("  Your mission has expired and has been returned to the board."))
            return None

        return active

    async def _complete_space_branch(self, ctx, board, active):
        """Handle space mission completion: validation, reward, credits, achievements."""
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

        await self._award_credits(ctx, earned)
        await self._fire_achievements(ctx, earned)

    async def _check_ground_destination(self, ctx, active):
        """Check if the player is at the mission destination. Returns True/False."""
        char = ctx.session.character
        current_room = char.get("room_id")
        at_destination = False

        if active.destination_room_id:
            at_destination = (str(current_room) == str(active.destination_room_id))
        else:
            try:
                room = await ctx.db.get_room(current_room)
                if room:
                    room_name = room.get("name", "")
                    at_destination = (
                        active.destination.lower() in room_name.lower()
                        or room_name.lower() in active.destination.lower()
                    )
            except Exception:
                log.warning("_check_ground_destination: room lookup failed", exc_info=True)

        if not at_destination:
            await ctx.session.send_line(
                f"  You're not at the destination: {ansi.BOLD}{active.destination}{ansi.RESET}")
            await ctx.session.send_line(
                "  Travel there and type 'complete' again.")
            return False
        return True

    async def _resolve_ground_reward(self, ctx, completed):
        """Run skill check and award credits for ground mission. Returns earned amount."""
        from engine.skill_checks import resolve_mission_completion
        char = ctx.session.character

        check = resolve_mission_completion(
            char, completed.mission_type.value, completed.reward)

        earned = check["credits_earned"]
        old_credits = char.get("credits", 0)
        new_credits = old_credits + earned
        char["credits"] = new_credits
        await ctx.db.save_character(char["id"], credits=new_credits)

        if earned > 0:
            try:
                await ctx.db.log_credit(char["id"], earned, "mission", new_credits)
            except Exception as _e:
                log.debug("_resolve_ground_reward credit log: %s", _e, exc_info=True)

        # Display results
        await ctx.session.send_line(
            ansi.success(f"  Mission complete: {completed.title}"))
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

        return earned

    async def _award_credits(self, ctx, earned):
        """Award credits and log the transaction."""
        char = ctx.session.character
        old_credits = char.get("credits", 0)
        char["credits"] = old_credits + earned
        await ctx.db.save_character(char["id"], credits=old_credits + earned)
        try:
            await ctx.db.log_credit(char["id"], earned, "mission", old_credits + earned)
        except Exception as _e:
            log.debug("_award_credits credit log: %s", _e, exc_info=True)

    async def _fire_achievements(self, ctx, earned):
        """Fire mission completion + credits earned achievements."""
        try:
            from engine.achievements import on_mission_complete, on_mission_credits_earned
            await on_mission_complete(ctx.db, ctx.session.character["id"], session=ctx.session)
            if earned > 0:
                await on_mission_credits_earned(
                    ctx.db, ctx.session.character["id"], earned, session=ctx.session)
        except Exception as _e:
            log.debug("_fire_achievements: %s", _e, exc_info=True)

    async def _finalize_completion(self, ctx, board, completed, earned):
        """Fire achievements, replenish board, log, and run post-complete hooks."""
        char = ctx.session.character
        await self._fire_achievements(ctx, earned)

        # Replenish the board
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
            char.get("name"), completed.id, earned,
        )

        await self._post_complete_hooks(ctx, char, completed, earned)

    async def _post_complete_hooks(self, ctx, char, completed, earned):
        """Post-completion effects: faction rep, narrative, achievements, quests."""
        # ── Post-completion hooks (all non-critical) ──────────────────
        # Outer safety net: if anything leaks past the per-hook guards,
        # catch it here so the player never sees an error after a
        # successful completion.
        try:
            # Faction rep: +3 to character's primary faction on mission complete
            try:
                from engine.organizations import adjust_rep
                faction_id = char.get("faction_id", "independent")
                if faction_id and faction_id != "independent":
                    await adjust_rep(
                        char, faction_id, ctx.db,
                        action_key="complete_faction_mission",
                        reason=f"Mission: {completed.title}",
                        session=ctx.session,
                    )
            except Exception:
                log.exception("[missions] HOOK-1 faction rep failed")

            # Narrative: log mission completion
            try:
                from engine.narrative import log_action, ActionType as NT
                await log_action(ctx.db, char["id"], NT.MISSION_COMPLETE,
                                 f"Completed mission '{completed.title}' for {earned:,} credits",
                                 {"mission_type": completed.mission_type.value, "reward": earned})
            except Exception:
                log.exception("[missions] HOOK-2 narrative failed")
            try:
                from engine.ships_log import log_event as _mlog
                await _mlog(ctx.db, char, "missions_complete")
            except Exception:
                log.exception("[missions] HOOK-3 ships_log failed")
            try:
                from engine.tutorial_v2 import check_profession_chains
                await check_profession_chains(
                    ctx.session, ctx.db, "mission_complete",
                    mission_type=getattr(completed, "mission_type", None),
                )
            except Exception:
                log.exception("[missions] HOOK-4 profession_chains failed")
            # Territory influence: mission complete in zone
            try:
                from engine.territory import on_mission_complete
                await on_mission_complete(ctx.db, char, char.get("room_id", 0))
            except Exception:
                log.exception("[missions] HOOK-5 territory failed")
            # Spacer quest: mission complete
            try:
                from engine.spacer_quest import check_spacer_quest
                await check_spacer_quest(
                    ctx.session, ctx.db, "mission",
                    mission_type=getattr(completed, "mission_type", None),
                )
            except Exception:
                log.exception("[missions] HOOK-6 spacer_quest failed")
        except Exception:
            log.exception("[missions] OUTER post-completion safety net caught")



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
            row = await ctx.db.get_active_mission(char_id)
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


# ═══════════════════════════════════════════════════════════════════════════
# +mission — Umbrella command for all mission-board verbs (S55)
# ═══════════════════════════════════════════════════════════════════════════

# Map from canonical switch names to the per-verb class that implements them.
# When a player types `+mission/accept`, we look up "accept" here and call the
# corresponding command's execute(). When they type the bare alias `accept`,
# we map it back to the switch via _MISSION_ALIAS_TO_SWITCH.
#
# This table is the single source of truth for which verbs are switches
# under +mission. To add a new mission verb:
#   1. Add the class (as before)
#   2. Add an entry to _MISSION_SWITCH_IMPL
#   3. Add any bare aliases to _MISSION_ALIAS_TO_SWITCH
#   4. Add to MissionCommand.valid_switches
#   5. Update +mission.md help file
_MISSION_SWITCH_IMPL: dict = {}   # populated below; deferred to avoid forward-ref

# Map from bare alias to the canonical switch name. Players who type
# `accept m-4f3a` reach the umbrella; ctx.command is "accept"; we map
# to switch "accept" and dispatch. Covers every legacy bare verb.
#
# NOTE on collision: bare `accept` is also a combat PvP alias. Registration
# order makes mission win, which is the pre-S54 behavior (mission-accept
# has been the default meaning of bare `accept` since economy phase 2).
# After S55, canonical forms disambiguate: `+combat/accept` for PvP,
# `+mission/accept` for the board.
_MISSION_ALIAS_TO_SWITCH: dict[str, str] = {
    # Board (list available missions)
    "missions": "board", "mb": "board", "jobs": "board",
    # Accept
    "accept": "accept", "takejob": "accept",
    # View active
    "mission": "view", "myjob": "view", "activemission": "view",
    # Complete
    "complete": "complete", "finishjob": "complete", "turnin": "complete",
    # Abandon
    "abandon": "abandon", "dropmission": "abandon", "quitjob": "abandon",
}


class MissionCommand(BaseCommand):
    """`+mission` umbrella — dispatches to mission-board verb handlers by switch.

    Every mission-board verb is a switch under `+mission` as of S55:

    Canonical               Bare aliases (still work)
    --------------------    ---------------------------
    +mission                mission, myjob, activemission, +myjob  (view active)
    +mission/board          missions, mb, jobs, +jobs, +mb, +missions
    +mission/accept <id>    accept, takejob
    +mission/view           (same as +mission default)
    +mission/complete       complete, finishjob, turnin
    +mission/abandon        abandon, dropmission, quitjob

    `+mission` with no switch shows the player's active mission (preserves
    existing ActiveMissionCommand UX). `+mission/board` browses available
    jobs. `+mission/accept <id>` takes one. `+mission/complete` turns it
    in at the destination. `+mission/abandon` drops it back to the board.
    """

    key = "+mission"
    aliases = [
        # View-active aliases (from old ActiveMissionCommand)
        "mission", "myjob", "activemission", "+myjob",
        # Board aliases (from old MissionsCommand)
        "missions", "mb", "jobs", "+jobs", "+mb", "+missions",
        # Accept
        "accept", "takejob",
        # Complete
        "complete", "finishjob", "turnin",
        # Abandon
        "abandon", "dropmission", "quitjob",
    ]
    help_text = (
        "All mission-board verbs live under +mission/<switch>. "
        "Bare verbs (missions, accept, complete, abandon) still work as aliases."
    )
    usage = "+mission[/switch] [args]  — see 'help +mission' for all switches"
    valid_switches = [
        "board", "accept", "view", "complete", "abandon",
    ]

    async def execute(self, ctx: CommandContext):
        """Dispatch to the switch handler.

        Resolution priority:
          1. Explicit switch on the canonical form: `+mission/accept`
          2. Bare alias: `accept m-4f3a` → ctx.command=="accept" →
             _MISSION_ALIAS_TO_SWITCH maps it to "accept"
          3. Bare umbrella: `+mission` or `mission` → show active (view)
        """
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            # Could be the raw umbrella name ("+mission" / "mission" / "myjob")
            # or a bare alias mapped via _MISSION_ALIAS_TO_SWITCH.
            switch = _MISSION_ALIAS_TO_SWITCH.get(typed, "view")

        impl = _MISSION_SWITCH_IMPL.get(switch)
        if impl is None:
            await ctx.session.send_line(
                f"  Unknown mission switch: /{switch}. "
                f"Type 'help +mission' for the full list."
            )
            return
        # Delegate. The per-verb class's execute() handles all edge cases —
        # we're just the router.
        await impl.execute(ctx)


def _init_mission_switch_impl():
    """Build the switch → command instance dispatch table.

    Called once at module load. Maps the canonical switch name to the
    per-verb command class instance. The umbrella's execute() looks up
    here and delegates.
    """
    global _MISSION_SWITCH_IMPL
    _MISSION_SWITCH_IMPL = {
        "board":    MissionsCommand(),
        "accept":   AcceptMissionCommand(),
        "view":     ActiveMissionCommand(),
        "complete": CompleteMissionCommand(),
        "abandon":  AbandonMissionCommand(),
    }


# ── Registration ───────────────────────────────────────────────────────────────

def register_mission_commands(registry) -> None:
    """Register all mission commands. Call from game_server.py __init__.

    The `+mission` umbrella is the canonical form for every mission verb
    (`+mission/board`, `+mission/accept`, `+mission/complete`, etc.). Bare
    verb forms (`missions`, `accept`, `complete`, `abandon`) remain as
    aliases. Players' muscle memory keeps working; the canonical name moves.

    One subtlety on `accept`: both combat (PvP challenge) and mission
    (board) use the bare word. Registration order makes mission
    win the bare `accept`. Under `+combat/accept` vs `+mission/accept`
    the collision disappears.
    """
    # Umbrella first — registers `+mission` and all the canonical
    # verb aliases. (The dispatch table is populated at module-load
    # time via _init_mission_switch_impl() at the bottom of this file.)
    registry.register(MissionCommand())

    # Per-verb classes register their bare keys as fallback paths. The
    # umbrella's alias list above handles bare-word player input, but
    # these registrations are kept so any deep imports or tests that
    # call the class directly continue to work.
    #
    # NOTE: ActiveMissionCommand is NOT re-registered because its key
    # `+mission` collides with the umbrella. Its aliases are already in
    # the umbrella's alias list, and dispatch reaches it via
    # _MISSION_SWITCH_IMPL["view"]. Registering it here would silently
    # overwrite the umbrella in the registry.
    for cmd in [
        MissionsCommand(),
        AcceptMissionCommand(),
        CompleteMissionCommand(),
        AbandonMissionCommand(),
    ]:
        registry.register(cmd)


# ── Populate the umbrella switch-dispatch map (S55) ──
# Must happen after all per-verb classes are defined in this module.
_init_mission_switch_impl()
