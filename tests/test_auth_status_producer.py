# -*- coding: utf-8 -*-
"""Structured ``auth_status`` producer for the SPA login form.

THE GAP (verified at HEAD before this drop):
  ``static/client.html`` has a complete CONSUMER for a structured auth result —
  ``handleAuthStatus(msg)`` (``case 'auth_status'`` in the WS dispatch) reading
  ``{ok, kind, username?, reason?, message?}``, documented as "Structured auth
  result from server (replaces regex matching on text)". But NO server code path
  ever emitted ``auth_status`` (exhaustive grep: the only two references in the
  whole tree were the client comment + the client ``case``). So the SPA's login
  form ran ENTIRELY on the brittle ``checkForAuthFailure`` regex-on-English-text
  fallback — which only pattern-matches a handful of error wordings and, notably,
  does NOT match the per-IP rate-limit notice ("Too many login attempts ...").
  A rate-limited web login therefore hung the form in its ``awaitingAuth`` state
  forever with no error shown.

THE FIX:
  ``GameServer.handle_new_session`` now emits a structured ``auth_status`` event
  on EVERY connect/create outcome (success + each failure), via the fail-open,
  telnet-safe ``_emit_auth_status`` helper. The SPA's existing consumer resolves
  the form deterministically, independent of the error wording; the legacy text
  + regex fallback stays in place for old servers but is no longer relied upon.

These tests drive the REAL login loop (the proven WS-session harness from
``test_t321_preauth_throttle``) and assert the structured event is produced with
the right shape on each branch, that it is telnet-safe (no JSON leaks to a telnet
client), and that the producer/consumer contract is pinned at both ends.
"""
import asyncio
import json
import os
import pathlib
import tempfile

import pytest

from server.game_server import (
    _preauth_rate_ok,
    _reset_preauth_throttle,
    _PREAUTH_RATE_MAX,
)

