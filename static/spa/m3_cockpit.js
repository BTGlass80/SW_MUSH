/* ============================================================================
   m3_cockpit.js — Cockpit (Tier 4a · in-space view) renderer.

   Drop 4.9 · Tier 1 #4 · ported from map_v3/cockpit.jsx (623 JSX LOC)
   in SW_MUSH_UIUX_Bugfix_26May26.zip (May 27 2026).

   Adapted from the original space.jsx with the map_v3 holocarta palette.
   D6-accurate ship: dice hull, fore/aft shields, binary systems.
   Phase-aware bottom strip just like m3_combat_theater (Drop 4.5).

   What this module ships:
     · M3Cockpit.buildCockpitView(p, hooks?)          top-level container
     · M3Cockpit.buildShipInstruments(p, ship)        LEFT column
     · M3Cockpit.buildTacticalRadar(p)                CENTER · viewport
     · M3Cockpit.buildCockpitFeedRow(p, entry)        pose/comms/sys-event
     · M3Cockpit.buildTargetLockPanel(p, target)      RIGHT · target lock
     · M3Cockpit.buildHyperspacePlot(p, dest, pct,
                                     backupDrive?)    RIGHT · jump status
     · M3Cockpit.buildCrewPanel(p, crew?)             RIGHT · stations
     · M3Cockpit.buildCockpitActionStrip(p, hooks?)   BOTTOM · phase-aware
     · M3Cockpit.buildLabel(p, label, right?, style?) section header helper
     · M3Cockpit.COCKPIT_SHIP_FIXTURE                 Rusty Mynock demo ship
     · M3Cockpit.COCKPIT_TARGET_FIXTURE               Vulture Droid demo target
     · M3Cockpit.COCKPIT_FEED_FIXTURE                 sample pose/comms feed

   Era cleanness: the demo fixtures are Clone-Wars-era only — Vulture
   Droid (CIS), Geonosian signatures, Tatooine low orbit, no Empire
   references anywhere in the source.

   Dependencies (loaded earlier in the SPA load order):
     · window.M3CombatTheater.buildActionButton (Drop 4.5) — consumed
       by buildCockpitActionStrip for the action chips. If absent, the
       action strip still renders, with a minimal fallback button per
       chip. The fallback is documented; the production path is always
       the M3CombatTheater builder.

   What this module does NOT ship:
     · A +cockpit command wire-in. The eventual integration: when the
       player is aboard a ship, the SPA can swap from the standard
       ground HUD to the cockpit view.
     · Live phase-state management. Like Drop 4.5 combat-theater, this
       is scaffold-and-pieces; phase / actions / round all come from
       hooks.actionStripState (defaults to a DEMO state).
     · Real-time hull-pip animation. Static render of ship.hullDamage.

   Loading order in client.html: after m3_map_navigator.js (and after
   m3_combat_theater.js since it consumes buildActionButton via DI).
   ============================================================================ */
