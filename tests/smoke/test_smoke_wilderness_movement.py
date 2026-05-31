# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_wilderness_movement.py — Pytest entry points
for wilderness natural entry/exit scenarios (W-MV-1, W-MV-2).

Companion to test_smoke_wilderness_combat.py (combat in wilderness)
and test_w_2_3_1_bucket1_closure.py (unit-level coverage of the
movement helpers). These scenarios exercise the full parser →
engine → DB pipeline that wilderness_combat scenarios bypass via
the synthetic ``_drop_into_wilderness`` helper.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import wilderness_movement


pytestmark = pytest.mark.smoke


class TestWildernessMovement:
    """Wilderness natural entry/exit — end-to-end live-harness."""

    async def test_w_mv_1_natural_entry(self, harness):
        await wilderness_movement.w_mv_1_natural_entry(harness)

    async def test_w_mv_2_natural_exit(self, harness):
        await wilderness_movement.w_mv_2_natural_exit(harness)
