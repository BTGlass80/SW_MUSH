/* ============================================================================
   m3_map_navigator.js — Interactive zoom/pan/tier orchestrator.

   Drop 4.8 · Tier 1 #4 · ported from map_v3/map-navigator.jsx (394 JSX LOC)
   in SW_MUSH_UIUX_Bugfix_26May26.zip (May 27 2026).

   In the design canon: MapNavigator is the chrome that wraps the
   tier-body renderers (Tier1aBody and friends). It owns the active
   tier, zoom level, pan offset, fade-transition phase, and the
   holocron-open toggle. Mouse wheel zooms in/out (within tier); past
   a threshold, cross-fades to the next tier. Click-drag pans. Crumb
   ladder jumps. HOME resets.

   ── STATEFUL MODULE PATTERN ──────────────────────────────────────────
   This is the first SPA module that owns runtime state. The JSX uses
   React.useState for tier/zoom/pan/phase/dragging/holocronOpen; the
   vanilla version owns those in a private object inside .create().

   Public surface:
     · M3MapNavigator.init(deps)                  bind ambient helpers via DI
     · M3MapNavigator.create(p, hooks) → handle   instantiate; returns
            { element:   DOMElement     attach this to the parent,
              jumpTo:    function(id)   programmatic tier jump,
              getState:  function()     read-only state snapshot,
              destroy:   function()     remove wheel handler + dispose }
     · M3MapNavigator.TIER_DEFS                   the 7-tier ladder
     · M3MapNavigator.tierIndex(id) / tierAt(idx) helpers

   Hooks parameter:
     · getTierRenderer(tierId, args) → DOM element | null
                                       caller supplies tier-body
                                       renderers. tierId is one of
                                       '4c', '4a', '3', '2', '1a',
                                       '1b', '0'. args = { p, width,
                                       height, time, weather }.
                                       Production '1a' wires to
                                       M3CompositionEngine.Tier1aBody.
                                       Other tiers — caller decides
                                       (placeholder, defer, or render
                                       from a future m3_tier_X_body.js
                                       module when it lands).
     · onHolocronOpen()                holocron button clicked
     · onHolocronClose()               holocron modal closed
     · holocronModalBuilder(p, h)?     defaults to M3Holocron.buildHolocronModal
     · time / weather                  passed through to tier renderers
     · width / height                  outer dimensions (default 1280/920)
     · startTier                       starting tier id (default '1a')

   ── WHAT THIS MODULE DOES NOT DO ─────────────────────────────────────
     · Render the tier bodies themselves. Caller supplies them via
       hooks.getTierRenderer. The orchestrator is chrome only.
     · Wire a +map command. The eventual integration is a separate drop.
     · Persist tier/zoom between sessions.
     · Touch-screen pinch zoom. The JSX source uses pointer events
       for pan only; wheel for zoom. Same pattern preserved.

   Dependencies (loaded earlier in the SPA load order):
     · window.M3Holocron (Drop 4.7) — buildHolocronModal called when
       the holocron button is pressed. If absent, the holocron button
       still renders but clicks become no-ops (caller's
       onHolocronOpen fires, but the modal cannot render).

   Loading order in client.html: after m3_holocron.js.
   ============================================================================ */
(function(){
'use strict';

// ─── Module-private state ────────────────────────────────────────────
var _escapeHtml = null;

function init(deps) {
  deps = deps || {};
  _escapeHtml = deps.escapeHtml || _defaultEscapeHtml;
}

function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ─── htmlEl / svgEl: same shape as Drops 4.5/4.6/4.7 ─────────────────
function htmlEl(tag, props, children) {
  var el = document.createElement(tag);
  if (props) {
    for (var key in props) {
      if (!Object.prototype.hasOwnProperty.call(props, key)) continue;
      var val = props[key];
      if (val === undefined || val === null || val === false) continue;
      if (key === 'style') {
        applyStyle(el, val);
      } else if (key === 'className') {
        el.className = String(val);
      } else if (key === 'onClick' && typeof val === 'function') {
        el.addEventListener('click', val);
      } else if (key.indexOf('on') === 0 && typeof val === 'function') {
        el.addEventListener(key.slice(2).toLowerCase(), val);
      } else {
        el.setAttribute(key, String(val));
      }
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === null || child === undefined || child === false) continue;
      if (typeof child === 'string' || typeof child === 'number') {
        el.appendChild(document.createTextNode(String(child)));
      } else {
        el.appendChild(child);
      }
    }
  }
  return el;
}

function svgEl(tag, attrs, children) {
  var el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (attrs) {
    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      var val = attrs[key];
      if (val === undefined || val === null || val === false) continue;
      if (key === 'style') applyStyle(el, val);
      else el.setAttribute(_camelToKebabSvg(key), String(val));
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === null || child === undefined || child === false) continue;
      if (typeof child === 'string' || typeof child === 'number') {
        el.appendChild(document.createTextNode(String(child)));
      } else {
        el.appendChild(child);
      }
    }
  }
  return el;
}

