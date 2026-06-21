/* ============================================================================
   m3_onboard.js — Onboarding / training panel (Webify Drop UI-7)

   Renders the `onboarding_state` push produced by
   engine/chain_events.build_onboarding_state and pushed by
   server/session._hud_sidebar_onboarding on every HUD tick while the
   character's tutorial chain is active:

     active    → { active:true, chain_id, chain_name, step, total_steps,
                   completed_steps:[int], title, objective, location,
                   npc, npc_role, npc_intro, teaches:[str], completion_type,
                   next_hint, command_to_type }
     graduated → { active:false, graduated:true, chain_id, chain_name }
                 (pushed once, on the active→graduated transition only)

   NPE-A (2026-06-20): `command_to_type` (optional) is the single
   canonical command for this step; when present it renders as a
   spotlight "TYPE" chip above the teach chips, staging the FULL runnable
   command. Empty/absent → no spotlight (the honest rail holds: the panel
   renders only the corpus-authored literal; it cannot invent a verb).

   Three honest rails:
   • Every staged string is either a corpus-authored `teaches` token
     (staged as `token + ' '`, never auto-sent) or the real
     `chain attempt` (shown only when completion_type ===
     'skill_check_passed' — the one step kind that verb drives).
     The panel CANNOT invent a verb: it renders only what chains.yaml
     teaches.
   • Everything shown is text-reachable (`chain status`, the NPC's
     streamed dialogue) — display-richness, not web-exclusive state.
   • Coach pulses land only on EXISTING quick-action anchors
     (look→LOOK, say/talk→SAY, +bounties→JOBS); unmapped tokens are
     chips only. Pulses are finite CSS animations — no nag, no cleanup.

   Step-advance detection is a module memo (_lastStep per chain): a step
   increase renders a one-beat STEP COMPLETE band and pops the newly
   filled rail dot. Credits rewards already toast via the UI-6
   credit_event riders — no reward plumbing here. The graduated payload
   renders a one-time CHAIN COMPLETE card whose DISMISS invokes the
   onDismiss callback (the client hides the panel).

   Token-only CSS (m3o-* classes styled in client.html). No intervals →
   no stop() needed. resetState() exists for tests/chain switches.
   ============================================================================ */
