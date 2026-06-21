# -*- coding: utf-8 -*-
"""tests/test_qa_scene_bad_arg_and_summary_cap.py

QA regression tests for two parser fixes:
  LOW  — +scene <bad-arg>: negative/non-integer IDs produce "Invalid scene ID."
          instead of silently falling through to "No active scene here."
  MED  — +scene/summary and +plot/create, +plot/summary: summaries longer than
          MAX_SUMMARY_LEN (4000) are truncated with a truncation notice, not
          stored at full size (storage-DoS guard).
"""
from __future__ import annotations

import sys
import os
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from parser.scene_commands import SceneCommand, MAX_SUMMARY_LEN as SCENE_SUMMARY_CAP
from parser.plot_commands import MAX_SUMMARY_LEN as PLOT_SUMMARY_CAP


# ── Shared fake infrastructure ─────────────────────────────────────────────────

class _Lines:
    """Captures send_line output."""
    def __init__(self):
        self.lines = []

    async def send_line(self, text):
        self.lines.append(text)

    def combined(self):
        return "\n".join(self.lines)


def _make_ctx(args="", switches=None):
    session = mock.MagicMock()
    session.character = {"id": 1, "name": "Rex", "room_id": 42, "is_admin": 0}
    out = _Lines()
    session.send_line = out.send_line
    ctx = mock.MagicMock()
    ctx.args = args
    ctx.switches = switches or []
    ctx.session = session
    ctx._out = out
    ctx.db = mock.MagicMock()
    return ctx


# ── Tests: +scene <bad-arg> ────────────────────────────────────────────────────

class TestSceneBadArgDistinction(unittest.IsolatedAsyncioTestCase):

    async def _run_scene(self, args):
        ctx = _make_ctx(args=args)
        with mock.patch("engine.scenes.get_active_scene", new=mock.AsyncMock(return_value=None)):
            cmd = SceneCommand()
            await cmd.execute(ctx)
        return ctx._out.combined()

    async def test_negative_id_gives_invalid_error_not_no_scene(self):
        out = await self._run_scene("-1")
        self.assertIn("Invalid scene ID", out,
                      "negative ID must produce 'Invalid scene ID', not 'No active scene'")
        self.assertNotIn("No active scene", out)

    async def test_float_string_gives_invalid_error(self):
        out = await self._run_scene("3.5")
        self.assertIn("Invalid scene ID", out)
        self.assertNotIn("No active scene", out)

    async def test_alpha_string_gives_invalid_error(self):
        out = await self._run_scene("foo")
        self.assertIn("Invalid scene ID", out)
        self.assertNotIn("No active scene", out)

    async def test_valid_positive_id_calls_show_log(self):
        ctx = _make_ctx(args="7")
        scene_detail = {
            "id": 7, "title": "Test Scene", "status": "completed",
            "scene_type": "Social", "location": "Cantina",
            "started_at": 1700000000.0, "completed_at": 1700001000.0,
            "summary": "", "creator_name": "Rex",
            "participants": ["Rex"], "poses": [],
        }
        with mock.patch("engine.scenes.get_scene_detail",
                        new=mock.AsyncMock(return_value=scene_detail)):
            cmd = SceneCommand()
            await cmd.execute(ctx)
        out = ctx._out.combined()
        self.assertIn("Test Scene", out, "scene log display should include the scene title")
        self.assertNotIn("Invalid scene ID", out)

    async def test_no_args_falls_through_to_room_scene(self):
        ctx = _make_ctx(args="")
        with mock.patch("engine.scenes.get_active_scene",
                        new=mock.AsyncMock(return_value=None)):
            cmd = SceneCommand()
            await cmd.execute(ctx)
        out = ctx._out.combined()
        self.assertIn("No active scene", out,
                      "empty args should still show room scene message")


# ── Tests: scene summary cap ───────────────────────────────────────────────────

