"""
test_m3_tier_registry.py — Drop 4.15 (cutover) regression lock for
m3_tier_registry.js.

The canonical getTierRenderer lookup. Maps all seven tier IDs to their
body builders; default for both M3MapNavigator and
M3AssembledClient.MiniMap.

What this file pins:

  · Module shape (IIFE + window.M3TierRegistry + documented surface).
  · getTierRenderer(tierId, args) resolves each demo-fixture tier
    (4c/4a/3/2/1b/0) to a real <svg> when its module is loaded.
  · getTierRenderer('1a', { data }) routes to
    M3CompositionEngine.Tier1aBody when live data is supplied; falls to
    a labeled placeholder without it.
  · Unknown / unloaded tiers degrade to a labeled placeholder — never
    null, never throws.
  · hasRenderer(tierId) reports module availability.
  · TIER_RENDERERS table covers the six demo-fixture tiers (1a is
    handled separately).
  · B3 era cleanness — zero Empire/Imperial/Rebel/TIE/X-wing refs.
  · The module owns no runtime state (pure lookup).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPA_DIR = REPO_ROOT / "static" / "spa"
MODULE = SPA_DIR / "m3_tier_registry.js"
CLIENT_HTML = REPO_ROOT / "static" / "client.html"

# All modules the registry resolves against, in load order.
TIER_MODULES = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_palettes.js",
    SPA_DIR / "m3_assets_styles.js",
    SPA_DIR / "m3_assets_icons.js",
    SPA_DIR / "m3_assets_markers.js",
    SPA_DIR / "m3_assets_wilderness.js",
    SPA_DIR / "m3_assets_overlays.js",
    SPA_DIR / "m3_assets_landmarks.js",
    SPA_DIR / "m3_composition_engine.js",
    SPA_DIR / "m3_adapter.js",
    SPA_DIR / "m3_tier_galaxy_body.js",
    SPA_DIR / "m3_tier_system_body.js",
    SPA_DIR / "m3_tier_planet_body.js",
    SPA_DIR / "m3_tier_city_body.js",
    SPA_DIR / "m3_tier_wilderness_body.js",
    SPA_DIR / "m3_tier_interior_body.js",
    MODULE,
]

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
    assert "window.M3TierRegistry" in src


def test_module_defines_surface():
    src = MODULE.read_text(encoding="utf-8")
    assert "function getTierRenderer(" in src
    assert "function hasRenderer(" in src
    assert re.search(r"getTierRenderer\s*:\s*getTierRenderer\b", src)
    assert re.search(r"hasRenderer\s*:\s*hasRenderer\b", src)
    assert re.search(r"TIER_RENDERERS\s*:\s*TIER_RENDERERS\b", src)


def test_tier_renderers_table_covers_six_demo_tiers():
    """The TIER_RENDERERS table maps the six demo-fixture tiers; 1a is
    handled specially (composition engine + live data)."""
    src = MODULE.read_text(encoding="utf-8")
    for tier in ("'4c'", "'4a'", "'3'", "'2'", "'1b'", "'0'"):
        assert tier in src
    # The builder method names must match the real exports.
    assert "buildTierFourGalaxy" in src
    assert "buildTierFourASystemBody" in src
    assert "buildTierThreeBody" in src
    assert "buildTierTwoBody" in src
    assert "buildTierOneBBody" in src
    assert "buildTierZeroBody" in src


def test_client_html_loads_module():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_tier_registry.js" in src


def test_client_html_loads_registry_after_tier_bodies():
    """The registry script tag must come after all six tier-body tags so
    they're available by call-time."""
    src = CLIENT_HTML.read_text(encoding="utf-8")
    reg_pos = src.find("/static/spa/m3_tier_registry.js")
    interior_pos = src.find("/static/spa/m3_tier_interior_body.js")
    assert reg_pos != -1 and interior_pos != -1
    assert reg_pos > interior_pos


