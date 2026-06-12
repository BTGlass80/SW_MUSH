# -*- coding: utf-8 -*-
"""
server/tick_handlers_progression.py — Progression-gates tick handlers.

Currently hosts three handlers:

  playtime_heartbeat_tick    — increments characters.play_time_seconds
                               for every actively-playing non-idle PC.
                               Per design §2.3, this is the foundation
                               of the 50-hour gate.

  force_sign_emit_tick       — for each post-gate active session, rolls
                               for a Force-sign emission scaled by the
                               character's predisposition. Per design
                               §2.3 / §2.4, this is what drives the
                               Hermit invitation ladder (5 signs).

  wow_passive_decay_tick     — hourly scan of all Jedi PCs for passive
                               Weight-of-War decay. Per WoW design §5.1
                               and WoW.3b scope (May 24 2026): -1 Weight
                               per 7 real-time days of no Weight events,
                               skipping retreat-active characters.

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


# ── PG.2 session 2 (May 21 2026): PC bounty expiry tick ─────────────────


async def pc_bounty_expiry_tick(ctx: "TickContext") -> None:
    """Hourly tick: auto-expire active bounties past their 30-day
    window and revert claimed bounties whose 7-day BH claim timer
    has elapsed.

    Per progression_gates_and_consequences_design_v1.md §4.3:
      - Active → Expired (30 days unclaimed): escrow returns to
        contributors minus the 10% posting fee (already sunk).
      - Claimed → Active (7 days unfulfilled): contract reverts
        to active for another BH to claim.

    Delegates the actual work to
    ``parser.pc_bounty_commands.run_pc_bounty_expiry_tick`` so the
    bounty business logic lives next to the rest of the bounty
    module. The tick handler is the thin scheduler hook.

    Failure-tolerant: any uncaught exception is logged and
    swallowed. The next tick will retry.
    """
    try:
        from parser.pc_bounty_commands import (
            run_pc_bounty_expiry_tick,
        )
        summary = await run_pc_bounty_expiry_tick(ctx.db)
        if summary.get("expired") or summary.get("reverted"):
            log.info(
                "[pc_bounty_expiry] expired=%d reverted=%d "
                "refunded_total=%d",
                summary["expired"], summary["reverted"],
                summary["refunded_total"],
            )
    except Exception:
        log.warning(
            "[pc_bounty_expiry] tick handler raised",
            exc_info=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Weight of War passive decay tick (WoW.3b, May 24 2026)
# ─────────────────────────────────────────────────────────────────────────────


async def wow_passive_decay_tick(ctx: "TickContext") -> None:
    """Hourly tick: apply passive Weight decay to eligible Jedi PCs.

    Per weight_of_war_design_v1.md §5.1 and the WoW.3b scope
    decision (May 24 2026): every Jedi PC whose last Weight
    event (accrual or decay) is at least 7 real-time days old
    gets -1 Weight, with the standard substrate floor (0). This
    is the "idle decay" — the slow shrinkage that happens
    during peacetime arcs.

    Delegates to ``engine.weight_of_war.run_passive_decay_tick``
    so the business logic lives next to the rest of the WoW
    substrate. This handler is the thin scheduler hook per
    architecture v45 §4.5.

    Cadence: every 3600 ticks (1 hour). The 7-day eligibility
    check means hourly granularity is plenty — a server restart
    on day-7 won't miss anyone's decay by more than an hour.
    Offset chosen to spread server load.

    Failure-tolerant: any uncaught exception is logged and
    swallowed. The next tick will retry.
    """
    try:
        from engine.weight_of_war import run_passive_decay_tick
        summary = await run_passive_decay_tick(ctx.db)
        if summary.get("decayed") or summary.get("errors"):
            log.debug(
                "[wow_passive_decay] tick=%d scanned=%d "
                "decayed=%d errors=%d",
                ctx.tick_count,
                summary["scanned"], summary["decayed"],
                summary["errors"],
            )
    except Exception:
        log.warning(
            "[wow_passive_decay] tick handler raised",
            exc_info=True,
        )


# ── Drop 4b (hunter.1): roaming Dark-Side bounty hunter tick ────────────────


async def dsp_hunter_tick(ctx: "TickContext") -> None:
    """Advance every active Dark-Side hunter pursuit by one step.

    Per the III.3 persistent-threat design + the locked hunter decisions:

      - Every character at/over the DSP wanted threshold has a named, non-canon
        hunter on their trail. Each tick the hunter *closes in* by a step keyed
        to the quarry's DSP tier (deeper fall → faster hunt). The pursuit is the
        only persistent state; the wanted flag itself stays derived from
        dark_side_points.

      - When a pursuit enters a new stage (tracking → closing → imminent →
        at_heels), the hunted character — if online and in-game — gets a single
        escalating warning. ``last_notified_stage`` prevents repeats, so the
        held "at your heels" climax doesn't spam.

      - A character who **atones** (drops back under the threshold) has their
        pursuit cleared — "the trail goes cold" — the intended escape hatch.

    Prestige-domain, faction-agnostic, deterministic, era/Q1-clean. The live
    fightable-hunter climax + reward-on-defeat loop lands in hunter.2 (the pure
    spawn/reward functions are documented as that drop's seam).

    Cadence: registered at interval≈120 ticks (~2 min) so the dread builds over
    a real-time window rather than instantly. Failure-tolerant: the whole body
    and each per-character step are guarded; a bad row never aborts the rest.
    """
    try:
        from engine.bounty_board import DSP_BOUNTY_THRESHOLD
        from engine import dsp_hunter as H
    except Exception:
        log.warning("[dsp_hunter] module import failed", exc_info=True)
        return

    try:
        wanted = await ctx.db.get_dsp_wanted_characters(DSP_BOUNTY_THRESHOLD)
    except Exception:
        log.warning("[dsp_hunter] wanted query failed", exc_info=True)
        return

    # Map of in-game character id -> session (for warning delivery).
    online: dict = {}
    try:
        for s in ctx.session_mgr.all:
            if s.is_in_game and s.character:
                cid = s.character.get("id")
                if cid is not None:
                    online[cid] = s
    except Exception:
        log.debug("[dsp_hunter] session enumeration failed", exc_info=True)

    wanted_ids = set()
    advanced = 0
    warned = 0

    for w in (wanted or []):
        try:
            cid = w.get("id")
            if cid is None:
                continue
            wanted_ids.add(cid)
            dsp = w.get("dark_side_points", 0)

            row = await ctx.db.get_dsp_pursuit(cid)
            hunter = (row or {}).get("hunter_name") or H.hunter_for(cid)
            progress = (row or {}).get("progress", 0)
            last_notified = (row or {}).get("last_notified_stage", "") or ""

            new_progress = H.advance_progress(progress, dsp)
            new_stage = H.pursuit_stage(new_progress)

            sess = online.get(cid)
            stage_changed = (new_stage != last_notified)
            if stage_changed and sess is not None:
                line = H.warning_for_stage(new_stage, hunter)
                if line:
                    try:
                        await sess.send_line(line)
                        warned += 1
                    except Exception:
                        log.debug("[dsp_hunter] warn send failed for %s", cid,
                                  exc_info=True)
                # Mark this stage as delivered so we don't repeat it.
                await ctx.db.upsert_dsp_pursuit(
                    cid, hunter, new_progress, new_stage,
                    last_notified_stage=new_stage)
            else:
                # Advance silently; leave last_notified_stage intact (so an
                # offline quarry still gets warned for the current stage once
                # they log back in).
                await ctx.db.upsert_dsp_pursuit(
                    cid, hunter, new_progress, new_stage)

            # ── hunter.2: live-spawn climax + escape reconcile ──────────────
            # At `at_heels`, an online quarry gets a real, fightable hunter
            # spawned into their room (idempotent). If a hunter was previously
            # spawned but the quarry slipped it, despawn and reset the dread to
            # `imminent` so it rebuilds toward another climax.
            try:
                from engine import dsp_hunter_runtime as HR
                prev_spawn = (row or {}).get("spawned_npc_id")
                if new_stage == H.STAGE_AT_HEELS and sess is not None:
                    await HR.spawn_hunter(
                        ctx.db, ctx.session_mgr, sess.character, dsp)
                elif prev_spawn:
                    cur_npc = await ctx.db.get_npc(prev_spawn)
                    quarry_room = (sess.character.get("room_id")
                                   if sess is not None else None)
                    if cur_npc is None:
                        # Hunter gone (defeated/removed) — drop the stale ref.
                        await ctx.db.set_dsp_pursuit_spawn(cid, None)
                    elif (quarry_room is not None
                          and cur_npc.get("room_id") != quarry_room):
                        await HR.despawn_hunter(
                            ctx.db, prev_spawn, quarry_id=cid,
                            session_mgr=ctx.session_mgr,
                            room_id=cur_npc.get("room_id"),
                            line=H.collected_line(hunter))
                        await ctx.db.upsert_dsp_pursuit(
                            cid, hunter, H._IMMINENT_AT, H.STAGE_IMMINENT)
            except Exception:
                log.debug("[dsp_hunter] spawn/reconcile failed for %s", cid,
                          exc_info=True)
            advanced += 1
        except Exception:
            log.warning("[dsp_hunter] pursuit advance failed for %r",
                        w.get("id") if isinstance(w, dict) else w, exc_info=True)

    # Clear pursuits for anyone no longer wanted (they atoned).
    cleared = 0
    try:
        for p in await ctx.db.get_all_dsp_pursuits():
            pid = p.get("char_id")
            if pid is None or pid in wanted_ids:
                continue
            try:
                # hunter.2: if a live hunter was spawned, remove it too.
                spawned = p.get("spawned_npc_id")
                if spawned:
                    try:
                        from engine import dsp_hunter_runtime as HR
                        await HR.despawn_hunter(
                            ctx.db, spawned, quarry_id=pid,
                            session_mgr=ctx.session_mgr)
                    except Exception:
                        log.debug("[dsp_hunter] atone-despawn failed for %s",
                                  pid, exc_info=True)
                await ctx.db.clear_dsp_pursuit(pid)
                cleared += 1
                sess = online.get(pid)
                if sess is not None:
                    await sess.send_line(
                        H.trail_cold_line(p.get("hunter_name") or ""))
            except Exception:
                log.debug("[dsp_hunter] clear failed for %s", pid, exc_info=True)
    except Exception:
        log.warning("[dsp_hunter] pursuit sweep failed", exc_info=True)

    if advanced or warned or cleared:
        log.debug("[dsp_hunter] tick=%d advanced=%d warned=%d cleared=%d",
                  ctx.tick_count, advanced, warned, cleared)


async def communal_objective_tick(ctx: "TickContext") -> None:
    """Drive the dark-side cult communal objective (design III.3, the rally villain).

    Counterpart to dsp_hunter_tick. Where that closes a per-PC hunt, this runs the
    COMMUNAL beat: each cadence it (1) posts a fresh uprising when none is active
    and the repost cooldown has elapsed, and (2) escalates the active uprising's
    menace and resolves win/lose — paying Republic rep + a III.2 status flag to
    contributors on a win (prestige-domain; no credits).

    All work lives in engine/communal_objective_runtime (IO) over the pure
    engine/communal_objective state machine. Best-effort: a failure logs and the
    next cadence retries; it never aborts the tick.

    Cadence: registered at interval≈120 ticks (~2 min), matching the hunter, so the
    menace builds over a real-time window rather than instantly.
    """
    try:
        import engine.communal_objective_runtime as COR
    except Exception:
        log.warning("[communal_obj] runtime import failed", exc_info=True)
        return

    try:
        posted = await COR.maybe_post(ctx.db, ctx.session_mgr)
        if posted is None:
            await COR.advance_and_resolve(ctx.db, ctx.session_mgr)
    except Exception:
        log.warning("[communal_obj] tick body failed", exc_info=True)
