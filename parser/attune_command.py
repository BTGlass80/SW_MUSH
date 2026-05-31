# -*- coding: utf-8 -*-
"""
parser/attune_command.py — the ``attune`` command (SYN.6.c, 2026-05-25).

Per ``contestable_wilderness_design_v2.md`` §2.5.6: Jedi PC at a
force-resonant wilderness landmark spends a Knowledge skill check
attempt to acquire 1 ``kyber_shard_minor`` resource stack at q75-95.

Thin wrapper over ``engine.kyber_attunement.attune_to_landmark``. The
engine module owns all the validation, gating, and reward logic.
This surface is character + room resolution + result-line emission.

Web-first per arch v50: this surface is text-mode, no web-only fields.
Telnet sees the same message stream as the web client.
"""
from __future__ import annotations

import logging

from parser.commands import AccessLevel, BaseCommand, CommandContext

log = logging.getLogger(__name__)


class AttuneCommand(BaseCommand):
    """The ``attune`` command. Force-sensitive PC at a force-resonant
    wilderness landmark performs a meditation/knowledge check; on
    success, acquires 1 minor kyber shard at q75-95 quality."""

    key = "attune"
    aliases = []
    access_level = AccessLevel.PLAYER
    help_text = (
        "Attune to a force-resonant wilderness landmark to draw out\n"
        "a minor kyber shard.\n"
        "\n"
        "  Force-sensitive characters only. Must be standing at a\n"
        "  landmark flagged 'force resonant' (places like the Anchor\n"
        "  Stones, the Ruined Obelisk, the Whispering Caves — any\n"
        "  wilderness landmark where the Force runs near the\n"
        "  surface).\n"
        "\n"
        "  Rolls Scholar (or Willpower, or raw Knowledge) vs\n"
        "  Moderate difficulty. On success, you acquire 1\n"
        "  kyber_shard_minor at quality 75-95, scaling with your\n"
        "  margin. The shard is a T5 crafting component — a\n"
        "  master-crafted lightsaber requires one.\n"
        "\n"
        "  24-hour personal cooldown per landmark. Each force-\n"
        "  resonant site yields one shard per attempt, then the\n"
        "  resonance settles.\n"
        "\n"
        "EXAMPLES:\n"
        "  attune"
    )
    usage = "attune"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to attune to anything."
            )
            return

        room_id = char.get("room_id")
        if not room_id:
            await ctx.session.send_line(
                "  You aren't anywhere a kyber resonance could be felt."
            )
            return

        try:
            from engine.kyber_attunement import attune_to_landmark
            result = await attune_to_landmark(ctx.db, char, int(room_id))
        except Exception:
            log.exception("[attune] attune_to_landmark raised unexpectedly")
            await ctx.session.send_line(
                "  Something disrupts your concentration. Try again."
            )
            return

        msg = result.get("msg") or "You attune."
        await ctx.session.send_line(f"  {msg}")

        # On a meaningful success (shard awarded), surface the
        # skill roll for player feedback — same pattern as harvest.
        if result.get("ok") and result.get("quality") is not None:
            margin = result.get("margin", 0)
            skill = result.get("skill_used", "?")
            roll = result.get("skill_roll", 0)
            await ctx.session.send_line(
                f"  [{skill} roll: {roll} vs DC 11, margin +{margin}]"
            )


def register_attune_command(registry) -> None:
    """Register the ``attune`` command. Called from
    ``server/game_server.py`` during bootstrap."""
    registry.register(AttuneCommand())
