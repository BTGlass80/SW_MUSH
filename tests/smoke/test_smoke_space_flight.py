# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_space_flight.py — Pytest entry points for SH4
Layer B: launch & flight (S6-S10).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import space_flight


pytestmark = pytest.mark.smoke


class TestSpaceFlight:
    """Layer B — launch & flight. Builds on Layer A (boarding)."""

    async def test_s6_launch_from_dock(self, harness):
        await space_flight.s6_launch_from_dock(harness)

    async def test_s7_land_at_destination(self, harness):
        await space_flight.s7_land_at_destination(harness)

    async def test_s8_scan_in_space(self, harness):
        await space_flight.s8_scan_in_space(harness)

    async def test_s9_shields_command_runs(self, harness):
        await space_flight.s9_shields_command_runs(harness)

    async def test_s10_power_command_runs(self, harness):
        await space_flight.s10_power_command_runs(harness)
