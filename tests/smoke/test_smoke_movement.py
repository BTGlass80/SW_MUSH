# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_movement.py — Pytest entry points for M1-M6.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import movement


pytestmark = pytest.mark.smoke


class TestMovement:
    """Movement and exploration scenarios — Mos Eisley spawn area."""

    async def test_m1_walk_spawn_exit(self, harness):
        await movement.m1_walk_spawn_exit(harness)

    async def test_m2_path_through_three_rooms(self, harness):
        await movement.m2_path_through_three_rooms(harness)

    async def test_m3_invalid_exit_rejected(self, harness):
        await movement.m3_invalid_exit_rejected(harness)

    async def test_m4_look_after_move(self, harness):
        await movement.m4_look_after_move(harness)

    async def test_m5_inventory_command(self, harness):
        await movement.m5_inventory_command(harness)

    async def test_m6_who_lists_other_player(self, harness):
        await movement.m6_who_lists_other_player(harness)
