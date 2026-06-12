"""
test_inventory_state.py — engine.items.build_inventory_state payload.

The inventory_state push (Webify UI-4a) assembles equipped + carried for the
web inventory modal: name / slot / value / stats resolve from the weapon
registry by key; condition / quality / crafter / experiment_count / quantity
come from the stored ItemInstance (equipped) or carried dict. No container /
weight (no encumbrance model at HEAD). A fake registry keeps this off the
weapons.yaml data file.
"""
from __future__ import annotations

import json
import unittest

from engine.items import ItemInstance, write_equipment, build_inventory_state
from engine.weapons import WeaponData


class _FakeRegistry:
    def __init__(self, mapping):
        self._m = mapping

    def get(self, key):
        return self._m.get(key)


def _registry():
    return _FakeRegistry({
        "blaster_pistol": WeaponData(
            key="blaster_pistol", name="Blaster Pistol", weapon_type="blaster",
            skill="blaster", damage="4D", cost=500, ranges=[3, 10, 30, 120]),
        "blaster_rifle": WeaponData(
            key="blaster_rifle", name="Blaster Rifle", weapon_type="blaster",
            skill="blaster", damage="5D", cost=1000, ranges=[3, 30, 100, 300]),
        "padded_armor": WeaponData(
            key="padded_armor", name="Padded Armor", weapon_type="armor",
            skill="", damage="", cost=250, protection_energy="1D",
            protection_physical="1D+1", dexterity_penalty="1D"),
    })


class TestBuildInventoryState(unittest.TestCase):
    def test_equipped_weapon_and_armor_resolved_from_registry(self):
        raw = write_equipment(
            weapon=ItemInstance(key="blaster_pistol", condition=80, quality=60,
                                crafter="Tey"),
            armor=ItemInstance(key="padded_armor", condition=100, quality=50))
        out = build_inventory_state(raw, [], registry=_registry())
        w = out["equipped"]["weapon"]
        self.assertEqual(w["name"], "Blaster Pistol")
        self.assertEqual(w["slot"], "weapon")
        self.assertEqual(w["value"], 500)           # WeaponData.cost
        self.assertEqual(w["condition"], 80)
        self.assertEqual(w["quality"], 60)
        self.assertEqual(w["crafter"], "Tey")
        self.assertEqual(w["stats"]["damage"], "4D")
        self.assertEqual(w["stats"]["range"], "10/30/120")   # short/med/long
        a = out["equipped"]["armor"]
        self.assertEqual(a["slot"], "armor")
        self.assertEqual(a["stats"]["energy"], "1D")
        self.assertEqual(a["stats"]["physical"], "1D+1")
        self.assertEqual(a["stats"]["dex_penalty"], "1D")
        self.assertNotIn("damage", a["stats"])      # armor has no damage axis

    def test_empty_slots_are_none(self):
        out = build_inventory_state("{}", [], registry=_registry())
        self.assertIsNone(out["equipped"]["weapon"])
        self.assertIsNone(out["equipped"]["armor"])
        self.assertEqual(out["carried"], [])

    def test_carried_items_resolved_and_quantity_preserved(self):
        carried = [
            {"key": "blaster_rifle", "quantity": 1, "condition": 90, "quality": 70,
             "crafter": "Mott", "experiment_count": 2},
            {"key": "padded_armor", "qty": 3},        # legacy 'qty'
        ]
        out = build_inventory_state("{}", carried, registry=_registry())
        self.assertEqual(len(out["carried"]), 2)
        rifle = out["carried"][0]
        self.assertEqual(rifle["name"], "Blaster Rifle")
        self.assertEqual(rifle["slot"], "weapon")
        self.assertEqual(rifle["value"], 1000)
        self.assertEqual(rifle["quantity"], 1)
        self.assertEqual(rifle["experiment_count"], 2)
        self.assertEqual(rifle["stats"]["damage"], "5D")
        armor = out["carried"][1]
        self.assertEqual(armor["quantity"], 3)        # qty → quantity

    def test_unknown_key_falls_back_to_dict_name_and_misc_slot(self):
        carried = [{"key": "quest_holocron", "name": "Cracked Holocron",
                    "quantity": 1, "value": 0}]
        out = build_inventory_state("{}", carried, registry=_registry())
        it = out["carried"][0]
        self.assertEqual(it["name"], "Cracked Holocron")  # dict name, no registry hit
        self.assertEqual(it["slot"], "misc")
        self.assertEqual(it["stats"], {})

    def test_no_container_field_emitted(self):
        out = build_inventory_state("{}", [], registry=_registry())
        self.assertNotIn("container", out)            # no encumbrance model

    def test_tolerant_of_legacy_equipment_shapes(self):
        # shape-1 flat key string still resolves through the registry
        out = build_inventory_state(json.dumps({"weapon": "blaster_pistol"}),
                                    [], registry=_registry())
        self.assertEqual(out["equipped"]["weapon"]["name"], "Blaster Pistol")


if __name__ == "__main__":
    unittest.main()
