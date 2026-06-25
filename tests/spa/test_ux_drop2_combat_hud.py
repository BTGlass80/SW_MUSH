"""
test_ux_drop2_combat_hud.py — UX Drop 2 (Combat HUD) client-contract tests.

Verifies the pre-launch Combat-HUD slice from
docs/design/ux_engagement_roadmap_2026-06-23.md "## Combat HUD":

  gap 1 — cover indicator on the pip meta line + initiative ladder rows
  gap 2 — player's own 7-rung wound track (M3CombatTheater.buildYourStatus)
          keyed off wound_level + stun_count, colored via woundColor
  gap 3 — brief hit/wound flash (≤600ms combatPulse), rate-limited per round,
          gated by the combat-hud localStorage toggle, never delays the feed
  gap 5 — round-flow coaching subtitle off phase + waiting_for + your_actions

Two layers, mirroring tests/spa/test_m3_combat_theater.py + the static-parse
style of tests/spa/test_gnd_ux_context_affordances.py:

  · static-parse asserts (cheap, no node) on the client.html wiring + the
    COVER_NAMES mirror + the toggle idiom;
  · jsdom runtime asserts on the module builders AND the extracted client.html
    glue functions (fed a combat_state-shaped fixture under a stub harness).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .spa_dom_harness import run_with_dom, require_node_and_jsdom

REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
THEATER_JS  = REPO_ROOT / "static" / "spa" / "m3_combat_theater.js"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════════
# Static-parse: client.html wiring
# ════════════════════════════════════════════════════════════════════

def test_yourstatus_slot_present():
    assert 'id="combat-yourstatus"' in _html(), "your-status DOM slot missing"


def test_coach_slot_present():
    assert 'id="combat-coach"' in _html(), "coaching subtitle DOM slot missing"


def test_render_functions_defined():
    html = _html()
    for fn in ("renderYourStatus", "renderCombatCoaching", "buildCombatCoaching",
               "applyCombatHitFlash", "coverLabel", "combatHudMode",
               "combatFlashEnabled"):
        assert re.search(r"function\s+" + fn + r"\s*\(", html), f"{fn} not defined"


def test_handle_combat_state_invokes_new_renderers():
    """handleCombatState must call the four new viewer-facing renderers."""
    html = _html()
    start = html.find("function handleCombatState(data)")
    assert start != -1, "handleCombatState not found"
    body = html[start:start + 12000]
    for call in ("renderYourStatus(", "renderCombatCoaching(",
                 "applyCombatHitFlash("):
        assert call in body, f"handleCombatState does not call {call}"


def test_flash_runs_after_feed_render():
    """The hit flash must be applied AFTER renderCombatFeed so the feed row
    is never delayed by the motion (roadmap non-negotiable #3)."""
    html = _html()
    start = html.find("function handleCombatState(data)")
    body = html[start:start + 12000]
    feed_idx = body.find("renderCombatFeed(data.events)")
    flash_idx = body.find("applyCombatHitFlash(data)")
    assert feed_idx != -1 and flash_idx != -1
    assert feed_idx < flash_idx, (
        "applyCombatHitFlash must run AFTER renderCombatFeed (no delayed feed)"
    )


def test_cover_names_mirror_engine():
    """The client COVER_NAMES must mirror engine/combat.py COVER_NAMES
    semantics (1/2 cover at index 2, etc.)."""
    html = _html()
    m = re.search(r"var COVER_NAMES\s*=\s*\[([^\]]*)\]", html)
    assert m, "COVER_NAMES array not defined in client.html"
    arr = m.group(1)
    assert "1/2 COVER" in arr and "3/4 COVER" in arr and "FULL COVER" in arr, (
        "COVER_NAMES must carry the graded cover labels"
    )


def test_combat_hud_toggle_uses_localstorage():
    """combat-hud setting mirrors the fk_clean_mode localStorage idiom."""
    html = _html()
    assert "localStorage.getItem('combat-hud')" in html, (
        "combat-hud toggle must read from localStorage like fk_clean_mode"
    )
    assert "'Off'" in html and "'Flashes-only'" in html and "'Full'" in html, (
        "combat-hud toggle must support Off / Flashes-only / Full"
    )


def test_hit_flash_css_present_and_bounded():
    """The flash class reuses combatPulse but bounded ≤600ms (not infinite)."""
    html = _html()
    assert ".cmb-hit-flash" in html, "hit-flash CSS class missing"
    m = re.search(r"\.cmb-hit-flash\s*\{[^}]*animation:\s*combatPulse\s+0\.5\d*s",
                  html)
    assert m, "hit flash must run combatPulse once at ~0.5s (≤600ms cap)"
    # Reduced-motion guard.
    assert re.search(r"prefers-reduced-motion[^}]*\.cmb-hit-flash", html, re.S) \
        or re.search(r"\.cmb-hit-flash\s*\{\s*animation:\s*none", html), (
        "hit flash must honor prefers-reduced-motion"
    )


def test_no_era_tokens_in_new_blocks():
    """Era cleanness — no Imperial/Empire/Rebel/TIE in the added HUD code."""
    html = _html()
    start = html.find("function renderYourStatus(")
    end = html.find("function _pulseOnce(")
    assert start != -1 and end != -1
    block = html[start:end].lower()
    for tok in ("imperial", "empire", " rebel", " tie "):
        assert tok not in block, f"era-contaminated token {tok!r} in HUD block"


# ════════════════════════════════════════════════════════════════════
# Runtime jsdom — module builders (mirror test_m3_combat_theater.py)
# ════════════════════════════════════════════════════════════════════

SAMPLE_PALETTE = {
    "amber": "#ffc857", "red": "#ff5a4a", "green": "#7ce068", "cyan": "#7ce0d0",
    "ink": "#d6cbb7", "inkBright": "#fff4d6", "inkDim": "#a09584",
    "inkFaint": "#6b6253", "sky": "#2a2418", "skyDeep": "#1a160c",
}


def _palette_prelude() -> str:
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_your_status_uses_woundcolor():
    """buildYourStatus colors the lit pips with the passed woundColor (gap 2:
    'colored via the existing woundColor') instead of flat red."""
    setup = _palette_prelude() + r"""
        var WOUND_RED = '#ff0000';
        var status = {
            name: 'TEY VOSS', wound: 'WOUNDED ×2', woundPen: '−2D',
            woundProgress: '3/6',
            pips: [true, true, true, true, false, false, false],
            chips: ['STUN ×1 (−1D)'],
            woundColor: WOUND_RED,
        };
        var el = window.M3CombatTheater.buildYourStatus(p, status);
        document.body.appendChild(el);
        var pipDivs = el.querySelectorAll('div[style*="flex: 1"]');
        // Lit pips carry the woundColor as background; unlit do not.
        var litWithWoundColor = 0;
        Array.prototype.forEach.call(pipDivs, function(d) {
            if (d.style.background && d.style.background.indexOf('rgb(255, 0, 0)') !== -1) {
                litWithWoundColor++;
            }
        });
        result = {
            pipCount: pipDivs.length,
            litWithWoundColor: litWithWoundColor,
            hasStunChip: el.textContent.indexOf('STUN ×1') !== -1,
            hasProgress: el.textContent.indexOf('3/6') !== -1,
        };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["pipCount"] == 7, "7-rung wound track expected"
    assert out["litWithWoundColor"] == 4, (
        "the 4 lit pips must take the woundColor, not flat red"
    )
    assert out["hasStunChip"], "stun chip must render from the chips array"
    assert out["hasProgress"]


def test_runtime_your_status_default_unchanged():
    """No woundColor → original red-lit / green-label fixture behavior
    (regression guard for the existing test_m3_combat_theater fixtures)."""
    setup = _palette_prelude() + r"""
        var el = window.M3CombatTheater.buildYourStatus(p);  // default fixture
        document.body.appendChild(el);
        var pipDivs = el.querySelectorAll('div[style*="flex: 1"]');
        result = { pipCount: pipDivs.length,
                   hasWound: el.textContent.indexOf('WOUNDED') !== -1 };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["pipCount"] == 5  # default fixture has 5 pips
    assert out["hasWound"]


def test_runtime_initiative_ladder_cover_label():
    """buildInitiativeLadder renders a cover label when a row carries
    `cover`, and none when absent (gap 1: cover on ladder rows)."""
    setup = _palette_prelude() + r"""
        var order = [
            { init: 12, name: 'TEY', side: 'self', action: 'AIM', cover: '1/2 COVER' },
            { init: 9,  name: 'B1',  side: 'hostile', action: 'Shoot' },
        ];
        var el = window.M3CombatTheater.buildInitiativeLadder(p, order);
        document.body.appendChild(el);
        result = {
            hasCover: el.textContent.indexOf('1/2 COVER') !== -1,
            coverEls: el.querySelectorAll('.init-cover').length,
        };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["hasCover"], "cover label must render on the ladder row"
    assert out["coverEls"] == 1, "exactly one row has cover → one cover label"


# ════════════════════════════════════════════════════════════════════
# Runtime jsdom — client.html glue (extracted under a stub harness)
# ════════════════════════════════════════════════════════════════════

# The pip-render / coaching / flash logic lives in client.html's inline
# <script>, not a module. We extract the self-contained functions by name and
# eval them under jsdom with minimal stubs for the globals they touch
# ($, lastHud, escapeHtml, FK, WOUND_RUNGS, woundRung/woundColor, the toggle
# state, and the M3CombatTheater module).

_CLIENT_FNS = [
    "coverLabel", "combatHudMode", "combatFlashEnabled",
    "buildCombatCoaching", "_joinNames", "renderCombatCoaching",
    "renderYourStatus", "_combatHudPalette", "_viewerCombatant",
    "applyCombatHitFlash", "_viewerDeclaredTargetName", "_findPipByName",
    "_pulseOnce",
]


def _extract_fn(html: str, name: str) -> str:
    """Extract a top-level `function name(...) { ... }` by brace-matching."""
    m = re.search(r"\nfunction\s+" + re.escape(name) + r"\s*\(", html)
    assert m, f"function {name} not found in client.html"
    i = html.index("{", m.start())
    depth = 0
    j = i
    while j < len(html):
        ch = html[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[m.start() + 1:j + 1]
        j += 1
    raise AssertionError(f"unbalanced braces extracting {name}")


def _client_glue_prelude() -> str:
    """Stub globals + the extracted client functions, ready to eval."""
    html = _html()
    # Extract the COVER_NAMES array literal verbatim so the mirror is real.
    m = re.search(r"(var COVER_NAMES\s*=\s*\[[^\]]*\];)", html)
    assert m, "COVER_NAMES literal not found"
    cover_names = m.group(1)

    fns = "\n\n".join(_extract_fn(html, n) for n in _CLIENT_FNS)

    stub = r"""
        // ── Minimal client.html global stubs ─────────────────────────
        function $(id) { return document.getElementById(id); }
        function escapeHtml(s) {
            return String(s == null ? '' : s)
                .replace(/&/g,'&amp;').replace(/</g,'&lt;')
                .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        }
        var FK = {
            padAmber:'#ffc857', padAmberBright:'#ffe3a0', padGreen:'#7ce068',
            padRed:'#ff6e4a', padText:'#d9b472', padTextDim:'#7a5e2e',
            padBezel:'#1e1815', padScreen:'#14200e', padScreenDim:'#0b1408',
            cockAmber:'#ffa640', cockRed:'#ff5a4a', cockGreen:'#7ce068',
            cockCyan:'#6ee8ff', cockText:'#bfd8e4', cockTextDim:'#5a7584',
            cockMetalLight:'#3e4855', cockScreen:'#04141a', cockScreenDim:'#02090d'
        };
        var WOUND_RUNGS = [
            {v:0,label:'HEALTHY',pen:'',sev:'ok'},
            {v:1,label:'STUNNED',pen:'',sev:'warn'},
            {v:2,label:'WOUNDED',pen:'-1D',sev:'warn'},
            {v:3,label:'WOUNDED x2',pen:'-2D',sev:'hurt'},
            {v:4,label:'INCAP',pen:'',sev:'crit'},
            {v:5,label:'MORTAL',pen:'',sev:'crit'},
            {v:6,label:'DEAD',pen:'',sev:'dead'}
        ];
        function woundRung(level) {
            for (var i=0;i<WOUND_RUNGS.length;i++) if (WOUND_RUNGS[i].v===level) return WOUND_RUNGS[i];
            return WOUND_RUNGS[0];
        }
        function woundColor(sev, theme) {
            if (sev==='ok') return '#7ce068';
            if (sev==='warn') return '#ffc857';
            if (sev==='hurt') return '#ff6e4a';
            if (sev==='crit') return '#ff6e4a';
            if (sev==='dead') return '#7a5e2e';
            return '#d9b472';
        }
        var lastHud = { character_id: 1 };
        // The SPA module assigns window.M3CombatTheater; in client.html a bare
        // `M3CombatTheater` ref resolves to the window global, but in the
        // harness IIFE scope it doesn't — alias it so the glue can call it.
        var M3CombatTheater = window.M3CombatTheater;
        // Module-level flash rate-limit state (top-level `var`s in client.html;
        // the function extractor only grabs functions, so declare them here).
        var _combatLastRound = null;
        var _combatFlashesThisRound = 0;
        var _COMBAT_FLASH_MAX_PER_ROUND = 3;
        // combat-hud toggle: jsdom's real localStorage throws SecurityError
        // on the opaque about:blank origin (which is exactly why the
        // production combatHudMode() wraps it in try/except). Shadow it with
        // an in-memory shim so the extracted glue + tests can drive the flag.
        var localStorage = (function(){
            var s = {};
            return {
                getItem: function(k){ return (k in s) ? s[k] : null; },
                setItem: function(k,v){ s[k] = String(v); },
                removeItem: function(k){ delete s[k]; },
            };
        })();
    """

    # Mount the DOM scaffold the renderers write into.
    scaffold = r"""
        document.body.innerHTML =
          '<div id="combat-yourstatus" style="display:none"></div>' +
          '<div id="combat-coach" style="display:none"></div>' +
          '<div id="combatant-strip"></div>';
    """
    return ("\n".join([cover_names, stub, fns, scaffold]))


def test_runtime_cover_label_mirror():
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        result = {
            none: coverLabel(0),
            half: coverLabel(2),
            full: coverLabel(4),
            bad:  coverLabel(99),
        };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["none"] == "", "cover 0 renders no label"
    assert out["half"] == "1/2 COVER"
    assert out["full"] == "FULL COVER"
    assert out["bad"] == ""


def test_runtime_coaching_reflects_waiting_for():
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        var data = {
            active: true, round: 2, phase: 'declaration',
            your_actions: ['attack B1 with blaster'],
            waiting_for: ['Jane', 'Throk'],
            combatants: [{ id: 1, name: 'You', wound_level: 0, cover: 0 }],
        };
        renderCombatCoaching(data);
        var el = $('combat-coach');
        result = {
            text: el.textContent,
            shown: el.style.display !== 'none',
            // Empty / no-phase → hidden.
            emptyHidden: (function(){
                renderCombatCoaching({ phase: '', waiting_for: [], your_actions: [] });
                return $('combat-coach').style.display === 'none';
            })(),
        };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["shown"], "coaching subtitle must render when there's something to say"
    assert "Jane & Throk" in out["text"], (
        "coaching must name who we're waiting for: " + out["text"]
    )
    assert "declared" in out["text"].lower()
    assert out["emptyHidden"], "coaching renders zero DOM (hidden) when empty"


def test_runtime_wound_track_renders_at_rung():
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        var data = {
            active: true, round: 1, phase: 'posing',
            your_actions: [], waiting_for: [],
            combatants: [
                { id: 1, name: 'You', wound_level: 3, stun_count: 1, cover: 0 },
                { id: 2, name: 'B1',  wound_level: 0, stun_count: 0, cover: 2 },
            ],
        };
        renderYourStatus(data, 'ground');
        var slot = $('combat-yourstatus');
        var pipDivs = slot.querySelectorAll('div[style*="flex: 1"]');
        var litCount = 0;
        Array.prototype.forEach.call(pipDivs, function(d){
            // Lit = a non-rgba(0,0,0,...) background (the woundColor hex).
            if (d.style.background && d.style.background.indexOf('rgba(0, 0, 0') === -1) litCount++;
        });
        result = {
            shown: slot.style.display !== 'none',
            pipCount: pipDivs.length,
            litCount: litCount,
            hasWoundWord: slot.textContent.indexOf('WOUNDED') !== -1,
            hasStunChip: slot.textContent.indexOf('STUN') !== -1,
        };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["shown"], "your-status slot must show when you're a combatant"
    assert out["pipCount"] == 7, "7-rung wound track"
    # wound_level 3 → rungs 0..3 lit = 4 pips.
    assert out["litCount"] == 4, "track fills to rung 3 (4 pips lit)"
    assert out["hasWoundWord"], "wound level word must render"
    assert out["hasStunChip"], "stun_count=1 → a STUN chip"


def test_runtime_yourstatus_hidden_when_not_combatant():
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        var data = {
            active: true, round: 1, phase: 'posing',
            combatants: [{ id: 2, name: 'B1', wound_level: 0, cover: 0 }],
        };
        renderYourStatus(data, 'ground');
        result = { shown: $('combat-yourstatus').style.display !== 'none' };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert not out["shown"], "no your-status card when viewer isn't in the fight"


def test_runtime_hit_flash_targets_you_and_feed_present():
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        localStorage.setItem('combat-hud', 'Full');
        // Render pips first (so applyCombatHitFlash can locate them).
        $('combatant-strip').innerHTML =
          '<div class="combatant-pip" data-cid="1">' +
            '<div class="combatant-name">You</div></div>' +
          '<div class="combatant-pip" data-cid="2">' +
            '<div class="combatant-name">B1</div></div>';
        var data = {
            active: true, round: 1, phase: 'resolution',
            your_actions: [], waiting_for: [],
            combatants: [
                { id: 1, name: 'You', wound_level: 2, cover: 0 },
                { id: 2, name: 'B1',  wound_level: 0, cover: 0 },
            ],
            events: [{ attacker: 'B1', target: 'You', result: 'hit',
                       wound: 'Wounded', weapon: 'blaster' }],
        };
        // Show the your-status slot so the flash can pulse it.
        renderYourStatus(data, 'ground');
        applyCombatHitFlash(data);
        var youPip = $('combatant-strip').querySelector('[data-cid="1"]');
        result = {
            youPipFlashed: youPip.classList.contains('cmb-hit-flash'),
            statusFlashed: $('combat-yourstatus').classList.contains('cmb-hit-flash'),
        };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["youPipFlashed"], "a hit on you must flash your pip"
    assert out["statusFlashed"], "a hit on you must flash your wound track"


def test_runtime_hit_flash_targets_your_declared_target():
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        localStorage.setItem('combat-hud', 'Full');
        $('combatant-strip').innerHTML =
          '<div class="combatant-pip" data-cid="1">' +
            '<div class="combatant-name">You</div></div>' +
          '<div class="combatant-pip" data-cid="2">' +
            '<div class="combatant-name">B1</div></div>';
        var data = {
            active: true, round: 1, phase: 'resolution',
            your_actions: ['attack B1 with blaster'], waiting_for: [],
            combatants: [
                { id: 1, name: 'You', wound_level: 0, cover: 0 },
                { id: 2, name: 'B1',  wound_level: 2, cover: 0 },
            ],
            events: [{ attacker: 'You', target: 'B1', result: 'hit',
                       wound: 'Wounded', weapon: 'blaster' }],
        };
        applyCombatHitFlash(data);
        var b1 = $('combatant-strip').querySelector('[data-cid="2"]');
        result = { b1Flashed: b1.classList.contains('cmb-hit-flash') };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["b1Flashed"], "a hit on your declared target flashes its pip"


def test_runtime_hit_flash_off_toggle_suppresses():
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        localStorage.setItem('combat-hud', 'Off');
        $('combatant-strip').innerHTML =
          '<div class="combatant-pip" data-cid="1">' +
            '<div class="combatant-name">You</div></div>';
        var data = {
            active: true, round: 1, phase: 'resolution',
            your_actions: [], waiting_for: [],
            combatants: [{ id: 1, name: 'You', wound_level: 2, cover: 0 }],
            events: [{ attacker: 'B1', target: 'You', result: 'hit',
                       wound: 'Wounded', weapon: 'blaster' }],
        };
        applyCombatHitFlash(data);
        var youPip = $('combatant-strip').querySelector('[data-cid="1"]');
        result = { flashed: youPip.classList.contains('cmb-hit-flash') };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert not out["flashed"], "combat-hud:'Off' must suppress the hit flash"


def test_runtime_hit_flash_ignores_miss_and_others():
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        localStorage.setItem('combat-hud', 'Full');
        $('combatant-strip').innerHTML =
          '<div class="combatant-pip" data-cid="1">' +
            '<div class="combatant-name">You</div></div>';
        var data = {
            active: true, round: 1, phase: 'resolution',
            your_actions: [], waiting_for: [],
            combatants: [{ id: 1, name: 'You', wound_level: 0, cover: 0 }],
            events: [{ attacker: 'B1', target: 'You', result: 'miss',
                       wound: '', weapon: 'blaster' }],
        };
        applyCombatHitFlash(data);
        result = { flashed: $('combatant-strip')
                     .querySelector('[data-cid="1"]')
                     .classList.contains('cmb-hit-flash') };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert not out["flashed"], "a miss on you must NOT flash (hit-only)"


def test_runtime_soaked_hit_does_not_flash():
    """A 'soaked' connection (attack landed, armor absorbed it) is intentionally
    NOT flashed -- the flash is a wound cue and the feed already reads soaked."""
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        localStorage.setItem('combat-hud', 'Full');
        $('combatant-strip').innerHTML =
          '<div class="combatant-pip" data-cid="1"><div class="combatant-name">You</div></div>';
        var data = { active:true, round:1, phase:'resolution', your_actions:[], waiting_for:[],
            combatants:[{id:1,name:'You',wound_level:0,cover:0}],
            events:[{attacker:'B1',target:'You',result:'soaked',wound:'No Damage',weapon:'blaster'}] };
        renderYourStatus(data, 'ground');
        applyCombatHitFlash(data);
        result = { flashed: $('combatant-strip').querySelector('[data-cid="1"]').classList.contains('cmb-hit-flash') };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert not out["flashed"], "a soaked (no-wound) connection must NOT flash"


def test_runtime_hit_flash_scans_non_final_event():
    """A hit on the viewer must flash even when it is NOT the last-resolved
    event of the round (multi-combatant rounds resolve several swings)."""
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        localStorage.setItem('combat-hud', 'Full');
        $('combatant-strip').innerHTML =
          '<div class="combatant-pip" data-cid="1"><div class="combatant-name">You</div></div>' +
          '<div class="combatant-pip" data-cid="2"><div class="combatant-name">B1</div></div>';
        var data = { active:true, round:1, phase:'resolution', your_actions:[], waiting_for:[],
            combatants:[{id:1,name:'You',wound_level:2,cover:0},{id:2,name:'B1',wound_level:1,cover:0}],
            events:[
                {attacker:'B1',target:'You',result:'hit',wound:'Wounded',weapon:'blaster'},
                {attacker:'You',target:'B1',result:'hit',wound:'Stunned',weapon:'rifle'}
            ] };
        renderYourStatus(data, 'ground');
        applyCombatHitFlash(data);
        result = { youFlashed: $('combatant-strip').querySelector('[data-cid="1"]').classList.contains('cmb-hit-flash') };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["youFlashed"], "a non-final hit on you must still flash"


def test_runtime_flash_budget_only_counts_genuine_flashes():
    """A no-op event (target matches but no pip in the DOM + status hidden) must
    NOT consume the per-round flash budget, so a later real hit still flashes."""
    require_node_and_jsdom()
    setup = _client_glue_prelude() + r"""
        localStorage.setItem('combat-hud', 'Full');
        $('combatant-strip').innerHTML = '';   // no pips => no genuine flash
        var data = { active:true, round:1, phase:'resolution', your_actions:[], waiting_for:[],
            combatants:[{id:1,name:'You',wound_level:2,cover:0}],
            events:[{attacker:'B1',target:'You',result:'hit',wound:'Wounded',weapon:'blaster'}] };
        applyCombatHitFlash(data);                       // status slot stays hidden
        var budgetAfterNoop = _combatFlashesThisRound;
        $('combatant-strip').innerHTML =
          '<div class="combatant-pip" data-cid="1"><div class="combatant-name">You</div></div>';
        data.events = [{attacker:'B2',target:'You',result:'hit',wound:'Wounded Twice',weapon:'rifle'}];
        renderYourStatus(data, 'ground');
        applyCombatHitFlash(data);
        result = { budgetAfterNoop: budgetAfterNoop,
                   secondFlashed: $('combatant-strip').querySelector('[data-cid="1"]').classList.contains('cmb-hit-flash') };
    """
    out = run_with_dom([str(THEATER_JS)], setup)
    assert out["budgetAfterNoop"] == 0, "a no-op event must NOT consume the flash budget"
    assert out["secondFlashed"], "a real hit must still flash after a no-op did not eat the budget"
