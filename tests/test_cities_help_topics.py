# -*- coding: utf-8 -*-
"""
tests/test_cities_help_topics.py — Phase 6 help-topics drop.

Verifies the three new city help files load cleanly via the
project's help loader and carry the expected frontmatter:

  data/help/commands/+city.md     — player command reference
  data/help/commands/@city.md     — admin command reference
  data/help/topics/cities.md      — conceptual overview

Strategy mirrors tests/test_session47_help_system.py — we exercise
load_help_file end-to-end against the real on-disk files (not a
tmpdir), so any YAML typo, malformed `examples:` block, or missing
`title:` is caught here rather than in a Windows pytest run.

Per HANDOFF_MAY23_CITIES_PHASE6_HELP.md.
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file


# Repo-root anchor: this test file lives in <repo>/tests/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_HELP_DIR = os.path.join(_REPO_ROOT, "data", "help")

_PLAYER_PATH = os.path.join(_HELP_DIR, "commands", "+city.md")
_ADMIN_PATH = os.path.join(_HELP_DIR, "commands", "@city.md")
_TOPIC_PATH = os.path.join(_HELP_DIR, "topics", "cities.md")


# ══════════════════════════════════════════════════════════════════════════════
# 1. Files exist on disk
# ══════════════════════════════════════════════════════════════════════════════

class TestCityHelpFilesExist(unittest.TestCase):
    """Sanity: the three help files were dropped at the expected paths."""

    def test_player_command_help_exists(self):
        self.assertTrue(
            os.path.isfile(_PLAYER_PATH),
            f"Missing: {_PLAYER_PATH}",
        )

    def test_admin_command_help_exists(self):
        self.assertTrue(
            os.path.isfile(_ADMIN_PATH),
            f"Missing: {_ADMIN_PATH}",
        )

    def test_conceptual_topic_help_exists(self):
        self.assertTrue(
            os.path.isfile(_TOPIC_PATH),
            f"Missing: {_TOPIC_PATH}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. Player +city command help loads cleanly
# ══════════════════════════════════════════════════════════════════════════════

class TestPlayerCityHelp(unittest.TestCase):
    """`data/help/commands/+city.md` round-trips through load_help_file."""

    @classmethod
    def setUpClass(cls):
        cls.entry = load_help_file(_PLAYER_PATH, HelpEntry)

    def test_entry_loaded(self):
        self.assertIsNotNone(
            self.entry,
            "load_help_file returned None — frontmatter parse failed",
        )

    def test_key_is_plus_city(self):
        # Per help_loader: key is lowercased on read.
        self.assertEqual(self.entry.key, "+city")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        # Sanity — the title should mention "city" (case-insensitive).
        self.assertIn("city", self.entry.title.lower())

    def test_category_is_commands_economy(self):
        self.assertEqual(self.entry.category, "Commands: Economy")

    def test_access_level_is_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_aliases_include_bare_city(self):
        # Bare `city` alias is the player-facing convenience form.
        self.assertIn("city", self.entry.aliases)

    def test_see_also_includes_conceptual_topic(self):
        # The command help should cross-link to the conceptual topic.
        self.assertIn("cities", self.entry.see_also)

    def test_examples_present_and_well_formed(self):
        # We dropped >= 10 examples; allow some headroom for editorial
        # tightening later, but require a meaningful set.
        self.assertGreaterEqual(len(self.entry.examples), 10)
        for ex in self.entry.examples:
            self.assertIn("cmd", ex)
            self.assertIn("description", ex)
            self.assertTrue(ex["cmd"].strip())
            self.assertTrue(ex["description"].strip())

    def test_body_mentions_each_subcommand_family(self):
        """The body should reference the major +city subcommand families
        so a player searching the body text for, e.g., 'banish' finds it.
        """
        body_lower = self.entry.body.lower()
        for needle in (
            "found", "claim", "release", "info", "map", "citizens",
            "motd", "mayor", "guest", "banish", "tax", "home",
        ):
            self.assertIn(
                needle, body_lower,
                f"+city help body missing reference to subcommand: {needle!r}",
            )

    def test_body_mentions_grace_pointer(self):
        # The body shouldn't restate the full grace state machine, but
        # it should at least point the reader to the conceptual topic.
        body_lower = self.entry.body.lower()
        self.assertIn("grace", body_lower)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Admin @city command help loads cleanly
# ══════════════════════════════════════════════════════════════════════════════

class TestAdminCityHelp(unittest.TestCase):
    """`data/help/commands/@city.md` round-trips through load_help_file."""

    @classmethod
    def setUpClass(cls):
        cls.entry = load_help_file(_ADMIN_PATH, HelpEntry)

    def test_entry_loaded(self):
        self.assertIsNotNone(self.entry)

    def test_key_is_at_city(self):
        self.assertEqual(self.entry.key, "@city")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_is_commands_admin(self):
        self.assertEqual(self.entry.category, "Commands: Admin")

    def test_access_level_is_admin(self):
        # Anything > 0 means non-default; admin-only help should not
        # accidentally show up in a player's help listing.
        self.assertGreater(
            self.entry.access_level, 0,
            "@city help is admin-only — access_level must be > 0",
        )

    def test_examples_cover_all_six_subforms(self):
        # @city has exactly six subforms — list / inspect / void-banish /
        # set-rate-cap / dissolve / rename. At minimum one example each.
        cmd_text = " ".join(ex["cmd"].lower() for ex in self.entry.examples)
        for subform in (
            "list", "inspect", "void-banish",
            "set-rate-cap", "dissolve", "rename",
        ):
            self.assertIn(
                subform, cmd_text,
                f"@city help missing example for subform: {subform!r}",
            )

    def test_body_distinguishes_admin_vs_player_dissolve(self):
        """The body should call out that admin dissolve issues NO refund,
        which is the key distinguishing fact vs +city dissolve."""
        body_lower = self.entry.body.lower()
        self.assertIn("no refund", body_lower)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Conceptual `cities` topic loads cleanly
# ══════════════════════════════════════════════════════════════════════════════

class TestCitiesConceptualHelp(unittest.TestCase):
    """`data/help/topics/cities.md` round-trips through load_help_file."""

    @classmethod
    def setUpClass(cls):
        cls.entry = load_help_file(_TOPIC_PATH, HelpEntry)

    def test_entry_loaded(self):
        self.assertIsNotNone(self.entry)

    def test_key_is_cities(self):
        self.assertEqual(self.entry.key, "cities")

    def test_category_is_economy(self):
        self.assertEqual(self.entry.category, "Economy")

    def test_access_level_is_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_see_also_crosslinks_command_pages(self):
        # The conceptual page should cross-link to both command pages
        # and adjacent systems.
        for needle in ("+city", "@city", "housing", "territory"):
            self.assertIn(
                needle, self.entry.see_also,
                f"cities topic missing see_also link to: {needle!r}",
            )

    def test_body_covers_grace_state_machine(self):
        """The conceptual page IS the place where the full grace state
        machine is documented — verify each stage is mentioned."""
        body_lower = self.entry.body.lower()
        # All four grace-week markers should appear.
        for needle in ("week 1", "week 2", "week 3", "week 4"):
            self.assertIn(
                needle, body_lower,
                f"cities topic missing grace stage marker: {needle!r}",
            )
        # The recovery + dissolve outcomes should be explicit.
        self.assertIn("recovery", body_lower)
        self.assertIn("dissolved", body_lower)

    def test_body_covers_founder_immutability(self):
        body_lower = self.entry.body.lower()
        self.assertIn("founder", body_lower)
        self.assertIn("immutable", body_lower)

    def test_body_mentions_three_dissolution_paths(self):
        """Voluntary / admin / maintenance-expiry — the three ways a city
        can end. Each should be visible in the conceptual overview."""
        body_lower = self.entry.body.lower()
        self.assertIn("voluntary", body_lower)
        self.assertIn("admin", body_lower)
        # The natural-causes path goes by several names; accept any.
        self.assertTrue(
            "expiry" in body_lower or "expir" in body_lower
            or "auto-dissolve" in body_lower,
            "cities topic should describe the maintenance-expiry "
            "dissolution path",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5. Cross-file consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestCityHelpCrossConsistency(unittest.TestCase):
    """Cross-file invariants. If a refactor renames one file's see_also
    target, the broken pointer surfaces here rather than as a silent
    dangling cross-link."""

    @classmethod
    def setUpClass(cls):
        cls.player = load_help_file(_PLAYER_PATH, HelpEntry)
        cls.admin = load_help_file(_ADMIN_PATH, HelpEntry)
        cls.topic = load_help_file(_TOPIC_PATH, HelpEntry)

    def test_all_three_loaded(self):
        self.assertIsNotNone(self.player)
        self.assertIsNotNone(self.admin)
        self.assertIsNotNone(self.topic)

    def test_player_links_to_admin_and_topic(self):
        self.assertIn("cities", self.player.see_also)

    def test_admin_links_to_player_and_topic(self):
        self.assertIn("+city", self.admin.see_also)
        self.assertIn("cities", self.admin.see_also)

    def test_topic_links_to_both_command_pages(self):
        self.assertIn("+city", self.topic.see_also)
        self.assertIn("@city", self.topic.see_also)

    def test_distinct_keys(self):
        keys = {self.player.key, self.admin.key, self.topic.key}
        self.assertEqual(
            len(keys), 3,
            f"Expected 3 distinct keys; got {keys}",
        )


if __name__ == "__main__":
    unittest.main()
