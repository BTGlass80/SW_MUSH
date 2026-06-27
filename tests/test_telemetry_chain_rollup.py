# -*- coding: utf-8 -*-
"""tests/test_telemetry_chain_rollup.py — T3.19 telemetry READ-SIDE: the
``chain_reward`` rollup in ``telemetry.summarize`` + the ``@balance chains``
sub-board.

The PRODUCER half has been wired + tested since the onboarding-funnel drop
(``tests/test_t319_chain_reward_telemetry.py``): a reward-bearing chain step
emits ``chain_reward`` phase="step" and a graduation ALWAYS emits
phase="graduation" — the load-bearing NPE / questline-completion signal
("chain completion rate per chain_id", per the emit-site comments).

But the CONSUMER half was missing: ``summarize`` rolled up grind / cp_income /
objective / wild_encounter / communal but DROPPED ``chain_reward`` on the floor,
and ``@balance`` had grind/cp/objectives/encounters/events sub-boards but no
chain board — so the funnel those events were emitted FOR appeared nowhere
except the generic event-mix count + the raw dump. This drop adds the consumer:
a per-chain ``chain`` rollup in ``summarize`` (graduations = completions,
reward-steps, credit flow, per chain_id, with the graduation's human label) and
a ``@balance chains`` board that renders it.

This suite proves: ``summarize`` buckets the REAL producer field names into the
right per-chain aggregates and tolerates junk; the chain key is additive (the
other rollups are unperturbed); the ``@balance chains`` board renders the funnel
(label preferred over id, completion-ordered), is gated (absent under other
subs), and degrades cleanly with no data; and — the load-bearing contract — the
REAL ``apply_graduation_rewards`` producer feeds the new consumer end-to-end.

Run: python -m pytest tests/test_telemetry_chain_rollup.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SW_ERA", "clone_wars")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from engine.chain_rewards import apply_graduation_rewards  # noqa: E402
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


# Mirrors the REAL producer envelope (engine/chain_rewards.py):
#   step       : {phase, chain_id, step, char_id, credits, items, rep}
#   graduation : {phase, chain_id, chain_label, char_id, credits, items,
#                 achievements, rep, errors}
def _step(chain_id, *, credits=0, items=0, rep=0, step=1, char_id=1):
    return {"ts": 100.0, "ev": "chain_reward", "phase": "step",
            "chain_id": chain_id, "step": step, "char_id": char_id,
            "credits": credits, "items": items, "rep": rep}


def _grad(chain_id, *, label="", credits=0, items=0, achievements=0,
          rep=0, char_id=1):
    return {"ts": 200.0, "ev": "chain_reward", "phase": "graduation",
            "chain_id": chain_id, "chain_label": label, "char_id": char_id,
            "credits": credits, "items": items, "achievements": achievements,
            "rep": rep, "errors": 0}


# ── summarize: the chain rollup ───────────────────────────────────────────────
class SummarizeChainTests(unittest.TestCase):
    def _mix(self):
        return [
            _step("nar_shaddaa_forged_notice", credits=150, items=1, step=2),
            _grad("nar_shaddaa_forged_notice", label="The Forged Notice",
                  credits=300, items=0, achievements=1),
            _grad("kuat_ring_skimmed_line", label="The Skimmed Line",
                  credits=300, achievements=1),
            _step("kuat_ring_skimmed_line", credits=150, step=3),
            _grad("kuat_ring_skimmed_line", label="The Skimmed Line",
                  credits=300, achievements=1),
            # a graduation that never fired a reward-bearing step (zero credits)
            _grad("republic_soldier", label="Republic Soldier"),
        ]

    def test_chain_rollup_top_level(self):
        c = telemetry.summarize(self._mix())["chain"]
        # 4 graduations (forged×1, kuat×2, republic×1), 2 reward-steps
        self.assertEqual(c["graduations"], 4)
        self.assertEqual(c["step_events"], 2)
        # credit flow = 150 + 300 + 300 + 150 + 300 + 0
        self.assertEqual(c["credits"], 1200)
        self.assertEqual(c["items"], 1)
        self.assertEqual(c["achievements"], 3)

    def test_chain_rollup_per_chain(self):
        by = telemetry.summarize(self._mix())["chain"]["by_chain"]
        # Kuat completed twice (two graduations), one reward-step
        k = by["kuat_ring_skimmed_line"]
        self.assertEqual(k["graduations"], 2)
        self.assertEqual(k["steps"], 1)
        self.assertEqual(k["credits"], 750)
        self.assertEqual(k["label"], "The Skimmed Line")
        # Forged Notice: one graduation, one reward-step
        f = by["nar_shaddaa_forged_notice"]
        self.assertEqual(f["graduations"], 1)
        self.assertEqual(f["steps"], 1)
        self.assertEqual(f["label"], "The Forged Notice")
        # A zero-credit graduation still counts as a completion
        r = by["republic_soldier"]
        self.assertEqual(r["graduations"], 1)
        self.assertEqual(r["steps"], 0)
        self.assertEqual(r["credits"], 0)

    def test_chain_key_is_additive_other_rollups_intact(self):
        # The chain rollup must not disturb the sibling rollups: a mixed batch
        # still produces every existing key and the right grind/objective counts.
        s = telemetry.summarize([
            {"ts": 1.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "npc_name": "Swoop Thug"},
            {"ts": 2.0, "ev": "objective", "kind": "mission",
             "phase": "complete", "reward": 500},
            _grad("kuat_ring_skimmed_line", label="The Skimmed Line",
                  credits=300),
        ])
        for key in ("grind", "cp_income", "objective", "chain",
                    "wild_encounter", "communal"):
            self.assertIn(key, s)
        self.assertEqual(s["grind"]["kills"], 1)
        self.assertEqual(s["objective"]["mission"]["complete"], 1)
        self.assertEqual(s["chain"]["graduations"], 1)

    def test_empty_and_junk_tolerated(self):
        # No chain events → empty rollup, no error.
        c0 = telemetry.summarize([])["chain"]
        self.assertEqual(c0["graduations"], 0)
        self.assertEqual(c0["by_chain"], {})
        # bad credit type coerces to 0; missing chain_id buckets under "?"
        c1 = telemetry.summarize([
            {"ev": "chain_reward", "phase": "graduation", "credits": "bad"},
        ])["chain"]
        self.assertEqual(c1["graduations"], 1)
        self.assertEqual(c1["credits"], 0)
        self.assertIn("?", c1["by_chain"])

    def test_unknown_phase_ignored_but_still_sums_value(self):
        # A malformed phase neither graduates nor steps, but its credit flow is
        # still attributed (the value is real even if the lifecycle tag is bad).
        c = telemetry.summarize([
            {"ev": "chain_reward", "phase": "weird",
             "chain_id": "x", "credits": 99},
        ])["chain"]
        self.assertEqual(c["graduations"], 0)
        self.assertEqual(c["step_events"], 0)
        self.assertEqual(c["credits"], 99)
        self.assertEqual(c["by_chain"]["x"]["credits"], 99)


# ── @balance chains board ─────────────────────────────────────────────────────
class _IsolatedTelemetryTest(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        self._tmp = tempfile.mkdtemp(prefix="swmush_tele_chain_")
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


class BalanceChainsBoardTests(_IsolatedTelemetryTest):
    def _emit_chain_sample(self):
        telemetry.emit("chain_reward", {"phase": "step",
                                        "chain_id": "kuat_ring_skimmed_line",
                                        "step": 2, "char_id": 1, "credits": 150,
                                        "items": 0, "rep": 0})
        telemetry.emit("chain_reward", {"phase": "graduation",
                                        "chain_id": "kuat_ring_skimmed_line",
                                        "chain_label": "The Skimmed Line",
                                        "char_id": 1, "credits": 300,
                                        "items": 0, "achievements": 1,
                                        "rep": 0, "errors": 0})

    def test_chains_subcommand_renders_funnel(self):
        self._emit_chain_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "chains")))
        out = "\n".join(sess.lines)
        self.assertIn("CHAIN / QUESTLINE FUNNEL", out)
        # label preferred over the raw chain_id
        self.assertIn("The Skimmed Line", out)
        self.assertIn("Graduations: 1", out)
        # other boards are NOT shown under the chains sub
        self.assertNotIn("MOB GRIND", out)

    def test_overview_includes_chain_section(self):
        self._emit_chain_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("CHAIN / QUESTLINE FUNNEL", out)
        self.assertIn("OBJECTIVE FUNNEL", out)  # still renders the siblings

    def test_chain_section_absent_under_other_sub(self):
        self._emit_chain_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "grind")))
        out = "\n".join(sess.lines)
        self.assertNotIn("CHAIN / QUESTLINE FUNNEL", out)

    def test_chains_board_degrades_with_no_chain_data(self):
        # Some telemetry exists (so the dashboard renders) but no chain events.
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 5,
                                      "npc_name": "Womp Rat"})
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "chains")))
        out = "\n".join(sess.lines)
        self.assertIn("no chain reward events recorded", out)


# ── producer → consumer round-trip (the load-bearing contract) ────────────────
class _StubDB:
    def __init__(self):
        self.credit_log = []

    async def adjust_credits(self, cid, delta, source):
        self.credit_log.append((cid, delta, source))
        return 1000 + delta

    async def add_to_inventory(self, cid, item):
        pass

    async def save_character(self, cid, **kw):
        pass


class ProducerToConsumerTests(_IsolatedTelemetryTest):
    def test_real_graduation_feeds_the_chain_rollup(self):
        # Drive the REAL graduation producer, flush to the isolated sink, then
        # read it back through the REAL consumer path (read_recent + summarize).
        db = _StubDB()
        grad = SimpleNamespace(credits=300, faction_rep={},
                               items=["datapad"], achievements=[],
                               follow_up_hint="")
        _run(apply_graduation_rewards(
            db, {"id": 7, "credits": 1000, "chargen_notes": "{}"}, {},
            grad, "kuat_ring_skimmed_line", "The Skimmed Line"))
        telemetry.get_sink().flush()

        events = telemetry.read_recent()
        summary = telemetry.summarize(events)
        c = summary["chain"]
        self.assertEqual(c["graduations"], 1)
        self.assertEqual(c["credits"], 300)
        by = c["by_chain"]["kuat_ring_skimmed_line"]
        self.assertEqual(by["graduations"], 1)
        self.assertEqual(by["label"], "The Skimmed Line")

        # And the admin board surfaces it from the same on-disk record.
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "chains")))
        out = "\n".join(sess.lines)
        self.assertIn("The Skimmed Line", out)


if __name__ == "__main__":
    unittest.main()
