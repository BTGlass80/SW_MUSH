"""
test_paint_brief_faithful.py — Drop 4.18 regression lock.

The Nano paint brief is GENERATED from the same projected grid data that
builds the seed, so the PROMPT can't drift from the map any more than the seed
can. These tests pin:

  · the shared primitives (relative placement, flavor extraction, density
    phrasing, aspect) behave;
  · the generated brief embeds the canonical master prompt, the correct
    aspect, each landmark's relative placement, and each landmark's authored
    visual (with narrative tails trimmed);
  · edge vs interior exits are phrased differently (off-map trail vs in-place
    shaft);
  · the brief invents no extra landmarks and stays era-clean.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools"
SEEDS = REPO_ROOT / "static" / "tools" / "seeds"
GEN_TOOL = TOOLS / "gen_wilderness_overview.py"

ERA_DIRTY = ["stormtrooper", "tie fighter", "x-wing", "death star",
             "rebel alliance", "darth"]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pbc():
    sys.path.insert(0, str(TOOLS))
    return _load(TOOLS / "paint_brief_common.py", "pbc_418")


@pytest.fixture(scope="module")
def gen():
    sys.path.insert(0, str(TOOLS))
    return _load(GEN_TOOL, "gen_wild_418b")


# ── primitives ─────────────────────────────────────────────────────────────

def test_relative_region_quadrants(pbc):
    W, H = 700, 600
    assert pbc.relative_region(90, 80, W, H) == "upper-left"
    assert pbc.relative_region(350, 300, W, H) == "center"
    assert pbc.relative_region(640, 410, W, H) == "lower-right"
    # y-down: a LOW y is the TOP of the frame (north)
    top = pbc.relative_region(350, 30, W, H)
    bot = pbc.relative_region(350, 570, W, H)
    assert "top" in top and "bottom" in bot


def test_relative_region_edges_are_off_map(pbc):
    W, H = 700, 600
    assert "far-west edge" in pbc.relative_region(0, 300, W, H)
    assert "far-east edge" in pbc.relative_region(700, 300, W, H)


def test_visual_from_desc_trims_narrative(pbc):
    # em-dash narrative tail dropped
    assert pbc.visual_from_desc(
        "A toppled obelisk, deliberately defaced — someone wanted it forgotten.", None
    ) == "A toppled obelisk, deliberately defaced"
    # proper-name duty sentence dropped, visual sentence kept
    out = pbc.visual_from_desc(
        "A simple gate of hand-cut sandstone blocks. Sister Vitha keeps the watch.", None)
    assert "sandstone blocks" in out and "Vitha" not in out
    # fully-visual short_desc kept intact
    assert pbc.visual_from_desc(
        "Three weathered pillars rise from the sand at irregular angles.", None
    ).startswith("Three weathered pillars")


def test_visual_falls_back_to_description(pbc):
    out = pbc.visual_from_desc("", "A black-stone obelisk lies broken across a low shelf. Older than the Republic.")
    assert "black-stone obelisk" in out


def test_aspect_phrase(pbc):
    assert pbc.aspect_phrase({"x_min": 0, "y_min": 0, "x_max": 700, "y_max": 600}) == "1.167:1"


def test_placement_clause_exit_is_edge_aware(pbc):
    W, H = 700, 600
    # an edge exit → off-map trail
    edge = pbc.placement_clause(
        [{"name": "WEST GATE", "kind": "exit", "pos": [0, 300]}], W, H)
    assert "off-map" in edge and "leaving the frame" in edge
    # an interior exit → in-place access point (stair/shaft), NOT off-map
    interior = pbc.placement_clause(
        [{"name": "SHAFT", "kind": "exit", "pos": [350, 300]}], W, H)
    assert "access point" in interior and "off-map" not in interior


# ── generated brief ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def dune_brief(gen):
    ov = gen.build_overview(
        REPO_ROOT / "data/worlds/clone_wars/wilderness/dune_sea.yaml",
        REPO_ROOT / "static" / "maps")
    return ov


def test_brief_files_present():
    for slug in ("tatooine_dune_sea", "coruscant_underworld"):
        p = SEEDS / f"{slug}_paint_brief.md"
        assert p.exists(), f"missing generated brief: {p}"
        txt = p.read_text(encoding="utf-8")
        assert "GENERATED" in txt and "DO NOT HAND-EDIT" in txt


def test_dune_brief_has_master_prompt_and_aspect():
    txt = (SEEDS / "tatooine_dune_sea_paint_brief.md").read_text(encoding="utf-8")
    # canonical master-prompt anchors
    assert "BASE LAYER ONLY" in txt
    assert "absolutely NO" in txt and "TEXT" in txt
    assert "1.167:1 aspect ratio" in txt


def test_dune_brief_places_each_landmark_relatively():
    txt = (SEEDS / "tatooine_dune_sea_paint_brief.md").read_text(encoding="utf-8")
    assert "THE HIDDEN VILLAGE center" in txt
    assert "RUINED OBELISK upper-left" in txt
    assert "THE ANCHOR STONES lower-right" in txt
    assert "HERMIT'S HUT lower-center" in txt
    # the Jundland exit is an off-map trail, not a structure
    assert "far-west edge" in txt and "leaving the frame" in txt


def test_dune_brief_embeds_authored_visuals():
    txt = (SEEDS / "tatooine_dune_sea_paint_brief.md").read_text(encoding="utf-8")
    assert "Three weathered pillars rise from the sand" in txt
    assert "toppled obelisk, deliberately defaced" in txt
    # narrative tail must NOT leak into the brief
    assert "someone wanted it forgotten" not in txt
    assert "Vitha" not in txt


def test_dune_brief_states_dominant_terrain_and_count():
    txt = (SEEDS / "tatooine_dune_sea_paint_brief.md").read_text(encoding="utf-8")
    assert "open rolling sand dunes almost everywhere" in txt
    # honesty line: keep features spaced, name the real count
    assert "keep generous open ground between the 4 features" in txt
    assert "no other major landmarks" in txt


def test_underworld_brief_interior_exit_is_shaft():
    txt = (SEEDS / "coruscant_underworld_paint_brief.md").read_text(encoding="utf-8")
    # the surface entry sits mid-grid → in-place shaft phrasing, not off-map
    assert "SURFACE ENTRY" in txt
    assert "access point" in txt
    assert "ferrocrete" in txt          # dark-strata terrain, not desert


def test_briefs_are_era_clean():
    for slug in ("tatooine_dune_sea", "coruscant_underworld"):
        txt = (SEEDS / f"{slug}_paint_brief.md").read_text(encoding="utf-8").lower()
        for tok in ERA_DIRTY:
            assert tok not in txt, f"{slug}: era-dirty token {tok!r}"


def test_brief_count_matches_real_landmarks(dune_brief, gen):
    """The brief paints exactly the real landmark count (no invented POIs)."""
    real = [n for n in dune_brief["nodes"] if n.get("kind") != "exit"]
    assert len(real) == 4   # obelisk, anchor, hermit, collapsed village
