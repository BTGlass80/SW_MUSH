# -*- coding: utf-8 -*-
"""T3.21 Blocker 2 (protocol half) — per-IP throttle on the raw telnet/WS
pre-auth `connect` / `create` login loop.

THE GAP (verified at HEAD before the fix):
  The PORTAL login path (POST /api/portal/login) is per-IP throttled
  (web_portal._login_rate_ok, 10/60s). The raw protocol login loop in
  game_server.handle_new_session — fed verbatim by BOTH transports (telnet
  `_telnet_read_loop` and the public web port's WebSocket `{"input": ...}`
  channel) — was NOT. db.authenticate's lockout is PER-ACCOUNT (5 fails /
  5 min), so credential-stuffing ACROSS many accounts from one socket, and
  spamming `create` to burn bcrypt CPU on the shared event loop, were both
  unbounded.

THE FIX:
  Session.client_ip is captured at each transport seam (telnet/WS peername;
  the aiohttp web port via the spoof-resistant api._get_client_ip). A shared
  per-IP sliding-window bucket (_preauth_rate_ok, 10/60s) gates BOTH `connect`
  and `create` before any DB / bcrypt work; the throttled attempt is rejected
  with a wait-and-retry message and never reaches authenticate()/create_account().

These tests prove (1) the limiter admits up to MAX then blocks and resets,
(2) Session carries a client_ip the handlers set, (3) the seams are wired,
and (4) end-to-end: an 11th `connect` from one IP is rejected without ever
calling db.authenticate, while a different IP is unaffected.
"""
import asyncio
import os
import pathlib
import tempfile

import pytest

from server import game_server
from server.game_server import (
    _preauth_rate_ok,
    _reset_preauth_throttle,
    _PREAUTH_RATE_MAX,
)

_SRV = pathlib.Path(__file__).resolve().parent.parent / "server"
GAME_SERVER_SRC = (_SRV / "game_server.py").read_text(encoding="utf-8")
TELNET_SRC = (_SRV / "telnet_handler.py").read_text(encoding="utf-8")
WEB_CLIENT_SRC = (_SRV / "web_client.py").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_throttle():
    """Each test starts with empty per-IP buckets."""
    _reset_preauth_throttle()
    yield
    _reset_preauth_throttle()


# ── 1. The limiter admits up to MAX, then blocks; reset clears ───────────────

def test_limiter_admits_then_blocks():
    ip = "203.0.113.7"
    # The first MAX calls are admitted (all within one 60s window).
    for i in range(_PREAUTH_RATE_MAX):
        assert _preauth_rate_ok(ip) is True, f"call {i} should be admitted"
    # The next one is throttled.
    assert _preauth_rate_ok(ip) is False
    assert _preauth_rate_ok(ip) is False


def test_limiter_is_per_ip():
    a, b = "198.51.100.1", "198.51.100.2"
    for _ in range(_PREAUTH_RATE_MAX):
        assert _preauth_rate_ok(a) is True
    assert _preauth_rate_ok(a) is False
    # A different IP has its own independent budget.
    assert _preauth_rate_ok(b) is True


def test_reset_clears_buckets():
    ip = "192.0.2.5"
    for _ in range(_PREAUTH_RATE_MAX):
        _preauth_rate_ok(ip)
    assert _preauth_rate_ok(ip) is False
    _reset_preauth_throttle()
    assert _preauth_rate_ok(ip) is True


def test_unknown_sentinel_is_exempt():
    # The not-captured sentinel never throttles: a live socket always has a
    # peername (an attacker can't force "unknown"), so this fails open and
    # avoids coupling unrelated callers through one shared bucket.
    for _ in range(_PREAUTH_RATE_MAX * 3):
        assert _preauth_rate_ok("unknown") is True
    assert _preauth_rate_ok("") is True


# ── 2. Session carries a client_ip the handlers can set ──────────────────────

def test_session_has_client_ip_default():
    from server.session import Session, Protocol

    async def _noop(*_a, **_k):
        return None

    s = Session(Protocol.TELNET, _noop, _noop, width=80, height=24)
    assert s.client_ip == "unknown"
    s.client_ip = "10.0.0.9"
    assert s.client_ip == "10.0.0.9"


# ── 3. The seams are wired ───────────────────────────────────────────────────

def test_login_loop_throttles_before_auth():
    # The connect branch checks the limiter before authenticate(), and the
    # create branch before create_account().
    assert "_preauth_rate_ok(session.client_ip)" in GAME_SERVER_SRC
    # Two call sites (connect + create), one shared bucket.
    assert GAME_SERVER_SRC.count("_preauth_rate_ok(session.client_ip)") == 2


