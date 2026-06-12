# -*- coding: utf-8 -*-
"""
tests/test_b1d1_housing_constants_era_aware.py

Post-GCW-retirement CW-contract guard for engine/housing.py faction-quarter
constants. The GCW (empire/rebel/hutt) tier/home-planet/HQ-desc entries were
retired with the GCW data tree; CW factions remain.
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


class TestFactionQuarterTiersCW(unittest.TestCase):
    def test_cw_factions_present(self):
        from engine.housing import FACTION_QUARTER_TIERS
        facs = {k[0] for k in FACTION_QUARTER_TIERS}
        for code in ("republic", "cis", "jedi_order", "hutt_cartel"):
            self.assertIn(code, facs)

    def test_no_gcw_factions(self):
        from engine.housing import FACTION_QUARTER_TIERS
        facs = {k[0] for k in FACTION_QUARTER_TIERS}
        for code in _GCW:
            self.assertNotIn(code, facs)

    def test_storage_increases_by_rank_for_republic(self):
        from engine.housing import FACTION_QUARTER_TIERS
        rep = sorted((rank, cfg["storage_max"])
                     for (fc, rank), cfg in FACTION_QUARTER_TIERS.items()
                     if fc == "republic")
        caps = [c for _, c in rep]
        self.assertEqual(caps, sorted(caps), "republic storage not monotonic")

    def test_jedi_order_rank_keywords(self):
        from engine.housing import FACTION_QUARTER_TIERS
        labels = {rank: cfg["label"]
                  for (fc, rank), cfg in FACTION_QUARTER_TIERS.items()
                  if fc == "jedi_order"}
        self.assertTrue(any("Jedi Temple" in v for v in labels.values()))

    def test_all_cw_entries_have_required_keys(self):
        from engine.housing import FACTION_QUARTER_TIERS
        for key, cfg in FACTION_QUARTER_TIERS.items():
            for field in ("label", "storage_max", "room_name", "room_desc"):
                self.assertIn(field, cfg, f"{key} missing {field}")


class TestFactionHomePlanetCW(unittest.TestCase):
    def test_cw_home_planets(self):
        from engine.housing import FACTION_HOME_PLANET
        self.assertEqual(FACTION_HOME_PLANET["republic"], "coruscant")
        self.assertEqual(FACTION_HOME_PLANET["cis"], "geonosis")
        self.assertEqual(FACTION_HOME_PLANET["jedi_order"], "coruscant")
        self.assertEqual(FACTION_HOME_PLANET["hutt_cartel"], "nar_shaddaa")

    def test_no_gcw_home_planets(self):
        from engine.housing import FACTION_HOME_PLANET
        for code in _GCW:
            self.assertNotIn(code, FACTION_HOME_PLANET)

    def test_bounty_hunters_guild_absent(self):
        from engine.housing import FACTION_HOME_PLANET
        self.assertNotIn("bounty_hunters_guild", FACTION_HOME_PLANET)


class TestTier5RoomDescsCW(unittest.TestCase):
    def test_cw_keys_present(self):
        from engine.housing import _TIER5_ROOM_DESCS
        for code in ("republic", "cis", "jedi_order", "hutt_cartel", "default"):
            self.assertIn(code, _TIER5_ROOM_DESCS)

    def test_no_gcw_keys(self):
        from engine.housing import _TIER5_ROOM_DESCS
        for code in _GCW:
            self.assertNotIn(code, _TIER5_ROOM_DESCS)


class TestPlanetView(unittest.TestCase):
    def test_cw_planets_have_views(self):
        from engine.housing import _planet_view
        for p in ("coruscant", "kuat", "kamino", "geonosis", "tatooine",
                  "nar_shaddaa"):
            self.assertNotEqual(_planet_view(p), "the street outside",
                                f"{p} should have a custom view")

    def test_gcw_planets_fall_to_default(self):
        from engine.housing import _planet_view
        self.assertEqual(_planet_view("kessel"), "the street outside")
        self.assertEqual(_planet_view("corellia"), "the street outside")


if __name__ == "__main__":
    unittest.main()
