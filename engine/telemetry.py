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

# Bounded tail read for the offline read-side (``read_recent`` / the @balance
# admin view). The sink is append-only and can grow large over a launch; an
# admin asking for a balance summary should never read an unbounded file, so we
# seek to the last N bytes and parse only that window. ~4 MiB ≈ 25k events.
_MAX_READ_BYTES = 4 * 1024 * 1024


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


def summarize(events: list[dict]) -> dict:
    """Aggregate parsed telemetry events into balance-tuning rollups (pure).

    Generic envelope (``total``, per-event-type counts, time span) plus the
    domain rollups that carry the live tuning signal:
      - grind:        kill volume, payout, soft-/over-cap pressure, top mobs,
                      distinct grinders — for BASE_REWARD / DAILY_SOFT_CAP /
                      OVER_CAP_FLOOR.
      - cp_income:    CP-source mix + weekly-cap pressure — for the CP levers.
      - objective:    start→complete→abandon funnel + reward, per kind — for
                      mission/bounty/smuggling tier pay.
      - wild_encounter: roll→fire rate by threat band — for encounter pacing.
      - communal:     menace escalation + strike success — for cult tuning.

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
    cp = {"events": 0, "cp": 0, "ticks": 0, "at_cap": 0, "by_source": Counter()}
    objective: dict = {}
    enc = {"rolls": 0, "fired": 0, "by_band": Counter()}
    communal = {"menace_events": 0, "tier_escalations": 0,
                "strikes": 0, "strike_success": 0}

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

    grind["grinders"] = len(grinders)
    grind["npcs"] = grind["npcs"].most_common(8)
    cp["by_source"] = cp["by_source"].most_common()
    enc["by_band"] = dict(sorted(enc["by_band"].items()))

    return {
        "total": len(events),
        "by_type": by_type.most_common(),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "grind": grind,
        "cp_income": cp,
        "objective": objective,
        "wild_encounter": enc,
        "communal": communal,
    }
