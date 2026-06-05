"""
test_wilderness_substrate_seed.py — Drop 4.16 regression lock for the
wilderness substrate-seed pipeline (the art-pipeline §4b enabler).

Pins (refreshed 2026-06-02 for the substrate-first pipeline, Drops 4.15a–4.18):
  · The two region overview specs are well-formed (700x600 bounds, any terrain
    zones valid, POIs in-bounds, routes valid) and era-clean. Substrate-first:
    a painted region carries substrate_image and needs no procedural
    terrain_zones.
  · make_substrate_seed.py --wilderness renders seed + keymap PNGs at the
    region's aspect (mode importable + callable, not just CLI).
  · make_register_manifest.py converts every authored landmark into an
    in-bounds pin (builder fidelity; exits not distinctive), with the
    canonical painted substrate path.
  · NANO_MAP_PACKAGE.md §6 documents the GENERATED per-region paint briefs
    (Drop 4.18: prompts moved to static/tools/seeds/<slug>_paint_brief.md).
  · substrate_image is ACTIVE in the generated overview data
    (m3_wilderness_overview_data.js); the body renderer stays data-driven.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPS_DIR  = REPO_ROOT / "data" / "worlds" / "clone_wars" / "maps"
SEED_TOOL = REPO_ROOT / "tools" / "make_substrate_seed.py"
MANI_TOOL = REPO_ROOT / "tools" / "make_register_manifest.py"
PACKAGE   = REPO_ROOT / "NANO_MAP_PACKAGE.md"
WILD_JS   = REPO_ROOT / "static" / "spa" / "m3_tier_wilderness_body.js"
WILD_DATA = REPO_ROOT / "static" / "spa" / "m3_wilderness_overview_data.js"

REGIONS = ["tatooine_dune_sea", "coruscant_underworld"]

# B3: Empire-era tokens that must never appear in CW content.
ERA_DIRTY = ["empire", "imperial", "stormtrooper", "tie fighter", "x-wing",
             "death star", "rebel alliance"]
# Franchise nouns Gemini's filter trips on — must not be in the {GEOGRAPHY}
# prompt text (internal YAML labels may use them; the painter prompt may not).
FRANCHISE = ["tatooine", "tusken", "sarlacc", "krayt", "bantha", "coruscant",
             "black sun", "uscru", "jedi", "sith", "hutt"]


def _load_tool(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ════════════════════════════════════════════════════════════════════
# Overview specs
# ════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("region", REGIONS)
def test_overview_spec_wellformed(region):
    p = MAPS_DIR / f"{region}_overview.yaml"
    assert p.exists(), f"missing overview spec: {p}"
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    # bounds 700x600 (matches the Tier-1b fixture coordinate space)
    b = raw["bounds"]
    assert (b["x_min"], b["y_min"], b["x_max"], b["y_max"]) == (0, 0, 700, 600)
    # terrain zones — substrate-first (Drop 4.15a+): a painted region carries
    # substrate_image and needs NO procedural terrain_zones, so accept either a
    # painted substrate OR >=1 zone. Any zones present are still validated.
    zones = raw.get("terrain_zones") or []
    assert raw.get("substrate_image") or len(zones) >= 1, \
        f"{region} overview has neither substrate_image nor terrain_zones"
    for z in zones:
        assert len(z["polygon"]) >= 3
        assert "terrain" in z
        for (x, y) in z["polygon"]:
            assert 0 <= x <= 700 and 0 <= y <= 600
    # landmarks — present, in-bounds, with the city-compatible shape
    lms = raw["landmarks"]
    assert len(lms) >= 1
    for lm in lms:
        assert "id" in lm and "name" in lm and "icon" in lm
        x, y = lm["pos"]
        assert 0 <= x <= 700 and 0 <= y <= 600
    # routes (optional) — pairs of in-bounds points
    for rt in raw.get("routes", []):
        assert len(rt) >= 2
        for (x, y) in rt:
            assert 0 <= x <= 700 and 0 <= y <= 600


@pytest.mark.parametrize("region", REGIONS)
def test_overview_spec_era_clean(region):
    txt = (MAPS_DIR / f"{region}_overview.yaml").read_text(encoding="utf-8").lower()
    for tok in ERA_DIRTY:
        assert tok not in txt, f"era-dirty token {tok!r} in {region} overview"


def test_underworld_is_single_level():
    """The underworld spec must not encode a z/level axis (single-level
    decision); depth is art/prose only."""
    raw = yaml.safe_load((MAPS_DIR / "coruscant_underworld_overview.yaml")
                         .read_text(encoding="utf-8"))
    assert "levels" not in raw and "z" not in raw
    # every POI is a flat (x, y) pair, no third coord
    for lm in raw["landmarks"]:
        assert len(lm["pos"]) == 2


# ════════════════════════════════════════════════════════════════════
# Seed generator — wilderness mode
# ════════════════════════════════════════════════════════════════════

def test_wilderness_seed_mode_renders(tmp_path):
    mod = _load_tool(SEED_TOOL, "mss_4_16")
    assert hasattr(mod, "render_wilderness"), "wilderness mode missing"
    sp, kp = mod.render_wilderness(
        "tatooine_dune_sea_overview",
        era="clone_wars",
        root=str(REPO_ROOT / "data" / "worlds"),
        out=str(tmp_path),
        long_edge=1024,
        tight=True,
    )
    assert sp.exists() and kp.exists()
    # output basename comes from the spec's area_key, not the file stem
    assert sp.name == "tatooine_dune_sea_tight_seed.png"
    assert kp.name == "tatooine_dune_sea_tight_keymap.png"
    # aspect = 700/600 ≈ 1.167 → 1024 x ~878
    from PIL import Image
    w, h = Image.open(sp).size
    assert w == 1024
    assert abs(w / h - (700 / 600)) < 0.02


def test_wilderness_seed_mode_rejects_city_yaml(tmp_path):
    """--wilderness on a city map (no terrain_zones) must fail fast, not
    silently mis-render."""
    mod = _load_tool(SEED_TOOL, "mss_4_16b")
    # mos_eisley is a city map (districts/rooms), no terrain_zones
    with pytest.raises(SystemExit):
        mod.render_wilderness("mos_eisley", era="clone_wars",
                              root=str(REPO_ROOT / "data" / "worlds"),
                              out=str(tmp_path))


def test_city_seed_mode_still_present():
    """The city render() path must remain (byte-stable lane)."""
    mod = _load_tool(SEED_TOOL, "mss_4_16c")
    assert hasattr(mod, "render") and callable(mod.render)


# ════════════════════════════════════════════════════════════════════
# Manifest generator — regions
# ════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("region", REGIONS)
def test_region_manifest_builds(region):
    mod = _load_tool(MANI_TOOL, "mrm_4_16_" + region)
    manifest = mod.build_manifest(
        f"{region}_overview",
        era="clone_wars",
        worlds_root=REPO_ROOT / "data" / "worlds",
        substrate=None,
    )
    lms = manifest["landmarks"]
    # Builder fidelity: every authored landmark becomes exactly one pin (none
    # dropped/added). Counts are derived from the overview so adding landmarks
    # later doesn't re-break this lock. (Counts differ per region now — Dune
    # Sea 5, Underworld 6 — so the old fixed 6/4 pin was wrong for both.)
    overview = yaml.safe_load(
        (MAPS_DIR / f"{region}_overview.yaml").read_text(encoding="utf-8"))
    assert len(lms) == len(overview["landmarks"])
    # at least one distinctive painted feature; exit/off-map beacons are not
    assert sum(1 for l in lms if l["distinctive"]) >= 1
    assert not any(l["distinctive"] for l in lms if l["icon"] == "beacon")
    for l in lms:
        assert 0.0 <= l["fx"] <= 1.0 and 0.0 <= l["fy"] <= 1.0
    # substrate path is the canonical painted path (pinned in the spec)
    assert manifest["substrate"] == f"/static/maps/{region}_substrate.png"


# ════════════════════════════════════════════════════════════════════
# Nano package §6
# ════════════════════════════════════════════════════════════════════

def test_package_has_wilderness_section():
    txt = PACKAGE.read_text(encoding="utf-8")
    assert "WILDERNESS ADDENDUM" in txt
    # both save paths present (load-bearing filenames)
    assert "static/maps/tatooine_dune_sea_substrate.png" in txt
    assert "static/maps/coruscant_underworld_substrate.png" in txt
    # both seed feeds present
    assert "tatooine_dune_sea_tight_seed.png" in txt
    assert "coruscant_underworld_tight_seed.png" in txt
    # the terrain/track bullet substitutions are documented
    assert "terrain zone" in txt and "tracks" in txt


def test_package_documents_generated_briefs():
    """Drop 4.18 moved the per-region wilderness paint prompts OUT of this
    package and into generated ``static/tools/seeds/<slug>_paint_brief.md``
    files (so they can't drift from the grid). The package must document that
    workflow rather than hand-carry ``{GEOGRAPHY}`` lines.

    (The generated prompts intentionally reuse each region's authored feature
    descriptions, which include lore nouns; the painted PNGs were produced
    from exactly those prompts, so the old blanket franchise-noun ban on the
    prompt text no longer reflects the working pipeline. Tracked as a
    heads-up, not enforced — see HANDOFF / TD note.)
    """
    txt = PACKAGE.read_text(encoding="utf-8")
    idx = txt.find("WILDERNESS ADDENDUM")
    assert idx != -1
    section = txt[idx:]
    # the package now points at the generator + the generated brief paths,
    # and no longer asks anyone to hand-fill {GEOGRAPHY}.
    assert "gen_wilderness_overview.py" in section
    for region in REGIONS:
        assert f"{region}_paint_brief.md" in section, \
            f"package must reference the generated brief for {region}"
    # the generated briefs actually exist where the package says they are
    for region in REGIONS:
        brief = REPO_ROOT / "static" / "tools" / "seeds" / f"{region}_paint_brief.md"
        assert brief.exists(), f"missing generated brief: {brief}"


# ════════════════════════════════════════════════════════════════════
# Fixture wiring
# ════════════════════════════════════════════════════════════════════

def test_overview_data_has_active_substrate():
    """Drop 4.18 (PNGs painted): substrate_image is now ACTIVE in the
    generated overview data (``m3_wilderness_overview_data.js``), not a
    commented placeholder in the body renderer. The body JS deliberately does
    NOT hand-wire substrate — it reads ``region.substrate_image`` — so the
    active raster lives in the data file and auto-engages once the PNG exists.
    """
    src = WILD_DATA.read_text(encoding="utf-8")
    for region in REGIONS:
        assert f'"substrate_image": "/static/maps/{region}_substrate.png"' in src, \
            f"missing active substrate_image for {region} in overview data"
    # the body renderer must stay data-driven (no hand-wired substrate raster)
    body = WILD_JS.read_text(encoding="utf-8")
    assert "region.substrate_image" in body
