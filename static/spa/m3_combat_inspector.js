/* ============================================================================
   m3_combat_inspector.js — D' (combat_resolution_event) rendering surface.

   Drop 4.4 · Tier 1 #4 · ported from the D' block in static/client.html
   (lines 9591–10054 of the May 26 2026 HEAD).

   Drop D' itself shipped earlier: engine factory (engine/combat_events.py),
   engine wiring (engine/combat.py:_build_resolution_event), parser broadcast
   (parser/combat_commands.py), 76 engine-side tests in
   tests/test_field_kit_drop_d_prime.py.

   Drop 4.3 added a marker-based extraction harness so the 15 rendering
   functions could be exercised in jsdom without depending on the full
   client.html being parseable (a pre-existing showToast bug at ~line 7434
   blocked whole-file eval).

   Drop 4.4 — this module — replaces the marker-extract pattern with a
   proper SPA module. The same 15 functions are now defined inside an IIFE
   that exports a single namespaced object. client.html keeps two thin
   delegators (handleCombatResolutionEvent and isDuplicateOfRecentCombatEvent
   are called from the WS router and the legacy pose-text dedup site
   respectively); they just forward to this module. The window._sw_*
   convenience exposures are preserved for browser-console use.

   What this does NOT change:
     · CSS: the .cri-* class rules continue to live in client.html's
       <style> block — they're loaded once per page and don't belong in
       a per-feature module.
     · Behavior: every rendering path is byte-identical to what Drop 4.3
       locked. The 29 regression tests in
       tests/spa/test_combat_inspector_d_prime_client.py must still pass.
     · The two call-sites in client.html (line 4791
       isDuplicateOfRecentCombatEvent, line 10378
       handleCombatResolutionEvent) keep their existing names; client.html
       defines thin functions that forward to this module's exports.

   Dependency injection. The original block referenced five ambient
   client.html symbols (escapeHtml, stripAnsi, appendEvent, rememberActorName,
   lastHud). Rather than re-defining them inside the module, the module
   accepts them via M3CombatInspector.init(deps) at load time. lastHud is
   passed as a getter (getLastHud) rather than a value because client.html
   reassigns lastHud on every HUD update — capturing a stale reference
   would break the viewer-role computation.

   Loading order. The module must load AFTER any module that defines
   the helpers it needs (escapeHtml, stripAnsi etc.) — but those helpers
   live in client.html's inline script, so the actual ordering is:
   <script src=".../m3_combat_inspector.js"></script> can load before the
   inline <script>, but the inline script must call M3CombatInspector.init()
   BEFORE the first WS message arrives. client.html does this near the top
   of its boot sequence.
   ============================================================================ */
