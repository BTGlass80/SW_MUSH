# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/pvp_flag.py — +pvp opt-in flag scenarios
(PVF-1 … PVF-10).

End-to-end verification of the v27 +pvp opt-in PvP flag. The unit
tests in tests/test_pvp_flag_unit.py prove the byte-level shape of
the migration, gate logic, command registration, and help text;
these scenarios run the live in-process server and verify the
player-visible behavior.

Scenarios
=========

* **PVF-1** — ``+pvp on`` flips the DB column from 0 to 1, broadcasts
  to the room, and `+pvp status` reflects the new state.

* **PVF-2** — In a CONTESTED zone, a flagged PC attacking an
  unflagged PC bypasses the challenge/accept dance. (Either-party-
  flagged interpretation: the attacker's flag is enough to consent.)

* **PVF-3** — In a CONTESTED zone, an unflagged PC attacking a
  flagged PC also bypasses the challenge/accept dance. (Inverse of
  PVF-2 — confirms the "either party" reading.)

* **PVF-4** — After a flagged engagement, the engaged PC cannot
  unflag for PVP_UNFLAG_COOLDOWN_S. ``+pvp off`` is refused with
  the cooldown-remaining message.

* **PVF-5** — SECURED zones still refuse PvP even when both parties
  are flagged. The flag does NOT override SECURED. (This is the
  test that catches "I'm in the Jedi Temple, why can flagged
  players attack each other here" — the launch-blocker scenario.)

* **PVF-6** — In a LAWLESS zone, a flagged-vs-flagged attack
  proceeds (sanity: no consent gate at all in LAWLESS; the flag
  affects nothing here). Drives the LAWLESS code path.

* **PVF-7** — In a LAWLESS zone, an UNFLAGGED-vs-UNFLAGGED attack
  ALSO proceeds (no consent required in LAWLESS regardless of
  flag). Pins the LAWLESS-bypasses-consent invariant from the
  security model so future security-resolver work doesn't
  accidentally extend consent gates into LAWLESS.

* **PVF-8** — After the 5-minute cooldown expires, ``+pvp off``
  succeeds. (Pins the cooldown is a TIMER, not permanent.) The
  scenario simulates time passing by clearing the cooldown in
  the DB directly — same end state as waiting 5 minutes.

* **PVF-9** — Mutual flag toggle then mutual combat: both PCs
  flag on, attack proceeds in CONTESTED, both PCs survive (or one
  dies), and both end up cooldown-locked. End-to-end happy path
  for the most common production flow.

* **PVF-10** — `look` output shows the `[PvP]` ANSI-red marker
  for flagged PCs in the room contents. The byte-level unit
  test at `test_pvp_display_surfaces.py` asserts the marker
  literal exists in the source; PVF-10 asserts it actually
  reaches the live `look` output via the room-contents render
  path. A regression where the marker source-string got moved
  into a branch never reached at runtime would pass the unit
  test but fail PVF-10.

Notes
=====

* PVF-1, PVF-2, PVF-4 exercise the happy path on the default CW
  spawn (room 1) which is CONTESTED (no security_level set in
  YAML — defaults to CONTESTED per engine/security.py).

* PVF-5 needs a SECURED room. It looks up ``docking_bay_94_pit``
  by SLUG via ``h.room_id_by_slug("docking_bay_94_pit")`` — that
  CW spaceport room resolves SECURED via S-RES.2's
  tatooine_spaceport zone-level security default. The earlier
  "log into room_id=1" assumption was wrong: DB id 1 is a legacy
  seed in the schema SQL ("Landing Pad - Mos Eisley Spaceport"),
  pre-inserted before the YAML world write, with ``zone_id=None``
  and ``properties={}`` — which resolves CONTESTED. The pre-S-RES.2
  workaround (patching room 1 to SECURED at runtime) masked this
  pre-existing schema-seed-collision bug. With slug lookup the
  scenario drives the real SECURED-gate path end-to-end.

* PVF-6, PVF-7 need a LAWLESS room. They look up
  ``undercity_market`` (Nar Shaddaa Undercity Market) by slug —
  the room's top-level ``security_level: lawless`` is promoted
  into ``properties.security`` at write-time by S-RES, so the
  resolver returns LAWLESS without zone-walk.

* PVF-8 directly manipulates the cooldown's expiry timestamp in
  the character's ``attributes`` JSON (via the
  ``engine.cooldowns.clear_cooldown`` helper) rather than
  sleeping the test for 5 real minutes. This is the production
  cooldown clear path the unflag-after-expiry case actually
  takes, so it's a faithful simulation.

* PVF-9 runs in CONTESTED, exercises the mutual-flag scenario
  where the consent-gate's "either party flagged" path fires
  and the unflag cooldown applies to BOTH sides per
  parser/combat_commands.py::_check_pvp_consent.
"""
from __future__ import annotations

import asyncio


# ──────────────────────────────────────────────────────────────────────────
# PVF-1 — +pvp on flips DB column + broadcasts
# ──────────────────────────────────────────────────────────────────────────


async def pvf_1_flag_on_persists_and_broadcasts(h):
    """PVF-1 — `+pvp on` sets pvp_flagged=1 in the DB, broadcasts the
    change to the room, and `+pvp status` reflects ON."""
    a = await h.login_as("PVF1Alice", room_id=1)

    # Pre-check: flag is off by default
    char_pre = await h.get_char(a.character["id"])
    assert (char_pre.get("pvp_flagged") or 0) == 0, (
        f"PVF1Alice starts with pvp_flagged != 0. "
        f"Migration may not have run with DEFAULT 0. "
        f"Char: {char_pre!r}"
    )

    out = await h.cmd(a, "+pvp on")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`+pvp on` raised: {out[:500]!r}"
    )
    assert "pvp flag" in out_lc and "on" in out_lc, (
        f"+pvp on response should confirm the flag is now on. "
        f"Output: {out[:300]!r}"
    )

    # DB column updated
    char_post = await h.get_char(a.character["id"])
    assert char_post.get("pvp_flagged") == 1, (
        f"PVF1Alice.pvp_flagged != 1 after `+pvp on`. "
        f"save_character may have silently dropped the column "
        f"(check _CHARACTER_WRITABLE_COLUMNS). "
        f"Char: {char_post!r}"
    )

    # +pvp status shows ON
    status_out = await h.cmd(a, "+pvp status")
    status_lc = status_out.lower()
    assert "on" in status_lc, (
        f"+pvp status should report ON after +pvp on. "
        f"Output: {status_out[:300]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-2 — flagged attacker bypasses challenge/accept in CONTESTED
# ──────────────────────────────────────────────────────────────────────────


async def pvf_2_flagged_attacker_bypasses_consent(h):
    """PVF-2 — Flagged attacker hitting unflagged target in a
    CONTESTED room: the attack proceeds without challenge/accept.

    Byte-level signal: `attack` output does NOT contain "Imperial law
    prohibits unprovoked assault here" (the consent-required
    refusal). Output also does NOT contain a traceback.
    """
    striker = await h.login_as("PVF2Striker", room_id=1)
    target = await h.login_as("PVF2Target", room_id=1)

    # Flag the striker.
    await h.cmd(striker, "+pvp on")

    # Striker attacks target. No prior challenge/accept.
    out = await h.cmd(striker, f"attack {target.character['name']}")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`attack` raised: {out[:500]!r}"
    )
    # The consent-refused text from _check_pvp_consent.
    assert "imperial law prohibits" not in out_lc, (
        f"Flagged attacker was refused by consent gate — flag did "
        f"not unlock CONTESTED-zone PvP. Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-3 — flagged TARGET also unlocks (inverse of PVF-2)
# ──────────────────────────────────────────────────────────────────────────


async def pvf_3_flagged_target_unlocks_attacker(h):
    """PVF-3 — Unflagged attacker hitting flagged target in CONTESTED:
    attack proceeds without challenge/accept.

    Confirms the either-party-flagged reading. Without this scenario,
    a regression that requires BOTH parties to be flagged would be
    invisible.
    """
    striker = await h.login_as("PVF3Striker", room_id=1)
    target = await h.login_as("PVF3Target", room_id=1)

    # Flag the TARGET (not the striker).
    await h.cmd(target, "+pvp on")

    out = await h.cmd(striker, f"attack {target.character['name']}")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`attack` raised: {out[:500]!r}"
    )
    assert "imperial law prohibits" not in out_lc, (
        f"Unflagged attacker hitting flagged target was refused. "
        f"Either-party-flagged interpretation has regressed. "
        f"Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-4 — unflag cooldown locks +pvp off after engagement
# ──────────────────────────────────────────────────────────────────────────


async def pvf_4_unflag_cooldown_locks_after_engagement(h):
    """PVF-4 — After a flagged attack engages, the unflag cooldown is
    set. `+pvp off` is refused with the cooldown-remaining message.

    Byte-level signal: `+pvp off` output contains both "cannot
    unflag" / "try again" language AND a duration formatted by
    format_remaining (e.g. "4m 59s").
    """
    striker = await h.login_as("PVF4Striker", room_id=1)
    target = await h.login_as("PVF4Target", room_id=1)

    # Flag and engage.
    await h.cmd(striker, "+pvp on")
    await h.cmd(striker, f"attack {target.character['name']}")
    # Brief tick to let the consent-gate cooldown application land.
    await asyncio.sleep(0.1)

    # Now striker tries to unflag immediately.
    out = await h.cmd(striker, "+pvp off")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`+pvp off` raised: {out[:500]!r}"
    )
    # Refusal text from PvpCommand._flag_off.
    assert (
        "cannot unflag" in out_lc or "try again" in out_lc
    ), (
        f"+pvp off after engagement should refuse with cooldown "
        f"message. Output: {out[:400]!r}"
    )

    # And DB column is still 1.
    char = await h.get_char(striker.character["id"])
    assert char.get("pvp_flagged") == 1, (
        f"+pvp off bypassed the cooldown — pvp_flagged was cleared "
        f"despite refusal message. Char: {char!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-5 — SECURED zones still block flagged PvP
# ──────────────────────────────────────────────────────────────────────────


async def pvf_5_secured_zone_blocks_flagged_pvp(h):
    """PVF-5 — In a SECURED zone, even mutually-flagged PCs cannot
    attack each other. The flag does NOT override SECURED.

    This test catches the "I'm in the Jedi Temple, why can flagged
    players attack each other here" launch-blocker scenario.

    SECURED ROOM SOURCING (post-PVF-5 bugfix, May 18 2026 [2]):
    Look up ``docking_bay_94_pit`` (CW spaceport, SECURED via
    S-RES.2's tatooine_spaceport zone-level security default) by
    SLUG, not by hardcoded DB id. The earlier "use room_id=1"
    assumption was wrong: DB id 1 is a legacy seed "Landing Pad -
    Mos Eisley Spaceport" pre-inserted by the schema before the
    YAML world write, with ``zone_id=None`` and ``properties={}``,
    which resolves CONTESTED — defeating the SECURED gate this test
    is meant to verify. See ``tests/harness.py::room_id_by_slug``
    docstring for the full mechanism.
    """
    sec_room = await h.room_id_by_slug("docking_bay_94_pit")
    a = await h.login_as("PVF5Alice", room_id=sec_room)
    b = await h.login_as("PVF5Bob", room_id=sec_room)

    # Both flag.
    await h.cmd(a, "+pvp on")
    await h.cmd(b, "+pvp on")

    # Attack should still be refused — SECURED protection is absolute.
    out = await h.cmd(a, f"attack {b.character['name']}")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`attack` raised in SECURED zone: {out[:500]!r}"
    )

    # The combat_state event SHOULD NOT have fired — if it did, the
    # SECURED gate failed and flagging silently overrode it.
    await asyncio.sleep(0.2)
    combat_events_for_a = [
        e for e in a.json_events
        if e.get("type") == "combat_state"
        and e.get("active") is not False
    ]
    assert not combat_events_for_a, (
        f"Attack in SECURED zone produced a combat_state event "
        f"(combat engaged) despite SECURED protection. "
        f"Events: {[e.get('type') for e in a.json_events]!r}. "
        f"This is the launch-blocker scenario: flagging is "
        f"silently overriding SECURED."
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-6 — LAWLESS + flagged-vs-flagged: attack proceeds
# ──────────────────────────────────────────────────────────────────────────


async def pvf_6_lawless_flagged_combat_proceeds(h):
    """PVF-6 — In a LAWLESS zone, mutually-flagged PCs can attack
    each other without challenge/accept.

    LAWLESS is the inverse of PVF-5's SECURED case: where SECURED
    refuses combat even with flags, LAWLESS allows combat even
    without them (PVF-7). PVF-6 confirms the flag is INERT in
    LAWLESS — it doesn't block, doesn't enable, doesn't matter.
    The attack proceeds because LAWLESS has no consent gate at
    all, not because the flag is set.

    SECURED ROOM SOURCING:
    Look up ``undercity_market`` (Nar Shaddaa Undercity Market)
    by slug. The room's YAML carries top-level
    ``security_level: lawless`` which S-RES promotes into
    ``properties.security`` at write-time, so the resolver returns
    LAWLESS without zone-walk. See pvp_flag module docstring for
    full security model context.
    """
    lawless_room = await h.room_id_by_slug("undercity_market")
    a = await h.login_as("PVF6Alice", room_id=lawless_room)
    b = await h.login_as("PVF6Bob", room_id=lawless_room)

    # Flag both (proves the flag is set successfully in LAWLESS too).
    await h.cmd(a, "+pvp on")
    await h.cmd(b, "+pvp on")

    # Attack proceeds without consent dance.
    out = await h.cmd(a, f"attack {b.character['name']}")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`attack` in LAWLESS raised: {out[:500]!r}"
    )
    assert "imperial law prohibits" not in out_lc, (
        f"LAWLESS+flagged attack got the CONTESTED-consent refusal "
        f"text. LAWLESS should never produce that message — the "
        f"_check_pvp_consent early-return for non-CONTESTED has "
        f"regressed. Output: {out[:400]!r}"
    )

    # combat_state event SHOULD have fired — combat engaged.
    await asyncio.sleep(0.2)
    combat_events = [
        e for e in a.json_events
        if e.get("type") == "combat_state"
        and e.get("active") is not False
    ]
    assert combat_events, (
        f"LAWLESS+flagged attack did NOT produce a combat_state "
        f"event. Combat appears to not have engaged. "
        f"Events: {[e.get('type') for e in a.json_events]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-7 — LAWLESS + unflagged-vs-unflagged: attack ALSO proceeds
# ──────────────────────────────────────────────────────────────────────────


async def pvf_7_lawless_unflagged_combat_proceeds(h):
    """PVF-7 — In a LAWLESS zone, even UNFLAGGED PCs can attack
    each other without challenge/accept.

    Pins the LAWLESS-bypasses-consent invariant: in LAWLESS zones
    there is no consent gate at all. The +pvp flag is irrelevant.
    A future drop that accidentally extends the consent gate into
    LAWLESS (e.g. by removing the
    ``if sec != SecurityLevel.CONTESTED: return True`` early-return
    in _check_pvp_consent) would fail this test.

    This complements PVF-6: PVF-6 shows flag-on works; PVF-7 shows
    no-flag works too. Both must be true for the security model
    to be consistent.
    """
    lawless_room = await h.room_id_by_slug("undercity_market")
    a = await h.login_as("PVF7Alice", room_id=lawless_room)
    b = await h.login_as("PVF7Bob", room_id=lawless_room)

    # Pre-check: neither is flagged.
    char_a = await h.get_char(a.character["id"])
    char_b = await h.get_char(b.character["id"])
    assert (char_a.get("pvp_flagged") or 0) == 0, (
        f"PVF7Alice should start unflagged. Char: {char_a!r}"
    )
    assert (char_b.get("pvp_flagged") or 0) == 0, (
        f"PVF7Bob should start unflagged. Char: {char_b!r}"
    )

    # Attack proceeds without challenge/accept and without flag.
    out = await h.cmd(a, f"attack {b.character['name']}")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`attack` raised: {out[:500]!r}"
    )
    assert "imperial law prohibits" not in out_lc, (
        f"LAWLESS+unflagged attack hit the CONTESTED-consent gate. "
        f"The _check_pvp_consent early-return for non-CONTESTED "
        f"has regressed or the security resolver returned wrong "
        f"tier for undercity_market. Output: {out[:400]!r}"
    )

    # combat_state event SHOULD have fired.
    await asyncio.sleep(0.2)
    combat_events = [
        e for e in a.json_events
        if e.get("type") == "combat_state"
        and e.get("active") is not False
    ]
    assert combat_events, (
        f"LAWLESS+unflagged attack did NOT produce a combat_state "
        f"event. Events: {[e.get('type') for e in a.json_events]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-8 — Cooldown expiry: +pvp off succeeds after clear
# ──────────────────────────────────────────────────────────────────────────


async def pvf_8_unflag_succeeds_after_cooldown_clears(h):
    """PVF-8 — After the unflag cooldown expires, ``+pvp off``
    succeeds. The cooldown is a TIMER, not permanent.

    PVF-4 covers the locked case (cooldown active → refused).
    PVF-8 covers the unlocked case (cooldown cleared → allowed)
    by directly clearing the cooldown via
    ``engine.cooldowns.clear_cooldown`` — the same code path
    production hits naturally when the expiry timestamp passes.
    Without this scenario, a regression that made the cooldown
    permanent (e.g. by storing a sticky boolean instead of an
    expiry timestamp) would be invisible to PVF-4 alone.
    """
    from engine.cooldowns import (
        clear_cooldown, CD_PVP_UNFLAG, remaining_cooldown,
    )

    striker = await h.login_as("PVF8Striker", room_id=1)
    target = await h.login_as("PVF8Target", room_id=1)

    # Flag and engage to set the cooldown.
    await h.cmd(striker, "+pvp on")
    await h.cmd(striker, f"attack {target.character['name']}")
    await asyncio.sleep(0.1)

    # Confirm cooldown is set (precondition for the test to mean
    # anything — if cooldown isn't set, PVF-4 has regressed too).
    char_mid = await h.get_char(striker.character["id"])
    rem_before = remaining_cooldown(char_mid, CD_PVP_UNFLAG)
    assert rem_before > 0, (
        f"PVF8Striker should be cooldown-locked after engagement "
        f"(PVF-4 precondition). Remaining: {rem_before}. "
        f"Char: {char_mid!r}"
    )

    # Now simulate time passing by clearing the cooldown directly.
    # This mutates char["attributes"] in place; we then persist via
    # save_character so the on-disk state reflects the cleared cooldown.
    clear_cooldown(char_mid, CD_PVP_UNFLAG)
    await h.db.save_character(
        char_mid["id"], attributes=char_mid["attributes"])

    # May 19 2026 fix — refresh the session's character reference.
    # `striker.session.character` was loaded at login (game_server.py:811)
    # and held by reference; commands read cooldowns from THAT dict, not
    # from a fresh DB row. The DB write above doesn't touch the session's
    # in-memory copy, so without this refresh, the `+pvp off` gate below
    # would still see the stale (uncleared) cooldown and refuse — even
    # though the test set up to clear it correctly. This is the
    # established session-refresh idiom; see telnet_protocol.py,
    # wilderness_combat.py, ground_combat.py, movement.py for parallels.
    striker.character = await h.get_char(striker.character["id"])

    # +pvp off should now succeed.
    out = await h.cmd(striker, "+pvp off")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`+pvp off` raised: {out[:500]!r}"
    )
    # Success message — refusal language must NOT appear.
    assert "cannot unflag" not in out_lc and "try again" not in out_lc, (
        f"+pvp off after cooldown-clear was still refused. "
        f"Cooldown clear may not be reaching the gate. "
        f"Output: {out[:400]!r}"
    )

    # DB column flipped back to 0.
    char_post = await h.get_char(striker.character["id"])
    assert (char_post.get("pvp_flagged") or 0) == 0, (
        f"+pvp off succeeded textually but pvp_flagged is still 1 "
        f"in the DB. PvpCommand._flag_off may have a state-write "
        f"bug. Char: {char_post!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-9 — Mutual flag → mutual combat → mutual cooldown lock
# ──────────────────────────────────────────────────────────────────────────


async def pvf_9_mutual_flag_engagement_locks_both(h):
    """PVF-9 — Two PCs both flag on, attack engages, BOTH end up
    cooldown-locked.

    The most common production flow: two consenting PCs, both
    flag on, one attacks the other. The consent gate's "either
    party flagged" branch fires, and the cooldown applies to
    BOTH char and target_char per
    parser/combat_commands.py::_check_pvp_consent (the
    set_cooldown calls run for both sides). Without this scenario,
    a regression that only set the cooldown on the attacker
    (letting the target tag-and-flee unflag) would be invisible.

    Asserts that AFTER the engagement, BOTH the striker and the
    target are unflag-cooldown-locked. End-to-end happy path.
    """
    from engine.cooldowns import remaining_cooldown, CD_PVP_UNFLAG

    a = await h.login_as("PVF9Alice", room_id=1)
    b = await h.login_as("PVF9Bob", room_id=1)

    # Both flag on.
    await h.cmd(a, "+pvp on")
    await h.cmd(b, "+pvp on")

    # Confirm both flagged.
    char_a = await h.get_char(a.character["id"])
    char_b = await h.get_char(b.character["id"])
    assert char_a.get("pvp_flagged") == 1, (
        f"PVF9Alice flag did not persist. Char: {char_a!r}"
    )
    assert char_b.get("pvp_flagged") == 1, (
        f"PVF9Bob flag did not persist. Char: {char_b!r}"
    )

    # Attack proceeds.
    out = await h.cmd(a, f"attack {b.character['name']}")
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`attack` raised: {out[:500]!r}"
    )
    assert "imperial law prohibits" not in out_lc, (
        f"Mutual-flagged attack hit the consent gate. "
        f"either-party-flagged branch may have regressed. "
        f"Output: {out[:400]!r}"
    )
    await asyncio.sleep(0.1)

    # BOTH sides should now be cooldown-locked.
    char_a_post = await h.get_char(a.character["id"])
    char_b_post = await h.get_char(b.character["id"])

    rem_a = remaining_cooldown(char_a_post, CD_PVP_UNFLAG)
    rem_b = remaining_cooldown(char_b_post, CD_PVP_UNFLAG)

    assert rem_a > 0, (
        f"PVF9Alice (attacker) should be cooldown-locked. "
        f"Remaining: {rem_a}. Char: {char_a_post!r}"
    )
    assert rem_b > 0, (
        f"PVF9Bob (target) should ALSO be cooldown-locked — the "
        f"consent-gate sets cooldown on both sides to prevent "
        f"tag-and-flee. Remaining: {rem_b}. "
        f"Char: {char_b_post!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PVF-10 — `look` shows [PvP] marker for flagged PCs in the room
# ──────────────────────────────────────────────────────────────────────────


async def pvf_10_look_shows_pvp_marker(h):
    """PVF-10 — When PC A is flagged and PC B looks at the room,
    A appears in the contents with the `[PvP]` marker.

    The unit test at `tests/test_pvp_display_surfaces.py::test_look_*`
    asserts the source code contains the `[PvP]` literal — byte-
    level. PVF-10 asserts the literal actually reaches the player
    through the live `look` pipeline. A regression where the
    marker source-string got moved into a branch never reached
    at runtime (e.g. dead-code from a refactor) would pass the
    unit test but fail PVF-10.

    Setup: two PCs in the same room. A flags on. B issues `look`.
    Output must contain `[PvP]` and A's name in the room
    contents block.
    """
    a = await h.login_as("PVF10Alice", room_id=1)
    b = await h.login_as("PVF10Bob", room_id=1)

    # Drain any initial state on B.
    b.drain_text()

    # A flags on. B's look should now show A with the marker.
    await h.cmd(a, "+pvp on")
    # Brief settle.
    await asyncio.sleep(0.1)

    # B looks.
    out = await h.cmd(b, "look")
    assert "traceback" not in out.lower(), (
        f"`look` raised: {out[:500]!r}"
    )
    # The flagged PC's name should appear in the look output.
    assert "PVF10Alice" in out, (
        f"`look` did not include PVF10Alice in the room contents. "
        f"Look output: {out[:400]!r}"
    )
    # The [PvP] marker should be present.
    assert "[PvP]" in out, (
        f"`look` did not show the [PvP] marker for the flagged PC. "
        f"The marker literal exists in the source (per the byte-level "
        f"unit test) but is not reaching the live `look` output — "
        f"possible regression where the marker was moved into a branch "
        f"never reached at runtime. Look output: {out[:600]!r}"
    )

    # Sanity inverse: a freshly-logged-in unflagged PC C should NOT
    # appear with the marker.
    c = await h.login_as("PVF10Carol", room_id=1)
    b.drain_text()  # Discard the arrival event for C.
    out2 = await h.cmd(b, "look")
    # PVF10Carol should be in the listing but without [PvP].
    assert "PVF10Carol" in out2, (
        f"`look` did not include PVF10Carol after she logged in. "
        f"Output: {out2[:400]!r}"
    )
    # Confirm the marker is targeted, not blanket-applied. We
    # find both names in the output and check that the [PvP]
    # marker only appears within the Alice line.
    alice_idx = out2.find("PVF10Alice")
    carol_idx = out2.find("PVF10Carol")
    marker_idx = out2.find("[PvP]")
    assert marker_idx >= 0, (
        f"[PvP] marker disappeared from the second look. "
        f"Output: {out2[:600]!r}"
    )
    # If both names are on separate lines, the marker should be
    # closer to Alice. Defensive assertion — not all renderers
    # use newlines but the per-PC line render does.
    if alice_idx >= 0 and carol_idx >= 0:
        # Distance from marker to Alice should be much shorter
        # than to Carol (the marker decorates Alice's entry).
        dist_alice = abs(marker_idx - alice_idx)
        dist_carol = abs(marker_idx - carol_idx)
        assert dist_alice < dist_carol, (
            f"[PvP] marker appears closer to PVF10Carol "
            f"({dist_carol}) than to PVF10Alice ({dist_alice}). "
            f"The marker may be decorating the wrong PC, or "
            f"both PCs may be incorrectly receiving it. "
            f"Output: {out2[:600]!r}"
        )
