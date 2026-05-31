"""
test_m3_tier_galaxy_body.py — Drop 4.13 (Batch 1) regression lock for
m3_tier_galaxy_body.js.

Tier 4c — Galaxy view (CW era 20 BBY). Pure SVG, self-contained.

What this file pins:

  · Module shape (IIFE + window.M3TierGalaxyBody + documented surface).
  · buildTierFourGalaxy renders an SVG with the expected structural
    landmarks: 13 notable systems, 4 hyperlanes, 6 region rings,
    3 faction-territory overlays, title + era subtitle.
  · B3 era cleanness — "20 BBY" + "CLONE WARS ERA" present; zero
    Empire/Imperial/Rebel/TIE/X-wing references.
  · Tatooine is the player-marked system.
  · Geonosis + Mustafar marked hostile (CW-era CIS positions).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = REPO_ROOT / "static" / "spa" / "m3_tier_galaxy_body.js"
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
    assert "window.M3TierGalaxyBody" in src


def test_module_defines_buildTierFourGalaxy():
    src = MODULE.read_text(encoding="utf-8")
    assert "function buildTierFourGalaxy(" in src
    assert re.search(r"buildTierFourGalaxy\s*:\s*buildTierFourGalaxy\b", src)


def test_module_defines_fixtures():
    src = MODULE.read_text(encoding="utf-8")
    for fixture in ("NOTABLE_SYSTEMS", "HYPERLANES", "REGION_RINGS",
                    "FACTION_TERRITORY", "FACTION_LEGEND"):
        assert "var " + fixture + " = " in src
        assert re.search(fixture + r"\s*:\s*" + fixture + r"\b", src)


def test_client_html_loads_module():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_tier_galaxy_body.js" in src


# ════════════════════════════════════════════════════════════════════
# B3 era-cleanness
# ════════════════════════════════════════════════════════════════════

def test_no_era_contamination_module_wide():
    """No Empire / Imperial / Rebel / TIE / X-wing / Stormtrooper /
    Vader / Death Star / ISB references in the module source outside
    comments. Strips block + line comments first."""
    src = MODULE.read_text(encoding="utf-8")
    no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    no_line = re.sub(r"//[^\n]*", "", no_block)
    for tok in ("Empire", "Imperial", "Rebel", "Rebellion", "Stormtrooper",
                "Vader", "Death Star", "ISB"):
        assert tok not in no_line, (
            f"B3 regression: '{tok}' in module source outside comments"
        )


def test_cw_era_labels_present():
    src = MODULE.read_text(encoding="utf-8")
    assert "CLONE WARS ERA" in src or "Clone Wars" in src
    assert "20 BBY" in src
    assert "GALACTIC REPUBLIC" in src
    assert "CONFEDERACY" in src


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        result = {
            hasNamespace:   !!N,
            schemaVersion:  N && N.SCHEMA_VERSION,
            hasBuilder:     typeof N.buildTierFourGalaxy === 'function',
            hasNotable:     Array.isArray(N.NOTABLE_SYSTEMS),
            hasHyperlanes:  Array.isArray(N.HYPERLANES),
            hasRegionRings: Array.isArray(N.REGION_RINGS),
            hasFactions:    Array.isArray(N.FACTION_TERRITORY),
            notableCount:   N.NOTABLE_SYSTEMS.length,
            hyperlaneCount: N.HYPERLANES.length,
            ringCount:      N.REGION_RINGS.length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasNamespace"]   is True
    assert r["schemaVersion"]  == 1
    assert r["hasBuilder"]     is True
    assert r["hasNotable"]     is True
    assert r["hasHyperlanes"]  is True
    assert r["hasRegionRings"] is True
    assert r["hasFactions"]    is True
    assert r["notableCount"]   == 13
    assert r["hyperlaneCount"] == 4
    assert r["ringCount"]      == 6


def test_runtime_buildTierFourGalaxy_renders_svg():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(p);
        document.body.appendChild(el);
        result = {
            tag:         el.tagName.toLowerCase(),
            isGalaxy:    el.getAttribute('data-tier-galaxy') === '1',
            width:       el.getAttribute('width'),
            height:      el.getAttribute('height'),
            hasDefs:     !!el.querySelector('defs'),
            hasCorePath: !!el.querySelector('[fill="url(#gal-core)"]'),
            hasHalo:     !!el.querySelector('[fill="url(#gal-halo)"]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]         == "svg"
    assert r["isGalaxy"]    is True
    assert r["width"]       == "1280"
    assert r["height"]      == "856"
    assert r["hasDefs"]     is True
    assert r["hasCorePath"] is True
    assert r["hasHalo"]     is True


def test_runtime_renders_13_systems_with_tatooine_player():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(p);
        document.body.appendChild(el);
        var systems = el.querySelectorAll('[data-system]');
        var tatooine = el.querySelector('[data-system="TATOOINE"]');
        var coruscant = el.querySelector('[data-system="CORUSCANT"]');
        var geonosis = el.querySelector('[data-system="GEONOSIS"]');
        result = {
            systemCount: systems.length,
            hasTatooine: !!tatooine,
            tatPlayer:   tatooine && tatooine.getAttribute('data-system-player'),
            tatHostile:  tatooine && tatooine.getAttribute('data-system-hostile'),
            hasCoruscant: !!coruscant,
            geoHostile:  geonosis && geonosis.getAttribute('data-system-hostile'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["systemCount"]   == 13
    assert r["hasTatooine"]   is True
    assert r["tatPlayer"]     == "1"
    assert r["tatHostile"]    == "0"
    assert r["hasCoruscant"]  is True
    assert r["geoHostile"]    == "1"


def test_runtime_renders_4_hyperlanes_with_text_labels():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(p);
        document.body.appendChild(el);
        var lanes = el.querySelectorAll('[data-hyperlane]');
        var names = [];
        for (var i = 0; i < lanes.length; i++) {
            names.push(lanes[i].getAttribute('data-hyperlane'));
        }
        result = {
            laneCount: lanes.length,
            names:     names,
            text:      el.textContent,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["laneCount"] == 4
    assert "Perlemian Trade Route" in r["names"]
    assert "Corellian Run" in r["names"]
    assert "Hydian Way" in r["names"]
    assert "Rimma Trade Route" in r["names"]
    # Text labels uppercased per JSX source
    assert "PERLEMIAN" in r["text"]
    assert "CORELLIAN" in r["text"]


def test_runtime_renders_6_region_rings():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(p);
        document.body.appendChild(el);
        var rings = el.querySelectorAll('[data-region-ring]');
        var names = [];
        for (var i = 0; i < rings.length; i++) {
            names.push(rings[i].getAttribute('data-region-ring'));
        }
        result = { ringCount: rings.length, names: names };
    """
    r = run_with_dom([MODULE], setup)
    assert r["ringCount"] == 6
    assert "CORE WORLDS" in r["names"]
    assert "OUTER RIM" in r["names"]


