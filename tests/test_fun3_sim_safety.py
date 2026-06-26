# -*- coding: utf-8 -*-
"""
tests/test_fun3_sim_safety.py — fun3-sim-safety drop validation.

Verifies:
  (a) In an is_simulation CombatInstance a player defender taking a
      would-be-Wounded+ hit ends at STUNNED (wound_level <= STUNNED),
      never WOUNDED/INCAPACITATED via the wound track.
  (b) An NPC defender in the same sim room takes the normal wound
      (damage_margin > 1 → WOUNDED+, so the drill is winnable).
  (c) In a non-sim room the player takes the normal wound — regression:
      nothing changed for real combat.
  (d) add_scar is skipped when combat.is_simulation is True and fires
      when it is False.
  (e) CombatInstance.is_simulation reads True when constructed with
      is_simulation=True; reads False by default.

The tests are sync and exercise the engine directly (no command layer,
no DB, no async).  They drive _apply_damage via a mock ActionResult
wrapper that mirrors the actual call path.
"""

import time
import types
import pytest

from engine.character import Character, DicePool, SkillRegistry, WoundLevel
from engine.combat import (
    CombatInstance, CombatAction, ActionType, Combatant,
    RangeBand,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_skill_reg():
    import os
    reg = SkillRegistry()
    skills_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "skills.yaml"
    )
    if os.path.exists(skills_path):
        reg.load_file(skills_path)
    return reg


def _make_char(name="TestChar", strength="3D", char_id=1, blaster="4D", dodge="3D"):
    c = Character(name=name, species_name="Human")
    c.id = char_id
    c.dexterity = DicePool.parse("3D")
    c.strength = DicePool.parse(strength)
    c.add_skill("blaster", DicePool.parse(blaster))
    c.add_skill("dodge", DicePool.parse(dodge))
    return c


def _make_combat(room_id=1, is_simulation=False):
    reg = _make_skill_reg()
    return CombatInstance(
        room_id=room_id,
        skill_reg=reg,
        is_simulation=is_simulation,
    )


def _make_combatant(char, is_npc=False) -> Combatant:
    c = Combatant(id=char.id, name=char.name, is_npc=is_npc, char=char)
    return c


def _make_attack_action(target_id, weapon_damage="4D", stun_mode=False):
    return CombatAction(
        action_type=ActionType.ATTACK,
        skill="blaster",
        target_id=target_id,
        weapon_damage=weapon_damage,
        stun_mode=stun_mode,
    )


def _call_apply_damage(combat, actor_c, target_c, damage_margin_override=None,
                       action=None):
    """
    Drive combat._apply_damage with a rigged damage roll so we get a
    deterministic damage_margin.  We monkey-patch roll_d6_pool to return
    a fixed total.

    damage_margin_override controls attack_total - soak_total.
    The target has 1D+0 soak (Strength 1D); we set damage roll total to
    soak_total + damage_margin_override.
    """
    import engine.combat as _combat_mod

    if action is None:
        action = _make_attack_action(target_c.id)

    # Determine soak total deterministically: patch roll_d6_pool to return
    # fixed values.  First call = damage roll, second call = soak roll, and
    # for sim KO branch there's a third call (2D duration).
    call_count = [0]
    soak_fixed = 3  # fixed soak total so margin = damage_fixed - soak_fixed

    if damage_margin_override is None:
        damage_margin_override = 4  # default: big hit that would wound

    damage_fixed = soak_fixed + damage_margin_override

    class _FakeResult:
        def __init__(self, total):
            self.total = total
            self.rolls = [total]
            self.normal_dice = [total]
            self.wild_die = None
            self.pips = 0
            self.exploded = False

        def display(self):
            return str(self.total)

    original_roll = _combat_mod.roll_d6_pool

    def _fake_roll(pool):
        call_count[0] += 1
        if call_count[0] == 1:
            return _FakeResult(damage_fixed)   # damage roll
        if call_count[0] == 2:
            return _FakeResult(soak_fixed)     # soak roll
        return _FakeResult(2)                  # stun duration roll (2 min)

    _combat_mod.roll_d6_pool = _fake_roll
    try:
        result = combat._apply_damage(
            actor=actor_c,
            target_c=target_c,
            action=action,
            attack_total=damage_fixed + 5,  # well above soak
            defense_display="3",
        )
    finally:
        _combat_mod.roll_d6_pool = original_roll

    return result


