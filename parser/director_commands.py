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
        log.warning("format_ts failed", exc_info=True)
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
            log.warning("_status: unhandled exception", exc_info=True)
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
            except ValueError as _e:
                log.debug("silent except in parser/director_commands.py:265: %s", _e, exc_info=True)
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


class EconomyCommand(BaseCommand):
    """@economy — Admin economy dashboard: shop stats, credit flow, zone prices."""
    key = "@economy"
    aliases = ["@econ"]
    access_level = AccessLevel.ADMIN
    help_text = (
        "Admin economy dashboard.\n"
        "  @economy shops     — active vendor droids, total escrow, top earners\n"
        "  @economy credits   — credit distribution across active characters\n"
        "  @economy zones     — Director zone influence + alert levels\n"
        "  @economy velocity  — credit faucet/sink flow (1h, 24h, 7d)\n"
        "  @economy alerts    — whale transactions, farming alerts, inflation metrics\n"
        "  @economy           — all of the above"
    )
    usage = "@economy [shops|credits|zones|velocity|alerts]"

    async def execute(self, ctx: CommandContext):
        parts = (ctx.args or "").split()
        sub   = parts[0].lower() if parts else "all"

        lines = ["\033[1;36m══════════════════════════════════════════\033[0m",
                 "  \033[1;37m@ECONOMY DASHBOARD\033[0m",
                 "\033[1;36m──────────────────────────────────────────\033[0m"]

        show_shops    = sub in ("all", "shops")
        show_credits  = sub in ("all", "credits")
        show_zones    = sub in ("all", "zones")
        show_velocity = sub in ("all", "velocity")
        show_alerts   = sub in ("all", "alerts")

        # ── Shop stats ────────────────────────────────────────────────────
        if show_shops:
            try:
                rows = await ctx.db.fetchall(
                    "SELECT * FROM objects WHERE type = 'vendor_droid'"
                )
                from engine.vendor_droids import _load_data
                total = len(rows)
                placed = sum(1 for r in rows if r["room_id"])
                total_escrow = 0
                total_items  = 0
                top = []
                for r in rows:
                    d = _load_data(dict(r))
                    esc = d.get("escrow_credits", 0)
                    inv = len([s for s in d.get("inventory", [])
                               if s.get("quantity", 0) > 0])
                    total_escrow += esc
                    total_items  += inv
                    top.append((esc, d.get("shop_name") or r["name"]))
                top.sort(reverse=True)
                lines += [
                    "  \033[1;33mSHOPS\033[0m",
                    f"  Active droids : {placed}/{total} placed",
                    f"  Total items   : {total_items}",
                    f"  Total escrow  : {total_escrow:,} cr (uncollected)",
                ]
                if top[:5]:
                    lines.append("  Top earners:")
                    for esc, name in top[:5]:
                        lines.append(f"    {name:<28}  {esc:>8,} cr pending")

                # Recent sales volume (last 24h)
                import time as _t
                cutoff = _t.time() - 86400
                try:
                    sale_rows = await ctx.db.fetchall(
                        "SELECT SUM(total_price) as vol, COUNT(*) as cnt "
                        "FROM shop_transactions WHERE created_at > ?", (cutoff,)
                    )
                    if sale_rows and sale_rows[0]["vol"]:
                        lines.append(
                            f"  Sales (24h)   : "
                            f"{sale_rows[0]['cnt']} txns / "
                            f"{int(sale_rows[0]['vol']):,} cr volume"
                        )
                except Exception:
                    log.warning("execute: unhandled exception", exc_info=True)
                    pass
            except Exception as e:
                lines.append(f"  Shop stats error: {e}")

        # ── Credit distribution ───────────────────────────────────────────
        if show_credits:
            try:
                lines.append("  \033[1;33mCREDITS\033[0m")
                rows = await ctx.db.fetchall(
                    "SELECT credits FROM characters WHERE is_active = 1 ORDER BY credits DESC"
                )
                if rows:
                    vals = [r["credits"] for r in rows]
                    total = sum(vals)
                    avg   = total // len(vals)
                    lines += [
                        f"  Active chars  : {len(vals)}",
                        f"  Total credits : {total:,} cr",
                        f"  Average       : {avg:,} cr",
                        f"  Richest       : {vals[0]:,} cr",
                        f"  Poorest       : {vals[-1]:,} cr",
                    ]
            except Exception as e:
                lines.append(f"  Credit stats error: {e}")

        # ── Zone influence ────────────────────────────────────────────────
        if show_zones:
            try:
                from engine.director import get_director
                director = get_director()
                states   = director.get_all_zone_states()
                lines.append("  \033[1;33mZONE INFLUENCE\033[0m")
                lines.append(
                    f"  {'Zone':<14} {'Imp':>4} {'Reb':>4} {'Cri':>4} {'Ind':>4}  Alert"
                )
                for zk, zs in sorted(states.items()):
                    alert = zs.get("alert_level", "standard")
                    alert_color = {
                        "lockdown":   "\033[1;31m",
                        "underworld": "\033[1;35m",
                        "unrest":     "\033[1;33m",
                        "lax":        "\033[2m",
                    }.get(alert, "")
                    lines.append(
                        f"  {zk:<14} "
                        f"{zs['imperial']:>4} "
                        f"{zs['rebel']:>4} "
                        f"{zs['criminal']:>4} "
                        f"{zs['independent']:>4}  "
                        f"{alert_color}{alert}\033[0m"
                    )
            except Exception as e:
                lines.append(f"  Zone stats error: {e}")

        # ── Credit velocity (economy hardening v23) ─────────────────────
        if show_velocity:
            try:
                lines.append("  \033[1;33mCREDIT VELOCITY\033[0m")
                for label, secs in [("1 hour", 3600), ("24 hours", 86400), ("7 days", 604800)]:
                    v = await ctx.db.get_credit_velocity(secs)
                    lines.append(f"  \033[1m{label}:\033[0m  "
                                 f"Faucets: +{v['faucet_total']:,} cr  "
                                 f"Sinks: {v['sink_total']:,} cr  "
                                 f"Net: {v['net']:,} cr  "
                                 f"({v['txn_count']} txns)")
                # Show top faucets/sinks for 24h
                v24 = await ctx.db.get_credit_velocity(86400)
                if v24["top_faucets"]:
                    lines.append("  Top faucets (24h):")
                    for src, total in v24["top_faucets"]:
                        lines.append(f"    {src:<20}  +{total:>10,} cr")
                if v24["top_sinks"]:
                    lines.append("  Top sinks (24h):")
                    for src, total in v24["top_sinks"]:
                        lines.append(f"    {src:<20}  {total:>10,} cr")
                if v24["top_earners"]:
                    lines.append("  Top earners (24h):")
                    for cid, total in v24["top_earners"][:5]:
                        try:
                            ch = await ctx.db.get_character(cid)
                            name = ch["name"] if ch else f"char#{cid}"
                        except Exception:
                            name = f"char#{cid}"
                        lines.append(f"    {name:<20}  {total:>+10,} cr")
            except Exception as e:
                lines.append(f"  Velocity stats error: {e}")

        # ── Alerts (S51 economy hardening) ──────────────────────────────
        # Three separate signals that surface concerning credit movement:
        #   - Whale transactions: single moves >= 50,000 cr in last 24h
        #   - Farming alerts:     chars sustaining >5,000 cr/hr earnings
        #   - Inflation metrics:  net 24h flow vs total circulation
        # All three failsafe to "nothing to report" on DB error so this
        # never tanks the dashboard.
        if show_alerts:
            try:
                lines.append("  \033[1;33mECONOMY ALERTS\033[0m")
                # Whale transactions
                whales = await ctx.db.get_whale_transactions(threshold=50000)
                if whales:
                    lines.append(f"  Whale txns (>=50k, 24h): {len(whales)}")
                    for w in whales[:5]:
                        try:
                            ch = await ctx.db.get_character(w["char_id"])
                            name = ch["name"] if ch else f"char#{w['char_id']}"
                        except Exception:
                            name = f"char#{w['char_id']}"
                        sign = "+" if w["delta"] > 0 else ""
                        lines.append(
                            f"    {name:<20}  {sign}{w['delta']:>10,} cr  "
                            f"({w['source']})"
                        )
                else:
                    lines.append("  Whale txns (>=50k, 24h): none")

                # Farming alerts
                farmers = await ctx.db.get_farming_alerts(
                    hourly_threshold=5000, sustained_hours=2,
                )
                if farmers:
                    lines.append(
                        f"  Sustained farming (>=5k/hr, 2+ hrs): {len(farmers)}"
                    )
                    for f in farmers[:5]:
                        try:
                            ch = await ctx.db.get_character(f["char_id"])
                            name = ch["name"] if ch else f"char#{f['char_id']}"
                        except Exception:
                            name = f"char#{f['char_id']}"
                        lines.append(
                            f"    {name:<20}  "
                            f"{f['hours_over_threshold']} hrs  "
                            f"peak {f['peak_hour_total']:,} cr  "
                            f"total {f['total_in_window']:,} cr"
                        )
                else:
                    lines.append("  Sustained farming: none")

                # Inflation metrics
                infl = await ctx.db.get_inflation_metrics()
                pct = infl["flow_pct"] * 100.0
                # Color the headline number by direction + magnitude
                if abs(pct) < 5:
                    pct_color = "\033[2m"
                elif pct > 10 or pct < -10:
                    pct_color = "\033[1;31m"
                else:
                    pct_color = "\033[1;33m"
                sign = "+" if infl["net_flow"] >= 0 else ""
                lines += [
                    "  \033[1mInflation (24h):\033[0m",
                    f"    Net flow      : {sign}{infl['net_flow']:,} cr",
                    f"    Circulation   : {infl['circulation']:,} cr",
                    f"    Flow / circ   : {pct_color}{pct:+.1f}%\033[0m",
                ]
            except Exception as e:
                lines.append(f"  Alerts error: {e}")

        lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
        await ctx.session.send_line("\n".join(lines))


