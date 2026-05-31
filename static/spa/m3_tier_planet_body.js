/* ============================================================================
   m3_tier_planet_body.js — Tier 3 Planet renderer (Tatooine).

   Drop 4.13 (Batch 1, outer-tier triplet) · Tier 1 #4 · ported from
   map_v3/tier-three.jsx (235 JSX LOC) in SW_MUSH_UIUX_Bugfix_26May26.zip
   (May 27 2026).

   This is the third-outermost zoom of the SPA map navigator's tier
   ladder — the planet-scale Tatooine view between system view (4a)
   and city view (Tier 2). Stylized top-down disk with:
     · Space-background grain (80 stars)
     · Twin-sun bloom over upper area (radial gradients)
     · Planet disk with radial body gradient + terminator shadow +
       atmospheric halo
     · 5 wilderness regions as terrain-tinted polygons (Dune Sea,
       Jundland Wastes, Northern Dunes, Xelric Basin, Outer Wastes)
     · 8 cities with mini skyline silhouettes (Mos Eisley player,
       Anchorhead, Mos Entha, Mos Espa, Tosche Station, Bestine)
       + 2 landmark glyphs (Jabba's Palace, Pit of Carkoon hazard)
     · 6 arrowed travel routes between cities
     · Hyperspace beacon pulsing at Mos Eisley
     · Time-of-day overlay (via OV_TimeOfDay from M3AssetsOverlays)
     · Atmosphere haze ring at planet edge
     · Planet name + sector subtitle
     · Twin-sun annotations
     · Compass rose (via CompassRose from M3CompositionEngine)
     · Scale bar

   Two surfaces (matches JSX source):
     · buildTierThreeBody(p, opts?)     — SVG only, for embedding
     · buildTierThreeTatooine(p, opts?) — SVG wrapped in HolocartaFrame
                                           (the chrome'd version)

   What this module ships:
     · M3TierPlanetBody.buildTierThreeBody(p, opts?)
            inner SVG renderer; signature compatible with the
            getTierRenderer DI seam in M3MapNavigator (Drop 4.8) and
            M3AssembledClient.MiniMap (Drop 4.12b). Returns <svg>.
     · M3TierPlanetBody.buildTierThreeTatooine(p, opts?)
            chrome'd version using HolocartaFrame from
            M3CompositionEngine. Returns the frame's outer HTMLDivElement
            (or a labeled fallback if HolocartaFrame is unavailable).
     · M3TierPlanetBody.CITIES           8-city + landmark fixture
     · M3TierPlanetBody.REGIONS          5-region fixture array
     · M3TierPlanetBody.TRAVEL_ROUTES    6-route fixture array

   B3 era-cleanness:
     · Era subtitle "ARKANIS SECTOR · OUTER RIM · 20 BBY"
     · All city/landmark names are Tatooine-canonical (era-neutral).
     · Zero Empire/Imperial/TIE/X-wing/Rebel/Stormtrooper/Vader/Death
       Star/ISB references in data blocks.

   Q1 canonical-character policy note (architecture v50 §6.2):
     · "JABBA'S PALACE" — canonical-character-adjacent landmark name,
       preserved verbatim from JSX source per Drop 4.6 / 4.7 / 4.10 /
       4.11 / 4.12 source-fidelity policy. Tracked in Q1 cleanup queue.
     · "PIT OF CARKOON" — same. Canonical sarlacc-pit landmark adjacent
       to Jabba's territory. Preserved per same policy.

   Palette keys consumed:
     p.amber, p.cyan, p.green, p.gold, p.red, p.ink, p.inkBright,
     p.inkDim, p.skyDeep
     · p.paper        — UNDOCUMENTED key from JSX source. Fallback to
                        p.inkBright per Drop 4.11 loud-substitution.
     · p.ground       — UNDOCUMENTED. Fallback to p.amber.
     · p.groundDeep   — UNDOCUMENTED. Fallback to p.skyDeep.
     · p.groundShadow — UNDOCUMENTED. Fallback to p.skyDeep.
     (Standard palettes lacking these keys still render the planet
     body — the gradient just degrades to amber/skyDeep transitions.)

   Dependencies (consumed via defensive DI):
     · window.M3CompositionEngine.HolocartaFrame
            used by buildTierThreeTatooine. If unavailable, the
            chrome'd version returns a labeled placeholder.
     · window.M3CompositionEngine.CompassRose
            optional decoration. If unavailable, skipped silently.
     · window.M3AssetsOverlays.TerrainDefs / HazeDefs / OV_TimeOfDay
            optional. If unavailable, the relevant <defs>/overlays
            are skipped — terrain polygons render as solid color.

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
var REGIONS = [
  // [path-d, label, fill-id, opacity, label-x, label-y, label-size]
  ['M 480 280 Q 600 320 580 460 Q 540 540 440 520 Q 400 480 420 380 Q 440 300 480 280 Z',
   'DUNE SEA',         'url(#terr-dune)',   0.85, 510, 400, 11, 4,  'inkBright'],
  ['M 320 270 Q 420 250 460 310 Q 440 380 380 400 Q 300 380 280 320 Q 290 280 320 270 Z',
   'JUNDLAND WASTES',  'url(#terr-canyon)', 0.80, 370, 330, 10, 3,  'inkBright'],
  ['M 200 220 Q 280 200 360 230 Q 340 260 280 270 Q 220 260 200 220 Z',
   'NORTHERN DUNES',   'url(#terr-dune)',   0.70, 280, 244, 9,  2,  'inkDim'],
  ['M 140 360 Q 200 320 260 360 Q 240 430 180 440 Q 130 410 140 360 Z',
   'XELRIC BASIN',     'url(#terr-scrub)',  0.80, 200, 400, 9,  2,  'inkDim'],
  ['M 240 500 Q 350 540 440 530 Q 460 580 360 600 Q 260 590 240 540 Z',
   'OUTER WASTES',     'url(#terr-dune)',   0.85, 340, 560, 9,  2,  'inkDim']
];

var CITIES = [
  // Q1 watch: "JABBA'S PALACE" and "PIT OF CARKOON" preserved per
  // source-fidelity policy. See module header.
  { x: 300, y: 295, name: 'MOS EISLEY',     player: true,  size: 9 },
  { x: 250, y: 380, name: 'ANCHORHEAD',     size: 7 },
  { x: 410, y: 470, name: "JABBA'S PALACE", landmark: true, size: 8 },
  { x: 380, y: 350, name: 'MOS ENTHA',      size: 7 },
  { x: 200, y: 470, name: 'MOS ESPA',       size: 8 },
  { x: 480, y: 380, name: 'TOSCHE STATION', size: 6 },
  { x: 530, y: 480, name: 'PIT OF CARKOON', landmark: true, hazard: true, size: 7 },
  { x: 320, y: 530, name: 'BESTINE',        size: 7 }
];

var TRAVEL_ROUTES = [
  // [[fromX, fromY], [toX, toY]]
  [[300, 295], [380, 350]],   // Eisley → Entha
  [[300, 295], [250, 380]],   // Eisley → Anchorhead
  [[250, 380], [200, 470]],   // Anchorhead → Espa
  [[380, 350], [410, 470]],   // Entha → Jabba
  [[410, 470], [320, 530]],   // Jabba → Bestine
  [[380, 350], [480, 380]]    // Entha → Tosche
];

// ════════════════════════════════════════════════════════════════════
// buildTierThreeBody(p, opts?) → <svg>
//
// Signature compatible with the getTierRenderer DI seam:
//   hooks.getTierRenderer('3', { p, width, height, time }) → element
// ════════════════════════════════════════════════════════════════════
function buildTierThreeBody(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierThreeBody: palette argument required');

  var width  = opts.width  || 700;
  var height = opts.height || 700;
  var time   = opts.time   || 'day';

  // Loud-substitution fallbacks for undocumented palette keys.
  var paper        = p.paper        || p.inkBright;
  var ground       = p.ground       || p.amber;
  var groundDeep   = p.groundDeep   || p.skyDeep;
  // groundShadow not used in this module — see tier-4a for that one.

  // Defensive DI for overlay helpers.
  var overlays = (typeof window !== 'undefined' && window.M3AssetsOverlays) || {};
  var TerrainDefs = overlays.TerrainDefs;
  var HazeDefs    = overlays.HazeDefs;
  var OV_TimeOfDay = overlays.OV_TimeOfDay;

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

  // Local defs: twin-sun glows, planet body, terminator shadow.
  var defs = svgEl('defs', null, [
    svgEl('radialGradient', { id: 'tw-sun-1', cx: '35%', cy: '20%', r: '40%' }, [
      svgEl('stop', { offset: '0%',   stopColor: p.amber, stopOpacity: 0.25 }),
      svgEl('stop', { offset: '100%', stopColor: p.amber, stopOpacity: 0 })
    ]),
    svgEl('radialGradient', { id: 'tw-sun-2', cx: '65%', cy: '25%', r: '40%' }, [
      svgEl('stop', { offset: '0%',   stopColor: p.gold, stopOpacity: 0.20 }),
      svgEl('stop', { offset: '100%', stopColor: p.gold, stopOpacity: 0 })
    ]),
    svgEl('radialGradient', { id: 'planet-body', cx: '40%', cy: '35%', r: '65%' }, [
      svgEl('stop', { offset: '0%',   stopColor: paper }),
      svgEl('stop', { offset: '50%',  stopColor: ground }),
      svgEl('stop', { offset: '100%', stopColor: groundDeep })
    ]),
    svgEl('radialGradient', { id: 'planet-shadow', cx: '80%', cy: '80%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   stopColor: p.skyDeep, stopOpacity: 0.55 }),
      svgEl('stop', { offset: '100%', stopColor: 'transparent' })
    ])
  ]);
  children.push(defs);

  // Space-background grain (80 stars, deterministic).
  for (var i = 0; i < 80; i++) {
    var sx = (i * 53) % 700;
    var sy = (i * 47) % 700;
    children.push(svgEl('circle', {
      cx: sx, cy: sy, r: 0.5, fill: p.inkBright, opacity: 0.4
    }));
  }

  // Twin sun bloom over upper area.
  children.push(svgEl('rect', {
    x: 0, y: 0, width: 700, height: 700, fill: 'url(#tw-sun-1)'
  }));
  children.push(svgEl('rect', {
    x: 0, y: 0, width: 700, height: 700, fill: 'url(#tw-sun-2)'
  }));

  // Planet disk.
  children.push(svgEl('circle', {
    cx: 350, cy: 360, r: 290, fill: 'url(#planet-body)',
    stroke: p.ink, strokeWidth: 1.5
  }));
  // Terminator shadow.
  children.push(svgEl('circle', {
    cx: 350, cy: 360, r: 290, fill: 'url(#planet-shadow)'
  }));
  // Atmospheric halo.
  children.push(svgEl('circle', {
    cx: 350, cy: 360, r: 300, fill: 'none',
    stroke: p.amber, strokeWidth: 0.6, opacity: 0.4
  }));
  children.push(svgEl('circle', {
    cx: 350, cy: 360, r: 310, fill: 'none',
    stroke: p.amber, strokeWidth: 0.3, opacity: 0.2
  }));

  // Wilderness regions.
  var regionChildren = [];
  for (var ri = 0; ri < REGIONS.length; ri++) {
    var reg = REGIONS[ri];
    var rPath = reg[0], rLabel = reg[1], rFill = reg[2], rOp = reg[3];
    var rLabelX = reg[4], rLabelY = reg[5], rLabelSize = reg[6];
    var rLabelLetterSpacing = reg[7], rLabelColorKey = reg[8];
    regionChildren.push(svgEl('path', {
      'data-region': rLabel,
      d: rPath,
      fill: rFill,
      opacity: rOp,
      stroke: p.inkDim,
      strokeWidth: 0.5 + (rOp > 0.8 ? 0.1 : 0)  // tiny mod for visual
    }));
    regionChildren.push(svgEl('text', {
      x: rLabelX, y: rLabelY, fontSize: rLabelSize,
      fill: p[rLabelColorKey] || p.inkDim,
      textAnchor: 'middle',
      style: { letterSpacing: rLabelLetterSpacing }
    }, [rLabel]));
  }
  children.push(svgEl('g', { 'data-regions': '1' }, regionChildren));

  // Cities + landmarks.
  for (var ci = 0; ci < CITIES.length; ci++) {
    var c = CITIES[ci];
    var dotColor = c.player    ? p.cyan
                 : c.hazard    ? p.red
                 : c.landmark  ? p.gold
                 :               p.amber;

    var cityKids = [];

    // Mini city skyline silhouette (skip for landmarks and hazards).
    if (!c.landmark && !c.hazard) {
      cityKids.push(svgEl('g', {
        transform: 'translate(0 ' + (-c.size - 3) + ')'
      }, [
        svgEl('path', {
          d: 'M ' + (-c.size - 1) + ' 0 L ' + (-c.size - 1) + ' -3 ' +
             'L ' + (-c.size + 3) + ' -3 L ' + (-c.size + 3) + ' -5 ' +
             'L -1 -5 L -1 -7 ' +
             'L 1 -7 L 1 -4 ' +
             'L ' + (c.size - 2) + ' -4 L ' + (c.size - 2) + ' -2 ' +
             'L ' + (c.size + 1) + ' -2 L ' + (c.size + 1) + ' 0 Z',
          fill: p.ink, opacity: 0.7
        })
      ]));
    }

    // Landmark glyph (diamond/rhombus).
    if (c.landmark && !c.player) {
      var diamondPts = '0,' + (-c.size - 2) + ' ' +
                       (c.size - 1) + ',0 ' +
                       '0,' + (c.size - 2) + ' ' +
                       (-c.size + 1) + ',0';
      cityKids.push(svgEl('polygon', {
        points: diamondPts,
        fill: dotColor, stroke: p.ink, strokeWidth: 0.5
      }));
    }

    // Dot (skip for landmarks — they got the diamond above).
    if (!c.landmark) {
      cityKids.push(svgEl('circle', {
        r: c.size * 0.5, fill: dotColor, stroke: p.ink, strokeWidth: 0.5,
        style: {
          filter: c.player ? 'drop-shadow(0 0 4px ' + dotColor + ')' : 'none'
        }
      }));
    }

    // Player pulse.
    if (c.player) {
      cityKids.push(svgEl('circle', {
        r: c.size * 0.6, fill: 'none', stroke: p.cyan,
        strokeWidth: 0.6, opacity: 0.5
      }, [
        svgEl('animate', {
          attributeName: 'r',
          values: (c.size * 0.6) + ';' + (c.size * 1.6) + ';' + (c.size * 0.6),
          dur: '2s', repeatCount: 'indefinite'
        }),
        svgEl('animate', {
          attributeName: 'opacity', values: '0.6;0;0.6',
          dur: '2s', repeatCount: 'indefinite'
        })
      ]));
    }

    // Label.
    cityKids.push(svgEl('text', {
      x: 0, y: c.size + 12, fontSize: c.player ? 11 : 9,
      textAnchor: 'middle',
      fill: c.player ? p.inkBright : p.ink,
      style: { letterSpacing: 2, fontWeight: c.player ? 700 : 400 }
    }, [c.name]));

    children.push(svgEl('g', {
      'data-city': c.name,
      'data-city-player': c.player ? '1' : '0',
      'data-city-landmark': c.landmark ? '1' : '0',
      'data-city-hazard': c.hazard ? '1' : '0',
      transform: 'translate(' + c.x + ' ' + c.y + ')'
    }, cityKids));
  }

  // Travel routes with arrow heads.
  var routeChildren = [];
  for (var tri = 0; tri < TRAVEL_ROUTES.length; tri++) {
    var route = TRAVEL_ROUTES[tri];
    var rx1 = route[0][0], ry1 = route[0][1];
    var rx2 = route[1][0], ry2 = route[1][1];
    routeChildren.push(svgEl('g', null, [
      svgEl('line', {
        x1: rx1, y1: ry1, x2: rx2, y2: ry2,
        stroke: p.inkDim, strokeWidth: 0.5,
        strokeDasharray: '3 3', opacity: 0.6
      }),
      _arrowHead(rx1, ry1, rx2, ry2, p.inkDim)
    ]));
  }
  children.push(svgEl('g', {
    'data-travel-routes': '1',
    style: { pointerEvents: 'none' }
  }, routeChildren));

  // Hyperspace beacon at Mos Eisley.
  children.push(svgEl('g', {
    'data-hyperspace-beacon': 'MOS EISLEY',
    transform: 'translate(300 295)'
  }, [
    svgEl('circle', {
      r: 18, fill: 'none', stroke: p.green,
      strokeWidth: 0.4, opacity: 0.3
    }, [
      svgEl('animate', {
        attributeName: 'r', values: '16;22;16',
        dur: '3s', repeatCount: 'indefinite'
      })
    ]),
    svgEl('circle', {
      r: 4, fill: 'none', stroke: p.green, strokeWidth: 1
    }),
    svgEl('circle', { r: 1.5, fill: p.green })
  ]));

  // Time-of-day overlay (optional).
  if (OV_TimeOfDay) {
    try {
      var tod = OV_TimeOfDay({ time: time, width: 700, height: 700 });
      if (tod) children.push(tod);
    } catch (e) { /* skip */ }
  }

  // Atmosphere haze ring at planet edge.
  children.push(svgEl('circle', {
    cx: 350, cy: 360, r: 295, fill: 'none',
    stroke: p.amber, strokeWidth: 2.5, opacity: 0.15
  }));

  // Planet name + sector subtitle.
  children.push(svgEl('text', {
    x: 350, y: 56, fontSize: 22, textAnchor: 'middle', fill: p.inkBright,
    style: {
      letterSpacing: 8, fontWeight: 600,
      textShadow: '0 0 8px ' + p.amber
    }
  }, ['TATOOINE']));
  children.push(svgEl('text', {
    x: 350, y: 72, fontSize: 9, textAnchor: 'middle', fill: p.inkDim,
    style: { letterSpacing: 4 }
  }, ['ARKANIS SECTOR · OUTER RIM · 20 BBY']));

  // Twin-sun annotations.
  children.push(svgEl('g', {
    transform: 'translate(160, 110)'
  }, [
    svgEl('circle', { r: 5, fill: p.amber }),
    svgEl('circle', {
      r: 11, fill: 'none', stroke: p.amber,
      strokeWidth: 0.4, opacity: 0.5
    })
  ]));
  children.push(svgEl('g', {
    transform: 'translate(200, 80)'
  }, [
    svgEl('circle', { r: 4, fill: p.gold }),
    svgEl('circle', {
      r: 9, fill: 'none', stroke: p.gold,
      strokeWidth: 0.3, opacity: 0.5
    })
  ]));
  children.push(svgEl('text', {
    x: 180, y: 140, fontSize: 8, textAnchor: 'middle', fill: p.inkDim,
    style: { letterSpacing: 1.5 }
  }, ['TATOO I · TATOO II']));

  // Compass rose (optional).
  if (CompassRose) {
    try {
      var compass = CompassRose({ p: p, x: width - 60, y: height - 60 });
      if (compass) children.push(compass);
    } catch (e) { /* skip */ }
  }

  // Scale bar.
  children.push(svgEl('g', {
    'data-scale-bar': '1',
    transform: 'translate(40, 660)'
  }, [
    svgEl('line', {
      x1: 0, y1: 0, x2: 80, y2: 0, stroke: p.ink, strokeWidth: 1
    }),
    svgEl('line', {
      x1: 0, y1: -3, x2: 0, y2: 3, stroke: p.ink, strokeWidth: 1
    }),
    svgEl('line', {
      x1: 80, y1: -3, x2: 80, y2: 3, stroke: p.ink, strokeWidth: 1
    }),
    svgEl('text', {
      x: 40, y: 14, fontSize: 8, fill: p.inkDim, textAnchor: 'middle',
      style: { letterSpacing: 1.5 }
    }, ['~ 2,000 km'])
  ]));

  return svgEl('svg', {
    'data-tier-planet': '1',
    width: width, height: height,
    viewBox: '0 0 700 700',
    style: { display: 'block', background: p.skyDeep }
  }, children);
}

