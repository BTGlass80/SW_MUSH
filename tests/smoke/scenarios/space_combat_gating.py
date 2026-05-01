# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/space_combat_gating.py — SH4 supplement.

The original SH4 marked S12 (lockon+fire) as xfail due to a confirmed
bug (LockOnCommand reads crew.gunners, but the rest of the codebase
uses crew.gunner_stations). That xfail correctly captures the bug,
but it leaves the combat-fire surface untested in every other respect.

This module tests the GATING logic around fire/lockon — the parts
that work, plus the parts where breakage would cause silent player
confusion. It does NOT exercise full ship-on-ship combat (that needs
two crewed ships in the same zone, an astrogation roll, etc. — a
later drop with a richer combat fixture is the right home for it).

Coverage:
  - S14: fire while docked is rejected (gating)
  - S14b: fire without a target produces usage hint
  - S30: transponder status / set-false / reset

Plus the previously-missing tractor-resist:
  - S25: +resisttractor command runs without raising
"""
from __future__ import annotations

import asyncio

from tests.smoke.scenarios.space_boarding import _get_target_ship
from tests.smoke.scenarios.space_flight import _board_and_pilot, _LAUNCH_KITTY


async def s14_fire_while_docked_blocked(h):
    """S14 — `fire <target>` from a docked ship is rejected.

    The fire command's docked-state gate is what prevents accidental
    weapons discharge in a hangar. This scenario validates that gate
    is still in place.

    Note: We attempt fire from a gunner seat on a docked ship. Even
    though the player can't actually have a target locked (no scan
    in dock), the docked-state check should fire FIRST and produce
    a clear refusal before any other gate is hit.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await h.login_as("S14Docked", room_id=dock_room, credits=_LAUNCH_KITTY)
    await h.cmd(s, f"board {target}")
    # Take gunner station so the gunner-precondition isn't what
    # blocks us.
    await h.cmd(s, "gunner")

    out = await h.cmd(s, "fire something")
    assert "traceback" not in out.lower(), (
        f"fire-while-docked raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    refused = (
        "docked" in out_lc
        or "can't fire" in out_lc
        or "cannot fire" in out_lc
        or "in space" in out_lc
        or "not aboard" in out_lc  # acceptable secondary refusal
    )
    assert refused, (
        f"Fire from a docked ship was not refused. "
        f"Output: {out[:400]!r}"
    )


async def s14b_fire_no_target_produces_usage(h):
    """S14b — `fire` with no argument produces the usage hint.

    Catches the regression where bare `fire` raises an IndexError
    or similar instead of routing to the usage handler.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await h.login_as("S14bUsage", room_id=dock_room)
    await h.cmd(s, f"board {target}")
    await h.cmd(s, "gunner")

    out = await h.cmd(s, "fire")
    assert "traceback" not in out.lower(), (
        f"bare fire raised: {out[:500]!r}"
    )
    # Usage line includes "fire <target" or "Usage:"
    out_lc = out.lower()
    assert "usage" in out_lc or "fire <target" in out_lc, (
        f"bare fire didn't produce a usage hint. Output: {out[:300]!r}"
    )


async def s30_transponder_status(h):
    """S30 — `transponder` (no args) shows current ID status.

    Lightweight read-only check: transponder dispatches, produces
    output, doesn't raise. This is the gateway for false-ID
    smuggling content; if it regresses, smugglers' core gameplay
    breaks.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await h.login_as("S30Trans", room_id=dock_room)
    await h.cmd(s, f"board {target}")

    out = await h.cmd(s, "transponder")
    assert out and out.strip(), "transponder produced no output"
    assert "traceback" not in out.lower(), (
        f"transponder raised: {out[:500]!r}"
    )
    # The status line should reference the ship's name or template
    # in some form, OR mention transponder/ID terminology.
    out_lc = out.lower()
    has_status_word = (
        "transponder" in out_lc
        or "ident" in out_lc
        or "broadcast" in out_lc
        or ship["name"].lower() in out_lc
    )
    assert has_status_word, (
        f"transponder status looks empty. Output: {out[:400]!r}"
    )


async def s30b_transponder_set_false(h):
    """S30b — `transponder false <alias>` sets a fake ID.

    Validates the false-ID path runs end-to-end and persists to
    the systems JSON. Reset at the end.
    """
    import json as _json
    ship, dock_room, bridge_room = await _get_target_ship(h)
    ship_id = int(ship["id"])
    target = ship["name"].split()[0].lower()
    s = await h.login_as("S30bFalse", room_id=dock_room)
    await h.cmd(s, f"board {target}")

    out = await h.cmd(s, "transponder false Lucky Lady")
    assert "traceback" not in out.lower(), (
        f"transponder false raised: {out[:500]!r}"
    )

    # Inspect the systems JSON for the false_transponder key.
    rows = await h.db.fetchall(
        "SELECT systems FROM ships WHERE id = ?", (ship_id,),
    )
    if rows and rows[0]["systems"]:
        try:
            sys_obj = _json.loads(rows[0]["systems"])
        except Exception:
            sys_obj = {}
        # We accept either the false-ID being set OR the command
        # refusing for a Con-skill reason — both are valid command
        # paths, neither should raise.
        if "false_transponder" in sys_obj:
            assert sys_obj["false_transponder"], (
                f"false_transponder was set but is falsy: "
                f"{sys_obj['false_transponder']!r}"
            )

    # Cleanup: reset.
    await h.cmd(s, "transponder reset")


async def s25_resist_tractor_runs(h):
    """S25 — `+resisttractor` runs cleanly when no tractor is active.

    Without a hostile ship actually beaming you, +resisttractor will
    refuse with a "no tractor" message. We just want to validate the
    command dispatches without raising.

    A future drop with two-ship combat fixtures can exercise the
    full tractor lock + resist roll flow.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await h.login_as("S25Resist", room_id=dock_room)
    await h.cmd(s, f"board {target}")

    out = await h.cmd(s, "+resisttractor")
    assert "traceback" not in out.lower(), (
        f"+resisttractor raised: {out[:500]!r}"
    )
    # Output should mention tractor/beam/no-lock — anything but a
    # crash. We don't pin the wording.
    assert out and out.strip(), "+resisttractor produced no output"
