# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/foundation.py — Foundation scenarios (F1-F5).

These are the spine: if any of these break, every other scenario
breaks. They are deliberately simple — they assert on the
infrastructure being wired correctly, not on game depth.

F1: connect + login + look
F2: account creation flow (fresh, NOT short-circuited)
F3: chargen — Telnet text wizard (deferred to SH3 when Telnet driver lands)
F4: reconnect after logout
F5: multi-character +char/switch
"""
from __future__ import annotations

import asyncio


async def f1_login_and_look(h):
    """F1 — Boot + login + look at the spawn room.

    The most basic possible end-to-end check. If this fails, the
    harness is broken or boot is broken; nothing else will work.

    Asserts:
      - login_as returns a session in IN_GAME state
      - `look` produces some non-empty text
      - the text is not obviously an error
    """
    s = await h.login_as("F1Look")
    out = await h.cmd(s, "look")
    assert out and out.strip(), "look produced no output"
    # An error response would typically start with "Unknown command" or
    # similar; we don't assert on a specific room name here because the
    # spawn room varies by era. Specific-content assertions are layered
    # on in later scenarios.
    assert "unknown command" not in out.lower(), (
        f"`look` returned an error: {out[:200]!r}"
    )
    return s


async def f1_who_lists_self(h):
    """F1 (extended) — `who` shows the logged-in character.

    Validates that the session is registered with the SessionManager
    and the WhoCommand can find it.
    """
    s = await h.login_as("F1Who")
    out = await h.cmd(s, "who")
    assert "f1who" in out.lower() or s.character["name"].lower() in out.lower(), (
        f"`who` did not show this session's character. Output: {out[:300]!r}"
    )


async def _wait_until(predicate, *, timeout: float = 3.0,
                      interval: float = 0.05) -> bool:
    """Poll *predicate* until it returns truthy or *timeout* elapses.

    Returns True if the predicate became truthy, False on timeout.
    Used by F2 et al. to avoid fixed-sleep races against pytest-asyncio's
    cooperative scheduling.
    """
    import time as _t
    deadline = _t.monotonic() + timeout
    while _t.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def f2_account_creation_flow(h):
    """F2 — Drive the on-the-wire `create <user> <pass>` flow.

    Unlike every other scenario (which short-circuits chargen via
    direct DB seed), this one walks the actual login prompt → create →
    auth path that a real new player hits. It validates:

      - the create command parses
      - the account row gets written to the DB
      - too-short password is rejected (validation fires)

    Note: after a successful create, the server flow falls into
    ``_character_select`` and (for a 0-character new account on
    WebSocket) into ``_run_web_chargen``, which sends a ``chargen_start``
    JSON event and then waits for ``__chargen_done__``. We do NOT
    drive chargen end-to-end here — chargen has its own scenario
    (F3, deferred to drop SH3 with the Telnet driver).
    """
    from server.session import Session, Protocol

    text_buf: list[str] = []
    json_buf: list[dict] = []

    async def _send(payload):
        import json as _j
        if isinstance(payload, str):
            try:
                obj = _j.loads(payload)
                if isinstance(obj, dict):
                    if obj.get("type") == "text":
                        text_buf.append(obj.get("data", ""))
                    else:
                        json_buf.append(obj)
                    return
            except (ValueError, TypeError):
                pass
        text_buf.append(str(payload))

    async def _close():
        return None

    session = Session(
        protocol=Protocol.WEBSOCKET,
        send_callback=_send, close_callback=_close,
        width=100, height=40,
    )
    h.server.session_mgr.add(session)

    task = asyncio.create_task(h.server.handle_new_session(session, reader=None))

    # Wait for the welcome banner to land. Poll instead of sleeping
    # blindly — pytest-asyncio's cooperative scheduling gives less
    # wall-time to background tasks than asyncio.run() does, so any
    # fixed sleep is racy.
    await _wait_until(lambda: bool(text_buf), timeout=3.0)
    text_buf.clear()

    # ── Test 1: short-password validation ──
    session.feed_input("create f2user x")
    got_short = await _wait_until(
        lambda: any("password" in t.lower() for t in text_buf),
        timeout=3.0,
    )
    assert got_short, (
        f"Short-password validation didn't fire within timeout. "
        f"Output: {''.join(text_buf)[:300]!r}"
    )
    text_buf.clear()

    # ── Test 2: valid create → DB row exists + chargen_start fires ──
    session.feed_input("create f2user smoketestpass")

    # Wait for the chargen_start event — that's the authoritative
    # signal that create_account succeeded and _character_select
    # entered _run_web_chargen.
    got_chargen = await _wait_until(
        lambda: any(e.get("type") == "chargen_start" for e in json_buf),
        timeout=5.0,
    )
    assert got_chargen, (
        f"chargen_start event not sent within timeout — flow stalled. "
        f"JSON events seen: {[e.get('type') for e in json_buf]!r}; "
        f"text: {''.join(text_buf)[:300]!r}"
    )

    # The account row should now exist.
    rows = await h.db.fetchall(
        "SELECT id, username FROM accounts WHERE username = ?",
        ("f2user",),
    )
    assert len(rows) == 1, (
        f"chargen_start fired but account row missing. "
        f"Captured text: {''.join(text_buf)[:300]!r}"
    )

    # Cleanup: cancel the background task. We deliberately don't
    # complete chargen (that's F3's job).
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def f4_reconnect_preserves_state(h):
    """F4 — Logout, reconnect, verify character state preserved.

    Sets a known-mutable state (room_id), logs the character out
    explicitly, then reloads from DB to verify the state stuck. We
    don't go through ``login_as`` again because that would create a
    fresh character.

    Implementation note: writing room_id with ``save_character``
    alone is insufficient because the quit-handling path re-saves
    using ``session.character["room_id"]`` which would clobber our
    DB-only write. So we update both: in-memory AND DB, mimicking
    what a real movement command does. This makes the assertion
    valid — we're testing "did the persisted row match the player's
    last known state," not "did save_character succeed in
    isolation."
    """
    s = await h.login_as("F4Recon", room_id=1, credits=500)
    char_id = s.character["id"]

    # Mutate room_id in BOTH places: the in-memory session.character
    # dict AND the DB. This is what a real MoveCommand path does
    # (it updates session.character then calls db.save_character).
    s.character["room_id"] = 2
    s.session.invalidate_char_obj()
    await h.db.save_character(char_id, room_id=2)

    # Verify the save landed before the quit.
    pre_quit = await h.get_char(char_id)
    assert int(pre_quit["room_id"]) == 2, (
        f"Pre-quit save didn't land. DB row: {dict(pre_quit)!r}"
    )

    # Send `quit` — the QuitCommand will save room_id from
    # session.character (which is now 2), close the session, and
    # the row should land at room_id=2.
    quit_out = await h.cmd(s, "quit", timeout=1.0)

    # Give the game loop one more tick to fully exit and any
    # post-quit handlers to settle.
    await asyncio.sleep(0.2)

    # Reload from DB — this is what reconnect would see.
    reloaded = await h.get_char(char_id)
    assert reloaded is not None, "Character row missing after quit"
    assert int(reloaded["room_id"]) == 2, (
        f"room_id not persisted across logout. "
        f"Expected 2, got {reloaded['room_id']!r}. "
        f"In-memory at quit time was {s.character.get('room_id')!r}. "
        f"Quit output: {quit_out[:200]!r}"
    )
    assert int(reloaded.get("credits", 0)) == 500, (
        f"credits not persisted across logout. "
        f"Expected 500, got {reloaded.get('credits')!r}"
    )


async def f5_char_switch_alt(h):
    """F5 — Multi-character: create alt, verify both rows exist.

    The full +char/switch flow (live SessionState.CHAR_SWITCH path)
    requires driving the login loop end-to-end and is the focus of
    a richer test in SH2/SH3. SH1 verifies the underlying capability:
    one account can hold multiple characters and the DB layer
    distinguishes them correctly.
    """
    s = await h.login_as("F5Main")
    main_id = s.character["id"]
    account_id = s.session.account["id"]

    # Create a second character on the same account by going around
    # login_as (which would conflict on account creation). We use
    # db.create_character() directly — the same path chargen uses.
    alt_fields = await h._build_test_character_fields(
        name="F5Alt",
        species="Human",
        template="scout",
        room_id=1,
        credits=0,
    )
    alt_fields["chargen_notes"] = "smoke-harness-seeded"
    alt_id = await h.db.create_character(account_id, alt_fields)

    chars = await h.db.get_characters(account_id)
    names = {c["name"] for c in chars}
    assert "F5Main" in names and "F5Alt" in names, (
        f"Both characters should be on the account. Got: {names!r}"
    )
    assert main_id != alt_id, "Alt should have a distinct character ID"
