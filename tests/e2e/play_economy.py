#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tests/e2e/play_economy.py — NORMAL-PLAY QA: economy loop (shop / inventory / housing).

Not adversarial. A PLAYER doing the intended thing: graduate the new-player
tutorial, find a shop, buy an affordable weapon, check inventory, equip/wield,
sell something, and look at housing. Judge whether the experience WORKS + READS.

REACHABILITY MAP (discovered live, 2026-06-23):
  * A fresh new player spawns in the LEGACY core tutorial: "Landing Pad" ->
    east -> "Desert Trail" -> ... -> "Mos Eisley Gate" -> NORTH into the city.
    (6-room linear desert walk with a scripted ambush at "Ambush Point".)
  * The open-market `buy <weapon>` requires an NPC with ai_config.vendor:true in
    the room. The reachable one for a tutorial graduate is the Jawa Trade-Elder
    in "Jawa Traders" (off the Mos Eisley Market District).
  * `+inv` opens a blocking inventory MODAL overlay — must be closed before the
    next typed command works.

The script walks the tutorial east/north, hunts for a vendor room by following
exits + `look`ing, then runs the economy loop (weapons/buy/inv/equip/sell/
housing/commissary). It is resilient (try/except per beat) and captures a
screenshot + ground-feed + credits + equip-list at every beat.

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/play_economy.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.e2e.breakit_harness import BreakItSession  # noqa: E402

OUT = Path(__file__).resolve().parent / "_play_economy"
_N = [0]
MANIFEST: list[dict] = []
FINDINGS: list[dict] = []
CREDIT_LOG: list[dict] = []

# Affordable vendor_stocked weapons (name -> cost) for the buy attempt.
BUYABLE = [("hold-out blaster", 275), ("knife", 25),
           ("blaster pistol", 500), ("sporting blaster", 300)]


def _txt(page, selector: str) -> str:
    try:
        return page.inner_text(selector)
    except Exception as e:
        return f"<<inner_text({selector}) error: {e}>>"


def _credits(page) -> str:
    return _txt(page, "#g-credits").strip()


def _close_modals(page):
    """Close any blocking modal overlay that a command may have popped (+inv,
    shop, board, craft). Otherwise the next command-box click is intercepted."""
    for fn in ("closeInventoryModal", "closeShopModal", "closeBoardModal",
               "closeCraftModal"):
        try:
            page.evaluate(f"() => {{ if (window.{fn}) window.{fn}(); }}")
        except Exception:
            pass
    try:
        page.wait_for_timeout(150)
    except Exception:
        pass


def send(sess, cmd: str, settle_ms: int = 750):
    """Type a command, closing any blocking modal first."""
    _close_modals(sess.page)
    try:
        sess.send(cmd, settle_ms=settle_ms)
    except Exception as e:
        print(f"[play] send({cmd!r}) err: {e}", flush=True)


def room_name(page) -> str:
    try:
        return page.inner_text("#top-context")
    except Exception:
        return ""


def in_combat(page) -> bool:
    block = _txt(page, "#ground-feed-col")
    tail = block[-600:].lower()
    return ("under attack" in tail or "you're in combat" in tail
            or "declare: attack" in tail or "attacks!" in tail)


def clear_combat(sess, tries: int = 8):
    """If a hostile mob locked us in combat, fight it out (attack) so movement
    unlocks. A fresh char has a 4D blaster and wins the tutorial-grade mobs."""
    page = sess.page
    for _ in range(tries):
        if not in_combat(page):
            return
        # attack the named enemy generically
        send(sess, "attack smuggler", settle_ms=900)
        if not in_combat(page):
            return
        send(sess, "attack", settle_ms=900)


def server_exits(page) -> list[str]:
    try:
        se = page.evaluate("() => (window.lastExits || [])")
    except Exception:
        return []
    if not isinstance(se, list):
        return []
    return [str(x.get("dir")) for x in se
            if isinstance(x, dict) and x.get("dir")]


_DIRS = ("north", "south", "east", "west", "up", "down", "in", "out",
         "northeast", "northwest", "southeast", "southwest", "enter")


