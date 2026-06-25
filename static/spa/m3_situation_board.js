/* ============================================================================
   m3_situation_board.js — Living-world situation board (UX Drop 4).

   The SIT cartridge / sidebar body. A lean, always-current read-only MIRROR of
   what the Director already produced for the player's current zone:

     · zone-faction INFLUENCE ladder  (region-ladder idiom + faction colors)
     · live WORLD-EVENTS rows         (M3Holonet.buildWorldEventsPanel idiom)
     · the active UPRISING card       (cult scenario + menace threat-meter)
     · the last 3-5 HEADLINE rows      (holonet news-row idiom, truncated)

   It never GATES pace or information — every fact is already reachable via
   +news / +holonet / the region panel. Pure render over the `situation_state`
   push (server/session.py _hud_situation_digest → DirectorAI.compile_situation_
   digest). Zero new socket cadence: rides the existing HUD tick.

   Payload (situation_state):
     { zone: "mos_eisley",
       influence: [ {faction, score}, ... ],          // 0-100 score
       events:    [ {type, name, zones, remaining_minutes, effects, headline}, ... ],
       uprising:  {cult_key, zone_label, menace, state} | null,   // menace 0-100
       news:      [ {timestamp, event_type, summary}, ... ] }

   B3 era-cleanness: faction / cult codes are humanized for display only; no
   Imperial/Rebel literal can leak (server emits native CW faction keys).

   Dependencies (all OPTIONAL — degrades cleanly if absent so the module is
   unit-testable standalone under jsdom):
     · window.M3AssetsIcons.FACTION_ICONS  — per-faction color/icon (m3_assets_icons.js)
     · injected escapeHtml via init({escapeHtml}) — else a built-in fallback.
   ============================================================================ */
