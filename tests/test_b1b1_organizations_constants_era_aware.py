# -*- coding: utf-8 -*-
"""
tests/test_b1b1_organizations_constants_era_aware.py

Post-GCW-retirement (T2.CW.gcw_retirement, 2026-06-06) CW-contract guard for
engine/organizations.py faction constants. The GCW byte-equivalence classes
that pinned the empire/rebel/hutt/bh_guild entries were retired together with
the GCW data tree; these checks now assert the Clone-Wars-only contract and
that the GCW keys are gone.

Constants covered:
  1. STIPEND_TABLE          — CW factions only
  2. CROSS_FACTION_PENALTIES — republic↔cis only
  3. EQUIPMENT_CATALOG       — CW + shared items; no GCW-only items
  4. RANK_0_EQUIPMENT        — CW factions only
  5. RANK_1_EQUIPMENT        — CW factions only
  6. Cross-validation        — every RANK_* item exists in EQUIPMENT_CATALOG
  7. Era-cleanliness         — GCW faction keys absent
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_GCW_FACTIONS = ("empire", "rebel", "hutt", "bh_guild")
_CW_FACTIONS = ("republic", "cis", "jedi_order", "hutt_cartel",
                "bounty_hunters_guild")
_GCW_ONLY_ITEMS = (
    "imperial_uniform", "se_14c_pistol", "e11_blaster_rifle",
    "stormtrooper_armor", "officers_uniform", "datapad_imperial",
    "flight_suit_imperial", "flight_suit", "rebel_combat_vest", "a280_rifle",
)


# ──────────────────────────────────────────────────────────────────────
# 1. STIPEND_TABLE
# ──────────────────────────────────────────────────────────────────────
class TestStipendTableCW(unittest.TestCase):
    def test_republic_scale(self):
        from engine.organizations import STIPEND_TABLE
        for rank, amt in {1: 50, 2: 100, 3: 200, 4: 350, 5: 500, 6: 500}.items():
            self.assertEqual(STIPEND_TABLE[("republic", rank)], amt)

    def test_cis_scale(self):
        from engine.organizations import STIPEND_TABLE
        for rank, amt in {1: 25, 2: 50, 3: 100, 4: 200, 5: 300}.items():
            self.assertEqual(STIPEND_TABLE[("cis", rank)], amt)

    def test_jedi_order_present(self):
        from engine.organizations import STIPEND_TABLE
        self.assertGreater(STIPEND_TABLE[("jedi_order", 1)], 0)
        self.assertGreater(STIPEND_TABLE[("jedi_order", 2)], 0)

    def test_hutt_cartel_scale(self):
        from engine.organizations import STIPEND_TABLE
        for rank, amt in {1: 75, 2: 150, 3: 300, 4: 500, 5: 750}.items():
            self.assertEqual(STIPEND_TABLE[("hutt_cartel", rank)], amt)

    def test_bounty_hunters_guild_scale(self):
        from engine.organizations import STIPEND_TABLE
        for rank, amt in {1: 25, 2: 75, 3: 150, 4: 300, 5: 500}.items():
            self.assertEqual(STIPEND_TABLE[("bounty_hunters_guild", rank)], amt)

    def test_no_gcw_factions(self):
        from engine.organizations import STIPEND_TABLE
        for code in _GCW_FACTIONS:
            for rank in range(0, 7):
                self.assertNotIn((code, rank), STIPEND_TABLE,
                                 f"GCW stipend ({code},{rank}) should be gone")

    def test_unknown_returns_zero_via_get(self):
        from engine.organizations import STIPEND_TABLE
        self.assertEqual(STIPEND_TABLE.get(("nonexistent", 99), 0), 0)


# ──────────────────────────────────────────────────────────────────────
# 2. CROSS_FACTION_PENALTIES
# ──────────────────────────────────────────────────────────────────────
class TestCrossFactionPenaltiesCW(unittest.TestCase):
    def test_republic_cis_mirror(self):
        from engine.organizations import CROSS_FACTION_PENALTIES
        self.assertEqual(CROSS_FACTION_PENALTIES["republic"], {"cis": -0.5})
        self.assertEqual(CROSS_FACTION_PENALTIES["cis"], {"republic": -0.5})

    def test_jedi_and_hutt_cartel_do_not_cross_penalize(self):
        from engine.organizations import CROSS_FACTION_PENALTIES
        self.assertNotIn("jedi_order", CROSS_FACTION_PENALTIES)
        self.assertNotIn("hutt_cartel", CROSS_FACTION_PENALTIES)

    def test_no_gcw_pairs(self):
        from engine.organizations import CROSS_FACTION_PENALTIES
        self.assertNotIn("empire", CROSS_FACTION_PENALTIES)
        self.assertNotIn("rebel", CROSS_FACTION_PENALTIES)


# ──────────────────────────────────────────────────────────────────────
# 3. EQUIPMENT_CATALOG
# ──────────────────────────────────────────────────────────────────────
class TestEquipmentCatalogCW(unittest.TestCase):
    CW_ITEMS = (
        "republic_uniform", "dc17_pistol", "dc15_blaster_rifle",
        "republic_light_armor", "flight_suit_republic",
        "officers_uniform_republic", "datapad_republic", "civilian_gear",
        "heavy_blaster_pistol", "smuggler_vest", "padawan_robes",
        "jedi_utility_belt", "jedi_robes",
    )
    SHARED_ITEMS = (
        "improved_armor", "officers_sidearm", "civilian_cover", "slicing_kit",
        "encrypted_comlink", "blaster_pistol", "binder_cuffs", "guild_license",
        "tracking_fob", "medpac",
    )

    def test_cw_items_present(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in self.CW_ITEMS + self.SHARED_ITEMS:
            self.assertIn(code, EQUIPMENT_CATALOG, f"item {code} missing")

    def test_each_item_has_required_keys(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code, entry in EQUIPMENT_CATALOG.items():
            self.assertIn("name", entry, f"{code} missing name")
            self.assertIn("slot", entry, f"{code} missing slot")
            self.assertIn("description", entry, f"{code} missing description")
            self.assertIn(entry["slot"], ("weapon", "armor", "misc"))

    def test_no_gcw_only_items(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in _GCW_ONLY_ITEMS:
            self.assertNotIn(code, EQUIPMENT_CATALOG,
                             f"GCW-only item {code} should be gone")

    def test_reskinned_items_b3_clean(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in ("officers_sidearm", "encrypted_comlink", "blaster_pistol",
                     "dc15_blaster_rifle"):
            desc = EQUIPMENT_CATALOG[code]["description"].lower()
            for banned in ("imperial", "rebel"):
                self.assertNotIn(banned, desc,
                                 f"{code} description still B3-dirty: {desc!r}")


# ──────────────────────────────────────────────────────────────────────
# 4 & 5. RANK_0 / RANK_1 EQUIPMENT
# ──────────────────────────────────────────────────────────────────────
class TestRankEquipmentCW(unittest.TestCase):
    def test_rank0_cw_factions(self):
        from engine.organizations import RANK_0_EQUIPMENT
        for code in _CW_FACTIONS:
            self.assertIn(code, RANK_0_EQUIPMENT)

    def test_rank1_cw_factions(self):
        from engine.organizations import RANK_1_EQUIPMENT
        for code in _CW_FACTIONS:
            self.assertIn(code, RANK_1_EQUIPMENT)

    def test_rank0_no_gcw(self):
        from engine.organizations import RANK_0_EQUIPMENT
        for code in _GCW_FACTIONS:
            self.assertNotIn(code, RANK_0_EQUIPMENT)

    def test_rank1_no_gcw(self):
        from engine.organizations import RANK_1_EQUIPMENT
        for code in _GCW_FACTIONS:
            self.assertNotIn(code, RANK_1_EQUIPMENT)

    def test_get_fallback_empty(self):
        from engine.organizations import RANK_0_EQUIPMENT, RANK_1_EQUIPMENT
        self.assertEqual(RANK_0_EQUIPMENT.get("empire", []), [])
        self.assertEqual(RANK_1_EQUIPMENT.get("empire", []), [])


# ──────────────────────────────────────────────────────────────────────
# 6. Cross-validation: every RANK_* item exists in the catalog
# ──────────────────────────────────────────────────────────────────────
class TestRankItemsResolveInCatalog(unittest.TestCase):
    def test_all_rank_items_in_catalog(self):
        from engine.organizations import (
            EQUIPMENT_CATALOG, RANK_0_EQUIPMENT, RANK_1_EQUIPMENT,
        )
        for table in (RANK_0_EQUIPMENT, RANK_1_EQUIPMENT):
            for fac, items in table.items():
                for code in items:
                    self.assertIn(code, EQUIPMENT_CATALOG,
                                  f"{fac} item {code} not in EQUIPMENT_CATALOG")


if __name__ == "__main__":
    unittest.main()
