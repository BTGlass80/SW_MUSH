# -*- coding: utf-8 -*-
"""
tests/test_fun11_goals_handoff.py — FUN11 graduation guidance handoff.

8th fun re-run #1 kills-it: the moment the NPE chain completed ("the galaxy is
open"), the GOALS sidebar stayed blank — the just-accepted tutorial mission
"First Deployment" was filtered out of the GOALS mission slot by
is_chain_mission_visible_to (a BOARD-offering filter wrongly applied to an
ALREADY-ACCEPTED mission), so questline+mission+bounty were all empty and the
panel early-returned to nothing exactly when the player most needed direction.

Fix: an accepted mission always surfaces in GOALS regardless of chain-step
visibility. This test drives Session._hud_sidebar_goals with a fake self and an
accepted chain-mission on the board and asserts goals_status fires with it.
"""
from __future__ import annotations

import asyncio
import json
import types

from engine.missions import get_mission_board, MissionStatus
from server.session import Session


def _run_goals(char, char_id):
    sent = {}

    async def _send_json(typ, payload):
        sent["type"] = typ
        sent["payload"] = payload

    fake_self = types.SimpleNamespace(send_json=_send_json)
    asyncio.run(Session._hud_sidebar_goals(fake_self, None, char, char_id))
    return sent


def test_accepted_chain_mission_surfaces_in_goals_post_graduation():
    board = get_mission_board()
    mid = "m-fun11test"
    fake_mission = types.SimpleNamespace(
        id=mid,
        accepted_by="77",
        status=MissionStatus.ACCEPTED,
        title="First Deployment: Coruscant Industrial District",
        objective="Report to Sergeant Drix at the Coruscant Works landing zone.",
        reward=300,
        # chain_mission_id present → the OLD code's is_chain_mission_visible_to
        # filter would have HIDDEN this post-graduation. It must surface now.
        mission_data={"chain_mission_id": "tutorial_republic_first_deployment"},
    )
    board._missions[mid] = fake_mission
    try:
        # A freshly-graduated char: no active onboarding, no questline yet.
        char = {"id": 77, "name": "Grad", "attributes": json.dumps({})}
        sent = _run_goals(char, 77)
        assert sent.get("type") == "goals_status", (
            "GOALS panel did not fire post-graduation (guidance vacuum)")
        mission = sent["payload"].get("mission")
        assert mission is not None, "accepted mission missing from GOALS"
        assert "Deployment" in (mission.get("title") or "")
        assert mission.get("stage_cmd") == "+missions"
    finally:
        board._missions.pop(mid, None)


def test_goals_empty_when_nothing_active():
    """No questline, no accepted mission, no bounty → no panel (unchanged)."""
    char = {"id": 9999, "name": "Idle", "attributes": json.dumps({})}
    sent = _run_goals(char, 9999)
    # send_json should not have been called → empty dict
    assert sent == {}, f"GOALS fired with nothing active: {sent}"
