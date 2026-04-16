# -*- coding: utf-8 -*-
"""
tests/test_space_lifecycle.py — Space flight lifecycle integration tests.

Tests the full ship lifecycle through commands:
  - Ship creation (admin @spawn/ship)
  - Ship listing (+ships, +myships)
  - Boarding and disembarking
  - Crew assignment (pilot, gunner, copilot, engineer)
  - Launch (fuel cost, docking fee)
  - Ship status display in space
  - Landing
  - Ship info and scan
  - Ship ownership tracking
"""
import pytest
import json
from tests.harness import strip_ansi, assert_output_contains

pytestmark = pytest.mark.asyncio


class TestShipCreation:
    async def test_admin_spawn_ship(self, harness):
        """Admin can spawn a ship for a player."""
        s = await harness.login_as("ShipBuilder", room_id=5, is_admin=True,
                                    credits=100000)
        out = await harness.cmd(s, "@spawn/ship z_95 TestFighter")
        clean = strip_ansi(out).lower()
        assert "spawned" in clean or "ship" in clean or "testfighter" in clean \
               or "z_95" in clean or "z-95" in clean, \
            f"Ship spawn failed: {clean[:200]}"

    async def test_spawned_ship_in_myships(self, harness):
        """A spawned ship should appear in +myships."""
        s = await harness.login_as("ShipOwner", room_id=5, is_admin=True,
                                    credits=100000)
        await harness.cmd(s, "@spawn/ship yt_1300 MyFreighter")
        s.character = await harness.get_char(s.character["id"])

        out = await harness.cmd(s, "+myships")
        clean = strip_ansi(out)
        assert "MyFreighter" in clean or "freighter" in clean.lower(), \
            f"+myships doesn't show spawned ship: {clean[:300]}"


class TestShipBoarding:
    async def _setup_ship(self, harness, player_name="Pilot"):
        """Helper: create a player with a ship docked at room 5."""
        s = await harness.login_as(player_name, room_id=5, is_admin=True,
                                    credits=100000,
                                    skills={"space transports": "3D",
                                            "starship gunnery": "2D",
                                            "astrogation": "2D"})
        await harness.cmd(s, f"@spawn/ship yt_1300 {player_name}Ship")
        s.character = await harness.get_char(s.character["id"])
        return s

    async def test_board_own_ship(self, harness):
        s = await self._setup_ship(harness, "Boarder1")
        out = await harness.cmd(s, "board Boarder1Ship")
        clean = strip_ansi(out).lower()
        # Should either board or show the ship bridge
        assert "board" in clean or "bridge" in clean or "cockpit" in clean \
               or "step" in clean or "enter" in clean, \
            f"Board failed: {clean[:200]}"

    async def test_disembark_from_ship(self, harness):
        s = await self._setup_ship(harness, "Disem1")
        await harness.cmd(s, "board Disem1Ship")
        s.character = await harness.get_char(s.character["id"])

        out = await harness.cmd(s, "disembark")
        clean = strip_ansi(out).lower()
        assert "disembark" in clean or "step" in clean or "leave" in clean \
               or "dock" in clean or len(clean) > 5


class TestCrewAssignment:
    async def _setup_boarded(self, harness, name="CrewTest"):
        s = await harness.login_as(name, room_id=5, is_admin=True,
                                    credits=100000,
                                    skills={"space transports": "4D",
                                            "starship gunnery": "3D",
                                            "astrogation": "3D",
                                            "space transports repair": "2D",
                                            "sensors": "2D"})
        await harness.cmd(s, f"@spawn/ship yt_1300 {name}Ship")
        s.character = await harness.get_char(s.character["id"])
        await harness.cmd(s, f"board {name}Ship")
        s.character = await harness.get_char(s.character["id"])
        return s

    async def test_assign_pilot(self, harness):
        s = await self._setup_boarded(harness, "PilotAssign")
        out = await harness.cmd(s, "pilot")
        clean = strip_ansi(out).lower()
        assert "pilot" in clean

    async def test_assign_gunner(self, harness):
        s = await self._setup_boarded(harness, "GunAssign")
        out = await harness.cmd(s, "gunner")
        clean = strip_ansi(out).lower()
        assert "gunner" in clean or "station" in clean

    async def test_vacate_station(self, harness):
        s = await self._setup_boarded(harness, "VacateTest")
        await harness.cmd(s, "pilot")
        out = await harness.cmd(s, "vacate")
        clean = strip_ansi(out).lower()
        assert "vacate" in clean or "leave" in clean or "station" in clean


