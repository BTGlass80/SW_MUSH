"""Help corpus: +spacerquest, debt, travel — QA help-sweep addition.

Three commands from the From Dust to Stars new-player quest chain were
missing rich help entries and only had auto-generated stubs:
  +spacerquest  — quest-chain progress display
  debt          — Hutt Cartel debt management
  travel        — interplanetary passage booking (Phases 2-3 only)

Tests confirm:
  1. All three help files parse and load without error.
  2. Each entry has a non-empty summary, body, and examples list.
  3. Canonical aliases (quest / +debt / passage) resolve to the right key.
  4. The +spacerquest entry cross-links to debt and travel via see_also.
"""
from __future__ import annotations

import os
import unittest

DATA_HELP_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "help")


def _load_entries():
    from engine.help_loader import load_help_directory
    from data.help_topics import HelpEntry
    return {e.key: e for e in load_help_directory(DATA_HELP_ROOT, HelpEntry)}


class TestSpacerQuestHelpFiles(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.entries = _load_entries()

    # ── Existence ──────────────────────────────────────────────────────

    def test_spacerquest_entry_exists(self):
        self.assertIn("+spacerquest", self.entries,
                      "+spacerquest help file not found")

    def test_debt_entry_exists(self):
        self.assertIn("debt", self.entries,
                      "debt help file not found")

    def test_travel_entry_exists(self):
        self.assertIn("travel", self.entries,
                      "travel help file not found")

    # ── Non-empty content ──────────────────────────────────────────────

    def test_spacerquest_has_summary(self):
        e = self.entries["+spacerquest"]
        self.assertTrue(e.summary.strip(), "+spacerquest summary is empty")

    def test_spacerquest_has_body(self):
        e = self.entries["+spacerquest"]
        self.assertGreater(len(e.body.strip()), 50,
                           "+spacerquest body too short or missing")

    def test_spacerquest_has_examples(self):
        e = self.entries["+spacerquest"]
        self.assertGreater(len(e.examples), 0,
                           "+spacerquest has no examples")

    def test_debt_has_summary(self):
        e = self.entries["debt"]
        self.assertTrue(e.summary.strip(), "debt summary is empty")

    def test_debt_has_body(self):
        e = self.entries["debt"]
        self.assertGreater(len(e.body.strip()), 50,
                           "debt body too short or missing")

    def test_debt_has_examples(self):
        e = self.entries["debt"]
        self.assertGreater(len(e.examples), 0,
                           "debt has no examples")

    def test_travel_has_summary(self):
        e = self.entries["travel"]
        self.assertTrue(e.summary.strip(), "travel summary is empty")

    def test_travel_has_body(self):
        e = self.entries["travel"]
        self.assertGreater(len(e.body.strip()), 50,
                           "travel body too short or missing")

    def test_travel_has_examples(self):
        e = self.entries["travel"]
        self.assertGreater(len(e.examples), 0,
                           "travel has no examples")

    # ── Aliases resolve correctly ──────────────────────────────────────

    def test_spacerquest_alias_quest(self):
        e = self.entries["+spacerquest"]
        self.assertIn("quest", [a.lower() for a in e.aliases],
                      "'quest' not listed as alias of +spacerquest")

    def test_spacerquest_alias_fdts(self):
        e = self.entries["+spacerquest"]
        self.assertIn("+fdts", [a.lower() for a in e.aliases],
                      "'+fdts' not listed as alias of +spacerquest")

    def test_debt_alias_plus_debt(self):
        e = self.entries["debt"]
        self.assertIn("+debt", [a.lower() for a in e.aliases],
                      "'+debt' not listed as alias of debt")

    def test_travel_alias_passage(self):
        e = self.entries["travel"]
        self.assertIn("passage", [a.lower() for a in e.aliases],
                      "'passage' not listed as alias of travel")

    # ── see_also cross-links ───────────────────────────────────────────

    def test_spacerquest_see_also_debt(self):
        e = self.entries["+spacerquest"]
        self.assertIn("debt", e.see_also,
                      "+spacerquest see_also does not include 'debt'")

    def test_spacerquest_see_also_travel(self):
        e = self.entries["+spacerquest"]
        self.assertIn("travel", e.see_also,
                      "+spacerquest see_also does not include 'travel'")

    # ── Category sanity ───────────────────────────────────────────────

    def test_spacerquest_category_set(self):
        e = self.entries["+spacerquest"]
        self.assertTrue(e.category.strip(),
                        "+spacerquest category is empty")

    def test_debt_category_set(self):
        e = self.entries["debt"]
        self.assertTrue(e.category.strip(),
                        "debt category is empty")

    def test_travel_category_set(self):
        e = self.entries["travel"]
        self.assertTrue(e.category.strip(),
                        "travel category is empty")


if __name__ == "__main__":
    unittest.main()
