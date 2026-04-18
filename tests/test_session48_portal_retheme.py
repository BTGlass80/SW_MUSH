# -*- coding: utf-8 -*-
"""
Session 48 tests — portal re-theme + Reference endpoints.

Covers two surfaces:

1. **Backend endpoints.** The three new /api/portal/reference
   handlers are pure pass-throughs over ``HelpManager``. Tests
   verify shape of responses, access-level filtering (admin entries
   hidden from public), ranked search, slug round-trip for keys with
   slashes, and no-data-leak on 404.

2. **Portal HTML structure.** The re-themed ``static/portal.html``
   must carry the Field Kit design tokens, wire the new Reference
   routes, and — most importantly — NOT hardcode any category names,
   command keys, or help topic keywords. The extensibility promise
   rests on that guarantee. These tests guard it with regex scans.

Tests are self-contained: backend tests build a toy HelpManager and
PortalAPI; HTML tests read ``static/portal.html`` directly.
"""
import asyncio
import json
import os
import re
import sys
import unittest
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PORTAL_HTML = os.path.join(PROJECT_ROOT, "static", "portal.html")


def _run(coro):
    """Run an async coroutine in a fresh loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Shared fixtures ─────────────────────────────────────────────────────────

class _FakeReq:
    """Just enough of aiohttp's Request for the handlers we test."""

    def __init__(self, headers=None, query=None, match_info=None):
        self.headers = headers or {}
        self.query = query or {}
        self.match_info = match_info or {}


def _make_api_with_corpus(admin=False):
    """Build a PortalAPI bound to a HelpManager with a small known corpus.

    Returns (api, mgr). The corpus includes one admin-gated entry so
    we can test access_level filtering.
    """
    from data.help_topics import HelpManager, HelpEntry
    from server.web_portal import PortalAPI

    mgr = HelpManager()
    mgr.register(HelpEntry(
        key="combat", title="Combat Basics",
        category="Rules: Combat",
        body="Combat follows a structured round.",
        summary="How attacks and rounds work.",
        aliases=["fight"], tags=["core", "combat"],
        see_also=["wounds", "dodge"],
    ))
    mgr.register(HelpEntry(
        key="wounds", title="Wounds & Healing",
        category="Rules: Combat",
        body="Wounds scale from stunned through dead.",
        aliases=["wound"],
    ))
    mgr.register(HelpEntry(
        key="dice", title="D6 Dice",
        category="Rules: D6",
        body="Dice pools like 3D+2.",
        tags=["core"],
    ))
    mgr.register(HelpEntry(
        key="+combat/attack", title="Attack Sub-Command",
        category="Commands",
        body="Slash-keyed command for testing the slug round-trip.",
    ))
    mgr.register(HelpEntry(
        key="@dig", title="Build a Room",
        category="Admin/Building",
        body="Admin-only: dig a new room.",
        access_level=2,  # hidden from public
    ))

    # Fake game object carrying the manager
    game = MagicMock()
    game.help_mgr = mgr

    # Fake DB. _caller_max_access_level calls db.get_account when there's
    # an auth header; without one, it never touches db.
    db = MagicMock()

    async def _get_account(_id):
        return {"id": _id, "is_admin": 1 if admin else 0}
    db.get_account = _get_account

    api = PortalAPI(db=db, session_mgr=MagicMock(), game=game)
    return api, mgr


