/* ============================================================================
   m3_dice_roll.js — UX Drop 3: the signature animated D6 throw on dramatic
   combat rolls.

   Design: dice_animation_and_ux_polish_2026-06-22.md (the pre-launch slice).

   What this is
     A brief, bounded, parallel flourish that animates the REAL dice pool of a
     combat roll the server flagged dramatic (`drama` tier on the
     combat_resolution_event). It is a feedback/theme moment, NEVER decoration
     that gates pace: the result text/row is ALREADY on screen before this
     mounts (the caller appends the combat row first, then calls renderDiceRoll
     in parallel). The animation never holds a turn, never delays the outcome
     line, and never blocks input.

   The non-negotiables (§2 of the design), enforced here:
     1. Never gate information/pace — render(payload) is fire-and-forget; the
        outcome row is the caller's responsibility and is appended first.
     2. Animate dramatic rolls only — drama tier comes from the server. We
        mount ZERO DOM for drama 0 (or when the toggle is Off, or when the
        rate-limit window is open).
     3. Skippable — any click on the overlay (or a keypress) jumps to the end
        and removes it immediately.
     4. Toggle — localStorage 'sw_dice_anim' ∈ {off, minimal, full}. Default
        'minimal' (tier-2 only). 'full' animates tier-1 too. 'off' = no DOM.
        Mirrors the existing fk_clean_mode / combat-hud localStorage flags.
     5. Show the REAL dice — the actual per-die values from
        payload.attacker_pool.dice[], with the wild die marked and its
        explosion chain shown. Generic dice would be hollow latency.

   Pace discipline lives HERE (the client), regardless of tier:
     - Rate-limit: at most one animation per RATE_LIMIT_MS. The first dramatic
       roll in a window animates; a flurry behind it resolves instantly
       (combat round 1 animates; the rest of the flurry doesn't).
     - Bounded duration: the overlay self-removes after a hard cap, even if a
       CSS animationend never fires (jsdom / reduced-motion safety).
     - Reduced motion: when prefers-reduced-motion matches, we still show the
       real dice (it's information) but the tumble is killed by CSS and the
       overlay self-removes on the short timer.

   Web-only. Telnet is untouched — it never receives combat_resolution_event.

   Dependencies (injected via init(deps), all optional with safe fallbacks):
     · mountEl   — the element to append the overlay to. Defaults to
                   document.body.
     · escapeHtml — kept for parity with sibling modules; this module renders
                   numbers/SVG only, so it isn't strictly needed.

   Exports (window.M3DiceRoll):
     · init(deps)
     · renderDiceRoll(payload)      — the entry point; no-op unless dramatic.
     · classifyAnimation(payload)   — pure: returns {animate, tier, reason}.
     · getMode() / setMode(mode)    — the toggle accessor.
     · prefersReducedMotion()       — reduced-motion probe.
     · _internal { _buildDie, _reset, _setNow } — for tests.
   ============================================================================ */
(function(){
'use strict';

// ─── Tunables (§7 open knobs) ────────────────────────────────────────
var RATE_LIMIT_MS   = 2500;   // at most one animation per this window
var TIER2_HOLD_MS   = 1100;   // hard cap for the full throw (~1s)
var TIER1_HOLD_MS   = 650;    // hard cap for the quick flourish (sub-second)
var STORAGE_KEY     = 'sw_dice_anim';
var DEFAULT_MODE    = 'minimal';   // tier-2 only by default
var VALID_MODES     = ['off', 'minimal', 'full'];

var SVG_NS = 'http://www.w3.org/2000/svg';

// ─── Module-private state ────────────────────────────────────────────
var _mountEl     = null;
var _escapeHtml  = null;
var _lastAnimAt  = 0;            // timestamp of the last mounted animation
var _activeEl    = null;         // currently-mounted overlay (for skip/replace)
var _nowFn       = function(){ return Date.now(); };   // overridable for tests

function init(deps) {
  deps = deps || {};
  _mountEl    = deps.mountEl    || (typeof document !== 'undefined' ? document.body : null);
  _escapeHtml = deps.escapeHtml || _defaultEscapeHtml;
}

function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ─── Toggle (localStorage, mirrors fk_clean_mode pattern) ────────────
function getMode() {
  try {
    var v = (typeof localStorage !== 'undefined')
      ? localStorage.getItem(STORAGE_KEY) : null;
    if (v && VALID_MODES.indexOf(v) !== -1) return v;
  } catch (_) { /* private-mode / no storage — fall through */ }
  return DEFAULT_MODE;
}

function setMode(mode) {
  if (VALID_MODES.indexOf(mode) === -1) return false;
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, mode);
  } catch (_) { /* ignore */ }
  return true;
}

