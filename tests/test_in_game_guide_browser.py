"""
Source-guard tests for the in-game guide browser (static/client.html).

Asserts structural presence of all required pieces added by the guide-browser
drop.  These are intentionally fast static checks — no server, no browser.
"""

import re
import pathlib

_CLIENT = pathlib.Path("static/client.html").read_text(encoding="utf-8")


def test_render_guide_markdown_function_present():
    """renderGuideMarkdown must be defined (not just referenced)."""
    assert "function renderGuideMarkdown" in _CLIENT


def test_open_guide_browser_function_present():
    assert "function openGuideBrowser" in _CLIENT


def test_close_guide_browser_function_present():
    assert "function closeGuideBrowser" in _CLIENT


def test_load_guide_into_pane_function_present():
    assert "function loadGuideIntoPane" in _CLIENT


def test_guide_overlay_html_element_present():
    """The guide overlay div must exist in HTML."""
    assert 'id="guide-overlay"' in _CLIENT


def test_guide_overlay_class_present():
    """Container must carry the guide-overlay CSS class."""
    assert 'class="guide-overlay"' in _CLIENT


def test_guide_list_col_present():
    assert 'id="guide-list-col"' in _CLIENT


def test_guide_read_col_present():
    assert 'id="guide-read-col"' in _CLIENT


def test_fetches_portal_guides_index():
    """/api/portal/guides endpoint must be fetched."""
    assert "/api/portal/guides" in _CLIENT


def test_fetches_portal_guide_slug():
    """/api/portal/guide/ path must be fetched (content endpoint)."""
    assert "/api/portal/guide/" in _CLIENT


def test_sendcmd_intercept_open_guide():
    """openGuideBrowser() must be reachable from sendCmd (command intercept)."""
    # Find sendCmd function body
    m = re.search(r"function sendCmd\(text\)\s*\{(.+?)^}", _CLIENT,
                  re.DOTALL | re.MULTILINE)
    assert m, "sendCmd function not found"
    body = m.group(1)
    assert "openGuideBrowser" in body, (
        "openGuideBrowser() not called inside sendCmd — command intercept missing"
    )


def test_sendcmd_intercepts_guide_keyword():
    """sendCmd must intercept 'guide' (lowercased) and return early."""
    m = re.search(r"function sendCmd\(text\)\s*\{(.+?)^}", _CLIENT,
                  re.DOTALL | re.MULTILINE)
    assert m, "sendCmd not found"
    body = m.group(1)
    # Should contain the bare 'guide' keyword check
    assert "'guide'" in body or '"guide"' in body, (
        "Bare 'guide' intercept string not found in sendCmd"
    )


def test_sendcmd_intercepts_plus_guide():
    """+guide must also be intercepted."""
    m = re.search(r"function sendCmd\(text\)\s*\{(.+?)^}", _CLIENT,
                  re.DOTALL | re.MULTILINE)
    assert m
    body = m.group(1)
    assert "'+guide'" in body or '"+guide"' in body, (
        "+guide intercept not found in sendCmd"
    )


def test_sendcmd_intercepts_help():
    """Bare 'help' (no args) must open the guide browser, not go to server."""
    m = re.search(r"function sendCmd\(text\)\s*\{(.+?)^}", _CLIENT,
                  re.DOTALL | re.MULTILINE)
    assert m
    body = m.group(1)
    assert "'help'" in body or '"help"' in body, (
        "Bare 'help' intercept not found in sendCmd"
    )


def test_guide_qa_button_present():
    """GUIDE button must exist in the qa-row for discoverability."""
    assert "openGuideBrowser()" in _CLIENT
    # The button must use the guide-qa-btn class
    assert "guide-qa-btn" in _CLIENT


def test_window_exports_present():
    """Guide functions must be exported onto window for inline-onclick use."""
    assert "window.openGuideBrowser" in _CLIENT
    assert "window.closeGuideBrowser" in _CLIENT
    assert "window.loadGuideIntoPane" in _CLIENT
    assert "window.guideOverlayBackdropClick" in _CLIENT


def test_guide_md_css_present():
    """.guide-md CSS block must be present for markdown rendering."""
    assert ".guide-md" in _CLIENT


def test_guide_modal_css_present():
    """.guide-modal CSS class must be present."""
    assert ".guide-modal" in _CLIENT


def test_escape_to_close_handler():
    """Escape key handler for the guide overlay must exist."""
    assert "_guideEscHandler" in _CLIENT


def test_no_era_violations_in_new_strings():
    """New guide browser user-facing strings must not contain era-forbidden words.

    Only checks the guide-browser JS block itself (between the two guide-browser
    section markers), so pre-existing era-mapping comments elsewhere in the file
    do not trigger a false positive.
    """
    # The guide JS block starts at the second occurrence of the marker (first is
    # in the CSS block, second is in the JS block).
    start = _CLIENT.find("IN-GAME GUIDE BROWSER", _CLIENT.find("IN-GAME GUIDE BROWSER") + 1)
    # The block ends at the window-export comment that immediately follows it.
    end = _CLIENT.find("/* INLINE-HANDLER EXPORTS", start)
    assert start != -1 and end != -1, "Guide browser JS section markers not found"
    section = _CLIENT[start:end]
    for forbidden in ("Imperial", "TIE Fighter"):
        assert forbidden not in section, (
            f"Era-forbidden term '{forbidden}' found in guide browser JS section"
        )
    # 'Empire'/'Rebel' are allowed in comments (invariant exempts comment text),
    # so we only check that no user-facing *string literals* contain them.
    # Strip JS // line comments before checking.
    stripped = re.sub(r'//[^\n]*', '', section)
    # Strip JS /* block */ comments.
    stripped = re.sub(r'/\*.*?\*/', '', stripped, flags=re.DOTALL)
    for forbidden in ("Empire", "Rebel"):
        assert forbidden not in stripped, (
            f"Era-forbidden term '{forbidden}' found in guide browser string literals"
        )
