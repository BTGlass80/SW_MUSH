"""Regression tests for the expanded-map sizing fix.

Bug (playtest, May 28 2026): the expanded sector map rendered as a tiny
~320px stamp floating in a huge near-empty modal. Root cause: openMapModal
called renderMapModal() BEFORE adding the `.show` class, so the modal body
was still display:none and measured 0×0 when _renderModalViaM3 read
getBoundingClientRect(); the Math.max(320,…)/Math.max(240,…) floor then
locked the map at its minimum size.

These are text-level invariants over static/client.html (no headless browser
in CI). If any regress, the postage-stamp map comes back.
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


def _func_body(text: str, signature: str, span: int = 4000) -> str:
    start = text.find(signature)
    assert start > 0, f"{signature} not found"
    return text[start: start + span]


# ── The core ordering invariant ─────────────────────────────────────────

def test_openmapmodal_shows_overlay_before_rendering(client_html: str) -> None:
    """openMapModal must add the `.show` class (which flips the overlay
    from display:none to flex) BEFORE calling renderMapModal — otherwise
    the body measures 0×0 and the map collapses to its size floor."""
    body = _func_body(client_html, "function openMapModal(")
    show_pos = body.find("classList.add('show')")
    render_pos = body.find("renderMapModal(kind)")
    assert show_pos > 0, "openMapModal no longer adds the .show class"
    assert render_pos > 0, "openMapModal no longer calls renderMapModal(kind)"
    assert show_pos < render_pos, (
        "openMapModal renders the map BEFORE showing the overlay — the body "
        "will measure 0×0 and the map will render at its minimum-size floor "
        "(the tiny-map-in-a-huge-modal bug)."
    )


def test_openmapmodal_rerenders_after_layout_flush(client_html: str) -> None:
    """After the synchronous render, openMapModal must re-render on a
    later animation frame so the map picks up the real body size even if
    the first measure (same frame as the class flip) was short."""
    body = _func_body(client_html, "function openMapModal(")
    assert "requestAnimationFrame" in body, (
        "openMapModal should re-render via requestAnimationFrame after the "
        "overlay is shown so the map fills the settled layout."
    )


# ── Measurement robustness ──────────────────────────────────────────────

def test_modal_m3_sizing_falls_back_off_the_floor(client_html: str) -> None:
    """_renderModalViaM3 must not size the map straight off the
    Math.max(320/240) floor when the body measures small. It should fall
    back to the modal's own box, then the viewport, so a real (large)
    screen never yields a 320px map."""
    body = _func_body(client_html, "function _renderModalViaM3(")
    # Borrows the modal element's box as a fallback measure.
    assert "getElementById('map-modal')" in body, (
        "sizing fallback should borrow the modal's own bounding box"
    )
    # Viewport fallback as last resort.
    assert "innerWidth" in body and "innerHeight" in body, (
        "sizing fallback should fall back to the viewport when the modal "
        "box is also unavailable"
    )
    # A threshold guard distinguishing "layout not settled" from a real size.
    assert re.search(r"<\s*200", body), (
        "expected a small-measurement threshold guard (e.g. w < 200)"
    )


def test_modal_renders_bare_tier1abody_not_nested_chrome(client_html: str) -> None:
    """Single-chrome design: the modal supplies its own header + legend,
    so the M3 modal path renders the bare Tier1aBody SVG, NOT MapRenderer
    (which would nest a second HolocartaFrame device inside the modal)."""
    body = _func_body(client_html, "function _renderModalViaM3(", span=2500)
    assert "Tier1aBody" in body, "modal should render the bare Tier1aBody"
    # The only MapRenderer mention in this function is the explanatory
    # comment about why it's NOT used; there must be no MapRenderer CALL.
    assert not re.search(r"M3CompositionEngine\.MapRenderer\s*\(", body), (
        "modal must not invoke MapRenderer — that nests a second chrome "
        "frame inside the modal's own chrome"
    )


# ── Resize tracking ─────────────────────────────────────────────────────

def test_modal_rerenders_on_window_resize(client_html: str) -> None:
    """The map SVG is sized in pixels at render time, so it can't reflow
    on its own. A debounced window resize handler must re-render the open
    modal so it keeps filling the screen."""
    assert "addEventListener('resize'" in client_html, (
        "no window resize handler — the expanded map won't track screen "
        "size changes"
    )
    # The handler must be gated on the modal being open and re-render it.
    m = re.search(
        r"addEventListener\('resize',[\s\S]{0,400}mapModalOpen[\s\S]{0,400}"
        r"renderMapModal\(mapModalKind\)",
        client_html,
    )
    assert m is not None, (
        "resize handler should re-render the open modal via "
        "renderMapModal(mapModalKind)"
    )
