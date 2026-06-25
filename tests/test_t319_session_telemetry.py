# -*- coding: utf-8 -*-
"""tests/test_t319_session_telemetry.py — T3.19 telemetry breadth for the
session-lifecycle SINK (login + logout).

The economy/progression funnels capture what players DO once in-game, but
nothing recorded *how long they stay* or *how often they come back* — and a DB
scan can't reconstruct it (there is no login ledger). This drop adds ONE
fail-open, sample-tunable ``session`` event type tagged by ``phase``:

  * ``phase=login``  — emitted in ``game_server._character_select`` the moment a
    character enters the world (reaches IN_GAME). char_id / account_id / transport.
  * ``phase=logout`` — emitted in ``SessionManager.remove`` (the documented single
    chokepoint every disconnect funnels through), carrying play duration
    (login→logout), the full connect→disconnect span, transport, and
    ``reached_game`` so a bounce at the login screen is the funnel denominator.

This suite proves: the ``emit_session`` helper schema + str-id/account coercion +
None-drop; the ``_emit_session_end`` producer maps a torn-down session to the
right fields (duration vs connected span, reached_game, the login-bounce case);
``SessionManager.remove`` emits exactly once even when called twice (idempotent
teardown); the ``telemetry.session_sample`` tunable is honoured; the seams are
wired; and — the load-bearing contract — a broken sink NEVER disturbs login or
teardown.

Run: python -m pytest tests/test_t319_session_telemetry.py
"""
from __future__ import annotations

import json
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from server.session import SessionManager, _emit_session_end  # noqa: E402

REPO = PROJECT_ROOT


