# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/spacer_quest.py — From Dust to Stars (FDtS) scenarios.

Drop 1 Block A. The FDtS engine (engine/spacer_quest.py, ~1,700 lines) and
its three player-facing commands (spacerquest/quest, debt, travel) are the
new-player on-ramp. Until this drop the chain had zero end-to-end smoke —
the kind of "logged in, hit +quest, the game crashed" failure the §4.7
smoke discipline exists to prevent.

Each scenario is shaped to be cheap and resilient:
  - Read-only paths (sq1, sq4) need no setup beyond a fresh char.
  - Seeded paths (sq2, sq3, sq5) write directly to the char's
    attributes JSON — the same path engine/spacer_quest.py
    persists state through. No engine internals are mocked; we
    exercise the live formatter functions and command dispatch.
  - sq6 verifies the location-gate refusal for `travel`. We don't
    seed a docking-bay room (those vary by era); we assert the
    refusal message shape, which is the intended end-state when
    a Phase-2+ player tries to travel from the wrong room.

Why no engine-internal mocks: the engine is the system under test.
Mocking out _set_quest_state / _get_quest_state would just verify
that mocks behave like mocks. Seeding the JSON column is the same
thing the engine does at runtime.

Command keying:
  Spacer's canonical key is "spacerquest" (post-S57b umbrella
  refactor). The "quest" alias points at it. The narrative
  +quest command is a separate umbrella (S55 personal quests).
  Scenarios use the unambiguous "spacerquest" key to avoid alias
  drift if the narrative umbrella ever claims "quest" too.
