"""
test_m3_map_navigator.py — Drop 4.8 regression lock for m3_map_navigator.js.

Drop 4.8 ports map_v3/map-navigator.jsx (394 JSX LOC) into a vanilla-JS
SPA module at static/spa/m3_map_navigator.js. The module exports a
stateful component: M3MapNavigator.create(p, hooks) instantiates a
self-contained orchestrator that owns its tier/zoom/pan/phase state
inside a closure. This is the first SPA module to follow this pattern.

This file pins:
  · Module shape (IIFE + window.M3MapNavigator + documented surface).
  · TIER_DEFS contract (7-tier ladder, Clone-Wars-era references only).
  · create() returns a handle with the documented methods.
  · The hooks.getTierRenderer DI seam works correctly.
  · State mutations (jumpTo, getState, closeHolocron) behave as documented.
  · Crumb-row clicks dispatch jumpTo.
  · Holocron button click calls hooks.onHolocronOpen.
  · destroy() removes the wheel handler.

Pattern parallels tests/spa/test_m3_holocron.py (Drop 4.7).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT       = Path(__file__).resolve().parent.parent.parent
NAV_MODULE      = REPO_ROOT / "static" / "spa" / "m3_map_navigator.js"
CLIENT_HTML     = REPO_ROOT / "static" / "client.html"

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
    assert NAV_MODULE.exists(), (
        f"Module missing at {NAV_MODULE}. Drop 4.8 either didn't "
        "ship or was reverted."
    )


def test_module_is_iife():
    src = NAV_MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src, (
        "m3_map_navigator.js must be wrapped in an IIFE."
    )
    assert "})();" in src, "IIFE not closed at end of m3_map_navigator.js"


def test_module_exports_namespace():
    src = NAV_MODULE.read_text(encoding="utf-8")
    assert "window.M3MapNavigator" in src, (
        "Module must export window.M3MapNavigator"
    )


def test_module_defines_all_documented_exports():
    """The module exports init + create + TIER_DEFS + helpers."""
    src = NAV_MODULE.read_text(encoding="utf-8")
    # Functions defined
    for fn in ["init", "create", "tierIndex", "tierAt",
               "legendForTier", "buildZoomBtn"]:
        assert "function " + fn in src, f"Missing function definition: {fn}"
    # Exported entries (function exports)
    for fn in ["init", "create", "tierIndex", "tierAt",
               "legendForTier", "buildZoomBtn"]:
        assert re.search(r"\b" + fn + r"\s*:\s*" + fn + r"\b", src), (
            f"Missing export entry for {fn} in window.M3MapNavigator"
        )
    # TIER_DEFS export
    assert re.search(r"TIER_DEFS\s*:\s*TIER_DEFS\b", src)


def test_client_html_loads_module_and_calls_init():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert '/static/spa/m3_map_navigator.js' in src
    assert "M3MapNavigator.init(" in src


# ════════════════════════════════════════════════════════════════════
# TIER_DEFS contract — Clone-Wars-era references only
# ════════════════════════════════════════════════════════════════════

def test_tier_defs_has_seven_entries():
    src = NAV_MODULE.read_text(encoding="utf-8")
    m = re.search(r"var TIER_DEFS\s*=\s*\[(.+?)\];", src, flags=re.DOTALL)
    assert m, "TIER_DEFS array not found"
    block = m.group(1)
    # Count "id: 'X'" patterns
    ids = re.findall(r"id:\s*'([^']+)'", block)
    expected_ids = ['4c', '4a', '3', '2', '1a', '0', '1b']
    assert ids == expected_ids, (
        f"TIER_DEFS ids mismatch. Expected {expected_ids}, got {ids}"
    )


def test_tier_defs_clone_wars_era_references():
    """TIER_DEFS includes Clone Wars (~20 BBY) framing; no Empire refs.
    Scoped to the TIER_DEFS array, NOT module-level comments."""
    src = NAV_MODULE.read_text(encoding="utf-8")
    m = re.search(r"var TIER_DEFS\s*=\s*\[(.+?)\];", src, flags=re.DOTALL)
    assert m, "TIER_DEFS array not found"
    block = m.group(1)
    # Clone Wars era marker
    assert "Clone Wars" in block, (
        "TIER_DEFS must mention Clone Wars era (20 BBY) for the galaxy tier"
    )
    assert "20 BBY" in block, (
        "TIER_DEFS must include the 20 BBY date for tier 4c"
    )
    # No Empire framing inside the data block.
    assert "Empire" not in block, (
        "TIER_DEFS regression: 'Empire' references in tier sub-labels"
    )
    assert "Imperial" not in block, (
        "TIER_DEFS regression: 'Imperial' references in tier sub-labels"
    )


def test_tier_defs_dune_sea_is_branch():
    """The 1b 'DUNE SEA' wilderness tier is marked as a branch off the
    main ladder."""
    src = NAV_MODULE.read_text(encoding="utf-8")
    m = re.search(r"var TIER_DEFS\s*=\s*\[(.+?)\];", src, flags=re.DOTALL)
    block = m.group(1)
    # Find the 1b entry and verify it has branch: true.
    dune = re.search(r"id:\s*'1b'[^}]+branch:\s*true", block)
    assert dune, "Tier 1b 'DUNE SEA' must be marked with branch: true"


def test_legend_for_tier_no_imperial_references():
    """The legendForTier function returns legend entries per tier;
    none should mention Empire/Imperial."""
    src = NAV_MODULE.read_text(encoding="utf-8")
    # Extract the legendForTier function body.
    m = re.search(
        r"function legendForTier\([^)]*\)\s*\{(.+?)^\}",
        src, flags=re.DOTALL | re.MULTILINE
    )
    assert m, "legendForTier function not found"
    block = m.group(1)
    # The legend includes 'REPUBLIC', 'CIS', 'HUTT SPACE' (Clone Wars era);
    # no Empire/Imperial labels.
    assert "REPUBLIC" in block
    assert "'CIS'" in block
    assert "Empire" not in block, (
        "legendForTier regression: 'Empire' in legend labels"
    )
    assert "Imperial" not in block, (
        "legendForTier regression: 'Imperial' in legend labels"
    )


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests — the stateful handle contract
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3MapNavigator;
        result = {
            hasNamespace:    !!N,
            schemaVersion:   N && N.SCHEMA_VERSION,
            hasInit:         typeof N.init === 'function',
            hasCreate:       typeof N.create === 'function',
            hasTierDefs:     Array.isArray(N.TIER_DEFS),
            tierDefsLength:  N.TIER_DEFS.length,
            hasTierIndex:    typeof N.tierIndex === 'function',
            hasTierAt:       typeof N.tierAt === 'function',
            hasLegendFor:    typeof N.legendForTier === 'function',
            hasZoomBtn:      typeof N.buildZoomBtn === 'function',
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["hasNamespace"]
    assert out["schemaVersion"] == 1
    assert out["hasInit"]
    assert out["hasCreate"]
    assert out["hasTierDefs"]
    assert out["tierDefsLength"] == 7
    assert out["hasTierIndex"]
    assert out["hasTierAt"]
    assert out["hasLegendFor"]
    assert out["hasZoomBtn"]


def test_runtime_tier_helpers_work():
    setup = _setup_prelude() + r"""
        var N = window.M3MapNavigator;
        result = {
            idxOf1a:       N.tierIndex('1a'),
            idxOfMissing:  N.tierIndex('XXX'),
            tierAt0:       N.tierAt(0).id,
            tierAtClamped: N.tierAt(99).id,  // clamped to last
            tierAtNeg:     N.tierAt(-5).id,  // clamped to first
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["idxOf1a"] == 4
    assert out["idxOfMissing"] == -1
    assert out["tierAt0"] == "4c"
    assert out["tierAtClamped"] == "1b"   # last entry
    assert out["tierAtNeg"] == "4c"       # first entry


def test_runtime_create_returns_handle_with_documented_methods():
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);
        result = {
            hasElement:        !!handle.element,
            elementTag:        handle.element.tagName,
            elementHasMarker:  handle.element.hasAttribute('data-map-navigator'),
            hasJumpTo:         typeof handle.jumpTo === 'function',
            hasGetState:       typeof handle.getState === 'function',
            hasDestroy:        typeof handle.destroy === 'function',
            hasCloseHolocron:  typeof handle.closeHolocron === 'function',
            initialState:      handle.getState(),
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["hasElement"]
    assert out["elementTag"] == "DIV"
    assert out["elementHasMarker"]
    assert out["hasJumpTo"]
    assert out["hasGetState"]
    assert out["hasDestroy"]
    assert out["hasCloseHolocron"]
    # Default state
    assert out["initialState"]["tier"] == "1a"
    assert out["initialState"]["zoom"] == 1
    assert out["initialState"]["phase"] == "idle"
    assert out["initialState"]["holocronOpen"] is False


def test_runtime_initial_render_has_chrome_and_body():
    """The initial DOM has the top bar with status line + crumbs, a
    stage with zoom-wrap, the legend bar at bottom, the holocron button
    and tier overlay."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);
        document.body.appendChild(handle.element);
        var el = handle.element;
        result = {
            hasHolocarta: el.textContent.indexOf('HOLOCARTA') !== -1,
            hasLiveTag:   el.textContent.indexOf('LIVE') !== -1,
            hasZoomHint:  el.textContent.indexOf('SCROLL TO ZOOM') !== -1,
            // Crumbs render with all 7 ids
            crumbRowCount: el.querySelectorAll('[data-crumb-id]').length,
            hasStage:     !!el.querySelector('[data-stage]'),
            hasZoomWrap:  !!el.querySelector('[data-zoom-wrap]'),
            hasLegendRow: !!el.querySelector('[data-legend-row]'),
            hasHolocronBtn: !!el.querySelector('[data-holocron-btn]'),
            hasTierOverlay: !!el.querySelector('[data-tier-overlay]'),
            // SPACEPORT (1a) label is visible since 1a is the default tier
            hasSpaceportLabel: el.textContent.indexOf('SPACEPORT') !== -1,
            // Default tier-body placeholder renders
            hasDefaultTierBody: !!el.querySelector('[data-default-tier-body]'),
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["hasHolocarta"]
    assert out["hasLiveTag"]
    assert out["hasZoomHint"]
    assert out["crumbRowCount"] == 7
    assert out["hasStage"]
    assert out["hasZoomWrap"]
    assert out["hasLegendRow"]
    assert out["hasHolocronBtn"]
    assert out["hasTierOverlay"]
    assert out["hasSpaceportLabel"]
    assert out["hasDefaultTierBody"]


def test_runtime_active_crumb_highlighted():
    """The crumb for the active tier has stronger styling (amber bg)
    than the passed/inactive crumbs."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);
        var el = handle.element;
        document.body.appendChild(el);
        var crumbs = el.querySelectorAll('[data-crumb-id]');
        var byId = {};
        for (var i = 0; i < crumbs.length; i++) {
            byId[crumbs[i].getAttribute('data-crumb-id')] = crumbs[i];
        }
        result = {
            active1aFontWeight: byId['1a'].style.fontWeight,
            // Passed crumb (deeper in the ladder than current 1a)
            // doesn't exist before 1a — 4c/4a/3/2 are PASSED.
            passed4cFontWeight: byId['4c'].style.fontWeight,
            // Tier 0 (deeper than 1a) — inactive, not passed.
            inactive0FontWeight: byId['0'].style.fontWeight,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["active1aFontWeight"] == "700"
    assert out["passed4cFontWeight"] == "500"  # non-bold passed
    assert out["inactive0FontWeight"] == "500"


def test_runtime_jumpTo_changes_state_after_fade():
    """jumpTo triggers the fade-out → swap → fade-in sequence. With
    sync transitionDelays, state.tier reflects the new tier and crumbs
    re-render immediately."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p, {
            transitionDelays: { fadeOutMs: 0, fadeInMs: 0 }
        });
        document.body.appendChild(handle.element);
        var initial = handle.getState();
        handle.jumpTo('0');
        var after = handle.getState();
        var el = handle.element;
        result = {
            initialTier: initial.tier,
            finalTier: after.tier,
            finalPhase: after.phase,
            hasCantinaLabel: el.textContent.indexOf("CHALMUN'S") !== -1,
            defaultBodyTier: (function() {
                var b = el.querySelector('[data-default-tier-body]');
                return b && b.getAttribute('data-default-tier-body');
            })(),
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["initialTier"] == "1a"
    assert out["finalTier"] == "0"
    assert out["finalPhase"] == "idle"
    assert out["hasCantinaLabel"]
    assert out["defaultBodyTier"] == "0"


def test_runtime_jumpTo_no_op_when_already_on_tier():
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);
        var before = handle.getState();
        handle.jumpTo('1a');  // already on '1a'
        var after = handle.getState();
        result = {
            beforeTier: before.tier,
            afterTier:  after.tier,
            // Phase remained 'idle' — no transition started
            afterPhase: after.phase,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["beforeTier"] == "1a"
    assert out["afterTier"] == "1a"
    assert out["afterPhase"] == "idle"


def test_runtime_crumb_click_triggers_jumpTo():
    """Clicking a crumb dispatches jumpTo — verified with sync delays."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p, {
            transitionDelays: { fadeOutMs: 0, fadeInMs: 0 }
        });
        document.body.appendChild(handle.element);
        var crumb3 = handle.element.querySelector('[data-crumb-id="3"]');
        crumb3.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = {
            finalTier: handle.getState().tier,
            finalPhase: handle.getState().phase,
            hasTatooineLabel: handle.element.textContent.indexOf('TATOOINE') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["finalTier"] == "3"
    assert out["finalPhase"] == "idle"
    assert out["hasTatooineLabel"]


def test_runtime_jumpTo_phase_mid_flight():
    """With default (non-zero) transitionDelays, immediately after
    jumpTo the phase is 'fade-out' (not yet swapped)."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);  // default 180/160 delays
        document.body.appendChild(handle.element);
        handle.jumpTo('0');
        var mid = handle.getState();
        result = {
            midPhase: mid.phase,
            // Tier hasn't changed yet (still 1a until fadeOutMs elapses)
            midTier: mid.tier,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["midPhase"] == "fade-out"
    assert out["midTier"] == "1a"


def test_runtime_holocron_button_opens_modal():
    """Holocron button click calls hooks.onHolocronOpen and (if
    M3Holocron is available) renders a modal inside the container."""
    setup = _setup_prelude() + r"""
        var opened = false;
        var closedCalled = false;
        // Stub holocron modal builder — just returns a marker div.
        var handle = window.M3MapNavigator.create(p, {
            onHolocronOpen: function() { opened = true; },
            onHolocronClose: function() { closedCalled = true; },
            holocronModalBuilder: function(p, hooks) {
                var el = document.createElement('div');
                el.setAttribute('data-stub-holocron-modal', '1');
                el.addEventListener('click', hooks.onClose);
                return el;
            }
        });
        document.body.appendChild(handle.element);
        var btn = handle.element.querySelector('[data-holocron-btn]');
        btn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        var afterOpen = handle.getState();
        var hasModal = !!handle.element.querySelector('[data-stub-holocron-modal]');
        // Now close via handle.closeHolocron
        handle.closeHolocron();
        var afterClose = handle.getState();
        result = {
            opened: opened,
            holocronOpen: afterOpen.holocronOpen,
            hasModal: hasModal,
            closedCalled: closedCalled,
            stillOpen: afterClose.holocronOpen,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["opened"]
    assert out["holocronOpen"]
    assert out["hasModal"]
    assert out["closedCalled"]
    assert out["stillOpen"] is False


def test_runtime_custom_tier_renderer_called():
    """hooks.getTierRenderer is called when rendering the tier body.
    The renderer's return value becomes the zoom-wrap's content."""
    setup = _setup_prelude() + r"""
        var callsReceived = [];
        var customRenderer = function(tierId, args) {
            callsReceived.push({
                tierId: tierId,
                hasP: !!args.p,
                width: args.width,
                height: args.height,
            });
            var div = document.createElement('div');
            div.setAttribute('data-custom-renderer', tierId);
            div.textContent = 'CUSTOM ' + tierId;
            return div;
        };
        var handle = window.M3MapNavigator.create(p, {
            getTierRenderer: customRenderer,
            startTier: '3',  // tier 3 from boot
        });
        document.body.appendChild(handle.element);
        result = {
            callsReceived: callsReceived,
            hasCustomBody: !!handle.element.querySelector('[data-custom-renderer="3"]'),
            customBodyText: (function() {
                var b = handle.element.querySelector('[data-custom-renderer]');
                return b && b.textContent;
            })(),
            // The default placeholder must NOT render.
            hasDefaultBody: !!handle.element.querySelector('[data-default-tier-body]'),
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert len(out["callsReceived"]) == 1
    call = out["callsReceived"][0]
    assert call["tierId"] == "3"
    assert call["hasP"]
    assert call["width"] == 1280
    assert call["height"] == 832  # 920 - 60 (TOP) - 28 (BOTTOM)
    assert out["hasCustomBody"]
    assert out["customBodyText"] == "CUSTOM 3"
    assert out["hasDefaultBody"] is False


def test_runtime_wheel_handler_zooms():
    """Wheel event on the stage updates state.zoom and the zoom-HUD label."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);
        document.body.appendChild(handle.element);
        var stage = handle.element.querySelector('[data-stage]');
        // Dispatch a wheel event with deltaY = -100 (scroll up = zoom in)
        var ev = new window.WheelEvent('wheel', {
            deltaY: -100, bubbles: true, cancelable: true,
        });
        stage.dispatchEvent(ev);
        var after = handle.getState();
        result = {
            initialZoom: 1,
            afterZoom: after.zoom,
            // Zoom increased (deltaY negative = scroll up = zoom in)
            zoomedIn: after.zoom > 1,
            // Phase still idle (didn't cross tier threshold)
            phase: after.phase,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["zoomedIn"]
    assert out["phase"] == "idle"


def test_runtime_destroy_removes_wheel_handler():
    """After destroy(), wheel events on the stage no longer update state."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);
        document.body.appendChild(handle.element);
        var stage = handle.element.querySelector('[data-stage]');
        // First wheel — should zoom
        stage.dispatchEvent(new window.WheelEvent('wheel', {
            deltaY: -100, bubbles: true, cancelable: true,
        }));
        var zoomAfterFirst = handle.getState().zoom;
        // Now destroy
        handle.destroy();
        // Second wheel — should be no-op since handler removed
        stage.dispatchEvent(new window.WheelEvent('wheel', {
            deltaY: -500, bubbles: true, cancelable: true,
        }));
        var zoomAfterDestroy = handle.getState().zoom;
        result = {
            zoomAfterFirst: zoomAfterFirst,
            zoomAfterDestroy: zoomAfterDestroy,
            // Should be unchanged (handler removed)
            unchanged: zoomAfterDestroy === zoomAfterFirst,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["zoomAfterFirst"] > 1
    assert out["unchanged"], (
        f"Wheel handler still active after destroy: "
        f"{out['zoomAfterFirst']} → {out['zoomAfterDestroy']}"
    )


def test_runtime_default_tier_renderer_shows_placeholder():
    """When no getTierRenderer is supplied, the default placeholder
    renders 'TIER RENDERER NOT WIRED' text."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);
        document.body.appendChild(handle.element);
        var bodyEl = handle.element.querySelector('[data-default-tier-body]');
        result = {
            hasBody: !!bodyEl,
            bodyTier: bodyEl && bodyEl.getAttribute('data-default-tier-body'),
            hasNotWiredText: handle.element.textContent.indexOf('TIER RENDERER NOT WIRED') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["hasBody"]
    assert out["bodyTier"] == "1a"
    assert out["hasNotWiredText"]


def test_runtime_legend_changes_on_tier_change():
    """When the tier changes, the bottom legend bar refreshes to show
    the appropriate icons for that tier."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p, {
            transitionDelays: { fadeOutMs: 0, fadeInMs: 0 }
        });
        document.body.appendChild(handle.element);
        var legendBefore = handle.element.querySelector('[data-legend-row]').textContent;
        handle.jumpTo('4c');
        var legendAfter = handle.element.querySelector('[data-legend-row]').textContent;
        result = {
            legendBefore: legendBefore,
            legendAfter: legendAfter,
            beforeHadObjective: legendBefore.indexOf('OBJECTIVE') !== -1,
            afterHadRepublic: legendAfter.indexOf('REPUBLIC') !== -1,
            afterHadCis: legendAfter.indexOf('CIS') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["beforeHadObjective"]
    assert out["afterHadRepublic"]
    assert out["afterHadCis"]
    assert "OBJECTIVE" not in out["legendAfter"]


def test_runtime_startTier_option_respected():
    """hooks.startTier sets the initial tier."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p, { startTier: '2' });
        document.body.appendChild(handle.element);
        result = {
            tier: handle.getState().tier,
            // Active crumb is '2'
            activeCrumbWeight: handle.element.querySelector(
                '[data-crumb-id="2"]'
            ).style.fontWeight,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["tier"] == "2"
    assert out["activeCrumbWeight"] == "700"


def test_runtime_holocron_open_no_modal_builder_no_op():
    """If M3Holocron isn't available AND no holocronModalBuilder hook,
    clicking the holocron button still fires onHolocronOpen and toggles
    state, but no modal renders."""
    setup = _setup_prelude() + r"""
        // Save and clear window.M3Holocron temporarily
        var saved = window.M3Holocron;
        window.M3Holocron = undefined;
        try {
            var opened = false;
            var handle = window.M3MapNavigator.create(p, {
                onHolocronOpen: function() { opened = true; }
            });
            document.body.appendChild(handle.element);
            var btn = handle.element.querySelector('[data-holocron-btn]');
            btn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
            var modal = handle.element.querySelector('[data-stub-holocron-modal]');
            result = {
                opened: opened,
                stateOpen: handle.getState().holocronOpen,
                modalRendered: !!modal,
            };
        } finally {
            window.M3Holocron = saved;
        }
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    assert out["opened"]
    assert out["stateOpen"]
    assert out["modalRendered"] is False


def test_runtime_pointer_drag_pans():
    """Pointer down → move → up on the stage updates state.pan."""
    setup = _setup_prelude() + r"""
        var handle = window.M3MapNavigator.create(p);
        document.body.appendChild(handle.element);
        var stage = handle.element.querySelector('[data-stage]');
        // Dispatch pointer events with synthetic coordinates.
        function pointerEvent(type, x, y) {
            var ev = new window.PointerEvent(type, {
                bubbles: true, button: 0, pointerId: 1,
                clientX: x, clientY: y,
            });
            return ev;
        }
        stage.dispatchEvent(pointerEvent('pointerdown', 100, 100));
        stage.dispatchEvent(pointerEvent('pointermove', 150, 130));
        var midPan = handle.getState().pan;
        stage.dispatchEvent(pointerEvent('pointerup', 150, 130));
        var afterPan = handle.getState().pan;
        result = {
            midPanX: midPan.x,
            midPanY: midPan.y,
            // After pointerup, state.dragging should be null;
            // pan stays at the last position.
            afterPanX: afterPan.x,
            afterPanY: afterPan.y,
        };
    """
    out = run_with_dom(["static/spa/m3_map_navigator.js"], setup)
    # zoom=1, so dx = (150-100)/1 = 50, dy = (130-100)/1 = 30
    assert out["midPanX"] == 50
    assert out["midPanY"] == 30
    assert out["afterPanX"] == 50
    assert out["afterPanY"] == 30
