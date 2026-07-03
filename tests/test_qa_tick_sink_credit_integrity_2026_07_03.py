# -*- coding: utf-8 -*-
"""tests/test_qa_tick_sink_credit_integrity_2026_07_03.py — weekly-tick sink
credit-integrity.

The 2026-06-21 QA sweep (``test_qa_housing_credit_integrity_2026_06_21``) closed
the "stale pre-check + no ``allow_negative`` guard" credit-integrity bug class in
the PLAYER-INITIATED housing paths (``rent_room`` / ``purchase_home`` /
``purchase_shopfront``). It did not touch the two AUTOMATED weekly-tick sinks,
which carried the same class:

  * ``engine/debt.py::process_all_debts`` — the Hutt-debt weekly payment
    persisted the principal reduction via ``save_character`` BEFORE debiting
    credits, and debited with the default ``allow_negative=True`` against a STALE
    per-tick balance snapshot (the bulk SELECT at the top of the loop). A debit
    failure between the two writes handed out free debt forgiveness; a concurrent
    spend drove the balance negative.
  * ``engine/housing.py::tick_housing_rent`` — the weekly rent debit likewise
    used the default ``allow_negative=True`` against a per-row balance read, so a
    concurrent drain drove the balance negative while rent still "collected".

Fix (mirrors the player-path pattern): debit FIRST, atomically, with
``allow_negative=False``. A refused overdraw (``None``) is treated as a missed
payment / overdue rent instead of an overdraw. For debt, a principal-persist
failure AFTER a successful debit refunds the debit (sink compensation, mirroring
``engine/dens.py``) so a tenant is never charged without progress.

Deterministic stub-DB coverage (no live harness): drive the real tick functions
and assert the credit-integrity contract.

Run: python -m pytest tests/test_qa_tick_sink_credit_integrity_2026_07_03.py
"""
from __future__ import annotations

import asyncio
import json
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


# ── debt-tick stub DB ───────────────────────────────────────────────────────
class _DebtDB:
    """Records the ordered credit/persist calls the debt tick makes.

    ``credit_fn(char_id, delta, source, allow_negative)`` supplies the
    ``adjust_credits`` return (an int balance, or ``None`` to simulate an atomic
    overdraw refusal); it may also raise to simulate a debit fault.
    """

    def __init__(self, rows, *, credit_fn=None, save_raises=False):
        self.rows = rows
        self.calls = []          # ordered log of ("adjust", ...) / ("save", cid)
        self._credit_fn = credit_fn
        self._save_raises = save_raises
        self.saved_attrs = {}    # cid -> last SUCCESSFULLY persisted attrs

    async def fetchall(self, sql, params=None):
        return self.rows

    async def save_character(self, char_id, *, attributes=None, **kw):
        self.calls.append(("save", char_id))
        if self._save_raises:
            raise RuntimeError("persist boom")
        if attributes is not None:
            self.saved_attrs[char_id] = json.loads(attributes)

    async def adjust_credits(self, char_id, delta, source, *,
                             allow_negative=True):
        self.calls.append(("adjust", char_id, delta, source, allow_negative))
        if self._credit_fn is not None:
            return self._credit_fn(char_id, delta, source, allow_negative)
        return 1000

    # helpers for assertions
    def adjusts(self):
        return [c for c in self.calls if c[0] == "adjust"]

    def first_index(self, kind):
        for i, c in enumerate(self.calls):
            if c[0] == kind:
                return i
        return -1


def _debt_row(cid=1, credits=1000, principal=2000, missed=0):
    return {
        "id": cid,
        "credits": credits,
        "attributes": json.dumps({
            "hutt_debt": {
                "principal": principal,
                "total_paid": 0,
                "payments_missed": missed,
                "next_payment_due": 0,   # due (now > 0)
            }
        }),
    }