// Helper for arrow heads on travel-route lines.
function _arrowHead(x1, y1, x2, y2, color) {
  var a = Math.atan2(y2 - y1, x2 - x1);
  var ax = x2 - Math.cos(a) * 12;
  var ay = y2 - Math.sin(a) * 12;
  var leftX  = ax - 3 * Math.cos(a - 0.4);
  var leftY  = ay - 3 * Math.sin(a - 0.4);
  var rightX = ax - 3 * Math.cos(a + 0.4);
  var rightY = ay - 3 * Math.sin(a + 0.4);
  return svgEl('path', {
    d: 'M ' + ax + ' ' + ay +
       ' L ' + leftX + ' ' + leftY +
       ' L ' + rightX + ' ' + rightY + ' Z',
    fill: color, opacity: 0.6
  });
}

// ════════════════════════════════════════════════════════════════════
// buildTierThreeTatooine(p, opts?)
// Chrome-wrapped variant — uses HolocartaFrame if available.
// ════════════════════════════════════════════════════════════════════
function buildTierThreeTatooine(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierThreeTatooine: palette argument required');

  var width  = opts.width  || 700;
  var height = opts.height || 700;
  var time   = opts.time   || 'day';

  // Defensive DI for HolocartaFrame.
  var compEng = (typeof window !== 'undefined' && window.M3CompositionEngine) || {};
  var HolocartaFrame = compEng.HolocartaFrame;

  var innerSvg = buildTierThreeBody(p, {
    width: width, height: height, time: time
  });

  if (!HolocartaFrame) {
    // Labeled fallback — return the bare SVG with a wrapping div that
    // makes it obvious the frame is missing.
    return htmlEl('div', {
      'data-tier-planet-frame-fallback': '1',
      style: {
        position: 'relative', width: width, height: height + 64,
        background: p.skyDeep, color: p.inkDim,
        fontSize: 9, letterSpacing: 2,
        fontFamily: "'IBM Plex Mono', monospace"
      }
    }, [
      htmlEl('div', {
        style: { padding: '4px 8px', borderBottom: '1px solid ' + p.inkDim }
      }, ['HOLOCARTA FRAME · M3CompositionEngine.HolocartaFrame not loaded']),
      innerSvg
    ]);
  }

  return HolocartaFrame({
    p: p,
    width: width,
    height: height + 64,
    breadcrumb: 'GALAXY \u25b8 OUTER RIM \u25b8 ARKANIS SECTOR \u25b8 TATOOINE',
    tier: '3 · PLANET',
    legend: [
      { color: p.cyan,  shape: 'circle', glow: true, label: 'YOU · MOS EISLEY' },
      { color: p.amber, shape: 'circle', label: 'CITY' },
      { color: p.gold,  shape: 'circle', label: 'LANDMARK' },
      { color: p.red,   shape: 'tri',    label: 'HOSTILE TERRITORY' },
      { color: p.green, shape: 'circle', label: 'BEACON' }
    ],
    children: [innerSvg]
  });
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3TierPlanetBody = {
  SCHEMA_VERSION: 1,

  // Top-level
  buildTierThreeBody:     buildTierThreeBody,
  buildTierThreeTatooine: buildTierThreeTatooine,

  // Fixtures (public for downstream composition / Q1 audits)
  CITIES:         CITIES,
  REGIONS:        REGIONS,
  TRAVEL_ROUTES:  TRAVEL_ROUTES,

  _internal: { _svgEl: svgEl, _htmlEl: htmlEl, _arrowHead: _arrowHead }
};

})();
