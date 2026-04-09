# -*- coding: utf-8 -*-
"""
Shared text formatting utilities — width-aware.

Every display surface (Telnet, WebSocket browser client) may have a
different usable width.  Instead of hardcoding W = 78 everywhere, this
module provides helpers that accept an explicit *width* parameter and
defaults that look good on a standard 80-column terminal.

    from engine.text_format import Fmt

    fmt = Fmt(width=session.width)   # or Fmt() for 78-col default
    output = fmt.bar()
    output += fmt.wrap("Long paragraph...")

Design rules
============
* ``max_prose`` caps paragraph text so lines never exceed ~100 visible
  characters even on ultra-wide viewports.  This keeps poses / descs
  readable without turning into wall-of-text.
* ``bar()``, ``header()``, and ``center()`` respect the full width so
  decorative rules still span the terminal.
* No text is ever truncated with ``"..."`` — everything wraps.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

from server.ansi import (
    BOLD, RESET, DIM, CYAN, YELLOW,
    BRIGHT_WHITE, BRIGHT_CYAN, BRIGHT_YELLOW, BRIGHT_GREEN,
    BRIGHT_RED, BRIGHT_BLUE, BRIGHT_MAGENTA,
)

# ── Constants ──

DEFAULT_WIDTH = 72          # Conservative default; resize updates this
MAX_PROSE_WIDTH = 100       # Readable cap for paragraph text
MIN_WIDTH = 40              # Floor for narrow clients


def _ansi_len(text: str) -> int:
    """Visible length of *text* after stripping ANSI escape codes."""
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def _ansi_pad(text: str, width: int) -> str:
    """Right-pad *text* to *width* visible characters."""
    return text + " " * max(0, width - _ansi_len(text))


# ══════════════════════════════════════════════════════
#  Fmt — the main formatting helper
# ══════════════════════════════════════════════════════

@dataclass
class Fmt:
    """
    Width-aware text formatter.

    Construct with the target display width (typically ``session.width``).
    All methods produce plain strings containing ANSI color codes that
    are suitable for ``session.send_line()``.

    Parameters
    ----------
    width : int
        Total character width of the output surface.  Decorative bars
        span this full width.  Set from ``session.width`` at render time.
    """

    width: int = DEFAULT_WIDTH

    def __post_init__(self):
        self.width = max(MIN_WIDTH, self.width)

    # ── Computed helpers ──

    @property
    def prose_width(self) -> int:
        """Width for paragraph text (body copy, descriptions).

        Text is typically rendered with a 2-char indent, so the
        visible line spans ``prose_width`` characters starting at
        column 2.  Capped at MAX_PROSE_WIDTH for readability on
        ultra-wide terminals.
        """
        return min(self.width - 4, MAX_PROSE_WIDTH)

    @property
    def col_width(self) -> int:
        """Width of a single column in a two-column layout."""
        return (self.width - 4) // 2   # 4 = 2-char gutter + margins

    # ── Decorative elements ──

    @property
    def display_width(self) -> int:
        """Width for decorative bars, rules, and centered text.

        Equals ``prose_width + 4`` so that a bar visually frames
        indented prose with a 2-char margin on each side.  This
        ensures bars and text always end at the same right edge
        regardless of session width.
        """
        return self.prose_width + 4

    def bar(self, char: str = "=", color: str = BRIGHT_CYAN) -> str:
        """Decorative rule spanning the display width."""
        return f"{color}{char * self.display_width}{RESET}"

    def header(self, text: str) -> str:
        """Bold bright-white header text (no decoration)."""
        return f"{BOLD}{BRIGHT_WHITE}{text}{RESET}"

    def center(self, text: str) -> str:
        """Center *text* within the display width."""
        pad = max(0, self.display_width - _ansi_len(text))
        return " " * (pad // 2) + text

    # ── Text wrapping ──

    def wrap(self, text: str, indent: int = 2, width: int | None = None) -> list[str]:
        """
        Word-wrap *text* to ``prose_width`` (or *width*).

        Returns a list of lines, each prefixed with *indent* spaces.
        Paragraph breaks (blank lines in the source) are preserved.
        """
        w = width or self.prose_width
        lines: list[str] = []
        for para in text.strip().split("\n"):
            para = para.strip()
            if not para:
                lines.append("")
                continue
            for line in textwrap.wrap(para, width=w):
                lines.append(" " * indent + line)
        return lines

    def wrap_str(self, text: str, indent: int = 2, width: int | None = None) -> str:
        """Convenience: ``wrap()`` joined into a single string."""
        return "\n".join(self.wrap(text, indent, width))

    # ── Padding / column helpers ──

    def pad(self, text: str, target: int | None = None) -> str:
        """Right-pad *text* to *target* visible chars (default: col_width)."""
        return _ansi_pad(text, target or self.col_width)

    def merge_columns(self, left: list[str], right: list[str],
                      gutter: str = "  ") -> list[str]:
        """Side-by-side merge of two line lists."""
        cw = self.col_width
        result = []
        for i in range(max(len(left), len(right))):
            l = left[i] if i < len(left) else ""
            r = right[i] if i < len(right) else ""
            result.append(f"{_ansi_pad(l, cw)}{gutter}{r}")
        return result

    # ── Semantic color helpers ──
    # These match the old _yl/_gr/_cy/etc. but are methods so they
    # stay co-located with the formatter.

    @staticmethod
    def yl(text: str) -> str:
        """Bright yellow."""
        return f"{BRIGHT_YELLOW}{text}{RESET}"

    @staticmethod
    def gr(text: str) -> str:
        """Bright green."""
        return f"{BRIGHT_GREEN}{text}{RESET}"

    @staticmethod
    def cy(text: str) -> str:
        """Cyan."""
        return f"{CYAN}{text}{RESET}"

    @staticmethod
    def bl(text: str) -> str:
        """Bright blue."""
        return f"{BRIGHT_BLUE}{text}{RESET}"

    @staticmethod
    def mg(text: str) -> str:
        """Bright magenta."""
        return f"{BRIGHT_MAGENTA}{text}{RESET}"

    @staticmethod
    def rd(text: str) -> str:
        """Bright red."""
        return f"{BRIGHT_RED}{text}{RESET}"

    @staticmethod
    def dim(text: str) -> str:
        """Dim text."""
        return f"{DIM}{text}{RESET}"

    @staticmethod
    def hdr(text: str) -> str:
        """Bold bright-white (alias for header)."""
        return f"{BOLD}{BRIGHT_WHITE}{text}{RESET}"