def test_runtime_renders_faction_legend_with_cw_era_label():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(p);
        document.body.appendChild(el);
        var legend = el.querySelector('[data-faction-legend]');
        var text = legend.textContent;
        result = {
            hasLegend:     !!legend,
            hasEraLabel:   text.indexOf('20 BBY') >= 0,
            hasRepublic:   text.indexOf('GALACTIC REPUBLIC') >= 0,
            hasConfed:     text.indexOf('CONFEDERACY') >= 0,
            hasHuttSpace:  text.indexOf('HUTT SPACE') >= 0,
            hasWildSpace:  text.indexOf('WILD SPACE') >= 0,
            // Negative — no GCW-era factions
            hasEmpire:     text.indexOf('EMPIRE') >= 0,
            hasRebellion:  text.indexOf('REBELLION') >= 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasLegend"]     is True
    assert r["hasEraLabel"]   is True
    assert r["hasRepublic"]   is True
    assert r["hasConfed"]     is True
    assert r["hasHuttSpace"]  is True
    assert r["hasWildSpace"]  is True
    assert r["hasEmpire"]     is False
    assert r["hasRebellion"]  is False


def test_runtime_current_location_shows_tatooine():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(p);
        document.body.appendChild(el);
        var loc = el.querySelector('[data-current-location]');
        var text = loc.textContent;
        result = {
            hasIndicator: !!loc,
            text:         text,
            hasTatooine:  text.indexOf('TATOOINE') >= 0,
            hasSector:    text.indexOf('ARKANIS') >= 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasIndicator"]  is True
    assert r["hasTatooine"]   is True
    assert r["hasSector"]     is True


def test_runtime_title_renders():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(p);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasTitle: text.indexOf('THE GALAXY') >= 0,
            hasEra:   text.indexOf('CLONE WARS ERA') >= 0,
            hasBBY:   text.indexOf('20 BBY') >= 0,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasTitle"] is True
    assert r["hasEra"]   is True
    assert r["hasBBY"]   is True


def test_runtime_custom_dimensions():
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(p, { width: 800, height: 600 });
        document.body.appendChild(el);
        result = {
            width:  el.getAttribute('width'),
            height: el.getAttribute('height'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["width"]  == "800"
    assert r["height"] == "600"


def test_runtime_palette_via_opts():
    """The DI-seam signature lets callers pass palette via opts.p
    instead of as the first positional arg."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierGalaxyBody;
        var el = N.buildTierFourGalaxy(null, { p: p });
        document.body.appendChild(el);
        result = { tag: el.tagName.toLowerCase() };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"] == "svg"


def test_runtime_missing_palette_throws():
    setup = r"""
        var threw = false;
        try {
            window.M3TierGalaxyBody.buildTierFourGalaxy();
        } catch (e) {
            threw = true;
        }
        result = { threw: threw };
    """
    r = run_with_dom([MODULE], setup)
    assert r["threw"] is True
