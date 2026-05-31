"""
test_client_wireup_42a.py — Drop 4.2a wire-in verification.

Tier 1 #4 · May 26 2026.

These tests verify that the M3 SPA composition engine is correctly
wired into static/client.html (render-only — no interaction handlers
in 4.2a). They cover:

1. STATIC CHECKS (no jsdom needed):
   - All 9 expected SPA script tags appear in client.html in the
     correct dependency order.
   - The legacy <svg id="g-area-map-svg"> slot still exists.
   - renderMapV2() carries both the M3 branch and the legacy fallback.

2. DOM TESTS (jsdom, exercises the actual rendering pipeline):
   - With flag on + a fixture geometry, M3Adapter.fromAreaGeometry
     produces a valid M3 data shape.
   - The composition engine's Tier1aBody renders the adapted geometry
     into a non-empty SVG tree.
   - The adapter is robust to incomplete geometry (returns null
     instead of throwing).
   - The adapter correctly partitions contacts into pcs vs npcs.
"""
from __future__ import annotations

import re
from pathlib import Path

from .spa_dom_harness import run_with_dom, require_node_and_jsdom


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
SPA_DIR = REPO_ROOT / "static" / "spa"


# Load order MUST match the dependency declarations in each module:
#   m3_tokens                 → base (svgEl)
#   m3_palettes               → independent
#   m3_assets_*               → depend on tokens; load before composition
#   m3_composition_engine     → depends on tokens + all asset modules
#   m3_adapter                → depends on M3Adapter only at call time
#                               (no hard deps; bundled here for cohesion)
#   m3_combat_inspector       → Drop 4.4 — independent SPA module ported
#                               from the in-line D' block; init() called
#                               by client.html after load
#   m3_combat_theater         → Drop 4.5 — HUD chrome (right-rail panels +
#                               bottom action strip with bug-fix-sprint
#                               corrections); init() called by client.html
#   m3_sheet                  → Drop 4.6 — character-sheet renderer ported
#                               from sheet-v2.jsx with B3/B4/H4/H5/L3/L5
#                               bug-fix-sprint corrections preserved
#   m3_holocron               → Drop 4.7 — in-game lore browser ported
#                               from holocron.jsx; B3-clean (Clone Wars
#                               era framing); Hutt Cartel demo fixture
#   m3_map_navigator          → Drop 4.8 — interactive zoom/pan/tier
#                               orchestrator ported from map-navigator.jsx;
#                               first SPA module with internal runtime
#                               state (stateful component pattern via
#                               .create(p, hooks) handle)
#   m3_cockpit                → Drop 4.9 — cockpit flight console ported
#                               from cockpit.jsx; D6-accurate ship with
#                               dice hull + fore/aft shields; phase-aware
#                               action strip that DI's M3CombatTheater
#                               .buildActionButton (with local fallback)
#   m3_holonet                → Drop 4.10 — Holonet news/world-state
#                               surface (ticker marquee + full popup
#                               browser) ported from holonet.jsx;
#                               CW-era 20 BBY framing
#   m3_skill_check            → Drop 4.11 — Skill-check ribbon showcase
#                               (unopposed + opposed WEG D6 non-combat
#                               resolution) ported from skill-check.jsx;
#                               scene + setup pose + dice + outcome pose
#                               + system effects; Mos Eisley Tey Voss
#                               fixtures
#   m3_assembled_client       → Drop 4.12b — Integration target / full
#                               field-kit shell ported from
#                               assembled-client.jsx; composes Sheet,
#                               Holocron, MapNavigator, Holonet via DI;
#                               owns popup + cartridge state; tier-
#                               renderer seam mirrors Drop 4.8
#   m3_tier_galaxy_body       → Drop 4.13 (Batch 1) — Tier 4c galaxy
#                               view (CW era 20 BBY); pure SVG; 13
#                               notable systems + 4 hyperlanes
#   m3_tier_system_body       → Drop 4.13 (Batch 1) — Tier 4a Tatooine
#                               system view; twin suns, 5 bodies +
#                               asteroid belt + 4 hyperspace beacons +
#                               RUSTY MYNOCK player ship
#   m3_tier_planet_body       → Drop 4.13 (Batch 1) — Tier 3 Tatooine
#                               planet view; HolocartaFrame chrome
#                               (via DI), 8 cities, 5 regions, 6
#                               travel routes
#   m3_tier_city_body         → Drop 4.14 (Batch 2) — Tier 2 Mos Eisley
#                               city overview; 6 districts, 5 landmarks,
#                               street grid, beacon pulse
#   m3_tier_wilderness_body   → Drop 4.14 (Batch 2) — Tier 1b Dune Sea
#                               region; 5 sub-regions, 6 POIs, 4 routes,
#                               9 dune ridges, inline DUNE_SEA fixture
#   m3_tier_interior_body     → Drop 4.14 (Batch 2) — Tier 0 Chalmun's
#                               Cantina interior; 5 furniture, 4 exits,
#                               7 entity dots, faction tints
#   m3_tier_registry          → Drop 4.15 (cutover) — canonical
#                               getTierRenderer lookup; resolves all 7
#                               tiers; default for both consumers
EXPECTED_SPA_LOAD_ORDER = [
    "m3_tokens.js",
    "m3_palettes.js",
    "m3_assets_styles.js",
    "m3_assets_icons.js",
    "m3_assets_markers.js",
    "m3_assets_wilderness.js",
    "m3_assets_overlays.js",
    "m3_assets_landmarks.js",
    "m3_composition_engine.js",
    "m3_adapter.js",
    "m3_combat_inspector.js",
    "m3_combat_theater.js",
    "m3_sheet.js",
    "m3_holocron.js",
    "m3_map_navigator.js",
    "m3_cockpit.js",
    "m3_holonet.js",
    "m3_skill_check.js",
    "m3_assembled_client.js",
    "m3_tier_galaxy_body.js",
    "m3_tier_system_body.js",
    "m3_tier_planet_body.js",
    "m3_tier_city_body.js",
    "m3_tier_wilderness_body.js",
    "m3_tier_interior_body.js",
    "m3_tier_registry.js",
]


