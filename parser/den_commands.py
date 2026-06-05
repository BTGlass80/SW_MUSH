# -*- coding: utf-8 -*-
"""
parser/den_commands.py — Drop 3 A5: sabacc dens (+den).

Front end for the criminal-empire loop in ``engine/dens.py``. A sufficiently-
ranked Hutt-cartel member establishes a den in a cantina room; while a room is a
den, the sabacc house rake (after the city's slice) flows to the cartel org's
treasury (see ``parser/sabacc_commands.py``).

Commands:
    +den               - show this room's den (and your cartel's dens)
    +den establish     - establish a cartel den here (cantina; setup cost)
    +den abandon       - abandon your cartel's den here (no refund)
"""

import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi
from engine.dens import (
    establish_den, abandon_den, get_room_den, get_org_dens,
    DEN_SETUP_COST, DEN_ESTABLISH_MIN_RANK, HUTT_ORG_CODE,
)

log = logging.getLogger(__name__)


class DenCommand(BaseCommand):
    key = "+den"
    aliases = ["den"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "Sabacc dens - a Hutt cartel den in a cantina collects the sabacc\n"
        "house rake into the cartel treasury. Establishing one needs cartel\n"
        "rank {rank}+ and a {cost:,}-credit stake.\n"
        "\n"
        "  +den            - this room's den, and your cartel's dens\n"
        "  +den establish  - establish a den here (cantina only)\n"
        "  +den abandon    - abandon your cartel's den here (no refund)"
    ).format(rank=DEN_ESTABLISH_MIN_RANK, cost=DEN_SETUP_COST)
    usage = "+den [establish | abandon]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in-game.")
            return
        sub = (ctx.args or "").strip().lower()
        if sub in ("establish", "open", "claim"):
            await self._establish(ctx, char)
        elif sub in ("abandon", "close", "drop"):
            await self._abandon(ctx, char)
        else:
            await self._status(ctx, char)

    async def _status(self, ctx, char):
        lines = [ansi.header("=== Sabacc Den ===")]
        den = await get_room_den(ctx.db, char.get("room_id"))
        if den:
            lines.append(
                "  This room is a den run by {} - the sabacc rake here "
                "flows to its treasury.".format(den.get("org_code", "a cartel")))
        else:
            lines.append("  This room is not a den.")
        # Your cartel's dens, if you're a member.
        try:
            org = await ctx.db.get_organization(HUTT_ORG_CODE)
            mem = await ctx.db.get_membership(char["id"], org["id"]) if org else None
            if org and mem:
                dens = await get_org_dens(ctx.db, org["id"])
                lines.append("  Your cartel operates {} den(s).".format(len(dens)))
        except Exception:
            log.warning("[dens] status org lookup failed", exc_info=True)
        await ctx.session.send_line("\n".join(lines))

    async def _establish(self, ctx, char):
        res = await establish_den(ctx.db, char)
        if res.get("ok"):
            await ctx.session.send_line(ansi.success(
                "  Den established for {} ({:,} credits). The sabacc rake in "
                "this cantina now flows to the cartel treasury.".format(
                    res.get("org_name", "the cartel"), res["cost"])))
            return
        reason = res.get("reason")
        msgs = {
            "not_cantina": "  A den can only be run out of a cantina.",
            "not_member": "  Only the Hutt cartel runs dens - and only its members.",
            "rank": "  You lack the standing. Cartel rank {}+ is required.".format(
                DEN_ESTABLISH_MIN_RANK),
            "already_den": "  This cantina already has a den.",
            "insufficient": "  A den takes a {:,}-credit stake - you're {:,} short.".format(
                res.get("cost", DEN_SETUP_COST), res.get("short", 0)),
        }
        await ctx.session.send_line(ansi.error(
            msgs.get(reason, "  The den couldn't be established. No credits were spent.")))

    async def _abandon(self, ctx, char):
        res = await abandon_den(ctx.db, char)
        if res.get("ok"):
            await ctx.session.send_line(
                "  Den abandoned. The rake here no longer flows to the cartel. "
                "(No refund - the stake is spent.)")
            return
        reason = res.get("reason")
        msgs = {
            "no_den": "  There's no den here to abandon.",
            "rank": "  You lack the standing to close this den.",
            "not_yours": "  This den isn't run by your cartel.",
        }
        await ctx.session.send_line(ansi.error(
            msgs.get(reason, "  Couldn't change the den right now.")))


def register_den_commands(registry):
    """Register the +den sabacc-den command (Drop 3 A5)."""
    registry.register(DenCommand())
    log.info("[dens] +den command registered")
