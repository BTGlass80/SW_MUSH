# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_harness.py — reusable REAL-BROWSER break-it harness.

The Playwright PoC (playwright_new_player_poc.py) drives ONE happy-path flow as a
regression gate. This harness turns that scaffolding into an ADVERSARIAL break-it
tool: it boots a live server + Chromium, gets you into the game, and -- the part
nothing else can do -- AUTOMATICALLY CAPTURES browser-layer breakage that the
in-process parser break-it and the jsdom unit tests structurally cannot see:

  * uncaught JS exceptions in the SPA          (page "pageerror")   <- the big one
  * console.error output                        (page "console")
  * HTTP 5xx responses from any XHR/fetch/WS    (page "response")
  * outright failed requests                    (page "requestfailed")
  * websocket frames carrying an error/500      (page "websocket")

A scenario drives the `page` however it likes (malformed chargen input, rapid
double-clicks, out-of-order actions, disconnect/reconnect, huge/injection input,
clicking disabled/hidden controls) and then calls `session.defects()` -- any
captured browser-layer fault is a finding the happy-path gate would never surface.

USAGE (the pattern the break-it Workflow agents follow) -- one standalone script
per surface, booting its own isolated server+browser+DB on free ports:

    from tests.e2e.breakit_harness import BreakItSession, run_scenarios

    def s_smoke(sess):
        sess.new_player()                 # portal -> chargen -> login -> in game
        sess.send("look")
        sess.send("x" * 5000)             # adversarial: huge input
        sess.send(";;;@@@##")             # adversarial: junk
        # any uncaught JS exception / console.error / 5xx is auto-recorded

    if __name__ == "__main__":
        sys.exit(run_scenarios("ground-commands", [s_smoke]))

`run_scenarios` prints a single JSON report ({surface, scenarios:[{name, ok,
defects:[...], error}]}) and exits non-zero if ANY scenario recorded a defect or
threw -- so an agent runs it via Bash and reads the JSON straight back.

Local + headless, no API cost (ANTHROPIC_API_KEY is cleared so the Director never
spends). Requires Chromium: `python -m playwright install chromium`
(Norton-TLS box: prefix `NODE_OPTIONS=--use-system-ca`).
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Reuse the PoC's proven boot + chargen + login helpers (page-level, importable;
# importing the module does NOT run its main()).
from tests.e2e.playwright_new_player_poc import (  # noqa: E402
    free_port, wait_ready, boot_server, drive_wizard, login_and_enter, run_command,
)


def _log(msg: str) -> None:
    print(f"[breakit] {msg}", flush=True)


class Defect:
    """One captured browser-layer fault."""
    __slots__ = ("kind", "detail", "where")

    def __init__(self, kind: str, detail: str, where: str = ""):
        self.kind = kind          # pageerror | console.error | http5xx | requestfailed | ws
        self.detail = detail
        self.where = where

    def as_dict(self) -> dict:
        return {"kind": self.kind, "detail": self.detail[:1200], "where": self.where[:300]}