(function(){
'use strict';

// ─── Module-private state ────────────────────────────────────────────
var _escapeHtml = null;

function init(deps) {
  deps = deps || {};
  _escapeHtml = deps.escapeHtml || _defaultEscapeHtml;
}

function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ─── htmlEl / svgEl: same shape as Drops 4.5-4.8 ─────────────────────
function htmlEl(tag, props, children) {
  var el = document.createElement(tag);
  if (props) {
    for (var key in props) {
      if (!Object.prototype.hasOwnProperty.call(props, key)) continue;
      var val = props[key];
      if (val === undefined || val === null || val === false) continue;
      if (key === 'style') {
        applyStyle(el, val);
      } else if (key === 'className') {
        el.className = String(val);
      } else if (key === 'onClick' && typeof val === 'function') {
        el.addEventListener('click', val);
      } else if (key.indexOf('on') === 0 && typeof val === 'function') {
        el.addEventListener(key.slice(2).toLowerCase(), val);
      } else {
        el.setAttribute(key, String(val));
      }
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
  if (k === 'viewBox' || k === 'preserveAspectRatio' ||
      k === 'gradientTransform' || k === 'patternTransform' ||
      k === 'patternUnits' || k === 'patternContentUnits') return k;
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
// FIXTURES — Clone-Wars-era demo data
// ════════════════════════════════════════════════════════════════════
var COCKPIT_SHIP_FIXTURE = {
  name: 'RUSTY MYNOCK',
  class: 'YT-1300 · Starfighter Scale',
  hullDice: '4D',
  hullPips: 12,
  hullDamage: 3,
  cond: 'LIGHT DAMAGE',
  shieldsUp: true,
  shieldFore: 2,
  shieldAft:  1,
  hyperdrive: 2,
  hyperdriveBackup: 12,
  consumables: '2 MO',
  systems: [
    { name: 'ENGINES',    ok: true },
    { name: 'WEAPONS',    ok: true },
    { name: 'SHIELDS',    ok: true },
    { name: 'HYPERDRIVE', ok: false },
    { name: 'SENSORS',    ok: true },
  ],
};

var COCKPIT_TARGET_FIXTURE = {
  id: 'CIS-V1',
  class: 'Vulture Droid · Light Starfighter',
  faction: 'CIS · Hostile',
  range: '14.2K',
  bearing: '305°',
  hullDice: '2D',
  cond: 'PRISTINE',
  shieldDice: '1D',
};

var COCKPIT_FEED_FIXTURE = [
  { kind: 'system-event', text: 'Sublight engaged · Tatooine low orbit · 142km altitude', muted: true },
  { kind: 'pose', actor: 'TEY VOSS', verb: 'poses', side: 'self', time: '0:48',
    text: "rolls the Mynock hard to port, twin engines glowing as she chases the vulture droid through the upper atmosphere haze. Stars wheel sideways past the cockpit canopy." },
  { kind: 'comms', sender: 'MAREK · COM 4', tone: 'ally',
    text: '"Tey, two more bandits coming up from the surface — Geonosian signatures. They want you BAD."' },
  { kind: 'sys-event', text: 'Proximity warning · 2 hostiles closing · range 22K → 18K', tone: 'red' },
  { kind: 'pose', actor: 'SCENE', verb: '', side: 'system', time: '0:32',
    text: "The vulture droid pulls into a tight banking turn, droid brain calculating an intercept. Its forward cannons begin to glow." },
  { kind: 'sys-event', text: 'Target lock acquired · CIS-V1 · range 14.2K', tone: 'green' },
];

var COCKPIT_ACTION_DEFAULT = {
  phase: 'DECLARATION',
  round: 4,
  waitingOn: 'you, marek, k3-s0',
  declared: '— none yet',
  actions: [
    { id: 'fire',    label: 'FIRE',          icon: '✤', enabled: true,  cost: 'Gunnery 5D' },
    { id: 'dodge',   label: 'DODGE',         icon: '⚝', enabled: true,  cost: '−1D MAP if 2nd' },
    { id: 'evade',   label: 'EVADE',         icon: '↬', enabled: true,  cost: 'Piloting 5D+2' },
    { id: 'aim',     label: 'AIM',           icon: '⦿', enabled: true,  cost: '+1D next' },
    { id: 'shields', label: 'ANGLE SHIELDS', icon: '◈', enabled: true,  cost: '+1D fore/aft' },
    { id: 'jam',     label: 'JAM SENSORS',   icon: '⊠', enabled: false, cost: 'sensors damaged' },
    { id: 'jump',    label: 'JUMP',          icon: '✦', enabled: false, cost: 'nav comp 62%' },
    { id: 'flee',    label: 'BUG OUT',       icon: '⤥', enabled: true,  cost: 'end combat' },
  ],
};

// ════════════════════════════════════════════════════════════════════
// Label helper — section heading with optional right-aligned chip
// ════════════════════════════════════════════════════════════════════
function buildLabel(p, label, right, style) {
  var base = {
    fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600,
    marginBottom: 6, display: 'flex', justifyContent: 'space-between',
  };
  if (style) {
    for (var k in style) {
      if (Object.prototype.hasOwnProperty.call(style, k)) base[k] = style[k];
    }
  }
  var children = [htmlEl('span', null, [label])];
  if (right !== undefined && right !== null) {
    if (typeof right === 'string' || typeof right === 'number') {
      children.push(htmlEl('span', null, [right]));
    } else {
      children.push(right);
    }
  }
  return htmlEl('div', { style: base }, children);
}

// ════════════════════════════════════════════════════════════════════
// SHIP INSTRUMENTS — LEFT column (hull / shields / systems / hyperdrive)
// ════════════════════════════════════════════════════════════════════
function buildShipInstruments(p, ship) {
  ship = ship || COCKPIT_SHIP_FIXTURE;
  var condColorMap = {
    'PRISTINE':         p.green,
    'LIGHT DAMAGE':     p.green,
    'MODERATE DAMAGE':  p.amber,
    'HEAVY DAMAGE':     p.amber,
    'CRITICAL DAMAGE':  p.red,
    'DESTROYED':        p.red,
  };
  var condColor = condColorMap[ship.cond] || p.cyan;
  var remaining = Math.max(0, ship.hullPips - ship.hullDamage);

  // Ship name + class banner
  var nameBlock = htmlEl('div', null, [
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 16, color: p.cyan,
        letterSpacing: 2, textShadow: '0 0 6px ' + p.cyan + '66', fontWeight: 700,
      }
    }, [ship.name]),
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 2, color: p.inkDim, marginTop: 2, marginBottom: 16 }
    }, [String(ship.class || '').toUpperCase()]),
  ]);

  // HULL — pips + condition
  var pips = [];
  for (var i = 0; i < ship.hullPips; i++) {
    pips.push(htmlEl('div', {
      'data-hull-pip-index': String(i),
      'data-hull-pip-state': i < remaining ? 'ok' : 'damaged',
      style: {
        width: 10, height: 10,
        background: i < remaining ? p.cyan : 'transparent',
        border: '1px solid ' + (i < remaining ? p.cyan : p.red),
        boxShadow: i < remaining ? ('0 0 3px ' + p.cyan) : 'none',
      }
    }));
  }
  var hullBlock = htmlEl('div', null, [
    buildLabel(p, '▮▮ HULL',
      htmlEl('span', { style: { color: p.cyan } }, [ship.hullDice])),
    htmlEl('div', {
      'data-section': 'hull',
      style: {
        padding: 8, background: 'rgba(0,0,0,0.45)',
        border: '1px solid ' + p.cyan + '44', marginBottom: 14,
      }
    }, [
      htmlEl('div', {
        style: { display: 'flex', flexWrap: 'wrap', gap: 2, marginBottom: 6 }
      }, pips),
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 12,
          color: condColor, letterSpacing: 2, fontWeight: 700,
          textShadow: '0 0 6px ' + condColor,
        }
      }, [ship.cond]),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, letterSpacing: 1, marginTop: 2 }
      }, [ship.hullDamage + '/' + ship.hullPips + ' pips damage']),
    ]),
  ]);

  // SHIELDS — fore/aft bars
  var shieldRows = [['FORE', ship.shieldFore], ['AFT', ship.shieldAft]].map(function(pair) {
    var arc = pair[0], dice = pair[1];
    var diceCells = [];
    for (var j = 0; j < 3; j++) {
      diceCells.push(htmlEl('div', {
        style: {
          flex: 1, height: 6,
          background: (j < dice && ship.shieldsUp) ? p.cyan : 'transparent',
          border: '1px solid ' + p.cyan + '44',
          boxShadow: (j < dice && ship.shieldsUp) ? ('0 0 3px ' + p.cyan) : 'none',
        }
      }));
    }
    return htmlEl('div', {
      'data-shield-arc': arc,
      style: {
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '4px 0', borderBottom: '1px dotted ' + p.cyan + '33',
      }
    }, [
      htmlEl('span', {
        style: { fontSize: 9, letterSpacing: 2, color: p.inkDim, width: 36 }
      }, [arc]),
      htmlEl('div', {
        style: { display: 'flex', gap: 2, flex: 1 }
      }, diceCells),
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 12,
          color: ship.shieldsUp ? p.cyan : p.inkDim,
          letterSpacing: 1, minWidth: 22, textAlign: 'right',
        }
      }, [dice + 'D']),
    ]);
  });
  var shieldsBlock = htmlEl('div', null, [
    buildLabel(p, '▮▮ SHIELDS',
      htmlEl('span', {
        style: {
          color: ship.shieldsUp ? p.green : p.red, letterSpacing: 1,
        }
      }, [ship.shieldsUp ? '◉ UP' : '○ DOWN'])),
    htmlEl('div', {
      'data-section': 'shields',
      style: {
        padding: 8, background: 'rgba(0,0,0,0.45)',
        border: '1px solid ' + p.cyan + '44', marginBottom: 14,
      }
    }, shieldRows),
  ]);

  // SYSTEMS — list of binary OK/DMG rows
  var systemRows = (ship.systems || []).map(function(s) {
    return htmlEl('div', {
      'data-system-name': s.name,
      'data-system-ok': s.ok ? 'true' : 'false',
      style: {
        display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 10, padding: '3px 6px', marginBottom: 3,
        background: 'rgba(0,0,0,0.4)',
        border: '1px solid ' + (s.ok ? (p.cyan + '44') : p.red),
      }
    }, [
      htmlEl('div', {
        style: {
          width: 6, height: 6, borderRadius: '50%',
          background: s.ok ? p.green : p.red,
          boxShadow: '0 0 4px ' + (s.ok ? p.green : p.red),
        }
      }),
      htmlEl('span', {
        style: { color: s.ok ? p.inkBright : p.red, letterSpacing: 1, flex: 1 }
      }, [s.name]),
      htmlEl('span', {
        style: {
          color: s.ok ? p.green : p.red, fontWeight: 600,
          letterSpacing: 1, fontSize: 9,
        }
      }, [s.ok ? 'OK' : 'DMG']),
    ]);
  });
  var systemsBlock = htmlEl('div', null,
    [buildLabel(p, '▮▮ SYSTEMS')].concat(systemRows)
  );

  // HYPERDRIVE
  var hyperdriveBlock = htmlEl('div', null, [
    buildLabel(p, '▮▮ HYPERDRIVE', null, { marginTop: 14 }),
    htmlEl('div', {
      'data-section': 'hyperdrive',
      style: {
        padding: 8, background: 'rgba(0,0,0,0.45)',
        border: '1px solid ' + p.cyan + '44',
      }
    }, [
      htmlEl('div', {
        style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }
      }, [
        htmlEl('span', {
          style: {
            fontFamily: "'Space Grotesk'", fontSize: 22, color: p.cyan,
            letterSpacing: 1, fontWeight: 700,
          }
        }, ['×' + ship.hyperdrive]),
        htmlEl('span', {
          style: { fontSize: 9, color: p.inkDim, letterSpacing: 2 }
        }, ['PRIMARY']),
      ]),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, marginTop: 4 }
      }, ['backup ×' + ship.hyperdriveBackup + ' · consumables ' + ship.consumables]),
    ]),
  ]);

  return htmlEl('div', {
    'data-cockpit-instruments': '1',
    style: { color: p.ink, fontSize: 11 }
  }, [nameBlock, hullBlock, shieldsBlock, systemsBlock, hyperdriveBlock]);
}

