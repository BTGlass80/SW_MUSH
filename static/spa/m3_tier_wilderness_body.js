/* ============================================================================
   m3_tier_wilderness_body.js — Tier 1b Wilderness renderer (region-driven).

   Drop 4.14 (Batch 2) ported map_v3/tier-1b.jsx as a Dune-Sea-hardcoded
   body. Drop 4.15a generalised it to "render the region passed in,
   substrate-first" so a SECOND region (Coruscant Underworld) renders
   correctly instead of Tatooine sand, and any future wilderness region —
   painted or procedural — drops in as data. The Dune Sea fixture is
   retained as the loud-substitution default: a bare buildTierOneBBody(p)
   is byte-stable with the pre-4.15a renderer.

   Region descriptor schema — see the block comment above DUNE_SEA.

   What this module ships:
     · M3TierWildernessBody.buildTierOneBBody(p, opts?)
            inner SVG renderer. opts.region (object) | opts.regionKey
            (slug) selects the region; falls back to Dune Sea. When the
            region carries substrate_image the procedural ground/dune/
            terrain-blob layers are skipped and the painted raster is
            rendered (mirrors L_SubstrateImage), POIs/routes/labels on top.
            Returns <svg>.
     · M3TierWildernessBody.buildTierOneBRegion(p, opts?)
            chrome'd (HolocartaFrame) region renderer; breadcrumb / tier /
            legend come from the region descriptor. Returns the frame's
            outer <div> (or a labeled fallback if HolocartaFrame absent).
     · M3TierWildernessBody.buildTierOneBDuneSea(p, opts?)     → Dune Sea
     · M3TierWildernessBody.buildTierOneBUnderworld(p, opts?)  → Underworld
            thin back-compat / convenience wrappers over buildTierOneBRegion.
     · M3TierWildernessBody.REGIONS / .resolveRegion(slug)     region table
     · M3TierWildernessBody.DUNE_SEA / .CORUSCANT_UNDERWORLD   fixtures
     · M3TierWildernessBody.SUB_REGIONS / .POIS / .ROUTES      Dune Sea bits

   Live-wiring boundary (Drop 4.15a): the renderer + the registry seam
   (m3_tier_registry.js forwards args.region / args.regionKey into '1b')
   are in place. Selecting WHICH region from the player's live location
   (navigator / assembled-client) remains the deferred UI-wiring drop —
   until then the showcase/registry default to Dune Sea.

   B3 era-cleanness:
     · Era subtitle "DUNE SEA \u00b7 TATOOINE \u00b7 OUTER RIM"
     · All sub-region/POI names are Tatooine-canonical (era-neutral).
     · Zero Empire/Imperial/TIE/X-wing/Rebel/Stormtrooper/Vader/Death
       Star/ISB references in data blocks.

   Q1 canonical-character policy note (architecture v50 §6.2):
     · "KRAYT GRAVEYARD" — canonical Tatooine landmark (krayt dragon
       bones), preserved verbatim per Drop 4.6 / 4.7 / 4.10 / 4.11 /
       4.12 / 4.13 source-fidelity policy.
     · "SARLACC PIT" — canonical hazard, preserved per same policy.
     · "TUSKEN CAMP" — canonical species locale, preserved per same
       policy.

   Palette keys consumed:
     p.amber, p.cyan, p.green, p.gold, p.red, p.ink, p.inkBright,
     p.inkDim, p.skyDeep
     · p.paper        — UNDOCUMENTED key from JSX source. Fallback to
                        p.inkBright per Drop 4.11 loud-substitution.
     · p.ground       — UNDOCUMENTED. Fallback to p.amber.
     · p.groundDeep   — UNDOCUMENTED. Fallback to p.skyDeep.
     · p.groundShadow — UNDOCUMENTED. Fallback to p.skyDeep.
     (Standard palettes lacking these keys still render the wilderness
     body — the sand gradient just degrades to amber/skyDeep bands.)

   Dependencies (consumed via defensive DI):
     · window.M3CompositionEngine.HolocartaFrame
            used by buildTierOneBDuneSea. If unavailable, the chrome'd
            version returns a labeled placeholder.
     · window.M3CompositionEngine.CompassRose
            optional decoration. If unavailable, skipped silently.
     · window.M3AssetsOverlays.TerrainDefs / HazeDefs / OV_TimeOfDay /
       OV_SandHaze
            optional. If unavailable, the relevant <defs>/overlays are
            skipped — sub-region blobs render as solid color.

   Loading order in client.html: AFTER m3_assets_overlays.js and
   m3_composition_engine.js (so DI hooks resolve).
   ============================================================================ */
