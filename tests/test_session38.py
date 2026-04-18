# -*- coding: utf-8 -*-
"""
tests/test_session38.py — Session 38 feature tests

Tests:
  1. Texture encounter auto-trigger during transit
  2. NPC combat zone-change cleanup on hyperspace
  3. Silent except/pass invariant enforcement
  4. Faction mission board generation + gating
"""
import json
import os
import random
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Texture encounter auto-trigger
# ══════════════════════════════════════════════════════════════════════════════

class TestTextureEncounterTick:
    """Test texture_encounter_tick triggers encounters during transit."""

    def _make_ctx(self, ships, sessions_by_room=None):
        """Build a minimal TickContext-like object."""
        ctx = MagicMock()
        ctx.ships_in_space = ships
        ctx.db = AsyncMock()
        mock_sm = MagicMock()
        if sessions_by_room:
            def _sessions_in_room(room_id):
                return sessions_by_room.get(room_id, [])
            mock_sm.sessions_in_room = _sessions_in_room
        else:
            mock_sm.sessions_in_room = MagicMock(return_value=[])
        ctx.session_mgr = mock_sm
        return ctx

    def _make_ship(self, ship_id=1, bridge=100, zone="tatooine_deep_space",
                   sublight=False, hyperspace=False, docked=False):
        systems = {
            "current_zone": zone,
            "sublight_transit": sublight,
            "in_hyperspace": hyperspace,
        }
        return {
            "id": ship_id,
            "bridge_room_id": bridge,
            "docked_at": 1 if docked else None,
            "systems": json.dumps(systems),
        }

    @pytest.mark.asyncio
    async def test_no_trigger_when_not_in_transit(self):
        """Ships not in transit should never trigger texture encounters."""
        from server.tick_handlers_ships import texture_encounter_tick
        ship = self._make_ship(sublight=False, hyperspace=False)
        ctx = self._make_ctx([ship])

        with patch("engine.space_encounters.get_encounter_manager") as mock_mgr:
            # Run many ticks — should never create an encounter
            for _ in range(100):
                await texture_encounter_tick(ctx)
            mock_mgr.return_value.create_encounter.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_trigger_when_docked(self):
        """Docked ships should be skipped."""
        from server.tick_handlers_ships import texture_encounter_tick
        ship = self._make_ship(sublight=True, docked=True)
        ctx = self._make_ctx([ship])

        with patch("engine.space_encounters.get_encounter_manager") as mock_mgr:
            for _ in range(100):
                await texture_encounter_tick(ctx)
            mock_mgr.return_value.create_encounter.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_trigger_without_player_aboard(self):
        """Ships with no player sessions on bridge are skipped."""
        from server.tick_handlers_ships import texture_encounter_tick
        ship = self._make_ship(sublight=True)
        # Empty sessions on bridge
        ctx = self._make_ctx([ship], sessions_by_room={100: []})

        with patch("engine.space_encounters.get_encounter_manager") as mock_mgr:
            for _ in range(100):
                await texture_encounter_tick(ctx)
            mock_mgr.return_value.create_encounter.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_during_sublight_transit(self):
        """Ships in sublight transit with a player aboard should eventually trigger."""
        from server.tick_handlers_ships import texture_encounter_tick
        ship = self._make_ship(sublight=True)
        mock_session = MagicMock()
        mock_session.character = {"id": 1, "name": "TestPilot"}
        ctx = self._make_ctx([ship], sessions_by_room={100: [mock_session]})

        with patch("engine.space_encounters.get_encounter_manager") as mock_mgr_fn:
            mock_mgr = MagicMock()
            mock_mgr.create_encounter = AsyncMock(return_value=MagicMock())
            mock_mgr_fn.return_value = mock_mgr

            # Force random to always succeed
            with patch("server.tick_handlers_ships.random") as mock_random:
                mock_random.random.return_value = 0.001  # Below any threshold
                mock_random.choices.return_value = ["mechanical"]

                await texture_encounter_tick(ctx)

                mock_mgr.create_encounter.assert_called_once()
                call_args = mock_mgr.create_encounter.call_args
                assert call_args.kwargs.get("encounter_type") == "mechanical"

    @pytest.mark.asyncio
    async def test_trigger_during_hyperspace(self):
        """Ships in hyperspace should also trigger texture encounters."""
        from server.tick_handlers_ships import texture_encounter_tick
        ship = self._make_ship(hyperspace=True)
        mock_session = MagicMock()
        mock_session.character = {"id": 1}
        ctx = self._make_ctx([ship], sessions_by_room={100: [mock_session]})

        with patch("engine.space_encounters.get_encounter_manager") as mock_mgr_fn:
            mock_mgr = MagicMock()
            mock_mgr.create_encounter = AsyncMock(return_value=MagicMock())
            mock_mgr_fn.return_value = mock_mgr
            with patch("server.tick_handlers_ships.random") as mock_random:
                mock_random.random.return_value = 0.001
                mock_random.choices.return_value = ["cargo"]
                await texture_encounter_tick(ctx)
                mock_mgr.create_encounter.assert_called_once()

    @pytest.mark.asyncio
    async def test_security_scaling(self):
        """Secured zones should have much lower trigger chance."""
        from server.tick_handlers_ships import texture_encounter_tick

        triggered_secured = 0
        triggered_lawless = 0
        iterations = 5000

        for security, zone in [("secured", "corellia_orbit"),
                               ("lawless", "kessel_approach")]:
            ship = self._make_ship(sublight=True, zone=zone)
            mock_session = MagicMock()
            mock_session.character = {"id": 1}
            ctx = self._make_ctx([ship], sessions_by_room={100: [mock_session]})

            with patch("engine.space_encounters.get_encounter_manager") as mock_mgr_fn:
                mock_mgr = MagicMock()
                mock_mgr.create_encounter = AsyncMock(return_value=MagicMock())
                mock_mgr_fn.return_value = mock_mgr

                for _ in range(iterations):
                    await texture_encounter_tick(ctx)

                count = mock_mgr.create_encounter.call_count
                if security == "secured":
                    triggered_secured = count
                else:
                    triggered_lawless = count

        # Lawless should trigger significantly more than secured
        assert triggered_lawless > triggered_secured, (
            f"lawless={triggered_lawless} should exceed secured={triggered_secured}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. NPC combat zone-change cleanup
# ══════════════════════════════════════════════════════════════════════════════

class TestHyperspaceCombatCleanup:
    """Test that NPC combatants are cleaned up when player enters hyperspace."""

    def test_combatant_remove_method_exists(self):
        """NpcSpaceCombatManager has remove_combatant and get_combatant_targeting."""
        from engine.npc_space_combat_ai import NpcSpaceCombatManager
        mgr = NpcSpaceCombatManager()
        assert hasattr(mgr, "remove_combatant")
        assert hasattr(mgr, "get_combatant_targeting")

    def test_encounter_manager_resolve_exists(self):
        """EncounterManager has resolve and get_encounter methods."""
        from engine.space_encounters import EncounterManager
        mgr = EncounterManager()
        assert hasattr(mgr, "resolve")
        assert hasattr(mgr, "get_encounter")

    def test_get_combatant_targeting_returns_none_when_empty(self):
        """get_combatant_targeting returns None when no combatants exist."""
        from engine.npc_space_combat_ai import NpcSpaceCombatManager
        mgr = NpcSpaceCombatManager()
        result = mgr.get_combatant_targeting(999)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. Silent except/pass invariant
# ══════════════════════════════════════════════════════════════════════════════

class TestSilentExceptInvariant:
    """Enforce zero silent except/pass blocks in production code."""

    def test_no_silent_except_pass_in_production(self):
        """No production .py file should have except Exception followed by pass."""
        violations = []
        project_root = Path(__file__).resolve().parent.parent

        for dirpath, _, filenames in os.walk(project_root):
            # Skip non-production dirs
            rel = os.path.relpath(dirpath, project_root)
            if any(skip in rel for skip in ["venv", "__pycache__", "tests", ".git"]):
                continue
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                filepath = os.path.join(dirpath, fname)
                with open(filepath) as fh:
                    lines = fh.readlines()
                for i, line in enumerate(lines):
                    if "except Exception" in line or "except:" in line:
                        for j in range(i + 1, min(i + 4, len(lines))):
                            stripped = lines[j].strip()
                            if stripped == "":
                                continue
                            if stripped == "pass":
                                violations.append(f"{filepath}:{i+1}")
                            break

        assert violations == [], (
            f"Found {len(violations)} silent except/pass blocks:\n"
            + "\n".join(violations)
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Faction mission board
# ══════════════════════════════════════════════════════════════════════════════

class TestFactionMissions:
    """Test faction mission generation and rep-gating."""

    def test_faction_mission_config_exists(self):
        """FACTION_MISSION_CONFIG should define at least empire, rebel, hutt."""
        from engine.missions import FACTION_MISSION_CONFIG
        assert "empire" in FACTION_MISSION_CONFIG
        assert "rebel" in FACTION_MISSION_CONFIG
        assert "hutt" in FACTION_MISSION_CONFIG

    def test_generate_faction_mission_returns_mission(self):
        """generate_faction_mission should return a Mission with faction_code set."""
        from engine.missions import generate_faction_mission
        m = generate_faction_mission("empire")
        assert m is not None
        assert m.faction_code == "empire"
        assert m.faction_rep_required > 0

    def test_generate_faction_mission_invalid_code_returns_none(self):
        """Unknown faction code returns None."""
        from engine.missions import generate_faction_mission
        m = generate_faction_mission("nonexistent_faction")
        assert m is None

    def test_faction_mission_reward_multiplier(self):
        """Faction missions should pay more than base missions of the same type."""
        from engine.missions import generate_faction_mission, FACTION_MISSION_CONFIG
        # The config specifies a reward_mult > 1.0 for each faction
        for fc, cfg in FACTION_MISSION_CONFIG.items():
            mult = cfg.get("reward_mult", 1.0)
            assert mult > 1.0, (
                f"Faction '{fc}' should have reward_mult > 1.0, got {mult}"
            )

        # Also verify a faction mission actually has faction_code set
        m = generate_faction_mission("empire", skill_level=4)
        assert m is not None
        assert m.faction_code == "empire"
        assert m.reward > 0

    def test_faction_mission_title_has_badge(self):
        """Faction mission titles should be prefixed with [FACTION]."""
        from engine.missions import generate_faction_mission
        m = generate_faction_mission("rebel")
        assert m is not None
        assert m.title.startswith("[REBEL]")

    def test_mission_to_dict_includes_faction_fields(self):
        """Mission.to_dict() should include faction_code and faction_rep_required."""
        from engine.missions import generate_faction_mission
        m = generate_faction_mission("hutt")
        d = m.to_dict()
        assert "faction_code" in d
        assert d["faction_code"] == "hutt"
        assert "faction_rep_required" in d

    def test_mission_from_dict_roundtrip(self):
        """Mission should survive to_dict -> from_dict roundtrip."""
        from engine.missions import generate_faction_mission, Mission
        m = generate_faction_mission("empire")
        d = m.to_dict()
        m2 = Mission.from_dict(d)
        assert m2.faction_code == "empire"
        assert m2.faction_rep_required == m.faction_rep_required
        assert m2.reward == m.reward


# ══════════════════════════════════════════════════════════════════════════════
# 5. Encounter manager integration
# ══════════════════════════════════════════════════════════════════════════════

class TestEncounterManagerIntegration:
    """Test encounter manager resolve with player_fled_hyperspace outcome."""

    def test_resolve_with_custom_outcome(self):
        """Resolving an encounter with a custom outcome should set it."""
        from engine.space_encounters import (
            SpaceEncounter, get_encounter_manager, EncounterManager,
        )
        mgr = EncounterManager()  # fresh instance for test isolation
        enc = SpaceEncounter(
            id="test-001",
            encounter_type="patrol",
            zone_id="tatooine_deep_space",
            target_ship_id=42,
            target_bridge_room=100,
            state="active",
        )
        mgr._encounters[42] = enc

        mgr.resolve(enc, outcome="player_fled_hyperspace")
        assert enc.state == "resolved"
        assert enc.outcome == "player_fled_hyperspace"
        assert 42 not in mgr._encounters


class TestTextureHandlerRegistration:
    """Test that all texture encounter handlers are properly registered."""

    def test_texture_handlers_registered(self):
        """register_texture_handlers should register mechanical, cargo, contact."""
        from engine.space_encounters import EncounterManager
        from engine.encounter_texture import register_texture_handlers
        mgr = EncounterManager()
        register_texture_handlers(mgr)
        # Handlers are stored as (type, event) tuple keys
        assert ("mechanical", "setup") in mgr._handlers
        assert ("cargo", "setup") in mgr._handlers
        assert ("contact", "setup") in mgr._handlers


# ══════════════════════════════════════════════════════════════════════════════
# 6. Trade goods pricing fix (v29)
# ══════════════════════════════════════════════════════════════════════════════

class TestTradeGoodsPricing:
    """Test the v29 trade goods pricing rebalance."""

    def test_source_price_is_70_percent(self):
        """Source planets should sell at 70% of base price."""
        from engine.trading import TRADE_GOODS, get_planet_price
        good = TRADE_GOODS["raw_ore"]
        # Raw ore source = tatooine, base = 100
        price = get_planet_price(good, "tatooine")
        assert price == 70, f"Expected 70, got {price}"

    def test_demand_price_is_140_percent(self):
        """Demand planets should buy at 140% of base price."""
        from engine.trading import TRADE_GOODS, get_planet_price
        good = TRADE_GOODS["raw_ore"]
        # Raw ore demand = corellia, base = 100
        price = get_planet_price(good, "corellia")
        assert price == 140, f"Expected 140, got {price}"

    def test_normal_price_is_100_percent(self):
        """Non-source non-demand planets use base price."""
        from engine.trading import TRADE_GOODS, get_planet_price
        good = TRADE_GOODS["raw_ore"]
        # Raw ore: nar_shaddaa is neither source nor demand
        price = get_planet_price(good, "nar_shaddaa")
        assert price == 100, f"Expected 100, got {price}"

    def test_margin_is_100_percent(self):
        """Source→demand margin should be 100% (buy at 70, sell at 140)."""
        from engine.trading import TRADE_GOODS, get_planet_price
        good = TRADE_GOODS["raw_ore"]
        buy = get_planet_price(good, "tatooine")
        sell = get_planet_price(good, "corellia")
        margin = (sell - buy) / buy * 100
        assert 99 <= margin <= 101, f"Expected ~100% margin, got {margin:.1f}%"

    def test_old_300_percent_margin_is_gone(self):
        """The old 300% exploit margin should not exist on any route."""
        from engine.trading import TRADE_GOODS, get_planet_price
        for good in TRADE_GOODS.values():
            for src in good.source:
                for dst in good.demand:
                    buy = get_planet_price(good, src)
                    sell = get_planet_price(good, dst)
                    margin = (sell - buy) / buy * 100 if buy > 0 else 0
                    assert margin < 150, (
                        f"{good.name} {src}→{dst}: margin {margin:.0f}% "
                        f"exceeds 150% (buy={buy}, sell={sell})"
                    )


class TestDemandPool:
    """Test demand depression mechanics."""

    def test_no_depression_initially(self):
        """Fresh demand pool has zero depression."""
        from engine.trading import DemandPool
        pool = DemandPool()
        assert pool.get_depression("tatooine", "luxury_goods") == 0.0

    def test_depression_increases_with_sales(self):
        """Selling cargo increases demand depression."""
        from engine.trading import DemandPool
        pool = DemandPool()
        pool.record_sale("tatooine", "luxury_goods", 10)
        dep = pool.get_depression("tatooine", "luxury_goods")
        assert dep > 0, f"Expected positive depression, got {dep}"
        assert abs(dep - 0.05) < 0.001, f"Expected 5% (10t × 0.5%), got {dep*100:.1f}%"

    def test_depression_caps_at_max(self):
        """Depression cannot exceed MAX_DEPRESSION (30%)."""
        from engine.trading import DemandPool, MAX_DEPRESSION
        pool = DemandPool()
        pool.record_sale("tatooine", "luxury_goods", 1000)
        dep = pool.get_depression("tatooine", "luxury_goods")
        assert dep == MAX_DEPRESSION, f"Expected {MAX_DEPRESSION}, got {dep}"

    def test_depression_per_planet_per_good(self):
        """Depression is tracked per (planet, good) pair."""
        from engine.trading import DemandPool
        pool = DemandPool()
        pool.record_sale("tatooine", "luxury_goods", 20)
        pool.record_sale("corellia", "raw_ore", 10)
        assert pool.get_depression("tatooine", "luxury_goods") > pool.get_depression("corellia", "raw_ore")
        assert pool.get_depression("tatooine", "raw_ore") == 0.0

    def test_depressed_price_never_below_normal(self):
        """Even at max depression, demand price should not drop below normal."""
        from engine.trading import TRADE_GOODS, get_planet_price, DemandPool, DEMAND_POOL
        # Save and replace singleton for test isolation
        old_pool = DEMAND_POOL._sales.copy()
        DEMAND_POOL._sales = {}
        DEMAND_POOL.record_sale("corellia", "raw_ore", 200)  # max depression
        good = TRADE_GOODS["raw_ore"]
        eff = get_planet_price(good, "corellia", include_demand_depression=True)
        base = good.base_price  # 100 = PRICE_NORMAL
        assert eff >= base, f"Depressed price {eff} below base {base}"
        # Restore
        DEMAND_POOL._sales = old_pool

    def test_recent_volume_tracking(self):
        """get_recent_volume returns correct tonnage."""
        from engine.trading import DemandPool
        pool = DemandPool()
        pool.record_sale("kessel", "foodstuffs", 5)
        pool.record_sale("kessel", "foodstuffs", 10)
        assert pool.get_recent_volume("kessel", "foodstuffs") == 15


class TestSupplyPoolCaps:
    """Test that supply caps are tightened in v29."""

    def test_luxury_goods_cap(self):
        """Luxury goods should have a tight supply cap."""
        from engine.trading import MAX_UNITS_PER_REFRESH
        assert MAX_UNITS_PER_REFRESH["luxury_goods"] <= 8

    def test_foodstuffs_loosest_cap(self):
        """Foodstuffs should have the loosest cap (bulk/cheap)."""
        from engine.trading import MAX_UNITS_PER_REFRESH
        assert MAX_UNITS_PER_REFRESH["foodstuffs"] >= 15
        assert MAX_UNITS_PER_REFRESH["foodstuffs"] > MAX_UNITS_PER_REFRESH["luxury_goods"]
