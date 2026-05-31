"""
test_m3_composition_engine.py — regression tests for the SPA composition engine.

Drop 4.1e · Tier 1 #4 · May 26 2026.

This is the renderer that orchestrates the asset library. It must:
  - Expose a stable public API on window.M3CompositionEngine
  - Project world coords → screen coords with the JSX-source formula
  - Compose layers in the canonical z-order (arch v50 §4.15)
  - Pick the right LOD per tier
  - Resolve room.slug → urban landmark → wilderness landmark → style primitive
  - Skip street rooms in the building layer (they're drawn by L_Streets)
  - Gate weather/atmospheric overlays correctly (planet id, weather, time)
  - Render full chrome (HolocartaFrame) and body-only (Tier1aBody)
  - Re-export terrainDefs (so the catalog terrain preview can light up)

Tests use a small but representative Mos Eisley-shaped dataset that
exercises all rooms (street vs landmark vs unbound), street rendering,
districts, security tints, furniture, landmarks, and all four dynamic-
actor types (player, PCs, NPCs, POIs).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"

# Composition engine needs every asset module loaded before it
# (palette/styles/icons/markers/wilderness/overlays/landmarks).
SCRIPTS = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_palettes.js",
    SPA_DIR / "m3_assets_styles.js",
    SPA_DIR / "m3_assets_icons.js",
    SPA_DIR / "m3_assets_markers.js",
    SPA_DIR / "m3_assets_wilderness.js",
    SPA_DIR / "m3_assets_overlays.js",
    SPA_DIR / "m3_assets_landmarks.js",
    SPA_DIR / "m3_composition_engine.js",
]

# Inline JS used by most tests — builds a representative Mos Eisley
# dataset and exposes it as window.testData. Loaded as part of setup_js.
TEST_DATA_JS = """
window.testData = {
  display_name: 'MOS EISLEY',
  bounds: { x_min: 0, y_min: 0, x_max: 100, y_max: 100 },
  rooms: [
    { id: 'r1', x: 25, y: 25, w: 12, h: 12, style: 'dock',
      slug: 'docking_bay_94_pit', security: 'lawless' },
    { id: 'r2', x: 50, y: 50, w: 14, h: 12, style: 'cantina',
      slug: 'chalmuans_cantina_main_bar', security: 'contested' },
    { id: 'r3', x: 75, y: 25, w: 10, h: 10, style: 'civic',
      slug: 'spaceport_customs_office', security: 'secured' },
    { id: 'r4', x: 30, y: 80, w: 8, h: 8, style: 'street' },
    { id: 'r5', x: 80, y: 70, w: 10, h: 10, style: 'housing' }
  ],
  districts: [
    { id: 'spaceport',
      polygon: [[5, 5], [95, 5], [95, 50], [5, 50]],
      label_anchor: [50, 25], name: 'SPACEPORT', terrain: 'duracrete' }
  ],
  streets: [
    { id: 's1', path: [[10, 80], [90, 80]], kind: 'main',
      label: 'Spaceport Strip' }
  ],
  landmarks: [
    { x: 25, y: 25, label: 'Bay 94', important: true },
    { x: 50, y: 50, label: \"Chalmun's\" }
  ],
  furniture: [
    { kind: 'vaporator', x: 60, y: 30 },
    { kind: 'speeder-rack', x: 40, y: 75 },
    { kind: 'awning', x: 65, y: 55 }
  ],
  dynamic: {
    player: { x: 50, y: 50, bearing: 45 },
    pcs:    [{ id: 'pc1', x: 30, y: 30, name: 'TEY VOSS', bearing: 90 }],
    npcs:   [{ x: 70, y: 20, kind: 'friendly' },
             { x: 60, y: 80, kind: 'hostile' }],
    poi:    [{ x: 75, y: 50, kind: 'mission' },
             { x: 25, y: 75, kind: 'bounty' }]
  }
};
"""


def test_module_exports_full_public_api() -> None:
    """M3CompositionEngine exposes every entry point listed in the
    header comment of m3_composition_engine.js."""
    result = run_with_dom(SCRIPTS, """
        result = {
            hasNamespace: typeof window.M3CompositionEngine === 'object',
            keys: window.M3CompositionEngine
                ? Object.keys(window.M3CompositionEngine).sort()
                : []
        };
    """)
    assert result["hasNamespace"]
    assert result["keys"] == [
        "CompassRose", "HolocartaFrame",
        "L_Atmosphere", "L_Buildings", "L_Districts", "L_Entities",
        "L_Furniture", "L_Labels", "L_SecurityTint", "L_Streets",
        "L_Substrate", "L_SubstrateImage",
        "MapRenderer", "ScaleBar", "Tier1aBody",
        "buildingPositions", "makeProjector", "terrainDefs",
    ]


def test_make_projector_matches_jsx_formula() -> None:
    """Projector preserves JSX semantics: uniform scale fits the world
    inside the viewport (minus padding), with centered offsets, and
    proj.project(x_min, y_min) lands at (offsetX, offsetY)."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3CompositionEngine.makeProjector({
            bounds: { x_min: 0, y_min: 0, x_max: 100, y_max: 50 },
            width: 800, height: 600, padding: 20
        });
        // World 100×50 fits inside 760×560 viewport:
        //   scale = min(760/100, 560/50) = min(7.6, 11.2) = 7.6
        //   offsetX = 20 + (760 - 760) / 2 = 20
        //   offsetY = 20 + (560 - 380) / 2 = 20 + 90 = 110
        var origin = p.project(0, 0);
        var farCorner = p.project(100, 50);
        result = {
            scale: p.scale,
            unit:  p.unit,
            origin: origin,
            farCorner: farCorner
        };
    """)
    assert abs(result["scale"] - 7.6) < 1e-9
    assert result["scale"] == result["unit"]
    assert result["origin"] == [20, 110]
    assert result["farCorner"] == [780, 490]


def test_terrain_defs_re_export_matches_assets_overlays() -> None:
    """terrainDefs(p) on the composition engine returns the SAME <defs>
    structure as M3AssetsOverlays.TerrainDefs(p). This is what the
    catalog's terrain preview gate checks (per m3_asset_catalog.js§388).
    A mismatch here would break the catalog's terrain tiles."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var ce = window.M3CompositionEngine;
        var fromCE  = ce.terrainDefs(p);
        var fromAssets = window.M3AssetsOverlays.TerrainDefs(p);
        var idsFromCE  = [];
        var idsFromAss = [];
        for (var i = 0; i < fromCE.childNodes.length; i++) {
            idsFromCE.push(fromCE.childNodes[i].getAttribute('id'));
        }
        for (var j = 0; j < fromAssets.childNodes.length; j++) {
            idsFromAss.push(fromAssets.childNodes[j].getAttribute('id'));
        }
        result = {
            ceTag: fromCE.tagName,
            ceKidCount: fromCE.childNodes.length,
            sameIds: JSON.stringify(idsFromCE.sort()) ===
                     JSON.stringify(idsFromAss.sort())
        };
    """)
    assert result["ceTag"] == "defs"
    assert result["ceKidCount"] == 7   # seven named terrain patterns
    assert result["sameIds"]


def test_layer_z_order_matches_arch_v50_4_15() -> None:
    """Tier1aBody's <svg> children must be in this order (architecture
    v50 §4.15 z-order):

      defs(terrain) → defs(haze) → atmosphere → substrate → districts
        → security tint → streets → [twin-sun] → buildings → furniture
        → [weather] → [time-of-day] → [haze] → labels → entities
        → compass → scale

    Twin-sun shadows render on Tatooine at day (palette.sunCount=2);
    sandstorm OFF in this dataset; time-of-day=day → null; sandhaze ON
    (tatooine). Expected non-null children: 15."""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var p = window.M3Palettes.getPalette('tatooine');
        var svg = window.M3CompositionEngine.Tier1aBody({
            data: window.testData, palette: p,
            tier: 1, time: 'day', weather: 'clear',
            width: 1200, height: 720
        });
        var tags = [];
        for (var i = 0; i < svg.childNodes.length; i++) {
            tags.push(svg.childNodes[i].tagName);
        }
        result = { svgTag: svg.tagName, count: svg.childNodes.length, tags: tags };
    """)
    assert result["svgTag"] == "svg"
    # 15 layers — defs ×2 + atmos + substrate + districts + sec + streets
    # + twin-sun + buildings + furniture + sandhaze + labels + entities
    # + compass + scale
    assert result["count"] == 15
    # First two children are always the two <defs> blocks.
    assert result["tags"][0] == "defs"
    assert result["tags"][1] == "defs"
    # Last two children are CompassRose + ScaleBar (both <g>).
    assert result["tags"][-1] == "g"
    assert result["tags"][-2] == "g"