_ROOT = pathlib.Path(__file__).resolve().parent.parent
GAME_SERVER_SRC = (_ROOT / "server" / "game_server.py").read_text(encoding="utf-8")
CLIENT_HTML_SRC = (_ROOT / "static" / "client.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_throttle():
    _reset_preauth_throttle()
    yield
    _reset_preauth_throttle()


# ── harness (mirrors test_t321_preauth_throttle) ─────────────────────────────

@pytest.fixture
async def server_db():
    """A minimal booted GameServer with a real temp DB (no world build)."""
    from server.config import Config
    from engine.era_state import set_active_config
    from server.game_server import GameServer

    tmpdir = tempfile.mkdtemp(prefix="sw_mush_authstatus_")
    db_path = os.path.join(tmpdir, "authstatus.db")
    config = Config(
        db_path=db_path,
        telnet_host="127.0.0.1", telnet_port=0,
        web_client_host="127.0.0.1", web_client_port=0,
        idle_timeout=5,
    )
    set_active_config(config)
    srv = GameServer(config)
    await srv.db.connect()
    await srv.db.initialize()

    async def _fake_select(session):
        return None
    srv._character_select = _fake_select  # type: ignore[assignment]

    yield srv

    try:
        await srv.db.close()
    except Exception:
        pass


def _make_session(client_ip: str, protocol=None):
    from server.session import Session, Protocol
    sent: list = []

    async def _send(payload):
        sent.append(str(payload))

    async def _close():
        return None

    sess = Session(
        protocol=protocol or Protocol.WEBSOCKET,
        send_callback=_send, close_callback=_close,
        width=80, height=40,
    )
    sess.client_ip = client_ip
    return sess, sent


async def _drive_lines(srv, session, lines, *, max_wait=3.0, grace=0.9):
    task = asyncio.create_task(srv.handle_new_session(session, reader=None))
    await asyncio.sleep(0.02)
    for line in lines:
        session.feed_input(line)
    waited = 0.0
    while waited < max_wait:
        await asyncio.sleep(0.02)
        waited += 0.02
        if session._input_queue.empty():
            break
    # Grace for the final line's post-dequeue work — a create does TWO bcrypt
    # ops (hash + verify) which can exceed a short grace before the structured
    # event is emitted.
    await asyncio.sleep(grace)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


def _auth_events(sent):
    """Extract the parsed ``auth_status`` JSON payloads from captured sends."""
    out = []
    for s in sent:
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("type") == "auth_status":
            out.append(obj)
    return out


# ── 1. connect: success + each failure emits a structured event ──────────────

async def test_connect_success_emits_ok(server_db):
    srv = server_db
    aid = await srv.db.create_account("realuser", "correcthorsebattery")
    assert aid is not None

    session, sent = _make_session("203.0.113.10")
    await _drive_lines(srv, session, ["connect realuser correcthorsebattery"])

    events = _auth_events(sent)
    assert len(events) == 1
    ev = events[0]
    assert ev["ok"] is True
    assert ev["kind"] == "connect"
    assert ev["username"] == "realuser"


async def test_connect_bad_credentials_emits_failure(server_db):
    srv = server_db
    session, sent = _make_session("203.0.113.11")
    await _drive_lines(srv, session, ["connect nobody wrongpass"])

    events = _auth_events(sent)
    assert len(events) == 1
    ev = events[0]
    assert ev["ok"] is False
    assert ev["kind"] == "connect"
    assert ev["reason"] == "invalid_credentials"
    assert "Invalid username or password." in ev["message"]


async def test_connect_rate_limited_emits_structured_failure(server_db):
    """THE LATENT BUG THIS CLOSES: the rate-limit notice is NOT matched by the
    SPA's regex fallback, so before this producer a rate-limited web login hung
    the form forever. Now it emits a structured ``rate_limited`` failure."""
    srv = server_db
    ip = "203.0.113.12"
    # Exhaust the per-IP budget directly so the next connect is throttled.
    for _ in range(_PREAUTH_RATE_MAX):
        assert _preauth_rate_ok(ip) is True
    assert _preauth_rate_ok(ip) is False

    # Re-exhaust isn't needed; the bucket is already over budget. Drive one
    # connect — it must be throttled BEFORE authenticate() and emit the event.
    session, sent = _make_session(ip)
    await _drive_lines(srv, session, ["connect realuser whatever"])

    events = _auth_events(sent)
    assert any(
        e["ok"] is False and e["kind"] == "connect"
        and e.get("reason") == "rate_limited"
        for e in events
    ), events


# ── 2. create: success + validation/taken failures ──────────────────────────

async def test_create_success_emits_ok(server_db):
    srv = server_db
    session, sent = _make_session("203.0.113.20")
    await _drive_lines(srv, session, ["create brandnewpilot supersecretpw"])

    events = _auth_events(sent)
    assert len(events) == 1
    ev = events[0]
    assert ev["ok"] is True
    assert ev["kind"] == "create"
    assert ev["username"] == "brandnewpilot"


async def test_create_username_taken_emits_failure(server_db):
    srv = server_db
    assert await srv.db.create_account("takenname", "firstpassword") is not None

    session, sent = _make_session("203.0.113.21")
    await _drive_lines(srv, session, ["create takenname anotherpassword"])

    events = _auth_events(sent)
    assert len(events) == 1
    ev = events[0]
    assert ev["ok"] is False
    assert ev["kind"] == "create"
    assert ev["reason"] == "username_taken"


async def test_create_short_username_emits_validation_failure(server_db):
    srv = server_db
    # min_username_len defaults > 1; a single char is below it.
    session, sent = _make_session("203.0.113.22")
    await _drive_lines(srv, session, ["create x somepasswordhere"])

    events = _auth_events(sent)
    assert len(events) == 1
    ev = events[0]
    assert ev["ok"] is False
    assert ev["kind"] == "create"
    assert ev["reason"] == "username_too_short"
    # No account was created (validation rejected before create_account).
    assert session.account is None


# ── 3. telnet-safe: no JSON leaks to a telnet client ─────────────────────────

async def test_telnet_failure_emits_no_json(server_db):
    """A telnet session gets the text error but NO auth_status JSON line —
    ``send_json`` silently drops unknown types for non-WebSocket transports, so
    the producer is purely additive for telnet (which has no SPA form to drive)."""
    from server.session import Protocol
    srv = server_db
    session, sent = _make_session("203.0.113.30", protocol=Protocol.TELNET)
    await _drive_lines(srv, session, ["connect nobody wrongpass"])

    assert _auth_events(sent) == []
    # The human-readable error still reaches the telnet client.
    assert any("Invalid username or password." in s for s in sent)


# ── 4. producer/consumer contract pinned at both ends ────────────────────────

def test_producer_helper_wired_at_every_branch():
    # The fail-open helper exists...
    assert "_emit_auth_status" in GAME_SERVER_SRC
    assert 'send_json("auth_status"' in GAME_SERVER_SRC
    # ...and is invoked on success + failure of both connect and create plus
    # the token-auth handoff (9 outcomes: connect ok/bad/rate-limited, create
    # ok/taken/short-user/short-pass/rate-limited, token-auth ok) — guards
    # against a future branch dropping the structured signal and regressing to
    # regex-only.
    assert GAME_SERVER_SRC.count("self._emit_auth_status(") >= 9


def test_spa_consumer_contract_present():
    # The consumer the producer feeds must still exist (both ends of the
    # contract pinned: removing either without the other fails this).
    assert "case 'auth_status':" in CLIENT_HTML_SRC
    assert "function handleAuthStatus(" in CLIENT_HTML_SRC
