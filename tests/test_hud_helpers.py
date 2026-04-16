# -*- coding: utf-8 -*-
"""
tests/test_hud_helpers.py — Tests for Phase 3 C2 send_hud_update decomposition.

Verifies that the extracted helper methods produce the same HUD payload
structure as the original monolithic send_hud_update.
"""

import json
import pytest


# ── Minimal stubs ──

class FakeSend:
    """Captures all messages sent via _send."""
    def __init__(self):
        self.messages = []

    async def __call__(self, data):
        self.messages.append(data)


def make_session(char=None):
    """Create a minimal Session for testing HUD helpers."""
    from server.session import Session, Protocol, SessionState
    sender = FakeSend()

    async def noop():
        pass

    s = Session(Protocol.WEBSOCKET, sender, noop)
    s.state = SessionState.IN_GAME
    s.character = char or {
        "id": 1,
        "name": "Test Char",
        "wound_level": 0,
        "credits": 5000,
        "_room_name": "Cantina",
        "room_id": 10,
        "force_points": 2,
        "character_points": 3,
        "dark_side_points": 0,
        "force_sensitive": False,
        "equipment": json.dumps({
            "weapon": {"name": "DL-44 Blaster", "damage": "4D", "type": "blaster"},
            "armor": {"name": "Blast Vest", "location": "torso", "bonus": "+1D"},
        }),
        "inventory": json.dumps([
            {"name": "Medpac", "type": "healing"},
            {"name": "Medpac", "type": "healing"},
            {"name": "Frag Grenade", "type": "grenade"},
        ]),
        "attributes": "{}",
    }
    return s, sender


# ── Tests ──

class TestHudBase:
    def test_base_payload_structure(self):
        s, _ = make_session()
        hud = s._hud_base()
        assert hud["character_id"] == 1
        assert hud["name"] == "Test Char"
        assert hud["credits"] == 5000
        assert hud["room_id"] == 10
        assert hud["wound_name"] == "healthy"
        assert hud["exits"] == []
        assert hud["zone_name"] == ""
        assert hud["loadout"] is None

    def test_base_wound_levels(self):
        for wl, expected in [(0, "healthy"), (1, "stunned"), (2, "wounded"),
                              (4, "incapacitated"), (5, "mortally wounded"),
                              (6, "dead")]:
            s, _ = make_session({"id": 1, "name": "X", "wound_level": wl,
                                  "credits": 0, "_room_name": "", "room_id": 1})
            hud = s._hud_base()
            assert hud["wound_name"] == expected, f"wound_level={wl}"


class TestHudEquippedWeapon:
    def test_weapon_from_equipment_json(self):
        s, _ = make_session()
        hud = s._hud_base()
        s._hud_equipped_weapon(hud)
        assert hud.get("equipped_weapon") == "DL-44 Blaster"

    def test_no_weapon(self):
        s, _ = make_session({"id": 1, "name": "X", "wound_level": 0,
                              "credits": 0, "_room_name": "", "room_id": 1})
        hud = s._hud_base()
        s._hud_equipped_weapon(hud)
        assert "equipped_weapon" not in hud

    def test_weapon_from_dict_equipment(self):
        s, _ = make_session({"id": 1, "name": "X", "wound_level": 0,
                              "credits": 0, "_room_name": "", "room_id": 1,
                              "equipment": {"weapon": {"name": "Vibroblade"}}})
        hud = s._hud_base()
        s._hud_equipped_weapon(hud)
        assert hud.get("equipped_weapon") == "Vibroblade"


class TestHudLoadout:
    def test_loadout_built(self):
        s, _ = make_session()
        hud = s._hud_base()
        s._hud_loadout(hud)
        assert hud["loadout"] is not None
        assert hud["loadout"]["weapon"]["name"] == "DL-44 Blaster"
        assert hud["loadout"]["armor"]["name"] == "Blast Vest"
        assert len(hud["loadout"]["consumables"]) >= 1


class TestHudRoomDescription:
    def test_with_desc_long(self):
        s, _ = make_session()
        hud = s._hud_base()
        room_row = {"desc_long": "A smoky cantina.", "desc_short": "Cantina"}
        s._hud_room_description(hud, room_row)
        assert hud["room_description"] == "A smoky cantina."

    def test_fallback_to_desc_short(self):
        s, _ = make_session()
        hud = s._hud_base()
        room_row = {"desc_long": None, "desc_short": "Cantina"}
        s._hud_room_description(hud, room_row)
        assert hud["room_description"] == "Cantina"

    def test_no_room_row(self):
        s, _ = make_session()
        hud = s._hud_base()
        s._hud_room_description(hud, None)
        assert hud["room_description"] == ""


class TestHudCreditEvent:
    @pytest.mark.asyncio
    async def test_credit_delta_sent(self):
        s, sender = make_session()
        s._last_sent_credits = 4000
        hud = {"credits": 5000}
        await s._hud_send_credit_event(hud)
        assert len(sender.messages) == 1
        msg = json.loads(sender.messages[0])
        assert msg["type"] == "credit_event"
        assert msg["delta"] == 1000
        assert msg["credits"] == 5000

    @pytest.mark.asyncio
    async def test_no_event_when_unchanged(self):
        s, sender = make_session()
        s._last_sent_credits = 5000
        hud = {"credits": 5000}
        await s._hud_send_credit_event(hud)
        assert len(sender.messages) == 0

    @pytest.mark.asyncio
    async def test_first_tick_no_event(self):
        s, sender = make_session()
        # _last_sent_credits is None on first tick
        hud = {"credits": 5000}
        await s._hud_send_credit_event(hud)
        assert len(sender.messages) == 0
        assert s._last_sent_credits == 5000


class TestHudActiveJobs:
    @pytest.mark.asyncio
    async def test_empty_when_no_jobs(self):
        s, _ = make_session()
        hud = {}
        # This will try to import mission/bounty/smuggling boards
        # which may not be initialized, but the try/except blocks
        # should handle it gracefully
        await s._hud_active_jobs(hud, s.character)
        assert "active_jobs" in hud
        assert isinstance(hud["active_jobs"], list)


class TestSendHudUpdateOrchestrator:
    @pytest.mark.asyncio
    async def test_telnet_session_skips(self):
        """Telnet sessions should return immediately."""
        from server.session import Session, Protocol, SessionState
        sender = FakeSend()
        async def noop(): pass
        s = Session(Protocol.TELNET, sender, noop)
        s.state = SessionState.IN_GAME
        s.character = {"id": 1, "name": "X"}
        await s.send_hud_update()
        assert len(sender.messages) == 0

    @pytest.mark.asyncio
    async def test_no_character_skips(self):
        """No character attached should return immediately."""
        from server.session import Session, Protocol, SessionState
        sender = FakeSend()
        async def noop(): pass
        s = Session(Protocol.WEBSOCKET, sender, noop)
        s.state = SessionState.IN_GAME
        s.character = None
        await s.send_hud_update()
        assert len(sender.messages) == 0

    @pytest.mark.asyncio
    async def test_basic_hud_without_db(self):
        """With no DB, should still send base HUD with character data."""
        s, sender = make_session()
        await s.send_hud_update(db=None, session_mgr=None)
        assert len(sender.messages) >= 1
        hud_msg = json.loads(sender.messages[-1])
        assert hud_msg["type"] == "hud_update"
        assert hud_msg["name"] == "Test Char"
        assert hud_msg["credits"] == 5000
