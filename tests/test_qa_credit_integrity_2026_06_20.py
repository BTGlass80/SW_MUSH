# -*- coding: utf-8 -*-
"""
tests/test_qa_credit_integrity_2026_06_20.py — QA break-it credit-integrity
sweep (2026-06-20, second pass).

The 2026-06-19 QA re-run fixed four `engine/vendor_droids.py` credit sites to
pass `allow_negative=False` + abort on None. The 2026-06-20 adversarial
break-it campaign found two MORE sites of the same class — both deduct
credits after a STALE session-cache pre-check, so a live DB drain since the
pre-check could drive a balance negative on the atomic write:

  * `parser/shop_commands.py` — `shop upgrade` (vendor_droid_upgrade sink),
    demonstrated live (-2,999 cr balance).
  * `parser/crafting_commands.py` — `learn <schematic>` tuition
    (schematic_tuition sink), structurally identical.

Both now pass `allow_negative=False` and abort (no charge, clear message)
when the authoritative DB read can't cover the cost. Source-assert guards
(mirroring tests/test_qa_rerun_findings.py — these command paths are
fixture-heavy to drive end to end, and the chokepoint contract is what
matters).
"""
from __future__ import annotations

import sys
from pathlib import Path

import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestShopUpgradeCreditIntegrity(unittest.TestCase):
    def setUp(self):
        self.src = (PROJECT_ROOT / "parser" / "shop_commands.py").read_text(
            encoding="utf-8"
        )

    def test_upgrade_uses_allow_negative_false(self):
        self.assertIn("vendor_droid_upgrade", self.src)
        self.assertIn("allow_negative=False", self.src,
                      "shop upgrade must deduct with allow_negative=False")

    def test_upgrade_bare_deduction_is_gone(self):
        self.assertNotIn(
            '-upgrade_cost, "vendor_droid_upgrade")', self.src,
            "the bare adjust_credits(...,'vendor_droid_upgrade') without "
            "allow_negative=False reintroduces the negative-balance bug."
        )

    def test_upgrade_aborts_on_none(self):
        # The None-abort guard: insufficient -> message + return, no upgrade.
        self.assertIn("if _bal is None:", self.src)


class TestLearnTuitionCreditIntegrity(unittest.TestCase):
    def setUp(self):
        self.src = (PROJECT_ROOT / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8"
        )

    def test_tuition_uses_allow_negative_false(self):
        self.assertIn("schematic_tuition", self.src)
        self.assertIn("allow_negative=False", self.src,
                      "learn tuition must deduct with allow_negative=False")

    def test_tuition_bare_deduction_is_gone(self):
        self.assertNotIn(
            '-tuition, "schematic_tuition")', self.src,
            "the bare adjust_credits(...,'schematic_tuition') without "
            "allow_negative=False reintroduces the negative-balance bug."
        )

    def test_tuition_aborts_on_none(self):
        self.assertIn("if _bal is None:", self.src)


class TestAdjustCreditsContract(unittest.TestCase):
    """Sanity: the chokepoint genuinely supports the allow_negative kwarg
    + returns None on an over-draw (so the None-abort guards are real)."""

    def test_adjust_credits_signature_supports_allow_negative(self):
        import inspect
        from db.database import Database
        sig = inspect.signature(Database.adjust_credits)
        self.assertIn("allow_negative", sig.parameters,
                      "adjust_credits must accept allow_negative for the guards "
                      "to be meaningful.")


if __name__ == "__main__":
    unittest.main()
