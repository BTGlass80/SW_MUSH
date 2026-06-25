/* ============================================================================
   m3_goals.js — Consolidated GOALS / objectives tracker (UX Drop 6).

   The right-rail GOALS card. A lean, read-only MIRROR of the graduated
   player's three persistent open loops, consolidated from producers that
   already run server-side:

     · QUESTLINE  — the active mid-game questline step (step rail + NEXT line),
                    reusing the m3_onboard.js step-dot idiom.
     · MISSION    — the one accepted board mission (title + objective + reward).
     · BOUNTY     — the player's claimed/active contract (tier color + a live
                    countdown), reusing the m3_board.js TIER_TOKEN / countdown
                    idiom (self-contained here so the module is testable alone).

   It never GATES pace or information — every goal is already reachable by
   typing (quests / chain status, +missions, bounties). Pure render
   over the `goals_status` push (server/session.py _hud_sidebar_goals). Zero
   new socket cadence: rides the existing HUD tick. The only client interval is
   the bounty countdown (1 s), armed by start() and cleared by stop() — so a
   collapsed/absent panel costs nothing.

   Each action chip STAGES its authored command via the injected stage()
   callback (mirrors m3_onboard's stage chips) — the player still presses Enter.
   The panel cannot invent a verb: it stages only the literal the producer
   authored (questline `command_to_type`, the mission's `+missions`, the
   bounty's `bounties`).

   Payload (goals_status):
     { questline: { chain_id, title, objective, step, total_steps,
                    next_hint, command_to_type } | null,
       mission:   { id, title, objective, reward, stage_cmd } | null,
       bounty:    { id, target_name, tier, reward, expires_in_secs,
                    stage_cmd } | null }

   XSS contract: titles, objectives, target names and hints are server-authored
   free text — every one is written via textContent (the `el` 'text' path) or
   routed through the injected escapeHtml, never raw innerHTML.

   Dependency injection (mirrors m3_situation_board / m3_scene_panel):
     · init({ escapeHtml }) — injects the shared client escape; falls back to a
       built-in so the module is unit-testable standalone under jsdom.
   ============================================================================ */