def feed_exits(page) -> list[str]:
    """Parse the LAST 'Exits: east (Desert Trail)' line out of the prose feed.

    The ground feed ACCUMULATES every room's prose, so earlier rooms' 'Exits:'
    lines linger. We want the current room's exits, so take the last such line.
    """
    feed = _txt(page, "#ground-feed-col")
    last = None
    for line in feed.splitlines():
        s = line.strip()
        if s.lower().startswith("exits:"):
            last = s
    if not last:
        return []
    dirs = []
    for tok in last.split(":", 1)[1].replace(",", " ").split():
        t = tok.strip().lower()
        if t in _DIRS and t not in dirs:
            dirs.append(t)
    return dirs


def current_exits(page) -> list[str]:
    """Current-room exits, preferring the mini-map buttons (always reflect the
    CURRENT room) and falling back to the last feed 'Exits:' line."""
    try:
        mini = page.eval_on_selector_all(
            "#g-map-exits button.mm-exit-btn",
            "els => els.map(e => (e.getAttribute('data-cmd')||'').toLowerCase())")
    except Exception:
        mini = []
    mini = [m for m in (mini or []) if m in _DIRS]
    if mini:
        return mini
    return feed_exits(page)


def looks_like_json(text: str) -> bool:
    for line in (text or "").splitlines():
        s = line.strip()
        if ((s.startswith("{") and s.endswith("}") and '":' in s) or
                (s.startswith("[{") and '":' in s)) and len(s) > 40:
            return True
    return False


def beat(sess, label: str, note: str = "") -> dict:
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

    feed = _txt(page, "#ground-feed-col")
    equip = _txt(page, "#g-equip-list")
    credits = _credits(page)
    rm = room_name(page)
    se = server_exits(page)
    fe = feed_exits(page)
    # mini-map clickable exit buttons
    try:
        mini = page.eval_on_selector_all(
            "#g-map-exits button.mm-exit-btn",
            "els => els.map(e => e.getAttribute('data-cmd'))")
    except Exception:
        mini = []

    rec.update({"room": rm, "credits": credits, "equip": equip.strip(),
                "server_exits": se, "feed_exits": fe, "mini_exits": mini})
    try:
        txt.write_text(
            f"=== BEAT {n}: {label} ===\nNOTE: {note}\nROOM: {rm}\n"
            f"CREDITS (#g-credits): {credits}\n"
            f"FEED EXITS: {fe}   SERVER lastExits: {se}   "
            f"MINI BTNS: {mini}\n\n"
            f"--- #g-equip-list ---\n{equip}\n\n"
            f"--- #ground-feed-col text ---\n{feed}\n",
            encoding="utf-8")
        rec["txt"] = txt.name
    except Exception as e:
        rec["txt_err"] = str(e)
    MANIFEST.append(rec)
    print(f"[play] beat {n:02d} {label}: room={rm!r} credits={credits!r} "
          f"feed_exits={fe} mini={mini}", flush=True)
    return rec


def last_room_block(page) -> str:
    """Return only the CURRENT room's look block (last 'YOU ARE IN' section),
    so vendor detection doesn't false-match prose from earlier rooms that
    lingers in the accumulating feed."""
    feed = _txt(page, "#ground-feed-col")
    idx = feed.rfind("YOU ARE IN")
    return (feed[idx:] if idx >= 0 else feed).lower()


def vendor_works_here(sess) -> bool:
    """AUTHORITATIVE vendor test: type `buy hold-out blaster` and read the
    refusal. 'No merchant here sells weapons' => no vendor. Anything else
    (price/haggle/insufficient/bought) => a vendor is present. Restores
    credits is unnecessary — we only buy if affordable later."""
    page = sess.page
    before = _credits(page)
    send(sess, "buy hold-out blaster", settle_ms=850)
    block = last_room_block(page)
    feed = _txt(page, "#ground-feed-col").lower()
    after = _credits(page)
    # If credits moved, we bought it (vendor present).
    if before != after:
        return True
    # Refusal phrasing tells us whether a vendor exists in the room.
    if "no merchant here sells weapons" in feed:
        return False
    if "find a shop" in feed:
        return False
    # 'Not enough credits' / haggle / faction-refusal => vendor IS here.
    if ("not enough credits" in feed or "costs" in block
            or "the vendor" in feed):
        return True
    return False


def note_credit(label, before, after, expect):
    CREDIT_LOG.append({"beat": label, "before": before, "after": after,
                       "expect": expect})


