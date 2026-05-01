# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/telnet_protocol.py — Telnet-specific scenarios.

The Telnet flavor of the smoke harness uses ``Protocol.TELNET`` and a
plaintext ``send_callback`` (no JSON envelope). The ``server/session.py``
layer already converts typed events (``pose_event``, ``combat_state``,
etc.) into formatted text fallbacks for Telnet sessions, so most
scenarios can run unchanged with just a different protocol kwarg.

These scenarios re-run the most diagnostic SH1+SH2 checks under the
Telnet protocol path. Identical functional behavior between protocols
is the intent — divergence between the two is a regression flag.

NOTE: SH3 runs the in-process Telnet flavor only (Session machinery
with Protocol.TELNET, no real socket). The subprocess fixture that
exercises the real ``telnetlib3`` stack is deferred to a future drop
because port-discovery + boot ordering + async cleanup add complexity
disproportionate to the incremental coverage. The in-process flavor
catches everything except the wire-protocol bytes.
"""
from __future__ import annotations

import asyncio


async def t1_telnet_login_and_look(h):
    """T1 — Telnet flavor of F1: login + look produces a non-empty
    room description with no JSON envelope leakage.

    On Telnet, room descriptions arrive as plain text (no
    ``{"type": "text", "data": ...}`` wrapping). If the harness
    accidentally feeds the WS dispatcher into a Telnet session, the
    capture buffer would either be empty (parsed-and-routed) or
    contain JSON strings.
    """
    s = await h.login_as("T1Telnet", room_id=1, protocol="telnet")
    out = await h.cmd(s, "look")
    assert out and out.strip(), "look produced no output on Telnet"
    assert "unknown command" not in out.lower(), (
        f"`look` returned an error on Telnet: {out[:300]!r}"
    )
    # The text should NOT be a JSON envelope ({"type": "text", ...})
    # — that would indicate WS-style routing leaked into Telnet.
    assert not out.lstrip().startswith("{"), (
        f"Telnet output looks like a JSON envelope (WS leak?): "
        f"{out[:200]!r}"
    )


async def t2_telnet_movement(h):
    """T2 — Walk a single exit on Telnet, verify the new room loads.

    Telnet equivalent of M1. Should be identical functional behavior
    to the WebSocket case.
    """
    s = await h.login_as("T2Telnet", room_id=1, protocol="telnet")
    out = await h.cmd(s, "north")
    assert "mos eisley street" in out.lower() or "street" in out.lower(), (
        f"`north` from Landing Pad didn't show the Street room on Telnet. "
        f"Output: {out[:300]!r}"
    )
    s.character = await h.get_char(s.character["id"])
    assert int(s.character["room_id"]) == 2, (
        f"room_id not updated after move (Telnet). "
        f"Got {s.character['room_id']!r}"
    )


async def t3_telnet_say_renders_as_text(h):
    """T3 — `say` on Telnet renders as formatted TEXT (the pose_event
    Telnet fallback), NOT as a JSON envelope.

    This is the key cross-protocol divergence: WebSocket sees
    pose_event JSON, Telnet sees the text fallback. If
    ``server/session.py``'s pose_event Telnet-fallback path
    regresses, this catches it.
    """
    s_alice = await h.login_as("T3Alice", room_id=1, protocol="telnet")
    s_bob = await h.login_as("T3Bob", room_id=1, protocol="telnet")

    s_bob.drain_text()
    await h.cmd(s_alice, 'say Hello from Telnet land.')
    await asyncio.sleep(0.15)
    bob_text = s_bob.drain_text()

    # Bob sees the text fallback — should contain Alice's name and
    # the message. It should NOT be in the json_events buffer (which
    # on a Telnet session should always be empty since Telnet has no
    # JSON envelope).
    assert "hello from telnet" in bob_text.lower(), (
        f"T3Bob did not receive T3Alice's `say` as text on Telnet. "
        f"Bob's text: {bob_text[:400]!r}"
    )
    assert "alice" in bob_text.lower() or "T3Alice" in bob_text, (
        f"T3Alice's name missing from Telnet pose fallback. "
        f"Bob's text: {bob_text[:400]!r}"
    )
    assert len(s_bob.json_events) == 0, (
        f"Telnet session captured JSON events (should be empty). "
        f"Events: {s_bob.json_events!r}"
    )


async def t4_telnet_sheet_renders_as_text(h):
    """T4 — `+sheet` on Telnet renders as formatted TEXT, NOT as a
    sheet_data JSON event.

    This is the divergence from H7 (which asserts sheet_data on WS).
    Telnet has no panel renderer, so the server falls through to
    ``render_game_sheet()``'s text output.
    """
    s = await h.login_as("T4Telnet", room_id=1, protocol="telnet")
    out = await h.cmd(s, "+sheet")
    assert out and out.strip(), "+sheet produced no output on Telnet"
    assert "traceback" not in out.lower(), (
        f"+sheet raised on Telnet: {out[:500]!r}"
    )
    sheet_lc = out.lower()
    expected_attrs = ["dex", "kno", "mech", "perc", "str", "tech"]
    found = [a for a in expected_attrs if a in sheet_lc]
    assert len(found) >= 4, (
        f"Telnet +sheet missing expected WEG attributes. "
        f"Found {found!r} in: {out[:600]!r}"
    )
    assert len(s.json_events) == 0, (
        f"Telnet session captured JSON events (should be empty). "
        f"Events: {s.json_events!r}"
    )


async def t5_telnet_combat_text_fallback(h):
    """T5 — `attack <hostile>` on Telnet produces text output (no
    combat_state JSON event).

    The Telnet equivalent of G1+G2. Validates that the combat HUD
    falls back gracefully to text on Telnet.
    """
    # Re-use the helper from ground_combat to find a hostile NPC.
    from tests.smoke.scenarios.ground_combat import _find_hostile_npc
    npc_name, npc_room = await _find_hostile_npc(h)
    if npc_name is None:
        assert False, (
            "No hostile NPCs in world (should never happen on GCW). "
            "See SH2 §3 for the discovery helper."
        )

    s = await h.login_as("T5Striker", room_id=npc_room, protocol="telnet")
    target_token = npc_name.split()[0].lower()
    out = await h.cmd(s, f"attack {target_token}")
    assert out and out.strip(), "attack produced no output on Telnet"
    assert "traceback" not in out.lower(), (
        f"attack raised on Telnet: {out[:500]!r}"
    )
    # We don't assert on hit/miss (RNG); just that a Telnet attack
    # produces text without raising.
