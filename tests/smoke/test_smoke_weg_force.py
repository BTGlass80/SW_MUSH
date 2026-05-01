# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_weg_force.py — Pytest entry points for W1-W4.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import weg_force


pytestmark = pytest.mark.smoke


class TestWEGForce:
    """WEG D6 dice + Force surface."""

    async def test_w1_roll_dice_expression(self, harness):
        await weg_force.w1_roll_dice_expression(harness)

    async def test_w2_opposed_check(self, harness):
        await weg_force.w2_opposed_check(harness)

    async def test_w3_powers_list(self, harness):
        await weg_force.w3_powers_list(harness)

    async def test_w4_force_status(self, harness):
        await weg_force.w4_force_status(harness)
