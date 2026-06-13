# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_buy_vendor_gate.py — Pytest entry points for
open-market buy gate smoke scenarios (BVG1–BVG3).

Drops 10-11: market segmentation (vendor_stocked flag) + vendor-presence
gate (ai_config vendor:true NPC required in room).

Test ordering within the class is intentional:
  test_bvg1 (refusal — no vendor NPC)  →
  test_bvg2 (success — seeds vendor NPC + buys)  →
  test_bvg3 (stock gate — contraband refused with vendor present)

The class-scoped harness shares one DB across all three tests so NPC state
seeded in bvg2 is visible to bvg3.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import buy_vendor_gate


pytestmark = pytest.mark.smoke


class TestBuyVendorGate:
    """Open-market buy gate: vendor-presence + vendor_stocked checks."""

    async def test_bvg1_refusal_no_vendor(self, harness):
        await buy_vendor_gate.bvg1_refusal_no_vendor(harness)

    async def test_bvg2_success_with_vendor(self, harness):
        await buy_vendor_gate.bvg2_success_with_vendor(harness)

    async def test_bvg3_stock_gate_contraband(self, harness):
        await buy_vendor_gate.bvg3_stock_gate_contraband(harness)
