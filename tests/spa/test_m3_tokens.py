"""
test_m3_tokens.py — regression test for static/spa/m3_tokens.js.

Drop 4.1a · Tier 1 #4 · May 26 2026.

Validates:
1. The module file exists at the expected path.
2. The module is syntactically valid JS (no parse errors).
3. The module exports window.M3Tokens with WOUND_RUNGS and woundRung.
4. WOUND_RUNGS matches the engine's WoundLevel(IntEnum) structure
   (7 rungs, v: 0..6, every rung has label/labelLong/pen/sev fields).
5. woundRung() returns the right rung for each level and defaults
   to HEALTHY on out-of-range input.

How the JS is exercised: each test runs the module under Node.js with a
minimal `window` shim. This catches bugs that pure-syntax-check or pure-grep
would miss (e.g. typos in attribute names, broken control flow). Avoids
the Playwright dependency for this drop; Playwright harness lands in 4.1c
when real DOM rendering needs to be asserted.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"
MODULE_PATH = SPA_DIR / "m3_tokens.js"


def _run_js_in_node(setup_js: str) -> dict:
    """Run setup_js in Node.js with a minimal window shim; return parsed JSON output.

    The setup script must set `result` to a JSON-serializable value, then we
    print(JSON.stringify(result)) and parse it back here.
    """
    if shutil.which("node") is None:
        pytest.skip("node not available; install Node.js to run SPA tests")

    wrapper = f"""
        // Minimal browser globals the SPA modules expect.
        var window = globalThis;

        // Load the module under test.
        var fs = require('fs');
        var moduleSrc = fs.readFileSync({json.dumps(str(MODULE_PATH))}, 'utf8');
        eval(moduleSrc);

        // User-supplied setup script.
        var result;
        (function() {{
            {setup_js}
        }})();

        process.stdout.write(JSON.stringify(result));
    """
    proc = subprocess.run(
        ["node", "-e", wrapper],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"node exited {proc.returncode}\n"
            f"stderr:\n{proc.stderr}\n"
            f"stdout:\n{proc.stdout}"
        )
    return json.loads(proc.stdout)


# ── Test 1: file existence and syntax ──────────────────────────────


def test_module_file_exists() -> None:
    """m3_tokens.js exists at the expected path."""
    assert MODULE_PATH.exists(), f"Module not found at {MODULE_PATH}"


def test_module_syntax_valid() -> None:
    """m3_tokens.js parses cleanly under Node.js."""
    if shutil.which("node") is None:
        pytest.skip("node not available")
    proc = subprocess.run(
        ["node", "--check", str(MODULE_PATH)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert proc.returncode == 0, (
        f"Syntax check failed:\n{proc.stderr}"
    )


# ── Test 2: module exports ─────────────────────────────────────────


def test_exports_M3Tokens_namespace() -> None:
    """Loading the module populates window.M3Tokens."""
    result = _run_js_in_node("""
        result = {
            hasNamespace: typeof window.M3Tokens === 'object' && window.M3Tokens !== null,
            keys: window.M3Tokens ? Object.keys(window.M3Tokens).sort() : []
        };
    """)
    assert result["hasNamespace"], "window.M3Tokens was not populated"
    # Drop 4.1b extended M3Tokens with svgEl + SVG_NS for SVG-generating
    # modules. Original 4.1a keys were just WOUND_RUNGS + woundRung.
    assert result["keys"] == ["SVG_NS", "WOUND_RUNGS", "svgEl", "woundRung"], (
        f"Unexpected M3Tokens keys: {result['keys']}"
    )


# ── Test 3: WOUND_RUNGS structure ──────────────────────────────────


def test_wound_rungs_has_seven_rungs() -> None:
    """WOUND_RUNGS has exactly 7 entries (one per WoundLevel enum value)."""
    result = _run_js_in_node("""
        result = { length: window.M3Tokens.WOUND_RUNGS.length };
    """)
    assert result["length"] == 7, (
        f"Expected 7 wound rungs (HEALTHY..DEAD), got {result['length']}"
    )


def test_wound_rungs_v_values_are_zero_through_six() -> None:
    """Each rung's `v` field matches its position 0..6."""
    result = _run_js_in_node("""
        result = { vs: window.M3Tokens.WOUND_RUNGS.map(function(r) { return r.v; }) };
    """)
    assert result["vs"] == [0, 1, 2, 3, 4, 5, 6]


def test_every_rung_has_required_fields() -> None:
    """Every rung carries label, labelLong, pen, sev."""
    result = _run_js_in_node("""
        var required = ['v', 'label', 'labelLong', 'pen', 'sev'];
        result = window.M3Tokens.WOUND_RUNGS.map(function(r) {
            var missing = required.filter(function(k) { return !(k in r); });
            return { v: r.v, missing: missing };
        });
    """)
    for entry in result:
        assert entry["missing"] == [], (
            f"Rung v={entry['v']} missing fields: {entry['missing']}"
        )


