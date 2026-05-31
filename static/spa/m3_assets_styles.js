/* ============================================================================
   m3_assets_styles.js — style primitive footprints for the SPA map.

   Drop 4.1b · Tier 1 #4 · ported from map_v3/assets-styles.jsx (May 26 2026).

   Twelve primitive building footprints, each drawn at a 100×100 viewBox.
   The composition engine uses these as fallbacks when a room has no
   named-landmark binding (see asset-catalog §7.13.2.B).

   Each builder takes a palette `p` and returns an SVG <g> element built
   with M3Tokens.svgEl. The composition engine wraps each builder's <g>
   with the transform that places and scales the footprint at the room's
   world coordinates.

   Public API: window.M3AssetsStyles.STYLE_PRIMITIVES — a dict keyed by
   style name (`dock`, `cantina`, `civic`, ...). The composition engine
   does STYLE_PRIMITIVES[room.style](palette) to get the <g>.
   ============================================================================ */
(function(){
'use strict';

var svgEl = window.M3Tokens.svgEl;

// ── Dock — landing-bay door + central pad ring ──────────────────────
function SP_Dock(p) {
  return svgEl('g', null, [
    svgEl('rect', { x: 14, y: 14, width: 72, height: 72,
                    fill: p.fillDock, stroke: p.ink, strokeWidth: 1 }),
    // notched bay door at top
    svgEl('path', { d: 'M 36 14 L 44 8 L 56 8 L 64 14 Z',
                    fill: p.fillDock, stroke: p.ink, strokeWidth: 0.9 }),
    svgEl('line', { x1: 36, y1: 14, x2: 64, y2: 14,
                    stroke: p.inkDim, strokeWidth: 0.5, strokeDasharray: '2 2' }),
    // landing pad ring inside
    svgEl('circle', { cx: 50, cy: 54, r: 20,
                      fill: 'none', stroke: p.inkDim, strokeWidth: 0.5, strokeDasharray: '3 2' }),
    svgEl('circle', { cx: 50, cy: 54, r: 4,
                      fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.4 })
  ]);
}

// ── Cantina — rounded form with awning and amber pinpoint ───────────
function SP_Cantina(p) {
  return svgEl('g', null, [
    svgEl('rect', { x: 14, y: 26, width: 72, height: 56, rx: 20,
                    fill: p.fillCantina, stroke: p.ink, strokeWidth: 1 }),
    svgEl('path', { d: 'M 38 18 L 62 18 L 62 30 L 38 30 Z',
                    fill: p.fillCantina, stroke: p.ink, strokeWidth: 0.9 }),
    svgEl('line', { x1: 14, y1: 54, x2: 86, y2: 54,
                    stroke: p.inkDim, strokeWidth: 0.4 }),
    svgEl('circle', { cx: 50, cy: 54, r: 3, fill: p.amber, opacity: 0.7 })
  ]);
}

// ── Civic — pediment + columned entrance ────────────────────────────
function SP_Civic(p) {
  return svgEl('g', null, [
    svgEl('rect', { x: 16, y: 20, width: 68, height: 62, rx: 3,
                    fill: p.fillCivic, stroke: p.ink, strokeWidth: 1 }),
    // pediment
    svgEl('path', { d: 'M 22 20 L 50 10 L 78 20 Z',
                    fill: p.fillCivic, stroke: p.ink, strokeWidth: 0.9 }),
    svgEl('line', { x1: 50, y1: 10, x2: 50, y2: 20,
                    stroke: p.inkDim, strokeWidth: 0.4 }),
    // columned entrance
    svgEl('rect', { x: 42, y: 70, width: 4, height: 12,
                    fill: p.paperDark, stroke: p.ink, strokeWidth: 0.3 }),
    svgEl('rect', { x: 54, y: 70, width: 4, height: 12,
                    fill: p.paperDark, stroke: p.ink, strokeWidth: 0.3 })
  ]);
}

// ── Housing — circular form, dwelling at bottom ─────────────────────
function SP_Housing(p) {
  return svgEl('g', null, [
    svgEl('circle', { cx: 50, cy: 54, r: 32,
                      fill: p.fillHousing, stroke: p.ink, strokeWidth: 1 }),
    svgEl('circle', { cx: 50, cy: 54, r: 22,
                      fill: 'none', stroke: p.inkDim, strokeWidth: 0.3 }),
    svgEl('rect', { x: 46, y: 82, width: 8, height: 6,
                    fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.5 })
  ]);
}

// ── Vendor — awning with stripes + stall display ────────────────────
function SP_Vendor(p) {
  var children = [
    svgEl('rect', { x: 16, y: 28, width: 68, height: 56,
                    fill: p.fillVendor, stroke: p.ink, strokeWidth: 1 }),
    // awning
    svgEl('path', { d: 'M 12 20 L 88 20 L 84 28 L 16 28 Z',
                    fill: p.paperDark, stroke: p.ink, strokeWidth: 0.8 })
  ];
  // awning stripes
  [20, 30, 40, 50, 60, 70, 80].forEach(function(x) {
    children.push(svgEl('line', { x1: x, y1: 20, x2: x - 4, y2: 28,
                                  stroke: p.inkDim, strokeWidth: 0.3 }));
  });
  // stall display
  children.push(svgEl('line', { x1: 28, y1: 50, x2: 72, y2: 50,
                                stroke: p.inkDim, strokeWidth: 0.4 }));
  children.push(svgEl('line', { x1: 28, y1: 62, x2: 72, y2: 62,
                                stroke: p.inkDim, strokeWidth: 0.4 }));
  return svgEl('g', null, children);
}

// ── Gate — wedge pointing inward + gate-light ───────────────────────
function SP_Gate(p) {
  return svgEl('g', null, [
    svgEl('path', { d: 'M 18 14 L 82 14 L 50 80 Z',
                    fill: p.fillCivic, stroke: p.ink, strokeWidth: 1 }),
    svgEl('path', { d: 'M 30 22 L 70 22 L 50 66 Z',
                    fill: 'none', stroke: p.inkDim, strokeWidth: 0.5 }),
    // gate light
    svgEl('circle', { cx: 50, cy: 86, r: 2, fill: p.amber, opacity: 0.8 })
  ]);
}

// ── Hutt — doubled borders + central glyph (wealth marker) ──────────
function SP_Hutt(p) {
  var glyph = svgEl('text', {
    x: 50, y: 60, fontSize: 28, textAnchor: 'middle',
    fill: p.gold, opacity: 0.7,
    fontFamily: 'serif', fontWeight: 700
  }, ['\uD80C\uDD97']);  // 𓆗 — Egyptian crocodile glyph (Hutt wealth marker)
  return svgEl('g', null, [
    svgEl('rect', { x: 14, y: 14, width: 72, height: 72,
                    fill: p.fillHutt, stroke: p.ink, strokeWidth: 1.2 }),
    svgEl('rect', { x: 20, y: 20, width: 60, height: 60,
                    fill: 'none', stroke: p.ink, strokeWidth: 0.6 }),
    // doubled border — wealth marker
    svgEl('rect', { x: 26, y: 26, width: 48, height: 48,
                    fill: 'none', stroke: p.inkDim, strokeWidth: 0.4 }),
    glyph
  ]);
}

// ── Industrial — vent stacks + corrugated lines ─────────────────────
function SP_Industrial(p) {
  var children = [
    svgEl('rect', { x: 14, y: 20, width: 72, height: 60,
                    fill: p.fillIndustrial, stroke: p.ink, strokeWidth: 1 })
  ];
  // vent stacks
  [22, 36, 50, 64, 78].forEach(function(x) {
    children.push(svgEl('rect', { x: x - 3, y: 14, width: 6, height: 8,
                                  fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }));
  });
  // corrugated lines (8 of them)
  for (var i = 0; i < 8; i++) {
    var y = 28 + i * 6.5;
    children.push(svgEl('line', { x1: 14, y1: y, x2: 86, y2: y,
                                  stroke: p.inkDim, strokeWidth: 0.25 }));
  }
  return svgEl('g', null, children);
}

// ── Warehouse — long form + bay doors ───────────────────────────────
function SP_Warehouse(p) {
  var children = [
    svgEl('rect', { x: 10, y: 32, width: 80, height: 44,
                    fill: p.fillIndustrial, stroke: p.ink, strokeWidth: 1 })
  ];
  // bay doors
  [18, 36, 54, 72].forEach(function(x) {
    children.push(svgEl('rect', { x: x, y: 64, width: 12, height: 12,
                                  fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.5 }));
  });
  // roof line
  children.push(svgEl('line', { x1: 10, y1: 42, x2: 90, y2: 42,
                                stroke: p.inkDim, strokeWidth: 0.3 }));
  return svgEl('g', null, children);
}

// ── Street — horizontal band with center dashed line ────────────────
function SP_Street(p) {
  return svgEl('g', null, [
    svgEl('rect', { x: 0, y: 36, width: 100, height: 28, fill: p.groundDeep }),
    svgEl('line', { x1: 0, y1: 50, x2: 100, y2: 50,
                    stroke: p.inkFaint, strokeWidth: 0.6, strokeDasharray: '6 4' })
  ]);
}

// ── Landmark — hexagonal "important place" footprint ────────────────
function SP_Landmark(p) {
  return svgEl('g', null, [
    svgEl('polygon', { points: '50,10 86,32 86,68 50,90 14,68 14,32',
                       fill: p.fillLandmark, stroke: p.ink, strokeWidth: 1 }),
    svgEl('polygon', { points: '50,20 76,36 76,64 50,80 24,64 24,36',
                       fill: 'none', stroke: p.inkDim, strokeWidth: 0.5 }),
    svgEl('circle', { cx: 50, cy: 50, r: 4, fill: p.gold, opacity: 0.7 })
  ]);
}

// ── Default fallback — dashed square placeholder ────────────────────
function SP_Default(p) {
  // Returns a single <rect>, not wrapped in <g> — the composition engine
  // accepts either. Matches the JSX source which returns one element.
  return svgEl('rect', { x: 20, y: 20, width: 60, height: 60,
                         fill: p.paperDark, stroke: p.ink, strokeWidth: 0.9,
                         strokeDasharray: '2 2' });
}

var STYLE_PRIMITIVES = {
  dock:       SP_Dock,
  cantina:    SP_Cantina,
  civic:      SP_Civic,
  housing:    SP_Housing,
  vendor:     SP_Vendor,
  gate:       SP_Gate,
  hutt:       SP_Hutt,
  industrial: SP_Industrial,
  warehouse:  SP_Warehouse,
  street:     SP_Street,
  landmark:   SP_Landmark,
  'default':  SP_Default     // quoted because `default` is a reserved word
};

window.M3AssetsStyles = {
  STYLE_PRIMITIVES: STYLE_PRIMITIVES
};

})();