class TestSceneSummaryCap(unittest.IsolatedAsyncioTestCase):

    async def _run_summary_field(self, value):
        ctx = _make_ctx(args=value, switches=["summary"])
        saved_summary = {}

        async def _fake_set_summary(db, char, room_id, summary):
            saved_summary["value"] = summary
            return {"ok": True, "msg": "Scene summary saved."}

        with mock.patch("engine.scenes.set_scene_summary",
                        new=_fake_set_summary):
            cmd = SceneCommand()
            await cmd.execute(ctx)

        return ctx._out.combined(), saved_summary.get("value", "")

    async def test_summary_over_cap_is_truncated(self):
        long_text = "A" * (SCENE_SUMMARY_CAP + 500)
        out, stored = await self._run_summary_field(long_text)
        self.assertEqual(len(stored), SCENE_SUMMARY_CAP,
                         "stored summary must not exceed MAX_SUMMARY_LEN")
        self.assertIn("truncated", out.lower(),
                      "user must be notified of truncation")

    async def test_summary_at_cap_is_stored_intact(self):
        exact_text = "B" * SCENE_SUMMARY_CAP
        _out, stored = await self._run_summary_field(exact_text)
        self.assertEqual(len(stored), SCENE_SUMMARY_CAP)

    async def test_summary_under_cap_stored_intact(self):
        short_text = "Short summary."
        _out, stored = await self._run_summary_field(short_text)
        self.assertEqual(stored, short_text)

    def test_scene_summary_cap_value(self):
        self.assertEqual(SCENE_SUMMARY_CAP, 4000)


# ── Tests: plot summary cap ────────────────────────────────────────────────────

class TestPlotSummaryCap(unittest.IsolatedAsyncioTestCase):

    async def _run_plot_create(self, summary_text):
        from parser.plot_commands import _cmd_create
        saved = {}

        async def _fake_create(db, creator_id, creator_name, title, summary):
            saved["summary"] = summary
            return {"id": 1, "title": title}

        ctx = _make_ctx(args=f"My Plot={summary_text}")
        with mock.patch("engine.plots.create_plot", new=_fake_create):
            await _cmd_create(ctx)
        return ctx._out.combined(), saved.get("summary", "")

    async def _run_plot_summary_update(self, summary_text):
        from parser.plot_commands import _cmd_summary
        saved = {}

        async def _fake_update(db, plot_id, **kwargs):
            saved.update(kwargs)

        ctx = _make_ctx(args=f"1={summary_text}")
        plot_row = {"id": 1, "creator_id": 1, "title": "A Plot"}
        with mock.patch("engine.plots.get_plot",
                        new=mock.AsyncMock(return_value=plot_row)), \
             mock.patch("engine.plots.update_plot", new=_fake_update):
            await _cmd_summary(ctx)
        return ctx._out.combined(), saved.get("summary", "")

    async def test_create_long_summary_truncated(self):
        long = "X" * (PLOT_SUMMARY_CAP + 200)
        out, stored = await self._run_plot_create(long)
        self.assertLessEqual(len(stored), PLOT_SUMMARY_CAP)
        self.assertIn("truncated", out.lower())

    async def test_create_short_summary_intact(self):
        short = "A brief arc about pirates."
        _out, stored = await self._run_plot_create(short)
        self.assertEqual(stored, short)

    async def test_update_long_summary_truncated(self):
        long = "Y" * (PLOT_SUMMARY_CAP + 100)
        out, stored = await self._run_plot_summary_update(long)
        self.assertLessEqual(len(stored), PLOT_SUMMARY_CAP)
        self.assertIn("truncated", out.lower())

    async def test_update_short_summary_intact(self):
        short = "Just a few words."
        _out, stored = await self._run_plot_summary_update(short)
        self.assertEqual(stored, short)

    def test_plot_summary_cap_value(self):
        self.assertEqual(PLOT_SUMMARY_CAP, 4000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
