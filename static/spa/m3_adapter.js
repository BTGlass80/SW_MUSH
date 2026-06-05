/* ============================================================================
   m3_adapter.js — server AreaGeometry → M3 composition engine input contract.

   Drop 4.2a · Tier 1 #4 · ported wire-in adapter (May 26 2026).
   Drop 4.2c · added optional areaMap second arg + label translation + per-room
              security cross-reference (May 26 2026 — schema bump 1 → 2).

   The composition engine (m3_composition_engine.js, drop 4.1e) expects a
   `data` shape derived from the React-prototype's static fixtures. The
   live server emits `area_geometry` payloads sourced from
   data/worlds/<era>/maps/<area>.yaml via engine/area_loader.py. The two
   shapes are close but not identical. This module is the translation
   seam.

   LOUD SUBSTITUTION NOTICE (per architecture v50 §6.2 phantom catalog,
   pattern 3). 4.2a/b/c closure status:

     - `labels` (street labels, flavor warnings) → 4.2c RESTORED.
       Street-anchored labels (kind='street' + path_id set) attach to the
       matching street's `label` field. Flavor/warning labels with `pos`
       become entries in the top-level landmarks[] array (important=true
       for warnings, so the engine underlines them).
       BETWEEN-mode labels (kind='street' + between=[a,b]) are still
       skipped — they'd require synthesizing a virtual street between the
       two rooms, which is structural rather than translational. Rare in
       practice (Mos Eisley has zero); rebuild is a small follow-up.
     - `landmarks` array → 4.2c PROMOTED. AreaGeometry landmarks now go
       into the M3 top-level landmarks[] array (where L_Labels renders
       their text per the engine spec) AND continue to populate
       dynamic.poi (where L_Entities renders their glyphs). Named-
       landmark illustrations still resolve via room.slug in L_Buildings.
     - `furniture` → still empty in 4.2c. Server emits no furniture; not
       fixable client-side. Queued as Phase-1-protocol-substrate scope.
     - `dynamic.pcs/npcs` → working since 4.2a.
     - `dynamic.player.bearing` → still defaults to 0. Server emits no
       bearing. Phase-1-protocol-substrate scope.
     - palette name → passed through to MapRenderer opts. Working.
     - `security` per-room → 4.2c PARTIAL RESTORE via area_map cross-
       reference. Pass the optional second arg areaMap to
       fromAreaGeometry; security comes from area_map.rooms[].sec keyed
       by NAME-match against AreaGeometry rooms[].name (the two payloads
       use disjoint id namespaces — see §"the namespace gap" below).
       When areaMap omitted or no match, security stays unset and the
       engine's SecurityTint layer no-ops on that room.
     - `time`/`weather` (consumed by Tier1aBody/MapRenderer, not by the
       adapter) → still hardcoded at call sites in client.html. Server
       emits no time-of-day or weather state. Phase-1-protocol-substrate.

   THE NAMESPACE GAP (4.2c key insight). area_geometry's `rooms[].id`
   uses YAML-internal ids (1..n per file); area_map's `rooms[].id` uses
   SERVER database ids. The two payloads describe overlapping rooms but
   in disjoint namespaces. Stable shared keys:
     - room NAME (canonical text per side, exact match in well-built data)
     - room SLUG (only present in some payloads)
   For 4.2c we cross-reference by NAME, with a fallback (when names
   differ — e.g. truncated names in area_map) to SPATIAL position
   matching (closest XY centroid).

   ID-namespace cross-reference is also used at the CLIENT layer (not
   in this adapter) to power click-to-walk on the M3 mini — see
   _xrefAreaMapToGeom() in client.html.

   The adapter returns NULL when the input geometry is incomplete —
   client.html falls back to the legacy MapView renderer in that case.

   Public API:
     window.M3Adapter.fromAreaGeometry(geom, areaMap?) → data | null
     window.M3Adapter.SCHEMA_VERSION                   → 2
   ============================================================================ */
