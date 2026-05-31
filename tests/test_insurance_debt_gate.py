# -*- coding: utf-8 -*-
"""
tests/test_insurance_debt_gate.py — engine/insurance_debt.py

Per progression_gates_and_consequences_design_v1.md §4.4.

Drop 1 of the May 21 2026 phantom-rebuild wave: replaces the
phantom `engine.insurance_debt` module that `parser/pc_bounty_commands.py`
and `engine/organizations.py` reference. The full HEAD audit
(HEAD_AUDIT_MAY21.md) showed 15 failing tests in PG.2.bounty
suites all collapsing to this one missing import.

Test sections
=============

  1. TestModuleSurface             — exports + constants
  2. TestServiceLabels             — formatting / unknown service handling
  3. TestZeroDebtAllows            — no debt → allow
  4. TestMissingDebtRowAllows      — None / 0 row → allow
  5. TestDebtBlocks                — positive debt → block
  6. TestRefusalFormat             — refusal text shape
  7. TestRefusalAmountFormat       — thousands separator
  8. TestUnknownServiceTreatedAsBP — unknown service still gates
  9. TestFailSoftOnDbError         — lookup raise → allow (fail-open)
 10. TestGetDebtHelper             — get_debt: zero, positive, missing
 11. TestGetDebtFailSoft           — get_debt: lookup raise → 0
 12. TestHasDebtHelper             — has_debt: bool form
 13. TestGateAcrossServices        — same debt blocks every gated service
 14. TestNoSideEffects             — gate is read-only
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ─── Minimal in-memory DB fake ────────────────────────────────────────
# We don't need real SQLite for these tests. The gate only calls
# db.get_insurance_debt(char_id); a fake is sharper than a real DB
# fixture for this unit and avoids coupling the test suite to the
# v18/v29 schema details.


class _FakeDB:
    def __init__(self, debts: dict | None = None, raise_on_lookup: bool = False):
        # debts: char_id -> outstanding debt int
        self._debts = dict(debts or {})
        self._raise = raise_on_lookup
        self.lookups = []  # log of (char_id,) calls
        self.mutations = []  # any write call should be empty

    async def get_insurance_debt(self, char_id: int):
        self.lookups.append(char_id)
        if self._raise:
            raise RuntimeError("simulated DB failure")
        return self._debts.get(char_id)

    # Anything else should fail loudly — the gate must not mutate.
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        def _trap(*a, **kw):
            self.mutations.append((name, a, kw))
            raise AssertionError(
                f"FakeDB: gate must not call .{name}() "
                f"(args={a}, kwargs={kw})"
            )
        return _trap


# ═════════════════════════════════════════════════════════════════════
# 1. Module surface
# ═════════════════════════════════════════════════════════════════════

class TestModuleSurface(unittest.TestCase):
    def test_constants_exported(self):
        from engine.insurance_debt import (
            BOUNTY_POST, FACTION_STIPEND, BH_TIER_VENDOR, ALL_SERVICES,
        )
        self.assertEqual(BOUNTY_POST, "bounty_post")
        self.assertEqual(FACTION_STIPEND, "faction_stipend")
        self.assertEqual(BH_TIER_VENDOR, "bh_tier_vendor")
        self.assertIn(BOUNTY_POST, ALL_SERVICES)
        self.assertIn(FACTION_STIPEND, ALL_SERVICES)
        self.assertIn(BH_TIER_VENDOR, ALL_SERVICES)

    def test_callables_exported(self):
        from engine.insurance_debt import check_debt_gate, get_debt, has_debt
        self.assertTrue(callable(check_debt_gate))
        self.assertTrue(callable(get_debt))
        self.assertTrue(callable(has_debt))


# ═════════════════════════════════════════════════════════════════════
# 2. Service labels
# ═════════════════════════════════════════════════════════════════════

class TestServiceLabels(unittest.TestCase):
    def test_labels_cover_all_services(self):
        from engine.insurance_debt import SERVICE_LABELS, ALL_SERVICES
        for svc in ALL_SERVICES:
            self.assertIn(svc, SERVICE_LABELS,
                          f"missing label for service {svc!r}")
            self.assertIsInstance(SERVICE_LABELS[svc], str)
            self.assertTrue(SERVICE_LABELS[svc])  # non-empty

    def test_labels_are_action_phrases(self):
        from engine.insurance_debt import SERVICE_LABELS, BOUNTY_POST
        # Should read naturally inside "You cannot {label} until ..."
        self.assertIn("bounty", SERVICE_LABELS[BOUNTY_POST])


# ═════════════════════════════════════════════════════════════════════
# 3. Zero debt allows
# ═════════════════════════════════════════════════════════════════════

class TestZeroDebtAllows(unittest.TestCase):
    def test_zero_debt(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 0})
        allowed, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertTrue(allowed)
        self.assertIsNone(refusal)


# ═════════════════════════════════════════════════════════════════════
# 4. Missing debt row allows
# ═════════════════════════════════════════════════════════════════════

class TestMissingDebtRowAllows(unittest.TestCase):
    def test_no_row(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({})  # char not in dict; lookup returns None
        allowed, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertTrue(allowed)
        self.assertIsNone(refusal)


# ═════════════════════════════════════════════════════════════════════
# 5. Positive debt blocks
# ═════════════════════════════════════════════════════════════════════

class TestDebtBlocks(unittest.TestCase):
    def test_one_credit_debt_blocks(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 1})
        allowed, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertFalse(allowed)
        self.assertIsNotNone(refusal)

    def test_large_debt_blocks(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 50_000})
        allowed, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertFalse(allowed)
        self.assertIsNotNone(refusal)


# ═════════════════════════════════════════════════════════════════════
# 6. Refusal text format
# ═════════════════════════════════════════════════════════════════════

class TestRefusalFormat(unittest.TestCase):
    def test_mentions_bh_guild(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 500})
        _, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertIn("BH Guild", refusal)

    def test_mentions_action(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 500})
        _, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertIn("bounty", refusal.lower())

    def test_mentions_paydown_command(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 500})
        _, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        # Should reference +bounty debt and +bounty pay
        self.assertIn("+bounty", refusal)

    def test_no_leading_indent(self):
        # Caller (pc_bounty_commands) prefixes "  "; gate must not.
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 500})
        _, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertFalse(refusal.startswith(" "))


# ═════════════════════════════════════════════════════════════════════
# 7. Refusal amount format
# ═════════════════════════════════════════════════════════════════════

class TestRefusalAmountFormat(unittest.TestCase):
    def test_thousands_separator_for_large_amounts(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 12_345})
        _, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertIn("12,345", refusal)

    def test_small_amount_no_separator_needed(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 50})
        _, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertIn("50 cr", refusal)


# ═════════════════════════════════════════════════════════════════════
# 8. Unknown service still gates
# ═════════════════════════════════════════════════════════════════════

class TestUnknownServiceTreatedAsBP(unittest.TestCase):
    def test_unknown_service_with_debt_still_blocks(self):
        from engine.insurance_debt import check_debt_gate
        db = _FakeDB({42: 500})
        allowed, refusal = _run(check_debt_gate(db, 42, "made_up_service"))
        self.assertFalse(allowed)
        self.assertIsNotNone(refusal)

    def test_unknown_service_with_no_debt_allows(self):
        from engine.insurance_debt import check_debt_gate
        db = _FakeDB({42: 0})
        allowed, refusal = _run(check_debt_gate(db, 42, "made_up_service"))
        self.assertTrue(allowed)
        self.assertIsNone(refusal)


# ═════════════════════════════════════════════════════════════════════
# 9. Fail-soft on DB error
# ═════════════════════════════════════════════════════════════════════

class TestFailSoftOnDbError(unittest.TestCase):
    def test_db_raise_returns_allowed(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 999_999}, raise_on_lookup=True)
        allowed, refusal = _run(check_debt_gate(db, 42, BOUNTY_POST))
        # Fail-open: even with notional debt, if lookup raises we allow.
        self.assertTrue(allowed)
        self.assertIsNone(refusal)


# ═════════════════════════════════════════════════════════════════════
# 10. get_debt helper
# ═════════════════════════════════════════════════════════════════════

class TestGetDebtHelper(unittest.TestCase):
    def test_zero(self):
        from engine.insurance_debt import get_debt
        db = _FakeDB({42: 0})
        self.assertEqual(_run(get_debt(db, 42)), 0)

    def test_positive(self):
        from engine.insurance_debt import get_debt
        db = _FakeDB({42: 500})
        self.assertEqual(_run(get_debt(db, 42)), 500)

    def test_missing_row(self):
        from engine.insurance_debt import get_debt
        db = _FakeDB({})
        self.assertEqual(_run(get_debt(db, 42)), 0)


# ═════════════════════════════════════════════════════════════════════
# 11. get_debt fail-soft
# ═════════════════════════════════════════════════════════════════════

class TestGetDebtFailSoft(unittest.TestCase):
    def test_raise_returns_zero(self):
        from engine.insurance_debt import get_debt
        db = _FakeDB({42: 500}, raise_on_lookup=True)
        self.assertEqual(_run(get_debt(db, 42)), 0)


# ═════════════════════════════════════════════════════════════════════
# 12. has_debt helper
# ═════════════════════════════════════════════════════════════════════

class TestHasDebtHelper(unittest.TestCase):
    def test_zero(self):
        from engine.insurance_debt import has_debt
        db = _FakeDB({42: 0})
        self.assertFalse(_run(has_debt(db, 42)))

    def test_positive(self):
        from engine.insurance_debt import has_debt
        db = _FakeDB({42: 1})
        self.assertTrue(_run(has_debt(db, 42)))

    def test_missing(self):
        from engine.insurance_debt import has_debt
        db = _FakeDB({})
        self.assertFalse(_run(has_debt(db, 42)))


# ═════════════════════════════════════════════════════════════════════
# 13. Gate across services
# ═════════════════════════════════════════════════════════════════════

class TestGateAcrossServices(unittest.TestCase):
    def test_debt_blocks_every_known_service(self):
        from engine.insurance_debt import (
            check_debt_gate, ALL_SERVICES,
        )
        db = _FakeDB({42: 100})
        for svc in ALL_SERVICES:
            allowed, refusal = _run(check_debt_gate(db, 42, svc))
            self.assertFalse(allowed, f"{svc} should be blocked")
            self.assertIsNotNone(refusal, f"{svc} should refuse")

    def test_no_debt_allows_every_known_service(self):
        from engine.insurance_debt import (
            check_debt_gate, ALL_SERVICES,
        )
        db = _FakeDB({42: 0})
        for svc in ALL_SERVICES:
            allowed, refusal = _run(check_debt_gate(db, 42, svc))
            self.assertTrue(allowed, f"{svc} should be allowed")
            self.assertIsNone(refusal, f"{svc} should not refuse")


# ═════════════════════════════════════════════════════════════════════
# 14. No side effects
# ═════════════════════════════════════════════════════════════════════

class TestNoSideEffects(unittest.TestCase):
    """The gate must only read. The _FakeDB will raise on any other
    attribute access; if the gate ever calls a write helper, this
    test will turn into a hard error during the lookup."""

    def test_gate_calls_only_get_insurance_debt(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 500})
        _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertEqual(db.lookups, [42])
        self.assertEqual(db.mutations, [])

    def test_zero_debt_gate_calls_only_get_insurance_debt(self):
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        db = _FakeDB({42: 0})
        _run(check_debt_gate(db, 42, BOUNTY_POST))
        self.assertEqual(db.lookups, [42])
        self.assertEqual(db.mutations, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
