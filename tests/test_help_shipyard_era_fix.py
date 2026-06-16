# -*- coding: utf-8 -*-
"""
tests/test_help_shipyard_era_fix.py — help-corpus batch 9 + portal era-fix.

Verifies:
  data/help/commands/+shipyard.md  — Kuat Drive Yards ship brokerage
  static/portal.html               — era string is Clone Wars, not GCW
"""

from __future__ import annotations

import os
import re
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")
_SHIPYARD_PATH = os.path.join(_CMD_DIR, "+shipyard.md")
_PORTAL_PATH = os.path.join(_REPO_ROOT, "static", "portal.html")


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


class TestShipyardHelpFile(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(os.path.isfile(_SHIPYARD_PATH),
                        f"Missing: {_SHIPYARD_PATH}")

    def test_loads_cleanly(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertIsNotNone(entry)

    def test_key(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertEqual(entry.key, "+shipyard")

    def test_title_set(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertTrue(entry.title, "title should not be empty")

    def test_category_ships(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertIn("ship", entry.category.lower(),
                      "category should reference ships")

    def test_summary_set(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertTrue(entry.summary, "summary should not be empty")

    def test_aliases_include_broker(self):
        entry = _load(_SHIPYARD_PATH)
        aliases_lower = [a.lower() for a in (entry.aliases or [])]
        self.assertIn("+broker", aliases_lower)

    def test_body_mentions_kuat(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertIn("kuat", entry.body.lower())

    def test_body_mentions_buy(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertIn("buy", entry.body.lower())

    def test_no_imperial_era_strings(self):
        entry = _load(_SHIPYARD_PATH)
        body_lower = entry.body.lower()
        forbidden = ["galactic civil war", "imperial era", "rebel era"]
        for f in forbidden:
            self.assertNotIn(f, body_lower, f"Forbidden era string: {f!r}")

    def test_see_also_set(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertTrue(entry.see_also, "see_also should not be empty")

    def test_examples_set(self):
        entry = _load(_SHIPYARD_PATH)
        self.assertTrue(entry.examples, "examples should not be empty")


class TestPortalEraFix(unittest.TestCase):
    def _read_portal(self) -> str:
        with open(_PORTAL_PATH, encoding="utf-8") as f:
            return f.read()

    def test_portal_exists(self):
        self.assertTrue(os.path.isfile(_PORTAL_PATH),
                        f"Missing: {_PORTAL_PATH}")

    def test_no_gcw_era_string(self):
        html = self._read_portal()
        self.assertNotIn("GALACTIC CIVIL WAR ERA", html,
                         "B3 era violation: 'GALACTIC CIVIL WAR ERA' must not appear in production strings")

    def test_clone_wars_era_string_present(self):
        html = self._read_portal()
        self.assertIn("CLONE WARS ERA", html,
                      "Expected 'CLONE WARS ERA' subtitle in portal.html landing hero")

    def test_weg_revised_still_present(self):
        html = self._read_portal()
        self.assertIn("WEG REVISED", html,
                      "WEG REVISED & EXPANDED should still be in the subtitle")
