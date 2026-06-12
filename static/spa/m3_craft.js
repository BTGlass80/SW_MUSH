/* ============================================================================
   m3_craft.js — Crafting panel modal (Webify Drop UI-8)

   Renders the `crafting_state` push produced by the schematics /
   resources / craft verbs via engine/crafting.build_crafting_state
   (ABI: protocol ledger v1_4 §1.9, accepted 2026-06-10):

     { schematics: [ {key, name, skill, difficulty, craftable,
                      components:[{type, quantity, min_quality,
                                   have, have_at_quality}],
                      output_type, t5} ],
       resources:  [ {type, quantity, quality} ],
       last_result: {success, partial, fumble, quality, name} | null }

   The panel renders ONLY what the engine computes — `craftable` and the
   per-component have/have_at_quality numbers are the CRAFT.P0.1
   check_resources diagnostics exposed structurally. It cannot invent a
   recipe: known schematics only (discovery stays with trainers).

   Real verbs only — staged via the callback, never auto-sent:
     • CRAFT      → `craft <name>`            (craftable rows)
     • SURVEY     → `survey`                  (footer)
     • BUY <type> → `buyresources <type> `    (quantity left to the player)
   There is no web-exclusive verb; Telnet parity is the text listings the
   same commands just printed.

   Component readiness is TOKEN-ONLY: met → --self, quality-blocked →
   --warn (you HAVE the material, it's too low-grade — the actionable
   distinction P0.1 introduced), quantity-blocked → --text-dim. T5 rows
   get an --accent-bright stud (mirrors the Telnet T5 emphasis).

   No timers — M3Craft.stop() exists for symmetry with the M3Region/
   M3Board close convention but is a no-op.
   ============================================================================ */
