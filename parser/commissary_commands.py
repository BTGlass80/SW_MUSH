# -*- coding: utf-8 -*-
"""
parser/commissary_commands.py — Drop 3 A4 (commissary): +commissary.

The player-facing front end for the faction requisition sink in
``engine/commissary.py``. A sworn faction member browses rank-appropriate gear
and requisitions it for credits (a ``commissary_purchase`` sink). Resolves the
member's rank from their org membership.

Commands:
    +commissary              — show your faction's requisition list + prices
    +commissary buy <key>    — requisition an item (debits the cost)
"""

import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi
from engine.commissary import (
    faction_has_commissary, commissary_status_lines, purchase_commissary,
    commissary_vendor_payload, sell_commissary, COMMISSARY_SELLBACK_RATE,
)

log = logging.getLogger(__name__)


async def _resolve_faction_rank(ctx, char):
    """Return (faction_code, rank_level). rank_level is 0 if no membership row."""
    faction_code = (char.get("faction_id") or "independent")
    rank_level = 0
    try:
        org = await ctx.db.get_organization(faction_code)
        if org:
            mem = await ctx.db.get_membership(char["id"], org["id"])
            if mem is not None:
                rank_level = int(mem["rank_level"] or 0)
    except Exception:
        log.warning("[commissary] rank lookup failed for char %s",
                    char.get("id"), exc_info=True)
    return faction_code, rank_level


