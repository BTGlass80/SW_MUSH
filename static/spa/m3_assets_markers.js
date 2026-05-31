/* ============================================================================
   m3_assets_markers.js — entity markers drawn on top of the static cartography.

   Drop 4.1c · Tier 1 #4 · ported from map_v3/assets-markers.jsx (May 26 2026).

   Player chevron, PCs, NPCs by attitude, anomalies, objectives, vendor/mission/
   bounty pins. Markers are drawn at native screen size; the composition engine
   counter-scales them (`1/scale`) so they stay constant on screen at any zoom
   level (architecture v50 §4.15).

   Each builder takes an options object `{ p, size, ... }` and returns an SVG
   `<g>` element built with M3Tokens.svgEl. The composition engine wraps each
   builder's <g> with a `translate(...)` transform that positions it on the map.

   Public API: window.M3AssetsMarkers.MARKERS — a dict keyed by marker name
   (`player`, `pc`, `npc`, `vendor`, `mission`, `bounty`, `objective`,
   `anomaly_t1`, `anomaly_t2`, `anomaly_t3`). The composition engine does
   MARKERS[entity.kind]({ p: palette, ...entity }) to get the <g>.

   Note on animations: several markers (`player`, `anomaly_t1`, `anomaly_t2`,
   `anomaly_t3`) include SMIL <animate>/<animateTransform> children for pulsing
   and rotation. svgEl preserves the camelCase SVG-spec attribute names
   (`attributeName`, `repeatCount`, etc.) verbatim — they are NOT in the
   SVG_ATTR_KEBAB conversion table because they ARE camelCase in the SVG spec.
   ============================================================================ */