// ════════════════════════════════════════════════════════════════════
// TACTICAL RADAR — CENTER viewport
// ════════════════════════════════════════════════════════════════════
function buildTacticalRadar(p) {
  var svgChildren = [];

  // grid
  for (var i = 0; i < 16; i++) {
    svgChildren.push(svgEl('line', {
      x1: i * 50, y1: 0, x2: i * 50, y2: 200,
      stroke: p.cyan, strokeWidth: 0.3, strokeDasharray: '2 3', opacity: 0.3,
    }));
  }
  for (var j = 0; j < 8; j++) {
    svgChildren.push(svgEl('line', {
      x1: 0, y1: j * 25, x2: 800, y2: j * 25,
      stroke: p.cyan, strokeWidth: 0.3, strokeDasharray: '2 3', opacity: 0.3,
    }));
  }

  // horizon
  svgChildren.push(svgEl('line', {
    x1: 0, y1: 100, x2: 800, y2: 100,
    stroke: p.cyan, strokeWidth: 0.6, opacity: 0.4,
  }));

  // range arcs
  [200, 320, 440].forEach(function(r, idx) {
    svgChildren.push(svgEl('ellipse', {
      cx: 400, cy: 100, rx: r * 0.9, ry: r * 0.45,
      fill: 'none', stroke: p.cyan, strokeWidth: 0.4,
      opacity: 0.3 - idx * 0.07, strokeDasharray: '4 4',
    }));
  });

  // YOU marker (green crosshair + ring)
  var youGroup = svgEl('g', { transform: 'translate(400 100)', 'data-radar-marker': 'you' }, [
    svgEl('circle', { r: 10, fill: 'none', stroke: p.green, strokeWidth: 0.8, opacity: 0.5 }),
    svgEl('circle', { r: 5, fill: p.green,
                      style: { filter: 'drop-shadow(0 0 6px ' + p.green + ')' } }),
    svgEl('line', { x1: -14, y1: 0, x2: -7, y2: 0, stroke: p.green, strokeWidth: 0.8 }),
    svgEl('line', { x1: 7,   y1: 0, x2: 14, y2: 0, stroke: p.green, strokeWidth: 0.8 }),
    svgEl('line', { x1: 0, y1: -14, x2: 0, y2: -7, stroke: p.green, strokeWidth: 0.8 }),
    svgEl('line', { x1: 0, y1: 7,   x2: 0, y2: 14, stroke: p.green, strokeWidth: 0.8 }),
    svgEl('text', { y: -18, textAnchor: 'middle', fontSize: 9, fill: p.green,
                    fontFamily: 'IBM Plex Mono', letterSpacing: 2 }, ['YOU']),
  ]);
  svgChildren.push(youGroup);

  // Allied wingmate (MAREK)
  svgChildren.push(svgEl('g', {
    transform: 'translate(280 80)', 'data-radar-marker': 'marek'
  }, [
    svgEl('circle', { r: 4, fill: p.cyan,
                      style: { filter: 'drop-shadow(0 0 4px ' + p.cyan + ')' } }),
    svgEl('text', { y: -8, textAnchor: 'middle', fontSize: 8, fill: p.cyan,
                    fontFamily: 'IBM Plex Mono' }, ['MAREK']),
  ]));

  // Hostile — locked (CIS-V1)
  svgChildren.push(svgEl('g', {
    transform: 'translate(560 70)', 'data-radar-marker': 'cis-v1'
  }, [
    svgEl('rect', {
      x: -8, y: -8, width: 16, height: 16,
      fill: 'none', stroke: p.red, strokeWidth: 0.8,
    }, [
      svgEl('animate', {
        attributeName: 'opacity', values: '1;0.4;1',
        dur: '1.2s', repeatCount: 'indefinite',
      }),
    ]),
    svgEl('path', { d: 'M 0 -5 L 5 4 L -5 4 Z', fill: p.red,
                    style: { filter: 'drop-shadow(0 0 4px ' + p.red + ')' } }),
    svgEl('text', { y: -14, textAnchor: 'middle', fontSize: 8, fill: p.red,
                    fontFamily: 'IBM Plex Mono', fontWeight: 600, letterSpacing: 1 },
          ['CIS-V1 ◉ LOCKED']),
    svgEl('text', { y: 22, textAnchor: 'middle', fontSize: 7, fill: p.red,
                    fontFamily: 'IBM Plex Mono' }, ['14.2K · 305°']),
  ]));

  // CIS-V2
  svgChildren.push(svgEl('g', {
    transform: 'translate(640 130)', 'data-radar-marker': 'cis-v2'
  }, [
    svgEl('path', { d: 'M 0 -4 L 4 3 L -4 3 Z', fill: p.red, opacity: 0.7 }),
    svgEl('text', { y: -8, textAnchor: 'middle', fontSize: 7, fill: p.red,
                    fontFamily: 'IBM Plex Mono' }, ['CIS-V2']),
  ]));

  // Geonosian
  svgChildren.push(svgEl('g', {
    transform: 'translate(720 60)', 'data-radar-marker': 'geono-1'
  }, [
    svgEl('path', { d: 'M 0 -4 L 4 3 L -4 3 Z', fill: p.red, opacity: 0.7 }),
    svgEl('text', { y: -8, textAnchor: 'middle', fontSize: 7, fill: p.red,
                    fontFamily: 'IBM Plex Mono' }, ['GEONO-1']),
  ]));

  // atmospheric horizon glow
  svgChildren.push(svgEl('ellipse', {
    cx: 400, cy: 200, rx: 500, ry: 70, fill: p.amber, opacity: 0.08,
  }));

  var svg = svgEl('svg', {
    viewBox: '0 0 800 200', width: '100%', height: '100%',
    preserveAspectRatio: 'none',
  }, svgChildren);

  // HUD overlays
  var hudTopLeft = htmlEl('div', {
    style: { position: 'absolute', top: 8, left: 14,
             fontSize: 9, letterSpacing: 3, color: p.cyan }
  }, ['▮ TACTICAL · 40K RANGE']);

  var hudTopRight = htmlEl('div', {
    style: { position: 'absolute', top: 8, right: 14,
             fontSize: 9, letterSpacing: 2, color: p.inkDim, textAlign: 'right' }
  }, [
    'BEARING ',
    htmlEl('span', { style: { color: p.cyan } }, ['112°']),
    htmlEl('br', null),
    'ALT ',
    htmlEl('span', { style: { color: p.cyan } }, ['142 KM']),
  ]);

  var hudBottomLeft = htmlEl('div', {
    style: { position: 'absolute', bottom: 8, left: 14,
             fontSize: 9, letterSpacing: 2, color: p.inkDim }
  }, [
    'SUBLIGHT ',
    htmlEl('span', { style: { color: p.green } }, ['78%']),
    ' · IFF ',
    htmlEl('span', { style: { color: p.red } }, ['3 HOSTILE']),
  ]);

  var hudBottomRight = htmlEl('div', {
    style: { position: 'absolute', bottom: 8, right: 14,
             fontSize: 9, letterSpacing: 2, color: p.inkDim }
  }, [
    'SCAN ',
    htmlEl('span', {
      style: { color: p.cyan, animation: 'combatPulse 2s linear infinite' }
    }, ['●']),
  ]);

  return htmlEl('div', {
    'data-cockpit-radar': '1',
    style: {
      height: 200, position: 'relative', overflow: 'hidden',
      background: 'radial-gradient(ellipse at center, ' + p.cyan + '11, transparent 70%), ' + p.skyDeep,
    }
  }, [svg, hudTopLeft, hudTopRight, hudBottomLeft, hudBottomRight]);
}

