"""TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES — Stage 1.

The Character object stores equipped_weapon/worn_armor as bare KEY strings, but
the canonical DB column is per-slot ItemInstance JSON. Stage 1 ADDITIVELY caches
the parsed instances (from the read_equipment call from_db_dict already makes)
and exposes them via two read-only properties — WITHOUT changing the bare-key
fields (the 56 key-only consumers are untouched). It also fixes the two live
consumer bugs the seam map found:

  1. server/session._build_loadout — read name/damage/type keys that
     ItemInstance.to_dict() never emits → the web HUD loadout was always blank.
  2. engine/espionage.generate_scan_result — read equipped_weapon/worn_armor off
     the char DICT (those are Character ATTRIBUTES, never dict columns) → intel
     scans always reported "Unarmed" / no armor.

Sections:
  1. TestAccessor            — the new instance properties
  2. TestAccessorSafety      — None defaults, default-ctor, legacy shapes
  3. TestBuildLoadoutFix     — web loadout now shows real name + condition/quality
  4. TestEspionageScanFix    — intel scan now reports the real loadout
  5. TestBareKeysUntouched   — the additive contract: keys still work
"""
import json
import unittest

from engine.character import Character
from engine.items import ItemInstance, write_equipment


def _char_with_equipment(weapon=None, armor=None):
    equip = write_equipment(weapon=weapon, armor=armor)
    return Character.from_db_dict({"name": "Tester", "equipment": equip})


class TestAccessor(unittest.TestCase):

    def test_weapon_inst_carries_full_state(self):
        ch = _char_with_equipment(
            weapon=ItemInstance(key="blaster_pistol", quality=88,
                                condition=70, crafter="Jax"))
        wi = ch.equipped_weapon_inst
        self.assertIsNotNone(wi)
        self.assertEqual(wi.key, "blaster_pistol")
        self.assertEqual(wi.quality, 88)
        self.assertEqual(wi.condition, 70)
        self.assertEqual(wi.crafter, "Jax")

    def test_armor_inst_carries_quality(self):
        ch = _char_with_equipment(
            armor=ItemInstance(key="blast_vest", quality=95))
        ai = ch.worn_armor_inst
        self.assertIsNotNone(ai)
        self.assertEqual(ai.key, "blast_vest")
        self.assertEqual(ai.quality, 95)

    def test_returns_iteminstance_type(self):
        ch = _char_with_equipment(weapon=ItemInstance(key="blaster_pistol"))
        self.assertIsInstance(ch.equipped_weapon_inst, ItemInstance)


class TestAccessorSafety(unittest.TestCase):

    def test_empty_slots_return_none(self):
        ch = Character.from_db_dict({"name": "Bare", "equipment": "{}"})
        self.assertIsNone(ch.equipped_weapon_inst)
        self.assertIsNone(ch.worn_armor_inst)

    def test_default_constructed_char_no_attributeerror(self):
        # A Character built WITHOUT from_db_dict (test fixture / from_npc_sheet)
        # must not AttributeError — the field default covers it.
        ch = Character()
        self.assertIsNone(ch.equipped_weapon_inst)
        self.assertIsNone(ch.worn_armor_inst)

    def test_legacy_flat_key_shape(self):
        # Historical shape: bare key string (no instance) → an ItemInstance with
        # default condition/quality, key preserved.
        data = {"name": "Legacy",
                "equipment": json.dumps({"weapon": "blaster_pistol"})}
        ch = Character.from_db_dict(data)
        wi = ch.equipped_weapon_inst
        self.assertIsNotNone(wi)
        self.assertEqual(wi.key, "blaster_pistol")
        self.assertEqual(wi.quality, 50)  # default vendor

    def test_only_weapon_equipped(self):
        ch = _char_with_equipment(weapon=ItemInstance(key="blaster_pistol"))
        self.assertIsNotNone(ch.equipped_weapon_inst)
        self.assertIsNone(ch.worn_armor_inst)

    def test_from_npc_sheet_populates_weapon_inst(self):
        # An armed sheet-NPC's accessor returns a (vendor) instance, not None,
        # so a Stage-2 NPC consumer doesn't silently get None.
        ch = Character.from_npc_sheet(1, {"name": "Thug", "weapon": "vibroblade"})
        self.assertEqual(ch.equipped_weapon, "vibroblade")
        self.assertIsNotNone(ch.equipped_weapon_inst)
        self.assertEqual(ch.equipped_weapon_inst.key, "vibroblade")
        self.assertIsNone(ch.worn_armor_inst)

    def test_from_npc_sheet_unarmed_returns_none(self):
        ch = Character.from_npc_sheet(1, {"name": "Pacifist"})
        self.assertIsNone(ch.equipped_weapon_inst)


