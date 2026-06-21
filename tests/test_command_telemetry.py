"""tests/test_command_telemetry.py — T3.19 telemetry for the command chokepoint.

The command-frequency histogram (catalog C — "a dead feature shows up as ~0
use") and the unknown-command "huh?" friction rate (catalog D — "which verbs
confuse") were the last broad utilization signals with no emitter. Every other
instrumented funnel (skill_check / craft / objective / influence / cp_award)
captures ONE subsystem; the command dispatcher is the single seam that sees the
WHOLE game, so one fail-open emit there yields the per-command + per-system
engagement split offline.

This suite proves the ``command`` event fires once per dispatched line at the
real chokepoint (``CommandParser._execute`` for resolved commands; the unknown
branch of ``parse_and_dispatch`` for misses), carries the canonical key (so
aliases/glued-prefixes/directions group together) plus the lean optional fields
(typed-alias, switches, char_id), honours the ``telemetry.command_sample``
tunable, and — the load-bearing contract — NEVER disturbs dispatch when
telemetry breaks.

Run: python3 -m pytest tests/test_command_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser.commands import (  # noqa: E402
    BaseCommand,
    CommandContext,
    CommandParser,
    CommandRegistry,
    _emit_command_telemetry,
)


def _events(ev_type="command"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeSession:
    """Just enough Session surface for parse_and_dispatch / _execute."""

    def __init__(self, *, character=None, in_game=True, sid=1):
        self.id = sid
        self.character = character
        self.is_in_game = in_game
        self.account = None
        self.lines: list = []

    async def send_line(self, msg=""):
        self.lines.append(msg)

    async def send_prompt(self):
        pass

    async def send_hud_update(self, **kw):
        pass


class _Ping(BaseCommand):
    key = "ping"
    aliases = ["pi"]

    async def execute(self, ctx):
        pass


def _ctx(session, command="ping", switches=None):
    return CommandContext(
        session=session,
        raw_input=command,
        command=command,
        args="",
        args_list=[],
        switches=switches or [],
        db=None,
        session_mgr=None,
    )


class CommandTelemetryHelperTests(unittest.TestCase):
    """Field assembly for _emit_command_telemetry (the shared seam)."""

    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    def test_matched_emits_canonical_key_and_char_id(self):
        ctx = _ctx(_FakeSession(character={"id": 7}), command="ping")
        _emit_command_telemetry(ctx, "ping", matched=True)
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertTrue(e["matched"])
        self.assertEqual(e["cmd"], "ping")
        self.assertEqual(e["char_id"], 7)
        # typed == cmd → omitted to keep the record lean
        self.assertNotIn("typed", e)
        self.assertNotIn("sw", e)

    def test_alias_records_typed_form(self):
        # Player typed "pi" but it resolved to canonical "ping".
        ctx = _ctx(_FakeSession(character={"id": 7}), command="pi")
        _emit_command_telemetry(ctx, "ping", matched=True)
        e = _events()[0]
        self.assertEqual(e["cmd"], "ping")
        self.assertEqual(e["typed"], "pi")

    def test_switches_recorded(self):
        ctx = _ctx(_FakeSession(character={"id": 7}),
                   command="+sheet", switches=["brief"])
        _emit_command_telemetry(ctx, "+sheet", matched=True)
        e = _events()[0]
        self.assertEqual(e["sw"], ["brief"])

    def test_no_character_omits_char_id(self):
        ctx = _ctx(_FakeSession(character=None), command="who")
        _emit_command_telemetry(ctx, "who", matched=True)
        e = _events()[0]
        self.assertNotIn("char_id", e)

    def test_unmatched_flag(self):
        ctx = _ctx(_FakeSession(character=None), command="zzznotacmd")
        _emit_command_telemetry(ctx, "zzznotacmd", matched=False)
        e = _events()[0]
        self.assertFalse(e["matched"])
        self.assertEqual(e["cmd"], "zzznotacmd")

    # ── sampling honours the tunable ──────────────────────────────────────
    def test_sample_zero_suppresses(self):
        tunables._TUNABLES["telemetry.command_sample"] = 0.0
        ctx = _ctx(_FakeSession(character={"id": 7}), command="ping")
        _emit_command_telemetry(ctx, "ping", matched=True)
        self.assertEqual(len(_events()), 0)

    def test_sample_default_captures(self):
        # No tunable loaded → default 1.0 → captured.
        ctx = _ctx(_FakeSession(character={"id": 7}), command="ping")
        _emit_command_telemetry(ctx, "ping", matched=True)
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: never raises ────────────────────────────────────────
    def test_fail_open_when_emit_raises(self):
        orig = telemetry.emit

        def _boom(*a, **k):
            raise RuntimeError("sink down")

        telemetry.emit = _boom
        try:
            ctx = _ctx(_FakeSession(character={"id": 7}), command="ping")
            # Must not raise.
            _emit_command_telemetry(ctx, "ping", matched=True)
        finally:
            telemetry.emit = orig

    def test_fail_open_when_session_missing(self):
        # Defensive: a ctx whose session is None must not raise.
        ctx = CommandContext(session=None, raw_input="ping", command="ping",
                             args="", args_list=[], switches=[])
        _emit_command_telemetry(ctx, "ping", matched=True)
        e = _events()[0]
        self.assertEqual(e["cmd"], "ping")
        self.assertNotIn("char_id", e)


class CommandTelemetryDispatchTests(unittest.TestCase):
    """The emit actually fires at the real dispatch chokepoints."""

    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()
        self.reg = CommandRegistry()
        self.reg.register(_Ping())
        self.parser = CommandParser(self.reg, db=None, session_mgr=None)

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    def test_resolved_command_emits_once_at_execute(self):
        sess = _FakeSession(character={"id": 7})
        ctx = _ctx(sess, command="ping")
        asyncio.run(self.parser._execute(self.reg.get("ping"), ctx))
        evs = _events()
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["matched"])
        self.assertEqual(evs[0]["cmd"], "ping")
        self.assertEqual(evs[0]["char_id"], 7)

    def test_unknown_command_emits_miss(self):
        # character=None so the NL-combat intercept is skipped; "zzznotacmd"
        # prefix-matches nothing in a one-command registry → genuine miss.
        sess = _FakeSession(character=None)
        asyncio.run(self.parser.parse_and_dispatch(sess, "zzznotacmd"))
        evs = _events()
        self.assertEqual(len(evs), 1)
        self.assertFalse(evs[0]["matched"])
        self.assertEqual(evs[0]["cmd"], "zzznotacmd")
        # The player still got the "Huh?" line (dispatch unaffected).
        self.assertTrue(any("Huh?" in ln for ln in sess.lines))

    def test_disabled_sink_still_dispatches(self):
        telemetry.configure(enabled=False)
        sess = _FakeSession(character={"id": 7})
        ctx = _ctx(sess, command="ping")
        asyncio.run(self.parser._execute(self.reg.get("ping"), ctx))
        self.assertEqual(len(_events()), 0)


if __name__ == "__main__":
    unittest.main()
