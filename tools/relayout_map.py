#!/usr/bin/env python3
"""
tools/relayout_map.py
=====================
Philosophy A for a map: move room x/y so the layout AGREES with the gameplay
exit directions (instead of relabelling directions). A constraint solver
rotates each cardinal exit to its correct compass angle while keeping its
current length, lightly anchored to current positions so structure that's
already correct barely moves. Then it regenerates the dependent map elements
that reference room positions — district polygons + label anchors, street
ribbons (exit_paths), and bounds — so a freshly-generated seed stays coherent.

Gameplay is untouched: only the MAP yaml (display geometry) changes; the
planet yaml (movement directions) is read-only here.

Usage:
  python tools/relayout_map.py <area_key|map.yaml> [--iters 1200]
        [--init identity|rot180] [--pad 0.08] [--dry-run]
"""
from __future__ import annotations
import argparse, math, sys
from pathlib import Path
import yaml
from ruamel.yaml import YAML

DIR_ANGLE = {"east": 0, "northeast": 45, "north": 90, "northwest": 135,
             "west": 180, "southwest": 225, "south": 270, "southeast": 315}
CARDINALS = set(DIR_ANGLE)
VERTICAL = {"up", "down", "in", "out", "enter", "exit", "leave", "inside", "outside"}


def base_word(s): return (s or "").strip().lower().split()[0] if s and s.strip() else ""


def gameplay_edges(planet, slug_set):
    """(from_slug, to_slug, forward) for exits with both ends on the map."""
    rooms = planet.get("rooms", []) or []
    id2slug = {r.get("id"): r.get("slug") for r in rooms}
    out = []
    top = planet.get("exits")
    if isinstance(top, list) and top:
        for e in top:
            fa, fb = id2slug.get(e.get("from")), id2slug.get(e.get("to"))
            if fa in slug_set and fb in slug_set:
                out.append((fa, fb, e.get("forward", "")))
    else:
        for r in rooms:
            for k, tgt in (r.get("exits") or {}).items():
                if r.get("slug") in slug_set and tgt in slug_set:
                    out.append((r.get("slug"), tgt, k))
    return out


def solve(rooms, edges, iters, init, pad):
    idx = {r["slug"]: i for i, r in enumerate(rooms)}
    xs = [float(r["x"]) for r in rooms]
    ys = [float(r["y"]) for r in rooms]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    if init == "rot180":
        xs = [(xmax + xmin) - x for x in xs]
        ys = [(ymax + ymin) - y for y in ys]
    px = list(xs); py = list(ys)
    ix = list(xs); iy = list(ys)   # anchors

    card = []   # (a, b, theta_rad, L0)
    noncard = []  # (a, b, dx0, dy0) — interior/vertical/named: keep relative offset
    for fa, fb, fwd in edges:
        bw = base_word(fwd)
        a, b = idx[fa], idx[fb]
        if bw in CARDINALS:
            L0 = math.hypot(px[b] - px[a], py[b] - py[a])
            card.append((a, b, math.radians(DIR_ANGLE[bw]), L0))
        else:
            noncard.append((a, b, px[b] - px[a], py[b] - py[a]))

    # typical edge length (for collapsed/degenerate edges and repulsion)
    lens = [l for _, _, _, l in card if l > 1e-9]
    med = sorted(lens)[len(lens) // 2] if lens else 1.0
    min_sep = med * 0.5
    # fixed-length target per edge (no shrink -> chains can't collapse); the
    # compass targets are ABSOLUTE angles, so orientation is already pinned and
    # only translation needs a (tiny) anchor for numerical stability.
    card = [(a, b, th, (L if L > 1e-6 else med)) for (a, b, th, L) in card]
    anchor_w = 0.0

    n = len(rooms)
    for it in range(iters):
        rate = 0.12 * (1 - it / iters) + 0.02
        fx = [0.0] * n; fy = [0.0] * n
        # angular constraints: rotate each edge to its target angle at its
        # FIXED original length
        for a, b, th, L in card:
            dx = px[b] - px[a]; dy = py[b] - py[a]
            tx = math.cos(th) * L; ty = math.sin(th) * L
            ex = tx - dx; ey = ty - dy
            fx[b] += ex * 0.5; fy[b] += ey * 0.5
            fx[a] -= ex * 0.5; fy[a] -= ey * 0.5
        # interior/vertical/named edges: keep each at its original relative
        # offset from its parent (so a building's interior rooms follow it and
        # don't scatter), without imposing a compass direction
        for a, b, dx0, dy0 in noncard:
            ex = (px[a] + dx0) - px[b]; ey = (py[a] + dy0) - py[b]
            fx[b] += ex * 0.3; fy[b] += ey * 0.3
            fx[a] -= ex * 0.3; fy[a] -= ey * 0.3
        # gentle repulsion for overlapping rooms only
        for i in range(n):
            for j in range(i + 1, n):
                dx = px[j] - px[i]; dy = py[j] - py[i]
                d = math.hypot(dx, dy)
                if 1e-6 < d < min_sep:
                    push = (min_sep - d) / d * 0.25
                    fx[j] += dx * push; fy[j] += dy * push
                    fx[i] -= dx * push; fy[i] -= dy * push
        # apply, then recenter to pin translation (prevents free drift)
        for i in range(n):
            px[i] += fx[i] * rate
            py[i] += fy[i] * rate
        cx = sum(px) / n - sum(ix) / n
        cy = sum(py) / n - sum(iy) / n
        for i in range(n):
            px[i] -= cx; py[i] -= cy

    for i, r in enumerate(rooms):
        r["__nx"] = round(px[i], 2)
        r["__ny"] = round(py[i], 2)
    nxs = [r["__nx"] for r in rooms]; nys = [r["__ny"] for r in rooms]
    bx0, bx1, by0, by1 = min(nxs), max(nxs), min(nys), max(nys)
    mx = (bx1 - bx0) * pad + 0.5
    my = (by1 - by0) * pad + 0.5
    bounds = {"x_min": round(bx0 - mx, 2), "x_max": round(bx1 + mx, 2),
              "y_min": round(by0 - my, 2), "y_max": round(by1 + my, 2)}
    return bounds


def regen_districts(map_doc, rooms_by_slug):
    """Recompute each district polygon as a padded bbox of its member rooms
       (rooms grouped by zone == district id) and re-center its label anchor."""
    by_zone = {}
    for r in map_doc.get("rooms", []) or []:
        by_zone.setdefault(r.get("zone"), []).append(r)
    for d in map_doc.get("districts", []) or []:
        members = by_zone.get(d.get("id")) or []
        if not members:
            continue
        xs = [m["__nx"] for m in members]; ys = [m["__ny"] for m in members]
        pad = 0.6
        x0, x1 = min(xs) - pad, max(xs) + pad
        y0, y1 = min(ys) - pad, max(ys) + pad
        d["polygon"] = [[round(x0, 2), round(y0, 2)], [round(x1, 2), round(y0, 2)],
                        [round(x1, 2), round(y1, 2)], [round(x0, 2), round(y1, 2)]]
        d["label_anchor"] = [round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2)]


