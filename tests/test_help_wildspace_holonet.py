# -*- coding: utf-8 -*-
"""
tests/test_help_wildspace_holonet.py — help-corpus completeness drop.

Verifies that four newly-added help files load cleanly and carry the
expected frontmatter:

  data/help/commands/+holonet.md  — HoloNet browser command
  data/help/commands/mine.md      — wildspace mining caches
  data/help/commands/salvage.md   — derelict recovery
  data/help/commands/harvest.md   — faction caches (space) / Survival (ground)

Strategy mirrors tests/test_cities_help_topics.py: exercise
load_help_file end-to-end against the real on-disk files so any YAML
typo or missing required field is caught early.
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_HOLONET_PATH = os.path.join(_CMD_DIR, "+holonet.md")
_MINE_PATH    = os.path.join(_CMD_DIR, "mine.md")
_SALVAGE_PATH = os.path.join(_CMD_DIR, "salvage.md")
_HARVEST_PATH = os.path.join(_CMD_DIR, "harvest.md")


# ── helpers ──────────────────────────────────────────────────────────────────

def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ══════════════════════════════════════════════════════════════════════════════
# 1.  Files exist on disk
# ══════════════════════════════════════════════════════════════════════════════

class TestHelpFilesExist(unittest.TestCase):
    def test_holonet_exists(self):
        self.assertTrue(os.path.isfile(_HOLONET_PATH), f"Missing: {_HOLONET_PATH}")

    def test_mine_exists(self):
        self.assertTrue(os.path.isfile(_MINE_PATH), f"Missing: {_MINE_PATH}")

    def test_salvage_exists(self):
        self.assertTrue(os.path.isfile(_SALVAGE_PATH), f"Missing: {_SALVAGE_PATH}")

    def test_harvest_exists(self):
        self.assertTrue(os.path.isfile(_HARVEST_PATH), f"Missing: {_HARVEST_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
# 2.  +holonet help
# ══════════════════════════════════════════════════════════════════════════════

class TestHolonetHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_HOLONET_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+holonet")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("holonet", self.entry.title.lower())

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_holonet_alias(self):
        self.assertIn("holonet", self.entry.aliases)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)
        for ex in self.entry.examples:
            self.assertIn("cmd", ex)
            self.assertIn("description", ex)

    def test_body_mentions_web_client(self):
        self.assertIn("web client", self.entry.body.lower())

    def test_body_mentions_telnet(self):
        self.assertIn("telnet", self.entry.body.lower())

    def test_body_mentions_world_events(self):
        self.assertIn("world event", self.entry.body.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 3.  mine help
# ══════════════════════════════════════════════════════════════════════════════

class TestMineHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_MINE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "mine")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("mine", self.entry.title.lower())

    def test_category_ships(self):
        self.assertIn("ship", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_see_also_includes_salvage(self):
        self.assertIn("salvage", self.entry.see_also)

    def test_examples_cover_both_forms(self):
        self.assertGreaterEqual(len(self.entry.examples), 2)
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(
            any("mine" == c.strip() for c in cmds),
            "mine help missing bare 'mine' example",
        )
        self.assertTrue(
            any(c.strip().startswith("mine ") for c in cmds),
            "mine help missing 'mine <id>' example",
        )

    def test_body_mentions_wildspace(self):
        self.assertIn("wildspace", self.entry.body.lower())

    def test_body_mentions_cooldown(self):
        self.assertIn("cooldown", self.entry.body.lower())

    def test_body_mentions_resources(self):
        body_lower = self.entry.body.lower()
        for rtype in ("metal", "energy", "composite", "rare"):
            self.assertIn(rtype, body_lower, f"mine body missing resource type: {rtype!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 4.  salvage help
# ══════════════════════════════════════════════════════════════════════════════

class TestSalvageHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_SALVAGE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "salvage")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("salvage", self.entry.title.lower())

    def test_category_ships(self):
        self.assertIn("ship", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_see_also_includes_mine(self):
        self.assertIn("mine", self.entry.see_also)

    def test_see_also_includes_anomalies(self):
        self.assertIn("anomalies", self.entry.see_also)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_derelict(self):
        self.assertIn("derelict", self.entry.body.lower())

    def test_body_mentions_skill_check(self):
        self.assertIn("skill", self.entry.body.lower())

    def test_body_mentions_salvage_arm(self):
        self.assertIn("salvage arm", self.entry.body.lower())

    def test_body_mentions_open_space(self):
        self.assertIn("open space", self.entry.body.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 5.  harvest help
# ══════════════════════════════════════════════════════════════════════════════

class TestHarvestHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_HARVEST_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "harvest")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("harvest", self.entry.title.lower())

    def test_category_economy(self):
        self.assertIn("economy", self.entry.category.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_see_also_includes_mine_and_salvage(self):
        self.assertIn("mine", self.entry.see_also)
        self.assertIn("salvage", self.entry.see_also)

    def test_see_also_includes_wilderness(self):
        self.assertIn("wilderness", self.entry.see_also)

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)

    def test_body_mentions_space_mode(self):
        body_lower = self.entry.body.lower()
        self.assertIn("faction cache", body_lower)

    def test_body_mentions_ground_mode(self):
        self.assertIn("survival", self.entry.body.lower())

    def test_body_mentions_cooldown(self):
        self.assertIn("cooldown", self.entry.body.lower())

    def test_body_mentions_turf_tax(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "15%" in body_lower or "turf" in body_lower or "treasury" in body_lower,
            "harvest body should mention turf tax mechanic",
        )

    def test_body_distinguishes_space_and_ground(self):
        body_lower = self.entry.body.lower()
        self.assertIn("space mode", body_lower)
        self.assertIn("ground mode", body_lower)


# ══════════════════════════════════════════════════════════════════════════════
# 6.  Cross-file consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossConsistency(unittest.TestCase):
    """Distinct keys and bidirectional see_also cross-links."""

    @classmethod
    def setUpClass(cls):
        cls.holonet = _load(_HOLONET_PATH)
        cls.mine    = _load(_MINE_PATH)
        cls.salvage = _load(_SALVAGE_PATH)
        cls.harvest = _load(_HARVEST_PATH)

    def test_distinct_keys(self):
        keys = {self.holonet.key, self.mine.key, self.salvage.key, self.harvest.key}
        self.assertEqual(len(keys), 4, f"Duplicate keys among help files: {keys}")

    def test_mine_and_salvage_cross_link(self):
        self.assertIn("salvage", self.mine.see_also)
        self.assertIn("mine", self.salvage.see_also)

    def test_harvest_links_mine_and_salvage(self):
        self.assertIn("mine", self.harvest.see_also)
        self.assertIn("salvage", self.harvest.see_also)


if __name__ == "__main__":
    unittest.main()
