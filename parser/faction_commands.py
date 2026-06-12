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

  specialize <1-4>    — choose your faction specialization
"""
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel

# F.7.j follow-up (May 4 2026): hoisted from inside FactionCommand.execute
# so the post-Phase-3-C4 `_cmd_*` dispatch handlers can see these symbols.
# Prior to this hoist, `_cmd_status`, `_cmd_list`, `_cmd_join`, `_cmd_leave`
# raised `NameError: name 'format_faction_status' is not defined` (and
# similar for `format_faction_list`, `join_faction`, `leave_faction`)
# because the imports were local to `execute()` and didn't reach the
# named methods. Caught by tests/smoke/test_smoke_channels_faction.py
# (the +faction with no args path → _cmd_status) on the Windows ground-
# truth full-suite run. The guild-side imports stay local because
# GuildCommand.execute is still inline (no `_cmd_*` split there).
from engine.organizations import (
    format_org_posture_line,
    join_faction, leave_faction,
    format_faction_status, format_faction_list,
)

log = logging.getLogger(__name__)

_DIFFICULTY_LABELS = {
    "easy": "Easy", "moderate": "Moderate",
    "difficult": "Difficult", "heroic": "Heroic",
}


class FactionCommand(BaseCommand):
    key = "faction"
    aliases = ["fac"]
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
        "\n"
        "RESOURCE OUTLOOK (weekly, per design §2.5.5):\n"
        "  faction resource_outlook   — show this week's per-region quality\n"
        "                                multipliers (best/worst types per region).\n"
        "                                Aliases: outlook, resources.\n"
        "\n"
        "You can only belong to ONE faction at a time.\n"
        "Switching factions has a 7-day cooldown."
    )
    usage = "faction [list|join|leave|info|roster|missions|channel|invest|influence|claim|unclaim|guard|armory]"

    async def execute(self, ctx: CommandContext):
        """Dispatch to sub-command handlers. Phase 3 C4 refactor.

        Module-level imports of `join_faction`, `leave_faction`,
        `format_faction_status`, `format_faction_list` (top of file)
        are visible to the `_cmd_*` handlers below — see the F.7.j
        follow-up note at the top of this module.
        """
        from server import ansi

        char = ctx.session.character
        args = (ctx.args or "").strip()
        parts = args.split(None, 1)
        sub  = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        # ── faction (no args) ──

        if not sub:
            return await self._cmd_status(ctx, char, rest)

        _dispatch = {
            "list": self._cmd_list,
            "join": self._cmd_join,
            "leave": self._cmd_leave,
            "info": self._cmd_info,
            "roster": self._cmd_roster,
            "missions": self._cmd_missions,
            "channel": self._cmd_channel,
            "requisition": self._cmd_requisition,
            "invest": self._cmd_invest,
            "influence": self._cmd_influence,
            "territory": self._cmd_influence,
            "terr": self._cmd_influence,
            "claim": self._cmd_claim,
            "unclaim": self._cmd_unclaim,
            # ── SYN.6.b (May 25 2026): resource outlook digest ──
            "resource_outlook": self._cmd_resource_outlook,
            "outlook": self._cmd_resource_outlook,
            "resources": self._cmd_resource_outlook,
            "guard": self._cmd_guard,
            "armory": self._cmd_armory,
            "hq": self._handle_hq,
        }
        handler = _dispatch.get(sub)
        if handler:
            return await handler(ctx, char, rest)

        if sub in _LEADER_SUBS:
            from parser.faction_leader_commands import FactionLeaderCommand
            handled = await FactionLeaderCommand.dispatch(ctx, sub, rest)
            if handled:
                return

        await ctx.session.send_line(
            f"  Unknown faction subcommand '{sub}'.\n"
            f"  Try: list, join, leave, info, roster, missions, channel, "
            f"requisition, invest, influence, claim, unclaim, "
            f"resource_outlook, guard, armory, hq"
        )

    async def _cmd_status(self, ctx, char, rest):
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
        except Exception as _e:
            log.debug("silent except in parser/faction_commands.py:96: %s", _e, exc_info=True)
        return

        # ── faction list ──

    async def _cmd_list(self, ctx, char, rest):
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
        except Exception as _e:
            log.debug("silent except in parser/faction_commands.py:113: %s", _e, exc_info=True)
        return

        # ── faction join <code> ──

    async def _cmd_join(self, ctx, char, rest):
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
                source_char=char,
        )
        return

        # ── faction leave ──

    async def _cmd_leave(self, ctx, char, rest):
        ok, msg = await leave_faction(char, ctx.db)
        await ctx.session.send_line(f"  {msg}")
        return

        # ── faction info <code> ──

    async def _cmd_info(self, ctx, char, rest):
        # B.6 (defensive): distinguish "user typed a bad code" from
        # "your own faction_id references a stale faction." The latter
        # shows up when a PC's stored faction_id was valid in a prior
        # era but isn't in the currently-seeded DB.
        explicit = bool(rest)
        code = rest or char.get("faction_id", "independent")
        org = await ctx.db.get_organization(code)
        if not org:
            if explicit:
                await ctx.session.send_line(f"  Unknown faction '{code}'.")
            else:
                await ctx.session.send_line(
                    f"  \033[1;33mYour faction record references '{code}', "
                    f"which no longer\033[0m\n"
                    f"  \033[1;33mexists in this universe.\033[0m "
                    f"Use \033[1;37mfaction list\033[0m to see your\n"
                    f"  options, then \033[1;37mfaction join <code>\033[0m "
                    f"to refresh."
                )
            return
        ranks = await ctx.db.get_org_ranks(org["id"])
        lines = [
            f"\033[1;36m══════════════════════════════════════════\033[0m",
            f"  \033[1;37m{org['name']}\033[0m",
            f"\033[1;36m──────────────────────────────────────────\033[0m",
            f"  Rank Table:",
        ]
        _posture = format_org_posture_line(org)
        if _posture:
            lines.insert(3, _posture)
        for r in ranks:
            lines.append(
                f"    [{r['rank_level']}] {r['title']:<18}  "
                f"Min rep: \033[1;33m{r['min_rep']}\033[0m"
            )
        lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
        await ctx.session.send_line("\n".join(lines))
        return

        # ── faction roster ──

    async def _cmd_roster(self, ctx, char, rest):
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

    async def _cmd_missions(self, ctx, char, rest):
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

    async def _cmd_channel(self, ctx, char, rest):
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

    async def _cmd_requisition(self, ctx, char, rest):
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

    async def _cmd_invest(self, ctx, char, rest):
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

    async def _cmd_influence(self, ctx, char, rest):
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

    async def _cmd_claim(self, ctx, char, rest):
        """SYN.1.b (2026-05-24): retargeted from per-room
        ``claim_room`` to region-scope ``claim_region``. Player must
        be standing in a room within the wilderness region they want
        to claim — the room's ``wilderness_region_id`` is the slug
        passed to ``claim_region``. City-map rooms (no
        wilderness_region_id) get a clear-message rejection.
        """
        faction_id = char.get("faction_id", "independent")
        if not faction_id or faction_id == "independent":
            await ctx.session.send_line("  You're not in a faction.")
            return
        room_id = char.get("room_id")
        room = await ctx.db.get_room(room_id) if room_id else None
        region_slug = (room or {}).get("wilderness_region_id")
        if not region_slug:
            await ctx.session.send_line(
                "  \033[1;33mTerritory claims are made on wilderness "
                "regions, not city-map rooms. Travel into a wilderness "
                "region first, then use 'faction claim' to claim it for "
                "your organization.\033[0m"
            )
            return
        from engine.territory import claim_region
        result = await claim_region(ctx.db, char, faction_id, region_slug)
        await ctx.session.send_line(
            f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
            else f"  \033[1;33m{result['msg']}\033[0m"
        )
        if result["ok"]:
            await ctx.session_mgr.broadcast_to_room(
                room_id,
                f"  \033[1;37m{char['name']} plants a banner — "
                f"this region is now claimed by "
                f"{faction_id.replace('_', ' ').title()}.\033[0m",
                exclude=ctx.session,
                source_char=char,
        )
        return

        # ── faction unclaim ──

    async def _cmd_unclaim(self, ctx, char, rest):
        """SYN.1.b (2026-05-24): retargeted from per-room
        ``unclaim_room`` to region-scope ``unclaim_region``."""
        faction_id = char.get("faction_id", "independent")
        if not faction_id or faction_id == "independent":
            await ctx.session.send_line("  You're not in a faction.")
            return
        room_id = char.get("room_id")
        room = await ctx.db.get_room(room_id) if room_id else None
        region_slug = (room or {}).get("wilderness_region_id")
        if not region_slug:
            await ctx.session.send_line(
                "  \033[1;33mYou must be standing in the wilderness region "
                "you want to release. City-map rooms aren't claimable.\033[0m"
            )
            return
        from engine.territory import unclaim_region
        result = await unclaim_region(ctx.db, char, faction_id, region_slug)
        await ctx.session.send_line(
            f"  \033[1;36m{result['msg']}\033[0m" if result["ok"]
            else f"  \033[1;33m{result['msg']}\033[0m"
        )
        return

        # ── faction resource_outlook ── (SYN.6.b, 2026-05-25)
        # The Director's "crafter's news feed" — per design §2.5.5,
        # shows which wilderness regions have the best resource
        # multipliers this week. Restricted to the caller's owned
        # regions if they're in a faction; shows everything if
        # independent (with a "for context only" framing line).

    async def _cmd_resource_outlook(self, ctx, char, rest):
        """SYN.6.b: weekly resource outlook digest.

        Surfaces the per-region per-resource-type quality multipliers
        rolled by ``engine.region_quality.tick_weekly_region_quality``.
        For a faction member: limited to their org's owned regions.
        For an independent: shows all regions (read-only context).

        Per design §2.5.5: this is the "crafter's news feed" that
        drives wilderness traffic without forcing combat engagement.
        """
        from engine.region_quality import get_outlook, _iso_year_week

        faction_id = char.get("faction_id", "independent")
        is_independent = (not faction_id) or faction_id == "independent"
        org_filter = None if is_independent else faction_id

        outlook = await get_outlook(ctx.db, org_filter)
        current_week = _iso_year_week()

        await ctx.session.send_line(
            f"  \033[1;36mResource Outlook — week {current_week}\033[0m"
        )
        if is_independent:
            await ctx.session.send_line(
                "  \033[2m(All wilderness regions; you're not in a "
                "faction so this is for context only.)\033[0m"
            )
        else:
            org_label = faction_id.replace("_", " ").title()
            await ctx.session.send_line(
                f"  \033[2m({org_label} territories)\033[0m"
            )

        if not outlook:
            await ctx.session.send_line(
                "  \033[2mNo region quality data yet. The weekly tick "
                "rolls Monday at server midnight.\033[0m"
            )
            return

        # Sort regions by best-multiplier descending so the most
        # interesting regions surface first.
        sorted_regions = sorted(
            outlook.items(),
            key=lambda kv: kv[1]["best"][1],
            reverse=True,
        )
        for slug, summary in sorted_regions:
            best_type, best_mult = summary["best"]
            worst_type, worst_mult = summary["worst"]
            slug_label = slug.replace("_", " ").title()
            # Color-grade by best multiplier: green for ≥1.2×, yellow
            # for 1.0..1.2×, dim for <1.0×.
            if best_mult >= 1.2:
                color = "\033[1;32m"  # bright green
            elif best_mult >= 1.0:
                color = "\033[1;33m"  # bright yellow
            else:
                color = "\033[2m"     # dim
            await ctx.session.send_line(
                f"  {color}{slug_label:<28}\033[0m  "
                f"best: {best_type:<8} {best_mult:.2f}×   "
                f"worst: {worst_type:<8} {worst_mult:.2f}×"
            )
        return

        # ── faction guard ──
        # faction guard          — show guard status in current room
        # faction guard station  — station a guard in the current claimed room
        # faction guard remove   — dismiss the guard from the current claimed room

    async def _cmd_guard(self, ctx, char, rest):
        """SYN.1.b (2026-05-24): per-room guard stationing retired.
        Region garrisons are deployed automatically by ``claim_region``;
        there is no player-driven per-room guard command under the
        region model. Body preserved as a clear-message rejection so
        existing help text + tab-completion continue to work, but the
        underlying spawn_guard_npc / remove_guard_npc / get_claim
        surfaces are stubs now (see engine/territory.py).
        """
        faction_id = char.get("faction_id", "independent")
        if not faction_id or faction_id == "independent":
            await ctx.session.send_line("  You're not in a faction.")
            return
        await ctx.session.send_line(
            "  \033[1;33mPer-room guard stationing has been retired. "
            "Region garrisons are deployed automatically when your "
            "faction claims a wilderness region — see "
            "'faction claim' and 'faction territory'.\033[0m"
        )
        return
        # ── unreachable: preserved for reference until SYN.4 cleanup ──
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
                    source_char=char,
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
                    source_char=char,
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

    async def _cmd_armory(self, ctx, char, rest):
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
        # RETIRED in SYN.3 (2026-05-25). Per-room seizure is gone
        # — per-room claims retired in SYN.1.b, and the Drop 6D
        # hostile-takeover-on-guard-kill flow deleted in SYN.3.
        # Region-level seizure happens organically through the
        # contest state machine in engine/contest.py.


        # ── faction hq ──

    async def _handle_hq(self, ctx, char, rest):
        """Handle faction hq sub-commands."""
        from server import ansi
        faction_id = char.get("faction_id", "independent")
        if not faction_id or faction_id == "independent":
            await ctx.session.send_line("  You're not in a faction.")
            return

        parts = rest.split(None, 1) if rest else []
        hq_sub = parts[0].lower() if parts else ""
        hq_rest = parts[1].strip() if len(parts) > 1 else ""

        # faction hq (no args) — show status
        if not hq_sub:
            from engine.housing import get_hq_status_lines
            lines = await get_hq_status_lines(ctx.db, faction_id)
            for line in lines:
                await ctx.session.send_line(line)
            return

        # faction hq locations — show available lots
        if hq_sub in ("locations", "lots", "list"):
            from engine.housing import get_tier5_listing_lines
            lines = await get_tier5_listing_lines(ctx.db, faction_id)
            for line in lines:
                await ctx.session.send_line(line)
            return

        # faction hq purchase <type> <lot_id>
        if hq_sub in ("purchase", "buy", "establish"):
            hq_parts = hq_rest.split()
            if len(hq_parts) < 2:
                await ctx.session.send_line(
                    "  Usage: faction hq purchase <type> <lot_id>\n"
                    "  Types: outpost, chapter_house, fortress\n"
                    "  Use 'faction hq locations' to see lot IDs."
                )
                return
            hq_type = hq_parts[0].lower()
            try:
                lot_id = int(hq_parts[1])
            except ValueError:
                await ctx.session.send_line(f"  '{hq_parts[1]}' isn't a valid lot ID.")
                return
            from engine.housing import purchase_hq
            result = await purchase_hq(ctx.db, char, faction_id, hq_type, lot_id)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        # faction hq sell [confirm]
        if hq_sub == "sell":
            if hq_rest.lower() != "confirm":
                from engine.housing import get_org_hq
                h = await get_org_hq(ctx.db, faction_id)
                if not h:
                    await ctx.session.send_line("  Your faction doesn't have an HQ.")
                    return
                refund = h.get("purchase_price", 0) // 4
                await ctx.session.send_line(
                    f"  \033[1;33mWARNING:\033[0m This will disband the HQ.\n"
                    f"  Refund: {refund:,}cr to treasury (25% of purchase price).\n"
                    f"  Storage items returned to faction armory.\n"
                    f"  Type \033[1;37mfaction hq sell confirm\033[0m to proceed."
                )
                return
            from engine.housing import sell_hq
            result = await sell_hq(ctx.db, char, faction_id)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        await ctx.session.send_line(
            "  faction hq commands:\n"
            "    faction hq              — view HQ status\n"
            "    faction hq locations    — available lots\n"
            "    faction hq purchase <type> <lot>  — establish HQ\n"
            "    faction hq sell         — disband HQ (25% refund)"
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
        "Select your faction specialization. Available once you've joined a "
        "faction that offers onboarding specializations.\n"
        "  Type `specialize <1-4>` — the roles available to your faction "
        "are listed when you run it."
    )
    usage = "specialize <1-4>"

    async def execute(self, ctx: CommandContext):
        # B.1.b.2 (Apr 29 2026): faction-aware dispatch. Routes to the
        # generic `complete_specialization` helper based on the player's
        # actual faction. Pre-B.1.b.2 callers landed only on Imperial.
        from engine.organizations import (
            complete_specialization,
            faction_has_specialization,
            get_specialization_config,
        )
        char = ctx.session.character
        faction_code = char.get("faction_id", "independent")

        if not faction_has_specialization(faction_code):
            await ctx.session.send_line(
                "  This command is only available to faction members "
                "whose faction offers onboarding specializations."
            )
            return

        # Build a faction-aware usage line on bad input
        cfg = get_specialization_config(faction_code) or {}
        labels = cfg.get("spec_labels", {})
        spec_map = cfg.get("spec_map", {})
        # Order: 1, 2, 3, 4 — display labels in numeric order.
        ordered_pairs = []
        for n in sorted(spec_map.keys()):
            spec_key = spec_map[n]
            ordered_pairs.append(f"{n} = {labels.get(spec_key, spec_key.title())}")
        usage_tail = "  ".join(ordered_pairs)

        arg = (ctx.args or "").strip()
        if not arg.isdigit() or int(arg) not in spec_map:
            await ctx.session.send_line(
                "  Usage: specialize <1-4>\n"
                f"  {usage_tail}"
            )
            return

        ok, msg = await complete_specialization(
            char, ctx.db, int(arg),
            faction_code=faction_code,
            session=ctx.session,
        )
        await ctx.session.send_line(f"  {msg}")
        if ok:
            await ctx.db.save_character(
                char["id"], attributes=char.get("attributes", "{}")
            )


class ReputationCommand(BaseCommand):
    key = "+reputation"
    aliases = ["+rep", "reputation"]
    help_text = (
        "View your faction reputation standings.\n"
        "\n"
        "USAGE:\n"
        "  +reputation          — overview of all faction standings\n"
        "  +reputation <code>   — detailed view for a specific faction\n"
        "\n"
        "Rep determines your rank, shop discounts, and NPC attitudes."
    )
    usage = "+reputation [faction_code]"

    async def execute(self, ctx: CommandContext):
        from engine.organizations import (
            format_reputation_overview,
            format_reputation_detail,
        )

        char = ctx.session.character
        args = (ctx.args or "").strip().lower()

        if args:
            result = await format_reputation_detail(char, args, ctx.db)
        else:
            result = await format_reputation_overview(char, ctx.db)

        await ctx.session.send_line(result)


# ═══════════════════════════════════════════════════════════════════════════
# +faction — Forwarding umbrella (S58)
# ═══════════════════════════════════════════════════════════════════════════
#
# `+faction` is a thin player-facing umbrella that fans out to the
# existing FactionCommand / GuildCommand / SpecializeCommand /
# ReputationCommand machinery.
#
# Design notes (mirrors +home pattern):
#   - FORWARDING umbrella. `valid_switches` enumerates verbs the
#     umbrella advertises in help; `_FACTION_SWITCH_IMPL` is the
#     smaller set of verbs the umbrella routes itself.
#   - `+faction` (bare) → FactionCommand status view.
#   - `+faction guild` / `specialize` / `reputation` → respective
#     dedicated commands.
#   - All other listed verbs (list/join/leave/roster/missions/claim/hq)
#     forward to FactionCommand which already dispatches them.

_FACTION_SWITCH_IMPL: dict = {}

_FACTION_ALIAS_TO_SWITCH: dict[str, str] = {
    "":      "view",
    "show":  "view",
    "info":  "view",
    "rep":   "reputation",
    "spec":  "specialize",
    # SYN.10 (May 25 2026): contest + resource_outlook subcommands
    # per design §2.6. Provides faction-scoped views of active
    # contests and weekly resource quality for owned regions.
    "contests":         "contest",
    "outlook":          "resource_outlook",
    "resource":         "resource_outlook",
    "quality":          "resource_outlook",
}


class FactionUmbrellaCommand(BaseCommand):
    """`+faction` umbrella — see module docstring for forwarding rules."""
    key = "+faction"
    aliases: list[str] = []
    help_text = (
        "Faction membership and operations. Try '+faction', "
        "'+faction list', '+faction join <code>', '+faction guild', "
        "'+faction reputation'. Type 'help +faction' for the full "
        "reference."
    )
    usage = "+faction [verb] [args]  — see 'help +faction'"
    valid_switches: list[str] = [
        "view", "guild", "specialize", "reputation",
        "list", "join", "leave", "roster", "missions",
        "claim", "hq",
        # SYN.10 (May 25 2026): contest + resource_outlook
        "contest", "resource_outlook",
    ]

    async def execute(self, ctx: CommandContext):
        args = ctx.args.strip() if ctx.args else ""
        first, _, rest = args.partition(" ")
        switch = _FACTION_ALIAS_TO_SWITCH.get(first.lower(), first.lower())

        # Direct routes handled by _FACTION_SWITCH_IMPL.
        impl = _FACTION_SWITCH_IMPL.get(switch)
        if impl is not None:
            await impl(ctx, rest)
            return

        # All other listed verbs forward to FactionCommand intact.
        if switch in self.valid_switches:
            forwarded = FactionCommand()
            ctx.args = args
            await forwarded.execute(ctx)
            return

        await ctx.session.send_line(self.help_text)


def _init_faction_switch_impl():
    """Wire forwarding handlers into _FACTION_SWITCH_IMPL."""
    async def _view(ctx, rest):
        cmd = FactionCommand()
        ctx.args = ""
        await cmd.execute(ctx)

    async def _guild(ctx, rest):
        cmd = GuildCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _specialize(ctx, rest):
        cmd = SpecializeCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _reputation(ctx, rest):
        cmd = ReputationCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    # SYN.10 (May 25 2026): contest + resource_outlook handlers.
    # Per design §2.6. Both surface engine.territory_display data
    # via faction-scoped renderers. Failure-tolerant: any engine
    # exception falls back to a one-liner so the umbrella doesn't
    # become a UX hole.
    async def _contest(ctx, rest):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game.")
            return
        org_code = char.get("faction_id")
        if not org_code or org_code == "independent":
            await ctx.session.send_line(
                "  You aren't a member of a faction. Join one to "
                "see contests."
            )
            return
        try:
            from engine.territory_display import (
                get_faction_contests_lines,
            )
            lines = await get_faction_contests_lines(
                ctx.db, org_code, ansi=True,
            )
        except Exception:
            log.exception("[+faction contest] render failed")
            await ctx.session.send_line(
                "  The contests display is offline. Try again."
            )
            return
        await ctx.session.send_line("")
        for line in lines:
            await ctx.session.send_line(line)

    async def _resource_outlook(ctx, rest):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game.")
            return
        org_code = char.get("faction_id")
        if not org_code or org_code == "independent":
            await ctx.session.send_line(
                "  You aren't a member of a faction. Join one to "
                "see resource outlook."
            )
            return
        try:
            from engine.territory_display import (
                get_faction_resource_outlook_lines,
            )
            lines = await get_faction_resource_outlook_lines(
                ctx.db, org_code, ansi=True,
            )
        except Exception:
            log.exception("[+faction resource_outlook] render failed")
            await ctx.session.send_line(
                "  The resource outlook is offline. Try again."
            )
            return
        await ctx.session.send_line("")
        for line in lines:
            await ctx.session.send_line(line)

    _FACTION_SWITCH_IMPL["view"] = _view
    _FACTION_SWITCH_IMPL["guild"] = _guild
    _FACTION_SWITCH_IMPL["specialize"] = _specialize
    _FACTION_SWITCH_IMPL["reputation"] = _reputation
    _FACTION_SWITCH_IMPL["contest"] = _contest
    _FACTION_SWITCH_IMPL["resource_outlook"] = _resource_outlook


_init_faction_switch_impl()


def register_faction_commands(registry):
    registry.register(FactionUmbrellaCommand())
    registry.register(FactionCommand())
    registry.register(GuildCommand())
    registry.register(SpecializeCommand())
    registry.register(ReputationCommand())
