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
  - The on-disk sink is bounded too: the append-only file is rotated when it
    reaches ``max_file_bytes`` (keeping ``backup_count`` backups), so broad
    default-on capture over a launch can never exhaust the disk. Rotation runs
    on the flush executor thread and is itself fail-open.
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

# Bounded tail read for the offline read-side (``read_recent`` / the @balance
# admin view). The sink is append-only and can grow large over a launch; an
# admin asking for a balance summary should never read an unbounded file, so we
# seek to the last N bytes and parse only that window. ~4 MiB ≈ 25k events.
_MAX_READ_BYTES = 4 * 1024 * 1024

# On-disk sink cap. The in-memory buffer (above) is bounded, but the
# append-only FILE was not — a default-on, broad-capture sink grows without
# bound over a launch and can eventually exhaust the disk. When the current
# file reaches this size it is rotated (``events.jsonl`` -> ``events.jsonl.1``,
# older backups shift up to ``.<BACKUP_COUNT>``, the oldest discarded), so
# on-disk telemetry is bounded at roughly ``(BACKUP_COUNT + 1) * MAX_FILE_BYTES``.
# The cap is set well above the read window (``_MAX_READ_BYTES``) so the
# @balance read view stays full in steady state (it reads only the current
# file). Overridable via env; ``0`` disables rotation (unbounded growth).
_DEFAULT_MAX_FILE_BYTES = 64 * 1024 * 1024   # 64 MiB
_DEFAULT_BACKUP_COUNT = 3


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