// ════════════════════════════════════════════════════════════════════
// COCKPIT FEED ROW — poses / comms / sys-events / system-events
// ════════════════════════════════════════════════════════════════════
function buildCockpitFeedRow(p, entry) {
  if (!entry || !entry.kind) return null;

  if (entry.kind === 'pose') {
    var c = (entry.side === 'self')   ? p.green
          : (entry.side === 'system') ? p.inkDim
          :                             p.cyan;
    var header = [
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 12, fontWeight: 700,
          color: c, letterSpacing: 1.5,
        }
      }, [entry.actor]),
    ];
    if (entry.verb) {
      header.push(htmlEl('span', {
        style: { fontSize: 10, fontStyle: 'italic', color: p.inkDim }
      }, [entry.verb]));
    }
    header.push(htmlEl('span', {
      style: { marginLeft: 'auto', fontSize: 9, color: p.inkFaint, letterSpacing: 1.5 }
    }, [entry.time || '']));

    return htmlEl('div', {
      'data-feed-kind': 'pose',
      'data-feed-side': entry.side || '',
      style: {
        padding: '8px 12px', marginBottom: 8,
        background: (entry.side === 'self') ? (p.green + '10') : (c + '08'),
        borderLeft: '3px solid ' + c,
      }
    }, [
      htmlEl('div', {
        style: { display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 3 }
      }, header),
      htmlEl('div', {
        style: {
          fontFamily: "'IBM Plex Sans', sans-serif",
          fontSize: 13, lineHeight: 1.6, color: p.inkBright,
        }
      }, [entry.text || '']),
    ]);
  }

  if (entry.kind === 'comms') {
    var commsColor = (entry.tone === 'ally') ? p.cyan : p.amber;
    return htmlEl('div', {
      'data-feed-kind': 'comms',
      style: {
        padding: '6px 12px', marginBottom: 8,
        background: 'rgba(0,0,0,0.35)',
        borderLeft: '2px dashed ' + commsColor,
      }
    }, [
      htmlEl('div', {
        style: { fontSize: 9, letterSpacing: 2, color: commsColor, marginBottom: 3 }
      }, ['◇ COMMS · ' + (entry.sender || '')]),
      htmlEl('div', {
        style: {
          fontFamily: "'IBM Plex Sans'", fontSize: 12.5, color: p.ink, fontStyle: 'italic',
        }
      }, [entry.text || '']),
    ]);
  }

  if (entry.kind === 'sys-event') {
    var sysColor = (entry.tone === 'red')   ? p.red
                 : (entry.tone === 'green') ? p.green
                 :                            p.inkDim;
    var prefix = (entry.tone === 'red')   ? '⚠ '
              : (entry.tone === 'green') ? '✓ '
              :                            '› ';
    return htmlEl('div', {
      'data-feed-kind': 'sys-event',
      'data-feed-tone': entry.tone || 'neutral',
      style: {
        padding: '4px 12px', marginBottom: 6,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 10.5, color: sysColor, letterSpacing: 0.5,
        opacity: entry.muted ? 0.6 : 1,
        borderLeft: '2px solid ' + sysColor,
      }
    }, [prefix + (entry.text || '')]);
  }

  if (entry.kind === 'system-event') {
    return htmlEl('div', {
      'data-feed-kind': 'system-event',
      style: {
        padding: '6px 12px', margin: '6px 0',
        borderTop: '1px dashed ' + p.inkFaint,
        borderBottom: '1px dashed ' + p.inkFaint,
        fontSize: 10, color: p.inkDim, letterSpacing: 3,
        opacity: entry.muted ? 0.7 : 1,
      }
    }, ['▮ ' + (entry.text || '')]);
  }

  return null;
}

