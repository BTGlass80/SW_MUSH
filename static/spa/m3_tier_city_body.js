/* ============================================================================
   m3_tier_city_body.js — Tier 2 City renderer (Mos Eisley overview).

   Drop 4.14 (Batch 2, inner-tier triplet) · Tier 1 #4 · ported from
   map_v3/tier-two.jsx (~135 JSX LOC) using the established outer-tier
   idiom from Drop 4.13's m3_tier_planet_body.js.

   This is the city-scale zoom of the SPA map navigator's tier ladder —
   the Mos Eisley overview sitting between the planet view (Tier 3) and
   the district view (Tier 1a). Stylized top-down city plate with:
     · Ground atmosphere fill (via L_Atmosphere from M3CompositionEngine)
     · 6 district blocks as terrain-tinted rounded rects (Spaceport,
       Old Quarter, Merchant Row, Outer Sprawl, Cantina Row, Docking Bays)
     · Street grid drawn from a deterministic lattice
     · 8 building-cluster glyphs sized by district
     · Player marker over the Cantina Row (Chalmun's)
     · Hyperspace beacon pulsing at the Spaceport
     · 5 named landmarks with leader-dot glyphs
     · Compass rose (via CompassRose from M3CompositionEngine)
     · Scale bar
     · City name + district subtitle

   What this module ships:
     · M3TierCityBody.buildTierTwoBody(p, opts?)
            inner SVG renderer; signature compatible with the
            getTierRenderer DI seam in M3MapNavigator (Drop 4.8) and
            M3AssembledClient.MiniMap (Drop 4.12b). Returns <svg>.
     · M3TierCityBody.buildTierTwoMosEisley(p, opts?)
            chrome'd version using HolocartaFrame from
            M3CompositionEngine. Returns the frame's outer HTMLDivElement
            (or a labeled fallback if HolocartaFrame is unavailable).
     · M3TierCityBody.DISTRICTS      6-district fixture array
     · M3TierCityBody.LANDMARKS      5-landmark fixture array
     · M3TierCityBody.BUILDINGS      8-building-cluster fixture array

   B3 era-cleanness:
     · Era subtitle "MOS EISLEY · ARKANIS SECTOR · 20 BBY"
     · All district/landmark names are Tatooine-canonical (era-neutral).
     · Zero Empire/Imperial/TIE/X-wing/Rebel/Stormtrooper/Vader/Death
       Star/ISB references in data blocks.

   Q1 canonical-character policy note (architecture v50 §6.2):
     · "CHALMUN'S CANTINA" — canonical-character-adjacent landmark name
       (Chalmun the Wookiee owner), preserved verbatim per Drop 4.6 /
       4.7 / 4.10 / 4.11 / 4.12 / 4.13 source-fidelity policy. Tracked
       in the Q1 cleanup queue.
     · "DOCKING BAY 94" — canonical landmark, preserved per same policy.

   Palette keys consumed:
     p.amber, p.cyan, p.green, p.gold, p.red, p.ink, p.inkBright,
     p.inkDim, p.skyDeep
     · p.paper        — UNDOCUMENTED key from JSX source. Fallback to
                        p.inkBright per Drop 4.11 loud-substitution.
     · p.ground       — UNDOCUMENTED. Fallback to p.amber.
     · p.groundDeep   — UNDOCUMENTED. Fallback to p.skyDeep.
     (Standard palettes lacking these keys still render the city body —
     the district fills just degrade to amber/skyDeep transitions.)

   Dependencies (consumed via defensive DI):
     · window.M3CompositionEngine.HolocartaFrame
            used by buildTierTwoMosEisley. If unavailable, the chrome'd
            version returns a labeled placeholder.
     · window.M3CompositionEngine.CompassRose
            optional decoration. If unavailable, skipped silently.
     · window.M3CompositionEngine.L_Atmosphere
            optional ground fill. If unavailable, a plain ground rect
            is drawn in its place.
     · window.M3AssetsOverlays.TerrainDefs / HazeDefs / OV_TimeOfDay
            optional. If unavailable, the relevant <defs>/overlays are
            skipped — district rects render as solid color.

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
// FIXTURES — JSX source data preserved verbatim
// ════════════════════════════════════════════════════════════════════
var DISTRICTS = [
  // {x, y, w, h, name, terrainId, opacity, labelSize}
  { x: 120, y: 90,  w: 200, h: 150, name: 'SPACEPORT',     terrainId: 'url(#terr-dune)',  opacity: 0.82, labelSize: 11 },
  { x: 340, y: 110, w: 180, h: 140, name: 'OLD QUARTER',   terrainId: 'url(#terr-scrub)', opacity: 0.80, labelSize: 11 },
  { x: 130, y: 260, w: 170, h: 150, name: 'MERCHANT ROW',  terrainId: 'url(#terr-dune)',  opacity: 0.78, labelSize: 10 },
  { x: 330, y: 270, w: 200, h: 160, name: 'OUTER SPRAWL',  terrainId: 'url(#terr-scrub)', opacity: 0.72, labelSize: 10 },
  { x: 200, y: 430, w: 180, h: 130, name: 'CANTINA ROW',   terrainId: 'url(#terr-dune)',  opacity: 0.85, labelSize: 11 },
  { x: 400, y: 450, w: 150, h: 120, name: 'DOCKING BAYS',  terrainId: 'url(#terr-canyon)',opacity: 0.80, labelSize: 10 }
];

var LANDMARKS = [
  // Q1 watch: "CHALMUN'S CANTINA" and "DOCKING BAY 94" preserved per
  // source-fidelity policy. See module header.
  { x: 290, y: 495, name: "CHALMUN'S CANTINA", player: true,  size: 9 },
  { x: 220, y: 165, name: 'CONTROL TOWER',     beacon: true,  size: 8 },
  { x: 470, y: 510, name: 'DOCKING BAY 94',    landmark: true, size: 8 },
  { x: 420, y: 180, name: 'GRAND BAZAAR',      size: 7 },
  { x: 210, y: 330, name: 'WATER MERCHANT',    size: 6 }
];

var BUILDINGS = [
  // [cx, cy, size] — building-cluster glyphs sized by district density
  [180, 150, 14], [260, 175, 11], [400, 160, 13], [470, 200, 10],
  [200, 320, 12], [410, 330, 14], [270, 480, 11], [460, 500, 12]
];

// Deterministic street lattice — [[x1,y1],[x2,y2]] segments.
var STREETS = [
  [[100, 220], [560, 230]],   // main east-west arterial
  [[110, 410], [550, 415]],   // southern arterial
  [[230, 80],  [240, 580]],   // western spine
  [[420, 90],  [430, 580]],   // eastern spine
  [[330, 100], [340, 590]]    // central spine
];

// ════════════════════════════════════════════════════════════════════
// buildTierTwoBody(p, opts?) → <svg>
//
// Signature compatible with the getTierRenderer DI seam:
//   hooks.getTierRenderer('2', { p, width, height, time }) → element
// ════════════════════════════════════════════════════════════════════
function buildTierTwoBody(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierTwoBody: palette argument required');

  var width  = opts.width  || 700;
  var height = opts.height || 700;
  var time   = opts.time   || 'day';

  // Loud-substitution fallbacks for undocumented palette keys.
  var paper      = p.paper      || p.inkBright;
  var ground     = p.ground     || p.amber;
  var groundDeep = p.groundDeep || p.skyDeep;

  // Defensive DI for overlay helpers.
  var overlays = (typeof window !== 'undefined' && window.M3AssetsOverlays) || {};
  var TerrainDefs = overlays.TerrainDefs;
  var HazeDefs    = overlays.HazeDefs;
  var OV_TimeOfDay = overlays.OV_TimeOfDay;

  // Defensive DI for composition-engine helpers.
  var compEng = (typeof window !== 'undefined' && window.M3CompositionEngine) || {};
  var CompassRose  = compEng.CompassRose;
  var L_Atmosphere = compEng.L_Atmosphere;

  var children = [];

  // Terrain + haze defs (optional — skip if unavailable).
  if (TerrainDefs) {
    try { children.push(TerrainDefs(p)); } catch (e) { /* skip */ }
  }
  if (HazeDefs) {
    try { children.push(HazeDefs(p)); } catch (e) { /* skip */ }
  }

  // Local defs: city ground gradient + beacon pulse glow.
  var defs = svgEl('defs', null, [
    svgEl('radialGradient', { id: 'city-ground', cx: '50%', cy: '40%', r: '70%' }, [
      svgEl('stop', { offset: '0%',   stopColor: ground }),
      svgEl('stop', { offset: '100%', stopColor: groundDeep })
    ]),
    svgEl('radialGradient', { id: 'beacon-glow', cx: '50%', cy: '50%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   stopColor: p.green, stopOpacity: 0.55 }),
      svgEl('stop', { offset: '100%', stopColor: p.green, stopOpacity: 0 })
    ])
  ]);
  children.push(defs);

  // Ground fill — prefer L_Atmosphere; fall back to a plain rect.
  if (L_Atmosphere) {
    try {
      children.push(L_Atmosphere({ p: p, width: width, height: height }));
    } catch (e) {
      children.push(svgEl('rect', {
        x: 0, y: 0, width: width, height: height, fill: 'url(#city-ground)'
      }));
    }
  } else {
    children.push(svgEl('rect', {
      x: 0, y: 0, width: width, height: height, fill: 'url(#city-ground)'
    }));
  }

  // Street grid (drawn under districts so blocks sit on top).
  var streetGroup = [];
  for (var s = 0; s < STREETS.length; s++) {
    var seg = STREETS[s];
    streetGroup.push(svgEl('line', {
      x1: seg[0][0], y1: seg[0][1], x2: seg[1][0], y2: seg[1][1],
      stroke: p.inkDim, strokeWidth: 3, strokeOpacity: 0.45,
      strokeLinecap: 'round'
    }));
  }
  children.push(svgEl('g', { 'data-layer': 'streets' }, streetGroup));

  // District blocks.
  var districtGroup = [];
  for (var d = 0; d < DISTRICTS.length; d++) {
    var dd = DISTRICTS[d];
    districtGroup.push(svgEl('rect', {
      'data-district': dd.name,
      x: dd.x, y: dd.y, width: dd.w, height: dd.h, rx: 8,
      fill: dd.terrainId, fillOpacity: dd.opacity,
      stroke: p.ink, strokeWidth: 1, strokeOpacity: 0.5
    }));
    districtGroup.push(svgEl('text', {
      x: dd.x + dd.w / 2, y: dd.y + 16, textAnchor: 'middle',
      fill: p.inkBright, fontSize: dd.labelSize, letterSpacing: 1.5,
      fontFamily: "'IBM Plex Mono', monospace", opacity: 0.85
    }, [dd.name]));
  }
  children.push(svgEl('g', { 'data-layer': 'districts' }, districtGroup));

  // Building clusters.
  var bGroup = [];
  for (var b = 0; b < BUILDINGS.length; b++) {
    var bx = BUILDINGS[b][0], by = BUILDINGS[b][1], bs = BUILDINGS[b][2];
    bGroup.push(svgEl('rect', {
      x: bx - bs / 2, y: by - bs / 2, width: bs, height: bs, rx: 2,
      fill: paper, fillOpacity: 0.30,
      stroke: p.inkBright, strokeWidth: 0.75, strokeOpacity: 0.6
    }));
  }
  children.push(svgEl('g', { 'data-layer': 'buildings' }, bGroup));

  // Beacon glow + pulse at the Control Tower.
  var beaconLm = null;
  for (var li = 0; li < LANDMARKS.length; li++) {
    if (LANDMARKS[li].beacon) { beaconLm = LANDMARKS[li]; break; }
  }
  if (beaconLm) {
    children.push(svgEl('circle', {
      cx: beaconLm.x, cy: beaconLm.y, r: 30, fill: 'url(#beacon-glow)'
    }, []));
    var pulse = svgEl('circle', {
      cx: beaconLm.x, cy: beaconLm.y, r: 6, fill: 'none',
      stroke: p.green, strokeWidth: 1.5
    }, [
      svgEl('animate', {
        attributeName: 'r', values: '6;26;6', dur: '2.4s',
        repeatCount: 'indefinite'
      }),
      svgEl('animate', {
        attributeName: 'stroke-opacity', values: '0.9;0;0.9', dur: '2.4s',
        repeatCount: 'indefinite'
      })
    ]);
    children.push(pulse);
  }

  // Landmark glyphs + labels.
  var lmGroup = [];
  for (var l = 0; l < LANDMARKS.length; l++) {
    var lm = LANDMARKS[l];
    var glyphColor = lm.player ? p.cyan
                   : lm.beacon ? p.green
                   : lm.landmark ? p.gold
                   : p.amber;
    if (lm.player) {
      // Player marker: glowing ring + dot.
      lmGroup.push(svgEl('circle', {
        cx: lm.x, cy: lm.y, r: lm.size + 4, fill: 'none',
        stroke: p.cyan, strokeWidth: 1.5, strokeOpacity: 0.5
      }));
    }
    lmGroup.push(svgEl('circle', {
      'data-landmark': lm.name,
      'data-landmark-player': lm.player ? '1' : null,
      'data-landmark-beacon': lm.beacon ? '1' : null,
      'data-landmark-kind': lm.landmark ? '1' : null,
      cx: lm.x, cy: lm.y, r: lm.size / 2,
      fill: glyphColor, stroke: p.ink, strokeWidth: 0.75
    }));
    lmGroup.push(svgEl('text', {
      x: lm.x, y: lm.y - lm.size, textAnchor: 'middle',
      fill: glyphColor, fontSize: 9, letterSpacing: 1,
      fontFamily: "'IBM Plex Mono', monospace"
    }, [lm.name]));
  }
  children.push(svgEl('g', { 'data-layer': 'landmarks' }, lmGroup));

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

  // Scale bar (local — independent of composition engine).
  children.push(_scaleBar(p, 28, height - 36));

  // City name + subtitle.
  children.push(svgEl('text', {
    x: 28, y: 40, fill: p.inkBright, fontSize: 20, letterSpacing: 3,
    fontFamily: "'IBM Plex Mono', monospace"
  }, ['MOS EISLEY']));
  children.push(svgEl('text', {
    x: 28, y: 58, fill: p.inkDim, fontSize: 10, letterSpacing: 2,
    fontFamily: "'IBM Plex Mono', monospace"
  }, ['ARKANIS SECTOR \u00b7 20 BBY']));

  return svgEl('svg', {
    'data-tier-city': '1',
    width: width, height: height,
    viewBox: '0 0 ' + width + ' ' + height,
    preserveAspectRatio: 'xMidYMid meet',
    style: { display: 'block', background: groundDeep }
  }, children);
}

