"""
test_m3_palettes.py — regression test for static/spa/m3_palettes.js.

Drop 4.1a · Tier 1 #4 · May 26 2026.

Validates:
1. The module file exists and parses.
2. The module exports window.M3Palettes with PALETTES and getPalette.
3. Three palettes ship by default (tatooine, coruscant_under, nar_shaddaa).
4. Each palette has the full schema (substrate, cartography, accents,
   per-style fills, atmosphere).
5. getPalette() returns the right palette for a known id and null
   for unknown ids (no throw).

Pattern mirrors tests/spa/test_m3_tokens.py — Node sandbox approach,
no Playwright dependency (lands in Drop 4.1c).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"
MODULE_PATH = SPA_DIR / "m3_palettes.js"


# Required schema for every palette entry. If a palette ships without one
# of these, the composition engine will likely render it broken — catch
# the omission here loudly.
REQUIRED_PALETTE_FIELDS = [
    # Identity
    "id", "label", "sub",
    # Substrate
    "sky", "skyDeep", "ground", "groundDeep", "groundShadow",
    # Cartography (drawn lines and labels)
    "ink", "inkBright", "inkDim", "inkFaint", "paper", "paperDark",
    # Accents
    "cyan", "red", "green", "amber", "gold",
    # Per-style fills (used by style primitives in 4.1b)
    "fillDock", "fillCantina", "fillCivic", "fillHousing",
    "fillVendor", "fillIndustrial", "fillHutt", "fillLandmark",
    # Atmosphere
    "sunCount", "shadowAngle", "shadowOpacity",
    "ambient", "hazeColor", "grainColor",
]


def _run_js_in_node(setup_js: str) -> dict:
    """Run setup_js in Node.js with a minimal window shim."""
    if shutil.which("node") is None:
        pytest.skip("node not available; install Node.js to run SPA tests")

    wrapper = f"""
        var window = globalThis;
        var fs = require('fs');
        var moduleSrc = fs.readFileSync({json.dumps(str(MODULE_PATH))}, 'utf8');
        eval(moduleSrc);

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
        timeout=10,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"node exited {proc.returncode}\n"
            f"stderr:\n{proc.stderr}\n"
            f"stdout:\n{proc.stdout}"
        )
    return json.loads(proc.stdout)


def test_module_file_exists() -> None:
    """m3_palettes.js exists at the expected path."""
    assert MODULE_PATH.exists(), f"Module not found at {MODULE_PATH}"


def test_module_syntax_valid() -> None:
    """m3_palettes.js parses cleanly under Node.js."""
    if shutil.which("node") is None:
        pytest.skip("node not available")
    proc = subprocess.run(
        ["node", "--check", str(MODULE_PATH)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"Syntax check failed:\n{proc.stderr}"


def test_exports_M3Palettes_namespace() -> None:
    """Loading the module populates window.M3Palettes."""
    result = _run_js_in_node("""
        result = {
            hasNamespace: typeof window.M3Palettes === 'object' && window.M3Palettes !== null,
            keys: window.M3Palettes ? Object.keys(window.M3Palettes).sort() : []
        };
    """)
    assert result["hasNamespace"], "window.M3Palettes was not populated"
    assert result["keys"] == ["PALETTES", "getPalette"]


def test_three_canonical_palettes_ship() -> None:
    """PALETTES has the three canonical entries from the v3 prototype."""
    result = _run_js_in_node("""
        result = { keys: Object.keys(window.M3Palettes.PALETTES).sort() };
    """)
    # Order-independent comparison.
    assert set(result["keys"]) == {"coruscant_under", "nar_shaddaa", "tatooine"}, (
        f"Unexpected palette set: {result['keys']}"
    )


def test_each_palette_has_full_schema() -> None:
    """Every palette has all REQUIRED_PALETTE_FIELDS."""
    result = _run_js_in_node("""
        result = {};
        Object.keys(window.M3Palettes.PALETTES).forEach(function(k) {
            result[k] = Object.keys(window.M3Palettes.PALETTES[k]).sort();
        });
    """)
    for palette_id, fields in result.items():
        missing = [f for f in REQUIRED_PALETTE_FIELDS if f not in fields]
        assert not missing, (
            f"Palette '{palette_id}' missing required fields: {missing}"
        )


def test_tatooine_has_twin_suns() -> None:
    """Tatooine palette has sunCount=2 (the iconic twin-suns detail)."""
    result = _run_js_in_node("""
        result = {
            sunCount: window.M3Palettes.PALETTES.tatooine.sunCount,
            shadowAngleCount: window.M3Palettes.PALETTES.tatooine.shadowAngle.length
        };
    """)
    assert result["sunCount"] == 2, "Tatooine should have 2 suns"
    assert result["shadowAngleCount"] == 2, (
        "Tatooine should have 2 shadow directions (one per sun)"
    )


def test_coruscant_underworld_has_no_sun() -> None:
    """Coruscant Underworld palette has sunCount=0 (perpetual twilight)."""
    result = _run_js_in_node("""
        result = { sunCount: window.M3Palettes.PALETTES.coruscant_under.sunCount };
    """)
    assert result["sunCount"] == 0


def test_color_strings_are_hex() -> None:
    """All color fields (ink/sky/ground/accents) are 7-char hex (`#rrggbb`)."""
    import re
    hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
    color_fields = [
        "sky", "skyDeep", "ground", "groundDeep", "groundShadow",
        "ink", "inkBright", "inkDim", "inkFaint", "paper", "paperDark",
        "cyan", "red", "green", "amber", "gold",
        "fillDock", "fillCantina", "fillCivic", "fillHousing",
        "fillVendor", "fillIndustrial", "fillHutt", "fillLandmark",
    ]
    result = _run_js_in_node("""
        result = {};
        Object.keys(window.M3Palettes.PALETTES).forEach(function(k) {
            var p = window.M3Palettes.PALETTES[k];
            result[k] = {};
            ['sky', 'skyDeep', 'ground', 'groundDeep', 'groundShadow',
             'ink', 'inkBright', 'inkDim', 'inkFaint', 'paper', 'paperDark',
             'cyan', 'red', 'green', 'amber', 'gold',
             'fillDock', 'fillCantina', 'fillCivic', 'fillHousing',
             'fillVendor', 'fillIndustrial', 'fillHutt', 'fillLandmark']
            .forEach(function(field) {
                result[k][field] = p[field];
            });
        });
    """)
    for palette_id, fields in result.items():
        for field, value in fields.items():
            assert hex_pattern.match(value), (
                f"Palette '{palette_id}' field '{field}' is not 7-char hex: {value!r}"
            )


def test_get_palette_returns_known() -> None:
    """getPalette('tatooine') returns the tatooine palette."""
    result = _run_js_in_node("""
        var p = window.M3Palettes.getPalette('tatooine');
        result = { id: p ? p.id : null, label: p ? p.label : null };
    """)
    assert result["id"] == "tatooine"
    assert result["label"] == "TATOOINE"


def test_get_palette_returns_null_for_unknown() -> None:
    """getPalette('unknown_planet') returns null (does not throw)."""
    result = _run_js_in_node("""
        result = {
            unknown:  window.M3Palettes.getPalette('unknown_planet'),
            empty:    window.M3Palettes.getPalette(''),
            null_in:  window.M3Palettes.getPalette(null),
            undef_in: window.M3Palettes.getPalette(undefined)
        };
    """)
    assert result["unknown"] is None
    assert result["empty"] is None
    assert result["null_in"] is None
    assert result["undef_in"] is None
