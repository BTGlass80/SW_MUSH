# -*- coding: utf-8 -*-
"""
parser/cp_commands.py  --  Character Point progression commands.

Commands:
  cpstatus            Show your tick/CP progress.
  train <skill>       Spend CP to advance a skill by 1 pip.
  kudos <player>      Give a roleplay kudos to another player (35 ticks/week max 3).
  scenebonus          Claim a scene completion bonus (staff/auto use; players
                      can manually trigger at scene close).

Design:
  - 300 ticks = 1 CP
  - Weekly hard cap: 300 ticks
  - train costs current_dice CP (doubled if above attribute) per the existing
    advance_skill() implementation in engine/character.py
  - kudos: 3 receivable per week, 35 ticks each, 7-day rolling giver→target lockout
"""

import os
import json
import logging
from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)
from server import ansi
from engine.character import Character, SkillRegistry, DicePool
from engine.cp_engine import get_cp_engine, TICKS_PER_CP, WEEKLY_CAP_TICKS, KUDOS_PER_WEEK


# ── Skill registry helper (mirrors combat_commands pattern) ──────────────────

def _get_skill_reg() -> SkillRegistry:
    reg = SkillRegistry()
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    skills_path = os.path.join(data_dir, "skills.yaml")
    if os.path.exists(skills_path):
        reg.load_file(skills_path)
    return reg


# ── cpstatus ──────────────────────────────────────────────────────────────────

class CPStatusCommand(BaseCommand):
    key = "+cpstatus"
    aliases = ["cpstatus", "cpinfo", "advancement", "+cp", "+advancement"]
    help_text = "Show your Character Point progression status."
    usage = "cpstatus"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(ansi.error("Not logged in."))
            return

        char_id = char["id"]
        engine = get_cp_engine()
        status = await engine.get_status(ctx.db, char_id)

        ticks_total = status["ticks_total"]
        ticks_week = status["ticks_this_week"]
        cap = status["weekly_cap"]
        cp = status["cp_available"]
        to_next = status["ticks_to_next_cp"]
        kudos_recv = status["kudos_received_week"]
        kudos_left = status["kudos_remaining_week"]

        # Progress bar for weekly cap (20 chars wide)
        bar_filled = int((ticks_week / cap) * 20)
        bar = ansi.BRIGHT_GREEN + "█" * bar_filled + ansi.DIM + "░" * (20 - bar_filled) + ansi.RESET

        lines = [
            ansi.header("── Character Point Progression ──"),
            f"  {ansi.BRIGHT_YELLOW}CP Available:{ansi.RESET}    {ansi.BRIGHT_WHITE}{cp}{ansi.RESET}",
            f"  {ansi.BRIGHT_YELLOW}Ticks (total):{ansi.RESET}   {ticks_total}",
            f"  {ansi.BRIGHT_YELLOW}To next CP:{ansi.RESET}      {to_next} ticks needed",
            f"",
            f"  {ansi.BRIGHT_YELLOW}This week:{ansi.RESET}  [{bar}] {ticks_week}/{cap}",
        ]

        if ticks_week >= cap:
            lines.append(f"  {ansi.BRIGHT_RED}Weekly cap reached.{ansi.RESET} Cap resets on a rolling 7-day window.")
        else:
            lines.append(f"  {ansi.DIM}Weekly cap: {cap - ticks_week} ticks remaining this week.{ansi.RESET}")

        lines += [
            f"",
            f"  {ansi.BRIGHT_YELLOW}Kudos received:{ansi.RESET}  {kudos_recv}/{KUDOS_PER_WEEK} this week  "
            f"({kudos_left} more receivable)",
            f"",
            f"  {ansi.DIM}300 ticks = 1 CP.  Use {ansi.BRIGHT_CYAN}train <skill>{ansi.RESET}{ansi.DIM} to spend CP.{ansi.RESET}",
            f"  {ansi.DIM}Use {ansi.BRIGHT_CYAN}kudos <player>{ansi.RESET}{ansi.DIM} to recognise good RP.{ansi.RESET}",
        ]

        for line in lines:
            await ctx.session.send_line(line)
        # Spacer quest: cpstatus viewed
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(ctx.session, ctx.db, "use_command", command="cpstatus")
        except Exception as _e:
            log.debug("silent except in parser/cp_commands.py:101: %s", _e, exc_info=True)


