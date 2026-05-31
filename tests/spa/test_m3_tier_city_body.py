"""
test_m3_tier_city_body.py — Drop 4.14 (Batch 2) regression lock for
m3_tier_city_body.js.

Tier 2 — Mos Eisley city overview. SVG body + optional HolocartaFrame
chrome via composition-engine DI.

What this file pins:

  · Module shape (IIFE + window.M3TierCityBody + documented surface).
  · Two builders: buildTierTwoBody (inner SVG) and
    buildTierTwoMosEisley (chrome-wrapped).
  · buildTierTwoBody renders an SVG with 6 districts, 5 landmarks,
    a street grid, building clusters, beacon pulse.
  · B3 era cleanness — zero Empire/Imperial/Rebel/TIE/X-wing refs.
  · Chalmun's Cantina is the player-marked landmark.
  · Q1 source-fidelity flag — CHALMUN'S CANTINA + DOCKING BAY 94
    preserved.
  · Loud-substitution: undocumented palette keys (p.paper, p.ground,
    p.groundDeep) fall back gracefully.
  · Defensive DI: when M3CompositionEngine.HolocartaFrame is missing,
    buildTierTwoMosEisley returns a labeled fallback rather than throwing.
  · Defensive DI: optional helpers (L_Atmosphere, CompassRose,
    overlay defs) are skipped silently when unavailable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = REPO_ROOT / "static" / "spa" / "m3_tier_city_body.js"
CLIENT_HTML = REPO_ROOT / "static" / "client.html"

# Minimal palette intentionally lacking p.paper / p.ground / p.groundDeep
# to exercise loud-substitution fallbacks.
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
    assert "window.M3TierCityBody" in src


def test_module_defines_both_builders():
    src = MODULE.read_text(encoding="utf-8")
    assert "function buildTierTwoBody(" in src
    assert "function buildTierTwoMosEisley(" in src
    assert re.search(r"buildTierTwoBody\s*:\s*buildTierTwoBody\b", src)
    assert re.search(
        r"buildTierTwoMosEisley\s*:\s*buildTierTwoMosEisley\b", src
    )


def test_module_defines_fixtures():
    src = MODULE.read_text(encoding="utf-8")
    for fixture in ("DISTRICTS", "LANDMARKS", "BUILDINGS", "STREETS"):
        assert "var " + fixture + " = " in src
        assert re.search(fixture + r"\s*:\s*" + fixture + r"\b", src)


def test_module_applies_palette_fallbacks():
    """Drop 4.11 loud-substitution: p.paper / p.ground / p.groundDeep
    must have || fallbacks so the city renders on standard palettes
    that don't define these keys."""
    src = MODULE.read_text(encoding="utf-8")
    assert "p.paper" in src and "|| p.inkBright" in src
    assert "p.ground" in src and "|| p.amber" in src
    assert "p.groundDeep" in src and "|| p.skyDeep" in src


def test_client_html_loads_module():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_tier_city_body.js" in src


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


def test_q1_chalmuns_cantina_preserved():
    """CHALMUN'S CANTINA preserved verbatim per source-fidelity policy."""
    src = MODULE.read_text(encoding="utf-8")
    assert "CHALMUN'S CANTINA" in src


