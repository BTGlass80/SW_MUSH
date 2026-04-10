# -*- coding: utf-8 -*-
"""
parser/director_commands.py
---------------------------
Admin commands for the Director AI system.
All commands require AccessLevel.ADMIN.
"""
import logging
import time
from datetime import datetime, timezone

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


def _time_ago(ts_val) -> str:
    """Convert a float timestamp or ISO string to relative time."""
    try:
        if isinstance(ts_val, (int, float)):
            if ts_val == 0:
                return "never"
            delta = time.time() - float(ts_val)
        else:
            ts = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = (datetime.now(timezone.utc) - ts).total_seconds()
        secs = int(delta)
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
        return str(ts_val)


class DirectorCommand(BaseCommand):
    key = "@director"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = "Manage the Director AI system. Sub-commands: status enable disable trigger budget influence log reset narrative"
    usage = "@director status|enable|disable|trigger|budget|influence|log [n]|reset|narrative [enable|disable|status]"

    async def execute(self, ctx: CommandContext) -> None:
        args = (ctx.args or "").strip().lower()
        parts = args.split(None, 1)
        subcmd = parts[0] if parts else "status"
        subargs = parts[1].strip() if len(parts) > 1 else ""

        dispatch = {
            "status":    self._status,
            "enable":    self._enable,
            "disable":   self._disable,
            "trigger":   self._trigger,
            "budget":    self._budget,
            "influence": self._influence_cmd,
            "log":       self._log,
            "reset":     self._reset,
            "narrative": self._narrative,
        }
        handler = dispatch.get(subcmd)
        if handler is None:
            await ctx.session.send_line(
                ansi.error(f"  Unknown sub-command '{subcmd}'. Usage: {self.usage}")
            )
            return
        await handler(ctx, subargs)

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

        enabled_str = ansi.green("ENABLED") if director.enabled else ansi.red("DISABLED")
        await ctx.session.send_line(f"  Director:    {enabled_str}")

        # API availability
        try:
            ai_mgr = getattr(ctx.session_mgr, "_ai_manager", None)
            claude = ai_mgr.providers.get("claude") if ai_mgr else None
            if claude and await claude.is_available():
                api_str = ansi.green("ONLINE")
            else:
                api_str = ansi.yellow("OFFLINE (timer fallback active)")
        except Exception:
            api_str = ansi.yellow("UNKNOWN")
        await ctx.session.send_line(f"  Claude API:  {api_str}")

        # Narrative AI status
        try:
            from engine.narrative import is_narrative_ai_enabled
            narr_str = ansi.green("ENABLED") if is_narrative_ai_enabled() else ansi.yellow("DISABLED")
            await ctx.session.send_line(f"  Narrative AI:{narr_str}  (logging: always on)")
        except Exception:
            pass

        # Last / next turn
        last = director._last_turn_time
        await ctx.session.send_line(f"  Last Turn:   {_time_ago(last)}")
        if director.enabled and last > 0:
            elapsed = time.time() - last
            remaining = max(0, director._turn_interval - elapsed)
            mins, secs = int(remaining) // 60, int(remaining) % 60
            await ctx.session.send_line(f"  Next Turn:   ~{mins}m {secs}s")
        else:
            await ctx.session.send_line("  Next Turn:   (director disabled)")

        # Active events
        active = wem.get_status()
        if active:
            await ctx.session.send_line(f"  Active Events ({len(active)}):")
            for evt in active:
                zones = ", ".join(evt.get("zones", []))
                await ctx.session.send_line(f"    * {evt.get('type', 'unknown')} [{zones}]")
        else:
            await ctx.session.send_line("  Active Events: None")

        # Alert levels per zone
        await ctx.session.send_line("  Alert Levels:")
        for zone_key, zs in sorted(director._zones.items()):
            alert_name = zs.alert_level.value.upper().replace("_", " ")
            color_fn = {
                "LOCKDOWN":   ansi.red,
                "HIGH ALERT": ansi.yellow,
                "STANDARD":   ansi.white,
                "LAX":        ansi.green,
                "UNDERWORLD": ansi.red,
                "UNREST":     ansi.yellow,
            }.get(alert_name, ansi.white)
            await ctx.session.send_line(f"    {zone_key:<14} {color_fn(alert_name)}")

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
        director.enable()
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
        director.disable()
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
        try:
            await get_director().faction_turn(ctx.db, ctx.session_mgr)
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
        await ctx.session.send_line(f"  Month:      {stats.get('month', 'N/A')}")
        await ctx.session.send_line(
            f"  Spent:      ${stats.get('spent_dollars', 0):.4f} / "
            f"${stats.get('budget_dollars', 20):.2f} "
            f"({stats.get('pct_used', 0):.1f}%)"
        )
        await ctx.session.send_line(
            f"  Remaining:  ${stats.get('remaining_cents', 0) / 100:.4f}"
        )
        await ctx.session.send_line(f"  API Calls:  {stats.get('call_count', 0)}")
        if stats.get("over_budget"):
            await ctx.session.send_line(
                ansi.red("  CIRCUIT BREAKER: Budget at 90%+ — API suspended.")
            )
        else:
            pct = stats.get("pct_used", 0)
            bar = "X" * int(pct / 5) + "." * (20 - int(pct / 5))
            await ctx.session.send_line(f"  [{bar}] {pct:.1f}%")

    async def _influence_cmd(self, ctx: CommandContext, _args: str) -> None:
        try:
            from engine.director import get_director
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return

        director = get_director()
        await ctx.session.send_line(ansi.header("=== Zone Influence Table ==="))
        await ctx.session.send_line(
            f"  {'Zone':<14} {'Imperial':>9} {'Rebel':>6} {'Criminal':>9} {'Indep.':>7}"
        )
        await ctx.session.send_line("  " + "-" * 50)
        for zone_key, zs in sorted(director._zones.items()):
            imp = zs.imperial
            reb = zs.rebel
            cri = zs.criminal
            ind = zs.independent
            imp_s = ansi.red(f"{imp:>9}") if imp >= 70 else f"{imp:>9}"
            reb_s = ansi.green(f"{reb:>6}") if reb >= 40 else f"{reb:>6}"
            cri_s = ansi.yellow(f"{cri:>9}") if cri >= 70 else f"{cri:>9}"
            await ctx.session.send_line(
                f"  {zone_key:<14} {imp_s} {reb_s} {cri_s} {ind:>7}"
            )
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.red('Red')} >= 70 (Lockdown/Underworld)  "
            f"{ansi.green('Green')} >= 40 Rebel (Unrest)"
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
        try:
            entries = await get_director().get_recent_log(ctx.db, limit=n)
        except Exception as exc:
            await ctx.session.send_line(ansi.error(f"  Error reading log: {exc}"))
            return
        await ctx.session.send_line(ansi.header(f"=== Director Log (last {n}) ==="))
        if not entries:
            await ctx.session.send_line("  No log entries found.")
            return
        for entry in entries:
            ts   = _time_ago(entry.get("timestamp", 0))
            typ  = entry.get("event_type", "unknown")
            summ = entry.get("summary", "(no summary)")
            tok_in  = entry.get("token_cost_input", 0)
            tok_out = entry.get("token_cost_output", 0)
            cost = f"  [{tok_in}in/{tok_out}out]" if (tok_in or tok_out) else ""
            await ctx.session.send_line(f"  [{ts}] {ansi.dim(typ)}: {summ}{cost}")

    async def _reset(self, ctx: CommandContext, _args: str) -> None:
        try:
            from engine.director import get_director
        except ImportError as exc:
            await ctx.session.send_line(ansi.error(f"  Director not loaded: {exc}"))
            return
        try:
            await get_director().reset_influence(ctx.db)
            await ctx.session.send_line(
                ansi.success("  Zone influence reset to starting defaults.")
            )
            log.info("[director] Influence reset by admin %s.", ctx.session.char_name)
        except Exception as exc:
            await ctx.session.send_line(ansi.error(f"  Reset failed: {exc}"))

    async def _narrative(self, ctx: CommandContext, args: str) -> None:
        """
        @director narrative [enable|disable|status]

        Toggles the narrative AI feature set:
          - short_record injection into NPC brain prompts
          - nightly Haiku summarization pipeline (Phase 3)

        Action *logging* is always on regardless of this flag — it's just
        DB writes with zero API cost and should always be collecting data.

        Default: DISABLED during development.
        """
        from engine.narrative import set_narrative_ai, is_narrative_ai_enabled

        sub = args.strip().lower()

        if sub in ("enable", "on"):
            set_narrative_ai(True)
            await ctx.session.send_line(
                ansi.success(
                    "  Narrative AI: ENABLED\n"
                    "  NPC brain prompts will now include player short_record.\n"
                    "  Action logging was already running."
                )
            )
            log.info("[director] Narrative AI enabled by %s", ctx.session.char_name)

        elif sub in ("disable", "off"):
            set_narrative_ai(False)
            await ctx.session.send_line(
                ansi.success(
                    "  Narrative AI: DISABLED\n"
                    "  NPC prompts revert to per-NPC memory only.\n"
                    "  Action logging continues (zero cost)."
                )
            )
            log.info("[director] Narrative AI disabled by %s", ctx.session.char_name)

        else:
            # status (default)
            enabled = is_narrative_ai_enabled()
            state = ansi.green("ENABLED") if enabled else ansi.yellow("DISABLED (default)")
            await ctx.session.send_line(
                f"\n  Narrative AI:     {state}\n"
                f"  Action logging:   {ansi.green('ALWAYS ON')} (zero API cost)\n"
                f"  NPC short_record: {'injected into prompts' if enabled else 'suppressed'}\n"
                f"  Summarization:    {'active (Phase 3 pending)' if enabled else 'suppressed'}\n\n"
                f"  Usage: @director narrative enable|disable"
            )


def register_director_commands(registry) -> None:
    registry.register(DirectorCommand())
