# -*- coding: utf-8 -*-
"""
tests/test_help_dice_party_scene.py — help-corpus completeness (batch 4).

Verifies that nine newly-added help files load cleanly and carry the
expected frontmatter:

  data/help/commands/+roll.md     — +roll dice command
  data/help/commands/+check.md    — +check skill vs difficulty
  data/help/commands/+opposed.md  — +opposed opposed roll
  data/help/commands/+party.md    — +party group system
  data/help/commands/+scene.md    — +scene scene logging
  data/help/commands/+scenes.md   — +scenes scene list
  data/help/commands/+events.md   — +events event calendar list
  data/help/commands/+event.md    — +event detail/management
  data/help/commands/+cantina.md  — +cantina staff encounter table
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_ROLL_PATH     = os.path.join(_CMD_DIR, "+roll.md")
_CHECK_PATH    = os.path.join(_CMD_DIR, "+check.md")
_OPPOSED_PATH  = os.path.join(_CMD_DIR, "+opposed.md")
_PARTY_PATH    = os.path.join(_CMD_DIR, "+party.md")
_SCENE_PATH    = os.path.join(_CMD_DIR, "+scene.md")
_SCENES_PATH   = os.path.join(_CMD_DIR, "+scenes.md")
_EVENTS_PATH   = os.path.join(_CMD_DIR, "+events.md")
_EVENT_PATH    = os.path.join(_CMD_DIR, "+event.md")
_CANTINA_PATH  = os.path.join(_CMD_DIR, "+cantina.md")


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ══════════════════════════════════════════════════════════════════════════════
# 1.  Files exist on disk
# ══════════════════════════════════════════════════════════════════════════════

class TestHelpFilesExist(unittest.TestCase):
    def test_roll_exists(self):
        self.assertTrue(os.path.isfile(_ROLL_PATH), f"Missing: {_ROLL_PATH}")

    def test_check_exists(self):
        self.assertTrue(os.path.isfile(_CHECK_PATH), f"Missing: {_CHECK_PATH}")

    def test_opposed_exists(self):
        self.assertTrue(os.path.isfile(_OPPOSED_PATH), f"Missing: {_OPPOSED_PATH}")

    def test_party_exists(self):
        self.assertTrue(os.path.isfile(_PARTY_PATH), f"Missing: {_PARTY_PATH}")

    def test_scene_exists(self):
        self.assertTrue(os.path.isfile(_SCENE_PATH), f"Missing: {_SCENE_PATH}")

    def test_scenes_exists(self):
        self.assertTrue(os.path.isfile(_SCENES_PATH), f"Missing: {_SCENES_PATH}")

    def test_events_exists(self):
        self.assertTrue(os.path.isfile(_EVENTS_PATH), f"Missing: {_EVENTS_PATH}")

    def test_event_exists(self):
        self.assertTrue(os.path.isfile(_EVENT_PATH), f"Missing: {_EVENT_PATH}")

    def test_cantina_exists(self):
        self.assertTrue(os.path.isfile(_CANTINA_PATH), f"Missing: {_CANTINA_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
# 2.  +roll help
# ══════════════════════════════════════════════════════════════════════════════

class TestRollHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_ROLL_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+roll")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_dice(self):
        self.assertIn("dice", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_roll(self):
        self.assertIn("roll", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)

    def test_body_mentions_wild_die(self):
        body_lower = self.entry.body.lower()
        self.assertIn("wild", body_lower)

    def test_body_mentions_skill(self):
        self.assertIn("skill", self.entry.body.lower())

    def test_see_also_includes_check(self):
        self.assertIn("+check", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 3.  +check help
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_CHECK_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+check")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_dice(self):
        self.assertIn("dice", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_check(self):
        self.assertIn("check", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)

    def test_body_mentions_difficulty(self):
        self.assertIn("difficult", self.entry.body.lower())

    def test_body_mentions_success(self):
        self.assertIn("success", self.entry.body.lower())

    def test_see_also_includes_roll(self):
        self.assertIn("+roll", self.entry.see_also)

    def test_see_also_includes_opposed(self):
        self.assertIn("+opposed", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 4.  +opposed help
# ══════════════════════════════════════════════════════════════════════════════

class TestOpposedHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_OPPOSED_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+opposed")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_dice(self):
        self.assertIn("dice", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_vs(self):
        self.assertIn("vs", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)

    def test_body_mentions_opposing(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "opposing" in body_lower or "opposed" in body_lower,
            "+opposed body should mention opposing/opposed roll",
        )

    def test_body_mentions_pool(self):
        self.assertIn("pool", self.entry.body.lower())

    def test_see_also_includes_roll(self):
        self.assertIn("+roll", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 5.  +party help
# ══════════════════════════════════════════════════════════════════════════════

class TestPartyHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_PARTY_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+party")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_party(self):
        self.assertIn("party", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)

    def test_body_mentions_invite(self):
        self.assertIn("invite", self.entry.body.lower())

    def test_body_mentions_leader(self):
        self.assertIn("leader", self.entry.body.lower())

    def test_body_mentions_six(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "six" in body_lower or "6" in self.entry.body,
            "+party body should mention the 6-member cap",
        )

    def test_see_also_includes_who(self):
        self.assertIn("+who", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 6.  +scene help
# ══════════════════════════════════════════════════════════════════════════════

class TestSceneHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SCENE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+scene")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_rp(self):
        self.assertIn("rp", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_scene(self):
        self.assertIn("scene", self.entry.aliases)

    def test_examples_include_start(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("start" in c for c in cmds), "Missing /start example")

    def test_examples_include_stop(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("stop" in c for c in cmds), "Missing /stop example")

    def test_body_mentions_log(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "log" in body_lower or "logged" in body_lower,
            "+scene body should mention logging",
        )

    def test_body_mentions_share(self):
        self.assertIn("share", self.entry.body.lower())

    def test_see_also_includes_scenes(self):
        self.assertIn("+scenes", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 7.  +scenes help
# ══════════════════════════════════════════════════════════════════════════════

class TestScenesHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SCENES_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+scenes")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_rp(self):
        self.assertIn("rp", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_scenes(self):
        self.assertIn("scenes", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_status(self):
        self.assertIn("status", self.entry.body.lower())

    def test_body_mentions_active(self):
        self.assertIn("active", self.entry.body.lower())

    def test_see_also_includes_scene(self):
        self.assertIn("+scene", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 8.  +events help
# ══════════════════════════════════════════════════════════════════════════════

class TestEventsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_EVENTS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+events")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_calendar(self):
        self.assertIn("+calendar", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_signup(self):
        self.assertIn("sign", self.entry.body.lower())

    def test_see_also_includes_event(self):
        self.assertIn("+event", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 9.  +event help
# ══════════════════════════════════════════════════════════════════════════════

class TestEventHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_EVENT_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+event")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_examples_include_create(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("create" in c for c in cmds), "Missing /create example")

    def test_examples_include_signup(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("signup" in c for c in cmds), "Missing /signup example")

    def test_body_mentions_creator(self):
        self.assertIn("creator", self.entry.body.lower())

    def test_body_mentions_cancel(self):
        self.assertIn("cancel", self.entry.body.lower())

    def test_see_also_includes_events(self):
        self.assertIn("+events", self.entry.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 10.  +cantina help (staff)
# ══════════════════════════════════════════════════════════════════════════════

class TestCantinaHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_CANTINA_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+cantina")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_staff(self):
        self.assertIn("staff", self.entry.category.lower())

    def test_access_level_builder(self):
        self.assertEqual(self.entry.access_level, 2)

    def test_aliases_include_cantinaroll(self):
        self.assertIn("+cantinaroll", self.entry.aliases)

    def test_examples_include_random(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertIn("+cantina", cmds)

    def test_examples_include_code(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any(c.startswith("+cantina ") for c in cmds), "Missing code example")

    def test_body_mentions_d66(self):
        self.assertIn("d66", self.entry.body.lower())

    def test_body_mentions_staff(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "staff" in body_lower or "builder" in body_lower or "gm" in body_lower,
            "+cantina body should mention staff/builder/GM access",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 11.  Cross-file consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roll     = _load(_ROLL_PATH)
        cls.check    = _load(_CHECK_PATH)
        cls.opposed  = _load(_OPPOSED_PATH)
        cls.party    = _load(_PARTY_PATH)
        cls.scene    = _load(_SCENE_PATH)
        cls.scenes   = _load(_SCENES_PATH)
        cls.events   = _load(_EVENTS_PATH)
        cls.event    = _load(_EVENT_PATH)
        cls.cantina  = _load(_CANTINA_PATH)

    def test_distinct_keys(self):
        keys = {
            self.roll.key, self.check.key, self.opposed.key,
            self.party.key, self.scene.key, self.scenes.key,
            self.events.key, self.event.key, self.cantina.key,
        }
        self.assertEqual(len(keys), 9, f"Duplicate keys: {keys}")

    def test_roll_links_check(self):
        self.assertIn("+check", self.roll.see_also)

    def test_check_links_roll(self):
        self.assertIn("+roll", self.check.see_also)

    def test_check_links_opposed(self):
        self.assertIn("+opposed", self.check.see_also)

    def test_opposed_links_roll(self):
        self.assertIn("+roll", self.opposed.see_also)

    def test_scene_links_scenes(self):
        self.assertIn("+scenes", self.scene.see_also)

    def test_scenes_links_scene(self):
        self.assertIn("+scene", self.scenes.see_also)

    def test_events_links_event(self):
        self.assertIn("+event", self.events.see_also)

    def test_event_links_events(self):
        self.assertIn("+events", self.event.see_also)


if __name__ == "__main__":
    unittest.main()
