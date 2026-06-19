# -*- coding: utf-8 -*-
"""
tests/test_help_basic_interaction_gaps.py — help-corpus basic interaction gap coverage.

Verifies that the most-used player commands return help entries via the
markdown-loaded HelpManager (not auto-stubs). These commands previously
returned "No help found" when looked up without the command registry:

  look / l                   → look.md
  equip / wield / draw /
    wear / don /
    unequip / holster / sheathe /
    remove / doff              → equip.md
  buy / purchase             → buy.md
  sell                       → sell.md
  give / hand                → give.md
  loot                       → loot.md
  get / take / pickup / grab /
    drop / discard             → get.md
  train                      → train.md
  talk / ask                 → talk.md
  board / disembark /
    deboard / leave_ship       → board.md
  respawn / revive / bacta   → respawn.md
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
    """Build a HelpManager loaded from the real help directory (md-only)."""
    mgr = HelpManager()
    mgr.load_markdown_files(os.path.join(_REPO_ROOT, "data", "help"))
    return mgr


# ═══════════════════════════════════════════════════════════════════════════
# 1. File existence
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpBasicInteractionFilesExist(unittest.TestCase):
    def test_look_exists(self):
        self.assertTrue(os.path.isfile(_path("look.md")))

    def test_equip_exists(self):
        self.assertTrue(os.path.isfile(_path("equip.md")))

    def test_buy_exists(self):
        self.assertTrue(os.path.isfile(_path("buy.md")))

    def test_sell_exists(self):
        self.assertTrue(os.path.isfile(_path("sell.md")))

    def test_give_exists(self):
        self.assertTrue(os.path.isfile(_path("give.md")))

    def test_loot_exists(self):
        self.assertTrue(os.path.isfile(_path("loot.md")))

    def test_get_exists(self):
        self.assertTrue(os.path.isfile(_path("get.md")))

    def test_train_exists(self):
        self.assertTrue(os.path.isfile(_path("train.md")))

    def test_talk_exists(self):
        self.assertTrue(os.path.isfile(_path("talk.md")))

    def test_board_exists(self):
        self.assertTrue(os.path.isfile(_path("board.md")))

    def test_respawn_exists(self):
        self.assertTrue(os.path.isfile(_path("respawn.md")))


# ═══════════════════════════════════════════════════════════════════════════
# 2. Frontmatter keys are correct
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpBasicInteractionFrontmatter(unittest.TestCase):
    def test_look_key(self):
        e = _load(_path("look.md"))
        self.assertEqual(e.key, "look")

    def test_equip_key(self):
        e = _load(_path("equip.md"))
        self.assertEqual(e.key, "equip")

    def test_buy_key(self):
        e = _load(_path("buy.md"))
        self.assertEqual(e.key, "buy")

    def test_sell_key(self):
        e = _load(_path("sell.md"))
        self.assertEqual(e.key, "sell")

    def test_give_key(self):
        e = _load(_path("give.md"))
        self.assertEqual(e.key, "give")

    def test_loot_key(self):
        e = _load(_path("loot.md"))
        self.assertEqual(e.key, "loot")

    def test_get_key(self):
        e = _load(_path("get.md"))
        self.assertEqual(e.key, "get")

    def test_train_key(self):
        e = _load(_path("train.md"))
        self.assertEqual(e.key, "train")

    def test_talk_key(self):
        e = _load(_path("talk.md"))
        self.assertEqual(e.key, "talk")

    def test_board_key(self):
        e = _load(_path("board.md"))
        self.assertEqual(e.key, "board")

    def test_respawn_key(self):
        e = _load(_path("respawn.md"))
        self.assertEqual(e.key, "respawn")

    def test_equip_has_equipment_aliases(self):
        e = _load(_path("equip.md"))
        for alias in ("wield", "draw", "wear", "don",
                      "unequip", "holster", "sheathe", "remove", "doff"):
            self.assertIn(alias, e.aliases,
                          f"equip.md missing alias: {alias!r}")

    def test_look_has_l_alias(self):
        e = _load(_path("look.md"))
        self.assertIn("l", e.aliases)

    def test_buy_has_purchase_alias(self):
        e = _load(_path("buy.md"))
        self.assertIn("purchase", e.aliases)

    def test_give_has_hand_alias(self):
        e = _load(_path("give.md"))
        self.assertIn("hand", e.aliases)

    def test_get_has_take_drop_aliases(self):
        e = _load(_path("get.md"))
        for alias in ("take", "pickup", "grab", "drop", "discard"):
            self.assertIn(alias, e.aliases,
                          f"get.md missing alias: {alias!r}")

    def test_talk_has_ask_alias(self):
        e = _load(_path("talk.md"))
        self.assertIn("ask", e.aliases)

    def test_board_has_disembark_aliases(self):
        e = _load(_path("board.md"))
        for alias in ("disembark", "deboard", "leave_ship"):
            self.assertIn(alias, e.aliases,
                          f"board.md missing alias: {alias!r}")

    def test_respawn_has_revive_bacta_aliases(self):
        e = _load(_path("respawn.md"))
        for alias in ("revive", "bacta"):
            self.assertIn(alias, e.aliases,
                          f"respawn.md missing alias: {alias!r}")


# ═══════════════════════════════════════════════════════════════════════════
# 3. HelpManager lookup — aliases resolve to the right entry
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpBasicInteractionLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mgr = _manager()

    # Primary keys
    def test_look_resolves(self):
        self.assertIsNotNone(self.mgr.get("look"))

    def test_equip_resolves(self):
        self.assertIsNotNone(self.mgr.get("equip"))

    def test_buy_resolves(self):
        self.assertIsNotNone(self.mgr.get("buy"))

    def test_sell_resolves(self):
        self.assertIsNotNone(self.mgr.get("sell"))

    def test_give_resolves(self):
        self.assertIsNotNone(self.mgr.get("give"))

    def test_loot_resolves(self):
        self.assertIsNotNone(self.mgr.get("loot"))

    def test_get_resolves(self):
        self.assertIsNotNone(self.mgr.get("get"))

    def test_train_resolves(self):
        self.assertIsNotNone(self.mgr.get("train"))

    def test_talk_resolves(self):
        self.assertIsNotNone(self.mgr.get("talk"))

    def test_board_resolves(self):
        self.assertIsNotNone(self.mgr.get("board"))

    def test_respawn_resolves(self):
        self.assertIsNotNone(self.mgr.get("respawn"))

    # Important aliases
    def test_l_resolves_to_look(self):
        e = self.mgr.get("l")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "look")

    def test_wield_resolves_to_equip(self):
        e = self.mgr.get("wield")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_wear_resolves_to_equip(self):
        e = self.mgr.get("wear")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_don_resolves_to_equip(self):
        e = self.mgr.get("don")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_unequip_resolves_to_equip(self):
        e = self.mgr.get("unequip")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_holster_resolves_to_equip(self):
        e = self.mgr.get("holster")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_sheathe_resolves_to_equip(self):
        e = self.mgr.get("sheathe")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_remove_resolves_to_equip(self):
        e = self.mgr.get("remove")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_doff_resolves_to_equip(self):
        e = self.mgr.get("doff")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_draw_resolves_to_equip(self):
        e = self.mgr.get("draw")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "equip")

    def test_purchase_resolves_to_buy(self):
        e = self.mgr.get("purchase")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "buy")

    def test_hand_resolves_to_give(self):
        e = self.mgr.get("hand")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "give")

    def test_take_resolves_to_get(self):
        e = self.mgr.get("take")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "get")

    def test_drop_resolves_to_get(self):
        e = self.mgr.get("drop")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "get")

    def test_discard_resolves_to_get(self):
        e = self.mgr.get("discard")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "get")

    def test_ask_resolves_to_talk(self):
        e = self.mgr.get("ask")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "talk")

    def test_disembark_resolves_to_board(self):
        e = self.mgr.get("disembark")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "board")

    def test_deboard_resolves_to_board(self):
        e = self.mgr.get("deboard")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "board")

    def test_leave_ship_resolves_to_board(self):
        e = self.mgr.get("leave_ship")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "board")

    def test_revive_resolves_to_respawn(self):
        e = self.mgr.get("revive")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "respawn")

    def test_bacta_resolves_to_respawn(self):
        e = self.mgr.get("bacta")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "respawn")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Content sanity — entries have non-trivial bodies
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpBasicInteractionContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mgr = _manager()

    def _assert_body(self, key: str, min_len: int = 100):
        e = self.mgr.get(key)
        self.assertIsNotNone(e, f"No entry for {key!r}")
        self.assertGreater(len(e.body), min_len,
                           f"{key!r} body too short ({len(e.body)} chars)")

    def test_look_has_body(self):
        self._assert_body("look")

    def test_equip_has_body(self):
        self._assert_body("equip")

    def test_buy_has_body(self):
        self._assert_body("buy")

    def test_sell_has_body(self):
        self._assert_body("sell")

    def test_give_has_body(self):
        self._assert_body("give")

    def test_loot_has_body(self):
        self._assert_body("loot")

    def test_get_has_body(self):
        self._assert_body("get")

    def test_train_has_body(self):
        self._assert_body("train")

    def test_talk_has_body(self):
        self._assert_body("talk")

    def test_board_has_body(self):
        self._assert_body("board")

    def test_respawn_has_body(self):
        self._assert_body("respawn")


if __name__ == "__main__":
    unittest.main()
