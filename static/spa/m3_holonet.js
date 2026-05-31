/* ============================================================================
   m3_holonet.js — Holonet news / world-state surface.

   Drop 4.10 · Tier 1 #4 · ported from map_v3/holonet.jsx (653 JSX LOC)
   in SW_MUSH_UIUX_Bugfix_26May26.zip (May 27 2026).

   Per design canon vision §6.10: Director AI emits ambient events,
   news, faction movements, anomalies. The ticker is a live feed; the
   browser is the catalog.

   Two surfaces ship together:
     · HolonetTicker  — single-line marquee for the shell sidebar
     · HolonetBrowser — full popup browser (modal like Holocron)
                       with featured story + 142-story feed +
                       category filter + world-events sidebar

   What this module ships:
     · M3Holonet.buildHolonetTicker(p, hooks?)        single-line marquee
     · M3Holonet.buildHolonetBrowser(p, hooks?)       standalone container
     · M3Holonet.buildHolonetBrowserModal(p, hooks?)  popup with chrome
     · M3Holonet.buildHolonetBrowserBody(p, hooks?)   3-column body
     · M3Holonet.buildFeaturedStory(p, story, hooks?) hero card
     · M3Holonet.buildGunshipSketch(p)                SVG sketch
     · M3Holonet.buildNewsRow(p, story, hooks?)       single feed row
     · M3Holonet.buildWorldEventsPanel(p, events)     RIGHT · live world state
     · M3Holonet.buildFactionMovementsPanel(p, moves) RIGHT · delta list
     · M3Holonet.buildDirectorAINote(p, note?)        RIGHT · AI commentary
     · M3Holonet.HOLONET_DATA_FIXTURE                 demo data
     · M3Holonet.HOLONET_CATEGORIES                   left-column category list

   B3 era-cleanness:
     · Headline + deck reference Ryloth / Venator-class / 91st Recon /
       CIS Lessu Garrison — Clone Wars era native.
     · Ticker mentions Geonosis (CW battlefield), Krayt dragon (Tatooine
       lore), Bail Organa + Senator Organa (CW senator), Hutt Cartel,
       Mos Espa Boonta Eve, Black Sun, Nar Shaddaa — all CW-era.
     · Zero `Empire`/`Imperial` references in the data block. The
       featured story explicitly tags '20 BBY' as the active year.

   Q1 canonical-character policy note (architecture v50 §6.2):
     The fixture preserves the JSX source's Mace Windu reference (in
     the featured deck "General Mace Windu en route" and a faction-
     movements label "Static · M. Windu deployed"). Per v50 Q1 the
     production swap-in must replace these strings — fictional original
     NPCs ("General Var Velo en route"), or absence-framing ("Republic
     command staff en route"). Flagged in the test suite + handoff for
     pre-production cleanup. Drop 4.10 preserves source-fidelity at
     the scaffold level; this is consistent with Drops 4.6 (sheet has
     Jabba in connections) and 4.7 (holocron stat-block leaders).

   Dependencies (loaded earlier in the SPA load order):
     · window.M3AssetsIcons.FACTION_ICONS (m3_assets_icons.js Drop 4.1c)
       — consumed by FactionMovementsPanel for per-faction icons. Falls
       back to a small placeholder if the asset module isn't loaded or
       a given faction-id isn't found.

   What this module does NOT ship:
     · Live ticker animation logic. The CSS @keyframes `tickerScroll`
       is consumed from client.html's stylesheet (defined alongside
       `combatPulse`, `holoFade`, `holoPop`). If the keyframe isn't
       present, the ticker still renders but doesn't scroll.
     · Real-time feed updates. Caller supplies a `data` hook with
       fresh news entries; module is stateless per render.
     · Search functionality. The search bar is presentational.
     · Live category-filter behavior. `onCategoryClick(id)` fires but
       the caller is responsible for re-rendering with filtered data.

   Loading order in client.html: after m3_assets_icons.js. Placed
   alongside m3_cockpit.js in the SPA script-tag block.
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

// ─── htmlEl / svgEl: same shape as Drops 4.5-4.9 ─────────────────────
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
// (Preserves the bug-fix-sprint JSX source verbatim. Production
//  swap-in replaces canonical-character references per v50 Q1.)
// ════════════════════════════════════════════════════════════════════
var HOLONET_DATA_FIXTURE = {
  ticker: [
    { cat: 'WAR',     text: 'Separatist forces clash with Republic gunships near Geonosis',  priority: 'high' },
    { cat: 'LOCAL',   text: 'Krayt dragon sighted north of Anchorhead — Tusken activity up', priority: 'med'  },
    { cat: 'BOUNTY',  text: 'Jabba the Hutt issues 18,000 cr bounty on Sullustan smuggler',  priority: 'med'  },
    { cat: 'WEATHER', text: 'SANDSTORM WARNING · Dune Sea · 6-hour duration · evac advised', priority: 'high' },
    { cat: 'POLITICS', text: 'Senator Bail Organa decries Outer Rim siege tactics',          priority: 'low'  },
    { cat: 'TRADE',   text: 'Hutt Cartel raises spice tariff 12% Outer Rim sector-wide',     priority: 'med'  },
  ],
  featured: {
    headline: 'REPUBLIC CRUISERS CONVERGE ON RYLOTH AS CIS GROUND ASSAULT STALLS',
    deck: 'Three Venator-class Star Destroyers arrive in Ryloth orbit with the 91st ' +
          'Reconnaissance Corps. CIS forces dug in at Lessu reportedly running low on ' +
          'droid stockpiles. General Mace Windu en route.',
    location: 'RYLOTH · 12 ARKANIS HOURS AGO',
    related: ['Ryloth', '91st Recon', 'Mace Windu', 'CIS Lessu Garrison'],
    image: 'gunship',
  },
  feed: [
    { cat: 'WAR', priority: 'high', time: '02:14',
      title: 'Republic cruisers converge on Ryloth',
      summary: 'Three Venators arrive. CIS forces digging in at Lessu reportedly running low on droid stockpiles.',
      tags: ['ryloth', 'republic', 'cis'],
      readers: 4127 },
    { cat: 'LOCAL', priority: 'med', time: '00:42',
      title: 'Krayt dragon sighted north of Anchorhead',
      summary: "Moisture farmers report tracks 'larger than a sandcrawler.' Outpost militia mustering.",
      tags: ['tatooine', 'anchorhead', 'krayt'],
      readers: 89, hot: true },
    { cat: 'BOUNTY', priority: 'med', time: '03:18',
      title: 'Hutt Cartel: 18,000 cr bounty on Vex Drago',
      summary: 'Sullustan smuggler wanted alive for double-crossing Jabba Desilijic on the Kessel run.',
      tags: ['jabba', 'bounty-guild', 'kessel'],
      readers: 612, you: true },
    { cat: 'WEATHER', priority: 'high', time: '00:08',
      title: 'SANDSTORM · Dune Sea · 6-hour duration',
      summary: 'Dust front 200 km wide approaching from the deep desert. Travel suspended past Tosche Station.',
      tags: ['tatooine', 'weather'],
      readers: 230 },
    { cat: 'WAR', priority: 'low', time: '06:00',
      title: 'Senator Organa decries siege tactics',
      summary: "Alderaanian senator's HoloNet address calls for 'restraint' in Outer Rim campaigns. Republic Senate session ongoing.",
      tags: ['organa', 'republic', 'senate'],
      readers: 1840 },
    { cat: 'TRADE', priority: 'med', time: '08:50',
      title: 'Hutt Cartel raises spice tariff 12%',
      summary: 'All-Outer Rim adjustment effective immediately. Independent transporters protest.',
      tags: ['hutt-cartel', 'spice', 'trade'],
      readers: 2100 },
    { cat: 'AMBIENT', priority: 'low', time: '11:32',
      title: 'Mos Espa pod race tournament announced',
      summary: 'Boonta Eve Classic registration opens in 14 days. Purse: 50,000 cr.',
      tags: ['mos-espa', 'gambling'],
      readers: 388 },
    { cat: 'FACTION', priority: 'med', time: '09:11',
      title: 'Black Sun couriers active on Nar Shaddaa',
      summary: 'Bounty Guild flagging increased neuranium movement. Quiet war in the lower levels.',
      tags: ['black-sun', 'nar-shaddaa', 'rumor'],
      readers: 410 },
  ],
  worldEvents: [
    { kind: 'anomaly', tier: 3, name: 'Krayt Dragon',    loc: 'Dune Sea', status: 'ACTIVE',    color: 'gold'  },
    { kind: 'contest',          name: "Jabba's Palace Approach", loc: 'Dune Sea', status: 'CONTESTED', color: 'red'   },
    { kind: 'weather',          name: 'Sandstorm',       loc: 'Dune Sea', status: '6H WINDOW', color: 'amber' },
    { kind: 'anomaly', tier: 2, name: 'Republic Patrol', loc: 'Jundland', status: 'ACTIVE',    color: 'red'   },
    { kind: 'event',            name: 'Boonta Eve Race', loc: 'Mos Espa', status: 'UPCOMING',  color: 'cyan'  },
  ],
  factionMovements: [
    { faction: 'republic',  delta: 12,  label: 'Increased patrols · Ryloth' },
    { faction: 'cis',       delta: -8,  label: 'Withdrawing from Lessu' },
    { faction: 'hutt',      delta: 6,   label: 'Tariff increase · spice' },
    { faction: 'bounty',    delta: 3,   label: 'Tatooine contracts surge' },
    { faction: 'jedi',      delta: 0,   label: 'Static · M. Windu deployed' },
    { faction: 'black_sun', delta: 2,   label: 'Quiet expansion · Nar Shaddaa' },
  ],
};

// LEFT-column category nav (count totals demo-canonical; production
// would compute from the live feed)
var HOLONET_CATEGORIES = [
  { id: 'all',      label: 'ALL FEEDS', count: 142, active: true },
  { id: 'WAR',      label: 'WAR',       count: 38  },
  { id: 'LOCAL',    label: 'LOCAL',     count: 24  },
  { id: 'BOUNTY',   label: 'BOUNTY',    count: 17  },
  { id: 'TRADE',    label: 'TRADE',     count: 21  },
  { id: 'POLITICS', label: 'POLITICS',  count: 13  },
  { id: 'WEATHER',  label: 'WEATHER',   count: 8   },
  { id: 'FACTION',  label: 'FACTION',   count: 11  },
  { id: 'AMBIENT',  label: 'AMBIENT',   count: 10  },
];

// ════════════════════════════════════════════════════════════════════
// HOLONET TICKER — single-line scrolling marquee
// ════════════════════════════════════════════════════════════════════
function buildHolonetTicker(p, hooks) {
  hooks = hooks || {};
  var height  = hooks.height  || 24;
  var items   = (hooks.data && hooks.data.ticker) || HOLONET_DATA_FIXTURE.ticker;
  var onOpen  = hooks.onOpen || null;

  // Label cluster (left-anchored amber chip)
  var labelChip = htmlEl('div', {
    'data-ticker-label': '1',
    style: {
      padding: '0 10px', height: '100%',
      display: 'flex', alignItems: 'center', gap: 6,
      background: p.amber + '22',
      borderRight: '1px solid ' + p.amber + '66',
      zIndex: 5, flexShrink: 0,
    }
  }, [
    htmlEl('div', {
      style: {
        width: 5, height: 5, borderRadius: '50%', background: p.amber,
        boxShadow: '0 0 4px ' + p.amber,
        animation: 'combatPulse 2.4s ease-in-out infinite',
      }
    }),
    htmlEl('span', {
      style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 700 }
    }, ['HOLONET']),
  ]);

  // Build a single ticker item (priority-colored chip + text)
  function buildTickerItem(it) {
    var c = (it.priority === 'high') ? p.red
          : (it.priority === 'med')  ? p.amber
          :                            p.inkDim;
    return htmlEl('span', {
      'data-ticker-item-cat': it.cat,
      'data-ticker-item-priority': it.priority,
      style: {
        display: 'inline-flex', alignItems: 'center', gap: 8, padding: '0 24px',
        borderRight: '1px solid ' + p.inkFaint,
        fontSize: 11, color: p.ink,
      }
    }, [
      htmlEl('span', {
        style: {
          fontSize: 8, color: c, letterSpacing: 1.5, fontWeight: 700,
          padding: '1px 5px', border: '1px solid ' + c,
        }
      }, [it.cat]),
      htmlEl('span', { style: { color: p.inkBright } }, [it.text]),
    ]);
  }

  // Doubled item list for seamless marquee loop
  var doubled = items.concat(items).map(buildTickerItem);

  var scrollTrack = htmlEl('div', {
    'data-ticker-track': '1',
    style: {
      display: 'flex', alignItems: 'center', whiteSpace: 'nowrap', height: '100%',
      animation: 'tickerScroll 80s linear infinite',
    }
  }, doubled);

  var scrollMask = htmlEl('div', {
    style: {
      flex: 1, position: 'relative', overflow: 'hidden', height: '100%',
      WebkitMaskImage: 'linear-gradient(90deg, transparent 0%, black 4%, black 96%, transparent 100%)',
      maskImage: 'linear-gradient(90deg, transparent 0%, black 4%, black 96%, transparent 100%)',
    }
  }, [scrollTrack]);

  var children = [labelChip, scrollMask];

  // Optional expand affordance
  if (onOpen) {
    children.push(htmlEl('div', {
      'data-ticker-open-hint': '1',
      style: {
        padding: '0 10px', height: '100%',
        display: 'flex', alignItems: 'center', gap: 6,
        borderLeft: '1px solid ' + p.inkFaint,
        fontSize: 9, color: p.inkDim, letterSpacing: 2,
      }
    }, ['⤢ OPEN']));
  }

  var props = {
    'data-holonet-ticker': '1',
    style: {
      width: '100%', height: height,
      position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', ' + p.sky + ')',
      borderTop:    '1px solid ' + p.amber + '55',
      borderBottom: '1px solid ' + p.inkFaint,
      fontFamily: "'IBM Plex Mono', monospace",
      cursor: onOpen ? 'pointer' : 'default',
      display: 'flex', alignItems: 'center',
    }
  };
  if (typeof onOpen === 'function') props.onClick = onOpen;

  return htmlEl('div', props, children);
}

// ════════════════════════════════════════════════════════════════════
// GUNSHIP SKETCH — featured-story SVG (LAAT silhouette)
// ════════════════════════════════════════════════════════════════════
function buildGunshipSketch(p) {
  var defs = svgEl('defs', null, [
    svgEl('radialGradient', { id: 'gs-glow', cx: '50%', cy: '50%', r: '50%' }, [
      svgEl('stop', { offset: '0%',   'stop-color': p.amber, 'stop-opacity': 0.3 }),
      svgEl('stop', { offset: '100%', 'stop-color': p.amber, 'stop-opacity': 0   }),
    ]),
  ]);
  var atmosphericGlow = svgEl('rect', {
    x: 0, y: 0, width: 160, height: 100, fill: 'url(#gs-glow)'
  });

  // LAAT gunship silhouette
  var fuselageGroup = svgEl('g', { transform: 'translate(80 52)' }, [
    svgEl('path', {
      d: 'M -40 0 L -30 -8 L 30 -8 L 40 0 L 30 8 L -30 8 Z',
      fill: p.skyDeep, stroke: p.cyan, strokeWidth: 1.2,
    }),
    svgEl('path', {
      d: 'M -30 -8 L -50 -22 L -42 -22 L -22 -8 Z',
      fill: p.skyDeep, stroke: p.cyan, strokeWidth: 1,
    }),
    svgEl('path', {
      d: 'M 30 -8 L 50 -22 L 42 -22 L 22 -8 Z',
      fill: p.skyDeep, stroke: p.cyan, strokeWidth: 1,
    }),
    svgEl('path', {
      d: 'M -30 8 L -50 22 L -42 22 L -22 8 Z',
      fill: p.skyDeep, stroke: p.cyan, strokeWidth: 1,
    }),
    svgEl('path', {
      d: 'M 30 8 L 50 22 L 42 22 L 22 8 Z',
      fill: p.skyDeep, stroke: p.cyan, strokeWidth: 1,
    }),
    svgEl('circle', { cx: -32, cy: 0, r: 3, fill: p.cyan, opacity: 0.7 }),
    svgEl('circle', { cx: 40,  cy: 0, r: 4, fill: p.amber, opacity: 0.8 }),
    svgEl('circle', {
      cx: 36, cy: 0, r: 2.5, fill: p.amber, opacity: 1,
      style: { filter: 'drop-shadow(0 0 4px ' + p.amber + ')' },
    }),
  ]);

  // Lower fire streaks
  var fireStreaks = [
    svgEl('line', { x1: 20, y1: 88, x2: 50, y2: 88, stroke: p.amber, strokeWidth: 1.2, opacity: 0.6 }),
    svgEl('line', { x1: 110, y1: 88, x2: 140, y2: 88, stroke: p.amber, strokeWidth: 1.2, opacity: 0.6 }),
  ];

  return svgEl('svg', {
    viewBox: '0 0 160 100', width: '100%', height: '100%',
    'data-holonet-gunship-sketch': '1',
  }, [defs, atmosphericGlow, fuselageGroup].concat(fireStreaks));
}

// ════════════════════════════════════════════════════════════════════
// FEATURED STORY — hero card at top of feed
// ════════════════════════════════════════════════════════════════════
function buildFeaturedStory(p, story, hooks) {
  hooks = hooks || {};
  var onRelatedClick = hooks.onRelatedClick || null;

  var relatedTags = (story.related || []).map(function(tag) {
    var tagProps = {
      'data-related-tag': tag,
      style: {
        fontSize: 9, letterSpacing: 1.5,
        padding: '2px 6px',
        color: p.cyan, border: '1px solid ' + p.cyan + '55',
        background: p.cyan + '11',
        cursor: 'pointer',
      }
    };
    if (typeof onRelatedClick === 'function') {
      tagProps.onClick = function() { onRelatedClick(tag); };
    }
    return htmlEl('span', tagProps, ['↪ ' + tag]);
  });

  var textColumn = htmlEl('div', null, [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 700 }
    }, ['★ FEATURED · LIVE']),
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk', sans-serif",
        fontSize: 22, fontWeight: 700, color: p.inkBright,
        letterSpacing: 1, lineHeight: 1.15, marginTop: 6,
        textShadow: '0 0 6px ' + p.amber + '33',
      }
    }, [story.headline]),
    htmlEl('div', {
      style: {
        fontFamily: "'IBM Plex Sans', sans-serif",
        fontSize: 13, lineHeight: 1.6, color: p.ink, marginTop: 8,
      }
    }, [story.deck]),
    htmlEl('div', {
      style: { fontSize: 9, color: p.inkDim, letterSpacing: 2, marginTop: 8 }
    }, [story.location]),
    htmlEl('div', {
      style: { display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 8 }
    }, relatedTags),
  ]);

  // Sketch column (LAAT or fallback)
  var sketchColumn = htmlEl('div', {
    style: {
      background: p.skyDeep, border: '1px solid ' + p.inkFaint,
      padding: 8, height: 130,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }
  }, [buildGunshipSketch(p)]);

  return htmlEl('div', {
    'data-holonet-featured': '1',
    style: {
      padding: 14,
      background: 'linear-gradient(135deg, ' + p.amber + '15, transparent 60%)',
      border: '1px solid ' + p.amber + '55',
      borderLeft: '4px solid ' + p.amber,
    }
  }, [
    htmlEl('div', {
      style: { display: 'grid', gridTemplateColumns: '1fr 180px', gap: 16 }
    }, [textColumn, sketchColumn]),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// NEWS ROW — single feed row
// ════════════════════════════════════════════════════════════════════
function buildNewsRow(p, story, hooks) {
  hooks = hooks || {};
  var onClick = hooks.onStoryClick || null;
  var catColors = {
    WAR:      p.red,
    LOCAL:    p.amber,
    BOUNTY:   p.gold || p.amber,
    TRADE:    p.green,
    POLITICS: p.cyan,
    WEATHER:  p.amber,
    FACTION:  p.cyan,
    AMBIENT:  p.inkDim,
  };
  var c = catColors[story.cat] || p.amber;

  // Category + time column
  var catTimeCol = htmlEl('div', null, [
    htmlEl('span', {
      'data-news-cat-chip': story.cat,
      style: {
        fontSize: 8, letterSpacing: 1.5, color: c, fontWeight: 700,
        padding: '1px 4px', border: '1px solid ' + c + '55',
      }
    }, [story.cat]),
    htmlEl('div', {
      style: { fontSize: 9, color: p.inkDim, marginTop: 4, letterSpacing: 1 }
    }, [story.time + ' ago']),
  ]);

  // Title with hot / following badges
  var titleChildren = [story.title];
  if (story.hot) {
    titleChildren.push(htmlEl('span', {
      'data-news-hot-badge': '1',
      style: {
        marginLeft: 8, fontSize: 8, color: p.red, letterSpacing: 1.5, fontWeight: 700,
        padding: '1px 4px', border: '1px solid ' + p.red,
        animation: 'combatPulse 1.4s ease-in-out infinite',
      }
    }, ['● HOT']));
  }
  if (story.you) {
    titleChildren.push(htmlEl('span', {
      'data-news-following-badge': '1',
      style: {
        marginLeft: 8, fontSize: 8, color: p.green, letterSpacing: 1.5, fontWeight: 700,
        padding: '1px 4px', border: '1px solid ' + p.green,
      }
    }, ['★ FOLLOWING']));
  }

  var tagChildren = (story.tags || []).map(function(t) {
    return htmlEl('span', {
      style: { fontSize: 8.5, color: p.inkDim, letterSpacing: 0.5 }
    }, ['#' + t]);
  });

  var titleSummaryCol = htmlEl('div', null, [
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk', sans-serif",
        fontSize: 14, color: p.inkBright, fontWeight: 600,
        lineHeight: 1.3,
      }
    }, titleChildren),
    htmlEl('div', {
      style: {
        fontFamily: "'IBM Plex Sans', sans-serif",
        fontSize: 12, color: p.ink, lineHeight: 1.5, marginTop: 3, opacity: 0.85,
      }
    }, [story.summary]),
    htmlEl('div', {
      style: { display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }
    }, tagChildren),
  ]);

  // Readers column
  var readersFormatted = (typeof story.readers === 'number')
                         ? story.readers.toLocaleString()
                         : String(story.readers || '');
  var readersCol = htmlEl('div', {
    style: { textAlign: 'right', fontSize: 9, color: p.inkDim, letterSpacing: 1 }
  }, [
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 13, color: p.ink, fontWeight: 600,
      }
    }, [readersFormatted]),
    htmlEl('div', null, ['READERS']),
  ]);

  var rowProps = {
    'data-news-row-cat': story.cat,
    'data-news-row-title': story.title,
    style: {
      padding: '10px 0',
      borderBottom: '1px dashed ' + p.inkFaint,
      display: 'grid', gridTemplateColumns: '70px 1fr 90px',
      gap: 12, alignItems: 'baseline',
      cursor: 'pointer',
    }
  };
  if (typeof onClick === 'function') {
    rowProps.onClick = function() { onClick(story); };
  }
  return htmlEl('div', rowProps, [catTimeCol, titleSummaryCol, readersCol]);
}

// ════════════════════════════════════════════════════════════════════
// WORLD EVENTS PANEL — RIGHT column
// ════════════════════════════════════════════════════════════════════
function buildWorldEventsPanel(p, events) {
  var colors = {
    gold: p.gold || p.amber, red: p.red, amber: p.amber,
    cyan: p.cyan, green: p.green,
  };
  var rows = (events || []).map(function(e) {
    var c = colors[e.color] || p.amber;
    var kindGlyph;
    if (e.kind === 'anomaly') {
      kindGlyph = htmlEl('span', { style: { color: c, marginRight: 4 } },
                          ['●' + (e.tier ? ('T' + e.tier) : '')]);
    } else if (e.kind === 'contest') {
      kindGlyph = htmlEl('span', { style: { color: c, marginRight: 4 } }, ['⚔']);
    } else if (e.kind === 'weather') {
      kindGlyph = htmlEl('span', { style: { color: c, marginRight: 4 } }, ['≈']);
    } else if (e.kind === 'event') {
      kindGlyph = htmlEl('span', { style: { color: c, marginRight: 4 } }, ['★']);
    } else {
      kindGlyph = htmlEl('span', { style: { color: c, marginRight: 4 } }, ['●']);
    }

    return htmlEl('div', {
      'data-world-event-name': e.name,
      'data-world-event-kind': e.kind,
      style: {
        padding: '6px 8px',
        background: 'rgba(0,0,0,0.4)',
        borderLeft: '3px solid ' + c,
      }
    }, [
      htmlEl('div', {
        style: {
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
          fontSize: 11, color: p.inkBright,
        }
      }, [
        htmlEl('span', { style: { fontWeight: 600 } }, [kindGlyph, e.name]),
        htmlEl('span', {
          style: { fontSize: 8.5, color: c, letterSpacing: 1.5, fontWeight: 600 }
        }, [e.status]),
      ]),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, marginTop: 2 }
      }, [e.loc]),
    ]);
  });

  return htmlEl('div', {
    'data-holonet-world-events': '1'
  }, [
    htmlEl('div', {
      style: {
        fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 700, marginBottom: 8,
      }
    }, ['▮▮ LIVE GALAXY STATE']),
    htmlEl('div', {
      style: { display: 'flex', flexDirection: 'column', gap: 4 }
    }, rows),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// FACTION MOVEMENTS PANEL — RIGHT column
// ════════════════════════════════════════════════════════════════════
function buildFactionMovementsPanel(p, moves) {
  var FACTION_ICONS = (window.M3AssetsIcons && window.M3AssetsIcons.FACTION_ICONS) || {};

  var rows = (moves || []).map(function(m) {
    var iconFn = FACTION_ICONS[m.faction] || FACTION_ICONS.republic;
    var iconEl;
    if (typeof iconFn === 'function') {
      try { iconEl = iconFn({ c: p.amber, size: 16 }); }
      catch (e) { iconEl = htmlEl('span', { style: { color: p.amber } }, ['•']); }
    } else {
      iconEl = htmlEl('span', { style: { color: p.amber } }, ['•']);
    }
    // Defensive: ensure DOM node, not React element
    if (iconEl && !iconEl.nodeType) {
      iconEl = htmlEl('span', { style: { color: p.amber } }, ['•']);
    }

    var deltaColor = (m.delta > 0) ? p.green
                   : (m.delta < 0) ? p.red
                   :                 p.inkDim;
    var deltaText = (m.delta > 0 ? '+' : '') + String(m.delta);

    return htmlEl('div', {
      'data-faction-movement': m.faction,
      style: {
        display: 'grid', gridTemplateColumns: '20px 1fr auto',
        gap: 6, alignItems: 'center',
        padding: '4px 6px',
        background: 'rgba(0,0,0,0.35)',
        border: '1px solid ' + p.inkFaint,
      }
    }, [
      iconEl,
      htmlEl('div', null, [
        htmlEl('div', {
          style: {
            fontSize: 10, color: p.ink, letterSpacing: 0.5,
            textTransform: 'capitalize',
          }
        }, [m.faction.replace('_', ' ')]),
        htmlEl('div', {
          style: { fontSize: 9, color: p.inkDim }
        }, [m.label]),
      ]),
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 14,
          color: deltaColor, fontWeight: 700,
        }
      }, [deltaText]),
    ]);
  });

  return htmlEl('div', {
    'data-holonet-faction-movements': '1'
  }, [
    htmlEl('div', {
      style: {
        fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 700, marginBottom: 8,
      }
    }, ['▮▮ FACTION MOVEMENTS · 24H']),
    htmlEl('div', {
      style: { display: 'flex', flexDirection: 'column', gap: 3 }
    }, rows),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// DIRECTOR AI NOTE — RIGHT column commentary
// ════════════════════════════════════════════════════════════════════
function buildDirectorAINote(p, note) {
  // Default note text matches the JSX source.
  var defaultText = 'World tension up 8% in last hour. Outer Rim sees ' +
                    'increased CIS recon activity. Hutt Cartel reacting with ' +
                    'tariff adjustments. Consider declaring before next session lock.';
  var defaultTimestamp = '14:32';
  var n = note || {};
  var text      = n.text      || defaultText;
  var timestamp = n.timestamp || defaultTimestamp;

  return htmlEl('div', {
    'data-holonet-director-ai': '1',
    style: {
      padding: '8px 10px',
      background: p.cyan + '11',
      border: '1px solid ' + p.cyan + '66',
    }
  }, [
    htmlEl('div', {
      style: {
        fontSize: 9, letterSpacing: 2, color: p.cyan, fontWeight: 600, marginBottom: 4,
      }
    }, ['◇ DIRECTOR AI · ' + timestamp]),
    htmlEl('div', {
      style: {
        fontFamily: "'IBM Plex Sans', sans-serif",
        fontSize: 11, color: p.ink, lineHeight: 1.5,
      }
    }, [text]),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// CATEGORY FILTER — LEFT column (category list + filter checkboxes)
// ════════════════════════════════════════════════════════════════════
function buildCategoryFilter(p, categories, hooks) {
  hooks = hooks || {};
  var onCategoryClick = hooks.onCategoryClick || null;
  var onFilterToggle  = hooks.onFilterToggle  || null;

  var cats = categories || HOLONET_CATEGORIES;
  var catRows = cats.map(function(cat) {
    var rowProps = {
      'data-category-id': cat.id,
      style: {
        padding: '6px 10px', marginBottom: 2,
        background: cat.active ? (p.amber + '22') : 'transparent',
        borderLeft: cat.active ? ('2px solid ' + p.amber) : '2px solid transparent',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        cursor: 'pointer',
        fontSize: 10,
      }
    };
    if (typeof onCategoryClick === 'function') {
      rowProps.onClick = function() { onCategoryClick(cat.id); };
    }
    return htmlEl('div', rowProps, [
      htmlEl('span', {
        style: { color: cat.active ? p.inkBright : p.ink, letterSpacing: 1.5 }
      }, [cat.label]),
      htmlEl('span', {
        style: { color: p.inkDim, fontSize: 9 }
      }, [String(cat.count)]),
    ]);
  });

  // Filter checkboxes (4 demo filters from the JSX source)
  var filterRows = ['Following you', 'Near you', 'High priority', 'Faction-relevant']
    .map(function(f, idx) {
      var checked = (idx === 0);
      var labelProps = {
        'data-filter-label': f,
        style: {
          display: 'flex', alignItems: 'center', gap: 6,
          fontSize: 10, color: p.ink, cursor: 'pointer',
        }
      };
      if (typeof onFilterToggle === 'function') {
        labelProps.onClick = function() { onFilterToggle(f); };
      }
      return htmlEl('label', labelProps, [
        htmlEl('span', {
          style: {
            width: 10, height: 10, border: '1px solid ' + p.inkDim,
            background: checked ? p.amber : 'transparent',
          }
        }),
        f,
      ]);
    });

  return htmlEl('div', {
    'data-holonet-category-filter': '1',
    style: {
      borderRight: '1px solid ' + p.inkDim,
      background: 'rgba(0,0,0,0.3)',
      overflowY: 'auto', padding: '14px 12px',
    }
  }, [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600, marginBottom: 8 }
    }, ['▮ CATEGORIES']),
    htmlEl('div', null, catRows),
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600, margin: '18px 0 8px' }
    }, ['▮ FILTERS']),
    htmlEl('div', {
      style: { display: 'flex', flexDirection: 'column', gap: 4 }
    }, filterRows),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// HOLONET BROWSER BODY — the 3-column body used by both modal and standalone
// ════════════════════════════════════════════════════════════════════
function buildHolonetBrowserBody(p, hooks) {
  hooks = hooks || {};
  var data = hooks.data || HOLONET_DATA_FIXTURE;
  var width  = hooks.width  || 1280;
  var height = hooks.height || 920;

  var ticker = buildHolonetTicker(p, {
    height: 24,
    data: data,
    onOpen: null, // already in browser — no "OPEN" affordance
  });

  // Header
  var holonetGlyph = svgEl('svg', {
    width: 36, height: 36, viewBox: '0 0 36 36',
    style: { filter: 'drop-shadow(0 0 6px ' + p.amber + ')' }
  }, [
    svgEl('circle',  { cx: 18, cy: 18, r: 16,           fill: 'none', stroke: p.amber, strokeWidth: 1.5 }),
    svgEl('ellipse', { cx: 18, cy: 18, rx: 16, ry: 6,   fill: 'none', stroke: p.amber, strokeWidth: 1.2 }),
    svgEl('ellipse', { cx: 18, cy: 18, rx: 6,  ry: 16,  fill: 'none', stroke: p.amber, strokeWidth: 1.2 }),
    svgEl('circle',  { cx: 18, cy: 18, r: 3,            fill: p.amber }),
  ]);

  var headerLeft = htmlEl('div', {
    style: { display: 'flex', alignItems: 'flex-start', gap: 14 }
  }, [
    holonetGlyph,
    htmlEl('div', null, [
      htmlEl('div', {
        style: { fontSize: 10, letterSpacing: 4, color: p.inkDim }
      }, ['HOLONET · GALACTIC NEWS NETWORK']),
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk', sans-serif",
          fontSize: 22, color: p.inkBright, letterSpacing: 2, fontWeight: 700,
          marginTop: 2, textShadow: '0 0 6px ' + p.amber + '55',
        }
      }, ['FRONT PAGE']),
      htmlEl('div', {
        style: { fontSize: 9, letterSpacing: 2, color: p.inkDim, marginTop: 2 }
      }, ['CW-ERA · 20 BBY · UPDATED 4 MIN AGO']),
    ]),
  ]);

  var headerSearch = htmlEl('div', {
    style: {
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 12px', minWidth: 260,
      background: p.skyDeep, border: '1px solid ' + p.inkDim,
    }
  }, [
    htmlEl('span', { style: { color: p.amber, fontSize: 14 } }, ['⌕']),
    htmlEl('span', {
      style: { color: p.inkDim, fontSize: 11, flex: 1 }
    }, ['Search galactic news…']),
    htmlEl('span', { style: { color: p.inkFaint, fontSize: 9 } }, ['⌘K']),
  ]);

  var header = htmlEl('div', {
    'data-holonet-header': '1',
    style: {
      padding: '14px 20px',
      background: 'linear-gradient(180deg, ' + p.amber + '11, transparent)',
      borderBottom: '1px solid ' + p.inkDim,
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
    }
  }, [headerLeft, headerSearch]);

  // BODY columns
  var leftCol = buildCategoryFilter(p, hooks.categories, hooks);

  var feedRows = (data.feed || []).map(function(story) {
    return buildNewsRow(p, story, { onStoryClick: hooks.onStoryClick });
  });
  var centerCol = htmlEl('div', {
    'data-holonet-center': '1',
    style: { overflowY: 'auto', padding: '16px 20px' }
  }, [
    buildFeaturedStory(p, data.featured, { onRelatedClick: hooks.onRelatedClick }),
    // Feed header
    htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        marginTop: 24, paddingBottom: 6,
        borderBottom: '1px solid ' + p.inkDim,
      }
    }, [
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 14, color: p.inkBright,
          letterSpacing: 3, fontWeight: 700,
        }
      }, ['LIVE FEED · ' + (data.feed ? data.feed.length : 0) + ' STORIES SHOWN']),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, letterSpacing: 1.5 }
      }, [
        'SORT: ',
        htmlEl('span', { style: { color: p.amber } }, ['RECENT']),
        ' · POPULAR · NEAR YOU',
      ]),
    ]),
    htmlEl('div', {
      'data-holonet-feed': '1',
      style: { marginTop: 10, display: 'flex', flexDirection: 'column', gap: 0 }
    }, feedRows),
  ]);

  var rightCol = htmlEl('div', {
    'data-holonet-right': '1',
    style: {
      borderLeft: '1px solid ' + p.inkDim,
      background: 'rgba(0,0,0,0.3)',
      overflowY: 'auto', padding: '14px 14px',
      display: 'flex', flexDirection: 'column', gap: 14,
    }
  }, [
    buildWorldEventsPanel(p, data.worldEvents),
    buildFactionMovementsPanel(p, data.factionMovements),
    buildDirectorAINote(p, hooks.directorNote),
  ]);

  // BODY container — top offset accounts for 24px ticker + ~92px header
  var bodyTopOffset = 24 + 92;
  var body = htmlEl('div', {
    style: {
      position: 'absolute', top: bodyTopOffset, left: 0, right: 0, bottom: 0,
      display: 'grid', gridTemplateColumns: '180px 1fr 320px',
    }
  }, [leftCol, centerCol, rightCol]);

  return htmlEl('div', {
    'data-holonet-browser-body': '1',
    style: { width: width, height: height, position: 'relative', overflow: 'hidden' }
  }, [ticker, header, body]);
}

// ════════════════════════════════════════════════════════════════════
// HOLONET BROWSER — standalone (no popup chrome)
// ════════════════════════════════════════════════════════════════════
function buildHolonetBrowser(p, hooks) {
  hooks = hooks || {};
  var width  = hooks.width  || 1280;
  var height = hooks.height || 920;
  return htmlEl('div', {
    'data-holonet-browser': 'standalone',
    style: {
      width: width, height: height, position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + p.inkDim,
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      boxShadow: 'inset 0 0 40px ' + p.skyDeep + ', 0 0 0 1px #000, 0 20px 50px rgba(0,0,0,0.7)',
    }
  }, [buildHolonetBrowserBody(p, hooks)]);
}

// ════════════════════════════════════════════════════════════════════
// HOLONET BROWSER MODAL — popup with chrome (matches HolocronModal)
// ════════════════════════════════════════════════════════════════════
function buildHolonetBrowserModal(p, hooks) {
  hooks = hooks || {};
  var width  = hooks.width  || 1080;
  var height = hooks.height || 720;
  var onClose = hooks.onClose || null;

  // Drag-bar with traffic lights
  var redLight = htmlEl('div', {
    style: {
      width: 11, height: 11, borderRadius: '50%',
      background: p.red, cursor: 'pointer',
      boxShadow: '0 0 4px ' + p.red + '88, inset 0 -1px 1px rgba(0,0,0,0.4)',
    }
  });
  if (typeof onClose === 'function') {
    redLight.addEventListener('click', onClose);
  }
  var amberLight = htmlEl('div', {
    style: {
      width: 11, height: 11, borderRadius: '50%',
      background: p.amber, opacity: 0.65,
    }
  });
  var greenLight = htmlEl('div', {
    style: {
      width: 11, height: 11, borderRadius: '50%',
      background: p.green, opacity: 0.65,
    }
  });

  var titleLabel = htmlEl('div', {
    style: {
      position: 'absolute', left: '50%', transform: 'translateX(-50%)',
      fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600,
    }
  }, ['HOLONET']);

  var dragBar = htmlEl('div', {
    'data-holonet-dragbar': '1',
    style: {
      height: 22, padding: '0 10px',
      background: 'linear-gradient(180deg, ' + p.amber + '33, transparent)',
      borderBottom: '1px solid ' + p.amber + '55',
      display: 'flex', alignItems: 'center', gap: 8,
      position: 'relative',
    }
  }, [redLight, amberLight, greenLight, titleLabel]);

  var bodyEl = buildHolonetBrowserBody(p, {
    data: hooks.data,
    width: width, height: height - 22,
    onCategoryClick: hooks.onCategoryClick,
    onFilterToggle:  hooks.onFilterToggle,
    onStoryClick:    hooks.onStoryClick,
    onRelatedClick:  hooks.onRelatedClick,
    categories:      hooks.categories,
    directorNote:    hooks.directorNote,
  });

  var wrap = htmlEl('div', {
    style: {
      width: width, height: height,
      position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + p.amber,
      color: p.ink,
      fontFamily: "'IBM Plex Mono', monospace",
      boxShadow: '0 0 0 1px #000, 0 0 30px ' + p.amber + '55, 0 40px 80px rgba(0,0,0,0.85)',
      animation: 'holoPop 220ms cubic-bezier(.4,.0,.2,1)',
    }
  }, []);
  wrap.addEventListener('click', function(e) { e.stopPropagation(); });
  wrap.appendChild(dragBar);
  wrap.appendChild(bodyEl);

  var backdropProps = {
    'data-holonet-browser': 'modal',
    style: {
      position: 'absolute', inset: 0, zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.5)',
      backdropFilter: 'blur(1px)',
      animation: 'holoFade 200ms ease-out',
    }
  };
  if (typeof onClose === 'function') {
    backdropProps.onClick = function(e) {
      if (e.target === backdrop) onClose();
    };
  }
  var backdrop = htmlEl('div', backdropProps, [wrap]);

  return backdrop;
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3Holonet = {
  SCHEMA_VERSION: 1,

  init:                       init,

  // Top-level
  buildHolonetTicker:         buildHolonetTicker,
  buildHolonetBrowser:        buildHolonetBrowser,
  buildHolonetBrowserModal:   buildHolonetBrowserModal,
  buildHolonetBrowserBody:    buildHolonetBrowserBody,

  // Section builders
  buildFeaturedStory:         buildFeaturedStory,
  buildGunshipSketch:         buildGunshipSketch,
  buildNewsRow:               buildNewsRow,
  buildWorldEventsPanel:      buildWorldEventsPanel,
  buildFactionMovementsPanel: buildFactionMovementsPanel,
  buildDirectorAINote:        buildDirectorAINote,
  buildCategoryFilter:        buildCategoryFilter,

  // Fixtures
  HOLONET_DATA_FIXTURE:       HOLONET_DATA_FIXTURE,
  HOLONET_CATEGORIES:         HOLONET_CATEGORIES,

  _internal: {
    _htmlEl: htmlEl,
    _svgEl:  svgEl,
  },
};

})();
