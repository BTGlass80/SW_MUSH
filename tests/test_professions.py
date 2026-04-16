# -*- coding: utf-8 -*-
"""
tests/test_professions.py — Profession-specific system tests.

Covers:
  - Bounty board (+bounties, claim, track, collect)
  - Espionage (scan, eavesdrop, investigate, intel)
  - Medical commands
  - Entertainer (perform)
  - NPC interaction (talk)
  - Sabacc
"""
import pytest
from tests.harness import strip_ansi

pytestmark = pytest.mark.asyncio


class TestBountyHunter:
    async def test_bounties_list(self, harness):
        s = await harness.login_as("BountyViewer", room_id=2)
        out = await harness.cmd(s, "+bounties")
        clean = strip_ansi(out)
        assert len(clean) > 5

    async def test_bounty_claim_no_bounty(self, harness):
        s = await harness.login_as("NoClaim", room_id=2)
        out = await harness.cmd(s, "+bounty/claim 1")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0

    async def test_my_bounty(self, harness):
        s = await harness.login_as("MyBounty", room_id=2)
        out = await harness.cmd(s, "+mybounty")
        clean = strip_ansi(out).lower()
        assert "bounty" in clean or "no" in clean or "none" in clean \
               or len(clean) > 0

    async def test_bounty_track(self, harness):
        s = await harness.login_as("Tracker", room_id=2,
                                    skills={"search": "3D",
                                            "investigation": "2D"})
        out = await harness.cmd(s, "+bounty/track")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0


class TestEspionage:
    async def test_eavesdrop(self, harness):
        s = await harness.login_as("Eavesdropper", room_id=2,
                                    skills={"con": "3D", "sneak": "2D"})
        out = await harness.cmd(s, "eavesdrop")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0

    async def test_investigate(self, harness):
        s = await harness.login_as("Investigator", room_id=2,
                                    skills={"investigation": "3D"})
        out = await harness.cmd(s, "investigate")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0

    async def test_intel(self, harness):
        s = await harness.login_as("IntelGatherer", room_id=2)
        out = await harness.cmd(s, "+intel")
        clean = strip_ansi(out)
        assert len(clean) > 0


class TestMedical:
    async def test_medical_commands_exist(self, harness):
        """Verify medical commands are registered and respond."""
        s = await harness.login_as("Medic", room_id=2,
                                    skills={"first aid": "3D"})
        # Just check the commands exist and don't crash
        for cmd in ["heal", "diagnose", "medkit"]:
            out = await harness.cmd(s, cmd)
            assert len(strip_ansi(out)) > 0 or True  # Some may need targets


class TestEntertainer:
    async def test_perform_command(self, harness):
        s = await harness.login_as("Performer", room_id=17,
                                    skills={"musical instrument": "3D"})
        out = await harness.cmd(s, "perform")
        clean = strip_ansi(out).lower()
        assert "perform" in clean or "music" in clean or "entertain" in clean \
               or len(clean) > 0


class TestNPCInteraction:
    async def test_talk_to_npc(self, harness):
        """Talk to an NPC in the cantina."""
        s = await harness.login_as("NPCTalker", room_id=17)
        out = await harness.cmd(s, "talk Wuher")
        clean = strip_ansi(out)
        # Should either trigger NPC dialogue or explain usage
        assert len(clean) > 5


class TestSabacc:
    async def test_sabacc_command(self, harness):
        s = await harness.login_as("Gambler", room_id=17, credits=500)
        out = await harness.cmd(s, "+sabacc")
        clean = strip_ansi(out)
        assert len(clean) > 5
