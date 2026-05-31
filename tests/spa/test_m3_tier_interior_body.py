"""
test_m3_tier_interior_body.py — Drop 4.14 (Batch 2) regression lock for
m3_tier_interior_body.js.

Tier 0 — Chalmun's Cantina interior floorplan. SVG body + optional
HolocartaFrame chrome via composition-engine DI.

What this file pins:

  · Module shape (IIFE + window.M3TierInteriorBody + documented surface).
  · Two builders: buildTierZeroBody (inner SVG) and
    buildTierZeroCantina (chrome-wrapped).
  · buildTierZeroBody renders an SVG with 5 furniture footprints,
    4 named exits, 7 entity dots, floor grid.
  · Entities are overridable via opts.entities.
  · B3 era cleanness — zero Empire/Imperial/Rebel/TIE/X-wing refs.
  · The player entity (faction=player) gets a glow ring; hostile
    entities render as triangles.
  · Q1 source-fidelity flag — CHALMUN'S CANTINA + DEJARIK TABLE
    preserved.
  · Loud-substitution: undocumented palette keys (p.paper, p.ground,
    p.groundDeep) fall back gracefully.
  · Defensive DI: when M3CompositionEngine.HolocartaFrame is missing,
    buildTierZeroCantina returns a labeled fallback rather than throwing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = REPO_ROOT / "static" / "spa" / "m3_tier_interior_body.js"
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
    assert "window.M3TierInteriorBody" in src


def test_module_defines_both_builders():
    src = MODULE.read_text(encoding="utf-8")
    assert "function buildTierZeroBody(" in src
    assert "function buildTierZeroCantina(" in src
    assert re.search(r"buildTierZeroBody\s*:\s*buildTierZeroBody\b", src)
    assert re.search(
        r"buildTierZeroCantina\s*:\s*buildTierZeroCantina\b", src
    )


def test_module_defines_fixtures():
    src = MODULE.read_text(encoding="utf-8")
    for fixture in ("FURNITURE", "EXITS", "ENTITIES", "ROOM"):
        assert "var " + fixture + " = " in src
        assert re.search(fixture + r"\s*:\s*" + fixture + r"\b", src)


def test_module_applies_palette_fallbacks():
    """Drop 4.11 loud-substitution: p.paper / p.ground / p.groundDeep
    must have || fallbacks so the interior renders on standard palettes
    that don't define these keys."""
    src = MODULE.read_text(encoding="utf-8")
    assert "p.paper" in src and "|| p.inkBright" in src
    assert "p.ground" in src and "|| p.amber" in src
    assert "p.groundDeep" in src and "|| p.skyDeep" in src


def test_client_html_loads_module():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_tier_interior_body.js" in src


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


