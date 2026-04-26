# -*- coding: utf-8 -*-
"""
parser/smuggling_commands.py  --  Smuggling Job Board Commands

Commands:
  smugjobs   — View available smuggling contacts (must be in eligible room)
  smugaccept <id> — Take a smuggling job
  smugjob    — View your active run
  smugdeliver — Deliver cargo at destination (must be docked)
  smugdump   — Jettison cargo (no fine, no pay)

Eligible rooms for viewing the board:
  Any room whose name contains "Jabba", "Cantina", or "Docking Bay"
  (or has zone key "jabba" or "cantina"). This keeps it in-world.

Patrol encounter:
  Triggered at launch (LandCommand/LaunchCommand hook — Drop 2).
  Resolved here for on-foot delivery.

Registration:
  from parser.smuggling_commands import register_smuggling_commands
  register_smuggling_commands(registry)
"""
import logging
import random

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)

# Rooms where the smuggling board is accessible (substring match on room name)
_BOARD_ROOM_KEYWORDS = ["jabba", "cantina", "docking bay", "docking", "spaceport"]


def _in_board_room(ctx: CommandContext) -> bool:
    """True if the player's current room gives access to the board."""
    room = ctx.session.current_room
    if not room:
        return False
    name = room.get("name", "").lower()
    return any(kw in name for kw in _BOARD_ROOM_KEYWORDS)


async def _get_board(ctx: CommandContext):
    from engine.smuggling import get_smuggling_board
    board = get_smuggling_board()
    await board.ensure_loaded(ctx.db)
    return board


class SmugJobsCommand(BaseCommand):
    key = "+smugjobs"
    aliases = ["smugjobs", "smugboard", "smugcontacts", "underworld", "+underworld"]
    access_level = AccessLevel.ANYONE
    help_text = "View available smuggling runs from your current location."
    usage = "smugjobs"

    async def execute(self, ctx: CommandContext) -> None:
        if not _in_board_room(ctx):
            await ctx.session.send_line(
                "  You need to be near a cantina, docking bay, or Jabba's contacts "
                "to access the underground job board."
            )
            return

        board = await _get_board(ctx)
        jobs = board.available_jobs()

        from engine.smuggling import format_board
        for line in format_board(jobs):
            await ctx.session.send_line(line)


class SmugAcceptCommand(BaseCommand):
    key = "smugaccept"
    aliases = ["takesmug", "takerun"]
    access_level = AccessLevel.ANYONE
    help_text = "Accept a smuggling job. Usage: smugaccept <id>"
    usage = "smugaccept <id>"

    async def execute(self, ctx: CommandContext) -> None:
        if not _in_board_room(ctx):
            await ctx.session.send_line(
                "  You need to be near a contact to accept a job."
            )
            return

        job_id = (ctx.args or "").strip().lower()
        if not job_id:
            await ctx.session.send_line("  Usage: smugaccept <job id>")
            await ctx.session.send_line("  Type 'smugjobs' to see available runs.")
            return

        char_id = ctx.session.character["id"]
        board = await _get_board(ctx)

        # Check not already carrying cargo
        if board.get_active_job(char_id):
            await ctx.session.send_line(
                "  You already have an active run. Deliver or dump it first."
            )
            return

        # Fuzzy prefix match
        job = None
        for j in board.available_jobs():
            if j.id == job_id or j.id.startswith(job_id):
                job = j
                break

        if not job:
            await ctx.session.send_line(
                f"  No job '{job_id}' available. Type 'smugjobs' to see current listings."
            )
            return

        accepted = await board.accept(job.id, char_id, ctx.db)
        if not accepted:
            await ctx.session.send_line(
                "  That job is no longer available. Someone got there first."
            )
            return

        from engine.smuggling import TIER_NAMES, _BOLD, _RESET, _RED
        await ctx.session.send_line(
            ansi.success(f"  Job accepted: {TIER_NAMES[accepted.tier]} — {accepted.cargo_type}")
        )
        await ctx.session.send_line(
            f"  {_BOLD}Reward:{_RESET} {accepted.reward:,} credits on delivery."
        )
        await ctx.session.send_line(
            f"  {_BOLD}Risk:{_RESET}   Fine of {_RED}{accepted.fine:,} credits{_RESET} if caught."
        )
        await ctx.session.send_line(
            f"  Contact: {accepted.contact_name}. Deliver to: {accepted.dropoff_name}."
        )
        await ctx.session.send_line(
            "  Launch when ready. Type 'smugjob' to review your run."
        )


