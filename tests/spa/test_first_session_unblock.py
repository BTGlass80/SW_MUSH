"""
test_first_session_unblock.py — first-session-unblock client fixes.

Guards the two kills-it fixes from the fun-assessment pass:
  (1) The first-run tour overlay must NOT eat clicks/typing meant for the UI
      (pointer-events:none on the dimmer; the control card re-enables them),
      and must be Escape-closable + auto-dismiss the moment the player types.
  (2) Exit affordances (the feed exit-chips AND the qa-row direction buttons)
      must send "move <dir>" so NAMED (non-compass) exits resolve — a bare
      named dir is rejected by the parser's compass-only fallback.

Static parse of static/client.html (mirrors test_sheet_content_surface.py /
test_client_onclick_exports.py style).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ── (1) Tour overlay must not block the UI ──────────────────────────────────

def test_tour_overlay_pointer_events_none():
    """The full-screen tour dimmer must be pointer-events:none so it can't
    swallow the command bar / exit clicks."""
    html = _html()
    m = re.search(r"\.m3o-tour-overlay\s*\{[^}]*\}", html)
    assert m, ".m3o-tour-overlay rule missing"
    assert "pointer-events: none" in m.group(0), (
        ".m3o-tour-overlay must be pointer-events:none (must not block input)")


def test_tour_card_pointer_events_auto():
    """The tour control card must re-enable pointer events so SKIP/NEXT work."""
    html = _html()
    m = re.search(r"\.m3o-tour-card\s*\{[^}]*\}", html)
    assert m, ".m3o-tour-card rule missing"
    assert "pointer-events: auto" in m.group(0), (
        ".m3o-tour-card must be pointer-events:auto")


def test_tour_escape_and_autodismiss_handler():
    """A keydown handler closes the tour on Escape and auto-dismisses it when
    the player types into a command input."""
    html = _html()
    # The handler references the tour-active guard + endOnboardTour + Escape +
    # a command-input target check.
    assert "_onboardTourActive" in html, "tour-active guard helper missing"
    # Find the keydown handler block and assert its content.
    assert re.search(r"addEventListener\(\s*['\"]keydown['\"]", html), (
        "no keydown handler present")
    # Escape path closes the tour.
    assert re.search(r"Escape[^\n]*endOnboardTour|endOnboardTour[^\n]*Escape", html) or (
        "'Escape'" in html and "endOnboardTour()" in html), (
        "Escape must call endOnboardTour")
    # Auto-dismiss on typing into a command input.
    assert "cmd-input-ground" in html and "cmd-input" in html, (
        "auto-dismiss must key off the command input id/class")


# ── (2) Exit affordances send "move <dir>" ──────────────────────────────────

def test_exit_chip_sends_move_prefix():
    """The feed exit-chip click must send 'move <dir>', not the bare dir."""
    html = _html()
    # Locate the exit-chip click wiring.
    idx = html.find(".exit-chip')")
    assert idx != -1, "exit-chip wiring not found"
    window = html[idx: idx + 600]
    assert re.search(r"sendCmd\(\s*['\"]move ['\"]\s*\+\s*chip\.getAttribute\(\s*['\"]data-dir['\"]",
                     window), (
        "exit-chip click must send 'move ' + data-dir (named exits need MoveCommand)")
    # And it must NOT send the bare data-dir.
    assert not re.search(r"sendCmd\(\s*chip\.getAttribute\(\s*['\"]data-dir['\"]\s*\)\s*\)",
                         window), (
        "exit-chip must not send the bare data-dir (rejected for named exits)")


def test_direction_buttons_send_move_prefix():
    """The qa-row direction buttons (rebuildDirectionButtons) must carry
    'move <dir>' in data-cmd."""
    html = _html()
    idx = html.find("function rebuildDirectionButtons")
    assert idx != -1, "rebuildDirectionButtons not found"
    block = html[idx: idx + 1200]
    assert re.search(r"setAttribute\(\s*['\"]data-cmd['\"]\s*,\s*['\"]move ['\"]\s*\+\s*ex\.dir",
                     block), (
        "rebuildDirectionButtons must set data-cmd = 'move ' + ex.dir")