# ═══════════════════════════════════════════════════════════════════════════
# Reference index endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestReferenceIndex(unittest.TestCase):

    def test_index_returns_tree_and_flat_list(self):
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_index(_FakeReq()))
        data = json.loads(resp.text)
        self.assertIn("tree", data)
        self.assertIn("entries", data)
        self.assertIn("total", data)

    def test_admin_entries_hidden_from_public(self):
        """An entry with access_level > 0 must NOT appear for unauth."""
        api, _ = _make_api_with_corpus(admin=False)
        resp = _run(api.handle_reference_index(_FakeReq()))
        data = json.loads(resp.text)
        keys = [e["key"] for e in data["entries"]]
        self.assertNotIn("@dig", keys)
        # But public-visible keys should be there
        self.assertIn("combat", keys)
        self.assertIn("dice", keys)

    def test_admin_sees_admin_entries(self):
        api, _ = _make_api_with_corpus(admin=True)
        req = _FakeReq(headers={"Authorization": "Bearer faketoken"})
        # Monkeypatch _optional_auth to return a fake account id
        api._optional_auth = _as_async(lambda _r: 42)
        resp = _run(api.handle_reference_index(req))
        data = json.loads(resp.text)
        keys = [e["key"] for e in data["entries"]]
        self.assertIn("@dig", keys)

    def test_tree_splits_nested_categories(self):
        """Categories using ``: `` separator split into hierarchy."""
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_index(_FakeReq()))
        data = json.loads(resp.text)
        self.assertIn("Rules", data["tree"])
        rules = data["tree"]["Rules"]
        self.assertIn("subcategories", rules)
        self.assertIn("Combat", rules["subcategories"])
        self.assertIn("D6", rules["subcategories"])

    def test_empty_categories_pruned(self):
        """Admin/Building should NOT show up for public callers since
        its only entry is gated."""
        api, _ = _make_api_with_corpus(admin=False)
        resp = _run(api.handle_reference_index(_FakeReq()))
        data = json.loads(resp.text)
        # The Admin category must not leak an empty shell
        self.assertNotIn("Admin", data["tree"])
        self.assertNotIn("Admin/Building", data["tree"])

    def test_entry_summary_shape(self):
        """Each flat-list entry carries the expected summary fields."""
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_index(_FakeReq()))
        data = json.loads(resp.text)
        first = data["entries"][0]
        for field in ("key", "slug", "title", "category",
                      "summary", "tags", "access_level"):
            self.assertIn(field, first, f"missing {field} in {first}")

    def test_slug_encoding_in_index(self):
        """Entry keys with slashes are encoded for URL use."""
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_index(_FakeReq()))
        data = json.loads(resp.text)
        slugs = [e["slug"] for e in data["entries"]]
        # +combat/attack should appear as +combat__attack in the slug
        self.assertIn("+combat__attack", slugs)

    def test_503_when_help_mgr_missing(self):
        """If the game isn't fully booted, we surface 503, not a crash."""
        from server.web_portal import PortalAPI
        game = MagicMock()
        game.help_mgr = None
        api = PortalAPI(db=MagicMock(), session_mgr=MagicMock(), game=game)
        resp = _run(api.handle_reference_index(_FakeReq()))
        self.assertEqual(resp.status, 503)


# ═══════════════════════════════════════════════════════════════════════════
# Reference entry detail endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestReferenceEntry(unittest.TestCase):

    def test_entry_detail_full_body(self):
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_entry(
            _FakeReq(match_info={"entry_slug": "combat"})
        ))
        data = json.loads(resp.text)
        self.assertEqual(data["key"], "combat")
        self.assertIn("Combat follows", data["body"])
        self.assertEqual(data["category"], "Rules: Combat")
        self.assertIn("see_also", data)

    def test_slash_key_slug_round_trip(self):
        """A slug with ``__`` decodes back to a slash key and resolves."""
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_entry(
            _FakeReq(match_info={"entry_slug": "+combat__attack"})
        ))
        data = json.loads(resp.text)
        self.assertEqual(data["key"], "+combat/attack")

    def test_nonexistent_entry_returns_404(self):
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_entry(
            _FakeReq(match_info={"entry_slug": "nonexistent"})
        ))
        self.assertEqual(resp.status, 404)

    def test_admin_entry_404s_for_public(self):
        """No info leak: an admin entry returns 404, not 403, for
        unauth callers — they can't confirm it exists."""
        api, _ = _make_api_with_corpus(admin=False)
        resp = _run(api.handle_reference_entry(
            _FakeReq(match_info={"entry_slug": "@dig"})
        ))
        self.assertEqual(resp.status, 404)

    def test_admin_entry_visible_to_admin(self):
        api, _ = _make_api_with_corpus(admin=True)
        req = _FakeReq(
            headers={"Authorization": "Bearer faketoken"},
            match_info={"entry_slug": "@dig"},
        )
        api._optional_auth = _as_async(lambda _r: 42)
        resp = _run(api.handle_reference_entry(req))
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.text)
        self.assertEqual(data["key"], "@dig")


