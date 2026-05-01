# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_space_sh7.py — SH7 entry points.

Closes the seven remaining space gaps from design §6.5 using the
new advance_ticks(n) and setup_two_ship_combat() harness helpers.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import space_sh7


pytestmark = pytest.mark.smoke


class TestSpaceSH7:
    """Closes the SH4 long-tail gaps."""

    async def test_s8_sublight_transit_progresses_with_ticks(self, harness):
        await space_sh7.s8_sublight_transit_progresses_with_ticks(harness)

    async def test_s16_evade_with_two_ships_in_zone(self, harness):
        await space_sh7.s16_evade_with_two_ships_in_zone(harness)

    async def test_s17_close_range_close_command(self, harness):
        await space_sh7.s17_close_range_close_command(harness)

    async def test_s20_ship_ownership_transfer(self, harness):
        await space_sh7.s20_ship_ownership_transfer(harness)

    async def test_s24_tractor_beam_command_runs(self, harness):
        await space_sh7.s24_tractor_beam_command_runs(harness)

    async def test_s26_salvage_command_runs(self, harness):
        await space_sh7.s26_salvage_command_runs(harness)

    async def test_s27_market_list_runs(self, harness):
        await space_sh7.s27_market_list_runs(harness)

    async def test_s29_setbounty_runs(self, harness):
        await space_sh7.s29_setbounty_runs(harness)
