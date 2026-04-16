# -*- coding: utf-8 -*-
"""
parser/force_commands.py
Force Powers Commands — WEG D6 Revised & Expanded

Commands:
  force <power> [target]  — use a Force power
  powers                  — list available powers
  forcestatus             — show Force attribute totals and DSP

Wires into the existing character system (control/sense/alter DicePool
attributes, force_points, dark_side_points) without touching combat_commands.py.
"""
import json
import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.character import Character, SkillRegistry
from engine.force_powers import (
    POWERS, get_power, list_powers_for_char, resolve_force_power,
    format_power_list, ForcePower,
)
from server import ansi

log = logging.getLogger(__name__)

# Achievement hooks (graceful-drop)
async def _ach_force_hook(db, char_id, event, session=None):
    try:
        from engine.achievements import check_achievement
        await check_achievement(db, char_id, event, session=session)
    except Exception as _e:
        log.debug("silent except in parser/force_commands.py:32: %s", _e, exc_info=True)


_SKILL_REG_CACHE: SkillRegistry | None = None


def _get_skill_reg() -> SkillRegistry:
    global _SKILL_REG_CACHE
    if _SKILL_REG_CACHE is None:
        _SKILL_REG_CACHE = SkillRegistry()
        _SKILL_REG_CACHE.load_file("data/skills.yaml")
    return _SKILL_REG_CACHE


def _char_obj(char_dict: dict) -> Character:
    return Character.from_db_dict(char_dict)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def _find_target_char(ctx: CommandContext, target_name: str):
    """
    Find a target character in the same room by partial name match.
    Returns (char_dict, Character) or (None, None).
    """
    room_id = ctx.session.character["room_id"]
    chars_in_room = await ctx.db.get_characters_in_room(room_id)
    target_name_lower = target_name.lower()
    for c in chars_in_room:
        c = dict(c)
        if c["id"] == ctx.session.character["id"]:
            continue
        if c["name"].lower().startswith(target_name_lower):
            return c, _char_obj(c)
    return None, None


async def _save_char_after_force(ctx: CommandContext, char_obj: Character):
    """Persist force-related fields back to DB after a power use."""
    char_dict = ctx.session.character
    # Wound level may have changed (accelerate_healing)
    char_dict["wound_level"] = char_obj.wound_level.value
    # DSP always persists
    char_dict["dark_side_points"] = char_obj.dark_side_points
    await ctx.db.save_character(
        char_dict["id"],
        wound_level=char_obj.wound_level.value,
        dark_side_points=char_obj.dark_side_points,
    )


async def _save_target_after_force(ctx: CommandContext,
                                    target_dict: dict, target_obj: Character):
    """Persist wound changes on a Force-affected target."""
    await ctx.db.save_character(
        target_dict["id"],
        wound_level=target_obj.wound_level.value,
    )


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

