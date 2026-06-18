# -*- coding: utf-8 -*-
"""
server/tick_handlers_death.py — PG.1.death.b (Drop 2d, May 19 2026
evening). Periodic handlers for the death-penalty loop:

  * corpse_decay_tick:    every 5 min, process expired corpses
                          (bound items → owner, generics destroyed).
  * wound_recovery_tick:  every 30 s, scan online characters whose
                          wound_clear_at has passed and transition
                          them back to wound_state='healthy'.

Both are registered in server/game_server.py against the existing
TickScheduler. They're intentionally idempotent — running twice on
the same tick has no observable effect — so missing or repeated
ticks don't accumulate damage.

Failure isolation: each handler logs and continues on per-row
errors. The TickScheduler already wraps the whole handler in
try/except + log.exception, so an entire handler failing one tick
won't kill the others. No global state mutation outside the DB.

Per architecture v45 §4.5 (seam discipline): the actual work lives
in engine/death.py. These handlers are just the scheduler-side
plumbing.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.tick_scheduler import TickContext

log = logging.getLogger(__name__)


async def corpse_decay_tick(ctx: "TickContext") -> None:
    """Sweep all corpses whose decay_at has passed. For each:
    bound items back to owner, generics destroyed, row deleted.

    See engine/death.run_decay_tick for the per-corpse logic.

    Cadence: every 5 minutes (300 ticks). Cheaper than every tick;
    the design's decay windows are hours, so 5-min granularity is
    fine. Phase-shift with offset=37 so this doesn't pile on the
    same wall-clock second as the other 300-interval handlers.
    """
    from engine.death import run_decay_tick
    summaries = await run_decay_tick(ctx.db)
    if summaries:
        log.debug(
            "[corpse_decay_tick] tick=%d processed %d corpse(s)",
            ctx.tick_count, len(summaries),
        )


async def wound_recovery_tick(ctx: "TickContext") -> None:
    """Scan online characters whose wound_clear_at has passed and
    flip them back to wound_state='healthy'. We restrict to online
    chars to avoid scanning the whole characters table every 30
    seconds — offline players will get the transition lazily the
    next time they log in (Drop 2c.c could wire that pickup if
    needed).

    Cadence: every 30 ticks (~30 s). The design's recovery is 1
    hour, so granularity within tens of seconds is plenty.
    """
    now = time.time()
    sm = ctx.session_mgr
    if sm is None:
        return
    # session_mgr exposes the sessions; we want one DB hit per char
    # to check wound_state, then transition. We expect O(few) wounded
    # online players at any time.
    sessions = []
    for s in sm.all:
        if getattr(s, "character", None):
            sessions.append(s)

    for s in sessions:
        char = s.character
        if not char:
            continue
        # Local-fast-path: skip chars we can already see are healthy.
        cached_state = char.get("wound_state") or "healthy"
        cached_clear_at = float(char.get("wound_clear_at") or 0.0)
        if cached_state != "wounded":
            continue
        if cached_clear_at <= 0 or cached_clear_at > now:
            continue
        # Authoritative DB read, then transition. tick_wound_recovery
        # idempotently returns False if the DB row's state diverges
        # (e.g. bacta tank already cleared it in another tick).
        try:
            from engine.death import tick_wound_recovery
            cleared = await tick_wound_recovery(ctx.db, char["id"])
            if cleared:
                # Sync the in-memory cache so subsequent commands
                # see healthy without an extra DB hit.
                char["wound_state"] = "healthy"
                char["wound_clear_at"] = 0.0
                # User-visible message — a tap on the shoulder when
                # the timer expires. Quiet and one-line, in the
                # bacta-narration colour palette to stay consistent
                # with the respawn flow.
                try:
                    await s.send_line(
                        "  \033[36mYour wounds finish knitting. "
                        "You feel whole again.\033[0m"
                    )
                except Exception:
                    log.debug(
                        "wound_recovery_tick: send_line failed for "
                        "char %d", char.get("id"), exc_info=True,
                    )
        except Exception:
            log.warning(
                "wound_recovery_tick: tick_wound_recovery failed "
                "for char %s", char.get("id"), exc_info=True,
            )