# Canonical Mos Eisley AreaGeometry payload — the minimum shape the
# server emits today via engine.area_loader.load_area_geometry().to_dict
# (after the client.html intake at line 5463 adds .player/.contacts).
# Coordinates lifted from data/worlds/clone_wars/maps/mos_eisley.yaml so
# this fixture stays in sync with production data.
MOS_EISLEY_FIXTURE = {
    "schema_version": 1,
    "area_key": "tatooine.mos_eisley",
    "display_name": "MOS EISLEY",
    "planet": "TATOOINE",
    "era": "20 BBY · Clone Wars",
    "default_terrain": "sand",
    "palette": "tatooine",
    "bounds": {"x_min": 2.4, "y_min": -0.4, "x_max": 14.8, "y_max": 7.6},
    "districts": [
        {
            "id": "spaceport",
            "name": "SPACEPORT",
            "polygon": [[3.4, 3.6], [7.4, 3.6], [7.4, 7.4], [3.4, 7.4]],
            "label_anchor": [6.6, 7.0],
            "rotation": 0,
        },
        {
            "id": "market",
            "name": "MARKET QUARTER",
            "polygon": [[7.6, 3.6], [12.4, 3.6], [12.4, 7.4], [7.6, 7.4]],
            "label_anchor": [11.4, 7.0],
            "rotation": 0,
        },
    ],
    "rooms": [
        {"id": 1, "name": "Docking Bay 94", "zone": "spaceport",
         "x": 4.0, "y": 5.0, "w": 1.0, "h": 1.0,
         "style": "dock", "symbol": "▽", "slug": "docking_bay_94"},
        {"id": 7, "name": "Westport Cantina", "zone": "market",
         "x": 8.0, "y": 4.0, "w": 0.8, "h": 0.8,
         "style": "cantina", "symbol": "♪"},
        {"id": 11, "name": "Mos Eisley Market", "zone": "market",
         "x": 9.5, "y": 5.5, "w": 1.2, "h": 0.8,
         "style": "market", "symbol": "$"},
    ],
    "exits": [[1, 7], [7, 11]],
    "exit_paths": {
        "1-7": {"kind": "street", "path": [[4.5, 5.0], [5.4, 5.0], [5.4, 4.0], [7.6, 4.0]], "width": 0.30},
        "7-11": {"kind": "street", "path": [[8.4, 4.0], [9.5, 4.0], [9.5, 5.1]], "width": 0.30},
    },
    "labels": [],
    "landmarks": [
        {"kind": "tower", "x": 6.0, "y": 7.2, "label": "Lars Homestead Marker", "min_zoom": 1},
    ],
    # Populated by client.html at lines 5463-5475 from the
    # area_geometry event + the contacts list. Tests inject directly.
    "player": {"room_id": 1, "x": 4.0, "y": 5.0},
    "contacts": [
        {"id": "pc_jax", "name": "Jax Vey", "x": 4.2, "y": 5.0, "kind": "pc", "bearing": 90},
        {"id": "npc_wuher", "name": "Wuher", "x": 8.0, "y": 4.0, "kind": "npc"},
        {"id": "npc_bartender", "name": "Cantina Patron", "x": 8.1, "y": 4.1},  # no kind → defaults to npc
    ],
}


