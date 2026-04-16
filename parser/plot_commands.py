# -*- coding: utf-8 -*-
"""
parser/plot_commands.py — Plot / Story Arc commands for SW_MUSH.

Commands:
  +plots                           List open plots
  +plot <id>                       View plot details + linked scenes
  +plot/create <title>=<summary>   Create a new plot
  +plot/summary <id>=<text>        Update plot summary
  +plot/link <plot_id>=<scene_id>  Link a scene to a plot
  +plot/unlink <plot_id>=<scene_id> Unlink a scene from a plot
  +plot/close <id>                 Close a completed plot
  +plot/reopen <id>                Reopen a closed plot
"""

import logging
import time

from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)


# ── Formatting helpers ─────────────────────────────────────────────────────────

_STATUS_COLOR = {
    "open":   "\033[1;32m",   # bright green
    "closed": "\033[0;33m",   # amber
}

def _fmt_status(status: str) -> str:
    color = _STATUS_COLOR.get(status, "\033[0m")
    return f"{color}{status.upper()}\033[0m"

def _fmt_date(ts) -> str:
    if not ts:
        return "—"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


# ── Commands ───────────────────────────────────────────────────────────────────

class PlotsListCommand(BaseCommand):
    """List plots."""
    key = "+plots"
    aliases = ["+plot/list", "+arcs"]
    help_category = "Social"
    help_text = "List open story arcs / plots."

    async def execute(self, ctx: CommandContext):
        from engine.plots import get_open_plots, get_scene_count
        plots = await get_open_plots(ctx.db, limit=30)
        if not plots:
            await ctx.session.send_line("No open plots.")
            await ctx.session.send_line(
                "\033[2mUse +plot/create <title>=<summary> to start one!\033[0m")
            return

        lines = ["\033[33m═══ OPEN PLOTS ═══\033[0m"]
        for p in plots:
            sc_count = await get_scene_count(ctx.db, p["id"])
            lines.append(
                f"  \033[96m#{p['id']}\033[0m {p['title']}  "
                f"{_fmt_status(p['status'])}"
            )
            lines.append(
                f"      \033[2m{sc_count} scene{'s' if sc_count != 1 else ''} · "
                f"by {p['creator_name']} · updated {_fmt_date(p['updated_at'])}\033[0m"
            )
            if p.get("summary"):
                # Truncate summary for list view
                s = p["summary"]
                if len(s) > 80:
                    s = s[:77] + "..."
                lines.append(f"      \033[2m{s}\033[0m")

        lines.append("")
        lines.append("\033[2mUse +plot <id> for details. +plot/create <title>=<summary> to start one.\033[0m")
        await ctx.session.send_line("\r\n".join(lines))


