# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_mission_loop.py — Pytest entry points for ML1-ML4.

Exercises the FACTION/MISSION core loop end-to-end:
  ML1: mission board renders
  ML2: accept → active (verified via `mission` + DB row)
  ML3: complete → credit delta (adjust_credits funnel)
  ML4: abandon → no active mission
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import mission_loop


pytestmark = pytest.mark.smoke


class TestMissionLoop:
    """Mission board → accept → complete (reward) → abandon."""

    async def test_ml1_board_renders(self, harness):
        await mission_loop.ml1_board_renders(harness)

    async def test_ml2_accept_shows_active(self, harness):
        await mission_loop.ml2_accept_shows_active(harness)

    async def test_ml3_complete_pays_reward(self, harness):
        await mission_loop.ml3_complete_pays_reward(harness)

    async def test_ml4_abandon_clears_mission(self, harness):
        await mission_loop.ml4_abandon_clears_mission(harness)
