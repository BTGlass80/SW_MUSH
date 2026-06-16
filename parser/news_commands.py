# -*- coding: utf-8 -*-
"""
parser/news_commands.py
-----------------------
The `news` command — world events board for players.

Reads the 10 most recent entries from director_log and formats them
as a "Galactic News Network" style bulletin board.

Time display:
    just now | X minutes ago | X hours ago | yesterday | X days ago

Registration:
    from parser.news_commands import register_news_commands
    register_news_commands(registry)
"""
import logging
from datetime import datetime, timezone

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)

_HEADER = "=== Mos Eisley Galactic News Network ==="
_INDENT = "  "


def _time_ago(ts_str: str) -> str:
    """Convert ISO timestamp string to player-friendly relative time label."""
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        secs = int(delta.total_seconds())

        if secs < 90:
            return "just now"
        if secs < 3600:
            m = secs // 60
            return f"{m} minute{'s' if m != 1 else ''} ago"
        if secs < 7200:
            return "1 hour ago"
        if secs < 86400:
            h = secs // 3600
            return f"{h} hours ago"
        if secs < 172800:
            return "yesterday"
        d = secs // 86400
        return f"{d} days ago"
    except Exception:
        log.warning("format_ts failed", exc_info=True)
        return ts_str


def _wrap_summary(summary: str, width: int = 60) -> list[str]:
    """
    Wrap a summary string to `width` characters.
    Returns a list of lines (first line and continuation lines).
    """
    if not summary:
        return ["(no summary)"]

    words = summary.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current:
            test = current + " " + word
        else:
            test = word
        if len(test) <= width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or ["(no summary)"]


class NewsCommand(BaseCommand):
    key = "+news"
    aliases = ["news", "worldnews", "galacticnews"]
    access_level = AccessLevel.ANYONE
    help_text = "Display the Galactic News Network world events board."
    usage = "news"

    async def execute(self, ctx: CommandContext) -> None:
        try:
            from engine.director import get_director
        except ImportError:
            # Director not installed yet — show empty board gracefully
            await ctx.session.send_line(ansi.header(_HEADER))
            await ctx.session.send_line(
                _INDENT + ansi.dim("No news available at this time.")
            )
            return

        try:
            entries = await get_director().get_recent_log(ctx.db, limit=10)
        except Exception as exc:
            log.warning("[news] Failed to read director_log: %s", exc)
            await ctx.session.send_line(ansi.header(_HEADER))
            await ctx.session.send_line(
                _INDENT + ansi.dim("The holonet is experiencing technical difficulties.")
            )
            return

        await ctx.session.send_line(ansi.header(_HEADER))
        await ctx.session.send_line("")

        if not entries:
            await ctx.session.send_line(
                _INDENT + ansi.dim("No recent news. The galaxy is quiet... for now.")
            )
            await ctx.session.send_line("")
            return

        for entry in entries:
            ts_str = entry.get("timestamp", "")
            summary = entry.get("summary", "").strip()

            time_label = _time_ago(ts_str)
            wrapped = _wrap_summary(summary, width=55)

            # First line: timestamp label + first line of summary
            first_line = wrapped[0]
            time_col = ansi.dim(f"[{time_label}]")
            await ctx.session.send_line(
                f"{_INDENT}{time_col:<30} {first_line}"
            )

            # Continuation lines (indented to align with first line)
            for cont in wrapped[1:]:
                await ctx.session.send_line(
                    f"{_INDENT}{'':30} {cont}"
                )

        await ctx.session.send_line("")
        await ctx.session.send_line(
            _INDENT + ansi.dim(
                "Mos Eisley GNN — 'All the news credits can buy.'"
            )
        )
        await ctx.session.send_line("")


class HolonetCommand(BaseCommand):
    """Open the HoloNet news browser (web client only).

    Sends a ``holonet_state`` JSON event that the SPA handles by opening the
    M3Holonet browser modal.  Live world-event data from ``world_events`` fills
    the right-rail; the fixture news stories ship with the client module.
    Telnet gets a brief text notice.
    """
    key = "+holonet"
    aliases = ["holonet"]
    access_level = AccessLevel.ANYONE
    help_text = "Open the HoloNet galactic news browser (web client)."
    usage = "+holonet"

    async def execute(self, ctx: CommandContext) -> None:
        from server.session import Protocol  # avoid circular at module level
        if ctx.session.protocol != Protocol.WEBSOCKET:
            await ctx.session.send_line(
                ansi.header("=== HoloNet requires the web client ===")
            )
            return

        try:
            from engine.world_events import get_world_event_manager
            live_events = get_world_event_manager().get_status()
        except Exception:
            live_events = []

        await ctx.session.send_json("holonet_state", {"world_events": live_events})


# ── Registration ───────────────────────────────────────────────────────────────

def register_news_commands(registry) -> None:
    """Register the news and holonet commands."""
    registry.register(NewsCommand())
    registry.register(HolonetCommand())
