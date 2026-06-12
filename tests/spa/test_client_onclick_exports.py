"""
test_client_onclick_exports.py — Webify bugfix drop 3 (2026-06-11).

THE CLASS: static/client.html's entire inline script is a strict-mode
IIFE, so functions defined there are CLOSURE-scoped — but inline
``onclick="..."`` attributes resolve in GLOBAL scope at click time.
Any handler referenced from markup without a ``window.NAME = NAME``
export is a silently dead button (console ReferenceError, no UI effect).

Found live by Brian on the UI-7 first-run tour (NEXT / SKIP TOUR did
nothing); the audit then showed the whole Webify modal wave shipped the
same gap: inventory, shop, board, craft, and city modal close/backdrop
handlers were all dead — 12 handlers total. ESC paths worked
(addEventListener inside the IIFE), which is why the modals seemed fine.

Tests here:
  1. A whole-file SWEEP that makes the class unrepresentable: every
     function invoked from an inline onclick must be window-exported in
     client.html or provided as a global by a loaded external script.
  2. Instance pins for the 12 repaired handlers.
  3. A DYNAMIC jsdom test (runScripts: 'dangerously' — attribute
     handlers only execute in that mode) that extracts the REAL tour JS
     + the REAL action-button markup from client.html at test time,
     dispatches actual clicks, and verifies advance / skip / replay /
     localStorage semantics end-to-end through the onclick path.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
NODE_MODULES = "/tmp/node_modules"


# ──────────────────────────────────────────────────────────────────────
# Parsing helpers
# ──────────────────────────────────────────────────────────────────────

def _onclick_names(html: str) -> set[str]:
    """Function names invoked from inline onclick attributes.

    The negative lookbehind skips method calls (``event.stopPropagation()``,
    ``el.remove()``) — only bare identifiers resolve against window.
    """
    names: set[str] = set()
    for m in re.finditer(r'onclick="([^"]*)"', html):
        for call in re.finditer(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)\s*\(",
                                m.group(1)):
            if call.group(1) != "event":
                names.add(call.group(1))
    return names


def _window_exports(src: str) -> set[str]:
    return set(re.findall(r"window\.([A-Za-z_][A-Za-z0-9_]*)\s*=", src))


def _external_globals() -> set[str]:
    out: set[str] = set()
    for path in list((REPO_ROOT / "static").glob("*.js")) + \
            list((REPO_ROOT / "static" / "spa").glob("*.js")):
        src = path.read_text(encoding="utf-8")
        out |= _window_exports(src)
        out |= set(re.findall(r"^function\s+([A-Za-z_][A-Za-z0-9_]*)",
                              src, re.M))
    return out


# ──────────────────────────────────────────────────────────────────────
# 1. The sweep — class unrepresentable
# ──────────────────────────────────────────────────────────────────────

def test_every_inline_onclick_handler_is_window_visible():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    missing = sorted(
        _onclick_names(html) - _window_exports(html) - _external_globals())
    assert missing == [], (
        "Dead button(s): these inline onclick handlers are defined inside "
        "the strict IIFE but never exported — clicking them is a silent "
        f"ReferenceError. Add `window.NAME = NAME;` for: {missing}")


# ──────────────────────────────────────────────────────────────────────
# 2. Instance pins — the 12 repaired handlers
# ──────────────────────────────────────────────────────────────────────

REPAIRED = [
    "advanceOnboardTour", "endOnboardTour", "showOnboardTour",
    "closeInventoryModal", "invModalBackdropClick",
    "closeShopModal", "shopModalBackdropClick",
    "closeBoardModal", "boardModalBackdropClick",
    "closeCraftModal", "craftModalBackdropClick",
    "closeCityModal",
]


def test_repaired_handlers_exported():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    exports = _window_exports(html)
    not_exported = [n for n in REPAIRED if n not in exports]
    assert not_exported == [], not_exported


def test_repaired_handlers_still_referenced_by_markup():
    # Guards the pins above against rot: if markup stops using a handler
    # the pin should be retired consciously, not silently.
    html = CLIENT_HTML.read_text(encoding="utf-8")
    used = _onclick_names(html)
    unused = [n for n in REPAIRED if n not in used]
    assert unused == [], unused


# ──────────────────────────────────────────────────────────────────────
# 3. Dynamic: real clicks through the onclick path (tour semantics)
# ──────────────────────────────────────────────────────────────────────

def _extract_tour_js(html: str) -> str:
    start = html.index("var ONBOARD_TOUR_KEY")
    end_marker = "window.endOnboardTour = endOnboardTour;"
    end = html.index(end_marker) + len(end_marker)
    return html[start:end]


def _extract_tour_actions_markup(html: str) -> str:
    m = re.search(
        r'<div class="m3o-tour-actions">.*?</div>', html, re.S)
    assert m, "tour actions markup not found in client.html"
    return m.group(0)


def test_tour_buttons_click_through_real_onclick_path():
    if shutil.which("node") is None:
        pytest.skip("node not available")
    if not Path(NODE_MODULES, "jsdom").exists():
        pytest.skip(f"jsdom not installed at {NODE_MODULES}/jsdom")

    html = CLIENT_HTML.read_text(encoding="utf-8")
    tour_js = _extract_tour_js(html)
    actions = _extract_tour_actions_markup(html)

    doc = f"""<!doctype html><html><body>
      <div id="cmd-bar-ground"></div>
      <div id="qa-row"></div>
      <div id="g-objective"></div>
      <div id="onboard-panel"></div>
      <div class="m3o-tour-overlay" id="m3o-tour-overlay">
        <div class="m3o-tour-ring" id="m3o-tour-ring"></div>
        <div class="m3o-tour-card" id="m3o-tour-card">
          <div class="m3o-tour-step" id="m3o-tour-step"></div>
          <div class="m3o-tour-text" id="m3o-tour-text"></div>
          {actions}
        </div>
      </div>
    </body></html>"""

    wrapper = f"""
        var {{ JSDOM }} = require('{NODE_MODULES}/jsdom');
        var dom = new JSDOM({json.dumps(doc)}, {{
            url: 'http://localhost/',
            runScripts: 'dangerously',   // attribute handlers need this
            pretendToBeVisual: true
        }});
        var w = dom.window;
        // jsdom computes offsetParent as null (no layout); the tour uses
        // it for visibility — patch like a laid-out page.
        Object.defineProperty(w.HTMLElement.prototype, 'offsetParent',
            {{ get() {{ return this.parentElement; }}, configurable: true }});
        w.eval('function $(id) {{ return document.getElementById(id); }}');
        w.eval({json.dumps(tour_js)});

        var out = {{}};
        out.typeof_advance = typeof w.advanceOnboardTour;
        out.typeof_end     = typeof w.endOnboardTour;
        out.typeof_show    = typeof w.showOnboardTour;

        w.showOnboardTour(true);
        var ov = w.document.getElementById('m3o-tour-overlay');
        out.shown = ov.classList.contains('show');
        out.step1 = w.document.getElementById('m3o-tour-step').textContent;

        // REAL click on the NEXT button — exercises the onclick attribute.
        w.document.getElementById('m3o-tour-next').click();
        out.step2 = w.document.getElementById('m3o-tour-step').textContent;

        // REAL click on SKIP TOUR.
        w.document.querySelector('.m3o-tour-btn.skip').click();
        out.hidden_after_skip = !ov.classList.contains('show');
        out.ls = w.localStorage.getItem('m3_onboard_tour_done');

        // maybeShow must now be a no-op (seen flag) …
        w.maybeShowOnboardTour();
        out.stays_hidden = !ov.classList.contains('show');
        // … but the TRAINING-head ? (force replay) must still work.
        w.showOnboardTour(true);
        out.replay_shows = ov.classList.contains('show');

        process.stdout.write(JSON.stringify(out));
    """
    proc = subprocess.run(["node", "-e", wrapper], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    assert out["typeof_advance"] == "function"
    assert out["typeof_end"] == "function"
    assert out["typeof_show"] == "function"
    assert out["shown"] is True
    assert out["step1"] == "1 / 4"
    assert out["step2"] == "2 / 4", (
        "NEXT click did not advance the tour — the exact bug Brian hit")
    assert out["hidden_after_skip"] is True
    assert out["ls"] == "1"
    assert out["stays_hidden"] is True
    assert out["replay_shows"] is True