def test_canonical_labels_present() -> None:
    """Specific canonical labels are at their expected positions."""
    result = _run_js_in_node("""
        var rungs = window.M3Tokens.WOUND_RUNGS;
        result = {
            healthy_short: rungs[0].label,
            healthy_long:  rungs[0].labelLong,
            wounded_twice_short: rungs[3].label,
            wounded_twice_long:  rungs[3].labelLong,
            incap_short: rungs[4].label,
            incap_long:  rungs[4].labelLong,
            mortal_short: rungs[5].label,
            mortal_long:  rungs[5].labelLong,
            dead_short: rungs[6].label,
            dead_long:  rungs[6].labelLong
        };
    """)
    assert result["healthy_short"] == "HEALTHY"
    assert result["healthy_long"] == "HEALTHY"
    assert result["wounded_twice_short"] == "WOUNDED ×2"
    assert result["wounded_twice_long"] == "WOUNDED TWICE"
    assert result["incap_short"] == "INCAP"
    assert result["incap_long"] == "INCAPACITATED"
    assert result["mortal_short"] == "MORTAL"
    assert result["mortal_long"] == "MORTALLY WOUNDED"
    assert result["dead_short"] == "DEAD"
    assert result["dead_long"] == "DEAD"


def test_dice_penalties_correct() -> None:
    """Penalty strings match WEG R&E: WOUNDED -1D, WOUNDED ×2 -2D, others empty."""
    result = _run_js_in_node("""
        var rungs = window.M3Tokens.WOUND_RUNGS;
        result = {
            healthy_pen:        rungs[0].pen,
            stunned_pen:        rungs[1].pen,
            wounded_pen:        rungs[2].pen,
            wounded_twice_pen:  rungs[3].pen,
            incap_pen:          rungs[4].pen,
            mortal_pen:         rungs[5].pen,
            dead_pen:           rungs[6].pen
        };
    """)
    assert result["healthy_pen"]       == ""
    assert result["stunned_pen"]       == ""   # stun penalty comes from stun_timers
    assert result["wounded_pen"]       == "-1D"
    assert result["wounded_twice_pen"] == "-2D"
    assert result["incap_pen"]         == ""
    assert result["mortal_pen"]        == ""
    assert result["dead_pen"]          == ""


# ── Test 4: woundRung() lookup behavior ────────────────────────────


def test_wound_rung_lookup_in_range() -> None:
    """woundRung(N) returns the rung with v === N for N in 0..6."""
    result = _run_js_in_node("""
        result = {};
        for (var i = 0; i <= 6; i++) {
            var r = window.M3Tokens.woundRung(i);
            result['v' + i] = { v: r.v, label: r.label };
        }
    """)
    for i in range(7):
        key = f"v{i}"
        assert result[key]["v"] == i, (
            f"woundRung({i}) returned v={result[key]['v']} (expected {i})"
        )


def test_wound_rung_lookup_out_of_range_returns_healthy() -> None:
    """woundRung(N) for N out of range defaults to HEALTHY (v=0)."""
    result = _run_js_in_node("""
        result = {
            negative:     window.M3Tokens.woundRung(-1).v,
            too_high:     window.M3Tokens.woundRung(99).v,
            undefined_in: window.M3Tokens.woundRung(undefined).v,
            null_in:      window.M3Tokens.woundRung(null).v,
            string_in:    window.M3Tokens.woundRung('three').v
        };
    """)
    assert result["negative"] == 0
    assert result["too_high"] == 0
    assert result["undefined_in"] == 0
    assert result["null_in"] == 0
    assert result["string_in"] == 0


# ── Test 5: parity with engine WoundLevel enum ─────────────────────


def test_parity_with_engine_wound_level_enum() -> None:
    """Verify the JS WOUND_RUNGS labels align with engine/character.py WoundLevel.

    This test would crash if the engine added/removed a wound level without
    a corresponding update to m3_tokens.js, surfacing the drift loudly.
    Pulls the canonical enum from the engine source and checks each value
    exists in WOUND_RUNGS.
    """
    # Walk up to the project root to find engine/character.py.
    # tests/spa/test_m3_tokens.py -> tests/spa -> tests -> <root>
    project_root = Path(__file__).resolve().parent.parent.parent
    char_py = project_root / "engine" / "character.py"
    if not char_py.exists():
        pytest.skip(f"engine/character.py not found at {char_py}")

    content = char_py.read_text(encoding="utf-8")
    # Find WoundLevel(IntEnum) block — accept either spelling.
    # Look for `class WoundLevel(IntEnum):` then read assignments until
    # we hit a blank line followed by something else.
    import re
    m = re.search(
        r"class WoundLevel\(IntEnum\):\s*\n((?:\s+[A-Z_]+\s*=\s*\d+\s*\n)+)",
        content,
    )
    if not m:
        pytest.skip("Could not locate WoundLevel(IntEnum) in engine/character.py")

    enum_block = m.group(1)
    # Parse "  HEALTHY = 0" lines
    engine_levels = {}
    for line in enum_block.strip().splitlines():
        parts = line.strip().split("=")
        if len(parts) == 2:
            name = parts[0].strip()
            value = int(parts[1].strip())
            engine_levels[value] = name

    # Should be exactly 7 entries 0..6
    assert sorted(engine_levels.keys()) == [0, 1, 2, 3, 4, 5, 6], (
        f"Engine WoundLevel doesn't match expected 0..6: {engine_levels}"
    )

    # Cross-check against JS WOUND_RUNGS — every engine value should have a
    # JS rung at the same v.
    result = _run_js_in_node("""
        result = {};
        window.M3Tokens.WOUND_RUNGS.forEach(function(r) {
            result['v' + r.v] = r.label;
        });
    """)
    for v in sorted(engine_levels.keys()):
        assert f"v{v}" in result, (
            f"Engine WoundLevel has v={v} ({engine_levels[v]}) "
            f"but JS WOUND_RUNGS has no matching rung"
        )
