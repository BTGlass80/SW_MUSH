# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_era_clone_wars.py — Era validation classes.

Originally CW-only. Since the May 2026 era pivot (default flipped
to clone_wars), this file now hosts BOTH era classes:

  TestCloneWarsEra — explicit CW pin (redundant with the default,
                     kept for documentation + future-proofing if the
                     default ever changes again)
  TestGCWEra       — the legacy era as a regression check that GCW
                     content still loads cleanly

Both classes run the SAME diagnostic scenarios (login + look,
movement, ground combat, sheet, say) — they're era-portable. Each
scenario takes an ``expected_era`` argument so its assertion adapts
to whichever class is calling it.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import era_clone_wars


pytestmark = pytest.mark.smoke


class TestCloneWarsEra:
    """Clone Wars era — runs the diagnostic scenarios under CW.

    Now redundant with the default-era harness, but kept as an
    explicit pin so the era contract is documented and the class
    survives if/when the default flips again."""

    smoke_era = "clone_wars"

    async def test_cw1_login_in_clone_wars_era(self, harness):
        await era_clone_wars.cw1_login_in_clone_wars_era(harness, "clone_wars")

    async def test_cw2_movement_works(self, harness):
        await era_clone_wars.cw2_movement_works(harness, "clone_wars")

    async def test_cw3_combat_finds_hostile(self, harness):
        await era_clone_wars.cw3_combat_finds_hostile(harness, "clone_wars")

    async def test_cw4_sheet_renders_in_cw(self, harness):
        await era_clone_wars.cw4_sheet_renders_in_cw(harness, "clone_wars")

    async def test_cw5_say_broadcasts_in_cw(self, harness):
        await era_clone_wars.cw5_say_broadcasts_in_cw(harness, "clone_wars")


class TestGCWEra:
    """GCW era — regression check that the legacy era still works.

    Same scenarios as TestCloneWarsEra but pinned to GCW. Catches
    the bug class where the CW pivot accidentally breaks GCW content
    loading (e.g. an era-aware path that defaults to "clone_wars"
    and silently produces an empty GCW world)."""

    smoke_era = "gcw"

    async def test_gcw1_login_in_gcw_era(self, harness):
        await era_clone_wars.cw1_login_in_clone_wars_era(harness, "gcw")

    async def test_gcw2_movement_works(self, harness):
        await era_clone_wars.cw2_movement_works(harness, "gcw")

    async def test_gcw3_combat_finds_hostile(self, harness):
        await era_clone_wars.cw3_combat_finds_hostile(harness, "gcw")

    async def test_gcw4_sheet_renders_in_gcw(self, harness):
        await era_clone_wars.cw4_sheet_renders_in_cw(harness, "gcw")

    async def test_gcw5_say_broadcasts_in_gcw(self, harness):
        await era_clone_wars.cw5_say_broadcasts_in_cw(harness, "gcw")
