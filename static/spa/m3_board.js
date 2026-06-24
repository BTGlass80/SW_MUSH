/* ============================================================================
   m3_board.js — Bounty board modal (Webify Drop UI-5)

   Renders the `board_state` push produced by BountiesCommand (the
   `bounties` verb) via engine/bounty_board.build_board_state:

     { contracts: [ BountyContract.to_dict()
                    + {expires_in_secs:int|null} ],
       claimed_id: str|null }

   Contract fields used: id, tier, target_name, target_species,
   target_archetype, crime_description, posting_org, tip, reward,
   reward_alive_bonus, status, chain_bounty_id, expires_in_secs,
   track_difficulty.

   Real verbs only — the two staged actions are:
     • ACCEPT       → `+bounty/claim <id>` (posted card, viewer unclaimed)
     • TRACK TARGET → `+bounty/track`      (the viewer's claimed card)
   Both are STAGED into the input via the callback, never auto-sent.
   There is no abandon verb at HEAD, so none is offered. One claim at a
   time (enforced server-side; the UI hides ACCEPT while claimed).

   The viewer's claimed contract is pinned to the top; the rest sort by
   reward descending. A live 1-second countdown ticks off a deadline
   snapshot taken from the SERVER-derived expires_in_secs (never the
   raw expires_at epoch — no client-clock trust). Countdowns under 30
   minutes go urgent (--warn). Callers MUST invoke M3Board.stop() when
   the modal closes so the interval drains (jsdom tests rely on this —
   same convention as M3Region).

   Tier ramp is TOKEN-ONLY (no new colours): extra --text-dim →
   average --text → novice --accent → veteran --accent-bright →
   superior --warn. Mirrors the escalation of the Telnet board's ANSI
   _TIER_COLORS within the pad palette. Chain-tagged tutorial contracts
   (chain_bounty_id) get a small CHAIN tag; the chain dispatcher
   advances the bounty-hunter tutorial on claim server-side.
   ============================================================================ */