function _camelToKebabSvg(k) {
  if (k === 'viewBox' || k === 'preserveAspectRatio' ||
      k === 'gradientTransform' || k === 'patternTransform' ||
      k === 'patternUnits' || k === 'patternContentUnits') return k;
  return k.replace(/[A-Z]/g, function(c) { return '-' + c.toLowerCase(); });
}

function applyStyle(el, style) {
  if (!style) return;
  for (var k in style) {
    if (!Object.prototype.hasOwnProperty.call(style, k)) continue;
    var v = style[k];
    if (v === null || v === undefined || v === false) continue;
    el.style[k] = (typeof v === 'number' && !_isUnitlessCss(k)) ? (v + 'px') : v;
  }
}

function _isUnitlessCss(k) {
  return (k === 'opacity' || k === 'zIndex' || k === 'fontWeight' ||
          k === 'flex' || k === 'flexGrow' || k === 'flexShrink' ||
          k === 'lineHeight' || k === 'order');
}

// ─── TIER_DEFS — the canonical 7-tier ladder ────────────────────────
// Going inward: 4c GALAXY → 4a SYSTEM → 3 PLANET → 2 CITY → 1a DISTRICT
// → 0 INTERIOR. 1b WILDERNESS branches off the main ladder. Era refs
// are Clone-Wars-era only — no Empire framing.
var TIER_DEFS = [
  { id: '4c', label: 'GALAXY',     sub: 'Clone Wars · 20 BBY',           crumb: 'GALAXY' },
  { id: '4a', label: 'SYSTEM',     sub: 'Tatooine system · binary',      crumb: 'SYSTEM' },
  { id: '3',  label: 'TATOOINE',   sub: 'Arkanis Sector · Outer Rim',    crumb: 'TATOOINE' },
  { id: '2',  label: 'MOS EISLEY', sub: 'Spaceport City',                crumb: 'MOS EISLEY' },
  { id: '1a', label: 'SPACEPORT',  sub: 'District · Docking Bay 94',     crumb: 'SPACEPORT' },
  { id: '0',  label: "CHALMUN'S",  sub: 'Cantina · Interior',            crumb: "CHALMUN'S" },
  { id: '1b', label: 'DUNE SEA',   sub: 'Wilderness region · 40×24 tiles', crumb: 'DUNE SEA', branch: true },
];

function tierIndex(id) {
  for (var i = 0; i < TIER_DEFS.length; i++) {
    if (TIER_DEFS[i].id === id) return i;
  }
  return -1;
}

function tierAt(idx) {
  return TIER_DEFS[Math.max(0, Math.min(TIER_DEFS.length - 1, idx))];
}

