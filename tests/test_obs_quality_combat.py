"""
test_obs_quality_combat.py — Drop 19: crafted weapon quality + boosts reach combat.

OBS.quality_and_boosts_not_combat_read, Option B (Brian-ratified 2026-06-12).

Covers:
  - _quality_band_pips boundary values
  - crafted_combat_pips: quality bands, damage_mod boosts, accuracy_mod, edge cases
  - apply_damage_pips: carry/borrow, STR+ prefix, fail-open
  - Integration via _resolve_equipped_weapon: q95 crafted vs q50 vendor
  - Guard/isolation regressions: Drop F isolation pin; CombatAction field presence
"""
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class TestQualityBandPips(unittest.TestCase):
    def setUp(self):
        from engine.items import _quality_band_pips
        self.f = _quality_band_pips

    def test_boundary_49(self):
        self.assertEqual(self.f(49), -1)

    def test_boundary_50_vendor(self):
        self.assertEqual(self.f(50), 0)

    def test_boundary_69(self):
        self.assertEqual(self.f(69), 0)

    def test_boundary_70(self):
        self.assertEqual(self.f(70), 1)

    def test_boundary_89(self):
        self.assertEqual(self.f(89), 1)

    def test_boundary_90(self):
        self.assertEqual(self.f(90), 2)

    def test_boundary_100(self):
        self.assertEqual(self.f(100), 2)

    def test_shoddy_low(self):
        self.assertEqual(self.f(0), -1)

    def test_bad_input_none(self):
        self.assertEqual(self.f(None), 0)

    def test_bad_input_str(self):
        self.assertEqual(self.f("abc"), 0)


class TestCraftedCombatPips(unittest.TestCase):
    def setUp(self):
        from engine.items import ItemInstance, crafted_combat_pips
        self.f = crafted_combat_pips
        self.ItemInstance = ItemInstance

    def _inst(self, quality=50, damage_mod=0.0, accuracy_mod=0.0):
        inst = self.ItemInstance(key="blaster_pistol", quality=quality)
        if damage_mod:
            inst.effective_mods["damage_mod"] = damage_mod
            inst.experiment_count = 1
        if accuracy_mod:
            inst.effective_mods["accuracy_mod"] = accuracy_mod
            inst.experiment_count = max(inst.experiment_count, 1)
        return inst

    # --- Quality bands ---
    def test_q40_shoddy_minus1(self):
        dmg, acc = self.f(self._inst(quality=40))
        self.assertEqual(dmg, -1)
        self.assertEqual(acc, 0)

    def test_q50_vendor_zero(self):
        dmg, acc = self.f(self._inst(quality=50))
        self.assertEqual(dmg, 0)
        self.assertEqual(acc, 0)

    def test_q60_zero(self):
        dmg, acc = self.f(self._inst(quality=60))
        self.assertEqual(dmg, 0)
        self.assertEqual(acc, 0)

    def test_q75_plus1(self):
        dmg, acc = self.f(self._inst(quality=75))
        self.assertEqual(dmg, 1)
        self.assertEqual(acc, 0)

    def test_q95_plus2(self):
        dmg, acc = self.f(self._inst(quality=95))
        self.assertEqual(dmg, 2)
        self.assertEqual(acc, 0)

    # --- damage_mod boost ---
    def test_damage_mod_3p2_adds_1_boost_pip(self):
        # damage_mod=3.2 → 3.2//2.0=1 → boost_pips=1
        dmg, _ = self.f(self._inst(quality=50, damage_mod=3.2))
        self.assertEqual(dmg, 1)  # q50=0 + boost=1 = 1

    def test_damage_mod_zero_no_boost(self):
        dmg, _ = self.f(self._inst(quality=50, damage_mod=0.0))
        self.assertEqual(dmg, 0)

    def test_damage_mod_1p8_no_boost(self):
        # 1.8 // 2.0 = 0 → no boost
        dmg, _ = self.f(self._inst(quality=50, damage_mod=1.8))
        self.assertEqual(dmg, 0)

    def test_q95_plus_damage_mod_3p2_capped_at_3(self):
        # q95=+2, boost=1 → raw 3, cap is +3 → stays 3
        dmg, _ = self.f(self._inst(quality=95, damage_mod=3.2))
        self.assertEqual(dmg, 3)

    def test_q95_plus_damage_mod_10p0_still_capped_at_3(self):
        # boost capped at +1 pip per spec; combined cap +3
        dmg, _ = self.f(self._inst(quality=95, damage_mod=10.0))
        self.assertEqual(dmg, 3)

    # --- accuracy_mod ---
    def test_accuracy_mod_2p4_plus1(self):
        # 2.4 // 2.0 = 1
        _, acc = self.f(self._inst(quality=50, accuracy_mod=2.4))
        self.assertEqual(acc, 1)

    def test_accuracy_mod_1p8_zero(self):
        # 1.8 // 2.0 = 0
        _, acc = self.f(self._inst(quality=50, accuracy_mod=1.8))
        self.assertEqual(acc, 0)

    def test_accuracy_mod_large_capped_1(self):
        _, acc = self.f(self._inst(quality=50, accuracy_mod=8.0))
        self.assertEqual(acc, 1)

    # --- None / garbage ---
    def test_none_returns_zero_zero(self):
        self.assertEqual(self.f(None), (0, 0))

    def test_garbage_object_returns_zero_zero(self):
        self.assertEqual(self.f("garbage"), (0, 0))


