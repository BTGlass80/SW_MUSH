"""
test_ambient_bark_dedup.py — ambient-bark consecutive-duplicate suppression.

The server re-emits the same ambient line on a cadence ("Distant thunder
rolls..."); a steady repeat buried the player's own command output
(fun-assessment finding). handleAmbientBark now suppresses a bark identical to
the most-recent one within a short window (distinct lines always render; the
same line returns after the window — atmosphere kept, not spammed).

Static parse of static/client.html.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _handle_ambient() -> str:
    src = CLIENT_HTML.read_text(encoding="utf-8")
    i = src.find("function handleAmbientBark")
    assert i != -1, "handleAmbientBark not found"
    return src[i: i + 700]


def test_ambient_bark_dedup_state_exists():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "_lastAmbientBarkText" in src and "_lastAmbientBarkTs" in src, (
        "ambient-bark dedup state (last text + timestamp) missing")


def test_ambient_bark_suppresses_recent_duplicate():
    body = _handle_ambient()
    # Guard: identical-to-last text within the window returns early (skips render).
    assert "_lastAmbientBarkText" in body, "handleAmbientBark must check the last bark text"
    assert re.search(r"text\s*===\s*_lastAmbientBarkText", body), (
        "handleAmbientBark must compare the new bark to the last one")
    assert re.search(r"return", body), "duplicate within the window must early-return"
    # And a distinct/after-window bark still renders.
    assert "appendEvent(" in body, "non-duplicate barks must still render via appendEvent"


def test_ambient_bark_window_bounded():
    body = _handle_ambient()
    assert "_AMBIENT_BARK_DEDUP_MS" in body or re.search(r"<\s*\d{4,}", body), (
        "dedup must be time-bounded (a window), not permanent suppression")