class PlotDetailCommand(BaseCommand):
    """View plot details + linked scenes."""
    key = "+plot"
    help_category = "Social"
    help_text = "View plot details: +plot <id>"

    async def execute(self, ctx: CommandContext):
        # Dispatch sub-commands
        if ctx.switches:
            sub = ctx.switches[0]
            if sub == "create":
                return await _cmd_create(ctx)
            elif sub == "summary":
                return await _cmd_summary(ctx)
            elif sub == "link":
                return await _cmd_link(ctx)
            elif sub == "unlink":
                return await _cmd_unlink(ctx)
            elif sub == "close":
                return await _cmd_close(ctx)
            elif sub == "reopen":
                return await _cmd_reopen(ctx)
            else:
                await ctx.session.send_line(
                    f"Unknown switch: /{sub}. "
                    f"Valid: /create, /summary, /link, /unlink, /close, /reopen")
                return

        if not ctx.args or not ctx.args.strip():
            await ctx.session.send_line("Usage: +plot <id>")
            return

        try:
            plot_id = int(ctx.args.strip().lstrip("#"))
        except ValueError:
            await ctx.session.send_line("Usage: +plot <number>")
            return

        from engine.plots import get_plot, get_plot_scenes
        p = await get_plot(ctx.db, plot_id)
        if not p:
            await ctx.session.send_line(f"Plot #{plot_id} not found.")
            return

        scenes = await get_plot_scenes(ctx.db, plot_id)

        lines = [f"\033[33m═══ PLOT #{p['id']}: {p['title']} ═══\033[0m"]
        lines.append(f"  \033[96mStatus:\033[0m  {_fmt_status(p['status'])}")
        lines.append(f"  \033[96mCreator:\033[0m {p['creator_name']}")
        lines.append(f"  \033[96mCreated:\033[0m {_fmt_date(p['created_at'])}")
        lines.append(f"  \033[96mUpdated:\033[0m {_fmt_date(p['updated_at'])}")

        if p.get("summary"):
            lines.append(f"  \033[96mSummary:\033[0m")
            for line in p["summary"].split("\n"):
                lines.append(f"    {line}")

        if scenes:
            lines.append(f"  \033[96mLinked Scenes ({len(scenes)}):\033[0m")
            for s in scenes:
                status_tag = ""
                if s["status"] == "active":
                    status_tag = " \033[92m[ACTIVE]\033[0m"
                elif s["status"] == "shared":
                    status_tag = " \033[36m[SHARED]\033[0m"
                parts_str = ", ".join(s.get("participants", [])[:5])
                lines.append(
                    f"    \033[96m#{s['id']}\033[0m {s.get('title') or '(untitled)'}"
                    f"{status_tag}"
                )
                lines.append(
                    f"        \033[2m{s.get('scene_type', '')} · "
                    f"{s['pose_count']} poses · "
                    f"{parts_str}\033[0m"
                )
        else:
            lines.append(f"  \033[2mNo linked scenes yet.\033[0m")

        lines.append("")
        char_id = ctx.session.character["id"]
        if p["creator_id"] == char_id:
            lines.append(
                "\033[2m+plot/link %d=<scene_id> to add scenes. "
                "+plot/close %d when finished.\033[0m" % (plot_id, plot_id))
        else:
            lines.append(
                "\033[2m+plot/link %d=<scene_id> to add your scenes.\033[0m"
                % plot_id)

        await ctx.session.send_line("\r\n".join(lines))


# ── Sub-command handlers ───────────────────────────────────────────────────────

async def _cmd_create(ctx: CommandContext):
    """Create a new plot: +plot/create <title>=<summary>"""
    if not ctx.args or "=" not in ctx.args:
        await ctx.session.send_line("Usage: +plot/create <title>=<summary>")
        return

    title, _, summary = ctx.args.partition("=")
    title = title.strip()
    summary = summary.strip()

    if not title:
        await ctx.session.send_line("Plot title required.")
        return
    if len(title) > 100:
        await ctx.session.send_line("Title too long (100 char max).")
        return

    from engine.plots import create_plot
    p = await create_plot(
        ctx.db,
        creator_id=ctx.session.character["id"],
        creator_name=ctx.session.character["name"],
        title=title,
        summary=summary,
    )

    await ctx.session.send_line(f"\033[92mPlot #{p['id']} created: {title}\033[0m")
    await ctx.session.send_line(
        f"Link scenes: +plot/link {p['id']}=<scene_id>")
    if not summary:
        await ctx.session.send_line(
            f"Add summary: +plot/summary {p['id']}=<text>")


