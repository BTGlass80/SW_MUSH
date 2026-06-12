"""
test_equipment_untangle.py — canonical per-slot equipment helpers.

Pins read_equipment / equipment_keys / write_equipment (engine/items.py):
the tolerant reader must normalize ALL three historical on-disk shapes (and
empty/list/None) to {"weapon": ItemInstance|None, "armor": ItemInstance|None},
and write_equipment must round-trip through read_equipment preserving both
slots and instance condition/quality/crafter.

These functions are the foundation the inventory panel (UI-4a) reads through,
and the fix for the equip-clobbers-armor / unequip-wipes-armor / sheet-reads-
only-shape-2 bugs.
"""
from __future__ import annotations

import json
import unittest

from engine.items import (
    ItemInstance, read_equipment, equipment_keys, write_equipment,
)


class TestReadEquipmentToleratesAllShapes(unittest.TestCase):
    def test_shape3_per_slot_instance_canonical(self):
        raw = json.dumps({
            "weapon": {"key": "blaster_pistol", "condition": 80, "quality": 60,
                       "crafter": "Tey"},
            "armor": {"key": "padded_armor", "condition": 100, "quality": 50},
        })
        slots = read_equipment(raw)
        self.assertEqual(slots["weapon"].key, "blaster_pistol")
        self.assertEqual(slots["weapon"].condition, 80)
        self.assertEqual(slots["weapon"].quality, 60)
        self.assertEqual(slots["weapon"].crafter, "Tey")
        self.assertEqual(slots["armor"].key, "padded_armor")

    def test_shape1_flat_key_strings(self):
        raw = json.dumps({"weapon": "blaster_pistol", "armor": "padded_armor"})
        slots = read_equipment(raw)
        self.assertEqual(slots["weapon"].key, "blaster_pistol")
        self.assertEqual(slots["armor"].key, "padded_armor")
        # defaults applied
        self.assertEqual(slots["weapon"].condition, 100)
        self.assertEqual(slots["weapon"].quality, 50)
        self.assertIsNone(slots["weapon"].crafter)

    def test_shape2_top_level_single_instance_weapon_only(self):
        raw = json.dumps({"key": "vibroblade", "condition": 70, "quality": 55})
        slots = read_equipment(raw)
        self.assertEqual(slots["weapon"].key, "vibroblade")
        self.assertEqual(slots["weapon"].condition, 70)
        self.assertIsNone(slots["armor"])

    def test_empty_and_malformed_yield_two_none(self):
        for raw in ("{}", "", None, "[]", "not json", json.dumps([])):
            slots = read_equipment(raw)
            self.assertIsNone(slots["weapon"], f"weapon not None for {raw!r}")
            self.assertIsNone(slots["armor"], f"armor not None for {raw!r}")

    def test_accepts_already_parsed_dict(self):
        slots = read_equipment({"weapon": "hold_out_blaster"})
        self.assertEqual(slots["weapon"].key, "hold_out_blaster")
        self.assertIsNone(slots["armor"])


class TestEquipmentKeys(unittest.TestCase):
    def test_keys_from_each_shape(self):
        self.assertEqual(
            equipment_keys(json.dumps({"weapon": "a", "armor": "b"})),
            {"weapon": "a", "armor": "b"})
        self.assertEqual(
            equipment_keys(json.dumps({"key": "c"})),
            {"weapon": "c", "armor": ""})
        self.assertEqual(
            equipment_keys(json.dumps({"weapon": {"key": "d", "condition": 1}})),
            {"weapon": "d", "armor": ""})
        self.assertEqual(equipment_keys("{}"), {"weapon": "", "armor": ""})


