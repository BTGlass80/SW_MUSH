/* ============================================================================
   m3_asset_catalog.js — designer-facing inventory of the SPA asset library.

   Drop 4.1b · Tier 1 #4 · ported from map_v3/asset-catalog.jsx (May 26 2026).
   Drop 4.1c · two edits:
     - buildLandmarksColumn now resolves builders via a chain:
       short-slug dict → long-ident dict → namespace's long-ident export.
       (WILDERNESS_LANDMARKS is keyed by short slug per the composition-
        engine contract; the namespace also exposes WLM_* long-idents
        for catalog lookup.)
     - landmark builder call uses object form `builder({ p, lod })`,
       matching the props-object convention used by the marker builders
       and the React JSX source. Old positional form `(p, 'detailed')`
       was a port artifact.

   Visible inventory of every asset the composition engine can compose,
   rendered using the SAME builders the composition engine consumes (so
   what the designer authors IS what the runtime composes — no drift).

   This module is a designer/debug surface, not used by the production
   composition path. It graceful-degrades when later-drop dependencies
   (LANDMARKS, TerrainDefs) aren't loaded yet: each missing dependency
   shows a placeholder "loading…" tile rather than throwing. After 4.1c
   the wilderness and markers columns light up automatically. Terrain
   tiles stay '(loading)' until 4.1e (composition-engine wraps overlays).

   Activated by Drop 4.1c (MARKERS + WILDERNESS_LANDMARKS) → 4.1d (urban
   LANDMARKS) → 4.1e (TerrainDefs via composition-engine).

   Public API: window.M3AssetCatalog.mount(rootEl, opts) — clears rootEl
   and renders the full catalog into it. Returns the catalog's outer
   container element.
   ============================================================================ */
(function(){
'use strict';

// Small DOM helper — mirrors svgEl shape but for HTML elements.
// (Pulled out as a local helper since this catalog is HTML-heavy, not SVG;
// we don't add it to M3Tokens because subsequent modules are SVG-only.)
function el(tag, attrs, children) {
  var node = document.createElement(tag);
  if (attrs) {
    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      var val = attrs[key];
      if (val === null || val === undefined || val === false) continue;
      if (key === 'style' && typeof val === 'object') {
        for (var sk in val) {
          if (Object.prototype.hasOwnProperty.call(val, sk)) {
            node.style[sk] = val[sk];
          }
        }
      } else if (key === 'title') {
        node.setAttribute('title', String(val));
      } else if (key === 'class') {
        node.className = String(val);
      } else {
        node.setAttribute(key, String(val));
      }
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === null || child === undefined) continue;
      if (typeof child === 'string') {
        node.appendChild(document.createTextNode(child));
      } else {
        node.appendChild(child);
      }
    }
  }
  return node;
}

var svgEl = window.M3Tokens.svgEl;

// ── Counts row (header right-hand) ──────────────────────────────────
function countRow(label, n, amberColor) {
  return el('div', {}, [
    String(n) + ' ',
    el('span', { style: { color: amberColor } }, [label])
  ]);
}

