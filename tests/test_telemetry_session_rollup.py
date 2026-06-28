# -*- coding: utf-8 -*-
"""tests/test_telemetry_session_rollup.py — T3.19 telemetry READ-SIDE: the
``session`` rollup in ``telemetry.summarize`` + the ``@balance sessions``
sub-board.

The PRODUCER half has been wired since the session-lifecycle drop: a login
emits ``emit_session("login", ...)`` when a character enters the world
(``server/game_server.py``) and EVERY disconnect funnels through one chokepoint
that emits ``emit_session("logout", ..., duration_s, connected_s, reached_game)``
(``server/session.py::SessionManager.remove`` → ``_emit_session_end``) — the
engagement/retention funnel (how long players stay, the connect→login
conversion, the web-vs-telnet mix).

But the CONSUMER half was missing: ``summarize`` rolled up grind / cp_income /
objective / wild_encounter / communal / chain_reward but DROPPED ``session`` on
the floor, and ``@balance`` had grind/cp/objectives/chains/encounters/events
sub-boards but no sessions board — so the richest launch retention signal
appeared nowhere except the generic event-mix count + the raw dump. This drop
adds the consumer: a ``session`` rollup in ``summarize`` (login/logout counts,
connect→login conversion, play-time avg/max, connected-span avg, distinct
players/accounts, transport mix) and a ``@balance sessions`` board.

Mirrors the chain-rollup guard (``tests/test_telemetry_chain_rollup.py``): the
rollup buckets the REAL producer field names + tolerates junk; the session key
is additive (siblings unperturbed); the board renders/gates/degrades; and the
REAL ``emit_session`` producer feeds the new consumer end-to-end.

Run: python -m pytest tests/test_telemetry_session_rollup.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SW_ERA", "clone_wars")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser.commands import AccessLevel, CommandContext  # noqa: E402
from parser import director_commands as dc  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeSession:
    def __init__(self):
        self.lines: list = []
        self.char_name = "Admin"
        self.account = {"username": "admin"}

    async def send_line(self, msg=""):
        self.lines.append(msg)


def _ctx(session, args=""):
    return CommandContext(
        session=session,
        raw_input=f"@balance {args}".strip(),
        command="@balance",
        args=args,
        args_list=args.split(),
        switches=[],
        db=None,
        session_mgr=None,
    )


# Mirrors the REAL producer envelope (server/game_server.py + server/session.py):
#   login  : {phase, char_id, account_id, transport}
#   logout : {phase, char_id, account_id, transport, duration_s, connected_s,
#             reached_game}
def _login(*, char_id=1, account_id=10, transport="websocket"):
    return {"ts": 100.0, "ev": "session", "phase": "login",
            "char_id": char_id, "account_id": account_id,
            "transport": transport}


def _logout(*, char_id=1, account_id=10, transport="websocket",
            duration_s=600.0, connected_s=620.0, reached_game=True):
    rec = {"ts": 200.0, "ev": "session", "phase": "logout",
           "char_id": char_id, "account_id": account_id,
           "transport": transport, "reached_game": reached_game}
    if duration_s is not None:
        rec["duration_s"] = duration_s
    if connected_s is not None:
        rec["connected_s"] = connected_s
    return rec


# ── summarize: the session rollup ─────────────────────────────────────────────
class SummarizeSessionTests(unittest.TestCase):
    def _mix(self):
        return [
            _login(char_id=1, account_id=10, transport="websocket"),
            _login(char_id=2, account_id=20, transport="telnet"),
            _logout(char_id=1, account_id=10, transport="websocket",
                    duration_s=600.0, connected_s=620.0, reached_game=True),
            _logout(char_id=2, account_id=20, transport="telnet",
                    duration_s=300.0, connected_s=305.0, reached_game=True),
            # a connection that bounced at the login screen (never reached game)
            _logout(char_id=None, account_id=30, transport="websocket",
                    duration_s=None, connected_s=15.0, reached_game=False),
        ]

    def test_session_rollup_top_level(self):
        s = telemetry.summarize(self._mix())["session"]
        self.assertEqual(s["logins"], 2)
        self.assertEqual(s["logouts"], 3)
        self.assertEqual(s["reached_game"], 2)
        # avg play time over the two sessions that reached the game
        self.assertAlmostEqual(s["avg_duration_s"], 450.0)
        self.assertAlmostEqual(s["max_duration_s"], 600.0)
        # connected span averaged over all three logouts (incl. the bounce)
        self.assertAlmostEqual(s["avg_connected_s"], (620.0 + 305.0 + 15.0) / 3)

    def test_distinct_players_and_accounts(self):
        s = telemetry.summarize(self._mix())["session"]
        # distinct non-None char_ids seen across login OR logout: {1, 2}
        self.assertEqual(s["players"], 2)
        # distinct accounts (the retention join key): {10, 20, 30}
        self.assertEqual(s["accounts"], 3)

    def test_transport_mix_per_connection(self):
        # Transport is counted once per CONNECTION (logout only), not per event,
        # so two complete web connections + one telnet read 2/1, not 3/2.
        s = telemetry.summarize(self._mix())["session"]
        mix = dict(s["by_transport"])
        self.assertEqual(mix.get("websocket"), 2)
        self.assertEqual(mix.get("telnet"), 1)

    def test_duration_only_from_reached_logouts(self):
        # A logout with no duration (the login-screen bounce) must not drag the
        # average toward zero — it is excluded from the play-time mean entirely.
        s = telemetry.summarize([
            _logout(char_id=1, duration_s=1000.0, connected_s=1010.0,
                    reached_game=True),
            _logout(char_id=None, duration_s=None, connected_s=5.0,
                    reached_game=False),
        ])["session"]
        self.assertEqual(s["logouts"], 2)
        self.assertEqual(s["reached_game"], 1)
        self.assertAlmostEqual(s["avg_duration_s"], 1000.0)   # not 500
        self.assertAlmostEqual(s["max_duration_s"], 1000.0)

    def test_session_key_additive_other_rollups_intact(self):
        s = telemetry.summarize([
            {"ts": 1.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "npc_name": "Swoop Thug"},
            {"ts": 2.0, "ev": "objective", "kind": "mission",
             "phase": "complete", "reward": 500},
            _login(char_id=9),
            _logout(char_id=9, duration_s=42.0),
        ])
        for key in ("grind", "cp_income", "objective", "chain",
                    "wild_encounter", "communal", "session"):
            self.assertIn(key, s)
        self.assertEqual(s["grind"]["kills"], 1)
        self.assertEqual(s["objective"]["mission"]["complete"], 1)
        self.assertEqual(s["session"]["logins"], 1)
        self.assertEqual(s["session"]["logouts"], 1)

    def test_empty_and_junk_tolerated(self):
        s0 = telemetry.summarize([])["session"]
        self.assertEqual(s0["logins"], 0)
        self.assertEqual(s0["logouts"], 0)
        self.assertEqual(s0["avg_duration_s"], 0.0)
        self.assertEqual(s0["by_transport"], [])
        self.assertEqual(s0["players"], 0)
        # bad duration type is ignored (not crashed on); the logout still counts
        s1 = telemetry.summarize([
            {"ev": "session", "phase": "logout", "duration_s": "bad",
             "connected_s": None, "transport": "telnet", "reached_game": True},
        ])["session"]
        self.assertEqual(s1["logouts"], 1)
        self.assertEqual(s1["reached_game"], 1)
        self.assertEqual(s1["avg_duration_s"], 0.0)   # no valid duration
        self.assertEqual(dict(s1["by_transport"]).get("telnet"), 1)

    def test_unknown_phase_neither_login_nor_logout(self):
        # A malformed phase neither logs in nor out, and (since transport is
        # logout-scoped) does not perturb the mix — but distinct players still
        # accrues from its char_id.
        s = telemetry.summarize([
            {"ev": "session", "phase": "weird", "char_id": 5,
             "account_id": 50, "transport": "telnet"},
        ])["session"]
        self.assertEqual(s["logins"], 0)
        self.assertEqual(s["logouts"], 0)
        self.assertEqual(s["by_transport"], [])
        self.assertEqual(s["players"], 1)
        self.assertEqual(s["accounts"], 1)


# ── @balance sessions board ───────────────────────────────────────────────────
class _IsolatedTelemetryTest(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        self._tmp = tempfile.mkdtemp(prefix="swmush_tele_sess_")
        self._path = os.path.join(self._tmp, "events.jsonl")
        telemetry.configure(path=self._path, enabled=True)

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
            os.rmdir(self._tmp)
        except OSError:
            pass


class BalanceSessionsBoardTests(_IsolatedTelemetryTest):
    def _emit_session_sample(self):
        telemetry.emit("session", {"phase": "login", "char_id": 1,
                                   "account_id": 10, "transport": "websocket"})
        telemetry.emit("session", {"phase": "logout", "char_id": 1,
                                   "account_id": 10, "transport": "websocket",
                                   "duration_s": 720.0, "connected_s": 740.0,
                                   "reached_game": True})

    def test_sessions_subcommand_renders_funnel(self):
        self._emit_session_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "sessions")))
        out = "\n".join(sess.lines)
        self.assertIn("SESSIONS / ENGAGEMENT", out)
        self.assertIn("reached game", out)
        self.assertIn("websocket", out)
        # other boards are NOT shown under the sessions sub
        self.assertNotIn("MOB GRIND", out)

    def test_session_alias_accepted(self):
        # singular 'session' is an accepted alias for the board
        self._emit_session_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "session")))
        out = "\n".join(sess.lines)
        self.assertIn("SESSIONS / ENGAGEMENT", out)

    def test_overview_includes_session_section(self):
        self._emit_session_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("SESSIONS / ENGAGEMENT", out)
        self.assertIn("OBJECTIVE FUNNEL", out)   # siblings still render

    def test_session_section_absent_under_other_sub(self):
        self._emit_session_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "grind")))
        out = "\n".join(sess.lines)
        self.assertNotIn("SESSIONS / ENGAGEMENT", out)

    def test_sessions_board_degrades_with_no_session_data(self):
        # Some telemetry exists (so the dashboard renders) but no session events.
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 5,
                                      "npc_name": "Womp Rat"})
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "sessions")))
        out = "\n".join(sess.lines)
        self.assertIn("no session events recorded", out)


# ── _fmt_dur formatter (the board's play-time / connected-span helper) ─────────
class FmtDurTests(unittest.TestCase):
    def test_compact_durations(self):
        self.assertEqual(dc._fmt_dur(0), "0s")
        self.assertEqual(dc._fmt_dur(45), "45s")
        self.assertEqual(dc._fmt_dur(312), "5m 12s")
        self.assertEqual(dc._fmt_dur(3 * 3600 + 4 * 60), "3h 4m")

    def test_bad_input_is_soft(self):
        self.assertEqual(dc._fmt_dur(None), "—")
        self.assertEqual(dc._fmt_dur("nope"), "—")


# ── producer → consumer round-trip (the load-bearing contract) ────────────────
class ProducerToConsumerTests(_IsolatedTelemetryTest):
    def test_real_emit_session_feeds_the_rollup(self):
        # Drive the REAL emit_session producer helper (the same fn the server
        # calls), flush to the isolated sink, then read it back through the REAL
        # consumer path (read_recent + summarize), and confirm the admin board
        # surfaces it from the same on-disk record.
        telemetry.emit_session("login", char_id=7, account_id=70,
                               transport="websocket")
        telemetry.emit_session("logout", char_id=7, account_id=70,
                               transport="websocket", duration_s=480.0,
                               connected_s=495.0, reached_game=True)
        telemetry.get_sink().flush()

        events = telemetry.read_recent()
        s = telemetry.summarize(events)["session"]
        self.assertEqual(s["logins"], 1)
        self.assertEqual(s["logouts"], 1)
        self.assertEqual(s["reached_game"], 1)
        self.assertAlmostEqual(s["avg_duration_s"], 480.0)
        self.assertEqual(s["players"], 1)
        self.assertEqual(s["accounts"], 1)
        self.assertEqual(dict(s["by_transport"]).get("websocket"), 1)

        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "sessions")))
        out = "\n".join(sess.lines)
        self.assertIn("SESSIONS / ENGAGEMENT", out)
        self.assertIn("reached game", out)


if __name__ == "__main__":
    unittest.main()