# ── train ─────────────────────────────────────────────────────────────────────

class TrainCommand(BaseCommand):
    key = "train"
    aliases = []
    help_text = (
        "Spend CP to advance a skill by one pip.\n"
        "Cost = number of dice in total pool.\n"
        "\n"
        "EXAMPLE: train blaster\n"
        "  Blaster at 5D costs 5 CP per pip.\n"
        "  Three pips = one die: 5D > 5D+1 > 5D+2 > 6D.\n"
        "\n"
        "Type +cpstatus to check your CP balance."
    )
    usage = "train <skill name>"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(ansi.error("Not logged in."))
            return

        skill_name = (ctx.args or "").strip().lower()
        if not skill_name:
            await ctx.session.send_line(ansi.error("Usage: train <skill name>"))
            await ctx.session.send_line(ansi.dim("Example: train blaster  |  train space transports"))
            return

        skill_reg = _get_skill_reg()
        skill_def = skill_reg.get(skill_name)
        if not skill_def:
            await ctx.session.send_line(
                ansi.error(f"Unknown skill: '{skill_name}'.  Check your sheet with {ansi.BRIGHT_CYAN}sheet{ansi.RESET}.")
            )
            return

        # Load full character object for advance_skill
        char_row = await ctx.db.get_character(char["id"])
        if not char_row:
            await ctx.session.send_line(ansi.error("Could not load character data."))
            return

        character = Character.from_db_row(char_row)
        cp_available = character.character_points

        # Calculate cost without committing (peek)
        key = skill_name.lower()
        current_bonus = character.skills.get(key, DicePool(0, 0))
        attr_pool = character.get_attribute(skill_def.attribute)
        total_pool = attr_pool + current_bonus
        cost = total_pool.dice  # advance_skill cost formula

        # Guild training bonus: 20% discount for guild members
        try:
            from engine.organizations import get_guild_cp_multiplier
            multiplier = await get_guild_cp_multiplier(char, ctx.db)
            cost = max(1, int(cost * multiplier))
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        if cp_available < cost:
            await ctx.session.send_line(
                ansi.error(
                    f"Not enough CP.  {skill_name.title()} costs {cost} CP "
                    f"(you have {cp_available} CP)."
                )
            )
            pool_str = f"{attr_pool + current_bonus}"
            await ctx.session.send_line(
                ansi.dim(f"Current pool: {pool_str}  →  next pip costs {cost} CP.")
            )
            return

        # Commit the advance
        character.advance_skill(skill_name, skill_reg)
        character.character_points -= cost
        actual_cost = cost

        # Save updated skills + CP
        await ctx.db.save_character(
            char["id"],
            skills=json.dumps({k: str(v) for k, v in character.skills.items()}),
            character_points=character.character_points,
        )

        # Update session character cache
        ctx.session.character["character_points"] = character.character_points

        new_pool = character.get_attribute(skill_def.attribute) + character.skills.get(key, DicePool(0, 0))
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_GREEN}[ADVANCEMENT]{ansi.RESET} "
            f"{skill_name.title()} trained: {attr_pool + current_bonus} → {new_pool}  "
            f"({actual_cost} CP spent, {character.character_points} CP remaining)"
        )

        # Narrative: log skill training
        try:
            from engine.narrative import log_action, ActionType as NT
            await log_action(ctx.db, char["id"], NT.SKILL_TRAIN,
                             f"Trained {skill_name.title()} to {new_pool} ({actual_cost} CP)",
                             {"skill": skill_name, "new_pool": str(new_pool), "cost": actual_cost})
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass


# ── kudos ─────────────────────────────────────────────────────────────────────

