# -*- coding: utf-8 -*-
"""
tests/test_help_gear_economy_combat.py — help-corpus completeness batch 6.

Verifies that eight newly-added help files load cleanly and carry the
expected frontmatter:

  data/help/commands/+finances.md  — credit flow ledger
  data/help/commands/+buffs.md     — active effects display
  data/help/commands/+weapons.md   — weapon reference list
  data/help/commands/+armor.md     — armor reference list
  data/help/commands/+threat.md    — area threat band
  data/help/commands/+weather.md   — local time and weather
  data/help/commands/+repair.md    — repair equipped weapon
  data/help/commands/+soak.md      — pre-declare CP for soak
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_FINANCES_PATH = os.path.join(_CMD_DIR, "+finances.md")
_BUFFS_PATH    = os.path.join(_CMD_DIR, "+buffs.md")
_WEAPONS_PATH  = os.path.join(_CMD_DIR, "+weapons.md")
_ARMOR_PATH    = os.path.join(_CMD_DIR, "+armor.md")
_THREAT_PATH   = os.path.join(_CMD_DIR, "+threat.md")
_WEATHER_PATH  = os.path.join(_CMD_DIR, "+weather.md")
_REPAIR_PATH   = os.path.join(_CMD_DIR, "+repair.md")
_SOAK_PATH     = os.path.join(_CMD_DIR, "+soak.md")

_ALL_PATHS = [
    _FINANCES_PATH, _BUFFS_PATH, _WEAPONS_PATH, _ARMOR_PATH,
    _THREAT_PATH, _WEATHER_PATH, _REPAIR_PATH, _SOAK_PATH,
]


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ══════════════════════════════════════════════════════════════════════════════
# 1.  Files exist on disk
# ══════════════════════════════════════════════════════════════════════════════

class TestHelpFilesExist(unittest.TestCase):
    def test_finances_exists(self):
        self.assertTrue(os.path.isfile(_FINANCES_PATH), f"Missing: {_FINANCES_PATH}")

    def test_buffs_exists(self):
        self.assertTrue(os.path.isfile(_BUFFS_PATH), f"Missing: {_BUFFS_PATH}")

    def test_weapons_exists(self):
        self.assertTrue(os.path.isfile(_WEAPONS_PATH), f"Missing: {_WEAPONS_PATH}")

    def test_armor_exists(self):
        self.assertTrue(os.path.isfile(_ARMOR_PATH), f"Missing: {_ARMOR_PATH}")

    def test_threat_exists(self):
        self.assertTrue(os.path.isfile(_THREAT_PATH), f"Missing: {_THREAT_PATH}")

    def test_weather_exists(self):
        self.assertTrue(os.path.isfile(_WEATHER_PATH), f"Missing: {_WEATHER_PATH}")

    def test_repair_exists(self):
        self.assertTrue(os.path.isfile(_REPAIR_PATH), f"Missing: {_REPAIR_PATH}")

    def test_soak_exists(self):
        self.assertTrue(os.path.isfile(_SOAK_PATH), f"Missing: {_SOAK_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
# 2.  +finances help
# ══════════════════════════════════════════════════════════════════════════════

class TestFinancesHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_FINANCES_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+finances")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("finance", self.entry.title.lower())

    def test_category_economy(self):
        self.assertIn("economy", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_ledger(self):
        self.assertIn("+ledger", self.entry.aliases)

    def test_examples_cover_windows(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("hour" in c for c in cmds), "Missing 'hour' window example")
        self.assertTrue(any("week" in c for c in cmds), "Missing 'week' window example")

    def test_body_mentions_credits(self):
        self.assertIn("credit", self.entry.body.lower())

    def test_body_mentions_faucet_or_earned(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "faucet" in body_lower or "earned" in body_lower,
            "finances body should mention income",
        )

    def test_body_mentions_sink_or_spent(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "sink" in body_lower or "spent" in body_lower,
            "finances body should mention spending",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.  +buffs help
# ══════════════════════════════════════════════════════════════════════════════

class TestBuffsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_BUFFS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+buffs")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("buff", self.entry.title.lower())

    def test_category_character(self):
        self.assertIn("character", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_effects(self):
        self.assertIn("+effects", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_duration(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "duration" in body_lower or "remaining" in body_lower,
            "buffs body should mention duration/remaining",
        )

    def test_body_mentions_debuff(self):
        self.assertIn("debuff", self.entry.body.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 4.  +weapons help
# ══════════════════════════════════════════════════════════════════════════════

class TestWeaponsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_WEAPONS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+weapons")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("weapon", self.entry.title.lower())

    def test_category_gear(self):
        self.assertIn("gear", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_armory(self):
        self.assertIn("armory", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_damage(self):
        self.assertIn("damage", self.entry.body.lower())

    def test_body_mentions_range(self):
        self.assertIn("range", self.entry.body.lower())

    def test_body_mentions_craft(self):
        self.assertIn("craft", self.entry.body.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 5.  +armor help
# ══════════════════════════════════════════════════════════════════════════════

class TestArmorHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_ARMOR_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+armor")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("armor", self.entry.title.lower())

    def test_category_gear(self):
        self.assertIn("gear", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_armorlist(self):
        self.assertIn("armorlist", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_protection(self):
        self.assertIn("protection", self.entry.body.lower())

    def test_body_mentions_dexterity_penalty(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "dex" in body_lower or "dexterity" in body_lower,
            "armor body should mention DEX penalty",
        )

    def test_see_also_includes_weapons(self):
        self.assertIn("+weapons", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 6.  +threat help
# ══════════════════════════════════════════════════════════════════════════════

class TestThreatHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_THREAT_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+threat")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("threat", self.entry.title.lower())

    def test_category_world(self):
        self.assertIn("world", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_threat(self):
        self.assertIn("threat", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_frontier(self):
        self.assertIn("frontier", self.entry.body.lower())

    def test_body_mentions_deep_wilds(self):
        self.assertIn("deep wilds", self.entry.body.lower())

    def test_body_distinguishes_threat_from_security(self):
        body_lower = self.entry.body.lower()
        self.assertIn("security", body_lower)
        self.assertIn("threat", body_lower)


# ══════════════════════════════════════════════════════════════════════════════
# 7.  +weather help
# ══════════════════════════════════════════════════════════════════════════════

class TestWeatherHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_WEATHER_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+weather")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("weather", self.entry.title.lower())

    def test_category_world(self):
        self.assertIn("world", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_time(self):
        self.assertIn("+time", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_tatooine(self):
        self.assertIn("tatooine", self.entry.body.lower())

    def test_body_mentions_sandstorm(self):
        self.assertIn("sandstorm", self.entry.body.lower())

    def test_body_mentions_penalty(self):
        self.assertIn("penalty", self.entry.body.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 8.  +repair help
# ══════════════════════════════════════════════════════════════════════════════

class TestRepairHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_REPAIR_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+repair")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("repair", self.entry.title.lower())

    def test_category_gear(self):
        self.assertIn("gear", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_condition(self):
        self.assertIn("condition", self.entry.body.lower())

    def test_body_mentions_max_condition_drop(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "max" in body_lower and "condition" in body_lower,
            "repair body should mention max condition drop",
        )

    def test_body_mentions_credits(self):
        self.assertIn("credit", self.entry.body.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 9.  +soak help
# ══════════════════════════════════════════════════════════════════════════════

class TestSoakHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SOAK_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+soak")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("soak", self.entry.title.lower())

    def test_category_combat(self):
        self.assertIn("combat", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_soak(self):
        self.assertIn("soak", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_character_points(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "character point" in body_lower or " cp " in body_lower,
            "soak body should mention Character Points",
        )

    def test_body_mentions_strength(self):
        self.assertIn("strength", self.entry.body.lower())

    def test_body_mentions_five_cp_max(self):
        self.assertIn("5", self.entry.body)


# ══════════════════════════════════════════════════════════════════════════════
# 10.  Cross-file consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossConsistency(unittest.TestCase):
    """Distinct keys; weapons/armor cross-link each other."""

    @classmethod
    def setUpClass(cls):
        cls.finances = _load(_FINANCES_PATH)
        cls.buffs    = _load(_BUFFS_PATH)
        cls.weapons  = _load(_WEAPONS_PATH)
        cls.armor    = _load(_ARMOR_PATH)
        cls.threat   = _load(_THREAT_PATH)
        cls.weather  = _load(_WEATHER_PATH)
        cls.repair   = _load(_REPAIR_PATH)
        cls.soak     = _load(_SOAK_PATH)

    def test_distinct_keys(self):
        keys = {
            self.finances.key, self.buffs.key, self.weapons.key,
            self.armor.key, self.threat.key, self.weather.key,
            self.repair.key, self.soak.key,
        }
        self.assertEqual(len(keys), 8, f"Duplicate keys among help files: {keys}")

    def test_weapons_and_armor_cross_link(self):
        self.assertIn("+armor", self.weapons.see_also)
        self.assertIn("+weapons", self.armor.see_also)

    def test_repair_links_weapons(self):
        self.assertIn("+weapons", self.repair.see_also)

    def test_soak_links_combat(self):
        self.assertIn("+combat", self.soak.see_also)


if __name__ == "__main__":
    unittest.main()
