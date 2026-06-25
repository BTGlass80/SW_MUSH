# -*- coding: utf-8 -*-
"""tests/test_t319_balance_dashboard.py — T3.19 telemetry READ-SIDE: the
``@balance`` admin dashboard + the engine/telemetry.py aggregation helpers.

The emit side of T3.19 is saturated (24+ event types produced across the
engine), but until now there was no in-game way to SEE that data — an admin had
to read the raw JSON-line dumps off the box. This drop adds the read side:

  - ``TelemetrySink.peek()``         — copy the un-flushed buffer WITHOUT draining
  - ``telemetry.read_recent[_async]``— bounded on-disk tail + buffer, fail-open
  - ``telemetry.summarize``          — pure rollups into balance-tuning signals
  - ``@balance`` (BalanceCommand)    — the ADMIN dashboard rendering those rollups

This suite proves: peek is non-destructive; the readers are bounded + fail-open
+ never double-count buffer vs disk; summarize rolls the real producer field
names (grind_kill / cp_income / objective / wild_encounter / communal_*) into the
right aggregates and tolerates junk; and the command renders every section,
degrades cleanly with no data, honours the `raw` sub, and is ADMIN-gated +
registered.

Run: python -m pytest tests/test_t319_balance_dashboard.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

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


class _IsolatedTelemetryTest(unittest.TestCase):
    """Each test gets a fresh sink pointed at a throwaway temp file so the
    disk read can never pick up the dev box's real logs/telemetry dump."""

    def setUp(self):
        tunables.reset_tunables()
        self._tmp = tempfile.mkdtemp(prefix="swmush_tele_")
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


# ── peek / read_recent ───────────────────────────────────────────────────────
class ReadSideTests(_IsolatedTelemetryTest):
    def test_peek_does_not_drain(self):
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 10})
        sink = telemetry.get_sink()
        peeked = sink.peek()
        self.assertEqual(len(peeked), 1)
        # peeking again still sees it — buffer untouched
        self.assertEqual(len(sink.peek()), 1)
        # and a real drain still yields the event (peek didn't consume it)
        self.assertEqual(len(sink.drain()), 1)

    def test_parse_lines_skips_blank_and_malformed(self):
        recs = telemetry._parse_lines(
            ['{"ev":"a"}', "", "   ", "not json", "[1,2]", '{"ev":"b"}'])
        self.assertEqual([r["ev"] for r in recs], ["a", "b"])

    def test_read_recent_combines_disk_and_buffer_no_double_count(self):
        # One event on disk (flushed), one still in the buffer.
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 10})
        self.assertEqual(telemetry.get_sink().flush(), 1)   # buffer → disk
        telemetry.emit("grind_kill", {"char_id": 2, "reward": 20})  # buffered
        recs = telemetry.read_recent()
        self.assertEqual(len(recs), 2)
        self.assertEqual({r["char_id"] for r in recs}, {1, 2})

    def test_read_recent_disk_only(self):
        telemetry.emit("cp_income", {"source": "scene"})
        telemetry.get_sink().flush()
        recs = telemetry.read_recent(include_buffer=False)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["source"], "scene")

    def test_read_recent_limit_keeps_most_recent(self):
        for i in range(10):
            telemetry.emit("command", {"n": i})
        recs = telemetry.read_recent(limit=3)
        self.assertEqual([r["n"] for r in recs], [7, 8, 9])

    def test_read_recent_missing_file_is_empty(self):
        # No emits, no file → fail-open empty, no error.
        self.assertEqual(telemetry.read_recent(), [])

    def test_read_recent_async_matches_sync(self):
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 10})
        telemetry.get_sink().flush()
        telemetry.emit("grind_kill", {"char_id": 2, "reward": 20})
        recs = _run(telemetry.read_recent_async())
        self.assertEqual(len(recs), 2)


