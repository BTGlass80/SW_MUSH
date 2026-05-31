#!/usr/bin/env python3
"""
tools/apply_cardinal_fixes.py
=============================
Apply Philosophy B (rendered map x/y is spatial truth) to the gameplay exit
graph: rewrite wrong-way compass words to the geometry-correct ones. Handles
BOTH planet exit formats, preserves comments (ruamel), resolves direction
collisions greedily, and FLAGS anything it cannot resolve cleanly instead of
guessing on the live movement graph.

Only planar cardinal exits whose BOTH endpoints are on a painted map and whose
current direction is a >90deg ("wrong way") mismatch are touched. Vertical /
interior / named exits and ok/minor exits are left exactly as-is. Reverses are
set to the opposite of the corrected forward (correct by construction).

Usage:
  python tools/apply_cardinal_fixes.py <area_key|map.yaml> [more ...]   # writes in place
  python tools/apply_cardinal_fixes.py --all
  python tools/apply_cardinal_fixes.py --all --dry-run                  # report only
"""
from __future__ import annotations
import argparse, glob, math, sys
from pathlib import Path
import yaml
from ruamel.yaml import YAML

MAPS_GLOB = "data/worlds/clone_wars/maps/*.yaml"
DIR_ANGLE = {"east": 0, "northeast": 45, "north": 90, "northwest": 135,
             "west": 180, "southwest": 225, "south": 270, "southeast": 315}
CARDINALS = set(DIR_ANGLE)
OPPOSITE = {"east": "west", "west": "east", "north": "south", "south": "north",
            "northeast": "southwest", "southwest": "northeast",
            "northwest": "southeast", "southeast": "northwest"}
VERTICAL = {"up", "down", "in", "out", "enter", "exit", "leave", "inside", "outside"}


def base_word(s): return (s or "").strip().lower().split()[0] if s and s.strip() else ""
def ang_diff(a, b): return abs((a - b + 180) % 360 - 180)
def octants_ranked(actual): return sorted(DIR_ANGLE, key=lambda n: ang_diff(actual, DIR_ANGLE[n]))


def maps_for(planet_stem, all_map_paths):
    out = []
    for mp in all_map_paths:
        m = yaml.safe_load(mp.read_text(encoding="utf-8"))
        if m.get("area_key", "").split(".", 1)[0] == planet_stem:
            out.append(m)
    return out


def collect_xy(maps):
    xy = {}
    for m in maps:
        for r in m.get("rooms", []) or []:
            xy[r["slug"]] = (float(r["x"]), float(r["y"]))
    return xy


def normalize_edges(p):
    """Return list of edges as dicts with handles into the ruamel doc:
       {fr, to, fwd, kind:'list'|'inline', ref:(container,key)}.
       For 'list', ref is (exits_list, index). For 'inline', ref is
       (room_exits_map, dir_key)."""
    rooms = p.get("rooms", []) or []
    id2slug = {r.get("id"): r.get("slug") for r in rooms}
    edges = []
    top = p.get("exits")
    if top is not None and len(top):
        for i, e in enumerate(top):
            edges.append(dict(fr=id2slug.get(e.get("from")), to=id2slug.get(e.get("to")),
                              fwd=e.get("forward", ""), kind="list", ref=(top, i)))
    else:
        for r in rooms:
            ex = r.get("exits")
            if ex is None:
                continue
            for k in list(ex.keys()):
                edges.append(dict(fr=r.get("slug"), to=ex[k], fwd=k,
                                  kind="inline", ref=(ex, k)))
    return edges


def room_dir_sets(edges):
    """Map room_slug -> list of (edge, is_outbound). For 'list' format an edge
       contributes forward to fr and reverse to to. For 'inline' the dir key is
       fr's outbound only (the reverse is a separate inline edge)."""
    sets = {}
    for e in edges:
        sets.setdefault(e["fr"], []).append(e)
    return sets