(function(){
'use strict';

// ─── Module-private state ────────────────────────────────────────────
// The dependency-injected helpers. Populated by init().
var _escapeHtml        = null;
var _stripAnsi         = null;
var _appendEvent       = null;
var _rememberActorName = null;
var _getLastHud        = null;

// AC10 dedup state. Lives at module scope so the WS dispatcher and the
// legacy-text suppressor both see the same fingerprint window.
var combatEventFingerprints = [];  // [{sig, ts}, ...]
var COMBAT_DEDUP_WINDOW_MS  = 250;

// ─── Init: bind ambient helpers ──────────────────────────────────────
// Called once from client.html after the script tag loads. Pass the
// hostsite-defined helpers. Idempotent (re-calling overwrites).
function init(deps) {
  deps = deps || {};
  _escapeHtml        = deps.escapeHtml        || _defaultEscapeHtml;
  _stripAnsi         = deps.stripAnsi         || _defaultStripAnsi;
  _appendEvent       = deps.appendEvent       || _noopAppendEvent;
  _rememberActorName = deps.rememberActorName || _noopRememberActorName;
  _getLastHud        = deps.getLastHud        || _defaultGetLastHud;
}

// Defaults — used when init() is omitted (tests, or accidental early use).
// They're intentionally minimal: escapeHtml is real (the rendering needs
// it); the side-effect stubs are no-ops; getLastHud returns null so role
// defaults to bystander.
function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function _defaultStripAnsi(s) {
  return String(s == null ? '' : s).replace(/\x1b\[[0-9;]*m/g, '');
}
function _noopAppendEvent(ev) { /* discarded */ }
function _noopRememberActorName(name) { /* discarded */ }
function _defaultGetLastHud() { return null; }

// ─── Dedup helpers (AC10) ────────────────────────────────────────────
function recordCombatEventFingerprint(text) {
  if (!text) return;
  var sig = (text + '').replace(/\s+/g, ' ').trim().slice(0, 80).toLowerCase();
  if (!sig) return;
  combatEventFingerprints.push({ sig: sig, ts: Date.now() });
  var cutoff = Date.now() - COMBAT_DEDUP_WINDOW_MS;
  while (combatEventFingerprints.length > 0 && combatEventFingerprints[0].ts < cutoff) {
    combatEventFingerprints.shift();
  }
}

function isDuplicateOfRecentCombatEvent(rawText) {
  if (!rawText) return false;
  var sig = (_stripAnsi(rawText) + '').replace(/\s+/g, ' ').trim().slice(0, 80).toLowerCase();
  if (!sig) return false;
  var cutoff = Date.now() - COMBAT_DEDUP_WINDOW_MS;
  for (var i = combatEventFingerprints.length - 1; i >= 0; i--) {
    var fp = combatEventFingerprints[i];
    if (fp.ts < cutoff) break;
    if (sig.indexOf(fp.sig) !== -1 || fp.sig.indexOf(sig) !== -1) return true;
  }
  return false;
}

// ─── WS dispatcher (AC4) ─────────────────────────────────────────────
function handleCombatResolutionEvent(msg) {
  if (!msg) return;
  // Schema sanity guard — refuse to render mismatched protocol versions
  // rather than show wrong data. The factory currently emits
  // schema_version=1; bump on breaking change.
  if (msg.schema_version != null && msg.schema_version !== 1) {
    return;  // silent drop; logging here would just spam
  }

  // Compute viewer role for default expand state.
  var lastHud = _getLastHud();
  var myId = (lastHud && lastHud.character_id) || null;
  var actorId  = msg.actor  && msg.actor.id;
  var targetId = msg.target && msg.target.id;
  var role = 'bystander';
  if (myId != null) {
    if (actorId === myId)       role = 'self';
    else if (targetId === myId) role = 'target';
  }

  // Track names so the pose classifier knows them.
  if (msg.actor  && msg.actor.name)  _rememberActorName(msg.actor.name);
  if (msg.target && msg.target.name) _rememberActorName(msg.target.name);

  _appendEvent({
    t: 'combat-result',
    payload: msg,
    role: role,
    expanded: (role === 'self' || role === 'target'),
  });

  // Fingerprint the legacy two-line content for dedup. The engine still
  // emits the existing story line + mechanics line via broadcast_to_room
  // for telnet compatibility; on WebSocket sessions we suppress those
  // when the structured event arrived first.
  recordCombatEventFingerprint(composeCombatHeadline(msg));
  recordCombatEventFingerprint(composeCombatMechline(msg));
}

// ─── Pure helpers: skill → verb ──────────────────────────────────────
function combatVerbForSkill(skill) {
  var s = (skill || '').toLowerCase();
  if (s.indexOf('lightsaber') !== -1) return 'strikes';
  if (s.indexOf('blaster') !== -1 || s.indexOf('gunnery') !== -1) return 'blasts';
  if (s.indexOf('brawling') !== -1) return 'punches';
  if (s.indexOf('thrown') !== -1)   return 'throws at';
  if (s.indexOf('melee') !== -1)    return 'attacks';
  if (s.indexOf('missile') !== -1)  return 'fires at';
  if (s.indexOf('vehicle') !== -1)  return 'fires at';
  return 'attacks';
}

// ─── Plain-text composers (used for dedup matching) ──────────────────
function composeCombatHeadline(msg) {
  // Reproduces the engine's "<actor> <verb> <target> with <weapon>" story
  // line so the dedup matcher can suppress the parallel text broadcast.
  // Exact byte-match isn't required — dedup is a case-insensitive
  // substring match on the first 80 chars.
  var a = (msg.actor  && msg.actor.name)  || '?';
  var t = (msg.target && msg.target.name) || '?';
  var w = msg.action && msg.action.weapon_name;
  var skill = (msg.action && msg.action.skill) || '';
  var verb = combatVerbForSkill(skill);
  var weaponPart = w ? (' with ' + w) : '';
  var outcome = msg.hit ? 'HIT' : 'MISS';
  var wound = (msg.wound_outcome && msg.wound_outcome.display_name) || '';
  return a + ' ' + verb + ' ' + t + weaponPart + ' — ' + outcome +
         (wound ? ' — ' + wound : '');
}

function composeCombatMechline(msg) {
  var atk = (msg.attacker_pool && msg.attacker_pool.total != null)
              ? msg.attacker_pool.total : 0;
  var defTotal;
  if (msg.defender_pool && msg.defender_pool.total != null) {
    defTotal = msg.defender_pool.total;
  } else if (msg.difficulty && msg.difficulty.number != null) {
    defTotal = msg.difficulty.number;
  } else {
    defTotal = 0;
  }
  var parts = ['Roll: ' + atk + ' vs ' + defTotal];
  if (msg.hit && msg.damage_pool && msg.soak) {
    parts.push('Damage ' + (msg.damage_pool.total || 0) +
               ' vs Soak ' + (msg.soak.total || 0));
    if (msg.wound_outcome && msg.wound_outcome.display_name) {
      parts.push('→ ' + msg.wound_outcome.display_name);
    }
  }
  return '(' + parts.join(' · ') + ')';
}

// ─── DOM renderers ───────────────────────────────────────────────────
function buildCombatResultRow(ev) {
  var msg = ev.payload || {};
  var role = ev.role || 'bystander';
  var expanded = !!ev.expanded;

  var row = document.createElement('div');
  row.className = 'pose-row row-combat-result';
  if (role === 'self')   row.classList.add('is-self');
  if (role === 'target') row.classList.add('is-target');

  // ── Summary (always visible, clickable to toggle inspector) ─────
  var summary = document.createElement('div');
  summary.className = 'cri-summary' + (expanded ? ' expanded' : '');
  summary.innerHTML =
    '<span class="cri-chevron">▶</span>' +
    '<span class="cri-headline">' + buildCombatHeadlineHtml(msg) + '</span>';
  row.appendChild(summary);

  // ── Mechanics line (always visible, dim) ────────────────────────
  var mech = document.createElement('div');
  mech.className = 'cri-mechline';
  mech.textContent = composeCombatMechline(msg);
  row.appendChild(mech);

  // ── Inspector body (collapsible via .expanded ~ .cri-body) ──────
  var body = document.createElement('div');
  body.className = 'cri-body';
  body.appendChild(buildAttackerSection(msg));
  if (msg.action && msg.action.is_opposed) {
    body.appendChild(buildDefenderSection(msg));
  } else {
    body.appendChild(buildDifficultySection(msg));
  }
  if (msg.hit && msg.damage_pool) body.appendChild(buildDamageSection(msg));
  if (msg.hit && msg.soak)        body.appendChild(buildSoakSection(msg));
  body.appendChild(buildWoundSection(msg));
  body.appendChild(buildSourceLegend());
  row.appendChild(body);

  summary.addEventListener('click', function() {
    summary.classList.toggle('expanded');
  });

  return row;
}

function buildCombatHeadlineHtml(msg) {
  var a = (msg.actor  && msg.actor.name)  || '?';
  var t = (msg.target && msg.target.name) || '?';
  var w = msg.action && msg.action.weapon_name;
  var skill = (msg.action && msg.action.skill) || '';
  var verb = combatVerbForSkill(skill);
  var fpFlag = (msg.actor && msg.actor.is_force_point_active)
    ? '<span class="cri-fp">FP</span>' : '';
  var weaponHtml = w
    ? ' <span class="cri-meta">with ' + _escapeHtml(w) + '</span>' : '';
  var outcomeText = msg.hit ? 'HIT' : 'MISS';
  var outcomeCls  = msg.hit ? 'hit' : 'miss';
  var woundHtml = '';
  var wo = msg.wound_outcome || {};
  if (wo.display_name && msg.hit) {
    var woCls = (wo.outcome_type || 'no-damage').replace(/_/g, '-');
    woundHtml = ' <span class="cri-outcome ' + woCls + '">— ' +
                _escapeHtml(wo.display_name) + '</span>';
  }
  return '<span class="cri-actor">' + _escapeHtml(a) + '</span>' + fpFlag +
         ' <span class="cri-verb">' + _escapeHtml(verb) + '</span> ' +
         '<span class="cri-target">' + _escapeHtml(t) + '</span>' +
         weaponHtml +
         ' <span class="cri-outcome ' + outcomeCls + '">— ' + outcomeText + '</span>' +
         woundHtml;
}

function buildAttackerSection(msg) {
  var sec = document.createElement('div');
  sec.className = 'cri-section';
  var actorName = (msg.actor && msg.actor.name) || '';
  var skill = (msg.action && msg.action.skill) || '';
  var pool = msg.attacker_pool || {};
  sec.innerHTML =
    '<div class="cri-section-head">' +
      'ATTACKER · <span class="cri-actor-tag">' + _escapeHtml(actorName.toUpperCase()) + '</span>' +
      (skill ? ' · ' + _escapeHtml(skill.toUpperCase()) : '') +
      (pool.pool_text ? ' ' + _escapeHtml(pool.pool_text) : '') +
    '</div>';
  appendPoolRow(sec, pool, 'Roll');
  return sec;
}

function buildDefenderSection(msg) {
  var sec = document.createElement('div');
  sec.className = 'cri-section';
  var targetName = (msg.target && msg.target.name) || '';
  var pool = msg.defender_pool || {};
  sec.innerHTML =
    '<div class="cri-section-head">' +
      'DEFENDER · <span class="cri-actor-tag">' + _escapeHtml(targetName.toUpperCase()) + '</span> · OPPOSED' +
      (pool.pool_text ? ' ' + _escapeHtml(pool.pool_text) : '') +
    '</div>';
  appendPoolRow(sec, pool, 'Roll');
  return sec;
}

function buildDifficultySection(msg) {
  var sec = document.createElement('div');
  sec.className = 'cri-section';
  var diff = msg.difficulty || {};
  sec.innerHTML =
    '<div class="cri-section-head">DIFFICULTY</div>' +
    '<div class="cri-diff-block">' +
      '<span class="cri-diff-num">' + (diff.number != null ? diff.number : '—') + '</span>' +
      '<span class="cri-diff-label">' + _escapeHtml(diff.label || '') + '</span>' +
    '</div>';
  if (diff.breakdown && diff.breakdown.length > 1) {
    var bk = document.createElement('div');
    bk.className = 'cri-diff-breakdown';
    bk.textContent = diff.breakdown.map(function(b) {
      var sign = (b.mod != null && b.mod >= 0) ? '+' : '';
      return (b.name || '') + ' ' + sign + (b.mod != null ? b.mod : '');
    }).join(' · ');
    sec.appendChild(bk);
  }
  return sec;
}

function buildDamageSection(msg) {
  var sec = document.createElement('div');
  sec.className = 'cri-section';
  var pool = msg.damage_pool || {};
  sec.innerHTML =
    '<div class="cri-section-head">DAMAGE' +
      (pool.pool_text ? ' · ' + _escapeHtml(pool.pool_text) : '') +
    '</div>';
  appendPoolRow(sec, pool, 'Roll');
  return sec;
}

// Append a complete pool render (row + optional CP/complication notes)
// to the given parent. Mutating the parent rather than returning a
// fragment lets the section builders stay one-line at call sites.
function appendPoolRow(parent, pool, label) {
  var div = document.createElement('div');
  div.className = 'cri-pool-row';

  var labelEl = document.createElement('span');
  labelEl.className = 'cri-pool-label';
  labelEl.textContent = label || '';
  div.appendChild(labelEl);

  (pool.dice || []).forEach(function(d) { div.appendChild(buildDieChip(d)); });

  if (pool.pool_pips) {
    var pip = document.createElement('span');
    pip.className = 'cri-pool-pip';
    pip.textContent = (pool.pool_pips > 0 ? '+' : '') + pool.pool_pips;
    div.appendChild(pip);
  }

  var total = document.createElement('span');
  total.className = 'cri-pool-total';
  total.textContent = pool.total != null ? '= ' + pool.total : '';
  div.appendChild(total);

  parent.appendChild(div);

  if (pool.cp_spent && pool.cp_rolls && pool.cp_rolls.length) {
    var cp = document.createElement('div');
    cp.className = 'cri-cp-line';
    cp.textContent = '+ ' + pool.cp_spent + ' CP: [' +
      pool.cp_rolls.join(', ') + '] = ' + (pool.cp_bonus || 0);
    parent.appendChild(cp);
  }

  if (pool.complication) {
    var comp = document.createElement('div');
    comp.className = 'cri-complication-note';
    comp.textContent = pool.removed_die_value != null
      ? 'Complication! Wild Die rolled 1; dropped highest normal die (' +
        pool.removed_die_value + ').'
      : 'Complication! Wild Die rolled 1.';
    parent.appendChild(comp);
  }
}

// ── UI-3: combat condition chip rail (Lane-A creature conditions) ─────
// Surfaces the poison DoT + restraint that the engine already tracks but the
// HUD never showed. Fields are normalized onto each combatant in the
// combat_state push (engine/combat.py to_hud_dict):
//   poison_stacks: [{source, damage, onset, ticks_left}]   (onset>0 = pre-bite)
//   restraint:     {grappler_id, kind, hold_damage, source} | null
// Returns a .combatant-chips element, or null when the combatant carries no
// condition (so non-creature fights add zero DOM). `isYou` tunes the restraint
// note (the held player needs to know WHY their flee is blocked). NO command
// is staged: ground break-free is automatic at round end (combat.py
// _resolve_flee), so the restraint chip is display-only — there is no ground
// breakfree verb (that exists only for space boarding).
var RESTRAINT_LABELS = { grapple: 'GRAPPLED', constriction: 'CONSTRICTED', choke: 'CHOKED' };

function buildConditionChips(c, isYou) {
  c = c || {};
  var poison = c.poison_stacks || [];
  var restraint = c.restraint || null;
  if (poison.length === 0 && !restraint) return null;

  var rail = document.createElement('div');
  rail.className = 'combatant-chips';

  // Poison — one aggregate chip. Biting (onset 0) pulses and shows the worst
  // active stack; pre-onset shows the soonest onset countdown.
  if (poison.length) {
    var biting = poison.filter(function(s){ return (s.onset | 0) <= 0; });
    var chip = document.createElement('span');
    chip.className = 'cmb-chip poison';
    var detail;
    if (biting.length) {
      chip.classList.add('biting');  // pulses — actively dealing damage
      var worst = biting.reduce(function(a, b){ return (b.ticks_left | 0) > (a.ticks_left | 0) ? b : a; });
      detail = (worst.damage != null ? worst.damage + '\u00B7' : '') + (worst.ticks_left | 0) + 't';
      chip.title = 'Poisoned — taking damage at round end';
    } else {
      var soonest = poison.reduce(function(a, b){ return (b.onset | 0) < (a.onset | 0) ? b : a; });
      detail = 'onset ' + (soonest.onset | 0);
      chip.title = 'Poisoned — damage begins after onset';
    }
    chip.textContent = '\u2623 POISON \u00D7' + poison.length + ' \u00B7 ' + detail;
    rail.appendChild(chip);
  }

  // Restraint — display-only. Shows the hold kind + per-round hold damage; the
  // chip pulses (active threat). The held actor cannot flee and the break-free
  // roll runs automatically at round end, so NO button is staged.
  if (restraint) {
    var kind = String(restraint.kind || 'grapple').toLowerCase();
    var rchip = document.createElement('span');
    rchip.className = 'cmb-chip restraint';  // pulses
    var label = RESTRAINT_LABELS[kind] || 'HELD';
    var hold = restraint.hold_damage ? (' \u00B7 ' + restraint.hold_damage) : '';
    rchip.textContent = '\u26D3 ' + label + hold;
    rchip.title = 'Held — cannot flee; automatic break-free roll at round end (no action required)';
    rail.appendChild(rchip);
    if (isYou) {
      var note = document.createElement('div');
      note.className = 'combatant-restraint-note';
      note.textContent = "\u270B can't flee \u2014 auto break-free at round end";
      rail.appendChild(note);
    }
  }
  return rail;
}

function buildDieChip(d) {
  d = d || {};
  var el = document.createElement('span');
  el.className = 'cri-die';
  el.setAttribute('data-source', d.source || 'skill');
  if (d.is_wild)  el.classList.add('is-wild');
  if (d.exploded) el.classList.add('is-exploded');
  if (d.dropped)  el.classList.add('is-dropped');

  var titleParts = [d.source || 'skill'];
  if (d.is_wild)  titleParts.push('Wild Die');
  if (d.exploded && d.explosion_chain) titleParts.push('Exploded: ' + d.explosion_chain.join('→'));
  if (d.dropped)  titleParts.push('Dropped (complication)');
  el.title = titleParts.join(' · ');

  if (d.is_wild && d.exploded && d.explosion_chain && d.explosion_chain.length) {
    el.classList.add('is-exploded-chain');
    el.textContent = d.explosion_chain.join('→') + '=' + (d.value != null ? d.value : '');
  } else if (d.is_wild && d.value === 0) {
    el.textContent = '1!';  // complication: Wild Die zeroed
  } else {
    el.textContent = (d.value != null ? d.value : '?');
  }
  return el;
}

function buildSoakSection(msg) {
  var sec = document.createElement('div');
  sec.className = 'cri-section';
  var soak = msg.soak || {};
  sec.innerHTML = '<div class="cri-section-head">SOAK</div>';

  (soak.components || []).forEach(function(c) {
    if (!c) return;
    var row = document.createElement('div');
    row.className = 'cri-soak-comp';
    row.setAttribute('data-source', c.source || 'strength');
    var rollsHtml = (c.rolls && c.rolls.length)
      ? '<span class="cri-soak-rolls">[' + c.rolls.join(', ') + ']</span>'
      : '';
    row.innerHTML =
      '<span class="cri-soak-label">' + _escapeHtml(c.label || '') + '</span>' +
      rollsHtml +
      '<span class="cri-soak-value">' + (c.value != null ? c.value : '') + '</span>';
    sec.appendChild(row);
  });

  var total = document.createElement('div');
  total.className = 'cri-soak-total';
  total.innerHTML =
    '<span class="cri-pool-label">Total</span>' +
    '<span class="cri-pool-total">= ' + (soak.total != null ? soak.total : 0) + '</span>';
  sec.appendChild(total);
  return sec;
}

function buildWoundSection(msg) {
  var sec = document.createElement('div');
  sec.className = 'cri-section';
  sec.innerHTML = '<div class="cri-section-head">OUTCOME</div>';

  var wo = msg.wound_outcome || {};
  var ot = wo.outcome_type || 'no_damage';
  var cls = ot.replace(/_/g, '-');

  var row = document.createElement('div');
  row.className = 'cri-wound-row';
  var html = '<span class="cri-wound-display ' + cls + '">' +
             _escapeHtml(wo.display_name || '—') + '</span>';

  if (wo.wound_level_before || wo.wound_level_after) {
    var before = wo.wound_level_before || '—';
    var after  = wo.wound_level_after  || '—';
    var deltaTxt = wo.wound_level_delta
      ? ' <span class="cri-wound-delta">(+' + wo.wound_level_delta + ')</span>'
      : '';
    html += '<span class="cri-wound-track">' +
      _escapeHtml(before) +
      '<span class="cri-wound-arrow">→</span>' +
      '<span class="cri-wound-after">' + _escapeHtml(after) + '</span>' +
      deltaTxt + '</span>';
  }

  if (msg.hit && msg.damage_margin != null) {
    var dm = msg.damage_margin;
    html += '<span class="cri-wound-track">margin ' + (dm >= 0 ? '+' : '') + dm + '</span>';
  } else if (!msg.hit && msg.margin != null) {
    html += '<span class="cri-wound-track">margin ' +
            (msg.margin >= 0 ? '+' : '') + msg.margin + '</span>';
  }

  row.innerHTML = html;
  sec.appendChild(row);

  if (wo.drama_text) {
    var drama = document.createElement('div');
    drama.className = 'cri-wound-drama';
    drama.textContent = wo.drama_text;
    sec.appendChild(drama);
  }

  // Stun-unconscious duration line. v1.1 reserves the schema fields;
  // engine doesn't roll them yet (separate ticket — Drop D Phase 3), so
  // we render a placeholder when the fields are null.
  if (ot === 'stun_unconscious') {
    var sd = document.createElement('div');
    sd.className = 'cri-stun-duration';
    if (wo.stun_duration_dice && wo.stun_duration_unit) {
      sd.textContent = 'Unconscious for ' + wo.stun_duration_dice +
                       ' ' + wo.stun_duration_unit + '.';
    } else {
      sd.textContent = 'Unconscious — duration roll pending.';
    }
    sec.appendChild(sd);
  }

  return sec;
}

function buildSourceLegend() {
  var leg = document.createElement('div');
  leg.className = 'cri-legend';
  leg.innerHTML =
    '<span class="cri-legend-item" style="color:#ffc857">' +
      '<span class="cri-legend-swatch"></span>SKILL</span>' +
    '<span class="cri-legend-item" style="color:#ff8a5a">' +
      '<span class="cri-legend-swatch"></span>WEAPON</span>' +
    '<span class="cri-legend-item" style="color:#b07cff">' +
      '<span class="cri-legend-swatch"></span>MOD</span>' +
    '<span class="cri-legend-item" style="color:#7ce068">' +
      '<span class="cri-legend-swatch"></span>FP DOUBLE</span>' +
    '<span class="cri-legend-item">★ Wild Die · ⊘ dropped</span>';
  return leg;
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3CombatInspector = {
  SCHEMA_VERSION:    1,
  COMBAT_DEDUP_WINDOW_MS: COMBAT_DEDUP_WINDOW_MS,

  // Wiring
  init:                          init,

  // Event-handling surface
  handleCombatResolutionEvent:   handleCombatResolutionEvent,
  isDuplicateOfRecentCombatEvent: isDuplicateOfRecentCombatEvent,
  recordCombatEventFingerprint:  recordCombatEventFingerprint,

  // Pure helpers
  combatVerbForSkill:            combatVerbForSkill,
  composeCombatHeadline:         composeCombatHeadline,
  composeCombatMechline:         composeCombatMechline,

  // DOM renderers
  buildCombatResultRow:          buildCombatResultRow,
  buildConditionChips:           buildConditionChips,
  RESTRAINT_LABELS:              RESTRAINT_LABELS,
  buildCombatHeadlineHtml:       buildCombatHeadlineHtml,
  buildAttackerSection:          buildAttackerSection,
  buildDefenderSection:          buildDefenderSection,
  buildDifficultySection:        buildDifficultySection,
  buildDamageSection:            buildDamageSection,
  buildSoakSection:              buildSoakSection,
  buildWoundSection:             buildWoundSection,
  buildSourceLegend:             buildSourceLegend,
  buildDieChip:                  buildDieChip,
  appendPoolRow:                 appendPoolRow,

  // Test reach (private state for fingerprint-state introspection)
  _internal: {
    _getFingerprints: function() { return combatEventFingerprints.slice(); },
    _clearFingerprints: function() { combatEventFingerprints.length = 0; },
  },
};

})();
