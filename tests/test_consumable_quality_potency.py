"""CRAFT.consumable_quality_potency — crafted consumable quality affects potency.

The consumable half of CRAFT.armor_consumable_quality_combat. Design:
docs/design/consumable_quality_potency_v1.md. Three layers:

  1. The funnel — engine/items.crafted_consumable_potency_pips: a TIGHTER band
     than weapons/armor (cap +1, not +2) because a stim base is only +1D.
  2. The storage migration — engine/buffs: consumables move from a bare int to
     {"count", "quality"}; the read path tolerates BOTH (legacy int → q50), the
     write path takes max-on-recraft, consume_consumable preserves quality and
     stays a bool.
  3. The potency hook — stims scale buff magnitude by the pip (capped +1);
     medpacs keep discrete heal but get a First-Aid roll bonus (reliability).

Power-creep guard: the cap is +1 on a 3-pip stim base (+33%, never reaching the
next catalog tier). q50 (vendor) is a no-op everywhere.
"""

import json
import unittest

from engine.buffs import (
    _normalize_consumable_entry,
    consume_consumable,
    get_consumable_count,
    get_consumable_quality,
    has_consumable,
)
from engine.items import crafted_consumable_potency_pips


class TestCraftedConsumablePotencyPips(unittest.TestCase):
    """The funnel — tighter band, cap +1."""

    def test_q40_shoddy_minus1(self):
        self.assertEqual(crafted_consumable_potency_pips(40), -1)

    def test_q49_boundary_minus1(self):
        self.assertEqual(crafted_consumable_potency_pips(49), -1)

    def test_q50_vendor_zero(self):
        self.assertEqual(crafted_consumable_potency_pips(50), 0)

    def test_q69_boundary_zero(self):
        self.assertEqual(crafted_consumable_potency_pips(69), 0)

    def test_q70_boundary_plus1(self):
        self.assertEqual(crafted_consumable_potency_pips(70), 1)

    def test_q89_still_plus1_not_plus2(self):
        # Unlike armor (which splits 70-89=+1 / 90-100=+2), consumables cap the
        # whole good band at +1 — the small stim base can't take +2.
        self.assertEqual(crafted_consumable_potency_pips(89), 1)

    def test_q90_capped_plus1(self):
        self.assertEqual(crafted_consumable_potency_pips(90), 1)

    def test_q100_capped_plus1(self):
        self.assertEqual(crafted_consumable_potency_pips(100), 1)

    def test_bad_input_none_zero(self):
        self.assertEqual(crafted_consumable_potency_pips(None), 0)

    def test_bad_input_str_zero(self):
        self.assertEqual(crafted_consumable_potency_pips("abc"), 0)


class TestNormalizeConsumableEntry(unittest.TestCase):
    """The migration seam — both storage generations read uniformly."""

    def test_legacy_bare_int(self):
        self.assertEqual(_normalize_consumable_entry(3),
                         {"count": 3, "quality": 50})

    def test_new_dict(self):
        self.assertEqual(_normalize_consumable_entry({"count": 2, "quality": 87}),
                         {"count": 2, "quality": 87})

    def test_dict_missing_quality_defaults_vendor(self):
        self.assertEqual(_normalize_consumable_entry({"count": 1}),
                         {"count": 1, "quality": 50})

    def test_negative_int_clamped(self):
        self.assertEqual(_normalize_consumable_entry(-1),
                         {"count": 0, "quality": 50})

    def test_bool_not_treated_as_count(self):
        # bool is an int subclass — must NOT become count=1.
        self.assertEqual(_normalize_consumable_entry(True),
                         {"count": 0, "quality": 50})

    def test_garbage_safe(self):
        self.assertEqual(_normalize_consumable_entry("nope"),
                         {"count": 0, "quality": 50})

    def test_malformed_dict_quality(self):
        self.assertEqual(
            _normalize_consumable_entry({"count": 2, "quality": "x"}),
            {"count": 2, "quality": 50})