class TestWriteEquipmentRoundTrip(unittest.TestCase):
    def test_write_then_read_preserves_both_slots_and_instance_data(self):
        w = ItemInstance(key="blaster_rifle", condition=90, max_condition=100,
                         quality=65, crafter="Mott")
        a = ItemInstance(key="combat_jumpsuit", condition=100, quality=50)
        raw = write_equipment(weapon=w, armor=a)
        slots = read_equipment(raw)
        self.assertEqual(slots["weapon"].key, "blaster_rifle")
        self.assertEqual(slots["weapon"].condition, 90)
        self.assertEqual(slots["weapon"].quality, 65)
        self.assertEqual(slots["weapon"].crafter, "Mott")
        self.assertEqual(slots["armor"].key, "combat_jumpsuit")

    def test_idempotent_canonical_roundtrip(self):
        w = ItemInstance(key="blaster_pistol", condition=80, quality=60)
        raw1 = write_equipment(weapon=w)
        raw2 = write_equipment(weapon=read_equipment(raw1)["weapon"])
        self.assertEqual(json.loads(raw1), json.loads(raw2))

    def test_both_empty_is_brace_brace(self):
        self.assertEqual(write_equipment(), "{}")
        self.assertEqual(read_equipment(write_equipment()),
                         {"weapon": None, "armor": None})

    def test_weapon_only_omits_armor_slot(self):
        raw = write_equipment(weapon=ItemInstance(key="bowcaster"))
        d = json.loads(raw)
        self.assertIn("weapon", d)
        self.assertNotIn("armor", d)

    def test_unequip_weapon_keeps_armor_pattern(self):
        # Simulate the unequip fix: read both, drop weapon, keep armor.
        stored = write_equipment(
            weapon=ItemInstance(key="blaster_pistol", condition=75),
            armor=ItemInstance(key="padded_armor", condition=88, quality=52),
        )
        slots = read_equipment(stored)
        after = write_equipment(weapon=None, armor=slots["armor"])
        re = read_equipment(after)
        self.assertIsNone(re["weapon"])
        self.assertEqual(re["armor"].key, "padded_armor")
        self.assertEqual(re["armor"].condition, 88)


class TestReloadRoundTrip(unittest.TestCase):
    """The reload invariant: Character.from_db_dict must recover the right
    equipped keys from ALL historical on-disk shapes. Shape 2 (top-level
    single instance) previously broke reload — equip.get('weapon') returned
    '' because there is no 'weapon' slot — silently dropping the equipped
    weapon. This guards that regression (folds toward T3.20 reload invariants)."""

    @staticmethod
    def _minimal(equipment_json: str) -> dict:
        return {
            "name": "T", "species": "Human", "template": "smuggler",
            "attributes": json.dumps({
                "dexterity": "3D", "knowledge": "2D", "mechanical": "2D",
                "perception": "3D", "strength": "2D", "technical": "2D"}),
            "skills": json.dumps({}), "wound_level": 0, "character_points": 5,
            "force_points": 1, "dark_side_points": 0, "credits": 100,
            "room_id": 1, "description": "", "equipment": equipment_json,
            "chargen_notes": "",
        }

    def _reload(self, equipment_json: str):
        from engine.character import Character
        c = Character.from_db_dict(self._minimal(equipment_json))
        return c.equipped_weapon, c.worn_armor

    def test_shape1_flat_reloads(self):
        self.assertEqual(
            self._reload(json.dumps({"weapon": "blaster_pistol",
                                     "armor": "padded_armor"})),
            ("blaster_pistol", "padded_armor"))

    def test_shape2_top_level_reloads_weapon(self):
        # The bug fix: weapon survives reload from the legacy weapon-only shape.
        self.assertEqual(
            self._reload(json.dumps({"key": "vibroblade", "condition": 70})),
            ("vibroblade", ""))

    def test_shape3_per_slot_reloads_both(self):
        self.assertEqual(
            self._reload(json.dumps({
                "weapon": {"key": "blaster_rifle", "condition": 90},
                "armor": {"key": "combat_jumpsuit", "condition": 100}})),
            ("blaster_rifle", "combat_jumpsuit"))

    def test_empty_reloads_blank(self):
        self.assertEqual(self._reload("{}"), ("", ""))


if __name__ == "__main__":
    unittest.main()