/* ============================================================================
   m3_composition_engine.js — runtime renderer for the SPA holocarta map.

   Drop 4.1e · Tier 1 #4 · ported from map_v3/composition-engine.jsx
   (May 26 2026).

   The composition engine layers static cartography + dynamic state +
   the asset library + an active palette per the canonical z-order
   (architecture v50 §4.15):

     atmosphere → substrate → districts → security tint → streets
       → twin-sun shadows → buildings → furniture → weather overlays
       → time-of-day → sand haze → labels → entities → compass/scale

   It draws nothing itself — it orchestrates the asset modules:
     - M3AssetsStyles.STYLE_PRIMITIVES   (fallback footprints)
     - M3AssetsLandmarks.LANDMARKS       (named landmark illustrations)
     - M3AssetsWilderness.WILDERNESS_LANDMARKS
     - M3AssetsMarkers.MARKERS           (player, PCs, NPCs, POIs)
     - M3AssetsOverlays.{TerrainDefs, HazeDefs, OVERLAYS, OV_*}
                                         (terrain patterns + atmospherics)

   Public API (window.M3CompositionEngine):
     - makeProjector(opts)               world→screen coords
     - MapRenderer(opts) → HTMLDivElement   full chrome + map
     - Tier1aBody(opts)  → SVGElement       just the SVG (no chrome)
     - HolocartaFrame(opts) → HTMLDivElement
                                         diegetic device chrome
     - buildingPositions(proj, rooms) → []  for OV_TwinSunShadows
     - L_Atmosphere / L_Substrate / L_Districts / L_SecurityTint /
       L_Streets / L_Buildings / L_Furniture / L_Labels / L_Entities
                                         individual layer builders
     - CompassRose / ScaleBar            chrome decorations
     - terrainDefs(p)                    re-exports M3AssetsOverlays.TerrainDefs
                                         (catalog's terrain-tile preview
                                         gates on this property — see
                                         m3_asset_catalog.js§388)

   Input contract for MapRenderer/Tier1aBody:
     data = {
       display_name: string,
       bounds: {x_min, y_min, x_max, y_max},
       rooms:    [{id, x, y, w, h, style, slug?, security?}, ...],
       districts:[{id, polygon: [[x,y]...], label_anchor, name, rotation?, terrain?}, ...],
       streets:  [{id, path: [[x,y]...], kind, label?, dashed?}, ...],
       landmarks:[{x, y, label, important?}, ...],
       furniture:[{kind, x, y}, ...],
       dynamic: {
         player: {x, y, bearing},
         pcs:    [{id, x, y, name, bearing}, ...],
         npcs:   [{x, y, kind}, ...],
         poi:    [{x, y, kind}, ...]
       }
     }
   ============================================================================ */
