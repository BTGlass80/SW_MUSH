# -*- coding: utf-8 -*-
"""
parser/tutorial_commands.py — Tutorial commands for SW_MUSH.  [v21]

Commands:
  training              -- go to Training Grounds hub
  training <module>     -- go directly to a module
  training list         -- show training progress
  training return       -- return to where you were before training
  training skip         -- skip the core tutorial (experienced players)

v21 additions:
  - 'factions' added to _MODULE_ROOMS (Galactic Factions elective)
  - 'training skip' subcommand for experienced players bypasses core tutorial
  - check_core_tutorial_step called from movement (hook note in docstring)
  - check_all_electives_complete called after each elective set_elective('complete')
"""
import logging
from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)

# Module name -> room name in the Training Grounds (built by build_tutorial.py)
_MODULE_ROOMS = {
    "space":    "Space Academy",
    "combat":   "Combat Arena",
    "economy":  "Trader's Hall",
    "crafting": "Crafter's Workshop",
    "force":    "Jedi Enclave",
    "bounty":   "Bounty Office",
    "crew":     "Crew Quarters",
    "factions": "Galactic Factions Briefing Room",   # [v21]
}
_HUB_ROOM_NAME = "Training Grounds"


async def _find_room_by_name(db, name: str):
    """Find a room ID by exact name match (case-insensitive)."""
    rows = await db.fetchall(
        "SELECT id FROM rooms WHERE LOWER(name) = LOWER(?) LIMIT 1",
        (name,),
    )
    return rows[0]["id"] if rows else None


async def _teleport(session, db, session_mgr, target_room_id: int,
                    departure_msg: str = None, arrival_msg: str = None):
    """Teleport a player to a room, broadcasting messages and auto-looking."""
    char = session.character
    old_room = char["room_id"]

    if departure_msg:
        await session_mgr.broadcast_to_room(
            old_room, departure_msg, exclude=session
        )

    char["room_id"] = target_room_id
    await db.save_character(char["id"], room_id=target_room_id)

    if arrival_msg:
        await session_mgr.broadcast_to_room(
            target_room_id, arrival_msg, exclude=session
        )

    # Auto-look
    from parser.builtin_commands import LookCommand
    from parser.commands import CommandContext as CC
    look_ctx = CC(
        session=session, raw_input="look", command="look",
        args="", args_list=[], db=db, session_mgr=session_mgr,
    )
    await LookCommand().execute(look_ctx)
    await session.send_hud_update(db=db, session_mgr=session_mgr)


