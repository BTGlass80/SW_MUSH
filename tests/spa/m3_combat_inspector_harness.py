"""
m3_combat_inspector_harness.py — load static/spa/m3_combat_inspector.js
into jsdom and provide the same test surface the old marker-extract
harness did.

Drop 4.4 (Tier 1 #4) · May 27 2026.

Replaces tests/spa/combat_inspector_extract.py, which sliced the D'
rendering block out of client.html via comment markers. Drop 4.4 moved
that block into a proper SPA module (static/spa/m3_combat_inspector.js),
so the slicing trick is no longer needed. We load the module the same
way every other m3_* module loads — via jsdom + a script-tag include —
and present the same `run_with_d_prime_block(setup_js)` signature so
the existing 29 regression tests need only minimal changes.

What this preserves:
  · The signature run_with_d_prime_block(setup_js, extra_stubs="") -> dict
  · The five ambient symbols the old harness defined (escapeHtml,
    stripAnsi, appendEvent, rememberActorName, lastHud) — they're now
    set up as `var`-bindings in the eval scope AND wired into the
    module via M3CombatInspector.init().
  · The window._sw_* alias surface — set in client.html at runtime;
    the harness mirrors it so tests that read window.buildCombatResultRow
    keep working.
  · The same closure semantics: tests that reassign appendEvent mid-
    setup expect the next handleCombatResolutionEvent call to use the
    new function. The module captures `_appendEvent` at init() time,
    so to make this work, the harness installs a TRAMPOLINE that
    reads the ambient `appendEvent` binding on every call. Same for
    rememberActorName. lastHud is already accessed via the getter
    pattern (getLastHud closes over the binding) so reassigning
    lastHud.character_id continues to work.

Pattern parallels tests/spa/spa_dom_harness.py (Drop 4.1b) — same jsdom
require, same /tmp/node_modules, same tempfile-based script loading.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


REPO_ROOT       = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML     = REPO_ROOT / "static" / "client.html"
INSPECTOR_MODULE = REPO_ROOT / "static" / "spa" / "m3_combat_inspector.js"
# drop 26 (2026-06-13): prefer the repo-local node_modules (where jsdom
# actually lives) over the legacy /tmp location; forward slashes for the
# JS require(). See spa_dom_harness._resolve_node_modules.
def _resolve_node_modules() -> str:
    for c in (REPO_ROOT / "node_modules", Path("/tmp/node_modules")):
        if (c / "jsdom").exists():
            return c.as_posix()
    return (REPO_ROOT / "node_modules").as_posix()


NODE_MODULES    = _resolve_node_modules()


# ── Stubs prepended before the module loads ─────────────────────────
# These mirror the minimal contract of the symbols client.html provides
# at runtime when it calls M3CombatInspector.init(...). Tests can
# override appendEvent / rememberActorName / lastHud by reassigning
# them in the test setup body; the trampolines below pick up the new
# binding on every call.
STUBS_JS = r"""
// Defaults used by the trampolines below — tests reassign these.
var _appended = [];
function appendEvent(ev) { _appended.push(ev); }
function rememberActorName(name) { /* default: no-op */ }
function isSelfName(name) { return false; /* default */ }
var lastHud = { character_id: null, name: '' };

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
"""


# After the module loads, this init+alias block runs. It binds the
# module to the harness stubs via TRAMPOLINES (so a later reassign of
# `appendEvent = ...` in test setup_js takes effect on the next call),
# then exposes the module's named exports on `window` so the test
# setup bodies can still write `window.buildCombatResultRow` /
# `buildCombatResultRow` / `handleCombatResolutionEvent` etc.
INIT_AND_ALIAS_JS = r"""
M3CombatInspector.init({
  // Trampolines — pick up reassigned bindings on every call. The
  // tests do `appendEvent = function(ev){...}` mid-setup and expect
  // the next handleCombatResolutionEvent to call the new function.
  escapeHtml:        function(s) { return escapeHtml(s); },
  stripAnsi:         function(s) { return stripAnsi(s); },
  appendEvent:       function(ev) { return appendEvent(ev); },
  rememberActorName: function(n)  { return rememberActorName(n); },
  getLastHud:        function()   { return lastHud; },
});