def test_q1_docking_bay_94_preserved():
    """DOCKING BAY 94 preserved verbatim per source-fidelity policy."""
    src = MODULE.read_text(encoding="utf-8")
    assert "DOCKING BAY 94" in src


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3TierCityBody;
        result = {
            hasNamespace:    !!N,
            schemaVersion:   N && N.SCHEMA_VERSION,
            hasBody:         typeof N.buildTierTwoBody === 'function',
            hasMosEisley:    typeof N.buildTierTwoMosEisley === 'function',
            hasDistricts:    Array.isArray(N.DISTRICTS),
            hasLandmarks:    Array.isArray(N.LANDMARKS),
            hasBuildings:    Array.isArray(N.BUILDINGS),
            districtCount:   N.DISTRICTS.length,
            landmarkCount:   N.LANDMARKS.length,
            buildingCount:   N.BUILDINGS.length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasNamespace"]   is True
    assert r["schemaVersion"]  == 1
    assert r["hasBody"]        is True
    assert r["hasMosEisley"]   is True
    assert r["hasDistricts"]   is True
    assert r["hasLandmarks"]   is True
    assert r["hasBuildings"]   is True
    assert r["districtCount"]  == 6
    assert r["landmarkCount"]  == 5
    assert r["buildingCount"]  == 8


def test_runtime_buildTierTwoBody_renders_svg():
    setup = _setup_prelude() + r"""
        var N = window.M3TierCityBody;
        var el = N.buildTierTwoBody(p);
        document.body.appendChild(el);
        result = {
            tag:          el.tagName.toLowerCase(),
            isCity:       el.getAttribute('data-tier-city') === '1',
            width:        el.getAttribute('width'),
            height:       el.getAttribute('height'),
            hasDefs:      !!el.querySelector('defs'),
            hasGround:    !!el.querySelector('[fill="url(#city-ground)"]') ||
                          !!el.querySelector('[data-layer]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]      == "svg"
    assert r["isCity"]   is True
    assert r["width"]    == "700"
    assert r["height"]   == "700"
    assert r["hasDefs"]  is True


def test_runtime_renders_6_districts():
    setup = _setup_prelude() + r"""
        var N = window.M3TierCityBody;
        var el = N.buildTierTwoBody(p);
        document.body.appendChild(el);
        var ds = el.querySelectorAll('[data-district]');
        var names = [];
        for (var i = 0; i < ds.length; i++) {
            names.push(ds[i].getAttribute('data-district'));
        }
        result = { count: ds.length, names: names };
    """
    r = run_with_dom([MODULE], setup)
    assert r["count"] == 6
    assert "SPACEPORT" in r["names"]
    assert "OLD QUARTER" in r["names"]
    assert "MERCHANT ROW" in r["names"]
    assert "OUTER SPRAWL" in r["names"]
    assert "CANTINA ROW" in r["names"]
    assert "DOCKING BAYS" in r["names"]


def test_runtime_renders_5_landmarks_with_chalmuns_player():
    setup = _setup_prelude() + r"""
        var N = window.M3TierCityBody;
        var el = N.buildTierTwoBody(p);
        document.body.appendChild(el);
        var lms = el.querySelectorAll('[data-landmark]');
        var names = [];
        var chalmuns = null, tower = null, bay = null;
        for (var i = 0; i < lms.length; i++) {
            var n = lms[i].getAttribute('data-landmark');
            names.push(n);
            if (n === "CHALMUN'S CANTINA") chalmuns = lms[i];
            if (n === 'CONTROL TOWER')     tower = lms[i];
            if (n === 'DOCKING BAY 94')    bay = lms[i];
        }
        result = {
            count:        lms.length,
            names:        names,
            chalmunsPlayer: chalmuns && chalmuns.getAttribute('data-landmark-player'),
            towerBeacon:  tower && tower.getAttribute('data-landmark-beacon'),
            bayKind:      bay && bay.getAttribute('data-landmark-kind'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["count"] == 5
    assert "CHALMUN'S CANTINA" in r["names"]
    assert "CONTROL TOWER" in r["names"]
    assert "DOCKING BAY 94" in r["names"]
    assert "GRAND BAZAAR" in r["names"]
    assert "WATER MERCHANT" in r["names"]
    assert r["chalmunsPlayer"] == "1"
    assert r["towerBeacon"]    == "1"
    assert r["bayKind"]        == "1"


def test_runtime_renders_street_grid_and_buildings():
    setup = _setup_prelude() + r"""
        var N = window.M3TierCityBody;
        var el = N.buildTierTwoBody(p);
        document.body.appendChild(el);
        result = {
            streets:   el.querySelectorAll('[data-layer="streets"] line').length,
            buildings: el.querySelectorAll('[data-layer="buildings"] rect').length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["streets"]   == 5
    assert r["buildings"] == 8


def test_runtime_palette_fallbacks_work():
    """A palette omitting p.paper/p.ground/p.groundDeep still renders."""
    minimal = {
        "amber": "#ffc857", "red": "#ff5a4a", "green": "#7ce068",
        "cyan": "#7ce0d0", "gold": "#d4a44b", "ink": "#d6cbb7",
        "inkBright": "#fff4d6", "inkDim": "#a09584", "skyDeep": "#1a160c",
    }
    setup = "var p = " + json.dumps(minimal) + ";\n" + r"""
        var N = window.M3TierCityBody;
        var el = N.buildTierTwoBody(p);
        document.body.appendChild(el);
        result = {
            tag:           el.tagName.toLowerCase(),
            districtCount: el.querySelectorAll('[data-district]').length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"] == "svg"
    assert r["districtCount"] == 6


def test_runtime_mosEisley_chrome_fallback_without_holocarta():
    """buildTierTwoMosEisley returns a labeled fallback div when
    HolocartaFrame is unavailable (rather than throwing)."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierCityBody;
        var el = N.buildTierTwoMosEisley(p);
        document.body.appendChild(el);
        result = {
            tag:        el.tagName.toLowerCase(),
            fallback:   el.getAttribute('data-tier-city-frame-fallback'),
            hasSvg:     !!el.querySelector('svg'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]      == "div"
    assert r["fallback"] == "1"
    assert r["hasSvg"]   is True


def test_runtime_mosEisley_chrome_uses_holocarta_when_present():
    """When a HolocartaFrame stub is present, buildTierTwoMosEisley
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
        var N = window.M3TierCityBody;
        var el = N.buildTierTwoMosEisley(p);
        document.body.appendChild(el);
        result = {
            holocarta: el.getAttribute('data-holocarta'),
            tier:      el.getAttribute('data-tier'),
            hasSvg:    !!el.querySelector('svg'),
            fallback:  el.getAttribute('data-tier-city-frame-fallback'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["holocarta"] == "1"
    assert "CITY" in r["tier"]
    assert r["hasSvg"]    is True
    assert r["fallback"]  is None
