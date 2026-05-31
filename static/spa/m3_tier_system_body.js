/* ============================================================================
   m3_tier_system_body.js — Tier 4a Star System renderer (Tatooine system).

   Drop 4.13 (Batch 1, outer-tier triplet) · Tier 1 #4 · ported from
   map_v3/tier-4a.jsx (186 JSX LOC) in SW_MUSH_UIUX_Bugfix_26May26.zip
   (May 27 2026).

   This is the second-outermost zoom of the SPA map navigator's tier
   ladder. Stylized top-down star system map with:
     · Starfield (180 stars, deterministic prime-distributed)
     · Orbital paths (dashed ellipses) for 5 bodies
     · Asteroid belt — 90 dotted bodies between Tatooine and Tatoo VI
     · Twin suns (Tatoo I primary K-class amber + Tatoo II secondary
       G-class gold) with radial bloom
     · Planets — Tatoo IV, Tatoo V, Tatooine (player-marked),
       Ghest, Tatoo VI
     · Player-marked Tatooine with pulsing animation
     · Hyperspace beacons — Kessel (active), Anchorhead (idle),
       Geonosis (active, hostile), Ryloth (idle)
     · Player ship "RUSTY MYNOCK" in low orbit (cyan triangle glyph)
     · Title + era-coded subtitle
     · Legend top-right + scale bar bottom-left

   What this module ships:
     · M3TierSystemBody.buildTierFourASystemBody(p, opts?)
            top-level renderer; signature compatible with the
            getTierRenderer DI seam in M3MapNavigator (Drop 4.8) and
            M3AssembledClient.MiniMap (Drop 4.12b). Returns an <svg>.
     · M3TierSystemBody.ORBITAL_BODIES   5-body fixture array
     · M3TierSystemBody.BEACONS          4-beacon fixture array
     · M3TierSystemBody.TWIN_SUNS        sun position fixture

   B3 era-cleanness:
     · Era subtitle "BINARY K+G" (stellar classification, era-neutral)
     · Beacon labels are inter-system hyperspace destinations
       (Kessel, Anchorhead, Geonosis, Ryloth) — all CW-era valid
       per source.
     · Zero Empire/Imperial/TIE/X-wing/Rebel/Stormtrooper/Vader/Death
       Star/ISB references in data blocks.

   Q1 canonical-character policy note (architecture v50 §6.2):
     · "RUSTY MYNOCK" — the Tey Voss player ship name, preserved
       verbatim from the JSX source. Same as M3AssembledClient (4.12b)
       which references "Mynock" in feed items. Tracked in the Q1
       cleanup queue.

   Palette keys consumed:
     p.amber, p.cyan, p.gold, p.green, p.red, p.ink, p.inkBright,
     p.inkDim, p.skyDeep
     · p.groundShadow — UNDOCUMENTED key from JSX source. Per Drop 4.11
       loud-substitution policy, we apply a `p.groundShadow || p.skyDeep`
       fallback so the gradient renders cleanly when the palette
       doesn't define groundShadow.

   Dependencies: none. Self-contained — pure SVG generation.

   Loading order in client.html: anywhere after m3_palettes.js.
   ============================================================================ */
