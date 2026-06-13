# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_underworld_loop.py — Pytest entry points for
the Coruscant Underworld reachability and exploration-verb scenarios
(UW1, UW2).

UW1 proves the coruscant_underworld wilderness region is reachable via
synthetic drop (the natural "deeper" direction entry is not wired through
the parser's direction dispatch — see scenario module docstring). UW2
exercises the three exploration verbs (look, anomalies, loot) inside the
region and asserts no crash.

This is the P3 underworld smoke gap-matrix item — the new-system-no-driver
smoke for the Drop 18 coruscant_underworld wilderness region build-out.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import underworld_loop


pytestmark = pytest.mark.smoke


class TestUnderworldLoop:
    """Coruscant Underworld: reachability and exploration-verb no-crash."""

    async def test_uw1_synthetic_entry(self, harness):
        await underworld_loop.uw1_synthetic_entry(harness)

    async def test_uw2_exploration_verbs(self, harness):
        await underworld_loop.uw2_exploration_verbs(harness)
