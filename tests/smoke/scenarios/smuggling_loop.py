# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/smuggling_loop.py — Smuggling job loop smoke (SL1-SL4).

Coverage:
  SL1: `+smugjobs` in a board-eligible room (name contains a board keyword)
       renders the board header without crash; job ids appear in the listing.
  SL2: `smugaccept <id>` confirms job accepted; `+smugjob` then shows
       "ACTIVE SMUGGLING RUN" with cargo details.
  SL3: `+smuggle/deliver` from a character who HAS an active job but is NOT
       aboard any ship returns the "aboard a docked ship" refusal.
  SL4: `+smugjobs` from a room whose name contains NONE of the board
       keywords returns the "near a cantina" refusal.

Bug FIXED (2026-06-12): `_in_board_room` (parser/smuggling_commands.py) was
reading `ctx.session.current_room` — an attribute that was **never assigned**
anywhere in server/, parser/, or engine/ (every other room-gated command
reads `char["room_id"]`). Accessing it raised AttributeError, which the
dispatch wrapper caught and rendered as "An error occurred...". The fix rewrites
`_in_board_room` as `async def` and reads the room from the DB via
`ctx.db.get_room(ctx.session.character["room_id"])`, matching the established
idiom (e.g. builtin_commands.py:180). All four arms are now live passing tests.

