# -*- coding: utf-8 -*-
"""
parser/ship_crew_commands.py — flight-authorization roster (Drop 3b.1).

Companion to the ship-control gate in ``parser/space_commands.py``
(``PilotCommand`` / ``LaunchCommand``). Under the "open boarding, gated
control" model, the **owner** uses ``+shipcrew`` to authorize co-pilots; anyone
on the roster (plus the owner) may take the pilot seat and launch.

Commands:
    +shipcrew                  — list who is cleared to fly the ship you're aboard
    +shipcrew add <name>       — owner authorizes a character
    +shipcrew remove <name>    — owner de-authorizes a character

Scope is the ship whose bridge you are standing in (``get_ship_by_bridge``).
Only the owner may modify the roster.
"""

import json
import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.ship_access import (
    get_authorized_pilots, add_authorized_pilot, remove_authorized_pilot,
)
from server import ansi

log = logging.getLogger(__name__)


def _as_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _parse_systems(ship) -> dict:
    raw = ship.get("systems", "{}")
    if isinstance(raw, str):
        try:
            return json.loads(raw) or {}
        except Exception:
            log.warning("[shipcrew] systems parse failed for ship %s",
                        ship.get("id"), exc_info=True)
            return {}
    return raw or {}


class ShipCrewCommand(BaseCommand):
    key = "+shipcrew"
    aliases = ["shipcrew", "+permit"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Manage who is cleared to fly your ship (owner only for changes).\n"
        "\n"
        "  +shipcrew                — list cleared pilots for the ship you're aboard\n"
        "  +shipcrew add <name>     — authorize a co-pilot\n"
        "  +shipcrew remove <name>  — revoke a co-pilot\n"
        "\n"
        "Anyone may board a docked ship, but only the owner and authorized\n"
        "crew may take the pilot seat and launch."
    )
    usage = "+shipcrew  |  +shipcrew add <name>  |  +shipcrew remove <name>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in-game.")
            return
        ship = await ctx.db.get_ship_by_bridge(char.get("room_id"))
        if not ship:
            await ctx.session.send_line(
                "  Board the ship you want to manage, then use +shipcrew.")
            return

        args = (ctx.args or "").strip()
        parts = args.split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub in ("add", "remove", "rm", "revoke", "del"):
            await self._modify(ctx, char, ship, sub, rest)
            return

        await self._show_roster(ctx, char, ship)

    async def _modify(self, ctx, char, ship, sub, rest):
        # Owner-only.
        if _as_int(char["id"]) != _as_int(ship.get("owner_id")):
            await ctx.session.send_line(
                "  Only the ship's owner can change its crew roster.")
            return
        if not rest:
            await ctx.session.send_line(f"  Usage: +shipcrew {sub} <name>")
            return
        target = await ctx.db.get_character_by_name(rest)
        if not target:
            await ctx.session.send_line(f"  No character named '{rest}'.")
            return
        tid = target["id"]
        if _as_int(tid) == _as_int(ship.get("owner_id")):
            await ctx.session.send_line(
                "  The owner is always cleared to fly — no need to add them.")
            return

        systems = _parse_systems(ship)
        if sub == "add":
            if not add_authorized_pilot(systems, tid):
                await ctx.session.send_line(
                    f"  {target['name']} is already cleared to fly {ship['name']}.")
                return
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            await ctx.session.send_line(ansi.success(
                f"  {target['name']} is now cleared to fly {ship['name']}."))
        else:
            if not remove_authorized_pilot(systems, tid):
                await ctx.session.send_line(
                    f"  {target['name']} isn't on {ship['name']}'s crew roster.")
                return
            await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
            await ctx.session.send_line(ansi.success(
                f"  {target['name']} is no longer cleared to fly {ship['name']}."))

    async def _show_roster(self, ctx, char, ship):
        systems = _parse_systems(ship)
        ids = get_authorized_pilots(systems)
        oi = _as_int(ship.get("owner_id"))

        lines = [ansi.bold(f"  Flight authorization — {ship['name']}")]
        if not oi:
            lines.append("    (unowned hull — anyone aboard may fly it)")
        else:
            owner = await ctx.db.get_character(oi)
            lines.append(f"    {(owner['name'] if owner else '#'+str(oi))} (owner)")
            if ids:
                for cid in ids:
                    c = await ctx.db.get_character(cid)
                    lines.append(f"    {c['name'] if c else '#'+str(cid)}")
            else:
                lines.append("    (no additional crew authorized)")
            if _as_int(char["id"]) == oi:
                lines.append("  +shipcrew add <name>  /  +shipcrew remove <name>")
        await ctx.session.send_line("\n".join(lines))


def register_ship_crew_commands(registry):
    """Register the +shipcrew flight-authorization command (Drop 3b.1)."""
    registry.register(ShipCrewCommand())
    log.info("[shipcrew] flight-authorization command registered")
