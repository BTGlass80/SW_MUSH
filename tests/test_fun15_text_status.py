# -*- coding: utf-8 -*-
"""
tests/test_fun15_text_status.py — fun15 text-status newcomer commands.

New players who type `goals`, `situation`, `list`, or `presence` at the prompt
used to hit a generic "Huh?" recovery.  fun15 adds real text-output commands
that reuse the same data the web sidebars consume, so telnet AND web players
get a useful answer.

Coverage:
  (a) `goals` prints the accepted mission for a char who has one (mirrors
      test_fun11_goals_handoff.py fake-mission setup).
  (b) `goals` with nothing active prints the friendly empty line, no crash.
  (c) `list` prints vendor_stocked items when an ai_config.vendor NPC is in
      the room, and the no-vendor line otherwise.
  (d) `presence` resolves to the +who command in the registry.
  (e) `situation` prints without crashing — empty-events path and, if easy, a
      populated path via a fake ActiveEvent.
"""
from __future__ import annotations

import asyncio
import json
import types
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from engine.missions import get_mission_board, MissionStatus
from engine.bounty_board import get_bounty_board, BountyStatus
from engine.world_events import get_world_event_manager


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine synchronously (tests are sync)."""
    return asyncio.run(coro)


def _make_fake_session(char):
    """Return a minimal fake session + list of lines sent."""
    lines = []

    async def send_line(text):
        lines.append(text)

    fake = types.SimpleNamespace(
        character=char,
        send_line=send_line,
    )
    return fake, lines


def _make_ctx(session, db=None, session_mgr=None):
    """Return a minimal CommandContext-alike for command.execute()."""
    return types.SimpleNamespace(
        session=session,
        db=db,
        session_mgr=session_mgr,
        args="",
        switches=[],
    )


# ── (a) goals — prints accepted mission ───────────────────────────────────────

def test_goals_prints_accepted_mission():
    """GoalsCommand shows the one accepted mission in the board."""
    from parser.builtin_commands import GoalsCommand

    board = get_mission_board()
    mid = "m-fun15test-a"
    fake_mission = types.SimpleNamespace(
        id=mid,
        accepted_by="42",
        status=MissionStatus.ACCEPTED,
        title="Test Deployment: fun15",
        objective="Report to the test zone.",
        reward=500,
    )
    board._missions[mid] = fake_mission
    try:
        char = {"id": 42, "name": "Tester", "attributes": json.dumps({})}
        session, lines = _make_fake_session(char)
        ctx = _make_ctx(session)
        _run(GoalsCommand().execute(ctx))

        combined = "\n".join(lines)
        assert "Mission" in combined, f"'Mission' not in output: {lines}"
        assert "fun15" in combined, f"mission title not in output: {lines}"
        assert "+missions" in combined, f"stage_cmd hint missing: {lines}"
        assert "500" in combined, f"reward missing: {lines}"
    finally:
        board._missions.pop(mid, None)


# ── (b) goals — nothing active → friendly empty line, no crash ───────────────

def test_goals_empty_no_crash():
    """GoalsCommand with no active goals prints the friendly prompt line."""
    from parser.builtin_commands import GoalsCommand

    # Unique char_id unlikely to be claimed by anything in-board
    char = {"id": 99991, "name": "Empty", "attributes": json.dumps({})}
    session, lines = _make_fake_session(char)
    ctx = _make_ctx(session)
    # Must not raise
    _run(GoalsCommand().execute(ctx))

    combined = "\n".join(lines)
    # Either the "no active goals" line, OR it printed some goals — either way
    # it must not be empty (it always sends at least one line).
    assert lines, "GoalsCommand sent nothing at all — should at least send an empty-state line"
    # If truly empty, the friendly prompt must mention +missions or bounties
    if "Goal" not in combined and "Mission" not in combined:
        assert "+missions" in combined or "bounties" in combined, (
            f"Empty-goals line missing navigation hint: {lines}")


# ── (c) list — vendor present → stock; no vendor → helpful message ────────────

class _FakeDB:
    """Minimal async-DB stub with get_npcs_in_room."""
    def __init__(self, npcs):
        self._npcs = npcs

    async def get_npcs_in_room(self, room_id):
        return self._npcs


def test_list_with_vendor_shows_stock():
    """ListCommand prints vendor_stocked weapons when a vendor NPC is present."""
    from parser.builtin_commands import ListCommand
    from engine.weapons import get_weapon_registry

    # Confirm there's at least one vendor_stocked weapon in the registry
    wr = get_weapon_registry()
    stocked = [w for w in wr.all_weapons() if getattr(w, "vendor_stocked", False)]
    assert stocked, "No vendor_stocked weapons found — test pre-condition failed"

    vendor_npc = {
        "name": "Keval the Arms Dealer",
        "ai_config_json": json.dumps({"vendor": True}),
    }
    char = {"id": 7, "name": "Buyer", "room_id": 1}
    session, lines = _make_fake_session(char)
    db = _FakeDB([vendor_npc])
    ctx = _make_ctx(session, db=db)

    _run(ListCommand().execute(ctx))

    combined = "\n".join(lines)
    assert "Stock" in combined or "Item" in combined, (
        f"Vendor stock header missing: {lines}")
    # At least one stocked weapon name should appear
    found_any = any(w.name in combined for w in stocked)
    assert found_any, f"No vendor_stocked weapon name found in output: {lines}"
    assert "buy" in combined.lower(), f"buy hint missing: {lines}"


def test_list_no_vendor_shows_helpful_message():
    """ListCommand prints the no-vendor helpful line when no vendor NPC in room."""
    from parser.builtin_commands import ListCommand

    char = {"id": 8, "name": "Lost", "room_id": 1}
    session, lines = _make_fake_session(char)
    db = _FakeDB([])  # empty room
    ctx = _make_ctx(session, db=db)

    _run(ListCommand().execute(ctx))

    combined = "\n".join(lines)
    assert "No vendor" in combined or "browse" in combined, (
        f"No-vendor message missing: {lines}")


# ── (d) presence resolves to +who command ─────────────────────────────────────

def test_presence_resolves_to_who_command():
    """'presence' is a registered alias that resolves to WhoCommand (+who)."""
    from tests.test_t321_admin_command_access_invariant import _build_full_registry

    registry = _build_full_registry()
    who_cmd = registry.get("+who")
    assert who_cmd is not None, "+who not in registry"

    presence_cmd = registry.get("presence")
    assert presence_cmd is not None, "'presence' not registered in registry"
    assert presence_cmd is who_cmd, (
        f"'presence' resolves to {presence_cmd!r}, not WhoCommand (+who)")


# ── (e) situation — no crash on empty + active-events path ───────────────────

def test_situation_empty_events_no_crash():
    """SituationCommand prints the quiet-sector line when no events are active."""
    from parser.builtin_commands import SituationCommand

    # Reset the manager to ensure clean state for this test
    import engine.world_events as _we
    original_manager = _we._manager
    _we._manager = None  # force fresh empty manager

    try:
        char = {"id": 10, "name": "Scout", "room_id": 1}
        session, lines = _make_fake_session(char)
        ctx = _make_ctx(session)

        _run(SituationCommand().execute(ctx))

        combined = "\n".join(lines)
        assert lines, "SituationCommand sent nothing"
        assert "quiet" in combined.lower() or "no active" in combined.lower(), (
            f"Empty-events line missing: {lines}")
    finally:
        _we._manager = original_manager


def test_situation_active_event_shown():
    """SituationCommand lists active event name and headline without crashing."""
    from parser.builtin_commands import SituationCommand
    import engine.world_events as _we
    from engine.world_events import WorldEventManager

    # Construct a fake manager with one fake active event via get_status
    class _FakeManager:
        def get_status(self):
            return [
                {
                    "type": "merchant_arrival",
                    "name": "Merchant Arrival",
                    "headline": "A rare merchant has arrived in the sector.",
                    "zones": [],
                    "remaining_minutes": 30,
                    "effects": {},
                }
            ]

    original_manager = _we._manager
    _we._manager = _FakeManager()
    try:
        char = {"id": 11, "name": "Scout2", "room_id": 1}
        session, lines = _make_fake_session(char)
        ctx = _make_ctx(session)

        _run(SituationCommand().execute(ctx))

        combined = "\n".join(lines)
        assert "Merchant" in combined, f"Event name missing: {lines}"
        assert "rare merchant" in combined.lower(), f"Headline missing: {lines}"
    finally:
        _we._manager = original_manager
