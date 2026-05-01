# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_economy_progression.py — Pytest entry points
for E1-E6 (economy + progression).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import economy_progression


pytestmark = pytest.mark.smoke


class TestEconomyProgression:
    """Shop, market, CP, kudos, scenebonus, survey."""

    async def test_e1_shop_lists(self, harness):
        await economy_progression.e1_shop_lists(harness)

    async def test_e2_market_lists(self, harness):
        await economy_progression.e2_market_lists(harness)

    async def test_e3_cpstatus(self, harness):
        await economy_progression.e3_cpstatus(harness)

    async def test_e4_kudos_awards_cp(self, harness):
        await economy_progression.e4_kudos_awards_cp(harness)

    async def test_e5_scenebonus_runs(self, harness):
        await economy_progression.e5_scenebonus_runs(harness)

    async def test_e6_survey_runs_with_skill(self, harness):
        await economy_progression.e6_survey_runs_with_skill(harness)