def regen_exit_paths(map_doc, rooms):
    """Remove the hand-authored street ribbons entirely. After a directional
    relayout, straight room-to-room ribbons tangle and would mislead the
    painting; they aren't used under a substrate at runtime and are
    regenerable. The seed locks districts + rooms + landmarks; streets get
    painted in organically. (Removing the whole key — not clearing it — avoids
    orphaned comments that would corrupt the YAML.)"""
    if "exit_paths" in map_doc:
        del map_doc["exit_paths"]
        ca = getattr(map_doc, "ca", None)
        if ca is not None and "exit_paths" in getattr(ca, "items", {}):
            del ca.items["exit_paths"]


def regen_labels(map_doc):
    """Drop street-name labels that reference exit_paths (path_id) — those
    paths were removed, and the loader validates the reference. Flavor/pos
    labels (no path_id) are kept. Street labels get re-authored on repaint."""
    labels = map_doc.get("labels")
    if not isinstance(labels, list):
        return
    for i in range(len(labels) - 1, -1, -1):
        item = labels[i]
        if isinstance(item, dict) and "path_id" in item:
            del labels[i]


def regen_landmarks(map_doc, rooms, old_bounds, new_bounds):
    """Re-anchor the landmarks block to the new layout. A landmark is matched to
    a room by NAME tokens against room slugs (reliable: 'Krayt Graveyard' ->
    jundland_krayt_graveyard) and snapped to that room's new position, so the
    seed's distinctive gold blocks land on their rooms. Landmarks with no room
    match (a pure marker, or an off-map arrow pointer) are proportionally
    remapped into the new bounds so they stay at a sensible spot/edge."""
    import re
    STOP = {"the", "of", "and", "to"}
    by_slug_new = {r["slug"]: (r["__nx"], r["__ny"]) for r in rooms if "__nx" in r}
    slugs = list(by_slug_new.keys())
    obx0, obx1 = old_bounds["x_min"], old_bounds["x_max"]
    oby0, oby1 = old_bounds["y_min"], old_bounds["y_max"]
    nbx0, nbx1 = new_bounds["x_min"], new_bounds["x_max"]
    nby0, nby1 = new_bounds["y_min"], new_bounds["y_max"]

    def match_room(name):
        toks = [t for t in re.findall(r"[a-z0-9]+", name.lower())
                if t not in STOP and (len(t) >= 3 or t.isdigit())]
        best, bscore = None, 0
        for s in slugs:
            score = sum(1 for t in toks if t in s)
            # prefer a "front" room when several in a complex match equally
            if score > bscore or (score == bscore and score > 0 and best
                                  and len(s) < len(best)):
                bscore, best = score, s
        return best if bscore > 0 else None

    for lm in map_doc.get("landmarks", []) or []:
        pos = lm.get("pos")
        if not pos:
            continue
        px, py = float(pos[0]), float(pos[1])
        name = str(lm.get("name", ""))
        room = None if any(a in name for a in ("\u2197", "\u2199", "\u2196", "\u2198")) \
            else match_room(name)
        if room:
            nx, ny = by_slug_new[room]
            lm["pos"] = [round(nx, 2), round(ny, 2)]
        else:  # off-map pointer or roomless marker: proportional remap
            fx = (px - obx0) / (obx1 - obx0) if obx1 > obx0 else 0.5
            fy = (py - oby0) / (oby1 - oby0) if oby1 > oby0 else 0.5
            lm["pos"] = [round(nbx0 + fx * (nbx1 - nbx0), 2),
                         round(nby0 + fy * (nby1 - nby0), 2)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--iters", type=int, default=1200)
    ap.add_argument("--init", choices=["identity", "rot180"], default="identity")
    ap.add_argument("--pad", type=float, default=0.08)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    mp = Path(a.map)
    if not (mp.suffix == ".yaml" and mp.exists()):
        cand = Path("data/worlds/clone_wars/maps") / f"{a.map.split('.')[-1]}.yaml"
        mp = cand if cand.exists() else mp
    if not mp.exists():
        sys.exit(f"map not found: {mp}")

    plain = yaml.safe_load(mp.read_text(encoding="utf-8"))
    area_key = plain.get("area_key", mp.stem)
    planet_file = mp.parent.parent / "planets" / f"{area_key.split('.')[0]}.yaml"
    planet = yaml.safe_load(planet_file.read_text(encoding="utf-8"))

    rooms = plain.get("rooms", []) or []
    slug_set = {r["slug"] for r in rooms}
    edges = gameplay_edges(planet, slug_set)
    ncard = sum(1 for _, _, f in edges if base_word(f) in CARDINALS)
    print(f"{area_key}: {len(rooms)} rooms, {ncard} cardinal constraints, init={a.init}, iters={a.iters}")

    bounds = solve(rooms, edges, a.iters, a.init, a.pad)
    rooms_by_slug = {r["slug"]: r for r in rooms}
    regen_districts(plain, rooms_by_slug)
    regen_exit_paths(plain, rooms)

    # write back via ruamel (preserve comments + matched indent)
    rt = YAML(); rt.preserve_quotes = True; rt.width = 4096
    rt.indent(mapping=2, sequence=4, offset=2)
    doc = rt.load(mp.read_text(encoding="utf-8"))
    for r in doc.get("rooms", []) or []:
        nr = rooms_by_slug.get(r.get("slug"))
        if nr is not None:
            r["x"] = nr["__nx"]; r["y"] = nr["__ny"]
    # districts + exit_paths + bounds (recompute on the ruamel doc the same way)
    for r in doc.get("rooms", []):
        r2 = rooms_by_slug.get(r.get("slug"))
        if r2 is not None:
            r["__nx"] = r2["__nx"]; r["__ny"] = r2["__ny"]
    regen_districts(doc, rooms_by_slug)
    regen_exit_paths(doc, list(doc.get("rooms", [])))
    regen_labels(doc)
    regen_landmarks(doc, rooms, plain.get("bounds", {}), bounds)
    for r in doc.get("rooms", []):
        r.pop("__nx", None); r.pop("__ny", None)
    for k in ("x_min", "x_max", "y_min", "y_max"):
        if "bounds" in doc and k in doc["bounds"]:
            doc["bounds"][k] = bounds[k]
    aspect = round((bounds["x_max"] - bounds["x_min"]) / (bounds["y_max"] - bounds["y_min"]), 3)
    print(f"new bounds: {bounds}  aspect {aspect}:1")

    if a.dry_run:
        print("(dry-run, not written)")
        return
    from io import StringIO
    buf = StringIO(); rt.dump(doc, buf)
    mp.write_text(buf.getvalue(), encoding="utf-8")
    print(f"wrote {mp}")


if __name__ == "__main__":
    main()