def walk_tutorial(sess) -> bool:
    """Walk the linear desert tutorial east, fighting/surviving the ambush,
    then north into Mos Eisley. Returns True if we left the tutorial."""
    page = sess.page
    for step in range(12):
        rm = room_name(page)
        feed = _txt(page, "#ground-feed-col").lower()
        in_tutorial = ("tutorial" in rm.lower() or "tutorial" in feed[:400]
                       or "landing pad" in rm.lower())
        # Ambush handling: if combat is live, fight the raider until clear.
        if in_combat(page) or "raider" in feed[-400:]:
            for _ in range(8):
                if not in_combat(page):
                    break
                send(sess, "attack raider", settle_ms=950)
                if not in_combat(page):
                    break
                send(sess, "attack", settle_ms=950)
        # Choose a direction from the CURRENT room's exits (mini buttons).
        # The desert path runs east; the Mos Eisley Gate graduates NORTH.
        # Never walk 'west' (that's back toward the landing pad).
        ce = [d for d in current_exits(page) if d != "west"]
        nxt = None
        for pref in ("north", "east", "northeast", "in", "enter"):
            if pref in ce:
                nxt = pref
                break
        if nxt is None and ce:
            nxt = ce[0]
        if nxt is None:
            nxt = "east"
        send(sess, nxt, settle_ms=850)
        beat(sess, f"tut{step:02d}_{nxt}", f"tutorial walk: moved '{nxt}'")
        new_rm = room_name(page)
        new_feed = _txt(page, "#ground-feed-col").lower()
        # Are we out of the tutorial now? (city room name w/o 'tutorial')
        if ("tutorial" not in new_rm.lower()
                and "tutorial" not in new_feed[:300]
                and "landing pad" not in new_rm.lower()
                and ("mos eisley" in new_rm.lower()
                     or "mos eisley" in new_feed[:300])):
            print(f"[play] left tutorial at room={new_rm!r}", flush=True)
            return True
    return ("tutorial" not in room_name(page).lower())


_OPPOSITE = {
    "north": "south", "south": "north", "east": "west", "west": "east",
    "up": "down", "down": "up", "in": "out", "out": "in",
    "northeast": "southwest", "southwest": "northeast",
    "northwest": "southeast", "southeast": "northwest",
}

# Reachable-room map: room_name -> {"exits": [...], "vendor": bool}
POCKET_MAP: dict[str, dict] = {}


def _visit(sess, rm) -> bool:
    """Record a room (exits + authoritative vendor test). Returns vendor bool."""
    page = sess.page
    if rm in POCKET_MAP:
        return POCKET_MAP[rm].get("vendor", False)
    beat(sess, f"visit_{len(POCKET_MAP):02d}", f"vendor-hunt: arrived {rm!r}")
    v = vendor_works_here(sess)
    POCKET_MAP[rm] = {"exits": current_exits(page), "vendor": v}
    beat(sess, f"vtest_{len(POCKET_MAP):02d}",
         f"vendor test {rm!r}: {'VENDOR' if v else 'no vendor'}")
    return v


def hunt_for_vendor(sess, max_steps: int = 22) -> bool:
    """Combat-aware DFS of the reachable post-tutorial pocket. Records each
    room's exits + authoritative vendor presence (POCKET_MAP). Returns True as
    soon as a real weapon vendor is reached."""
    page = sess.page
    clear_combat(sess)
    send(sess, "look", settle_ms=600)
    start = room_name(page)
    # path stack: list of (room_name, dir_taken_to_get_here)
    path = [(start, None)]
    if _visit(sess, start):
        return True

    for _ in range(max_steps):
        clear_combat(sess)
        rm = room_name(page)
        walked = POCKET_MAP.setdefault(rm, {}).setdefault("_walked", [])
        cur = current_exits(page)
        candidates = [d for d in cur if d not in walked]
        if candidates:
            nxt = candidates[0]
            walked.append(nxt)
            send(sess, nxt, settle_ms=850)
            clear_combat(sess)
            beat(sess, f"move_{nxt}", f"vendor-hunt moved '{nxt}'")
            new_rm = room_name(page)
            if new_rm != rm:
                path.append((new_rm, nxt))
                if _visit(sess, new_rm):
                    return True
        else:
            # dead end here — backtrack via the opposite of how we arrived
            if len(path) <= 1:
                break
            _, came_via = path.pop()
            back = _OPPOSITE.get(came_via) if came_via else None
            if not back or back not in current_exits(page):
                # fall back to any exit
                ce = current_exits(page)
                back = ce[0] if ce else None
            if not back:
                break
            send(sess, back, settle_ms=800)
            clear_combat(sess)
            beat(sess, f"back_{back}", f"vendor-hunt backtrack '{back}'")

    return any(v.get("vendor") for v in POCKET_MAP.values())


