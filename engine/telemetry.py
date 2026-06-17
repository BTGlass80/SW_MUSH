"""engine/telemetry.py — append-only JSON-line telemetry sink (T3.19, half 2).

Brian 2026-06-06 (``telemetry_purpose_clarified`` in TODO T3.19): the telemetry
half exists to collect broad behavioral + economy data USEFUL TO CLAUDE for
post-launch analysis, so Claude can recommend config-knob changes (the T3.19
levers) grounded in real player behaviour. Posture: append-only JSON-line
events to a dedicated sink, high-frequency events SAMPLED, all emitters
async/buffered/non-blocking — **NEVER slow the game loop**. Aggregation is
offline (Claude reads the dumps), not in-process.

Design (the "never slow the game loop" contract):
  - ``emit()`` ONLY appends a record to a bounded in-memory buffer. It does
    NO file I/O, never raises (fail-open), and is safe to call from sync or
    async code on the event-loop thread.
  - ALL disk writes happen on a periodic flush driven by a tick handler
    (``server/tick_handlers_telemetry.flush_telemetry_tick``), offloaded to a
    thread executor (``flush_async``) so the event loop is never blocked by
    the write.
  - The buffer is a bounded ``deque`` — a stalled or disabled flush can never
    grow memory without bound; overflow silently drops the OLDEST events and
    counts the drop (visible via ``stats()``).
  - Telemetry is fail-open everywhere: a missing/unwritable sink degrades to
    dropping events, never to disturbing gameplay. A credit move, a skill
    check, or a CP award must succeed even if telemetry is broken.

Test isolation: ``emit()`` only buffers; nothing is written to disk until a
flush runs, and flushes are driven by the tick loop (which unit tests do not
run). So a test that exercises an emitter just fills the buffer — call
``reset()`` in a fixture, ``drain()`` to inspect, or ``configure(path=tmp)`` +
``flush()`` to assert the on-disk JSON-line format.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from collections import deque
from typing import Any, Optional

log = logging.getLogger(__name__)

# Default sink lives under the gitignored ``logs/`` tree so it is never
# committed and a fresh checkout writes nothing surprising into version
# control. Overridable via SWMUSH_TELEMETRY_FILE.
_DEFAULT_PATH = os.path.join("logs", "telemetry", "events.jsonl")

# Hard ceiling on the in-memory buffer. At ~150 bytes/event this is a few MB
# worst case if the flush handler dies — bounded, never a leak.
_DEFAULT_MAX_BUFFER = 10_000


def _env_enabled() -> bool:
    """Default-on unless explicitly disabled.

    Brian wants BROAD capture in production, so the live game (which boots the
    flush tick handler) collects by default. The buffer-only ``emit()`` is
    always safe regardless, so this flag only governs whether records are
    retained for flushing — it never affects gameplay.
    """
    raw = os.environ.get("SWMUSH_TELEMETRY_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


class TelemetrySink:
    """Bounded in-memory buffer + append-only JSON-line flush.

    Single instance per process (see ``get_sink()``). Not thread-safe by
    design: every ``emit()`` happens on the asyncio event-loop thread, and
    the only multi-thread hop is the executor-offloaded file write in
    ``flush_async``, which operates on a list already drained on the loop
    thread — so no lock is needed.
    """

    def __init__(self, path: Optional[str] = None, *,
                 enabled: Optional[bool] = None,
                 max_buffer: int = _DEFAULT_MAX_BUFFER) -> None:
        self.path = path if path is not None else os.environ.get(
            "SWMUSH_TELEMETRY_FILE", _DEFAULT_PATH)
        self.enabled = _env_enabled() if enabled is None else bool(enabled)
        self._buffer: deque[str] = deque(maxlen=max(1, int(max_buffer)))
        self._seq = 0
        # Lightweight counters for ops / tests (stats()).
        self._emitted = 0
        self._sampled_out = 0
        self._dropped_overflow = 0
        self._flushed = 0
        self._write_errors = 0

    # ── ingress ──────────────────────────────────────────────────────────
    def emit(self, event_type: str, fields: Optional[dict] = None, *,
             sample: float = 1.0) -> None:
        """Append one event. Non-blocking, fail-open, never raises.

        ``sample`` in (0, 1] keeps a fraction of high-frequency events; a
        value >= 1 always keeps. Sampling decisions are independent per call.
        The serialized record is ``{"ts","seq","ev", **fields}``; a
        non-serializable field degrades to ``str`` rather than dropping the
        event (``default=str``).
        """
        try:
            if not self.enabled or not event_type:
                return
            if sample < 1.0:
                if sample <= 0.0 or random.random() >= sample:
                    self._sampled_out += 1
                    return
            self._seq += 1
            record: dict[str, Any] = {
                "ts": round(time.time(), 3),
                "seq": self._seq,
                "ev": str(event_type),
            }
            if fields:
                # Never let a caller key collide with the envelope fields.
                for k, v in fields.items():
                    if k not in ("ts", "seq", "ev"):
                        record[k] = v
            line = json.dumps(record, separators=(",", ":"), default=str)
            if len(self._buffer) >= self._buffer.maxlen:
                # deque drops the oldest on append at maxlen; count it.
                self._dropped_overflow += 1
            self._buffer.append(line)
            self._emitted += 1
        except Exception:
            # Telemetry must never disturb gameplay. Swallow everything.
            log.debug("telemetry.emit failed", exc_info=True)

    # ── egress ───────────────────────────────────────────────────────────
    def drain(self) -> list[str]:
        """Pop and return all buffered JSON lines (oldest first)."""
        out = list(self._buffer)
        self._buffer.clear()
        return out

    def flush(self) -> int:
        """Synchronously write the buffer to the sink file (append).

        Returns the number of lines written. Fail-open: on any I/O error the
        drained events are dropped (NOT re-queued — re-queuing a permanently
        failing sink would grow unbounded) and counted in ``_write_errors``.
        Mainly for tests + the executor body of ``flush_async``.
        """
        lines = self.drain()
        if not lines:
            return 0
        return self._write_lines(lines)

    def _write_lines(self, lines: list[str]) -> int:
        try:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
                fh.write("\n")
            self._flushed += len(lines)
            return len(lines)
        except Exception:
            self._write_errors += 1
            log.debug("telemetry.flush write failed (events dropped)",
                      exc_info=True)
            return 0

    async def flush_async(self) -> int:
        """Drain on the loop thread, write on a thread executor.

        Keeps the event loop unblocked: the (small) buffer is snapshotted
        synchronously here, then the blocking file write runs off-loop.
        """
        lines = self.drain()
        if not lines:
            return 0
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._write_lines, lines)
        except Exception:
            # No running loop / executor failure → fall back to inline write
            # rather than losing the events.
            return self._write_lines(lines)

    def stats(self) -> dict:
        """Counters for ops dashboards + tests (never affects emit)."""
        return {
            "enabled": self.enabled,
            "path": self.path,
            "buffered": len(self._buffer),
            "emitted": self._emitted,
            "sampled_out": self._sampled_out,
            "dropped_overflow": self._dropped_overflow,
            "flushed": self._flushed,
            "write_errors": self._write_errors,
        }


# ── module singleton + convenience API ───────────────────────────────────
_sink: Optional[TelemetrySink] = None


def get_sink() -> TelemetrySink:
    """Lazily construct and return the process-wide telemetry sink."""
    global _sink
    if _sink is None:
        _sink = TelemetrySink()
    return _sink


def emit(event_type: str, fields: Optional[dict] = None, *,
         sample: float = 1.0) -> None:
    """Module-level convenience: emit through the singleton sink.

    This is the function call sites use. It is fail-open and never raises;
    constructing the sink lazily here means an emitter that fires before the
    server wires telemetry still buffers correctly.
    """
    try:
        get_sink().emit(event_type, fields, sample=sample)
    except Exception:
        log.debug("telemetry.emit (module) failed", exc_info=True)


def configure(*, path: Optional[str] = None, enabled: Optional[bool] = None,
              max_buffer: Optional[int] = None) -> TelemetrySink:
    """(Re)build the singleton with explicit settings. For boot + tests."""
    global _sink
    cur = get_sink()
    _sink = TelemetrySink(
        path=path if path is not None else cur.path,
        enabled=cur.enabled if enabled is None else enabled,
        max_buffer=int(max_buffer) if max_buffer is not None
        else (cur._buffer.maxlen or _DEFAULT_MAX_BUFFER),
    )
    return _sink


def reset() -> None:
    """Drop the singleton (test isolation — next get_sink() rebuilds fresh)."""
    global _sink
    _sink = None
