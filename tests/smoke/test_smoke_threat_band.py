# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_threat_band.py — DIFF.2 runtime UI smoke.

See tests/smoke/scenarios/threat_band.py.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import threat_band


pytestmark = pytest.mark.smoke


class TestThreatBandUI:
    """Threat band surfaces in look + the +threat command."""

    async def test_tb_1_look_header_shows_frontier(self, harness):
        await threat_band.tb_1_look_header_shows_frontier(harness)

    async def test_tb_2_look_header_suppresses_settled(self, harness):
        await threat_band.tb_2_look_header_suppresses_settled(harness)

    async def test_tb_3_threat_command_renders_band(self, harness):
        await threat_band.tb_3_threat_command_renders_band(harness)
