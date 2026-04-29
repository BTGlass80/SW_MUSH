# -*- coding: utf-8 -*-
"""
tests/test_b1b1_organizations_constants_era_aware.py — B.1.b.1 tests.

Per architecture v38 §19.7 and `b1_audit_v1.md` §3, B.1.b is the
extension of `engine/organizations.py` constants to support both eras.
Split into two sub-drops by scope:

  - **B.1.b.1 (this drop):** Pure data-table extensions. No code-flow
    changes. Five constants:
      1. `STIPEND_TABLE`    — extended with 5 CW factions × ranks
      2. `CROSS_FACTION_PENALTIES` — extended with republic↔cis mirror
      3. `EQUIPMENT_CATALOG` — added 10 CW item entries
      4. `RANK_0_EQUIPMENT`  — extended with 5 CW factions
      5. `RANK_1_EQUIPMENT`  — extended with 5 CW factions

  - **B.1.b.2 (next drop):** Specialization function extensions —
    REPUBLIC_SPEC_EQUIPMENT + Republic specialization prompt/complete
    helpers + `join_faction` branch + parser SpecializeCommand routing.

All extensions are additive; existing GCW entries are byte-equivalent
to pre-B.1.b. Tests are split into:

  - "ByteEquivalence" classes assert GCW behavior is unchanged.
  - "CWAdditions" classes assert the new CW entries exist and have
    the right shape.
  - "Schema" classes assert cross-table consistency (e.g., every
    item code in RANK_*_EQUIPMENT exists in EQUIPMENT_CATALOG).
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# 1. STIPEND_TABLE
# ──────────────────────────────────────────────────────────────────────

class TestStipendTableByteEquivalence(unittest.TestCase):
    """All GCW stipend entries must be byte-identical to pre-B.1.b."""

    def test_empire_entries_unchanged(self):
        from engine.organizations import STIPEND_TABLE
        expected = {
            ("empire", 1): 50,
            ("empire", 2): 100,
            ("empire", 3): 200,
            ("empire", 4): 350,
            ("empire", 5): 500,
            ("empire", 6): 500,
        }
        for k, v in expected.items():
            self.assertEqual(STIPEND_TABLE[k], v)

    def test_rebel_entries_unchanged(self):
        from engine.organizations import STIPEND_TABLE
        expected = {
            ("rebel", 1): 25,
            ("rebel", 2): 50,
            ("rebel", 3): 100,
            ("rebel", 4): 200,
            ("rebel", 5): 300,
            ("rebel", 6): 300,
        }
        for k, v in expected.items():
            self.assertEqual(STIPEND_TABLE[k], v)

    def test_hutt_entries_unchanged(self):
        from engine.organizations import STIPEND_TABLE
        expected = {
            ("hutt", 1): 75,
            ("hutt", 2): 150,
            ("hutt", 3): 300,
            ("hutt", 4): 500,
            ("hutt", 5): 750,
        }
        for k, v in expected.items():
            self.assertEqual(STIPEND_TABLE[k], v)

    def test_bh_guild_entries_unchanged(self):
        from engine.organizations import STIPEND_TABLE
        expected = {
            ("bh_guild", 1): 25,
            ("bh_guild", 2): 75,
            ("bh_guild", 3): 150,
            ("bh_guild", 4): 300,
            ("bh_guild", 5): 500,
        }
        for k, v in expected.items():
            self.assertEqual(STIPEND_TABLE[k], v)


class TestStipendTableCWAdditions(unittest.TestCase):
    """CW factions must be present with sensible payouts."""

    def test_republic_mirrors_empire_scale(self):
        from engine.organizations import STIPEND_TABLE
        # Republic is the lawful state of the era; pay scale should
        # mirror the empire scale (B.1.b.1 design decision).
        for rank in range(1, 7):
            self.assertEqual(
                STIPEND_TABLE[("republic", rank)],
                STIPEND_TABLE[("empire", rank)],
                f"republic rank {rank} should match empire pay",
            )

    def test_cis_mirrors_rebel_scale(self):
        from engine.organizations import STIPEND_TABLE
        # CIS is the insurgent of the era; pay mirrors rebel scale.
        # CIS only goes to rank 5 per CW orgs YAML.
        for rank in range(1, 6):
            self.assertEqual(
                STIPEND_TABLE[("cis", rank)],
                STIPEND_TABLE[("rebel", rank)],
                f"cis rank {rank} should match rebel pay",
            )

    def test_jedi_order_present(self):
        from engine.organizations import STIPEND_TABLE
        # Jedi Order has only ranks 1 (Knight) and 2 (Master); rank 0
        # (Padawan) gets no stipend.
        self.assertIn(("jedi_order", 1), STIPEND_TABLE)
        self.assertIn(("jedi_order", 2), STIPEND_TABLE)
        self.assertGreater(STIPEND_TABLE[("jedi_order", 1)], 0)
        self.assertGreater(STIPEND_TABLE[("jedi_order", 2)], 0)

    def test_hutt_cartel_rename_matches_hutt(self):
        from engine.organizations import STIPEND_TABLE
        # hutt_cartel is the CW rename of hutt; pay scale is identical.
        for rank in range(1, 6):
            self.assertEqual(
                STIPEND_TABLE[("hutt_cartel", rank)],
                STIPEND_TABLE[("hutt", rank)],
                f"hutt_cartel rank {rank} should match hutt pay",
            )

    def test_bounty_hunters_guild_rename_matches_bh_guild(self):
        from engine.organizations import STIPEND_TABLE
        for rank in range(1, 6):
            self.assertEqual(
                STIPEND_TABLE[("bounty_hunters_guild", rank)],
                STIPEND_TABLE[("bh_guild", rank)],
                f"bounty_hunters_guild rank {rank} should match bh_guild pay",
            )

    def test_unknown_faction_rank_returns_zero_via_get(self):
        from engine.organizations import STIPEND_TABLE
        # Production code uses `STIPEND_TABLE.get((org_code, rank), 0)`;
        # missing keys must yield 0 not raise.
        self.assertEqual(STIPEND_TABLE.get(("nonexistent", 99), 0), 0)


# ──────────────────────────────────────────────────────────────────────
# 2. CROSS_FACTION_PENALTIES
# ──────────────────────────────────────────────────────────────────────

class TestCrossFactionPenaltiesByteEquivalence(unittest.TestCase):

    def test_gcw_pair_unchanged(self):
        from engine.organizations import CROSS_FACTION_PENALTIES
        self.assertEqual(CROSS_FACTION_PENALTIES["empire"], {"rebel": -0.5})
        self.assertEqual(CROSS_FACTION_PENALTIES["rebel"],  {"empire": -0.5})


class TestCrossFactionPenaltiesCWAdditions(unittest.TestCase):

    def test_republic_cis_mirror_present(self):
        from engine.organizations import CROSS_FACTION_PENALTIES
        self.assertEqual(CROSS_FACTION_PENALTIES["republic"], {"cis": -0.5})
        self.assertEqual(CROSS_FACTION_PENALTIES["cis"],      {"republic": -0.5})

    def test_jedi_order_does_not_cross_penalize(self):
        from engine.organizations import CROSS_FACTION_PENALTIES
        # Per CW v3 §3.1 design decision: Jedi faction is village-quest-
        # gated and is "a way of life" rather than a political affiliation.
        # No cross-penalty.
        self.assertNotIn("jedi_order", CROSS_FACTION_PENALTIES)

    def test_hutt_cartel_does_not_cross_penalize(self):
        from engine.organizations import CROSS_FACTION_PENALTIES
        # Hutts are neutral in the war; same as GCW.
        self.assertNotIn("hutt_cartel", CROSS_FACTION_PENALTIES)
        self.assertNotIn("hutt", CROSS_FACTION_PENALTIES)


# ──────────────────────────────────────────────────────────────────────
# 3. EQUIPMENT_CATALOG
# ──────────────────────────────────────────────────────────────────────

class TestEquipmentCatalogByteEquivalence(unittest.TestCase):
    """Existing GCW item entries must be byte-identical."""

    GCW_ITEMS = [
        "imperial_uniform", "se_14c_pistol", "e11_blaster_rifle",
        "stormtrooper_armor", "improved_armor", "officers_sidearm",
        "officers_uniform", "datapad_imperial", "flight_suit_imperial",
        "civilian_cover", "slicing_kit",
        "encrypted_comlink", "blaster_pistol", "flight_suit",
        "rebel_combat_vest", "a280_rifle",
        "binder_cuffs", "guild_license", "tracking_fob",
        "medpac",
    ]

    def test_all_gcw_items_present(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in self.GCW_ITEMS:
            self.assertIn(code, EQUIPMENT_CATALOG, f"GCW item {code} missing")

    def test_imperial_uniform_unchanged(self):
        from engine.organizations import EQUIPMENT_CATALOG
        e = EQUIPMENT_CATALOG["imperial_uniform"]
        self.assertEqual(e["name"], "Imperial Officer's Uniform")
        self.assertEqual(e["slot"], "armor")

    def test_e11_blaster_rifle_unchanged(self):
        from engine.organizations import EQUIPMENT_CATALOG
        e = EQUIPMENT_CATALOG["e11_blaster_rifle"]
        self.assertEqual(e["name"], "E-11 Blaster Rifle")
        self.assertEqual(e["slot"], "weapon")

    def test_blaster_pistol_unchanged(self):
        from engine.organizations import EQUIPMENT_CATALOG
        # blaster_pistol is shared between rebel and CW factions; the
        # GCW entry must remain (DH-17, 4D damage).
        e = EQUIPMENT_CATALOG["blaster_pistol"]
        self.assertEqual(e["name"], "DH-17 Blaster Pistol")


class TestEquipmentCatalogCWAdditions(unittest.TestCase):
    """The 10 CW item codes referenced by the CW orgs YAML must be present."""

    CW_NEW_ITEMS = [
        "republic_uniform", "dc17_pistol", "dc15_blaster_rifle",
        "republic_light_armor",
        "civilian_gear", "heavy_blaster_pistol", "smuggler_vest",
        "padawan_robes", "jedi_utility_belt", "jedi_robes",
    ]

    def test_all_cw_items_present(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in self.CW_NEW_ITEMS:
            self.assertIn(code, EQUIPMENT_CATALOG, f"CW item {code} missing")

    def test_each_cw_item_has_required_keys(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in self.CW_NEW_ITEMS:
            entry = EQUIPMENT_CATALOG[code]
            self.assertIn("name", entry, f"{code} missing name")
            self.assertIn("slot", entry, f"{code} missing slot")
            self.assertIn("description", entry, f"{code} missing description")
            # Slot must be one of the recognized values
            self.assertIn(entry["slot"], ("weapon", "armor", "misc"),
                          f"{code} has unknown slot {entry['slot']!r}")

    def test_cw_weapons_classed_correctly(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in ("dc17_pistol", "dc15_blaster_rifle", "heavy_blaster_pistol"):
            self.assertEqual(EQUIPMENT_CATALOG[code]["slot"], "weapon")

    def test_cw_armor_classed_correctly(self):
        from engine.organizations import EQUIPMENT_CATALOG
        for code in ("republic_uniform", "republic_light_armor",
                     "smuggler_vest", "padawan_robes", "jedi_robes"):
            self.assertEqual(EQUIPMENT_CATALOG[code]["slot"], "armor")


# ──────────────────────────────────────────────────────────────────────
# 4. RANK_0_EQUIPMENT
# ──────────────────────────────────────────────────────────────────────

class TestRank0EquipmentByteEquivalence(unittest.TestCase):

    def test_empire_unchanged(self):
        from engine.organizations import RANK_0_EQUIPMENT
        self.assertEqual(RANK_0_EQUIPMENT["empire"],
                         ["imperial_uniform", "se_14c_pistol"])

    def test_rebel_unchanged(self):
        from engine.organizations import RANK_0_EQUIPMENT
        self.assertEqual(RANK_0_EQUIPMENT["rebel"], ["encrypted_comlink"])

    def test_hutt_unchanged(self):
        from engine.organizations import RANK_0_EQUIPMENT
        self.assertEqual(RANK_0_EQUIPMENT["hutt"], [])

    def test_bh_guild_unchanged(self):
        from engine.organizations import RANK_0_EQUIPMENT
        self.assertEqual(RANK_0_EQUIPMENT["bh_guild"],
                         ["binder_cuffs", "guild_license"])


class TestRank0EquipmentCWAdditions(unittest.TestCase):

    def test_all_cw_factions_present(self):
        from engine.organizations import RANK_0_EQUIPMENT
        for code in ("republic", "cis", "jedi_order",
                     "hutt_cartel", "bounty_hunters_guild"):
            self.assertIn(code, RANK_0_EQUIPMENT)

    def test_republic_rank0_matches_yaml(self):
        from engine.organizations import RANK_0_EQUIPMENT
        # Per data/worlds/clone_wars/organizations.yaml: Conscript gets
        # republic_uniform + dc17_pistol.
        self.assertEqual(RANK_0_EQUIPMENT["republic"],
                         ["republic_uniform", "dc17_pistol"])

    def test_jedi_order_rank0_matches_yaml(self):
        from engine.organizations import RANK_0_EQUIPMENT
        # Padawans get robes + utility belt; lightsaber via Village quest.
        self.assertEqual(RANK_0_EQUIPMENT["jedi_order"],
                         ["padawan_robes", "jedi_utility_belt"])

    def test_cis_rank0_matches_yaml(self):
        from engine.organizations import RANK_0_EQUIPMENT
        # Sympathizer just gets a comlink.
        self.assertEqual(RANK_0_EQUIPMENT["cis"], ["encrypted_comlink"])

    def test_bounty_hunters_guild_matches_legacy(self):
        from engine.organizations import RANK_0_EQUIPMENT
        # Direct rename of bh_guild.
        self.assertEqual(RANK_0_EQUIPMENT["bounty_hunters_guild"],
                         RANK_0_EQUIPMENT["bh_guild"])


# ──────────────────────────────────────────────────────────────────────
# 5. RANK_1_EQUIPMENT
# ──────────────────────────────────────────────────────────────────────

class TestRank1EquipmentByteEquivalence(unittest.TestCase):

    def test_empire_unchanged(self):
        from engine.organizations import RANK_1_EQUIPMENT
        # Empire handles rank-1 via specialization, not the catalog.
        self.assertEqual(RANK_1_EQUIPMENT["empire"], [])

    def test_rebel_unchanged(self):
        from engine.organizations import RANK_1_EQUIPMENT
        self.assertEqual(RANK_1_EQUIPMENT["rebel"],
                         ["blaster_pistol", "flight_suit"])

    def test_bh_guild_unchanged(self):
        from engine.organizations import RANK_1_EQUIPMENT
        self.assertEqual(RANK_1_EQUIPMENT["bh_guild"], ["tracking_fob"])


class TestRank1EquipmentCWAdditions(unittest.TestCase):

    def test_all_cw_factions_present(self):
        from engine.organizations import RANK_1_EQUIPMENT
        for code in ("republic", "cis", "jedi_order",
                     "hutt_cartel", "bounty_hunters_guild"):
            self.assertIn(code, RANK_1_EQUIPMENT)

    def test_republic_rank1_matches_yaml(self):
        from engine.organizations import RANK_1_EQUIPMENT
        # Private gets DC-15A rifle + light armor.
        self.assertEqual(RANK_1_EQUIPMENT["republic"],
                         ["dc15_blaster_rifle", "republic_light_armor"])

    def test_jedi_order_rank1_matches_yaml(self):
        from engine.organizations import RANK_1_EQUIPMENT
        # Knight gets the earned robes.
        self.assertEqual(RANK_1_EQUIPMENT["jedi_order"], ["jedi_robes"])

    def test_hutt_cartel_rank1_matches_yaml(self):
        from engine.organizations import RANK_1_EQUIPMENT
        self.assertEqual(RANK_1_EQUIPMENT["hutt_cartel"],
                         ["heavy_blaster_pistol", "smuggler_vest"])


# ──────────────────────────────────────────────────────────────────────
# 6. Cross-table schema consistency
# ──────────────────────────────────────────────────────────────────────

class TestCrossTableSchemaConsistency(unittest.TestCase):
    """Every item code referenced by RANK_*_EQUIPMENT must exist in
    EQUIPMENT_CATALOG. This is the schema gate that would catch any
    typo in either file."""

    def test_all_rank0_items_exist_in_catalog(self):
        from engine.organizations import RANK_0_EQUIPMENT, EQUIPMENT_CATALOG
        missing = []
        for faction, items in RANK_0_EQUIPMENT.items():
            for code in items:
                if code not in EQUIPMENT_CATALOG:
                    missing.append((faction, code))
        self.assertEqual(missing, [],
                         f"RANK_0_EQUIPMENT references items not in catalog: {missing}")

    def test_all_rank1_items_exist_in_catalog(self):
        from engine.organizations import RANK_1_EQUIPMENT, EQUIPMENT_CATALOG
        missing = []
        for faction, items in RANK_1_EQUIPMENT.items():
            for code in items:
                if code not in EQUIPMENT_CATALOG:
                    missing.append((faction, code))
        self.assertEqual(missing, [],
                         f"RANK_1_EQUIPMENT references items not in catalog: {missing}")

    def test_cw_rank_equipment_aligns_with_yaml(self):
        """Spot-check that the in-Python RANK_*_EQUIPMENT values match
        the data/worlds/clone_wars/organizations.yaml ranks[level=0/1]
        equipment lists. If the YAML drifts, this catches it."""
        import os, yaml
        yaml_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "organizations.yaml",
        )
        if not os.path.exists(yaml_path):
            self.skipTest("CW organizations.yaml not present in this checkout")
        with open(yaml_path, "r", encoding="utf-8") as f:
            cw = yaml.safe_load(f)

        from engine.organizations import (
            RANK_0_EQUIPMENT, RANK_1_EQUIPMENT,
        )

        # Build code -> {level: equipment_list} from YAML
        yaml_equip = {}
        for fac in cw.get("factions", []):
            code = fac.get("code")
            if not code:
                continue
            per_rank = {}
            for r in fac.get("ranks", []):
                level = r.get("level")
                if level in (0, 1):
                    per_rank[level] = list(r.get("equipment", []))
            yaml_equip[code] = per_rank

        # Now compare for the 5 CW factions we care about
        cw_factions = ("republic", "cis", "jedi_order",
                       "hutt_cartel", "bounty_hunters_guild")
        for code in cw_factions:
            if code not in yaml_equip:
                continue   # YAML may not include all (e.g., npc_only)
            yaml_r0 = yaml_equip[code].get(0, [])
            yaml_r1 = yaml_equip[code].get(1, [])
            py_r0 = RANK_0_EQUIPMENT.get(code, [])
            py_r1 = RANK_1_EQUIPMENT.get(code, [])
            self.assertEqual(
                py_r0, yaml_r0,
                f"{code} rank-0 mismatch: py={py_r0!r} vs yaml={yaml_r0!r}",
            )
            self.assertEqual(
                py_r1, yaml_r1,
                f"{code} rank-1 mismatch: py={py_r1!r} vs yaml={yaml_r1!r}",
            )


# ──────────────────────────────────────────────────────────────────────
# 7. Production lookup pattern (defensive)
# ──────────────────────────────────────────────────────────────────────

class TestProductionLookupPattern(unittest.TestCase):
    """Production code uses .get(...) on these dicts; CW additions must
    not change the .get() default-return contract for unknown keys."""

    def test_stipend_get_default_zero(self):
        from engine.organizations import STIPEND_TABLE
        self.assertEqual(STIPEND_TABLE.get(("missing", 1), 0), 0)

    def test_rank0_get_default_empty_list(self):
        from engine.organizations import RANK_0_EQUIPMENT
        self.assertEqual(RANK_0_EQUIPMENT.get("missing", []), [])

    def test_rank1_get_default_empty_list(self):
        from engine.organizations import RANK_1_EQUIPMENT
        self.assertEqual(RANK_1_EQUIPMENT.get("missing", []), [])

    def test_catalog_get_default_empty_dict(self):
        from engine.organizations import EQUIPMENT_CATALOG
        # `format_equipment_inventory` does `EQUIPMENT_CATALOG.get(e, {}).get("name", e)`
        self.assertEqual(EQUIPMENT_CATALOG.get("missing", {}).get("name", "fallback"),
                         "fallback")

    def test_cross_faction_penalties_get_default_empty(self):
        from engine.organizations import CROSS_FACTION_PENALTIES
        # `adjust_rep` does `CROSS_FACTION_PENALTIES.get(faction_code, {})`
        self.assertEqual(CROSS_FACTION_PENALTIES.get("missing", {}), {})


if __name__ == "__main__":
    unittest.main()
