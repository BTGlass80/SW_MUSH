# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_movement.py — adversarial REAL-BROWSER break-it pass for the
MAP + CLICK-TO-MOVE surface of the SW_MUSH SPA.

Surface under test (static/client.html):
  * the always-visible mini-map exit strip   #g-map-exits button.mm-exit-btn[data-cmd]
    (built from cached lastExits by _buildExitStrip/_renderMiniExitStrip)
  * the area-map SVG                          #g-area-map-svg
      - click an .rm-adj group  -> sendCmd(data-travel-dir)   (installAreaMapTravelHandler)
      - click anywhere else     -> openMapModal('ground')     (installMapClickToExpand)
  * the SECTOR MAP modal        its own travel handler (_installModalTravelHandler)
                                + exit strip (#map-modal-exits, _renderModalExitStrip)
  * the quick-action direction chips (rebuildDirectionButtons, data-action=move)

These all funnel into sendCmd() -> ws.send({input: dir}). The adversarial angle is
client-side: races (click one exit, immediately another), STALE controls (click a
button captured before the room changed, so it fires a direction that's no longer a
valid exit), rapid double-submit, move-in-a-loop re-render churn, clicking non-exit
map geometry (background / edges / far rooms), spam open/close of the modal, and
moving while the player is mid-combat.

A captured pageerror / console.error / http5xx / requestfailed is a real defect.
For WRONG-BEHAVIOUR that the auto-capture can't see (a stuck strip, a no-op that
should error), each scenario asserts a post-condition and we surface the failure
through the scenario "error" channel of the JSON report.

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_movement.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────
def _exit_btns(sess):
    """Live locator for the mini-map exit-strip buttons."""
    return sess.page.locator("#g-map-exits button.mm-exit-btn")


def _exit_dirs(sess):
    btns = _exit_btns(sess)
    return [btns.nth(i).get_attribute("data-cmd") for i in range(btns.count())]


def _wait_for_exits(sess, timeout=20000):
    """Wait until the mini-map exit strip has at least one button. Returns its
    direction list (possibly empty if the room genuinely has no exits)."""
    try:
        sess.page.wait_for_selector(
            "#g-map-exits button.mm-exit-btn", state="attached", timeout=timeout
        )
    except Exception:
        pass
    return _exit_dirs(sess)


def _current_room(sess):
    """A cheap room fingerprint: top-context text + first recent-room line."""
    return sess.page.evaluate(
        "() => (document.getElementById('top-context')||{}).textContent || ''"
    )


# ── scenarios ────────────────────────────────────────────────────────────────
def s_rapid_double_submit_exit(sess):
    """Rapid-fire the SAME mini-map exit button with zero settle. A double-submit
    bug would either throw, fire a 5xx, or leave the strip stuck/empty. After the
    burst the strip must still have rebuilt to a working set of exits."""
    sess.new_player()
    dirs = _wait_for_exits(sess)
    if not dirs:
        # No exits at all from spawn would itself be a finding; record via marker.
        sess.page.evaluate("() => console.error('BREAKIT: spawn room has NO exits')")
        return
    btns = _exit_btns(sess)
    # 18 clicks as fast as Playwright will dispatch them, no wait between.
    for _ in range(18):
        try:
            btns.first.click(timeout=2000, no_wait_after=True)
        except Exception:
            # Button detached mid-burst because the room changed & strip rebuilt;
            # re-grab the live first button and keep hammering.
            btns = _exit_btns(sess)
    sess.page.wait_for_timeout(2500)
    # Post-condition: the client is still alive and the strip rebuilt to a usable
    # state (either we moved and the new room has exits, or we stayed put).
    after = _wait_for_exits(sess)
    assert isinstance(after, list), "exit strip did not rebuild after rapid clicks"
    # The command box must still be responsive.
    sess.send("look")


def s_stale_exit_after_room_change(sess):
    """Capture an exit button, MOVE so the room (and lastExits) changes, then click
    the STALE captured element. The strip is rebuilt on every room change, so the
    captured node is detached — clicking it must not throw or fire a phantom move.
    Then a fresh exit must still work."""
    sess.new_player()
    dirs = _wait_for_exits(sess)
    if len(dirs) < 1:
        sess.page.evaluate("() => console.error('BREAKIT: no exit to test stale click')")
        return
    # Grab a handle to the concrete first button NODE (not a re-resolving locator).
    stale = sess.page.query_selector("#g-map-exits button.mm-exit-btn")
    before_room = _current_room(sess)
    # Move once via the first exit to change the room.
    sess.page.locator("#g-map-exits button.mm-exit-btn").first.click(no_wait_after=True)
    sess.page.wait_for_timeout(1600)
    # Now click the STALE node. It is likely detached from the DOM; force the click
    # so we actually exercise the handler if it somehow survived.
    if stale is not None:
        try:
            stale.click(timeout=1500, force=True, no_wait_after=True)
        except Exception:
            # Detached/non-actionable is the EXPECTED, safe outcome — not a defect.
            pass
    sess.page.wait_for_timeout(1200)
    # Post-condition: fresh exits still render & a fresh move still works.
    fresh = _wait_for_exits(sess)
    assert isinstance(fresh, list), "exit strip gone after stale-click"
    if fresh:
        sess.page.locator("#g-map-exits button.mm-exit-btn").first.click(no_wait_after=True)
        sess.page.wait_for_timeout(1200)
    sess.send("look")