(function(){
'use strict';

// ─── svgEl/htmlEl helpers ────────────────────────────────────────────
function svgEl(tag, attrs, children) {
  var el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (attrs) {
    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      var val = attrs[key];
      if (val === undefined || val === null || val === false) continue;
      if (key === 'style') applyStyle(el, val);
      else el.setAttribute(_camelToKebabSvg(key), String(val));
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === null || child === undefined || child === false) continue;
      if (typeof child === 'string' || typeof child === 'number') {
        el.appendChild(document.createTextNode(String(child)));
      } else {
        el.appendChild(child);
      }
    }
  }
  return el;
}

function htmlEl(tag, props, children) {
  var el = document.createElement(tag);
  if (props) {
    for (var key in props) {
      if (!Object.prototype.hasOwnProperty.call(props, key)) continue;
      var val = props[key];
      if (val === undefined || val === null || val === false) continue;
      if (key === 'style') applyStyle(el, val);
      else el.setAttribute(key, String(val));
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === null || child === undefined || child === false) continue;
      if (typeof child === 'string' || typeof child === 'number') {
        el.appendChild(document.createTextNode(String(child)));
      } else {
        el.appendChild(child);
      }
    }
  }
  return el;
}

function _camelToKebabSvg(k) {
  if (k === 'viewBox' || k === 'preserveAspectRatio') return k;
  return k.replace(/[A-Z]/g, function(c) { return '-' + c.toLowerCase(); });
}

function applyStyle(el, style) {
  if (!style) return;
  for (var k in style) {
    if (!Object.prototype.hasOwnProperty.call(style, k)) continue;
    var v = style[k];
    if (v === null || v === undefined || v === false) continue;
    el.style[k] = (typeof v === 'number' && !_isUnitlessCss(k)) ? (v + 'px') : v;
  }
}

function _isUnitlessCss(k) {
  return (k === 'opacity' || k === 'zIndex' || k === 'fontWeight' ||
          k === 'flex' || k === 'flexGrow' || k === 'flexShrink' ||
          k === 'lineHeight' || k === 'order');
}

// ════════════════════════════════════════════════════════════════════
// FIXTURES — JSX source data preserved verbatim (inline DUNE_SEA)
// ════════════════════════════════════════════════════════════════════
var SUB_REGIONS = [
  // {path-d, name, terrainId, opacity, labelX, labelY, labelColor, hazard?}
  { d: 'M 80 120 Q 240 90 380 140 Q 360 230 240 250 Q 120 240 80 160 Z',
    name: 'OPEN DUNES',     terrainId: 'url(#terr-dune)',   opacity: 0.82,
    lx: 230, ly: 175, color: 'inkBright' },
  { d: 'M 400 110 Q 540 90 620 160 Q 600 240 500 250 Q 410 230 400 150 Z',
    name: 'ROCK FLATS',     terrainId: 'url(#terr-scrub)',  opacity: 0.78,
    lx: 510, ly: 180, color: 'inkBright' },
  { d: 'M 120 280 Q 250 260 330 310 Q 310 400 200 410 Q 110 380 120 310 Z',
    name: 'THE PINNACLES',  terrainId: 'url(#terr-canyon)', opacity: 0.80,
    lx: 220, ly: 340, color: 'inkBright' },
  { d: 'M 380 290 Q 520 270 600 330 Q 580 420 470 430 Q 380 400 380 330 Z',
    name: 'SINKING SANDS',  terrainId: 'url(#terr-dune)',   opacity: 0.70,
    lx: 490, ly: 360, color: 'red', hazard: true },
  { d: 'M 200 440 Q 360 420 480 470 Q 460 560 320 570 Q 200 540 200 480 Z',
    name: 'KRAYT GRAVEYARD',terrainId: 'url(#terr-scrub)',  opacity: 0.76,
    lx: 340, ly: 505, color: 'gold' }
];

var POIS = [
  // Q1 watch: "SARLACC PIT", "TUSKEN CAMP", "KRAYT GRAVEYARD" preserved
  // per source-fidelity policy. See module header.
  { x: 180, y: 175, name: 'MOISTURE FARM', player: true,  size: 9 },
  { x: 500, y: 175, name: 'TUSKEN CAMP',   hostile: true, size: 8 },
  { x: 470, y: 360, name: 'SARLACC PIT',   hazard: true,  size: 9 },
  { x: 230, y: 340, name: 'CRASHED FREIGHTER', size: 7 },
  { x: 340, y: 505, name: 'BANTHA HERD',   size: 6 },
  { x: 320, y: 250, name: 'SANDCRAWLER TRACK', size: 6 }
];