async def _cmd_summary(ctx: CommandContext):
    """Update plot summary: +plot/summary <id>=<text>"""
    if not ctx.args or "=" not in ctx.args:
        await ctx.session.send_line("Usage: +plot/summary <id>=<text>")
        return

    id_str, _, text = ctx.args.partition("=")
    try:
        plot_id = int(id_str.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +plot/summary <id>=<text>")
        return

    from engine.plots import get_plot, update_plot
    p = await get_plot(ctx.db, plot_id)
    if not p:
        await ctx.session.send_line(f"Plot #{plot_id} not found.")
        return
    if p["creator_id"] != ctx.session.character["id"]:
        await ctx.session.send_line("Only the plot creator can update the summary.")
        return

    await update_plot(ctx.db, plot_id, summary=text.strip())
    await ctx.session.send_line(f"\033[92mPlot #{plot_id} summary updated.\033[0m")


async def _cmd_link(ctx: CommandContext):
    """Link scene to plot: +plot/link <plot_id>=<scene_id>"""
    if not ctx.args or "=" not in ctx.args:
        await ctx.session.send_line("Usage: +plot/link <plot_id>=<scene_id>")
        return

    pid_str, _, sid_str = ctx.args.partition("=")
    try:
        plot_id = int(pid_str.strip().lstrip("#"))
        scene_id = int(sid_str.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +plot/link <plot_id>=<scene_id>")
        return

    from engine.plots import get_plot, link_scene
    p = await get_plot(ctx.db, plot_id)
    if not p:
        await ctx.session.send_line(f"Plot #{plot_id} not found.")
        return

    # Verify scene exists
    rows = await ctx.db.fetchall(
        "SELECT id, title FROM scenes WHERE id = ?", (scene_id,)
    )
    if not rows:
        await ctx.session.send_line(f"Scene #{scene_id} not found.")
        return

    # Verify caller participated in the scene or is plot creator
    char_id = ctx.session.character["id"]
    parts = await ctx.db.fetchall(
        "SELECT 1 FROM scene_participants WHERE scene_id=? AND char_id=?",
        (scene_id, char_id)
    )
    if not parts and p["creator_id"] != char_id:
        await ctx.session.send_line(
            "You must be a scene participant or the plot creator to link scenes.")
        return

    ok = await link_scene(ctx.db, plot_id, scene_id)
    scene_title = rows[0]["title"] or f"Scene #{scene_id}"
    if ok:
        await ctx.session.send_line(
            f"\033[92mLinked '{scene_title}' to plot #{plot_id}.\033[0m")
    else:
        await ctx.session.send_line(
            f"Scene #{scene_id} is already linked to plot #{plot_id}.")


async def _cmd_unlink(ctx: CommandContext):
    """Unlink scene from plot: +plot/unlink <plot_id>=<scene_id>"""
    if not ctx.args or "=" not in ctx.args:
        await ctx.session.send_line("Usage: +plot/unlink <plot_id>=<scene_id>")
        return

    pid_str, _, sid_str = ctx.args.partition("=")
    try:
        plot_id = int(pid_str.strip().lstrip("#"))
        scene_id = int(sid_str.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +plot/unlink <plot_id>=<scene_id>")
        return

    from engine.plots import get_plot, unlink_scene
    p = await get_plot(ctx.db, plot_id)
    if not p:
        await ctx.session.send_line(f"Plot #{plot_id} not found.")
        return

    # Only plot creator can unlink
    if p["creator_id"] != ctx.session.character["id"]:
        await ctx.session.send_line("Only the plot creator can unlink scenes.")
        return

    ok = await unlink_scene(ctx.db, plot_id, scene_id)
    if ok:
        await ctx.session.send_line(
            f"\033[92mScene #{scene_id} unlinked from plot #{plot_id}.\033[0m")
    else:
        await ctx.session.send_line(
            f"Scene #{scene_id} is not linked to plot #{plot_id}.")


async def _cmd_close(ctx: CommandContext):
    """Close a plot: +plot/close <id>"""
    if not ctx.args:
        await ctx.session.send_line("Usage: +plot/close <id>")
        return

    try:
        plot_id = int(ctx.args.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +plot/close <id>")
        return

    from engine.plots import get_plot, close_plot
    p = await get_plot(ctx.db, plot_id)
    if not p:
        await ctx.session.send_line(f"Plot #{plot_id} not found.")
        return
    if p["creator_id"] != ctx.session.character["id"]:
        await ctx.session.send_line("Only the plot creator can close it.")
        return
    if p["status"] == "closed":
        await ctx.session.send_line("Plot is already closed.")
        return

    await close_plot(ctx.db, plot_id)
    await ctx.session.send_line(
        f"\033[33mPlot #{plot_id} '{p['title']}' has been closed.\033[0m")


async def _cmd_reopen(ctx: CommandContext):
    """Reopen a closed plot: +plot/reopen <id>"""
    if not ctx.args:
        await ctx.session.send_line("Usage: +plot/reopen <id>")
        return

    try:
        plot_id = int(ctx.args.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +plot/reopen <id>")
        return

    from engine.plots import get_plot, reopen_plot
    p = await get_plot(ctx.db, plot_id)
    if not p:
        await ctx.session.send_line(f"Plot #{plot_id} not found.")
        return
    if p["creator_id"] != ctx.session.character["id"]:
        await ctx.session.send_line("Only the plot creator can reopen it.")
        return
    if p["status"] == "open":
        await ctx.session.send_line("Plot is already open.")
        return

    await reopen_plot(ctx.db, plot_id)
    await ctx.session.send_line(
        f"\033[92mPlot #{plot_id} '{p['title']}' has been reopened.\033[0m")


# ── Registration ───────────────────────────────────────────────────────────────

def register_plot_commands(registry) -> None:
    registry.register(PlotsListCommand())
    registry.register(PlotDetailCommand())
    log.info("[plots] plot commands registered")
