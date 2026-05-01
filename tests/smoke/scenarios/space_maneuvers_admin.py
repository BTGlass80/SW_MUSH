# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/space_maneuvers_admin.py — Space Layers D + F:
maneuvers (S15-S16), comms (S21-S22), admin (S28).

Per design §6.5.

These are quick-fire scenarios — each one drives a single command
and checks it doesn't blow up. Most are pilot-only and need a
ship in space.
"""
from __future__ import annotations

import asyncio
import json

from tests.smoke.scenarios.space_boarding import _get_target_ship
from tests.smoke.scenarios.space_flight import _board_and_pilot


async def s15_defensive_maneuvers(h):
    """S15 — All five defensive maneuvers (evade/jink/barrelroll/loop/slip)
    run cleanly from the pilot seat in space.

    Each one is a one-action maneuver with no target. We don't
    assert on dice outcomes — just that the command path runs.
    """
    ship, dock_room, _ = await _get_target_ship(h)
    target_token = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S15Maneuver", target_token, dock_room)
    await h.cmd(s, "launch")

    for cmd in ["evade", "jink", "barrelroll", "loop", "slip"]:
        out = await h.cmd(s, cmd)
        assert "traceback" not in out.lower(), (
            f"`{cmd}` raised: {out[:500]!r}"
        )
        # Each maneuver should produce some output (success or
        # failure narration).
        assert out and out.strip(), (
            f"`{cmd}` produced no output"
        )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s21_hail_command_runs(h):
    """S21 — `hail <target>` runs without raising.

    With no ship to hail (empty zone), it should produce a
    "no such target" or similar friendly error, not blow up.
    """
    ship, dock_room, _ = await _get_target_ship(h)
    target_token = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S21Hailer", target_token, dock_room)
    await h.cmd(s, "launch")

    out = await h.cmd(s, "hail ghost_ship")
    assert "traceback" not in out.lower(), (
        f"hail raised: {out[:500]!r}"
    )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s22_comms_command_runs(h):
    """S22 — `comms <message>` (open broadcast) runs without raising."""
    ship, dock_room, _ = await _get_target_ship(h)
    target_token = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S22Comms", target_token, dock_room)
    await h.cmd(s, "launch")

    out = await h.cmd(s, "comms anyone listening?")
    assert "traceback" not in out.lower(), (
        f"comms raised: {out[:500]!r}"
    )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s23_npc_traffic_visible_on_scan(h):
    """S23 — NPC space traffic is visible on a scan.

    The npc_space_traffic engine should produce some contacts in the
    Tatooine orbit zone after a few ticks. We don't fire ticks
    explicitly (advance_ticks lands in a future drop), but the seed
    may already include some traffic. If no traffic exists at scan
    time, that's a finding worth surfacing — but we mark this
    scenario tolerant to empty results.
    """
    ship, dock_room, _ = await _get_target_ship(h)
    target_token = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S23TrafficSpotter", target_token, dock_room)
    await h.cmd(s, "launch")
    out = await h.cmd(s, "scan")

    assert "traceback" not in out.lower(), (
        f"scan raised: {out[:500]!r}"
    )
    # Soft assertion: the scan response should be structured. Empty
    # zones produce "No other ships detected" or similar; populated
    # zones list specific contacts. Both are acceptable.

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s28_shipname_displays(h):
    """S28 — `shipname` (no args) displays the current ship name.

    Cheap admin command — exercises the ship-name resolver path.
    Renaming a ship typically requires ownership; we don't actually
    rename, just query.
    """
    ship, dock_room, _ = await _get_target_ship(h)
    target_token = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S28Namer", target_token, dock_room)

    out = await h.cmd(s, "shipname")
    assert "traceback" not in out.lower(), (
        f"shipname raised: {out[:500]!r}"
    )
    # Output should reference the ship name in some form.
    assert ship["name"].lower() in out.lower() or "ship" in out.lower() \
           or "usage" in out.lower(), (
        f"shipname output unexpected: {out[:300]!r}"
    )

    await h.cmd(s, "vacate")