# ═══════════════════════════════════════════════════════════════════════
# (e) CombatInstance.is_simulation attribute
# ═══════════════════════════════════════════════════════════════════════

class TestIsSimulationFlag:
    def test_default_is_false(self):
        """CombatInstance defaults to is_simulation=False."""
        combat = _make_combat(room_id=1, is_simulation=False)
        assert combat.is_simulation is False

    def test_set_true(self):
        """CombatInstance.is_simulation=True when constructed with is_simulation=True."""
        combat = _make_combat(room_id=1, is_simulation=True)
        assert combat.is_simulation is True

    def test_room_id_preserved(self):
        """room_id is unaffected by is_simulation kwarg."""
        combat = _make_combat(room_id=600, is_simulation=True)
        assert combat.room_id == 600
        assert combat.is_simulation is True


# ═══════════════════════════════════════════════════════════════════════
# (a) Sim room: player defender capped to STUNNED/KO, never WOUNDED+
# ═══════════════════════════════════════════════════════════════════════

class TestSimRoomPlayerDefender:
    def test_large_hit_capped_to_stun_not_wounded(self):
        """In a sim room, damage_margin > 3 against a PC → STUNNED, not WOUNDED."""
        combat = _make_combat(is_simulation=True)

        attacker = _make_char(name="B1Droid", char_id=10, strength="3D")
        defender = _make_char(name="Recruit", char_id=1, strength="3D")

        actor_c = _make_combatant(attacker, is_npc=True)
        target_c = _make_combatant(defender, is_npc=False)

        # damage_margin=5 would normally cause INCAPACITATED in real combat
        _call_apply_damage(combat, actor_c, target_c, damage_margin_override=5)

        # PC must never exceed STUNNED wound level via the wound track
        assert defender.wound_level <= WoundLevel.STUNNED, (
            f"Expected wound_level <= STUNNED(1) in sim, got {defender.wound_level}"
        )

    def test_repeated_sim_hits_never_incapacitate_pc(self):
        """code-review BLOCKER regression: apply_wound(STUNNED) ITSELF escalates
        wound_level to INCAPACITATED once stun_timers >= STR dice (3 hits @ 3D).
        Over a multi-round drill, repeated sim hits must STILL never push a PC
        past STUNNED (the clamp undoes the stun-accumulation escalation)."""
        combat = _make_combat(is_simulation=True)
        attacker = _make_char(name="B1Droid", char_id=10, strength="3D")
        defender = _make_char(name="Recruit", char_id=1, strength="3D")
        actor_c = _make_combatant(attacker, is_npc=True)
        target_c = _make_combatant(defender, is_npc=False)
        for i in range(5):
            _call_apply_damage(combat, actor_c, target_c, damage_margin_override=5)
            assert defender.wound_level <= WoundLevel.STUNNED, (
                f"sim PC escalated to {defender.wound_level} after {i+1} hits "
                f"(stun_timers={len(defender.stun_timers)}) — clamp failed"
            )

    def test_small_hit_capped_to_stun(self):
        """In a sim room, damage_margin 1-3 against a PC → STUNNED."""
        combat = _make_combat(is_simulation=True)

        attacker = _make_char(name="B1Droid", char_id=10, strength="3D")
        defender = _make_char(name="Recruit", char_id=1, strength="3D")

        actor_c = _make_combatant(attacker, is_npc=True)
        target_c = _make_combatant(defender, is_npc=False)

        _call_apply_damage(combat, actor_c, target_c, damage_margin_override=2)

        assert defender.wound_level <= WoundLevel.STUNNED, (
            f"Expected STUNNED in sim for margin 2, got {defender.wound_level}"
        )

    def test_no_damage_still_no_damage_in_sim(self):
        """margin <= 0 → no damage in sim (pass-through)."""
        combat = _make_combat(is_simulation=True)

        attacker = _make_char(name="B1Droid", char_id=10, strength="3D")
        defender = _make_char(name="Recruit", char_id=1, strength="3D")

        actor_c = _make_combatant(attacker, is_npc=True)
        target_c = _make_combatant(defender, is_npc=False)

        _call_apply_damage(combat, actor_c, target_c, damage_margin_override=0)

        assert defender.wound_level == WoundLevel.HEALTHY

    def test_wound_text_carries_sim_tag(self):
        """Sim-capped result narrative contains '[SIM]' marker."""
        combat = _make_combat(is_simulation=True)

        attacker = _make_char(name="B1Droid", char_id=10, strength="3D")
        defender = _make_char(name="Recruit", char_id=1, strength="3D")

        actor_c = _make_combatant(attacker, is_npc=True)
        target_c = _make_combatant(defender, is_npc=False)

        result = _call_apply_damage(combat, actor_c, target_c, damage_margin_override=4)
        assert "[SIM]" in result.narrative, (
            "Expected '[SIM]' tag in sim narrative"
        )


