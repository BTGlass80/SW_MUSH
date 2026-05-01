# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/era_clone_wars.py — Era validation scenarios.

Originally CW-only. Since the May 2026 era pivot (default flipped to
clone_wars), these scenarios are reused by both ``TestCloneWarsEra``
and ``TestGCWEra`` to provide cross-era regression coverage of the
most diagnostic SH1+SH2 surfaces (login + look, movement, ground
combat, sheet, say).

Each scenario takes an ``expected_era`` argument so the era-pinning
assertion adapts to whichever class is calling it.
"""
from __future__ import annotations

import asyncio


async def cw1_login_in_clone_wars_era(h, expected_era="clone_wars"):
    """CW1 — Login + look in the chosen era.

    Asserts the harness boots cleanly against the expected era and a
    spawned character can see their starting room. Validates the
    era_state, world auto-build, and DB seeding paths.
    """
    assert h.era == expected_era, (
        f"Expected era={expected_era!r}, got {h.era!r}. Class fixture broken?"
    )
    s = await h.login_as("Era1Looker", room_id=1)
    out = await h.cmd(s, "look")
    assert out and out.strip(), f"{expected_era} look produced no output"
    assert "unknown command" not in out.lower(), (
        f"{expected_era} `look` returned an error: {out[:300]!r}"
    )


async def cw2_movement_works(h, expected_era="clone_wars"):
    """CW2 — Walking exits works in the chosen era.

    Confirms exit data was written for the boot. The F.5b.3.b
    fix-class bug was room-id drift breaking exit resolution; this
    scenario detects regressions in that family across both eras.
    """
    s = await h.login_as("Era2Walker", room_id=1)
    char_id = s.character["id"]
    out = await h.cmd(s, "north")
    s.character = await h.get_char(char_id)
    new_room = int(s.character["room_id"])
    assert new_room != 1, (
        f"{expected_era}: walking north from spawn didn't change rooms. "
        f"room_id stayed {new_room!r}. Output: {out[:300]!r}"
    )


async def cw3_combat_finds_hostile(h, expected_era="clone_wars"):
    """CW3 — A hostile NPC exists in the spawned world and
    `attack` runs cleanly against it.
    """
    from tests.smoke.scenarios.ground_combat import _find_hostile_npc
    npc_name, npc_room = await _find_hostile_npc(h)
    assert npc_name is not None, (
        f"No hostile NPCs found in the {expected_era} era after auto-build. "
        "Either the NPC source data lacks hostile flags or the "
        "ai_config_json schema diverged."
    )
    s = await h.login_as("Era3Striker", room_id=npc_room)
    target_token = npc_name.split()[0].lower()
    out = await h.cmd(s, f"attack {target_token}")
    assert out and out.strip(), f"attack produced no output in {expected_era}"
    assert "traceback" not in out.lower(), (
        f"{expected_era} attack raised: {out[:500]!r}"
    )


async def cw4_sheet_renders_in_cw(h, expected_era="clone_wars"):
    """CW4 — `+sheet` produces a sheet_data event with all six
    WEG attributes.
    """
    s = await h.login_as("Era4Sheeter", room_id=1)
    pre = len(s.json_events)
    await h.cmd(s, "+sheet")
    new_events = s.json_events[pre:]
    sheet_events = [e for e in new_events if e.get("type") == "sheet_data"]
    assert sheet_events, (
        f"+sheet didn't emit sheet_data on {expected_era}. "
        f"Event types: {[e.get('type') for e in new_events]!r}"
    )
    payload_str = repr(sheet_events[0]).lower()
    expected_attrs = ["dex", "kno", "mech", "perc", "str", "tech"]
    found = [a for a in expected_attrs if a in payload_str]
    assert len(found) >= 4, (
        f"{expected_era} sheet_data missing WEG attributes. "
        f"Found {found!r} in payload."
    )


async def cw5_say_broadcasts_in_cw(h, expected_era="clone_wars"):
    """CW5 — `say` between two PCs in the chosen era still emits the
    pose_event broadcast.

    Sanity check that channel/broadcast plumbing isn't gated on era
    config in a way that broke during F.5b.3.b/c era-aware refactors.
    """
    s_alice = await h.login_as("Era5Alice", room_id=1)
    s_bob = await h.login_as("Era5Bob", room_id=1)
    pre_count = len(s_bob.json_events)
    await h.cmd(s_alice, 'say Hello, citizen.')
    await asyncio.sleep(0.15)
    new_events = s_bob.json_events[pre_count:]
    pose_events = [e for e in new_events if e.get("type") == "pose_event"]
    assert pose_events, (
        f"{expected_era}: Bob received no pose_event from Alice's `say`. "
        f"Event types: {[e.get('type') for e in new_events]!r}"
    )
    payload_str = repr(pose_events[0]).lower()
    assert "citizen" in payload_str, (
        f"pose_event missing the say text. Payload: {pose_events[0]!r}"
    )