(function(){
'use strict';

var svgEl = window.M3Tokens.svgEl;

// ────────────────────────────────────────────────────────────────
// htmlEl — internal helper for the chrome HTML.
//
// MapRenderer/HolocartaFrame build div trees with inline CSS-in-JS.
// React JSX writes `style={{ position: 'absolute', top: 0 }}` — we
// use a tiny equivalent that takes a style object and assigns it
// onto the element's `style` property.
//
// htmlEl(tag, props, children) where:
//   props.style  = {...}  // assigned via Object.assign(el.style, ...)
//   props.<attr> = value  // assigned via setAttribute (skipped if null)
//   children     = array (HTMLElement | string | null)
//
// Numeric style values get px appended where appropriate (matches React
// JSX behavior). Specifically: top/left/right/bottom/width/height/
// padding/margin/gap/fontSize/letterSpacing/borderRadius/lineHeight.
// ────────────────────────────────────────────────────────────────
var PX_STYLE_KEYS = {
  top: 1, left: 1, right: 1, bottom: 1,
  width: 1, height: 1,
  padding: 1, margin: 1, gap: 1,
  fontSize: 1, letterSpacing: 1, borderRadius: 1, lineHeight: 1,
  marginLeft: 1, marginRight: 1, marginTop: 1, marginBottom: 1,
  paddingLeft: 1, paddingRight: 1, paddingTop: 1, paddingBottom: 1
};

function applyStyle(el, styleObj) {
  for (var key in styleObj) {
    if (!Object.prototype.hasOwnProperty.call(styleObj, key)) continue;
    var val = styleObj[key];
    if (val === undefined || val === null || val === false) continue;
    if (typeof val === 'number' && PX_STYLE_KEYS[key]) {
      val = val + 'px';
    }
    el.style[key] = String(val);
  }
}

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

// ════════════════════════════════════════════════════════════════
// makeProjector — world-units → screen-pixel projection.
//
// Preserves the JSX semantics exactly:
//   scale = min(sW/wW, sH/wH)  — uniform scale, fits within viewport
//   project(wx, wy) = [offsetX + (wx - x_min) * scale,
//                      offsetY + (wy - y_min) * scale]
//   unit = scale                — 1 world unit = `unit` screen px
// ════════════════════════════════════════════════════════════════
function makeProjector(opts) {
  var bounds = opts.bounds;
  var width  = opts.width;
  var height = opts.height;
  var padding = opts.padding || 0;
  var wW = bounds.x_max - bounds.x_min;
  var wH = bounds.y_max - bounds.y_min;
  var sW = width  - padding * 2;
  var sH = height - padding * 2;
  var scale = Math.min(sW / wW, sH / wH);
  var offsetX = padding + (sW - wW * scale) / 2;
  var offsetY = padding + (sH - wH * scale) / 2;
  return {
    scale: scale,
    unit:  scale,
    project: function(wx, wy) {
      return [offsetX + (wx - bounds.x_min) * scale,
              offsetY + (wy - bounds.y_min) * scale];
    }
  };
}

// ════════════════════════════════════════════════════════════════
// LAYER COMPONENTS — each returns an SVG element (typically <g>).
//
// All layer builders take props objects matching the JSX source's
// destructured signatures: `L_Streets({ p, proj, streets })` etc.
// ════════════════════════════════════════════════════════════════

// L_Atmosphere — ground fill + radial vignette via atmosphere-grad def
// (HazeDefs supplies the gradient). Source returned a React fragment;
// we wrap in a <g> for a single returnable element.
function L_Atmosphere(o) {
  var p = o.p, width = o.width, height = o.height;
  return svgEl('g', null, [
    svgEl('rect', { x: 0, y: 0, width: width, height: height,
                    fill: p.ground }),
    svgEl('rect', { x: 0, y: 0, width: width, height: height,
                    fill: 'url(#atmosphere-grad)' })
  ]);
}

// L_Substrate — paint the terrain pattern over the world bounds.
function L_Substrate(o) {
  var proj = o.proj, bounds = o.bounds;
  var terrain = o.terrain || 'city';
  var tl = proj.project(bounds.x_min, bounds.y_min);
  var br = proj.project(bounds.x_max, bounds.y_max);
  return svgEl('rect', {
    x: tl[0], y: tl[1],
    width:  br[0] - tl[0],
    height: br[1] - tl[1],
    fill: 'url(#terr-' + terrain + ')',
    opacity: 0.85
  });
}

// L_SubstrateImage — render a pre-painted raster substrate at the world
// bounds. Used when the area carries a `substrate_image` (architecture
// v51 hybrid lane). Replaces the procedural L_Substrate tile pattern and
// causes Tier1aBody to skip the procedural district/street/building/
// furniture layers (they're baked into the painting).
//
// Orientation: the painting is authored north-up; the adapter
// (m3_adapter.js::fromAreaGeometry) reflects overlay coords Y so they
// land north-up too, so the image is drawn at the bounds rect with NO
// flip and registers with the overlays. preserveAspectRatio='none'
// stretches the PNG to the projected bounds rect — overlay registration
// stays self-consistent because labels/markers use the same projector;
// any PNG/bounds aspect mismatch is a (small) cosmetic stretch only.
function L_SubstrateImage(o) {
  var proj = o.proj, bounds = o.bounds;
  var tl = proj.project(bounds.x_min, bounds.y_min);
  var br = proj.project(bounds.x_max, bounds.y_max);
  var attrs = {
    href: o.href,
    x: tl[0], y: tl[1],
    width:  br[0] - tl[0],
    height: br[1] - tl[1],
    preserveAspectRatio: 'none'
  };
  // 4.x micro-overlay: at close tiers the painting recedes to atmosphere so
  // the tactical room layer reads as the navigable truth on top of it.
  if (o.opacity != null && o.opacity < 1) attrs.opacity = o.opacity;
  return svgEl('image', attrs);
}

// L_SubstrateRooms — the micro-overlay's tactical room layer. When an area
// has a painted substrate the procedural L_Buildings layer is skipped, so the
// painting carries NO interactive room cells. At close zoom (tier <= 1) this
// layer paints each room as a translucent, glowing tactical cell ON TOP of the
// (dimmed) painting: precise click targets and a holo-map read, without
// pretending to be opaque buildings. It mirrors L_Buildings' projection and
// emits the same data-room-id wrapper so client.html's click-to-walk
// decoration (class="rm-adj" + data-travel-dir) works under substrates too.
function L_SubstrateRooms(o) {
  var p = o.p, proj = o.proj;
  var rooms = o.rooms || [];
  var glow = (p.cyan || p.amber || '#39c5cf');
  var children = [];
  rooms.forEach(function(r) {
    if (r.style === 'street') return;
    if (r.x == null || r.y == null) return;
    var w = (r.w || 1) * proj.scale;
    var h = (r.h || 1) * proj.scale;
    var tl = proj.project(r.x - (r.w || 1) / 2, r.y - (r.h || 1) / 2);
    var cx = tl[0] + w / 2, cy = tl[1] + h / 2;
    var cell = [
      svgEl('rect', {
        x: tl[0], y: tl[1], width: w, height: h, rx: 3, ry: 3,
        fill: glow, 'fill-opacity': 0.10,
        stroke: glow, strokeWidth: 1.3, 'stroke-opacity': 0.85,
        'vector-effect': 'non-scaling-stroke'
      }),
      svgEl('circle', { cx: cx, cy: cy, r: 1.6, fill: glow, 'fill-opacity': 0.7 })
    ];
    var wrapAttrs = { 'class': 'rm-cell' };
    if (r.id != null) wrapAttrs['data-room-id'] = String(r.id);
    children.push(svgEl('g', wrapAttrs, cell));
  });
  return svgEl('g', { 'class': 'substrate-rooms' }, children);
}

// L_Districts — district polygons with terrain fills and faint borders.
function L_Districts(o) {
  var p = o.p, proj = o.proj;
  var districts = o.districts || [];
  var terrainOverrides = o.terrainOverrides || {};
  var children = districts.map(function(d) {
    var pts = d.polygon.map(function(pt) { return proj.project(pt[0], pt[1]); });
    var pointsStr = pts.map(function(pair) { return pair.join(','); }).join(' ');
    var terr = d.terrain || terrainOverrides[d.id];
    return svgEl('g', null, [
      svgEl('polygon', {
        points: pointsStr,
        fill:   terr ? 'url(#terr-' + terr + ')' : 'transparent',
        stroke: p.inkFaint, strokeWidth: 0.6,
        opacity: terr ? 0.9 : 1
      })
    ]);
  });
  return svgEl('g', null, children);
}

// L_SecurityTint — per-room translucent overlay by security tier.
// JSX used template-literal hex+alpha suffixes like `${p.green}18`
// (note: requires palette colors to be 6-digit #RRGGBB so the +alpha
// suffix produces valid #RRGGBBAA — palettes already comply).
function L_SecurityTint(o) {
  var p = o.p, proj = o.proj;
  var rooms = o.rooms || [];
  var colors = {
    secured:    p.green + '18',
    commercial: p.amber + '10',
    contested:  p.amber + '25',
    lawless:    p.red   + '22'
  };
  var children = rooms.map(function(r) {
    var tl = proj.project(r.x - r.w / 2, r.y - r.h / 2);
    var w = r.w * proj.scale;
    var h = r.h * proj.scale;
    return svgEl('rect', {
      x: tl[0], y: tl[1], width: w, height: h,
      fill: colors[r.security] || 'transparent'
    });
  });
  return svgEl('g', null, children);
}

// L_Streets — shoulder + surface + optional centerline + optional label.
function L_Streets(o) {
  var p = o.p, proj = o.proj;
  var streets = o.streets || [];

  function widthFor(kind) {
    if (kind === 'main')    return 16;
    if (kind === 'cross')   return 12;
    if (kind === 'cantina') return 10;
    return 8;
  }

  var children = streets.map(function(s) {
    var pts = s.path.map(function(pt) { return proj.project(pt[0], pt[1]); });
    var d = 'M ' + pts.map(function(pair) { return pair.join(' '); }).join(' L ');
    var w = widthFor(s.kind) * (proj.unit / 100);
    var streetKids = [
      // shoulder
      svgEl('path', { d: d, stroke: p.groundShadow,
                      strokeWidth: w + 4, fill: 'none',
                      strokeLinecap: 'round', opacity: 0.4 }),
      // surface
      svgEl('path', { d: d, stroke: p.groundDeep,
                      strokeWidth: w, fill: 'none', strokeLinecap: 'round' })
    ];
    // dashed centerline (main streets only, when not explicitly dashed)
    if (!s.dashed && s.kind === 'main') {
      streetKids.push(svgEl('path', {
        d: d, stroke: p.inkFaint, strokeWidth: 0.6, fill: 'none',
        strokeDasharray: '6 5', opacity: 0.55
      }));
    }
    // alternative: explicit dashed line
    if (s.dashed) {
      streetKids.push(svgEl('path', {
        d: d, stroke: p.inkDim, strokeWidth: 0.8, fill: 'none',
        strokeDasharray: '4 4', opacity: 0.7
      }));
    }
    // street label (centered between first and last points)
    if (s.label) {
      var p0 = pts[0], pLast = pts[pts.length - 1];
      var midX = (p0[0] + pLast[0]) / 2;
      var midY = (p0[1] + pLast[1]) / 2 - w / 2 - 3;
      streetKids.push(svgEl('text', {
        x: midX, y: midY,
        fontSize: 8, fill: p.inkDim, textAnchor: 'middle',
        style: 'letter-spacing: 2px'
      }, [s.label.toUpperCase()]));
    }
    return svgEl('g', null, streetKids);
  });
  return svgEl('g', null, children);
}

// L_Buildings — for each non-street room, try the named landmark binding
// first, then fall back to a style primitive. Each is wrapped in a
// transform that places + scales the 100×100 footprint at world coords.
function L_Buildings(o) {
  var p = o.p, proj = o.proj;
  var rooms = o.rooms || [];
  var tier = (o.tier == null) ? 1 : o.tier;
  var time = o.time;

  // LOD selection per tier (matches JSX source line 205).
  var lod = (tier <= 0) ? 'detailed'
          : (tier === 1) ? 'detailed'
          : (tier === 2) ? 'simplified'
          : 'icon';

  var landmarks = (window.M3AssetsLandmarks &&
                   window.M3AssetsLandmarks.LANDMARKS) || {};
  var wlandmarks = (window.M3AssetsWilderness &&
                    window.M3AssetsWilderness.WILDERNESS_LANDMARKS) || {};
  var styles = (window.M3AssetsStyles &&
                window.M3AssetsStyles.STYLE_PRIMITIVES) || {};

  var children = [];
  rooms.forEach(function(r) {
    if (r.style === 'street') return;
    var tl = proj.project(r.x - r.w / 2, r.y - r.h / 2);
    var w = r.w * proj.scale;
    var h = r.h * proj.scale;
    var transform = 'translate(' + tl[0] + ' ' + tl[1] +
                    ') scale(' + (w / 100) + ' ' + (h / 100) + ')';
    // Prefer urban landmark, then wilderness landmark, then style primitive.
    var landmarkBuilder = r.slug ? (landmarks[r.slug] || wlandmarks[r.slug]) : null;
    var inner;
    if (landmarkBuilder) {
      inner = landmarkBuilder({ p: p, lod: lod, t: time });
    } else {
      var stylePrim = styles[r.style] || styles['default'];
      inner = stylePrim ? stylePrim(p) : null;
    }
    if (inner) {
      // 4.2c: emit data-room-id on the building wrapper so client.html
      // can decorate adjacent-room buildings with click-to-walk
      // attributes (class="rm-adj" + data-travel-dir="<dir>"). The
      // engine itself remains presentation-only; the data attribute is
      // structural, not behavioral. r.id is the AreaGeometry-internal
      // render_room_id (1..n) — same namespace the client uses to look
      // up adjacency in _sw_areaGeom.exits.
      var wrapAttrs = { transform: transform };
      if (r.id != null) wrapAttrs['data-room-id'] = String(r.id);
      children.push(svgEl('g', wrapAttrs, [inner]));
    }
  });
  return svgEl('g', null, children);
}

// L_Furniture — light-touch decorative bits at street/landmark level.
// 6 kinds: speeder-rack, vaporator, scrap-pile, awning, cart, dune-mark.
// Each is positioned at the projected (f.x, f.y) and drawn small.
function L_Furniture(o) {
  var p = o.p, proj = o.proj;
  var items = o.items || [];

  function speederRack(x, y) {
    return svgEl('g', { transform: 'translate(' + x + ' ' + y + ')' }, [
      svgEl('ellipse', { cx: -4, cy: 0, rx: 3, ry: 1.2,
                         fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }),
      svgEl('ellipse', { cx:  4, cy: 0, rx: 3, ry: 1.2,
                         fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 })
    ]);
  }
  function vaporator(x, y) {
    return svgEl('g', { transform: 'translate(' + x + ' ' + y + ')' }, [
      svgEl('circle', { r: 3, fill: p.paperDark,
                        stroke: p.ink, strokeWidth: 0.5 }),
      svgEl('circle', { r: 1.2, fill: p.cyan, opacity: 0.6 })
    ]);
  }
  function scrapPile(x, y) {
    return svgEl('g', { transform: 'translate(' + x + ' ' + y + ')' }, [
      svgEl('path', { d: 'M -5 2 L -2 -3 L 2 -3 L 5 2 Z',
                      fill: p.paperDark, stroke: p.ink, strokeWidth: 0.4 }),
      svgEl('line', { x1: -3, y1: 0, x2: 3, y2: 0,
                      stroke: p.inkDim, strokeWidth: 0.3 })
    ]);
  }
  function awning(x, y) {
    var kids = [
      svgEl('path', { d: 'M -6 0 L 6 0 L 4 -3 L -4 -3 Z',
                      fill: p.amber, opacity: 0.6,
                      stroke: p.ink, strokeWidth: 0.3 })
    ];
    [-3, 0, 3].forEach(function(dx) {
      kids.push(svgEl('line', { x1: dx, y1: 0, x2: dx - 1, y2: -3,
                                stroke: p.inkDim, strokeWidth: 0.2 }));
    });
    return svgEl('g', { transform: 'translate(' + x + ' ' + y + ')' }, kids);
  }
  function cart(x, y) {
    return svgEl('g', { transform: 'translate(' + x + ' ' + y + ')' }, [
      svgEl('rect', { x: -4, y: -2, width: 8, height: 3,
                      fill: p.paperDark, stroke: p.ink, strokeWidth: 0.3 }),
      svgEl('circle', { cx: -3, cy: 2, r: 0.8, fill: p.ink }),
      svgEl('circle', { cx:  3, cy: 2, r: 0.8, fill: p.ink })
    ]);
  }
  function duneMark(x, y) {
    return svgEl('path', {
      d: 'M ' + (x - 6) + ' ' + y +
         ' Q ' + x + ' ' + (y - 4) +
         ' ' + (x + 6) + ' ' + y,
      fill: 'none', stroke: p.inkFaint, strokeWidth: 0.5, opacity: 0.5
    });
  }

  var children = [];
  items.forEach(function(f) {
    var pt = proj.project(f.x, f.y);
    var x = pt[0], y = pt[1];
    var built = null;
    switch (f.kind) {
      case 'speeder-rack': built = speederRack(x, y); break;
      case 'vaporator':    built = vaporator(x, y); break;
      case 'scrap-pile':   built = scrapPile(x, y); break;
      case 'awning':       built = awning(x, y); break;
      case 'cart':         built = cart(x, y); break;
      case 'dune-mark':    built = duneMark(x, y); break;
      default: break;  // unknown kinds silently skipped (matches JSX behavior)
    }
    if (built) children.push(built);
  });
  return svgEl('g', null, children);
}

// L_Labels — district names (tier ≥ 1) + landmark labels (tier ≤ 2).
// pointer-events: none so labels don't intercept clicks.
function L_Labels(o) {
  var p = o.p, proj = o.proj;
  var landmarks = o.landmarks || [];
  var districts = o.districts || [];
  var tier = (o.tier == null) ? 1 : o.tier;

  var children = [];
  // district names — only at tier ≥ 1 (zoomed-out view shows them)
  if (tier >= 1) {
    districts.forEach(function(d) {
      var pt = proj.project(d.label_anchor[0], d.label_anchor[1]);
      var x = pt[0], y = pt[1];
      var attrs = {
        x: x, y: y,
        fontSize: 11, fill: p.inkDim, textAnchor: 'middle',
        style: 'letter-spacing: 4px; font-weight: 600; opacity: 0.55'
      };
      if (d.rotation) {
        attrs.transform = 'rotate(' + d.rotation + ' ' + x + ' ' + y + ')';
      }
      children.push(svgEl('text', attrs, [d.name]));
    });
  }
  // landmark labels — only at tier ≤ 2 (zoomed-in views show them)
  if (tier <= 2) {
    landmarks.forEach(function(l) {
      var pt = proj.project(l.x, l.y);
      var x = pt[0], y = pt[1];
      var size = l.important ? 10 : 8;
      var kids = [
        svgEl('text', {
          x: x, y: y - 18,
          fontSize: size, fill: p.inkBright, textAnchor: 'middle',
          style: 'letter-spacing: 2px; font-weight: 600'
        }, [l.label])
      ];
      if (l.important) {
        kids.push(svgEl('line', {
          x1: x - 18, y1: y - 14, x2: x + 18, y2: y - 14,
          stroke: p.inkDim, strokeWidth: 0.4
        }));
      }
      children.push(svgEl('g', null, kids));
    });
  }
  return svgEl('g', { style: 'pointer-events: none' }, children);
}

// L_Entities — dynamic actors. POIs below NPCs below other PCs below
// the player (per JSX render order). Each is wrapped in a translate.
function L_Entities(o) {
  var p = o.p, proj = o.proj;
  var dyn = o.dynamic || {};
  var poiList = dyn.poi || [];
  var npcs    = dyn.npcs || [];
  var pcs     = dyn.pcs  || [];
  var player  = dyn.player;

  var markers = (window.M3AssetsMarkers &&
                 window.M3AssetsMarkers.MARKERS) || {};

  // POI kind → marker name
  var poiMap = {
    vendor:     markers.vendor,
    mission:    markers.mission,
    bounty:     markers.bounty,
    objective:  markers.objective,
    anomaly_t1: markers.anomaly_t1,
    anomaly_t2: markers.anomaly_t2,
    anomaly_t3: markers.anomaly_t3
  };

  var children = [];
  // POIs first
  poiList.forEach(function(poi) {
    var build = poiMap[poi.kind];
    if (!build) return;
    var pt = proj.project(poi.x, poi.y);
    children.push(svgEl('g', {
      transform: 'translate(' + pt[0] + ' ' + pt[1] + ')'
    }, [build({ p: p })]));
  });
  // NPCs above POIs
  if (markers.npc) {
    npcs.forEach(function(npc) {
      var pt = proj.project(npc.x, npc.y);
      children.push(svgEl('g', {
        transform: 'translate(' + pt[0] + ' ' + pt[1] + ')'
      }, [markers.npc({ p: p, kind: npc.kind })]));
    });
  }
  // Other PCs above NPCs
  if (markers.pc) {
    pcs.forEach(function(pc) {
      var pt = proj.project(pc.x, pc.y);
      children.push(svgEl('g', {
        transform: 'translate(' + pt[0] + ' ' + pt[1] + ')'
      }, [markers.pc({ p: p, name: pc.name, bearing: pc.bearing })]));
    });
  }
  // Player always topmost
  if (player && markers.player) {
    var pt = proj.project(player.x, player.y);
    children.push(svgEl('g', {
      transform: 'translate(' + pt[0] + ' ' + pt[1] + ')'
    }, [markers.player({ p: p, bearing: player.bearing })]));
  }
  return svgEl('g', null, children);
}

// buildingPositions — pre-compute centers for OV_TwinSunShadows.
// Returns { x, y, r, lit } projected positions for non-street rooms.
function buildingPositions(proj, rooms) {
  return (rooms || []).filter(function(r) { return r.style !== 'street'; })
    .map(function(r) {
      var pt = proj.project(r.x, r.y);
      return {
        x: pt[0], y: pt[1],
        r: Math.max(r.w, r.h) * proj.scale * 0.5,
        lit: false
      };
    });
}

// ════════════════════════════════════════════════════════════════
// CHROME — compass rose + scale bar at the corners of the SVG.
// ════════════════════════════════════════════════════════════════
function CompassRose(o) {
  var p = o.p, x = o.x, y = o.y;
  var children = [
    svgEl('circle', { r: 22, fill: 'none', stroke: p.inkDim, strokeWidth: 0.5 }),
    svgEl('circle', { r: 18, fill: 'none', stroke: p.inkFaint, strokeWidth: 0.3 })
  ];
  var labels = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' };
  [0, 90, 180, 270].forEach(function(a) {
    var rad = (a - 90) * Math.PI / 180;
    var x2 = Math.cos(rad) * 16;
    var y2 = Math.sin(rad) * 16;
    var tx = Math.cos(rad) * 26;
    var ty = Math.sin(rad) * 26 + 3;
    children.push(svgEl('g', null, [
      svgEl('line', {
        x1: 0, y1: 0, x2: x2, y2: y2,
        stroke: a === 0 ? p.amber : p.inkDim,
        strokeWidth: a === 0 ? 1.2 : 0.6
      }),
      svgEl('text', {
        x: tx, y: ty, fontSize: 8, fill: p.inkDim, textAnchor: 'middle'
      }, [labels[a]])
    ]));
  });
  children.push(svgEl('circle', { r: 1.5, fill: p.amber }));
  return svgEl('g', { transform: 'translate(' + x + ' ' + y + ')' }, children);
}

function ScaleBar(o) {
  var p = o.p, proj = o.proj, x = o.x, y = o.y;
  var km = 0.5;            // 0.5 world units = the marked distance
  var px = km * proj.scale;
  return svgEl('g', { transform: 'translate(' + x + ' ' + y + ')' }, [
    svgEl('line', { x1: 0,  y1: 0, x2: px, y2: 0, stroke: p.ink, strokeWidth: 1 }),
    svgEl('line', { x1: 0,  y1: -3, x2: 0,  y2: 3, stroke: p.ink, strokeWidth: 1 }),
    svgEl('line', { x1: px, y1: -3, x2: px, y2: 3, stroke: p.ink, strokeWidth: 1 }),
    svgEl('line', { x1: px / 2, y1: -2, x2: px / 2, y2: 2,
                    stroke: p.inkDim, strokeWidth: 0.7 }),
    svgEl('text', { x: px / 2, y: 14, fontSize: 8, fill: p.inkDim,
                    textAnchor: 'middle',
                    style: 'letter-spacing: 1.5px' }, ['~ 250 m'])
  ]);
}

// ════════════════════════════════════════════════════════════════
// HolocartaFrame — diegetic device chrome (HTML divs, not SVG).
//
// Top bar: ◉ HOLOCARTA · breadcrumb · TIER N · ● LIVE
// Body: caller-supplied children (the SVG map content)
// Bottom legend: small chips per `legend` entry + controls hint
// ════════════════════════════════════════════════════════════════
function HolocartaFrame(o) {
  var p = o.p;
  var width = o.width, height = o.height;
  var breadcrumb = o.breadcrumb || '';
  var legend = o.legend || [];
  var tier = o.tier;
  var children = o.children || [];  // accept array, single el, or string

  // Normalize children to an array.
  var childArr;
  if (Array.isArray(children)) childArr = children;
  else if (children) childArr = [children];
  else childArr = [];

  // ── Top bar ─────────────────────────────────────────────────
  var topLeft = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 14 }
  }, [
    htmlEl('span', { style: { color: p.cyan } }, ['◉ HOLOCARTA']),
    htmlEl('span', { style: { color: p.inkDim } }, ['·']),
    htmlEl('span', { style: { color: p.ink } }, [breadcrumb])
  ]);
  var topRight = htmlEl('div', {
    style: { display: 'flex', gap: 14, color: p.inkDim, fontSize: 9 }
  }, [
    htmlEl('span', null, ['TIER ' + tier]),
    htmlEl('span', { style: { color: p.amber } }, ['● LIVE'])
  ]);
  var topBar = htmlEl('div', {
    style: {
      position: 'absolute', top: 0, left: 0, right: 0, height: 36,
      borderBottom: '1px solid ' + p.inkDim,
      background: 'linear-gradient(180deg, ' + p.sky + ', ' + p.skyDeep + ')',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px', fontSize: 10, letterSpacing: 2.5,
      zIndex: 50
    }
  }, [topLeft, topRight]);

  // ── Map content area ────────────────────────────────────────
  var contentArea = htmlEl('div', {
    style: {
      position: 'absolute', top: 36, left: 0, right: 0, bottom: 28
    }
  }, childArr);

  // ── Bottom legend ───────────────────────────────────────────
  var legendChips = legend.map(function(l) {
    var chipSwatch = htmlEl('span', { style: {
      width: 8, height: 8,
      background: l.color || p.ink,
      borderRadius: l.shape === 'square' ? 0 : '50%',
      clipPath: l.shape === 'tri' ? 'polygon(50% 0, 100% 100%, 0 100%)' : null,
      display: 'inline-block',
      boxShadow: l.glow ? ('0 0 4px ' + (l.color || p.ink)) : 'none'
    } });
    var chipLabel = htmlEl('span', { style: { color: p.ink } }, [l.label]);
    return htmlEl('div', {
      style: { display: 'flex', alignItems: 'center', gap: 5, color: p.inkDim }
    }, [chipSwatch, chipLabel]);
  });
  var controlsHint = htmlEl('div', {
    style: { marginLeft: 'auto', color: p.inkDim, fontSize: 9 }
  }, ['◯ scroll-zoom · click-drag pan · esc to close']);
  var bottomBar = htmlEl('div', {
    style: {
      position: 'absolute', bottom: 0, left: 0, right: 0, height: 28,
      borderTop: '1px solid ' + p.inkDim,
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', ' + p.sky + ')',
      display: 'flex', alignItems: 'center',
      padding: '0 16px', gap: 18, fontSize: 9, letterSpacing: 1.5,
      zIndex: 50
    }
  }, legendChips.concat([controlsHint]));

  // ── Outer chrome ────────────────────────────────────────────
  return htmlEl('div', {
    style: {
      width: width, height: height, position: 'relative',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + p.inkDim,
      boxShadow: 'inset 0 0 40px ' + p.skyDeep +
                 ', 0 0 0 1px #000, 0 20px 50px rgba(0,0,0,0.7)',
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      overflow: 'hidden'
    }
  }, [topBar, contentArea, bottomBar]);
}