// ─── legendForTier — bottom-strip legend per active tier ────────────
function legendForTier(tier, p) {
  if (tier === '4c') return [
    { color: 'rgba(120,180,255,0.7)', shape: 'square', label: 'REPUBLIC' },
    { color: 'rgba(255,100,80,0.7)',  shape: 'square', label: 'CIS' },
    { color: 'rgba(140,220,120,0.7)', shape: 'square', label: 'HUTT SPACE' },
    { color: p.gold,                  shape: 'circle', glow: true, label: 'YOU · TATOOINE' },
  ];
  if (tier === '3') return [
    { color: p.cyan,  shape: 'circle', glow: true, label: 'YOU · MOS EISLEY' },
    { color: p.amber, shape: 'circle', label: 'CITY' },
    { color: p.gold,  shape: 'circle', label: 'LANDMARK' },
    { color: p.red,   shape: 'tri',    label: 'HOSTILE' },
  ];
  if (tier === '2') return [
    { color: p.cyan,  shape: 'circle', glow: true, label: 'YOU' },
    { color: p.amber, shape: 'square', label: 'DISTRICT' },
    { color: p.gold,  shape: 'circle', label: 'LANDMARK' },
  ];
  if (tier === '1a') return [
    { color: p.cyan,  shape: 'circle', glow: true, label: 'YOU' },
    { color: p.cyan,  shape: 'circle',             label: 'PC' },
    { color: p.amber, shape: 'circle',             label: 'FRIENDLY' },
    { color: p.red,   shape: 'tri',                label: 'HOSTILE' },
    { color: p.amber, shape: 'square',             label: 'VENDOR' },
    { color: p.green, shape: 'circle',             label: 'OBJECTIVE' },
    { color: p.gold,  shape: 'circle', glow: true, label: 'ANOMALY T3' },
  ];
  if (tier === '1b') return [
    { color: p.cyan,  shape: 'circle', glow: true, label: 'YOU · SIGHT R6' },
    { color: p.cyan,  shape: 'circle', label: 'PC' },
    { color: p.red,   shape: 'tri',    label: 'CONTEST' },
    { color: p.amber, shape: 'circle', label: 'ANOMALY T1' },
    { color: p.red,   shape: 'circle', label: 'ANOMALY T2' },
    { color: p.gold,  shape: 'circle', glow: true, label: 'WORLD BOSS' },
  ];
  if (tier === '0') return [
    { color: p.cyan,  shape: 'circle', glow: true, label: 'YOU' },
    { color: p.amber, shape: 'circle', label: 'BARTENDER' },
    { color: p.red,   shape: 'tri',    label: 'HOSTILE' },
    { color: p.ink,   shape: 'square', label: 'TABLE/BOOTH' },
  ];
  return [];
}

// ─── ZoomBtn helper ─────────────────────────────────────────────────
function buildZoomBtn(p, onClick, label, hint) {
  var btn = htmlEl('button', {
    title: hint,
    style: {
      width: 32, height: 32, padding: 0,
      background: p.skyDeep + 'dd',
      border: '1px solid ' + p.inkDim,
      color: p.inkBright,
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 16, fontWeight: 600, cursor: 'pointer',
      transition: 'background 120ms',
    },
    onClick: onClick
  }, [label]);
  btn.addEventListener('mouseenter', function() {
    btn.style.background = p.amber + '33';
  });
  btn.addEventListener('mouseleave', function() {
    btn.style.background = p.skyDeep + 'dd';
  });
  return btn;
}

