/* ============================================================================
   m3_command_palette.js — Ctrl/Cmd+K command palette (UX Drop 7).

   An opt-in, fuzzy-searchable overlay over the full player verb surface.
   Data source: GET /api/portal/reference (the existing, access-gated
   reference index). The endpoint already filters by caller access level, so
   the palette is access-filtered for free — zero engine/server change needed.

   STAGING CONTRACT (invariant):
     Selecting a verb STAGES it into the active input (sets value, focuses).
     It NEVER calls ws.send / sendCmd. The player presses Enter themselves.

   CLOSED-PALETTE INPUT INVARIANT:
     When the palette is closed, setupInput's existing keydown behavior is
     byte-for-byte unchanged. The palette attaches a SEPARATE document-level
     keydown (Ctrl/Cmd+K only); its Up/Down/Enter navigation is dead unless
     the palette is open.

   Keyboard:
     Ctrl/Cmd+K  — toggle palette (preventDefault only for this combo)
     Escape      — close
     Up/Down     — navigate rows while OPEN
     Enter       — stage the selected row while OPEN

   localStorage key: sw_cmd_palette  (default enabled; set to '0' to disable)

   Dependency injection (mirrors m3_goals.js / m3_scene_panel.js):
     init({ escapeHtml, fetchImpl, stage })
       escapeHtml  — injected from the host page (falls back to built-in)
       fetchImpl   — fetch replacement for tests (defaults to window.fetch)
       stage(cmd)  — callback that puts cmd into the active input + focuses
                     (injected so tests can assert it without a real DOM input)

   Testable standalone under jsdom — event handlers use only module-private
   helpers (no references to top-level client.html helpers inside handlers).
   ============================================================================ */
(function () {
'use strict';

// ── Module-private DI sinks ─────────────────────────────────────────────────
var _escapeHtml = _defaultEscapeHtml;
var _fetch = (typeof window !== 'undefined' && window.fetch)
  ? function (url) { return window.fetch(url); }
  : null;
var _stage = null;   // injected stage(cmd) callback

// ── State ───────────────────────────────────────────────────────────────────
var _open = false;
var _cache = null;    // flat array of summary entries after first fetch
var _fetching = false; // in-flight guard so rapid re-opens don't fetch-storm
var _query = '';
var _results = [];    // top-10 currently displayed entries
var _cursor = -1;     // keyboard-selected row index (-1 = none)
var _overlayEl = null;
var _inputEl = null;  // palette search <input>
var _listEl = null;   // <ul> for results

// ── Reduced-motion preference (checked once at module load) ─────────────────
// We do not animate when the user prefers reduced motion. The palette itself
// has no animation — this guard future-proofs any CSS transition we might add.
var _prefersReducedMotion = (
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches
);

// ── Init ────────────────────────────────────────────────────────────────────
function init(deps) {
  deps = deps || {};
  if (typeof deps.escapeHtml === 'function')  _escapeHtml = deps.escapeHtml;
  if (typeof deps.fetchImpl  === 'function')  _fetch      = deps.fetchImpl;
  if (typeof deps.stage      === 'function')  _stage      = deps.stage;

  // Wire the document-level Ctrl/Cmd+K handler (separate from setupInput).
  if (typeof document !== 'undefined') {
    document.addEventListener('keydown', _handleGlobalKeydown);

    // If the static HTML element already exists, wire its backdrop click and
    // the search input now so they're ready before the first open.
    var existing = document.getElementById('command-palette');
    if (existing) {
      _wireStaticOverlay(existing);
    }
  }
}

// ── Wire an already-existing static overlay element ──────────────────────────
// Called once from init() when client.html provides the #command-palette div.
// The programmatic-build path in _getOrCreateOverlay wires these same events
// itself, so this is only needed for the static HTML case.
function _wireStaticOverlay(ov) {
  // Backdrop click
  ov.addEventListener('click', function (e) {
    if (e.target === ov) _close();
  });

  // Search input events
  var inp = ov.querySelector('.cp-input');
  if (inp) {
    inp.addEventListener('input', function () {
      _query = inp.value;
      _renderResults(_query);
    });
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') e.preventDefault();
    });
  }
}

