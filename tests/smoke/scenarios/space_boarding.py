# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/space_boarding.py — Space Layer A: boarding & crew (S1-S5).

Per design §6.5.

Anchored on the GCW seed which produces 7 ships at boot. Ship #1 is
'Rusty Mynock' (yt_1300) docked in Docking Bay 94 - Pit Floor (room 5).
PC spawns in room 5 to be in the same room as the ship.

These scenarios validate the spine of space gameplay:
  - board (does the bridge load)
  - station seats (pilot/gunner/copilot/engineer/navigator/sensors/commander)
  - vacate (release station)
  - disembark (leave ship)
  - multi-PC crew coordination
"""
from __future__ import annotations

import asyncio
import json


async def _get_target_ship(h):
    """Locate a docked ship suitable for smoke scenarios.

    Returns (ship_dict, dock_room_id, bridge_room_id) or fails.
    Picks the first ship currently docked. Owner-aware scenarios
    can claim ownership separately.
    """
    rows = await h.db.fetchall(
        "SELECT * FROM ships WHERE docked_at IS NOT NULL "
        "ORDER BY id LIMIT 1"
    )
    assert rows, (
        "No ships found in the spawned world. "
        "Space scenarios require at least one docked ship."
    )
    ship = dict(rows[0])
    return ship, int(ship["docked_at"]), int(ship["bridge_room_id"])


async def s1_board_ship_and_look_bridge(h):
    """S1 — Board a docked ship and verify the bridge loads.

    `board <name>` should:
      - move the character into the ship's bridge_room_id
      - emit a `look` of the bridge (shows ship interior)
      - update the character row

    This is the spine — every other space scenario depends on `board`.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    s = await h.login_as("S1Boarder", room_id=dock_room)
    char_id = s.character["id"]

    # First word of the ship name as the search token.
    target_token = ship["name"].split()[0].lower()
    out = await h.cmd(s, f"board {target_token}")

    assert out and out.strip(), "board produced no output"
    assert "traceback" not in out.lower(), (
        f"board raised: {out[:500]!r}"
    )

    # Character should now be in the bridge.
    s.character = await h.get_char(char_id)
    actual_room = int(s.character["room_id"])
    assert actual_room == bridge_room, (
        f"After board, character is in room {actual_room!r} "
        f"(expected bridge_room {bridge_room!r}). "
        f"Ship: {ship['name']!r}, Output: {out[:300]!r}"
    )


async def s2_pilot_seat(h):
    """S2 — `pilot` claims the pilot seat on the boarded ship.

    Asserts:
      - ``pilot`` produces a success acknowledgment
      - ship.crew JSON has ``pilot`` set to the character's ID
      - cleanup: vacate before exit so downstream scenarios in the
        same class start with a clean ship

    The cleanup matters because the class-scoped harness fixture
    means ships persist between scenarios. Failing to vacate left
    pilot=<S2_char_id> set, which made S3's "claim pilot" silently
    refuse with "seat is occupied" — a bug found during SH4 dev.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    s = await h.login_as("S2Pilot", room_id=dock_room)
    char_id = s.character["id"]

    target_token = ship["name"].split()[0].lower()
    await h.cmd(s, f"board {target_token}")
    out = await h.cmd(s, "pilot")

    assert "traceback" not in out.lower(), (
        f"pilot raised: {out[:500]!r}"
    )
    # Genuine success: "You take the pilot seat" or similar.
    out_lc = out.lower()
    assert "pilot" in out_lc and (
        "take" in out_lc or "controls" in out_lc or "seat" in out_lc
    ) and "occupied" not in out_lc, (
        f"pilot did not claim the seat. Output: {out[:300]!r}"
    )

    # Reload the ship row and check crew.pilot.
    rows = await h.db.fetchall(
        "SELECT crew FROM ships WHERE id = ?", (ship["id"],)
    )
    crew = json.loads(rows[0]["crew"] or "{}")
    assert crew.get("pilot") == char_id, (
        f"Ship crew.pilot is {crew.get('pilot')!r}, "
        f"expected {char_id!r}. Output: {out[:300]!r}"
    )

    # Cleanup: vacate so the next scenario in this class starts clean.
    await h.cmd(s, "vacate")


async def s3_all_crew_stations_cycle(h):
    """S3 — Cycle through every crew station and back via vacate.

    Sequence: board → pilot → vacate → gunner → vacate → copilot →
    vacate → engineer → vacate → navigator → vacate → sensors →
    vacate → commander → vacate.

    Asserts each station claim *genuinely succeeds* (the seat row
    in crew JSON points to this character) and each vacate
    releases. Naive "no-traceback" assertions are insufficient
    because refused commands return cleanly — see the S4 bug
    discovery during SH4 development.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    s = await h.login_as("S3Cycler", room_id=dock_room)
    char_id = s.character["id"]

    target_token = ship["name"].split()[0].lower()
    await h.cmd(s, f"board {target_token}")

    # Per-station expected key in crew JSON. gunner is special —
    # it stores in crew.gunner_stations[idx] rather than
    # crew.gunner directly. We check that this char_id appears
    # somewhere in crew.values for gunner.
    single_seat_stations = ["pilot", "copilot", "engineer",
                            "navigator", "sensors", "commander"]

    for station in single_seat_stations:
        out_take = await h.cmd(s, station)
        assert "traceback" not in out_take.lower(), (
            f"`{station}` raised: {out_take[:500]!r}"
        )
        # Verify the seat is actually claimed by this character.
        rows = await h.db.fetchall(
            "SELECT crew FROM ships WHERE id = ?", (ship["id"],)
        )
        crew = json.loads(rows[0]["crew"] or "{}")
        assert crew.get(station) == char_id, (
            f"After `{station}`, ship crew.{station} is "
            f"{crew.get(station)!r}, expected {char_id!r}. "
            f"Was the seat already occupied? Output: {out_take[:300]!r}"
        )
        out_vacate = await h.cmd(s, "vacate")
        assert "traceback" not in out_vacate.lower(), (
            f"`vacate` after `{station}` raised: {out_vacate[:500]!r}"
        )
        # Verify the seat is genuinely released.
        rows = await h.db.fetchall(
            "SELECT crew FROM ships WHERE id = ?", (ship["id"],)
        )
        crew = json.loads(rows[0]["crew"] or "{}")
        assert crew.get(station) != char_id, (
            f"After vacate from `{station}`, char_id still occupies seat. "
            f"crew={crew!r}"
        )

    # gunner has a different shape; check it last.
    out_gunner = await h.cmd(s, "gunner")
    assert "traceback" not in out_gunner.lower(), (
        f"`gunner` raised: {out_gunner[:500]!r}"
    )
    rows = await h.db.fetchall(
        "SELECT crew FROM ships WHERE id = ?", (ship["id"],)
    )
    crew = json.loads(rows[0]["crew"] or "{}")
    gunner_stations = crew.get("gunner_stations", {})
    assert char_id in gunner_stations.values(), (
        f"`gunner` did not claim a weapon station. "
        f"gunner_stations={gunner_stations!r}, char_id={char_id!r}"
    )
    await h.cmd(s, "vacate")


