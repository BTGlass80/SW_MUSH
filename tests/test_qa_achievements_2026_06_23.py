# -*- coding: utf-8 -*-
"""
tests/test_qa_achievements_2026_06_23.py — QA break-it regression
(achievements/progression sweep, 2026-06-23).

#1 [SWALLOW, BLOCKER] `+achievements` was dead for EVERY player -- it read
   `ctx.session.game_server.db`, but Session has no `game_server` attribute, so
   `hasattr(...)` was always False, `db` was None, and the command always
   printed "Achievement system unavailable." Fix: use the wired `ctx.db`.

#2 [SWALLOW] the `popular_figure` achievement (threshold 10) was permanently
   unreachable -- `on_kudos_received` was called with the WEEKLY kudos count
   (`kudos_count_received_this_week`, capped at KUDOS_PER_WEEK=3), never the
   lifetime total. Fix: a new `kudos_count_received_lifetime` db method, passed
   to `on_kudos_received`.
"""
from __future__ import annotations

import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACH_SRC = (REPO / "parser" / "achievement_commands.py").read_text(encoding="utf-8")
CP_SRC = (REPO / "parser" / "cp_commands.py").read_text(encoding="utf-8")


class TestAchievementsDbWiring(unittest.TestCase):
    def test_uses_ctx_db_not_session_game_server(self):
        self.assertIn("db = ctx.db", ACH_SRC)
        # the buggy assignment (not the explanatory comment) must be gone
        self.assertNotIn("db = ctx.session.game_server.db", ACH_SRC,
                         "+achievements must not read the nonexistent "
                         "session.game_server (it made the command always dead)")


class TestKudosLifetimeWiring(unittest.TestCase):
    def test_cp_commands_passes_lifetime_to_on_kudos_received(self):
        i = CP_SRC.index("from engine.achievements import on_kudos_received")
        block = CP_SRC[i:i + 500]
        self.assertIn("kudos_count_received_lifetime", block)
        self.assertNotIn("kudos_count_received_this_week", block,
                         "the achievement hook must use the lifetime count")

    def test_db_has_lifetime_method(self):
        from db.database import Database
        self.assertTrue(hasattr(Database, "kudos_count_received_lifetime"))


class TestKudosLifetimeBehavioral:
    async def test_lifetime_counts_all_weekly_counts_window(self, harness):
        tgt = (await harness.login_as("PopFigure")).character["id"]
        giver = (await harness.login_as("KudosGiver")).character["id"]
        now = time.time()
        # one OLD kudos (>7-day window) + one fresh
        await harness.db.kudos_log(giver, tgt, 1, now - 10 * 24 * 3600)
        await harness.db.kudos_log(giver, tgt, 1, now)
        weekly = await harness.db.kudos_count_received_this_week(tgt)
        lifetime = await harness.db.kudos_count_received_lifetime(tgt)
        assert weekly == 1, f"weekly window should see only the fresh kudos: {weekly}"
        assert lifetime == 2, f"lifetime must count both kudos: {lifetime}"


if __name__ == "__main__":
    unittest.main()