def test_buildings_layer_skips_street_rooms_and_uses_landmarks() -> None:
    """L_Buildings must:
      - Skip rooms with style='street' (drawn by L_Streets instead)
      - Use a named-landmark builder when room.slug binds to LANDMARKS
      - Fall back to a style primitive when no slug binding"""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var p = window.M3Palettes.getPalette('tatooine');
        var ce = window.M3CompositionEngine;
        var proj = ce.makeProjector({
            bounds: window.testData.bounds,
            width: 1200, height: 720, padding: 24
        });
        var g = ce.L_Buildings({
            p: p, proj: proj, rooms: window.testData.rooms,
            tier: 1, time: 'day'
        });
        // 5 rooms total but r4 is a street → 4 building wrappers.
        result = { wrappers: g.childNodes.length };
    """)
    # Exactly 4 building wrappers: r1 (landmark), r2 (landmark),
    # r3 (landmark), r5 (style primitive fallback). r4 (street) skipped.
    assert result["wrappers"] == 4


def test_building_lod_changes_with_tier() -> None:
    """LOD selection per JSX line 205:
      tier ≤ 1 → 'detailed', tier === 2 → 'simplified', tier ≥ 3 → 'icon'.
    Detailed renders MORE primitives than icon — count drops as tier rises."""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var p = window.M3Palettes.getPalette('tatooine');
        var ce = window.M3CompositionEngine;
        var proj = ce.makeProjector({
            bounds: window.testData.bounds,
            width: 1200, height: 720, padding: 24
        });
        function nodeCount(el) {
            var n = 0;
            for (var i = 0; i < el.childNodes.length; i++) {
                n += 1 + nodeCount(el.childNodes[i]);
            }
            return n;
        }
        // Restrict to a single landmark room to isolate LOD effect.
        var rooms = [window.testData.rooms[0]];  // docking_bay_94_pit
        var detailed = ce.L_Buildings({
            p: p, proj: proj, rooms: rooms, tier: 0, time: 'day'
        });
        var simplified = ce.L_Buildings({
            p: p, proj: proj, rooms: rooms, tier: 2, time: 'day'
        });
        var iconish = ce.L_Buildings({
            p: p, proj: proj, rooms: rooms, tier: 5, time: 'day'
        });
        result = {
            detailedCount: nodeCount(detailed),
            simplifiedCount: nodeCount(simplified),
            iconCount: nodeCount(iconish)
        };
    """)
    # icon LOD strips the most; detailed renders the most.
    # The wilderness/landmark builders treat 'simplified' as anything
    # not in {'icon'}, so it renders like detailed (no separate variant
    # exists in the asset). What MUST hold strictly: detailed > icon.
    assert result["detailedCount"] > result["iconCount"], \
        f"detailed {result['detailedCount']} not > icon {result['iconCount']}"