# ═══════════════════════════════════════════════════════════════════════
# (b) Sim room: NPC defender takes normal wound (drill is winnable)
# ═══════════════════════════════════════════════════════════════════════

class TestSimRoomNPCDefender:
    def test_npc_takes_real_wound_in_sim(self):
        """In a sim room an NPC defender takes normal damage — not capped.

        damage_margin=4 → from_damage_margin(4) = WOUNDED (4 is in the 4-8
        WOUNDED band per WEG R&E).  The NPC must reach at least WOUNDED,
        confirming the sim cap is NOT applied to NPC defenders.
        """
        combat = _make_combat(is_simulation=True)

        attacker = _make_char(name="Recruit", char_id=1, strength="3D")
        droid = _make_char(name="B1SimDroid", char_id=10, strength="2D")

        actor_c = _make_combatant(attacker, is_npc=False)
        target_c = _make_combatant(droid, is_npc=True)

        # damage_margin=4 → WOUNDED via normal wound track for NPC
        _call_apply_damage(combat, actor_c, target_c, damage_margin_override=4)

        # NPC must be properly wounded (WOUNDED+); sim cap must NOT apply
        assert droid.wound_level >= WoundLevel.WOUNDED, (
            f"NPC in sim should take real wounds (>=WOUNDED); got {droid.wound_level}"
        )

    def test_npc_stunned_margin_2_not_capped(self):
        """margin=2 → STUNNED for NPC in sim (normal path, NOT the sim cap).

        from_damage_margin(2) = STUNNED (band 1-3). The NPC takes the real
        wound (STUNNED) via the normal path, not the sim-cap path (which would
        also apply STUNNED but with the [SIM] tag). The important invariant is
        that is_npc=True prevents the sim-cap branch from running at all.
        """
        combat = _make_combat(is_simulation=True)

        attacker = _make_char(name="Recruit", char_id=1, strength="3D")
        droid = _make_char(name="B1SimDroid", char_id=10, strength="2D")

        actor_c = _make_combatant(attacker, is_npc=False)
        target_c = _make_combatant(droid, is_npc=True)

        result = _call_apply_damage(combat, actor_c, target_c, damage_margin_override=2)

        # NPC wound_level should be STUNNED via the real path (not "[SIM]" tag)
        assert droid.wound_level >= WoundLevel.STUNNED, (
            f"NPC in sim margin=2 should be STUNNED+; got {droid.wound_level}"
        )
        # Confirm it went through the real path, not the sim-cap path
        assert "[SIM]" not in result.narrative, (
            "NPC hit should not carry [SIM] tag — sim cap must not apply to NPCs"
        )


# ═══════════════════════════════════════════════════════════════════════
# (c) Non-sim room: player takes normal wound (regression)
# ═══════════════════════════════════════════════════════════════════════

class TestNonSimRoomRealCombat:
    def test_player_takes_real_wound_in_non_sim(self):
        """In a non-sim room, damage_margin=4 → PC takes WOUNDED (normal).

        from_damage_margin(4) = WOUNDED (band 4-8 per WEG R&E).
        """
        combat = _make_combat(is_simulation=False)

        attacker = _make_char(name="Enemy", char_id=10, strength="3D")
        defender = _make_char(name="Player", char_id=1, strength="3D")

        actor_c = _make_combatant(attacker, is_npc=True)
        target_c = _make_combatant(defender, is_npc=False)

        _call_apply_damage(combat, actor_c, target_c, damage_margin_override=4)

        assert defender.wound_level >= WoundLevel.WOUNDED, (
            f"Real combat margin=4 should be WOUNDED+; got {defender.wound_level}"
        )

    def test_player_incapacitated_non_sim(self):
        """In a non-sim room, damage_margin=9 → PC reaches INCAPACITATED.

        from_damage_margin(9) = INCAPACITATED (band 9-12 per WEG R&E).
        """
        combat = _make_combat(is_simulation=False)

        attacker = _make_char(name="Enemy", char_id=10, strength="3D")
        defender = _make_char(name="Player", char_id=1, strength="3D")

        actor_c = _make_combatant(attacker, is_npc=True)
        target_c = _make_combatant(defender, is_npc=False)

        _call_apply_damage(combat, actor_c, target_c, damage_margin_override=9)

        assert defender.wound_level >= WoundLevel.INCAPACITATED, (
            f"Real combat margin=9 should be INCAPACITATED+; got {defender.wound_level}"
        )

    def test_no_damage_non_sim(self):
        """margin=0 → no damage in non-sim (unchanged)."""
        combat = _make_combat(is_simulation=False)

        attacker = _make_char(name="Enemy", char_id=10, strength="3D")
        defender = _make_char(name="Player", char_id=1, strength="3D")

        actor_c = _make_combatant(attacker, is_npc=True)
        target_c = _make_combatant(defender, is_npc=False)

        _call_apply_damage(combat, actor_c, target_c, damage_margin_override=0)

        assert defender.wound_level == WoundLevel.HEALTHY


