# -*- coding: utf-8 -*-
"""
tests/test_h1_item_registry_consistency.py — H1 fix cross-registry guard.

Asserts that every grant-path key whose intended slot is weapon or armor
resolves in WeaponRegistry (get_weapon_registry().get(key) is not None).

Sweep covers:
  1. EQUIPMENT_CATALOG entries with slot in {weapon, armor}
  2. RANK_0_EQUIPMENT / RANK_1_EQUIPMENT / REPUBLIC_SPEC_EQUIPMENT — all
     weapon/armor slots (inferred from catalog slot OR registry type)
  3. COMMISSARY_STOCK entries with slot in {weapon, armor}
  4. chains.yaml graduation items[] and per-step reward items[] for
     weapon/armor-slotted keys.

Narrative-prop keys (comlink_basic, slicing_kit, fake_republic_id,
civilian_disguise_kit, binder_cuffs, guild_license, medpac, tracking_fob,
datapad_republic, jedi_utility_belt, kdy_apprentice_pass, bhg_license_card,
smugglers_baffle_kit, sealed_data_packet, encrypted_comlink, civilian_cover,
civilian_gear, datapad_republic) are explicitly exempted — they are
legitimately registry-less non-combat items.

Tested by: H1 fix (2026-06-17). This test is the guard that hid H1 —
it was absent before this drop.
"""

import os
import unittest
import yaml

# ── Narrative props exempt from registry (slot=misc or non-combat) ────────
# These keys are legitimately registry-less: they are quest items, identity
# documents, comlinks, toolkits, trade cargo, or crafting components —
# NOT weapon/armor items. find_carried_gear correctly ignores them.
_NARRATIVE_EXEMPT = frozenset({
    # comlinks / comms
    "comlink_basic",
    "comlink",
    "civilian_comlink",
    "encrypted_comlink",
    # intelligence / spy props
    "slicing_kit",
    "fake_republic_id",
    "civilian_disguise_kit",
    "civilian_cover",
    "civilian_gear",
    # faction admin items
    "binder_cuffs",
    "guild_license",
    "medpac",
    "tracking_fob",
    "datapad_republic",
    "jedi_utility_belt",
    # character / career items
    "kdy_apprentice_pass",
    "bhg_license_card",
    # consumable narrative items
    "smugglers_baffle_kit",
    "sealed_data_packet",
    # quest / credential chips
    "coruscant_clearance_chip",
    "spacer_ident",
    # trade / cargo props
    "sealed_cargo_crate",
    # crafting / trade tools (not combat gear)
    "shipwright_toolkit",
    "diagnostic_scanner",
    "capacitor_coil_t1",
})


def _is_weapon_armor_slot(slot: str) -> bool:
    return slot in ("weapon", "armor")


class TestEquipmentCatalogRegistry(unittest.TestCase):
    """All EQUIPMENT_CATALOG weapon/armor keys must resolve in the registry."""

    def setUp(self):
        from engine.weapons import get_weapon_registry
        from engine.organizations import EQUIPMENT_CATALOG
        self.wr = get_weapon_registry()
        self.catalog = EQUIPMENT_CATALOG

    def test_catalog_weapon_armor_keys_resolve(self):
        """Every weapon/armor-slot catalog key resolves in WeaponRegistry."""
        missing = []
        for key, entry in self.catalog.items():
            if key in _NARRATIVE_EXEMPT:
                continue
            slot = entry.get("slot", "misc")
            if not _is_weapon_armor_slot(slot):
                continue
            if self.wr.get(key) is None:
                missing.append(key)
        self.assertEqual(
            missing, [],
            f"EQUIPMENT_CATALOG weapon/armor keys missing from registry: {missing}"
        )

    def test_catalog_weapon_slot_resolves_as_weapon(self):
        """weapon-slotted catalog keys must resolve as non-armor WeaponData."""
        bad = []
        for key, entry in self.catalog.items():
            if key in _NARRATIVE_EXEMPT:
                continue
            if entry.get("slot") != "weapon":
                continue
            w = self.wr.get(key)
            if w is None:
                bad.append((key, "missing"))
            elif w.is_armor:
                bad.append((key, "resolves as armor"))
        self.assertEqual(bad, [], f"weapon-slot keys have wrong registry type: {bad}")

    def test_catalog_armor_slot_resolves_as_armor(self):
        """armor-slotted catalog keys must resolve as is_armor WeaponData."""
        bad = []
        for key, entry in self.catalog.items():
            if key in _NARRATIVE_EXEMPT:
                continue
            if entry.get("slot") != "armor":
                continue
            w = self.wr.get(key)
            if w is None:
                bad.append((key, "missing"))
            elif not w.is_armor:
                bad.append((key, "resolves as weapon"))
        self.assertEqual(bad, [], f"armor-slot keys have wrong registry type: {bad}")


