# -*- coding: utf-8 -*-
"""
tests/test_b1d2_housing_codeflow_era_aware.py

Post-GCW-retirement CW-contract guard for engine/housing.py faction-quarter
code flow. INSURGENT_FACTIONS no longer carries the legacy 'rebel'; the CIS is
the Clone-Wars insurgent. FACTION_QUARTER_LOTS carries CW anchors only.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_GCW = ("empire", "rebel", "hutt", "bh_guild")


class TestInsurgentFactions(unittest.TestCase):
    def test_set_is_cis_only(self):
        from engine.housing import INSURGENT_FACTIONS
        self.assertIn("cis", INSURGENT_FACTIONS)
        self.assertNotIn("rebel", INSURGENT_FACTIONS)

    def test_cis_is_insurgent(self):
        from engine.housing import is_insurgent_faction
        self.assertTrue(is_insurgent_faction("cis"))

    def test_non_insurgents(self):
        from engine.housing import is_insurgent_faction
        for code in ("republic", "jedi_order", "hutt_cartel",
                     "bounty_hunters_guild", "empire", "rebel", "hutt",
                     "independent", "nonexistent"):
            self.assertFalse(is_insurgent_faction(code),
                             f"{code} should not be insurgent")


class TestFactionQuarterLotsCW(unittest.TestCase):
    def test_cw_anchors_present(self):
        from engine.housing import FACTION_QUARTER_LOTS
        self.assertIn(("jedi_order", "coruscant"), FACTION_QUARTER_LOTS)
        self.assertIn(("republic", "coruscant"), FACTION_QUARTER_LOTS)
        self.assertIn(("cis", "geonosis"), FACTION_QUARTER_LOTS)
        self.assertIn(("hutt_cartel", "nar_shaddaa"), FACTION_QUARTER_LOTS)

    def test_no_gcw_anchors(self):
        from engine.housing import FACTION_QUARTER_LOTS
        gcw_keys = [k for k in FACTION_QUARTER_LOTS if k[0] in _GCW]
        self.assertEqual(gcw_keys, [], f"GCW anchors leaked: {gcw_keys}")


if __name__ == "__main__":
    unittest.main()
