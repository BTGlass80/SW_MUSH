/* ============================================================================
   m3_skill_check.js — Skill-check ribbon showcase (non-combat WEG D6).

   Drop 4.11 · Tier 1 #4 · ported from map_v3/skill-check.jsx (669 JSX LOC)
   in SW_MUSH_UIUX_Bugfix_26May26.zip (May 27 2026).

   What this surface shows:
     The skill-check ribbon — the WEG D6 non-combat resolution surface.
     Each check is wrapped in scene context (room + setup pose), resolved
     with dice math, and closed with an outcome pose. Two variants ship:

       · UNOPPOSED  — player vs environment difficulty (DIFFICULTY_BANDS).
       · OPPOSED    — two characters compared (attacker.total vs defender.total).

     The showcase stacks both variants for designer/training contexts.
     Production wire-in (eventual): when the engine emits a skill-check
     resolution event, the SPA can swap in a single Unopposed or Opposed
     panel rather than the full showcase.

   What this module ships:
     · M3SkillCheck.buildSkillCheckShowcase(p, hooks?) full stacked showcase
     · M3SkillCheck.buildUnopposedCheck(p, check)      single unopposed panel
     · M3SkillCheck.buildOpposedCheck(p, check)        single opposed panel
     · M3SkillCheck.buildSceneStrip(p, scene)          scene context block
     · M3SkillCheck.buildPoseBlock(p, pose, kind)      setup/outcome pose
     · M3SkillCheck.buildSystemEffects(p, effects)     mechanical effects list
     · M3SkillCheck.buildPoolBlock(p, skill, mods, eff, accent) pool computation
     · M3SkillCheck.buildDiceRowSmall(p, dice, pip, total, accent) dice display
     · M3SkillCheck.buildDiffBlock(p, diff, band, accent) difficulty stack
     · M3SkillCheck.buildOpposedSide(p, side, accent)  one side of an opposed
     · M3SkillCheck.buildResultCallout(p, success, margin, tier, total, diff)
     · M3SkillCheck.buildDieMini(p, face, wild, explode, accent) single die SVG
     · M3SkillCheck.buildExampleHeader(p, num, label, sub) example separator
     · M3SkillCheck.SKILL_UNOPPOSED                    demo fixture (Streetwise)
     · M3SkillCheck.SKILL_OPPOSED                      demo fixture (Sneak vs Search)
     · M3SkillCheck.DIFFICULTY_BANDS                   WEG R&E difficulty table

   B3 era-cleanness:
     · Both fixtures are Tatooine / Mos Eisley locations (Chalmun's Cantina,
       Spaceport Customs Corridor B). The Wuher mention is Tatooine
       cantina lore — pre-CW and CW-stable (Wuher is a Tatooine native
       per Galaxy Guide 7).
     · Greedo is referenced as a Rodian bounty hunter — pre-CW and CW-era
       active (per Wookieepedia he's active in the years before 22 BBY).
     · Tey Voss is the standardized demo PC name (L5 fix from May 26
       bug-fix sprint).
     · Zero Empire / Imperial / TIE / X-wing / Stormtrooper / Rebel /
       Vader / Death Star / ISB references in the data block.

   Q1 canonical-character policy note (architecture v50 §6.2):
     The fixtures preserve the JSX source's references to Wuher (Tatooine
     cantina bartender) and Greedo (Rodian bounty hunter). Per v50 Q1,
     these are canonical characters. Wuher and Greedo are documented in
     the Mos Eisley canon and pre-date the GCW; using them as flavor
     references (rather than scene-controlling NPCs) is consistent with
     Drop 4.7 (holocron stat-block leaders), Drop 4.6 (sheet connections),
     Drop 4.10 (holonet Mace Windu). Flagged in the test suite for the
     dedicated Q1-hardening drop. Drop 4.11 preserves source-fidelity at
     the scaffold level.

   Dependencies (loaded earlier in the SPA load order):
     · None. This module is fully self-contained — no DI hooks beyond
       the optional escapeHtml passed via init(deps). Like m3_holonet,
       all rendering uses the local htmlEl/svgEl helpers.

   What this module does NOT ship:
     · No dice-roll animation logic. Dice fixtures are pre-rolled.
       Animation can layer on later via re-render with new fixtures.
     · No interactive difficulty-tweaking. The DiffBlock is presentational.
     · No real `+skill` command wire-in. Eventual integration: a slash
       command opens this surface populated from a live skill_check_event.

   Loading order in client.html: placed alongside m3_holonet.js in the
   SPA script-tag block. Self-contained — no cross-module references.
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

// ─── htmlEl / svgEl: same shape as Drops 4.5-4.10 ─────────────────────
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
// DIFFICULTY BANDS — WEG R&E difficulty table
// (R&E core p41 — Very Easy 1-5, Easy 6-10, Moderate 11-15, Difficult
//  16-20, Very Difficult 21-30, Heroic 31+. Fixture uses upper-bound
//  values 5/10/15/20/25/30 which matches band ceilings, ish — preserved
//  from JSX source.)
// ════════════════════════════════════════════════════════════════════
var DIFFICULTY_BANDS = [
  { label: 'Very Easy', v: 5,  color: 'green' },
  { label: 'Easy',      v: 10, color: 'green' },
  { label: 'Moderate',  v: 15, color: 'amber' },
  { label: 'Difficult', v: 20, color: 'amber' },
  { label: 'Very Diff.',v: 25, color: 'red'   },
  { label: 'Heroic',    v: 30, color: 'red'   },
];

// ════════════════════════════════════════════════════════════════════
// FIXTURES — Mos Eisley scene fixtures (Tey Voss demo character)
// (Preserves the bug-fix-sprint JSX source verbatim. Wuher / Greedo
//  references retained per source-fidelity policy; flagged for Q1
//  hardening sweep.)
// ════════════════════════════════════════════════════════════════════
var SKILL_UNOPPOSED = {
  kind: 'unopposed',
  scene: {
    room: "Chalmun's Cantina · Back Booth",
    zone: 'Cantina Row · Mos Eisley',
    desc: "Smoke-blue light from the bandstand globe. Three Sullustans share a sabacc hand at the next table. A Bith band is between sets — silence under the bar chatter.",
  },
  setupPose: {
    actor: 'TEY VOSS', verb: 'poses',
    text: "leans into the booth, voice low. 'Yenn says you saw a Rodian asking around about a Corellian smuggler. What did he look like?'",
  },
  actor: { name: 'TEY VOSS', side: 'self' },
  skill: {
    name: 'STREETWISE',
    attr: 'KNO',
    code: '5D',
    spec: { name: 'Mos Eisley', bonus: '+2D' },
  },
  intent: "Find out who's been asking around about you.",
  modifiers: [
    { label: 'Spec · Mos Eisley',   code: '+2D', positive: true },
    { label: 'Wounded',             code: '\u22121D', positive: false },
  ],
  effective: '6D',
  dice: [{face: 4}, {face: 5}, {face: 3}, {face: 5}, {face: 2}, {face: 6, wild: true, explode: 4}],
  pipBonus: 0,
  total: 23,
  difficulty: {
    band: 'Moderate',
    stack: [
      { label: 'Mos Eisley · Moderate',    v: 15 },
      { label: 'Crowd suspicious',         v: 3  },
      { label: 'Hutt favor (Yenn vouches)',v: -3, positive: true },
    ],
    total: 15,
  },
  result: { success: true, margin: 8, tier: 'good' },
  outcomePose: {
    actor: 'WUHER', verb: 'mutters',
    text: "wipes a glass, eyes flicking to the door. 'Green-skin. Bounty hunter rig. Been at the bar since suns-set asking after a Corellian woman. Name of Greedo. He's two stools down right now.'",
  },
  systemEffects: ['+1 holocron entry: Greedo \u00b7 Rodian bounty hunter', 'Greedo location marked on Holocarta'],
};

var SKILL_OPPOSED = {
  kind: 'opposed',
  scene: {
    room: 'Spaceport Customs \u00b7 Corridor B',
    zone: 'Mos Eisley Spaceport',
    desc: "Narrow service corridor between Customs and Bay 87. One overhead striplight stutters. A guard's footsteps echo from the next bend \u2014 boots, regular cadence.",
  },
  setupPose: {
    actor: 'TEY VOSS', verb: 'poses',
    text: "presses against the corridor wall, slows her breathing. The guard's pacing route brings him past the maintenance hatch every twelve seconds. She times it.",
  },
  attacker: {
    actor: { name: 'TEY VOSS',  side: 'self',    sideLabel: 'STEALTH' },
    skill: { name: 'SNEAK',     code: '3D+1' },
    modifiers: [
      { label: 'Padded armor (silent)', code: '+1D', positive: true },
      { label: 'Wounded',               code: '\u22121D', positive: false },
    ],
    effective: '3D+1',
    dice: [{face: 5}, {face: 4}, {face: 6, wild: true, explode: 3}],
    pipBonus: 1,
    total: 18,
  },
  defender: {
    actor: { name: 'CUSTOMS GUARD', side: 'hostile', sideLabel: 'DETECTION' },
    skill: { name: 'SEARCH', code: '3D+2' },
    modifiers: [
      { label: 'Dim corridor',  code: '\u22121D', positive: false },
    ],
    effective: '2D+2',
    dice: [{face: 3}, {face: 4}, {face: 5, wild: true}],
    pipBonus: 2,
    total: 14,
  },
  result: { winner: 'attacker', margin: 4 },
  outcomePose: {
    actor: 'SCENE', verb: '',
    text: "Tey slips past the guard's pacing route, into the shadow of the customs office wall. The chime of the security palm scanner is two corridors over. The guard's bootsteps fade. She's through.",
  },
  systemEffects: ['+1 covert ingress \u00b7 Customs interior unlocked'],
};

// ════════════════════════════════════════════════════════════════════
// TOP-LEVEL — renders both variants stacked for the showcase
// ════════════════════════════════════════════════════════════════════
function buildSkillCheckShowcase(p, hooks) {
  hooks = hooks || {};
  var width  = hooks.width  || 1280;
  var height = hooks.height || 920;
  var unopposed = hooks.unopposed || SKILL_UNOPPOSED;
  var opposed   = hooks.opposed   || SKILL_OPPOSED;

  // Header note
  var headerLabel = htmlEl('div', {
    style: { fontSize: 10, letterSpacing: 3, color: p.amber, fontWeight: 700 },
  }, ['\u25ae\u25ae SKILL CHECK RIBBON \u00b7 NON-COMBAT DICE RESOLUTION']);

  // Header body uses inline italic/bold spans. Build the children list.
  var headerBody = htmlEl('div', {
    style: { fontSize: 11.5, color: p.ink, marginTop: 3, fontFamily: "'IBM Plex Sans'" },
  }, [
    'In actual play, ONE roll happens at a time \u2014 wrapped in scene context, setup pose, dice math, outcome pose. Below are ',
    htmlEl('b', { style: { color: p.amber } }, ['two separate examples']),
    ' showing the two variants the ribbon handles: an ',
    htmlEl('i', { style: { color: p.cyan } }, ['unopposed']),
    ' check (you vs a difficulty) and an ',
    htmlEl('i', { style: { color: p.red } }, ['opposed']),
    " check (you vs another character).",
  ]);

  var header = htmlEl('div', {
    style: {
      padding: '10px 14px',
      background: 'linear-gradient(90deg, ' + p.amber + '11, transparent)',
      borderLeft: '3px solid ' + p.amber,
      flexShrink: 0,
    },
  }, [headerLabel, headerBody]);

  // Visual separator between Example 1 and Example 2
  var sepInner = htmlEl('span', {
    style: {
      fontSize: 9, letterSpacing: 4, color: p.inkDim,
      padding: '0 12px', background: '#000',
      position: 'relative', top: -14,
    },
  }, ['\u00b7 \u00b7 \u00b7 A DIFFERENT MOMENT, A DIFFERENT ROLL \u00b7 \u00b7 \u00b7']);

  var separator = htmlEl('div', {
    style: {
      margin: '4px 0',
      borderTop: '1px dashed ' + p.inkFaint,
      textAlign: 'center',
      paddingTop: 6,
    },
  }, [sepInner]);

  return htmlEl('div', {
    style: {
      width: width, height: height,
      position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + p.inkDim,
      padding: 22,
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      boxShadow: 'inset 0 0 40px ' + p.skyDeep + ', 0 0 0 1px #000, 0 20px 50px rgba(0,0,0,0.7)',
      display: 'flex', flexDirection: 'column', gap: 14,
      overflowY: 'auto',
    },
  }, [
    header,
    buildExampleHeader(p, '01', 'UNOPPOSED \u00b7 vs ENVIRONMENT DIFFICULTY',
                       "Streetwise to find out who's been asking around about you"),
    buildUnopposedCheck(p, unopposed),
    separator,
    buildExampleHeader(p, '02', 'OPPOSED \u00b7 vs ANOTHER CHARACTER\u2019S ROLL',
                       'Sneak vs Search \u2014 slipping past a customs guard'),
    buildOpposedCheck(p, opposed),
  ]);
}

function buildExampleHeader(p, num, label, sub) {
  var titleLine = htmlEl('div', {
    style: { display: 'flex', alignItems: 'baseline', gap: 12 },
  }, [
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 18, color: p.inkDim,
        fontWeight: 700, letterSpacing: 2,
      },
    }, ['EXAMPLE \u00b7 ' + num]),
    htmlEl('span', {
      style: { fontSize: 10, color: p.amber, letterSpacing: 2.5, fontWeight: 600 },
    }, [label]),
  ]);

  var subLine = htmlEl('div', {
    style: {
      fontSize: 10, color: p.inkDim, marginTop: 2, fontStyle: 'italic',
      fontFamily: "'IBM Plex Sans'",
    },
  }, [sub]);

  return htmlEl('div', {
    style: {
      padding: '6px 14px',
      borderLeft: '3px solid ' + p.inkDim,
      background: 'rgba(0,0,0,0.4)',
      flexShrink: 0,
    },
  }, [titleLine, subLine]);
}

// ════════════════════════════════════════════════════════════════════
// UNOPPOSED — player vs environment difficulty
// ════════════════════════════════════════════════════════════════════
function buildUnopposedCheck(p, check) {
  var c = check;

  // Header strip
  var unopposedChip = htmlEl('span', {
    style: {
      fontSize: 9, letterSpacing: 2.5, color: p.cyan, fontWeight: 700,
      padding: '2px 6px', border: '1px solid ' + p.cyan,
      background: p.cyan + '11',
    },
  }, ['UNOPPOSED']);

  var titleSpan = htmlEl('span', {
    style: {
      fontFamily: "'Space Grotesk'", fontSize: 16, fontWeight: 700,
      color: p.inkBright, letterSpacing: 1.5,
    },
  }, [c.actor.name + ' \u00b7 ' + c.skill.name]);

  var headerRow = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 10 },
  }, [unopposedChip, titleSpan]);

  var headerStrip = htmlEl('div', {
    style: {
      padding: '8px 14px',
      background: 'linear-gradient(90deg, ' + p.cyan + '22, transparent)',
      borderBottom: '1px solid ' + p.inkFaint,
      flexShrink: 0,
    },
  }, [headerRow]);

  // Dice-math grid (POOL + DIFF)
  var mathGrid = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  }, [
    buildPoolBlock(p, c.skill, c.modifiers, c.effective, p.cyan),
    buildDiffBlock(p, c.difficulty, c.difficulty.band, p.cyan),
  ]);

  // Scrolling content
  var body = htmlEl('div', {
    style: {
      flex: 1, overflowY: 'auto', padding: '12px 14px',
      display: 'flex', flexDirection: 'column', gap: 10,
    },
  }, [
    buildSceneStrip(p, c.scene),
    buildPoseBlock(p, c.setupPose, 'setup'),
    mathGrid,
    buildDiceRowSmall(p, c.dice, c.pipBonus, c.total, p.cyan),
    buildResultCallout(p, c.result.success, c.result.margin, c.result.tier,
                       c.total, c.difficulty.total),
    buildPoseBlock(p, c.outcomePose, 'outcome'),
    buildSystemEffects(p, c.systemEffects),
  ]);

  return htmlEl('div', {
    style: {
      background: 'rgba(0,0,0,0.35)',
      border: '1px solid ' + p.cyan + '66',
      borderLeft: '3px solid ' + p.cyan,
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    },
  }, [headerStrip, body]);
}

// ════════════════════════════════════════════════════════════════════
// OPPOSED — two characters compared
// ════════════════════════════════════════════════════════════════════
function buildOpposedCheck(p, check) {
  var c = check;
  var winnerC = c.result.winner === 'attacker' ? p.green : p.red;

  // Header strip — "SKILL_A vs SKILL_B"
  var opposedChip = htmlEl('span', {
    style: {
      fontSize: 9, letterSpacing: 2.5, color: p.amber, fontWeight: 700,
      padding: '2px 6px', border: '1px solid ' + p.amber,
      background: p.amber + '11',
    },
  }, ['OPPOSED']);

  var titleSpan = htmlEl('span', {
    style: {
      fontFamily: "'Space Grotesk'", fontSize: 16, fontWeight: 700,
      color: p.inkBright, letterSpacing: 1.5,
    },
  }, [
    c.attacker.skill.name,
    htmlEl('span', { style: { color: p.inkDim, margin: '0 6px' } }, ['vs']),
    c.defender.skill.name,
  ]);

  var headerRow = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 10 },
  }, [opposedChip, titleSpan]);

  var headerStrip = htmlEl('div', {
    style: {
      padding: '8px 14px',
      background: 'linear-gradient(90deg, ' + p.amber + '22, transparent)',
      borderBottom: '1px solid ' + p.inkFaint,
      flexShrink: 0,
    },
  }, [headerRow]);

  // Two-side dice math
  var sidesGrid = htmlEl('div', {
    style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  }, [
    buildOpposedSide(p, c.attacker, p.green),
    buildOpposedSide(p, c.defender, p.red),
  ]);

  // Margin reveal
  var attackerTotalSpan = htmlEl('span', {
    style: {
      fontFamily: "'Space Grotesk'", fontSize: 20, fontWeight: 700,
      color: winnerC, letterSpacing: 2,
      textShadow: '0 0 6px ' + winnerC,
    },
  }, [String(c.attacker.total)]);

  var vsLabel = htmlEl('span', {
    style: { fontSize: 11, color: p.inkDim, letterSpacing: 2 },
  }, ['vs']);

  var defenderColor = c.result.winner === 'defender' ? p.red : p.inkDim;
  var defenderOpacity = c.result.winner === 'defender' ? 1 : 0.55;
  var defenderTotalSpan = htmlEl('span', {
    style: {
      fontFamily: "'Space Grotesk'", fontSize: 20, fontWeight: 700,
      color: defenderColor, letterSpacing: 2, opacity: defenderOpacity,
    },
  }, [String(c.defender.total)]);

  var winnerLabel = c.result.winner === 'attacker'
    ? c.attacker.actor.sideLabel
    : c.defender.actor.sideLabel;
  var marginChip = htmlEl('span', {
    style: {
      fontSize: 11, color: winnerC, letterSpacing: 2, fontWeight: 700,
      padding: '3px 10px', border: '1px solid ' + winnerC,
    },
  }, [winnerLabel + ' +' + c.result.margin]);

  var marginReveal = htmlEl('div', {
    style: {
      padding: '8px 12px',
      background: winnerC + '22',
      border: '1px solid ' + winnerC,
      boxShadow: '0 0 12px ' + winnerC + '33, inset 0 0 12px ' + winnerC + '11',
      display: 'flex', alignItems: 'center', justifyContent: 'space-around',
    },
  }, [attackerTotalSpan, vsLabel, defenderTotalSpan, marginChip]);

  // Scrolling content
  var body = htmlEl('div', {
    style: {
      flex: 1, overflowY: 'auto', padding: '12px 14px',
      display: 'flex', flexDirection: 'column', gap: 10,
    },
  }, [
    buildSceneStrip(p, c.scene),
    buildPoseBlock(p, c.setupPose, 'setup'),
    sidesGrid,
    marginReveal,
    buildPoseBlock(p, c.outcomePose, 'outcome'),
    buildSystemEffects(p, c.systemEffects),
  ]);

  return htmlEl('div', {
    style: {
      background: 'rgba(0,0,0,0.35)',
      border: '1px solid ' + p.amber + '66',
      borderLeft: '3px solid ' + p.amber,
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    },
  }, [headerStrip, body]);
}

// ────────────────────────────────────────────────────────────────────
// OPPOSED SIDE — attacker or defender column
// ────────────────────────────────────────────────────────────────────
function buildOpposedSide(p, side, accent) {
  var nameRow = htmlEl('div', {
    style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' },
  }, [
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 12, color: accent,
        fontWeight: 700, letterSpacing: 1,
      },
    }, [side.actor.name]),
    htmlEl('span', {
      style: { fontSize: 9, color: accent, letterSpacing: 1.5, fontWeight: 600 },
    }, [side.actor.sideLabel]),
  ]);

  var skillLine = htmlEl('div', {
    style: { fontSize: 10, color: p.inkDim, marginTop: 2 },
  }, [side.skill.name + ' ' + side.skill.code]);

  // Modifiers
  var modRows = [];
  for (var i = 0; i < side.modifiers.length; i++) {
    var m = side.modifiers[i];
    var sign = m.positive ? '+' : '\u2212';
    var modRow = htmlEl('div', {
      style: {
        fontSize: 9, color: p.inkDim,
        display: 'flex', justifyContent: 'space-between',
      },
    }, [
      htmlEl('span', {}, [
        htmlEl('span', { style: { color: m.positive ? p.green : p.red } }, [sign]),
        ' ' + m.label,
      ]),
      htmlEl('span', {
        style: { color: m.positive ? p.green : p.red, fontWeight: 600 },
      }, [m.code]),
    ]);
    modRows.push(modRow);
  }

  var effRow = htmlEl('div', {
    style: {
      marginTop: 3, paddingTop: 3,
      borderTop: '1px dashed ' + p.inkFaint,
      display: 'flex', justifyContent: 'space-between',
      fontSize: 10,
    },
  }, [
    htmlEl('span', {
      style: { color: p.amber, letterSpacing: 1, fontWeight: 600 },
    }, ['EFF']),
    htmlEl('span', {
      style: { fontFamily: "'Space Grotesk'", color: p.inkBright, fontWeight: 700 },
    }, [side.effective]),
  ]);

  var modsContainer = htmlEl('div', { style: { marginTop: 6 } },
                              modRows.concat([effRow]));

  // Dice
  var diceChildren = [];
  for (var j = 0; j < side.dice.length; j++) {
    var d = side.dice[j];
    diceChildren.push(buildDieMini(p, d.face, d.wild, d.explode, accent));
  }
  if (side.pipBonus > 0) {
    diceChildren.push(htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 13, fontWeight: 700,
        color: p.inkBright,
      },
    }, ['+' + side.pipBonus]));
  }
  var diceRow = htmlEl('div', {
    style: {
      display: 'flex', gap: 4, marginTop: 8,
      alignItems: 'center', flexWrap: 'wrap',
    },
  }, diceChildren);

  // Total
  var totalRow = htmlEl('div', {
    style: {
      marginTop: 6, padding: '4px 8px',
      background: accent + '22', border: '1px solid ' + accent + '55',
      display: 'flex', justifyContent: 'space-between',
    },
  }, [
    htmlEl('span', {
      style: { fontSize: 9, color: p.inkDim, letterSpacing: 1.5 },
    }, ['TOTAL']),
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 16, color: accent,
        fontWeight: 700, lineHeight: 1,
      },
    }, [String(side.total)]),
  ]);

  return htmlEl('div', {
    style: {
      padding: 10,
      background: accent + '0a',
      border: '1px solid ' + accent + '55',
    },
  }, [nameRow, skillLine, modsContainer, diceRow, totalRow]);
}

// ────────────────────────────────────────────────────────────────────
// SCENE + POSE COMPONENTS
// ────────────────────────────────────────────────────────────────────
function buildSceneStrip(p, scene) {
  var label = htmlEl('div', {
    style: { fontSize: 9, letterSpacing: 3, color: p.inkDim },
  }, ['\u25b8 SCENE']);

  var roomName = htmlEl('div', {
    style: {
      fontFamily: "'Space Grotesk'", fontSize: 13, color: p.inkBright,
      letterSpacing: 0.5, fontWeight: 700, marginTop: 2,
      textShadow: '0 0 4px ' + p.amber + '44',
    },
  }, [scene.room]);

  var zoneLine = htmlEl('div', {
    style: { fontSize: 9, letterSpacing: 1.5, color: p.inkDim, marginTop: 1 },
  }, [scene.zone]);

  // The original JSX used `p.body` for desc color, which isn't a
  // documented palette key. Fall back to p.ink (the documented neutral
  // text color) for safety. The original visual intent was "soft body
  // text" — p.ink at 92% opacity matches the original style block.
  var descLine = htmlEl('div', {
    style: {
      fontFamily: "'IBM Plex Sans'", fontSize: 11.5,
      color: p.body || p.ink, lineHeight: 1.5,
      marginTop: 5, opacity: 0.92,
    },
  }, [scene.desc]);

  return htmlEl('div', {
    style: {
      padding: '8px 12px',
      background: 'linear-gradient(90deg, ' + p.amber + '18, transparent)',
      borderLeft: '3px solid ' + p.amber,
    },
  }, [label, roomName, zoneLine, descLine]);
}

function buildPoseBlock(p, pose, kind) {
  var isSelf   = pose.actor === 'TEY VOSS';
  var isSystem = pose.actor === 'SCENE';
  var c = isSelf ? p.green : isSystem ? p.inkDim : p.amber;
  var bg = isSelf   ? (p.green + '10')
        : isSystem  ? 'rgba(0,0,0,0.35)'
        :             (c + '10');

  var actorSpan = htmlEl('span', {
    style: {
      fontFamily: "'Space Grotesk'", fontSize: 11.5, color: c,
      fontWeight: 700, letterSpacing: 1,
    },
  }, [pose.actor]);

  var headChildren = [actorSpan];

  if (pose.verb) {
    headChildren.push(htmlEl('span', {
      style: { fontSize: 9.5, fontStyle: 'italic', color: p.inkDim },
    }, [pose.verb]));
  }

  var kindLabel = kind === 'setup'
    ? '\u25b8 TRIGGERS THE ROLL'
    : '\u2726 RESULT OF THE ROLL';
  headChildren.push(htmlEl('span', {
    style: {
      marginLeft: 'auto', fontSize: 8, color: p.inkFaint,
      letterSpacing: 1.5, fontWeight: 600,
    },
  }, [kindLabel]));

  var headRow = htmlEl('div', {
    style: { display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 3 },
  }, headChildren);

  var textBody = htmlEl('div', {
    style: {
      fontFamily: "'IBM Plex Sans'", fontSize: 12.5,
      color: p.inkBright, lineHeight: 1.6,
    },
  }, [pose.text]);

  return htmlEl('div', {
    style: {
      padding: '8px 12px',
      background: bg,
      borderLeft: '3px solid ' + c,
    },
  }, [headRow, textBody]);
}

function buildSystemEffects(p, effects) {
  if (!effects || effects.length === 0) return null;

  var children = [
    htmlEl('div', {
      style: { fontSize: 8, letterSpacing: 2, color: p.inkDim, marginBottom: 3 },
    }, ['\u25c7 SYSTEM EFFECTS']),
  ];

  for (var i = 0; i < effects.length; i++) {
    children.push(htmlEl('div', {
      style: {
        fontFamily: "'IBM Plex Mono'", fontSize: 10, color: p.amber, letterSpacing: 0.5,
      },
    }, ['\u203a ' + effects[i]]));
  }

  return htmlEl('div', {
    style: {
      padding: '6px 12px',
      background: 'rgba(0,0,0,0.4)',
      border: '1px dashed ' + p.inkFaint,
    },
  }, children);
}

// ────────────────────────────────────────────────────────────────────
// SHARED HELPERS
// ────────────────────────────────────────────────────────────────────
function buildPoolBlock(p, skill, mods, effective, accent) {
  var children = [
    htmlEl('div', {
      style: { fontSize: 8, letterSpacing: 2, color: p.inkDim, marginBottom: 4 },
    }, ['POOL']),
    htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between',
        fontSize: 10.5, color: p.inkBright,
      },
    }, [
      htmlEl('span', {}, [
        htmlEl('span', { style: { color: p.green, marginRight: 4 } }, ['+']),
        skill.name,
      ]),
      htmlEl('span', {
        style: { fontFamily: "'Space Grotesk'", color: p.green, fontWeight: 600 },
      }, [skill.code]),
    ]),
  ];

  if (skill.spec) {
    children.push(htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between',
        fontSize: 9.5, color: p.inkDim, paddingLeft: 10,
      },
    }, [
      htmlEl('span', {}, ['\u21b3 ' + skill.spec.name]),
      htmlEl('span', {
        style: { fontFamily: "'Space Grotesk'", color: p.amber, fontWeight: 600 },
      }, [skill.spec.bonus]),
    ]));
  }

  for (var i = 0; i < mods.length; i++) {
    var m = mods[i];
    var sign = m.positive ? '+' : '\u2212';
    children.push(htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between',
        fontSize: 9.5, color: p.ink,
      },
    }, [
      htmlEl('span', {}, [
        htmlEl('span', {
          style: { color: m.positive ? p.green : p.red, marginRight: 4 },
        }, [sign]),
        m.label,
      ]),
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'",
          color: m.positive ? p.green : p.red, fontWeight: 600,
        },
      }, [m.code]),
    ]));
  }

  children.push(htmlEl('div', {
    style: {
      marginTop: 5, paddingTop: 4,
      borderTop: '1px dashed ' + accent,
      display: 'flex', justifyContent: 'space-between',
    },
  }, [
    htmlEl('span', {
      style: { fontSize: 9, letterSpacing: 2, color: accent, fontWeight: 700 },
    }, ['EFFECTIVE']),
    htmlEl('span', {
      style: { fontFamily: "'Space Grotesk'", fontSize: 14, color: p.inkBright, fontWeight: 700 },
    }, [effective]),
  ]));

  return htmlEl('div', {
    style: {
      padding: '8px 10px',
      background: 'rgba(0,0,0,0.4)',
      border: '1px solid ' + p.inkFaint,
    },
  }, children);
}

function buildDiceRowSmall(p, dice, pipBonus, total, accent) {
  var diceChildren = [];
  for (var i = 0; i < dice.length; i++) {
    var d = dice[i];
    diceChildren.push(buildDieMini(p, d.face, d.wild, d.explode,
                                   d.wild ? p.green : accent));
  }
  if (pipBonus > 0) {
    diceChildren.push(htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 18, fontWeight: 700,
        color: p.inkBright, marginLeft: 4,
      },
    }, ['+' + pipBonus]));
  }

  var diceRow = htmlEl('div', {
    style: {
      display: 'flex', gap: 5, alignItems: 'center',
      justifyContent: 'center', flexWrap: 'wrap',
    },
  }, diceChildren);

  var sumRow = htmlEl('div', {
    style: {
      paddingTop: 5, borderTop: '1px dashed ' + p.inkFaint,
      display: 'flex', justifyContent: 'space-between',
    },
  }, [
    htmlEl('span', {
      style: { fontSize: 9, letterSpacing: 2, color: p.inkDim },
    }, ['SUM']),
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 20,
        color: p.inkBright, fontWeight: 700,
      },
    }, [String(total)]),
  ]);

  return htmlEl('div', {
    style: {
      padding: '8px 10px',
      background: 'rgba(0,0,0,0.4)',
      border: '1px solid ' + p.inkFaint,
      display: 'flex', flexDirection: 'column', gap: 6,
    },
  }, [
    htmlEl('div', {
      style: { fontSize: 8, letterSpacing: 2, color: p.inkDim },
    }, ['DICE \u00b7 WILD \u2605']),
    diceRow,
    sumRow,
  ]);
}

function buildDiffBlock(p, diff, band, accent) {
  // Find band color (preserve JSX source semantics).
  var bandData = null;
  for (var k = 0; k < DIFFICULTY_BANDS.length; k++) {
    if (DIFFICULTY_BANDS[k].label === band) {
      bandData = DIFFICULTY_BANDS[k];
      break;
    }
  }
  var bandColor = bandData
    ? (bandData.color === 'green' ? p.green
       : bandData.color === 'amber' ? p.amber
       : p.red)
    : p.red;

  var headerRow = htmlEl('div', {
    style: {
      display: 'flex', justifyContent: 'space-between',
      alignItems: 'baseline', marginBottom: 4,
    },
  }, [
    htmlEl('span', {
      style: { fontSize: 8, letterSpacing: 2, color: p.inkDim },
    }, ['DIFFICULTY \u00b7 BAND']),
    htmlEl('span', {
      style: {
        fontSize: 8, color: bandColor, letterSpacing: 1.5, fontWeight: 700,
        padding: '1px 5px', border: '1px solid ' + bandColor,
      },
    }, [band.toUpperCase()]),
  ]);

  var stackRows = [];
  for (var i = 0; i < diff.stack.length; i++) {
    var s = diff.stack[i];
    var sign = s.v >= 0 ? '+' : '\u2212';
    stackRows.push(htmlEl('div', {
      style: {
        display: 'flex', justifyContent: 'space-between',
        fontSize: 9.5, color: p.ink,
      },
    }, [
      htmlEl('span', {}, [
        htmlEl('span', {
          style: {
            color: s.positive ? p.green : p.inkDim,
            marginRight: 4,
          },
        }, [sign]),
        s.label,
      ]),
      htmlEl('span', {
        style: {
          fontFamily: "'Space Grotesk'",
          color: s.positive ? p.green : p.inkBright,
          fontWeight: 600,
        },
      }, [String(Math.abs(s.v))]),
    ]));
  }

  var targetRow = htmlEl('div', {
    style: {
      marginTop: 5, paddingTop: 4,
      borderTop: '1px dashed ' + accent,
      display: 'flex', justifyContent: 'space-between',
    },
  }, [
    htmlEl('span', {
      style: { fontSize: 9, letterSpacing: 2, color: accent, fontWeight: 700 },
    }, ['TARGET']),
    htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 14,
        color: p.inkBright, fontWeight: 700,
      },
    }, [String(diff.total)]),
  ]);

  return htmlEl('div', {
    style: {
      padding: '8px 10px',
      background: 'rgba(0,0,0,0.4)',
      border: '1px solid ' + p.inkFaint,
    },
  }, [headerRow].concat(stackRows).concat([targetRow]));
}

function buildResultCallout(p, success, margin, tier, total, diff) {
  var c = success ? p.green : p.red;
  var tierLabel = tier === 'spectacular'  ? 'SPECTACULAR'
                : tier === 'good'         ? 'CLEAN'
                : tier === 'marginal'     ? 'MARGINAL'
                : tier === 'catastrophic' ? 'CATASTROPHIC'
                : null;

  var headline = htmlEl('div', {
    style: {
      fontFamily: "'Space Grotesk'", fontSize: 18, fontWeight: 700,
      letterSpacing: 3, color: c,
      textShadow: '0 0 8px ' + c,
    },
  }, ['\u25b8 ' + (success ? 'SUCCESS' : 'FAILURE')
       + ' \u00b7 ' + total + ' vs ' + diff]);

  var subLineChildren = [
    'MARGIN ',
    htmlEl('span', { style: { color: c, fontWeight: 700 } }, [String(margin)]),
  ];
  if (tierLabel) {
    subLineChildren.push(' \u00b7 ');
    subLineChildren.push(
      htmlEl('span', { style: { color: c, fontWeight: 700 } }, [tierLabel])
    );
  }

  var subLine = htmlEl('div', {
    style: { fontSize: 10, color: p.inkBright, letterSpacing: 2, marginTop: 3 },
  }, subLineChildren);

  return htmlEl('div', {
    style: {
      padding: '8px 14px',
      background: 'linear-gradient(90deg, ' + c + '33, ' + c + '11, ' + c + '33)',
      border: '2px solid ' + c,
      boxShadow: '0 0 14px ' + c + '55, inset 0 0 14px ' + c + '11',
      textAlign: 'center',
    },
  }, [headline, subLine]);
}

// ────────────────────────────────────────────────────────────────────
// DieMini — recursive SVG die with optional explode chain
// ────────────────────────────────────────────────────────────────────
var DIE_PIPS = {
  1: [[50, 50]],
  2: [[28, 28], [72, 72]],
  3: [[28, 28], [50, 50], [72, 72]],
  4: [[28, 28], [72, 28], [28, 72], [72, 72]],
  5: [[28, 28], [72, 28], [50, 50], [28, 72], [72, 72]],
  6: [[28, 28], [72, 28], [28, 50], [72, 50], [28, 72], [72, 72]],
};

function buildDieMini(p, face, wild, explode, accent) {
  var color = wild ? p.green : (accent || p.amber);

  // SVG body
  var svgChildren = [
    svgEl('rect', {
      x: 6, y: 6, width: 88, height: 88, rx: 10,
      fill: wild ? (color + '22') : 'rgba(0,0,0,0.55)',
      stroke: color, strokeWidth: 3,
    }),
  ];

  var pips = DIE_PIPS[face] || [];
  for (var i = 0; i < pips.length; i++) {
    var pip = pips[i];
    svgChildren.push(svgEl('circle', {
      cx: pip[0], cy: pip[1], r: 7, fill: color,
    }));
  }

  if (wild) {
    svgChildren.push(svgEl('text', {
      x: 50, y: 18, fontSize: 10, textAnchor: 'middle',
      fill: color, fontFamily: 'IBM Plex Mono',
    }, ['\u2605']));
  }

  var svg = svgEl('svg', {
    viewBox: '0 0 100 100', width: 28, height: 28,
    style: { filter: 'drop-shadow(0 0 3px ' + color + '55)' },
  }, svgChildren);

  var children = [svg];

  if (explode != null) {
    children.push(htmlEl('span', {
      style: {
        fontFamily: "'Space Grotesk'", fontSize: 12, fontWeight: 700, color: color,
      },
    }, ['+']));
    // The exploded die is itself a Wild visually (per JSX: `wild` flag set true).
    children.push(buildDieMini(p, explode, true, undefined, accent));
  }

  return htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 3 },
  }, children);
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3SkillCheck = {
  SCHEMA_VERSION: 1,

  init:                      init,

  // Top-level
  buildSkillCheckShowcase:   buildSkillCheckShowcase,
  buildExampleHeader:        buildExampleHeader,

  // Single-check builders
  buildUnopposedCheck:       buildUnopposedCheck,
  buildOpposedCheck:         buildOpposedCheck,
  buildOpposedSide:          buildOpposedSide,

  // Scene / pose / effects
  buildSceneStrip:           buildSceneStrip,
  buildPoseBlock:            buildPoseBlock,
  buildSystemEffects:        buildSystemEffects,

  // Math primitives
  buildPoolBlock:            buildPoolBlock,
  buildDiceRowSmall:         buildDiceRowSmall,
  buildDiffBlock:            buildDiffBlock,
  buildResultCallout:        buildResultCallout,
  buildDieMini:              buildDieMini,

  // Fixtures + constants
  SKILL_UNOPPOSED:           SKILL_UNOPPOSED,
  SKILL_OPPOSED:             SKILL_OPPOSED,
  DIFFICULTY_BANDS:          DIFFICULTY_BANDS,

  _internal: {
    _htmlEl: htmlEl,
    _svgEl:  svgEl,
  },
};

})();
