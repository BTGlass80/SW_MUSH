"""
combat_inspector_extract.py — slice the D' rendering block out of
static/client.html and load it into jsdom for regression testing.

Drop 4.3 (Tier 1 #4) — D' regression lock harness, May 26 2026.

The D' inspector code (handleCombatResolutionEvent, buildCombatResultRow,
buildDieChip, the build*Section helpers) lives inside client.html's
inline IIFE. We can't `eval` the whole file in jsdom because client.html
has a pre-existing syntax bug at lines ~7434 (orphaned showToast body —
documented in 4.2b §6, queued as a separate hotfix drop). So we extract
just the D' chunk via comment markers, prepend stubs for its external
dependencies, and eval that subset.

Markers in client.html (DON'T rename without updating this file):
    /* DROP-D'-TEST-EXTRACT-START
       ...
    */
    var combatEventFingerprints = [];
    ...
    if (typeof window !== 'undefined') {
      window._sw_buildCombatResultRow = buildCombatResultRow;
      ...
    }
    /* DROP-D'-TEST-EXTRACT-END */

External symbols the slice references that we must stub:
    escapeHtml         — HTML-escape utility; trivial mirror sufficient
    stripAnsi          — ANSI escape stripper; trivial mirror sufficient
    lastHud            — global; tests set lastHud.character_id explicitly
    appendEvent        — side-effect; only used by handleCombatResolutionEvent
    rememberActorName  — side-effect; only used by handleCombatResolutionEvent
    isSelfName         — defensive; not actually called by the slice
"""
from __future__ import annotations

import re
import shutil
import subprocess
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
NODE_MODULES = "/tmp/node_modules"


# ── Stubs prepended before the extracted D' block ────────────────────
# These mirror the minimal contract of the symbols the slice references
# from elsewhere in client.html. Where the production code's helper
# has rich behavior, the stub captures the relevant subset (e.g.,
# escapeHtml's HTML escaping for the 5 chars buildCombatHeadlineHtml
# would care about).
STUBS_JS = r"""
// Minimal stubs for symbols the extracted D' block references but
// that live outside the extract zone.
function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function stripAnsi(s) {
  return String(s == null ? '' : s).replace(/\x1b\[[0-9;]*m/g, '');
}
// Side-effect symbols used by handleCombatResolutionEvent only.
// Tests that exercise that function should override these stubs to
// capture the calls; tests of buildCombatResultRow / buildDieChip
// don't touch these.
var _appended = [];
function appendEvent(ev) { _appended.push(ev); }
function rememberActorName(name) { /* no-op for tests */ }
function isSelfName(name) { return false; /* tests override per-case */ }
// lastHud is the global combat-state proxy; tests set its character_id
// to make role assignment deterministic.
var lastHud = { character_id: null, name: '' };
"""


def require_node_and_jsdom() -> None:
    if shutil.which("node") is None:
        pytest.skip("node not available")
    if not Path(NODE_MODULES, "jsdom").exists():
        pytest.skip(f"jsdom not installed at {NODE_MODULES}/jsdom")


def extract_d_prime_block() -> str:
    """Read client.html, slice out the D' block via markers, return the
    raw JS. Fails the calling test with a clear error if markers are
    missing or out of order.

    Subtlety: the START marker's own comment body contains the literal
    string 'DROP-D'-TEST-EXTRACT-END' as part of its explanatory text.
    So END must be searched for AFTER the START comment closes.
    """
    src = CLIENT_HTML.read_text(encoding="utf-8")
    start_m = re.search(r"DROP-D'-TEST-EXTRACT-START", src)
    if not start_m:
        pytest.fail(
            "DROP-D'-TEST-EXTRACT-START marker missing from client.html"
        )
    # Walk past START's enclosing '*/' to get to actual code
    after_start = src.find("*/", start_m.end())
    if after_start < 0:
        pytest.fail("DROP-D'-TEST-EXTRACT-START comment isn't closed")
    code_start = after_start + 2  # past the */

    # Now search for END *after* the START comment has closed.
    end_m = re.search(r"DROP-D'-TEST-EXTRACT-END", src[code_start:])
    if not end_m:
        pytest.fail(
            "DROP-D'-TEST-EXTRACT-END marker missing from client.html"
        )
    end_abs = code_start + end_m.start()
    # END marker is itself inside a comment '/* ... */'; back up to '/*'
    end_comment_open = src.rfind("/*", code_start, end_abs)
    if end_comment_open < 0:
        pytest.fail("DROP-D'-TEST-EXTRACT-END comment open not found")
    code_end = end_comment_open
    extracted = src[code_start:code_end]
    if len(extracted) < 1000:
        pytest.fail(
            f"D' extraction produced suspiciously short block "
            f"({len(extracted)} bytes). Markers may be in the wrong "
            f"order or block contents changed."
        )
    return extracted


def run_with_d_prime_block(setup_js: str, extra_stubs: str = "") -> dict:
    """Run the D' block + setup_js under jsdom. Returns parsed result.

    setup_js executes after the D' block loads; it must set `result`
    to a JSON-serializable value (no DOM elements; extract .tagName,
    .className, .getAttribute(), .textContent etc.).

    extra_stubs is JS prepended BEFORE STUBS_JS — use it to override
    stub behavior (e.g., to swap appendEvent for a capturing version).
    """
    require_node_and_jsdom()

    block = extract_d_prime_block()
    # Compose the full script: stubs + block + setup
    full_js = (
        "// ─── test-extra stubs ─────────────────────────────────\n"
        + extra_stubs
        + "\n// ─── default stubs ────────────────────────────────────\n"
        + STUBS_JS
        + "\n// ─── extracted D' block from client.html ──────────────\n"
        + block
        + "\n// ─── test setup ───────────────────────────────────────\n"
        + setup_js
    )

    # Write to a temp file so we don't have to escape JS for the node -e
    # command line. Use Python's tempfile module via the simpler mkstemp
    # pattern that jsdom-harness uses.
    import tempfile, os
    fd, tmppath = tempfile.mkstemp(suffix=".js", prefix="d_prime_extract_")
    os.close(fd)
    try:
        with open(tmppath, "w", encoding="utf-8") as f:
            f.write(full_js)
        wrapper = f"""
            var {{ JSDOM }} = require('{NODE_MODULES}/jsdom');
            var fs = require('fs');
            var dom = new JSDOM('<!doctype html><html><body></body></html>', {{
                runScripts: 'outside-only',
                pretendToBeVisual: true
            }});
            var window = dom.window;
            var document = window.document;
            var src = fs.readFileSync({json.dumps(tmppath)}, 'utf8');
            // Inject the document/window globals before eval so the
            // extracted block's document.createElement calls find them.
            // The setup_js sets `result`.
            var result;
            (function() {{
                window.eval(src);
                result = window.__d_prime_result;
            }}).call(window);
            process.stdout.write(JSON.stringify(result));
        """
        proc = subprocess.run(
            ["node", "-e", wrapper],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode != 0:
            pytest.fail(
                f"node exited {proc.returncode}\n"
                f"stderr:\n{proc.stderr}\n"
                f"stdout:\n{proc.stdout}\n"
                f"(extracted block size: {len(block)} bytes)"
            )
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            pytest.fail(
                f"D' harness output not JSON: {e}\n"
                f"stdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            )
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass
