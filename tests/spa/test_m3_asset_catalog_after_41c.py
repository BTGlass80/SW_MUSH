"""
test_m3_asset_catalog_after_41c.py — catalog integration tests for Drop 4.1c.

Drop 4.1c · Tier 1 #4 · May 26 2026.

The 4.1b catalog was designed to gracefully degrade when MARKERS,
WILDERNESS_LANDMARKS, and LANDMARKS aren't loaded yet (see
test_m3_asset_catalog.py::test_landmarks_column_shows_loading_stubs).

This file is the complement: it loads the 4.1c modules alongside the
4.1a/b set and verifies the catalog lights up the wilderness and
markers columns, with the header counts rising to reflect the loaded
modules. Terrain tiles are NOT exercised here — they stay '(loading)'
until 4.1e composition-engine because the catalog gates terrain on
window.M3CompositionEngine, not on this module directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"

# Full 4.1a + 4.1b + 4.1c module set.
SCRIPTS_41ABC = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_palettes.js",
    SPA_DIR / "m3_assets_styles.js",
    SPA_DIR / "m3_assets_icons.js",
    # 4.1c additions:
    SPA_DIR / "m3_assets_markers.js",
    SPA_DIR / "m3_assets_wilderness.js",
    SPA_DIR / "m3_assets_overlays.js",
    # catalog goes last so it sees all the above
    SPA_DIR / "m3_asset_catalog.js",
]


def test_header_counts_rise_after_41c_modules_load() -> None:
    """With 4.1c loaded, header shows LANDMARKS=6, MARKERS=10."""
    result = run_with_dom(SCRIPTS_41ABC, """
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
    # Order: LANDMARKS, STYLES, MARKERS, ICONS
    # LANDMARKS = 6 (just wilderness — urban landmarks still wait for 4.1d).
    # MARKERS = 10 (all of them — that's the full set this drop provides).
    assert "6 LANDMARKS" in result["counts"][0]
    assert "12 STYLES" in result["counts"][1]
    assert "10 MARKERS" in result["counts"][2]
    assert "28 ICONS" in result["counts"][3]


def test_wilderness_landmark_cards_render_real_builders() -> None:
    """The 6 wilderness landmark cards in the catalog now render real
    SVG (not 'loading…' stubs) because M3AssetsWilderness is loaded."""
    result = run_with_dom(SCRIPTS_41ABC, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var landmarksColumn = grid.childNodes[0];
        var body = landmarksColumn.childNodes[1];
        var landmarksGrid = body.childNodes[0];

        // The catalog entries list has 15 cards: indices 0-8 are urban
        // (LM_*, not yet ported) and 9-14 are wilderness (WLM_*, this drop).
        var wildernessSlice = [];
        for (var i = 9; i < 15; i++) {
            var card = landmarksGrid.childNodes[i];
            var svg = card.childNodes[0];
            // A loading stub has a single <text> with content 'loading…';
            // a real builder produces SVG with much richer structure.
            var stubText = svg.querySelector('text');
            wildernessSlice.push({
                label: card.querySelector('div').textContent,
                isLoadingStub: stubText && stubText.textContent === 'loading…',
                svgChildCount: svg.childNodes.length
            });
        }
        // Sanity-check the urban slice is still 'loading…' (4.1d not landed).
        var urbanCard0 = landmarksGrid.childNodes[0];
        var urbanSvg0 = urbanCard0.childNodes[0];
        var urbanText0 = urbanSvg0.querySelector('text');

        result = {
            wildernessSlice: wildernessSlice,
            urbanStillLoading: urbanText0 && urbanText0.textContent === 'loading…'
        };
    """)
    # No wilderness card should still be a loading stub.
    for entry in result["wildernessSlice"]:
        assert not entry["isLoadingStub"], \
            f"Wilderness card '{entry['label']}' still showing loading stub"
        # Real builders produce SVG with several child nodes.
        assert entry["svgChildCount"] > 1, \
            f"Wilderness card '{entry['label']}' suspiciously empty " \
            f"(svgChildCount={entry['svgChildCount']})"
    # Urban landmarks not yet ported — should still stub.
    assert result["urbanStillLoading"], \
        "Urban LM_* cards should still show loading stub until 4.1d"


def test_markers_column_shows_real_marker_tiles() -> None:
    """With markers loaded, the MARKERS column shows real SVG previews."""
    result = run_with_dom(SCRIPTS_41ABC, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var markersColumn = grid.childNodes[2];
        var body = markersColumn.childNodes[1];
        var markersGrid = body.childNodes[0];

        // Catalog markers column has 12 entries (player, pc, 3 npc kinds,
        // vendor, mission, bounty, objective, 3 anomaly tiers).
        var tiles = [];
        for (var i = 0; i < markersGrid.childNodes.length; i++) {
            var card = markersGrid.childNodes[i];
            var svg = card.childNodes[0];
            var stubText = svg.querySelector('text');
            tiles.push({
                label: card.querySelector('div').textContent,
                isLoading: stubText && stubText.textContent === 'loading…'
            });
        }
        result = { tiles: tiles };
    """)
    assert len(result["tiles"]) == 12
    for tile in result["tiles"]:
        assert not tile["isLoading"], \
            f"Marker tile '{tile['label']}' still showing loading stub"


def test_terrain_tiles_still_stub_until_composition_engine_lands() -> None:
    """Terrain tiles are gated on window.M3CompositionEngine, not on
    M3AssetsOverlays directly — so they should still render '(loading)'
    after 4.1c. This locks the gating in place so a future drop can't
    silently let terrain through without going via the composition engine."""
    result = run_with_dom(SCRIPTS_41ABC, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        // Walk the support column to find the terrain tiles section.
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var supportColumn = grid.childNodes[3];
        var supportBody = supportColumn.childNodes[1];
        var wrapper = supportBody.childNodes[0];
        // Section index 3 is terrain (services / mixed / palettes / terrain)
        var terrainSection = wrapper.childNodes[3];
        var tileGrid = terrainSection.childNodes[1];
        var firstTile = tileGrid.childNodes[0];
        // The inner element is a div with text '(loading)' when stubbed.
        var inner = firstTile.childNodes[0];
        result = { innerTag: inner.tagName, innerText: inner.textContent };
    """)
    assert result["innerTag"] == "DIV"  # not an <svg>
    assert "loading" in result["innerText"].lower()
