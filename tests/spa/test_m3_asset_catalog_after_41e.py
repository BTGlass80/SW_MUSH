"""
test_m3_asset_catalog_after_41e.py — catalog integration tests for Drop 4.1e.

Drop 4.1e · Tier 1 #4 · May 26 2026.

Complement to test_m3_asset_catalog_after_41{c,d}.py: with the composition
engine loaded, the catalog's terrain-tile preview must FINALLY render real
SVG terrain (not '(loading)' stubs). The catalog gate is:

  if (window.M3CompositionEngine && window.M3CompositionEngine.terrainDefs) {
    // render real terrain tile
  } else {
    // show '(loading)' stub
  }

This was the last graceful-degradation hold from 4.1b. After 4.1e, the
catalog is fully populated — no more loading stubs anywhere.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"

# Full 4.1a + 4.1b + 4.1c + 4.1d + 4.1e module set.
SCRIPTS_41ABCDE = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_palettes.js",
    SPA_DIR / "m3_assets_styles.js",
    SPA_DIR / "m3_assets_icons.js",
    SPA_DIR / "m3_assets_markers.js",
    SPA_DIR / "m3_assets_wilderness.js",
    SPA_DIR / "m3_assets_overlays.js",
    SPA_DIR / "m3_assets_landmarks.js",
    # 4.1e addition:
    SPA_DIR / "m3_composition_engine.js",
    # catalog goes last
    SPA_DIR / "m3_asset_catalog.js",
]


def test_terrain_tile_preview_lights_up_after_41e() -> None:
    """After 4.1e, the terrain section of the support column shows real
    SVG (not '(loading)'). Locks the final gate: now that M3CompositionEngine
    exposes terrainDefs, the catalog should render the previews."""
    result = run_with_dom(SCRIPTS_41ABCDE, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var supportColumn = grid.childNodes[3];
        var supportBody = supportColumn.childNodes[1];
        var wrapper = supportBody.childNodes[0];
        // Section index 3 = terrain (services / mixed / palettes / terrain)
        var terrainSection = wrapper.childNodes[3];
        var tileGrid = terrainSection.childNodes[1];

        // Walk all 6 terrain tiles. Each tile's first child must be
        // <svg> (real preview), not <div> (loading stub).
        var tiles = [];
        for (var i = 0; i < tileGrid.childNodes.length; i++) {
            var tile = tileGrid.childNodes[i];
            var inner = tile.childNodes[0];
            tiles.push({
                tileIdx: i,
                innerTag: inner.tagName,
                isStub: inner.tagName === 'DIV'
            });
        }
        result = { tiles: tiles, count: tiles.length };
    """)
    assert result["count"] == 6  # city, dune, duracrete, scrub, canyon, vapor
    for tile in result["tiles"]:
        assert not tile["isStub"], \
            f"Terrain tile {tile['tileIdx']} still showing loading stub " \
            f"(inner tag = {tile['innerTag']}); expected <svg>."
        assert tile["innerTag"] == "svg", \
            f"Terrain tile {tile['tileIdx']} unexpected tag: {tile['innerTag']}"


def test_header_counts_unchanged_by_41e() -> None:
    """4.1e adds the composition engine but no NEW raw assets, so the
    header counts must NOT change from their 4.1d values. Specifically:
    18 LANDMARKS · 12 STYLES · 10 MARKERS · 28 ICONS. (If composition
    engine accidentally registered itself as something countable, this
    would catch it.)"""
    result = run_with_dom(SCRIPTS_41ABCDE, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var header = container.childNodes[0];
        var countsSide = header.childNodes[1];
        var counts = [];
        for (var i = 0; i < countsSide.childNodes.length; i++) {
            counts.push(countsSide.childNodes[i].textContent);
        }
        result = { counts: counts };
    """)
    assert "18 LANDMARKS" in result["counts"][0]
    assert "12 STYLES" in result["counts"][1]
    assert "10 MARKERS" in result["counts"][2]
    assert "28 ICONS" in result["counts"][3]


def test_full_catalog_has_zero_loading_stubs_after_41e() -> None:
    """Final regression sweep: walk EVERY catalog tile and confirm
    NONE show 'loading…' text. 4.1e is the final asset-substrate drop
    and the catalog should be fully populated."""
    result = run_with_dom(SCRIPTS_41ABCDE, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        // Search the entire rendered tree for any text node whose
        // content is exactly 'loading…' (the catalog stub string).
        function walk(node, stubs) {
            if (!node) return;
            if (node.nodeType === 3 /*TEXT_NODE*/) {
                if (node.textContent === 'loading…') stubs.push(node);
                return;
            }
            for (var i = 0; i < node.childNodes.length; i++) {
                walk(node.childNodes[i], stubs);
            }
        }
        var stubs = [];
        walk(root, stubs);
        result = { stubCount: stubs.length };
    """)
    assert result["stubCount"] == 0, \
        f"Expected zero 'loading…' stubs after 4.1e but found {result['stubCount']}"