def _events(ev_type="session"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeSession:
    """Duck-typed stand-in carrying only what _emit_session_end / remove read."""

    def __init__(self, sid=1, char=None, account=None, login_at=None,
                 connected_at=None, protocol_value="websocket"):
        self.id = sid
        self.character = char
        self.account = account
        self.login_at = login_at
        self.connected_at = (connected_at if connected_at is not None
                             else time.time())
        self.protocol = types.SimpleNamespace(value=protocol_value)


class SessionTelemetryTests(unittest.TestCase):

    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    # ── helper schema: login envelope, coercion, None-drop ───────────────────
    def test_login_helper_schema(self):
        telemetry.emit_session("login", "42", account_id="7",
                               transport="websocket")
        e = _events()[0]
        self.assertEqual(e["ev"], "session")
        self.assertEqual(e["phase"], "login")
        self.assertEqual(e["char_id"], 42)        # str id coerced
        self.assertEqual(e["account_id"], 7)      # str account coerced
        self.assertEqual(e["transport"], "websocket")
        # login carries no duration / connected span / reached_game
        self.assertNotIn("duration_s", e)
        self.assertNotIn("connected_s", e)
        self.assertNotIn("reached_game", e)

    def test_logout_helper_schema(self):
        telemetry.emit_session("logout", 5, account_id=9, transport="telnet",
                               duration_s=123.456, connected_s=200.0,
                               reached_game=True)
        e = _events()[0]
        self.assertEqual(e["phase"], "logout")
        self.assertEqual(e["char_id"], 5)
        self.assertEqual(e["transport"], "telnet")
        self.assertEqual(e["duration_s"], 123.5)  # rounded to 0.1
        self.assertEqual(e["connected_s"], 200.0)
        self.assertTrue(e["reached_game"])

    def test_none_char_id_dropped(self):
        # a bounce at the login screen: no character ever selected
        telemetry.emit_session("logout", None, transport="telnet",
                               connected_s=4.0, reached_game=False)
        e = _events()[0]
        self.assertNotIn("char_id", e)
        self.assertEqual(e["connected_s"], 4.0)
        self.assertFalse(e["reached_game"])
        self.assertNotIn("duration_s", e)         # never reached the game

    def test_unparseable_account_id_preserved(self):
        telemetry.emit_session("login", 1, account_id="abc")
        self.assertEqual(_events()[0]["account_id"], "abc")

    def test_bad_duration_dropped_not_event(self):
        # a non-numeric duration must drop only that field, not the whole event
        telemetry.emit_session("logout", 1, duration_s="oops",
                               connected_s=10.0, reached_game=True)
        e = _events()[0]
        self.assertEqual(e["phase"], "logout")
        self.assertNotIn("duration_s", e)
        self.assertEqual(e["connected_s"], 10.0)

    # ── _emit_session_end producer: maps a torn-down session ─────────────────
    def test_producer_full_session(self):
        now = time.time()
        sess = _FakeSession(
            char={"id": 11, "name": "Hunter"},
            account={"id": 3},
            login_at=now - 100.0,
            connected_at=now - 130.0,
            protocol_value="websocket",
        )
        _emit_session_end(sess)
        e = _events()[0]
        self.assertEqual(e["phase"], "logout")
        self.assertEqual(e["char_id"], 11)
        self.assertEqual(e["account_id"], 3)
        self.assertEqual(e["transport"], "websocket")
        self.assertTrue(e["reached_game"])
        self.assertAlmostEqual(e["duration_s"], 100.0, delta=2.0)
        self.assertAlmostEqual(e["connected_s"], 130.0, delta=2.0)

    def test_producer_bounce_never_logged_in(self):
        # connected but never selected a character → no duration, no char_id,
        # reached_game False, but the connect span is still recorded.
        now = time.time()
        sess = _FakeSession(char=None, account=None, login_at=None,
                            connected_at=now - 8.0, protocol_value="telnet")
        _emit_session_end(sess)
        e = _events()[0]
        self.assertFalse(e["reached_game"])
        self.assertNotIn("char_id", e)
        self.assertNotIn("account_id", e)
        self.assertNotIn("duration_s", e)
        self.assertAlmostEqual(e["connected_s"], 8.0, delta=2.0)
        self.assertEqual(e["transport"], "telnet")

    def test_producer_mid_char_switch_window(self):
        # disconnect in the +char/switch window: the departing character was
        # cleared (character=None) but login_at is still the departed char's
        # stamp. Must NOT report a reached_game=True logout with a stale
        # duration + no char_id — it reads as not-yet-in-game.
        now = time.time()
        sess = _FakeSession(char=None, account={"id": 3},
                            login_at=now - 50.0, connected_at=now - 80.0,
                            protocol_value="websocket")
        _emit_session_end(sess)
        e = _events()[0]
        self.assertFalse(e["reached_game"])
        self.assertNotIn("char_id", e)
        self.assertNotIn("duration_s", e)        # no stale duration leaked
        self.assertAlmostEqual(e["connected_s"], 80.0, delta=2.0)

    # ── SessionManager.remove: single chokepoint, once-only ──────────────────
    def test_remove_emits_logout_once(self):
        mgr = SessionManager()
        sess = _FakeSession(sid=77, char={"id": 4}, account={"id": 2},
                            login_at=time.time() - 5.0)
        mgr.add(sess)
        mgr.remove(sess)
        mgr.remove(sess)          # second call (transport finally after a kick)
        evs = _events()
        self.assertEqual(len(evs), 1)         # idempotent — emitted exactly once
        self.assertEqual(evs[0]["phase"], "logout")
        self.assertEqual(evs[0]["char_id"], 4)
        self.assertTrue(evs[0]["reached_game"])

    def test_remove_unknown_session_emits_nothing(self):
        mgr = SessionManager()
        sess = _FakeSession(sid=5)
        mgr.remove(sess)          # never added → nothing to tear down
        self.assertEqual(len(_events()), 0)

    # ── sampling honours the tunable ─────────────────────────────────────────
    def test_sample_zero_suppresses(self):
        tunables._TUNABLES["telemetry.session_sample"] = 0.0
        telemetry.emit_session("login", 1, transport="telnet")
        self.assertEqual(len(_events()), 0)

    def test_sample_default_captures(self):
        telemetry.emit_session("login", 1)
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs teardown / login ──────────
    def test_fail_open_producer(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        sess = _FakeSession(char={"id": 1}, login_at=time.time())
        with mock.patch.object(telemetry, "emit", _boom):
            _emit_session_end(sess)               # must not raise

    def test_fail_open_remove(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        mgr = SessionManager()
        sess = _FakeSession(sid=9, char={"id": 1}, login_at=time.time())
        mgr.add(sess)
        with mock.patch.object(telemetry, "emit", _boom):
            mgr.remove(sess)                      # must not raise
        # teardown still happened: the session is gone from the registry
        self.assertIsNone(mgr.get(9))

    # ── seams wired + tunable registered (drift pins) ────────────────────────
    def test_login_seam_wired(self):
        src = (REPO / "server" / "game_server.py").read_text(encoding="utf-8")
        self.assertIn("emit_session(", src)
        self.assertIn("session.login_at", src)

    def test_logout_seam_wired(self):
        src = (REPO / "server" / "session.py").read_text(encoding="utf-8")
        self.assertIn("def _emit_session_end(", src)
        self.assertIn("_emit_session_end(session)", src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.session_sample:", ty)


if __name__ == "__main__":
    unittest.main()
