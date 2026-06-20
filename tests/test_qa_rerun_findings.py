# -*- coding: utf-8 -*-
"""tests/test_qa_rerun_findings.py — fixes from the 2026-06-20 post-fix QA
regression re-run.

The adversarial re-run found two REAL adjacent corruption bugs (and confirmed no
regressions in the fixed B6/H9/H10/B5/chain-rep paths):
  1. FP-not-persisted — combat saved wound_level + character_points but NOT
     force_points, so a FORCE POINT spent in combat was refunded on reconnect
     (FP-dup), the exact parallel of the CP M-fix.
  2. Vendor credit-integrity — the vendor deduction sites lacked
     allow_negative=False, so a stale session-cache pre-check could drive credits
     negative (demonstrated -20cr on a buy-order escrow), the parallel of B6.
Plus two smoke-harness blind-spots (achievements + area-geometry registry never
loaded in-process) that let those paths silently false-pass.
"""
from __future__ import annotations

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel: str) -> str:
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_fp_persisted_after_combat():
    s = _src("parser/combat_commands.py")
    assert "force_points=c.char.force_points" in s, (
        "FP-persist: combat post-round save must persist force_points (FP-dup fix)"
    )


def test_vendor_deductions_guard_negative():
    s = _src("engine/vendor_droids.py")
    # All four credit-deduction sites (deploy / purchase / buy-order escrow /
    # relist fee) must pass allow_negative=False so a stale cache can't go negative.
    assert s.count("allow_negative=False") >= 4, (
        "vendor credit-deduction sites must guard against negative balances"
    )
    # The demonstrated -20cr site specifically:
    assert 'adjust_credits(char["id"], -escrow_needed, "vendor_buy_order_escrow")' not in s, (
        "the buy-order escrow deduction must no longer be an unguarded call"
    )


def test_smoke_harness_loads_achievements_and_area_registry():
    s = _src("tests/harness.py")
    assert "load_achievements()" in s, "harness must load achievements (was false-passing)"
    assert "AreaGeometryRegistry.load_era" in s, "harness must attach the area registry"
    assert "_area_registry" in s
