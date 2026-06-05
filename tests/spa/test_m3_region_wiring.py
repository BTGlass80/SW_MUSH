"""
test_m3_region_wiring.py — Drop 4.15b regression lock for the wilderness
region-selection seam through the SPA map stack.

Drop 4.15a made m3_tier_wilderness_body.js render whichever region it is
handed (Dune Sea default, Coruscant Underworld added) and taught the tier
registry to forward region / regionKey. Drop 4.15b wires that seam through
the two consumers of the registry — M3MapNavigator and M3AssembledClient —
and adds M3Adapter.regionKeyForArea() so a caller holding the player's live
area geometry can derive the region slug in one call.

What this file pins:

  · M3MapNavigator.create accepts hooks.region / hooks.regionKey and
    forwards both to getTierRenderer for the active tier (only the '1b'
    builder consumes them; every other tier ignores the extra opts).
  · With neither supplied, region / regionKey arrive null (the '1b'
    builder then falls back to its Dune Sea default).
  · M3AssembledClient.create threads region / regionKey through the MAP
    popup into M3MapNavigator.create.
  · M3Adapter.regionKeyForArea maps a live area payload (or a bare slug)
    to a wilderness region slug, validated against the wilderness body's
    own registry — returns null for city/interior/unknown areas.

NOTE (intentional boundary — not a gap this drop closes): nothing here
mounts the navigator as a live, player-reachable map. The navigator/
assembled-client are still bound-but-not-live in client.html; making them
live (and emitting a clean region field from the server) are separate
drops. These tests pin the *seam*, not an end-to-end in-game render.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NAV_MODULE   = REPO_ROOT / "static" / "spa" / "m3_map_navigator.js"
AC_MODULE    = REPO_ROOT / "static" / "spa" / "m3_assembled_client.js"
ADAPTER_MODULE = REPO_ROOT / "static" / "spa" / "m3_adapter.js"
WILD_MODULE  = REPO_ROOT / "static" / "spa" / "m3_tier_wilderness_body.js"

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
    "body":      "#cdc3b0",
    "fg":        "#d6cbb7",
}

from .spa_dom_harness import run_with_dom


def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


# ════════════════════════════════════════════════════════════════════
# Static source checks
# ════════════════════════════════════════════════════════════════════

def test_navigator_source_forwards_region():
    src = NAV_MODULE.read_text(encoding="utf-8")
    # Captured from hooks…
    assert re.search(r"region\s*=\s*hooks\.region", src)
    assert re.search(r"regionKey\s*=\s*hooks\.regionKey", src)
    # …and forwarded into getTierRenderer opts.
    assert re.search(r"region:\s*region", src)
    assert re.search(r"regionKey:\s*regionKey", src)


def test_assembled_client_source_threads_region():
    src = AC_MODULE.read_text(encoding="utf-8")
    # Into M3MapNavigator.create and into the map-popup builder call.
    assert re.search(r"region:\s*hooks\.region", src)
    assert re.search(r"regionKey:\s*hooks\.regionKey", src)
    # The navigator spawn must carry it (guard against threading only the
    # popup builder but not the navigator).
    assert "M3MapNavigator.create" in src


def test_adapter_source_exports_region_key_helper():
    src = ADAPTER_MODULE.read_text(encoding="utf-8")
    assert "function regionKeyForArea" in src
    assert re.search(r"regionKeyForArea:\s*regionKeyForArea", src)
    # Source-of-truth delegation — must validate via the wilderness
    # registry rather than maintaining a second hard-coded list.
    assert "resolveRegion" in src


# ════════════════════════════════════════════════════════════════════
# Navigator: forwards region / regionKey to the tier renderer
# ════════════════════════════════════════════════════════════════════

def test_navigator_forwards_regionkey_at_tier_1b():
    setup = _setup_prelude() + r"""
        var calls = [];
        var rec = function(tierId, args) {
            calls.push({
                tierId: tierId,
                regionKey: (args.regionKey === undefined) ? null : args.regionKey,
                regionName: (args.region && args.region.name) || null,
            });
            var d = document.createElement('div');
            d.setAttribute('data-rec-body', tierId);
            return d;
        };
        var handle = window.M3MapNavigator.create(p, {
            getTierRenderer: rec,
            startTier: '1b',
            regionKey: 'coruscant_underworld',
        });
        document.body.appendChild(handle.element);
        result = { calls: calls };
    """
    out = run_with_dom([str(NAV_MODULE)], setup)
    assert len(out["calls"]) == 1
    c = out["calls"][0]
    assert c["tierId"] == "1b"
    assert c["regionKey"] == "coruscant_underworld"
    assert c["regionName"] is None   # no region object supplied


def test_navigator_forwards_region_object():
    setup = _setup_prelude() + r"""
        var calls = [];
        var rec = function(tierId, args) {
            calls.push({
                tierId: tierId,
                regionName: (args.region && args.region.name) || null,
            });
            return document.createElement('div');
        };
        var handle = window.M3MapNavigator.create(p, {
            getTierRenderer: rec,
            startTier: '1b',
            region: { name: 'CORUSCANT UNDERWORLD' },
        });
        document.body.appendChild(handle.element);
        result = { calls: calls };
    """
    out = run_with_dom([str(NAV_MODULE)], setup)
    assert len(out["calls"]) == 1
    assert out["calls"][0]["regionName"] == "CORUSCANT UNDERWORLD"


def test_navigator_region_null_when_not_supplied():
    setup = _setup_prelude() + r"""
        var calls = [];
        var rec = function(tierId, args) {
            calls.push({
                tierId: tierId,
                regionKeyNull: (args.regionKey === null || args.regionKey === undefined),
                regionNull:    (args.region === null || args.region === undefined),
                // the opts keys must still be present (forwarded, just empty)
                hasRegionKeyKey: ('regionKey' in args),
            });
            return document.createElement('div');
        };
        var handle = window.M3MapNavigator.create(p, {
            getTierRenderer: rec,
            startTier: '1b',
        });
        document.body.appendChild(handle.element);
        result = { calls: calls };
    """
    out = run_with_dom([str(NAV_MODULE)], setup)
    assert len(out["calls"]) == 1
    c = out["calls"][0]
    assert c["regionKeyNull"] is True
    assert c["regionNull"] is True
    assert c["hasRegionKeyKey"] is True


def test_navigator_other_tiers_receive_region_harmlessly():
    """region/regionKey are forwarded to whatever tier is active; non-'1b'
    builders simply ignore them. Pinning this documents that forwarding is
    unconditional (the wilderness body is the only consumer)."""
    setup = _setup_prelude() + r"""
        var calls = [];
        var rec = function(tierId, args) {
            calls.push({ tierId: tierId, regionKey: args.regionKey || null });
            return document.createElement('div');
        };
        var handle = window.M3MapNavigator.create(p, {
            getTierRenderer: rec,
            startTier: '3',                       // planet tier, not wilderness
            regionKey: 'coruscant_underworld',
        });
        document.body.appendChild(handle.element);
        result = { calls: calls };
    """
    out = run_with_dom([str(NAV_MODULE)], setup)
    assert len(out["calls"]) == 1
    assert out["calls"][0]["tierId"] == "3"
    assert out["calls"][0]["regionKey"] == "coruscant_underworld"


# ════════════════════════════════════════════════════════════════════
# Assembled client: threads region / regionKey into the navigator
# ════════════════════════════════════════════════════════════════════

def test_assembled_client_threads_region_into_navigator():
    setup = _setup_prelude() + r"""
        // Stub the navigator so we can capture exactly what hooks the
        // assembled-client's MAP popup hands it.
        var captured = null;
        window.M3MapNavigator = {
            create: function(pal, h) {
                captured = {
                    regionKey: (h && h.regionKey) || null,
                    regionName: (h && h.region && h.region.name) || null,
                };
                var el = document.createElement('div');
                el.setAttribute('data-stub-navigator', '1');
                return { element: el, destroy: function() {} };
            }
        };
        var handle = window.M3AssembledClient.create(p, {
            region:    { name: 'CORUSCANT UNDERWORLD' },
            regionKey: 'coruscant_underworld',
        });
        document.body.appendChild(handle.element);
        handle.openPopup('map');
        result = { captured: captured };
    """
    out = run_with_dom([str(AC_MODULE)], setup)
    assert out["captured"] is not None, "MAP popup never spawned the navigator"
    assert out["captured"]["regionKey"] == "coruscant_underworld"
    assert out["captured"]["regionName"] == "CORUSCANT UNDERWORLD"


# ════════════════════════════════════════════════════════════════════
# Adapter: regionKeyForArea mapping (validated via the wilderness registry)
# ════════════════════════════════════════════════════════════════════

def _adapter_setup(body):
    # Load the wilderness body first (defines resolveRegion) then the
    # adapter (defines regionKeyForArea, which calls resolveRegion).
    return _setup_prelude() + body


def test_adapter_region_key_underworld():
    setup = _adapter_setup(r"""
        result = { key: window.M3Adapter.regionKeyForArea({ area_key: 'coruscant_underworld' }) };
    """)
    out = run_with_dom([str(WILD_MODULE), str(ADAPTER_MODULE)], setup)
    assert out["key"] == "coruscant_underworld"


def test_adapter_region_key_dune_sea_alias():
    setup = _adapter_setup(r"""
        result = { key: window.M3Adapter.regionKeyForArea({ area_key: 'tatooine_dune_sea' }) };
    """)
    out = run_with_dom([str(WILD_MODULE), str(ADAPTER_MODULE)], setup)
    assert out["key"] == "tatooine_dune_sea"


def test_adapter_region_key_field_priority():
    """region_key wins over wilderness_region_id wins over area_key."""
    setup = _adapter_setup(r"""
        var A = window.M3Adapter;
        result = {
            explicit: A.regionKeyForArea({
                region_key: 'coruscant_underworld',
                area_key:   'mos_eisley'            // ignored
            }),
            wildId: A.regionKeyForArea({
                wilderness_region_id: 'tatooine_dune_sea',
                area_key:             'mos_eisley'  // ignored
            }),
        };
    """)
    out = run_with_dom([str(WILD_MODULE), str(ADAPTER_MODULE)], setup)
    assert out["explicit"] == "coruscant_underworld"
    assert out["wildId"]   == "tatooine_dune_sea"


def test_adapter_region_key_string_arg():
    setup = _adapter_setup(r"""
        result = { key: window.M3Adapter.regionKeyForArea('coruscant_underworld') };
    """)
    out = run_with_dom([str(WILD_MODULE), str(ADAPTER_MODULE)], setup)
    assert out["key"] == "coruscant_underworld"


def test_adapter_region_key_city_is_null():
    """A city/interior area (not a wilderness region) maps to null."""
    setup = _adapter_setup(r"""
        var A = window.M3Adapter;
        result = {
            city:    A.regionKeyForArea({ area_key: 'mos_eisley' }),
            empty:   A.regionKeyForArea({ }),
            nullArg: A.regionKeyForArea(null),
            blank:   A.regionKeyForArea(''),
        };
    """)
    out = run_with_dom([str(WILD_MODULE), str(ADAPTER_MODULE)], setup)
    assert out["city"]    is None
    assert out["empty"]   is None
    assert out["nullArg"] is None
    assert out["blank"]   is None
