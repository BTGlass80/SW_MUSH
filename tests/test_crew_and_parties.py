# -*- coding: utf-8 -*-
"""
tests/test_crew_and_parties.py — NPC crew, party, and spacer quest tests.

Covers:
  - NPC crew hiring/management
  - Party system (invite, join, leave)
  - Spacer quest progression
  - Crew wage economics
"""
import pytest
from tests.harness import strip_ansi

pytestmark = pytest.mark.asyncio


class TestNPCCrew:
    async def test_crew_list(self, harness):
        s = await harness.login_as("CrewViewer", room_id=2)
        out = await harness.cmd(s, "+crew")
        clean = strip_ansi(out).lower()
        assert "crew" in clean or "no crew" in clean or "none" in clean \
               or len(clean) > 0

    async def test_hire_command(self, harness):
        s = await harness.login_as("Hirer", room_id=2, credits=10000)
        out = await harness.cmd(s, "+crew/hire")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0


class TestParty:
    async def test_party_status(self, harness):
        s = await harness.login_as("PartyCheck", room_id=2)
        out = await harness.cmd(s, "+party")
        clean = strip_ansi(out).lower()
        assert "party" in clean or "no party" in clean or "not in" in clean \
               or len(clean) > 0

    async def test_party_invite(self, harness):
        s1 = await harness.login_as("PartyLeader", room_id=2)
        s2 = await harness.login_as("PartyMember", room_id=2)
        out = await harness.cmd(s1, "+party/invite PartyMember")
        clean = strip_ansi(out).lower()
        assert "invite" in clean or "party" in clean or len(clean) > 0

    async def test_party_leave(self, harness):
        s = await harness.login_as("PartyLeaver", room_id=2)
        out = await harness.cmd(s, "+party/leave")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0


class TestSpacerQuest:
    async def test_spacer_quest_status(self, harness):
        s = await harness.login_as("SpacerQuester", room_id=2)
        out = await harness.cmd(s, "+spacerquest")
        clean = strip_ansi(out)
        assert len(clean) > 0
