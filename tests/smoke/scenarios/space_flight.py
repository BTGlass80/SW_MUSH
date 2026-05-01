# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/space_flight.py — Space Layer B: launch & flight (S6-S10).

Per design §6.5.

Scenarios that exercise the launch → in-space → land state machine.
Requires successful Layer A (boarding & pilot seat) as a precondition,
which the scenarios set up themselves.

Each scenario uses a freshly-logged character and CLEANS UP at the
end (lands the ship if launched, vacates the pilot seat) so the
class-scoped harness ship state stays sane across scenarios.
"""
from __future__ import annotations

import asyncio
import json

from tests.smoke.scenarios.space_boarding import _get_target_ship


# Standard launch cost on a YT-1300 (speed 5): 50 + 5*10 = 100cr.
# We give every flight character enough to launch + land + spare.
_LAUNCH_KITTY = 5000


async def _board_and_pilot(h, name, ship_token, dock_room, credits=_LAUNCH_KITTY):
    """Helper: log in, board, take pilot seat. Returns the session."""
    s = await h.login_as(name, room_id=dock_room, credits=credits)
    await h.cmd(s, f"board {ship_token}")
    out = await h.cmd(s, "pilot")
    if "occupied" in out.lower():
        raise AssertionError(
            f"Pilot seat already occupied at scenario start. "
            f"Cleanup leak from earlier scenario? Output: {out[:200]!r}"
        )
    return s


async def s6_launch_from_dock(h):
    """S6 — `launch` on a docked ship transitions to in-space state.

    Asserts:
      - launch produces non-error output
      - ship.docked_at becomes NULL
      - the character's credits decreased (fuel paid)

    Cleanup: lands the ship before exit.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S6Launcher", target, dock_room)
    char_id = s.character["id"]
    pre_credits = (await h.get_char(char_id))["credits"]

    out = await h.cmd(s, "launch")
    assert "traceback" not in out.lower(), (
        f"launch raised: {out[:500]!r}"
    )

    rows = await h.db.fetchall(
        "SELECT docked_at FROM ships WHERE id = ?", (ship["id"],)
    )
    assert rows[0]["docked_at"] is None, (
        f"After launch, ship.docked_at is {rows[0]['docked_at']!r} "
        f"(expected NULL). Output: {out[:300]!r}"
    )

    post_credits = (await h.get_char(char_id))["credits"]
    assert post_credits < pre_credits, (
        f"Credits did not decrease on launch (no fuel cost?). "
        f"pre={pre_credits!r}, post={post_credits!r}"
    )

    # Cleanup — land back to leave ship docked for next scenario.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s7_land_at_destination(h):
    """S7 — `land` puts the ship back into a docked state.

    Asserts:
      - launch + land round-trips cleanly
      - ship.docked_at is set after land
      - docking fee was charged
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S7Lander", target, dock_room)
    char_id = s.character["id"]

    await h.cmd(s, "launch")
    pre_credits = (await h.get_char(char_id))["credits"]

    out = await h.cmd(s, "land")
    assert "traceback" not in out.lower(), (
        f"land raised: {out[:500]!r}"
    )

    rows = await h.db.fetchall(
        "SELECT docked_at FROM ships WHERE id = ?", (ship["id"],)
    )
    assert rows[0]["docked_at"] is not None, (
        f"After land, ship.docked_at is NULL. Output: {out[:300]!r}"
    )

    post_credits = (await h.get_char(char_id))["credits"]
    assert post_credits < pre_credits, (
        f"Docking fee not charged. pre={pre_credits!r}, post={post_credits!r}"
    )

    await h.cmd(s, "vacate")


async def s8_scan_in_space(h):
    """S8 — After launching, `scan` produces sensor output.

    Validates that the in-space sensor pipeline is wired:
      - scan command runs cleanly
      - output contains some scan-related content (range, contacts,
        empty-space message — anything but a traceback)

    Doesn't assert specific contacts because the orbit zone may have
    none, depending on traffic state.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S8Scanner", target, dock_room)

    await h.cmd(s, "launch")
    out = await h.cmd(s, "scan")
    assert out and out.strip(), "scan produced no output in space"
    assert "traceback" not in out.lower(), (
        f"scan raised: {out[:500]!r}"
    )
    # Some marker that this is a scan response — accept several
    # variants that scanning surfaces use.
    out_lc = out.lower()
    has_scan_marker = (
        "scan" in out_lc or "sensor" in out_lc or "contact" in out_lc
        or "range" in out_lc or "empty" in out_lc or "nothing" in out_lc
        or "no ships" in out_lc or "no contacts" in out_lc
    )
    assert has_scan_marker, (
        f"scan output doesn't look like a scan result. "
        f"Output: {out[:500]!r}"
    )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s9_shields_command_runs(h):
    """S9 — `shields` produces non-error output (status or toggle).

    Doesn't assert on specific shield state — just that the command
    is wired and doesn't blow up. Catches the bug class where a
    shield-state read accesses a missing systems key.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S9Shielder", target, dock_room)

    await h.cmd(s, "launch")
    out = await h.cmd(s, "shields")
    assert "traceback" not in out.lower(), (
        f"shields raised: {out[:500]!r}"
    )
    # Some shield-related substring should be present.
    assert "shield" in out.lower(), (
        f"shields output doesn't reference shields: {out[:300]!r}"
    )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s10_power_command_runs(h):
    """S10 — `power` shows or sets capacitor allocation without raising.

    Like S9, this just validates the command path is wired and
    doesn't blow up on a fresh ship's systems JSON.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S10Power", target, dock_room)

    await h.cmd(s, "launch")
    out = await h.cmd(s, "power")
    assert "traceback" not in out.lower(), (
        f"power raised: {out[:500]!r}"
    )
    # Should mention power/capacitor/energy somewhere.
    out_lc = out.lower()
    assert any(t in out_lc for t in ("power", "capacitor", "energy",
                                     "engine", "weapon")), (
        f"power output doesn't reference power systems: {out[:300]!r}"
    )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")
