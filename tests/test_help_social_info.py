# -*- coding: utf-8 -*-
"""
tests/test_help_social_info.py — help-corpus completeness (batch 5).

Verifies that nine newly-added help files load cleanly and carry the
expected frontmatter:

  data/help/commands/+finger.md       — player info card
  data/help/commands/+where.md        — player locations
  data/help/commands/+ooc.md          — local OOC chat
  data/help/commands/+channels.md     — channel overview
  data/help/commands/+freqs.md        — tuned frequencies
  data/help/commands/+news.md         — galactic news network
  data/help/commands/+reputation.md   — faction standings
  data/help/commands/+achievements.md — achievement progress
  data/help/commands/+background.md   — character background
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_FINGER_PATH      = os.path.join(_CMD_DIR, "+finger.md")
_WHERE_PATH       = os.path.join(_CMD_DIR, "+where.md")
_OOC_PATH         = os.path.join(_CMD_DIR, "+ooc.md")
_CHANNELS_PATH    = os.path.join(_CMD_DIR, "+channels.md")
_FREQS_PATH       = os.path.join(_CMD_DIR, "+freqs.md")
_NEWS_PATH        = os.path.join(_CMD_DIR, "+news.md")
_REPUTATION_PATH  = os.path.join(_CMD_DIR, "+reputation.md")
_ACHIEVEMENTS_PATH = os.path.join(_CMD_DIR, "+achievements.md")
_BACKGROUND_PATH  = os.path.join(_CMD_DIR, "+background.md")


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ══════════════════════════════════════════════════════════════════════════════
# 1.  Files exist on disk
# ══════════════════════════════════════════════════════════════════════════════

class TestHelpFilesExist(unittest.TestCase):
    def test_finger_exists(self):
        self.assertTrue(os.path.isfile(_FINGER_PATH), f"Missing: {_FINGER_PATH}")

    def test_where_exists(self):
        self.assertTrue(os.path.isfile(_WHERE_PATH), f"Missing: {_WHERE_PATH}")

    def test_ooc_exists(self):
        self.assertTrue(os.path.isfile(_OOC_PATH), f"Missing: {_OOC_PATH}")

    def test_channels_exists(self):
        self.assertTrue(os.path.isfile(_CHANNELS_PATH), f"Missing: {_CHANNELS_PATH}")

    def test_freqs_exists(self):
        self.assertTrue(os.path.isfile(_FREQS_PATH), f"Missing: {_FREQS_PATH}")

    def test_news_exists(self):
        self.assertTrue(os.path.isfile(_NEWS_PATH), f"Missing: {_NEWS_PATH}")

    def test_reputation_exists(self):
        self.assertTrue(os.path.isfile(_REPUTATION_PATH), f"Missing: {_REPUTATION_PATH}")

    def test_achievements_exists(self):
        self.assertTrue(os.path.isfile(_ACHIEVEMENTS_PATH), f"Missing: {_ACHIEVEMENTS_PATH}")

    def test_background_exists(self):
        self.assertTrue(os.path.isfile(_BACKGROUND_PATH), f"Missing: {_BACKGROUND_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
# 2.  +finger help
# ══════════════════════════════════════════════════════════════════════════════

class TestFingerHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_FINGER_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+finger")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_finger(self):
        self.assertIn("finger", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)

    def test_body_mentions_species(self):
        self.assertIn("species", self.entry.body.lower())

    def test_body_mentions_fields(self):
        self.assertIn("field", self.entry.body.lower())

    def test_see_also_includes_who(self):
        self.assertIn("+who", self.entry.see_also)

    def test_see_also_includes_where(self):
        self.assertIn("+where", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 3.  +where help
# ══════════════════════════════════════════════════════════════════════════════

class TestWhereHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_WHERE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+where")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_where(self):
        self.assertIn("where", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_location(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "location" in body_lower or "room" in body_lower,
            "+where body should mention location/room",
        )

    def test_body_mentions_idle(self):
        self.assertIn("idle", self.entry.body.lower())

    def test_see_also_includes_who(self):
        self.assertIn("+who", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 4.  +ooc help
# ══════════════════════════════════════════════════════════════════════════════

class TestOocHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_OOC_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+ooc")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)

    def test_body_distinguishes_local_vs_global(self):
        body_lower = self.entry.body.lower()
        self.assertIn("local", body_lower)
        self.assertIn("global", body_lower)

    def test_body_mentions_room(self):
        self.assertIn("room", self.entry.body.lower())

    def test_see_also_includes_say(self):
        self.assertIn("say", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 5.  +channels help
# ══════════════════════════════════════════════════════════════════════════════

class TestChannelsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_CHANNELS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+channels")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_channels(self):
        self.assertIn("channels", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_ooc(self):
        self.assertIn("ooc", self.entry.body.lower())

    def test_body_mentions_comlink(self):
        self.assertIn("comlink", self.entry.body.lower())

    def test_body_mentions_faction(self):
        self.assertIn("faction", self.entry.body.lower())

    def test_see_also_includes_freqs(self):
        self.assertIn("+freqs", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 6.  +freqs help
# ══════════════════════════════════════════════════════════════════════════════

class TestFreqsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_FREQS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+freqs")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_freqs(self):
        self.assertIn("freqs", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)

    def test_body_mentions_tune(self):
        self.assertIn("tune", self.entry.body.lower())

    def test_body_mentions_commfreq(self):
        self.assertIn("commfreq", self.entry.body.lower())

    def test_see_also_includes_channels(self):
        self.assertIn("+channels", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 7.  +news help
# ══════════════════════════════════════════════════════════════════════════════

class TestNewsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_NEWS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+news")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_info(self):
        self.assertIn("info", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_news(self):
        self.assertIn("news", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_director(self):
        self.assertIn("director", self.entry.body.lower())

    def test_body_mentions_galactic(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "galactic" in body_lower or "gnn" in body_lower,
            "+news body should mention galactic/GNN",
        )

    def test_see_also_includes_holonet(self):
        self.assertIn("+holonet", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 8.  +reputation help
# ══════════════════════════════════════════════════════════════════════════════

class TestReputationHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_REPUTATION_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+reputation")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_factions(self):
        self.assertIn("faction", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_rep(self):
        self.assertIn("+rep", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)

    def test_body_mentions_tiers(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "tier" in body_lower or "neutral" in body_lower,
            "+reputation body should mention tiers or Neutral",
        )

    def test_body_mentions_missions(self):
        self.assertIn("mission", self.entry.body.lower())

    def test_see_also_includes_faction(self):
        self.assertIn("+faction", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 9.  +achievements help
# ══════════════════════════════════════════════════════════════════════════════

class TestAchievementsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_ACHIEVEMENTS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+achievements")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_progress(self):
        self.assertIn("progress", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_ach(self):
        self.assertIn("+ach", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)

    def test_body_mentions_categories(self):
        body_lower = self.entry.body.lower()
        self.assertIn("combat", body_lower)

    def test_body_mentions_cp(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "cp" in body_lower or "contribution" in body_lower,
            "+achievements body should mention CP/Contribution Points",
        )

    def test_see_also_includes_sheet(self):
        self.assertIn("+sheet", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 10.  +background help
# ══════════════════════════════════════════════════════════════════════════════

class TestBackgroundHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_BACKGROUND_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+background")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_character(self):
        self.assertIn("character", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_bg(self):
        self.assertIn("+bg", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)

    def test_body_mentions_director(self):
        self.assertIn("director", self.entry.body.lower())

    def test_body_mentions_npc(self):
        self.assertIn("npc", self.entry.body.lower())

    def test_see_also_includes_sheet(self):
        self.assertIn("+sheet", self.entry.see_also)

    def test_see_also_includes_finger(self):
        self.assertIn("+finger", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 11.  Cross-file consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.finger       = _load(_FINGER_PATH)
        cls.where        = _load(_WHERE_PATH)
        cls.ooc          = _load(_OOC_PATH)
        cls.channels     = _load(_CHANNELS_PATH)
        cls.freqs        = _load(_FREQS_PATH)
        cls.news         = _load(_NEWS_PATH)
        cls.reputation   = _load(_REPUTATION_PATH)
        cls.achievements = _load(_ACHIEVEMENTS_PATH)
        cls.background   = _load(_BACKGROUND_PATH)

    def test_distinct_keys(self):
        keys = {
            self.finger.key, self.where.key, self.ooc.key,
            self.channels.key, self.freqs.key, self.news.key,
            self.reputation.key, self.achievements.key, self.background.key,
        }
        self.assertEqual(len(keys), 9, f"Duplicate keys: {keys}")

    def test_finger_links_where(self):
        self.assertIn("+where", self.finger.see_also)

    def test_where_links_who(self):
        self.assertIn("+who", self.where.see_also)

    def test_channels_links_freqs(self):
        self.assertIn("+freqs", self.channels.see_also)

    def test_freqs_links_channels(self):
        self.assertIn("+channels", self.freqs.see_also)

    def test_news_links_holonet(self):
        self.assertIn("+holonet", self.news.see_also)

    def test_background_links_finger(self):
        self.assertIn("+finger", self.background.see_also)

    def test_reputation_links_faction(self):
        self.assertIn("+faction", self.reputation.see_also)


if __name__ == "__main__":
    unittest.main()
