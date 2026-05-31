# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_padawan_master.py — Pytest entry points for
the Padawan-Master bond scenarios (PM-1 … PM-3).

End-to-end verification of P-M.2 (May 20 2026):

  - PM-1: bond establishment via the player flow
          (+bond <padawan>  /  +bond accept <master>)
  - PM-2: look-output [Padawan] / [Master] markers
          for bonded PCs in the room contents block
  - PM-3: +release dissolves the bond AND writes
          'bond_dissolved' entries to pc_action_log on BOTH sides
          (the §8.12 #2 design-call shared-memory cross-write seam)

Unit-level coverage of the schema migration, command surface,
master-cap enforcement, and marker source-string presence lives
in tests/test_pm2_commands.py (34 tests).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import padawan_master


pytestmark = pytest.mark.smoke


class TestPadawanMaster:
    """Padawan-Master bond — end-to-end live-harness scenarios."""

    async def test_pm_1_bond_happy_path(self, harness):
        await padawan_master.pm_1_bond_happy_path(harness)

    async def test_pm_2_look_shows_bond_markers(self, harness):
        await padawan_master.pm_2_look_shows_bond_markers(harness)

    async def test_pm_3_release_dissolves_and_logs(self, harness):
        await padawan_master.pm_3_release_dissolves_and_logs(harness)
