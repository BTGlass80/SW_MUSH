# -*- coding: utf-8 -*-
"""
parser/faction_commands.py — Faction and guild commands for SW_MUSH.

Commands:
  faction             — show your faction status
  faction list        — list all factions
  faction join <code> — join a faction
  faction leave       — leave current faction
  faction info <code> — show faction details and ranks

  guild               — show your guild memberships
  guild list          — list all guilds
  guild join <code>   — join a guild (max 3)
  guild leave <code>  — leave a guild
"""
import logging
from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


class FactionCommand(BaseCommand):
    key = "faction"
    aliases = ["+faction", "fac"]
    help_text = (
        "Manage your faction membership.\n"
        "\n"
        "USAGE:\n"
        "  faction            — show your current faction and rank\n"
        "  faction list       — show all factions\n"
        "  faction join <f>   — join a faction (code from 'faction list')\n"
        "  faction leave      — leave your current faction\n"
        "  faction info <f>   — show faction details and rank table\n"
        "\n"
        "You can only belong to ONE faction at a time.\n"
        "Switching factions has a 7-day cooldown."
    )
    usage = "faction [list | join <code> | leave | info <code>]"

    async def execute(self, ctx: CommandContext):
        from engine.organizations import (
            join_faction, leave_faction, format_faction_status,
            format_faction_list,
        )

        char = ctx.session.character
        args = (ctx.args or "").strip().lower()
        parts = args.split(None, 1)
        sub = parts[0] if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        # ── faction (no args) ──
        if not sub:
            await ctx.session.send_line(await format_faction_status(char, ctx.db))
            # Starter quest Step 5.5 hook — "The Powers That Be"
            try:
                from engine.tutorial_v2 import check_starter_quest
                await check_starter_quest(ctx.session, ctx.db,
                                          trigger="command", command="faction")
            except Exception:
                pass
            return

        # ── faction list ──
        if sub == "list":
            await ctx.session.send_line(await format_faction_list(ctx.db))
            # Starter quest Step 5.5 hook — also fires on 'faction list'
            try:
                from engine.tutorial_v2 import check_starter_quest
                await check_starter_quest(ctx.session, ctx.db,
                                          trigger="command", command="faction")
            except Exception:
                pass
            return

        # ── faction join <code> ──
        if sub == "join":
            if not rest:
                await ctx.session.send_line("Usage: faction join <code>  (use 'faction list' to see codes)")
                return
            ok, msg = await join_faction(char, rest, ctx.db, session=ctx.session)
            await ctx.session.send_line(f"  {msg}")
            if ok:
                await ctx.session_mgr.broadcast_to_room(
                    char["room_id"],
                    f"  {char['name']} has aligned with a new cause.",
                    exclude=ctx.session,
                )
            return

        # ── faction leave ──
        if sub == "leave":
            ok, msg = await leave_faction(char, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── faction info <code> ──
        if sub == "info":
            code = rest or char.get("faction_id", "independent")
            org = await ctx.db.get_organization(code)
            if not org:
                await ctx.session.send_line(f"  Unknown faction '{code}'.")
                return
            ranks = await ctx.db.get_org_ranks(org["id"])
            lines = [
                f"\033[1;36m══════════════════════════════════════════\033[0m",
                f"  \033[1;37m{org['name']}\033[0m",
                f"\033[1;36m──────────────────────────────────────────\033[0m",
                f"  Rank Table:",
            ]
            for r in ranks:
                lines.append(
                    f"    [{r['rank_level']}] {r['title']:<18}  "
                    f"Min rep: \033[1;33m{r['min_rep']}\033[0m"
                )
            lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
            await ctx.session.send_line("\n".join(lines))
            return

        await ctx.session.send_line(f"  Unknown faction subcommand '{sub}'. Try: faction list, faction join, faction leave, faction info")


class GuildCommand(BaseCommand):
    key = "guild"
    aliases = ["+guild"]
    help_text = (
        "Manage your guild memberships.\n"
        "\n"
        "USAGE:\n"
        "  guild            — show your guild memberships\n"
        "  guild list       — show all guilds\n"
        "  guild join <g>   — join a guild (code from 'guild list')\n"
        "  guild leave <g>  — leave a guild\n"
        "\n"
        "You can belong to up to 3 guilds simultaneously.\n"
        "Guild members receive a 20% CP cost discount on skill training."
    )
    usage = "guild [list | join <code> | leave <code>]"

    async def execute(self, ctx: CommandContext):
        from engine.organizations import (
            join_guild, leave_guild, format_faction_status, format_guild_list,
        )

        char = ctx.session.character
        args = (ctx.args or "").strip().lower()
        parts = args.split(None, 1)
        sub = parts[0] if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        # ── guild (no args) ──
        if not sub:
            await ctx.session.send_line(await format_faction_status(char, ctx.db))
            return

        # ── guild list ──
        if sub == "list":
            await ctx.session.send_line(await format_guild_list(ctx.db))
            return

        # ── guild join <code> ──
        if sub == "join":
            if not rest:
                await ctx.session.send_line("Usage: guild join <code>  (use 'guild list' to see codes)")
                return
            ok, msg = await join_guild(char, rest, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── guild leave <code> ──
        if sub == "leave":
            if not rest:
                await ctx.session.send_line("Usage: guild leave <code>")
                return
            ok, msg = await leave_guild(char, rest, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        await ctx.session.send_line(f"  Unknown subcommand '{sub}'. Try: guild list, guild join, guild leave")


class SpecializeCommand(BaseCommand):
    key = "specialize"
    aliases = ["specialise"]
    help_text = (
        "Select your Imperial specialization (only available after joining the Empire).\n"
        "  1 = Stormtrooper  2 = TIE Pilot  3 = Naval Officer  4 = Intelligence"
    )
    usage = "specialize <1-4>"

    async def execute(self, ctx: CommandContext):
        from engine.organizations import complete_imperial_specialization
        char = ctx.session.character

        if char.get("faction_id", "independent") != "empire":
            await ctx.session.send_line(
                "  This command is only available to Imperial faction members."
            )
            return

        arg = (ctx.args or "").strip()
        if not arg.isdigit() or int(arg) not in (1, 2, 3, 4):
            await ctx.session.send_line(
                "  Usage: specialize <1-4>\n"
                "  1 = Stormtrooper  2 = TIE Pilot  3 = Naval Officer  4 = Intelligence"
            )
            return

        ok, msg = await complete_imperial_specialization(
            char, ctx.db, int(arg), session=ctx.session
        )
        await ctx.session.send_line(f"  {msg}")
        if ok:
            await ctx.db.save_character(
                char["id"], attributes=char.get("attributes", "{}")
            )


def register_faction_commands(registry):
    registry.register(FactionCommand())
    registry.register(GuildCommand())
    registry.register(SpecializeCommand())
