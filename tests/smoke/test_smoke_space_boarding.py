# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_space_boarding.py — Pytest entry points for
SH4 Layer A: boarding & crew (S1-S5).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import space_boarding


pytestmark = pytest.mark.smoke


class TestSpaceBoarding:
    """Layer A — boarding & crew. The spine of every other space
    scenario."""

    async def test_s1_board_ship_and_look_bridge(self, harness):
        await space_boarding.s1_board_ship_and_look_bridge(harness)

    async def test_s2_pilot_seat(self, harness):
        await space_boarding.s2_pilot_seat(harness)

    async def test_s3_all_crew_stations_cycle(self, harness):
        await space_boarding.s3_all_crew_stations_cycle(harness)

    async def test_s4_multi_pc_crew_coordination(self, harness):
        await space_boarding.s4_multi_pc_crew_coordination(harness)

    async def test_s5_disembark_returns_to_dock(self, harness):
        await space_boarding.s5_disembark_returns_to_dock(harness)
