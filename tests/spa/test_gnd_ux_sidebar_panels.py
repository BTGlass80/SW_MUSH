"""
test_gnd_ux_sidebar_panels.py — Ground-UX sidebar panels drop-B verification.

Asserts (via static parse of static/client.html) that the two new
side-panel cards shipped correctly:

  D) here-panel        (HERE)         — room_contents: NPCs/players/vendor_droids
  E) activejobs-panel  (ACTIVE JOBS)  — active_jobs: job list

Pure-Python regex/string checks against the raw HTML; no DOM runtime
needed (mirrors test_gnd_ux_context_panel.py style).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ─── A. DOM IDs — two new panels must exist ───────────────────────────

def test_here_panel_id_exists():
    """here-panel DOM id is present in client.html."""
    assert 'id="here-panel"' in _html(), "here-panel missing from DOM"


def test_activejobs_panel_id_exists():
    """activejobs-panel DOM id is present in client.html."""
    assert 'id="activejobs-panel"' in _html(), "activejobs-panel missing from DOM"


# ─── B. Render functions defined ──────────────────────────────────────

def test_renderHerePanel_defined():
    """renderHerePanel function is defined."""
    assert re.search(r"function\s+renderHerePanel\s*\(", _html()), (
        "renderHerePanel not defined"
    )


def test_renderActiveJobsPanel_defined():
    """renderActiveJobsPanel function is defined."""
    assert re.search(r"function\s+renderActiveJobsPanel\s*\(", _html()), (
        "renderActiveJobsPanel not defined"
    )


# ─── C. Render functions invoked from handleHudUpdate ─────────────────

def _handleHudUpdate_body(html: str) -> str:
    """Extract text of handleHudUpdate from its definition; take 32K chars."""
    start = html.find("function handleHudUpdate(data)")
    assert start != -1, "handleHudUpdate not found"
    return html[start: start + 32000]


def test_renderHerePanel_called_from_handleHudUpdate():
    """renderHerePanel is called inside handleHudUpdate."""
    body = _handleHudUpdate_body(_html())
    assert "renderHerePanel(data)" in body, (
        "renderHerePanel not invoked from handleHudUpdate"
    )


def test_renderActiveJobsPanel_called_from_handleHudUpdate():
    """renderActiveJobsPanel is called inside handleHudUpdate."""
    body = _handleHudUpdate_body(_html())
    assert "renderActiveJobsPanel(data)" in body, (
        "renderActiveJobsPanel not invoked from handleHudUpdate"
    )


# ─── D. HUD fields consumed ───────────────────────────────────────────

def test_room_contents_field_consumed():
    """room_contents field is referenced in client.html."""
    assert "room_contents" in _html(), "room_contents field not referenced"


def test_npcs_sub_field_consumed():
    """room_contents.npcs sub-field is accessed."""
    assert ".npcs" in _html(), ".npcs sub-field not accessed"


def test_players_sub_field_consumed():
    """room_contents.players sub-field is accessed."""
    assert ".players" in _html(), ".players sub-field not accessed"


def test_vendor_droids_sub_field_consumed():
    """room_contents.vendor_droids sub-field is accessed."""
    assert ".vendor_droids" in _html(), ".vendor_droids sub-field not accessed"


def test_active_jobs_field_consumed():
    """active_jobs field is referenced in client.html."""
    assert "active_jobs" in _html(), "active_jobs field not referenced"


# ─── E. HERE panel — NPC interaction correctness ──────────────────────

def _extract_fn(html: str, fn_name: str) -> str:
    """Extract a top-level function from the HTML by brace-counting."""
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
    return html[start: start + 6000]


def test_here_panel_npc_action_buttons_wire_sendCmd():
    """NPC action buttons in renderHerePanel call sendCmd(action + ' ' + npc.name)."""
    block = _extract_fn(_html(), "renderHerePanel")
    assert re.search(r"sendCmd\s*\(\s*action\s*\+\s*['\"] ['\"]", block), (
        "renderHerePanel action buttons should call sendCmd(action + ' ' + npc.name)"
    )


def test_here_panel_hostile_handled():
    """renderHerePanel handles the hostile flag (class or branch on npc.hostile)."""
    block = _extract_fn(_html(), "renderHerePanel")
    assert "hostile" in block, (
        "renderHerePanel does not reference 'hostile'"
    )


def test_here_panel_actions_uses_addEventListener():
    """renderHerePanel attaches action button clicks via addEventListener."""
    block = _extract_fn(_html(), "renderHerePanel")
    assert "addEventListener" in block, (
        "renderHerePanel should use addEventListener for action buttons"
    )


def test_here_panel_players_rendered():
    """renderHerePanel has a code path for players."""
    block = _extract_fn(_html(), "renderHerePanel")
    assert "players" in block, (
        "renderHerePanel does not render players"
    )


def test_here_panel_vendor_droids_rendered():
    """renderHerePanel has a code path for vendor_droids."""
    block = _extract_fn(_html(), "renderHerePanel")
    assert "vendor_droids" in block, (
        "renderHerePanel does not render vendor_droids"
    )


# ─── F. Active Jobs panel — type coverage ─────────────────────────────

def test_activejobs_tutorial_handled():
    """renderActiveJobsPanel handles 'tutorial' job type."""
    block = _extract_fn(_html(), "renderActiveJobsPanel")
    assert "tutorial" in block, "renderActiveJobsPanel missing 'tutorial' type"


def test_activejobs_mission_handled():
    """renderActiveJobsPanel handles 'mission' job type."""
    block = _extract_fn(_html(), "renderActiveJobsPanel")
    assert "mission" in block, "renderActiveJobsPanel missing 'mission' type"


def test_activejobs_bounty_handled():
    """renderActiveJobsPanel handles 'bounty' job type."""
    block = _extract_fn(_html(), "renderActiveJobsPanel")
    assert "bounty" in block, "renderActiveJobsPanel missing 'bounty' type"


def test_activejobs_smuggle_handled():
    """renderActiveJobsPanel handles 'smuggle' job type."""
    block = _extract_fn(_html(), "renderActiveJobsPanel")
    assert "smuggle" in block, "renderActiveJobsPanel missing 'smuggle' type"


def test_activejobs_quest_handled():
    """renderActiveJobsPanel handles 'quest' job type."""
    block = _extract_fn(_html(), "renderActiveJobsPanel")
    assert "quest" in block, "renderActiveJobsPanel missing 'quest' type"


def test_activejobs_reward_rendered():
    """renderActiveJobsPanel renders the reward field."""
    block = _extract_fn(_html(), "renderActiveJobsPanel")
    assert "reward" in block, "renderActiveJobsPanel does not render reward"


def test_activejobs_target_rendered_for_bounty():
    """renderActiveJobsPanel renders the target field for bounty jobs."""
    block = _extract_fn(_html(), "renderActiveJobsPanel")
    assert "target" in block, "renderActiveJobsPanel does not render target"


def test_activejobs_objective_rendered():
    """renderActiveJobsPanel renders the objective field."""
    block = _extract_fn(_html(), "renderActiveJobsPanel")
    assert "objective" in block, "renderActiveJobsPanel does not render objective"


# ─── G. Era cleanliness — no GCW tokens in the two new renderers ──────

def _combined_new_renderer_blocks(html: str) -> str:
    return (
        _extract_fn(html, "renderHerePanel") +
        _extract_fn(html, "renderActiveJobsPanel")
    )


def test_no_gcw_empire_in_new_renderers():
    """'empire' must not appear in the two new renderers."""
    block = _combined_new_renderer_blocks(_html())
    assert not re.search(r"empire", block, re.IGNORECASE), (
        "GCW token 'empire' found in new sidebar renderers"
    )


def test_no_gcw_rebel_in_new_renderers():
    """'rebel' must not appear in the two new renderers."""
    block = _combined_new_renderer_blocks(_html())
    assert not re.search(r"rebel", block, re.IGNORECASE), (
        "GCW token 'rebel' found in new sidebar renderers"
    )


def test_no_gcw_tie_in_new_renderers():
    """'\\bTIE\\b' must not appear in the two new renderers."""
    block = _combined_new_renderer_blocks(_html())
    assert not re.search(r"\bTIE\b", block, re.IGNORECASE), (
        "GCW token 'TIE' found in new sidebar renderers"
    )


# ─── H. CSS classes are defined ───────────────────────────────────────

def test_here_entry_css_defined():
    """.here-entry CSS class is defined in the stylesheet."""
    assert ".here-entry" in _html(), ".here-entry CSS missing"


def test_job_entry_css_defined():
    """.job-entry CSS class is defined in the stylesheet."""
    assert ".job-entry" in _html(), ".job-entry CSS missing"
