#!/usr/bin/env python3
"""tools/_wire_interiors_6.py — wire the 6 remaining building interiors
(2026-06-21). These share room slugs with their parent city-overview map
(stalgasin_hive / tipoca_city / mos_eisley), which is additive-only so the
slug can't be removed there. Resolved by `is_interior: true` + the
interior-wins precedence in AreaGeometryRegistry._add: the interior binds the
slug, the city overview keeps rendering the building as a landmark.

Candidate picks are Opus-vision selections from the _review montages
(2026-06-21), confirmed by Brian for petranaki_arena.
"""
from __future__ import annotations
import re
import shutil
from pathlib import Path

from tools.mapgen import paths

SRC = Path("static/tools/_interior_test/clone_wars/maps")
DST = Path("data/worlds/clone_wars/maps")
MAPS = Path("static/maps")

# key -> chosen candidate (montage labels 0-3)
PICKS = {
    "chalmuns_cantina": "cand_02",
    "cloning_halls":    "cand_00",
    "deep_hive":        "cand_00",
    "droid_foundry":    "cand_02",
    "petranaki_arena":  "cand_02",
    "tipoca_admin":     "cand_03",
}
AREA_KEY = {
    "chalmuns_cantina": "tatooine.chalmuns_cantina",
    "cloning_halls":    "kamino.cloning_halls",
    "deep_hive":        "geonosis.deep_hive",
    "droid_foundry":    "geonosis.droid_foundry",
    "petranaki_arena":  "geonosis.petranaki_arena",
    "tipoca_admin":     "kamino.tipoca_admin",
}

DST.mkdir(parents=True, exist_ok=True)
for key, cand in PICKS.items():
    src_png = paths.BATCHES_DIR / key / "int1" / "candidates" / f"{cand}.png"
    shutil.copy2(src_png, MAPS / f"{key}_substrate.png")
    text = (SRC / f"{key}.yaml").read_text(encoding="utf-8")
    # Splice substrate_image + is_interior right after the palette: line
    # (additive, comment-preserving). Idempotent.
    add = []
    if "substrate_image:" not in text:
        add.append(f"substrate_image: /static/maps/{key}_substrate.png")
    if "is_interior:" not in text:
        add.append("is_interior: true")
    if add:
        repl = "\\1\n" + "\n".join(add)
        text = re.sub(r"(?m)^(palette: .*)$", repl, text, count=1)
    (DST / f"{key}.yaml").write_text(text, encoding="utf-8")
    print(f"  wired {key}: {cand}.png + maps/{key}.yaml (is_interior)")

# Validate: load + substrate + interior-wins binding (no leak to the city map)
from engine.area_loader import load_area_geometry, AreaGeometryRegistry
print("--- validate load + substrate ---")
for key, ak in AREA_KEY.items():
    g = load_area_geometry(ak)
    assert g.substrate_image, f"{key}: substrate_image not set"
    assert g.is_interior, f"{key}: is_interior not set"
    print(f"  OK {ak}: {len(g.rooms)} rooms, is_interior={g.is_interior}")

print("--- validate registry binding (interior wins the shared slugs) ---")
reg = AreaGeometryRegistry.load_era("clone_wars")
all_ok = True
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
        all_ok = False
        print(f"  LEAK {ak}: {bad}")
    else:
        print(f"  OK {ak}: all {sum(1 for r in g.rooms if r.slug)} slugs bind to it")
print("DONE" if all_ok else "FAILED — slug leak")
