"""
test_m3_assets_overlays.py — regression tests for static/spa/m3_assets_overlays.js.

Drop 4.1c · Tier 1 #4 · May 26 2026.

Two related concerns under test:
  - TerrainDefs + HazeDefs build <defs> trees the composition engine
    will reference via fill="url(#...)".
  - The OVERLAYS dict has 9 atmospheric/contest builders that take
    options and return SVG elements (or null for "not applicable").
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
    SPA_DIR / "m3_assets_overlays.js",
]


def test_module_loads_and_exports_namespace() -> None:
    """M3AssetsOverlays exports TerrainDefs, HazeDefs, and 9 OVERLAYS keys."""
    result = run_with_dom(SCRIPTS, """
        var ns = window.M3AssetsOverlays || {};
        result = {
            hasNamespace: typeof window.M3AssetsOverlays === 'object',
            hasTerrainDefs: typeof ns.TerrainDefs === 'function',
            hasHazeDefs: typeof ns.HazeDefs === 'function',
            overlayKeys: ns.OVERLAYS ? Object.keys(ns.OVERLAYS).sort() : []
        };
    """)
    assert result["hasNamespace"]
    assert result["hasTerrainDefs"]
    assert result["hasHazeDefs"]
    assert result["overlayKeys"] == [
        "contest_banner", "faction_territory", "neon_halos",
        "rain", "sand_haze", "sandstorm", "smog",
        "time_of_day", "twin_sun_shadows",
    ]


def test_terrain_defs_yields_seven_named_patterns() -> None:
    """TerrainDefs returns a <defs> with all 7 named terrain <pattern>s."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var defs = window.M3AssetsOverlays.TerrainDefs(p);
        var ids = [];
        for (var i = 0; i < defs.childNodes.length; i++) {
            ids.push(defs.childNodes[i].getAttribute('id'));
        }
        result = {
            tag: defs.tagName,
            ns: defs.namespaceURI,
            ids: ids.sort()
        };
    """)
    assert result["tag"] == "defs"
    assert result["ns"] == "http://www.w3.org/2000/svg"
    assert result["ids"] == [
        "terr-canyon", "terr-city", "terr-dune",
        "terr-duracrete", "terr-oasis", "terr-scrub", "terr-vapor",
    ]


def test_haze_defs_yields_two_gradients() -> None:
    """HazeDefs returns a <defs> with haze-grad and atmosphere-grad."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var defs = window.M3AssetsOverlays.HazeDefs(p);
        var ids = [], tags = [];
        for (var i = 0; i < defs.childNodes.length; i++) {
            ids.push(defs.childNodes[i].getAttribute('id'));
            tags.push(defs.childNodes[i].tagName);
        }
        // The haze-grad stop must reference the palette's hazeColor.
        var hazeGrad = defs.childNodes[0];
        var firstStop = hazeGrad.childNodes[0];
        result = {
            ids: ids,
            tags: tags,
            hazeStopColor: firstStop.getAttribute('stop-color'),
            expectedHaze: p.hazeColor
        };
    """)
    assert result["ids"] == ["haze-grad", "atmosphere-grad"]
    assert result["tags"] == ["radialGradient", "radialGradient"]
    assert result["hazeStopColor"] == result["expectedHaze"]


def test_twin_sun_shadows_returns_null_when_not_applicable() -> None:
    """OV_TwinSunShadows returns null on single-sun palettes OR at night,
    and a populated <g> otherwise. (Catches a regression where the early-return
    guard silently turns into a NodeList of empty <g>s.)"""
    result = run_with_dom(SCRIPTS, """
        var tat = window.M3Palettes.getPalette('tatooine');         // sunCount=2
        var cor = window.M3Palettes.getPalette('coruscant_under');  // sunCount=1
        var ov = window.M3AssetsOverlays.OV_TwinSunShadows;
        var buildings = [{ x: 50, y: 50, r: 10 }, { x: 80, y: 30, r: 8 }];
        var dayTat   = ov({ p: tat, buildings: buildings, time: 'day' });
        var nightTat = ov({ p: tat, buildings: buildings, time: 'night' });
        var dayCor   = ov({ p: cor, buildings: buildings, time: 'day' });
        result = {
            dayTatTag:   dayTat   ? dayTat.tagName   : 'null',
            dayTatKids:  dayTat   ? dayTat.childNodes.length : 0,
            nightTatTag: nightTat ? nightTat.tagName : 'null',
            dayCorTag:   dayCor   ? dayCor.tagName   : 'null'
        };
    """)
    # Tatooine at day → 2 buildings × 2 shadow ellipses = 4 children
    assert result["dayTatTag"] == "g"
    assert result["dayTatKids"] == 4
    # Tatooine at night → null
    assert result["nightTatTag"] == "null"
    # Coruscant (single sun) at day → null
    assert result["dayCorTag"] == "null"


def test_time_of_day_renders_tint_rect_or_null() -> None:
    """OV_TimeOfDay returns null for 'day' and a coloured <rect> otherwise."""
    result = run_with_dom(SCRIPTS, """
        var ov = window.M3AssetsOverlays.OV_TimeOfDay;
        var day   = ov({ time: 'day',   width: 800, height: 600 });
        var dusk  = ov({ time: 'dusk',  width: 800, height: 600 });
        var night = ov({ time: 'night', width: 800, height: 600 });
        result = {
            dayNull:   day === null,
            duskTag:   dusk.tagName,
            duskFill:  dusk.getAttribute('fill'),
            nightFill: night.getAttribute('fill')
        };
    """)
    assert result["dayNull"] is True
    assert result["duskTag"] == "rect"
    assert "rgba(255, 100, 60" in result["duskFill"]
    assert "rgba(20, 20, 60" in result["nightFill"]


def test_sandstorm_streaks_count() -> None:
    """OV_Sandstorm: 1 backing rect + 40 streak lines = 41 children."""
    result = run_with_dom(SCRIPTS, """
        var g = window.M3AssetsOverlays.OV_Sandstorm({ width: 800, height: 600 });
        var rectCount = 0, lineCount = 0;
        for (var i = 0; i < g.childNodes.length; i++) {
            var t = g.childNodes[i].tagName;
            if (t === 'rect') rectCount++;
            if (t === 'line') lineCount++;
        }
        result = { total: g.childNodes.length, rects: rectCount, lines: lineCount,
                   style: g.getAttribute('style') };
    """)
    assert result["rects"] == 1
    assert result["lines"] == 40
    assert result["total"] == 41
    # pointer-events: none must be present for visual-only overlays
    assert "pointer-events" in result["style"]
    assert "none" in result["style"]


def test_neon_halos_only_lights_lit_buildings() -> None:
    """OV_NeonHalos skips buildings without `lit: true`. Halo count must
    match the lit-building count, not the total building count."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('coruscant_under');
        var buildings = [
            { x: 10, y: 10, r: 5, lit: true },
            { x: 30, y: 30, r: 5, lit: false },
            { x: 50, y: 50, r: 5, lit: true },
            { x: 70, y: 70, r: 5 }  // missing lit — falsy
        ];
        var g = window.M3AssetsOverlays.OV_NeonHalos({ p: p, buildings: buildings });
        result = { halos: g.childNodes.length };
    """)
    assert result["halos"] == 2  # only buildings[0] and buildings[2] are lit


def test_contest_banner_renders_label_and_score() -> None:
    """OV_ContestBanner emits a translated group with the contest label
    and score in two <text> elements (per architecture v50 §6.10/§7.13.5)."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsOverlays.OV_ContestBanner({
            p: p, x: 100, y: 80, label: 'KRAYT DRAGON', score: '3 / 5'
        });
        var transform = g.getAttribute('transform');
        var texts = [];
        for (var i = 0; i < g.childNodes.length; i++) {
            if (g.childNodes[i].tagName === 'text') {
                texts.push(g.childNodes[i].textContent);
            }
        }
        result = { transform: transform, texts: texts };
    """)
    assert result["transform"] == "translate(100 80)"
    assert len(result["texts"]) == 2
    # First text is the contest label with warning glyph + dot separator.
    assert "KRAYT DRAGON" in result["texts"][0]
    assert "CONTEST" in result["texts"][0]
    # Second text is the score, rendered as the string we passed in.
    assert result["texts"][1] == "3 / 5"