class BreakItSession:
    """Boots a live server + Chromium, auto-captures browser-layer defects.

    Use as a context manager. The `page` attribute is the live Playwright page;
    drive it however the scenario needs. `defects()` returns everything captured
    so far. `new_player()` is a convenience that walks portal->chargen->login->game.
    """

    # console.error noise that is not a defect (best-effort allowlist; kept tight
    # so we don't mask real faults). Add only proven-benign, app-irrelevant spam.
    _CONSOLE_IGNORE = (
        "Failed to load resource: net::ERR_FAILED",          # we abort google-fonts
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "favicon.ico",
    )

    def __init__(self, headless: bool = True, label: str = "breakit",
                 ignore_5xx_paths: tuple = ()):
        self.label = label
        self.headless = headless
        self.ignore_5xx_paths = ignore_5xx_paths
        self._defects: list[Defect] = []
        self.page = None
        self.base = None
        self._pw = self._browser = self._ctx = None
        self._proc = self._lf = None
        self._tmpdir = None

    # ── lifecycle ──────────────────────────────────────────────────────────
    def __enter__(self) -> "BreakItSession":
        web_port, telnet_port = free_port(), free_port()
        self._tmpdir = tempfile.mkdtemp(prefix=f"swmush_breakit_{self.label}_")
        db_path = os.path.join(self._tmpdir, "breakit.db")
        log_path = Path(self._tmpdir) / "_server.log"
        self._proc, self._lf = boot_server(web_port, telnet_port, db_path, log_path)
        wait_ready(web_port, timeout=90)
        self.base = f"http://127.0.0.1:{web_port}"

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._ctx = self._browser.new_context(viewport={"width": 1280, "height": 860})
        self.page = self._ctx.new_page()
        for pat in ("**/fonts.googleapis.com/**", "**/fonts.gstatic.com/**"):
            self.page.route(pat, lambda route: route.abort())
        self._attach_listeners(self.page)
        return self

    def __exit__(self, *exc):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except Exception:
                self._proc.kill()
        if self._lf is not None:
            try:
                self._lf.close()
            except Exception:
                pass
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        return False

    # ── defect capture ────────────────────────────────────────────────────
    def _attach_listeners(self, page) -> None:
        def on_pageerror(exc):
            self._defects.append(Defect("pageerror", str(exc), page.url))

        def on_console(msg):
            if msg.type != "error":
                return
            text = msg.text or ""
            if any(ig in text for ig in self._CONSOLE_IGNORE):
                return
            self._defects.append(Defect("console.error", text, page.url))

        def on_response(resp):
            try:
                if resp.status >= 500:
                    url = resp.url
                    if any(p in url for p in self.ignore_5xx_paths):
                        return
                    self._defects.append(Defect("http5xx", f"{resp.status} {url}", page.url))
            except Exception:
                pass

        def on_requestfailed(req):
            try:
                # Aborted font routes show as failures; ignore those.
                if any(ig in req.url for ig in self._CONSOLE_IGNORE):
                    return
                self._defects.append(
                    Defect("requestfailed", f"{req.failure or '?'} {req.url}", page.url))
            except Exception:
                pass

        page.on("pageerror", on_pageerror)
        page.on("console", on_console)
        page.on("response", on_response)
        page.on("requestfailed", on_requestfailed)

    def defects(self) -> list:
        return list(self._defects)

    def clear_defects(self) -> None:
        self._defects.clear()

    # ── convenience drivers (reuse the PoC helpers) ───────────────────────
    def new_player(self, name: str | None = None) -> dict:
        """Portal -> chargen wizard -> login -> character select -> live game."""
        suffix = random.randint(100000, 999999)
        name = name or f"Brk{suffix}"
        user, pw = f"brk{suffix}", "testpass123"
        self.page.goto(self.base + "/", wait_until="domcontentloaded")
        self.page.wait_for_timeout(300)
        self.page.goto(self.base + "/chargen", wait_until="domcontentloaded")
        self.page.wait_for_selector("#templateCards .card[data-key]", timeout=25000)
        drive_wizard(self.page, name, user, pw)
        self.page.wait_for_selector("#successOverlay", state="visible", timeout=25000)
        self.page.goto(self.base + "/client.html", wait_until="domcontentloaded")
        login_and_enter(self.page, user, pw)
        return {"name": name, "user": user, "pw": pw}

    def send(self, cmd: str, settle_ms: int = 700) -> None:
        """Type a command into the ground command box and submit."""
        run_command(self.page, cmd)
        if settle_ms:
            self.page.wait_for_timeout(settle_ms)

    def goto(self, path: str) -> None:
        self.page.goto(self.base + path, wait_until="domcontentloaded")


def run_scenarios(surface: str, scenarios: list, headless: bool = True) -> int:
    """Run each scenario in its OWN fresh session; print a JSON report; return a
    nonzero exit code if any scenario recorded a defect or threw. Each scenario is
    `def s(session): ...`; its function name (minus a leading 's_') labels it."""
    results = []
    any_bad = False
    for fn in scenarios:
        sname = getattr(fn, "__name__", "scenario")
        sname = sname[2:] if sname.startswith("s_") else sname
        rec = {"name": sname, "ok": True, "defects": [], "error": None}
        try:
            with BreakItSession(headless=headless, label=sname) as sess:
                fn(sess)
                rec["defects"] = [d.as_dict() for d in sess.defects()]
        except PWTimeout as e:
            rec["error"] = f"PWTimeout: {e}"
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
        rec["ok"] = (not rec["defects"]) and (rec["error"] is None)
        any_bad = any_bad or (not rec["ok"])
        _log(f"scenario {sname}: {'OK' if rec['ok'] else 'DEFECT/ERROR'} "
             f"({len(rec['defects'])} defects)")
        results.append(rec)
    print("BREAKIT_REPORT_JSON " + json.dumps({"surface": surface, "scenarios": results}))
    return 1 if any_bad else 0
