#!/usr/bin/env python3
"""
gen_wilderness_overview.py — generate a FAITHFUL Tier-1b overview spec from
the real, navigable wilderness region data (Drop 4.17).

WHY THIS EXISTS
---------------
The Tier-1b wilderness overview must be a navigation aid, not decoration.
Wilderness movement is a coordinate grid (engine/wilderness_movement.py):
x = column (0 west … width-1 east), y = row (0 south … height-1 north),
and **north is computed as y+1** — a deterministic delta, not a hand-authored
exit label. So the overview is only honest if its POIs sit where the real
landmarks actually are on that grid.

The 4.15a/4.16 overview was hand-authored decorative data (a moisture farm,
sarlacc pit, bantha herd, etc.) that does NOT exist in the real grid — a
player navigating by it would be lost. This tool replaces that hand-authoring:
it reads the region YAML (+ its landmark_includes), takes the real landmark
ids and grid coordinates as GROUND TRUTH, and PROJECTS them north-up into the
700x600 overview space. The overview therefore cannot drift from the grid —
the single-source fix MAP_PLAN.md §6.4 called for.

WHAT IT EMITS (both from the same projection, so they cannot disagree)
----------------------------------------------------------------------
  1. data/worlds/clone_wars/maps/<slug>_overview.yaml
       — seed + registration source (consumed by make_substrate_seed.py
         --wilderness and make_register_manifest.py).
  2. static/spa/m3_wilderness_overview_data.js
       — the live Tier-1b region objects (consumed by
         m3_tier_wilderness_body.js · resolveRegion, which prefers this
         generated data over its built-in showcase fixtures).

COORDINATE CONVENTION (the crux — seed and renderer MUST agree)
---------------------------------------------------------------
Overview space is SVG-style: origin top-left, x→right, y→DOWN. NORTH is the
TOP of the screen. So a northern landmark (high grid y) projects to a LOW
overview y. Both the renderer (draws POIs at SVG (x,y)) and the seed tool
(after the Drop 4.17 no-flip fix) read overview pos in this same space, so a
landmark lands in the same spot in the seed, the painting, and the live map.

    ox = grid_x / (grid_w - 1) * 700                 # west→east, left→right
    oy = (grid_h - 1 - grid_y) / (grid_h - 1) * 600  # north(high y)→top(low oy)

CLUSTER COLLAPSE
----------------
The Jedi village is ~9 rooms packed into a 7x5-tile corner; at overview scale
those pins overlap into mush. Landmarks in a recognised cluster (the village)
collapse to ONE representative POI at the cluster centroid, and adjacency
edges into the cluster remap to that node (self-loops dropped). This is the
only collapse; every other landmark is shown individually.

TERRAIN ZONES ARE LEFT EMPTY (deliberately)
-------------------------------------------
The grid has per-tile terrain but no authored terrain *regions*; inventing
broad zones was the original drift. So terrain_zones is emitted empty —
terrain atmosphere comes from the Nano {GEOGRAPHY} prompt, while POSITIONS
(POIs/routes) come faithfully from the grid. The seed shows real positions;
the prompt paints the terrain.

USAGE
-----
    python3 tools/gen_wilderness_overview.py \
        data/worlds/clone_wars/wilderness/dune_sea.yaml \
        data/worlds/clone_wars/wilderness/coruscant_underworld.yaml

Re-run after painting (saving static/maps/<slug>_substrate.png): the
substrate_image key auto-engages because the generator checks the PNG's
presence on disk. Pins stay grid-faithful — do NOT drag pins in
map_register.html to match a reflowed painting (that would re-introduce
drift); registration is verification-only for wilderness.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paint_brief_common as pbc   # noqa: E402

OVERVIEW_W = 700
OVERVIEW_H = 600

# terrain id → painterly ground noun for the {GEOGRAPHY} texture line
TERRAIN_PAINT = {
    "dune": "open rolling sand dunes",
    "rocky_outcrop": "broken rocky outcrops and weathered stone",
    "ruins": "weathered ancient ruins",
    "village_interior": "packed-earth settlement ground",
    "ferrocrete_corridor": "grey ferrocrete corridors and tenement strata",
    "abandoned_plaza": "hollow derelict plazas",
    "industrial_ruin": "ruined factory ductwork",
    "service_tunnel": "cramped service tunnels and pipework",
    "bottom_dark": "lightless sump at the lowest level",
}

# Presentation layer (NOT in the gameplay YAML): biome strings, base tones,
# breadcrumbs. Positions are derived from the grid; only the chrome lives here.
PRESENTATION = {
    "tatooine_dune_sea": {
        "display_name": "Dune Sea (Tatooine)",
        "biome": "TATOOINE \u00b7 OUTER RIM \u00b7 ARID",
        "base_tone": [38, 33, 26],
        "bg": None,
        "breadcrumb": "GALAXY \u25b8 OUTER RIM \u25b8 TATOOINE \u25b8 DUNE SEA",
        "tier_label": "1B \u00b7 WILDERNESS",
    },
    "coruscant_underworld": {
        "display_name": "Coruscant Underworld",
        "biome": "GALACTIC CORE \u00b7 UNDERLEVELS",
        "base_tone": [10, 11, 14],
        "bg": "#070809",
        "breadcrumb": "GALAXY \u25b8 CORE \u25b8 CORUSCANT \u25b8 UNDERWORLD",
        "tier_label": "1B \u00b7 WILDERNESS",
    },
}
_DEFAULT_PRESENTATION = {
    "display_name": None, "biome": "WILDERNESS", "base_tone": [22, 22, 26],
    "bg": None, "breadcrumb": "GALAXY \u25b8 WILDERNESS", "tier_label": "1B \u00b7 WILDERNESS",
}

# id-keyword → distinctive icon (checked first), then terrain → icon. Icons
# must be in make_register_manifest.DISTINCTIVE_ICONS to count as distinctive.
ICON_BY_IDHINT = [
    ("hideout", "hideout"), ("factory", "factory"), ("maze", "maze"),
    ("uscru", "shaft"), ("shaft", "shaft"), ("shrine", "spire"),
    ("obelisk", "spire"), ("stones", "spire"), ("hermit", "farm"),
    ("village", "tents"), ("camp", "tents"), ("farm", "farm"),
    ("pit", "pit"), ("sarlacc", "pit"),
]
ICON_BY_TERRAIN = {
    "ruins": "spire", "rocky_outcrop": "farm", "village_interior": "tents",
}
DISTINCTIVE_ICONS = {"dock", "ship", "wreck", "cantina", "bones", "palace",
                     "farm", "tents", "pit", "spire", "shaft", "factory",
                     "hideout", "maze"}

LEGEND_SPEC = [
    {"colorKey": "cyan",  "shape": "circle", "glow": True, "label": "YOU"},
    {"colorKey": "gold",  "shape": "circle",               "label": "LANDMARK"},
    {"colorKey": "amber", "shape": "circle",               "label": "REGION EXIT"},
    {"colorKey": "red",   "shape": "tri",                  "label": "HAZARD"},
]


def _is_cluster_member(lm: dict) -> bool:
    """The Jedi village: terrain village_interior or a village_* id."""
    return (lm.get("terrain") == "village_interior"
            or str(lm.get("id", "")).startswith("village_"))


def _pick_icon(lm: dict) -> str:
    lid = str(lm.get("id", "")).lower()
    for hint, icon in ICON_BY_IDHINT:
        if hint in lid:
            return icon
    return ICON_BY_TERRAIN.get(str(lm.get("terrain", "")), "beacon")


def _label_from_id(lid: str) -> str:
    # 'jundland_dune_sea_edge' → 'JUNDLAND DUNE SEA EDGE'; trims common noise.
    return lid.replace("_", " ").upper()


def load_roster(region_path: Path):
    """Return (region_slug, grid, [landmark dicts]) — the authoritative roster
    after merging landmark_includes (region-filtered), inline landmarks win."""
    raw = yaml.safe_load(region_path.read_text(encoding="utf-8"))
    region = raw.get("region") or {}
    slug = region.get("slug")
    if not slug:
        sys.exit(f"{region_path}: missing region.slug")
    grid = raw.get("grid") or {}
    if not grid.get("width") or not grid.get("height"):
        sys.exit(f"{region_path}: missing grid.width/height")

    roster: dict[str, dict] = {}
    for lm in (raw.get("landmarks") or []):
        if lm.get("id"):
            roster[lm["id"]] = dict(lm)

    base_dir = region_path.parent
    for inc in (raw.get("landmark_includes") or []):
        inc_path = base_dir / inc
        if not inc_path.exists():
            print(f"  ! include not found, skipping: {inc_path}", file=sys.stderr)
            continue
        inc_raw = yaml.safe_load(inc_path.read_text(encoding="utf-8")) or {}
        for lm in (inc_raw.get("landmarks") or []):
            lid = lm.get("id")
            if not lid:
                continue
            lm_region = lm.get("region") or lm.get("wilderness_region_id")
            # Region-tagged entries (e.g. force_resonant_landmarks.yaml) are
            # filtered to this region. Untagged entries in a region-specific
            # include are assumed to belong here.
            if lm_region and lm_region != slug:
                continue
            if lid in roster:
                for k, v in lm.items():
                    roster[lid].setdefault(k, v)   # enrich missing fields only
            else:
                roster[lid] = dict(lm)

    # Drop any landmark without usable coordinates (can't be placed).
    out = []
    for lm in roster.values():
        c = lm.get("coordinates")
        if isinstance(c, (list, tuple)) and len(c) == 2:
            out.append(lm)
        else:
            print(f"  ! {lm.get('id')}: no coordinates, skipping", file=sys.stderr)
    return slug, grid, out


def project(gx: float, gy: float, gw: int, gh: int,
            frame: tuple | None = None):
    """Grid (x east, y north) → overview (SVG x right, y DOWN; north at top).

    `frame` = (fx0, fy0, fx1, fy1) in grid units restricts the mapped window
    (fit-to-content). When None, the full 0..gw-1 / 0..gh-1 grid maps. Either
    way relative positions are preserved — fit-to-content is a faithful zoom,
    not a distortion."""
    if frame is None:
        fx0, fy0, fx1, fy1 = 0, 0, gw - 1, gh - 1
    else:
        fx0, fy0, fx1, fy1 = frame
    denom_x = max(1e-6, fx1 - fx0)
    denom_y = max(1e-6, fy1 - fy0)
    ox = (gx - fx0) / denom_x * OVERVIEW_W
    oy = (fy1 - gy) / denom_y * OVERVIEW_H   # north (high gy) → top (low oy)
    return round(ox, 1), round(oy, 1)


def _content_frame(coords: list, gw: int, gh: int,
                   pad_frac: float = 0.18, min_span: int = 6):
    """Bounding box of the real landmark coords, padded, clamped to the grid.
    Keeps the view faithful but reframes empty terrain out (so a corner-
    clustered region like the Dune Sea reads with the landmarks spread)."""
    if not coords:
        return (0, 0, gw - 1, gh - 1)
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    # enforce a minimum span so a tight cluster doesn't over-zoom
    if x1 - x0 < min_span:
        c = (x0 + x1) / 2; x0, x1 = c - min_span / 2, c + min_span / 2
    if y1 - y0 < min_span:
        c = (y0 + y1) / 2; y0, y1 = c - min_span / 2, c + min_span / 2
    padx = (x1 - x0) * pad_frac
    pady = (y1 - y0) * pad_frac
    x0, x1 = max(0, x0 - padx), min(gw - 1, x1 + padx)
    y0, y1 = max(0, y0 - pady), min(gh - 1, y1 + pady)
    return (round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2))


def build_overview(region_path: Path, maps_static: Path, fit: bool = True) -> dict:
    slug, grid, roster = load_roster(region_path)
    gw, gh = int(grid["width"]), int(grid["height"])
    raw = yaml.safe_load(region_path.read_text(encoding="utf-8"))

    pres = PRESENTATION.get(slug, dict(_DEFAULT_PRESENTATION))
    if not pres.get("display_name"):
        pres["display_name"] = (raw.get("region") or {}).get("name") or slug

    # Fit-to-content frame from the LANDMARKS (not edges — a region exit can
    # sit far across the empty grid and would stretch the frame, re-cramping
    # the landmarks). Edge markers are clamped into the resulting frame below.
    all_coords = [lm["coordinates"] for lm in roster
                  if isinstance(lm.get("coordinates"), (list, tuple))]
    frame = _content_frame(all_coords, gw, gh) if fit else None

    def proj(gx, gy):
        ox, oy = project(gx, gy, gw, gh, frame)
        return max(0.0, min(OVERVIEW_W, ox)), max(0.0, min(OVERVIEW_H, oy))

    # ── nodes: collapse the village cluster, keep everything else ──────────
    id_to_node: dict[str, str] = {}     # original id → node id (for routes)
    nodes: dict[str, dict] = {}         # node id → projected POI

    cluster_members = [lm for lm in roster if _is_cluster_member(lm)]
    cluster_node_id = None
    if cluster_members:
        cx = sum(lm["coordinates"][0] for lm in cluster_members) / len(cluster_members)
        cy = sum(lm["coordinates"][1] for lm in cluster_members) / len(cluster_members)
        ox, oy = proj(cx, cy)
        cluster_node_id = f"{slug}_village"
        # synthesize a village visual from the most central member's flavor
        rep = None
        for want in ("square", "common", "gate"):
            rep = next((m for m in cluster_members if want in m["id"]), None)
            if rep:
                break
        rep = rep or cluster_members[0]
        nodes[cluster_node_id] = {
            "id": cluster_node_id, "name": "THE HIDDEN VILLAGE",
            "icon": "tents", "distinctive": True, "kind": "landmark",
            "pos": [ox, oy],
            "_grid": [round(cx, 1), round(cy, 1)], "_collapsed": len(cluster_members),
            "_short_desc": "A small hidden settlement of mud-brick domes and "
                           "tents clustered around a hard-packed square",
            "_terrain": "village_interior",
        }
        for lm in cluster_members:
            id_to_node[lm["id"]] = cluster_node_id

    for lm in roster:
        if _is_cluster_member(lm):
            continue
        gx, gy = lm["coordinates"]
        ox, oy = proj(gx, gy)
        icon = _pick_icon(lm)
        props = lm.get("properties") or {}
        node = {
            "id": lm["id"],
            "name": (lm.get("name") or _label_from_id(lm["id"])).upper(),
            "icon": icon,
            "distinctive": icon in DISTINCTIVE_ICONS,
            "kind": "landmark",
            "pos": [ox, oy],
            "_grid": [gx, gy],
        }
        if props.get("force_resonant"):
            node["force_resonant"] = True
        node["_short_desc"] = (lm.get("short_desc") or "").strip()
        node["_description"] = (lm.get("description") or "").strip()
        node["_terrain"] = lm.get("terrain")
        nodes[lm["id"]] = node
        id_to_node[lm["id"]] = lm["id"]

    # ── region exits (edges block) as generic markers ─────────────────────
    for e in (raw.get("edges") or []):
        coords = e.get("coords")
        if not (isinstance(coords, (list, tuple)) and len(coords) == 2):
            continue
        ox, oy = proj(coords[0], coords[1])
        eid = "exit_" + str(e.get("room_slug") or f"{coords[0]}_{coords[1]}")
        nodes[eid] = {
            "id": eid,
            "name": _label_from_id(str(e.get("room_slug") or "REGION EXIT")),
            "icon": "beacon", "distinctive": False, "kind": "exit",
            "pos": [ox, oy], "_grid": [coords[0], coords[1]],
        }

    # ── routes from adjacency (remapped through the cluster) ───────────────
    edges = set()
    for lm in roster:
        a = id_to_node.get(lm["id"])
        if not a:
            continue
        for adj in (lm.get("adjacency") or []):
            b = id_to_node.get(adj)
            if not b or a == b:
                continue
            edges.add(frozenset((a, b)))
    routes = []
    for pair in edges:
        a, b = tuple(pair)
        if a in nodes and b in nodes:
            routes.append([nodes[a]["pos"], nodes[b]["pos"], False])

    # ── assemble ───────────────────────────────────────────────────────────
    node_list = list(nodes.values())
    substrate_png = maps_static / f"{slug}_substrate.png"
    substrate_rel = (f"/static/maps/{slug}_substrate.png"
                     if substrate_png.exists() else None)

    return {
        "slug": slug,
        "grid": {"width": gw, "height": gh},
        "default_terrain": (grid.get("default_terrain") or "open ground"),
        "presentation": pres,
        "nodes": node_list,
        "routes": routes,
        "substrate_image": substrate_rel,
        "n_cluster": (nodes[cluster_node_id]["_collapsed"] if cluster_node_id else 0),
    }


# ════════════════════════════════════════════════════════════════════════
# Emitters
# ════════════════════════════════════════════════════════════════════════

def emit_overview_yaml(ov: dict, out_path: Path):
    pres = ov["presentation"]
    landmarks = []
    for n in ov["nodes"]:
        landmarks.append({
            "id": n["id"], "name": n["name"], "icon": n["icon"],
            "distinctive": bool(n["distinctive"]),
            "pos": n["pos"], "min_zoom": 0, "max_zoom": 1,
            "grid": n["_grid"],
        })
    doc = {
        "area_key": ov["slug"],
        "display_name": pres["display_name"],
        "biome": pres["biome"],
        "base_tone": pres["base_tone"],
        "bounds": {"x_min": 0, "y_min": 0, "x_max": OVERVIEW_W, "y_max": OVERVIEW_H},
        # Empty by design — terrain atmosphere comes from the Nano prompt;
        # POSITIONS are faithful to the grid. See the module docstring.
        "terrain_zones": [],
        "routes": [[r[0], r[1]] for r in ov["routes"]],
        "landmarks": landmarks,
    }
    if ov["substrate_image"]:
        doc["substrate_image"] = ov["substrate_image"]

    header = (
        f"# {ov['slug']}_overview.yaml — GENERATED by tools/gen_wilderness_overview.py\n"
        f"# DO NOT HAND-EDIT. Faithful Tier-1b overview projected from the\n"
        f"# navigable grid in the region YAML. POI `pos` is overview space\n"
        f"# (700x600, SVG y-DOWN, north=top); `grid` is the source [x,y]\n"
        f"# (0..{ov['grid']['width']-1} W->E, 0..{ov['grid']['height']-1} S->N, north=y+1).\n"
        f"# {len(landmarks)} POIs"
        + (f" (village = {ov['n_cluster']} rooms collapsed)" if ov["n_cluster"] else "")
        + f", {len(doc['routes'])} routes. Re-run the generator to refresh.\n\n"
    )
    out_path.write_text(header + yaml.safe_dump(doc, sort_keys=False,
                                                default_flow_style=None,
                                                allow_unicode=True),
                        encoding="utf-8")
    print(f"  → {out_path}  ({len(landmarks)} POIs, {len(doc['routes'])} routes"
          + (f", substrate ENGAGED" if ov['substrate_image'] else "") + ")")


def _js_region(ov: dict) -> dict:
    pres = ov["presentation"]
    pois = []
    for n in ov["nodes"]:
        poi = {"x": n["pos"][0], "y": n["pos"][1], "name": n["name"]}
        if n["kind"] == "exit":
            poi["size"] = 6
        else:
            poi["size"] = 8
            poi["landmark"] = True
        pois.append(poi)
    region = {
        "name": pres["display_name"].upper(),
        "biome": pres["biome"],
        "bounds": {"x_min": 0, "y_min": 0, "x_max": OVERVIEW_W, "y_max": OVERVIEW_H},
        "sub_regions": [],
        "pois": pois,
        "routes": ov["routes"],
        "breadcrumb": pres["breadcrumb"],
        "tier_label": pres["tier_label"],
        "legend_spec": LEGEND_SPEC,
    }
    if pres.get("bg"):
        region["bg"] = pres["bg"]
    if ov["substrate_image"]:
        region["substrate_image"] = ov["substrate_image"]
    return region


def emit_js(overviews: list[dict], out_path: Path):
    table = {ov["slug"]: _js_region(ov) for ov in overviews}
    body = json.dumps(table, indent=2, ensure_ascii=True)
    js = (
        "// m3_wilderness_overview_data.js — GENERATED by\n"
        "// tools/gen_wilderness_overview.py. DO NOT HAND-EDIT.\n"
        "//\n"
        "// Faithful Tier-1b region objects, projected from the navigable\n"
        "// wilderness grid (north=y+1) into 700x600 overview space (SVG\n"
        "// y-down, north=top). m3_tier_wilderness_body.js · resolveRegion\n"
        "// prefers this data over its built-in showcase fixtures, so the\n"
        "// live overview map cannot drift from the grid. POIs/routes are\n"
        "// authoritative; sub_regions is empty (terrain is the painted\n"
        "// substrate / procedural base). substrate_image appears only once\n"
        "// the PNG exists on disk at generation time.\n"
        "(function () {\n"
        "  'use strict';\n"
        "  var DATA = " + body + ";\n"
        "  if (typeof window !== 'undefined') { window.M3WildernessOverviewData = DATA; }\n"
        "  if (typeof module !== 'undefined' && module.exports) { module.exports = DATA; }\n"
        "})();\n"
    )
    out_path.write_text(js, encoding="utf-8")
    print(f"  → {out_path}  ({len(table)} region(s): {', '.join(table)})")


def emit_paint_brief(ov: dict, out_path: Path):
    """Generate the FULL Nano/Gemini paint prompt from the projected data —
    placement (relative regions), per-feature visuals (authored short_desc),
    and a terrain-texture line — so the prompt is as faithful as the seed.
    All three trace to the same grid; nothing is hand-typed per region."""
    pres = ov["presentation"]
    W, H = OVERVIEW_W, OVERVIEW_H
    nodes = ov["nodes"]
    landmark_nodes = [n for n in nodes if n.get("kind") != "exit"]

    aspect = pbc.aspect_phrase({"x_min": 0, "y_min": 0, "x_max": W, "y_max": H})

    # ── {GEOGRAPHY} assembly ───────────────────────────────────────────────
    biome = pres["biome"].replace("\u00b7", "—")
    base_noun = TERRAIN_PAINT.get(ov["default_terrain"], ov["default_terrain"])

    # terrain texture: dominant ground + what the non-default ground is (the
    # WHERE is carried by the placement clause + honesty line, so we don't
    # restate frame-spread here — it conflicts with "keep them spaced out").
    nondefault = sorted({TERRAIN_PAINT.get(n.get("_terrain"), n.get("_terrain"))
                         for n in landmark_nodes
                         if n.get("_terrain") and n.get("_terrain") != ov["default_terrain"]})
    texture = f"The ground is {base_noun} almost everywhere."
    if nondefault:
        texture += (" The only other ground is right at the features: "
                    + ", ".join(nondefault) + ".")

    placement = pbc.placement_clause(nodes, W, H)

    # per-feature visual lines (authored flavor, trimmed to the paintable bit)
    feat_lines = []
    for n in landmark_nodes:
        vis = pbc.visual_from_desc(n.get("_short_desc"), n.get("_description"))
        if vis:
            feat_lines.append(f"  • {n['name']}: {vis}.")
    features = ("Paint these specific features (and no other major landmarks — "
                "fill the rest with ordinary biome-appropriate background):\n"
                + "\n".join(feat_lines)) if feat_lines else ""

    # honesty line: the fitted frame is the populated heart, not the whole region
    n_real = sum(1 for n in nodes if n.get("kind") != "exit")
    honesty = (f"This view is framed to the populated part of the region; the "
               f"true {pres['display_name']} is mostly empty {base_noun} — keep "
               f"generous open ground between the {n_real} features, do not crowd them.")

    geography = (
        f"Subject: {pres['display_name']} — {biome}. {texture} {honesty}\n\n"
        f"{placement}\n\n{features}"
    ).strip()

    prompt = pbc.MASTER_PROMPT.replace("{ASPECT}", aspect).replace("{GEOGRAPHY}", geography)

    # ── the brief doc ──────────────────────────────────────────────────────
    seed_name = f"{ov['slug']}_tight_seed.png"
    doc = (
        f"# {ov['slug']} — Nano paint brief (GENERATED by gen_wilderness_overview.py)\n\n"
        f"DO NOT HAND-EDIT — re-run the generator to refresh (placement, flavor,\n"
        f"and texture are all derived from the navigable grid, so this prompt\n"
        f"cannot drift from the map).\n\n"
        f"- **Feed seed:** `static/tools/seeds/{seed_name}`\n"
        f"- **Aspect:** {aspect}\n"
        f"- **Save painting to:** `static/maps/{ov['slug']}_substrate.png`\n"
        f"- After saving, re-run the generator — `substrate_image` auto-engages.\n\n"
        f"## Prompt (paste verbatim into Nano/Gemini with the seed attached)\n\n"
        f"```\n{prompt}\n```\n"
    )
    out_path.write_text(doc, encoding="utf-8")
    print(f"  → {out_path}  ({len(feat_lines)} feature lines)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("region_yamls", nargs="+",
                    help="paths to wilderness region YAMLs (e.g. .../wilderness/dune_sea.yaml)")
    ap.add_argument("--maps-out", default="data/worlds/clone_wars/maps",
                    help="dir for the generated *_overview.yaml specs")
    ap.add_argument("--js-out", default="static/spa/m3_wilderness_overview_data.js",
                    help="path for the generated live JS region data")
    ap.add_argument("--static-maps", default="static/maps",
                    help="dir checked for painted <slug>_substrate.png (auto-engage)")
    ap.add_argument("--briefs-out", default="static/tools/seeds",
                    help="dir for the generated <slug>_paint_brief.md Nano prompts")
    ap.add_argument("--no-fit", action="store_true",
                    help="map the full grid instead of fitting to the populated "
                         "region (fit is faithful — a zoom, not a distortion)")
    a = ap.parse_args()

    maps_out = Path(a.maps_out)
    maps_out.mkdir(parents=True, exist_ok=True)
    static_maps = Path(a.static_maps)
    briefs_out = Path(a.briefs_out)
    briefs_out.mkdir(parents=True, exist_ok=True)

    overviews = []
    for rp in a.region_yamls:
        rp = Path(rp)
        print(f"{rp.name}:")
        ov = build_overview(rp, static_maps, fit=not a.no_fit)
        emit_overview_yaml(ov, maps_out / f"{ov['slug']}_overview.yaml")
        emit_paint_brief(ov, briefs_out / f"{ov['slug']}_paint_brief.md")
        overviews.append(ov)

    emit_js(overviews, Path(a.js_out))
    print("done.")


if __name__ == "__main__":
    main()
