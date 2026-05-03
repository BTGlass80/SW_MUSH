# -*- coding: utf-8 -*-
"""
server/tick_handlers_progression.py — Progression-gates tick handlers.

Currently hosts two handlers:

  playtime_heartbeat_tick    — increments characters.play_time_seconds
                               for every actively-playing non-idle PC.
                               Per design §2.3, this is the foundation
                               of the 50-hour gate.

  force_sign_emit_tick       — for each post-gate active session, rolls
                               for a Force-sign emission scaled by the
                               character's predisposition. Per design
                               §2.3 / §2.4, this is what drives the
                               Hermit invitation ladder (5 signs).

Idle filter:
  A session is "idle" if it has had no input in the last
  IDLE_THRESHOLD_SECONDS. Idle sessions are skipped — they don't
  accumulate playtime AND they don't roll for signs (a player
  AFK at the prompt should not progress along the path).

Registration: see GameServer.__init__ in server/game_server.py.
"""
from __future__ import annotations

import logging

from server.tick_scheduler import TickContext

log = logging.getLogger(__name__)


# Run once a minute. The handler is registered with interval=60.
# Each call adds 60 seconds of playtime per active non-idle session.
HEARTBEAT_INCREMENT_SECONDS: int = 60

# A session is considered idle if it has had no input within this
# many seconds. Tuned slightly above the heartbeat interval so a
# session that *just* finished its 60-second window with one
# command at second 0 still gets credit for that minute.
#
# Rationale on the value: long enough that a player reading a long
# room description, composing a pose, or stepping away briefly
# doesn't get penalized; short enough that a window left open
# overnight doesn't accumulate gate progress.
IDLE_THRESHOLD_SECONDS: int = 300  # 5 minutes


async def playtime_heartbeat_tick(ctx: TickContext) -> None:
    """Tick every 60s; bump play_time_seconds for active non-idle PCs.

    Iterates the session manager. For each session that is:
      - in-game (has a character attached and is post-login)
      - not idle (has had input within IDLE_THRESHOLD_SECONDS)

    we increment that character's play_time_seconds by 60. The DB
    write is delegated to ``engine.jedi_gating.accumulate_play_time``
    so the rules around clamping and idempotence live there, not
    here.

    Failure mode: if the schema doesn't yet have play_time_seconds
    (i.e. running PG.3 code against a pre-PG.1 DB), the underlying
    UPDATE will raise. That error is caught by the TickScheduler's
    per-handler try/except wrapper and logged at exception level —
    the right behavior, because it's a configuration issue, not a
    transient one.
    """
    from engine.jedi_gating import accumulate_play_time

    # Snapshot the session list — sessions may come and go mid-tick
    # but we just want a stable view for this iteration.
    sessions = ctx.session_mgr.all
    if not sessions:
        return

    bumped = 0
    skipped_idle = 0
    skipped_no_char = 0

    for s in sessions:
        # Filter: must be in-game with an attached character.
        if not s.is_in_game or not s.character:
            skipped_no_char += 1
            continue

        # Filter: idle sessions don't accumulate.
        if s.is_idle_for(IDLE_THRESHOLD_SECONDS):
            skipped_idle += 1
            continue

        char_id = s.character.get("id")
        if not char_id:
            skipped_no_char += 1
            continue

        try:
            new_total = await accumulate_play_time(
                ctx.db, char_id, HEARTBEAT_INCREMENT_SECONDS,
            )
            bumped += 1

            # Maintain in-memory cache consistency. The Session
            # holds a character dict cached at login time; if we
            # don't update it, downstream code that reads
            # s.character['play_time_seconds'] sees a stale value
            # for the rest of the connection. Cheap to keep in
            # sync — just bump the field if it's there.
            if "play_time_seconds" in s.character:
                s.character["play_time_seconds"] = new_total
        except Exception:
            # Per TickScheduler protocol, raising would break this
            # handler's run for the whole tick but not block other
            # handlers. We swallow per-character failures here so
            # one bad row doesn't strand the whole heartbeat.
            log.warning(
                "playtime_heartbeat_tick: accumulate failed for char_id=%s",
                char_id, exc_info=True,
            )

    if bumped or skipped_idle:
        # DEBUG-level summary — useful for confirming the heartbeat
        # is alive without spamming production logs.
        log.debug(
            "playtime_heartbeat: bumped=%d idle=%d no_char=%d",
            bumped, skipped_idle, skipped_no_char,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Force-sign emission tick (PG.3.gates.b)
# ─────────────────────────────────────────────────────────────────────────────


async def force_sign_emit_tick(ctx: TickContext) -> None:
    """Tick every 60s; roll for a Force-sign for each gate-cleared PC.

    Per progression_gates_and_consequences_design_v1.md §2.3 / §2.4:

      - Pre-gate PCs (under 50 hours) never roll. Predisposition
        only affects flavor density during this phase, which is the
        Director's job, not this handler.

      - Post-gate PCs roll once per minute. Probability scales by
        predisposition (see engine.force_signs).

      - Once a PC accumulates 5 signs, the invitation threshold is
        hit and ``maybe_emit_force_sign`` returns the
        ``invitation_unlocked`` sentinel. Handling that sentinel
        (firing the Hermit NPC dialog) is the future Village quest
        engine's job; this handler just logs the milestone.

    Idle filter is the same as ``playtime_heartbeat_tick``: a PC
    AFK at the prompt should not advance along the path.
    """
    from engine.force_signs import maybe_emit_force_sign, SignOutcome

    sessions = ctx.session_mgr.all
    if not sessions:
        return

    rolled = 0
    emitted = 0
    invitations = 0

    for s in sessions:
        if not s.is_in_game or not s.character:
            continue
        if s.is_idle_for(IDLE_THRESHOLD_SECONDS):
            continue

        char_id = s.character.get("id")
        if not char_id:
            continue

        # Pass the cached character dict as the snapshot; it has
        # play_time_seconds (kept fresh by playtime_heartbeat_tick),
        # force_predisposition (set once at chargen), and
        # force_signs_accumulated (kept fresh by this handler when
        # signs fire). Avoids a per-tick DB SELECT.
        try:
            outcome = await maybe_emit_force_sign(
                ctx.db, char_id, char=s.character,
            )
        except Exception:
            log.warning(
                "force_sign_emit_tick: roll failed for char_id=%s",
                char_id, exc_info=True,
            )
            continue

        rolled += 1
        if outcome in (SignOutcome.SIGN_EMITTED,
                       SignOutcome.SIGN_THRESHOLD_HIT):
            emitted += 1
            # Maintain in-memory cache consistency. Read back the
            # new count so the cached dict reflects the increment.
            try:
                rows = await ctx.db._db.execute_fetchall(
                    "SELECT force_signs_accumulated FROM characters "
                    "WHERE id = ?", (char_id,),
                )
                if rows:
                    s.character["force_signs_accumulated"] = (
                        rows[0]["force_signs_accumulated"]
                    )
            except Exception:
                # Cache update failure is non-fatal; the next read
                # path will refresh from DB.
                pass

        if outcome == SignOutcome.SIGN_THRESHOLD_HIT:
            invitations += 1
            log.info(
                "[force_signs] char_id=%d hit invitation threshold "
                "(5 signs); Village invitation now unlocked", char_id,
            )

    if rolled or emitted:
        log.debug(
            "force_sign_emit: rolled=%d emitted=%d invitations=%d",
            rolled, emitted, invitations,
        )
