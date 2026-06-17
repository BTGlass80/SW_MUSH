# -*- coding: utf-8 -*-
"""
tests/test_help_pm_commands.py — help-corpus: Padawan-Master command cluster.

Verifies 14 newly-added help files load cleanly and carry correct frontmatter:

  data/help/commands/+master.md       — Padawan views bonded Master status
  data/help/commands/+padawan.md      — Master views bonded Padawan(s) status
  data/help/commands/+bond.md         — propose / accept / decline a bond
  data/help/commands/+release.md      — Master dissolves a bond
  data/help/commands/+leave-master.md — Padawan leaves a bond
  data/help/commands/+trials.md       — view Five Trials progress
  data/help/commands/+trial.md        — Master attests a passed Trial
  data/help/commands/+endorse.md      — Master endorses a Trial attempt
  data/help/commands/+authorize.md    — Master pre-authorizes Padawan
  data/help/commands/+knight.md       — Knight promotion ceremony
  data/help/commands/+learn.md        — Padawan requests Force power training
  data/help/commands/+teach.md        — Master teaches a Force power
  data/help/commands/+spar.md         — training duel (CP grant)
  data/help/commands/+help.md         — the help command itself
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_MASTER_PATH       = os.path.join(_CMD_DIR, "+master.md")
_PADAWAN_PATH      = os.path.join(_CMD_DIR, "+padawan.md")
_BOND_PATH         = os.path.join(_CMD_DIR, "+bond.md")
_RELEASE_PATH      = os.path.join(_CMD_DIR, "+release.md")
_LEAVE_MASTER_PATH = os.path.join(_CMD_DIR, "+leave-master.md")
_TRIALS_PATH       = os.path.join(_CMD_DIR, "+trials.md")
_TRIAL_PATH        = os.path.join(_CMD_DIR, "+trial.md")
_ENDORSE_PATH      = os.path.join(_CMD_DIR, "+endorse.md")
_AUTHORIZE_PATH    = os.path.join(_CMD_DIR, "+authorize.md")
_KNIGHT_PATH       = os.path.join(_CMD_DIR, "+knight.md")
_LEARN_PATH        = os.path.join(_CMD_DIR, "+learn.md")
_TEACH_PATH        = os.path.join(_CMD_DIR, "+teach.md")
_SPAR_PATH         = os.path.join(_CMD_DIR, "+spar.md")
_HELP_PATH         = os.path.join(_CMD_DIR, "+help.md")

_ALL_PATHS = [
    _MASTER_PATH, _PADAWAN_PATH, _BOND_PATH, _RELEASE_PATH,
    _LEAVE_MASTER_PATH, _TRIALS_PATH, _TRIAL_PATH, _ENDORSE_PATH,
    _AUTHORIZE_PATH, _KNIGHT_PATH, _LEARN_PATH, _TEACH_PATH,
    _SPAR_PATH, _HELP_PATH,
]

_ERA_FORBIDDEN = [
    "empire", "imperial", "rebel alliance", "tie fighter",
    "galactic civil war", "stormtrooper",
]


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 1.  +master
# ═══════════════════════════════════════════════════════════════════════════

class TestMasterHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_MASTER_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+master")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_pm(self):
        self.assertIn("padawan", self.entry.category.lower())

    def test_aliases_include_master(self):
        self.assertIn("master", self.entry.aliases)

    def test_body_mentions_bond(self):
        self.assertIn("bond", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 2.  +padawan
# ═══════════════════════════════════════════════════════════════════════════

class TestPadawanHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_PADAWAN_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+padawan")

    def test_category_pm(self):
        self.assertIn("padawan", self.entry.category.lower())

    def test_aliases_include_padawan(self):
        self.assertIn("padawan", self.entry.aliases)

    def test_body_mentions_bond(self):
        self.assertIn("bond", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 3.  +bond
# ═══════════════════════════════════════════════════════════════════════════

class TestBondHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_BOND_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+bond")

    def test_category_pm(self):
        self.assertIn("padawan", self.entry.category.lower())

    def test_body_mentions_accept(self):
        self.assertIn("accept", self.entry.body.lower())

    def test_body_mentions_propose(self):
        self.assertIn("propose", self.entry.body.lower())

    def test_examples_multiple(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 4.  +release
# ═══════════════════════════════════════════════════════════════════════════

class TestReleaseHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_RELEASE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+release")

    def test_body_mentions_dissolve(self):
        self.assertIn("dissolve", self.entry.body.lower())

    def test_body_mentions_reason(self):
        self.assertIn("reason", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 5.  +leave-master
# ═══════════════════════════════════════════════════════════════════════════

class TestLeaveMasterHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_LEAVE_MASTER_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+leave-master")

    def test_body_mentions_reason(self):
        self.assertIn("reason", self.entry.body.lower())

    def test_body_mentions_padawan(self):
        self.assertIn("padawan", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 6.  +trials
# ═══════════════════════════════════════════════════════════════════════════

class TestTrialsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_TRIALS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+trials")

    def test_body_mentions_five(self):
        self.assertIn("five", self.entry.body.lower())

    def test_body_mentions_skill_trial(self):
        self.assertIn("skill", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 7.  +trial
# ═══════════════════════════════════════════════════════════════════════════

class TestTrialHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_TRIAL_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+trial")

    def test_body_mentions_attest(self):
        self.assertIn("attest", self.entry.body.lower())

    def test_body_mentions_endorsement(self):
        self.assertIn("endorse", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 8.  +endorse
# ═══════════════════════════════════════════════════════════════════════════

class TestEndorseHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_ENDORSE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+endorse")

    def test_body_mentions_consumed(self):
        self.assertIn("consum", self.entry.body.lower())

    def test_body_mentions_auto_fail(self):
        self.assertIn("auto-fail", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 9.  +authorize
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthorizeHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_AUTHORIZE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+authorize")

    def test_body_mentions_offworld(self):
        self.assertIn("offworld", self.entry.body.lower())

    def test_body_mentions_trials_category(self):
        self.assertIn("trials", self.entry.body.lower())

    def test_body_mentions_standing(self):
        self.assertIn("standing", self.entry.body.lower())

    def test_examples_multiple(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)


# ═══════════════════════════════════════════════════════════════════════════
# 10.  +knight
# ═══════════════════════════════════════════════════════════════════════════

class TestKnightHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_KNIGHT_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+knight")

    def test_body_mentions_force_point(self):
        self.assertIn("force point", self.entry.body.lower())

    def test_body_mentions_five_trials(self):
        self.assertIn("five trials", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 11.  +learn
# ═══════════════════════════════════════════════════════════════════════════

class TestLearnHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_LEARN_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+learn")

    def test_body_mentions_master(self):
        self.assertIn("master", self.entry.body.lower())

    def test_body_mentions_teach(self):
        self.assertIn("teach", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 12.  +teach
# ═══════════════════════════════════════════════════════════════════════════

class TestTeachHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_TEACH_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+teach")

    def test_body_mentions_cp(self):
        self.assertIn("character point", self.entry.body.lower())

    def test_body_mentions_same_room(self):
        self.assertIn("same room", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 13.  +spar
# ═══════════════════════════════════════════════════════════════════════════

class TestSparHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SPAR_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+spar")

    def test_body_mentions_cooldown(self):
        self.assertIn("cooldown", self.entry.body.lower())

    def test_body_mentions_cp(self):
        self.assertIn("cp", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 14.  +help
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_HELP_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+help")

    def test_access_level_anyone(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_search(self):
        self.assertIn("search", self.entry.body.lower())

    def test_examples_multiple(self):
        self.assertGreaterEqual(len(self.entry.examples), 3)


# ═══════════════════════════════════════════════════════════════════════════
# 15.  Bulk sanity — all files load cleanly
# ═══════════════════════════════════════════════════════════════════════════

class TestAllPMFilesLoad(unittest.TestCase):
    def test_all_load(self):
        for path in _ALL_PATHS:
            with self.subTest(path=os.path.basename(path)):
                entry = load_help_file(path, HelpEntry)
                self.assertIsNotNone(
                    entry, f"load_help_file returned None for {path}"
                )
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
        for path in _ALL_PATHS:
            with self.subTest(path=os.path.basename(path)):
                entry = _load(path)
                body_lower = entry.body.lower()
                for term in _ERA_FORBIDDEN:
                    self.assertNotIn(
                        term, body_lower,
                        f"Era violation: '{term}' in {os.path.basename(path)}"
                    )

    def test_all_keys_match_filenames(self):
        for path in _ALL_PATHS:
            with self.subTest(path=os.path.basename(path)):
                entry = _load(path)
                fname = os.path.basename(path).replace(".md", "")
                self.assertEqual(
                    entry.key, fname,
                    f"Key '{entry.key}' doesn't match filename '{fname}'"
                )


if __name__ == "__main__":
    unittest.main()