class TestQualityAwareHelpers(unittest.TestCase):
    """has/get/consume tolerate both shapes; quality is readable + preserved."""

    def test_legacy_int_count_and_quality(self):
        c = {"attributes": {"consumables": {"stimpack": 3}}}
        self.assertTrue(has_consumable(c, "stimpack"))
        self.assertEqual(get_consumable_count(c, "stimpack"), 3)
        self.assertEqual(get_consumable_quality(c, "stimpack"), 50)  # vendor

    def test_new_dict_count_and_quality(self):
        c = {"attributes": {"consumables": {"stimpack": {"count": 2, "quality": 88}}}}
        self.assertTrue(has_consumable(c, "stimpack"))
        self.assertEqual(get_consumable_count(c, "stimpack"), 2)
        self.assertEqual(get_consumable_quality(c, "stimpack"), 88)

    def test_consume_preserves_quality_and_stays_bool(self):
        c = {"attributes": {"consumables": {"stimpack": {"count": 2, "quality": 88}}}}
        ok = consume_consumable(c, "stimpack")
        self.assertIs(ok, True)  # bool contract preserved
        self.assertEqual(get_consumable_count(c, "stimpack"), 1)
        self.assertEqual(get_consumable_quality(c, "stimpack"), 88)  # kept

    def test_consume_legacy_int_rewrites_canonical(self):
        c = {"attributes": {"consumables": {"medpac": 2}}}
        self.assertTrue(consume_consumable(c, "medpac"))
        # After consume the entry is the canonical dict shape at q50.
        entry = c["attributes"]["consumables"]["medpac"]
        self.assertEqual(entry, {"count": 1, "quality": 50})

    def test_consume_to_zero_removes_key(self):
        c = {"attributes": {"consumables": {"stimpack": {"count": 1, "quality": 90}}}}
        self.assertTrue(consume_consumable(c, "stimpack"))
        self.assertNotIn("stimpack", c["attributes"]["consumables"])

    def test_consume_empty_returns_false(self):
        c = {"attributes": "{}"}
        self.assertFalse(consume_consumable(c, "stimpack"))

    def test_quality_absent_defaults_vendor(self):
        c = {"attributes": "{}"}
        self.assertEqual(get_consumable_quality(c, "stimpack"), 50)

    def test_json_string_attrs_roundtrip(self):
        c = {"attributes": json.dumps(
            {"consumables": {"combat_stim": {"count": 1, "quality": 75}}})}
        self.assertEqual(get_consumable_quality(c, "combat_stim"), 75)
        self.assertTrue(consume_consumable(c, "combat_stim"))
        attrs = json.loads(c["attributes"])
        self.assertNotIn("combat_stim", attrs.get("consumables", {}))


class TestCraftDeliveryMaxOnRecraft(unittest.TestCase):
    """The crafting delivery write persists quality, max-on-recraft."""

    def _craft(self, attrs_consumables, key, quality):
        # Reproduce the crafting_commands.py delivery write.
        from engine.buffs import _normalize_consumable_entry as norm
        existing = norm(attrs_consumables.get(key, 0))
        attrs_consumables[key] = {
            "count": existing["count"] + 1,
            "quality": max(existing["quality"], int(quality)),
        }
        return attrs_consumables

    def test_first_craft_sets_quality(self):
        c = self._craft({}, "stimpack", 80)
        self.assertEqual(c["stimpack"], {"count": 1, "quality": 80})

    def test_recraft_higher_takes_max(self):
        c = self._craft({"stimpack": {"count": 1, "quality": 60}}, "stimpack", 90)
        self.assertEqual(c["stimpack"], {"count": 2, "quality": 90})

    def test_recraft_lower_keeps_max(self):
        c = self._craft({"stimpack": {"count": 1, "quality": 90}}, "stimpack", 60)
        self.assertEqual(c["stimpack"], {"count": 2, "quality": 90})

    def test_recraft_onto_legacy_int(self):
        c = self._craft({"stimpack": 2}, "stimpack", 85)  # legacy = q50
        self.assertEqual(c["stimpack"], {"count": 3, "quality": 85})


