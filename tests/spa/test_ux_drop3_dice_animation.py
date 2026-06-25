"""UX Drop 3 — client contract for the animated D6 dice flourish.

jsdom client-contract tests (mirror tests/spa/test_m3_skill_check.py +
spa_dom_harness). Per dice_animation_and_ux_polish_2026-06-22.md §2/§4 the
animation is a parallel flourish that NEVER gates pace/information:

  - a `drama:2` payload mounts an animation overlay showing the REAL dice,
    bounded (fixed-position overlay, hard-capped duration);
  - a `drama:0` (or absent) payload mounts ZERO animation DOM;
  - the Off toggle suppresses it entirely;
  - the result text is the caller's row — renderDiceRoll only mounts the
    overlay and returns it, never touching/blocking the row (asserted by
    feeding a payload and confirming the overlay is independent + the
    function returns synchronously without consuming the row);
  - reduced-motion path: the dice still render (information) but the module
    is reduced-motion aware.

Static-parse companions assert the module is wired into client.html (script
tag, init, parallel fire after the inspector row).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from tests.spa.spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE = REPO_ROOT / "static" / "spa" / "m3_dice_roll.js"
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


# ── A localStorage stub + a fresh document.body mount, prepended so the
#    toggle paths are deterministic regardless of jsdom storage support. ──
def _harness(setup_body: str, mode: str = "minimal", reduced: str = "false") -> dict:
    boot = (
        "(function(){"
        "  var _store = {};"
        "  Object.defineProperty(window, 'localStorage', { configurable: true, value: {"
        "    getItem: function(k){ return Object.prototype.hasOwnProperty.call(_store,k) ? _store[k] : null; },"
        "    setItem: function(k,v){ _store[k] = String(v); },"
        "    removeItem: function(k){ delete _store[k]; }"
        "  }});"
        "  try { window.localStorage.setItem('sw_dice_anim', " + json.dumps(mode) + "); } catch(e){}"
        "  window.matchMedia = function(q){"
        "    return { matches: (String(q).indexOf('reduce') !== -1 ? " + reduced + " : false),"
        "             media: q, addListener: function(){}, removeListener: function(){} };"
        "  };"
        "  if (window.M3DiceRoll) {"
        "    window.M3DiceRoll.init({});"
        "    window.M3DiceRoll._internal._setMount(document.body);"
        "    window.M3DiceRoll._internal._reset();"
        "    window.M3DiceRoll._internal._setNow(function(){ return window.__now || 0; });"
        "    window.__now = 100000;"  # past any rate-limit window from t=0
        "  }"
        "})();\n"
    )
    return run_with_dom([str(MODULE)], boot + setup_body)


def _payload(drama: int, **over) -> dict:
    p = {
        "msg_type": "combat_resolution_event",
        "drama": drama,
        "actor": {"id": 1, "name": "Tey Voss", "kind": "pc"},
        "target": {"id": 2, "name": "Greedo", "kind": "npc"},
        "action": {"skill": "blaster", "is_opposed": False},
        "attacker_pool": {
            "pool_text": "5D+1", "total": 23, "pool_pips": 1,
            "dice": [
                {"value": 4, "source": "skill"},
                {"value": 5, "source": "skill"},
                {"value": 3, "source": "skill"},
                {"value": 13, "source": "skill", "is_wild": True,
                 "exploded": True, "explosion_chain": [6, 6, 1]},
            ],
        },
        "hit": True,
    }
    p.update(over)
    return p


# ════════════════════════════════════════════════════════════════════
# DOM-runtime contract (jsdom)
# ════════════════════════════════════════════════════════════════════

def test_dramatic_payload_mounts_overlay_with_real_dice():
    out = _harness(
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "var dice = document.querySelectorAll('.dice-roll-die');"
        "var wild = document.querySelector('.dice-roll-die.is-wild');"
        "result = {"
        "  mounted: !!el,"
        "  cls: el ? el.className : '',"
        "  overlayCount: document.querySelectorAll('.dice-roll-overlay').length,"
        "  dieCount: dice.length,"
        "  hasWild: !!wild,"
        "  firstDieValue: dice.length ? dice[0].getAttribute('data-value') : null,"
        "  wildValue: wild ? wild.getAttribute('data-value') : null,"
        "};"
    )
    assert out["mounted"] is True
    assert "dice-roll-overlay" in out["cls"]
    assert "tier-2" in out["cls"], "drama 2 → full-tier overlay"
    assert out["overlayCount"] == 1
    # Real dice: 4 dice in the pool (3 normal + 1 wild), the wild marked.
    assert out["dieCount"] == 4
    assert out["hasWild"] is True
    assert out["firstDieValue"] == "4", "shows the REAL first die value"
    assert out["wildValue"] == "13", "shows the REAL exploded wild-die chain total"


def test_non_dramatic_payload_mounts_zero_dom():
    out = _harness(
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(0)) + ");"
        "result = {"
        "  ret: el,"
        "  overlayCount: document.querySelectorAll('.dice-roll-overlay').length,"
        "};"
    )
    assert out["ret"] is None, "drama 0 → renderDiceRoll returns null"
    assert out["overlayCount"] == 0, "drama 0 → zero animation DOM"


def test_absent_drama_field_mounts_zero_dom():
    p = _payload(0)
    del p["drama"]
    out = _harness(
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(p) + ");"
        "result = { ret: el, overlayCount: document.querySelectorAll('.dice-roll-overlay').length };"
    )
    assert out["ret"] is None
    assert out["overlayCount"] == 0


def test_toggle_off_suppresses_even_tier2():
    out = _harness(
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "result = { ret: el, overlayCount: document.querySelectorAll('.dice-roll-overlay').length,"
        "           mode: window.M3DiceRoll.getMode() };",
        mode="off",
    )
    assert out["mode"] == "off"
    assert out["ret"] is None, "toggle Off → no animation"
    assert out["overlayCount"] == 0


def test_minimal_mode_suppresses_tier1():
    # Default 'minimal' animates tier-2 only; a tier-1 flourish is suppressed.
    out = _harness(
        "var d = window.M3DiceRoll.classifyAnimation(" + json.dumps(_payload(1)) + ");"
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(1)) + ");"
        "result = { animate: d.animate, reason: d.reason,"
        "           overlayCount: document.querySelectorAll('.dice-roll-overlay').length };",
        mode="minimal",
    )
    assert out["animate"] is False
    assert out["reason"] == "tier-below-minimal"
    assert out["overlayCount"] == 0


def test_full_mode_animates_tier1():
    out = _harness(
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(1)) + ");"
        "result = { mounted: !!el, cls: el ? el.className : '',"
        "           overlayCount: document.querySelectorAll('.dice-roll-overlay').length };",
        mode="full",
    )
    assert out["mounted"] is True
    assert "tier-1" in out["cls"], "drama 1 in full mode → flourish-tier overlay"
    assert out["overlayCount"] == 1


def test_rate_limit_suppresses_second_animation_in_window():
    out = _harness(
        # First dramatic roll animates; a second one in the same window does not.
        "var a = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "var afterFirst = document.querySelectorAll('.dice-roll-overlay').length;"
        "var b = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "var afterSecond = document.querySelectorAll('.dice-roll-overlay').length;"
        "result = { firstMounted: !!a, secondMounted: !!b,"
        "           afterFirst: afterFirst, afterSecond: afterSecond };"
    )
    assert out["firstMounted"] is True
    assert out["secondMounted"] is False, "a flurry behind the first resolves instantly"
    # Still exactly one overlay (the second never mounted; the first wasn't replaced).
    assert out["afterSecond"] == 1


def test_rate_limit_allows_animation_after_window():
    out = _harness(
        "var a = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "window.__now = window.__now + 5000;"  # advance past RATE_LIMIT_MS
        "var b = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "result = { firstMounted: !!a, secondMounted: !!b,"
        "           overlayCount: document.querySelectorAll('.dice-roll-overlay').length };"
    )
    assert out["firstMounted"] is True
    assert out["secondMounted"] is True, "after the window, a dramatic roll animates again"
    # The new overlay replaced the old one (a dramatic roll never strobes over a prior).
    assert out["overlayCount"] == 1


def test_reduced_motion_probe_true_when_media_matches():
    out = _harness(
        "result = { reduced: window.M3DiceRoll.prefersReducedMotion() };",
        reduced="true",
    )
    assert out["reduced"] is True


def test_reduced_motion_still_renders_dice_information():
    # Reduced-motion suppresses the tumble (CSS), but the dice are information
    # and must still mount so the player sees the real pool.
    out = _harness(
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "result = { mounted: !!el,"
        "           dieCount: document.querySelectorAll('.dice-roll-die').length };",
        reduced="true",
    )
    assert out["mounted"] is True
    assert out["dieCount"] == 4, "reduced-motion still shows the real dice"


def test_renderDiceRoll_does_not_touch_or_require_a_result_row():
    # The animation is parallel-only: renderDiceRoll mounts ONLY the overlay
    # and returns synchronously; it never creates/blocks the combat result
    # row (that's the inspector's job, already on screen). Proven by the
    # body containing only the overlay (no pose/combat row) after the call.
    out = _harness(
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "result = {"
        "  overlayCount: document.querySelectorAll('.dice-roll-overlay').length,"
        "  poseRowCount: document.querySelectorAll('.pose-row, .row-combat-result').length,"
        "};"
    )
    assert out["overlayCount"] == 1
    assert out["poseRowCount"] == 0, "renderDiceRoll never renders the result row"


def test_skip_click_removes_overlay_immediately():
    out = _harness(
        "var el = window.M3DiceRoll.renderDiceRoll(" + json.dumps(_payload(2)) + ");"
        "var before = document.querySelectorAll('.dice-roll-overlay').length;"
        "el.dispatchEvent(new window.Event('click'));"
        "var after = document.querySelectorAll('.dice-roll-overlay').length;"
        "result = { before: before, after: after };"
    )
    assert out["before"] == 1
    assert out["after"] == 0, "any click jumps straight to done (skippable)"


# ════════════════════════════════════════════════════════════════════
# Static wire-in (client.html)
# ════════════════════════════════════════════════════════════════════

def _client_html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


def test_module_script_tag_present():
    assert "/static/spa/m3_dice_roll.js" in _client_html(), (
        "m3_dice_roll.js must be loaded in client.html's SPA script block"
    )


def test_module_initialized():
    html = _client_html()
    assert re.search(r"M3DiceRoll\.init\s*\(", html), (
        "M3DiceRoll.init(...) must be called in client.html"
    )


def test_fired_in_parallel_after_inspector():
    # The dice flourish is fired from handleCombatResolutionEvent AFTER the
    # inspector appends the row — so the outcome text renders first.
    html = _client_html()
    idx = html.find("function handleCombatResolutionEvent(")
    assert idx != -1
    insp = html.find("M3CombatInspector.handleCombatResolutionEvent", idx)
    dice = html.find("M3DiceRoll.renderDiceRoll", idx)
    assert insp != -1, "inspector row render call missing"
    assert dice != -1, "M3DiceRoll.renderDiceRoll not fired from the delegator"
    assert insp < dice, "dice animation must fire AFTER the inspector appends the row"


def test_reduced_motion_css_for_dice_overlay_present():
    html = _client_html()
    # A reduced-motion override that kills the dice tumble must exist.
    assert ".dice-roll-die" in html
    assert re.search(
        r"@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)\s*\{[^@]*?\.dice-roll-die\s*\{[^}]*animation:\s*none",
        html), "a prefers-reduced-motion rule killing the dice tumble must be present"
