# -*- coding: utf-8 -*-
"""parser/restraints_commands.py — the restraint verbs (CRAFT.HOOK.restraints).

Thin parser front ends over engine/restraints.py (mirrors
parser/demolitions_commands.py — the engine does the work, the parser handles
I/O + room broadcast):

  cuff <target>     Bind a defeated or willing PC with binders (consumes one).
  uncuff <target>   Release someone you cuffed (or as admin).
  escape            Struggle free of your binders (Strength check).
  allowrestrain on|off   Opt in/out of being restrained (willing captures / RP).

PvP norm (Brian): a PC may cuff another PC only if DEFEATED (incapacitated) or
CONSENTING; never a healthy unwilling PC. v1 cuffs PCs only.
"""
from __future__ import annotations

import logging

from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


def _char_and_session(ctx: CommandContext):
    """Return char or None (after sending the not-in-game line)."""
    if not ctx.session.is_in_game or not ctx.session.character:
        return None
    return ctx.session.character


class CuffCommand(BaseCommand):
    key = "cuff"
    aliases = ["restrain", "bind"]
    help_text = (
        "Bind a subdued or willing target with binders.\n"
        "\n"
        "USAGE:\n"
        "  cuff <target>   Snap binders on a player who has been DEFEATED\n"
        "                  (incapacitated in combat) or who has opted in via\n"
        "                  `allowrestrain on`. Consumes one pair of binders.\n"
        "\n"
        "You can't cuff a healthy, unwilling player. A cuffed prisoner can't\n"
        "move, attack, or change gear until they break free (escape) or you\n"
        "release them (uncuff). Binders are crafted (Security)."
    )
    usage = "cuff <target>"

    async def execute(self, ctx: CommandContext):
        char = _char_and_session(ctx)
        if char is None:
            await ctx.session.send_line("  You must be in the game to do that.")
            return
        from engine.restraints import attempt_cuff
        result = await attempt_cuff(
            ctx.db, char, ctx.args or "", session_mgr=ctx.session_mgr)
        await ctx.session.send_line(result["msg"])
        if result.get("ok"):
            try:
                await ctx.session_mgr.broadcast_to_room(
                    char["room_id"],
                    f"  \033[1;33m{char.get('name', 'Someone')} restrains "
                    f"{result['target_name']} with binders.\033[0m",
                    exclude=ctx.session,
                )
            except Exception:
                log.debug("[cuff] room broadcast failed", exc_info=True)


class UncuffCommand(BaseCommand):
    key = "uncuff"
    aliases = ["unbind", "release"]
    help_text = (
        "Release a restrained player.\n"
        "\n"
        "USAGE:\n"
        "  uncuff <target>   Free someone you cuffed. Only the captor (or an\n"
        "                    admin) can release a prisoner."
    )
    usage = "uncuff <target>"

    async def execute(self, ctx: CommandContext):
        char = _char_and_session(ctx)
        if char is None:
            await ctx.session.send_line("  You must be in the game to do that.")
            return
        is_admin = bool(ctx.session.account.get("is_admin", 0)) \
            if getattr(ctx.session, "account", None) else False
        from engine.restraints import attempt_uncuff
        result = await attempt_uncuff(
            ctx.db, char, ctx.args or "",
            session_mgr=ctx.session_mgr, is_admin=is_admin)
        await ctx.session.send_line(result["msg"])
        if result.get("ok"):
            try:
                await ctx.session_mgr.broadcast_to_room(
                    char["room_id"],
                    f"  {char.get('name', 'Someone')} releases "
                    f"{result['target_name']} from their binders.",
                    exclude=ctx.session,
                )
            except Exception:
                log.debug("[uncuff] room broadcast failed", exc_info=True)


class EscapeCommand(BaseCommand):
    key = "escape"
    aliases = ["struggle"]
    help_text = (
        "Struggle free of binders.\n"
        "\n"
        "USAGE:\n"
        "  escape   Attempt to break out of your binders (a hard Strength\n"
        "           effort). One attempt per command."
    )
    usage = "escape"

    async def execute(self, ctx: CommandContext):
        char = _char_and_session(ctx)
        if char is None:
            await ctx.session.send_line("  You must be in the game to do that.")
            return
        from engine.restraints import attempt_escape_action
        result = await attempt_escape_action(ctx.db, char)
        await ctx.session.send_line(result["msg"])
        if result.get("escaped"):
            try:
                await ctx.session_mgr.broadcast_to_room(
                    char["room_id"],
                    f"  {char.get('name', 'Someone')} wrenches free of "
                    f"their binders!",
                    exclude=ctx.session,
                )
            except Exception:
                log.debug("[escape] room broadcast failed", exc_info=True)


class AllowRestrainCommand(BaseCommand):
    key = "allowrestrain"
    aliases = ["consentrestrain"]
    help_text = (
        "Opt in or out of being restrained.\n"
        "\n"
        "USAGE:\n"
        "  allowrestrain on    Let others cuff you (willing captures / RP).\n"
        "  allowrestrain off   Default — you can only be cuffed once subdued.\n"
        "\n"
        "Being DEFEATED in combat always allows cuffing regardless of this."
    )
    usage = "allowrestrain on|off"

    async def execute(self, ctx: CommandContext):
        char = _char_and_session(ctx)
        if char is None:
            await ctx.session.send_line("  You must be in the game to do that.")
            return
        arg = (ctx.args or "").strip().lower()
        if arg not in ("on", "off"):
            await ctx.session.send_line("  Usage: allowrestrain on|off")
            return
        from engine.restraints import set_consent_action
        result = await set_consent_action(ctx.db, char, arg == "on")
        await ctx.session.send_line(result["msg"])


def register_restraints_commands(registry) -> None:
    """Register the restraint verbs. Called from server/game_server.py."""
    registry.register(CuffCommand())
    registry.register(UncuffCommand())
    registry.register(EscapeCommand())
    registry.register(AllowRestrainCommand())
