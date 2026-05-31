/* ============================================================================
   m3_sheet.js — Character sheet renderer (+sheet command surface).

   Drop 4.6 · Tier 1 #4 · ported from map_v3/sheet-v2.jsx (1,195 JSX LOC)
   in SW_MUSH_UIUX_Bugfix_26May26.zip (May 27 2026).

   Bug-fix sprint corrections preserved:
     · B3   Era contamination — no Empire/imperial tags in story sections;
            "Sealed Senate Dispatch", "Distrusts Senate elites and Trade
            Federation profiteers", Senate in the noun-highlight list.
     · B4   Canonical 7-rung wound ladder consumed from window.WOUND_RUNGS
            (which gained a labelLong field for this drop — see client.html
            line 4257 post-4.6). Rungs 1-6 render in the sheet; HEALTHY
            (rung 0) is implicit at tier 0.
     · H4   Force panel restructured per WEG R&E — three skills
            (Control/Sense/Alter) with dice + descriptions + powers list
            tagged with the skill(s) each draws on.
     · H5   FP rendered without an fpMax denominator (WEG R&E does not
            cap FP). DSP still capped at 5 per design conventions.
     · L3   Wound strings consume r.labelLong (no "KILLED" — "DEAD" to
            match engine/character.py WoundLevel(IntEnum).DEAD).
     · L5   "TEY VOSS" — uppercase in the header per design standard.

   What this module ships:
     · M3Sheet.buildCharacterSheet(p, character, currentTab, hooks)
            top-level renderer; consumer controls tab via currentTab arg
            ('VITALS' | 'SKILLS' | 'GEAR' | 'WORLD' | 'STORY' | 'FORCE')
     · M3Sheet.buildCharacterSheetModal(p, character, hooks)
            popup wrapper — backdrop scrim + animated window; renders
            buildCharacterSheet inside with asPopup=true. Caller owns
            the `maxed` state via hooks.maxed; hooks.onMaximize fires
            on the maximize button. Drop 4.12a — added so assembled-
            client can consume it without inventing its own modal.
     · M3Sheet.createCharacterSheetModal(p, character, hooks) → handle
            stateful convenience — owns the `maxed` toggle internally
            and re-renders the modal in place on toggle. Returns
            { element, destroy }. Drop 4.12a — companion to the
            stateless builder; mirrors the Drop 4.8 stateful pattern.
     · M3Sheet.buildSheetHeader(p, character, hooks)
     · M3Sheet.buildSheetVitals(p, character)
     · M3Sheet.buildSheetSkills(p, character)
     · M3Sheet.buildSheetGear(p, character)
     · M3Sheet.buildSheetWorld(p, character)
     · M3Sheet.buildSheetStory(p, character)
     · M3Sheet.buildSheetForce(p, character)
     · M3Sheet.buildPaperDoll(p, loadout)
     · M3Sheet.buildFactionRadar(p, factions)
     · M3Sheet.buildWoundFigure(p, tier, size?)
     · M3Sheet.buildCooldownWheel(p, cd, colorOverride?)
     · M3Sheet.TEY_V2_FIXTURE              demo character data
     · M3Sheet.STORY_NOUNS                 keywords for story-text highlight

   What this module does NOT ship:
     · Tab-state management (caller's job). The JSX uses React.useState
       to track the active tab; vanilla version exposes currentTab as an
       arg to buildCharacterSheet and a hooks.onTabClick(id) callback.
       Caller re-renders on tab change.
     · Live wire-in to the existing +sheet command. The existing sheet
       rendering in client.html (lines 8425+) stays in place; this
       module is scaffold for the eventual swap-in.
     · Inline editing of background/personality/objectives. The JSX
       shows EDIT buttons but no edit-mode UI; that's a separate drop.
     · CP-spend skill-advancement workflow. Buttons render but click
       wiring is a separate drop.

   Dependencies (loaded earlier in the SPA load order):
     · window.WOUND_RUNGS (from client.html — gained labelLong field
       in Drop 4.6 to satisfy B4)
     · window.M3AssetsIcons.FACTION_ICONS (from m3_assets_icons.js
       Drop 4.1c)

   Loading order in client.html: after m3_assets_icons.js (uses
   FACTION_ICONS) and AFTER the WOUND_RUNGS declaration (client.html
   inline IIFE, line 4257). Placed alongside m3_combat_theater.js in
   the SPA script-tag block.
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

// ─── htmlEl / svgEl: same shape as m3_combat_theater.js (Drop 4.5) ───
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

// ─── Shared Section helper ──────────────────────────────────────────
// JSX: <Section p={p} title="X">{children}</Section>
// Vanilla: Section(p, 'X', [child1, child2, ...]) → <div>
function Section(p, title, children) {
  var header = htmlEl('div', {
    style: {
      fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 700,
      marginBottom: 8,
    }
  }, ['▮▮ ' + title]);
  return htmlEl('div', null, [header].concat(children || []));
}

// ─── B3 story-noun highlight list ───────────────────────────────────
// Preserves the bug-fix-sprint correction: Senate present, no Empire/
// Imperial. Words used in the Clone Wars era; the SHIPPING era at this
// build is 20 BBY per active_era pivot.
var STORY_NOUNS = [
  'Corellian', 'Corellia', 'Kessel', 'Jabba Desilijic Tiure', 'Jabba',
  'Hutt', 'Republic', 'CIS', 'Mak Torrin', 'Senate', 'Mynock', 'Yenn Karac',
  'Anchorhead', 'Outer Rim', 'Mos Eisley'
];

// ─── TEY_V2 sample fixture ──────────────────────────────────────────
// Bug-fix-sprint-canonical sample character. Used as default character
// arg if caller doesn't pass one; also used by the regression tests to
// pin the B3/H4/H5/L5 corrections.
var TEY_V2_FIXTURE = {
  name: 'TEY VOSS',                        // L5 — uppercase in header
  type: 'Tramp Freighter Captain',
  species: 'Human',
  homeworld: 'Corellia',
  age: 27, gender: 'F',
  height: '1.72 m', weight: '64 kg', move: 10,
  physDesc: 'Black hair cropped short. Faded blaster burn along the left jaw. ' +
            'Wears a smuggler-cut jacket too warm for the desert.',
  // H4 — Force-sensitive demo to show the panel.
  forceSensitive: true,
  inCombat: true,
  // B4 — wounds.tier consumed against WOUND_RUNGS.
  wounds: { tier: 1 },
  // H5 — FP rendered without a max denominator. DSP still capped 0..5.
  fp: 2, dsp: 0, cp: 18, credits: 4250,
  status: [
    { label: 'WOUNDED',  desc: '−1D to all rolls until healed', color: 'red'   },
    { label: 'IN COVER', desc: '+3 difficulty for attackers',   color: 'amber' },
    { label: 'AIM HELD', desc: '+1D next attack',               color: 'green' },
  ],
  attrs: [
    { k: 'DEX', name: 'DEXTERITY',  code: '3D+2', skills: [
      { name: 'Blaster',        code: '5D+2', cp: 20,
        specs: [{ name: 'Heavy Blaster Pistol', code: '6D+1' }] },
      { name: 'Dodge',          code: '4D+2', cp: 16 },
      { name: 'Melee Combat',   code: '3D+2', cp: 8 },
      { name: 'Brawling Parry', code: '3D+2', cp: 8 },
    ]},
    { k: 'KNO', name: 'KNOWLEDGE', code: '3D',   skills: [
      { name: 'Streetwise',     code: '5D',   cp: 24,
        specs: [{ name: 'Mos Eisley', code: '5D+2' }] },
      { name: 'Languages',      code: '3D+1', cp: 4,
        specs: [{ name: 'Huttese', code: '4D' }] },
      { name: 'Value',          code: '4D',   cp: 12 },
      { name: 'Planetary Sys.', code: '3D+1', cp: 4 },
    ]},
    { k: 'MEC', name: 'MECHANICAL', code: '4D+1', skills: [
      { name: 'Astrogation',         code: '5D',   cp: 12 },
      { name: 'Space Transports',    code: '5D+2', cp: 20,
        specs: [{ name: 'YT-1300', code: '6D' }] },
      { name: 'Starship Gunnery',    code: '5D',   cp: 12,
        specs: [{ name: 'Quad Laser', code: '5D+2' }] },
      { name: 'Starship Shields',    code: '4D+2', cp: 8 },
      { name: 'Sensors',             code: '4D+1', cp: 4 },
    ]},
    { k: 'PER', name: 'PERCEPTION', code: '3D+1', skills: [
      { name: 'Bargain', code: '4D+2', cp: 12 },
      { name: 'Con',     code: '4D',   cp: 8 },
      { name: 'Search',  code: '3D+2', cp: 4 },
      { name: 'Sneak',   code: '3D+1', cp: 0 },
    ]},
    { k: 'STR', name: 'STRENGTH',  code: '2D+2', skills: [
      { name: 'Brawling', code: '3D',   cp: 4 },
      { name: 'Stamina',  code: '2D+2', cp: 0 },
    ], penalty: true },
    { k: 'TEC', name: 'TECHNICAL', code: '3D',   skills: [
      { name: 'Sp. Trans. Repair', code: '4D+1', cp: 16,
        specs: [{ name: 'YT-1300', code: '5D' }] },
      { name: 'Computer P/R',      code: '3D+2', cp: 8 },
      { name: 'First Aid',         code: '3D',   cp: 4 },
    ]},
  ],
  loadout: {
    head:   null,
    chest:  { id: 'padded-armor', name: 'Padded Armor', sub: '+1D / +1D', soak: '+1D' },
    main:   { id: 'heavy-blaster', name: 'Heavy Blaster Pistol', sub: '5D · 50/50', dmg: '5D' },
    off:    { id: 'vibroknife', name: 'Vibroknife', sub: 'STR+1D · pierces armor', dmg: 'STR+1D' },
    belt:   { id: 'belt-stim', name: 'Stim Pack ×2', sub: 'consumable' },
    boots:  { id: 'smuggler-boots', name: 'Smuggler Boots', sub: '+1 sneak' },
  },
  carry: [
    { id: 'medkit',   name: 'Med-Kit',          qty: '3/3',    kind: 'consume'  },
    { id: 'stim',     name: 'Stim Pack',        qty: 'x2',     kind: 'consume'  },
    { id: 'ammo',     name: 'Power Pack',       qty: 'x3',     kind: 'ammo'     },
    { id: 'hydro',    name: 'Hydration Pouch',  qty: '75%',    kind: 'consume'  },
    { id: 'credits',  name: 'Credit Chit',      qty: '4,250',  kind: 'currency' },
    { id: 'glow',     name: 'Glow-Rod',         qty: '1',      kind: 'gear'     },
    { id: 'rations',  name: 'Survival Rations', qty: '4 day',  kind: 'consume'  },
    { id: 'restrain', name: 'Stun Cuffs',       qty: '1',      kind: 'gear'     },
    // B3 — generic "Sealed Dispatch" — Clone-Wars-era sender.
    { id: 'dispatch', name: 'Sealed Dispatch',  qty: '1',      kind: 'quest'    },
    { id: 'comlink',  name: 'Comlink',          qty: '—',      kind: 'gear'     },
    { id: 'datapad',  name: 'Datapad',          qty: '—',      kind: 'gear'     },
  ],
  factions: [
    { id: 'hutt',         label: 'Hutt Cartel',          standing: 'Friendly',   value: 4, owed: '2 favors' },
    { id: 'republic',     label: 'Galactic Republic',    standing: 'Neutral',    value: 3 },
    { id: 'cis',          label: 'Separatists',          standing: 'Unfriendly', value: 2 },
    { id: 'jedi',         label: 'Jedi Order',           standing: 'Neutral',    value: 3 },
    { id: 'bounty_guild', label: 'Bounty Hunters Guild', standing: 'Friendly',   value: 4 },
    { id: 'black_sun',    label: 'Black Sun',            standing: 'Neutral',    value: 3 },
    { id: 'mandalorian',  label: 'Mandalorian Clans',    standing: 'Unknown',    value: 1 },
  ],
  ship: {
    name: 'RUSTY MYNOCK',
    class: 'YT-1300 Light Freighter',
    cond: 'LIGHT DAMAGE',
    hullDice: '4D · 3 pips damage',
    shields: '2D fore / 1D aft',
    modifications: ['Smuggling compartments', 'Custom hyperdrive (×2)', 'Forward quad laser turret'],
  },
  jobs: [
    { id: 'kessel', title: 'Spice Run · Kessel',
      sub: '2/4 stops complete · 18,000 cr', pct: 50, faction: 'hutt' },
    { id: 'bounty', title: 'Bounty · Vex Drago',
      sub: '3 days remain · 8,000 cr', pct: 30, faction: 'bounty_guild', urgent: true },
    // B3 — Senate dispatch — sender authority of the Clone-Wars era.
    { id: 'mail',   title: 'Sealed Senate Dispatch',
      sub: 'Deliver to Anchorhead · TBD reward', pct: 80 },
  ],
  cooldowns: [
    { id: 'heal',    label: 'NATURAL HEAL',  pct: 72, color: 'green' },
    { id: 'mission', label: 'MISSION ACCEPT', pct: 30, color: 'amber' },
    { id: 'sabacc',  label: 'SABACC HAND',    pct: 95, color: 'cyan'  },
    { id: 'harvest', label: 'HARVEST',        pct: 60, color: 'amber' },
  ],
  background: 'Grew up in the Corellian shipyards under a foreman who taught her ' +
              'how to fly and how to steal in the same lesson. Lifted her first ' +
              'freighter at sixteen and never looked back. Owes Jabba Desilijic ' +
              'Tiure 18,000 credits and counting after a botched Kessel run.',
  // B3 — Senate elites + Trade Federation profiteers; Clone-Wars-era only.
  personality: 'Loyal to a fault but slow to trust. Quick with a joke, faster ' +
               'with a blaster. Hates owing favors. ' +
               'Distrusts Senate elites and Trade Federation profiteers in equal measure. ' +
               'Pretends not to care about the war; cares deeply.',
  objectives: 'Clear the Hutt debt. Get the Mynock\'s hyperdrive certified. Keep ' +
              'Mak Torrin alive long enough to teach her the Kessel Run shortcut. ' +
              'Avoid the Republic and the CIS in equal measure.',
  quote: "I've flown worse for less. Strap in.",
  connections: [
    { id: 'yenn',  name: 'Yenn Karac',     role: 'Mos Eisley mechanic',
      standing: 'friendly', desc: 'Owes you for the Kessel patch.' },
    { id: 'mak',   name: 'Mak Torrin',     role: 'Old pilot · mentor',
      standing: 'loyal',    desc: "Knows your debt; doesn't care." },
    { id: 'jabba', name: 'Jabba the Hutt', role: 'Cartel boss',
      standing: 'owed',     desc: '18,000 cr outstanding.' },
    { id: 'marek', name: 'Marek Tan',      role: 'Wingmate',
      standing: 'friendly', desc: 'Saved you once. Owes you once.' },
  ],
  // H4 — Force panel restructured per WEG R&E.
  force: {
    skills: [
      { name: 'Control', code: '3D+1', desc: 'Force-related actions on self' },
      { name: 'Sense',   code: '2D+2', desc: 'Force-related perception'      },
      { name: 'Alter',   code: '2D',   desc: 'Force-related effects on others' },
    ],
    powers: [
      { name: 'Concentration',       skills: ['Control'],                   learned: true  },
      { name: 'Reduce Injury',       skills: ['Control'],                   learned: true  },
      { name: 'Combat Sense',        skills: ['Sense'],                     learned: true  },
      { name: 'Receptive Telepathy', skills: ['Sense'],                     learned: false },
      { name: 'Telekinesis',         skills: ['Alter'],                     learned: false },
      { name: 'Lightsaber Combat',   skills: ['Control', 'Sense'],          learned: true  },
      { name: 'Affect Mind',         skills: ['Control', 'Sense', 'Alter'], learned: false },
    ],
    master: { name: 'Master Tarn Velek', species: "Twi'lek",
              last: 'Coruscant temple, 8 days ago' },
    apprentice: null,
    alignment: 0,
  },
};

// ════════════════════════════════════════════════════════════════════
// HEADER — identity strip + actions
// ════════════════════════════════════════════════════════════════════
function buildPortraitSilhouette(p) {
  return svgEl('svg', { viewBox: '0 0 40 44', width: 36, height: 40 }, [
    svgEl('ellipse', { cx: 20, cy: 14, rx: 7, ry: 8,
                       fill: 'none', stroke: p.amber, strokeWidth: 1.5 }),
    svgEl('path', { d: 'M 10 26 Q 20 24 30 26 L 28 42 L 12 42 Z',
                    fill: 'none', stroke: p.amber, strokeWidth: 1.5 }),
    svgEl('path', { d: 'M 24 17 L 27 19',
                    stroke: p.red, strokeWidth: 1, opacity: 0.8 }),
  ]);
}

function buildHeaderBtn(p, label, onClick) {
  var props = {
    style: {
      padding: '6px 12px', background: 'transparent',
      border: '1px solid ' + p.amber, color: p.amber,
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 10, letterSpacing: 2, fontWeight: 600,
      cursor: 'pointer',
    }
  };
  if (typeof onClick === 'function') props.onClick = onClick;
  return htmlEl('button', props, [label]);
}

function buildSheetHeader(p, character, hooks) {
  hooks = hooks || {};
  var c = character;
  var asPopup = !!hooks.asPopup;
  var maxed = !!hooks.maxed;

  var children = [];

  // Traffic-light buttons (popup mode only)
  if (asPopup) {
    children.push(htmlEl('div', {
      style: { display: 'flex', gap: 6, position: 'absolute', top: 10, left: 14 }
    }, [
      htmlEl('div', {
        style: {
          width: 11, height: 11, borderRadius: '50%', background: p.red,
          cursor: 'pointer', boxShadow: '0 0 4px ' + p.red + '88',
        },
        onClick: hooks.onClose || null
      }),
      htmlEl('div', {
        style: { width: 11, height: 11, borderRadius: '50%',
                 background: p.amber, opacity: 0.65 }
      }),
      htmlEl('div', {
        style: {
          width: 11, height: 11, borderRadius: '50%', background: p.green,
          cursor: 'pointer', boxShadow: '0 0 4px ' + p.green + '88',
        },
        onClick: hooks.onMaximize || null
      }),
    ]));
  }

  // Portrait + name block
  var portrait = htmlEl('div', {
    style: {
      width: 50, height: 54,
      border: '1px solid ' + p.amber,
      background: p.amber + '11',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }
  }, [buildPortraitSilhouette(p)]);

  // L5 — c.name rendered uppercase by the source (fixture has 'TEY VOSS').
  var subline = c.species.toUpperCase() + ' · ' + c.type.toUpperCase();
  var idBlockChildren = [
    htmlEl('div', {
      style: { fontSize: 10, letterSpacing: 4, color: p.inkDim }
    }, ['+SHEET · CHARACTER DOSSIER']),
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk', sans-serif",
        fontSize: 26, letterSpacing: 3, color: p.inkBright, fontWeight: 700,
        lineHeight: 1, marginTop: 4,
        textShadow: '0 0 8px ' + p.amber + '66',
      }
    }, [c.name]),
  ];

  var sublineChildren = [subline];
  if (c.forceSensitive) {
    sublineChildren.push(htmlEl('span', {
      style: { color: p.cyan, marginLeft: 8 }
    }, ['· ✺ FORCE-SENSITIVE']));
  }
  idBlockChildren.push(htmlEl('div', {
    style: { fontSize: 10, color: p.inkDim, letterSpacing: 2, marginTop: 4 }
  }, sublineChildren));

  var idBlock = htmlEl('div', null, idBlockChildren);

  var leftCluster = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 18,
             marginLeft: asPopup ? 60 : 0 }
  }, [portrait, idBlock]);

  // Right-side action buttons
  var rightButtons = [];
  if (!asPopup) {
    rightButtons.push(buildHeaderBtn(p, '↗ POP OUT', hooks.onPopOut));
  } else {
    rightButtons.push(buildHeaderBtn(p, maxed ? '⛶ RESTORE' : '⛶ MAXIMIZE',
                                     hooks.onMaximize));
    rightButtons.push(buildHeaderBtn(p, '✕ CLOSE', hooks.onClose));
  }
  var rightCluster = htmlEl('div', {
    style: { display: 'flex', gap: 8 }
  }, rightButtons);

  children.push(leftCluster, rightCluster);

  return htmlEl('div', {
    style: {
      height: 78, padding: '12px 22px',
      background: 'linear-gradient(90deg, ' + p.amber + '1a, transparent 60%)',
      borderBottom: '1px solid ' + p.inkDim,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      position: 'relative',
    }
  }, children);
}

// ════════════════════════════════════════════════════════════════════
// VITALS — identity + wound figure + points
// ════════════════════════════════════════════════════════════════════
function buildSheetVitals(p, c) {
  // LEFT column — IDENTITY card + CURRENT STATUS
  var identityGrid = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 18px' }
  }, [
    ['SPECIES',   c.species],
    ['HOMEWORLD', c.homeworld],
    ['AGE',       String(c.age)],
    ['GENDER',    c.gender],
    ['HEIGHT',    c.height],
    ['WEIGHT',    c.weight],
    ['MOVE',      String(c.move)],
    ['SOAK',      '3D+2 (4D+2 w/ armor)'],
  ].map(function(pair) {
    return htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between',
        padding: '4px 0', borderBottom: '1px dashed ' + p.inkFaint,
        fontSize: 11,
      }
    }, [
      htmlEl('span', {
        style: { color: p.inkDim, letterSpacing: 1.5 }
      }, [pair[0]]),
      htmlEl('span', {
        style: { color: p.inkBright }
      }, [pair[1]]),
    ]);
  }));

  var physLine = htmlEl('div', {
    style: {
      marginTop: 12, fontSize: 12, color: p.ink, lineHeight: 1.6,
      fontFamily: "'IBM Plex Sans', sans-serif",
    }
  }, [
    htmlEl('span', {
      style: { fontSize: 9, letterSpacing: 2, color: p.inkDim, marginRight: 8 }
    }, ['PHYS:']),
    c.physDesc,
  ]);

  var identitySection = Section(p, 'IDENTITY', [identityGrid, physLine]);

  var statusChips = (c.status || []).map(function(s) {
    var color = (s.color === 'red')   ? p.red
              : (s.color === 'green') ? p.green
              :                         p.amber;
    return htmlEl('div', {
      title: s.desc,
      style: {
        padding: '4px 10px',
        background: color + '22', border: '1px solid ' + color,
        fontSize: 10, letterSpacing: 2, color: color, fontWeight: 600,
        cursor: 'help',
      }
    }, [s.label]);
  });
  var statusSection = Section(p, 'CURRENT STATUS', [
    htmlEl('div', {
      style: { display: 'flex', flexWrap: 'wrap', gap: 6 }
    }, statusChips),
  ]);

  var leftColumn = htmlEl('div', {
    style: { display: 'flex', flexDirection: 'column', gap: 16 }
  }, [identitySection, statusSection]);

  // RIGHT column — WOUND TRACK + POINTS
  // B4 — read canonical WOUND_RUNGS (must have labelLong per Drop 4.6).
  // Rungs 1..6 always render; HEALTHY is implicit at tier 0.
  var rungs = (window.WOUND_RUNGS || []).filter(function(r) { return r.v >= 1; });
  var rungRows = rungs.map(function(r) {
    var active = c.wounds.tier >= r.v;
    var labelText = r.labelLong + (r.pen ? (' (' + r.pen + ')') : '');
    return htmlEl('div', {
      'data-rung-v': String(r.v),
      style: {
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '4px 8px',
        background: active ? (p.red + '22') : 'rgba(0,0,0,0.25)',
        border: '1px solid ' + (active ? p.red : p.inkFaint),
      }
    }, [
      htmlEl('div', {
        style: {
          width: 10, height: 10,
          border: '1px solid ' + (active ? p.red : p.inkDim),
          background: active ? p.red : 'transparent',
          boxShadow: active ? '0 0 4px ' + p.red : 'none',
        }
      }),
      htmlEl('span', {
        style: {
          fontSize: 10, color: active ? p.red : p.ink,
          letterSpacing: 1, fontWeight: active ? 600 : 400,
        }
      }, [labelText]),
    ]);
  });
  var rungColumn = htmlEl('div', {
    style: { flex: 1, display: 'flex', flexDirection: 'column', gap: 3 }
  }, rungRows);

  var woundBlock = htmlEl('div', {
    style: { display: 'flex', gap: 18, alignItems: 'flex-start' }
  }, [buildWoundFigure(p, c.wounds.tier, 120), rungColumn]);
  var woundSection = Section(p, 'WOUND TRACK · AUTO-UPDATED', [woundBlock]);

  // Points panel — H5: FP rendered without fpMax (no denominator).
  var pointsGrid = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }
  }, [
    buildPointBlock(p, 'FORCE PTS', c.fp,  null, p.green, 'spend → ×2 ALL DICE'),
    buildPointBlock(p, 'DARK SIDE', c.dsp, 5,    p.red,   'avoid · falling risk'),
    buildPointBlock(p, 'CHAR PTS',  c.cp,  null, p.amber, 'advance · CP +1D ad-hoc'),
  ]);
  var pointsSection = Section(p, 'POINTS', [pointsGrid]);

  var rightColumn = htmlEl('div', {
    style: { display: 'flex', flexDirection: 'column', gap: 16 }
  }, [woundSection, pointsSection]);

  return htmlEl('div', {
    style: { padding: 26, display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 22 }
  }, [leftColumn, rightColumn]);
}

function buildPointBlock(p, label, value, max, color, sub) {
  // H5 — when max is null/undefined, do NOT render a /max denominator.
  var valueChildren = [String(value)];
  if (max != null) {
    valueChildren.push(htmlEl('span', {
      style: { fontSize: 14, color: p.inkDim, fontWeight: 400 }
    }, ['/' + max]));
  }
  return htmlEl('div', {
    style: {
      padding: '8px 10px', background: 'rgba(0,0,0,0.35)',
      border: '1px solid ' + color + '66',
    }
  }, [
    htmlEl('div', {
      style: { fontSize: 8, letterSpacing: 2, color: p.inkDim }
    }, [label]),
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk', sans-serif",
        fontSize: 24, color: color, fontWeight: 700, lineHeight: 1.1,
        textShadow: '0 0 8px ' + color + '66',
      }
    }, valueChildren),
    htmlEl('div', {
      style: { fontSize: 8, color: p.inkDim, marginTop: 3 }
    }, [sub]),
  ]);
}

function buildWoundFigure(p, tier, size) {
  size = size || 110;
  var w = size * 0.55;
  var primaryColor = (tier === 0) ? p.green : p.red;
  var children = [
    svgEl('circle', { cx: 20, cy: 10, r: 6,
                      fill: 'none', stroke: primaryColor, strokeWidth: 1.2 }),
    svgEl('path', { d: 'M 12 18 L 28 18 L 26 48 L 14 48 Z',
                    fill: 'none', stroke: primaryColor, strokeWidth: 1.2 }),
    svgEl('line', { x1: 12, y1: 20, x2: 6,  y2: 38,
                    stroke: p.amber, strokeWidth: 1.2 }),
    svgEl('line', { x1: 28, y1: 20, x2: 34, y2: 38,
                    stroke: p.amber, strokeWidth: 1.2 }),
    svgEl('line', { x1: 16, y1: 48, x2: 13, y2: 72,
                    stroke: p.amber, strokeWidth: 1.2 }),
    svgEl('line', { x1: 24, y1: 48, x2: 27, y2: 72,
                    stroke: p.amber, strokeWidth: 1.2 }),
  ];
  // Tier dots
  for (var t = 1; t <= 5; t++) {
    children.push(svgEl('circle', {
      cx: 36, cy: 20 + (t - 1) * 10, r: 2,
      fill: t <= tier ? p.red : 'none',
      stroke: t <= tier ? p.red : p.inkDim,
      strokeWidth: 1,
    }));
  }
  return svgEl('svg', {
    viewBox: '0 0 40 80', width: w, height: size
  }, children);
}

// ════════════════════════════════════════════════════════════════════
// SKILLS — CP banner + 3-col attribute cards
// ════════════════════════════════════════════════════════════════════
function buildSheetSkills(p, c) {
  var bannerChildren = [
    htmlEl('div', {
      style: { fontSize: 10, letterSpacing: 2.5, color: p.amber, fontWeight: 700 }
    }, ['CHARACTER POINTS · ' + c.cp]),
  ];
  if (c.inCombat) {
    bannerChildren.push(htmlEl('div', {
      style: { fontSize: 10, color: p.ink, flex: 1 }
    }, [
      htmlEl('span', { style: { color: p.red } }, ['⚠ IN COMBAT']),
      ' — advancement locked. CP burnable for +1D on a roll (combat panel handles that).',
    ]));
  } else {
    bannerChildren.push(htmlEl('div', {
      style: { fontSize: 10, color: p.ink, flex: 1 }
    }, [
      'Click ',
      htmlEl('span', { style: { color: p.green } }, ['↑ ADVANCE']),
      ' next to any skill to spend CP. Costs scale with the new level.',
    ]));
  }
  var banner = htmlEl('div', {
    style: {
      padding: '8px 14px', marginBottom: 14,
      background: c.inCombat ? (p.red + '22') : (p.amber + '22'),
      border: '1px solid ' + (c.inCombat ? p.red : p.amber),
      display: 'flex', alignItems: 'center', gap: 14,
    }
  }, bannerChildren);

  var canAdvance = !c.inCombat;
  var attrCards = (c.attrs || []).map(function(a) {
    return buildAttrCard(p, a, canAdvance);
  });
  var attrGrid = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }
  }, attrCards);

  return htmlEl('div', {
    style: { padding: 22 }
  }, [banner, attrGrid]);
}

function buildAttrCard(p, a, canAdvance) {
  var headerChildren = [
    htmlEl('div', null, [
      htmlEl('div', {
        style: { fontSize: 9, letterSpacing: 3, color: p.inkDim }
      }, [a.k]),
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 13, color: p.inkBright,
          letterSpacing: 1.5, fontWeight: 700,
        }
      }, [a.name]),
    ]),
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 20, fontWeight: 700,
        color: a.penalty ? p.red : p.inkBright,
      }
    }, [a.code]),
  ];
  if (a.penalty) {
    headerChildren.push(htmlEl('div', {
      style: {
        position: 'absolute', marginTop: 22, marginLeft: -50,
        fontSize: 8, color: p.red, letterSpacing: 1.5,
      }
    }, ['WND −1D']));
  }
  var header = htmlEl('div', {
    style: {
      padding: '8px 12px',
      background: p.amber + '1a',
      borderBottom: '1px solid ' + p.inkFaint,
      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
    }
  }, headerChildren);

  // Skill rows + their inline specializations.
  var skillRows = [];
  (a.skills || []).forEach(function(skill) {
    var rowEls = buildSkillRow(p, skill, canAdvance);
    rowEls.forEach(function(el) { skillRows.push(el); });
  });
  var skillsBody = htmlEl('div', {
    style: { padding: '6px 10px' }
  }, skillRows);

  return htmlEl('div', {
    style: {
      padding: 0,
      background: 'rgba(0,0,0,0.35)',
      border: '1px solid ' + (a.penalty ? p.red : p.inkFaint),
      position: 'relative',
    }
  }, [header, skillsBody]);
}

// Returns an ARRAY of elements (skill row + optional specialization rows).
function buildSkillRow(p, skill, canAdvance) {
  var cpCost = skill.cp + 4;
  var advanceCell;
  if (canAdvance) {
    advanceCell = htmlEl('button', {
      title: 'Costs ' + cpCost + ' CP',
      style: {
        padding: '2px 6px', background: 'transparent',
        border: '1px solid ' + p.green + '66', color: p.green,
        fontSize: 8, letterSpacing: 1, fontWeight: 700, cursor: 'pointer',
        fontFamily: "'IBM Plex Mono', monospace",
      }
    }, ['↑ ' + cpCost]);
  } else {
    advanceCell = htmlEl('span', {
      style: { fontSize: 8, color: p.inkFaint, letterSpacing: 1 }
    }, ['—']);
  }
  var skillRow = htmlEl('div', {
    'data-skill-name': skill.name,
    style: {
      display: 'grid', gridTemplateColumns: '1fr auto auto',
      gap: 8, alignItems: 'baseline',
      padding: '4px 0', borderBottom: '1px dashed ' + p.inkFaint + '33',
    }
  }, [
    htmlEl('span', {
      style: { fontSize: 11.5, color: p.ink, letterSpacing: 0.5 }
    }, [skill.name]),
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 12,
        color: p.inkBright, fontWeight: 600,
      }
    }, [skill.code]),
    advanceCell,
  ]);

  var result = [skillRow];
  (skill.specs || []).forEach(function(sp) {
    result.push(htmlEl('div', {
      'data-spec-of': skill.name,
      style: {
        display: 'grid', gridTemplateColumns: '1fr auto auto',
        gap: 8, alignItems: 'baseline',
        padding: '2px 0 2px 18px',
        fontSize: 10, color: p.inkDim,
      }
    }, [
      htmlEl('span', null, ['↳ ' + sp.name]),
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 11,
          color: p.amber, fontWeight: 600,
        }
      }, [sp.code]),
      htmlEl('span', null, ['']),
    ]));
  });
  return result;
}

// ════════════════════════════════════════════════════════════════════
// GEAR — paper doll + carried inventory grid
// ════════════════════════════════════════════════════════════════════
function buildSheetGear(p, c) {
  // LEFT: loadout / paper doll + soak panel
  var soakBlock = htmlEl('div', {
    style: {
      marginTop: 14, padding: '8px 12px',
      background: p.amber + '22', border: '1px solid ' + p.amber,
    }
  }, [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 2, color: p.inkDim }
    }, ['TOTAL SOAK']),
    htmlEl('div', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 22, color: p.inkBright, fontWeight: 700,
      }
    }, [
      '3D+2 ',
      htmlEl('span', { style: { fontSize: 12, color: p.amber } }, ['+ 1D armor']),
      ' = ',
      htmlEl('span', { style: { color: p.amber } }, ['4D+2']),
    ]),
    htmlEl('div', {
      style: { fontSize: 9, color: p.inkDim, marginTop: 2 }
    }, ['STR 2D+2 + Padded Armor +1D physical / +1D energy']),
  ]);
  var leftSection = Section(p, 'LOADOUT · DRAG TO EQUIP',
                            [buildPaperDoll(p, c.loadout), soakBlock]);

  // RIGHT: filter chips + 4-column inventory grid
  var filterChips = ['ALL', 'WEAPONS', 'ARMOR', 'CONSUME', 'AMMO', 'QUEST', 'GEAR']
    .map(function(t, i) {
      return htmlEl('div', {
        style: {
          fontSize: 9, letterSpacing: 1.5, padding: '3px 8px',
          color: (i === 0) ? p.skyDeep : p.inkDim,
          background: (i === 0) ? p.amber : 'transparent',
          border: '1px solid ' + ((i === 0) ? p.amber : p.inkFaint),
        }
      }, [t]);
    });
  var filterRow = htmlEl('div', {
    style: { display: 'flex', gap: 4, marginBottom: 10, flexWrap: 'wrap' }
  }, filterChips);

  var invCards = (c.carry || []).map(function(item) {
    return buildInventoryCard(p, item);
  });
  var invGrid = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }
  }, invCards);

  var rightTitle = 'CARRIED · ' + (c.carry || []).length + ' ITEMS · 38% ENCUMB';
  var rightSection = Section(p, rightTitle, [filterRow, invGrid]);

  return htmlEl('div', {
    style: { padding: 22, display: 'grid', gridTemplateColumns: '360px 1fr', gap: 20 }
  }, [leftSection, rightSection]);
}

function buildPaperDoll(p, loadout) {
  var slots = [
    { id: 'head',  x: 50,  y: 7,  w: 130, label: 'HEAD',  item: loadout.head },
    { id: 'chest', x: 50,  y: 30, w: 150, label: 'CHEST', item: loadout.chest },
    { id: 'main',  x: 12,  y: 55, w: 130, label: 'MAIN',  item: loadout.main },
    { id: 'off',   x: 88,  y: 55, w: 130, label: 'OFF',   item: loadout.off },
    { id: 'belt',  x: 50,  y: 70, w: 150, label: 'BELT',  item: loadout.belt },
    { id: 'boots', x: 50,  y: 94, w: 150, label: 'BOOTS', item: loadout.boots },
  ];

  // Silhouette SVG centered
  var silhouette = svgEl('svg', {
    viewBox: '0 0 100 130', width: '42%', height: '100%',
    preserveAspectRatio: 'xMidYMid meet',
    style: { position: 'absolute', left: '29%', top: 0 }
  }, [
    svgEl('ellipse', { cx: 50, cy: 14, rx: 9, ry: 11,
                       fill: 'rgba(0,0,0,0.5)', stroke: p.inkDim, strokeWidth: 0.8 }),
    svgEl('path', { d: 'M 32 26 L 68 26 L 64 70 L 36 70 Z',
                    fill: 'rgba(0,0,0,0.5)', stroke: p.inkDim, strokeWidth: 0.8 }),
    svgEl('line', { x1: 32, y1: 28, x2: 18, y2: 60, stroke: p.inkDim, strokeWidth: 0.8 }),
    svgEl('line', { x1: 68, y1: 28, x2: 82, y2: 60, stroke: p.inkDim, strokeWidth: 0.8 }),
    svgEl('line', { x1: 36, y1: 70, x2: 32, y2: 120, stroke: p.inkDim, strokeWidth: 0.8 }),
    svgEl('line', { x1: 64, y1: 70, x2: 68, y2: 120, stroke: p.inkDim, strokeWidth: 0.8 }),
  ]);

  var pins = slots.map(function(s) { return buildSlotPin(p, s); });
  return htmlEl('div', {
    style: { position: 'relative', height: 440, padding: '0 6px' }
  }, [silhouette].concat(pins));
}

function buildSlotPin(p, slot) {
  var item = slot.item;
  var empty = !item;
  var tooltip = item ? (item.name + ' · ' + item.sub)
                     : ('Drop a ' + slot.label.toLowerCase() + ' here');

  var children = [
    htmlEl('div', {
      style: {
        fontSize: 8, letterSpacing: 2,
        color: empty ? p.inkFaint : p.amber, fontWeight: 600,
      }
    }, [slot.label]),
    htmlEl('div', {
      style: {
        fontSize: 10, color: empty ? p.inkFaint : p.inkBright, marginTop: 1,
        fontStyle: empty ? 'italic' : 'normal',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }
    }, [empty ? 'empty' : item.name]),
  ];
  if (item) {
    children.push(htmlEl('div', {
      style: {
        fontSize: 8, color: p.inkDim, marginTop: 1,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }
    }, [item.sub]));
  }

  return htmlEl('div', {
    style: {
      position: 'absolute',
      left: slot.x + '%', top: slot.y + '%',
      transform: 'translate(-50%, -50%)',
      width: slot.w,
    }
  }, [
    htmlEl('div', {
      title: tooltip,
      'data-slot-id': slot.id,
      style: {
        padding: '4px 8px',
        background: empty ? 'rgba(0,0,0,0.55)' : (p.amber + '22'),
        border: '1px ' + (empty ? 'dashed' : 'solid') + ' ' +
                (empty ? p.inkFaint : p.amber),
        cursor: empty ? 'pointer' : 'grab',
        boxShadow: empty ? 'none' : '0 0 6px ' + p.amber + '33',
      }
    }, children),
  ]);
}

function buildInventoryCard(p, item) {
  var kindColors = {
    weapon: p.red, armor: p.amber, consume: p.green, ammo: p.cyan,
    currency: p.gold || p.amber, gear: p.inkDim, quest: p.green,
  };
  var color = kindColors[item.kind] || p.amber;

  return htmlEl('div', {
    'data-item-id': item.id,
    style: {
      padding: '6px 8px',
      background: 'rgba(0,0,0,0.4)',
      border: '1px solid ' + p.inkFaint,
      borderLeft: '2px solid ' + color,
      cursor: 'grab',
    }
  }, [
    htmlEl('div', {
      style: { fontSize: 9.5, color: p.ink, letterSpacing: 0.5, lineHeight: 1.3 }
    }, [item.name]),
    htmlEl('div', {
      style: { display: 'flex', justifyContent: 'space-between',
               marginTop: 3, alignItems: 'baseline' }
    }, [
      htmlEl('span', {
        style: { fontFamily: "'Space Grotesk'", fontSize: 12,
                 color: p.inkBright, fontWeight: 600 }
      }, [item.qty]),
      htmlEl('span', {
        style: { fontSize: 8, color: color, letterSpacing: 1.5 }
      }, [String(item.kind || '').toUpperCase()]),
    ]),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// WORLD — factions + ship + jobs + cooldowns
// ════════════════════════════════════════════════════════════════════
function buildSheetWorld(p, c) {
  // LEFT: faction reputation (radar + list)
  var leftBody = [buildFactionRadar(p, c.factions || [])];

  // Faction list rows
  var standingColors = {
    Loyal:      p.green,
    Friendly:   p.green,
    Neutral:    p.inkDim,
    Unfriendly: p.amber,
    Hostile:    p.red,
    Owed:       p.red,
    Unknown:    p.inkFaint,
  };
  // Read M3AssetsIcons.FACTION_ICONS for the faction icon SVG factory.
  // Fall back to a small placeholder if the asset module isn't loaded.
  var FACTION_ICONS = (window.M3AssetsIcons && window.M3AssetsIcons.FACTION_ICONS) || {};

  var factionRows = (c.factions || []).map(function(f) {
    var iconFn = FACTION_ICONS[f.id] || FACTION_ICONS.republic;
    var iconEl;
    if (typeof iconFn === 'function') {
      // map_v3 icons render as React components — call them with the
      // same {c, size} props the JSX uses. Since they're not in this
      // module, we just try calling; if it throws, render a placeholder.
      try { iconEl = iconFn({ c: p.amber, size: 16 }); }
      catch (e) { iconEl = htmlEl('span', { style: { color: p.amber } }, ['•']); }
    } else {
      iconEl = htmlEl('span', { style: { color: p.amber } }, ['•']);
    }
    // Defensive: ensure iconEl is a DOM node, not a React element.
    if (iconEl && !iconEl.nodeType) {
      iconEl = htmlEl('span', { style: { color: p.amber } }, ['•']);
    }

    var standingColor = standingColors[f.standing] || p.inkDim;
    var rowChildren = [
      iconEl,
      htmlEl('span', {
        style: { fontSize: 11, color: p.ink, letterSpacing: 0.5 }
      }, [f.label]),
    ];
    if (f.owed) {
      rowChildren.push(htmlEl('span', {
        style: { fontSize: 9, color: p.amber, letterSpacing: 1 }
      }, [f.owed]));
    } else {
      rowChildren.push(htmlEl('span', null, ['']));  // grid filler
    }
    rowChildren.push(htmlEl('span', {
      style: {
        fontSize: 9, letterSpacing: 1.5, fontWeight: 600,
        color: standingColor,
        padding: '1px 6px',
        border: '1px solid ' + standingColor + '55',
      }
    }, [String(f.standing).toUpperCase()]));

    return htmlEl('div', {
      'data-faction-id': f.id,
      style: {
        display: 'grid', gridTemplateColumns: '20px 1fr auto auto',
        gap: 8, alignItems: 'center',
        padding: '4px 8px',
        background: 'rgba(0,0,0,0.3)',
        border: '1px solid ' + p.inkFaint,
      }
    }, rowChildren);
  });
  leftBody.push(htmlEl('div', {
    style: { marginTop: 12, display: 'flex', flexDirection: 'column', gap: 3 }
  }, factionRows));
  var leftSection = Section(p, 'FACTION REPUTATION', leftBody);

  // RIGHT: ship card + active jobs + cooldowns
  var rightSections = [];

  if (c.ship) {
    var modLines = (c.ship.modifications || []).map(function(m) {
      return htmlEl('div', {
        style: { fontSize: 10, color: p.ink, paddingLeft: 8 }
      }, ['· ' + m]);
    });
    var shipBody = htmlEl('div', {
      style: {
        padding: '10px 12px', background: p.cyan + '11',
        border: '1px solid ' + p.cyan + '66',
      }
    }, [
      htmlEl('div', {
        style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }
      }, [
        htmlEl('span', {
          style: { fontFamily: "'Space Grotesk'", fontSize: 14, color: p.cyan,
                   letterSpacing: 2, fontWeight: 700 }
        }, [c.ship.name]),
        htmlEl('span', {
          style: { fontSize: 9, color: p.amber, letterSpacing: 1.5,
                   padding: '1px 5px', border: '1px solid ' + p.amber + '55' }
        }, [c.ship.cond]),
      ]),
      htmlEl('div', {
        style: { fontSize: 10, color: p.inkDim, marginTop: 4 }
      }, [c.ship.class]),
      htmlEl('div', {
        style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6,
                 marginTop: 8, fontSize: 10 }
      }, [
        htmlEl('span', null, [
          htmlEl('span', { style: { color: p.inkDim } }, ['HULL ']),
          htmlEl('span', { style: { color: p.cyan } }, [c.ship.hullDice]),
        ]),
        htmlEl('span', null, [
          htmlEl('span', { style: { color: p.inkDim } }, ['SHLD ']),
          htmlEl('span', { style: { color: p.cyan } }, [c.ship.shields]),
        ]),
      ]),
      htmlEl('div', {
        style: { marginTop: 8, fontSize: 9, color: p.inkDim }
      }, ['MODS:']),
    ].concat(modLines));
    rightSections.push(Section(p, 'SHIP · ' + c.ship.name, [shipBody]));
  }

  var jobCards = (c.jobs || []).map(function(j) {
    var headerChildren = [
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'", fontSize: 12, color: p.inkBright, fontWeight: 600,
        }
      }, [j.title]),
    ];
    if (j.urgent) {
      headerChildren.push(htmlEl('span', {
        style: { fontSize: 8, color: p.red, fontWeight: 700, letterSpacing: 1.5 }
      }, ['● URGENT']));
    }
    var jobColor = j.urgent ? p.red : p.amber;
    return htmlEl('div', {
      'data-job-id': j.id,
      style: {
        padding: '6px 10px', marginBottom: 4,
        background: 'rgba(0,0,0,0.3)', border: '1px solid ' + p.inkFaint,
        borderLeft: '2px solid ' + jobColor,
      }
    }, [
      htmlEl('div', {
        style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }
      }, headerChildren),
      htmlEl('div', {
        style: { fontSize: 10, color: p.inkDim, marginTop: 2 }
      }, [j.sub]),
      htmlEl('div', {
        style: { marginTop: 4, height: 3, background: 'rgba(0,0,0,0.5)' }
      }, [
        htmlEl('div', {
          style: {
            width: j.pct + '%', height: '100%',
            background: jobColor,
            boxShadow: '0 0 4px ' + jobColor,
          }
        }),
      ]),
    ]);
  });
  rightSections.push(Section(p, 'ACTIVE JOBS', jobCards));

  var cdCards = (c.cooldowns || []).map(function(cd) {
    var cdColor = (cd.color === 'green') ? p.green
                : (cd.color === 'amber') ? p.amber
                : (cd.color === 'cyan')  ? p.cyan
                :                          p.amber;
    return buildCooldownWheel(p, cd, cdColor);
  });
  rightSections.push(Section(p, 'COOLDOWNS', [
    htmlEl('div', {
      style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }
    }, cdCards),
  ]));

  var rightColumn = htmlEl('div', {
    style: { display: 'flex', flexDirection: 'column', gap: 16 }
  }, rightSections);

  return htmlEl('div', {
    style: { padding: 22, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }
  }, [leftSection, rightColumn]);
}

function buildCooldownWheel(p, cd, colorOverride) {
  var color = colorOverride || p.amber;
  var C = 2 * Math.PI * 18;
  return htmlEl('div', {
    'data-cd-id': cd.id,
    style: {
      textAlign: 'center', padding: 6,
      background: 'rgba(0,0,0,0.3)', border: '1px solid ' + p.inkFaint,
    }
  }, [
    svgEl('svg', { viewBox: '0 0 44 44', width: 48, height: 48 }, [
      svgEl('circle', { cx: 22, cy: 22, r: 18,
                        fill: 'none', stroke: p.inkFaint, strokeWidth: 3 }),
      svgEl('circle', { cx: 22, cy: 22, r: 18,
                        fill: 'none', stroke: color, strokeWidth: 3,
                        strokeDasharray: String(C),
                        strokeDashoffset: String(C * (1 - cd.pct / 100)),
                        transform: 'rotate(-90 22 22)',
                        style: { filter: 'drop-shadow(0 0 3px ' + color + ')' } }),
      svgEl('text', { x: 22, y: 26, fontSize: 11, fill: color,
                      textAnchor: 'middle',
                      fontFamily: 'IBM Plex Mono', fontWeight: 700 },
            [String(cd.pct)]),
    ]),
    htmlEl('div', {
      style: { fontSize: 8, letterSpacing: 1, color: p.inkDim, marginTop: 2 }
    }, [cd.label]),
  ]);
}

function buildFactionRadar(p, factions) {
  var N = factions.length;
  if (N === 0) return svgEl('svg', { viewBox: '0 0 200 180', width: '100%' }, []);
  var r = 60;
  var cx = 100, cy = 90;

  var poly = factions.map(function(f, i) {
    var angle = (i / N) * Math.PI * 2 - Math.PI / 2;
    var dist = (f.value / 5) * r;
    return [cx + Math.cos(angle) * dist, cy + Math.sin(angle) * dist];
  });

  var children = [];
  // Concentric guide circles
  [1, 2, 3, 4, 5].forEach(function(k) {
    children.push(svgEl('circle', {
      cx: cx, cy: cy, r: (k / 5) * r,
      fill: 'none', stroke: p.inkFaint, strokeWidth: 0.3,
    }));
  });
  // Radial spokes
  factions.forEach(function(_, i) {
    var angle = (i / N) * Math.PI * 2 - Math.PI / 2;
    children.push(svgEl('line', {
      x1: cx, y1: cy,
      x2: cx + Math.cos(angle) * r, y2: cy + Math.sin(angle) * r,
      stroke: p.inkFaint, strokeWidth: 0.3,
    }));
  });
  // Poly
  children.push(svgEl('polygon', {
    points: poly.map(function(pp) { return pp.join(','); }).join(' '),
    fill: p.amber + '55', stroke: p.amber, strokeWidth: 0.8,
    style: { filter: 'drop-shadow(0 0 4px ' + p.amber + ')' },
  }));
  // Labels
  factions.forEach(function(f, i) {
    var angle = (i / N) * Math.PI * 2 - Math.PI / 2;
    var lx = cx + Math.cos(angle) * (r + 12);
    var ly = cy + Math.sin(angle) * (r + 12) + 2;
    children.push(svgEl('text', {
      x: lx, y: ly, fontSize: 7,
      textAnchor: 'middle',
      fill: p.inkDim, fontFamily: 'IBM Plex Mono', letterSpacing: 1,
    }, [f.label.split(' ')[0].toUpperCase()]));
  });

  return svgEl('svg', {
    viewBox: '0 0 200 180', width: '100%',
    style: { maxHeight: 200 },
  }, children);
}

// ════════════════════════════════════════════════════════════════════
// STORY — quote + editable sections + connections
// (B3 era contamination — preserved through TEY_V2_FIXTURE text +
//  STORY_NOUNS — both contain Senate references, none of Empire/imperial)
// ════════════════════════════════════════════════════════════════════
function buildSheetStory(p, c) {
  var quote = htmlEl('div', {
    style: {
      padding: '12px 18px',
      background: p.amber + '11',
      borderLeft: '4px solid ' + p.amber,
      position: 'relative',
    }
  }, [
    htmlEl('div', {
      style: {
        fontFamily: "'IBM Plex Sans', sans-serif",
        fontSize: 16, fontStyle: 'italic', color: p.inkBright, lineHeight: 1.5,
      }
    }, ['“' + (c.quote || '') + '”']),
    htmlEl('button', {
      style: {
        position: 'absolute', top: 8, right: 8,
        padding: '2px 6px', background: 'transparent',
        border: '1px solid ' + p.inkFaint, color: p.inkDim,
        fontSize: 8, letterSpacing: 1.5, cursor: 'pointer',
        fontFamily: "'IBM Plex Mono', monospace",
      }
    }, ['✎ EDIT']),
  ]);

  var leftColumn = htmlEl('div', {
    style: { display: 'flex', flexDirection: 'column', gap: 16 }
  }, [
    quote,
    buildEditableSection(p, 'BACKGROUND',  c.background),
    buildEditableSection(p, 'PERSONALITY', c.personality),
    buildEditableSection(p, 'OBJECTIVES',  c.objectives),
  ]);

  var connRows = (c.connections || []).map(function(conn) {
    return buildConnectionRow(p, conn);
  });
  var rightSection = Section(p, 'CONNECTIONS', connRows);

  return htmlEl('div', {
    style: { padding: 22, display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 20 }
  }, [leftColumn, rightSection]);
}

function buildEditableSection(p, label, text) {
  return htmlEl('div', {
    'data-editable-label': label,
    style: {
      padding: '12px 14px',
      background: 'rgba(0,0,0,0.3)',
      border: '1px solid ' + p.inkFaint,
      position: 'relative',
    }
  }, [
    htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        marginBottom: 6,
      }
    }, [
      htmlEl('div', {
        style: { fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 700 }
      }, ['▮▮ ' + label]),
      htmlEl('button', {
        style: {
          padding: '2px 6px', background: 'transparent',
          border: '1px solid ' + p.inkFaint, color: p.inkDim,
          fontSize: 8, letterSpacing: 1.5, cursor: 'pointer',
          fontFamily: "'IBM Plex Mono', monospace",
        }
      }, ['✎ EDIT INLINE']),
    ]),
    htmlEl('div', {
      style: {
        fontFamily: "'IBM Plex Sans', sans-serif",
        fontSize: 13, color: p.ink, lineHeight: 1.65,
      }
    }, highlightStoryNouns(text, p)),
  ]);
}

// Returns an array of DOM nodes/strings — plain text segments + clickable
// noun spans. Mirrors the JSX highlightStoryNouns semantics.
function highlightStoryNouns(text, p) {
  if (!text) return [''];
  var escapeRegex = function(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  };
  var re = new RegExp(
    '(' + STORY_NOUNS.map(escapeRegex).join('|') + ')',
    'g'
  );
  var parts = String(text).split(re);
  return parts.map(function(part) {
    if (STORY_NOUNS.indexOf(part) !== -1) {
      return htmlEl('span', {
        title: 'Open holocron: ' + part,
        style: {
          color: p.amber,
          borderBottom: '1px dotted ' + p.amber,
          cursor: 'pointer',
        }
      }, [part]);
    }
    return part;
  });
}

function buildConnectionRow(p, conn) {
  var standingColors = {
    loyal: p.green, friendly: p.amber, neutral: p.inkDim,
    unfriendly: p.amber, hostile: p.red, owed: p.red,
  };
  var color = standingColors[conn.standing] || p.amber;
  return htmlEl('div', {
    'data-conn-id': conn.id,
    title: 'Open holocron: ' + conn.name,
    style: {
      padding: '6px 10px', marginBottom: 4,
      background: 'rgba(0,0,0,0.3)',
      border: '1px solid ' + p.inkFaint,
      borderLeft: '2px solid ' + color,
      cursor: 'pointer',
    }
  }, [
    htmlEl('div', {
      style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }
    }, [
      htmlEl('span', {
        style: { fontFamily: "'Space Grotesk'", fontSize: 13, fontWeight: 600,
                 color: p.amber, letterSpacing: 0.5 }
      }, [conn.name]),
      htmlEl('span', {
        style: { fontSize: 8, color: color, letterSpacing: 1.5, fontWeight: 700 }
      }, [String(conn.standing).toUpperCase()]),
    ]),
    htmlEl('div', {
      style: { fontSize: 10, color: p.inkDim, marginTop: 1 }
    }, [conn.role]),
    htmlEl('div', {
      style: { fontSize: 10.5, color: p.ink, marginTop: 4, lineHeight: 1.5,
               fontFamily: "'IBM Plex Sans', sans-serif" }
    }, [conn.desc]),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// FORCE — H4 — three skills (Control/Sense/Alter) + powers list
// ════════════════════════════════════════════════════════════════════
function buildSheetForce(p, c) {
  var f = c.force || {};

  // Three Force skills — Control / Sense / Alter cards.
  var skillCards = (f.skills || []).map(function(s) {
    return htmlEl('div', {
      'data-force-skill': s.name,
      style: {
        padding: '10px 12px',
        background: 'rgba(0,0,0,0.35)',
        border: '1px solid ' + p.cyan + '66',
      }
    }, [
      htmlEl('div', {
        style: { fontSize: 9, letterSpacing: 2, color: p.inkDim }
      }, [s.name.toUpperCase()]),
      htmlEl('div', {
        style: {
          fontFamily: "'Space Grotesk', sans-serif",
          fontSize: 22, color: p.cyan, fontWeight: 700, lineHeight: 1.1,
          textShadow: '0 0 8px ' + p.cyan + '66',
        }
      }, [s.code]),
      htmlEl('div', {
        style: { fontSize: 8, color: p.inkDim, marginTop: 3 }
      }, [s.desc]),
    ]);
  });
  var skillsSection = Section(p, 'FORCE SKILLS · CONTROL · SENSE · ALTER', [
    htmlEl('div', {
      style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }
    }, skillCards),
  ]);

  // Powers — each tagged with the skill(s) it draws on.
  var powerRows = (f.powers || []).map(function(pw) {
    var tagText = (pw.skills || [])
      .map(function(s) { return s.slice(0, 3).toUpperCase(); })
      .join(' · ');
    return htmlEl('div', {
      'data-power-name': pw.name,
      style: {
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '4px 8px',
        background: pw.learned ? 'rgba(0,0,0,0.35)' : 'rgba(0,0,0,0.18)',
        border: '1px solid ' + (pw.learned ? p.cyan + '66' : p.inkFaint),
        opacity: pw.learned ? 1 : 0.55,
      }
    }, [
      htmlEl('span', {
        style: {
          fontSize: 11, color: pw.learned ? p.cyan : p.inkDim,
          fontWeight: pw.learned ? 600 : 400, flex: 1, letterSpacing: 0.5,
        }
      }, [(pw.learned ? '✺' : '○') + ' ' + pw.name]),
      htmlEl('span', {
        style: { fontSize: 9, color: p.inkDim, letterSpacing: 1.5 }
      }, [tagText]),
    ]);
  });
  var powersSection = Section(p, 'POWERS · KNOWN AND OBSERVED', [
    htmlEl('div', {
      style: { display: 'flex', flexDirection: 'column', gap: 3 }
    }, powerRows),
  ]);

  // Master / Apprentice + Alignment row.
  var masterBlock;
  if (f.master) {
    masterBlock = htmlEl('div', {
      style: {
        padding: '10px 12px',
        background: p.cyan + '11',
        border: '1px solid ' + p.cyan,
      }
    }, [
      htmlEl('div', {
        style: { fontSize: 9, letterSpacing: 2, color: p.inkDim }
      }, ['MASTER']),
      htmlEl('div', {
        style: { fontFamily: "'Space Grotesk'", fontSize: 16,
                 color: p.cyan, fontWeight: 700 }
      }, [f.master.name]),
      htmlEl('div', {
        style: { fontSize: 10, color: p.inkDim, marginTop: 2 }
      }, [f.master.species]),
      htmlEl('div', {
        style: { fontSize: 10, color: p.ink, marginTop: 6 }
      }, [
        'Last lesson: ',
        htmlEl('span', { style: { color: p.amber } }, [f.master.last]),
      ]),
    ]);
  } else {
    masterBlock = htmlEl('div', null, []);
  }
  var masterSection = Section(p, 'MASTER · APPRENTICE', [masterBlock]);

  var alignment = (typeof f.alignment === 'number') ? f.alignment : 0;
  var alignmentTrack = htmlEl('div', {
    style: {
      padding: 12, background: 'rgba(0,0,0,0.3)',
      border: '1px solid ' + p.inkFaint,
    }
  }, [
    htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between', fontSize: 9,
        letterSpacing: 2, color: p.inkDim, marginBottom: 6,
      }
    }, [
      htmlEl('span', { style: { color: p.red } }, ['DARK']),
      htmlEl('span', { style: { color: p.green } }, ['LIGHT']),
    ]),
    htmlEl('div', {
      style: { height: 12, background: 'rgba(0,0,0,0.5)', position: 'relative' }
    }, [
      htmlEl('div', {
        style: {
          position: 'absolute', left: '50%', top: 0, bottom: 0,
          width: 1, background: p.inkDim,
        }
      }),
      htmlEl('div', {
        'data-alignment-marker': '1',
        style: {
          position: 'absolute', top: -3, bottom: -3,
          left: (50 + alignment * 0.5) + '%',
          width: 4, background: p.amber, boxShadow: '0 0 6px ' + p.amber,
        }
      }),
    ]),
  ]);
  var alignmentSection = Section(p, 'ALIGNMENT', [alignmentTrack]);

  var bottomRow = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }
  }, [masterSection, alignmentSection]);

  return htmlEl('div', {
    style: { padding: 22, display: 'flex', flexDirection: 'column', gap: 18 }
  }, [skillsSection, powersSection, bottomRow]);
}

// ════════════════════════════════════════════════════════════════════
// TOP-LEVEL — CharacterSheet renderer
// ════════════════════════════════════════════════════════════════════
function buildCharacterSheet(p, character, currentTab, hooks) {
  character = character || TEY_V2_FIXTURE;
  currentTab = currentTab || 'SKILLS';
  hooks = hooks || {};
  var c = character;

  // Tab definitions — FORCE only shown when character is Force-sensitive.
  var tabs = [
    { id: 'VITALS', label: 'VITALS',  icon: '◉' },
    { id: 'SKILLS', label: 'SKILLS',  icon: '✦' },
    { id: 'GEAR',   label: 'GEAR',    icon: '⋈' },
    { id: 'WORLD',  label: 'WORLD',   icon: '◈' },
    { id: 'STORY',  label: 'STORY',   icon: '✎' },
  ];
  if (c.forceSensitive) {
    tabs.push({ id: 'FORCE', label: 'FORCE', icon: '✺' });
  }

  // Tab strip
  var tabPills = tabs.map(function(t) {
    var isActive = (t.id === currentTab);
    var props = {
      'data-tab-id': t.id,
      style: {
        padding: '0 22px', height: '100%',
        display: 'flex', alignItems: 'center', gap: 8,
        background: isActive ? (p.amber + '22') : 'transparent',
        borderBottom: isActive ? ('2px solid ' + p.amber) : '2px solid transparent',
        color: isActive ? p.amber : p.inkDim,
        fontSize: 11, letterSpacing: 3, fontWeight: 600,
        cursor: 'pointer',
      }
    };
    if (typeof hooks.onTabClick === 'function') {
      props.onClick = function() { hooks.onTabClick(t.id); };
    }
    return htmlEl('div', props, [
      htmlEl('span', { style: { fontSize: 13 } }, [t.icon]),
      htmlEl('span', null, [t.label]),
    ]);
  });

  // H5 — render CP/FP/CR; FP value rendered without /max in the tab strip.
  var statBlock = htmlEl('div', {
    style: {
      marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 14,
      padding: '0 18px', fontSize: 10,
    }
  }, [
    buildSheetStat(p, 'CP', String(c.cp), p.amber),
    buildSheetStat(p, 'FP', String(c.fp), p.green),  // H5: just the value
    buildSheetStat(p, 'CR', _formatNumber(c.credits), p.cyan),
  ]);

  var tabStrip = htmlEl('div', {
    style: {
      position: 'absolute', top: 78, left: 0, right: 0, height: 38,
      display: 'flex', borderBottom: '1px solid ' + p.inkDim,
      background: 'rgba(0,0,0,0.4)',
    }
  }, tabPills.concat([statBlock]));

  // Body — dispatch on currentTab.
  var bodyContent;
  switch (currentTab) {
    case 'VITALS': bodyContent = buildSheetVitals(p, c); break;
    case 'SKILLS': bodyContent = buildSheetSkills(p, c); break;
    case 'GEAR':   bodyContent = buildSheetGear(p, c);   break;
    case 'WORLD':  bodyContent = buildSheetWorld(p, c);  break;
    case 'STORY':  bodyContent = buildSheetStory(p, c);  break;
    case 'FORCE':
      bodyContent = c.forceSensitive ? buildSheetForce(p, c)
                                     : htmlEl('div', null, []);
      break;
    default:       bodyContent = buildSheetSkills(p, c); break;
  }
  var body = htmlEl('div', {
    'data-current-tab': currentTab,
    style: {
      position: 'absolute', top: 78 + 38, left: 0, right: 0, bottom: 0,
      overflow: 'auto',
    }
  }, [bodyContent]);

  // Outer container.
  var width = hooks.width || 1280;
  var height = hooks.height || 920;
  var asPopup = !!hooks.asPopup;
  var outerShadow = asPopup
    ? '0 0 0 1px #000, 0 0 30px ' + p.amber + '55, 0 40px 80px rgba(0,0,0,0.85)'
    : 'inset 0 0 40px ' + p.skyDeep + ', 0 0 0 1px #000, 0 20px 50px rgba(0,0,0,0.7)';

  return htmlEl('div', {
    'data-sheet-character': c.name,
    style: {
      width: width, height: height, position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + (asPopup ? p.amber : p.inkDim),
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      boxShadow: outerShadow,
    }
  }, [
    buildSheetHeader(p, c, hooks),
    tabStrip,
    body,
  ]);
}

function buildSheetStat(p, label, value, color) {
  return htmlEl('div', {
    style: { display: 'flex', alignItems: 'baseline', gap: 4 }
  }, [
    htmlEl('span', {
      style: { fontSize: 9, letterSpacing: 2, color: p.inkDim }
    }, [label]),
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 14, color: color, fontWeight: 700,
      }
    }, [value]),
  ]);
}

function _formatNumber(n) {
  if (n == null) return '0';
  if (typeof n.toLocaleString === 'function') return n.toLocaleString();
  return String(n);
}

// ════════════════════════════════════════════════════════════════════
// CHARACTER SHEET MODAL — popup wrapper (Drop 4.12a)
//
// Ported from sheet-v2.jsx::CharacterSheetModal (1165-1193). The JSX
// version owned a `maxed` boolean via React.useState. The vanilla
// version splits this into two surfaces:
//
//   · buildCharacterSheetModal(p, character, hooks) — stateless. Caller
//     supplies hooks.maxed and hooks.onMaximize; caller owns re-render.
//     This is the "library" form — useful for tests and for embedding
//     the modal into a larger composition that owns its own state.
//
//   · createCharacterSheetModal(p, character, hooks) → handle — stateful
//     convenience. Returns { element, destroy }. The handle owns the
//     `maxed` toggle internally and swaps the inner DOM on toggle. This
//     is what assembled-client consumes when wiring the popup.
//
// Dimensions match the JSX source:
//   · maxed:false → 1080 × 720 (px)
//   · maxed:true  → 95% × 92%  (responsive)
// Animation: holoFade (backdrop) + holoPop (window) — same as the
// holocron and holonet modals. Keyframes defined in client.html
// stylesheet (unchanged from prior drops).
// ════════════════════════════════════════════════════════════════════
function buildCharacterSheetModal(p, character, hooks) {
  hooks = hooks || {};
  character = character || TEY_V2_FIXTURE;

  var maxed = !!hooks.maxed;
  var onClose = hooks.onClose || null;
  var onMaximize = hooks.onMaximize || null;

  // Resolve dimensions. The JSX uses '95%' / '92%' strings when maxed —
  // these are CSS percent values, so the style assignment passes them
  // through as-is. Non-maxed uses numeric px values.
  var w, h;
  if (maxed) {
    w = hooks.maxedWidth  || '95%';
    h = hooks.maxedHeight || '92%';
  } else {
    w = hooks.width  || 1080;
    h = hooks.height || 720;
  }

  // Inner sheet — passes asPopup=true so the header shows close +
  // maximize affordances (already wired in buildSheetHeader). The
  // numeric dims passed in match the JSX source: when maxed, the
  // wrapper percent-sizes itself but the inner sheet still uses
  // 1200×800 (per JSX line 1184-1185).
  var sheetWidth  = (typeof w === 'number') ? w : 1200;
  var sheetHeight = (typeof h === 'number') ? h : 800;

  var sheetHooks = {
    asPopup:    true,
    maxed:      maxed,
    width:      sheetWidth,
    height:     sheetHeight,
    onClose:    onClose,
    onMaximize: onMaximize,
    onTabClick: hooks.onTabClick || null,
  };
  var sheet = buildCharacterSheet(p, character, hooks.currentTab, sheetHooks);

  // Window wrapper — picks up the animated holoPop.
  var wrap = htmlEl('div', {
    'data-sheet-modal-wrap': maxed ? 'maxed' : 'normal',
    style: {
      width:    w,
      height:   h,
      maxWidth:  '95%',
      maxHeight: '95%',
      position: 'relative',
      animation: 'holoPop 220ms cubic-bezier(.4,.0,.2,1)',
    }
  }, [sheet]);

  // Backdrop scrim — clicking outside the window dismisses the modal.
  var backdropProps = {
    'data-sheet-mode': 'modal',
    style: {
      position: 'absolute', inset: 0, zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.55)',
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

  // Stop click-through on the window itself (so dragging inside doesn't
  // dismiss the modal). Matches the JSX e.stopPropagation pattern.
  wrap.addEventListener('click', function(e) { e.stopPropagation(); });

  return backdrop;
}

// Stateful convenience — owns the maxed toggle internally. Returns a
// handle { element, destroy } that assembled-client can mount and
// dismiss without re-implementing the state plumbing.
//
// `element` is a stable outer container; on state change the inner
// modal DOM is swapped under it. Callers can safely cache the
// reference (e.g., append once, query later) without re-fetching.
//
// The first render uses holoFade+holoPop animations (via the
// stateless builder); subsequent toggles re-render the inner modal
// — the backdrop animation replays, which matches the JSX behavior
// (React reconciles to a new VDOM tree on setMaxed too).
function createCharacterSheetModal(p, character, hooks) {
  hooks = hooks || {};
  character = character || TEY_V2_FIXTURE;

  // Internal state.
  var state = {
    maxed:      !!hooks.startMaxed,
    currentTab: hooks.startTab || 'SKILLS',
  };

  var onCloseUser = hooks.onClose || null;

  // Stable outer container — appended by caller; child swaps on
  // re-render. Using `display: contents` would be ideal but isn't
  // universally supported and would break absolute-positioned
  // children. Instead, we use an inline-style-free wrapper that
  // doesn't interfere with the inner modal's `position: absolute,
  // inset: 0` chrome — the wrapper just inherits its parent's box.
  var container = document.createElement('div');
  container.setAttribute('data-sheet-modal-container', '1');
  // The modal's backdrop uses `position: absolute, inset: 0`, so the
  // container needs `position: relative` (or absolute) for inset to
  // anchor correctly. Match the JSX assembled-client expectation:
  // the modal sits inside an already-positioned shell.
  container.style.position = 'absolute';
  container.style.inset = '0';
  container.style.zIndex = '200';
  container.style.pointerEvents = 'none';  // children re-enable

  function _onMaximize() {
    state.maxed = !state.maxed;
    _rerenderInner();
    if (typeof hooks.onMaximize === 'function') {
      hooks.onMaximize(state.maxed);
    }
  }

  function _onTabClick(tabId) {
    state.currentTab = tabId;
    _rerenderInner();
    if (typeof hooks.onTabClick === 'function') {
      hooks.onTabClick(tabId);
    }
  }

  function _buildInner() {
    var modal = buildCharacterSheetModal(p, character, {
      maxed:        state.maxed,
      currentTab:   state.currentTab,
      width:        hooks.width,
      height:       hooks.height,
      maxedWidth:   hooks.maxedWidth,
      maxedHeight:  hooks.maxedHeight,
      onClose:      onCloseUser,
      onMaximize:   _onMaximize,
      onTabClick:   _onTabClick,
    });
    // Re-enable pointer events on the modal (container disabled them
    // so the underlying app stays clickable when no modal is mounted).
    modal.style.pointerEvents = 'auto';
    return modal;
  }

  function _rerenderInner() {
    while (container.firstChild) container.removeChild(container.firstChild);
    container.appendChild(_buildInner());
  }

  container.appendChild(_buildInner());

  return {
    element: container,
    getState: function() {
      return { maxed: state.maxed, currentTab: state.currentTab };
    },
    setTab: function(tabId) {
      _onTabClick(tabId);
    },
    setMaxed: function(v) {
      if (!!v === state.maxed) return;
      _onMaximize();
    },
    destroy: function() {
      while (container.firstChild) container.removeChild(container.firstChild);
      if (container.parentNode) container.parentNode.removeChild(container);
    },
  };
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3Sheet = {
  SCHEMA_VERSION: 1,

  // Wiring
  init: init,

  // Top-level
  buildCharacterSheet:       buildCharacterSheet,
  buildCharacterSheetModal:  buildCharacterSheetModal,   // Drop 4.12a
  createCharacterSheetModal: createCharacterSheetModal,  // Drop 4.12a

  // Tab body renderers
  buildSheetHeader:       buildSheetHeader,
  buildSheetVitals:       buildSheetVitals,
  buildSheetSkills:       buildSheetSkills,
  buildSheetGear:         buildSheetGear,
  buildSheetWorld:        buildSheetWorld,
  buildSheetStory:        buildSheetStory,
  buildSheetForce:        buildSheetForce,

  // Sub-builders (public for caller composition)
  buildPaperDoll:         buildPaperDoll,
  buildFactionRadar:      buildFactionRadar,
  buildWoundFigure:       buildWoundFigure,
  buildCooldownWheel:     buildCooldownWheel,

  // Fixtures
  TEY_V2_FIXTURE:         TEY_V2_FIXTURE,
  STORY_NOUNS:            STORY_NOUNS,

  // Test reach
  _internal: {
    _htmlEl: htmlEl,
    _svgEl:  svgEl,
    _Section: Section,
    _highlightStoryNouns: highlightStoryNouns,
  },
};

})();
