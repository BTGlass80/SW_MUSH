/* ============================================================================
   m3_assets_landmarks.js — urban named-landmark footprints for the SPA map.

   Drop 4.1d · Tier 1 #4 · ported from map_v3/assets-landmarks.jsx
   (May 26 2026; bugfix overlay applied — B3 era-comment edits to
   LM_CustomsOffice).

   Ten Mos Eisley landmark builders, each authored at a 100×100 viewBox
   with "hand-drawn cartographic" sensibility (varying line weight,
   suggested detail, atmospheric shading via wobble paths):
     - LM_DockingBay94      — iconic circular landing pit with YT-1300
     - LM_ChalmunsCantina   — dome silhouette + bandstand annex
     - LM_LuckyDespot       — wrecked star cruiser, repurposed cantina/hotel
     - LM_ControlTower      — conical spaceport tower + comm dish
     - LM_CustomsOffice     — civic/Republic-government rectangular block
     - LM_MosEisleyInn      — multi-story dome with vaporator on roof
     - LM_SpaceportHotel    — three-dome cluster
     - LM_MomawNadon        — single moisture-farmer dome + vaporator field
     - LM_TransportDepot    — long warehouse with bay doors
     - LM_SpeederLot        — open-air vendor lot with parked speeders

   Each builder accepts an options object `{ p, lod, t }` where
     - p   — active palette
     - lod — 'icon' | 'detail' | 'detailed' (zoom-tier appropriate)
     - t   — time-of-day 'day' | 'dusk' | 'night' (reserved; not yet
              consumed in this drop — atmospheric overlay handles tinting)

   Public API: window.M3AssetsLandmarks exposes LANDMARKS keyed by
   12 short slugs (matches the composition-engine contract used by
   wilderness in 4.1c), plus each LM_* builder by long ident for the
   catalog's namespace-fallback chain (see m3_asset_catalog.js Drop 4.1c).
   Two of the slug entries are aliases: docking_bay_94_pit + _entrance
   both point at LM_DockingBay94; lucky_despot_staircase + _star_chamber
   both point at LM_LuckyDespot. That mirrors the JSX source registry
   verbatim.
   ============================================================================ */
