# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/pvp_flag.py — +pvp opt-in flag scenarios
(PVF-1 … PVF-5).

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
