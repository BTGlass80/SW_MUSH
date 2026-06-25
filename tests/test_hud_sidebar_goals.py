# -*- coding: utf-8 -*-
"""
tests/test_hud_sidebar_goals.py — UX Drop 6: Session._hud_sidebar_goals.

Exercises the engine HUD producer that consolidates the graduated player's
active questline step + accepted mission + claimed bounty into one
`goals_status` push. Mirrors the stub-session harness of
tests/test_hud_scene_context.py (call the unbound method against a stub
`self`; capture the send_json output).

The mission + bounty slices read the REAL in-memory board singletons (the same
authoritative source _hud_active_jobs reads); the questline slice + onboarding
gate are monkeypatched (they need corpus state). This proves the producer's own
composition / visibility-filter / shape / early-return logic.

Asserts:
  · a character with each of the three goal sources yields the composed payload
    with the right per-slot shape + reward/progress
  · the questline slice is SUPPRESSED while the onboarding chain is active
  · all-empty (no questline/mission/bounty) → NO send (early return)
  · a mission/bounty accepted by a DIFFERENT character is not surfaced
  · a chain-tagged bounty the viewer can't see is filtered out
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import engine.chain_events as chain_events
import engine.missions as missions_mod
import engine.bounty_board as bounty_mod
from engine.missions import Mission, MissionType, MissionStatus
from engine.bounty_board import BountyContract, BountyTier, BountyStatus
from server.session import Session


# ── Stub session: a bare object carrying .character + a captured send_json. ──
class _StubSession:
    def __init__(self, char):
        self.character = char
        self.sent = []          # list of (msg_type, data)

    async def send_json(self, msg_type, data):
        self.sent.append((msg_type, data))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Board singleton isolation ───────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _fresh_boards():
    """Reset the mission + bounty board singletons around each test so seeded
    objects never leak between tests (or from the real game state)."""
    missions_mod._board = missions_mod.MissionBoard()
    bounty_mod._board = bounty_mod.BountyBoard()
    yield
    missions_mod._board = None
    bounty_mod._board = None


@pytest.fixture(autouse=True)
def _no_onboarding(monkeypatch):
    """Default: the player has graduated (no active onboarding chain), so the
    questline slice is NOT suppressed. Individual tests override as needed."""
    monkeypatch.setattr(chain_events, "build_onboarding_state",
                        lambda char, era=None: None)
    monkeypatch.setattr(chain_events, "get_questline_status",
                        lambda char, era=None: None)


def _seed_mission(char_id_str, *, mission_id="m-1", title="Run the blockade",
                  objective="Reach Bay 94 undetected.", reward=750,
                  status=MissionStatus.ACCEPTED):
    m = Mission(
        id=mission_id, mission_type=MissionType.DELIVERY, title=title,
        giver="Marunt", objective=objective, destination="Docking Bay 94",
        destination_room_id=None, reward=reward, required_skill="streetwise",
        status=status, accepted_by=char_id_str,
    )
    missions_mod._board._missions[m.id] = m
    return m


def _seed_bounty(char_id_str, *, bounty_id="b-1", target="Tarko Vinn",
                 tier=BountyTier.VETERAN, reward=2400,
                 status=BountyStatus.CLAIMED, expires_at=None,
                 chain_bounty_id=""):
    if expires_at is None:
        expires_at = time.time() + 3600
    c = BountyContract(
        id=bounty_id, tier=tier, target_name=target, target_species="Human",
        target_archetype="thug", crime_description="wanted", posting_org="Guild",
        tip="last seen at the cantina", reward=reward, reward_alive_bonus=0,
        target_npc_id=None, target_room_id=None, status=status,
        claimed_by=char_id_str, expires_at=expires_at,
        chain_bounty_id=chain_bounty_id,
    )
    bounty_mod._board._contracts[c.id] = c
    return c


# ── Tests ───────────────────────────────────────────────────────────────────

def test_composes_all_three_slots(monkeypatch):
    char = {"id": 7, "name": "Rax", "attributes": "{}"}
    # Questline present (graduated → not suppressed).
    monkeypatch.setattr(chain_events, "get_questline_status",
        lambda c, era=None: {
            "chain_id": "smuggler_run", "chain_name": "Smuggler's Run",
            "title": "The Kessel Gambit", "objective": "Slice the terminal.",
            "step": 2, "chain_total_steps": 4,
            "next_hint": "Return to Marunt.", "command_to_type": "chain attempt",
        })
    _seed_mission("7")
    _seed_bounty("7")

    s = _StubSession(char)
    _run(Session._hud_sidebar_goals(s, None, char, 7))

    assert len(s.sent) == 1, "exactly one goals_status push expected"
    msg_type, data = s.sent[0]
    assert msg_type == "goals_status"

    q = data["questline"]
    assert q["chain_id"] == "smuggler_run"
    assert q["title"] == "The Kessel Gambit"
    assert q["step"] == 2 and q["total_steps"] == 4
    assert q["command_to_type"] == "chain attempt"

    m = data["mission"]
    assert m["id"] == "m-1"
    assert m["title"] == "Run the blockade"
    assert m["objective"] == "Reach Bay 94 undetected."
    assert m["reward"] == 750
    assert m["stage_cmd"] == "+missions"

    b = data["bounty"]
    assert b["id"] == "b-1"
    assert b["target_name"] == "Tarko Vinn"
    assert b["tier"] == "veteran"           # enum .value
    assert b["reward"] == 2400
    assert isinstance(b["expires_in_secs"], int) and b["expires_in_secs"] > 0
    assert b["stage_cmd"] == "bounties"


def test_no_goals_sends_nothing():
    char = {"id": 7, "name": "Rax", "attributes": "{}"}
    s = _StubSession(char)
    _run(Session._hud_sidebar_goals(s, None, char, 7))
    assert s.sent == [], "a player with no goals must get no push (early return)"


def test_questline_suppressed_while_onboarding_active(monkeypatch):
    char = {"id": 7, "name": "Rax", "attributes": "{}"}
    # Onboarding chain still active → questline slice suppressed.
    monkeypatch.setattr(chain_events, "build_onboarding_state",
                        lambda c, era=None: {"active": True, "chain_id": "npe"})
    monkeypatch.setattr(chain_events, "get_questline_status",
        lambda c, era=None: {
            "chain_id": "q", "chain_name": "Q", "title": "Q", "objective": "o",
            "step": 1, "chain_total_steps": 2, "next_hint": "",
            "command_to_type": "",
        })
    _seed_mission("7")          # a mission keeps the panel alive

    s = _StubSession(char)
    _run(Session._hud_sidebar_goals(s, None, char, 7))

    assert len(s.sent) == 1
    _, data = s.sent[0]
    assert data["questline"] is None, "questline must be suppressed during the NPE"
    assert data["mission"] is not None, "the mission slice still surfaces"


def test_mission_for_other_character_not_surfaced():
    char = {"id": 7, "name": "Rax", "attributes": "{}"}
    _seed_mission("99")         # accepted by a DIFFERENT character
    s = _StubSession(char)
    _run(Session._hud_sidebar_goals(s, None, char, 7))
    assert s.sent == [], "another character's mission must not surface (no goals)"


def test_unclaimed_bounty_not_surfaced():
    char = {"id": 7, "name": "Rax", "attributes": "{}"}
    # Claimed by someone else AND a posted (unclaimed) one for the viewer.
    _seed_bounty("99", bounty_id="b-other")
    _seed_bounty("7", bounty_id="b-posted", status=BountyStatus.POSTED)
    s = _StubSession(char)
    _run(Session._hud_sidebar_goals(s, None, char, 7))
    assert s.sent == [], "only a viewer-CLAIMED contract counts as a goal"


def test_chain_bounty_filtered_when_not_visible():
    """A chain-tagged bounty the viewer can't see (no matching active chain)
    is excluded by is_chain_bounty_visible_to."""
    char = {"id": 7, "name": "Rax", "attributes": "{}"}
    _seed_bounty("7", bounty_id="b-chain",
                 chain_bounty_id="tutorial_bhg_tarko_vinn")
    s = _StubSession(char)
    _run(Session._hud_sidebar_goals(s, None, char, 7))
    # Viewer has no active tutorial chain → the chain bounty is invisible →
    # no other goals → nothing sent.
    assert s.sent == [], "an invisible chain bounty must be filtered out"


def test_bounty_expires_in_secs_floors_at_zero():
    char = {"id": 7, "name": "Rax", "attributes": "{}"}
    _seed_bounty("7", expires_at=time.time() - 5)   # already expired epoch
    s = _StubSession(char)
    _run(Session._hud_sidebar_goals(s, None, char, 7))
    assert len(s.sent) == 1
    _, data = s.sent[0]
    assert data["bounty"]["expires_in_secs"] == 0, "expired countdown floors at 0"