// ════════════════════════════════════════════════════════════════
// Tier1aBody — the actual SVG renderer, no HTML chrome.
//
// Used by the navigator (and by anything that wants to compose the
// map into something other than HolocartaFrame). Returns a <svg>.
// ════════════════════════════════════════════════════════════════
function Tier1aBody(o) {
  var data = o.data;
  var p = o.palette;
  var tier = (o.tier == null) ? 1 : o.tier;
  var time = o.time || 'day';
  var weather = o.weather || 'clear';
  var width = o.width, height = o.height;
  var proj = makeProjector({
    bounds: data.bounds, width: width, height: height, padding: 24
  });
  // JSX used React.useMemo; we just recompute (cheap at this scale).
  var buildings = buildingPositions(proj, data.rooms);

  // Pull terrain/haze defs from the assets module.
  var overlays = window.M3AssetsOverlays || {};
  var TerrainDefs = overlays.TerrainDefs;
  var HazeDefs = overlays.HazeDefs;
  var OV_TwinSunShadows = overlays.OV_TwinSunShadows;
  var OV_TimeOfDay = overlays.OV_TimeOfDay;
  var OV_SandHaze = overlays.OV_SandHaze;
  var OV_Sandstorm = overlays.OV_Sandstorm;
  var OV_Rain = overlays.OV_Rain;
  var OV_Smog = overlays.OV_Smog;

  var children = [];
  if (TerrainDefs) children.push(TerrainDefs(p));
  if (HazeDefs)    children.push(HazeDefs(p));
  children.push(L_Atmosphere({ p: p, width: width, height: height }));
  // Substrate: a pre-painted raster when the area provides one
  // (architecture v51 hybrid lane), else the procedural tile pattern +
  // district fills + security tint + street ribbons. Under a substrate
  // those four layers are baked into the painting, so they're skipped —
  // including L_SecurityTint (the painting already reads the security
  // character of each district; a per-room wash on top would muddy it).
  if (data.substrate_image) {
    // micro-overlay: dim the painting at close zoom (tier <= 1) so the
    // tactical room layer below reads as the navigable surface.
    var subOpacity = (tier <= 1) ? 0.5 : 1;
    children.push(L_SubstrateImage({
      proj: proj, bounds: data.bounds, href: data.substrate_image,
      opacity: subOpacity
    }));
  } else {
    children.push(L_Substrate({ proj: proj, bounds: data.bounds, terrain: 'city' }));
    children.push(L_Districts({ p: p, proj: proj, districts: data.districts || [] }));
    children.push(L_SecurityTint({ p: p, proj: proj, rooms: data.rooms || [] }));
    children.push(L_Streets({ p: p, proj: proj, streets: data.streets || [] }));
  }

  // Twin-sun shadows, building footprints, ambient furniture — all baked
  // into the substrate painting, so render them only in procedural mode.
  if (!data.substrate_image) {
    // twin-sun shadows — null when not applicable, push only if non-null
    if (OV_TwinSunShadows) {
      var shadows = OV_TwinSunShadows({ p: p, buildings: buildings, time: time });
      if (shadows) children.push(shadows);
    }

    children.push(L_Buildings({ p: p, proj: proj, rooms: data.rooms || [],
                                tier: tier, time: time }));
    children.push(L_Furniture({ p: p, proj: proj, items: data.furniture || [] }));
  }

  // weather/atmospheric overlays — gated by inputs
  if (weather === 'sandstorm' && OV_Sandstorm) {
    children.push(OV_Sandstorm({ width: width, height: height }));
  }
  if (p.id === 'nar_shaddaa' && OV_Rain) {
    children.push(OV_Rain({ width: width, height: height }));
  }
  if (p.id === 'coruscant_under' && OV_Smog) {
    children.push(OV_Smog({ p: p, width: width, height: height }));
  }
  if (OV_TimeOfDay) {
    var tod = OV_TimeOfDay({ time: time, width: width, height: height });
    if (tod) children.push(tod);
  }
  if (p.id === 'tatooine' && OV_SandHaze) {
    children.push(OV_SandHaze({ p: p, width: width, height: height }));
  }

  // micro-overlay: tactical room cells over the (dimmed) substrate at close
  // zoom. Placed after weather so it reads clearly, before labels/entities so
  // room labels and the player marker sit on top.
  if (data.substrate_image && tier <= 1) {
    children.push(L_SubstrateRooms({ p: p, proj: proj, rooms: data.rooms || [] }));
  }

  children.push(L_Labels({ p: p, proj: proj,
                           landmarks: data.landmarks || [],
                           districts: data.districts || [],
                           tier: tier }));
  children.push(L_Entities({ p: p, proj: proj,
                             dynamic: data.dynamic || {} }));
  children.push(CompassRose({ p: p, x: width - 60, y: height - 60 }));
  children.push(ScaleBar({ p: p, proj: proj, x: 28, y: height - 36 }));

  return svgEl('svg', {
    width: width, height: height,
    viewBox: '0 0 ' + width + ' ' + height,
    style: 'display: block; background: ' + p.groundDeep
  }, children);
}

