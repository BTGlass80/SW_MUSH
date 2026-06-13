"""
test_m3_substrate_hybrid.py — hybrid raster-substrate lane (architecture v51).

Covers the two coupled changes shipped together in the substrate
integration drop:

  1. Y-axis reconciliation in m3_adapter.js::fromAreaGeometry — AreaGeometry
     is authored Y-up; the M3 projector maps y straight down, so the adapter
     reflects every emitted y about the bounds' vertical midline. Without
     this the whole map (and any north-up painted substrate) renders
     vertically inverted against the overlays.

  2. L_SubstrateImage + the Tier1aBody mode switch in
     m3_composition_engine.js — when an area carries `substrate_image`, the
     renderer draws the painted PNG at the world bounds and SKIPS the
     procedural substrate/district/security/street/twin-sun/building/
     furniture layers (baked into the painting), while keeping atmosphere,
     weather, labels, entities, and chrome on top.

Harness: jsdom via spa_dom_harness.run_with_dom (skips if node/jsdom absent).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"

# Full asset stack the composition engine depends on (mirror of
# test_m3_composition_engine.py SCRIPTS).
ENGINE_SCRIPTS = [
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

# The adapter declares no load-time dependency on other M3 modules
# (it uses M3Adapter internals only), so it can be exercised alone.
ADAPTER_SCRIPTS = [SPA_DIR / "m3_adapter.js"]

# A representative Tatooine-shaped dataset. Identical in spirit to the
# composition-engine test's TEST_DATA but parameterized for the substrate
# switch — we render it once with and once without `substrate_image`.
_BASE_DATA = {
    "display_name": "MOS EISLEY",
    "bounds": {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100},
    "rooms": [
        {"id": "r1", "x": 25, "y": 25, "w": 12, "h": 12, "style": "dock",
         "slug": "docking_bay_94_pit", "security": "lawless"},
        {"id": "r4", "x": 30, "y": 80, "w": 8, "h": 8, "style": "street"},
        {"id": "r5", "x": 80, "y": 70, "w": 10, "h": 10, "style": "housing"},
    ],
    "districts": [
        {"id": "spaceport",
         "polygon": [[5, 5], [95, 5], [95, 50], [5, 50]],
         "label_anchor": [50, 25], "name": "SPACEPORT", "terrain": "duracrete"},
    ],
    "streets": [
        {"id": "s1", "path": [[10, 80], [90, 80]], "kind": "main",
         "label": "Spaceport Strip"},
    ],
    "landmarks": [
        {"x": 25, "y": 25, "label": "Bay 94", "important": True},
    ],
    "furniture": [
        {"kind": "vaporator", "x": 60, "y": 30},
    ],
    "dynamic": {
        "player": {"x": 50, "y": 50, "bearing": 45},
        "pcs": [],
        "npcs": [{"x": 70, "y": 20, "kind": "friendly"}],
        "poi": [{"x": 75, "y": 50, "kind": "mission"}],
    },
}


# ── L_SubstrateImage ────────────────────────────────────────────────────

def test_l_substrate_image_emits_image_at_projected_bounds() -> None:
    """L_SubstrateImage returns a single <image> whose box is the world
    bounds run through the same projector the overlays use. With the
    canonical projector test bounds (0,0,100,50) @ 800x600 padding 20:
    project(0,0)=[20,110], project(100,50)=[780,490]."""
    result = run_with_dom(ENGINE_SCRIPTS, """
        var ce = window.M3CompositionEngine;
        var bounds = { x_min: 0, y_min: 0, x_max: 100, y_max: 50 };
        var proj = ce.makeProjector({
            bounds: bounds, width: 800, height: 600, padding: 20
        });
        var el = ce.L_SubstrateImage({
            proj: proj, bounds: bounds,
            href: '/static/maps/mos_eisley_substrate.png'
        });
        result = {
            tag:    el.tagName,
            href:   el.getAttribute('href'),
            x:      Number(el.getAttribute('x')),
            y:      Number(el.getAttribute('y')),
            width:  Number(el.getAttribute('width')),
            height: Number(el.getAttribute('height')),
            par:    el.getAttribute('preserveAspectRatio')
        };
    """)
    assert result["tag"] == "image"
    assert result["href"] == "/static/maps/mos_eisley_substrate.png"
    assert result["x"] == 20
    assert result["y"] == 110
    assert result["width"] == 760
    assert result["height"] == 380
    # 'none' so the painting fills the bounds rect; registration stays
    # self-consistent because overlays use the same projector.
    assert result["par"] == "none"


# ── Tier1aBody mode switch ──────────────────────────────────────────────

def test_tier1abody_with_substrate_emits_image_and_skips_procedural() -> None:
    """When data.substrate_image is set, Tier1aBody emits exactly one
    <image> and skips the six procedural geometry layers (district fills,
    security tint, streets, twin-sun shadows, building footprints, ambient
    furniture). The procedural substrate <rect> is replaced by the image.

    Procedural tatooine/day = 15 children (see composition-engine z-order
    test). Substrate mode removes districts+security+streets+twin-sun+
    buildings+furniture (6) and swaps the procedural substrate rect for an
    <image>, then ADDS L_SubstrateRooms (the tier<=1 tactical click-target
    layer that replaces the skipped L_Buildings cells under a painting):
    15 - 6 + 1 = 10 children, exactly one of them an <image>.

    Count attribution (2026-06-13, xdist triage): the original pin was 9,
    computed as 15-6 and predating L_SubstrateRooms — which landed in the
    SAME squash commit (`catchup_01`) but was never exercised because jsdom
    wasn't resolvable, so this test always skipped. With repo-local
    node_modules now present (drop 26), the test runs and the
    substrate-rooms layer is correctly counted: 10, not 9."""
    data_with = dict(_BASE_DATA)
    data_with["substrate_image"] = "/static/maps/mos_eisley_substrate.png"
    result = run_with_dom(ENGINE_SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var svg = window.M3CompositionEngine.Tier1aBody({
            data: %s, palette: p,
            tier: 1, time: 'day', weather: 'clear',
            width: 1200, height: 720
        });
        var tags = [], images = 0;
        for (var i = 0; i < svg.childNodes.length; i++) {
            var t = svg.childNodes[i].tagName;
            tags.push(t);
            if (t === 'image') images++;
        }
        var img = svg.querySelectorAll('image');
        var subRooms = svg.querySelectorAll('g.substrate-rooms');
        var clickTargets = svg.querySelectorAll('g.substrate-rooms g[data-room-id]');
        result = {
            count: svg.childNodes.length,
            images: images,
            tags: tags,
            imageHref: img.length ? img[0].getAttribute('href') : null,
            substrateRoomsLayers: subRooms.length,
            clickTargets: clickTargets.length
        };
    """ % json.dumps(data_with))
    assert result["count"] == 10, f"expected 10 children, got {result['count']}"
    assert result["images"] == 1, "expected exactly one <image> substrate"
    assert result["imageHref"] == "/static/maps/mos_eisley_substrate.png"
    # The skipped procedural L_Buildings is replaced by L_SubstrateRooms,
    # which paints one click-target <g data-room-id> per non-street room so
    # click-to-walk still works under a painting. _BASE_DATA has 3 rooms,
    # one of style 'street' (skipped) → 2 click targets.
    assert result["substrateRoomsLayers"] == 1, "substrate mode must add L_SubstrateRooms"
    assert result["clickTargets"] == 2, (
        f"expected 2 non-street room click targets, got {result['clickTargets']}")
    # Atmosphere (a <g>) is retained and sits BEHIND the substrate; the
    # painted <image> immediately follows it. The two leading <defs> blocks
    # (terrain + haze gradients) are always present.
    assert result["tags"][0] == "defs" and result["tags"][1] == "defs"
    assert result["tags"][2] == "g", "atmosphere layer must be retained"
    assert result["tags"][3] == "image", "substrate must render right after atmosphere"


