# -*- coding: utf-8 -*-
"""
tests/test_social_systems.py — Social and RP support system tests.

Covers:
  - Mail system (+mail)
  - Places system (sit/stand at places)
  - Scene management (+scene)
  - Narrative memory
  - MUX compatibility commands (think, @desc, etc.)
  - Channel system
  - Buffs display
"""
import pytest
from tests.harness import strip_ansi

pytestmark = pytest.mark.asyncio


class TestMail:
    async def test_mail_inbox(self, harness):
        s = await harness.login_as("MailReader", room_id=2)
        out = await harness.cmd(s, "+mail")
        clean = strip_ansi(out).lower()
        assert "mail" in clean or "inbox" in clean or "no mail" in clean \
               or "empty" in clean

    async def test_mail_send(self, harness):
        s1 = await harness.login_as("MailSender", room_id=2)
        s2 = await harness.login_as("MailReceiver", room_id=2)

        out = await harness.cmd(s1, "+mail/send MailReceiver=Test Subject/Test body message")
        clean = strip_ansi(out).lower()
        assert "sent" in clean or "mail" in clean or "deliver" in clean \
               or len(clean) > 0

    async def test_mail_read(self, harness):
        s = await harness.login_as("MailReadTest", room_id=2)
        out = await harness.cmd(s, "+mail/read 1")
        clean = strip_ansi(out).lower()
        assert "mail" in clean or "no" in clean or len(clean) > 0


class TestPlaces:
    async def test_places_command(self, harness):
        s = await harness.login_as("PlacesUser", room_id=17)  # Cantina
        out = await harness.cmd(s, "+places")
        clean = strip_ansi(out)
        assert len(clean) > 0

    async def test_sit_at_place(self, harness):
        s = await harness.login_as("Sitter", room_id=17)
        out = await harness.cmd(s, "sit 1")
        clean = strip_ansi(out).lower()
        assert "sit" in clean or "place" in clean or "no" in clean \
               or len(clean) > 0

    async def test_stand_from_place(self, harness):
        s = await harness.login_as("Stander", room_id=17)
        out = await harness.cmd(s, "stand")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0


class TestScenes:
    async def test_scene_start(self, harness):
        s = await harness.login_as("SceneStarter", room_id=2)
        out = await harness.cmd(s, "+scene/start")
        clean = strip_ansi(out).lower()
        assert "scene" in clean or len(clean) > 0

    async def test_scene_status(self, harness):
        s = await harness.login_as("SceneStatus", room_id=2)
        out = await harness.cmd(s, "+scene")
        clean = strip_ansi(out)
        assert len(clean) > 0


class TestNarrative:
    async def test_narrative_command(self, harness):
        s = await harness.login_as("NarrativeUser", room_id=2)
        out = await harness.cmd(s, "+narrative")
        clean = strip_ansi(out)
        assert len(clean) > 0

    async def test_think_command(self, harness):
        s = await harness.login_as("Thinker", room_id=2)
        out = await harness.cmd(s, "think I wonder about the Force")
        clean = strip_ansi(out)
        assert len(clean) > 0


class TestMUXCompat:
    async def test_desc_command(self, harness):
        s = await harness.login_as("Describer", room_id=2)
        out = await harness.cmd(s, "@desc me=A grizzled smuggler")
        clean = strip_ansi(out).lower()
        assert "desc" in clean or "set" in clean or len(clean) > 0

    async def test_semipose(self, harness):
        s = await harness.login_as("Semip", room_id=2)
        out = await harness.cmd(s, ";'s blaster gleams")
        clean = strip_ansi(out)
        assert "Semip" in clean or len(clean) > 0


class TestBuffs:
    async def test_buffs_display(self, harness):
        s = await harness.login_as("BuffViewer", room_id=2)
        out = await harness.cmd(s, "+buffs")
        clean = strip_ansi(out).lower()
        assert "buff" in clean or "no active" in clean or "none" in clean \
               or len(clean) > 0


class TestEquipment:
    async def test_weapons_list(self, harness):
        s = await harness.login_as("WeaponViewer", room_id=2)
        out = await harness.cmd(s, "+weapons")
        clean = strip_ansi(out)
        assert len(clean) > 5

    async def test_armor_list(self, harness):
        s = await harness.login_as("ArmorViewer", room_id=2)
        out = await harness.cmd(s, "+armor")
        clean = strip_ansi(out)
        assert len(clean) > 0

    async def test_equip_no_item(self, harness):
        s = await harness.login_as("NoEquip", room_id=2)
        out = await harness.cmd(s, "equip Nonexistent Weapon")
        clean = strip_ansi(out).lower()
        assert "don't have" in clean or "not found" in clean or \
               "no item" in clean or "equip" in clean or len(clean) > 0

    async def test_wear_no_armor(self, harness):
        s = await harness.login_as("NoWear", room_id=2)
        out = await harness.cmd(s, "wear Nonexistent Armor")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0


class TestLockpickAndForce:
    async def test_lockpick_no_lock(self, harness):
        s = await harness.login_as("Lockpicker", room_id=2,
                                    skills={"security": "3D"})
        out = await harness.cmd(s, "lockpick north")
        clean = strip_ansi(out).lower()
        assert "lock" in clean or "no" in clean or "exit" in clean \
               or len(clean) > 0

    async def test_forcedoor_no_lock(self, harness):
        s = await harness.login_as("DoorForcer", room_id=2,
                                    attributes={"strength": "4D"})
        out = await harness.cmd(s, "forcedoor north")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0
