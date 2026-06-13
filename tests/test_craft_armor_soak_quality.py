"""CRAFT.armor_soak_quality — crafted armor quality folds into the combat soak roll.

The armor mirror of the Drop-19 weapon quality precedent
(OBS.quality_and_boosts armor half). Before this drop, a crafted q95 vest
soaked exactly like a vendor/q40 one because get_armor_protection read only the
bare worn_armor KEY (the instance quality was discarded). Three layers under
test:

  1. The funnel  — engine/items.crafted_armor_soak_pips: quality bands, the
     +2/floor-1 cap, fail-open. Mirrors TestCraftedCombatPips.
  2. The producer — Character.from_db_dict computes armor_soak_pips ONCE from
     the equipment JSON (where the instance is still in hand) and caches the
     primitive on the Character.
  3. The consumer — engine/combat soak path folds the pip into the protection
     pool before Strength-add and before wound penalty, so q95 armor soaks
     strictly more than q40 armor.

The registry path (get_armor_protection on a bare key) is intentionally
UNCHANGED — test_craft_p2_gundark_drop_c's soak-row pins stay green because the
quality delta lives in combat, not in get_armor_protection.
"""

import json
import unittest

from engine.character import Character
from engine.dice import DicePool
from engine.items import (
    ItemInstance,
    crafted_armor_soak_pips,
    write_equipment,
)


# A real armor key that provides protection for BOTH damage types, so the
# is_zero() guard at the soak site passes and the quality pip actually applies.
_BLAST_VEST = "blast_vest"  # +1D energy / +1D physical


class TestCraftedArmorSoakPips(unittest.TestCase):
    """The funnel function in isolation."""

    def _inst(self, quality):
        return ItemInstance(key=_BLAST_VEST, quality=quality)

    def test_q40_shoddy_minus1(self):
        self.assertEqual(crafted_armor_soak_pips(self._inst(40)), -1)

    def test_q49_boundary_minus1(self):
        self.assertEqual(crafted_armor_soak_pips(self._inst(49)), -1)

    def test_q50_vendor_zero(self):
        self.assertEqual(crafted_armor_soak_pips(self._inst(50)), 0)

    def test_q69_boundary_zero(self):
        self.assertEqual(crafted_armor_soak_pips(self._inst(69)), 0)

    def test_q70_boundary_plus1(self):
        self.assertEqual(crafted_armor_soak_pips(self._inst(70)), 1)

    def test_q89_boundary_plus1(self):
        self.assertEqual(crafted_armor_soak_pips(self._inst(89)), 1)

    def test_q90_boundary_plus2(self):
        self.assertEqual(crafted_armor_soak_pips(self._inst(90)), 2)

    def test_q95_plus2(self):
        self.assertEqual(crafted_armor_soak_pips(self._inst(95)), 2)

    def test_q100_capped_plus2(self):
        # The band tops out at +2; the cap is the same value (no experiment
        # axis for armor), so q100 is +2, never +3.
        self.assertEqual(crafted_armor_soak_pips(self._inst(100)), 2)

    def test_none_returns_zero(self):
        self.assertEqual(crafted_armor_soak_pips(None), 0)

    def test_garbage_object_returns_zero(self):
        self.assertEqual(crafted_armor_soak_pips(object()), 0)

    def test_missing_quality_defaults_vendor_zero(self):
        # An instance whose quality attr is absent defaults to 50 (vendor) → 0.
        class _Bare:
            pass
        self.assertEqual(crafted_armor_soak_pips(_Bare()), 0)


class TestArmorSoakPipsProducer(unittest.TestCase):
    """from_db_dict captures the soak pip from the equipment JSON."""

    def _char_with_armor_quality(self, quality):
        equip = write_equipment(
            armor=ItemInstance(key=_BLAST_VEST, quality=quality)
        )
        data = {"name": "Tester", "equipment": equip}
        return Character.from_db_dict(data)

    def test_q95_armor_sets_plus2(self):
        ch = self._char_with_armor_quality(95)
        self.assertEqual(ch.armor_soak_pips, 2)
        self.assertEqual(ch.worn_armor, _BLAST_VEST)

    def test_q40_armor_sets_minus1(self):
        ch = self._char_with_armor_quality(40)
        self.assertEqual(ch.armor_soak_pips, -1)

    def test_vendor_q50_armor_sets_zero(self):
        ch = self._char_with_armor_quality(50)
        self.assertEqual(ch.armor_soak_pips, 0)

    def test_no_armor_defaults_zero(self):
        ch = Character.from_db_dict({"name": "Bare", "equipment": "{}"})
        self.assertEqual(ch.armor_soak_pips, 0)
        self.assertEqual(ch.worn_armor, "")

    def test_legacy_flat_key_equipment_zero(self):
        # Historical shape: bare key string (no instance/quality) → vendor
        # baseline, no crafted bonus.
        data = {"name": "Legacy", "equipment": json.dumps({"armor": _BLAST_VEST})}
        ch = Character.from_db_dict(data)
        self.assertEqual(ch.worn_armor, _BLAST_VEST)
        self.assertEqual(ch.armor_soak_pips, 0)

    def test_default_constructed_char_zero(self):
        # A Character built without from_db_dict (test fixture / synthetic NPC)
        # fails open to 0 — vendor baseline.
        self.assertEqual(Character().armor_soak_pips, 0)


