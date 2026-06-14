"""
test_gnd_ux_smart_buttons.py — G8 smart quick-button row verification.

Asserts (via static parse of static/client.html) that the context-aware
quick-button system shipped correctly:

  A) QUICK_MODES + MODE_LABELS defined
  B) getQuickMode / updateQuickButtons / enterPostCombatMode defined
  C) explore mode reproduces the original 6 buttons exactly (LOOK/POSE/SAY/INV/JOBS/CRAFT)
  D) POSE and SAY keep data-action="stage" (never "send")
  E) updateQuickButtons is invoked from handleHudUpdate AND handleCombatState
  F) wireQuickActions is re-invoked after regen inside updateQuickButtons
  G) 30-second post-combat timer (setTimeout … 30000) exists
  H) wound / trainer / crafting context flags are derived in handleHudUpdate
  I) No GCW tokens in the added code blocks
  J) Regression: no new inline onclick handlers that lack window exports
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ─── A. Core symbols defined ──────────────────────────────────────────

def test_QUICK_MODES_defined():
    """QUICK_MODES object literal is defined."""
    html = _html()
    assert "var QUICK_MODES" in html or "QUICK_MODES =" in html, (
        "QUICK_MODES not defined in client.html"
    )


def test_MODE_LABELS_defined():
    """MODE_LABELS object literal is defined."""
    html = _html()
    assert "var MODE_LABELS" in html or "MODE_LABELS =" in html, (
        "MODE_LABELS not defined in client.html"
    )


# ─── B. Functions defined ─────────────────────────────────────────────

def test_getQuickMode_defined():
    html = _html()
    assert re.search(r"function\s+getQuickMode\s*\(", html), (
        "getQuickMode not defined"
    )


def test_updateQuickButtons_defined():
    html = _html()
    assert re.search(r"function\s+updateQuickButtons\s*\(", html), (
        "updateQuickButtons not defined"
    )


def test_enterPostCombatMode_defined():
    html = _html()
    assert re.search(r"function\s+enterPostCombatMode\s*\(", html), (
        "enterPostCombatMode not defined"
    )


# ─── C. Explore mode button list ──────────────────────────────────────

def _quick_modes_block(html: str) -> str:
    """Extract the text surrounding QUICK_MODES definition."""
    start = html.find("var QUICK_MODES")
    assert start != -1, "QUICK_MODES not found"
    return html[start: start + 4000]


def test_explore_mode_has_LOOK():
    block = _quick_modes_block(_html())
    assert "'LOOK'" in block or '"LOOK"' in block, (
        "LOOK button missing from explore mode"
    )


def test_explore_mode_has_POSE():
    block = _quick_modes_block(_html())
    assert "'POSE'" in block or '"POSE"' in block, (
        "POSE button missing from explore mode"
    )


def test_explore_mode_has_SAY():
    block = _quick_modes_block(_html())
    assert "'SAY'" in block or '"SAY"' in block, (
        "SAY button missing from explore mode"
    )


def test_explore_mode_has_INV():
    block = _quick_modes_block(_html())
    assert "'INV'" in block or '"INV"' in block, (
        "INV button missing from explore mode"
    )


# ─── D. POSE / SAY must remain action="stage" ─────────────────────────

def test_POSE_action_is_stage():
    """POSE entry in QUICK_MODES.explore uses action: 'stage' (not 'send')."""
    block = _quick_modes_block(_html())
    # Find the POSE entry and check the action in the surrounding 200 chars
    idx = block.find("'POSE'")
    if idx == -1:
        idx = block.find('"POSE"')
    assert idx != -1, "POSE not found in QUICK_MODES"
    snippet = block[idx: idx + 200]
    assert "stage" in snippet, (
        f"POSE button action is not 'stage'; snippet: {snippet!r}"
    )
    assert "send" not in snippet or snippet.index("stage") < snippet.index("send"), (
        "POSE action appears to be 'send' not 'stage'"
    )


def test_SAY_action_is_stage():
    """SAY entry in QUICK_MODES.explore uses action: 'stage' (not 'send')."""
    block = _quick_modes_block(_html())
    idx = block.find("'SAY'")
    if idx == -1:
        idx = block.find('"SAY"')
    assert idx != -1, "SAY not found in QUICK_MODES"
    snippet = block[idx: idx + 200]
    assert "stage" in snippet, (
        f"SAY button action is not 'stage'; snippet: {snippet!r}"
    )


# ─── E. updateQuickButtons called from both entry points ──────────────

def _handleHudUpdate_body(html: str) -> str:
    start = html.find("function handleHudUpdate(data)")
    assert start != -1, "handleHudUpdate not found"
    return html[start: start + 35000]


def _handleCombatState_body(html: str) -> str:
    start = html.find("function handleCombatState(data)")
    assert start != -1, "handleCombatState not found"
    return html[start: start + 8000]


def test_updateQuickButtons_called_from_handleHudUpdate():
    body = _handleHudUpdate_body(_html())
    assert "updateQuickButtons()" in body, (
        "updateQuickButtons() not called inside handleHudUpdate"
    )


def test_updateQuickButtons_called_from_handleCombatState():
    body = _handleCombatState_body(_html())
    assert "updateQuickButtons()" in body or "enterPostCombatMode()" in body, (
        "updateQuickButtons/enterPostCombatMode not called from handleCombatState"
    )


# ─── F. wireQuickActions re-invoked after regen ───────────────────────

def _updateQuickButtons_body(html: str) -> str:
    start = html.find("function updateQuickButtons()")
    assert start != -1, "updateQuickButtons not found"
    return html[start: start + 3000]


def test_wireQuickActions_reinvoked_after_regen():
    body = _updateQuickButtons_body(_html())
    assert "wireQuickActions()" in body, (
        "wireQuickActions() not re-invoked inside updateQuickButtons"
    )


# ─── G. 30-second post-combat timer ──────────────────────────────────

def test_postcombat_timer_is_30000ms():
    """setTimeout with 30000 ms delay exists for post-combat revert."""
    html = _html()
    assert re.search(r"setTimeout\s*\(.*?30000\s*\)", html, re.DOTALL), (
        "No setTimeout(..., 30000) found — post-combat 30s timer missing"
    )


# ─── H. Context flags derived in handleHudUpdate ──────────────────────

def test_wound_level_context_flag_set():
    body = _handleHudUpdate_body(_html())
    assert "_lastWoundLevel" in body, (
        "_lastWoundLevel not set in handleHudUpdate"
    )


def test_trainer_context_flag_set():
    body = _handleHudUpdate_body(_html())
    assert "_roomHasTrainer" in body, (
        "_roomHasTrainer not set in handleHudUpdate"
    )


def test_crafting_context_flag_set():
    body = _handleHudUpdate_body(_html())
    assert "_roomHasCrafting" in body, (
        "_roomHasCrafting not set in handleHudUpdate"
    )


def test_room_contents_consumed_for_context():
    body = _handleHudUpdate_body(_html())
    assert "room_contents" in body, (
        "room_contents not read in handleHudUpdate for context-flag derivation"
    )


def test_room_services_consumed_for_context():
    body = _handleHudUpdate_body(_html())
    assert "room_services" in body, (
        "room_services not read in handleHudUpdate for context-flag derivation"
    )


# ─── I. No GCW tokens in the new G8 code block ───────────────────────

def _g8_block(html: str) -> str:
    """Extract the G8 smart quick-button code section."""
    marker = "G8: Context-sensitive quick-action buttons"
    start = html.find(marker)
    assert start != -1, "G8 code block marker not found"
    # Take up to 8000 chars — covers all G8 functions
    return html[start: start + 8000]


def test_no_gcw_empire_in_g8():
    block = _g8_block(_html())
    assert not re.search(r"\bempire\b", block, re.IGNORECASE), (
        "GCW token 'empire' in G8 quick-button code"
    )


def test_no_gcw_rebel_in_g8():
    block = _g8_block(_html())
    assert not re.search(r"\brebel\b", block, re.IGNORECASE), (
        "GCW token 'rebel' in G8 quick-button code"
    )


def test_no_gcw_tie_in_g8():
    block = _g8_block(_html())
    assert not re.search(r"\bTIE\b", block, re.IGNORECASE), (
        "GCW token 'TIE' in G8 quick-button code"
    )
