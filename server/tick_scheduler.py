"""
Tick scheduler — review fix v1.

Replaces the 470-line monolithic `_game_tick_loop` in game_server.py with a
registry of independent handlers. Each handler declares its interval (in
ticks) and receives a shared TickContext so expensive fetches like
`get_ships_in_space()` happen once per tick, not N times.

Design doc: code_review_fixes_design_v1.md §3.

Migration strategy: This scaffold runs *alongside* the existing inline
tick blocks. Handlers are ported over incrementally — one per session —
with each ported block deleted from game_server.py. When empty, the old
inline code is gone.

Important: handlers that mutate ship state should also update their
entry in `ctx.ships_in_space` in-place so later handlers in the same
tick see fresh data.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

if TYPE_CHECKING:
    from server.game_server import GameServer
    from server.session import SessionManager
    from db.database import Database

log = logging.getLogger(__name__)


@dataclass
class TickContext:
    """Shared state for a single tick. Handlers read and may mutate this."""
    server: "GameServer"
    db: "Database"
    session_mgr: "SessionManager"
    tick_count: int
    # Fetched once at the top of the tick. Handlers that mutate ships
    # should also mutate the corresponding dict in this list so later
    # handlers see the new state.
    ships_in_space: list[dict] = field(default_factory=list)


HandlerFn = Callable[[TickContext], Awaitable[None]]


@dataclass
class TickHandler:
    name: str
    interval: int  # every N ticks
    fn: HandlerFn
    offset: int = 0  # optional phase shift so handlers don't all pile on tick 0


class TickScheduler:
    """Registry + dispatch for per-tick game logic.

    Each handler is wrapped in its own try/except that calls log.exception
    (NOT log.debug) so that any failing handler is visible in production
    logs without affecting the others.
    """

    def __init__(self) -> None:
        self._handlers: list[TickHandler] = []

    def register(
        self,
        name: str,
        fn: HandlerFn,
        *,
        interval: int = 1,
        offset: int = 0,
    ) -> None:
        """Register a tick handler.

        interval=1  → every tick (~1s)
        interval=30 → every 30 ticks (~30s)
        interval=3600 → every hour
        """
        if interval < 1:
            raise ValueError(f"interval must be >= 1, got {interval}")
        self._handlers.append(TickHandler(name=name, interval=interval,
                                          fn=fn, offset=offset))
        log.info("TickScheduler: registered %s (every %d ticks)",
                 name, interval)

    async def run_tick(self, ctx: TickContext) -> None:
        """Run every handler whose interval matches this tick.

        Failures in one handler never affect another. Every failure is
        logged with full traceback — this is deliberate, to fix the
        "silent subsystem" bug identified in the code review.
        """
        for h in self._handlers:
            if (ctx.tick_count - h.offset) % h.interval != 0:
                continue
            try:
                await h.fn(ctx)
            except Exception:
                # log.exception, NOT log.debug. Noise is the point.
                log.exception(
                    "Tick handler %r raised at tick %d",
                    h.name, ctx.tick_count,
                )

    def handler_count(self) -> int:
        return len(self._handlers)
