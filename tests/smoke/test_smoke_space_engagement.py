# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_space_engagement.py — Pytest entry points
for SH4 Layer C: sensors & engagement (S11-S13).

S12 was previously xfailed with a confirmed bug in LockOnCommand
(read site used legacy ``crew.gunners`` after ``_get_crew()`` migrated
it to ``crew.gunner_stations``). Fix landed — see the LockFix drop:
``parser/space_commands.py`` now uses ``_seated_gunner_ids(crew)`` at
all four read sites (DisembarkCommand, AssistCommand x2, LockOnCommand).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import space_engagement


pytestmark = pytest.mark.smoke


class TestSpaceEngagement:
    """Layer C — sensors & engagement."""

    async def test_s11_scan_and_deepscan(self, harness):
        await space_engagement.s11_scan_and_deepscan(harness)

    async def test_s12_lockon_requires_correct_gunner_field(self, harness):
        await space_engagement.s12_lockon_requires_correct_gunner_field(harness)

    async def test_s13_shields_in_space(self, harness):
        await space_engagement.s13_shields_in_space(harness)
