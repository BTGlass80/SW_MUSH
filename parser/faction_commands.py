# -*- coding: utf-8 -*-
"""
parser/faction_commands.py — Faction and guild commands for SW_MUSH.

Commands:
  faction             — show your faction status
  faction list        — list all factions
  faction join <code> — join a faction
  faction leave       — leave current faction
  faction info <code> — show faction details and ranks
  faction roster      — list faction members (rank 3+ only)
  faction missions    — show faction-specific mission board
  faction channel <m> — send message on faction comms channel
  faction requisition <item> — request replacement equipment (logged for Director)

  guild               — show your guild memberships
  guild list          — list all guilds
  guild join <code>   — join a guild (max 3)
  guild leave <code>  — leave a guild

  specialize <1-4>    — choose Imperial specialization
"""
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel

log = logging.getLogger(__name__)

_DIFFICULTY_LABELS = {
    "easy": "Easy", "moderate": "Moderate",
    "difficult": "Difficult", "heroic": "Heroic",
}


class FactionCommand(BaseCommand):
    key = "faction"
    aliases = ["+faction", "fac"]
    help_text = (
        "Manage your faction membership.\n"
        "\n"
        "USAGE:\n"
        "  faction              — show your current faction and rank\n"
        "  faction list         — show all factions\n"
        "  faction join <f>     — join a faction (code from 'faction list')\n"
        "  faction leave        — leave your current faction\n"
        "  faction info <f>     — show faction details and rank table\n"
        "  faction roster       — list all faction members (rank 3+ only)\n"
        "  faction missions     — show faction-exclusive mission board\n"
        "  faction channel <m>  — send message on faction comms channel\n"
        "  faction requisition <item> — request replacement equipment\n"
        "\n"
        "You can only belong to ONE faction at a time.\n"
        "Switching factions has a 7-day cooldown."
    )
    usage = "faction [list | join <code> | leave | info <code> | roster | missions | channel <msg> | requisition <item>]"

    async def execute(self, ctx: CommandContext):
        from engine.organizations import (
            join_faction, leave_faction, format_faction_status,
            format_faction_list,
        )
        from server import ansi

        char = ctx.session.character
        args = (ctx.args or "").strip()
        parts = args.split(None, 1)
        sub  = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        # ── faction (no args) ──
        if not sub:
            await ctx.session.send_line(await format_faction_status(char, ctx.db))
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
                await ctx.session.send_line(
                    "Usage: faction join <code>  (use 'faction list' to see codes)"
                )
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

        # ── faction roster ──
        if sub == "roster":
            faction_id = char.get("faction_id", "independent")
            if faction_id == "independent":
                await ctx.session.send_line(
                    "  You must be a faction member to view the roster."
                )
                return

            org = await ctx.db.get_organization(faction_id)
            if not org:
                await ctx.session.send_line("  Faction data unavailable.")
                return

            # Require rank 3+ per design
            mem = await ctx.db.get_membership(char["id"], org["id"])
            if not mem or mem.get("rank_level", 0) < 3:
                await ctx.session.send_line(
                    "  Roster access requires rank 3 or higher."
                )
                return

            members = await ctx.db.get_org_members(org["id"])
            if not members:
                await ctx.session.send_line(
                    f"  {org['name']} has no registered members."
                )
                return

            ranks = await ctx.db.get_org_ranks(org["id"])
            rank_titles = {r["rank_level"]: r["title"] for r in ranks}

            lines = [
                f"\033[1;36m══════════════════════════════════════════\033[0m",
                f"  \033[1;37m{org['name'].upper()} — ROSTER\033[0m",
                f"\033[1;36m──────────────────────────────────────────\033[0m",
            ]
            for m in members:
                title = rank_titles.get(m["rank_level"], f"Rank {m['rank_level']}")
                standing = m.get("standing", "good")
                standing_tag = (
                    ""            if standing == "good"      else
                    f" \033[1;33m[Probation]\033[0m"  if standing == "probation" else
                    f" \033[1;31m[Expelled]\033[0m"
                )
                lines.append(
                    f"  \033[1;37m{m['char_name']:<20}\033[0m "
                    f"\033[2m{title:<18}\033[0m"
                    f"  Rep: {m.get('rep_score', 0):>3}"
                    f"{standing_tag}"
                )
            lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
            await ctx.session.send_line("\n".join(lines))
            return

        # ── faction missions ──
        if sub == "missions":
            faction_id = char.get("faction_id", "independent")
            if faction_id == "independent":
                await ctx.session.send_line(
                    "  You need to join a faction to access its mission board.\n"
                    "  Use 'missions' for the public mission board."
                )
                return

            org = await ctx.db.get_organization(faction_id)
            org_name = org["name"] if org else faction_id.title()
            missions = await ctx.db.get_faction_missions(faction_id, limit=10)

            if not missions:
                await ctx.session.send_line(
                    f"  No faction missions available from {org_name}.\n"
                    f"  Check back after the next Director cycle (every 30 minutes)."
                )
                return

            lines = [
                f"\033[1;36m══════════════════════════════════════════\033[0m",
                f"  \033[1;37m{org_name.upper()} — MISSION BOARD\033[0m",
                f"\033[1;36m──────────────────────────────────────────\033[0m",
            ]
            for m in missions:
                diff_label = _DIFFICULTY_LABELS.get(
                    m.get("difficulty", "easy"), "Easy"
                )
                lines.append(
                    f"  \033[1;37m[{m['id']}]\033[0m {m['title']:<36} "
                    f"\033[1;33m{m.get('reward', 0):,}cr\033[0m  "
                    f"\033[2m{diff_label}\033[0m"
                )
                if m.get("description"):
                    lines.append(f"      \033[2m{m['description'][:80]}\033[0m")
            lines.append(
                "\033[1;36m──────────────────────────────────────────\033[0m"
            )
            lines.append(
                "  Type \033[1;33mmission accept <id>\033[0m to accept a mission."
            )
            lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
            await ctx.session.send_line("\n".join(lines))
            return

        # ── faction channel <message> ──
        if sub == "channel":
            if not rest:
                await ctx.session.send_line(
                    "  Usage: faction channel <message>"
                )
                return

            faction_id = char.get("faction_id", "independent")
            if faction_id == "independent":
                await ctx.session.send_line(
                    "  You must be a faction member to use the faction channel."
                )
                return

            try:
                from server.channels import get_channel_manager
                cm = get_channel_manager()
                await cm.broadcast_fcomm(
                    ctx.session_mgr, char["name"], faction_id, rest
                )
            except Exception as e:
                log.warning("[faction] channel broadcast failed: %s", e)
                await ctx.session.send_line(
                    "  Faction comms unavailable."
                )
            return

        # ── faction requisition <item> ──
        if sub == "requisition":
            faction_id = char.get("faction_id", "independent")
            if faction_id == "independent":
                await ctx.session.send_line(
                    "  You must be a faction member to submit a requisition."
                )
                return

            if not rest:
                await ctx.session.send_line(
                    "  Usage: faction requisition <item description>"
                )
                return

            org = await ctx.db.get_organization(faction_id)
            if org:
                await ctx.db.log_faction_action(
                    char["id"], org["id"], "requisition_request",
                    f"Requested: {rest[:200]}"
                )

            await ctx.session.send_line(
                f"  Requisition submitted: \033[2m{rest[:100]}\033[0m\n"
                f"  The Director will review your request at the next faction cycle."
            )
            return

        # ── faction leader sub-commands (rank 5+) ──
        if sub in _LEADER_SUBS:
            from parser.faction_leader_commands import FactionLeaderCommand
            handled = await FactionLeaderCommand.dispatch(ctx, sub, rest)
            if handled:
                return

        await ctx.session.send_line(
            f"  Unknown faction subcommand '{sub}'.\n"
            f"  Try: list, join, leave, info, roster, missions, channel, requisition"
        )
# Import and delegate to faction_leader_commands for rank-5+ sub-commands.
# This wrapper is inserted here so FactionCommand stays as the single
# registered command; leader subs are just an extension of its execute().

_LEADER_SUBS = frozenset({
    "promote", "demote", "warn", "probation", "pardon", "expel",
    "announce", "treasury", "motd", "log", "mission",
})


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
        sub  = parts[0] if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if not sub:
            await ctx.session.send_line(await format_faction_status(char, ctx.db))
            return
        if sub == "list":
            await ctx.session.send_line(await format_guild_list(ctx.db))
            return
        if sub == "join":
            if not rest:
                await ctx.session.send_line(
                    "Usage: guild join <code>  (use 'guild list' to see codes)"
                )
                return
            ok, msg = await join_guild(char, rest, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return
        if sub == "leave":
            if not rest:
                await ctx.session.send_line("Usage: guild leave <code>")
                return
            ok, msg = await leave_guild(char, rest, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        await ctx.session.send_line(
            f"  Unknown subcommand '{sub}'. Try: guild list, guild join, guild leave"
        )


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
