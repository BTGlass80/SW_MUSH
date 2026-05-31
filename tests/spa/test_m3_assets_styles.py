"""
test_m3_assets_styles.py — regression tests for static/spa/m3_assets_styles.js.

Drop 4.1b · Tier 1 #4 · May 26 2026.

Each of the 12 STYLE_PRIMITIVES builders should:
  - Return an SVG element (g or rect, depending on the style)
  - Use the supplied palette for fills and strokes
  - Produce the expected child count (catches off-by-one in the port)
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
    SPA_DIR / "m3_assets_styles.js",
]


def test_module_loads_and_exports() -> None:
    """STYLE_PRIMITIVES is exported with the 12 expected style keys."""
    result = run_with_dom(SCRIPTS, """
        result = {
            hasNamespace: typeof window.M3AssetsStyles === 'object',
            keys: window.M3AssetsStyles
                ? Object.keys(window.M3AssetsStyles.STYLE_PRIMITIVES).sort()
                : []
        };
    """)
    assert result["hasNamespace"]
    assert result["keys"] == [
        "cantina", "civic", "default", "dock", "gate", "housing",
        "hutt", "industrial", "landmark", "street", "vendor", "warehouse",
    ]


def test_every_primitive_returns_svg_element() -> None:
    """Every builder, called with a palette, returns an SVG element."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var sp = window.M3AssetsStyles.STYLE_PRIMITIVES;
        result = {};
        Object.keys(sp).forEach(function(name) {
            var el = sp[name](p);
            result[name] = {
                tag: el.tagName,
                ns: el.namespaceURI,
                hasChildren: el.childNodes.length > 0 || el.tagName === 'rect'
            };
        });
    """)
    for name, info in result.items():
        # Most return <g>; SP_Default returns a single <rect>.
        assert info["tag"] in ("g", "rect"), f"{name} returned <{info['tag']}>"
        assert info["ns"] == "http://www.w3.org/2000/svg", f"{name} not in SVG namespace"


def test_dock_has_expected_children() -> None:
    """SP_Dock: outer rect + bay door path + door line + landing ring + center."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsStyles.STYLE_PRIMITIVES.dock(p);
        var tags = [];
        for (var i = 0; i < g.childNodes.length; i++) tags.push(g.childNodes[i].tagName);
        result = { count: g.childNodes.length, tags: tags };
    """)
    assert result["count"] == 5
    assert result["tags"] == ["rect", "path", "line", "circle", "circle"]


def test_industrial_has_8_corrugated_lines() -> None:
    """SP_Industrial: outer rect + 5 vent stacks + 8 corrugated lines = 14 children."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsStyles.STYLE_PRIMITIVES.industrial(p);
        var tags = [];
        for (var i = 0; i < g.childNodes.length; i++) tags.push(g.childNodes[i].tagName);
        var lineCount = tags.filter(function(t) { return t === 'line'; }).length;
        var rectCount = tags.filter(function(t) { return t === 'rect'; }).length;
        result = { total: g.childNodes.length, lines: lineCount, rects: rectCount };
    """)
    assert result["rects"] == 6  # outer + 5 vent stacks
    assert result["lines"] == 8  # 8 corrugated lines


def test_vendor_uses_palette_fill() -> None:
    """SP_Vendor's main rect uses palette.fillVendor."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsStyles.STYLE_PRIMITIVES.vendor(p);
        var mainRect = g.childNodes[0];
        result = {
            tag: mainRect.tagName,
            fill: mainRect.getAttribute('fill'),
            expected: p.fillVendor
        };
    """)
    assert result["tag"] == "rect"
    assert result["fill"] == "#d4a060"
    assert result["fill"] == result["expected"]


def test_default_returns_single_rect_not_g() -> None:
    """SP_Default returns a lone <rect>, not wrapped in <g> (matches JSX source)."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var el = window.M3AssetsStyles.STYLE_PRIMITIVES['default'](p);
        result = {
            tag: el.tagName,
            dasharray: el.getAttribute('stroke-dasharray')
        };
    """)
    assert result["tag"] == "rect"
    assert result["dasharray"] == "2 2"


def test_hutt_includes_text_glyph() -> None:
    """SP_Hutt includes a <text> child with the Egyptian crocodile glyph."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsStyles.STYLE_PRIMITIVES.hutt(p);
        var lastChild = g.childNodes[g.childNodes.length - 1];
        result = {
            lastTag: lastChild.tagName,
            text: lastChild.textContent,
            fill: lastChild.getAttribute('fill'),
            fontFamily: lastChild.getAttribute('font-family')
        };
    """)
    assert result["lastTag"] == "text"
    assert result["text"] == "𓆗"  # the wealth-marker glyph
    assert result["fill"] == "#ffd56e"  # tatooine.gold
    assert result["fontFamily"] == "serif"


def test_palette_swap_changes_colors() -> None:
    """Same builder with a different palette produces different fills."""
    result = run_with_dom(SCRIPTS, """
        var tat = window.M3Palettes.getPalette('tatooine');
        var cor = window.M3Palettes.getPalette('coruscant_under');
        var sp  = window.M3AssetsStyles.STYLE_PRIMITIVES;
        var dockTat = sp.dock(tat).childNodes[0].getAttribute('fill');
        var dockCor = sp.dock(cor).childNodes[0].getAttribute('fill');
        result = { tat: dockTat, cor: dockCor };
    """)
    assert result["tat"] == "#b46a3a"  # tatooine.fillDock
    assert result["cor"] == "#3a2820"  # coruscant_under.fillDock
    assert result["tat"] != result["cor"]
