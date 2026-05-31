"""
test_m3_skill_check.py — Drop 4.11 regression lock for m3_skill_check.js.

Drop 4.11 ports map_v3/skill-check.jsx (669 JSX LOC) into a vanilla-JS
SPA module at static/spa/m3_skill_check.js. This file pins:

  · Module shape (IIFE + window.M3SkillCheck + documented surface).
  · 13 public builders + 3 fixtures/constants + init exported.
  · B3 era cleanness — Mos Eisley / Tatooine references in the
    fixtures; zero Empire/Imperial/Rebel/TIE/X-wing references in
    the data block.
  · Unopposed showcase, opposed showcase, and stacked showcase all
    render correctly.
  · DIFFICULTY_BANDS table matches WEG R&E ceilings (5/10/15/20/25/30).
  · DieMini renders SVG correctly with pip patterns + wild marker.

Pattern parallels tests/spa/test_m3_holonet.py (Drop 4.10).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT          = Path(__file__).resolve().parent.parent.parent
SKILL_CHECK_MODULE = REPO_ROOT / "static" / "spa" / "m3_skill_check.js"
CLIENT_HTML        = REPO_ROOT / "static" / "client.html"

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
}

from .spa_dom_harness import run_with_dom


# ════════════════════════════════════════════════════════════════════
# Static module-shape checks
# ════════════════════════════════════════════════════════════════════

def test_module_file_exists():
    assert SKILL_CHECK_MODULE.exists()


def test_module_is_iife():
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src
    assert "})();" in src


def test_module_exports_namespace():
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    assert "window.M3SkillCheck" in src


def test_module_defines_all_documented_builders():
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    builders = [
        "buildSkillCheckShowcase",
        "buildExampleHeader",
        "buildUnopposedCheck",
        "buildOpposedCheck",
        "buildOpposedSide",
        "buildSceneStrip",
        "buildPoseBlock",
        "buildSystemEffects",
        "buildPoolBlock",
        "buildDiceRowSmall",
        "buildDiffBlock",
        "buildResultCallout",
        "buildDieMini",
    ]
    for b in builders:
        assert "function " + b in src, f"Missing function definition: {b}"
        assert re.search(r"\b" + b + r"\s*:\s*" + b + r"\b", src), (
            f"Missing export entry for {b} in window.M3SkillCheck"
        )


def test_init_function_present_and_exported():
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    assert "function init(" in src
    assert re.search(r"init\s*:\s*init\b", src)


def test_client_html_loads_module_and_calls_init():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_skill_check.js" in src
    assert "M3SkillCheck.init(" in src


# ════════════════════════════════════════════════════════════════════
# Helper — extract a brace/bracket-delimited block by anchors
# ════════════════════════════════════════════════════════════════════

def _extract_block(src: str, start_marker: str) -> str:
    """Find start_marker in src and return the brace/bracket-balanced
    block that follows. Handles both `{...}` and `[...]`."""
    i = src.find(start_marker)
    if i < 0:
        return ""
    open_brace = -1
    opener = None
    for j in range(i, len(src)):
        if src[j] in "{[":
            open_brace = j
            opener = src[j]
            break
    if open_brace < 0:
        return ""
    closer = "}" if opener == "{" else "]"
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


# ════════════════════════════════════════════════════════════════════
# B3 era-cleanness — Tatooine / Mos Eisley CW-stable references
# ════════════════════════════════════════════════════════════════════

def test_unopposed_fixture_mos_eisley_references():
    """SKILL_UNOPPOSED is the Streetwise-in-Chalmun's-Cantina fixture."""
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    block = _extract_block(src, "var SKILL_UNOPPOSED = {")
    assert block, "SKILL_UNOPPOSED block not found"
    assert "Chalmun" in block
    assert "Mos Eisley" in block
    assert "STREETWISE" in block
    assert "TEY VOSS" in block
    # The L5 Tey Voss standardization (May 26 bug-fix sprint) must not
    # regress. The Tundra Vex name is gone for good.
    assert "Tundra Vex" not in block


def test_opposed_fixture_customs_corridor():
    """SKILL_OPPOSED is the Sneak-vs-Search-at-customs fixture."""
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    block = _extract_block(src, "var SKILL_OPPOSED = {")
    assert block, "SKILL_OPPOSED block not found"
    assert "Customs" in block
    assert "SNEAK" in block
    assert "SEARCH" in block
    assert "TEY VOSS" in block


