"""tests/test_p2p_trade_telemetry.py — T3.19 telemetry for the P2P trade seam.

The ``trade`` command's credit legs already ride ``credit_flow`` (adjust_credits
tags ``p2p_transfer`` / ``p2p_tax``), but those three separate ledger rows can't
be rejoined offline into a single sender→recipient→tax transfer — and an ITEM
trade moves NO credits at all, so ``credit_flow`` never sees it. So the P2P
barter economy (item flows) is entirely dark, and the per-trade tax
distribution (the direct tuning signal for ``p2p.tax_pct`` + the velocity-alert
thresholds) is unreconstructable. This drop adds ONE fail-open, sample-tunable
``p2p_trade`` event at the two completion seams of ``TradeCommand._accept``.

This suite drives the REAL ``TradeCommand._accept`` (a populated ``_pending_trades``
offer + faked sessions/db) and proves: exactly one ``p2p_trade`` event per
completed trade at the post-mutation seam; the credit-trade envelope matches the
ledger legs; the item-trade event is the ONLY record of a flow ``credit_flow``
can't see; aborted/declined paths emit nothing; the ``telemetry.p2p_trade_sample``
tunable is honoured; and — the load-bearing contract — a broken sink NEVER
disturbs the completed trade.

Run: python -m pytest tests/test_p2p_trade_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser import builtin_commands as bc  # noqa: E402
from parser.commands import CommandContext  # noqa: E402

REPO = Path(PROJECT_ROOT)


def _events(ev_type="p2p_trade"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeSession:
    def __init__(self, character, account=None):
        self.id = character["id"]
        self.character = character
        self.account = account
        self.lines: list = []

    async def send_line(self, msg=""):
        self.lines.append(msg)


class _FakeSessionMgr:
    def __init__(self, by_char):
        self._by_char = by_char

    def find_by_character(self, char_id):
        return self._by_char.get(char_id)

    async def broadcast_to_room(self, *a, **kw):
        pass


class _FakeDB:
    """Records the trade's ledger + inventory writes."""

    def __init__(self, *, adjust_returns_none=False,
                 offerer_has_item=True, item_name=""):
        self.credit_calls: list = []
        self.inv_added: list = []
        self.inv_removed: list = []
        self._adjust_returns_none = adjust_returns_none
        self._offerer_has_item = offerer_has_item
        self._item_name = item_name
        self._balances = {0: 0, 3: 10_000, 7: 5_000}

    async def adjust_credits(self, char_id, delta, tag, allow_negative=True):
        self.credit_calls.append((char_id, delta, tag))
        # The atomic offerer-debit guard returns None when it would go
        # negative; the real path then aborts before crediting/taxing.
        if (self._adjust_returns_none and tag == "p2p_transfer"
                and delta < 0 and allow_negative is False):
            return None
        self._balances[char_id] = self._balances.get(char_id, 0) + delta
        return self._balances[char_id]

    async def get_inventory(self, char_id):
        if self._offerer_has_item:
            return [{"key": "heavy_blaster_pistol", "name": self._item_name}]
        return []

    async def remove_from_inventory(self, char_id, key):
        self.inv_removed.append((char_id, key))
        return True

    async def add_to_inventory(self, char_id, data):
        self.inv_added.append((char_id, data))
        return True


