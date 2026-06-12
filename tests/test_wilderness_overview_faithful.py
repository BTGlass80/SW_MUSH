"""
test_wilderness_overview_faithful.py — Drop 4.17 regression lock.

The Tier-1b wilderness overview is now GENERATED from the navigable grid
(tools/gen_wilderness_overview.py), not hand-authored. These tests pin the
property that makes it a real navigation aid: POIs sit where the real
landmarks actually are on the grid, and the seed / manifest / live-renderer
all read the same coordinate frame.

Pins:
  · Generator merges the real roster (region YAML + landmark_includes,
    region-filtered) and projects grid coords → overview space.
  · Projection is north-up / SVG-y-down: higher grid y → LOWER overview y.
  · Relative positions are preserved (obelisk stays NW of the village, etc.)
    — fidelity to the grid, not to any hand-placed fiction.
  · The village cluster (≥2 village_interior rooms) collapses to ONE POI.
  · Region exits (edges) appear as generic (non-distinctive) markers.
  · Generated overview YAML + manifest agree on the y-down convention
    (north → low fy).
  · The seed tool's --wilderness projector is no-flip (matches the renderer).
  · m3_tier_wilderness_body.resolveRegion PREFERS the generated data over the
    built-in showcase fixtures, and the generated data is wired into
    client.html's script loads before the wilderness body.
  · Era-clean; no invented terrain_zones (empty by design).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WILD_DIR  = REPO_ROOT / "data" / "worlds" / "clone_wars" / "wilderness"
MAPS_DIR  = REPO_ROOT / "data" / "worlds" / "clone_wars" / "maps"
GEN_TOOL  = REPO_ROOT / "tools" / "gen_wilderness_overview.py"
SEED_TOOL = REPO_ROOT / "tools" / "make_substrate_seed.py"
MANI_TOOL = REPO_ROOT / "tools" / "make_register_manifest.py"
GEN_JS    = REPO_ROOT / "static" / "spa" / "m3_wilderness_overview_data.js"
WILD_JS   = REPO_ROOT / "static" / "spa" / "m3_tier_wilderness_body.js"
CLIENT    = REPO_ROOT / "static" / "client.html"

DUNE_REGION = WILD_DIR / "dune_sea.yaml"
UW_REGION   = WILD_DIR / "coruscant_underworld.yaml"

ERA_DIRTY = ["empire", "imperial", "stormtrooper", "tie fighter", "x-wing",
             "death star", "rebel alliance"]


def _load_tool(path, name):
    # The substrate-seed tool imports Pillow (PIL) for raster rendering.
    # Skip (don't fail) the tests that load it when Pillow isn't installed
    # — these are optional art-pipeline tool tests, not core game logic.
    if "make_substrate_seed" in str(path):
        pytest.importorskip("PIL", reason="make_substrate_seed.py requires Pillow")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen():
    return _load_tool(GEN_TOOL, "gen_wild_417")


# ════════════════════════════════════════════════════════════════════
# Roster merge — real landmarks, region-filtered includes
# ════════════════════════════════════════════════════════════════════

def test_dune_roster_includes_real_landmarks(gen):
    slug, grid, roster = gen.load_roster(DUNE_REGION)
    assert slug == "tatooine_dune_sea"
    ids = {lm["id"] for lm in roster}
    # the real anchors must be present; the decorative POIs must NOT exist
    assert "dune_sea_anchor_stones" in ids
    assert "village_common_square" in ids
    assert "sarlacc_pit" not in ids and "bantha_herd" not in ids


def test_underworld_roster_from_includes_region_filtered(gen):
    """Underworld has no inline landmarks; the roster comes entirely from
    landmark_includes, filtered to this region."""
    slug, grid, roster = gen.load_roster(UW_REGION)
    assert slug == "coruscant_underworld"
    ids = {lm["id"] for lm in roster}
    assert "black_sun_crawler_hideout" in ids
    assert "forgotten_jedi_shrine" in ids        # from force_resonant, region-matched
    # a different region's force-resonant landmark must be filtered out
    assert "bantha_graveyard" not in ids          # tatooine_jundland


# ════════════════════════════════════════════════════════════════════
# Projection — north-up, grid-faithful, relative positions preserved
# ════════════════════════════════════════════════════════════════════

def test_projection_is_north_up(gen):
    # higher grid y (more north) must map to LOWER overview y (toward top)
    gw = gh = 40
    _, north_y = gen.project(20, 39, gw, gh)
    _, south_y = gen.project(20, 0, gw, gh)
    assert north_y < south_y
    # west→east preserved on x
    west_x, _ = gen.project(0, 20, gw, gh)
    east_x, _ = gen.project(39, 20, gw, gh)
    assert west_x < east_x


def test_overview_preserves_relative_positions(gen):
    """The generated overview must keep the grid's relative geometry: the
    obelisk (grid [29,24], north + west of the village ~[34.6,18.2]) must be
    above-and-left of the village in overview space."""
    ov = gen.build_overview(DUNE_REGION, REPO_ROOT / "static" / "maps")
    by_id = {n["id"]: n for n in ov["nodes"]}
    village = by_id["tatooine_dune_sea_village"]
    obelisk = by_id["dune_sea_ruined_obelisk"]
    anchor = by_id["dune_sea_anchor_stones"]
    # obelisk north of village → smaller y; west of village → smaller x
    assert obelisk["pos"][1] < village["pos"][1]
    assert obelisk["pos"][0] < village["pos"][0]
    # anchor stones east of the village (grid x 38 > 34.6) → larger x
    assert anchor["pos"][0] > village["pos"][0]


def test_village_cluster_collapsed(gen):
    ov = gen.build_overview(DUNE_REGION, REPO_ROOT / "static" / "maps")
    ids = [n["id"] for n in ov["nodes"]]
    # exactly one village node, none of the raw village_* rooms survive
    assert ids.count("tatooine_dune_sea_village") == 1
    assert not any(i.startswith("village_") for i in ids)
    assert ov["n_cluster"] >= 2


def test_region_exit_is_generic_marker(gen):
    ov = gen.build_overview(DUNE_REGION, REPO_ROOT / "static" / "maps")
    exits = [n for n in ov["nodes"] if n["kind"] == "exit"]
    assert len(exits) >= 1
    assert all(not e["distinctive"] for e in exits)


def test_routes_from_adjacency_remapped(gen):
    """Adjacency into the village must remap to the single village node
    (no self-loops, real edges preserved)."""
    ov = gen.build_overview(DUNE_REGION, REPO_ROOT / "static" / "maps")
    # anchor_stones ↔ obelisk is a real adjacency → a route must connect them
    by_id = {n["id"]: tuple(n["pos"]) for n in ov["nodes"]}
    a = by_id["dune_sea_anchor_stones"]
    o = by_id["dune_sea_ruined_obelisk"]
    pairs = {frozenset((tuple(r[0]), tuple(r[1]))) for r in ov["routes"]}
    assert frozenset((a, o)) in pairs


# ════════════════════════════════════════════════════════════════════
# Generated artifacts on disk
# ════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("slug", ["tatooine_dune_sea", "coruscant_underworld"])
def test_generated_overview_yaml_present_and_clean(slug):
    p = MAPS_DIR / f"{slug}_overview.yaml"
    assert p.exists()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert raw["bounds"] == {"x_min": 0, "y_min": 0, "x_max": 700, "y_max": 600}
    # terrain_zones is empty by design (atmosphere comes from the prompt)
    assert raw["terrain_zones"] == []
    # every landmark carries its source grid coord (provenance / fidelity)
    for lm in raw["landmarks"]:
        assert "grid" in lm and len(lm["grid"]) == 2
        assert 0 <= lm["pos"][0] <= 700 and 0 <= lm["pos"][1] <= 600
    txt = p.read_text(encoding="utf-8").lower()
    for tok in ERA_DIRTY:
        assert tok not in txt


def test_manifest_y_convention_matches_overview():
    """North landmark (low overview y) → low fy. Confirms the manifest tool
    is NOT inverting y (which it used to, for the old y-up convention)."""
    mod = _load_tool(MANI_TOOL, "mani_417")
    manifest = mod.build_manifest("tatooine_dune_sea_overview", era="clone_wars",
                                  worlds_root=REPO_ROOT / "data" / "worlds",
                                  substrate=None)
    by_id = {l["id"]: l for l in manifest["landmarks"]}
    # obelisk is the northernmost (grid y=24) → should have the smallest fy
    obelisk_fy = by_id["dune_sea_ruined_obelisk"]["fy"]
    hermit_fy = by_id["hermit_hut"]["fy"]          # grid y=16 (south)
    assert obelisk_fy < hermit_fy


def test_seed_projector_is_no_flip():
    """render_wilderness must project y WITHOUT a flip, so the seed agrees
    with the renderer + overview (north=top=low y)."""
    src = SEED_TOOL.read_text(encoding="utf-8")
    # the old north-up flip (y1 - wy) must be gone from the wilderness path
    assert "(wy - y0)" in src
    # guard: ensure we didn't leave the flipped form in render_wilderness
    rw = src[src.index("def render_wilderness"):]
    assert "y1 - wy" not in rw[:rw.index("if __name__")]


# ════════════════════════════════════════════════════════════════════
# Renderer wiring — prefers generated data, loaded in client.html
# ════════════════════════════════════════════════════════════════════

def test_generated_js_present_and_valid():
    assert GEN_JS.exists()
    txt = GEN_JS.read_text(encoding="utf-8")
    assert "M3WildernessOverviewData" in txt
    assert "tatooine_dune_sea" in txt and "coruscant_underworld" in txt
    assert "GENERATED" in txt and "DO NOT HAND-EDIT" in txt


def test_resolveRegion_prefers_generated_data():
    src = WILD_JS.read_text(encoding="utf-8")
    # resolveRegion must consult the generated table before REGIONS
    fn = src[src.index("function resolveRegion"):]
    fn = fn[:fn.index("\n}")]
    assert "M3WildernessOverviewData" in fn
    # the generated lookup precedes the REGIONS fallback
    assert fn.index("M3WildernessOverviewData") < fn.index("REGIONS[")


def test_client_html_loads_generated_before_body():
    src = CLIENT.read_text(encoding="utf-8")
    gen_load = src.find("m3_wilderness_overview_data.js")
    body_load = src.find("m3_tier_wilderness_body.js")
    assert gen_load != -1 and body_load != -1
    assert gen_load < body_load, "generated data must load before the body"


# ════════════════════════════════════════════════════════════════════
# Seed renders from the faithful spec
# ════════════════════════════════════════════════════════════════════

def test_wilderness_seed_renders_from_faithful_spec(tmp_path):
    mod = _load_tool(SEED_TOOL, "seed_417")
    sp, kp = mod.render_wilderness(
        "tatooine_dune_sea_overview", era="clone_wars",
        root=str(REPO_ROOT / "data" / "worlds"),
        out=str(tmp_path), long_edge=1024, tight=True)
    assert sp.exists() and kp.exists()
    from PIL import Image
    w, h = Image.open(sp).size
    assert w == 1024 and abs(w / h - 700 / 600) < 0.02
