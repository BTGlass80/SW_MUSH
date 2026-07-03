#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tests/e2e/play_onboarding.py — NORMAL-PLAY QA: new-player onboarding chain.

Not adversarial. Plays the intended new-player journey end-to-end through the
REAL web SPA in a headless browser:

  1. new_player() — portal -> chargen wizard (picks the FIRST selectable
     tutorial chain at step6 = republic_soldier) -> login -> live game.
  2. Walks the republic_soldier chain step by step using ONLY player commands
     the way a new player would, reading the on-screen guidance (the TRAINING
     onboarding panel + the #g-objective line + the ground/combat feed) and
     doing what each step asks:
        step 1  Reporting In        -> look, +sheet, talk Major Tarrn
        step 2  Combat Sim Drill    -> attack the two B1 sim droids
        step 3  Receiving Assignment-> +missions, accept chain_<mission>
        step 4  Transit to Coruscant-> talk Pilot CT-7567
        step 5  First Day           -> +factions
     ...then graduation.
  3. After EACH beat: screenshot + dump #ground-feed-col, #combat-feed,
     #g-objective-text, and the onboarding TRAINING panel (#onboard-body) to
     tests/e2e/_play_onboarding/.

Judges EXPERIENCE: does each instruction render clearly? does the step advance
when the player complies (vs strand)? does it reach graduation?

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/play_onboarding.py
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent / "_play_onboarding"

from tests.e2e.breakit_harness import BreakItSession  # noqa: E402

_N = [0]
_MANIFEST: list[str] = []


def _safe_text(page, sel: str) -> str:
    try:
        loc = page.locator(sel)
        if loc.count() == 0:
            return f"<no element {sel}>"
        return loc.first.inner_text()
    except Exception as e:
        return f"<error reading {sel}: {e}>"


def dismiss_overlays(page) -> None:
    """A real player who types `+sheet` / opens a modal must close it before
    typing the next command. The sheet panel + map modal both intercept
    pointer events over the ground command box. Press Escape and, as a JS
    fallback, call the known close fns so the command input is clickable."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
    except Exception:
        pass
    try:
        page.evaluate(
            "() => { try { if (window.closeSheetPanel) closeSheetPanel(); } "
            "catch(e){} try { if (window.closeMapModal) closeMapModal(); } "
            "catch(e){} }"
        )
        page.wait_for_timeout(120)
    except Exception:
        pass


def send(sess, cmd: str, settle_ms: int = 700) -> None:
    """Dismiss any open overlay, then issue a ground command."""
    dismiss_overlays(sess.page)
    sess.send(cmd, settle_ms=settle_ms)


def beat(page, label: str) -> None:
    """Capture a screenshot + the key text panels for one beat."""
    _N[0] += 1
    n = _N[0]
    png = OUT / f"{n:02d}_{label}.png"
    txt = OUT / f"{n:02d}_{label}.txt"
    try:
        page.screenshot(path=str(png), full_page=False)
        _MANIFEST.append(str(png))
    except Exception as e:
        print(f"[play] shot FAILED ({label}): {e}", flush=True)
    try:
        ground = _safe_text(page, "#ground-feed-col")
        combat = _safe_text(page, "#combat-feed")
        objective = _safe_text(page, "#g-objective-text")
        onboard = _safe_text(page, "#onboard-body")
        body = (
            f"=== BEAT {n:02d}: {label} ===\n\n"
            f"--- #g-objective-text (vitals objective line) ---\n{objective}\n\n"
            f"--- #onboard-body (TRAINING panel) ---\n{onboard}\n\n"
            f"--- #combat-feed ---\n{combat}\n\n"
            f"--- #ground-feed-col ---\n{ground}\n"
        )
        txt.write_text(body, encoding="utf-8")
        _MANIFEST.append(str(txt))
    except Exception as e:
        print(f"[play] text dump FAILED ({label}): {e}", flush=True)
    print(f"[play] beat {n:02d} {label}", flush=True)


def onboard_state(page) -> dict:
    """Read the live onboarding panel state the SPA last received, by
    re-deriving it from the rendered panel text. We can't reach the JS var,
    so we parse the STEP x/y header off the panel."""
    txt = _safe_text(page, "#onboard-body")
    state = {"raw": txt, "step": None, "total": None}
    import re
    m = re.search(r"STEP\s+(\d+)\s*/\s*(\d+)", txt)
    if m:
        state["step"] = int(m.group(1))
        state["total"] = int(m.group(2))
    return state


def chain_step_via_status(sess) -> dict:
    """Authoritative read of the active chain step: type `chain status` and
    parse the ground feed. Returns {step, raw}."""
    send(sess, "chain status", settle_ms=600)
    raw = _safe_text(sess.page, "#ground-feed-col")
    import re
    # The status output prints "Step N of M" / "STEP N/M" style text.
    step = None
    for pat in (r"[Ss]tep\s+(\d+)\s+of\s+\d+", r"STEP\s+(\d+)\s*/\s*\d+"):
        m = re.search(pat, raw)
        if m:
            step = int(m.group(1))
            break
    return {"step": step, "raw": raw[-1500:]}


def play(sess: BreakItSession) -> None:
    page = sess.page
    info = sess.new_player()
    print(f"[play] new player: {info}", flush=True)
    page.wait_for_timeout(1200)
    beat(page, "00_in_game_fresh")

    # Make sure the TRAINING panel is visible/expanded (it auto-shows while a
    # chain is active). Read its state.
    st = onboard_state(page)
    print(f"[play] onboarding panel after entry: step={st['step']}/{st['total']}",
          flush=True)

    # ── STEP 1: Reporting In — look, +sheet, talk Major Tarrn ──
    try:
        send(sess, "look", settle_ms=700)
        beat(page, "01_look")
        send(sess, "+sheet", settle_ms=700)
        beat(page, "02_sheet")
        send(sess, "talk Major Tarrn", settle_ms=2500)  # AI dialogue settle
        beat(page, "03_talk_major_tarrn")
    except Exception as e:
        print(f"[play] STEP1 error: {e}", flush=True)

    s1 = chain_step_via_status(sess)
    beat(page, "04_after_step1_status")
    print(f"[play] after step1: chain status step={s1['step']}", flush=True)

    # ── STEP 2: Combat Sim Drill — defeat two B1 sim droids ──
    # A normal player reads the room for droid names. We attack 'droid' /
    # 'b1' and keep swinging until combat resolves, then re-engage the 2nd.
    try:
        send(sess, "look", settle_ms=700)
        beat(page, "05_look_sim_room")
        # Drive combat: keep attacking. The drill droids fight back; a fresh
        # republic_soldier should win, but we cap the swings either way.
        for i in range(60):
            send(sess, "attack droid", settle_ms=900)
            if i in (0, 4, 9, 19, 39):
                beat(page, f"06_combat_swing_{i:02d}")
            cs = chain_step_via_status(sess)
            if cs["step"] is not None and cs["step"] >= 3:
                break
            # If "no one here" / "not in combat" type message, try b1 token.
            gf = _safe_text(page, "#ground-feed-col").lower()
            cf = _safe_text(page, "#combat-feed").lower()
            if ("no one" in gf[-400:] or "don't see" in gf[-400:]
                    or "no target" in cf[-400:]):
                send(sess, "attack b1", settle_ms=900)
        beat(page, "07_after_combat")
    except Exception as e:
        print(f"[play] STEP2 error: {e}", flush=True)

    s2 = chain_step_via_status(sess)
    beat(page, "08_after_step2_status")
    print(f"[play] after step2 combat: chain status step={s2['step']}", flush=True)

    # ── STEP 3: Receiving the Assignment — +missions, accept ──
    try:
        send(sess, "+missions", settle_ms=900)
        beat(page, "09_missions")
        # Accept the chain mission. Board id is chain_<mission_id>.
        send(sess, "accept chain_tutorial_republic_first_deployment",
                  settle_ms=1200)
        beat(page, "10_accept_mission")
    except Exception as e:
        print(f"[play] STEP3 error: {e}", flush=True)

    s3 = chain_step_via_status(sess)
    beat(page, "11_after_step3_status")
    print(f"[play] after step3: chain status step={s3['step']}", flush=True)

    # ── STEP 4: Transit to Coruscant — talk Pilot CT-7567 ──
    try:
        send(sess, "look", settle_ms=700)
        beat(page, "12_look_transport_pad")
        send(sess, "talk Pilot", settle_ms=2500)
        beat(page, "13_talk_pilot")
    except Exception as e:
        print(f"[play] STEP4 error: {e}", flush=True)

    s4 = chain_step_via_status(sess)
    beat(page, "14_after_step4_status")
    print(f"[play] after step4: chain status step={s4['step']}", flush=True)

    # ── STEP 5: First Day on Coruscant — +factions ──
    try:
        send(sess, "look", settle_ms=700)
        beat(page, "15_look_coruscant")
        send(sess, "+factions", settle_ms=1200)
        beat(page, "16_factions")
    except Exception as e:
        print(f"[play] STEP5 error: {e}", flush=True)

    # ── Graduation ──
    page.wait_for_timeout(1500)
    s5 = chain_step_via_status(sess)
    beat(page, "17_after_step5_graduation")
    print(f"[play] after step5: chain status step={s5['step']}", flush=True)

    # Final onboarding panel + look in the drop room.
    send(sess, "look", settle_ms=900)
    beat(page, "18_final_drop_room")

    # Record any browser-layer defects the harness captured.
    defs = [d.as_dict() for d in sess.defects()]
    (OUT / "browser_defects.json").write_text(
        json.dumps(defs, indent=2), encoding="utf-8")
    _MANIFEST.append(str(OUT / "browser_defects.json"))
    print(f"[play] browser-layer defects captured: {len(defs)}", flush=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        try:
            old.unlink()
        except Exception:
            pass
    rc = 0
    try:
        with BreakItSession(headless=True, label="play_onboarding") as sess:
            try:
                play(sess)
            except Exception as e:
                print(f"[play] PLAY ERROR: {type(e).__name__}: {e}", flush=True)
                print(traceback.format_exc(), flush=True)
                try:
                    beat(sess.page, "99_ERROR_STATE")
                except Exception:
                    pass
                rc = 1
    except Exception as e:
        print(f"[play] HARNESS ERROR: {type(e).__name__}: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        rc = 2
    print("\n[play] === MANIFEST ===", flush=True)
    for p in _MANIFEST:
        print(f"  {p}", flush=True)
    print(f"[play] artifacts dir: {OUT}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