(function(){
'use strict';

// ── Tier → accent color. Self-contained (mirrors m3_board.js TIER_TOKEN, but
//    the module owns its own copy so it has no cross-module dependency and is
//    unit-testable standalone — same pattern as m3_situation_board's
//    _FACTION_COLOR). Bounty tier values are the engine BountyTier enum. ──
var TIER_COLOR = {
  extra:    'var(--text-dim)',
  average:  'var(--text)',
  novice:   'var(--accent)',
  veteran:  'var(--accent-bright)',
  superior: 'var(--warn)',
};

// ── Module-private escape hook (DI, mirrors m3_scene_panel.init). ──
var _escapeHtml = _defaultEscapeHtml;

function init(deps) {
  deps = deps || {};
  if (typeof deps.escapeHtml === 'function') _escapeHtml = deps.escapeHtml;
}

function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── tiny element helper (mirror m3_scene_panel.el(); textContent is the safe
//    path — server text never reaches innerHTML here). ──
function el(tag, attrs, children){
  var n = document.createElement(tag);
  if (attrs){
    Object.keys(attrs).forEach(function(k){
      if (k === 'text') { n.textContent = attrs[k]; }
      else if (k === 'class') { n.className = attrs[k]; }
      else if (k === 'title') { n.setAttribute('title', attrs[k]); }
      else if (k.slice(0, 5) === 'data-') { n.setAttribute(k, attrs[k]); }
      else { n.setAttribute(k, attrs[k]); }
    });
  }
  (children || []).forEach(function(c){
    if (c == null) return;
    n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  });
  return n;
}

function humanize(code){
  if (!code) return '';
  return String(code).replace(/_/g, ' ').replace(/\b\w/g, function(m){
    return m.toUpperCase();
  });
}

function tierColor(tier){ return TIER_COLOR[tier] || 'var(--accent)'; }

// ── countdown formatter (mirror m3_board.js fmtCountdown; self-contained). ──
function fmtCountdown(secs){
  if (secs == null) return '';
  secs = Math.max(0, Math.floor(secs));
  if (secs <= 0) return 'EXPIRED';
  var h = Math.floor(secs / 3600);
  var m = Math.floor((secs % 3600) / 60);
  var s = secs % 60;
  if (h > 0) return h + 'h ' + (m < 10 ? '0' : '') + m + 'm';
  return m + 'm ' + (s < 10 ? '0' : '') + s + 's';
}

function fmtReward(n){
  n = Number(n || 0);
  return n > 0 ? (n.toLocaleString() + ' cr') : '';
}

// ── one action chip that STAGES (never sends) an authored command. ──
function stageChip(label, cmd, stage){
  var btn = el('button', {
    class: 'm3g-chip', type: 'button', 'data-stage-cmd': cmd,
    text: label,
  });
  btn.onclick = function(){
    if (typeof stage === 'function' && cmd) stage(cmd);
  };
  return btn;
}

// ── questline row (reuses the onboard step-rail dot idiom) ─────────────────
function stepRail(total, current){
  total = Number(total || 0);
  current = Number(current || 0);
  var rail = el('div', { class: 'm3g-rail' });
  for (var i = 1; i <= total; i++){
    var cls = 'm3g-dot';
    if (i < current) cls += ' done';
    else if (i === current) cls += ' current';
    rail.appendChild(el('span', { class: cls, 'data-step': String(i) }));
  }
  return rail;
}

function buildQuestline(q, stage){
  if (!q) return null;
  var row = el('div', { class: 'm3g-row m3g-quest', 'data-goal': 'questline' });
  row.appendChild(el('div', { class: 'm3g-head' }, [
    el('span', { class: 'm3g-kind', text: 'QUESTLINE' }),
    (q.step != null && q.total_steps != null)
      ? el('span', { class: 'm3g-step', text: 'STEP ' + q.step + '/' + q.total_steps })
      : null,
  ]));
  if (q.title){
    row.appendChild(el('div', { class: 'm3g-title', text: q.title, title: q.title }));
  }
  if (q.total_steps){
    row.appendChild(stepRail(q.total_steps, q.step));
  }
  if (q.objective){
    row.appendChild(el('div', { class: 'm3g-obj', text: q.objective }));
  }
  if (q.next_hint){
    row.appendChild(el('div', { class: 'm3g-next' }, [
      el('span', { class: 'm3g-next-label', text: 'NEXT' }),
      el('span', { class: 'm3g-next-text', text: q.next_hint }),
    ]));
  }
  // Authored literal only — "" suppresses the chip (no invented verb).
  if (q.command_to_type){
    row.appendChild(el('div', { class: 'm3g-chips' }, [
      stageChip('TYPE · ' + q.command_to_type, q.command_to_type, stage),
    ]));
  }
  return row;
}

// ── mission row ────────────────────────────────────────────────────────────
function buildMission(m, stage){
  if (!m) return null;
  var row = el('div', { class: 'm3g-row m3g-mission', 'data-goal': 'mission' });
  var head = el('div', { class: 'm3g-head' }, [
    el('span', { class: 'm3g-kind', text: 'MISSION' }),
  ]);
  var reward = fmtReward(m.reward);
  if (reward){
    head.appendChild(el('span', { class: 'm3g-reward', text: reward }));
  }
  row.appendChild(head);
  if (m.title){
    row.appendChild(el('div', { class: 'm3g-title', text: m.title, title: m.title }));
  }
  if (m.objective){
    row.appendChild(el('div', { class: 'm3g-obj', text: m.objective }));
  }
  var cmd = m.stage_cmd || '+missions';
  row.appendChild(el('div', { class: 'm3g-chips' }, [
    stageChip('OPEN · ' + cmd, cmd, stage),
  ]));
  return row;
}

// ── bounty row (tier color + live countdown) ───────────────────────────────
function buildBounty(b, stage){
  if (!b) return null;
  var color = tierColor(b.tier);
  var row = el('div', { class: 'm3g-row m3g-bounty', 'data-goal': 'bounty' });
  var head = el('div', { class: 'm3g-head' }, [
    el('span', { class: 'm3g-kind', text: 'BOUNTY', style: 'color:' + color + ';' }),
  ]);
  var reward = fmtReward(b.reward);
  if (reward){
    head.appendChild(el('span', { class: 'm3g-reward', text: reward }));
  }
  row.appendChild(head);
  row.appendChild(el('div', { class: 'm3g-title',
    text: b.target_name || 'Unknown target',
    title: b.target_name || 'Unknown target' }));
  if (b.tier){
    row.appendChild(el('span', { class: 'm3g-tier',
      text: humanize(b.tier), style: 'color:' + color + ';' }));
  }
  // Live countdown span (the only client interval; updated by tick()).
  if (b.expires_in_secs != null){
    row.appendChild(el('div', { class: 'm3g-count', 'data-expires-at':
      String(Date.now() + Number(b.expires_in_secs) * 1000),
      text: fmtCountdown(b.expires_in_secs) }));
  }
  var cmd = b.stage_cmd || 'JOBS';
  row.appendChild(el('div', { class: 'm3g-chips' }, [
    stageChip('OPEN · ' + cmd, cmd, stage),
  ]));
  return row;
}

/* render(state, stage) → DOM node, or null when there are no goals at all.

   `state` is the goals_status payload. A falsy value, or one whose three
   slots are all null/absent, returns null so the consumer hides the card. */
function render(state, stage){
  if (!state || typeof state !== 'object') return null;
  var q = state.questline, m = state.mission, b = state.bounty;
  if (!q && !m && !b) return null;

  var root = el('div', { class: 'm3g-root', 'data-goals-board': '1' });
  var qNode = buildQuestline(q, stage);
  var mNode = buildMission(m, stage);
  var bNode = buildBounty(b, stage);
  if (qNode) root.appendChild(qNode);
  if (mNode) root.appendChild(mNode);
  if (bNode) root.appendChild(bNode);
  // Nothing rendered (all slots malformed) → hide.
  if (!root.firstChild) return null;
  return root;
}

// ── live bounty countdown (1 s) — armed only while the panel is visible. ──
var _interval = null;
var _bodyEl = null;

function tick(){
  if (!_bodyEl) return;
  var spans = _bodyEl.querySelectorAll('.m3g-count[data-expires-at]');
  var now = Date.now();
  for (var i = 0; i < spans.length; i++){
    var at = Number(spans[i].getAttribute('data-expires-at'));
    spans[i].textContent = fmtCountdown(Math.max(0, Math.round((at - now) / 1000)));
  }
}

function start(bodyEl){
  _bodyEl = bodyEl || null;
  stop();
  if (!_bodyEl) return;
  // Only arm the interval when there is at least one live countdown.
  if (_bodyEl.querySelector('.m3g-count[data-expires-at]')){
    tick();
    if (typeof setInterval === 'function'){
      _interval = setInterval(tick, 1000);
    }
  }
}

function stop(){
  if (_interval != null && typeof clearInterval === 'function'){
    clearInterval(_interval);
  }
  _interval = null;
}

function isTicking(){ return _interval != null; }

window.M3Goals = {
  render: render,
  init: init,
  start: start,
  stop: stop,
  // exposed for tests / reuse
  isTicking: isTicking,
  fmtCountdown: fmtCountdown,
  TIER_COLOR: TIER_COLOR,
};

})();