class SmugJobCommand(BaseCommand):
    key = "+smugjob"
    aliases = ["smugjob", "myrun", "activerun", "cargo", "+cargo"]
    access_level = AccessLevel.ANYONE
    help_text = "View your active smuggling run."
    usage = "smugjob"

    async def execute(self, ctx: CommandContext) -> None:
        char_id = ctx.session.character["id"]
        board = await _get_board(ctx)
        job = board.get_active_job(char_id)

        if not job:
            await ctx.session.send_line(
                "  You have no active smuggling run. Type 'smugjobs' near a contact."
            )
            return

        from engine.smuggling import format_job_detail
        for line in format_job_detail(job):
            await ctx.session.send_line(line)


class SmugDeliverCommand(BaseCommand):
    key = "smugdeliver"
    aliases = ["deliver", "dropoff"]
    access_level = AccessLevel.ANYONE
    help_text = "Deliver your smuggled cargo. Must be docked in a ship."
    usage = "smugdeliver"

    async def execute(self, ctx: CommandContext) -> None:
        char_id = ctx.session.character["id"]
        board = await _get_board(ctx)
        job = board.get_active_job(char_id)

        if not job:
            await ctx.session.send_line(
                "  You have no active smuggling run."
            )
            return

        # Must be docked (not in space)
        char = ctx.session.character
        # Check if the player is on a ship that is docked
        # We check for current_room being a ship bridge room
        ship = await _get_player_ship(ctx)
        if not ship:
            await ctx.session.send_line(
                "  You need to be aboard a docked ship to make a delivery."
            )
            return
        if not ship.get("docked_at"):
            await ctx.session.send_line(
                "  You need to be docked first. Land your ship at a docking bay."
            )
            return

        # ── Destination planet check (Drop 11) ─────────────────────────────
        if job.destination_planet:
            # Verify ship is in the correct planet's zone
            import json as _smj
            _ship_sys = _smj.loads(ship.get("systems") or "{}")
            _current_zone = _ship_sys.get("current_zone", "")
            from engine.smuggling import PLANET_DOCK_ZONES
            _valid_zones = PLANET_DOCK_ZONES.get(job.destination_planet, [])
            if not _current_zone or not any(
                _current_zone.startswith(z) or z.startswith(_current_zone)
                for z in _valid_zones
            ):
                _planet_name = job.destination_planet.replace("_", " ").title()
                await ctx.session.send_line(
                    f"  This cargo is bound for {_planet_name}. "
                    f"You need to be docked there to make the delivery."
                )
                return

        # Run the patrol check (retroactively on delivery for ground-only runs)
        # For simplicity: patrol check happens here for non-space runs
        # (space runs get checked in the launch hook — Drop 2 patch)
        # If they made it to delivery without a space run, they're clean.
        completed = await board.complete(char_id, ctx.db)
        if not completed:
            await ctx.session.send_line("  Delivery failed — job no longer active.")
            return

        reward = completed.reward
        new_credits = char.get("credits", 0) + reward
        char["credits"] = new_credits
        await ctx.db.save_character(char_id, credits=new_credits)
        try:
            await ctx.db.log_credit(char["id"], reward, "smuggling", new_credits)
        except Exception as _e:
            log.debug("silent except in parser/smuggling_commands.py:234: %s", _e, exc_info=True)

        await ctx.session.send_line(
            ansi.success(
                f"  Delivery complete. {completed.cargo_type.title()} delivered "
                f"to {completed.dropoff_name}."
            )
        )
        # Ship's log: smuggling run completed (Drop 19)
        try:
            from engine.ships_log import log_event as _smlog
            await _smlog(ctx.db, char, "smuggling_runs")
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        try:
            from engine.tutorial_v2 import check_profession_chains
            _smug_job_data = completed.__dict__ if hasattr(completed, "__dict__") else {}
            _dest_p = getattr(completed, "dropoff_planet", "") or getattr(completed, "dropoff_name", "")
            _orig_p = getattr(completed, "pickup_planet", "") or getattr(completed, "pickup_name", "")
            await check_profession_chains(
                ctx.session, ctx.db, "smuggling_complete",
                dest_planet=str(_dest_p), origin_planet=str(_orig_p),
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
        # Achievement: smuggling_complete
        try:
            from engine.achievements import on_smuggling_complete, on_mission_credits_earned
            await on_smuggling_complete(ctx.db, char["id"], session=ctx.session)
            await on_mission_credits_earned(ctx.db, char["id"], reward, session=ctx.session)
        except Exception as _e:
            log.debug("silent except in parser/smuggling_commands.py:274: %s", _e, exc_info=True)
        await ctx.session.send_line(
            f"  Payment received: {reward:,} credits. Balance: {new_credits:,} credits."
        )

        # Director integration: record contraband sale
        try:
            from engine.director import get_director
            get_director().digest.record_contraband_sale()
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        # Narrative + faction rep hooks
        try:
            from engine.narrative import log_action, ActionType as NT
            await log_action(ctx.db, char["id"], NT.SMUGGLE_DELIVER,
                             f"Delivered {completed.cargo_type} to {completed.dropoff_name} "
                             f"for {reward:,} credits",
                             {"cargo": completed.cargo_type, "dropoff": completed.dropoff_name,
                              "reward": reward})
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        try:
            from engine.organizations import adjust_rep
            faction_id = char.get("faction_id", "independent")
            if faction_id and faction_id != "independent":
                await adjust_rep(
                    char, faction_id, ctx.db,
                    action_key="deliver_contraband",
                    reason=f"Smuggling delivery: {completed.cargo_type}",
                    session=ctx.session,
                )
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        # Spacer quest: smuggling job delivered
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(
                ctx.session, ctx.db, "smuggling",
                tier=getattr(completed, "tier", 0),
            )
        except Exception as _e:
            log.debug("silent except in parser/smuggling_commands.py:319: %s", _e, exc_info=True)


class SmugDumpCommand(BaseCommand):
    key = "smugdump"
    aliases = ["dumpcargo", "jettison"]
    access_level = AccessLevel.ANYONE
    help_text = "Jettison your smuggled cargo. No fine, no pay."
    usage = "smugdump"

    async def execute(self, ctx: CommandContext) -> None:
        char_id = ctx.session.character["id"]
        board = await _get_board(ctx)
        job = board.get_active_job(char_id)

        if not job:
            await ctx.session.send_line("  You're not carrying any cargo.")
            return

        from engine.smuggling import TIER_NAMES
        dumped = await board.dump_cargo(char_id, ctx.db)
        if dumped:
            await ctx.session.send_line(
                ansi.success(
                    f"  The {dumped.cargo_type} tumbles out the airlock. "
                    f"Job abandoned — no pay, no fine."
                )
            )
        else:
            await ctx.session.send_line("  Failed to dump cargo.")


# ── Patrol encounter helper (called from space launch hook) ───────────────────

async def check_patrol_on_launch(ctx: CommandContext) -> bool:
    """
    Check for an Imperial patrol encounter when launching.
    Call this from the LaunchCommand or hyperspace hook.

    Returns True if the player was caught (cargo confiscated, fine applied).
    """
    char_id = ctx.session.character["id"]

    from engine.smuggling import get_smuggling_board, resolve_patrol_encounter
    board = get_smuggling_board()
    job = board.get_active_job(char_id)
    if not job:
        return False  # No cargo, no problem

    # Check for lockdown
    lockdown_active = False
    try:
        from engine.director import get_director, AlertLevel
        lockdown_active = (
            get_director().get_alert_level("spaceport") == AlertLevel.LOCKDOWN
        )
    except Exception:
        log.warning("check_patrol_on_launch: unhandled exception", exc_info=True)
        pass

    # Player rolls Con or Sneak via perform_skill_check (skill check invariant).
    # Uses whichever pool is higher. Wound penalties and buffs apply properly.
    char = ctx.session.character
    from engine.skill_checks import perform_skill_check

    # Determine which skill to use: Con or Sneak (higher pool)
    try:
        import json as _sj
        _skills = _sj.loads(char.get("skills", "{}"))
        _attrs = _sj.loads(char.get("attributes", "{}"))
        from engine.dice import DicePool as _DP
        _perc = _DP.parse(_attrs.get("perception", "2D"))
        _con_bonus = _DP.parse(_skills.get("con", "0D"))
        _sneak_bonus = _DP.parse(_skills.get("sneak", "0D"))
        con_total = _perc.total_pips() + _con_bonus.total_pips()
        sneak_total = _perc.total_pips() + _sneak_bonus.total_pips()
        skill_name = "con" if con_total >= sneak_total else "sneak"
    except Exception:
        skill_name = "con"

    # Use difficulty 0 so we get the raw roll — resolve_patrol_encounter
    # does its own difficulty comparison.
    result = perform_skill_check(char, skill_name, 0)
    roll_total = result.roll
    display_skill = skill_name.title()

    outcome = resolve_patrol_encounter(job, roll_total, lockdown_active)

    if not outcome["intercepted"]:
        return False

    await ctx.session.send_line(f"\n  {outcome['message']}")

    if outcome["caught"]:
        # Confiscate cargo and apply fine
        fine = job.fine
        char = ctx.session.character
        credits = char.get("credits", 0)
        new_credits = max(0, credits - fine)
        char["credits"] = new_credits
        await ctx.db.save_character(char_id, credits=new_credits)
        try:
            await ctx.db.log_credit(char["id"], -fine, "smuggling_fine", new_credits)
        except Exception as _e:
            log.debug("silent except in parser/smuggling_commands.py:423: %s", _e, exc_info=True)
        await board.fail(char_id, ctx.db)
        await ctx.session.send_line(
            f"  Fine deducted: {fine:,} credits. Balance: {new_credits:,} credits."
        )
        return True
    else:
        await ctx.session.send_line(
            f"  ({display_skill} roll: {roll_total} vs difficulty {outcome['difficulty']})"
        )
        return False


async def check_patrol_on_arrival(ctx: CommandContext, dest_planet: str) -> bool:
    """
    Check for an Imperial patrol encounter on hyperspace arrival.
    Call this from the hyperspace arrival tick in game_server.py.

    dest_planet: e.g. "corellia", "kessel", "nar_shaddaa", "tatooine"
    Returns True if the player was caught (cargo confiscated, fine applied).

    Only triggers if the character has an active smuggling run with a
    matching destination_planet. Gracefully no-ops if no run active.
    """
    char_id = ctx.session.character["id"]

    from engine.smuggling import (
        get_smuggling_board, resolve_patrol_encounter,
        PLANET_PATROL_FREQUENCY,
    )
    board = get_smuggling_board()
    job = board.get_active_job(char_id)
    if not job:
        return False
    if job.destination_planet != dest_planet:
        return False  # Different destination — not their stop

    # Roll whether patrol intercepts at this planet
    arrival_chance = PLANET_PATROL_FREQUENCY.get(dest_planet, 0.0)
    import random as _arr_r
    if _arr_r.random() > arrival_chance:
        return False

    # Reuse launch patrol logic (same skill check, same outcome)
    lockdown_active = False
    try:
        from engine.director import get_director, AlertLevel
        lockdown_active = (
            get_director().get_alert_level("spaceport") == AlertLevel.LOCKDOWN
        )
    except Exception:
        log.warning("check_patrol_on_arrival: unhandled exception", exc_info=True)
        pass

    char = ctx.session.character
    from engine.skill_checks import perform_skill_check

    # Determine which skill to use: Con or Sneak (higher pool)
    try:
        import json as _sj2
        _skills = _sj2.loads(char.get("skills", "{}"))
        _attrs = _sj2.loads(char.get("attributes", "{}"))
        from engine.dice import DicePool as _DP2
        _perc = _DP2.parse(_attrs.get("perception", "2D"))
        _con_bonus = _DP2.parse(_skills.get("con", "0D"))
        _sneak_bonus = _DP2.parse(_skills.get("sneak", "0D"))
        con_total = _perc.total_pips() + _con_bonus.total_pips()
        sneak_total = _perc.total_pips() + _sneak_bonus.total_pips()
        skill_name = "con" if con_total >= sneak_total else "sneak"
    except Exception:
        skill_name = "con"

    result = perform_skill_check(char, skill_name, 0)
    roll_total = result.roll
    display_skill = skill_name.title()

    outcome = resolve_patrol_encounter(job, roll_total, lockdown_active)

    if not outcome["intercepted"]:
        return False

    planet_name = dest_planet.replace("_", " ").title()
    _CUSTOMS_BOLD_RED = "[1;31m"
    _CUSTOMS_RESET    = "[0m"
    _customs_msg = _CUSTOMS_BOLD_RED + "[CUSTOMS]" + _CUSTOMS_RESET + " Imperial customs intercepts your ship on arrival at " + planet_name + "!"
    await ctx.session.send_line("  " + _customs_msg)
    await ctx.session.send_line(f"  {outcome['message']}")

    if outcome["caught"]:
        fine = job.fine
        credits = char.get("credits", 0)
        new_credits = max(0, credits - fine)
        char["credits"] = new_credits
        await ctx.db.save_character(char_id, credits=new_credits)
        await board.fail(char_id, ctx.db)
        await ctx.session.send_line(
            f"  Fine deducted: {fine:,} credits. Balance: {new_credits:,} credits."
        )
        return True
    else:
        await ctx.session.send_line(
            f"  ({display_skill} roll: {roll_total} vs difficulty {outcome['difficulty']} — cleared)"
        )
        return False


async def _get_player_ship(ctx: CommandContext):
    """Get the ship the player is currently aboard, or None."""
    char_id = ctx.session.character["id"]
    try:
        ships = await ctx.db.get_ships_with_character(char_id)
        if ships:
            return ships[0]
        # Fallback: check ships owned by char that are docked
        owned = await ctx.db.get_ships_owned_by(char_id)
        if owned:
            return owned[0]
    except Exception:
        log.warning("_get_player_ship: unhandled exception", exc_info=True)
        pass
    return None


# ── Registration ──────────────────────────────────────────────────────────────

# S55: Switch & alias dispatch tables for the +smuggle umbrella.
_SMUGGLE_SWITCH_IMPL: dict = {}

_SMUGGLE_ALIAS_TO_SWITCH: dict[str, str] = {
    # board
    "smugjobs":   "board",
    "smugboard":  "board",
    "underworld": "board",
    "board":      "board",
    # accept
    "smugaccept": "accept",
    "takesmug":   "accept",
    "takerun":    "accept",
    "accept":     "accept",
    # view (active run)
    "smugjob":    "view",
    "myrun":      "view",
    "activerun":  "view",
    "cargo":      "view",
    "view":       "view",
    # deliver
    "smugdeliver":"deliver",
    "deliver":    "deliver",
    "dropoff":    "deliver",
    # dump
    "smugdump":   "dump",
    "dumpcargo":  "dump",
    "jettison":   "dump",
    "dump":       "dump",
}


class SmuggleCommand(BaseCommand):
    """`+smuggle` umbrella — full S55 dispatch over smuggling jobs."""
    key = "+smuggle"
    aliases: list[str] = [
        "smugjobs", "smugboard", "underworld",
        "smugaccept", "takerun",
        "smugjob", "myrun", "cargo",
        "smugdeliver", "deliver", "dropoff",
        "smugdump", "dumpcargo", "jettison",
    ]
    help_text = (
        "Smuggling job verbs: '+smuggle/board' (list), '+smuggle/accept "
        "<id>', '+smuggle/view' (active), '+smuggle/deliver', "
        "'+smuggle/dump'. Bare verbs (smugjobs/smugaccept/...) still "
        "work. Type 'help +smuggle' for the full reference."
    )
    usage = "+smuggle[/<switch>] [args]  — see 'help +smuggle'"
    valid_switches: list[str] = ["view", "board", "deliver", "accept", "dump"]

    async def execute(self, ctx: CommandContext):
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            switch = _SMUGGLE_ALIAS_TO_SWITCH.get(
                ctx.command.lower() if ctx.command else "",
                "view",
            )
        impl_cls = _SMUGGLE_SWITCH_IMPL.get(switch)
        if impl_cls is None:
            await ctx.session.send_line(self.help_text)
            return
        await impl_cls().execute(ctx)


def _init_smuggle_switch_impl():
    _SMUGGLE_SWITCH_IMPL["board"]   = SmugJobsCommand
    _SMUGGLE_SWITCH_IMPL["accept"]  = SmugAcceptCommand
    _SMUGGLE_SWITCH_IMPL["view"]    = SmugJobCommand
    _SMUGGLE_SWITCH_IMPL["deliver"] = SmugDeliverCommand
    _SMUGGLE_SWITCH_IMPL["dump"]    = SmugDumpCommand


_init_smuggle_switch_impl()


def register_smuggling_commands(registry) -> None:
    """Register all smuggling commands."""
    for cmd in [
        SmuggleCommand(),
        SmugJobsCommand(),
        SmugAcceptCommand(),
        SmugJobCommand(),
        SmugDeliverCommand(),
        SmugDumpCommand(),
    ]:
        registry.register(cmd)
