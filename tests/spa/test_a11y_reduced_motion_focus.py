"""
test_a11y_reduced_motion_focus.py — UX-6 Section B accessibility drop.

Static-parse checks against static/client.html (mirrors test_gnd_ux_context_panel.py style):

  1. prefers-reduced-motion media query: present, sets animation/transition near-zero.
  2. Return-focus helpers: _a11yRememberOpener / _a11yRestoreFocus defined AND
     wired into every role="dialog" modal open + close path.

No DOM runtime required — pure regex/string checks.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ─── 1. prefers-reduced-motion media query ────────────────────────────────

def test_reduced_motion_media_query_present():
    """@media (prefers-reduced-motion: reduce) block exists in client.html."""
    assert "prefers-reduced-motion" in _html(), (
        "@media (prefers-reduced-motion: reduce) block missing"
    )


def test_reduced_motion_sets_animation_duration_near_zero():
    """Reduced-motion block sets animation-duration to near-zero value."""
    html = _html()
    # Find the media block and check for near-zero animation-duration
    m = re.search(
        r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)"
        r"[^}]*?\{([\s\S]*?)\}\s*\n?\s*</style>",
        html,
    )
    assert m, "Could not locate prefers-reduced-motion block body"
    block = m.group(0)
    # Should contain animation-duration set to near-zero (0.001ms)
    assert re.search(r"animation-duration\s*:\s*0\.001ms", block), (
        "Reduced-motion block should set animation-duration: 0.001ms"
    )


def test_reduced_motion_sets_transition_duration_near_zero():
    """Reduced-motion block sets transition-duration to near-zero value."""
    html = _html()
    m = re.search(
        r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)"
        r"[^}]*?\{([\s\S]*?)\}\s*\n?\s*</style>",
        html,
    )
    assert m, "Could not locate prefers-reduced-motion block body"
    block = m.group(0)
    assert re.search(r"transition-duration\s*:\s*0\.001ms", block), (
        "Reduced-motion block should set transition-duration: 0.001ms"
    )


def test_reduced_motion_sets_animation_iteration_count():
    """Reduced-motion block sets animation-iteration-count: 1."""
    html = _html()
    m = re.search(
        r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)"
        r"[^}]*?\{([\s\S]*?)\}\s*\n?\s*</style>",
        html,
    )
    assert m, "Could not locate prefers-reduced-motion block body"
    block = m.group(0)
    assert re.search(r"animation-iteration-count\s*:\s*1", block), (
        "Reduced-motion block should set animation-iteration-count: 1"
    )


def test_reduced_motion_sets_scroll_behavior_auto():
    """Reduced-motion block sets scroll-behavior: auto."""
    html = _html()
    m = re.search(
        r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)"
        r"[^}]*?\{([\s\S]*?)\}\s*\n?\s*</style>",
        html,
    )
    assert m, "Could not locate prefers-reduced-motion block body"
    block = m.group(0)
    assert re.search(r"scroll-behavior\s*:\s*auto", block), (
        "Reduced-motion block should set scroll-behavior: auto"
    )


def test_reduced_motion_targets_pseudo_elements():
    """Reduced-motion block targets *, *::before, *::after."""
    html = _html()
    assert "*::before" in html and "*::after" in html, (
        "Reduced-motion rule should target *::before and *::after"
    )


def test_reduced_motion_block_inside_style_tag():
    """prefers-reduced-motion block appears before </style> (inside the style block)."""
    html = _html()
    rm_pos = html.find("prefers-reduced-motion")
    style_close_pos = html.find("</style>")
    assert rm_pos != -1, "prefers-reduced-motion not found"
    assert style_close_pos != -1, "</style> not found"
    assert rm_pos < style_close_pos, (
        "prefers-reduced-motion block should appear before </style>"
    )


# ─── 2. Return-focus helpers defined ─────────────────────────────────────

def test_a11y_remember_opener_defined():
    """_a11yRememberOpener function is defined in client.html."""
    assert re.search(r"function\s+_a11yRememberOpener\s*\(", _html()), (
        "_a11yRememberOpener is not defined"
    )


def test_a11y_restore_focus_defined():
    """_a11yRestoreFocus function is defined in client.html."""
    assert re.search(r"function\s+_a11yRestoreFocus\s*\(", _html()), (
        "_a11yRestoreFocus is not defined"
    )


def test_a11y_restore_focus_uses_contains_guard():
    """_a11yRestoreFocus guards the call with document.body.contains."""
    html = _html()
    # Extract the function body
    start = html.find("function _a11yRestoreFocus(")
    assert start != -1, "_a11yRestoreFocus not found"
    block = html[start: start + 500]
    assert "contains" in block, (
        "_a11yRestoreFocus should guard el.focus() with document.body.contains()"
    )


# ─── 3. Remember called in each modal-open path ──────────────────────────

def _fn_body(html: str, fn_name: str, window: int = 800) -> str:
    """Return a fixed window of text starting from the named function definition."""
    idx = html.find("function " + fn_name + "(")
    assert idx != -1, f"function {fn_name} not found in client.html"
    return html[idx: idx + window]


def test_remember_called_in_openSheetPanel():
    """_a11yRememberOpener is called inside openSheetPanel."""
    block = _fn_body(_html(), "openSheetPanel")
    assert "_a11yRememberOpener" in block, (
        "_a11yRememberOpener not called from openSheetPanel"
    )


def test_remember_called_in_openInventoryModal():
    """_a11yRememberOpener is called inside openInventoryModal."""
    block = _fn_body(_html(), "openInventoryModal")
    assert "_a11yRememberOpener" in block, (
        "_a11yRememberOpener not called from openInventoryModal"
    )


def test_remember_called_in_openShopModal():
    """_a11yRememberOpener is called inside openShopModal."""
    block = _fn_body(_html(), "openShopModal")
    assert "_a11yRememberOpener" in block, (
        "_a11yRememberOpener not called from openShopModal"
    )


def test_remember_called_in_openBoardModal():
    """_a11yRememberOpener is called inside openBoardModal."""
    block = _fn_body(_html(), "openBoardModal")
    assert "_a11yRememberOpener" in block, (
        "_a11yRememberOpener not called from openBoardModal"
    )


def test_remember_called_in_openCraftModal():
    """_a11yRememberOpener is called inside openCraftModal."""
    block = _fn_body(_html(), "openCraftModal")
    assert "_a11yRememberOpener" in block, (
        "_a11yRememberOpener not called from openCraftModal"
    )


# ─── 4. Restore called in each modal-close path ──────────────────────────

def test_restore_called_in_closeSheetPanel():
    """_a11yRestoreFocus is called inside closeSheetPanel."""
    block = _fn_body(_html(), "closeSheetPanel")
    assert "_a11yRestoreFocus" in block, (
        "_a11yRestoreFocus not called from closeSheetPanel"
    )


def test_restore_called_in_closeInventoryModal():
    """_a11yRestoreFocus is called inside closeInventoryModal."""
    block = _fn_body(_html(), "closeInventoryModal")
    assert "_a11yRestoreFocus" in block, (
        "_a11yRestoreFocus not called from closeInventoryModal"
    )


def test_restore_called_in_closeShopModal():
    """_a11yRestoreFocus is called inside closeShopModal."""
    block = _fn_body(_html(), "closeShopModal")
    assert "_a11yRestoreFocus" in block, (
        "_a11yRestoreFocus not called from closeShopModal"
    )


def test_restore_called_in_closeBoardModal():
    """_a11yRestoreFocus is called inside closeBoardModal."""
    block = _fn_body(_html(), "closeBoardModal")
    assert "_a11yRestoreFocus" in block, (
        "_a11yRestoreFocus not called from closeBoardModal"
    )


def test_restore_called_in_closeCraftModal():
    """_a11yRestoreFocus is called inside closeCraftModal."""
    block = _fn_body(_html(), "closeCraftModal")
    assert "_a11yRestoreFocus" in block, (
        "_a11yRestoreFocus not called from closeCraftModal"
    )


# ─── 5. Helper count sanity — both helpers invoked at least 5× each ──────

def test_remember_invoked_at_least_five_times():
    """_a11yRememberOpener() called at least 5 times (one per open path)."""
    count = _html().count("_a11yRememberOpener()")
    assert count >= 5, (
        f"Expected _a11yRememberOpener() at least 5 times; got {count}"
    )


def test_restore_invoked_at_least_five_times():
    """_a11yRestoreFocus() called at least 5 times (one per close path)."""
    count = _html().count("_a11yRestoreFocus()")
    assert count >= 5, (
        f"Expected _a11yRestoreFocus() at least 5 times; got {count}"
    )