var ROUTES = [
  // [[fromX,fromY],[toX,toY], dashed?]
  [[180, 175], [320, 250], false],   // farm → sandcrawler track
  [[320, 250], [500, 175], true],    // track → tusken camp (caution)
  [[180, 175], [230, 340], false],   // farm → crashed freighter
  [[230, 340], [340, 505], true]     // freighter → bantha herd (rough)
];

// Composite fixture (matches the JSX source's exported shape).
//
// Region descriptor schema consumed by buildTierOneBBody / buildTierOneBRegion:
//   name          title text (top-left)            string
//   biome         subtitle text (under title)       string
//   bounds        world bounds {x_min,..,y_max}     object
//   sub_regions   terrain blob array                array  → SUB_REGIONS shape
//   pois          point-of-interest array           array  → POIS shape
//   routes        track polyline array              array  → ROUTES shape
//   substrate_image (optional) painted raster href  string → substrate-first
//   bg            (optional) svg background fill     CSS color   (def groundDeep)
//   ridge_count   (optional) background ridge count  int         (def 9 dunes)
//   ridge_color   (optional) ridge stroke palette-key/CSS         (def alt-band)
//   ground_stops  (optional) [{offset,color,opacity?}] for the body gradient
//   breadcrumb    (optional) HolocartaFrame breadcrumb           (def Dune Sea)
//   tier_label    (optional) HolocartaFrame tier label           (def 1B·WILD)
//   legend_spec   (optional) [{colorKey,shape,glow?,label}]      (def dune)
//
// Every optional key falls back to the Dune Sea behaviour (loud-substitution
// per Drop 4.11), so a region carrying ONLY {name,biome,sub_regions,pois,
// routes} renders correctly and a bare buildTierOneBBody(p) is byte-stable.
var DUNE_SEA = {
  name: 'DUNE SEA',
  biome: 'TATOOINE \u00b7 OUTER RIM \u00b7 ARID',
  // NOTE (Drop 4.17): the LIVE Tier-1b map uses the generated faithful
  // region data (m3_wilderness_overview_data.js), where substrate_image
  // auto-engages once static/maps/tatooine_dune_sea_substrate.png exists at
  // generation time. This fixture is now only a showcase/test fallback; do
  // not hand-wire a substrate here — re-run tools/gen_wilderness_overview.py.
  bounds: { x_min: 0, y_min: 0, x_max: 700, y_max: 600 },
  sub_regions: SUB_REGIONS,
  pois: POIS,
  routes: ROUTES,
  breadcrumb: 'GALAXY \u25b8 OUTER RIM \u25b8 TATOOINE \u25b8 DUNE SEA',
  tier_label: '1B \u00b7 WILDERNESS',
  legend_spec: [
    { colorKey: 'cyan',  shape: 'circle', glow: true, label: 'YOU \u00b7 MOISTURE FARM' },
    { colorKey: 'amber', shape: 'circle',            label: 'POINT OF INTEREST' },
    { colorKey: 'red',   shape: 'tri',               label: 'HOSTILE / HAZARD' },
    { colorKey: 'gold',  shape: 'circle',            label: 'LANDMARK' }
  ]
};

