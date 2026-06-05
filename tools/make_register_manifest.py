#!/usr/bin/env python3
"""make_register_manifest.py — generate a registration manifest from a map YAML.

Phase 1b of the map-substrate lane. Turns any
``data/worlds/<era>/maps/<place>.yaml`` into the JSON manifest that
``static/tools/map_register.html`` consumes via ``?manifest=<url>`` — so
registering a new city is: run this, open the tool, drag, export. No more
hand-editing the tool's HTML per area.

Coordinate model (must match the tool's ``fracToWorld`` exactly).
The substrate is authored NORTH-UP filling the world bounds rect. A
landmark's authored world coord (Y-up) maps to an image fraction:
    fx = (wx - x_min) / (x_max - x_min)          # left→right
    fy = (y_max - wy) / (y_max - y_min)          # top→bottom (inverted)
This is the inverse of the tool's pin→world conversion, so a manifest
generated from existing ``landmarks:`` re-seeds each pin exactly where it
already sits. Drag only what the painting shows is off.

Distinctive vs generic. Landmarks whose ``icon`` is in DISTINCTIVE_ICONS
(or whose id is in DISTINCTIVE_IDS) are flagged ``distinctive: true`` so
the tool renders them as "place precisely" pins; everything else is
"approx OK". Tune the sets below per the painting if needed.

Usage:
    python tools/make_register_manifest.py tatooine.mos_eisley
    python tools/make_register_manifest.py tatooine.mos_eisley \\
        --substrate /static/maps/mos_eisley_substrate.png \\
        --out static/tools/manifests/tatooine.mos_eisley.json

If --out is omitted, prints JSON to stdout. If --substrate is omitted,
uses the YAML's substrate_image when present, else a conventional guess
(/static/maps/<place>_substrate.png).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

# Icons that correspond to visually distinctive painted features — the
# ~handful a player can actually verify. Everything else is an
# unfalsifiable dome only needing to be in-zone. Off-map directional
# pointers (name contains ↗ etc.) are forced non-distinctive regardless
# of icon, so monumental icons like `palace` are safe here even though
# Mos Eisley uses `palace` for the off-map Jabba's Palace pointer.
DISTINCTIVE_ICONS = {
    # city features
    "dock", "ship", "wreck", "cantina", "bones", "palace",
    # wilderness / underworld POI features (Drop 4.16) — distinctive painted
    # landmarks a player can actually verify on the substrate
    "farm", "tents", "pit", "spire", "shaft", "factory", "hideout", "maze",
}
# Explicit id overrides (e.g. a beacon that IS a painted landmark, or a
# generic-icon thing you nonetheless want placed precisely).
DISTINCTIVE_IDS: set[str] = set()
# ids that are off-map directional pointers (edge placement is fine).
OFFMAP_HINT = ("\u2197", "\u2199", "\u2196", "\u2198")  # ↗ ↙ ↖ ↘ in the name


def _repo_root() -> Path:
    # tools/ lives at project root.
    return Path(__file__).resolve().parent.parent


def _resolve_map_path(area_key: str, era: str, worlds_root: Path) -> Path:
    place = area_key.rsplit(".", 1)[-1] if "." in area_key else area_key
    return worlds_root / era / "maps" / f"{place}.yaml"


def build_manifest(area_key: str, *, era: str, worlds_root: Path,
                   substrate: str | None) -> dict:
    path = _resolve_map_path(area_key, era, worlds_root)
    if not path.exists():
        raise SystemExit(f"map YAML not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"map YAML is not a mapping: {path}")

    bounds = raw.get("bounds")
    if not bounds or any(k not in bounds for k in ("x_min", "y_min", "x_max", "y_max")):
        raise SystemExit(f"map YAML missing complete bounds: {path}")
    x_min, y_min = float(bounds["x_min"]), float(bounds["y_min"])
    x_max, y_max = float(bounds["x_max"]), float(bounds["y_max"])
    dx = (x_max - x_min) or 1.0
    dy = (y_max - y_min) or 1.0

    if substrate is None:
        place = area_key.rsplit(".", 1)[-1] if "." in area_key else area_key
        substrate = raw.get("substrate_image") or f"/static/maps/{place}_substrate.png"

    def world_to_frac(wx: float, wy: float) -> tuple[float, float]:
        fx = (wx - x_min) / dx
        # Drop 4.17: overview pos is SVG-space (y DOWN, north=top), matching
        # the seed tool (no-flip) and the renderer; the substrate painting is
        # in that same space, so the pin fraction must NOT be inverted.
        fy = (wy - y_min) / dy
        # clamp into [0,1] so off-bounds points still render a draggable pin
        return (min(max(fx, 0.0), 1.0), min(max(fy, 0.0), 1.0))

    landmarks_out = []
    for lm in (raw.get("landmarks") or []):
        if not isinstance(lm, dict):
            continue
        pos = lm.get("pos")
        if not (isinstance(pos, (list, tuple)) and len(pos) >= 2):
            continue
        fx, fy = world_to_frac(float(pos[0]), float(pos[1]))
        icon = str(lm.get("icon", "beacon"))
        lid = str(lm.get("id", ""))
        name = str(lm.get("name", lid or "?"))
        offmap = any(h in name for h in OFFMAP_HINT)
        distinctive = (not offmap) and (
            icon in DISTINCTIVE_ICONS or lid in DISTINCTIVE_IDS
        )
        if offmap:
            note = "off-map pointer — edge is fine"
        elif distinctive:
            note = f"distinctive painted feature — place on the {icon}"
        else:
            note = "indistinct / generic — approximate is fine"
        landmarks_out.append({
            "id": lid,
            "icon": icon,
            "name": name,
            "distinctive": distinctive,
            "fx": round(fx, 4),
            "fy": round(fy, 4),
            "note": note,
            "min_zoom": int(lm.get("min_zoom", 2)),
            "max_zoom": int(lm.get("max_zoom", 3)),
        })

    return {
        "area_key": raw.get("area_key", area_key),
        "display_name": raw.get("display_name", area_key),
        "substrate": substrate,
        "bounds": {"x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max},
        "landmarks": landmarks_out,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("area_key", help="e.g. tatooine.mos_eisley")
    ap.add_argument("--era", default="clone_wars")
    ap.add_argument("--worlds-root", default=None,
                    help="defaults to <repo>/data/worlds")
    ap.add_argument("--substrate", default=None,
                    help="override the substrate image URL")
    ap.add_argument("--out", default=None,
                    help="write JSON here (default: stdout). Parent dirs created.")
    args = ap.parse_args(argv)

    worlds_root = (Path(args.worlds_root) if args.worlds_root
                   else _repo_root() / "data" / "worlds")
    manifest = build_manifest(args.area_key, era=args.era,
                              worlds_root=worlds_root, substrate=args.substrate)
    text = json.dumps(manifest, indent=2, ensure_ascii=False)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        n = len(manifest["landmarks"])
        d = sum(1 for l in manifest["landmarks"] if l["distinctive"])
        print(f"wrote {out}  ({n} landmarks, {d} distinctive)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
