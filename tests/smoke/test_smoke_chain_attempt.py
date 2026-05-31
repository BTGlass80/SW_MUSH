# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_chain_attempt.py — Pytest entry points for
the `chain attempt` end-to-end scenarios (CA-1 … CA-4).

End-to-end verification of F.8.c.2.b₆ (May 20 2026): the explicit
`chain attempt` command, plus the post-chargen prerequisite
chain-event dispatch.

Unit-level coverage of the matcher / dispatcher / failure paths
lives in tests/test_f8c2b6_chain_attempt_command.py (17 tests).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import chain_attempt


pytestmark = pytest.mark.smoke


class TestChainAttempt:
    """`chain attempt` — end-to-end live-harness scenarios."""

    async def test_ca_1_status_no_active_chain(self, harness):
        await chain_attempt.ca_1_status_no_active_chain(harness)

    async def test_ca_2_attempt_no_active_chain(self, harness):
        await chain_attempt.ca_2_attempt_no_active_chain(harness)

    async def test_ca_3_attempt_rolls_on_skill_step(self, harness):
        await chain_attempt.ca_3_attempt_rolls_on_skill_step(harness)

    async def test_ca_4_attempt_on_non_skill_step_rejected(self, harness):
        await chain_attempt.ca_4_attempt_on_non_skill_step_rejected(harness)