class TrainingCommand(BaseCommand):
    key = "training"
    aliases = ["+training", "train"]
    help_text = (
        "Access the Training Grounds -- a persistent practice facility.\n"
        "\n"
        "USAGE:\n"
        "  training            -- go to the Training Grounds hub\n"
        "  training list       -- show your progress\n"
        "  training <module>   -- go directly to a module\n"
        "  training return     -- return to where you were\n"
        "  training skip       -- skip the core tutorial (experienced players)\n"
        "\n"
        "MODULES: space, combat, economy, crafting, force, bounty, crew, factions\n"
        "\n"
        "The Training Grounds are always available after you complete the\n"
        "core tutorial. Each module teaches a different game system.\n"
        "Completing modules earns credits and titles."
    )
    usage = "training [list | return | skip | <module>]"

    async def execute(self, ctx: CommandContext):
        from engine.tutorial_v2 import (
            format_status, set_return_room, get_tutorial_state,
            set_tutorial_core, start_starter_quest, ELECTIVE_LABELS,
            CORE_REWARD_CREDITS, grant_reward,
        )

        char = ctx.session.character
        args = (ctx.args or "").strip().lower()

        # -- training list ----------------------------------------------------
        if args in ("list", "status"):
            await ctx.session.send_line(format_status(char))
            return

        # -- training return --------------------------------------------------
        if args == "return":
            ts = get_tutorial_state(char)
            return_room = ts.get("return_room")
            if not return_room:
                await ctx.session.send_line(
                    "  You have no saved location to return to."
                )
                return
            set_return_room(char, None)
            await ctx.db.save_character(char["id"],
                                        attributes=char.get("attributes", "{}"))
            await _teleport(
                ctx.session, ctx.db, ctx.session_mgr,
                return_room,
                departure_msg=f"{char['name']} steps out of the Training Grounds.",
                arrival_msg=f"{char['name']} returns from the Training Grounds.",
            )
            return

        # -- training skip ----------------------------------------------------
        if args == "skip":
            # Drop 2 (May 19 2026): retire `training skip` under CW.
            # The legacy GCW core tutorial (Training Grounds elective
            # modules with Chalmun's Cantina as the post-tutorial
            # destination) is era-bound to GCW. Under CW the canonical
            # tutorial is the chain system selected at chargen, and
            # the skip path is the alt-character starter kit applied
            # at character creation (engine/api.py, Drop 2b). There is
            # no in-game way to "skip" the core tutorial post-creation
            # under CW — by the time the player runs commands, chargen
            # has already locked in their tutorial choice.
            try:
                from engine.era_state import get_active_era
                active_era = get_active_era()
            except Exception:
                active_era = "clone_wars"  # CW is production default

            if active_era != "gcw":
                await ctx.session.send_line(
                    "  The `training skip` command is a legacy of the GCW-era\n"
                    "  elective tutorial. Under the Clone Wars, your tutorial\n"
                    "  chain was selected at character creation and is the only\n"
                    "  path through training. If you want to play without a\n"
                    "  tutorial, create a second character on this account and\n"
                    "  pick the skip option in chargen."
                )
                return

            ts = get_tutorial_state(char)
            if ts["core"] == "complete":
                await ctx.session.send_line(
                    "  You've already completed the core tutorial."
                )
                return
            # Mark complete and grant reward without requiring room traversal
            set_tutorial_core(char, "complete", step=5)
            start_starter_quest(char)
            await ctx.db.save_character(char["id"],
                                        attributes=char.get("attributes", "{}"))
            await grant_reward(
                ctx.session, ctx.db,
                credits=CORE_REWARD_CREDITS,
                message=(
                    "Core tutorial skipped. "
                    f"+{CORE_REWARD_CREDITS:,} credits granted.\n"
                    "  Find Kessa Dray in Chalmun's Cantina for the starter quest chain.\n"
                    "  Type 'training list' to see available training modules."
                ),
            )
            return

        # -- training <module> ------------------------------------------------
        if args and args in _MODULE_ROOMS:
            module = args
            if module == "force" and not char.get("force_sensitive", False):
                await ctx.session.send_line(
                    "  The Jedi Enclave is only accessible to Force-sensitive individuals.\n"
                    "  You feel... nothing as you approach the door."
                )
                return
            target_name = _MODULE_ROOMS[module]
            target_id = await _find_room_by_name(ctx.db, target_name)
            if not target_id:
                await ctx.session.send_line(
                    f"  The {ELECTIVE_LABELS[module]} hasn't been built yet.\n"
                    "  (Run build_tutorial.py to create training facilities.)"
                )
                return
            set_return_room(char, char["room_id"])
            await ctx.db.save_character(char["id"],
                                        attributes=char.get("attributes", "{}"))
            await _teleport(
                ctx.session, ctx.db, ctx.session_mgr,
                target_id,
                departure_msg=f"{char['name']} heads to the {ELECTIVE_LABELS[module]}.",
                arrival_msg=f"{char['name']} arrives at the {ELECTIVE_LABELS[module]}.",
            )
            return

        if args and args not in _MODULE_ROOMS and args not in (
                "list", "return", "status", "skip"):
            valid = ", ".join(sorted(_MODULE_ROOMS.keys()))
            await ctx.session.send_line(
                f"  Unknown module '{args}'.\n"
                f"  Valid modules: {valid}"
            )
            return

        # -- training (no args) -- go to hub ----------------------------------
        hub_id = await _find_room_by_name(ctx.db, _HUB_ROOM_NAME)
        if not hub_id:
            await ctx.session.send_line(
                "  The Training Grounds haven't been built yet.\n"
                "  (Run build_tutorial.py to create training facilities.)"
            )
            return

        set_return_room(char, char["room_id"])
        await ctx.db.save_character(char["id"],
                                    attributes=char.get("attributes", "{}"))
        await _teleport(
            ctx.session, ctx.db, ctx.session_mgr,
            hub_id,
            departure_msg=f"{char['name']} heads to the Training Grounds.",
            arrival_msg=f"{char['name']} arrives at the Training Grounds.",
        )


def register_tutorial_commands(registry):
    registry.register(TrainingCommand())
