# -*- coding: utf-8 -*-
"""tests/test_scene_summary_storage_cap.py

Storage-seam regression for the scene/plot summary cap.

The command layer already truncates over-long summaries with a user notice
(tests/test_qa_scene_bad_arg_and_summary_cap.py). THIS file pins the *storage
seam* — the engine functions that actually write the `summary` column — so the
cap holds for every producer, including ones that never pass through a command:

  - engine.scenes.set_scene_summary       (+scene/summary path)
  - engine.plots.create_plot / update_plot (+plot/create, +plot/summary paths)
  - engine.idle_queue.SceneSummaryTask     (the background Mistral summary writer,
                                            which writes raw LLM output via SQL)

Without the seam cap a misbehaving/non-Ollama provider or a future web/API
producer could persist an unbounded blob (the QA repro stored a 100 KB summary).
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import engine.scenes as scenes_mod
import engine.plots as plots_mod
import engine.idle_queue as idle_mod


# ── engine.scenes.set_scene_summary ─────────────────────────────────────────────

class TestSceneSummarySeam(unittest.IsolatedAsyncioTestCase):

    class _DB:
        def __init__(self, creator_id=1):
            self.executes = []
            self._creator_id = creator_id

        async def fetchall(self, sql, params=()):
            if "creator_id" in sql and "scenes" in sql:
                return [{"creator_id": self._creator_id}]
            return []

        async def execute(self, sql, params=()):
            self.executes.append((sql, params))

        async def commit(self):
            pass

    async def test_over_cap_summary_clamped_at_seam(self):
        room_id = 990001
        scenes_mod._active_scenes[room_id] = 555
        self.addCleanup(scenes_mod._active_scenes.pop, room_id, None)

        db = self._DB(creator_id=1)
        char = {"id": 1, "is_admin": 0}
        long_text = "A" * (scenes_mod.MAX_SUMMARY_LEN + 5000)

        res = await scenes_mod.set_scene_summary(db, char, room_id, long_text)
        self.assertTrue(res["ok"])

        updates = [p for (s, p) in db.executes
                   if "UPDATE scenes SET summary" in s]
        self.assertTrue(updates, "summary UPDATE must fire")
        stored = updates[0][0]
        self.assertEqual(len(stored), scenes_mod.MAX_SUMMARY_LEN,
                         "stored summary must be clamped at the storage seam")

    async def test_under_cap_summary_unchanged(self):
        room_id = 990002
        scenes_mod._active_scenes[room_id] = 556
        self.addCleanup(scenes_mod._active_scenes.pop, room_id, None)

        db = self._DB(creator_id=1)
        char = {"id": 1, "is_admin": 0}
        res = await scenes_mod.set_scene_summary(db, char, room_id, "  A short tale.  ")
        self.assertTrue(res["ok"])
        stored = [p for (s, p) in db.executes
                  if "UPDATE scenes SET summary" in s][0][0]
        self.assertEqual(stored, "A short tale.")  # stripped, intact


# ── engine.plots.create_plot / update_plot ──────────────────────────────────────

class TestPlotSummarySeam(unittest.IsolatedAsyncioTestCase):

    async def test_create_plot_clamps_summary(self):
        captured = {}

        class _DB:
            async def execute(self, sql, params=()):
                if "INSERT INTO plots" in sql:
                    captured["summary"] = params[1]

            async def commit(self):
                pass

            async def fetchall(self, sql, params=()):
                return [{
                    "id": 1, "title": "T", "summary": captured.get("summary", ""),
                    "creator_id": 1, "creator_name": "Rex", "status": "open",
                    "created_at": 0.0, "updated_at": 0.0,
                }]

        long_text = "X" * (plots_mod.MAX_SUMMARY_LEN + 1000)
        res = await plots_mod.create_plot(_DB(), 1, "Rex", "Title", long_text)
        self.assertEqual(len(captured["summary"]), plots_mod.MAX_SUMMARY_LEN)
        self.assertEqual(len(res["summary"]), plots_mod.MAX_SUMMARY_LEN)

    async def test_update_plot_clamps_summary(self):
        captured = {}

        class _DB:
            async def execute(self, sql, params=()):
                captured["params"] = params

            async def commit(self):
                pass

        long_text = "Y" * (plots_mod.MAX_SUMMARY_LEN + 1000)
        ok = await plots_mod.update_plot(_DB(), 7, summary=long_text)
        self.assertTrue(ok)
        # vals = [summary_clamped, updated_at, plot_id]
        self.assertEqual(len(captured["params"][0]), plots_mod.MAX_SUMMARY_LEN)

    async def test_update_plot_without_summary_is_fine(self):
        class _DB:
            async def execute(self, sql, params=()):
                pass

            async def commit(self):
                pass

        ok = await plots_mod.update_plot(_DB(), 7, status="closed")
        self.assertTrue(ok)


# ── engine.idle_queue.SceneSummaryTask (LLM writer) ──────────────────────────────

class TestIdleQueueSummarySeam(unittest.IsolatedAsyncioTestCase):

    async def test_llm_summary_clamped_before_write(self):
        captured = {}

        class _DB:
            async def execute(self, sql, params=()):
                if "UPDATE scenes SET summary" in sql:
                    captured["summary"] = params[0]

            async def commit(self):
                pass

        class _AI:
            async def generate(self, **kwargs):
                # An over-long / misbehaving-provider output (max_tokens is a
                # soft hint the provider can ignore). "A"*N is era-clean.
                return "A" * (idle_mod.MAX_SUMMARY_LEN + 8000)

        task = idle_mod.SceneSummaryTask(
            scene_id=5, room_name="Cantina",
            participants="Rex", poses_text="Rex: greets the room.",
        )
        await task.execute(_AI(), _DB())
        self.assertIn("summary", captured, "LLM summary must be persisted")
        self.assertEqual(len(captured["summary"]), idle_mod.MAX_SUMMARY_LEN,
                         "raw LLM summary must be clamped at the storage seam")


# ── Drift guard: every layer's cap agrees ────────────────────────────────────────

class TestSummaryCapDriftGuard(unittest.TestCase):

    def test_all_caps_agree(self):
        from parser.scene_commands import MAX_SUMMARY_LEN as scene_cmd_cap
        from parser.plot_commands import MAX_SUMMARY_LEN as plot_cmd_cap
        caps = {
            "engine.scenes": scenes_mod.MAX_SUMMARY_LEN,
            "engine.plots": plots_mod.MAX_SUMMARY_LEN,
            "engine.idle_queue": idle_mod.MAX_SUMMARY_LEN,
            "parser.scene_commands": scene_cmd_cap,
            "parser.plot_commands": plot_cmd_cap,
        }
        self.assertEqual(set(caps.values()), {4000},
                         f"summary caps must all equal 4000: {caps}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
