# -*- coding: utf-8 -*-
"""
parser/harvest_command.py — the ``harvest`` command (SYN.6.a, 2026-05-25).

Per ``contestable_wilderness_design_v2.md`` §2.5.2 + §2.5.3.

Thin wrapper over ``engine.harvest.perform_harvest``. The engine
module owns the mechanic; this surface owns:

  * Session/character resolution.
  * Location resolution (which room is the character in?).
  * Result-dict → human-readable message translation.
  * Web-client metadata emission (for the "requires web client"
    rule per arch v50: nothing here is web-only, so Telnet sees
    the full message).

The command takes no arguments. Optional future surface (deferred):
  * ``harvest /survey`` — preview the yield table for the current
    region without consuming the cooldown.

Per architecture invariant §4.25 (wilderness-only influence): no
explicit zone-type gate is needed here. ``engine.harvest`` resolves
the room via ``_resolve_room_region`` and short-circuits to a
"not a harvest node" message if the room is city-map (returns
``region_slug=None``).
"""
from __future__ import annotations

import logging

from parser.commands import AccessLevel, BaseCommand, CommandContext

log = logging.getLogger(__name__)


class HarvestCommand(BaseCommand):
    """The ``harvest`` command. Wilderness-only, 30-min per-region
    cooldown, Survival skill check, credits + resource stacks."""

    key = "harvest"
    aliases = []
    access_level = AccessLevel.PLAYER
    help_text = (
        "Harvest wilderness resources at your current location.\n"
        "\n"
        "  Runs a Survival skill check. On success, awards credits\n"
        "  + resource stacks (metal, organic, chemical, rare) at a\n"
        "  quality determined by your roll and the region's current\n"
        "  yield.\n"
        "\n"
        "  Yields scale with the security tier (Contested vs\n"
        "  Lawless) and the owning faction's influence in the\n"
        "  parent zone (Foothold / Dominant / Control). If you\n"
        "  harvest in a region owned by an org you don't belong to,\n"
        "  15% of the credits route to that org's treasury — the\n"
        "  cost of doing business on someone else's turf.\n"
        "\n"
        "  30-minute personal cooldown per region. Wilderness only;\n"
        "  city-map rooms are not harvest nodes.\n"
        "\n"
        "EXAMPLES:\n"
        "  harvest"
    )
    usage = "harvest"

    async def execute(self, ctx: CommandContext) -> None:
        # ── Resolve character + location ────────────────────────────────────
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to harvest."
            )
            return

        # Space context: aboard a ship in open space, `harvest` means
        # wildspace faction caches (space_wildspace_design_v1 §4.3). The
        # space handler returns True when it took the command; otherwise
        # fall through to ground wilderness harvest. One verb, no
        # colliding second registration (extend, don't add).
        try:
            from parser.space_commands import handle_space_harvest
            if await handle_space_harvest(ctx):
                return
        except Exception:
            log.exception("[harvest] space dispatch raised; falling back to ground")

        room_id = char.get("room_id")
        if not room_id:
            await ctx.session.send_line(
                "  You aren't anywhere a harvest could happen."
            )
            return

        # ── Delegate to engine module ───────────────────────────────────────
        try:
            from engine.harvest import perform_harvest
            result = await perform_harvest(ctx.db, char, int(room_id))
        except Exception:
            log.exception("[harvest] perform_harvest raised unexpectedly")
            await ctx.session.send_line(
                "  Something went wrong with the harvest. Try again."
            )
            return

        # ── Surface result ──────────────────────────────────────────────────
        msg = result.get("msg") or "Harvest complete."
        await ctx.session.send_line(f"  {msg}")

        # On success-with-payout, emit a brief skill-feedback line so
        # the player can see how their margin shaped the outcome.
        # This is parallel to how skill_checks surfaces in combat
        # (engine/combat.py emits per-attack roll lines).
        if result.get("ok") and (
            result.get("credits_kept") or result.get("resource_stacks")
        ):
            margin = result.get("margin", 0)
            pool = result.get("skill_pool", "?")
            roll = result.get("skill_roll", 0)
            await ctx.session.send_line(
                f"  [Survival {pool}: rolled {roll} "
                f"vs DC 6, margin +{margin}]"
            )


def register_harvest_command(registry) -> None:
    """Register the ``harvest`` command. Called from
    ``server/game_server.py`` during bootstrap."""
    registry.register(HarvestCommand())
