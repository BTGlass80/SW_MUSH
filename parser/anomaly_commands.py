# -*- coding: utf-8 -*-
"""
parser/anomaly_commands.py — wilderness anomaly parser surface
(SYN.7.a, 2026-05-25).

Two commands:
  * ``anomalies`` — list active anomalies in the caller's current
    wilderness region.
  * ``investigate <id>`` — attempt to resolve a specific anomaly.

Thin wrappers over ``engine.wilderness_anomalies``. The engine
module owns all gating + reward logic.

Per design §2.8, the news broadcast on spawn is the primary
discoverability surface; the ``anomalies`` command is the secondary
"what's active right now?" check.
"""
from __future__ import annotations

import logging

from parser.commands import AccessLevel, BaseCommand, CommandContext

log = logging.getLogger(__name__)


class AnomaliesCommand(BaseCommand):
    """List active wilderness anomalies in the caller's region."""

    key = "anomalies"
    aliases = ["anom"]
    access_level = AccessLevel.PLAYER
    help_text = (
        "List active wilderness anomalies in your current region.\n"
        "\n"
        "  Anomalies are temporary, time-limited events that spawn in\n"
        "  wilderness regions — stranded patrols, salvage caches,\n"
        "  raider parties, crashed reconnaissance droids. They are\n"
        "  resolvable for credits, crafting materials, and faction\n"
        "  influence.\n"
        "\n"
        "  To resolve an anomaly, travel to its anchor location and\n"
        "  run 'investigate <id>'.\n"
        "\n"
        "  Anomalies last ~30 minutes after spawning.\n"
        "\n"
        "EXAMPLES:\n"
        "  anomalies\n"
        "  investigate 3"
    )
    usage = "anomalies"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game.")
            return

        room_id = char.get("room_id")
        if not room_id:
            await ctx.session.send_line("  You are nowhere.")
            return

        # Resolve room → region
        try:
            from engine.territory import _resolve_room_region
            region_slug, _zid = await _resolve_room_region(
                ctx.db, int(room_id),
            )
        except Exception:
            log.warning("[anomalies] region resolve failed", exc_info=True)
            region_slug = None

        if not region_slug:
            await ctx.session.send_line(
                "  \033[2mAnomalies appear in wilderness regions. "
                "You aren't in one.\033[0m"
            )
            return

        from engine.wilderness_anomalies import get_anomalies_for_region
        active = get_anomalies_for_region(region_slug)

        region_label = region_slug.replace("_", " ").title()
        await ctx.session.send_line(
            f"  \033[1;36mActive Anomalies — {region_label}\033[0m"
        )
        if not active:
            await ctx.session.send_line(
                "  \033[2m(No active anomalies. They spawn periodically; "
                "check news broadcasts.)\033[0m"
            )
            return

        for a in active:
            import time as _time
            remaining_min = max(0, int((a.expiry - _time.time()) / 60))
            await ctx.session.send_line(
                f"  \033[1;33m#{a.id}\033[0m  "
                f"\033[1m{a.display_name}\033[0m  "
                f"\033[2m(~{remaining_min}m left)\033[0m"
            )
            await ctx.session.send_line(
                f"      \033[2m{a.template.get('short_desc', '')}\033[0m"
            )
            await ctx.session.send_line("")


