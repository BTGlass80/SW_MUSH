"""
test_m3_tier_wilderness_body.py — Drop 4.14 (Batch 2) regression lock for
m3_tier_wilderness_body.js.

Tier 1b — Dune Sea wilderness region. SVG body + optional HolocartaFrame
chrome via composition-engine DI.

What this file pins:

  · Module shape (IIFE + window.M3TierWildernessBody + documented surface).
  · Two builders: buildTierOneBBody (inner SVG) and
    buildTierOneBDuneSea (chrome-wrapped).
  · buildTierOneBBody renders an SVG with 5 sub-regions, 6 POIs,
    4 routes, 9 dune ridges, heat-shimmer band.
  · Inline DUNE_SEA composite fixture exported.
  · B3 era cleanness — zero Empire/Imperial/Rebel/TIE/X-wing refs.
  · Moisture Farm is the player POI; Tusken Camp is hostile; Sarlacc
    Pit is a hazard.
  · Q1 source-fidelity flag — KRAYT GRAVEYARD + SARLACC PIT + TUSKEN
    CAMP preserved.
  · Loud-substitution: undocumented palette keys (p.paper, p.ground,
    p.groundDeep, p.groundShadow) fall back gracefully.
  · Defensive DI: when M3CompositionEngine.HolocartaFrame is missing,
    buildTierOneBDuneSea returns a labeled fallback rather than throwing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = REPO_ROOT / "static" / "spa" / "m3_tier_wilderness_body.js"
CLIENT_HTML = REPO_ROOT / "static" / "client.html"

# Minimal palette intentionally lacking p.paper / p.ground / p.groundDeep
# / p.groundShadow to exercise loud-substitution fallbacks.
SAMPLE_PALETTE = {
    "amber":     "#ffc857",
    "red":       "#ff5a4a",
    "green":     "#7ce068",
    "cyan":      "#7ce0d0",
    "gold":      "#d4a44b",
    "ink":       "#d6cbb7",
    "inkBright": "#fff4d6",
    "inkDim":    "#a09584",
    "inkFaint":  "#6b6253",
    "skyDeep":   "#1a160c",
}

from .spa_dom_harness import run_with_dom


# ════════════════════════════════════════════════════════════════════
# Static module-shape checks
# ════════════════════════════════════════════════════════════════════

def test_module_file_exists():
    assert MODULE.exists()


def test_module_is_iife():
    src = MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src
    assert "})();" in src


def test_module_exports_namespace():
    src = MODULE.read_text(encoding="utf-8")
    assert "window.M3TierWildernessBody" in src


def test_module_defines_both_builders():
    src = MODULE.read_text(encoding="utf-8")
    assert "function buildTierOneBBody(" in src
    assert "function buildTierOneBDuneSea(" in src
    assert re.search(r"buildTierOneBBody\s*:\s*buildTierOneBBody\b", src)
    assert re.search(
        r"buildTierOneBDuneSea\s*:\s*buildTierOneBDuneSea\b", src
    )


def test_module_defines_fixtures():
    src = MODULE.read_text(encoding="utf-8")
    for fixture in ("DUNE_SEA", "SUB_REGIONS", "POIS", "ROUTES"):
        assert "var " + fixture + " = " in src
        assert re.search(fixture + r"\s*:\s*" + fixture + r"\b", src)


def test_module_applies_palette_fallbacks():
    """Drop 4.11 loud-substitution: p.paper / p.ground / p.groundDeep /
    p.groundShadow must have || fallbacks so the region renders on
    standard palettes that don't define these keys."""
    src = MODULE.read_text(encoding="utf-8")
    assert "p.paper" in src and "|| p.inkBright" in src
    assert "p.ground" in src and "|| p.amber" in src
    assert "p.groundDeep" in src and "|| p.skyDeep" in src
    assert "p.groundShadow" in src and "|| p.skyDeep" in src


def test_client_html_loads_module():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_tier_wilderness_body.js" in src


# ════════════════════════════════════════════════════════════════════
# B3 + Q1
# ════════════════════════════════════════════════════════════════════