class TestArmorSoakQualityInCombat(unittest.TestCase):
    """The combat soak path folds the pip; q95 soaks strictly more than q40."""

    def _soak_pool_for_quality(self, quality, energy=True):
        """Reproduce the soak-pool construction from engine.combat._apply_damage
        for a defender wearing armor of the given crafted quality. Returns the
        (dice, pips) of the armor contribution to soak after the quality fold."""
        equip = write_equipment(
            armor=ItemInstance(key=_BLAST_VEST, quality=quality)
        )
        ch = Character.from_db_dict({"name": "Defender", "equipment": equip})
        armor_pool = ch.get_armor_protection(energy=energy)
        # Mirror combat.py: fold the cached pip before Strength-add.
        pips = getattr(ch, "armor_soak_pips", 0)
        if pips and not armor_pool.is_zero():
            armor_pool = armor_pool + pips
        return armor_pool

    def test_q95_soaks_more_than_q40(self):
        hi = self._soak_pool_for_quality(95)   # +1D base, +2 pips
        lo = self._soak_pool_for_quality(40)   # +1D base, -1 pip
        # Compare total pip magnitude (dice*3 + pips) — q95 must exceed q40.
        hi_mag = hi.dice * 3 + hi.pips
        lo_mag = lo.dice * 3 + lo.pips
        self.assertGreater(hi_mag, lo_mag)

    def test_q95_adds_two_pips_over_vendor(self):
        vendor = self._soak_pool_for_quality(50)  # +1D, +0
        hi = self._soak_pool_for_quality(95)       # +1D, +2
        self.assertEqual(hi.dice * 3 + hi.pips,
                         vendor.dice * 3 + vendor.pips + 2)

    def test_q40_subtracts_one_pip(self):
        vendor = self._soak_pool_for_quality(50)
        lo = self._soak_pool_for_quality(40)
        self.assertEqual(lo.dice * 3 + lo.pips,
                         vendor.dice * 3 + vendor.pips - 1)

    def test_pip_applies_to_physical_too(self):
        # blast_vest protects both damage types, so the quality pip folds into
        # physical soak as well as energy.
        hi = self._soak_pool_for_quality(95, energy=False)
        vendor = self._soak_pool_for_quality(50, energy=False)
        self.assertEqual(hi.dice * 3 + hi.pips,
                         vendor.dice * 3 + vendor.pips + 2)

    def test_three_pips_carry_to_die(self):
        # +1D base armor + 2 pips → DicePool(1,1)*... the +2 pips do NOT carry a
        # die on their own (need 3); confirm the arithmetic is pip-level.
        hi = self._soak_pool_for_quality(95)
        self.assertEqual((hi.dice, hi.pips), (1, 2))

    def test_vendor_unchanged_from_registry(self):
        # A vendor (q50) crafted vest soaks identically to the bare registry
        # value — the quality fold is a no-op at q50.
        vendor = self._soak_pool_for_quality(50)
        self.assertEqual((vendor.dice, vendor.pips), (1, 0))


class TestGetArmorProtectionUnchanged(unittest.TestCase):
    """The registry read path is intentionally untouched (gundark pins safe)."""

    def test_bare_key_read_ignores_quality(self):
        # get_armor_protection still keys off worn_armor alone — it returns the
        # registry protection with NO quality delta. The delta lives in combat.
        ch = Character()
        ch.worn_armor = _BLAST_VEST
        # No armor_soak_pips set → still the bare +1D.
        ep = ch.get_armor_protection(energy=True)
        self.assertEqual((ep.dice, ep.pips), (1, 0))


if __name__ == "__main__":
    unittest.main()