// ════════════════════════════════════════════════════════════════════
// TARGET LOCK PANEL — RIGHT column
// ════════════════════════════════════════════════════════════════════
function buildTargetLockPanel(p, target) {
  target = target || COCKPIT_TARGET_FIXTURE;

  var stats = [
    ['RANGE', target.range],
    ['BRG',   target.bearing],
    ['HULL',  target.hullDice + ' · ' + target.cond],
    ['SHLD',  target.shieldDice],
  ].map(function(pair) {
    return htmlEl('div', {
      'data-target-stat': pair[0],
      style: { padding: '3px 6px', background: 'rgba(0,0,0,0.35)' }
    }, [
      htmlEl('span', {
        style: { color: p.inkDim, fontSize: 8, letterSpacing: 1.5 }
      }, [pair[0]]),
      htmlEl('div', {
        style: { color: p.red, fontWeight: 600 }
      }, [pair[1]]),
    ]);
  });

  return htmlEl('div', {
    'data-cockpit-target': '1'
  }, [
    buildLabel(p, '▮▮ TARGET LOCK'),
    htmlEl('div', {
      style: {
        padding: 10, background: 'rgba(0,0,0,0.45)',
        border: '1px solid ' + p.red,
        boxShadow: 'inset 0 0 10px ' + p.red + '22',
      }
    }, [
      htmlEl('div', {
        style: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }
      }, [
        htmlEl('div', {
          style: {
            fontFamily: "'Space Grotesk'", fontSize: 15, color: p.red,
            letterSpacing: 1.5, fontWeight: 700,
          }
        }, [target.id]),
        htmlEl('div', {
          style: {
            fontSize: 9, letterSpacing: 2, color: p.red,
            border: '1px solid ' + p.red, padding: '1px 5px',
          }
        }, ['LOCKED']),
      ]),
      htmlEl('div', {
        style: { fontSize: 10, color: p.inkBright, marginTop: 3 }
      }, [target.class]),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, marginTop: 1, letterSpacing: 1 }
      }, [target.faction]),
      htmlEl('div', {
        style: {
          marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 10,
        }
      }, stats),
    ]),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// HYPERSPACE PLOT — RIGHT column
