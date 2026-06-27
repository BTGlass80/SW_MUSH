# -*- coding: utf-8 -*-
"""
Web `help` onboarding-landing guard (2026-06-27).

What this drop changed
----------------------
In the web client a bare ``help`` (and ``guide``/``+guide``) is intercepted
client-side and opens the in-game Guide overlay (``openGuideBrowser`` in
``static/client.html``). The overlay auto-loads the FIRST guide in the index
when nothing is active yet:

    if (!_guideActiveSlug && data.guides && data.guides.length) {
        loadGuideIntoPane(data.guides[0].slug);
    }

``data.guides[0]`` is whatever the server sorts first — by (category-order,
intra-order, title). The foundations category sorts first, so foundations
``order: 1`` is the guide a brand-new player lands on the moment they type the
single most natural "I'm lost" command: ``help``.

Before this drop that landing guide was **WEG D6 Core Mechanics** — the densest
dice-pool / wild-die / difficulty-number reference in the corpus. The worst
possible first impression for a nervous newcomer. The foundations order was
reshuffled into a new-player journey so the landing is the welcoming onboarding
guide instead:

    1  tutorial-chains        Tutorial Chains & First Character   <- help lands here
    2  character-creation     Character Creation
    3  weg-d6-core-mechanics  WEG D6 Core Mechanics
    4  cp-progression         CP Progression

These tests pin that contract end-to-end so a future frontmatter shuffle that
re-buries the onboarding guide (or re-promotes a dense reference) fails loudly.
Pure data + source-guard; no engine/parser/client behavior changed.
"""
import importlib
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CLIENT_HTML = os.path.join(PROJECT_ROOT, "static", "client.html")

# The new-player onboarding guide (Guide_16_Tutorial_Chains.md → slug below).
# Its own frontmatter summary calls it "the mandatory onboarding path for new
# players" — it is, by design, where `help` should land a brand-new player.
ONBOARDING_SLUG = "tutorial-chains"
# A dense rules reference that must NOT be the first thing `help` shows.
DENSE_REFERENCE_SLUG = "weg-d6-core-mechanics"


class TestHelpLandsOnOnboardingGuide(unittest.TestCase):
    """Server side: the first index entry (web `help` auto-load target)
    is the onboarding guide, not a dense reference."""

    def setUp(self):
        import server.web_portal as wp
        importlib.reload(wp)
        wp._load_guides()
        self.wp = wp
        self.idx = wp._GUIDE_INDEX
        self.by_slug = {g["slug"]: g for g in self.idx}

    def test_onboarding_guide_loaded(self):
        self.assertIn(
            ONBOARDING_SLUG, self.by_slug,
            f"onboarding guide {ONBOARDING_SLUG!r} not loaded",
        )

    def test_onboarding_guide_is_foundations_order_one(self):
        g = self.by_slug[ONBOARDING_SLUG]
        self.assertEqual(g["category"], "foundations")
        self.assertEqual(
            g["order"], 1,
            f"{ONBOARDING_SLUG} must be foundations order 1 so it is the "
            f"web `help` landing guide; got order {g['order']}",
        )

    def test_first_index_entry_is_onboarding_guide(self):
        """``_GUIDE_INDEX[0]`` is what the client auto-loads on bare `help`
        (``loadGuideIntoPane(data.guides[0].slug)``). It must be the
        onboarding guide."""
        self.assertEqual(
            self.idx[0]["slug"], ONBOARDING_SLUG,
            "the web `help` overlay auto-loads guides[0]; it must be the "
            f"onboarding guide {ONBOARDING_SLUG!r}, not {self.idx[0]['slug']!r}",
        )

    def test_dense_reference_is_not_the_landing_guide(self):
        """The dice-mechanics reference must not be index[0] — it's the
        regression this drop fixes."""
        self.assertNotEqual(
            self.idx[0]["slug"], DENSE_REFERENCE_SLUG,
            "the dense WEG-D6 mechanics reference must not be the first guide "
            "a new player sees when they type `help`",
        )
        # And it should still live in foundations (just not first).
        self.assertEqual(self.by_slug[DENSE_REFERENCE_SLUG]["category"],
                         "foundations")

    def test_foundations_orders_are_unique_and_dense(self):
        """Foundations orders stay a clean 1..N with no gaps/collisions so
        the sort is deterministic and the landing is stable."""
        orders = sorted(g["order"] for g in self.idx
                        if g["category"] == "foundations")
        self.assertEqual(
            orders, list(range(1, len(orders) + 1)),
            f"foundations orders should be a contiguous 1..N; got {orders}",
        )


class TestClientAutoLoadsFirstGuide(unittest.TestCase):
    """Client side (source guard): the overlay auto-loads the FIRST index
    entry. This is the consumer half of the contract the server-side tests
    pin — together they ensure `help` lands on the onboarding guide."""

    @classmethod
    def setUpClass(cls):
        with open(CLIENT_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    def test_open_guide_browser_auto_loads_first_guide(self):
        m = re.search(r"function openGuideBrowser\(\)\s*\{(.+?)^}",
                      self.html, re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(m, "openGuideBrowser function not found")
        body = m.group(1)
        # The auto-load must target the first index entry — guides[0].
        self.assertIn(
            "data.guides[0]", body,
            "openGuideBrowser must auto-load data.guides[0] (the first index "
            "entry) — this is what makes the foundations order-1 guide the "
            "`help` landing page",
        )
        self.assertIn("loadGuideIntoPane", body)

    def test_bare_help_opens_guide_browser(self):
        """Sanity: bare `help` is still routed to the overlay (not the
        server), so the landing-guide contract is actually reached."""
        m = re.search(r"function sendCmd\(text\)\s*\{(.+?)^}",
                      self.html, re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(m, "sendCmd not found")
        body = m.group(1)
        self.assertTrue("'help'" in body or '"help"' in body,
                        "bare `help` intercept missing from sendCmd")
        self.assertIn("openGuideBrowser", body)


if __name__ == "__main__":
    unittest.main()