// ── Default escape (mirrors m3_scene_panel / m3_goals built-in) ─────────────
function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Global keydown: Ctrl/Cmd+K only ─────────────────────────────────────────
// This handler is SEPARATE from setupInput's keydown and only acts on
// Ctrl/Cmd+K (or Escape to close). When the palette is CLOSED it does
// nothing at all for any other key, leaving setupInput's behavior 100% intact.
function _handleGlobalKeydown(e) {
  // Ctrl/Cmd+K — toggle palette
  var isK = (e.key === 'k' || e.key === 'K');
  if (isK && (e.ctrlKey || e.metaKey)) {
    // Respect opt-out preference.
    if (!_isPaletteEnabled()) return;
    e.preventDefault();
    if (_open) _close(); else _open_palette();
    return;
  }
  // Escape — close when open
  if (e.key === 'Escape' && _open) {
    _close();
    return;
  }
  // Up/Down/Enter — palette navigation ONLY when open
  if (!_open) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _moveCursor(1);
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    _moveCursor(-1);
    return;
  }
  if (e.key === 'Enter') {
    e.preventDefault();
    _selectCurrent();
    return;
  }
}

// ── opt-in check ─────────────────────────────────────────────────────────────
function _isPaletteEnabled() {
  try {
    var v = localStorage.getItem('sw_cmd_palette');
    return v !== '0';
  } catch (_) {
    return true;
  }
}

// ── Open ─────────────────────────────────────────────────────────────────────
function _open_palette() {
  _overlayEl = _getOrCreateOverlay();
  if (!_overlayEl) return;   // no document (e.g. headless) — nothing to open
  _inputEl   = _overlayEl.querySelector('.cp-input');
  _listEl    = _overlayEl.querySelector('.cp-list');

  _open = true;
  _cursor = -1;
  _overlayEl.style.display = 'flex';

  // Reset search field and results
  if (_inputEl) {
    _inputEl.value = '';
    _query = '';
    _inputEl.focus();
  }
  _renderResults('');

  // Prefetch on first open (subsequent opens reuse cache)
  if (!_cache) {
    _fetchIndex();
  }
}

// ── Close ────────────────────────────────────────────────────────────────────
function _close() {
  _open = false;
  if (_overlayEl) _overlayEl.style.display = 'none';
  // Return focus to the game input (not the palette input) so the player
  // can type a command immediately.
  if (typeof document !== 'undefined') {
    var inp = document.activeElement;
    // Only shift focus away if the palette input currently has it.
    if (inp && inp.classList && inp.classList.contains('cp-input')) {
      // Delegate back to the host page — if stage() is set, we trust the host
      // has its own active input; we look for a well-known id as fallback.
      var gameInput =
        document.getElementById('cmd-input-ground') ||
        document.getElementById('cmd-input-space');
      if (gameInput) gameInput.focus();
    }
  }
}

// ── Overlay DOM: get-or-create ────────────────────────────────────────────────
function _getOrCreateOverlay() {
  if (typeof document === 'undefined') return null;
  var existing = document.getElementById('command-palette');
  if (existing) return existing;

  // Fallback: build the overlay programmatically. In production the
  // client.html provides the element (wired in the static HTML), so
  // this branch only fires in tests / when the element is absent.
  var ov = document.createElement('div');
  ov.id = 'command-palette';
  ov.className = 'cp-overlay';
  ov.style.display = 'none';

  var modal = document.createElement('div');
  modal.className = 'cp-modal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-label', 'Command palette');

  var searchWrap = document.createElement('div');
  searchWrap.className = 'cp-search-wrap';

  var inp = document.createElement('input');
  inp.type = 'text';
  inp.className = 'cp-input';
  inp.placeholder = 'Search commands…';
  inp.setAttribute('autocomplete', 'off');
  inp.setAttribute('spellcheck', 'false');
  inp.setAttribute('aria-label', 'Command search');

  searchWrap.appendChild(inp);

  var list = document.createElement('ul');
  list.className = 'cp-list';
  list.setAttribute('role', 'listbox');
  list.setAttribute('aria-label', 'Command results');

  var footer = document.createElement('div');
  footer.className = 'cp-footer';
  footer.innerHTML = '<span class="cp-hint">&#8593;&#8595; navigate &nbsp;&#x23CE; stage &nbsp;Esc close</span>';

  modal.appendChild(searchWrap);
  modal.appendChild(list);
  modal.appendChild(footer);
  ov.appendChild(modal);

  // Backdrop click closes
  ov.addEventListener('click', function (e) {
    if (e.target === ov) _close();
  });

  // Input events drive filtering
  inp.addEventListener('input', function () {
    _query = inp.value;
    _renderResults(_query);
  });

  // Prevent keydown from escaping to global handler while typing in palette
  // (the global handler already gates on _open; this is defense-in-depth so
  // Arrow keys in the search field scroll results, not the page).
  inp.addEventListener('keydown', function (e) {
    // Let the global handler deal with Escape/Up/Down/Enter while open.
    // Suppress default scroll for arrow keys so only the list scrolls.
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') e.preventDefault();
  });

  document.body.appendChild(ov);
  return ov;
}