# ─── Static checks ───────────────────────────────────────────────────


def test_client_html_loads_all_spa_modules_in_order():
    """client.html must load all 10 SPA scripts in dependency order."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    # Find every /static/spa/m3_*.js script src in document order
    pattern = re.compile(r'<script src="/static/spa/(m3_[a-z_]+\.js)"></script>')
    found = pattern.findall(text)
    assert found == EXPECTED_SPA_LOAD_ORDER, (
        f"SPA script tags out of order or missing.\n"
        f"  expected: {EXPECTED_SPA_LOAD_ORDER}\n"
        f"  found:    {found}"
    )


def test_legacy_map_view_script_still_loaded():
    """map_view.js must still be loaded — it's the fallback path."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    assert '<script src="/static/map_view.js"></script>' in text, (
        "Legacy MapView script tag missing — fallback path is broken."
    )


def test_legacy_svg_slot_preserved():
    """The legacy SVG render target #g-area-map-svg must still exist."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    assert 'id="g-area-map-svg"' in text, (
        "Legacy SVG slot id missing — render target broken."
    )


def test_renderMapV2_has_m3_branch_and_legacy_fallback():
    """renderMapV2() must carry BOTH the M3 branch and the legacy MapView
    fallback (so a flag flip — or M3 module load failure — cleanly
    reverts to the legacy renderer)."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    # Isolate the function body
    func_start = text.find("function renderMapV2()")
    assert func_start > 0, "renderMapV2 function missing"
    # Walk forward until matching close brace at column 0
    func_tail = text[func_start:]
    end_match = re.search(r"\n}\n", func_tail)
    assert end_match, "renderMapV2 close brace not found"
    body = func_tail[: end_match.end()]
    # M3 branch markers
    assert "M3Adapter" in body and "M3CompositionEngine" in body and "Tier1aBody" in body, (
        "M3 branch missing from renderMapV2"
    )
    assert "_sw_useM3MiniRenderer" in body, "Feature flag check missing"
    # Legacy fallback markers
    assert "MapView.render" in body, "Legacy MapView fallback removed"
    # Renderer-tag side effect (helps smoke tests + debug)
    assert "data-renderer" in body, "data-renderer attribute hook missing"


# ─── DOM tests (jsdom — exercise the actual M3 pipeline) ─────────────


def _spa_script_paths():
    """All SPA modules a real client would load, in dependency order."""
    return [SPA_DIR / name for name in EXPECTED_SPA_LOAD_ORDER]


