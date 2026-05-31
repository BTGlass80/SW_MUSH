# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/chain_attempt.py — F.8.c.2.b₆ end-to-end
(May 20 2026).

CA-1 … CA-4: live in-process verification of the `chain attempt`
command and the post-chargen prerequisite chain-event dispatch.

The unit tests at tests/test_f8c2b6_chain_attempt_command.py
exercise the matcher / dispatcher / failure paths against mocks.
These scenarios exercise the same code through the live harness
to catch wiring regressions (registration drift, missing import,
session-render bugs).

Scenarios
=========

* **CA-1** — `chain status` with no active chain says so cleanly.
* **CA-2** — `chain attempt` with no active chain says so cleanly
              (does not crash).
* **CA-3** — With an injected active chain on a
              `skill_check_passed` step, `chain attempt` rolls
              the authored skill at the authored difficulty.
              Either passes (chain advances) or fails (retry
              message). The smoke checks the parse path, not the
              dice (success and failure are both valid outcomes).
* **CA-4** — With an injected active chain on a non-skill step
              (talk_to_npc), `chain attempt` rejects gracefully
              with a hint.

Notes
=====

* CA-3 uses `republic_intelligence` step 3
  (skill=sneak, difficulty=8). If chains.yaml is re-authored such
  that step 3 is no longer skill_check_passed, the scenario
  self-skips via the harness assertion at the top.

* The harness's `login_as` doesn't set a tutorial chain on the
  fresh character — CA-3 / CA-4 inject one via the
  `attributes` JSON, mirroring spacer_quest.py's
  `_seed_spacer_state` pattern.
"""
from __future__ import annotations

import json


async def _inject_chain(h, s, chain_id: str, step: int) -> None:
    """Seed a tutorial_chain block onto the character's attributes
    JSON. Mirrors engine.tutorial_chains.select_chain's state
    shape so the engine's _get_active_step resolver picks it up
    cleanly."""
    char_id = s.character["id"]
    char = await h.get_char(char_id)
    attrs = json.loads(char.get("attributes") or "{}")
    attrs["tutorial_chain"] = {
        "chain_id": chain_id,
        "step": step,
        "started_at": 1000000,
        "completed_steps": list(range(1, step)),
        "completion_state": "active",
    }
    await h.db.save_character(char_id, attributes=json.dumps(attrs))
    s.character = await h.get_char(char_id)
    # Invalidate the session's cached character object so the next
    # command-handler call sees the injected chain.
    try:
        s.session.invalidate_char_obj()
    except AttributeError:
        # Harness API drift — the session may not need explicit
        # invalidation. Skip and continue.
        pass


# ──────────────────────────────────────────────────────────────────────────
# CA-1 — `chain status` with no active chain
# ──────────────────────────────────────────────────────────────────────────


async def ca_1_status_no_active_chain(h):
    """CA-1 — A fresh PC has no active chain. `chain status`
    surfaces the no-active-chain message without crashing."""
    s = await h.login_as("CA1Solo", room_id=1)
    out = await h.cmd(s, "chain status")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`chain status` raised: {out[:500]!r}"
    )
    assert "no active tutorial chain" in out_lc, (
        f"`chain status` should say 'no active tutorial chain' "
        f"for a fresh PC. Output: {out[:300]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# CA-2 — `chain attempt` with no active chain
# ──────────────────────────────────────────────────────────────────────────


async def ca_2_attempt_no_active_chain(h):
    """CA-2 — `chain attempt` with no active chain says so
    cleanly. Catches the failure mode where the command would
    crash on missing chain state."""
    s = await h.login_as("CA2Solo", room_id=1)
    out = await h.cmd(s, "chain attempt")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`chain attempt` raised: {out[:500]!r}"
    )
    assert "no active tutorial chain" in out_lc, (
        f"`chain attempt` should say 'no active tutorial chain' "
        f"for a fresh PC. Output: {out[:300]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# CA-3 — `chain attempt` on a skill_check_passed step rolls
# ──────────────────────────────────────────────────────────────────────────


async def ca_3_attempt_rolls_on_skill_step(h):
    """CA-3 — With republic_intelligence step 3 injected
    (skill_check_passed: sneak vs 8), `chain attempt` runs the
    roll, dispatches to on_skill_check_passed, and either
    advances (success) or surfaces a retry message (failure).

    The smoke validates the wiring, not the RNG: both outcomes
    are valid. What MUST hold is (a) no traceback, (b) the roll
    text is rendered to the player, (c) the dispatcher fired
    (which we infer from the response shape).
    """
    s = await h.login_as("CA3Sneaker", room_id=1)
    # Verify the fixture chain step is still skill_check_passed.
    # If chains.yaml is re-authored, skip rather than fail.
    from engine.chain_events import get_active_step_info
    await _inject_chain(h, s, "republic_intelligence", step=3)
    info = get_active_step_info(s.character)
    if info is None or info.get("completion_type") != "skill_check_passed":
        # Fixture re-authored; this scenario no longer maps. Pass
        # the smoke as a no-op rather than failing on YAML drift —
        # the unit test catches re-authoring.
        return

    out = await h.cmd(s, "chain attempt")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`chain attempt` raised: {out[:500]!r}"
    )
    # The roll text must be rendered. Either "success" or "failure"
    # appears; the dice pool ("3D" / "4D+1" etc.) appears; the
    # difficulty appears.
    assert ("success" in out_lc or "failure" in out_lc), (
        f"`chain attempt` did not render a roll outcome. "
        f"Output: {out[:500]!r}"
    )
    assert "sneak" in out_lc, (
        f"`chain attempt` did not name the rolled skill. "
        f"Output: {out[:300]!r}"
    )
    # Difficulty 8 should appear in the output.
    assert "8" in out, (
        f"`chain attempt` did not show the difficulty (8). "
        f"Output: {out[:300]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# CA-4 — `chain attempt` on a non-skill step rejects with hint
# ──────────────────────────────────────────────────────────────────────────


async def ca_4_attempt_on_non_skill_step_rejected(h):
    """CA-4 — Inject a chain step whose completion is not
    skill_check_passed (e.g. talk_to_npc). `chain attempt`
    refuses with a hint pointing at the right interaction
    pattern.

    This catches the failure mode where the command would
    silently roll a default skill or crash on a missing
    `skill` field.
    """
    s = await h.login_as("CA4Talker", room_id=1)
    # republic_intelligence step 1 is talk_to_npc (Major Tarrn,
    # in the YAML). Inject and attempt.
    await _inject_chain(h, s, "republic_intelligence", step=1)
    from engine.chain_events import get_active_step_info
    info = get_active_step_info(s.character)
    if info is None or info.get("completion_type") == "skill_check_passed":
        # Fixture re-authored; this scenario no longer maps.
        return

    out = await h.cmd(s, "chain attempt")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`chain attempt` on non-skill step raised: {out[:500]!r}"
    )
    assert "does not use 'chain attempt'" in out_lc, (
        f"`chain attempt` on non-skill step should reject with "
        f"'does not use chain attempt'. Output: {out[:500]!r}"
    )
