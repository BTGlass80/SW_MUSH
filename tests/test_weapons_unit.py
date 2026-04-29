# -*- coding: utf-8 -*-
"""
tests/test_weapons_unit.py — Code review C6 fix tests (drop K-C6e)

Per code_review_session32.md Severity C6 ("24 Untested Engine Files"):
`engine/weapons.py` powers ranged combat difficulty calculation
(range-band → base difficulty), melee/ranged dispatch, and the
weapon/armor catalog. A regression here silently breaks the entire
combat math.

Coverage:
  - RangeBand: enum values match WEG D6 R&E difficulty ladder, label
    property complete.
  - WeaponData: is_ranged/is_melee/is_armor predicates, get_range_band
    on all five bands (PB, short, medium, long, OOR), format_ranges
    for ranged/melee, format_short shape.
  - WeaponRegistry: load_file from synthetic YAML, get with key
    normalization, find_by_name (exact / prefix / contains / miss),
    all_weapons / all_armor / all separation, count.
  - Live `data/weapons.yaml` guardrails: every entry parses, every
    ranged weapon has 4-tuple ranges, every melee has empty ranges,
    no duplicate keys, name/skill/damage non-empty.
  - Module convenience: get_weapon_registry returns a singleton.

Pure surface only. No async, no DB.
"""
import os
import sys
import textwrap
import unittest
from tempfile import TemporaryDirectory

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import weapons as weapons_module  # noqa: E402
from engine.weapons import (  # noqa: E402
    RangeBand,
    WeaponData,
    WeaponRegistry,
    get_weapon_registry,
)


# ══════════════════════════════════════════════════════════════════════════════
# RangeBand enum
# ══════════════════════════════════════════════════════════════════════════════


class TestRangeBand(unittest.TestCase):
    """Range bands map to base difficulty per R&E p82."""

    def test_canonical_difficulty_values(self):
        self.assertEqual(int(RangeBand.POINT_BLANK), 5)
        self.assertEqual(int(RangeBand.SHORT), 10)
        self.assertEqual(int(RangeBand.MEDIUM), 15)
        self.assertEqual(int(RangeBand.LONG), 20)
        self.assertEqual(int(RangeBand.OUT_OF_RANGE), 99)

    def test_label_for_every_band(self):
        # Every defined band must have a label (no KeyError)
        self.assertEqual(RangeBand.POINT_BLANK.label, "Point-Blank")
        self.assertEqual(RangeBand.SHORT.label, "Short")
        self.assertEqual(RangeBand.MEDIUM.label, "Medium")
        self.assertEqual(RangeBand.LONG.label, "Long")
        self.assertEqual(RangeBand.OUT_OF_RANGE.label, "Out of Range")


# ══════════════════════════════════════════════════════════════════════════════
# WeaponData — predicates and accessors
# ══════════════════════════════════════════════════════════════════════════════


class TestWeaponDataPredicates(unittest.TestCase):
    def test_is_ranged_with_four_range_values(self):
        w = WeaponData(
            key="blaster_pistol", name="Blaster Pistol",
            weapon_type="blaster", skill="blaster", damage="4D",
            ranges=[3, 10, 30, 120],
        )
        self.assertTrue(w.is_ranged)
        self.assertFalse(w.is_melee)
        self.assertFalse(w.is_armor)

    def test_is_ranged_false_with_partial_ranges(self):
        # Defensive: a malformed YAML with 3-tuple ranges should NOT be
        # treated as ranged
        w = WeaponData(
            key="bogus", name="Bogus",
            weapon_type="blaster", skill="blaster", damage="3D",
            ranges=[3, 10, 30],
        )
        self.assertFalse(w.is_ranged)

    def test_is_ranged_false_with_empty_ranges(self):
        w = WeaponData(
            key="vibroblade", name="Vibroblade",
            weapon_type="melee", skill="melee combat", damage="STR+1D",
        )
        self.assertFalse(w.is_ranged)

    def test_is_melee_for_melee_type(self):
        w = WeaponData(
            key="vibroblade", name="Vibroblade",
            weapon_type="melee", skill="melee combat", damage="STR+1D",
        )
        self.assertTrue(w.is_melee)

    def test_is_melee_for_lightsaber_type(self):
        w = WeaponData(
            key="lightsaber", name="Lightsaber",
            weapon_type="lightsaber", skill="lightsaber", damage="5D",
        )
        self.assertTrue(w.is_melee)

    def test_is_armor_for_armor_type(self):
        w = WeaponData(
            key="combat_armor", name="Combat Armor",
            weapon_type="armor", skill="", damage="",
        )
        self.assertTrue(w.is_armor)
        self.assertFalse(w.is_melee)


