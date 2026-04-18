# -*- coding: utf-8 -*-
"""
tests/test_session39.py — Session 39 Tests

Tests for:
  1. Vendor droid faction discount integration (Known Issue #5)
  2. NPC pilot skill lookup fix (Known Issue #1)
  3. Boarding link system (Priority D Phase 3)
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ═══════════════════════════════════════════════════════════════════════
# 1. Vendor Droid Faction Discount
# ═══════════════════════════════════════════════════════════════════════

class TestVendorDroidFactionDiscount:
    """Verify faction discount code path exists in buy_from_droid."""

    def test_buy_from_droid_has_faction_block(self):
        """buy_from_droid should contain faction shop modifier logic."""
        import inspect
        from engine.vendor_droids import buy_from_droid
        src = inspect.getsource(buy_from_droid)
        assert "get_faction_shop_modifier" in src, \
            "buy_from_droid must call get_faction_shop_modifier"
        assert "faction_msg" in src, \
            "buy_from_droid must build a faction_msg string"
        assert "vendor refuses to serve" in src.lower() or "refuses to serve" in src.lower(), \
            "buy_from_droid must handle blocked purchases"

    def test_buy_from_droid_returns_faction_msg(self):
        """The return message should include faction_msg."""
        import inspect
        from engine.vendor_droids import buy_from_droid
        src = inspect.getsource(buy_from_droid)
        assert "faction_msg" in src
        # The return string should concatenate faction_msg
        assert "bargain_msg}{faction_msg}" in src or \
               "{faction_msg}" in src, \
            "Return message must include {faction_msg}"

    def test_faction_map_covers_all_factions(self):
        """The faction name → code mapping should cover all 4 factions."""
        import inspect
        from engine.vendor_droids import buy_from_droid
        src = inspect.getsource(buy_from_droid)
        for code in ["empire", "rebel", "hutt", "bh_guild"]:
            assert f'"{code}"' in src, \
                f"Faction code '{code}' must be in faction map"


# ═══════════════════════════════════════════════════════════════════════
# 2. NPC Pilot Skill Fix
# ═══════════════════════════════════════════════════════════════════════

class TestNpcPilotSkillFix:
    """Verify NPC combat AI reads actual target pilot skill."""

    def test_no_hardcoded_3d_in_fire(self):
        """_do_fire should not use hardcoded '3D' for target pilot skill."""
        import inspect
        from engine.npc_space_combat_ai import NpcSpaceCombatManager
        src = inspect.getsource(NpcSpaceCombatManager._do_fire)
        # Should NOT have DicePool.parse("3D") for target_pilot_skill
        assert 'target_pilot_skill=DicePool.parse("3D")' not in src, \
            "_do_fire must not hardcode target_pilot_skill to 3D"
        assert "_get_target_pilot_skill" in src, \
            "_do_fire must call _get_target_pilot_skill"

    def test_no_hardcoded_3d_in_maneuver(self):
        """_do_maneuver should not use hardcoded '3D' for target pilot skill."""
        import inspect
        from engine.npc_space_combat_ai import NpcSpaceCombatManager
        src = inspect.getsource(NpcSpaceCombatManager._do_maneuver)
        assert 'target_pilot_skill=DicePool.parse("3D")' not in src, \
            "_do_maneuver must not hardcode target_pilot_skill to 3D"
        assert "_get_target_pilot_skill" in src, \
            "_do_maneuver must call _get_target_pilot_skill"

    def test_helper_method_exists(self):
        """_get_target_pilot_skill helper must exist."""
        from engine.npc_space_combat_ai import NpcSpaceCombatManager
        assert hasattr(NpcSpaceCombatManager, "_get_target_pilot_skill"), \
            "NpcSpaceCombatManager must have _get_target_pilot_skill method"

    def test_helper_returns_default_on_no_crew(self):
        """Helper should return 3D default when ship has no crew."""
        import asyncio
        from engine.npc_space_combat_ai import NpcSpaceCombatManager
        from engine.dice import DicePool

        mgr = NpcSpaceCombatManager()
        ship = {"crew": "{}"}

        class MockDB:
            async def get_character(self, cid):
                return None

        result = asyncio.get_event_loop().run_until_complete(
            mgr._get_target_pilot_skill(ship, None, MockDB())
        )
        assert result.dice == 3 and result.pips == 0, \
            "Should return 3D+0 default when no pilot found"

    def test_helper_returns_default_on_empty_crew(self):
        """Helper returns default when crew JSON is empty."""
        import asyncio
        from engine.npc_space_combat_ai import NpcSpaceCombatManager

        mgr = NpcSpaceCombatManager()
        ship = {"crew": ""}

        class MockDB:
            async def get_character(self, cid):
                return None

        result = asyncio.get_event_loop().run_until_complete(
            mgr._get_target_pilot_skill(ship, None, MockDB())
        )
        assert result.dice == 3 and result.pips == 0


# ═══════════════════════════════════════════════════════════════════════
# 3. Boarding Link System
# ═══════════════════════════════════════════════════════════════════════

class TestBoardingLinkEngine:
    """Test the boarding link engine module."""

    def test_module_imports(self):
        """Boarding module should import cleanly."""
        from engine.boarding import (
            create_boarding_link, sever_boarding_link,
            get_boarding_link_info, startup_cleanup,
            BOARDING_EXIT_DIR_TO, BOARDING_EXIT_DIR_FROM,
        )
        assert BOARDING_EXIT_DIR_TO == "boarding_link"
        assert BOARDING_EXIT_DIR_FROM == "boarding_link_back"

    def test_get_boarding_link_info_none(self):
        """No link → returns None."""
        from engine.boarding import get_boarding_link_info
        ship = {"systems": "{}"}
        assert get_boarding_link_info(ship) is None

    def test_get_boarding_link_info_active(self):
        """Active link → returns dict with linked_to."""
        from engine.boarding import get_boarding_link_info
        ship = {"systems": json.dumps({
            "boarding_linked_to": 42,
            "boarding_exit_ids": [100, 101],
        })}
        info = get_boarding_link_info(ship)
        assert info is not None
        assert info["linked_to"] == 42
        assert info["exit_ids"] == [100, 101]

    def test_get_systems_handles_string(self):
        """_get_systems should parse JSON string."""
        from engine.boarding import _get_systems
        ship = {"systems": '{"foo": 1}'}
        assert _get_systems(ship) == {"foo": 1}

    def test_get_systems_handles_dict(self):
        """_get_systems should pass through dict."""
        from engine.boarding import _get_systems
        ship = {"systems": {"foo": 1}}
        assert _get_systems(ship) == {"foo": 1}

    def test_get_systems_handles_empty(self):
        """_get_systems should handle empty/None."""
        from engine.boarding import _get_systems
        assert _get_systems({"systems": ""}) == {}
        assert _get_systems({"systems": None}) == {}
        assert _get_systems({}) == {}

    def test_get_all_crew_ids(self):
        """_get_all_crew_ids should extract all crew character IDs."""
        from engine.boarding import _get_all_crew_ids
        ship = {"crew": json.dumps({
            "pilot": 10,
            "copilot": 20,
            "engineer": 30,
            "gunner_stations": {"0": 40, "1": 50},
        })}
        ids = _get_all_crew_ids(ship)
        assert ids == {10, 20, 30, 40, 50}

    def test_get_all_crew_ids_empty(self):
        """_get_all_crew_ids handles empty crew."""
        from engine.boarding import _get_all_crew_ids
        assert _get_all_crew_ids({"crew": "{}"}) == set()
        assert _get_all_crew_ids({"crew": ""}) == set()
        assert _get_all_crew_ids({}) == set()


class TestBoardingLinkValidation:
    """Test create_boarding_link validation logic."""

    def test_rejects_no_bridge(self):
        """Should reject if either ship lacks a bridge."""
        import asyncio
        from engine.boarding import create_boarding_link

        ship_a = {"id": 1, "bridge_room_id": None, "systems": "{}"}
        ship_b = {"id": 2, "bridge_room_id": 100, "systems": "{}"}

        ok, msg = asyncio.get_event_loop().run_until_complete(
            create_boarding_link(ship_a, ship_b, None)
        )
        assert not ok
        assert "no accessible interior" in msg.lower()

    def test_rejects_docked_target(self):
        """Should reject if target is docked."""
        import asyncio
        from engine.boarding import create_boarding_link

        ship_a = {"id": 1, "bridge_room_id": 10, "docked_at": None, "systems": "{}"}
        ship_b = {"id": 2, "bridge_room_id": 20, "docked_at": 99, "systems": "{}"}

        ok, msg = asyncio.get_event_loop().run_until_complete(
            create_boarding_link(ship_a, ship_b, None)
        )
        assert not ok
        assert "docked" in msg.lower()

    def test_rejects_already_linked(self):
        """Should reject if initiator already has a link."""
        import asyncio
        from engine.boarding import create_boarding_link

        ship_a = {"id": 1, "bridge_room_id": 10, "docked_at": None,
                  "systems": json.dumps({"boarding_linked_to": 99})}
        ship_b = {"id": 2, "bridge_room_id": 20, "docked_at": None, "systems": "{}"}

        ok, msg = asyncio.get_event_loop().run_until_complete(
            create_boarding_link(ship_a, ship_b, None)
        )
        assert not ok
        assert "already has" in msg.lower()


class TestBoardShipCommand:
    """Test the BoardShipCommand parser class."""

    def test_command_registered(self):
        """BoardShipCommand should be in the registration list."""
        import inspect
        from parser.space_commands import register_space_commands
        src = inspect.getsource(register_space_commands)
        assert "BoardShipCommand" in src

    def test_command_key(self):
        """BoardShipCommand should have key 'boardship'."""
        from parser.space_commands import BoardShipCommand
        cmd = BoardShipCommand()
        assert cmd.key == "boardship"
        assert "boardlink" in cmd.aliases

    def test_help_text(self):
        """Help text should mention tractor and Close range."""
        from parser.space_commands import BoardShipCommand
        cmd = BoardShipCommand()
        assert "tractor" in cmd.help_text.lower()
        assert "close" in cmd.help_text.lower()


class TestBoardingHyperspaceCleanup:
    """Verify boarding link cleanup is wired into hyperspace."""

    def test_hyperspace_has_boarding_cleanup(self):
        """HyperspaceCommand should sever boarding links."""
        import inspect
        from parser.space_commands import HyperspaceCommand
        src = inspect.getsource(HyperspaceCommand)
        assert "sever_boarding_link" in src
        assert 'reason="hyperspace"' in src

    def test_resist_tractor_has_boarding_cleanup(self):
        """ResistTractorCommand should sever boarding links on breakfree."""
        import inspect
        from parser.space_commands import ResistTractorCommand
        src = inspect.getsource(ResistTractorCommand)
        assert "sever_boarding_link" in src
        assert 'reason="tractor_release"' in src


class TestBoardingBootCleanup:
    """Verify boarding cleanup is in boot sequence."""

    def test_boot_has_boarding_cleanup(self):
        """game_server should call boarding startup_cleanup."""
        import inspect
        from server.game_server import GameServer
        src = inspect.getsource(GameServer.start)
        assert "boarding_cleanup" in src or "startup_cleanup" in src


class TestBoardingShipStatus:
    """Verify boarding link info appears in ship status."""

    def test_ship_info_shows_boarding(self):
        """ShipCommand should display boarding link status."""
        import inspect
        from parser.space_commands import ShipCommand
        src = inspect.getsource(ShipCommand)
        assert "boarding_linked_to" in src
        assert "BOARDING" in src

    def test_hud_includes_boarding(self):
        """HUD JSON builder should include boarding_linked_to."""
        with open("parser/space_commands.py") as f:
            src = f.read()
        # The build_space_state dict should include boarding data
        assert '"boarding_linked_to"' in src


# ═══════════════════════════════════════════════════════════════════════
# 4. Regression: Silent Except Invariant (carried from Session 38)
# ═══════════════════════════════════════════════════════════════════════

class TestSilentExceptInvariant:
    """Ensure no new silent except/pass blocks in production code."""

    def test_no_silent_except_pass_in_new_files(self):
        """New/modified files must not have silent except: pass blocks."""
        import re
        pattern = re.compile(
            r'except\s+(?:Exception)?.*?:\s*\n\s*pass\s*$',
            re.MULTILINE
        )
        files = [
            "engine/boarding.py",
            "engine/vendor_droids.py",
            "engine/npc_space_combat_ai.py",
        ]
        for filepath in files:
            if not os.path.exists(filepath):
                continue
            with open(filepath) as f:
                content = f.read()
            matches = pattern.findall(content)
            assert len(matches) == 0, \
                f"Silent except/pass found in {filepath}: {matches}"
