/* ============================================================================
   m3_assets_wilderness.js — wilderness-region landmark footprints.

   Drop 4.1c · Tier 1 #4 · ported from map_v3/assets-wilderness.jsx
   (May 26 2026).

   Six named landmarks for the Dune Sea / Jundland Wastes wilderness:
     - WLM_TuskenCamp     — tent ring around bonfire, banthas at edges
     - WLM_Sandcrawler    — treaded mining vehicle, Jawa-glow windows
     - WLM_AbandonedMine  — tunnel into rock outcrop, rail tracks
     - WLM_KraytSkeleton  — vertebrae and ribs in bleached sand
     - WLM_JabbaPalace    — palace mass with arch, watchtowers
     - WLM_MoistureFarm   — dome + vaporator cluster

   Same authoring pattern as urban landmarks (100×100 viewBox, hand-drawn
   cartographic sensibility). Each builder accepts `{ p, lod }` where
   `lod` is one of 'icon' | 'detail' | 'detailed'. 'icon' is the
   simplified small-zoom form; anything else renders the full landmark,
   with extra flourishes (smoke, banthas, debris) gated by `lod === 'detailed'`.

   Public API: window.M3AssetsWilderness.WILDERNESS_LANDMARKS — a dict
   keyed by landmark slug (e.g. `tusken_camp`). Per Tier 1 #4 the asset
   catalog references these directly (see m3_asset_catalog.js§§201–243).
   ============================================================================ */
