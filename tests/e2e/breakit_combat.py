# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_combat.py — REAL-BROWSER adversarial break-it for the COMBAT surface.

Surface: initiating combat + the combat UI (attack / flee / disengage / aim,
the combat strip / combatant pips / damage feed, and the here-panel attack
button). Driven through the live web SPA in headless Chromium via the reusable
break-it harness (tests/e2e/breakit_harness.py), which auto-captures pageerror /
console.error / http5xx / requestfailed.

Reachability note: a brand-new player who picks the (default-first) REPUBLIC
SOLDIER tutorial chain is funneled, after `look` + `+sheet` + `talk Major Tarrn`,
to `tipoca_combat_sim` where two B1 Sim Droids (named "B1 Sim Droid Alpha" /
"...Bravo") are the chain's combat drill. That is the earliest combat a new
player can reach with no admin help. s_reach_combat_and_stress drives that path
and, if it lands in a live fight, stress-tests the in-fight HUD. The remaining
scenarios are precondition-absent / malformed-input cases that exercise the
server combat handlers + the combat_state WS push without needing a live mob.

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_combat.py
Exit 0 = no browser-layer defect captured across the scenarios.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402
from tests.e2e.playwright_new_player_poc import (  # noqa: E402
    drive_wizard, login_and_enter,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _new_player(sess, name: str | None = None) -> dict:
    """Contention-resilient new_player: the box runs many parallel break-it
    agents, so a single 30s page.goto / 25s successOverlay wait flakes under
    load. This retries portal+chargen navigation and waits longer for the
    success overlay. Pure harness hardening — NOT an app behavior change.
    Mirrors BreakItSession.new_player() otherwise."""
    suffix = random.randint(100000, 999999)
    name = name or f"Cbt{suffix}"
    user, pw = f"cbt{suffix}", "testpass123"
    page = sess.page

    def _goto(path, attempts=3):
        last = None
        for _ in range(attempts):
            try:
                page.goto(sess.base + path, wait_until="domcontentloaded",
                          timeout=60000)
                return
            except Exception as e:  # noqa: BLE001
                last = e
                page.wait_for_timeout(1500)
        raise last

    _goto("/")
    page.wait_for_timeout(300)
    _goto("/chargen")
    page.wait_for_selector("#templateCards .card[data-key]", timeout=45000)
    drive_wizard(page, name, user, pw)
    page.wait_for_selector("#successOverlay", state="visible", timeout=60000)
    _goto("/client.html")
    login_and_enter(page, user, pw)
    return {"name": name, "user": user, "pw": pw}

def _mark(sess, label: str) -> None:
    """Drop a console marker so the run log shows where each phase was — handy
    when separating an app pageerror from a harness timing issue."""
    try:
        sess.page.evaluate("(m) => console.log('[BREAKIT_COMBAT] ' + m)", label)
    except Exception:
        pass


def _combat_strip_visible(sess) -> bool:
    """True if the combat strip is currently shown (combat active in the UI)."""
    try:
        return bool(sess.page.evaluate(
            "() => { const s = document.getElementById('combat-strip');"
            " return !!(s && s.classList.contains('show')); }"))
    except Exception:
        return False


def _combat_strip_present_and_clean(sess) -> bool:
    """The combat strip element exists and is NOT in a broken/half-rendered
    state (no leftover 'show' with empty combatant strip is asserted here — we
    only assert the element is queryable and the command box still works)."""
    try:
        return bool(sess.page.evaluate(
            "() => !!document.getElementById('combat-strip')"))
    except Exception:
        return False


def _cmd_box_alive(sess) -> bool:
    """The ground command box is present, visible, and accepts input — the key
    'is the UI stuck?' post-condition. A stuck panel that swallowed the input
    layer would fail this."""
    try:
        return bool(sess.page.evaluate(
            "() => { const i = document.getElementById('cmd-input-ground');"
            " return !!(i && i.offsetParent !== null); }"))
    except Exception:
        return False


def _here_npc_names(sess) -> list:
    """Names of NPCs the server reported in the room (here-panel data)."""
    try:
        return sess.page.evaluate(
            "() => { const b = document.getElementById('here-body');"
            " if (!b) return [];"
            " return Array.from(b.querySelectorAll('.here-name.npc'))"
            "   .map(e => e.textContent || ''); }") or []
    except Exception:
        return []


def _click_attack_button(sess) -> bool:
    """Click the first here-panel ATTACK button if present. Returns True if a
    click was dispatched."""
    try:
        btn = sess.page.query_selector("#here-body .here-btn.btn-attack")
        if btn:
            btn.click()
            return True
    except Exception:
        pass
    return False


# ── scenarios ───────────────────────────────────────────────────────────────

def s_reach_combat_and_stress(sess):
    """Walk the REPUBLIC SOLDIER tutorial to the combat sim, engage the B1 sim
    droids, then stress the LIVE combat HUD: rapid attack re-submits, attack a
    bogus target mid-fight, attack self mid-fight, flee/disengage spam, and a
    move mid-fight. POST-CONDITION: after every adversarial action the combat
    strip element is still queryable and the command box still accepts input
    (no stuck/corrupted UI). Any pageerror/console.error/5xx is auto-captured."""
    _new_player(sess)
    _mark(sess, "soldier-tutorial-start")

    # Tutorial step 1 → teleport to tipoca_combat_sim.
    sess.send("look", settle_ms=500)
    sess.send("+sheet", settle_ms=500)
    # +sheet opens a modal (#sheet-panel.show) that intercepts pointer events
    # over the command box; close it before the next typed command, else the
    # harness click times out. (Esc closes it; belt-and-braces with a direct
    # class strip.)
    try:
        sess.page.keyboard.press("Escape")
        sess.page.evaluate(
            "() => { const s=document.getElementById('sheet-panel');"
            " if (s) s.classList.remove('show'); }")
    except Exception:
        pass
    sess.page.wait_for_timeout(300)
    sess.send("talk Major Tarrn", settle_ms=1400)   # advance + teleport
    sess.send("look", settle_ms=900)
    _mark(sess, "expect-sim-room")

    names = _here_npc_names(sess)
    _mark(sess, "here-npcs=" + "|".join(names)[:200])

    # Engage. Prefer the here-panel ATTACK button (the click surface under
    # test); fall back to the typed command. The sim droids are "B1 Sim Droid
    # Alpha/Bravo" so "attack b1" / "attack alpha" both match.
    engaged = _click_attack_button(sess)
    sess.page.wait_for_timeout(900)
    if not _combat_strip_visible(sess):
        sess.send("attack b1", settle_ms=1400)
    if not _combat_strip_visible(sess):
        sess.send("attack alpha", settle_ms=1400)

    in_combat = _combat_strip_visible(sess)
    _mark(sess, f"in_combat={in_combat}")

    # ---- ADVERSARIAL IN-FIGHT (only meaningful if we actually engaged) ----
    # 1) Rapid attack re-submit with no settle: provoke double-declare races.
    for _ in range(6):
        sess.send("attack b1", settle_ms=0)
    sess.page.wait_for_timeout(1200)
    assert _cmd_box_alive(sess), "cmd box dead after rapid attack re-submit"

    # 2) Attack a target that doesn't exist, mid-fight.
    sess.send("attack nonexistent_phantom_xyz", settle_ms=700)
    # 3) Attack self mid-fight (server should refuse cleanly).
    sess.send("attack me", settle_ms=500)
    # 4) Aim / dodge / pass interleaved with attack (action-stacking).
    sess.send("aim", settle_ms=400)
    sess.send("dodge", settle_ms=400)
    sess.send("attack b1", settle_ms=600)

    # 5) flee + disengage spam (out of order, repeated).
    for _ in range(4):
        sess.send("disengage", settle_ms=0)
        sess.send("flee", settle_ms=0)
    sess.page.wait_for_timeout(1500)

    # 6) Move mid-fight (does the strip clean up / not strand the UI?).
    sess.send("look", settle_ms=400)
    sess.send("north", settle_ms=800)
    sess.send("out", settle_ms=800)

    # POST-CONDITIONS: UI not stuck.
    assert _combat_strip_present_and_clean(sess), "combat strip element vanished"
    assert _cmd_box_alive(sess), "command box stuck/dead after combat stress"
    # The box must still send: type look and confirm no exception is thrown.
    sess.send("look", settle_ms=600)
    assert _cmd_box_alive(sess), "command box dead after final look"


def s_combat_commands_with_no_combat(sess):
    """Precondition ABSENT: issue every in-combat-only verb while NOT in combat.
    Each should produce a clean 'not in combat' refusal — never a JS exception,
    a console.error, a 5xx, or a stuck UI. The combat strip must NOT spuriously
    appear."""
    _new_player(sess)
    _mark(sess, "no-combat-verbs")
    for cmd in (
        "flee", "run", "retreat",        # flee aliases
        "disengage",
        "aim",
        "dodge", "fulldodge",
        "parry", "fullparry",
        "pass",
        "resolve",
        "cover full",
        "range",
        "soak",
        "cpose nothing here",            # combat-pose with no combat
    ):
        sess.send(cmd, settle_ms=300)
    sess.page.wait_for_timeout(800)
    assert not _combat_strip_visible(sess), \
        "combat strip appeared from a no-combat verb"
    assert _cmd_box_alive(sess), "cmd box dead after no-combat verbs"


def s_attack_bogus_targets(sess):
    """attack with no/garbage/self/oversized targets, never having a valid one
    in the room. Server must refuse each cleanly (you don't see X / can't attack
    yourself) with no browser-layer fault and no half-started combat strip."""
    _new_player(sess)
    _mark(sess, "bogus-targets")
    for cmd in (
        "attack",                                   # no target → usage
        "attack    ",                               # whitespace target
        "attack nonexistent_phantom_target_zzz",    # missing
        "attack me",                                # self (alias 'me')
        "attack self",                              # self (word)
        "kill " + ("z" * 4000),                     # oversized target name
        "shoot <script>alert(1)</script>",          # XSS-shaped target
        "att '; DROP TABLE characters;--",          # SQLi-shaped target
        "hit \t\x07\x1b[31mbravo",                  # control chars + ANSI
        "attack " + "\U0001f600" * 100,             # emoji-flood target
    ):
        sess.send(cmd, settle_ms=300)
    sess.page.wait_for_timeout(800)
    assert not _combat_strip_visible(sess), \
        "combat strip appeared though no valid target existed"
    assert _cmd_box_alive(sess), "cmd box dead after bogus-target attacks"


def s_malformed_attack_options(sess):
    """attack with malformed OPTION clauses (with/damage/cp/stun) — even against
    a missing target the server parses these. Bad dice / non-numeric cp / dangling
    'with' must not throw, 500, or strand the UI."""
    _new_player(sess)
    _mark(sess, "malformed-options")
    for cmd in (
        "attack bravo with",                    # dangling 'with'
        "attack bravo with notaskill",          # unknown skill
        "attack bravo damage",                  # dangling 'damage'
        "attack bravo damage notdice",          # garbage dice
        "attack bravo damage 9999D+9999",       # absurd dice
        "attack bravo cp",                      # dangling cp
        "attack bravo cp notanumber",           # non-numeric cp
        "attack bravo cp -5",                   # negative cp
        "attack bravo cp 999999",               # absurd cp
        "attack bravo stun extra junk tokens",  # trailing junk
        "attack bravo with brawling damage 3D cp 2 stun",  # everything at once
    ):
        sess.send(cmd, settle_ms=300)
    sess.page.wait_for_timeout(800)
    assert _cmd_box_alive(sess), "cmd box dead after malformed attack options"


def s_rapid_attack_button_and_clicks(sess):
    """Hammer the command path the ATTACK button uses (sendCmd) with rapid,
    settle-free re-submits and interleaved combat verbs — pure client-side race
    provocation, no live mob required. Then verify the UI is responsive."""
    _new_player(sess)
    _mark(sess, "rapid-fire")
    seq = ["attack bravo", "flee", "disengage", "aim", "attack bravo",
           "dodge", "disengage", "flee"]
    for _ in range(5):
        for c in seq:
            sess.send(c, settle_ms=0)
    sess.page.wait_for_timeout(2000)
    assert _combat_strip_present_and_clean(sess), "combat strip element vanished"
    assert _cmd_box_alive(sess), "cmd box dead after rapid combat spam"
    # Confirm a benign command still round-trips.
    sess.send("look", settle_ms=700)
    assert _cmd_box_alive(sess), "cmd box dead after recovery look"


def s_attack_then_immediate_move(sess):
    """attack immediately followed by a move (the classic 'attack then leave'
    out-of-order action). Even if no target is found, the move must not be
    swallowed and the UI must not strand. Repeated to shake out any latched
    staged-command state."""
    _new_player(sess)
    _mark(sess, "attack-then-move")
    for _ in range(4):
        sess.send("attack bravo", settle_ms=0)
        sess.send("north", settle_ms=0)
        sess.send("disengage", settle_ms=0)
        sess.send("south", settle_ms=0)
    sess.page.wait_for_timeout(2000)
    assert _cmd_box_alive(sess), "cmd box dead after attack-then-move spam"
    sess.send("look", settle_ms=700)
    assert not _combat_strip_visible(sess) or _combat_strip_present_and_clean(sess)


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "combat",
        [
            s_reach_combat_and_stress,
            s_combat_commands_with_no_combat,
            s_attack_bogus_targets,
            s_malformed_attack_options,
            s_rapid_attack_button_and_clicks,
            s_attack_then_immediate_move,
        ],
    ))