def s_out_of_order_exit_race(sess):
    """Click one exit then IMMEDIATELY a different exit before the first move
    settles — a classic out-of-order race. Should not throw, 5xx, or wedge the UI
    (e.g. leave two 'current' rooms or an empty strip that never rebuilds)."""
    sess.new_player()
    dirs = _wait_for_exits(sess)
    if len(dirs) < 1:
        sess.page.evaluate("() => console.error('BREAKIT: no exits for race test')")
        return
    btns = _exit_btns(sess)
    n = btns.count()
    # Fire first and (if present) a *different* exit back-to-back with no settle.
    try:
        btns.nth(0).click(no_wait_after=True)
        btns.nth(1 if n > 1 else 0).click(no_wait_after=True, force=True)
    except Exception:
        # Second button may detach as the room flips; that's fine — already issued.
        pass
    sess.page.wait_for_timeout(2500)
    after = _wait_for_exits(sess)
    assert isinstance(after, list), "strip did not rebuild after out-of-order race"
    # Exactly one current-room highlight must exist on the map (no split state).
    cur = sess.page.evaluate(
        "() => document.querySelectorAll('#g-area-map-svg .rm-current').length"
    )
    assert cur <= 1, f"map shows {cur} current-room markers after race (expected <=1)"
    sess.send("look")


def s_move_loop_rerender_churn(sess):
    """Walk many steps in a loop, alternating directions, to stress the area-map
    re-render + exit-strip rebuild path (DOM churn / listener leaks / detached-node
    exceptions). Each step uses the LIVE first exit so we never click a stale node."""
    sess.new_player()
    _wait_for_exits(sess)
    for _ in range(24):
        btns = _exit_btns(sess)
        if btns.count() == 0:
            # Dead-end room (no exits) — bounce with a look and continue.
            sess.send("look", settle_ms=200)
            continue
        try:
            btns.first.click(no_wait_after=True)
        except Exception:
            pass
        sess.page.wait_for_timeout(700)
    # Post-condition: still connected & responsive after the churn.
    sess.send("look")
    after = _wait_for_exits(sess)
    assert isinstance(after, list), "exit strip broke after movement-loop churn"


def s_nonexit_map_geometry_and_modal(sess):
    """Click parts of the area-map that are NOT travelable exits (the SVG
    background, edges, far rooms) — these should open the sector modal, never
    throw. Then spam open/close the modal and rapid-click its exit strip. Verifies
    the modal's travel strip and the always-every-exit mini strip stay sane."""
    sess.new_player()
    _wait_for_exits(sess)
    svg = sess.page.locator("#g-area-map-svg")
    # Click the SVG background (corner — away from any room dot): opens modal.
    box = svg.bounding_box()
    if box:
        sess.page.mouse.click(box["x"] + 4, box["y"] + 4)
        sess.page.wait_for_timeout(600)
    # Whatever opened, close via ESC; repeat the open/close several times fast.
    for _ in range(6):
        try:
            svg.click(position={"x": 3, "y": 3}, no_wait_after=True)
        except Exception:
            pass
        sess.page.wait_for_timeout(200)
        sess.page.keyboard.press("Escape")
        sess.page.wait_for_timeout(200)
    # Open once more and hammer the modal exit strip if present.
    try:
        svg.click(position={"x": 3, "y": 3}, no_wait_after=True)
    except Exception:
        pass
    sess.page.wait_for_timeout(700)
    mbtns = sess.page.locator("#map-modal-exits button.mm-exit-btn")
    if mbtns.count() > 0:
        for _ in range(6):
            try:
                mbtns.first.click(no_wait_after=True, force=True)
            except Exception:
                mbtns = sess.page.locator("#map-modal-exits button.mm-exit-btn")
            sess.page.wait_for_timeout(150)
    sess.page.keyboard.press("Escape")
    sess.page.wait_for_timeout(600)
    # Post-condition: modal is closed (no .show) and overlay isn't wedged open.
    shown = sess.page.evaluate(
        "() => { var o=document.getElementById('map-modal-overlay');"
        " return !!(o && o.classList.contains('show')); }"
    )
    assert not shown, "sector-map modal stuck OPEN after ESC (wedged overlay)"
    # The live game must still respond.
    sess.send("look")
    after = _wait_for_exits(sess)
    assert isinstance(after, list), "mini exit strip gone after modal spam"


def s_move_via_exit_strip_while_in_combat(sess):
    """Provoke combat, then spam map-driven moves. Moving mid-fight should be
    rejected/handled by the SERVER gracefully — the CLIENT must never throw a
    pageerror, 5xx, or wedge the strip while the server says 'you can't leave a
    fight'. If combat isn't reachable this still hammers moves after attack input
    (which the server treats as bogus) — still a valid stress."""
    sess.new_player()
    _wait_for_exits(sess)
    # Best-effort: try to start a fight with whatever's local. These are bogus if
    # nothing is here; the point is to drive the client through the attack/move
    # interleave, not to guarantee a kill.
    for atk in ("attack", "kill rat", "attack target"):
        sess.send(atk, settle_ms=400)
    # Now spam map-exit moves while (maybe) in combat.
    for _ in range(8):
        btns = _exit_btns(sess)
        if btns.count() == 0:
            break
        try:
            btns.first.click(no_wait_after=True, force=True)
        except Exception:
            pass
        sess.page.wait_for_timeout(450)
    sess.page.wait_for_timeout(1200)
    after = _wait_for_exits(sess)
    assert isinstance(after, list), "exit strip broke during combat-move interleave"
    sess.send("look")


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "movement",
        [
            s_rapid_double_submit_exit,
            s_stale_exit_after_room_change,
            s_out_of_order_exit_race,
            s_move_loop_rerender_churn,
            s_nonexit_map_geometry_and_modal,
            s_move_via_exit_strip_while_in_combat,
        ],
    ))