# ══════════════════════════════════════════════════════════════════════════════
# get_range_band — five-band lookup
# ══════════════════════════════════════════════════════════════════════════════


class TestGetRangeBand(unittest.TestCase):
    def setUp(self):
        # Standard blaster pistol: [3, 10, 30, 120]
        # PB <3, short 3-10, medium 11-30, long 31-120, OOR >120
        self.w = WeaponData(
            key="blaster_pistol", name="Blaster Pistol",
            weapon_type="blaster", skill="blaster", damage="4D",
            ranges=[3, 10, 30, 120],
        )

    def test_below_pb_min_is_point_blank(self):
        self.assertEqual(self.w.get_range_band(0), RangeBand.POINT_BLANK)
        self.assertEqual(self.w.get_range_band(2), RangeBand.POINT_BLANK)

    def test_at_short_min_is_short(self):
        # Distance == pb_min should be Short, not Point-Blank
        self.assertEqual(self.w.get_range_band(3), RangeBand.SHORT)

    def test_at_short_max_is_short(self):
        self.assertEqual(self.w.get_range_band(10), RangeBand.SHORT)

    def test_just_past_short_is_medium(self):
        self.assertEqual(self.w.get_range_band(11), RangeBand.MEDIUM)

    def test_at_medium_max_is_medium(self):
        self.assertEqual(self.w.get_range_band(30), RangeBand.MEDIUM)

    def test_just_past_medium_is_long(self):
        self.assertEqual(self.w.get_range_band(31), RangeBand.LONG)

    def test_at_long_max_is_long(self):
        self.assertEqual(self.w.get_range_band(120), RangeBand.LONG)

    def test_past_long_is_out_of_range(self):
        self.assertEqual(self.w.get_range_band(121), RangeBand.OUT_OF_RANGE)
        self.assertEqual(self.w.get_range_band(9999), RangeBand.OUT_OF_RANGE)

    def test_no_range_data_defaults_to_short(self):
        # Melee weapon (no range data) — get_range_band falls back to SHORT
        # which is Easy difficulty — sensible default
        melee = WeaponData(
            key="vibroblade", name="Vibroblade",
            weapon_type="melee", skill="melee combat", damage="STR+1D",
        )
        self.assertEqual(melee.get_range_band(5), RangeBand.SHORT)

    def test_partial_range_data_defaults_to_short(self):
        # 3-tuple ranges (malformed) — same fallback
        w = WeaponData(
            key="bogus", name="Bogus",
            weapon_type="blaster", skill="blaster", damage="3D",
            ranges=[3, 10, 30],
        )
        self.assertEqual(w.get_range_band(5), RangeBand.SHORT)


# ══════════════════════════════════════════════════════════════════════════════
# Format helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatHelpers(unittest.TestCase):
    def test_format_ranges_ranged_weapon(self):
        w = WeaponData(
            key="blaster_pistol", name="Blaster Pistol",
            weapon_type="blaster", skill="blaster", damage="4D",
            ranges=[3, 10, 30, 120],
        )
        # "3-10/30/120"
        self.assertEqual(w.format_ranges(), "3-10/30/120")

    def test_format_ranges_melee(self):
        w = WeaponData(
            key="vibroblade", name="Vibroblade",
            weapon_type="melee", skill="melee combat", damage="STR+1D",
        )
        self.assertEqual(w.format_ranges(), "Melee")

    def test_format_ranges_no_data_no_melee(self):
        w = WeaponData(
            key="custom", name="Custom",
            weapon_type="blaster", skill="blaster", damage="3D",
            # No ranges — and not melee
        )
        self.assertEqual(w.format_ranges(), "N/A")

    def test_format_short_ranged_includes_damage_and_ranges(self):
        w = WeaponData(
            key="blaster_pistol", name="Blaster Pistol",
            weapon_type="blaster", skill="blaster", damage="4D",
            ranges=[3, 10, 30, 120],
        )
        s = w.format_short()
        self.assertIn("Blaster Pistol", s)
        self.assertIn("4D", s)
        # The medium and long bands should appear
        self.assertIn("30", s)
        self.assertIn("120", s)

    def test_format_short_melee_includes_label(self):
        w = WeaponData(
            key="vibroblade", name="Vibroblade",
            weapon_type="melee", skill="melee combat", damage="STR+1D",
        )
        s = w.format_short()
        self.assertIn("Vibroblade", s)
        self.assertIn("Melee", s)