async def s4_multi_pc_crew_coordination(h):
    """S4 — Two PCs aboard the same ship — one pilot, one gunner.

    Asserts both seats are claimed in the ship.crew JSON. Catches
    the bug class where station claims clobber each other due to
    JSON-write race.

    Cleanup: both PCs vacate their stations before exit so the ship
    starts clean for any downstream scenario in the class.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    s_pilot = await h.login_as("S4Pilot", room_id=dock_room)
    s_gunner = await h.login_as("S4Gunner", room_id=dock_room)
    pilot_id = s_pilot.character["id"]
    gunner_id = s_gunner.character["id"]

    target_token = ship["name"].split()[0].lower()
    await h.cmd(s_pilot, f"board {target_token}")
    out_pilot = await h.cmd(s_pilot, "pilot")
    assert "occupied" not in out_pilot.lower(), (
        f"Pilot seat already occupied at S4 start (cleanup leak from "
        f"earlier scenario). Output: {out_pilot[:300]!r}"
    )
    await h.cmd(s_gunner, f"board {target_token}")
    await h.cmd(s_gunner, "gunner")

    rows = await h.db.fetchall(
        "SELECT crew FROM ships WHERE id = ?", (ship["id"],)
    )
    crew = json.loads(rows[0]["crew"] or "{}")
    assert crew.get("pilot") == pilot_id, (
        f"Ship crew.pilot expected {pilot_id!r}, got {crew.get('pilot')!r}. "
        f"Full crew: {crew!r}"
    )
    # gunner stored in crew.gunner_stations[idx].
    gunner_stations = crew.get("gunner_stations", {})
    assert gunner_id in gunner_stations.values(), (
        f"Gunner char_id {gunner_id!r} not in gunner_stations. "
        f"gunner_stations={gunner_stations!r}, full crew: {crew!r}"
    )

    # Cleanup.
    await h.cmd(s_pilot, "vacate")
    await h.cmd(s_gunner, "vacate")


async def s5_disembark_returns_to_dock(h):
    """S5 — `disembark` returns the character to the docking bay.

    The reverse of S1. Catches the bug pattern where disembark
    leaves the character stranded inside the ship's interior or
    teleports them to room 0.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    s = await h.login_as("S5Disembarker", room_id=dock_room)
    char_id = s.character["id"]

    target_token = ship["name"].split()[0].lower()
    await h.cmd(s, f"board {target_token}")
    s.character = await h.get_char(char_id)
    assert int(s.character["room_id"]) == bridge_room, "Setup: board failed"

    out = await h.cmd(s, "disembark")
    assert "traceback" not in out.lower(), (
        f"disembark raised: {out[:500]!r}"
    )

    s.character = await h.get_char(char_id)
    actual = int(s.character["room_id"])
    assert actual == dock_room, (
        f"After disembark, character in room {actual!r} "
        f"(expected dock_room {dock_room!r}). "
        f"Output: {out[:300]!r}"
    )
