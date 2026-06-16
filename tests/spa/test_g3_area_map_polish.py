"""
test_g3_area_map_polish.py — G3 area-map polish verification (T3.18 tail).

Asserts that the two G3 cosmetic additions shipped correctly in
static/client.html:

  1. rm-far CSS class — dot + label opacity for far (non-adjacent, non-current)
     rooms in the legacy renderAreaMap path.
  2. Per-move fade-in — #g-area-map-svg CSS transition + svg.style.opacity
     set/cleared around each re-render.

Pure-Python string checks; no DOM runtime needed.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ─── CSS: rm-far class ────────────────────────────────────────────────

def test_rm_far_dot_opacity_css():
    """.rm-far .rm-dot has reduced opacity styling."""
    html = _html()
    assert ".rm-far .rm-dot" in html, ".rm-far .rm-dot CSS rule missing"
    # The opacity value should be < 1 (dimming)
    m = re.search(r"\.rm-far \.rm-dot\s*\{[^}]*opacity\s*:\s*([\d.]+)", html)
    assert m, ".rm-far .rm-dot opacity property not found"
    assert float(m.group(1)) < 1.0, "rm-far dot opacity should be < 1"


def test_rm_far_label_opacity_css():
    """.rm-far .rm-label has reduced opacity styling."""
    html = _html()
    assert ".rm-far .rm-label" in html, ".rm-far .rm-label CSS rule missing"
    m = re.search(r"\.rm-far \.rm-label\s*\{[^}]*opacity\s*:\s*([\d.]+)", html)
    assert m, ".rm-far .rm-label opacity property not found"
    assert float(m.group(1)) < 1.0, "rm-far label opacity should be < 1"


# ─── CSS: SVG transition ──────────────────────────────────────────────

def test_area_map_svg_transition_css():
    """#g-area-map-svg has a CSS opacity transition for per-move fade-in."""
    html = _html()
    m = re.search(r"#g-area-map-svg\s*\{[^}]*transition[^}]*\}", html)
    assert m, "#g-area-map-svg transition CSS not found"
    assert "opacity" in m.group(0), "#g-area-map-svg transition must include opacity"


# ─── JS: renderAreaMap assigns rm-far ────────────────────────────────

def test_render_area_map_assigns_rm_far():
    """renderAreaMap pushes 'rm-far' for non-current, non-adjacent rooms."""
    html = _html()
    # The function body should contain the else branch that pushes 'rm-far'
    assert "classes.push('rm-far')" in html or 'classes.push("rm-far")' in html, (
        "renderAreaMap must push 'rm-far' class for far rooms"
    )


def test_render_area_map_uses_else_if_for_adj():
    """renderAreaMap uses else-if so rm-far is mutually exclusive with rm-adj."""
    html = _html()
    # The pattern must be else if (isAdj) not two separate ifs
    assert re.search(r"else if \(isAdj\)", html), (
        "renderAreaMap should use 'else if (isAdj)' to ensure mutual exclusion "
        "of rm-adj and rm-far classes"
    )


# ─── JS: fade-in animation ───────────────────────────────────────────

def test_render_area_map_sets_opacity_zero_before_clear():
    """renderAreaMap sets svg.style.opacity='0' before clearing the SVG."""
    html = _html()
    # Find renderAreaMap body
    fn_start = html.find("function renderAreaMap(mapData)")
    fn_end = html.find("\nfunction _reverseDir(d)", fn_start)
    assert fn_start != -1, "renderAreaMap not found"
    fn_body = html[fn_start:fn_end]
    assert "svg.style.opacity = '0'" in fn_body or 'svg.style.opacity = "0"' in fn_body, (
        "renderAreaMap must set svg.style.opacity='0' before clearing to enable fade-in"
    )


def test_render_area_map_uses_request_animation_frame_for_fade_in():
    """renderAreaMap uses requestAnimationFrame to restore opacity after render."""
    html = _html()
    fn_start = html.find("function renderAreaMap(mapData)")
    fn_end = html.find("\nfunction _reverseDir(d)", fn_start)
    fn_body = html[fn_start:fn_end]
    assert "requestAnimationFrame" in fn_body, (
        "renderAreaMap must use requestAnimationFrame to trigger opacity fade-in"
    )
    assert "svg.style.opacity = '1'" in fn_body or 'svg.style.opacity = "1"' in fn_body, (
        "renderAreaMap must restore svg.style.opacity to '1' inside requestAnimationFrame"
    )
