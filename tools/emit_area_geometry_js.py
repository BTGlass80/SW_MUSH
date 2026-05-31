# -*- coding: utf-8 -*-
"""
tools/emit_area_geometry_js.py — convert AreaGeometry YAML → JS fixture.

Drop F.MAP.1 helper.

Run from project root:

    python tools/emit_area_geometry_js.py tatooine.mos_eisley \
        > static/map_v2/mos_eisley_fixture.js

The output is a JS file that exposes
`window.MOS_EISLEY_FIXTURE = { ... }` ready for inclusion by
`static/map_v2_preview.html`.

Once the live wire-up drop lands, the preview page will be replaced by
the real client surface — at that point the server emits AreaGeometry
on the wire and this generator becomes preview-only tooling.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from project root without setting PYTHONPATH manually
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.area_loader import load_area_geometry  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python tools/emit_area_geometry_js.py <area_key> [--var NAME] [--player room_id,x,y]",
              file=sys.stderr)
        return 2
    area_key = sys.argv[1]
    var_name = "AREA_GEOMETRY"
    player_args = None
    contacts_args = None
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--var" and i + 1 < len(sys.argv):
            var_name = sys.argv[i + 1]
            i += 2
        elif arg == "--player" and i + 1 < len(sys.argv):
            parts = sys.argv[i + 1].split(",")
            player_args = {
                "room_id": int(parts[0]),
                "x": float(parts[1]), "y": float(parts[2]),
            }
            i += 2
        else:
            print(f"unknown arg: {arg}", file=sys.stderr)
            return 2

    geom = load_area_geometry(area_key)
    out = geom.to_dict(
        include_player=True,
        player=player_args or {"room_id": geom.rooms[0].id,
                               "x": geom.rooms[0].x, "y": geom.rooms[0].y},
        contacts=contacts_args or [],
    )
    body = json.dumps(out, indent=2, ensure_ascii=False)
    print(f"// Auto-generated from data/worlds/clone_wars/maps/<>.yaml")
    print(f"// Regenerate via: python tools/emit_area_geometry_js.py {area_key}")
    print(f"window.{var_name} = {body};")
    return 0


if __name__ == "__main__":
    sys.exit(main())