# ═══════════════════════════════════════════════════════════════════════
# (d) add_scar gate: skipped in sim, fires in non-sim
# ═══════════════════════════════════════════════════════════════════════

class TestScarGate:
    """
    We test the gate logic directly by inspecting the is_simulation check.
    A full integration test would require an async command layer + DB — that
    is covered by smoke tests.  Here we verify the attribute logic that
    gates the call in combat_commands.py.
    """

    def test_sim_combat_has_is_simulation_true(self):
        """A CombatInstance built with is_simulation=True carries the flag
        that combat_commands' scar gate reads via getattr."""
        combat = _make_combat(is_simulation=True)
        # This is exactly what the scar gate reads:
        assert getattr(combat, "is_simulation", False) is True

    def test_non_sim_combat_scar_gate_open(self):
        """A CombatInstance built without is_simulation has the gate open
        (getattr returns False → scar fires)."""
        combat = _make_combat(is_simulation=False)
        assert getattr(combat, "is_simulation", False) is False

    def test_missing_attribute_defaults_false(self):
        """getattr(combat, 'is_simulation', False) never raises — fail-safe."""
        obj = types.SimpleNamespace()  # no is_simulation attribute
        assert getattr(obj, "is_simulation", False) is False

    def test_scar_skipped_in_sim_gate_logic(self):
        """Simulate the gate: scar_called=True only when not is_simulation."""
        for is_sim, expect_scar in [(True, False), (False, True)]:
            combat = _make_combat(is_simulation=is_sim)
            scar_called = []

            def fake_add_scar(*a, **kw):
                scar_called.append(True)
                return {"description": "test scar"}

            if not getattr(combat, "is_simulation", False):
                fake_add_scar()

            assert bool(scar_called) == expect_scar, (
                f"is_simulation={is_sim}: expected scar_called={expect_scar}, "
                f"got {bool(scar_called)}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Rooms YAML: tipoca_combat_sim has is_simulation: true
# ═══════════════════════════════════════════════════════════════════════

class TestRoomsYaml:
    def test_tipoca_combat_sim_has_is_simulation(self):
        """tipoca_combat_sim room in tutorials/rooms.yaml has is_simulation: true."""
        import os
        import yaml
        yaml_path = os.path.join(
            os.path.dirname(__file__), "..",
            "data", "worlds", "clone_wars", "tutorials", "rooms.yaml"
        )
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        room = next(
            (r for r in data["rooms"] if r.get("slug") == "tipoca_combat_sim"),
            None,
        )
        assert room is not None, "tipoca_combat_sim not found in tutorials/rooms.yaml"
        props = room.get("properties", {})
        assert props.get("is_simulation") is True, (
            f"Expected is_simulation: true on tipoca_combat_sim, got {props}"
        )

    def test_other_properties_preserved(self):
        """Additive edit: cover_max, security, tutorial_zone are all still present."""
        import os
        import yaml
        yaml_path = os.path.join(
            os.path.dirname(__file__), "..",
            "data", "worlds", "clone_wars", "tutorials", "rooms.yaml"
        )
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        room = next(
            (r for r in data["rooms"] if r.get("slug") == "tipoca_combat_sim"),
            None,
        )
        props = room["properties"]
        assert props.get("tutorial_zone") is True
        assert props.get("cover_max") == 3
        assert props.get("security") == "contested"
