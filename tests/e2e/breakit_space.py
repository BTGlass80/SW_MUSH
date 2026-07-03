# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_space.py — REAL-BROWSER adversarial break-it for the SPACE surface.

Surface: the space command surface (#cmd-input-space + space mode) and the space
commands (course / scan / deepscan / board / disembark / transponder / order /
salvage / launch / pilot). The skill-gate registry fix
(test_fork_space_skill_registry_2026_06_23) just landed, so the scan/deepscan/
salvage/hyperspace/transponder paths now actually run a perform_skill_check instead
of NO-OPing on a phantom load_default() — which means real result objects flow into
the client render path for the first time. That is exactly the kind of seam a
browser break-it can catch faulting.

What a new player can reach: chargen drops them in a ground room. The SPACE MODE UI
(#cmd-input-space, the FIRE/EVADE/JUMP hardware strip) only appears once the server
pushes space_state.active=true, which requires boarding a docked ship + launching.
Ships are spawned UNOWNED, and `pilot` fails open on an unowned hull, so a new player
CAN in principle board → pilot → launch into space. These scenarios attempt that and,
when the start room has no reachable bay, fall back to break-it'ing the space *command
verbs* from the ground box (every one must degrade gracefully to "You're not aboard a
ship" — never a 5xx, a pageerror, or a silent freeze) plus force-render the space-mode
UI directly to shake out render faults.

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_space.py
Exit 0 = no browser-layer defect captured. Any pageerror / console.error / http5xx /
requestfailed is a real finding the happy-path PoC would never surface.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402


# ── helpers (page-level; the harness only wires the GROUND box) ──────────────

def _prep(sess) -> None:
    """Bump Playwright's default timeouts before chargen. The box runs 6 server
    boots + Chromium back-to-back; the default 30s nav timeout flakes on the
    /chargen navigation under that load. This is a harness-robustness knob, not a
    change to what we test — every assertion still runs identically."""
    try:
        sess.page.set_default_navigation_timeout(60000)
        sess.page.set_default_timeout(45000)
    except Exception:
        pass


def _new_player_resilient(sess) -> None:
    """new_player() but retried once on a transient navigation/selector timeout
    (load-induced /chargen goto flake), on a fresh page so no half-wizard state
    leaks into the retry."""
    from playwright.sync_api import TimeoutError as PWTimeout
    _prep(sess)
    try:
        sess.new_player()
        return
    except PWTimeout:
        pass
    # Fresh page, retry once.
    try:
        sess.page.close()
    except Exception:
        pass
    sess.page = sess._ctx.new_page()
    for pat in ("**/fonts.googleapis.com/**", "**/fonts.gstatic.com/**"):
        sess.page.route(pat, lambda route: route.abort())
    sess._attach_listeners(sess.page)
    _prep(sess)
    sess.new_player()


def _send_space_box(sess, cmd: str, settle_ms: int = 450) -> None:
    """Type into the SPACE command input (#cmd-input-space) and submit.

    Routes through setMode('space') so the strip is shown the SAME way the server
    drives it (no leftover inline display override that would later intercept the
    ground box). Adversarial: acting on the space input even before/without a real
    launch, a control the normal flow keeps hidden."""
    page = sess.page
    page.evaluate(
        """() => {
            const inp = document.getElementById('cmd-input-space');
            if (!inp) return false;
            // Use the app's own mode switch so display is toggled the canonical
            // way (CSS-driven, no stuck inline style).
            try { if (typeof setMode === 'function') setMode('space'); } catch (e) {}
            return true;
        }"""
    )
    inp = page.locator("#cmd-input-space")
    inp.fill(cmd)
    inp.press("Enter")
    page.wait_for_timeout(settle_ms)


def _board_pilot_launch(sess) -> bool:
    """Best-effort: board a docked ship, take the pilot seat, launch into space.

    Returns True if space_state went active (cmd-input-space surfaced as the live
    input, i.e. the SPA flipped to flight mode). Tolerant of the new player not
    starting at a bay — returns False rather than raising."""
    page = sess.page
    # `board` with no arg lists docked ships; parse the first ship name out of the
    # rendered pose log so we can board it by name.
    sess.send("board", settle_ms=700)
    ship_name = page.evaluate(
        """() => {
            const log = document.getElementById('pose-log');
            if (!log) return null;
            const txt = log.innerText || '';
            // "Ships docked here:" then "    <Name> (<Type>)" lines
            const lines = txt.split('\\n');
            const idx = lines.findIndex(l => /docked here/i.test(l));
            if (idx === -1) return null;
            for (let i = idx + 1; i < lines.length; i++) {
                const m = lines[i].trim();
                if (!m || /usage/i.test(m)) continue;
                // strip a trailing "(Type)" qualifier
                return m.replace(/\\s*\\(.*\\)\\s*$/, '').trim();
            }
            return null;
        }"""
    )
    if not ship_name:
        return False
    sess.send(f"board {ship_name}", settle_ms=900)
    sess.send("pilot", settle_ms=700)
    sess.send("launch", settle_ms=1100)
    # space_state.active flips the live input to #cmd-input-space (setMode('space')).
    active = page.evaluate(
        "() => { try { return !!window.inSpaceMode; } catch (e) { return false; } }"
    )
    return bool(active)


# ── scenarios ───────────────────────────────────────────────────────────────

def s_space_verbs_without_a_ship(sess):
    """Every space verb fired by a player who is NOT aboard a ship must degrade
    to a clean refusal — no uncaught exception, no console.error, no 5xx, no
    silent freeze of the command box. This hits the skill-gated handlers
    (scan/deepscan/salvage/transponder) that the registry fix just made *run*."""
    _new_player_resilient(sess)
    for cmd in (
        "scan",
        "deepscan",
        "deepscan 3",
        "course",
        "course Outer Rim",
        "course anomaly 7",      # anomaly branch runs BEFORE the aboard check
        "course cancel",
        "salvage",
        "disembark",             # not aboard
        "transponder",
        "transponder reset",
        "order",
        "order 4",
        "launch",
        "land",
        "hyperspace coruscant",
        "evade",
        "fire",
    ):
        sess.send(cmd, settle_ms=300)
    # Post-condition: the ground command box must still accept input.
    sess.send("look", settle_ms=400)
    ok = sess.page.evaluate(
        "() => { const i=document.getElementById('cmd-input-ground');"
        " return !!i && !i.disabled; }"
    )
    if not ok:
        sess.page.evaluate("() => console.error('BREAKIT: ground input disabled "
                           "after space verbs without a ship')")


def s_boarding_flow_adversarial(sess):
    """The board/disembark flow under junk: board nothing, board a non-existent
    ship, disembark when not aboard, board-twice. None should fault."""
    _new_player_resilient(sess)
    for cmd in (
        "board",                                   # list (maybe empty)
        "board NoSuchShipNameAtAll",               # invalid name
        "board <script>alert(1)</script>",         # injection-shaped name
        "board " + "z" * 4000,                     # oversized name
        "disembark",                               # not aboard
        "deboard",                                 # alias, not aboard
        "boardship",                               # PvP board verb, no target
        "board ; DROP TABLE ships;--",             # SQLi-shaped
    ):
        sess.send(cmd, settle_ms=350)
    sess.send("look", settle_ms=400)


def s_reach_space_then_break(sess):
    """Try the real path to space (board→pilot→launch); if it lands, throw
    adversarial / out-of-order / boundary commands at the live flight surface.
    If space is unreachable from the start room, this still recorded the boarding
    attempts above; the space-mode UI is force-exercised in a separate scenario."""
    _new_player_resilient(sess)
    reached = _board_pilot_launch(sess)
    # Mark reachability for the human report (console marker is harmless).
    sess.page.evaluate(
        "(r) => console.log('BREAKIT_SPACE_REACHED=' + r)", reached
    )
    if not reached:
        # Still adversarial: fire space verbs from wherever we are. Each must be
        # a clean refusal, never a crash.
        for cmd in ("scan", "course Tatooine", "order 99", "salvage", "disembark"):
            sess.send(cmd, settle_ms=300)
        return
    # In flight: boundary + out-of-order + malformed via the SPACE box.
    for cmd in (
        "scan",
        "deepscan",
        "deepscan 999999999",          # absurd anomaly id
        "deepscan -1",                 # negative id
        "course",
        "course NotAnAdjacentZone",    # invalid destination
        "course anomaly notanumber",   # non-numeric anomaly id
        "course anomaly 0",
        "order 0",                     # boundary (orders are 1-8)
        "order 9",                     # boundary high
        "order 99999",                 # out of range
        "order notanumber",
        "transponder false",           # 'false' with NO alias arg
        "salvage",                     # nothing to salvage here
        "hyperspace",                  # no destination
        "hyperspace notaplace",        # bogus destination
    ):
        _send_space_box(sess, cmd, settle_ms=350)
    # Land + disembark to exercise the teardown path too.
    _send_space_box(sess, "land", settle_ms=900)
    sess.send("disembark", settle_ms=600)
    sess.send("look", settle_ms=400)


def s_malformed_space_input(sess):
    """Oversized / injection / control-char / emoji input aimed at the space
    verbs. None should produce a pageerror, console.error, or 5xx."""
    _new_player_resilient(sess)
    for junk in (
        "scan " + "x" * 6000,                       # oversized arg
        "course <script>alert('x')</script>",       # XSS-shaped destination
        "course '; DROP TABLE ships;--",            # SQLi-shaped
        "deepscan \t\x07\x1b[31m",                   # tab + bell + ANSI escape
        "order " + "9" * 400,                       # giant number
        "transponder false " + "\U0001f680" * 200,  # emoji flood alias
        "salvage \x00\x01\x02",                      # raw control bytes
        "course anomaly 999999999999999999999999",  # int overflow-shaped id
    ):
        sess.send(junk, settle_ms=300)
    sess.send("look", settle_ms=400)


def s_force_space_mode_ui(sess):
    """Force-render the space-mode cockpit UI (setMode('space')) without a real
    launch, then drive the hardware controls (FIRE, EVADE/SHLD/BOOST/JUMP/DISENG
    switches) and the space input. Acting on these controls with no ship/combat
    must not throw, must not 5xx, and must leave the command box usable. Then flip
    back to ground and confirm the ground UI is intact."""
    _new_player_resilient(sess)
    page = sess.page
    # Flip the SPA into space mode directly (the server normally drives this).
    page.evaluate("() => { try { setMode('space'); } catch (e) {"
                  " console.error('BREAKIT: setMode(space) threw: ' + e); } }")
    page.wait_for_timeout(500)
    # Click every hardware control on the space strip — staging-only, but the
    # click handlers run regardless of whether a ship is present.
    for sel in (
        "#fire-btn",
        '.switch[data-switch="EVADE"]',
        '.switch[data-switch="SHLDF"]',
        '.switch[data-switch="BOOST"]',
        '.switch[data-switch="JUMP"]',
        '.switch[data-switch="DISENGAGE"]',
    ):
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.click(timeout=2000)
            except Exception:
                pass
            page.wait_for_timeout(120)
    # Drive a few commands through the SPACE box itself.
    for cmd in ("scan", "course", "fire", "disengage", "x" * 3000):
        _send_space_box(sess, cmd, settle_ms=300)
    # Flip back to ground.
    page.evaluate("() => { try { setMode('ground'); } catch (e) {"
                  " console.error('BREAKIT: setMode(ground) threw: ' + e); } }")
    page.wait_for_timeout(400)
    # Post-condition: after the space->ground round trip the GROUND command box
    # must be the live, clickable input — not occluded by a stale space-strip
    # overlay still intercepting pointer events (real stuck-overlay bug class).
    diag = page.evaluate(
        """() => {
            const i = document.getElementById('cmd-input-ground');
            if (!i) return {ok:false, why:'no ground input'};
            if (i.disabled) return {ok:false, why:'ground input disabled'};
            if (i.offsetParent === null) return {ok:false, why:'ground input not displayed'};
            const r = i.getBoundingClientRect();
            const top = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
            // whatever is on top at the ground input's center must BE the ground
            // input (or a descendant) -- not the space strip.
            const onSpaceStrip = top && top.closest && top.closest('#space-strip');
            if (onSpaceStrip) return {ok:false, why:'space-strip intercepts ground input'};
            return {ok:true, why:''};
        }"""
    )
    if not diag.get("ok"):
        page.evaluate("(w) => console.error('BREAKIT: ground box unusable after "
                      "space round trip: ' + w)", diag.get("why"))
    # And it actually accepts a command.
    sess.send("look", settle_ms=400)


def s_rapid_out_of_order_space(sess):
    """Fire space verbs rapid-fire with no settle to provoke client-side races,
    double-submit, or dropped-frame handling in the space render path."""
    _new_player_resilient(sess)
    burst = ["scan", "course", "deepscan", "order", "transponder",
             "salvage", "launch", "land", "disembark"]
    for _ in range(3):
        for cmd in burst:
            sess.send(cmd, settle_ms=0)
    sess.page.wait_for_timeout(2000)
    sess.send("look", settle_ms=500)


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "space",
        [
            s_space_verbs_without_a_ship,
            s_boarding_flow_adversarial,
            s_reach_space_then_break,
            s_malformed_space_input,
            s_force_space_mode_ui,
            s_rapid_out_of_order_space,
        ],
    ))