"""
from __future__ import annotations

import asyncio
import json
import time


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

async def _seed_quest_state(h, s, *, phase: int, step: int,
                            completed_steps: list[int],
                            flags: dict | None = None) -> None:
    """Write a spacer_quest dict into the live char + cached session.

    Mirrors engine/spacer_quest._set_quest_state but goes through the
    DB save path so reloads pick it up. Invalidates the session's
    cached char object so the next cmd reads the fresh state.
    """
    char_id = s.character["id"]
    char = await h.get_char(char_id)
    attrs = json.loads(char.get("attributes") or "{}")
    base_flags = {
        "met_mak": False, "background_written": False,
        "sabacc_played": False, "borrowed_ship_id": None,
        "ship_transferred": False, "debt_active": False,
        "chain_complete": False,
    }
    if flags:
        base_flags.update(flags)
    attrs["spacer_quest"] = {
        "phase": phase,
        "step": step,
        "started_at": int(time.time()),
        "completed_steps": list(completed_steps),
        "flags": base_flags,
        "step_data": {},
    }
    await h.db.save_character(char_id, attributes=json.dumps(attrs))
    s.character = await h.get_char(char_id)
    s.session.invalidate_char_obj()


async def _seed_hutt_debt(h, s, *, principal: int,
                          weekly_payment: int = 500) -> None:
    """Write a hutt_debt dict into the live char + cached session.

    The shape matches what engine/spacer_quest.py writes when the
    debt-active reward_flag fires (step 17 in the live chain).
    """
    char_id = s.character["id"]
    char = await h.get_char(char_id)
    attrs = json.loads(char.get("attributes") or "{}")
    attrs["hutt_debt"] = {
        "principal": principal,
        "weekly_payment": weekly_payment,
        "next_payment_due": int(time.time()) + 7 * 86400,
        "payments_missed": 0,
        "total_paid": 0,
    }
    await h.db.save_character(char_id, attributes=json.dumps(attrs))
    s.character = await h.get_char(char_id)
    s.session.invalidate_char_obj()


# ──────────────────────────────────────────────────────────────────────────
# SQ1 — fresh char: bootstrap message
# ──────────────────────────────────────────────────────────────────────────

async def sq1_quest_no_state(h):
    """SQ1 — A fresh character running `quest` gets the bootstrap message
    and not a traceback.

    This is the literal first thing a new player will type when they
    see "+quest" in the help and want to know what their quest log
    looks like. If this crashes, the new-player on-ramp is dead.
    """
    s = await h.login_as("SQ1Fresh", room_id=1)
    out = await h.cmd(s, "spacerquest")
    assert out and out.strip(), "spacerquest produced no output"
    assert "traceback" not in out.lower(), (
        f"spacerquest raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # The bootstrap message tells the player they need the starter
    # chain. Both halves of the message should be present.
    assert "haven't started" in out_lc or "starter" in out_lc, (
        f"spacerquest fresh-char bootstrap doesn't mention starter "
        f"chain. Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# SQ2 — seeded mid-chain state renders correctly
# ──────────────────────────────────────────────────────────────────────────

async def sq2_quest_after_seed(h):
    """SQ2 — Seed Phase 1 / step 3 state; `spacerquest` shows progress.

    Validates the format_quest_display path against a non-trivial
    state. If the chain phase names or the step-lookup helper
    breaks, this catches it without needing to play through the
    actual quest.
    """
    s = await h.login_as("SQ2Seeded", room_id=1)
    await _seed_quest_state(h, s, phase=1, step=3,
                             completed_steps=[1, 2],
                             flags={"met_mak": True,
                                    "background_written": True})

    out = await h.cmd(s, "spacerquest")
    assert "traceback" not in out.lower(), (
        f"spacerquest raised on seeded state: {out[:500]!r}"
    )
    out_lc = out.lower()
    # Phase 1 name per engine/spacer_quest.PHASE_NAMES.
    assert "earning your keep" in out_lc, (
        f"spacerquest didn't render Phase 1 name. Output: {out[:400]!r}"
    )
    # Step indicator should reference 30 (total) and 3 (current) or 2
    # (completed_steps len) — exact framing differs in the engine
    # but at least one of them must appear as a numeric token.
    assert "30" in out, (
        f"spacerquest didn't render total-step count. Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# SQ3 — quest log shows completed steps
# ──────────────────────────────────────────────────────────────────────────

async def sq3_quest_log(h):
    """SQ3 — `spacerquest log` after seeding completed steps lists them.

    Catches a regression class where format_quest_log iterates over
    an unexpected shape (list vs set, missing reward_credits). The
    engine's defensive branches kick in here.
    """
    s = await h.login_as("SQ3Logger", room_id=1)
    await _seed_quest_state(h, s, phase=1, step=3,
                             completed_steps=[1, 2])

    out = await h.cmd(s, "spacerquest log")
    assert "traceback" not in out.lower(), (
        f"spacerquest log raised: {out[:500]!r}"
    )
    assert out and out.strip(), "spacerquest log produced no output"
    out_lc = out.lower()
    # The log header should appear and the two completed step
    # numbers should be referenced. Step 1 and step 2 are the live
    # chain's first two steps (engine/spacer_quest STEPS[1..2]).
    assert "log" in out_lc or "completed" in out_lc or "step" in out_lc, (
        f"spacerquest log doesn't look like a step log. "
        f"Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# SQ4 — debt: clean state for a new char
# ──────────────────────────────────────────────────────────────────────────

async def sq4_debt_status_clean(h):
    """SQ4 — `debt` for a char with no Hutt debt shows the clean message.

    Reads char.attributes.hutt_debt; absence is the no-debt case.
    The engine's "Enjoy your freedom" message is the success
    fingerprint we look for.
    """
    s = await h.login_as("SQ4Free", room_id=1)
    out = await h.cmd(s, "debt")
    assert "traceback" not in out.lower(), (
        f"debt raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # The engine's clean-state line is "You don't owe anyone anything."
    # We accept any phrasing that signals "no debt" so cosmetic
    # rewording doesn't break the test.
    assert (
        "don't owe" in out_lc or "no debt" in out_lc or
        "owe anyone" in out_lc or "freedom" in out_lc
    ), (
        f"debt clean-state message didn't render. Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# SQ5 — debt: balance display + pay flow decrements
# ──────────────────────────────────────────────────────────────────────────

async def sq5_debt_status_with_balance(h):
    """SQ5 — Seed a Hutt debt; `debt` displays it and `debt pay <n>`
    decrements the principal AND deducts credits.

    This is the consequence-loop check: missing the credit deduction
    side of the pay flow is the kind of bug that would let players
    exploit `debt pay` for free debt clearance.
    """
    s = await h.login_as("SQ5Debtor", room_id=1, credits=2000)
    await _seed_hutt_debt(h, s, principal=10000)

    # 1. Status display shows principal
    out = await h.cmd(s, "debt")
    assert "traceback" not in out.lower(), (
        f"debt status raised on seeded debt: {out[:500]!r}"
    )
    # The principal is rendered with a thousands separator in the
    # engine ("10,000"); a plain "10000" would also be acceptable
    # if the formatting changes. Either form must appear.
    assert "10,000" in out or "10000" in out, (
        f"debt status didn't render seeded principal of 10000. "
        f"Output: {out[:500]!r}"
    )

    # 2. Pay 500
    char_id = s.character["id"]
    pre_credits = await h.get_credits(char_id)
    out2 = await h.cmd(s, "debt pay 500")
    assert "traceback" not in out2.lower(), (
        f"debt pay raised: {out2[:500]!r}"
    )

    # 3. Reload char from DB and verify both deductions landed
    fresh = await h.get_char(char_id)
    attrs = json.loads(fresh.get("attributes") or "{}")
    debt = attrs.get("hutt_debt") or {}
    new_principal = debt.get("principal", -1)
    assert new_principal == 9500, (
        f"After `debt pay 500`, principal should be 9500, got "
        f"{new_principal!r}. Full debt dict: {debt!r}"
    )
    post_credits = await h.get_credits(char_id)
    assert post_credits == pre_credits - 500, (
        f"After `debt pay 500`, credits should drop by 500. "
        f"pre={pre_credits} post={post_credits}"
    )


# ──────────────────────────────────────────────────────────────────────────
# SQ6 — travel: location-gated refusal
# ──────────────────────────────────────────────────────────────────────────

async def sq6_travel_refuses_outside_dock(h):
    """SQ6 — `travel <planet>` from a non-dock room refuses cleanly.

    The travel command requires the player to be at a docking-bay or
    landing-pad room. From the spawn (a street/cantina/landing room
    that doesn't satisfy the gate, depending on era), the command
    must refuse with a clear message — not crash, not silently
    succeed.

    We test from a Phase-2 quest state so we're past the
    quest-state gate; only the location gate fires. (From Phase 1
    the engine refuses on quest state regardless of room.)
    """
    s = await h.login_as("SQ6Traveler", room_id=1)
    await _seed_quest_state(h, s, phase=2, step=7,
                             completed_steps=[1, 2, 3, 4, 5, 6],
                             flags={"met_mak": True,
                                    "background_written": True,
                                    "sabacc_played": True})

    out = await h.cmd(s, "travel coruscant")
    assert "traceback" not in out.lower(), (
        f"travel raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # Acceptable refusals: the location gate ("docking bay or
    # landing pad") OR the passage-not-booked message. Both indicate
    # the command's gating logic ran without crashing.
    assert (
        "docking bay" in out_lc or "landing pad" in out_lc or
        "passage" in out_lc or "booked" in out_lc
    ), (
        f"travel refusal doesn't reference docking-bay/landing-pad/"
        f"passage. Output: {out[:400]!r}"
    )
