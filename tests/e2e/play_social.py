# -*- coding: utf-8 -*-
"""
tests/e2e/play_social.py — NORMAL-PLAY QA: the Social / RP / comms journey.

NOT adversarial. A real player sits down and does the intended social things:
  say / ' / "      — speak aloud
  pose / :         — describe an action
  emote            — same family
  whisper          — local private
  channels         — see what channels exist
  ooc / comlink    — global OOC + planet-wide IC chat
  tune + commfreq  — a custom frequency
  who  AND  +who   — see who's online (player will TRY bare `who` first)

After each beat we screenshot the page and dump #ground-feed-col (the pose-log
column) so a human can judge: do the messages render as PROSE (not raw JSON),
do channels show membership, is anything garbled / raw / missing?

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/play_social.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.e2e.breakit_harness import BreakItSession  # noqa: E402

OUT = REPO / "tests" / "e2e" / "_play_social"


def _capture(sess, n: int, label: str, manifest: list) -> None:
    """Screenshot + dump the ground feed text for one beat."""
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{n:02d}_{label}.png"
    txt = OUT / f"{n:02d}_{label}.txt"
    try:
        sess.page.screenshot(path=str(png), full_page=False)
    except Exception as e:
        print(f"  [warn] screenshot {label} failed: {e}", flush=True)
    feed = ""
    try:
        feed = sess.page.inner_text("#ground-feed-col")
    except Exception as e:
        feed = f"<<feed read failed: {e}>>"
    # Also grab the comms pane rows (mirrored channel/IC messages).
    comms = ""
    try:
        comms = sess.page.eval_on_selector_all(
            "#comms-body-ground .comms-row",
            "els => els.map(e => e.textContent).join('\\n')",
        )
    except Exception:
        comms = ""
    try:
        body = feed
        if comms:
            body = feed + "\n\n===== COMMS PANE ROWS =====\n" + comms
        txt.write_text(body, encoding="utf-8")
    except Exception as e:
        print(f"  [warn] feed write {label} failed: {e}", flush=True)
    manifest.append((png.name, txt.name))
    print(f"  [beat {n:02d}] {label}: png+txt written "
          f"(feed {len(feed)} chars, comms {len(comms)} chars)", flush=True)


def _beat(sess, n, label, cmds, manifest, settle=900):
    """Send one or more commands, then capture."""
    if isinstance(cmds, str):
        cmds = [cmds]
    for c in cmds:
        try:
            sess.send(c, settle_ms=settle)
        except Exception as e:
            print(f"  [warn] send {c!r} failed: {e}", flush=True)
    _capture(sess, n, label, manifest)


def main() -> int:
    # wipe prior run
    if OUT.exists():
        for f in OUT.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
    manifest: list = []
    rc = 1
    with BreakItSession(headless=True, label="social") as sess:
        # Generous timeouts: cold boot + chargen under a single browser.
        sess.page.set_default_navigation_timeout(90000)
        sess.page.set_default_timeout(45000)
        try:
            info = sess.new_player()
            print(f"  player: {info}", flush=True)
        except Exception as e:
            print(f"  [FATAL] new_player failed: {e}\n{traceback.format_exc()}",
                  flush=True)
            return 1

        # Beat 0 — baseline: just look at the room before talking.
        _beat(sess, 0, "arrival_look", "look", manifest)

        # Beat 1 — say (the canonical verb).
        _beat(sess, 1, "say_hello", 'say Hello there, anyone around?', manifest)

        # Beat 2 — the ' shortcut.
        _beat(sess, 2, "say_quote_shortcut", "'Nice cantina.", manifest)

        # Beat 3 — pose (alias of emote).
        _beat(sess, 3, "pose_waves", "pose waves a friendly hand.", manifest)

        # Beat 4 — the : shortcut for pose/emote.
        _beat(sess, 4, "colon_emote", ":leans against the bar, looking relaxed.",
              manifest)

        # Beat 5 — emote explicit verb.
        _beat(sess, 5, "emote_explicit", "emote scans the room slowly.", manifest)

        # Beat 6 — whisper to nobody (solo) — see the validation feedback.
        _beat(sess, 6, "whisper_no_target",
              "whisper Tundra = psst, over here", manifest)

        # Beat 7 — bare `who` (what a NORMAL player types first).
        _beat(sess, 7, "who_bare", "who", manifest)

        # Beat 8 — +who (the canonical form).
        _beat(sess, 8, "plus_who", "+who", manifest)

        # Beat 9 — channels overview.
        _beat(sess, 9, "channels", "channels", manifest)

        # Beat 10 — OOC global chat.
        _beat(sess, 10, "ooc_global", "ooc Hi all, new player here!", manifest)

        # Beat 11 — comlink (planet-wide IC).
        _beat(sess, 11, "comlink", "comlink Anyone near the spaceport?", manifest)

        # Beat 12 — fcomm (faction channel).
        _beat(sess, 12, "fcomm", "fcomm checking in.", manifest)

        # Beat 13 — tune a custom frequency, then transmit.
        _beat(sess, 13, "tune_freq", "tune 1138", manifest)
        _beat(sess, 14, "commfreq_transmit",
              "commfreq 1138 meet at bay 94 in five", manifest)
        _beat(sess, 15, "freqs_list", "freqs", manifest)

        # Beat 16 — open the COMMS pane explicitly + click through its tabs so we
        # capture what membership/filtering looks like to a player.
        try:
            sess.page.evaluate("() => toggleCommsPane('ground')")
            sess.page.wait_for_timeout(400)
        except Exception as e:
            print(f"  [warn] toggleCommsPane failed: {e}", flush=True)
        _capture(sess, 16, "comms_pane_open", manifest)

        for f in ("ic", "ooc", "sys", "all"):
            try:
                sess.page.evaluate("ff => setCommsFilter('ground', ff)", f)
                sess.page.wait_for_timeout(300)
            except Exception as e:
                print(f"  [warn] setCommsFilter {f} failed: {e}", flush=True)
            _capture(sess, 17, f"comms_tab_{f}", manifest)

        # Beat 18 — a final say so the feed shows the full conversation flow.
        _beat(sess, 18, "say_goodbye", 'say Heading out, see you around.', manifest)

        # Record any auto-captured browser-layer defects (pageerror / 5xx / etc).
        d = [x.as_dict() for x in sess.defects()]
        (OUT / "_browser_defects.json").write_text(
            __import__("json").dumps(d, indent=2), encoding="utf-8")
        print(f"  browser-layer defects captured: {len(d)}", flush=True)
        for x in d:
            print(f"    - {x['kind']}: {x['detail'][:200]}", flush=True)
        rc = 0

    print("\n=== MANIFEST ===", flush=True)
    for png, txt in manifest:
        print(f"  {png}  |  {txt}", flush=True)
    print(f"\nArtifacts in: {OUT}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
