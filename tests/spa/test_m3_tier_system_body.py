"""
test_m3_tier_system_body.py — Drop 4.13 (Batch 1) regression lock for
m3_tier_system_body.js.

Tier 4a — Tatooine system view. Pure SVG, self-contained.

What this file pins:

  · Module shape (IIFE + window.M3TierSystemBody + documented surface).
  · buildTierFourASystemBody renders an SVG with the expected structural
    landmarks: 5 orbital bodies, 4 hyperspace beacons, asteroid belt,
    twin suns, RUSTY MYNOCK player ship.
  · B3 era cleanness — zero Empire/Imperial/Rebel/TIE/X-wing refs.
  · Tatooine is the player-marked body.
  · Geonosis beacon is hostile.
  · Q1 source-fidelity flag — RUSTY MYNOCK preserved verbatim.
  · Loud-substitution: p.groundShadow fallback works when absent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = REPO_ROOT / "static" / "spa" / "m3_tier_system_body.js"
CLIENT_HTML = REPO_ROOT / "static" / "client.html"

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
    "sky":       "#2a2418",
    "skyDeep":   "#1a160c",
    # Intentionally omitting groundShadow to exercise the fallback.
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
    assert "window.M3TierSystemBody" in src


def test_module_defines_buildTierFourASystemBody():
    src = MODULE.read_text(encoding="utf-8")
    assert "function buildTierFourASystemBody(" in src
    assert re.search(
        r"buildTierFourASystemBody\s*:\s*buildTierFourASystemBody\b", src
    )


def test_module_defines_fixtures():
    src = MODULE.read_text(encoding="utf-8")
    for fixture in ("ORBITAL_BODIES", "BEACONS", "TWIN_SUNS"):
        assert "var " + fixture + " = " in src
        assert re.search(fixture + r"\s*:\s*" + fixture + r"\b", src)


def test_module_applies_groundshadow_fallback():
    """Drop 4.11 loud-substitution: p.groundShadow falls back to
    p.skyDeep so the gradient renders even on palettes lacking it."""
    src = MODULE.read_text(encoding="utf-8")
    assert "groundShadow || p.skyDeep" in src or \
           "p.groundShadow || p.skyDeep" in src


def test_client_html_loads_module():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_tier_system_body.js" in src


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


def test_q1_rusty_mynock_preserved_from_source():
    """Drop 4.13 preserves the JSX source's reference to RUSTY MYNOCK
    (Tey Voss player ship name). Tracked for Q1-hardening sweep."""
    src = MODULE.read_text(encoding="utf-8")
    assert "RUSTY MYNOCK" in src


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        result = {
            hasNamespace:  !!N,
            schemaVersion: N && N.SCHEMA_VERSION,
            hasBuilder:    typeof N.buildTierFourASystemBody === 'function',
            hasBodies:     Array.isArray(N.ORBITAL_BODIES),
            hasBeacons:    Array.isArray(N.BEACONS),
            hasSuns:       !!N.TWIN_SUNS,
            bodyCount:     N.ORBITAL_BODIES.length,
            beaconCount:   N.BEACONS.length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasNamespace"]   is True
    assert r["schemaVersion"]  == 1
    assert r["hasBuilder"]     is True
    assert r["hasBodies"]      is True
    assert r["hasBeacons"]     is True
    assert r["hasSuns"]        is True
    assert r["bodyCount"]      == 5
    assert r["beaconCount"]    == 4


def test_runtime_builder_renders_svg():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        var el = N.buildTierFourASystemBody(p);
        document.body.appendChild(el);
        result = {
            tag:        el.tagName.toLowerCase(),
            isSystem:   el.getAttribute('data-tier-system') === '1',
            width:      el.getAttribute('width'),
            height:     el.getAttribute('height'),
            hasDefs:    !!el.querySelector('defs'),
            hasSunA:    !!el.querySelector('[fill="url(#sun-glow-a)"]'),
            hasSunB:    !!el.querySelector('[fill="url(#sun-glow-b)"]'),
            hasTatooineGrad: !!el.querySelector('[fill="url(#planet-tatooine)"]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]               == "svg"
    assert r["isSystem"]          is True
    assert r["width"]             == "1280"
    assert r["height"]            == "856"
    assert r["hasDefs"]           is True
    assert r["hasSunA"]           is True
    assert r["hasSunB"]           is True
    assert r["hasTatooineGrad"]   is True


def test_runtime_renders_5_bodies_with_tatooine_player():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        var el = N.buildTierFourASystemBody(p);
        document.body.appendChild(el);
        var bodies = el.querySelectorAll('[data-body]');
        var names = [];
        var tatooine = null;
        for (var i = 0; i < bodies.length; i++) {
            var name = bodies[i].getAttribute('data-body');
            names.push(name);
            if (name === 'TATOOINE') tatooine = bodies[i];
        }
        result = {
            bodyCount: bodies.length,
            names:     names,
            tatPlayer: tatooine && tatooine.getAttribute('data-body-player'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["bodyCount"] == 5
    assert "TATOOINE" in r["names"]
    assert "TATOO IV" in r["names"]
    assert "TATOO VI" in r["names"]
    assert "GHEST" in r["names"]
    assert r["tatPlayer"] == "1"


def test_runtime_renders_4_beacons_with_geonosis_hostile():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        var el = N.buildTierFourASystemBody(p);
        document.body.appendChild(el);
        var beacons = el.querySelectorAll('[data-beacon]');
        var labels = [];
        var geonosis = null;
        var kessel = null;
        for (var i = 0; i < beacons.length; i++) {
            var lbl = beacons[i].getAttribute('data-beacon');
            labels.push(lbl);
            if (lbl === 'TO GEONOSIS') geonosis = beacons[i];
            if (lbl === 'TO KESSEL')   kessel = beacons[i];
        }
        result = {
            beaconCount: beacons.length,
            labels:      labels,
            geoHostile:  geonosis && geonosis.getAttribute('data-beacon-hostile'),
            geoActive:   geonosis && geonosis.getAttribute('data-beacon-active'),
            kesselActive: kessel && kessel.getAttribute('data-beacon-active'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["beaconCount"] == 4
    assert "TO GEONOSIS" in r["labels"]
    assert "TO KESSEL" in r["labels"]
    assert "TO ANCHORHEAD" in r["labels"]
    assert "TO RYLOTH" in r["labels"]
    assert r["geoHostile"]  == "1"
    assert r["geoActive"]   == "1"
    assert r["kesselActive"] == "1"


def test_runtime_renders_player_ship_rusty_mynock():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        var el = N.buildTierFourASystemBody(p);
        document.body.appendChild(el);
        var ship = el.querySelector('[data-player-ship]');
        result = {
            hasShip:  !!ship,
            shipName: ship && ship.getAttribute('data-player-ship'),
            hasText:  ship && ship.textContent.indexOf('RUSTY MYNOCK') >= 0,
            hasOrbitText: ship && ship.textContent.indexOf('low orbit') >= 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasShip"]      is True
    assert r["shipName"]     == "RUSTY MYNOCK"
    assert r["hasText"]      is True
    assert r["hasOrbitText"] is True


def test_runtime_asteroid_belt_renders_with_90_bodies():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        var el = N.buildTierFourASystemBody(p);
        document.body.appendChild(el);
        var belt = el.querySelector('[data-asteroid-belt]');
        result = {
            hasBelt: !!belt,
            // Each asteroid is a <circle>; count children
            asteroidCount: belt ? belt.children.length : 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasBelt"]       is True
    assert r["asteroidCount"] == 90


def test_runtime_groundshadow_fallback_works_without_palette_key():
    """The palette in this test deliberately omits groundShadow.
    The module should still render without throwing."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        // Verify palette has no groundShadow.
        var threw = false;
        var el = null;
        try {
            el = N.buildTierFourASystemBody(p);
            document.body.appendChild(el);
        } catch (e) {
            threw = true;
        }
        result = {
            paletteHasKey: ('groundShadow' in p),
            threw:         threw,
            hasSvg:        !!el && el.tagName.toLowerCase() === 'svg',
            hasTatooineGrad: !!el && !!el.querySelector('[fill="url(#planet-tatooine)"]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["paletteHasKey"] is False
    assert r["threw"]         is False
    assert r["hasSvg"]        is True
    assert r["hasTatooineGrad"] is True


def test_runtime_title_renders():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        var el = N.buildTierFourASystemBody(p);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasTitle:  text.indexOf('TATOOINE SYSTEM') >= 0,
            hasBinary: text.indexOf('BINARY') >= 0,
            hasSector: text.indexOf('ARKANIS') >= 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasTitle"]  is True
    assert r["hasBinary"] is True
    assert r["hasSector"] is True


def test_runtime_legend_renders():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        var el = N.buildTierFourASystemBody(p);
        document.body.appendChild(el);
        var legend = el.querySelector('[data-legend]');
        result = {
            hasLegend:  !!legend,
            hasBeacon:  legend && legend.textContent.indexOf('HYPERSPACE BEACON') >= 0,
            hasBelt:    legend && legend.textContent.indexOf('ASTEROID BELT') >= 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasLegend"] is True
    assert r["hasBeacon"] is True
    assert r["hasBelt"]   is True


def test_runtime_custom_dimensions():
    setup = _setup_prelude() + r"""
        var N = window.M3TierSystemBody;
        var el = N.buildTierFourASystemBody(p, { width: 900, height: 600 });
        document.body.appendChild(el);
        result = {
            width:  el.getAttribute('width'),
            height: el.getAttribute('height'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["width"]  == "900"
    assert r["height"] == "600"


def test_runtime_missing_palette_throws():
    setup = r"""
        var threw = false;
        try {
            window.M3TierSystemBody.buildTierFourASystemBody();
        } catch (e) {
            threw = true;
        }
        result = { threw: threw };
    """
    r = run_with_dom([MODULE], setup)
    assert r["threw"] is True
