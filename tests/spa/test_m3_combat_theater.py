"""
test_m3_combat_theater.py — Drop 4.5 regression lock for m3_combat_theater.js.

Drop 4.5 ports the HUD chrome (right rail + bottom action strip) from the
post-bug-fix-sprint combat-theater.jsx into a vanilla-JS SPA module at
static/spa/m3_combat_theater.js. This file pins:

  · Module loads cleanly under jsdom, exports window.M3CombatTheater
    with the documented surface.
  · Bug-fix-sprint corrections (B1/H1/H2/H3/M4) are preserved in the
    default fixture data.
  · Each renderer returns a DOM element with the expected structure.
  · The action-strip phase dispatcher (POSING / DECLARATION /
    RESOLUTION / INITIATIVE) builds the right body per phase.
  · Hooks (onPassPose, onActionClick, onSubmitDeclaration) fire when
    the relevant button is clicked.

Pattern parallels tests/spa/test_m3_*.py (4.1/4.2 series) — load the
module under jsdom, exercise its exported functions, inspect the
resulting DOM via .tagName / .textContent / .getAttribute() / classList.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT      = Path(__file__).resolve().parent.parent.parent
THEATER_MODULE = REPO_ROOT / "static" / "spa" / "m3_combat_theater.js"
CLIENT_HTML    = REPO_ROOT / "static" / "client.html"


# Minimal palette matching the JSX prototype's `p` arg. The actual
# palette keys come from map_v3/palettes.jsx; here we use the most
# common ones referenced by combat-theater.jsx.
SAMPLE_PALETTE = {
    "amber":     "#ffc857",
    "red":       "#ff5a4a",
    "green":     "#7ce068",
    "cyan":      "#7ce0d0",
    "ink":       "#d6cbb7",
    "inkBright": "#fff4d6",
    "inkDim":    "#a09584",
    "inkFaint":  "#6b6253",
    "sky":       "#2a2418",
    "skyDeep":   "#1a160c",
}


# ════════════════════════════════════════════════════════════════════
# Static module-shape checks (cheap; don't require node/jsdom)
# ════════════════════════════════════════════════════════════════════

def test_module_file_exists():
    """The Drop 4.5 module must exist at the documented path."""
    assert THEATER_MODULE.exists(), (
        f"Module missing at {THEATER_MODULE}. Drop 4.5 either didn't "
        "ship or was reverted."
    )


def test_module_is_iife():
    """SPA modules must be wrapped in an IIFE per /static/spa/README.md."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src, (
        "m3_combat_theater.js must be wrapped in an IIFE."
    )
    assert "})();" in src, "IIFE not closed at end of m3_combat_theater.js"


def test_module_exports_namespace():
    """Module must export window.M3CombatTheater per the SPA convention."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    assert "window.M3CombatTheater" in src, (
        "Module must export window.M3CombatTheater"
    )


def test_module_defines_all_documented_builders():
    """All builders listed in the module docstring must exist as
    functions and be exported."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    builders = [
        "buildInitiativeLadder",
        "buildTargetCard",
        "buildRollPreview",
        "buildShotContext",
        "buildYourStatus",
        "buildActionStrip",
        "buildPhaseBadge",
        "buildPoseTimer",
        "buildDeclarationBody",
        "buildPosingBody",
        "buildPassiveBody",
        "buildActionButton",
    ]
    for b in builders:
        assert "function " + b in src, (
            f"Missing function definition: {b}"
        )
        # Each must also be listed in the exports object — pattern
        # ` <name>: <name>,` (with optional whitespace).
        assert re.search(r"\b" + b + r"\s*:\s*" + b + r"\b", src), (
            f"Missing export entry for {b} in window.M3CombatTheater"
        )


def test_init_function_present_and_exported():
    """init() is the DI entry point that client.html calls."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    assert "function init(" in src, "Module must define init() for DI"
    assert re.search(r"init\s*:\s*init\b", src), (
        "Module must export init in window.M3CombatTheater"
    )


def test_client_html_loads_module_and_calls_init():
    """client.html must include the script tag AND call
    M3CombatTheater.init(). Without init, the module's helpers fall
    back to defaults — usable, but escapeHtml etc. won't match the
    host site's behavior."""
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert '/static/spa/m3_combat_theater.js' in src, (
        "client.html missing <script> tag for m3_combat_theater.js"
    )
    assert "M3CombatTheater.init(" in src, (
        "client.html doesn't call M3CombatTheater.init() — module helpers "
        "will fall back to defaults."
    )


