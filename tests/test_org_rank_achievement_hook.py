# -*- coding: utf-8 -*-
"""tests/test_org_rank_achievement_hook.py — promote() emits on_org_rank_reached.

Defect-hunt finding: engine/achievements.py::on_org_rank_reached was defined but
NEVER called, so the `faction_loyalist` achievement (trigger org_rank_reached
count 3) could never fire. engine/organizations.py::promote now emits the hook
after recording the promotion. Both manual `promote` and `check_auto_promote`
(which calls promote) flow through the one emit. Fail-safe: a hook failure must
not block the promotion.
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

from engine import organizations


class _FakeDB:
    """Minimal DB that lets promote() succeed up to (and past) the hook."""
    def __init__(self):
        self.updated = []

    async def get_organization(self, code):
        return {"id": 1, "name": "Test Guild"}

    async def get_membership(self, char_id, org_id):
        return {"rank_level": 2, "rep_score": 100}

    async def get_org_ranks(self, org_id):
        # next rank (level 3) needs 50 rep; the member has 100 -> qualifies.
        return [{"rank_level": 3, "title": "Captain", "min_rep": 50,
                 "equipment": "[]"}]

    async def update_membership(self, char_id, org_id, rank_level=None):
        self.updated.append((char_id, org_id, rank_level))

    async def log_faction_action(self, *a, **k):
        pass


class TestOrgRankAchievementHook(unittest.IsolatedAsyncioTestCase):
    async def test_promote_emits_org_rank_hook_with_new_level(self):
        db = _FakeDB()
        char = {"id": 7, "name": "Han"}
        with mock.patch("engine.achievements.on_org_rank_reached",
                        new=mock.AsyncMock()) as spy:
            ok, msg = await organizations.promote(char, "test_guild", db)
        self.assertTrue(ok, msg)
        spy.assert_awaited_once()
        args = spy.await_args.args
        self.assertEqual(args[0], db)        # db
        self.assertEqual(args[1], 7)         # char_id
        self.assertEqual(args[2], 3)         # new rank level (high-water mark)

    async def test_hook_failure_does_not_block_promotion(self):
        db = _FakeDB()
        char = {"id": 7, "name": "Han"}

        async def _boom(*a, **k):
            raise RuntimeError("achievement DB unavailable")

        with mock.patch("engine.achievements.on_org_rank_reached", new=_boom):
            ok, msg = await organizations.promote(char, "test_guild", db)
        self.assertTrue(ok, "a hook failure must not block the promotion")
        self.assertIn("promoted", msg.lower())
        # the rank update still happened (promotion persisted)
        self.assertEqual(db.updated[-1][2], 3)

    async def test_no_promotion_no_hook(self):
        # Already max rank -> promote fails -> hook must NOT fire.
        class _MaxedDB(_FakeDB):
            async def get_org_ranks(self, org_id):
                return [{"rank_level": 2, "title": "Member", "min_rep": 0,
                         "equipment": "[]"}]  # no level-3 rank exists

        db = _MaxedDB()
        char = {"id": 7, "name": "Han"}
        with mock.patch("engine.achievements.on_org_rank_reached",
                        new=mock.AsyncMock()) as spy:
            ok, _ = await organizations.promote(char, "test_guild", db)
        self.assertFalse(ok)
        spy.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
