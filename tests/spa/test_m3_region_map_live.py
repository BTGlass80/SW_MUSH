"""
test_m3_region_map_live.py — Drop 4.15c regression lock for the live
Holocarta region/overview map (Option A from the 4.15b handoff).

4.15a made the wilderness body region-selectable; 4.15b wired the region
seam through the navigator / assembled-client and added
M3Adapter.regionKeyForArea. 4.15c mounts M3MapNavigator as a live,
player-reachable overview map in client.html — an additive affordance that
does NOT touch the tactical sector modal. Its '1b' wilderness tier renders
the player's region (Dune Sea vs Coruscant Underworld), derived from the
live area via regionKeyForArea; its '1a' tier renders the player's real
district via the new navigator `data` pass-through.

client.html is a full page (WebSocket, etc.), so its wiring is pinned with
static source assertions — the established pattern for this file. The
navigator `data` forwarding (a real JS change) gets a DOM runtime test.

What this file pins:
  · A ⊕ region-map button (openRegionMap) sits in the ground .map-frame.
  · The #holocarta-overlay container + .holocarta-overlay CSS exist.
  · openRegionMap derives regionKey via M3Adapter.regionKeyForArea,
    preferring the live per-tick wilderness region slug
    (window._sw_wildernessRegion, Drop 4.22) and falling back to the
    area_geometry payload; mounts M3MapNavigator.create with palette +
    regionKey + live data, opens '1b' when in a region else '1a'.
  · closeRegionMap destroys the navigator handle; ESC + backdrop close.
  · Functions are window-exported (the page script is an IIFE).
  · REGRESSION GUARD: the tactical sector modal (openMapModal, tier rail)
    is untouched.
  · M3MapNavigator forwards hooks.data to getTierRenderer (tier '1a'),
    alongside region/regionKey (no 4.15b regression).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
NAV_MODULE  = REPO_ROOT / "static" / "spa" / "m3_map_navigator.js"

SAMPLE_PALETTE = {
    "amber": "#ffc857", "red": "#ff5a4a", "green": "#7ce068",
    "cyan": "#7ce0d0", "gold": "#d4a44b", "ink": "#d6cbb7",
    "inkBright": "#fff4d6", "inkDim": "#a09584", "inkFaint": "#6b6253",
    "sky": "#2a2418", "skyDeep": "#1a160c",
}

from .spa_dom_harness import run_with_dom


def _html():
    return CLIENT_HTML.read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════════
# client.html — affordance + overlay present
# ════════════════════════════════════════════════════════════════════

def test_region_map_button_present():
    src = _html()
    # A button that opens the region map, styled as the holocarta variant.
    assert "openRegionMap()" in src
    assert "map-holocarta-btn" in src


def test_region_map_overlay_present():
    src = _html()
    assert 'id="holocarta-overlay"' in src
    assert "regionMapBackdropClick(event)" in src
    # CSS for the overlay must exist (the show toggle is the render gate).
    assert ".holocarta-overlay" in src
    assert ".holocarta-overlay.show" in src


def test_region_map_functions_defined_and_exported():
    src = _html()
    for fn in ("openRegionMap", "closeRegionMap", "regionMapBackdropClick"):
        assert ("function " + fn) in src, f"missing function {fn}"
        assert re.search(r"window\." + fn + r"\s*=\s*" + fn, src), (
            f"{fn} not exported to window (page script is an IIFE; inline "
            f"onclick handlers cannot reach un-exported functions)"
        )


# ════════════════════════════════════════════════════════════════════
# client.html — open path wires region + palette + data correctly
# ════════════════════════════════════════════════════════════════════

def test_open_region_map_derives_region_from_live_area():
    src = _html()
    # Drop 4.22: openRegionMap still derives the regionKey via
    # M3Adapter.regionKeyForArea, but now PREFERS the explicit per-tick
    # wilderness region slug the server stamps for wilderness rooms
    # (window._sw_wildernessRegion), falling back to the area_geometry
    # payload for covered city/interior areas. This is what makes the
    # painted wilderness substrate reachable: wilderness rooms have no
    # AreaGeometry, so _sw_areaGeom is null for them and the old
    # _sw_areaGeom-only argument always resolved to the Dune Sea default.
    assert "M3Adapter.regionKeyForArea(" in src
    assert "window._sw_wildernessRegion || window._sw_areaGeom" in src


def test_open_region_map_mounts_navigator_with_seed():
    src = _html()
    assert "M3MapNavigator.create(palette" in src
    # Open on the wilderness overview when in a region, else the district.
    assert "regionKey ? '1b' : '1a'" in src
    # Live district data forwarded so '1a' renders the real area.
    assert "M3Adapter.fromAreaGeometry(" in src


def test_close_region_map_destroys_handle():
    src = _html()
    # Find the closeRegionMap body and assert it disposes the navigator.
    m = re.search(r"function closeRegionMap\(\)\s*\{(.+?)\n\}", src, re.DOTALL)
    assert m, "closeRegionMap not found"
    body = m.group(1)
    assert ".destroy()" in body, "closeRegionMap must destroy the navigator handle"


def test_region_map_esc_handler_present():
    src = _html()
    assert "installRegionMapKeyHandler" in src
    # ESC handler must gate on the open flag (no global side effects).
    assert "_regionMapOpen" in src


# ════════════════════════════════════════════════════════════════════
# REGRESSION GUARD — the tactical sector modal is untouched
# ════════════════════════════════════════════════════════════════════

def test_tactical_sector_modal_untouched():
    src = _html()
    # The original sector-map modal entry + tier rail must still be present.
    assert "openMapModal('ground')" in src
    assert 'id="map-modal-overlay"' in src
    assert "setMapModalTier(1)" in src
    assert "setMapModalTier(2)" in src


# ════════════════════════════════════════════════════════════════════
# Navigator — forwards hooks.data to the tier renderer (tier '1a')
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_navigator_forwards_data_at_tier_1a():
    setup = _setup_prelude() + r"""
        var calls = [];
        var rec = function(tierId, args) {
            calls.push({
                tierId: tierId,
                dataName: (args.data && args.data.display_name) || null,
            });
            return document.createElement('div');
        };
        var handle = window.M3MapNavigator.create(p, {
            getTierRenderer: rec,
            startTier: '1a',
            data: { display_name: 'MOS EISLEY', rooms: [] },
        });
        document.body.appendChild(handle.element);
        result = { calls: calls };
    """
    out = run_with_dom([str(NAV_MODULE)], setup)
    assert len(out["calls"]) == 1
    assert out["calls"][0]["tierId"] == "1a"
    assert out["calls"][0]["dataName"] == "MOS EISLEY"


def test_navigator_forwards_data_and_region_together():
    """The 4.15c data pass-through must coexist with the 4.15b region
    pass-through — both reach getTierRenderer on the same call."""
    setup = _setup_prelude() + r"""
        var calls = [];
        var rec = function(tierId, args) {
            calls.push({
                tierId: tierId,
                regionKey: args.regionKey || null,
                dataName: (args.data && args.data.display_name) || null,
            });
            return document.createElement('div');
        };
        var handle = window.M3MapNavigator.create(p, {
            getTierRenderer: rec,
            startTier: '1b',
            regionKey: 'coruscant_underworld',
            data: { display_name: 'UNDERLEVELS' },
        });
        document.body.appendChild(handle.element);
        result = { calls: calls };
    """
    out = run_with_dom([str(NAV_MODULE)], setup)
    assert len(out["calls"]) == 1
    c = out["calls"][0]
    assert c["tierId"] == "1b"
    assert c["regionKey"] == "coruscant_underworld"
    assert c["dataName"] == "UNDERLEVELS"


def test_navigator_data_accepts_areaGeometryData_alias():
    setup = _setup_prelude() + r"""
        var calls = [];
        var rec = function(tierId, args) {
            calls.push({ dataName: (args.data && args.data.display_name) || null });
            return document.createElement('div');
        };
        var handle = window.M3MapNavigator.create(p, {
            getTierRenderer: rec,
            startTier: '1a',
            areaGeometryData: { display_name: 'ALIASED' },
        });
        document.body.appendChild(handle.element);
        result = { calls: calls };
    """
    out = run_with_dom([str(NAV_MODULE)], setup)
    assert len(out["calls"]) == 1
    assert out["calls"][0]["dataName"] == "ALIASED"
