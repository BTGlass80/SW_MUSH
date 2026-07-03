# -*- coding: utf-8 -*-
"""tests/test_qa_stale_snapshot_sink_credit_integrity_2026_07_03.py —
stale-session-snapshot sink credit-integrity.

The tick-sink pass (``test_qa_tick_sink_credit_integrity_2026_07_03``) closed the
AUTOMATED weekly-tick sinks. This pass closes the same credit-integrity class in
three PLAYER-FACING sinks that debited a delta computed from a *cached* session
balance (``credits = char.get("credits", 0)``) applied with the default
``allow_negative=True``:

  * ``parser/smuggling_commands.py`` — the customs FINE (``check_patrol_on_launch``
    + ``check_patrol_on_arrival``): ``adjust_credits(cid, new-credits, "smuggling_fine")``.
  * ``parser/sabacc_commands.py`` — a LOSS/TIE/FUMBLE: ``adjust_credits(cid,
    new_credits - credits, "sabacc")`` where ``new_credits = max(0, credits - bet)``.
  * ``engine/sleeping.py::attempt_pickpocket`` — the THEFT transfer: debited the
    victim off a cached snapshot, and a fault crediting the thief destroyed the
    credits (debited victim, thief gained nothing, no refund).

When the cached snapshot is stale (an out-of-band weekly-debt / housing-rent
tick, or an earlier theft, drained the real balance since the character was
loaded) the delta overdraws the LIVE balance and the column goes negative.

Fix: a shared funnel helper ``db.debit_capped(char_id, cost, source)`` charges up
to ``cost`` against the live balance (``allow_negative=False``; floors at the real
remaining balance), and the theft becomes an atomic transfer that refunds the
victim if crediting the thief fails.

Run: python -m pytest tests/test_qa_stale_snapshot_sink_credit_integrity_2026_07_03.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── faithful adjust_credits/get_character stub ──────────────────────────────
class _CreditStub:
    """Stands in for a Database for ``debit_capped``: a faithful atomic
    ``adjust_credits`` (refuses an overdraw when ``allow_negative=False``) plus
    ``get_character``. ``debit_capped`` is invoked as an unbound method with this
    stub as ``self`` so the REAL helper logic is exercised."""

    def __init__(self, balance):
        self.balance = int(balance)
        self.calls = []   # (char_id, delta, source, allow_negative)

    async def adjust_credits(self, char_id, delta, source, *,
                             allow_negative=True):
        self.calls.append((char_id, delta, source, allow_negative))
        if delta < 0 and not allow_negative and self.balance + delta < 0:
            return None   # atomic overdraw refusal — nothing applied
        self.balance += delta
        return self.balance

    async def get_character(self, char_id):
        return {"id": char_id, "credits": self.balance}


class TestDebitCapped(unittest.TestCase):
    """Behavioural coverage of the real ``Database.debit_capped`` helper."""

    def _call(self, stub, cost, source="test_sink"):
        from db.database import Database
        return _run(Database.debit_capped(stub, 1, cost, source))

    def test_covered_charge_takes_full_cost(self):
        stub = _CreditStub(1000)
        out = self._call(stub, 200)
        self.assertEqual(out, 800)
        self.assertEqual(stub.balance, 800)
        # The fast path uses the atomic guard.
        self.assertEqual(stub.calls[0], (1, -200, "test_sink", False))
        self.assertEqual(len(stub.calls), 1, "covered charge is a single debit")

    def test_overdraw_floors_to_live_balance_never_negative(self):
        # Stale caller thinks they can pay 500; live balance is only 120.
        stub = _CreditStub(120)
        out = self._call(stub, 500)
        self.assertEqual(out, 0, "floors to zero, never overdraws")
        self.assertEqual(stub.balance, 0)
        # First the guarded attempt is refused, then exactly the live 120 is taken.
        self.assertEqual(stub.calls[0], (1, -500, "test_sink", False))
        self.assertEqual(stub.calls[1], (1, -120, "test_sink", True))
        self.assertGreaterEqual(stub.balance, 0)

    def test_broke_target_charges_nothing(self):
        stub = _CreditStub(0)
        out = self._call(stub, 300)
        self.assertEqual(out, 0)
        self.assertEqual(stub.balance, 0)
        # Guard refused; no second (real) debit is issued against a 0 balance.
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(stub.calls[0][3], False)

    def test_zero_cost_is_a_noop_no_debit(self):
        stub = _CreditStub(750)
        out = self._call(stub, 0)
        self.assertEqual(out, 750)
        self.assertEqual(stub.calls, [], "cost==0 issues no credit movement")

    def test_negative_cost_charged_as_magnitude(self):
        stub = _CreditStub(1000)
        out = self._call(stub, -150)   # a caller passing a signed cost
        self.assertEqual(out, 850)
        self.assertEqual(stub.calls[0], (1, -150, "test_sink", False))

    def test_every_movement_routes_through_the_funnel(self):
        # No path mutates a balance except via adjust_credits (ledger/funnel).
        stub = _CreditStub(50)
        self._call(stub, 999)
        for c in stub.calls:
            self.assertEqual(c[2], "test_sink")
        # exactly: refused guard, then the floored real debit.
        self.assertEqual([c[1] for c in stub.calls], [-999, -50])


# ── structural drift-guards on the three call sites ─────────────────────────
def _read(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _func_body(src, name):
    m = re.search(rf"\n[ \t]*async def {re.escape(name)}\b", src)
    assert m, f"function {name} not found"
    start = m.start()
    nxt = re.search(r"\n[ \t]*async def ", src[start + 1:])
    end = start + 1 + nxt.start() if nxt else len(src)
    return src[start:end]


class TestSinkCallSiteGuards(unittest.TestCase):
    def test_debit_capped_helper_exists_and_is_funnel_routed(self):
        body = _func_body(_read("db", "database.py"), "debit_capped")
        self.assertIn("allow_negative=False", body)
        # It must move credits only through the funnel, never a raw UPDATE.
        self.assertIn("self.adjust_credits", body)
        self.assertNotIn("UPDATE characters", body)

    def test_smuggling_fine_uses_capped_debit_both_sites(self):
        src = _read("parser", "smuggling_commands.py")
        # Both patrol paths route the fine through the capped helper...
        self.assertEqual(
            src.count('debit_capped(char_id, fine, "smuggling_fine")'), 2)
        # ...and the stale-snapshot delta debit is gone.
        self.assertNotIn(
            'adjust_credits(char_id, new_credits - credits, "smuggling_fine")',
            src)

    def test_sabacc_loss_uses_capped_debit(self):
        src = _read("parser", "sabacc_commands.py")
        self.assertIn('debit_capped(char["id"], bet, "sabacc")', src)
        # The win branch stays a plain faucet; the old snapshot-delta call is gone.
        self.assertIn('net_win, "sabacc"', src)
        self.assertNotIn(
            'adjust_credits(char["id"], new_credits - credits, "sabacc")', src)

    def test_theft_is_an_atomic_refunding_transfer(self):
        body = _func_body(_read("engine", "sleeping.py"), "attempt_pickpocket")
        # Reads the LIVE victim balance rather than trusting the cached snapshot.
        self.assertIn("get_character(target_char", body)
        # Debits the victim with the atomic overdraw guard...
        self.assertIn('allow_negative=False', body)
        # ...and refunds the victim if crediting the thief fails.
        self.assertIn('"theft_loss_refund"', body)


if __name__ == "__main__":
    unittest.main()
