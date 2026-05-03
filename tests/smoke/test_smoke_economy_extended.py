# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_economy_extended.py — Pytest entry points for the
extended economy smoke scenarios (EE1–EE9). Drop 2 Block B.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import economy_extended


pytestmark = pytest.mark.smoke


class TestEconomyExtended:
    """Vendor droids, buy/sell flows, P2P trade cap, cargo wiring."""

    async def test_ee1_shop_buy_droid_insufficient_credits(self, harness):
        await economy_extended.ee1_shop_buy_droid_insufficient_credits(harness)

    async def test_ee2_shop_buy_droid_success(self, harness):
        await economy_extended.ee2_shop_buy_droid_success(harness)

    async def test_ee3_shop_place_recall_lifecycle(self, harness):
        await economy_extended.ee3_shop_place_recall_lifecycle(harness)

    async def test_ee4_browse_empty_room(self, harness):
        await economy_extended.ee4_browse_empty_room(harness)

    async def test_ee5_browse_with_droid(self, harness):
        await economy_extended.ee5_browse_with_droid(harness)

    async def test_ee6_buy_from_droid(self, harness):
        await economy_extended.ee6_buy_from_droid(harness)

    async def test_ee7_sell_resource_to_droid_routes(self, harness):
        await economy_extended.ee7_sell_resource_to_droid_routes(harness)

    async def test_ee8_p2p_cap_blocks_over_limit(self, harness):
        await economy_extended.ee8_p2p_cap_blocks_over_limit(harness)

    async def test_ee9_buy_cargo_no_ship_refuses_cleanly(self, harness):
        await economy_extended.ee9_buy_cargo_no_ship_refuses_cleanly(harness)
