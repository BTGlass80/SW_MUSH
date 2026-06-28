# -*- coding: utf-8 -*-
"""tests/test_telemetry_economy_rollup.py — T3.19 telemetry READ-SIDE: the
``economy`` credit-flow rollup + the ``cp_spend`` sink, both in
``telemetry.summarize``, surfaced by ``@balance flows`` and the enriched
``@balance cp`` board.

The PRODUCER half has been wired for a while: ten distinct credit faucet/sink
systems each emit their own dedicated telemetry event — ``vendor_txn`` /
``commissary_txn`` / ``gamble`` / ``debt`` / ``gear_insurance`` / ``housing`` /
``den`` / ``medical_treatment`` / ``pc_bounty`` / ``entertainer_perform`` — and
the CP economy emits the ``cp_spend`` sink (the ``train`` advancement spend) to
pair with the ``cp_income`` faucet.

But the CONSUMER half was missing: ``summarize`` rolled up grind / cp_income /
objective / wild_encounter / communal / chain_reward / session / skill_check and
silently DROPPED all eleven of those producers on the floor, and ``@balance``
had no credit-flow board and showed only the CP income half. So the credit
faucet/sink VOLUME the ``@economy`` DB snapshot can't trend, and the CP
hoard-vs-spend signal, appeared nowhere but the generic event-mix count + the
raw dump. This drop adds the consumers: an ``economy`` rollup (per-system gross
credit throughput) → ``@balance flows``, and a ``cp_spend`` extension of the
``cp`` rollup → the enriched ``@balance cp`` board.

Mirrors the chain / session / skill_check rollup guards: the rollup buckets the
REAL producer field names + tolerates junk; the new keys are additive (siblings
unperturbed); the boards render/gate/degrade; and the REAL ``_emit_*`` producers
feed the new consumers end-to-end.

Run: python -m pytest tests/test_telemetry_economy_rollup.py
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


# ── Records mirroring the REAL producer envelopes (one per system) ────────────
def _econ_mix():
    return [
        # vendor_txn: ``price`` is the TOTAL credits that changed hands.
        {"ev": "vendor_txn", "phase": "buy", "char_id": 1, "price": 250, "qty": 1},
        {"ev": "vendor_txn", "phase": "sell", "char_id": 2, "price": 120, "qty": 3},
        # commissary_txn: cost (buy) OR refund (sell), never both.
        {"ev": "commissary_txn", "phase": "buy", "char_id": 1, "cost": 80},
        {"ev": "commissary_txn", "phase": "sell", "char_id": 1, "refund": 30},
        # gamble: ``bet`` is the gross wagered (net/rake are separate).
        {"ev": "gamble", "char_id": 3, "bet": 500, "net": -500, "rake": 25},
        # signed-``amount`` systems.
        {"ev": "debt", "action": "payment", "char_id": 4, "amount": -500},
        {"ev": "gear_insurance", "action": "purchase", "char_id": 4, "amount": -200},
        {"ev": "housing", "action": "rent_paid", "char_id": 5, "amount": -300},
        {"ev": "den", "action": "establish", "char_id": 6, "amount": -10000},
        {"ev": "pc_bounty", "action": "post", "char_id": 9, "amount": -1000, "fee": 50},
        # ``paid`` (medical) / ``payout`` (entertainer).
        {"ev": "medical_treatment", "healer_char": 7, "patient_char": 8,
         "paid": 150, "outcome": "success"},
        {"ev": "entertainer_perform", "char_id": 10, "payout": 75, "outcome": "ok"},
    ]


# ── 1. The economy rollup buckets the real producer field names ───────────────
class SummarizeEconomyTests(unittest.TestCase):
    def test_top_level_totals(self):
        e = telemetry.summarize(_econ_mix())["economy"]
        self.assertEqual(e["events"], 12)
        # gross = 250+120 + 80+30 + 500 + 500+200+300+10000+1000 + 150 + 75
        self.assertEqual(e["credits"],
                         250 + 120 + 80 + 30 + 500 + 500 + 200 + 300
                         + 10000 + 1000 + 150 + 75)

    def test_per_domain_buckets(self):
        e = telemetry.summarize(_econ_mix())["economy"]
        dom = {d: (evs, cr) for d, evs, cr in e["by_domain"]}
        # the two vendor events collapse to one "vendor" domain w/ summed gross
        self.assertEqual(dom["vendor"], (2, 370))
        self.assertEqual(dom["commissary"], (2, 110))
        self.assertEqual(dom["gambling"], (1, 500))
        self.assertEqual(dom["debt"], (1, 500))
        self.assertEqual(dom["insurance"], (1, 200))
        self.assertEqual(dom["housing"], (1, 300))
        self.assertEqual(dom["den"], (1, 10000))
        self.assertEqual(dom["bounty"], (1, 1000))
        self.assertEqual(dom["medical"], (1, 150))
        self.assertEqual(dom["entertainer"], (1, 75))

    def test_ordered_biggest_mover_first(self):
        e = telemetry.summarize(_econ_mix())["economy"]
        creds = [cr for _, _, cr in e["by_domain"]]
        self.assertEqual(creds, sorted(creds, reverse=True))
        self.assertEqual(e["by_domain"][0][0], "den")   # 10000 cr, the top mover

    def test_credit_field_extraction_pins_each_schema(self):
        # No-phantom, both directions: each producer's CREDIT field name is
        # load-bearing for this rollup, so pin the extractor against the live
        # field names. A producer that renames its credit field fails HERE.
        self.assertEqual(telemetry._economy_credits(
            "vendor_txn", {"price": 99}), 99)
        self.assertEqual(telemetry._economy_credits(
            "commissary_txn", {"cost": 40}), 40)
        self.assertEqual(telemetry._economy_credits(
            "commissary_txn", {"refund": 12}), 12)
        self.assertEqual(telemetry._economy_credits(
            "gamble", {"bet": 250}), 250)
        self.assertEqual(telemetry._economy_credits(
            "medical_treatment", {"paid": 60}), 60)
        self.assertEqual(telemetry._economy_credits(
            "entertainer_perform", {"payout": 33}), 33)
        # the signed-amount systems take abs() (gross, not net)
        for et in ("debt", "gear_insurance", "housing", "den", "pc_bounty"):
            self.assertEqual(telemetry._economy_credits(et, {"amount": -77}), 77)

    def test_domain_map_covers_the_credit_producers(self):
        # The domain map is the canonical list of credit faucet/sink event types
        # this board surfaces; pin it so a dropped/renamed entry is visible.
        self.assertEqual(set(telemetry._ECONOMY_DOMAINS), {
            "vendor_txn", "commissary_txn", "gamble", "debt", "gear_insurance",
            "housing", "den", "medical_treatment", "pc_bounty",
            "entertainer_perform",
        })

    def test_empty_and_junk_tolerated(self):
        e0 = telemetry.summarize([])["economy"]
        self.assertEqual(e0["events"], 0)
        self.assertEqual(e0["credits"], 0)
        self.assertEqual(e0["by_domain"], [])
        # a bad / missing amount must not crash; the event still counts (gross 0)
        e1 = telemetry.summarize([
            {"ev": "debt", "action": "missed", "char_id": 1, "amount": "bad"},
            {"ev": "housing", "action": "overdue", "char_id": 1},  # no amount
        ])["economy"]
        self.assertEqual(e1["events"], 2)
        self.assertEqual(e1["credits"], 0)

    def test_economy_key_additive_other_rollups_intact(self):
        s = telemetry.summarize([
            {"ts": 1.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "npc_name": "Swoop Thug"},
            {"ts": 2.0, "ev": "objective", "kind": "mission",
             "phase": "complete", "reward": 500},
            {"ev": "vendor_txn", "phase": "buy", "char_id": 1, "price": 42},
        ])
        for key in ("grind", "cp_income", "objective", "chain",
                    "wild_encounter", "communal", "skill_check", "session",
                    "economy"):
            self.assertIn(key, s)
        self.assertEqual(s["grind"]["kills"], 1)
        self.assertEqual(s["objective"]["mission"]["complete"], 1)
        self.assertEqual(s["economy"]["events"], 1)
        self.assertEqual(s["economy"]["credits"], 42)

    def test_unknown_event_lands_only_in_by_type(self):
        s = telemetry.summarize([{"ev": "garbage_type", "x": 1}])
        self.assertEqual(s["economy"]["events"], 0)
        self.assertIn("garbage_type", dict(s["by_type"]))


# ── 2. cp_spend folded into the cp rollup ─────────────────────────────────────
class SummarizeCpSpendTests(unittest.TestCase):
    def _mix(self):
        return [
            {"ev": "cp_income", "source": "scene", "char_id": 1,
             "cp_gained": 1, "ticks": 2},
            {"ev": "cp_spend", "source": "train", "char_id": 1,
             "skill": "blaster", "cost": 5},
            {"ev": "cp_spend", "source": "train", "char_id": 2,
             "skill": "blaster", "cost": 7},
            {"ev": "cp_spend", "source": "train", "char_id": 1,
             "skill": "dodge", "cost": 3},
        ]

    def test_spend_rollup(self):
        cp = telemetry.summarize(self._mix())["cp_income"]
        self.assertEqual(cp["spends"], 3)
        self.assertEqual(cp["cp_spent"], 15)
        by_skill = dict(cp["by_skill"])
        self.assertEqual(by_skill["blaster"], 2)
        self.assertEqual(by_skill["dodge"], 1)

    def test_income_preserved_alongside_spend(self):
        cp = telemetry.summarize(self._mix())["cp_income"]
        self.assertEqual(cp["events"], 1)       # income faucet untouched
        self.assertEqual(cp["cp"], 1)
        self.assertEqual(dict(cp["by_source"]).get("scene"), 1)

    def test_spend_only_no_income(self):
        cp = telemetry.summarize([
            {"ev": "cp_spend", "source": "train", "char_id": 1,
             "skill": "brawling", "cost": 4},
        ])["cp_income"]
        self.assertEqual(cp["events"], 0)
        self.assertEqual(cp["spends"], 1)
        self.assertEqual(cp["cp_spent"], 4)

    def test_spend_junk_tolerated(self):
        cp = telemetry.summarize([
            {"ev": "cp_spend", "char_id": 1, "cost": "bad"},  # bad cost, no skill
        ])["cp_income"]
        self.assertEqual(cp["spends"], 1)
        self.assertEqual(cp["cp_spent"], 0)
        self.assertEqual(dict(cp["by_skill"]), {})


# ── 3. The @balance boards ────────────────────────────────────────────────────
class _IsolatedTelemetryTest(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        self._tmp = tempfile.mkdtemp(prefix="swmush_tele_econ_")
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


class BalanceFlowsBoardTests(_IsolatedTelemetryTest):
    def _emit_econ_sample(self):
        telemetry.emit("den", {"action": "establish", "char_id": 6,
                               "amount": -10000})
        telemetry.emit("vendor_txn", {"phase": "buy", "char_id": 1,
                                      "price": 250})
        telemetry.emit("gamble", {"char_id": 3, "bet": 500, "net": -100})

    def test_flows_subcommand_renders(self):
        self._emit_econ_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "flows")))
        out = "\n".join(sess.lines)
        self.assertIn("CREDIT FLOWS", out)
        self.assertIn("den", out)
        self.assertIn("vendor", out)
        self.assertIn("gross moved", out)
        # other boards are NOT shown under the flows sub
        self.assertNotIn("MOB GRIND", out)

    def test_flows_aliases_accepted(self):
        self._emit_econ_sample()
        for alias in ("flow", "economy", "econ", "credits"):
            sess = _FakeSession()
            _run(dc.BalanceCommand().execute(_ctx(sess, alias)))
            out = "\n".join(sess.lines)
            self.assertIn("CREDIT FLOWS", out, f"alias {alias!r} did not render")

    def test_overview_includes_flows_section(self):
        self._emit_econ_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("CREDIT FLOWS", out)
        self.assertIn("OBJECTIVE FUNNEL", out)   # siblings still render

    def test_flows_section_absent_under_other_sub(self):
        self._emit_econ_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "grind")))
        out = "\n".join(sess.lines)
        self.assertNotIn("CREDIT FLOWS", out)

    def test_flows_board_degrades_with_no_economy_data(self):
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 5,
                                      "npc_name": "Womp Rat"})
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "flows")))
        out = "\n".join(sess.lines)
        self.assertIn("no economy-flow events recorded", out)


class BalanceCpSpendBoardTests(_IsolatedTelemetryTest):
    def test_cp_board_shows_spend_section(self):
        telemetry.emit("cp_income", {"source": "scene", "char_id": 1,
                                     "cp_gained": 2, "ticks": 4})
        telemetry.emit("cp_spend", {"source": "train", "char_id": 1,
                                    "skill": "blaster", "cost": 5})
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "cp")))
        out = "\n".join(sess.lines)
        self.assertIn("CP ECONOMY", out)
        self.assertIn("Income", out)
        self.assertIn("Spent (train)", out)
        self.assertIn("blaster", out)


# ── 4. Load-bearing contract: the REAL producers feed the consumers ───────────
class RealProducerEndToEndTests(_IsolatedTelemetryTest):
    def test_real_emit_helpers_reach_the_flows_board(self):
        # Drive the actual engine/parser emit helpers (not hand-built records),
        # then read them back through the real read-side and render the board —
        # so a producer that renames its credit field or stops emitting is
        # caught here, not just by the static record fixtures above.
        from engine.debt import _emit_debt
        from engine.housing import _emit_housing
        from engine.gear_insurance import _emit_gear_insurance
        from engine.dens import _emit_den

        _emit_debt("payment", 1, -500, principal_remaining=4500)
        _emit_housing("rent_paid", 2, -300, lot_id="lot_7")
        _emit_gear_insurance("purchase", 3, -200, premium=200)
        _emit_den("establish", 4, -10000, org_code="hutt_cartel")

        events = telemetry.read_recent()
        e = telemetry.summarize(events)["economy"]
        self.assertEqual(e["events"], 4)
        self.assertEqual(e["credits"], 500 + 300 + 200 + 10000)
        dom = {d: (evs, cr) for d, evs, cr in e["by_domain"]}
        self.assertEqual(dom["debt"], (1, 500))
        self.assertEqual(dom["housing"], (1, 300))
        self.assertEqual(dom["insurance"], (1, 200))
        self.assertEqual(dom["den"], (1, 10000))

        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "flows")))
        out = "\n".join(sess.lines)
        self.assertIn("CREDIT FLOWS", out)
        self.assertIn("10,000", out)   # the den's gross, comma-formatted

    def test_real_cp_spend_helper_reaches_the_cp_board(self):
        from parser.cp_commands import _emit_cp_spend

        _emit_cp_spend(1, "blaster", 5, dice=4, cp_remaining=3)
        _emit_cp_spend(2, "blaster", 7, dice=5)

        events = telemetry.read_recent()
        cp = telemetry.summarize(events)["cp_income"]
        self.assertEqual(cp["spends"], 2)
        self.assertEqual(cp["cp_spent"], 12)
        self.assertEqual(dict(cp["by_skill"])["blaster"], 2)

        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "cp")))
        out = "\n".join(sess.lines)
        self.assertIn("Spent (train)", out)
        self.assertIn("blaster", out)


if __name__ == "__main__":
    unittest.main()