# ════════════════════════════════════════════════════════════════════
# Bug-fix-sprint contract checks (B1 / H1 / H2 / H3 / M4)
# Tests that the module's default fixtures preserve the corrections
# from design_review_may24_v1.md.
# ════════════════════════════════════════════════════════════════════

def test_b1_pass_action_in_default_phase_info():
    """B1: `pass` must be a first-class action in
    availableNextDeclaration with cost 'hold action this round'."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    # Pattern: a pass action entry inside DEFAULT_PHASE_INFO.
    m = re.search(
        r"id:\s*'pass'[^}]*label:\s*'PASS'[^}]*cost:\s*'hold action this round'",
        src
    )
    assert m, (
        "B1 fix not preserved: pass action with 'hold action this round' "
        "cost label must be in DEFAULT_PHASE_INFO.availableNextDeclaration"
    )


def test_h1_map_label_disambiguated():
    """H1: MAP cost label rewritten to 'declare 2nd → both at −1D' for
    both dodge and move (or any action that triggers second-action MAP)."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    occurrences = src.count('declare 2nd → both at −1D')
    assert occurrences >= 2, (
        f"H1 fix not preserved: expected ≥2 'declare 2nd → both at −1D' "
        f"labels in DEFAULT_PHASE_INFO; got {occurrences}"
    )


def test_h2_aim_cost_label():
    """H2: AIM is an action, not 'free'; label reads '1 action · +1D
    next round'."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    assert "'1 action · +1D next round'" in src, (
        "H2 fix not preserved: AIM cost label must be "
        "'1 action · +1D next round' (was 'free · +1D next' pre-fix)"
    )
    # Negative control — make sure the old "free" framing didn't sneak back
    # in *as the aim cost label*. (We can't ban the word "free" entirely
    # because it might appear elsewhere; we just make sure the specific
    # legacy formulation isn't present.)
    assert "'free · +1D next'" not in src, (
        "H2 regression: legacy 'free · +1D next' label is back."
    )


def test_h3_cover_label_exposes_graded_tier():
    """H3: COVER button label exposes the graded tier
    ('already in 1/2 cover (+2D)')."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    assert "already in 1/2 cover (+2D)" in src, (
        "H3 fix not preserved: COVER label must read "
        "'already in 1/2 cover (+2D)' (was 'already in cover' pre-fix)"
    )


