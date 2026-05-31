# -*- coding: utf-8 -*-
"""
Tests for the guides reorganization (May 2026).

What this drop changed
----------------------
1. ``data/guides/`` now contains 24 guides (was 11), each with a YAML
   frontmatter block declaring ``category``, ``order``, ``summary`` and
   ``tags``.
2. ``server/web_portal.py:_load_guides()`` parses that frontmatter and
   sorts entries by (category, intra-order, title).
3. ``GET /api/portal/guides`` returns ``{guides: [...], categories: [...]}``
   where ``categories`` is the server-authored ordered list of
   {key, label, blurb} that the portal JS renders headers from. This
   keeps the portal JS category-agnostic — adding a new category is a
   one-place edit in ``_CATEGORY_TABLE``.
4. ``static/portal.html`` was rewritten to render category sections with
   a search box that filters cards by title/summary/tag.

Tests verify
------------
A. Content audit — every shipped guide has valid frontmatter pointing at a
   known category, an integer order, a non-empty summary, and a list of
   tags. Catches the "phantom-undelivered" failure mode where a guide
   ships without metadata and lands in the trailing "Other" bucket.
B. Loader behaviour — the loader produces the expected sorted index with
   proper titles (the legacy "# SW_MUSH Detailed Systems Guide #N" H1 is
   ignored), the categories payload only includes categories that have at
   least one guide, and the per-guide content excludes the frontmatter.
C. Endpoint shape — ``handle_guides`` emits both ``guides`` and
   ``categories`` keys; ``handle_guide_content`` still returns a working
   markdown payload for every slug.
D. Portal HTML contract — the JS uses the server's category metadata
   (renders ``c.label`` / ``c.blurb`` / ``c.key`` from the response) and
   does NOT hardcode the human-readable category labels in the static
   HTML. Mirrors the extensibility contract test that already guards the
   reference surface.
"""
import asyncio
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

GUIDES_DIR = os.path.join(PROJECT_ROOT, "data", "guides")
PORTAL_HTML = os.path.join(PROJECT_ROOT, "static", "portal.html")

# Known category keys, mirroring _CATEGORY_TABLE in server/web_portal.py.
# Kept here as an explicit allow-list so that if the table changes server-side
# without an intentional update to the guides themselves, the audit test
# fails loudly rather than silently routing guides into "Other".
KNOWN_CATEGORIES = {
    "foundations", "combat", "galaxy", "economy", "paths", "community",
}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeReq:
    """Just enough of aiohttp's Request for the handlers we test."""
    def __init__(self, headers=None, query=None, match_info=None):
        self.headers = headers or {}
        self.query = query or {}
        self.match_info = match_info or {}


# ── A. Content audit ───────────────────────────────────────────────────────

