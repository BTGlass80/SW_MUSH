# -*- coding: utf-8 -*-
"""
parser/hunting_commands.py — +hunting: the solo-PvE hunting log (2026-06-21).

Read-only front end for engine/hunting_rewards.py. Shows the player's lifetime
kill tally (the prestige axis), today's grind income against the daily soft cap
(the credit trickle), and the next milestone title. No subcommands, no payout
here — the rewards accrue automatically on a huntable-mob defeat.
"""

import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi
from engine.hunting_rewards import hunting_log_view, TITLE_THRESHOLDS

log = logging.getLogger(__name__)


class HuntingCommand(BaseCommand):
    key = "+hunting"
    aliases = ["hunting", "+huntlog", "huntlog"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Your hunting log — the tally of hostiles you've felled out in the\n"
        "field. Defeating an ordinary roaming hostile pays a small credit\n"
        "trickle (capped per day) and counts toward milestone hunter titles.\n"
        "It is a way to earn a little when you're playing solo; roleplay is\n"
        "still the real path to advancement (hunting grants NO character points).\n"
        "\n"
        "  +hunting   — show your kill tally, today's take, and your next title"
    )
    usage = "+hunting"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in-game.")
            return

        view = hunting_log_view(char)
        kills = view["kills"]
        await ctx.session.send_line(ansi.dim(
            "─────────────  HUNTING LOG  ─────────────"))
        await ctx.session.send_line(
            f"  Quarry felled (lifetime): {ansi.bold(str(kills))}")
        cap = view["daily_cap"]
        today = view["daily_credits"]
        if today >= cap:
            await ctx.session.send_line(
                f"  Today's take: {today:,} cr  "
                + ansi.dim(f"(daily {cap:,} cr reached — only token rewards "
                           "until tomorrow)"))
        else:
            await ctx.session.send_line(
                f"  Today's take: {today:,} / {cap:,} cr")

        nxt = view["next_threshold"]
        if nxt is not None:
            remaining = nxt - kills
            await ctx.session.send_line(
                f"  Next milestone: {remaining} more to reach {nxt} felled.")
        else:
            top = TITLE_THRESHOLDS[-1][0]
            await ctx.session.send_line(ansi.dim(
                f"  You have passed every hunting milestone ({top}+). "
                "You stand at the apex."))
        await ctx.session.send_line(ansi.dim(
            "  Earned hunter titles wear via +title wear <key>. "
            "Roleplay remains the path to advancement."))


def register_hunting_commands(registry):
    """Register the +hunting solo-PvE log command (2026-06-21)."""
    registry.register(HuntingCommand())
    log.info("[hunting] +hunting command registered")
