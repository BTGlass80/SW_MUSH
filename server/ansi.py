# -*- coding: utf-8 -*-
"""
ANSI color codes for terminal output.

Provides a clean API for colorizing text sent to Telnet clients.
WebSocket clients receive the raw codes; the browser client can
strip or interpret them.
"""

# Reset
RESET = "\033[0m"

# Standard colors
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

# Bright colors
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

# Styles
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# ── Convenience functions ──


def color(text: str, code: str) -> str:
    """Wrap text in a color code with auto-reset."""
    return f"{code}{text}{RESET}"


def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def red(text: str) -> str:
    return color(text, RED)


def green(text: str) -> str:
    return color(text, GREEN)


def yellow(text: str) -> str:
    return color(text, YELLOW)


def blue(text: str) -> str:
    return color(text, BLUE)


def cyan(text: str) -> str:
    return color(text, CYAN)


def magenta(text: str) -> str:
    return color(text, MAGENTA)


def bright_white(text: str) -> str:
    return color(text, BRIGHT_WHITE)


def highlight(text: str) -> str:
    """Visual highlight for inline tokens (commands, names, frequencies).

    DROP-3 ANSI FIX (May 2026): added because 10 callers across
    parser/channel_commands.py and parser/party_commands.py invoke
    `ansi.highlight(...)` and would AttributeError-out otherwise.
    The crash made `+faction`, `+channels`, `tune`, `+freqs`,
    `commfreq`, and the party-accept/decline messaging chain
    non-functional in production. Smoke FC1/CN1 are the regression
    guards.

    Style: bold bright-cyan. Mirrors the existing `header()` look
    on a single inline token without the surrounding heavyweight
    framing — same visual weight as a Wikipedia link in body text.
    """
    return f"{BOLD}{BRIGHT_CYAN}{text}{RESET}"


def dim(text: str) -> str:
    return color(text, DIM)


def header(text: str) -> str:
    """Format a section header."""
    return f"{BOLD}{BRIGHT_CYAN}{text}{RESET}"


def error(text: str) -> str:
    """Format an error message."""
    return f"{BRIGHT_RED}Error: {text}{RESET}"


def success(text: str) -> str:
    """Format a success message."""
    return f"{BRIGHT_GREEN}{text}{RESET}"


def system_msg(text: str) -> str:
    """Format a system message."""
    return f"{YELLOW}[SYSTEM] {text}{RESET}"


def combat_msg(text: str) -> str:
    """Format a combat message."""
    return f"{BRIGHT_RED}[COMBAT] {text}{RESET}"


def force_msg(text: str) -> str:
    """Format a Force-related message."""
    return f"{BRIGHT_BLUE}[THE FORCE] {text}{RESET}"


def room_name(text: str) -> str:
    """Format a room name."""
    return f"{BOLD}{BRIGHT_WHITE}{text}{RESET}"


def exit_color(text: str) -> str:
    """Format an exit direction."""
    return f"{BRIGHT_GREEN}{text}{RESET}"


def npc_name(text: str) -> str:
    """Format an NPC name."""
    return f"{BRIGHT_YELLOW}{text}{RESET}"


def player_name(text: str) -> str:
    """Format a player name."""
    return f"{BOLD}{CYAN}{text}{RESET}"


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape codes from text."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


# Precompiled patterns for sanitize_for_display (untrusted-text display guard).
import re as _re

# CSI sequences: ESC [ ... final-byte (colors, cursor moves, screen clears, …).
_CSI_RE = _re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# OSC sequences: ESC ] ... terminated by BEL or ST (window title, hyperlinks, …).
_OSC_RE = _re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
# Any remaining C0/C1 control chars (incl. bare ESC and DEL); whitespace handled
# separately so headlines collapse cleanly to a single line.
_CTRL_RE = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_WS_RE = _re.compile(r"\s+")


def sanitize_for_display(text: str, max_len: int = 200) -> str:
    """Strip ANSI/VT escape sequences and control characters from untrusted text
    before showing it to players.

    The Director's faction-turn ``news_headline`` is LLM-generated and reaches
    players verbatim via the ``news`` command (telnet) and ``/api/portal/news``
    (web). An LLM (or a poisoned prompt) could emit ANSI/control sequences that
    rewrite the telnet terminal (cursor moves, screen clears, colour spoofing)
    or smuggle control bytes into the web feed. This collapses any such input to
    a single safe line of printable text. (The web SPA also HTML-escapes on
    render — this is server-side defence in depth, and it also cleans rows that
    were stored before this guard existed.)
    """
    if not text:
        return ""
    text = _CSI_RE.sub("", text)
    text = _OSC_RE.sub("", text)
    text = text.replace("\x1b", "")           # any stray ESC left over
    text = _CTRL_RE.sub("", text)             # other control chars
    text = _WS_RE.sub(" ", text).strip()      # collapse whitespace to one line
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    return text
