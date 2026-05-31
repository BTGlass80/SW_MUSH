/* ============================================================================
   m3_tier_registry.js — canonical getTierRenderer lookup (production cutover).

   Drop 4.15 · Tier 1 #4 · the production-cutover decision-drop named in
   the Drop 4.13 + 4.14 handoffs. This is the single source of truth that
   maps each of the seven tier IDs to the renderer that draws it, so both
   M3MapNavigator (Drop 4.8) and M3AssembledClient.MiniMap (Drop 4.12b)
   can resolve every tier without each caller re-implementing the lookup.

   The seven-tier ladder (matching M3MapNavigator.TIER_DEFS):

     '4c' GALAXY      → M3TierGalaxyBody.buildTierFourGalaxy        (Drop 4.13)
     '4a' SYSTEM      → M3TierSystemBody.buildTierFourASystemBody   (Drop 4.13)
     '3'  PLANET      → M3TierPlanetBody.buildTierThreeBody         (Drop 4.13)
     '2'  CITY        → M3TierCityBody.buildTierTwoBody             (Drop 4.14)
     '1a' DISTRICT    → M3CompositionEngine.Tier1aBody              (Drop 4.1e)
     '1b' WILDERNESS  → M3TierWildernessBody.buildTierOneBBody      (Drop 4.14)
     '0'  INTERIOR    → M3TierInteriorBody.buildTierZeroBody        (Drop 4.14)

   What this module ships:
     · M3TierRegistry.getTierRenderer(tierId, args) → DOM element
            The lookup. `args` is { p, width, height, time?, weather?,
            entities?, data? } — the same shape both consumers pass.
            Returns the rendered tier body (an <svg> for the body
            builders; a chrome'd <div> is NOT returned here — the
            navigator/mini supply their own chrome). On any miss or
            failure, returns a labeled placeholder so the caller never
            gets null and never crashes.
     · M3TierRegistry.TIER_RENDERERS
            The id→descriptor table (public for tests / Q1 audits).
     · M3TierRegistry.hasRenderer(tierId) → bool
            True when the module backing `tierId` is currently loaded.

   Design notes:
     · 1a (district) is special. It's the only tier whose renderer
       (M3CompositionEngine.Tier1aBody) consumes a live AreaGeometry-
       derived `data` object rather than a self-contained demo fixture.
       When the caller passes args.data (the production path), 1a renders
       from it. When args.data is absent (the showcase / navigator-
       preview path), 1a falls back to the same labeled placeholder the
       navigator used pre-cutover — there is no demo fixture for 1a in
       the tier-body modules (it lives in the composition engine's own
       MOS_EISLEY fixture, which the live path feeds via M3Adapter).
     · All resolution is defensive: a missing module → placeholder, a
       throwing builder → placeholder. The registry never throws.
     · This module owns NO runtime state. It's a pure lookup.

   B3 era-cleanness: this module has no fixture data of its own — every
   name it surfaces comes from the tier-body modules (each independently
   B3-scrubbed). The only era reference here is the doc subtitle in the
   placeholder, which is Clone-Wars-neutral.

   Loading order in client.html: AFTER all six tier-body modules and
   m3_composition_engine.js, and BEFORE m3_map_navigator.js /
   m3_assembled_client.js so those modules can pick it up as the default
   getTierRenderer.
   ============================================================================ */
(function(){
'use strict';

// ─── htmlEl helper (placeholder only — bodies come from tier modules) ─
function htmlEl(tag, props, children) {
  var el = document.createElement(tag);
  if (props) {
    for (var key in props) {
      if (!Object.prototype.hasOwnProperty.call(props, key)) continue;
      var val = props[key];
      if (val === undefined || val === null || val === false) continue;
      if (key === 'style') applyStyle(el, val);
      else el.setAttribute(key, String(val));
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

// ════════════════════════════════════════════════════════════════════
// TIER_RENDERERS — id → descriptor.
//
// Each descriptor:
//   ns      module namespace name on window
//   method  builder method name on that namespace
//   label   human label for the placeholder
//
// '1a' is intentionally NOT in this table — it routes through the
// composition engine and needs live `data`, handled separately in
// getTierRenderer below.
// ════════════════════════════════════════════════════════════════════
var TIER_RENDERERS = {
  '4c': { ns: 'M3TierGalaxyBody',     method: 'buildTierFourGalaxy',      label: 'GALAXY' },
  '4a': { ns: 'M3TierSystemBody',     method: 'buildTierFourASystemBody', label: 'SYSTEM' },
  '3':  { ns: 'M3TierPlanetBody',     method: 'buildTierThreeBody',       label: 'TATOOINE' },
  '2':  { ns: 'M3TierCityBody',       method: 'buildTierTwoBody',         label: 'MOS EISLEY' },
  '1b': { ns: 'M3TierWildernessBody', method: 'buildTierOneBBody',        label: 'DUNE SEA' },
  '0':  { ns: 'M3TierInteriorBody',   method: 'buildTierZeroBody',        label: "CHALMUN'S" },
};

// ════════════════════════════════════════════════════════════════════
// hasRenderer(tierId) → bool
// True when the backing module + method are loaded. For '1a', true when
// the composition engine's Tier1aBody is available.
// ════════════════════════════════════════════════════════════════════
function hasRenderer(tierId) {
  if (tierId === '1a') {
    return !!(typeof window !== 'undefined' &&
              window.M3CompositionEngine &&
              typeof window.M3CompositionEngine.Tier1aBody === 'function');
  }
  var desc = TIER_RENDERERS[tierId];
  if (!desc) return false;
  var ns = (typeof window !== 'undefined') ? window[desc.ns] : null;
  return !!(ns && typeof ns[desc.method] === 'function');
}

// ════════════════════════════════════════════════════════════════════
// getTierRenderer(tierId, args) → DOM element (never null, never throws)
//
// args: { p, width, height, time?, weather?, entities?, region?, regionKey?, data? }
//   · p        palette (required)
//   · width    body width  (px)
//   · height   body height (px)
//   · time     'day' | 'night' (forwarded to body builders that use it)
//   · weather  'clear' | 'sandstorm' | ... (forwarded where relevant)
//   · entities optional entity override, forwarded to the '0' interior
//              builder so live room occupancy can replace demo patrons
//   · region   optional wilderness region descriptor object, forwarded to
//              the '1b' wilderness builder (Drop 4.15a)
//   · regionKey optional wilderness region slug (e.g. 'coruscant_underworld');
//              resolved by the '1b' builder when no region object is given
//   · data     live AreaGeometry-derived data for the '1a' district
//              renderer (M3CompositionEngine.Tier1aBody). Ignored by
//              the demo-fixture tiers.
// ════════════════════════════════════════════════════════════════════
function getTierRenderer(tierId, args) {
  args = args || {};
  var p = args.p;

  // ── 1a district — composition-engine path (needs live data) ──────
  if (tierId === '1a') {
    var compEng = (typeof window !== 'undefined' && window.M3CompositionEngine) || {};
    if (typeof compEng.Tier1aBody === 'function' && args.data) {
      try {
        return compEng.Tier1aBody({
          data:    args.data,
          palette: p,
          tier:    1,
          time:    args.time    || 'day',
          weather: args.weather || 'clear',
          width:   args.width   || 700,
          height:  args.height  || 700,
        });
      } catch (e1a) {
        if (typeof console !== 'undefined' && console.warn) {
          console.warn('M3TierRegistry: Tier1aBody threw:', e1a);
        }
        // fall through to placeholder
      }
    }
    // No live data (showcase/preview) or engine missing → placeholder.
    return _placeholder(p, '1a', 'SPACEPORT', args);
  }

  // ── Demo-fixture tiers (4c / 4a / 3 / 2 / 1b / 0) ────────────────
  var desc = TIER_RENDERERS[tierId];
  if (!desc) {
    return _placeholder(p, tierId, tierId, args);
  }
  var ns = (typeof window !== 'undefined') ? window[desc.ns] : null;
  if (!ns || typeof ns[desc.method] !== 'function') {
    return _placeholder(p, tierId, desc.label, args);
  }
  try {
    // The '0' interior builder accepts an entities override; the '1b'
    // wilderness builder accepts region / regionKey (Drop 4.15a); the
    // rest ignore extra opts harmlessly. We pass a uniform opts object.
    return ns[desc.method](p, {
      width:     args.width,
      height:    args.height,
      time:      args.time,
      weather:   args.weather,
      entities:  args.entities,
      region:    args.region,
      regionKey: args.regionKey,
    });
  } catch (eBody) {
    if (typeof console !== 'undefined' && console.warn) {
      console.warn('M3TierRegistry: ' + desc.ns + '.' + desc.method +
                   ' threw:', eBody);
    }
    return _placeholder(p, tierId, desc.label, args);
  }
}

// ── Labeled placeholder — identical visual contract to the navigator's
// old _defaultTierRenderer so the cutover is visually seamless when a
// module happens to be missing. ──────────────────────────────────────
function _placeholder(p, tierId, label, args) {
  p = p || { inkDim: '#a09584', inkBright: '#fff4d6', amber: '#ffc857',
             inkFaint: '#6b6253' };
  var width  = args.width  || 700;
  var height = args.height || 700;
  return htmlEl('div', {
    'data-default-tier-body': tierId,
    'data-registry-placeholder': '1',
    style: {
      width: width, height: height,
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
      style: {
        marginTop: 16, padding: '6px 14px', fontSize: 9, letterSpacing: 1.5,
        color: p.amber, border: '1px solid ' + p.amber + '55',
      }
    }, [(tierId === '1a')
        ? 'DISTRICT \u00b7 AWAITING LIVE AREAGEOMETRY'
        : 'TIER MODULE NOT LOADED \u00b7 ' + tierId]),
  ]);
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3TierRegistry = {
  SCHEMA_VERSION: 1,

  getTierRenderer: getTierRenderer,
  hasRenderer:     hasRenderer,
  TIER_RENDERERS:  TIER_RENDERERS,

  _internal: { _placeholder: _placeholder, _htmlEl: htmlEl },
};

})();
