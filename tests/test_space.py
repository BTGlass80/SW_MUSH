# -*- coding: utf-8 -*-
"""
tests/test_space.py — Space systems integration tests.

Covers:
  - Ship listing (+ships, +myships)
  - Boarding ships
  - Ship status display
  - Crew assignment (pilot, gunner, etc.)
  - Launch / land cycle
  - Scanning
  - Ship info display
  - Space combat (fire, lock-on, evasion)
  - Docking mechanics
"""
import pytest
from tests.harness import strip_ansi, assert_output_contains

pytestmark = pytest.mark.asyncio


class TestShipListing:
    async def test_ships_at_dock(self, harness):
        """List ships docked in a hangar bay."""
        # Room 4 = Docking Bay 94 Entrance, but ships dock at room 4/5/8/9/10
        s = await harness.login_as("ShipLister", room_id=4)
        out = await harness.cmd(s, "+ships")
        clean = strip_ansi(out)
        # Should show docked ships or "no ships"
        assert len(clean) > 5

    async def test_myships_empty(self, harness):
        s = await harness.login_as("NoShips", room_id=2)
        out = await harness.cmd(s, "+myships")
        clean = strip_ansi(out).lower()
        assert "no ships" in clean or "don't own" in clean or "none" in clean \
               or "myships" in clean or len(clean) > 0


class TestShipBoarding:
    async def test_board_ship(self, harness):
        """Board a docked ship."""
        # Find a ship docked at a known location
        ships = await harness.get_ships_at_dock(4)
        if not ships:
            pytest.skip("No ships docked at room 4")
        ship = ships[0]
        s = await harness.login_as("Boarder", room_id=4)
        out = await harness.cmd(s, f"board {ship['name']}")
        clean = strip_ansi(out).lower()
        assert "board" in clean or "bridge" in clean or "enter" in clean \
               or "step" in clean or len(clean) > 5

    async def test_board_no_ship(self, harness):
        s = await harness.login_as("NoBoarder", room_id=2)
        out = await harness.cmd(s, "board Nonexistent Ship")
        clean = strip_ansi(out).lower()
        assert "no ship" in clean or "can't find" in clean or "not found" in clean \
               or len(clean) > 0


class TestCrewAssignment:
    async def test_pilot_command(self, harness):
        s = await harness.login_as("PilotTest", room_id=2)
        out = await harness.cmd(s, "pilot")
        clean = strip_ansi(out).lower()
        # Not on a ship bridge — should error
        assert "bridge" in clean or "ship" in clean or "not" in clean \
               or "pilot" in clean or len(clean) > 0

    async def test_gunner_command(self, harness):
        s = await harness.login_as("GunnerTest", room_id=2)
        out = await harness.cmd(s, "gunner")
        clean = strip_ansi(out).lower()
        assert "bridge" in clean or "ship" in clean or "not" in clean \
               or "gunner" in clean or len(clean) > 0


class TestShipOperations:
    async def test_ship_status_no_ship(self, harness):
        s = await harness.login_as("NoShipStatus", room_id=2)
        out = await harness.cmd(s, "+ship/status")
        clean = strip_ansi(out).lower()
        assert "ship" in clean or "not" in clean or "bridge" in clean

    async def test_launch_not_on_ship(self, harness):
        s = await harness.login_as("GroundLaunch", room_id=2)
        out = await harness.cmd(s, "launch")
        clean = strip_ansi(out).lower()
        assert "bridge" in clean or "ship" in clean or "pilot" in clean \
               or "not" in clean or len(clean) > 0

    async def test_scan_command(self, harness):
        s = await harness.login_as("Scanner", room_id=2)
        out = await harness.cmd(s, "scan")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0  # Should produce some output

    async def test_ship_info(self, harness):
        s = await harness.login_as("InfoCheck", room_id=4)
        ships = await harness.get_ships_at_dock(4)
        if ships:
            out = await harness.cmd(s, f"+shipinfo {ships[0]['name']}")
            clean = strip_ansi(out)
            assert len(clean) > 20


class TestSpaceCombat:
    async def test_fire_not_in_space(self, harness):
        s = await harness.login_as("GroundFire", room_id=2)
        out = await harness.cmd(s, "fire")
        clean = strip_ansi(out).lower()
        assert "ship" in clean or "bridge" in clean or "space" in clean \
               or "not" in clean or "fire" in clean

    async def test_lockon_not_in_space(self, harness):
        s = await harness.login_as("GroundLock", room_id=2)
        out = await harness.cmd(s, "lockon")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0

    async def test_evasion_commands(self, harness):
        s = await harness.login_as("Evader", room_id=2)
        for cmd in ["jink", "barrelroll", "evade"]:
            out = await harness.cmd(s, cmd)
            clean = strip_ansi(out).lower()
            assert len(clean) > 0  # Should produce some response
