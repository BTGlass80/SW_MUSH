# -*- coding: utf-8 -*-
"""
parser/insurance_commands.py — Drop 3 B4: gear insurance (+insure).

Player front end for the loadout-protection sink in ``engine/gear_insurance.py``.
Buy a one-shot policy (a pure credit sink) that keeps your loose loadout on you
the next time you die in a lawless/contested zone; cancel it (no refund) to opt
back into the gear-loss risk. There is no cash payout - only the loadout is
protected (a payout would be a suicide-faucet; see the engine module).

Commands:
    +insure            - show your coverage, the premium, and what it protects
    +insure buy        - buy a one-shot policy (debits the premium)
    +insure cancel     - drop coverage (no refund)
"""

import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi
from engine.gear_insurance import (
    purchase_gear_insurance, cancel_gear_insurance, insure_status_lines,
)

log = logging.getLogger(__name__)


class InsureCommand(BaseCommand):
    key = "+insure"
    aliases = ["insure", "+insurance", "insurance"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Gear insurance - a one-shot policy that protects your loose\n"
        "loadout the next time you die in a lawless or contested zone\n"
        "(the gear stays on you instead of dropping to a lootable corpse,\n"
        "and the policy is then spent). Equipped gear is always kept. There\n"
        "is no cash payout - only the loadout is protected.\n"
        "\n"
        "  +insure          - your coverage and the premium\n"
        "  +insure buy      - buy a one-shot policy\n"
        "  +insure cancel   - drop coverage (no refund)"
    )
    usage = "+insure [buy | cancel]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in-game.")
            return

        sub = (ctx.args or "").strip().lower()
        if sub in ("buy", "purchase"):
            await self._buy(ctx, char)
        elif sub in ("cancel", "drop", "stop", "off"):
            await self._cancel(ctx, char)
        else:
            await self._status(ctx, char)

    async def _status(self, ctx, char):
        lines = [ansi.header("=== Gear Insurance ===")]
        lines.extend(insure_status_lines(char))
        await ctx.session.send_line("\n".join(lines))

    async def _buy(self, ctx, char):
        res = await purchase_gear_insurance(ctx.db, char)
        if res.get("ok"):
            await ctx.session.send_line(ansi.success(
                "  Coverage bought for {:,} credits. Your loose loadout is "
                "protected on your next lawless/contested death.".format(
                    res["cost"])))
            return
        reason = res.get("reason")
        if reason == "already":
            await ctx.session.send_line(
                "  You already hold a policy. Use +insure to review it.")
        elif reason == "insufficient":
            await ctx.session.send_line(ansi.error(
                "  A policy costs {:,} credits - you're {:,} short.".format(
                    res["cost"], res["short"])))
        else:
            await ctx.session.send_line(ansi.error(
                "  The purchase couldn't be completed. No credits were spent."))

    async def _cancel(self, ctx, char):
        res = await cancel_gear_insurance(ctx.db, char)
        if res.get("ok"):
            await ctx.session.send_line(
                "  Coverage dropped. (No refund - the premium bought the "
                "option.) Your loose gear will drop on death again.")
            return
        if res.get("reason") == "none":
            await ctx.session.send_line(
                "  You don't hold a policy. +insure buy starts one.")
        else:
            await ctx.session.send_line(ansi.error(
                "  Couldn't change your coverage right now."))


def register_insurance_commands(registry):
    """Register the +insure gear-insurance command (Drop 3 B4)."""
    registry.register(InsureCommand())
    log.info("[gear_insurance] +insure command registered")