// ── Fetch index (once, cached) ────────────────────────────────────────────────
function _fetchIndex() {
  if (!_fetch) return;
  if (_fetching) return;   // a fetch is already in flight — don't storm the endpoint
  _fetching = true;
  _fetch('/api/portal/reference')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      _cache = (data && Array.isArray(data.entries)) ? data.entries : [];
      _fetching = false;
      // Re-render with whatever the user already typed
      if (_open) _renderResults(_query);
    })
    .catch(function () {
      // Silently fail — the palette shows "no results" which is acceptable
      // during a network hiccup or when not connected. Clear the in-flight
      // flag so a later open can retry.
      _fetching = false;
    });
}

// ── Fuzzy scorer: subsequence + substring + prefix boost ────────────────────
// Inline helper (not a module-level declaration referenced from handlers) —
// matches the Drop 2 pattern that avoided the _evSig ReferenceError.
function _score(entry, q) {
  if (!q) return 1;   // empty query: show everything (rendered as top entries)
  var ql = q.toLowerCase();
  var kl = (entry.key   || '').toLowerCase();
  var tl = (entry.title || '').toLowerCase();
  var sl = (entry.summary || '').toLowerCase();

  var score = 0;

  // Exact key match
  if (kl === ql) return 1000;
  // Key prefix
  if (kl.indexOf(ql) === 0) score += 400;
  // Key substring
  else if (kl.indexOf(ql) !== -1) score += 200;
  // Title prefix
  if (tl.indexOf(ql) === 0) score += 150;
  // Title substring
  else if (tl.indexOf(ql) !== -1) score += 80;
  // Summary substring
  if (sl.indexOf(ql) !== -1) score += 30;

  // Subsequence bonus (each char of q found in order in key)
  if (score === 0) {
    var ki = 0;
    var matches = 0;
    for (var qi = 0; qi < ql.length; qi++) {
      while (ki < kl.length && kl[ki] !== ql[qi]) ki++;
      if (ki < kl.length) { matches++; ki++; }
    }
    if (matches === ql.length) score += 20;
    // Also try title subsequence
    else {
      ki = 0; matches = 0;
      for (var qi2 = 0; qi2 < ql.length; qi2++) {
        while (ki < tl.length && tl[ki] !== ql[qi2]) ki++;
        if (ki < tl.length) { matches++; ki++; }
      }
      if (matches === ql.length) score += 10;
    }
  }

  return score;
}

