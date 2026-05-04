# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_pvp.py — Pytest entry points for the PvP
positive-path scenarios (PV1–PV3). Drop 5.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import pvp


pytestmark = pytest.mark.smoke


class TestPvP:
    """Challenge → accept → attack — PvP consent flow."""

    async def test_pv1_challenge_records_pending_consent(self, harness):
        await pvp.pv1_challenge_records_pending_consent(harness)

    async def test_pv2_accept_activates_consent(self, harness):
        await pvp.pv2_accept_activates_consent(harness)

    async def test_pv3_post_consent_attack_starts_combat(self, harness):
        await pvp.pv3_post_consent_attack_starts_combat(harness)
