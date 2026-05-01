# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_missions_factions.py — Pytest entry points
for Q1-Q6 (missions, bounties, factions, scenes, plots).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import missions_factions


pytestmark = pytest.mark.smoke


class TestMissionsFactions:
    """Missions, bounties, factions, reputation, scenes, plots."""

    async def test_q1_missions_list(self, harness):
        await missions_factions.q1_missions_list(harness)

    async def test_q2_bounties_list(self, harness):
        await missions_factions.q2_bounties_list(harness)

    async def test_q3_faction_list(self, harness):
        await missions_factions.q3_faction_list(harness)

    async def test_q4_reputation(self, harness):
        await missions_factions.q4_reputation(harness)

    async def test_q5_scenes_list(self, harness):
        await missions_factions.q5_scenes_list(harness)

    async def test_q6_plots_list(self, harness):
        await missions_factions.q6_plots_list(harness)
