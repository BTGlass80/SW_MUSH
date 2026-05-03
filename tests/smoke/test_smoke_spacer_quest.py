# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_spacer_quest.py — Pytest entry points for the
From Dust to Stars (FDtS) smoke scenarios (SQ1–SQ6). Drop 1 Block A.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import spacer_quest


pytestmark = pytest.mark.smoke


class TestSpacerQuest:
    """FDtS new-player on-ramp: spacerquest, debt, travel."""

    async def test_sq1_quest_no_state(self, harness):
        await spacer_quest.sq1_quest_no_state(harness)

    async def test_sq2_quest_after_seed(self, harness):
        await spacer_quest.sq2_quest_after_seed(harness)

    async def test_sq3_quest_log(self, harness):
        await spacer_quest.sq3_quest_log(harness)

    async def test_sq4_debt_status_clean(self, harness):
        await spacer_quest.sq4_debt_status_clean(harness)

    async def test_sq5_debt_status_with_balance(self, harness):
        await spacer_quest.sq5_debt_status_with_balance(harness)

    async def test_sq6_travel_refuses_outside_dock(self, harness):
        await spacer_quest.sq6_travel_refuses_outside_dock(harness)
