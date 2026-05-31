# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_pc_bounty.py — Pytest entry points for
PG.2.bounty session 1 scenarios (BTY-1 … BTY-4).

End-to-end verification of the PC bounty player surface:

  - BTY-1: post happy path + mail delivery
  - BTY-2: stack onto existing bounty
  - BTY-3: cancel + proportional refunds to all contributors
  - BTY-4: cooldown blocks repost

Unit-level coverage in tests/test_pg2_pc_bounty_session1.py
(39 tests).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import pc_bounty


pytestmark = pytest.mark.smoke


class TestPcBounty:
    """PG.2 PC bounty — end-to-end live-harness scenarios."""

    async def test_bty_1_post_happy_path(self, harness):
        await pc_bounty.bty_1_post_happy_path(harness)

    async def test_bty_2_stack_merges_escrow(self, harness):
        await pc_bounty.bty_2_stack_merges_escrow(harness)

    async def test_bty_3_cancel_proportional_refunds(self, harness):
        await pc_bounty.bty_3_cancel_proportional_refunds(harness)

    async def test_bty_4_cancel_sets_cooldown(self, harness):
        await pc_bounty.bty_4_cancel_sets_cooldown(harness)
