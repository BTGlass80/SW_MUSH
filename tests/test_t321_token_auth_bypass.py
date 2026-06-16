# -*- coding: utf-8 -*-
"""T3.21 security — close the unauthenticated `__token_auth__` auth-bypass.

THE BUG (verified at HEAD before the fix):
  The web-chargen "auto-login" handoff was a synthetic command
  `__token_auth__ <account_id>` fed into the shared `handle_new_session`
  login loop. The branch trusted that the caller (web_client.py) had already
  verified a token and just did `get_account(int(parts[1]))` -> login, no
  password. But BOTH transports feed RAW client input into that same loop:
    - Telnet: `_telnet_read_loop` -> `session.feed_input(line)` verbatim.
    - WebSocket (the PUBLIC web port): `{"input": "..."}` -> `feed_input`.
  So any unauthenticated client could send `__token_auth__ 1` and seize
  account #1 (sequential ids -> trivial enumeration) with no credentials.

THE FIX:
  The `__token_auth__` branch is now the AUTHORITATIVE verifier: its argument
  is the HMAC-signed login token (not a bare id), and it calls
  `verify_login_token` itself. web_client.py feeds the signed token straight
  through instead of resolving it to an account_id. A forged/guessed argument
  fails `verify_login_token` -> no auth.

These tests prove (1) the verifier rejects a bare id / garbage and accepts a
genuine token, (2) the two call sites are wired correctly, and (3) end-to-end:
driving the real login loop, a forged `__token_auth__ 1` does NOT authenticate
while a server-minted token does.
"""
import asyncio
import os
import pathlib
import tempfile

import pytest

from server import api
from server.api import create_login_token, verify_login_token

_SRV = pathlib.Path(__file__).resolve().parent.parent / "server"
GAME_SERVER_SRC = (_SRV / "game_server.py").read_text(encoding="utf-8")
WEB_CLIENT_SRC = (_SRV / "web_client.py").read_text(encoding="utf-8")


# ── 1. The verifier rejects forgeable inputs, accepts a genuine token ────────

def test_bare_account_id_does_not_verify():
    # The crux of the bypass: a raw integer string is NOT a valid token.
    assert verify_login_token("1") is None
    assert verify_login_token("5") is None
    assert verify_login_token("42") is None


def test_garbage_token_does_not_verify():
    assert verify_login_token("") is None
    assert verify_login_token("not.a.token") is None
    assert verify_login_token("__token_auth__ 1") is None


def test_genuine_token_round_trips():
    # The legitimate web handoff still works end-to-end through the verifier.
    tok = create_login_token(7)
    assert verify_login_token(tok) == 7


def test_token_with_tampered_signature_rejected():
    tok = create_login_token(3)
    payload, _sig = tok.rsplit(".", 1)
    forged = payload + ".0000000000000000"
    assert verify_login_token(forged) is None


# ── 2. Both call sites are wired to the token, not a bare id ─────────────────

def test_branch_verifies_token_not_bare_int():
    # The branch must call verify_login_token on the argument...
    assert "verify_login_token(parts[1])" in GAME_SERVER_SRC
    # ...and must NOT trust a caller-supplied account_id integer.
    assert "account_id = int(parts[1])" not in GAME_SERVER_SRC


def test_web_client_feeds_token_not_account_id():
    # The producer hands the signed token straight through.
    assert 'f"__token_auth__ {token}"' in WEB_CLIENT_SRC
    # The old bare-id feed is gone.
    assert "__token_auth__ {account_id}" not in WEB_CLIENT_SRC


# ── 3. End-to-end against the real login loop ────────────────────────────────

@pytest.fixture
async def server_db():
    """A minimal booted GameServer with a real temp DB (no world build).

    The `__token_auth__` auth decision needs only the accounts table and the
    session manager, so we skip the (slow) world/org seed. `_character_select`
    is monkeypatched to a recorder so the success path never touches the world.
    """
    from server.config import Config
    from engine.era_state import set_active_config
    from server.game_server import GameServer

    tmpdir = tempfile.mkdtemp(prefix="sw_mush_tokenauth_")
    db_path = os.path.join(tmpdir, "tokenauth.db")
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

    # Record _character_select calls; never run the real chargen/world path.
    selected: list = []

    async def _fake_select(session):
        selected.append(session)
    srv._character_select = _fake_select  # type: ignore[assignment]

    yield srv, selected

    try:
        await srv.db.close()
    except Exception:
        pass


def _make_session():
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
    return sess, sent


async def _drive(srv, session, line, *, settle=0.25):
    """Run the login loop, feed one line, let it settle, then tear down."""
    task = asyncio.create_task(srv.handle_new_session(session, reader=None))
    # Let the loop reach its first receive() and emit the banner.
    await asyncio.sleep(0.02)
    session.feed_input(line)
    await asyncio.sleep(settle)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def test_forged_bare_id_does_not_authenticate(server_db):
    """The exploit input: `__token_auth__ 1` must NOT log anyone in."""
    from server.session import SessionState
    srv, selected = server_db
    # Seed account #1 so a successful bypass would actually have a target.
    aid = await srv.db.create_account("victim", "correct horse battery")
    assert aid is not None

    session, _sent = _make_session()
    await _drive(srv, session, f"__token_auth__ {aid}")

    assert session.account is None, "forged bare-id token authenticated a session!"
    assert session.state == SessionState.CONNECTED
    assert selected == [], "_character_select ran on a forged token"


async def test_forged_garbage_does_not_authenticate(server_db):
    from server.session import SessionState
    srv, selected = server_db
    await srv.db.create_account("victim2", "correct horse battery")
    session, _sent = _make_session()
    await _drive(srv, session, "__token_auth__ deadbeef.cafebabe")
    assert session.account is None
    assert session.state == SessionState.CONNECTED
    assert selected == []


async def test_genuine_token_authenticates(server_db):
    """The legitimate handoff still works: a server-minted token logs in."""
    from server.session import SessionState
    srv, selected = server_db
    aid = await srv.db.create_account("realuser", "correct horse battery")
    assert aid is not None
    tok = create_login_token(aid)

    session, _sent = _make_session()
    await _drive(srv, session, f"__token_auth__ {tok}")

    assert session.account is not None, "a genuine token failed to authenticate"
    assert session.account["id"] == aid
    assert session.state == SessionState.AUTHENTICATED
    assert selected == [session], "_character_select did not run for a valid token"
