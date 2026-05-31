"""
test_m3_sheet.py — Drop 4.6 regression lock for m3_sheet.js.

Drop 4.6 ports map_v3/sheet-v2.jsx (1,195 JSX LOC) into a vanilla-JS
SPA module at static/spa/m3_sheet.js. This file pins:

  · Module shape (IIFE + window.M3Sheet + documented surface).
  · Bug-fix sprint corrections (B3/B4/H4/H5/L3/L5) preserved in
    TEY_V2_FIXTURE and renderer code.
  · WOUND_RUNGS in client.html gained a labelLong field per rung.
  · Each tab body renderer (Vitals/Skills/Gear/World/Story/Force)
    returns the expected structure.
  · The tab dispatcher routes by currentTab arg.

Pattern parallels tests/spa/test_m3_combat_theater.py (Drop 4.5).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT     = Path(__file__).resolve().parent.parent.parent
SHEET_MODULE  = REPO_ROOT / "static" / "spa" / "m3_sheet.js"
CLIENT_HTML   = REPO_ROOT / "static" / "client.html"

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
    assert SHEET_MODULE.exists(), (
        f"Module missing at {SHEET_MODULE}. Drop 4.6 either didn't ship "
        "or was reverted."
    )


def test_module_is_iife():
    src = SHEET_MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src, (
        "m3_sheet.js must be wrapped in an IIFE."
    )
    assert "})();" in src, "IIFE not closed at end of m3_sheet.js"


def test_module_exports_namespace():
    src = SHEET_MODULE.read_text(encoding="utf-8")
    assert "window.M3Sheet" in src, "Module must export window.M3Sheet"


def test_module_defines_all_documented_builders():
    src = SHEET_MODULE.read_text(encoding="utf-8")
    builders = [
        "buildCharacterSheet",
        "buildSheetHeader",
        "buildSheetVitals",
        "buildSheetSkills",
        "buildSheetGear",
        "buildSheetWorld",
        "buildSheetStory",
        "buildSheetForce",
        "buildPaperDoll",
        "buildFactionRadar",
        "buildWoundFigure",
        "buildCooldownWheel",
    ]
    for b in builders:
        assert "function " + b in src, f"Missing function definition: {b}"
        assert re.search(r"\b" + b + r"\s*:\s*" + b + r"\b", src), (
            f"Missing export entry for {b} in window.M3Sheet"
        )


def test_init_function_present_and_exported():
    src = SHEET_MODULE.read_text(encoding="utf-8")
    assert "function init(" in src
    assert re.search(r"init\s*:\s*init\b", src)


def test_client_html_loads_module_and_calls_init():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert '/static/spa/m3_sheet.js' in src, (
        "client.html missing <script> tag for m3_sheet.js"
    )
    assert "M3Sheet.init(" in src, (
        "client.html doesn't call M3Sheet.init()"
    )


# ════════════════════════════════════════════════════════════════════
# WOUND_RUNGS contract — Drop 4.6 added a labelLong field to client.html
# ════════════════════════════════════════════════════════════════════

def test_wound_rungs_gained_label_long_field():
    """B4 / L3: WOUND_RUNGS in client.html must carry a labelLong field
    per rung so the sheet's wound ladder renders the full names
    ('WOUNDED TWICE', 'INCAPACITATED', 'MORTALLY WOUNDED', 'DEAD')."""
    src = CLIENT_HTML.read_text(encoding="utf-8")
    # The block lives near line 4257. Find a stable anchor.
    m = re.search(
        r"var WOUND_RUNGS\s*=\s*\[(.+?)\];",
        src, flags=re.DOTALL
    )
    assert m, "WOUND_RUNGS array not found in client.html"
    block = m.group(1)
    # Every rung must have a labelLong.
    occurrences = block.count("labelLong:")
    assert occurrences == 7, (
        f"All 7 WOUND_RUNGS entries must have labelLong; got {occurrences}"
    )
    # Specific labels — these are the L3-canonical strings.
    for expected in (
        "'HEALTHY'",
        "'STUNNED'",
        "'WOUNDED'",
        "'WOUNDED TWICE'",
        "'INCAPACITATED'",
        "'MORTALLY WOUNDED'",
        "'DEAD'",
    ):
        assert expected in block, (
            f"WOUND_RUNGS labelLong missing or renamed: {expected}"
        )
    # Negative control — "KILLED" must NOT appear as a labelLong (L3 fix).
    assert "labelLong: 'KILLED'" not in block, (
        "L3 regression: 'KILLED' used as labelLong; should be 'DEAD'"
    )


# ════════════════════════════════════════════════════════════════════
# Bug-fix-sprint contract — B3/B4/H4/H5/L5
# ════════════════════════════════════════════════════════════════════

def test_b3_era_contamination_personality_text():
    """B3: personality text mentions 'Senate elites' and 'Trade
    Federation profiteers' — Clone Wars era contemporaries — and does
    NOT mention 'Empire' or 'Imperial'."""
    src = SHEET_MODULE.read_text(encoding="utf-8")
    assert "Distrusts Senate elites and Trade Federation profiteers" in src, (
        "B3 fix: personality text must include 'Distrusts Senate elites "
        "and Trade Federation profiteers'"
    )
    # Negative control — no Empire/Imperial framing in story texts.
    # (The word might appear in unrelated comments, but the fixture
    # texts shouldn't carry it.)
    # Scope: scan within the TEY_V2_FIXTURE literal.
    fixture = _extract_block(src, "var TEY_V2_FIXTURE = {", "};")
    assert fixture, "TEY_V2_FIXTURE block not found"
    assert "Empire" not in fixture, (
        "B3 regression: 'Empire' present in TEY_V2_FIXTURE story texts"
    )
    assert "Imperial" not in fixture, (
        "B3 regression: 'Imperial' present in TEY_V2_FIXTURE story texts"
    )


def test_b3_sealed_senate_dispatch():
    """B3: the dispatch job is 'Sealed Senate Dispatch' (Clone Wars era)
    — not 'Imperial Dispatch'."""
    src = SHEET_MODULE.read_text(encoding="utf-8")
    assert "Sealed Senate Dispatch" in src
    assert "Imperial Dispatch" not in src


def test_b3_story_nouns_include_senate_not_empire():
    """B3: the story-noun highlight list contains 'Senate' for B3-era
    clickability and does NOT contain 'Empire' / 'Imperial'."""
    src = SHEET_MODULE.read_text(encoding="utf-8")
    m = re.search(r"var STORY_NOUNS\s*=\s*\[(.+?)\];", src, flags=re.DOTALL)
    assert m, "STORY_NOUNS array not found"
    block = m.group(1)
    assert "'Senate'" in block, "B3 fix: 'Senate' must be in STORY_NOUNS"
    assert "'Empire'" not in block
    assert "'Imperial'" not in block


def test_h4_force_panel_carries_three_skills():
    """H4: the Force panel data carries three skills (Control, Sense,
    Alter), each with code + desc; powers list tagged with the
    skill(s) each draws on."""
    src = SHEET_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var TEY_V2_FIXTURE = {", "};")
    assert fixture, "TEY_V2_FIXTURE block not found"
    # Force skills section
    assert "name: 'Control'" in fixture
    assert "name: 'Sense'" in fixture
    assert "name: 'Alter'" in fixture
    # Powers — at least Concentration + Combat Sense should appear,
    # each with a `skills:` array.
    assert "name: 'Concentration'" in fixture
    assert "name: 'Combat Sense'" in fixture
    assert "name: 'Lightsaber Combat'" in fixture
    # Lightsaber Combat draws on Control + Sense.
    m = re.search(
        r"name:\s*'Lightsaber Combat'[^}]*skills:\s*\[\s*'Control'\s*,\s*'Sense'\s*\]",
        fixture
    )
    assert m, (
        "H4: Lightsaber Combat must be tagged with ['Control', 'Sense']"
    )


def test_h5_fp_renders_without_fpmax():
    """H5: FP value rendered without an fpMax denominator. The sample
    fixture must not declare fpMax; the renderer paths must not
    reference an fp/max construct for FP."""
    src = SHEET_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var TEY_V2_FIXTURE = {", "};")
    assert fixture, "TEY_V2_FIXTURE block not found"
    assert "fpMax" not in fixture, (
        "H5 regression: TEY_V2_FIXTURE carries an fpMax field"
    )
    # The Vitals points panel must call buildPointBlock with null for max
    # on the FORCE PTS slot. Pattern: buildPointBlock(p, 'FORCE PTS', c.fp, null, ...)
    assert re.search(
        r"buildPointBlock\(p,\s*'FORCE PTS',\s*c\.fp,\s*null",
        src,
    ), (
        "H5 fix not preserved: buildSheetVitals must pass null as the "
        "max arg for the FORCE PTS PointBlock"
    )


def test_h5_dsp_still_capped_at_5():
    """H5: DSP is still capped at 5 per design conventions; PointBlock
    for DARK SIDE passes 5 as the max."""
    src = SHEET_MODULE.read_text(encoding="utf-8")
    assert re.search(
        r"buildPointBlock\(p,\s*'DARK SIDE',\s*c\.dsp,\s*5",
        src,
    ), (
        "H5 fix: DSP must still have max=5 in buildSheetVitals"
    )


def test_l3_wound_ladder_consumes_labelLong():
    """L3: the wound-track ladder reads r.labelLong (full name), not
    r.label (compact name)."""
    src = SHEET_MODULE.read_text(encoding="utf-8")
    # The rung-row builder in buildSheetVitals reads r.labelLong
    assert re.search(r"r\.labelLong", src), (
        "L3 fix: wound rendering must consume r.labelLong (full name)"
    )


def test_l5_tey_voss_uppercase_in_fixture():
    """L5: character name is 'TEY VOSS' (uppercase) in the fixture so
    the header renders consistently with the design standard."""
    src = SHEET_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var TEY_V2_FIXTURE = {", "};")
    assert fixture, "TEY_V2_FIXTURE block not found"
    assert "name: 'TEY VOSS'" in fixture, (
        "L5 fix: fixture character name must be 'TEY VOSS' (uppercase)"
    )


# ════════════════════════════════════════════════════════════════════
# Helper — extract a brace-delimited block by anchors
# ════════════════════════════════════════════════════════════════════

def _extract_block(src: str, start_marker: str, end_marker: str) -> str:
    """Find start_marker in src, return text between it and the first
    occurrence of end_marker that brings the brace count back to zero.
    Not a full JS parser — works for our case where TEY_V2_FIXTURE is
    a single brace-balanced literal."""
    i = src.find(start_marker)
    if i < 0:
        return ""
    open_brace = src.find("{", i)
    if open_brace < 0:
        return ""
    depth = 0
    j = open_brace
    while j < len(src):
        ch = src[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace:j+1]
        j += 1
    return ""


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

# Prelude loads palette + WOUND_RUNGS shim (m3_sheet.js consumes
# window.WOUND_RUNGS, which lives in client.html in production).
_WOUND_RUNGS_SHIM = """
window.WOUND_RUNGS = [
  { v: 0, label: 'HEALTHY',     labelLong: 'HEALTHY',          pen: '',    sev: 'ok'   },
  { v: 1, label: 'STUNNED',     labelLong: 'STUNNED',          pen: '',    sev: 'warn' },
  { v: 2, label: 'WOUNDED',     labelLong: 'WOUNDED',          pen: '-1D', sev: 'warn' },
  { v: 3, label: 'WOUNDED \\u00d72',  labelLong: 'WOUNDED TWICE',    pen: '-2D', sev: 'hurt' },
  { v: 4, label: 'INCAP',       labelLong: 'INCAPACITATED',    pen: '',    sev: 'crit' },
  { v: 5, label: 'MORTAL',      labelLong: 'MORTALLY WOUNDED', pen: '',    sev: 'crit' },
  { v: 6, label: 'DEAD',        labelLong: 'DEAD',             pen: '',    sev: 'dead' }
];
"""

def _setup_prelude():
    return (
        "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"
        + _WOUND_RUNGS_SHIM
    )


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var S = window.M3Sheet;
        result = {
            hasNamespace:       !!S,
            schemaVersion:      S && S.SCHEMA_VERSION,
            hasInit:            typeof S.init === 'function',
            hasBuildSheet:      typeof S.buildCharacterSheet === 'function',
            hasBuildVitals:     typeof S.buildSheetVitals === 'function',
            hasBuildForce:      typeof S.buildSheetForce === 'function',
            hasFixture:         !!S.TEY_V2_FIXTURE,
            hasStoryNouns:      Array.isArray(S.STORY_NOUNS),
            storyNounsHasSenate:S.STORY_NOUNS.indexOf('Senate') !== -1,
            fixtureName:        S.TEY_V2_FIXTURE.name,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["hasNamespace"]
    assert out["schemaVersion"] == 1
    assert out["hasInit"]
    assert out["hasBuildSheet"]
    assert out["hasBuildVitals"]
    assert out["hasBuildForce"]
    assert out["hasFixture"]
    assert out["hasStoryNouns"]
    assert out["storyNounsHasSenate"]
    assert out["fixtureName"] == "TEY VOSS"


def test_runtime_buildCharacterSheet_skills_default_tab():
    """Top-level renderer with no explicit currentTab defaults to SKILLS."""
    setup = _setup_prelude() + r"""
        var el = window.M3Sheet.buildCharacterSheet(p);
        document.body.appendChild(el);
        var body = el.querySelector('[data-current-tab]');
        result = {
            tag: el.tagName,
            currentTab: body && body.getAttribute('data-current-tab'),
            sheetName: el.getAttribute('data-sheet-character'),
            // Skills tab body contains 'CHARACTER POINTS' banner
            hasCpBanner: el.textContent.indexOf('CHARACTER POINTS') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["tag"] == "DIV"
    assert out["currentTab"] == "SKILLS"
    assert out["sheetName"] == "TEY VOSS"
    assert out["hasCpBanner"]


def test_runtime_buildCharacterSheet_routes_each_tab():
    """Each currentTab value routes to the right body renderer."""
    setup = _setup_prelude() + r"""
        var tabs = ['VITALS', 'SKILLS', 'GEAR', 'WORLD', 'STORY', 'FORCE'];
        var probes = {};
        tabs.forEach(function(t) {
            var el = window.M3Sheet.buildCharacterSheet(p, null, t);
            probes[t] = {
                tag: el.tagName,
                bodyTab: el.querySelector('[data-current-tab]').getAttribute('data-current-tab'),
                // Each tab's body has distinguishing content. Use anchor text.
                vitalsHasWound: el.textContent.indexOf('WOUND TRACK') !== -1,
                skillsHasCP:    el.textContent.indexOf('CHARACTER POINTS') !== -1,
                gearHasLoadout: el.textContent.indexOf('LOADOUT') !== -1,
                worldHasFaction:el.textContent.indexOf('FACTION REPUTATION') !== -1,
                storyHasQuote:  el.textContent.indexOf('flown worse for less') !== -1,
                forceHasSkills: el.textContent.indexOf('FORCE SKILLS') !== -1,
            };
        });
        result = probes;
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    # VITALS shows WOUND TRACK
    assert out["VITALS"]["vitalsHasWound"]
    # SKILLS shows CHARACTER POINTS
    assert out["SKILLS"]["skillsHasCP"]
    # GEAR shows LOADOUT
    assert out["GEAR"]["gearHasLoadout"]
    # WORLD shows FACTION REPUTATION
    assert out["WORLD"]["worldHasFaction"]
    # STORY shows the Tey Voss quote
    assert out["STORY"]["storyHasQuote"]
    # FORCE shows FORCE SKILLS (the H4 panel)
    assert out["FORCE"]["forceHasSkills"]


def test_runtime_force_tab_only_shown_when_force_sensitive():
    """If character.forceSensitive is false, the FORCE tab pill is not
    rendered and FORCE currentTab returns empty body."""
    setup = _setup_prelude() + r"""
        var nonForce = Object.assign({}, window.M3Sheet.TEY_V2_FIXTURE,
                                     { forceSensitive: false });
        var el = window.M3Sheet.buildCharacterSheet(p, nonForce, 'FORCE');
        document.body.appendChild(el);
        var tabPills = el.querySelectorAll('[data-tab-id]');
        var tabIds = Array.prototype.map.call(tabPills, function(t) {
            return t.getAttribute('data-tab-id');
        });
        // FORCE shouldn't be in the tab list; FORCE body renders empty.
        result = {
            tabIds: tabIds,
            hasForceTab: tabIds.indexOf('FORCE') !== -1,
            forceBodyHasContent: el.textContent.indexOf('FORCE SKILLS') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert not out["hasForceTab"], (
        "FORCE tab should be hidden when character.forceSensitive=false"
    )
    assert not out["forceBodyHasContent"], (
        "FORCE body should be empty when character.forceSensitive=false"
    )
    assert "VITALS" in out["tabIds"]
    assert "SKILLS" in out["tabIds"]


def test_runtime_tab_click_hook_fires():
    """hooks.onTabClick fires when a tab pill is clicked."""
    setup = _setup_prelude() + r"""
        var clicked = null;
        var el = window.M3Sheet.buildCharacterSheet(p, null, 'SKILLS', {
            onTabClick: function(id) { clicked = id; }
        });
        document.body.appendChild(el);
        var gearPill = el.querySelector('[data-tab-id="GEAR"]');
        gearPill.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { clickedTab: clicked };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["clickedTab"] == "GEAR"


def test_runtime_vitals_renders_six_wound_rungs_with_labelLong():
    """B4 / L3: the wound ladder renders rungs 1..6 (HEALTHY is implicit
    at tier 0), each labeled with its full labelLong, never KILLED."""
    setup = _setup_prelude() + r"""
        var el = window.M3Sheet.buildSheetVitals(p, window.M3Sheet.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        var rungs = el.querySelectorAll('[data-rung-v]');
        var labels = Array.prototype.map.call(rungs, function(r) {
            return r.textContent.replace(/\s+/g, ' ').trim();
        });
        result = {
            rungCount: rungs.length,
            // Just the label substrings — penalty in parens may be appended.
            hasWoundedTwice:     labels.some(function(l) { return l.indexOf('WOUNDED TWICE') !== -1; }),
            hasIncapacitated:    labels.some(function(l) { return l.indexOf('INCAPACITATED') !== -1; }),
            hasMortallyWounded:  labels.some(function(l) { return l.indexOf('MORTALLY WOUNDED') !== -1; }),
            hasDead:             labels.some(function(l) { return l.indexOf('DEAD') !== -1; }),
            hasKilled:           labels.some(function(l) { return l.indexOf('KILLED') !== -1; }),
            allLabels: labels,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["rungCount"] == 6, (
        f"Wound ladder should render 6 rungs (1..6); got {out['rungCount']}"
    )
    assert out["hasWoundedTwice"]
    assert out["hasIncapacitated"]
    assert out["hasMortallyWounded"]
    assert out["hasDead"]
    # L3 negative control — KILLED must not appear.
    assert not out["hasKilled"], (
        "L3 regression: 'KILLED' label rendered (should be 'DEAD')"
    )


def test_runtime_vitals_fp_block_has_no_max_denominator():
    """H5: FORCE PTS PointBlock renders the FP value without a '/max'
    denominator. DSP block does have '/5'."""
    setup = _setup_prelude() + r"""
        var el = window.M3Sheet.buildSheetVitals(p, window.M3Sheet.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        var text = el.textContent;
        // The PointBlock for FORCE PTS is identifiable by border color
        // (p.green + '66'). Easier: it's the PointBlock that contains
        // the substring 'FORCE PTS' AND 'spend → ×2 ALL DICE' AND nothing else.
        // Find the smallest such ancestor by walking the DOM.
        result = {
            hasForcePtsLabel: text.indexOf('FORCE PTS') !== -1,
            hasDarkSideLabel: text.indexOf('DARK SIDE') !== -1,
            // The '/5' (DSP max) should appear somewhere.
            hasDspMaxSlash: text.indexOf('/5') !== -1,
            // The FORCE PTS block itself: find a div whose textContent
            // starts with 'FORCE PTS' AND ends with the FORCE PTS sub-text
            // (no DARK SIDE bleed-through). That isolates the inner block.
            forceBlockHasSlash: (function() {
                var divs = el.querySelectorAll('div');
                for (var i = 0; i < divs.length; i++) {
                    var d = divs[i];
                    var t = d.textContent;
                    if (t.indexOf('FORCE PTS') === 0 &&
                        t.indexOf('DARK SIDE') === -1 &&
                        t.indexOf('CHAR PTS') === -1 &&
                        t.indexOf('×2 ALL DICE') !== -1) {
                        return t.indexOf('/') !== -1;
                    }
                }
                return null;
            })(),
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["hasForcePtsLabel"]
    assert out["hasDarkSideLabel"]
    assert out["hasDspMaxSlash"], "DSP block should still show /5 max"
    assert out["forceBlockHasSlash"] is False, (
        "H5 regression: FORCE PTS block contains a '/' (max denominator)"
    )


def test_runtime_force_panel_renders_three_skills_and_powers():
    """H4: SheetForce renders Control/Sense/Alter skill cards + powers
    list with skill-tag suffixes."""
    setup = _setup_prelude() + r"""
        var el = window.M3Sheet.buildSheetForce(p, window.M3Sheet.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        var skillCards = el.querySelectorAll('[data-force-skill]');
        var skillNames = Array.prototype.map.call(skillCards, function(c) {
            return c.getAttribute('data-force-skill');
        });
        var powerRows = el.querySelectorAll('[data-power-name]');
        var powerNames = Array.prototype.map.call(powerRows, function(r) {
            return r.getAttribute('data-power-name');
        });
        result = {
            skillNames: skillNames,
            powerNames: powerNames,
            // Powers tagged with their skill(s) — 'Lightsaber Combat'
            // shows 'CON · SEN' (3-letter caps of Control + Sense).
            hasLightsaberTag: el.textContent.indexOf('CON · SEN') !== -1,
            // Alignment marker present (it's a small div)
            hasAlignmentMarker: !!el.querySelector('[data-alignment-marker]'),
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["skillNames"] == ["Control", "Sense", "Alter"]
    # All 7 powers in the fixture
    assert "Concentration" in out["powerNames"]
    assert "Combat Sense" in out["powerNames"]
    assert "Lightsaber Combat" in out["powerNames"]
    assert "Affect Mind" in out["powerNames"]
    assert out["hasLightsaberTag"], (
        "H4: 'Lightsaber Combat' must show 'CON · SEN' (Control+Sense tags)"
    )
    assert out["hasAlignmentMarker"]


def test_runtime_skills_combat_locked_banner():
    """In-combat character: CP-advancement banner shows 'IN COMBAT' and
    SkillRow advance cells show '—' (locked)."""
    setup = _setup_prelude() + r"""
        var inCombatChar = Object.assign({}, window.M3Sheet.TEY_V2_FIXTURE,
                                        { inCombat: true });
        var el = window.M3Sheet.buildSheetSkills(p, inCombatChar);
        document.body.appendChild(el);
        result = {
            hasInCombatBanner: el.textContent.indexOf('IN COMBAT') !== -1,
            hasAdvanceButton: !!el.querySelector('button[title^="Costs"]'),
            advanceCellTextHasDash: el.textContent.indexOf('—') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["hasInCombatBanner"]
    # No advance buttons when locked
    assert not out["hasAdvanceButton"]
    assert out["advanceCellTextHasDash"]


def test_runtime_skills_out_of_combat_advance_buttons():
    """Out-of-combat character: SkillRow shows clickable '↑ NN' advance
    buttons."""
    setup = _setup_prelude() + r"""
        var ooc = Object.assign({}, window.M3Sheet.TEY_V2_FIXTURE,
                                { inCombat: false });
        var el = window.M3Sheet.buildSheetSkills(p, ooc);
        document.body.appendChild(el);
        var advanceButtons = el.querySelectorAll('button[title^="Costs"]');
        result = {
            hasAdvanceButton: advanceButtons.length > 0,
            buttonCount: advanceButtons.length,
            firstButtonText: advanceButtons[0] ? advanceButtons[0].textContent : null,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["hasAdvanceButton"]
    # Skills count varies by attribute, ~18+ in the fixture
    assert out["buttonCount"] >= 15
    assert out["firstButtonText"].startswith("↑ ")


def test_runtime_gear_renders_paper_doll_and_inventory():
    """Gear tab renders 6-slot paper doll + carried-item grid."""
    setup = _setup_prelude() + r"""
        var el = window.M3Sheet.buildSheetGear(p, window.M3Sheet.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        var slots = el.querySelectorAll('[data-slot-id]');
        var slotIds = Array.prototype.map.call(slots, function(s) {
            return s.getAttribute('data-slot-id');
        });
        var items = el.querySelectorAll('[data-item-id]');
        result = {
            slotIds: slotIds,
            slotCount: slots.length,
            itemCount: items.length,
            hasHeavyBlaster: el.textContent.indexOf('Heavy Blaster Pistol') !== -1,
            hasSoakTotal: el.textContent.indexOf('TOTAL SOAK') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["slotCount"] == 6
    assert set(out["slotIds"]) == {"head", "chest", "main", "off", "belt", "boots"}
    assert out["itemCount"] == 11  # TEY_V2_FIXTURE.carry length
    assert out["hasHeavyBlaster"]
    assert out["hasSoakTotal"]


def test_runtime_world_renders_factions_jobs_cooldowns():
    """World tab renders faction list + radar + jobs + cooldowns."""
    setup = _setup_prelude() + r"""
        var el = window.M3Sheet.buildSheetWorld(p, window.M3Sheet.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        var factionRows = el.querySelectorAll('[data-faction-id]');
        var jobCards = el.querySelectorAll('[data-job-id]');
        var cdWheels = el.querySelectorAll('[data-cd-id]');
        result = {
            factionCount: factionRows.length,
            jobCount: jobCards.length,
            cdCount: cdWheels.length,
            // B3 — Senate Dispatch job present
            hasSenateDispatch: el.textContent.indexOf('Sealed Senate Dispatch') !== -1,
            // Ship card
            hasMynock: el.textContent.indexOf('RUSTY MYNOCK') !== -1,
            // SVG radar present
            hasRadar: !!el.querySelector('svg polygon'),
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["factionCount"] == 7
    assert out["jobCount"] == 3
    assert out["cdCount"] == 4
    assert out["hasSenateDispatch"]
    assert out["hasMynock"]
    assert out["hasRadar"]


def test_runtime_story_renders_highlighted_nouns():
    """STORY tab: text is rendered with story-noun highlights as
    clickable spans. Senate is highlighted (B3); Empire is not in the
    list."""
    setup = _setup_prelude() + r"""
        var el = window.M3Sheet.buildSheetStory(p, window.M3Sheet.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        // The highlightStoryNouns function wraps nouns in a <span> with
        // a 'cursor: pointer' style; easier check: find a span whose
        // title attribute starts with 'Open holocron:'
        var holoSpans = el.querySelectorAll('span[title^="Open holocron:"]');
        var titles = Array.prototype.map.call(holoSpans, function(s) {
            return s.getAttribute('title');
        });
        result = {
            count: holoSpans.length,
            hasSenateHighlight: titles.some(function(t) { return t.indexOf('Senate') !== -1; }),
            hasKesselHighlight: titles.some(function(t) { return t.indexOf('Kessel') !== -1; }),
            hasJabbaHighlight:  titles.some(function(t) { return t.indexOf('Jabba') !== -1; }),
            // Story-text negative: no Empire span
            hasEmpireHighlight: titles.some(function(t) { return t.indexOf('Empire') !== -1; }),
            // Connections render
            hasMakTorrin: el.textContent.indexOf('Mak Torrin') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    # Several nouns should be highlighted in fixture text
    assert out["count"] >= 5, (
        f"Expected several story-noun highlights; got {out['count']}"
    )
    assert out["hasSenateHighlight"], (
        "B3 fix: Senate must be a clickable story-noun"
    )
    assert out["hasKesselHighlight"]
    assert out["hasJabbaHighlight"]
    assert not out["hasEmpireHighlight"]
    assert out["hasMakTorrin"]


def test_runtime_l5_uppercase_name_in_header():
    """L5: header renders TEY VOSS in uppercase exactly."""
    setup = _setup_prelude() + r"""
        var el = window.M3Sheet.buildSheetHeader(p, window.M3Sheet.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        result = {
            hasUppercaseName: el.textContent.indexOf('TEY VOSS') !== -1,
            // Lowercase variant should NOT appear in the header.
            hasLowercaseName: el.textContent.indexOf('Tey Voss') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["hasUppercaseName"]
    assert not out["hasLowercaseName"]


# ════════════════════════════════════════════════════════════════════
# Drop 4.12a — buildCharacterSheetModal + createCharacterSheetModal
# ════════════════════════════════════════════════════════════════════

def test_module_exports_modal_builder_and_handle():
    """Drop 4.12a — both the stateless builder and the stateful create
    handle are exported on window.M3Sheet."""
    src = (Path(__file__).resolve().parent.parent.parent
           / "static" / "spa" / "m3_sheet.js").read_text(encoding="utf-8")
    assert "function buildCharacterSheetModal(" in src
    assert "function createCharacterSheetModal(" in src
    import re
    assert re.search(
        r"buildCharacterSheetModal\s*:\s*buildCharacterSheetModal\b", src
    )
    assert re.search(
        r"createCharacterSheetModal\s*:\s*createCharacterSheetModal\b", src
    )


def test_runtime_modal_builder_renders_backdrop_and_window():
    """The stateless builder returns a backdrop element with the
    expected window child. data-sheet-mode attribute on backdrop
    pins the surface for SPA-router/CSS targeting."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var el = N.buildCharacterSheetModal(p, N.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        var wrap = el.querySelector('[data-sheet-modal-wrap]');
        result = {
            tag:              el.tagName,
            mode:             el.getAttribute('data-sheet-mode'),
            childCount:       el.children.length,
            wrapMode:         wrap && wrap.getAttribute('data-sheet-modal-wrap'),
            wrapWidth:        wrap && wrap.style.width,
            wrapHeight:       wrap && wrap.style.height,
            // The sheet inside should be there with the character name.
            hasSheet:         !!wrap.querySelector('[data-sheet-character]'),
            sheetName:        wrap.querySelector('[data-sheet-character]').getAttribute('data-sheet-character'),
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["tag"]         == "DIV"
    assert out["mode"]        == "modal"
    assert out["childCount"]  == 1                 # just the wrap
    assert out["wrapMode"]    == "normal"           # not maxed by default
    assert out["wrapWidth"]   == "1080px"
    assert out["wrapHeight"]  == "720px"
    assert out["hasSheet"]    is True
    assert out["sheetName"]   == "TEY VOSS"


def test_runtime_modal_builder_maxed_uses_percent_dims():
    """When hooks.maxed=true, the wrapper dims switch to 95%/92% per
    the JSX source."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var el = N.buildCharacterSheetModal(p, N.TEY_V2_FIXTURE, { maxed: true });
        document.body.appendChild(el);
        var wrap = el.querySelector('[data-sheet-modal-wrap]');
        result = {
            wrapMode:    wrap.getAttribute('data-sheet-modal-wrap'),
            wrapWidth:   wrap.style.width,
            wrapHeight:  wrap.style.height,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["wrapMode"]    == "maxed"
    assert out["wrapWidth"]   == "95%"
    assert out["wrapHeight"]  == "92%"


def test_runtime_modal_backdrop_click_fires_onClose():
    """Clicking the backdrop (but NOT the window) fires onClose."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var closeCount = 0;
        var el = N.buildCharacterSheetModal(p, N.TEY_V2_FIXTURE, {
            onClose: function() { closeCount++; },
        });
        document.body.appendChild(el);

        // Simulate click on backdrop (target === backdrop). The handler
        // checks e.target === backdrop, so we need to fire a real click
        // event with the right target.
        var ev = new window.Event('click', { bubbles: true });
        // jsdom doesn't set target via constructor; dispatch via the
        // backdrop element directly.
        el.dispatchEvent(ev);
        var afterBackdropClick = closeCount;

        // Now click inside the wrap. Should NOT increment closeCount
        // because e.target !== backdrop.
        var wrap = el.querySelector('[data-sheet-modal-wrap]');
        var ev2 = new window.Event('click', { bubbles: true });
        wrap.dispatchEvent(ev2);
        var afterWrapClick = closeCount;

        result = {
            afterBackdropClick: afterBackdropClick,
            afterWrapClick:     afterWrapClick,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["afterBackdropClick"] == 1
    # Click on wrap bubbles → backdrop's click handler sees target=wrap,
    # not target=backdrop, so onClose should NOT fire again.
    assert out["afterWrapClick"]     == 1


def test_runtime_modal_inner_sheet_renders_close_and_maximize_affordances():
    """asPopup=true is threaded through to buildCharacterSheet, so the
    inner sheet header should show CLOSE and MAXIMIZE buttons."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var el = N.buildCharacterSheetModal(p, N.TEY_V2_FIXTURE);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            // The header's right-buttons (asPopup branch) include these.
            hasClose:    text.indexOf('CLOSE') >= 0,
            hasMaximize: text.indexOf('MAXIMIZE') >= 0 || text.indexOf('RESTORE') >= 0,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["hasClose"]    is True
    assert out["hasMaximize"] is True


def test_runtime_modal_close_affordance_fires_onClose():
    """The X CLOSE button in the sheet header fires hooks.onClose."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var closeCount = 0;
        var el = N.buildCharacterSheetModal(p, N.TEY_V2_FIXTURE, {
            onClose: function() { closeCount++; },
        });
        document.body.appendChild(el);

        // Find the CLOSE button in the header. buildHeaderBtn returns a
        // <button> element with the text label.
        var buttons = el.querySelectorAll('button');
        var closeBtn = null;
        for (var i = 0; i < buttons.length; i++) {
            var t = buttons[i].textContent || '';
            if (t.indexOf('CLOSE') >= 0) {
                closeBtn = buttons[i];
                break;
            }
        }
        if (closeBtn) {
            closeBtn.click();
        }
        result = {
            closeCount:    closeCount,
            foundBtn:      !!closeBtn,
            buttonCount:   buttons.length,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["foundBtn"]   is True
    assert out["closeCount"] == 1


def test_runtime_create_handle_owns_state_and_renders():
    """createCharacterSheetModal returns a handle with the expected
    surface: element + getState + setTab + setMaxed + destroy. The
    element is a stable outer container; the modal sits inside."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var h = N.createCharacterSheetModal(p, N.TEY_V2_FIXTURE);
        document.body.appendChild(h.element);

        var s0 = h.getState();
        var backdrop = h.element.querySelector('[data-sheet-mode]');
        result = {
            hasElement:    !!h.element,
            elementTag:    h.element.tagName,
            isContainer:   h.element.getAttribute('data-sheet-modal-container') === '1',
            hasBackdrop:   !!backdrop,
            backdropMode:  backdrop && backdrop.getAttribute('data-sheet-mode'),
            startMaxed:    s0.maxed,
            startTab:      s0.currentTab,
            hasGetState:   typeof h.getState === 'function',
            hasSetTab:     typeof h.setTab === 'function',
            hasSetMaxed:   typeof h.setMaxed === 'function',
            hasDestroy:    typeof h.destroy === 'function',
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["hasElement"]    is True
    assert out["elementTag"]    == "DIV"
    assert out["isContainer"]   is True
    assert out["hasBackdrop"]   is True
    assert out["backdropMode"]  == "modal"
    assert out["startMaxed"]    is False
    assert out["startTab"]      == "SKILLS"
    assert out["hasGetState"]   is True
    assert out["hasSetTab"]     is True
    assert out["hasSetMaxed"]   is True
    assert out["hasDestroy"]    is True


def test_runtime_create_handle_setMaxed_toggles_dims():
    """h.setMaxed(true) re-renders the inner wrap with percent dims."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var maximizeCount = 0;
        var h = N.createCharacterSheetModal(p, N.TEY_V2_FIXTURE, {
            onMaximize: function(maxed) { maximizeCount++; },
        });
        document.body.appendChild(h.element);

        // Initially normal.
        var w1 = h.element.querySelector('[data-sheet-modal-wrap]');
        var dim1 = { mode: w1.getAttribute('data-sheet-modal-wrap'),
                     w: w1.style.width, h: w1.style.height };

        // Toggle to maxed via the handle.
        h.setMaxed(true);
        var w2 = h.element.querySelector('[data-sheet-modal-wrap]');
        var dim2 = { mode: w2.getAttribute('data-sheet-modal-wrap'),
                     w: w2.style.width, h: w2.style.height };

        // setMaxed(true) again should be a no-op (already maxed).
        h.setMaxed(true);
        var w3 = h.element.querySelector('[data-sheet-modal-wrap]');
        var dim3 = { mode: w3.getAttribute('data-sheet-modal-wrap') };

        // Back to normal.
        h.setMaxed(false);
        var w4 = h.element.querySelector('[data-sheet-modal-wrap]');
        var dim4 = { mode: w4.getAttribute('data-sheet-modal-wrap'),
                     w: w4.style.width, h: w4.style.height };

        result = {
            dim1: dim1, dim2: dim2, dim3: dim3, dim4: dim4,
            maximizeCount: maximizeCount,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["dim1"]["mode"]  == "normal"
    assert out["dim1"]["w"]     == "1080px"
    assert out["dim2"]["mode"]  == "maxed"
    assert out["dim2"]["w"]     == "95%"
    assert out["dim2"]["h"]     == "92%"
    assert out["dim3"]["mode"]  == "maxed"            # no-op confirmed
    assert out["dim4"]["mode"]  == "normal"
    assert out["dim4"]["w"]     == "1080px"
    # onMaximize fires exactly twice: true→toggle, true→noop (skipped),
    # false→toggle. So count == 2.
    assert out["maximizeCount"] == 2


def test_runtime_create_handle_setTab_swaps_active_tab():
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var lastTab = null;
        var h = N.createCharacterSheetModal(p, N.TEY_V2_FIXTURE, {
            onTabClick: function(id) { lastTab = id; },
        });
        document.body.appendChild(h.element);

        // Default tab.
        var s0 = h.getState();

        // Switch to GEAR via the handle API.
        h.setTab('GEAR');
        var s1 = h.getState();
        var body1 = h.element.querySelector('[data-current-tab]');

        // Switch to VITALS.
        h.setTab('VITALS');
        var s2 = h.getState();
        var body2 = h.element.querySelector('[data-current-tab]');

        result = {
            s0Tab: s0.currentTab,
            s1Tab: s1.currentTab,
            s2Tab: s2.currentTab,
            body1Tab: body1.getAttribute('data-current-tab'),
            body2Tab: body2.getAttribute('data-current-tab'),
            lastTab: lastTab,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["s0Tab"]    == "SKILLS"
    assert out["s1Tab"]    == "GEAR"
    assert out["s2Tab"]    == "VITALS"
    assert out["body1Tab"] == "GEAR"
    assert out["body2Tab"] == "VITALS"
    assert out["lastTab"]  == "VITALS"


def test_runtime_create_handle_destroy_removes_element_from_dom():
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var h = N.createCharacterSheetModal(p, N.TEY_V2_FIXTURE);
        document.body.appendChild(h.element);

        var modalInDomBefore = !!document.body.querySelector('[data-sheet-mode]');
        var containerInDomBefore = !!document.body.querySelector('[data-sheet-modal-container]');
        h.destroy();
        var modalInDomAfter = !!document.body.querySelector('[data-sheet-mode]');
        var containerInDomAfter = !!document.body.querySelector('[data-sheet-modal-container]');

        result = {
            modalInDomBefore:     modalInDomBefore,
            containerInDomBefore: containerInDomBefore,
            modalInDomAfter:      modalInDomAfter,
            containerInDomAfter:  containerInDomAfter,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["modalInDomBefore"]     is True
    assert out["containerInDomBefore"] is True
    assert out["modalInDomAfter"]      is False
    assert out["containerInDomAfter"]  is False


def test_runtime_create_handle_start_maxed_option():
    """hooks.startMaxed=true initializes the handle in maxed state."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        var h = N.createCharacterSheetModal(p, N.TEY_V2_FIXTURE, {
            startMaxed: true,
            startTab: 'GEAR',
        });
        document.body.appendChild(h.element);
        var s = h.getState();
        var wrap = h.element.querySelector('[data-sheet-modal-wrap]');
        result = {
            maxed:  s.maxed,
            tab:    s.currentTab,
            wrap:   wrap.getAttribute('data-sheet-modal-wrap'),
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["maxed"]  is True
    assert out["tab"]    == "GEAR"
    assert out["wrap"]   == "maxed"


def test_runtime_modal_custom_character_renders():
    """A custom character (not TEY_V2_FIXTURE) should render with its
    own name in the sheet header."""
    setup = _setup_prelude() + r"""
        var N = window.M3Sheet;
        // Clone the fixture; swap the name to something detectable.
        var custom = JSON.parse(JSON.stringify(N.TEY_V2_FIXTURE));
        custom.name = 'KIRA NAS';
        var el = N.buildCharacterSheetModal(p, custom);
        document.body.appendChild(el);
        var sheetEl = el.querySelector('[data-sheet-character]');
        result = {
            sheetCharName: sheetEl.getAttribute('data-sheet-character'),
            hasInHeader:   el.textContent.indexOf('KIRA NAS') >= 0,
            // Should not contain the default fixture name.
            hasDefaultName: el.textContent.indexOf('TEY VOSS') >= 0,
        };
    """
    out = run_with_dom(["static/spa/m3_sheet.js"], setup)
    assert out["sheetCharName"]  == "KIRA NAS"
    assert out["hasInHeader"]    is True
    assert out["hasDefaultName"] is False
