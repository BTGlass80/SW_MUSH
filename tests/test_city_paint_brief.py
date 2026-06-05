"""
test_city_paint_brief.py — Drop 4.19 regression lock.

The city paint brief is generated from the real city map (maps/<key>.yaml):
districts, rooms, and landmarks at their authored positions. These tests pin
that the generated brief places each real landmark by its true relative
region, characterizes each district where it sits, pulls IP-safe per-icon
visuals, and respects off-map markers — for Mos Eisley.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools"
SEEDS = REPO_ROOT / "static" / "tools" / "seeds"
GEN = TOOLS / "gen_city_paint_brief.py"
MOS = REPO_ROOT / "data" / "worlds" / "clone_wars" / "maps" / "mos_eisley.yaml"

ERA_DIRTY = ["stormtrooper", "tie fighter", "x-wing", "death star", "rebel alliance"]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen():
    sys.path.insert(0, str(TOOLS))
    return _load(GEN, "gen_city_419")


@pytest.fixture(scope="module")
def ci(gen):
    return gen.build_city_brief(MOS)


def test_reads_real_districts_rooms_landmarks(ci):
    assert ci["slug"] == "mos_eisley"
    assert ci["n_rooms"] == 53           # real background room count
    assert len(ci["districts"]) == 7     # 7 districts in the map
    # 9 landmarks total, 2 of which are off-map (Jabba's Palace, Sarlacc)
    assert ci["n_real"] == 7


def test_landmarks_placed_by_true_region(gen, ci):
    txt = gen.render_geography(ci)
    # Docking Bay 94 is at pos [2.6,-1.4] → lower-left of the frame
    assert "DOCKING BAY 94 lower-left" in txt
    # Hyperspace Beacon at [3.5,6] → upper-left (high world-y = north = top)
    assert "HYPERSPACE BEACON upper-left" in txt
    # Krayt Graveyard at far-east x → east edge
    assert "KRAYT GRAVEYARD" in txt and "far-east edge" in txt


def test_offmap_landmark_is_leaving_frame_even_if_interior(gen, ci):
    """Jabba's Palace carries a '↗' and sits interior-upper-right; it must read
    as an off-map direction (leaving the frame), NOT an in-place shaft."""
    txt = gen.render_geography(ci)
    assert "JABBA'S PALACE" in txt
    seg = txt[txt.index("JABBA'S PALACE"):txt.index("JABBA'S PALACE") + 140]
    assert "off-map direction" in seg and "leaving the frame" in seg
    assert "stairwell" not in seg


def test_districts_characterized_and_placed(gen, ci):
    txt = gen.render_geography(ci)
    assert "SPACEPORT" in txt and "docking pits" in txt
    assert "MARKET QUARTER" in txt and "market quarter" in txt
    assert "CANTINA ROW" in txt and "cantinas" in txt
    # each district line carries a relative region in parens
    assert "(lower-center)" in txt or "(center)" in txt


def test_per_icon_visuals_are_ip_safe(gen, ci):
    txt = gen.render_geography(ci)
    # icon → authored "Say" vocabulary, no franchise names in the visual lines
    assert "a circular landing pad" in txt                 # dock (world-agnostic)
    assert "grounded vessel repurposed" in txt             # ship
    assert "notorious cantina" in txt                      # cantina
    assert "field of giant bleached skeletal bones" in txt # bones (desert landmark)


def test_generated_brief_file_present_and_clean():
    p = SEEDS / "mos_eisley_paint_brief.md"
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    assert "GENERATED" in txt and "DO NOT HAND-EDIT" in txt
    assert "BASE LAYER ONLY" in txt           # master prompt embedded
    assert "1.046:1 aspect ratio" in txt      # aspect from real bounds
    low = txt.lower()
    for tok in ERA_DIRTY:
        assert tok not in low


def test_background_room_count_in_brief(gen, ci):
    txt = gen.render_geography(ci)
    # the brief tells Nano how many background buildings to fill generically
    assert "53 ordinary background buildings" in txt
    assert "no other major landmarks" in txt


def test_non_desert_districts_read_correctly(gen):
    """Kamino (tipoca) must read as a storm-ocean stilt-city, not desert —
    proves the district vocabulary covers other worlds, no generic fallback."""
    tip = REPO_ROOT / "data" / "worlds" / "clone_wars" / "maps" / "tipoca_city.yaml"
    txt = gen.render_geography(gen.build_city_brief(tip))
    assert "ocean" in txt and "stilts" in txt
    assert "sand" not in txt and "desert" not in txt
    assert "built-up urban ground" not in txt   # no fallback used


@pytest.mark.parametrize("slug", ["kuat_city", "senate_district", "smugglers_moon",
                                  "stalgasin_hive", "tipoca_city"])
def test_other_city_briefs_present_and_clean(slug):
    p = SEEDS / f"{slug}_paint_brief.md"
    assert p.exists(), f"missing generated brief: {p}"
    txt = p.read_text(encoding="utf-8")
    assert "GENERATED" in txt and "BASE LAYER ONLY" in txt
    low = txt.lower()
    for tok in ERA_DIRTY:
        assert tok not in low
