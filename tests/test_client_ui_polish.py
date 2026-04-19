"""Regression tests for the S60/P1 UI polish drop.

These are text-level assertions over ``static/client.html``. We don't have a
headless browser in CI, so we verify the structural/CSS invariants that each
bug fix depends on. If any of these regress, the corresponding playtest bug
will come back.

Each test targets exactly ONE of the four fixes from
HANDOFF_APR18_SESSION59_OPUS_TO_SONNET.md §P1 so a failure points at the
specific regression.
"""

from __future__ import annotations

import os
import re

import pytest

CLIENT_HTML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
    "client.html",
)


@pytest.fixture(scope="module")
def client_html() -> str:
    with open(CLIENT_HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────────
# Bug 1 — Sector map expanded-view text clipping
# ─────────────────────────────────────────────────────────────────────────

def test_render_map_modal_expands_viewbox(client_html: str) -> None:
    """renderMapModal must rewrite the cloned viewBox to absorb scaled text.

    The live mini-map viewBox stays as-is (0 0 400 300 for ground, -100 -100
    200 200 for radar). In the modal clone we pad each side by a fraction of
    the corresponding dimension so 2.2×-scaled labels don't overflow — but
    NOT so much that the map shrinks into a tiny centered square.
    """
    assert "function renderMapModal" in client_html, (
        "renderMapModal function is missing"
    )

    # The fix adds a TEXT_SCALE constant and a viewBox rewrite block.
    assert "TEXT_SCALE" in client_html, (
        "Bug 1 regressed: renderMapModal no longer declares TEXT_SCALE — "
        "expanded-view text will clip again."
    )
    # Presence of setAttribute('viewBox', newVB) on the clone.
    assert re.search(
        r"clone\.setAttribute\(\s*['\"]viewBox['\"]\s*,",
        client_html,
    ), (
        "Bug 1 regressed: renderMapModal no longer rewrites the cloned "
        "viewBox; 2.2×-scaled text will overflow the original bounds."
    )

    # [S60/P1a] PAD_FACTOR must be in a sensible range. Too small (< 0.15)
    # lets worst-case labels clip again; too large (> 0.6) shrinks the map
    # into a postage-stamp centered in empty space (the original S60 bug —
    # the initial S60 drop had PAD_FACTOR = TEXT_SCALE - 1 = 1.2, which
    # shrank the map to ~45% of the modal in both axes).
    pad_match = re.search(
        r"var\s+PAD_FACTOR\s*=\s*([\d.]+)\s*;",
        client_html,
    )
    assert pad_match, (
        "Bug 1 regressed: PAD_FACTOR declaration not found or not a numeric "
        "literal. The fix requires a tuned constant — do NOT re-tie it to "
        "TEXT_SCALE."
    )
    pad_factor = float(pad_match.group(1))
    assert 0.15 <= pad_factor <= 0.6, (
        f"Bug 1 regressed: PAD_FACTOR = {pad_factor} is outside the "
        f"tuned range [0.15, 0.6]. Below 0.15 lets labels clip; above 0.6 "
        f"shrinks the map into a postage stamp (the S60 over-correction)."
    )


# ─────────────────────────────────────────────────────────────────────────
# Bug 2 — "ESC ×" close button inside expanded modal doesn't fire
# ─────────────────────────────────────────────────────────────────────────

def test_mm_close_has_elevated_stacking(client_html: str) -> None:
    """The close button must declare position/z-index/pointer-events so it
    reliably sits above anything in the modal body.
    """
    # Pull out the .mm-close rule.
    m = re.search(
        r"\.map-modal-head\s+\.mm-close\s*\{([^}]*)\}",
        client_html,
    )
    assert m, "Could not find .map-modal-head .mm-close CSS rule"
    rule = m.group(1)

    assert "position" in rule and "relative" in rule, (
        "Bug 2 regressed: .mm-close lost position:relative — click may be "
        "swallowed by an overlay in the modal body."
    )
    assert "z-index" in rule, (
        "Bug 2 regressed: .mm-close lost its z-index."
    )
    assert "pointer-events" in rule, (
        "Bug 2 regressed: .mm-close lost pointer-events declaration."
    )


def test_map_modal_head_has_stacking_context(client_html: str) -> None:
    """The header block needs its own stacking context above the body."""
    m = re.search(
        r"\.map-modal-head\s*\{([^}]*)\}",
        client_html,
    )
    assert m, "Could not find .map-modal-head CSS rule"
    rule = m.group(1)
    assert "position" in rule and "relative" in rule, (
        "Bug 2 regressed: .map-modal-head lost position:relative."
    )
    assert "z-index" in rule, (
        "Bug 2 regressed: .map-modal-head lost z-index — header content "
        "may be covered by oversized body SVG."
    )


# ─────────────────────────────────────────────────────────────────────────
# Bug 3 — Backdrop-click outside modal doesn't close it
# ─────────────────────────────────────────────────────────────────────────

def test_map_modal_backdrop_uses_contains_test(client_html: str) -> None:
    """The handler must test 'target not inside .map-modal' rather than the
    old strict id-equality check, which only fired on the 40px overlay
    padding strip.
    """
    # Extract the mapModalBackdropClick body.
    m = re.search(
        r"function\s+mapModalBackdropClick\s*\([^)]*\)\s*\{([^}]*)\}",
        client_html,
        re.DOTALL,
    )
    assert m, "mapModalBackdropClick function not found"
    body = m.group(1)

    # New semantics: use modal.contains(target).
    assert ".contains(" in body, (
        "Bug 3 regressed: mapModalBackdropClick no longer uses .contains() "
        "to test target-outside-modal; backdrop clicks will stop closing "
        "the modal."
    )
    # The old strict-equality check must not appear in executable code.
    # Strip // line comments first so historical references in explanatory
    # comments don't trigger a false positive.
    code_only = re.sub(r"//[^\n]*", "", body)
    assert "evt.target.id === 'map-modal-overlay'" not in code_only, (
        "Bug 3 regressed: the old strict id-equality check is back — "
        "backdrop clicks only fire on overlay padding, not on any click "
        "outside the modal box."
    )


# ─────────────────────────────────────────────────────────────────────────
# Bug 4 — Maximize button (⛶) on mini-map isn't clickable
# ─────────────────────────────────────────────────────────────────────────

def test_map_expand_btn_z_index_raised(client_html: str) -> None:
    """The expand button must have z-index ≥ 10 and explicit pointer-events
    so clicks on the button aren't captured by the sibling SVG.
    """
    m = re.search(
        r"\.map-expand-btn\s*\{([^}]*)\}",
        client_html,
    )
    assert m, ".map-expand-btn CSS rule not found"
    rule = m.group(1)

    zm = re.search(r"z-index\s*:\s*(\d+)", rule)
    assert zm, "Bug 4 regressed: .map-expand-btn has no z-index."
    z = int(zm.group(1))
    assert z >= 10, (
        f"Bug 4 regressed: .map-expand-btn z-index is {z}, expected ≥ 10. "
        "Button may be covered by sibling SVG in some browsers."
    )

    assert "pointer-events" in rule and "auto" in rule, (
        "Bug 4 regressed: .map-expand-btn lost pointer-events:auto — "
        "clicks may stop landing on the button."
    )


# ─────────────────────────────────────────────────────────────────────────
# Sanity: the modal DOM structure the fixes depend on still exists
# ─────────────────────────────────────────────────────────────────────────

def test_map_modal_dom_structure_intact(client_html: str) -> None:
    """If the modal markup disappears or is renamed, every fix above is moot.
    Assert the anchoring IDs/classes still exist so regressions here are
    loud.
    """
    assert 'id="map-modal-overlay"' in client_html
    assert 'id="map-modal"' in client_html
    assert 'class="mm-close"' in client_html
    assert 'class="map-expand-btn"' in client_html
    # The two mini-maps the expand flow sources from.
    assert 'id="g-area-map-svg"' in client_html
    assert 'id="s-radar-svg"' in client_html
