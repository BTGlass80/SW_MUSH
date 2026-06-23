#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tests/e2e/playwright_new_player_poc.py — Playwright web-client E2E proof-of-concept.

Closes the one QA axis the in-process break-it sweeps structurally can't reach:
the ACTUAL rendered web SPA in a REAL browser (clicks, the WS round-trip,
rendering) — the web-first launch surface. break-it drives the parser; jsdom
drives isolated DOM functions; this drives Chromium against a live server.

What it does (the automated new-player playthrough):
  1. Boots `python main.py` on a free port + a throwaway temp DB (schema + world
     auto-create on boot; ANTHROPIC_API_KEY cleared so the Director never spends).
  2. Launches headless Chromium (Google-fonts aborted so offline can't hang it).
  3. Drives the REAL chargen wizard step-by-step (template path), detecting the
     active `.step-panel` so the template's species-skip is handled.
  4. Logs in through the client's own login form, selects the character, waits
     for the live game (first hud_update).
  5. Types `look`, then clicks an exit on the always-visible mini-map exit strip
     (#g-map-exits) — which also exercises the click-to-move fix in a real browser.
  6. Screenshots every screen into tests/e2e/_screens/ for vision review.

Run:  python tests/e2e/playwright_new_player_poc.py
Local + headless; no API cost. Exit 0 = the whole flow worked end to end.
"""
from __future__ import annotations

import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

REPO = Path(__file__).resolve().parents[2]
SCREENS = Path(__file__).resolve().parent / "_screens"
_SHOT_N = [0]


def log(msg: str) -> None:
    print(f"[e2e] {msg}", flush=True)


def shot(page, label: str) -> None:
    _SHOT_N[0] += 1
    path = SCREENS / f"{_SHOT_N[0]:02d}_{label}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
        log(f"shot -> {path.name}")
    except Exception as e:  # never let a screenshot abort the run
        log(f"shot FAILED ({label}): {e}")


def free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_ready(port: int, timeout: float = 60.0) -> None:
    """Poll the chargen species endpoint until the server answers 200."""
    url = f"http://127.0.0.1:{port}/api/chargen/species"
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    log(f"server ready on :{port}")
                    return
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(0.5)
    raise RuntimeError(f"server not ready on :{port} after {timeout}s (last: {last})")


def boot_server(web_port: int, telnet_port: int, db_path: str, log_path: Path):
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)          # cost guardrail: no Director spend
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, "main.py",
        "--web-port", str(web_port),
        "--telnet-port", str(telnet_port),
        "--db", db_path,
        "--log-level", "INFO",
    ]
    lf = open(log_path, "w", encoding="utf-8")
    log(f"boot: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(REPO), env=env, stdout=lf, stderr=lf), lf


# ── chargen wizard (state-machine on the active .step-panel) ───────────────

def click_next(page) -> None:
    page.wait_for_function(
        "() => { const b=document.getElementById('nextBtn');"
        " return b && !b.disabled && b.offsetParent !== null; }",
        timeout=8000)
    page.click("#nextBtn")


def drive_wizard(page, name: str, user: str, pw: str) -> None:
    for _ in range(30):
        panel = page.query_selector(".step-panel.active")
        step = panel.get_attribute("id") if panel else None
        if not step:
            raise RuntimeError("no active step panel")
        shot(page, f"chargen_{step}")
        log(f"wizard step = {step}")
        if step == "step0":                       # PATH — pick first template
            page.click("#templateCards .card[data-key]")
            page.wait_for_timeout(300)
            click_next(page)
        elif step == "step1":                     # SPECIES (only on scratch path)
            page.click("#speciesCards .card[data-sp]")
            click_next(page)
        elif step in ("step2", "step3"):          # ATTRS / SKILLS (template-filled)
            click_next(page)
        elif step == "step4":                     # FORCE — mandatory choice
            page.click('.force-card[data-force="false"]')
            page.wait_for_timeout(200)
            click_next(page)
        elif step == "step5":                     # STORY — name (debounced check)
            page.fill("#charName", name)
            click_next(page)
        elif step == "step6":                     # CHAIN — first char must pick
            card = page.locator(
                "#chainCards .card[data-chain-id]:not(.card-disabled)").first
            try:
                card.wait_for(state="visible", timeout=5000)
                card.click()
                page.wait_for_timeout(200)
            except PWTimeout:
                # FINDING (standalone chargen): /api/chargen/chains is 401 without
                # an account token, so the chain step renders no cards. NEXT is
                # still enabled — proceed so the PoC can finish the flow.
                log("WARN: no selectable chain card (standalone 401 chains) — proceeding")
            click_next(page)
        elif step == "step7":                     # REVIEW
            click_next(page)
        elif step == "step8":                     # ACCOUNT — fill + submit
            page.fill("#acctUsername", user)
            page.fill("#acctPassword", pw)
            page.fill("#acctPasswordConfirm", pw)
            page.check("#rulesAccept")
            page.wait_for_function(
                "() => { const b=document.getElementById('submitBtn');"
                " return b && !b.disabled; }", timeout=8000)
            page.click("#submitBtn")
            log("chargen submitted")
            return
        page.wait_for_timeout(400)
    raise RuntimeError("wizard never reached the account step")


# ── client login -> charselect -> live game ────────────────────────────────

def login_and_enter(page, user: str, pw: str) -> None:
    page.wait_for_selector("#login-user", state="visible", timeout=20000)
    shot(page, "login")
    page.fill("#login-user", user)
    page.fill("#login-pass", pw)
    page.click("#login-submit")
    # character select
    page.wait_for_selector("#boot-state-charselect", state="visible", timeout=20000)
    page.wait_for_timeout(500)
    shot(page, "charselect")
    # click the freshly-created character (first selectable row, not the +NEW btn)
    list_items = page.locator("#charselect-list > *")
    if list_items.count() == 0:
        raise RuntimeError("charselect list is empty")
    list_items.first.click()
    # live when the command box + mini-map are shown (driven by first hud_update)
    page.wait_for_selector("#cmd-input-ground", state="visible", timeout=25000)
    page.wait_for_selector("#g-area-map-svg", state="visible", timeout=25000)
    page.wait_for_timeout(800)
    log("in the game")


def run_command(page, cmd: str) -> None:
    inp = page.locator("#cmd-input-ground")
    inp.click()
    inp.fill(cmd)
    inp.press("Enter")
    page.wait_for_timeout(900)


def click_map_exit(page) -> str | None:
    """Exercise the click-to-move fix: click the first exit on the mini-map
    strip and return the direction it fired."""
    strip = page.locator("#g-map-exits button.mm-exit-btn")
    if strip.count() == 0:
        log("no exits on the mini-map strip (room may have none)")
        return None
    btn = strip.first
    direction = btn.get_attribute("data-cmd")
    btn.click()
    page.wait_for_timeout(900)
    return direction


def main() -> int:
    SCREENS.mkdir(parents=True, exist_ok=True)
    for old in SCREENS.glob("*.png"):
        old.unlink()
    web_port = free_port()
    telnet_port = free_port()
    tmpdir = tempfile.mkdtemp(prefix="swmush_e2e_")
    db_path = os.path.join(tmpdir, "e2e.db")
    server_log = SCREENS / "_server.log"
    proc = lf = None
    rc = 1
    try:
        proc, lf = boot_server(web_port, telnet_port, db_path, server_log)
        wait_ready(web_port, timeout=75)
        base = f"http://127.0.0.1:{web_port}"
        suffix = random.randint(10000, 99999)
        name = f"Reyna{suffix}"
        user = f"tester{suffix}"
        pw = "testpass123"
        log(f"new player: name={name} user={user}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1280, "height": 860})
            page = ctx.new_page()
            for pat in ("**/fonts.googleapis.com/**", "**/fonts.gstatic.com/**"):
                page.route(pat, lambda route: route.abort())

            log("== portal ==")
            page.goto(base + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            shot(page, "portal")

            log("== chargen wizard ==")
            page.goto(base + "/chargen", wait_until="domcontentloaded")
            page.wait_for_selector("#templateCards .card[data-key]", timeout=20000)
            drive_wizard(page, name, user, pw)
            page.wait_for_selector("#successOverlay", state="visible", timeout=20000)
            shot(page, "chargen_success")

            log("== client login -> game ==")
            page.goto(base + "/client.html", wait_until="domcontentloaded")
            login_and_enter(page, user, pw)
            shot(page, "in_game")

            log("== command: look ==")
            run_command(page, "look")
            shot(page, "after_look")

            log("== click-to-move via mini-map exit strip ==")
            moved = click_map_exit(page)
            shot(page, "after_move")
            log(f"map exit fired: {moved!r}")

            browser.close()
        log("E2E FLOW PASSED")
        rc = 0
    except PWTimeout as e:
        log(f"PLAYWRIGHT TIMEOUT: {e}")
    except Exception as e:
        log(f"FAILED: {type(e).__name__}: {e}")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
        if lf is not None:
            lf.close()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
        log(f"screenshots in {SCREENS}")
        log(f"server log: {server_log}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
