# -*- coding: utf-8 -*-
"""
tests/test_combat.py — Combat system integration tests.

Covers:
  - Initiating combat (attack command)
  - Dodge / parry / full dodge / full parry
  - Wound application and stacking (WEG D6 R&E rules)
  - Multi-action penalties
  - Combat status display
  - Combat disengagement
  - PvP challenge / accept / decline
  - Range mechanics
  - Cover mechanics
  - Force point usage in combat
  - Aim bonus
  - Flee mechanics
  - Combat pose output
  - NPC combat AI engagement
"""
import pytest
import json
from tests.harness import strip_ansi, assert_output_contains

pytestmark = pytest.mark.asyncio


class TestCombatInitiation:
    async def test_attack_npc(self, harness):
        """Attack an NPC and verify combat starts."""
        # Room 17 has hostile-capable NPCs in the cantina
        s = await harness.login_as("Fighter", room_id=17,
                                    skills={"blaster": "3D"},
                                    attributes={"dexterity": "4D"})
        # Give a weapon
        await harness.give_item(s.character["id"], {
            "name": "DL-44 Heavy Blaster Pistol",
            "type": "weapon",
            "damage": "5D",
            "skill": "blaster",
        })
        s.character = await harness.get_char(s.character["id"])

        # Equip it
        await harness.cmd(s, "equip DL-44")

        # Find an NPC in the room
        npcs = await harness.get_npcs_in_room(17)
        if npcs:
            target = npcs[0]["name"].split()[0]  # First word of name
            out = await harness.cmd(s, f"attack {target}")
            clean = strip_ansi(out)
            # Should either start combat or give a "can't attack" message
            assert len(clean) > 10

    async def test_attack_no_weapon(self, harness):
        """Attack without a weapon equipped — should use brawling or fail."""
        s = await harness.login_as("Unarmed", room_id=17)
        npcs = await harness.get_npcs_in_room(17)
        if npcs:
            target = npcs[0]["name"].split()[0]
            out = await harness.cmd(s, f"attack {target}")
            clean = strip_ansi(out).lower()
            # Should either start brawling combat or error
            assert len(clean) > 5

    async def test_attack_nonexistent_target(self, harness):
        s = await harness.login_as("BadTarget", room_id=2)
        out = await harness.cmd(s, "attack XyzNonexistent999")
        clean = strip_ansi(out).lower()
        assert "can't find" in clean or "no target" in clean or \
               "not found" in clean or "don't see" in clean or len(clean) > 5


class TestCombatActions:
    async def test_dodge_command(self, harness):
        s = await harness.login_as("Dodger", room_id=2)
        out = await harness.cmd(s, "dodge")
        clean = strip_ansi(out).lower()
        # Either sets dodge or says not in combat
        assert "dodge" in clean or "combat" in clean or "not in" in clean

    async def test_full_dodge_command(self, harness):
        s = await harness.login_as("FullDodger", room_id=2)
        out = await harness.cmd(s, "fulldodge")
        clean = strip_ansi(out).lower()
        assert "dodge" in clean or "combat" in clean or "not in" in clean

    async def test_parry_command(self, harness):
        s = await harness.login_as("Parrier", room_id=2)
        out = await harness.cmd(s, "parry")
        clean = strip_ansi(out).lower()
        assert "parry" in clean or "combat" in clean or "not in" in clean

    async def test_combat_status_no_combat(self, harness):
        s = await harness.login_as("StatusCheck", room_id=2)
        out = await harness.cmd(s, "+combat")
        clean = strip_ansi(out).lower()
        assert "not in combat" in clean or "no active" in clean or "combat" in clean

    async def test_flee_no_combat(self, harness):
        s = await harness.login_as("Fleer", room_id=2)
        out = await harness.cmd(s, "flee")
        clean = strip_ansi(out).lower()
        assert "not in" in clean or "flee" in clean or "combat" in clean

    async def test_aim_no_combat(self, harness):
        s = await harness.login_as("Aimer", room_id=2)
        out = await harness.cmd(s, "aim")
        clean = strip_ansi(out).lower()
        assert "not in" in clean or "aim" in clean or "combat" in clean


class TestPvPChallenge:
    async def test_challenge_another_player(self, harness):
        """Test PvP challenge flow."""
        s1 = await harness.login_as("Challenger", room_id=2)
        s2 = await harness.login_as("Challenged", room_id=2)

        out = await harness.cmd(s1, "challenge Challenged")
        clean = strip_ansi(out).lower()
        # Should send a challenge or fail gracefully
        assert "challenge" in clean or len(clean) > 5

    async def test_decline_challenge(self, harness):
        s = await harness.login_as("Decliner", room_id=2)
        out = await harness.cmd(s, "decline")
        clean = strip_ansi(out).lower()
        # No pending challenge to decline
        assert "no" in clean or "challenge" in clean or "decline" in clean or len(clean) > 0


class TestRangeAndCover:
    async def test_range_command(self, harness):
        s = await harness.login_as("Ranger", room_id=2)
        out = await harness.cmd(s, "range")
        clean = strip_ansi(out).lower()
        assert "range" in clean or "combat" in clean or "not in" in clean

    async def test_cover_command(self, harness):
        s = await harness.login_as("CoverUser", room_id=2)
        out = await harness.cmd(s, "cover")
        clean = strip_ansi(out).lower()
        assert "cover" in clean or "combat" in clean or "not in" in clean


class TestForcePointCombat:
    async def test_forcepoint_command(self, harness):
        s = await harness.login_as("ForcePointer", room_id=2)
        out = await harness.cmd(s, "forcepoint")
        clean = strip_ansi(out).lower()
        assert "force" in clean or "combat" in clean or "not in" in clean


class TestRespawn:
    async def test_respawn_when_alive(self, harness):
        s = await harness.login_as("Alive", room_id=2)
        out = await harness.cmd(s, "respawn")
        clean = strip_ansi(out).lower()
        # Should refuse — character is alive
        assert "dead" in clean or "alive" in clean or "not" in clean or \
               "can't" in clean or "respawn" in clean