class LoreCommand(BaseCommand):
    """@lore — Admin world lore management."""
    key = "@lore"
    aliases = ["@worldlore"]
    access_level = AccessLevel.ADMIN
    help_text = (
        "@lore — Manage world lore entries.\n"
        "\n"
        "  @lore                     — list all active entries\n"
        "  @lore/search <query>      — search by title or keyword\n"
        "  @lore/add                 — add a new entry (interactive)\n"
        "  @lore/disable <id>        — deactivate an entry\n"
        "  @lore/enable <id>         — reactivate an entry\n"
    )
    usage = "@lore [/search|/add|/disable|/enable] [args]"

    async def execute(self, ctx: CommandContext):
        from engine.world_lore import (
            get_all_lore, search_lore, add_lore, edit_lore, disable_lore,
        )

        args = (ctx.args or "").strip()
        B, DIM, CYAN, RST = "\033[1m", "\033[2m", "\033[1;36m", "\033[0m"
        w = 60

        # @lore/add title=X keywords=Y category=Z content=C
        if args.lower().startswith("add ") or args.lower().startswith("add="):
            rest = args[4:].strip()
            # Parse key=value pairs
            params = {}
            for part in rest.split("|"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k.strip().lower()] = v.strip()
            if not params.get("title") or not params.get("keywords") or not params.get("content"):
                await ctx.session.send_line(
                    "  Usage: @lore/add title=X | keywords=a,b,c | content=Text | category=faction | priority=7\n"
                    "  Separate fields with | character. Title, keywords, and content are required."
                )
                return
            result = await add_lore(
                ctx.db,
                title=params["title"],
                keywords=params["keywords"],
                content=params["content"],
                category=params.get("category", "general"),
                zone_scope=params.get("zone_scope", ""),
                priority=int(params.get("priority", "5")),
            )
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        # @lore/search <query>
        if args.lower().startswith("search "):
            query = args[7:].strip()
            results = await search_lore(ctx.db, query, include_inactive=True)
            if not results:
                await ctx.session.send_line(f"  No lore entries matching '{query}'.")
                return
            await ctx.session.send_line(f"\n  {CYAN}{'═' * w}{RST}")
            await ctx.session.send_line(f"  {B}World Lore — Search: {query}{RST}")
            await ctx.session.send_line(f"  {CYAN}{'─' * w}{RST}")
            for e in results:
                status = "" if e.get("active", 1) else f" {DIM}[DISABLED]{RST}"
                await ctx.session.send_line(
                    f"  [{e['id']:>3}] {B}{e['title']}{RST}{status}  "
                    f"{DIM}({e['category']}, p{e['priority']}){RST}"
                )
                await ctx.session.send_line(f"       {DIM}kw: {e['keywords']}{RST}")
            await ctx.session.send_line(f"  {CYAN}{'═' * w}{RST}\n")
            return

        # @lore/disable <id>
        if args.lower().startswith("disable "):
            try:
                lore_id = int(args[8:].strip())
            except ValueError:
                await ctx.session.send_line("  Usage: @lore/disable <id>")
                return
            result = await disable_lore(ctx.db, lore_id)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        # @lore/enable <id>
        if args.lower().startswith("enable "):
            try:
                lore_id = int(args[7:].strip())
            except ValueError:
                await ctx.session.send_line("  Usage: @lore/enable <id>")
                return
            result = await edit_lore(ctx.db, lore_id, active=1)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        # Default: list all
        entries = await get_all_lore(ctx.db)
        await ctx.session.send_line(f"\n  {CYAN}{'═' * w}{RST}")
        await ctx.session.send_line(f"  {B}World Lore — {len(entries)} active entries{RST}")
        await ctx.session.send_line(f"  {CYAN}{'─' * w}{RST}")
        for e in entries:
            scope = f" [{e['zone_scope']}]" if e.get("zone_scope") else ""
            await ctx.session.send_line(
                f"  [{e['id']:>3}] {B}{e['title']}{RST}  "
                f"{DIM}({e['category']}, p{e['priority']}{scope}){RST}"
            )
        await ctx.session.send_line(f"  {CYAN}{'─' * w}{RST}")
        await ctx.session.send_line(f"  {DIM}@lore/search <q> · @lore/add · @lore/disable <id>{RST}")
        await ctx.session.send_line(f"  {CYAN}{'═' * w}{RST}\n")