# ════════════════════════════════════════════════════════════════════
# B3
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


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _palette_prelude():
    # Resolve a real palette from M3Palettes (loaded in TIER_MODULES).
    return "var p = window.M3Palettes.getPalette('tatooine');\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _palette_prelude() + r"""
        var R = window.M3TierRegistry;
        result = {
            hasNamespace:   !!R,
            schemaVersion:  R && R.SCHEMA_VERSION,
            hasGetter:      typeof R.getTierRenderer === 'function',
            hasHasRenderer: typeof R.hasRenderer === 'function',
            hasTable:       !!R.TIER_RENDERERS,
            tableKeys:      R.TIER_RENDERERS ? Object.keys(R.TIER_RENDERERS).sort() : [],
        };
    """
    r = run_with_dom(TIER_MODULES, setup)
    assert r["hasNamespace"]   is True
    assert r["schemaVersion"]  == 1
    assert r["hasGetter"]      is True
    assert r["hasHasRenderer"] is True
    assert r["hasTable"]       is True
    assert r["tableKeys"] == ["0", "1b", "2", "3", "4a", "4c"]


def test_runtime_resolves_all_six_demo_tiers_to_svg():
    setup = _palette_prelude() + r"""
        var R = window.M3TierRegistry;
        var tiers = ['4c', '4a', '3', '2', '1b', '0'];
        var out = {};
        for (var i = 0; i < tiers.length; i++) {
            var el = R.getTierRenderer(tiers[i], { p: p, width: 700, height: 600 });
            out[tiers[i]] = {
                tag:         el.tagName.toLowerCase(),
                placeholder: el.getAttribute('data-registry-placeholder'),
            };
        }
        result = out;
    """
    r = run_with_dom(TIER_MODULES, setup)
    for tier in ("4c", "4a", "3", "2", "1b", "0"):
        assert r[tier]["tag"] == "svg", f"tier {tier} did not resolve to svg"
        assert r[tier]["placeholder"] is None, f"tier {tier} fell to placeholder"


def test_runtime_hasRenderer_true_for_loaded_tiers():
    setup = _palette_prelude() + r"""
        var R = window.M3TierRegistry;
        result = {
            t4c: R.hasRenderer('4c'),
            t2:  R.hasRenderer('2'),
            t0:  R.hasRenderer('0'),
            t1a: R.hasRenderer('1a'),
            tUnknown: R.hasRenderer('zzz'),
        };
    """
    r = run_with_dom(TIER_MODULES, setup)
    assert r["t4c"] is True
    assert r["t2"]  is True
    assert r["t0"]  is True
    assert r["t1a"] is True   # Tier1aBody is in the composition engine
    assert r["tUnknown"] is False


def test_runtime_1a_without_data_returns_placeholder():
    setup = _palette_prelude() + r"""
        var R = window.M3TierRegistry;
        var el = R.getTierRenderer('1a', { p: p, width: 360, height: 420 });
        result = {
            tag:         el.tagName.toLowerCase(),
            placeholder: el.getAttribute('data-registry-placeholder'),
            tierAttr:    el.getAttribute('data-default-tier-body'),
        };
    """
    r = run_with_dom(TIER_MODULES, setup)
    assert r["tag"]         == "div"
    assert r["placeholder"] == "1"
    assert r["tierAttr"]    == "1a"


def test_runtime_1a_with_live_data_renders_svg():
    """When fed adapter-derived AreaGeometry data, 1a routes through
    M3CompositionEngine.Tier1aBody and returns a real svg."""
    setup = _palette_prelude() + r"""
        var geom = {
            schema_version: 1, area_key: 'tatooine.mos_eisley',
            display_name: 'MOS EISLEY',
            bounds: { x_min: 2.4, y_min: -0.4, x_max: 14.8, y_max: 7.6 },
            districts: [{ id: 'd1', polygon: [[3,0],[14,0],[14,7],[3,7]],
                         name: 'SPACEPORT', label_anchor: [8,3] }],
            rooms: [{ id: 1, x: 5, y: 2, w: 1, h: 1, slug: 'bay94', style: 'building' },
                    { id: 2, x: 8, y: 3, w: 1, h: 1, slug: 'cantina', style: 'building' }],
            exit_paths: [], landmarks: [], labels: [],
            player: { x: 5, y: 2 }, contacts: []
        };
        var data = window.M3Adapter.fromAreaGeometry(geom, null);
        var R = window.M3TierRegistry;
        var el = R.getTierRenderer('1a', { p: p, width: 360, height: 420, data: data });
        result = {
            adapterOk:   !!(data && data.bounds),
            roomCount:   data ? data.rooms.length : 0,
            tag:         el.tagName.toLowerCase(),
            placeholder: el.getAttribute('data-registry-placeholder'),
            childCount:  el.childNodes.length,
        };
    """
    r = run_with_dom(TIER_MODULES, setup)
    assert r["adapterOk"]   is True
    assert r["roomCount"]   == 2
    assert r["tag"]         == "svg"
    assert r["placeholder"] is None
    assert r["childCount"]  > 0


def test_runtime_unknown_tier_returns_placeholder_not_null():
    setup = _palette_prelude() + r"""
        var R = window.M3TierRegistry;
        var el = R.getTierRenderer('nonsense', { p: p, width: 200, height: 200 });
        result = {
            isNull:      el === null,
            tag:         el ? el.tagName.toLowerCase() : null,
            placeholder: el ? el.getAttribute('data-registry-placeholder') : null,
        };
    """
    r = run_with_dom(TIER_MODULES, setup)
    assert r["isNull"]      is False
    assert r["tag"]         == "div"
    assert r["placeholder"] == "1"


def test_runtime_interior_entities_override_flows_through():
    """getTierRenderer('0', { entities }) forwards the override to the
    interior builder."""
    setup = _palette_prelude() + r"""
        var R = window.M3TierRegistry;
        var el = R.getTierRenderer('0', {
            p: p, width: 700, height: 600,
            entities: [
                { x: 300, y: 300, name: 'LONE', faction: 'player' },
                { x: 350, y: 320, name: 'GUARD', faction: 'hostile' }
            ]
        });
        result = {
            tag:         el.tagName.toLowerCase(),
            entityCount: el.querySelectorAll('[data-entity]').length,
            hasLone:     el.textContent.indexOf('LONE') !== -1,
        };
    """
    r = run_with_dom(TIER_MODULES, setup)
    assert r["tag"]         == "svg"
    assert r["entityCount"] == 2
    assert r["hasLone"]     is True


def test_runtime_missing_module_degrades_to_placeholder():
    """If a tier module isn't loaded, the registry returns a labeled
    placeholder rather than throwing. Load ONLY the registry +
    palettes (no tier-body modules)."""
    minimal_modules = [
        SPA_DIR / "m3_tokens.js",
        SPA_DIR / "m3_palettes.js",
        MODULE,
    ]
    setup = _palette_prelude() + r"""
        var R = window.M3TierRegistry;
        var el = R.getTierRenderer('2', { p: p, width: 700, height: 600 });
        result = {
            tag:         el.tagName.toLowerCase(),
            placeholder: el.getAttribute('data-registry-placeholder'),
            hasRenderer: R.hasRenderer('2'),
        };
    """
    r = run_with_dom(minimal_modules, setup)
    assert r["tag"]         == "div"
    assert r["placeholder"] == "1"
    assert r["hasRenderer"] is False
