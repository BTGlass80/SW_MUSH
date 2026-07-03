#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tests/e2e/play_combat.py — NORMAL-PLAY QA: the combat loop.

Not adversarial. A PLAYER doing the intended thing: a brand-new REPUBLIC SOLDIER
walks the tutorial to the combat sim, engages the B1 sim droids, and fights the
drill to resolution (kill or defeat). The whole point is to READ the combat
output beat by beat and judge:

  * Does the combat FEED (#combat-feed) render attack/damage/round/death as
    READABLE prose / labelled rows — or does it dump raw JSON / garbled text?
  * Does the ground feed (#ground-feed-col) narrate the fight in prose?
  * Does combat PROGRESS round to round (initiative → declare → pose → resolve)?
  * Does it END cleanly (droids defeated, tutorial advances) and return control
    to the player (command box alive, combat strip torn down)?

Reachability: a fresh player who takes the default-first REPUBLIC SOLDIER chain
is funneled — after look + +sheet + talk Major Tarrn — to tipoca_combat_sim with
two "B1 Sim Droid" enemies. That is the earliest combat a new player can reach
with no admin help (documented in breakit_combat.py). If we CANNOT reach a mob,
that itself is a finding (kind=unreachable).

After each beat: screenshot + dump #ground-feed-col, #combat-feed, and
#g-objective-text to _play_combat/.

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/play_combat.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.e2e.breakit_harness import BreakItSession  # noqa: E402

OUT = Path(__file__).resolve().parent / "_play_combat"
_N = [0]
MANIFEST: list[dict] = []


# ── per-beat capture ────────────────────────────────────────────────────────

def beat(sess, label: str, note: str = "") -> dict:
    """Screenshot + dump the player-facing feeds + combat state snapshot."""
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

    def _inner(sel: str) -> str:
        try:
            return page.inner_text(sel)
        except Exception as e:
            return f"<<no {sel}: {e}>>"

    ground = _inner("#ground-feed-col")
    objective = _inner("#g-objective-text")
    # combat-feed is display:none until a fight; inner_text still reads it.
    combat_feed = _inner("#combat-feed")
    try:
        ctx = page.inner_text("#top-context")
    except Exception:
        ctx = ""

    # Live combat-state snapshot straight off the client (the WS push the UI
    # renders from). Lets us judge progression (phase/round) + see if the feed
    # rows the client builds match the server events.
    try:
        cstate = page.evaluate(
            "() => { try { return window.lastCombatStateData || null; }"
            " catch(e){ return {err:String(e)}; } }")
    except Exception as e:
        cstate = {"err": str(e)}
    # Combat strip visible?
    try:
        strip_show = bool(page.evaluate(
            "() => { const s=document.getElementById('combat-strip');"
            " return !!(s && s.classList.contains('show')); }"))
    except Exception:
        strip_show = False
    # Here-panel NPCs (with hostile flag) + their action verbs.
    try:
        here_npcs = page.evaluate(
            "() => { const b=document.getElementById('here-body'); if(!b) return [];"
            " return Array.from(b.querySelectorAll('.here-entry')).map(r => {"
            "   const nm=r.querySelector('.here-name'); "
            "   const acts=Array.from(r.querySelectorAll('.here-btn')).map(x=>x.textContent);"
            "   return {name: nm?nm.textContent:'', hostile: nm?nm.classList.contains('hostile'):false,"
            "           actions: acts}; }); }") or []
    except Exception as e:
        here_npcs = [{"err": str(e)}]
    # Rendered combat-feed rows as the player SEES them (actors + outcome text).
    try:
        feed_rows = page.evaluate(
            "() => { const f=document.getElementById('combat-feed'); if(!f) return [];"
            " return Array.from(f.querySelectorAll('.cf-row')).map(r => ({"
            "   cls: r.className,"
            "   actors: (r.querySelector('.cf-actors')||{}).textContent || '',"
            "   outcome: (r.querySelector('.cf-outcome')||{}).textContent || '' })); }") or []
    except Exception as e:
        feed_rows = [{"err": str(e)}]

    # Combat pose-timer texts (NaN-bug surface): the strip deadline pill
    # (#ch-deadline) and the posing-panel countdown (#cpp-timer).
    try:
        timers = page.evaluate(
            "() => ({ ch_deadline: (document.getElementById('ch-deadline')||{}).textContent || null,"
            "         cpp_timer:   (document.getElementById('cpp-timer')||{}).textContent || null }) ")
    except Exception as e:
        timers = {"err": str(e)}

    rec["room"] = ctx
    rec["strip_show"] = strip_show
    rec["objective"] = objective
    rec["here_npcs"] = here_npcs
    rec["feed_rows"] = feed_rows
    rec["pose_timers"] = timers
    rec["combat_phase"] = (cstate or {}).get("phase") if isinstance(cstate, dict) else None
    rec["combat_round"] = (cstate or {}).get("round") if isinstance(cstate, dict) else None

    try:
        txt.write_text(
            f"=== BEAT {n}: {label} ===\nNOTE: {note}\nROOM: {ctx}\n"
            f"COMBAT STRIP VISIBLE: {strip_show}\n"
            f"COMBAT PHASE/ROUND: {rec['combat_phase']} / {rec['combat_round']}\n\n"
            f"--- #g-objective-text ---\n{objective}\n\n"
            f"--- POSE TIMERS (#ch-deadline / #cpp-timer) ---\n"
            f"{json.dumps(timers, indent=2, ensure_ascii=False)}\n\n"
            f"--- HERE panel npcs ---\n{json.dumps(here_npcs, indent=2, ensure_ascii=False)}\n\n"
            f"--- RENDERED combat-feed rows (.cf-row) ---\n"
            f"{json.dumps(feed_rows, indent=2, ensure_ascii=False)}\n\n"
            f"--- window.lastCombatStateData (raw WS push) ---\n"
            f"{json.dumps(cstate, indent=2, ensure_ascii=False)[:4000]}\n\n"
            f"--- #combat-feed inner_text ---\n{combat_feed}\n\n"
            f"--- #ground-feed-col inner_text ---\n{ground}\n",
            encoding="utf-8")
        rec["txt"] = txt.name
    except Exception as e:
        rec["txt_err"] = str(e)

    MANIFEST.append(rec)
    print(f"[play] beat {n:02d} {label}: room={ctx!r} strip={strip_show} "
          f"phase={rec['combat_phase']} round={rec['combat_round']} "
          f"feed_rows={len(feed_rows) if isinstance(feed_rows, list) else '?'}",
          flush=True)
    return rec


def _strip_visible(sess) -> bool:
    try:
        return bool(sess.page.evaluate(
            "() => { const s=document.getElementById('combat-strip');"
            " return !!(s && s.classList.contains('show')); }"))
    except Exception:
        return False


def _close_sheet(sess) -> None:
    """+sheet opens a modal that intercepts the command box; strip it."""
    try:
        sess.page.keyboard.press("Escape")
        sess.page.evaluate(
            "() => { const s=document.getElementById('sheet-panel');"
            " if (s) s.classList.remove('show'); }")
        sess.page.wait_for_timeout(250)
    except Exception:
        pass


def _here_hostiles(sess) -> list:
    try:
        return sess.page.evaluate(
            "() => { const b=document.getElementById('here-body'); if(!b) return [];"
            " return Array.from(b.querySelectorAll('.here-name.npc'))"
            "   .map(e => e.textContent || ''); }") or []
    except Exception:
        return []


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        try:
            old.unlink()
        except Exception:
            pass

    findings: list[dict] = []
    reached_combat = False
    combat_ended_clean = False

    with BreakItSession(headless=True, label="combat") as sess:
        info = sess.new_player()
        print(f"[play] new player: {info}", flush=True)
        sess.page.wait_for_timeout(900)

        # ── BEAT 1: where did we land? A standalone-chargen new player is
        #    funneled into the "The Arrival" onboarding tutorial: Landing Pad
        #    -> Desert Trail -> Rocky Pass -> Ambush Point -> ... The game
        #    itself tells you to walk EAST. At "Ambush Point" the tutorial
        #    scripts the first fight: "attack raider" (a Sand Raider mob).
        #    That is the earliest combat a fresh web player reaches. ────────
        try:
            sess.send("look", settle_ms=900)
            beat(sess, "01_start_look", "fresh new player, typed look")
        except Exception as e:
            print(f"[play] beat1 err: {e}", flush=True)

        # ── BEAT 2: read your gear (the tutorial nudges +sheet) ──────────
        try:
            sess.send("+sheet", settle_ms=900)
            _close_sheet(sess)
            beat(sess, "02_sheet", "checked gear with +sheet")
        except Exception as e:
            print(f"[play] beat2 err: {e}", flush=True)

        # ── BEATS 3..: WALK EAST toward Mos Eisley, following the tutorial.
        #    The "Arrival" path is Landing Pad → Desert Trail → Rocky Pass →
        #    Ambush Point (scripted Sand Raider fight) → Desert Road → Gate.
        #    A real player reads the room, talks to the guide (Kessa Dray) on
        #    Desert Trail, then keeps going east to the ambush. We do NOT click
        #    Kessa's attack button — she's the friendly guide; only a genuine
        #    HOSTILE (the Sand Raider) is a combat target. Walk until a hostile
        #    appears or exits run out. ──────────────────────────────────────
        def _exit_dirs() -> set:
            """Directions available, read off the rendered mini-map exit strip
            (#g-map-exits buttons) — the DOM is the reliable source; the
            window.lastExits global reads empty intermittently via evaluate."""
            for _ in range(6):
                try:
                    dirs = set(sess.page.eval_on_selector_all(
                        "#g-map-exits button.mm-exit-btn",
                        "els => els.map(e => (e.getAttribute('data-cmd')||'').toLowerCase())") or [])
                    dirs.discard("")
                except Exception:
                    dirs = set()
                if dirs:
                    return dirs
                sess.page.wait_for_timeout(350)
            return set()

        def _go(direction: str) -> None:
            """Move by clicking the mini-map exit button for `direction` (the
            click-to-move surface a real player uses), falling back to typing."""
            try:
                btn = sess.page.query_selector(
                    f"#g-map-exits button.mm-exit-btn[data-cmd='{direction}']")
                if btn:
                    btn.click()
                    sess.page.wait_for_timeout(1300)
                    return
            except Exception:
                pass
            sess.send(direction, settle_ms=1300)

        hostiles: list = []
        target_token = None
        reached_ambush = False
        talked_to_guide = False
        max_hops = 8
        for hop in range(1, max_hops + 1):
            try:
                r = beat(sess, f"{2+hop:02d}_walk_{hop}", f"hop {hop} (read room)")
                room = (r.get("room") or "")
                here = r.get("here_npcs") or []
                all_names = [n.get("name") for n in here if isinstance(n, dict)]
                hostile_here = [n.get("name") for n in here
                                if isinstance(n, dict) and n.get("hostile")]
                hostiles = hostile_here
                print(f"[play] hop {hop}: room={room!r} all_npcs={all_names} "
                      f"hostiles={hostile_here}", flush=True)

                # Found a hostile mob → stop walking, we engage below.
                if hostile_here:
                    nm = hostile_here[0]
                    target_token = "raider" if "raider" in nm.lower() else nm.split()[0]
                    reached_ambush = "ambush" in room.lower()
                    break
                # At Ambush Point even if the HERE push lags → the raider lives
                # here; give it a beat then re-read.
                if "ambush" in room.lower():
                    reached_ambush = True
                    sess.page.wait_for_timeout(800)
                    hostiles = _here_hostiles(sess)
                    target_token = "raider"
                    break

                # Friendly guide on Desert Trail → do the intended thing: talk.
                if not talked_to_guide and any("kessa" in (n or "").lower()
                                               for n in all_names):
                    sess.send("talk kessa", settle_ms=1200)
                    talked_to_guide = True
                    beat(sess, f"{2+hop:02d}b_talk_kessa",
                         "talked to the tutorial guide Kessa Dray (as instructed)")

                # Move east toward the city (the tutorial says 'east').
                dirs = _exit_dirs()
                print(f"[play] hop {hop} exits={dirs}", flush=True)
                if "east" in dirs:
                    _go("east")
                else:
                    # don't backtrack west (whence we came); try another way
                    nxt = next((d for d in ("north", "south", "northeast",
                                            "southeast") if d in dirs), None)
                    if nxt is None and "west" in dirs and hop == 1:
                        nxt = "west"  # only if truly stuck at the start
                    print(f"[play] no east exit at hop {hop}; dirs={dirs} "
                          f"-> trying {nxt}", flush=True)
                    if nxt:
                        _go(nxt)
                    else:
                        break
            except Exception as e:
                print(f"[play] hop {hop} err: {e}", flush=True)

        print(f"[play] reached_ambush={reached_ambush} target_token={target_token} "
              f"hostiles={hostiles}", flush=True)

        # ── ENGAGE the hostile. Prefer the here-panel ATTACK button on the
        #    HOSTILE row (the click surface a real player uses); the tutorial's
        #    own instruction is `attack raider`. Only engage if we actually
        #    found a hostile — never attack the friendly guide. ─────────────
        if target_token:
            try:
                clicked = False
                # Click the attack button only on a HOSTILE here-entry.
                try:
                    clicked = bool(sess.page.evaluate(
                        "() => { const rows=document.querySelectorAll('#here-body .here-entry');"
                        " for (const r of rows) { const nm=r.querySelector('.here-name.hostile');"
                        "   if (nm) { const b=r.querySelector('.here-btn.btn-attack');"
                        "     if (b) { b.click(); return true; } } } return false; }"))
                    if clicked:
                        sess.page.wait_for_timeout(1400)
                except Exception:
                    pass
                if not _strip_visible(sess):
                    sess.send("attack " + target_token, settle_ms=1700)
                if not _strip_visible(sess) and target_token != "raider":
                    sess.send("attack raider", settle_ms=1700)
                reached_combat = _strip_visible(sess)
                beat(sess, "ENGAGE",
                     f"engaged {target_token!r} (hostile attack btn clicked={clicked}); "
                     f"strip={reached_combat}")
                print(f"[play] reached_combat={reached_combat}", flush=True)
            except Exception as e:
                print(f"[play] engage err: {e}", flush=True)
        else:
            beat(sess, "ENGAGE", "no hostile mob found to engage")

        if not reached_combat:
            findings.append({
                "beat": "engage", "kind": "unreachable",
                "detail": "Could not enter combat as a fresh ARRIVAL-tutorial "
                          "player after walking east toward Mos Eisley and "
                          "issuing `attack raider` at Ambush Point. "
                          f"reached_ambush={reached_ambush}, HERE npcs={hostiles!r}",
            })

        # ── BEATS 6..N: FIGHT round by round, AS A PLAYER. The combat is
        #    phased (initiative → declaration → posing → resolution). A real
        #    player declares `attack <target>`, then writes a pose — or types
        #    `pass` to take an auto-generated pose, which closes the posing
        #    window and resolves the round. We loop attack→pass and read the
        #    feed each round. NOTE: we deliberately do NOT use `resolve` — that
        #    is a builder/admin-only force-resolve, not a player verb.
        #    Progression is judged by the ground-feed growing (combat is a
        #    text-feed surface; the lastCombatStateData global is only set on
        #    the posing-panel path, so phase/round telemetry is unreliable). ─
        def _feed_len() -> int:
            try:
                return len(sess.page.inner_text("#ground-feed-col") or "")
            except Exception:
                return 0

        tok = target_token or "raider"
        max_rounds = 14
        prev_feed = -1
        stalled = 0
        for rnd in range(1, max_rounds + 1):
            if not _strip_visible(sess):
                break  # combat ended — capture aftermath below
            try:
                # Declare the attack for this round.
                sess.send("attack " + tok, settle_ms=1300)
                # Take the auto-pose to close the posing window + resolve.
                if _strip_visible(sess):
                    sess.send("pass", settle_ms=1400)
                r = beat(sess, f"{5+rnd:02d}_round_{rnd}", f"combat round {rnd}")

                cur_feed = _feed_len()
                if cur_feed <= prev_feed:
                    stalled += 1
                else:
                    stalled = 0
                prev_feed = cur_feed
                if stalled >= 4 and _strip_visible(sess):
                    findings.append({
                        "beat": f"round {rnd}", "kind": "broken-progression",
                        "detail": "Combat appears STALLED: the ground feed stopped "
                                  f"growing for {stalled} consecutive attack→pass "
                                  "cycles yet the combat strip is still up — the "
                                  "fight is not resolving / returning control.",
                    })
                    break
            except Exception as e:
                print(f"[play] round {rnd} err: {e}", flush=True)

        # ── AFTERMATH: combat should have ended. Capture the resolution,
        #    confirm the strip tore down + control returned. ──────────────
        try:
            sess.page.wait_for_timeout(1500)
            sess.send("look", settle_ms=1100)
            r_end = beat(sess, f"{6+max_rounds:02d}_aftermath",
                         "post-combat look (expect strip gone, prose result, control returned)")
            strip_gone = not _strip_visible(sess)
            cmd_alive = bool(sess.page.evaluate(
                "() => { const i=document.getElementById('cmd-input-ground');"
                " return !!(i && i.offsetParent !== null); }"))
            combat_ended_clean = reached_combat and strip_gone and cmd_alive
            print(f"[play] aftermath: strip_gone={strip_gone} cmd_alive={cmd_alive} "
                  f"ended_clean={combat_ended_clean}", flush=True)
            if reached_combat and not strip_gone:
                findings.append({
                    "beat": "aftermath", "kind": "stuck-ui",
                    "detail": "Combat strip still visible after the fight should "
                              "have resolved — UI did not tear down / return control.",
                })
        except Exception as e:
            print(f"[play] aftermath err: {e}", flush=True)

        # ── Objective progression: did the tutorial step advance off the
        #    combat drill? Read the objective text after the fight. ────────
        try:
            obj_after = sess.page.inner_text("#g-objective-text")
            print(f"[play] objective after combat: {obj_after!r}", flush=True)
            MANIFEST[-1]["objective_after"] = obj_after
        except Exception:
            pass

        browser_defects = [d.as_dict() for d in sess.defects()]

    # ── manifest + summary ────────────────────────────────────────────────
    print("\n========== PLAY MANIFEST ==========", flush=True)
    for rec in MANIFEST:
        print(f"  {rec['n']:02d} {rec['label']:24s} "
              f"png={rec.get('png','-'):26s} txt={rec.get('txt','-')}", flush=True)
    print("\n========== JUDGMENT FLAGS ==========", flush=True)
    print(f"  reached_combat     = {reached_combat}", flush=True)
    print(f"  combat_ended_clean = {combat_ended_clean}", flush=True)
    print("\n========== SCRIPT FINDINGS ==========", flush=True)
    if findings:
        for f in findings:
            print(f"  !! {json.dumps(f, ensure_ascii=False)}", flush=True)
    else:
        print("  (none recorded by the driver heuristics)", flush=True)
    print("\n========== BROWSER-LAYER DEFECTS ==========", flush=True)
    if browser_defects:
        for d in browser_defects:
            print(f"  !! {json.dumps(d, ensure_ascii=False)}", flush=True)
    else:
        print("  (none)", flush=True)

    summary = {"manifest": MANIFEST, "findings": findings,
               "reached_combat": reached_combat,
               "combat_ended_clean": combat_ended_clean,
               "browser_defects": browser_defects}
    (OUT / "_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[play] artifacts in {OUT}", flush=True)
    print(f"[play] summary -> {OUT / '_summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
