/* ============================================================================
   m3_assets_overlays.js — terrain patterns + atmospheric overlays for the SPA map.

   Drop 4.1c · Tier 1 #4 · ported from map_v3/assets-overlays.jsx (May 26 2026).

   Two related concerns in one module:

     1. TERRAIN PATTERNS — SVG <pattern> defs that paint the substrate
        beneath rooms. The composition engine references these by id
        (`fill="url(#terr-dune)"`, etc.) on the world background rect.
        TerrainDefs(p) returns a single <defs> element containing all
        seven patterns; HazeDefs(p) returns the radial-gradient defs
        used by OV_SandHaze.

     2. ATMOSPHERIC OVERLAYS — drawn on top of everything (time of day,
        twin-sun shadows, sandstorm, smog, neon halos, faction territory
        polygons, contest banners). Activation rules per architecture
        v50 §7.13.5.

   Each overlay builder takes an options object and returns either an
   SVG element (`<g>`/`<rect>`) or null when the overlay shouldn't render
   (e.g. OV_TwinSunShadows returns null on non-binary-star palettes).

   Public API: window.M3AssetsOverlays — TerrainDefs, HazeDefs, and an
   OVERLAYS dict keyed by overlay name (`twin_sun_shadows`, `time_of_day`,
   `sand_haze`, `sandstorm`, `rain`, `smog`, `neon_halos`, `faction_territory`,
   `contest_banner`). The composition engine in 4.1e will pick which to
   render based on planet, weather event, and active overlays config.

   Terrain catalog gating: the catalog (m3_asset_catalog.js Drop 4.1b §388)
   currently gates the terrain-tile preview on `window.M3CompositionEngine`
   not on this module — so terrain tiles still show '(loading)' here in 4.1c
   and will light up when the composition engine (4.1e) re-exports
   terrainDefs. That's intentional: the catalog wants a single point of
   indirection so terrain rendering can be re-tested through the engine,
   not just the raw defs.
   ============================================================================ */
