# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_space_maneuvers_admin.py — Pytest entry points
for SH4 Layers D + F.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import space_maneuvers_admin


pytestmark = pytest.mark.smoke


class TestSpaceManeuversAdmin:
    """Layer D maneuvers + Layer F comms + admin commands."""

    async def test_s15_defensive_maneuvers(self, harness):
        await space_maneuvers_admin.s15_defensive_maneuvers(harness)

    async def test_s21_hail_command_runs(self, harness):
        await space_maneuvers_admin.s21_hail_command_runs(harness)

    async def test_s22_comms_command_runs(self, harness):
        await space_maneuvers_admin.s22_comms_command_runs(harness)

    async def test_s23_npc_traffic_visible_on_scan(self, harness):
        await space_maneuvers_admin.s23_npc_traffic_visible_on_scan(harness)

    async def test_s28_shipname_displays(self, harness):
        await space_maneuvers_admin.s28_shipname_displays(harness)