(function(){
'use strict';

var svgEl = window.M3Tokens.svgEl;

// ── MK_Player — pulsing cyan chevron with bearing ────────────────────
// Renders the local player's position. Outer pulse ring loops r and opacity.
function MK_Player(o) {
  var p = o.p;
  var bearing = (o.bearing != null) ? o.bearing : 0;
  var size = o.size || 14;

  var pulseRing = svgEl('circle', {
    r: size * 1.5, fill: 'none', stroke: p.cyan,
    strokeWidth: 0.8, opacity: 0.4
  }, [
    svgEl('animate', {
      attributeName: 'r',
      values: size + ';' + (size * 2.2) + ';' + size,
      dur: '2s', repeatCount: 'indefinite'
    }),
    svgEl('animate', {
      attributeName: 'opacity',
      values: '0.5;0;0.5',
      dur: '2s', repeatCount: 'indefinite'
    })
  ]);

  var inner = svgEl('circle', {
    r: size * 0.85, fill: p.skyDeep, stroke: p.cyan, strokeWidth: 1.6
  });

  // chevron path — points up before the rotate(bearing) is applied
  var chevron = svgEl('path', {
    d: 'M 0 ' + (-size * 0.65) +
       ' L ' + (size * 0.55) + ' ' + (size * 0.35) +
       ' L 0 ' + (size * 0.05) +
       ' L ' + (-size * 0.55) + ' ' + (size * 0.35) + ' Z',
    fill: p.cyan, stroke: p.cyan, strokeWidth: 0.5,
    style: 'filter: drop-shadow(0 0 ' + (size * 0.4) + 'px ' + p.cyan + ')'
  });

  return svgEl('g', { transform: 'rotate(' + bearing + ')' },
               [pulseRing, inner, chevron]);
}

// ── MK_PC — small cyan chevron with optional name label ──────────────
// Other players in the area. The label is omitted when name is falsy.
function MK_PC(o) {
  var p = o.p;
  var bearing = (o.bearing != null) ? o.bearing : 0;
  var size = o.size || 9;

  var ring = svgEl('circle', {
    r: size, fill: p.skyDeep, stroke: p.cyan,
    strokeWidth: 1, opacity: 0.9
  });

  var chevronInner = svgEl('path', {
    d: 'M 0 ' + (-size * 0.5) +
       ' L ' + (size * 0.4) + ' ' + (size * 0.3) +
       ' L ' + (-size * 0.4) + ' ' + (size * 0.3) + ' Z',
    fill: p.cyan, opacity: 0.85
  });
  var chevronGroup = svgEl('g', { transform: 'rotate(' + bearing + ')' },
                           [chevronInner]);

  var children = [ring, chevronGroup];
  if (o.name) {
    children.push(svgEl('text', {
      x: 0, y: size + 7,
      fontSize: 6, textAnchor: 'middle', fill: p.cyan,
      style: 'font-family: IBM Plex Mono, monospace; letter-spacing: 0.5px'
    }, [o.name]));
  }
  return svgEl('g', null, children);
}

// ── MK_NPC — variant by attitude ─────────────────────────────────────
// kind='hostile' → red triangle, kind='neutral' → dim grey dot,
// kind='friendly' (default) → amber dot. All glow via drop-shadow.
function MK_NPC(o) {
  var p = o.p;
  var kind = o.kind || 'friendly';
  var size = o.size || 6;

  var c;
  if (kind === 'hostile')      c = p.red;
  else if (kind === 'neutral') c = p.inkDim;
  else                         c = p.amber;

  if (kind === 'hostile') {
    var tri = svgEl('path', {
      d: 'M 0 ' + (-size * 0.9) +
         ' L ' + (size * 0.85) + ' ' + (size * 0.5) +
         ' L ' + (-size * 0.85) + ' ' + (size * 0.5) + ' Z',
      fill: c, stroke: c, strokeWidth: 0.5,
      style: 'filter: drop-shadow(0 0 3px ' + c + ')'
    });
    return svgEl('g', null, [tri]);
  }
  // neutral or friendly — dot. Neutral dims to 0.7 opacity.
  var dot = svgEl('circle', {
    r: size * 0.9, fill: c, stroke: c, strokeWidth: 0.5,
    style: 'filter: drop-shadow(0 0 2px ' + c + '); opacity: ' +
           (kind === 'neutral' ? '0.7' : '1')
  });
  return svgEl('g', null, [dot]);
}

// ── MK_Vendor — amber dot with awning glyph above ────────────────────
function MK_Vendor(o) {
  var p = o.p;
  var size = o.size || 6;
  return svgEl('g', null, [
    svgEl('circle', { r: size, fill: p.amber, opacity: 0.9 }),
    svgEl('path', {
      d: 'M ' + (-size) + ' ' + (-size * 0.2) +
         ' L ' + size + ' ' + (-size * 0.2) +
         ' L ' + (size * 0.7) + ' ' + (-size * 0.8) +
         ' L ' + (-size * 0.7) + ' ' + (-size * 0.8) + ' Z',
      fill: p.amber, stroke: p.ink, strokeWidth: 0.4
    })
  ]);
}

// ── MK_Mission — exclamation in an amber halo ────────────────────────
function MK_Mission(o) {
  var p = o.p;
  var size = o.size || 8;
  return svgEl('g', null, [
    svgEl('circle', { r: size, fill: p.amber, opacity: 0.4 }),
    svgEl('circle', { r: size * 0.6, fill: p.amber }),
    svgEl('text', {
      x: 0, y: size * 0.4,
      fontSize: size * 1.1, textAnchor: 'middle', fill: p.skyDeep,
      fontFamily: 'serif', fontWeight: 700
    }, ['!'])
  ]);
}

// ── MK_Bounty — red crosshair ────────────────────────────────────────
function MK_Bounty(o) {
  var p = o.p;
  var size = o.size || 8;
  return svgEl('g', null, [
    svgEl('circle', { r: size, fill: 'none', stroke: p.red, strokeWidth: 1.2 }),
    svgEl('line', { x1: -size * 1.4, y1: 0, x2: -size * 0.5, y2: 0,
                    stroke: p.red, strokeWidth: 1 }),
    svgEl('line', { x1:  size * 0.5, y1: 0, x2:  size * 1.4, y2: 0,
                    stroke: p.red, strokeWidth: 1 }),
    svgEl('line', { x1: 0, y1: -size * 1.4, x2: 0, y2: -size * 0.5,
                    stroke: p.red, strokeWidth: 1 }),
    svgEl('line', { x1: 0, y1:  size * 0.5, x2: 0, y2:  size * 1.4,
                    stroke: p.red, strokeWidth: 1 }),
    svgEl('circle', { r: 1.5, fill: p.red })
  ]);
}

// ── MK_Objective — green star, drop-shadow glow ──────────────────────
function MK_Objective(o) {
  var p = o.p;
  var size = o.size || 8;
  var pts = [];
  for (var i = 0; i < 10; i++) {
    var r = (i % 2 === 0) ? size : size * 0.45;
    var a = (i / 10) * Math.PI * 2 - Math.PI / 2;
    pts.push((Math.cos(a) * r) + ',' + (Math.sin(a) * r));
  }
  // The JSX source returns a bare <polygon>, not wrapped in <g> — match it.
  return svgEl('polygon', {
    points: pts.join(' '),
    fill: p.green, stroke: p.green, strokeWidth: 0.4,
    style: 'filter: drop-shadow(0 0 3px ' + p.green + ')'
  });
}

// ── MK_AnomalyT1 — amber pulsing target (low-tier anomaly) ───────────
function MK_AnomalyT1(o) {
  var p = o.p;
  var size = o.size || 9;
  return svgEl('g', null, [
    svgEl('circle', {
      r: size * 1.4, fill: 'none', stroke: p.amber,
      strokeWidth: 0.8, opacity: 0.5
    }, [
      svgEl('animate', {
        attributeName: 'r',
        values: size + ';' + (size * 1.8) + ';' + size,
        dur: '1.6s', repeatCount: 'indefinite'
      }),
      svgEl('animate', {
        attributeName: 'opacity',
        values: '0.6;0;0.6',
        dur: '1.6s', repeatCount: 'indefinite'
      })
    ]),
    svgEl('circle', { r: size, fill: p.amber, opacity: 0.3 }),
    svgEl('circle', { r: size * 0.5, fill: p.amber })
  ]);
}

// ── MK_AnomalyT2 — red rotating hex (mid-tier anomaly) ───────────────
function MK_AnomalyT2(o) {
  var p = o.p;
  var size = o.size || 10;
  function hex(r) {
    var s = [];
    for (var i = 0; i < 6; i++) {
      var a = (i / 6) * Math.PI * 2;
      s.push((Math.cos(a) * r) + ',' + (Math.sin(a) * r));
    }
    return s.join(' ');
  }
  return svgEl('g', null, [
    svgEl('polygon', {
      points: hex(size * 1.4), fill: 'none', stroke: p.red,
      strokeWidth: 0.6, opacity: 0.4
    }, [
      svgEl('animateTransform', {
        attributeName: 'transform', type: 'rotate',
        from: '0', to: '60', dur: '3s', repeatCount: 'indefinite'
      })
    ]),
    svgEl('polygon', { points: hex(size),         fill: p.red, opacity: 0.3 }),
    svgEl('polygon', { points: hex(size * 0.55),  fill: p.red })
  ]);
}

// ── MK_AnomalyT3 — gold mythic glyph (world boss) ────────────────────
// Pulsing outer ring + 8 radial spikes + glowing core.
function MK_AnomalyT3(o) {
  var p = o.p;
  var size = o.size || 14;

  var ring = svgEl('circle', {
    r: size * 1.6, fill: 'none', stroke: p.gold,
    strokeWidth: 0.8, opacity: 0.6
  }, [
    svgEl('animate', {
      attributeName: 'r',
      values: (size * 1.4) + ';' + (size * 2) + ';' + (size * 1.4),
      dur: '2.4s', repeatCount: 'indefinite'
    })
  ]);

  var children = [ring];
  // 8 spikes
  for (var i = 0; i < 8; i++) {
    var a = (i / 8) * Math.PI * 2;
    var x1 = Math.cos(a) * size * 1.1;
    var y1 = Math.sin(a) * size * 1.1;
    var x2 = Math.cos(a) * size * 1.7;
    var y2 = Math.sin(a) * size * 1.7;
    children.push(svgEl('line', {
      x1: x1, y1: y1, x2: x2, y2: y2,
      stroke: p.gold, strokeWidth: 1.2
    }));
  }
  children.push(svgEl('circle', {
    r: size, fill: p.gold, opacity: 0.3,
    style: 'filter: drop-shadow(0 0 ' + (size * 0.6) + 'px ' + p.gold + ')'
  }));
  children.push(svgEl('circle', { r: size * 0.5, fill: p.gold }));

  return svgEl('g', null, children);
}

var MARKERS = {
  player:     MK_Player,
  pc:         MK_PC,
  npc:        MK_NPC,
  vendor:     MK_Vendor,
  mission:    MK_Mission,
  bounty:     MK_Bounty,
  objective:  MK_Objective,
  anomaly_t1: MK_AnomalyT1,
  anomaly_t2: MK_AnomalyT2,
  anomaly_t3: MK_AnomalyT3
};

window.M3AssetsMarkers = {
  MARKERS: MARKERS
};

})();