class KudosCommand(BaseCommand):
    key = "+kudos"
    aliases = ["kudos", "givekudos", "+givekudos"]
    help_text = (
        "Award kudos to a player for great RP. Grants 35 ticks\n"
        "toward their CP. You can give 3/week (7-day lockout\n"
        "per recipient).\n"
        "\n"
        "EXAMPLE: +kudos Tundra Great scene at the cantina!"
    )
    usage = "kudos <player name>"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(ansi.error("Not logged in."))
            return

        target_name = (ctx.args or "").strip()
        if not target_name:
            await ctx.session.send_line(ansi.error("Usage: kudos <player name>"))
            await ctx.session.send_line(
                ansi.dim(f"Kudos recognise excellent RP.  Each player can receive up to {KUDOS_PER_WEEK} kudos/week.")
            )
            return

        # Find target — any online player (v23: removed same-room requirement
        # to reduce bottleneck at small population sizes)
        target = None
        tl = target_name.lower()
        for s in ctx.session_mgr._sessions.values():
            if (s.character and
                    s.character["name"].lower().startswith(tl) and
                    s.character["id"] != char["id"]):
                target = s.character
                break

        if not target:
            await ctx.session.send_line(
                ansi.error(f"No online player named '{target_name}' found.")
            )
            return

        engine = get_cp_engine()
        result = await engine.award_kudos(ctx.db, char["id"], target["id"])

        if result["success"]:
            ticks = result["ticks_awarded"]
            giver_name = char.get("name", "Someone")
            target_name_display = target["name"]

            # Notify giver
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}[KUDOS]{ansi.RESET} "
                f"You gave kudos to {ansi.player_name(target_name_display)}. "
                f"+{ticks} ticks awarded to them."
            )

            # Notify target if online
            target_sess = ctx.session_mgr.find_by_character(target["id"])
            if target_sess:
                await target_sess.send_line(
                    f"  {ansi.BRIGHT_CYAN}[KUDOS]{ansi.RESET} "
                    f"{ansi.player_name(giver_name)} recognised your RP with kudos! "
                    f"+{ticks} ticks."
                )

            # Achievement: kudos_received (for target)
            try:
                from engine.achievements import on_kudos_received
                total_kudos = await ctx.db.kudos_count_received_this_week(target["id"])
                await on_kudos_received(ctx.db, target["id"], total_kudos,
                                        session=target_sess)
            except Exception as _e:
                log.debug("silent except in parser/cp_commands.py:288: %s", _e, exc_info=True)
        else:
            await ctx.session.send_line(ansi.error(result["message"]))


# ── scenebonus ────────────────────────────────────────────────────────────────

class SceneBonusCommand(BaseCommand):
    key = "+scenebonus"
    aliases = ["scenebonus", "endscene", "closescene", "+endscene"]
    help_text = "Claim a scene completion bonus based on your pose count."
    usage = "scenebonus [pose_count]"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(ansi.error("Not logged in."))
            return

        # If a staff/admin passes an explicit pose count, use it.
        # Otherwise default to a reasonable estimate (players self-report).
        arg = (ctx.args or "").strip()
        if arg.isdigit():
            pose_count = int(arg)
        else:
            # Ask the player to self-report their pose count for this scene
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[SCENE]{ansi.RESET} "
                f"How many poses did you contribute to this scene?"
            )
            await ctx.session.send_line(
                ansi.dim("Usage: scenebonus <number>  (e.g. scenebonus 8)")
            )
            return

        engine = get_cp_engine()
        result = await engine.award_scene_bonus(ctx.db, char["id"], pose_count)

        if result["ticks"] > 0:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[SCENE]{ansi.RESET} {result['message']}"
            )
        else:
            await ctx.session.send_line(
                f"  {ansi.DIM}[SCENE]{ansi.RESET} {result['message']}"
            )


# ── Registration ──────────────────────────────────────────────────────────────

def register_cp_commands(registry) -> None:
    registry.register(CPStatusCommand())
    registry.register(TrainCommand())
    registry.register(KudosCommand())
    registry.register(SceneBonusCommand())
