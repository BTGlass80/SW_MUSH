# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_pvp_flag.py — Pytest entry points for the +pvp
opt-in flag scenarios (PVF-1 … PVF-10).

End-to-end verification of the v27 +pvp flag. Unit-level coverage of
the migration, gate logic, command registration, and help text lives
in tests/test_pvp_flag_unit.py. Byte-level coverage of the display
surfaces lives in tests/test_pvp_display_surfaces.py.

PVF-6 … PVF-9 added by the May 19 smoke harness expansion drop —
LAWLESS happy-path (flagged + unflagged), cooldown expiry (negative
of PVF-4), and mutual-flag end-to-end with both-sides cooldown
lock.

PVF-10 added by the May 19 smoke harness expansion (continued) —
live-`look` integration of the [PvP] marker that the byte-level
display-surface unit test asserts exists in the source.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import pvp_flag


pytestmark = pytest.mark.smoke


class TestPvpFlag:
    """+pvp opt-in flag — end-to-end live-harness scenarios."""

    async def test_pvf_1_flag_on_persists_and_broadcasts(self, harness):
        await pvp_flag.pvf_1_flag_on_persists_and_broadcasts(harness)

    async def test_pvf_2_flagged_attacker_bypasses_consent(self, harness):
        await pvp_flag.pvf_2_flagged_attacker_bypasses_consent(harness)

    async def test_pvf_3_flagged_target_unlocks_attacker(self, harness):
        await pvp_flag.pvf_3_flagged_target_unlocks_attacker(harness)

    async def test_pvf_4_unflag_cooldown_locks_after_engagement(self, harness):
        await pvp_flag.pvf_4_unflag_cooldown_locks_after_engagement(harness)

    async def test_pvf_5_secured_zone_blocks_flagged_pvp(self, harness):
        await pvp_flag.pvf_5_secured_zone_blocks_flagged_pvp(harness)

    async def test_pvf_6_lawless_flagged_combat_proceeds(self, harness):
        await pvp_flag.pvf_6_lawless_flagged_combat_proceeds(harness)

    async def test_pvf_7_lawless_unflagged_combat_proceeds(self, harness):
        await pvp_flag.pvf_7_lawless_unflagged_combat_proceeds(harness)

    async def test_pvf_8_unflag_succeeds_after_cooldown_clears(self, harness):
        await pvp_flag.pvf_8_unflag_succeeds_after_cooldown_clears(harness)

    async def test_pvf_9_mutual_flag_engagement_locks_both(self, harness):
        await pvp_flag.pvf_9_mutual_flag_engagement_locks_both(harness)

    async def test_pvf_10_look_shows_pvp_marker(self, harness):
        await pvp_flag.pvf_10_look_shows_pvp_marker(harness)