(function(){
'use strict';

var svgEl = window.M3Tokens.svgEl;

// ── WLM_TuskenCamp — radial tents, central bonfire, smoke trail ──────
function WLM_TuskenCamp(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('path', {
      d: 'M 50 80 L 30 50 L 50 30 L 70 50 Z',
      fill: p.red, stroke: p.ink, strokeWidth: 1.2
    });
  }

  var children = [];
  // sandy halo
  children.push(svgEl('circle', { cx: 50, cy: 50, r: 40,
                                  fill: p.ground, opacity: 0.5 }));
  // 5 tents in a radial cluster
  [0, 72, 144, 216, 288].forEach(function(angleDeg) {
    var tx = 50 + Math.cos(angleDeg * Math.PI / 180) * 22;
    var ty = 50 + Math.sin(angleDeg * Math.PI / 180) * 22;
    var tent = svgEl('path', {
      d: 'M -8 4 L 0 -10 L 8 4 Z',
      fill: p.paperDark, stroke: p.ink, strokeWidth: 0.5
    });
    var pole = svgEl('line', { x1: 0, y1: -10, x2: 0, y2: 4,
                               stroke: p.ink, strokeWidth: 0.4 });
    children.push(svgEl('g', { transform: 'translate(' + tx + ' ' + ty + ')' },
                       [tent, pole]));
  });

  // central bonfire (+ smoke trail when 'detailed')
  var bonfireKids = [
    svgEl('circle', { r: 5, fill: p.red,   opacity: 0.5 }),
    svgEl('circle', { r: 3, fill: p.amber, opacity: 0.9 })
  ];
  if (lod === 'detailed') {
    bonfireKids.push(svgEl('path', {
      d: 'M 0 -3 Q -2 -10 1 -16 Q -1 -22 2 -28',
      fill: 'none', stroke: p.inkDim, strokeWidth: 1.2, opacity: 0.5
    }));
  }
  children.push(svgEl('g', { transform: 'translate(50 50)' }, bonfireKids));

  // banthas at edges of camp
  if (lod === 'detailed') {
    var bantha1 = svgEl('g', { transform: 'translate(20 78)' }, [
      svgEl('ellipse', { cx: 0, cy: 0, rx: 6, ry: 3,
                         fill: p.paperDark, stroke: p.ink, strokeWidth: 0.5 }),
      svgEl('path', { d: 'M -3 -1 L -5 -3 M 3 -1 L 5 -3',
                      stroke: p.ink, strokeWidth: 0.4 })
    ]);
    var bantha2 = svgEl('g', { transform: 'translate(78 30)' }, [
      svgEl('ellipse', { cx: 0, cy: 0, rx: 5, ry: 2.5,
                         fill: p.paperDark, stroke: p.ink, strokeWidth: 0.5 })
    ]);
    children.push(bantha1);
    children.push(bantha2);
  }

  return svgEl('g', null, children);
}

// ── WLM_Sandcrawler — brick body with treads top and bottom ──────────
function WLM_Sandcrawler(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('rect', {
      x: 20, y: 36, width: 60, height: 28,
      fill: p.paperDark, stroke: p.ink, strokeWidth: 1.2
    });
  }

  var children = [
    // main body
    svgEl('rect', { x: 14, y: 30, width: 72, height: 40,
                    fill: p.paperDark, stroke: p.ink, strokeWidth: 1.3 }),
    // sloped front
    svgEl('path', { d: 'M 86 30 L 92 36 L 92 64 L 86 70',
                    fill: p.paperDark, stroke: p.ink, strokeWidth: 1 })
  ];

  // bottom tread segments (12)
  for (var i = 0; i < 12; i++) {
    children.push(svgEl('rect', {
      x: 16 + i * 6, y: 72, width: 4, height: 6,
      fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.3
    }));
  }
  // top tread segments (12)
  for (var j = 0; j < 12; j++) {
    children.push(svgEl('rect', {
      x: 16 + j * 6, y: 22, width: 4, height: 6,
      fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.3
    }));
  }
  // hull plating lines
  [30, 50, 70].forEach(function(x) {
    children.push(svgEl('line', { x1: x, y1: 30, x2: x, y2: 70,
                                  stroke: p.inkDim, strokeWidth: 0.4 }));
  });

  if (lod === 'detailed') {
    // Jawa-glow windows
    [24, 38, 54, 70].forEach(function(x) {
      children.push(svgEl('rect', { x: x, y: 44, width: 3, height: 4,
                                    fill: p.amber, opacity: 0.8 }));
    });
    // ramp deployed
    children.push(svgEl('path', {
      d: 'M 92 56 L 100 62 L 100 70 L 92 64 Z',
      fill: p.groundDeep, stroke: p.ink, strokeWidth: 0.6
    }));
    // sand trail behind
    children.push(svgEl('path', { d: 'M 4 50 Q 8 44 12 50',
                                  fill: 'none', stroke: p.inkFaint,
                                  strokeWidth: 0.4, opacity: 0.5 }));
    children.push(svgEl('path', { d: 'M 0 60 Q 6 54 12 60',
                                  fill: 'none', stroke: p.inkFaint,
                                  strokeWidth: 0.4, opacity: 0.5 }));
  }

  return svgEl('g', null, children);
}

