# -*- coding: utf-8 -*-
"""
parser/region_commands.py — `+region` parser surface (SYN.10,
2026-05-25).

One standalone command:

  ``+region`` (no args) — show the region the player is currently in.
  ``+region <slug>`` — show the named region (any wilderness region).

Thin wrapper over ``engine.territory_display.get_region_look_block``.
The same block is auto-included in wilderness `look` output via
``parser/builtin_commands.py::LookCommand._look_wilderness``; this
command makes the surface explicit and queryable for any region.

UI pivot: rendering is via ``get_region_look_block`` (CLI text);
structured data via ``get_region_data_block``. The data dict is
the contract for the upcoming web HUD.
"""
from __future__ import annotations

import logging

from parser.commands import AccessLevel, BaseCommand, CommandContext

log = logging.getLogger(__name__)


class RegionCommand(BaseCommand):
    """Show the region look block for the caller's current region
    or for a named region."""

    key = "+region"
    aliases = ["+reg"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Show the region info block — ownership, influence, "
        "weekly resource quality, and active contests.\n"
        "\n"
        "  No args: show your current region (you must be in a "
        "wilderness region or at a wilderness sentinel).\n"
        "  <slug>:  show the named wilderness region (e.g. "
        "'dune_sea', 'coruscant_underworld').\n"
        "\n"
        "  The same block auto-includes in 'look' when you are "
        "in a wilderness region.\n"
        "\n"
        "EXAMPLES:\n"
        "  +region\n"
        "  +region dune_sea\n"
        "  +region coruscant_underworld"
    )
    usage = "+region [slug]"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game.")
            return

        args = (ctx.args or "").strip()
        slug = None

        if args:
            slug = args.lower().split()[0]
        else:
            # Resolve caller's current region.
            try:
                from engine.wilderness_movement import (
                    get_wilderness_coords,
                )
                coords = get_wilderness_coords(char)
                if coords:
                    slug = coords[0]
            except Exception:
                log.debug("[+region] wilderness coord lookup failed",
                          exc_info=True)
            if not slug:
                # Fall back to room's wilderness_region_id.
                room_id = char.get("room_id")
                if room_id:
                    try:
                        from engine.territory import _resolve_room_region
                        region_slug, _zid = await _resolve_room_region(
                            ctx.db, int(room_id),
                        )
                        slug = region_slug
                    except Exception:
                        log.debug("[+region] room region lookup failed",
                                  exc_info=True)

        if not slug:
            await ctx.session.send_line(
                "  Usage: +region [slug]\n"
                "  Region info is only available in wilderness "
                "regions. You don't seem to be in one — pass a "
                "slug explicitly (e.g. '+region dune_sea')."
            )
            return

        # Render and surface.
        from engine.territory_display import get_region_look_block
        viewing_org = char.get("faction_id")
        if viewing_org == "independent":
            viewing_org = None

        try:
            lines = await get_region_look_block(
                ctx.db, slug, viewing_org_code=viewing_org, ansi=True,
            )
        except Exception:
            log.exception("[+region] get_region_look_block raised")
            await ctx.session.send_line(
                "  The astrogation systems are offline. Try again."
            )
            return

        await ctx.session.send_line("")
        for line in lines:
            await ctx.session.send_line(line)


def register_region_commands(registry) -> None:
    """Register the +region command. Called from
    ``server/game_server.py`` during bootstrap."""
    registry.register(RegionCommand())