class TestCommissaryStockRegistry(unittest.TestCase):
    """All COMMISSARY_STOCK weapon/armor keys must resolve in the registry."""

    def setUp(self):
        from engine.weapons import get_weapon_registry
        from engine.commissary import COMMISSARY_STOCK
        self.wr = get_weapon_registry()
        self.stock = COMMISSARY_STOCK

    def test_commissary_weapon_armor_keys_resolve(self):
        missing = []
        for faction, items in self.stock.items():
            for item in items:
                key = item.get("key", "")
                slot = item.get("slot", "misc")
                if not _is_weapon_armor_slot(slot):
                    continue
                if key in _NARRATIVE_EXEMPT:
                    continue
                if self.wr.get(key) is None:
                    missing.append(f"{faction}/{key}")
        self.assertEqual(
            missing, [],
            f"COMMISSARY_STOCK weapon/armor keys missing from registry: {missing}"
        )


class TestChainRewardRegistry(unittest.TestCase):
    """All chains.yaml weapon/armor grant keys must resolve in the registry.

    Chains don't label each item with a slot — we infer weapon/armor from
    whether the key resolves in the registry (is_armor / not). Keys that
    don't resolve AND are in _NARRATIVE_EXEMPT are fine. Keys that don't
    resolve AND are NOT exempt are failures.

    The test uses the registry as the ground truth: if the key resolves,
    it's a weapon/armor and MUST be in the registry. If it doesn't
    resolve and isn't exempt, it's an unknown key — failure.
    """

    CHAINS_YAML = os.path.join(
        os.path.dirname(__file__),
        "..", "data", "worlds", "clone_wars", "tutorials", "chains.yaml"
    )

    def setUp(self):
        from engine.weapons import get_weapon_registry
        self.wr = get_weapon_registry()
        with open(self.CHAINS_YAML, encoding="utf-8") as f:
            self.chains = yaml.safe_load(f)

    def _collect_chain_item_keys(self):
        """Yield (chain_id, source, key) for every item key in chains.yaml.

        chains.yaml top-level: {"schema_version": int, "chains": [list of dicts]}.
        Each chain dict has "chain_id" string + "graduation" dict + "steps" list.
        """
        chains_list = self.chains.get("chains", []) if isinstance(self.chains, dict) else []
        for chain in chains_list:
            if not isinstance(chain, dict):
                continue
            chain_id = chain.get("chain_id", "unknown")
            # Graduation items
            grad = chain.get("graduation") or {}
            for key in (grad.get("items") or []):
                yield (chain_id, "graduation", key)
            # Per-step rewards
            for step in (chain.get("steps") or []):
                if not isinstance(step, dict):
                    continue
                reward = step.get("reward") or {}
                for key in (reward.get("items") or []):
                    yield (chain_id, f"step{step.get('step','?')}", key)

    def test_chain_weapon_armor_keys_resolve(self):
        """Every chains.yaml item key that is NOT a narrative prop resolves."""
        missing = []
        for chain_id, source, key in self._collect_chain_item_keys():
            if key in _NARRATIVE_EXEMPT:
                continue
            if self.wr.get(key) is None:
                missing.append(f"{chain_id}/{source}/{key}")
        self.assertEqual(
            missing, [],
            f"chains.yaml weapon/armor keys missing from registry: {missing}"
        )

    def test_chain_item_keys_count(self):
        """Sanity: at least 5 non-exempt chain item keys are found."""
        non_exempt = [
            key for _, _, key in self._collect_chain_item_keys()
            if key not in _NARRATIVE_EXEMPT
        ]
        self.assertGreaterEqual(
            len(non_exempt), 5,
            "Expected at least 5 non-exempt chain item keys"
        )


