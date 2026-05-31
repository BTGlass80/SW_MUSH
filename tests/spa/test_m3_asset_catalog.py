"""
test_m3_asset_catalog.py — regression tests for static/spa/m3_asset_catalog.js.

Drop 4.1b · Tier 1 #4 · May 26 2026.

Validates:
  - mount() function exists and returns a container
  - Catalog renders successfully with only the modules from 4.1a + 4.1b
    (graceful degradation when LANDMARKS / MARKERS / WILDERNESS not yet loaded)
  - Counts row reflects what's actually loaded
  - Style primitives and icons appear correctly (those ARE loaded by 4.1b)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"
SCRIPTS_41AB = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_palettes.js",
    SPA_DIR / "m3_assets_styles.js",
    SPA_DIR / "m3_assets_icons.js",
    SPA_DIR / "m3_asset_catalog.js",
]


def test_module_exports_mount() -> None:
    """M3AssetCatalog.mount is exposed as a function."""
    result = run_with_dom(SCRIPTS_41AB, """
        result = {
            type: typeof window.M3AssetCatalog,
            mount: typeof window.M3AssetCatalog.mount
        };
    """)
    assert result["type"] == "object"
    assert result["mount"] == "function"


def test_mount_renders_into_root() -> None:
    """mount(rootEl, opts) clears rootEl and appends a container div."""
    result = run_with_dom(SCRIPTS_41AB, """
        var root = window.document.createElement('div');
        // Pre-populate root to verify mount clears it
        root.appendChild(window.document.createElement('span'));
        var container = window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine'),
            width: 1280, height: 920
        });
        result = {
            rootChildCount: root.childNodes.length,
            rootFirstTag: root.childNodes[0].tagName,
            containerTag: container.tagName,
            containerWidth: container.style.width,
            containerHeight: container.style.height
        };
    """)
    assert result["rootChildCount"] == 1  # just the new container, original span gone
    assert result["rootFirstTag"] == "DIV"
    assert result["containerTag"] == "DIV"
    assert result["containerWidth"] == "1280px"
    assert result["containerHeight"] == "920px"


def test_header_counts_reflect_loaded_modules() -> None:
    """Header right-column shows counts. With only 4.1a+4.1b loaded, landmarks=0, markers=0."""
    result = run_with_dom(SCRIPTS_41AB, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        // The header is the first child of the container; counts side is its second child
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
    # Landmarks: 0 (not loaded yet — 4.1d)
    # Styles:    12 (from 4.1b)
    # Markers:   0 (not loaded yet — 4.1c)
    # Icons:     10 + 5 + 6 + 7 = 28 (all from 4.1b)
    assert "0 LANDMARKS" in result["counts"][0]
    assert "12 STYLES" in result["counts"][1]
    assert "0 MARKERS" in result["counts"][2]
    assert "28 ICONS" in result["counts"][3]


def test_styles_column_renders_twelve_tiles() -> None:
    """The STYLE PRIMITIVES column renders 12 cards (one per primitive)."""
    result = run_with_dom(SCRIPTS_41AB, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        // 4-column grid is the second child of the container
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        // Columns: [landmarks, styles, markers, support]
        var stylesColumn = grid.childNodes[1];
        // Inside the column: [header, body, footer]; body contains the grid of cards
        var body = stylesColumn.childNodes[1];
        var stylesGrid = body.childNodes[0];
        result = { cardCount: stylesGrid.childNodes.length };
    """)
    assert result["cardCount"] == 12


def test_landmarks_column_shows_loading_stubs() -> None:
    """With LANDMARKS not loaded, landmark cards still render (with 'loading…' stub)."""
    result = run_with_dom(SCRIPTS_41AB, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var landmarksColumn = grid.childNodes[0];
        var body = landmarksColumn.childNodes[1];
        var landmarksGrid = body.childNodes[0];
        // First card → its <svg> → looking for the 'loading…' text node
        var firstCard = landmarksGrid.childNodes[0];
        var svg = firstCard.childNodes[0];
        var stubText = svg.querySelector('text');
        result = {
            cardCount: landmarksGrid.childNodes.length,
            stubPresent: !!stubText,
            stubText: stubText ? stubText.textContent : null,
            firstCardLabel: firstCard.querySelector('div').textContent
        };
    """)
    # 15 named landmarks even though none of the builders are loaded yet
    assert result["cardCount"] == 15
    assert result["stubPresent"], "Expected 'loading…' stub when LANDMARKS not loaded"
    assert result["stubText"] == "loading…"
    assert result["firstCardLabel"] == "Docking Bay 94"


def test_support_column_shows_palette_swatches() -> None:
    """The support column renders all 3 palette swatch cards."""
    result = run_with_dom(SCRIPTS_41AB, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var supportColumn = grid.childNodes[3];
        var supportBody = supportColumn.childNodes[1];
        // Inside support column body: a single wrapper div with 4 sections
        var wrapper = supportBody.childNodes[0];
        // Section index 2 = palettes section (services, mixed icons, palettes, terrain)
        var paletteSection = wrapper.childNodes[2];
        // Section structure: [subLabel, divOfSwatches]
        var swatchContainer = paletteSection.childNodes[1];
        // Each swatch card is a div
        result = {
            swatchCount: swatchContainer.childNodes.length
        };
    """)
    assert result["swatchCount"] == 3  # tatooine + coruscant_under + nar_shaddaa


def test_mount_handles_missing_palette() -> None:
    """When no palette is available, mount returns a helpful error message."""
    result = run_with_dom([SPA_DIR / "m3_tokens.js",
                          SPA_DIR / "m3_asset_catalog.js"], """
        // Deliberately skip loading m3_palettes.js
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {});
        result = { text: root.textContent };
    """)
    assert "no palette available" in result["text"].lower()


def test_active_palette_marker() -> None:
    """The palette that matches the active one shows the '● ACTIVE' marker."""
    result = run_with_dom(SCRIPTS_41AB, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('nar_shaddaa')
        });
        var allText = root.textContent;
        result = { hasActiveMarker: allText.indexOf('● ACTIVE') !== -1 };
    """)
    assert result["hasActiveMarker"], "Expected '● ACTIVE' marker for selected palette"
