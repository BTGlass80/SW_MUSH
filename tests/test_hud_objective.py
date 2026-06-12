# -*- coding: utf-8 -*-
"""
test_hud_objective.py — Webify Drop UI-6: hud_update.objective.

Three layers, all sandbox-runnable (server/session.py imports only
stdlib + engine modules at top level — no aiohttp):

1. `_objective_line` (pure): per-type formats, first-job priority,
   truncation, empty/malformed tolerance.
2. `_hud_active_jobs` bounty branch FIX: BountyContract fields are
   `claimed_by` + status "claimed"; the old `accepted_by`/"accepted"
   check matched nothing ever. Functional test against the real board
   singleton (reset in teardown — singleton-isolation discipline).
3. `_hud_active_jobs` tutorial priority: a stub corpus (monkeypatched
   through engine.chain_events._get_corpus) puts the active chain step
   first, and the derived hud["objective"] is the step objective.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

import engine.bounty_board as bounty_board
from engine.bounty_board import (
    BountyContract,
    BountyStatus,
    BountyTier,
)
from server.session import Session, _objective_line, _OBJECTIVE_MAX_LEN


# ── 1. _objective_line (pure) ────────────────────────────────────────


def test_objective_tutorial_uses_step_objective():
    jobs = [{"type": "tutorial", "label": "First Steps",
             "objective": "Speak with Sergeant Kappehl in the mess hall."}]
    assert _objective_line(jobs) == (
        "Speak with Sergeant Kappehl in the mess hall.")


def test_objective_bounty_format_matches_design():
    jobs = [{"type": "bounty", "label": "Bounty: Tarko Vinn",
             "target": "Tarko Vinn", "reward": 1500}]
    assert _objective_line(jobs) == "Hunt Tarko Vinn — 1,500 cr bounty"


def test_objective_mission_label_dash_objective():
    jobs = [{"type": "mission", "label": "Cargo Run",
             "objective": "Anchorhead", "reward": 400}]
    assert _objective_line(jobs) == "Cargo Run — Anchorhead"


def test_objective_smuggle_label_dash_reward():
    jobs = [{"type": "smuggle", "label": "Spice → Anchorhead",
             "reward": 750}]
    assert _objective_line(jobs) == "Spice → Anchorhead — 750 cr"


def test_objective_quest_prefers_objective_text():
    jobs = [{"type": "quest", "label": "The Spacer's Path",
             "objective": "Refuel at Docking Bay 94."}]
    assert _objective_line(jobs) == "Refuel at Docking Bay 94."


def test_objective_first_job_wins():
    jobs = [
        {"type": "tutorial", "label": "T", "objective": "Tutorial first."},
        {"type": "bounty", "label": "B", "target": "X", "reward": 100},
    ]
    assert _objective_line(jobs) == "Tutorial first."


def test_objective_truncates_with_ellipsis():
    long = "x" * 300
    line = _objective_line([{"type": "quest", "label": "Q", "objective": long}])
    assert len(line) <= _OBJECTIVE_MAX_LEN
    assert line.endswith("…")


def test_objective_empty_and_malformed_safe():
    assert _objective_line([]) == ""
    assert _objective_line(None) == ""
    # A malformed entry is skipped; the next usable one wins.
    jobs = [None, {"type": "quest", "label": "", "objective": ""},
            {"type": "mission", "label": "Real", "objective": ""}]
    assert _objective_line(jobs) == "Real"


# ── 2 + 3. _hud_active_jobs (functional, singleton-isolated) ─────────


@pytest.fixture
def clean_board():
    """Reset the bounty-board singleton around each functional test
    (singleton-isolation discipline — same lesson as world_events)."""
    bounty_board._board = None
    yield bounty_board.get_bounty_board()
    bounty_board._board = None


def _run_active_jobs(char: dict) -> dict:
    """Invoke the (self-free) _hud_active_jobs body and return the hud."""
    hud: dict = {}
    asyncio.run(Session._hud_active_jobs(None, hud, char))
    return hud


def test_active_jobs_bounty_branch_fix(clean_board):
    """The branch must match claimed_by + status 'claimed' — the old
    accepted_by/'accepted' check never fired for any contract."""
    c = BountyContract(
        id="b-hud1", tier=BountyTier.VETERAN, target_name="Tarko Vinn",
        target_species="Human", target_archetype="smuggler",
        crime_description="c", posting_org="o", tip="t",
        reward=1500, reward_alive_bonus=150,
        target_npc_id=1, target_room_id=2,
        status=BountyStatus.CLAIMED, claimed_by="7",
        expires_at=time.time() + 600,
    )
    clean_board._contracts[c.id] = c

    char = {"id": 7, "attributes": "{}"}
    hud = _run_active_jobs(char)

    bounty_jobs = [j for j in hud["active_jobs"] if j["type"] == "bounty"]
    assert len(bounty_jobs) == 1
    assert bounty_jobs[0]["target"] == "Tarko Vinn"
    assert bounty_jobs[0]["reward"] == 1500
    assert hud["objective"] == "Hunt Tarko Vinn — 1,500 cr bounty"


def test_active_jobs_bounty_not_listed_for_other_character(clean_board):
    c = BountyContract(
        id="b-hud2", tier=BountyTier.NOVICE, target_name="N",
        target_species="Human", target_archetype="thug",
        crime_description="c", posting_org="o", tip="t",
        reward=900, reward_alive_bonus=0,
        target_npc_id=1, target_room_id=2,
        status=BountyStatus.CLAIMED, claimed_by="999",
        expires_at=time.time() + 600,
    )
    clean_board._contracts[c.id] = c

    hud = _run_active_jobs({"id": 7, "attributes": "{}"})
    assert [j for j in hud["active_jobs"] if j["type"] == "bounty"] == []
    assert hud["objective"] == ""


def test_active_jobs_tutorial_step_first_and_drives_objective(
        clean_board, monkeypatch):
    """An active tutorial-chain step is the highest-priority job and
    the derived objective line. Corpus is stubbed through the cached
    loader seam (engine.chain_events._get_corpus)."""
    step = SimpleNamespace(step=2, title="Meet the Quartermaster",
                           objective="Requisition a blaster from Sergeant Kappehl.")
    chain = SimpleNamespace(steps=[SimpleNamespace(step=1, title="x",
                                                   objective="y"), step])
    corpus = SimpleNamespace(by_id=lambda: {"republic_soldier": chain})

    import engine.chain_events as chain_events
    monkeypatch.setattr(chain_events, "_get_corpus", lambda era=None: corpus)

    # Give the same character a claimed bounty too — tutorial must win.
    c = BountyContract(
        id="b-hud3", tier=BountyTier.EXTRA, target_name="Z",
        target_species="Human", target_archetype="thug",
        crime_description="c", posting_org="o", tip="t",
        reward=200, reward_alive_bonus=0,
        target_npc_id=1, target_room_id=2,
        status=BountyStatus.CLAIMED, claimed_by="7",
        expires_at=time.time() + 600,
    )
    clean_board._contracts[c.id] = c

    attrs = json.dumps({"tutorial_chain": {
        "completion_state": "active",
        "chain_id": "republic_soldier",
        "step": 2,
    }})
    hud = _run_active_jobs({"id": 7, "attributes": attrs})

    assert hud["active_jobs"][0]["type"] == "tutorial"
    assert hud["active_jobs"][0]["label"] == "Meet the Quartermaster"
    assert hud["objective"] == (
        "Requisition a blaster from Sergeant Kappehl.")
    # The bounty job is still present, just lower priority.
    assert any(j["type"] == "bounty" for j in hud["active_jobs"])


def test_active_jobs_no_tutorial_when_chain_inactive(clean_board, monkeypatch):
    corpus = SimpleNamespace(by_id=lambda: {})
    import engine.chain_events as chain_events
    monkeypatch.setattr(chain_events, "_get_corpus", lambda era=None: corpus)

    attrs = json.dumps({"tutorial_chain": {
        "completion_state": "graduated",
        "chain_id": "republic_soldier",
        "step": 9,
    }})
    hud = _run_active_jobs({"id": 7, "attributes": attrs})
    assert [j for j in hud["active_jobs"] if j["type"] == "tutorial"] == []
