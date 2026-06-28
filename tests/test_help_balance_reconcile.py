# -*- coding: utf-8 -*-
"""tests/test_help_balance_reconcile.py

Help-corpus launch reconcile (2026-06-27, OpusLoop) — the Sonnet help-corpus
loop (SWMUSH-DurableLoop) is DISABLED, so the admin `@balance`/`@bal`
telemetry dashboard (shipped by the T3.19 read-side + the chain-rollup drop)
had NO `data/help/**` entry at all — a launch corner for the one admin board
Brian reads to tune balance.

This guard pins BOTH the new help entry AND the live producer it documents
(`parser/director_commands.py::BalanceCommand`), so a regression in either
the docs or the command fails loudly (no-phantom, both directions):

  - the help file loads with the right key/alias/admin access_level;
  - it teaches the load-bearing @balance-vs-@economy distinction;
  - it documents EVERY sub-board the live command advertises in its own
    `usage` string (self-maintaining — add a sub-board to the command
    without documenting it and this test goes red).
"""

from __future__ import annotations

import os
import re
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file
from parser.commands import AccessLevel
from parser.director_commands import BalanceCommand

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")
_BALANCE_PATH = os.path.join(_CMD_DIR, "@balance.md")


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


def _usage_subboards() -> list[str]:
    """Derive the canonical sub-board list from the LIVE command's usage.

    ``@balance [grind|cp|objectives|chains|encounters|events|raw [N]]`` →
    ['grind','cp','objectives','chains','encounters','events','raw'].
    Self-maintaining: a new sub-board added to the command's usage must
    then be documented in the help body or the doc-coverage test fails.
    """
    usage = BalanceCommand.usage
    inner = usage.split("[", 1)[1] if "[" in usage else usage
    boards: list[str] = []
    for piece in inner.split("|"):
        m = re.search(r"[a-z]+", piece.lower())
        if m:
            boards.append(m.group(0))
    return boards


# ── 1. The help file loads with the right contract ───────────────────────────

class TestBalanceHelpEntry(unittest.TestCase):
    def setUp(self):
        self.e = _load(_BALANCE_PATH)
        self.body = self.e.body.lower()

    def test_key_is_balance(self):
        self.assertEqual(self.e.key, "@balance")

    def test_bal_alias_present(self):
        self.assertIn("@bal", self.e.aliases)

    def test_admin_access_level(self):
        # 2 == AccessLevel.ADMIN — this board must not be visible to players.
        self.assertEqual(self.e.access_level, int(AccessLevel.ADMIN))

    def test_has_summary_and_admin_category(self):
        self.assertTrue(self.e.summary.strip(), "@balance help needs a summary")
        self.assertIn("admin", self.e.category.lower())

    def test_teaches_economy_distinction(self):
        # The load-bearing concept: @balance = telemetry trend over time,
        # the companion to @economy's live-DB snapshot.
        self.assertIn("@economy", self.body)
        self.assertIn("append-only", self.body)
        self.assertIn("telemetry", self.body)


# ── 2. Help ↔ live command stay in lockstep (no-phantom, both directions) ─────

class TestBalanceHelpMatchesProducer(unittest.TestCase):
    def test_command_contract_unchanged(self):
        # If the live command's key/alias/access drift, the help is wrong.
        self.assertEqual(BalanceCommand.key, "@balance")
        self.assertIn("@bal", BalanceCommand.aliases)
        self.assertEqual(BalanceCommand.access_level, AccessLevel.ADMIN)

    def test_every_subboard_is_documented(self):
        # Self-maintaining: every sub-board the command advertises must
        # appear in the help body, so a future sub-board can't ship undocumented.
        body = _load(_BALANCE_PATH).body.lower()
        boards = _usage_subboards()
        # sanity: the usage actually parsed to the expected core set
        for expected in ("grind", "cp", "objectives", "chains",
                         "encounters", "events", "sessions", "skills", "raw"):
            self.assertIn(expected, boards,
                          f"usage parse missing {expected!r}: {boards}")
        for board in boards:
            self.assertIn(board, body,
                          f"@balance help omits the {board!r} sub-board")

    def test_chains_board_documented(self):
        # The chains funnel board (telemetry-chain-rollup consumer) is the
        # newest sub-board — make sure the help names it explicitly.
        body = _load(_BALANCE_PATH).body.lower()
        self.assertIn("chains", body)
        self.assertIn("completion funnel", body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