// ════════════════════════════════════════════════════════════════
// MapRenderer — convenience wrapper: chrome + Tier1aBody.
//
// Returns the outer HolocartaFrame div, containing the SVG body
// inside its map content area.
// ════════════════════════════════════════════════════════════════
function MapRenderer(o) {
  var data = o.data;
  var p = o.palette;
  var tier = o.tier || 1;
  var time = o.time || 'day';
  var weather = o.weather || 'clear';
  var width = o.width, height = o.height;

  var legend = [
    { color: p.cyan,  shape: 'circle', glow: true,  label: 'YOU' },
    { color: p.cyan,  shape: 'circle',              label: 'PC' },
    { color: p.amber, shape: 'circle',              label: 'FRIENDLY' },
    { color: p.red,   shape: 'tri',                 label: 'HOSTILE' },
    { color: p.amber, shape: 'square',              label: 'VENDOR' },
    { color: p.green, shape: 'circle',              label: 'OBJECTIVE' },
    { color: p.gold,  shape: 'circle', glow: true,  label: 'ANOMALY · T3' }
  ];
  var breadcrumb =
    'GALAXY ▸ OUTER RIM ▸ TATOOINE ▸ ' +
    (data.display_name || '') +
    ' ▸ SPACEPORT';

  var body = Tier1aBody({
    data: data, palette: p, tier: tier, time: time, weather: weather,
    width: width, height: height
  });
  return HolocartaFrame({
    p: p, width: width, height: height + 64,
    breadcrumb: breadcrumb, legend: legend,
    tier: '1A · DISTRICT',
    children: [body]
  });
}