def test_no_era_contamination_in_fixtures():
    """No Empire/Imperial/Rebel/TIE/X-wing references in either fixture
    block. The `_extract_block` scoping excludes module-level comments,
    which are allowed to discuss the era policy."""
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    for marker in ("var SKILL_UNOPPOSED = {", "var SKILL_OPPOSED = {"):
        block = _extract_block(src, marker)
        assert block, f"Block missing for {marker}"
        # These tokens must not appear in the fixture data.
        for tok in ("Empire", "Imperial", "Rebel", "Rebellion",
                    "Stormtrooper", "Vader", "Death Star", "ISB",
                    "X-wing"):
            assert tok not in block, (
                f"B3 regression: '{tok}' present in {marker}"
            )
        # "TIE" is a sub-string of legitimate words ("attacker.actor",
        # 'tier', etc.) — narrow regex with word boundary on at least
        # one side.
        assert not re.search(r"\bTIE/", block), f"B3 regression: 'TIE/' in {marker}"
        assert not re.search(r"\bTIE-", block), f"B3 regression: 'TIE-' in {marker}"


def test_difficulty_bands_table_matches_weg_re():
    """The DIFFICULTY_BANDS table matches the WEG R&E ceilings:
    Very Easy 5, Easy 10, Moderate 15, Difficult 20, Very Diff. 25, Heroic 30."""
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    block = _extract_block(src, "var DIFFICULTY_BANDS = [")
    assert block
    # Six bands, exact labels + values from the source.
    assert "'Very Easy'" in block and "v: 5"  in block
    assert "'Easy'"      in block and "v: 10" in block
    assert "'Moderate'"  in block and "v: 15" in block
    assert "'Difficult'" in block and "v: 20" in block
    assert "'Very Diff.'" in block and "v: 25" in block
    assert "'Heroic'"    in block and "v: 30" in block


# ════════════════════════════════════════════════════════════════════
# Q1 canonical-character note — preserved from source, flagged for
# production swap-in
# ════════════════════════════════════════════════════════════════════

