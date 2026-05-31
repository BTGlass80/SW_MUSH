# -*- coding: utf-8 -*-
"""
parser/player_building_commands.py — `+building` parser surface
(SYN.9, 2026-05-25).

One dispatch command with 7 subcommands for the player-constructed
building system. Thin wrapper over `engine.buildings`; all gating
+ state mutation lives in the engine.

NOTE: This file is separate from `parser/building_commands.py`
(which contains admin/builder room-construction commands — the
two are unrelated systems with a name collision).

Subcommands:
  * `+building construct <category>` — start construction
  * `+building demolish <id>` — owner demolishes (25% refund)
  * `+building evict <id>` — mayor evicts (2-day notice)
  * `+building list` — list buildings in current room
  * `+building inspect <id>` — show building details
  * `+building store <id> <item>` — owner stores item in residence
  * `+building take <id> <item>` — owner takes item from residence
"""
from __future__ import annotations

import logging
import time

from parser.commands import AccessLevel, BaseCommand, CommandContext

log = logging.getLogger(__name__)


class PlayerBuildingCommand(BaseCommand):
    """Dispatch command for the `+building` subcommand family
    (player-constructed buildings per SYN.9)."""

    key = "+building"
    aliases = ["+bldg", "+pbuild"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Manage buildings on city-claimed wilderness landmarks.\n"
        "\n"
        "  SUBCOMMANDS:\n"
        "    +building construct <category>  Start construction\n"
        "    +building demolish <id>         Owner demolish (25% refund)\n"
        "    +building evict <id>            Mayor evict (2-day notice)\n"
        "    +building list                  List buildings in current room\n"
        "    +building inspect <id>          Show building details\n"
        "    +building store <id> <item>     Store item in residence\n"
        "    +building take <id> <item>      Take item from residence\n"
        "\n"
        "  CATEGORIES:\n"
        "    residence        Personal storage (50-item cap)\n"
        "    crafting_station +1D bonus to crafts done here\n"
        "    commerce_stall   Vendor with 50/50 city tax split\n"
        "    garrison_annex   2 additional defending NPCs\n"
        "    cultural_hall    +1 daily CP for citizens here\n"
        "\n"
        "  REQUIREMENTS:\n"
        "  - Rank 3+ in city's owning org to construct.\n"
        "  - Materials in inventory + credits in wallet.\n"
        "  - Landmark must have a free building slot.\n"
        "  - Force-resonant sites cannot host buildings.\n"
        "\n"
        "  Construction takes 24 real-time hours.\n"
        "  Owner demolish refunds 25%% of materials.\n"
        "  Same-owner rebuild gets 10%% material discount.\n"
        "\n"
        "EXAMPLES:\n"
        "  +building construct residence\n"
        "  +building list\n"
        "  +building inspect 5\n"
        "  +building demolish 5"
    )
    usage = "+building <subcommand> [args]"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game.")
            return

        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line(
                "  Usage: +building <subcommand> [args]\n"
                "  Subcommands: construct, demolish, evict, list, "
                "inspect, store, take."
            )
            return

        parts = args.split(None, 2)
        sub = parts[0].lower()
        rest = parts[1:] if len(parts) > 1 else []

        handlers = {
            "construct": self._handle_construct,
            "demolish": self._handle_demolish,
            "evict": self._handle_evict,
            "list": self._handle_list,
            "inspect": self._handle_inspect,
            "store": self._handle_store,
            "take": self._handle_take,
        }
        handler = handlers.get(sub)
        if not handler:
            await ctx.session.send_line(
                f"  Unknown subcommand: '{sub}'. "
                f"Known: {', '.join(sorted(handlers.keys()))}."
            )
            return

        try:
            await handler(ctx, char, rest)
        except Exception:
            log.exception("[building] %s raised", sub)
            await ctx.session.send_line(
                "  Something disrupts the construction office. "
                "Try again."
            )

    # ── Subcommand handlers ──────────────────────────────────────

    async def _handle_construct(
        self, ctx: CommandContext, char: dict, rest: list,
    ) -> None:
        if not rest:
            await ctx.session.send_line(
                "  Usage: +building construct <category>\n"
                "  Categories: residence, crafting_station, "
                "commerce_stall, garrison_annex, cultural_hall."
            )
            return
        category = rest[0].strip().lower()
        room_id = char.get("room_id")
        if not room_id:
            await ctx.session.send_line("  You are nowhere.")
            return

        from engine.buildings import construct_building
        result = await construct_building(
            ctx.db, char, category, int(room_id),
        )
        await ctx.session.send_line(
            f"  {result.get('msg', '(silent)')}"
        )

    async def _handle_demolish(
        self, ctx: CommandContext, char: dict, rest: list,
    ) -> None:
        if not rest:
            await ctx.session.send_line(
                "  Usage: +building demolish <id>"
            )
            return
        try:
            bid = int(rest[0])
        except ValueError:
            await ctx.session.send_line(
                f"  '{rest[0]}' is not a valid building id."
            )
            return

        from engine.buildings import demolish_building
        result = await demolish_building(ctx.db, char, bid)
        await ctx.session.send_line(
            f"  {result.get('msg', '(silent)')}"
        )

    async def _handle_evict(
        self, ctx: CommandContext, char: dict, rest: list,
    ) -> None:
        if not rest:
            await ctx.session.send_line(
                "  Usage: +building evict <id>"
            )
            return
        try:
            bid = int(rest[0])
        except ValueError:
            await ctx.session.send_line(
                f"  '{rest[0]}' is not a valid building id."
            )
            return

        from engine.buildings import evict_building
        result = await evict_building(ctx.db, char, bid)
        await ctx.session.send_line(
            f"  {result.get('msg', '(silent)')}"
        )

    async def _handle_list(
        self, ctx: CommandContext, char: dict, rest: list,
    ) -> None:
        room_id = char.get("room_id")
        if not room_id:
            await ctx.session.send_line("  You are nowhere.")
            return

        from engine.buildings import (
            list_buildings_in_room, get_slot_capacity,
            BUILDING_CATEGORIES,
        )
        cap = await get_slot_capacity(ctx.db, int(room_id))
        buildings = await list_buildings_in_room(ctx.db, int(room_id))

        if cap == 0 and not buildings:
            await ctx.session.send_line(
                "  This location cannot host buildings (not a "
                "city-claimed landmark)."
            )
            return

        await ctx.session.send_line(
            f"  \033[1;36mBuildings here:\033[0m "
            f"({len(buildings)}/{cap} slots used)"
        )
        if not buildings:
            await ctx.session.send_line(
                "  \033[2m(No buildings yet. Use "
                "'+building construct <category>' to start one.)\033[0m"
            )
            return

        now = time.time()
        for b in buildings:
            cat_def = BUILDING_CATEGORIES.get(b["category"], {})
            display = cat_def.get("display_name", b["category"])
            status = b["status"]
            owner_id = b["owner_char_id"]
            line = f"  #{b['id']}  {display}  (owner: char {owner_id})"
            if status == "under_construction":
                secs_left = int(float(b["completion_ts"]) - now)
                hrs = max(0, secs_left // 3600)
                mins = max(0, (secs_left % 3600) // 60)
                line += (
                    f"  \033[33m[under construction — "
                    f"{hrs}h {mins}m left]\033[0m"
                )
            elif status == "operational":
                if b.get("evict_after_ts"):
                    ev_left = int(float(b["evict_after_ts"]) - now)
                    line += (
                        f"  \033[31m[EVICTION NOTICE — "
                        f"{max(0, ev_left // 3600)}h left]\033[0m"
                    )
                else:
                    line += "  \033[32m[operational]\033[0m"
            else:
                line += f"  [{status}]"
            await ctx.session.send_line(line)

    async def _handle_inspect(
        self, ctx: CommandContext, char: dict, rest: list,
    ) -> None:
        if not rest:
            await ctx.session.send_line(
                "  Usage: +building inspect <id>"
            )
            return
        try:
            bid = int(rest[0])
        except ValueError:
            await ctx.session.send_line(
                f"  '{rest[0]}' is not a valid building id."
            )
            return

        from engine.buildings import (
            get_building, BUILDING_CATEGORIES,
        )
        b = await get_building(ctx.db, bid)
        if not b:
            await ctx.session.send_line(f"  No building #{bid}.")
            return

        cat_def = BUILDING_CATEGORIES.get(b["category"], {})
        display = cat_def.get("display_name", b["category"])
        desc = cat_def.get("description", "")
        effect = cat_def.get("effect_summary", "")

        await ctx.session.send_line(
            f"  \033[1;36mBuilding #{b['id']}: {display}\033[0m"
        )
        await ctx.session.send_line(f"  Category: {b['category']}")
        await ctx.session.send_line(f"  Owner (char id): {b['owner_char_id']}")
        if b.get("owning_org_id"):
            await ctx.session.send_line(
                f"  Owning org id: {b['owning_org_id']}"
            )
        await ctx.session.send_line(f"  Status: {b['status']}")
        await ctx.session.send_line(f"  Room: {b['room_id']}")
        if desc:
            await ctx.session.send_line(f"  \033[2m{desc}\033[0m")
        if effect:
            await ctx.session.send_line(f"  Effect: {effect}")

        now = time.time()
        if b["status"] == "under_construction":
            secs_left = int(float(b["completion_ts"]) - now)
            hrs = max(0, secs_left // 3600)
            mins = max(0, (secs_left % 3600) // 60)
            await ctx.session.send_line(
                f"  Construction time remaining: {hrs}h {mins}m"
            )
        elif b.get("evict_after_ts"):
            ev_left = int(float(b["evict_after_ts"]) - now)
            await ctx.session.send_line(
                f"  \033[31mUnder eviction notice — "
                f"{max(0, ev_left // 3600)}h until eviction.\033[0m"
            )

    async def _handle_store(
        self, ctx: CommandContext, char: dict, rest: list,
    ) -> None:
        if len(rest) < 2:
            await ctx.session.send_line(
                "  Usage: +building store <id> <item_name>"
            )
            return
        try:
            bid = int(rest[0])
        except ValueError:
            await ctx.session.send_line(
                f"  '{rest[0]}' is not a valid building id."
            )
            return
        item_key = rest[1].strip()

        from engine.buildings import residence_store_item
        result = await residence_store_item(
            ctx.db, char, bid, item_key,
        )
        await ctx.session.send_line(
            f"  {result.get('msg', '(silent)')}"
        )

    async def _handle_take(
        self, ctx: CommandContext, char: dict, rest: list,
    ) -> None:
        if len(rest) < 2:
            await ctx.session.send_line(
                "  Usage: +building take <id> <item_name>"
            )
            return
        try:
            bid = int(rest[0])
        except ValueError:
            await ctx.session.send_line(
                f"  '{rest[0]}' is not a valid building id."
            )
            return
        item_key = rest[1].strip()

        from engine.buildings import residence_take_item
        result = await residence_take_item(
            ctx.db, char, bid, item_key,
        )
        await ctx.session.send_line(
            f"  {result.get('msg', '(silent)')}"
        )


def register_player_building_commands(registry) -> None:
    """Register the +building dispatch command. Called from
    ``server/game_server.py`` during bootstrap."""
    registry.register(PlayerBuildingCommand())
