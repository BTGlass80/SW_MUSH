"""
test_m3_asset_catalog_after_41d.py — catalog integration tests for Drop 4.1d.

Drop 4.1d · Tier 1 #4 · May 26 2026.

Complement to test_m3_asset_catalog_after_41c.py: with all 4.1a/b/c/d
modules loaded, the catalog's urban landmark cards must now render real
SVG (not the 'loading…' stubs they showed in 4.1c). The 4.1c namespace-
fallback chain in buildLandmarksColumn is what makes that happen — the
catalog passes 'LM_DockingBay94' (long ident) and falls back to the
M3AssetsLandmarks namespace export when the short-slug dict misses.

Header count goes UP from "6 LANDMARKS" (4.1c — wilderness only) to
"18 LANDMARKS" (4.1d — 12 urban slugs + 6 wilderness). The 18 reflects
the registry size, not the displayed-card count: the catalog's entries
array displays 9 urban + 6 wilderness = 15 cards. Two urban slugs are
aliases (docking_bay_94_pit / _entrance both map to LM_DockingBay94;
lucky_despot_staircase / _star_chamber both map to LM_LuckyDespot), and
one builder (LM_SpeederLot, slug spaceport_speeders) is in the registry
for engine-side composition but not in the catalog's preview list.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"

# Full 4.1a + 4.1b + 4.1c + 4.1d module set.
SCRIPTS_41ABCD = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_palettes.js",
    SPA_DIR / "m3_assets_styles.js",
    SPA_DIR / "m3_assets_icons.js",
    SPA_DIR / "m3_assets_markers.js",
    SPA_DIR / "m3_assets_wilderness.js",
    SPA_DIR / "m3_assets_overlays.js",
    # 4.1d addition:
    SPA_DIR / "m3_assets_landmarks.js",
    # catalog goes last so it sees all the above
    SPA_DIR / "m3_asset_catalog.js",
]


def test_header_counts_rise_after_41d_modules_load() -> None:
    """With 4.1d loaded, header shows LANDMARKS=18 (12 urban + 6 wilderness)."""
    result = run_with_dom(SCRIPTS_41ABCD, """
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
    # Order in the header: LANDMARKS, STYLES, MARKERS, ICONS.
    # LANDMARKS = 18 (12 urban + 6 wilderness — slug-registry size).
    assert "18 LANDMARKS" in result["counts"][0]
    assert "12 STYLES" in result["counts"][1]
    assert "10 MARKERS" in result["counts"][2]
    assert "28 ICONS" in result["counts"][3]


def test_urban_landmark_cards_render_real_builders() -> None:
    """All 9 urban landmark cards in the catalog now render real SVG
    (not 'loading…' stubs) via the namespace-fallback chain established
    in 4.1c. The 6 wilderness cards also stay rendered (regression check
    on the 4.1c integration)."""
    result = run_with_dom(SCRIPTS_41ABCD, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var landmarksColumn = grid.childNodes[0];
        var body = landmarksColumn.childNodes[1];
        var landmarksGrid = body.childNodes[0];

        // The catalog entries list has 15 cards: indices 0-8 urban,
        // 9-14 wilderness. Walk all 15 and verify none are loading stubs.
        var cards = [];
        for (var i = 0; i < landmarksGrid.childNodes.length; i++) {
            var card = landmarksGrid.childNodes[i];
            var svg = card.childNodes[0];
            var stubText = svg.querySelector('text');
            var isStub = stubText && stubText.textContent === 'loading…';
            cards.push({
                index: i,
                label: card.querySelector('div').textContent,
                isLoadingStub: isStub,
                svgChildCount: svg.childNodes.length
            });
        }
        result = { cards: cards, total: cards.length };
    """)
    assert result["total"] == 15
    for entry in result["cards"]:
        assert not entry["isLoadingStub"], \
            f"Card {entry['index']} '{entry['label']}' still showing loading stub"
        # Real builders produce SVG with several child nodes.
        assert entry["svgChildCount"] > 1, \
            f"Card {entry['index']} '{entry['label']}' suspiciously empty"


def test_urban_card_labels_match_catalog_entries() -> None:
    """The 9 urban card labels are the human-readable names from the
    catalog's entries array (4.1b §211-219). Verifies the integration
    is exposing the correct cards, not some other set."""
    result = run_with_dom(SCRIPTS_41ABCD, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var landmarksColumn = grid.childNodes[0];
        var body = landmarksColumn.childNodes[1];
        var landmarksGrid = body.childNodes[0];
        var labels = [];
        // Just the first 9 — the urban entries.
        for (var i = 0; i < 9; i++) {
            labels.push(landmarksGrid.childNodes[i].querySelector('div').textContent);
        }
        result = { labels: labels };
    """)
    assert result["labels"] == [
        "Docking Bay 94",
        "Chalmun's",
        "Lucky Despot",
        "Control Tower",
        "Customs",
        "Mos Eisley Inn",
        "Spaceport Hotel",
        "House of M.N.",
        "Transport",
    ]


def test_terrain_tiles_still_stub_after_41d() -> None:
    """Terrain tiles remain '(loading)' until 4.1e composition-engine
    lands. Locks the gating: 4.1d adding LANDMARKS doesn't accidentally
    affect terrain (which goes via composition-engine, not assets)."""
    result = run_with_dom(SCRIPTS_41ABCD, """
        var root = window.document.createElement('div');
        window.M3AssetCatalog.mount(root, {
            palette: window.M3Palettes.getPalette('tatooine')
        });
        var container = root.childNodes[0];
        var grid = container.childNodes[1];
        var supportColumn = grid.childNodes[3];
        var supportBody = supportColumn.childNodes[1];
        var wrapper = supportBody.childNodes[0];
        var terrainSection = wrapper.childNodes[3];
        var tileGrid = terrainSection.childNodes[1];
        var firstTile = tileGrid.childNodes[0];
        var inner = firstTile.childNodes[0];
        result = { innerTag: inner.tagName, innerText: inner.textContent };
    """)
    assert result["innerTag"] == "DIV"
    assert "loading" in result["innerText"].lower()
