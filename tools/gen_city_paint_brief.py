#!/usr/bin/env python3
"""
gen_city_paint_brief.py — generate a faithful Nano/Gemini paint brief for a
CITY map from its real district / room / landmark layout (Drop 4.19).

WHY (and how it differs from wilderness)
----------------------------------------
For wilderness, the Tier-1b overview was decorative fiction and had to be
rebuilt from the grid (Drop 4.17). Cities are different: the city map YAML
(maps/<key>.yaml) ALREADY carries faithful data — real `bounds`, `districts`
(polygons + label anchors), `rooms` (positioned), and `landmarks` (gold-block
key structures at real `pos`). So the city positions don't need rebuilding.

What's missing is the same thing wilderness was missing before Drop 4.18: a
generated PAINT BRIEF. We were hand-writing each city's {GEOGRAPHY}. This tool
replaces that — it reads the city map and emits the full master prompt with a
{GEOGRAPHY} assembled from:
  · district character + where each district sits (from polygon centroids)
  · every landmark placed by relative region (from its real pos) with a
    painterly visual pulled from the authored "Say" vocabulary (icon → phrase)
  · a density line (where the rooms cluster) and a count discipline
All of it derived from the map, so the prompt can't drift and a re-paint (or a
brand-new city) needs zero hand-authoring.

Shares the placement/flavor/aspect primitives with wilderness via
paint_brief_common.

USAGE
-----
    python3 tools/gen_city_paint_brief.py data/worlds/clone_wars/maps/mos_eisley.yaml
    python3 tools/gen_city_paint_brief.py data/worlds/clone_wars/maps/*.yaml   # all cities
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paint_brief_common as pbc   # noqa: E402

# icon → painterly visual for a city landmark. This is the canonical "Say"
# vocabulary (NANO_MAP_PACKAGE §3 translation table), kept IP-safe and
# era-clean. A landmark with an unknown icon falls back to a generic building.
ICON_VISUAL = {
    "dock":    "a circular landing pad / docking berth for a starship",
    "ship":    "a large grounded vessel repurposed as a structure",
    "wreck":   "a half-buried old starship wreck jutting from the ground",
    "cantina": "a notorious cantina, the busiest dive around",
    "bones":   "a field of giant bleached skeletal bones in the open desert",
    "hutt":    "an opulent fortified townhouse of a local crime boss",
    "palace":  "a large imposing fortified palace complex",
    "beacon":  "a tall slender navigation/comms tower",
    "sarlacc": "a vast sand pit with a toothed maw at its center",
    "spire":   "a tall weathered stone spire",
    "factory": "a grimy industrial works with smokestacks",
    "hideout": "a fortified hideout built into a derelict structure",
    "maze":    "a dense tangled warren of cramped alleys",
    "tents":   "a cluster of hide tents and mud-brick domes",
    "farm":    "a low domed homestead",
    "shaft":   "a stairwell/shaft access point",
    "palace_hall": "a grand columned hall",
}

# district id/name keyword → ground character for the {GEOGRAPHY} zone line.
DISTRICT_CHAR = {
    # Tatooine / desert frontier
    "spaceport":  "an open landing field of circular docking pits and parked freighters",
    "market":     "a dense crowded market quarter of stalls and low blocky buildings",
    "cantina":    "a seedy strip of cantinas and dives",
    "civic":      "a small orderly civic quarter",
    "outskirts":  "thinning ramshackle outskirts fading toward open ground",
    "jundland":   "rocky badlands and broken canyon country",
    "dune_sea":   "open empty sand dunes",
    "residential":"packed low residential housing",
    "industrial": "a grimy industrial district of works and stacks",
    "underlevel": "dark layered ferrocrete underlevels",
    # generic civic / approach
    "gateway":    "a formal arrival gateway and approach road",
    "center":     "a built-up central quarter",
    "embassy":    "a stately embassy quarter with formal gardens",
    "axis":       "a grand monumental ceremonial axis",
    "chancellery":"an imposing seat-of-government complex",
    # Nar Shaddaa / smuggler's moon (vertical neon slum)
    "promenade":  "a garish neon vice-strip of bars and dens",
    "landing":    "industrial freighter docking bays",
    "undercity":  "a dark decaying under-tier of scaffolding and smog",
    "warrens":    "a cramped tangle of slum warrens and catwalks",
    # Geonosis / stalgasin hive (insectile rock)
    "surface":    "baked orange-red rock flats and dust",
    "foundries":  "a smoking subterranean foundry complex",
    "hive":       "a towering organic mud-spire hive",
    "arena":      "a great open-air execution arena",
    # Kamino / tipoca city (storm ocean stilt-city)
    "ocean":      "dark storm-lashed open ocean under perpetual rain",
    "tipoca":     "smooth white domed pods on stilts linked by causeways",
    "cloning":    "large rounded laboratory pods on stilts",
}


def _offmap(name: str) -> bool:
    return any(a in name for a in ("\u2197", "\u2199", "\u2196", "\u2198", "\u2192", "\u2190"))


def _clean_name(name: str) -> str:
    for a in ("\u2197", "\u2199", "\u2196", "\u2198", "\u2192", "\u2190"):
        name = name.replace(a, "")
    return name.strip()


def _district_char(d: dict) -> str:
    key = str(d.get("id") or "").lower()
    for k, v in DISTRICT_CHAR.items():
        if k in key:
            return v
    nm = str(d.get("name") or "").lower()
    for k, v in DISTRICT_CHAR.items():
        if k in nm:
            return v
    return "built-up urban ground"


def _poly_centroid(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def build_city_brief(map_path: Path) -> dict:
    raw = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    b = raw["bounds"]
    x0, y0 = float(b["x_min"]), float(b["y_min"])
    x1, y1 = float(b["x_max"]), float(b["y_max"])
    spanx = (x1 - x0) or 1.0
    spany = (y1 - y0) or 1.0
    W, H = 700.0, 600.0

    def proj(wx, wy):
        # world (y UP, like map_x/map_y) → overview SVG (y DOWN, north=top)
        ox = (float(wx) - x0) / spanx * W
        oy = (y1 - float(wy)) / spany * H
        return max(0.0, min(W, ox)), max(0.0, min(H, oy))

    name = raw.get("display_name") or raw.get("area_key") or map_path.stem
    aspect = f"{spanx / spany:.3f}".rstrip("0").rstrip(".") + ":1"

    # ── districts: character + where each sits ─────────────────────────────
    district_lines = []
    for d in (raw.get("districts") or []):
        poly = d.get("polygon") or []
        anchor = d.get("label_anchor") or (poly[0] if poly else None)
        if not anchor:
            continue
        ox, oy = proj(anchor[0], anchor[1])
        where = pbc.relative_region(ox, oy, W, H)
        if _offmap(str(d.get("name") or "")):
            continue
        district_lines.append(f"{_clean_name(str(d.get('name') or d.get('id')))} "
                              f"({where}): {_district_char(d)}")

    # ── landmarks: placement + authored visual ─────────────────────────────
    landmark_nodes, lm_lines = [], []
    for lm in (raw.get("landmarks") or []):
        pos = lm.get("pos")
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
            continue
        ox, oy = proj(pos[0], pos[1])
        nm = _clean_name(str(lm.get("name") or lm.get("id")))
        is_off = _offmap(str(lm.get("name") or ""))
        node = {"name": nm.upper(), "pos": [ox, oy],
                "kind": "exit" if is_off else "landmark",
                "offmap": is_off}
        landmark_nodes.append(node)
        if node["kind"] != "exit":
            vis = ICON_VISUAL.get(str(lm.get("icon") or "").lower(),
                                  "a distinct weathered building")
            lm_lines.append(f"  • {nm.upper()}: {vis}.")

    # ── density of rooms (where the town is built-up) ──────────────────────
    room_pts = []
    for r in (raw.get("rooms") or []):
        if r.get("x") is not None and r.get("y") is not None:
            room_pts.append(proj(r["x"], r["y"]))
    density = pbc.coarse_region_phrase(room_pts, W, H) if room_pts else "spread across the map"

    n_real = sum(1 for n in landmark_nodes if n["kind"] != "exit")
    n_rooms = len(room_pts)

    return {
        "slug": map_path.stem,
        "name": name,
        "aspect": aspect,
        "districts": district_lines,
        "landmark_nodes": landmark_nodes,
        "landmark_lines": lm_lines,
        "density": density,
        "n_real": n_real,
        "n_rooms": n_rooms,
        "W": W, "H": H,
    }


def render_geography(ci: dict) -> str:
    W, H = ci["W"], ci["H"]
    districts = ""
    if ci["districts"]:
        districts = ("Districts — repaint each colored region in place as its ground type: "
                     + "; ".join(ci["districts"]) + ".")
    placement = pbc.placement_clause(ci["landmark_nodes"], W, H)
    features = ("Paint these specific key structures (and no other major landmarks — the "
                f"faint pale rectangles are ~{ci['n_rooms']} ordinary background buildings, "
                "fill them as generic structures, NOT distinct landmarks):\n"
                + "\n".join(ci["landmark_lines"])) if ci["landmark_lines"] else ""
    dens = ci["density"]
    if "spread" in dens or "loosely" in dens:
        density = ("The town is built up across the whole map; keep the roads and "
                   "open ground between districts clear.")
    else:
        density = (f"The buildings are densest {dens}; keep the roads and open "
                   "ground between districts clear.")
    return (f"Subject: {ci['name']} — a lived-in frontier settlement. {density}\n\n"
            f"{districts}\n\n{placement}\n\n{features}").strip()


def emit(ci: dict, out_path: Path):
    prompt = (pbc.MASTER_PROMPT
              .replace("{ASPECT}", ci["aspect"])
              .replace("{GEOGRAPHY}", render_geography(ci)))
    seed = f"{ci['slug']}_tight_seed.png"
    doc = (
        f"# {ci['slug']} — Nano CITY paint brief (GENERATED by gen_city_paint_brief.py)\n\n"
        f"DO NOT HAND-EDIT — re-run the generator to refresh. Placement, district\n"
        f"character, and per-landmark visuals are all derived from the city map\n"
        f"(maps/{ci['slug']}.yaml), so this prompt cannot drift from the map.\n\n"
        f"- **Feed seed:** `static/tools/seeds/{seed}` (the city tight seed)\n"
        f"- **Aspect:** {ci['aspect']}\n"
        f"- **Save painting to:** `static/maps/{ci['slug']}_substrate.png`\n"
        f"- {ci['n_real']} key landmarks, {ci['n_rooms']} background rooms, "
        f"{len(ci['districts'])} districts.\n\n"
        f"## Prompt (paste verbatim into Nano/Gemini with the seed attached)\n\n"
        f"```\n{prompt}\n```\n"
    )
    out_path.write_text(doc, encoding="utf-8")
    print(f"  → {out_path}  ({ci['n_real']} landmarks, {len(ci['districts'])} districts, "
          f"{ci['n_rooms']} rooms)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("city_maps", nargs="+", help="city map YAMLs (maps/<key>.yaml)")
    ap.add_argument("--briefs-out", default="static/tools/seeds")
    a = ap.parse_args()
    out = Path(a.briefs_out)
    out.mkdir(parents=True, exist_ok=True)
    for mp in a.city_maps:
        mp = Path(mp)
        # skip wilderness overview specs if globbed in
        head = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
        if "districts" not in head and "rooms" not in head:
            print(f"{mp.name}: not a city map (no districts/rooms) — skipping")
            continue
        print(f"{mp.name}:")
        ci = build_city_brief(mp)
        emit(ci, out / f"{ci['slug']}_paint_brief.md")
    print("done.")


if __name__ == "__main__":
    main()