# ── summarize ────────────────────────────────────────────────────────────────
class SummarizeTests(unittest.TestCase):
    def _mix(self):
        return [
            {"ts": 100.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "at_cap": False, "over_cap": False, "npc_name": "Swoop Thug"},
            {"ts": 110.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "at_cap": True, "over_cap": False, "npc_name": "Swoop Thug"},
            {"ts": 120.0, "ev": "grind_kill", "char_id": 2, "reward": 3,
             "at_cap": True, "over_cap": True, "npc_name": "Womp Rat"},
            {"ts": 130.0, "ev": "cp_income", "source": "scene",
             "cp_gained": 1, "ticks": 5, "at_cap": False},
            {"ts": 140.0, "ev": "cp_income", "source": "kudos",
             "cp_gained": 0, "ticks": 2, "at_cap": True},
            {"ts": 150.0, "ev": "objective", "kind": "mission",
             "phase": "start"},
            {"ts": 160.0, "ev": "objective", "kind": "mission",
             "phase": "complete", "reward": 500},
            {"ts": 170.0, "ev": "objective", "kind": "bounty",
             "phase": "abandon"},
            {"ts": 180.0, "ev": "wild_encounter", "fired": True, "band": 3},
            {"ts": 190.0, "ev": "wild_encounter", "fired": False, "band": 1},
            {"ts": 200.0, "ev": "communal_menace", "tier_changed": True},
            {"ts": 210.0, "ev": "communal_strike", "success": True},
            {"ts": 220.0, "ev": "communal_strike", "success": False},
        ]

    def test_envelope(self):
        s = telemetry.summarize(self._mix())
        self.assertEqual(s["total"], 13)
        self.assertEqual(s["first_ts"], 100.0)
        self.assertEqual(s["last_ts"], 220.0)
        bt = dict(s["by_type"])
        self.assertEqual(bt["grind_kill"], 3)
        self.assertEqual(bt["objective"], 3)

    def test_grind_rollup(self):
        g = telemetry.summarize(self._mix())["grind"]
        self.assertEqual(g["kills"], 3)
        self.assertEqual(g["credits"], 27)
        self.assertEqual(g["at_cap"], 2)
        self.assertEqual(g["over_cap"], 1)
        self.assertEqual(g["grinders"], 2)
        self.assertEqual(dict(g["npcs"])["Swoop Thug"], 2)

    def test_cp_rollup(self):
        c = telemetry.summarize(self._mix())["cp_income"]
        self.assertEqual(c["events"], 2)
        self.assertEqual(c["cp"], 1)
        self.assertEqual(c["ticks"], 7)
        self.assertEqual(c["at_cap"], 1)
        self.assertEqual(dict(c["by_source"]), {"scene": 1, "kudos": 1})

    def test_objective_funnel(self):
        o = telemetry.summarize(self._mix())["objective"]
        self.assertEqual(o["mission"]["start"], 1)
        self.assertEqual(o["mission"]["complete"], 1)
        self.assertEqual(o["mission"]["reward"], 500)
        self.assertEqual(o["bounty"]["abandon"], 1)

    def test_encounter_and_communal_rollup(self):
        s = telemetry.summarize(self._mix())
        e = s["wild_encounter"]
        self.assertEqual(e["rolls"], 2)
        self.assertEqual(e["fired"], 1)
        self.assertEqual(e["by_band"], {"1": 1, "3": 1})
        c = s["communal"]
        self.assertEqual(c["menace_events"], 1)
        self.assertEqual(c["tier_escalations"], 1)
        self.assertEqual(c["strikes"], 2)
        self.assertEqual(c["strike_success"], 1)

    def test_empty_and_junk_tolerated(self):
        s = telemetry.summarize([])
        self.assertEqual(s["total"], 0)
        self.assertIsNone(s["first_ts"])
        # mixed junk: non-dicts, missing fields, bad reward type
        s2 = telemetry.summarize([
            "nope", 5, None,
            {"ev": "grind_kill", "reward": "bad"},   # bad int coerces to 0
            {"no_ev_key": 1},
        ])
        self.assertEqual(s2["grind"]["kills"], 1)
        self.assertEqual(s2["grind"]["credits"], 0)


# ── BalanceCommand ───────────────────────────────────────────────────────────
class BalanceCommandTests(_IsolatedTelemetryTest):
    def _emit_sample(self):
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 12,
                                      "at_cap": True, "npc_name": "Swoop Thug"})
        telemetry.emit("cp_income", {"source": "scene", "cp_gained": 1,
                                     "ticks": 5})
        telemetry.emit("objective", {"kind": "mission", "phase": "complete",
                                     "reward": 500})
        telemetry.emit("wild_encounter", {"fired": True, "band": 2})
        telemetry.emit("communal_strike", {"success": True})

    def test_overview_renders_all_sections(self):
        self._emit_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("@BALANCE DASHBOARD", out)
        self.assertIn("EVENT MIX", out)
        self.assertIn("MOB GRIND", out)
        self.assertIn("CP INCOME", out)
        self.assertIn("OBJECTIVE FUNNEL", out)
        self.assertIn("WILDERNESS ENCOUNTERS", out)
        self.assertIn("COMMUNAL OBJECTIVES", out)
        self.assertIn("Swoop Thug", out)

    def test_empty_telemetry_degrades_cleanly(self):
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("No telemetry events recorded yet", out)

    def test_grind_subcommand_only(self):
        self._emit_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "grind")))
        out = "\n".join(sess.lines)
        self.assertIn("MOB GRIND", out)
        self.assertNotIn("CP INCOME", out)

    def test_raw_subcommand_lists_records(self):
        self._emit_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "raw 3")))
        out = "\n".join(sess.lines)
        self.assertIn("raw events", out)
        # the last 3 of the 5 emitted should appear (objective onward)
        self.assertIn("communal_strike", out)

    def test_registered_and_admin_gated(self):
        self.assertEqual(dc.BalanceCommand.access_level, AccessLevel.ADMIN)
        registered = []

        class _Reg:
            def register(self, cmd):
                registered.append(type(cmd).__name__)

        dc.register_director_commands(_Reg())
        self.assertIn("BalanceCommand", registered)


if __name__ == "__main__":
    unittest.main()
