"""
test_m3_tokens_svgel.py — tests for the svgEl helper added in Drop 4.1b.

Drop 4.1b · Tier 1 #4 · May 26 2026.

The base m3_tokens.js tests (WOUND_RUNGS, woundRung) live in
test_m3_tokens.py — those don't need a DOM. This file covers the new
svgEl helper which requires document.createElementNS to work.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add this directory to sys.path so we can import spa_dom_harness
sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom


SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"
TOKENS_JS = SPA_DIR / "m3_tokens.js"


def test_svgel_exists_on_m3tokens() -> None:
    """M3Tokens.svgEl is exported as a function."""
    result = run_with_dom([TOKENS_JS], """
        result = {
            type: typeof window.M3Tokens.svgEl,
            ns:   window.M3Tokens.SVG_NS
        };
    """)
    assert result["type"] == "function"
    assert result["ns"] == "http://www.w3.org/2000/svg"


def test_svgel_creates_element_in_svg_namespace() -> None:
    """svgEl('rect', ...) creates a real SVG element."""
    result = run_with_dom([TOKENS_JS], """
        var rect = window.M3Tokens.svgEl('rect', { x: 10, y: 20, width: 30, height: 40 });
        result = {
            tag: rect.tagName,
            ns:  rect.namespaceURI,
            x: rect.getAttribute('x'),
            y: rect.getAttribute('y'),
            width: rect.getAttribute('width'),
            height: rect.getAttribute('height')
        };
    """)
    # jsdom returns 'rect' lowercase for SVG elements (case-preserving)
    assert result["tag"] == "rect"
    assert result["ns"] == "http://www.w3.org/2000/svg"
    assert result["x"] == "10"
    assert result["y"] == "20"
    assert result["width"] == "30"
    assert result["height"] == "40"


def test_svgel_converts_camelcase_to_kebab() -> None:
    """svgEl converts strokeWidth/strokeDasharray etc. to kebab-case."""
    result = run_with_dom([TOKENS_JS], """
        var line = window.M3Tokens.svgEl('line', {
            x1: 0, y1: 0, x2: 100, y2: 100,
            stroke: '#ff0000',
            strokeWidth: 2.5,
            strokeDasharray: '5 3',
            strokeLinecap: 'round',
            strokeOpacity: 0.7,
            fillOpacity: 0.3
        });
        result = {
            stroke:           line.getAttribute('stroke'),
            stroke_width:     line.getAttribute('stroke-width'),
            stroke_dasharray: line.getAttribute('stroke-dasharray'),
            stroke_linecap:   line.getAttribute('stroke-linecap'),
            stroke_opacity:   line.getAttribute('stroke-opacity'),
            fill_opacity:     line.getAttribute('fill-opacity'),
            // camelCase form should NOT be present
            strokeWidth_camel:     line.getAttribute('strokeWidth'),
            strokeDasharray_camel: line.getAttribute('strokeDasharray')
        };
    """)
    assert result["stroke"] == "#ff0000"
    assert result["stroke_width"] == "2.5"
    assert result["stroke_dasharray"] == "5 3"
    assert result["stroke_linecap"] == "round"
    assert result["stroke_opacity"] == "0.7"
    assert result["fill_opacity"] == "0.3"
    # camelCase forms should be null (not set as attrs)
    assert result["strokeWidth_camel"] is None
    assert result["strokeDasharray_camel"] is None


def test_svgel_preserves_viewbox_camelcase() -> None:
    """svgEl leaves viewBox alone (it really IS camelCase in SVG)."""
    result = run_with_dom([TOKENS_JS], """
        var svg = window.M3Tokens.svgEl('svg', { viewBox: '0 0 100 100', width: 200 });
        result = {
            viewBox_camel: svg.getAttribute('viewBox'),
            viewbox_lower: svg.getAttribute('viewbox')
        };
    """)
    # viewBox is camelCase in actual SVG spec; svgEl should preserve it.
    assert result["viewBox_camel"] == "0 0 100 100"


def test_svgel_skips_null_and_false_attrs() -> None:
    """null, undefined, false attributes are skipped silently."""
    result = run_with_dom([TOKENS_JS], """
        var rect = window.M3Tokens.svgEl('rect', {
            x: 0, y: 0,
            fill: null,
            stroke: undefined,
            visible: false,
            opacity: 0  // zero is a valid value, NOT skipped
        });
        result = {
            x:       rect.getAttribute('x'),
            fill:    rect.getAttribute('fill'),
            stroke:  rect.getAttribute('stroke'),
            visible: rect.getAttribute('visible'),
            opacity: rect.getAttribute('opacity')
        };
    """)
    assert result["x"] == "0"
    assert result["fill"] is None
    assert result["stroke"] is None
    assert result["visible"] is None
    assert result["opacity"] == "0", "Zero is a real value; should NOT be skipped"


def test_svgel_appends_children() -> None:
    """svgEl(tag, attrs, [c1, c2, ...]) appends each child element."""
    result = run_with_dom([TOKENS_JS], """
        var rect1 = window.M3Tokens.svgEl('rect', { x: 0, y: 0, width: 10, height: 10 });
        var rect2 = window.M3Tokens.svgEl('rect', { x: 20, y: 20, width: 10, height: 10 });
        var g = window.M3Tokens.svgEl('g', { transform: 'translate(50 50)' }, [rect1, rect2]);
        result = {
            childCount: g.childNodes.length,
            child0: g.childNodes[0].tagName,
            child1: g.childNodes[1].tagName,
            transform: g.getAttribute('transform')
        };
    """)
    assert result["childCount"] == 2
    assert result["child0"] == "rect"
    assert result["child1"] == "rect"
    assert result["transform"] == "translate(50 50)"


def test_svgel_string_children_become_text_nodes() -> None:
    """svgEl('text', {...}, ['some content']) wraps string in a text node."""
    result = run_with_dom([TOKENS_JS], """
        var text = window.M3Tokens.svgEl('text', { x: 10, y: 20 }, ['Hello world']);
        result = {
            tag: text.tagName,
            childCount: text.childNodes.length,
            textContent: text.textContent
        };
    """)
    assert result["tag"] == "text"
    assert result["childCount"] == 1
    assert result["textContent"] == "Hello world"


def test_svgel_skips_null_children() -> None:
    """null/undefined entries in children array are silently skipped."""
    result = run_with_dom([TOKENS_JS], """
        // Two distinct rect nodes — appendChild moves existing nodes,
        // it doesn't duplicate them, so passing the same rect twice gives 1 child.
        var r1 = window.M3Tokens.svgEl('rect', { x: 0,  y: 0,  width: 10, height: 10 });
        var r2 = window.M3Tokens.svgEl('rect', { x: 20, y: 20, width: 10, height: 10 });
        var g = window.M3Tokens.svgEl('g', null, [r1, null, undefined, r2]);
        result = { childCount: g.childNodes.length };
    """)
    # Two real rects, two nulls skipped → 2 children
    assert result["childCount"] == 2


def test_svgel_no_children_arg_is_fine() -> None:
    """svgEl(tag, attrs) with no children arg returns a leaf element."""
    result = run_with_dom([TOKENS_JS], """
        var circle = window.M3Tokens.svgEl('circle', { cx: 50, cy: 50, r: 20 });
        result = {
            tag: circle.tagName,
            childCount: circle.childNodes.length
        };
    """)
    assert result["tag"] == "circle"
    assert result["childCount"] == 0