// ── Header ──────────────────────────────────────────────────────────
function buildHeader(p) {
  // Dependency-aware counts (graceful degradation if a module hasn't loaded).
  var landmarkCount =
    (window.M3AssetsLandmarks && Object.keys(window.M3AssetsLandmarks.LANDMARKS || {}).length || 0) +
    (window.M3AssetsWilderness && Object.keys(window.M3AssetsWilderness.WILDERNESS_LANDMARKS || {}).length || 0);
  var styleCount =
    (window.M3AssetsStyles && Object.keys(window.M3AssetsStyles.STYLE_PRIMITIVES || {}).length || 0);
  var markerCount =
    (window.M3AssetsMarkers && Object.keys(window.M3AssetsMarkers.MARKERS || {}).length || 0);
  var icons = window.M3AssetsIcons || {};
  var iconCount =
    Object.keys(icons.SERVICE_ICONS || {}).length +
    Object.keys(icons.STATUS_ICONS  || {}).length +
    Object.keys(icons.ATTR_ICONS    || {}).length +
    Object.keys(icons.FACTION_ICONS || {}).length;

  var titleSide = el('div', {}, [
    el('div', { style: {
      fontSize: '11px', letterSpacing: '4px', color: p.inkDim, marginBottom: '4px'
    }}, ['ASSET LIBRARY · §7.13.2 DELIVERABLE']),
    el('div', { style: {
      fontSize: '22px', letterSpacing: '2px', color: p.inkBright, fontWeight: '600'
    }}, ['HOLOCARTA · COMPOSITION ASSETS']),
    el('div', { style: {
      fontSize: '10px', letterSpacing: '1.5px', color: p.inkDim, marginTop: '4px'
    }}, ['HAND-AUTHORED SVG · CONSUMED BY THE RUNTIME COMPOSITION ENGINE'])
  ]);

  var countsSide = el('div', { style: {
    textAlign: 'right', fontSize: '10px', letterSpacing: '2px',
    color: p.inkDim, lineHeight: '1.8'
  }}, [
    countRow('LANDMARKS', landmarkCount, p.amber),
    countRow('STYLES',    styleCount,    p.amber),
    countRow('MARKERS',   markerCount,   p.amber),
    countRow('ICONS',     iconCount,     p.amber)
  ]);

  return el('div', { style: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    marginBottom: '20px', paddingBottom: '12px',
    borderBottom: '1px solid ' + p.inkDim
  }}, [titleSide, countsSide]);
}

// ── Sub-label ───────────────────────────────────────────────────────
function subLabel(p, text) {
  return el('div', { style: {
    fontSize: '8px', letterSpacing: '2px', color: p.inkDim, fontWeight: '600'
  }}, [text]);
}

// ── Generic catalog card (one tile per asset) ───────────────────────
// renderFn returns an SVG element (or null for "missing dep" stub).
function catalogCard(p, opts) {
  var svg = svgEl('svg', {
    width: '100%', height: '100%',
    viewBox: opts.marker ? '-15 -15 30 30' : '0 0 100 100'
  });

  // SVG tile background for terrain-aware cards
  if (opts.svgTile) {
    svg.appendChild(svgEl('rect', {
      x: 0, y: 0, width: 100, height: 100, fill: 'url(#asset-tile)'
    }));
  }

  var rendered = opts.render ? opts.render() : null;
  if (rendered) {
    svg.appendChild(rendered);
  } else {
    // Graceful degradation when dependency module isn't loaded
    svg.appendChild(svgEl('text', {
      x: opts.marker ? 0 : 50, y: opts.marker ? 0 : 50,
      textAnchor: 'middle', fontSize: 8,
      fill: p.inkDim, opacity: 0.5
    }, ['loading…']));
  }

  return el('div', { style: {
    aspectRatio: '1 / 1', position: 'relative',
    background: opts.svgTile ? p.ground : p.skyDeep,
    border: '1px solid ' + p.inkFaint, overflow: 'hidden'
  }}, [
    svg,
    el('div', { style: {
      position: 'absolute', bottom: '0', left: '0', right: '0',
      fontSize: '7px', letterSpacing: '1px', color: p.inkBright,
      background: 'rgba(0,0,0,0.65)', padding: '1px 4px', textAlign: 'center'
    }}, [opts.label])
  ]);
}

function catalogGrid(cols, items) {
  return el('div', { style: {
    display: 'grid',
    gridTemplateColumns: 'repeat(' + cols + ', 1fr)', gap: '6px'
  }}, items);
}

function catalogColumn(p, opts, body) {
  return el('div', { style: {
    background: p.skyDeep + 'cc',
    border: '1px solid ' + p.inkFaint,
    padding: '10px 12px', display: 'flex', flexDirection: 'column',
    overflow: 'hidden'
  }}, [
    el('div', { style: { marginBottom: '10px' }}, [
      el('div', { style: {
        fontSize: '10px', letterSpacing: '3px', color: p.amber, fontWeight: '600'
      }}, [opts.title]),
      opts.sub ? el('div', { style: {
        fontSize: '8px', letterSpacing: '1.5px', color: p.inkDim, marginTop: '2px'
      }}, [opts.sub]) : null
    ]),
    el('div', { style: { flex: '1', overflow: 'auto' }}, [body]),
    opts.footer ? el('div', { style: {
      marginTop: '8px', paddingTop: '6px',
      borderTop: '1px dashed ' + p.inkFaint,
      fontSize: '8px', letterSpacing: '0.5px',
      color: p.inkDim, lineHeight: '1.4'
    }}, [opts.footer]) : null
  ]);
}

