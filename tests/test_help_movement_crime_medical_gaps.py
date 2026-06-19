# -*- coding: utf-8 -*-
"""
tests/test_help_movement_crime_medical_gaps.py — help-corpus gap coverage:
movement, think, coords, stim/stimaccept, steal, forcedoor, escape.

Commands covered:
  move / north / south / east / west / n / s / e / w
    / ne / nw / se / sw / up / down / u / d / enter / leave  → move.md
  think                                                        → think.md
  coords / coordinates                                         → coords.md
  stim / stimaccept / saccept                                  → stim.md
  steal / pilfer / swipe                                       → steal.md
  forcedoor / breakin                                          → forcedoor.md
  escape / struggle                                            → escape.md
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry, HelpManager
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")


def _path(fname: str) -> str:
    return os.path.join(_CMD_DIR, fname)


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


def _manager() -> HelpManager:
    mgr = HelpManager()
    mgr.load_markdown_files(os.path.join(_REPO_ROOT, "data", "help"))
    return mgr


# ═══════════════════════════════════════════════════════════════════════════
# 1. File existence
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpMovementCrimeMedicalFilesExist(unittest.TestCase):
    def test_move_exists(self):
        self.assertTrue(os.path.isfile(_path("move.md")))

    def test_think_exists(self):
        self.assertTrue(os.path.isfile(_path("think.md")))

    def test_coords_exists(self):
        self.assertTrue(os.path.isfile(_path("coords.md")))

    def test_stim_exists(self):
        self.assertTrue(os.path.isfile(_path("stim.md")))

    def test_steal_exists(self):
        self.assertTrue(os.path.isfile(_path("steal.md")))

    def test_forcedoor_exists(self):
        self.assertTrue(os.path.isfile(_path("forcedoor.md")))

    def test_escape_exists(self):
        self.assertTrue(os.path.isfile(_path("escape.md")))


# ═══════════════════════════════════════════════════════════════════════════
# 2. Frontmatter keys and aliases
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpMovementCrimeMedicalFrontmatter(unittest.TestCase):
    def test_move_key(self):
        e = _load(_path("move.md"))
        self.assertEqual(e.key, "move")

    def test_think_key(self):
        e = _load(_path("think.md"))
        self.assertEqual(e.key, "think")

    def test_coords_key(self):
        e = _load(_path("coords.md"))
        self.assertEqual(e.key, "coords")

    def test_stim_key(self):
        e = _load(_path("stim.md"))
        self.assertEqual(e.key, "stim")

    def test_steal_key(self):
        e = _load(_path("steal.md"))
        self.assertEqual(e.key, "steal")

    def test_forcedoor_key(self):
        e = _load(_path("forcedoor.md"))
        self.assertEqual(e.key, "forcedoor")

    def test_escape_key(self):
        e = _load(_path("escape.md"))
        self.assertEqual(e.key, "escape")

    def test_move_has_cardinal_aliases(self):
        e = _load(_path("move.md"))
        for alias in ("north", "south", "east", "west", "up", "down",
                      "n", "s", "e", "w", "u", "d",
                      "ne", "nw", "se", "sw",
                      "northeast", "northwest", "southeast", "southwest",
                      "enter", "leave"):
            self.assertIn(alias, e.aliases,
                          f"move.md missing direction alias: {alias!r}")

    def test_coords_has_coordinates_alias(self):
        e = _load(_path("coords.md"))
        self.assertIn("coordinates", e.aliases)

    def test_stim_has_stimaccept_aliases(self):
        e = _load(_path("stim.md"))
        for alias in ("stimaccept", "saccept"):
            self.assertIn(alias, e.aliases,
                          f"stim.md missing alias: {alias!r}")

    def test_steal_has_pilfer_alias(self):
        e = _load(_path("steal.md"))
        for alias in ("pilfer", "swipe"):
            self.assertIn(alias, e.aliases,
                          f"steal.md missing alias: {alias!r}")

    def test_forcedoor_has_breakin_alias(self):
        e = _load(_path("forcedoor.md"))
        self.assertIn("breakin", e.aliases)

    def test_escape_has_struggle_alias(self):
        e = _load(_path("escape.md"))
        self.assertIn("struggle", e.aliases)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Body sanity — non-trivial content
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpMovementCrimeMedicalBody(unittest.TestCase):
    def test_move_body_mentions_directions(self):
        e = _load(_path("move.md"))
        self.assertIn("north", e.body.lower())
        self.assertGreater(len(e.body), 200)

    def test_think_body_mentions_private(self):
        e = _load(_path("think.md"))
        self.assertIn("private", e.body.lower())
        self.assertGreater(len(e.body), 100)

    def test_coords_body_mentions_wilderness(self):
        e = _load(_path("coords.md"))
        self.assertIn("wilderness", e.body.lower())

    def test_stim_body_mentions_medpac(self):
        e = _load(_path("stim.md"))
        self.assertIn("medpac", e.body.lower())
        self.assertGreater(len(e.body), 300)

    def test_steal_body_mentions_zone(self):
        e = _load(_path("steal.md"))
        self.assertIn("lawless", e.body.lower())

    def test_forcedoor_body_mentions_strength(self):
        e = _load(_path("forcedoor.md"))
        self.assertIn("strength", e.body.lower())

    def test_escape_body_mentions_strength(self):
        e = _load(_path("escape.md"))
        self.assertIn("strength", e.body.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 4. HelpManager lookup — keys and aliases resolve
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpMovementCrimeMedicalLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mgr = _manager()

    # Primary keys
    def test_move_resolves(self):
        self.assertIsNotNone(self.mgr.get("move"))

    def test_think_resolves(self):
        self.assertIsNotNone(self.mgr.get("think"))

    def test_coords_resolves(self):
        self.assertIsNotNone(self.mgr.get("coords"))

    def test_stim_resolves(self):
        self.assertIsNotNone(self.mgr.get("stim"))

    def test_steal_resolves(self):
        self.assertIsNotNone(self.mgr.get("steal"))

    def test_forcedoor_resolves(self):
        self.assertIsNotNone(self.mgr.get("forcedoor"))

    def test_escape_resolves(self):
        self.assertIsNotNone(self.mgr.get("escape"))

    # Direction aliases → move
    def test_north_resolves_to_move(self):
        e = self.mgr.get("north")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "move")

    def test_south_resolves_to_move(self):
        e = self.mgr.get("south")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "move")

    def test_n_resolves_to_move(self):
        e = self.mgr.get("n")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "move")

    def test_ne_resolves_to_move(self):
        e = self.mgr.get("ne")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "move")

    def test_up_resolves_to_move(self):
        e = self.mgr.get("up")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "move")

    def test_enter_resolves_to_move(self):
        e = self.mgr.get("enter")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "move")

    # Stim aliases
    def test_stimaccept_resolves_to_stim(self):
        e = self.mgr.get("stimaccept")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "stim")

    def test_saccept_resolves_to_stim(self):
        e = self.mgr.get("saccept")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "stim")

    # Other aliases
    def test_coordinates_resolves_to_coords(self):
        e = self.mgr.get("coordinates")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "coords")

    def test_pilfer_resolves_to_steal(self):
        e = self.mgr.get("pilfer")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "steal")

    def test_breakin_resolves_to_forcedoor(self):
        e = self.mgr.get("breakin")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "forcedoor")

    def test_struggle_resolves_to_escape(self):
        e = self.mgr.get("struggle")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "escape")
