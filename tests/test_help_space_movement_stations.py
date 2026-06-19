"""Help corpus: space movement + crew station alias coverage.

QA help-sweep (2026-06-19): six ship commands returned 'No help found' because
they were not covered by any help-file alias:
  launch / land / hyperspace  — pilot-gated movement verbs
  copilot / navigator         — crew station verbs (added to +pilot.md)
  engineer                    — crew station verb (added to +bridge.md)

Fix: aliases added to data/help/commands/+pilot.md and +bridge.md; +pilot.md
body extended with LAUNCH / LAND / HYPERSPACE and CREW STATIONS sections.

Tests confirm:
  1. +pilot entry resolves for all six new aliases via the help loader.
  2. +bridge entry resolves for engineer / eng.
  3. The +pilot body mentions launch, land, and hyperspace.
  4. The +bridge body mentions the engineer station.
"""
from __future__ import annotations

import os
import unittest

DATA_HELP_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "help")


def _load_entries():
    from engine.help_loader import load_help_directory
    from data.help_topics import HelpEntry
    return {e.key: e for e in load_help_directory(DATA_HELP_ROOT, HelpEntry)}


class TestSpaceMovementStationsHelp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.entries = _load_entries()
        # Build alias → key mapping for lookup tests
        cls.alias_map: dict[str, str] = {}
        for key, entry in cls.entries.items():
            for alias in (entry.aliases or []):
                cls.alias_map[alias.lower()] = key

    # ── +pilot.md resolves for movement aliases ────────────────────────

    def test_launch_alias_resolves_to_pilot(self):
        self.assertEqual(self.alias_map.get("launch"), "+pilot",
                         "'launch' alias not pointing to +pilot entry")

    def test_takeoff_alias_resolves_to_pilot(self):
        self.assertEqual(self.alias_map.get("takeoff"), "+pilot",
                         "'takeoff' alias not pointing to +pilot entry")

    def test_land_alias_resolves_to_pilot(self):
        self.assertEqual(self.alias_map.get("land"), "+pilot",
                         "'land' alias not pointing to +pilot entry")

    def test_dock_alias_resolves_to_pilot(self):
        self.assertEqual(self.alias_map.get("dock"), "+pilot",
                         "'dock' alias not pointing to +pilot entry")

    def test_hyperspace_alias_resolves_to_hyperdrive(self):
        # 'hyperspace' and 'jump' were already covered by the hyperdrive topic —
        # they should continue to resolve there (not +pilot).
        self.assertEqual(self.alias_map.get("hyperspace"), "hyperdrive",
                         "'hyperspace' alias not pointing to hyperdrive entry")

    def test_jump_alias_resolves_to_hyperdrive(self):
        self.assertEqual(self.alias_map.get("jump"), "hyperdrive",
                         "'jump' alias not pointing to hyperdrive entry")

    def test_hyper_alias_resolves_to_hyperdrive(self):
        # 'hyper' short form — added to hyperdrive topic aliases this drop.
        self.assertEqual(self.alias_map.get("hyper"), "hyperdrive",
                         "'hyper' alias not pointing to hyperdrive entry")

    # ── +pilot.md resolves for crew station aliases ────────────────────

    def test_copilot_alias_resolves_to_pilot(self):
        self.assertEqual(self.alias_map.get("copilot"), "+pilot",
                         "'copilot' alias not pointing to +pilot entry")

    def test_copiloting_alias_resolves_to_pilot(self):
        self.assertEqual(self.alias_map.get("copiloting"), "+pilot",
                         "'copiloting' alias not pointing to +pilot entry")

    def test_navigator_alias_resolves_to_pilot(self):
        self.assertEqual(self.alias_map.get("navigator"), "+pilot",
                         "'navigator' alias not pointing to +pilot entry")

    def test_nav_alias_resolves_to_pilot(self):
        self.assertEqual(self.alias_map.get("nav"), "+pilot",
                         "'nav' alias not pointing to +pilot entry")

    # ── +bridge.md resolves for engineer alias ────────────────────────

    def test_engineer_alias_resolves_to_bridge(self):
        self.assertEqual(self.alias_map.get("engineer"), "+bridge",
                         "'engineer' alias not pointing to +bridge entry")

    def test_eng_alias_resolves_to_bridge(self):
        self.assertEqual(self.alias_map.get("eng"), "+bridge",
                         "'eng' alias not pointing to +bridge entry")

    # ── Body content checks ────────────────────────────────────────────

    def test_pilot_body_mentions_launch(self):
        entry = self.entries.get("+pilot")
        self.assertIsNotNone(entry, "+pilot entry missing")
        self.assertIn("launch", entry.body.lower(),
                      "+pilot body does not mention 'launch'")

    def test_pilot_body_mentions_land(self):
        entry = self.entries.get("+pilot")
        self.assertIsNotNone(entry, "+pilot entry missing")
        self.assertIn("land", entry.body.lower(),
                      "+pilot body does not mention 'land'")

    def test_pilot_body_mentions_hyperspace(self):
        entry = self.entries.get("+pilot")
        self.assertIsNotNone(entry, "+pilot entry missing")
        self.assertIn("hyperspace", entry.body.lower(),
                      "+pilot body does not mention 'hyperspace'")

    def test_pilot_body_mentions_copilot(self):
        entry = self.entries.get("+pilot")
        self.assertIsNotNone(entry, "+pilot entry missing")
        self.assertIn("copilot", entry.body.lower(),
                      "+pilot body does not mention 'copilot'")

    def test_pilot_body_mentions_navigator(self):
        entry = self.entries.get("+pilot")
        self.assertIsNotNone(entry, "+pilot entry missing")
        self.assertIn("navigator", entry.body.lower(),
                      "+pilot body does not mention 'navigator'")

    def test_bridge_body_mentions_engineer(self):
        entry = self.entries.get("+bridge")
        self.assertIsNotNone(entry, "+bridge entry missing")
        self.assertIn("engineer", entry.body.lower(),
                      "+bridge body does not mention 'engineer'")

    # ── No regressions on existing aliases ────────────────────────────

    def test_pilot_existing_alias_still_resolves(self):
        self.assertEqual(self.alias_map.get("evade"), "+pilot",
                         "Regression: 'evade' alias broken for +pilot")

    def test_bridge_existing_alias_still_resolves(self):
        self.assertEqual(self.alias_map.get("commander"), "+bridge",
                         "Regression: 'commander' alias broken for +bridge")


if __name__ == "__main__":
    unittest.main()