// ── Render results ──────────────────────────────────────────────────────────
function _renderResults(q) {
  if (!_listEl) return;

  var corpus = _cache || [];

  // Score and sort. Filter to is_command entries only: help-only TOPIC_HELP
  // entries carry is_command=false from the server; selecting them would stage
  // a non-typeable key that dead-ends at "Huh?". Topics are reachable via the
  // Reference sidebar; the palette is exclusively for typeable verb shortcuts.
  var scored = [];
  for (var i = 0; i < corpus.length; i++) {
    if (!corpus[i].is_command) continue;
    var s = _score(corpus[i], q);
    if (s > 0) scored.push({ e: corpus[i], s: s });
  }
  scored.sort(function (a, b) {
    if (b.s !== a.s) return b.s - a.s;
    return (a.e.key || '').localeCompare(b.e.key || '');
  });

  // Cap at 10
  _results = scored.slice(0, 10).map(function (x) { return x.e; });
  _cursor = _results.length > 0 ? 0 : -1;

  // Build list HTML using escapeHtml for every server string
  var html = '';
  for (var j = 0; j < _results.length; j++) {
    var entry = _results[j];
    var activeClass = (j === _cursor) ? ' cp-row-active' : '';
    var cat = entry.category ? '<span class="cp-cat">' + _escapeHtml(entry.category) + '</span>' : '';
    var summary = entry.summary
      ? '<span class="cp-summary">' + _escapeHtml(entry.summary) + '</span>'
      : '';
    html += '<li class="cp-row' + activeClass + '" role="option"'
          + ' aria-selected="' + (j === _cursor ? 'true' : 'false') + '"'
          + ' data-idx="' + j + '">'
          + '<span class="cp-key">' + _escapeHtml(entry.key) + '</span>'
          + cat
          + summary
          + '</li>';
  }

  if (!html && !_cache) {
    html = '<li class="cp-row cp-empty">Loading commands…</li>';
  } else if (!html) {
    html = '<li class="cp-row cp-empty">No matches</li>';
  }

  _listEl.innerHTML = html;

  // Wire row clicks
  // (inline, not referencing external helpers — matches Drop 2 pattern)
  var rows = _listEl.querySelectorAll('.cp-row[data-idx]');
  for (var r = 0; r < rows.length; r++) {
    (function (rowEl) {
      rowEl.addEventListener('click', function () {
        var idx = parseInt(rowEl.getAttribute('data-idx'), 10);
        _stageEntry(idx);
      });
      rowEl.addEventListener('mouseenter', function () {
        var idx = parseInt(rowEl.getAttribute('data-idx'), 10);
        _setCursor(idx);
      });
    }(rows[r]));
  }
}

// ── Cursor movement ──────────────────────────────────────────────────────────
function _moveCursor(delta) {
  if (_results.length === 0) return;
  _cursor = (_cursor + delta + _results.length) % _results.length;
  _setCursor(_cursor);
}

function _setCursor(idx) {
  _cursor = idx;
  if (!_listEl) return;
  var rows = _listEl.querySelectorAll('.cp-row[data-idx]');
  for (var i = 0; i < rows.length; i++) {
    var active = (i === idx);
    if (active) {
      rows[i].classList.add('cp-row-active');
      rows[i].setAttribute('aria-selected', 'true');
      // Scroll into view if needed
      if (typeof rows[i].scrollIntoView === 'function') {
        rows[i].scrollIntoView({ block: 'nearest' });
      }
    } else {
      rows[i].classList.remove('cp-row-active');
      rows[i].setAttribute('aria-selected', 'false');
    }
  }
}

// ── Select current cursor row ────────────────────────────────────────────────
function _selectCurrent() {
  _stageEntry(_cursor);
}

// ── Stage an entry (never auto-send) ────────────────────────────────────────
function _stageEntry(idx) {
  if (idx < 0 || idx >= _results.length) return;
  var entry = _results[idx];
  var cmd = (entry.key || '') + ' ';
  _close();
  if (typeof _stage === 'function') {
    _stage(cmd);
  }
}

// ── Public API ───────────────────────────────────────────────────────────────
window.M3CommandPalette = {
  init:         init,
  // Exposed for tests:
  _score:       _score,
  _open:        function () { return _open; },
  _getCache:    function () { return _cache; },
  _setCache:    function (c) { _cache = c; },
  _openPalette: _open_palette,
  _close:       _close,
  _stageEntry:  _stageEntry,
  _renderResults: _renderResults,
  // Expose internal state accessors for test assertions
  _getCursor:   function () { return _cursor; },
  _getResults:  function () { return _results; },
  _getListEl:   function () { return _listEl; },
};

}());
