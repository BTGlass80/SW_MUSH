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
    # S58 — `+faction` alias moved to FactionUmbrellaCommand. Umbrella's
    # default (no switch) routes back to this class for backward compat.
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
        "  faction seize             — seize rival room after killing its guard (lawless only)\n"
        "\n"
        "You can only belong to ONE faction at a time.\n"
        "Switching factions has a 7-day cooldown."
    )
    usage = "faction [list|join|leave|info|roster|missions|channel|invest|influence|claim|unclaim|guard|armory]"

    async def execute(self, ctx: CommandContext):
        """Dispatch to sub-command handlers. Phase 3 C4 refactor."""
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
            "guard": self._cmd_guard,
            "armory": self._cmd_armory,
            "seize": self._cmd_seize,
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
            f"requisition, invest, influence, claim, unclaim, guard, armory, seize, hq"
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
            )
        return

        # ── faction leave ──

    async def _cmd_leave(self, ctx, char, rest):
        ok, msg = await leave_faction(char, ctx.db)
        await ctx.session.send_line(f"  {msg}")
        return

        # ── faction info <code> ──

    async def _cmd_info(self, ctx, char, rest):
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

    async def _cmd_unclaim(self, ctx, char, rest):
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

    async def _cmd_guard(self, ctx, char, rest):
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
        # Hostile takeover of a rival-claimed room after killing its guard.
        # Lawless zones only. Requires 50+ influence and 5,000cr treasury.

    async def _cmd_seize(self, ctx, char, rest):
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


def register_faction_commands(registry):
    """Register faction / guild / reputation commands.

    S58 — +faction umbrella registered first.
    """
    registry.register(FactionUmbrellaCommand())
    registry.register(FactionCommand())
    registry.register(GuildCommand())
    registry.register(SpecializeCommand())
    registry.register(ReputationCommand())


# ═══════════════════════════════════════════════════════════════════════════
# +faction — Umbrella for faction/guild/reputation verbs (S58)
# ═══════════════════════════════════════════════════════════════════════════

_FACTION_SWITCH_IMPL: dict = {}

_FACTION_ALIAS_TO_SWITCH: dict[str, str] = {
    # Faction view — default (absorbed from FactionCommand aliases)
    "faction": "view", "fac": "view",
    # Guild
    "guild": "guild",
    # Specialize (skill specialization within a faction)
    "specialize": "specialize", "specialise": "specialize",
    # Reputation
    "reputation": "reputation", "rep": "reputation",
}


class FactionUmbrellaCommand(BaseCommand):
    """`+faction` umbrella — faction, guild, specialize, reputation.

    Canonical                Bare aliases (still work)
    ---------------------    ---------------------------
    +faction                 faction, fac (view your faction — default)
    +faction/view            same as default
    +faction/guild           guild, +guild
    +faction/specialize      specialize, specialise
    +faction/reputation      reputation, +reputation, +rep, rep

    UNKNOWN-SWITCH FORWARDING (S58):
    FactionCommand uses positional-argument subcommands (e.g.
    `faction join rebel`, `faction list`, `faction roster`) rather
    than switch syntax. To preserve the existing `+faction/<sub>`
    form from pre-S58 (when `+faction` was just an alias for
    `FactionCommand`), any switch NOT in valid_switches is forwarded
    to FactionCommand with the switch name prepended to ctx.args.
    So `+faction/join rebel` reaches FactionCommand as
    `faction join rebel` and works as before.
    """

    key = "+faction"
    aliases = [
        "fac",
        "guild",
        "specialize", "specialise",
        "reputation", "rep",
    ]
    help_text = (
        "All faction verbs live under +faction/<switch>. "
        "Bare verbs (faction, guild, reputation) still work."
    )
    usage = "+faction[/switch] [args]  — see 'help +faction'"
    # NOTE: Explicit umbrella switches. Other switches (join, leave,
    # list, roster, etc.) are forwarded to FactionCommand's positional
    # parser rather than being listed here.
    valid_switches = ["view", "guild", "specialize", "reputation",
                      # FactionCommand subcommands — forwarded
                      "list", "join", "leave", "info", "roster",
                      "missions", "channel", "requisition",
                      "invest", "influence", "territory", "terr",
                      "claim", "unclaim", "guard", "armory", "seize",
                      "hq",
                      # Leader subs (forwarded to FactionLeaderCommand via
                      # FactionCommand's own dispatch)
                      "promote", "demote", "kick", "invite", "motd",
                      "setrank", "disband", "treasury", "payroll"]

    async def execute(self, ctx: CommandContext):
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            switch = _FACTION_ALIAS_TO_SWITCH.get(typed, "view")

        # First: check the real umbrella switches
        impl = _FACTION_SWITCH_IMPL.get(switch)
        if impl is not None:
            await impl.execute(ctx)
            return

        # Fallback: forward to FactionCommand with switch prepended to args
        # Preserves pre-S58 `+faction/join rebel` → `faction join rebel`
        args_before = ctx.args or ""
        ctx.args = f"{switch} {args_before}".strip()
        ctx.switches = []
        try:
            await FactionCommand().execute(ctx)
        finally:
            # Restore so callers don't see the mutation
            ctx.args = args_before
            ctx.switches = [switch]


def _init_faction_switch_impl():
    global _FACTION_SWITCH_IMPL
    _FACTION_SWITCH_IMPL = {
        "view":       FactionCommand(),
        "guild":      GuildCommand(),
        "specialize": SpecializeCommand(),
        "reputation": ReputationCommand(),
    }


_init_faction_switch_impl()
