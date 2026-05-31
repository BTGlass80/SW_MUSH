"""
test_m3_tier_wilderness_region.py — Drop 4.15a regression lock for the
region-selectable + substrate-first generalization of
m3_tier_wilderness_body.js.

Drop 4.14 shipped the Dune Sea wilderness body hardwired. Drop 4.15a
generalizes it to "render the region passed in, substrate-first" and adds a
second region — the Coruscant Underworld — closing the Tatooine/Coruscant
parity gap at the renderer layer (the underworld *data* was already at parity;
only the renderer was hardwired to Tatooine sand).

What this file pins (deliberately a SEPARATE file, not an extension of
test_m3_tier_wilderness_body.py — per-drop test discipline):

  · New public surface: buildTierOneBRegion, buildTierOneBUnderworld,
    REGIONS, resolveRegion, CORUSCANT_UNDERWORLD.
  · Region-omitted → Dune Sea default is byte-stable (the 4.14 contract is
    untouched; that file's 19 tests are the primary guard, this re-pins the
    default from the region seam's side).
  · regionKey='coruscant_underworld' renders the underworld: its title,
    its sub-regions, its POIs — and NONE of the Dune Sea landmarks.
  · A region object passed directly (opts.region) wins over regionKey.
  · Loud-substitution: a partial region (e.g. missing `pois`) falls back to
    the Dune Sea fixture for the missing slice while honoring what it does
    supply (title, sub_regions). Mirrors the Drop 4.11 palette-key policy.
  · Substrate-first: a region carrying `substrate_image` paints an
    <image data-layer="substrate"> and SKIPS the procedural ground/dune
    plate and sub-region terrain blobs, while POIs/routes stay on top.
    This mirrors L_SubstrateImage in m3_composition_engine.js.
  · resolveRegion alias/miss semantics (dune_sea / tatooine_dune_sea /
    coruscant_underworld; unknown → null → DUNE_SEA fallback).
  · The chrome path (buildTierOneBRegion) flows the region's breadcrumb /
    tier / legend through HolocartaFrame.
  · B3 era cleanness + Q1 canonical-individual policy for the new fixture.
  · m3_tier_registry.js forwards region / regionKey through getTierRenderer.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = REPO_ROOT / "static" / "spa" / "m3_tier_wilderness_body.js"
REGISTRY = REPO_ROOT / "static" / "spa" / "m3_tier_registry.js"

# Minimal palette intentionally lacking p.paper / p.ground / p.groundDeep
# / p.groundShadow to exercise loud-substitution fallbacks (same shape the
# Drop 4.14 suite uses).
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


def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


# Minimal HolocartaFrame stub: records the breadcrumb / tier / legend it was
# handed and returns a queryable div. Lets the chrome path be exercised
# without the real composition engine present in the harness.
_HOLOCARTA_STUB = r"""
    window.M3CompositionEngine = window.M3CompositionEngine || {};
    window.M3CompositionEngine.HolocartaFrame = function(o) {
        var d = document.createElement('div');
        d.setAttribute('data-holocarta', '1');
        d.setAttribute('data-breadcrumb', o.breadcrumb || '');
        d.setAttribute('data-tier', o.tier || '');
        d.setAttribute('data-legend-count', String((o.legend || []).length));
        var kids = o.children || [];
        for (var i = 0; i < kids.length; i++) d.appendChild(kids[i]);
        return d;
    };