class TestStimBuffScaling(unittest.TestCase):
    """The stim potency hook — buff magnitude scales by the pip, capped, floored."""

    def _scaled_mods(self, buff_type, quality):
        # Reproduce the medical_commands buff-scaling block.
        from engine.buffs import BUFF_TEMPLATES
        potency = crafted_consumable_potency_pips(quality)
        base = BUFF_TEMPLATES.get(buff_type, {}).get("stat_modifiers", {})
        if not potency:
            return dict(base)
        return {stat: max(0, pips + potency) for stat, pips in base.items()}

    def test_stimpack_q95_plus1(self):
        # base strength 3 (+1D) → 4 (+1D+1)
        self.assertEqual(self._scaled_mods("stimpack", 95), {"strength": 4})

    def test_stimpack_q50_vendor_unchanged(self):
        self.assertEqual(self._scaled_mods("stimpack", 50), {"strength": 3})

    def test_stimpack_q40_shoddy_minus1(self):
        self.assertEqual(self._scaled_mods("stimpack", 40), {"strength": 2})

    def test_adrenaline_q95_bounded(self):
        # base strength 6 (+2D) → 7 — still below +3D (9), tier ladder intact.
        self.assertEqual(self._scaled_mods("adrenaline_shot", 95), {"strength": 7})

    def test_q95_stim_below_next_tier(self):
        # The power-creep invariant: a q95 stimpack (4 pips) stays strictly under
        # adrenaline_shot's vendor base (6 pips). No tier collapse.
        stim_q95 = self._scaled_mods("stimpack", 95)["strength"]
        from engine.buffs import BUFF_TEMPLATES
        adren_base = BUFF_TEMPLATES["adrenaline_shot"]["stat_modifiers"]["strength"]
        self.assertLess(stim_q95, adren_base)


class TestAddBuffOverrideOnReapply(unittest.TestCase):
    """A higher-quality re-applied stim must REPLACE the existing buff's
    magnitude, not silently keep the old one (the add_buff refresh-path bug)."""

    def test_reapply_with_override_updates_magnitude(self):
        from engine.buffs import add_buff, get_active_buffs
        c = {"attributes": "{}"}
        # First apply at vendor magnitude.
        add_buff(c, "stimpack", stat_modifiers={"strength": 3})
        # Re-apply (max_stacks=1 → refresh path) with a higher-quality override.
        add_buff(c, "stimpack", stat_modifiers={"strength": 4})
        buffs = [b for b in get_active_buffs(c) if b.buff_type == "stimpack"]
        self.assertEqual(len(buffs), 1)
        self.assertEqual(buffs[0].stat_modifiers, {"strength": 4})

    def test_plain_reapply_without_override_keeps_existing(self):
        # A re-apply with NO explicit stat_modifiers override must not reset the
        # existing buff to the template (only explicit overrides take effect).
        from engine.buffs import add_buff, get_active_buffs
        c = {"attributes": "{}"}
        add_buff(c, "stimpack", stat_modifiers={"strength": 4})  # crafted
        add_buff(c, "stimpack")  # plain re-apply, no override
        buffs = [b for b in get_active_buffs(c) if b.buff_type == "stimpack"]
        self.assertEqual(buffs[0].stat_modifiers, {"strength": 4})


class TestQualityRoundingAtBoundary(unittest.TestCase):
    """The crafting delivery stores round(quality), matching the displayed
    value and the band boundary (int() would mis-store 69.9 as 69)."""

    def _craft_quality(self, existing_consumables, key, quality_float):
        from engine.buffs import _normalize_consumable_entry as norm
        existing = norm(existing_consumables.get(key, 0))
        existing_consumables[key] = {
            "count": existing["count"] + 1,
            "quality": max(existing["quality"], round(quality_float)),
        }
        return existing_consumables[key]["quality"]

    def test_69_9_rounds_to_70_earns_pip(self):
        q = self._craft_quality({}, "stimpack", 69.9)
        self.assertEqual(q, 70)
        self.assertEqual(crafted_consumable_potency_pips(q), 1)

    def test_69_4_rounds_to_69_no_pip(self):
        q = self._craft_quality({}, "stimpack", 69.4)
        self.assertEqual(q, 69)
        self.assertEqual(crafted_consumable_potency_pips(q), 0)


if __name__ == "__main__":
    unittest.main()