class P2PTradeTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()
        bc._pending_trades.clear()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()
        bc._pending_trades.clear()

    # ── core driver: a populated offer + the real _accept ─────────────────────
    def _run_accept(self, *, kind="credits", amount=500,
                    item_name="Heavy Blaster Pistol",
                    offerer_acct=None, acceptor_acct=None, room=100,
                    offerer_credits=10_000, offerer_has_item=True,
                    adjust_returns_none=False):
        # `char` = the acceptor (calls "trade accept Alice"); offerer = giver.
        acceptor = {"id": 7, "name": "Bob", "credits": 5_000,
                    "room_id": room, "faction_id": None}
        offerer = {"id": 3, "name": "Alice", "credits": offerer_credits,
                   "room_id": room, "faction_id": None}
        acc_sess = _FakeSession(acceptor, account=acceptor_acct)
        off_sess = _FakeSession(offerer, account=offerer_acct)
        db = _FakeDB(adjust_returns_none=adjust_returns_none,
                     offerer_has_item=offerer_has_item, item_name=item_name)
        smgr = _FakeSessionMgr({3: off_sess})
        ctx = CommandContext(
            session=acc_sess, raw_input="trade accept Alice",
            command="trade", args="accept Alice", args_list=[],
            switches=[], db=db, session_mgr=smgr,
        )

        offer = {
            "offerer_id": 3, "offerer_name": "Alice",
            "target_id": 7, "target_name": "Bob",
            "ts": bc._trade_time.time(), "kind": kind, "amount": 0,
        }
        if kind == "credits":
            offer["amount"] = amount
        else:
            offer["item_key"] = "heavy_blaster_pistol"
            offer["item_name"] = item_name
            offer["item"] = {"key": "heavy_blaster_pistol", "name": item_name}
        bc._pending_trades[(3, 7)] = offer

        asyncio.run(bc.TradeCommand()._accept(ctx, acceptor, "Alice"))
        return db

    # ── credit trade: one event, envelope matches the ledger ──────────────────
    def test_credit_trade_emits_one_event(self):
        self._run_accept(kind="credits", amount=500)
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["kind"], "credits")
        self.assertEqual(e["from_char"], 3)        # offerer (giver)
        self.assertEqual(e["to_char"], 7)          # acceptor (recipient)
        self.assertEqual(e["room_id"], 100)
        self.assertEqual(e["amount"], 500)         # gross debited
        self.assertEqual(e["tax_pct"], 5)          # p2p.tax_pct default
        self.assertEqual(e["tax"], 25)             # max(1, 500*5//100)
        self.assertEqual(e["received"], 475)       # amount - tax
        # An item field never appears on a credit event.
        self.assertNotIn("item", e)

    def test_credit_event_matches_ledger_legs(self):
        db = self._run_accept(kind="credits", amount=500)
        e = _events()[0]
        # Three credit_flow legs: offerer debit, recipient credit, tax sink.
        debit = [c for c in db.credit_calls if c == (3, -500, "p2p_transfer")]
        credit = [c for c in db.credit_calls if c == (7, 475, "p2p_transfer")]
        tax = [c for c in db.credit_calls if c == (0, -25, "p2p_tax")]
        self.assertEqual(len(debit), 1)
        self.assertEqual(len(credit), 1)
        self.assertEqual(len(tax), 1)
        # The single event re-links what the three legs scatter.
        self.assertEqual(e["received"], credit[0][1])
        self.assertEqual(e["tax"], -tax[0][1])
        self.assertEqual(e["amount"], -debit[0][1])

    # ── item trade: the ONLY record of a credit_flow-invisible flow ───────────
    def test_item_trade_emits_one_event(self):
        db = self._run_accept(kind="item", item_name="Heavy Blaster Pistol")
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["kind"], "item")
        self.assertEqual(e["from_char"], 3)
        self.assertEqual(e["to_char"], 7)
        self.assertEqual(e["room_id"], 100)
        self.assertEqual(e["item"], "Heavy Blaster Pistol")
        # No credit fields on an item event.
        self.assertNotIn("amount", e)
        self.assertNotIn("tax", e)
        # The transfer really happened.
        self.assertEqual(db.inv_removed, [(3, "heavy_blaster_pistol")])
        self.assertEqual(len(db.inv_added), 1)

    def test_item_trade_is_dark_to_credit_flow(self):
        # The load-bearing justification: an item trade moves zero credits,
        # so credit_flow records NOTHING — this event is the sole signal.
        db = self._run_accept(kind="item")
        self.assertEqual(db.credit_calls, [])
        self.assertEqual(len(_events()), 1)

    # ── aborted / non-completing paths emit nothing ───────────────────────────
    def test_aborted_credit_debit_no_emit(self):
        # The atomic offerer-debit guard returns None → trade aborts before
        # the recipient is credited; no event, no recipient/tax legs.
        db = self._run_accept(kind="credits", amount=500,
                              adjust_returns_none=True)
        self.assertEqual(len(_events()), 0)
        # Only the (refused) debit attempt was made — no credit, no tax.
        self.assertNotIn((7, 475, "p2p_transfer"), db.credit_calls)
        self.assertNotIn((0, -25, "p2p_tax"), db.credit_calls)

    def test_item_trade_missing_item_no_emit(self):
        db = self._run_accept(kind="item", offerer_has_item=False)
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.inv_added, [])

    def test_no_pending_offer_no_emit(self):
        # Accept with an empty offer table → nothing to complete.
        acceptor = {"id": 7, "name": "Bob", "room_id": 100}
        ctx = CommandContext(
            session=_FakeSession(acceptor), raw_input="trade accept Alice",
            command="trade", args="accept Alice", args_list=[],
            switches=[], db=_FakeDB(), session_mgr=_FakeSessionMgr({}),
        )
        asyncio.run(bc.TradeCommand()._accept(ctx, acceptor, "Alice"))
        self.assertEqual(len(_events()), 0)

    # ── sampling honours the tunable, mutation still lands ────────────────────
    def test_sample_zero_suppresses_event_not_the_trade(self):
        tunables._TUNABLES["telemetry.p2p_trade_sample"] = 0.0
        db = self._run_accept(kind="credits", amount=500)
        self.assertEqual(len(_events()), 0)
        # Credits still moved despite no telemetry.
        self.assertIn((7, 475, "p2p_transfer"), db.credit_calls)

    def test_sample_default_captures(self):
        self._run_accept(kind="credits", amount=500)  # no tunable → 1.0
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the completed trade ────────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        with mock.patch.object(telemetry, "emit", _boom):
            db = self._run_accept(kind="credits", amount=500)
        # No crash; the trade resolved and the ledger was written.
        self.assertIn((7, 475, "p2p_transfer"), db.credit_calls)

    # ── helper unit: field schema for both kinds ──────────────────────────────
    def test_helper_credits_schema(self):
        bc._emit_trade_telemetry(
            kind="credits", from_id=3, to_id=7, room_id=42,
            amount=1000, received=950, tax=50, tax_pct=5)
        e = _events()[0]
        self.assertEqual(
            {e["kind"], e["from_char"], e["to_char"], e["room_id"],
             e["amount"], e["received"], e["tax"], e["tax_pct"]},
            {"credits", 3, 7, 42, 1000, 950, 50, 5})

    def test_helper_item_schema(self):
        bc._emit_trade_telemetry(
            kind="item", from_id=3, to_id=7, room_id=42, item="Vibroblade")
        e = _events()[0]
        self.assertEqual(e["kind"], "item")
        self.assertEqual(e["item"], "Vibroblade")
        self.assertNotIn("amount", e)

    def test_helper_coerces_none_ids(self):
        # Fail-open coercion: a None id never raises, lands as 0.
        bc._emit_trade_telemetry(
            kind="item", from_id=None, to_id=None, room_id=None, item="X")
        e = _events()[0]
        self.assertEqual(e["from_char"], 0)
        self.assertEqual(e["to_char"], 0)

    # ── both seams wired + tunable registered (source pins) ───────────────────
    def test_both_seams_call_helper(self):
        src = (REPO / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8")
        self.assertIn('kind="credits", from_id=offerer["id"]', src)
        self.assertIn('kind="item", from_id=offerer["id"]', src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.p2p_trade_sample:", ty)


if __name__ == "__main__":
    unittest.main()