def test_q1_dejarik_table_preserved():
    """DEJARIK TABLE preserved verbatim per source-fidelity policy."""
    src = MODULE.read_text(encoding="utf-8")
    assert "DEJARIK TABLE" in src


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3TierInteriorBody;
        result = {
            hasNamespace:   !!N,
            schemaVersion:  N && N.SCHEMA_VERSION,
            hasBody:        typeof N.buildTierZeroBody === 'function',
            hasCantina:     typeof N.buildTierZeroCantina === 'function',
            hasFurniture:   Array.isArray(N.FURNITURE),
            hasExits:       Array.isArray(N.EXITS),
            hasEntities:    Array.isArray(N.ENTITIES),
            hasRoom:        !!N.ROOM && typeof N.ROOM === 'object',
            furnitureCount: N.FURNITURE.length,
            exitCount:      N.EXITS.length,
            entityCount:    N.ENTITIES.length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasNamespace"]   is True
    assert r["schemaVersion"]  == 1
    assert r["hasBody"]        is True
    assert r["hasCantina"]     is True
    assert r["hasFurniture"]   is True
    assert r["hasExits"]       is True
    assert r["hasEntities"]    is True
    assert r["hasRoom"]        is True
    assert r["furnitureCount"] == 5
    assert r["exitCount"]      == 4
    assert r["entityCount"]    == 7


def test_runtime_buildTierZeroBody_renders_svg():
    setup = _setup_prelude() + r"""
        var N = window.M3TierInteriorBody;
        var el = N.buildTierZeroBody(p);
        document.body.appendChild(el);
        result = {
            tag:          el.tagName.toLowerCase(),
            isInterior:   el.getAttribute('data-tier-interior') === '1',
            width:        el.getAttribute('width'),
            height:       el.getAttribute('height'),
            hasDefs:      !!el.querySelector('defs'),
            hasFloorGrid: !!el.querySelector('[data-layer="floor-grid"]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]          == "svg"
    assert r["isInterior"]   is True
    assert r["width"]        == "700"
    assert r["height"]       == "600"
    assert r["hasDefs"]      is True
    assert r["hasFloorGrid"] is True


def test_runtime_renders_5_furniture():
    setup = _setup_prelude() + r"""
        var N = window.M3TierInteriorBody;
        var el = N.buildTierZeroBody(p);
        document.body.appendChild(el);
        var fs = el.querySelectorAll('[data-furniture]');
        var names = [];
        for (var i = 0; i < fs.length; i++) {
            names.push(fs[i].getAttribute('data-furniture'));
        }
        result = { count: fs.length, names: names };
    """
    r = run_with_dom([MODULE], setup)
    assert r["count"] == 5
    assert "BAR COUNTER" in r["names"]
    assert "BANDSTAND" in r["names"]
    assert "DEJARIK TABLE" in r["names"]
    assert "BOOTH CLUSTER" in r["names"]
    assert "RAISED DAIS" in r["names"]


def test_runtime_renders_4_exits():
    setup = _setup_prelude() + r"""
        var N = window.M3TierInteriorBody;
        var el = N.buildTierZeroBody(p);
        document.body.appendChild(el);
        var xs = el.querySelectorAll('[data-exit]');
        var names = [];
        for (var i = 0; i < xs.length; i++) {
            names.push(xs[i].getAttribute('data-exit'));
        }
        result = { count: xs.length, names: names };
    """
    r = run_with_dom([MODULE], setup)
    assert r["count"] == 4
    assert "FRONT ENTRANCE" in r["names"]
    assert "BAR STOREROOM" in r["names"]
    assert "BACK HALL" in r["names"]
    assert "BOOTH ALCOVE" in r["names"]


def test_runtime_renders_7_entities_with_player_and_hostile():
    setup = _setup_prelude() + r"""
        var N = window.M3TierInteriorBody;
        var el = N.buildTierZeroBody(p);
        document.body.appendChild(el);
        var es = el.querySelectorAll('[data-entity]');
        var names = [];
        var you = null, enforcer = null;
        for (var i = 0; i < es.length; i++) {
            var n = es[i].getAttribute('data-entity');
            names.push(n);
            if (n === 'YOU')      you = es[i];
            if (n === 'ENFORCER') enforcer = es[i];
        }
        result = {
            count:        es.length,
            names:        names,
            youFaction:   you && you.getAttribute('data-entity-faction'),
            enforcerFaction: enforcer && enforcer.getAttribute('data-entity-faction'),
            enforcerTag:  enforcer && enforcer.tagName.toLowerCase(),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["count"] == 7
    assert "YOU" in r["names"]
    assert "BARKEEP" in r["names"]
    assert "ENFORCER" in r["names"]
    assert r["youFaction"]      == "player"
    assert r["enforcerFaction"] == "hostile"
    # Hostile entities render as a triangle <path>, not a <circle>.
    assert r["enforcerTag"] == "path"


def test_runtime_entities_override():
    """opts.entities overrides the demo patrons; occupancy subtitle
    reflects the override count."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierInteriorBody;
        var el = N.buildTierZeroBody(p, {
            entities: [
                { x: 300, y: 300, name: 'LONE', faction: 'player' },
                { x: 350, y: 320, name: 'GUARD', faction: 'hostile' }
            ]
        });
        document.body.appendChild(el);
        result = {
            entityCount: el.querySelectorAll('[data-entity]').length,
            hasLone:     el.textContent.indexOf('LONE') !== -1,
            occupancy:   el.textContent.indexOf('2 PRESENT') !== -1,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["entityCount"] == 2
    assert r["hasLone"]     is True
    assert r["occupancy"]   is True


def test_runtime_palette_fallbacks_work():
    """A palette omitting p.paper/p.ground/p.groundDeep still renders."""
    minimal = {
        "amber": "#ffc857", "red": "#ff5a4a", "green": "#7ce068",
        "cyan": "#7ce0d0", "gold": "#d4a44b", "ink": "#d6cbb7",
        "inkBright": "#fff4d6", "inkDim": "#a09584", "skyDeep": "#1a160c",
    }
    setup = "var p = " + json.dumps(minimal) + ";\n" + r"""
        var N = window.M3TierInteriorBody;
        var el = N.buildTierZeroBody(p);
        document.body.appendChild(el);
        result = {
            tag:            el.tagName.toLowerCase(),
            furnitureCount: el.querySelectorAll('[data-furniture]').length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"] == "svg"
    assert r["furnitureCount"] == 5


def test_runtime_cantina_chrome_fallback_without_holocarta():
    """buildTierZeroCantina returns a labeled fallback div when
    HolocartaFrame is unavailable (rather than throwing)."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierInteriorBody;
        var el = N.buildTierZeroCantina(p);
        document.body.appendChild(el);
        result = {
            tag:        el.tagName.toLowerCase(),
            fallback:   el.getAttribute('data-tier-interior-frame-fallback'),
            hasSvg:     !!el.querySelector('svg'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["tag"]      == "div"
    assert r["fallback"] == "1"
    assert r["hasSvg"]   is True


def test_runtime_cantina_chrome_uses_holocarta_when_present():
    """When a HolocartaFrame stub is present, buildTierZeroCantina
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
        var N = window.M3TierInteriorBody;
        var el = N.buildTierZeroCantina(p);
        document.body.appendChild(el);
        result = {
            holocarta: el.getAttribute('data-holocarta'),
            tier:      el.getAttribute('data-tier'),
            hasSvg:    !!el.querySelector('svg'),
            fallback:  el.getAttribute('data-tier-interior-frame-fallback'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["holocarta"] == "1"
    assert "INTERIOR" in r["tier"]
    assert r["hasSvg"]    is True
    assert r["fallback"]  is None