// ════════════════════════════════════════════════════════════════════
// CORUSCANT UNDERWORLD — second wilderness region (parity with Tatooine).
//
// Faithful to the gameplay data: POI names mirror the real landmarks in
// data/worlds/clone_wars/wilderness/coruscant_underworld_landmarks.yaml
// (Transit Shaft, Uscru Fringe, Black Sun Crawler Hideout, The Reaper's
// Maze, Abandoned Factory Dominus, Surface Manhole) and sub-region names
// mirror the region's terrain ids (ferrocrete_corridor, abandoned_plaza,
// industrial_ruin, service_tunnel, bottom_dark).
//
// SINGLE-LEVEL per Brian's 2026-05-24 call (re-confirmed 2026-05-31): the
// mechanical grid is one flat 40×40; the *descent* (1313 → sublevels →
// bottom dark) is conveyed by art/prose only — a dark top→bottom depth
// gradient, flattened strata ridges, and a "THE BOTTOM DARK" floor blob —
// NOT by a z-layer affordance. Flavour brief is Nar Shaddaa (smog, strata,
// verticality), NOT Dune Sea. Palette-agnostic fills (cool greys / near
// black) so the region reads correctly under any planet palette.
//
// B3 era-cleanness: zero Empire/Imperial/TIE/Rebel refs. "Black Sun" and
// "Uscru" are Clone-Wars-era canonical and already present in the region
// YAML; no canonical-restricted *individuals* appear (Q1 policy).
var CORUSCANT_UNDERWORLD = {
  name: 'CORUSCANT UNDERWORLD',
  biome: 'GALACTIC CORE \u00b7 UNDERLEVELS',
  // NOTE (Drop 4.17): the LIVE Tier-1b map uses the generated faithful
  // region data (m3_wilderness_overview_data.js), where substrate_image
  // auto-engages once static/maps/coruscant_underworld_substrate.png exists
  // at generation time. This fixture is now only a showcase/test fallback;
  // do not hand-wire a substrate here — re-run gen_wilderness_overview.py.
  bounds: { x_min: 0, y_min: 0, x_max: 700, y_max: 600 },
  bg: '#070809',
  ridge_count: 6,            // flattened architectural strata, not dunes
  ridge_color: 'inkDim',
  ground_stops: [            // descent: faint upper-level light → bottom dark
    { offset: '0%',   color: '#2a2f3a', opacity: 0.55 },
    { offset: '45%',  color: '#15171d' },
    { offset: '100%', color: '#070809' }
  ],
  sub_regions: [
    { d: 'M 80 120 Q 240 90 380 140 Q 360 230 240 250 Q 120 240 80 160 Z',
      name: 'FERROCRETE WARRENS', fill: '#1c2129', opacity: 0.88,
      lx: 230, ly: 175, color: 'inkBright' },
    { d: 'M 400 110 Q 540 90 620 160 Q 600 240 500 250 Q 410 230 400 150 Z',
      name: 'ABANDONED PLAZA',    fill: '#23262e', opacity: 0.85,
      lx: 510, ly: 180, color: 'inkBright' },
    { d: 'M 120 280 Q 250 260 330 310 Q 310 400 200 410 Q 110 380 120 310 Z',
      name: 'INDUSTRIAL RUIN',    fill: '#2a2230', opacity: 0.86,
      lx: 220, ly: 340, color: 'red', hazard: true },
    { d: 'M 380 290 Q 520 270 600 330 Q 580 420 470 430 Q 380 400 380 330 Z',
      name: 'SERVICE TUNNELS',    fill: '#171a20', opacity: 0.82,
      lx: 490, ly: 360, color: 'inkBright' },
    { d: 'M 200 440 Q 360 420 480 470 Q 460 560 320 570 Q 200 540 200 480 Z',
      name: 'THE BOTTOM DARK',    fill: '#0b0d12', opacity: 0.92,
      lx: 340, ly: 505, color: 'gold', hazard: true }
  ],
  pois: [
    { x: 180, y: 175, name: 'TRANSIT SHAFT',     player: true,  size: 9 },
    { x: 500, y: 175, name: 'BLACK SUN HIDEOUT',  hostile: true, size: 8 },
    { x: 220, y: 340, name: "REAPER'S MAZE",      hazard: true,  size: 9 },
    { x: 510, y: 360, name: 'FACTORY DOMINUS',                   size: 7 },
    { x: 340, y: 505, name: 'SURFACE MANHOLE',                   size: 6 },
    { x: 320, y: 250, name: 'USCRU FRINGE',                      size: 7 }
  ],
  routes: [
    [[180, 175], [320, 250], false],   // transit shaft → uscru fringe
    [[320, 250], [510, 360], true],    // uscru fringe → factory dominus (rough)
    [[180, 175], [220, 340], true],    // transit shaft → reaper's maze (caution)
    [[510, 360], [500, 175], false]    // factory dominus → black sun hideout
  ],
  breadcrumb: 'GALAXY \u25b8 CORE \u25b8 CORUSCANT \u25b8 UNDERWORLD',
  tier_label: '1B \u00b7 WILDERNESS',
  legend_spec: [
    { colorKey: 'cyan',  shape: 'circle', glow: true, label: 'YOU \u00b7 TRANSIT SHAFT' },
    { colorKey: 'amber', shape: 'circle',            label: 'POINT OF INTEREST' },
    { colorKey: 'red',   shape: 'tri',               label: 'HOSTILE / HAZARD' },
    { colorKey: 'gold',  shape: 'circle',            label: 'LANDMARK' }
  ]
};

// Region registry + resolver. Keyed by region slug (lower-cased). The
// region YAML's `region.slug` values map here (tatooine_dune_sea,
// coruscant_underworld); short aliases are accepted too. resolveRegion
// returns null on a miss so the builder can fall back to DUNE_SEA loudly.
var REGIONS = {
  dune_sea:              DUNE_SEA,
  tatooine_dune_sea:     DUNE_SEA,
  coruscant_underworld:  CORUSCANT_UNDERWORLD
};