class HazardCommand(BaseCommand):
    """@hazard — Set or clear environmental hazards on the current room."""
    key = "@hazard"
    access_level = AccessLevel.ADMIN
    help_text = (
        "@hazard — Manage room environmental hazards.\n"
        "\n"
        "  @hazard <type> [severity]  — set hazard on current room (severity 1-5)\n"
        "  @hazard clear              — remove hazard from current room\n"
        "  @hazard list               — show available hazard types\n"
        "\n"
        "Types: extreme_heat, toxic_atmosphere, urban_danger, radiation"
    )
    usage = "@hazard <type> [severity]  |  @hazard clear  |  @hazard list"

    async def execute(self, ctx: CommandContext):
        from engine.hazards import (
            set_room_hazard, clear_room_hazard, HAZARD_TYPES,
        )
        char = ctx.session.character
        if not char:
            return
        room_id = char.get("room_id")
        args = (ctx.args or "").strip()

        if not args or args.lower() == "list":
            lines = ["  \033[1;37mAvailable Hazard Types:\033[0m"]
            for hk, hv in HAZARD_TYPES.items():
                envs = ", ".join(hv["environments"]) if hv["environments"] else "manual only"
                lines.append(
                    f"    \033[1m{hk}\033[0m — {hv['display_name']} "
                    f"(skill: {hv['skill']}, base diff: {hv['base_difficulty']}, "
                    f"envs: {envs})"
                )
            lines.append("  \033[2mUsage: @hazard <type> [severity 1-5]\033[0m")
            for line in lines:
                await ctx.session.send_line(line)
            return

        if args.lower() == "clear":
            result = await clear_room_hazard(ctx.db, room_id)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        parts = args.split()
        hazard_type = parts[0].lower()
        severity = 1
        if len(parts) > 1:
            try:
                severity = int(parts[1])
            except ValueError:
                await ctx.session.send_line("  Severity must be a number 1-5.")
                return

        result = await set_room_hazard(ctx.db, room_id, hazard_type, severity)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )


class RoomStateCommand(BaseCommand):
    """@roomstate — Set or clear dynamic room state descriptions."""
    key = "@roomstate"
    access_level = AccessLevel.ADMIN
    help_text = (
        "@roomstate — Manage dynamic state overlays on the current room.\n"
        "\n"
        "  @roomstate <state>           — apply a predefined state\n"
        "  @roomstate <state> = <text>  — apply with custom description\n"
        "  @roomstate clear <state>     — remove a specific state\n"
        "  @roomstate clear             — remove all states\n"
        "  @roomstate list              — show available predefined states\n"
        "\n"
        "States appear as italic atmospheric text after the room description."
    )
    usage = "@roomstate <state> [= text]  |  @roomstate clear [state]  |  @roomstate list"

    async def execute(self, ctx: CommandContext):
        from engine.room_states import (
            set_room_state, clear_room_state, clear_all_states,
            get_room_states, STATE_DESCRIPTIONS,
        )
        char = ctx.session.character
        if not char:
            return
        room_id = char.get("room_id")
        args = (ctx.args or "").strip()

        if not args or args.lower() == "list":
            lines = ["  \033[1;37mPredefined Room States:\033[0m"]
            for sk in sorted(STATE_DESCRIPTIONS.keys()):
                preview = STATE_DESCRIPTIONS[sk][:60] + "..."
                lines.append(f"    \033[1m{sk}\033[0m — \033[2m{preview}\033[0m")
            lines.append("")
            # Show current states on this room
            room = await ctx.db.get_room(room_id)
            if room:
                current = get_room_states(room)
                if current:
                    lines.append(f"  \033[1;37mCurrent states on this room:\033[0m")
                    for ck in current:
                        lines.append(f"    \033[1;33m• {ck}\033[0m")
                else:
                    lines.append(f"  \033[2mNo states set on this room.\033[0m")
            for line in lines:
                await ctx.session.send_line(line)
            return

        if args.lower() == "clear":
            result = await clear_all_states(ctx.db, room_id)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        if args.lower().startswith("clear "):
            state_key = args[6:].strip().lower().replace(" ", "_")
            result = await clear_room_state(ctx.db, room_id, state_key)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        # @roomstate <state> = <custom text>  or  @roomstate <state>
        custom_text = ""
        state_key = args
        if "=" in args:
            state_key, custom_text = args.split("=", 1)
            custom_text = custom_text.strip()
        state_key = state_key.strip().lower().replace(" ", "_")

        result = await set_room_state(
            ctx.db, room_id, state_key,
            custom_text=custom_text, set_by="admin",
        )
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )


