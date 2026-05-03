# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_combat_extended.py — Pytest entry points for
the extended combat scenarios (CX1–CX4). Drop 2 Block C.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import combat_extended


pytestmark = pytest.mark.smoke


class TestCombatExtended:
    """Security gate, PvP consent, fulldodge, +combat status."""

    async def test_cx1_attack_refused_in_secured_zone(self, harness):
        await combat_extended.cx1_attack_refused_in_secured_zone(harness)

    async def test_cx2_pvp_attack_refused_without_consent(self, harness):
        await combat_extended.cx2_pvp_attack_refused_without_consent(harness)

    async def test_cx3_fulldodge_in_active_combat(self, harness):
        await combat_extended.cx3_fulldodge_in_active_combat(harness)

    async def test_cx4_combat_status_renders_in_active_combat(self, harness):
        await combat_extended.cx4_combat_status_renders_in_active_combat(harness)
