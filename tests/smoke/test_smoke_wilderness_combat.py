# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_wilderness_combat.py — Pytest entry point for
the wilderness combat smoke scenarios (W-CMB-1, W-CMB-2, W-CMB-3).

This is the Tier 2 follow-up called out in W.2.4's handoff doc
(HANDOFF_MAY17_W24_COMBAT_WILDERNESS.md L373-376). W-CMB-1 verifies
the wilderness gate is lifted at the live-harness level. W-CMB-2
verifies that combat broadcasts at one tile do NOT leak to PCs at
a different tile of the same sentinel room. W-CMB-3 verifies that
the tuple-keyed ``_active_combats`` dict creates separate
CombatInstance objects per tile, not one shared one.

All three were originally drafted as part of the W-CMB-1 drop but
W-CMB-2 and W-CMB-3 deferred for two reasons: (a) the
``security_level`` YAML field was inert at runtime [closed by
S-RES + S-RES.2 on May 18 2026]; (b) the original W-CMB-1 scenario
hardcoded ``DUNE_SEA_SENTINEL_ROOM = 53`` as a DB id, but YAML id
53 doesn't map to DB id 53 because the schema's seed-data SQL
pre-inserts three legacy Mos Eisley rooms at DB ids 1-3, offsetting
all YAML ids [closed by the harness ``room_id_by_slug()`` helper
in this drop]. Both bugs surfaced via PVF-5's tight assertion
catching the off-by-N misresolution.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import wilderness_combat


pytestmark = pytest.mark.smoke


class TestWildernessCombat:
    """Combat in wilderness: gate-lift, tile-isolated broadcasts,
    tuple-keyed combat instances (W-CMB-1, W-CMB-2, W-CMB-3)."""

    async def test_w_cmb_1_attack_in_wilderness_not_refused(self, harness):
        await wilderness_combat.w_cmb_1_attack_in_wilderness_not_refused(
            harness)

    async def test_w_cmb_2_tile_isolated_broadcasts(self, harness):
        await wilderness_combat.w_cmb_2_tile_isolated_broadcasts(harness)

    async def test_w_cmb_3_separate_combat_instances_per_tile(self, harness):
        await wilderness_combat.w_cmb_3_separate_combat_instances_per_tile(
            harness)
