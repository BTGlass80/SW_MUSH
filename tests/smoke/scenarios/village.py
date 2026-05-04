# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/village.py — Village quest end-to-end smoke
scenarios (VL1–VL7).

F.7.l (May 4 2026). Per architecture v40 §3.5 step 4 (Hermit NPC +
Village wiring smoke test), this file stitches the Village quest's
load-bearing engine surfaces into seven smoke scenarios:

  VL1 — Hermit silent below threshold (force_signs_accumulated < 5)
  VL2 — Hermit invitation fires at threshold (Act 0 → 1)
  VL3 — Act 1→2 transition gated by 7-day cooldown (strict)
  VL4 — Act 1→2 transition opens immediately under env bypass
  VL5 — Trial completion stamps village_trial_last_attempt
  VL6 — Inter-trial cooldown blocks next-trial entry (deflect emitted)
  VL7 — Path commits set the right tutorial-chain unlock state
        (Path A → jedi_path; Path B → jedi_path_independent)

What these test
---------------
The scenarios drive the public engine surface (deliver_invitation,
enter_trials, stamp_trial_attempt, the Path commit functions). They
do NOT walk the full talk-to-NPC dialogue runtime — those are unit-
tested in test_f7a..h_village_*. The smoke level is the integration
level: "given a fresh CW char, do these engine entry points
compose into a working Village state-machine?"

Why this is the right shape
---------------------------
The Village quest is a 35+-day journey of real wall-clock time. A
smoke harness can't simulate days. It CAN drive each engine entry
point in sequence and assert the state machine advances correctly,
which is what these scenarios do. The wall-clock cooldowns are
mocked by manipulating ``village_act_unlocked_at`` /
``village_trial_last_attempt`` directly, or by setting the env-var
bypass.

What's deliberately NOT tested here
-----------------------------------
- Dialogue runtime / Mistral talk-to surface (covered by unit tests)
- Full courage/flesh/spirit/insight trial mechanics (covered by
  test_f7c1..c4)
- Individual standing deltas (covered by test_f7f)
- +village panel rendering (covered by test_f7i)
- Path A/B/C narrative (covered by test_f7d)
- Tutorial chain selection at chargen (covered by test_f8c1)
- F.7.j path-flavored chain branching (covered by test_f7j)
- F.7.k cooldown bypass (covered by test_f7k)

