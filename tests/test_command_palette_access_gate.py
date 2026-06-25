# -*- coding: utf-8 -*-
"""
test_command_palette_access_gate.py — UX Drop 7: reference-index access-gate.

The command palette consumes GET /api/portal/reference.  This test suite
asserts that the endpoint is ACCESS-GATED: a low-access (unauthenticated
or non-admin) caller's index EXCLUDES admin/builder-gated verbs that a
high-access (admin) caller DOES see.

Extends the contract already established in tests/test_session48_portal_retheme.py
(TestReferenceIndex.test_admin_entries_hidden_from_public) with an explicit
palette-centric framing and an additional "admin caller sees admin entries"
counterpart assertion.

Uses the same _make_api_with_corpus fixture pattern as session48 tests.
"""
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
    """Wrap a sync function so it can be awaited."""
    async def _inner(*args, **kwargs):
        return fn(*args, **kwargs)
    return _inner


class _FakeReq:
    """Minimal aiohttp.Request stand-in."""
    def __init__(self, headers=None, query=None, match_info=None):
        self.headers     = headers     or {}
        self.query       = query       or {}
        self.match_info  = match_info  or {}


def _make_corpus_api(admin_caller: bool):
    """Build a PortalAPI with a corpus that includes one admin-gated entry.

    The admin-gated entry (@build) has access_level=2 (BUILDER), which
    exceeds the PLAYER (1) ceiling for non-admin callers.

    Returns the api object ready to call handle_reference_index.
    """
    from data.help_topics import HelpManager, HelpEntry
    from server.web_portal import PortalAPI

    mgr = HelpManager()

    # Public player commands
    mgr.register(HelpEntry(
        key="look",   title="Look",   category="Commands",
        body="Look around the room.",
        summary="Examine your surroundings.",
    ))
    mgr.register(HelpEntry(
        key="attack", title="Attack", category="Combat",
        body="Start a fight.",
        summary="Initiate a melee attack.",
    ))
    mgr.register(HelpEntry(
        key="craft",  title="Craft",  category="Economy",
        body="Make items.",
        summary="Craft an item from a schematic.",
    ))

    # Admin/builder-only entry — must NOT appear for non-admin callers
    mgr.register(HelpEntry(
        key="@build",  title="Build a Room",  category="Admin",
        body="Admin-only: dig a room.",
        access_level=2,   # BUILDER
    ))
    # A second admin entry at ADMIN level (3)
    mgr.register(HelpEntry(
        key="@director", title="Director AI",  category="Admin",
        body="Control the Director.",
        access_level=3,   # ADMIN
    ))
    # An internal sentinel key (dunder-wrapped legacy no-op stub). NOT a
    # typeable verb — the reference endpoint must filter it so the palette
    # never stages it (phantom-verb guard).
    mgr.register(HelpEntry(
        key="__bacta_pack_legacy__", title="(legacy)", category="Internal",
        body="Internal no-op stub.",
        summary="",
    ))

    game = MagicMock()
    game.help_mgr = mgr

    db = MagicMock()

    async def _get_account(_id):
        return {"id": _id, "is_admin": 1 if admin_caller else 0}
    db.get_account = _get_account

    api = PortalAPI(db=db, session_mgr=MagicMock(), game=game)
    if admin_caller:
        # Monkeypatch _optional_auth to simulate an authenticated admin session.
        api._optional_auth = _as_async(lambda _r: 99)
    return api


class TestCommandPaletteAccessGate(unittest.TestCase):
    """The /api/portal/reference endpoint is access-gated.

    The command palette consumes this endpoint exclusively; because the
    server filters by caller access_level, the palette is access-filtered
    for free — no separate palette-side gating is needed or added.
    """

    def _index_keys_for(self, admin: bool) -> set:
        api = _make_corpus_api(admin_caller=admin)
        req = _FakeReq(
            headers={"Authorization": "Bearer tok"} if admin else {}
        )
        resp = _run(api.handle_reference_index(req))
        data = json.loads(resp.text)
        return {e["key"] for e in data["entries"]}

    # ── Non-admin / unauthenticated callers ──────────────────────────────

    def test_player_caller_sees_public_verbs(self):
        """Public/player caller receives the standard player command corpus."""
        keys = self._index_keys_for(admin=False)
        for expected in ("look", "attack", "craft"):
            self.assertIn(
                expected, keys,
                f"Player-visible command {expected!r} missing from index for "
                f"non-admin caller. Keys present: {sorted(keys)!r}"
            )

    def test_player_caller_excluded_from_builder_verb(self):
        """Admin/builder-gated verbs (@build) must NOT appear for non-admin."""
        keys = self._index_keys_for(admin=False)
        self.assertNotIn(
            "@build", keys,
            "Admin-gated @build verb leaked to non-admin caller's index. "
            "Command palette would expose it without permission."
        )

    def test_player_caller_excluded_from_admin_verb(self):
        """ADMIN-level verbs (@director) must NOT appear for non-admin."""
        keys = self._index_keys_for(admin=False)
        self.assertNotIn(
            "@director", keys,
            "Admin-level @director verb leaked to non-admin caller's index."
        )

    # ── Admin callers ────────────────────────────────────────────────────

    def test_admin_caller_sees_gated_verbs(self):
        """An authenticated admin sees the admin-gated entries."""
        keys = self._index_keys_for(admin=True)
        self.assertIn(
            "@build", keys,
            "Admin caller should see @build in the reference index."
        )
        self.assertIn(
            "@director", keys,
            "Admin caller should see @director in the reference index."
        )

    def test_admin_caller_also_sees_player_verbs(self):
        """Admin callers see player verbs too (not just admin-only entries)."""
        keys = self._index_keys_for(admin=True)
        for expected in ("look", "attack", "craft"):
            self.assertIn(
                expected, keys,
                f"Admin caller missing player verb {expected!r}."
            )

    # ── Phantom-verb guard: internal sentinel keys filtered ──────────────

    def test_dunder_sentinel_key_excluded(self):
        """Dunder-wrapped sentinel keys must NOT appear in the index.

        ``__bacta_pack_legacy__`` is an internal no-op stub, not a typeable
        verb. The reference endpoint filters dunder-wrapped keys so the
        command palette can never stage one (it would dispatch to nothing
        useful and read as a phantom verb).
        """
        for admin in (False, True):
            keys = self._index_keys_for(admin=admin)
            self.assertNotIn(
                "__bacta_pack_legacy__", keys,
                f"Internal sentinel key leaked to {'admin' if admin else 'player'} "
                f"index — palette would surface a non-verb."
            )

    # ── Shape contract (palette consumes these fields) ───────────────────

    def test_entry_shape_for_palette(self):
        """Each entry in the index carries the fields the palette renders.

        The palette uses: key (verb to stage), title, category, summary.
        All must be present even if empty.
        """
        api = _make_corpus_api(admin_caller=False)
        resp = _run(api.handle_reference_index(_FakeReq()))
        data = json.loads(resp.text)
        self.assertIn("entries", data)
        self.assertGreater(len(data["entries"]), 0)
        for entry in data["entries"]:
            for field in ("key", "title", "category", "summary"):
                self.assertIn(
                    field, entry,
                    f"Palette-required field {field!r} missing from entry: {entry!r}"
                )


if __name__ == "__main__":
    unittest.main()