(function(){
'use strict';

var svgEl = window.M3Tokens.svgEl;

// ────────────────────────────────────────────────────────────────
// SHARED HELPERS (ported from the JSX module scope, lines 16–29)
// ────────────────────────────────────────────────────────────────

// "Hand-drawn" wobble path — utility for jagged organic outlines.
// Deterministic given a seed (Math.sin lookup) so output is identical
// across runs. Used by LM_DockingBay94's berm and pit silhouettes.
function wobble(cx, cy, r, n, jitter, seed) {
  if (n == null) n = 24;
  if (jitter == null) jitter = 0.6;
  if (seed == null) seed = 1;
  var out = [];
  for (var i = 0; i < n; i++) {
    var a = (i / n) * Math.PI * 2;
    var rj = r + Math.sin(seed * 100 + i * 7.31) * jitter;
    out.push([cx + Math.cos(a) * rj, cy + Math.sin(a) * rj]);
  }
  return 'M ' + out.map(function(pt) {
    return pt[0].toFixed(2) + ' ' + pt[1].toFixed(2);
  }).join(' L ') + ' Z';
}

// ════════════════════════════════════════════════════════════════
// LM_DockingBay94 — iconic circular landing pit + docked freighter
// ════════════════════════════════════════════════════════════════
function LM_DockingBay94(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';
  var f = p.fillDock;

  if (lod === 'icon') {
    return svgEl('g', null, [
      svgEl('circle', { cx: 50, cy: 50, r: 32, fill: f,
                        stroke: p.ink, strokeWidth: 1.5 }),
      svgEl('circle', { cx: 50, cy: 50, r: 20, fill: p.groundDeep,
                        stroke: p.ink, strokeWidth: 0.8 })
    ]);
  }

  var children = [
    // outer rim (raised berm of the pit) — wobble for hand-drawn feel
    svgEl('path', { d: wobble(50, 50, 42, 36, 0.5, 1),
                    fill: f, stroke: p.ink, strokeWidth: 1.2 }),
    // secondary rim ledge
    svgEl('circle', { cx: 50, cy: 50, r: 36, fill: 'none',
                      stroke: p.inkDim, strokeWidth: 0.5,
                      strokeDasharray: '2 1.5' }),
    // pit interior — deeper shadow
    svgEl('path', { d: wobble(50, 50, 30, 32, 0.4, 2),
                    fill: p.groundDeep, stroke: p.ink, strokeWidth: 0.8 })
  ];
  // landing-light ring — 12 lights, two extinguished
  for (var i = 0; i < 12; i++) {
    var a = (i / 12) * Math.PI * 2;
    var x = 50 + Math.cos(a) * 27;
    var y = 50 + Math.sin(a) * 27;
    var lit = (i !== 3 && i !== 8);
    children.push(svgEl('circle', {
      cx: x, cy: y, r: 1,
      fill: lit ? p.amber : p.inkFaint
    }));
  }

  if (lod === 'detailed') {
    // docked YT-1300 silhouette (the Mynock)
    children.push(svgEl('g', { transform: 'translate(50 50) rotate(28)' }, [
      svgEl('ellipse', { cx: 0, cy: 0, rx: 14, ry: 10,
                         fill: p.paperDark, stroke: p.ink, strokeWidth: 0.6 }),
      svgEl('rect', { x: -2, y: -13, width: 4, height: 6,
                      fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }),
      svgEl('circle', { cx:  6, cy: -4, r: 2,   fill: p.amber, opacity: 0.7 }),
      svgEl('circle', { cx: -6, cy: -4, r: 1.5, fill: p.cyan,  opacity: 0.4 }),
      svgEl('line', { x1: -14, y1: 0, x2: -18, y2: 0,
                      stroke: p.ink, strokeWidth: 0.6 })
    ]));
    // blast doors on the north edge
    children.push(svgEl('path', {
      d: 'M 38 8 L 62 8 L 62 14 L 38 14 Z',
      fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.7
    }));
    children.push(svgEl('line', { x1: 50, y1: 8, x2: 50, y2: 14,
                                  stroke: p.ink, strokeWidth: 0.4 }));
    // fuel cells along the back wall (per Tier 1 #3 L4 fidelity)
    [28, 36, 64, 72].forEach(function(x) {
      children.push(svgEl('circle', {
        cx: x, cy: 88, r: 2.5,
        fill: p.fillIndustrial, stroke: p.ink, strokeWidth: 0.5
      }));
    });
    // scorching radiating from center — 6 ground-shadow lines
    [0, 60, 120, 180, 240, 300].forEach(function(angle) {
      var rad = angle * Math.PI / 180;
      children.push(svgEl('line', {
        x1: 50 + Math.cos(rad) * 18, y1: 50 + Math.sin(rad) * 18,
        x2: 50 + Math.cos(rad) * 26, y2: 50 + Math.sin(rad) * 26,
        stroke: p.groundShadow, strokeWidth: 1, opacity: 0.7
      }));
    });
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_ChalmunsCantina — dome + bandstand annex + oculus
// ════════════════════════════════════════════════════════════════
function LM_ChalmunsCantina(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('g', null, [
      svgEl('ellipse', { cx: 50, cy: 56, rx: 32, ry: 26,
                         fill: p.fillCantina, stroke: p.ink, strokeWidth: 1.5 }),
      svgEl('ellipse', { cx: 50, cy: 36, rx: 8, ry: 6,
                         fill: p.fillCantina, stroke: p.ink, strokeWidth: 1.2 })
    ]);
  }

  var children = [
    // main dome — slightly squashed
    svgEl('ellipse', { cx: 50, cy: 56, rx: 36, ry: 30,
                       fill: p.fillCantina, stroke: p.ink, strokeWidth: 1.2 }),
    // dome panel lines (two curves + vertical dashed seam)
    svgEl('path', { d: 'M 14 56 Q 50 36 86 56',
                    fill: 'none', stroke: p.inkDim, strokeWidth: 0.4 }),
    svgEl('path', { d: 'M 18 70 Q 50 48 82 70',
                    fill: 'none', stroke: p.inkDim, strokeWidth: 0.4 }),
    svgEl('line', { x1: 50, y1: 26, x2: 50, y2: 86,
                    stroke: p.inkDim, strokeWidth: 0.3, strokeDasharray: '2 2' }),
    // bandstand protrusion (north annex)
    svgEl('path', { d: 'M 38 32 Q 50 22 62 32 L 62 38 L 38 38 Z',
                    fill: p.fillCantina, stroke: p.ink, strokeWidth: 0.9 }),
    // entrance at south
    svgEl('path', { d: 'M 42 84 L 58 84 L 58 90 L 42 90 Z',
                    fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.8 })
  ];

  if (lod === 'detailed') {
    // curved bar inside
    children.push(svgEl('path', { d: 'M 28 62 Q 42 50 56 62',
                                  fill: 'none', stroke: p.ink, strokeWidth: 0.6 }));
    children.push(svgEl('path', { d: 'M 28 64 Q 42 52 56 64',
                                  fill: 'none', stroke: p.ink, strokeWidth: 0.4 }));
    // tables — small concentric circles scattered
    [[64, 56], [66, 70], [72, 62], [42, 74], [58, 76], [34, 72]]
      .forEach(function(pt) {
        var x = pt[0], y = pt[1];
        children.push(svgEl('g', null, [
          svgEl('circle', { cx: x, cy: y, r: 1.6,
                            fill: p.paperDark, stroke: p.ink, strokeWidth: 0.3 }),
          svgEl('circle', { cx: x, cy: y, r: 0.6, fill: p.ink })
        ]));
      });
    // the iconic round window / oculus
    children.push(svgEl('circle', { cx: 50, cy: 56, r: 3,
                                    fill: p.amber, stroke: p.ink,
                                    strokeWidth: 0.4, opacity: 0.7 }));
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_LuckyDespot — wrecked star cruiser repurposed cantina/hotel
// ════════════════════════════════════════════════════════════════
function LM_LuckyDespot(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('ellipse', {
      cx: 50, cy: 50, rx: 38, ry: 16,
      fill: p.fillCantina, stroke: p.ink, strokeWidth: 1.2
    });
  }

  var children = [
    // main hull — long ovoid
    svgEl('ellipse', { cx: 50, cy: 50, rx: 44, ry: 18,
                       fill: p.fillCantina, stroke: p.ink, strokeWidth: 1.1 })
  ];
  // hull plating lines
  [-30, -15, 0, 15, 30].forEach(function(dx) {
    children.push(svgEl('line', {
      x1: 50 + dx, y1: 32, x2: 50 + dx, y2: 68,
      stroke: p.inkDim, strokeWidth: 0.3
    }));
  });
  // command tower remnant
  children.push(svgEl('ellipse', { cx: 20, cy: 50, rx: 8, ry: 6,
                                   fill: p.paperDark, stroke: p.ink,
                                   strokeWidth: 0.7 }));
  children.push(svgEl('line', { x1: 12, y1: 50, x2: 6, y2: 48,
                                stroke: p.ink, strokeWidth: 0.5 }));

  if (lod === 'detailed') {
    // engine cluster at rear (right side) — 3 circles
    [44, 50, 56].forEach(function(cy) {
      children.push(svgEl('circle', {
        cx: 86, cy: cy, r: 3,
        fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.5
      }));
    });
    // port-side fin (broken triangle)
    children.push(svgEl('path', { d: 'M 40 32 L 36 24 L 30 26 Z',
                                  fill: p.paperDark, stroke: p.ink, strokeWidth: 0.6 }));
    // starboard fin
    children.push(svgEl('path', { d: 'M 60 68 L 64 76 L 70 74 Z',
                                  fill: p.paperDark, stroke: p.ink, strokeWidth: 0.6 }));
    // lit windows along hull — 12 small amber rects
    for (var i = 0; i < 12; i++) {
      var x = 24 + i * 5;
      children.push(svgEl('rect', {
        x: x, y: 48, width: 1.5, height: 1,
        fill: p.amber, opacity: 0.7
      }));
    }
    // boarding ramp at center
    children.push(svgEl('path', { d: 'M 46 68 L 54 68 L 56 80 L 44 80 Z',
                                  fill: p.groundDeep, stroke: p.ink,
                                  strokeWidth: 0.6 }));
    // sand piled around the wreck
    children.push(svgEl('path', { d: 'M 4 50 Q 8 42 12 50',
                                  fill: 'none', stroke: p.inkFaint, strokeWidth: 0.4 }));
    children.push(svgEl('path', { d: 'M 88 50 Q 92 58 96 50',
                                  fill: 'none', stroke: p.inkFaint, strokeWidth: 0.4 }));
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_ControlTower — conical spaceport tower with comm dish
// ════════════════════════════════════════════════════════════════
function LM_ControlTower(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('g', null, [
      svgEl('path', { d: 'M 38 76 L 62 76 L 56 36 L 44 36 Z',
                      fill: p.fillCivic, stroke: p.ink, strokeWidth: 1.2 }),
      svgEl('circle', { cx: 50, cy: 28, r: 6,
                        fill: p.fillCivic, stroke: p.ink, strokeWidth: 1 })
    ]);
  }

  var children = [
    // base footprint
    svgEl('rect', { x: 30, y: 68, width: 40, height: 18,
                    fill: p.fillCivic, stroke: p.ink, strokeWidth: 1 }),
    // tower shaft seen from above
    svgEl('ellipse', { cx: 50, cy: 50, rx: 14, ry: 12,
                       fill: p.fillCivic, stroke: p.ink, strokeWidth: 1 }),
    // control dome on top
    svgEl('ellipse', { cx: 50, cy: 48, rx: 10, ry: 8,
                       fill: p.paper, stroke: p.ink, strokeWidth: 0.9 }),
    // dome panel lines
    svgEl('line', { x1: 40, y1: 48, x2: 60, y2: 48,
                    stroke: p.inkDim, strokeWidth: 0.4 }),
    svgEl('path', { d: 'M 42 44 Q 50 42 58 44',
                    fill: 'none', stroke: p.inkDim, strokeWidth: 0.3 })
  ];

  if (lod === 'detailed') {
    // viewport windows around dome — 8 cyan dots
    for (var i = 0; i < 8; i++) {
      var a = (i / 8) * Math.PI * 2;
      var x = 50 + Math.cos(a) * 7.5;
      var y = 48 + Math.sin(a) * 6;
      children.push(svgEl('circle', { cx: x, cy: y, r: 0.6,
                                      fill: p.cyan, opacity: 0.7 }));
    }
    // comm dish on top
    children.push(svgEl('line', { x1: 50, y1: 38, x2: 50, y2: 32,
                                  stroke: p.ink, strokeWidth: 0.6 }));
    children.push(svgEl('ellipse', { cx: 50, cy: 32, rx: 5, ry: 1.5,
                                     fill: p.paperDark, stroke: p.ink,
                                     strokeWidth: 0.5 }));
    // drop shadow indicating height
    children.push(svgEl('ellipse', { cx: 56, cy: 56, rx: 14, ry: 10,
                                     fill: p.groundShadow, opacity: 0.3 }));
    // landing pad lights at base corners
    [[33, 72], [67, 72], [33, 82], [67, 82]].forEach(function(pt) {
      children.push(svgEl('circle', { cx: pt[0], cy: pt[1], r: 0.8,
                                      fill: p.amber }));
    });
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_CustomsOffice — Civic / Republic-government rectangular block
// (B3 bugfix: comment swap from "Imperial-style" to neutral civic)
// ════════════════════════════════════════════════════════════════
function LM_CustomsOffice(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('rect', { x: 20, y: 20, width: 60, height: 60,
                           fill: p.fillCivic, stroke: p.ink, strokeWidth: 1.2 });
  }

  var children = [
    // main body
    svgEl('rect', { x: 18, y: 20, width: 64, height: 60,
                    fill: p.fillCivic, stroke: p.ink, strokeWidth: 1.1 }),
    // pediment / awning over the entrance
    svgEl('path', { d: 'M 30 78 L 70 78 L 70 86 L 30 86 Z',
                    fill: p.paperDark, stroke: p.ink, strokeWidth: 0.8 }),
    // central entrance
    svgEl('rect', { x: 44, y: 78, width: 12, height: 8,
                    fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.5 })
  ];

  if (lod === 'detailed') {
    // roof segments
    children.push(svgEl('line', { x1: 18, y1: 36, x2: 82, y2: 36,
                                  stroke: p.inkDim, strokeWidth: 0.4 }));
    children.push(svgEl('line', { x1: 18, y1: 56, x2: 82, y2: 56,
                                  stroke: p.inkDim, strokeWidth: 0.4 }));
    // two rows of windows
    [22, 30, 38, 46, 54, 62, 70, 78].forEach(function(x) {
      children.push(svgEl('rect', { x: x, y: 28, width: 3, height: 4,
                                    fill: p.amber, opacity: 0.5 }));
    });
    [22, 30, 38, 46, 54, 62, 70, 78].forEach(function(x) {
      children.push(svgEl('rect', { x: x, y: 48, width: 3, height: 4,
                                    fill: p.amber, opacity: 0.5 }));
    });
    // Civic banner — Clone Wars era (B3 bugfix: era-neutral comment)
    children.push(svgEl('rect', { x: 47, y: 22, width: 6, height: 14,
                                  fill: p.red, opacity: 0.7,
                                  stroke: p.ink, strokeWidth: 0.3 }));
    children.push(svgEl('path', { d: 'M 47 36 L 50 38 L 53 36',
                                  fill: 'none', stroke: p.ink, strokeWidth: 0.4 }));
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_MosEisleyInn — multi-story dome with vaporator on roof
// ════════════════════════════════════════════════════════════════
function LM_MosEisleyInn(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('circle', { cx: 50, cy: 50, r: 32,
                             fill: p.fillHousing, stroke: p.ink, strokeWidth: 1.2 });
  }

  var children = [
    // main dome
    svgEl('circle', { cx: 50, cy: 50, r: 34,
                      fill: p.fillHousing, stroke: p.ink, strokeWidth: 1.1 }),
    // concentric "stories" as rings
    svgEl('circle', { cx: 50, cy: 50, r: 26,
                      fill: 'none', stroke: p.inkDim, strokeWidth: 0.4 }),
    svgEl('circle', { cx: 50, cy: 50, r: 18,
                      fill: 'none', stroke: p.inkDim, strokeWidth: 0.4 }),
    // central courtyard
    svgEl('circle', { cx: 50, cy: 50, r: 9,
                      fill: p.groundDeep, stroke: p.ink, strokeWidth: 0.5 }),
    // entrance south
    svgEl('path', { d: 'M 46 84 L 54 84 L 54 92 L 46 92 Z',
                    fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.6 })
  ];

  if (lod === 'detailed') {
    // windows around the outer ring — 16 amber slits, rotated tangent
    for (var i = 0; i < 16; i++) {
      var a = (i / 16) * Math.PI * 2 - Math.PI / 2;
      var x = 50 + Math.cos(a) * 30;
      var y = 50 + Math.sin(a) * 30;
      var rotDeg = a * 180 / Math.PI + 90;
      children.push(svgEl('rect', {
        x: x - 0.7, y: y - 1, width: 1.5, height: 2,
        fill: p.amber, opacity: 0.6,
        transform: 'rotate(' + rotDeg + ' ' + x + ' ' + y + ')'
      }));
    }
    // vaporator on roof — small dot + stem
    children.push(svgEl('circle', { cx: 50, cy: 50, r: 2,
                                    fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }));
    children.push(svgEl('line', { x1: 50, y1: 48, x2: 50, y2: 44,
                                  stroke: p.ink, strokeWidth: 0.4 }));
    // moisture coils — 6 cyan dots in a circle
    [0, 60, 120, 180, 240, 300].forEach(function(angle) {
      var rad = angle * Math.PI / 180;
      children.push(svgEl('circle', {
        cx: 50 + Math.cos(rad) * 22,
        cy: 50 + Math.sin(rad) * 22,
        r: 0.8, fill: p.cyan, opacity: 0.5
      }));
    });
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_SpaceportHotel — three-dome cluster (triangle layout)
// ════════════════════════════════════════════════════════════════
function LM_SpaceportHotel(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('circle', { cx: 50, cy: 50, r: 32,
                             fill: p.fillHousing, stroke: p.ink, strokeWidth: 1.2 });
  }

  var children = [
    // three-dome cluster: NW, NE, S
    svgEl('circle', { cx: 30, cy: 42, r: 22,
                      fill: p.fillHousing, stroke: p.ink, strokeWidth: 1 }),
    svgEl('circle', { cx: 68, cy: 42, r: 22,
                      fill: p.fillHousing, stroke: p.ink, strokeWidth: 1 }),
    svgEl('circle', { cx: 50, cy: 68, r: 24,
                      fill: p.fillHousing, stroke: p.ink, strokeWidth: 1.1 }),
    // inner rings
    svgEl('circle', { cx: 30, cy: 42, r: 14, fill: 'none',
                      stroke: p.inkDim, strokeWidth: 0.3 }),
    svgEl('circle', { cx: 68, cy: 42, r: 14, fill: 'none',
                      stroke: p.inkDim, strokeWidth: 0.3 }),
    svgEl('circle', { cx: 50, cy: 68, r: 16, fill: 'none',
                      stroke: p.inkDim, strokeWidth: 0.3 })
  ];

  if (lod === 'detailed') {
    // central courtyard between domes
    children.push(svgEl('circle', { cx: 50, cy: 50, r: 6,
                                    fill: p.groundDeep, stroke: p.ink, strokeWidth: 0.5 }));
    // entrance south
    children.push(svgEl('path', { d: 'M 46 88 L 54 88 L 54 94 L 46 94 Z',
                                  fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.5 }));
    // dome panel lines
    children.push(svgEl('path', { d: 'M 16 42 Q 30 32 44 42',
                                  fill: 'none', stroke: p.inkDim, strokeWidth: 0.3 }));
    children.push(svgEl('path', { d: 'M 54 42 Q 68 32 82 42',
                                  fill: 'none', stroke: p.inkDim, strokeWidth: 0.3 }));
    children.push(svgEl('path', { d: 'M 30 68 Q 50 56 70 68',
                                  fill: 'none', stroke: p.inkDim, strokeWidth: 0.3 }));
    // lit windows scattered across the domes
    [[24, 36], [36, 36], [62, 36], [74, 36], [40, 64], [58, 64]]
      .forEach(function(pt) {
        children.push(svgEl('rect', {
          x: pt[0], y: pt[1], width: 2, height: 1.4,
          fill: p.amber, opacity: 0.6
        }));
      });
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_MomawNadon — single moisture-farmer dome + vaporator field
// ════════════════════════════════════════════════════════════════
function LM_MomawNadon(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('circle', { cx: 50, cy: 50, r: 26,
                             fill: p.fillHousing, stroke: p.ink, strokeWidth: 1.2 });
  }

  var children = [
    svgEl('circle', { cx: 50, cy: 54, r: 28,
                      fill: p.fillHousing, stroke: p.ink, strokeWidth: 1.1 }),
    svgEl('circle', { cx: 50, cy: 54, r: 20, fill: 'none',
                      stroke: p.inkDim, strokeWidth: 0.3 }),
    svgEl('circle', { cx: 50, cy: 54, r: 4,
                      fill: p.groundDeep, stroke: p.ink, strokeWidth: 0.4 }),
    // entrance
    svgEl('path', { d: 'M 46 82 L 54 82 L 54 88 L 46 88 Z',
                    fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.5 })
  ];

  if (lod === 'detailed') {
    // vaporator field — 7 stations around the dome
    [[24, 24], [76, 24], [22, 60], [78, 60],
     [50, 16], [30, 84], [70, 84]].forEach(function(pt) {
      var x = pt[0], y = pt[1];
      children.push(svgEl('g', null, [
        svgEl('circle', { cx: x, cy: y, r: 2.5,
                          fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }),
        svgEl('circle', { cx: x, cy: y, r: 1, fill: p.cyan, opacity: 0.5 })
      ]));
    });
    // connecting paths to the 4 corner vaporators
    [[24, 24], [76, 24], [22, 60], [78, 60]].forEach(function(pt) {
      children.push(svgEl('line', {
        x1: 50, y1: 54, x2: pt[0], y2: pt[1],
        stroke: p.inkFaint, strokeWidth: 0.3, strokeDasharray: '1 1'
      }));
    });
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_TransportDepot — long warehouse with bay doors
// ════════════════════════════════════════════════════════════════
function LM_TransportDepot(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('rect', { x: 14, y: 32, width: 72, height: 36,
                           fill: p.fillIndustrial, stroke: p.ink, strokeWidth: 1.2 });
  }

  var children = [
    svgEl('rect', { x: 12, y: 28, width: 76, height: 44,
                    fill: p.fillIndustrial, stroke: p.ink, strokeWidth: 1.1 })
  ];
  // bay doors along south — 5 bays, each with a center seam line
  [18, 32, 46, 60, 74].forEach(function(x) {
    children.push(svgEl('g', null, [
      svgEl('rect', { x: x, y: 62, width: 10, height: 10,
                      fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.6 }),
      svgEl('line', { x1: x + 5, y1: 62, x2: x + 5, y2: 72,
                      stroke: p.inkDim, strokeWidth: 0.3 })
    ]));
  });

  if (lod === 'detailed') {
    // roof vents
    [28, 50, 72].forEach(function(x) {
      children.push(svgEl('rect', { x: x - 4, y: 36, width: 8, height: 4,
                                    fill: p.paperDark, stroke: p.ink, strokeWidth: 0.3 }));
    });
    // loading sign
    children.push(svgEl('rect', { x: 44, y: 20, width: 12, height: 6,
                                  fill: p.amber, opacity: 0.6,
                                  stroke: p.ink, strokeWidth: 0.3 }));
    // parked speeders out front
    children.push(svgEl('ellipse', { cx: 26, cy: 82, rx: 3, ry: 1.5,
                                     fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }));
    children.push(svgEl('ellipse', { cx: 36, cy: 82, rx: 3, ry: 1.5,
                                     fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }));
  }

  return svgEl('g', null, children);
}

// ════════════════════════════════════════════════════════════════
// LM_SpeederLot — open-air vendor lot with parked speeder bikes
// (referenced in registry as 'spaceport_speeders'; not in the 4.1b
// catalog's 9-entry preview list but still part of LANDMARKS for
// the composition engine to render against the slug).
// ════════════════════════════════════════════════════════════════
function LM_SpeederLot(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('rect', { x: 16, y: 28, width: 68, height: 44,
                           fill: p.fillVendor, stroke: p.ink, strokeWidth: 1.2 });
  }

  var children = [
    // lot perimeter — dashed
    svgEl('rect', { x: 14, y: 24, width: 72, height: 52,
                    fill: p.fillVendor, stroke: p.ink, strokeWidth: 0.9,
                    strokeDasharray: '2 1.5' }),
    // awning over the office
    svgEl('path', { d: 'M 14 16 L 50 16 L 50 28 L 14 28 Z',
                    fill: p.paperDark, stroke: p.ink, strokeWidth: 0.7 })
  ];
  // awning stripes — 5 lines
  [20, 26, 32, 38, 44].forEach(function(x) {
    children.push(svgEl('line', { x1: x, y1: 16, x2: x, y2: 28,
                                  stroke: p.inkDim, strokeWidth: 0.3 }));
  });

  if (lod === 'detailed') {
    // parked speeders in a 3×4 grid (12 speeders)
    [[28, 38], [44, 38], [60, 38], [76, 38],
     [28, 50], [44, 50], [60, 50], [76, 50],
     [28, 62], [44, 62], [60, 62], [76, 62]].forEach(function(pt) {
      var x = pt[0], y = pt[1];
      children.push(svgEl('g', null, [
        svgEl('ellipse', { cx: x, cy: y, rx: 5, ry: 2.5,
                           fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }),
        svgEl('ellipse', { cx: x, cy: y, rx: 2.5, ry: 1,
                           fill: p.inkDim, opacity: 0.6 })
      ]));
    });
  }

  return svgEl('g', null, children);
}

// ────────────────────────────────────────────────────────────────
// LANDMARK REGISTRY — 12 short-slug → component bindings
// ────────────────────────────────────────────────────────────────
// Slug list mirrors the JSX source registry verbatim. Two builders
// (LM_DockingBay94 and LM_LuckyDespot) are referenced by multiple
// slugs because a single landmark occupies more than one room from
// the engine's perspective (e.g. the docking-bay pit and its
// adjoining blast-door entrance are separate rooms but share the
// same landmark illustration).
var LANDMARKS = {
  docking_bay_94_pit:          LM_DockingBay94,
  docking_bay_94_entrance:     LM_DockingBay94,
  chalmuans_cantina_main_bar:  LM_ChalmunsCantina,
  lucky_despot_staircase:      LM_LuckyDespot,
  lucky_despot_star_chamber:   LM_LuckyDespot,
  mos_eisley_control_tower:    LM_ControlTower,
  spaceport_customs_office:    LM_CustomsOffice,
  mos_eisley_inn:              LM_MosEisleyInn,
  spaceport_hotel:             LM_SpaceportHotel,
  house_of_momaw_nadon:        LM_MomawNadon,
  transport_depot:             LM_TransportDepot,
  spaceport_speeders:          LM_SpeederLot
};

// Namespace mirrors the m3_assets_wilderness.js shape: short-slug
// dict for the composition engine, plus each builder by long ident
// for the catalog's namespace-fallback chain (m3_asset_catalog.js
// `buildLandmarksColumn`).
window.M3AssetsLandmarks = {
  LANDMARKS:           LANDMARKS,
  LM_DockingBay94:     LM_DockingBay94,
  LM_ChalmunsCantina:  LM_ChalmunsCantina,
  LM_LuckyDespot:      LM_LuckyDespot,
  LM_ControlTower:     LM_ControlTower,
  LM_CustomsOffice:    LM_CustomsOffice,
  LM_MosEisleyInn:     LM_MosEisleyInn,
  LM_SpaceportHotel:   LM_SpaceportHotel,
  LM_MomawNadon:       LM_MomawNadon,
  LM_TransportDepot:   LM_TransportDepot,
  LM_SpeederLot:       LM_SpeederLot
};

})();
