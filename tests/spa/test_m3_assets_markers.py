"""
test_m3_assets_markers.py — regression tests for static/spa/m3_assets_markers.js.

Drop 4.1c · Tier 1 #4 · May 26 2026.

Each of the 10 MARKERS builders should:
  - Return an SVG element in the SVG namespace
  - Use the supplied palette for fills and strokes
  - Produce the expected child structure (catches off-by-one in the port)
  - Handle their option variants (kind, bearing, name, size) correctly
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"
SCRIPTS = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_palettes.js",
    SPA_DIR / "m3_assets_markers.js",
]


def test_module_loads_and_exports_ten_markers() -> None:
    """MARKERS exports the 10 expected marker keys."""
    result = run_with_dom(SCRIPTS, """
        result = {
            hasNamespace: typeof window.M3AssetsMarkers === 'object',
            keys: window.M3AssetsMarkers
                ? Object.keys(window.M3AssetsMarkers.MARKERS).sort()
                : []
        };
    """)
    assert result["hasNamespace"]
    assert result["keys"] == [
        "anomaly_t1", "anomaly_t2", "anomaly_t3",
        "bounty", "mission", "npc", "objective",
        "pc", "player", "vendor",
    ]


def test_every_marker_returns_svg_element() -> None:
    """Every builder, called with a palette, returns an SVG element."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var m = window.M3AssetsMarkers.MARKERS;
        var defaults = {
            player:     { p: p, bearing: 0, size: 11 },
            pc:         { p: p, bearing: 30, size: 9, name: 'TEY VOSS' },
            npc:        { p: p, kind: 'friendly', size: 8 },
            vendor:     { p: p, size: 8 },
            mission:    { p: p, size: 9 },
            bounty:     { p: p, size: 9 },
            objective:  { p: p, size: 9 },
            anomaly_t1: { p: p, size: 9 },
            anomaly_t2: { p: p, size: 10 },
            anomaly_t3: { p: p, size: 12 }
        };
        result = {};
        Object.keys(m).forEach(function(name) {
            var el = m[name](defaults[name]);
            result[name] = { tag: el.tagName, ns: el.namespaceURI };
        });
    """)
    for name, info in result.items():
        # Most return <g>; MK_Objective returns a single <polygon>.
        assert info["tag"] in ("g", "polygon"), f"{name} returned <{info['tag']}>"
        assert info["ns"] == "http://www.w3.org/2000/svg", \
            f"{name} not in SVG namespace"


def test_player_marker_has_three_children_with_rotation() -> None:
    """MK_Player: rotation group containing pulse ring + inner + chevron."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsMarkers.MARKERS.player({ p: p, bearing: 45, size: 14 });
        var kids = [];
        for (var i = 0; i < g.childNodes.length; i++) kids.push(g.childNodes[i].tagName);
        result = {
            tag: g.tagName,
            transform: g.getAttribute('transform'),
            childCount: g.childNodes.length,
            childTags: kids,
            // pulse ring (first child) should contain two <animate> elements
            pulseAnimateCount: g.childNodes[0].childNodes.length
        };
    """)
    assert result["tag"] == "g"
    assert result["transform"] == "rotate(45)"
    assert result["childCount"] == 3
    assert result["childTags"] == ["circle", "circle", "path"]
    # Two <animate> elements (r + opacity) inside the pulse ring
    assert result["pulseAnimateCount"] == 2


def test_npc_hostile_returns_red_triangle() -> None:
    """MK_NPC(kind='hostile') returns a triangle path, not a dot."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsMarkers.MARKERS.npc({ p: p, kind: 'hostile', size: 8 });
        result = {
            tag: g.tagName,
            firstChildTag: g.childNodes[0].tagName,
            fill: g.childNodes[0].getAttribute('fill'),
            expected: p.red
        };
    """)
    assert result["tag"] == "g"
    assert result["firstChildTag"] == "path"
    assert result["fill"] == result["expected"]


def test_npc_friendly_returns_amber_dot() -> None:
    """MK_NPC(kind='friendly') uses palette.amber for the dot."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsMarkers.MARKERS.npc({ p: p, kind: 'friendly', size: 6 });
        var dot = g.childNodes[0];
        result = {
            tag: dot.tagName,
            fill: dot.getAttribute('fill'),
            expectedAmber: p.amber
        };
    """)
    assert result["tag"] == "circle"
    assert result["fill"] == result["expectedAmber"]


def test_pc_marker_label_appears_when_named() -> None:
    """MK_PC with a name adds a fourth child — the <text> label."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var withName = window.M3AssetsMarkers.MARKERS.pc({ p: p, name: 'TEY VOSS', size: 9 });
        var noName  = window.M3AssetsMarkers.MARKERS.pc({ p: p, size: 9 });
        var lastWithName = withName.childNodes[withName.childNodes.length - 1];
        result = {
            withName: withName.childNodes.length,
            withoutName: noName.childNodes.length,
            labelTag: lastWithName.tagName,
            labelText: lastWithName.textContent
        };
    """)
    assert result["withoutName"] == 2  # ring + chevron group
    assert result["withName"] == 3     # + text label
    assert result["labelTag"] == "text"
    assert result["labelText"] == "TEY VOSS"


def test_objective_is_a_10pt_star() -> None:
    """MK_Objective is a single <polygon> with 10 points (5-point star outline)."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var poly = window.M3AssetsMarkers.MARKERS.objective({ p: p, size: 8 });
        var points = poly.getAttribute('points').split(' ');
        result = {
            tag: poly.tagName,
            ptCount: points.length,
            fill: poly.getAttribute('fill'),
            expectedGreen: p.green
        };
    """)
    assert result["tag"] == "polygon"
    assert result["ptCount"] == 10  # alternating outer/inner radii
    assert result["fill"] == result["expectedGreen"]


def test_anomaly_t3_has_pulse_ring_eight_spikes_glow_core() -> None:
    """MK_AnomalyT3: 1 ring + 8 spike lines + 2 core circles = 11 children."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsMarkers.MARKERS.anomaly_t3({ p: p, size: 14 });
        var tags = [];
        for (var i = 0; i < g.childNodes.length; i++) tags.push(g.childNodes[i].tagName);
        var lineCount = tags.filter(function(t) { return t === 'line'; }).length;
        var circleCount = tags.filter(function(t) { return t === 'circle'; }).length;
        // The animate node lives INSIDE the first circle (the pulse ring),
        // not as a sibling — verify that wiring too.
        var firstChild = g.childNodes[0];
        result = {
            total: g.childNodes.length,
            lines: lineCount,
            circles: circleCount,
            firstChildAnimateCount: firstChild.childNodes.length,
            firstChildAnimateTag: firstChild.childNodes[0].tagName
        };
    """)
    assert result["lines"] == 8        # 8 radial spikes
    assert result["circles"] == 3      # pulse ring + glow + core
    assert result["total"] == 11
    assert result["firstChildAnimateCount"] == 1
    assert result["firstChildAnimateTag"] == "animate"