// ════════════════════════════════════════════════════════════════
// PUBLIC API
// terrainDefs is the catalog's awaited reference (see
// m3_asset_catalog.js§388). It's the same TerrainDefs from
// M3AssetsOverlays — just exposed here so the catalog's gate
// (`window.M3CompositionEngine && window.M3CompositionEngine.terrainDefs`)
// can light up the terrain-tile preview.
// ════════════════════════════════════════════════════════════════
window.M3CompositionEngine = {
  // primary entry points
  makeProjector:     makeProjector,
  MapRenderer:       MapRenderer,
  Tier1aBody:        Tier1aBody,
  HolocartaFrame:    HolocartaFrame,
  buildingPositions: buildingPositions,
  // layer components
  L_Atmosphere:      L_Atmosphere,
  L_Substrate:       L_Substrate,
  L_SubstrateImage:  L_SubstrateImage,
  L_Districts:       L_Districts,
  L_SecurityTint:    L_SecurityTint,
  L_Streets:         L_Streets,
  L_Buildings:       L_Buildings,
  L_Furniture:       L_Furniture,
  L_Labels:          L_Labels,
  L_Entities:        L_Entities,
  // chrome
  CompassRose:       CompassRose,
  ScaleBar:          ScaleBar,
  // terrain re-export for the catalog
  terrainDefs: function(p) {
    var overlays = window.M3AssetsOverlays;
    if (!overlays || typeof overlays.TerrainDefs !== 'function') return null;
    return overlays.TerrainDefs(p);
  }
};

})();
