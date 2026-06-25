/* ============================================================================
   m3_combat_theater.js — Combat HUD chrome (right rail + bottom action strip).

   Drop 4.5 · Tier 1 #4 · ported from map_v3/combat-theater.jsx
   (May 27 2026 — post-bug-fix-sprint JSX in SW_MUSH_UIUX_Bugfix_26May26.zip).

   Bug-fix sprint corrections baked into the default phaseInfo:
     · B1   pass action chip (9th action in availableNextDeclaration)
     · H1   MAP labels rewritten ("declare 2nd → both at −1D")
     · H2   AIM cost label ("1 action · +1D next round")
     · H3   COVER label exposes graded tier ("already in 1/2 cover (+2D)")
     · H6/M5 stun-mode clarity (encoded in the feed sample for prototype use)
     · M4   InitiativeLadder values labeled "init N" with Perception subtitle

   See ui_bugfix_sprint_design_v1.md and design_review_may24_v1.md for the
   issue catalog.

   What this module ships:
     · M3CombatTheater.buildInitiativeLadder(p, order)         right-rail
     · M3CombatTheater.buildTargetCard(p, target)              right-rail
     · M3CombatTheater.buildRollPreview(p, preview)            right-rail
     · M3CombatTheater.buildShotContext(p, ctx)                right-rail
     · M3CombatTheater.buildYourStatus(p, status)              right-rail
     · M3CombatTheater.buildActionStrip(p, phaseInfo, hooks)   bottom-strip
       (internally dispatches to buildDeclarationBody /
        buildPosingBody / buildPassiveBody / buildPhaseBadge / buildPoseTimer)
     · M3CombatTheater.buildActionButton(p, action, hasMap)    declaration chip
     · M3CombatTheater.DEFAULT_PHASE_INFO                      sample fixture
     · M3CombatTheater.DEFAULT_INITIATIVE_ORDER                sample fixture

   What this module does NOT ship:
     · The full pose-stream-dominant layout (CombatDiceTheater wrapper).
       That's a larger UX decision; the existing client.html has its own
       combat-strip-at-top layout. This module provides the LEGO pieces
       so client.html can swap them in panel-by-panel without committing
       to the full theater layout up front.
     · FeedItem / PoseRow / CompactRoll / ExpandedRoll / SysResult /
       DamageBlock / WaitingBlock — these duplicate work already done by
       static/spa/m3_combat_inspector.js (Drop 4.4) and the existing pose
       log in client.html. The combat-theater JSX bundles them for the
       design canvas; production splits them across modules.
     · CSS keyframes (combatPulse / dieDrop). The JSX inlines them as
       `animation: combatPulse 1.4s ...` strings. Production already has
       a `combatPulse` keyframe in client.html's <style> block (used by
       the existing combat-strip phase pill) — the module's renderers
       set the same `animation:` style values; the keyframes are loaded
       once globally.
     · The bug-fix-sprint H4 Force panel — that's in sheet-v2.jsx, not
       combat-theater.jsx. See Drop 4.6 / sheet-v2 port.

   Dependency injection. Like m3_combat_inspector.js (Drop 4.4), this
   module accepts an init({ escapeHtml, getPalette }) call from client.html.
   Defaults are wired so the module is usable bare. Each renderer also
   accepts the palette `p` as a first argument for consistency with the
   JSX source signatures.

   Loading order in client.html: after m3_palettes.js (uses palette
   tokens), independent of m3_composition_engine.js (different surface).
   Placed alongside m3_combat_inspector.js in the SPA script-tag block.
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

// ─── htmlEl: same shape as m3_composition_engine.js (Drop 4.1e) ──────
// JSX → vanilla DOM. style objects become CSS-in-JS via applyStyle.
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
      } else if (key === 'onKeydown' && typeof val === 'function') {
        el.addEventListener('keydown', val);
      } else if (key.indexOf('on') === 0 && typeof val === 'function') {
        // Generic event handler: onMouseEnter → 'mouseenter' etc.
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
  // SVG attributes use kebab-case; React/JSX uses camelCase. Convert,
  // but preserve viewBox and a handful of genuinely-camelCase SVG attrs.
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
    // CSS property names: keep camelCase (DOM CSSStyleDeclaration accepts both).
    el.style[k] = (typeof v === 'number' && !_isUnitlessCss(k)) ? (v + 'px') : v;
  }
}

function _isUnitlessCss(k) {
  // Subset of React's well-known unitless CSS properties.
  return (k === 'opacity' || k === 'zIndex' || k === 'fontWeight' ||
          k === 'flex' || k === 'flexGrow' || k === 'flexShrink' ||
          k === 'lineHeight' || k === 'order');
}

// ─── Sample fixtures (used as defaults; production passes real data) ─
// Lifted verbatim from the bug-fix-sprint JSX so the prototype-fidelity
// tests can assert on the same values that drive the design canvas.
var DEFAULT_PHASE_INFO = {
  phase: 'POSING',  // 'INITIATIVE' | 'DECLARATION' | 'POSING' | 'RESOLUTION'
  round: 3,
  poseDeadline: 134,
  poseTotal: 180,
  yourActions: [
    { id: 'a1', label: 'AIM',            map: 0, status: 'done', icon: '⦿' },
    { id: 'a2', label: 'ATTACK · B1 #1', map: 0, status: 'hit',  icon: '✤', result: 'HIT 18' },
  ],
  // B1 / H1 / H2 / H3 (bug-fix sprint, May 26 2026): pass added as 9th action;
  // MAP labels disambiguated; AIM costed as the action it is; COVER exposes
  // graded tier. See web_client_vision_and_protocol_v1_3 §3.15.
  availableNextDeclaration: [
    { id: 'attack', label: 'ATTACK',   icon: '✤', enabled: true,  cost: '−0D' },
    { id: 'dodge',  label: 'DODGE',    icon: '⚝', enabled: true,  cost: 'declare 2nd → both at −1D' },
    { id: 'aim',    label: 'AIM',      icon: '⦿', enabled: true,  cost: '1 action · +1D next round' },
    { id: 'cover',  label: 'COVER',    icon: '◥', enabled: false, cost: 'already in 1/2 cover (+2D)' },
    { id: 'move',   label: 'MOVE',     icon: '→', enabled: true,  cost: 'declare 2nd → both at −1D' },
    { id: 'reload', label: 'RELOAD',   icon: '↻', enabled: false, cost: 'mag at 49/50' },
    { id: 'fp',     label: 'SPEND FP', icon: '✮', enabled: true,  cost: '×2 ALL DICE' },
    { id: 'flee',   label: 'FLEE',     icon: '⤥', enabled: true,  cost: 'end combat' },
    { id: 'pass',   label: 'PASS',     icon: '·', enabled: true,  cost: 'hold action this round' },
  ],
};

var DEFAULT_INITIATIVE_ORDER = [
  { init: 14, name: '★ TEY VOSS',     side: 'self',    action: 'AIM → FIRE',    done: true },
  { init: 11, name: 'MAREK TAN',      side: 'ally',    action: 'Cover → fire',  done: true },
  { init: 9,  name: 'B1 #1',          side: 'hostile', action: 'DISABLED',      struck: true },
  { init: 8,  name: 'B1 #2',          side: 'hostile', action: 'Shoot Marek',   current: true },
];

// ════════════════════════════════════════════════════════════════════
// INITIATIVE LADDER — right rail (M4 bug-fix sprint applied)
// ════════════════════════════════════════════════════════════════════
function buildInitiativeLadder(p, order) {
  order = order || DEFAULT_INITIATIVE_ORDER;
  var header = htmlEl('div', {
    style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600, marginBottom: 6 }
  }, ['▮▮ INITIATIVE · ROUND 3']);

  // M4: Perception-roll subtitle so non-WEG players read the values right.
  var subtitle = htmlEl('div', {
    style: { fontSize: 8, letterSpacing: 1.5, color: p.inkDim, marginBottom: 6 }
  }, ['Perception roll · highest acts first']);

  var rows = order.map(function(o) {
    var c = (o.side === 'self')  ? p.green
          : (o.side === 'ally')  ? p.cyan
          :                        p.red;
    var children = [];
    children.push(htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 11, color: c,
        fontWeight: 700, textAlign: 'center', letterSpacing: 0.5,
      }
    }, ['init ' + o.init]));
    // UX Drop 2 (combat HUD): cover label on the ladder row. `o.cover` is
    // the COVER_NAMES short label ("1/2 COVER") the live wiring passes when
    // the combatant is behind cover; absent ⇒ no label (zero DOM), matching
    // the buildConditionChips returns-null-when-empty convention.
    var nameChildren = [
      htmlEl('div', {
        style: {
          fontSize: 10.5, color: c, letterSpacing: 0.5,
          textDecoration: o.struck ? 'line-through' : 'none',
        }
      }, [o.name]),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim }
      }, [o.action || '']),
    ];
    if (o.cover) {
      nameChildren.push(htmlEl('div', {
        className: 'init-cover',
        style: { fontSize: 8, color: p.cyan, letterSpacing: 1, marginTop: 1 }
      }, ['◣ ' + o.cover]));
    }
    children.push(htmlEl('div', null, nameChildren));
    if (o.current) {
      children.push(htmlEl('span', {
        style: {
          fontSize: 7, letterSpacing: 1.5, color: c, fontWeight: 600,
          padding: '1px 4px', border: '1px solid ' + c,
          animation: 'combatPulse 1.4s ease-in-out infinite',
        }
      }, ['NOW']));
    } else if (o.done && !o.struck) {
      children.push(htmlEl('span', {
        style: { fontSize: 8, color: p.inkDim, letterSpacing: 1 }
      }, ['✓']));
    } else if (o.struck) {
      children.push(htmlEl('span', {
        style: { fontSize: 8, color: p.red, letterSpacing: 1.5 }
      }, ['OUT']));
    } else {
      children.push(htmlEl('span', null, ['']));  // spacer placeholder
    }

    return htmlEl('div', {
      // M4: tooltip explains the Perception-roll semantics.
      title: 'Perception roll ' + o.init + ' — determines turn order this combat',
      style: {
        display: 'grid', gridTemplateColumns: '52px 1fr auto', gap: 6,
        alignItems: 'center',
        padding: '5px 7px',
        background: o.current ? (c + '22') : 'rgba(0,0,0,0.3)',
        borderLeft: '2px solid ' + c,
        opacity: o.struck ? 0.5 : 1,
      },
    }, children);
  });

  var rowsWrap = htmlEl('div', {
    style: { display: 'flex', flexDirection: 'column', gap: 3 }
  }, rows);

  return htmlEl('div', null, [header, subtitle, rowsWrap]);
}

// ════════════════════════════════════════════════════════════════════
// TARGET CARD — right rail
// ════════════════════════════════════════════════════════════════════
function buildTargetCard(p, target) {
  target = target || {
    name: 'B1 BATTLE DROID #1',
    sub:  'CIS · Hostile · Infantry',
    status: 'DISABLED · WND 1/2',
    woundProgress: [true, false],  // 1/2 wounded
  };

  // SVG B1-droid silhouette — kept simple, palette-driven.
  var silhouette = svgEl('svg', {
    viewBox: '0 0 60 100', width: 64, height: 100
  }, [
    svgEl('circle', { cx: 30, cy: 14, r: 8, fill: 'none',
                      stroke: p.red, strokeWidth: 1.4 }),
    svgEl('line', { x1: 26, y1: 6, x2: 20, y2: 2, stroke: p.red, strokeWidth: 0.8 }),
    svgEl('line', { x1: 34, y1: 6, x2: 40, y2: 2, stroke: p.red, strokeWidth: 0.8 }),
    svgEl('path', { d: 'M 22 22 L 38 22 L 36 50 L 24 50 Z',
                    fill: 'none', stroke: p.red, strokeWidth: 1.4 }),
    svgEl('line', { x1: 22, y1: 26, x2: 12, y2: 48, stroke: p.red, strokeWidth: 1.2 }),
    svgEl('line', { x1: 38, y1: 26, x2: 48, y2: 48, stroke: p.red, strokeWidth: 1.2 }),
    svgEl('line', { x1: 26, y1: 50, x2: 22, y2: 90, stroke: p.red, strokeWidth: 1.2 }),
    svgEl('line', { x1: 34, y1: 50, x2: 38, y2: 90, stroke: p.red, strokeWidth: 1.2 }),
    svgEl('circle', { cx: 30, cy: 34, r: 3, fill: p.red, opacity: 0.7,
                      style: { filter: 'drop-shadow(0 0 4px ' + p.red + ')' } }),
  ]);

  var pips = (target.woundProgress || []).map(function(on) {
    return htmlEl('div', { style: {
      flex: 1, height: 5,
      background: on ? p.red : 'rgba(0,0,0,0.4)',
      boxShadow: on ? '0 0 4px ' + p.red : 'none',
      border: on ? 'none' : ('1px solid ' + p.inkFaint),
    }});
  });

  var info = htmlEl('div', null, [
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 14, fontWeight: 700,
        color: p.red, letterSpacing: 2, lineHeight: 1.2,
      }
    }, [target.name]),
    htmlEl('div', {
      style: { fontSize: 9, color: p.inkDim, letterSpacing: 1, marginTop: 2 }
    }, [target.sub]),
    htmlEl('div', {
      style: {
        marginTop: 8, padding: '3px 6px',
        background: p.red + '33',
        border: '1px solid ' + p.red, color: p.red,
        fontSize: 9, letterSpacing: 2, fontWeight: 600, textAlign: 'center',
      }
    }, [target.status]),
    htmlEl('div', { style: { display: 'flex', gap: 3, marginTop: 4 } }, pips),
  ]);

  var header = htmlEl('div', {
    style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600, marginBottom: 6 }
  }, ['▮▮ ACTIVE TARGET']);

  var body = htmlEl('div', {
    style: {
      padding: 10,
      background: 'rgba(0,0,0,0.35)',
      border: '1px solid ' + p.red,
      display: 'grid', gridTemplateColumns: '70px 1fr', gap: 10,
    }
  }, [silhouette, info]);

  return htmlEl('div', null, [header, body]);
}

// ════════════════════════════════════════════════════════════════════
// ROLL PREVIEW — right rail
// ════════════════════════════════════════════════════════════════════
function buildRollPreview(p, preview) {
  preview = preview || {
    targetName: 'B1 #2',
    rangeBand:  'SHORT',
    components: [
      { label: 'Blaster (spec)', code: '+6D+1', positive: true  },
      { label: 'Aim held',       code: '+1D',   positive: true  },
      { label: 'Wounded',        code: '−1D',   positive: false },
    ],
    effPool:    '6D+1',
    avgRoll:    '~22',
    diffNum:    11,
    expected:   'HIT · ~95%',
    diffStack:  'DIFF stack: Easy 10 +Med 2 +Cov 3 −2 aim −2 spec',
  };

  var header = htmlEl('div', {
    style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600, marginBottom: 6 }
  }, ['▮▮ NEXT ROLL PREVIEW']);

  var ifLine = htmlEl('div', {
    style: { fontSize: 9, color: p.inkDim, marginBottom: 4, letterSpacing: 1 }
  }, [
    'IF YOU ',
    htmlEl('span', { style: { color: p.red } }, ['ATTACK ' + preview.targetName]),
    ' AT ',
    htmlEl('span', { style: { color: p.amber } }, [preview.rangeBand]),
  ]);

  var componentRows = preview.components.map(function(c) {
    return htmlEl('div', {
      style: { display: 'flex', justifyContent: 'space-between' }
    }, [
      htmlEl('span', { style: { color: p.ink } }, [c.label]),
      htmlEl('span', {
        style: { color: c.positive ? p.green : p.red, fontWeight: 600 }
      }, [c.code]),
    ]);
  });

  var effLine = htmlEl('div', {
    style: {
      display: 'flex', justifyContent: 'space-between',
      marginTop: 4, paddingTop: 3, borderTop: '1px dashed ' + p.amber,
    }
  }, [
    htmlEl('span', {
      style: { color: p.amber, fontWeight: 600, letterSpacing: 1 }
    }, ['EFF POOL']),
    htmlEl('span', {
      style: { fontFamily: "'Space Grotesk'", color: p.inkBright, fontWeight: 700 }
    }, [preview.effPool]),
  ]);

  var poolBlock = htmlEl('div', {
    style: { fontSize: 10, lineHeight: 1.5 }
  }, componentRows.concat([effLine]));

  var expectedBlock = htmlEl('div', {
    style: {
      marginTop: 8, padding: '6px 8px',
      background: p.green + '11', border: '1px solid ' + p.green + '66',
    }
  }, [
    htmlEl('div', {
      style: { display: 'flex', justifyContent: 'space-between', fontSize: 10 }
    }, [
      htmlEl('span', { style: { color: p.inkDim } }, ['AVG ROLL']),
      htmlEl('span', {
        style: { fontFamily: "'Space Grotesk'", color: p.inkBright, fontWeight: 700 }
      }, [preview.avgRoll]),
    ]),
    htmlEl('div', {
      style: { display: 'flex', justifyContent: 'space-between', fontSize: 10 }
    }, [
      htmlEl('span', { style: { color: p.inkDim } }, ['vs DIFF']),
      htmlEl('span', {
        style: { fontFamily: "'Space Grotesk'", color: p.inkBright, fontWeight: 700 }
      }, [String(preview.diffNum)]),
    ]),
    htmlEl('div', {
      style: {
        marginTop: 4, paddingTop: 3,
        borderTop: '1px dashed ' + p.green,
        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
      }
    }, [
      htmlEl('span', {
        style: { fontSize: 9, color: p.green, letterSpacing: 1.5, fontWeight: 700 }
      }, ['EXPECTED']),
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 14, color: p.green, fontWeight: 700,
          textShadow: '0 0 4px ' + p.green + '55',
        }
      }, [preview.expected]),
    ]),
  ]);

  var diffStack = htmlEl('div', {
    style: { marginTop: 6, fontSize: 9, color: p.inkDim, letterSpacing: 0.5, lineHeight: 1.4 }
  }, [preview.diffStack]);

  var body = htmlEl('div', {
    style: { padding: 8, background: 'rgba(0,0,0,0.45)', border: '1px solid ' + p.amber + '66' }
  }, [ifLine, poolBlock, expectedBlock, diffStack]);

  return htmlEl('div', null, [header, body]);
}

// ════════════════════════════════════════════════════════════════════
// SHOT CONTEXT — right rail
// ════════════════════════════════════════════════════════════════════
function buildShotContext(p, ctx) {
  ctx = ctx || [
    ['RANGE',  'Short · 5m'],
    ['BAND',   '+0'],
    ['COVER',  'Medium'],
    ['COVER+', '+3'],
    ['LOS',    'Clear'],
    ['LIGHT',  'Dim · n/a'],
  ];

  var header = htmlEl('div', {
    style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600, marginBottom: 6 }
  }, ['▮▮ SHOT CONTEXT']);

  var grid = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }
  }, ctx.map(function(pair) {
    return htmlEl('div', {
      style: { padding: '4px 6px', background: 'rgba(0,0,0,0.3)',
               border: '1px solid ' + p.inkFaint }
    }, [
      htmlEl('div', {
        style: { fontSize: 8, color: p.inkDim, letterSpacing: 1.5 }
      }, [pair[0]]),
      htmlEl('div', {
        style: { fontSize: 10, color: p.inkBright, marginTop: 1 }
      }, [pair[1]]),
    ]);
  }));

  return htmlEl('div', null, [header, grid]);
}

// ════════════════════════════════════════════════════════════════════
// YOUR STATUS — right rail
// ════════════════════════════════════════════════════════════════════
function buildYourStatus(p, status) {
  status = status || {
    name:    'TEY VOSS · LIVE',
    wound:   'WOUNDED',
    woundPen: '−1D',
    woundProgress: '1/5',
    pips:    [true, false, false, false, false],
    chips:   ['IN COVER', 'AIM USED', 'FP 2'],
  };

  // UX Drop 2 (combat HUD wound track): the live wiring passes a
  // severity-keyed color (from client.html's woundColor()) so the track
  // grades green→amber→red as wounds stack, instead of a flat red. When
  // absent (the prototype default fixture / existing tests), fall back to
  // the original red-lit / green-label vocabulary so nothing regresses.
  var litColor   = status.woundColor || p.red;     // lit pip + wound label
  var labelColor = status.woundColor || p.green;   // wound-level word

  var header = htmlEl('div', {
    style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600, marginBottom: 6 }
  }, ['▮▮ ' + status.name]);

  var topLine = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 8, alignItems: 'baseline' }
  }, [
    htmlEl('span', {
      style: { fontFamily: "'Space Grotesk'", fontSize: 12, fontWeight: 600, color: labelColor }
    }, [status.wound]),
    htmlEl('span', {
      style: { fontSize: 9, color: p.red, letterSpacing: 1.5 }
    }, [status.woundPen]),
    htmlEl('span', {
      style: { fontSize: 9, color: p.inkDim }
    }, [status.woundProgress]),
  ]);

  var pips = htmlEl('div', {
    style: { display: 'flex', gap: 3, marginTop: 4 }
  }, status.pips.map(function(on) {
    return htmlEl('div', { style: {
      flex: 1, height: 5,
      background: on ? litColor : 'rgba(0,0,0,0.4)',
      border: '1px solid ' + (on ? litColor : p.inkFaint),
      boxShadow: on ? '0 0 3px ' + litColor : 'none',
    }});
  }));

  var chipsRow = htmlEl('div', {
    style: { marginTop: 6, display: 'flex', gap: 4, flexWrap: 'wrap' }
  }, status.chips.map(function(s) {
    return htmlEl('span', {
      style: {
        fontSize: 8, letterSpacing: 1.5, color: p.amber,
        padding: '1px 4px', border: '1px solid ' + p.amber + '66',
        background: p.amber + '11',
      }
    }, [s]);
  }));

  var body = htmlEl('div', {
    style: { padding: '6px 10px', background: 'rgba(0,0,0,0.35)',
             border: '1px solid ' + p.green + '66' }
  }, [topLine, pips, chipsRow]);

  return htmlEl('div', null, [header, body]);
}

// ════════════════════════════════════════════════════════════════════
// PHASE BADGE — bottom action strip header
// ════════════════════════════════════════════════════════════════════
function buildPhaseBadge(p, phase) {
  var C = ({
    INITIATIVE:  { c: p.cyan,  label: 'INITIATIVE' },
    DECLARATION: { c: p.amber, label: 'DECLARATION' },
    RESOLUTION:  { c: p.red,   label: 'RESOLUTION' },
    POSING:      { c: p.green, label: 'POSING' },
  })[phase] || { c: p.inkDim, label: phase || 'UNKNOWN' };

  return htmlEl('div', {
    style: {
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '4px 10px',
      background: C.c + '22',
      border: '1px solid ' + C.c,
      boxShadow: '0 0 8px ' + C.c + '44',
    }
  }, [
    htmlEl('div', {
      style: {
        width: 6, height: 6, borderRadius: '50%', background: C.c,
        boxShadow: '0 0 4px ' + C.c,
        animation: 'combatPulse 1.4s ease-in-out infinite',
      }
    }),
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk', sans-serif",
        fontSize: 11, color: C.c, letterSpacing: 3, fontWeight: 700,
      }
    }, ['PHASE · ' + C.label]),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// POSE TIMER — circular gauge with seconds-left readout
// ════════════════════════════════════════════════════════════════════
function buildPoseTimer(p, secondsLeft, total) {
  var lowTime = secondsLeft < 30;
  var c = lowTime ? p.red : p.green;
  var ratio = (total > 0) ? (secondsLeft / total) : 0;
  var mins = Math.floor(secondsLeft / 60);
  var secs = secondsLeft % 60;
  var circ = 2 * Math.PI * 13;

  var gauge = svgEl('svg', { width: 32, height: 32, viewBox: '0 0 32 32' }, [
    svgEl('circle', { cx: 16, cy: 16, r: 13, fill: 'none',
                      stroke: p.inkFaint, strokeWidth: 2 }),
    svgEl('circle', { cx: 16, cy: 16, r: 13, fill: 'none',
                      stroke: c, strokeWidth: 2,
                      strokeDasharray: String(circ),
                      strokeDashoffset: String(circ * (1 - ratio)),
                      transform: 'rotate(-90 16 16)',
                      strokeLinecap: 'butt',
                      style: { filter: 'drop-shadow(0 0 4px ' + c + ')' } }),
    svgEl('text', { x: 16, y: 20, fontSize: 9, fill: c,
                    textAnchor: 'middle',
                    fontFamily: 'IBM Plex Mono', fontWeight: 700 },
          [String(mins)]),
  ]);

  var readout = htmlEl('div', null, [
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 18, fontWeight: 700, color: c,
        letterSpacing: 1, lineHeight: 1,
        textShadow: lowTime ? '0 0 6px ' + c : 'none',
        animation: lowTime ? 'combatPulse 0.8s ease-in-out infinite' : 'none',
      }
    }, [mins + ':' + (secs < 10 ? '0' + secs : String(secs))]),
    htmlEl('div', {
      style: { fontSize: 8, color: p.inkDim, letterSpacing: 1.5 }
    }, ['POSE WINDOW · 3 MIN']),
  ]);

  return htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 10 }
  }, [gauge, readout]);
}

// ════════════════════════════════════════════════════════════════════
// ACTION BUTTON — declaration-phase action chip
// (B1: pass is one of these; H1/H2/H3 cost labels are passed in via
//  action.cost from the bug-fix-sprint phaseInfo data above.)
// ════════════════════════════════════════════════════════════════════
function buildActionButton(p, action, hasMap, onClick) {
  var showsMapPenalty = !!(hasMap && action.id !== 'aim' && action.id !== 'fp');

  var children = [];
  children.push(htmlEl('span', { style: { fontSize: 12 } }, [action.icon]));
  children.push(htmlEl('span', null, [action.label]));
  if (showsMapPenalty) {
    children.push(htmlEl('span', {
      style: {
        fontSize: 8, color: p.red, marginLeft: 4,
        padding: '0 4px', border: '1px solid ' + p.red + '66',
      }
    }, ['−1D']));
  }
  if (!action.enabled) {
    children.push(htmlEl('span', {
      style: {
        position: 'absolute', top: -5, right: -3,
        fontSize: 7, color: p.inkDim, letterSpacing: 1,
        padding: '1px 3px', background: p.skyDeep,
        border: '1px solid ' + p.inkFaint,
      }
    }, [String(action.cost).toUpperCase()]));
  }

  var props = {
    title: action.cost,
    'data-action-id': action.id,
    style: {
      padding: '6px 10px',
      background: action.enabled ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.6)',
      border: '1px solid ' + (action.enabled ? p.amber : p.inkFaint),
      color: action.enabled ? p.amber : p.inkFaint,
      opacity: action.enabled ? 1 : 0.5,
      fontSize: 10, letterSpacing: 1.5,
      cursor: action.enabled ? 'pointer' : 'not-allowed',
      display: 'flex', alignItems: 'center', gap: 4,
      position: 'relative',
    },
  };
  if (action.enabled && typeof onClick === 'function') {
    props.onClick = function() { onClick(action); };
  }
  return htmlEl('div', props, children);
}

// ════════════════════════════════════════════════════════════════════
// DECLARATION BODY — list of declared + available action chips
// ════════════════════════════════════════════════════════════════════
function buildDeclarationBody(p, phaseInfo, hooks) {
  hooks = hooks || {};
  var onActionClick = hooks.onActionClick || null;
  var onSubmitDeclaration = hooks.onSubmitDeclaration || null;

  // Mock declared state — production passes phaseInfo.declared.
  var declared = (phaseInfo && phaseInfo.declared) || [
    { id: 'attack', label: 'ATTACK B1 #2', icon: '⚔', mapDie: 0 },
  ];
  var adding = (phaseInfo && phaseInfo.adding !== undefined) ? phaseInfo.adding : true;

  var declaredChips = declared.map(function(d) {
    return htmlEl('span', {
      style: {
        fontSize: 10, color: p.amber, letterSpacing: 1.5,
        padding: '2px 6px', border: '1px solid ' + p.amber,
        background: p.amber + '22',
      }
    }, [d.icon + ' ' + d.label]);
  });
  var declaredBlock = htmlEl('div', {
    style: {
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '4px 10px', background: 'rgba(0,0,0,0.3)',
      border: '1px solid ' + p.inkFaint, minWidth: 180,
    }
  }, [htmlEl('span', {
    style: { fontSize: 8, color: p.inkDim, letterSpacing: 2 }
  }, ['DECLARED:'])].concat(declaredChips));

  var hasMap = declared.length > 0;
  var actionButtons = (phaseInfo.availableNextDeclaration || []).map(function(a) {
    return buildActionButton(p, a, hasMap, onActionClick);
  });
  var actionRow = htmlEl('div', {
    style: { display: 'flex', gap: 4, flex: 1, flexWrap: 'wrap', alignItems: 'center' }
  }, actionButtons);

  var rightSide = [];
  if (adding && declared.length > 0) {
    rightSide.push(htmlEl('div', {
      style: {
        fontSize: 9, color: p.red, letterSpacing: 1.5,
        padding: '2px 6px', border: '1px solid ' + p.red,
        background: p.red + '22',
      }
    }, ['2 actions · MAP −1D each']));
  }
  var submitProps = {
    style: {
      padding: '6px 14px',
      background: p.amber, color: p.skyDeep,
      border: '1px solid ' + p.amber, fontWeight: 700, letterSpacing: 2,
      fontSize: 11, cursor: 'pointer',
      boxShadow: '0 0 10px ' + p.amber + '66',
    },
  };
  if (typeof onSubmitDeclaration === 'function') {
    submitProps.onClick = onSubmitDeclaration;
  }
  rightSide.push(htmlEl('button', submitProps, ['SUBMIT DECLARATION ↵']));
  var rightBlock = htmlEl('div', {
    style: { display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }
  }, rightSide);

  return htmlEl('div', {
    style: { display: 'flex', gap: 10, alignItems: 'stretch' }
  }, [declaredBlock, actionRow, rightBlock]);
}

// ════════════════════════════════════════════════════════════════════
// POSING BODY — pose input + B1 ACCEPT AUTO-POSE button (Alt+P)
// ════════════════════════════════════════════════════════════════════
function buildPosingBody(p, phaseInfo, hooks) {
  hooks = hooks || {};
  var onPassPose = hooks.onPassPose || null;
  var autoPoseText = (phaseInfo && phaseInfo.autoPoseText) ||
    "rises slow from cover, scans the bay for the second droid, blaster still smoking. The lead droid is twitching in the dust at her feet, sparks fading._";

  // Pose input — dominant, green outline.
  var poseInput = htmlEl('div', {
    style: {
      flex: 1, height: 56, padding: '6px 12px',
      background: p.skyDeep,
      border: '1px solid ' + p.green,
      boxShadow: 'inset 0 0 12px ' + p.green + '22',
      display: 'flex', alignItems: 'flex-start', gap: 8,
      fontFamily: "'IBM Plex Mono', monospace",
    }
  }, [
    htmlEl('span', { style: { color: p.green, fontSize: 13, paddingTop: 2 } }, [':']),
    htmlEl('span', {
      style: { color: p.inkBright, fontSize: 13, opacity: 0.9, lineHeight: 1.5, flex: 1 }
    }, [autoPoseText]),
  ]);

  // B1 — Accept auto-pose button: equal visual weight to the cpose input.
  var acceptBtnProps = {
    'data-test':  'accept-auto-pose-btn',
    'data-action': 'pass',
    title: 'Sends `pass` — uses the engine-generated default pose above. (Alt+P)',
    style: {
      height: 56, padding: '0 14px',
      background: p.skyDeep,
      color: p.green,
      border: '1px solid ' + p.green,
      boxShadow: 'inset 0 0 12px ' + p.green + '22, 0 0 8px ' + p.green + '33',
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 11, fontWeight: 700, letterSpacing: 2,
      cursor: 'pointer',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 2,
    },
  };
  if (typeof onPassPose === 'function') {
    acceptBtnProps.onClick = onPassPose;
  }
  var acceptBtn = htmlEl('button', acceptBtnProps, [
    htmlEl('span', null, ['▸ ACCEPT AUTO-POSE']),
    htmlEl('span', {
      style: { fontSize: 8, letterSpacing: 1.5, color: p.inkDim, fontWeight: 400 }
    }, ['sends `pass` · Alt+P']),
  ]);

  // "Your actions this round" — small panel on the right.
  var yourActions = (phaseInfo && phaseInfo.yourActions) || [];
  var actionRows = yourActions.map(function(a) {
    var statusColor = (a.status === 'hit') ? p.green : p.inkBright;
    var iconColor = (a.status === 'hit') ? p.green : p.amber;
    var children = [
      htmlEl('span', { style: { color: iconColor } }, [a.icon]),
      htmlEl('span', { style: { flex: 1 } }, [a.label]),
    ];
    if (a.result) {
      children.push(htmlEl('span', {
        style: { color: p.green, fontSize: 9, fontWeight: 600 }
      }, [a.result]));
    }
    return htmlEl('div', {
      style: {
        fontSize: 10, color: statusColor,
        display: 'flex', alignItems: 'center', gap: 5,
      }
    }, children);
  });
  var yourActionsHeader = htmlEl('div', {
    style: { fontSize: 8, letterSpacing: 2, color: p.inkDim, marginBottom: 1 }
  }, ['YOUR ACTIONS THIS ROUND']);
  var yourActionsBlock = htmlEl('div', {
    style: {
      width: 220, height: 56,
      padding: '4px 10px',
      background: 'rgba(0,0,0,0.35)',
      border: '1px solid ' + p.inkFaint,
      display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 2,
    }
  }, [yourActionsHeader].concat(actionRows));

  return htmlEl('div', {
    style: { display: 'flex', alignItems: 'flex-start', gap: 12 }
  }, [poseInput, acceptBtn, yourActionsBlock]);
}

// ════════════════════════════════════════════════════════════════════
// PASSIVE BODY — resolution / initiative phases (no input)
// ════════════════════════════════════════════════════════════════════
function buildPassiveBody(p, phase) {
  var label = (phase === 'RESOLUTION') ? 'RESOLVING DICE…' : 'ROLLING INITIATIVE…';
  var diceIndicator = htmlEl('div', {
    style: {
      width: 24, height: 24, position: 'relative',
      animation: 'dieDrop 800ms ease-in-out infinite alternate',
    }
  }, [
    svgEl('svg', { viewBox: '0 0 24 24', width: 24, height: 24 }, [
      svgEl('rect', { x: 3, y: 3, width: 18, height: 18, rx: 3,
                      fill: 'none', stroke: p.red, strokeWidth: 1.5 }),
      svgEl('circle', { cx: 8, cy: 8, r: 1.5, fill: p.red }),
      svgEl('circle', { cx: 16, cy: 16, r: 1.5, fill: p.red }),
    ]),
  ]);

  return htmlEl('div', {
    style: {
      height: 56, padding: '0 16px',
      background: 'rgba(0,0,0,0.4)',
      border: '1px dashed ' + p.inkFaint,
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14,
    }
  }, [
    diceIndicator,
    htmlEl('span', {
      style: { fontFamily: "'IBM Plex Mono'", fontSize: 11, letterSpacing: 3, color: p.red }
    }, [label]),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// ACTION STRIP — full bottom strip orchestrator
// Dispatches on phaseInfo.phase to the appropriate body builder.
// ════════════════════════════════════════════════════════════════════
function buildActionStrip(p, phaseInfo, hooks) {
  phaseInfo = phaseInfo || DEFAULT_PHASE_INFO;
  hooks = hooks || {};
  var ph = phaseInfo.phase;

  var topLine = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 14 }
  }, _buildActionStripTopLine(p, phaseInfo));

  var body;
  if (ph === 'POSING') {
    body = buildPosingBody(p, phaseInfo, hooks);
  } else if (ph === 'DECLARATION') {
    body = buildDeclarationBody(p, phaseInfo, hooks);
  } else {
    // RESOLUTION or INITIATIVE — passive
    body = buildPassiveBody(p, ph);
  }

  var borderColor = (ph === 'POSING') ? p.green
                  : (ph === 'DECLARATION') ? p.amber
                  : p.red;

  return htmlEl('div', {
    'data-phase': ph,
    style: {
      position: 'absolute', bottom: 0, left: 0, right: 0, height: 110,
      borderTop: '2px solid ' + borderColor,
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', ' + p.sky + ')',
      padding: '10px 16px',
      display: 'flex', flexDirection: 'column', gap: 8,
      zIndex: 60,
    }
  }, [topLine, body]);
}

function _buildActionStripTopLine(p, phaseInfo) {
  var ph = phaseInfo.phase;
  var isPosing      = (ph === 'POSING');
  var isDeclaration = (ph === 'DECLARATION');
  var isResolution  = (ph === 'RESOLUTION');
  var isInitiative  = (ph === 'INITIATIVE');

  var badge = buildPhaseBadge(p, ph);

  var helpChildren = [];
  if (isPosing) {
    helpChildren.push(htmlEl('span', { style: { color: p.green } }, ['Your pose required.']));
    helpChildren.push(' Type below — ');
    helpChildren.push(htmlEl('code', { style: { color: p.amber } }, ['pose']));
    helpChildren.push(' for narrative, ');
    helpChildren.push(htmlEl('code', { style: { color: p.amber } }, [':']));
    helpChildren.push(' shorthand. Will broadcast to room when submitted.');
  } else if (isDeclaration) {
    helpChildren.push('Pick your action(s). Second action in the same round incurs ');
    helpChildren.push(htmlEl('span', { style: { color: p.red } }, ['MAP −1D']));
    helpChildren.push(' to both rolls.');
  } else if (isResolution) {
    helpChildren.push('Resolving dice for all declared actions. No input accepted.');
  } else if (isInitiative) {
    helpChildren.push('Rolling initiative for all combatants. Hold.');
  }
  var helpLine = htmlEl('div', {
    style: { fontSize: 10, color: p.inkDim, letterSpacing: 1.5, flex: 1 }
  }, helpChildren);

  var children = [badge, helpLine];
  if (isPosing) {
    children.push(buildPoseTimer(p, phaseInfo.poseDeadline, phaseInfo.poseTotal));
  }
  return children;
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3CombatTheater = {
  SCHEMA_VERSION: 1,

  // Wiring
  init: init,

  // Right-rail builders
  buildInitiativeLadder: buildInitiativeLadder,
  buildTargetCard:       buildTargetCard,
  buildRollPreview:      buildRollPreview,
  buildShotContext:      buildShotContext,
  buildYourStatus:       buildYourStatus,

  // Bottom action strip
  buildActionStrip:      buildActionStrip,
  buildPhaseBadge:       buildPhaseBadge,
  buildPoseTimer:        buildPoseTimer,
  buildDeclarationBody:  buildDeclarationBody,
  buildPosingBody:       buildPosingBody,
  buildPassiveBody:      buildPassiveBody,
  buildActionButton:     buildActionButton,

  // Defaults / fixtures
  DEFAULT_PHASE_INFO:         DEFAULT_PHASE_INFO,
  DEFAULT_INITIATIVE_ORDER:   DEFAULT_INITIATIVE_ORDER,

  // Test reach — helpers (mostly for harness use)
  _internal: {
    _htmlEl: htmlEl,
    _svgEl:  svgEl,
  },
};

})();