def test_tier1abody_without_substrate_renders_procedural_layers() -> None:
    """Regression: with no substrate_image, Tier1aBody renders the full
    procedural stack (15 children on tatooine/day) and emits NO <image>."""
    result = run_with_dom(ENGINE_SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var svg = window.M3CompositionEngine.Tier1aBody({
            data: %s, palette: p,
            tier: 1, time: 'day', weather: 'clear',
            width: 1200, height: 720
        });
        var images = 0;
        for (var i = 0; i < svg.childNodes.length; i++) {
            if (svg.childNodes[i].tagName === 'image') images++;
        }
        result = { count: svg.childNodes.length, images: images };
    """ % json.dumps(_BASE_DATA))
    assert result["count"] == 15, f"expected 15 children, got {result['count']}"
    assert result["images"] == 0, "procedural mode must emit no <image>"


# ── Adapter Y reflection ────────────────────────────────────────────────

def test_adapter_reflects_y_about_bounds_midline() -> None:
    """fromAreaGeometry reflects every emitted y as (y_min+y_max)-y, leaves
    x untouched, and maps the midline to itself. Bounds y in [-0.4, 7.6]
    → midline 3.6; a room at y=6.4 lands at 0.8; a room at y=3.6 is fixed."""
    fixture = {
        "display_name": "TEST",
        "bounds": {"x_min": 2.4, "y_min": -0.4, "x_max": 14.8, "y_max": 7.6},
        "rooms": [
            {"id": "hi", "x": 3.9, "y": 6.4, "w": 0.9, "h": 0.9, "style": "dock"},
            {"id": "mid", "x": 5.0, "y": 3.6, "w": 0.5, "h": 0.5, "style": "civic"},
        ],
        "districts": [
            {"id": "d", "name": "D", "polygon": [[3.4, 3.6], [7.4, 7.4]],
             "label_anchor": [6.6, 7.0], "rotation": 0},
        ],
        "exit_paths": {
            "1-2": {"kind": "street", "path": [[5.4, 6.4], [5.4, 5.4]], "width": 0.3},
        },
        "landmarks": [
            {"x": 3.9, "y": 6.4, "label": "Bay"},
        ],
        "labels": [],
        "exits": [],
        "player": {"x": 3.9, "y": 6.4},
        "contacts": [{"x": 5.4, "y": 5.4, "kind": "npc", "name": "NPC"}],
    }
    result = run_with_dom(ADAPTER_SCRIPTS, """
        var data = window.M3Adapter.fromAreaGeometry(%s);
        var rByHi = null, rByMid = null;
        for (var i = 0; i < data.rooms.length; i++) {
            if (data.rooms[i].id === 'hi')  rByHi  = data.rooms[i];
            if (data.rooms[i].id === 'mid') rByMid = data.rooms[i];
        }
        result = {
            roomHiX:       rByHi.x,
            roomHiY:       rByHi.y,
            roomMidY:      rByMid.y,
            districtPoly0Y: data.districts[0].polygon[0][1],
            districtAnchorY: data.districts[0].label_anchor[1],
            streetPt0Y:    data.streets[0].path[0][1],
            landmarkY:     data.landmarks[0].y,
            playerY:       data.dynamic.player.y,
            npcY:          data.dynamic.npcs[0].y,
            poiY:          data.dynamic.poi[0].y
        };
    """ % json.dumps(fixture))
    # (y_min + y_max) = -0.4 + 7.6 = 7.2
    assert result["roomHiX"] == 3.9, "x must be untouched by the Y reflection"
    assert abs(result["roomHiY"] - 0.8) < 1e-9      # 7.2 - 6.4
    assert abs(result["roomMidY"] - 3.6) < 1e-9     # midline fixed point
    assert abs(result["districtPoly0Y"] - 3.6) < 1e-9   # 7.2 - 3.6
    assert abs(result["districtAnchorY"] - 0.2) < 1e-9  # 7.2 - 7.0
    assert abs(result["streetPt0Y"] - 0.8) < 1e-9       # 7.2 - 6.4
    assert abs(result["landmarkY"] - 0.8) < 1e-9        # 7.2 - 6.4
    assert abs(result["playerY"] - 0.8) < 1e-9          # 7.2 - 6.4
    assert abs(result["npcY"] - 1.8) < 1e-9             # 7.2 - 5.4
    assert abs(result["poiY"] - 0.8) < 1e-9             # 7.2 - 6.4 (landmark→POI)


def test_adapter_does_not_mutate_source_geometry_arrays() -> None:
    """The reflection must build NEW arrays. The cached source geom is
    re-fed through the adapter every tick; mutating shared polygon/path
    arrays would compound the flip and drift the map on each re-render."""
    fixture = {
        "display_name": "TEST",
        "bounds": {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10},
        "rooms": [{"id": "a", "x": 1, "y": 2, "w": 1, "h": 1, "style": "dock"}],
        "districts": [
            {"id": "d", "name": "D", "polygon": [[1, 1], [9, 9]],
             "label_anchor": [5, 5], "rotation": 0},
        ],
        "exit_paths": {"1-2": {"kind": "street", "path": [[2, 3], [4, 5]]}},
        "landmarks": [], "labels": [], "exits": [],
        "player": {"x": 1, "y": 2}, "contacts": [],
    }
    result = run_with_dom(ADAPTER_SCRIPTS, """
        var geom = %s;
        // Two passes simulate the per-tick re-feed of the cached geom.
        var d1 = window.M3Adapter.fromAreaGeometry(geom);
        var d2 = window.M3Adapter.fromAreaGeometry(geom);
        result = {
            sourcePoly0Y:  geom.districts[0].polygon[0][1],   // must stay 1
            sourcePathY:   geom.exit_paths['1-2'].path[0][1], // must stay 3
            firstPassY:    d1.districts[0].polygon[0][1],     // 10 - 1 = 9
            secondPassY:   d2.districts[0].polygon[0][1]      // still 9
        };
    """ % json.dumps(fixture))
    assert result["sourcePoly0Y"] == 1, "source polygon was mutated!"
    assert result["sourcePathY"] == 3, "source street path was mutated!"
    assert abs(result["firstPassY"] - 9.0) < 1e-9
    assert abs(result["secondPassY"] - 9.0) < 1e-9, "flip compounded across re-renders"


# ── Adapter substrate_image forwarding ──────────────────────────────────

def test_adapter_forwards_substrate_image_when_present() -> None:
    """The substrate path must survive translation so Tier1aBody can read
    data.substrate_image. Present => forwarded; absent => omitted."""
    base = {
        "display_name": "T",
        "bounds": {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10},
        "rooms": [{"id": "a", "x": 1, "y": 2, "w": 1, "h": 1, "style": "dock"}],
        "districts": [], "exit_paths": {}, "landmarks": [], "labels": [],
        "exits": [], "player": {"x": 1, "y": 2}, "contacts": [],
    }
    with_sub = dict(base)
    with_sub["substrate_image"] = "/static/maps/mos_eisley_substrate.png"
    result = run_with_dom(ADAPTER_SCRIPTS, """
        var dWith = window.M3Adapter.fromAreaGeometry(%s);
        var dWithout = window.M3Adapter.fromAreaGeometry(%s);
        result = {
            withVal:      dWith.substrate_image || null,
            withoutHasIt: Object.prototype.hasOwnProperty.call(dWithout, 'substrate_image')
        };
    """ % (json.dumps(with_sub), json.dumps(base)))
    assert result["withVal"] == "/static/maps/mos_eisley_substrate.png"
    assert result["withoutHasIt"] is False, "procedural areas must omit substrate_image"


# ── Adapter landmark shape: pos[] (loader format) ───────────────────────

def test_adapter_reads_loader_landmark_pos_array() -> None:
    """The AreaGeometry loader emits landmarks as {id, icon, name, pos:[x,y]}
    — NOT {x, y, label}. The adapter must read `pos` (and `name`) or every
    real landmark is silently dropped (it was: 0 POI, only flavor-labels as
    labels). Regression for the pos[]-vs-x/y mismatch. Y is also reflected."""
    fixture = {
        "display_name": "T",
        "bounds": {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10},
        "rooms": [{"id": "a", "x": 1, "y": 2, "w": 1, "h": 1, "style": "dock"}],
        "districts": [], "exit_paths": {}, "labels": [], "exits": [],
        "player": {"x": 1, "y": 2}, "contacts": [],
        "landmarks": [
            {"id": "bay94", "icon": "dock", "name": "Docking Bay 94",
             "pos": [3.9, 6.4], "min_zoom": 2, "max_zoom": 2},
            {"id": "chalmun", "icon": "cantina", "name": "Chalmun's Cantina",
             "pos": [2.8, 2.9], "min_zoom": 2, "max_zoom": 2},
        ],
    }
    result = run_with_dom(ADAPTER_SCRIPTS, """
        var data = window.M3Adapter.fromAreaGeometry(%s);
        var byName = {};
        data.landmarks.forEach(function (l) { byName[l.label] = l; });
        result = {
            labelCount: data.landmarks.length,
            poiCount:   data.dynamic.poi.length,
            bayLabel:   !!byName['Docking Bay 94'],
            bayY:       byName['Docking Bay 94'] ? byName['Docking Bay 94'].y : null,
            firstPoiKind: data.dynamic.poi[0] ? data.dynamic.poi[0].kind : null
        };
    """ % json.dumps(fixture))
    # Both landmarks become labels (name used as label) AND POI markers.
    assert result["labelCount"] == 2, "pos[] landmarks must produce labels"
    assert result["poiCount"] == 2, "pos[] landmarks must produce POI markers"
    assert result["bayLabel"] is True, "landmark name must become the label"
    # Y reflected about midline (y_min+y_max=10): 10 - 6.4 = 3.6
    assert abs(result["bayY"] - 3.6) < 1e-9
    # POI kind derives from icon when no explicit kind
    assert result["firstPoiKind"] == "dock"


def test_adapter_still_accepts_xy_landmark_shape() -> None:
    """Back-compat: the older {x, y, label} landmark shape (used by some
    synthetic callers) must still translate, via the same normalizer."""
    fixture = {
        "display_name": "T",
        "bounds": {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10},
        "rooms": [{"id": "a", "x": 1, "y": 2, "w": 1, "h": 1, "style": "dock"}],
        "districts": [], "exit_paths": {}, "labels": [], "exits": [],
        "player": {"x": 1, "y": 2}, "contacts": [],
        "landmarks": [{"x": 4.0, "y": 7.0, "label": "Old Shape", "important": True}],
    }
    result = run_with_dom(ADAPTER_SCRIPTS, """
        var data = window.M3Adapter.fromAreaGeometry(%s);
        result = {
            labelCount: data.landmarks.length,
            label:      data.landmarks[0] ? data.landmarks[0].label : null,
            y:          data.landmarks[0] ? data.landmarks[0].y : null
        };
    """ % json.dumps(fixture))
    assert result["labelCount"] == 1
    assert result["label"] == "Old Shape"
    assert abs(result["y"] - 3.0) < 1e-9   # 10 - 7.0