class AIStatusCommand(BaseCommand):
    """@ai — Admin AI status dashboard: Ollama, idle queue, bark cache."""
    key = "@ai"
    aliases = ["@ollama", "@idle"]
    access_level = AccessLevel.ADMIN
    help_text = (
        "AI subsystem status dashboard.\n"
        "  @ai          — full dashboard (Ollama + idle queue + barks)\n"
        "  @ai queue    — pending idle queue tasks\n"
        "  @ai barks    — bark cache inventory\n"
        "  @ai flush    — clear bark cache (forces regeneration)"
    )
    usage = "@ai [queue|barks|flush]"

    async def execute(self, ctx: CommandContext):
        parts = (ctx.args or "").split()
        sub = parts[0].lower() if parts else "all"

        CYAN = "\033[1;36m"
        WHITE = "\033[1;37m"
        YELLOW = "\033[1;33m"
        GREEN = "\033[1;32m"
        RED = "\033[1;31m"
        DIM = "\033[2m"
        RST = "\033[0m"

        lines = [f"{CYAN}══════════════════════════════════════════{RST}",
                 f"  {WHITE}@AI STATUS DASHBOARD{RST}",
                 f"{CYAN}──────────────────────────────────────────{RST}"]

        show_providers = sub in ("all", "providers", "ollama")
        show_queue = sub in ("all", "queue")
        show_barks = sub in ("all", "barks")
        do_flush = sub == "flush"

        # ── Flush bark cache ────────────────────────────────────────
        if do_flush:
            try:
                from engine.idle_queue import _bark_cache
                count = len(_bark_cache)
                _bark_cache.clear()
                lines.append(f"  {GREEN}Bark cache cleared.{RST} {count} entries removed.")
                lines.append(f"  Barks will regenerate on next seed tick or room entry.")
            except Exception as e:
                lines.append(f"  {RED}Flush failed: {e}{RST}")
            lines.append(f"{CYAN}══════════════════════════════════════════{RST}")
            await ctx.session.send_line("\n".join(lines))
            return

        # ── Provider status ─────────────────────────────────────────
        if show_providers:
            lines.append(f"  {YELLOW}AI PROVIDERS{RST}")
            try:
                ai_mgr = getattr(ctx.session_mgr, '_ai_manager', None)
                if ai_mgr:
                    status = await ai_mgr.check_status()
                    for pname, pinfo in status.items():
                        avail = pinfo.get("available", False)
                        icon = f"{GREEN}●{RST}" if avail else f"{RED}●{RST}"
                        line = f"  {icon} {pname:<12}"
                        models = pinfo.get("models", [])
                        if models:
                            line += f"  models: {', '.join(models[:5])}"
                        lines.append(line)
                else:
                    lines.append(f"  {RED}AI manager not found{RST}")
            except Exception as e:
                lines.append(f"  Provider status error: {e}")

        # ── Idle queue stats ────────────────────────────────────────
        if show_queue:
            lines.append(f"  {YELLOW}IDLE QUEUE{RST}")
            try:
                _iq = getattr(ctx.server, '_idle_queue', None)
                if not _iq:
                    _iq = getattr(ctx.session_mgr, '_idle_queue', None)
                if _iq:
                    st = _iq.stats
                    lines.append(f"  Pending     : {st['pending']}")
                    lines.append(f"  Completed   : {st['completed']}")
                    lines.append(f"  Failed      : {st['failed']}")
                    busy_str = f"{GREEN}processing{RST}" if st['busy'] else f"{DIM}idle{RST}"
                    lines.append(f"  Status      : {busy_str}")
                    backoff = st.get('backoff_remaining', 0)
                    if backoff > 0:
                        lines.append(f"  Backoff     : {backoff:.1f}s remaining")
                    # Show pending task breakdown
                    if st['pending'] > 0:
                        types = {}
                        for t in _iq._queue:
                            types[t.task_type] = types.get(t.task_type, 0) + 1
                        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(types.items()))
                        lines.append(f"  Breakdown   : {breakdown}")
                else:
                    lines.append(f"  {RED}Idle queue not initialized{RST}")
            except Exception as e:
                lines.append(f"  Queue stats error: {e}")

        # ── Bark cache ──────────────────────────────────────────────
        if show_barks:
            lines.append(f"  {YELLOW}BARK CACHE{RST}")
            try:
                from engine.idle_queue import _bark_cache, BARK_REFRESH_HOURS
                total_npcs = len(_bark_cache)
                total_barks = sum(len(e.get("barks", [])) for e in _bark_cache.values())
                lines.append(f"  NPCs cached : {total_npcs}")
                lines.append(f"  Total barks : {total_barks}")
                lines.append(f"  Refresh     : every {BARK_REFRESH_HOURS}h")
                if _bark_cache:
                    lines.append(f"  {'NPC':<22} {'Barks':>5}  {'Age':>8}")
                    now = time.time()
                    for npc_id, entry in sorted(
                        _bark_cache.items(),
                        key=lambda x: x[1].get("generated_at", 0),
                        reverse=True,
                    )[:10]:
                        name = entry.get("npc_name", f"#{npc_id}")[:20]
                        bcount = len(entry.get("barks", []))
                        age_s = now - entry.get("generated_at", 0)
                        if age_s < 3600:
                            age_str = f"{age_s / 60:.0f}m"
                        else:
                            age_str = f"{age_s / 3600:.1f}h"
                        lines.append(f"    {name:<22} {bcount:>5}  {age_str:>8}")
            except Exception as e:
                lines.append(f"  Bark cache error: {e}")

        lines.append(f"{CYAN}══════════════════════════════════════════{RST}")
        await ctx.session.send_line("\n".join(lines))


def register_director_commands(registry) -> None:
    registry.register(DirectorCommand())
    registry.register(EconomyCommand())
    registry.register(LoreCommand())
    registry.register(HazardCommand())
    registry.register(RoomStateCommand())
    registry.register(AIStatusCommand())