def plan_corrections(p, xy):
    """Greedy global assignment. Maintains taken[room] = set of cardinal
    directions currently used by that room (forwards where it is 'from' +
    reverses where it is 'to' for the list format; keys for inline). A
    correction is only applied if its new forward is free in the from-room AND
    its new reverse (the opposite) is free in the to-room; otherwise it is
    FLAGGED rather than creating an ambiguous duplicate."""
    edges = normalize_edges(p)
    taken = {}

    def add(room, d):
        if room and d in CARDINALS:
            taken.setdefault(room, set()).add(d)

    def remove(room, d):
        if room in taken:
            taken[room].discard(d)

    # seed taken from the current graph (cardinals only)
    for e in edges:
        add(e["fr"], base_word(e["fwd"]))
        if e["kind"] == "list":
            entry = e["ref"][0][e["ref"][1]]
            add(e["to"], base_word(entry.get("reverse", "")))

    # candidate corrections: planar cardinal exits, both ends on-map, >90deg off
    cands = []
    for e in edges:
        bw = base_word(e["fwd"])
        if bw not in CARDINALS:
            continue
        fr, to = e["fr"], e["to"]
        if fr not in xy or to not in xy:
            continue
        (ax, ay), (bx, by) = xy[fr], xy[to]
        dx, dy = bx - ax, by - ay
        if math.hypot(dx, dy) < 1e-6:
            continue
        act = math.degrees(math.atan2(dy, dx)) % 360
        if ang_diff(act, DIR_ANGLE[bw]) > 90:
            cands.append((e, act, bw))
    # most geometrically-precise first, so the clearest cases claim their octant
    cands.sort(key=lambda t: ang_diff(t[1], DIR_ANGLE[octants_ranked(t[1])[0]]))

    corrections, flags = [], []
    for e, act, oldbw in cands:
        if e["kind"] == "list":
            entry = e["ref"][0][e["ref"][1]]
            oldrev = base_word(entry.get("reverse", ""))
            remove(e["fr"], oldbw)
            remove(e["to"], oldrev)
            chosen = None
            for cand in octants_ranked(act):
                if ang_diff(act, DIR_ANGLE[cand]) > 67.5:
                    break
                if cand in taken.get(e["fr"], set()):
                    continue
                if OPPOSITE[cand] in taken.get(e["to"], set()):
                    continue
                chosen = cand
                break
            if chosen is None:
                add(e["fr"], oldbw)
                add(e["to"], oldrev)
                flags.append((e, "no free octant (would duplicate a direction in the from- or to-room)"))
            else:
                add(e["fr"], chosen)
                add(e["to"], OPPOSITE[chosen])
                corrections.append((e, chosen))
        else:  # inline (one-way; reverse is a separate edge handled on its own)
            remove(e["fr"], oldbw)
            chosen = None
            for cand in octants_ranked(act):
                if ang_diff(act, DIR_ANGLE[cand]) > 67.5:
                    break
                if cand in taken.get(e["fr"], set()):
                    continue
                chosen = cand
                break
            if chosen is None:
                add(e["fr"], oldbw)
                flags.append((e, "no free octant (would duplicate a direction in the room)"))
            else:
                add(e["fr"], chosen)
                corrections.append((e, chosen))
    return edges, corrections, flags


def find_reciprocal(edges, fr, to):
    """For inline format, the reverse of fr->to is the inline edge to->fr."""
    for e in edges:
        if e["kind"] == "inline" and e["fr"] == to and e["to"] == fr:
            return e
    return None


def apply_to_doc(edges, corrections):
    """Mutate the ruamel structures in place. Returns list of human-readable changes."""
    changes = []
    for e, new_dir in corrections:
        if e["kind"] == "list":
            lst, i = e["ref"]
            entry = lst[i]
            old_f, old_r = entry.get("forward"), entry.get("reverse")
            entry["forward"] = new_dir
            entry["reverse"] = OPPOSITE[new_dir]
            changes.append(f"[list] {e['fr']} -> {e['to']}: forward {old_f!r}->{new_dir!r}, "
                           f"reverse {old_r!r}->{OPPOSITE[new_dir]!r}")
        else:  # inline: each one-way edge is corrected independently by its
                # own from-room pass, so we only rename THIS edge's key. (The
                # reverse edge to->from is a separate inline entry and is fixed
                # by that room's pass if it is itself a mismatch; touching it
                # here would double-edit and could conflict with greedy choices.)
            ex, old_key = e["ref"]
            target = ex[old_key]
            _rename_key(ex, old_key, new_dir)
            changes.append(f"[inline] {e['fr']}.{old_key} -> {e['fr']}.{new_dir}  (-> {target})")
    return changes


