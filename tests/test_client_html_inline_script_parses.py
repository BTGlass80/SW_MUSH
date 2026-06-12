"""
test_client_html_inline_script_parses.py — Drop CI-guard, May 28 2026.

Whole-file syntax-check for the inline `<script>` block in
static/client.html. This block runs the entire field-kit client surface
(~6,000 lines of vanilla JS as of Drop 4.15) and is loaded by every
production session; a single typo silently bricks the client.

Existing SPA tests query for *behaviors* (does the sheet panel render?
does the map modal open?) — none of them assert that the inline script
parses end-to-end. A drop that adds a missing brace inside an init
block, or a stray comma in an event handler, can land green if no test
happens to hit that branch.

This guard fills that gap. Cost: one subprocess invoking `node --check`
on the extracted body (~250 ms). Skip cleanly on machines without node.

History — recommended in three consecutive handoffs before being built:
  · Drop 4.13 §10  (May 28 — outer-tier triplet)
  · Drop 4.14 §10  (May 28 — inner-tier triplet)
  · Drop 4.15 §10  (May 28 — production cutover)

Together those three drops added ~58 lines of new inline JS (script tags
+ init-comment blocks + namespace guards) to the same file, raising the
value of the guard each time.

Drop D Phase 3 (engine-only) added zero inline JS but doesn't change the
analysis — every future SPA / client.html drop is what this guard
protects against.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _require_node() -> None:
    """Skip cleanly when node isn't available (Windows dev box without
    node-on-PATH, CI runners that haven't installed it yet, etc.)."""
    if shutil.which("node") is None:
        pytest.skip(
            "node not available on PATH; install Node.js to run the "
            "inline-script syntax-check guard"
        )


def _extract_inline_script() -> tuple[str, int, int]:
    """Extract the single inline <script>...</script> body from client.html.

    Returns ``(body, start_line, end_line)`` where line numbers are
    1-indexed and refer to the *body* (excluding the open/close tags).

    The extraction relies on the boundary convention: the open tag
    appears on its own line as ``<script>`` and the close as
    ``</script>``. As of Drop 4.15 client.html has exactly one such
    block; if a future drop introduces another inline block (rather
    than adding a script-src tag), this helper will need a small
    update and the test below will flag the assumption-break loudly.
    """
    lines = CLIENT_HTML.read_text(encoding="utf-8").splitlines()
    start = end = None
    open_count = sum(1 for ln in lines if ln.strip() == "<script>")
    close_count = sum(1 for ln in lines if ln.strip() == "</script>")
    assert open_count == 1, (
        f"client.html now has {open_count} standalone-line <script> open "
        f"tags; the guard expects exactly one inline block. If a new "
        f"inline block was added, extend _extract_inline_script to scan "
        f"all of them and run node --check on each."
    )
    assert close_count == 1, (
        f"client.html now has {close_count} standalone-line </script> "
        f"close tags; mismatched with {open_count} open tags."
    )
    for i, ln in enumerate(lines):
        if ln.strip() == "<script>" and start is None:
            start = i + 1  # body starts on the line AFTER the open tag
        elif ln.strip() == "</script>" and start is not None:
            end = i  # body ends on the line BEFORE the close tag
            break
    assert start is not None and end is not None, (
        "Failed to locate the inline <script> block boundaries. Check "
        "client.html's open/close tags are each on their own line."
    )
    body = "\n".join(lines[start:end])
    # +1 to surface 1-indexed line numbers for any failure message.
    return body, start + 1, end


# ════════════════════════════════════════════════════════════════════
# The guard
# ════════════════════════════════════════════════════════════════════

def test_client_html_inline_script_is_extractable():
    """The extraction itself must succeed — the guard fails LOUDLY if
    a future drop changes the inline-block convention (e.g. moves the
    block to a separate file, adds a second inline block, or inlines
    the script onto the same line as the open tag)."""
    body, start_line, end_line = _extract_inline_script()
    assert len(body) > 0, "Inline script body is empty"
    assert end_line > start_line, "Inline script has zero lines"
    # Sanity floor — the body has been ~6k lines for months. Anything
    # under 100 lines means we extracted the wrong block.
    assert end_line - start_line >= 100, (
        f"Extracted inline body is only {end_line - start_line} lines; "
        f"expected >= 100 (the SPA shell is ~6k lines). Wrong block?"
    )


def test_client_html_inline_script_parses_under_node():
    """The core guard: `node --check` must accept the extracted inline
    script body. A failure here means client.html will brick on every
    production session — the inline script is the entire field-kit
    shell. Surface the node error with file:line context so the
    breaking drop is easy to locate."""
    _require_node()
    body, start_line, _end_line = _extract_inline_script()

    proc = subprocess.run(
        ["node", "--check", "-"],
        input=body,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if proc.returncode != 0:
        # node reports errors as `[stdin]:LINENO\n...SyntaxError...`.
        # Translate the stdin line number into a real client.html line
        # number so the diff hunk is one grep away.
        stderr = proc.stderr or ""
        annotated = stderr
        # Best-effort: rewrite the first `[stdin]:N` reference to point
        # at the actual client.html line. The inline block starts at
        # client.html line (start_line); node's lineno is 1-indexed
        # within the body, so client.html line = start_line + N - 1.
        import re as _re
        m = _re.search(r"\[stdin\]:(\d+)", stderr)
        if m:
            stdin_line = int(m.group(1))
            real_line = start_line + stdin_line - 1
            annotated = (
                f"client.html line {real_line} (inline-script line "
                f"{stdin_line}):\n\n" + stderr
            )
        pytest.fail(
            "Inline <script> body in static/client.html fails "
            "`node --check`. This bricks the field-kit client on every "
            "production session — fix before merging.\n\n"
            + annotated
        )
