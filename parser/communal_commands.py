"""parser/communal_commands.py — the `rally` command (Drop 4b, communal-rally villain).

Player surface for the dark-side cult communal objective (design III.3):

  rally            — show the active uprising: who they are, where, the menace
                     meter, the win/lose state, and how to help.
  rally strike     — make your move against the cult. Rolls your BEST cross-
                     playstyle pool (a soldier swings, a slicer digs, a face
                     rallies civilians, a Jedi acts), pushing the menace down.
                     One counted strike per ~10 min so wins come from the
                     COMMUNITY, not one person macroing.

The uprising itself is posted/escalated/resolved by the Director tick
(server/tick_handlers_progression.py::communal_objective_tick); this command is
the participation + visibility surface. All logic lives in
engine/communal_objective_runtime over the pure engine/communal_objective.
Rewards (Republic rep + a III.2 status flag, on a community win) are paid by the
runtime — never credits.
"""
from __future__ import annotations

import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)

_HEADER = "THE CALL TO RALLY"
_INDENT = "  "

_STRIKE_WORDS = {"strike", "hit", "attack", "fight", "act"}


class RallyCommand(BaseCommand):
    key = "rally"
    aliases = ["+rally", "front"]
    access_level = AccessLevel.ANYONE
    help_text = (
        "Rally against the active dark-side cult uprising. "
        "'rally' shows the threat board; 'rally strike' makes your move."
    )
    usage = "rally [strike]"

    async def _emit_staged_tracker(self, ctx, active):
        """EVENT staged scenario: for a STAGED uprising (hollow_sun), print the
        stage tracker -- which stage, the objective, progress -- so `rally` reads
        as a multi-stage operation, not a flat counter. No-op for menace cults."""
        try:
            from engine import staged_event as SE
            from engine import communal_objective as CO
            ckey = active.get("cult_key", "") if active else ""
            if not SE.is_staged(ckey):
                return
            import json as _j
            raw = active.get("contributions_json")
            contribs = raw if isinstance(raw, dict) else _j.loads(raw or "{}")
            cult = CO.CULT_BY_KEY.get(ckey)
            for ln in SE.stage_tracker_lines(
                    cult.name if cult else "the cult", ckey,
                    SE.get_stage_state(contribs)):
                await ctx.session.send_line(ln)
        except Exception:
            log.debug("[rally] staged tracker failed", exc_info=True)

    async def execute(self, ctx: CommandContext) -> None:
        try:
            import engine.communal_objective_runtime as COR
        except Exception:
            await ctx.session.send_line(
                _INDENT + ansi.dim("The rally effort is unavailable right now.")
            )
            return

        sub = (ctx.args or "").strip().lower()

        # ── participate ──────────────────────────────────────────────────────
        if sub in _STRIKE_WORDS:
            char = ctx.session.character if ctx.session else None
            if not char:
                await ctx.session.send_line(
                    _INDENT + ansi.dim("You must be in the world to do that.")
                )
                return
            try:
                result = await COR.record_strike(ctx.db, ctx.session_mgr, char)
            except Exception:
                log.warning("[rally] strike failed", exc_info=True)
                await ctx.session.send_line(
                    _INDENT + ansi.dim("Your move falters in the confusion. Try again.")
                )
                return

            from engine import communal_objective as CO
            if not result.ok and result.reason == "no_active":
                await ctx.session.send_line(
                    _INDENT + ansi.dim("There's no uprising to strike against right now.")
                )
                return
            if not result.ok and result.reason == "cooldown":
                for ln in result.lines:
                    await ctx.session.send_line(_INDENT + ln)
                return
            # hit or miss: render the personal line + the updated meter
            if result.ok and result.outcome is not None:
                await ctx.session.send_line(
                    _INDENT + CO.strike_success_line(result.cult, result.outcome)
                )
            else:
                await ctx.session.send_line(
                    _INDENT + CO.strike_fail_line(result.cult)
                )
            await ctx.session.send_line(
                _INDENT + "Menace: " + CO.menace_bar(result.menace)
            )
            await self._emit_staged_tracker(ctx, await COR.get_active(ctx.db))
            if result.state == CO.STATE_WON:
                await ctx.session.send_line(
                    _INDENT + ansi.dim("The cult is broken — watch the holonet.")
                )
            return

        # ── board view (default) ─────────────────────────────────────────────
        if sub and sub not in _STRIKE_WORDS:
            await ctx.session.send_line(
                _INDENT + ansi.dim("Usage: rally  (view)   |   rally strike  (participate)")
            )
            # fall through to also show the board, so a typo still informs

        try:
            active = await COR.get_active(ctx.db)
            lines = COR.render_board(active)
        except Exception:
            log.warning("[rally] board render failed", exc_info=True)
            await ctx.session.send_line(
                _INDENT + ansi.dim("The rally board is unavailable right now.")
            )
            return

        await ctx.session.send_line(ansi.header(_HEADER))
        await ctx.session.send_line("")
        for ln in lines:
            await ctx.session.send_line(_INDENT + ln)

        await self._emit_staged_tracker(ctx, active)

        # the viewer's own stake + strike-cooldown (blank for onlookers who
        # haven't joined in yet)
        try:
            char = ctx.session.character if ctx.session else None
            if active and char:
                import json as _j
                import time as _t
                from engine import communal_objective as CO
                raw = active.get("contributions_json")
                contribs = raw if isinstance(raw, dict) else _j.loads(raw or "{}")
                mine = CO.viewer_contribution_line(
                    contribs, char["id"], int(_t.time() * 1000))
                if mine:
                    await ctx.session.send_line(_INDENT + mine)
        except Exception:
            log.debug("[rally] viewer-contribution line failed", exc_info=True)

        await ctx.session.send_line("")


# ── Registration ──────────────────────────────────────────────────────────────
def register_communal_commands(registry) -> None:
    """Register the rally command."""
    registry.register(RallyCommand())
