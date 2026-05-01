# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/builtins.py — Help, sheet, MUX-style basics (H6-H8).

Per design §6.9.

These are the "every player uses these in their first 30 seconds"
commands: +help, +sheet, +inv (already in movement.py), +who, +finger,
+where. If any of these regress, every player notices immediately.
"""
from __future__ import annotations


async def h6_help_index_and_topic(h):
    """H6 — `+help` produces a help index, and `+help <topic>`
    produces topic-specific output.

    Specifically catches HelpEntry schema regressions — the help
    loader was fixed in the architecture v34 era (HelpEntry kwargs
    not declared in the dataclass). Worth a smoke check.
    """
    s = await h.login_as("H6Reader", room_id=1)

    # Top-level `+help` (index).
    out_index = await h.cmd(s, "+help")
    assert out_index and out_index.strip(), "+help produced no output"
    assert "traceback" not in out_index.lower(), (
        f"+help index raised: {out_index[:400]!r}"
    )

    # `+help look` should have content. Even if the specific
    # description differs, we should see the word 'look' somewhere.
    out_look = await h.cmd(s, "+help look")
    assert out_look and out_look.strip(), "+help look produced no output"
    assert "traceback" not in out_look.lower(), (
        f"+help look raised: {out_look[:400]!r}"
    )
    # The help text for `look` mentions surroundings. Allow a few
    # variants.
    look_lc = out_look.lower()
    assert (
        "surroundings" in look_lc
        or "room" in look_lc
        or "look" in look_lc
    ), f"+help look output doesn't reference look semantics: {out_look[:500]!r}"


async def h6b_help_unknown_topic(h):
    """H6 (extension) — `+help <bogus>` fails gracefully.

    Catches the bug where unknown help topics raise instead of
    producing a "no such topic" message.
    """
    s = await h.login_as("H6Bogus", room_id=1)
    out = await h.cmd(s, "+help bogus_topic_xyzzy")
    assert "traceback" not in out.lower(), (
        f"+help <bogus> raised: {out[:500]!r}"
    )
    # Some output should be present (even if it's "no such topic").
    assert out and out.strip(), "+help <bogus> produced no output"


async def h7_sheet_displays(h):
    """H7 — `+sheet` produces sheet data for the character.

    Hits attribute display, the JSON-attributes parse, and the
    character sheet renderer. If `attributes` is malformed or the
    sheet renderer regressed, this catches it.

    NOTE: WebSocket sessions receive `+sheet` output as a typed
    ``sheet_data`` JSON event (the browser renders a slide-in
    panel; the legacy text dump is suppressed on WS). Telnet
    sessions get text. Smoke harness is on WS, so we assert on
    the typed event.
    """
    s = await h.login_as("H7Sheeter", room_id=1)
    pre = len(s.json_events)
    out = await h.cmd(s, "+sheet")
    new_events = s.json_events[pre:]
    sheet_events = [e for e in new_events if e.get("type") == "sheet_data"]
    assert sheet_events, (
        f"+sheet didn't emit a sheet_data event. "
        f"Event types: {[e.get('type') for e in new_events]!r}, "
        f"text: {out[:200]!r}"
    )
    # The payload should reference some standard sheet fields.
    payload = sheet_events[0]
    payload_str = repr(payload).lower()
    expected_attrs = ["dex", "kno", "mech", "perc", "str", "tech"]
    found = [a for a in expected_attrs if a in payload_str]
    assert len(found) >= 4, (
        f"sheet_data payload missing expected WEG attribute names. "
        f"Found {found!r} in payload (truncated): {payload_str[:600]!r}"
    )


async def h8_where_command(h):
    """H8 — `+where` shows where players are located.

    Catches WhereCommand regressions and validates that the
    SessionManager + room name resolution still cooperate.
    """
    s_self = await h.login_as("H8Self", room_id=1)
    s_other = await h.login_as("H8Other", room_id=3)
    out = await h.cmd(s_self, "+where")
    assert out and out.strip(), "+where produced no output"
    assert "traceback" not in out.lower(), (
        f"+where raised: {out[:500]!r}"
    )
    # H8Other should appear in the listing (they're in-game).
    assert "h8other" in out.lower(), (
        f"+where missing the other PC. Output: {out[:500]!r}"
    )