def test_adapter_translates_canonical_geom_to_m3_data():
    """The adapter must produce a valid M3 data shape from the canonical
    Mos Eisley geometry payload — districts, streets, rooms, and the
    dynamic.{player,pcs,npcs,poi} layer all populated."""
    import json
    setup_js = """
        var fixture = %s;
        var data = window.M3Adapter.fromAreaGeometry(fixture);
        result = {
          schemaVersion: window.M3Adapter.SCHEMA_VERSION,
          displayName:   data && data.display_name,
          roomCount:     data && data.rooms ? data.rooms.length : 0,
          districtCount: data && data.districts ? data.districts.length : 0,
          streetCount:   data && data.streets ? data.streets.length : 0,
          firstStreetId: data && data.streets && data.streets[0] && data.streets[0].id,
          firstStreetKind: data && data.streets && data.streets[0] && data.streets[0].kind,
          pcCount:       data && data.dynamic && data.dynamic.pcs.length,
          npcCount:      data && data.dynamic && data.dynamic.npcs.length,
          poiCount:      data && data.dynamic && data.dynamic.poi.length,
          playerX:       data && data.dynamic && data.dynamic.player.x,
          playerBearing: data && data.dynamic && data.dynamic.player.bearing,
          firstRoomSlug: data && data.rooms && data.rooms[0] && data.rooms[0].slug
        };
    """ % (json.dumps(MOS_EISLEY_FIXTURE),)
    out = run_with_dom(_spa_script_paths(), setup_js)
    assert out["schemaVersion"] == 2   # bumped 1→2 in 4.2c
    assert out["displayName"] == "MOS EISLEY"
    assert out["roomCount"] == 3, f"expected 3 rooms, got {out['roomCount']}"
    assert out["districtCount"] == 2, f"expected 2 districts, got {out['districtCount']}"
    assert out["streetCount"] == 2, f"expected 2 streets, got {out['streetCount']}"
    assert out["firstStreetId"] in ("1-7", "7-11"), f"unexpected street id {out['firstStreetId']}"
    assert out["firstStreetKind"] == "street"
    assert out["pcCount"] == 1, f"expected 1 PC (kind='pc'), got {out['pcCount']}"
    # Two unkinded/npc contacts → both should land in npcs
    assert out["npcCount"] == 2, f"expected 2 NPCs, got {out['npcCount']}"
    # Landmark becomes a POI
    assert out["poiCount"] == 1, f"expected 1 POI (landmark), got {out['poiCount']}"
    assert out["playerX"] == 4.0
    # Bearing defaulted to 0 since fixture player doesn't include one
    assert out["playerBearing"] == 0
    # Slug preserved through translation (matters for L_Buildings landmark resolution)
    assert out["firstRoomSlug"] == "docking_bay_94"


def test_adapter_returns_null_on_incomplete_geom():
    """Defensive: incomplete geometry → adapter returns null (caller
    falls back to legacy MapView, not a thrown exception)."""
    setup_js = """
        var nullRes  = window.M3Adapter.fromAreaGeometry(null);
        var emptyRes = window.M3Adapter.fromAreaGeometry({});
        var noBounds = window.M3Adapter.fromAreaGeometry({rooms: [{id:1, x:0, y:0, w:1, h:1, style:'dock'}]});
        var noRooms  = window.M3Adapter.fromAreaGeometry({bounds: {x_min:0,y_min:0,x_max:10,y_max:10}, rooms: []});
        result = {
          nullCase: nullRes,
          emptyCase: emptyRes,
          noBoundsCase: noBounds,
          noRoomsCase: noRooms
        };
    """
    out = run_with_dom(_spa_script_paths(), setup_js)
    assert out["nullCase"] is None
    assert out["emptyCase"] is None
    assert out["noBoundsCase"] is None
    assert out["noRoomsCase"] is None


