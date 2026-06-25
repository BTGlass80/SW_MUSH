# -*- coding: utf-8 -*-
"""
test_fun2_palette_iscommand.py — Fun-2 drop: is_command distinction on
HelpEntry and the reference-index payload.

Assertions:
  1. HelpEntry.is_command defaults to False (TOPIC_HELP entries, markdown
     entries, and bare HelpEntry() constructors).
  2. auto_register_commands() sets is_command=True on code-derived verbs.
  3. handle_reference_index() includes is_command in each entry's payload.
  4. A known TOPIC_HELP key ("dice") is present in the index but carries
     is_command=False.
  5. A code-registered command verb carries is_command=True in the index.
  6. handle_reference_search() also includes is_command in result payloads.
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
import unittest
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _as_async(fn):
    async def _inner(*args, **kwargs):
        return fn(*args, **kwargs)
    return _inner


class _FakeReq:
    def __init__(self, headers=None, query=None, match_info=None):
        self.headers    = headers    or {}
        self.query      = query      or {}
        self.match_info = match_info or {}


# ── Build a minimal fake command registry ────────────────────────────────────

class _FakeCmd:
    """Minimal stand-in for a BaseCommand instance."""
    def __init__(self, key, help_text="", usage="", aliases=None, access_level=0):
        self.key          = key
        self.help_text    = help_text
        self.usage        = usage
        self.aliases      = aliases or []
        self.access_level = access_level
        self.valid_switches = None


class _FakeRegistry:
    def __init__(self, cmds):
        self.all_commands = cmds


def _make_mixed_mgr():
    """HelpManager with one auto-registered command AND the full TOPIC_HELP set."""
    from data.help_topics import HelpManager, TOPIC_HELP

    mgr = HelpManager()

    # Auto-register one real command verb (look)
    registry = _FakeRegistry([
        _FakeCmd("look", help_text="Examine your surroundings.", access_level=0),
        _FakeCmd("attack", help_text="Attack a target.", access_level=0),
    ])
    mgr.auto_register_commands(registry)

    # Register all TOPIC_HELP entries (the static list in help_topics.py)
    for entry in TOPIC_HELP:
        mgr.register(entry)

    return mgr


def _make_api(mgr, admin=False):
    from server.web_portal import PortalAPI

    game = MagicMock()
    game.help_mgr = mgr

    db = MagicMock()

    async def _get_account(_id):
        return {"id": _id, "is_admin": 1 if admin else 0}
    db.get_account = _get_account

    api = PortalAPI(db=db, session_mgr=MagicMock(), game=game)
    if admin:
        api._optional_auth = _as_async(lambda _r: 99)
    return api


# ════════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════════

class TestHelpEntryIsCommandDefault(unittest.TestCase):
    """HelpEntry.is_command defaults False for bare / topic entries."""

    def test_bare_helpentry_defaults_false(self):
        from data.help_topics import HelpEntry
        e = HelpEntry(key="dice", title="Dice", category="Rules", body="roll dice")
        self.assertFalse(
            e.is_command,
            "Bare HelpEntry() should default is_command=False"
        )

    def test_topic_help_entries_all_false(self):
        """Every entry in TOPIC_HELP is a help topic, not a typeable command."""
        from data.help_topics import TOPIC_HELP
        for e in TOPIC_HELP:
            self.assertFalse(
                e.is_command,
                f"TOPIC_HELP entry {e.key!r} should have is_command=False "
                f"(it's a reference topic, not a typeable verb)"
            )

    def test_explicit_true_passes_through(self):
        from data.help_topics import HelpEntry
        e = HelpEntry(key="look", title="Look", category="Commands",
                      body="Look around.", is_command=True)
        self.assertTrue(e.is_command)


class TestAutoRegisterCommandsSetsIsCommand(unittest.TestCase):
    """auto_register_commands() marks derived entries is_command=True."""

    def _run_auto_register(self, keys):
        from data.help_topics import HelpManager
        mgr = HelpManager()
        registry = _FakeRegistry([_FakeCmd(k) for k in keys])
        mgr.auto_register_commands(registry)
        return mgr

    def test_registered_verbs_have_is_command_true(self):
        mgr = self._run_auto_register(["look", "attack", "+sheet"])
        for key in ("look", "attack", "+sheet"):
            entry = mgr.get(key)
            self.assertIsNotNone(entry, f"Entry {key!r} not found after auto_register")
            self.assertTrue(
                entry.is_command,
                f"auto_register_commands entry {key!r} should have is_command=True"
            )

    def test_topic_help_after_auto_register_stays_false(self):
        """TOPIC_HELP entries registered after auto_register keep is_command=False."""
        from data.help_topics import HelpManager, TOPIC_HELP
        mgr = HelpManager()
        registry = _FakeRegistry([_FakeCmd("look")])
        mgr.auto_register_commands(registry)
        for e in TOPIC_HELP:
            mgr.register(e)
        # Check a few topic keys
        for key in ("dice", "combat", "force", "moseisley"):
            entry = mgr.get(key)
            self.assertIsNotNone(entry, f"Topic {key!r} not found")
            self.assertFalse(
                entry.is_command,
                f"Topic {key!r} must remain is_command=False even after "
                f"being registered into a manager that also has command entries"
            )


class TestReferenceIndexIsCommandPayload(unittest.TestCase):
    """handle_reference_index carries is_command in every entry payload."""

    def _get_index_entries(self, admin=False):
        mgr = _make_mixed_mgr()
        api = _make_api(mgr, admin=admin)
        resp = _run(api.handle_reference_index(_FakeReq()))
        data = json.loads(resp.text)
        return {e["key"]: e for e in data["entries"]}

    def test_is_command_field_present_in_all_entries(self):
        entries = self._get_index_entries()
        self.assertGreater(len(entries), 0, "Index should not be empty")
        for key, e in entries.items():
            self.assertIn(
                "is_command", e,
                f"Entry {key!r} missing 'is_command' field in index payload"
            )

    def test_command_verb_has_is_command_true(self):
        """'look' auto-registered from the fake registry → is_command=True."""
        entries = self._get_index_entries()
        self.assertIn("look", entries, "'look' missing from index")
        self.assertTrue(
            entries["look"]["is_command"],
            "Auto-registered verb 'look' should have is_command=True in index"
        )

    def test_topic_entry_has_is_command_false(self):
        """'dice' is a TOPIC_HELP entry → is_command=False in index."""
        entries = self._get_index_entries()
        self.assertIn("dice", entries,
                      "'dice' TOPIC_HELP entry missing from index; cannot verify flag")
        self.assertFalse(
            entries["dice"]["is_command"],
            "TOPIC_HELP entry 'dice' should have is_command=False in index payload"
        )

    def test_multiple_topic_entries_all_false(self):
        """All TOPIC_HELP keys in the index carry is_command=False."""
        from data.help_topics import TOPIC_HELP
        entries = self._get_index_entries()
        for topic in TOPIC_HELP:
            key = topic.key
            if key not in entries:
                continue  # access-gated entry absent — that's fine
            self.assertFalse(
                entries[key]["is_command"],
                f"TOPIC_HELP key {key!r} should carry is_command=False in index"
            )

    def test_is_command_is_bool_not_truthy_value(self):
        """is_command is strictly a JSON boolean (true/false), not 0/1/None."""
        entries = self._get_index_entries()
        for key, e in entries.items():
            v = e["is_command"]
            self.assertIsInstance(
                v, bool,
                f"Entry {key!r}: is_command should be bool, got {type(v).__name__!r}"
            )


class TestReferenceSearchIsCommandPayload(unittest.TestCase):
    """handle_reference_search also carries is_command in result payloads."""

    def _search(self, q, admin=False):
        mgr = _make_mixed_mgr()
        api = _make_api(mgr, admin=admin)
        resp = _run(api.handle_reference_search(_FakeReq(query={"q": q})))
        data = json.loads(resp.text)
        return {e["key"]: e for e in data["results"]}

    def test_search_results_carry_is_command(self):
        results = self._search("look")
        self.assertIn("look", results, "'look' missing from search results")
        self.assertIn("is_command", results["look"],
                      "is_command missing from search result entry")
        self.assertTrue(results["look"]["is_command"],
                        "Command 'look' should be is_command=True in search results")

    def test_search_topic_result_is_command_false(self):
        results = self._search("dice")
        self.assertIn("dice", results, "'dice' topic missing from search results")
        self.assertFalse(results["dice"]["is_command"],
                         "Topic 'dice' should be is_command=False in search results")


if __name__ == "__main__":
    unittest.main()
