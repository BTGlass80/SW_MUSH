"""test_xss_hardening_invariant.py — XSS hardening (audit Section B, DEV-5/UX-8).

Locks the safe state after removing the dead ``ev.html`` fast-path from the
web client's event renderer:

  1. PRODUCER side — no server/engine/parser code emits an outbound event
     payload carrying an ``html`` dict key. The client renders every
     user-reachable string through ``ansiToHtml(ev.text)`` (which escapes via
     ``escapeHtml``); an ``html`` field would have been injected into
     ``innerHTML`` unescaped, so its absence is the invariant that keeps the
     escape path mandatory.

  2. CONSUMER side — the client event renderer (``buildRow`` /
     ``buildCommsRow``) no longer references ``ev.html`` and routes user text
     through ``ansiToHtml``. Guards against silent reintroduction of the
     fast-path.

Pure-python (regex/string over source); no Node/DOM required, so these run in
the default suite. The runtime escape proof lives in
``tests/spa/test_xss_event_escaping.py`` (Node).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"

# A dict-literal key named html: "html": ... or 'html': ...
_HTML_KEY_RE = re.compile(r"""['"]html['"]\s*:""")


def _python_sources(*subdirs: str):
    for sub in subdirs:
        base = REPO_ROOT / sub
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p


# ─── 1. PRODUCER invariant ────────────────────────────────────────────────

def test_no_html_event_field_in_producers():
    """No server/engine/parser dict literal emits an ``html`` key.

    Outbound events are built as plain dicts (``{"t": ..., "text": ...}``).
    Adding an ``html`` key would feed unescaped markup to ``innerHTML`` on the
    client, which is exactly the surface this drop closed.
    """
    offenders = []
    for path in _python_sources("server", "engine", "parser"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _HTML_KEY_RE.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "Found producer(s) emitting an 'html' event field — this re-opens the "
        "XSS surface closed by audit DEV-5/UX-8. Render user text through "
        "ansiToHtml(text) instead.\n" + "\n".join(offenders)
    )


# ─── 2. CONSUMER guard (client.html) ──────────────────────────────────────

def _client_html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


def test_client_renderer_has_no_ev_html_reference():
    """The client event renderers (buildRow/buildCommsRow) no longer read ev.html.

    Scoped to the render-function bodies so the in-file documentation comment
    (which names the removed field) doesn't trip the guard.
    """
    html = _client_html()
    for fn in ("function buildRow(ev)", "function buildCommsRow(ev)"):
        idx = html.find(fn)
        assert idx != -1, f"{fn} not found in client.html"
        block = html[idx: idx + 4000]
        assert "ev.html" not in block, (
            f"ev.html reappeared in {fn} — the removed unescaped fast-path must "
            "stay removed (XSS hardening, audit DEV-5/UX-8)."
        )


def test_buildrow_routes_text_through_ansitohtml():
    """buildRow renders user text via ansiToHtml(ev.text), the escaping path."""
    html = _client_html()
    idx = html.find("function buildRow(ev)")
    assert idx != -1, "buildRow not found in client.html"
    block = html[idx: idx + 4000]
    assert "ansiToHtml(ev.text" in block, (
        "buildRow no longer routes user text through ansiToHtml — escaping path lost"
    )


def test_ansitohtml_escapes_via_escapehtml():
    """ansiToHtml delegates plain text segments to escapeHtml (the escaper)."""
    html = _client_html()
    idx = html.find("function ansiToHtml(text)")
    assert idx != -1, "ansiToHtml not found in client.html"
    block = html[idx: idx + 1200]
    assert "escapeHtml(" in block, (
        "ansiToHtml no longer routes text through escapeHtml — escaping path lost"
    )