// ── WLM_AbandonedMine — outcrop, tunnel void, rails, debris ──────────
function WLM_AbandonedMine(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('ellipse', {
      cx: 50, cy: 50, rx: 20, ry: 14,
      fill: p.groundDeep, stroke: p.ink, strokeWidth: 1.2
    });
  }

  var children = [
    // rocky outcrop surrounding
    svgEl('path', { d: 'M 14 70 L 24 32 L 50 20 L 76 32 L 86 70 Z',
                    fill: p.paperDark, stroke: p.ink, strokeWidth: 1.2 }),
    // tunnel entrance — dark void
    svgEl('ellipse', { cx: 50, cy: 64, rx: 20, ry: 14,
                       fill: p.skyDeep, stroke: p.ink, strokeWidth: 1.2 }),
    svgEl('ellipse', { cx: 50, cy: 64, rx: 14, ry: 10,
                       fill: '#000', opacity: 0.85 }),
    // lintel beam
    svgEl('rect', { x: 28, y: 50, width: 44, height: 3,
                    fill: p.ink, opacity: 0.6 }),
    // support posts
    svgEl('rect', { x: 28, y: 50, width: 3, height: 20,
                    fill: p.ink, opacity: 0.6 }),
    svgEl('rect', { x: 69, y: 50, width: 3, height: 20,
                    fill: p.ink, opacity: 0.6 })
  ];

  if (lod === 'detailed') {
    // rail tracks coming out
    children.push(svgEl('line', { x1: 42, y1: 70, x2: 36, y2: 88,
                                  stroke: p.inkDim, strokeWidth: 0.6 }));
    children.push(svgEl('line', { x1: 58, y1: 70, x2: 64, y2: 88,
                                  stroke: p.inkDim, strokeWidth: 0.6 }));
    // crossties
    [74, 78, 82, 86].forEach(function(y) {
      children.push(svgEl('line', {
        x1: 40 - (y - 70) * 0.3, y1: y,
        x2: 60 + (y - 70) * 0.3, y2: y,
        stroke: p.inkDim, strokeWidth: 0.4
      }));
    });
    // mining debris
    children.push(svgEl('circle', { cx: 20, cy: 80, r: 2,
                                    fill: p.groundShadow,
                                    stroke: p.ink, strokeWidth: 0.3 }));
    children.push(svgEl('circle', { cx: 80, cy: 82, r: 1.6,
                                    fill: p.groundShadow,
                                    stroke: p.ink, strokeWidth: 0.3 }));
    // abandoned sign
    children.push(svgEl('rect', { x: 70, y: 26, width: 12, height: 6,
                                  fill: p.paperDark, stroke: p.ink,
                                  strokeWidth: 0.4 }));
    children.push(svgEl('line', { x1: 71, y1: 29, x2: 81, y2: 29,
                                  stroke: p.ink, strokeWidth: 0.3 }));
    // sand-filling
    children.push(svgEl('path', { d: 'M 30 70 Q 50 68 70 70',
                                  fill: 'none', stroke: p.inkFaint,
                                  strokeWidth: 0.4, opacity: 0.6 }));
  }

  return svgEl('g', null, children);
}

// ── WLM_KraytSkeleton — vertebrae, ribs, skull ───────────────────────
function WLM_KraytSkeleton(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    var iconKids = [
      svgEl('line', { x1: 20, y1: 50, x2: 80, y2: 50,
                      stroke: p.inkBright, strokeWidth: 2 })
    ];
    [28, 38, 48, 58, 68].forEach(function(x) {
      iconKids.push(svgEl('circle', { cx: x, cy: 50, r: 2, fill: p.inkBright }));
    });
    return svgEl('g', null, iconKids);
  }

  var children = [
    // bleached sand patch around the bones
    svgEl('ellipse', { cx: 50, cy: 50, rx: 44, ry: 20,
                       fill: p.ground, opacity: 0.6 }),
    // spine — curved
    svgEl('path', { d: 'M 12 56 Q 30 48 50 52 T 88 48',
                    fill: 'none', stroke: p.inkBright, strokeWidth: 1.6 }),
    // skull
    svgEl('ellipse', { cx: 86, cy: 48, rx: 6, ry: 4,
                       fill: p.inkBright, stroke: p.ink, strokeWidth: 0.5 }),
    svgEl('circle', { cx: 88, cy: 47, r: 1, fill: '#000' })
  ];

  // vertebrae beads along the spine
  [20, 28, 36, 44, 52, 60, 68, 76].forEach(function(x) {
    var y = 56 - Math.sin((x - 12) / 76 * Math.PI) * 6;
    children.push(svgEl('circle', { cx: x, cy: y, r: 1.8,
                                    fill: p.inkBright,
                                    stroke: p.ink, strokeWidth: 0.3 }));
  });

  // ribs — two angled lines per vertebra
  [24, 34, 44, 54, 64, 72].forEach(function(x) {
    var y = 56 - Math.sin((x - 12) / 76 * Math.PI) * 6;
    children.push(svgEl('g', null, [
      svgEl('line', { x1: x, y1: y, x2: x - 3, y2: y + 12,
                      stroke: p.inkBright, strokeWidth: 0.9 }),
      svgEl('line', { x1: x, y1: y, x2: x + 3, y2: y + 14,
                      stroke: p.inkBright, strokeWidth: 0.9 })
    ]));
  });

  if (lod === 'detailed') {
    // tail tip vertebrae
    [6, 9, 12].forEach(function(x, idx) {
      children.push(svgEl('circle', { cx: x, cy: 58 + idx * 0.5,
                                      r: 1, fill: p.inkBright }));
    });
    // sand swirls from wind erosion
    children.push(svgEl('path', { d: 'M 24 80 Q 36 76 48 80',
                                  fill: 'none', stroke: p.inkFaint,
                                  strokeWidth: 0.3, opacity: 0.5 }));
    children.push(svgEl('path', { d: 'M 52 78 Q 64 74 76 78',
                                  fill: 'none', stroke: p.inkFaint,
                                  strokeWidth: 0.3, opacity: 0.5 }));
  }

  return svgEl('g', null, children);
}

