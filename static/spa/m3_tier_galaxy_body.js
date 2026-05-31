/* ============================================================================
   m3_tier_galaxy_body.js — Tier 4c Galaxy renderer (CW era, 20 BBY).

   Drop 4.13 (Batch 1, outer-tier triplet) · Tier 1 #4 · ported from
   map_v3/tier-four.jsx (220 JSX LOC) in SW_MUSH_UIUX_Bugfix_26May26.zip
   (May 27 2026).

   This is the outermost zoom of the SPA map navigator's tier ladder.
   Stylized galaxy disk with:
     · Deep-space starfield (240 stars, golden-ratio distribution)
     · Galactic halo + dim disk ellipse
     · CW-era faction territory overlays (Republic / CIS / Hutt Space)
     · Four spiral arms with embedded star density
     · Galactic core glow + bright nucleus
     · Four major hyperlanes (Perlemian, Corellian Run, Hydian, Rimma)
     · Six region rings (Core → Outer Rim)
     · 13 notable systems with Tatooine player-marked
     · CW-era faction legend bottom-left
     · Current-location indicator top-right
     · Title + era subtitle

   What this module ships:
     · M3TierGalaxyBody.buildTierFourGalaxy(p, opts?)
            top-level renderer; signature compatible with the
            getTierRenderer DI seam in M3MapNavigator (Drop 4.8) and
            M3AssembledClient.MiniMap (Drop 4.12b). Returns an <svg>.
     · M3TierGalaxyBody.NOTABLE_SYSTEMS    13-system fixture array
     · M3TierGalaxyBody.HYPERLANES         4 hyperlane fixture entries
     · M3TierGalaxyBody.REGION_RINGS       6-ring fixture array
     · M3TierGalaxyBody.FACTION_TERRITORY  3-overlay fixture array

   B3 era-cleanness:
     · Era subtitle "CLONE WARS ERA · 20 BBY"
     · Faction legend reads "GALACTIC REPUBLIC", "CONFEDERACY", "HUTT
       SPACE", "WILD SPACE" — NOT Empire/Rebellion.
     · Geonosis + Mustafar marked hostile (CW-era CIS positions).
     · Zero Empire/Imperial/TIE/X-wing/Rebel/Stormtrooper/Vader/Death
       Star/ISB references in data blocks.

   Q1 canonical-character policy note (architecture v50 §6.2):
     This module contains no canonical-character references. All
     entries are place names (planets, hyperlanes, regions).

   Palette keys consumed:
     p.amber, p.cyan, p.green, p.gold, p.red, p.ink, p.inkBright,
     p.inkDim, p.inkFaint, p.skyDeep
     (All standard. No undocumented keys.)

   Dependencies: none. Self-contained — pure SVG generation.

   Loading order in client.html: anywhere after m3_palettes.js. Drop 4.13
   places this in the SPA script-tag block alongside the other tier-body
   renderers (after m3_assembled_client.js, before any tier-body
   integration code).
   ============================================================================ */
