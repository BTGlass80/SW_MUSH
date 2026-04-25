"""Field Kit Drop A — static-content guards for static/client.html.

Drop A ports drop_v2/prototype/tokens.jsx (JS portion) into client.html
as IIFE-scoped vars + window-exposed debug surface. These tests don't
execute the JS — they just assert the symbols and key invariants are
present in the file. Browser-console smoke tests (and the node-side
smoke tests in tools/) cover runtime behavior.

If any of these fail, Drop A has been partially undone or a downstream
drop has stomped its anchors.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CLIENT_HTML = Path(__file__).parent.parent / "static" / "client.html"


@pytest.fixture(scope="module")
def client_html_text() -> str:
    assert CLIENT_HTML.exists(), f"missing {CLIENT_HTML}"
    return CLIENT_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def drop_a_block(client_html_text: str) -> str:
    """The FIELD KIT TOKENS & HELPERS section, between its header and STATE."""
    m = re.search(
        r"// ── FIELD KIT TOKENS & HELPERS ──.*?// ── STATE ──",
        client_html_text,
        re.DOTALL,
    )
    assert m, "Drop A block not found — was tokens.jsx port removed?"
    return m.group(0)


# ────────────────────────────────────────────────────────────────────
# Section structure
# ────────────────────────────────────────────────────────────────────

class TestDropABlockStructure:

    def test_block_exists(self, drop_a_block: str):
        assert "FIELD KIT TOKENS & HELPERS" in drop_a_block

    def test_block_lives_inside_iife(self, client_html_text: str):
        """Drop A block must come AFTER `(function(){` and BEFORE `})();`."""
        iife_open = client_html_text.find("(function(){")
        block_pos = client_html_text.find("FIELD KIT TOKENS & HELPERS")
        iife_close = client_html_text.rfind("})();")
        assert iife_open != -1
        assert block_pos != -1
        assert iife_close != -1
        assert iife_open < block_pos < iife_close, (
            "Drop A block is not inside the IIFE"
        )


# ────────────────────────────────────────────────────────────────────
# F1 — Wound ladder (7 levels)
# ────────────────────────────────────────────────────────────────────

class TestF1WoundRungs:

    def test_wound_rungs_var_present(self, drop_a_block: str):
        assert "var WOUND_RUNGS = [" in drop_a_block

    @pytest.mark.parametrize("label", [
        "HEALTHY",
        "STUNNED",
        "WOUNDED",
        "WOUNDED \\u00d72",  # ×2 as escape (file is ASCII-clean)
        "INCAP",
        "MORTAL",
        "DEAD",
    ])
    def test_all_seven_levels_defined(self, drop_a_block: str, label: str):
        assert f"label: '{label}'" in drop_a_block, f"Missing wound level: {label}"

    def test_wound_rung_function_present(self, drop_a_block: str):
        assert "function woundRung(level)" in drop_a_block

    def test_wound_color_function_present(self, drop_a_block: str):
        assert "function woundColor(sev, theme)" in drop_a_block


# ────────────────────────────────────────────────────────────────────
# F8 — stun cap from STR.dice
# ────────────────────────────────────────────────────────────────────

class TestF8StunCap:

    def test_stun_cap_function_present(self, drop_a_block: str):
        assert "function stunCap(strengthDice)" in drop_a_block

    def test_stun_cap_has_fallback_of_3(self, drop_a_block: str):
        # Conservative fallback when strengthDice is missing/invalid
        assert "? n : 3" in drop_a_block


# ────────────────────────────────────────────────────────────────────
# F11 / F13 — condition color (title-case keys)
# ────────────────────────────────────────────────────────────────────

class TestF13ConditionColors:

    def test_condition_colors_var_present(self, drop_a_block: str):
        assert "var CONDITION_COLORS = {" in drop_a_block

    @pytest.mark.parametrize("title_key", [
        "Pristine",
        "Light Damage",
        "Moderate Damage",
        "Heavy Damage",
        "Critical Damage",
        "Destroyed",
    ])
    def test_title_case_keys(self, drop_a_block: str, title_key: str):
        assert f"'{title_key}':" in drop_a_block

    def test_no_shoutcase_keys(self, drop_a_block: str):
        # F13 fix: keys must be title-case, not SHOUT-CASE.
        for shout in ("'PRISTINE'", "'LIGHT DAMAGE'", "'CRITICAL DAMAGE'"):
            assert shout not in drop_a_block, (
                f"F13 regression: SHOUT-CASE key {shout} reintroduced"
            )

    def test_condition_color_function_present(self, drop_a_block: str):
        assert "function conditionColor(cond)" in drop_a_block


# ────────────────────────────────────────────────────────────────────
# FK palette twin — must match :root CSS values
# ────────────────────────────────────────────────────────────────────

class TestFKPaletteTwin:
    """FK JS palette must agree with --pad-* / --cock-* CSS vars in :root.

    They're duplicates by design (CSS vars for stylesheets, JS values for
    inline styling / canvas / template literals), but they must not drift.
    """

    PAIRS = [
        # (FK key, CSS var name, expected hex)
        ("padShell",       "--pad-shell",        "#2a2220"),
        ("padAmber",       "--pad-amber",        "#ffc857"),
        ("padGreen",       "--pad-green",        "#7ce068"),
        ("padRed",         "--pad-red",          "#ff6e4a"),
        ("padText",        "--pad-text",         "#d9b472"),
        ("cockMetal",      "--cock-metal",       "#2e3540"),
        ("cockCyan",       "--cock-cyan",        "#6ee8ff"),
        ("cockAmber",      "--cock-amber",       "#ffa640"),
        ("cockRed",        "--cock-red",         "#ff5a4a"),
        ("cockGreen",      "--cock-green",       "#7ce068"),
    ]

    @pytest.mark.parametrize("fk_key,css_var,expected_hex", PAIRS)
    def test_fk_matches_css(
        self, client_html_text: str, drop_a_block: str,
        fk_key: str, css_var: str, expected_hex: str,
    ):
        # FK side: `padAmber: '#ffc857'`
        fk_pat = re.compile(
            rf"\b{re.escape(fk_key)}\s*:\s*'(#[0-9a-fA-F]{{6}})'"
        )
        fk_m = fk_pat.search(drop_a_block)
        assert fk_m, f"FK.{fk_key} not found in Drop A block"
        assert fk_m.group(1).lower() == expected_hex.lower()

        # CSS side: `--pad-amber: #ffc857;` (whitespace-tolerant)
        css_pat = re.compile(
            rf"{re.escape(css_var)}:\s*(#[0-9a-fA-F]{{6}})"
        )
        css_m = css_pat.search(client_html_text)
        assert css_m, f"{css_var} not found in :root"
        assert css_m.group(1).lower() == expected_hex.lower()


# ────────────────────────────────────────────────────────────────────
# Window exposure for browser-console smoke tests
# ────────────────────────────────────────────────────────────────────

class TestWindowExposure:

    @pytest.mark.parametrize("symbol", [
        "FK", "WOUND_RUNGS", "woundRung", "woundColor",
        "stunCap", "CONDITION_COLORS", "conditionColor",
    ])
    def test_symbol_exposed_to_window(self, drop_a_block: str, symbol: str):
        assert f"window.{symbol} = {symbol};" in drop_a_block, (
            f"Drop A acceptance criterion #5 (browser console) requires "
            f"window.{symbol} to be exposed for smoke testing"
        )
