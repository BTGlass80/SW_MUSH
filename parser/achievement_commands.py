# -*- coding: utf-8 -*-
"""
parser/achievement_commands.py — Achievement display commands for SW_MUSH.

Commands:
  +achievements           List all achievements with progress
  +achievements <cat>     Filter by category (combat, space, economy, etc.)
"""

import logging

from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)


# ── Formatting Helpers ────────────────────────────────────────────────────────

def _progress_bar(progress: int, target: int, width: int = 12) -> str:
    """Render a small ASCII progress bar."""
    if target <= 0:
        target = 1
    ratio = min(progress / target, 1.0)
    filled = int(ratio * width)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}]"


def _status_str(ach: dict) -> str:
    """Return a colored status string for an achievement."""
    if ach["completed"]:
        return f"{ansi.BRIGHT_GREEN}★ Complete{ansi.RESET}"
    if ach["locked"]:
        return f"{ansi.DIM}○ Locked{ansi.RESET}"
    if ach["progress"] > 0:
        bar = _progress_bar(ach["progress"], ach["target"])
        return (
            f"{ansi.BRIGHT_CYAN}{bar}{ansi.RESET} "
            f"{ach['progress']}/{ach['target']}"
        )
    return f"{ansi.DIM}○ Not started{ansi.RESET}"


# ── Commands ─────────────────────────────────────────────────────────────────

class AchievementsCommand(BaseCommand):
    """
    Display your achievement progress.

    Usage:
      +achievements           — show all achievements
      +achievements combat    — show only combat achievements
      +achievements space     — show only space achievements
    """
    key = "+achievements"
    aliases = ["+achievement", "+ach", "achievements"]
    help_text = (
        "View your achievement progress across all game systems.\n"
        "\n"
        "USAGE:\n"
        "  +achievements              — show all achievements\n"
        "  +achievements <category>   — filter by category\n"
        "\n"
        "CATEGORIES: combat, space, economy, crafting, social, "
        "exploration, smuggling, force\n"
        "\n"
        "Achievements award Character Points (CP) when completed.\n"
        "Some achievements require completing a prerequisite first."
    )
    usage = "+achievements [category]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be logged in.")
            return

        db = ctx.session.game_server.db if hasattr(ctx.session, "game_server") else None
        if not db:
            await ctx.session.send_line("  Achievement system unavailable.")
            return

        from engine.achievements import (
            get_achievements_status, CATEGORY_ORDER, CATEGORY_LABELS,
        )

        char_id = char.get("id")
        status = await get_achievements_status(db, char_id)
        all_achs = status["achievements"]
        completed = status["completed_count"]
        total = status["total_count"]

        # Filter by category if specified
        filter_cat = (ctx.args or "").strip().lower()
        valid_cats = set(CATEGORY_ORDER + ["smuggling"])

        if filter_cat and filter_cat not in valid_cats:
            await ctx.session.send_line(
                f"  Unknown category '{filter_cat}'. "
                f"Valid: {', '.join(CATEGORY_ORDER)}"
            )
            return

        # Header
        char_name = char.get("name", "Unknown")
        lines = []
        lines.append(
            f"{ansi.BRIGHT_YELLOW}"
            f"{'═' * 60}{ansi.RESET}"
        )
        lines.append(
            f"  {ansi.BRIGHT_WHITE}ACHIEVEMENTS{ansi.RESET}"
            f" — {char_name}"
            f"    {ansi.BRIGHT_GREEN}{completed}{ansi.RESET}"
            f"/{total} Complete"
        )
        lines.append(
            f"{ansi.BRIGHT_YELLOW}"
            f"{'═' * 60}{ansi.RESET}"
        )

        # Group by category
        cats_to_show = [filter_cat] if filter_cat else CATEGORY_ORDER
        # Include smuggling in exploration if not filtering
        if not filter_cat:
            cats_to_show = CATEGORY_ORDER  # smuggling is in CATEGORY_ORDER

        for cat in cats_to_show:
            cat_achs = [a for a in all_achs if a["category"] == cat]
            if not cat_achs:
                continue

            label = CATEGORY_LABELS.get(cat, cat.upper())
            cat_completed = sum(1 for a in cat_achs if a["completed"])
            lines.append(
                f"\n  {ansi.BRIGHT_CYAN}{label.upper()}{ansi.RESET}"
                f"  ({cat_completed}/{len(cat_achs)})"
            )

            for ach in cat_achs:
                icon = ach["icon"]
                name = ach["name"]
                status_text = _status_str(ach)
                cp_text = (
                    f" {ansi.DIM}({ach['cp_reward']} CP){ansi.RESET}"
                    if ach["cp_reward"] and not ach["completed"]
                    else ""
                )

                # Name formatting
                if ach["completed"]:
                    name_fmt = f"{ansi.BRIGHT_WHITE}{name}{ansi.RESET}"
                elif ach["locked"]:
                    name_fmt = f"{ansi.DIM}{name}{ansi.RESET}"
                else:
                    name_fmt = name

                lines.append(
                    f"    {icon} {name_fmt} — {status_text}{cp_text}"
                )

                # Show description for incomplete, unlocked achievements
                if not ach["completed"] and not ach["locked"]:
                    lines.append(
                        f"       {ansi.DIM}{ach['description']}{ansi.RESET}"
                    )

        lines.append(
            f"\n{ansi.BRIGHT_YELLOW}"
            f"{'═' * 60}{ansi.RESET}"
        )

        # Send HUD event for web client
        if hasattr(ctx.session, "send_json"):
            try:
                await ctx.session.send_json({
                    "type": "achievements_status",
                    "completed": completed,
                    "total": total,
                    "achievements": [
                        {
                            "key": a["key"],
                            "name": a["name"],
                            "description": a["description"],
                            "category": a["category"],
                            "icon": a["icon"],
                            "cp_reward": a["cp_reward"],
                            "progress": a["progress"],
                            "target": a["target"],
                            "completed": a["completed"],
                            "locked": a["locked"],
                        }
                        for a in all_achs
                    ],
                })
            except Exception as _e:
                log.debug("silent except in parser/achievement_commands.py:198: %s", _e, exc_info=True)

        await ctx.session.send_line("\n".join(lines))


# ── Registration ─────────────────────────────────────────────────────────────

def register_achievement_commands(registry) -> None:
    registry.register(AchievementsCommand())
    log.info("[achievements] achievement commands registered")
