# -*- coding: utf-8 -*-
"""
test_onboarding_state.py — Webify Drop UI-7: onboarding_state producer.

Tests engine/chain_events.build_onboarding_state and the ADDITIVE
extension of get_active_step_info, against a stub corpus injected
through the cached-loader seam (engine.chain_events._get_corpus — the
same monkeypatch pattern test_hud_objective.py established).

Covers: the active payload shape + field passthrough (incl.
completed_steps and total_steps), the graduated payload (with
chain-name resolution and the unknown-chain fallback), the
no-chain-ever None, legacy get_active_step_info keys surviving the
extension, list-copy isolation (callers can't mutate the corpus), and
malformed-attrs tolerance. Pure aside from the (stubbed) corpus cache;
sandbox-runnable.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import engine.chain_events as chain_events
from engine.chain_events import build_onboarding_state, get_active_step_info


def _mk_corpus():
    step1 = SimpleNamespace(
        step=1, title="Vetting at the Chapter House",
        objective="Pass the Guild's intake interview.",
        location="nar_shaddaa_bhg_chapter_house",
        npc="Adjudicator Kaeleth Voss", npc_role="instructor",
        npc_intro="Another one. Sit down.",
        teaches=["look", "+sheet"],
        completion={"type": "command_executed", "command": "+sheet"},
        next_hint="The board is on the back wall — pick a contract.",
    )
    step2 = SimpleNamespace(
        step=2, title="Take a Contract",
        objective="Claim a bounty off the board.",
        location="nar_shaddaa_bhg_chapter_house",
        npc="Adjudicator Kaeleth Voss", npc_role="instructor",
        npc_intro="The board is on the back wall.",
        teaches=["+bounties"],
        completion={"type": "bounty_accepted"},
        next_hint="Track your mark down in the warrens.",
    )
    step3 = SimpleNamespace(
        step=3, title="Prove Your Aim",
        objective="Pass the range qualification.",
        location="nar_shaddaa_bhg_range",
        npc="Range Master Dex", npc_role="instructor",
        npc_intro="Blaster on the line.",
        teaches=["attack"],
        completion={"type": "skill_check_passed", "skill": "blaster",
                    "difficulty": 10},
        next_hint="Qualification passed — collect your card.",
    )
    chain = SimpleNamespace(
        chain_id="bounty_hunter", chain_name="Bounty Hunter",
        steps=[step1, step2, step3],
    )
    return SimpleNamespace(by_id=lambda: {"bounty_hunter": chain})


@pytest.fixture
def stub_corpus(monkeypatch):
    corpus = _mk_corpus()
    monkeypatch.setattr(chain_events, "_get_corpus",
                        lambda era=None: corpus)
    return corpus


def _char(state) -> dict:
    return {"id": 7, "attributes": json.dumps({"tutorial_chain": state}
                                              if state else {})}


def test_active_payload_shape_and_passthrough(stub_corpus):
    char = _char({"chain_id": "bounty_hunter", "step": 2,
                  "completed_steps": [1], "completion_state": "active"})
    s = build_onboarding_state(char)

    assert s["active"] is True
    assert s["chain_id"] == "bounty_hunter"
    assert s["chain_name"] == "Bounty Hunter"
    assert s["step"] == 2
    assert s["total_steps"] == 3
    assert s["completed_steps"] == [1]
    assert s["title"] == "Take a Contract"
    assert s["objective"] == "Claim a bounty off the board."
    assert s["npc"] == "Adjudicator Kaeleth Voss"
    assert s["npc_role"] == "instructor"
    assert s["npc_intro"] == "The board is on the back wall."
    assert s["teaches"] == ["+bounties"]
    assert s["completion_type"] == "bounty_accepted"
    # drop 26: next_hint threaded into the active payload.
    assert s["next_hint"] == "Track your mark down in the warrens."


def test_skill_check_step_exposes_completion_type(stub_corpus):
    char = _char({"chain_id": "bounty_hunter", "step": 3,
                  "completed_steps": [1, 2], "completion_state": "active"})
    s = build_onboarding_state(char)
    assert s["completion_type"] == "skill_check_passed"
    assert s["teaches"] == ["attack"]


def test_graduated_payload_resolves_chain_name(stub_corpus):
    char = _char({"chain_id": "bounty_hunter", "step": 4,
                  "completed_steps": [1, 2, 3],
                  "completion_state": "graduated"})
    s = build_onboarding_state(char)
    assert s == {"active": False, "graduated": True,
                 "chain_id": "bounty_hunter",
                 "chain_name": "Bounty Hunter"}


def test_graduated_unknown_chain_falls_back_to_id(stub_corpus):
    char = _char({"chain_id": "retired_chain", "step": 9,
                  "completion_state": "graduated"})
    s = build_onboarding_state(char)
    assert s["graduated"] is True
    assert s["chain_name"] == "retired_chain"


def test_no_chain_ever_returns_none(stub_corpus):
    assert build_onboarding_state(_char(None)) is None


def test_malformed_attrs_tolerated(stub_corpus):
    assert build_onboarding_state({"id": 7, "attributes": "{not json"}) is None
    assert build_onboarding_state({"id": 7}) is None


def test_get_active_step_info_legacy_keys_survive(stub_corpus):
    """chain status / chain attempt read these named keys — the UI-7
    extension must be additive."""
    char = _char({"chain_id": "bounty_hunter", "step": 1,
                  "completed_steps": [], "completion_state": "active"})
    info = get_active_step_info(char)
    for k in ("chain_id", "chain_name", "step", "title", "objective",
              "location", "npc", "completion_type", "completion"):
        assert k in info, f"legacy key {k} missing"
    # New additive keys present.
    assert info["chain_total_steps"] == 3
    assert info["teaches"] == ["look", "+sheet"]
    assert info["npc_role"] == "instructor"
    assert info["npc_intro"] == "Another one. Sit down."
    assert info["completed_steps"] == []


def test_list_copies_do_not_alias_corpus(stub_corpus):
    char = _char({"chain_id": "bounty_hunter", "step": 1,
                  "completed_steps": [], "completion_state": "active"})
    info = get_active_step_info(char)
    info["teaches"].append("hacked_verb")
    again = get_active_step_info(char)
    assert again["teaches"] == ["look", "+sheet"]