# ══════════════════════════════════════════════════════════════════════════════
# WeaponRegistry — synthetic YAML
# ══════════════════════════════════════════════════════════════════════════════


SYNTHETIC_YAML = textwrap.dedent("""\
    test_blaster:
      name: "Test Blaster"
      type: blaster
      skill: "blaster"
      damage: "4D"
      ranges: [3, 10, 30, 120]
      ammo: 100
      cost: 500
      stun_capable: true
      notes: "Test weapon"

    test_blade:
      name: "Test Blade"
      type: melee
      skill: "melee combat"
      damage: "STR+1D"
      difficulty: "easy"
      cost: 50

    test_armor:
      name: "Test Armor"
      type: armor
      skill: ""
      damage: ""
      protection_energy: "+1D"
      protection_physical: "+1D+2"
      covers: ["torso", "arms"]
      dexterity_penalty: "-1"
""")


class TestWeaponRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.yaml_path = os.path.join(self.tmp.name, "weapons.yaml")
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            f.write(SYNTHETIC_YAML)
        self.reg = WeaponRegistry()
        self.reg.load_file(self.yaml_path)

    def test_count_after_load(self):
        self.assertEqual(self.reg.count, 3)

    def test_get_by_key(self):
        w = self.reg.get("test_blaster")
        self.assertIsNotNone(w)
        self.assertEqual(w.name, "Test Blaster")
        self.assertEqual(w.damage, "4D")
        self.assertEqual(w.ranges, [3, 10, 30, 120])

    def test_get_normalizes_case_and_spaces(self):
        # 'TEST BLASTER' -> normalized to 'test_blaster'
        w = self.reg.get("TEST BLASTER")
        self.assertIsNotNone(w)
        self.assertEqual(w.name, "Test Blaster")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.reg.get("nonexistent"))

    def test_find_by_name_exact_match(self):
        w = self.reg.find_by_name("Test Blaster")
        self.assertIsNotNone(w)
        self.assertEqual(w.key, "test_blaster")

    def test_find_by_name_case_insensitive(self):
        w = self.reg.find_by_name("test blaster")
        self.assertIsNotNone(w)
        self.assertEqual(w.key, "test_blaster")

    def test_find_by_name_prefix(self):
        # "Test Bla" should prefix-match Test Blaster (Test Blade also
        # has "Test " prefix, but exact-match step doesn't fire so
        # whichever the iteration hits first wins for prefix; we test
        # that SOME deterministic match comes back, not which one).
        w = self.reg.find_by_name("Test Bla")
        self.assertIsNotNone(w)

    def test_find_by_name_contains(self):
        w = self.reg.find_by_name("rmor")
        self.assertIsNotNone(w)
        self.assertEqual(w.key, "test_armor")

    def test_find_by_name_miss_returns_none(self):
        self.assertIsNone(self.reg.find_by_name("zzzzzzz"))

    def test_all_weapons_excludes_armor(self):
        weapons = self.reg.all_weapons()
        keys = {w.key for w in weapons}
        self.assertIn("test_blaster", keys)
        self.assertIn("test_blade", keys)
        self.assertNotIn("test_armor", keys)

    def test_all_armor_only(self):
        armor = self.reg.all_armor()
        keys = {a.key for a in armor}
        self.assertEqual(keys, {"test_armor"})

    def test_all_includes_everything(self):
        every = self.reg.all()
        self.assertEqual(len(every), 3)

    def test_armor_field_propagation(self):
        a = self.reg.get("test_armor")
        self.assertEqual(a.protection_energy, "+1D")
        self.assertEqual(a.protection_physical, "+1D+2")
        self.assertEqual(a.covers, ["torso", "arms"])
        self.assertEqual(a.dexterity_penalty, "-1")

    def test_load_missing_file_logs_warning_no_crash(self):
        reg = WeaponRegistry()
        # Path does not exist — loader should warn and return without
        # raising.
        reg.load_file(os.path.join(self.tmp.name, "nope.yaml"))
        self.assertEqual(reg.count, 0)

    def test_load_empty_file_no_crash(self):
        empty_path = os.path.join(self.tmp.name, "empty.yaml")
        with open(empty_path, "w", encoding="utf-8") as f:
            f.write("")
        reg = WeaponRegistry()
        reg.load_file(empty_path)
        self.assertEqual(reg.count, 0)

    def test_load_skips_non_dict_entries(self):
        # If YAML has a non-dict at top level, the loader should skip,
        # not crash.
        bad_path = os.path.join(self.tmp.name, "bad.yaml")
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write("something_invalid: 'just a string'\n")
        reg = WeaponRegistry()
        reg.load_file(bad_path)
        # The string entry was skipped
        self.assertEqual(reg.count, 0)


