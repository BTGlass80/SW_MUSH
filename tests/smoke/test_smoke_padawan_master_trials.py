# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_padawan_master_trials.py — Pytest entry
points for P-M.3 Trials + Knight promotion scenarios (PM3-1 …
PM3-4).

End-to-end verification of P-M.3 (May 20 2026):

  - PM3-1: full promotion happy path
  - PM3-2: +knight hard gate refusal
  - PM3-3: @knight staff override
  - PM3-4: endorsement flag round-trip

Unit-level coverage in tests/test_pm3_trials_and_knight.py
(33 tests).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import padawan_master_trials


pytestmark = pytest.mark.smoke


class TestPadawanMasterTrials:
    """P-M.3 Trials + Knight — end-to-end live-harness scenarios."""

    async def test_pm3_1_full_promotion_happy_path(self, harness):
        await padawan_master_trials.pm3_1_full_promotion_happy_path(harness)

    async def test_pm3_2_knight_hard_gate(self, harness):
        await padawan_master_trials.pm3_2_knight_hard_gate(harness)

    async def test_pm3_3_admin_knight_override(self, harness):
        await padawan_master_trials.pm3_3_admin_knight_override(harness)

    async def test_pm3_4_endorsement_consumed_on_trial_record(self, harness):
        await padawan_master_trials.pm3_4_endorsement_consumed_on_trial_record(harness)