class CommissaryCommand(BaseCommand):
    key = "+commissary"
    aliases = ["commissary", "+requisition", "requisition"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Faction commissary — requisition rank-appropriate gear for credits, at\n"
        "a requisition rate below the open market. Gear unlocks with your\n"
        "faction rank; the Jedi Order keeps no commissary.\n"
        "\n"
        "  +commissary            — your faction's requisition list + prices\n"
        "  +commissary buy <key>  — requisition an item\n"
        "  +commissary sell <key> — sell faction gear back to the commissary\n"
        "                           for a partial refund (faction gear can't\n"
        "                           be sold to ordinary vendors)"
    )
    usage = "+commissary [buy <key> | sell <key>]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in-game.")
            return

        faction_code = (char.get("faction_id") or "independent")
        if not faction_code or faction_code == "independent":
            await ctx.session.send_line("  You're not in a faction.")
            return

        parts = (ctx.args or "").strip().split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub in ("buy", "requisition", "req", "purchase"):
            await self._buy(ctx, char, rest)
        elif sub in ("sell", "sellback", "refund"):
            await self._sell(ctx, char, rest)
        else:
            await self._status(ctx, char)

    async def _status(self, ctx, char):
        faction_code, rank_level = await _resolve_faction_rank(ctx, char)
        try:
            balance = int(char.get("credits") or 0)
        except (TypeError, ValueError):
            balance = 0
        lines = [ansi.header("=== Faction Commissary ===")]
        rows = commissary_status_lines(faction_code, rank_level, balance)
        for row in rows:
            if isinstance(row, str):
                lines.append(row)
                continue
            if row["mark"] == "buy":
                tag = ansi.yellow("buy   ")
            elif row["mark"] == "rank":
                tag = ansi.dim("rank %d" % row["min_rank"])
            else:
                tag = ansi.dim("short ")
            cost_str = ansi.dim("{:,} cr".format(row["cost"]))
            key_str = ansi.dim("(" + row["key"] + ")")
            name = ansi.bright_white(row["name"])
            lines.append("    [{}] {}  {}  {}".format(tag, name, cost_str, key_str))
            if row.get("desc"):
                lines.append("        " + ansi.dim(row["desc"]))
        lines.append("")
        await ctx.session.send_line("\n".join(lines))
        # Web panel: push vendor payload alongside the text block (WS only;
        # Telnet keeps text above as the graceful-degradation surface).
        try:
            from server.session import Protocol
            if ctx.session.protocol == Protocol.WEBSOCKET:
                await ctx.session.send_json(
                    "shop_state",
                    commissary_vendor_payload(faction_code, rank_level, balance),
                )
        except Exception:
            # Non-critical — text output already sent. Log at debug so a
            # broken web push is visible without breaking the text surface
            # (matches the bounty/inventory/crafting best-effort idiom).
            log.debug("[commissary] list shop_state push failed", exc_info=True)

    async def _buy(self, ctx, char, key):
        if not key:
            await ctx.session.send_line("  Usage: +commissary buy <key>")
            return
        faction_code, rank_level = await _resolve_faction_rank(ctx, char)
        if not faction_has_commissary(faction_code):
            await ctx.session.send_line(
                "  Your faction does not maintain a commissary.")
            return
        res = await purchase_commissary(ctx.db, char, faction_code, rank_level, key)
        if res.get("ok"):
            await ctx.session.send_line(ansi.success(
                "  Requisitioned {} for {:,} credits.".format(
                    res["name"], res["cost"])))
            # Re-push the vendor panel so balances/marks refresh in the live web
            # panel; balance is read from char AFTER the buy (purchase_commissary
            # updated char["credits"] on success).
            try:
                from server.session import Protocol
                if ctx.session.protocol == Protocol.WEBSOCKET:
                    updated_balance = int(char.get("credits") or 0)
                    await ctx.session.send_json(
                        "shop_state",
                        commissary_vendor_payload(
                            faction_code, rank_level, updated_balance),
                    )
            except Exception:
                # Non-critical — purchase already confirmed above.
                log.debug("[commissary] buy shop_state push failed", exc_info=True)
            return
        reason = res.get("reason")
        if reason == "no_commissary":
            await ctx.session.send_line(
                "  Your faction does not maintain a commissary.")
        elif reason == "rank_locked":
            await ctx.session.send_line(
                "  '{}' requires rank {}.".format(
                    res.get("name", key), res.get("min_rank", "?")))
        elif reason == "unknown":
            await ctx.session.send_line(
                "  No such item. Use +commissary to see the requisition list.")
        elif reason == "insufficient":
            await ctx.session.send_line(ansi.error(
                "  '{}' costs {:,} credits — you're {:,} short.".format(
                    res["name"], res["cost"], res["short"])))
        else:
            await ctx.session.send_line(ansi.error(
                "  The requisition couldn't be completed. "
                "No credits were spent."))


    async def _sell(self, ctx, char, key):
        if not key:
            await ctx.session.send_line("  Usage: +commissary sell <key>")
            return
        faction_code, _rank = await _resolve_faction_rank(ctx, char)
        if not faction_has_commissary(faction_code):
            await ctx.session.send_line(
                "  Your faction does not maintain a commissary.")
            return
        res = await sell_commissary(ctx.db, char, faction_code, key)
        if res.get("ok"):
            pct = int(COMMISSARY_SELLBACK_RATE * 100)
            await ctx.session.send_line(ansi.success(
                "  Sold {} back to the commissary for {:,} credits "
                "({}% requisition refund).".format(
                    res["name"], res["refund"], pct)))
            # Refresh the web vendor panel balance.
            try:
                from server.session import Protocol
                if ctx.session.protocol == Protocol.WEBSOCKET:
                    _, rank_level = await _resolve_faction_rank(ctx, char)
                    await ctx.session.send_json(
                        "shop_state",
                        commissary_vendor_payload(
                            faction_code, rank_level,
                            int(char.get("credits") or 0)),
                    )
            except Exception:
                # Non-critical — sellback already confirmed above.
                log.debug("[commissary] sell shop_state push failed", exc_info=True)
            return
        reason = res.get("reason")
        if reason == "no_commissary":
            await ctx.session.send_line(
                "  Your faction does not maintain a commissary.")
        elif reason == "not_owned":
            await ctx.session.send_line(
                "  You're not carrying any faction-issued '{}'. "
                "(Only commissary/faction gear sells back here.)".format(key))
        elif reason == "wrong_channel":
            await ctx.session.send_line(ansi.error(
                "  That's {}-issued gear — sell it back through THEIR "
                "commissary, not yours.".format(
                    res.get("item_faction", "another faction"))))
        else:
            await ctx.session.send_line(ansi.error(
                "  The sellback couldn't be completed. "
                "Nothing was changed."))


def register_commissary_commands(registry):
    """Register the +commissary faction requisition command (Drop 3 A4)."""
    registry.register(CommissaryCommand())
    log.info("[commissary] +commissary command registered")
