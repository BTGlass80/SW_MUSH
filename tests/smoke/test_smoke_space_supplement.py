# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_space_supplement.py — Pytest entry points for
the SH4 supplement scenarios.

Fills gaps in the original SH4 drop:
  - S9 / S9b: hyperspace (list-mode + docked-state gate)
  - S14 / S14b: combat fire gating (docked / no-target)
  - S18: damcon status read
  - S19: ship repair
  - S25: tractor resist gating
  - S30 / S30b: transponder

Class-scoped harness; GCW only (CW has 0 seeded ships).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import (
    space_hyperspace_repair,
    space_combat_gating,
)


pytestmark = pytest.mark.smoke


class TestSpaceHyperspaceAndRepair:
    """SH4 supplement — hyperspace + damcon + ship repair."""

    async def test_s9_hyperspace_list_destinations(self, harness):
        await space_hyperspace_repair.s9_hyperspace_list_destinations(harness)

    async def test_s9b_hyperspace_blocked_when_docked(self, harness):
        await space_hyperspace_repair.s9b_hyperspace_blocked_when_docked(harness)

    async def test_s18_damcon_status(self, harness):
        await space_hyperspace_repair.s18_damcon_status(harness)

    async def test_s19_ship_repair_at_dock(self, harness):
        await space_hyperspace_repair.s19_ship_repair_at_dock(harness)


class TestSpaceCombatGating:
    """SH4 supplement — combat-fire gating, transponder, tractor.

    Note: Full ship-on-ship combat (S12 lockon+fire) is xfailed in
    the original SH4 due to a confirmed crew.gunners vs.
    crew.gunner_stations bug. These supplement scenarios exercise
    the surrounding gates so a regression in the docked-state
    check or usage hint is caught even while the main fire path
    is broken.
    """

    async def test_s14_fire_while_docked_blocked(self, harness):
        await space_combat_gating.s14_fire_while_docked_blocked(harness)

    async def test_s14b_fire_no_target_produces_usage(self, harness):
        await space_combat_gating.s14b_fire_no_target_produces_usage(harness)

    async def test_s30_transponder_status(self, harness):
        await space_combat_gating.s30_transponder_status(harness)

    async def test_s30b_transponder_set_false(self, harness):
        await space_combat_gating.s30b_transponder_set_false(harness)

    async def test_s25_resist_tractor_runs(self, harness):
        await space_combat_gating.s25_resist_tractor_runs(harness)