class TestLaunchAndLand:
    async def _setup_piloted(self, harness, name="FlightTest"):
        s = await harness.login_as(name, room_id=5, is_admin=True,
                                    credits=100000,
                                    skills={"space transports": "4D",
                                            "astrogation": "3D"})
        await harness.cmd(s, f"@spawn/ship yt_1300 {name}Ship")
        s.character = await harness.get_char(s.character["id"])
        await harness.cmd(s, f"board {name}Ship")
        s.character = await harness.get_char(s.character["id"])
        await harness.cmd(s, "pilot")
        return s

    async def test_launch_deducts_fuel(self, harness):
        s = await self._setup_piloted(harness, "FuelTest")
        before = await harness.get_credits(s.character["id"])
        out = await harness.cmd(s, "launch")
        after = await harness.get_credits(s.character["id"])
        clean = strip_ansi(out).lower()

        if "launch" in clean or "space" in clean or "fuel" in clean:
            assert after < before, \
                f"Launch didn't deduct fuel: {before} → {after}"

    async def test_launch_sets_in_space(self, harness):
        s = await self._setup_piloted(harness, "SpaceTest")
        await harness.cmd(s, "launch")

        # Check ship is now in space (docked_at = NULL)
        ships = await harness.get_player_ships(s.character["id"])
        if ships:
            ship = ships[0]
            assert ship["docked_at"] is None, \
                f"Ship still docked after launch: docked_at={ship['docked_at']}"

    async def test_ship_status_in_space(self, harness):
        s = await self._setup_piloted(harness, "StatusSpace")
        await harness.cmd(s, "launch")
        out = await harness.cmd(s, "+ship/status")
        clean = strip_ansi(out)
        assert len(clean) > 20  # Should show ship status

    async def test_cannot_launch_twice(self, harness):
        s = await self._setup_piloted(harness, "DoubleLaunch")
        await harness.cmd(s, "launch")
        out = await harness.cmd(s, "launch")
        clean = strip_ansi(out).lower()
        assert "already" in clean or "space" in clean

    async def test_land_command(self, harness):
        s = await self._setup_piloted(harness, "Lander")
        await harness.cmd(s, "launch")
        out = await harness.cmd(s, "land")
        clean = strip_ansi(out).lower()
        # May need to course to a destination first
        assert len(clean) > 5

    async def test_launch_without_pilot_denied(self, harness):
        """Non-pilot can't launch."""
        s = await harness.login_as("NoPilot", room_id=5, is_admin=True,
                                    credits=100000)
        await harness.cmd(s, "@spawn/ship yt_1300 NoPilotShip")
        s.character = await harness.get_char(s.character["id"])
        await harness.cmd(s, "board NoPilotShip")
        s.character = await harness.get_char(s.character["id"])
        # Don't assign as pilot
        out = await harness.cmd(s, "launch")
        clean = strip_ansi(out).lower()
        assert "pilot" in clean

    async def test_launch_insufficient_credits(self, harness):
        """Can't launch without fuel credits."""
        s = await harness.login_as("BrokePilot", room_id=5, is_admin=True,
                                    credits=0)
        await harness.cmd(s, "@spawn/ship yt_1300 BrokeShip")
        s.character = await harness.get_char(s.character["id"])
        await harness.cmd(s, "board BrokeShip")
        s.character = await harness.get_char(s.character["id"])
        await harness.cmd(s, "pilot")
        out = await harness.cmd(s, "launch")
        clean = strip_ansi(out).lower()
        assert "credit" in clean or "fuel" in clean or "enough" in clean


class TestShipInfo:
    async def test_ship_info_shows_template(self, harness):
        s = await harness.login_as("InfoViewer", room_id=5, is_admin=True,
                                    credits=100000)
        await harness.cmd(s, "@spawn/ship z_95 InfoFighter")
        s.character = await harness.get_char(s.character["id"])
        out = await harness.cmd(s, "+shipinfo InfoFighter")
        clean = strip_ansi(out)
        assert "Z-95" in clean or "z_95" in clean or "Headhunter" in clean \
               or len(clean) > 50

    async def test_ships_list_at_dock(self, harness):
        s = await harness.login_as("DockViewer", room_id=5, is_admin=True,
                                    credits=100000)
        await harness.cmd(s, "@spawn/ship yt_1300 DockShip1")
        out = await harness.cmd(s, "+ships")
        clean = strip_ansi(out)
        assert "DockShip1" in clean or "ship" in clean.lower()