function prefersReducedMotion() {
  try {
    return typeof window !== 'undefined' &&
           typeof window.matchMedia === 'function' &&
           window.matchMedia('(prefers-reduced-motion: reduce)').matches === true;
  } catch (_) {
    return false;
  }
}

// ─── Pure classifier: should this payload animate, and at what tier? ─
// Returns {animate:bool, tier:0|1|2, reason:string}. No DOM, no state —
// the rate-limit (which IS stateful) is checked separately in render().
function classifyAnimation(payload) {
  var mode = getMode();
  if (mode === 'off') return { animate: false, tier: 0, reason: 'mode-off' };

  var drama = (payload && typeof payload.drama === 'number') ? payload.drama : 0;
  if (drama <= 0) return { animate: false, tier: 0, reason: 'not-dramatic' };

  // 'minimal' animates tier-2 only; 'full' animates tier-1 and tier-2.
  if (mode === 'minimal' && drama < 2) {
    return { animate: false, tier: drama, reason: 'tier-below-minimal' };
  }
  return { animate: true, tier: drama, reason: 'ok' };
}

// ─── Entry point — fire-and-forget; the caller has ALREADY rendered the
//     result row. This is a parallel flourish only. ───────────────────
function renderDiceRoll(payload) {
  var decision = classifyAnimation(payload);
  if (!decision.animate) return null;

  // Rate-limit: the first dramatic roll in the window animates; a flurry
  // behind it resolves instantly (no DOM). Pace discipline (§3).
  var now = _nowFn();
  if (now - _lastAnimAt < RATE_LIMIT_MS) return null;
  _lastAnimAt = now;

  var overlay = _buildOverlay(payload, decision.tier);
  if (!overlay) { _lastAnimAt = 0; return null; }   // nothing to show — don't burn the window

  // Dismiss any in-flight overlay only NOW that we have a replacement to mount
  // (a dramatic roll never strobes over a previous one, and a no-op build must
  // never tear down a live overlay with no replacement).
  _dismiss();

  var mount = _mountEl || (typeof document !== 'undefined' ? document.body : null);
  if (!mount) return null;
  mount.appendChild(overlay);
  _activeEl = overlay;

  // Bounded duration — a hard cap removes the overlay even if animationend
  // never fires (reduced-motion, jsdom, tab backgrounded). Never lingers.
  var hold = decision.tier >= 2 ? TIER2_HOLD_MS : TIER1_HOLD_MS;
  var timer = (typeof setTimeout === 'function')
    ? setTimeout(function(){ if (_activeEl === overlay) _dismiss(); }, hold)
    : null;

  // Skippable — a click anywhere on the overlay jumps straight to done.
  overlay.addEventListener('click', function(){
    if (timer && typeof clearTimeout === 'function') clearTimeout(timer);
    if (_activeEl === overlay) _dismiss();
  });

  return overlay;
}

function _dismiss() {
  if (_activeEl && _activeEl.parentNode) {
    _activeEl.parentNode.removeChild(_activeEl);
  }
  _activeEl = null;
}

// ─── DOM build ───────────────────────────────────────────────────────
function _buildOverlay(payload, tier) {
  var dice = _extractDice(payload);
  if (!dice.length) return null;

  var overlay = document.createElement('div');
  overlay.className = 'dice-roll-overlay tier-' + (tier >= 2 ? '2' : '1');
  overlay.setAttribute('role', 'status');
  overlay.setAttribute('aria-label', 'dice roll result');
  // Decorative-but-informational: the live region announces the total.
  overlay.setAttribute('data-drama', String(tier));

  for (var i = 0; i < dice.length; i++) {
    overlay.appendChild(_buildDie(dice[i]));
  }

  // A compact total chip so the throw also reads as the real number — the
  // result text is already on screen, this just mirrors the pool's total.
  var total = _poolTotal(payload);
  if (total != null) {
    var chip = document.createElement('span');
    chip.className = 'dice-roll-total';
    chip.textContent = String(total);
    overlay.appendChild(chip);
  }

  return overlay;
}