// ════════════════════════════════════════════════════════════════════
function buildHyperspacePlot(p, dest, pct, backupDriveMultiplier) {
  return htmlEl('div', {
    'data-cockpit-hyperspace': '1'
  }, [
    buildLabel(p, '▮▮ HYPERSPACE PLOT'),
    htmlEl('div', {
      style: { padding: 10, background: 'rgba(0,0,0,0.45)', border: '1px solid ' + p.cyan + '44' }
    }, [
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 13, color: p.cyan,
          letterSpacing: 1, fontWeight: 600,
        }
      }, [dest]),
      htmlEl('div', {
        style: {
          height: 6, background: p.skyDeep, border: '1px solid ' + p.cyan + '44',
          marginTop: 6, position: 'relative', overflow: 'hidden',
        }
      }, [
        htmlEl('div', {
          'data-hyperspace-fill': '1',
          style: {
            position: 'absolute', inset: 0, width: pct + '%',
            background: p.cyan, boxShadow: '0 0 4px ' + p.cyan,
          }
        }),
      ]),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, marginTop: 4, letterSpacing: 1 }
      }, [
        'NAV COMP ',
        htmlEl('span', { style: { color: p.cyan } }, [pct + '%']),
        ' · jump in 2:30',
      ]),
      (backupDriveMultiplier != null ? htmlEl('div', {
        style: { fontSize: 9, color: p.red, marginTop: 4, letterSpacing: 1 }
      }, [
        '⚠ HYPERDRIVE DAMAGED · backup engaged ×' + backupDriveMultiplier
      ]) : null),
    ]),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// CREW PANEL — RIGHT column