(function(){
'use strict';

var _data = null;          // last board_state
var _filter = 'all';       // active tier filter
var _expanded = {};        // contract id → details open
var _deadlines = {};       // contract id → epoch-ms deadline (from expires_in_secs)
var _timer = null;
var _bodyEl = null;
var _stage = null;

var TIERS = ['extra', 'average', 'novice', 'veteran', 'superior'];

// Token-only tier ramp (resolved from client.html :root).
var TIER_TOKEN = {
  extra:    'var(--text-dim)',
  average:  'var(--text)',
  novice:   'var(--accent)',
  veteran:  'var(--accent-bright)',
  superior: 'var(--warn)'
};

// Display legend mirroring engine/bounty_board.PAY_RANGES (static engine
// constants; labels only — never used for any computation).
var PAY_LABEL = {
  extra:    '100–300',
  average:  '300–800',
  novice:   '800–1.5k',
  veteran:  '1.5–3k',
  superior: '3–10k'
};

var URGENT_SECS = 1800;    // countdown turns --warn under 30 minutes

function el(tag, attrs, children){
  var n = document.createElement(tag);
  if (attrs){
    Object.keys(attrs).forEach(function(k){
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else if (k === 'style') n.setAttribute('style', attrs[k]);
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

function fmtCr(n){
  n = Number(n) || 0;
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

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

function tierHue(tier){ return TIER_TOKEN[tier] || 'var(--accent)'; }

function remainingSecs(id){
  var dl = _deadlines[id];
  if (dl == null) return null;
  return Math.max(0, Math.round((dl - Date.now()) / 1000));
}

// ── tick: update every live countdown span in place ──
function tick(){
  if (!_bodyEl) return;
  var spans = _bodyEl.querySelectorAll('.m3b-count[data-cid]');
  for (var i = 0; i < spans.length; i++){
    var sp = spans[i];
    var secs = remainingSecs(sp.getAttribute('data-cid'));
    if (secs == null) continue;
    sp.textContent = '\u29D7 ' + fmtCountdown(secs);
    if (secs < URGENT_SECS) sp.classList.add('urgent');
    else sp.classList.remove('urgent');
  }
}

function ensureTimer(){
  if (_timer == null) _timer = setInterval(tick, 1000);
}

function stop(){
  if (_timer != null){ clearInterval(_timer); _timer = null; }
}

// ── card builders ──

function tierStud(tier){
  var hue = tierHue(tier);
  return el('div', {class: 'm3b-stud'}, [
    el('div', {class: 'm3b-stud-ring', style: 'border-color:' + hue +
        ';color:' + hue, text: (tier || '?').charAt(0).toUpperCase()}),
    el('span', {class: 'm3b-stud-label', style: 'color:' + hue,
        text: tier || ''})
  ]);
}

function contractCard(c, claimedId){
  var isClaimed = (claimedId != null && c.id === claimedId);
  var hue = tierHue(c.tier);
  var secs = remainingSecs(c.id);

  var headBits = [
    el('span', {class: 'm3b-name', text: c.target_name || '?'}),
    el('span', {class: 'm3b-sub',
        text: (c.target_species || '?') + ' \u00B7 ' + (c.target_archetype || '?')})
  ];
  if (isClaimed) headBits.push(el('span', {class: 'm3b-badge claimed', text: 'CLAIMED'}));
  if (c.chain_bounty_id) headBits.push(el('span', {class: 'm3b-badge chain', text: 'CHAIN'}));

  var payBits = [
    el('span', {class: 'm3b-reward'}, [
      fmtCr(c.reward), el('span', {class: 'm3b-cr', text: ' cr'})
    ])
  ];
  if (c.reward_alive_bonus > 0){
    payBits.push(el('span', {class: 'm3b-alive',
        text: '+' + fmtCr(c.reward_alive_bonus) + ' alive'}));
  }
  payBits.push(el('span', {class: 'm3b-spacer'}));
  if (secs != null){
    payBits.push(el('span', {
      class: 'm3b-count' + (secs < URGENT_SECS ? ' urgent' : ''),
      'data-cid': c.id,
      text: '\u29D7 ' + fmtCountdown(secs)
    }));
  }

  var body = [
    el('div', {class: 'm3b-head'}, headBits),
    el('div', {class: 'm3b-crime', text: c.crime_description || ''}),
    el('div', {class: 'm3b-pay'}, payBits)
  ];

  if (_expanded[c.id]){
    var diffVal = (c.track_difficulty != null) ? String(c.track_difficulty) : null;
    var diffHint = diffVal
      ? 'Track: Difficulty ' + diffVal + ' (Search/Streetwise/Tracking)'
      : null;
    body.push(el('div', {class: 'm3b-details'}, [
      el('div', {class: 'm3b-kv'}, [
        el('span', {class: 'm3b-k', text: 'Posted by'}),
        el('span', {class: 'm3b-v', text: c.posting_org || '?'})
      ]),
      el('div', {class: 'm3b-kv'}, [
        el('span', {class: 'm3b-k', text: 'Contract'}),
        el('span', {class: 'm3b-v mono', text: c.id || '?'})
      ]),
      diffHint ? el('div', {class: 'm3b-kv'}, [
        el('span', {class: 'm3b-k', text: 'Hunt'}),
        el('span', {class: 'm3b-v m3b-track-diff', text: diffHint})
      ]) : null,
      c.tip ? el('div', {class: 'm3b-tip', text: '\u275D ' + c.tip + ' \u275E'}) : null
    ]));
  }

  var actions = [];
  if (isClaimed){
    actions.push(el('button', {
      class: 'm3b-act primary', type: 'button',
      'data-act': 'track', 'data-cid': c.id,
      text: 'TRACK TARGET \u00B7 +bounty/track'
    }));
  } else if (claimedId == null && c.status === 'posted'){
    actions.push(el('button', {
      class: 'm3b-act accept', type: 'button',
      'data-act': 'claim', 'data-cid': c.id,
      text: 'ACCEPT \u00B7 +bounty/claim ' + c.id
    }));
  }
  actions.push(el('button', {
    class: 'm3b-act', type: 'button',
    'data-act': 'details', 'data-cid': c.id,
    text: _expanded[c.id] ? 'LESS' : 'DETAILS'
  }));
  body.push(el('div', {class: 'm3b-actions'}, actions));

  return el('div', {
    class: 'm3b-card' + (isClaimed ? ' claimed' : ''),
    style: 'border-left-color:' + hue
  }, [tierStud(c.tier), el('div', {class: 'm3b-body'}, body)]);
}

function filterRow(counts){
  var chips = [el('button', {
    class: 'm3b-chip' + (_filter === 'all' ? ' active' : ''),
    type: 'button', 'data-filter': 'all', text: 'ALL'
  })];
  TIERS.forEach(function(t){
    var hue = tierHue(t);
    var active = (_filter === t);
    chips.push(el('button', {
      class: 'm3b-chip tier' + (active ? ' active' : ''),
      type: 'button', 'data-filter': t,
      style: active
        ? ('background:' + hue + ';border-color:' + hue + ';color:var(--screen)')
        : ('border-color:' + hue + ';color:' + hue),
      text: t + ' \u00B7 ' + PAY_LABEL[t]
    }));
  });
  return el('div', {class: 'm3b-filter'}, chips);
}

// ── render ──

function render(bodyEl, data, stage){
  _bodyEl = bodyEl;
  _data = data || {contracts: [], claimed_id: null};
  _stage = stage;

  // Deadline snapshots from the server-derived remaining seconds.
  _deadlines = {};
  (_data.contracts || []).forEach(function(c){
    if (c && c.expires_in_secs != null){
      _deadlines[c.id] = Date.now() + (c.expires_in_secs * 1000);
    }
  });

  redraw();
  ensureTimer();
}

function redraw(){
  if (!_bodyEl || !_data) return;
  var claimedId = _data.claimed_id || null;
  var all = (_data.contracts || []).slice();

  var list = all.filter(function(c){
    return _filter === 'all' || c.tier === _filter;
  });
  // Viewer's claimed contract pins to the top; the rest by reward desc.
  list.sort(function(a, b){
    var ac = (claimedId != null && a.id === claimedId) ? 1 : 0;
    var bc = (claimedId != null && b.id === claimedId) ? 1 : 0;
    if (ac !== bc) return bc - ac;
    return (b.reward || 0) - (a.reward || 0);
  });

  _bodyEl.textContent = '';

  _bodyEl.appendChild(el('div', {class: 'm3b-meta'}, [
    el('span', {class: 'm3b-open-count',
        text: all.length + ' open contract' + (all.length === 1 ? '' : 's')})
  ]));
  _bodyEl.appendChild(filterRow());

  var listEl = el('div', {class: 'm3b-list'});
  if (!list.length){
    listEl.appendChild(el('div', {class: 'm3b-empty',
        text: _filter === 'all'
          ? 'No active bounties posted. Check back later.'
          : 'No ' + _filter + '-tier contracts on the board.'}));
  } else {
    list.forEach(function(c){ listEl.appendChild(contractCard(c, claimedId)); });
  }
  _bodyEl.appendChild(listEl);

  _bodyEl.appendChild(el('div', {class: 'm3b-foot',
      text: 'One claim at a time \u00B7 contracts expire if unclaimed \u00B7 ' +
            'alive bonus needs a live capture.'}));

  // Single delegated click handler per redraw.
  _bodyEl.onclick = function(ev){
    var t = ev.target;
    while (t && t !== _bodyEl && !t.getAttribute) t = t.parentNode;
    while (t && t !== _bodyEl &&
           !(t.getAttribute('data-act') || t.getAttribute('data-filter'))){
      t = t.parentNode;
    }
    if (!t || t === _bodyEl) return;
    var f = t.getAttribute('data-filter');
    if (f){ _filter = f; redraw(); return; }
    var act = t.getAttribute('data-act');
    var cid = t.getAttribute('data-cid');
    if (act === 'details'){
      _expanded[cid] = !_expanded[cid];
      redraw();
    } else if (act === 'claim' && _stage){
      _stage('+bounty/claim ' + cid);
    } else if (act === 'track' && _stage){
      _stage('+bounty/track');
    }
  };
}

function titleFor(data){
  return 'Bounty Board';
}

function resetState(){
  _filter = 'all';
  _expanded = {};
}

window.M3Board = {
  render: render,
  stop: stop,
  titleFor: titleFor,
  resetState: resetState
};

})();