function resolveRegion(key) {
  if (!key) return null;
  var k = String(key).toLowerCase();
  // Drop 4.17: prefer FAITHFUL overview data generated from the navigable
  // grid (tools/gen_wilderness_overview.py → m3_wilderness_overview_data.js,
  // loaded before this module). It projects the real landmark coordinates,
  // so the Tier-1b map matches where things actually are. The built-in
  // DUNE_SEA / CORUSCANT_UNDERWORLD objects below remain only as a showcase
  // fallback (and for bare buildTierOneBBody(p) byte-stability + tests).
  var gen = (typeof window !== 'undefined' && window.M3WildernessOverviewData)
            || (typeof M3WildernessOverviewData !== 'undefined'
                ? M3WildernessOverviewData : null);
  if (gen && gen[k]) return gen[k];
  return REGIONS[k] || null;
}

// ════════════════════════════════════════════════════════════════════
// buildTierOneBBody(p, opts?) → <svg>
//
// Signature compatible with the getTierRenderer DI seam:
//   hooks.getTierRenderer('1b', { p, width, height, time }) → element
// ════════════════════════════════════════════════════════════════════
function buildTierOneBBody(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierOneBBody: palette argument required');

  var width  = opts.width  || 700;
  var height = opts.height || 600;
  var time   = opts.time   || 'day';

  // Region selection (Drop 4.15a). A region object via opts.region wins;
  // else resolve opts.regionKey against REGIONS; else fall back to the
  // Dune Sea fixture (loud-substitution — a bare buildTierOneBBody(p) is
  // byte-stable with the pre-4.15a renderer).
  var region = opts.region || resolveRegion(opts.regionKey) || DUNE_SEA;
  var subRegions = (region && region.sub_regions) || SUB_REGIONS;
  var pois       = (region && region.pois)        || POIS;
  var routes     = (region && region.routes)      || ROUTES;
  var regionName = (region && region.name)        || 'DUNE SEA';
  var regionSub  = (region && region.biome)       || 'TATOOINE \u00b7 OUTER RIM \u00b7 ARID';

  // Substrate-first (mirrors L_SubstrateImage in m3_composition_engine.js):
  // when the region carries a painted raster, paint it over the bounds and
  // skip the procedural ground/dune/terrain-blob decoration; the POI,
  // route and label layers stay ON TOP so the overview remains navigable.
  // Unpainted regions fall through to the procedural sand-/terrain-plate.
  var substrate = (region && region.substrate_image) || opts.substrate_image || null;

  // Decoration knobs (desert defaults; underworld supplies cooler values).
  var bgFill     = (region && region.bg) || null;          // resolved post-fallback below
  var ridgeCount = (region && region.ridge_count != null) ? region.ridge_count : 9;
  var ridgeColor = (region && region.ridge_color) || null;
  var groundStops = (region && region.ground_stops) || null;

  // Loud-substitution fallbacks for undocumented palette keys.
  var paper        = p.paper        || p.inkBright;
  var ground       = p.ground       || p.amber;
  var groundDeep   = p.groundDeep   || p.skyDeep;
  var groundShadow = p.groundShadow || p.skyDeep;

  // Defensive DI for overlay helpers.
  var overlays = (typeof window !== 'undefined' && window.M3AssetsOverlays) || {};
  var TerrainDefs = overlays.TerrainDefs;
  var HazeDefs    = overlays.HazeDefs;
  var OV_TimeOfDay = overlays.OV_TimeOfDay;
  var OV_SandHaze  = overlays.OV_SandHaze;

  // Defensive DI for CompassRose.
  var compEng = (typeof window !== 'undefined' && window.M3CompositionEngine) || {};
  var CompassRose = compEng.CompassRose;

  var children = [];

  // Terrain + haze defs (optional — skip if unavailable).
  if (TerrainDefs) {
    try { children.push(TerrainDefs(p)); } catch (e) { /* skip */ }
  }
  if (HazeDefs) {
    try { children.push(HazeDefs(p)); } catch (e) { /* skip */ }
  }

  // Local defs: sand body gradient + heat-shimmer band + hazard glow.
  // The body gradient stops are region-tunable (ground_stops); the desert
  // default reproduces the original sand radial exactly.
  var bodyStops = groundStops || [
    { offset: '0%',   color: paper,      opacity: 0.6 },
    { offset: '45%',  color: ground },
    { offset: '100%', color: groundDeep }
  ];
  var bodyStopEls = [];
  for (var bs = 0; bs < bodyStops.length; bs++) {
    var st = bodyStops[bs];
    var stAttrs = { offset: st.offset, stopColor: st.color };
    if (st.opacity != null) stAttrs.stopOpacity = st.opacity;
    bodyStopEls.push(svgEl('stop', stAttrs));
  }
  var defs = svgEl('defs', null, [
    svgEl('radialGradient', { id: 'sand-body', cx: '45%', cy: '30%', r: '80%' },
      bodyStopEls),
    svgEl('linearGradient', { id: 'heat-shimmer', x1: '0%', y1: '0%', x2: '0%', y2: '100%' }, [
      svgEl('stop', { offset: '0%',   stopColor: ground,       stopOpacity: 0 }),
      svgEl('stop', { offset: '100%', stopColor: p.inkBright,  stopOpacity: 0.10 })
    ]),
    svgEl('radialGradient', { id: 'hazard-glow', cx: '50%', cy: '50%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   stopColor: p.red, stopOpacity: 0.40 }),
      svgEl('stop', { offset: '100%', stopColor: p.red, stopOpacity: 0 })
    ])
  ]);
  children.push(defs);

  if (substrate) {
    // Painted region: drop the procedural plate + ridges; paint the raster.
    children.push(svgEl('image', {
      'data-layer': 'substrate',
      href: substrate,
      x: 0, y: 0, width: width, height: height,
      preserveAspectRatio: 'none'
    }));
  } else {
    // Procedural ground fill.
    children.push(svgEl('rect', {
      x: 0, y: 0, width: width, height: height, fill: 'url(#sand-body)'
    }));

    // Background ridge polylines (deterministic parallax swells). Desert =
    // 9 rolling dunes; underworld supplies fewer/flatter strata via
    // ridge_count + ridge_color.
    var ridgeStroke = ridgeColor ? (p[ridgeColor] || ridgeColor) : null;
    var duneGroup = [];
    for (var r = 0; r < ridgeCount; r++) {
      var baseY = 60 + r * (height / Math.max(ridgeCount + 1, 2));
      var pts = [];
      for (var x = 0; x <= 700; x += 70) {
        var wobble = Math.sin((x / 700) * Math.PI * 2 + r) * (8 + r);
        pts.push(x + ',' + (baseY + wobble).toFixed(1));
      }
      duneGroup.push(svgEl('polyline', {
        points: pts.join(' '), fill: 'none',
        stroke: ridgeStroke || (r % 2 === 0 ? groundShadow : p.inkDim),
        strokeWidth: 1, strokeOpacity: 0.25 + (r % 3) * 0.05
      }));
    }
    children.push(svgEl('g', { 'data-layer': 'dunes' }, duneGroup));
  }

  // Sub-region terrain blobs (skipped under a painted substrate — the
  // painting carries the terrain). Each blob may specify a solid `fill`
  // (palette-agnostic) or a `terrainId` gradient ref.
  if (!substrate) {
    var srGroup = [];
    for (var s = 0; s < subRegions.length; s++) {
      var sr = subRegions[s];
      srGroup.push(svgEl('path', {
        'data-subregion': sr.name,
        'data-subregion-hazard': sr.hazard ? '1' : null,
        d: sr.d, fill: sr.fill || sr.terrainId, fillOpacity: sr.opacity,
        stroke: sr.hazard ? p.red : p.ink, strokeWidth: 1,
        strokeOpacity: sr.hazard ? 0.7 : 0.45,
        strokeDasharray: sr.hazard ? '4 3' : null
      }));
      var srColor = (p[sr.color] || p.inkBright);
      srGroup.push(svgEl('text', {
        x: sr.lx, y: sr.ly, textAnchor: 'middle',
        fill: srColor, fontSize: 10, letterSpacing: 1.5,
        fontFamily: "'IBM Plex Mono', monospace", opacity: 0.9
      }, [sr.name]));
    }
    children.push(svgEl('g', { 'data-layer': 'subregions' }, srGroup));
  }

  // Routes (footpaths / skiff tracks) drawn under POIs.
  var routeGroup = [];
  for (var rt = 0; rt < routes.length; rt++) {
    var rr = routes[rt];
    routeGroup.push(svgEl('line', {
      x1: rr[0][0], y1: rr[0][1], x2: rr[1][0], y2: rr[1][1],
      stroke: p.inkDim, strokeWidth: 1.5, strokeOpacity: 0.55,
      strokeDasharray: rr[2] ? '6 4' : null, strokeLinecap: 'round'
    }));
  }
  children.push(svgEl('g', { 'data-layer': 'routes' }, routeGroup));

  // Hazard glows under hazard POIs.
  var hazardGroup = [];
  for (var hp = 0; hp < pois.length; hp++) {
    if (pois[hp].hazard) {
      hazardGroup.push(svgEl('circle', {
        cx: pois[hp].x, cy: pois[hp].y, r: 26, fill: 'url(#hazard-glow)'
      }));
    }
  }
  children.push(svgEl('g', { 'data-layer': 'hazard-glow' }, hazardGroup));

  // POI glyphs + labels.
  var poiGroup = [];
  for (var i = 0; i < pois.length; i++) {
    var poi = pois[i];
    var glyphColor = poi.player ? p.cyan
                   : poi.hostile ? p.red
                   : poi.hazard ? p.red
                   : p.amber;
    if (poi.player) {
      poiGroup.push(svgEl('circle', {
        cx: poi.x, cy: poi.y, r: poi.size + 4, fill: 'none',
        stroke: p.cyan, strokeWidth: 1.5, strokeOpacity: 0.5
      }));
    }
    if (poi.hostile) {
      // Hostile POIs use a triangle glyph.
      var t = poi.size;
      poiGroup.push(svgEl('path', {
        'data-poi': poi.name,
        'data-poi-hostile': '1',
        d: 'M ' + poi.x + ' ' + (poi.y - t) +
           ' L ' + (poi.x + t) + ' ' + (poi.y + t) +
           ' L ' + (poi.x - t) + ' ' + (poi.y + t) + ' Z',
        fill: glyphColor, stroke: p.ink, strokeWidth: 0.75
      }));
    } else {
      poiGroup.push(svgEl('circle', {
        'data-poi': poi.name,
        'data-poi-player': poi.player ? '1' : null,
        'data-poi-hazard': poi.hazard ? '1' : null,
        cx: poi.x, cy: poi.y, r: poi.size / 2,
        fill: glyphColor, stroke: p.ink, strokeWidth: 0.75
      }));
    }
    poiGroup.push(svgEl('text', {
      x: poi.x, y: poi.y - poi.size - 2, textAnchor: 'middle',
      fill: glyphColor, fontSize: 9, letterSpacing: 1,
      fontFamily: "'IBM Plex Mono', monospace"
    }, [poi.name]));
  }
  children.push(svgEl('g', { 'data-layer': 'pois' }, poiGroup));

  // Heat-shimmer band over the lower third.
  children.push(svgEl('rect', {
    x: 0, y: height * 0.6, width: width, height: height * 0.4,
    fill: 'url(#heat-shimmer)'
  }));

  // Sand haze overlay (optional).
  if (OV_SandHaze) {
    try {
      children.push(OV_SandHaze({ p: p, width: width, height: height }));
    } catch (e) { /* skip */ }
  }

  // Time-of-day overlay (optional).
  if (OV_TimeOfDay) {
    try {
      var tod = OV_TimeOfDay({ time: time, width: width, height: height });
      if (tod) children.push(tod);
    } catch (e) { /* skip */ }
  }

  // Compass rose (optional decoration).
  if (CompassRose) {
    try {
      children.push(CompassRose({ p: p, x: width - 60, y: height - 60 }));
    } catch (e) { /* skip */ }
  }

  // Scale bar (local).
  children.push(_scaleBar(p, 28, height - 30));

  // Region name + biome subtitle.
  children.push(svgEl('text', {
    x: 28, y: 40, fill: p.inkBright, fontSize: 20, letterSpacing: 3,
    fontFamily: "'IBM Plex Mono', monospace"
  }, [regionName]));
  children.push(svgEl('text', {
    x: 28, y: 58, fill: p.inkDim, fontSize: 10, letterSpacing: 2,
    fontFamily: "'IBM Plex Mono', monospace"
  }, [regionSub]));

  return svgEl('svg', {
    'data-tier-wilderness': '1',
    width: width, height: height,
    viewBox: '0 0 ' + width + ' ' + height,
    preserveAspectRatio: 'xMidYMid meet',
    style: { display: 'block', background: bgFill || groundDeep }
  }, children);
}

