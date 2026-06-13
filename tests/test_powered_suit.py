# -*- coding: utf-8 -*-
"""tests/test_powered_suit.py — CRAFT.powered_suit_design (2026-06-13).

The first POWERED exo-armor: a servo-assisted Strength bonus folded into the
combat soak roll, HARD-CAPPED +1D and HALVED for a wearer without the new
Powersuit Operation skill. Design: docs/design (logged in TODO under
CRAFT.powered_suit_design); Brian ruled "register a new powersuit skill."

Covers:
  1. The Powersuit Operation skill registers (Mechanical attribute).
  2. The exo-frame item loads with strength_bonus + powersuit_skill.
  3. get_powersuit_strength_bonus: trained full / untrained half / capped /
     ordinary-armor zero / no-armor zero.
  4. The combat soak path folds the bonus (trained soaks more than untrained,
     who soaks more than an ordinary-armor wearer of similar protection).
  5. The schematic is craftable (Armor Repair / Sela Tarn) with canonical
     components.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.character import Character, SkillRegistry
from engine.dice import DicePool
from engine.weapons import get_weapon_registry

_EXO = "labor_exo_frame_pl9"


class TestPowersuitSkillRegistered(unittest.TestCase):

    def test_skill_registers_under_mechanical(self):
        r = SkillRegistry()
        r.load_file(str(PROJECT_ROOT / "data" / "skills.yaml"))
        sd = r.get("powersuit operation")
        self.assertIsNotNone(sd)
        self.assertEqual(sd.attribute, "mechanical")

    def test_skill_resolves_underscore_form(self):
        r = SkillRegistry()
        r.load_file(str(PROJECT_ROOT / "data" / "skills.yaml"))
        self.assertIsNotNone(r.get("powersuit_operation"))


class TestExoFrameItem(unittest.TestCase):

    def test_item_loads_with_powered_fields(self):
        a = get_weapon_registry().get(_EXO)
        self.assertIsNotNone(a)
        self.assertTrue(a.is_armor)
        self.assertEqual(a.strength_bonus, "+1D")
        self.assertTrue(a.powersuit_skill)
        # Still a normal armor row otherwise.
        self.assertTrue(a.protection_energy)
        self.assertTrue(a.protection_physical)

    def test_ordinary_armor_has_no_strength_bonus(self):
        a = get_weapon_registry().get("blast_vest")
        self.assertEqual(a.strength_bonus, "")
        self.assertFalse(a.powersuit_skill)


class TestPowersuitStrengthBonus(unittest.TestCase):

    def _wearer(self, armor=_EXO, ps_skill=None):
        ch = Character()
        ch.worn_armor = armor
        if ps_skill:
            ch.skills["powersuit operation"] = DicePool.parse(ps_skill)
        return ch

    def test_trained_gets_full_capped_bonus(self):
        b = self._wearer(ps_skill="2D").get_powersuit_strength_bonus()
        self.assertEqual((b.dice, b.pips), (1, 0))  # +1D

    def test_untrained_gets_half(self):
        b = self._wearer().get_powersuit_strength_bonus()
        self.assertEqual((b.dice, b.pips), (0, 1))  # half of 3 pips, floor

    def test_ordinary_armor_zero(self):
        b = self._wearer(armor="blast_vest", ps_skill="2D").get_powersuit_strength_bonus()
        self.assertTrue(b.is_zero())

    def test_no_armor_zero(self):
        b = Character().get_powersuit_strength_bonus()
        self.assertTrue(b.is_zero())

    def test_zero_dice_skill_is_untrained(self):
        # A 0D skill entry must count as UNTRAINED (DicePool has no __bool__, so
        # a naive truthiness check would wrongly treat 0D as trained).
        b = self._wearer(ps_skill="0D").get_powersuit_strength_bonus()
        self.assertEqual((b.dice, b.pips), (0, 1))  # half, like no skill at all

    def test_underscore_form_skill_counts_as_trained(self):
        # An NPC sheet storing the skill underscore-form must still count.
        ch = Character()
        ch.worn_armor = _EXO
        ch.skills["powersuit_operation"] = DicePool.parse("2D")
        b = ch.get_powersuit_strength_bonus()
        self.assertEqual((b.dice, b.pips), (1, 0))  # full +1D

    def test_non_powered_armor_with_str_bonus_ignored(self):
        # An armor row that has a strength_bonus but is NOT flagged powersuit_skill
        # grants NO bonus (the flag is the gate; guards against a stray field).
        wr = get_weapon_registry()
        a = wr.get("blast_vest")
        orig_b, orig_f = a.strength_bonus, a.powersuit_skill
        try:
            a.strength_bonus = "+1D"
            a.powersuit_skill = False
            b = self._wearer(armor="blast_vest", ps_skill="2D").get_powersuit_strength_bonus()
            self.assertTrue(b.is_zero())  # no flag → no bonus
        finally:
            a.strength_bonus, a.powersuit_skill = orig_b, orig_f

    def test_cap_holds_against_inflated_bonus(self):
        # A hypothetical suit declaring +5D must still cap at +1D for a trained
        # wearer (no power creep). Patch the registry entry's bonus in-memory.
        wr = get_weapon_registry()
        a = wr.get(_EXO)
        orig = a.strength_bonus
        try:
            a.strength_bonus = "+5D"
            b = self._wearer(ps_skill="3D").get_powersuit_strength_bonus()
            self.assertEqual((b.dice, b.pips), (1, 0))  # still capped +1D
        finally:
            a.strength_bonus = orig


class TestCombatSoakIntegration(unittest.TestCase):
    """The bonus folds into the soak roll — trained > untrained > unpowered."""

    def _soak_pool(self, armor=_EXO, ps_skill=None, str_code="3D"):
        # Reproduce the combat soak-pool construction (engine/combat _apply_damage)
        # for the strength + powersuit-bonus portion (excluding the random roll).
        ch = Character()
        ch.set_attribute("strength", DicePool.parse(str_code))
        ch.worn_armor = armor
        if ps_skill:
            ch.skills["powersuit operation"] = DicePool.parse(ps_skill)
        soak = ch.get_attribute("strength")
        bonus = ch.get_powersuit_strength_bonus()
        if not bonus.is_zero():
            soak = soak + bonus
        return soak

    def _mag(self, pool):
        return pool.dice * 3 + pool.pips

    def test_trained_soaks_more_than_untrained(self):
        trained = self._soak_pool(ps_skill="2D")
        untrained = self._soak_pool()
        self.assertGreater(self._mag(trained), self._mag(untrained))

    def test_untrained_still_soaks_more_than_unpowered(self):
        untrained = self._soak_pool()              # +1 pip from the suit
        unpowered = self._soak_pool(armor="blast_vest")
        self.assertGreater(self._mag(untrained), self._mag(unpowered))

    def test_trained_bonus_is_exactly_one_die_over_base(self):
        base = self._soak_pool(armor="blast_vest")   # strength only (blast_vest str_bonus="")
        trained = self._soak_pool(ps_skill="2D")
        self.assertEqual(self._mag(trained) - self._mag(base), 3)  # +1D = 3 pips


class TestExoSchematic(unittest.TestCase):

    def test_schematic_is_craftable(self):
        import yaml
        schems = yaml.safe_load(
            (PROJECT_ROOT / "data" / "schematics.yaml").read_text(encoding="utf-8")
        )["schematics"]
        ex = [s for s in schems if s.get("output_key") == _EXO]
        self.assertEqual(len(ex), 1)
        s = ex[0]
        self.assertEqual(s["skill_required"], "armor_repair")
        self.assertEqual(s["output_type"], "armor")
        self.assertTrue(s.get("trainer_npc"))
        # Components canonical.
        from engine.crafting import RESOURCE_TYPES
        for c in s["components"]:
            self.assertIn(c["type"], RESOURCE_TYPES)


class TestSkillLoadRobustness(unittest.TestCase):
    """Hardening from the drop-44-50 adversarial sweep (2026-06-13)."""

    def test_has_skill_dice_tolerates_non_dicepool(self):
        # A non-DicePool value in skills must read as untrained, not crash
        # (has_skill_dice has no live unguarded caller, but it's a footgun).
        ch = Character()
        ch.skills["powersuit operation"] = "2D"   # junk string, not DicePool
        self.assertFalse(ch.has_skill_dice("powersuit operation"))
        ch.skills["powersuit operation"] = DicePool.parse("2D")
        self.assertTrue(ch.has_skill_dice("powersuit operation"))

    def test_from_db_dict_skips_unparseable_skill(self):
        # A corrupted skills column (a non-D6 string) must NOT abort the whole
        # character load + leak a raw Python error to the player.
        import json
        data = {
            "id": 1, "name": "T",
            "attributes": json.dumps({"strength": "3D"}),
            "skills": json.dumps({"blaster": "TRAINED", "sneak": "2D"}),
            "equipment": "{}", "wound_level": 0,
        }
        ch = Character.from_db_dict(data)          # must not raise
        self.assertNotIn("blaster", ch.skills)     # bad entry skipped
        self.assertIn("sneak", ch.skills)          # good entry kept


if __name__ == "__main__":
    unittest.main()
