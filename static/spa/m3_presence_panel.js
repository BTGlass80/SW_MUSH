/* ============================================================================
   m3_presence_panel.js — Global who's-online card (UX Drop 5: presence/social).

   A right-rail PRESENCE card answering a new player's first-60-seconds
   question — "are other humans logged in right now, and where?" — by surfacing
   the already-public online roster. Pure social proof + low-friction discovery:
   see who's around, then walk toward an active area.

   Fed by the EXISTING public endpoint GET /api/portal/who
   (server/web_portal.py::handle_who), whose shape is:
     { online: [ {name, species, location_area, idle_seconds, faction}, ... ],
       count: N, uptime_seconds: N }

   Off-cost-free discipline (the add-vs-detract contract):
     · Polls ONLY while the card is expanded. start(bodyEl) arms a single
       interval and does one immediate fetch; stop() clears it. Collapsed =
       zero render + zero polling. The consumer wires start/stop to the panel's
       collapse toggle so a keyboard player who never opens it pays nothing.
     · No focus-steal, no auto-scroll, no animation beyond the rail idiom.
     · Read-only: it lists presence, it never sends a command or gates pace.

   XSS contract: name / species / location_area / faction are server free text
   — every one is written via textContent or routed through injected escapeHtml,
   never raw innerHTML.

   Dependency injection (testable standalone under jsdom):
     · init({ escapeHtml, fetchImpl, intervalMs })
         escapeHtml  — shared client escape (falls back to a built-in).
         fetchImpl   — fetch override for tests (defaults to window.fetch).
         intervalMs  — poll cadence (default 8000ms; bounded 5-10s per spec).
   ============================================================================ */
(function(){
'use strict';

var WHO_URL       = '/api/portal/who';
var DEFAULT_POLL  = 8000;   // 8s — within the 5-10s spec band.
var MIN_POLL      = 4000;

// ── Module-private state ──────────────────────────────────────────────
var _escapeHtml = _defaultEscapeHtml;
var _fetch      = null;     // resolved lazily (window.fetch) unless injected.
var _intervalMs = DEFAULT_POLL;
var _timer      = null;     // single poll interval; null when collapsed/stopped.
var _bodyEl     = null;     // the target body element while running.
var _countEl    = null;     // optional count-badge element (updated each poll).

function init(deps) {
  deps = deps || {};
  if (typeof deps.escapeHtml === 'function') _escapeHtml = deps.escapeHtml;
  if (typeof deps.fetchImpl === 'function') _fetch = deps.fetchImpl;
  if (typeof deps.intervalMs === 'number' && deps.intervalMs > 0) {
    _intervalMs = Math.max(MIN_POLL, deps.intervalMs);
  }
}

function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _resolveFetch() {
  if (typeof _fetch === 'function') return _fetch;
  if (typeof window !== 'undefined' && typeof window.fetch === 'function') {
    return window.fetch.bind(window);
  }
  return null;
}

function el(tag, attrs, children){
  var n = document.createElement(tag);
  if (attrs){
    Object.keys(attrs).forEach(function(k){
      if (k === 'text') { n.textContent = attrs[k]; }
      else if (k === 'class') { n.className = attrs[k]; }
      else if (k === 'title') { n.setAttribute('title', attrs[k]); }
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

// Compact idle label: <1m → "active", else "Nm" / "Nh".
function _fmtIdle(secs){
  var s = Number(secs) || 0;
  if (s < 60) return 'active';
  if (s < 3600) return Math.floor(s / 60) + 'm idle';
  return Math.floor(s / 3600) + 'h idle';
}

/* renderInto(bodyEl, data) — pure render of the who payload into bodyEl.
   `data` is the parsed /api/portal/who response. Tolerant of a missing/empty
   `online` list (renders an empty-state line). Returns the player count. */
function renderInto(bodyEl, data){
  if (!bodyEl) return 0;
  var online = (data && Array.isArray(data.online)) ? data.online : [];

  bodyEl.innerHTML = '';

  if (online.length === 0) {
    bodyEl.appendChild(el('div', {
      class: 'presence-empty',
      text: 'No other players online right now.',
    }));
    return 0;
  }

  online.forEach(function(p){
    if (!p) return;
    var row = el('div', { class: 'presence-row' });
    row.appendChild(el('span', { class: 'presence-icon', text: '👤' }));

    var nameWrap = el('div', { class: 'presence-namewrap' });
    nameWrap.appendChild(el('span', {
      class: 'presence-name',
      text: p.name || 'Unknown',
      title: (p.name || 'Unknown') +
             (p.species ? ' — ' + humanize(p.species) : ''),
    }));
    var loc = p.location_area ? String(p.location_area) : 'Unknown';
    nameWrap.appendChild(el('span', {
      class: 'presence-loc',
      text: loc,
      title: loc,
    }));
    row.appendChild(nameWrap);

    row.appendChild(el('span', {
      class: 'presence-idle',
      text: _fmtIdle(p.idle_seconds),
    }));
    bodyEl.appendChild(row);
  });

  return online.length;
}

// One fetch + render. Best-effort: a failed fetch leaves the last render in
// place (no flicker to an error state on a transient blip).
function _poll(bodyEl){
  var f = _resolveFetch();
  if (!f) return;
  var p = f(WHO_URL, { credentials: 'same-origin' });
  if (!p || typeof p.then !== 'function') return;
  p.then(function(resp){
    return resp && typeof resp.json === 'function' ? resp.json() : null;
  }).then(function(data){
    // Only render if we're still the active body (not stopped mid-flight).
    if (data && bodyEl === _bodyEl) {
      renderInto(bodyEl, data);
      if (_countEl) _countEl.textContent = (data.count != null) ? String(data.count) : '';
    }
  }).catch(function(){ /* transient: keep last good render */ });
}

/* start(bodyEl) — begin polling into bodyEl. Idempotent: a second start
   re-targets the body and resets the interval. Does an immediate fetch so the
   card populates the instant it's expanded. */
function start(bodyEl, countEl){
  stop();
  _bodyEl = bodyEl || null;
  _countEl = countEl || null;
  if (!_bodyEl) return;
  _poll(_bodyEl);
  _timer = setInterval(function(){ _poll(_bodyEl); }, _intervalMs);
}

/* stop() — halt polling. Collapsed cards call this so they cost nothing. */
function stop(){
  if (_timer != null){ clearInterval(_timer); _timer = null; }
  _bodyEl = null;
  if (_countEl){ _countEl.textContent = ''; _countEl = null; }
}

function isPolling(){ return _timer != null; }

window.M3PresencePanel = {
  init: init,
  render: renderInto,     // alias for the pure render (tests + manual calls)
  renderInto: renderInto,
  start: start,
  stop: stop,
  isPolling: isPolling,
};

})();
