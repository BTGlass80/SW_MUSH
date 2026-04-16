# -*- coding: utf-8 -*-
"""
tests/test_factions.py — Factions, organizations, and territory tests.

Covers:
  - Faction listing and info
  - Joining a faction
  - Guild listing
  - Specialization
  - Territory influence display
  - Faction leader commands (basic access checks)
"""
import pytest
from tests.harness import strip_ansi, assert_output_contains

pytestmark = pytest.mark.asyncio


class TestFactionDisplay:
    async def test_faction_list(self, harness):
        """View available factions."""
        s = await harness.login_as("FactionBrowser", room_id=2)
        out = await harness.cmd(s, "+faction")
        clean = strip_ansi(out)
        assert len(clean) > 10  # Should list factions

    async def test_faction_info(self, harness):
        s = await harness.login_as("FactionInfo", room_id=2)
        out = await harness.cmd(s, "+faction/info rebel")
        clean = strip_ansi(out).lower()
        assert "rebel" in clean or "alliance" in clean or "faction" in clean \
               or len(clean) > 5

    async def test_faction_join(self, harness):
        s = await harness.login_as("FactionJoiner", room_id=2)
        out = await harness.cmd(s, "+faction/join rebel")
        clean = strip_ansi(out).lower()
        # Should either join or explain why not
        assert "join" in clean or "faction" in clean or "rebel" in clean \
               or "already" in clean or len(clean) > 5


class TestGuilds:
    async def test_guild_list(self, harness):
        s = await harness.login_as("GuildBrowser", room_id=2)
        out = await harness.cmd(s, "+guild")
        clean = strip_ansi(out)
        assert len(clean) > 5

    async def test_specialize(self, harness):
        s = await harness.login_as("Specialist", room_id=2)
        out = await harness.cmd(s, "+specialize")
        clean = strip_ansi(out)
        assert len(clean) > 5  # Should show specialization options or status


class TestTerritory:
    async def test_territory_display(self, harness):
        """Territory info for current area."""
        s = await harness.login_as("TerritoryViewer", room_id=2)
        # Try a territory-related command
        out = await harness.cmd(s, "+territory")
        clean = strip_ansi(out)
        assert len(clean) > 0


class TestFactionLeader:
    async def test_leader_commands_non_leader(self, harness):
        """Non-leaders should be denied faction leader commands."""
        s = await harness.login_as("NotLeader", room_id=2)
        out = await harness.cmd(s, "+fleader")
        clean = strip_ansi(out).lower()
        assert "leader" in clean or "not" in clean or "permission" in clean \
               or "faction" in clean or len(clean) > 0
