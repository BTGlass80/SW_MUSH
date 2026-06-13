# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_commissary_loop.py — Pytest entry points for
commissary faction-gear loop smoke scenarios (CL1-CL3).

Drop 13 tracking_fob seam / commissary loop:
  CL1 — BHG member at rank 1 sees tracking_fob on +commissary listing.
  CL2 — +commissary buy tracking_fob debits 350 cr (commissary_purchase
         sink) and inventory blob carries the item with skill_bonus dict.
  CL3 — jedi_order (no commissary) gets austere refusal on both listing
         and buy; no credits debited.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import commissary_loop


pytestmark = pytest.mark.smoke


class TestCommissaryLoop:
    """Commissary faction-gear loop: listing + purchase + negative gate."""

    async def test_cl1_bhg_member_sees_tracking_fob(self, harness):
        await commissary_loop.cl1_bhg_member_sees_tracking_fob(harness)

    async def test_cl2_buy_tracking_fob_debits_and_grants(self, harness):
        await commissary_loop.cl2_buy_tracking_fob_debits_and_grants(harness)

    async def test_cl3_no_commissary_faction_refused(self, harness):
        await commissary_loop.cl3_no_commissary_faction_refused(harness)