class TestDebtTickCreditIntegrity(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        telemetry.reset()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_happy_path_debits_before_persist_and_reduces_principal(self):
        from engine.debt import process_all_debts, DEBT_WEEKLY_PAYMENT
        db = _DebtDB([_debt_row(cid=1, credits=1000, principal=2000)],
                     credit_fn=lambda *a: 500)
        _run(process_all_debts(db, None))
        # The credit debit must precede the principal persist.
        di = db.first_index("adjust")
        si = db.first_index("save")
        self.assertGreaterEqual(di, 0, "debit must have been attempted")
        self.assertGreaterEqual(si, 0, "principal must have been persisted")
        self.assertLess(di, si, "the debit must run BEFORE the principal persist")
        # And it must be the guarded sink.
        first = db.adjusts()[0]
        self.assertEqual(first[2], -DEBT_WEEKLY_PAYMENT)
        self.assertEqual(first[3], "debt_payment")
        self.assertFalse(first[4], "debit must use allow_negative=False")
        # Principal actually dropped by the payment.
        self.assertEqual(
            db.saved_attrs[1]["hutt_debt"]["principal"],
            2000 - DEBT_WEEKLY_PAYMENT)

    def test_overdraw_refused_does_not_reduce_principal(self):
        from engine.debt import process_all_debts
        db = _DebtDB([_debt_row(cid=1, credits=1000, principal=2000)],
                     credit_fn=lambda *a: None)   # atomic refusal
        _run(process_all_debts(db, None))
        # Debit was attempted with the atomic guard...
        self.assertTrue(db.adjusts(), "a debit must have been attempted")
        self.assertFalse(db.adjusts()[0][4], "must use allow_negative=False")
        # ...but the principal was NOT reduced (refused == missed payment).
        self.assertEqual(db.saved_attrs[1]["hutt_debt"]["principal"], 2000)
        self.assertEqual(db.saved_attrs[1]["hutt_debt"]["payments_missed"], 1)
        # No refund leg — nothing was ever debited.
        self.assertNotIn("debt_payment_refund",
                         [c[3] for c in db.adjusts()])

    def test_debit_fault_gives_no_free_forgiveness(self):
        from engine.debt import process_all_debts

        def _boom(*a):
            raise RuntimeError("db locked")

        db = _DebtDB([_debt_row(cid=1, credits=1000, principal=2000)],
                     credit_fn=_boom)
        _run(process_all_debts(db, None))
        # The pre-fix bug: principal was persisted BEFORE the (failing) debit, so
        # the debtor got free forgiveness. Now the debit is first, so a fault
        # leaves the principal untouched (recorded as a missed payment).
        self.assertEqual(db.saved_attrs[1]["hutt_debt"]["principal"], 2000)
        self.assertEqual(db.saved_attrs[1]["hutt_debt"]["payments_missed"], 1)

    def test_persist_failure_refunds_the_debit(self):
        from engine.debt import process_all_debts, DEBT_WEEKLY_PAYMENT
        # Debit succeeds, but persisting the principal reduction fails.
        db = _DebtDB([_debt_row(cid=1, credits=1000, principal=2000)],
                     credit_fn=lambda *a: 500, save_raises=True)
        _run(process_all_debts(db, None))
        adj = db.adjusts()
        # Exactly the debit then its compensating refund — never charged net.
        self.assertEqual(adj[0][2], -DEBT_WEEKLY_PAYMENT)
        self.assertEqual(adj[0][3], "debt_payment")
        self.assertTrue(any(c[3] == "debt_payment_refund" and c[2] == DEBT_WEEKLY_PAYMENT
                            for c in adj),
                        "a failed principal persist must refund the debit")
        # Nothing was persisted (the save failed), so no reduced principal leaked.
        self.assertNotIn(1, db.saved_attrs)


# ── housing rent-tick stub DB ───────────────────────────────────────────────
class _HousingDB:
    def __init__(self, housing_rows, char_rows, *, credit_fn=None):
        self._housing = housing_rows
        self._chars = {c["id"]: c for c in char_rows}
        self._credit_fn = credit_fn
        self.executed = []       # list of (sql, params)

    async def fetchall(self, sql, params=None):
        if "player_housing" in sql:
            return list(self._housing)
        # characters lookup by id
        cid = params[0] if params else None
        c = self._chars.get(cid)
        return [c] if c else []

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return None

    async def commit(self):
        return None

    async def adjust_credits(self, char_id, delta, source, *,
                             allow_negative=True):
        self._last_adjust = (char_id, delta, source, allow_negative)
        if self._credit_fn is not None:
            return self._credit_fn(char_id, delta, source, allow_negative)
        return 800


class _NullSessions:
    def find_by_character(self, cid):
        return None


def _housing_row(hid=10, cid=1, rent=200):
    return {"id": hid, "char_id": cid, "weekly_rent": rent,
            "rent_paid_until": 0, "rent_overdue": 0,
            "housing_type": "apartment", "last_activity": 0}


class TestHousingRentTickCreditIntegrity(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        telemetry.reset()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_rent_overdraw_refused_marks_overdue_no_negative(self):
        from engine.housing import tick_housing_rent
        db = _HousingDB([_housing_row(rent=200)],
                        [{"id": 1, "credits": 1000}],   # stale says affordable
                        credit_fn=lambda *a: None)       # atomic refusal
        _run(tick_housing_rent(db, _NullSessions()))
        # Guarded debit was attempted.
        self.assertFalse(db._last_adjust[3], "rent debit must use allow_negative=False")
        self.assertEqual(db._last_adjust[2], "housing_rent")
        # The only UPDATE was the overdue increment — rent did NOT "collect".
        sqls = " ".join(sql for sql, _ in db.executed)
        self.assertIn("rent_overdue = ?", sqls)
        self.assertNotIn("rent_paid_until = ?", sqls)

    def test_rent_happy_path_collects_and_advances(self):
        from engine.housing import tick_housing_rent
        db = _HousingDB([_housing_row(rent=200)],
                        [{"id": 1, "credits": 1000}],
                        credit_fn=lambda *a: 800)
        _run(tick_housing_rent(db, _NullSessions()))
        self.assertEqual(db._last_adjust[1], -200)
        self.assertFalse(db._last_adjust[3])
        sqls = " ".join(sql for sql, _ in db.executed)
        self.assertIn("rent_paid_until = ?", sqls)
        self.assertIn("rent_overdue = 0", sqls)


# ── structural guards (drift-proof the ordering + the atomic flag) ──────────
def _func_body(src, name):
    m = re.search(rf"\nasync def {re.escape(name)}\b", src)
    assert m, f"function {name} not found"
    start = m.start()
    nxt = re.search(r"\nasync def ", src[start + 1:])
    end = start + 1 + nxt.start() if nxt else len(src)
    return src[start:end]


class TestTickSinkSourceGuards(unittest.TestCase):
    def test_debt_tick_debits_first_with_atomic_guard(self):
        src = open(os.path.join(PROJECT_ROOT, "engine", "debt.py"),
                   encoding="utf-8").read()
        body = _func_body(src, "process_all_debts")
        self.assertIn("allow_negative=False", body)
        self.assertIn("debt_payment_refund", body)   # persist-failure compensation
        # The debit must precede the principal-reducing save_character.
        debit = body.find('"debt_payment"')
        persist = body.find("save_character")
        self.assertNotEqual(debit, -1)
        self.assertNotEqual(persist, -1)
        self.assertLess(debit, persist,
                        "the debt debit must run BEFORE the principal persist")

    def test_housing_rent_tick_uses_atomic_guard(self):
        src = open(os.path.join(PROJECT_ROOT, "engine", "housing.py"),
                   encoding="utf-8").read()
        body = _func_body(src, "tick_housing_rent")
        self.assertIn("allow_negative=False", body)
        self.assertIn('"housing_rent"', body)


if __name__ == "__main__":
    unittest.main()