Board singleton is reset before each scenario (`_reset_board`) to avoid
cross-scenario pollution under the class-scoped harness.
"""
from __future__ import annotations

import time


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_board() -> None:
    """Wipe the in-memory board singleton so each scenario starts clean."""
    import engine.smuggling as _es
    _es._board = None


def _inject_active_job(char_id: int, board) -> "engine.smuggling.SmugglingJob":
    """Build a GREY_MARKET job (tier 0, 0% patrol) and inject it into the
    board as ACCEPTED by *char_id*.  Returns the job.

    Grey market is the safest choice for the deliver-refusal test: 0% patrol,
    small fine — the exact values don't matter since SL3 never reaches the
    patrol check or credit delta.
    """
    from engine.smuggling import (
        SmugglingJob, CargoTier, JobStatus,
        _generate_id, TIER_PAY_RANGE, FINE_FRACTION,
    )
    import random
    lo, hi = TIER_PAY_RANGE[CargoTier.GREY_MARKET]
    reward = random.randint(lo, hi)
    now = time.time()
    job = SmugglingJob(
        id=_generate_id(),
        tier=CargoTier.GREY_MARKET,
        cargo_type="smoke-test medical supplies",
        contact_name="a smoke-test Rodian",
        dropoff_name="a smoke-test fence at Bay 94",
        reward=reward,
        fine=int(reward * FINE_FRACTION),
        patrol_chance=0.0,          # no patrol risk
        status=JobStatus.ACCEPTED,
        accepted_by=char_id,
        destination_planet=None,    # local run, no planet check
        created_at=now,
        expires_at=now + 7200,
    )
    board._jobs[job.id] = job
    board._loaded = True            # prevent ensure_loaded clobbering
    return job


# ── SL1 — board renders in a board-eligible room ─────────────────────────────

async def sl1_board_renders_in_cantina(h):
    """SL1 — `+smugjobs` renders the board without crash when the player is in
    a board-eligible room.

    Asserts:
      - No traceback / error-occurred in output.
      - "smuggling" header visible.
      - At least one job id ("smug-") present.
    """
    _reset_board()
    # Room name with a board keyword ("cantina") in the clone_wars auto-build.
    s = await h.login_as("SL1BoardRender", room_id=3)

    out = await h.cmd(s, "+smugjobs")
    low = out.lower()

    assert out and out.strip(), "SL1: +smugjobs produced no output"
    assert "traceback" not in low, f"SL1: traceback in +smugjobs output: {out[:500]!r}"
    assert "error occurred" not in low, (
        f"SL1: 'error occurred' in +smugjobs output — the current_room gate "
        f"bug (parser/smuggling_commands.py:38). Output: {out[:500]!r}"
    )
    assert "smuggling" in low, (
        f"SL1: board header 'smuggling' not in output: {out[:400]!r}"
    )
    assert "smug-" in out, (
        f"SL1: no job id (smug-...) on rendered board: {out[:600]!r}"
    )


# ── SL2 — accept → active cargo ───────────────────────────────────────────────

async def sl2_accept_and_view_active_run(h):
    """SL2 — `smugaccept <id>` marks a job accepted; `+smugjob` shows the
    active run.

    Asserts:
      - `smugaccept <id>` confirms acceptance + reward.
      - `+smugjob` renders "ACTIVE SMUGGLING RUN".
      - Board state: job ACCEPTED, accepted_by == char_id.
    """
    _reset_board()
    s = await h.login_as("SL2AcceptRun", room_id=3)
    char_id = s.character["id"]

    out_board = await h.cmd(s, "+smugjobs")
    low_board = out_board.lower()
    assert "traceback" not in low_board, f"SL2: traceback in +smugjobs: {out_board[:500]!r}"
    assert "error occurred" not in low_board, (
        f"SL2: error in +smugjobs (current_room gate bug): {out_board[:500]!r}"
    )

    from engine.smuggling import get_smuggling_board, JobStatus
    board = get_smuggling_board()
    available = board.available_jobs()
    assert available, (
        "SL2: board has no available jobs after +smugjobs (refresh failed?). "
        f"Board jobs: {list(board._jobs.keys())!r}"
    )
    job_id = available[0].id

    out_accept = await h.cmd(s, f"smugaccept {job_id}")
    low_accept = out_accept.lower()
    assert "traceback" not in low_accept, f"SL2: traceback in smugaccept: {out_accept[:500]!r}"
    assert "error occurred" not in low_accept, f"SL2: error in smugaccept: {out_accept[:500]!r}"
    assert "accepted" in low_accept, (
        f"SL2: smugaccept did not confirm acceptance: {out_accept[:500]!r}"
    )
    assert "reward" in low_accept, (
        f"SL2: smugaccept output missing reward info: {out_accept[:500]!r}"
    )

    out_job = await h.cmd(s, "+smugjob")
    low_job = out_job.lower()
    assert "traceback" not in low_job, f"SL2: traceback in +smugjob: {out_job[:500]!r}"
    assert "active smuggling run" in low_job, (
        f"SL2: +smugjob did not render 'ACTIVE SMUGGLING RUN': {out_job[:500]!r}"
    )
    assert job_id in out_job, (
        f"SL2: accepted job id {job_id!r} not visible in +smugjob: {out_job[:500]!r}"
    )

    job_in_board = board._jobs.get(job_id)
    assert job_in_board is not None, f"SL2: job {job_id!r} disappeared after accept."
    assert job_in_board.status == JobStatus.ACCEPTED, (
        f"SL2: job {job_id!r} not ACCEPTED: status={job_in_board.status!r}"
    )
    assert job_in_board.accepted_by == char_id, (
        f"SL2: job {job_id!r} accepted_by={job_in_board.accepted_by!r}, expected {char_id!r}"
    )


# ── SL3 — deliver refusal when not aboard a docked ship (REAL PASS) ───────────

async def sl3_deliver_refusal_not_docked(h):
    """SL3 — `+smuggle/deliver` refuses when the player has an active job but is
    NOT aboard any ship.

    Independent of the `current_room` bug: deliver gates on an active job
    + a docked ship, never on `_in_board_room`. This is a real passing test.

    Strategy: inject a pre-accepted job directly into the board, then issue
    `+smuggle/deliver` from a character who owns no ship → `_get_player_ship`
    None → "aboard a docked ship" refusal. Credits unchanged. (The run-on
    `smugdeliver` was deleted in command-syntax rework Drop 2.)
    """
    _reset_board()
    s = await h.login_as("SL3DeliverRefuse", room_id=3, credits=500)
    char_id = s.character["id"]

    from engine.smuggling import get_smuggling_board
    board = get_smuggling_board()
    _inject_active_job(char_id, board)
    assert board.get_active_job(char_id) is not None, (
        f"SL3: pre-condition failed — injected job not found for char {char_id}"
    )

    credits_before = await h.get_credits(char_id)

    out = await h.cmd(s, "+smuggle/deliver")
    low = out.lower()

    assert "traceback" not in low, f"SL3: traceback in +smuggle/deliver: {out[:500]!r}"
    assert "error occurred" not in low, f"SL3: error in +smuggle/deliver: {out[:500]!r}"
    assert out and out.strip(), "SL3: +smuggle/deliver produced no output (silent no-op)"
    assert "docked" in low, (
        f"SL3: expected 'docked' refusal in +smuggle/deliver output, got: {out[:400]!r}"
    )

    credits_after = await h.get_credits(char_id)
    assert credits_after == credits_before, (
        f"SL3: credits changed on refused delivery! before={credits_before}, after={credits_after}"
    )


# ── SL4 — board refuses from a non-board room ─────────────────────────────────

async def sl4_board_refused_outside_eligible_room(h):
    """SL4 — `+smugjobs` refuses with the "near a cantina" message when the
    player is in a room whose name has none of the board keywords.

    Room 2 ("Mos Eisley Street") has no board keyword → proper refusal.

    Asserts:
      - No traceback / error-occurred.
      - Output contains the cantina/docking-bay/underground refusal.
      - No board job id rendered.
    """
    _reset_board()
    # Room 2 ("Mos Eisley Street") — name has none of the board keywords.
    # (Room 1 "Landing Pad - Mos Eisley Spaceport" contains "spaceport" and
    # would pass the gate, so it is unusable for the negative arm.)
    s = await h.login_as("SL4GateRefuse", room_id=2)

    out = await h.cmd(s, "+smugjobs")
    low = out.lower()

    assert "traceback" not in low, f"SL4: traceback in +smugjobs: {out[:500]!r}"
    assert "error occurred" not in low, (
        f"SL4: error in +smugjobs (current_room gate bug): {out[:500]!r}"
    )
    assert out and out.strip(), "SL4: +smugjobs from non-board room produced no output"
    assert "cantina" in low or "docking bay" in low or "underground" in low, (
        f"SL4: expected cantina/docking-bay/underground refusal; got: {out[:400]!r}"
    )
    assert "smug-" not in out, (
        f"SL4: board rendered a job id despite a non-board room: {out[:400]!r}"
    )