class TestBuildLoadoutFix(unittest.TestCase):
    """The web HUD loadout sidebar now shows real data (was always blank)."""

    def _loadout(self, weapon=None, armor=None):
        from server.session import _build_loadout
        equip = write_equipment(weapon=weapon, armor=armor)
        return _build_loadout({"equipment": equip})

    def test_weapon_name_resolved_from_registry(self):
        lo = self._loadout(
            weapon=ItemInstance(key="blaster_pistol", quality=90,
                                condition=80, crafter="Mara"))
        self.assertIsNotNone(lo["weapon"])
        # name comes from the registry (NOT blank — the old bug read it off the
        # instance JSON where it never existed).
        self.assertTrue(lo["weapon"]["name"])
        self.assertNotEqual(lo["weapon"]["name"], "")

    def test_armor_name_resolved_from_registry(self):
        lo = self._loadout(armor=ItemInstance(key="blast_vest", quality=95))
        self.assertIsNotNone(lo["armor"])
        self.assertTrue(lo["armor"]["name"])

    def test_no_equipment_empty_loadout(self):
        lo = self._loadout()
        self.assertIsNone(lo["weapon"])
        self.assertIsNone(lo["armor"])

    def test_unknown_key_falls_back_to_titleized_key(self):
        # A key the registry doesn't know still yields a non-blank name.
        lo = self._loadout(weapon=ItemInstance(key="mystery_blaster_xyz"))
        self.assertEqual(lo["weapon"]["name"], "Mystery Blaster Xyz")


class TestEspionageScanFix(unittest.TestCase):
    """Intel scans now report the real loadout (were always 'Unarmed')."""

    def _scan(self, margin, weapon=None, armor=None):
        from engine.espionage import generate_scan_result
        equip = write_equipment(weapon=weapon, armor=armor)
        target = {"name": "Mark", "equipment": equip, "wound_level": 0}
        return "\n".join(generate_scan_result({}, target, margin))

    def test_armed_line_reports_weapon(self):
        out = self._scan(0, weapon=ItemInstance(key="blaster_pistol"))
        self.assertIn("Blaster Pistol", out)
        self.assertNotIn("Unarmed", out)

    def test_unarmed_when_no_weapon(self):
        out = self._scan(0)
        self.assertIn("Unarmed", out)

    def test_armor_line_at_margin_5(self):
        out = self._scan(5, armor=ItemInstance(key="blast_vest"))
        self.assertIn("Blast Vest", out)

    def test_no_armor_line_when_unarmored(self):
        out = self._scan(5)
        # The "Armor:" label only appears when armor is worn.
        self.assertNotIn("Armor:", out)


class TestBareKeysUntouched(unittest.TestCase):
    """The additive contract: the bare-key fields still work as before."""

    def test_bare_keys_still_strings(self):
        ch = _char_with_equipment(
            weapon=ItemInstance(key="blaster_pistol", quality=88),
            armor=ItemInstance(key="blast_vest", quality=95))
        self.assertEqual(ch.equipped_weapon, "blaster_pistol")
        self.assertEqual(ch.worn_armor, "blast_vest")
        self.assertIsInstance(ch.equipped_weapon, str)
        self.assertIsInstance(ch.worn_armor, str)

    def test_armor_soak_pips_still_computed(self):
        # Drop 44's armor_soak_pips must still work alongside the new accessor.
        ch = _char_with_equipment(
            armor=ItemInstance(key="blast_vest", quality=95))
        self.assertEqual(ch.armor_soak_pips, 2)  # q95 → +2


if __name__ == "__main__":
    unittest.main()
