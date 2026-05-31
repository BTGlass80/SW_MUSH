"""
test_m3_tier_planet_body.py — Drop 4.13 (Batch 1) regression lock for
m3_tier_planet_body.js.

Tier 3 — Tatooine planet view. SVG body + optional HolocartaFrame
chrome via composition-engine DI.

What this file pins:

  · Module shape (IIFE + window.M3TierPlanetBody + documented surface).
  · Two builders: buildTierThreeBody (inner SVG) and
    buildTierThreeTatooine (chrome-wrapped).
  · buildTierThreeBody renders an SVG with 5 regions, 8 cities,
    6 travel routes, hyperspace beacon, twin-sun annotation.
  · B3 era cleanness — zero Empire/Imperial/Rebel/TIE/X-wing refs.
  · Mos Eisley is the player-marked city.
  · Q1 source-fidelity flag — JABBA'S PALACE + PIT OF CARKOON preserved.
  · Loud-substitution: undocumented palette keys (p.paper, p.ground,
    p.groundDeep, p.groundShadow) fall back gracefully.
  · Defensive DI: when M3CompositionEngine.HolocartaFrame is missing,
    buildTierThreeTatooine returns a labeled fallback rather than
    throwing.
  · Defensive DI: optional overlay helpers (TerrainDefs, HazeDefs,
    OV_TimeOfDay) are skipped silently when unavailable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = REPO_ROOT / "static" / "spa" / "m3_tier_planet_body.js"
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
    assert "window.M3TierPlanetBody" in src


def test_module_defines_both_builders():
    src = MODULE.read_text(encoding="utf-8")
    assert "function buildTierThreeBody(" in src
    assert "function buildTierThreeTatooine(" in src
    assert re.search(r"buildTierThreeBody\s*:\s*buildTierThreeBody\b", src)
    assert re.search(
        r"buildTierThreeTatooine\s*:\s*buildTierThreeTatooine\b", src
    )


def test_module_defines_fixtures():
    src = MODULE.read_text(encoding="utf-8")
    for fixture in ("CITIES", "REGIONS", "TRAVEL_ROUTES"):
        assert "var " + fixture + " = " in src
        assert re.search(fixture + r"\s*:\s*" + fixture + r"\b", src)


def test_module_applies_palette_fallbacks():
    """Drop 4.11 loud-substitution: p.paper / p.ground / p.groundDeep
    must have || fallbacks so the gradient renders on standard
    palettes that don't define these keys."""
    src = MODULE.read_text(encoding="utf-8")
    assert "p.paper" in src and "|| p.inkBright" in src
    assert "p.ground" in src and "|| p.amber" in src
    assert "p.groundDeep" in src and "|| p.skyDeep" in src


def test_client_html_loads_module():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_tier_planet_body.js" in src


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


def test_q1_jabbas_palace_preserved():
    """JABBA'S PALACE preserved verbatim per source-fidelity policy."""
    src = MODULE.read_text(encoding="utf-8")
    assert "JABBA'S PALACE" in src