// ── Named landmarks column ──────────────────────────────────────────
function buildLandmarksColumn(p) {
  var lm = (window.M3AssetsLandmarks && window.M3AssetsLandmarks.LANDMARKS) || {};
  var wlm = (window.M3AssetsWilderness && window.M3AssetsWilderness.WILDERNESS_LANDMARKS) || {};

  // The original v3 prototype hard-codes the display order for visual
  // priority; we preserve that here. Each entry tries the live builder;
  // missing entries fall back to the loading stub via catalogCard's
  // graceful render path.
  var entries = [
    ['LM_DockingBay94',   'Docking Bay 94'],
    ['LM_ChalmunsCantina',"Chalmun's"],
    ['LM_LuckyDespot',    'Lucky Despot'],
    ['LM_ControlTower',   'Control Tower'],
    ['LM_CustomsOffice',  'Customs'],
    ['LM_MosEisleyInn',   'Mos Eisley Inn'],
    ['LM_SpaceportHotel', 'Spaceport Hotel'],
    ['LM_MomawNadon',     'House of M.N.'],
    ['LM_TransportDepot', 'Transport'],
    ['WLM_TuskenCamp',    'Tusken Camp'],
    ['WLM_Sandcrawler',   'Sandcrawler'],
    ['WLM_AbandonedMine', 'Abandoned Mine'],
    ['WLM_KraytSkeleton', 'Krayt Skeleton'],
    ['WLM_JabbaPalace',   "Jabba's Palace"],
    ['WLM_MoistureFarm',  'Moisture Farm']
  ];

  var cards = entries.map(function(entry) {
    var id = entry[0], label = entry[1];
    // Drop 4.1c: the WILDERNESS_LANDMARKS / LANDMARKS dicts are keyed
    // by short slug (composition-engine contract), but the entries
    // array above keys by long ident (JSX function name). Fall back
    // to the namespace's long-ident exports so either form resolves.
    var builder =
      lm[id] || wlm[id] ||
      (window.M3AssetsLandmarks   && window.M3AssetsLandmarks[id]) ||
      (window.M3AssetsWilderness  && window.M3AssetsWilderness[id]);
    // Drop 4.1c: landmark builders take an options object `{ p, lod }`,
    // matching the props-object convention used by the marker builders
    // (see buildMarkersColumn below) and the React JSX source.
    return catalogCard(p, {
      label: label,
      svgTile: true,
      render: builder ? function() { return builder({ p: p, lod: 'detailed' }); } : null
    });
  });

  return catalogColumn(p, {
    title:  'NAMED LANDMARKS',
    sub:    'MOS EISLEY + WILDERNESS · DETAILED LOD',
    footer: '§7.13.2.A · Each authored at 3 LOD variants'
  }, catalogGrid(3, cards));
}

// ── Style primitives column ─────────────────────────────────────────
function buildStylePrimsColumn(p) {
  var sp = (window.M3AssetsStyles && window.M3AssetsStyles.STYLE_PRIMITIVES) || {};
  var cards = Object.keys(sp).map(function(id) {
    return catalogCard(p, {
      label: id.toUpperCase(),
      svgTile: true,
      render: function() { return sp[id](p); }
    });
  });

  return catalogColumn(p, {
    title:  'STYLE PRIMITIVES',
    sub:    'FALLBACK FOOTPRINTS',
    footer: '§7.13.2.B · Used when room.slug is unbound'
  }, catalogGrid(2, cards));
}

