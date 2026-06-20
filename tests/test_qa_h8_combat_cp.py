# -*- coding: utf-8 -*-
"""tests/test_qa_h8_combat_cp.py — QA HIGH H8 (+ adjacent MEDIUM) regression.

H8: declaring multiple CP-spending actions in one round validated each action's
cp_spend against CURRENT CP, not the RUNNING SUM, so two 5-CP actions with 5 CP
on hand both passed and the resolvers drove character_points negative. Fix:
running-sum validation in declare_action + a 0-floor in both resolvers.

M (adjacent): combat CP spend was never persisted (only wound_level saved), so
reconnect refunded it. Fix: persist character_points alongside wound_level.
"""
from __future__ import annotations

import os

from engine.character import Character, DicePool, SkillRegistry
from engine.combat import CombatInstance, CombatAction, ActionType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reg():
    reg = SkillRegistry()
    p = os.path.join(REPO_ROOT, "data", "skills.yaml")
    if os.path.exists(p):
        reg.load_file(p)
    return reg


def _fighter(name, char_id, cp):
    c = Character(name=name, species_name="Human")
    c.id = char_id
    c.dexterity = DicePool.parse("4D")
    c.strength = DicePool.parse("3D")
    c.add_skill("blaster", DicePool.parse("3D"))
    c.add_skill("dodge", DicePool.parse("2D"))
    c.character_points = cp
    return c


def _engine(cp=5):
    combat = CombatInstance(room_id=1, skill_reg=_reg())
    combat.add_combatant(_fighter("Spender", 1, cp=cp))
    combat.add_combatant(_fighter("Target", 2, cp=cp))
    return combat


def _atk(cp):
    return CombatAction(action_type=ActionType.ATTACK, skill="blaster",
                        target_id=2, cp_spend=cp)


def test_h8_single_action_within_budget_ok():
    assert _engine(cp=5).declare_action(1, _atk(5)) is None


def test_h8_single_action_over_budget_rejected():
    err = _engine(cp=5).declare_action(1, _atk(6))
    assert err and "Character Points" in err


def test_h8_running_sum_blocks_second_overcommit():
    # The bug: first 5-CP action OK, second 5-CP action also passed (5 <= 5) and
    # the resolvers drove CP to -5. The fix rejects the second on the running sum.
    combat = _engine(cp=5)
    assert combat.declare_action(1, _atk(5)) is None
    err = combat.declare_action(1, _atk(5))
    assert err and "Character Points" in err, (
        "H8 regressed: running-sum CP validation lets a 2nd action overcommit"
    )


def test_h8_floor_and_m_persist_in_source():
    with open(os.path.join(REPO_ROOT, "engine", "combat.py"), encoding="utf-8") as f:
        cb = f.read()
    assert "max(0, actor.char.character_points - action.cp_spend)" in cb, \
        "H8 resolver floor missing"
    assert "character_points -= action.cp_spend" not in cb, \
        "H8 regressed: an unfloored CP subtract remains"
    with open(os.path.join(REPO_ROOT, "parser", "combat_commands.py"), encoding="utf-8") as f:
        cc = f.read()
    assert "character_points=c.char.character_points" in cc, \
        "M regressed: combat CP spend no longer persisted"
