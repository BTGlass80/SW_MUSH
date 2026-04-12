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
        "TERRITORY:\n"
        "  faction invest <cr>  — invest treasury credits into zone influence\n"
        "  faction influence    — show territorial influence and claimed rooms\n"
        "  faction claim        — claim the current room (rank 3+, costs 5,000cr)\n"
        "  faction unclaim      — release the current room claim\n"
        "  faction guard        — show guard status in current claimed room\n"
        "  faction guard station — station a guard (500cr + 100cr/wk)\n"
        "  faction guard remove  — dismiss the guard from this room\n"
        "  faction armory       — view shared faction armory (claimed rooms only)\n"
        "  faction armory deposit <item>      — deposit item into armory\n"
        "  faction armory withdraw <item>     — withdraw item from armory\n"
        "  faction armory withdraw <res> <n>  — withdraw crafting resources\n"
        "  faction seize             — seize rival room after killing its guard (lawless only)\n"
        "\n"
        "You can only belong to ONE faction at a time.\n"
        "Switching factions has a 7-day cooldown."
    )
    usage = "faction [list|join|leave|info|roster|missions|channel|invest|influence|claim|unclaim|guard|armory]"

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
                log.warning("execute: unhandled exception", exc_info=True)
                pass
            try:
                from engine.spacer_quest import check_spacer_quest
                await check_spacer_quest(ctx.session, ctx.db, "use_command", command="faction")
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
                log.warning("execute: unhandled exception", exc_info=True)
                pass
            try:
                from engine.spacer_quest import check_spacer_quest
                await check_spacer_quest(ctx.session, ctx.db, "use_command", command="faction")
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

        # ── faction invest <amount> ──
        if sub == "invest":
            faction_id = char.get("faction_id", "independent")
            if not faction_id or faction_id == "independent":
                await ctx.session.send_line("  You're not in a faction.")
                return
            if not rest or not rest.isdigit():
                await ctx.session.send_line(
                    "  Usage: faction invest <amount>\n"
                    "  Invest credits from your faction treasury to build territorial influence.\n"
                    "  Minimum 1,000cr, maximum 10,000cr per investment. Requires rank 3+."
                )
                return
            from engine.territory import invest_influence
            result = await invest_influence(ctx.db, char, faction_id, int(rest))
            await ctx.session.send_line(
                f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
                else f"  \033[1;33m{result['msg']}\033[0m"
            )
            return

        # ── faction influence ──
        if sub in ("influence", "territory", "terr"):
            faction_id = char.get("faction_id", "independent")
            if not faction_id or faction_id == "independent":
                await ctx.session.send_line("  You're not in a faction.")
                return
            from engine.territory import get_influence_status_lines, get_claims_status_lines
            lines = await get_influence_status_lines(ctx.db, faction_id)
            for line in lines:
                await ctx.session.send_line(line)
            await ctx.session.send_line("")
            claim_lines = await get_claims_status_lines(ctx.db, faction_id)
            for line in claim_lines:
                await ctx.session.send_line(line)
            return

        # ── faction claim ──
        if sub == "claim":
            faction_id = char.get("faction_id", "independent")
            if not faction_id or faction_id == "independent":
                await ctx.session.send_line("  You're not in a faction.")
                return
            from engine.territory import claim_room
            room_id = char.get("room_id")
            result = await claim_room(ctx.db, char, faction_id, room_id)
            await ctx.session.send_line(
                f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
                else f"  \033[1;33m{result['msg']}\033[0m"
            )
            if result["ok"]:
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    f"  \033[1;37m{char['name']} plants a marker — "
                    f"this room is now claimed by {faction_id.replace('_', ' ').title()}.\033[0m",
                    exclude=ctx.session,
                )
            return

        # ── faction unclaim ──
        if sub == "unclaim":
            faction_id = char.get("faction_id", "independent")
            if not faction_id or faction_id == "independent":
                await ctx.session.send_line("  You're not in a faction.")
                return
            from engine.territory import unclaim_room
            room_id = char.get("room_id")
            result = await unclaim_room(ctx.db, char, faction_id, room_id)
            await ctx.session.send_line(
                f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
                else f"  \033[1;33m{result['msg']}\033[0m"
            )
            return

        # ── faction guard ──
        # faction guard          — show guard status in current room
        # faction guard station  — station a guard in the current claimed room
        # faction guard remove   — dismiss the guard from the current claimed room
        if sub == "guard":
            faction_id = char.get("faction_id", "independent")
            if not faction_id or faction_id == "independent":
                await ctx.session.send_line("  You're not in a faction.")
                return
            room_id = char.get("room_id")
            from engine.territory import (
                get_claim, spawn_guard_npc, remove_guard_npc,
                GUARD_COST, GUARD_WEEKLY_UPKEEP,
            )
            guard_sub = rest.lower() if rest else ""

            if guard_sub == "station":
                result = await spawn_guard_npc(ctx.db, faction_id, room_id, char["id"])
                await ctx.session.send_line(
                    f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
                    else f"  \033[1;33m{result['msg']}\033[0m"
                )
                if result["ok"]:
                    await ctx.session_mgr.broadcast_to_room(
                        room_id,
                        f"  \033[2mA guard takes up position, eyes scanning the room.\033[0m",
                        exclude=ctx.session,
                    )
            elif guard_sub == "remove":
                result = await remove_guard_npc(ctx.db, faction_id, room_id, char["id"])
                await ctx.session.send_line(
                    f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
                    else f"  \033[1;33m{result['msg']}\033[0m"
                )
                if result["ok"]:
                    await ctx.session_mgr.broadcast_to_room(
                        room_id,
                        f"  \033[2mThe guard is dismissed and departs without a word.\033[0m",
                        exclude=ctx.session,
                    )
            else:
                # Show guard status for this room
                claim = await get_claim(ctx.db, room_id)
                if not claim or claim["org_code"] != faction_id:
                    await ctx.session.send_line(
                        "  This room is not claimed by your faction.\n"
                        f"  Cost to station a guard: {GUARD_COST:,}cr (one-time) + "
                        f"{GUARD_WEEKLY_UPKEEP}cr/week upkeep.\n"
                        "  Usage: faction guard station | faction guard remove"
                    )
                    return
                if claim.get("guard_npc_id"):
                    npc = await ctx.db.get_npc(claim["guard_npc_id"])
                    npc_name = npc["name"] if npc else "Unknown Guard"
                    await ctx.session.send_line(
                        f"  \033[1;32mGuard stationed:\033[0m {npc_name}\n"
                        f"  Weekly upkeep: +{GUARD_WEEKLY_UPKEEP}cr/wk\n"
                        f"  Use \033[1;37mfaction guard remove\033[0m to dismiss."
                    )
                else:
                    await ctx.session.send_line(
                        "  No guard stationed in this room.\n"
                        f"  Cost to station: {GUARD_COST:,}cr (one-time) + "
                        f"{GUARD_WEEKLY_UPKEEP}cr/wk upkeep.\n"
                        "  Use \033[1;37mfaction guard station\033[0m to station one."
                    )
            return

        # ── faction armory ──
        # faction armory                    — show armory contents
        # faction armory deposit <item>     — deposit item from inventory
        # faction armory withdraw <item>    — withdraw item to inventory
        # faction armory withdraw <type> <qty>  — withdraw crafting resources
        if sub == "armory":
            faction_id = char.get("faction_id", "independent")
            if not faction_id or faction_id == "independent":
                await ctx.session.send_line("  You're not in a faction.")
                return
            room_id = char.get("room_id")
            from engine.territory import (
                is_room_claimed_by, get_armory_lines,
                armory_deposit_item, armory_withdraw_item,
                armory_withdraw_resources,
            )

            # Must be in a claimed room for this faction
            if not await is_room_claimed_by(ctx.db, room_id, faction_id):
                await ctx.session.send_line(
                    "  You must be standing in one of your faction's claimed rooms "
                    "to access the armory.\n"
                    "  Use \033[1;37mfaction territory\033[0m to see your claimed rooms."
                )
                return

            armory_parts = rest.split(None, 1) if rest else []
            armory_sub = armory_parts[0].lower() if armory_parts else ""
            armory_arg = armory_parts[1].strip() if len(armory_parts) > 1 else ""

            if armory_sub == "deposit":
                if not armory_arg:
                    await ctx.session.send_line(
                        "  Usage: faction armory deposit <item name>"
                    )
                    return
                result = await armory_deposit_item(ctx.db, char, faction_id, armory_arg)
                await ctx.session.send_line(
                    f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
                    else f"  \033[1;33m{result['msg']}\033[0m"
                )

            elif armory_sub == "withdraw":
                if not armory_arg:
                    await ctx.session.send_line(
                        "  Usage: faction armory withdraw <item name>\n"
                        "         faction armory withdraw <resource type> <quantity>"
                    )
                    return
                # Check if this looks like "resource_type quantity"
                withdraw_parts = armory_arg.split()
                if len(withdraw_parts) == 2 and withdraw_parts[1].isdigit():
                    res_type = withdraw_parts[0]
                    qty = int(withdraw_parts[1])
                    result = await armory_withdraw_resources(
                        ctx.db, char, faction_id, res_type, qty
                    )
                else:
                    result = await armory_withdraw_item(ctx.db, char, faction_id, armory_arg)
                await ctx.session.send_line(
                    f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
                    else f"  \033[1;33m{result['msg']}\033[0m"
                )

            else:
                # Show armory contents
                lines = await get_armory_lines(ctx.db, faction_id)
                for line in lines:
                    await ctx.session.send_line(line)

            return

        # ── faction seize ──
        # Hostile takeover of a rival-claimed room after killing its guard.
        # Lawless zones only. Requires 50+ influence and 5,000cr treasury.
        if sub == "seize":
            faction_id = char.get("faction_id", "independent")
            if not faction_id or faction_id == "independent":
                await ctx.session.send_line("  You're not in a faction.")
                return
            from engine.territory import hostile_takeover_claim
            room_id = char.get("room_id")
            result = await hostile_takeover_claim(ctx.db, char, faction_id, room_id)
            await ctx.session.send_line(
                f"  [1;31m{result['msg']}[0m" if result["ok"]
                else f"  [1;33m{result['msg']}[0m"
            )
            if result["ok"]:
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    f"  [1;31m[TERRITORY SEIZED][0m "
                    f"{char['name']} claims this room for "
                    f"{faction_id.replace('_', ' ').title()}!",
                    exclude=ctx.session,
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
            f"  Try: list, join, leave, info, roster, missions, channel, requisition, invest, influence, claim, unclaim, guard, armory, seize"
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