"""


# ════════════════════════════════════════════════════════════════════
# Static source checks
# ════════════════════════════════════════════════════════════════════

def test_module_exports_region_surface():
    src = MODULE.read_text(encoding="utf-8")
    for sym in (
        "buildTierOneBRegion",
        "buildTierOneBUnderworld",
        "CORUSCANT_UNDERWORLD",
        "resolveRegion",
    ):
        assert sym in src, f"missing symbol in source: {sym}"
    # Exported on the namespace object (not merely defined locally).
    assert re.search(r"REGIONS:\s*REGIONS", src)
    assert re.search(r"resolveRegion:\s*resolveRegion", src)
    assert re.search(r"CORUSCANT_UNDERWORLD:\s*CORUSCANT_UNDERWORLD", src)


def test_registry_forwards_region_params():
    src = REGISTRY.read_text(encoding="utf-8")
    # getTierRenderer must forward both region and regionKey into the
    # uniform opts handed to the demo-fixture body builders.
    assert re.search(r"region:\s*args\.region", src)
    assert re.search(r"regionKey:\s*args\.regionKey", src)


def test_underworld_fixture_era_clean():
    """B3: the new fixture must not introduce Empire-era references."""
    src = MODULE.read_text(encoding="utf-8")
    # Strip block + line comments before grepping (B3 policy: comments are
    # allowed to mention era for documentation; rendered strings are not).
    no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    no_comments = re.sub(r"//[^\n]*", "", no_block)
    banned = ["empire", "imperial", "rebel", "stormtrooper", "tie fighter",
              "x-wing", "death star"]
    low = no_comments.lower()
    for term in banned:
        assert term not in low, f"era-dirty token in code: {term!r}"


def test_underworld_fixture_no_canonical_individuals():
    """Q1: no canonical-restricted individuals baked into the fixture."""
    src = MODULE.read_text(encoding="utf-8")
    no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    no_comments = re.sub(r"//[^\n]*", "", no_block)
    low = no_comments.lower()
    for name in ("anakin", "obi-wan", "obiwan", "yoda", "mace windu",
                 "dooku", "grievous", "palpatine", "sidious"):
        assert name not in low, f"canonical individual in code: {name!r}"


# ════════════════════════════════════════════════════════════════════
# Runtime: exports + resolver
# ════════════════════════════════════════════════════════════════════

def test_runtime_region_surface_present():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        result = {
            hasRegionBuilder:   typeof N.buildTierOneBRegion === 'function',
            hasUnderworld:      typeof N.buildTierOneBUnderworld === 'function',
            hasResolve:         typeof N.resolveRegion === 'function',
            hasRegionsTable:    !!N.REGIONS && typeof N.REGIONS === 'object',
            hasUnderworldObj:   !!N.CORUSCANT_UNDERWORLD &&
                                typeof N.CORUSCANT_UNDERWORLD === 'object',
            underworldName:     N.CORUSCANT_UNDERWORLD &&
                                N.CORUSCANT_UNDERWORLD.name,
            regionsKeys:        N.REGIONS ? Object.keys(N.REGIONS).sort() : [],
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["hasRegionBuilder"] is True
    assert r["hasUnderworld"]    is True
    assert r["hasResolve"]       is True
    assert r["hasRegionsTable"]  is True
    assert r["hasUnderworldObj"] is True
    assert r["underworldName"]   == "CORUSCANT UNDERWORLD"
    assert "coruscant_underworld" in r["regionsKeys"]
    assert "dune_sea" in r["regionsKeys"]


def test_runtime_resolve_region_aliases_and_miss():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        result = {
            dune:        N.resolveRegion('dune_sea') === N.DUNE_SEA,
            duneAlias:   N.resolveRegion('tatooine_dune_sea') === N.DUNE_SEA,
            duneUpper:   N.resolveRegion('DUNE_SEA') === N.DUNE_SEA,
            under:       N.resolveRegion('coruscant_underworld') ===
                         N.CORUSCANT_UNDERWORLD,
            missNull:    N.resolveRegion('nowhere') === null,
            emptyNull:   N.resolveRegion('') === null,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["dune"]      is True
    assert r["duneAlias"] is True
    assert r["duneUpper"] is True
    assert r["under"]     is True
    assert r["missNull"]  is True
    assert r["emptyNull"] is True


# ════════════════════════════════════════════════════════════════════
# Runtime: Dune Sea default is byte-stable from the region seam
# ════════════════════════════════════════════════════════════════════

def test_runtime_region_omitted_renders_dune_sea():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBBody(p);          // no region/regionKey
        document.body.appendChild(el);
        var texts = el.querySelectorAll('text');
        var titles = [];
        for (var i = 0; i < texts.length; i++) titles.push(texts[i].textContent);
        var poiNames = [];
        var ps = el.querySelectorAll('[data-poi]');
        for (var j = 0; j < ps.length; j++) poiNames.push(ps[j].getAttribute('data-poi'));
        result = {
            titlePresent:  titles.indexOf('DUNE SEA') !== -1,
            duneRidges:    el.querySelectorAll('[data-layer="dunes"] polyline').length,
            subregions:    el.querySelectorAll('[data-subregion]').length,
            hasMoistFarm:  poiNames.indexOf('MOISTURE FARM') !== -1,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["titlePresent"] is True
    assert r["duneRidges"]   == 9
    assert r["subregions"]   == 5
    assert r["hasMoistFarm"] is True


# ════════════════════════════════════════════════════════════════════
# Runtime: Coruscant Underworld renders from regionKey
# ════════════════════════════════════════════════════════════════════

def test_runtime_underworld_by_regionkey():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBBody(p, { regionKey: 'coruscant_underworld' });
        document.body.appendChild(el);

        var texts = el.querySelectorAll('text');
        var titles = [];
        for (var i = 0; i < texts.length; i++) titles.push(texts[i].textContent);

        var srNames = [];
        var srs = el.querySelectorAll('[data-subregion]');
        for (var s = 0; s < srs.length; s++) srNames.push(srs[s].getAttribute('data-subregion'));

        var poiNames = [];
        var ps = el.querySelectorAll('[data-poi]');
        for (var j = 0; j < ps.length; j++) poiNames.push(ps[j].getAttribute('data-poi'));

        result = {
            titleUnderworld: titles.indexOf('CORUSCANT UNDERWORLD') !== -1,
            srNames:         srNames,
            poiNames:        poiNames,
            // descent flavour: dark svg background + flattened strata count
            bg:              (el.getAttribute('style') || ''),
            ridges:          el.querySelectorAll('[data-layer="dunes"] polyline').length,
            // no Dune Sea leakage
            hasKrayt:        srNames.indexOf('KRAYT GRAVEYARD') !== -1,
            hasSarlacc:      poiNames.indexOf('SARLACC PIT') !== -1,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["titleUnderworld"] is True
    # underworld sub-regions present
    assert "FERROCRETE WARRENS" in r["srNames"]
    assert "THE BOTTOM DARK" in r["srNames"]
    assert "INDUSTRIAL RUIN" in r["srNames"]
    # underworld POIs present (faithful to the landmark YAML)
    assert "TRANSIT SHAFT" in r["poiNames"]
    assert "BLACK SUN HIDEOUT" in r["poiNames"]
    assert "REAPER'S MAZE" in r["poiNames"]
    assert "USCRU FRINGE" in r["poiNames"]
    # descent flavour: dark background, fewer flattened strata than dunes.
    # (jsdom normalizes the inline hex to rgb(); accept either form.)
    assert ("#070809" in r["bg"]) or ("rgb(7, 8, 9)" in r["bg"])
    assert r["ridges"] == 6
    # NO Tatooine landmark leakage
    assert r["hasKrayt"]   is False
    assert r["hasSarlacc"] is False


def test_runtime_region_object_overrides_regionkey():
    """A region object passed directly wins over a (conflicting) regionKey."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBBody(p, {
            regionKey: 'dune_sea',                 // would resolve to Dune Sea
            region:    N.CORUSCANT_UNDERWORLD      // ...but object wins
        });
        document.body.appendChild(el);
        var texts = el.querySelectorAll('text');
        var titles = [];
        for (var i = 0; i < texts.length; i++) titles.push(texts[i].textContent);
        result = {
            underworld: titles.indexOf('CORUSCANT UNDERWORLD') !== -1,
            dune:       titles.indexOf('DUNE SEA') !== -1,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["underworld"] is True
    assert r["dune"]       is False


# ════════════════════════════════════════════════════════════════════
# Runtime: loud-substitution for a partial region
# ════════════════════════════════════════════════════════════════════

def test_runtime_partial_region_falls_back_to_dune_pois():
    """A region supplying only name + sub_regions keeps its own title/sub-
    regions but falls back to the Dune Sea POIs for the slice it omits."""
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var partial = {
            name: 'TEST REGION',
            biome: 'TEST BIOME',
            sub_regions: [
                { d: 'M 0 0 L 10 0 L 10 10 Z', name: 'TEST ZONE',
                  fill: '#222', opacity: 0.8, lx: 5, ly: 5, color: 'inkBright' }
            ]
            // pois + routes intentionally omitted
        };
        var el = N.buildTierOneBBody(p, { region: partial });
        document.body.appendChild(el);
        var texts = el.querySelectorAll('text');
        var titles = [];
        for (var i = 0; i < texts.length; i++) titles.push(texts[i].textContent);
        var srNames = [];
        var srs = el.querySelectorAll('[data-subregion]');
        for (var s = 0; s < srs.length; s++) srNames.push(srs[s].getAttribute('data-subregion'));
        var poiNames = [];
        var ps = el.querySelectorAll('[data-poi]');
        for (var j = 0; j < ps.length; j++) poiNames.push(ps[j].getAttribute('data-poi'));
        result = {
            title:        titles.indexOf('TEST REGION') !== -1,
            ownSubregion: srNames.indexOf('TEST ZONE') !== -1,
            subCount:     srNames.length,
            // POIs omitted → loud fallback to Dune Sea fixture
            fellBackPois: poiNames.indexOf('MOISTURE FARM') !== -1,
            poiCount:     poiNames.length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["title"]        is True
    assert r["ownSubregion"] is True
    assert r["subCount"]     == 1
    assert r["fellBackPois"] is True
    assert r["poiCount"]     == 6


# ════════════════════════════════════════════════════════════════════
# Runtime: substrate-first
# ════════════════════════════════════════════════════════════════════

def test_runtime_substrate_paints_image_and_skips_procedural():
    setup = _setup_prelude() + r"""
        var N = window.M3TierWildernessBody;
        var region = {
            name: 'PAINTED REGION',
            biome: 'PAINTED',
            substrate_image: 'maps/test_region.png',
            pois: [ { x: 100, y: 100, name: 'PIN A', size: 7 } ],
            routes: [],
            sub_regions: [
                { d: 'M 0 0 L 10 0 L 10 10 Z', name: 'SHOULD NOT RENDER',
                  fill: '#222', opacity: 0.8, lx: 5, ly: 5, color: 'inkBright' }
            ]
        };
        var el = N.buildTierOneBBody(p, { region: region });
        document.body.appendChild(el);
        var img = el.querySelector('image[data-layer="substrate"]');
        result = {
            imageCount:   el.querySelectorAll('image[data-layer="substrate"]').length,
            href:         img && img.getAttribute('href'),
            preserve:     img && img.getAttribute('preserveAspectRatio'),
            // procedural plate + ridges skipped under a painting
            dunesGroups:  el.querySelectorAll('[data-layer="dunes"]').length,
            subregions:   el.querySelectorAll('[data-subregion]').length,
            // POIs still painted on top
            pois:         el.querySelectorAll('[data-poi]').length,
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["imageCount"]  == 1
    assert r["href"]        == "maps/test_region.png"
    assert r["preserve"]    == "none"
    assert r["dunesGroups"] == 0   # no procedural dune ridges under a painting
    assert r["subregions"]  == 0   # no terrain blobs under a painting
    assert r["pois"]        == 1   # navigable POIs stay on top


# ════════════════════════════════════════════════════════════════════
# Runtime: chrome path flows region descriptor through HolocartaFrame
# ════════════════════════════════════════════════════════════════════

def test_runtime_chrome_underworld_breadcrumb():
    setup = _setup_prelude() + _HOLOCARTA_STUB + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBUnderworld(p);
        document.body.appendChild(el);
        result = {
            holocarta:  el.getAttribute('data-holocarta'),
            breadcrumb: el.getAttribute('data-breadcrumb'),
            tier:       el.getAttribute('data-tier'),
            legendCt:   el.getAttribute('data-legend-count'),
            hasInner:   !!el.querySelector('[data-tier-wilderness="1"]'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert r["holocarta"] == "1"
    assert "UNDERWORLD" in (r["breadcrumb"] or "")
    assert "CORE" in (r["breadcrumb"] or "")
    assert r["tier"]     == "1B \u00b7 WILDERNESS"
    assert r["legendCt"] == "4"
    assert r["hasInner"] is True


def test_runtime_chrome_dune_sea_breadcrumb_unchanged():
    """The 4.14 chrome default (Dune Sea) still flows its own breadcrumb."""
    setup = _setup_prelude() + _HOLOCARTA_STUB + r"""
        var N = window.M3TierWildernessBody;
        var el = N.buildTierOneBDuneSea(p);
        document.body.appendChild(el);
        result = {
            breadcrumb: el.getAttribute('data-breadcrumb'),
            tier:       el.getAttribute('data-tier'),
        };
    """
    r = run_with_dom([MODULE], setup)
    assert "DUNE SEA" in (r["breadcrumb"] or "")
    assert "TATOOINE" in (r["breadcrumb"] or "")
    assert r["tier"] == "1B \u00b7 WILDERNESS"
