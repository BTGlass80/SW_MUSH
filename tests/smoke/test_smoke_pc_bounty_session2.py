# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_pc_bounty_session2.py — Pytest entry
points for PG.2.bounty session 2 scenarios (BTY-5 … BTY-7).

End-to-end verification of the BH workflow + insurance hook +
expiry tick:

  - BTY-5: BH claims + releases; non-BH rejected
  - BTY-6: full insurance loop on BH kill (insurance hit +
           payout + fulfillment)
  - BTY-7: expiry tick refunds stake + reverts stale claims

Unit-level coverage in tests/test_pg2_pc_bounty_session2.py
(39 tests).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import pc_bounty_session2


pytestmark = pytest.mark.smoke


class TestPcBountySession2:
    """PG.2 PC bounty session 2 — end-to-end live-harness."""

    async def test_bty_5_bh_claim_and_release(self, harness):
        await pc_bounty_session2.bty_5_bh_claim_and_release(harness)

    async def test_bty_6_full_insurance_loop(self, harness):
        await pc_bounty_session2.bty_6_full_insurance_loop(harness)

    async def test_bty_7_expiry_tick(self, harness):
        await pc_bounty_session2.bty_7_expiry_tick(harness)