class ForceCommand(BaseCommand):
    key = "force"
    aliases = ["useforce"]
    help_text = (
        "Use a Force power. Usage: force <power name> [target]\n"
        "Examples: force control_pain\n"
        "          force telekinesis R2\n"
        "          force life_sense\n"
        "Type 'powers' to see available powers."
    )
    usage = "force <power> [target]"

    async def execute(self, ctx: CommandContext):
        char_dict = ctx.session.character
        char_obj = _char_obj(char_dict)

        # ── Force-sensitive check ──────────────────────────────────────────
        if not char_obj.force_sensitive:
            await ctx.session.send_line(
                "  You are not Force-sensitive. "
                "The Force flows through you but you cannot grasp it."
            )
            return

        # ── Parse args: power [target] ─────────────────────────────────────
        if not ctx.args:
            await ctx.session.send_line(
                "  Usage: force <power name> [target]\n"
                "  Type 'powers' to see available powers."
            )
            return

        parts = ctx.args.strip().split(None, 1)
        raw_key = parts[0]
        target_name = parts[1].strip() if len(parts) > 1 else None

        power = get_power(raw_key)
        if power is None:
            await ctx.session.send_line(
                f"  Unknown Force power '{raw_key}'. Type 'powers' to see options."
            )
            return

        # ── Skill check — does the char have the required skills? ──────────
        sr = _get_skill_reg()
        missing = []
        for skill in power.skills:
            pool = char_obj.get_attribute(skill)
            if pool.dice == 0 and pool.pips == 0:
                missing.append(skill.title())
        if missing:
            await ctx.session.send_line(
                f"  You lack the Force skill(s) needed: {', '.join(missing)}. "
                f"You must develop {', '.join(missing)} to use {power.name}."
            )
            return

        # ── Resolve target if needed ───────────────────────────────────────
        target_dict = None
        target_obj = None
        if power.target == "target":
            if not target_name:
                await ctx.session.send_line(
                    f"  '{power.name}' requires a target. "
                    f"Usage: force {raw_key} <target name>"
                )
                return
            target_dict, target_obj = await _find_target_char(ctx, target_name)
            if target_obj is None:
                await ctx.session.send_line(
                    f"  No one named '{target_name}' is here."
                )
                return

        # ── Resolve the power ──────────────────────────────────────────────
        result = resolve_force_power(
            power_key=power.key,
            char=char_obj,
            skill_reg=sr,
            target_char=target_obj,
        )

        # ── Announce to room ───────────────────────────────────────────────
        room_id = char_dict["room_id"]
        if result.success:
            color = ansi.BRIGHT_BLUE
            tag = "FORCE"
        else:
            color = ansi.DIM
            tag = "FORCE"

        # Personal result
        for line in result.narrative.split("\n"):
            await ctx.session.send_line(f"  {color}[{tag}]{ansi.RESET} {line}")

        # Broadcast to room
        if result.success:
            broadcast_msg = _build_room_broadcast(char_dict["name"], power, target_dict)
            await ctx.session_mgr.broadcast_to_room(
                room_id, broadcast_msg, exclude=ctx.session
            )

        # ── Persist changes ────────────────────────────────────────────────
        await _save_char_after_force(ctx, char_obj)
        if target_dict and target_obj and (
            result.damage_dealt > 0 or power.key == "affect_mind"
        ):
            await _save_target_after_force(ctx, target_dict, target_obj)

        # ── Pain suppression: store flag on session char for combat system ─
        if result.pain_suppressed:
            char_dict["_pain_suppressed"] = True
            log.info(f"[force] {char_dict['name']} activated control_pain")

        # ── Fall notification ──────────────────────────────────────────────
        if result.fall_check:
            fall_color = ansi.BRIGHT_RED if result.fall_failed else ansi.BRIGHT_YELLOW
            await ctx.session.send_line(
                f"  {fall_color}[DARK SIDE]{ansi.RESET} "
                + ("You have fallen to the dark side." if result.fall_failed
                   else "You resist the pull of the dark side.")
            )

        # ── Achievement hooks ─────────────────────────────────────────────
        try:
            if result.success and hasattr(ctx.session, "game_server"):
                from engine.achievements import on_force_power_used, on_dark_side_point
                await on_force_power_used(ctx.db, char_dict["id"], session=ctx.session)
                if result.dsp_gained if hasattr(result, "dsp_gained") else False:
                    await on_dark_side_point(ctx.db, char_dict["id"], session=ctx.session)
        except Exception as _e:
            log.debug("silent except in parser/force_commands.py:229: %s", _e, exc_info=True)


def _build_room_broadcast(char_name: str, power: ForcePower,
                           target_dict: dict | None) -> str:
    """Build the message other players in the room see."""
    target_str = f" on {target_dict['name']}" if target_dict else ""
    templates = {
        "accelerate_healing": f"  {char_name} closes their eyes and focuses. Their wounds visibly improve.",
        "control_pain":       f"  {char_name}'s expression hardens — they push past pain through sheer will.",
        "remain_conscious":   f"  {char_name} staggers but forces themselves upright through the Force.",
        "life_sense":         f"  {char_name}'s eyes go distant. They reach out with the Force.",
        "sense_force":        f"  {char_name} goes still, eyes half-closed, feeling something unseen.",
        "telekinesis":        f"  Objects {target_str} move by themselves — {char_name} extends a hand.",
        "injure_kill":        f"  {char_name} thrusts a hand forward. Dark energy crackles{target_str}!",
        "affect_mind":        f"  {char_name} stares intently at {target_dict['name'] if target_dict else 'nothing'}...",
    }
    return templates.get(power.key, f"  {char_name} reaches out with the Force{target_str}.")


