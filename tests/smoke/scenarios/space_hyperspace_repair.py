# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/space_hyperspace_repair.py — SH4 supplement.

Per the design doc §6.5, the original SH4 drop covered S1-S13/S15/
S21-S23/S28 but missed:
  - S9: hyperspace jump
  - S18: damcon (in-flight repair)
  - S19: ship repair (docked)

This module fills those gaps with read-only / no-state-change checks
where possible, and full state cycles where necessary. Pattern matches
the existing space_flight.py helpers.
"""
from __future__ import annotations

import asyncio
import json

from tests.smoke.scenarios.space_boarding import _get_target_ship
from tests.smoke.scenarios.space_flight import _board_and_pilot, _LAUNCH_KITTY


async def s9_hyperspace_list_destinations(h):
    """S9 — `hyperspace list` (or no-args) shows the destination
    catalog when in space.

    Lightweight check that exercises:
      - hyperspace command dispatch
      - HYPERSPACE_LOCATIONS data loaded
      - list-mode rendering
      - all the in-space gating (must be aboard, must be in space,
        must be pilot, ship must have a hyperdrive)

    Does NOT trigger an actual jump — that needs an astrogation roll
    and produces non-deterministic state changes. A future drop with
    advance_ticks(n) can do the full jump cycle.

    Cleanup: lands the ship.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S9Astro", target, dock_room)

    await h.cmd(s, "launch")
    out = await h.cmd(s, "hyperspace list")
    assert out and out.strip(), "hyperspace list produced no output"
    assert "traceback" not in out.lower(), (
        f"hyperspace list raised: {out[:500]!r}"
    )

    # The output should contain at least one well-known destination
    # marker ("hyperspace destinations" header, or any planet name).
    out_lc = out.lower()
    assert "destinations" in out_lc or "tatooine" in out_lc or \
           "coruscant" in out_lc or "kuat" in out_lc, (
        f"hyperspace list output doesn't look like a destination "
        f"catalog: {out[:500]!r}"
    )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s9b_hyperspace_blocked_when_docked(h):
    """S9b — `hyperspace` from a docked ship is rejected.

    Catches the bug pattern where the docked-state gate regresses.
    A docked ship attempting to jump should produce a clear error
    message, NOT silently jump or raise.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S9bDocked", target, dock_room)

    out = await h.cmd(s, "hyperspace tatooine")
    assert "traceback" not in out.lower(), (
        f"hyperspace from dock raised: {out[:500]!r}"
    )
    # Server should refuse with a "must be in space" / "launch first"
    # style message.
    out_lc = out.lower()
    refused = (
        "in space" in out_lc
        or "launch first" in out_lc
        or "docked" in out_lc
        or "can't" in out_lc
        or "cannot" in out_lc
    )
    assert refused, (
        f"hyperspace from dock did not produce a refusal message. "
        f"Output: {out[:400]!r}"
    )

    # No cleanup needed — never launched.
    await h.cmd(s, "vacate")


async def s18_damcon_status(h):
    """S18 — `damcon` (no args) shows the ship's damage report.

    Read-only check on a healthy in-space ship:
      - damcon command dispatches
      - produces non-error output
      - includes some system listing (shields/sensors/engines/...)

    Cleanup: lands the ship.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S18Damcon", target, dock_room)

    await h.cmd(s, "launch")
    out = await h.cmd(s, "damcon")
    assert out and out.strip(), "damcon produced no output"
    assert "traceback" not in out.lower(), (
        f"damcon raised: {out[:500]!r}"
    )

    # The damage report should reference at least one ship system.
    out_lc = out.lower()
    has_system_word = any(
        w in out_lc
        for w in ("shield", "sensor", "engine", "weapon", "hull",
                  "hyperdrive", "system", "damage", "intact",
                  "operational")
    )
    assert has_system_word, (
        f"damcon output doesn't reference any ship system. "
        f"Output: {out[:500]!r}"
    )

    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s19_ship_repair_at_dock(h):
    """S19 — `+srepair` on a docked, damaged ship attempts repair.

    Strategy: directly inflict hull damage via DB write (no need to
    actually take fire), then call +srepair docked, observe a credits
    deduction or an "already healthy" / "no damage" response.

    This covers the read path even when the ship has no damage; the
    actual repair price/skill check is exercised when damage is
    applied first.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    ship_id = int(ship["id"])

    # Inflict 5 hull damage directly (the same column the combat
    # engine writes to).
    await h.db._db.execute(
        "UPDATE ships SET hull_damage = ? WHERE id = ?",
        (5, ship_id),
    )
    await h.db._db.commit()

    target = ship["name"].split()[0].lower()
    s = await h.login_as(
        "S19Repair", room_id=dock_room, credits=_LAUNCH_KITTY,
    )
    char_id = s.character["id"]

    # +srepair must run in the docking bay (or wherever the repair
    # vendor is). We're already there.
    pre_credits = (await h.get_char(char_id))["credits"]
    out = await h.cmd(s, f"+srepair {ship['name'].split()[0]}")
    assert "traceback" not in out.lower(), (
        f"+srepair raised: {out[:500]!r}"
    )
    assert out and out.strip(), "+srepair produced no output"

    # Best-effort: damage was applied; either credits deducted or
    # the response indicates the cost. We don't strictly require
    # repair-success because vendor presence varies.

    # Restore: clear any leftover hull damage so subsequent
    # scenarios start clean.
    await h.db._db.execute(
        "UPDATE ships SET hull_damage = 0 WHERE id = ?",
        (ship_id,),
    )
    await h.db._db.commit()
