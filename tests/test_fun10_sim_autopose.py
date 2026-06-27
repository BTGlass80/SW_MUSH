# -*- coding: utf-8 -*-
"""
tests/test_fun10_sim_autopose.py — FUN10 sim combat auto-resolve.

7th fun re-run #1 kills-it: the tutorial combat soft-locked because a newcomer's
instinct (type `attack` again) stacked multi-action penalties in an unresolved
ROUND 1 until the dice pool hit 0D and every swing auto-missed forever — the
round only resolved on a `pass`/pose the player didn't know to give. In a sim,
players are now auto-posed (like NPCs) so each declared attack resolves
immediately and spamming `attack` wins.
"""
from __future__ import annotations

import inspect

from parser.combat_commands import _auto_pose_sim_players, _start_posing_window


class _Comb:
    def __init__(self, cid, is_npc):
        self.id = cid
        self.is_npc = is_npc


class _FakeCombat:
    def __init__(self, pending):
        self._pending = list(pending)
        self._by = {1: _Comb(1, False), 2: _Comb(2, True)}
        self.posed = {}

    def get_pending_poser_ids(self):
        return list(self._pending)

    def get_combatant(self, cid):
        return self._by.get(cid)

    def generate_auto_pose(self, cid):
        return f"auto-{cid}"

    def set_pose_status(self, cid, status, text=None):
        self.posed[cid] = (status, text)


def test_sim_autopose_poses_players_not_npcs():
    c = _FakeCombat(pending=[1, 2])
    _auto_pose_sim_players(c)
    assert c.posed.get(1) == ("passed", "auto-1"), "player not auto-posed in sim"
    # NPCs are handled by _auto_generate_npc_poses, not here
    assert 2 not in c.posed, "NPC should not be (re)posed by the sim-player helper"


def test_sim_autopose_no_pending_is_noop():
    c = _FakeCombat(pending=[])
    _auto_pose_sim_players(c)
    assert c.posed == {}


def test_start_posing_window_calls_sim_autopose():
    """Guard against a refactor dropping the sim auto-resolve from the posing
    window (the actual soft-lock fix)."""
    src = inspect.getsource(_start_posing_window)
    assert "_auto_pose_sim_players" in src
    assert "is_simulation" in src
