/* ─────────────────────────────────────────────────────────────────────
   map_view.js — vanilla-JS port of the React-prototype MapView.

   Drop F.MAP.1 (Tier 1 #4, Step 1 of map redesign implementation).

   Sourced from design_handoff_datapad_map/reference/map-view.jsx
   (the prototype) and ported to vanilla DOM/SVG so it can ship in
   client.html without dragging in React 18 + Babel-standalone (~3MB
   CDN weight). The bundle README explicitly invites this:

       "The task is to recreate these designs in the SW_MUSH client
        codebase using its established patterns and libraries."

   Z-order (architecture v41 §4.15 — DON'T REORDER):
     substrate → districts → street ribbons → exit paths → rooms →
     landmarks → labels → contacts → player

   Coordinate system: world units, Y-UP. The renderer flips at the
   world <g> via scale(1, -1) so SVG draws correctly while data
   stays Y-up.

   Public API:
     window.MapView.MAP_TOKENS            — base palette constants
     window.MapView.PALETTES              — per-area palette overlays
     window.MapView.STYLE_TAGS            — room-style → glyph tint/weight
     window.MapView.render(svg, geom, opts)
       svg:  <svg> element to render INTO (will be cleared first)
       geom: AreaGeometry dict (loaded from server or static fixture)
       opts: {
         viewBox: [x, y, w, h]   // required; world rect to show
         zoomTier: 1              // 0 site · 1 district · 2 city · 3 planet
         showSubstrate: true
         showDistrictFills: true
         showDistrictLabels: true
         showRooms: "full"        // "full" | "dot" | "dot+player" | "hide"
         showExits: true
         showLabels: true
         showLandmarks: true
         showMarkers: true
         pulse: true              // SVG <animate> on player marker
         width: 600, height: 600  // CSS px, sets viewport
       }

   Seam discipline (architecture v41 §4.5): this renderer is loaded
   but NOT YET wired into the live game. The legacy renderAreaMap()
   in client.html keeps running. This module is exercised only via
   the standalone preview page (static/map_v2_preview.html) until
   the wire-up drop lands.
   ───────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  // ── Tokens ────────────────────────────────────────────────────────
  // Mirror of design_handoff_datapad_map/reference/tokens.js.
  // Kept in sync verbatim with the prototype — palette tweaks made
  // here MUST be ported back to the prototype to keep the design
  // handoff and the production renderer aligned.

  var MAP_TOKENS = {
    font: {
      mono: "'IBM Plex Mono', 'Berkeley Mono', Menlo, Consolas, monospace",
      sans: "'IBM Plex Sans', 'Inter', system-ui, sans-serif",
    },
    hud: {
      bg:        "#04141a",
      bgDeep:    "#020a0e",
      panel:     "#07181f",
      line:      "#0f2a33",
      lineMid:   "#163844",
      cyan:      "#6ee8ff",
      cyanDim:   "#2e7080",
      cyanGhost: "#143540",
      amber:     "#ffa640",
      amberDim:  "#a86c20",
      red:       "#ff5a4a",
      redDim:    "#7a261e",
      text:      "#cfe9f0",
      textDim:   "#5e8590",
    },
    marker: {
      self:        "#6ee8ff",
      pc:          "#6ee8ff",
      npcFriend:   "#ffa640",
      npcHostile:  "#ff5a4a",
      npcNeutral:  "#7a8a90",
    },
    pathStyle: {
      street:   { color: "#7a6a52", width: 0.18, dash: null },
      alley:    { color: "#5a4d3a", width: 0.10, dash: null },
      road:     { color: "#86755a", width: 0.14, dash: null },
      trail:    { color: "#5d4a30", width: 0.06, dash: "0.18 0.12" },
      corridor: { color: "#3d525a", width: 0.12, dash: null },
    },
  };

  var PALETTES = {
    tatooine: {
      name: "TATOOINE · sand-bleached duracrete",
      sky: "#0c0805", void: "#070503",
      sand: "#2a1f12", sandLit: "#5a4528", duracrete: "#2a2218",
      streetSurface: "#8a6e42", streetShoulder: "#4a3820",
      streetLabel: "#1a1208", labelHalo: "#a8895a",
      districtFill: "rgba(216, 176, 112, 0.07)",
      districtBorder: "rgba(255, 166, 64, 0.35)",
      districtBorderDash: "0.5 0.3",
      districtLabel: "#a87a3c",
      accent: "#ffa640", accentDim: "#a86c20",
      secondary: "#6ee8ff",
      roomFill: "#0e0a05", roomStroke: "#7a5a30", roomActive: "#ffa640",
      suns: "#ffd089",
    },
    coruscant_senate: {
      name: "CORUSCANT · Senate District",
      sky: "#06090e", void: "#02050a",
      sand: "#0a121a", sandLit: "#1d2c38", duracrete: "#0d1620",
      streetSurface: "#3a5870", streetShoulder: "#1a2a38",
      streetLabel: "#e8f4ff", labelHalo: "#243f55",
      districtFill: "rgba(140, 200, 255, 0.06)",
      districtBorder: "rgba(110, 232, 255, 0.45)",
      districtBorderDash: null,
      districtLabel: "#aac9d8",
      accent: "#6ee8ff", accentDim: "#2e7080",
      secondary: "#dfeaff",
      roomFill: "#0a1620", roomStroke: "#2a4858", roomActive: "#6ee8ff",
      suns: "#ffffff",
    },
  };

  var STYLE_TAGS = {
    dock:       { tint: "#ffa640", weight: 600 },
    cantina:    { tint: "#ff8a3a", weight: 600 },
    vendor:     { tint: "#d8b070", weight: 500 },
    market:     { tint: "#d8b070", weight: 500 },
    housing:    { tint: "#a89878", weight: 400 },
    civic:      { tint: "#9ab8c4", weight: 500 },
    medical:    { tint: "#6ee8ff", weight: 600 },
    temple:     { tint: "#c4a060", weight: 500 },
    hutt:       { tint: "#a8c068", weight: 600 },
    street:     { tint: "#6a5a40", weight: 300 },
    gate:       { tint: "#ffa640", weight: 600 },
    ruin:       { tint: "#7a6a52", weight: 400 },
    landmark:   { tint: "#ffd089", weight: 600 },
    wilderness: { tint: "#7a5a30", weight: 400 },
    hostile:    { tint: "#ff5a4a", weight: 600 },
    hidden:     { tint: "#5a8a70", weight: 500 },
  };

  // Landmark icon glyphs (subset of the unicode set the prototype uses).
  var LM_GLYPHS = {
    wreck: "※", hutt: "H", cantina: "Λ", dock: "≡", ship: "◅",
    bones: "Ψ", palace: "♛", sarlacc: "◉", beacon: "◇",
  };

  // SVG namespace shorthand
  var NS = "http://www.w3.org/2000/svg";

  // ── DOM helpers ───────────────────────────────────────────────────

  function el(tag, attrs, parent) {
    var node = document.createElementNS(NS, tag);
    if (attrs) {
      for (var k in attrs) {
        if (attrs[k] === null || attrs[k] === undefined) continue;
        node.setAttribute(k, String(attrs[k]));
      }
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function pathD(pts) {
    if (!pts || pts.length === 0) return "";
    var s = "M" + pts[0][0] + " " + pts[0][1];
    for (var i = 1; i < pts.length; i++) {
      s += " L " + pts[i][0] + " " + pts[i][1];
    }
    return s;
  }

  function polyPoints(pts) {
    return pts.map(function (p) { return p[0] + "," + p[1]; }).join(" ");
  }

  // Random-ish stable id for <pattern>/<defs>. Each render call gets
  // its own id so two MapView instances on the same page don't collide.
  function genId() {
    return "mv-" + Math.floor(Math.random() * 1e9).toString(36);
  }

  // ── Substrate ─────────────────────────────────────────────────────
  // Sand pattern (grit dots) + dark scanline overlay.

  function renderSubstrate(parent, defs, palette, bounds, idPrefix) {
    var gritId = idPrefix + "-grit";
    var scanId = idPrefix + "-scan";

    var gritPattern = el("pattern", {
      id: gritId, x: 0, y: 0, width: 0.4, height: 0.4,
      patternUnits: "userSpaceOnUse",
    }, defs);
    el("rect", { width: 0.4, height: 0.4, fill: palette.sand }, gritPattern);
    el("circle", { cx: 0.08, cy: 0.12, r: 0.012, fill: palette.sandLit, opacity: 0.5 }, gritPattern);
    el("circle", { cx: 0.32, cy: 0.28, r: 0.010, fill: palette.sandLit, opacity: 0.4 }, gritPattern);
    el("circle", { cx: 0.20, cy: 0.36, r: 0.008, fill: palette.sandLit, opacity: 0.3 }, gritPattern);

    var scanPattern = el("pattern", {
      id: scanId, x: 0, y: 0, width: 1, height: 0.06,
      patternUnits: "userSpaceOnUse",
    }, defs);
    el("rect", { width: 1, height: 0.06, fill: "transparent" }, scanPattern);
    el("rect", { width: 1, height: 0.012, fill: "#000", opacity: 0.18 }, scanPattern);

    var w = bounds.x_max - bounds.x_min;
    var h = bounds.y_max - bounds.y_min;
    el("rect", {
      x: bounds.x_min, y: bounds.y_min,
      width: w, height: h, fill: "url(#" + gritId + ")",
    }, parent);
    el("rect", {
      x: bounds.x_min, y: bounds.y_min,
      width: w, height: h, fill: "url(#" + scanId + ")",
    }, parent);
  }

  // ── Districts ─────────────────────────────────────────────────────

  function renderDistricts(parent, districts, palette, opts) {
    var g = el("g", null, parent);
    if (opts.showFills) {
      for (var i = 0; i < districts.length; i++) {
        var d = districts[i];
        el("polygon", {
          points: polyPoints(d.polygon),
          fill: palette.districtFill,
          stroke: palette.districtBorder,
          "stroke-width": 0.04,
          "stroke-dasharray": palette.districtBorderDash || null,
          "vector-effect": "non-scaling-stroke",
        }, g);
      }
    }
    if (opts.showLabels) {
      for (var j = 0; j < districts.length; j++) {
        var dd = districts[j];
        var lx = dd.label_anchor[0], ly = dd.label_anchor[1];
        var rot = dd.rotation || 0;
        var labelG = el("g", {
          transform: "translate(" + lx + " " + ly + ") scale(1 -1) rotate(" + rot + ")",
        }, g);
        // halo
        var haloT = el("text", {
          "text-anchor": "middle", "dominant-baseline": "middle",
          "font-family": MAP_TOKENS.font.mono,
          "font-size": 0.34, "letter-spacing": 0.06,
          stroke: palette.sand, "stroke-width": 0.16,
          "stroke-linejoin": "round", "stroke-opacity": 0.85,
          fill: "none", "paint-order": "stroke fill",
          "vector-effect": "non-scaling-stroke",
        }, labelG);
        haloT.style.textTransform = "uppercase";
        haloT.textContent = dd.name;
        // fill
        var t = el("text", {
          "text-anchor": "middle", "dominant-baseline": "middle",
          "font-family": MAP_TOKENS.font.mono,
          "font-size": 0.34, "letter-spacing": 0.06,
          fill: palette.districtLabel, opacity: 0.78,
        }, labelG);
        t.style.textTransform = "uppercase";
        t.textContent = dd.name;
      }
    }
  }

  // ── Street Ribbons ────────────────────────────────────────────────
  // Three passes per ribbon: shoulder (wider/darker) → surface (the
  // road) → centerline (thin dashed). Streets/roads only get a
  // centerline; trails/alleys skip it.

  var RIBBON_W = { street: 0.90, road: 0.65, alley: 0.40, trail: 0.22 };

  function renderStreetRibbons(parent, exit_paths, palette) {
    if (!exit_paths) return;
    var g = el("g", null, parent);
    var surface = palette.streetSurface || palette.sandLit || "#5a4528";
    var shoulder = palette.streetShoulder || palette.sand || "#3a2c1a";
    var entries = Object.keys(exit_paths).map(function (k) {
      return [k, exit_paths[k]];
    });

    // shoulder pass
    for (var i = 0; i < entries.length; i++) {
      var k = entries[i][0], p = entries[i][1];
      var w = (RIBBON_W[p.kind] || 0.30) + 0.10;
      el("path", {
        d: pathD(p.path), stroke: shoulder, "stroke-width": w,
        "stroke-linecap": "round", "stroke-linejoin": "round",
        fill: "none", opacity: 0.7,
        "vector-effect": "non-scaling-stroke",
      }, g);
    }
    // surface pass
    for (var j = 0; j < entries.length; j++) {
      var k2 = entries[j][0], p2 = entries[j][1];
      var w2 = RIBBON_W[p2.kind] || 0.30;
      el("path", {
        d: pathD(p2.path), stroke: surface, "stroke-width": w2,
        "stroke-linecap": "round", "stroke-linejoin": "round",
        fill: "none",
        "vector-effect": "non-scaling-stroke",
      }, g);
    }
    // centerline (street + road only)
    for (var m = 0; m < entries.length; m++) {
      var k3 = entries[m][0], p3 = entries[m][1];
      if (p3.kind !== "street" && p3.kind !== "road") continue;
      el("path", {
        d: pathD(p3.path),
        stroke: palette.accentDim || "#a86c20",
        "stroke-width": 0.018,
        "stroke-dasharray": "0.18 0.14",
        fill: "none", opacity: 0.55,
        "vector-effect": "non-scaling-stroke",
      }, g);
    }
  }

  // ── Plain (non-ribbon) exits — straight lines between rooms ───────

  function renderExitLines(parent, rooms, exits, exit_paths) {
    var byId = {};
    for (var i = 0; i < rooms.length; i++) byId[rooms[i].id] = rooms[i];
    var g = el("g", null, parent);
    for (var k = 0; k < exits.length; k++) {
      var e = exits[k];
      var isObj = !Array.isArray(e);
      var a = isObj ? e.from : e[0];
      var b = isObj ? e.to : e[1];
      var hidden = isObj && !!e.hidden;
      var ra = byId[a], rb = byId[b];
      if (!ra || !rb) continue;
      // If a path exists for this pair, the ribbon already drew it.
      var key1 = a + "-" + b, key2 = b + "-" + a;
      if (exit_paths[key1] || exit_paths[key2]) continue;
      el("line", {
        x1: ra.x, y1: ra.y, x2: rb.x, y2: rb.y,
        stroke: hidden ? "#5a8a70" : "#3a2c1a",
        "stroke-width": 0.04,
        "stroke-dasharray": hidden ? "0.1 0.08" : null,
        "vector-effect": "non-scaling-stroke",
        opacity: hidden ? 0.45 : 0.65,
      }, g);
    }
  }

  // ── Rooms ─────────────────────────────────────────────────────────

  function renderRooms(parent, rooms, palette, mode, playerRoomId, onClickRoom) {
    if (mode === "hide") return;
    var g = el("g", null, parent);
    for (var i = 0; i < rooms.length; i++) {
      var r = rooms[i];
      var tag = STYLE_TAGS[r.style] || STYLE_TAGS.street;
      var isMe = r.id === playerRoomId;

      // mode "dot" → dot for everyone; "dot+player" → dot for everyone EXCEPT player
      if (mode === "dot" || (mode === "dot+player" && !isMe)) {
        var dot = el("circle", {
          cx: r.x, cy: r.y, r: 0.10,
          fill: tag.tint, opacity: 0.85,
          stroke: palette.roomStroke, "stroke-width": 0.02,
          "vector-effect": "non-scaling-stroke",
          "data-room-id": r.id,
        }, g);
        if (onClickRoom) {
          dot.style.cursor = "pointer";
          dot.addEventListener("click", makeClickHandler(onClickRoom, r.id));
        }
        continue;
      }

      // full mode: footprint + glyph
      var roomG = el("g", { "data-room-id": r.id }, g);
      el("rect", {
        x: r.x - r.w / 2, y: r.y - r.h / 2,
        width: r.w, height: r.h,
        fill: palette.roomFill,
        stroke: isMe ? palette.roomActive : palette.roomStroke,
        "stroke-width": isMe ? 0.06 : 0.025,
        "vector-effect": "non-scaling-stroke",
        rx: 0.04,
      }, roomG);
      var glyphG = el("g", {
        transform: "translate(" + r.x + " " + r.y + ") scale(1 -1)",
      }, roomG);
      var glyphSize = Math.min(r.w, r.h) * 0.55;
      var glyph = el("text", {
        "text-anchor": "middle", "dominant-baseline": "central",
        "font-family": MAP_TOKENS.font.mono,
        "font-size": glyphSize,
        fill: tag.tint, "font-weight": tag.weight,
      }, glyphG);
      glyph.textContent = r.symbol;
      if (onClickRoom) {
        roomG.style.cursor = "pointer";
        roomG.addEventListener("click", makeClickHandler(onClickRoom, r.id));
      }
    }
  }

  function makeClickHandler(handler, roomId) {
    return function (ev) {
      ev.stopPropagation();
      handler(roomId);
    };
  }

  // ── Landmarks ─────────────────────────────────────────────────────

  function renderLandmarks(parent, landmarks, zoomTier, palette) {
    var g = el("g", null, parent);
    for (var i = 0; i < landmarks.length; i++) {
      var lm = landmarks[i];
      if (zoomTier < lm.min_zoom || zoomTier > lm.max_zoom) continue;
      var lmg = el("g", {
        transform: "translate(" + lm.pos[0] + " " + lm.pos[1] + ")",
      }, g);
      el("circle", {
        r: 0.22, fill: MAP_TOKENS.hud.bgDeep,
        stroke: palette.accent, "stroke-width": 0.04,
        "vector-effect": "non-scaling-stroke",
      }, lmg);
      var glyphG = el("g", { transform: "scale(1 -1)" }, lmg);
      var t = el("text", {
        "text-anchor": "middle", "dominant-baseline": "central",
        "font-family": MAP_TOKENS.font.mono, "font-size": 0.26,
        fill: palette.accent, "font-weight": 600,
      }, glyphG);
      t.textContent = LM_GLYPHS[lm.icon] || "•";
    }
  }

  // ── Label utilities ───────────────────────────────────────────────

  // Walk a polyline; return point + tangent angle at fractional length t∈[0,1].
  function pointAlongPolyline(pts, t) {
    if (!pts || pts.length < 2) return null;
    var segs = [], total = 0;
    for (var i = 0; i < pts.length - 1; i++) {
      var dx = pts[i + 1][0] - pts[i][0];
      var dy = pts[i + 1][1] - pts[i][1];
      var len = Math.hypot(dx, dy);
      segs.push({ a: pts[i], b: pts[i + 1], len: len, dx: dx, dy: dy });
      total += len;
    }
    if (total === 0) {
      return { x: pts[0][0], y: pts[0][1], angleDeg: 0, pathLen: 0 };
    }
    var target = Math.max(0, Math.min(1, t)) * total;
    for (var s = 0; s < segs.length; s++) {
      var seg = segs[s];
      if (target <= seg.len || s === segs.length - 1) {
        var k = seg.len === 0 ? 0 : target / seg.len;
        var x = seg.a[0] + seg.dx * k;
        var y = seg.a[1] + seg.dy * k;
        var ang = Math.atan2(seg.dy, seg.dx) * 180 / Math.PI;
        return { x: x, y: y, angleDeg: ang, pathLen: total };
      }
      target -= seg.len;
    }
    return null;
  }

  function resolveLabelAnchor(label, geom) {
    if (label.path_id) {
      var ep = geom.exit_paths && geom.exit_paths[label.path_id];
      if (ep && ep.path) {
        var p = pointAlongPolyline(ep.path, label.t == null ? 0.5 : label.t);
        if (p) return p;
      }
    }
    if (label.between) {
      var byId = {};
      for (var i = 0; i < geom.rooms.length; i++) byId[geom.rooms[i].id] = geom.rooms[i];
      var a = byId[label.between[0]], b = byId[label.between[1]];
      if (a && b) {
        var p2 = pointAlongPolyline([[a.x, a.y], [b.x, b.y]],
          label.t == null ? 0.5 : label.t);
        if (p2) return p2;
      }
    }
    if (label.pos) {
      return { x: label.pos[0], y: label.pos[1], angleDeg: label.rot || 0 };
    }
    return null;
  }

  // ── Single label (with halo, fit-to-length, perpendicular offset) ─

  function renderLabel(parent, label, anchor, palette) {
    var x = anchor.x, y = anchor.y;
    var angleDeg = anchor.angleDeg, pathLen = anchor.pathLen || 0;
    var isStreet  = label.kind === "street";
    var isFlavor  = label.kind === "flavor";
    var isWarning = label.kind === "warning";

    // Flip text the right way up if road runs roughly right→left.
    var flipped = false;
    if (angleDeg > 90)  { angleDeg -= 180; flipped = true; }
    if (angleDeg < -90) { angleDeg += 180; flipped = true; }

    // Perpendicular offset
    var side = ((label.side != null ? label.side : 0)) * (flipped ? -1 : 1);
    var offset = label.offset != null ? label.offset : 0;
    var rad = angleDeg * Math.PI / 180;
    var ox = -Math.sin(rad) * offset * side;
    var oy =  Math.cos(rad) * offset * side;
    x += ox; y += oy;

    // Type spec
    var sz = (label.size != null ? label.size : 8) / 22;
    var isAllCaps = isStreet && /[A-Z]{3,}/.test(label.text);
    var tracking = isStreet
      ? (isAllCaps ? sz * 0.18 : sz * 0.06)
      : sz * 0.04;

    // Fit-to-length: shrink if approx width > path length × 0.98
    if (isStreet && pathLen) {
      var charAdvance = sz * 0.60 + tracking;
      var approxW = label.text.length * charAdvance;
      var cap = pathLen * 0.98;
      if (approxW > cap) {
        var k = cap / approxW;
        sz *= k; tracking *= k;
      }
      // Cap by ribbon width too
      var ribbonW = label.kind === "street" ? 0.90 : 0.65;
      var maxSz = ribbonW * 0.75;
      if (sz > maxSz) {
        var k2 = maxSz / sz;
        sz *= k2; tracking *= k2;
      }
    }

    var weight = label.weight || (isStreet && isAllCaps ? 500 : 400);
    var fill = isWarning ? MAP_TOKENS.hud.red
             : isFlavor  ? "#7a8a90"
             : (palette.streetLabel || palette.districtLabel);
    var opacity = isFlavor ? 0.7 : 0.95;
    var fontStyle = isFlavor ? "italic" : "normal";
    var halo = palette.labelHalo
            || (isStreet ? (palette.sandLit || "#5a4528")
                         : (palette.sand || "#3a2c1a"));

    var labG = el("g", {
      transform: "translate(" + x + " " + y + ") scale(1 -1) rotate(" + (-angleDeg) + ")",
    }, parent);
    var halotxt = el("text", {
      "text-anchor": "middle", "dominant-baseline": "middle",
      "font-family": MAP_TOKENS.font.mono,
      "font-size": sz, "font-weight": weight,
      "font-style": fontStyle, "letter-spacing": tracking,
      stroke: halo, "stroke-width": sz * 0.55,
      "stroke-linejoin": "round", "stroke-opacity": 0.95,
      fill: halo, "fill-opacity": 0.95,
      "paint-order": "stroke fill",
      "vector-effect": "non-scaling-stroke",
    }, labG);
    halotxt.textContent = label.text;
    var fillT = el("text", {
      "text-anchor": "middle", "dominant-baseline": "middle",
      "font-family": MAP_TOKENS.font.mono,
      "font-size": sz, "font-weight": weight,
      "font-style": fontStyle, "letter-spacing": tracking,
      fill: fill, "fill-opacity": opacity,
    }, labG);
    fillT.textContent = label.text;
  }

  // ── Labels (filtered by zoomTier visibility) ──────────────────────

  function renderLabels(parent, labels, zoomTier, palette, geom) {
    var g = el("g", null, parent);
    for (var i = 0; i < labels.length; i++) {
      var l = labels[i];
      var minZ = l.min_zoom != null ? l.min_zoom : 0;
      var maxZ = l.max_zoom != null ? l.max_zoom : 99;
      if (zoomTier < minZ || zoomTier > maxZ) continue;
      var anchor = resolveLabelAnchor(l, geom);
      if (!anchor) continue;
      renderLabel(g, l, anchor, palette);
    }
  }

  // ── Markers (player + contacts) ───────────────────────────────────

  function renderMarkers(parent, player, contacts, palette, scale, pulse) {
    var k = 1 / scale;
    var g = el("g", null, parent);

    // Contacts first, player on top
    for (var i = 0; i < contacts.length; i++) {
      var c = contacts[i];
      var color =
        c.kind === "pc" ? MAP_TOKENS.marker.pc :
        c.kind === "npc_friend" ? MAP_TOKENS.marker.npcFriend :
        c.kind === "npc_hostile" ? MAP_TOKENS.marker.npcHostile :
        MAP_TOKENS.marker.npcNeutral;

      var cg = el("g", {
        transform: "translate(" + c.x + " " + c.y + ")",
      }, g);
      if (c.kind === "npc_hostile") {
        el("polygon", {
          points: "0,-0.16 0.14,0.10 -0.14,0.10",
          fill: color, stroke: "#000", "stroke-width": 0.02,
          transform: "scale(" + k + ")",
        }, cg);
      } else if (c.kind === "pc") {
        var inner = el("g", { transform: "scale(" + k + ")" }, cg);
        el("polygon", {
          points: "0,-0.18 0.14,0.10 0,0.04 -0.14,0.10",
          fill: color, stroke: "#04141a", "stroke-width": 0.02,
        }, inner);
      } else {
        el("circle", {
          r: 0.10, fill: color,
          stroke: "#000", "stroke-width": 0.02,
          transform: "scale(" + k + ")",
        }, cg);
      }
    }

    // Player on top
    if (!player) return;
    var pg = el("g", {
      transform: "translate(" + player.x + " " + player.y + ")",
    }, g);
    var inner2 = el("g", { transform: "scale(" + k + ")" }, pg);
    var pulseRing = el("circle", {
      r: 0.40, fill: "none",
      stroke: MAP_TOKENS.marker.self,
      "stroke-width": 0.025, opacity: 0.45,
    }, inner2);
    if (pulse) {
      var a1 = el("animate", {
        attributeName: "r",
        values: "0.32;0.50;0.32",
        dur: "2.4s",
        repeatCount: "indefinite",
      }, pulseRing);
      var a2 = el("animate", {
        attributeName: "opacity",
        values: "0.55;0.05;0.55",
        dur: "2.4s",
        repeatCount: "indefinite",
      }, pulseRing);
      // Suppress unused-var lint
      void a1; void a2;
    }
    el("circle", {
      r: 0.22, fill: "none",
      stroke: MAP_TOKENS.marker.self, "stroke-width": 0.04,
    }, inner2);
    el("polygon", {
      points: "0,-0.20 0.16,0.12 0,0.04 -0.16,0.12",
      fill: MAP_TOKENS.marker.self,
      stroke: "#04141a", "stroke-width": 0.025,
    }, inner2);
  }

  // ── Top-level render ──────────────────────────────────────────────

  function render(svg, geom, opts) {
    if (!svg || !geom) return;
    opts = opts || {};
    var viewBox = opts.viewBox || [
      geom.bounds.x_min, geom.bounds.y_min,
      geom.bounds.x_max - geom.bounds.x_min,
      geom.bounds.y_max - geom.bounds.y_min,
    ];
    var zoomTier = opts.zoomTier == null ? 1 : opts.zoomTier;
    var showSubstrate     = opts.showSubstrate     !== false;
    var showDistrictFills = opts.showDistrictFills !== false;
    var showDistrictLabels= opts.showDistrictLabels!== false;
    var showRooms         = opts.showRooms || "full";
    var showExits         = opts.showExits         !== false;
    var showLabels        = opts.showLabels        !== false;
    var showLandmarks     = opts.showLandmarks     !== false;
    var showMarkers       = opts.showMarkers       !== false;
    var pulse             = opts.pulse             !== false;
    var width             = opts.width  || 600;
    var height            = opts.height || 600;
    var palette           = opts.palette
                         || PALETTES[geom.palette]
                         || PALETTES.tatooine;

    var vx = viewBox[0], vy = viewBox[1], vw = viewBox[2], vh = viewBox[3];
    var scale = Math.min(width / vw, height / vh);

    // Reset the SVG
    clear(svg);
    svg.setAttribute("viewBox", vx + " " + vy + " " + vw + " " + vh);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    if (opts.width)  svg.setAttribute("width",  width);
    if (opts.height) svg.setAttribute("height", height);
    svg.style.background = palette.sky;
    svg.style.display = "block";

    var idPrefix = genId();
    var defs = el("defs", null, svg);

    // World group: flip Y so world is Y-up
    var world = el("g", {
      transform: "translate(0 " + (vy * 2 + vh) + ") scale(1 -1)",
    }, svg);

    if (showSubstrate) {
      renderSubstrate(world, defs, palette, geom.bounds, idPrefix);
    }
    renderDistricts(world, geom.districts, palette, {
      showFills: showDistrictFills,
      showLabels: showDistrictLabels && zoomTier >= 2,
    });
    if (showExits) {
      renderStreetRibbons(world, geom.exit_paths, palette);
      renderExitLines(world, geom.rooms, geom.exits, geom.exit_paths || {});
    }
    var playerRoomId = (geom.player && geom.player.room_id) || null;
    renderRooms(world, geom.rooms, palette, showRooms, playerRoomId, opts.onClickRoom);
    if (showLandmarks) {
      // Pass merged palette so the landmark circle uses bgDeep from MAP_TOKENS.hud
      var mergedPal = {};
      for (var pk in palette) mergedPal[pk] = palette[pk];
      for (var hk in MAP_TOKENS.hud) {
        if (mergedPal[hk] === undefined) mergedPal[hk] = MAP_TOKENS.hud[hk];
      }
      renderLandmarks(world, geom.landmarks, zoomTier, mergedPal);
    }
    if (showLabels) {
      renderLabels(world, geom.labels, zoomTier, palette, geom);
    }
    if (showMarkers) {
      renderMarkers(world,
        geom.player || { x: 0, y: 0, room_id: null },
        geom.contacts || [],
        palette, scale, pulse);
    }
  }

  // Expose
  window.MapView = {
    MAP_TOKENS: MAP_TOKENS,
    PALETTES: PALETTES,
    STYLE_TAGS: STYLE_TAGS,
    LM_GLYPHS: LM_GLYPHS,
    render: render,
    // Expose helpers for the preview page (and future tests):
    _internal: {
      pointAlongPolyline: pointAlongPolyline,
      resolveLabelAnchor: resolveLabelAnchor,
    },
  };
})();
