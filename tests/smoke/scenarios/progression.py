# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/progression.py — Progression / Jedi-gating /
+kudos recipient-side scenarios (PR1–PR5). Drop 3 Block D.

Existing E4 in `economy_progression.py` only checks that `+kudos`
runs without traceback — it does not verify the recipient's CP
state actually moved. PR3 closes that gap.

The CW progression system has shipped major engine modules with
unit tests but limited end-to-end smoke:
  - engine/tutorial_chains.py (667 LoC) — chain corpus + state
  - engine/jedi_gating.py (504 LoC) — playtime + predisposition
  - engine/force_signs.py (258 LoC) — sign emitters + cooldowns
  - engine/cp_engine.py — kudos awarding + ticks accumulator

Block D walks the player-observable parts of those systems through
the smoke harness:
  PR1 — Chain corpus loads cleanly, 9 chains, exactly 2 locked
        (the two Jedi-Path flavors)
  PR2 — Jedi-Path locked messages reference in-fiction
        discovery path (the "find the village" UX)
  PR3 — `+kudos <player>` increments recipient's cp_ticks total
  PR4 — `accumulate_play_time` writes to characters.play_time_seconds
        and `is_force_gate_passed` predicate works
  PR5 — Playtime persists across a fresh char fetch (proxy for
        login persistence — SQLite commits are atomic, so a fresh
        SELECT after the UPDATE is the same observation as a
        fresh login session reading the row)