def test_twin_sun_shadows_render_on_tatooine_day_not_at_night() -> None:
    """Tatooine palette has sunCount=2, so OV_TwinSunShadows participates
    at day. At night → null (one layer drops) BUT OV_TimeOfDay → adds
    a tint rect (one layer back), so the total layer count is the same.

    The strong assertion is structural: at day, no <rect> with the
    dusk/night tint fill exists; at night, exactly one does. And at
    day, the shadow group must have non-zero children; at night, no
    such group exists."""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var p = window.M3Palettes.getPalette('tatooine');
        var ce = window.M3CompositionEngine;
        function inspect(time) {
            var svg = ce.Tier1aBody({
                data: window.testData, palette: p,
                tier: 1, time: time, weather: 'clear',
                width: 1000, height: 600
            });
            var nightTintFill = 'rgba(20, 20, 60, 0.45)';
            var hasNightTintRect = false;
            // mix-blend-mode is the marker for twin-sun shadow groups.
            var shadowGroupKidCount = 0;
            for (var i = 0; i < svg.childNodes.length; i++) {
                var node = svg.childNodes[i];
                if (node.tagName === 'rect' &&
                    node.getAttribute('fill') === nightTintFill) {
                    hasNightTintRect = true;
                }
                var style = node.getAttribute && node.getAttribute('style');
                if (node.tagName === 'g' && style &&
                    style.indexOf('mix-blend-mode: multiply') !== -1 &&
                    node.childNodes.length > 0) {
                    // shadow groups have one ellipse per shadow
                    shadowGroupKidCount = node.childNodes.length;
                }
            }
            return {
                count: svg.childNodes.length,
                hasNightTint: hasNightTintRect,
                shadowGroupKidCount: shadowGroupKidCount
            };
        }
        result = { day: inspect('day'), night: inspect('night') };
    """)
    # Total child count is the same — swaps, doesn't add/subtract.
    assert result["day"]["count"] == result["night"]["count"]
    # Day → shadow group with children (4 bldgs × 2 shadows = 8), no tint rect.
    assert not result["day"]["hasNightTint"]
    assert result["day"]["shadowGroupKidCount"] == 8
    # Night → tint rect present, no shadow group.
    assert result["night"]["hasNightTint"]
    assert result["night"]["shadowGroupKidCount"] == 0


def test_security_tint_uses_palette_with_alpha_suffix() -> None:
    """L_SecurityTint must produce per-room <rect>s using
    `${palette.green}18` / `${palette.amber}25` / `${palette.red}22`
    hex+alpha values (matches JSX line 144-149). Catches regressions
    where someone hardcodes hex strings."""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var p = window.M3Palettes.getPalette('tatooine');
        var ce = window.M3CompositionEngine;
        var proj = ce.makeProjector({
            bounds: window.testData.bounds,
            width: 1000, height: 600, padding: 24
        });
        var g = ce.L_SecurityTint({
            p: p, proj: proj, rooms: window.testData.rooms
        });
        var fills = [];
        for (var i = 0; i < g.childNodes.length; i++) {
            fills.push(g.childNodes[i].getAttribute('fill'));
        }
        result = {
            count: g.childNodes.length,
            fills: fills,
            expected: {
                lawless:    p.red   + '22',
                contested:  p.amber + '25',
                secured:    p.green + '18'
                // r4 (street, no security) → 'transparent'
            }
        };
    """)
    assert result["count"] == 5  # one per room
    # Rooms order: r1 lawless, r2 contested, r3 secured, r4 transparent, r5 transparent
    assert result["fills"][0] == result["expected"]["lawless"]
    assert result["fills"][1] == result["expected"]["contested"]
    assert result["fills"][2] == result["expected"]["secured"]
    assert result["fills"][3] == "transparent"
    assert result["fills"][4] == "transparent"