def test_no_era_contamination_module_wide():
    src = MODULE.read_text(encoding="utf-8")
    no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    no_line = re.sub(r"//[^\n]*", "", no_block)
    for tok in ("Empire", "Imperial", "Rebel", "Rebellion", "Stormtrooper",
                "Vader", "Death Star", "ISB"):
        assert tok not in no_line, (
            f"B3 regression: '{tok}' in module source outside comments"
        )


def test_q1_krayt_graveyard_preserved():
    """KRAYT GRAVEYARD preserved verbatim per source-fidelity policy."""
    src = MODULE.read_text(encoding="utf-8")
    assert "KRAYT GRAVEYARD" in src


def test_q1_sarlacc_pit_preserved():
    """SARLACC PIT preserved verbatim per source-fidelity policy."""
    src = MODULE.read_text(encoding="utf-8")
    assert "SARLACC PIT" in src


def test_q1_tusken_camp_preserved():
    """TUSKEN CAMP preserved verbatim per source-fidelity policy."""
    src = MODULE.read_text(encoding="utf-8")
    assert "TUSKEN CAMP" in src


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        result = {
            hasNamespace:   !!N,
            schemaVersion:  N && N.SCHEMA_VERSION,
            hasBody:        typeof N.buildTierOneBBody === 'function',
            hasDuneSea:     typeof N.buildTierOneBDuneSea === 'function',
            hasFixtureObj:  !!N.DUNE_SEA && typeof N.DUNE_SEA === 'object',
            hasSubRegions:  Array.isArray(N.SUB_REGIONS),
            hasPois:        Array.isArray(N.POIS),
            hasRoutes:      Array.isArray(N.ROUTES),
            subRegionCount: N.SUB_REGIONS.length,
            poiCount:       N.POIS.length,
            routeCount:     N.ROUTES.length,
            fixtureSubs:    N.DUNE_SEA.sub_regions.length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasNamespace"]   is True
    assert r["schemaVersion"]  == 1
    assert r["hasBody"]        is True
    assert r["hasDuneSea"]     is True
    assert r["hasFixtureObj"]  is True
    assert r["hasSubRegions"]  is True
    assert r["hasPois"]        is True
    assert r["hasRoutes"]      is True
    assert r["subRegionCount"] == 5
    assert r["poiCount"]       == 6
    assert r["routeCount"]     == 4
    assert r["fixtureSubs"]    == 5


def test_runtime_buildTierOneBBody_renders_svg():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBBody(p);
        document.body.appendChild(el);
        result = {
            tag:           el.tagName.toLowerCase(),
            isWilderness:  el.getAttribute('data-tier-wilderness') === '1',
            width:         el.getAttribute('width'),
            height:        el.getAttribute('height'),
            hasDefs:       !!el.querySelector('defs'),
            duneRidges:    el.querySelectorAll('[data-layer="dunes"] polyline').length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]          == "svg"
    assert r["isWilderness"] is True
    assert r["width"]        == "700"
    assert r["height"]       == "600"
    assert r["hasDefs"]      is True
    assert r["duneRidges"]   == 9


def test_runtime_renders_5_subregions_with_hazard():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBBody(p);
        document.body.appendChild(el);
        var srs = el.querySelectorAll('[data-subregion]');
        var names = [];
        var sinking = null;
        for (var i = 0; i < srs.length; i++) {
            var n = srs[i].getAttribute('data-subregion');
            names.push(n);
            if (n === 'SINKING SANDS') sinking = srs[i];
        }
        result = {
            count:        srs.length,
            names:        names,
            sinkingHazard: sinking && sinking.getAttribute('data-subregion-hazard'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["count"] == 5
    assert "OPEN DUNES" in r["names"]
    assert "ROCK FLATS" in r["names"]
    assert "THE PINNACLES" in r["names"]
    assert "SINKING SANDS" in r["names"]
    assert "KRAYT GRAVEYARD" in r["names"]
    assert r["sinkingHazard"] == "1"


def test_runtime_renders_6_pois_with_player_and_hostile():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBBody(p);
        document.body.appendChild(el);
        var ps = el.querySelectorAll('[data-poi]');
        var names = [];
        var farm = null, tusken = null, sarlacc = null;
        for (var i = 0; i < ps.length; i++) {
            var n = ps[i].getAttribute('data-poi');
            names.push(n);
            if (n === 'MOISTURE FARM') farm = ps[i];
            if (n === 'TUSKEN CAMP')   tusken = ps[i];
            if (n === 'SARLACC PIT')   sarlacc = ps[i];
        }
        result = {
            count:        ps.length,
            names:        names,
            farmPlayer:   farm && farm.getAttribute('data-poi-player'),
            tuskenHostile: tusken && tusken.getAttribute('data-poi-hostile'),
            sarlaccHazard: sarlacc && sarlacc.getAttribute('data-poi-hazard'),
            tuskenTag:    tusken && tusken.tagName.toLowerCase(),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["count"] == 6
    assert "MOISTURE FARM" in r["names"]
    assert "TUSKEN CAMP" in r["names"]
    assert "SARLACC PIT" in r["names"]
    assert "CRASHED FREIGHTER" in r["names"]
    assert "BANTHA HERD" in r["names"]
    assert "SANDCRAWLER TRACK" in r["names"]
    assert r["farmPlayer"]    == "1"
    assert r["tuskenHostile"] == "1"
    assert r["sarlaccHazard"] == "1"
    # Hostile POIs render as a triangle <path>, not a <circle>.
    assert r["tuskenTag"] == "path"


def test_runtime_renders_routes():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBBody(p);
        document.body.appendChild(el);
        result = {
            routes: el.querySelectorAll('[data-layer="routes"] line').length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["routes"] == 4


def test_runtime_palette_fallbacks_work():
    """A palette omitting p.paper/p.ground/p.groundDeep/p.groundShadow
    still renders the wilderness body."""
    minimal = {
        "amber": "#ffc857", "red": "#ff5a4a", "green": "#7ce068",
        "cyan": "#7ce0d0", "gold": "#d4a44b", "ink": "#d6cbb7",
        "inkBright": "#fff4d6", "inkDim": "#a09584", "skyDeep": "#1a160c",
    }
    setup = "var p = " + json.dumps(minimal) + ";\n" + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBBody(p);
        document.body.appendChild(el);
        result = {
            tag:            el.tagName.toLowerCase(),
            subRegionCount: el.querySelectorAll('[data-subregion]').length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"] == "svg"
    assert r["subRegionCount"] == 5


def test_runtime_duneSea_chrome_fallback_without_holocarta():
    """buildTierOneBDuneSea returns a labeled fallback div when
    HolocartaFrame is unavailable (rather than throwing)."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBDuneSea(p);
        document.body.appendChild(el);
        result = {
            tag:        el.tagName.toLowerCase(),
            fallback:   el.getAttribute('data-tier-wilderness-frame-fallback'),
            hasSvg:     !!el.querySelector('svg'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]      == "div"
    assert r["fallback"] == "1"
    assert r["hasSvg"]   is True


def test_runtime_duneSea_chrome_uses_holocarta_when_present():
    """When a HolocartaFrame stub is present, buildTierOneBDuneSea
    routes through it (happy path)."""
    setup = _setup_prelude() + r"""
        window.M3CompositionEngine = {
            HolocartaFrame: function(o) {
                var d = document.createElement('div');
                d.setAttribute('data-holocarta', '1');
                d.setAttribute('data-tier', o.tier || '');
                (o.children || []).forEach(function(c){ d.appendChild(c); });
                return d;
            }
        };
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBDuneSea(p);
        document.body.appendChild(el);
        result = {
            holocarta: el.getAttribute('data-holocarta'),
            tier:      el.getAttribute('data-tier'),
            hasSvg:    !!el.querySelector('svg'),
            fallback:  el.getAttribute('data-tier-wilderness-frame-fallback'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["holocarta"] == "1"
    assert "WILDERNESS" in r["tier"]
    assert r["hasSvg"]    is True
    assert r["fallback"]  is None