(function(){
'use strict';

// ── Influence scale (0-100; the Director's MIN/MAX_INFLUENCE). foothold/
//    dominant thresholds mirror the region ladder's reading idiom. ──
var INFLUENCE_MAX      = 100;
var INFLUENCE_FOOTHOLD = 40;
var INFLUENCE_DOMINANT = 70;

// ── Menace → threat-level token (0-100). Mirrors the influence-threshold
//    idiom: a discrete band drives a color token + label. ──
var MENACE_LOW    = 33;   // < LOW          → simmering
var MENACE_MED    = 66;   // LOW .. < MED   → rising
                          // >= MED          → cresting

// Per-faction accent color, resolved from the shared faction-icon asset's
// own palette where available, else a small CW-native fallback map. Used as
// the ladder fill color. Server faction codes map onto the icon keys.
var _FACTION_COLOR = {
  republic:    '#7ce0d0',
  cis:         '#ff5a4a',
  jedi_order:  '#9ad1ff',
  hutt_cartel: '#d4a44b',
  bhg:         '#ffc857',
  black_sun:   '#b388ff',
  independent: '#a09584',
};

// Module-private escape hook (DI, mirrors m3_holonet.init).
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

// ── tiny HTML element helper (mirror m3_region.js el(); textContent is the
//    safe path, but headlines also route through _escapeHtml on the title
//    attribute / any innerHTML edge per the XSS contract). ──
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

// Assign server-authored text through the XSS escape, written as escaped
// entities (inert). The escape is applied ONCE — the result is set via
// innerHTML, so a malicious <script>/<img> renders as &lt;…&gt; text, never
// as a live tag. (textContent would single-escape too, but the explicit
// escapeHtml path satisfies the XSS contract and keeps the entity form
// assertable in tests.)
function setText(node, raw){
  node.innerHTML = _escapeHtml(raw);
  return node;
}

function truncate(s, n){
  s = String(s == null ? '' : s);
  return (s.length > n) ? (s.slice(0, n - 1) + '…') : s;
}

function influenceTier(score){
  score = Number(score || 0);
  if (score >= INFLUENCE_DOMINANT) return 'DOMINANT';
  if (score >= INFLUENCE_FOOTHOLD) return 'FOOTHOLD';
  return null;
}

function factionColor(code){
  return _FACTION_COLOR[code] || '#ffc857';
}

function sectionLabel(txt){
  return el('div', { class: 'sit-sec-label' }, [ el('span', { text: txt }) ]);
}

// ── influence ladder ─────────────────────────────────────────────────────
function buildInfluence(influence){
  var wrap = el('div', { class: 'sit-inf-wrap' });
  var rows = (influence || []).slice().sort(function(a, b){
    return Number(b.score || 0) - Number(a.score || 0);
  });
  rows.forEach(function(o){
    var c   = factionColor(o.faction);
    var pct = Math.min(100, (Number(o.score || 0) / INFLUENCE_MAX) * 100);
    var tier = influenceTier(o.score);

    var scoreSpan = el('span', { class: 'sit-inf-score' }, [
      document.createTextNode(String(Number(o.score || 0))),
    ]);
    if (tier){
      scoreSpan.appendChild(el('span', { class: 'sit-inf-tier', text: ' ' + tier }));
    }

    var head = el('div', { class: 'sit-inf-head' }, [
      el('span', { class: 'sit-inf-name', text: humanize(o.faction) }),
      scoreSpan,
    ]);
    var track = el('div', { class: 'sit-inf-track' }, [
      el('div', { class: 'sit-inf-fill', style: 'width:' + pct.toFixed(1) + '%;background:' + c + ';' }),
      el('div', { class: 'sit-inf-tick', style: 'left:' + ((INFLUENCE_FOOTHOLD / INFLUENCE_MAX) * 100).toFixed(1) + '%;' }),
      el('div', { class: 'sit-inf-tick', style: 'left:' + ((INFLUENCE_DOMINANT / INFLUENCE_MAX) * 100).toFixed(1) + '%;' }),
    ]);
    wrap.appendChild(el('div', { class: 'sit-inf-row' }, [head, track]));
  });
  if (rows.length === 0){
    wrap.appendChild(el('span', { class: 'sit-empty', text: 'no influence data for this zone' }));
  }
  return wrap;
}

// ── world-events rows (adapt the situation_state event shape to the holonet
//    world-events idiom). Falls back to a self-contained row if M3Holonet
//    isn't loaded. ──
function buildEvents(events){
  events = events || [];
  var wrap = el('div', { class: 'sit-events-wrap', 'data-sit-events': '1' });
  if (events.length === 0){
    wrap.appendChild(el('span', { class: 'sit-empty', text: 'no active galaxy events here' }));
    return wrap;
  }
  events.forEach(function(e){
    var mins = Number(e.remaining_minutes || 0);
    var status = mins > 0 ? (mins + 'M LEFT') : 'ACTIVE';
    var row = el('div', { class: 'sit-event-row', 'data-world-event-name': e.name || (e.type || '') }, [
      el('div', { class: 'sit-event-head' }, [
        el('span', { class: 'sit-event-name', text: e.name || humanize(e.type) }),
        el('span', { class: 'sit-event-status', text: status }),
      ]),
    ]);
    // Headline is server-authored text. setText() routes it through the XSS
    // escape (single-escaped, then assigned as text — no live markup).
    if (e.headline){
      row.appendChild(setText(el('div', { class: 'sit-event-headline' }), e.headline));
    }
    wrap.appendChild(row);
  });
  return wrap;
}

// ── uprising card with a menace threat-meter token ─────────────────────────
function menaceBand(menace){
  menace = Number(menace || 0);
  if (menace >= MENACE_MED) return { key: 'cresting', label: 'CRESTING', cls: 'sit-menace-high' };
  if (menace >= MENACE_LOW) return { key: 'rising',   label: 'RISING',   cls: 'sit-menace-med'  };
  return { key: 'simmering', label: 'SIMMERING', cls: 'sit-menace-low' };
}

function buildUprising(uprising){
  // Null/absent uprising → no card (graceful degrade, no throw).
  if (!uprising || !uprising.cult_key) return null;
  var menace = Number(uprising.menace || 0);
  var pct = Math.min(100, Math.max(0, menace));
  var band = menaceBand(menace);

  var card = el('div', { class: 'sit-uprising ' + band.cls, 'data-sit-uprising': uprising.cult_key }, [
    el('div', { class: 'sit-uprising-head' }, [
      el('span', { class: 'sit-uprising-title', text: '⚠ ' + humanize(uprising.cult_key) }),
      el('span', { class: 'sit-uprising-band', text: band.label }),
    ]),
  ]);
  if (uprising.zone_label){
    card.appendChild(el('div', { class: 'sit-uprising-loc', text: uprising.zone_label }));
  }
  // Menace threat-meter token.
  card.appendChild(el('div', { class: 'sit-menace-track', 'data-sit-menace': String(Math.round(menace)) }, [
    el('div', { class: 'sit-menace-fill', style: 'width:' + pct.toFixed(1) + '%;' }),
    el('div', { class: 'sit-menace-tick', style: 'left:' + MENACE_LOW + '%;' }),
    el('div', { class: 'sit-menace-tick', style: 'left:' + MENACE_MED + '%;' }),
  ]));
  card.appendChild(el('div', { class: 'sit-menace-scale' }, [
    el('span', { text: 'MENACE ' + Math.round(menace) }),
    el('span', { text: String(uprising.state || '').toUpperCase() }),
  ]));
  return card;
}

// ── headline rows (truncated, holonet news-row idiom) ─────────────────────
function buildNews(news){
  var wrap = el('div', { class: 'sit-news-wrap', 'data-sit-news': '1' });
  var rows = (news || []).slice(0, 5);
  if (rows.length === 0){
    wrap.appendChild(el('span', { class: 'sit-empty', text: 'no recent headlines' }));
    return wrap;
  }
  rows.forEach(function(r){
    var cat = String(r.event_type || 'news').toUpperCase();
    // Server-authored summary. The full text rides the title attr — setAttribute
    // is a safe sink (attribute values aren't parsed as HTML), so it carries the
    // raw text for a clean tooltip. The visible row is a truncated copy written
    // through setText/escapeHtml (inert — no live markup can leak).
    var summary = el('span', { class: 'sit-news-summary',
                               title: String(r.summary || '') });
    setText(summary, truncate(r.summary, 72));
    var row = el('div', { class: 'sit-news-row', 'data-sit-news-row': '1' }, [
      el('span', { class: 'sit-news-cat', text: cat }),
      summary,
    ]);
    wrap.appendChild(row);
  });
  return wrap;
}

// ── public: render the cartridge / sidebar body for a situation_state ──────
function render(state){
  state = state || {};
  var root = el('div', { class: 'sit-root', 'data-sit-board': '1' });

  // Zone identity row.
  root.appendChild(el('div', { class: 'sit-zone-row' }, [
    el('span', { class: 'sit-zone-name', text: humanize(state.zone) || 'UNKNOWN ZONE' }),
  ]));

  // Influence ladder.
  root.appendChild(el('div', { class: 'sit-block' }, [
    sectionLabel('Zone Influence'),
    buildInfluence(state.influence),
  ]));

  // Active uprising (only when one is live).
  var uprisingCard = buildUprising(state.uprising);
  if (uprisingCard){
    root.appendChild(el('div', { class: 'sit-block' }, [
      sectionLabel('Active Uprising'),
      uprisingCard,
    ]));
  }

  // Live world events.
  root.appendChild(el('div', { class: 'sit-block' }, [
    sectionLabel('Live Galaxy State'),
    buildEvents(state.events),
  ]));

  // Recent headlines.
  root.appendChild(el('div', { class: 'sit-block' }, [
    sectionLabel('Headlines'),
    buildNews(state.news),
  ]));

  return root;
}

window.M3SituationBoard = {
  render: render,
  init: init,
  // exposed for tests / reuse
  INFLUENCE_MAX: INFLUENCE_MAX,
  INFLUENCE_FOOTHOLD: INFLUENCE_FOOTHOLD,
  INFLUENCE_DOMINANT: INFLUENCE_DOMINANT,
  MENACE_LOW: MENACE_LOW,
  MENACE_MED: MENACE_MED,
  menaceBand: menaceBand,
};

})();
