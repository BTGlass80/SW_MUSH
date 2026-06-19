# -*- coding: utf-8 -*-
"""
tests/test_help_narrative_admin_and_crossrefs.py

Help-corpus: @narrative admin entry + broken cross-reference repairs.

New entries / alias additions in this drop:
  - data/help/commands/@narrative.md  — admin @narrative command (closes
    the '+help @narrative' dead-link in +quest.md)
  - encounter.md aliases += encounters
  - +ship.md aliases   += ships
  - +craft.md aliases  += trainers
"""
import unittest


def _make_mgr():
    from data.help_topics import HelpEntry, HelpManager
    from engine.help_loader import load_help_directory
    mgr = HelpManager()
    for e in load_help_directory("data/help", HelpEntry):
        mgr.register(e)
    return mgr


class TestNarrativeHelpEntry(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mgr = _make_mgr()
        cls.entry = cls.mgr.get("@narrative")

    def test_entry_exists(self):
        self.assertIsNotNone(self.entry, "@narrative help entry must exist")

    def test_key(self):
        self.assertEqual(self.entry.key, "@narrative")

    def test_alias_narr(self):
        e = self.mgr.get("@narr")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "@narrative")

    def test_admin_access_level(self):
        self.assertEqual(self.entry.access_level, 3,
                         "@narrative is admin-only (access_level 3)")

    def test_category_admin(self):
        self.assertIn("Admin", self.entry.category)

    def test_body_covers_subcommands(self):
        body = self.entry.body.lower()
        for sub in ("status", "view", "update", "reset", "log", "enable", "disable", "runnow"):
            self.assertIn(sub, body, f"Body missing subcommand: {sub!r}")

    def test_summary_non_empty(self):
        self.assertTrue(len(self.entry.summary) > 20)


class TestHelpCrossRefs(unittest.TestCase):
    """Cross-reference lookups that were broken before this drop."""

    @classmethod
    def setUpClass(cls):
        cls.mgr = _make_mgr()

    def _assert_resolves(self, name, expected_key):
        e = self.mgr.get(name)
        self.assertIsNotNone(e, f"+help {name!r} must resolve (broken cross-ref)")
        self.assertEqual(e.key, expected_key,
                         f"+help {name!r} resolved to {e.key!r}, expected {expected_key!r}")

    def test_encounters_resolves(self):
        self._assert_resolves("encounters", "encounter")

    def test_ships_resolves(self):
        self._assert_resolves("ships", "+ship")

    def test_trainers_resolves(self):
        self._assert_resolves("trainers", "+craft")

    def test_narrative_resolves(self):
        self._assert_resolves("@narrative", "@narrative")

    def test_engineer_resolves(self):
        e = self.mgr.get("engineer")
        self.assertIsNotNone(e, "+help engineer must resolve via +bridge aliases")

    def test_reputation_resolves(self):
        e = self.mgr.get("reputation")
        self.assertIsNotNone(e, "+help reputation must resolve via +reputation")

    def test_range_resolves(self):
        e = self.mgr.get("range")
        self.assertIsNotNone(e, "+help range must resolve via +combat aliases")


if __name__ == "__main__":
    unittest.main()
