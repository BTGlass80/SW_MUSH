# -*- coding: utf-8 -*-
"""
tests/test_help_comms_gaps.py — help-corpus comms/social gap coverage.

Verifies that the communication and social commands that previously returned
"No help found" now resolve correctly via the help system:

  - comlink / cl / clink   → +channels.md (IC planet comlink)
  - fcomm / fc / faction-comm → +channels.md (faction channel)
  - newbie / oocsay        → +channels.md (global OOC channels)
  - tune / tunein / untune / tuneout / commfreq / cf / freq → +freqs.md
  - tt / tabletalk / ttooc / mutter → +place.md (table talk / RP poses)
  - rally / +rally         → rally.md (community event)
  - page / p               → page.md (private messaging)
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry, HelpManager
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_CHANNELS_PATH = os.path.join(_CMD_DIR, "+channels.md")
_FREQS_PATH    = os.path.join(_CMD_DIR, "+freqs.md")
_PLACE_PATH    = os.path.join(_CMD_DIR, "+place.md")
_RALLY_PATH    = os.path.join(_CMD_DIR, "rally.md")
_PAGE_PATH     = os.path.join(_CMD_DIR, "page.md")


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


def _manager() -> HelpManager:
    """Build a HelpManager loaded from the real help directory."""
    import data.help_topics as ht
    mgr = HelpManager()
    mgr.load_markdown_files(os.path.join(_REPO_ROOT, "data", "help"))
    return mgr


# ═══════════════════════════════════════════════════════════════════════════
# 1. File existence
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpGapFilesExist(unittest.TestCase):
    def test_channels_exists(self):
        self.assertTrue(os.path.isfile(_CHANNELS_PATH))

    def test_freqs_exists(self):
        self.assertTrue(os.path.isfile(_FREQS_PATH))

    def test_place_exists(self):
        self.assertTrue(os.path.isfile(_PLACE_PATH))

    def test_rally_exists(self):
        self.assertTrue(os.path.isfile(_RALLY_PATH))

    def test_page_exists(self):
        self.assertTrue(os.path.isfile(_PAGE_PATH))


# ═══════════════════════════════════════════════════════════════════════════
# 2. page.md — new file sanity
# ═══════════════════════════════════════════════════════════════════════════

class TestPageHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_PAGE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "page")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("page", self.entry.title.lower())

    def test_access_level_player(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_p(self):
        self.assertIn("p", self.entry.aliases)

    def test_body_mentions_syntax(self):
        self.assertIn("page", self.entry.body.lower())

    def test_body_mentions_equal_sign(self):
        self.assertIn("=", self.entry.body)


# ═══════════════════════════════════════════════════════════════════════════
# 3. +channels.md — comlink / fcomm / newbie / oocsay aliases
# ═══════════════════════════════════════════════════════════════════════════

class TestChannelsGapAliases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_CHANNELS_PATH)

    def test_comlink_alias(self):
        self.assertIn("comlink", self.entry.aliases)

    def test_cl_alias(self):
        self.assertIn("cl", self.entry.aliases)

    def test_clink_alias(self):
        self.assertIn("clink", self.entry.aliases)

    def test_fcomm_alias(self):
        self.assertIn("fcomm", self.entry.aliases)

    def test_fc_alias(self):
        self.assertIn("fc", self.entry.aliases)

    def test_faction_comm_alias(self):
        self.assertIn("faction-comm", self.entry.aliases)

    def test_oocsay_alias(self):
        self.assertIn("oocsay", self.entry.aliases)


# ═══════════════════════════════════════════════════════════════════════════
# 4. +freqs.md — tune / commfreq aliases
# ═══════════════════════════════════════════════════════════════════════════

class TestFreqsGapAliases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_FREQS_PATH)

    def test_tune_alias(self):
        self.assertIn("tune", self.entry.aliases)

    def test_tunein_alias(self):
        self.assertIn("tunein", self.entry.aliases)

    def test_untune_alias(self):
        self.assertIn("untune", self.entry.aliases)

    def test_tuneout_alias(self):
        self.assertIn("tuneout", self.entry.aliases)

    def test_commfreq_alias(self):
        self.assertIn("commfreq", self.entry.aliases)

    def test_cf_alias(self):
        self.assertIn("cf", self.entry.aliases)

    def test_freq_alias(self):
        self.assertIn("freq", self.entry.aliases)


# ═══════════════════════════════════════════════════════════════════════════
# 5. +place.md — tt / tabletalk / ttooc / mutter aliases
# ═══════════════════════════════════════════════════════════════════════════

class TestPlaceGapAliases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_PLACE_PATH)

    def test_tt_alias(self):
        self.assertIn("tt", self.entry.aliases)

    def test_tabletalk_alias(self):
        self.assertIn("tabletalk", self.entry.aliases)

    def test_ttooc_alias(self):
        self.assertIn("ttooc", self.entry.aliases)

    def test_mutter_alias(self):
        self.assertIn("mutter", self.entry.aliases)


# ═══════════════════════════════════════════════════════════════════════════
# 6. rally.md — +rally alias
# ═══════════════════════════════════════════════════════════════════════════

class TestRallyGapAliases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_RALLY_PATH)

    def test_rally_alias(self):
        self.assertIn("+rally", self.entry.aliases)


# ═══════════════════════════════════════════════════════════════════════════
# 7. End-to-end HelpManager lookup — all gap commands resolve
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpManagerLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mgr = _manager()

    def _resolves(self, name: str, expected_key: str):
        entry = self.mgr.get(name)
        self.assertIsNotNone(entry, f"help '{name}' returned None")
        self.assertEqual(entry.key, expected_key,
                         f"help '{name}' resolved to '{entry.key}', expected '{expected_key}'")

    def test_comlink_resolves(self):
        self._resolves("comlink", "+channels")

    def test_cl_resolves(self):
        self._resolves("cl", "+channels")

    def test_fcomm_resolves(self):
        self._resolves("fcomm", "+channels")

    def test_fc_resolves(self):
        self._resolves("fc", "+channels")

    def test_newbie_resolves_builtin(self):
        # newbie is a built-in New Player Guide key — already covered, not a gap
        entry = self.mgr.get("newbie")
        self.assertIsNotNone(entry, "help 'newbie' returned None")
        self.assertEqual(entry.key, "newbie")

    def test_oocsay_resolves(self):
        self._resolves("oocsay", "+channels")

    def test_page_resolves(self):
        self._resolves("page", "page")

    def test_p_resolves(self):
        self._resolves("p", "page")

    def test_tune_resolves(self):
        self._resolves("tune", "+freqs")

    def test_tunein_resolves(self):
        self._resolves("tunein", "+freqs")

    def test_untune_resolves(self):
        self._resolves("untune", "+freqs")

    def test_commfreq_resolves(self):
        self._resolves("commfreq", "+freqs")

    def test_cf_resolves(self):
        self._resolves("cf", "+freqs")

    def test_tt_resolves(self):
        self._resolves("tt", "+place")

    def test_tabletalk_resolves(self):
        self._resolves("tabletalk", "+place")

    def test_ttooc_resolves(self):
        self._resolves("ttooc", "+place")

    def test_mutter_resolves(self):
        self._resolves("mutter", "+place")

    def test_rally_resolves(self):
        self._resolves("rally", "rally")

    def test_plus_rally_resolves(self):
        self._resolves("+rally", "rally")
