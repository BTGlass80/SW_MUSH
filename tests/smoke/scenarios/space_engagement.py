# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/space_engagement.py — Space Layer C: sensors & engagement (S11-S13).

Per design §6.5.

These scenarios exercise the offensive half of space combat: scan,
deepscan, lockon, fire. Expect bugs here — this is the densest part
of the 6,356-line space surface.

Layer C scenarios use a ship that's been launched into space. The
target for lockon/fire is constructed via NPC space traffic (the
GCW seed should produce some) or, if absent, the scenario skips
with a clear marker.
"""
from __future__ import annotations

import asyncio
import json

from tests.smoke.scenarios.space_boarding import _get_target_ship
from tests.smoke.scenarios.space_flight import _board_and_pilot


async def s11_scan_and_deepscan(h):
    """S11 — `scan` and `+deepscan` produce sensor output without
    raising.

    `+deepscan` is the higher-detail variant. Both commands should
    work in space (not docked). We don't assert on specific contacts
    because the orbit zone may be empty when the scenario runs.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target_token = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S11Scanner", target_token, dock_room)
    await h.cmd(s, "launch")

    out_scan = await h.cmd(s, "scan")
    assert "traceback" not in out_scan.lower(), (
        f"scan raised: {out_scan[:500]!r}"
    )
    assert "scan" in out_scan.lower() or "sensor" in out_scan.lower() or \
           "contact" in out_scan.lower() or "no other" in out_scan.lower(), (
        f"scan output unexpected: {out_scan[:300]!r}"
    )

    out_deep = await h.cmd(s, "+deepscan")
    assert "traceback" not in out_deep.lower(), (
        f"+deepscan raised: {out_deep[:500]!r}"
    )
    # Either it produces deeper info, or it requires sensor skill —
    # both are valid.

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s12_lockon_requires_correct_gunner_field(h):
    """S12 — KNOWN BUG (xfail): a character properly seated at a
    gunner station via `gunner` cannot `lockon` because LockOnCommand
    reads ``crew.gunners`` (legacy field) instead of
    ``crew.gunner_stations`` (current field).

    REPRO confirmed during SH4 development:
      1. Character takes `gunner` station — `crew.gunner_stations`
         gets `{"0": <char_id>}` (correct).
      2. Character types `lockon <target>` — LockOnCommand checks
         `crew.gunners.contains(char_id)`, which is empty/missing
         after the auto-migration in `_get_crew`. Result: "You're not
         at a gunner station. Type 'gunner' first."

    Affected paths in parser/space_commands.py:
      - LockOnCommand (line ~2806)
      - DisembarkCommand (line ~684)
      - AssistCommand (line ~1031)

    Fix: replace ``crew.get("gunners", [])`` with
    ``list(crew.get("gunner_stations", {}).values())`` everywhere.

    This scenario is marked ``xfail`` in the pytest entry point so
    it documents the bug without blocking the smoke suite. When the
    fix lands, ``xfail`` flips to ``passed`` and we know the bug is
    closed.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target_token = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S12Lockon", target_token, dock_room)
    char_id = s.character["id"]

    await h.cmd(s, "launch")
    # Drop pilot and take gunner.
    await h.cmd(s, "vacate")
    out_gunner = await h.cmd(s, "gunner")
    assert "traceback" not in out_gunner.lower(), (
        f"gunner raised: {out_gunner[:500]!r}"
    )

    # Confirm gunner_stations got us:
    rows = await h.db.fetchall(
        "SELECT crew FROM ships WHERE id = ?", (ship["id"],)
    )
    crew = json.loads(rows[0]["crew"] or "{}")
    gunner_stations = crew.get("gunner_stations", {})
    assert char_id in gunner_stations.values(), (
        f"Setup failed: character did not claim a gunner station. "
        f"crew={crew!r}"
    )

    # Try lockon — should work, but currently DOESN'T due to the bug.
    out_lock = await h.cmd(s, "lockon ghost_target")
    out_lc = out_lock.lower()
    # If the bug is fixed, we'll see either "no ship" (good — got
    # past the gate) OR "out of range" or similar. If the bug is
    # still present, we see "you're not at a gunner station".
    assert "not at a gunner station" not in out_lc, (
        f"BUG STILL PRESENT: LockOnCommand rejects a properly-seated "
        f"gunner. The crew field-name drift between `gunners` and "
        f"`gunner_stations` needs to be fixed in "
        f"parser/space_commands.py LockOnCommand. "
        f"Output: {out_lock[:400]!r}"
    )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")


async def s13_shields_in_space(h):
    """S13 — `shields` works in space (re-tests S9 in a Layer-C
    context to validate the cross-layer integration).

    Shields can be raised, lowered, or queried; the command is
    valid in space and should produce structured output.
    """
    ship, dock_room, bridge_room = await _get_target_ship(h)
    target_token = ship["name"].split()[0].lower()
    s = await _board_and_pilot(h, "S13Shield", target_token, dock_room)
    await h.cmd(s, "launch")

    out = await h.cmd(s, "shields")
    assert "traceback" not in out.lower(), (
        f"shields raised: {out[:500]!r}"
    )
    assert "shield" in out.lower(), (
        f"shields output doesn't reference shields: {out[:300]!r}"
    )

    # Try shields up (a common subcommand).
    out_up = await h.cmd(s, "shields up")
    assert "traceback" not in out_up.lower(), (
        f"shields up raised: {out_up[:500]!r}"
    )

    # Cleanup.
    await h.cmd(s, "land")
    await h.cmd(s, "vacate")
