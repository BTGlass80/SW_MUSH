# -*- coding: utf-8 -*-
"""
tests/test_drop1b1_crew_vendor_ledger.py -- Drop 1.b.1 (ledger migration tranche 1)

Drop 1.b migrates the credit-write sites that still bypass the credit_log
onto the ``Database.adjust_credits`` chokepoint introduced in Drop 1.a, in the
remediation doc's priority order (crew wages -> vendor -> harvest ->
entertainer -> city tax -> Director -> rest).

Tranche 1.b.1 covers the first two groups: **crew wages** (`parser/crew_commands.py`)
and the **vendor-droid** player-shop economy (`engine/vendor_droids.py`) — 7
previously-UNLOGGED credit movements (deploy cost, buyer purchase, owner escrow
collect, buy-order escrow fund / refund / fill payout, first-day crew wage).

`adjust_credits` behaviour itself is covered by
`tests/test_drop1a_adjust_credits.py`; the vendor/crew gameplay paths are
covered behaviourally by `test_session39` (vendor droids), `test_cities_phase4`
(vendor + city tax), and `test_session56` (crew). This file is the
structural-negative migration pin: it guarantees these two files no longer
write credits outside the chokepoint, and that the expected source tags are in
place — so a future edit can't silently reintroduce an unlogged
`save_character(credits=...)` here.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_MIGRATED_FILES = [
    "parser/crew_commands.py",
    "engine/vendor_droids.py",
    "db/database.py",
]

# Source tags introduced by this tranche (grouped, dashboard-legible).
_EXPECTED_TAGS = {
    "parser/crew_commands.py": ["crew_wage"],
    "db/database.py": ["crew_wages"],
    "engine/vendor_droids.py": [
        "vendor_droid_deploy",
        "vendor_purchase",
        "vendor_escrow_collect",
        "vendor_buy_order_escrow",
        "vendor_buy_order_refund",
        "vendor_buy_order_payout",
    ],
}


def _read(rel):
    with open(os.path.join(PROJECT_ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


class TestDrop1b1MigrationComplete(unittest.TestCase):
    def test_no_credit_writing_save_character_remains(self):
        """No `save_character(... credits ...)` (logged or unlogged) should
        remain in the migrated files — every credit movement routes through
        adjust_credits. (Non-credit save_character calls — e.g. inventory-only
        — are fine and expected.)"""
        offenders = {}
        for rel in _MIGRATED_FILES:
            src = _read(rel)
            # A save_character call whose argument list mentions `credits`.
            hits = re.findall(r"save_character\([^)]*credits", src)
            if hits:
                offenders[rel] = len(hits)
        self.assertEqual(
            offenders, {},
            "Migrated files must move credits via adjust_credits, not "
            f"save_character(credits=...). Offenders: {offenders}",
        )

    def test_no_direct_log_credit_remains(self):
        # db/database.py is excluded here: it *defines* log_credit and
        # adjust_credits (which internally calls log_credit).  The check
        # targets external call-sites that bypassed adjust_credits by
        # calling log_credit directly — not the implementation file itself.
        _LOG_CREDIT_EXEMPT = {"db/database.py"}
        offenders = {}
        for rel in _MIGRATED_FILES:
            if rel in _LOG_CREDIT_EXEMPT:
                continue
            if re.findall(r"\blog_credit\s*\(", _read(rel)):
                offenders[rel] = True
        self.assertEqual(offenders, {},
                         f"Migrated files must not call log_credit directly: {offenders}")

    def test_files_use_adjust_credits(self):
        for rel in _MIGRATED_FILES:
            self.assertIn("adjust_credits(", _read(rel),
                          f"{rel} should route credit movement through adjust_credits")


class TestDrop1b1SourceTags(unittest.TestCase):
    def test_expected_source_tags_present(self):
        for rel, tags in _EXPECTED_TAGS.items():
            src = _read(rel)
            for tag in tags:
                self.assertIn(
                    f'"{tag}"', src,
                    f"{rel} should carry the '{tag}' credit source tag",
                )


if __name__ == "__main__":
    unittest.main()
