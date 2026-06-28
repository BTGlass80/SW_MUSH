# -*- coding: utf-8 -*-
"""tests/test_telemetry_command_rollup.py — T3.19 telemetry READ-SIDE: the
``command`` rollup in ``telemetry.summarize`` + the ``@balance commands`` board.

The PRODUCER half has been wired for a while: ``parser/commands.py``'s
``_emit_command_telemetry`` fires one fail-open event at the SINGLE dispatch
chokepoint per command invocation, carrying:

  - ``matched``  — True if a command resolved, False for an unknown command
                   (the "Huh?" friction the NPE onboarding drive fights);
  - ``cmd``      — the canonical command key for a resolved command (so
                   aliases / glued prefixes group together) or the typed word
                   for an unknown one;
  - ``typed``    — present only when the typed form differed from the canonical
                   key (an alias / glued-prefix invocation);
  - ``char_id``  — the invoking character (when in-world);
  - ``sw``       — switch list (when present).

But the CONSUMER half was missing: ``summarize`` rolled up grind / cp /
objective / wild_encounter / communal / chain / session / skill_check / economy
/ progression and silently DROPPED ``command`` on the floor, and ``@balance``
had no command board — so command utilization (the catalog-C histogram: a dead
verb shows ~0), the unknown-command friction rate (catalog D: which words
confuse), and alias-vs-canonical use appeared nowhere but the generic event-mix
count + the raw dump. This drop adds the consumer: a ``command`` rollup →
``@balance commands``.

Mirrors the chain / session / skill_check / economy / progression rollup
guards: the rollup buckets the REAL producer field names + tolerates junk; the
new key is additive (siblings unperturbed); the board renders/aliases/gates/
degrades; the REAL ``_emit_command_telemetry`` producer feeds the consumer
end-to-end; and a source-scoped contract guard pins the emit-site field names
this rollup reads (no-phantom, both directions).

Run: python -m pytest tests/test_telemetry_command_rollup.py
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
from parser.commands import CommandContext  # noqa: E402
from parser import director_commands as dc  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeSession:
    def __init__(self):
        self.lines: list = []
        self.char_name = "Admin"
        self.account = {"username": "admin"}
        self.character = None  # set in the producer end-to-end test

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


# ── Records mirroring the REAL producer envelope (_emit_command_telemetry) ─────
def _cmd_mix():
    return [
        # matched, canonical key 'look' (no typed → typed==cmd, lean record).
        {"ev": "command", "matched": True, "cmd": "look", "char_id": 1},
        {"ev": "command", "matched": True, "cmd": "look", "char_id": 2},
        # matched via an alias / glued prefix (typed differs → aliased).
        {"ev": "command", "matched": True, "cmd": "inventory", "typed": "inv",
         "char_id": 1},
        {"ev": "command", "matched": True, "cmd": "attack", "typed": "kill",
         "char_id": 1, "sw": ["all"]},
        # unknown commands — the "Huh?" friction; ``cmd`` IS the typed token.
        {"ev": "command", "matched": False, "cmd": "blarg", "char_id": 2},
        {"ev": "command", "matched": False, "cmd": "blarg", "char_id": 1},
        {"ev": "command", "matched": False, "cmd": "fight", "char_id": 3},
    ]


# ── 1. The command rollup buckets the real producer field names ───────────────
class SummarizeCommandTests(unittest.TestCase):
    def setUp(self):
        self.c = telemetry.summarize(_cmd_mix())["command"]

    def test_totals(self):
        c = self.c
        self.assertEqual(c["total"], 7)
        self.assertEqual(c["matched"], 4)     # look×2 + inventory + attack
        self.assertEqual(c["unmatched"], 3)   # blarg×2 + fight

    def test_aliased_counts_typed_diverging_from_canonical(self):
        # Only the inventory (inv) + attack (kill) matched events carried a
        # ``typed`` that differed from the canonical key.
        self.assertEqual(self.c["aliased"], 2)

    def test_distinct_users(self):
        # char_id 1, 2, 3 across matched + unmatched.
        self.assertEqual(self.c["users"], 3)

    def test_top_commands_is_utilization_histogram(self):
        # Matched events grouped by CANONICAL key, most-used first.
        top = dict(self.c["top_commands"])
        self.assertEqual(top["look"], 2)
        self.assertEqual(top["inventory"], 1)
        self.assertEqual(top["attack"], 1)
        # 'look' is the most-used → leads the histogram.
        self.assertEqual(self.c["top_commands"][0], ("look", 2))
        # an unmatched token must NOT appear in the matched histogram
        self.assertNotIn("blarg", top)

    def test_top_unmatched_is_friction_targets(self):
        # Unknown commands grouped by the typed token, most-confusing first.
        top = dict(self.c["top_unmatched"])
        self.assertEqual(top["blarg"], 2)
        self.assertEqual(top["fight"], 1)
        self.assertEqual(self.c["top_unmatched"][0], ("blarg", 2))
        # a resolved command must NOT appear among the friction tokens
        self.assertNotIn("look", top)


# ── 2. Edge cases: junk tolerance + additivity ────────────────────────────────
class SummarizeCommandEdgeTests(unittest.TestCase):
    def test_empty(self):
        c = telemetry.summarize([])["command"]
        self.assertEqual(c["total"], 0)
        self.assertEqual(c["matched"], 0)
        self.assertEqual(c["unmatched"], 0)
        self.assertEqual(c["users"], 0)
        self.assertEqual(c["top_commands"], [])
        self.assertEqual(c["top_unmatched"], [])

    def test_junk_tolerated(self):
        # Missing fields must not crash; the event still counts.
        c = telemetry.summarize([
            {"ev": "command"},                       # no matched/cmd/char_id
            {"ev": "command", "matched": True},      # matched, no cmd
        ])["command"]
        self.assertEqual(c["total"], 2)
        # falsy/absent matched → unmatched bucket, cmd defaults to "?"
        self.assertEqual(c["unmatched"], 1)
        self.assertEqual(dict(c["top_unmatched"]).get("?"), 1)
        # matched-without-cmd → matched bucket, canonical defaults to "?"
        self.assertEqual(c["matched"], 1)
        self.assertEqual(dict(c["top_commands"]).get("?"), 1)
        self.assertEqual(c["users"], 0)             # no char_id anywhere

    def test_command_key_additive_other_rollups_intact(self):
        s = telemetry.summarize([
            {"ts": 1.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "npc_name": "Swoop Thug"},
            {"ts": 2.0, "ev": "command", "matched": False, "cmd": "blarg",
             "char_id": 1},
        ])
        for key in ("grind", "cp_income", "objective", "chain",
                    "wild_encounter", "communal", "skill_check", "session",
                    "economy", "progression", "command"):
            self.assertIn(key, s)
        self.assertEqual(s["grind"]["kills"], 1)
        self.assertEqual(s["command"]["total"], 1)
        self.assertEqual(s["command"]["unmatched"], 1)

    def test_unknown_event_lands_only_in_by_type(self):
        s = telemetry.summarize([{"ev": "garbage_type", "x": 1}])
        self.assertEqual(s["command"]["total"], 0)
        self.assertIn("garbage_type", dict(s["by_type"]))


# ── 3. The @balance commands board ────────────────────────────────────────────
class _IsolatedTelemetryTest(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        self._tmp = tempfile.mkdtemp(prefix="swmush_tele_cmd_")
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


class BalanceCommandBoardTests(_IsolatedTelemetryTest):
    def _emit_cmd_sample(self):
        telemetry.emit("command", {"matched": True, "cmd": "look",
                                   "char_id": 1})
        telemetry.emit("command", {"matched": True, "cmd": "inventory",
                                   "typed": "inv", "char_id": 1})
        telemetry.emit("command", {"matched": False, "cmd": "blarg",
                                   "char_id": 2})

    def test_commands_subcommand_renders(self):
        self._emit_cmd_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "commands")))
        out = "\n".join(sess.lines)
        self.assertIn("COMMAND USAGE", out)
        self.assertIn("Invocations", out)
        self.assertIn("'Huh?' friction", out)
        self.assertIn("look", out)       # top command
        self.assertIn("blarg", out)      # top unknown token
        # other boards are NOT shown under the commands sub
        self.assertNotIn("MOB GRIND", out)

    def test_commands_aliases_accepted(self):
        self._emit_cmd_sample()
        for alias in ("command", "cmds", "friction"):
            sess = _FakeSession()
            _run(dc.BalanceCommand().execute(_ctx(sess, alias)))
            out = "\n".join(sess.lines)
            self.assertIn("COMMAND USAGE", out,
                          f"alias {alias!r} did not render")

    def test_overview_includes_command_section(self):
        self._emit_cmd_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("COMMAND USAGE", out)
        self.assertIn("PROGRESSION / STANDING", out)  # siblings still render

    def test_command_section_absent_under_other_sub(self):
        self._emit_cmd_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "grind")))
        out = "\n".join(sess.lines)
        self.assertNotIn("COMMAND USAGE", out)

    def test_command_board_degrades_with_no_command_data(self):
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 5,
                                      "npc_name": "Womp Rat"})
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "commands")))
        out = "\n".join(sess.lines)
        self.assertIn("no command events recorded", out)


# ── 4. Load-bearing contract: the REAL producer feeds the consumer ────────────
class RealProducerEndToEndTests(_IsolatedTelemetryTest):
    def _producer_ctx(self, typed, switches=None):
        sess = _FakeSession()
        sess.character = {"id": 7}
        return CommandContext(
            session=sess,
            raw_input=typed,
            command=typed,
            args="",
            args_list=[],
            switches=list(switches or []),
            db=None,
            session_mgr=None,
        )

    def test_real_emit_helper_reaches_the_board(self):
        # Drive the actual producer (_emit_command_telemetry) — not hand-built
        # records — then read back through the real read-side and render the
        # board. A producer that renames a field or stops emitting is caught.
        from parser.commands import _emit_command_telemetry

        # alias/glued invocation: typed 'kil' resolves to canonical 'kill'
        _emit_command_telemetry(self._producer_ctx("kil", ["all"]),
                                "kill", matched=True)
        # an unknown command: typed == cmd, no alias
        _emit_command_telemetry(self._producer_ctx("blarg"),
                                "blarg", matched=False)

        events = telemetry.read_recent()
        c = telemetry.summarize(events)["command"]
        self.assertEqual(c["total"], 2)
        self.assertEqual(c["matched"], 1)
        self.assertEqual(c["unmatched"], 1)
        self.assertEqual(c["aliased"], 1)            # 'kil' != canonical 'kill'
        self.assertEqual(c["users"], 1)             # char_id 7 on both
        self.assertEqual(dict(c["top_commands"]).get("kill"), 1)
        self.assertEqual(dict(c["top_unmatched"]).get("blarg"), 1)

        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "commands")))
        out = "\n".join(sess.lines)
        self.assertIn("COMMAND USAGE", out)
        self.assertIn("'Huh?' friction", out)
        self.assertIn("kill", out)


# ── 5. No-phantom, both directions: pin the inline producer field names ────────
class ProducerFieldContractTests(unittest.TestCase):
    """``command`` is emitted INLINE in ``_emit_command_telemetry`` (the fields
    are built in the function body, not in a standalone helper). Pin the exact
    field names this rollup reads — scoped to the function — so a producer that
    renames ``matched`` / ``cmd`` / ``typed`` / ``sw`` fails loudly here.
    """

    @staticmethod
    def _func_block(rel_path: str, marker: str, span: int = 2400) -> str:
        with open(PROJECT_ROOT / rel_path, "r", encoding="utf-8") as fh:
            src = fh.read()
        i = src.index(marker)
        return src[i:i + span]

    def test_command_emit_fields(self):
        blk = self._func_block("parser/commands.py",
                               "def _emit_command_telemetry")
        # the event name + every field the rollup consumes
        self.assertIn('"command"', blk,
                      "command telemetry no longer emits the 'command' event")
        for field in ('"matched"', '"cmd"', '"typed"', '"sw"', '"char_id"'):
            self.assertIn(field, blk,
                          f"command emit no longer carries {field}")


if __name__ == "__main__":
    unittest.main()