class PowersCommand(BaseCommand):
    key = "+powers"
    aliases = ["powers", "forcepowers", "listpowers"]
    help_text = "List available Force powers for your character."
    usage = "powers"

    async def execute(self, ctx: CommandContext):
        char_obj = _char_obj(ctx.session.character)
        if not char_obj.force_sensitive:
            await ctx.session.send_line(
                "  You are not Force-sensitive and have no access to Force powers."
            )
            return

        available = list_powers_for_char(char_obj)
        if not available:
            await ctx.session.send_line(
                "  You are Force-sensitive but have no developed Force skills yet. "
                "Increase Control, Sense, or Alter to unlock powers."
            )
            return

        await ctx.session.send_line(
            f"\n  {ansi.BOLD}{ansi.BRIGHT_BLUE}Force Powers Available{ansi.RESET}"
        )
        await ctx.session.send_line(f"  {ansi.DIM}{'-' * 52}{ansi.RESET}")
        for line in format_power_list(available):
            await ctx.session.send_line(line)

        # Show locked powers (have wrong skills)
        locked = [p for p in POWERS.values() if p not in available]
        if locked:
            await ctx.session.send_line(
                f"\n  {ansi.DIM}Locked (requires further training):{ansi.RESET}"
            )
            for p in locked:
                skills_needed = " + ".join(s.title() for s in p.skills)
                await ctx.session.send_line(
                    f"  {ansi.DIM}  {p.name:<28s} (needs: {skills_needed}){ansi.RESET}"
                )
        await ctx.session.send_line("")


class ForceStatusCommand(BaseCommand):
    key = "+forcestatus"
    aliases = ["forcestatus", "fstatus", "forcesheet", "+fstatus"]
    help_text = "Display your Force attributes, points, and Dark Side status."
    usage = "forcestatus"

    async def execute(self, ctx: CommandContext):
        char_dict = ctx.session.character
        char_obj = _char_obj(char_dict)

        if not char_obj.force_sensitive:
            await ctx.session.send_line(
                "  You are not Force-sensitive."
            )
            return

        fp = char_dict.get("force_points", 0)
        dsp = char_dict.get("dark_side_points", 0)

        await ctx.session.send_line(
            f"\n  {ansi.BOLD}{ansi.BRIGHT_BLUE}Force Status — {char_obj.name}{ansi.RESET}"
        )
        await ctx.session.send_line(f"  {ansi.DIM}{'-' * 40}{ansi.RESET}")
        await ctx.session.send_line(
            f"  Control : {ansi.BRIGHT_YELLOW}{char_obj.control}{ansi.RESET}"
        )
        await ctx.session.send_line(
            f"  Sense   : {ansi.BRIGHT_YELLOW}{char_obj.sense}{ansi.RESET}"
        )
        await ctx.session.send_line(
            f"  Alter   : {ansi.BRIGHT_YELLOW}{char_obj.alter}{ansi.RESET}"
        )
        await ctx.session.send_line(f"  {ansi.DIM}{'-' * 40}{ansi.RESET}")
        await ctx.session.send_line(
            f"  Force Points : {ansi.BRIGHT_BLUE}{fp}{ansi.RESET}"
        )

        # DSP display
        if dsp == 0:
            dsp_display = f"{ansi.BRIGHT_GREEN}0 — Light Side{ansi.RESET}"
        elif dsp < 4:
            dsp_display = f"{ansi.BRIGHT_YELLOW}{dsp} — Touched by Darkness{ansi.RESET}"
        elif dsp < 6:
            dsp_display = f"{ansi.BRIGHT_RED}{dsp} — Danger Zone{ansi.RESET}"
        else:
            dsp_display = f"{ansi.BRIGHT_RED}{dsp} — FALLEN{ansi.RESET}"
        await ctx.session.send_line(f"  Dark Side Pts: {dsp_display}")

        # Available powers
        available = list_powers_for_char(char_obj)
        await ctx.session.send_line(
            f"\n  Powers available: {ansi.BRIGHT_CYAN}{len(available)}{ansi.RESET} "
            f"of {len(POWERS)}  (type 'powers' for details)"
        )
        await ctx.session.send_line("")


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

def register_force_commands(registry):
    """Register Force Power commands."""
    cmds = [
        ForceCommand(),
        PowersCommand(),
        ForceStatusCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)