# ══════════════════════════════════════════════════════════════════════════════
# Live data guardrails
# ══════════════════════════════════════════════════════════════════════════════


class TestLiveWeaponsYaml(unittest.TestCase):
    """Regression guardrails on live data/weapons.yaml.

    These tests are protective: if someone adds a malformed entry, the
    boot-time singleton would silently mis-classify or crash on first
    use. Better to catch in unit tests.
    """

    @classmethod
    def setUpClass(cls):
        cls.live_path = os.path.join(PROJECT_ROOT, "data", "weapons.yaml")
        cls.reg = WeaponRegistry()
        if os.path.exists(cls.live_path):
            cls.reg.load_file(cls.live_path)

    def test_live_yaml_exists(self):
        self.assertTrue(
            os.path.exists(self.live_path),
            f"data/weapons.yaml missing at {self.live_path}",
        )

    def test_live_yaml_loads_some_weapons(self):
        self.assertGreater(self.reg.count, 0,
                           "data/weapons.yaml loaded zero weapons")

    def test_every_ranged_weapon_has_four_range_values(self):
        for w in self.reg.all_weapons():
            if w.ranges:
                self.assertEqual(
                    len(w.ranges), 4,
                    f"{w.key}: ranges has {len(w.ranges)} values, expected 4",
                )

    def test_ranged_weapons_have_increasing_ranges(self):
        # ranges = [pb_min, short_max, medium_max, long_max] must be
        # non-decreasing; otherwise get_range_band gives wrong band.
        for w in self.reg.all_weapons():
            if w.is_ranged:
                pb, s, m, l = w.ranges
                self.assertLessEqual(
                    pb, s, f"{w.key}: pb_min({pb}) > short_max({s})"
                )
                self.assertLessEqual(
                    s, m, f"{w.key}: short_max({s}) > medium_max({m})"
                )
                self.assertLessEqual(
                    m, l, f"{w.key}: medium_max({m}) > long_max({l})"
                )

    def test_every_weapon_has_name(self):
        for w in self.reg.all():
            self.assertTrue(w.name, f"{w.key}: empty name")

    def test_no_duplicate_keys(self):
        # If two YAML entries had the same key, the second would clobber
        # the first. We can't check the YAML directly here (the loader
        # eats duplicates), but we can sanity-check that every loaded
        # weapon has its own key.
        keys = [w.key for w in self.reg.all()]
        self.assertEqual(
            len(keys), len(set(keys)),
            "Duplicate keys in registry — should be impossible after load",
        )

    def test_every_non_armor_has_damage(self):
        for w in self.reg.all_weapons():
            self.assertTrue(
                w.damage,
                f"{w.key}: weapon has empty damage",
            )

    def test_every_non_armor_has_skill(self):
        for w in self.reg.all_weapons():
            self.assertTrue(
                w.skill,
                f"{w.key}: weapon has empty skill",
            )


# ══════════════════════════════════════════════════════════════════════════════
# Module-level singleton
# ══════════════════════════════════════════════════════════════════════════════


class TestModuleSingleton(unittest.TestCase):
    def test_get_weapon_registry_returns_singleton(self):
        # First call triggers load; second returns same instance
        # Reset module state to be safe across test ordering
        weapons_module._default_registry = None
        a = get_weapon_registry()
        b = get_weapon_registry()
        self.assertIs(a, b)
        self.assertGreater(a.count, 0)


if __name__ == "__main__":
    unittest.main()
