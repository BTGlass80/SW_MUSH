#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tests/e2e/play_exploration.py — NORMAL-PLAY QA: map navigation + exploration.

Not adversarial. A PLAYER doing the intended thing: read the room + exits, move
via typed exits AND by clicking the mini-map exit strip (#g-map-exits
button.mm-exit-btn) AND via the modal map. Visit several rooms and judge whether
the experience WORKS:

  * Are ALL room exits clickable on the mini strip + modal strip?  (known bug:
    only marker-rendered exits were clickable; street/hub/off-crop exits dead.)
  * Does click-to-move actually MOVE you?
  * Is the map readable + does it update on each move?
  * Any room with exits you cannot reach by click?

After each beat: screenshot + dump #ground-feed-col text to _play_exploration/.

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/play_exploration.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.e2e.breakit_harness import BreakItSession  # noqa: E402

OUT = Path(__file__).resolve().parent / "_play_exploration"
_N = [0]
MANIFEST: list[dict] = []


def beat(sess, label: str, note: str = "") -> dict:
    """Capture a screenshot + the ground feed text + the mini/modal exit state."""
    _N[0] += 1
    n = _N[0]
    rec = {"n": n, "label": label, "note": note}
    page = sess.page
    png = OUT / f"{n:02d}_{label}.png"
    txt = OUT / f"{n:02d}_{label}.txt"
    try:
        page.screenshot(path=str(png), full_page=False)
        rec["png"] = png.name
    except Exception as e:
        rec["png_err"] = str(e)
    # Ground feed prose
    try:
        feed = page.inner_text("#ground-feed-col")
    except Exception as e:
        feed = f"<<inner_text error: {e}>>"
    # Room name / context
    try:
        ctx = page.inner_text("#top-context")
    except Exception:
        ctx = ""
    # Mini exit strip buttons (the always-visible strip)
    try:
        mini = page.eval_on_selector_all(
            "#g-map-exits button.mm-exit-btn",
            "els => els.map(e => ({cmd: e.getAttribute('data-cmd'), "
            "text: e.textContent, visible: e.offsetParent !== null}))")
    except Exception as e:
        mini = [{"err": str(e)}]
    # The server-pushed exit list (lastExits) — note: gets cleared/reassigned on
    # every hud_update, so a snapshot read here often races to []. We instead use
    # the room prose's "Exits:" line as ground truth for what exits the room has.
    try:
        last_exits = page.evaluate("() => (window.lastExits || [])")
    except Exception as e:
        last_exits = [{"err": str(e)}]
    # Parse the most recent "Exits: a (X), b (Y)" line from the ground feed prose.
    prose_dirs: list[str] = []
    try:
        matches = re.findall(r"Exits:\s*([^\n]+)", feed)
        if matches:
            seg = matches[-1]
            for piece in seg.split(","):
                d = piece.strip().split(" ")[0].strip().lower()
                if d and d not in prose_dirs:
                    prose_dirs.append(d)
    except Exception:
        pass
    rec["room"] = ctx
    rec["mini_exit_btns"] = mini
    rec["server_exits"] = last_exits
    rec["prose_exits"] = prose_dirs
    try:
        txt.write_text(
            f"=== BEAT {n}: {label} ===\nNOTE: {note}\nROOM: {ctx}\n\n"
            f"--- server exits (window.lastExits) ---\n"
            f"{json.dumps(last_exits, indent=2)}\n\n"
            f"--- mini exit strip buttons (#g-map-exits) ---\n"
            f"{json.dumps(mini, indent=2)}\n\n"
            f"--- #ground-feed-col text ---\n{feed}\n",
            encoding="utf-8")
        rec["txt"] = txt.name
    except Exception as e:
        rec["txt_err"] = str(e)
    MANIFEST.append(rec)
    print(f"[play] beat {n:02d} {label}: room={ctx!r} "
          f"server_exits={len(last_exits) if isinstance(last_exits, list) else '?'} "
          f"mini_btns={len(mini) if isinstance(mini, list) else '?'}", flush=True)
    return rec


def exit_coverage_check(rec: dict) -> dict | None:
    """Compare the room PROSE's declared exits to the clickable mini buttons.
    Returns a finding dict if any room exit has NO clickable mini button (the
    historical bug: street/hub/off-crop exits rendered but weren't clickable)."""
    prose = rec.get("prose_exits") or []
    mb = rec.get("mini_exit_btns") or []
    if not prose or not isinstance(mb, list):
        return None
    prose_dirs = {str(d).lower() for d in prose}
    btn_dirs = {str(b.get("cmd")).lower() for b in mb
                if isinstance(b, dict) and b.get("cmd") and b.get("visible")}
    missing = sorted(prose_dirs - btn_dirs)
    if missing:
        return {"room": rec.get("room"), "prose_dirs": sorted(prose_dirs),
                "clickable_dirs": sorted(btn_dirs), "missing": missing}
    return None


