# -*- coding: utf-8 -*-
"""
parser/title_commands.py — Drop 3 B3: vanity titles (+title).

The player-facing front end for the cosmetic-title sink in ``engine/titles.py``.
Buy an honorific (a pure credit sink), then wear / switch / clear it; the worn
title surfaces on ``+who``, ``+sheet``, and the room "is here" listing. No
payout, no mechanical benefit, nothing to farm.

Commands:
    +title                — show your worn title, owned titles, and the catalog
    +title buy <key>      — buy a title (debits the cost; auto-wears it)
    +title set <key>      — wear a title you already own
    +title clear          — stop wearing a title
"""

import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi
from engine.titles import (
    purchase_title, set_worn_title, title_status_lines, catalog_lines,
)

log = logging.getLogger(__name__)


class TitleCommand(BaseCommand):
    key = "+title"
    aliases = ["title", "+titles", "titles"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Vanity titles — buy and wear an honorific. Pure cosmetic standing:\n"
        "no payout, no mechanical benefit. The worn title shows on +who,\n"
        "+sheet, and when others look at the room.\n"
        "\n"
        "  +title             — your title, what you own, and the catalog\n"
        "  +title buy <key>   — buy a title (auto-wears it)\n"
        "  +title set <key>   — wear a title you already own\n"
        "  +title clear       — stop wearing a title"
    )
    usage = "+title [buy <key> | set <key> | clear]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in-game.")
            return

        parts = (ctx.args or "").strip().split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub in ("buy", "purchase"):
            await self._buy(ctx, char, rest)
        elif sub in ("set", "wear", "use"):
            await self._set(ctx, char, rest)
        elif sub in ("clear", "remove", "off", "none"):
            await self._clear(ctx, char)
        else:
            await self._status(ctx, char)

    async def _status(self, ctx, char):
        lines = [ansi.header("=== Vanity Titles ===")]
        lines.extend(title_status_lines(char))
        lines.append("")
        lines.append("  " + ansi.dim("Catalog  (+title buy <key>):"))
        for row in catalog_lines(char):
            if row["mark"] == "owned":
                tag = ansi.green("owned ")
            elif row["mark"] == "buy":
                tag = ansi.yellow("buy   ")
            else:
                tag = ansi.dim("locked")
            cost_str = ansi.dim("{:,} cr".format(row["cost"]))
            key_str = ansi.dim("(" + row["key"] + ")")
            label = ansi.bright_white(row["label"])
            lines.append("    [{}] {}  {}  {}".format(
                tag, label, cost_str, key_str))
            lines.append("        " + ansi.dim(row["blurb"]))
        lines.append("")
        await ctx.session.send_line("\n".join(lines))

    async def _buy(self, ctx, char, key):
        if not key:
            await ctx.session.send_line("  Usage: +title buy <key>")
            return
        res = await purchase_title(ctx.db, char, key)
        if res.get("ok"):
            await ctx.session.send_line(ansi.success(
                "  You acquire the title '{}' for {:,} credits "
                "— and now wear it.".format(res["label"], res["cost"])))
            return
        reason = res.get("reason")
        if reason == "unknown":
            await ctx.session.send_line(
                "  No such title. Use +title to see the catalog.")
        elif reason == "owned":
            await ctx.session.send_line(
                "  You already hold '{}'. Use +title set {} to wear it."
                .format(res["label"], key.strip().lower()))
        elif reason == "insufficient":
            await ctx.session.send_line(ansi.error(
                "  '{}' costs {:,} credits — you're {:,} short."
                .format(res["label"], res["cost"], res["short"])))
        else:
            await ctx.session.send_line(ansi.error(
                "  The purchase couldn't be completed. "
                "No credits were spent."))

    async def _set(self, ctx, char, key):
        if not key:
            await ctx.session.send_line("  Usage: +title set <key>")
            return
        res = await set_worn_title(ctx.db, char, key)
        if res.get("ok"):
            await ctx.session.send_line(ansi.success(
                "  You now wear '{}'.".format(res["label"])))
            return
        if res.get("reason") == "not_owned":
            await ctx.session.send_line(
                "  You don't own '{}'. Buy it first with +title buy {}."
                .format(res.get("label", key), key.strip().lower()))
        else:
            await ctx.session.send_line(ansi.error(
                "  Couldn't change your title right now."))

    async def _clear(self, ctx, char):
        res = await set_worn_title(ctx.db, char, None)
        if res.get("ok"):
            await ctx.session.send_line("  You set aside your title.")
        else:
            await ctx.session.send_line(ansi.error(
                "  Couldn't change your title right now."))


def register_title_commands(registry):
    """Register the +title vanity-title command (Drop 3 B3)."""
    registry.register(TitleCommand())
    log.info("[titles] +title command registered")