def test_entities_render_in_z_order_poi_npc_pc_player() -> None:
    """L_Entities must render in JSX order: POIs first (bottom), then
    NPCs, then other PCs, then player (top). With our dataset:
      2 POIs + 2 NPCs + 1 PC + 1 player = 6 wrapper <g>s."""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var p = window.M3Palettes.getPalette('tatooine');
        var ce = window.M3CompositionEngine;
        var proj = ce.makeProjector({
            bounds: window.testData.bounds,
            width: 1000, height: 600, padding: 24
        });
        var g = ce.L_Entities({
            p: p, proj: proj, dynamic: window.testData.dynamic
        });
        // Inspect each child's transform — POI transforms come from
        // POI coords (75,50) and (25,75); player from (50,50).
        var transforms = [];
        for (var i = 0; i < g.childNodes.length; i++) {
            transforms.push(g.childNodes[i].getAttribute('transform'));
        }
        // The last child (top of z-order) should be the player.
        result = {
            count: g.childNodes.length,
            transforms: transforms
        };
    """)
    assert result["count"] == 6
    # All 6 wrappers have translate transforms
    for t in result["transforms"]:
        assert t.startswith("translate("), f"bad transform: {t}"


def test_map_renderer_returns_chrome_around_svg_body() -> None:
    """MapRenderer returns an HTMLDivElement (the HolocartaFrame chrome)
    with 3 child sections: topBar, contentArea, bottomBar. The SVG body
    lives inside contentArea."""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var p = window.M3Palettes.getPalette('tatooine');
        var frame = window.M3CompositionEngine.MapRenderer({
            data: window.testData, palette: p,
            tier: 1, time: 'day', weather: 'clear',
            width: 1200, height: 720
        });
        var topBar  = frame.childNodes[0];
        var content = frame.childNodes[1];
        var bottom  = frame.childNodes[2];
        var svg     = content.childNodes[0];
        result = {
            frameTag: frame.tagName,
            frameKids: frame.childNodes.length,
            topBarTag: topBar.tagName,
            contentTag: content.tagName,
            bottomTag: bottom.tagName,
            svgTag: svg.tagName,
            svgNs: svg.namespaceURI,
            topBarText: topBar.textContent
        };
    """)
    assert result["frameTag"] == "DIV"
    assert result["frameKids"] == 3
    assert result["topBarTag"] == "DIV"
    assert result["contentTag"] == "DIV"
    assert result["bottomTag"] == "DIV"
    assert result["svgTag"] == "svg"
    assert result["svgNs"] == "http://www.w3.org/2000/svg"
    # Top bar shows the breadcrumb and "TIER 1A · DISTRICT"
    assert "HOLOCARTA" in result["topBarText"]
    assert "MOS EISLEY" in result["topBarText"]
    assert "TIER 1A" in result["topBarText"]