(function(){
'use strict';

var _expanded = {};   // schematic key → components open

function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}

function resetState(){ _expanded = {}; }
function stop(){ /* no timers — convention symmetry only */ }

function titleFor(data){
  var n = (data && data.schematics) ? data.schematics.length : 0;
  return 'Crafting — ' + n + ' schematic' + (n === 1 ? '' : 's');
}

// ── component line ──
// met:               have_at_quality >= quantity          → --self
// quality-blocked:   have >= quantity, qualified short    → --warn
// quantity-blocked:  have < quantity                      → --text-dim
function compState(c){
  if (c.have_at_quality >= c.quantity) return 'met';
  if (c.have >= c.quantity) return 'quality';
  return 'quantity';
}
var COMP_TOKEN = {
  met:      'var(--self)',
  quality:  'var(--warn)',
  quantity: 'var(--text-dim)'
};

function compLine(c){
  var st = compState(c);
  var detail;
  if (st === 'met'){
    detail = c.have_at_quality + '/' + c.quantity + ' ready';
  } else if (st === 'quality'){
    detail = 'have ' + c.have + 'x — only ' + c.have_at_quality +
             'x at q' + c.min_quality + '+';
  } else {
    detail = c.have + '/' + c.quantity;
  }
  var q = c.min_quality > 1 ? ' (q' + c.min_quality + '+)' : '';
  return '<div class="m3c-comp" style="color:' + COMP_TOKEN[st] + '">' +
    '<span class="m3c-comp-name">' + esc(c.quantity) + 'x ' +
    esc(c.type) + esc(q) + '</span>' +
    '<span class="m3c-comp-have">' + esc(detail) + '</span></div>';
}

// ── schematic card ──
function schemCard(s, stage){
  var open = !!_expanded[s.key];
  var stud = s.t5 ? 'var(--accent-bright)' : 'var(--accent-dim)';
  var h = '<div class="m3c-card' + (s.craftable ? ' craftable' : '') + '">';
  h += '<div class="m3c-head" data-m3c-toggle="' + esc(s.key) + '">';
  h += '<span class="m3c-stud" style="background:' + stud + '"></span>';
  h += '<span class="m3c-name">' + esc(s.name) + '</span>';
  if (s.t5) h += '<span class="m3c-t5">T5</span>';
  h += '<span class="m3c-skill">' + esc(s.skill) +
       ' vs ' + esc(s.difficulty) + '</span>';
  if (s.craftable){
    h += '<button class="m3c-btn" type="button" data-m3c-craft="' +
         esc(s.name) + '">CRAFT</button>';
  } else {
    h += '<span class="m3c-blocked">missing materials</span>';
  }
  h += '</div>';
  if (open){
    h += '<div class="m3c-comps">';
    for (var i = 0; i < (s.components || []).length; i++){
      h += compLine(s.components[i]);
    }
    h += '</div>';
  }
  h += '</div>';
  return h;
}

// ── result banner ──
function resultBanner(r){
  if (!r || !r.name) return '';
  var cls, txt;
  if (r.fumble){
    cls = 'fumble'; txt = '✗ ' + r.name + ' — components ruined';
  } else if (r.success && r.partial){
    cls = 'partial';
    txt = '~ ' + r.name + ' — passable work (q' + Math.round(r.quality) + ')';
  } else if (r.success){
    cls = 'success';
    txt = '✓ ' + r.name + ' crafted (q' + Math.round(r.quality) + ')';
  } else {
    cls = 'fail'; txt = '— ' + r.name + ' — no luck; components undamaged';
  }
  return '<div class="m3c-result ' + cls + '">' + esc(txt) + '</div>';
}

// ── render ──
function render(bodyEl, data, stage){
  if (!bodyEl) return;
  data = data || {};
  var schems = data.schematics || [];
  var res = data.resources || [];

  var h = resultBanner(data.last_result);

  // craftable first, then name
  schems = schems.slice().sort(function(a, b){
    if (a.craftable !== b.craftable) return a.craftable ? -1 : 1;
    return String(a.name).localeCompare(String(b.name));
  });
  if (!schems.length){
    h += '<div class="m3c-empty">No known schematics — find a trainer ' +
         'and use <code>talk</code> to learn some.</div>';
  } else {
    for (var i = 0; i < schems.length; i++) h += schemCard(schems[i], stage);
  }

  h += '<div class="m3c-res-head">MATERIALS</div>';
  if (!res.length){
    h += '<div class="m3c-empty">No materials. SURVEY finds free ' +
         'stock; vendors sell at q50.</div>';
  } else {
    h += '<div class="m3c-res">';
    for (var j = 0; j < res.length; j++){
      var r = res[j];
      h += '<div class="m3c-res-row"><span>' + esc(r.type) + '</span>' +
           '<span>x' + esc(r.quantity) + '</span>' +
           '<span class="m3c-res-q">q' + esc(Math.round(r.quality)) +
           '</span>' +
           '<button class="m3c-buy" type="button" data-m3c-buy="' +
           esc(r.type) + '">BUY</button></div>';
    }
    h += '</div>';
  }
  h += '<div class="m3c-foot">' +
       '<button class="m3c-btn" type="button" data-m3c-survey="1">SURVEY' +
       '</button><span class="m3c-foot-note">survey is free; ' +
       'cooldown applies</span></div>';

  bodyEl.innerHTML = h;

  // Wire interactions (delegation-free: small list sizes).
  var toggles = bodyEl.querySelectorAll('[data-m3c-toggle]');
  for (var t = 0; t < toggles.length; t++){
    toggles[t].addEventListener('click', function(ev){
      // CRAFT button inside the head must not also toggle.
      if (ev.target && ev.target.hasAttribute('data-m3c-craft')) return;
      var k = this.getAttribute('data-m3c-toggle');
      _expanded[k] = !_expanded[k];
      render(bodyEl, data, stage);
    });
  }
  var crafts = bodyEl.querySelectorAll('[data-m3c-craft]');
  for (var c = 0; c < crafts.length; c++){
    crafts[c].addEventListener('click', function(ev){
      ev.stopPropagation();
      if (stage) stage('craft ' + this.getAttribute('data-m3c-craft'));
    });
  }
  var buys = bodyEl.querySelectorAll('[data-m3c-buy]');
  for (var b = 0; b < buys.length; b++){
    buys[b].addEventListener('click', function(){
      if (stage) stage('buyresources ' +
                       this.getAttribute('data-m3c-buy') + ' ');
    });
  }
  var sv = bodyEl.querySelector('[data-m3c-survey]');
  if (sv) sv.addEventListener('click', function(){
    if (stage) stage('survey');
  });
}

window.M3Craft = {
  render: render,
  stop: stop,
  resetState: resetState,
  titleFor: titleFor,
  // exposed for jsdom tests
  _compState: compState
};

})();