def test_canonical_character_references_preserved_from_source():
    """The JSX source references Wuher (cantina bartender) and Greedo
    (Rodian bounty hunter) — both canonical to Tatooine cantina lore
    and pre-CW. Drop 4.11 preserves these verbatim from the JSX source
    per the source-fidelity policy used in Drops 4.6, 4.7, 4.10. The
    eventual Q1-hardening drop replaces these with original NPCs or
    absence framing."""
    src = SKILL_CHECK_MODULE.read_text(encoding="utf-8")
    block = _extract_block(src, "var SKILL_UNOPPOSED = {")
    assert block
    assert "WUHER" in block, "Source fidelity: Wuher outcome-pose actor removed"
    assert "Greedo" in block, "Source fidelity: Greedo flavor reference removed"
    # Q1 flag: a Q1 hardening drop should replace these with original
    # NPC names (e.g. "TARN" the cantina barkeep, "VEEZO" the Rodian
    # informant) or absence framing. Tracked in HANDOFF §6.


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        result = {
            hasNamespace:           !!N,
            schemaVersion:          N && N.SCHEMA_VERSION,
            hasInit:                typeof N.init === 'function',
            hasShowcase:            typeof N.buildSkillCheckShowcase === 'function',
            hasUnopposed:           typeof N.buildUnopposedCheck === 'function',
            hasOpposed:             typeof N.buildOpposedCheck === 'function',
            hasOpposedSide:         typeof N.buildOpposedSide === 'function',
            hasSceneStrip:          typeof N.buildSceneStrip === 'function',
            hasPoseBlock:           typeof N.buildPoseBlock === 'function',
            hasSystemEffects:       typeof N.buildSystemEffects === 'function',
            hasPoolBlock:           typeof N.buildPoolBlock === 'function',
            hasDiceRowSmall:        typeof N.buildDiceRowSmall === 'function',
            hasDiffBlock:           typeof N.buildDiffBlock === 'function',
            hasResultCallout:       typeof N.buildResultCallout === 'function',
            hasDieMini:             typeof N.buildDieMini === 'function',
            hasUnopposedFixture:    !!(N && N.SKILL_UNOPPOSED),
            hasOpposedFixture:      !!(N && N.SKILL_OPPOSED),
            hasDifficultyBands:     !!(N && N.DIFFICULTY_BANDS),
            difficultyBandCount:    N && N.DIFFICULTY_BANDS && N.DIFFICULTY_BANDS.length,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasNamespace"]            is True
    assert r["schemaVersion"]           == 1
    assert r["hasInit"]                 is True
    assert r["hasShowcase"]             is True
    assert r["hasUnopposed"]            is True
    assert r["hasOpposed"]              is True
    assert r["hasOpposedSide"]          is True
    assert r["hasSceneStrip"]           is True
    assert r["hasPoseBlock"]            is True
    assert r["hasSystemEffects"]        is True
    assert r["hasPoolBlock"]            is True
    assert r["hasDiceRowSmall"]         is True
    assert r["hasDiffBlock"]            is True
    assert r["hasResultCallout"]        is True
    assert r["hasDieMini"]              is True
    assert r["hasUnopposedFixture"]     is True
    assert r["hasOpposedFixture"]       is True
    assert r["hasDifficultyBands"]      is True
    assert r["difficultyBandCount"]     == 6


def test_runtime_showcase_renders_two_examples():
    setup = _setup_prelude() + r"""
        var el = window.M3SkillCheck.buildSkillCheckShowcase(p);
        document.body.appendChild(el);
        var text = document.body.textContent;
        result = {
            tag:               el.tagName,
            hasExample01:      text.indexOf('EXAMPLE \u00b7 01') >= 0,
            hasExample02:      text.indexOf('EXAMPLE \u00b7 02') >= 0,
            hasUnopposedChip:  text.indexOf('UNOPPOSED') >= 0,
            hasOpposedChip:    text.indexOf('OPPOSED') >= 0,
            hasTeyVoss:        text.indexOf('TEY VOSS') >= 0,
            hasStreetwise:     text.indexOf('STREETWISE') >= 0,
            hasSneak:          text.indexOf('SNEAK') >= 0,
            hasSearch:         text.indexOf('SEARCH') >= 0,
            hasRibbonHeader:   text.indexOf('SKILL CHECK RIBBON') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["tag"]              == "DIV"
    assert r["hasExample01"]     is True
    assert r["hasExample02"]     is True
    assert r["hasUnopposedChip"] is True
    assert r["hasOpposedChip"]   is True
    assert r["hasTeyVoss"]       is True
    assert r["hasStreetwise"]    is True
    assert r["hasSneak"]         is True
    assert r["hasSearch"]        is True
    assert r["hasRibbonHeader"]  is True


def test_runtime_unopposed_check_full_render():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildUnopposedCheck(p, N.SKILL_UNOPPOSED);
        document.body.appendChild(el);
        var text = document.body.textContent;
        result = {
            hasScene:        text.indexOf('SCENE') >= 0,
            hasChalmun:      text.indexOf("Chalmun") >= 0,
            hasSetupPose:    text.indexOf('TRIGGERS THE ROLL') >= 0,
            hasOutcomePose:  text.indexOf('RESULT OF THE ROLL') >= 0,
            hasPool:         text.indexOf('POOL') >= 0,
            hasEffective:    text.indexOf('EFFECTIVE') >= 0,
            hasDifficulty:   text.indexOf('DIFFICULTY') >= 0,
            hasTarget:       text.indexOf('TARGET') >= 0,
            hasSum:          text.indexOf('SUM') >= 0,
            hasSuccess:      text.indexOf('SUCCESS') >= 0,
            hasMargin:       text.indexOf('MARGIN') >= 0,
            hasCleanTier:    text.indexOf('CLEAN') >= 0,
            hasSystemFx:     text.indexOf('SYSTEM EFFECTS') >= 0,
            hasWuher:        text.indexOf('WUHER') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasScene"]       is True
    assert r["hasChalmun"]     is True
    assert r["hasSetupPose"]   is True
    assert r["hasOutcomePose"] is True
    assert r["hasPool"]        is True
    assert r["hasEffective"]   is True
    assert r["hasDifficulty"]  is True
    assert r["hasTarget"]      is True
    assert r["hasSum"]         is True
    assert r["hasSuccess"]     is True
    assert r["hasMargin"]      is True
    assert r["hasCleanTier"]   is True
    assert r["hasSystemFx"]    is True
    assert r["hasWuher"]       is True


def test_runtime_opposed_check_full_render():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildOpposedCheck(p, N.SKILL_OPPOSED);
        document.body.appendChild(el);
        var text = document.body.textContent;
        result = {
            hasScene:           text.indexOf('SCENE') >= 0,
            hasSneak:           text.indexOf('SNEAK') >= 0,
            hasSearch:          text.indexOf('SEARCH') >= 0,
            hasStealthLabel:    text.indexOf('STEALTH') >= 0,
            hasDetectionLabel:  text.indexOf('DETECTION') >= 0,
            hasMarginPlus:      text.indexOf('STEALTH +4') >= 0,
            hasAttackerTotal:   text.indexOf('18') >= 0,
            hasDefenderTotal:   text.indexOf('14') >= 0,
            hasCustomsGuard:    text.indexOf('CUSTOMS GUARD') >= 0,
            hasOutcomePose:     text.indexOf('RESULT OF THE ROLL') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasScene"]           is True
    assert r["hasSneak"]           is True
    assert r["hasSearch"]          is True
    assert r["hasStealthLabel"]    is True
    assert r["hasDetectionLabel"]  is True
    assert r["hasMarginPlus"]      is True
    assert r["hasAttackerTotal"]   is True
    assert r["hasDefenderTotal"]   is True
    assert r["hasCustomsGuard"]    is True
    assert r["hasOutcomePose"]     is True


def test_runtime_die_mini_renders_svg():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        // Plain face-4 die, not wild, no explode
        var el1 = N.buildDieMini(p, 4, false, undefined, p.cyan);
        document.body.appendChild(el1);
        var svg1 = el1.querySelector('svg');
        var rect1 = svg1.querySelector('rect');
        var pips1 = svg1.querySelectorAll('circle').length;
        var stars1 = svg1.querySelectorAll('text').length;

        // Wild face-6 with explode-4
        var el2 = N.buildDieMini(p, 6, true, 4, p.amber);
        document.body.appendChild(el2);
        // First svg = the face-6 wild. Should have a text (star).
        var svgs2 = el2.querySelectorAll('svg');

        result = {
            outerTag1:      el1.tagName,
            svg1Tag:        svg1.tagName.toLowerCase(),
            rect1Width:     rect1.getAttribute('width'),
            pipCount4:      pips1,
            wildStar1:      stars1,
            // For wild+explode case: two SVGs (main + exploded child)
            svgsCount2:     svgs2.length,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["outerTag1"]   == "DIV"
    assert r["svg1Tag"]     == "svg"
    assert r["rect1Width"]  == "88"
    assert r["pipCount4"]   == 4  # face-4 has 4 pips
    assert r["wildStar1"]   == 0  # not wild
    assert r["svgsCount2"]  == 2  # main + exploded


def test_runtime_pip_patterns_match_face():
    """Each face value (1-6) renders the right number of pips."""
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var counts = {};
        for (var f = 1; f <= 6; f++) {
            var el = N.buildDieMini(p, f, false, undefined, p.cyan);
            var svg = el.querySelector('svg');
            counts[f] = svg.querySelectorAll('circle').length;
        }
        result = counts;
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["1"] == 1
    assert r["2"] == 2
    assert r["3"] == 3
    assert r["4"] == 4
    assert r["5"] == 5
    assert r["6"] == 6


def test_runtime_scene_strip_renders():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildSceneStrip(p, {
            room: 'Test Room',
            zone: 'Test Zone',
            desc: 'Test description.',
        });
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasScene:    text.indexOf('SCENE') >= 0,
            hasRoom:     text.indexOf('Test Room') >= 0,
            hasZone:     text.indexOf('Test Zone') >= 0,
            hasDesc:     text.indexOf('Test description.') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasScene"]  is True
    assert r["hasRoom"]   is True
    assert r["hasZone"]   is True
    assert r["hasDesc"]   is True


def test_runtime_pose_block_setup_vs_outcome():
    """Setup pose shows TRIGGERS THE ROLL; outcome pose shows
    RESULT OF THE ROLL. Verb is shown when present."""
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var setupEl = N.buildPoseBlock(p, {
            actor: 'TEY VOSS', verb: 'poses', text: 'setup text',
        }, 'setup');
        var outcomeEl = N.buildPoseBlock(p, {
            actor: 'SCENE', verb: '', text: 'outcome text',
        }, 'outcome');
        document.body.appendChild(setupEl);
        document.body.appendChild(outcomeEl);
        result = {
            setupText:   setupEl.textContent,
            outcomeText: outcomeEl.textContent,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert "TEY VOSS"            in r["setupText"]
    assert "poses"               in r["setupText"]
    assert "TRIGGERS THE ROLL"   in r["setupText"]
    assert "setup text"          in r["setupText"]
    assert "SCENE"               in r["outcomeText"]
    assert "RESULT OF THE ROLL"  in r["outcomeText"]
    assert "outcome text"        in r["outcomeText"]


def test_runtime_system_effects_empty_returns_null():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var elNone = N.buildSystemEffects(p, []);
        var elNull = N.buildSystemEffects(p, null);
        var elWith = N.buildSystemEffects(p, ['effect one', 'effect two']);
        document.body.appendChild(elWith);
        result = {
            emptyNull:  elNone === null,
            nullNull:   elNull === null,
            withText:   elWith.textContent,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["emptyNull"]  is True
    assert r["nullNull"]   is True
    assert "SYSTEM EFFECTS" in r["withText"]
    assert "effect one"     in r["withText"]
    assert "effect two"     in r["withText"]


def test_runtime_result_callout_success_with_tier():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildResultCallout(p, true, 8, 'good', 23, 15);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            text: text,
            hasSuccess: text.indexOf('SUCCESS') >= 0,
            hasFailure: text.indexOf('FAILURE') >= 0,
            hasClean:   text.indexOf('CLEAN') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasSuccess"]  is True
    assert r["hasFailure"]  is False
    assert r["hasClean"]    is True
    assert "23 vs 15"       in r["text"]
    assert "MARGIN"         in r["text"]


def test_runtime_result_callout_failure_no_tier():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildResultCallout(p, false, 3, null, 10, 15);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            text: text,
            hasSuccess: text.indexOf('SUCCESS') >= 0,
            hasFailure: text.indexOf('FAILURE') >= 0,
            hasClean:   text.indexOf('CLEAN') >= 0,
            hasSpectacular: text.indexOf('SPECTACULAR') >= 0,
            hasCatastrophic: text.indexOf('CATASTROPHIC') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasFailure"]        is True
    assert r["hasSuccess"]        is False
    # null tier means no tier label
    assert r["hasClean"]          is False
    assert r["hasSpectacular"]    is False
    assert r["hasCatastrophic"]   is False


def test_runtime_diff_block_renders_stack():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildDiffBlock(p, {
            band: 'Moderate',
            stack: [
                { label: 'Base · Moderate', v: 15 },
                { label: 'Crowd suspicious', v: 3 },
                { label: 'Hutt favor',       v: -3, positive: true },
            ],
            total: 15,
        }, 'Moderate', p.cyan);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            text: text,
            hasBand: text.indexOf('MODERATE') >= 0,
            hasTarget: text.indexOf('TARGET') >= 0,
            hasTotal: text.indexOf('15') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasBand"]    is True
    assert r["hasTarget"]  is True
    assert r["hasTotal"]   is True
    assert "Base"          in r["text"]
    assert "Crowd"         in r["text"]
    assert "Hutt favor"    in r["text"]


def test_runtime_pool_block_with_spec():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildPoolBlock(p, {
            name: 'STREETWISE', code: '5D',
            spec: { name: 'Mos Eisley', bonus: '+2D' },
        }, [
            { label: 'Spec · Mos Eisley', code: '+2D', positive: true },
            { label: 'Wounded',           code: '-1D', positive: false },
        ], '6D', p.cyan);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            text: text,
            hasPool: text.indexOf('POOL') >= 0,
            hasSkill: text.indexOf('STREETWISE') >= 0,
            hasSkillCode: text.indexOf('5D') >= 0,
            hasSpec: text.indexOf('Mos Eisley') >= 0,
            hasSpecBonus: text.indexOf('+2D') >= 0,
            hasWounded: text.indexOf('Wounded') >= 0,
            hasEffective: text.indexOf('EFFECTIVE') >= 0,
            hasEffectiveValue: text.indexOf('6D') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasPool"]            is True
    assert r["hasSkill"]           is True
    assert r["hasSkillCode"]       is True
    assert r["hasSpec"]            is True
    assert r["hasSpecBonus"]       is True
    assert r["hasWounded"]         is True
    assert r["hasEffective"]       is True
    assert r["hasEffectiveValue"]  is True


def test_runtime_pool_block_no_spec():
    """Skill without a `spec` field renders without the ↳ row."""
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildPoolBlock(p, {
            name: 'SNEAK', code: '3D+1',
        }, [
            { label: 'Padded armor', code: '+1D', positive: true },
        ], '4D+1', p.amber);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasSkill: text.indexOf('SNEAK') >= 0,
            hasArrow: text.indexOf('\u21b3') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasSkill"]   is True
    assert r["hasArrow"]   is False  # no spec, no ↳ row


def test_runtime_dice_row_small_with_pip_bonus():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildDiceRowSmall(p, [
            {face: 4}, {face: 5}, {face: 6, wild: true, explode: 3},
        ], 1, 19, p.cyan);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            text: text,
            hasDice: text.indexOf('DICE') >= 0,
            hasWild: text.indexOf('WILD') >= 0,
            hasSum: text.indexOf('SUM') >= 0,
            hasTotal: text.indexOf('19') >= 0,
            hasPipBonus: text.indexOf('+1') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasDice"]      is True
    assert r["hasWild"]      is True
    assert r["hasSum"]       is True
    assert r["hasTotal"]     is True
    assert r["hasPipBonus"]  is True


def test_runtime_opposed_side_attacker():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildOpposedSide(p, N.SKILL_OPPOSED.attacker, p.green);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasName:   text.indexOf('TEY VOSS') >= 0,
            hasLabel:  text.indexOf('STEALTH') >= 0,
            hasSkill:  text.indexOf('SNEAK') >= 0,
            hasEff:    text.indexOf('EFF') >= 0,
            hasTotal:  text.indexOf('TOTAL') >= 0,
            hasValue:  text.indexOf('18') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasName"]   is True
    assert r["hasLabel"]  is True
    assert r["hasSkill"]  is True
    assert r["hasEff"]    is True
    assert r["hasTotal"]  is True
    assert r["hasValue"]  is True


def test_runtime_showcase_custom_hooks_override_fixtures():
    """The buildSkillCheckShowcase hooks parameter accepts custom
    unopposed / opposed checks that override the defaults."""
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        // Clone the default and inject a custom marker
        var custom = JSON.parse(JSON.stringify(N.SKILL_UNOPPOSED));
        custom.scene.room = 'CUSTOM ROOM MARKER';
        custom.outcomePose.actor = 'CUSTOM ACTOR';
        var el = N.buildSkillCheckShowcase(p, { unopposed: custom });
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasCustomRoom:   text.indexOf('CUSTOM ROOM MARKER') >= 0,
            hasCustomActor:  text.indexOf('CUSTOM ACTOR') >= 0,
            // The opposed check still uses the default fixture (no override).
            hasCustomsGuard: text.indexOf('CUSTOMS GUARD') >= 0,
            // The default Chalmun reference should NOT be present since we
            // overrode the scene.room field.
            stillHasChalmun: text.indexOf('Chalmun') >= 0,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["hasCustomRoom"]    is True
    assert r["hasCustomActor"]   is True
    assert r["hasCustomsGuard"]  is True
    assert r["stillHasChalmun"]  is False


def test_runtime_showcase_custom_width_height():
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var el = N.buildSkillCheckShowcase(p, { width: 800, height: 600 });
        document.body.appendChild(el);
        result = {
            width:  el.style.width,
            height: el.style.height,
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["width"]   == "800px"
    assert r["height"]  == "600px"


def test_runtime_init_is_idempotent():
    """Calling init() multiple times should not throw or break the
    module. Subsequent calls overwrite the escapeHtml binding."""
    setup = _setup_prelude() + r"""
        var N = window.M3SkillCheck;
        var threw = false;
        try {
            N.init();
            N.init({});
            N.init({ escapeHtml: function(s) { return s; } });
            N.init();
        } catch (e) {
            threw = true;
        }
        // Verify it still renders after multiple inits.
        var el = N.buildUnopposedCheck(p, N.SKILL_UNOPPOSED);
        document.body.appendChild(el);
        result = {
            threw:        threw,
            stillRenders: el.tagName === 'DIV',
        };
    """
    r = run_with_dom([SKILL_CHECK_MODULE], setup)
    assert r["threw"]         is False
    assert r["stillRenders"]  is True
