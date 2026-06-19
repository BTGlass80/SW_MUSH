# -*- coding: utf-8 -*-
"""
tests/test_help_chain_mastery_lockpick.py

Help-corpus completeness drop: verifies that the four newly-added
command help files load cleanly and carry expected frontmatter, and
that the +bounties alias is now resolved by HelpManager.

  data/help/commands/chain.md       — tutorial chain interaction
  data/help/commands/mastery.md     — master-trainer T5 questlines
  data/help/commands/lockpick.md    — housing lock-picking
  data/help/commands/pickpocket.md  — credit theft from sleeping chars

Also verifies that +bounties resolves via the +bounty.md alias list.
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry, HelpManager
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_CHAIN_PATH = os.path.join(_CMD_DIR, "chain.md")
_MASTERY_PATH = os.path.join(_CMD_DIR, "mastery.md")
_LOCKPICK_PATH = os.path.join(_CMD_DIR, "lockpick.md")
_PICKPOCKET_PATH = os.path.join(_CMD_DIR, "pickpocket.md")
_BOUNTY_PATH = os.path.join(_CMD_DIR, "+bounty.md")


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ── 1. Files exist ────────────────────────────────────────────────────────────

class TestHelpFilesExist(unittest.TestCase):
    def test_chain_exists(self):
        self.assertTrue(os.path.isfile(_CHAIN_PATH), f"Missing: {_CHAIN_PATH}")

    def test_mastery_exists(self):
        self.assertTrue(os.path.isfile(_MASTERY_PATH), f"Missing: {_MASTERY_PATH}")

    def test_lockpick_exists(self):
        self.assertTrue(os.path.isfile(_LOCKPICK_PATH), f"Missing: {_LOCKPICK_PATH}")

    def test_pickpocket_exists(self):
        self.assertTrue(os.path.isfile(_PICKPOCKET_PATH), f"Missing: {_PICKPOCKET_PATH}")


# ── 2. Files load cleanly ─────────────────────────────────────────────────────

class TestHelpFilesLoad(unittest.TestCase):
    def test_chain_loads(self):
        e = _load(_CHAIN_PATH)
        self.assertEqual(e.key, "chain")
        self.assertIn("Tutorial", e.title)
        self.assertTrue(e.body.strip())

    def test_mastery_loads(self):
        e = _load(_MASTERY_PATH)
        self.assertEqual(e.key, "mastery")
        self.assertIn("Mastery", e.title)
        self.assertTrue(e.body.strip())

    def test_lockpick_loads(self):
        e = _load(_LOCKPICK_PATH)
        self.assertEqual(e.key, "lockpick")
        self.assertIn("Lockpick", e.title)
        self.assertTrue(e.body.strip())

    def test_pickpocket_loads(self):
        e = _load(_PICKPOCKET_PATH)
        self.assertEqual(e.key, "pickpocket")
        self.assertIn("Pickpocket", e.title)
        self.assertTrue(e.body.strip())


# ── 3. Expected frontmatter fields ────────────────────────────────────────────

class TestHelpFrontmatter(unittest.TestCase):
    def test_chain_aliases_include_chainstatus(self):
        e = _load(_CHAIN_PATH)
        self.assertIn("chainstatus", e.aliases)

    def test_mastery_aliases_include_masteries(self):
        e = _load(_MASTERY_PATH)
        self.assertIn("masteries", e.aliases)

    def test_lockpick_aliases_include_pick(self):
        e = _load(_LOCKPICK_PATH)
        self.assertIn("pick", e.aliases)

    def test_pickpocket_aliases_include_pp(self):
        e = _load(_PICKPOCKET_PATH)
        self.assertIn("pp", e.aliases)

    def test_chain_has_see_also(self):
        e = _load(_CHAIN_PATH)
        self.assertTrue(e.see_also)

    def test_mastery_has_see_also(self):
        e = _load(_MASTERY_PATH)
        self.assertTrue(e.see_also)


# ── 4. HelpManager resolves lookups ──────────────────────────────────────────

class TestHelpManagerResolution(unittest.TestCase):
    def setUp(self):
        self.mgr = HelpManager()
        self.mgr.load_markdown_files()

    def test_chain_resolves(self):
        e = self.mgr.get("chain")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "chain")

    def test_mastery_resolves(self):
        e = self.mgr.get("mastery")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "mastery")

    def test_lockpick_resolves(self):
        e = self.mgr.get("lockpick")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "lockpick")

    def test_pick_alias_resolves_to_lockpick(self):
        e = self.mgr.get("pick")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "lockpick")

    def test_pickpocket_resolves(self):
        e = self.mgr.get("pickpocket")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "pickpocket")

    def test_pp_alias_resolves_to_pickpocket(self):
        e = self.mgr.get("pp")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "pickpocket")

    def test_bounties_plus_prefix_resolves(self):
        """Regression: +bounties (with + prefix) must resolve via +bounty aliases."""
        e = self.mgr.get("+bounties")
        self.assertIsNotNone(e, "+bounties should resolve via +bounty aliases")
        self.assertEqual(e.key, "+bounty")

    def test_masteries_alias_resolves(self):
        e = self.mgr.get("masteries")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "mastery")


if __name__ == "__main__":
    unittest.main()