// ════════════════════════════════════════════════════════════════════
function buildCrewPanel(p, crew) {
  // Default crew matches the JSX source.
  crew = crew || [
    { role: 'PILOT',    name: 'Tey Voss',    color: p.green },
    { role: 'CO-PILOT', name: '—',           color: p.inkFaint },
    { role: 'GUNNER',   name: 'K3-S0 (AI)',  color: p.amber },
    { role: 'ENGINEER', name: '—',           color: p.inkFaint },
  ];

  var rows = crew.map(function(c) {
    return htmlEl('div', {
      'data-crew-role': c.role,
      style: {
        display: 'flex', justifyContent: 'space-between',
        padding: '2px 0', borderBottom: '1px dotted ' + p.cyan + '22',
      }
    }, [
      htmlEl('span', {
        style: { color: p.inkDim, letterSpacing: 1 }
      }, [c.role]),
      htmlEl('span', {
        style: { color: c.color }
      }, [c.name]),
    ]);
  });

  return htmlEl('div', {
    'data-cockpit-crew': '1'
  }, [
    buildLabel(p, '▮▮ CREW · STATIONS'),
    htmlEl('div', {
      style: {
        padding: '4px 10px', background: 'rgba(0,0,0,0.35)',
        border: '1px solid ' + p.cyan + '33', fontSize: 10, lineHeight: 1.9,
      }
    }, rows),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// COCKPIT ACTION STRIP — phase-aware bottom strip
// (Wraps M3CombatTheater.buildActionButton via DI; falls back to a
// minimal local renderer if the combat-theater module isn't loaded.)
// ════════════════════════════════════════════════════════════════════
function buildCockpitActionStrip(p, hooks) {
  hooks = hooks || {};
  var state = hooks.actionStripState || COCKPIT_ACTION_DEFAULT;
  var onActionClick = hooks.onActionClick || null;
  var onSubmit      = hooks.onSubmit || null;

  // Phase header (chip + descriptor + waiting line)
  var phaseChip = htmlEl('div', {
    style: {
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '4px 10px',
      background: p.amber + '22',
      border: '1px solid ' + p.amber,
      boxShadow: '0 0 8px ' + p.amber + '44',
    }
  }, [
    htmlEl('div', {
      style: {
        width: 6, height: 6, borderRadius: '50%', background: p.amber,
        animation: 'combatPulse 1.4s ease-in-out infinite',
      }
    }),
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 11, color: p.amber,
        letterSpacing: 3, fontWeight: 700,
      }
    }, ['PHASE · ' + state.phase]),
  ]);

  var descLine = htmlEl('div', {
    style: { fontSize: 10, color: p.inkDim, letterSpacing: 1.5, flex: 1 }
  }, [
    'Declare action(s). Second action triggers ',
    htmlEl('span', { style: { color: p.red } }, ['MAP −1D']),
    '. Crew positions roll independently.',
  ]);

  var roundLine = htmlEl('div', {
    style: { fontSize: 10, color: p.cyan, letterSpacing: 2 }
  }, [
    'ROUND ' + state.round + ' · WAITING ON: ',
    htmlEl('span', { style: { color: p.amber } }, [state.waitingOn]),
  ]);

  var phaseHeader = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 14 }
  }, [phaseChip, descLine, roundLine]);

  // Action buttons. Prefer M3CombatTheater.buildActionButton if it's loaded.
  var theaterMod = (typeof window !== 'undefined') && window.M3CombatTheater;
  var actionFactory = (theaterMod && typeof theaterMod.buildActionButton === 'function')
                     ? theaterMod.buildActionButton
                     : _fallbackActionButton;
  var actionChips = (state.actions || []).map(function(a) {
    var onClick = (typeof onActionClick === 'function')
                  ? function() { onActionClick(a.id); }
                  : null;
    return actionFactory(p, a, false /* hasMap */, onClick);
  });

  var declaredLabel = htmlEl('div', {
    style: {
      fontSize: 9, color: p.inkDim, letterSpacing: 2,
      padding: '6px 10px', borderRight: '1px solid ' + p.inkFaint,
    }
  }, [
    'DECLARED: ',
    htmlEl('span', { style: { color: p.amber } }, [state.declared || '— none yet']),
  ]);

  var submitBtnProps = {
    'data-submit-btn': '1',
    style: {
      marginLeft: 'auto', padding: '6px 14px',
      background: p.amber, color: p.skyDeep,
      border: '1px solid ' + p.amber, fontWeight: 700, letterSpacing: 2,
      fontSize: 11, cursor: 'pointer',
      boxShadow: '0 0 10px ' + p.amber + '66',
      fontFamily: "'IBM Plex Mono', monospace",
    }
  };
  if (typeof onSubmit === 'function') submitBtnProps.onClick = onSubmit;
  var submitBtn = htmlEl('button', submitBtnProps, ['SUBMIT ↵']);

  var actionRow = htmlEl('div', {
    style: { display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }
  }, [declaredLabel].concat(actionChips).concat([submitBtn]));

  return htmlEl('div', {
    'data-cockpit-action-strip': '1',
    style: {
      position: 'absolute', bottom: 0, left: 0, right: 0, height: 110,
      borderTop: '2px solid ' + p.amber,
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', ' + p.sky + ')',
      padding: '10px 16px',
      display: 'flex', flexDirection: 'column', gap: 8,
      zIndex: 60,
    }
  }, [phaseHeader, actionRow]);
}

// Local fallback action-button renderer — used only when
// M3CombatTheater isn't loaded. Minimal styling, no MAP-decoration.
function _fallbackActionButton(p, action, hasMap, onClick) {
  var enabled = !!action.enabled;
  var props = {
    'data-fallback-action-btn': action.id,
    title: action.cost,
    style: {
      padding: '6px 10px',
      background: enabled ? (p.amber + '22') : 'transparent',
      border: '1px solid ' + (enabled ? p.amber : p.inkFaint),
      color: enabled ? p.amber : p.inkFaint,
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 10, letterSpacing: 1.5, fontWeight: 600,
      cursor: enabled ? 'pointer' : 'not-allowed',
      opacity: enabled ? 1 : 0.55,
    }
  };
  if (enabled && typeof onClick === 'function') props.onClick = onClick;
  return htmlEl('button', props, [(action.icon ? action.icon + ' ' : '') + action.label]);
}

