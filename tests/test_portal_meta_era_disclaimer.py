"""tests/test_portal_meta_era_disclaimer.py — B3 era-cleanness + fan disclaimer guards.

Verifies that static/portal.html:
1. Uses Clone Wars era in <title>, og:title, twitter:title (not "Galactic Civil War").
2. Uses correct planet count (6) in meta descriptions.
3. Has a fan-project disclaimer in the footer.
4. Does not contain "Galactic Civil War" anywhere in the HTML.
"""
from __future__ import annotations

import os
import re

PORTAL_HTML = os.path.join(os.path.dirname(__file__), "..", "static", "portal.html")


def _read():
    with open(PORTAL_HTML, encoding="utf-8") as f:
        return f.read()


class TestPortalMetaEraCleanness:
    def test_title_is_clone_wars_era(self):
        html = _read()
        m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
        assert m, "No <title> found in portal.html"
        assert "clone wars" in m.group(1).lower(), (
            f"<title> should say Clone Wars, got: {m.group(1)}"
        )
        assert "galactic civil war" not in m.group(1).lower(), (
            f"<title> still references Galactic Civil War (B3 violation): {m.group(1)}"
        )

    def test_og_title_is_clone_wars_era(self):
        html = _read()
        m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        assert m, "No og:title meta found in portal.html"
        assert "clone wars" in m.group(1).lower(), (
            f"og:title should say Clone Wars, got: {m.group(1)}"
        )
        assert "galactic civil war" not in m.group(1).lower(), (
            f"og:title still references Galactic Civil War (B3): {m.group(1)}"
        )

    def test_twitter_title_is_clone_wars_era(self):
        html = _read()
        m = re.search(r'<meta name="twitter:title" content="([^"]*)"', html)
        assert m, "No twitter:title meta found in portal.html"
        assert "clone wars" in m.group(1).lower(), (
            f"twitter:title should say Clone Wars, got: {m.group(1)}"
        )
        assert "galactic civil war" not in m.group(1).lower(), (
            f"twitter:title still references Galactic Civil War (B3): {m.group(1)}"
        )

    def test_no_galactic_civil_war_in_meta_description(self):
        html = _read()
        m = re.search(r'<meta name="description" content="([^"]*)"', html)
        assert m, "No description meta found in portal.html"
        assert "galactic civil war" not in m.group(1).lower(), (
            f"description still references Galactic Civil War (B3): {m.group(1)}"
        )

    def test_meta_description_mentions_six_planets(self):
        html = _read()
        m = re.search(r'<meta name="description" content="([^"]*)"', html)
        assert m, "No description meta found"
        desc = m.group(1).lower()
        assert "six" in desc or "6" in desc, (
            f"description should mention 6 planets, got: {m.group(1)}"
        )
        assert "four" not in desc and "4 planet" not in desc, (
            f"description still says 'four' planets (stale count): {m.group(1)}"
        )

    def test_og_description_mentions_six_planets(self):
        html = _read()
        m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
        assert m, "No og:description meta found"
        desc = m.group(1).lower()
        assert "6" in desc or "six" in desc, (
            f"og:description should mention 6 planets, got: {m.group(1)}"
        )
        assert "4 planet" not in desc, (
            f"og:description still says '4 planets' (stale count): {m.group(1)}"
        )

    def test_no_galactic_civil_war_in_footer(self):
        html = _read()
        # Find footer content
        m = re.search(r"<footer>(.*?)</footer>", html, re.DOTALL | re.IGNORECASE)
        assert m, "No <footer> found in portal.html"
        assert "galactic civil war" not in m.group(1).lower(), (
            "footer still references Galactic Civil War (B3 violation)"
        )
        assert "clone wars" in m.group(1).lower(), (
            "footer should mention Clone Wars era"
        )

    def test_no_galactic_civil_war_anywhere(self):
        html = _read()
        assert "Galactic Civil War" not in html, (
            "portal.html still contains 'Galactic Civil War' (B3 era violation) — "
            "the game is set in the Clone Wars era (~20 BBY)"
        )


class TestFanProjectDisclaimer:
    def test_fan_disclaimer_present(self):
        html = _read()
        html_lower = html.lower()
        # The disclaimer should mention "fan" and disclaim Lucasfilm/Disney affiliation.
        assert "fan" in html_lower, "No fan-project disclaimer found in portal.html"
        assert "lucasfilm" in html_lower, (
            "Fan disclaimer should mention Lucasfilm"
        )

    def test_disclaimer_in_footer(self):
        html = _read()
        m = re.search(r"<footer>(.*?)</footer>", html, re.DOTALL | re.IGNORECASE)
        assert m, "No <footer> found in portal.html"
        footer = m.group(1).lower()
        assert "unofficial" in footer or "fan" in footer, (
            "Fan disclaimer should be in the <footer> element"
        )
        assert "lucasfilm" in footer, (
            "Fan disclaimer in footer should mention Lucasfilm"
        )

    def test_disclaimer_mentions_not_affiliated(self):
        html = _read()
        html_lower = html.lower()
        assert "not affiliated" in html_lower or "unofficial" in html_lower, (
            "Fan disclaimer should state non-affiliation or unofficial status"
        )
