# -*- coding: utf-8 -*-
"""
tests/test_b1b2_specialization_era_aware.py

Post-GCW-retirement CW-contract guard for the specialization system in
engine/organizations.py. IMPERIAL_SPEC_EQUIPMENT and the empire entry in
_SPEC_CONFIG_BY_FACTION / SPEC_EQUIPMENT_BY_FACTION were retired with the GCW
data tree. Republic is now the only faction with a specialization flow.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestRepublicSpecEquipment(unittest.TestCase):
    def test_four_specs_present(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        for spec in ("clone_trooper", "clone_pilot", "clone_officer",
                     "republic_intelligence"):
            self.assertIn(spec, REPUBLIC_SPEC_EQUIPMENT)

    def test_clone_trooper_gear(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        self.assertEqual(REPUBLIC_SPEC_EQUIPMENT["clone_trooper"],
                         ["dc15_blaster_rifle", "republic_light_armor"])

    def test_clone_pilot_gear(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        self.assertEqual(REPUBLIC_SPEC_EQUIPMENT["clone_pilot"],
                         ["flight_suit_republic"])

    def test_clone_officer_gear(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        self.assertEqual(REPUBLIC_SPEC_EQUIPMENT["clone_officer"],
                         ["officers_uniform_republic", "datapad_republic"])

    def test_republic_intelligence_reuses_spy_gear(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        self.assertEqual(REPUBLIC_SPEC_EQUIPMENT["republic_intelligence"],
                         ["civilian_cover", "slicing_kit"])

    def test_all_referenced_items_in_catalog(self):
        from engine.organizations import (
            REPUBLIC_SPEC_EQUIPMENT, EQUIPMENT_CATALOG,
        )
        for spec, items in REPUBLIC_SPEC_EQUIPMENT.items():
            for code in items:
                self.assertIn(code, EQUIPMENT_CATALOG,
                              f"{spec} item {code} not in catalog")


class TestImperialSpecRetired(unittest.TestCase):
    def test_imperial_spec_equipment_gone(self):
        import engine.organizations as orgs
        self.assertFalse(hasattr(orgs, "IMPERIAL_SPEC_EQUIPMENT"),
                         "IMPERIAL_SPEC_EQUIPMENT should be retired")

    def test_imperial_shims_gone(self):
        import engine.organizations as orgs
        self.assertFalse(hasattr(orgs, "prompt_imperial_specialization"))
        self.assertFalse(hasattr(orgs, "complete_imperial_specialization"))


class TestSpecEquipmentByFactionDispatch(unittest.TestCase):
    def test_dispatch_table_republic_only(self):
        from engine.organizations import (
            SPEC_EQUIPMENT_BY_FACTION, REPUBLIC_SPEC_EQUIPMENT,
        )
        self.assertIs(SPEC_EQUIPMENT_BY_FACTION["republic"],
                      REPUBLIC_SPEC_EQUIPMENT)
        self.assertNotIn("empire", SPEC_EQUIPMENT_BY_FACTION)

    def test_unknown_faction_returns_empty_via_get(self):
        from engine.organizations import SPEC_EQUIPMENT_BY_FACTION
        self.assertEqual(SPEC_EQUIPMENT_BY_FACTION.get("nonexistent", {}), {})


class TestNewCatalogItems(unittest.TestCase):
    def test_republic_spec_items_present(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in ("flight_suit_republic", "officers_uniform_republic",
                     "datapad_republic"):
            self.assertIn(code, EQUIPMENT_CATALOG)


class TestGenericDispatchHelpers(unittest.TestCase):
    def test_republic_has_specialization(self):
        from engine.organizations import faction_has_specialization
        self.assertTrue(faction_has_specialization("republic"))

    def test_gcw_and_other_factions_no_specialization(self):
        from engine.organizations import faction_has_specialization
        for code in ("empire", "rebel", "cis", "jedi_order", "hutt_cartel",
                     "bounty_hunters_guild", "independent", "nonexistent"):
            self.assertFalse(faction_has_specialization(code),
                             f"{code} should not have a specialization flow")

    def test_get_specialization_config_republic(self):
        from engine.organizations import get_specialization_config
        cfg = get_specialization_config("republic")
        self.assertIsNotNone(cfg)
        self.assertIn("spec_map", cfg)
        self.assertIn("menu_lines", cfg)

    def test_get_specialization_config_gcw_and_unknown_none(self):
        from engine.organizations import get_specialization_config
        self.assertIsNone(get_specialization_config("empire"))
        self.assertIsNone(get_specialization_config("nonexistent"))


class TestRepublicMenuB3Clean(unittest.TestCase):
    def test_republic_menu_has_no_imperial_or_rebel(self):
        from engine.organizations import get_specialization_config
        cfg = get_specialization_config("republic")
        blob = " ".join(cfg["menu_lines"]) + cfg.get("header_label", "")
        low = blob.lower()
        self.assertNotIn("imperial", low)
        self.assertNotIn("rebel", low)
        self.assertNotIn("stormtrooper", low)

    def test_republic_spec_map_complete(self):
        from engine.organizations import get_specialization_config
        cfg = get_specialization_config("republic")
        self.assertEqual(
            cfg["spec_map"],
            {1: "clone_trooper", 2: "clone_pilot",
             3: "clone_officer", 4: "republic_intelligence"},
        )


if __name__ == "__main__":
    unittest.main()