// ════════════════════════════════════════════════════════════════════
// TOP-LEVEL — CockpitView
// ════════════════════════════════════════════════════════════════════
function buildCockpitView(p, hooks) {
  hooks = hooks || {};
  var ship   = hooks.ship   || COCKPIT_SHIP_FIXTURE;
  var target = hooks.target || COCKPIT_TARGET_FIXTURE;
  var feed   = hooks.feed   || COCKPIT_FEED_FIXTURE;
  var crew   = hooks.crew;     // null/undefined → buildCrewPanel default
  var width  = hooks.width  || 1280;
  var height = hooks.height || 920;
  var hyperspaceDest = hooks.hyperspaceDest || 'ANCHORHEAD → KESSEL';
  var hyperspacePct  = (hooks.hyperspacePct != null) ? hooks.hyperspacePct : 62;
  var backupDrive    = (hooks.backupDriveMultiplier != null)
                       ? hooks.backupDriveMultiplier
                       : ship.hyperdriveBackup;

  // TOP BAR — IFF / GST / location
  var topLeft = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 14 }
  }, [
    htmlEl('div', {
      style: {
        width: 8, height: 8, borderRadius: '50%', background: p.cyan,
        boxShadow: '0 0 6px ' + p.cyan,
        animation: 'combatPulse 2.4s ease-in-out infinite',
      }
    }),
    htmlEl('span', {
      style: { fontSize: 10, color: p.cyan, letterSpacing: 4, fontWeight: 600 }
    }, ['◉ COCKPIT · FLIGHT CONSOLE']),
    htmlEl('span', {
      style: { height: 18, width: 1, background: p.inkDim }
    }),
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk', sans-serif",
        fontSize: 16, color: p.cyan, letterSpacing: 2, fontWeight: 700,
        textShadow: '0 0 6px ' + p.cyan + '66',
      }
    }, [ship.name]),
    htmlEl('span', {
      style: { fontSize: 9, color: p.inkDim, letterSpacing: 2 }
    }, ['TATOOINE · LOW ORBIT · ATM 142KM']),
  ]);
  var topRight = htmlEl('div', {
    style: { display: 'flex', gap: 10, alignItems: 'center' }
  }, [
    htmlEl('span', {
      style: { fontSize: 9, color: p.red, letterSpacing: 2 }
    }, ['● IFF HOSTILE']),
    htmlEl('span', {
      style: { fontSize: 9, color: p.inkDim, letterSpacing: 2 }
    }, ['03:42 GST']),
  ]);
  var topBar = htmlEl('div', {
    style: {
      height: 50, padding: '10px 20px',
      background: 'linear-gradient(180deg, ' + p.sky + ', ' + p.skyDeep + ')',
      borderBottom: '1px solid ' + p.cyan + '44',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      zIndex: 50, position: 'relative',
    }
  }, [topLeft, topRight]);

  // LEFT column — instruments
  var leftCol = htmlEl('div', {
    'data-cockpit-left': '1',
    style: {
      padding: '14px 14px',
      background: 'rgba(0,0,0,0.35)',
      borderRight: '1px solid ' + p.cyan + '33',
      overflowY: 'auto',
    }
  }, [buildShipInstruments(p, ship)]);

  // CENTER column — tactical radar + pose feed
  var feedRows = feed.map(function(entry) {
    return buildCockpitFeedRow(p, entry);
  }).filter(function(row) { return row !== null; });
  var centerCol = htmlEl('div', {
    'data-cockpit-center': '1',
    style: { display: 'flex', flexDirection: 'column', minWidth: 0 }
  }, [
    buildTacticalRadar(p),
    htmlEl('div', {
      'data-cockpit-feed': '1',
      style: {
        flex: 1, overflowY: 'auto', padding: '12px 18px',
        borderTop: '1px solid ' + p.cyan + '33',
      }
    }, feedRows),
  ]);

  // RIGHT column — target + hyperspace + crew
  var rightCol = htmlEl('div', {
    'data-cockpit-right': '1',
    style: {
      padding: '14px 14px',
      background: 'rgba(0,0,0,0.35)',
      borderLeft: '1px solid ' + p.cyan + '33',
      overflowY: 'auto',
      display: 'flex', flexDirection: 'column', gap: 14,
    }
  }, [
    buildTargetLockPanel(p, target),
    buildHyperspacePlot(p, hyperspaceDest, hyperspacePct, backupDrive),
    buildCrewPanel(p, crew),
  ]);

  // MAIN body grid
  var mainBody = htmlEl('div', {
    style: {
      position: 'absolute', top: 50, left: 0, right: 0, bottom: 110,
      display: 'grid', gridTemplateColumns: '260px 1fr 290px',
      gap: 0,
    }
  }, [leftCol, centerCol, rightCol]);

  // Outer wrapper + action strip
  return htmlEl('div', {
    'data-cockpit-view': '1',
    style: {
      width: width, height: height, position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + p.cyan + '33',
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      boxShadow: 'inset 0 0 60px ' + p.cyan + '08, 0 0 0 1px #000, 0 20px 50px rgba(0,0,0,0.7)',
    }
  }, [
    topBar,
    mainBody,
    buildCockpitActionStrip(p, hooks),
  ]);
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3Cockpit = {
  SCHEMA_VERSION: 1,

  init:                       init,

  // Top-level
  buildCockpitView:           buildCockpitView,

  // Section builders
  buildShipInstruments:       buildShipInstruments,
  buildTacticalRadar:         buildTacticalRadar,
  buildCockpitFeedRow:        buildCockpitFeedRow,
  buildTargetLockPanel:       buildTargetLockPanel,
  buildHyperspacePlot:        buildHyperspacePlot,
  buildCrewPanel:             buildCrewPanel,
  buildCockpitActionStrip:    buildCockpitActionStrip,

  // Helpers
  buildLabel:                 buildLabel,

  // Fixtures
  COCKPIT_SHIP_FIXTURE:       COCKPIT_SHIP_FIXTURE,
  COCKPIT_TARGET_FIXTURE:     COCKPIT_TARGET_FIXTURE,
  COCKPIT_FEED_FIXTURE:       COCKPIT_FEED_FIXTURE,
  COCKPIT_ACTION_DEFAULT:     COCKPIT_ACTION_DEFAULT,

  _internal: {
    _htmlEl: htmlEl,
    _svgEl:  svgEl,
    _fallbackActionButton: _fallbackActionButton,
  },
};

})();
