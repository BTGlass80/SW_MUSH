# -*- coding: utf-8 -*-
"""
tests/test_help_economy_social_ships_batch8.py — help-corpus completeness batch 8.

Verifies that fourteen newly-added help files load cleanly and carry the
expected frontmatter:

  data/help/commands/+char.md           — account / alt-character management
  data/help/commands/+cpstatus.md       — CP advancement status
  data/help/commands/+kudos.md          — peer RP recognition
  data/help/commands/+scenebonus.md     — scene completion tick award
  data/help/commands/+building.md       — player-constructed structures
  data/help/commands/+pcbounty.md       — PC-to-PC bounty system
  data/help/commands/+spacedock.md      — ship yard full repair
  data/help/commands/+shipcrew.md       — ship crew authorization
  data/help/commands/+chargen_notes.md  — chargen rationale notes
  data/help/commands/+village.md        — village quest progress
  data/help/commands/+counsel.md        — Jedi Weight of War counsel
  data/help/commands/+retreat.md        — Jedi retreat declaration
  data/help/commands/+return.md         — end Jedi retreat
  data/help/commands/+healrate.md       — medic service rate
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_CHAR_PATH          = os.path.join(_CMD_DIR, "+char.md")
_CPSTATUS_PATH      = os.path.join(_CMD_DIR, "+cpstatus.md")
_KUDOS_PATH         = os.path.join(_CMD_DIR, "+kudos.md")
_SCENEBONUS_PATH    = os.path.join(_CMD_DIR, "+scenebonus.md")
_BUILDING_PATH      = os.path.join(_CMD_DIR, "+building.md")
_PCBOUNTY_PATH      = os.path.join(_CMD_DIR, "+pcbounty.md")
_SPACEDOCK_PATH     = os.path.join(_CMD_DIR, "+spacedock.md")
_SHIPCREW_PATH      = os.path.join(_CMD_DIR, "+shipcrew.md")
_CHARGEN_NOTES_PATH = os.path.join(_CMD_DIR, "+chargen_notes.md")
_VILLAGE_PATH       = os.path.join(_CMD_DIR, "+village.md")
_COUNSEL_PATH       = os.path.join(_CMD_DIR, "+counsel.md")
_RETREAT_PATH       = os.path.join(_CMD_DIR, "+retreat.md")
_RETURN_PATH        = os.path.join(_CMD_DIR, "+return.md")
_HEALRATE_PATH      = os.path.join(_CMD_DIR, "+healrate.md")

_ALL_PATHS = [
    _CHAR_PATH, _CPSTATUS_PATH, _KUDOS_PATH, _SCENEBONUS_PATH,
    _BUILDING_PATH, _PCBOUNTY_PATH, _SPACEDOCK_PATH, _SHIPCREW_PATH,
    _CHARGEN_NOTES_PATH, _VILLAGE_PATH, _COUNSEL_PATH, _RETREAT_PATH,
    _RETURN_PATH, _HEALRATE_PATH,
]


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 1.  Files exist on disk
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpFilesExist(unittest.TestCase):
    def test_char_exists(self):
        self.assertTrue(os.path.isfile(_CHAR_PATH), f"Missing: {_CHAR_PATH}")

    def test_cpstatus_exists(self):
        self.assertTrue(os.path.isfile(_CPSTATUS_PATH), f"Missing: {_CPSTATUS_PATH}")

    def test_kudos_exists(self):
        self.assertTrue(os.path.isfile(_KUDOS_PATH), f"Missing: {_KUDOS_PATH}")

    def test_scenebonus_exists(self):
        self.assertTrue(os.path.isfile(_SCENEBONUS_PATH), f"Missing: {_SCENEBONUS_PATH}")

    def test_building_exists(self):
        self.assertTrue(os.path.isfile(_BUILDING_PATH), f"Missing: {_BUILDING_PATH}")

    def test_pcbounty_exists(self):
        self.assertTrue(os.path.isfile(_PCBOUNTY_PATH), f"Missing: {_PCBOUNTY_PATH}")

    def test_spacedock_exists(self):
        self.assertTrue(os.path.isfile(_SPACEDOCK_PATH), f"Missing: {_SPACEDOCK_PATH}")

    def test_shipcrew_exists(self):
        self.assertTrue(os.path.isfile(_SHIPCREW_PATH), f"Missing: {_SHIPCREW_PATH}")

    def test_chargen_notes_exists(self):
        self.assertTrue(os.path.isfile(_CHARGEN_NOTES_PATH), f"Missing: {_CHARGEN_NOTES_PATH}")

    def test_village_exists(self):
        self.assertTrue(os.path.isfile(_VILLAGE_PATH), f"Missing: {_VILLAGE_PATH}")

    def test_counsel_exists(self):
        self.assertTrue(os.path.isfile(_COUNSEL_PATH), f"Missing: {_COUNSEL_PATH}")

    def test_retreat_exists(self):
        self.assertTrue(os.path.isfile(_RETREAT_PATH), f"Missing: {_RETREAT_PATH}")

    def test_return_exists(self):
        self.assertTrue(os.path.isfile(_RETURN_PATH), f"Missing: {_RETURN_PATH}")

    def test_healrate_exists(self):
        self.assertTrue(os.path.isfile(_HEALRATE_PATH), f"Missing: {_HEALRATE_PATH}")


# ═══════════════════════════════════════════════════════════════════════════
# 2.  +char
# ═══════════════════════════════════════════════════════════════════════════

class TestCharHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_CHAR_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+char")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("char", self.entry.title.lower())

    def test_category_character(self):
        self.assertIn("character", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_charswitch(self):
        self.assertIn("charswitch", self.entry.aliases)

    def test_body_mentions_list(self):
        self.assertIn("/list", self.entry.body.lower())

    def test_body_mentions_switch(self):
        self.assertIn("/switch", self.entry.body.lower())

    def test_body_mentions_delete(self):
        self.assertIn("/delete", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 3.  +cpstatus
# ═══════════════════════════════════════════════════════════════════════════

class TestCPStatusHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_CPSTATUS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+cpstatus")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_advancement(self):
        self.assertIn("advancement", self.entry.aliases)

    def test_body_mentions_cp(self):
        self.assertIn("cp", self.entry.body.lower())

    def test_body_mentions_ticks(self):
        self.assertIn("tick", self.entry.body.lower())

    def test_body_mentions_kudos(self):
        self.assertIn("kudos", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 4.  +kudos
# ═══════════════════════════════════════════════════════════════════════════

class TestKudosHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_KUDOS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+kudos")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_kudos(self):
        self.assertIn("kudos", self.entry.aliases)

    def test_body_mentions_ticks(self):
        self.assertIn("tick", self.entry.body.lower())

    def test_body_mentions_limit(self):
        body = self.entry.body.lower()
        self.assertTrue("week" in body or "limit" in body)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 5.  +scenebonus
# ═══════════════════════════════════════════════════════════════════════════

class TestSceneBonusHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SCENEBONUS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+scenebonus")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_endscene(self):
        self.assertIn("endscene", self.entry.aliases)

    def test_body_mentions_pose(self):
        self.assertIn("pose", self.entry.body.lower())

    def test_body_mentions_tick(self):
        self.assertIn("tick", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 6.  +building
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildingHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_BUILDING_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+building")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_cities(self):
        self.assertIn("cit", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_bldg(self):
        self.assertIn("+bldg", self.entry.aliases)

    def test_body_mentions_construct(self):
        self.assertIn("construct", self.entry.body.lower())

    def test_body_mentions_residence(self):
        self.assertIn("residence", self.entry.body.lower())

    def test_body_mentions_demolish(self):
        self.assertIn("demolish", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)


# ═══════════════════════════════════════════════════════════════════════════
# 7.  +pcbounty
# ═══════════════════════════════════════════════════════════════════════════

class TestPCBountyHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_PCBOUNTY_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+pcbounty")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_economy(self):
        self.assertIn("economy", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_pb(self):
        self.assertIn("+pb", self.entry.aliases)

    def test_body_mentions_post(self):
        self.assertIn("post", self.entry.body.lower())

    def test_body_mentions_cancel(self):
        self.assertIn("cancel", self.entry.body.lower())

    def test_body_mentions_bh_guild(self):
        body = self.entry.body.lower()
        self.assertTrue("guild" in body or "bounty hunter" in body)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)


# ═══════════════════════════════════════════════════════════════════════════
# 8.  +spacedock
# ═══════════════════════════════════════════════════════════════════════════

class TestSpacedockHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SPACEDOCK_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+spacedock")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_ships(self):
        self.assertIn("ship", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_spacedock(self):
        self.assertIn("spacedock", self.entry.aliases)

    def test_body_mentions_destroyed(self):
        self.assertIn("destroyed", self.entry.body.lower())

    def test_body_mentions_repair(self):
        self.assertIn("repair", self.entry.body.lower())

    def test_body_mentions_docked(self):
        self.assertIn("dock", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 9.  +shipcrew
# ═══════════════════════════════════════════════════════════════════════════

class TestShipCrewHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SHIPCREW_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+shipcrew")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_ships(self):
        self.assertIn("ship", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_shipcrew(self):
        self.assertIn("shipcrew", self.entry.aliases)

    def test_body_mentions_add(self):
        self.assertIn("add", self.entry.body.lower())

    def test_body_mentions_remove(self):
        self.assertIn("remove", self.entry.body.lower())

    def test_body_mentions_owner(self):
        self.assertIn("owner", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 10.  +chargen_notes
# ═══════════════════════════════════════════════════════════════════════════

class TestChargenNotesHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_CHARGEN_NOTES_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+chargen_notes")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_character(self):
        self.assertIn("character", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_cgn(self):
        self.assertIn("+cgn", self.entry.aliases)

    def test_body_mentions_private(self):
        self.assertIn("private", self.entry.body.lower())

    def test_body_mentions_background(self):
        self.assertIn("background", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 11.  +village
# ═══════════════════════════════════════════════════════════════════════════

class TestVillageHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_VILLAGE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+village")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_quests(self):
        self.assertIn("quest", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_vil(self):
        self.assertIn("+vil", self.entry.aliases)

    def test_body_mentions_standing(self):
        self.assertIn("standing", self.entry.body.lower())

    def test_body_mentions_trial(self):
        self.assertIn("trial", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 12.  +counsel
# ═══════════════════════════════════════════════════════════════════════════

class TestCounselHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_COUNSEL_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+counsel")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_force(self):
        self.assertIn("force", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_counsel(self):
        self.assertIn("counsel", self.entry.aliases)

    def test_body_mentions_weight(self):
        self.assertIn("weight", self.entry.body.lower())

    def test_body_mentions_jedi(self):
        self.assertIn("jedi", self.entry.body.lower())

    def test_body_mentions_weekly_cooldown(self):
        body = self.entry.body.lower()
        self.assertTrue("week" in body or "cooldown" in body)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 13.  +retreat
# ═══════════════════════════════════════════════════════════════════════════

class TestRetreatHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_RETREAT_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+retreat")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_force(self):
        self.assertIn("force", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_retreat(self):
        self.assertIn("retreat", self.entry.aliases)

    def test_body_mentions_weight(self):
        self.assertIn("weight", self.entry.body.lower())

    def test_body_mentions_per_day(self):
        body = self.entry.body.lower()
        self.assertTrue("per day" in body or "per real" in body or "/day" in body)

    def test_body_mentions_return(self):
        self.assertIn("+return", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 14.  +return
# ═══════════════════════════════════════════════════════════════════════════

class TestReturnHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_RETURN_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+return")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_force(self):
        self.assertIn("force", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_retreat(self):
        body = self.entry.body.lower()
        self.assertTrue("retreat" in body or "+retreat" in body)

    def test_body_mentions_decay(self):
        self.assertIn("decay", self.entry.body.lower())

    def test_body_mentions_cap(self):
        self.assertIn("cap", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 15.  +healrate
# ═══════════════════════════════════════════════════════════════════════════

class TestHealRateHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_HEALRATE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+healrate")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_medical(self):
        self.assertIn("medical", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_healrate(self):
        self.assertIn("healrate", self.entry.aliases)

    def test_body_mentions_credits(self):
        self.assertIn("credit", self.entry.body.lower())

    def test_body_mentions_rate(self):
        self.assertIn("rate", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 16.  Bulk sanity — all files load cleanly
# ═══════════════════════════════════════════════════════════════════════════

class TestAllBatch8FilesLoad(unittest.TestCase):
    def test_all_load(self):
        for path in _ALL_PATHS:
            with self.subTest(path=os.path.basename(path)):
                entry = load_help_file(path, HelpEntry)
                self.assertIsNotNone(entry, f"load_help_file returned None for {path}")
                self.assertTrue(entry.key, f"Empty key for {path}")
                self.assertTrue(entry.body.strip(), f"Empty body for {path}")

    def test_all_have_examples(self):
        for path in _ALL_PATHS:
            with self.subTest(path=os.path.basename(path)):
                entry = _load(path)
                self.assertGreaterEqual(
                    len(entry.examples), 1,
                    f"No examples in {os.path.basename(path)}"
                )

    def test_no_era_violations(self):
        forbidden = ["empire", "imperial", "rebel alliance", "tie fighter",
                     "galactic civil war", "stormtrooper"]
        for path in _ALL_PATHS:
            with self.subTest(path=os.path.basename(path)):
                entry = _load(path)
                body_lower = entry.body.lower()
                for term in forbidden:
                    self.assertNotIn(
                        term, body_lower,
                        f"Era violation: '{term}' in {os.path.basename(path)}"
                    )


if __name__ == "__main__":
    unittest.main()