// ════════════════════════════════════════════════════════════════════
// create — instantiate a MapNavigator
// ════════════════════════════════════════════════════════════════════
function create(p, hooks) {
  hooks = hooks || {};

  // ── Configuration knobs ─────────────────────────────────────────
  var width  = hooks.width  || 1280;
  var height = hooks.height || 920;
  var TOP    = 60;
  var BOTTOM = 28;
  var bodyW  = width;
  var bodyH  = height - TOP - BOTTOM;
  // Drop 4.15 cutover: when the caller doesn't supply getTierRenderer,
  // prefer the canonical M3TierRegistry lookup (which resolves all
  // seven tiers to their real body builders) over the bare per-tier
  // placeholder. The placeholder remains the final fallback so the
  // navigator is still usable if the registry module isn't loaded.
  var getTierRenderer =
        hooks.getTierRenderer ||
        (window.M3TierRegistry && window.M3TierRegistry.getTierRenderer) ||
        _defaultTierRenderer;
  var holocronModalBuilder = hooks.holocronModalBuilder
                          || (window.M3Holocron && window.M3Holocron.buildHolocronModal)
                          || null;
  // Fade-transition timings. JSX source: 180ms fade-out, 160ms fade-in.
  // Exposed as a hook so tests can pass 0 for synchronous behavior.
  var fadeOutMs = (hooks.transitionDelays && hooks.transitionDelays.fadeOutMs != null)
                  ? hooks.transitionDelays.fadeOutMs : 180;
  var fadeInMs  = (hooks.transitionDelays && hooks.transitionDelays.fadeInMs  != null)
                  ? hooks.transitionDelays.fadeInMs  : 160;

  // ── Internal state ──────────────────────────────────────────────
  var state = {
    tier:          hooks.startTier || '1a',
    zoom:          1,
    pan:           { x: 0, y: 0 },
    phase:         'idle',         // 'idle' | 'fade-out' | 'fade-in'
    dragging:      null,           // null or { x, y, startPan }
    holocronOpen:  false,
  };

  // ── Owned DOM references (assigned during initial render) ───────
  var outer       = null;
  var crumbRow    = null;
  var stage       = null;
  var zoomWrap    = null;
  var zoomLabel   = null;
  var tierLabel   = null;
  var tierLabelSub = null;
  var legendRow   = null;
  var holocronContainer = null;
  var wheelHandler = null;

  // ── Tier transition orchestration ───────────────────────────────
  function transitionTo(newTierId, fromDirection /* 'in' | 'out' | 'jump' */) {
    if (newTierId === state.tier) return;
    if (state.phase !== 'idle') return;
    state.phase = 'fade-out';
    _applyFadeStyle();
    function doSwap() {
      state.tier = newTierId;
      state.zoom = (fromDirection === 'in')  ? 0.85
                 : (fromDirection === 'out') ? 1.15
                 :                              1;
      state.pan = { x: 0, y: 0 };
      state.phase = 'fade-in';
      _rerenderBody();
      _applyFadeStyle();
      _refreshChrome();
      function doSettle() {
        state.phase = 'idle';
        _applyFadeStyle();
      }
      if (fadeInMs <= 0) doSettle();
      else setTimeout(doSettle, fadeInMs);
    }
    if (fadeOutMs <= 0) doSwap();
    else setTimeout(doSwap, fadeOutMs);
  }

  function zoomIn() {
    var idx = tierIndex(state.tier);
    if (idx < TIER_DEFS.length - 1) {
      transitionTo(TIER_DEFS[idx + 1].id, 'in');
    }
  }

  function zoomOut() {
    var idx = tierIndex(state.tier);
    if (idx > 0) {
      transitionTo(TIER_DEFS[idx - 1].id, 'out');
    }
  }

  function jumpTo(id) {
    transitionTo(id, 'jump');
  }

  function resetZoom() {
    state.zoom = 1;
    state.pan = { x: 0, y: 0 };
    _applyZoomTransform();
    _refreshZoomLabel();
  }

  // ── Wheel handler — smooth zoom; crosses tier threshold ────────
  function onWheel(e) {
    if (state.phase !== 'idle') return;
    e.preventDefault();
    e.stopPropagation();
    var delta = -e.deltaY * 0.0018;
    var newZoom = state.zoom * (1 + delta * 2.5);
    if (newZoom > 2.4) {
      var idxIn = tierIndex(state.tier);
      if (idxIn < TIER_DEFS.length - 1) {
        transitionTo(TIER_DEFS[idxIn + 1].id, 'in');
        return;
      }
    } else if (newZoom < 0.42) {
      var idxOut = tierIndex(state.tier);
      if (idxOut > 0) {
        transitionTo(TIER_DEFS[idxOut - 1].id, 'out');
        return;
      }
    }
    state.zoom = Math.max(0.42, Math.min(2.4, newZoom));
    _applyZoomTransform();
    _refreshZoomLabel();
  }

  // ── Pan handlers ────────────────────────────────────────────────
  function onPointerDown(e) {
    if (e.button !== 0) return;
    state.dragging = { x: e.clientX, y: e.clientY, startPan: state.pan };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) {}
    if (stage) stage.style.cursor = 'grabbing';
  }
  function onPointerMove(e) {
    if (!state.dragging) return;
    state.pan = {
      x: state.dragging.startPan.x + (e.clientX - state.dragging.x) / state.zoom,
      y: state.dragging.startPan.y + (e.clientY - state.dragging.y) / state.zoom,
    };
    _applyZoomTransform();
  }
  function onPointerUp(e) {
    state.dragging = null;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch (err) {}
    if (stage) stage.style.cursor = 'grab';
  }

  // ── Holocron toggle ─────────────────────────────────────────────
  function openHolocron() {
    if (state.holocronOpen) return;
    state.holocronOpen = true;
    if (typeof hooks.onHolocronOpen === 'function') hooks.onHolocronOpen();
    if (holocronModalBuilder) {
      var modal = holocronModalBuilder(p, {
        width:  Math.min(1040, bodyW - 60),
        height: Math.min(700,  bodyH - 60),
        draggable: true,
        onClose: closeHolocron,
      });
      holocronContainer.appendChild(modal);
    }
    _refreshHolocronBtn();
  }
  function closeHolocron() {
    if (!state.holocronOpen) return;
    state.holocronOpen = false;
    while (holocronContainer.firstChild) {
      holocronContainer.removeChild(holocronContainer.firstChild);
    }
    if (typeof hooks.onHolocronClose === 'function') hooks.onHolocronClose();
    _refreshHolocronBtn();
  }

  // ── Render helpers ──────────────────────────────────────────────
  function _applyFadeStyle() {
    if (!zoomWrap) return;
    zoomWrap.style.opacity = (state.phase === 'fade-out') ? '0' : '1';
    zoomWrap.style.transition =
        (state.phase === 'fade-out') ? 'opacity 180ms ease-out'
      : (state.phase === 'fade-in')  ? 'opacity 160ms ease-in'
      :                                'none';
  }

  function _applyZoomTransform() {
    if (!zoomWrap) return;
    zoomWrap.style.transform =
        'translate(' + state.pan.x + 'px, ' + state.pan.y + 'px) scale(' + state.zoom + ')';
  }

  function _refreshZoomLabel() {
    if (!zoomLabel) return;
    zoomLabel.textContent = (state.zoom * 100).toFixed(0) + '%';
  }

  function _refreshTierLabel() {
    if (!tierLabel) return;
    var t = tierAt(tierIndex(state.tier));
    tierLabel.textContent = t.label;
    if (tierLabelSub) tierLabelSub.textContent = t.sub;
  }

  function _refreshCrumbs() {
    if (!crumbRow) return;
    while (crumbRow.firstChild) crumbRow.removeChild(crumbRow.firstChild);
    var newCrumbs = _buildCrumbs();
    for (var i = 0; i < newCrumbs.length; i++) {
      crumbRow.appendChild(newCrumbs[i]);
    }
  }

  function _refreshLegend() {
    if (!legendRow) return;
    while (legendRow.firstChild) legendRow.removeChild(legendRow.firstChild);
    var newLegend = _buildLegendChildren();
    for (var i = 0; i < newLegend.length; i++) {
      legendRow.appendChild(newLegend[i]);
    }
  }

  function _refreshHolocronBtn() {
    // Defer to caller re-render; the button reference isn't kept (cheap).
  }

  function _refreshChrome() {
    _refreshTierLabel();
    _refreshCrumbs();
    _refreshLegend();
    _applyZoomTransform();
    _refreshZoomLabel();
  }

  function _rerenderBody() {
    if (!zoomWrap) return;
    while (zoomWrap.firstChild) zoomWrap.removeChild(zoomWrap.firstChild);
    var bodyEl = getTierRenderer(state.tier, {
      p: p, width: bodyW, height: bodyH,
      time: hooks.time, weather: hooks.weather,
    });
    if (bodyEl) zoomWrap.appendChild(bodyEl);
  }

  // ── Crumb-row construction ──────────────────────────────────────
  function _buildCrumbs() {
    var out = [];
    for (var i = 0; i < TIER_DEFS.length; i++) {
      var t = TIER_DEFS[i];
      var active = (t.id === state.tier);
      var passed = (!t.branch) && (tierIndex(state.tier) > i);

      if (t.branch) {
        out.push(htmlEl('span', {
          style: { color: p.inkDim, fontSize: 9, marginLeft: 4, letterSpacing: 1.5 }
        }, ['OR ⤷']));
      }

      out.push((function(tierId) {
        return htmlEl('div', {
          'data-crumb-id': tierId,
          onClick: function() { jumpTo(tierId); },
          style: {
            padding: '4px 10px', cursor: 'pointer',
            background: active ? p.amber : passed ? (p.amber + '22') : 'transparent',
            border: '1px solid ' + (active ? p.amber : passed ? (p.amber + '55') : p.inkFaint),
            color: active ? p.skyDeep : passed ? p.amber : p.inkDim,
            letterSpacing: 2, fontWeight: active ? 700 : 500,
            borderRadius: 2,
            boxShadow: active ? ('0 0 8px ' + p.amber + '66') : 'none',
            fontSize: active ? 10 : 9,
            transition: 'all 160ms',
          }
        }, ['T' + tierId + ' · ' + t.crumb]);
      })(t.id));

      // Separator chevron — only between non-branch consecutive crumbs.
      if (i < TIER_DEFS.length - 1 && !TIER_DEFS[i + 1].branch) {
        out.push(htmlEl('span', {
          style: { color: p.inkFaint, fontSize: 10 }
        }, ['▸']));
      }
    }
    return out;
  }

  // ── Legend-row construction ─────────────────────────────────────
  function _buildLegendChildren() {
    var legend = legendForTier(state.tier, p);
    var out = legend.map(function(l) {
      var dotStyle = {
        width: 8, height: 8, background: l.color,
        borderRadius: (l.shape === 'square') ? 0 : '50%',
        display: 'inline-block',
        boxShadow: l.glow ? ('0 0 4px ' + l.color) : 'none',
      };
      if (l.shape === 'tri') {
        dotStyle.clipPath = 'polygon(50% 0, 100% 100%, 0 100%)';
      }
      return htmlEl('div', {
        style: { display: 'flex', alignItems: 'center', gap: 5 }
      }, [
        htmlEl('span', { style: dotStyle }),
        htmlEl('span', { style: { color: p.ink } }, [l.label]),
      ]);
    });
    out.push(htmlEl('span', {
      style: { marginLeft: 'auto', color: p.inkDim }
    }, ['◯ HOLOCARTA · v3 · §7.13 RENDERER']));
    return out;
  }

  // ── TOP BAR ─────────────────────────────────────────────────────
  function _buildTopBar() {
    var statusLine = htmlEl('div', {
      style: { display: 'flex', alignItems: 'center', gap: 14, fontSize: 10, letterSpacing: 2.5 }
    }, [
      htmlEl('span', { style: { color: p.cyan } }, ['◉ HOLOCARTA']),
      htmlEl('span', { style: { color: p.inkDim } }, ['·']),
      htmlEl('span', { style: { color: p.amber } }, ['● LIVE']),
      htmlEl('span', {
        style: { marginLeft: 'auto', color: p.inkDim, fontSize: 9 }
      }, ['SCROLL TO ZOOM · DRAG TO PAN · CLICK A CRUMB TO JUMP']),
    ]);

    crumbRow = htmlEl('div', {
      'data-crumb-row': '1',
      style: {
        display: 'flex', alignItems: 'center', marginTop: 8,
        gap: 4, fontSize: 11, flexWrap: 'wrap',
      }
    }, _buildCrumbs());

    return htmlEl('div', {
      style: {
        position: 'absolute', top: 0, left: 0, right: 0, height: TOP,
        borderBottom: '1px solid ' + p.inkDim,
        background: 'linear-gradient(180deg, ' + p.sky + ', ' + p.skyDeep + ')',
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
        padding: '0 16px', zIndex: 50,
      }
    }, [statusLine, crumbRow]);
  }

  // ── STAGE — zoomable pannable body ──────────────────────────────
  function _buildStage() {
    zoomWrap = htmlEl('div', {
      'data-zoom-wrap': '1',
      style: {
        width: bodyW, height: bodyH,
        transformOrigin: '50% 50%',
        transform: 'translate(0px, 0px) scale(1)',
        opacity: 1,
        transition: 'none',
        pointerEvents: 'none',
      }
    }, []);
    // Insert initial body
    var initialBody = getTierRenderer(state.tier, {
      p: p, width: bodyW, height: bodyH,
      time: hooks.time, weather: hooks.weather,
    });
    if (initialBody) zoomWrap.appendChild(initialBody);

    stage = htmlEl('div', {
      'data-stage': '1',
      onPointerDown: onPointerDown,
      onPointerMove: onPointerMove,
      onPointerUp:   onPointerUp,
      onPointerCancel: onPointerUp,
      style: {
        position: 'absolute', top: TOP, left: 0, right: 0, bottom: BOTTOM,
        overflow: 'hidden',
        cursor: 'grab',
        touchAction: 'none',
        background: '#000',
      }
    }, [zoomWrap]);

    // Native wheel handler — passive: false so we can preventDefault.
    wheelHandler = function(ev) { onWheel(ev); };
    stage.addEventListener('wheel', wheelHandler, { passive: false });

    // Zoom HUD (bottom-left)
    var zoomValSpan = htmlEl('span', {
      style: { color: p.ink }
    }, ['100%']);
    zoomLabel = zoomValSpan;
    var zoomHUD = htmlEl('div', {
      style: {
        position: 'absolute', bottom: 14, left: 14, zIndex: 30,
        fontSize: 9, letterSpacing: 1.5, color: p.inkDim,
        background: p.skyDeep + 'cc', padding: '4px 8px',
        border: '1px solid ' + p.inkFaint,
      }
    }, [
      'ZOOM ', zoomValSpan, ' · TIER ',
      htmlEl('span', { style: { color: p.amber } }, [state.tier.toUpperCase()]),
    ]);
    stage.appendChild(zoomHUD);

    // Zoom controls (bottom-right)
    var zoomControls = htmlEl('div', {
      style: {
        position: 'absolute', right: 14, bottom: 14, zIndex: 30,
        display: 'flex', flexDirection: 'column', gap: 4,
      }
    }, [
      buildZoomBtn(p, zoomIn,  '+', 'Zoom in (deeper tier)'),
      buildZoomBtn(p, resetZoom, '⟲', 'Reset'),
      buildZoomBtn(p, zoomOut, '−', 'Zoom out (wider tier)'),
    ]);
    stage.appendChild(zoomControls);

    // Holocron toggle (top-left)
    var holocronBtn = htmlEl('button', {
      onClick: openHolocron,
      style: {
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 12px',
        background: p.skyDeep + 'cc',
        border: '1px solid ' + p.amber,
        color: p.amber,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 10, letterSpacing: 2, cursor: 'pointer', fontWeight: 600,
        boxShadow: '0 0 8px ' + p.amber + '44',
      }
    }, [
      svgEl('svg', { width: 14, height: 14, viewBox: '0 0 30 30' }, [
        svgEl('polygon', {
          points: '15,3 26,9 26,21 15,27 4,21 4,9',
          fill: 'none', stroke: 'currentColor', strokeWidth: 1.5
        }),
        svgEl('polygon', {
          points: '15,9 21,12 21,18 15,21 9,18 9,12',
          fill: 'currentColor', opacity: 0.4
        }),
      ]),
      'HOLOCRON',
    ]);
    holocronBtn.setAttribute('data-holocron-btn', '1');
    var holocronContainerEl = htmlEl('div', {
      'data-holocron-container': '1',
      style: { position: 'absolute', top: 14, left: 14, zIndex: 30 }
    }, [holocronBtn]);
    holocronContainer = holocronContainerEl;
    stage.appendChild(holocronContainer);

    // Tier label overlay (top-right)
    var initialTierAt = tierAt(tierIndex(state.tier));
    tierLabel = htmlEl('div', {
      style: { fontSize: 13, letterSpacing: 3, color: p.inkBright, fontWeight: 600 }
    }, [initialTierAt.label]);
    tierLabelSub = htmlEl('div', {
      style: { fontSize: 8, letterSpacing: 1, color: p.inkDim }
    }, [initialTierAt.sub]);
    var tierOverlay = htmlEl('div', {
      'data-tier-overlay': '1',
      style: {
        position: 'absolute', top: 14, right: 14, zIndex: 30,
        textAlign: 'right',
        background: p.skyDeep + 'cc', padding: '6px 10px',
        border: '1px solid ' + p.inkFaint,
      }
    }, [
      htmlEl('div', {
        style: { fontSize: 9, letterSpacing: 2, color: p.inkDim }
      }, ['VIEWING']),
      tierLabel,
      tierLabelSub,
    ]);
    stage.appendChild(tierOverlay);

    return stage;
  }

  // ── BOTTOM LEGEND ───────────────────────────────────────────────
  function _buildLegendBar() {
    legendRow = htmlEl('div', {
      'data-legend-row': '1',
      style: {
        position: 'absolute', bottom: 0, left: 0, right: 0, height: BOTTOM,
        borderTop: '1px solid ' + p.inkDim,
        background: 'linear-gradient(180deg, ' + p.skyDeep + ', ' + p.sky + ')',
        display: 'flex', alignItems: 'center',
        padding: '0 16px', gap: 18, fontSize: 9, letterSpacing: 1.5,
        zIndex: 50,
      }
    }, _buildLegendChildren());
    return legendRow;
  }

  // ── Initial render ──────────────────────────────────────────────
  outer = htmlEl('div', {
    'data-map-navigator': '1',
    style: {
      width: width, height: height, position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + p.inkDim,
      boxShadow: 'inset 0 0 40px ' + p.skyDeep + ', 0 0 0 1px #000, 0 20px 50px rgba(0,0,0,0.7)',
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
    }
  }, []);
  outer.appendChild(_buildTopBar());
  outer.appendChild(_buildStage());
  outer.appendChild(_buildLegendBar());

  // ── Public handle ───────────────────────────────────────────────
  return {
    element: outer,
    jumpTo:  jumpTo,
    closeHolocron: closeHolocron,
    getState: function() {
      // Return a defensive copy.
      return {
        tier:         state.tier,
        zoom:         state.zoom,
        pan:          { x: state.pan.x, y: state.pan.y },
        phase:        state.phase,
        holocronOpen: state.holocronOpen,
      };
    },
    destroy: function() {
      if (stage && wheelHandler) {
        stage.removeEventListener('wheel', wheelHandler);
      }
      // Caller is responsible for removing `outer` from the DOM.
    },
  };
}

