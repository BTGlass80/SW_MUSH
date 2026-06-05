# -*- coding: utf-8 -*-
"""
parser/finances_commands.py — player-facing credit ledger (Drop 1.c).

The player-side companion to the admin ``@economy`` dashboard: a character can
review their own credit faucets and sinks, grouped by source, over a recent
window. Consumes ``Database.get_char_credit_breakdown`` (which was built for
exactly this command). Read-only; fails open to a friendly empty summary.

Commands:
    +finances            — your credit flow over the last 24h (default)
    +finances hour       — last hour
    +finances week       — last 7 days
"""

import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)

_WINDOWS = {
    "hour": 3600, "h": 3600, "1h": 3600,
    "day": 86400, "d": 86400, "24h": 86400, "today": 86400,
    "week": 604800, "w": 604800, "7d": 604800,
}
_LABEL = {3600: "the last hour", 86400: "the last 24 hours",
          604800: "the last 7 days"}


def _pretty(source: str) -> str:
    """Turn an internal source tag into a readable label."""
    return (source or "?").replace("_", " ").strip().title()


class FinancesCommand(BaseCommand):
    key = "+finances"
    aliases = ["finances", "+ledger"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Review your own credit flow — what you've earned and spent, grouped\n"
        "by source, over a recent window.\n"
        "\n"
        "  +finances        — the last 24 hours (default)\n"
        "  +finances hour   — the last hour\n"
        "  +finances week   — the last 7 days"
    )
    usage = "+finances [hour|day|week]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in-game.")
            return

        arg = (ctx.args or "").strip().lower()
        seconds = _WINDOWS.get(arg, 86400)
        window_label = _LABEL.get(seconds, "the last 24 hours")

        try:
            bd = await ctx.db.get_char_credit_breakdown(char["id"], seconds)
        except Exception:
            log.debug("[finances] breakdown failed; failing open", exc_info=True)
            bd = {"faucet_total": 0, "sink_total": 0, "net": 0,
                  "txn_count": 0, "faucets": [], "sinks": []}

        try:
            bal = int(char.get("credits") or 0)
        except (TypeError, ValueError):
            bal = 0

        faucet = int(bd.get("faucet_total", 0))
        sink = int(bd.get("sink_total", 0))          # already negative
        net = int(bd.get("net", faucet + sink))
        cnt = int(bd.get("txn_count", 0))

        lines = [ansi.bold(f"  Your finances — {window_label}")]
        lines.append(f"  Balance:          {bal:,} cr")

        if cnt == 0:
            lines.append("  No credit activity in this window.")
            await ctx.session.send_line("\n".join(lines))
            return

        net_sign = "+" if net >= 0 else ""
        lines.append(f"  Earned (faucets): {ansi.GREEN}+{faucet:,} cr{ansi.RESET}")
        lines.append(f"  Spent (sinks):    {ansi.RED}{sink:,} cr{ansi.RESET}")
        lines.append(f"  Net:              {net_sign}{net:,} cr   "
                     f"({cnt} transaction{'s' if cnt != 1 else ''})")

        faucets = bd.get("faucets") or []
        if faucets:
            lines.append("  Top sources:")
            for src, total in faucets[:5]:
                lines.append(f"    {ansi.GREEN}+{total:>9,}{ansi.RESET}  {_pretty(src)}")

        sinks = bd.get("sinks") or []
        if sinks:
            lines.append("  Top spending:")
            for src, total in sinks[:5]:   # total is negative
                lines.append(f"    {ansi.RED}{total:>10,}{ansi.RESET}  {_pretty(src)}")

        await ctx.session.send_line("\n".join(lines))


def register_finances_commands(registry):
    """Register the +finances player ledger command (Drop 1.c)."""
    registry.register(FinancesCommand())
    log.info("[finances] +finances command registered")