class InvestigateCommand(BaseCommand):
    """Attempt to resolve a specific wilderness anomaly."""

    key = "investigate"
    aliases = []
    access_level = AccessLevel.PLAYER
    help_text = (
        "Investigate a wilderness anomaly to attempt resolution.\n"
        "\n"
        "  You must be standing at the anomaly's anchor location.\n"
        "  Use 'anomalies' to see the active list in your region\n"
        "  and 'look' at the anchor room before acting.\n"
        "\n"
        "  Resolution rolls a relevant skill. Success grants credits,\n"
        "  crafting materials, and a small influence delta for your\n"
        "  faction. Partial failure still grants a smaller reward.\n"
        "\n"
        "USAGE:\n"
        "  investigate <id>\n"
        "\n"
        "EXAMPLES:\n"
        "  anomalies\n"
        "  investigate 3"
    )
    usage = "investigate <id>"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game.")
            return

        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line(
                "  Usage: investigate <id>\n"
                "  Use 'anomalies' to see active anomalies in your region."
            )
            return

        try:
            anomaly_id = int(args.split()[0])
        except ValueError:
            await ctx.session.send_line(
                f"  '{args}' is not a valid anomaly id. "
                f"Use 'anomalies' for the list."
            )
            return

        try:
            from engine.wilderness_anomalies import resolve_anomaly
            result = await resolve_anomaly(
                ctx.db, char, anomaly_id,
                session_mgr=getattr(ctx, "session_mgr", None),
            )
        except Exception:
            log.exception("[investigate] resolve_anomaly raised")
            await ctx.session.send_line(
                "  Something disrupts your effort. Try again."
            )
            return

        msg = result.get("msg") or "You investigate."
        if result.get("ok") and result.get("success"):
            color = "\033[1;32m"  # green for full success
        elif result.get("ok"):
            color = "\033[1;33m"  # yellow for partial / engaged
        else:
            color = "\033[1;31m"  # red for rejection
        await ctx.session.send_line(f"  {color}{msg}\033[0m")

        # Mode-specific output.
        mode = result.get("mode", "skill")

        if mode == "combat" and result.get("ok"):
            # SYN.7.a.fix: combat-mode anomaly engaged. Surface the
            # template's long_desc so the player gets the narrative
            # set-piece, then nudge them toward `attack`.
            long_desc = result.get("long_desc", "")
            if long_desc:
                await ctx.session.send_line("")
                await ctx.session.send_line(f"  {long_desc}")
            await ctx.session.send_line(
                "  \033[2mUse 'attack <target>' to engage. The reward "
                "pays out when the last hostile is down.\033[0m"
            )
            return

        # T3.23: party-challenge skill_gate attempt. Surface the roll
        # against the (possibly solo-penalized) gate difficulty, plus any
        # final-clear reward.
        if mode == "skill_gate" and result.get("ok"):
            skill = result.get("skill_used", "?")
            roll = result.get("skill_roll", 0)
            dc = result.get("difficulty", 0)
            margin = result.get("margin", 0)
            verdict = "cleared" if result.get("gate_cleared") else "missed"
            await ctx.session.send_line(
                f"  \033[2m[{skill} roll: {roll} vs DC {dc}, "
                f"margin {margin:+d} — gate {verdict}]\033[0m"
            )
            credits = result.get("credits", 0)
            if credits:
                await ctx.session.send_line(
                    f"  \033[2mCredits: {credits:,}cr\033[0m")
            resources = result.get("resources", [])
            if resources:
                stacks = ", ".join(
                    f"{r['quantity']}x {r['type']} (q{r['quality']:.0f})"
                    for r in resources
                )
                await ctx.session.send_line(f"  \033[2mResources: {stacks}\033[0m")
            return

        # Detailed roll surfaced only on call success for skill-mode.
        if mode == "skill" and result.get("ok"):
            skill = result.get("skill_used", "?")
            roll = result.get("skill_roll", 0)
            margin = result.get("margin", 0)
            verdict = "success" if result.get("success") else "partial"
            await ctx.session.send_line(
                f"  \033[2m[{skill} roll: {roll} vs DC 13, "
                f"margin {margin:+d} — {verdict}]\033[0m"
            )
            # Resource grants
            resources = result.get("resources", [])
            if resources:
                stacks = ", ".join(
                    f"{r['quantity']}x {r['type']} (q{r['quality']:.0f})"
                    for r in resources
                )
                await ctx.session.send_line(f"  \033[2mResources: {stacks}\033[0m")


def register_anomaly_commands(registry) -> None:
    """Register both anomaly commands. Called from
    ``server/game_server.py`` during bootstrap."""
    registry.register(AnomaliesCommand())
    registry.register(InvestigateCommand())
