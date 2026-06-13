# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_chain_walkthrough.py — P0.2 per-chain
walkthrough smoke (drop 25, 2026-06-12).

Parametrized over all 7 unlocked Clone Wars tutorial chains. Each test
walks one chain from its REAL starting room to graduation using ONLY
player-issued commands, asserting the reachability gate at every step.
This is the runtime-truth half of the onboarding coverage net
(TD.ONBOARDING_CHAIN_REACHABILITY_COVERAGE); the static half is
tests/test_chain_corpus_reachability_invariant.py.

See tests/smoke/scenarios/chain_walkthrough.py for the walker and its
HARD RULES (no chain-event hooks, no room writes, no mid-walk state
injection — movement must come from the product).

The 7 unlocked chains (locked jedi_path / jedi_path_independent stubs
are excluded — they're rejected at chargen and never run):
    republic_soldier, republic_intelligence, separatist_commando,
    separatist_agent, bounty_hunter, smuggler, shipwright_trader
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import chain_walkthrough


pytestmark = pytest.mark.smoke


# Each entry: (chain_id, unique_walker_name). Names must be unique
# within the class-scoped harness lifetime.
_UNLOCKED_CHAINS = [
    ("republic_soldier", "WalkRepSoldier"),
    ("republic_intelligence", "WalkRepIntel"),
    ("separatist_commando", "WalkSepCommando"),
    ("separatist_agent", "WalkSepAgent"),
    ("bounty_hunter", "WalkBountyHunter"),
    ("smuggler", "WalkSmuggler"),
    ("shipwright_trader", "WalkShipwright"),
]


class TestChainWalkthrough:
    """Every unlocked chain must walk to graduation by player action."""

    @pytest.mark.parametrize("chain_id,walker_name", _UNLOCKED_CHAINS,
                             ids=[c[0] for c in _UNLOCKED_CHAINS])
    async def test_chain_walks_to_graduation(self, harness,
                                             chain_id, walker_name):
        await chain_walkthrough.walk_chain(harness, chain_id, walker_name)
