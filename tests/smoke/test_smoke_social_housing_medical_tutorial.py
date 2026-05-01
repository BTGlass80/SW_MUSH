# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_social_housing_medical_tutorial.py — Pytest
entry points for SH6 scenarios (H1-H9).

Covers housing, sabacc, perform (entertainer), medical, and the
tutorial system. Class-scoped harness; GCW only.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import social_housing_medical_tutorial as sh6


pytestmark = pytest.mark.smoke


class TestHousing:
    """Housing subcommands — exercises the post-fix path (the
    HousingCommand.execute scoping bug previously broke every
    housing subcommand with NameError)."""

    async def test_h1_housing_status_renders(self, harness):
        await sh6.h1_housing_status_renders(harness)

    async def test_h2_housing_storage_runs(self, harness):
        await sh6.h2_housing_storage_runs(harness)

    async def test_h3_sethome_unauthorized(self, harness):
        await sh6.h3_sethome_unauthorized(harness)


class TestCantinaActivities:
    """Sabacc + entertainer perform — both gated to cantina rooms."""

    async def test_h4_sabacc_in_cantina(self, harness):
        await sh6.h4_sabacc_in_cantina(harness)

    async def test_h5_perform_in_cantina(self, harness):
        await sh6.h5_perform_in_cantina(harness)


class TestMedical:
    """Medical commands — heal economy + heal usage."""

    async def test_h6_healrate_displays(self, harness):
        await sh6.h6_healrate_displays(harness)

    async def test_h7_heal_usage_with_no_args(self, harness):
        await sh6.h7_heal_usage_with_no_args(harness)


class TestTutorial:
    """Tutorial system — exercises the post-bugfix2 path. Before
    the bugfix landed, build_tutorial wrote to the wrong DB and
    these scenarios couldn't even find the Training Grounds room."""

    async def test_h8_training_list_runs(self, harness):
        await sh6.h8_training_list_runs(harness)

    async def test_h9_training_room_at_hub(self, harness):
        await sh6.h9_training_room_at_hub(harness)
