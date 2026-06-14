# -*- coding: utf-8 -*-
"""tests/test_scene_achievement_hook.py — stop_scene emits on_scene_completed.

Defect-hunt finding: engine/achievements.py::on_scene_completed was defined but
NEVER called, so the `storyteller` achievement (complete 5 RP scenes) was
unwinnable. The completion seam is ENGINE-side — engine/scenes.py::stop_scene
sets status='completed' (the parser +scene/stop just calls it) — so the emit is
parallel-safe. Every IC participant (the pose_counts keys) is awarded, not just
whoever ran +scene/stop. Fail-safe: a hook error must not break the scene stop.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import engine.scenes as scenes_mod
from engine.scenes import stop_scene


class _FakeDB:
    """Lets stop_scene run to completion. char 7 is the creator (passes perms);
    IC posers are char 7 (x3) and char 8 (x2)."""
    async def fetchall(self, sql, params=()):
        if "FROM scenes WHERE id" in sql:
            return [{"id": params[0], "creator_id": 7, "status": "active"}]
        if "scene_poses" in sql:
            return [{"char_id": 7, "cnt": 3}, {"char_id": 8, "cnt": 2}]
        return []  # scene_participants / anything else

    async def execute(self, sql, params=()):
        pass

    async def commit(self):
        pass


class TestSceneAchievementHook(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._saved = dict(scenes_mod._active_scenes)
        scenes_mod._active_scenes.clear()

    def tearDown(self):
        scenes_mod._active_scenes.clear()
        scenes_mod._active_scenes.update(self._saved)

    async def test_awards_every_ic_participant(self):
        scenes_mod._active_scenes[100] = 55
        char = {"id": 7, "name": "Han", "is_admin": 0}
        with mock.patch("engine.achievements.on_scene_completed",
                        new=mock.AsyncMock()) as spy:
            res = await stop_scene(_FakeDB(), char, 100)
        self.assertTrue(res["ok"], res)
        awarded = sorted(call.args[1] for call in spy.await_args_list)
        self.assertEqual(awarded, [7, 8], "both IC posers should be awarded")

    async def test_hook_failure_does_not_break_scene_stop(self):
        scenes_mod._active_scenes[100] = 55
        char = {"id": 7, "name": "Han", "is_admin": 0}

        async def _boom(*a, **k):
            raise RuntimeError("achievement DB unavailable")

        with mock.patch("engine.achievements.on_scene_completed", new=_boom):
            res = await stop_scene(_FakeDB(), char, 100)
        self.assertTrue(res["ok"], "a hook failure must not break +scene/stop")
        self.assertEqual(res["pose_counts"], {7: 3, 8: 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)
