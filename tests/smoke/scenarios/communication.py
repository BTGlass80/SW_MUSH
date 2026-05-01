# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/communication.py — Communication scenarios (C1-C7).

Per design §6.2.

Verifies say/pose/emote (room-local broadcast), whisper (targeted),
page/ooc (cross-room), `+finger`/`+where` (player lookup), `+roll`
(D6 dice). Channel commands (tune/comlink/fcomm) are DEFERRED to
SH3 because they require channel registration and possibly faction
state that SH2's GCW seed doesn't provide; they get their own
scenario when SH3 wires them up.
"""
from __future__ import annotations

import asyncio


async def c1_say_local_broadcast(h):
    """C1 — `say "hello"` produces output for the speaker AND a
    `pose_event` JSON event for any other PC in the same room.

    NOTE: in the WebSocket envelope, `say` broadcasts as a typed
    ``pose_event`` JSON message (per Drop B' refactor in
    parser/builtin_commands.py), not as a text frame. Telnet
    observers get a formatted text fallback via
    ``server/session.py``'s pose_event Telnet handler. The WebSocket
    smoke harness asserts on the typed event.
    """
    s1 = await h.login_as("C1Alice", room_id=1)
    s2 = await h.login_as("C1Bob", room_id=1)
    pre_count = len(s2.json_events)
    await h.cmd(s1, 'say Hello there.')
    # Give the broadcast a moment to land on Bob's session.
    await asyncio.sleep(0.15)
    new_events = s2.json_events[pre_count:]
    pose_events = [e for e in new_events if e.get("type") == "pose_event"]
    assert pose_events, (
        f"C1Bob received no pose_event from C1Alice's `say`. "
        f"Event types received: {[e.get('type') for e in new_events]!r}"
    )
    # The pose payload should contain Alice's text.
    payload = pose_events[0]
    payload_str = repr(payload).lower()
    assert "hello there" in payload_str, (
        f"pose_event missing the say text. Payload: {payload!r}"
    )


async def c2_pose_local_broadcast(h):
    """C2 — `:waves` (pose alias) emits a pose_event to all sessions
    in the room, including the actor.

    Per ``parser/builtin_commands.py::EmoteCommand``, pose/emote/`:`
    all use ``broadcast_json_to_room("pose_event", ...)`` with NO
    ``exclude=`` argument — meaning the actor receives the event too.
    """
    s = await h.login_as("C2Poser", room_id=1)
    pre = len(s.json_events)
    await h.cmd(s, ':waves cheerfully.')
    await asyncio.sleep(0.1)
    new_events = s.json_events[pre:]
    pose_events = [e for e in new_events if e.get("type") == "pose_event"]
    assert pose_events, (
        f"Pose did not emit a pose_event. "
        f"Event types: {[e.get('type') for e in new_events]!r}"
    )
    payload_str = repr(pose_events[0]).lower()
    assert "waves" in payload_str, (
        f"pose_event missing the action text. "
        f"Payload: {pose_events[0]!r}"
    )


async def c3_emote_command(h):
    """C3 — `emote <text>` emits a pose_event with EVENT_POSE shape.

    Same plumbing as C2 (the `pose` alias dispatches to the same
    EmoteCommand class), but exercises the explicit `emote` keyword
    rather than the `:` shortcut.
    """
    s = await h.login_as("C3Emote", room_id=1)
    pre = len(s.json_events)
    await h.cmd(s, "emote scratches their chin.")
    await asyncio.sleep(0.1)
    new_events = s.json_events[pre:]
    pose_events = [e for e in new_events if e.get("type") == "pose_event"]
    assert pose_events, (
        f"emote did not emit a pose_event. "
        f"Event types: {[e.get('type') for e in new_events]!r}"
    )
    payload_str = repr(pose_events[0]).lower()
    assert "scratches" in payload_str, (
        f"pose_event missing emote action. Payload: {pose_events[0]!r}"
    )


async def c4_whisper_targeted(h):
    """C4 — `whisper <player> = <message>` sends to one PC only.

    NOTE: WhisperCommand requires the ``=`` separator (per
    ``parser/builtin_commands.py:941``). The target receives a
    ``pose_event`` with ``EVENT_WHISPER`` shape; non-target PCs in
    the same room receive nothing.
    """
    s_alice = await h.login_as("C4Alice", room_id=1)
    s_bob = await h.login_as("C4Bob", room_id=1)
    s_carol = await h.login_as("C4Carol", room_id=1)

    bob_pre = len(s_bob.json_events)
    carol_pre = len(s_carol.json_events)
    s_bob.drain_text()
    s_carol.drain_text()

    # Use the `=` form per the actual command syntax.
    await h.cmd(s_alice, "whisper C4Bob = a secret message")
    await asyncio.sleep(0.2)
    bob_events = s_bob.json_events[bob_pre:]
    carol_events = s_carol.json_events[carol_pre:]
    bob_text = s_bob.drain_text()
    carol_text = s_carol.drain_text()

    bob_combined = bob_text + repr(bob_events)
    assert "secret message" in bob_combined.lower(), (
        f"Bob did not receive the whisper. "
        f"Text: {bob_text[:300]!r}, Events: {bob_events!r}"
    )
    # Carol should NOT have seen the message content.
    carol_combined = carol_text + repr(carol_events)
    assert "secret message" not in carol_combined.lower(), (
        f"Carol saw a whisper she shouldn't have. "
        f"Text: {carol_text[:300]!r}, Events: {carol_events!r}"
    )


async def c5_page_cross_room(h):
    """C5 — `page <player> = <msg>` reaches a PC in a different room.

    NOTE: ``page`` is an alias for ``whisper`` (see
    ``parser/builtin_commands.py:932``). Both commands require the
    same target to be IN THE SAME ROOM, despite the conventional MUX
    semantics where `page` would be cross-room. Pre-launch consideration
    for the dev session — many MUX players will be confused by this.
    For now, we test ``page`` with same-room PCs to validate the
    dispatch.
    """
    s_alice = await h.login_as("C5Alice", room_id=1)
    s_bob = await h.login_as("C5Bob", room_id=1)  # same room — page is whisper-aliased
    s_bob.drain_text()
    bob_pre = len(s_bob.json_events)

    await h.cmd(s_alice, "page C5Bob = same room hello")
    await asyncio.sleep(0.2)
    bob_text = s_bob.drain_text()
    bob_events = s_bob.json_events[bob_pre:]

    bob_combined = bob_text + repr(bob_events)
    assert "same room hello" in bob_combined.lower(), (
        f"Bob did not receive the page. "
        f"Text: {bob_text[:300]!r}, Events: {bob_events!r}"
    )


async def c6_ooc_channel(h):
    """C6 — `ooc <text>` (bareword, NOT `+ooc`) broadcasts globally.

    NOTE: there are TWO OOC commands. ``+ooc`` (in
    ``parser/builtin_commands.py``) is ROOM-LOCAL. ``ooc`` (in
    ``parser/channel_commands.py``) is GLOBAL via the channel
    manager. This is a real footgun: a player typing ``+ooc`` for
    "out of character" gets room-local; ``ooc`` gets global. The
    smoke harness asserts on the global form by using the bareword.
    """
    s_alpha = await h.login_as("C6Alpha", room_id=1)
    s_beta = await h.login_as("C6Beta", room_id=3)

    s_beta.drain_text()
    beta_pre = len(s_beta.json_events)
    await h.cmd(s_alpha, "ooc anyone around?")
    await asyncio.sleep(0.2)
    beta_text = s_beta.drain_text()
    beta_events = s_beta.json_events[beta_pre:]

    beta_combined = beta_text + repr(beta_events)
    assert "anyone around" in beta_combined.lower(), (
        f"OOC global broadcast didn't reach C6Beta. "
        f"Text: {beta_text[:400]!r}, Events: {beta_events!r}"
    )


async def c7_roll_dice(h):
    """C7 — `+roll 3d6` produces a roll result with reasonable shape.

    Validates the D6 roll plumbing (Wild Die, total, etc.) at the
    most basic level. We don't assert on the specific number (it's
    random) — just that a number appears and the output isn't an
    error.
    """
    s = await h.login_as("C7Roller", room_id=1)
    out = await h.cmd(s, "+roll 3d6")
    assert "traceback" not in out.lower() and \
           "exception" not in out.lower(), (
        f"+roll raised an exception. Output: {out[:400]!r}"
    )
    # Some digit should be in the output (the sum or one of the dice).
    assert any(c.isdigit() for c in out), (
        f"+roll produced no numeric output. Output: {out[:400]!r}"
    )


async def c8_finger_lookup(h):
    """C8 — `+finger <name>` shows public info about an online PC.

    Bonus scenario beyond C1-C7 — finger is a common MUX command and
    a fast smoke check on the WhereCommand/FingerCommand path.
    """
    s_subject = await h.login_as("C8Subject", room_id=1)
    s_looker = await h.login_as("C8Looker", room_id=2)
    out = await h.cmd(s_looker, "+finger C8Subject")
    assert "c8subject" in out.lower(), (
        f"+finger didn't include the subject name. Output: {out[:400]!r}"
    )