def try_buy(sess) -> tuple[str | None, str, str]:
    """Try to buy an affordable vendor_stocked weapon. Returns
    (weapon_bought_or_None, credits_before, credits_after)."""
    page = sess.page
    for name, _cost in BUYABLE:
        before = _credits(page)
        send(sess, f"buy {name}", settle_ms=900)
        feed = _txt(page, "#ground-feed-col").lower()
        after = _credits(page)
        bought = (before != after) or ("you buy" in feed
                                       or "purchased" in feed
                                       or "you now wield" in feed
                                       or "equipped" in feed)
        beat(sess, f"buy_{name.replace(' ', '_')}",
             f"attempted 'buy {name}'")
        note_credit(f"buy {name}", before, after, "debit")
        if bought and before != after:
            return name, before, after
        # If the room has no vendor at all, stop trying more weapons.
        if "no merchant here sells weapons" in feed or "find a shop" in feed:
            return None, before, after
    return None, _credits(page), _credits(page)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        try:
            old.unlink()
        except Exception:
            pass

    with BreakItSession(headless=True, label="economy") as sess:
        page = sess.page
        info = sess.new_player()
        print(f"[play] new player: {info}", flush=True)
        page.wait_for_timeout(900)

        # ── BEAT 1: spawn + starting credits ──────────────────────────
        send(sess, "look")
        r0 = beat(sess, "01_spawn", "fresh new player at spawn; look")
        start_credits = _credits(page)
        print(f"[play] starting credits = {start_credits!r}", flush=True)
        # Reachability/UX note: tutorial relies on TYPED exits — is the
        # mini-map exit strip empty here (no click-to-move)?
        if r0.get("feed_exits") and not r0.get("mini_exits"):
            FINDINGS.append({
                "beat": "1 (spawn / tutorial)", "kind": "stuck-ui",
                "detail": "Tutorial room shows 'Exits: east' in prose but the "
                          "mini-map exit strip (#g-map-exits) has NO clickable "
                          "buttons and window.lastExits is empty — a player who "
                          "navigates by clicking can't move; must type 'east'.",
                "severity": "low",
            })

        # ── walk the tutorial out to the city ─────────────────────────
        left = False
        try:
            left = walk_tutorial(sess)
        except Exception as e:
            print(f"[play] walk_tutorial err: {e}", flush=True)
        print(f"[play] left tutorial = {left}", flush=True)
        clear_combat(sess)
        beat(sess, "post_tutorial", f"after tutorial walk; left={left}")

        # ════════════════════════════════════════════════════════════════
        # PART A — the reachable economy commands, run NOW (in the cantina,
        # a SAFE room) before the vendor hunt provokes the pocket's mobs.
        # This captures clean output for weapons/browse/buy/inv/sell/
        # housing/commissary even though no vendor is reachable.
        # ════════════════════════════════════════════════════════════════

        # weapons — open-market catalog (works anywhere)
        send(sess, "weapons")
        beat(sess, "weapons_list", "typed 'weapons' (buyable catalog)")

        # browse — player vendor droids in room (expect none here)
        send(sess, "browse")
        beat(sess, "browse", "typed 'browse' (player vendor droids here)")

        # buy — no NPC vendor in the cantina; expect a clear refusal
        bbefore = _credits(page)
        send(sess, "buy hold-out blaster")
        beat(sess, "buy_attempt", "typed 'buy hold-out blaster' (no vendor here)")
        note_credit("buy (no vendor)", bbefore, _credits(page), "no-change")

        # +inv — inventory modal; confirm it renders + close it
        send(sess, "+inv")
        beat(sess, "inventory", "typed '+inv' (inventory modal)")
        _close_modals(page)
        if looks_like_json(_txt(page, "#ground-feed-col")):
            FINDINGS.append({"beat": "+inv", "kind": "raw-json",
                             "detail": "+inv dumped raw JSON to the feed.",
                             "severity": "high"})

        # sell — fresh char has no equipped weapon; expect a clear message
        sbefore = _credits(page)
        send(sess, "sell")
        beat(sess, "sell", "typed 'sell' (sell equipped weapon)")
        note_credit("sell", sbefore, _credits(page), "no-change")
        if looks_like_json(_txt(page, "#ground-feed-col")):
            FINDINGS.append({"beat": "sell", "kind": "raw-json",
                             "detail": "sell dumped raw JSON to the feed.",
                             "severity": "high"})

        # housing — status + available lots
        send(sess, "housing")
        beat(sess, "housing", "typed 'housing' (status + lots)")
        if looks_like_json(_txt(page, "#ground-feed-col")):
            FINDINGS.append({"beat": "housing", "kind": "raw-json",
                             "detail": "housing dumped raw JSON.",
                             "severity": "high"})

        # housing list — owned homes (expect none for a new player)
        send(sess, "housing list")
        beat(sess, "housing_list", "typed 'housing list'")

        # +commissary — faction requisition vendor
        send(sess, "+commissary")
        beat(sess, "commissary", "typed '+commissary'")

        # final +inv reconcile (credits unchanged from start+50 drink)
        send(sess, "+inv")
        beat(sess, "final_inv", "final '+inv' reconcile")
        _close_modals(page)

        # ════════════════════════════════════════════════════════════════
        # PART B — vendor reachability proof: DFS the pocket for an NPC
        # weapon vendor. (Runs LAST because the pocket has aggressive mobs
        # that lock movement — keeps Part A captures clean.)
        # ════════════════════════════════════════════════════════════════
        vendor_found = False
        if left:
            try:
                vendor_found = hunt_for_vendor(sess)
            except Exception as e:
                print(f"[play] hunt_for_vendor err: {e}", flush=True)
        print(f"[play] vendor_found = {vendor_found}", flush=True)
        reachable = sorted(r for r in POCKET_MAP.keys())
        print(f"[play] reachable pocket rooms = {reachable}", flush=True)
        if not (left and vendor_found):
            FINDINGS.append({
                "beat": "navigation (tutorial graduation -> shop)",
                "kind": "unreachable",
                "detail": (
                    "A fresh new player who graduates the Tatooine desert "
                    "tutorial lands in a small reachable pocket with NO weapon "
                    "vendor — even though the graduation NPC (Kessa) explicitly "
                    "tells them: \"Head to Kayson's Weapon Shop in the market "
                    "district.\" Reachable rooms explored (all vendor=False): "
                    f"{reachable}. left_tutorial={left}, vendor_found="
                    f"{vendor_found}. Economy buy/sell at an NPC vendor was "
                    "unreachable for this player."),
                "severity": "high",
            })

        browser_defects = [d.as_dict() for d in sess.defects()]

    # ── summary ────────────────────────────────────────────────────────
    print("\n========== PLAY MANIFEST ==========", flush=True)
    for rec in MANIFEST:
        print(f"  {rec['n']:02d} {rec['label']:22s} "
              f"png={rec.get('png','-'):24s} room={rec.get('room','-')!r} "
              f"credits={rec.get('credits','-')}", flush=True)

    print("\n========== CREDIT LOG ==========", flush=True)
    print(f"  starting credits = {start_credits!r}", flush=True)
    for c in CREDIT_LOG:
        same = c["before"] == c["after"]
        print(f"  [{c['beat']:>16}] expect={c['expect']:<6} "
              f"{c['before']!r} -> {c['after']!r} "
              f"{'(UNCHANGED!)' if same else 'changed'}", flush=True)

    print("\n========== REACHABLE POCKET MAP ==========", flush=True)
    for rm, info in POCKET_MAP.items():
        print(f"  {rm!r}: exits={info.get('exits')} "
              f"vendor={info.get('vendor')}", flush=True)

    print("\n========== HEURISTIC FINDINGS ==========", flush=True)
    for f in FINDINGS:
        print(f"  !! {json.dumps(f)}", flush=True)
    if not FINDINGS:
        print("  (none — judge artifacts by eye)", flush=True)

    print("\n========== BROWSER-LAYER DEFECTS ==========", flush=True)
    for d in browser_defects:
        print(f"  !! {json.dumps(d)}", flush=True)
    if not browser_defects:
        print("  (none)", flush=True)

    summary = {"manifest": MANIFEST, "start_credits": start_credits,
               "credit_log": CREDIT_LOG, "findings": FINDINGS,
               "pocket_map": POCKET_MAP, "browser_defects": browser_defects}
    (OUT / "_summary.json").write_text(json.dumps(summary, indent=2),
                                       encoding="utf-8")
    print(f"\n[play] artifacts in {OUT}", flush=True)
    print(f"[play] summary -> {OUT / '_summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
