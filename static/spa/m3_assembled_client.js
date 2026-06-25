/* ============================================================================
   m3_assembled_client.js — Assembled Field Kit shell (integration target).

   Drop 4.12b · Tier 1 #4 · ported from map_v3/assembled-client.jsx
   (701 JSX LOC) in SW_MUSH_UIUX_Bugfix_26May26.zip (May 27 2026).

   This is the "everything plugged in" canonical reference for what the
   production client looks like once all m3_* modules ship together.
   It's the integration target — not a render-once snapshot but a
   stateful composition that exercises every module's public surface.

   Layout:
     [HOLONET TICKER]                                — top, 26px
     [STATUS BAR]                                     — top, 30px
     [LEFT: identity/HUD] [CENTER: feed+comms] [RIGHT: cartridge]
     [COMMAND STRIP]                                  — bottom, 84px

   Popup overlays (one at a time):
     · HOLOCRON      — M3Holocron.buildHolocronModal
     · +SHEET        — M3Sheet.buildCharacterSheetModal / createCharacterSheetModal
                       (added by Drop 4.12a)
     · HOLONET       — M3Holonet.buildHolonetBrowserModal
     · MAP           — local MapPopupModal wrapper; renders M3MapNavigator inside

   What this module ships:
     · M3AssembledClient.create(p, hooks?) → handle
            instantiate. Returns { element, getState, openPopup, closePopup,
                                   setCartridge, destroy }
     · M3AssembledClient.buildAssembledClient(p, hooks?)
            convenience — wraps create() and returns element directly for
            test/snapshot use. The popup buttons fire hooks.onOpenPopup
            and hooks.onSetCartridge instead of managing state internally.
     · M3AssembledClient.buildLeftHUD(p, character, hooks?)
     · M3AssembledClient.buildCenterFeed(p, hooks?)
     · M3AssembledClient.buildCommsTabs(p)
     · M3AssembledClient.buildRightCartridge(p, cartridge, hooks?)
     · M3AssembledClient.buildMiniMap(p, hooks?)
     · M3AssembledClient.buildMiniInv(p)
     · M3AssembledClient.buildMiniJobs(p)
     · M3AssembledClient.buildMiniLore(p, hooks?)
     · M3AssembledClient.buildCommandStrip(p, height)
     · M3AssembledClient.buildStatusBar(p, character)
     · M3AssembledClient.DEMO_CHARACTER       fallback character fixture

   B3 era-cleanness:
     · Status bar reads `TATOOINE · MOS EISLEY · DOCKING BAY 94` and
       `03:42 GST · 20 BBY` — Clone Wars era reference.
     · Feed pose references `Republic gunships` (CW-era polity).
     · L4 fix preserved: Docking Bay 94 + fuel cells, not cargo lifter.
     · Zero `Empire` / `Imperial` / `TIE` / `X-wing` / `Rebel` /
       `Stormtrooper` / `Vader` / `Death Star` / `ISB` references in
       data blocks.

   Q1 canonical-character policy note (architecture v50 §6.2):
     The fixtures preserve the JSX source's references to:
       · Greedo (Rodian, hostile) — bay-floor presence
       · Wuher-adjacent flavor via the cantina exit
       · Han Solo's Mynock starship is referenced indirectly via "Mynock"
         (the ship name itself — preserved verbatim from source).
     Drop 4.12b preserves these references at scaffold level per the
     established source-fidelity policy (Drops 4.6, 4.7, 4.10, 4.11).
     Production swap-in is tracked in the Q1-hardening drop.

   Dependencies (loaded earlier in the SPA load order):
     · window.M3Sheet (Drop 4.6 + 4.12a) — character sheet modal
     · window.M3Holocron (Drop 4.7) — holocron modal
     · window.M3MapNavigator (Drop 4.8) — full-screen map navigator
     · window.M3Holonet (Drop 4.10) — holonet ticker + browser modal

     All four are consumed via OPTIONAL DI hooks with defensive
     fallbacks. If a dependency module isn't loaded (e.g., during
     isolated SPA-test runs), the assembled client renders a labeled
     placeholder slot instead of crashing. This mirrors the
     m3_map_navigator `_defaultTierRenderer` pattern from Drop 4.8.

   What this module does NOT ship:
     · Live data binding. All feed items, comms messages, status
       indicators, and cartridge contents are demo fixtures. The
       eventual integration: wire the engine's pose-broadcast stream,
       HUD updates, and command-strip suggestions into these surfaces.
     · The MAP cartridge mini-renderer is wired to a tier-renderer DI
       hook (`hooks.getTierRenderer`). Default behavior: when not
       wired, the mini-map shows "TIER RENDERER NOT WIRED" — same
       seam pattern as m3_map_navigator. The tier-body renderer ports
       (post-4.12 work) supply the real Tier1aBody. Drop 4.15b adds
       `hooks.region` / `hooks.regionKey` pass-through: these flow to
       the map-popup's M3MapNavigator so its tier '1b' renders the
       player's wilderness region (Dune Sea vs Coruscant Underworld).
       Derive the key via M3Adapter.regionKeyForArea(geom).
     · Comms tab interactivity. Tabs render with a hard-coded active
       indicator on ALL; clicks are no-ops. Drop 2.5 (vision §6.5)
       lands the dynamic-channel wire-in.
     · Real wire-in to existing client.html flows. The module loads
       and registers its namespace; no production code calls it yet.

   Loading order in client.html: AFTER m3_sheet (4.6 + 4.12a),
   m3_holocron (4.7), m3_map_navigator (4.8), m3_holonet (4.10).
   Placed at the END of the SPA script-tag block.
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

// ─── htmlEl / svgEl: same shape as Drops 4.5-4.11 ────────────────────
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
// DEMO CHARACTER — fallback fixture. In production, hooks.character
// is the live character; if absent we fall back to the demo Tey Voss
// fixture from M3Sheet (when loaded) and finally to this minimal
// inline character so the module never crashes on missing deps.
// ════════════════════════════════════════════════════════════════════
var DEMO_CHARACTER = {
  name: 'TEY VOSS',
  species: 'Human',
  fp: 2, dsp: 0, cp: 18,
  attrs: [
    { k: 'DEX', code: '3D+1', penalty: false },
    { k: 'KNO', code: '3D',   penalty: false },
    { k: 'MEC', code: '2D+2', penalty: false },
    { k: 'PER', code: '4D',   penalty: false },
    { k: 'STR', code: '2D+1', penalty: true  },  // Wounded
    { k: 'TEC', code: '2D+2', penalty: false },
  ],
  status: [
    { label: 'WOUNDED',  color: 'red'   },
    { label: 'DEBT',     color: 'amber' },
    { label: 'FAVORED',  color: 'green' },
  ],
};

// ════════════════════════════════════════════════════════════════════
// STATUS BAR
// ════════════════════════════════════════════════════════════════════
function buildStatusBar(p, character) {
  character = character || DEMO_CHARACTER;

  var leftBlock = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 12 },
  }, [
    htmlEl('div', {
      style: {
        width: 6, height: 6, borderRadius: '50%',
        background: p.green, boxShadow: '0 0 4px ' + p.green,
      },
    }),
    htmlEl('span', { style: { color: p.cyan } }, ['BOSS/CS-37 \u00b7 FIELD DATAPAD']),
    htmlEl('span', { style: { color: p.inkFaint } }, ['\u00b7']),
    htmlEl('span', { style: { color: p.amber } }, [character.name]),
    htmlEl('span', { style: { color: p.inkFaint } }, ['\u00b7']),
    htmlEl('span', { style: { color: p.green } }, ['GROUND OPS']),
  ]);

  var centerLabel = htmlEl('span', {
    style: { color: p.amber },
  }, ['TATOOINE \u00b7 MOS EISLEY \u00b7 DOCKING BAY 94']);

  var indicators = htmlEl('div', { style: { display: 'flex', gap: 4 } }, [
    htmlEl('div', {
      style: {
        width: 5, height: 5, borderRadius: '50%',
        background: p.green, boxShadow: '0 0 3px ' + p.green,
      },
    }),
    htmlEl('div', {
      style: {
        width: 5, height: 5, borderRadius: '50%',
        background: p.amber, boxShadow: '0 0 3px ' + p.amber,
      },
    }),
    htmlEl('div', {
      style: { width: 5, height: 5, borderRadius: '50%', background: p.inkFaint },
    }),
  ]);

  var rightBlock = htmlEl('div', {
    style: { display: 'flex', gap: 12, alignItems: 'center' },
  }, [
    htmlEl('span', null, ['03:42 GST \u00b7 20 BBY']),
    indicators,
  ]);

  return htmlEl('div', {
    'data-status-bar': '1',
    style: {
      background: 'linear-gradient(180deg, ' + p.sky + ', ' + p.skyDeep + ')',
      borderBottom: '1px solid ' + p.inkDim,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 18px', height: '100%',
      fontSize: 10, letterSpacing: 2.5, color: p.inkDim,
    },
  }, [leftBlock, centerLabel, rightBlock]);
}

// ════════════════════════════════════════════════════════════════════
// LEFT HUD
// ════════════════════════════════════════════════════════════════════
function buildLeftHUD(p, character, hooks) {
  hooks = hooks || {};
  character = character || DEMO_CHARACTER;

  // Identity block
  var identity = htmlEl('div', null, [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.inkDim },
    }, ['OPERATIVE']),
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 18, color: p.inkBright,
        letterSpacing: 2, fontWeight: 700, marginTop: 4,
        textShadow: '0 0 6px ' + p.amber + '55',
      },
    }, [character.name]),
    htmlEl('div', {
      style: { fontSize: 9, color: p.inkDim, letterSpacing: 1.5, marginTop: 2 },
    }, [String(character.species || '').toUpperCase() + ' \u00b7 SMUGGLER']),
  ]);

  // Wound rungs row — 5-cell with first lit.
  var rungs = [];
  var rungData = [true, false, false, false, false];
  for (var i = 0; i < rungData.length; i++) {
    var on = rungData[i];
    rungs.push(htmlEl('div', {
      style: {
        flex: 1, height: 6,
        background: on ? p.red : 'rgba(0,0,0,0.5)',
        border: '1px solid ' + (on ? p.red : p.inkFaint),
        boxShadow: on ? '0 0 3px ' + p.red : 'none',
      },
    }));
  }
  var vitals = htmlEl('div', {
    style: {
      padding: '8px 10px', background: 'rgba(0,0,0,0.4)',
      border: '1px solid ' + p.inkFaint,
      borderLeft: '2px solid ' + p.red,
    },
  }, [
    htmlEl('div', {
      style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' },
    }, [
      htmlEl('span', {
        style: { fontSize: 9, letterSpacing: 2, color: p.inkDim },
      }, ['VITALS']),
      htmlEl('span', {
        style: { fontSize: 9, color: p.red, letterSpacing: 1.5, fontWeight: 700 },
      }, ['WOUNDED \u00b7 \u22121D']),
    ]),
    htmlEl('div', {
      style: { display: 'flex', gap: 3, marginTop: 5 },
    }, rungs),
  ]);

  // FP/DSP/CP cells.
  var pointCells = [];
  var cellData = [
    ['FP',  String(character.fp), p.green],
    ['DSP', String(character.dsp), p.red],
    ['CP',  String(character.cp), p.amber],
  ];
  for (var j = 0; j < cellData.length; j++) {
    var cd = cellData[j];
    pointCells.push(htmlEl('div', {
      style: {
        padding: '5px 6px',
        background: 'rgba(0,0,0,0.4)',
        border: '1px solid ' + cd[2] + '55',
        textAlign: 'center',
      },
    }, [
      htmlEl('div', {
        style: { fontSize: 8, color: p.inkDim, letterSpacing: 1.5 },
      }, [cd[0]]),
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 16, color: cd[2],
          fontWeight: 700, lineHeight: 1,
        },
      }, [cd[1]]),
    ]));
  }
  var points = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 4 },
  }, pointCells);

  // Attributes mini-grid.
  var attrCells = [];
  var attrs = character.attrs || [];
  for (var k = 0; k < attrs.length; k++) {
    var a = attrs[k];
    attrCells.push(htmlEl('div', {
      style: {
        padding: '3px 6px',
        background: 'rgba(0,0,0,0.4)',
        border: '1px solid ' + (a.penalty ? (p.red + '88') : p.inkFaint),
      },
    }, [
      htmlEl('div', {
        style: { fontSize: 8, color: p.inkDim, letterSpacing: 1.5 },
      }, [a.k]),
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 11,
          color: a.penalty ? p.red : p.inkBright, fontWeight: 600, lineHeight: 1,
        },
      }, [a.code]),
    ]));
  }
  var attrsBlock = htmlEl('div', null, [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.inkDim, marginBottom: 5 },
    }, ['\u25ae\u25ae ATTRIBUTES']),
    htmlEl('div', {
      style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 3 },
    }, attrCells),
  ]);

  // Status chips.
  var statusChips = [];
  var statuses = character.status || [];
  for (var m = 0; m < statuses.length; m++) {
    var s = statuses[m];
    var sc = s.color === 'red' ? p.red : s.color === 'green' ? p.green : p.amber;
    statusChips.push(htmlEl('span', {
      style: {
        fontSize: 8, letterSpacing: 1.5, padding: '2px 5px',
        color: sc, border: '1px solid ' + sc,
        background: sc + '11',
      },
    }, [s.label]));
  }
  var statusBlock = htmlEl('div', null, [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.inkDim, marginBottom: 5 },
    }, ['\u25ae\u25ae STATUS']),
    htmlEl('div', {
      style: { display: 'flex', flexWrap: 'wrap', gap: 3 },
    }, statusChips),
  ]);

  // +SHEET button.
  var sheetBtnProps = {
    'data-sheet-open-btn': '1',
    style: {
      marginTop: 'auto',
      padding: '8px 10px',
      background: 'linear-gradient(180deg, ' + p.amber + ', ' + p.amber + 'cc)',
      color: p.skyDeep,
      border: '1px solid ' + p.amber,
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 10, letterSpacing: 2.5, fontWeight: 700,
      cursor: 'pointer',
      boxShadow: '0 0 10px ' + p.amber + '66',
    },
  };
  if (typeof hooks.onSheet === 'function') {
    sheetBtnProps.onClick = hooks.onSheet;
  }
  var sheetBtn = htmlEl('button', sheetBtnProps, ['+SHEET \u00b7 OPEN DOSSIER']);

  return htmlEl('div', {
    'data-left-hud': '1',
    style: {
      borderRight: '1px dashed ' + p.inkDim,
      background: 'rgba(0,0,0,0.2)',
      padding: 14, display: 'flex', flexDirection: 'column', gap: 12,
      overflowY: 'auto',
    },
  }, [identity, vitals, points, attrsBlock, statusBlock, sheetBtn]);
}

// ════════════════════════════════════════════════════════════════════
// CENTER FEED
// ════════════════════════════════════════════════════════════════════
function buildCenterFeed(p, hooks) {
  hooks = hooks || {};

  // Room banner
  var banner = htmlEl('div', {
    style: {
      padding: '8px 18px',
      background: 'linear-gradient(90deg, ' + p.amber + '1f, transparent)',
      borderBottom: '1px solid ' + p.inkFaint,
    },
  }, [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.inkDim },
    }, ['\u25b8 YOU ARE IN']),
    htmlEl('div', {
      style: { display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 2 },
    }, [
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 18, color: p.inkBright,
          letterSpacing: 1, fontWeight: 700, textShadow: '0 0 6px ' + p.amber + '55',
        },
      }, ['Docking Bay 94']),
      htmlEl('span', {
        style: {
          fontSize: 9, letterSpacing: 2, color: p.green,
          border: '1px solid ' + p.green, padding: '1px 5px',
        },
      }, ['SECURED']),
      htmlEl('span', {
        style: {
          fontSize: 9, color: p.inkDim, marginLeft: 'auto', letterSpacing: 1,
        },
      }, ['Mos Eisley Spaceport \u00b7 Pit Floor']),
    ]),
  ]);

  // Feed items
  var feedItems = [];

  // 1. Descriptive line with two hot nouns.
  feedItems.push(_feedItem(p, {}, [
    htmlEl('span', {
      style: {
        fontFamily: "'IBM Plex Sans'", fontSize: 12.5, lineHeight: 1.6,
        color: p.fg || p.ink,
      },
    }, [
      'A wide, sunken pit of pitted ',
      _hotNoun(p, 'duracrete', hooks.onHolocron, p.amber),
      '. Heat radiates from the floor. Eight landing lights ring the bay; two flicker. Cables snake across the scorched ground from the fuel cells.',
    ]),
  ]));

  // 2. "Also here" block with three rows.
  var presentRows = [
    ['Yenn Karac',  'Corellian mechanic',  p.amber],
    ['Mak Torrin',  'Old pilot',           p.amber],
    ['Greedo',      'Rodian, hostile',     p.red],
  ];
  var presentChildren = [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.inkDim, marginBottom: 3 },
    }, ['\u25c6 ALSO HERE']),
  ];
  for (var i = 0; i < presentRows.length; i++) {
    var r = presentRows[i];
    presentChildren.push(htmlEl('div', {
      style: { fontSize: 12, lineHeight: 1.5, fontFamily: "'IBM Plex Sans'" },
    }, [
      _hotNoun(p, r[0], hooks.onHolocron, r[2]),
      htmlEl('span', {
        style: { color: p.body || p.ink, opacity: 0.85 },
      }, [' \u00b7 ' + r[1]]),
    ]));
  }
  feedItems.push(_feedItem(p, { accent: true, border: true }, presentChildren));

  // 3. Yenn pose
  feedItems.push(_feedItem(p, { bar: p.amber, bg: p.amber + '10' }, [
    htmlEl('div', {
      style: { fontSize: 12, lineHeight: 1.6, fontFamily: "'IBM Plex Sans'" },
    }, [
      htmlEl('b', {
        style: {
          fontFamily: "'Space Grotesk'", color: p.amber,
          letterSpacing: 0.5, marginRight: 6,
        },
      }, ['Yenn Karac']),
      htmlEl('i', { style: { color: p.inkDim } }, ['says,']),
      ' "Late again, kid. That Mynock\'s been coughing since the Kessel run."',
    ]),
  ]));

  // 4. Tey Voss pose (self).
  feedItems.push(_feedItem(p, { bar: p.green, bg: p.green + '10' }, [
    htmlEl('div', {
      style: { fontSize: 12, lineHeight: 1.6, fontFamily: "'IBM Plex Sans'" },
    }, [
      htmlEl('b', {
        style: {
          fontFamily: "'Space Grotesk'", color: p.green,
          letterSpacing: 0.5, marginRight: 6,
        },
      }, ['Tey Voss']),
      "drops a bundle of credits on the workbench without a word. The clatter is louder than it has any right to be in the bay's hush.",
    ]),
  ]));

  // 5. Event.
  feedItems.push(_feedItem(p, {}, [
    htmlEl('span', {
      style: { fontFamily: "'IBM Plex Mono'", fontSize: 11, color: p.red },
    }, ['\u26a0 You hear blaster fire \u2014 somewhere distant, muffled.']),
  ]));

  // 6. Mak whisper pose with one hot noun.
  feedItems.push(_feedItem(p, { bar: p.amber, bg: p.amber + '10' }, [
    htmlEl('div', {
      style: { fontSize: 12, lineHeight: 1.6, fontFamily: "'IBM Plex Sans'" },
    }, [
      htmlEl('b', {
        style: {
          fontFamily: "'Space Grotesk'", color: p.amber,
          letterSpacing: 0.5, marginRight: 6,
        },
      }, ['Mak Torrin']),
      htmlEl('i', { style: { color: p.inkDim } }, ['whispers to you,']),
      ' "',
      _hotNoun(p, 'Republic', hooks.onHolocron, p.amber),
      ' gunships made orbit at midnight. Whatever you\'re running, get it off-planet before dawn."',
    ]),
  ]));

  var feed = htmlEl('div', {
    style: { flex: 1, overflowY: 'auto', padding: '8px 0' },
  }, feedItems);

  return htmlEl('div', {
    'data-center-feed': '1',
    style: {
      display: 'flex', flexDirection: 'column', minWidth: 0,
      borderRight: '1px dashed ' + p.inkDim,
    },
  }, [banner, feed, buildCommsTabs(p)]);
}

function _feedItem(p, opts, children) {
  opts = opts || {};
  return htmlEl('div', {
    style: {
      padding: '6px 18px',
      borderBottom: '1px solid ' + p.inkFaint + '33',
      borderLeft: opts.bar ? ('3px solid ' + opts.bar) : 'none',
      background: opts.bg || 'transparent',
    },
  }, children);
}

function _hotNoun(p, text, onClick, color) {
  var c = color || p.amber;
  var props = {
    style: {
      color: c, fontWeight: 600,
      borderBottom: '1px dotted ' + c + '66',
      cursor: 'pointer',
    },
    title: 'Open in Holocron',
  };
  if (typeof onClick === 'function') {
    props.onClick = onClick;
  }
  return htmlEl('span', props, [text]);
}

// ════════════════════════════════════════════════════════════════════
// COMMS TABS
// ════════════════════════════════════════════════════════════════════
function buildCommsTabs(p) {
  var tabs = [
    ['ALL',     4,  true],
    ['IC',      3, false],
    ['OOC',     0, false],
    ['SYSTEM',  1, false],
    ['COMLINK', 0, false],
    ['HOLONET', 1, false],
  ];

  var tabPills = [];
  for (var i = 0; i < tabs.length; i++) {
    var t = tabs[i];
    var label = t[0], badge = t[1], active = t[2];

    var pillChildren = [htmlEl('span', null, [label])];
    if (badge > 0) {
      pillChildren.push(htmlEl('span', {
        style: {
          fontSize: 8, padding: '0 4px',
          background: active ? p.amber : 'rgba(0,0,0,0.4)',
          color: active ? p.skyDeep : p.inkDim,
          borderRadius: 6,
        },
      }, [String(badge)]));
    }

    tabPills.push(htmlEl('div', {
      style: {
        padding: '5px 10px',
        background: active ? (p.amber + '22') : 'transparent',
        borderRight: i < tabs.length - 1 ? ('1px solid ' + p.inkFaint) : 'none',
        borderBottom: active ? ('2px solid ' + p.amber) : '2px solid transparent',
        fontSize: 10, letterSpacing: 1.8,
        color: active ? p.inkBright : p.inkDim,
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', gap: 4,
      },
    }, pillChildren));
  }

  var preview = htmlEl('div', {
    style: {
      padding: '5px 14px', fontSize: 10, lineHeight: 1.6,
      fontFamily: "'IBM Plex Mono'", height: 56, overflow: 'hidden',
    },
  }, [
    htmlEl('div', null, [
      htmlEl('span', { style: { color: p.inkDim } }, ['[IC]']),
      ' ',
      htmlEl('span', { style: { color: p.inkBright } },
             ['Yenn Karac: "Mynock\'s fueled."']),
    ]),
    htmlEl('div', null, [
      htmlEl('span', { style: { color: p.inkDim } }, ['[SYS]']),
      ' ',
      htmlEl('span', { style: { color: p.inkDim } },
             ['\u203a Greedo enters from the south.']),
    ]),
    htmlEl('div', null, [
      htmlEl('span', { style: { color: p.inkDim } }, ['[IC]']),
      ' ',
      htmlEl('span', { style: { color: p.inkBright } },
             ['Mak: "Republic gunships made orbit."']),
    ]),
  ]);

  return htmlEl('div', {
    'data-comms-tabs': '1',
    style: {
      borderTop: '1px solid ' + p.inkFaint,
      background: 'rgba(0,0,0,0.35)',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    },
  }, [
    htmlEl('div', {
      style: { display: 'flex', borderBottom: '1px solid ' + p.inkFaint },
    }, tabPills),
    preview,
  ]);
}

// ════════════════════════════════════════════════════════════════════
// RIGHT CARTRIDGE
// ════════════════════════════════════════════════════════════════════
function buildRightCartridge(p, cartridge, hooks) {
  hooks = hooks || {};
  cartridge = cartridge || 'MAP';

  var tabs = ['MAP', 'INV', 'JOBS', 'LORE', 'SIT'];
  var tabPills = [];
  for (var i = 0; i < tabs.length; i++) {
    var t = tabs[i];
    var active = cartridge === t;

    (function(label) {
      var pillProps = {
        'data-cartridge-tab': label,
        style: {
          padding: '10px 6px', textAlign: 'center',
          fontFamily: "'IBM Plex Mono'", fontSize: 10, letterSpacing: 2.5,
          color: active ? p.skyDeep : p.inkDim,
          background: active
            ? ('linear-gradient(180deg, ' + p.inkBright + ', ' + p.amber + ')')
            : 'transparent',
          borderRight: i < tabs.length - 1 ? ('1px solid ' + p.inkFaint) : 'none',
          boxShadow: active ? ('0 0 12px ' + p.amber + '66') : 'none',
          fontWeight: active ? 700 : 500,
          cursor: 'pointer',
        },
      };
      if (typeof hooks.onCartridgeClick === 'function') {
        pillProps.onClick = function() { hooks.onCartridgeClick(label); };
      }
      tabPills.push(htmlEl('div', pillProps, [label]));
    })(t);
  }

  var tabStrip = htmlEl('div', {
    style: {
      display: 'grid', gridTemplateColumns: 'repeat(' + tabs.length + ', 1fr)',
      borderBottom: '1px solid ' + p.inkDim,
      background: 'linear-gradient(180deg, ' + p.sky + ', ' + p.skyDeep + ')',
    },
  }, tabPills);

  // Body — dispatch on cartridge.
  var bodyContent;
  switch (cartridge) {
    case 'MAP':  bodyContent = buildMiniMap(p, hooks);  break;
    case 'INV':  bodyContent = buildMiniInv(p);          break;
    case 'JOBS': bodyContent = buildMiniJobs(p);         break;
    case 'LORE': bodyContent = buildMiniLore(p, hooks);  break;
    // Living-world situation board (UX Drop 4). The 'SIT' tab key is the
    // live cartridge value; 'SITUATION' is accepted as an alias.
    case 'SIT':
    case 'SITUATION':
      bodyContent = buildMiniSituation(p, hooks);        break;
    default:     bodyContent = buildMiniMap(p, hooks);  break;
  }
  var body = htmlEl('div', {
    'data-current-cartridge': cartridge,
    style: { flex: 1, overflowY: 'auto', padding: 14 },
  }, [bodyContent]);

  return htmlEl('div', {
    'data-right-cartridge': '1',
    style: {
      background: 'rgba(0,0,0,0.25)',
      display: 'flex', flexDirection: 'column',
    },
  }, [tabStrip, body]);
}

// ────────────────────────────────────────────────────────────────────
// MINIMAP — uses DI'd tier renderer (or fallback placeholder)
// ────────────────────────────────────────────────────────────────────
function buildMiniMap(p, hooks) {
  hooks = hooks || {};

  // Header strip with EXPAND button
  var expandBtnProps = {
    'data-map-expand-btn': '1',
    style: {
      fontFamily: "'IBM Plex Mono'", fontSize: 8, letterSpacing: 1.5,
      padding: '2px 6px', background: 'transparent',
      color: p.amber, border: '1px solid ' + p.amber + '66', cursor: 'pointer',
    },
  };
  if (typeof hooks.onMap === 'function') {
    expandBtnProps.onClick = hooks.onMap;
  }
  var expandBtn = htmlEl('button', expandBtnProps, ['\u2922 EXPAND']);

  var header = htmlEl('div', {
    style: {
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      marginBottom: 8,
    },
  }, [
    htmlEl('span', {
      style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600 },
    }, ['\u25ae\u25ae HOLOCARTA \u00b7 SPACEPORT']),
    expandBtn,
  ]);

  // Mini-map body — try the DI'd tier renderer, else the canonical
  // M3TierRegistry lookup (Drop 4.15 cutover), else placeholder. The
  // JSX source called <Tier1aBody data={MOS_EISLEY} ...>; we seam it
  // via hooks.getTierRenderer (same hook the M3MapNavigator accepts).
  var bodyEl;
  var tierFn = (typeof hooks.getTierRenderer === 'function')
                 ? hooks.getTierRenderer
                 : (window.M3TierRegistry && window.M3TierRegistry.getTierRenderer) || null;
  if (tierFn) {
    try {
      bodyEl = tierFn('1a', {
        p: p, width: 332, height: 230,
        time: 'night', weather: 'clear',
        data: hooks.areaGeometryData || null,
      });
    } catch (e) {
      bodyEl = null;
    }
  }
  if (!bodyEl) {
    // Placeholder — same labeled fallback pattern as M3MapNavigator
    bodyEl = htmlEl('div', {
      'data-default-tier-body': '1a',
      style: {
        width: 332, height: 230,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexDirection: 'column', gap: 8,
        color: p.inkDim,
        background: 'radial-gradient(circle at 50% 50%, ' + p.amber + '11, transparent 60%)',
      },
    }, [
      htmlEl('div', {
        style: { fontSize: 12, letterSpacing: 2, color: p.inkDim, textAlign: 'center' },
      }, ['TIER RENDERER NOT WIRED']),
      htmlEl('div', {
        style: { fontSize: 8, letterSpacing: 1, color: p.inkFaint, textAlign: 'center' },
      }, ['caller supplies via hooks.getTierRenderer']),
    ]);
  }

  var mapFrame = htmlEl('div', {
    style: {
      height: 230, border: '1px solid ' + p.inkFaint,
      background: '#000', overflow: 'hidden', position: 'relative',
    },
  }, [bodyEl]);

  // Legend
  var legend = htmlEl('div', {
    style: {
      marginTop: 6, fontSize: 8, letterSpacing: 1.5,
      color: p.inkDim, display: 'flex', justifyContent: 'space-between',
    },
  }, [
    htmlEl('span', null, ['\u25c9 YOU']),
    htmlEl('span', null, ['\u25cf PC']),
    htmlEl('span', null, ['\u25b4 HOSTILE']),
    htmlEl('span', null, ['\u232c NPC']),
  ]);

  // Exits
  var exitsData = [
    ['N', 'Entrance'], ['E', 'Bay 95'], ['U', 'Cantina'], ['\u2191', 'Mynock'],
  ];
  var exitCells = [];
  for (var i = 0; i < exitsData.length; i++) {
    var ex = exitsData[i];
    exitCells.push(htmlEl('div', {
      style: {
        padding: '4px 8px',
        border: '1px solid ' + p.inkFaint,
        background: 'rgba(0,0,0,0.3)',
        display: 'flex', gap: 6, alignItems: 'baseline',
      },
    }, [
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 12, color: p.amber,
          fontWeight: 700, minWidth: 12,
        },
      }, [ex[0]]),
      htmlEl('span', { style: { fontSize: 11, color: p.ink } }, [ex[1]]),
    ]));
  }
  var exits = htmlEl('div', { style: { marginTop: 14 } }, [
    htmlEl('div', {
      style: {
        fontSize: 9, letterSpacing: 3, color: p.amber,
        fontWeight: 600, marginBottom: 6,
      },
    }, ['\u25ae\u25ae EXITS']),
    htmlEl('div', {
      style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 },
    }, exitCells),
  ]);

  // Services
  var services = ['VENDOR', 'MAIL', 'DOCK', 'COMLINK'];
  var svcChips = [];
  for (var j = 0; j < services.length; j++) {
    svcChips.push(htmlEl('span', {
      style: {
        fontSize: 9, letterSpacing: 1.5, padding: '2px 6px',
        color: p.amber, border: '1px solid ' + p.inkFaint,
        background: 'rgba(0,0,0,0.3)',
      },
    }, [services[j]]));
  }
  var svcRow = htmlEl('div', {
    style: { marginTop: 10, display: 'flex', gap: 4, flexWrap: 'wrap' },
  }, svcChips);

  return htmlEl('div', null, [header, mapFrame, legend, exits, svcRow]);
}

// ────────────────────────────────────────────────────────────────────
// MINIINV
// ────────────────────────────────────────────────────────────────────
function buildMiniInv(p) {
  var items = [
    ['HVY BLASTER PISTOL', '5D \u00b7 50/50', p.inkBright],
    ['VIBROKNIFE',          'STR+1D',          p.ink],
    ['PADDED ARMOR',        '+1D/+1D',         p.ink],
    ['STIM PACK',           'x2',              p.green],
    ['MED-KIT',             '3/3',             p.green],
    ['COMLINK',             '\u2014',          p.inkDim],
  ];
  var rows = [];
  for (var i = 0; i < items.length; i++) {
    var it = items[i];
    rows.push(htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between',
        padding: '4px 8px', marginBottom: 2,
        background: 'rgba(0,0,0,0.3)',
        border: '1px solid ' + p.inkFaint,
      },
    }, [
      htmlEl('span', {
        style: { fontSize: 10, color: it[2], letterSpacing: 0.5 },
      }, [it[0]]),
      htmlEl('span', {
        style: { fontSize: 9, color: p.inkDim },
      }, [it[1]]),
    ]));
  }

  var soak = htmlEl('div', {
    style: {
      marginTop: 10, padding: '6px 8px',
      background: p.amber + '22', border: '1px solid ' + p.amber,
    },
  }, [
    htmlEl('div', {
      style: { display: 'flex', justifyContent: 'space-between' },
    }, [
      htmlEl('span', {
        style: { fontSize: 9, letterSpacing: 2, color: p.inkDim },
      }, ['SOAK']),
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 13,
          color: p.inkBright, fontWeight: 700,
        },
      }, ['4D+2']),
    ]),
  ]);

  return htmlEl('div', null, [
    htmlEl('div', {
      style: {
        fontSize: 9, letterSpacing: 3, color: p.amber,
        fontWeight: 600, marginBottom: 8,
      },
    }, ['\u25ae\u25ae LOADOUT']),
  ].concat(rows).concat([soak]));
}

// ────────────────────────────────────────────────────────────────────
// MINIJOBS
// ────────────────────────────────────────────────────────────────────
function buildMiniJobs(p) {
  var jobs = [
    ['Spice Run \u00b7 Kessel',  '2/4 stops \u00b7 18,000 cr',  50, p.amber, false],
    ['Bounty \u00b7 Vex Drago',  '3 days \u00b7 8,000 cr',      30, p.red,   true],
    ['Sealed Senate Disp.',      'Anchorhead \u00b7 TBD',       80, p.green, false],
  ];
  var rows = [];
  for (var i = 0; i < jobs.length; i++) {
    var j = jobs[i];
    var name = j[0], status = j[1], pct = j[2], c = j[3], urg = j[4];

    var headRowChildren = [
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 11,
          color: p.inkBright, fontWeight: 600,
        },
      }, [name]),
    ];
    if (urg) {
      headRowChildren.push(htmlEl('span', {
        style: { fontSize: 7, color: p.red, letterSpacing: 1.5, fontWeight: 700 },
      }, ['\u25cf URGENT']));
    }

    rows.push(htmlEl('div', {
      style: {
        padding: '6px 8px', marginBottom: 4,
        background: 'rgba(0,0,0,0.3)',
        border: '1px solid ' + p.inkFaint,
        borderLeft: '2px solid ' + c,
      },
    }, [
      htmlEl('div', {
        style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' },
      }, headRowChildren),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, marginTop: 2 },
      }, [status]),
      htmlEl('div', {
        style: { marginTop: 4, height: 3, background: 'rgba(0,0,0,0.5)' },
      }, [
        htmlEl('div', {
          style: {
            width: pct + '%', height: '100%',
            background: c, boxShadow: '0 0 3px ' + c,
          },
        }),
      ]),
    ]));
  }

  return htmlEl('div', null, [
    htmlEl('div', {
      style: {
        fontSize: 9, letterSpacing: 3, color: p.amber,
        fontWeight: 600, marginBottom: 8,
      },
    }, ['\u25ae\u25ae ACTIVE JOBS \u00b7 3']),
  ].concat(rows));
}

// ────────────────────────────────────────────────────────────────────
// MINILORE
// ────────────────────────────────────────────────────────────────────
function buildMiniLore(p, hooks) {
  hooks = hooks || {};

  var openBtnProps = {
    'data-holocron-open-btn': '1',
    style: {
      fontFamily: "'IBM Plex Mono'", fontSize: 8, letterSpacing: 1.5,
      padding: '2px 6px', background: 'transparent',
      color: p.amber, border: '1px solid ' + p.amber + '66',
      cursor: 'pointer',
    },
  };
  if (typeof hooks.onHolocron === 'function') {
    openBtnProps.onClick = hooks.onHolocron;
  }
  var openBtn = htmlEl('button', openBtnProps, ['\u2922 OPEN']);

  var header = htmlEl('div', {
    style: {
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      marginBottom: 8,
    },
  }, [
    htmlEl('span', {
      style: {
        fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600,
      },
    }, ['\u25ae\u25ae HOLOCRON']),
    openBtn,
  ]);

  // SVG hexagon
  var holocronSvg = svgEl('svg', { width: 28, height: 28, viewBox: '0 0 30 30' }, [
    svgEl('polygon', {
      points: '15,3 26,9 26,21 15,27 4,21 4,9',
      fill: 'none', stroke: p.amber, strokeWidth: 1.5,
    }),
    svgEl('polygon', {
      points: '15,9 21,12 21,18 15,21 9,18 9,12',
      fill: p.amber + '55', stroke: p.inkBright, strokeWidth: 0.7,
    }),
  ]);

  var factionCard = htmlEl('div', {
    style: {
      padding: 10, border: '1px solid ' + p.amber + '55',
      background: p.amber + '11',
      display: 'flex', alignItems: 'center', gap: 10,
    },
  }, [
    holocronSvg,
    htmlEl('div', null, [
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 12, color: p.amber,
          fontWeight: 700,
        },
      }, ['HUTT CARTEL']),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, letterSpacing: 1 },
      }, ['FACTION \u00b7 FRIENDLY']),
    ]),
  ]);

  var lastOpened = htmlEl('div', {
    style: {
      marginTop: 10, padding: '6px 8px',
      background: 'rgba(0,0,0,0.3)', border: '1px solid ' + p.inkFaint,
      fontSize: 10, color: p.inkDim, letterSpacing: 0.3, lineHeight: 1.5,
    },
  }, [
    'Last opened: ',
    htmlEl('span', { style: { color: p.amber } }, ['Greedo \u00b7 Rodian']),
    ' \u00b7 ',
    htmlEl('span', { style: { color: p.amber } }, ['Docking Bay 94']),
    ' \u00b7 ',
    htmlEl('span', { style: { color: p.amber } }, ['Kessel Run']),
  ]);

  return htmlEl('div', null, [header, factionCard, lastOpened]);
}

// ────────────────────────────────────────────────────────────────────
// MINI SITUATION — the SIT cartridge body (UX Drop 4).
// Renders the living-world situation board via M3SituationBoard.render
// over hooks.situation (the latest situation_state push). Degrades to a
// labeled placeholder if the board module or live data isn't present.
// ────────────────────────────────────────────────────────────────────
function buildMiniSituation(p, hooks) {
  hooks = hooks || {};

  var header = htmlEl('div', {
    style: {
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      marginBottom: 8,
    },
  }, [
    htmlEl('span', {
      style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600 },
    }, ['▮▮ SITUATION · LIVE GALAXY']),
  ]);

  var bodyEl = null;
  if (window.M3SituationBoard && typeof window.M3SituationBoard.render === 'function'
      && hooks.situation) {
    try { bodyEl = window.M3SituationBoard.render(hooks.situation); }
    catch (e) { bodyEl = null; }
  }
  if (!bodyEl) {
    bodyEl = htmlEl('div', {
      'data-sit-placeholder': '1',
      style: {
        padding: 14, textAlign: 'center',
        border: '1px solid ' + p.inkFaint, background: 'rgba(0,0,0,0.3)',
        color: p.inkDim, fontSize: 10, letterSpacing: 1,
      },
    }, ['No situation data yet — enter a tracked zone.']);
  }

  return htmlEl('div', { 'data-mini-situation': '1' }, [header, bodyEl]);
}

// ════════════════════════════════════════════════════════════════════
// COMMAND STRIP
// ════════════════════════════════════════════════════════════════════
function buildCommandStrip(p, height) {
  var actionKeys = ['LOOK', 'POSE', 'SAY', 'N', 'E', 'UP', 'BOARD'];
  var actionChips = [];
  for (var i = 0; i < actionKeys.length; i++) {
    actionChips.push(htmlEl('div', {
      style: {
        padding: '4px 10px',
        background: 'linear-gradient(180deg, ' + p.sky + ', ' + p.skyDeep + ')',
        border: '1px solid ' + p.amber + '66',
        color: p.amber,
        fontSize: 10, letterSpacing: 2,
        boxShadow: 'inset 0 -2px 2px rgba(0,0,0,0.4)',
        cursor: 'pointer',
      },
    }, [actionKeys[i]]));
  }

  var hint = htmlEl('span', {
    style: { fontSize: 9, color: p.inkDim, marginLeft: 8, letterSpacing: 1 },
  }, [
    'Type ',
    htmlEl('code', { style: { color: p.green } }, ['pose']),
    ' for narrative, ',
    htmlEl('code', { style: { color: p.amber } }, [':']),
    ' shorthand',
  ]);

  var actionRow = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 8 },
  }, actionChips.concat([hint]));

  // Composer line
  var caret = htmlEl('span', {
    style: {
      width: 7, height: 15, background: p.green,
      display: 'inline-block', marginLeft: 2,
      animation: 'shellblink 1s step-end infinite',
    },
  });

  var sendChip = htmlEl('span', {
    style: {
      marginLeft: 'auto', padding: '2px 10px',
      background: p.green, color: p.skyDeep,
      fontSize: 10, letterSpacing: 2, fontWeight: 700,
      border: '1px solid ' + p.green,
    },
  }, ['SEND \u21b5']);

  var composer = htmlEl('div', {
    style: {
      height: 30, padding: '0 12px',
      background: p.skyDeep,
      border: '1px solid ' + p.green + '66',
      boxShadow: 'inset 0 0 10px ' + p.green + '22',
      display: 'flex', alignItems: 'center', gap: 8,
      fontFamily: "'IBM Plex Mono', monospace", fontSize: 13, color: p.ink,
    },
  }, [
    htmlEl('span', { style: { color: p.green } }, ['>']),
    htmlEl('span', { style: { color: p.ink, opacity: 0.85 } },
           ['pose drops a bundle of credits on the workbench without a word']),
    caret,
    sendChip,
  ]);

  return htmlEl('div', {
    'data-command-strip': '1',
    style: {
      position: 'absolute', bottom: 0, left: 0, right: 0, height: height,
      background: 'linear-gradient(180deg, ' + p.sky + ', ' + p.skyDeep + ')',
      borderTop: '1px solid ' + p.inkDim,
      padding: '10px 18px',
      display: 'flex', flexDirection: 'column', gap: 8,
      zIndex: 9,
    },
  }, [actionRow, composer]);
}

// ════════════════════════════════════════════════════════════════════
// MAP POPUP MODAL — wraps M3MapNavigator at modal size
// (Local to this module per the JSX source — the JSX defined
//  MapPopupModal inline rather than as a shared modal builder.)
// ════════════════════════════════════════════════════════════════════
function _buildMapPopupModal(p, hooks) {
  hooks = hooks || {};
  var onClose = hooks.onClose || null;

  // Inner map element — use M3MapNavigator when available, else
  // placeholder. The Drop 4.8 navigator exposes .create() which
  // returns a handle whose .element we mount.
  var mapEl;
  if (window.M3MapNavigator && typeof window.M3MapNavigator.create === 'function') {
    try {
      var navHandle = window.M3MapNavigator.create(p, {
        width: 1080, height: 720,
        getTierRenderer: hooks.getTierRenderer || null,
        // Drop 4.15b: forward the player's wilderness region so tier '1b'
        // renders the correct overview (Dune Sea vs Coruscant Underworld).
        region:    hooks.region    || null,
        regionKey: hooks.regionKey || null,
      });
      mapEl = navHandle.element;
    } catch (e) {
      mapEl = null;
    }
  }
  if (!mapEl) {
    mapEl = htmlEl('div', {
      'data-map-popup-fallback': '1',
      style: {
        width: 1080, height: 720,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexDirection: 'column', gap: 8,
        background: 'rgba(0,0,0,0.85)', color: p.inkDim,
      },
    }, [
      htmlEl('div', {
        style: { fontSize: 18, letterSpacing: 3, color: p.amber },
      }, ['MAP NAVIGATOR NOT LOADED']),
      htmlEl('div', {
        style: { fontSize: 10, letterSpacing: 1, color: p.inkFaint },
      }, ['window.M3MapNavigator is required']),
    ]);
  }

  var closeBtnProps = {
    'data-map-close-btn': '1',
    style: {
      position: 'absolute', top: 10, right: 10, zIndex: 201,
      width: 24, height: 24, borderRadius: '50%',
      background: p.red, border: 'none', cursor: 'pointer',
      fontFamily: "'IBM Plex Mono'", fontSize: 10,
      color: p.skyDeep, fontWeight: 700,
    },
  };
  if (typeof onClose === 'function') {
    closeBtnProps.onClick = onClose;
  }
  var closeBtn = htmlEl('button', closeBtnProps, ['\u2715']);

  var window_ = htmlEl('div', {
    style: {
      width: 1080, height: 720, position: 'relative',
      animation: 'holoPop 220ms cubic-bezier(.4,.0,.2,1)',
      boxShadow: '0 0 0 1px #000, 0 0 30px ' + p.amber + '55, 0 40px 80px rgba(0,0,0,0.85)',
    },
  }, [mapEl, closeBtn]);

  window_.addEventListener('click', function(e) { e.stopPropagation(); });

  var backdropProps = {
    'data-map-modal': '1',
    style: {
      position: 'absolute', inset: 0, zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(1px)',
      animation: 'holoFade 200ms ease-out',
    },
  };
  if (typeof onClose === 'function') {
    backdropProps.onClick = function(e) {
      if (e.target === backdrop) onClose();
    };
  }
  var backdrop = htmlEl('div', backdropProps, [window_]);

  return backdrop;
}

// ════════════════════════════════════════════════════════════════════
// STATELESS BUILD (no popup state — caller wires onOpenPopup hook)
// ════════════════════════════════════════════════════════════════════
function buildAssembledClient(p, hooks) {
  hooks = hooks || {};
  var width  = hooks.width  || 1280;
  var height = hooks.height || 920;
  var character = hooks.character || _resolveCharacter();

  var TOP_TICKER = 26;
  var TOP_BAR    = 30;
  var BOTTOM     = 84;
  var RIGHT_RAIL = 360;
  var LEFT_RAIL  = 240;

  // Helper: dispatch popup-open via hook if provided.
  function _openPopup(name) {
    if (typeof hooks.onOpenPopup === 'function') hooks.onOpenPopup(name);
  }
  function _setCart(name) {
    if (typeof hooks.onSetCartridge === 'function') hooks.onSetCartridge(name);
  }

  // Top: Holonet ticker slot.
  var tickerEl;
  if (window.M3Holonet && typeof window.M3Holonet.buildHolonetTicker === 'function') {
    try {
      tickerEl = window.M3Holonet.buildHolonetTicker(p, {
        height: TOP_TICKER,
        onOpen: function() { _openPopup('holonet'); },
      });
    } catch (e) {
      tickerEl = null;
    }
  }
  if (!tickerEl) {
    tickerEl = htmlEl('div', {
      'data-holonet-ticker-fallback': '1',
      style: {
        width: '100%', height: '100%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.4)',
        fontSize: 9, color: p.inkDim, letterSpacing: 2,
      },
    }, ['HOLONET TICKER \u00b7 module not loaded']);
  }

  var tickerSlot = htmlEl('div', {
    style: {
      position: 'absolute', top: 0, left: 0, right: 0,
      height: TOP_TICKER, zIndex: 8,
    },
  }, [tickerEl]);

  // Status bar slot.
  var statusSlot = htmlEl('div', {
    style: {
      position: 'absolute', top: TOP_TICKER, left: 0, right: 0,
      height: TOP_BAR, zIndex: 8,
    },
  }, [buildStatusBar(p, character)]);

  // Main body grid.
  var bodyGrid = htmlEl('div', {
    'data-main-grid': '1',
    style: {
      position: 'absolute',
      top: TOP_TICKER + TOP_BAR, left: 0, right: 0, bottom: BOTTOM,
      display: 'grid',
      gridTemplateColumns: LEFT_RAIL + 'px 1fr ' + RIGHT_RAIL + 'px',
    },
  }, [
    buildLeftHUD(p, character, {
      onSheet: function() { _openPopup('sheet'); },
    }),
    buildCenterFeed(p, {
      onHolocron: function() { _openPopup('holocron'); },
    }),
    buildRightCartridge(p, hooks.cartridge || 'MAP', {
      onCartridgeClick: _setCart,
      onMap:       function() { _openPopup('map'); },
      onHolocron:  function() { _openPopup('holocron'); },
      getTierRenderer: hooks.getTierRenderer || null,
    }),
  ]);

  // Command strip
  var cmdSlot = buildCommandStrip(p, BOTTOM);

  // Outer
  return htmlEl('div', {
    'data-assembled-client': '1',
    style: {
      width: width, height: height, position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      border: '1px solid ' + p.inkDim,
      boxShadow: 'inset 0 0 40px ' + p.skyDeep + ', 0 0 0 1px #000, 0 20px 50px rgba(0,0,0,0.7)',
    },
  }, [tickerSlot, statusSlot, bodyGrid, cmdSlot]);
}

// ════════════════════════════════════════════════════════════════════
// STATEFUL HANDLE — owns popup + cartridge state; mounts popups
// into a stable container layer.
// ════════════════════════════════════════════════════════════════════
function create(p, hooks) {
  hooks = hooks || {};
  var character = hooks.character || _resolveCharacter();

  // State.
  var state = {
    popup:     null,                     // 'holocron' | 'sheet' | 'holonet' | 'map'
    cartridge: hooks.startCartridge || 'MAP',
  };

  // Stable outer container.
  var container = document.createElement('div');
  container.setAttribute('data-assembled-client-container', '1');
  container.style.position = 'relative';
  container.style.width  = (hooks.width  || 1280) + 'px';
  container.style.height = (hooks.height || 920)  + 'px';
  container.style.overflow = 'hidden';

  // Popup layer — separate stable child of container; popups mount here.
  var popupLayer = document.createElement('div');
  popupLayer.setAttribute('data-popup-layer', '1');
  popupLayer.style.position = 'absolute';
  popupLayer.style.inset = '0';
  popupLayer.style.zIndex = '100';
  popupLayer.style.pointerEvents = 'none';  // children re-enable

  // Shell layer — same idea; the assembled-client renders here.
  var shellLayer = document.createElement('div');
  shellLayer.setAttribute('data-shell-layer', '1');

  container.appendChild(shellLayer);
  container.appendChild(popupLayer);

  // Active popup handle (so we can destroy it on close).
  var activePopupHandle = null;
  var activePopupEl = null;

  function _rerenderShell() {
    while (shellLayer.firstChild) shellLayer.removeChild(shellLayer.firstChild);
    shellLayer.appendChild(buildAssembledClient(p, {
      width:           hooks.width,
      height:          hooks.height,
      character:       character,
      cartridge:       state.cartridge,
      getTierRenderer: hooks.getTierRenderer || null,
      onOpenPopup:     _openPopup,
      onSetCartridge:  _setCartridge,
    }));
  }

  function _closePopup() {
    state.popup = null;
    // Destroy/cleanup active popup if it exposed a destroy method
    // (M3Sheet.createCharacterSheetModal does; others return raw DOM).
    if (activePopupHandle && typeof activePopupHandle.destroy === 'function') {
      activePopupHandle.destroy();
    } else if (activePopupEl && activePopupEl.parentNode) {
      activePopupEl.parentNode.removeChild(activePopupEl);
    }
    activePopupHandle = null;
    activePopupEl = null;
    if (typeof hooks.onPopupChange === 'function') {
      hooks.onPopupChange(null);
    }
  }

  function _openPopup(name) {
    if (state.popup === name) return;
    // Close any currently-open popup.
    if (state.popup) _closePopup();
    state.popup = name;

    var el = null;
    var handle = null;
    switch (name) {
      case 'sheet':
        if (window.M3Sheet &&
            typeof window.M3Sheet.createCharacterSheetModal === 'function') {
          handle = window.M3Sheet.createCharacterSheetModal(p, character, {
            onClose: _closePopup,
          });
          el = handle.element;
        } else {
          el = _missingDepFallback(p, 'M3Sheet', _closePopup);
        }
        break;
      case 'holocron':
        if (window.M3Holocron &&
            typeof window.M3Holocron.buildHolocronModal === 'function') {
          el = window.M3Holocron.buildHolocronModal(p, {
            onClose: _closePopup,
            draggable: true,
          });
        } else {
          el = _missingDepFallback(p, 'M3Holocron', _closePopup);
        }
        break;
      case 'holonet':
        if (window.M3Holonet &&
            typeof window.M3Holonet.buildHolonetBrowserModal === 'function') {
          el = window.M3Holonet.buildHolonetBrowserModal(p, {
            onClose: _closePopup,
          });
        } else {
          el = _missingDepFallback(p, 'M3Holonet', _closePopup);
        }
        break;
      case 'map':
        el = _buildMapPopupModal(p, {
          onClose: _closePopup,
          getTierRenderer: hooks.getTierRenderer || null,
          region:    hooks.region    || null,
          regionKey: hooks.regionKey || null,
        });
        break;
      default:
        state.popup = null;
        return;
    }

    if (el) {
      el.style.pointerEvents = 'auto';
      popupLayer.appendChild(el);
      activePopupEl = el;
      activePopupHandle = handle;
    }
    if (typeof hooks.onPopupChange === 'function') {
      hooks.onPopupChange(name);
    }
  }

  function _setCartridge(name) {
    if (state.cartridge === name) return;
    state.cartridge = name;
    _rerenderShell();
    if (typeof hooks.onCartridgeChange === 'function') {
      hooks.onCartridgeChange(name);
    }
  }

  // Initial render.
  _rerenderShell();

  return {
    element: container,
    getState: function() {
      return { popup: state.popup, cartridge: state.cartridge };
    },
    openPopup:   _openPopup,
    closePopup:  _closePopup,
    setCartridge: _setCartridge,
    destroy: function() {
      _closePopup();
      while (shellLayer.firstChild) shellLayer.removeChild(shellLayer.firstChild);
      while (popupLayer.firstChild) popupLayer.removeChild(popupLayer.firstChild);
      if (container.parentNode) container.parentNode.removeChild(container);
    },
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────
function _resolveCharacter() {
  // Prefer M3Sheet's TEY_V2_FIXTURE for the full sheet character;
  // fall back to the minimal DEMO_CHARACTER if M3Sheet isn't loaded.
  if (window.M3Sheet && window.M3Sheet.TEY_V2_FIXTURE) {
    return window.M3Sheet.TEY_V2_FIXTURE;
  }
  return DEMO_CHARACTER;
}

function _missingDepFallback(p, depName, onClose) {
  var closeBtnProps = {
    style: {
      marginTop: 16, padding: '6px 14px',
      background: p.red, color: p.skyDeep,
      border: 'none', cursor: 'pointer',
      fontSize: 10, letterSpacing: 2, fontWeight: 700,
    },
  };
  if (typeof onClose === 'function') {
    closeBtnProps.onClick = onClose;
  }
  return htmlEl('div', {
    'data-missing-dep': depName,
    style: {
      position: 'absolute', inset: 0, zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexDirection: 'column', gap: 8,
      background: 'rgba(0,0,0,0.85)',
      color: p.inkBright,
    },
  }, [
    htmlEl('div', {
      style: { fontSize: 14, letterSpacing: 2, color: p.amber },
    }, [depName + ' NOT LOADED']),
    htmlEl('div', {
      style: { fontSize: 10, color: p.inkDim, letterSpacing: 1 },
    }, ['window.' + depName + ' is required for this popup']),
    htmlEl('button', closeBtnProps, ['CLOSE']),
  ]);
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3AssembledClient = {
  SCHEMA_VERSION: 1,

  // Wiring
  init: init,

  // Top-level
  create:                 create,
  buildAssembledClient:   buildAssembledClient,

  // Sub-builders (public for caller composition)
  buildStatusBar:         buildStatusBar,
  buildLeftHUD:           buildLeftHUD,
  buildCenterFeed:        buildCenterFeed,
  buildCommsTabs:         buildCommsTabs,
  buildRightCartridge:    buildRightCartridge,
  buildMiniMap:           buildMiniMap,
  buildMiniInv:           buildMiniInv,
  buildMiniJobs:          buildMiniJobs,
  buildMiniLore:          buildMiniLore,
  buildCommandStrip:      buildCommandStrip,

  // Fixtures
  DEMO_CHARACTER:         DEMO_CHARACTER,

  _internal: {
    _htmlEl: htmlEl,
    _svgEl:  svgEl,
    _buildMapPopupModal: _buildMapPopupModal,
  },
};

})();