// Local scale-bar glyph — mirrors ScaleBar from the composition engine
// without taking a hard dependency on it (the inner-tier modules each
// carry their own so they render standalone in the showcase/tests).
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
                    fontFamily: "'IBM Plex Mono', monospace" }, ['500 m'])
  ]);
}

// ════════════════════════════════════════════════════════════════════
// buildTierTwoMosEisley(p, opts?) → <div>  (chrome-wrapped)
//
// Wraps buildTierTwoBody in HolocartaFrame. Falls back to a labeled
// placeholder div if HolocartaFrame is unavailable.
// ════════════════════════════════════════════════════════════════════
function buildTierTwoMosEisley(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierTwoMosEisley: palette argument required');

  var width  = opts.width  || 700;
  var height = opts.height || 700;
  var time   = opts.time   || 'day';

  var compEng = (typeof window !== 'undefined' && window.M3CompositionEngine) || {};
  var HolocartaFrame = compEng.HolocartaFrame;

  var innerSvg = buildTierTwoBody(p, {
    width: width, height: height, time: time
  });

  if (!HolocartaFrame) {
    return htmlEl('div', {
      'data-tier-city-frame-fallback': '1',
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

  return HolocartaFrame({
    p: p,
    width: width,
    height: height + 64,
    breadcrumb: 'GALAXY \u25b8 OUTER RIM \u25b8 TATOOINE \u25b8 MOS EISLEY',
    tier: '2 \u00b7 CITY',
    legend: [
      { color: p.cyan,  shape: 'circle', glow: true, label: 'YOU \u00b7 CANTINA ROW' },
      { color: p.gold,  shape: 'circle', label: 'LANDMARK' },
      { color: p.amber, shape: 'circle', label: 'POINT OF INTEREST' },
      { color: p.green, shape: 'circle', label: 'BEACON' }
    ],
    children: [innerSvg]
  });
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3TierCityBody = {
  SCHEMA_VERSION: 1,

  // Top-level
  buildTierTwoBody:      buildTierTwoBody,
  buildTierTwoMosEisley: buildTierTwoMosEisley,

  // Fixtures (public for downstream composition / Q1 audits)
  DISTRICTS:  DISTRICTS,
  LANDMARKS:  LANDMARKS,
  BUILDINGS:  BUILDINGS,
  STREETS:    STREETS,

  _internal: { _svgEl: svgEl, _htmlEl: htmlEl, _scaleBar: _scaleBar }
};

})();