(function(){
'use strict';

// ─── svgEl helper: same shape as Drops 4.5-4.12 ──────────────────────
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
var HYPERLANES = [
  // [from-radius, from-angle, to-radius, to-angle, name]
  [0.05, 0, 0.95, 30, 'Perlemian Trade Route'],
  [0.05, 0, 0.95, 150, 'Corellian Run'],
  [0.05, 0, 0.95, 210, 'Hydian Way'],
  [0.05, 0, 0.95, 330, 'Rimma Trade Route']
];

var REGION_RINGS = [
  // [radius-fraction, label, color-key, opacity]
  [0.20, 'CORE WORLDS',      'inkDim',   0.7],
  [0.42, 'COLONIES',         'inkFaint', 0.5],
  [0.60, 'INNER RIM',        'inkFaint', 0.4],
  [0.75, 'EXPANSION REGION', 'inkFaint', 0.3],
  [0.87, 'MID RIM',          'inkFaint', 0.3],
  [0.98, 'OUTER RIM',        'inkDim',   0.5]
];

var NOTABLE_SYSTEMS = [
  { name: 'CORUSCANT',   r: 0.05, a: 0,   colorKey: 'cyan',  important: true },
  { name: 'KAMINO',      r: 0.96, a: 195, colorKey: 'cyan' },
  { name: 'GEONOSIS',    r: 0.78, a: 60,  colorKey: 'red',   hostile: true },
  { name: 'KASHYYYK',    r: 0.66, a: 122, colorKey: 'green' },
  { name: 'NABOO',       r: 0.74, a: 250, colorKey: 'cyan' },
  { name: 'MANDALORE',   r: 0.55, a: 95,  colorKey: 'amber' },
  { name: 'TATOOINE',    r: 0.94, a: 28,  colorKey: 'gold',  player: true },
  { name: 'NAR SHADDAA', r: 0.88, a: 50,  colorKey: 'amber' },
  { name: 'BESPIN',      r: 0.82, a: 195, colorKey: 'amber' },
  { name: 'DAGOBAH',     r: 0.95, a: 240, colorKey: 'green' },
  { name: 'HOTH',        r: 0.99, a: 280, colorKey: 'cyan' },
  { name: 'ENDOR',       r: 0.99, a: 320, colorKey: 'green' },
  { name: 'MUSTAFAR',    r: 0.85, a: 75,  colorKey: 'red',   hostile: true }
];

var FACTION_TERRITORY = [
  // CW-era ~20 BBY
  // [label, fill, cx-offset, cy-offset, rx, ry]
  ['GALACTIC REPUBLIC',
   'rgba(120, 180, 255, 0.18)',
   -0.15, 0,    0.55, 0.55],
  ['CONFEDERACY',
   'rgba(255, 100, 80, 0.18)',
    0.45, 0.10, 0.42, 0.35],
  ['HUTT SPACE',
   'rgba(140, 220, 120, 0.16)',
    0.5,  0.5,  0.28, 0.22]
];

// Legend swatches use higher opacity so they read at small size.
var FACTION_LEGEND = [
  ['GALACTIC REPUBLIC', 'rgba(120,180,255,0.4)'],
  ['CONFEDERACY',       'rgba(255,100,80,0.4)'],
  ['HUTT SPACE',        'rgba(140,220,120,0.4)']
  // WILD SPACE entry is appended at render time using p.inkFaint.
];

// ════════════════════════════════════════════════════════════════════
// buildTierFourGalaxy(p, opts?) → <svg>
//
// Signature compatible with the getTierRenderer DI seam:
//   hooks.getTierRenderer('4c', { p, width, height }) → element
// ════════════════════════════════════════════════════════════════════
function buildTierFourGalaxy(p, opts) {
  opts = opts || {};
  // The seam also lets callers pass palette via opts.p; accept either.
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierFourGalaxy: palette argument required');

  var width  = opts.width  || 1280;
  var height = opts.height || 856;
  var cx = width / 2;
  var cy = height / 2 - 20;
  var rGal = Math.min(width, height) * 0.42;

  // ── Spiral arm path generator (4 arms) ──────────────────────────
  function armPath(offsetDeg, tightness) {
    if (tightness == null) tightness = 0.18;
    var pts = [];
    for (var r = 0.15; r <= 1.0; r += 0.04) {
      var theta = (offsetDeg * Math.PI / 180) + r * Math.PI * 3 * tightness;
      var x = cx + Math.cos(theta) * r * rGal;
      var y = cy + Math.sin(theta) * r * rGal * 0.85;
      pts.push([x, y]);
    }
    var parts = [];
    for (var i = 0; i < pts.length; i++) {
      parts.push(pts[i][0].toFixed(1) + ' ' + pts[i][1].toFixed(1));
    }
    return 'M ' + parts.join(' L ');
  }

  var children = [];

  // ── <defs>: galactic core + halo gradients ──────────────────────
  var defs = svgEl('defs', null, [
    svgEl('radialGradient', { id: 'gal-core', cx: '50%', cy: '50%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   stopColor: '#ffe8b0', stopOpacity: 1 }),
      svgEl('stop', { offset: '30%',  stopColor: p.amber,   stopOpacity: 0.6 }),
      svgEl('stop', { offset: '100%', stopColor: p.amber,   stopOpacity: 0 })
    ]),
    svgEl('radialGradient', { id: 'gal-halo', cx: '50%', cy: '50%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   stopColor: p.inkBright, stopOpacity: 0.4 }),
      svgEl('stop', { offset: '60%',  stopColor: p.ink,       stopOpacity: 0.15 }),
      svgEl('stop', { offset: '100%', stopColor: 'transparent' })
    ])
  ]);
  children.push(defs);

  // ── Deep-space starfield (240 stars, golden-ratio distribution) ──
  for (var i = 0; i < 240; i++) {
    var a = (i * 137.5) % 360;
    var r = Math.sqrt((i * 0.61) % 1) * Math.max(width, height) * 0.7;
    var sx = cx + Math.cos(a * Math.PI / 180) * r;
    var sy = cy + Math.sin(a * Math.PI / 180) * r;
    var sz = i % 19 === 0 ? 1.4 : i % 7 === 0 ? 0.8 : 0.4;
    children.push(svgEl('circle', {
      cx: sx, cy: sy, r: sz,
      fill: i % 11 === 0 ? p.cyan : p.inkBright,
      opacity: 0.3 + (i % 3) * 0.2
    }));
  }

  // ── Galactic halo ───────────────────────────────────────────────
  children.push(svgEl('ellipse', {
    cx: cx, cy: cy, rx: rGal * 1.05, ry: rGal * 0.92, fill: 'url(#gal-halo)'
  }));

  // ── Galactic disk (dim ellipse) ─────────────────────────────────
  children.push(svgEl('ellipse', {
    cx: cx, cy: cy, rx: rGal, ry: rGal * 0.85,
    fill: '#0a0a18', stroke: p.inkFaint, strokeWidth: 0.6, opacity: 0.6
  }));

  // ── Faction territory overlays (CW era ~20 BBY) ─────────────────
  var factionTerritoryChildren = [];
  for (var ti = 0; ti < FACTION_TERRITORY.length; ti++) {
    var ft = FACTION_TERRITORY[ti];
    factionTerritoryChildren.push(svgEl('ellipse', {
      cx: cx + rGal * ft[2],
      cy: cy + rGal * ft[3],
      rx: rGal * ft[4],
      ry: rGal * ft[5],
      fill: ft[1]
    }));
  }
  children.push(svgEl('g', {
    style: { mixBlendMode: 'screen' }
  }, factionTerritoryChildren));

  // ── Spiral arms (dust lanes + embedded stars) ───────────────────
  var armAngles = [0, 90, 180, 270];
  for (var ai = 0; ai < armAngles.length; ai++) {
    children.push(svgEl('path', {
      d: armPath(armAngles[ai]),
      fill: 'none',
      stroke: p.inkBright, strokeWidth: 0.6, opacity: 0.25
    }));
  }
  for (var ai2 = 0; ai2 < armAngles.length; ai2++) {
    var armStarChildren = [];
    for (var j = 0; j < 30; j++) {
      var rr = 0.15 + (j / 30) * 0.85;
      var theta = (armAngles[ai2] * Math.PI / 180) +
                  rr * Math.PI * 3 * 0.18 +
                  (j % 3 - 1) * 0.05;
      var ax = cx + Math.cos(theta) * rr * rGal;
      var ay = cy + Math.sin(theta) * rr * rGal * 0.85;
      armStarChildren.push(svgEl('circle', {
        cx: ax, cy: ay, r: 0.6,
        fill: p.inkBright, opacity: 0.5 + (j % 3) * 0.15
      }));
    }
    children.push(svgEl('g', null, armStarChildren));
  }

  // ── Galactic core ───────────────────────────────────────────────
  children.push(svgEl('circle', {
    cx: cx, cy: cy, r: rGal * 0.18, fill: 'url(#gal-core)'
  }));
  children.push(svgEl('circle', {
    cx: cx, cy: cy, r: 4, fill: p.inkBright,
    style: { filter: 'drop-shadow(0 0 6px ' + p.amber + ')' }
  }));

  // ── Major hyperlanes ────────────────────────────────────────────
  var hyperlaneChildren = [];
  for (var hi = 0; hi < HYPERLANES.length; hi++) {
    var hl = HYPERLANES[hi];
    var r1 = hl[0], a1 = hl[1], r2 = hl[2], a2 = hl[3], name = hl[4];
    var x1 = cx + Math.cos(a1 * Math.PI / 180) * r1 * rGal;
    var y1 = cy + Math.sin(a1 * Math.PI / 180) * r1 * rGal * 0.85;
    var x2 = cx + Math.cos(a2 * Math.PI / 180) * r2 * rGal;
    var y2 = cy + Math.sin(a2 * Math.PI / 180) * r2 * rGal * 0.85;
    var mx = (x1 + x2) / 2;
    var my = (y1 + y2) / 2;
    var angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;
    hyperlaneChildren.push(svgEl('g', { 'data-hyperlane': name }, [
      svgEl('line', {
        x1: x1, y1: y1, x2: x2, y2: y2,
        stroke: p.cyan, strokeWidth: 0.4, opacity: 0.4, strokeDasharray: '6 3'
      }),
      svgEl('text', {
        transform: 'translate(' + mx + ' ' + my + ') rotate(' + angle + ')',
        fontSize: 8, fill: p.cyan, textAnchor: 'middle', dy: -3,
        style: { letterSpacing: 1.5, opacity: 0.7 }
      }, [name.toUpperCase()])
    ]));
  }
  children.push(svgEl('g', { style: { pointerEvents: 'none' } }, hyperlaneChildren));

  // ── Region rings ────────────────────────────────────────────────
  for (var rri = 0; rri < REGION_RINGS.length; rri++) {
    var rr2 = REGION_RINGS[rri];
    var ringR = rr2[0], ringLabel = rr2[1], colorKey = rr2[2], ringOp = rr2[3];
    var ringColor = p[colorKey] || p.inkFaint;
    children.push(svgEl('g', { 'data-region-ring': ringLabel }, [
      svgEl('ellipse', {
        cx: cx, cy: cy, rx: ringR * rGal, ry: ringR * rGal * 0.85,
        fill: 'none', stroke: ringColor, strokeWidth: 0.3,
        strokeDasharray: '2 4', opacity: ringOp
      }),
      svgEl('text', {
        x: cx + ringR * rGal + 6, y: cy + 3, fontSize: 9, fill: ringColor,
        style: { letterSpacing: 2, opacity: ringOp }
      }, [ringLabel])
    ]));
  }

  // ── Notable systems ─────────────────────────────────────────────
  for (var si = 0; si < NOTABLE_SYSTEMS.length; si++) {
    var s = NOTABLE_SYSTEMS[si];
    var sxCoord = cx + Math.cos(s.a * Math.PI / 180) * s.r * rGal;
    var syCoord = cy + Math.sin(s.a * Math.PI / 180) * s.r * rGal * 0.85;
    var sColor = p[s.colorKey] || p.inkBright;

    var systemKids = [];
    if (s.player) {
      // Pulsing ring + outline + filled dot for player position.
      var pulseRing = svgEl('circle', {
        r: 14, fill: 'none', stroke: sColor, strokeWidth: 0.5, opacity: 0.5
      }, [
        svgEl('animate', {
          attributeName: 'r', values: '10;18;10',
          dur: '2.4s', repeatCount: 'indefinite'
        }),
        svgEl('animate', {
          attributeName: 'opacity', values: '0.6;0;0.6',
          dur: '2.4s', repeatCount: 'indefinite'
        })
      ]);
      systemKids.push(pulseRing);
      systemKids.push(svgEl('circle', {
        r: 6, fill: 'none', stroke: sColor, strokeWidth: 1
      }));
    }
    systemKids.push(svgEl('circle', {
      r: s.player ? 3 : s.important ? 2.5 : 1.8,
      fill: sColor, stroke: p.skyDeep, strokeWidth: 0.4,
      style: {
        filter: 'drop-shadow(0 0 ' + (s.player ? 6 : 3) + 'px ' + sColor + ')'
      }
    }));
    systemKids.push(svgEl('text', {
      x: 0, y: s.player ? 18 : 12,
      fontSize: s.player ? 11 : s.important ? 10 : 8.5,
      textAnchor: 'middle',
      fill: s.player ? p.inkBright : p.ink,
      style: {
        letterSpacing: 2,
        fontWeight: s.player ? 700 : 400,
        textShadow: s.player ? ('0 0 4px ' + sColor) : 'none'
      }
    }, [s.name]));

    children.push(svgEl('g', {
      'data-system': s.name,
      'data-system-player': s.player ? '1' : '0',
      'data-system-hostile': s.hostile ? '1' : '0',
      transform: 'translate(' + sxCoord + ' ' + syCoord + ')'
    }, systemKids));
  }

  // ── Faction legend (bottom-left) ────────────────────────────────
  var legendKids = [
    svgEl('text', {
      x: 0, y: 0, fontSize: 10, fill: p.inkDim,
      style: { letterSpacing: 3, fontWeight: 600 }
    }, ['FACTION TERRITORY · 20 BBY'])
  ];
  var legendItems = FACTION_LEGEND.slice();
  legendItems.push(['WILD SPACE', p.inkFaint]);
  for (var li = 0; li < legendItems.length; li++) {
    var ll = legendItems[li];
    legendKids.push(svgEl('g', {
      transform: 'translate(0 ' + (18 + li * 14) + ')'
    }, [
      svgEl('rect', { x: 0, y: -5, width: 16, height: 6, fill: ll[1] }),
      svgEl('text', {
        x: 22, y: 0, fontSize: 9, fill: p.ink,
        style: { letterSpacing: 1.5 }
      }, [ll[0]])
    ]));
  }
  children.push(svgEl('g', {
    'data-faction-legend': '1',
    transform: 'translate(40, ' + (height - 110) + ')'
  }, legendKids));

  // ── Current-location indicator (top-right) ──────────────────────
  children.push(svgEl('g', {
    'data-current-location': '1',
    transform: 'translate(' + (width - 220) + ', 60)'
  }, [
    svgEl('text', {
      x: 0, y: 0, fontSize: 9, fill: p.inkDim,
      style: { letterSpacing: 2 }
    }, ['CURRENT LOCATION']),
    svgEl('text', {
      x: 0, y: 18, fontSize: 14, fill: p.inkBright,
      style: { letterSpacing: 3, fontWeight: 600 }
    }, ['TATOOINE']),
    svgEl('text', {
      x: 0, y: 32, fontSize: 9, fill: p.inkDim,
      style: { letterSpacing: 1.5 }
    }, ['ARKANIS SECTOR · OUTER RIM'])
  ]));

  // ── Title + era subtitle ────────────────────────────────────────
  children.push(svgEl('text', {
    x: cx, y: 42, fontSize: 20, textAnchor: 'middle', fill: p.inkBright,
    style: {
      letterSpacing: 10, fontWeight: 600,
      textShadow: '0 0 8px ' + p.amber
    }
  }, ['THE GALAXY']));
  children.push(svgEl('text', {
    x: cx, y: 58, fontSize: 9, textAnchor: 'middle', fill: p.inkDim,
    style: { letterSpacing: 4 }
  }, ['CLONE WARS ERA · 20 BBY']));

  return svgEl('svg', {
    'data-tier-galaxy': '1',
    width: width, height: height,
    viewBox: '0 0 ' + width + ' ' + height,
    style: { display: 'block', background: '#000' }
  }, children);
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3TierGalaxyBody = {
  SCHEMA_VERSION: 1,

  // Top-level
  buildTierFourGalaxy: buildTierFourGalaxy,

  // Fixtures (public for downstream composition / Q1 audits)
  NOTABLE_SYSTEMS:     NOTABLE_SYSTEMS,
  HYPERLANES:          HYPERLANES,
  REGION_RINGS:        REGION_RINGS,
  FACTION_TERRITORY:   FACTION_TERRITORY,
  FACTION_LEGEND:      FACTION_LEGEND,

  _internal: { _svgEl: svgEl }
};

})();