class TestGuideFrontmatterAudit(unittest.TestCase):
    """Every guide in data/guides/ has valid, well-formed frontmatter."""

    @classmethod
    def setUpClass(cls):
        import yaml  # noqa: F401  — pyyaml is in requirements.txt
        cls.yaml = yaml
        cls.files = sorted(
            f for f in os.listdir(GUIDES_DIR)
            if f.endswith(".md") and f.startswith("Guide_")
        )

    def test_expected_guide_count(self):
        """24 guides currently ship. The number is asserted exactly so
        adding or removing a guide is a deliberate test edit."""
        self.assertEqual(
            len(self.files), 24,
            f"expected 24 guides in {GUIDES_DIR}, found {len(self.files)}: "
            f"{self.files}"
        )

    def _read_frontmatter(self, fname):
        with open(os.path.join(GUIDES_DIR, fname), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(
            text.startswith("---\n"),
            f"{fname}: missing leading frontmatter delimiter"
        )
        end = text.find("\n---\n", 4)
        self.assertGreater(end, 4, f"{fname}: missing closing frontmatter delimiter")
        meta = self.yaml.safe_load(text[4:end])
        self.assertIsInstance(
            meta, dict, f"{fname}: frontmatter is not a YAML mapping"
        )
        return meta, text[end + 5:]

    def test_every_guide_has_required_fields(self):
        """Frontmatter must declare category, order, summary, tags."""
        required = {"category", "order", "summary", "tags"}
        for fname in self.files:
            meta, _ = self._read_frontmatter(fname)
            missing = required - set(meta.keys())
            self.assertFalse(
                missing,
                f"{fname}: missing frontmatter keys {sorted(missing)}"
            )

    def test_every_category_is_known(self):
        """No guide may land in 'Other' — categories are deliberate."""
        for fname in self.files:
            meta, _ = self._read_frontmatter(fname)
            self.assertIn(
                meta["category"], KNOWN_CATEGORIES,
                f"{fname}: unknown category {meta['category']!r}; "
                f"valid categories are {sorted(KNOWN_CATEGORIES)}"
            )

    def test_order_is_positive_int(self):
        for fname in self.files:
            meta, _ = self._read_frontmatter(fname)
            self.assertIsInstance(
                meta["order"], int,
                f"{fname}: order must be int, got {type(meta['order']).__name__}"
            )
            self.assertGreater(meta["order"], 0, f"{fname}: order must be > 0")

    def test_summary_present_and_reasonable_length(self):
        for fname in self.files:
            meta, _ = self._read_frontmatter(fname)
            summary = meta["summary"]
            self.assertIsInstance(summary, str, f"{fname}: summary must be string")
            self.assertGreaterEqual(
                len(summary), 20, f"{fname}: summary too short to be useful"
            )
            # Don't gate too aggressively, but flag absurdly long blurbs that
            # would wreck the card grid layout.
            self.assertLess(
                len(summary), 200, f"{fname}: summary too long for a card"
            )

    def test_tags_are_lowercase_strings(self):
        for fname in self.files:
            meta, _ = self._read_frontmatter(fname)
            tags = meta["tags"]
            self.assertIsInstance(tags, list, f"{fname}: tags must be a list")
            self.assertGreater(len(tags), 0, f"{fname}: must have at least one tag")
            for t in tags:
                self.assertIsInstance(t, str, f"{fname}: tag {t!r} not a string")
                self.assertEqual(
                    t, t.lower(),
                    f"{fname}: tag {t!r} must be lowercase (search is case-folded)"
                )

    def test_orders_are_unique_within_category(self):
        """No two guides in the same category share an order value —
        otherwise the display ordering is non-deterministic."""
        per_cat = {}
        for fname in self.files:
            meta, _ = self._read_frontmatter(fname)
            cat = meta["category"]
            order = meta["order"]
            existing = per_cat.setdefault(cat, {})
            self.assertNotIn(
                order, existing,
                f"{fname}: order {order} collides with {existing.get(order)} "
                f"in category {cat!r}"
            )
            existing[order] = fname

    def test_legacy_h1_stripped_from_body(self):
        """The 'SW_MUSH Detailed Systems Guide #N' header was a numbering
        artifact and must not appear in shipped guide bodies — it would
        otherwise be picked up as the title by older loaders."""
        for fname in self.files:
            _, body = self._read_frontmatter(fname)
            first_h1 = re.search(r"^# (.+)$", body, re.MULTILINE)
            self.assertIsNotNone(first_h1, f"{fname}: no H1 found in body")
            title = first_h1.group(1).strip()
            self.assertFalse(
                title.startswith("SW_MUSH Detailed Systems Guide"),
                f"{fname}: first H1 is still the legacy generic header {title!r}"
            )


# ── B. Loader behaviour ────────────────────────────────────────────────────

class TestLoaderBehaviour(unittest.TestCase):
    """``_load_guides()`` parses the shipped guides correctly."""

    def setUp(self):
        # Re-import fresh to ensure module-level state is repopulated.
        import importlib
        import server.web_portal as wp
        importlib.reload(wp)
        wp._load_guides()
        self.wp = wp

    def test_all_24_guides_loaded(self):
        self.assertEqual(len(self.wp._GUIDE_INDEX), 24)

    def test_all_present_categories_in_payload(self):
        """Every category that has at least one guide is in
        _GUIDE_CATEGORIES; none of the six categories should be missing
        given the canonical content."""
        keys = [c["key"] for c in self.wp._GUIDE_CATEGORIES]
        for k in KNOWN_CATEGORIES:
            self.assertIn(k, keys, f"category {k!r} should be present")

    def test_category_order_is_table_order(self):
        """The order of categories in the payload matches the table —
        foundations first, community last."""
        keys = [c["key"] for c in self.wp._GUIDE_CATEGORIES]
        self.assertEqual(keys[0], "foundations")
        # community must come after paths must come after economy etc.
        ordered = ["foundations", "combat", "galaxy", "economy", "paths", "community"]
        # The payload is a subset of the table; preserve relative ordering.
        filtered = [k for k in ordered if k in keys]
        self.assertEqual(keys[:len(filtered)], filtered)

    def test_each_category_has_label_and_blurb(self):
        for c in self.wp._GUIDE_CATEGORIES:
            self.assertIn("label", c)
            self.assertIn("blurb", c)
            self.assertTrue(c["label"])
            self.assertTrue(c["blurb"])

    def test_titles_use_real_h1_not_legacy_header(self):
        """The title shown to players must be the meaningful H1, not
        the legacy 'SW_MUSH Detailed Systems Guide #N' line."""
        for g in self.wp._GUIDE_INDEX:
            self.assertFalse(
                g["title"].startswith("SW_MUSH Detailed Systems Guide"),
                f"{g['slug']}: title {g['title']!r} still uses legacy H1"
            )

    def test_guide_content_has_no_frontmatter(self):
        """``_GUIDE_CONTENT[slug]`` returns the body sans the YAML block."""
        for g in self.wp._GUIDE_INDEX:
            content = self.wp._GUIDE_CONTENT[g["slug"]]
            self.assertFalse(
                content.startswith("---"),
                f"{g['slug']}: served content still contains frontmatter"
            )

    def test_guides_sorted_by_category_then_order(self):
        """Within each category, guides appear in ascending order; categories
        themselves follow the table order."""
        seen_cats = []
        last_order_in_cat = {}
        for g in self.wp._GUIDE_INDEX:
            cat = g["category"]
            if cat not in seen_cats:
                seen_cats.append(cat)
                last_order_in_cat[cat] = -1
            self.assertGreater(
                g["order"], last_order_in_cat[cat],
                f"guide {g['slug']} (order {g['order']}) out of sequence "
                f"in category {cat}"
            )
            last_order_in_cat[cat] = g["order"]

        # seen_cats must be a prefix-respecting projection of _CATEGORY_TABLE
        table_keys = [c["key"] for c in self.wp._CATEGORY_TABLE]
        self.assertEqual(
            seen_cats, [k for k in table_keys if k in seen_cats]
        )

    def test_slugs_unique(self):
        slugs = [g["slug"] for g in self.wp._GUIDE_INDEX]
        self.assertEqual(len(slugs), len(set(slugs)), "duplicate slug detected")

    def test_summaries_and_tags_propagated(self):
        for g in self.wp._GUIDE_INDEX:
            self.assertIsInstance(g["summary"], str)
            self.assertTrue(g["summary"], f"{g['slug']}: empty summary")
            self.assertIsInstance(g["tags"], list)
            self.assertTrue(g["tags"], f"{g['slug']}: empty tags")


# ── C. Endpoint shape ──────────────────────────────────────────────────────

class TestGuideEndpoints(unittest.TestCase):

    def setUp(self):
        import importlib
        import server.web_portal as wp
        importlib.reload(wp)
        self.wp = wp
        # Minimal PortalAPI instance — handlers we test only touch the
        # module-level guide state, not DB or session_mgr.
        self.api = wp.PortalAPI(db=None, session_mgr=None, game=None)

    def test_handle_guides_shape(self):
        resp = _run(self.api.handle_guides(_FakeReq()))
        body = json.loads(resp.body)
        self.assertIn("guides", body)
        self.assertIn("categories", body)
        self.assertIsInstance(body["guides"], list)
        self.assertIsInstance(body["categories"], list)
        self.assertEqual(len(body["guides"]), 24)
        # Categories are objects with key/label/blurb.
        for c in body["categories"]:
            self.assertIn("key", c)
            self.assertIn("label", c)
            self.assertIn("blurb", c)

    def test_handle_guides_entries_include_category_metadata(self):
        """Each guide entry exposes the fields the JS uses for filtering
        and rendering."""
        resp = _run(self.api.handle_guides(_FakeReq()))
        body = json.loads(resp.body)
        for g in body["guides"]:
            for field in ("slug", "title", "category", "summary", "tags", "order"):
                self.assertIn(field, g, f"{g.get('slug')}: missing {field}")

    def test_handle_guide_content_returns_body_for_every_slug(self):
        """Every guide listed in the index is reachable by slug."""
        index_resp = _run(self.api.handle_guides(_FakeReq()))
        index = json.loads(index_resp.body)["guides"]
        for g in index:
            req = _FakeReq(match_info={"slug": g["slug"]})
            resp = _run(self.api.handle_guide_content(req))
            self.assertEqual(resp.status, 200, f"404 for slug {g['slug']}")
            body = json.loads(resp.body)
            self.assertEqual(body["slug"], g["slug"])
            self.assertEqual(body["title"], g["title"])
            self.assertTrue(body["content"], f"{g['slug']}: empty content")
            self.assertFalse(
                body["content"].startswith("---"),
                f"{g['slug']}: frontmatter leaked into content payload"
            )

    def test_unknown_slug_returns_404(self):
        req = _FakeReq(match_info={"slug": "totally-not-a-real-guide"})
        resp = _run(self.api.handle_guide_content(req))
        self.assertEqual(resp.status, 404)


# ── D. Portal HTML contract ────────────────────────────────────────────────

class TestPortalHTMLContract(unittest.TestCase):
    """The portal JS reads category metadata from the API — it must not
    hardcode category labels or blurbs in the static HTML."""

    @classmethod
    def setUpClass(cls):
        with open(PORTAL_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    def test_renderGuides_present(self):
        self.assertIn("function renderGuides", self.html)

    def test_renderGuides_consumes_categories_from_api(self):
        """The function must reference data.categories — not a hardcoded list."""
        # Pull the renderGuides body out and assert key constructs.
        m = re.search(
            r"async function renderGuides\(el\).+?\n\}",
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m, "renderGuides function not found")
        fn = m.group(0)
        self.assertIn("data.categories", fn,
                      "renderGuides must read categories from the API response")
        self.assertIn("data.guides", fn)
        # And it must iterate the categories, not assume keys.
        self.assertTrue(
            re.search(r"categories\.map", fn) or re.search(r"for.*of\s+categories", fn),
            "renderGuides must iterate the categories array"
        )

    def test_filterGuides_present(self):
        """Live search wired up."""
        self.assertIn("function filterGuides", self.html)
        self.assertIn("guide-search", self.html)

    def test_no_hardcoded_category_labels_in_html(self):
        """The category labels live in web_portal.py. The static HTML
        must not contain any of the human-readable labels as bare string
        literals — that would mean adding a 7th category requires an
        HTML edit, which is the exact failure mode we're avoiding.

        We scan for the **display labels** as quoted JS string literals.
        The category KEYS (foundations, etc.) may appear in class names
        and that's fine — those are stable identifiers, not user copy.
        """
        forbidden_labels = [
            '"Foundations"', "'Foundations'",
            '"Combat & Survival"', "'Combat & Survival'",
            '"The Galaxy"', "'The Galaxy'",
            '"Economy & Trade"', "'Economy & Trade'",
            '"Paths & Specialties"', "'Paths & Specialties'",
            '"Community & Story"', "'Community & Story'",
        ]
        for label in forbidden_labels:
            self.assertNotIn(
                label, self.html,
                f"hardcoded category label {label} found in portal.html — "
                f"labels must come from /api/portal/guides response, not be "
                f"baked into the JS"
            )

    def test_no_hardcoded_category_blurbs_in_html(self):
        """Same principle for the per-category blurbs."""
        # Sample distinctive substrings from each blurb in _CATEGORY_TABLE.
        forbidden_phrases = [
            "Read these first",                          # foundations
            "things that can kill you",                  # combat
            "Space travel, security zones",              # galaxy
            "ways to earn a living",                     # economy
            "Force-sensitive training tracks",           # paths
            "Factions, cities, communication",           # community
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(
                phrase, self.html,
                f"hardcoded category blurb fragment {phrase!r} found in "
                f"portal.html — blurbs must come from the API response"
            )

    def test_nav_link_to_guides_still_present(self):
        """Don't accidentally drop the nav link during the rewrite."""
        self.assertIn('href="#/guides"', self.html)

    def test_guide_card_class_used(self):
        """JS marks each card with .guide-card so filterGuides can find them."""
        self.assertIn("guide-card", self.html)

    def test_markdown_renderer_supports_links(self):
        """Guides use [label](#/guide/slug) cross-references that must
        survive renderMarkdown() and produce <a href> tags in the DOM.
        Without this, every link renders as literal '[label](url)' text."""
        m = re.search(
            r"function renderMarkdown\(md\)\s*\{[\s\S]*?\n\}",
            self.html,
        )
        self.assertIsNotNone(m, "renderMarkdown not found")
        fn = m.group(0)
        self.assertIn("[", fn)  # sanity
        self.assertIn(
            "\\[([^\\]]+)\\]\\(", fn,
            "renderMarkdown is missing the [label](url) link regex — "
            "cross-references will render as literal markdown"
        )
        # And reject javascript: URLs.
        self.assertIn(
            "#\\/|https?", fn,
            "renderMarkdown's link regex should restrict allowed schemes "
            "(hash / http / https / mailto) to refuse javascript: payloads"
        )


# ── E. Rewrite-pattern audit (Drop 2: gold-standard rewrites) ──────────────

class TestGoldStandardRewrites(unittest.TestCase):
    """Locks in the rewrite shape for the three pilot guides:
    Core Mechanics, Ground Combat, Security Zones.

    These tests are intentionally specific — they catch the failure mode
    of someone accidentally re-introducing developer notes, file paths,
    or stale 'Guide #N' numbering into the pilot set. When more older
    guides are rewritten in future drops, this test class should be
    widened to cover them too (just add slugs to PILOTS)."""

    PILOTS = (
        "ground-combat",
        "security-zones",
        "organizations-factions",
        "director-ai",
    )

    @classmethod
    def setUpClass(cls):
        import importlib
        import server.web_portal as wp
        importlib.reload(wp)
        wp._load_guides()
        cls.contents = {
            g["slug"]: wp._GUIDE_CONTENT[g["slug"]]
            for g in wp._GUIDE_INDEX
            if g["slug"] in cls.PILOTS
        }
        # Sanity: we found all three.
        assert set(cls.contents.keys()) == set(cls.PILOTS), (
            f"missing pilot guides: {set(cls.PILOTS) - set(cls.contents.keys())}"
        )

    def test_no_developer_internals_section(self):
        for slug, body in self.contents.items():
            self.assertNotIn(
                "Developer Internals", body,
                f"{slug}: 'Developer Internals' subsection leaked into "
                f"rewritten guide — dev-half should be fully gone"
            )
            self.assertNotIn(
                "🔧", body,
                f"{slug}: wrench emoji from dev block leaked"
            )

    def test_no_redundant_player_rules_label(self):
        """The label '### Player Rules' was a paired-section marker. After
        the rewrite there's no developer half to pair with — the label is
        noise. Variants like '### Player Rules (Staff Only)' are fine."""
        for slug, body in self.contents.items():
            # Match the exact bare heading on its own line.
            self.assertFalse(
                re.search(r"^### Player Rules\s*$", body, re.MULTILINE),
                f"{slug}: bare '### Player Rules' heading still present"
            )

    def test_no_file_path_references(self):
        """Player-facing guides must not reference source file paths or
        line numbers."""
        path_pat = re.compile(
            r"`(engine|parser|server|db|data|tests|static)/[a-z_]+"
            r"\.(py|yaml|yml|html|js)`"
        )
        for slug, body in self.contents.items():
            m = path_pat.search(body)
            self.assertIsNone(
                m,
                f"{slug}: file-path reference {m.group(0) if m else ''} "
                f"appears in player-facing content"
            )
            line_pat = re.compile(r"\(lines?\s+\d+[-–]?\d*\)")
            m = line_pat.search(body)
            self.assertIsNone(
                m,
                f"{slug}: line-number reference {m.group(0) if m else ''} "
                f"appears in player-facing content"
            )

    def test_no_implementation_status_or_file_reference_section(self):
        """The 'Implementation Status' and 'File Reference' sections were
        dev-internal scaffolding and have no place in a player guide."""
        for slug, body in self.contents.items():
            self.assertNotIn(
                "Implementation Status", body,
                f"{slug}: 'Implementation Status' section not removed"
            )
            self.assertNotIn(
                "## 12. File Reference", body,
                f"{slug}: 'File Reference' section not removed"
            )

    def test_no_legacy_guide_number_crossrefs(self):
        """Cross-references should use topic + portal-link form
        '[Topic](#/guide/slug)', not 'Guide #N'. The latter would go stale
        the moment a guide is reordered."""
        for slug, body in self.contents.items():
            m = re.search(r"Guide #\d+", body)
            self.assertIsNone(
                m,
                f"{slug}: legacy 'Guide #N' cross-reference found — "
                f"use [Topic](#/guide/slug) instead"
            )

    def test_crossref_slugs_all_resolve(self):
        """Every [label](#/guide/slug) link in a rewritten guide points
        to a slug that actually exists in the loaded index."""
        import server.web_portal as wp
        all_slugs = {g["slug"] for g in wp._GUIDE_INDEX}
        link_pat = re.compile(r"\]\(#/guide/([a-z0-9-]+)\)")
        for slug, body in self.contents.items():
            for target in link_pat.findall(body):
                self.assertIn(
                    target, all_slugs,
                    f"{slug}: cross-reference to unknown slug {target!r}"
                )

    def test_has_how_to_read_intro(self):
        """The gold-standard style opens with a 'How to Read This Guide'
        intro that orients the reader."""
        for slug, body in self.contents.items():
            self.assertIn(
                "## How to Read This Guide", body,
                f"{slug}: missing 'How to Read This Guide' intro section"
            )

    def test_lean_author_block(self):
        """The four-line meta block ('BTGlass80 — Month YYYY' /
        'Guide Version 1.0') was stripped down to a one-line attribution
        in the rewrite. Catch any guide that re-introduced the verbose
        version."""
        for slug, body in self.contents.items():
            self.assertNotIn(
                "Guide Version 1.0", body,
                f"{slug}: verbose meta block (Guide Version 1.0) not removed"
            )


# ── F. Era cleanliness audit (CW correctness across all guides) ────────────

class TestCloneWarsEraCleanliness(unittest.TestCase):
    """Active era is Clone Wars (~20 BBY). Galactic Civil War content is
    deprecated reference per the architecture-of-record. This test class
    audits all 24 shipped guides for GCW-era terminology that has snuck in.

    A small allowlist of intentional preservations is documented per file:
    direct WEG R&E rulebook quotes (which must remain accurate as quoted
    material), deliberate forward-references that add CW flavor by
    contrast (e.g. 'the reach the Empire will eventually claim'), and
    canonical rulebook examples that are clearly disclaimed in-text.
    """

    # Per-file intentional preservations. The KEY is the slug; the VALUE
    # is a list of substrings that may legitimately appear in that file.
    # If a GCW-tagged substring matches one of these, it's not counted as
    # a violation.
    ALLOWED_PRESERVATIONS = {
        "weg-d6-core-mechanics": [
            # Death Star kept as canonical Scale=18 reference with disclaimer
            "Death Star scale",
            "no such weapon exists in the Clone Wars era",
        ],
        "character-creation": [
            # Direct WEG R&E rulebook quote — must remain verbatim
            "Han Solo is at the beginning of A New Hope",
            "Luke Skywalker and Obi-Wan Kenobi",
        ],
        "security-zones": [
            # Deliberate forward-reference — adds CW flavor by contrast
            "the reach the Empire will eventually claim",
        ],
        "space-systems": [
            # Y-Wing is canonically a Clone Wars-era design (BTL-B variant)
            "BTL-B Y-Wing",
        ],
    }

    # GCW-era terms that should not appear (except in allowed preservations).
    # Matched as word-boundary patterns.
    FORBIDDEN_PATTERNS = [
        r"\bStormtrooper(?:s)?\b",
        r"\bGalactic Empire\b",
        r"\bRebel Alliance\b",
        r"\bRebellion\b",
        r"\bRebel\b(?! Sourcebook)",
        r"\bEmperor Palpatine\b",
        r"\bDarth Vader\b",
        r"\bLord Vader\b",
        r"\bPrincess Leia\b",
        r"\bHan Solo\b",
        r"\bLuke Skywalker\b",
        r"\bBoba Fett\b",
        r"\bMon Mothma\b",
        # 'Imperial Sourcebook' is a real WEG book — allowed
        r"\bImperial(?! Sourcebook)\b",
        r"\bthe Empire\b",
        r"\bGalactic Civil War\b",
        r"\bDeath Star\b",
        r"\bGCW\b",
        r"\bYavin\b",
        r"\bEndor\b",
        r"\bHoth\b",
        r"\bX-[Ww]ing\b",
        r"\bA-[Ww]ing\b",
        r"\bY-[Ww]ing\b",
        r"\bTIE [BFI]\w+\b",
    ]

    @classmethod
    def setUpClass(cls):
        import importlib
        import server.web_portal as wp
        importlib.reload(wp)
        wp._load_guides()
        cls.contents = {
            g["slug"]: wp._GUIDE_CONTENT[g["slug"]]
            for g in wp._GUIDE_INDEX
        }
        cls.compiled = [re.compile(p) for p in cls.FORBIDDEN_PATTERNS]

    def _violations(self, slug, body):
        """Return list of (line_no, line_text, pattern_matched) for each
        GCW-era term that isn't whitelisted for this slug."""
        allowed = self.ALLOWED_PRESERVATIONS.get(slug, [])
        out = []
        for i, line in enumerate(body.split("\n"), start=1):
            for pat in self.compiled:
                m = pat.search(line)
                if not m:
                    continue
                # Is this hit covered by an allowed preservation?
                if any(allow in line for allow in allowed):
                    continue
                out.append((i, line.strip()[:120], m.group(0)))
        return out

    def test_all_guides_are_era_clean(self):
        """Per-file assertion: produce a focused failure message naming
        the offending line(s) and pattern(s) so the fix is one edit
        away. Every guide must pass — no per-slug deferrals. If a guide
        needs a structural rewrite first, do that, then re-run this test."""
        all_violations = {}
        for slug, body in self.contents.items():
            viols = self._violations(slug, body)
            if viols:
                all_violations[slug] = viols
        if all_violations:
            detail = []
            for slug, viols in all_violations.items():
                detail.append(f"\n  {slug}: {len(viols)} violation(s)")
                for n, text, pat in viols:
                    detail.append(f"    line {n}: matched {pat!r} — {text}")
            self.fail(
                "GCW-era references found in CW-active guides:" +
                "".join(detail)
            )


if __name__ == "__main__":
    unittest.main()

