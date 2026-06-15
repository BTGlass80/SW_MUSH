"""test_xss_event_escaping.py — runtime proof of the XSS escape path.

Audit Section B (DEV-5/UX-8). After removing the dead ``ev.html`` fast-path,
ALL user-reachable text in the web client renders through
``ansiToHtml(ev.text)`` → ``escapeHtml``. This test proves at RUNTIME (real
JS execution under Node) that a malicious pose/say/sys payload renders
escaped rather than as live markup.

Mechanism: ``escapeHtml`` and ``ansiToHtml`` are pure string functions (no
DOM), so we extract their source from ``static/client.html`` and eval them in
a bare ``node -e`` subprocess — no jsdom needed. Skips cleanly if Node is
absent (the static-parse invariant in
``tests/test_xss_hardening_invariant.py`` still runs without Node).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _extract_escape_helpers() -> str:
    """Return the contiguous source of escapeHtml + ANSI tables + ansiToHtml.

    The block runs from ``function escapeHtml(s) {`` up to (but not including)
    ``function stripAnsi(``; it contains only pure function declarations and
    the two ANSI const tables, so it evals safely in bare Node.
    """
    html = CLIENT_HTML.read_text(encoding="utf-8")
    start = html.find("function escapeHtml(s) {")
    end = html.find("function stripAnsi(", start)
    assert start != -1 and end != -1 and end > start, (
        "Could not locate escapeHtml..ansiToHtml block in client.html"
    )
    return html[start:end]


def _run_escape_cases(cases_js: str) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node not available; install Node.js to run the escape proof")
    script = (
        _extract_escape_helpers()
        + "\nvar result = (function(){\n"
        + cases_js
        + "\n})();\nprocess.stdout.write(JSON.stringify(result));\n"
    )
    proc = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    if proc.returncode != 0:
        pytest.fail(f"node exited {proc.returncode}\nstderr:\n{proc.stderr}")
    return json.loads(proc.stdout)


def test_script_tag_in_text_renders_escaped():
    """A <script> in ev.text comes out escaped — never as a live tag."""
    out = _run_escape_cases(
        "return { s: ansiToHtml('<script>alert(1)</script>') };"
    )["s"]
    assert "<script>" not in out, "live <script> tag leaked through ansiToHtml"
    assert "&lt;script&gt;" in out, "script tag was not HTML-escaped"


def test_img_onerror_renders_escaped():
    """An <img onerror=...> payload renders inert (escaped)."""
    out = _run_escape_cases(
        "return { s: ansiToHtml('<img src=x onerror=alert(1)>') };"
    )["s"]
    assert "<img" not in out, "live <img> tag leaked through ansiToHtml"
    assert "&lt;img" in out, "img tag was not HTML-escaped"


def test_attribute_breakout_renders_escaped():
    """An attribute-breakout payload ("><svg onload>) renders escaped."""
    out = _run_escape_cases(
        "return { s: ansiToHtml('\\\"><svg onload=alert(1)>') };"
    )["s"]
    assert "<svg" not in out, "live <svg> tag leaked through ansiToHtml"
    assert "&lt;svg" in out
    assert "&quot;&gt;" in out, "quote/angle-bracket breakout not escaped"


def test_escapehtml_escapes_all_five_entities():
    """escapeHtml escapes & < > \" ' — the full set."""
    out = _run_escape_cases(
        "return { s: escapeHtml('<b>\\\"hi\\\"&\\'</b>') };"
    )["s"]
    assert out == "&lt;b&gt;&quot;hi&quot;&amp;&#39;&lt;/b&gt;", out


def test_legit_ansi_color_still_renders_span():
    """Escaping doesn't break the legitimate ANSI→span color path."""
    out = _run_escape_cases(
        "return { s: ansiToHtml('\\x1b[31mred\\x1b[0m') };"
    )["s"]
    assert '<span class="ansi-red">' in out, "ANSI color span path regressed"
    assert "red" in out
