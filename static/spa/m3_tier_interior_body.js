/* ============================================================================
   m3_tier_interior_body.js — Tier 0 Interior renderer (cantina interior).

   Drop 4.14 (Batch 2, inner-tier triplet) · Tier 1 #4 · ported from
   map_v3/tier-zero.jsx (~175 JSX LOC) using the established outer-tier
   idiom from Drop 4.13's m3_tier_planet_body.js. Cantina-specific
   fixtures are defined inline.

   This is the innermost zoom of the SPA map navigator's tier ladder —
   a single-room interior floorplan (Chalmun's Cantina main room). The
   most detailed view: actual furniture footprints, entity dots for
   patrons, and named exits. Stylized top-down floorplan with:
     · Room floor fill + wall outline (rounded-rect shell)
     · 5 furniture footprints (bar counter, 6 booth tables, dais,
       dejarik table, bandstand)
     · 4 named exits as wall-gap glyphs (Front Entrance, Back Hall,
       Bar Storeroom, Booth Alcove)
     · 7 entity dots (player + 6 NPC patrons with faction tints)
     · Floor-grid hatching for scale
     · Room name + occupancy subtitle
     · Compass rose (via CompassRose from M3CompositionEngine)
     · Scale bar (local, metre-scale)

   What this module ships:
     · M3TierInteriorBody.buildTierZeroBody(p, opts?)
            inner SVG renderer; signature compatible with the
            getTierRenderer DI seam in M3MapNavigator (Drop 4.8) and
            M3AssembledClient.MiniMap (Drop 4.12b). Returns <svg>.
            opts may carry { entities } to override the demo patrons.
     · M3TierInteriorBody.buildTierZeroCantina(p, opts?)
            chrome'd version using HolocartaFrame from
            M3CompositionEngine. Returns the frame's outer HTMLDivElement
            (or a labeled fallback if HolocartaFrame is unavailable).
     · M3TierInteriorBody.FURNITURE   5-furniture fixture array
     · M3TierInteriorBody.EXITS       4-exit fixture array
     · M3TierInteriorBody.ENTITIES    7-entity demo fixture array

   B3 era-cleanness:
     · Era subtitle "CHALMUN'S CANTINA \u00b7 MOS EISLEY"
     · All furniture/exit/entity names are era-neutral.
     · Zero Empire/Imperial/TIE/X-wing/Rebel/Stormtrooper/Vader/Death
       Star/ISB references in data blocks.

   Q1 canonical-character policy note (architecture v50 §6.2):
     · "CHALMUN'S CANTINA" — canonical-character-adjacent name (Chalmun
       the Wookiee owner). Preserved verbatim per Drop 4.6 / 4.7 / 4.10 /
       4.11 / 4.12 / 4.13 source-fidelity policy. Tracked in the Q1
       cleanup queue (shared with the Tier 2 city module from this drop).
     · "DEJARIK TABLE" — canonical cantina furnishing (holographic chess),
       preserved per same policy.

   Palette keys consumed:
     p.amber, p.cyan, p.green, p.gold, p.red, p.ink, p.inkBright,
     p.inkDim, p.skyDeep
     · p.paper        — UNDOCUMENTED key from JSX source. Fallback to
                        p.inkBright per Drop 4.11 loud-substitution.
     · p.ground       — UNDOCUMENTED. Fallback to p.amber.
     · p.groundDeep   — UNDOCUMENTED. Fallback to p.skyDeep.
     (Standard palettes lacking these keys still render the interior
     body — the floor fill just degrades to amber/skyDeep.)

   Dependencies (consumed via defensive DI):
     · window.M3CompositionEngine.HolocartaFrame
            used by buildTierZeroCantina. If unavailable, the chrome'd
            version returns a labeled placeholder.
     · window.M3CompositionEngine.CompassRose
            optional decoration. If unavailable, skipped silently.

   Loading order in client.html: AFTER m3_composition_engine.js (so DI
   hooks resolve).
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
// FIXTURES — JSX source data preserved verbatim (inline cantina)
// ════════════════════════════════════════════════════════════════════
// Room shell bounds inside the 700×600 plate (margin gives wall room).
var ROOM = { x: 80, y: 90, w: 540, h: 420 };

var FURNITURE = [
  // Q1 watch: "DEJARIK TABLE" preserved per source-fidelity policy.
  // {x, y, w, h, name, kind, rounded?}
  { x: 110, y: 120, w: 220, h: 46,  name: 'BAR COUNTER',   kind: 'bar' },
  { x: 380, y: 130, w: 90,  h: 90,  name: 'BANDSTAND',     kind: 'stage', rounded: true },
  { x: 360, y: 300, w: 70,  h: 70,  name: 'DEJARIK TABLE', kind: 'game',  rounded: true },
  { x: 110, y: 300, w: 60,  h: 60,  name: 'BOOTH CLUSTER', kind: 'seating', rounded: true },
  { x: 480, y: 380, w: 90,  h: 60,  name: 'RAISED DAIS',   kind: 'dais' }
];

var EXITS = [
  // {x, y, name, side} — gap glyph drawn on the named wall side.
  { x: 350, y: 510, name: 'FRONT ENTRANCE', side: 'south' },
  { x: 80,  y: 200, name: 'BAR STOREROOM',  side: 'west' },
  { x: 620, y: 300, name: 'BACK HALL',      side: 'east' },
  { x: 200, y: 90,  name: 'BOOTH ALCOVE',   side: 'north' }
];

var ENTITIES = [
  // {x, y, name, faction} — faction drives tint: player/friendly/
  // neutral/hostile. Era-neutral labels.
  { x: 260, y: 250, name: 'YOU',        faction: 'player' },
  { x: 300, y: 220, name: 'BARKEEP',    faction: 'neutral' },
  { x: 410, y: 320, name: 'GAMBLER',    faction: 'neutral' },
  { x: 150, y: 330, name: 'INFORMANT',  faction: 'friendly' },
  { x: 500, y: 400, name: 'ENFORCER',   faction: 'hostile' },
  { x: 430, y: 160, name: 'MUSICIAN',   faction: 'friendly' },
  { x: 540, y: 250, name: 'STRANGER',   faction: 'neutral' }
];

// ════════════════════════════════════════════════════════════════════
// buildTierZeroBody(p, opts?) → <svg>
//
// Signature compatible with the getTierRenderer DI seam:
//   hooks.getTierRenderer('0', { p, width, height, entities }) → element
// ════════════════════════════════════════════════════════════════════
function buildTierZeroBody(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierZeroBody: palette argument required');

  var width  = opts.width  || 700;
  var height = opts.height || 600;
  var entities = (opts.entities && opts.entities.length) ? opts.entities : ENTITIES;

  // Loud-substitution fallbacks for undocumented palette keys.
  var paper      = p.paper      || p.inkBright;
  var ground     = p.ground     || p.amber;
  var groundDeep = p.groundDeep || p.skyDeep;

  // Defensive DI for CompassRose.
  var compEng = (typeof window !== 'undefined' && window.M3CompositionEngine) || {};
  var CompassRose = compEng.CompassRose;

  var children = [];

  // Local defs: floor gradient + entity glow.
  children.push(svgEl('defs', null, [
    svgEl('radialGradient', { id: 'floor-body', cx: '50%', cy: '45%', r: '70%' }, [
      svgEl('stop', { offset: '0%',   stopColor: ground,     stopOpacity: 0.5 }),
      svgEl('stop', { offset: '100%', stopColor: groundDeep })
    ]),
    svgEl('radialGradient', { id: 'ent-self-glow', cx: '50%', cy: '50%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   stopColor: p.cyan, stopOpacity: 0.5 }),
      svgEl('stop', { offset: '100%', stopColor: p.cyan, stopOpacity: 0 })
    ])
  ]));

  // Plate background.
  children.push(svgEl('rect', {
    x: 0, y: 0, width: width, height: height, fill: groundDeep
  }));

  // Room floor + wall shell.
  children.push(svgEl('rect', {
    x: ROOM.x, y: ROOM.y, width: ROOM.w, height: ROOM.h, rx: 10,
    fill: 'url(#floor-body)', stroke: p.inkBright, strokeWidth: 2.5
  }));

  // Floor grid hatching for scale (1 cell ≈ 1 metre).
  var gridGroup = [];
  var step = 40;
  for (var gx = ROOM.x + step; gx < ROOM.x + ROOM.w; gx += step) {
    gridGroup.push(svgEl('line', {
      x1: gx, y1: ROOM.y, x2: gx, y2: ROOM.y + ROOM.h,
      stroke: p.inkDim, strokeWidth: 0.5, strokeOpacity: 0.18
    }));
  }
  for (var gy = ROOM.y + step; gy < ROOM.y + ROOM.h; gy += step) {
    gridGroup.push(svgEl('line', {
      x1: ROOM.x, y1: gy, x2: ROOM.x + ROOM.w, y2: gy,
      stroke: p.inkDim, strokeWidth: 0.5, strokeOpacity: 0.18
    }));
  }
  children.push(svgEl('g', { 'data-layer': 'floor-grid' }, gridGroup));

  // Furniture footprints.
  var furnGroup = [];
  for (var f = 0; f < FURNITURE.length; f++) {
    var ff = FURNITURE[f];
    furnGroup.push(svgEl('rect', {
      'data-furniture': ff.name,
      'data-furniture-kind': ff.kind,
      x: ff.x, y: ff.y, width: ff.w, height: ff.h,
      rx: ff.rounded ? Math.min(ff.w, ff.h) / 2 : 3,
      fill: paper, fillOpacity: 0.22,
      stroke: p.inkBright, strokeWidth: 1, strokeOpacity: 0.7
    }));
    furnGroup.push(svgEl('text', {
      x: ff.x + ff.w / 2, y: ff.y + ff.h / 2 + 3, textAnchor: 'middle',
      fill: p.inkDim, fontSize: 8, letterSpacing: 1,
      fontFamily: "'IBM Plex Mono', monospace"
    }, [ff.name]));
  }
  children.push(svgEl('g', { 'data-layer': 'furniture' }, furnGroup));

  // Exits — wall-gap glyphs + labels.
  var exitGroup = [];
  for (var e = 0; e < EXITS.length; e++) {
    var ex = EXITS[e];
    exitGroup.push(svgEl('rect', {
      'data-exit': ex.name,
      'data-exit-side': ex.side,
      x: ex.x - 14, y: ex.y - 4, width: 28, height: 8, rx: 2,
      fill: p.green, fillOpacity: 0.7, stroke: p.green, strokeWidth: 1
    }));
    // Label nudged toward room interior depending on wall side.
    var lx = ex.x, ly = ex.y;
    if (ex.side === 'south') ly = ex.y - 12;
    else if (ex.side === 'north') ly = ex.y + 20;
    else if (ex.side === 'west')  { lx = ex.x + 60; ly = ex.y + 3; }
    else if (ex.side === 'east')  { lx = ex.x - 60; ly = ex.y + 3; }
    exitGroup.push(svgEl('text', {
      x: lx, y: ly, textAnchor: 'middle',
      fill: p.green, fontSize: 8, letterSpacing: 1,
      fontFamily: "'IBM Plex Mono', monospace"
    }, [ex.name]));
  }
  children.push(svgEl('g', { 'data-layer': 'exits' }, exitGroup));

  // Entities — patron dots with faction tint.
  var entGroup = [];
  for (var i = 0; i < entities.length; i++) {
    var ent = entities[i];
    var tint = _factionTint(p, ent.faction);
    if (ent.faction === 'player') {
      entGroup.push(svgEl('circle', {
        cx: ent.x, cy: ent.y, r: 16, fill: 'url(#ent-self-glow)'
      }));
    }
    if (ent.faction === 'hostile') {
      // Hostile entities get a triangle.
      var s = 6;
      entGroup.push(svgEl('path', {
        'data-entity': ent.name,
        'data-entity-faction': ent.faction,
        d: 'M ' + ent.x + ' ' + (ent.y - s) +
           ' L ' + (ent.x + s) + ' ' + (ent.y + s) +
           ' L ' + (ent.x - s) + ' ' + (ent.y + s) + ' Z',
        fill: tint, stroke: p.ink, strokeWidth: 0.75
      }));
    } else {
      entGroup.push(svgEl('circle', {
        'data-entity': ent.name,
        'data-entity-faction': ent.faction,
        cx: ent.x, cy: ent.y, r: 5, fill: tint,
        stroke: p.ink, strokeWidth: 0.75
      }));
    }
    entGroup.push(svgEl('text', {
      x: ent.x, y: ent.y - 9, textAnchor: 'middle',
      fill: tint, fontSize: 8, letterSpacing: 0.5,
      fontFamily: "'IBM Plex Mono', monospace"
    }, [ent.name]));
  }
  children.push(svgEl('g', { 'data-layer': 'entities' }, entGroup));

  // Compass rose (optional decoration).
  if (CompassRose) {
    try {
      children.push(CompassRose({ p: p, x: width - 56, y: height - 56 }));
    } catch (eC) { /* skip */ }
  }

  // Scale bar (metre-scale).
  children.push(_scaleBar(p, 28, height - 30));

  // Room name + occupancy subtitle.
  children.push(svgEl('text', {
    x: 28, y: 40, fill: p.inkBright, fontSize: 18, letterSpacing: 2.5,
    fontFamily: "'IBM Plex Mono', monospace"
  }, ["CHALMUN'S CANTINA"]));
  children.push(svgEl('text', {
    x: 28, y: 58, fill: p.inkDim, fontSize: 10, letterSpacing: 2,
    fontFamily: "'IBM Plex Mono', monospace"
  }, ['MOS EISLEY \u00b7 ' + entities.length + ' PRESENT']));

  return svgEl('svg', {
    'data-tier-interior': '1',
    width: width, height: height,
    viewBox: '0 0 ' + width + ' ' + height,
    preserveAspectRatio: 'xMidYMid meet',
    style: { display: 'block', background: groundDeep }
  }, children);
}