(function(){
'use strict';

var svgEl = window.M3Tokens.svgEl;

// ────────────────────────────────────────────────────────────────
// TERRAIN PATTERNS — <defs> referenced by the composition engine.
// ────────────────────────────────────────────────────────────────

// Each helper builds one named <pattern>. They're broken out so that
// TerrainDefs() reads as a flat list of "here are the terrains" rather
// than one giant nested function.

function patternDune(p) {
  var kids = [
    svgEl('rect', { width: 120, height: 80, fill: p.ground }),
    // large undulating ridges
    svgEl('path', { d: 'M -10 30 Q 20 22 50 30 T 110 30 T 170 30',
                    fill: 'none', stroke: p.groundDeep,
                    strokeWidth: 0.6, opacity: 0.5 }),
    svgEl('path', { d: 'M -10 55 Q 25 47 55 55 T 115 55 T 175 55',
                    fill: 'none', stroke: p.groundDeep,
                    strokeWidth: 0.6, opacity: 0.5 }),
    // finer ripples
    svgEl('path', { d: 'M 0 18 Q 12 14 24 18 T 48 18 T 72 18 T 96 18 T 120 18',
                    fill: 'none', stroke: p.inkFaint,
                    strokeWidth: 0.3, opacity: 0.5 }),
    svgEl('path', { d: 'M 0 42 Q 15 38 30 42 T 60 42 T 90 42 T 120 42',
                    fill: 'none', stroke: p.inkFaint,
                    strokeWidth: 0.3, opacity: 0.5 }),
    svgEl('path', { d: 'M 0 66 Q 14 62 28 66 T 56 66 T 84 66 T 120 66',
                    fill: 'none', stroke: p.inkFaint,
                    strokeWidth: 0.3, opacity: 0.5 })
  ];
  // scattered grit
  [[12,10],[40,8],[70,12],[100,6],[20,38],[60,40],[88,36],[110,42],
   [16,68],[50,72],[80,70],[105,74]].forEach(function(pt) {
    kids.push(svgEl('circle', {
      cx: pt[0], cy: pt[1], r: 0.4,
      fill: p.groundShadow, opacity: 0.6
    }));
  });
  // wind streaks
  kids.push(svgEl('path', { d: 'M 0 12 L 8 12',
                            stroke: p.inkFaint, strokeWidth: 0.25, opacity: 0.4 }));
  kids.push(svgEl('path', { d: 'M 40 50 L 52 50',
                            stroke: p.inkFaint, strokeWidth: 0.25, opacity: 0.4 }));
  kids.push(svgEl('path', { d: 'M 80 8 L 92 8',
                            stroke: p.inkFaint, strokeWidth: 0.25, opacity: 0.4 }));
  return svgEl('pattern', {
    id: 'terr-dune', x: 0, y: 0, width: 120, height: 80,
    patternUnits: 'userSpaceOnUse'
  }, kids);
}

function patternDuracrete(p) {
  return svgEl('pattern', {
    id: 'terr-duracrete', x: 0, y: 0, width: 60, height: 60,
    patternUnits: 'userSpaceOnUse'
  }, [
    svgEl('rect', { width: 60, height: 60, fill: p.groundDeep }),
    // slab cracks
    svgEl('path', { d: 'M 0 22 L 60 22',
                    stroke: p.inkFaint, strokeWidth: 0.3, opacity: 0.3 }),
    svgEl('path', { d: 'M 0 44 L 60 44',
                    stroke: p.inkFaint, strokeWidth: 0.3, opacity: 0.3 }),
    svgEl('path', { d: 'M 22 0 L 22 60',
                    stroke: p.inkFaint, strokeWidth: 0.3, opacity: 0.3 }),
    svgEl('path', { d: 'M 42 0 L 42 60',
                    stroke: p.inkFaint, strokeWidth: 0.3, opacity: 0.3 }),
    // wear spots
    svgEl('circle', { cx: 14, cy: 32, r: 2,
                      fill: p.groundShadow, opacity: 0.5 }),
    svgEl('circle', { cx: 48, cy: 18, r: 1.5,
                      fill: p.groundShadow, opacity: 0.4 }),
    svgEl('circle', { cx: 32, cy: 50, r: 1.8,
                      fill: p.groundShadow, opacity: 0.5 })
  ]);
}

function patternScrub(p) {
  var kids = [
    svgEl('rect', { width: 80, height: 80, fill: p.groundDeep, opacity: 0.7 })
  ];
  // rock outcrops
  [[14,16,3],[48,28,2.2],[24,52,2.8],[64,60,2.4],
   [8,68,1.8],[72,12,2]].forEach(function(spec) {
    kids.push(svgEl('ellipse', {
      cx: spec[0], cy: spec[1], rx: spec[2], ry: spec[2] * 0.6,
      fill: p.groundShadow, stroke: p.inkFaint, strokeWidth: 0.3
    }));
  });
  // scrub tufts — 3-line bursts
  [[30,22],[58,18],[18,40],[44,46],
   [68,38],[12,58],[40,68],[62,72]].forEach(function(pt) {
    var x = pt[0], y = pt[1];
    kids.push(svgEl('g', null, [
      svgEl('line', { x1: x, y1: y, x2: x - 1.5, y2: y - 2.5,
                      stroke: p.inkFaint, strokeWidth: 0.3 }),
      svgEl('line', { x1: x, y1: y, x2: x + 1.5, y2: y - 2.5,
                      stroke: p.inkFaint, strokeWidth: 0.3 }),
      svgEl('line', { x1: x, y1: y, x2: x,         y2: y - 3,
                      stroke: p.inkFaint, strokeWidth: 0.3 })
    ]));
  });
  return svgEl('pattern', {
    id: 'terr-scrub', x: 0, y: 0, width: 80, height: 80,
    patternUnits: 'userSpaceOnUse'
  }, kids);
}

function patternCanyon(p) {
  var kids = [
    svgEl('rect', { width: 100, height: 70, fill: p.groundDeep })
  ];
  // striated layers
  [10, 22, 34, 46, 58].forEach(function(y) {
    kids.push(svgEl('path', {
      d: 'M 0 ' + y + ' Q 25 ' + (y - 2) + ' 50 ' + y + ' T 100 ' + y,
      fill: 'none', stroke: p.inkFaint, strokeWidth: 0.4, opacity: 0.6
    }));
  });
  // deep shadow gulleys
  kids.push(svgEl('path', { d: 'M 20 0 Q 30 30 25 70',
                            fill: 'none', stroke: p.skyDeep,
                            strokeWidth: 1.5, opacity: 0.5 }));
  kids.push(svgEl('path', { d: 'M 70 0 Q 60 30 75 70',
                            fill: 'none', stroke: p.skyDeep,
                            strokeWidth: 1.2, opacity: 0.5 }));
  return svgEl('pattern', {
    id: 'terr-canyon', x: 0, y: 0, width: 100, height: 70,
    patternUnits: 'userSpaceOnUse'
  }, kids);
}

function patternOasis(p) {
  var kids = [
    svgEl('rect', { width: 100, height: 100, fill: p.groundDeep }),
    svgEl('ellipse', { cx: 50, cy: 50, rx: 30, ry: 20,
                       fill: p.cyan, opacity: 0.3 }),
    svgEl('ellipse', { cx: 50, cy: 50, rx: 22, ry: 14,
                       fill: p.cyan, opacity: 0.5 })
  ];
  // palm-equivalents
  [[28,42],[72,52],[40,68],[60,32]].forEach(function(pt) {
    var x = pt[0], y = pt[1];
    kids.push(svgEl('g', null, [
      svgEl('circle', { cx: x, cy: y, r: 3, fill: p.green, opacity: 0.4 }),
      svgEl('line', { x1: x, y1: y, x2: x - 2, y2: y - 4,
                      stroke: p.green, strokeWidth: 0.5 }),
      svgEl('line', { x1: x, y1: y, x2: x + 2, y2: y - 4,
                      stroke: p.green, strokeWidth: 0.5 }),
      svgEl('line', { x1: x, y1: y, x2: x,     y2: y - 5,
                      stroke: p.green, strokeWidth: 0.5 })
    ]));
  });
  return svgEl('pattern', {
    id: 'terr-oasis', x: 0, y: 0, width: 100, height: 100,
    patternUnits: 'userSpaceOnUse'
  }, kids);
}

function patternVapor(p) {
  var kids = [
    svgEl('rect', { width: 60, height: 60, fill: p.ground, opacity: 0.8 })
  ];
  // vaporators in grid
  [[15,15],[45,15],[15,45],[45,45]].forEach(function(pt) {
    var x = pt[0], y = pt[1];
    kids.push(svgEl('g', null, [
      svgEl('circle', { cx: x, cy: y, r: 1.4,
                        fill: p.paperDark, stroke: p.ink, strokeWidth: 0.3 }),
      svgEl('circle', { cx: x, cy: y, r: 0.5,
                        fill: p.cyan, opacity: 0.6 })
    ]));
  });
  // faint connecting paths
  kids.push(svgEl('line', { x1: 15, y1: 15, x2: 45, y2: 15,
                            stroke: p.inkFaint, strokeWidth: 0.2, opacity: 0.4 }));
  kids.push(svgEl('line', { x1: 15, y1: 45, x2: 45, y2: 45,
                            stroke: p.inkFaint, strokeWidth: 0.2, opacity: 0.4 }));
  return svgEl('pattern', {
    id: 'terr-vapor', x: 0, y: 0, width: 60, height: 60,
    patternUnits: 'userSpaceOnUse'
  }, kids);
}

function patternCity(p) {
  var kids = [
    svgEl('rect', { width: 140, height: 100, fill: p.ground }),
    // large slab variation
    svgEl('rect', { x: 20, y: 10, width: 50, height: 30,
                    fill: p.groundDeep, opacity: 0.15 }),
    svgEl('rect', { x: 80, y: 50, width: 40, height: 30,
                    fill: p.groundDeep, opacity: 0.15 })
  ];
  // fine grit — 60 dots in a hash-deterministic grid
  for (var i = 0; i < 60; i++) {
    var x = (i * 17) % 140;
    var y = (i * 31) % 100;
    kids.push(svgEl('circle', { cx: x, cy: y, r: 0.3,
                                fill: p.groundShadow, opacity: 0.5 }));
  }
  // footprint suggestion lines
  kids.push(svgEl('path', { d: 'M 8 30 L 18 28',
                            stroke: p.inkFaint, strokeWidth: 0.25, opacity: 0.3 }));
  kids.push(svgEl('path', { d: 'M 90 18 L 102 16',
                            stroke: p.inkFaint, strokeWidth: 0.25, opacity: 0.3 }));
  kids.push(svgEl('path', { d: 'M 50 80 L 62 82',
                            stroke: p.inkFaint, strokeWidth: 0.25, opacity: 0.3 }));
  return svgEl('pattern', {
    id: 'terr-city', x: 0, y: 0, width: 140, height: 100,
    patternUnits: 'userSpaceOnUse'
  }, kids);
}

// TerrainDefs(p) — returns one <defs> containing all seven patterns.
// The composition engine appends this to the root <svg>'s first <defs>
// and then references each as fill="url(#terr-<name>)".
function TerrainDefs(p) {
  return svgEl('defs', null, [
    patternDune(p),
    patternDuracrete(p),
    patternScrub(p),
    patternCanyon(p),
    patternOasis(p),
    patternVapor(p),
    patternCity(p)
  ]);
}

// HazeDefs(p) — returns the <defs> for atmospheric gradients.
// Two gradients: haze-grad (used by OV_SandHaze) and atmosphere-grad
// (vignetting available to any overlay that wants edge darkening).
function HazeDefs(p) {
  return svgEl('defs', null, [
    svgEl('radialGradient', { id: 'haze-grad', cx: '50%', cy: '40%', r: '60%' }, [
      svgEl('stop', { offset: '0%', 'stop-color': p.hazeColor, 'stop-opacity': 0.4 }),
      svgEl('stop', { offset: '100%', 'stop-color': p.hazeColor, 'stop-opacity': 0 })
    ]),
    svgEl('radialGradient', { id: 'atmosphere-grad', cx: '50%', cy: '50%', r: '70%' }, [
      svgEl('stop', { offset: '0%', 'stop-color': 'transparent' }),
      svgEl('stop', { offset: '100%', 'stop-color': p.skyDeep, 'stop-opacity': 0.5 })
    ])
  ]);
}

// ────────────────────────────────────────────────────────────────
// ATMOSPHERIC OVERLAYS — drawn over the entire map area.
// ────────────────────────────────────────────────────────────────

// Twin-sun shadows — Tatooine-specific (and other binary-star palettes
// where p.sunCount === 2). Drops two angled shadows per building.
// Returns null when not applicable (single-sun planets, night).
function OV_TwinSunShadows(o) {
  var p = o.p;
  var buildings = o.buildings || [];
  var time = o.time || 'day';
  if (p.sunCount !== 2 || time === 'night') return null;

  var shadows = [];
  buildings.forEach(function(b) {
    var offsets = [
      { dx: -b.r * 0.7, dy: b.r * 0.55, opacity: time === 'dusk' ? 0.45 : 0.32 },
      { dx:  b.r * 0.5, dy: b.r * 0.65, opacity: time === 'dusk' ? 0.50 : 0.28 }
    ];
    offsets.forEach(function(off) {
      shadows.push(svgEl('ellipse', {
        cx: b.x + off.dx, cy: b.y + off.dy,
        rx: b.r * 0.85,   ry: b.r * 0.6,
        fill: p.skyDeep, opacity: off.opacity
      }));
    });
  });
  return svgEl('g', { style: 'mix-blend-mode: multiply' }, shadows);
}

// Time-of-day tint — drops a coloured rect over the whole viewport.
// 'day' is a no-op (returns null). Tints use multiply blend.
function OV_TimeOfDay(o) {
  var time = o.time || 'day';
  if (time === 'day') return null;
  var tints = {
    dusk:  'rgba(255, 100, 60, 0.18)',
    night: 'rgba(20, 20, 60, 0.45)',
    dawn:  'rgba(255, 200, 140, 0.12)'
  };
  return svgEl('rect', {
    x: 0, y: 0, width: o.width, height: o.height,
    fill: tints[time],
    style: 'mix-blend-mode: multiply'
  });
}

// Sand haze — Tatooine ambient. Uses haze-grad from HazeDefs.
function OV_SandHaze(o) {
  return svgEl('rect', {
    x: 0, y: 0, width: o.width, height: o.height,
    fill: 'url(#haze-grad)', opacity: 0.4
  });
}

// Sandstorm — active weather overlay with directional dust streaks.
function OV_Sandstorm(o) {
  var width = o.width, height = o.height;
  var children = [
    svgEl('rect', { x: 0, y: 0, width: width, height: height,
                    fill: 'rgba(220, 160, 80, 0.42)' })
  ];
  for (var i = 0; i < 40; i++) {
    var y = (i * 37) % height;
    var x = (i * 71) % width;
    var len = 30 + (i * 17) % 60;
    children.push(svgEl('line', {
      x1: x, y1: y, x2: x + len, y2: y + 6,
      stroke: 'rgba(255,210,140,0.5)',
      strokeWidth: 0.8 + (i % 3) * 0.3
    }));
  }
  return svgEl('g', { style: 'pointer-events: none' }, children);
}

// Rain — for wet planets (e.g. Kamino). Diagonal short streaks.
function OV_Rain(o) {
  var width = o.width, height = o.height;
  var children = [
    svgEl('rect', { x: 0, y: 0, width: width, height: height,
                    fill: 'rgba(40,60,80,0.18)' })
  ];
  for (var i = 0; i < 80; i++) {
    var x = (i * 47) % width;
    var y = (i * 31) % height;
    children.push(svgEl('line', {
      x1: x, y1: y, x2: x - 4, y2: y + 14,
      stroke: 'rgba(160,200,240,0.45)', strokeWidth: 0.6
    }));
  }
  return svgEl('g', { style: 'pointer-events: none' }, children);
}

// Smog — Coruscant Underworld. Tints + three horizontal smog bands.
function OV_Smog(o) {
  var width = o.width, height = o.height;
  var children = [
    svgEl('rect', { x: 0, y: 0, width: width, height: height,
                    fill: 'rgba(120,40,30,0.18)' })
  ];
  [0.2, 0.45, 0.7].forEach(function(yRatio, i) {
    children.push(svgEl('ellipse', {
      cx: width * (0.3 + i * 0.2),
      cy: height * yRatio,
      rx: width * 0.4,
      ry: height * 0.08,
      fill: 'rgba(120,80,60,0.25)'
    }));
  });
  return svgEl('g', { style: 'pointer-events: none' }, children);
}

// Neon halos — Nar Shaddaa / Coruscant Underworld. Pulses over lit buildings.
function OV_NeonHalos(o) {
  var p = o.p;
  var buildings = o.buildings || [];
  var children = [];
  buildings.forEach(function(b, i) {
    if (!b.lit) return;
    var halo = svgEl('ellipse', {
      cx: b.x, cy: b.y,
      rx: b.r * 1.4, ry: b.r * 1.4,
      fill: b.color || p.amber, opacity: 0.18
    }, [
      svgEl('animate', {
        attributeName: 'opacity',
        values: '0.14;0.22;0.14',
        dur: (2 + (i % 3) * 0.6) + 's',
        repeatCount: 'indefinite'
      })
    ]);
    children.push(halo);
  });
  return svgEl('g', {
    style: 'mix-blend-mode: screen; pointer-events: none'
  }, children);
}

// Faction territory — translucent polygons coloured per faction.
// Per Tier 1 #3 era-fidelity work, CW factions only (republic/cis/hutt/jedi).
function OV_FactionTerritory(o) {
  var polygons = o.polygons || [];
  var faction = o.faction;
  var colors = {
    republic: 'rgba(120, 180, 255, 0.18)',
    cis:      'rgba(255, 100, 80, 0.18)',
    hutt:     'rgba(140, 220, 120, 0.16)',
    jedi:     'rgba(180, 200, 255, 0.15)'
  };
  var fill = colors[faction] || 'rgba(255,255,255,0.1)';
  var children = polygons.map(function(poly) {
    var pts = poly.map(function(pair) { return pair.join(','); }).join(' ');
    return svgEl('polygon', { points: pts, fill: fill });
  });
  return svgEl('g', { style: 'pointer-events: none' }, children);
}

// Contest banner — small placard above a wilderness contest location.
function OV_ContestBanner(o) {
  var p = o.p;
  return svgEl('g', {
    transform: 'translate(' + o.x + ' ' + o.y + ')',
    style: 'pointer-events: none'
  }, [
    svgEl('rect', { x: -60, y: -12, width: 120, height: 24,
                    fill: p.skyDeep, stroke: p.red, strokeWidth: 1 }),
    svgEl('text', {
      x: 0, y: -1,
      fontSize: 8, textAnchor: 'middle', fill: p.red,
      style: 'font-family: IBM Plex Mono, monospace; ' +
             'letter-spacing: 2px; font-weight: 600'
    }, ['\u26A0 CONTEST \u00B7 ' + o.label]),
    svgEl('text', {
      x: 0, y: 9,
      fontSize: 7, textAnchor: 'middle', fill: p.amber,
      style: 'font-family: IBM Plex Mono, monospace; letter-spacing: 1px'
    }, [String(o.score)])
  ]);
}

var OVERLAYS = {
  twin_sun_shadows:    OV_TwinSunShadows,
  time_of_day:         OV_TimeOfDay,
  sand_haze:           OV_SandHaze,
  sandstorm:           OV_Sandstorm,
  rain:                OV_Rain,
  smog:                OV_Smog,
  neon_halos:          OV_NeonHalos,
  faction_territory:   OV_FactionTerritory,
  contest_banner:      OV_ContestBanner
};

window.M3AssetsOverlays = {
  TerrainDefs:        TerrainDefs,
  HazeDefs:           HazeDefs,
  OVERLAYS:           OVERLAYS,
  // Also expose individual overlay builders by long ident.
  OV_TwinSunShadows:  OV_TwinSunShadows,
  OV_TimeOfDay:       OV_TimeOfDay,
  OV_SandHaze:        OV_SandHaze,
  OV_Sandstorm:       OV_Sandstorm,
  OV_Rain:            OV_Rain,
  OV_Smog:            OV_Smog,
  OV_NeonHalos:       OV_NeonHalos,
  OV_FactionTerritory: OV_FactionTerritory,
  OV_ContestBanner:   OV_ContestBanner
};

})();
