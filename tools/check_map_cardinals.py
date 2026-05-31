#!/usr/bin/env python3
"""
tools/check_map_cardinals.py
=============================
Verify — and optionally CORRECT — agreement between the GAMEPLAY exit graph's
compass words (planet ``exits[].forward`` AND ``exits[].reverse``) and the MAP's
room placement (map ``rooms[].x/y``), aligned by slug.

WHY: the painted substrate + zoom-in overlay make the map a primary navigation
aid. For navigation to make sense, "go north" must move the player's marker
*up* on the map. The map x/y is the spatial ground truth (it is what we paint
and register against); where a planar cardinal exit disagrees with that
geometry, the compass WORD is what's wrong.

This checks BOTH directions of every edge:
  · forward  — the word shown at the *from* room (bearing from -> to)
  · reverse  — the word shown at the *to*   room (bearing to   -> from)
The original tool only validated ``forward`` and *assumed* the reverse was its
opposite. That blind spot let geometrically wrong reverse words ship (e.g. an
exit drawn due-north labelled "east", or a stale "...to Bay 86" pointing at a
different room). The reverse word is what the destination room actually
displays, so it must be checked on its own bearing.

``--derive`` proposes geometry-consistent words and is **collision-aware**: a
MUSH parser can't have two exits with the same word at one room, but the 2-D
layout often places several neighbours in the same compass octant (a hub like
Spaceport Row fans 7 exits out). When the ideal octant at a room is already
taken, the proposal nudges to the nearest FREE octant (staying within the
"minor" band), exactly as the hand-tuned data already does — so re-deriving a
broken word doesn't trample its neighbours.

``--write`` applies the proposals to the planet YAML in place. It edits only
the specific ``forward``/``reverse`` field of the matching exit line (the exits
are single-line flow mappings), preserving every other byte — comments,
ordering, quoting. A " to <label>" suffix is kept when it names the actual
destination room and dropped when it names a DIFFERENT room (a stale label);
labels are never invented. Idempotent: a second run finds nothing to do.

Classification (angular error between stated direction and actual bearing):
  ok        <= 45 deg   — within the direction's wedge
  minor     <= 90 deg   — approximate (adjacent compass point); acceptable
  MISMATCH   > 90 deg   — wrong way (includes 180 deg inversions); must fix
  degenerate            — rooms co-located (dx,dy ~ 0); almost always a
                          mislabelled vertical/interior move — review by hand

Usage:
  python tools/check_map_cardinals.py <area_key|path/to/map.yaml> [more ...]
  python tools/check_map_cardinals.py --all
  python tools/check_map_cardinals.py --all --derive      # print proposed fixes
  python tools/check_map_cardinals.py --all --write        # apply fixes in place
  python tools/check_map_cardinals.py --all --gate         # exit 1 if any MISMATCH
"""
from __future__ import annotations
import argparse, math, re, sys
from pathlib import Path
import yaml

MAPS_GLOB = "data/worlds/clone_wars/maps/*.yaml"

CARDINALS = {"east", "northeast", "north", "northwest",
             "west", "southwest", "south", "southeast"}
DIR_ANGLE = {"east": 0, "northeast": 45, "north": 90, "northwest": 135,
             "west": 180, "southwest": 225, "south": 270, "southeast": 315}
OPPOSITE = {"east": "west", "west": "east", "north": "south", "south": "north",
            "northeast": "southwest", "southwest": "northeast",
            "northwest": "southeast", "southeast": "northwest"}
VERTICAL = {"up", "down", "in", "out", "enter", "exit", "leave", "inside", "outside"}
STOPWORDS = {"the", "to", "of", "a", "an", "and"}
_LABEL_TBL = str.maketrans("-'", "  ")


def base_word(s: str) -> str:
    return (s or "").strip().lower().split()[0] if s and s.strip() else ""


def ang_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def nearest_octant(angle: float) -> str:
    best, bestd = "east", 999.0
    for name, a in DIR_ANGLE.items():
        d = ang_diff(angle, a)
        if d < bestd:
            bestd, best = d, name
    return best


def free_octant(angle: float, taken: set) -> tuple:
    """Nearest octant to `angle` that is not already used at this room."""
    for name in sorted(DIR_ANGLE, key=lambda n: ang_diff(angle, DIR_ANGLE[n])):
        if name not in taken:
            return name, ang_diff(angle, DIR_ANGLE[name])
    o = nearest_octant(angle)
    return o, ang_diff(angle, DIR_ANGLE[o])  # all 8 taken — best effort


