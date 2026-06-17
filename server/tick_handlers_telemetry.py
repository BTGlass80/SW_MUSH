"""server/tick_handlers_telemetry.py — periodic telemetry flush (T3.19).

Drains the in-memory telemetry buffer to the append-only JSON-line sink on a
slow cadence, off the per-command hot path. The write itself is offloaded to a
thread executor by ``flush_async`` so the tick (and the event loop) is never
blocked. Fail-open: a flush error is swallowed inside the sink and a failing
tick is already isolated by the scheduler's per-handler try/except.
"""
from __future__ import annotations

import logging

from server.tick_scheduler import TickContext

log = logging.getLogger(__name__)


async def flush_telemetry_tick(ctx: TickContext) -> None:
    """Flush buffered telemetry events to disk (registered ~every 30s)."""
    from engine.telemetry import get_sink
    await get_sink().flush_async()
