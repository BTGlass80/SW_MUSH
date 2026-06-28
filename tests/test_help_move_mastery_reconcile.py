# -*- coding: utf-8 -*-
"""tests/test_help_move_mastery_reconcile.py

Help-corpus launch reconcile (2026-06-27, OpusLoop) — the Sonnet help-corpus
loop (SWMUSH-DurableLoop) is DISABLED, so two player-facing (access_level 0)
help files had gone stale against subsystems shipped during the fun-drive:

  data/help/commands/move.md
    Was compass-directions-ONLY. The two biggest movement onboarding fixes
    of the fun-drive were undocumented:
      - named-exit walking  (parser/commands.py `_match_exit` routing, d3e1d3d)
      - `go`/`walk`/`head <dir>` verbs (parser/commands.py fun12, ddef084)

  data/help/commands/mastery.md
    Framed `mastery` as master-trainer-Tier-5-ONLY end-game content. Missing:
      - the FREELANCE accessible questlines (chargen_complete, open to anyone)
      - `mastery browse` galaxy-wide directory (ba59428;
        engine.chain_events.list_questline_directory + the browse consumer)

This guard pins BOTH the help prose AND the live producers it claims, so a
regression in either the docs or the engine fails loudly (no-phantom, both
directions).
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry, HelpManager
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")
_MOVE_PATH = os.path.join(_CMD_DIR, "move.md")
_MASTERY_PATH = os.path.join(_CMD_DIR, "mastery.md")


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


def _read(rel: str) -> str:
    with open(os.path.join(_REPO_ROOT, rel), "r", encoding="utf-8") as fh:
        return fh.read()


# ── 1. move.md teaches the shipped movement systems ──────────────────────────

class TestMoveHelpReconcile(unittest.TestCase):
    def setUp(self):
        self.e = _load(_MOVE_PATH)
        self.body = self.e.body.lower()

    def test_key_preserved(self):
        self.assertEqual(self.e.key, "move")

    def test_compass_contract_preserved(self):
        # The pre-existing test_help_movement_crime_medical_gaps contract:
        # body still mentions compass directions and stays substantial.
        self.assertIn("north", self.body)
        self.assertGreater(len(self.e.body), 200)

    def test_cardinal_aliases_preserved(self):
        for alias in ("north", "south", "east", "west", "up", "down",
                      "n", "s", "e", "w", "ne", "nw", "se", "sw",
                      "enter", "leave"):
            self.assertIn(alias, self.e.aliases,
                          f"move.md lost cardinal alias {alias!r}")

    def test_teaches_named_exit_walking(self):
        # The #1 fun-pass killer fix: walk by an exit's NAME.
        self.assertIn("exit name", self.body)
        self.assertTrue(
            "name of an exit" in self.body or "type the name" in self.body,
            "move.md must teach typing an exit name to walk it",
        )

    def test_teaches_go_walk_head(self):
        for verb in ("go", "walk", "head"):
            self.assertIn(verb, self.body,
                          f"move.md must document the {verb!r} movement verb")
        self.assertIn("go north", self.body)

    def test_go_walk_head_are_help_aliases(self):
        for verb in ("go", "walk", "head"):
            self.assertIn(verb, self.e.aliases,
                          f"`help {verb}` should resolve to move.md")


# ── 2. mastery.md teaches both questline kinds + the directory ───────────────

class TestMasteryHelpReconcile(unittest.TestCase):
    def setUp(self):
        self.e = _load(_MASTERY_PATH)
        self.body = self.e.body.lower()

    def test_key_and_title_preserved(self):
        # Pre-existing test_help_chain_mastery_lockpick contract.
        self.assertEqual(self.e.key, "mastery")
        self.assertIn("Mastery", self.e.title)
        self.assertIn("masteries", self.e.aliases)
        self.assertTrue(self.e.see_also)

    def test_teaches_freelance_kind(self):
        # Was trainer-T5-only; must now cover the open-to-anyone arcs.
        self.assertIn("freelance", self.body)
        self.assertTrue(
            "open to any" in self.body or "open to anyone" in self.body,
            "mastery.md must say freelance questlines are open to anyone",
        )

    def test_still_covers_trainer_t5_kind(self):
        self.assertIn("master", self.body)
        self.assertIn("tier-5", self.body)

    def test_teaches_browse_directory(self):
        self.assertIn("mastery browse", self.body)
        self.assertIn("directory", self.body)
        for alias in ("all", "directory", "catalog"):
            self.assertIn(alias, self.body)

    def test_no_phantom_questline_id_in_examples(self):
        # The example id must be a real chain in the corpus.
        text = _read("data/help/commands/mastery.md")
        self.assertIn("nar_freight_ghost_shipment", text)
        corpus = _read("data/worlds/clone_wars/tutorials/chains.yaml")
        self.assertIn("nar_freight_ghost_shipment", corpus,
                      "mastery.md example id is not a real questline")


# ── 3. HelpManager resolution (keys + new aliases) ───────────────────────────

class TestHelpResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mgr = HelpManager()
        cls.mgr.load_markdown_files()

    def test_move_resolves(self):
        e = self.mgr.get("move")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "move")

    def test_go_alias_resolves_to_move(self):
        e = self.mgr.get("go")
        self.assertIsNotNone(e, "`help go` should resolve")
        self.assertEqual(e.key, "move")

    def test_walk_alias_resolves_to_move(self):
        e = self.mgr.get("walk")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "move")

    def test_mastery_resolves(self):
        e = self.mgr.get("mastery")
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "mastery")


# ── 4. Producers exist at HEAD (no-phantom: docs ↔ engine) ───────────────────

class TestProducersExist(unittest.TestCase):
    def test_named_exit_and_go_walk_head_routing(self):
        src = _read("parser/commands.py")
        # named-exit walking via MoveCommand._match_exit
        self.assertIn("_match_exit", src,
                      "move.md claims named-exit walking but the router is gone")
        # fun12 go/walk/head prefix routing
        self.assertIn('("go", "walk", "head")', src,
                      "move.md documents go/walk/head but the routing is gone")

    def test_mastery_browse_producer(self):
        engine_src = _read("engine/chain_events.py")
        self.assertIn("def list_questline_directory", engine_src,
                      "mastery.md claims `mastery browse` but the directory "
                      "producer is gone")
        consumer = _read("parser/questline_commands.py")
        self.assertIn("_BROWSE_ALIASES", consumer)
        for alias in ("browse", "all", "directory", "catalog"):
            self.assertIn(alias, consumer)


if __name__ == "__main__":
    unittest.main()
