# -*- coding: utf-8 -*-
"""
tests/e2e/play_bounty.py — NORMAL-PLAY QA: the NPC bounty-hunting journey.

This is NOT an adversarial break-it. It is a PLAYER doing the intended thing:
find the bounty board, read a contract, accept it, hunt the target, resolve it.
After each beat it screenshots + dumps the relevant feed so the experience can be
judged the way a player would judge it (does the text read right? does accepting
work? can the quest actually be progressed and finished?).

Journey (the canonical NPC bounty surface — parser/bounty_commands.py):
  bounties              -> view the board (also fires the web board_state modal)
  +bounty/claim <id>    -> accept a contract
  +mybounty             -> review the active contract
  +bounty/track         -> investigation roll to reveal the target room
  (navigate to the target room)
  attack <target>       -> engage + defeat the fugitive
  +bounty/collect       -> collect the reward

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/play_bounty.py
Boot takes ~30-60s. Artifacts land in tests/e2e/_play_bounty/.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.e2e.breakit_harness import BreakItSession  # noqa: E402

OUT = Path(__file__).resolve().parent / "_play_bounty"
_N = [0]
_MANIFEST: list[str] = []


def _label(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def beat(sess, label: str, feeds=("ground",)):
    """Screenshot + dump the requested feeds for one journey beat."""
    _N[0] += 1
    n = _N[0]
    lab = _label(label)
    png = OUT / f"{n:02d}_{lab}.png"
    try:
        sess.page.screenshot(path=str(png), full_page=False)
        _MANIFEST.append(str(png))
    except Exception as e:
        print(f"[play] screenshot FAILED {label}: {e}", flush=True)

    feed_sel = {
        "ground": "#ground-feed-col",
        "combat": "#combat-feed",
        "objective": "#g-objective-text",
        "board": "#board-modal-body",
    }
    for f in feeds:
        sel = feed_sel.get(f)
        if not sel:
            continue
        txt_path = OUT / f"{n:02d}_{lab}__{f}.txt"
        try:
            txt = sess.page.inner_text(sel)
        except Exception as e:
            txt = f"<<inner_text({sel}) failed: {e}>>"
        try:
            txt_path.write_text(txt or "<<empty>>", encoding="utf-8")
            _MANIFEST.append(str(txt_path))
        except Exception as e:
            print(f"[play] write FAILED {txt_path}: {e}", flush=True)
    print(f"[play] beat {n:02d} {lab} -> {png.name}", flush=True)
    return n


def ground_text(sess) -> str:
    try:
        return sess.page.inner_text("#ground-feed-col") or ""
    except Exception:
        return ""


def board_modal_open(sess) -> bool:
    try:
        return bool(sess.page.evaluate(
            "() => { const p=document.getElementById('board-modal');"
            " return !!(p && p.classList.contains('show')); }"))
    except Exception:
        return False


def board_modal_text(sess) -> str:
    try:
        return sess.page.inner_text("#board-modal-body") or ""
    except Exception:
        return ""


def board_accept_buttons(sess):
    """Return a list of (text, staged-cmd) for every clickable button in the
    open board modal — so we can see if ACCEPT/TRACK actually exist + what they
    stage."""
    try:
        return sess.page.evaluate(
            """() => {
                const body = document.getElementById('board-modal-body');
                if (!body) return [];
                return Array.from(body.querySelectorAll('button')).map(b => ({
                    text: (b.textContent||'').trim(),
                    cmd: b.getAttribute('data-cmd') || b.getAttribute('data-stage') || '',
                    disabled: !!b.disabled
                }));
            }""") or []
    except Exception:
        return []


def staged_input(sess) -> str:
    """Read whatever is currently staged in the ground command box."""
    try:
        return sess.page.eval_on_selector(
            "#cmd-input-ground", "el => el.value || ''") or ""
    except Exception:
        return ""


def parse_contract_ids(text: str):
    """Pull `b-xxxxxxxx` contract ids out of any rendered text (board feed)."""
    return re.findall(r"b-[0-9a-f]{8}", text)


def _ascii(s: str) -> str:
    """Strip non-ASCII so Windows cp1252 stdout never crashes a print."""
    return (s or "").encode("ascii", "replace").decode("ascii")


def parse_board_rows(text: str):
    """Parse the BOUNTY BOARD text block into [{id,tier,reward}] rows so we can
    pick a trackable tier (Extra=diff 6) instead of the unwinnable Superior."""
    rows = []
    for m in re.finditer(
            r"(b-[0-9a-f]{8})\s+(\w+)\s+.*?([\d,]+)cr", text):
        cid, tier, reward = m.group(1), m.group(2).lower(), m.group(3)
        try:
            rew = int(reward.replace(",", ""))
        except ValueError:
            rew = 0
        rows.append({"id": cid, "tier": tier, "reward": rew})
    # de-dupe by id, keep first
    seen, out = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out


def here_npc_names(sess):
    try:
        return sess.page.evaluate(
            "() => { const b = document.getElementById('here-body');"
            " if (!b) return [];"
            " return Array.from(b.querySelectorAll('.here-name.npc'))"
            "   .map(e => (e.textContent||'').trim()); }") or []
    except Exception:
        return []


def visible_exits(sess):
    try:
        return sess.page.evaluate(
            "() => Array.from(document.querySelectorAll('#g-map-exits button.mm-exit-btn'))"
            ".map(b => b.getAttribute('data-cmd'))") or []
    except Exception:
        return []


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        try:
            old.unlink()
        except Exception:
            pass

    notes = []

    with BreakItSession(headless=True, label="bounty") as sess:
        # ── Beat 0: arrive in game ───────────────────────────────────────
        try:
            sess.new_player()
            sess.send("look", settle_ms=900)
            beat(sess, "01_arrived_look", feeds=("ground", "objective"))
        except Exception as e:
            print(f"[play] new_player/look FAILED: {e}", flush=True)
            notes.append(f"new_player failed: {e}")

        # ── Beat: discovery — does the game tell a player bounties exist? ─
        try:
            sess.send("help bounty", settle_ms=900)
            beat(sess, "02_help_bounty")
        except Exception as e:
            notes.append(f"help bounty failed: {e}")

        try:
            sess.send("help +bounty", settle_ms=900)
            beat(sess, "03_help_plus_bounty")
        except Exception as e:
            notes.append(f"help +bounty failed: {e}")

        # ── Beat: open the board via the typed verb ──────────────────────
        contract_ids = []
        board_rows = []
        try:
            sess.send("bounties", settle_ms=1200)
            gt = ground_text(sess)
            ids_from_feed = parse_contract_ids(gt)
            board_rows = parse_board_rows(gt)
            n = beat(sess, "04_bounties_board", feeds=("ground", "board"))
            modal = board_modal_open(sess)
            bt = board_modal_text(sess)
            btns = board_accept_buttons(sess)
            ids_from_modal = parse_contract_ids(bt)
            contract_ids = ids_from_modal or ids_from_feed
            print(f"[play] board modal open={modal} buttons={len(btns)} "
                  f"ids_feed={ids_from_feed} ids_modal={ids_from_modal}", flush=True)
            (OUT / f"{n:02d}_bounties_board__modal_meta.json").write_text(
                json.dumps({"modal_open": modal, "buttons": btns,
                            "ids_from_feed": ids_from_feed,
                            "ids_from_modal": ids_from_modal,
                            "board_modal_text": bt[:4000]}, indent=2),
                encoding="utf-8")
            _MANIFEST.append(str(OUT / f"{n:02d}_bounties_board__modal_meta.json"))
        except Exception as e:
            notes.append(f"bounties board failed: {e}")

        # ── Beat: click the JOBS quick-action button (the web entry) ─────
        # The `bounties` verb above already auto-opened the board modal, whose
        # overlay intercepts the JOBS click. Close it first so this beat tests
        # the JOBS->board path cleanly (not a script artifact).
        try:
            sess.page.evaluate(
                "() => { const ov=document.getElementById('board-modal-overlay');"
                " const p=document.getElementById('board-modal');"
                " if (ov) ov.classList.remove('show');"
                " if (p) p.classList.remove('show'); }")
            sess.page.wait_for_timeout(300)
        except Exception:
            pass
        try:
            sess.page.click('[data-qa="JOBS"]', timeout=5000)
            sess.page.wait_for_timeout(1200)
            n = beat(sess, "05_jobs_button", feeds=("board",))
            btns = board_accept_buttons(sess)
            modal = board_modal_open(sess)
            print(f"[play] JOBS button -> modal_open={modal} buttons="
                  f"{[b.get('text') for b in btns]}", flush=True)
            (OUT / f"{n:02d}_jobs_button__buttons.json").write_text(
                json.dumps({"modal_open": modal, "buttons": btns}, indent=2),
                encoding="utf-8")
            _MANIFEST.append(str(OUT / f"{n:02d}_jobs_button__buttons.json"))

            # Try clicking an ACCEPT button in the modal and see what it stages.
            accepted_via_button = False
            try:
                acc = sess.page.query_selector(
                    "#board-modal-body button:has-text('ACCEPT')") or \
                    sess.page.query_selector(
                        "#board-modal-body button:has-text('Accept')")
                if acc:
                    acc.click()
                    sess.page.wait_for_timeout(700)
                    staged = staged_input(sess)
                    print(f"[play] ACCEPT button staged: {staged!r}", flush=True)
                    accepted_via_button = bool(staged)
                    n2 = beat(sess, "06_accept_button_staged")
                    (OUT / f"{n2:02d}_accept_button_staged__cmd.txt").write_text(
                        staged or "<<nothing staged>>", encoding="utf-8")
                    _MANIFEST.append(
                        str(OUT / f"{n2:02d}_accept_button_staged__cmd.txt"))
            except Exception as e:
                print(f"[play] ACCEPT button click failed: {e}", flush=True)
            notes.append(f"accept_via_button_staged={accepted_via_button}")
        except Exception as e:
            notes.append(f"JOBS button failed: {e}")

        # Make sure the modal isn't blocking the command box.
        try:
            sess.page.keyboard.press("Escape")
            sess.page.evaluate(
                "() => { const ov=document.getElementById('board-modal-overlay');"
                " const p=document.getElementById('board-modal');"
                " if (ov) ov.classList.remove('show');"
                " if (p) p.classList.remove('show'); }")
            sess.page.wait_for_timeout(300)
        except Exception:
            pass

        # ── Beat: accept a contract via the typed command ────────────────
        # A brand-new non-combat template has Search ~3D+1 (max ~19). The
        # board lists the Superior (diff 21) FIRST (highest reward) — a new
        # player who claims the top row can NEVER track it. Pick the lowest
        # track-difficulty tier we can actually win (Extra=6, Average=10).
        _TIER_DIFF = {"extra": 6, "average": 10, "novice": 13,
                      "veteran": 17, "superior": 21}
        if not board_rows:
            sess.send("bounties", settle_ms=1000)
            board_rows = parse_board_rows(ground_text(sess)) or \
                parse_board_rows(board_modal_text(sess))
        chosen = None
        if board_rows:
            board_rows.sort(key=lambda r: _TIER_DIFF.get(r["tier"], 99))
            chosen = board_rows[0]["id"]
            print(_ascii(f"[play] board rows={board_rows}; "
                         f"picking trackable tier -> {chosen}"), flush=True)
        elif contract_ids:
            chosen = contract_ids[0]
        notes.append(f"chosen_contract_tier="
                     f"{board_rows[0]['tier'] if board_rows else '?'}")

        if chosen:
            try:
                sess.send(f"+bounty/claim {chosen}", settle_ms=1300)
                beat(sess, "07_claimed_contract", feeds=("ground", "objective"))
                gt = ground_text(sess)
                print(_ascii(f"[play] claim feed tail:\n{gt[-700:]}"),
                      flush=True)
            except Exception as e:
                notes.append(f"+bounty/claim failed: {e}")
        else:
            notes.append("NO contract id parseable -> cannot accept a bounty")
            print("[play] NO CONTRACT ID FOUND — cannot accept", flush=True)

        # ── Beat: review the active contract ─────────────────────────────
        target_name = None
        try:
            sess.send("+mybounty", settle_ms=1100)
            beat(sess, "08_mybounty", feeds=("ground",))
            gt = ground_text(sess)
            m = re.search(r"Target:\s+([^\(\n]+)", gt)
            if m:
                target_name = m.group(1).strip()
            print(f"[play] active target name = {target_name!r}", flush=True)
        except Exception as e:
            notes.append(f"+mybounty failed: {e}")

        # ── Beat: track the target (skill roll; retry up to 12x) ─────────
        # Detection MUST look only at the FRESHEST track output (after the
        # last "Investigating:" header) — the cached help text in the feed
        # contains an EXAMPLE "Lead found! ... last seen at: The Lucky
        # Despot's back corridor" line that a naive search false-positives on.
        revealed_room = None
        for i in range(12):
            try:
                sess.send("+bounty/track", settle_ms=1200)
                gt = ground_text(sess)
                n = beat(sess, f"09_track_attempt_{i+1}", feeds=("ground",))
                # Slice from the LAST "Investigating:" to end = this roll only.
                idx = gt.rfind("Investigating:")
                fresh = gt[idx:] if idx != -1 else ""
                m = re.search(r"last seen at:\s*(.+)", fresh)
                if "Lead found" in fresh and m:
                    revealed_room = re.sub(r"\s+$", "", m.group(1)).strip()
                    print(_ascii(f"[play] TRACK success attempt {i+1}; "
                                 f"room={revealed_room}"), flush=True)
                    break
                # Echo the actual roll line so we can judge difficulty.
                roll = re.search(r"roll:\s*\d+.*", fresh)
                print(_ascii(f"[play] track {i+1}: "
                             f"{roll.group(0) if roll else 'no lead'}"),
                      flush=True)
            except Exception as e:
                notes.append(f"+bounty/track attempt {i+1} failed: {e}")
        notes.append(f"track_revealed_room={revealed_room!r}")

        # ── Beat: try to reach + engage the target ───────────────────────
        # As a normal player we can only WALK the exit graph from the tutorial
        # Landing Pad. DFS up to 60 moves, looking for an NPC matching the
        # target. This measures whether the hunt is actually completable on
        # foot — the fugitive spawns in ANY room from list_rooms(limit=100),
        # which can be a different planet entirely.
        engaged = False
        defeated = False
        reached_revealed = False
        target_token = (target_name.split()[0].lower()
                        if target_name and target_name.lower() != "unnamed"
                        else None)
        # "Unnamed Imperial Officer" -> first usable token is "imperial".
        if not target_token and target_name:
            toks = [t for t in target_name.lower().split()
                    if t not in ("unnamed",)]
            target_token = toks[0] if toks else None
        print(_ascii(f"[play] hunting token={target_token!r} "
                     f"revealed_room={revealed_room!r}"), flush=True)

        visited = set()
        rooms_walked = []
        try:
            for step in range(60):
                # Current room name (top of the YOU ARE IN block).
                try:
                    rn = sess.page.evaluate(
                        "() => { const e=document.querySelector('.room-name-display');"
                        " return e ? (e.textContent||'').trim() : ''; }") or ""
                except Exception:
                    rn = ""
                if rn:
                    rooms_walked.append(rn)
                    if revealed_room and revealed_room.split("'")[0].strip()[:12] \
                            and revealed_room[:12].lower() in rn.lower():
                        reached_revealed = True

                names = here_npc_names(sess)
                match = None
                if target_token:
                    for nm in names:
                        if target_token in nm.lower():
                            match = nm
                            break
                if match:
                    print(_ascii(f"[play] FOUND {match} after {step} moves"),
                          flush=True)
                    sess.send(f"attack {target_token}", settle_ms=1500)
                    engaged = True
                    beat(sess, "10_engaged_target", feeds=("ground", "combat"))
                    for r in range(14):
                        sess.send(f"attack {target_token}", settle_ms=1300)
                        gt = ground_text(sess)
                        try:
                            ct = sess.page.inner_text("#combat-feed") or ""
                        except Exception:
                            ct = ""
                        blob = gt + "\n" + ct
                        if any(k in blob for k in (
                                "Bounty collected", "Reward: +",
                                "incapacitat", "mortally wounded",
                                "is dead", "defeated")):
                            defeated = True
                            print(f"[play] target down round {r+1}", flush=True)
                            break
                    beat(sess, "11_combat_resolved", feeds=("ground", "combat"))
                    break

                # Wander: prefer an unvisited exit direction.
                exits = visible_exits(sess)
                nxt = None
                for ex in exits:
                    if ex and (rn, ex) not in visited:
                        nxt = ex
                        break
                if not nxt and exits:
                    nxt = exits[0]
                if not nxt:
                    print(f"[play] dead end at step {step} (room={_ascii(rn)})",
                          flush=True)
                    break
                visited.add((rn, nxt))
                sess.send(nxt, settle_ms=850)
            if not engaged:
                print(_ascii("[play] never reached target on foot; walked "
                             f"{len(set(rooms_walked))} distinct rooms"),
                      flush=True)
                beat(sess, "10_wander_gave_up", feeds=("ground",))
        except Exception as e:
            notes.append(f"hunt/engage phase failed: {e}")
        notes.append(f"engaged={engaged} defeated={defeated} "
                     f"reached_revealed={reached_revealed} "
                     f"distinct_rooms_walked={len(set(rooms_walked))}")

        # ── Beat: attempt to collect the reward ──────────────────────────
        try:
            sess.send("+bounty/collect", settle_ms=1300)
            beat(sess, "12_collect", feeds=("ground",))
            gt = ground_text(sess)
            print(_ascii(f"[play] collect feed tail:\n{gt[-700:]}"), flush=True)
            notes.append("collect_attempted=True")
        except Exception as e:
            notes.append(f"+bounty/collect failed: {e}")

        # ── Beat: final state — board again to see next contract prompt ──
        try:
            sess.send("+mybounty", settle_ms=1000)
            beat(sess, "13_final_mybounty", feeds=("ground",))
        except Exception as e:
            notes.append(f"final +mybounty failed: {e}")

        # Browser-layer defects the harness auto-captured.
        defs = [d.as_dict() for d in sess.defects()]
        (OUT / "_browser_defects.json").write_text(
            json.dumps(defs, indent=2), encoding="utf-8")
        _MANIFEST.append(str(OUT / "_browser_defects.json"))
        print(f"[play] browser-layer defects captured: {len(defs)}", flush=True)
        for d in defs:
            print(f"[play]   {d['kind']}: {d['detail'][:200]}", flush=True)

    (OUT / "_notes.json").write_text(
        json.dumps(notes, indent=2), encoding="utf-8")
    _MANIFEST.append(str(OUT / "_notes.json"))

    print("\n[play] ===== MANIFEST =====", flush=True)
    for p in _MANIFEST:
        print("[play]   " + p, flush=True)
    print(f"[play] total artifacts: {len(_MANIFEST)}", flush=True)
    print("[play] notes: " + json.dumps(notes), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
