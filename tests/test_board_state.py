# -*- coding: utf-8 -*-
"""
test_board_state.py — Webify Drop UI-5: build_board_state producer.

Pure-python tests for engine/bounty_board.build_board_state, the
assembler behind the `board_state` web push:

    { "contracts": [ to_dict() + {"expires_in_secs": int|None} ],
      "claimed_id": str|None }

Covers: shape, server-derived expires_in_secs (clamped, None-safe),
claimed-first ordering + claimed_id, dedup when the claimed contract
also appears in the posted list, no-claim case, and malformed-contract
tolerance (skip, never raise). No DB, no singletons, sandbox-runnable.
"""
from __future__ import annotations

import time

from engine.bounty_board import (
    BountyContract,
    BountyStatus,
    BountyTier,
    build_board_state,
)


def _mk(cid: str, tier=BountyTier.NOVICE, reward=900, status=BountyStatus.POSTED,
        claimed_by=None, expires_at=None, chain_bounty_id="") -> BountyContract:
    return BountyContract(
        id=cid,
        tier=tier,
        target_name=f"Target-{cid}",
        target_species="Human",
        target_archetype="thug",
        crime_description="wanted for testing",
        posting_org="Mos Eisley Port Authority",
        tip="Last seen near the cantina district.",
        reward=reward,
        reward_alive_bonus=reward // 10,
        target_npc_id=1,
        target_room_id=2,
        status=status,
        claimed_by=claimed_by,
        expires_at=expires_at,
        chain_bounty_id=chain_bounty_id,
    )


def test_shape_and_expires_in_secs_derived():
    now = 1_000_000.0
    posted = [_mk("b-aaa", expires_at=now + 3600),
              _mk("b-bbb", expires_at=None)]
    state = build_board_state(posted, None, now=now)

    assert set(state.keys()) == {"contracts", "claimed_id"}
    assert state["claimed_id"] is None
    assert len(state["contracts"]) == 2

    by_id = {c["id"]: c for c in state["contracts"]}
    assert by_id["b-aaa"]["expires_in_secs"] == 3600
    assert by_id["b-bbb"]["expires_in_secs"] is None
    # to_dict() passthrough fields survive
    assert by_id["b-aaa"]["target_name"] == "Target-b-aaa"
    assert by_id["b-aaa"]["tier"] == "novice"
    assert by_id["b-aaa"]["chain_bounty_id"] == ""


def test_expires_in_secs_clamped_to_zero():
    now = 1_000_000.0
    posted = [_mk("b-old", expires_at=now - 500)]
    state = build_board_state(posted, None, now=now)
    assert state["contracts"][0]["expires_in_secs"] == 0


def test_claimed_contract_prepended_and_claimed_id_set():
    now = time.time()
    posted = [_mk("b-aaa", reward=900, expires_at=now + 100)]
    claimed = _mk("b-ccc", tier=BountyTier.VETERAN, reward=2000,
                  status=BountyStatus.CLAIMED, claimed_by="7",
                  expires_at=now + 7200)
    state = build_board_state(posted, claimed, now=now)

    assert state["claimed_id"] == "b-ccc"
    assert [c["id"] for c in state["contracts"]] == ["b-ccc", "b-aaa"]
    assert state["contracts"][0]["status"] == "claimed"
    assert state["contracts"][0]["expires_in_secs"] == 7200


def test_claimed_deduped_when_also_in_posted_list():
    # Defensive: if a caller ever hands the claimed contract inside the
    # posted list too, it must not render twice.
    now = time.time()
    claimed = _mk("b-dup", status=BountyStatus.CLAIMED, claimed_by="7",
                  expires_at=now + 60)
    posted = [claimed, _mk("b-other", expires_at=now + 60)]
    state = build_board_state(posted, claimed, now=now)

    ids = [c["id"] for c in state["contracts"]]
    assert ids == ["b-dup", "b-other"]
    assert state["claimed_id"] == "b-dup"


def test_empty_board_is_fine():
    state = build_board_state([], None)
    assert state == {"contracts": [], "claimed_id": None}
    state2 = build_board_state(None, None)
    assert state2 == {"contracts": [], "claimed_id": None}


def test_malformed_contract_skipped_never_raises():
    class Broken:
        id = "b-broken"

        def to_dict(self):
            raise RuntimeError("boom")

    now = time.time()
    posted = [Broken(), _mk("b-good", expires_at=now + 10)]
    state = build_board_state(posted, None, now=now)
    assert [c["id"] for c in state["contracts"]] == ["b-good"]


def test_chain_tag_passthrough():
    posted = [_mk("b-chain", chain_bounty_id="tutorial_bhg_tarko_vinn")]
    state = build_board_state(posted, None)
    assert state["contracts"][0]["chain_bounty_id"] == "tutorial_bhg_tarko_vinn"