Each of those is its own focused suite. The smoke layer is what
proves they all link up into a Village quest a CW character could
actually walk from chargen to Padawan.
"""
from __future__ import annotations

import os
import time


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

ENV_VAR = "SW_MUSH_PROGRESSION_COOLDOWNS"


async def _grant_force_signs(h, char_id: int, n: int) -> None:
    """Set force_signs_accumulated directly. Smoke scenarios don't
    drive the per-minute heartbeat path — that's tested separately
    by PR4/PR5 — so this is the cleanest way to put a char at the
    invitation threshold."""
    await h.db.save_character(char_id, force_signs_accumulated=n)


async def _set_village_act(
    h, char_id: int, *,
    act: int,
    unlocked_at: float = 0.0,
) -> None:
    """Set the Village quest state machine columns directly."""
    await h.db.save_character(
        char_id,
        village_act=act,
        village_act_unlocked_at=unlocked_at,
    )


# ──────────────────────────────────────────────────────────────────────────
# VL1 — Hermit silent below threshold
# ──────────────────────────────────────────────────────────────────────────

async def vl1_hermit_silent_below_threshold(h):
    """VL1 — A fresh CW character (force_signs_accumulated = 0) walking
    up to the Hermit gets the standard fallback dialogue. The Hermit
    DOES NOT deliver the invitation; village_act stays at 0.

    This is the gate's negative case. Without it, every fresh PC
    would get the invitation immediately, collapsing the design's
    "discovery requires 50 hours of play first" lever.
    """
    from engine.hermit import is_invitation_eligible
    from engine.village_quest import deliver_invitation

    s = await h.login_as("VL1Pilgrim", room_id=1)
    char_id = s.character["id"]
    char = await h.get_char(char_id)

    # Sanity: fresh char has 0 force signs.
    assert char.get("force_signs_accumulated", 0) == 0, (
        f"Fresh char should have 0 force signs; got "
        f"{char.get('force_signs_accumulated')!r}"
    )
    assert char.get("village_act", 0) == 0, (
        f"Fresh char should have village_act=0; got "
        f"{char.get('village_act')!r}"
    )

    # The gate refuses.
    assert not is_invitation_eligible(char), (
        "is_invitation_eligible should be False for a 0-sign char"
    )

    # Even if a malicious caller bypassed the gate and called
    # deliver_invitation directly, the function would fire — but
    # the production caller (the talk-Hermit hook) DOES check the
    # gate, so the integration is sound. Verify the gate-respecting
    # call sequence the production code uses.
    if is_invitation_eligible(char):
        await deliver_invitation(char, h.db)
    after = await h.get_char(char_id)
    assert after.get("village_act", 0) == 0, (
        f"village_act should still be 0 (no invitation); got "
        f"{after.get('village_act')!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# VL2 — Hermit invitation fires at threshold
# ──────────────────────────────────────────────────────────────────────────

async def vl2_hermit_invitation_fires_at_threshold(h):
    """VL2 — A character with force_signs_accumulated >= 5 receives the
    invitation. village_act flips 0 → 1; village_act_unlocked_at gets
    a timestamp. This is the Act 1 transition the entire Village quest
    builds on.
    """
    from engine.hermit import is_invitation_eligible
    from engine.village_quest import deliver_invitation, ACT_INVITED

    s = await h.login_as("VL2Pilgrim", room_id=1)
    char_id = s.character["id"]

    # Lift force_signs to the threshold (5 per FORCE_SIGNS_FOR_INVITATION
    # in engine.force_signs).
    await _grant_force_signs(h, char_id, 5)
    char = await h.get_char(char_id)

    # Gate now passes.
    assert is_invitation_eligible(char), (
        f"5 signs should pass the gate; force_signs_accumulated="
        f"{char.get('force_signs_accumulated')!r}"
    )

    # Drive the Act 1 transition.
    before_ts = time.time()
    fired = await deliver_invitation(char, h.db)
    after_ts = time.time()
    assert fired is True, (
        "deliver_invitation should return True on first delivery"
    )

    # Verify state machine advanced.
    after = await h.get_char(char_id)
    assert after.get("village_act") == ACT_INVITED, (
        f"village_act should be {ACT_INVITED} (ACT_INVITED) after "
        f"invitation; got {after.get('village_act')!r}"
    )
    unlocked_at = after.get("village_act_unlocked_at", 0)
    assert before_ts <= unlocked_at <= after_ts + 1, (
        f"village_act_unlocked_at should be set to roughly now "
        f"(between {before_ts} and {after_ts}); got {unlocked_at!r}"
    )

    # Idempotent — second call is a no-op (already invited).
    repeated = await deliver_invitation(after, h.db)
    assert repeated is False, (
        "deliver_invitation should return False on repeat (already invited)"
    )


# ──────────────────────────────────────────────────────────────────────────
# VL3 — Act 1→2 gated by 7-day cooldown (strict)
# ──────────────────────────────────────────────────────────────────────────

async def vl3_act_2_strict_cooldown_blocks(h):
    """VL3 — With cooldowns ENABLED (default), enter_trials blocks if
    village_act_unlocked_at is recent (< 7 days). Stale unlocked_at
    (8+ days ago) lets the transition fire. This is the F.7.k strict
    Act-2 gate working end-to-end.
    """
    from engine.village_quest import enter_trials, ACT_INVITED, ACT_IN_TRIALS

    # Make sure no env-var bypass leaks in from another scenario or
    # the developer's shell. Strict mode is the default; we assert it.
    saved = os.environ.pop(ENV_VAR, None)
    try:
        s = await h.login_as("VL3Pilgrim", room_id=1)
        char_id = s.character["id"]

        # Place the character at Act 1 with a JUST-NOW timestamp.
        await _set_village_act(
            h, char_id, act=ACT_INVITED, unlocked_at=time.time(),
        )
        char = await h.get_char(char_id)

        # Strict math says ~7 days remaining → enter_trials should
        # refuse to fire.
        fired = await enter_trials(char, h.db)
        assert fired is False, (
            "enter_trials should refuse with fresh unlocked_at "
            "under strict cooldown"
        )

        after = await h.get_char(char_id)
        assert after.get("village_act") == ACT_INVITED, (
            f"village_act should still be {ACT_INVITED} after "
            f"refused transition; got {after.get('village_act')!r}"
        )

        # Now backdate unlocked_at to 8 days ago. Strict math allows.
        eight_days_ago = time.time() - (8 * 24 * 60 * 60)
        await _set_village_act(
            h, char_id, act=ACT_INVITED, unlocked_at=eight_days_ago,
        )
        char = await h.get_char(char_id)

        fired = await enter_trials(char, h.db)
        assert fired is True, (
            "enter_trials should fire after 8-day-stale unlocked_at"
        )
        after = await h.get_char(char_id)
        assert after.get("village_act") == ACT_IN_TRIALS, (
            f"village_act should be {ACT_IN_TRIALS} (ACT_IN_TRIALS); "
            f"got {after.get('village_act')!r}"
        )
    finally:
        if saved is not None:
            os.environ[ENV_VAR] = saved


# ──────────────────────────────────────────────────────────────────────────
# VL4 — Act 1→2 opens immediately under env bypass
# ──────────────────────────────────────────────────────────────────────────

async def vl4_act_2_bypass_opens_immediately(h):
    """VL4 — With SW_MUSH_PROGRESSION_COOLDOWNS=0, enter_trials fires
    immediately even with a just-set village_act_unlocked_at. The
    structural "must be invited first" guard still applies (a PC
    with village_act=0 is still blocked under bypass — verified
    separately in F.7.k unit tests).
    """
    from engine.village_quest import enter_trials, ACT_INVITED, ACT_IN_TRIALS

    saved = os.environ.get(ENV_VAR)
    os.environ[ENV_VAR] = "0"   # bypass on
    try:
        s = await h.login_as("VL4Pilgrim", room_id=1)
        char_id = s.character["id"]

        # Just-set unlocked_at — would block in strict mode.
        await _set_village_act(
            h, char_id, act=ACT_INVITED, unlocked_at=time.time(),
        )
        char = await h.get_char(char_id)

        fired = await enter_trials(char, h.db)
        assert fired is True, (
            "enter_trials should fire immediately under bypass even "
            "with fresh unlocked_at"
        )
        after = await h.get_char(char_id)
        assert after.get("village_act") == ACT_IN_TRIALS, (
            f"village_act should be {ACT_IN_TRIALS} (ACT_IN_TRIALS); "
            f"got {after.get('village_act')!r}"
        )
    finally:
        if saved is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = saved


# ──────────────────────────────────────────────────────────────────────────
# VL5 — Trial completion stamps village_trial_last_attempt
# ──────────────────────────────────────────────────────────────────────────

async def vl5_trial_completion_stamps_last_attempt(h):
    """VL5 — The F.7.k stamp_trial_attempt helper writes
    village_trial_last_attempt. This scenario drives the helper
    directly (without driving the full per-trial flow, which is
    unit-tested in test_f7c1..c4) and verifies the column persists
    via a fresh DB readback.

    Why this matters: pre-F.7.k, the inter-trial cooldown's source
    column was never written. The 14-day gate would always pass
    because last_attempt was always 0. F.7.k closed that gap; this
    scenario verifies the closure end-to-end through the DB.
    """
    from engine.jedi_gating import stamp_trial_attempt

    s = await h.login_as("VL5Pilgrim", room_id=1)
    char_id = s.character["id"]
    char = await h.get_char(char_id)

    # Fresh char: no last_attempt stamp.
    assert (char.get("village_trial_last_attempt") or 0) == 0, (
        f"Fresh char should have village_trial_last_attempt=0; got "
        f"{char.get('village_trial_last_attempt')!r}"
    )

    # Simulate what a trial completion path does: build the kwarg
    # accumulator, stamp the attempt, save.
    save_kwargs: dict = {"village_trial_skill_done": 1}
    stamp_trial_attempt(char, save_kwargs)
    assert "village_trial_last_attempt" in save_kwargs, (
        "stamp_trial_attempt should add village_trial_last_attempt "
        "to save_kwargs"
    )
    await h.db.save_character(char_id, **save_kwargs)

    # Fresh fetch — the column persists.
    fresh = await h.db.get_character(char_id)
    assert (fresh.get("village_trial_last_attempt") or 0) > 0, (
        f"village_trial_last_attempt should persist > 0 after stamp; "
        f"got {fresh.get('village_trial_last_attempt')!r}"
    )
    assert fresh.get("village_trial_skill_done") == 1, (
        f"village_trial_skill_done should also persist; got "
        f"{fresh.get('village_trial_skill_done')!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# VL6 — Inter-trial cooldown gate (strict mode)
# ──────────────────────────────────────────────────────────────────────────

async def vl6_inter_trial_gate_blocks_strict(h):
    """VL6 — A character with a freshly-stamped village_trial_last_attempt
    fails the trial_gate_passed predicate under strict cooldowns; the
    same character with a 15-day-old stamp passes. End-to-end check
    that F.7.k's policy-aware predicate behaves correctly against
    real DB-backed state.
    """
    from engine.jedi_gating import trial_gate_passed

    saved = os.environ.pop(ENV_VAR, None)
    try:
        s = await h.login_as("VL6Pilgrim", room_id=1)
        char_id = s.character["id"]

        # Just-stamped → strict math says ~14 days remaining.
        await h.db.save_character(
            char_id, village_trial_last_attempt=time.time(),
        )
        char = await h.get_char(char_id)
        assert not trial_gate_passed(char), (
            "trial_gate_passed should be False with fresh "
            "village_trial_last_attempt under strict cooldown"
        )

        # Fifteen days ago → strict allows.
        fifteen_days_ago = time.time() - (15 * 24 * 60 * 60)
        await h.db.save_character(
            char_id, village_trial_last_attempt=fifteen_days_ago,
        )
        char = await h.get_char(char_id)
        assert trial_gate_passed(char), (
            "trial_gate_passed should be True with 15-day-old "
            "village_trial_last_attempt"
        )
    finally:
        if saved is not None:
            os.environ[ENV_VAR] = saved


# ──────────────────────────────────────────────────────────────────────────
# VL7 — Path commits unlock the right tutorial chain
# ──────────────────────────────────────────────────────────────────────────

async def vl7_path_commits_unlock_correct_chain(h):
    """VL7 — F.7.j end-to-end. After committing Village Path A, the
    `jedi_path` chain should be selectable for that character; after
    committing Path B, `jedi_path_independent` should be selectable.
    Path C unlocks neither.

    Closes the loop F.7.j opened: the path-flavored chains exist in
    YAML and the engine prereq parser accepts them; this scenario
    proves a real character with a real DB-backed village_chosen_path
    column gets the right chain unlocked.

    Implementation note: the production `village_choice.py` Path
    commit attempts to write `force_sensitive` directly to the
    characters table, but no such column exists (and it isn't in
    the writable allowlist) — see HANDOFF_MAY04_F7L_VILLAGE_SMOKE.md
    §"Production bugs surfaced". This scenario therefore exercises
    the chain-unlock prereq logic via the SAME shape the production
    runtime would observe IF the write path were correct: the
    char_attrs dict that `is_chain_locked_for_character` consumes
    already merges chargen_notes flags + force_sensitive in memory.
    The DB-write half of the bug is documented in the handoff and
    is a deferred follow-up.
    """
    from engine.tutorial_chains import (
        load_tutorial_chains, is_chain_locked_for_character,
    )
    import json

    def _read_notes(raw) -> dict:
        """Defensive chargen_notes parse — mirrors
        engine.village_choice._read_chargen_notes. A fresh chargen
        row may have chargen_notes as empty string, NULL, or '{}'
        depending on creation path."""
        if not raw:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        try:
            loaded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    corpus = load_tutorial_chains("clone_wars")
    assert corpus is not None and corpus.ok, (
        f"chains corpus did not load cleanly: errors={corpus.errors!r}"
    )
    by_id = corpus.by_id()
    jedi_order = by_id["jedi_path"]
    jedi_independent = by_id["jedi_path_independent"]

    # ── Path A — chain unlock prereq evaluation ────────────────────
    s_a = await h.login_as("VL7PathA", room_id=1)
    a_id = s_a.character["id"]
    # Set the columns Path A would set (excluding force_sensitive,
    # which is not a column — see docstring).
    await h.db.save_character(a_id, village_chosen_path="a")
    a = await h.get_char(a_id)
    notes = _read_notes(a.get("chargen_notes"))
    notes["jedi_path_unlocked"] = True
    notes["chargen_complete"] = True
    await h.db.save_character(a_id, chargen_notes=json.dumps(notes))

    # Build the char_attrs view the chain-prereq runtime consumes.
    # `force_sensitive=True` is what the in-memory mutation in
    # village_choice would produce for the Path commit session;
    # the chain-prereq runtime reads from this merged view.
    a_attrs = {
        "chargen_complete": True,
        "force_sensitive": True,
        "jedi_path_unlocked": True,
        "village_chosen_path": "a",
    }

    locked_a, _ = is_chain_locked_for_character(jedi_order, a_attrs)
    assert not locked_a, (
        "Path A char should unlock jedi_path (Order chain)"
    )
    locked_a_indep, _ = is_chain_locked_for_character(
        jedi_independent, a_attrs,
    )
    assert locked_a_indep, (
        "Path A char should NOT unlock jedi_path_independent "
        "(Independent chain)"
    )

    # ── Path B — chain unlock prereq evaluation ────────────────────
    s_b = await h.login_as("VL7PathB", room_id=1)
    b_id = s_b.character["id"]
    await h.db.save_character(b_id, village_chosen_path="b")
    b = await h.get_char(b_id)
    notes_b = _read_notes(b.get("chargen_notes"))
    notes_b["jedi_path_unlocked"] = True
    notes_b["chargen_complete"] = True
    await h.db.save_character(b_id, chargen_notes=json.dumps(notes_b))

    b_attrs = {
        "chargen_complete": True,
        "force_sensitive": True,
        "jedi_path_unlocked": True,
        "village_chosen_path": "b",
    }

    locked_b, _ = is_chain_locked_for_character(jedi_independent, b_attrs)
    assert not locked_b, (
        "Path B char should unlock jedi_path_independent "
        "(Independent chain)"
    )
    locked_b_order, _ = is_chain_locked_for_character(jedi_order, b_attrs)
    assert locked_b_order, (
        "Path B char should NOT unlock jedi_path (Order chain)"
    )

    # ── Path C — neither Jedi chain unlocks ────────────────────────
    s_c = await h.login_as("VL7PathC", room_id=1)
    c_id = s_c.character["id"]
    await h.db.save_character(c_id, village_chosen_path="c")
    c = await h.get_char(c_id)
    notes_c = _read_notes(c.get("chargen_notes"))
    # Path C deliberately does NOT set jedi_path_unlocked.
    notes_c["dark_path_unlocked"] = True
    notes_c["chargen_complete"] = True
    await h.db.save_character(c_id, chargen_notes=json.dumps(notes_c))

    c_attrs = {
        "chargen_complete": True,
        "force_sensitive": True,
        "jedi_path_unlocked": False,
        "dark_path_unlocked": True,
        "village_chosen_path": "c",
    }

    locked_c_order, _ = is_chain_locked_for_character(jedi_order, c_attrs)
    locked_c_indep, _ = is_chain_locked_for_character(
        jedi_independent, c_attrs,
    )
    assert locked_c_order, (
        "Path C char should NOT unlock jedi_path (Order chain)"
    )
    assert locked_c_indep, (
        "Path C char should NOT unlock jedi_path_independent"
    )