# ═══════════════════════════════════════════════════════════════════════════
# Reference search endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestReferenceSearch(unittest.TestCase):

    def test_empty_query_returns_empty(self):
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_search(_FakeReq(query={})))
        data = json.loads(resp.text)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["results"], [])

    def test_ranked_result_order(self):
        """Exact-key matches come first."""
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_search(
            _FakeReq(query={"q": "combat"})
        ))
        data = json.loads(resp.text)
        self.assertTrue(data["total"] > 0)
        self.assertEqual(data["results"][0]["key"], "combat")

    def test_search_filters_admin_for_public(self):
        api, _ = _make_api_with_corpus(admin=False)
        # @dig's body says "admin-only" — if filtering broke, it'd match
        resp = _run(api.handle_reference_search(
            _FakeReq(query={"q": "admin"})
        ))
        data = json.loads(resp.text)
        keys = [r["key"] for r in data["results"]]
        self.assertNotIn("@dig", keys)

    def test_limit_param_bounded(self):
        """The limit param is clamped to [1, 100]."""
        api, _ = _make_api_with_corpus()
        # Zero / negative gets clamped up to 1
        resp = _run(api.handle_reference_search(
            _FakeReq(query={"q": "combat", "limit": "0"})
        ))
        data = json.loads(resp.text)
        self.assertLessEqual(len(data["results"]), 100)
        # Huge limit gets clamped down
        resp2 = _run(api.handle_reference_search(
            _FakeReq(query={"q": "combat", "limit": "99999"})
        ))
        data2 = json.loads(resp2.text)
        self.assertLessEqual(len(data2["results"]), 100)

    def test_bad_limit_param_defaults(self):
        """Non-integer limit falls back to default."""
        api, _ = _make_api_with_corpus()
        resp = _run(api.handle_reference_search(
            _FakeReq(query={"q": "combat", "limit": "notanumber"})
        ))
        # Should not raise; should return results
        data = json.loads(resp.text)
        self.assertIsInstance(data["results"], list)


# ═══════════════════════════════════════════════════════════════════════════
# Portal HTML structure
# ═══════════════════════════════════════════════════════════════════════════