// ── Markers column ──────────────────────────────────────────────────
function buildMarkersColumn(p) {
  var m = (window.M3AssetsMarkers && window.M3AssetsMarkers.MARKERS) || {};
  var entries = [
    ['player',     'PLAYER',     function() { return m.player    && m.player(   { p: p, bearing: 0,  size: 11 }); }],
    ['pc',         'OTHER PC',   function() { return m.pc        && m.pc(       { p: p, bearing: 45, size: 9  }); }],
    ['npc-friend', 'FRIENDLY',   function() { return m.npc       && m.npc(      { p: p, kind: 'friendly', size: 9 }); }],
    ['npc-hostile','HOSTILE',    function() { return m.npc       && m.npc(      { p: p, kind: 'hostile',  size: 9 }); }],
    ['npc-neutral','NEUTRAL',    function() { return m.npc       && m.npc(      { p: p, kind: 'neutral',  size: 9 }); }],
    ['vendor',     'VENDOR',     function() { return m.vendor    && m.vendor(   { p: p, size: 8 }); }],
    ['mission',    'MISSION',    function() { return m.mission   && m.mission(  { p: p, size: 9 }); }],
    ['bounty',     'BOUNTY',     function() { return m.bounty    && m.bounty(   { p: p, size: 9 }); }],
    ['objective',  'OBJECTIVE',  function() { return m.objective && m.objective({ p: p, size: 9 }); }],
    ['anom_t1',    'ANOM · T1',  function() { return m.anomaly_t1 && m.anomaly_t1({ p: p, size: 9  }); }],
    ['anom_t2',    'ANOM · T2',  function() { return m.anomaly_t2 && m.anomaly_t2({ p: p, size: 10 }); }],
    ['anom_t3',    'WORLD BOSS', function() { return m.anomaly_t3 && m.anomaly_t3({ p: p, size: 11 }); }]
  ];
  var cards = entries.map(function(entry) {
    return catalogCard(p, {
      label: entry[1],
      marker: true,
      render: function() { var r = entry[2](); return r || null; }
    });
  });

  return catalogColumn(p, {
    title:  'MARKERS',
    sub:    'ENTITIES · LIVE OVERLAY',
    footer: '§7.9 · Fixed screen-size on top of cartography'
  }, catalogGrid(2, cards));
}