def click_mini_exit(sess, prefer: str | None = None):
    """Click an exit button on the always-visible mini strip. Returns the dir
    fired, or None. If `prefer` is given and present, clicks that one."""
    page = sess.page
    btns = page.locator("#g-map-exits button.mm-exit-btn")
    cnt = btns.count()
    if cnt == 0:
        return None
    target = btns.first
    fired = target.get_attribute("data-cmd")
    if prefer:
        for i in range(cnt):
            b = btns.nth(i)
            if (b.get_attribute("data-cmd") or "").lower() == prefer.lower():
                target = b
                fired = b.get_attribute("data-cmd")
                break
    target.click()
    page.wait_for_timeout(1100)
    return fired


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        try:
            old.unlink()
        except Exception:
            pass

    coverage_findings: list[dict] = []
    move_log: list[dict] = []
    visited: list[str] = []

    with BreakItSession(headless=True, label="exploration") as sess:
        info = sess.new_player()
        print(f"[play] new player: {info}", flush=True)
        sess.page.wait_for_timeout(800)

        # ── BEAT 1: start room (look) ─────────────────────────────────
        try:
            sess.send("look")
            r = beat(sess, "01_start_room", "fresh new player, typed look")
            visited.append(r.get("room"))
            f = exit_coverage_check(r)
            if f:
                coverage_findings.append({"beat": 1, **f})
        except Exception as e:
            print(f"[play] beat1 err: {e}", flush=True)

        def mini_dirs():
            """Current mini-strip button dirs (the ground truth for clickability)."""
            try:
                return sess.page.eval_on_selector_all(
                    "#g-map-exits button.mm-exit-btn",
                    "els => els.filter(e=>e.offsetParent!==null)"
                    ".map(e => e.getAttribute('data-cmd'))")
            except Exception:
                return []

        def pick_forward(dirs):
            """Pick a forward exit, avoiding immediate backtrack to last room.
            Prefer cardinals; east is the tutorial's forward direction."""
            order = ["east", "north", "south", "northeast", "southeast",
                     "west", "northwest", "southwest", "down", "up"]
            opp = {"east": "west", "west": "east", "north": "south",
                   "south": "north", "up": "down", "down": "up"}
            last_dir = move_log[-1]["dir"].lower() if move_log else None
            back = opp.get(last_dir) if last_dir else None
            cand = [d for d in dirs if d and d.lower() != back]
            cand = cand or [d for d in dirs if d]
            cand.sort(key=lambda d: order.index(d.lower())
                      if d.lower() in order else 99)
            return cand[0] if cand else None

        # ── BEATS 2-4: walk DEEPER via TYPED exits (follow the chain) ──
        for step in range(2, 5):
            try:
                dirs = mini_dirs()
                if not dirs:
                    print(f"[play] no exits to type-walk at step {step}", flush=True)
                    break
                chosen = pick_forward(dirs)
                before_room = MANIFEST[-1].get("room")
                sess.send(chosen)
                r = beat(sess, f"{step:02d}_typed_{chosen}",
                         f"typed exit '{chosen}' (deeper)")
                if r.get("room") and r.get("room") not in visited:
                    visited.append(r.get("room"))
                moved = (r.get("room") != before_room)
                move_log.append({"beat": step, "method": "typed",
                                 "dir": chosen, "from": before_room,
                                 "to": r.get("room"), "moved": moved})
                f = exit_coverage_check(r)
                if f:
                    coverage_findings.append({"beat": step, **f})
            except Exception as e:
                print(f"[play] step {step} err: {e}", flush=True)

        # ── BEATS 5-7: keep walking DEEPER via the MINI-MAP EXIT STRIP ──
        for step in range(5, 8):
            try:
                before_room = MANIFEST[-1].get("room")
                dirs = mini_dirs()
                fwd = pick_forward(dirs)
                if fwd is None:
                    print(f"[play] no mini exit buttons at step {step}", flush=True)
                    beat(sess, f"{step:02d}_mini_noexits",
                         "mini strip had NO clickable buttons")
                    break
                fired = click_mini_exit(sess, prefer=fwd)
                r = beat(sess, f"{step:02d}_mini_click_{fired}",
                         f"clicked mini exit '{fired}' (deeper)")
                if r.get("room") and r.get("room") not in visited:
                    visited.append(r.get("room"))
                moved = (r.get("room") != before_room)
                move_log.append({"beat": step, "method": "mini_click",
                                 "dir": fired, "from": before_room,
                                 "to": r.get("room"), "moved": moved})
                f = exit_coverage_check(r)
                if f:
                    coverage_findings.append({"beat": step, **f})
            except Exception as e:
                print(f"[play] mini step {step} err: {e}", flush=True)

        # ── BEAT 8: open the MODAL sector map ─────────────────────────
        try:
            sess.page.click(".map-expand-btn")  # ⛶ expand
            sess.page.wait_for_timeout(1200)
            r = beat(sess, "08_modal_open", "opened sector map modal (⛶)")
            # Modal exit strip coverage
            try:
                modal_btns = sess.page.eval_on_selector_all(
                    "#map-modal-exits button.mm-exit-btn",
                    "els => els.map(e => ({cmd: e.getAttribute('data-cmd'), "
                    "text: e.textContent, visible: e.offsetParent !== null}))")
            except Exception as e:
                modal_btns = [{"err": str(e)}]
            r["modal_exit_btns"] = modal_btns
            prose = r.get("prose_exits") or []
            prose_dirs = {str(d).lower() for d in prose}
            mbd = {str(b.get("cmd")).lower() for b in modal_btns
                   if isinstance(b, dict) and b.get("cmd") and b.get("visible")}
            missing = sorted(prose_dirs - mbd)
            print(f"[play] MODAL exit strip: prose={sorted(prose_dirs)} "
                  f"buttons={sorted(mbd)} missing={missing}", flush=True)
            if prose_dirs and missing:
                coverage_findings.append(
                    {"beat": 8, "surface": "modal_strip",
                     "room": r.get("room"), "prose_dirs": sorted(prose_dirs),
                     "clickable_dirs": sorted(mbd), "missing": missing})
        except Exception as e:
            print(f"[play] modal open err: {e}", flush=True)

        # ── BEAT 9: MOVE via the MODAL exit strip ─────────────────────
        try:
            before_room = MANIFEST[-1].get("room")
            mbtns = sess.page.locator("#map-modal-exits button.mm-exit-btn")
            if mbtns.count() > 0:
                fired = mbtns.first.get_attribute("data-cmd")
                mbtns.first.click()
                sess.page.wait_for_timeout(1200)
                r = beat(sess, f"09_modal_move_{fired}",
                         f"clicked modal exit strip '{fired}' (modal should close)")
                if r.get("room") and r.get("room") not in visited:
                    visited.append(r.get("room"))
                moved = (r.get("room") != before_room)
                # Did the modal actually CLOSE after the click? (it should)
                try:
                    modal_open = sess.page.evaluate(
                        "() => { const o=document.getElementById('map-modal-overlay');"
                        " return !!(o && o.classList.contains('show')); }")
                except Exception:
                    modal_open = None
                r["modal_still_open_after_click"] = modal_open
                move_log.append({"beat": 9, "method": "modal_strip_click",
                                 "dir": fired, "from": before_room,
                                 "to": r.get("room"), "moved": moved,
                                 "modal_still_open": modal_open})
            else:
                # modal strip empty — try the on-map SVG adjacency click
                print("[play] modal strip empty; trying modal SVG rm-adj click",
                      flush=True)
                adj = sess.page.locator("#map-modal-svg .rm-adj, "
                                        "#map-modal-body .rm-adj")
                if adj.count() > 0:
                    adj.first.click()
                    sess.page.wait_for_timeout(1200)
                beat(sess, "09_modal_move_attempt", "modal strip empty")
        except Exception as e:
            print(f"[play] modal move err: {e}", flush=True)

        # ── BEAT 10: back in live view, final look ────────────────────
        try:
            # ensure modal closed
            try:
                sess.page.keyboard.press("Escape")
                sess.page.wait_for_timeout(400)
            except Exception:
                pass
            sess.send("look")
            r = beat(sess, "10_final_look", "final look after modal navigation")
            f = exit_coverage_check(r)
            if f:
                coverage_findings.append({"beat": 10, **f})
        except Exception as e:
            print(f"[play] final look err: {e}", flush=True)

        browser_defects = [d.as_dict() for d in sess.defects()]

    # ── manifest + summary ────────────────────────────────────────────
    print("\n========== VISITED ROOMS (distinct) ==========", flush=True)
    seen = []
    for v in visited:
        if v and v not in seen:
            seen.append(v)
    for i, v in enumerate(seen, 1):
        print(f"  {i}. {v}", flush=True)
    print(f"  TOTAL DISTINCT: {len(seen)}", flush=True)

    print("\n========== PLAY MANIFEST ==========", flush=True)
    for rec in MANIFEST:
        print(f"  {rec['n']:02d} {rec['label']:30s} "
              f"png={rec.get('png','-'):28s} txt={rec.get('txt','-')}",
              flush=True)
    print("\n========== MOVE LOG ==========", flush=True)
    for m in move_log:
        print(f"  beat {m['beat']:>2} [{m['method']:>16}] dir={m['dir']!r:>10} "
              f"moved={m['moved']}  {m['from']!r} -> {m['to']!r}", flush=True)
    print("\n========== EXIT-COVERAGE FINDINGS ==========", flush=True)
    if coverage_findings:
        for f in coverage_findings:
            print(f"  !! {json.dumps(f)}", flush=True)
    else:
        print("  (none — every server exit had a clickable button)", flush=True)
    print("\n========== BROWSER-LAYER DEFECTS ==========", flush=True)
    if browser_defects:
        for d in browser_defects:
            print(f"  !! {json.dumps(d)}", flush=True)
    else:
        print("  (none)", flush=True)

    summary = {"manifest": MANIFEST, "move_log": move_log,
               "coverage_findings": coverage_findings,
               "browser_defects": browser_defects}
    (OUT / "_summary.json").write_text(json.dumps(summary, indent=2),
                                       encoding="utf-8")
    print(f"\n[play] artifacts in {OUT}", flush=True)
    print(f"[play] summary -> {OUT / '_summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