def test_m4_initiative_ladder_uses_perception_label():
    """M4: Initiative values are labeled 'init N' with a Perception-
    roll subtitle in the buildInitiativeLadder renderer."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    assert "'Perception roll · highest acts first'" in src, (
        "M4 fix not preserved: InitiativeLadder must have the "
        "'Perception roll · highest acts first' subtitle"
    )
    # The 'init {N}' literal — match via "'init ' +" prefix.
    assert re.search(r"'init '\s*\+\s*o\.init", src), (
        "M4 fix not preserved: init values must be rendered as "
        "'init {N}' via 'init ' + o.init"
    )


def test_action_count_includes_all_9_bug_fix_sprint_chips():
    """The bug-fix sprint added pass as the 9th action chip. Default
    fixture must include all 9 (attack/dodge/aim/cover/move/reload/
    fp/flee/pass)."""
    src = THEATER_MODULE.read_text(encoding="utf-8")
    ids = ['attack', 'dodge', 'aim', 'cover', 'move', 'reload', 'fp', 'flee', 'pass']
    for action_id in ids:
        assert "id: '" + action_id + "'" in src, (
            f"Action chip missing from default fixture: {action_id}"
        )


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests — load the module and exercise the renderers.
# These skip if node/jsdom isn't available (Brian's Windows dev box
# has both; the sandbox needs `npm install jsdom` in /tmp/node_modules).
# ════════════════════════════════════════════════════════════════════

from .spa_dom_harness import run_with_dom


def _setup_loads_palette():
    """Setup JS prelude: load the palette into a `p` global so the
    setup body can call M3CombatTheater builders directly."""
    return (
        "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"
    )


def test_runtime_module_loads_into_jsdom():
    """Module must load cleanly into jsdom and expose
    window.M3CombatTheater with all documented members."""
    setup = _setup_loads_palette() + r"""
        var T = window.M3CombatTheater;
        result = {
            hasNamespace:    !!T,
            schemaVersion:   T && T.SCHEMA_VERSION,
            hasInit:         typeof T.init === 'function',
            hasInitLadder:   typeof T.buildInitiativeLadder === 'function',
            hasTargetCard:   typeof T.buildTargetCard === 'function',
            hasRollPreview:  typeof T.buildRollPreview === 'function',
            hasShotContext:  typeof T.buildShotContext === 'function',
            hasYourStatus:   typeof T.buildYourStatus === 'function',
            hasActionStrip:  typeof T.buildActionStrip === 'function',
            hasActionButton: typeof T.buildActionButton === 'function',
            hasDefaultPhase: !!T.DEFAULT_PHASE_INFO,
            hasDefaultInit:  !!T.DEFAULT_INITIATIVE_ORDER,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["hasNamespace"]
    assert out["schemaVersion"] == 1
    assert out["hasInit"]
    assert out["hasInitLadder"]
    assert out["hasTargetCard"]
    assert out["hasRollPreview"]
    assert out["hasShotContext"]
    assert out["hasYourStatus"]
    assert out["hasActionStrip"]
    assert out["hasActionButton"]
    assert out["hasDefaultPhase"]
    assert out["hasDefaultInit"]


def test_runtime_initiative_ladder_renders_with_default_order():
    """buildInitiativeLadder(p) returns a DIV containing one row per
    combatant in DEFAULT_INITIATIVE_ORDER (4 rows)."""
    setup = _setup_loads_palette() + r"""
        var el = window.M3CombatTheater.buildInitiativeLadder(p);
        document.body.appendChild(el);
        // Each row has a grid layout — count by gridTemplateColumns marker.
        var rows = el.querySelectorAll('div[title*="Perception roll"]');
        result = {
            tag: el.tagName,
            rowCount: rows.length,
            firstName: rows[0].textContent.indexOf('TEY VOSS') !== -1,
            currentRowHasNow: el.textContent.indexOf('NOW') !== -1,
            structHasOut: el.textContent.indexOf('OUT') !== -1,
            subtitleText: el.children[1] && el.children[1].textContent,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["tag"] == "DIV"
    assert out["rowCount"] == 4, (
        f"Default initiative order has 4 entries; got {out['rowCount']} rows"
    )
    assert out["firstName"], "Tey Voss must appear in the first row"
    assert out["currentRowHasNow"], "Current actor row must show 'NOW' badge"
    assert out["structHasOut"], "Struck (disabled) actor must show 'OUT' badge"
    assert "Perception roll" in (out["subtitleText"] or ""), (
        "M4: subtitle 'Perception roll · highest acts first' must render"
    )


def test_runtime_target_card_renders_with_default_target():
    """buildTargetCard renders the B1 Battle Droid silhouette + status."""
    setup = _setup_loads_palette() + r"""
        var el = window.M3CombatTheater.buildTargetCard(p);
        document.body.appendChild(el);
        result = {
            tag: el.tagName,
            hasSvg: !!el.querySelector('svg'),
            hasName: el.textContent.indexOf('B1 BATTLE DROID #1') !== -1,
            hasStatus: el.textContent.indexOf('DISABLED') !== -1,
            hasSub: el.textContent.indexOf('Hostile') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["tag"] == "DIV"
    assert out["hasSvg"], "TargetCard must include an SVG silhouette"
    assert out["hasName"], "Target name must render"
    assert out["hasStatus"], "Target status must render"
    assert out["hasSub"], "Target sub-line must render"


def test_runtime_target_card_accepts_custom_target():
    """buildTargetCard(p, custom) overrides the default fixture."""
    setup = _setup_loads_palette() + r"""
        var custom = {
            name: 'SUPER BATTLE DROID',
            sub:  'CIS · Heavy · Infantry',
            status: 'WND 2/4',
            woundProgress: [true, true, false, false],
        };
        var el = window.M3CombatTheater.buildTargetCard(p, custom);
        document.body.appendChild(el);
        result = {
            hasCustomName: el.textContent.indexOf('SUPER BATTLE DROID') !== -1,
            hasCustomStatus: el.textContent.indexOf('WND 2/4') !== -1,
            // Default fixture's 'B1 BATTLE DROID #1' should NOT appear.
            noDefault: el.textContent.indexOf('B1 BATTLE DROID #1') === -1,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["hasCustomName"]
    assert out["hasCustomStatus"]
    assert out["noDefault"]


def test_runtime_action_button_b1_pass_renders():
    """B1 acceptance criterion: pass renders as a tappable action chip
    with the right cost label."""
    setup = _setup_loads_palette() + r"""
        var passAction = {
            id: 'pass', label: 'PASS', icon: '·', enabled: true,
            cost: 'hold action this round'
        };
        var clicked = null;
        var el = window.M3CombatTheater.buildActionButton(p, passAction, false,
            function(a) { clicked = a.id; });
        document.body.appendChild(el);
        // Synthesize click
        el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = {
            tag: el.tagName,
            text: el.textContent.replace(/\s+/g, ' ').trim(),
            actionId: el.getAttribute('data-action-id'),
            tooltip: el.getAttribute('title'),
            clickedId: clicked,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert "PASS" in out["text"], f"Pass button must render label: {out['text']}"
    assert out["actionId"] == "pass"
    assert out["tooltip"] == "hold action this round", (
        "Action chip tooltip must carry the cost label"
    )
    assert out["clickedId"] == "pass", "onClick hook must fire with the action"


def test_runtime_action_button_disabled_shows_cost_badge():
    """When action is disabled, the cost label is exposed as a corner
    badge so the player knows WHY it's disabled (e.g. H3 cover already
    in tier)."""
    setup = _setup_loads_palette() + r"""
        var coverAction = {
            id: 'cover', label: 'COVER', icon: '◥', enabled: false,
            cost: 'already in 1/2 cover (+2D)'
        };
        var el = window.M3CombatTheater.buildActionButton(p, coverAction, false);
        document.body.appendChild(el);
        result = {
            text: el.textContent.replace(/\s+/g, ' ').trim(),
            tooltip: el.getAttribute('title'),
            cursor: el.style.cursor,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    # H3 corner badge — the cost label upper-cased.
    assert "ALREADY IN 1/2 COVER" in out["text"].upper(), (
        "H3 fix: disabled COVER button must surface its cost label"
    )
    assert out["cursor"] == "not-allowed"


def test_runtime_action_button_with_map_shows_minus_1d_pip():
    """When hasMap=true and the action isn't aim/fp, a −1D pip badge
    appears on the chip."""
    setup = _setup_loads_palette() + r"""
        var attackAction = {
            id: 'attack', label: 'ATTACK', icon: '✤', enabled: true, cost: '−0D'
        };
        var el = window.M3CombatTheater.buildActionButton(p, attackAction, true);
        document.body.appendChild(el);
        result = { text: el.textContent };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert "−1D" in out["text"], (
        f"H1 second-action MAP penalty pip must show on chip; got {out['text']!r}"
    )


def test_runtime_action_button_aim_does_not_show_map_pip():
    """AIM doesn't count as a multi-action MAP trigger; no −1D pip
    even when hasMap=true."""
    setup = _setup_loads_palette() + r"""
        var aimAction = {
            id: 'aim', label: 'AIM', icon: '⦿', enabled: true,
            cost: '1 action · +1D next round'
        };
        var el = window.M3CombatTheater.buildActionButton(p, aimAction, true);
        document.body.appendChild(el);
        // Look for −1D inside a child span (the MAP pip), not the cost label.
        var pipSpans = Array.prototype.slice.call(el.querySelectorAll('span'));
        result = {
            // The pip span is the one with explicit border styling — easiest
            // signal here is to scan for a span whose text is exactly '−1D'.
            hasMapPip: pipSpans.some(function(s) {
                return s.textContent.trim() === '−1D';
            }),
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert not out["hasMapPip"], (
        "AIM should NOT show the second-action MAP pip"
    )


def test_runtime_phase_badge_renders_for_each_phase():
    """PhaseBadge dispatches color + label by phase. All 4 phases
    must render."""
    setup = _setup_loads_palette() + r"""
        var phases = ['INITIATIVE', 'DECLARATION', 'POSING', 'RESOLUTION'];
        var out = {};
        phases.forEach(function(ph) {
            var el = window.M3CombatTheater.buildPhaseBadge(p, ph);
            out[ph] = {
                text: el.textContent,
                hasMarker: el.textContent.indexOf('PHASE · ' + ph) !== -1,
            };
        });
        result = out;
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    for ph in ("INITIATIVE", "DECLARATION", "POSING", "RESOLUTION"):
        assert out[ph]["hasMarker"], (
            f"PhaseBadge for {ph} must contain 'PHASE · {ph}'"
        )


def test_runtime_pose_timer_low_time_styling():
    """PoseTimer styling shifts to red + animated when secondsLeft < 30."""
    setup = _setup_loads_palette() + r"""
        var lowEl  = window.M3CombatTheater.buildPoseTimer(p, 15, 180);
        var highEl = window.M3CombatTheater.buildPoseTimer(p, 134, 180);
        result = {
            lowText:  lowEl.textContent,
            highText: highEl.textContent,
            lowHasAnim:  lowEl.innerHTML.indexOf('combatPulse 0.8s') !== -1,
            highHasAnim: highEl.innerHTML.indexOf('combatPulse 0.8s') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert "0:15" in out["lowText"], "Low timer must show 0:15"
    assert "2:14" in out["highText"], "High timer must show 2:14"
    assert out["lowHasAnim"], "Low timer should have the 0.8s pulse animation"
    assert not out["highHasAnim"], (
        "High timer should NOT have the urgent pulse animation"
    )


def test_runtime_action_strip_posing_phase_renders_pose_input():
    """ActionStrip dispatches to buildPosingBody when phase=POSING,
    which renders the pose input + accept-auto-pose button."""
    setup = _setup_loads_palette() + r"""
        var phaseInfo = Object.assign({},
            window.M3CombatTheater.DEFAULT_PHASE_INFO, { phase: 'POSING' });
        var passed = false;
        var el = window.M3CombatTheater.buildActionStrip(p, phaseInfo, {
            onPassPose: function() { passed = true; }
        });
        document.body.appendChild(el);
        var acceptBtn = el.querySelector('[data-test="accept-auto-pose-btn"]');
        result = {
            stripPhase:    el.getAttribute('data-phase'),
            hasAcceptBtn:  !!acceptBtn,
            acceptText:    acceptBtn ? acceptBtn.textContent : null,
            hasPhaseBadge: el.textContent.indexOf('PHASE · POSING') !== -1,
            hasTimer:      el.textContent.indexOf('POSE WINDOW') !== -1,
        };
        // Click the accept button and verify the hook fired.
        if (acceptBtn) {
            acceptBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
            result.hookFired = passed;
        }
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["stripPhase"] == "POSING"
    assert out["hasAcceptBtn"], "B1: accept-auto-pose button must be present in POSING phase"
    assert "ACCEPT AUTO-POSE" in (out["acceptText"] or "")
    assert "sends `pass`" in (out["acceptText"] or "")
    assert "Alt+P" in (out["acceptText"] or "")
    assert out["hasPhaseBadge"]
    assert out["hasTimer"]
    assert out["hookFired"] is True, "onPassPose hook must fire on click"


def test_runtime_action_strip_declaration_phase_renders_chips():
    """ActionStrip dispatches to buildDeclarationBody when phase=
    DECLARATION, which renders the 9 action chips (B1: pass is one
    of them)."""
    setup = _setup_loads_palette() + r"""
        var phaseInfo = Object.assign({},
            window.M3CombatTheater.DEFAULT_PHASE_INFO, { phase: 'DECLARATION' });
        var lastClicked = null;
        var el = window.M3CombatTheater.buildActionStrip(p, phaseInfo, {
            onActionClick: function(a) { lastClicked = a.id; }
        });
        document.body.appendChild(el);
        var chips = el.querySelectorAll('[data-action-id]');
        var chipIds = Array.prototype.map.call(chips, function(c) {
            return c.getAttribute('data-action-id');
        });
        result = {
            stripPhase: el.getAttribute('data-phase'),
            chipCount: chips.length,
            chipIds: chipIds,
            hasPass: chipIds.indexOf('pass') !== -1,
        };
        // Click the pass chip — should fire the hook.
        var passChip = el.querySelector('[data-action-id="pass"]');
        if (passChip) {
            passChip.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
            result.lastClicked = lastClicked;
        }
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["stripPhase"] == "DECLARATION"
    assert out["chipCount"] == 9, (
        f"DECLARATION strip must show 9 action chips (incl. B1 pass); "
        f"got {out['chipCount']}: {out['chipIds']}"
    )
    assert out["hasPass"], "B1: pass chip must be in DECLARATION strip"
    assert out["lastClicked"] == "pass", "onActionClick hook must fire for pass"


def test_runtime_action_strip_resolution_phase_is_passive():
    """ActionStrip dispatches to buildPassiveBody when phase=RESOLUTION
    (no input accepted)."""
    setup = _setup_loads_palette() + r"""
        var phaseInfo = Object.assign({},
            window.M3CombatTheater.DEFAULT_PHASE_INFO, { phase: 'RESOLUTION' });
        var el = window.M3CombatTheater.buildActionStrip(p, phaseInfo);
        document.body.appendChild(el);
        result = {
            stripPhase: el.getAttribute('data-phase'),
            hasResolveText: el.textContent.indexOf('RESOLVING DICE') !== -1,
            // Resolution phase has no clickable action chips.
            actionChips: el.querySelectorAll('[data-action-id]').length,
            hasAcceptBtn: !!el.querySelector('[data-test="accept-auto-pose-btn"]'),
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["stripPhase"] == "RESOLUTION"
    assert out["hasResolveText"], "RESOLUTION phase must show 'RESOLVING DICE…'"
    assert out["actionChips"] == 0
    assert not out["hasAcceptBtn"]


def test_runtime_roll_preview_renders_pool_components():
    """RollPreview shows the pool components (e.g. 'Aim held +1D') +
    expected outcome."""
    setup = _setup_loads_palette() + r"""
        var el = window.M3CombatTheater.buildRollPreview(p);
        document.body.appendChild(el);
        result = {
            hasNextRoll:  el.textContent.indexOf('NEXT ROLL PREVIEW') !== -1,
            hasAimHeld:   el.textContent.indexOf('Aim held') !== -1,
            hasExpected:  el.textContent.indexOf('EXPECTED') !== -1,
            hasEffPool:   el.textContent.indexOf('EFF POOL') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["hasNextRoll"]
    assert out["hasAimHeld"]
    assert out["hasExpected"]
    assert out["hasEffPool"]


def test_runtime_your_status_pip_array_drives_wound_rendering():
    """YourStatus accepts a custom `pips` array — each entry becomes a
    rendered pip, lit when true."""
    setup = _setup_loads_palette() + r"""
        var status = {
            name: 'TEY VOSS · LIVE',
            wound: 'WOUNDED ×2',
            woundPen: '−2D',
            woundProgress: '3/5',
            pips: [true, true, true, false, false],
            chips: ['IN COVER'],
        };
        var el = window.M3CombatTheater.buildYourStatus(p, status);
        document.body.appendChild(el);
        var pipDivs = el.querySelectorAll('div[style*="flex: 1"]');
        result = {
            hasWoundLabel: el.textContent.indexOf('WOUNDED ×2') !== -1,
            hasPenalty: el.textContent.indexOf('−2D') !== -1,
            hasProgress: el.textContent.indexOf('3/5') !== -1,
            // 5 wound pips drawn
            pipCount: pipDivs.length,
            hasChip: el.textContent.indexOf('IN COVER') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_combat_theater.js"], setup)
    assert out["hasWoundLabel"]
    assert out["hasPenalty"]
    assert out["hasProgress"]
    assert out["pipCount"] == 5
    assert out["hasChip"]
