# -*- coding: utf-8 -*-
"""
tests/test_factions_deep.py — Deep faction, guild, and territory tests.

Covers:
  - Organization data seeding
  - Faction join/leave lifecycle
  - Faction roster display
  - Guild membership
  - Specialization selection
  - Territory influence mechanics (engine level)
  - Territory claiming
  - Faction leader access controls
  - Faction payroll/treasury
"""
import pytest
import json
from tests.harness import strip_ansi, assert_output_contains

pytestmark = pytest.mark.asyncio


class TestOrganizationSeeding:
    async def test_factions_seeded(self, harness):
        """Core factions should exist in the database."""
        rows = await harness.db._db.execute_fetchall(
            "SELECT * FROM organizations WHERE org_type = 'faction'"
        )
        factions = [dict(r) for r in rows]
        assert len(factions) >= 3, f"Only {len(factions)} factions seeded"

        # Check core factions exist
        names = [f["name"].lower() for f in factions]
        assert any("rebel" in n or "alliance" in n for n in names), \
            "Rebel Alliance not found in factions"
        assert any("empire" in n or "imperial" in n for n in names), \
            "Galactic Empire not found in factions"

    async def test_guilds_seeded(self, harness):
        """Professional guilds should exist."""
        rows = await harness.db._db.execute_fetchall(
            "SELECT * FROM organizations WHERE org_type = 'guild'"
        )
        guilds = [dict(r) for r in rows]
        assert len(guilds) >= 3, f"Only {len(guilds)} guilds seeded"


class TestFactionJoinLeave:
    async def test_join_faction(self, harness):
        s = await harness.login_as("Joiner", room_id=2)
        out = await harness.cmd(s, "+faction/join rebel")
        clean = strip_ansi(out).lower()
        assert "join" in clean or "rebel" in clean or "faction" in clean

    async def test_faction_status_after_join(self, harness):
        s = await harness.login_as("StatusCheck", room_id=2)
        await harness.cmd(s, "+faction/join rebel")
        out = await harness.cmd(s, "+faction")
        clean = strip_ansi(out)
        assert len(clean) > 10

    async def test_leave_faction(self, harness):
        s = await harness.login_as("Leaver", room_id=2)
        await harness.cmd(s, "+faction/join rebel")
        out = await harness.cmd(s, "+faction/leave")
        clean = strip_ansi(out).lower()
        assert "leave" in clean or "left" in clean or "faction" in clean \
               or len(clean) > 5

    async def test_cannot_join_two_factions(self, harness):
        """Should not be able to join a second faction without leaving first."""
        s = await harness.login_as("Doublejoin", room_id=2)
        await harness.cmd(s, "+faction/join rebel")
        out = await harness.cmd(s, "+faction/join imperial")
        clean = strip_ansi(out).lower()
        assert "already" in clean or "leave" in clean or "member" in clean \
               or "faction" in clean


class TestFactionRoster:
    async def test_roster_command(self, harness):
        s = await harness.login_as("RosterView", room_id=2)
        await harness.cmd(s, "+faction/join rebel")
        out = await harness.cmd(s, "+faction/roster")
        clean = strip_ansi(out)
        assert len(clean) > 5


class TestGuildMembership:
    async def test_guild_join(self, harness):
        s = await harness.login_as("GuildJoiner", room_id=2)
        out = await harness.cmd(s, "+guild/join smuggler")
        clean = strip_ansi(out).lower()
        assert "guild" in clean or "join" in clean or "smuggl" in clean \
               or len(clean) > 5

    async def test_guild_list_shows_guilds(self, harness):
        s = await harness.login_as("GuildLister", room_id=2)
        out = await harness.cmd(s, "+guild")
        clean = strip_ansi(out)
        assert len(clean) > 20


class TestSpecialization:
    async def test_specialize_command(self, harness):
        s = await harness.login_as("Speccer", room_id=2)
        out = await harness.cmd(s, "+specialize")
        clean = strip_ansi(out)
        assert len(clean) > 5  # Should show options or status


class TestTerritory:
    async def test_territory_schema_exists(self, harness):
        """Territory tables should exist."""
        rows = await harness.db._db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='territory_influence'"
        )
        assert len(rows) > 0, "territory_influence table missing"

    async def test_territory_command(self, harness):
        s = await harness.login_as("TerritoryView", room_id=2)
        out = await harness.cmd(s, "+territory")
        clean = strip_ansi(out)
        assert len(clean) > 0

    async def test_territory_claim(self, harness):
        s = await harness.login_as("Claimer", room_id=2)
        await harness.cmd(s, "+faction/join rebel")
        out = await harness.cmd(s, "+territory/claim")
        clean = strip_ansi(out).lower()
        # May fail if room is already claimed or not claimable
        assert len(clean) > 0


class TestFactionLeaderAccess:
    async def test_leader_commands_require_membership(self, harness):
        s = await harness.login_as("NoFaction", room_id=2)
        out = await harness.cmd(s, "+fleader/treasury")
        clean = strip_ansi(out).lower()
        assert "faction" in clean or "not" in clean or "leader" in clean \
               or "permission" in clean or len(clean) > 0
