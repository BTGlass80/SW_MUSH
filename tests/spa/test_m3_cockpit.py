"""
test_m3_cockpit.py — Drop 4.9 regression lock for m3_cockpit.js.

Drop 4.9 ports map_v3/cockpit.jsx (623 JSX LOC) into a vanilla-JS
SPA module at static/spa/m3_cockpit.js. This file pins:

  · Module shape (IIFE + window.M3Cockpit + documented surface).
  · D6-accurate ship rendering (hull pips against hullDamage,
    fore/aft shield bars, binary OK/DMG system rows).
  · Clone-Wars-era fixtures (CIS Vulture Droid target, Geonosian
    signatures); no Empire/Imperial references in the fixtures.
  · CockpitActionStrip DI to M3CombatTheater.buildActionButton with
    local fallback when M3CombatTheater isn't loaded.
  · onActionClick / onSubmit hooks fire correctly.

Pattern parallels tests/spa/test_m3_holocron.py (Drop 4.7).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT       = Path(__file__).resolve().parent.parent.parent
COCKPIT_MODULE  = REPO_ROOT / "static" / "spa" / "m3_cockpit.js"
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
    assert COCKPIT_MODULE.exists(), (
        f"Module missing at {COCKPIT_MODULE}. Drop 4.9 either didn't "
        "ship or was reverted."
    )


def test_module_is_iife():
    src = COCKPIT_MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src
    assert "})();" in src


def test_module_exports_namespace():
    src = COCKPIT_MODULE.read_text(encoding="utf-8")
    assert "window.M3Cockpit" in src


def test_module_defines_all_documented_builders():
    src = COCKPIT_MODULE.read_text(encoding="utf-8")
    builders = [
        "buildCockpitView",
        "buildShipInstruments",
        "buildTacticalRadar",
        "buildCockpitFeedRow",
        "buildTargetLockPanel",
        "buildHyperspacePlot",
        "buildCrewPanel",
        "buildCockpitActionStrip",
        "buildLabel",
    ]
    for b in builders:
        assert "function " + b in src, f"Missing function definition: {b}"
        assert re.search(r"\b" + b + r"\s*:\s*" + b + r"\b", src), (
            f"Missing export entry for {b} in window.M3Cockpit"
        )


def test_init_function_present_and_exported():
    src = COCKPIT_MODULE.read_text(encoding="utf-8")
    assert "function init(" in src
    assert re.search(r"init\s*:\s*init\b", src)


def test_client_html_loads_module_and_calls_init():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert '/static/spa/m3_cockpit.js' in src
    assert "M3Cockpit.init(" in src


# ════════════════════════════════════════════════════════════════════
# Fixture contracts — Clone-Wars-era cleanness
# ════════════════════════════════════════════════════════════════════

def _extract_block(src: str, start_marker: str, end_marker: str) -> str:
    i = src.find(start_marker)
    if i < 0:
        return ""
    # Find the first { or [ after the start marker.
    open_brace = -1
    for j in range(i, len(src)):
        if src[j] in "{[":
            open_brace = j
            opener = src[j]
            closer = "}" if opener == "{" else "]"
            break
    if open_brace < 0:
        return ""
    depth = 0
    j = open_brace
    while j < len(src):
        ch = src[j]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return src[open_brace:j+1]
        j += 1
    return ""


def test_ship_fixture_is_rusty_mynock():
    """COCKPIT_SHIP_FIXTURE is the Rusty Mynock, YT-1300 Starfighter
    Scale, 4D hull, 12 pips, 3 damage, light damage condition."""
    src = COCKPIT_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var COCKPIT_SHIP_FIXTURE = {", "};")
    assert fixture, "COCKPIT_SHIP_FIXTURE not found"
    assert "RUSTY MYNOCK" in fixture
    assert "YT-1300" in fixture
    assert "Starfighter Scale" in fixture
    assert "hullDice: '4D'" in fixture
    assert "hullPips: 12" in fixture
    assert "hullDamage: 3" in fixture
    assert "LIGHT DAMAGE" in fixture


def test_target_fixture_clone_wars_era():
    """COCKPIT_TARGET_FIXTURE is the Vulture Droid (CIS · Hostile),
    not an Imperial TIE."""
    src = COCKPIT_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var COCKPIT_TARGET_FIXTURE = {", "};")
    assert fixture
    assert "CIS-V1" in fixture
    assert "Vulture Droid" in fixture
    assert "CIS · Hostile" in fixture
    # No Empire/Imperial in the target.
    assert "Empire" not in fixture
    assert "Imperial" not in fixture


def test_feed_fixture_clone_wars_era():
    """COCKPIT_FEED_FIXTURE references Geonosian signatures (CW-era).
    Negative control: no Empire/Imperial references."""
    src = COCKPIT_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var COCKPIT_FEED_FIXTURE = [", "];")
    assert fixture
    assert "Geonosian" in fixture
    assert "Tatooine" in fixture
    assert "vulture droid" in fixture
    # No Galactic Empire framing.
    assert "Empire" not in fixture
    assert "Imperial" not in fixture


def test_action_defaults_phase_declaration():
    """The default action-strip state is in DECLARATION phase with
    8 action chips: fire / dodge / evade / aim / shields / jam /
    jump / flee."""
    src = COCKPIT_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var COCKPIT_ACTION_DEFAULT = {", "};")
    assert fixture
    assert "phase: 'DECLARATION'" in fixture
    for action_id in ["'fire'", "'dodge'", "'evade'", "'aim'",
                       "'shields'", "'jam'", "'jump'", "'flee'"]:
        assert "id: " + action_id in fixture, (
            f"Missing action id: {action_id}"
        )


# ════════════════════════════════════════════════════════════════════
# Runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var C = window.M3Cockpit;
        result = {
            hasNamespace:    !!C,
            schemaVersion:   C && C.SCHEMA_VERSION,
            hasInit:         typeof C.init === 'function',
            hasBuildView:    typeof C.buildCockpitView === 'function',
            hasInstruments:  typeof C.buildShipInstruments === 'function',
            hasRadar:        typeof C.buildTacticalRadar === 'function',
            hasFeedRow:      typeof C.buildCockpitFeedRow === 'function',
            hasTargetPanel:  typeof C.buildTargetLockPanel === 'function',
            hasHyperspace:   typeof C.buildHyperspacePlot === 'function',
            hasCrewPanel:    typeof C.buildCrewPanel === 'function',
            hasActionStrip:  typeof C.buildCockpitActionStrip === 'function',
            hasShipFixture:  !!C.COCKPIT_SHIP_FIXTURE,
            hasTargetFixture:!!C.COCKPIT_TARGET_FIXTURE,
            hasFeedFixture:  Array.isArray(C.COCKPIT_FEED_FIXTURE),
            shipName:        C.COCKPIT_SHIP_FIXTURE.name,
            targetId:        C.COCKPIT_TARGET_FIXTURE.id,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["hasNamespace"]
    assert out["schemaVersion"] == 1
    assert out["hasInit"]
    assert out["hasBuildView"]
    assert out["hasInstruments"]
    assert out["hasRadar"]
    assert out["hasFeedRow"]
    assert out["hasTargetPanel"]
    assert out["hasHyperspace"]
    assert out["hasCrewPanel"]
    assert out["hasActionStrip"]
    assert out["hasShipFixture"]
    assert out["hasTargetFixture"]
    assert out["hasFeedFixture"]
    assert out["shipName"] == "RUSTY MYNOCK"
    assert out["targetId"] == "CIS-V1"


def test_runtime_buildCockpitView_renders_full_layout():
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildCockpitView(p);
        document.body.appendChild(el);
        result = {
            tag: el.tagName,
            isView: el.hasAttribute('data-cockpit-view'),
            hasLeft:   !!el.querySelector('[data-cockpit-left]'),
            hasCenter: !!el.querySelector('[data-cockpit-center]'),
            hasRight:  !!el.querySelector('[data-cockpit-right]'),
            hasRadar:  !!el.querySelector('[data-cockpit-radar]'),
            hasFeed:   !!el.querySelector('[data-cockpit-feed]'),
            hasTarget: !!el.querySelector('[data-cockpit-target]'),
            hasHyper:  !!el.querySelector('[data-cockpit-hyperspace]'),
            hasCrew:   !!el.querySelector('[data-cockpit-crew]'),
            hasStrip:  !!el.querySelector('[data-cockpit-action-strip]'),
            // Top bar mentions cockpit
            hasCockpitHeader: el.textContent.indexOf('COCKPIT · FLIGHT CONSOLE') !== -1,
            // Ship name appears in header
            hasShipName: el.textContent.indexOf('RUSTY MYNOCK') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["tag"] == "DIV"
    assert out["isView"]
    assert out["hasLeft"]
    assert out["hasCenter"]
    assert out["hasRight"]
    assert out["hasRadar"]
    assert out["hasFeed"]
    assert out["hasTarget"]
    assert out["hasHyper"]
    assert out["hasCrew"]
    assert out["hasStrip"]
    assert out["hasCockpitHeader"]
    assert out["hasShipName"]


def test_runtime_ship_instruments_renders_12_hull_pips():
    """D6-accurate: 12 hull pips total, 9 OK + 3 damaged (RUSTY MYNOCK
    has hullDamage=3, hullPips=12)."""
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildShipInstruments(p,
                window.M3Cockpit.COCKPIT_SHIP_FIXTURE);
        document.body.appendChild(el);
        var pips = el.querySelectorAll('[data-hull-pip-index]');
        var states = Array.prototype.map.call(pips, function(p) {
            return p.getAttribute('data-hull-pip-state');
        });
        var okCount = states.filter(function(s) { return s === 'ok'; }).length;
        var damagedCount = states.filter(function(s) { return s === 'damaged'; }).length;
        result = {
            pipCount: pips.length,
            okCount: okCount,
            damagedCount: damagedCount,
            hasLightDamage: el.textContent.indexOf('LIGHT DAMAGE') !== -1,
            hasFore: !!el.querySelector('[data-shield-arc="FORE"]'),
            hasAft:  !!el.querySelector('[data-shield-arc="AFT"]'),
            // SYSTEMS section
            hyperdriveSystemOk: el.querySelector('[data-system-name="HYPERDRIVE"]')
                                  .getAttribute('data-system-ok'),
            enginesSystemOk: el.querySelector('[data-system-name="ENGINES"]')
                              .getAttribute('data-system-ok'),
            hasHullDamageText: el.textContent.indexOf('3/12 pips damage') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["pipCount"] == 12
    assert out["okCount"] == 9       # 12 - 3
    assert out["damagedCount"] == 3
    assert out["hasLightDamage"]
    assert out["hasFore"]
    assert out["hasAft"]
    # Hyperdrive is damaged in the fixture
    assert out["hyperdriveSystemOk"] == "false"
    assert out["enginesSystemOk"] == "true"
    assert out["hasHullDamageText"]


def test_runtime_tactical_radar_renders_markers():
    """Tactical radar SVG renders YOU + MAREK + CIS-V1 (locked) + CIS-V2
    + GEONO-1 markers."""
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildTacticalRadar(p);
        document.body.appendChild(el);
        var markers = el.querySelectorAll('[data-radar-marker]');
        var ids = Array.prototype.map.call(markers, function(m) {
            return m.getAttribute('data-radar-marker');
        });
        result = {
            markerCount: markers.length,
            ids: ids,
            // HUD overlays
            hasTacticalLabel: el.textContent.indexOf('TACTICAL · 40K RANGE') !== -1,
            hasBearing: el.textContent.indexOf('BEARING') !== -1,
            hasSublight: el.textContent.indexOf('SUBLIGHT') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["markerCount"] == 5
    assert set(out["ids"]) == {"you", "marek", "cis-v1", "cis-v2", "geono-1"}
    assert out["hasTacticalLabel"]
    assert out["hasBearing"]
    assert out["hasSublight"]


def test_runtime_feed_row_pose():
    setup = _setup_prelude() + r"""
        var entry = {
            kind: 'pose', actor: 'TEY VOSS', verb: 'poses', side: 'self',
            time: '0:48', text: 'rolls the Mynock hard to port.'
        };
        var el = window.M3Cockpit.buildCockpitFeedRow(p, entry);
        document.body.appendChild(el);
        result = {
            kind: el.getAttribute('data-feed-kind'),
            side: el.getAttribute('data-feed-side'),
            hasActor: el.textContent.indexOf('TEY VOSS') !== -1,
            hasVerb: el.textContent.indexOf('poses') !== -1,
            hasTime: el.textContent.indexOf('0:48') !== -1,
            hasText: el.textContent.indexOf('rolls the Mynock hard to port') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["kind"] == "pose"
    assert out["side"] == "self"
    assert out["hasActor"]
    assert out["hasVerb"]
    assert out["hasTime"]
    assert out["hasText"]


def test_runtime_feed_row_comms_ally():
    setup = _setup_prelude() + r"""
        var entry = {
            kind: 'comms', sender: 'MAREK · COM 4', tone: 'ally',
            text: '"Two more bandits — Geonosian signatures."'
        };
        var el = window.M3Cockpit.buildCockpitFeedRow(p, entry);
        document.body.appendChild(el);
        result = {
            kind: el.getAttribute('data-feed-kind'),
            hasComms: el.textContent.indexOf('COMMS · MAREK · COM 4') !== -1,
            hasGeonosianRef: el.textContent.indexOf('Geonosian signatures') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["kind"] == "comms"
    assert out["hasComms"]
    assert out["hasGeonosianRef"]


def test_runtime_feed_row_sys_event_tones():
    setup = _setup_prelude() + r"""
        var redEvent = { kind: 'sys-event', tone: 'red',
                         text: 'Proximity warning.' };
        var greenEvent = { kind: 'sys-event', tone: 'green',
                            text: 'Target lock acquired.' };
        var redEl = window.M3Cockpit.buildCockpitFeedRow(p, redEvent);
        var greenEl = window.M3Cockpit.buildCockpitFeedRow(p, greenEvent);
        result = {
            redTone: redEl.getAttribute('data-feed-tone'),
            greenTone: greenEl.getAttribute('data-feed-tone'),
            redHasWarn: redEl.textContent.indexOf('⚠') !== -1,
            greenHasCheck: greenEl.textContent.indexOf('✓') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["redTone"] == "red"
    assert out["greenTone"] == "green"
    assert out["redHasWarn"]
    assert out["greenHasCheck"]


def test_runtime_target_lock_panel_renders_stats():
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildTargetLockPanel(p,
                window.M3Cockpit.COCKPIT_TARGET_FIXTURE);
        document.body.appendChild(el);
        var stats = el.querySelectorAll('[data-target-stat]');
        var keys = Array.prototype.map.call(stats, function(s) {
            return s.getAttribute('data-target-stat');
        });
        result = {
            statKeys: keys,
            hasCisV1: el.textContent.indexOf('CIS-V1') !== -1,
            hasVultureDroid: el.textContent.indexOf('Vulture Droid') !== -1,
            hasLocked: el.textContent.indexOf('LOCKED') !== -1,
            hasRange: el.textContent.indexOf('14.2K') !== -1,
            hasBearing: el.textContent.indexOf('305°') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert set(out["statKeys"]) == {"RANGE", "BRG", "HULL", "SHLD"}
    assert out["hasCisV1"]
    assert out["hasVultureDroid"]
    assert out["hasLocked"]
    assert out["hasRange"]
    assert out["hasBearing"]


def test_runtime_hyperspace_plot_renders_progress():
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildHyperspacePlot(p,
                  'ANCHORHEAD → KESSEL', 62, 12);
        document.body.appendChild(el);
        var fill = el.querySelector('[data-hyperspace-fill]');
        result = {
            hasFill: !!fill,
            fillWidth: fill && fill.style.width,
            hasDest: el.textContent.indexOf('ANCHORHEAD → KESSEL') !== -1,
            hasPct: el.textContent.indexOf('62%') !== -1,
            hasBackupWarning: el.textContent.indexOf('HYPERDRIVE DAMAGED') !== -1,
            hasBackupMultiplier: el.textContent.indexOf('×12') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["hasFill"]
    assert out["fillWidth"] == "62%"
    assert out["hasDest"]
    assert out["hasPct"]
    assert out["hasBackupWarning"]
    assert out["hasBackupMultiplier"]


def test_runtime_hyperspace_plot_no_backup_when_omitted():
    """If backupDriveMultiplier is null, the 'HYPERDRIVE DAMAGED' line
    doesn't render."""
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildHyperspacePlot(p, 'DEST', 80, null);
        document.body.appendChild(el);
        result = {
            hasBackupWarning: el.textContent.indexOf('HYPERDRIVE DAMAGED') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["hasBackupWarning"] is False


def test_runtime_crew_panel_default_renders_four_stations():
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildCrewPanel(p);
        document.body.appendChild(el);
        var rows = el.querySelectorAll('[data-crew-role]');
        var roles = Array.prototype.map.call(rows, function(r) {
            return r.getAttribute('data-crew-role');
        });
        result = {
            roles: roles,
            count: rows.length,
            hasTeyVoss: el.textContent.indexOf('Tey Voss') !== -1,
            hasK3S0: el.textContent.indexOf('K3-S0 (AI)') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["count"] == 4
    assert out["roles"] == ["PILOT", "CO-PILOT", "GUNNER", "ENGINEER"]
    assert out["hasTeyVoss"]
    assert out["hasK3S0"]


def test_runtime_crew_panel_accepts_custom_crew():
    setup = _setup_prelude() + r"""
        var custom = [
            { role: 'CAPTAIN', name: 'Han', color: p.green },
            { role: 'CO-PILOT', name: 'Chewie', color: p.amber },
        ];
        var el = window.M3Cockpit.buildCrewPanel(p, custom);
        document.body.appendChild(el);
        var rows = el.querySelectorAll('[data-crew-role]');
        var roles = Array.prototype.map.call(rows, function(r) {
            return r.getAttribute('data-crew-role');
        });
        result = {
            roles: roles,
            hasHan: el.textContent.indexOf('Han') !== -1,
            hasChewie: el.textContent.indexOf('Chewie') !== -1,
            // Default crew names should NOT appear when custom is supplied.
            noTeyVoss: el.textContent.indexOf('Tey Voss') === -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["roles"] == ["CAPTAIN", "CO-PILOT"]
    assert out["hasHan"]
    assert out["hasChewie"]
    assert out["noTeyVoss"]


def test_runtime_action_strip_default_state_renders_8_actions():
    """The default action strip renders 8 action buttons + a SUBMIT
    button + the DECLARED label + phase chip + round info."""
    setup = _setup_prelude() + r"""
        // Without M3CombatTheater loaded, fallback action buttons are used.
        var el = window.M3Cockpit.buildCockpitActionStrip(p);
        document.body.appendChild(el);
        var fallbackBtns = el.querySelectorAll('[data-fallback-action-btn]');
        var ids = Array.prototype.map.call(fallbackBtns, function(b) {
            return b.getAttribute('data-fallback-action-btn');
        });
        result = {
            actionCount: fallbackBtns.length,
            ids: ids,
            hasPhaseDeclaration: el.textContent.indexOf('PHASE · DECLARATION') !== -1,
            hasRoundFour: el.textContent.indexOf('ROUND 4') !== -1,
            hasWaitingOn: el.textContent.indexOf('you, marek, k3-s0') !== -1,
            hasDeclared: el.textContent.indexOf('DECLARED:') !== -1,
            hasSubmit: !!el.querySelector('[data-submit-btn]'),
            hasMapWarning: el.textContent.indexOf('MAP −1D') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["actionCount"] == 8
    assert out["ids"] == ["fire", "dodge", "evade", "aim", "shields",
                          "jam", "jump", "flee"]
    assert out["hasPhaseDeclaration"]
    assert out["hasRoundFour"]
    assert out["hasWaitingOn"]
    assert out["hasDeclared"]
    assert out["hasSubmit"]
    assert out["hasMapWarning"]


def test_runtime_action_strip_uses_combat_theater_when_available():
    """When M3CombatTheater is loaded, buildCockpitActionStrip uses
    M3CombatTheater.buildActionButton instead of the local fallback."""
    setup = _setup_prelude() + r"""
        // Stub M3CombatTheater with a buildActionButton that marks output.
        window.M3CombatTheater = {
            buildActionButton: function(p, action, hasMap, onClick) {
                var b = document.createElement('button');
                b.setAttribute('data-theater-action-btn', action.id);
                b.textContent = action.label;
                if (typeof onClick === 'function') {
                    b.addEventListener('click', onClick);
                }
                return b;
            }
        };
        var el = window.M3Cockpit.buildCockpitActionStrip(p);
        document.body.appendChild(el);
        var theaterBtns = el.querySelectorAll('[data-theater-action-btn]');
        var fallbackBtns = el.querySelectorAll('[data-fallback-action-btn]');
        result = {
            theaterBtnCount: theaterBtns.length,
            fallbackBtnCount: fallbackBtns.length,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["theaterBtnCount"] == 8, (
        "When M3CombatTheater is loaded, action chips should use its builder"
    )
    assert out["fallbackBtnCount"] == 0, (
        "Local fallback should not be invoked when M3CombatTheater is present"
    )


def test_runtime_action_click_hook_fires():
    """The onActionClick hook fires with the action.id when an enabled
    action chip is clicked."""
    setup = _setup_prelude() + r"""
        var clicked = null;
        var el = window.M3Cockpit.buildCockpitActionStrip(p, {
            onActionClick: function(id) { clicked = id; }
        });
        document.body.appendChild(el);
        var fireBtn = el.querySelector('[data-fallback-action-btn="fire"]');
        fireBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { clickedAction: clicked };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["clickedAction"] == "fire"


def test_runtime_action_click_disabled_does_not_fire():
    """Disabled actions (jam / jump in default state) don't fire onClick."""
    setup = _setup_prelude() + r"""
        var clicked = null;
        var el = window.M3Cockpit.buildCockpitActionStrip(p, {
            onActionClick: function(id) { clicked = id; }
        });
        document.body.appendChild(el);
        var jamBtn = el.querySelector('[data-fallback-action-btn="jam"]');
        jamBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = {
            clicked: clicked,
            jamButtonOpacity: jamBtn.style.opacity,
            jamButtonCursor: jamBtn.style.cursor,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["clicked"] is None
    # Disabled buttons have reduced opacity + not-allowed cursor.
    assert float(out["jamButtonOpacity"]) < 1.0
    assert out["jamButtonCursor"] == "not-allowed"


def test_runtime_submit_hook_fires():
    setup = _setup_prelude() + r"""
        var submitted = false;
        var el = window.M3Cockpit.buildCockpitActionStrip(p, {
            onSubmit: function() { submitted = true; }
        });
        document.body.appendChild(el);
        var submitBtn = el.querySelector('[data-submit-btn]');
        submitBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { submitted: submitted };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["submitted"]


def test_runtime_custom_action_state():
    """A custom actionStripState passes through to the strip."""
    setup = _setup_prelude() + r"""
        var state = {
            phase: 'RESOLUTION', round: 7, waitingOn: 'tey, k3-s0',
            declared: 'FIRE × DODGE',
            actions: [
                { id: 'reload', label: 'RELOAD', icon: '⟲', enabled: true, cost: '1 action' },
                { id: 'pose',   label: 'POSE',   icon: '✎', enabled: true, cost: '—' },
            ],
        };
        var el = window.M3Cockpit.buildCockpitActionStrip(p, {
            actionStripState: state
        });
        document.body.appendChild(el);
        var btns = el.querySelectorAll('[data-fallback-action-btn]');
        result = {
            btnCount: btns.length,
            hasResolutionPhase: el.textContent.indexOf('PHASE · RESOLUTION') !== -1,
            hasRound7: el.textContent.indexOf('ROUND 7') !== -1,
            hasCustomDeclared: el.textContent.indexOf('FIRE × DODGE') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["btnCount"] == 2
    assert out["hasResolutionPhase"]
    assert out["hasRound7"]
    assert out["hasCustomDeclared"]


def test_runtime_cockpit_view_feed_renders_six_rows():
    """The default feed fixture has 6 entries; the rendered feed should
    contain 6 rows."""
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildCockpitView(p);
        document.body.appendChild(el);
        var feedEl = el.querySelector('[data-cockpit-feed]');
        var rows = feedEl.querySelectorAll('[data-feed-kind]');
        var kinds = Array.prototype.map.call(rows, function(r) {
            return r.getAttribute('data-feed-kind');
        });
        result = {
            rowCount: rows.length,
            kinds: kinds,
            // CIS-V1 target id appears in the radar + target + feed sys-event
            hasCisV1: el.textContent.indexOf('CIS-V1') !== -1,
            // The system-event 'Sublight engaged' appears at the top
            hasSublightEngaged: el.textContent.indexOf('Sublight engaged') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["rowCount"] == 6
    # Expected feed mix: system-event / pose / comms / sys-event / pose / sys-event
    assert out["kinds"] == [
        "system-event", "pose", "comms", "sys-event", "pose", "sys-event"
    ]
    assert out["hasCisV1"]
    assert out["hasSublightEngaged"]


def test_runtime_ship_no_damaged_systems_when_all_ok():
    """A ship with all systems OK shouldn't render any DMG markers."""
    setup = _setup_prelude() + r"""
        var allOkShip = Object.assign({}, window.M3Cockpit.COCKPIT_SHIP_FIXTURE, {
            systems: [
                { name: 'ENGINES', ok: true },
                { name: 'WEAPONS', ok: true },
                { name: 'SHIELDS', ok: true },
                { name: 'HYPERDRIVE', ok: true },
                { name: 'SENSORS', ok: true },
            ],
        });
        var el = window.M3Cockpit.buildShipInstruments(p, allOkShip);
        document.body.appendChild(el);
        var damaged = el.querySelectorAll('[data-system-ok="false"]');
        result = {
            damagedCount: damaged.length,
            // All five systems should be OK
            okCount: el.querySelectorAll('[data-system-ok="true"]').length,
            hasDmgText: el.textContent.indexOf('DMG') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["damagedCount"] == 0
    assert out["okCount"] == 5
    assert out["hasDmgText"] is False


def test_runtime_action_strip_disabled_actions_have_dimmed_styling():
    """Disabled actions in the default state (jam, jump) render with
    opacity < 1 and not-allowed cursor."""
    setup = _setup_prelude() + r"""
        var el = window.M3Cockpit.buildCockpitActionStrip(p);
        document.body.appendChild(el);
        var jamBtn = el.querySelector('[data-fallback-action-btn="jam"]');
        var fireBtn = el.querySelector('[data-fallback-action-btn="fire"]');
        result = {
            jamOpacity: jamBtn.style.opacity,
            jamCursor: jamBtn.style.cursor,
            fireOpacity: fireBtn.style.opacity,
            fireCursor: fireBtn.style.cursor,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert float(out["jamOpacity"]) < 1.0
    assert out["jamCursor"] == "not-allowed"
    assert float(out["fireOpacity"]) == 1.0
    assert out["fireCursor"] == "pointer"


def test_runtime_buildCockpitView_with_custom_ship():
    """Top-level cockpit accepts a custom ship via hooks.ship."""
    setup = _setup_prelude() + r"""
        var customShip = Object.assign({}, window.M3Cockpit.COCKPIT_SHIP_FIXTURE, {
            name: 'GHOST',
            class: 'VCX-100 · Light Freighter',
        });
        var el = window.M3Cockpit.buildCockpitView(p, { ship: customShip });
        document.body.appendChild(el);
        result = {
            hasGhost: el.textContent.indexOf('GHOST') !== -1,
            hasVCX: el.textContent.indexOf('VCX-100') !== -1,
            noRustyMynock: el.textContent.indexOf('RUSTY MYNOCK') === -1,
        };
    """
    out = run_with_dom(["static/spa/m3_cockpit.js"], setup)
    assert out["hasGhost"]
    assert out["hasVCX"]
    assert out["noRustyMynock"]