// Local scale-bar glyph (mirrors the city module's; kept per-module so
// each inner tier renders standalone in the showcase/tests).
function _scaleBar(p, x, y) {
  return svgEl('g', { 'data-layer': 'scalebar' }, [
    svgEl('line', { x1: x, y1: y, x2: x + 60, y2: y,
                    stroke: p.inkDim, strokeWidth: 2 }),
    svgEl('line', { x1: x, y1: y - 4, x2: x, y2: y + 4,
                    stroke: p.inkDim, strokeWidth: 2 }),
    svgEl('line', { x1: x + 60, y1: y - 4, x2: x + 60, y2: y + 4,
                    stroke: p.inkDim, strokeWidth: 2 }),
    svgEl('text', { x: x + 30, y: y - 8, textAnchor: 'middle',
                    fill: p.inkDim, fontSize: 8, letterSpacing: 1,
                    fontFamily: "'IBM Plex Mono', monospace" }, ['2 km'])
  ]);
}

// ════════════════════════════════════════════════════════════════════
// buildTierOneBRegion(p, opts?) → <div>  (chrome-wrapped, region-driven)
//
// opts.region (object) wins; else opts.regionKey is resolved; else the
// Dune Sea fixture. Breadcrumb / tier label / legend come from the region
// descriptor (loud-substitution to the Dune Sea values when absent).
// ════════════════════════════════════════════════════════════════════
function buildTierOneBRegion(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierOneBRegion: palette argument required');

  var width  = opts.width  || 700;
  var height = opts.height || 600;
  var time   = opts.time   || 'day';

  var region = opts.region || resolveRegion(opts.regionKey) || DUNE_SEA;

  var compEng = (typeof window !== 'undefined' && window.M3CompositionEngine) || {};
  var HolocartaFrame = compEng.HolocartaFrame;

  var innerSvg = buildTierOneBBody(p, {
    width: width, height: height, time: time, region: region
  });

  if (!HolocartaFrame) {
    return htmlEl('div', {
      'data-tier-wilderness-frame-fallback': '1',
      style: {
        position: 'relative', width: width, height: height + 64,
        background: p.skyDeep, color: p.inkDim,
        fontSize: 9, letterSpacing: 2,
        fontFamily: "'IBM Plex Mono', monospace"
      }
    }, [
      htmlEl('div', {
        style: { padding: '4px 8px', borderBottom: '1px solid ' + p.inkDim }
      }, ['HOLOCARTA FRAME \u00b7 M3CompositionEngine.HolocartaFrame not loaded']),
      innerSvg
    ]);
  }

  // Resolve the legend spec (palette-key → color) with a Dune Sea default.
  var legendSpec = (region && region.legend_spec) || DUNE_SEA.legend_spec;
  var legend = [];
  for (var li = 0; li < legendSpec.length; li++) {
    var ls = legendSpec[li];
    var entry = { color: (p[ls.colorKey] || p.inkBright), shape: ls.shape, label: ls.label };
    if (ls.glow) entry.glow = true;
    legend.push(entry);
  }

  return HolocartaFrame({
    p: p,
    width: width,
    height: height + 64,
    breadcrumb: (region && region.breadcrumb) || DUNE_SEA.breadcrumb,
    tier: (region && region.tier_label) || DUNE_SEA.tier_label,
    legend: legend,
    children: [innerSvg]
  });
}

