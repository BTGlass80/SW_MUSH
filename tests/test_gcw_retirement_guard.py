# -*- coding: utf-8 -*-
"""
tests/test_gcw_retirement_guard.py — T2.CW.gcw_retirement guard (2026-06-06)

Locks the GCW retirement in place. Asserts the deprecated Galactic-Civil-War
data tree and config surfaces are gone, the production era is clone_wars, and
the CW-reused organization/weapon strings are B3-clean. The org-axis legacy
rewicker (apply_org_rewicker / get_org_rewicker_map) is deliberately KEPT as a
permanent legacy-migration safety net and is NOT asserted gone here.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestGcwDataTreeGone(unittest.TestCase):
    def test_gcw_world_dir_absent(self):
        p = os.path.join(PROJECT_ROOT, "data", "worlds", "gcw")
        self.assertFalse(os.path.isdir(p), "data/worlds/gcw/ must be removed")

    def test_legacy_top_level_organizations_yaml_absent(self):
        p = os.path.join(PROJECT_ROOT, "data", "organizations.yaml")
        self.assertFalse(os.path.exists(p),
                         "legacy data/organizations.yaml must be removed")

    def test_clone_wars_tree_intact(self):
        cw = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
        self.assertTrue(os.path.isfile(os.path.join(cw, "era.yaml")))
        self.assertTrue(os.path.isfile(os.path.join(cw, "organizations.yaml")))


class TestOrganizationsConfigRetired(unittest.TestCase):
    def test_imperial_spec_equipment_gone(self):
        import engine.organizations as o
        self.assertFalse(hasattr(o, "IMPERIAL_SPEC_EQUIPMENT"))

    def test_imperial_spec_shims_gone(self):
        import engine.organizations as o
        self.assertFalse(hasattr(o, "prompt_imperial_specialization"))
        self.assertFalse(hasattr(o, "complete_imperial_specialization"))

    def test_no_empire_in_faction_constants(self):
        from engine.organizations import (
            STIPEND_TABLE, RANK_0_EQUIPMENT, RANK_1_EQUIPMENT,
            CROSS_FACTION_PENALTIES, SPEC_EQUIPMENT_BY_FACTION,
        )
        for code in ("empire", "rebel", "hutt", "bh_guild"):
            self.assertNotIn(code, RANK_0_EQUIPMENT)
            self.assertNotIn(code, RANK_1_EQUIPMENT)
            self.assertNotIn(code, SPEC_EQUIPMENT_BY_FACTION)
        self.assertNotIn("empire", CROSS_FACTION_PENALTIES)
        self.assertNotIn("rebel", CROSS_FACTION_PENALTIES)
        self.assertFalse(any(k[0] in ("empire", "rebel", "hutt", "bh_guild")
                             for k in STIPEND_TABLE))

    def test_gcw_only_catalog_items_gone(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in ("imperial_uniform", "se_14c_pistol", "e11_blaster_rifle",
                     "stormtrooper_armor", "datapad_imperial", "a280_rifle",
                     "rebel_combat_vest", "flight_suit_imperial"):
            self.assertNotIn(code, EQUIPMENT_CATALOG)

    def test_rewicker_retained_as_safety_net(self):
        import engine.organizations as o
        self.assertTrue(hasattr(o, "apply_org_rewicker"))
        self.assertTrue(hasattr(o, "get_org_rewicker_map"))


class TestEspionageFindingsRetired(unittest.TestCase):
    def test_no_gcw_faction_findings(self):
        from engine.espionage import _FACTION_FINDINGS
        for code in ("empire", "rebel", "hutt"):
            self.assertNotIn(code, _FACTION_FINDINGS)


class TestHousingConfigRetired(unittest.TestCase):
    def test_no_gcw_in_housing_constants(self):
        from engine.housing import (
            FACTION_QUARTER_TIERS, FACTION_HOME_PLANET, INSURGENT_FACTIONS,
        )
        gcw = ("empire", "rebel", "hutt", "bh_guild")
        self.assertFalse(any(k[0] in gcw for k in FACTION_QUARTER_TIERS))
        for code in gcw:
            self.assertNotIn(code, FACTION_HOME_PLANET)
        self.assertNotIn("rebel", INSURGENT_FACTIONS)


class TestChargenTemplatesRetired(unittest.TestCase):
    def test_legacy_gcw_template_literal_gone(self):
        import engine.chargen_templates_loader as c
        self.assertFalse(hasattr(c, "_LEGACY_TEMPLATES_GCW"))

    def test_empty_fallback_returns_empty_dict(self):
        from engine.chargen_templates_loader import _legacy_templates_dict
        self.assertEqual(_legacy_templates_dict(), {})


class TestProductionEraIsCloneWars(unittest.TestCase):
    def test_build_default_era_is_clone_wars(self):
        import inspect
        import build_mos_eisley
        sig = inspect.signature(build_mos_eisley.build)
        self.assertEqual(sig.parameters["era"].default, "clone_wars")

    def test_era_state_default_is_clone_wars(self):
        from engine.era_state import get_active_era, get_seeding_era
        self.assertEqual(get_active_era(), "clone_wars")
        self.assertEqual(get_seeding_era(), "clone_wars")


class TestB3CleanReusedStrings(unittest.TestCase):
    """The org/weapon strings the retirement touched must be B3-clean."""

    _BANNED = re.compile(
        r"\b(imperial|stormtrooper|rebel|rebels|alliance|the empire|"
        r"x-wing|tie fighter|tie-)\b", re.IGNORECASE)

    def test_reskinned_equipment_descriptions_clean(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in ("officers_sidearm", "encrypted_comlink", "blaster_pistol",
                     "dc15_blaster_rifle"):
            if code in EQUIPMENT_CATALOG:
                desc = EQUIPMENT_CATALOG[code].get("description", "")
                self.assertIsNone(self._BANNED.search(desc),
                                  f"{code} desc still B3-dirty: {desc!r}")

    def test_weapons_yaml_force_pike_clean(self):
        import yaml
        path = os.path.join(PROJECT_ROOT, "data", "weapons.yaml")
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        def _walk(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    yield from _walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from _walk(v)
            elif isinstance(obj, str):
                yield obj

        # stormtrooper_armor entry must be gone
        self.assertNotIn("stormtrooper_armor", (data or {}))
        for s in _walk(data):
            if "force_pike" in s.lower() or "vibro" in s.lower():
                self.assertIsNone(self._BANNED.search(s),
                                  f"weapons.yaml string B3-dirty: {s!r}")


if __name__ == "__main__":
    unittest.main()
