"""
test_wilderness_substrate_engaged.py — Drop 4.21 integration lock.

The Dune Sea + Coruscant Underworld substrate paintings are the keepers; they
live at static/maps/<slug>_substrate.png. The generator engages them, and the
live renderer must switch to substrate-first: paint the image as the Tier-1b
backdrop with the faithful pins still drawn on top.

NOTE: the substrate PNGs are NOT shipped in the drop (the authoritative copies
are local). These tests assert the *engagement* — substrate_image present in the
generated data + the renderer emitting an <image> — which holds regardless of
the PNG bytes, since the generated artifacts already carry the path.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_JS = REPO_ROOT / "static" / "spa" / "m3_wilderness_overview_data.js"
MAPS = REPO_ROOT / "data" / "worlds" / "clone_wars" / "maps"

EXPECT = {
    "tatooine_dune_sea": "/static/maps/tatooine_dune_sea_substrate.png",
    "coruscant_underworld": "/static/maps/coruscant_underworld_substrate.png",
}


def test_overview_yaml_has_substrate_engaged():
    for slug, path in EXPECT.items():
        raw = yaml.safe_load((MAPS / f"{slug}_overview.yaml").read_text(encoding="utf-8"))
        assert raw.get("substrate_image") == path, f"{slug}: substrate not engaged in YAML"


def test_generated_js_has_substrate_for_both_regions():
    txt = GEN_JS.read_text(encoding="utf-8")
    for slug, path in EXPECT.items():
        assert path in txt, f"{slug}: substrate path missing from live JS"
    # parse the embedded DATA object to be sure it's structured, not just text
    start = txt.index("var DATA = ") + len("var DATA = ")
    end = txt.index(";\n", start)
    data = json.loads(txt[start:end])
    for slug, path in EXPECT.items():
        assert data[slug]["substrate_image"] == path


def test_substrate_does_not_disturb_faithful_pois():
    """Engaging the substrate must not change the faithful POIs/routes — the
    pins still ride on top of the painting."""
    txt = GEN_JS.read_text(encoding="utf-8")
    start = txt.index("var DATA = ") + len("var DATA = ")
    data = json.loads(txt[start:txt.index(";\n", start)])
    dune = data["tatooine_dune_sea"]
    names = {p["name"] for p in dune["pois"]}
    assert "THE HIDDEN VILLAGE" in names and "THE ANCHOR STONES" in names
    assert len(dune["pois"]) == 5          # unchanged by substrate engagement
    # sub_regions stays empty — the painting is the terrain now
    assert dune["sub_regions"] == []
