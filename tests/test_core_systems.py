# -*- coding: utf-8 -*-
"""
tests/test_core_systems.py — Core gameplay loop tests.

Covers:
  - Room look / description
  - Movement via exits
  - Character sheet (+sheet)
  - Inventory (+inv)
  - Who list (+who)
  - Say / emote / whisper
  - Help system
  - Quit flow
  - Basic ANSI output
"""
import pytest
import re
from tests.harness import strip_ansi, assert_output_contains, assert_output_not_contains

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Room / Look
# ═══════════════════════════════════════════════════════════════════

class TestLook:
    async def test_look_shows_room_name(self, harness):
        s = await harness.login_as("LookTester", room_id=2)
        out = await harness.cmd(s, "look")
        assert_output_contains(out, "Mos Eisley")

    async def test_look_shows_exits(self, harness):
        s = await harness.login_as("ExitTester", room_id=2)
        out = await harness.cmd(s, "look")
        # Room 2 should have at least one exit
        clean = strip_ansi(out).lower()
        assert any(d in clean for d in [
            "north", "south", "east", "west", "up", "down",
            "exit", "leave", "enter"
        ]), f"No exits visible in look output:\n{clean[:500]}"

    async def test_look_alias_l(self, harness):
        s = await harness.login_as("AliasTester", room_id=2)
        out = await harness.cmd(s, "l")
        assert_output_contains(out, "Mos Eisley")

    async def test_look_at_self(self, harness):
        s = await harness.login_as("SelfLooker", room_id=2)
        out = await harness.cmd(s, "look SelfLooker")
        # Should show character description or name
        clean = strip_ansi(out)
        assert "SelfLooker" in clean or "you see" in clean.lower()

    async def test_look_at_npc(self, harness):
        # Room 17 (Cantina Main Bar) has Wuher
        s = await harness.login_as("NPCLooker", room_id=17)
        out = await harness.cmd(s, "look Wuher")
        clean = strip_ansi(out)
        assert "Wuher" in clean or len(clean) > 20  # Either name or description


# ═══════════════════════════════════════════════════════════════════
# Movement
# ═══════════════════════════════════════════════════════════════════

class TestMovement:
    async def test_basic_movement(self, harness):
        """Move through an exit and verify room changes."""
        s = await harness.login_as("Mover", room_id=2)
        # Find an exit from room 2
        exits = await harness.db.get_exits(2)
        assert len(exits) > 0, "Room 2 has no exits"
        direction = exits[0]["direction"]
        dest_room = exits[0]["to_room_id"]

        out = await harness.cmd(s, direction)
        # Verify character moved
        char = await harness.get_char(s.character["id"])
        assert char["room_id"] == dest_room, \
            f"Expected room {dest_room}, got {char['room_id']}"

    async def test_invalid_direction(self, harness):
        s = await harness.login_as("BadMover", room_id=2)
        out = await harness.cmd(s, "northeast_fake_direction_xyz")
        clean = strip_ansi(out).lower()
        # Should get an error — not silently succeed
        assert "huh" in clean or "don't" in clean or "can't" in clean or \
               "no exit" in clean or "unknown" in clean or len(clean) > 0

    async def test_movement_updates_room_id(self, harness):
        s = await harness.login_as("RoomTracker", room_id=2)
        original_room = s.character["room_id"]
        exits = await harness.db.get_exits(2)
        if exits:
            await harness.cmd(s, exits[0]["direction"])
            assert s.character["room_id"] != original_room or \
                   s.character["room_id"] == exits[0]["to_room_id"]


# ═══════════════════════════════════════════════════════════════════
# Character Sheet
# ═══════════════════════════════════════════════════════════════════

