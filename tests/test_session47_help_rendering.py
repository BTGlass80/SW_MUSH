"""
Session 47 tests — CLI rendering of enriched help entries.

The core HelpEntry / HelpManager / loader behaviour is covered by
``test_session47_help_system.py``. This file focuses on the one
surface that file doesn't touch: ``HelpCommand._render_entry``.

Coverage:
  - Old-shape entries (no summary, no examples) render identically
    to the pre-redesign output
  - Entries with a ``summary`` show the summary between title and body
  - Entries where the auto-derived summary duplicates the opening of
    the body don't print it twice
  - Entries with ``examples`` render an EXAMPLES block
  - Entries with ``examples`` containing empty/blank ``cmd`` skip
    those items instead of printing blanks
  - The legacy ``HelpCommand.CATEGORIES`` dict is still present (a
    guard: when the upcoming +help command refactor removes it, it
    must also update ``_show_categories`` to read from the manager)

These are async tests that exercise the real render method with an
in-memory send_line capture. No database, no server, no network.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ── Test harness ────────────────────────────────────────────────────────────

class _CaptureSession:
    """Minimal stand-in for ctx.session — captures every send_line call.

    Lines go into ``self.lines`` with ANSI escape sequences intact so
    tests can assert on raw content. ``output`` returns a single joined
    string for substring asserts.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []

    async def send_line(self, s: str) -> None:
        self.lines.append(s)

    @property
    def output(self) -> str:
        return "\n".join(self.lines)


class _Ctx:
    """Minimal ctx — just needs a ``.session``."""

    def __init__(self) -> None:
        self.session = _CaptureSession()