function _factionTint(p, faction) {
  if (faction === 'player')   return p.cyan;
  if (faction === 'friendly') return p.amber;
  if (faction === 'hostile')  return p.red;
  return p.inkBright;  // neutral / unknown
}

// Local scale-bar glyph (metre-scale for interiors).
function _scaleBar(p, x, y) {
  return svgEl('g', { 'data-layer': 'scalebar' }, [
    svgEl('line', { x1: x, y1: y, x2: x + 40, y2: y,
                    stroke: p.inkDim, strokeWidth: 2 }),
    svgEl('line', { x1: x, y1: y - 4, x2: x, y2: y + 4,
                    stroke: p.inkDim, strokeWidth: 2 }),
    svgEl('line', { x1: x + 40, y1: y - 4, x2: x + 40, y2: y + 4,
                    stroke: p.inkDim, strokeWidth: 2 }),
    svgEl('text', { x: x + 20, y: y - 8, textAnchor: 'middle',
                    fill: p.inkDim, fontSize: 8, letterSpacing: 1,
                    fontFamily: "'IBM Plex Mono', monospace" }, ['1 m'])
  ]);
}

// ════════════════════════════════════════════════════════════════════
// buildTierZeroCantina(p, opts?) → <div>  (chrome-wrapped)
// ════════════════════════════════════════════════════════════════════
function buildTierZeroCantina(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierZeroCantina: palette argument required');

  var width  = opts.width  || 700;
  var height = opts.height || 600;

  var compEng = (typeof window !== 'undefined' && window.M3CompositionEngine) || {};
  var HolocartaFrame = compEng.HolocartaFrame;

  var innerSvg = buildTierZeroBody(p, {
    width: width, height: height, entities: opts.entities
  });

  if (!HolocartaFrame) {
    return htmlEl('div', {
      'data-tier-interior-frame-fallback': '1',
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
    breadcrumb: 'GALAXY \u25b8 OUTER RIM \u25b8 TATOOINE \u25b8 MOS EISLEY \u25b8 CANTINA',
    tier: '0 \u00b7 INTERIOR',
    legend: [
      { color: p.cyan,      shape: 'circle', glow: true, label: 'YOU' },
      { color: p.amber,     shape: 'circle', label: 'FRIENDLY' },
      { color: p.inkBright, shape: 'circle', label: 'NEUTRAL' },
      { color: p.red,       shape: 'tri',    label: 'HOSTILE' },
      { color: p.green,     shape: 'square', label: 'EXIT' }
    ],
    children: [innerSvg]
  });
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3TierInteriorBody = {
  SCHEMA_VERSION: 1,

  // Top-level
  buildTierZeroBody:    buildTierZeroBody,
  buildTierZeroCantina: buildTierZeroCantina,

  // Fixtures (public for downstream composition / Q1 audits)
  ROOM:       ROOM,
  FURNITURE:  FURNITURE,
  EXITS:      EXITS,
  ENTITIES:   ENTITIES,

  _internal: { _svgEl: svgEl, _htmlEl: htmlEl, _scaleBar: _scaleBar,
               _factionTint: _factionTint }
};

})();
