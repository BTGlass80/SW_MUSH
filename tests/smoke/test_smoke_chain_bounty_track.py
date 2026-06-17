# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_chain_bounty_track.py — tutorial bounty target
binding smoke (drop 26, 2026-06-13).

See tests/smoke/scenarios/chain_bounty_track.py.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import chain_bounty_track


pytestmark = pytest.mark.smoke


class TestChainBountyTrack:
    """Tutorial bounty contract binds its target so +bounty/track works."""

    async def test_cbt_1_bountytrack_works_on_tutorial_contract(self, harness):
        await chain_bounty_track.cbt_1_bountytrack_works_on_tutorial_contract(
            harness)
