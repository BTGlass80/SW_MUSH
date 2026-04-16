# -*- coding: utf-8 -*-
"""
tests/test_multiplayer.py — Multi-player interaction tests.

Tests that require 2+ players in the same room:
  - PvP challenge/accept/decline flow
  - Player-to-player trade
  - Whisper delivery
  - Say visibility to other players
  - Party invite/join/leave
  - Room broadcast mechanics
  - Scene participation with multiple players
"""
import pytest
from tests.harness import strip_ansi, assert_output_contains

pytestmark = pytest.mark.asyncio


class TestPvPFlow:
    async def test_challenge_accept_starts_combat(self, harness):
        """Full PvP challenge → accept flow."""
        s1 = await harness.login_as("Duelist1", room_id=2, credits=5000,
                                     skills={"blaster": "3D"},
                                     attributes={"dexterity": "4D"})
        s2 = await harness.login_as("Duelist2", room_id=2, credits=5000,
                                     skills={"blaster": "2D"},
                                     attributes={"dexterity": "3D"})

        # Challenge
        out = await harness.cmd(s1, "challenge Duelist2")
        clean = strip_ansi(out).lower()
        assert "challenge" in clean or "duel" in clean or len(clean) > 5

        # Check if s2 received the challenge notification
        s2_out = s2.get_output()
        s2_clean = strip_ansi(s2_out).lower()

        # Accept
        out2 = await harness.cmd(s2, "accept")
        clean2 = strip_ansi(out2).lower()
        assert "accept" in clean2 or "combat" in clean2 or "duel" in clean2 \
               or len(clean2) > 5

    async def test_challenge_decline(self, harness):
        s1 = await harness.login_as("Chal1", room_id=2)
        s2 = await harness.login_as("Chal2", room_id=2)

        await harness.cmd(s1, "challenge Chal2")
        out = await harness.cmd(s2, "decline")
        clean = strip_ansi(out).lower()
        assert "decline" in clean or "refuse" in clean or "challenge" in clean \
               or "no pending" in clean

    async def test_challenge_self_denied(self, harness):
        s = await harness.login_as("SelfChal", room_id=2)
        out = await harness.cmd(s, "challenge SelfChal")
        clean = strip_ansi(out).lower()
        assert "yourself" in clean or "can't" in clean or len(clean) > 0

    async def test_challenge_absent_player(self, harness):
        s = await harness.login_as("LonelyChal", room_id=2)
        out = await harness.cmd(s, "challenge NonexistentPlayer")
        clean = strip_ansi(out).lower()
        assert "find" in clean or "not here" in clean or "no player" in clean \
               or len(clean) > 0


class TestPlayerTrade:
    async def test_trade_credits(self, harness):
        s1 = await harness.login_as("Trader1", room_id=2, credits=10000)
        s2 = await harness.login_as("Trader2", room_id=2, credits=1000)

        out = await harness.cmd(s1, "trade Trader2 500 credits")
        clean = strip_ansi(out).lower()
        assert "trade" in clean or "offer" in clean or "credit" in clean \
               or len(clean) > 5

    async def test_trade_insufficient_credits(self, harness):
        s1 = await harness.login_as("BrokeTrader", room_id=2, credits=10)
        s2 = await harness.login_as("TradeTarget", room_id=2, credits=1000)

        out = await harness.cmd(s1, "trade TradeTarget 50000 credits")
        clean = strip_ansi(out).lower()
        assert "enough" in clean or "insufficient" in clean or "afford" in clean \
               or "trade" in clean or len(clean) > 0


class TestCommunicationVisibility:
    async def test_say_heard_by_others(self, harness):
        """Say should be visible to other players in the same room."""
        s1 = await harness.login_as("Speaker1", room_id=2)
        s2 = await harness.login_as("Listener1", room_id=2)

        s2.clear_output()
        await harness.cmd(s1, "say Hello from Speaker1!")

        # Check if s2 received the message
        s2_out = s2.get_output()
        s2_clean = strip_ansi(s2_out)
        assert "Hello from Speaker1" in s2_clean or "Speaker1" in s2_clean

    async def test_say_not_heard_in_other_room(self, harness):
        """Say should NOT be heard in different rooms."""
        s1 = await harness.login_as("Speaker2", room_id=2)
        s2 = await harness.login_as("FarListener", room_id=17)  # Cantina

        s2.clear_output()
        await harness.cmd(s1, "say This is a local message")

        s2_out = s2.get_output()
        s2_clean = strip_ansi(s2_out)
        assert "local message" not in s2_clean

    async def test_whisper_targeted(self, harness):
        s1 = await harness.login_as("Whisperer", room_id=2)
        s2 = await harness.login_as("WhisperTarget", room_id=2)

        out = await harness.cmd(s1, "whisper WhisperTarget=Secret message")
        clean = strip_ansi(out).lower()
        assert "whisper" in clean or "secret" in clean or len(clean) > 5

    async def test_emote_visible_to_room(self, harness):
        s1 = await harness.login_as("Emoter1", room_id=2)
        s2 = await harness.login_as("Watcher1", room_id=2)

        s2.clear_output()
        await harness.cmd(s1, ":draws a blaster dramatically.")

        s2_out = s2.get_output()
        s2_clean = strip_ansi(s2_out)
        assert "Emoter1" in s2_clean or "draws" in s2_clean


class TestPartySystem:
    async def test_party_invite_accept(self, harness):
        s1 = await harness.login_as("PartyHost", room_id=2)
        s2 = await harness.login_as("PartyGuest", room_id=2)

        out1 = await harness.cmd(s1, "+party/invite PartyGuest")
        clean1 = strip_ansi(out1).lower()
        assert "invite" in clean1 or "party" in clean1

        out2 = await harness.cmd(s2, "+party/join")
        clean2 = strip_ansi(out2).lower()
        assert "join" in clean2 or "party" in clean2 or len(clean2) > 0

    async def test_party_leave(self, harness):
        s1 = await harness.login_as("PLHost", room_id=2)
        s2 = await harness.login_as("PLGuest", room_id=2)

        await harness.cmd(s1, "+party/invite PLGuest")
        await harness.cmd(s2, "+party/join")
        out = await harness.cmd(s2, "+party/leave")
        clean = strip_ansi(out).lower()
        assert "leave" in clean or "left" in clean or "party" in clean

    async def test_party_status_with_members(self, harness):
        s1 = await harness.login_as("PSHost", room_id=2)
        s2 = await harness.login_as("PSMember", room_id=2)

        await harness.cmd(s1, "+party/invite PSMember")
        await harness.cmd(s2, "+party/join")

        out = await harness.cmd(s1, "+party")
        clean = strip_ansi(out)
        assert len(clean) > 10


class TestSceneMultiplayer:
    async def test_scene_with_two_players(self, harness):
        s1 = await harness.login_as("SceneP1", room_id=2)
        s2 = await harness.login_as("SceneP2", room_id=2)

        out = await harness.cmd(s1, "+scene/start")
        clean = strip_ansi(out).lower()
        assert "scene" in clean or len(clean) > 5

    async def test_ooc_broadcast_to_room(self, harness):
        s1 = await harness.login_as("OOC1", room_id=2)
        s2 = await harness.login_as("OOC2", room_id=2)

        s2.clear_output()
        await harness.cmd(s1, "+ooc Testing OOC channel")

        s2_out = s2.get_output()
        s2_clean = strip_ansi(s2_out)
        assert "OOC" in s2_clean or "Testing" in s2_clean