// ── WLM_JabbaPalace — palace mass with entrance arch ─────────────────
function WLM_JabbaPalace(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('g', null, [
      svgEl('path', {
        d: 'M 30 80 L 30 50 Q 30 30 50 28 Q 70 30 70 50 L 70 80 Z',
        fill: p.fillHutt, stroke: p.ink, strokeWidth: 1.5
      }),
      svgEl('rect', { x: 42, y: 70, width: 16, height: 10,
                      fill: p.skyDeep, stroke: p.ink, strokeWidth: 0.8 })
    ]);
  }

  var children = [
    // rocky base / approaching dunes
    svgEl('path', {
      d: 'M 8 88 Q 30 78 50 84 Q 70 78 92 88 L 92 100 L 8 100 Z',
      fill: p.paperDark, stroke: p.ink, strokeWidth: 0.6, opacity: 0.6
    }),
    // main palace mass — cylindrical-with-dome
    svgEl('path', {
      d: 'M 24 86 L 24 48 Q 24 22 50 18 Q 76 22 76 48 L 76 86 Z',
      fill: p.fillHutt, stroke: p.ink, strokeWidth: 1.4
    }),
    // dome panel line
    svgEl('path', { d: 'M 26 48 Q 50 30 74 48',
                    fill: 'none', stroke: p.inkDim, strokeWidth: 0.4 }),
    svgEl('line', { x1: 24, y1: 62, x2: 76, y2: 62,
                    stroke: p.inkDim, strokeWidth: 0.3 }),
    // entrance arch — dark rectangle behind the curved Hutt-fill arch top
    svgEl('rect', { x: 40, y: 68, width: 20, height: 20,
                    fill: p.skyDeep, stroke: p.ink, strokeWidth: 1.2 }),
    svgEl('path', { d: 'M 40 68 Q 50 60 60 68',
                    fill: p.fillHutt, stroke: p.ink, strokeWidth: 1 }),
    // entrance light
    svgEl('circle', { cx: 50, cy: 76, r: 1.5,
                      fill: p.amber, opacity: 0.8 })
  ];

  if (lod === 'detailed') {
    // watchtowers flanking
    children.push(svgEl('rect', { x: 18, y: 56, width: 6, height: 10,
                                  fill: p.fillHutt, stroke: p.ink,
                                  strokeWidth: 0.6 }));
    children.push(svgEl('rect', { x: 76, y: 56, width: 6, height: 10,
                                  fill: p.fillHutt, stroke: p.ink,
                                  strokeWidth: 0.6 }));
    // lit narrow windows
    [40, 50, 60].forEach(function(x) {
      children.push(svgEl('rect', { x: x - 0.5, y: 38,
                                    width: 1.4, height: 3,
                                    fill: p.amber, opacity: 0.7 }));
    });
    // parked sail barge
    children.push(svgEl('ellipse', { cx: 86, cy: 92, rx: 10, ry: 2.5,
                                     fill: p.paperDark, stroke: p.ink,
                                     strokeWidth: 0.5 }));
    // hutt sigil above arch — Egyptian crocodile glyph, matches SP_Hutt
    children.push(svgEl('text', {
      x: 50, y: 26,
      fontSize: 6, textAnchor: 'middle', fill: p.gold, opacity: 0.6,
      fontFamily: 'serif', fontWeight: 700
    }, ['\uD80C\uDD97']));
    // approach road
    children.push(svgEl('path', {
      d: 'M 50 88 L 30 100 M 50 88 L 70 100',
      stroke: p.inkFaint, strokeWidth: 0.5, strokeDasharray: '2 2'
    }));
  }

  return svgEl('g', null, children);
}

