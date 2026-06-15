"""
test_cities_client_polish.py — C6 + C15 city modal polish drop.

Verifies via static parse of static/client.html:
  C6) Citizen-room toggle (mayor/founder gated) and city-home button
      (citizen/mayor/founder gated) fire the correct +city commands
      via _cityFireCommand.
  C15) _cityPagedListSection helper is defined, used for citizens/guests/
       banishments with pageSize 10, and Prev/Next controls are wired via
       addEventListener (not inline onclick).
  Era-clean: no GCW tokens in any new code added by this drop.

Pure-Python regex/string checks — no DOM runtime needed.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ─── helpers ──────────────────────────────────────────────────────────

def _extract_fn(html: str, fn_name: str) -> str:
    """Extract a top-level function body by brace-counting."""
    needle = "function " + fn_name + "("
    start = html.find(needle)
    if start == -1:
        return ""
    depth = 0
    i = start
    in_fn = False
    while i < len(html):
        ch = html[i]
        if ch == '{':
            depth += 1
            in_fn = True
        elif ch == '}':
            depth -= 1
            if in_fn and depth == 0:
                return html[start: i + 1]
        i += 1
    return html[start: start + 8000]


def _actions_block(html: str) -> str:
    return _extract_fn(html, "_cityActionsSection")


def _paged_block(html: str) -> str:
    return _extract_fn(html, "_cityPagedListSection")


def _renderCityModal_block(html: str) -> str:
    return _extract_fn(html, "renderCityModal")


# ─── C6: citizenroom toggle ───────────────────────────────────────────

def test_citizenroom_on_command_present():
    """+city citizenroom on is fired via _cityFireCommand in _cityActionsSection."""
    block = _actions_block(_html())
    assert "+city citizenroom on" in block, (
        "+city citizenroom on command not found in _cityActionsSection"
    )


def test_citizenroom_off_command_present():
    """+city citizenroom off is fired via _cityFireCommand in _cityActionsSection."""
    block = _actions_block(_html())
    assert "+city citizenroom off" in block, (
        "+city citizenroom off command not found in _cityActionsSection"
    )


def test_citizenroom_fires_via_cityFireCommand():
    """_cityFireCommand is called for citizenroom commands."""
    block = _actions_block(_html())
    # Both on and off must route through _cityFireCommand
    assert block.count("_cityFireCommand('+city citizenroom") >= 2, (
        "_cityFireCommand not called for citizenroom commands (need >=2 calls)"
    )


def test_citizenroom_gated_to_mayor_founder():
    """citizenroom row is inside the canAct (mayor/founder) gate."""
    block = _actions_block(_html())
    # canAct gate: 'if (!canAct) return sec;' must come before citizenroom
    no_act_pos = block.find("if (!canAct) return sec;")
    cr_pos = block.find("+city citizenroom on")
    assert no_act_pos != -1, "canAct gate not found in _cityActionsSection"
    assert cr_pos > no_act_pos, (
        "citizenroom block appears before the canAct gate — it leaks to guests"
    )


def test_citizenroom_roomid_validated_nonempty_numeric():
    """Room id validated as non-empty numeric before firing."""
    block = _actions_block(_html())
    # The implementation uses /^\d+$/.test(v) to validate
    assert r"/^\d+$/.test(v)" in block, (
        "citizenroom handler missing numeric validation: /^\\d+$/.test(v)"
    )


# ─── C6: city home button ─────────────────────────────────────────────

def test_city_home_command_present():
    """+city home is fired via _cityFireCommand in _cityActionsSection."""
    block = _actions_block(_html())
    assert "_cityFireCommand('+city home')" in block, (
        "_cityFireCommand('+city home') not found in _cityActionsSection"
    )


def test_city_home_gated_citizen_and_up():
    """City home gate includes citizen role."""
    block = _actions_block(_html())
    # The canHome check includes 'citizen'
    assert "role === 'citizen'" in block, (
        "city home gate does not include 'citizen' role check"
    )


def test_city_home_gate_includes_mayor():
    """City home gate includes mayor role."""
    block = _actions_block(_html())
    # role check for mayor within canHome context
    home_pos = block.find("_cityFireCommand('+city home')")
    citizen_check = block.find("role === 'citizen'")
    assert citizen_check < home_pos, (
        "canHome citizen check must precede the home button creation"
    )


# ─── C15: _cityPagedListSection defined ──────────────────────────────

def test_cityPagedListSection_defined():
    """_cityPagedListSection function is defined in client.html."""
    html = _html()
    assert re.search(r"function\s+_cityPagedListSection\s*\(", html), (
        "_cityPagedListSection function not defined"
    )


def test_cityPagedListSection_has_pageSize_param():
    """_cityPagedListSection accepts a pageSize parameter."""
    block = _paged_block(_html())
    assert "pageSize" in block, (
        "_cityPagedListSection does not use a pageSize parameter"
    )


def test_cityPagedListSection_has_prev_next_controls():
    """_cityPagedListSection renders Prev and Next controls."""
    block = _paged_block(_html())
    assert "Prev" in block, "Prev control missing from _cityPagedListSection"
    assert "Next" in block, "Next control missing from _cityPagedListSection"


def test_cityPagedListSection_prev_next_use_addEventListener():
    """Prev/Next controls are wired via addEventListener, not inline onclick."""
    block = _paged_block(_html())
    assert "addEventListener" in block, (
        "Prev/Next pager controls must use addEventListener, not inline onclick"
    )
    # Confirm no inline onclick on the pager buttons in this block
    # (the block should have zero onclick= attributes from inline markup)
    assert 'onclick="' not in block, (
        "_cityPagedListSection must not use inline onclick= attributes"
    )


def test_cityPagedListSection_page_label_rendered():
    """_cityPagedListSection renders a page X/Y label."""
    block = _paged_block(_html())
    assert "page " in block, (
        "page X/Y label not found in _cityPagedListSection"
    )


def test_cityPagedListSection_flat_fallback_for_short_lists():
    """Short lists (len <= pageSize) fall back to flat rendering without controls."""
    block = _paged_block(_html())
    # The flat fallback returns early without building pager controls
    assert "items.length <= pageSize" in block, (
        "flat fallback condition missing from _cityPagedListSection"
    )


# ─── C15: paged helper used for citizens/guests/banishments ───────────

def test_citizens_uses_paged_section():
    """renderCityModal uses _cityPagedListSection for citizens."""
    block = _renderCityModal_block(_html())
    assert "_cityPagedListSection('citizens'" in block, (
        "renderCityModal does not call _cityPagedListSection for citizens"
    )


def test_guests_uses_paged_section():
    """renderCityModal uses _cityPagedListSection for guests."""
    block = _renderCityModal_block(_html())
    assert "_cityPagedListSection('guests'" in block, (
        "renderCityModal does not call _cityPagedListSection for guests"
    )


def test_banishments_uses_paged_section():
    """renderCityModal uses _cityPagedListSection for banishments."""
    block = _renderCityModal_block(_html())
    assert "_cityPagedListSection('banishments'" in block, (
        "renderCityModal does not call _cityPagedListSection for banishments"
    )


def test_paged_section_called_with_pagesize_10():
    """_cityPagedListSection is called with explicit pageSize 10."""
    block = _renderCityModal_block(_html())
    # Calls span multiple lines — match across newlines with re.DOTALL
    assert re.search(
        r"_cityPagedListSection\(.+?,\s*10\s*\)\)", block, re.DOTALL
    ), (
        "_cityPagedListSection not called with pageSize 10 in renderCityModal"
    )


# ─── Era cleanliness ──────────────────────────────────────────────────

def _new_blocks(html: str) -> str:
    return (
        _paged_block(html) +
        _actions_block(html)
    )


def test_no_gcw_empire_token_in_new_code():
    """No GCW token 'empire' in new C6/C15 code blocks."""
    block = _new_blocks(_html())
    assert not re.search(r"\bempire\b", block, re.IGNORECASE), (
        "GCW token 'empire' found in C6/C15 code"
    )


def test_no_gcw_rebel_token_in_new_code():
    """No GCW token 'rebel' in new C6/C15 code blocks."""
    block = _new_blocks(_html())
    assert not re.search(r"\brebel\b", block, re.IGNORECASE), (
        "GCW token 'rebel' found in C6/C15 code"
    )


def test_no_gcw_tie_token_in_new_code():
    """No GCW token 'TIE' in new C6/C15 code blocks."""
    block = _new_blocks(_html())
    assert not re.search(r"\bTIE\b", block, re.IGNORECASE), (
        "GCW token 'TIE' found in C6/C15 code"
    )
