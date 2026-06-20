#!/usr/bin/env python3
"""tools/_wire_interiors.py — wire the 3 un-mapped building interiors into the
live map system (2026-06-20). Each becomes a real tier-1a AreaGeometry (the
senate_district pattern): a maps/*.yaml with room slugs + a substrate_image PNG;
AreaGeometryRegistry.load_era auto-discovers it + binds its rooms by slug.

Only the COLLISION-FREE interiors are wired (their room slugs appear in no other
maps/*.yaml): jedi_temple, coruscant_works, gladiator_barracks. The 6 interiors
whose rooms already live in a city map are NOT wired (slug collision).
"""
from __future__ import annotations
import re
import shutil
from pathlib import Path

from tools.mapgen import paths
import tools.make_interior_zonemap as gen

SRC = Path("static/tools/_interior_test/clone_wars/maps")
DST = Path("data/worlds/clone_wars/maps")
MAPS = Path("static/maps")

# key -> (batch dir, chosen candidate)  [Opus picks, 2026-06-20]
PICKS = {
    "jedi_temple":        ("jedi_temple",        "cand_00"),
    "coruscant_works":    ("coruscant_works",    "cand_01"),
    "gladiator_barracks": ("gladiator_barracks", "cand_00"),
}
AREA_KEY = {
    "jedi_temple":        "coruscant.jedi_temple",
    "coruscant_works":    "coruscant.coruscant_works",
    "gladiator_barracks": "geonosis.gladiator_barracks",
}

# 1. regenerate the 2 that needed the `zone` fix (jedi_temple is hand-authored).
gen.main(["--only", "coruscant_works,gladiator_barracks"])

DST.mkdir(parents=True, exist_ok=True)
for key, (batch, cand) in PICKS.items():
    # 2. copy the chosen painting -> static/maps/<key>_substrate.png
    src_png = paths.BATCHES_DIR / batch / "int1" / "candidates" / f"{cand}.png"
    shutil.copy2(src_png, MAPS / f"{key}_substrate.png")
    # 3. read the test-root zone-map, splice in substrate_image, write to data/worlds
    text = (SRC / f"{key}.yaml").read_text(encoding="utf-8")
    if "substrate_image:" not in text:
        text = re.sub(r"(?m)^(palette: .*)$",
                      r"\1\nsubstrate_image: /static/maps/" + key + "_substrate.png",
                      text, count=1)
    (DST / f"{key}.yaml").write_text(text, encoding="utf-8")
    print(f"  wired {key}: substrate {cand}.png + maps/{key}.yaml")

# 4. validate: each loads, and the registry binds its slugs to ITS area (no collision)
from engine.area_loader import load_area_geometry, AreaGeometryRegistry
print("--- validate load + substrate ---")
for key, ak in AREA_KEY.items():
    g = load_area_geometry(ak)
    assert g.substrate_image, f"{key}: substrate_image not set"
    print(f"  OK {ak}: {len(g.rooms)} rooms, substrate={g.substrate_image}")

print("--- validate registry binding (no slug collision) ---")
reg = AreaGeometryRegistry.load_era("clone_wars")
for key, ak in AREA_KEY.items():
    g = load_area_geometry(ak)
    bad = []
    for r in g.rooms:
        if not r.slug:
            continue
        e = reg.lookup(r.slug)
        if e is None or e.area_key != ak:
            bad.append((r.slug, None if e is None else e.area_key))
    if bad:
        print(f"  COLLISION {ak}: {bad}")
    else:
        print(f"  OK {ak}: all {sum(1 for r in g.rooms if r.slug)} slugs bind to it")
print("DONE")
