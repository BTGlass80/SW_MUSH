# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/movement.py — Movement and exploration scenarios (M1-M6).

Per design §6.2.

These scenarios anchor on the Mos Eisley Spaceport spawn area which
the GCW auto-build reliably produces:

    Room 1: Landing Pad - Mos Eisley Spaceport  (north → 2)
    Room 2: Mos Eisley Street                   (east → 3, north → 12, south → 1)
    Room 3: Chalmun's Cantina                   (east → 16, west → 2)

The path Room 1 → Room 2 → Room 3 → Room 2 → Room 1 hits movement,
exit resolution, room cache, and re-entry — all in 4 commands.

M1-M4 use these spawn rooms; M5-M6 (inventory) use a freshly-given item.
"""
from __future__ import annotations

import asyncio


async def m1_walk_spawn_exit(h):
    """M1 — Walk a single exit (north) and verify the new room loads.

    The simplest possible movement check. If this fails, MoveCommand
    or the exit-resolution path is broken.
    """
    s = await h.login_as("M1Walker", room_id=1)
    out = await h.cmd(s, "north")
    # We should now be in room 2 (Mos Eisley Street).
    assert "mos eisley street" in out.lower() or "street" in out.lower(), (
        f"`north` from Landing Pad didn't show the Street room. "
        f"Output: {out[:300]!r}"
    )
    # The character row should reflect the new room.
    s.character = await h.get_char(s.character["id"])
    assert int(s.character["room_id"]) == 2, (
        f"room_id not updated after move. Got {s.character['room_id']!r}"
    )


async def m2_path_through_three_rooms(h):
    """M2 — Walk a 3-room path and back, verifying each transition.

    Hits exit-cache stability across multiple moves and re-entry of a
    previously-visited room. If the world build wrote inconsistent
    exits, this is where it shows up.
    """
    s = await h.login_as("M2Pather", room_id=1)
    char_id = s.character["id"]

    # 1 → 2 (Landing Pad → Mos Eisley Street)
    await h.cmd(s, "north")
    s.character = await h.get_char(char_id)
    assert int(s.character["room_id"]) == 2, (
        f"Step 1: expected room 2, got {s.character['room_id']!r}"
    )

    # 2 → 3 (Street → Cantina)
    out = await h.cmd(s, "east")
    s.character = await h.get_char(char_id)
    assert int(s.character["room_id"]) == 3, (
        f"Step 2: expected room 3, got {s.character['room_id']!r}. "
        f"Output: {out[:200]!r}"
    )
    assert "cantina" in out.lower(), f"Cantina not in output: {out[:200]!r}"

    # 3 → 2 (Cantina → Street, via west)
    await h.cmd(s, "west")
    s.character = await h.get_char(char_id)
    assert int(s.character["room_id"]) == 2, (
        f"Step 3: expected room 2 on return, got {s.character['room_id']!r}"
    )

    # 2 → 1 (Street → Landing Pad, via south)
    await h.cmd(s, "south")
    s.character = await h.get_char(char_id)
    assert int(s.character["room_id"]) == 1, (
        f"Step 4: expected room 1, got {s.character['room_id']!r}"
    )


async def m3_invalid_exit_rejected(h):
    """M3 — Walking into a non-existent exit produces a friendly error
    and does NOT move the character.

    This catches a class of bug where a typo in the exits table or a
    missing exit silently teleports to room 0 / the void. Players
    have hit this kind of thing in the past.
    """
    s = await h.login_as("M3NoGo", room_id=1)
    char_id = s.character["id"]
    # Landing Pad has only `north`. `west` should fail.
    out = await h.cmd(s, "west")
    assert "can't" in out.lower() or "no exit" in out.lower() or \
           "cannot" in out.lower() or "don't see" in out.lower() or \
           "no such" in out.lower(), (
        f"Bad-direction error message not found. Output: {out[:300]!r}"
    )
    s.character = await h.get_char(char_id)
    assert int(s.character["room_id"]) == 1, (
        f"Character moved despite bad exit. room_id={s.character['room_id']!r}"
    )


async def m4_look_after_move(h):
    """M4 — `look` after move shows the new room without stale data.

    Catches the bug pattern where the room cache or the in-memory
    character object holds onto the old room's description.

    Note: the new room's exit list legitimately includes the previous
    room's name (e.g. Mos Eisley Street's exits show 'south → Landing
    Pad'), so we can't just assert the old name is absent. Instead we
    check that the FIRST line of look output is the new room's title.
    """
    s = await h.login_as("M4Looker", room_id=1)
    out_before = await h.cmd(s, "look")
    first_line_before = out_before.strip().splitlines()[0].lower()
    assert "landing pad" in first_line_before, (
        f"Initial look's first line wasn't Landing Pad. "
        f"First line: {first_line_before!r}"
    )

    await h.cmd(s, "north")
    out_after = await h.cmd(s, "look")
    first_line_after = out_after.strip().splitlines()[0].lower()
    assert "landing pad" not in first_line_after, (
        f"`look` after move still has Landing Pad as the first line. "
        f"First line: {first_line_after!r}"
    )
    assert "street" in first_line_after, (
        f"`look` after move first line doesn't show new room. "
        f"First line: {first_line_after!r}"
    )


async def m5_inventory_command(h):
    """M5 — `+inv` shows inventory state (empty for a fresh character)
    and reflects items added via the harness give_item.

    Validates inventory persistence + display roundtrip.
    """
    s = await h.login_as("M5Bagman", room_id=1)
    char_id = s.character["id"]

    # Empty inventory check.
    out_empty = await h.cmd(s, "+inv")
    assert out_empty and out_empty.strip(), (
        f"+inv produced no output for empty inventory: {out_empty!r}"
    )
    # Don't assert specific "empty" wording; the display style varies.
    # Just make sure no exception text is in there.
    assert "traceback" not in out_empty.lower(), (
        f"+inv raised an exception on empty inventory: {out_empty[:500]!r}"
    )

    # Give an item and check it appears.
    await h.give_item(char_id, {
        "name": "Datapad",
        "slot": "carried",
        "type": "misc",
        "qty": 1,
    })
    s.character = await h.get_char(char_id)
    # The session also needs a refreshed in-memory copy for +inv to see it.
    s.session.invalidate_char_obj()

    out_with_item = await h.cmd(s, "+inv")
    assert "datapad" in out_with_item.lower(), (
        f"+inv didn't show the granted Datapad. "
        f"Output: {out_with_item[:500]!r}"
    )


async def m6_who_lists_other_player(h):
    """M6 — Two PCs in the same room — each one's `who` lists the other.

    Validates that SessionManager broadcasts and lookups correctly
    handle multiple in-game sessions on a shared harness.
    """
    s1 = await h.login_as("M6Alpha", room_id=1)
    s2 = await h.login_as("M6Bravo", room_id=1)

    out_a = await h.cmd(s1, "who")
    assert "m6bravo" in out_a.lower() or "M6Bravo" in out_a, (
        f"M6Alpha's `who` missing M6Bravo. Output: {out_a[:300]!r}"
    )
    out_b = await h.cmd(s2, "who")
    assert "m6alpha" in out_b.lower() or "M6Alpha" in out_b, (
        f"M6Bravo's `who` missing M6Alpha. Output: {out_b[:300]!r}"
    )
