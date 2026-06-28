# -*- coding: utf-8 -*-
"""tests/test_telemetry_progression_rollup.py — T3.19 telemetry READ-SIDE: the
``progression`` rollup in ``telemetry.summarize`` + the ``@balance progress``
board.

The PRODUCER half has been wired for a while — four distinct NON-credit
advancement faucets each emit their own dedicated telemetry event:

  - ``faction_rep``  (``engine/organizations.py``) — personal reputation
    movement (``delta`` by ``faction``, the band-low-boundary ``tier`` /
    ``prev_tier`` ints, ``clamped`` at the rep cap);
  - ``influence``    (``engine/territory.py``)     — territorial control
    movement (``delta`` by ``zone_id``, ``clamped`` at INFLUENCE_CAP);
  - ``vanity_title`` (``engine/titles.py``)        — the prestige-title sink
    (``action`` purchase/grant, signed ``amount``);
  - ``spacer_quest`` (``engine/spacer_quest.py``)  — the spacer onboarding
    questline funnel (``phase`` start/step/complete, ``credits``/``title``/
    ``phase_gate``).

But the CONSUMER half was missing: ``summarize`` rolled up grind / cp /
objective / wild_encounter / communal / chain / session / skill_check / economy
and silently DROPPED all four of these on the floor, and ``@balance`` had no
progression board — so the non-credit advancement breadth (which factions
players court, where influence shifts, how the title sink performs, where the
spacer quest loses players) appeared nowhere but the generic event-mix count +
the raw dump. This drop adds the consumer: a ``progression`` rollup →
``@balance progress``.

Mirrors the chain / session / skill_check / economy rollup guards: the rollup
buckets the REAL producer field names + tolerates junk; the new key is additive
(siblings unperturbed); the board renders/aliases/gates/degrades; the REAL
``vanity_title`` + ``spacer_quest`` producers feed the consumer end-to-end; and
a source-scoped contract guard pins the inline ``faction_rep`` / ``influence``
emit field names this rollup depends on (no-phantom, both directions).

Run: python -m pytest tests/test_telemetry_progression_rollup.py
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


# ── Records mirroring the REAL producer envelopes (one per producer) ──────────
def _prog_mix():
    return [
        # faction_rep — delta / faction / tier / prev_tier / clamped.
        # tier is the band's low boundary (an int): 0=unknown, 10=recognized,
        # 75=revered, 90=exalted — monotonic, so a higher int IS a higher tier.
        {"ev": "faction_rep", "char_id": 1, "faction": "republic",
         "delta": 5, "rep": 15, "prev": 10, "tier": 10, "prev_tier": 0,
         "clamped": False},                                    # gain, tier UP
        {"ev": "faction_rep", "char_id": 1, "faction": "republic",
         "delta": -3, "rep": 12, "prev": 15, "tier": 10, "prev_tier": 10,
         "clamped": False},                                    # loss, no tier
        {"ev": "faction_rep", "char_id": 2, "faction": "hutt_cartel",
         "delta": 100, "rep": 100, "prev": 95, "tier": 90, "prev_tier": 75,
         "clamped": True},                                     # gain, UP, capped
        # influence — delta / zone_id / clamped.
        {"ev": "influence", "org": "republic", "zone_id": "coruscant_works",
         "delta": 4, "score": 4, "prev": 0, "clamped": False},
        {"ev": "influence", "org": "cis", "zone_id": "coruscant_works",
         "delta": -2, "score": 2, "prev": 4, "clamped": False},
        {"ev": "influence", "org": "hutt_cartel", "zone_id": "nar_shaddaa",
         "delta": 50, "score": 100, "prev": 80, "clamped": True},
        # vanity_title — action / amount (signed; purchase is the credit sink).
        {"ev": "vanity_title", "action": "purchase", "char_id": 1,
         "amount": -5000, "key": "warlord", "tier": 5},
        {"ev": "vanity_title", "action": "grant", "char_id": 2,
         "amount": 0, "key": "hero"},
        # spacer_quest — phase / credits / title / phase_gate.
        {"ev": "spacer_quest", "phase": "start", "char_id": 1},
        {"ev": "spacer_quest", "phase": "step", "char_id": 1, "step": 5,
         "credits": 100, "phase_gate": True},
        {"ev": "spacer_quest", "phase": "complete", "char_id": 1, "step": 30,
         "credits": 500, "title": True},
    ]


# ── 1. The progression rollup buckets the real producer field names ───────────
class SummarizeProgressionTests(unittest.TestCase):
    def setUp(self):
        self.p = telemetry.summarize(_prog_mix())["progression"]

    def test_faction_rep_totals(self):
        p = self.p
        self.assertEqual(p["rep_events"], 3)
        self.assertEqual(p["rep_gain"], 5 + 100)
        self.assertEqual(p["rep_loss"], 3)
        self.assertEqual(p["rep_clamped"], 1)

    def test_faction_rep_tier_transitions(self):
        # 0→10 and 75→90 are tier-ups; the -3 loss stayed within tier 10.
        self.assertEqual(self.p["rep_tier_ups"], 2)
        self.assertEqual(self.p["rep_tier_downs"], 0)

    def test_by_faction_net_and_order(self):
        # republic has 2 events (net +5-3=+2); hutt_cartel 1 (net +100).
        # Ranked by event volume → republic first.
        by = self.p["by_faction"]
        self.assertEqual(by[0], ("republic", 2, 2))
        self.assertEqual(dict((f, (e, n)) for f, e, n in by)["hutt_cartel"],
                         (1, 100))

    def test_influence_totals(self):
        p = self.p
        self.assertEqual(p["inf_events"], 3)
        self.assertEqual(p["inf_gain"], 4 + 50)
        self.assertEqual(p["inf_loss"], 2)
        self.assertEqual(p["inf_clamped"], 1)

    def test_by_zone_net_and_order(self):
        # coruscant_works: 2 events net +4-2=+2 (most active → first).
        by = self.p["by_zone"]
        self.assertEqual(by[0], ("coruscant_works", 2, 2))
        self.assertEqual(dict((z, (e, n)) for z, e, n in by)["nar_shaddaa"],
                         (1, 50))

    def test_vanity_title_economy(self):
        p = self.p
        self.assertEqual(p["title_events"], 2)
        self.assertEqual(p["title_buys"], 1)
        self.assertEqual(p["title_grants"], 1)
        self.assertEqual(p["title_credits"], 5000)   # gross |amount|

    def test_spacer_quest_funnel(self):
        p = self.p
        self.assertEqual(p["spacer_starts"], 1)
        self.assertEqual(p["spacer_steps"], 1)
        self.assertEqual(p["spacer_completes"], 1)
        self.assertEqual(p["spacer_credits"], 100 + 500)
        self.assertEqual(p["spacer_titles"], 1)
        self.assertEqual(p["spacer_phase_gates"], 1)


# ── 2. Edge cases: junk tolerance + additivity ────────────────────────────────
class SummarizeProgressionEdgeTests(unittest.TestCase):
    def test_empty(self):
        p = telemetry.summarize([])["progression"]
        self.assertEqual(p["rep_events"], 0)
        self.assertEqual(p["inf_events"], 0)
        self.assertEqual(p["title_events"], 0)
        self.assertEqual(p["by_faction"], [])
        self.assertEqual(p["by_zone"], [])

    def test_junk_tolerated(self):
        # Bad/missing numeric fields must not crash; the event still counts.
        p = telemetry.summarize([
            {"ev": "faction_rep", "faction": "republic", "delta": "bad"},
            {"ev": "influence", "delta": None},          # no zone_id
            {"ev": "vanity_title"},                       # no action/amount
            {"ev": "spacer_quest"},                       # no phase
        ])["progression"]
        self.assertEqual(p["rep_events"], 1)
        self.assertEqual(p["rep_gain"], 0)
        self.assertEqual(p["inf_events"], 1)
        self.assertEqual(p["title_events"], 1)
        # missing action + amount<0-test falls through to "earned" grant bucket
        self.assertEqual(p["title_grants"], 1)
        self.assertEqual(p["title_buys"], 0)

    def test_title_buy_falls_back_to_amount_sign(self):
        # No action label, negative amount → still classified as a buy.
        p = telemetry.summarize([
            {"ev": "vanity_title", "char_id": 1, "amount": -2000},
        ])["progression"]
        self.assertEqual(p["title_buys"], 1)
        self.assertEqual(p["title_grants"], 0)
        self.assertEqual(p["title_credits"], 2000)

    def test_progression_key_additive_other_rollups_intact(self):
        s = telemetry.summarize([
            {"ts": 1.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "npc_name": "Swoop Thug"},
            {"ts": 2.0, "ev": "vendor_txn", "phase": "buy", "char_id": 1,
             "price": 42},
            {"ts": 3.0, "ev": "faction_rep", "faction": "republic",
             "delta": 5, "tier": 10, "prev_tier": 0},
        ])
        for key in ("grind", "cp_income", "objective", "chain",
                    "wild_encounter", "communal", "skill_check", "session",
                    "economy", "progression"):
            self.assertIn(key, s)
        self.assertEqual(s["grind"]["kills"], 1)
        self.assertEqual(s["economy"]["events"], 1)
        self.assertEqual(s["progression"]["rep_events"], 1)
        self.assertEqual(s["progression"]["rep_tier_ups"], 1)

    def test_unknown_event_lands_only_in_by_type(self):
        s = telemetry.summarize([{"ev": "garbage_type", "x": 1}])
        self.assertEqual(s["progression"]["rep_events"], 0)
        self.assertIn("garbage_type", dict(s["by_type"]))


# ── 3. The @balance progress board ────────────────────────────────────────────
class _IsolatedTelemetryTest(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        self._tmp = tempfile.mkdtemp(prefix="swmush_tele_prog_")
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


class BalanceProgressBoardTests(_IsolatedTelemetryTest):
    def _emit_prog_sample(self):
        telemetry.emit("faction_rep", {"char_id": 1, "faction": "republic",
                                       "delta": 5, "tier": 10, "prev_tier": 0})
        telemetry.emit("influence", {"org": "cis", "zone_id": "kuat_ring",
                                     "delta": 3})
        telemetry.emit("vanity_title", {"action": "purchase", "char_id": 1,
                                        "amount": -5000})
        telemetry.emit("spacer_quest", {"phase": "complete", "char_id": 1,
                                        "credits": 500})

    def test_progress_subcommand_renders(self):
        self._emit_prog_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "progress")))
        out = "\n".join(sess.lines)
        self.assertIn("PROGRESSION / STANDING", out)
        self.assertIn("Faction rep", out)
        self.assertIn("republic", out)
        self.assertIn("Influence", out)
        self.assertIn("Vanity titles", out)
        self.assertIn("Spacer quest", out)
        # other boards are NOT shown under the progress sub
        self.assertNotIn("MOB GRIND", out)

    def test_progress_aliases_accepted(self):
        self._emit_prog_sample()
        for alias in ("progression", "standing", "rep"):
            sess = _FakeSession()
            _run(dc.BalanceCommand().execute(_ctx(sess, alias)))
            out = "\n".join(sess.lines)
            self.assertIn("PROGRESSION / STANDING", out,
                          f"alias {alias!r} did not render")

    def test_overview_includes_progress_section(self):
        self._emit_prog_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("PROGRESSION / STANDING", out)
        self.assertIn("SKILL CHECKS", out)   # siblings still render

    def test_progress_section_absent_under_other_sub(self):
        self._emit_prog_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "grind")))
        out = "\n".join(sess.lines)
        self.assertNotIn("PROGRESSION / STANDING", out)

    def test_progress_board_degrades_with_no_progression_data(self):
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 5,
                                      "npc_name": "Womp Rat"})
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "progress")))
        out = "\n".join(sess.lines)
        self.assertIn("no progression events recorded", out)


# ── 4. Load-bearing contract: the REAL producers feed the consumer ────────────
class RealProducerEndToEndTests(_IsolatedTelemetryTest):
    def test_real_title_and_spacer_helpers_reach_the_board(self):
        # Drive the actual engine emit helpers (not hand-built records), then
        # read them back through the real read-side and render the board — so a
        # producer that renames a field or stops emitting is caught here.
        from engine.titles import _emit_title_telemetry
        from engine.spacer_quest import _emit_spacer_telemetry

        _emit_title_telemetry("purchase", 1, -5000, key="warlord", tier=5)
        _emit_title_telemetry("grant", 2, 0, key="hero")
        _emit_spacer_telemetry("start", {"id": 3}, {"phase": 1})
        _emit_spacer_telemetry("complete", {"id": 3}, {"phase": 5},
                               step_id=30, credits=500, title=True,
                               phase_gate=True)

        events = telemetry.read_recent()
        p = telemetry.summarize(events)["progression"]
        self.assertEqual(p["title_buys"], 1)
        self.assertEqual(p["title_grants"], 1)
        self.assertEqual(p["title_credits"], 5000)
        self.assertEqual(p["spacer_starts"], 1)
        self.assertEqual(p["spacer_completes"], 1)
        self.assertEqual(p["spacer_credits"], 500)
        self.assertEqual(p["spacer_titles"], 1)
        self.assertEqual(p["spacer_phase_gates"], 1)

        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "progress")))
        out = "\n".join(sess.lines)
        self.assertIn("PROGRESSION / STANDING", out)
        self.assertIn("Vanity titles", out)
        self.assertIn("5,000", out)   # the title sink soak, comma-formatted


# ── 5. No-phantom, both directions: pin the inline producer field names ────────
class ProducerFieldContractTests(unittest.TestCase):
    """faction_rep / influence are emitted INLINE (no standalone helper), so the
    end-to-end test above can't drive them without a DB. Instead, pin the exact
    emit-site field names this rollup reads — scoped to the emit block so an
    unrelated field elsewhere in the module can't satisfy the assertion. A
    producer that renames ``delta`` / ``tier`` / ``zone_id`` fails loudly here.
    """

    @staticmethod
    def _emit_block(rel_path: str, marker: str, span: int = 700) -> str:
        with open(PROJECT_ROOT / rel_path, "r", encoding="utf-8") as fh:
            src = fh.read()
        i = src.index(marker)
        return src[i:i + span]

    def test_faction_rep_emit_fields(self):
        blk = self._emit_block("engine/organizations.py",
                               '_tele_emit("faction_rep"')
        for field in ('"delta"', '"faction"', '"tier"', '"prev_tier"',
                      '"clamped"'):
            self.assertIn(field, blk,
                          f"faction_rep emit no longer carries {field}")

    def test_influence_emit_fields(self):
        blk = self._emit_block("engine/territory.py",
                               '_tele_emit("influence"')
        for field in ('"delta"', '"zone_id"', '"clamped"'):
            self.assertIn(field, blk,
                          f"influence emit no longer carries {field}")


if __name__ == "__main__":
    unittest.main()