def _rename_key(cm, old, new):
    """Rename a key in a (ruamel) ordered mapping, preserving order and the
       trailing inline comment attached to the old key."""
    if old == new or old not in cm:
        return
    items = list(cm.items())
    ca = getattr(cm, "ca", None)
    old_comment = None
    if ca is not None and old in ca.items:
        old_comment = ca.items.pop(old)
    for k, _ in items:
        cm.pop(k)
    for k, v in items:
        nk = new if k == old else k
        cm[nk] = v
    if old_comment is not None and ca is not None:
        ca.items[new] = old_comment


def verify(planet_file, affected_maps):
    """yaml parses; area_loader loads each map; no room has duplicate cardinal dirs."""
    txt = planet_file.read_text(encoding="utf-8")
    yaml.safe_load(txt)  # raises on malformed
    # duplicate-direction check across the whole planet
    p = yaml.safe_load(txt)
    rooms = p.get("rooms", []) or []
    id2slug = {r.get("id"): r.get("slug") for r in rooms}
    dirs = {}
    top = p.get("exits")
    if top:
        for e in top:
            dirs.setdefault(id2slug.get(e.get("from")), []).append(base_word(e.get("forward", "")))
            dirs.setdefault(id2slug.get(e.get("to")), []).append(base_word(e.get("reverse", "")))
    else:
        for r in rooms:
            for k in (r.get("exits") or {}):
                dirs.setdefault(r.get("slug"), []).append(base_word(k))
    dupes = []
    for room, dl in dirs.items():
        cds = [d for d in dl if d in CARDINALS]
        seen = set()
        for d in cds:
            if d in seen:
                dupes.append((room, d))
            seen.add(d)
    return dupes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("maps", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    all_map_paths = [Path(p) for p in sorted(glob.glob(MAPS_GLOB))]
    if a.all:
        targets = all_map_paths
    else:
        targets = []
        for x in a.maps:
            p = Path(x)
            if p.suffix == ".yaml" and p.exists():
                targets.append(p)
            else:
                cand = Path("data/worlds/clone_wars/maps") / f"{x.split('.')[-1]}.yaml"
                targets.append(cand if cand.exists() else p)

    # group targets by planet
    planets = {}
    for mp in targets:
        m = yaml.safe_load(mp.read_text(encoding="utf-8"))
        planets.setdefault(m.get("area_key", "").split(".", 1)[0], []).append(mp)

    yamlrt = YAML()
    yamlrt.preserve_quotes = True
    yamlrt.width = 4096
    yamlrt.indent(mapping=2, sequence=4, offset=2)

    grand_applied = grand_flagged = 0
    for planet_stem, _maps in planets.items():
        planet_file = Path("data/worlds/clone_wars/planets") / f"{planet_stem}.yaml"
        if not planet_file.exists():
            print(f"!! {planet_stem}: planet file not found"); continue
        xy = collect_xy(maps_for(planet_stem, all_map_paths))
        doc = yamlrt.load(planet_file.read_text(encoding="utf-8"))
        edges, corrections, flags = plan_corrections(doc, xy)
        print(f"\n=== {planet_stem} === corrections={len(corrections)} flagged={len(flags)}")
        if flags:
            for e, why in flags:
                print(f"   FLAG {e['fr']} --{base_word(e['fwd'])}--> {e['to']}: {why}")
        changes = apply_to_doc(edges, corrections) if not a.dry_run else []
        for c in changes:
            print("   " + c)
        grand_applied += len(corrections); grand_flagged += len(flags)
        if not a.dry_run and corrections:
            from io import StringIO
            buf = StringIO(); yamlrt.dump(doc, buf)
            planet_file.write_text(buf.getvalue(), encoding="utf-8")
            dupes = verify(planet_file, _maps)
            print(f"   VERIFY: yaml parses OK; duplicate-direction rooms: {len(dupes)}"
                  + ("" if not dupes else f"  {dupes}"))

    print(f"\nTOTAL applied={grand_applied} flagged={grand_flagged}"
          + ("  (dry-run, nothing written)" if a.dry_run else ""))


if __name__ == "__main__":
    main()