// ════════════════════════════════════════════════════════════════════
// Back-compat / convenience chrome wrappers.
//   buildTierOneBDuneSea     — original Drop 4.14 entry point (Dune Sea)
//   buildTierOneBUnderworld  — Coruscant Underworld
// Both delegate to buildTierOneBRegion with their region pinned (an
// explicit opts.region still overrides, for showcase/test flexibility).
// ════════════════════════════════════════════════════════════════════
function buildTierOneBDuneSea(p, opts) {
  opts = opts || {};
  return buildTierOneBRegion(p, {
    p: opts.p, width: opts.width, height: opts.height, time: opts.time,
    region: opts.region || DUNE_SEA
  });
}

function buildTierOneBUnderworld(p, opts) {
  opts = opts || {};
  return buildTierOneBRegion(p, {
    p: opts.p, width: opts.width, height: opts.height, time: opts.time,
    region: opts.region || CORUSCANT_UNDERWORLD
  });
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3TierWildernessBody = {
  SCHEMA_VERSION: 1,

  // Top-level
  buildTierOneBBody:       buildTierOneBBody,
  buildTierOneBRegion:     buildTierOneBRegion,
  buildTierOneBDuneSea:    buildTierOneBDuneSea,
  buildTierOneBUnderworld: buildTierOneBUnderworld,

  // Region registry / resolver
  REGIONS:        REGIONS,
  resolveRegion:  resolveRegion,

  // Fixtures (public for downstream composition / Q1 audits)
  DUNE_SEA:             DUNE_SEA,
  CORUSCANT_UNDERWORLD: CORUSCANT_UNDERWORLD,
  SUB_REGIONS:  SUB_REGIONS,
  POIS:         POIS,
  ROUTES:       ROUTES,

  _internal: { _svgEl: svgEl, _htmlEl: htmlEl, _scaleBar: _scaleBar }
};

})();
