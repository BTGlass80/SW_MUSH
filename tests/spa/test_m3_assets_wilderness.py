"""
test_m3_assets_wilderness.py — regression tests for static/spa/m3_assets_wilderness.js.

Drop 4.1c · Tier 1 #4 · May 26 2026.

The 6 WILDERNESS_LANDMARKS builders must:
  - Return an SVG element for the requested LOD
  - Strip down to a single-element icon at lod='icon'
  - Fill in the detailed flourishes only at lod='detailed'
  - Expose both short-slug AND long-ident lookups (for composition engine
    AND for the asset catalog's WLM_* entries respectively)
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
    SPA_DIR / "m3_assets_wilderness.js",
]


def test_module_loads_and_exports_six_landmarks() -> None:
    """WILDERNESS_LANDMARKS exports exactly the 6 expected slugs."""
    result = run_with_dom(SCRIPTS, """
        result = {
            hasNamespace: typeof window.M3AssetsWilderness === 'object',
            keys: window.M3AssetsWilderness
                ? Object.keys(window.M3AssetsWilderness.WILDERNESS_LANDMARKS).sort()
                : []
        };
    """)
    assert result["hasNamespace"]
    assert result["keys"] == [
        "abandoned_mine", "jabba_palace", "krayt_skeleton",
        "moisture_farm", "sandcrawler", "tusken_camp",
    ]


def test_dual_lookup_short_slug_and_long_ident() -> None:
    """The catalog looks up by long ident (WLM_*); the engine by short slug.
    Both routes must resolve to the same builder."""
    result = run_with_dom(SCRIPTS, """
        var ns = window.M3AssetsWilderness;
        result = {
            byShort: typeof ns.WILDERNESS_LANDMARKS.tusken_camp === 'function',
            byLong:  typeof ns.WLM_TuskenCamp === 'function',
            sameFn:  ns.WILDERNESS_LANDMARKS.tusken_camp === ns.WLM_TuskenCamp
        };
    """)
    assert result["byShort"]
    assert result["byLong"]
    assert result["sameFn"]


def test_every_landmark_returns_svg_at_each_lod() -> None:
    """Every builder, called with each LOD, returns an SVG element."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var wl = window.M3AssetsWilderness.WILDERNESS_LANDMARKS;
        var lods = ['icon', 'detail', 'detailed'];
        result = {};
        Object.keys(wl).forEach(function(name) {
            result[name] = {};
            lods.forEach(function(lod) {
                var el = wl[name]({ p: p, lod: lod });
                result[name][lod] = { tag: el.tagName, ns: el.namespaceURI };
            });
        });
    """)
    for name, byLod in result.items():
        for lod, info in byLod.items():
            assert info["ns"] == "http://www.w3.org/2000/svg", \
                f"{name}@{lod} not in SVG namespace"
            # Icons are single primitives (rect/path/ellipse/circle/g);
            # detail/detailed always wrap in <g>.
            assert info["tag"] in ("g", "rect", "path", "ellipse", "circle"), \
                f"{name}@{lod} returned <{info['tag']}>"


def test_lod_icon_is_simpler_than_lod_detailed() -> None:
    """For each landmark, the detailed form must have strictly more SVG
    primitives than the icon form (a strong sanity check on LOD wiring)."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var wl = window.M3AssetsWilderness.WILDERNESS_LANDMARKS;
        function nodeCount(el) {
            // Recursively count primitive descendants
            var n = 0;
            for (var i = 0; i < el.childNodes.length; i++) {
                n += 1 + nodeCount(el.childNodes[i]);
            }
            // For lone-primitive returns (no children), count the element itself
            return n === 0 ? 1 : n;
        }
        result = {};
        Object.keys(wl).forEach(function(name) {
            var iconEl = wl[name]({ p: p, lod: 'icon' });
            var detEl  = wl[name]({ p: p, lod: 'detailed' });
            result[name] = { icon: nodeCount(iconEl), detailed: nodeCount(detEl) };
        });
    """)
    for name, counts in result.items():
        assert counts["detailed"] > counts["icon"], \
            f"{name}: detailed ({counts['detailed']}) not > icon ({counts['icon']})"


def test_tusken_camp_has_five_tents_in_radial_cluster() -> None:
    """WLM_TuskenCamp@detailed: sandy halo + 5 tent groups + bonfire +
    2 bantha groups = 9 top-level children."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsWilderness.WILDERNESS_LANDMARKS.tusken_camp({
            p: p, lod: 'detailed'
        });
        var tags = [];
        for (var i = 0; i < g.childNodes.length; i++) tags.push(g.childNodes[i].tagName);
        // 5 tent groups + 1 bonfire group + 2 bantha groups = 8 <g> children
        // plus the leading <circle> for the sandy halo
        var groupCount = tags.filter(function(t) { return t === 'g'; }).length;
        result = { total: g.childNodes.length, tags: tags, groups: groupCount };
    """)
    assert result["total"] == 9
    assert result["groups"] == 8  # 5 tents + 1 bonfire + 2 banthas


def test_jabba_palace_carries_hutt_sigil_at_detailed_lod() -> None:
    """At detailed LOD, WLM_JabbaPalace includes a <text> sigil with the
    Hutt crocodile glyph — same character as SP_Hutt in m3_assets_styles."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsWilderness.WILDERNESS_LANDMARKS.jabba_palace({
            p: p, lod: 'detailed'
        });
        var textNode = null;
        for (var i = 0; i < g.childNodes.length; i++) {
            if (g.childNodes[i].tagName === 'text') {
                textNode = g.childNodes[i];
                break;
            }
        }
        result = {
            hasText: textNode !== null,
            text: textNode ? textNode.textContent : '',
            fill: textNode ? textNode.getAttribute('fill') : '',
            expectedGold: p.gold
        };
    """)
    assert result["hasText"]
    assert result["text"] == "𓆗"  # Egyptian crocodile glyph — Hutt wealth marker
    assert result["fill"] == result["expectedGold"]


def test_palette_swap_changes_landmark_colors() -> None:
    """The same landmark with a different palette uses different fills."""
    result = run_with_dom(SCRIPTS, """
        var tat = window.M3Palettes.getPalette('tatooine');
        var cor = window.M3Palettes.getPalette('coruscant_under');
        var wl  = window.M3AssetsWilderness.WILDERNESS_LANDMARKS;
        // moisture_farm@icon is a single <circle> — easy to inspect.
        var tatFill = wl.moisture_farm({ p: tat, lod: 'icon' }).getAttribute('fill');
        var corFill = wl.moisture_farm({ p: cor, lod: 'icon' }).getAttribute('fill');
        result = { tat: tatFill, cor: corFill };
    """)
    # Both palettes have a fillHousing; the values must differ.
    assert result["tat"] != result["cor"]
    assert result["tat"]  # non-empty
    assert result["cor"]  # non-empty


def test_sandcrawler_has_twentyfour_tread_segments() -> None:
    """WLM_Sandcrawler@detailed: 12 bottom tread + 12 top tread = 24 tread
    rects out of the total child rectangle pool."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsWilderness.WILDERNESS_LANDMARKS.sandcrawler({
            p: p, lod: 'detailed'
        });
        var rectsWithGroundShadow = 0;
        for (var i = 0; i < g.childNodes.length; i++) {
            var c = g.childNodes[i];
            if (c.tagName === 'rect' && c.getAttribute('fill') === p.groundShadow) {
                rectsWithGroundShadow++;
            }
        }
        result = { treads: rectsWithGroundShadow };
    """)
    # 12 top + 12 bottom — palette.groundShadow fills only the treads.
    assert result["treads"] == 24
