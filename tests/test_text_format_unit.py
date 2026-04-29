# -*- coding: utf-8 -*-
"""
tests/test_text_format_unit.py — Code review C6 fix tests (drop K-C6i)

Per code_review_session32.md Severity C6 ("24 Untested Engine Files"):
`engine/text_format.py` is the shared width-aware formatter used by
every display surface (Telnet, WebSocket browser client). A regression
here silently breaks layout on every screen the player ever sees.

Coverage:
  - _ansi_len: strips ANSI codes correctly across single + multi-color
    runs, plain strings, mixed content.
  - _ansi_pad: pads to visible width, doesn't pad if already at/over
    width, handles strings with ANSI mid-string.
  - Fmt construction: default width = DEFAULT_WIDTH, MIN_WIDTH floor
    enforced via __post_init__.
  - prose_width: width - 4, capped at MAX_PROSE_WIDTH.
  - col_width: (width - 4) // 2 for two-column layouts.
  - display_width: prose_width + 4 (bar frames indented prose).
  - bar(): spans display_width, uses given char + color, ends with RESET.
  - header(): bold + bright-white wrapping.
  - center(): pads to display_width.
  - wrap(): splits, indents, preserves blank-line paragraph breaks.
  - wrap_str(): joins wrap output with newlines.
  - pad(): pads to col_width by default.
  - merge_columns(): side-by-side merge with default gutter, handles
    uneven list lengths.
  - Static color helpers (yl/gr/cy/bl/mg/rd/dim/hdr): wrap text with
    expected ANSI codes.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.text_format import (  # noqa: E402
    DEFAULT_WIDTH,
    Fmt,
    MAX_PROSE_WIDTH,
    MIN_WIDTH,
    _ansi_len,
    _ansi_pad,
)
from server.ansi import (  # noqa: E402
    BOLD,
    BRIGHT_BLUE,
    BRIGHT_CYAN,
    BRIGHT_GREEN,
    BRIGHT_MAGENTA,
    BRIGHT_RED,
    BRIGHT_WHITE,
    BRIGHT_YELLOW,
    CYAN,
    DIM,
    RESET,
)


# ══════════════════════════════════════════════════════════════════════════════
# _ansi_len — visible-character counting
# ══════════════════════════════════════════════════════════════════════════════


class TestAnsiLen(unittest.TestCase):
    def test_plain_string(self):
        self.assertEqual(_ansi_len("hello"), 5)

    def test_empty_string(self):
        self.assertEqual(_ansi_len(""), 0)

    def test_single_color_wrap(self):
        # 5 visible chars wrapped in BRIGHT_RED + RESET
        s = f"{BRIGHT_RED}hello{RESET}"
        self.assertEqual(_ansi_len(s), 5)

    def test_multi_color_run(self):
        s = f"{BOLD}{BRIGHT_RED}red{RESET} {BRIGHT_GREEN}green{RESET}"
        self.assertEqual(_ansi_len(s), len("red green"))

    def test_only_ansi_codes(self):
        s = f"{BOLD}{RESET}"
        self.assertEqual(_ansi_len(s), 0)

    def test_handles_complex_codes(self):
        # Codes like \033[1;36m (bold + cyan) should also strip
        s = "\033[1;36mhello\033[0m"
        self.assertEqual(_ansi_len(s), 5)


# ══════════════════════════════════════════════════════════════════════════════
# _ansi_pad — right-pad to visible width
# ══════════════════════════════════════════════════════════════════════════════


class TestAnsiPad(unittest.TestCase):
    def test_pads_plain_string(self):
        result = _ansi_pad("hi", 5)
        self.assertEqual(result, "hi   ")

    def test_no_pad_when_already_at_width(self):
        result = _ansi_pad("hello", 5)
        self.assertEqual(result, "hello")

    def test_no_pad_when_over_width(self):
        # String longer than target: just return as-is (max(0, ...))
        result = _ansi_pad("hello world", 5)
        self.assertEqual(result, "hello world")

    def test_pads_after_ansi_codes(self):
        s = f"{BRIGHT_RED}hi{RESET}"
        result = _ansi_pad(s, 5)
        # Visible 'hi' is 2 chars; pad with 3 spaces after the RESET
        self.assertEqual(result, s + "   ")
        # The visible length of the result is 5
        self.assertEqual(_ansi_len(result), 5)

    def test_zero_width_returns_unchanged(self):
        # max(0, 0 - 5) = 0 spaces
        self.assertEqual(_ansi_pad("hello", 0), "hello")


# ══════════════════════════════════════════════════════════════════════════════
# Fmt construction + width clamping
# ══════════════════════════════════════════════════════════════════════════════


class TestFmtConstruction(unittest.TestCase):
    def test_default_width(self):
        fmt = Fmt()
        self.assertEqual(fmt.width, DEFAULT_WIDTH)

    def test_explicit_width(self):
        fmt = Fmt(width=120)
        self.assertEqual(fmt.width, 120)

    def test_below_min_width_clamps_up(self):
        # MIN_WIDTH is the floor — narrower clients still get this min
        fmt = Fmt(width=20)
        self.assertEqual(fmt.width, MIN_WIDTH)

    def test_min_width_unchanged(self):
        fmt = Fmt(width=MIN_WIDTH)
        self.assertEqual(fmt.width, MIN_WIDTH)

    def test_zero_width_clamps_to_min(self):
        fmt = Fmt(width=0)
        self.assertEqual(fmt.width, MIN_WIDTH)


# ══════════════════════════════════════════════════════════════════════════════
# Computed widths
# ══════════════════════════════════════════════════════════════════════════════


class TestComputedWidths(unittest.TestCase):
    def test_prose_width_is_width_minus_four(self):
        fmt = Fmt(width=80)
        self.assertEqual(fmt.prose_width, 76)

    def test_prose_width_capped_at_max(self):
        # Width 200 -> 196 raw -> capped at MAX_PROSE_WIDTH
        fmt = Fmt(width=200)
        self.assertEqual(fmt.prose_width, MAX_PROSE_WIDTH)

    def test_col_width_for_two_column(self):
        fmt = Fmt(width=80)
        # (80 - 4) // 2 = 38
        self.assertEqual(fmt.col_width, 38)

    def test_col_width_handles_odd(self):
        fmt = Fmt(width=81)
        # (81 - 4) // 2 = 38 (floor)
        self.assertEqual(fmt.col_width, 38)

    def test_display_width_is_prose_width_plus_four(self):
        fmt = Fmt(width=80)
        self.assertEqual(fmt.display_width, fmt.prose_width + 4)
        self.assertEqual(fmt.display_width, 80)

    def test_display_width_with_capped_prose(self):
        # Wide client: prose capped at MAX_PROSE_WIDTH=100,
        # display_width = 104
        fmt = Fmt(width=200)
        self.assertEqual(fmt.display_width, MAX_PROSE_WIDTH + 4)


# ══════════════════════════════════════════════════════════════════════════════
# Decorative elements
# ══════════════════════════════════════════════════════════════════════════════


class TestBar(unittest.TestCase):
    def test_default_char_and_color(self):
        fmt = Fmt(width=80)
        bar = fmt.bar()
        # Should contain the BRIGHT_CYAN code and RESET
        self.assertIn(BRIGHT_CYAN, bar)
        self.assertTrue(bar.endswith(RESET))
        # Visible length matches display_width
        self.assertEqual(_ansi_len(bar), fmt.display_width)

    def test_custom_char(self):
        fmt = Fmt(width=80)
        bar = fmt.bar(char="-")
        # Strip color codes; should be all dashes
        stripped = bar.replace(BRIGHT_CYAN, "").replace(RESET, "")
        self.assertEqual(set(stripped), {"-"})

    def test_custom_color(self):
        fmt = Fmt(width=80)
        bar = fmt.bar(color=BRIGHT_RED)
        self.assertIn(BRIGHT_RED, bar)
        self.assertNotIn(BRIGHT_CYAN, bar)


class TestHeader(unittest.TestCase):
    def test_wraps_with_bold_bright_white(self):
        fmt = Fmt()
        result = fmt.header("Title")
        self.assertIn(BOLD, result)
        self.assertIn(BRIGHT_WHITE, result)
        self.assertIn("Title", result)
        self.assertTrue(result.endswith(RESET))


class TestCenter(unittest.TestCase):
    def test_centers_within_display_width(self):
        fmt = Fmt(width=80)
        # display_width = 80 — text 'hi' (2 chars) means 78 pad,
        # half = 39 leading spaces
        out = fmt.center("hi")
        self.assertTrue(out.startswith(" " * 39))
        self.assertIn("hi", out)

    def test_handles_ansi_in_text(self):
        fmt = Fmt(width=80)
        text = f"{BRIGHT_GREEN}hi{RESET}"
        out = fmt.center(text)
        # Visible length of leading spaces should still be (80-2)//2 = 39
        leading = out[:len(out) - len(text)]
        self.assertEqual(len(leading), 39)

    def test_text_wider_than_display_no_negative_pad(self):
        fmt = Fmt(width=80)
        long_text = "x" * 200
        out = fmt.center(long_text)
        # No leading spaces (max(0, ...) = 0)
        self.assertTrue(out.startswith("xxx"))


# ══════════════════════════════════════════════════════════════════════════════
# wrap / wrap_str
# ══════════════════════════════════════════════════════════════════════════════


class TestWrap(unittest.TestCase):
    def test_short_text_one_line(self):
        fmt = Fmt(width=80)
        lines = fmt.wrap("Hello")
        self.assertEqual(len(lines), 1)
        # Default indent = 2
        self.assertTrue(lines[0].startswith("  "))
        self.assertTrue(lines[0].endswith("Hello"))

    def test_long_text_wraps(self):
        fmt = Fmt(width=40)  # narrow -> prose_width = 36
        text = "word " * 30  # ~150 chars
        lines = fmt.wrap(text)
        # Multiple lines
        self.assertGreater(len(lines), 1)
        # Every line should be <= prose_width + indent
        for line in lines:
            self.assertLessEqual(len(line), fmt.prose_width + 2)

    def test_paragraph_break_preserved(self):
        fmt = Fmt(width=80)
        text = "First para.\n\nSecond para."
        lines = fmt.wrap(text)
        # Should have at least one empty line between
        self.assertIn("", lines)

    def test_custom_indent(self):
        fmt = Fmt(width=80)
        lines = fmt.wrap("Hello", indent=4)
        self.assertTrue(lines[0].startswith("    "))

    def test_zero_indent(self):
        fmt = Fmt(width=80)
        lines = fmt.wrap("Hello", indent=0)
        self.assertTrue(lines[0].startswith("Hello"))

    def test_custom_width_override(self):
        fmt = Fmt(width=80)
        # Force narrow wrap: width=10
        lines = fmt.wrap("one two three four five six seven", width=10)
        # Result is line-wrapped inside the 10-col window
        self.assertGreater(len(lines), 1)


class TestWrapStr(unittest.TestCase):
    def test_single_line_input_no_newline(self):
        # Short input fits in one wrapped line — wrap_str returns a
        # single line with the indent prefix and no embedded newline.
        fmt = Fmt(width=80)
        result = fmt.wrap_str("Hello world")
        self.assertNotIn("\n", result)
        self.assertIn("Hello world", result)
        # Default indent of 2
        self.assertTrue(result.startswith("  "))

    def test_multi_line_separated(self):
        fmt = Fmt(width=40)  # MIN_WIDTH clamp -> prose_width = 36
        # Make it longer than prose_width so wrap actually splits
        long_text = " ".join(["word"] * 20)  # 5*20 + 19 spaces = 99 chars
        result = fmt.wrap_str(long_text)
        self.assertIn("\n", result)


# ══════════════════════════════════════════════════════════════════════════════
# pad / merge_columns
# ══════════════════════════════════════════════════════════════════════════════


class TestPad(unittest.TestCase):
    def test_pads_to_col_width_default(self):
        fmt = Fmt(width=80)
        # col_width = 38
        result = fmt.pad("hi")
        self.assertEqual(_ansi_len(result), 38)

    def test_pads_to_explicit_target(self):
        fmt = Fmt()
        result = fmt.pad("hi", target=20)
        self.assertEqual(_ansi_len(result), 20)

    def test_no_pad_when_at_target(self):
        fmt = Fmt()
        result = fmt.pad("hello", target=5)
        self.assertEqual(result, "hello")


class TestMergeColumns(unittest.TestCase):
    def test_merges_equal_length_lists(self):
        fmt = Fmt(width=80)
        left = ["L1", "L2"]
        right = ["R1", "R2"]
        merged = fmt.merge_columns(left, right)
        self.assertEqual(len(merged), 2)
        # Each line should contain both
        self.assertIn("L1", merged[0])
        self.assertIn("R1", merged[0])
        self.assertIn("L2", merged[1])
        self.assertIn("R2", merged[1])

    def test_left_longer_than_right(self):
        fmt = Fmt(width=80)
        merged = fmt.merge_columns(["L1", "L2", "L3"], ["R1"])
        # Length = max(3, 1) = 3
        self.assertEqual(len(merged), 3)
        # Last two lines have no right content
        self.assertIn("L2", merged[1])
        self.assertIn("L3", merged[2])

    def test_right_longer_than_left(self):
        fmt = Fmt(width=80)
        merged = fmt.merge_columns(["L1"], ["R1", "R2", "R3"])
        self.assertEqual(len(merged), 3)
        self.assertIn("R2", merged[1])
        self.assertIn("R3", merged[2])

    def test_custom_gutter(self):
        fmt = Fmt(width=80)
        merged = fmt.merge_columns(["L"], ["R"], gutter=" | ")
        self.assertIn(" | ", merged[0])

    def test_left_padded_to_col_width(self):
        fmt = Fmt(width=80)
        # col_width = 38; default gutter = "  "
        merged = fmt.merge_columns(["L"], ["R"])
        # 'L' padded to 38 + 2 gutter + 'R' = total visible 41
        self.assertEqual(_ansi_len(merged[0]), 41)


# ══════════════════════════════════════════════════════════════════════════════
# Static color helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestColorHelpers(unittest.TestCase):
    def test_yl_wraps_with_bright_yellow(self):
        out = Fmt.yl("warn")
        self.assertEqual(out, f"{BRIGHT_YELLOW}warn{RESET}")

    def test_gr_wraps_with_bright_green(self):
        out = Fmt.gr("ok")
        self.assertEqual(out, f"{BRIGHT_GREEN}ok{RESET}")

    def test_cy_wraps_with_cyan(self):
        out = Fmt.cy("info")
        self.assertEqual(out, f"{CYAN}info{RESET}")

    def test_bl_wraps_with_bright_blue(self):
        out = Fmt.bl("link")
        self.assertEqual(out, f"{BRIGHT_BLUE}link{RESET}")

    def test_mg_wraps_with_bright_magenta(self):
        out = Fmt.mg("special")
        self.assertEqual(out, f"{BRIGHT_MAGENTA}special{RESET}")

    def test_rd_wraps_with_bright_red(self):
        out = Fmt.rd("err")
        self.assertEqual(out, f"{BRIGHT_RED}err{RESET}")

    def test_dim_wraps_with_dim(self):
        out = Fmt.dim("subtle")
        self.assertEqual(out, f"{DIM}subtle{RESET}")

    def test_hdr_wraps_with_bold_bright_white(self):
        out = Fmt.hdr("Title")
        self.assertEqual(out, f"{BOLD}{BRIGHT_WHITE}Title{RESET}")

    def test_helpers_are_static(self):
        # Should be callable on the class without an instance
        self.assertEqual(Fmt.yl("x"), f"{BRIGHT_YELLOW}x{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# Module constants
# ══════════════════════════════════════════════════════════════════════════════


class TestModuleConstants(unittest.TestCase):
    def test_default_width_sane(self):
        # Should be at least the min and at most ~80 for terminal default
        self.assertGreaterEqual(DEFAULT_WIDTH, MIN_WIDTH)
        self.assertLessEqual(DEFAULT_WIDTH, 100)

    def test_min_width_is_floor(self):
        self.assertGreater(MIN_WIDTH, 0)

    def test_max_prose_width_above_min(self):
        self.assertGreater(MAX_PROSE_WIDTH, MIN_WIDTH)


if __name__ == "__main__":
    unittest.main()
