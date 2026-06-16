# -*- coding: utf-8 -*-
"""
tests/test_help_social_basics.py — help-corpus completeness (batch 3).

Verifies that six newly-added help files load cleanly and carry the
expected frontmatter:

  data/help/commands/say.md      — say / ' / " speech command
  data/help/commands/emote.md    — emote / : / pose action command
  data/help/commands/whisper.md  — whisper / wh / tell private speech
  data/help/commands/+who.md     — +who / who online list
  data/help/commands/+inv.md     — +inv / inventory / i
  data/help/commands/+sheet.md   — +sheet / score / stats

Strategy mirrors tests/test_help_wildspace_holonet.py:
exercise load_help_file end-to-end against the real on-disk files.
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_SAY_PATH     = os.path.join(_CMD_DIR, "say.md")
_EMOTE_PATH   = os.path.join(_CMD_DIR, "emote.md")
_WHISPER_PATH = os.path.join(_CMD_DIR, "whisper.md")
_WHO_PATH     = os.path.join(_CMD_DIR, "+who.md")
_INV_PATH     = os.path.join(_CMD_DIR, "+inv.md")
_SHEET_PATH   = os.path.join(_CMD_DIR, "+sheet.md")


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ══════════════════════════════════════════════════════════════════════════════
# 1.  Files exist on disk
# ══════════════════════════════════════════════════════════════════════════════

class TestHelpFilesExist(unittest.TestCase):
    def test_say_exists(self):
        self.assertTrue(os.path.isfile(_SAY_PATH), f"Missing: {_SAY_PATH}")

    def test_emote_exists(self):
        self.assertTrue(os.path.isfile(_EMOTE_PATH), f"Missing: {_EMOTE_PATH}")

    def test_whisper_exists(self):
        self.assertTrue(os.path.isfile(_WHISPER_PATH), f"Missing: {_WHISPER_PATH}")

    def test_who_exists(self):
        self.assertTrue(os.path.isfile(_WHO_PATH), f"Missing: {_WHO_PATH}")

    def test_inv_exists(self):
        self.assertTrue(os.path.isfile(_INV_PATH), f"Missing: {_INV_PATH}")

    def test_sheet_exists(self):
        self.assertTrue(os.path.isfile(_SHEET_PATH), f"Missing: {_SHEET_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
# 2.  say help
# ══════════════════════════════════════════════════════════════════════════════

class TestSayHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SAY_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "say")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_shortcut(self):
        self.assertIn("'", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_room(self):
        self.assertIn("room", self.entry.body.lower())

    def test_body_mentions_shortcut(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "shortcut" in body_lower or "'" in self.entry.body,
            "say body should mention the quote shortcut",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3.  emote help
# ══════════════════════════════════════════════════════════════════════════════

class TestEmoteHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_EMOTE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "emote")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_colon(self):
        self.assertIn(":", self.entry.aliases)

    def test_aliases_include_pose(self):
        self.assertIn("pose", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)

    def test_body_mentions_third_person(self):
        body_lower = self.entry.body.lower()
        self.assertIn("third person", body_lower)

    def test_body_mentions_possessive(self):
        body_lower = self.entry.body.lower()
        self.assertIn("possessive", body_lower)


# ══════════════════════════════════════════════════════════════════════════════
# 4.  whisper help
# ══════════════════════════════════════════════════════════════════════════════

class TestWhisperHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_WHISPER_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "whisper")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_wh(self):
        self.assertIn("wh", self.entry.aliases)

    def test_aliases_include_tell(self):
        self.assertIn("tell", self.entry.aliases)

    def test_examples_use_equals_separator(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)
        for ex in self.entry.examples:
            self.assertIn("=", ex["cmd"], "whisper syntax requires '=' separator")

    def test_body_mentions_same_room(self):
        body_lower = self.entry.body.lower()
        self.assertIn("same room", body_lower)

    def test_body_mentions_page(self):
        body_lower = self.entry.body.lower()
        self.assertIn("page", body_lower)


# ══════════════════════════════════════════════════════════════════════════════
# 5.  +who help
# ══════════════════════════════════════════════════════════════════════════════

class TestWhoHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_WHO_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+who")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("online", self.entry.title.lower())

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_who(self):
        self.assertIn("who", self.entry.aliases)

    def test_aliases_include_online(self):
        self.assertIn("online", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_species(self):
        self.assertIn("species", self.entry.body.lower())

    def test_body_mentions_protocol(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "web" in body_lower or "telnet" in body_lower or "protocol" in body_lower,
            "+who body should mention connection protocol",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 6.  +inv help
# ══════════════════════════════════════════════════════════════════════════════

class TestInvHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_INV_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+inv")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("inv", self.entry.title.lower())

    def test_category_gear(self):
        self.assertIn("gear", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_i(self):
        self.assertIn("i", self.entry.aliases)

    def test_aliases_include_inventory(self):
        self.assertIn("inventory", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_equipped(self):
        self.assertIn("equipped", self.entry.body.lower())

    def test_body_mentions_credits(self):
        self.assertIn("credits", self.entry.body.lower())

    def test_body_mentions_carried(self):
        self.assertIn("carried", self.entry.body.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 7.  +sheet help
# ══════════════════════════════════════════════════════════════════════════════

class TestSheetHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SHEET_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+sheet")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("sheet", self.entry.title.lower())

    def test_category_info(self):
        self.assertIn("info", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_score(self):
        self.assertIn("score", self.entry.aliases)

    def test_aliases_include_stats(self):
        self.assertIn("stats", self.entry.aliases)

    def test_examples_include_switches(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("/brief" in c for c in cmds), "Missing /brief example")
        self.assertTrue(any("/skills" in c for c in cmds), "Missing /skills example")
        self.assertTrue(any("/combat" in c for c in cmds), "Missing /combat example")

    def test_body_mentions_attributes(self):
        body_lower = self.entry.body.lower()
        self.assertIn("attribute", body_lower)

    def test_body_mentions_skills(self):
        self.assertIn("skill", self.entry.body.lower())

    def test_body_mentions_d6(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "d6" in body_lower or "die code" in body_lower or "dice" in body_lower,
            "+sheet body should mention D6 / dice",
        )

    def test_body_mentions_wounds(self):
        self.assertIn("wound", self.entry.body.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 8.  Cross-file consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.say     = _load(_SAY_PATH)
        cls.emote   = _load(_EMOTE_PATH)
        cls.whisper = _load(_WHISPER_PATH)
        cls.who     = _load(_WHO_PATH)
        cls.inv     = _load(_INV_PATH)
        cls.sheet   = _load(_SHEET_PATH)

    def test_distinct_keys(self):
        keys = {
            self.say.key, self.emote.key, self.whisper.key,
            self.who.key, self.inv.key, self.sheet.key,
        }
        self.assertEqual(len(keys), 6, f"Duplicate keys: {keys}")

    def test_say_links_emote(self):
        self.assertIn("emote", self.say.see_also)

    def test_emote_links_say(self):
        self.assertIn("say", self.emote.see_also)

    def test_whisper_links_say(self):
        self.assertIn("say", self.whisper.see_also)

    def test_sheet_links_inv(self):
        self.assertIn("+inv", self.sheet.see_also)

    def test_inv_links_sheet(self):
        self.assertIn("+sheet", self.inv.see_also)


if __name__ == "__main__":
    unittest.main()