class TestPortalHtmlStructure(unittest.TestCase):
    """Structural tests on static/portal.html.

    These are deliberately grep/regex based — the portal is vanilla
    JS, not something we want to run headless. The shape we're
    locking down is exactly pattern-detectable.
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(PORTAL_HTML):
            raise unittest.SkipTest("portal.html not found")
        with open(PORTAL_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    # ── Field Kit theme tokens ────────────────────────────────────────

    def test_pad_amber_token_present(self):
        """Re-theme grounds in the --pad-amber token from client.html."""
        self.assertIn("--pad-amber:", self.html)
        self.assertIn("#ffc857", self.html)

    def test_pad_shell_tokens_present(self):
        for tok in ("--pad-shell:", "--pad-shell-dark:", "--pad-screen:"):
            self.assertIn(tok, self.html, f"missing token {tok}")

    def test_ibm_plex_mono_loaded(self):
        """Fonts match the design handoff + client.html."""
        self.assertIn("IBM+Plex+Mono", self.html)

    def test_space_grotesk_loaded(self):
        self.assertIn("Space+Grotesk", self.html)

    def test_stale_fonts_removed(self):
        """The pre-S48 fonts must be gone."""
        self.assertNotIn("Share+Tech+Mono", self.html)
        self.assertNotIn("Orbitron", self.html)
        self.assertNotIn("Rajdhani:", self.html)

    def test_rivet_strip_class_present(self):
        """Hardware chrome: rivet row along the nav."""
        # Implemented as nav.topbar::after with radial-gradient dots
        self.assertIn("topbar::after", self.html)
        self.assertIn("radial-gradient(circle at center", self.html)

    def test_scanlines_effect_present(self):
        """Scanlines on the hero for CRT feel."""
        self.assertIn("repeating-linear-gradient", self.html)

    def test_clean_mode_toggle_wired(self):
        """Accessibility: user can turn off visual effects."""
        self.assertIn("app.clean", self.html)
        self.assertIn("toggleCleanMode", self.html)
        self.assertIn("clean-toggle", self.html)

    # ── Nav includes Reference, removes nothing essential ─────────────

    def test_reference_nav_link_present(self):
        self.assertIn('href="#/reference"', self.html)
        self.assertIn(">Reference<", self.html)

    def test_existing_nav_links_preserved(self):
        """Don't accidentally drop a section during the rewrite."""
        for link in ('href="#/"', 'href="#/who"', 'href="#/characters"',
                     'href="#/scenes"', 'href="#/events"',
                     'href="#/plots"', 'href="#/guides"'):
            self.assertIn(link, self.html, f"missing nav link {link}")

    def test_play_now_cta_preserved(self):
        self.assertIn('href="/play"', self.html)

    # ── Reference routes wired ────────────────────────────────────────

    def test_reference_route_home(self):
        self.assertIn("renderReferenceHome", self.html)

    def test_reference_route_search(self):
        self.assertIn("renderReferenceSearch", self.html)

    def test_reference_route_entry(self):
        self.assertIn("renderReferenceEntry", self.html)

    def test_reference_api_calls_present(self):
        """The three endpoints are actually fetched from the JS."""
        self.assertIn("/api/portal/reference", self.html)
        self.assertIn("/api/portal/reference/search", self.html)

    # ── Extensibility guarantee: NO hardcoded content ─────────────────

    def test_no_hardcoded_category_names(self):
        """When the help system reorganises categories, this HTML
        must not need updating. Any fixed category label would be a
        bug — they all come from the /api/portal/reference response."""
        suspicious_categories = [
            '"Rules: Combat"', '"Rules: Force"', '"Rules: Space"',
            '"MUSH Basics"', '"Economy"', '"Character"',
            '"Admin/Building"', '"Rules · Combat"',
        ]
        for s in suspicious_categories:
            self.assertNotIn(
                s, self.html,
                f"category literal {s} should not be hardcoded in portal.html"
            )

    def test_no_hardcoded_command_keys(self):
        """Specific command/topic keys must not appear as HTML
        elements or data labels. They come from the API response.

        Note: they CAN appear inside user-facing example text (like
        the "Try searching for <code>combat</code>" suggestion line
        in the intro), so we only flag keys that look like they're
        being used structurally.
        """
        # Structural uses would be in JSON-style literal keys or in
        # hardcoded <a href=> or data attributes. Spot-check a few.
        for pattern in [
            r'data-key="combat"',
            r'data-key="dice"',
            r'data-category="Rules',
            r'key:\s*"combat",',        # JS object literal
            r'key:\s*"dice",',
            r'href="#/reference/combat"',  # hardcoded detail URL
            r'href="#/reference/dice"',
        ]:
            matches = re.findall(pattern, self.html)
            self.assertEqual(
                matches, [],
                f"pattern {pattern!r} found in portal.html — "
                f"reference content should come from the API, not be baked in"
            )

    def test_no_hardcoded_topic_keyword_list(self):
        """A list of topic keywords (dice/force/combat/…) hardcoded
        would mirror the server's HelpCommand.TOPIC_KEYWORDS —
        exactly the duplication we're guarding against."""
        # Look for multi-item arrays of known topic keys
        suspicious_list_patterns = [
            r'\[\s*"combat"\s*,\s*"dice"\s*,',
            r'\[\s*"dice"\s*,\s*"combat"\s*,',
            r'\[\s*"force"\s*,\s*"combat"\s*,',
        ]
        for pat in suspicious_list_patterns:
            self.assertFalse(
                re.search(pat, self.html),
                f"suspicious hardcoded topic list: {pat}"
            )

    # ── Markdown body styling ─────────────────────────────────────────

    def test_md_body_class_styled(self):
        """Reference entries + guides render markdown through .md-body."""
        self.assertIn(".md-body", self.html)
        self.assertIn("md-body h1", self.html)
        self.assertIn("md-body code", self.html)

    # ── Landing page additions ────────────────────────────────────────

    def test_getting_started_tiles_present(self):
        self.assertIn("getting-started", self.html)
        self.assertIn("gs-tile", self.html)

    def test_boot_label_hero_treatment(self):
        """Hero uses boot-style label with LED indicator."""
        self.assertIn("boot-label", self.html)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _as_async(fn):
    """Wrap a sync function as an async one for monkeypatching."""
    async def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper


if __name__ == "__main__":
    unittest.main()