(function(){
'use strict';

var _lastChain = null;   // chain_id of the last render
var _lastStep = null;    // step number of the last render (per chain)

// Teach token → existing quick-action anchor (data-qa). Mapping covers
// what EXISTS; everything else stays chip-only by design.
var TEACH_QA = {
  'look': 'LOOK',
  'say': 'SAY',
  'talk': 'SAY',
  '+bounties': 'JOBS'
};

var PULSE_CLASS = 'm3o-pulse';

function el(tag, attrs, children){
  var n = document.createElement(tag);
  if (attrs){
    Object.keys(attrs).forEach(function(k){
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else if (k.slice(0,5) === 'data-') n.setAttribute(k, attrs[k]);
      else n[k] = attrs[k];
    });
  }
  (children || []).forEach(function(c){
    if (c == null) return;
    n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  });
  return n;
}

function stepRail(total, current, completed){
  var done = {};
  (completed || []).forEach(function(s){ done[s] = true; });
  var rail = el('div', {class: 'm3o-rail'});
  for (var i = 1; i <= total; i++){
    var cls = 'm3o-dot';
    if (done[i]) cls += ' done';
    else if (i === current) cls += ' current';
    if (i === current && _lastStep !== null && current > _lastStep){
      // freshly reached → pop the dot
      cls += ' pop';
    }
    rail.appendChild(el('span', {class: cls, 'data-step': String(i)}));
  }
  return rail;
}

function teachChips(data, stage){
  var row = el('div', {class: 'm3o-chips'});
  // drop 26 (2026-06-13): on a skill_check_passed step the ONLY action
  // that advances the chain is `chain attempt` \u2014 the authored `teaches`
  // tokens on those steps (historically scan/search/sneak/etc.) are
  // descriptive, not actionable, and rendering them as clickable chips
  // misleads a new player into typing a command that does nothing. So
  // for skill_check_passed steps we render ONLY the ATTEMPT chip and
  // suppress the teach chips. For every other completion type the
  // teach tokens ARE the actionable commands, so they render as before.
  var skillStep = (data.completion_type === 'skill_check_passed');
  if (!skillStep){
    (data.teaches || []).forEach(function(tok){
      if (!tok) return;
      row.appendChild(el('button', {
        class: 'm3o-chip', type: 'button',
        'data-teach': tok,
        text: tok
      }));
    });
  }
  if (skillStep){
    row.appendChild(el('button', {
      class: 'm3o-chip attempt', type: 'button',
      'data-teach-cmd': 'chain attempt',
      text: 'ATTEMPT \u00B7 chain attempt'
    }));
  }
  row.onclick = function(ev){
    var t = ev.target;
    while (t && t !== row && !t.getAttribute) t = t.parentNode;
    while (t && t !== row &&
           !(t.getAttribute('data-teach') || t.getAttribute('data-teach-cmd'))){
      t = t.parentNode;
    }
    if (!t || t === row || !stage) return;
    var full = t.getAttribute('data-teach-cmd');
    if (full){ stage(full); return; }
    stage(t.getAttribute('data-teach') + ' ');
  };
  return row;
}

function pulseQuickActions(teaches){
  if (typeof document.querySelector !== 'function') return;
  (teaches || []).forEach(function(tok){
    var qa = TEACH_QA[tok];
    if (!qa) return;
    var btn = document.querySelector('[data-qa="' + qa + '"]');
    if (!btn) return;
    btn.classList.remove(PULSE_CLASS);
    void btn.offsetWidth;            // restart the finite animation
    btn.classList.add(PULSE_CLASS);
  });
}

function renderGraduated(bodyEl, data, onDismiss){
  bodyEl.textContent = '';
  var card = el('div', {class: 'm3o-grad'}, [
    el('div', {class: 'm3o-grad-glyph', text: '\u2726'}),
    el('div', {class: 'm3o-grad-title', text: 'CHAIN COMPLETE'}),
    el('div', {class: 'm3o-grad-name', text: data.chain_name || ''}),
    el('div', {class: 'm3o-grad-sub',
        text: 'Your training is done. The galaxy is open.'}),
    el('button', {class: 'm3o-grad-dismiss', type: 'button',
        text: 'DISMISS'})
  ]);
  card.querySelector('.m3o-grad-dismiss').onclick = function(){
    if (onDismiss) onDismiss();
  };
  bodyEl.appendChild(card);
}

function render(bodyEl, data, stage, onDismiss){
  if (!bodyEl || !data) return;

  if (!data.active){
    if (data.graduated) renderGraduated(bodyEl, data, onDismiss);
    _lastChain = null;
    _lastStep = null;
    return;
  }

  if (data.chain_id !== _lastChain){
    _lastChain = data.chain_id;
    _lastStep = null;          // new chain → no flash on first render
  }
  var advanced = (_lastStep !== null && data.step > _lastStep);

  bodyEl.textContent = '';

  bodyEl.appendChild(el('div', {class: 'm3o-meta'}, [
    el('span', {class: 'm3o-chain-name', text: data.chain_name || ''}),
    el('span', {class: 'm3o-step-count',
        text: 'STEP ' + data.step + '/' + data.total_steps})
  ]));

  if (advanced){
    bodyEl.appendChild(el('div', {class: 'm3o-flash', text: 'STEP COMPLETE'}));
  }

  bodyEl.appendChild(stepRail(data.total_steps, data.step,
                              data.completed_steps));

  bodyEl.appendChild(el('div', {class: 'm3o-title', text: data.title || ''}));
  if (data.npc){
    bodyEl.appendChild(el('div', {class: 'm3o-npc'}, [
      el('span', {class: 'm3o-npc-name', text: data.npc}),
      data.npc_role
        ? el('span', {class: 'm3o-npc-role', text: ' \u00B7 ' + data.npc_role})
        : null
    ]));
  }
  if (data.npc_intro){
    bodyEl.appendChild(el('div', {class: 'm3o-brief', text: data.npc_intro}));
  }
  if (data.objective){
    bodyEl.appendChild(el('div', {class: 'm3o-objective'}, [
      el('span', {class: 'm3o-obj-label', text: 'OBJECTIVE'}),
      el('span', {class: 'm3o-obj-text', text: data.objective})
    ]));
  }
  // drop 26 (2026-06-13): render the authored NEXT pointer (next_hint)
  // below the objective so a player who finishes the step knows where
  // the chain takes them. Authored in the corpus; now threaded through
  // build_onboarding_state. Suppressed when empty.
  if (data.next_hint){
    bodyEl.appendChild(el('div', {class: 'm3o-next'}, [
      el('span', {class: 'm3o-next-label', text: 'NEXT'}),
      el('span', {class: 'm3o-next-text', text: data.next_hint})
    ]));
  }
  // NPE-A (2026-06-20): spotlight the single "type this next" command
  // above the teach chips when the corpus authored one. Reuses the
  // .m3o-chips row + .m3o-chip.attempt prominent style (no new CSS) and
  // stages the FULL runnable command via the data-teach-cmd path.
  // skill_check_passed steps carry no command_to_type — teachChips
  // already renders their dedicated ATTEMPT chip, so there is no overlap.
  if (data.command_to_type){
    var spotRow = el('div', {class: 'm3o-chips'});
    spotRow.appendChild(el('button', {
      class: 'm3o-chip attempt', type: 'button',
      'data-teach-cmd': data.command_to_type,
      text: 'TYPE · ' + data.command_to_type
    }));
    spotRow.onclick = function(ev){
      var t = ev.target;
      while (t && t !== spotRow &&
             !(t.getAttribute && t.getAttribute('data-teach-cmd'))){
        t = t.parentNode;
      }
      if (t && t !== spotRow && stage){
        stage(t.getAttribute('data-teach-cmd'));
      }
    };
    bodyEl.appendChild(spotRow);
  }

  bodyEl.appendChild(teachChips(data, stage));

  pulseQuickActions(data.teaches);

  _lastStep = data.step;
}

function resetState(){
  _lastChain = null;
  _lastStep = null;
}

window.M3Onboard = {
  render: render,
  resetState: resetState
};

})();
