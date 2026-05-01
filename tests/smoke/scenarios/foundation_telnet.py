# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/foundation_telnet.py — F3 (Telnet text wizard chargen).

Deferred from SH1; lands in SH3 with the Telnet driver.

This scenario walks the on-the-wire Telnet flow:
  - connect (no welcome screen since handle_new_session is the gate)
  - create <user> <pass>
  - the new account has 0 characters → _character_select dispatches to
    _run_character_creation (text wizard), NOT _run_web_chargen
  - the wizard sends its welcome screen
  - we assert on the welcome text shape

We DO NOT drive the wizard end-to-end. Reasons:
  1. The full wizard is multi-step text I/O with significant state
     and many decision points (template vs scratch, species, attribute
     allocation, skill allocation, force sensitivity, freeform, etc.).
     A full end-to-end wizard scenario deserves its own scenario file.
  2. The wizard's terminal step calls db.create_character(...), which
     hits the SCHEMA_VERSION = 16 vs MIGRATIONS[17] bug from SH1 and
     blows up on a fresh DB. Until that bug is fixed, end-to-end
     wizard scenarios can't pass.
"""
from __future__ import annotations

import asyncio


async def f3_telnet_wizard_intro(h):
    """F3 — The Telnet `create <user> <pass>` flow lands in the text
    wizard and emits a welcome screen.

    Setup mirrors F2's WS account-creation flow but uses
    Protocol.TELNET. We can't go through harness.login_as because
    that short-circuits chargen via direct DB seed. We build the
    Session manually and drive handle_new_session like F2 does.
    """
    from server.session import Session, Protocol

    text_buf: list[str] = []

    async def _send(payload):
        # Telnet send_callback: raw text, no JSON envelope.
        text_buf.append(str(payload))

    async def _close():
        return None

    session = Session(
        protocol=Protocol.TELNET,
        send_callback=_send, close_callback=_close,
        width=100, height=40,
    )
    h.server.session_mgr.add(session)
    task = asyncio.create_task(h.server.handle_new_session(session, reader=None))

    # Wait for the welcome banner. Polling pattern from SH1
    # implementation gotcha §5.1.
    async def _wait_until(predicate, *, timeout=5.0, interval=0.05):
        import time as _t
        deadline = _t.monotonic() + timeout
        while _t.monotonic() < deadline:
            if predicate():
                return True
            await asyncio.sleep(interval)
        return False

    await _wait_until(lambda: bool(text_buf), timeout=5.0)
    # Don't drain — we want to see the welcome AND the post-create
    # output in the buffer for diagnostic purposes.
    text_buf.clear()

    # Drive the create flow.
    session.feed_input("create f3telnet smoketestpass")

    # Wait for the wizard's welcome screen. The wizard begins with
    # the WELCOME step, which renders introductory text. We look for
    # any of these markers (they're robust across wizard versions):
    wizard_markers = ["create your character", "welcome to character",
                      "step", "template", "scratch", "background"]

    def _wizard_visible():
        joined = "".join(text_buf).lower()
        return any(m in joined for m in wizard_markers)

    found = await _wait_until(_wizard_visible, timeout=8.0)
    full = "".join(text_buf)
    assert found, (
        f"Telnet chargen wizard did not produce its welcome screen "
        f"within 8s. Captured text: {full[:600]!r}"
    )
    # The wizard prompt is 'create>' typically. Validate that some
    # prompt-shaped string appears.
    has_prompt = ">" in full or "create" in full.lower()
    assert has_prompt, (
        f"Wizard appears not to have rendered a prompt. "
        f"Captured: {full[:600]!r}"
    )

    # Cleanup. We don't drive the wizard further (see module
    # docstring for why).
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