def _label_of(s: str) -> str:
    parts = (s or "").split(" to ", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def _sig_words(s: str) -> set:
    return set(w for w in (s or "").lower().translate(_LABEL_TBL).split()
               if w and w not in STOPWORDS)


def _label_matches(label: str, dest_name: str) -> bool:
    """True if the " to <label>" plausibly names the destination room."""
    if not label:
        return True
    return len(_sig_words(label) & _sig_words(dest_name)) > 0


def _resolve_map_path(arg: str) -> Path:
    p = Path(arg)
    if p.suffix == ".yaml" and p.exists():
        return p
    place = arg.split(".", 1)[-1]
    cand = Path("data/worlds/clone_wars/maps") / f"{place}.yaml"
    if cand.exists():
        return cand
    sys.exit(f"could not resolve map: {arg}")


def gameplay_exit_records(p: dict):
    """Yield exit records (top-level list format carries both forward+reverse):
       (from_id, to_id, from_slug, to_slug, forward, reverse).
    Per-room inline ``exits: {dir: target}`` has no reverse — forward only."""
    rooms = p.get("rooms", []) or []
    id2slug = {r.get("id"): r.get("slug") for r in rooms}
    top = p.get("exits")
    if isinstance(top, list) and top:
        for e in top:
            yield (e.get("from"), e.get("to"),
                   id2slug.get(e.get("from")), id2slug.get(e.get("to")),
                   e.get("forward", ""), e.get("reverse", ""))
    else:
        for r in rooms:
            ex = r.get("exits") or {}
            if isinstance(ex, dict):
                for direction, target in ex.items():
                    yield (r.get("id"), None, r.get("slug"), target, direction, "")


def _room_taken_octants(recs, xy):
    """For every room, the set of planar octants ALREADY used by its exits
    (forward word lives at `from`; reverse word lives at `to`). Used so a
    re-derived word avoids colliding with the room's other exits."""
    taken = {}
    for (fid, tid, fa, fb, fwd, rev) in recs:
        if fa in xy and fb in xy:
            fw = base_word(fwd)
            if fw in CARDINALS:
                taken.setdefault(fid, set()).add(fw)
            rw = base_word(rev)
            if rw in CARDINALS:
                taken.setdefault(tid, set()).add(rw)
    return taken


def check_map(map_path: Path) -> dict:
    m = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    area_key = m.get("area_key", map_path.stem)
    planet = area_key.split(".", 1)[0]
    planet_file = map_path.parent.parent / "planets" / f"{planet}.yaml"
    if not planet_file.exists():
        return {"area_key": area_key, "error": f"planet file not found: {planet_file}"}
    p = yaml.safe_load(planet_file.read_text(encoding="utf-8"))

    # Gameplay directions vs the RENDERED coordinates (map YAML x/y) — what the
    # player sees — NOT the planet's separate map_x/map_y.
    xy = {r["slug"]: (float(r["x"]), float(r["y"])) for r in m.get("rooms", []) or []}
    name_by_slug = {r.get("slug"): r.get("name") for r in p.get("rooms", []) or []}
    recs = list(gameplay_exit_records(p))
    taken = _room_taken_octants(recs, xy)

    rows = []
    for (fid, tid, fa, fb, fwd, rev) in recs:
        if fa not in xy or fb not in xy:
            continue  # exit leaves this map's view (cross-zone) — not our concern
        (ax, ay), (bx, by) = xy[fa], xy[fb]
        # forward: word at room `from`, bearing from -> to ; dest = to
        rows.append(_classify(side="forward", room_id=fid, frm=fa, to=fb,
                              word=fwd, dx=bx - ax, dy=by - ay,
                              dest_name=name_by_slug.get(fb), taken=taken.get(fid, set())))
        # reverse: word at room `to`, bearing to -> from ; dest = from
        if rev:
            rows.append(_classify(side="reverse", room_id=tid, frm=fa, to=fb,
                                  word=rev, dx=ax - bx, dy=ay - by,
                                  dest_name=name_by_slug.get(fa), taken=taken.get(tid, set())))
    return {"area_key": area_key, "planet": planet,
            "planet_file": str(planet_file), "rows": rows}


def _classify(side, room_id, frm, to, word, dx, dy, dest_name, taken):
    bw = base_word(word)
    label = _label_of(word)
    label_ok = _label_matches(label, dest_name)
    row = dict(side=side, room_id=room_id, frm=frm, to=to, word=word, bw=bw,
               dx=dx, dy=dy, geo=None, err=None, dest_name=dest_name,
               label=label, label_ok=label_ok, taken=set(taken), kind="cardinal",
               status="skip")
    if bw in VERTICAL or bw not in CARDINALS:
        row["kind"] = "vertical/interior" if bw in VERTICAL else "non-cardinal"
        return row
    if math.hypot(dx, dy) < 1e-6:
        row["status"] = "degenerate"
        return row
    act = math.degrees(math.atan2(dy, dx)) % 360
    err = ang_diff(act, DIR_ANGLE[bw])
    row["geo"] = nearest_octant(act)
    row["err"] = err
    row["act"] = act
    row["status"] = "ok" if err <= 45 else ("minor" if err <= 90 else "mismatch")
    return row


def derive_fixes(res: dict) -> list:
    """Collision-aware corrections for every MISMATCH row. Returns proposals:
    {planet_file, frm, to, side, old, new, note}."""
    proposals = []
    # accumulate per-room taken so two fixes at the same room don't collide
    extra_taken = {}
    rows = sorted([r for r in res.get("rows", []) if r["status"] == "mismatch"],
                  key=lambda r: (r["room_id"] if r["room_id"] is not None else -1, r["err"]))
    for r in rows:
        taken = set(r["taken"]) | extra_taken.get(r["room_id"], set())
        new_oct, err = free_octant(r["act"], taken)
        keep = r["label"] and r["label_ok"]
        new_val = f"{new_oct} to {r['label']}" if keep else new_oct
        note = (f"err {err:.0f}deg; "
                + ("label kept" if keep
                   else (f"label dropped (\"{r['label']}\" names a different room; "
                         f"dest is {r['dest_name']})" if r["label"] else "no label")))
        proposals.append(dict(planet_file=res["planet_file"], frm=r["frm"], to=r["to"],
                              frm_id=None, to_id=None, side=r["side"],
                              old=r["word"], new=new_val, note=note,
                              room_id=r["room_id"]))
        extra_taken.setdefault(r["room_id"], set()).add(new_oct)
    return proposals


def summarize(res: dict) -> dict:
    c = {"ok": 0, "minor": 0, "mismatch": 0, "degenerate": 0, "skip": 0}
    for r in res.get("rows", []):
        c[r["status"]] = c.get(r["status"], 0) + 1
    return c


def print_report(res: dict, derive: bool):
    if res.get("error"):
        print(f"  ERROR: {res['error']}")
        return
    c = summarize(res)
    planar = c["ok"] + c["minor"] + c["mismatch"] + c["degenerate"]
    print(f"  checked {planar} planar word(s) [forward+reverse]: ok={c['ok']} "
          f"minor={c['minor']} MISMATCH={c['mismatch']} degenerate={c['degenerate']} "
          f"(skipped {c['skip']} vertical/interior/cross-zone)")
    proposals = {(p["frm"], p["to"], p["side"]): p for p in derive_fixes(res)} if derive else {}
    for r in res["rows"]:
        if r["status"] in ("mismatch", "degenerate"):
            tag = "MISMATCH " if r["status"] == "mismatch" else "DEGENERATE"
            extra = f"err={r['err']:.0f}deg geo={r['geo']}" if r["err"] is not None else "co-located"
            arrow = "<--reverse--" if r["side"] == "reverse" else "--forward-->"
            print(f"    {tag} [{r['side']:7s}] {r['frm']} {arrow} {r['to']}  "
                  f"dx={r['dx']:+.1f} dy={r['dy']:+.1f}  {extra}   word={r['word']!r}")
            if derive:
                pr = proposals.get((r["frm"], r["to"], r["side"]))
                if pr:
                    print(f"        propose {r['side']}: {pr['old']!r} -> {pr['new']!r}   ({pr['note']})")
                elif r["status"] == "degenerate":
                    print(f"        propose: rooms co-located — likely vertical/interior; reconcile by hand")
    # Label warnings: a " to <name>" that points at a DIFFERENT room than the
    # exit's destination (stale copy-paste label). Reported even when the
    # direction is fine, since --write won't touch a non-mismatched line.
    for r in res["rows"]:
        if r["label"] and not r["label_ok"] and r["status"] != "mismatch":
            print(f"    LABEL?   [{r['side']:7s}] {r['frm']}->{r['to']}  word={r['word']!r} "
                  f"— \"{r['label']}\" does not name dest {r['dest_name']!r} (fix by hand)")


# ── write-back ───────────────────────────────────────────────────────

_EXIT_LINE = re.compile(r'(\{[^}]*\bfrom:\s*(\d+)\s*,\s*to:\s*(\d+)\b[^}]*\})')


def _replace_field(brace: str, field: str, new_value: str) -> str:
    """Replace `field: "..."` (or unquoted) inside a flow mapping, keeping quotes."""
    # quoted form
    q = re.compile(r'(\b' + field + r':\s*")[^"]*(")')
    if q.search(brace):
        return q.sub(lambda m: m.group(1) + new_value + m.group(2), brace, count=1)
    # unquoted form: field: value  (up to , or })
    u = re.compile(r'(\b' + field + r':\s*)([^,}]*)')
    return u.sub(lambda m: m.group(1) + '"' + new_value + '"', brace, count=1)


def apply_fixes(proposals: list) -> int:
    """Apply proposals to planet YAMLs in place (line/flow-mapping scoped).
    Returns the number of fields changed."""
    by_file = {}
    for p in proposals:
        by_file.setdefault(p["planet_file"], []).append(p)
    changed = 0
    for pf, props in by_file.items():
        path = Path(pf)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        # Resolve slug->id from the file's rooms, then key proposals by (from,to).
        p_obj = yaml.safe_load(text)
        slug2id = {r.get("slug"): r.get("id") for r in p_obj.get("rooms", []) or []}
        keyed = {}
        for pr in props:
            fid, tid = slug2id.get(pr["frm"]), slug2id.get(pr["to"])
            keyed.setdefault((fid, tid), {})[pr["side"]] = pr["new"]
        out = []
        for ln in lines:
            mm = _EXIT_LINE.search(ln)
            if mm:
                fid, tid = int(mm.group(2)), int(mm.group(3))
                if (fid, tid) in keyed:
                    brace = mm.group(1)
                    new_brace = brace
                    for side, new_val in keyed[(fid, tid)].items():
                        field = "forward" if side == "forward" else "reverse"
                        nb = _replace_field(new_brace, field, new_val)
                        if nb != new_brace:
                            changed += 1
                        new_brace = nb
                    ln = ln.replace(brace, new_brace, 1)
            out.append(ln)
        path.write_text("".join(out), encoding="utf-8")
        print(f"  wrote {path}")
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("maps", nargs="*", help="area_key(s) or map .yaml path(s)")
    ap.add_argument("--all", action="store_true", help="check every map under the clone_wars maps dir")
    ap.add_argument("--derive", action="store_true", help="print geometry-consistent, collision-aware proposals")
    ap.add_argument("--write", action="store_true", help="apply proposals to the planet YAML(s) in place")
    ap.add_argument("--gate", action="store_true", help="exit 1 if any MISMATCH (forward OR reverse) is found")
    a = ap.parse_args()

    paths = ([Path(p) for p in sorted(__import__("glob").glob(MAPS_GLOB))]
             if a.all else [_resolve_map_path(x) for x in a.maps])
    if not paths:
        sys.exit("no maps to check (pass area_keys/paths or --all)")

    total = {"ok": 0, "minor": 0, "mismatch": 0, "degenerate": 0, "skip": 0}
    all_props = []
    for mp in paths:
        res = check_map(mp)
        print(f"\n=== {res.get('area_key', mp.stem)} ===")
        print_report(res, a.derive or a.write)
        if a.write:
            all_props.extend(derive_fixes(res))
        for k, v in summarize(res).items():
            total[k] = total.get(k, 0) + v

    print(f"\n=== TOTAL across {len(paths)} map(s) ===")
    print(f"  ok={total['ok']} minor={total['minor']} MISMATCH={total['mismatch']} "
          f"degenerate={total['degenerate']} skipped={total['skip']}")

    if a.write:
        if all_props:
            print(f"\n=== APPLYING {len(all_props)} correction(s) ===")
            n = apply_fixes(all_props)
            print(f"  changed {n} field(s). Re-run --gate to confirm green.")
        else:
            print("\n  nothing to write — no MISMATCH rows.")

    if a.gate and total["mismatch"]:
        print(f"\nGATE FAIL: {total['mismatch']} wrong-way cardinal exit(s) "
              f"[forward+reverse] — reconcile before painting/go-live.")
        sys.exit(1)


if __name__ == "__main__":
    main()