def test_telnet_captures_peer_ip():
    assert 'writer.get_extra_info("peername")' in TELNET_SRC
    assert "session.client_ip" in TELNET_SRC


def test_web_client_captures_client_ip_spoof_resistant():
    assert "_get_client_ip(request)" in WEB_CLIENT_SRC
    assert "session.client_ip" in WEB_CLIENT_SRC


# ── 4. End-to-end against the real login loop ────────────────────────────────

@pytest.fixture
async def server_db():
    """A minimal booted GameServer with a real temp DB (no world build)."""
    from server.config import Config
    from engine.era_state import set_active_config
    from server.game_server import GameServer

    tmpdir = tempfile.mkdtemp(prefix="sw_mush_preauth_")
    db_path = os.path.join(tmpdir, "preauth.db")
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


def _make_session(client_ip: str):
    from server.session import Session, Protocol
    sent: list = []

    async def _send(payload):
        sent.append(str(payload))

    async def _close():
        return None

    sess = Session(
        protocol=Protocol.WEBSOCKET,
        send_callback=_send, close_callback=_close,
        width=80, height=40,
    )
    sess.client_ip = client_ip
    return sess, sent


async def _drive_lines(srv, session, lines, *, max_wait=3.0):
    """Run the login loop, feed several lines, wait until the loop has DRAINED
    every queued line (polling the input queue rather than a fixed sleep, so the
    end-to-end assertions don't flake under load), then tear down."""
    task = asyncio.create_task(srv.handle_new_session(session, reader=None))
    await asyncio.sleep(0.02)
    for line in lines:
        session.feed_input(line)
    # Poll until the loop has consumed every queued line...
    waited = 0.0
    while waited < max_wait:
        await asyncio.sleep(0.02)
        waited += 0.02
        if session._input_queue.empty():
            break
    # ...then a short grace for the final line's authenticate()/create_account().
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def test_connect_flood_throttled_without_reaching_auth(server_db, monkeypatch):
    """The (MAX+1)th connect from one IP is rejected before authenticate()."""
    srv = server_db

    calls = {"n": 0}
    orig = srv.db.authenticate

    async def _counting_auth(username, password):
        calls["n"] += 1
        return await orig(username, password)

    monkeypatch.setattr(srv.db, "authenticate", _counting_auth)

    session, sent = _make_session("203.0.113.50")
    # MAX+3 bad-credential connects from one IP.
    lines = ["connect nobody wrongpass"] * (_PREAUTH_RATE_MAX + 3)
    await _drive_lines(srv, session, lines)

    # Only the first MAX reached authenticate(); the rest were throttled.
    assert calls["n"] == _PREAUTH_RATE_MAX
    # The player saw the throttle notice.
    assert any("Too many login attempts" in s for s in sent)


async def test_other_ip_unaffected_by_neighbor_flood(server_db, monkeypatch):
    """One IP exhausting its budget does not block a different IP."""
    srv = server_db

    calls = {"n": 0}

    async def _counting_auth(username, password):
        calls["n"] += 1
        return None  # always invalid

    monkeypatch.setattr(srv.db, "authenticate", _counting_auth)

    # Exhaust IP A.
    sess_a, _ = _make_session("203.0.113.60")
    await _drive_lines(srv, sess_a, ["connect a b"] * (_PREAUTH_RATE_MAX + 2))
    assert calls["n"] == _PREAUTH_RATE_MAX

    # A fresh IP still gets through to authenticate().
    sess_b, sent_b = _make_session("203.0.113.61")
    await _drive_lines(srv, sess_b, ["connect c d"])
    assert calls["n"] == _PREAUTH_RATE_MAX + 1
    assert not any("Too many login attempts" in s for s in sent_b)


async def test_legit_single_login_not_throttled(server_db):
    """A normal user logging in once is unaffected and reaches char-select."""
    srv = server_db
    # The protocol login splits on whitespace and reads parts[2] as the
    # password, so use a single-token password here.
    aid = await srv.db.create_account("realuser", "correcthorsebattery")
    assert aid is not None

    selected: list = []

    async def _rec_select(session):
        selected.append(session)
    srv._character_select = _rec_select  # type: ignore[assignment]

    session, sent = _make_session("203.0.113.70")
    await _drive_lines(srv, session, ["connect realuser correcthorsebattery"])

    from server.session import SessionState
    assert session.account is not None
    assert session.account["id"] == aid
    assert session.state == SessionState.AUTHENTICATED
    assert selected == [session]
    assert not any("Too many login attempts" in s for s in sent)