(function(){
'use strict';

// ─── svgEl helper (same shape as m3_tier_galaxy_body) ────────────────
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
var ORBITAL_BODIES = [
  { name: 'TATOO IV',  r: 130, angle:  35, size: 5,  colorKey: 'inkDim' },
  { name: 'TATOO V',   r: 200, angle: 110, size: 6,  colorKey: 'inkDim' },
  // RUSTY MYNOCK ship reference for Q1 sweep — see module header.
  { name: 'TATOOINE',  r: 280, angle: 220, size: 12, colorKey: 'gold',
    player: true },
  { name: 'GHEST',     r: 340, angle: 300, size: 4,  colorKey: 'inkDim' },
  { name: 'TATOO VI',  r: 430, angle:  60, size: 7,  colorKey: 'inkDim' }
];

var BEACONS = [
  // x/y are pixel offsets relative to the svg corners; recomputed at
  // render time using actual width/height. Stored here as
  // [corner, x-offset, y-offset, label, active, hostile].
  ['top-right',    -60,   100,  'TO KESSEL',    true,  false],
  ['bottom-left',   60,   -80,  'TO ANCHORHEAD', false, false],
  ['bottom-right', -100,  -60,  'TO GEONOSIS',  true,  true],
  ['top-left',      80,    80,  'TO RYLOTH',    false, false]
];

var TWIN_SUNS = {
  // Offsets from center; recomputed at render time.
  primary:   { dx: -70, dy:  10, r: 30, bloomR: 140,
               innerFill: '#ffe9b0', colorKey: 'amber',
               name: 'TATOO I' },
  secondary: { dx:  60, dy: -20, r: 22, bloomR: 110,
               innerFill: '#fff0bd', colorKey: 'gold',
               name: 'TATOO II' }
};

// ════════════════════════════════════════════════════════════════════
// buildTierFourASystemBody(p, opts?) → <svg>
//
// Signature compatible with the getTierRenderer DI seam:
//   hooks.getTierRenderer('4a', { p, width, height }) → element
// ════════════════════════════════════════════════════════════════════
function buildTierFourASystemBody(p, opts) {
  opts = opts || {};
  if (!p && opts.p) p = opts.p;
  if (!p) throw new Error('buildTierFourASystemBody: palette argument required');

  var width  = opts.width  || 1280;
  var height = opts.height || 856;
  var cx = width / 2;
  var cy = height / 2 - 10;

  // Apply Drop 4.11 loud-substitution policy for undocumented palette keys.
  var groundShadow = p.groundShadow || p.skyDeep;

  var sunA = {
    x: cx + TWIN_SUNS.primary.dx,
    y: cy + TWIN_SUNS.primary.dy,
    r: TWIN_SUNS.primary.r,
    bloomR: TWIN_SUNS.primary.bloomR,
    color: p[TWIN_SUNS.primary.colorKey],
    innerFill: TWIN_SUNS.primary.innerFill,
    name: TWIN_SUNS.primary.name
  };
  var sunB = {
    x: cx + TWIN_SUNS.secondary.dx,
    y: cy + TWIN_SUNS.secondary.dy,
    r: TWIN_SUNS.secondary.r,
    bloomR: TWIN_SUNS.secondary.bloomR,
    color: p[TWIN_SUNS.secondary.colorKey],
    innerFill: TWIN_SUNS.secondary.innerFill,
    name: TWIN_SUNS.secondary.name
  };

  var beltInner = 340;
  // (beltOuter = 400 in source; not used directly — controls how the
  // dotted ring spreads via the (i*17)%60 mod.)

  var children = [];

  // ── <defs>: sun glows + Tatooine planet gradient ────────────────
  var defs = svgEl('defs', null, [
    svgEl('radialGradient', { id: 'sun-glow-a', cx: '50%', cy: '50%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   stopColor: '#ffe9b0', stopOpacity: 1 }),
      svgEl('stop', { offset: '30%',  stopColor: p.amber,   stopOpacity: 0.6 }),
      svgEl('stop', { offset: '100%', stopColor: p.amber,   stopOpacity: 0 })
    ]),
    svgEl('radialGradient', { id: 'sun-glow-b', cx: '50%', cy: '50%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   stopColor: '#fff0bd', stopOpacity: 0.9 }),
      svgEl('stop', { offset: '30%',  stopColor: p.gold,    stopOpacity: 0.55 }),
      svgEl('stop', { offset: '100%', stopColor: p.gold,    stopOpacity: 0 })
    ]),
    svgEl('radialGradient', {
      id: 'planet-tatooine', cx: '35%', cy: '30%', r: '70%'
    }, [
      svgEl('stop', { offset: '0%',   stopColor: '#ffd58c' }),
      svgEl('stop', { offset: '60%',  stopColor: p.amber }),
      svgEl('stop', { offset: '100%', stopColor: groundShadow })
    ])
  ]);
  children.push(defs);

  // ── Starfield (180 stars, deterministic) ────────────────────────
  for (var i = 0; i < 180; i++) {
    var sx = (i * 53) % width;
    var sy = (i * 79) % height;
    var sz = i % 23 === 0 ? 1.6 : i % 11 === 0 ? 0.9 : 0.4;
    children.push(svgEl('circle', {
      cx: sx, cy: sy, r: sz,
      fill: i % 13 === 0 ? p.cyan : p.inkBright,
      opacity: 0.3 + (i % 3) * 0.2
    }));
  }

  // ── Orbital paths ───────────────────────────────────────────────
  for (var bi = 0; bi < ORBITAL_BODIES.length; bi++) {
    var ob = ORBITAL_BODIES[bi];
    children.push(svgEl('ellipse', {
      cx: cx, cy: cy, rx: ob.r, ry: ob.r * 0.85,
      fill: 'none', stroke: p.inkFaint || p.inkDim, strokeWidth: 0.4,
      strokeDasharray: '3 4', opacity: 0.5
    }));
  }

  // ── Asteroid belt (90 dotted bodies) ────────────────────────────
  var beltChildren = [];
  for (var ai = 0; ai < 90; ai++) {
    var beltA = (ai * 4) * Math.PI / 180;
    var beltR = beltInner + ((ai * 17) % 60);
    var ax = cx + Math.cos(beltA) * beltR;
    var ay = cy + Math.sin(beltA) * beltR * 0.85;
    beltChildren.push(svgEl('circle', {
      cx: ax, cy: ay, r: 0.7 + (ai % 4) * 0.3,
      fill: p.inkDim, opacity: 0.6
    }));
  }
  children.push(svgEl('g', {
    'data-asteroid-belt': '1', opacity: 0.7
  }, beltChildren));

  // ── Twin suns with bloom ────────────────────────────────────────
  children.push(svgEl('circle', {
    cx: sunA.x, cy: sunA.y, r: sunA.bloomR, fill: 'url(#sun-glow-a)'
  }));
  children.push(svgEl('circle', {
    cx: sunB.x, cy: sunB.y, r: sunB.bloomR, fill: 'url(#sun-glow-b)'
  }));
  children.push(svgEl('circle', {
    cx: sunA.x, cy: sunA.y, r: sunA.r, fill: sunA.innerFill,
    style: { filter: 'drop-shadow(0 0 14px ' + sunA.color + ')' }
  }));
  children.push(svgEl('circle', {
    cx: sunB.x, cy: sunB.y, r: sunB.r, fill: sunB.innerFill,
    style: { filter: 'drop-shadow(0 0 10px ' + sunB.color + ')' }
  }));
  children.push(svgEl('text', {
    x: sunA.x, y: sunA.y + sunA.r + 14, fontSize: 9, textAnchor: 'middle',
    fill: sunA.color, letterSpacing: 2
  }, [sunA.name]));
  children.push(svgEl('text', {
    x: sunB.x, y: sunB.y + sunB.r + 12, fontSize: 9, textAnchor: 'middle',
    fill: sunB.color, letterSpacing: 2
  }, [sunB.name]));
  children.push(svgEl('text', {
    x: (sunA.x + sunB.x) / 2, y: cy + 56, fontSize: 8, textAnchor: 'middle',
    fill: p.inkDim, letterSpacing: 2
  }, ['BINARY · K-CLASS PRIMARY · G-CLASS SECONDARY']));

  // ── Planets ─────────────────────────────────────────────────────
  for (var pi = 0; pi < ORBITAL_BODIES.length; pi++) {
    var b = ORBITAL_BODIES[pi];
    var bA = b.angle * Math.PI / 180;
    var bx = cx + Math.cos(bA) * b.r;
    var by = cy + Math.sin(bA) * b.r * 0.85;
    var bColor = p[b.colorKey] || p.inkDim;

    var bKids = [];
    if (b.player) {
      // Pulsing ring + outline + Tatooine-gradient body
      var pulseRing = svgEl('circle', {
        r: b.size * 2.4, fill: 'none', stroke: bColor,
        strokeWidth: 0.6, opacity: 0.5
      }, [
        svgEl('animate', {
          attributeName: 'r',
          values: (b.size * 1.8) + ';' + (b.size * 3.2) + ';' + (b.size * 1.8),
          dur: '2.4s', repeatCount: 'indefinite'
        }),
        svgEl('animate', {
          attributeName: 'opacity', values: '0.6;0;0.6',
          dur: '2.4s', repeatCount: 'indefinite'
        })
      ]);
      bKids.push(pulseRing);
      bKids.push(svgEl('circle', {
        r: b.size + 2, fill: 'none', stroke: bColor, strokeWidth: 1
      }));
      bKids.push(svgEl('circle', {
        r: b.size, fill: 'url(#planet-tatooine)',
        style: { filter: 'drop-shadow(0 0 6px ' + bColor + ')' }
      }));
    } else {
      bKids.push(svgEl('circle', {
        r: b.size, fill: bColor, opacity: 0.85,
        stroke: p.skyDeep, strokeWidth: 0.4
      }));
    }
    bKids.push(svgEl('text', {
      y: b.size + 14, textAnchor: 'middle',
      fontSize: b.player ? 12 : 9,
      fill: b.player ? p.inkBright : p.ink,
      fontWeight: b.player ? 700 : 400,
      letterSpacing: 2,
      style: {
        textShadow: b.player ? ('0 0 4px ' + bColor) : 'none'
      }
    }, [b.name]));

    children.push(svgEl('g', {
      'data-body': b.name,
      'data-body-player': b.player ? '1' : '0',
      transform: 'translate(' + bx + ' ' + by + ')'
    }, bKids));
  }

  // ── Hyperspace beacons ──────────────────────────────────────────
  for (var bci = 0; bci < BEACONS.length; bci++) {
    var bc = BEACONS[bci];
    var corner = bc[0], xOff = bc[1], yOff = bc[2];
    var label = bc[3], active = bc[4], hostile = bc[5];
    // Resolve corner → absolute coords
    var bcx, bcy;
    if (corner === 'top-right')    { bcx = width + xOff;  bcy = yOff; }
    else if (corner === 'top-left'){ bcx = xOff;          bcy = yOff; }
    else if (corner === 'bottom-left')  { bcx = xOff;     bcy = height + yOff; }
    else /* bottom-right */         { bcx = width + xOff; bcy = height + yOff; }

    var beaconColor = hostile ? p.red : p.green;
    var dot = svgEl('circle', {
      r: 2, fill: beaconColor,
      style: { filter: 'drop-shadow(0 0 4px ' + beaconColor + ')' }
    });
    if (active) {
      dot.appendChild(svgEl('animate', {
        attributeName: 'opacity', values: '1;0.3;1',
        dur: '2s', repeatCount: 'indefinite'
      }));
    }

    children.push(svgEl('g', {
      'data-beacon': label,
      'data-beacon-active': active ? '1' : '0',
      'data-beacon-hostile': hostile ? '1' : '0',
      transform: 'translate(' + bcx + ' ' + bcy + ')'
    }, [
      svgEl('circle', {
        r: 6, fill: 'none', stroke: beaconColor, strokeWidth: 1
      }),
      dot,
      svgEl('text', {
        y: 20, textAnchor: 'middle', fontSize: 9, fill: beaconColor,
        letterSpacing: 1.5, fontWeight: 600
      }, [label])
    ]));
  }

  // ── Player ship — RUSTY MYNOCK in low orbit ─────────────────────
  children.push(svgEl('g', {
    'data-player-ship': 'RUSTY MYNOCK',
    transform: 'translate(' + (cx + 180) + ' ' + (cy - 60) + ')'
  }, [
    svgEl('circle', {
      r: 18, fill: 'none', stroke: p.cyan, strokeWidth: 0.5, opacity: 0.5
    }, [
      svgEl('animate', {
        attributeName: 'r', values: '14;22;14',
        dur: '2s', repeatCount: 'indefinite'
      })
    ]),
    svgEl('path', {
      d: 'M 0 -8 L 6 4 L 0 2 L -6 4 Z',
      fill: p.cyan,
      style: { filter: 'drop-shadow(0 0 6px ' + p.cyan + ')' }
    }),
    svgEl('text', {
      y: 20, textAnchor: 'middle', fontSize: 10, fill: p.cyan,
      letterSpacing: 2, fontWeight: 700
    }, ['RUSTY MYNOCK']),
    svgEl('text', {
      y: 32, textAnchor: 'middle', fontSize: 8, fill: p.cyan,
      letterSpacing: 1
    }, ['Tatooine · low orbit'])
  ]));

  // ── Title + subtitle ────────────────────────────────────────────
  children.push(svgEl('text', {
    x: cx, y: 50, textAnchor: 'middle', fontSize: 20, fill: p.inkBright,
    letterSpacing: 8, fontWeight: 600,
    style: { textShadow: '0 0 8px ' + p.amber }
  }, ['TATOOINE SYSTEM']));
  children.push(svgEl('text', {
    x: cx, y: 66, textAnchor: 'middle', fontSize: 9, fill: p.inkDim,
    letterSpacing: 4
  }, ['ARKANIS SECTOR · OUTER RIM · BINARY K+G']));

  // ── Legend (top-right) ──────────────────────────────────────────
  children.push(svgEl('g', {
    'data-legend': '1',
    transform: 'translate(' + (width - 200) + ' 96)'
  }, [
    svgEl('text', {
      fontSize: 9, fill: p.inkDim, letterSpacing: 2
    }, ['★ TWIN-SUN INSOLATION']),
    svgEl('text', {
      y: 14, fontSize: 9, fill: p.inkDim, letterSpacing: 2
    }, ['◯ HYPERSPACE BEACON']),
    svgEl('text', {
      y: 28, fontSize: 9, fill: p.inkDim, letterSpacing: 2
    }, ['● ASTEROID BELT'])
  ]));

  // ── Scale bar (bottom-left) ─────────────────────────────────────
  children.push(svgEl('g', {
    'data-scale-bar': '1',
    transform: 'translate(40, ' + (height - 32) + ')'
  }, [
    svgEl('line', {
      x1: 0, y1: 0, x2: 120, y2: 0, stroke: p.ink, strokeWidth: 1
    }),
    svgEl('line', {
      x1: 0, y1: -3, x2: 0, y2: 3, stroke: p.ink, strokeWidth: 1
    }),
    svgEl('line', {
      x1: 120, y1: -3, x2: 120, y2: 3, stroke: p.ink, strokeWidth: 1
    }),
    svgEl('text', {
      x: 60, y: 14, fontSize: 8, fill: p.inkDim,
      textAnchor: 'middle', letterSpacing: 1.5
    }, ['~ 0.5 AU'])
  ]));

  return svgEl('svg', {
    'data-tier-system': '1',
    width: width, height: height,
    viewBox: '0 0 ' + width + ' ' + height,
    style: { display: 'block', background: '#000' }
  }, children);
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3TierSystemBody = {
  SCHEMA_VERSION: 1,

  // Top-level
  buildTierFourASystemBody: buildTierFourASystemBody,

  // Fixtures (public for downstream composition / Q1 audits)
  ORBITAL_BODIES: ORBITAL_BODIES,
  BEACONS:        BEACONS,
  TWIN_SUNS:      TWIN_SUNS,

  _internal: { _svgEl: svgEl }
};

})();
