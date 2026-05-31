/* ============================================================================
   m3_tokens.js — shared constants and helpers for the SPA map_v3 surfaces.

   Drop 4.1a · Tier 1 #4 · ported from map_v3/tokens.jsx (May 26 2026).
   Drop 4.1b · added svgEl() helper for use by all subsequent SVG-generating
              modules (m3_assets_*, m3_composition_engine). See bottom of file.

   Today this module holds:
     - WOUND_RUNGS / woundRung   — canonical 7-rung wound ladder
                                   (mirrors engine/character.py WoundLevel)
     - svgEl / SVG_NS            — boilerplate-free SVG element creation

   client.html ALSO defines a WOUND_RUNGS constant (Drop A, line 4231),
   from the original Tier 1 #1/#2 prototype port. The two arrays match in
   structure but use slightly different field names (the original uses
   `pen`/`sev`/`color`; this one adds `labelLong` for full-text rendering
   in sheets, per Tier 1 #3 B4/L3 unification).

   When the SPA replaces the legacy combat HUD in Drop 4.3, the legacy
   WOUND_RUNGS in client.html becomes vestigial and can be removed; until
   then both exist side-by-side and consumers pick the right one based on
   which UI surface they render into.
   ============================================================================ */
(function(){
'use strict';

// Mirrors engine/character.py WoundLevel(IntEnum) — all 7 values, 0..6.
// Each rung carries a compact `label` (chips, HUD) AND a full `labelLong`
// (sheets, dossiers). `pen` is the dice penalty applied to actions at that
// rung; STUNNED's penalty comes from the stun_timers count, not the rung,
// so its `pen` is empty. `sev` lets a consumer choose a palette color
// without hard-coding hex values here.
var WOUND_RUNGS = [
  { v: 0, label: 'HEALTHY',     labelLong: 'HEALTHY',           pen: '',    sev: 'ok'   },
  { v: 1, label: 'STUNNED',     labelLong: 'STUNNED',           pen: '',    sev: 'warn' },
  { v: 2, label: 'WOUNDED',     labelLong: 'WOUNDED',           pen: '-1D', sev: 'warn' },
  { v: 3, label: 'WOUNDED ×2',  labelLong: 'WOUNDED TWICE',     pen: '-2D', sev: 'hurt' },
  { v: 4, label: 'INCAP',       labelLong: 'INCAPACITATED',     pen: '',    sev: 'crit' },
  { v: 5, label: 'MORTAL',      labelLong: 'MORTALLY WOUNDED',  pen: '',    sev: 'crit' },
  { v: 6, label: 'DEAD',        labelLong: 'DEAD',              pen: '',    sev: 'dead' }
];

// Lookup helper. Defaults to HEALTHY on out-of-range input rather than
// returning undefined; consumers that render the rung always get a row.
function woundRung(level) {
  for (var i = 0; i < WOUND_RUNGS.length; i++) {
    if (WOUND_RUNGS[i].v === level) return WOUND_RUNGS[i];
  }
  return WOUND_RUNGS[0];
}

// ────────────────────────────────────────────────────────────────────
// SVG creation helper.
//
// Drop 4.1b added this so the asset/composition modules don't need to
// hand-write the verbose document.createElementNS('http://www.w3.org/...')
// + setAttribute() + appendChild() boilerplate for every shape.
//
// Usage:
//   var rect = M3Tokens.svgEl('rect', { x: 10, y: 10, width: 80, height: 80,
//                                       fill: '#b46a3a', stroke: '#ffd07a' });
//   var g    = M3Tokens.svgEl('g', { transform: 'translate(50 50)' }, [rect]);
//
// Attribute names match SVG conventions (kebab-case for stroke-width,
// stroke-dasharray, etc.). camelCase aliases (strokeWidth, strokeDasharray)
// are accepted and auto-converted because the JSX prototypes use camelCase.
//
// children: an array of Element objects to appendChild. Strings are treated
// as text content (set via textContent). null/undefined entries are skipped.
//
// Returns the created SVG element.
// ────────────────────────────────────────────────────────────────────
var SVG_NS = 'http://www.w3.org/2000/svg';

// Attribute keys that need camelCase → kebab-case conversion when set
// via setAttribute(). Listed explicitly rather than auto-detected so
// non-style attrs (viewBox, gradientUnits, etc.) keep their camelCase.
var SVG_ATTR_KEBAB = {
  strokeWidth:     'stroke-width',
  strokeDasharray: 'stroke-dasharray',
  strokeLinecap:   'stroke-linecap',
  strokeLinejoin:  'stroke-linejoin',
  strokeOpacity:   'stroke-opacity',
  fillOpacity:     'fill-opacity',
  fontFamily:      'font-family',
  fontSize:        'font-size',
  fontWeight:      'font-weight',
  textAnchor:      'text-anchor',
  clipPath:        'clip-path'
};

function svgEl(tag, attrs, children) {
  var el = document.createElementNS(SVG_NS, tag);
  if (attrs) {
    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      var val = attrs[key];
      if (val === null || val === undefined || val === false) continue;
      var attrName = SVG_ATTR_KEBAB[key] || key;
      el.setAttribute(attrName, String(val));
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === null || child === undefined) continue;
      if (typeof child === 'string') {
        el.appendChild(document.createTextNode(child));
      } else {
        el.appendChild(child);
      }
    }
  }
  return el;
}

window.M3Tokens = {
  WOUND_RUNGS: WOUND_RUNGS,
  woundRung: woundRung,
  svgEl: svgEl,
  SVG_NS: SVG_NS
};

})();