def test_composition_engine_renders_adapted_geom_without_throwing():
    """The full pipeline: server geom → adapter → engine. Must produce
    a non-empty SVG tree with the expected layer structure."""
    import json
    setup_js = """
        var fixture = %s;
        var data    = window.M3Adapter.fromAreaGeometry(fixture);
        var palette = window.M3Palettes.getPalette('tatooine');
        var svg = window.M3CompositionEngine.Tier1aBody({
          data: data, palette: palette, tier: 1,
          time: 'day', weather: 'clear',
          width: 360, height: 420
        });
        result = {
          tagName:      svg && svg.tagName,
          namespaceOK:  svg && svg.namespaceURI === 'http://www.w3.org/2000/svg',
          childCount:   svg && svg.childNodes ? svg.childNodes.length : 0,
          viewBox:      svg && svg.getAttribute && svg.getAttribute('viewBox'),
          width:        svg && svg.getAttribute && svg.getAttribute('width'),
          height:       svg && svg.getAttribute && svg.getAttribute('height')
        };
    """ % (json.dumps(MOS_EISLEY_FIXTURE),)
    out = run_with_dom(_spa_script_paths(), setup_js)
    assert out["tagName"] == "svg", f"expected svg root, got {out['tagName']}"
    assert out["namespaceOK"] is True
    # The Tier1aBody output must have multiple layers (per arch v50
    # §4.15: ≥ atmosphere + substrate + districts + buildings + entities
    # + compass + scale = 7 minimum even with no weather/twin-sun gates)
    assert out["childCount"] >= 7, (
        f"expected ≥7 layered children in Tier1aBody output, got {out['childCount']}"
    )
    assert out["width"] is not None and out["height"] is not None
    assert out["viewBox"] is not None


def test_adapter_handles_geom_with_no_districts_or_landmarks():
    """An AreaGeometry that has rooms+bounds but no districts/landmarks/
    contacts is still acceptable — the engine should render a sparse map
    without crashing."""
    sparse = {
        "area_key": "test.sparse",
        "display_name": "TEST AREA",
        "bounds": {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10},
        "rooms": [
            {"id": 1, "name": "Room 1", "zone": "z",
             "x": 1.0, "y": 1.0, "w": 1.0, "h": 1.0, "style": "dock", "symbol": "▽"},
        ],
        "exit_paths": {},
        "landmarks": [],
        "player": {"x": 1.0, "y": 1.0},
        "contacts": [],
    }
    import json
    setup_js = """
        var fixture = %s;
        var data = window.M3Adapter.fromAreaGeometry(fixture);
        result = {
          roomCount:     data && data.rooms ? data.rooms.length : 0,
          districtCount: data && data.districts ? data.districts.length : 0,
          streetCount:   data && data.streets ? data.streets.length : 0,
          landmarkCount: data && data.landmarks ? data.landmarks.length : 0,
          poiCount:      data && data.dynamic && data.dynamic.poi.length,
          npcCount:      data && data.dynamic && data.dynamic.npcs.length
        };
    """ % (json.dumps(sparse),)
    out = run_with_dom(_spa_script_paths(), setup_js)
    assert out["roomCount"] == 1
    assert out["districtCount"] == 0
    assert out["streetCount"] == 0
    assert out["landmarkCount"] == 0   # 4.2a: always [] (LOUD substitution per adapter §)
    assert out["poiCount"] == 0
    assert out["npcCount"] == 0


def test_adapter_module_loads_after_engine_in_order():
    """Sanity: the adapter loads after the composition engine and binds
    its exports successfully. (jsdom verifies the script tags execute
    in load order and the exports survive.)"""
    setup_js = """
        result = {
          hasAdapter:    typeof window.M3Adapter === 'object' && window.M3Adapter !== null,
          hasEngine:     typeof window.M3CompositionEngine === 'object',
          hasTier1aBody: typeof window.M3CompositionEngine.Tier1aBody === 'function',
          hasFromArea:   typeof window.M3Adapter.fromAreaGeometry === 'function',
          adapterVer:    window.M3Adapter.SCHEMA_VERSION
        };
    """
    out = run_with_dom(_spa_script_paths(), setup_js)
    assert out["hasAdapter"] is True
    assert out["hasEngine"] is True
    assert out["hasTier1aBody"] is True
    assert out["hasFromArea"] is True
    assert out["adapterVer"] == 2     # bumped 1→2 in 4.2c
