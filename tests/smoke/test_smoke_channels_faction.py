# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_channels_faction.py — Pytest entry points for
the communication channels + faction reputation scenarios
(FC1–FC3, CN1–CN2). Drop 3 Block F.

(ML1–ML3 mail scenarios deferred — mail tables don't exist in the
current schema; see Drop 3 handoff.)
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import channels_faction


pytestmark = pytest.mark.smoke


class TestChannelsFaction:
    """+faction, +reputation, +channels, tune/+freqs round-trip."""

    async def test_fc1_faction_shows_current_affiliation(self, harness):
        await channels_faction.fc1_faction_shows_current_affiliation(harness)

    async def test_fc2_reputation_overview_lists_factions(self, harness):
        await channels_faction.fc2_reputation_overview_lists_factions(harness)

    async def test_fc3_reputation_detail_shows_ranks(self, harness):
        await channels_faction.fc3_reputation_detail_shows_ranks(harness)

    async def test_cn1_channels_lists_communication_surfaces(self, harness):
        await channels_faction.cn1_channels_lists_communication_surfaces(harness)

    async def test_cn2_tune_and_freqs_roundtrip(self, harness):
        await channels_faction.cn2_tune_and_freqs_roundtrip(harness)