class TestApplyDamagePips(unittest.TestCase):
    def setUp(self):
        from engine.items import apply_damage_pips
        self.f = apply_damage_pips

    def test_zero_pips_unchanged(self):
        self.assertEqual(self.f("4D", 0), "4D")

    def test_add_3_pips_carry_to_die(self):
        # 4D + 3 pips = 5D
        self.assertEqual(self.f("4D", 3), "5D")

    def test_add_2_pips_no_carry(self):
        # 4D+2 + 2 pips = 5D+1 (4 pips carry to 1D+1)
        self.assertEqual(self.f("4D+2", 2), "5D+1")

    def test_subtract_1_pip_borrow(self):
        # 4D - 1 pip = 3D+2
        self.assertEqual(self.f("4D", -1), "3D+2")

    def test_str_plus_2d_add_3(self):
        # STR+2D + 3 pips = STR+3D
        self.assertEqual(self.f("STR+2D", 3), "STR+3D")

    def test_str_plus_2d_add_1(self):
        # STR+2D + 1 pip = STR+2D+1
        self.assertEqual(self.f("STR+2D", 1), "STR+2D+1")

    def test_str_lowercase(self):
        # lowercase str+2D should also work
        self.assertEqual(self.f("str+2D", 3), "STR+3D")

    def test_malformed_fail_open(self):
        # unrecognised code returns unchanged
        self.assertEqual(self.f("xyz", 2), "xyz")

    def test_malformed_empty_parses_as_zero_die(self):
        # DicePool.parse("") returns DicePool(0,0); +1 pip → "0D+1" (not an error)
        self.assertEqual(self.f("", 1), "0D+1")