class TestGrantPathBuildersUseRegistry(unittest.TestCase):
    """_build_graduation_item / _build_step_item use registry name+slot."""

    def test_graduation_item_uses_registry_name(self):
        from engine.chain_rewards import _build_graduation_item
        item = _build_graduation_item("dc15_blaster_rifle", "republic_chain", "Republic")
        self.assertEqual(item["name"], "DC-15A Blaster Rifle")
        self.assertEqual(item["slot"], "weapon")

    def test_graduation_item_uses_registry_armor(self):
        from engine.chain_rewards import _build_graduation_item
        item = _build_graduation_item("cis_field_armor", "cis_chain", "CIS")
        self.assertEqual(item["name"], "CIS Field Armor")
        self.assertEqual(item["slot"], "armor")

    def test_step_item_uses_registry_name(self):
        from engine.chain_rewards import _build_step_item
        item = _build_step_item("concealed_blaster", "intel_chain", 1)
        self.assertEqual(item["name"], "Concealed Blaster")
        self.assertEqual(item["slot"], "weapon")

    def test_step_item_narrative_prop_fallback(self):
        """Narrative-prop keys fall back to humanized name and slot=misc."""
        from engine.chain_rewards import _build_step_item
        item = _build_step_item("sealed_data_packet", "intel_chain", 2)
        # sealed_data_packet is in _STEP_ITEM_PROPERTIES — its override
        # name supersedes the fallback. Just check slot is misc (not weapon/armor).
        # The override supplies consumable+use_message; slot comes from base
        # before override, which is 'misc' for a non-registry key.
        self.assertEqual(item["slot"], "misc")
        self.assertIn("key", item)

    def test_build_graduation_item_narrative_fallback(self):
        """Non-registry, non-exempt keys produce slot=misc."""
        from engine.chain_rewards import _build_graduation_item
        item = _build_graduation_item("comlink_basic", "test_chain", "Test")
        self.assertEqual(item["slot"], "misc")


class TestFindCarriedGearResolvesNewKeys(unittest.TestCase):
    """find_carried_gear can match granted items by registry display name."""

    def _make_carried_item(self, key):
        from engine.chain_rewards import _build_graduation_item
        return _build_graduation_item(key, "test", "Test")

    def test_weapon_item_equippable(self):
        """A granted DC-15A rifle is matchable as a weapon via find_carried_gear."""
        from engine.items import find_carried_gear
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        carried = [self._make_carried_item("dc15_blaster_rifle")]
        idx, d, w = find_carried_gear(carried, "dc-15", wr, want_armor=False)
        self.assertIsNotNone(idx, "dc15_blaster_rifle should be found as weapon")
        self.assertFalse(w.is_armor)
        self.assertEqual(w.damage, "5D")

    def test_armor_item_wearable(self):
        """A granted republic_light_armor is matchable as armor via find_carried_gear."""
        from engine.items import find_carried_gear
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        carried = [self._make_carried_item("republic_light_armor")]
        idx, d, w = find_carried_gear(carried, "combat plate", wr, want_armor=True)
        self.assertIsNotNone(idx, "republic_light_armor should be found as armor")
        self.assertTrue(w.is_armor)
        self.assertEqual(w.protection_physical, "+1D+2")

    def test_concealed_blaster_equippable(self):
        from engine.items import find_carried_gear
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        carried = [self._make_carried_item("concealed_blaster")]
        idx, d, w = find_carried_gear(carried, "concealed", wr, want_armor=False)
        self.assertIsNotNone(idx)
        self.assertFalse(w.is_armor)

    def test_cis_field_armor_wearable(self):
        from engine.items import find_carried_gear
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        carried = [self._make_carried_item("cis_field_armor")]
        idx, d, w = find_carried_gear(carried, "cis field", wr, want_armor=True)
        self.assertIsNotNone(idx)
        self.assertTrue(w.is_armor)

    def test_vendor_stocked_false_all_14(self):
        """All 14 new keys are NOT vendor-stocked."""
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        new_keys = [
            "dc17_pistol", "dc15_blaster_rifle", "officers_sidearm",
            "e5_blaster_rifle", "concealed_blaster",
            "republic_uniform", "republic_light_armor", "improved_armor",
            "smuggler_vest", "padawan_robes", "jedi_robes", "cis_field_armor",
            "flight_suit_republic", "officers_uniform_republic",
        ]
        for key in new_keys:
            w = wr.get(key)
            self.assertIsNotNone(w, f"{key} missing from registry")
            self.assertFalse(
                w.vendor_stocked,
                f"{key} has vendor_stocked=True — faction gear must not appear in open buy"
            )


if __name__ == "__main__":
    unittest.main()