// ── WLM_MoistureFarm — dome and vaporator cluster ────────────────────
function WLM_MoistureFarm(o) {
  var p = o.p;
  var lod = o.lod || 'detailed';

  if (lod === 'icon') {
    return svgEl('circle', { cx: 50, cy: 56, r: 18,
                             fill: p.fillHousing,
                             stroke: p.ink, strokeWidth: 1 });
  }

  var children = [
    // main dome
    svgEl('circle', { cx: 50, cy: 58, r: 20,
                      fill: p.fillHousing, stroke: p.ink, strokeWidth: 1 }),
    svgEl('circle', { cx: 50, cy: 58, r: 14,
                      fill: 'none', stroke: p.inkDim, strokeWidth: 0.3 }),
    // entrance
    svgEl('rect', { x: 47, y: 76, width: 6, height: 4,
                    fill: p.groundShadow, stroke: p.ink, strokeWidth: 0.4 })
  ];

  // vaporator field — 6 stations
  var vaporators = [[20, 28], [78, 30], [20, 70],
                    [78, 78], [42, 18], [60, 18]];
  vaporators.forEach(function(pos) {
    var x = pos[0], y = pos[1];
    children.push(svgEl('g', { transform: 'translate(' + x + ' ' + y + ')' }, [
      svgEl('circle', { r: 2, fill: p.paperDark,
                        stroke: p.ink, strokeWidth: 0.4 }),
      svgEl('circle', { r: 0.8, fill: p.cyan, opacity: 0.6 }),
      svgEl('line', { x1: 0, y1: -2, x2: 0, y2: -4,
                      stroke: p.ink, strokeWidth: 0.4 })
    ]));
  });

  if (lod === 'detailed') {
    // connecting condenser lines — only to the 4 corner vaporators
    [[20, 28], [78, 30], [20, 70], [78, 78]].forEach(function(pos) {
      children.push(svgEl('line', {
        x1: 50, y1: 58, x2: pos[0], y2: pos[1],
        stroke: p.inkFaint, strokeWidth: 0.3, strokeDasharray: '1 1'
      }));
    });
  }

  return svgEl('g', null, children);
}

// WILDERNESS_LANDMARKS is keyed by short slug, matching the contract the
// composition engine uses (composition engine looks up `wlm[room.slug]`,
// where slug is e.g. 'tusken_camp' from world YAML).
//
// The asset catalog (m3_asset_catalog.js Drop 4.1b §220-225) keys its
// entries by long ident (e.g. 'WLM_TuskenCamp') matching the JSX function
// name. To bridge the two key conventions, this file also exposes each
// builder by its long ident on the M3AssetsWilderness namespace; the
// catalog can fall back to those when its short-slug lookup misses.
var WILDERNESS_LANDMARKS = {
  tusken_camp:      WLM_TuskenCamp,
  sandcrawler:      WLM_Sandcrawler,
  abandoned_mine:   WLM_AbandonedMine,
  krayt_skeleton:   WLM_KraytSkeleton,
  jabba_palace:     WLM_JabbaPalace,
  moisture_farm:    WLM_MoistureFarm
};

window.M3AssetsWilderness = {
  WILDERNESS_LANDMARKS: WILDERNESS_LANDMARKS,
  // Individual builders by long ident — for catalog's WLM_* lookup form.
  WLM_TuskenCamp:     WLM_TuskenCamp,
  WLM_Sandcrawler:    WLM_Sandcrawler,
  WLM_AbandonedMine:  WLM_AbandonedMine,
  WLM_KraytSkeleton:  WLM_KraytSkeleton,
  WLM_JabbaPalace:    WLM_JabbaPalace,
  WLM_MoistureFarm:   WLM_MoistureFarm
};

})();