// ─── Default tier renderer — placeholder if caller doesn't supply ───
// Renders a simple per-tier placeholder div so the navigator is usable
// without external wiring. In production, caller supplies the real
// renderer via hooks.getTierRenderer; for tier '1a' that's typically
// M3CompositionEngine.Tier1aBody.
function _defaultTierRenderer(tierId, args) {
  var p = args.p;
  var t = tierAt(tierIndex(tierId));
  var label = t ? t.label : tierId;
  var sub = t ? t.sub : '';
  return htmlEl('div', {
    'data-default-tier-body': tierId,
    style: {
      width: args.width, height: args.height,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexDirection: 'column', gap: 12,
      color: p.inkDim,
      background: 'radial-gradient(circle at 50% 50%, ' + p.amber + '11, transparent 60%)',
    }
  }, [
    htmlEl('div', {
      style: {
        fontSize: 48, letterSpacing: 6, color: p.inkBright, fontWeight: 700,
        textShadow: '0 0 10px ' + p.amber + '55',
      }
    }, [label]),
    htmlEl('div', {
      style: { fontSize: 12, letterSpacing: 2, color: p.inkDim }
    }, [sub]),
    htmlEl('div', {
      style: {
        marginTop: 16, padding: '6px 14px', fontSize: 9, letterSpacing: 1.5,
        color: p.amber, border: '1px solid ' + p.amber + '55',
      }
    }, ['TIER RENDERER NOT WIRED · caller supplies via hooks.getTierRenderer']),
  ]);
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3MapNavigator = {
  SCHEMA_VERSION: 1,

  init:       init,
  create:     create,

  TIER_DEFS:  TIER_DEFS,
  tierIndex:  tierIndex,
  tierAt:     tierAt,

  legendForTier:    legendForTier,
  buildZoomBtn:     buildZoomBtn,
  _defaultTierRenderer: _defaultTierRenderer,

  _internal: {
    _htmlEl: htmlEl,
    _svgEl:  svgEl,
  },
};

})();
