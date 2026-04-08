# -*- coding: utf-8 -*-
"""
parser/director_commands.py
---------------------------
Admin commands for the Director AI system.

All commands require AccessLevel.ADMIN.

Commands:
    @director status    — Show enabled state, API status, last turn, active events
    @director enable    — Enable Director (starts faction turn timer)
    @director disable   — Disable Director, world events fall back to timer mode
    @director trigger   — Force an immediate Faction Turn (debug/testing)
    @director budget    — Show monthly token spend, remaining budget, estimated cost
    @director influence — Show full zone influence table (all zones × all factions)
    @director log [n]   — Show last N director_log entries (default 5)
    @director reset     — Reset all zone influence to starting defaults

Registration:
    from parser.director_commands import register_director_commands
    register_director_commands(registry)
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)

# Faction display order and labels
_FACTIONS = ("imperial", "rebel", "criminal", "independent")
_FACTION_LABEL = {
    "imperial":    "Imperial  ",
    "rebel":       "Rebel     ",
    "criminal":    "Criminal  ",
    "independent": "Independ. ",
}


def _time_ago(ts_str: str) -> str:
    """Convert ISO timestamp string to human-readable relative time."""
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        secs = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            m = secs // 60
            return f"{m} minute{'s' if m != 1 else ''} ago"
        if secs < 86400:
            h = secs // 3600
            return f"{h} hour{'s' if h != 1 else ''} ago"
        d = secs // 86400
        return f"{d} day{'s' if d != 1 else ''} ago"
    except Exception:
        return ts_str


class DirectorCommand(BaseCommand):
    key = "@director"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = "Manage the Director AI system."
    usage = (
        "@director status|enable|disable|trigger|budget|influence|log [n]|reset"
    )

    async def execute(self, ctx: CommandContext) -> None:
        args = (ctx.args or "").strip().lower()
        subargs = ""

        # Split sub-command from optional argument
        parts = args.split(None, 1)
        subcmd = parts[0] if parts else "status"
        if len(parts) > 1:
            subargs = parts[1].strip()

        dispatch = {
            "status":    self._status,
            "enable":    self._enable,
            "disable":   self._disable,
            "trigger":   self._trigger,
            "budget":    self._budget,
            "influence": self._influence,
            "log":       self._log,
            "reset":     self._reset,
        }

        handler = dispatch.get(subcmd)
        if handler is None:
            await ctx.session.send_line(
                ansi.error(f"  Unknown sub-command '{subcmd}'. Usage: {self.usage}")
            )
            return

        await handler(ctx, subargs)

    # ── Sub-command handlers ───────────────────────────────────────────────────

    async def _status(self, ctx: CommandContext, _args: str) -> None:
        try:
            from engine.director import get_director
            from engine.world_events import get_world_event_manager
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return

        director = get_director()
        wem = get_world_event_manager()

        await ctx.session.send_line(ansi.header("=== Director AI Status ==="))

        # Enabled state
        enabled_str = ansi.green("ENABLED") if director.enabled else ansi.red("DISABLED")
        await ctx.session.send_line(f"  Director:    {enabled_str}")

        # API availability
        try:
            from ai.claude_provider import ClaudeProvider
            ai_mgr = getattr(ctx.session_mgr, "_ai_manager", None)
            claude = ai_mgr.providers.get("claude") if ai_mgr else None
            if claude and await claude.is_available():
                api_str = ansi.green("ONLINE")
            else:
                api_str = ansi.yellow("OFFLINE (timer fallback active)")
        except Exception:
            api_str = ansi.yellow("UNKNOWN")
        await ctx.session.send_line(f"  Claude API:  {api_str}")

        # Last faction turn
        last_turn = director.last_turn_time
        if last_turn:
            await ctx.session.send_line(
                f"  Last Turn:   {_time_ago(last_turn)}"
            )
        else:
            await ctx.session.send_line("  Last Turn:   Never")

        # Ticks until next turn
        ticks_remaining = max(0, director.turn_interval_ticks - director._tick_counter)
        mins = ticks_remaining // 60
        secs = ticks_remaining % 60
        await ctx.session.send_line(f"  Next Turn:   ~{mins}m {secs}s")

        # Active world events
        active = wem.get_active_events()
        if active:
            await ctx.session.send_line(f"  Active Events ({len(active)}):")
            for evt in active:
                evt_type = evt.get("type", "unknown")
                zones = ", ".join(evt.get("zones_affected", []))
                await ctx.session.send_line(f"    • {evt_type} [{zones}]")
        else:
            await ctx.session.send_line("  Active Events: None")

        # Alert level summary (one per zone)
        await ctx.session.send_line("  Alert Levels:")
        try:
            from engine.director import AlertLevel
            for zone_id in director._influence:
                alert = director.get_alert_level(zone_id)
                color_fn = {
                    "LOCKDOWN":   ansi.red,
                    "HIGH_ALERT": ansi.yellow,
                    "STANDARD":   ansi.white,
                    "LAX":        ansi.green,
                    "UNDERWORLD": ansi.magenta if hasattr(ansi, "magenta") else ansi.red,
                    "UNREST":     ansi.yellow,
                }.get(alert.name if hasattr(alert, "name") else str(alert), ansi.white)
                alert_label = alert.name if hasattr(alert, "name") else str(alert)
                await ctx.session.send_line(
                    f"    {zone_id:<14} {color_fn(alert_label)}"
                )
        except Exception as exc:
            await ctx.session.send_line(f"    (error reading alert levels: {exc})")

    async def _enable(self, ctx: CommandContext, _args: str) -> None:
        try:
            from engine.director import get_director
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return

        director = get_director()
        if director.enabled:
            await ctx.session.send_line("  Director is already enabled.")
            return
        director.enabled = True
        director._tick_counter = 0
        await ctx.session.send_line(ansi.success("  Director enabled. Faction Turn timer started."))
        log.info("[director] Enabled by admin %s.", ctx.session.char_name)

    async def _disable(self, ctx: CommandContext, _args: str) -> None:
        try:
            from engine.director import get_director
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return

        director = get_director()
        if not director.enabled:
            await ctx.session.send_line("  Director is already disabled.")
            return
        director.enabled = False
        await ctx.session.send_line(
            ansi.success("  Director disabled. World events fall back to timer mode.")
        )
        log.info("[director] Disabled by admin %s.", ctx.session.char_name)

    async def _trigger(self, ctx: CommandContext, _args: str) -> None:
        try:
            from engine.director import get_director
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return

        await ctx.session.send_line("  Triggering immediate Faction Turn...")
        director = get_director()
        try:
            await director.faction_turn(ctx.db, ctx.session_mgr)
            await ctx.session.send_line(ansi.success("  Faction Turn complete."))
        except Exception as exc:
            await ctx.session.send_line(ansi.error(f"  Faction Turn failed: {exc}"))
            log.exception("[director] Manual trigger failed.")

    async def _budget(self, ctx: CommandContext, _args: str) -> None:
        ai_mgr = getattr(ctx.session_mgr, "_ai_manager", None)
        claude = ai_mgr.providers.get("claude") if ai_mgr else None

        await ctx.session.send_line(ansi.header("=== Director Budget ==="))

        if not claude:
            await ctx.session.send_line(
                "  Claude API not configured. Set ANTHROPIC_API_KEY to enable."
            )
            return

        stats = claude.get_budget_stats()
        month = stats.get("month", "N/A")
        spent_d = stats.get("spent_dollars", 0.0)
        budget_d = stats.get("budget_dollars", 20.0)
        remaining_d = stats.get("remaining_cents", 0.0) / 100.0
        pct = stats.get("pct_used", 0.0)
        calls = stats.get("call_count", 0)
        over = stats.get("over_budget", False)

        await ctx.session.send_line(f"  Month:      {month}")
        await ctx.session.send_line(
            f"  Spent:      ${spent_d:.4f} / ${budget_d:.2f} ({pct:.1f}%)"
        )
        await ctx.session.send_line(f"  Remaining:  ${remaining_d:.4f}")
        await ctx.session.send_line(f"  API Calls:  {calls}")

        if over:
            await ctx.session.send_line(
                ansi.red("  CIRCUIT BREAKER: Budget at 90%+ — API calls suspended.")
            )
        else:
            bar_filled = int(pct / 5)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            await ctx.session.send_line(f"  [{bar}] {pct:.1f}%")

        # Estimated monthly projection
        try:
            from engine.director import get_director
            d = get_director()
            # Estimate based on calls this month vs days elapsed
            now = datetime.now(timezone.utc)
            day_of_month = now.day
            if day_of_month > 1 and calls > 0:
                projected = (spent_d / day_of_month) * 30
                await ctx.session.send_line(
                    f"  Projected:  ~${projected:.2f}/month at current rate"
                )
        except Exception:
            pass

    async def _influence(self, ctx: CommandContext, _args: str) -> None:
        try:
            from engine.director import get_director
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return

        director = get_director()
        influence = director._influence  # zone_id -> {faction: score}

        await ctx.session.send_line(ansi.header("=== Zone Influence Table ==="))
        await ctx.session.send_line(
            f"  {'Zone':<14} {'Imperial':>9} {'Rebel':>6} {'Criminal':>9} {'Indep.':>7}"
        )
        await ctx.session.send_line("  " + "-" * 50)

        for zone_id in sorted(influence.keys()):
            scores = influence[zone_id]
            imp = scores.get("imperial", 0)
            reb = scores.get("rebel", 0)
            cri = scores.get("criminal", 0)
            ind = scores.get("independent", 0)

            # Color the dominant faction
            imp_s = ansi.red(f"{imp:>9}") if imp >= 70 else f"{imp:>9}"
            reb_s = ansi.green(f"{reb:>6}") if reb >= 40 else f"{reb:>6}"
            cri_s = ansi.yellow(f"{cri:>9}") if cri >= 70 else f"{cri:>9}"

            await ctx.session.send_line(
                f"  {zone_id:<14} {imp_s} {reb_s} {cri_s} {ind:>7}"
            )

        # Alert level legend
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.red('Red')} = ≥70 (Lockdown/Underworld)  "
            f"{ansi.green('Green')} = ≥40 Rebel (Unrest)"
        )

    async def _log(self, ctx: CommandContext, args: str) -> None:
        try:
            from engine.director import get_director
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return

        n = 5
        if args:
            try:
                n = max(1, min(20, int(args)))
            except ValueError:
                pass

        director = get_director()
        try:
            entries = await director.get_recent_log(ctx.db, limit=n)
        except Exception as exc:
            await ctx.session.send_line(ansi.error(f"  Error reading director log: {exc}"))
            return

        await ctx.session.send_line(ansi.header(f"=== Director Log (last {n}) ==="))

        if not entries:
            await ctx.session.send_line("  No log entries found.")
            return

        for entry in entries:
            ts = _time_ago(entry.get("timestamp", ""))
            evt_type = entry.get("event_type", "unknown")
            summary = entry.get("summary", "(no summary)")
            tok_in = entry.get("token_cost_input", 0)
            tok_out = entry.get("token_cost_output", 0)

            cost_str = ""
            if tok_in or tok_out:
                cost_str = f"  [{tok_in}in/{tok_out}out tok]"

            await ctx.session.send_line(
                f"  [{ts}] {ansi.dim(evt_type)}: {summary}{cost_str}"
            )

    async def _reset(self, ctx: CommandContext, _args: str) -> None:
        try:
            from engine.director import get_director
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return

        director = get_director()
        try:
            await director.reset_influence(ctx.db)
            await ctx.session.send_line(
                ansi.success("  Zone influence reset to starting defaults.")
            )
            log.info("[director] Influence reset by admin %s.", ctx.session.char_name)
        except Exception as exc:
            await ctx.session.send_line(ansi.error(f"  Reset failed: {exc}"))
            log.exception("[director] Reset failed.")


# ── Registration ───────────────────────────────────────────────────────────────

def register_director_commands(registry) -> None:
    """Register all Director admin commands."""
    registry.register(DirectorCommand())
