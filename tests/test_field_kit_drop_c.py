"""Field Kit Drop C — Ground UX (Datapad).

Static-content + targeted server-side guards for:
  · F1  — wound ladder renders all 7 rungs (was 6 in prior client)
  · F5  — FP dots clamp at FP_DISPLAY_MAX with explicit overflow indicator
          (Drop C divergence from prototype: WEG R&E p83 has no formal
           per-character fp_max, so we use a UI-side soft cap instead of a
           server-supplied per-character maximum)
  · F8  — stun-counter strip uses stunCap(STR.dice) for capacity;
          server payload exposes active_stun_count
  · F10 — wound-ladder penalty column right-aligned with fixed width

Drop C also depends on Drop A's primitives (WOUND_RUNGS, stunCap, etc.)
already living in static/client.html — Drop A's tests guard those.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CLIENT_HTML = ROOT / "static" / "client.html"
SESSION_PY = ROOT / "server" / "session.py"


@pytest.fixture(scope="module")
def client_html_text() -> str:
    assert CLIENT_HTML.exists(), f"missing {CLIENT_HTML}"
    return CLIENT_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def session_py_text() -> str:
    assert SESSION_PY.exists(), f"missing {SESSION_PY}"
    return SESSION_PY.read_text(encoding="utf-8")


# ────────────────────────────────────────────────────────────────────
# F1 — wound ladder all 7 rungs
# ────────────────────────────────────────────────────────────────────

class TestF1WoundLadder:

    def test_old_pip_strip_html_removed(self, client_html_text: str):
        """The 6-pip strip in static HTML scaffolding must be gone.
        If this regresses, F1 has been undone."""
        old_inline_pattern = re.compile(
            r'<div class="wound-pips"[^>]*>\s*'
            r'(?:<div class="wound-pip">\s*</div>\s*){6}',
            re.DOTALL,
        )
        assert not old_inline_pattern.search(client_html_text), (
            "F1 regression: 6-pip wound strip is back in static HTML"
        )

    def test_new_ladder_html_present(self, client_html_text: str):
        """The new wound-ladder div (JS-populated) must exist."""
        assert '<div class="wound-ladder" id="g-wound-ladder"></div>' in client_html_text

    def test_old_pip_loop_removed(self, client_html_text: str):
        """JS render loop should no longer use `for (var pi = 0; pi < 6; pi++)`
        for wound pips. The new render iterates WOUND_RUNGS."""
        old_loop = re.compile(
            r'for \(var pi = 0; pi < 6; pi\+\+\)\s*\{\s*'
            r'var pip = document\.createElement\([\'"]div[\'"]\);\s*'
            r'pip\.className = [\'"]wound-pip[\'"]',
            re.DOTALL,
        )
        assert not old_loop.search(client_html_text), (
            "F1 regression: old 6-pip loop is back in JS"
        )

    def test_new_ladder_render_uses_wound_rungs(self, client_html_text: str):
        """The new render must iterate WOUND_RUNGS."""
        assert "WOUND_RUNGS[ri]" in client_html_text or "WOUND_RUNGS.length" in client_html_text, (
            "F1: new render does not iterate WOUND_RUNGS"
        )

    def test_dead_rung_hidden_until_reached(self, client_html_text: str):
        """The DEAD rung (v=6) must be filtered out unless wl >= 6."""
        assert "rung.v === 6 && wl < 6" in client_html_text, (
            "F1: DEAD-rung-hidden-until-reached logic missing"
        )

    def test_active_rung_marker(self, client_html_text: str):
        """Active rung gets a ▸ prefix (Unicode \\u25b8)."""
        assert "\\u25b8" in client_html_text or "\u25b8" in client_html_text, (
            "F1: active-rung marker missing"
        )


# ────────────────────────────────────────────────────────────────────
# F1 — wound ladder CSS
# ────────────────────────────────────────────────────────────────────

class TestF1WoundLadderCSS:

    @pytest.mark.parametrize("selector", [
        ".wound-ladder",
        ".wound-rung",
        ".wound-rung.active",
        ".wound-rung.below",
        ".wound-rung-pip",
        ".wound-rung-label",
        ".wound-rung-pen",
    ])
    def test_selectors_present(self, client_html_text: str, selector: str):
        assert selector in client_html_text, (
            f"F1 CSS regression: selector `{selector}` missing"
        )

    def test_severity_modifier_classes_present(self, client_html_text: str):
        for sev in ("ok", "warn", "hurt", "crit", "dead"):
            assert f".sev-{sev}" in client_html_text, (
                f"F1 CSS: severity `.sev-{sev}` rule missing"
            )

    def test_old_pip_classes_removed(self, client_html_text: str):
        assert ".wound-pip {" not in client_html_text, (
            "F1 CSS: legacy `.wound-pip { ... }` rule still present"
        )
        assert ".wound-pips {" not in client_html_text, (
            "F1 CSS: legacy `.wound-pips { ... }` rule still present"
        )


# ────────────────────────────────────────────────────────────────────
# F10 — penalty column alignment
# ────────────────────────────────────────────────────────────────────

class TestF10PenaltyAlignment:

    def test_penalty_column_right_aligned(self, client_html_text: str):
        """The .wound-rung-pen rule must include text-align: right and a
        fixed min-width to keep rungs in column."""
        m = re.search(
            r"\.wound-rung-pen\s*\{([^}]*)\}",
            client_html_text,
        )
        assert m, "F10: .wound-rung-pen rule missing"
        body = m.group(1)
        assert "text-align: right" in body, (
            "F10: penalty column not right-aligned"
        )
        assert "min-width" in body, (
            "F10: penalty column missing fixed width"
        )


# ────────────────────────────────────────────────────────────────────
# F8 — stun strip
# ────────────────────────────────────────────────────────────────────

class TestF8StunStrip:

    def test_stun_block_html_present(self, client_html_text: str):
        assert 'class="stun-block"' in client_html_text
        assert 'id="g-stun-block"' in client_html_text
        assert 'id="g-stun-pips"' in client_html_text
        assert 'id="g-stun-count-text"' in client_html_text

    def test_stun_pip_css_present(self, client_html_text: str):
        for selector in (".stun-pips", ".stun-pip", ".stun-pip.filled"):
            assert selector in client_html_text, (
                f"F8 CSS: `{selector}` rule missing"
            )

    def test_render_parses_strength_dice(self, client_html_text: str):
        """JS must parse strength dice from attributes.strength string
        (engine sends it as 'XD+Y' format)."""
        assert "data.attributes.strength" in client_html_text, (
            "F8: render does not read attributes.strength"
        )
        assert re.search(r"strDiceStr\.match\(/\^\(\\d\+\)D/\)", client_html_text), (
            "F8: render missing dice-string regex parse"
        )

    def test_render_uses_stuncap_helper(self, client_html_text: str):
        """The Drop A `stunCap()` helper must be invoked here."""
        m = re.search(
            r"// F8 — STUN COUNTERS strip[\s\S]*?stunCap\(",
            client_html_text,
        )
        assert m, "F8: render does not invoke stunCap()"

    def test_render_reads_active_stun_count(self, client_html_text: str):
        assert "data.active_stun_count" in client_html_text, (
            "F8: render does not read data.active_stun_count from HUD payload"
        )

    def test_legacy_badge_kept_but_hidden(self, client_html_text: str):
        """The legacy g-stun-badge element should still exist in DOM (so
        non-migrated code paths don't break) but be hidden by Drop C."""
        assert 'id="g-stun-badge"' in client_html_text, (
            "F8: legacy badge element removed entirely (compat hazard)"
        )
        assert "if (legacyStunBadge) legacyStunBadge.style.display = 'none';" in client_html_text, (
            "F8: legacy badge not explicitly hidden by Drop C render"
        )


# ────────────────────────────────────────────────────────────────────
# F8 server-side: active_stun_count surfaced in _hud_base
# ────────────────────────────────────────────────────────────────────

class TestF8ServerPayload:

    def test_active_stun_count_in_hud_base(self, session_py_text: str):
        """server/session.py:_hud_base must include active_stun_count
        in the returned dict so the F8 strip can render."""
        m = re.search(
            r"def _hud_base\(self\) -> dict:.*?return hud",
            session_py_text,
            re.DOTALL,
        )
        assert m, "_hud_base function not found"
        body = m.group(0)
        assert '"active_stun_count":' in body, (
            "F8 server: _hud_base missing active_stun_count field"
        )

    def test_active_stun_count_uses_get_char_obj(self, session_py_text: str):
        """The value must come from the parsed Character object's
        active_stun_count property — not from the raw dict (which doesn't
        carry runtime stun_timers)."""
        m = re.search(
            r"def _hud_base\(self\) -> dict:.*?return hud",
            session_py_text,
            re.DOTALL,
        )
        assert m
        body = m.group(0)
        assert "get_char_obj()" in body, (
            "F8 server: _hud_base does not use get_char_obj() for stun count"
        )
        assert "active_stun_count" in body
        # Must be wrapped in try/except so a stale char_obj never breaks HUD
        assert "try:" in body and "except" in body, (
            "F8 server: get_char_obj fetch not exception-guarded"
        )


# ────────────────────────────────────────────────────────────────────
# F5 — FP dots clamp + explicit overflow indicator
# ────────────────────────────────────────────────────────────────────

class TestF5FPDots:
    """F5 (Drop C divergence): WEG R&E p83 has no formal per-character
    fp_max, so the prototype's `fp_max` field is not implementable
    against the live data model. We use a UI-side soft cap
    (FP_DISPLAY_MAX) plus explicit overflow indicator. The bug F5 reports
    (FP dots overflowing) is fully prevented either way."""

    def test_fp_display_max_constant_present(self, client_html_text: str):
        assert "var FP_DISPLAY_MAX = 6;" in client_html_text, (
            "F5: explicit FP_DISPLAY_MAX cap constant not present "
            "(was previously a bare `6` magic number)"
        )

    def test_fp_loop_uses_constant(self, client_html_text: str):
        """The FP-pip loop must iterate up to FP_DISPLAY_MAX, not a literal 6."""
        assert "fpi < FP_DISPLAY_MAX" in client_html_text, (
            "F5: FP loop does not use FP_DISPLAY_MAX constant"
        )

    def test_fp_overflow_uses_constant(self, client_html_text: str):
        """The overflow `+N` calculation must use FP_DISPLAY_MAX."""
        assert "fp > FP_DISPLAY_MAX" in client_html_text
        assert "(fp - FP_DISPLAY_MAX)" in client_html_text

    def test_fp_visible_clamp_uses_constant(self, client_html_text: str):
        assert "var visible = Math.min(fp, FP_DISPLAY_MAX);" in client_html_text

    def test_negative_fp_defended(self, client_html_text: str):
        """Defensive coding: if fp arrives as negative or NaN, treat as 0."""
        assert "if (!isFinite(fp) || fp < 0) fp = 0;" in client_html_text, (
            "F5 defensive: negative-fp guard missing"
        )


# ────────────────────────────────────────────────────────────────────
# Cross-cut: Drop C does not regress Drop A
# ────────────────────────────────────────────────────────────────────

class TestDropANotRegressed:
    """Drop C lives on top of Drop A's primitives. None of those should
    have been touched."""

    @pytest.mark.parametrize("symbol", [
        "var FK = {",
        "var WOUND_RUNGS = [",
        "function woundRung(level)",
        "function woundColor(sev, theme)",
        "function stunCap(strengthDice)",
        "var CONDITION_COLORS = {",
        "function conditionColor(cond)",
    ])
    def test_drop_a_primitives_intact(self, client_html_text: str, symbol: str):
        assert symbol in client_html_text, (
            f"Drop A regression: `{symbol}` missing — Drop C may have stomped Drop A"
        )