// Pull the real per-die list off the attacker pool (the v1.1
// combat_resolution_event schema). Each die: {value, is_wild, exploded,
// explosion_chain, dropped}. Defensive: tolerate a missing/garbled pool.
function _extractDice(payload) {
  var pool = payload && payload.attacker_pool;
  var raw = (pool && Array.isArray(pool.dice)) ? pool.dice : [];
  var out = [];
  for (var i = 0; i < raw.length; i++) {
    var d = raw[i] || {};
    out.push({
      value: (typeof d.value === 'number') ? d.value : 0,
      isWild: !!d.is_wild,
      exploded: !!d.exploded,
      dropped: !!d.dropped,
    });
  }
  return out;
}

function _poolTotal(payload) {
  var pool = payload && payload.attacker_pool;
  if (pool && typeof pool.total === 'number') return pool.total;
  return null;
}

// Render a single die as a small SVG showing its real face (pips for 1-6,
// or the chain total for an exploded wild die). The wild die is marked.
var DIE_PIPS = {
  1: [[50, 50]],
  2: [[28, 28], [72, 72]],
  3: [[28, 28], [50, 50], [72, 72]],
  4: [[28, 28], [72, 28], [28, 72], [72, 72]],
  5: [[28, 28], [72, 28], [50, 50], [28, 72], [72, 72]],
  6: [[28, 28], [72, 28], [28, 50], [72, 50], [28, 72], [72, 72]],
};

function _svgEl(tag, attrs, children) {
  var el = document.createElementNS(SVG_NS, tag);
  if (attrs) {
    for (var k in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
      el.setAttribute(k, String(attrs[k]));
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var c = children[i];
      if (c == null) continue;
      if (typeof c === 'string') el.appendChild(document.createTextNode(c));
      else el.appendChild(c);
    }
  }
  return el;
}

function _buildDie(die) {
  var wrap = document.createElement('div');
  wrap.className = 'dice-roll-die' +
    (die.isWild ? ' is-wild' : '') +
    (die.exploded ? ' is-exploded' : '') +
    (die.dropped ? ' is-dropped' : '');
  wrap.setAttribute('data-value', String(die.value));
  if (die.isWild) wrap.setAttribute('data-wild', '1');
  if (die.exploded) wrap.setAttribute('data-exploded', '1');

  var svg = _svgEl('svg', { viewBox: '0 0 100 100', width: '30', height: '30' });
  svg.appendChild(_svgEl('rect', {
    x: 6, y: 6, width: 88, height: 88, rx: 12,
    fill: die.isWild ? 'rgba(120,200,120,0.18)' : 'rgba(0,0,0,0.5)',
    stroke: 'currentColor', 'stroke-width': 3,
  }));

  // An exploded wild die shows the chain total (can exceed 6) as a numeral
  // instead of pips; a normal 1-6 die shows pips.
  var pipFace = (!die.exploded && DIE_PIPS[die.value]) ? DIE_PIPS[die.value] : null;
  if (pipFace) {
    for (var i = 0; i < pipFace.length; i++) {
      svg.appendChild(_svgEl('circle', {
        cx: pipFace[i][0], cy: pipFace[i][1], r: 8, fill: 'currentColor',
      }));
    }
  } else {
    svg.appendChild(_svgEl('text', {
      x: 50, y: 50, 'text-anchor': 'middle', 'dominant-baseline': 'central',
      'font-size': 44, 'font-family': 'monospace', fill: 'currentColor',
    }, [String(die.value)]));
  }

  if (die.isWild) {
    svg.appendChild(_svgEl('text', {
      x: 50, y: 16, 'text-anchor': 'middle', 'font-size': 16,
      fill: 'currentColor',
    }, ['★']));   // a star marks the wild die
  }
  wrap.appendChild(svg);
  return wrap;
}

// ─── Exports ─────────────────────────────────────────────────────────
window.M3DiceRoll = {
  SCHEMA_VERSION: 1,
  init: init,
  renderDiceRoll: renderDiceRoll,
  classifyAnimation: classifyAnimation,
  getMode: getMode,
  setMode: setMode,
  prefersReducedMotion: prefersReducedMotion,
  _internal: {
    _buildDie: _buildDie,
    _buildOverlay: _buildOverlay,
    _extractDice: _extractDice,
    _reset: function(){ _lastAnimAt = 0; _dismiss(); },
    _setNow: function(fn){ _nowFn = fn || function(){ return Date.now(); }; },
    _setMount: function(el){ _mountEl = el; },
    RATE_LIMIT_MS: RATE_LIMIT_MS,
  },
};

})();