PR4/PR5 directly drive the engine helpers rather than waiting for
the per-minute heartbeat tick to fire — `accumulate_play_time` is
the same path the heartbeat uses, so the assertion is on the
real persistence layer.
"""
from __future__ import annotations

import asyncio


# ──────────────────────────────────────────────────────────────────────────
# PR1 — Chain corpus loads
# ──────────────────────────────────────────────────────────────────────────

async def pr1_chain_corpus_loads_with_jedi_locked(h):
    """PR1 — `load_tutorial_chains('clone_wars')` yields a clean
    corpus with 9 chains; exactly two (the two Jedi-Path flavors)
    are locked.

    Catches the regression class where chains.yaml fails to parse
    or schema-validate at boot. Pre-fix this would surface as
    `corpus.errors` non-empty and players seeing zero chains in
    the chargen wizard.

    F.7.j (May 4 2026) — chain count went from 8 to 9 and locked
    count from 1 to 2 when the formerly-monolithic `jedi_path`
    chain was split into Path-A-flavored `jedi_path` and
    Path-B-flavored `jedi_path_independent`. Both remain locked at
    chargen; both surface the same in-fiction discovery message
    via PR2.
    """
    from engine.tutorial_chains import load_tutorial_chains

    corpus = load_tutorial_chains("clone_wars")
    assert corpus is not None, (
        "load_tutorial_chains('clone_wars') returned None — "
        "chains.yaml missing or unreadable."
    )
    assert corpus.ok, (
        f"chains.yaml has structural errors: {corpus.errors!r}"
    )
    assert len(corpus.chains) == 9, (
        f"Expected 9 CW chains; got {len(corpus.chains)}. "
        f"chain_ids: {[c.chain_id for c in corpus.chains]!r}"
    )
    locked = [c for c in corpus.chains if c.locked]
    locked_ids = {c.chain_id for c in locked}
    assert locked_ids == {"jedi_path", "jedi_path_independent"}, (
        f"Expected the two Jedi-Path chains locked; got "
        f"{sorted(locked_ids)!r}."
    )


# ──────────────────────────────────────────────────────────────────────────
# PR2 — Jedi-Path locked message references discovery
# ──────────────────────────────────────────────────────────────────────────

async def pr2_jedi_locked_message_references_discovery(h):
    """PR2 — At chargen, `is_chain_locked_for_character` for
    jedi_path returns True with a message that points the player
    toward the in-fiction discovery path.

    The locked message is canonical UX — players try to pick Jedi
    at chargen, get told "no, but here's how to unlock it." A
    stale or empty message would degrade silently to "This path is
    not yet available. Required: ..." (the generic fallback in
    `is_chain_locked_for_character`), which is correct but
    user-hostile.

    PR2 asserts the message contains at least one in-fiction
    reference (Jundland / village / trials / Master / discover) so
    a well-meaning "let's tighten the message" refactor that drops
    the discovery hint gets caught.
    """
    from engine.tutorial_chains import (
        load_tutorial_chains, is_chain_locked_for_character,
    )

    corpus = load_tutorial_chains("clone_wars")
    jedi = corpus.by_id().get("jedi_path")
    assert jedi is not None, "jedi_path chain not present in corpus"

    # Sentinel value matches the chargen wizard's bypass for the
    # faction_intent prereq (see is_chain_locked docstring).
    chargen_attrs = {
        "chargen_complete": False,
        "faction_intent": "__chargen_any__",
    }
    is_locked, msg = is_chain_locked_for_character(jedi, chargen_attrs)
    assert is_locked, (
        f"Jedi path should be locked at chargen for fresh char; "
        f"got is_locked={is_locked}"
    )
    msg_lc = msg.lower()
    discovery_terms = (
        "village", "jundland", "trial", "master", "discover", "find",
    )
    hit = [t for t in discovery_terms if t in msg_lc]
    assert hit, (
        f"Jedi locked-message doesn't reference the discovery path "
        f"(any of: {discovery_terms!r}). Message: {msg!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PR3 — kudos recipient cp_ticks delta
# ──────────────────────────────────────────────────────────────────────────

async def pr3_kudos_increments_recipient_cp_ticks(h):
    """PR3 — `+kudos Bob` from Alice increments Bob's cp_ticks row
    by KUDOS_TICKS (35).

    E4 only verifies +kudos runs cleanly from the giver's side. PR3
    confirms the recipient half — `engine/cp_engine.award_kudos`
    actually inserts/updates a cp_ticks row for the target char.
    Without this, a bug in `_award_ticks` would silently award no
    ticks while the giver sees the success message.
    """
    a = await h.login_as("PR3Alice", room_id=1)
    b = await h.login_as("PR3Bob", room_id=1)
    bob_id = b.character["id"]

    # Pre-state: cp_ticks row may not exist yet for a fresh char
    pre_rows = await h.db.fetchall(
        "SELECT ticks_total FROM cp_ticks WHERE char_id = ?",
        (bob_id,),
    )
    pre_total = pre_rows[0]["ticks_total"] if pre_rows else 0

    # +kudos takes a single name token; passing free-form comment
    # text after the name is rejected as a name-lookup miss
    # (pre-existing UX quirk in cp_commands._kudos.execute).
    out = await h.cmd(a, "+kudos PR3Bob")
    assert "traceback" not in out.lower(), (
        f"+kudos raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    assert "ticks awarded" in out_lc or "kudos" in out_lc, (
        f"+kudos didn't surface success message. Output: {out[:300]!r}"
    )

    # Post-state: cp_ticks must exist with delta of +35 (KUDOS_TICKS
    # in engine/cp_engine.py).
    post_rows = await h.db.fetchall(
        "SELECT ticks_total, last_source FROM cp_ticks WHERE char_id = ?",
        (bob_id,),
    )
    assert post_rows, (
        f"No cp_ticks row created for recipient after +kudos. "
        f"Recipient char_id={bob_id}. Output: {out[:300]!r}"
    )
    post_total = post_rows[0]["ticks_total"]
    delta = post_total - pre_total
    assert delta == 35, (
        f"+kudos should award 35 ticks (KUDOS_TICKS). pre={pre_total} "
        f"post={post_total} delta={delta}"
    )
    assert post_rows[0]["last_source"] == "kudos", (
        f"cp_ticks last_source should be 'kudos' after +kudos; "
        f"got {post_rows[0]['last_source']!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PR4 — accumulate_play_time persists and gate predicate works
# ──────────────────────────────────────────────────────────────────────────

async def pr4_playtime_accumulator_and_gate(h):
    """PR4 — Calling `accumulate_play_time(db, char_id, 60)` updates
    `characters.play_time_seconds`; `is_force_gate_passed` returns
    False below the 50-hour threshold and would return True above.

    Drives the same code path as the per-minute heartbeat tick. We
    don't wait for the tick to fire (slow) — the engine helper is
    the unit of test.
    """
    from engine.jedi_gating import (
        accumulate_play_time, is_force_gate_passed,
        PLAY_TIME_GATE_SECONDS,
    )

    s = await h.login_as("PR4Player", room_id=1)
    char_id = s.character["id"]

    # Sanity: gate threshold is 50h = 180,000s
    assert PLAY_TIME_GATE_SECONDS == 50 * 60 * 60, (
        f"PLAY_TIME_GATE_SECONDS expected 180000; got "
        f"{PLAY_TIME_GATE_SECONDS}. Design changed?"
    )

    # Initial state: gate not passed, playtime 0
    pre = await h.get_char(char_id)
    assert pre.get("play_time_seconds", 0) == 0, (
        f"Fresh char should have play_time_seconds=0; got "
        f"{pre.get('play_time_seconds')!r}"
    )
    assert not is_force_gate_passed(pre), (
        f"Fresh char (0s) should not pass the 50h gate."
    )

    # Accumulate 3 minutes
    new_total = await accumulate_play_time(h.db, char_id, 180)
    assert new_total == 180, (
        f"After accumulate(180s) on fresh char, total should be 180; "
        f"got {new_total!r}"
    )

    # Reload and verify gate still not passed
    after = await h.get_char(char_id)
    assert after.get("play_time_seconds") == 180, (
        f"DB readback after accumulate disagrees: db={after.get('play_time_seconds')!r}"
    )
    assert not is_force_gate_passed(after), (
        f"180s of playtime should not pass the 50h gate."
    )


# ──────────────────────────────────────────────────────────────────────────
# PR5 — Playtime persists across a fresh char fetch
# ──────────────────────────────────────────────────────────────────────────

async def pr5_playtime_persists_across_fetch(h):
    """PR5 — A second `accumulate_play_time` adds to the first;
    a fresh `db.get_character` after both shows the cumulative
    total.

    The pre-existing intent of this scenario was "playtime
    persists across login." The actual persistence layer is
    `UPDATE characters SET play_time_seconds = play_time_seconds + ?`,
    which is atomic at SQLite commit. A fresh `get_character`
    after the writes is the same observation a fresh login session
    would make on its character row read; testing the round-trip
    via the DB is more reliable than driving a logout-relogin
    sequence (the harness's session machinery is class-scoped).
    """
    from engine.jedi_gating import accumulate_play_time

    s = await h.login_as("PR5Player", room_id=1)
    char_id = s.character["id"]

    # Two independent increments
    await accumulate_play_time(h.db, char_id, 60)
    await accumulate_play_time(h.db, char_id, 120)

    # Force-fresh fetch through the same path the harness uses on
    # login (`db.get_character`). This is the persistence assertion.
    fresh = await h.db.get_character(char_id)
    assert fresh is not None, (
        f"get_character({char_id}) returned None after two accumulates"
    )
    assert fresh.get("play_time_seconds") == 180, (
        f"After two accumulates (60 + 120 = 180), the fresh-fetched "
        f"char should show 180; got "
        f"{fresh.get('play_time_seconds')!r}"
    )
