/* ============================================================================
   m3_region.js — Region-control side panel (Webify Drop UI-2)

   Right-column sibling of the room panel. Renders the region_state push
   (engine/territory_display.get_region_data_block): security, ownership,
   influence ladder (50 foothold / 100 dominant on a 0-150 scale, viewer row
   boxed), weekly resource outlook, and the active-contest tug-of-war + live
   countdown. No new engine logic — a wiring drop.

   Vanilla port of design_handoff_webify/webify/region.jsx. Token-only: every
   colour resolves from client.html :root (the prototype's per-org rainbow is a
   prototype nicety; the binding law is "no new colours", so orgs read through
   the existing accent/self/warn tokens). B3-clean: org *names* come straight
   from the server-resolved org_name field; codes are only ever humanized, so
   no Imperial/Rebel/etc. literal can leak in.
   ============================================================================ */
(function(){
'use strict';

// Influence scale + thresholds — must mirror engine/territory_display
// (_influence_tier: dominant >= 100, foothold >= 50). DO NOT invent others.
var INFLUENCE_MAX      = 150;
var INFLUENCE_FOOTHOLD = 50;
var INFLUENCE_DOMINANT = 100;

// The only three security values the engine emits. Maps to a token class on
// the shared .room-sec-badge idiom (secured=self/green, contested=accent,
// lawless=warn) — same classes the room banner already uses.
var SEC_CLASS = { secured: 'secured', contested: 'contested', lawless: 'lawless' };

// Module-held countdown interval so a re-render (every room-change push)
// never leaks a stale timer pointed at a discarded DOM node.
var _timer = null;

// ── tiny HTML element helper (modules use a local el() for HTML; svgEl is
//    M3Tokens' job and is SVG-only) ──────────────────────────────────────
function el(tag, attrs, children){
  var n = document.createElement(tag);
  if (attrs){
    Object.keys(attrs).forEach(function(k){
      if (k === 'text') { n.textContent = attrs[k]; }
      else if (k === 'class') { n.className = attrs[k]; }
      else if (k === 'style') { n.setAttribute('style', attrs[k]); }
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
  return String(code).replace(/_/g, ' ').replace(/\b\w/g, function(m){ return m.toUpperCase(); });
}

function fmtCountdown(secs){
  secs = Math.max(0, Math.floor(secs || 0));
  var m = Math.floor(secs / 60), s = secs % 60;
  if (m >= 60){ var h = Math.floor(m / 60); m = m % 60; return h + 'h ' + m + 'm'; }
  return m + ':' + (s < 10 ? '0' : '') + s;
}

function sectionLabel(txt, rightTxt){
  var kids = [ el('span', { text: txt }) ];
  if (rightTxt) kids.push(el('span', { class: 'rgn-sec-right', text: rightTxt }));
  return el('div', { class: 'rgn-sec-label' }, kids);
}

// ── influence ladder ─────────────────────────────────────────────────────
function buildInfluence(influence){
  var wrap = el('div', { class: 'rgn-inf-wrap' });
  (influence || []).forEach(function(o){
    var me  = !!o.is_viewer;
    var pct = Math.min(100, (Number(o.score || 0) / INFLUENCE_MAX) * 100);
    var row = el('div', { class: 'rgn-inf-row' + (me ? ' me' : '') });

    var nameKids = [ el('span', { class: 'rgn-inf-name', text: o.org_name || humanize(o.org_code) }) ];
    if (me) nameKids.push(el('span', { class: 'rgn-inf-you', text: ' \u25C2 you' }));

    var scoreKids = [ document.createTextNode(String(o.score)) ];
    if (o.tier && o.tier !== 'no_presence'){
      scoreKids.push(el('span', { class: 'rgn-inf-tier', text: ' ' + String(o.tier).toUpperCase() }));
    }
    var head = el('div', { class: 'rgn-inf-head' }, [
      el('span', {}, nameKids),
      el('span', { class: 'rgn-inf-score', text: '' }),
    ]);
    // fill the score span with mixed nodes
    var scoreSpan = head.lastChild; scoreSpan.textContent = '';
    scoreKids.forEach(function(k){ scoreSpan.appendChild(typeof k === 'string' ? document.createTextNode(k) : k); });

    var track = el('div', { class: 'rgn-inf-track' + (me ? ' glow' : '') }, [
      el('div', { class: 'rgn-inf-fill', style: 'width:' + pct.toFixed(1) + '%;' }),
      el('div', { class: 'rgn-inf-tick', style: 'left:' + ((INFLUENCE_FOOTHOLD / INFLUENCE_MAX) * 100).toFixed(1) + '%;' }),
      el('div', { class: 'rgn-inf-tick', style: 'left:' + ((INFLUENCE_DOMINANT / INFLUENCE_MAX) * 100).toFixed(1) + '%;' }),
    ]);

    row.appendChild(head);
    row.appendChild(track);
    wrap.appendChild(row);
  });
  wrap.appendChild(el('div', { class: 'rgn-inf-scale' }, [
    el('span', { text: '0' }),
    el('span', { text: '50 \u00B7 FOOTHOLD' }),
    el('span', { text: '100 \u00B7 DOMINANT' }),
    el('span', { text: '150' }),
  ]));
  return wrap;
}

// ── resource outlook chips ─────────────────────────────────────────────────
function buildResources(outlook){
  var all = (outlook && outlook.all) || {};
  var best = outlook && outlook.best;
  var wrap = el('div', { class: 'rgn-res-wrap' });
  Object.keys(all).forEach(function(type){
    var mult = Number(all[type]);
    var cls = 'rgn-res-chip';
    if (mult > 1.05) cls += ' good';
    else if (mult < 0.95) cls += ' bad';
    if (best && best.type === type) cls += ' best';
    wrap.appendChild(el('span', { class: cls, title: (best && best.type === type) ? 'best this week' : '' }, [
      el('span', { class: 'rgn-res-type', text: type }),
      el('span', { class: 'rgn-res-mult', text: mult.toFixed(2) + '\u00D7' }),
    ]));
  });
  if (Object.keys(all).length === 0){
    wrap.appendChild(el('span', { class: 'rgn-empty', text: 'no survey data' }));
  }
  return wrap;
}

// ── active-contest sub-card ─────────────────────────────────────────────────
function buildContest(contest, codeToName){
  var acc = contest.accumulation || {};
  var chCode = contest.challenger_org, dfCode = contest.defender_org;
  var chName = codeToName[chCode] || humanize(chCode);
  var dfName = codeToName[dfCode] || humanize(dfCode);
  var chScore = Number(acc[chCode] || 0), dfScore = Number(acc[dfCode] || 0);
  var total = chScore + dfScore;
  var chPct = total ? (chScore / total) * 100 : 50;

  var timerSpan = el('span', { class: 'rgn-contest-timer', text: '\u29D7 ' + fmtCountdown(contest.secs_remaining) });

  var card = el('div', { class: 'rgn-contest' }, [
    el('div', { class: 'rgn-contest-head' }, [
      el('span', { class: 'rgn-contest-title', text: '\u2694 ACTIVE CONTEST' }),
      timerSpan,
    ]),
    el('div', { class: 'rgn-contest-names' }, [
      el('span', { class: 'rgn-side-ch' }, [
        document.createTextNode(chName + ' '),
        el('span', { class: 'rgn-side-num', text: String(chScore) }),
      ]),
      el('span', { class: 'rgn-side-df' }, [
        el('span', { class: 'rgn-side-num', text: String(dfScore) }),
        document.createTextNode(' ' + dfName),
      ]),
    ]),
    el('div', { class: 'rgn-tug' }, [
      el('div', { class: 'rgn-tug-fill', style: 'width:' + chPct.toFixed(1) + '%;' }),
      el('div', { class: 'rgn-tug-mid' }),
    ]),
  ]);

  // Live countdown — re-render clears any prior interval first (see render()).
  var remaining = Math.max(0, Math.floor(contest.secs_remaining || 0));
  if (remaining > 0 && typeof setInterval === 'function'){
    _timer = setInterval(function(){
      remaining = Math.max(0, remaining - 1);
      timerSpan.textContent = '\u29D7 ' + fmtCountdown(remaining);
      if (remaining <= 0 && _timer){ clearInterval(_timer); _timer = null; }
    }, 1000);
  }
  return card;
}

// ── public: render the panel body for a region block ───────────────────────
function render(block){
  stop();  // clear any prior countdown before building a fresh body
  block = block || {};
  var root = el('div', { class: 'rgn-root' });

  // Identity row: region name + security badge inline (room-banner idiom).
  var secCls = SEC_CLASS[block.security] || 'contested';
  var nameRow = el('div', { class: 'rgn-name-row' }, [
    el('span', { class: 'rgn-name', text: block.region_name || humanize(block.region_slug) }),
    el('span', { class: 'room-sec-badge ' + secCls, text: (block.security || 'contested').toUpperCase() }),
  ]);
  root.appendChild(nameRow);
  if (block.planet) root.appendChild(el('div', { class: 'rgn-planet', text: String(block.planet).toUpperCase() }));
  if (block.description) root.appendChild(el('div', { class: 'rgn-desc', text: block.description }));

  // Ownership.
  var ownSec = el('div', { class: 'rgn-block' }, [ sectionLabel('Ownership') ]);
  if (block.ownership && block.ownership.org_code){
    ownSec.appendChild(el('div', { class: 'rgn-own' }, [
      el('span', { class: 'rgn-own-dot' }),
      el('span', { class: 'rgn-own-name', text: block.ownership.org_name || humanize(block.ownership.org_code) }),
      el('span', { class: 'room-sec-badge contested', text: String(block.ownership.tier || '').toUpperCase() }),
    ]));
  } else {
    ownSec.appendChild(el('span', { class: 'rgn-empty', text: 'un-owned' }));
  }
  root.appendChild(ownSec);

  // Influence ladder.
  root.appendChild(el('div', { class: 'rgn-block' }, [
    sectionLabel('Influence'),
    buildInfluence(block.influence),
  ]));

  // Independent / unaligned PCs may observe contest + outlook, but they read
  // as disabled rather than hidden (don't-invent rail).
  var spectating = !block.viewer_org || block.viewer_org === 'independent';

  // Resource outlook.
  var resBlock = el('div', { class: 'rgn-block' + (spectating ? ' rgn-spectating' : '') }, [
    sectionLabel('Resource outlook', 'this week'),
    buildResources(block.resource_outlook),
  ]);
  root.appendChild(resBlock);

  // Active contest (only if one is live).
  if (block.active_contest){
    var codeToName = {};
    (block.influence || []).forEach(function(o){ if (o.org_code) codeToName[o.org_code] = o.org_name || humanize(o.org_code); });
    var contestWrap = el('div', { class: spectating ? 'rgn-spectating' : '' }, [
      buildContest(block.active_contest, codeToName),
    ]);
    root.appendChild(contestWrap);
  }

  if (spectating){
    root.appendChild(el('div', { class: 'rgn-spectate-note', text: 'Unaligned \u2014 you can observe but not contest this region.' }));
  }
  return root;
}

function stop(){
  if (_timer){ clearInterval(_timer); _timer = null; }
}

window.M3Region = {
  render: render,
  stop: stop,
  // exposed for tests / reuse
  fmtCountdown: fmtCountdown,
  INFLUENCE_MAX: INFLUENCE_MAX,
  INFLUENCE_FOOTHOLD: INFLUENCE_FOOTHOLD,
  INFLUENCE_DOMINANT: INFLUENCE_DOMINANT,
};

})();