def _run(coro):
    """Run an async coroutine inside a fresh event loop for the test.

    A fresh loop avoids pytest-asyncio state bleeding between tests.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Tests ───────────────────────────────────────────────────────────────────

class TestRenderEntryBackwardCompat(unittest.TestCase):
    """Old-shape entries — no summary, no examples — must render the
    way they always did: title banner, body, optional see-also."""

    def setUp(self):
        from data.help_topics import HelpEntry
        from parser.builtin_commands import HelpCommand
        self.HelpEntry = HelpEntry
        self.cmd = HelpCommand()

    def test_old_shape_renders_without_crash(self):
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="legacy",
            title="Legacy Entry",
            category="Rules: Combat",
            body="First line of body.\nSecond line.",
            aliases=["leg"],
            see_also=["combat"],
            access_level=0,
        )
        _run(self.cmd._render_entry(ctx, entry))
        out = ctx.session.output
        self.assertIn("Legacy Entry", out)
        self.assertIn("First line of body", out)
        self.assertIn("Second line", out)
        self.assertIn("Rules: Combat", out)

    def test_see_also_rendered_when_present(self):
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X",
            body="Body.", see_also=["other1", "other2"],
        )
        _run(self.cmd._render_entry(ctx, entry))
        out = ctx.session.output
        self.assertIn("SEE ALSO", out)
        self.assertIn("other1", out)
        self.assertIn("other2", out)

    def test_no_see_also_omits_section(self):
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X", body="Body.",
        )
        _run(self.cmd._render_entry(ctx, entry))
        self.assertNotIn("SEE ALSO", ctx.session.output)


class TestRenderEntrySummary(unittest.TestCase):
    """Summary rendering — shown between title and body, but only when
    it adds information beyond the first line of the body."""

    def setUp(self):
        from data.help_topics import HelpEntry
        from parser.builtin_commands import HelpCommand
        self.HelpEntry = HelpEntry
        self.cmd = HelpCommand()

    def test_distinct_summary_is_rendered(self):
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X",
            body="The body starts with something completely different.",
            summary="A concise one-sentence pitch.",
        )
        _run(self.cmd._render_entry(ctx, entry))
        self.assertIn("A concise one-sentence pitch", ctx.session.output)

    def test_summary_matching_body_start_is_suppressed(self):
        """The migration auto-derived summaries from the first sentence
        of the body. Printing that twice would be noise."""
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X",
            body="The same opener appears here. Plus more detail after.",
            summary="The same opener appears here.",
        )
        _run(self.cmd._render_entry(ctx, entry))
        out = ctx.session.output
        # The opener must appear exactly once — from the body, not the
        # summary line.
        self.assertEqual(out.count("The same opener appears here"), 1)

    def test_empty_summary_is_silent(self):
        """An empty summary field must not produce a blank line or
        extra whitespace in the output."""
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X",
            body="Body content.",
            summary="",
        )
        _run(self.cmd._render_entry(ctx, entry))
        # Count blank lines: should match the pre-redesign layout
        # (blank after title banner, blank before final banner, and
        # nothing else).
        blanks = sum(1 for ln in ctx.session.lines if ln == "")
        # Exact count could change with future layout tweaks — assert
        # the summary didn't contribute an extra one by comparing
        # against a control entry.
        ctx_ctrl = _Ctx()
        entry_ctrl = self.HelpEntry(
            key="k", title="K", category="X", body="Body content.",
            # summary omitted — default empty
        )
        _run(self.cmd._render_entry(ctx_ctrl, entry_ctrl))
        blanks_ctrl = sum(1 for ln in ctx_ctrl.session.lines if ln == "")
        self.assertEqual(blanks, blanks_ctrl)


class TestRenderEntryExamples(unittest.TestCase):
    """Examples rendering — appears after body, before see-also."""

    def setUp(self):
        from data.help_topics import HelpEntry
        from parser.builtin_commands import HelpCommand
        self.HelpEntry = HelpEntry
        self.cmd = HelpCommand()

    def test_examples_block_rendered(self):
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X",
            body="Body.",
            examples=[
                {"cmd": "attack greedo", "description": "Attack Greedo at range."},
                {"cmd": "dodge", "description": "Declare a reactive dodge."},
            ],
        )
        _run(self.cmd._render_entry(ctx, entry))
        out = ctx.session.output
        self.assertIn("EXAMPLES", out)
        self.assertIn("attack greedo", out)
        self.assertIn("Attack Greedo at range", out)
        self.assertIn("dodge", out)
        self.assertIn("Declare a reactive dodge", out)

    def test_example_without_description_still_renders(self):
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X",
            body="Body.",
            examples=[{"cmd": "dodge", "description": ""}],
        )
        _run(self.cmd._render_entry(ctx, entry))
        out = ctx.session.output
        self.assertIn("EXAMPLES", out)
        self.assertIn("dodge", out)

    def test_example_with_blank_cmd_is_skipped(self):
        """A malformed example with no ``cmd`` must not render a blank
        row — it just gets dropped."""
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X",
            body="Body.",
            examples=[
                {"cmd": "", "description": "Orphan description"},
                {"cmd": "good", "description": "A valid one."},
            ],
        )
        _run(self.cmd._render_entry(ctx, entry))
        out = ctx.session.output
        self.assertNotIn("Orphan description", out)
        self.assertIn("good", out)

    def test_no_examples_omits_section(self):
        ctx = _Ctx()
        entry = self.HelpEntry(
            key="k", title="K", category="X",
            body="Body.",
        )
        _run(self.cmd._render_entry(ctx, entry))
        self.assertNotIn("EXAMPLES", ctx.session.output)


class TestHelpCommandLegacyCategories(unittest.TestCase):
    """Guard on the legacy hard-coded CATEGORIES dict.

    ``HelpCommand.CATEGORIES`` predates the HelpEntry.category field.
    Both exist today — the dict drives the top-level ``+help`` listing,
    the field drives ``+help/search`` and the (future) web portal.

    When the upcoming command refactor drops CATEGORIES in favour of
    reading ``help_mgr.categories()`` inside ``_show_categories``,
    this test will fail and that's the right time to delete it. It
    exists as a trip-wire so nobody removes the dict without also
    updating ``_show_categories``.
    """

    def test_categories_dict_still_exists(self):
        from parser.builtin_commands import HelpCommand
        self.assertTrue(
            hasattr(HelpCommand, "CATEGORIES"),
            "HelpCommand.CATEGORIES was removed. If this is intentional, "
            "update HelpCommand._show_categories to read from "
            "help_mgr.categories() and delete this test.",
        )


if __name__ == "__main__":
    unittest.main()
