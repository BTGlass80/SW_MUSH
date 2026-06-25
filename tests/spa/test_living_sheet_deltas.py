"""
test_living_sheet_deltas.py — UX Drop 8 (living character sheet) verification.

Two layers:

  1. Static parse of static/client.html (no node dep) — asserts the delta
     plumbing + Force/dark-side theme are wired into the existing sheet
     renderers, the toggles default ON, and the add-vs-detract guardrails hold
     (decoration only, reduced-motion-safe static marker, escapeHtml kept,
     era-clean).

  2. Runtime extraction-eval of the PURE diff fn `sheetComputeChanges` under
     node — feeds successive payloads and asserts EXACTLY the changed values
     are flagged, first-open flags nothing, identical payloads flag nothing.

Mirrors the static-parse style of test_sheet_content_surface.py and the node
subprocess pattern of spa_dom_harness.py.
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


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


def _extract_fn(html: str, fn_name: str) -> str:
    """Extract a top-level JS function by brace-counting (from client.html)."""
    needle = "function " + fn_name + "("
    start = html.find(needle)
    if start == -1:
        return ""
    depth = 0
    i = start
    in_fn = False
    while i < len(html):
        ch = html[i]
        if ch == "{":
            depth += 1
            in_fn = True
        elif ch == "}":
            depth -= 1
            if in_fn and depth == 0:
                return html[start : i + 1]
        i += 1
    return html[start : start + 8000]


# ── 1. Static-parse: plumbing present ───────────────────────────────────────

def test_diff_fn_defined():
    assert re.search(r"function\s+sheetComputeChanges\s*\(", _html()), (
        "sheetComputeChanges (the pure delta fn) not defined"
    )


def test_toggle_getters_defined_and_default_on():
    html = _html()
    assert re.search(r"function\s+sheetDeltasEnabled\s*\(", html), "sheetDeltasEnabled missing"
    assert re.search(r"function\s+sheetForceThemeEnabled\s*\(", html), "sheetForceThemeEnabled missing"
    # Default ON: the flag is "on unless explicitly '0'" (mirrors combat-hud).
    d = _extract_fn(html, "sheetDeltasEnabled")
    f = _extract_fn(html, "sheetForceThemeEnabled")
    assert "sheet-deltas" in d and "!== '0'" in d, "sheet-deltas toggle must default ON (!== '0')"
    assert "sheet-force-theme" in f and "!== '0'" in f, "sheet-force-theme toggle must default ON (!== '0')"


def test_handle_sheet_data_snapshots_prev_before_overwrite():
    block = _extract_fn(_html(), "handleSheetData")
    # The prev snapshot must be taken from sheetPanelData BEFORE it is replaced.
    i_prev = block.find("sheetPanelDataPrev = sheetPanelData")
    i_set = block.find("sheetPanelData = msg.payload")
    assert i_prev != -1, "handleSheetData must snapshot sheetPanelDataPrev"
    assert i_set != -1, "handleSheetData must assign sheetPanelData = msg.payload"
    assert i_prev < i_set, "prev snapshot must happen BEFORE sheetPanelData is overwritten"
    assert "sheetComputeChanges" in block, "handleSheetData must compute the changed-set"
    # Delta computation is gated on the toggle.
    assert "sheetDeltasEnabled()" in block, "changed-set must be gated on sheetDeltasEnabled()"


def test_changed_class_applied_in_each_renderer():
    html = _html()
    for fn in (
        "renderSheetPanel",
        "renderSheetAttrs",
        "renderSheetPoints",
        "renderSheetWoundLadder",
        "renderSheetCenter",
        "makeSheetSkillRow",
        "makeSheetSpecRow",
    ):
        block = _extract_fn(html, fn)
        assert "sheet-val-changed" in block, (
            f"{fn} does not apply the .sheet-val-changed delta marker"
        )


def test_force_theme_gated_on_payload_force_and_toggle():
    block = _extract_fn(_html(), "renderSheetPanel")
    assert "sheet-force-theme" in block, "renderSheetPanel must toggle the .sheet-force-theme class"
    # Gated on derived force-sensitivity (payload.force) AND the toggle.
    assert re.search(r"p\.force", block), "Force theme must read payload.force (derived, never recomputed)"
    assert "sheetForceThemeEnabled()" in block, "Force theme must be gated on sheetForceThemeEnabled()"
    # data-dsp tiering for the dark-side pull.
    assert "data-dsp" in block, "renderSheetPanel must set data-dsp for the dark-side DSP tier"


def test_force_sensitive_not_recomputed():
    """force_sensitive stays derived — the client reads it, never recomputes."""
    block = _extract_fn(_html(), "renderSheetPanel")
    # No client-side reconstruction from control/sense/alter presence.
    assert "force_sensitive =" not in block, (
        "renderSheetPanel must not assign/recompute force_sensitive (derived state)"
    )


# ── 2. Static-parse: guardrails (add-vs-detract) ────────────────────────────

def test_css_changed_marker_has_static_box_shadow():
    """Reduced-motion safety: the marker is a static box-shadow (not only an
    animation), so reduced-motion users still SEE the change after the global
    media query neutralizes the pulse."""
    html = _html()
    m = re.search(r"\.sheet-val-changed\s*\{([^}]*)\}", html)
    assert m, ".sheet-val-changed CSS rule missing"
    body = m.group(1)
    assert "box-shadow" in body, (
        ".sheet-val-changed must carry a static box-shadow (reduced-motion-safe marker)"
    )


def test_reduced_motion_block_present():
    """The global prefers-reduced-motion block (which neutralizes the pulse)
    must still exist."""
    assert "@media (prefers-reduced-motion: reduce)" in _html(), (
        "global prefers-reduced-motion block missing — pulse would strobe for "
        "reduced-motion users"
    )


def test_force_theme_css_present():
    html = _html()
    assert ".sheet-panel.sheet-force-theme" in html, "Force-theme CSS scope missing"
    assert re.search(r'\.sheet-force-theme\[data-dsp="crit"\]', html), (
        "dark-side DSP crit tier CSS missing"
    )


def test_escapehtml_preserved_in_touched_renderers():
    """The delta layer only adds classes — escaping of server values must be
    unchanged (no XSS regression)."""
    html = _html()
    for fn in ("renderSheetAttrs", "renderSheetPoints"):
        block = _extract_fn(html, fn)
        assert "escapeHtml" in block, f"{fn} lost its escapeHtml usage"


def test_no_engine_or_payload_field_invented():
    """Drop 8 is client-only: the diff reads existing payload fields only."""
    block = _extract_fn(_html(), "sheetComputeChanges")
    # It reads the documented payload blocks; assert no stray new wire field.
    for fld in ("attributes", "skills", "specializations", "force", "points", "wound"):
        assert fld in block, f"sheetComputeChanges should read payload.{fld}"


def test_era_clean_new_code():
    combined = (
        _extract_fn(_html(), "sheetComputeChanges")
        + _extract_fn(_html(), "renderSheetPanel")
        + _extract_fn(_html(), "sheetDeltasEnabled")
        + _extract_fn(_html(), "sheetForceThemeEnabled")
    )
    for token in ("empire", "rebel", r"\bTIE\b"):
        assert not re.search(token, combined, re.IGNORECASE), (
            f"era token '{token}' found in new sheet code"
        )


# ── 3. Runtime extraction-eval of the pure diff fn ──────────────────────────

def _node_available() -> bool:
    return shutil.which("node") is not None


def _eval_compute(prev, cur):
    """Extract SHEET_ATTR_ORDER + sheetComputeChanges from client.html and run
    them under node against (prev, cur); return the changed-set dict."""
    html = _html()
    m_order = re.search(r"var\s+SHEET_ATTR_ORDER\s*=\s*\[[^\]]*\];", html, re.DOTALL)
    assert m_order, "SHEET_ATTR_ORDER declaration not found"
    fn = _extract_fn(html, "sheetComputeChanges")
    assert fn, "sheetComputeChanges not found"
    driver = (
        m_order.group(0)
        + "\n"
        + fn
        + "\n"
        + "var prev = " + json.dumps(prev) + ";\n"
        + "var cur = " + json.dumps(cur) + ";\n"
        + "process.stdout.write(JSON.stringify(sheetComputeChanges(prev, cur)));\n"
    )
    proc = subprocess.run(
        ["node", "-e", driver],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    if proc.returncode != 0:
        pytest.fail(f"node exited {proc.returncode}\nstderr:\n{proc.stderr}")
    return json.loads(proc.stdout)


def _base_payload():
    return {
        "attributes": {
            "dexterity": {"d": 3, "p": 0}, "knowledge": {"d": 2, "p": 0},
            "mechanical": {"d": 2, "p": 0}, "perception": {"d": 3, "p": 0},
            "strength": {"d": 3, "p": 0}, "technical": {"d": 2, "p": 0},
        },
        "skills": {
            "blaster": {"bonus": {"d": 1, "p": 0}, "total": {"d": 4, "p": 0}},
            "dodge": {"bonus": {"d": 0, "p": 2}, "total": {"d": 3, "p": 2}},
        },
        "specializations": [
            {"skill": "blaster", "name": "blaster: heavy",
             "bonus": {"d": 0, "p": 1}, "total": {"d": 4, "p": 1}},
        ],
        "force": {"control": {"d": 1, "p": 0}, "sense": {"d": 1, "p": 0},
                  "alter": {"d": 0, "p": 0}},
        "points": {"credits": 500, "fp": 1, "cp": 3, "dsp": 0, "force_sensitive": True},
        "wound": {"level": 0},
    }


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_first_open_flags_nothing():
    cur = _base_payload()
    ch = _eval_compute(None, cur)
    assert ch == {"attrs": {}, "skills": {}, "specs": {}, "force": {}, "points": {}, "wound": False}


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_identical_payloads_flag_nothing():
    p = _base_payload()
    ch = _eval_compute(p, _base_payload())
    assert ch["attrs"] == {} and ch["skills"] == {} and ch["specs"] == {}
    assert ch["force"] == {} and ch["points"] == {} and ch["wound"] is False


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_only_changed_values_flagged():
    prev = _base_payload()
    cur = _base_payload()
    cur["attributes"]["dexterity"] = {"d": 3, "p": 1}      # attr moved
    cur["skills"]["blaster"]["total"] = {"d": 4, "p": 1}    # skill moved
    cur["points"]["credits"] = 1200                          # credits moved
    cur["points"]["dsp"] = 2                                 # dsp moved
    cur["force"]["control"] = {"d": 2, "p": 0}              # force pool moved
    cur["wound"]["level"] = 2                                # wounded
    cur["specializations"][0]["total"] = {"d": 4, "p": 2}   # spec moved
    ch = _eval_compute(prev, cur)
    assert ch["attrs"] == {"dexterity": True}, ch["attrs"]
    assert ch["skills"] == {"blaster": True}, ch["skills"]
    assert ch["force"] == {"control": True}, ch["force"]
    assert ch["points"].get("credits") and ch["points"].get("dsp")
    assert "fp" not in ch["points"] and "cp" not in ch["points"]
    assert ch["wound"] is True
    assert ch["specs"] == {"blaster::blaster: heavy": True}, ch["specs"]


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_newly_trained_skill_flagged():
    prev = _base_payload()
    cur = _base_payload()
    cur["skills"]["brawling"] = {"bonus": {"d": 0, "p": 0}, "total": {"d": 3, "p": 0}}
    ch = _eval_compute(prev, cur)
    assert ch["skills"] == {"brawling": True}, ch["skills"]


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_force_sensitivity_flip_flagged():
    prev = _base_payload()
    cur = _base_payload()
    cur["points"]["force_sensitive"] = False
    ch = _eval_compute(prev, cur)
    assert ch["points"].get("force_sensitive") is True
