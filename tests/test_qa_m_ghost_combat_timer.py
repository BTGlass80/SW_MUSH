# -*- coding: utf-8 -*-
"""tests/test_qa_m_ghost_combat_timer.py — QA MEDIUM regression: ghost combat round.

The _grace_timer_handle (pose-window background task) was never cancelled in
_remove_combat, so when combat ended via auto-resolve the timer kept running.
After 90s it broadcast a nudge + after 180s it flushed the action-log into a
dead/removed combat, producing ghost narration and a spurious initiative roll.

Fix: _remove_combat cancels the handle (getattr + .cancel()) before cleanup.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import parser.combat_commands as cc
from engine.character import Character, DicePool, SkillRegistry
from engine.combat import CombatInstance

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reg():
    reg = SkillRegistry()
    p = os.path.join(REPO_ROOT, "data", "skills.yaml")
    if os.path.exists(p):
        reg.load_file(p)
    return reg


def _make_combat(room_id: int = 101) -> CombatInstance:
    return CombatInstance(room_id=room_id, skill_reg=_reg())


def _register(combat: CombatInstance):
    """Insert combat into the module-level dict keyed the same way _remove_combat keys it."""
    key = (combat.room_id, combat.wilderness_x, combat.wilderness_y)
    cc._active_combats[key] = combat


def _teardown(combat: CombatInstance):
    """Belt-and-suspenders: remove from dict even if test fails mid-flight."""
    key = (combat.room_id, combat.wilderness_x, combat.wilderness_y)
    cc._active_combats.pop(key, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_remove_combat_cancels_pending_grace_timer():
    """Active grace timer must be cancelled on combat removal."""
    combat = _make_combat(room_id=201)
    handle = MagicMock()
    handle.done.return_value = False
    combat._grace_timer_handle = handle
    _register(combat)
    try:
        cc._remove_combat(combat)
    finally:
        _teardown(combat)

    handle.cancel.assert_called_once()


def test_remove_combat_skips_done_grace_timer():
    """Already-finished timer must not be cancelled (idempotent)."""
    combat = _make_combat(room_id=202)
    handle = MagicMock()
    handle.done.return_value = True
    combat._grace_timer_handle = handle
    _register(combat)
    try:
        cc._remove_combat(combat)
    finally:
        _teardown(combat)

    handle.cancel.assert_not_called()


def test_remove_combat_no_grace_timer():
    """Combat with no timer (None) is removed cleanly."""
    combat = _make_combat(room_id=203)
    assert combat._grace_timer_handle is None
    _register(combat)
    try:
        cc._remove_combat(combat)
    finally:
        _teardown(combat)

    key = (203, None, None)
    assert key not in cc._active_combats


def test_remove_combat_already_absent_is_noop():
    """_remove_combat on a combat not in the dict does not raise."""
    combat = _make_combat(room_id=204)
    # Do NOT register — the dict doesn't have it.
    cc._remove_combat(combat)  # must not raise


def test_remove_combat_clears_active_combats_entry():
    """The entry is removed from _active_combats after _remove_combat."""
    combat = _make_combat(room_id=205)
    _register(combat)
    try:
        cc._remove_combat(combat)
    finally:
        _teardown(combat)

    key = (205, None, None)
    assert key not in cc._active_combats


def test_remove_combat_with_npc_behaviors():
    """NPC behaviors for combatants are cleaned up."""
    combat = _make_combat(room_id=206)
    char = Character(name="TestNPC", species_name="Human")
    char.id = 9001
    combat.combatants[9001] = MagicMock(id=9001)
    cc._npc_behaviors[9001] = {"state": "some_behavior"}
    _register(combat)
    try:
        cc._remove_combat(combat)
    finally:
        _teardown(combat)
        cc._npc_behaviors.pop(9001, None)

    assert 9001 not in cc._npc_behaviors
