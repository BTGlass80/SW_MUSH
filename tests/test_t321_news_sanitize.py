# -*- coding: utf-8 -*-
"""
T3.21 (HIGH): Director LLM output sanitized before player display.

The Director's faction-turn ``news_headline`` is LLM-generated and reaches
players verbatim via the ``news`` command (telnet) and ``/api/portal/news``
(web). A poisoned/erratic LLM headline carrying ANSI or control bytes could
rewrite a telnet terminal or smuggle control characters into the web feed.

Both display seams now route the stored ``summary`` through
``server.ansi.sanitize_for_display`` before it touches a client. These tests
pin the sanitizer's behaviour and confirm both seams actually call it.
"""
import ast
from pathlib import Path

from server.ansi import sanitize_for_display


# ── The sanitizer itself ────────────────────────────────────────────────────

def test_empty_and_none_like():
    assert sanitize_for_display("") == ""
    assert sanitize_for_display(None) == ""  # falsy guard


def test_plain_text_passes_through():
    s = "Brisk trade draws a merchant caravan to the spaceport."
    assert sanitize_for_display(s) == s


def test_unicode_preserved():
    # Accented / non-ASCII prose (> U+009F) must survive untouched.
    s = "Crème de la résistance — the café reopens on Tatooine."
    assert sanitize_for_display(s) == s


def test_strips_sgr_colour_codes():
    assert sanitize_for_display("\x1b[1;31mDANGER\x1b[0m at the docks") == \
        "DANGER at the docks"


def test_strips_cursor_and_screen_control():
    # Cursor-home + clear-screen + cursor move — classic terminal hijack.
    payload = "\x1b[2J\x1b[H\x1b[10;5HFAKE PROMPT"
    assert sanitize_for_display(payload) == "FAKE PROMPT"


def test_strips_osc_sequences():
    # OSC window-title injection (BEL-terminated and ST-terminated).
    assert sanitize_for_display("\x1b]0;pwned\x07Hello") == "Hello"
    assert sanitize_for_display("\x1b]8;;http://evil\x1b\\link") == "link"


def test_strips_bare_esc_and_control_chars():
    assert sanitize_for_display("a\x1bb\x00c\x07d\x7fe") == "abcde"
    # C1 control range too.
    assert sanitize_for_display("x\x9by") == "xy"


def test_collapses_whitespace_to_single_line():
    assert sanitize_for_display("line one\nline\ttwo\r\n   three") == \
        "line one line two three"


def test_length_cap():
    out = sanitize_for_display("A" * 500, max_len=200)
    assert len(out) == 200
    assert out == "A" * 200


def test_carriage_return_overwrite_neutralized():
    # \r alone could let a headline overwrite the line it was printed on.
    out = sanitize_for_display("real news\rFAKE ALERT")
    assert "\r" not in out
    assert out == "real news FAKE ALERT"


# ── Both display seams must actually invoke the sanitizer ────────────────────

ROOT = Path(__file__).resolve().parent.parent


def _calls_sanitize(relpath: str, func_name: str) -> bool:
    """True if `func_name` in `relpath` contains a call to sanitize_for_display."""
    tree = ast.parse((ROOT / relpath).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name == func_name:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    f = sub.func
                    name = getattr(f, "attr", None) or getattr(f, "id", None)
                    if name == "sanitize_for_display":
                        return True
    return False


def test_web_news_seam_sanitizes():
    assert _calls_sanitize("server/web_portal.py", "handle_news"), \
        "handle_news must sanitize Director headlines before returning them"


def test_telnet_news_seam_sanitizes():
    assert _calls_sanitize("parser/news_commands.py", "execute"), \
        "NewsCommand.execute must sanitize Director headlines before display"
