"""
test_gnd_ux_context_panel.py — Ground-UX context panel drop verification.

Asserts (via static parse of static/client.html) that the three new
side-panel cards shipped correctly:

  A) roomdetail-panel  (LOCATION)        — security, desc, services
  B) nearby-panel      (NEARBY SERVICES) — clickable rows → sendCmd
  C) influence-panel   (ZONE INFLUENCE)  — CW-era org codes only

Pure-Python regex/string checks against the raw HTML; no DOM runtime
needed (mirrors test_client_wireup_42c.py style).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ─── A. DOM IDs — three panels must exist ─────────────────────────────

def test_roomdetail_panel_id_exists():
    """roomdetail-panel DOM id is present in client.html."""
    assert 'id="roomdetail-panel"' in _html(), (
        "roomdetail-panel missing from DOM"
    )


def test_nearby_panel_id_exists():
    """nearby-panel DOM id is present in client.html."""
    assert 'id="nearby-panel"' in _html(), (
        "nearby-panel missing from DOM"
    )


def test_influence_panel_id_exists():
    """influence-panel DOM id is present in client.html."""
    assert 'id="influence-panel"' in _html(), (
        "influence-panel missing from DOM"
    )


# ─── B. Render functions defined ──────────────────────────────────────

def test_renderRoomDetailPanel_defined():
    """renderRoomDetailPanel function is defined."""
    html = _html()
    assert re.search(r"function\s+renderRoomDetailPanel\s*\(", html), (
        "renderRoomDetailPanel not defined"
    )


def test_renderNearbyServices_defined():
    """renderNearbyServices function is defined."""
    html = _html()
    assert re.search(r"function\s+renderNearbyServices\s*\(", html), (
        "renderNearbyServices not defined"
    )


def test_renderZoneInfluence_defined():
    """renderZoneInfluence function is defined."""
    html = _html()
    assert re.search(r"function\s+renderZoneInfluence\s*\(", html), (
        "renderZoneInfluence not defined"
    )


# ─── C. Render functions invoked from handleHudUpdate ─────────────────

def _handleHudUpdate_body(html: str) -> str:
    """Extract text of handleHudUpdate from its definition to the next
    top-level function, so we scope all assertions to that function."""
    start = html.find("function handleHudUpdate(data)")
    assert start != -1, "handleHudUpdate not found"
    # The function body is large (~400 lines); take 30K chars to be safe.
    return html[start: start + 30000]


def test_renderRoomDetailPanel_called_from_handleHudUpdate():
    """renderRoomDetailPanel is called inside handleHudUpdate."""
    body = _handleHudUpdate_body(_html())
    assert "renderRoomDetailPanel(data)" in body, (
        "renderRoomDetailPanel not invoked from handleHudUpdate"
    )


def test_renderNearbyServices_called_from_handleHudUpdate():
    """renderNearbyServices is called inside handleHudUpdate."""
    body = _handleHudUpdate_body(_html())
    assert "renderNearbyServices(data)" in body, (
        "renderNearbyServices not invoked from handleHudUpdate"
    )


def test_renderZoneInfluence_called_from_handleHudUpdate():
    """renderZoneInfluence is called inside handleHudUpdate."""
    body = _handleHudUpdate_body(_html())
    assert "renderZoneInfluence(data)" in body, (
        "renderZoneInfluence not invoked from handleHudUpdate"
    )


# ─── D. HUD fields consumed ───────────────────────────────────────────

def test_room_services_field_consumed():
    """room_services field is read in the render functions."""
    assert "room_services" in _html(), (
        "room_services field not referenced"
    )


def test_nearby_services_field_consumed():
    """nearby_services field is read in the render functions."""
    assert "nearby_services" in _html(), (
        "nearby_services field not referenced"
    )


def test_zone_influence_field_consumed():
    """zone_influence field is read in the render functions."""
    assert "zone_influence" in _html(), (
        "zone_influence field not referenced"
    )


def test_room_description_field_consumed():
    """room_description field is read (both log append + panel)."""
    html = _html()
    # Must appear more than once: once in the existing log append, once in panel
    count = html.count("room_description")
    assert count >= 2, (
        f"Expected room_description to appear >=2 times; got {count}"
    )


def test_security_level_field_consumed():
    """security_level field is read in the panel renderer."""
    assert "security_level" in _html(), (
        "security_level field not referenced"
    )


# ─── E. Nearby rows wire sendCmd(direction) ───────────────────────────

def _nearby_renderer_block(html: str) -> str:
    """Extract the renderNearbyServices function body."""
    start = html.find("function renderNearbyServices(")
    assert start != -1, "renderNearbyServices not found"
    return html[start: start + 3000]


def test_nearby_rows_call_sendCmd_with_direction():
    """Nearby item click handler sends the direction via sendCmd."""
    block = _nearby_renderer_block(_html())
    assert re.search(r"sendCmd\s*\(\s*direction\s*\)", block), (
        "nearby-panel click should call sendCmd(direction)"
    )


def test_nearby_rows_use_addEventListener_not_inline_onclick():
    """Nearby rows use addEventListener (not inline onclick) for click."""
    block = _nearby_renderer_block(_html())
    assert "addEventListener" in block, (
        "nearby-panel should attach click via addEventListener"
    )


# ─── F. CW org codes in influence renderer ────────────────────────────

def _influence_renderer_block(html: str) -> str:
    """Extract the renderZoneInfluence function body."""
    start = html.find("function renderZoneInfluence(")
    assert start != -1, "renderZoneInfluence not found"
    return html[start: start + 3000]


def test_cw_org_republic_present():
    """'republic' appears in renderZoneInfluence."""
    assert "republic" in _influence_renderer_block(_html()), (
        "CW org 'republic' missing from influence renderer"
    )


def test_cw_org_cis_present():
    """'cis' appears in renderZoneInfluence."""
    assert "cis" in _influence_renderer_block(_html()), (
        "CW org 'cis' missing from influence renderer"
    )


def test_cw_org_hutt_cartel_present():
    """'hutt_cartel' appears in renderZoneInfluence."""
    assert "hutt_cartel" in _influence_renderer_block(_html()), (
        "CW org 'hutt_cartel' missing from influence renderer"
    )


# ─── G. Era cleanliness — no GCW tokens in the three new renderers ────

def _extract_fn(html: str, fn_name: str) -> str:
    """Extract a top-level function from the HTML by scanning for its
    closing brace (brace counting).  Stops as soon as the brace depth
    returns to 0 after the opening, so we never bleed into the next
    function."""
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
    # Fallback: take a safe fixed window
    return html[start: start + 3000]


def _combined_new_renderer_blocks(html: str) -> str:
    """Return the text of the three new render functions combined."""
    return (
        _extract_fn(html, "renderRoomDetailPanel") +
        _extract_fn(html, "renderNearbyServices") +
        _extract_fn(html, "renderZoneInfluence")
    )


def test_no_gcw_empire_token_in_new_renderers():
    """'empire' (case-insensitive) must not appear in the three new renderers."""
    block = _combined_new_renderer_blocks(_html())
    assert not re.search(r"empire", block, re.IGNORECASE), (
        "GCW token 'empire' found in new context-panel renderers"
    )


def test_no_gcw_rebel_token_in_new_renderers():
    """'rebel' (case-insensitive) must not appear in the three new renderers."""
    block = _combined_new_renderer_blocks(_html())
    assert not re.search(r"rebel", block, re.IGNORECASE), (
        "GCW token 'rebel' found in new context-panel renderers"
    )


def test_no_gcw_tie_token_in_new_renderers():
    """'\\bTIE\\b' must not appear in the three new renderers."""
    block = _combined_new_renderer_blocks(_html())
    assert not re.search(r"\bTIE\b", block, re.IGNORECASE), (
        "GCW token 'TIE' found in new context-panel renderers"
    )
