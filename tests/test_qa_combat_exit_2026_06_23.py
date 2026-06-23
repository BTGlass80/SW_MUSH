# -*- coding: utf-8 -*-
"""
tests/test_qa_combat_exit_2026_06_23.py — QA break-it regression (combat exit).

Two round-2 break-it findings, both about leaving combat:

BLOCKER (combat sweep): a CO-OP PvE kill stranded both players. The engine's
CombatInstance.is_over only counts heads (<=1 active combatant), so when 2+
allied PCs drop the last NPC, active_combatants is still [PC, PC] -> is_over is
False forever: `disengage` refused and `flee` resolved an opposed roll vs an
ALLY. Both players were stuck (couldn't trade/shop/heal/leave).

CORRUPTION (movement sweep): MoveCommand had no in-combat gate, so a player
could walk a normal exit out of an active fight, orphaning the combat instance
(NPCs left in a zombie combat, `who` showing stale 'In Combat', a slow
_active_combats leak).

Fix: a PvP-aware parser-level predicate `_combat_finished(combat)` — the fight
is over unless two MUTUALLY HOSTILE combatants can both still act (NPCs are
hostile to every PC; two PCs only under a live _pvp_active pact). It backs the
round-resolution end-check + disengage (so a co-op kill auto-ends the combat),
and MoveCommand now refuses to walk out of an unfinished combat (-> use flee).

These tests pin the predicate logic directly (fake combat) + structural guards
that it's wired at the round-end, disengage, and the move gate.
"""
from __future__ import annotations

import time
import unittest
from pathlib import Path

from parser import combat_commands
from parser.combat_commands import _combat_finished

REPO = Path(__file__).resolve().parent.parent
CC_SRC = (REPO / "parser" / "combat_commands.py").read_text(encoding="utf-8")
BC_SRC = (REPO / "parser" / "builtin_commands.py").read_text(encoding="utf-8")


class _FakeCombatant:
    def __init__(self, cid: int, is_npc: bool):
        self.id = cid
        self.is_npc = is_npc


class _FakeCombat:
    """Stands in for CombatInstance — _combat_finished only reads
    active_combatants and each combatant's .id / .is_npc."""
    def __init__(self, active):
        self._active = active

    @property
    def active_combatants(self):
        return self._active


def _pc(cid):
    return _FakeCombatant(cid, is_npc=False)


def _npc(cid):
    return _FakeCombatant(cid, is_npc=True)


class TestCombatFinishedPredicate(unittest.TestCase):
    def test_empty_or_lone_combatant_is_finished(self):
        self.assertTrue(_combat_finished(_FakeCombat([])))
        self.assertTrue(_combat_finished(_FakeCombat([_pc(1)])))
        self.assertTrue(_combat_finished(_FakeCombat([_npc(99)])))

    def test_npc_vs_pc_is_not_finished(self):
        self.assertFalse(_combat_finished(_FakeCombat([_pc(1), _npc(99)])))
        self.assertFalse(
            _combat_finished(_FakeCombat([_pc(1), _pc(2), _npc(99)])))

    def test_coop_two_allied_pcs_is_finished(self):
        # THE BLOCKER FIX: 2 PCs, 0 NPCs, no PvP pact -> the fight is over
        # (previously is_over=False stranded them).
        self.assertTrue(_combat_finished(_FakeCombat([_pc(1), _pc(2)])))
        self.assertTrue(
            _combat_finished(_FakeCombat([_pc(1), _pc(2), _pc(3)])))

    def test_only_npcs_left_is_finished(self):
        self.assertTrue(_combat_finished(_FakeCombat([_npc(98), _npc(99)])))

    def test_live_pvp_pair_is_not_finished(self):
        # Two PCs under an active PvP pact are still a real fight.
        combat_commands._pvp_active[(1, 2)] = time.time()
        try:
            self.assertFalse(_combat_finished(_FakeCombat([_pc(1), _pc(2)])))
            # reverse-keyed pact also counts
            combat_commands._pvp_active.pop((1, 2), None)
            combat_commands._pvp_active[(2, 1)] = time.time()
            self.assertFalse(_combat_finished(_FakeCombat([_pc(1), _pc(2)])))
        finally:
            combat_commands._pvp_active.pop((1, 2), None)
            combat_commands._pvp_active.pop((2, 1), None)

    def test_expired_pvp_pact_is_finished(self):
        # A stale (TTL-expired) pact is not hostile -> the fight is over.
        combat_commands._pvp_active[(1, 2)] = (
            time.time() - combat_commands._PVP_CHALLENGE_TTL - 10)
        try:
            self.assertTrue(_combat_finished(_FakeCombat([_pc(1), _pc(2)])))
        finally:
            combat_commands._pvp_active.pop((1, 2), None)

    def test_pvp_pair_among_allies_keeps_fight_alive(self):
        # 3 PCs, one PvP pact (1 vs 3) -> still a fight.
        combat_commands._pvp_active[(1, 3)] = time.time()
        try:
            self.assertFalse(
                _combat_finished(_FakeCombat([_pc(1), _pc(2), _pc(3)])))
        finally:
            combat_commands._pvp_active.pop((1, 3), None)


class TestWiring(unittest.TestCase):
    def test_no_is_over_decision_sites_remain(self):
        # all five decision sites were swapped to _combat_finished.
        self.assertNotIn("if combat.is_over:", CC_SRC)
        self.assertNotIn("if not combat.is_over:", CC_SRC)
        self.assertNotIn(
            "if combat.is_over or len(combat.active_combatants) <= 1:", CC_SRC)

    def test_round_resolution_and_disengage_use_predicate(self):
        # 2 round-end sites + 2 admin-resolve + disengage = 5 uses.
        self.assertGreaterEqual(CC_SRC.count("_combat_finished(combat)"), 5)

    def test_move_command_has_combat_gate(self):
        # the gate must call _combat_finished and direct the player to flee,
        # inside MoveCommand.execute (before the wilderness fork).
        i = BC_SRC.index("class MoveCommand")
        j = BC_SRC.index("class ", i + 1)
        body = BC_SRC[i:j]
        self.assertIn("_combat_finished(_cmb)", body)
        self.assertIn("Use `flee` to attempt escape", body)
        self.assertIn("_combat_key_for(char)", body)


if __name__ == "__main__":
    unittest.main()
