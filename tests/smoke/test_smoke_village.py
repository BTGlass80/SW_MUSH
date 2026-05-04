# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_village.py — Pytest entry points for the
Village-quest end-to-end smoke scenarios (VL1–VL7).

F.7.l (May 4 2026). Per architecture v40 §3.5 step 4 (Hermit NPC +
Village wiring smoke test). See the `village.py` scenario module
docstring for what each scenario covers.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import village


pytestmark = pytest.mark.smoke


class TestVillage:
    """Village quest end-to-end smoke: gate → invitation → Act 2 →
    trial completion → inter-trial cooldown → path commit → tutorial
    chain unlock."""

    smoke_era = "clone_wars"

    async def test_vl1_hermit_silent_below_threshold(self, harness):
        await village.vl1_hermit_silent_below_threshold(harness)

    async def test_vl2_hermit_invitation_fires_at_threshold(self, harness):
        await village.vl2_hermit_invitation_fires_at_threshold(harness)

    async def test_vl3_act_2_strict_cooldown_blocks(self, harness):
        await village.vl3_act_2_strict_cooldown_blocks(harness)

    async def test_vl4_act_2_bypass_opens_immediately(self, harness):
        await village.vl4_act_2_bypass_opens_immediately(harness)

    async def test_vl5_trial_completion_stamps_last_attempt(self, harness):
        await village.vl5_trial_completion_stamps_last_attempt(harness)

    async def test_vl6_inter_trial_gate_blocks_strict(self, harness):
        await village.vl6_inter_trial_gate_blocks_strict(harness)

    async def test_vl7_path_commits_unlock_correct_chain(self, harness):
        await village.vl7_path_commits_unlock_correct_chain(harness)