def _env_int(name: str, default: int) -> int:
    """Read a non-negative int env override, falling back on anything bad."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw.strip()))
    except (TypeError, ValueError):
        return default


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
                 max_buffer: int = _DEFAULT_MAX_BUFFER,
                 max_file_bytes: Optional[int] = None,
                 backup_count: Optional[int] = None) -> None:
        self.path = path if path is not None else os.environ.get(
            "SWMUSH_TELEMETRY_FILE", _DEFAULT_PATH)
        self.enabled = _env_enabled() if enabled is None else bool(enabled)
        self._buffer: deque[str] = deque(maxlen=max(1, int(max_buffer)))
        # On-disk rotation cap (0 disables). See _DEFAULT_MAX_FILE_BYTES.
        self.max_file_bytes = (
            _env_int("SWMUSH_TELEMETRY_MAX_BYTES", _DEFAULT_MAX_FILE_BYTES)
            if max_file_bytes is None else max(0, int(max_file_bytes)))
        self.backup_count = (
            _env_int("SWMUSH_TELEMETRY_BACKUPS", _DEFAULT_BACKUP_COUNT)
            if backup_count is None else max(0, int(backup_count)))
        self._seq = 0
        # Lightweight counters for ops / tests (stats()).
        self._emitted = 0
        self._sampled_out = 0
        self._dropped_overflow = 0
        self._flushed = 0
        self._write_errors = 0
        self._rotations = 0

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

    def peek(self) -> list[str]:
        """Copy the buffered JSON lines WITHOUT draining (oldest first).

        For the read-side (``read_recent`` / the @balance admin view): the
        un-flushed buffer holds the most recent events not yet on disk, so a
        summary must include them — but reading them must NOT consume them, or
        the next flush would lose those events. Returns a snapshot copy; the
        buffer is untouched and the flush tick still writes them normally.
        """
        return list(self._buffer)

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
            self._maybe_rotate()
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

    def _maybe_rotate(self) -> None:
        """Roll the sink file when it exceeds ``max_file_bytes``, keeping
        ``backup_count`` backups.

        The buffer is already bounded; only the append-only FILE was not, so a
        default-on broad-capture sink could grow without bound over a launch and
        eventually exhaust the disk. When the current file reaches the cap it is
        rolled to ``<path>.1`` (older backups shift up to ``.<backup_count>``,
        the oldest discarded), bounding on-disk telemetry at roughly
        ``(backup_count + 1) * max_file_bytes``.

        Runs on the executor thread (inside ``_write_lines``), never on the
        event loop. Fail-open: any rotation error is swallowed and we keep
        appending to the current file — telemetry must never disturb gameplay,
        and a failed roll is strictly better than a lost write. The brief
        post-rotation window where the current file is small (and the @balance
        read view shows less history) self-heals as the new file fills; the cap
        is set far above ``_MAX_READ_BYTES`` so this is rare.
        """
        try:
            cap = self.max_file_bytes
            if cap <= 0:
                return  # rotation disabled → unbounded (opt-out / tests)
            if not os.path.exists(self.path):
                return
            if os.path.getsize(self.path) < cap:
                return
            backups = self.backup_count
            if backups <= 0:
                # No history kept: discard the full file and start fresh.
                os.remove(self.path)
                self._rotations += 1
                return
            # Shift .{i} -> .{i+1} from oldest to newest, then path -> .1.
            # os.replace is atomic and overwrites, so the oldest backup
            # (.<backups>) is dropped without an explicit remove.
            for i in range(backups - 1, 0, -1):
                src = "%s.%d" % (self.path, i)
                if os.path.exists(src):
                    os.replace(src, "%s.%d" % (self.path, i + 1))
            os.replace(self.path, self.path + ".1")
            self._rotations += 1
        except Exception:
            log.debug("telemetry rotate failed (continuing on current file)",
                      exc_info=True)

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
            "max_file_bytes": self.max_file_bytes,
            "backup_count": self.backup_count,
            "rotations": self._rotations,
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


def emit_objective(kind: str, phase: str, char_id: Any, *, oid: str = "",
                   reward: int = 0, **extra: Any) -> None:
    """Emit one objective-funnel event (T3.19 catalog C — missions/quests).

    A SINGLE event type (``objective``) with ``kind`` + ``phase`` keeps the
    offline funnel trivial: ``count(start)`` vs ``count(complete)`` vs
    ``count(abandon)`` per ``kind``, plus the reward distribution per outcome
    — exactly the post-launch balance signal Brian wants (do missions get
    started but abandoned? is one tier's pay too low to bother finishing?).

      kind   : the objective system — ``"mission"`` / ``"bounty"`` / ``"smuggling"``
      phase  : the lifecycle transition — ``"start"`` / ``"complete"`` / ``"abandon"``
      char_id: the acting character (coerced to ``int`` when it parses, so a
               str-id system and an int-id system join on the same player)
      oid    : the objective id (mission / contract / job id)
      reward : credits at stake — the funnel value
      extra  : kind-specific fields (mission_type, tier, cargo, target, …);
               ``None`` values are dropped so the record stays clean.

    Fail-open: this wraps the already-fail-open ``emit()`` and additionally
    guards the field assembly, so a telemetry break can NEVER disturb the
    accept/complete/abandon path it observes.
    """
    try:
        try:
            char_id = int(char_id)
        except (TypeError, ValueError):
            pass
        fields: dict[str, Any] = {
            "kind": kind, "phase": phase, "char_id": char_id,
            "oid": oid, "reward": reward,
        }
        for k, v in extra.items():
            if v is not None and k not in fields:
                fields[k] = v
        emit("objective", fields)
    except Exception:
        log.debug("telemetry.emit_objective failed", exc_info=True)


def emit_cp_income(source: str, char_id: Any, *, cp_gained: int = 0,
                   ticks: int = 0, ticks_this_week: Any = None,
                   at_cap: bool = False, **extra: Any) -> None:
    """Emit one CP-income-funnel event (T3.19 catalog — progression).

    A SINGLE event type (``cp_income``) tagged by ``source`` collapses every
    Character-Point faucet into one offline funnel: the per-source CP-income
    share (kudos vs scene vs passive vs ai_eval vs milestone vs achievement vs
    padawan_training), the tick→CP conversion rate, and weekly-cap pressure —
    exactly the signal Brian wants to tune the CP levers (TICKS_PER_CP,
    WEEKLY_CAP_TICKS, KUDOS_TICKS, SCENE_TICKS_PER_POSE, …) on real post-launch
    progression data rather than guesses. (Named ``cp_income`` — NOT
    ``cp_progress`` — to stay clear of the HUD sidebar's ``cp_progress`` key.)

      source   : the CP income source — a tick source ("passive"/"scene"/
                 "kudos"/"ai_eval") or a direct-CP source ("milestone"/
                 "achievement"/"padawan_training").
      char_id  : the receiving character (coerced to int when it parses, so a
                 str-id system and an int-id system join on the same player).
      cp_gained: CP credited THIS event (tick→CP conversion, or the direct
                 grant amount). 0 is valid (ticks accrued, no conversion yet).
      ticks    : tick-economy ticks awarded this event (0 for direct-CP).
      ticks_this_week: ticks this rolling week AFTER the award — the cap-
                 pressure signal. ``None`` (direct-CP bypasses the cap) is
                 dropped from the record.
      at_cap   : the award reached / was bounded by the weekly tick cap.
      extra    : source-specific fields (reason, ach_key, …); ``None`` dropped.

    Sampling honours ``telemetry.cp_income_sample`` (default 1.0 — CP income is
    low-frequency + high-value, so full capture by default). Fail-open: wraps
    the already-fail-open ``emit()`` and guards the field assembly + tunable
    read, so a telemetry break can NEVER disturb a CP award.
    """
    try:
        try:
            char_id = int(char_id)
        except (TypeError, ValueError):
            pass
        fields: dict[str, Any] = {
            "source": source, "char_id": char_id,
            "cp_gained": cp_gained, "ticks": ticks, "at_cap": bool(at_cap),
        }
        if ticks_this_week is not None:
            fields["ticks_this_week"] = ticks_this_week
        for k, v in extra.items():
            if v is not None and k not in fields:
                fields[k] = v
        try:
            from engine.tunables import get_tunable
            sample = float(get_tunable("telemetry.cp_income_sample", 1.0))
        except Exception:
            sample = 1.0
        emit("cp_income", fields, sample=sample)
    except Exception:
        log.debug("telemetry.emit_cp_income failed", exc_info=True)


def emit_grind_kill(char_id: Any, *, reward: int = 0, daily_credits: int = 0,
                    at_cap: bool = False, over_cap: bool = False,
                    total_kills: int = 0, npc_name: str = "",
                    room_id: Any = None, **extra: Any) -> None:
    """Emit one mob-grind kill-reward event (T3.19 breadth — grind/rewards).

    The solo-PvE mob-grind faucet (``engine/hunting_rewards.on_huntable_kill``)
    already tags its CREDIT leg on the ledger (``mob_grind``), but those isolated
    credit rows cannot be rejoined offline into the grind FUNNEL: the per-kill
    payout distribution, how fast a grinder hits the 400 cr/day SOFT CAP (and how
    much of the session runs on the OVER_CAP_FLOOR trickle tail), what / where is
    being farmed, and how deep engagement runs (lifetime kills, milestone
    titles). A SINGLE ``grind_kill`` event joined to ``credit_flow`` on
    ``char_id`` gives exactly the signal to tune the grind knobs (BASE_REWARD /
    DAILY_SOFT_CAP / OVER_CAP_FLOOR) on real post-launch behaviour — does the cap
    bite too early? is the trickle tail so thin nobody grinds past it? are some
    zones farmed while others sit idle?

      char_id      : the grinding character (coerced to int when it parses, so a
                     str-id system and an int-id system join on the same player).
      reward       : credits paid for THIS kill (BASE_REWARD or OVER_CAP_FLOOR).
      daily_credits: grind credits earned today AFTER this kill — cap pressure.
      at_cap       : the day's grind income has reached / passed the soft cap.
      over_cap     : THIS kill was paid at the trickle floor (already past cap
                     when the reward was computed).
      total_kills  : lifetime huntable kills AFTER this one (engagement depth).
      npc_name     : what was killed (the mob's display name).
      room_id      : where the kill happened (the grinder's room — offline
                     resolves room->zone->threat-band). ``None`` is dropped.
      extra        : cheap in-memory context (species, faction, behavior);
                     ``None`` values dropped so the record stays clean.

    Sampling honours ``telemetry.grind_kill_sample`` (default 1.0 — the daily
    soft cap already bounds a grinder's kill volume, so full capture is
    affordable and sampling it down would blur the very cap-pressure curve this
    exists to show). Fail-open: wraps the already-fail-open ``emit()`` and guards
    the field assembly + tunable read, so a telemetry break can NEVER disturb the
    reward path it observes.
    """
    try:
        try:
            char_id = int(char_id)
        except (TypeError, ValueError):
            pass
        fields: dict[str, Any] = {
            "char_id": char_id, "reward": reward,
            "daily_credits": daily_credits, "at_cap": bool(at_cap),
            "over_cap": bool(over_cap), "total_kills": total_kills,
            "npc_name": npc_name,
        }
        if room_id is not None:
            fields["room_id"] = room_id
        for k, v in extra.items():
            if v is not None and k not in fields:
                fields[k] = v
        try:
            from engine.tunables import get_tunable
            sample = float(get_tunable("telemetry.grind_kill_sample", 1.0))
        except Exception:
            sample = 1.0
        emit("grind_kill", fields, sample=sample)
    except Exception:
        log.debug("telemetry.emit_grind_kill failed", exc_info=True)


def emit_session(phase: str, char_id: Any = None, *, account_id: Any = None,
                 transport: str = "", duration_s: Any = None,
                 connected_s: Any = None, reached_game: Any = None,
                 **extra: Any) -> None:
    """Emit one session-lifecycle event (T3.19 breadth — engagement/retention).

    The economy/progression funnels above show what players DO once in-game, but
    nothing captured *how long they stay* or *how often they come back* — the
    engagement primitive Brian wants for tuning the play loop (is ``idle_timeout``
    cutting real sessions short? what is a typical session length? do web players
    stay longer than telnet purists? what is the connect→login conversion?). A
    DB scan can't answer it (no login ledger), so this is the only record.

    A SINGLE event type (``session``) tagged by ``phase`` keeps the offline
    funnel trivial, mirroring ``objective``:

      phase       : the lifecycle transition —
                    ``"login"``  = a character entered the world (reached IN_GAME)
                    ``"logout"`` = a connection was torn down (every disconnect
                                   path funnels through SessionManager.remove).
      char_id     : the acting character (coerced to int when it parses, so a
                    str-id system and an int-id system join on the same player).
                    ``None`` for a connection that disconnected before selecting
                    a character (a bounce at the login screen).
      account_id  : the owning account (the retention join key across alts).
      transport   : ``"telnet"`` / ``"websocket"`` — the web-vs-purist mix.
      duration_s  : play time this session (login→logout), on the logout event
                    only. ``None`` when the connection never reached the game.
      connected_s : the full connect→disconnect span (logout only) — includes
                    pre-auth time, so connected_s vs duration_s exposes how much
                    of a connection is spent bouncing at the login screen.
      reached_game: whether the connection ever entered the world — the
                    connect→login funnel: ``count(logout)`` is connects,
                    ``count(login)`` (== logouts with reached_game) is logins.
      extra       : any cheap context (``None`` values dropped).

    Sampling honours ``telemetry.session_sample`` (default 1.0 — one event per
    connect/disconnect is very low frequency, and sampling would blur the very
    session-length distribution this exists to show). Fail-open: wraps the
    already-fail-open ``emit()`` and guards the field assembly + tunable read, so
    a telemetry break can NEVER disturb a login or a teardown.
    """
    try:
        try:
            char_id = int(char_id)
        except (TypeError, ValueError):
            pass
        fields: dict[str, Any] = {"phase": phase}
        if char_id is not None:
            fields["char_id"] = char_id
        if account_id is not None:
            try:
                fields["account_id"] = int(account_id)
            except (TypeError, ValueError):
                fields["account_id"] = account_id
        if transport:
            fields["transport"] = str(transport)
        if duration_s is not None:
            try:
                fields["duration_s"] = round(float(duration_s), 1)
            except (TypeError, ValueError):
                pass
        if connected_s is not None:
            try:
                fields["connected_s"] = round(float(connected_s), 1)
            except (TypeError, ValueError):
                pass
        if reached_game is not None:
            fields["reached_game"] = bool(reached_game)
        for k, v in extra.items():
            if v is not None and k not in fields:
                fields[k] = v
        try:
            from engine.tunables import get_tunable
            sample = float(get_tunable("telemetry.session_sample", 1.0))
        except Exception:
            sample = 1.0
        emit("session", fields, sample=sample)
    except Exception:
        log.debug("telemetry.emit_session failed", exc_info=True)


def configure(*, path: Optional[str] = None, enabled: Optional[bool] = None,
              max_buffer: Optional[int] = None,
              max_file_bytes: Optional[int] = None,
              backup_count: Optional[int] = None) -> TelemetrySink:
    """(Re)build the singleton with explicit settings. For boot + tests.

    Unspecified settings (including the on-disk rotation cap / backup count)
    are carried forward from the current sink so a re-``configure`` never
    silently drops the rotation policy.
    """
    global _sink
    cur = get_sink()
    _sink = TelemetrySink(
        path=path if path is not None else cur.path,
        enabled=cur.enabled if enabled is None else enabled,
        max_buffer=int(max_buffer) if max_buffer is not None
        else (cur._buffer.maxlen or _DEFAULT_MAX_BUFFER),
        max_file_bytes=cur.max_file_bytes if max_file_bytes is None
        else max_file_bytes,
        backup_count=cur.backup_count if backup_count is None
        else backup_count,
    )
    return _sink


def reset() -> None:
    """Drop the singleton (test isolation — next get_sink() rebuilds fresh)."""
    global _sink
    _sink = None


# ── read side (offline aggregation for the @balance admin view) ───────────
#
# The emit side is the hot path and stays write-only + fail-open. Everything
# below is the COLD read side: an admin asking "what is the economy/progression
# data telling us?" in-game. It reads the append-only dump (bounded tail) plus
# the un-flushed buffer, then rolls events up into the balance-tuning signals
# Brian wants (grind cap pressure, CP source mix, objective funnels, encounter
# pacing). It is itself fail-open — a missing/corrupt sink yields an empty
# summary, never an error — and bounded, so it cannot block or exhaust memory.

def _parse_lines(lines: list[str]) -> list[dict]:
    """Parse JSON-line records, skipping blanks and any malformed line."""
    out: list[dict] = []
    for ln in lines:
        ln = (ln or "").strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _read_disk_records(path: Optional[str]) -> list[dict]:
    """Read + parse the bounded tail of the on-disk sink. Fail-open → []."""
    try:
        if not path or not os.path.exists(path):
            return []
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > _MAX_READ_BYTES:
                fh.seek(size - _MAX_READ_BYTES)
                fh.readline()  # discard the partial line at the seek point
            data = fh.read()
        text = data.decode("utf-8", errors="replace")
        return _parse_lines(text.splitlines())
    except Exception:
        log.debug("telemetry.read disk failed", exc_info=True)
        return []


def read_recent(limit: int = 10_000, *, include_buffer: bool = True) -> list[dict]:
    """Read recent telemetry events: bounded on-disk tail + in-memory buffer.

    Synchronous (does a file read inline) — prefer ``read_recent_async`` from
    the event loop. ``include_buffer`` folds in the un-flushed events so a live
    summary is current. ``limit`` keeps only the most recent N records
    (``limit=0`` means no cap — return everything in view). The disk tail and
    the buffer are disjoint at any instant (drain clears the buffer before the
    write completes), so combining them never double-counts.
    """
    records = _read_disk_records(get_sink().path)
    if include_buffer:
        try:
            records.extend(_parse_lines(get_sink().peek()))
        except Exception:
            log.debug("telemetry.read buffer peek failed", exc_info=True)
    if limit and len(records) > int(limit):
        records = records[-int(limit):]
    return records


async def read_recent_async(limit: int = 10_000, *,
                            include_buffer: bool = True) -> list[dict]:
    """Async ``read_recent``: the disk read runs on a thread executor so the
    event loop is never blocked by the file I/O. The buffer peek happens on the
    loop thread (the buffer is loop-thread-only by design)."""
    buf: list[dict] = []
    if include_buffer:
        try:
            buf = _parse_lines(get_sink().peek())
        except Exception:
            buf = []
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        records = await loop.run_in_executor(
            None, _read_disk_records, get_sink().path)
    except Exception:
        records = _read_disk_records(get_sink().path)
    records.extend(buf)
    if limit and len(records) > int(limit):
        records = records[-int(limit):]
    return records


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# WEG R&E difficulty bands for the skill-check rollup. Each boundary is a
# ``Difficulty`` level's target number (the band's upper bound): a check of
# difficulty ``d`` falls in the first band whose ceiling it does not exceed.
# These mirror ``engine.dice.Difficulty`` (VERY_EASY=5 … HEROIC=30); a guard
# test pins them to the live enum so a rebalance there fails loudly here rather
# than letting this rollup drift to phantom thresholds. Anything above the top
# band reads as ``Heroic+``; a non-numeric difficulty reads as ``?``.
_DIFFICULTY_BANDS = (
    (5, "Very Easy"),
    (10, "Easy"),
    (15, "Moderate"),
    (20, "Difficult"),
    (25, "Very Difficult"),
    (30, "Heroic"),
)
_BAND_ORDER = [label for _, label in _DIFFICULTY_BANDS] + ["Heroic+", "?"]


def _difficulty_band(d: Any) -> str:
    """Bucket a skill-check difficulty (target number) into its WEG band label.

    Pure + total: a non-numeric difficulty buckets to ``"?"`` so ``summarize``
    never raises on a malformed record.
    """
    try:
        di = int(d)
    except (TypeError, ValueError):
        return "?"
    for hi, label in _DIFFICULTY_BANDS:
        if di <= hi:
            return label
    return "Heroic+"


# Credit-flow funnel (``economy`` rollup → ``@balance flows``). Each of these
# event types is a distinct credit faucet/sink that the live ``@economy`` board
# (a DB snapshot of who holds what NOW) cannot trend over time. This rollup
# captures the behavioural VOLUME of credits MOVING through each system — which
# systems players actually use and how much money flows through each — the
# direct signal for tuning a system's prices / fees / payouts. Map: emitted
# event type -> the human domain label it rolls up under.
_ECONOMY_DOMAINS = {
    "vendor_txn":         "vendor",
    "commissary_txn":     "commissary",
    "gamble":             "gambling",
    "debt":               "debt",
    "gear_insurance":     "insurance",
    "housing":            "housing",
    "den":                "den",
    "medical_treatment":  "medical",
    "pc_bounty":          "bounty",
    "entertainer_perform": "entertainer",
}


def _economy_credits(et: str, ev: dict) -> int:
    """Gross (non-negative) credits that changed hands in one economy event.

    The credit-amount field name varies per producer (``price`` for a vendor
    trade, ``cost``/``refund`` for a commissary requisition, ``bet`` for a
    sabacc hand, ``paid`` for a healer treatment, ``payout`` for a performance,
    a signed ``amount`` for the debt/insurance/housing/den/bounty systems). We
    report gross THROUGHPUT, not a signed net: these emitters record only the
    ACTING player's side of a possibly two-sided transfer (a P2P sale emits one
    event), so a summed "net" would be misleading — gross volume per system is
    the honest, robust signal. Pure + total: anything unparseable reads 0.
    """
    try:
        if et == "vendor_txn":
            return abs(_as_int(ev.get("price")))
        if et == "commissary_txn":
            # Exactly one of cost (buy) / refund (sell) is present per event.
            return abs(_as_int(ev.get("cost")) or _as_int(ev.get("refund")))
        if et == "gamble":
            return abs(_as_int(ev.get("bet")))
        if et == "medical_treatment":
            return abs(_as_int(ev.get("paid")))
        if et == "entertainer_perform":
            return abs(_as_int(ev.get("payout")))
        # debt / gear_insurance / housing / den / pc_bounty carry a signed
        # ``amount`` (negative for the sink leg, positive for a refund/payout).
        return abs(_as_int(ev.get("amount")))
    except Exception:
        return 0


def summarize(events: list[dict]) -> dict:
    """Aggregate parsed telemetry events into balance-tuning rollups (pure).

    Generic envelope (``total``, per-event-type counts, time span) plus the
    domain rollups that carry the live tuning signal:
      - grind:        kill volume, payout, soft-/over-cap pressure, top mobs,
                      distinct grinders — for BASE_REWARD / DAILY_SOFT_CAP /
                      OVER_CAP_FLOOR.
      - cp_income:    CP-source mix + weekly-cap pressure (faucet) PLUS the
                      ``cp_spend`` sink (CP spent on ``train``, by skill) — for
                      the CP levers and hoard-vs-spend behaviour.
      - economy:      per-system gross credit throughput for every credit
                      faucet/sink the @economy snapshot can't trend (vendor /
                      commissary / gambling / debt / insurance / housing / den /
                      medical / bounty / entertainer) — which systems move money
                      and how much, for tuning each system's prices/fees/payouts.
      - objective:    start→complete→abandon funnel + reward, per kind — for
                      mission/bounty/smuggling tier pay.
      - chain:        tutorial-chain / questline reward-step + graduation
                      (completion) counts + credit flow, per chain_id — the NPE
                      / questline-completion health signal.
      - wild_encounter: roll→fire rate by threat band — for encounter pacing.
      - communal:     menace escalation + strike success — for cult tuning.
      - skill_check:  out-of-combat dice pass rate by skill + difficulty band
                      (catalog D — are DCs calibrated). The single funnel for
                      ALL out-of-combat checks (perform_skill_check), so this is
                      the whole-game skill-difficulty signal.
      - session:      login/logout funnel — connect→login conversion, play-time
                      distribution, transport mix, distinct players/accounts —
                      the engagement/retention signal (is idle_timeout cutting
                      sessions short? do web players stay longer? how many of a
                      day's connects ever reach the world?).

    Pure + total: never reads files, never raises, accepts a possibly-mixed
    list of dicts and ignores fields it does not recognise.
    """
    from collections import Counter

    by_type: Counter = Counter()
    first_ts = None
    last_ts = None

    grind = {"kills": 0, "credits": 0, "at_cap": 0, "over_cap": 0,
             "npcs": Counter()}
    grinders: set = set()
    # CP economy: the income FAUCET (``cp_income``: kudos/scene/passive/…) and
    # its sink (``cp_spend``: the ``train`` advancement spend, by skill). The
    # faucet was rolled up; the sink was silently dropped — so the board showed
    # only half the CP economy. Both live here now (joined offline on char_id).
    cp = {"events": 0, "cp": 0, "ticks": 0, "at_cap": 0, "by_source": Counter(),
          "spends": 0, "cp_spent": 0, "by_skill": Counter()}
    objective: dict = {}
    enc = {"rolls": 0, "fired": 0, "by_band": Counter()}
    communal = {"menace_events": 0, "tier_escalations": 0,
                "strikes": 0, "strike_success": 0}
    # Out-of-combat skill-check funnel (``skill_check``: the perform_skill_check
    # chokepoint). The whole-game DC-calibration signal — pass rate overall,
    # per difficulty band, and per skill — which otherwise appeared nowhere but
    # the raw dump despite being the highest-frequency instrumented chokepoint.
    skill = {"checks": 0, "successes": 0, "crits": 0, "fumbles": 0,
             "by_band": [], "by_skill": []}
    skill_by_band: dict = {}
    skill_by_skill: dict = {}
    skill_rollers: set = set()
    # Tutorial-chain / questline funnel. ``chain_reward`` is emitted at a
    # reward-bearing step (phase="step") and ALWAYS at graduation
    # (phase="graduation"), so per-chain ``graduations`` is the true completion
    # count and ``credits`` is the onboarding/questline credit flow. (Empty-
    # reward steps emit nothing, so ``steps`` undercounts raw step traversal —
    # it is the reward-bearing-step count, not the completion count, which is
    # ``graduations``.)
    chain = {"step_events": 0, "graduations": 0, "credits": 0,
             "items": 0, "achievements": 0, "by_chain": {}}
    # Session / engagement funnel (``emit_session``: phase login|logout). Every
    # disconnect path funnels through one chokepoint (SessionManager.remove), so
    # ``logouts`` counts connections (connects); ``reached_game`` is the
    # connect→login conversion; durations arrive on the logout event only
    # (``duration_s`` = play time, ``connected_s`` = full connect→disconnect
    # span incl. the pre-auth login screen). The richest launch retention
    # signal — how long players stay, whether they return (distinct accounts),
    # the web-vs-telnet mix — which otherwise appeared nowhere but the raw dump.
    session = {"logins": 0, "logouts": 0, "reached_game": 0,
               "avg_duration_s": 0.0, "max_duration_s": 0.0,
               "avg_connected_s": 0.0, "players": 0, "accounts": 0,
               "by_transport": Counter()}
    _dur_sum = 0.0
    _dur_n = 0
    _dur_max = 0.0
    _con_sum = 0.0
    _con_n = 0
    sess_players: set = set()
    sess_accounts: set = set()
    # Credit-flow funnel (``economy`` → @balance flows). Per-domain {events,
    # credits-gross} for every dropped credit faucet/sink (vendor/commissary/
    # gambling/debt/insurance/housing/den/medical/bounty/entertainer), plus the
    # totals. Gross throughput, not net — see ``_economy_credits``.
    economy = {"events": 0, "credits": 0, "by_domain": {}}

    for ev in events:
        if not isinstance(ev, dict):
            continue
        et = ev.get("ev")
        if et:
            by_type[et] += 1
        ts = ev.get("ts")
        if isinstance(ts, (int, float)):
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

        if et == "grind_kill":
            grind["kills"] += 1
            grind["credits"] += _as_int(ev.get("reward"))
            if ev.get("at_cap"):
                grind["at_cap"] += 1
            if ev.get("over_cap"):
                grind["over_cap"] += 1
            cid = ev.get("char_id")
            if cid is not None:
                grinders.add(cid)
            name = ev.get("npc_name")
            if name:
                grind["npcs"][name] += 1
        elif et == "cp_income":
            cp["events"] += 1
            cp["cp"] += _as_int(ev.get("cp_gained"))
            cp["ticks"] += _as_int(ev.get("ticks"))
            if ev.get("at_cap"):
                cp["at_cap"] += 1
            cp["by_source"][ev.get("source") or "?"] += 1
        elif et == "cp_spend":
            # The CP sink: ``train`` spends CP to raise a skill pip. ``cost`` is
            # CP spent (after any guild discount). Joined to the cp_income
            # faucet on char_id this completes the CP-economy picture.
            cp["spends"] += 1
            cp["cp_spent"] += _as_int(ev.get("cost"))
            sk = ev.get("skill")
            if sk:
                cp["by_skill"][str(sk)] += 1
        elif et == "objective":
            kind = ev.get("kind") or "?"
            phase = ev.get("phase") or "?"
            d = objective.setdefault(
                kind, {"start": 0, "complete": 0, "abandon": 0, "reward": 0})
            if phase in ("start", "complete", "abandon"):
                d[phase] += 1
            if phase == "complete":
                d["reward"] += _as_int(ev.get("reward"))
        elif et == "wild_encounter":
            enc["rolls"] += 1
            if ev.get("fired"):
                enc["fired"] += 1
            band = ev.get("band")
            if band is not None:
                enc["by_band"][str(band)] += 1
        elif et == "communal_menace":
            communal["menace_events"] += 1
            if ev.get("tier_changed"):
                communal["tier_escalations"] += 1
        elif et == "communal_strike":
            communal["strikes"] += 1
            if ev.get("success"):
                communal["strike_success"] += 1
        elif et == "skill_check":
            skill["checks"] += 1
            ok = bool(ev.get("success"))
            if ok:
                skill["successes"] += 1
            if ev.get("crit"):
                skill["crits"] += 1
            if ev.get("fumble"):
                skill["fumbles"] += 1
            band = _difficulty_band(ev.get("difficulty"))
            bd = skill_by_band.setdefault(band, {"n": 0, "ok": 0})
            bd["n"] += 1
            if ok:
                bd["ok"] += 1
            sname = str(ev.get("skill") or "?")
            sd = skill_by_skill.setdefault(sname, {"n": 0, "ok": 0})
            sd["n"] += 1
            if ok:
                sd["ok"] += 1
            cid = ev.get("char_id")
            if cid is not None:
                skill_rollers.add(cid)
        elif et == "chain_reward":
            phase = ev.get("phase") or "?"
            cid = str(ev.get("chain_id") or "?")
            d = chain["by_chain"].setdefault(
                cid, {"steps": 0, "graduations": 0, "credits": 0,
                      "items": 0, "achievements": 0, "label": ""})
            cr = _as_int(ev.get("credits"))
            it = _as_int(ev.get("items"))
            ach = _as_int(ev.get("achievements"))
            d["credits"] += cr
            d["items"] += it
            d["achievements"] += ach
            chain["credits"] += cr
            chain["items"] += it
            chain["achievements"] += ach
            # Only the graduation event carries a human label; keep the first.
            label = ev.get("chain_label")
            if label and not d["label"]:
                d["label"] = str(label)
            if phase == "graduation":
                d["graduations"] += 1
                chain["graduations"] += 1
            elif phase == "step":
                d["steps"] += 1
                chain["step_events"] += 1
        elif et == "session":
            phase = ev.get("phase") or "?"
            if phase == "login":
                session["logins"] += 1
            elif phase == "logout":
                session["logouts"] += 1
                if ev.get("reached_game"):
                    session["reached_game"] += 1
                dval = ev.get("duration_s")
                if isinstance(dval, (int, float)):
                    _dur_sum += dval
                    _dur_n += 1
                    if dval > _dur_max:
                        _dur_max = dval
                cval = ev.get("connected_s")
                if isinstance(cval, (int, float)):
                    _con_sum += cval
                    _con_n += 1
                # Count transport per CONNECTION (logout only). Every teardown
                # funnels through one chokepoint so each connection emits exactly
                # one logout — counting both phases would double the mix.
                tr = ev.get("transport")
                if tr:
                    session["by_transport"][str(tr)] += 1
            cid = ev.get("char_id")
            if cid is not None:
                sess_players.add(cid)
            aid = ev.get("account_id")
            if aid is not None:
                sess_accounts.add(aid)
        elif et in _ECONOMY_DOMAINS:
            dom = _ECONOMY_DOMAINS[et]
            cr = _economy_credits(et, ev)
            d = economy["by_domain"].setdefault(dom, {"events": 0, "credits": 0})
            d["events"] += 1
            d["credits"] += cr
            economy["events"] += 1
            economy["credits"] += cr

    grind["grinders"] = len(grinders)
    grind["npcs"] = grind["npcs"].most_common(8)
    cp["by_source"] = cp["by_source"].most_common()
    cp["by_skill"] = cp["by_skill"].most_common(8)
    # Economy domains ranked by gross credit throughput (the biggest credit
    # movers first). Each row is (domain, events, credits).
    economy["by_domain"] = sorted(
        ((dom, d["events"], d["credits"])
         for dom, d in economy["by_domain"].items()),
        key=lambda r: (-r[2], -r[1], r[0]))
    enc["by_band"] = dict(sorted(enc["by_band"].items()))
    session["avg_duration_s"] = (_dur_sum / _dur_n) if _dur_n else 0.0
    session["max_duration_s"] = _dur_max
    session["avg_connected_s"] = (_con_sum / _con_n) if _con_n else 0.0
    session["players"] = len(sess_players)
    session["accounts"] = len(sess_accounts)
    session["by_transport"] = session["by_transport"].most_common()

    skill["rollers"] = len(skill_rollers)
    # Difficulty bands in canonical (easy→heroic) order; skip bands with no
    # rolls. Each row is (band, checks, successes).
    skill["by_band"] = [
        (b, skill_by_band[b]["n"], skill_by_band[b]["ok"])
        for b in _BAND_ORDER if b in skill_by_band
    ]
    # Skills ranked by roll volume (the most-tuned-against first), top 12. Each
    # row is (skill, checks, successes).
    skill["by_skill"] = sorted(
        ((name, d["n"], d["ok"]) for name, d in skill_by_skill.items()),
        key=lambda r: (-r[1], r[0]))[:12]

    return {
        "total": len(events),
        "by_type": by_type.most_common(),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "grind": grind,
        "cp_income": cp,
        "objective": objective,
        "chain": chain,
        "wild_encounter": enc,
        "communal": communal,
        "skill_check": skill,
        "session": session,
        "economy": economy,
    }