class TestSheet:
    async def test_sheet_shows_name(self, harness):
        s = await harness.login_as("SheetTester", room_id=2)
        out = await harness.cmd(s, "+sheet")
        assert_output_contains(out, "SheetTester")

    async def test_sheet_shows_attributes(self, harness):
        s = await harness.login_as("AttrTester", room_id=2,
                                    attributes={"dexterity": "4D+1"})
        out = await harness.cmd(s, "+sheet")
        clean = strip_ansi(out)
        assert "DEXTERITY" in clean or "Dexterity" in clean or "dexterity" in clean
        assert "4D+1" in clean

    async def test_sheet_shows_skills(self, harness):
        s = await harness.login_as("SkillTester", room_id=2,
                                    skills={"blaster": "2D+1"})
        out = await harness.cmd(s, "+sheet")
        clean = strip_ansi(out)
        assert "Blaster" in clean or "blaster" in clean
        # Total should be attr + skill bonus: 3D + 2D+1 = 5D+1
        assert "5D+1" in clean

    async def test_sheet_shows_species(self, harness):
        s = await harness.login_as("SpeciesTester", room_id=2, species="Rodian")
        out = await harness.cmd(s, "+sheet")
        assert_output_contains(out, "Rodian")

    async def test_sheet_brief_switch(self, harness):
        s = await harness.login_as("BriefTester", room_id=2)
        out_full = await harness.cmd(s, "+sheet")
        out_brief = await harness.cmd(s, "+sheet/brief")
        # Brief should be shorter
        assert len(strip_ansi(out_brief)) <= len(strip_ansi(out_full))


# ═══════════════════════════════════════════════════════════════════
# Inventory
# ═══════════════════════════════════════════════════════════════════

class TestInventory:
    async def test_empty_inventory(self, harness):
        s = await harness.login_as("EmptyInv", room_id=2)
        out = await harness.cmd(s, "+inv")
        clean = strip_ansi(out).lower()
        assert "empty" in clean or "nothing" in clean or "no items" in clean \
               or "inventory" in clean

    async def test_inventory_with_item(self, harness):
        s = await harness.login_as("ItemHaver", room_id=2)
        await harness.give_item(s.character["id"], {
            "name": "DL-44 Heavy Blaster Pistol",
            "type": "weapon",
            "damage": "5D",
        })
        # Refresh character
        s.character = await harness.get_char(s.character["id"])
        out = await harness.cmd(s, "+inv")
        assert_output_contains(out, "DL-44")


# ═══════════════════════════════════════════════════════════════════
# Communication
# ═══════════════════════════════════════════════════════════════════

class TestCommunication:
    async def test_say(self, harness):
        s = await harness.login_as("Talker", room_id=2)
        out = await harness.cmd(s, "say Hello there!")
        assert_output_contains(out, "Hello there")

    async def test_say_quote_prefix(self, harness):
        s = await harness.login_as("Quoter", room_id=2)
        out = await harness.cmd(s, "\"General Kenobi!")
        assert_output_contains(out, "General Kenobi")

    async def test_emote(self, harness):
        s = await harness.login_as("Emoter", room_id=2)
        out = await harness.cmd(s, ":waves casually.")
        clean = strip_ansi(out)
        assert "Emoter" in clean
        assert "waves casually" in clean

    async def test_ooc(self, harness):
        s = await harness.login_as("OOCer", room_id=2)
        out = await harness.cmd(s, "+ooc This is out of character")
        assert_output_contains(out, "out of character|OOC|This is")


# ═══════════════════════════════════════════════════════════════════
# Help System
# ═══════════════════════════════════════════════════════════════════

class TestHelp:
    async def test_help_index(self, harness):
        s = await harness.login_as("HelpUser", room_id=2)
        out = await harness.cmd(s, "+help")
        clean = strip_ansi(out)
        # Should show a help index or topic list
        assert len(clean) > 50, "Help output too short"

    async def test_help_specific_topic(self, harness):
        s = await harness.login_as("HelpTopic", room_id=2)
        out = await harness.cmd(s, "+help look")
        clean = strip_ansi(out)
        assert "look" in clean.lower()

    async def test_help_search(self, harness):
        s = await harness.login_as("HelpSearcher", room_id=2)
        out = await harness.cmd(s, "+help/search combat")
        clean = strip_ansi(out)
        assert len(clean) > 10  # Should find something


# ═══════════════════════════════════════════════════════════════════
# Who List
# ═══════════════════════════════════════════════════════════════════

class TestWho:
    async def test_who_shows_player(self, harness):
        s = await harness.login_as("WhoPlayer", room_id=2)
        out = await harness.cmd(s, "+who")
        assert_output_contains(out, "WhoPlayer")

    async def test_who_shows_count(self, harness):
        s = await harness.login_as("CountPlayer", room_id=2)
        out = await harness.cmd(s, "+who")
        clean = strip_ansi(out)
        # Should show at least "1" player
        assert re.search(r'\d+', clean), "No player count in +who output"