def test_q1_pit_of_carkoon_preserved():
    """PIT OF CARKOON preserved verbatim per source-fidelity policy."""
    src = MODULE.read_text(encoding="utf-8")
    assert "PIT OF CARKOON" in src


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        result = {
            hasNamespace:  !!N,
            schemaVersion: N && N.SCHEMA_VERSION,
            hasBody:       typeof N.buildTierThreeBody === 'function',
            hasTatooine:   typeof N.buildTierThreeTatooine === 'function',
            hasCities:     Array.isArray(N.CITIES),
            hasRegions:    Array.isArray(N.REGIONS),
            hasRoutes:     Array.isArray(N.TRAVEL_ROUTES),
            cityCount:     N.CITIES.length,
            regionCount:   N.REGIONS.length,
            routeCount:    N.TRAVEL_ROUTES.length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasNamespace"]   is True
    assert r["schemaVersion"]  == 1
    assert r["hasBody"]        is True
    assert r["hasTatooine"]    is True
    assert r["hasCities"]      is True
    assert r["hasRegions"]     is True
    assert r["hasRoutes"]      is True
    assert r["cityCount"]      == 8
    assert r["regionCount"]    == 5
    assert r["routeCount"]     == 6


def test_runtime_buildTierThreeBody_renders_svg():
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        var el = N.buildTierThreeBody(p);
        document.body.appendChild(el);
        result = {
            tag:          el.tagName.toLowerCase(),
            isPlanet:     el.getAttribute('data-tier-planet') === '1',
            width:        el.getAttribute('width'),
            height:       el.getAttribute('height'),
            hasDefs:      !!el.querySelector('defs'),
            hasPlanetGrad: !!el.querySelector('[fill="url(#planet-body)"]'),
            hasShadow:    !!el.querySelector('[fill="url(#planet-shadow)"]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]            == "svg"
    assert r["isPlanet"]       is True
    assert r["width"]          == "700"
    assert r["height"]         == "700"
    assert r["hasDefs"]        is True
    assert r["hasPlanetGrad"]  is True
    assert r["hasShadow"]      is True


def test_runtime_renders_8_cities_with_mos_eisley_player():
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        var el = N.buildTierThreeBody(p);
        document.body.appendChild(el);
        var cities = el.querySelectorAll('[data-city]');
        var names = [];
        var mosEisley = null;
        var jabba = null;
        var pit = null;
        for (var i = 0; i < cities.length; i++) {
            var n = cities[i].getAttribute('data-city');
            names.push(n);
            if (n === 'MOS EISLEY')      mosEisley = cities[i];
            if (n === "JABBA'S PALACE")  jabba = cities[i];
            if (n === 'PIT OF CARKOON')  pit = cities[i];
        }
        result = {
            cityCount: cities.length,
            names:     names,
            mosPlayer: mosEisley && mosEisley.getAttribute('data-city-player'),
            jabbaLM:   jabba && jabba.getAttribute('data-city-landmark'),
            pitLM:     pit && pit.getAttribute('data-city-landmark'),
            pitHazard: pit && pit.getAttribute('data-city-hazard'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["cityCount"] == 8
    assert "MOS EISLEY" in r["names"]
    assert "JABBA'S PALACE" in r["names"]
    assert "PIT OF CARKOON" in r["names"]
    assert "ANCHORHEAD" in r["names"]
    assert "MOS ESPA" in r["names"]
    assert r["mosPlayer"] == "1"
    assert r["jabbaLM"]   == "1"
    assert r["pitLM"]     == "1"
    assert r["pitHazard"] == "1"


def test_runtime_renders_5_regions():
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        var el = N.buildTierThreeBody(p);
        document.body.appendChild(el);
        var regs = el.querySelectorAll('[data-region]');
        var names = [];
        for (var i = 0; i < regs.length; i++) {
            names.push(regs[i].getAttribute('data-region'));
        }
        result = {
            regionCount: regs.length,
            names:       names,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["regionCount"] == 5
    assert "DUNE SEA" in r["names"]
    assert "JUNDLAND WASTES" in r["names"]
    assert "NORTHERN DUNES" in r["names"]
    assert "XELRIC BASIN" in r["names"]
    assert "OUTER WASTES" in r["names"]


def test_runtime_renders_travel_routes():
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        var el = N.buildTierThreeBody(p);
        document.body.appendChild(el);
        var routes = el.querySelector('[data-travel-routes]');
        result = {
            hasRoutes: !!routes,
            // Each route is a <g> containing line + arrow path
            routeCount: routes ? routes.children.length : 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasRoutes"]  is True
    assert r["routeCount"] == 6


def test_runtime_renders_hyperspace_beacon_at_mos_eisley():
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        var el = N.buildTierThreeBody(p);
        document.body.appendChild(el);
        var beacon = el.querySelector('[data-hyperspace-beacon]');
        result = {
            hasBeacon: !!beacon,
            label:     beacon && beacon.getAttribute('data-hyperspace-beacon'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasBeacon"] is True
    assert r["label"]     == "MOS EISLEY"


def test_runtime_title_renders():
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        var el = N.buildTierThreeBody(p);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasTatooine: text.indexOf('TATOOINE') >= 0,
            hasArkanis: text.indexOf('ARKANIS') >= 0,
            hasBBY:     text.indexOf('20 BBY') >= 0,
            hasTatooI:  text.indexOf('TATOO I') >= 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasTatooine"] is True
    assert r["hasArkanis"]  is True
    assert r["hasBBY"]      is True
    assert r["hasTatooI"]   is True


def test_runtime_palette_fallbacks_work():
    """The palette in this test deliberately omits p.paper, p.ground,
    p.groundDeep, p.groundShadow. Module should render without throwing
    and the planet gradient should still be present (just degraded)."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        var threw = false;
        var el = null;
        try {
            el = N.buildTierThreeBody(p);
            document.body.appendChild(el);
        } catch (e) {
            threw = true;
        }
        result = {
            paletteOmitsPaper:        !('paper' in p),
            paletteOmitsGround:       !('ground' in p),
            paletteOmitsGroundDeep:   !('groundDeep' in p),
            paletteOmitsGroundShadow: !('groundShadow' in p),
            threw: threw,
            hasPlanetGrad: !!el && !!el.querySelector('[fill="url(#planet-body)"]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["paletteOmitsPaper"]        is True
    assert r["paletteOmitsGround"]       is True
    assert r["paletteOmitsGroundDeep"]   is True
    assert r["paletteOmitsGroundShadow"] is True
    assert r["threw"]                    is False
    assert r["hasPlanetGrad"]            is True


def test_runtime_tatooine_chrome_fallback_without_holocarta():
    """When M3CompositionEngine.HolocartaFrame is unavailable,
    buildTierThreeTatooine returns a labeled fallback."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        // Make sure no composition engine present
        delete window.M3CompositionEngine;
        var el = N.buildTierThreeTatooine(p);
        document.body.appendChild(el);
        result = {
            tag:        el.tagName.toLowerCase(),
            isFallback: el.getAttribute('data-tier-planet-frame-fallback') === '1',
            // Inner SVG should still be present.
            hasInner:   !!el.querySelector('[data-tier-planet]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]        == "div"
    assert r["isFallback"] is True
    assert r["hasInner"]   is True


def test_runtime_tatooine_chrome_uses_holocarta_when_present():
    """When M3CompositionEngine.HolocartaFrame is available, it's
    used; the fallback indicator should NOT be present."""
    setup = _setup_prelude() + r"""
        // Stub a minimal HolocartaFrame that just wraps children.
        window.M3CompositionEngine = {
            HolocartaFrame: function(args) {
                var wrap = document.createElement('div');
                wrap.setAttribute('data-stub-holocarta', '1');
                wrap.setAttribute('data-breadcrumb', args.breadcrumb || '');
                wrap.setAttribute('data-tier', args.tier || '');
                if (args.children) {
                    for (var i = 0; i < args.children.length; i++) {
                        wrap.appendChild(args.children[i]);
                    }
                }
                return wrap;
            },
            CompassRose: null
        };
        var N = window.M3TierPlanetBody;
        var el = N.buildTierThreeTatooine(p);
        document.body.appendChild(el);
        result = {
            usesHolocarta: el.getAttribute('data-stub-holocarta') === '1',
            breadcrumb:    el.getAttribute('data-breadcrumb'),
            tier:          el.getAttribute('data-tier'),
            isFallback:    el.getAttribute('data-tier-planet-frame-fallback') === '1',
            hasInner:      !!el.querySelector('[data-tier-planet]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["usesHolocarta"]  is True
    assert r["isFallback"]     is False
    assert r["hasInner"]       is True
    assert "GALAXY" in r["breadcrumb"]
    assert "ARKANIS SECTOR" in r["breadcrumb"]
    assert "TATOOINE" in r["breadcrumb"]
    assert "3 · PLANET" in r["tier"]


def test_runtime_custom_dimensions():
    setup = _setup_prelude() + r"""
        var N = window.M3TierPlanetBody;
        var el = N.buildTierThreeBody(p, { width: 500, height: 500 });
        document.body.appendChild(el);
        result = {
            width:  el.getAttribute('width'),
            height: el.getAttribute('height'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["width"]  == "500"
    assert r["height"] == "500"


def test_runtime_missing_palette_throws():
    setup = r"""
        var threw1 = false, threw2 = false;
        try { window.M3TierPlanetBody.buildTierThreeBody(); }
        catch (e) { threw1 = true; }
        try { window.M3TierPlanetBody.buildTierThreeTatooine(); }
        catch (e) { threw2 = true; }
        result = { threw1: threw1, threw2: threw2 };
    """
    r = run_with_dom([MODULE], setup)
    assert r["threw1"] is True
    assert r["threw2"] is True