// Mirror client.html's runtime aliases so test setup_js bodies that
// call window.buildCombatResultRow / buildCombatResultRow continue to
// work unchanged. Also expose without the window. prefix for setup
// bodies that use the bare name (e.g. recordCombatEventFingerprint(...)).
var buildCombatResultRow      = M3CombatInspector.buildCombatResultRow;
var buildDieChip              = M3CombatInspector.buildDieChip;
var buildCombatHeadlineHtml   = M3CombatInspector.buildCombatHeadlineHtml;
var composeCombatHeadline     = M3CombatInspector.composeCombatHeadline;
var composeCombatMechline     = M3CombatInspector.composeCombatMechline;
var combatVerbForSkill        = M3CombatInspector.combatVerbForSkill;
var handleCombatResolutionEvent = M3CombatInspector.handleCombatResolutionEvent;
var isDuplicateOfRecentCombatEvent = M3CombatInspector.isDuplicateOfRecentCombatEvent;
var recordCombatEventFingerprint   = M3CombatInspector.recordCombatEventFingerprint;
// Module-private dedup state exposed via _internal for the AC10 test
// that reads combatEventFingerprints.length directly. The test calls
// it as a bare identifier; mirror it as a getter property on the
// global object so bare-name reads return a live snapshot. Do NOT
// also declare `var combatEventFingerprints` — that would shadow the
// getter with a captured-at-init snapshot.
Object.defineProperty(window, 'combatEventFingerprints', {
  get: function() { return M3CombatInspector._internal._getFingerprints(); },
  configurable: true,
});

window.buildCombatResultRow      = buildCombatResultRow;
window.buildDieChip              = buildDieChip;
window.buildCombatHeadlineHtml   = buildCombatHeadlineHtml;
window.composeCombatHeadline     = composeCombatHeadline;
window.composeCombatMechline     = composeCombatMechline;
window.combatVerbForSkill        = combatVerbForSkill;
window.handleCombatResolutionEvent     = handleCombatResolutionEvent;
window.isDuplicateOfRecentCombatEvent  = isDuplicateOfRecentCombatEvent;
window.recordCombatEventFingerprint    = recordCombatEventFingerprint;

// Reset module-private dedup state for test isolation. Each
// run_with_d_prime_block invocation gets a clean fingerprint window.
M3CombatInspector._internal._clearFingerprints();
"""


def require_node_and_jsdom() -> None:
    if shutil.which("node") is None:
        pytest.skip("node not available")
    if not Path(NODE_MODULES, "jsdom").exists():
        pytest.skip(f"jsdom not installed at {NODE_MODULES}/jsdom")


def run_with_d_prime_block(setup_js: str, extra_stubs: str = "") -> dict:
    """Run the D' module + setup_js under jsdom; return parsed result.

    setup_js executes AFTER:
      1. STUBS_JS (defines escapeHtml/stripAnsi/appendEvent/etc).
      2. extra_stubs (test-specific overrides, prepended after STUBS_JS).
      3. m3_combat_inspector.js (the SPA module).
      4. INIT_AND_ALIAS_JS (wires module to stubs + exposes window aliases).

    setup_js must set `window.__d_prime_result` to a JSON-serializable value
    (DOM elements aren't directly serializable — extract .tagName,
    .className, .getAttribute(), .textContent etc.).
    """
    require_node_and_jsdom()

    module_src = INSPECTOR_MODULE.read_text(encoding="utf-8")

    full_js = (
        "// ── default stubs ────────────────────────────────────────\n"
        + STUBS_JS
        + "\n// ── test-extra stubs (overrides) ─────────────────────────\n"
        + extra_stubs
        + "\n// ── m3_combat_inspector.js (the SPA module) ──────────────\n"
        + module_src
        + "\n// ── init + window aliases (mirrors client.html runtime) ──\n"
        + INIT_AND_ALIAS_JS
        + "\n// ── test setup ───────────────────────────────────────────\n"
        + setup_js
    )

    fd, tmppath = tempfile.mkstemp(suffix=".js", prefix="m3ci_harness_")
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
            var result;
            (function() {{
                window.eval(src);
                result = window.__d_prime_result;
            }}).call(window);
            process.stdout.write(JSON.stringify(result));
        """
        proc = subprocess.run(
            ["node", "-e", wrapper],
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        if proc.returncode != 0:
            pytest.fail(
                f"node exited {proc.returncode}\n"
                f"stderr:\n{proc.stderr}\n"
                f"stdout:\n{proc.stdout}\n"
                f"(module size: {len(module_src)} bytes)"
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


# ── Compat shim for the old `extract_d_prime_block` API ─────────────
# A small number of pre-4.4 tests called extract_d_prime_block() to read
# the raw JS block out of client.html. Drop 4.4 moved that block into
# m3_combat_inspector.js — so the shim now reads the module file and
# returns its source. Tests that asserted "function X is in the block"
# continue to work since the module still defines those function names.
def extract_d_prime_block() -> str:
    """Backward-compat: return the m3_combat_inspector.js source.

    Pre-4.4 callers sliced client.html via comment markers. Drop 4.4
    moved the block into static/spa/m3_combat_inspector.js; this shim
    returns the module source so tests like
    test_extraction_markers_present_and_well_ordered's `function X in
    block` checks continue to pass.
    """
    return INSPECTOR_MODULE.read_text(encoding="utf-8")