// ── Icons + palettes + overlays column ──────────────────────────────
function buildSupportColumn(p) {
  var icons = window.M3AssetsIcons || {};
  var palettes = window.M3Palettes && window.M3Palettes.PALETTES;

  // Service icons row
  var serviceTiles = Object.keys(icons.SERVICE_ICONS || {}).map(function(id) {
    var iconEl = icons.SERVICE_ICONS[id]({ c: p.amber, size: 20 });
    return el('div', {
      title: id,
      style: {
        width: '36px', height: '36px',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: '1px solid ' + p.inkFaint, background: p.skyDeep + '88'
      }
    }, [iconEl]);
  });
  var serviceSection = el('div', { style: { marginBottom: '14px' }}, [
    subLabel(p, 'SERVICE ICONS'),
    el('div', { style: {
      display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px'
    }}, serviceTiles)
  ]);

  // Attribute + status + faction icons row (mixed)
  var mixedTiles = [];
  ['ATTR_ICONS', 'STATUS_ICONS'].forEach(function(family) {
    Object.keys(icons[family] || {}).forEach(function(id) {
      var iconEl = icons[family][id]({ c: p.ink, size: 18 });
      mixedTiles.push(el('div', {
        title: id,
        style: {
          width: '28px', height: '28px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: '1px solid ' + p.inkFaint, background: p.skyDeep + '88'
        }
      }, [iconEl]));
    });
  });
  Object.keys(icons.FACTION_ICONS || {}).forEach(function(id) {
    var iconEl = icons.FACTION_ICONS[id]({ c: p.amber, size: 18 });
    mixedTiles.push(el('div', {
      title: id,
      style: {
        width: '28px', height: '28px',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: '1px solid ' + p.inkFaint, background: p.skyDeep + '88'
      }
    }, [iconEl]));
  });
  var mixedSection = el('div', { style: { marginBottom: '14px' }}, [
    subLabel(p, 'ATTRIBUTE GLYPHS · STATUS · FACTIONS'),
    el('div', { style: {
      display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px'
    }}, mixedTiles)
  ]);

  // Palette swatches
  var paletteCards = [];
  if (palettes) {
    Object.keys(palettes).forEach(function(palId) {
      var pal = palettes[palId];
      var active = (pal.id === p.id);
      var swatches = [pal.ink, pal.amber, pal.cyan, pal.red, pal.green, pal.ground].map(function(c) {
        return el('div', { style: {
          width: '9px', height: '18px', background: c
        }});
      });
      paletteCards.push(el('div', { style: {
        display: 'flex', alignItems: 'center', gap: '6px',
        padding: '4px 6px',
        background: active ? (pal.amber + '22') : 'rgba(0,0,0,0.3)',
        border: '1px solid ' + (active ? pal.amber : pal.inkFaint)
      }}, [
        el('div', { style: { display: 'flex', gap: '1px' }}, swatches),
        el('div', { style: { flex: '1', fontSize: '8px', letterSpacing: '1px', lineHeight: '1.3' }}, [
          el('div', { style: { color: pal.ink, fontWeight: '600' }}, [pal.label]),
          el('div', { style: { color: pal.inkDim, fontSize: '7px' }}, [pal.sub])
        ]),
        active ? el('div', { style: {
          fontSize: '7px', color: pal.amber, letterSpacing: '1.5px'
        }}, ['● ACTIVE']) : null
      ]));
    });
  }
  var palettesSection = el('div', { style: { marginBottom: '14px' }}, [
    subLabel(p, 'PALETTE SWATCHES'),
    el('div', { style: {
      display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px'
    }}, paletteCards)
  ]);

  // Terrain tiles (need TerrainDefs from composition-engine 4.1e — stub for now)
  var terrainKinds = ['city', 'dune', 'duracrete', 'scrub', 'canyon', 'vapor'];
  var terrainTiles = terrainKinds.map(function(t) {
    var inner;
    if (window.M3CompositionEngine && window.M3CompositionEngine.terrainDefs) {
      var s = svgEl('svg', { width: '100%', height: '100%', viewBox: '0 0 80 38',
                             preserveAspectRatio: 'none' });
      s.appendChild(window.M3CompositionEngine.terrainDefs(p));
      s.appendChild(svgEl('rect', { width: 80, height: 38, fill: 'url(#terr-' + t + ')' }));
      inner = s;
    } else {
      inner = el('div', { style: {
        fontSize: '8px', color: p.inkDim, padding: '12px', textAlign: 'center'
      }}, ['(loading)']);
    }
    return el('div', { style: {
      height: '38px', position: 'relative',
      border: '1px solid ' + p.inkFaint, overflow: 'hidden'
    }}, [
      inner,
      el('div', { style: {
        position: 'absolute', bottom: '0', left: '0', right: '0',
        background: 'rgba(0,0,0,0.6)', color: p.ink,
        fontSize: '7px', letterSpacing: '1.5px', padding: '1px 4px', textAlign: 'center'
      }}, [t.toUpperCase()])
    ]);
  });
  var terrainSection = el('div', {}, [
    subLabel(p, 'TERRAIN TILES · §7.13.2.B'),
    el('div', { style: {
      display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
      gap: '4px', marginTop: '6px'
    }}, terrainTiles)
  ]);

  return catalogColumn(p, {
    title:  'ICONS · PALETTES · OVERLAYS',
    sub:    'SUPPORT LIBRARY',
    footer: '§7.13.2.D/E/F · shared across panels'
  }, el('div', {}, [serviceSection, mixedSection, palettesSection, terrainSection]));
}

// ── Top-level mount function ────────────────────────────────────────
function mount(rootEl, opts) {
  opts = opts || {};
  var p = opts.palette || (window.M3Palettes && window.M3Palettes.getPalette('tatooine'));
  if (!p) {
    rootEl.textContent = 'AssetCatalog: no palette available';
    return rootEl;
  }
  var width  = opts.width  || 1280;
  var height = opts.height || 920;

  // Clear root
  while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);

  var container = el('div', { style: {
    width: width + 'px', height: height + 'px',
    background: '#000', border: '1px solid ' + p.inkDim,
    padding: '24px', color: p.ink,
    fontFamily: "'IBM Plex Mono', monospace",
    overflow: 'hidden', position: 'relative'
  }}, [
    buildHeader(p),
    el('div', { style: {
      display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr 1fr',
      gap: '20px', height: 'calc(100% - 90px)'
    }}, [
      buildLandmarksColumn(p),
      buildStylePrimsColumn(p),
      buildMarkersColumn(p),
      buildSupportColumn(p)
    ])
  ]);

  rootEl.appendChild(container);
  return container;
}

window.M3AssetCatalog = {
  mount: mount
};

})();
