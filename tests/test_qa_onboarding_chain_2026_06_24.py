# -*- coding: utf-8 -*-
"""
tests/test_qa_onboarding_chain_2026_06_24.py — BLOCKER fix from the normal-play QA
campaign: the standalone first-character chargen path never seeded the tutorial
chain the wizard collected at step6.

A brand-new player who creates their FIRST character through the public /chargen
wizard and picks a tutorial chain was dropped into the game with NO chain active
(blank TRAINING panel, empty #g-objective, `chain status` = "no active chain").
The whole guided-onboarding scaffolding is built and works -- but only for the
EMBEDDED path (handle_create_character, used by alts of an established account).
The first-timer -- who needs onboarding most -- got none.

Fix: mirror the embedded path into handle_submit (server/api.py) -- read chain_id,
resolve + lock-check the chain, place the character at the chain's starting_room,
and seed the tutorial_chain block into attributes -- and make the standalone
wizard actually SEND chain_id (static/chargen.html submitCharacter).
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
API = (REPO / "server" / "api.py").read_text(encoding="utf-8")
CHARGEN = (REPO / "static" / "chargen.html").read_text(encoding="utf-8")


def _handle_submit_body() -> str:
    i = API.index("async def handle_submit")
    j = API.index("async def handle_create_character")  # the next method
    assert i < j
    return API[i:j]


class TestStandaloneSubmitSeedsChain:
    def test_reads_chain_id_from_body(self):
        body = _handle_submit_body()
        assert 'chain_id = data.get("chain_id")' in body, \
            "handle_submit must read the wizard's chain_id"

    def test_resolves_and_lock_checks_the_chain(self):
        body = _handle_submit_body()
        assert "load_tutorial_chains" in body
        assert "is_chain_locked_for_character" in body
        assert "corpus.by_id().get(chain_id)" in body

    def test_places_at_chain_starting_room_with_landing_pad_fallback(self):
        body = _handle_submit_body()
        assert "selected_chain.starting_room" in body, \
            "must place at the chain's starting room"
        assert "placed_via_chain" in body
        # the legacy Landing Pad placement survives as the fallback
        assert "Landing Pad" in body and "tutorial_zone" in body

    def test_seeds_tutorial_chain_block_into_attributes(self):
        body = _handle_submit_body()
        # the keystone: the active tutorial_chain block the client TRAINING panel reads
        assert '"tutorial_chain"' in body
        assert '"completion_state": "active"' in body
        assert "selected_chain.chain_id" in body
        assert "selected_chain.faction_alignment" in body

    def test_never_blocks_account_creation_on_a_chain_miss(self):
        # a bad/locked/unknown chain must fall back, not 4xx the whole submit
        body = _handle_submit_body()
        assert "no chain seeded" in body  # the graceful-fallback log marker


class TestWizardSendsChainId:
    def test_submit_character_sends_chain_id(self):
        i = CHARGEN.index("async function submitCharacter")
        j = CHARGEN.index("/api/chargen/submit", i)
        block = CHARGEN[i:j + 200]
        assert "payload.chain_id = S.tutorialChainId" in block, \
            "submitCharacter must send the selected chain_id"


if __name__ == "__main__":
    import sys, pytest
    sys.exit(pytest.main([__file__, "-v"]))