(function(){
'use strict';

var SCHEMA_VERSION = 2;

// ─── helpers ─────────────────────────────────────────────────────────

function _isFiniteNum(v) {
  return typeof v === 'number' && isFinite(v);
}

function _hasFields(obj, fields) {
  if (!obj || typeof obj !== 'object') return false;
  for (var i = 0; i < fields.length; i++) {
    if (!(fields[i] in obj)) return false;
  }
  return true;
}

// ─── room translation ────────────────────────────────────────────────
// AreaGeometry MapRoom: {id, name, zone, x, y, w, h, style, symbol, slug?}
// M3 room:              {id, x, y, w, h, style, slug?, security?}
// Notes:
//   - `zone` (district id) is dropped at the room level — districts
//     are conveyed via the districts[] array, not per-room.
//   - `symbol` is dropped — M3 derives glyph from style or slug.
//   - `security` is not in AreaGeometry today. 4.2c adds optional
//     cross-reference via area_map.rooms[].sec by NAME match (see
//     _buildSecurityIndexFromAreaMap below).
function _translateRoom(r, securityIndex, flipY) {
  if (!_hasFields(r, ['id', 'x', 'y', 'w', 'h', 'style'])) return null;
  var out = {
    id:    r.id,
    x:     r.x,
    y:     flipY(r.y),
    w:     r.w,
    h:     r.h,
    style: r.style,
  };
  if (r.slug) out.slug = r.slug;
  if (r.name) out.name = r.name;   // preserved 4.2c — useful for client-side debug
  // 4.2c: explicit AreaGeometry security wins if present
  if (r.security) {
    out.security = r.security;
  } else if (securityIndex && r.name && securityIndex[r.name]) {
    // Cross-referenced from area_map by name
    out.security = securityIndex[r.name];
  }
  return out;
}

// ─── district translation ────────────────────────────────────────────
// AreaGeometry District: {id, name, polygon, label_anchor, rotation}
// M3 district:           {id, polygon, label_anchor, name, rotation?, terrain?}
// 1:1 map. terrain is reserved for future use.
function _translateDistrict(d, flipY) {
  if (!_hasFields(d, ['id', 'name', 'polygon', 'label_anchor'])) return null;
  // Build NEW arrays — do NOT mutate d.polygon / d.label_anchor. The
  // source geom is cached client-side (window._sw_areaGeom) and re-fed
  // through the adapter on every tick; mutating shared arrays would
  // compound the Y reflection across re-renders.
  var poly = Array.isArray(d.polygon)
    ? d.polygon.map(function (pt) { return [pt[0], flipY(pt[1])]; })
    : d.polygon;
  var anchor = (Array.isArray(d.label_anchor) && d.label_anchor.length >= 2)
    ? [d.label_anchor[0], flipY(d.label_anchor[1])]
    : d.label_anchor;
  var out = {
    id:           d.id,
    name:         d.name,
    polygon:      poly,
    label_anchor: anchor,
  };
  if (_isFiniteNum(d.rotation)) out.rotation = d.rotation;
  if (d.terrain) out.terrain = d.terrain;
  return out;
}

// ─── exit_paths → streets (+ optional street labels) ─────────────────
// AreaGeometry: exit_paths is a DICT keyed "fromId-toId" with values
// {kind, path, width?}. M3 streets is an ARRAY of {id, path, kind, ...}.
// We use the dict key as the street id (it's already unique per exit).
//
// 4.2c: also accepts an optional streetLabelIndex (built by
// _buildStreetLabelIndexFromLabels) — keyed by path_id, gives the
// matching MapLabel's text to attach as street.label.
function _translateStreets(exit_paths, streetLabelIndex, flipY) {
  if (!exit_paths || typeof exit_paths !== 'object') return [];
  var out = [];
  for (var key in exit_paths) {
    if (!Object.prototype.hasOwnProperty.call(exit_paths, key)) continue;
    var e = exit_paths[key];
    if (!e || !Array.isArray(e.path) || e.path.length < 2) continue;
    // NEW array — never mutate e.path (shared with cached geom).
    var s = {
      id:   key,
      path: e.path.map(function (pt) { return [pt[0], flipY(pt[1])]; }),
      kind: e.kind || 'street',
    };
    if (_isFiniteNum(e.width)) s.width = e.width;
    // 4.2c: attach label if available for this path_id
    if (streetLabelIndex && streetLabelIndex[key]) {
      s.label = streetLabelIndex[key];
    }
    out.push(s);
  }
  return out;
}

// ─── 4.2c: build a street-label lookup from AreaGeometry labels ──────
// MapLabel has three anchor modes (path_id / between / pos). We only
// translate path_id-mode street labels here — those map cleanly to
// M3's per-street `label` field. between-mode labels would need a
// synthesized intermediate street (out of scope for 4.2c). pos-mode
// labels become standalone landmarks (see _translateLabelsToLandmarks).
function _buildStreetLabelIndexFromLabels(labels) {
  if (!Array.isArray(labels)) return {};
  var index = {};
  for (var i = 0; i < labels.length; i++) {
    var lbl = labels[i];
    if (!lbl || !lbl.text) continue;
    if (lbl.kind !== 'street') continue;
    if (!lbl.path_id) continue;     // skip between/pos here
    // Last-write-wins if multiple labels target the same path_id (rare).
    index[lbl.path_id] = lbl.text;
  }
  return index;
}

// ─── 4.2c: free-floating labels → top-level landmarks ────────────────
// MapLabel with kind in {flavor, warning} and a `pos: [x, y]` anchor
// has no equivalent in the M3 engine's slot model — there's no "free
// label" layer. The closest semantic fit is the engine's landmarks[]
// array, which L_Labels renders as a text element at (x, y - 18).
// Important: warnings get `important: true` so the engine underlines
// them (a faint hairline above the text — see L_Labels:lm.important).
function _translateLabelsToLandmarks(labels, flipY) {
  if (!Array.isArray(labels)) return [];
  var out = [];
  for (var i = 0; i < labels.length; i++) {
    var lbl = labels[i];
    if (!lbl || !lbl.text) continue;
    if (lbl.kind !== 'flavor' && lbl.kind !== 'warning') continue;
    if (!Array.isArray(lbl.pos) || lbl.pos.length < 2) continue;
    if (!_isFiniteNum(lbl.pos[0]) || !_isFiniteNum(lbl.pos[1])) continue;
    out.push({
      x:         lbl.pos[0],
      y:         flipY(lbl.pos[1]),
      label:     lbl.text,
      important: lbl.kind === 'warning',
    });
  }
  return out;
}

// ─── 4.2c: AreaGeometry landmarks → top-level landmarks + POI ────────
// Promote AreaGeometry landmarks into the engine's top-level
// landmarks[] array so L_Labels renders their label text. Each
// landmark with a `label` field becomes a labeled landmark; landmarks
// without a label still ride along as POI markers (existing 4.2a
// behavior — see _translateLandmarksToPoi).
//
// Landmark coordinate shape: the AreaGeometry loader (engine/
// area_loader.py::Landmark) emits `pos: [x, y]` and `name`, NOT bare
// `x`/`y`/`label`. Earlier these helpers only read `x`/`y`/`label`, so
// EVERY real landmark was silently dropped (none of the 9 Mos Eisley
// landmarks rendered). _landmarkXY normalizes both shapes: prefer
// `pos`, fall back to `x`/`y`. Label text comes from `label` or `name`.
function _landmarkXY(lm) {
  if (!lm) return null;
  var x, y;
  if (Array.isArray(lm.pos) && lm.pos.length >= 2 &&
      _isFiniteNum(lm.pos[0]) && _isFiniteNum(lm.pos[1])) {
    x = lm.pos[0]; y = lm.pos[1];
  } else if (_isFiniteNum(lm.x) && _isFiniteNum(lm.y)) {
    x = lm.x; y = lm.y;
  } else {
    return null;
  }
  return { x: x, y: y };
}

function _translateLandmarksToTopLevel(landmarks, flipY) {
  if (!Array.isArray(landmarks)) return [];
  var out = [];
  for (var i = 0; i < landmarks.length; i++) {
    var lm = landmarks[i];
    var xy = _landmarkXY(lm);
    if (!xy) continue;
    var label = lm.label || lm.name;
    if (!label) continue;           // unlabeled landmarks → POI only
    out.push({
      x:         xy.x,
      y:         flipY(xy.y),
      label:     label,
      important: !!lm.important,
    });
  }
  return out;
}

// ─── landmarks → POI (continued from 4.2a) ───────────────────────────
// AreaGeometry Landmark carries {kind, x, y, label, min_zoom, ...}. The
// M3 engine resolves named-landmark illustrations by room slug, so
// landmarks that align with rooms render via L_Buildings. The remainder
// (free-standing landmarks not anchored to a room) become POI markers
// on the dynamic layer.
//
// 4.2c: dual-use — labeled landmarks also appear in the top-level
// landmarks[] array (via _translateLandmarksToTopLevel) so their text
// renders via L_Labels. The two paths are additive, not duplicative:
// L_Entities renders the glyph, L_Labels renders the text above.
function _translateLandmarksToPoi(landmarks, flipY) {
  if (!Array.isArray(landmarks)) return [];
  var out = [];
  for (var i = 0; i < landmarks.length; i++) {
    var lm = landmarks[i];
    var xy = _landmarkXY(lm);
    if (!xy) continue;
    out.push({
      x:    xy.x,
      y:    flipY(xy.y),
      kind: lm.kind || lm.icon || 'landmark',
    });
  }
  return out;
}

// ─── 4.2c: per-room security cross-reference from area_map ───────────
// area_map.rooms[].sec is keyed by server DB id; we need to look it
// up by name to bridge into AreaGeometry's render_room_id namespace.
// Returns a name → sec dict. Names are matched exactly (case-
// sensitive); server emits canonical names that match the YAML in
// well-built data. When names differ (e.g. server truncates names
// >28 chars per engine/area_map.py:207), no match — security falls
// through unset and the SecurityTint layer no-ops on that room.
function _buildSecurityIndexFromAreaMap(areaMap) {
  if (!areaMap || !Array.isArray(areaMap.rooms)) return {};
  var index = {};
  for (var i = 0; i < areaMap.rooms.length; i++) {
    var r = areaMap.rooms[i];
    if (!r || !r.name || !r.sec) continue;
    index[r.name] = r.sec;
  }
  return index;
}

// ─── dynamic state assembly ──────────────────────────────────────────
// (unchanged from 4.2a)
function _buildDynamic(geom, flipY) {
  var player = geom.player || {};
  var pcs = [];
  var npcs = [];
  var contacts = Array.isArray(geom.contacts) ? geom.contacts : [];
  for (var i = 0; i < contacts.length; i++) {
    var c = contacts[i];
    if (!c || !_isFiniteNum(c.x) || !_isFiniteNum(c.y)) continue;
    var entry = {
      x:       c.x,
      y:       flipY(c.y),
      bearing: _isFiniteNum(c.bearing) ? c.bearing : 0,
      name:    c.name || '',
      id:      c.id || c.name || ('c' + i),
    };
    if (c.kind === 'pc') {
      pcs.push(entry);
    } else {
      npcs.push({ x: entry.x, y: entry.y, kind: c.kind || 'npc' });
    }
  }
  var poi = _translateLandmarksToPoi(geom.landmarks, flipY);
  // Dynamic POI feed: server-emitted live entities (bounty targets, …) arrive
  // in Y-up render coords (same space as landmarks), so flip Y to match. These
  // are appended to the static authored-landmark POIs; L_Entities renders both.
  if (Array.isArray(geom.pois)) {
    for (var pj = 0; pj < geom.pois.length; pj++) {
      var sp = geom.pois[pj];
      if (!sp || !_isFiniteNum(sp.x) || !_isFiniteNum(sp.y) || !sp.kind) continue;
      poi.push({ x: sp.x, y: flipY(sp.y), kind: sp.kind });
    }
  }
  return {
    player: {
      x:       _isFiniteNum(player.x) ? player.x : 0,
      y:       flipY(_isFiniteNum(player.y) ? player.y : 0),
      bearing: _isFiniteNum(player.bearing) ? player.bearing : 0,
    },
    pcs:  pcs,
    npcs: npcs,
    poi:  poi,
  };
}

// ─── main entry ──────────────────────────────────────────────────────
// 4.2c: optional second arg areaMap. When supplied, the adapter uses
// it to cross-reference per-room security (via name match). Without
// it, security stays unset and the engine's SecurityTint no-ops.
function fromAreaGeometry(geom, areaMap) {
  if (!geom || typeof geom !== 'object') return null;
  if (!geom.bounds) return null;
  if (!Array.isArray(geom.rooms) || geom.rooms.length === 0) return null;

  // ── Y-axis reflection ──────────────────────────────────────────────
  // AreaGeometry data is authored Y-UP (origin bottom-left; higher y =
  // further "north" on the map). The datapad prototype / map_view.js
  // honor this by flipping the world <g> with scale(1,-1). The M3
  // composition engine's projector, by contrast, maps y straight down
  // (project(x_min, y_min) → top-left), so feeding it raw Y-up coords
  // renders the whole map vertically inverted. We reconcile here, once,
  // by reflecting every emitted y about the bounds' vertical midline:
  //   y' = (y_min + y_max) - y
  // This keeps text/glyphs upright (only positions move, unlike a
  // group scale(1,-1) which would mirror labels) and makes a Y-up
  // painted substrate register correctly with the overlays drawn on
  // top of it. The raster substrate is drawn at the bounds rect and is
  // NOT reflected here — authored north-up, it lands north-up.
  var _ymin = _isFiniteNum(geom.bounds.y_min) ? geom.bounds.y_min : 0;
  var _ymax = _isFiniteNum(geom.bounds.y_max) ? geom.bounds.y_max : 0;
  var _ysum = _ymin + _ymax;
  function flipY(y) { return _isFiniteNum(y) ? (_ysum - y) : y; }

  // 4.2c: build cross-reference indexes once
  var securityIndex    = _buildSecurityIndexFromAreaMap(areaMap);
  var streetLabelIndex = _buildStreetLabelIndexFromLabels(geom.labels);

  // Translate the static layers
  var rooms = [];
  for (var i = 0; i < geom.rooms.length; i++) {
    var r = _translateRoom(geom.rooms[i], securityIndex, flipY);
    if (r) rooms.push(r);
  }
  if (rooms.length === 0) return null;

  var districts = [];
  if (Array.isArray(geom.districts)) {
    for (var j = 0; j < geom.districts.length; j++) {
      var d = _translateDistrict(geom.districts[j], flipY);
      if (d) districts.push(d);
    }
  }

  var streets = _translateStreets(geom.exit_paths, streetLabelIndex, flipY);

  // 4.2c: top-level landmarks = (labeled AreaGeometry landmarks) ⊕
  // (flavor/warning labels with pos anchor). Both kinds render via
  // L_Labels with text + optional underline for important entries.
  var topLandmarks = _translateLandmarksToTopLevel(geom.landmarks, flipY)
                       .concat(_translateLabelsToLandmarks(geom.labels, flipY));

  var out = {
    display_name: geom.display_name || geom.area_key || '',
    bounds:       geom.bounds,
    rooms:        rooms,
    districts:    districts,
    streets:      streets,
    landmarks:    topLandmarks,
    // 4.2c: furniture still empty — server emits no furniture data.
    // Phase-1-protocol-substrate scope.
    furniture:    [],
    dynamic:      _buildDynamic(geom, flipY),
  };
  // Hybrid substrate (architecture v51 lane): forward the painted
  // substrate path so Tier1aBody can render it via L_SubstrateImage and
  // skip the procedural district/building/street/furniture layers. The
  // server omits this key for procedural areas; only forward when set.
  if (geom.substrate_image) {
    out.substrate_image = geom.substrate_image;
  }
  return out;
}

// ─── regionKeyForArea (Drop 4.15b) ───────────────────────────────────
// Map a live area-geometry payload (or a bare slug) to the wilderness
// region key consumed by M3TierWildernessBody at tier '1b'. Returns the
// normalized slug for a *known wilderness region* (e.g. 'coruscant_-
// underworld', 'tatooine_dune_sea'), or null for city/interior areas and
// unknown keys.
//
// Source-of-truth for "is this a wilderness region" is the wilderness
// body's own registry (M3TierWildernessBody.resolveRegion) — this helper
// does not maintain a second list. It reads, in priority order:
//   geom.region_key            (explicit, if the server emits one)
//   geom.wilderness_region_id   (server field set on wilderness rooms —
//                                see server/session.py; == region.slug)
//   geom.area_key               (fallback; equals the slug for wilderness
//                                areas whose area_key IS the region slug)
//
// Until the server emits a clean region field in the area payload, callers
// can pass whichever of the above is available; this stays correct because
// the final guard is resolveRegion(), which only accepts real region slugs.
function regionKeyForArea(geomOrKey) {
  if (!geomOrKey) return null;
  var key;
  if (typeof geomOrKey === 'string') {
    key = geomOrKey;
  } else {
    key = geomOrKey.region_key ||
          geomOrKey.wilderness_region_id ||
          geomOrKey.area_key || null;
  }
  if (!key) return null;
  var W = (typeof window !== 'undefined') && window.M3TierWildernessBody;
  if (W && typeof W.resolveRegion === 'function') {
    // resolveRegion returns the region descriptor (or null) for a known
    // slug/alias; only then is it a wilderness region we can render.
    if (W.resolveRegion(key)) return String(key).toLowerCase();
    return null;
  }
  // Wilderness body not loaded — cannot validate; be conservative.
  return null;
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3Adapter = {
  SCHEMA_VERSION:    SCHEMA_VERSION,
  fromAreaGeometry:  fromAreaGeometry,
  regionKeyForArea:  regionKeyForArea,
  _internal: {
    _translateRoom:                     _translateRoom,
    _translateDistrict:                 _translateDistrict,
    _translateStreets:                  _translateStreets,
    _translateLandmarksToPoi:           _translateLandmarksToPoi,
    _translateLandmarksToTopLevel:      _translateLandmarksToTopLevel,
    _translateLabelsToLandmarks:        _translateLabelsToLandmarks,
    _buildStreetLabelIndexFromLabels:   _buildStreetLabelIndexFromLabels,
    _buildSecurityIndexFromAreaMap:     _buildSecurityIndexFromAreaMap,
    _buildDynamic:                      _buildDynamic,
  },
};

})();
