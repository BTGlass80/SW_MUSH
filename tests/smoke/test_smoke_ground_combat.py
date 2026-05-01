# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_ground_combat.py — Pytest entry points for G1-G3.

G4-G8 are deferred to SH4 because they need richer state setup
(stun cap recovery, dodge declarations, cover modifiers, death+
respawn flow) that benefits from the same harness extensions space
combat needs (advance_ticks, etc.).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import ground_combat


pytestmark = pytest.mark.smoke


class TestGroundCombat:
    """Ground combat baseline — attack, HUD events, wound display."""

    async def test_g1_attack_starts_combat(self, harness):
        await ground_combat.g1_attack_starts_combat(harness)

    async def test_g2_combat_state_payload_emitted(self, harness):
        await ground_combat.g2_combat_state_payload_emitted(harness)

    async def test_g3_take_damage_wound_progression(self, harness):
        await ground_combat.g3_take_damage_wound_progression(harness)