class TestResolveEquippedWeaponIntegration(unittest.TestCase):
    """Integration: _resolve_equipped_weapon returns boosted damage for crafted weapon."""

    def _make_char(self, equipment_json):
        return {
            "id": 99,
            "name": "TestChar",
            "equipment": equipment_json,
            "attributes": "{}",
            "skills": "{}",
            "inventory": '{"items": [], "resources": []}',
        }

    def _get_resolver(self):
        from parser.combat_commands import AttackCommand
        cmd = AttackCommand.__new__(AttackCommand)
        return cmd

    def test_q95_crafted_boosted_damage(self):
        """q95 crafted blaster_pistol: base 4D → +2 pips → 4D+2."""
        from engine.items import ItemInstance, write_equipment
        inst = ItemInstance.new_crafted("blaster_pistol", quality=95, crafter="Tey")
        eq_json = write_equipment(weapon=inst)
        char = self._make_char(eq_json)

        cmd = self._get_resolver()
        ew, skill, damage, accuracy_pips = cmd._resolve_equipped_weapon(char)

        self.assertEqual(damage, "4D+2")  # 4D base + 2 pips (q95 band)
        self.assertEqual(accuracy_pips, 0)  # no accuracy_mod on fresh crafted

    def test_q95_with_damage_mod_3p2(self):
        """q95 + damage_mod=3.2 → +2+1=3 pips → 5D."""
        from engine.items import ItemInstance, write_equipment
        inst = ItemInstance.new_crafted("blaster_pistol", quality=95, crafter="Tey")
        inst.add_experiment("damage", 3.2)
        eq_json = write_equipment(weapon=inst)
        char = self._make_char(eq_json)

        cmd = self._get_resolver()
        ew, skill, damage, accuracy_pips = cmd._resolve_equipped_weapon(char)

        self.assertEqual(damage, "5D")   # 4D + 3 pips = 5D

    def test_q95_with_accuracy_mod_2p4(self):
        """q95 + accuracy_mod=2.4 → accuracy_pips=1."""
        from engine.items import ItemInstance, write_equipment
        inst = ItemInstance.new_crafted("blaster_pistol", quality=95, crafter="Tey")
        inst.add_experiment("accuracy", 2.4)
        eq_json = write_equipment(weapon=inst)
        char = self._make_char(eq_json)

        cmd = self._get_resolver()
        ew, skill, damage, accuracy_pips = cmd._resolve_equipped_weapon(char)

        self.assertEqual(damage, "4D+2")   # q95 quality only for damage
        self.assertEqual(accuracy_pips, 1)

    def test_q50_vendor_unchanged(self):
        """Vendor q50 weapon: zero delta, exact registry base returned."""
        from engine.items import ItemInstance, write_equipment
        inst = ItemInstance(key="blaster_pistol", quality=50)
        eq_json = write_equipment(weapon=inst)
        char = self._make_char(eq_json)

        cmd = self._get_resolver()
        ew, skill, damage, accuracy_pips = cmd._resolve_equipped_weapon(char)

        self.assertEqual(damage, "4D")     # unchanged
        self.assertEqual(accuracy_pips, 0)

    def test_no_equipment_defaults(self):
        """No equipment → bare defaults, no crash."""
        char = self._make_char("{}")
        cmd = self._get_resolver()
        ew, skill, damage, accuracy_pips = cmd._resolve_equipped_weapon(char)

        self.assertIsNone(ew)
        self.assertEqual(skill, "blaster")
        self.assertEqual(damage, "4D")
        self.assertEqual(accuracy_pips, 0)


class TestGuardIsolationRegressions(unittest.TestCase):
    """Structural pins: Drop F isolation + CombatAction field presence."""

    def test_combat_py_does_not_call_perform_skill_check(self):
        """Drop F isolation must remain intact: combat.py never calls the skill-check chokepoint."""
        src = (REPO / "engine" / "combat.py").read_text(encoding="utf-8")
        self.assertNotIn("perform_skill_check", src)

    def test_combataction_has_accuracy_bonus_pips_field(self):
        from engine.combat import CombatAction, ActionType
        action = CombatAction(action_type=ActionType.ATTACK)
        self.assertTrue(hasattr(action, "accuracy_bonus_pips"))
        self.assertEqual(action.accuracy_bonus_pips, 0)

    def test_combataction_accuracy_bonus_pips_set(self):
        from engine.combat import CombatAction, ActionType
        action = CombatAction(action_type=ActionType.ATTACK, accuracy_bonus_pips=1)
        self.assertEqual(action.accuracy_bonus_pips, 1)

    def test_resolve_equipped_weapon_returns_4_tuple(self):
        """_resolve_equipped_weapon must return a 4-tuple now."""
        from parser.combat_commands import AttackCommand
        import inspect
        src = inspect.getsource(AttackCommand._resolve_equipped_weapon)
        self.assertIn("accuracy_pips", src)
        self.assertIn("return equipped_weapon, default_skill, default_damage, accuracy_pips", src)


if __name__ == "__main__":
    unittest.main()
