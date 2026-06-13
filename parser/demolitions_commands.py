# -*- coding: utf-8 -*-
"""
parser/demolitions_commands.py — the `breach` command
(CRAFT.mines_breaching_split, breaching half — 2026-06-13).

`breach <target>` blows open a sealed obstacle (a `breachable` room
object) with a single-use breaching charge and a Demolitions skill check
vs the obstacle's difficulty. Safe by design — breaches obstacles, not
people (no blast-on-players); placed proximity mines are a separate
deferred system. The engine core is engine/breaching.py::attempt_breach;
this is the thin parser front end (mirrors ForceDoorCommand).
"""
from __future__ import annotations

import logging

from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


class BreachCommand(BaseCommand):
    key = "breach"
    aliases: list = []
    help_text = (
        "Blow open a sealed obstacle with a breaching charge.\n"
        "\n"
        "USAGE:\n"
        "  breach <obstacle>   Set a breaching charge on a sealed door /\n"
        "                      gate / barrier and blow it (Demolitions check\n"
        "                      vs the obstacle's difficulty). Consumes one\n"
        "                      breaching charge whether or not it succeeds.\n"
        "\n"
        "Breaching charges are crafted (Demolitions). They breach obstacles,\n"
        "not people — there's no blast on bystanders."
    )
    usage = "breach <obstacle>"

    async def execute(self, ctx: CommandContext):
        if not ctx.session.is_in_game or not ctx.session.character:
            await ctx.session.send_line(
                "  You must be in the game to breach.")
            return
        char = ctx.session.character
        target = (ctx.args or "").strip()

        try:
            from engine.breaching import attempt_breach
        except ImportError:
            await ctx.session.send_line("  Breaching is unavailable.")
            return

        result = await attempt_breach(ctx.db, char, target)
        await ctx.session.send_line(result["msg"])

        if not result.get("ok") or not result.get("breached"):
            return

        # Persist the consumed charge (attempt_breach mutated the DB
        # inventory; refresh the in-memory char so later reads agree) and
        # broadcast the blast to the room.
        try:
            await ctx.session_mgr.broadcast_to_room(
                char["room_id"],
                "  \033[1;33mA breaching charge detonates with a "
                "concussive crack!\033[0m",
                exclude=ctx.session,
            )
        except Exception:
            log.debug("[breach] room broadcast failed", exc_info=True)


def register_demolitions_commands(registry) -> None:
    """Register the `breach` command. Called from server/game_server.py."""
    registry.register(BreachCommand())