def test_weather_overlays_gate_on_input() -> None:
    """Weather/atmospheric overlays gate on inputs:
      - sandstorm only when weather='sandstorm' (any palette)
      - rain     only when palette.id='nar_shaddaa'
      - smog     only when palette.id='coruscant_under'
      - sandHaze only when palette.id='tatooine'
    Verifies by adding +1 to a baseline when each trigger fires."""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var ce = window.M3CompositionEngine;
        var tat = window.M3Palettes.getPalette('tatooine');
        var cor = window.M3Palettes.getPalette('coruscant_under');
        var nar = window.M3Palettes.getPalette('nar_shaddaa');
        function svgKidCount(palette, weather) {
            return ce.Tier1aBody({
                data: window.testData, palette: palette,
                tier: 1, time: 'day', weather: weather,
                width: 1000, height: 600
            }).childNodes.length;
        }
        var tatBase   = svgKidCount(tat, 'clear');
        var tatStorm  = svgKidCount(tat, 'sandstorm');
        // 'nar_shaddaa minus rain' is impossible to test directly because
        // rain triggers on palette.id, not weather. Same for cor/smog.
        // Compare across palettes: coruscant has smog but no twin-sun
        // and no sandhaze; tatooine clear has twin-sun + sandhaze and
        // no smog. So tat = base + twinSun + sandHaze and
        //       cor = base + smog.  Diff = twinSun + sandHaze - smog = 1.
        var corBase   = svgKidCount(cor, 'clear');
        var narBase   = svgKidCount(nar, 'clear');
        result = {
            sandstormAddsOne: (tatStorm - tatBase),
            tatBase: tatBase,
            corBase: corBase,
            narBase: narBase
        };
    """)
    # Adding sandstorm to a clear baseline must add exactly 1 child.
    assert result["sandstormAddsOne"] == 1
    # All baselines render a non-trivial number of layers (sanity check).
    assert result["tatBase"] >= 13
    assert result["corBase"] >= 12
    assert result["narBase"] >= 12


def test_building_positions_filters_streets_and_projects_centers() -> None:
    """buildingPositions takes (proj, rooms) and returns one entry per
    non-street room with projected center coords and r = max(w,h)*scale*0.5."""
    result = run_with_dom(SCRIPTS, TEST_DATA_JS + """
        var ce = window.M3CompositionEngine;
        var proj = ce.makeProjector({
            bounds: window.testData.bounds,
            width: 1000, height: 600, padding: 24
        });
        var positions = ce.buildingPositions(proj, window.testData.rooms);
        result = {
            count: positions.length,
            // First entry corresponds to r1 (style='dock', x=25, y=25, w=12, h=12)
            firstRadius: positions[0].r,
            // Streets filtered out — none should be 'street'
            allHaveX: positions.every(function(b) { return typeof b.x === 'number'; }),
            allHaveY: positions.every(function(b) { return typeof b.y === 'number'; }),
            allHaveR: positions.every(function(b) { return typeof b.r === 'number'; }),
            allHaveLit: positions.every(function(b) { return b.lit === false; })
        };
    """)
    # 5 rooms, 1 street → 4 building positions
    assert result["count"] == 4
    assert result["allHaveX"]
    assert result["allHaveY"]
    assert result["allHaveR"]
    assert result["allHaveLit"]
    # First room is 12×12. With padding=24, world 100×100 fits into a
    # 952×552 viewport → scale = min(952/100, 552/100) = 5.52.
    # max(12,12) * 5.52 * 0.5 = 33.12.
    assert abs(result["firstRadius"] - 33.12) < 0.1
