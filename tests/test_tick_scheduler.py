"""
Tests for TickScheduler, TickContext, and the tick handlers migrated in
review-fixes v1/v2.

These are sync-compatible where possible. Async handler tests use
asyncio.run() directly to avoid the pytest-asyncio dependency.

Coverage:
  - TickScheduler: register, interval dispatch, isolation (one handler
    failing doesn't block others), offset support
  - SupplyPool: available, consume, refresh, carryover, per-planet/good
    isolation
  - asteroid_collision_tick: skip docked, skip transit, skip non-heavy,
    hit on low roll, miss on high roll
  - hyperspace_arrival_tick: countdown decrement, arrival state mutations,
    ctx dict kept fresh
  - space_anomaly_tick: active-zone detection, expiry + spawn called
"""
from __future__ import annotations

import asyncio
import json
import time
import unittest
from dataclasses import dataclass, field
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch, call

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.tick_scheduler import TickScheduler, TickContext


# ── Helpers ──────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.run(coro)


def make_ctx(**kwargs):
    """Minimal TickContext for handler tests."""
    # session_mgr: sessions_in_room is sync; broadcast_to_room is async.
    session_mgr = MagicMock()
    session_mgr.sessions_in_room.return_value = []
    session_mgr.broadcast_to_room = AsyncMock()
    defaults = dict(
        server=MagicMock(),
        db=AsyncMock(),
        session_mgr=session_mgr,
        tick_count=1,
        ships_in_space=[],
    )
    defaults.update(kwargs)
    return TickContext(**defaults)


def ship(*, id=1, bridge=101, docked=None, systems=None, hull_damage=0,
         template="x_wing", current_zone=None):
    """Build a minimal ship dict as the DB would return it."""
    sys_dict = systems or {}
    return {
        "id": id,
        "bridge_room_id": bridge,
        "docked_at": docked,
        "systems": json.dumps(sys_dict),
        "hull_damage": hull_damage,
        "template": template,
        "current_zone": current_zone,
        "crew": "{}",
    }


# ── TickScheduler ────────────────────────────────────────────────────────────

class TestTickScheduler(unittest.TestCase):

    def test_register_adds_handler(self):
        sched = TickScheduler()
        sched.register("foo", AsyncMock(), interval=1)
        self.assertEqual(sched.handler_count(), 1)

    def test_interval_zero_raises(self):
        sched = TickScheduler()
        with self.assertRaises(ValueError):
            sched.register("bad", AsyncMock(), interval=0)

    def test_interval_1_fires_every_tick(self):
        sched = TickScheduler()
        fn = AsyncMock()
        sched.register("every", fn, interval=1)
        for tick in range(1, 6):
            ctx = make_ctx(tick_count=tick)
            run(sched.run_tick(ctx))
        self.assertEqual(fn.call_count, 5)

    def test_interval_3_fires_at_multiples(self):
        sched = TickScheduler()
        fn = AsyncMock()
        sched.register("every3", fn, interval=3)
        for tick in range(1, 10):
            run(sched.run_tick(make_ctx(tick_count=tick)))
        # ticks 3, 6, 9 → 3 fires
        self.assertEqual(fn.call_count, 3)

    def test_offset_shifts_firing_tick(self):
        sched = TickScheduler()
        fn = AsyncMock()
        # interval=5, offset=2: fires when (tick-2) % 5 == 0
        # i.e. ticks 2, 7, 12 → 3 fires in range 1..12
        sched.register("offset", fn, interval=5, offset=2)
        for tick in range(1, 13):
            run(sched.run_tick(make_ctx(tick_count=tick)))
        self.assertEqual(fn.call_count, 3)

    def test_offset_does_not_fire_at_interval_without_offset(self):
        sched = TickScheduler()
        fn = AsyncMock()
        # interval=5, offset=2: should NOT fire at tick 5 (would fire without offset)
        sched.register("offset", fn, interval=5, offset=2)
        run(sched.run_tick(make_ctx(tick_count=5)))
        fn.assert_not_called()

    def test_failing_handler_does_not_block_others(self):
        sched = TickScheduler()
        bad = AsyncMock(side_effect=RuntimeError("boom"))
        good = AsyncMock()
        sched.register("bad", bad, interval=1)
        sched.register("good", good, interval=1)
        run(sched.run_tick(make_ctx(tick_count=1)))
        good.assert_called_once()

    def test_multiple_handlers_all_fire(self):
        sched = TickScheduler()
        fns = [AsyncMock() for _ in range(4)]
        for i, fn in enumerate(fns):
            sched.register(f"h{i}", fn, interval=1)
        run(sched.run_tick(make_ctx(tick_count=1)))
        for fn in fns:
            fn.assert_called_once()

    def test_ctx_passed_to_handler(self):
        sched = TickScheduler()
        received = []
        async def capture(ctx):
            received.append(ctx)
        sched.register("capture", capture, interval=1)
        ctx = make_ctx(tick_count=42)
        run(sched.run_tick(ctx))
        self.assertEqual(received[0].tick_count, 42)


# ── SupplyPool ───────────────────────────────────────────────────────────────

class TestSupplyPool(unittest.TestCase):

    def _pool(self):
        from engine.trading import SupplyPool
        return SupplyPool()

    def test_first_access_returns_full_supply(self):
        p = self._pool()
        avail = p.available("corellia", "luxury_goods")
        self.assertGreater(avail, 0)

    def test_consume_reduces_supply(self):
        p = self._pool()
        before = p.available("corellia", "luxury_goods")
        ok = p.consume("corellia", "luxury_goods", 5)
        self.assertTrue(ok)
        self.assertEqual(p.available("corellia", "luxury_goods"), before - 5)

    def test_consume_beyond_available_returns_false(self):
        p = self._pool()
        ok = p.consume("corellia", "luxury_goods", 9999)
        self.assertFalse(ok)

    def test_consume_beyond_available_does_not_change_supply(self):
        p = self._pool()
        before = p.available("corellia", "luxury_goods")
        p.consume("corellia", "luxury_goods", 9999)
        self.assertEqual(p.available("corellia", "luxury_goods"), before)

    def test_different_planets_isolated(self):
        p = self._pool()
        p.consume("corellia", "luxury_goods", 5)
        avail_tat = p.available("tatooine", "luxury_goods")
        from engine.trading import _max_units
        self.assertEqual(avail_tat, _max_units("luxury_goods"))

    def test_different_goods_isolated(self):
        p = self._pool()
        p.consume("corellia", "luxury_goods", 5)
        avail_food = p.available("corellia", "foodstuffs")
        from engine.trading import _max_units
        self.assertEqual(avail_food, _max_units("foodstuffs"))

    def test_refresh_replenishes_after_interval(self):
        from engine.trading import SUPPLY_REFRESH_SECONDS
        p = self._pool()
        p.consume("corellia", "spice", 3)
        before = p.available("corellia", "spice")
        # Fake time forward past one refresh interval
        key = ("corellia", "spice")
        units, last_ts = p._pools[key]
        p._pools[key] = (units, last_ts - SUPPLY_REFRESH_SECONDS - 1)
        after = p.available("corellia", "spice")
        self.assertGreater(after, before)

    def test_carryover_does_not_exceed_cap(self):
        from engine.trading import SUPPLY_REFRESH_SECONDS, SUPPLY_CARRYOVER_MULT, _max_units
        p = self._pool()
        max_u = _max_units("luxury_goods")
        cap = max_u * SUPPLY_CARRYOVER_MULT
        # Seed at full, advance time by many intervals
        key = ("corellia", "luxury_goods")
        p.available("corellia", "luxury_goods")  # seed
        units, last_ts = p._pools[key]
        p._pools[key] = (units, last_ts - SUPPLY_REFRESH_SECONDS * 100)
        self.assertLessEqual(p.available("corellia", "luxury_goods"), cap)

    def test_seconds_until_refresh_zero_on_fresh_pool(self):
        p = self._pool()
        p.available("corellia", "spice")  # seed
        secs = p.seconds_until_refresh("corellia", "spice")
        from engine.trading import SUPPLY_REFRESH_SECONDS
        self.assertLessEqual(secs, SUPPLY_REFRESH_SECONDS)
        self.assertGreaterEqual(secs, 0)


# ── asteroid_collision_tick ───────────────────────────────────────────────────

class TestAsteroidCollisionTick(unittest.TestCase):

    def _run(self, ctx):
        from server.tick_handlers_ships import asteroid_collision_tick
        run(asteroid_collision_tick(ctx))

    def _zone(self, density="heavy"):
        z = MagicMock()
        z.hazards = {"asteroid_density": density}
        return z

    def test_skips_docked_ships(self):
        s = ship(docked="some_dock", systems={"current_zone": "asteroid_belt"})
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"asteroid_belt": self._zone()}):
            self._run(ctx)
        ctx.db.update_ship.assert_not_called()

    def test_skips_ships_in_hyperspace(self):
        s = ship(systems={"in_hyperspace": True, "current_zone": "asteroid_belt"})
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"asteroid_belt": self._zone()}):
            self._run(ctx)
        ctx.db.update_ship.assert_not_called()

    def test_skips_ships_in_sublight_transit(self):
        s = ship(systems={"sublight_transit": True, "current_zone": "asteroid_belt"})
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"asteroid_belt": self._zone()}):
            self._run(ctx)
        ctx.db.update_ship.assert_not_called()

    def test_skips_non_heavy_density(self):
        s = ship(systems={"current_zone": "light_field"})
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"light_field": self._zone("light")}):
            self._run(ctx)
        ctx.db.update_ship.assert_not_called()

    def test_no_damage_on_successful_roll(self):
        s = ship(systems={"current_zone": "belt", "_cached_pilot_dice": 3})
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"belt": self._zone()}), \
             patch("server.tick_handlers_ships.random.randint", return_value=6):
            self._run(ctx)
        ctx.db.update_ship.assert_not_called()

    def test_damage_on_failed_roll(self):
        s = ship(systems={"current_zone": "belt", "_cached_pilot_dice": 2}, hull_damage=2)
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"belt": self._zone()}), \
             patch("server.tick_handlers_ships.random.randint", return_value=1):
            self._run(ctx)
        ctx.db.update_ship.assert_called_once_with(1, hull_damage=3)

    def test_damage_updates_shared_dict(self):
        s = ship(systems={"current_zone": "belt"}, hull_damage=0)
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"belt": self._zone()}), \
             patch("server.tick_handlers_ships.random.randint", return_value=1):
            self._run(ctx)
        self.assertEqual(ctx.ships_in_space[0]["hull_damage"], 1)

    def test_bridge_notification_on_hit(self):
        s = ship(systems={"current_zone": "belt"}, hull_damage=0, bridge=55)
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"belt": self._zone()}), \
             patch("server.tick_handlers_ships.random.randint", return_value=1):
            self._run(ctx)
        ctx.session_mgr.broadcast_to_room.assert_called_once()
        args = ctx.session_mgr.broadcast_to_room.call_args[0]
        self.assertEqual(args[0], 55)
        self.assertIn("ASTEROID", args[1])


# ── hyperspace_arrival_tick ───────────────────────────────────────────────────

class TestHyperspaceArrivalTick(unittest.TestCase):

    def _run(self, ctx):
        from server.tick_handlers_ships import hyperspace_arrival_tick
        run(hyperspace_arrival_tick(ctx))

    def _hs_ship(self, ticks_remaining=1, dest="corellia", dest_name="Corellia",
                  bridge=101, template="x_wing"):
        return ship(
            id=10, bridge=bridge, template=template,
            systems={
                "in_hyperspace": True,
                "hyperspace_ticks_remaining": ticks_remaining,
                "hyperspace_dest": dest,
                "hyperspace_dest_name": dest_name,
            }
        )

    def test_skips_non_hyperspace_ships(self):
        s = ship(systems={})
        ctx = make_ctx(ships_in_space=[s])
        self._run(ctx)
        ctx.db.update_ship.assert_not_called()

    def test_countdown_decrements(self):
        s = self._hs_ship(ticks_remaining=5)
        ctx = make_ctx(ships_in_space=[s])
        zones = {"corellia_orbit": MagicMock()}
        with patch("engine.npc_space_traffic.ZONES", zones):
            self._run(ctx)
        saved_sys = json.loads(ctx.db.update_ship.call_args[1]["systems"])
        self.assertEqual(saved_sys["hyperspace_ticks_remaining"], 4)
        self.assertTrue(saved_sys["in_hyperspace"])

    def test_countdown_updates_shared_dict(self):
        s = self._hs_ship(ticks_remaining=3)
        ctx = make_ctx(ships_in_space=[s])
        with patch("engine.npc_space_traffic.ZONES", {"corellia_orbit": MagicMock()}):
            self._run(ctx)
        sys_after = json.loads(ctx.ships_in_space[0]["systems"])
        self.assertEqual(sys_after["hyperspace_ticks_remaining"], 2)

    def test_arrival_clears_hyperspace_flags(self):
        s = self._hs_ship(ticks_remaining=1, dest="corellia")
        ctx = make_ctx(ships_in_space=[s])
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock(speed=6)
        mock_grid = MagicMock()
        zones = {"corellia_orbit": MagicMock()}
        ctx.db.get_ship_by_bridge = AsyncMock(return_value=s)
        with patch("engine.npc_space_traffic.ZONES", zones), \
             patch("engine.starships.get_ship_registry", return_value=mock_registry), \
             patch("parser.space_commands.get_space_grid", return_value=mock_grid), \
             patch("parser.space_commands.broadcast_space_state", new=AsyncMock()):
            self._run(ctx)
        saved_sys = json.loads(ctx.db.update_ship.call_args[1]["systems"])
        self.assertFalse(saved_sys["in_hyperspace"])
        self.assertNotIn("hyperspace_dest", saved_sys)
        self.assertNotIn("hyperspace_ticks_remaining", saved_sys)
        self.assertEqual(saved_sys["current_zone"], "corellia_orbit")
        self.assertEqual(saved_sys["location"], "corellia")

    def test_arrival_updates_shared_dict(self):
        s = self._hs_ship(ticks_remaining=1, dest="corellia")
        ctx = make_ctx(ships_in_space=[s])
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock(speed=6)
        ctx.db.get_ship_by_bridge = AsyncMock(return_value=s)
        with patch("engine.npc_space_traffic.ZONES", {"corellia_orbit": MagicMock()}), \
             patch("engine.starships.get_ship_registry", return_value=mock_registry), \
             patch("parser.space_commands.get_space_grid", return_value=MagicMock()), \
             patch("parser.space_commands.broadcast_space_state", new=AsyncMock()):
            self._run(ctx)
        self.assertEqual(ctx.ships_in_space[0]["current_zone"], "corellia_orbit")

    def test_arrival_readds_to_space_grid(self):
        s = self._hs_ship(ticks_remaining=1, dest="corellia")
        ctx = make_ctx(ships_in_space=[s])
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock(speed=7)
        mock_grid = MagicMock()
        ctx.db.get_ship_by_bridge = AsyncMock(return_value=s)
        with patch("engine.npc_space_traffic.ZONES", {"corellia_orbit": MagicMock()}), \
             patch("engine.starships.get_ship_registry", return_value=mock_registry), \
             patch("parser.space_commands.get_space_grid", return_value=mock_grid), \
             patch("parser.space_commands.broadcast_space_state", new=AsyncMock()):
            self._run(ctx)
        mock_grid.add_ship.assert_called_once_with(10, 7)

    def test_arrival_bridge_notification(self):
        s = self._hs_ship(ticks_remaining=1, dest="corellia",
                          dest_name="Corellia", bridge=77)
        ctx = make_ctx(ships_in_space=[s])
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock(speed=5)
        ctx.db.get_ship_by_bridge = AsyncMock(return_value=s)
        with patch("engine.npc_space_traffic.ZONES", {"corellia_orbit": MagicMock()}), \
             patch("engine.starships.get_ship_registry", return_value=mock_registry), \
             patch("parser.space_commands.get_space_grid", return_value=MagicMock()), \
             patch("parser.space_commands.broadcast_space_state", new=AsyncMock()):
            self._run(ctx)
        broadcast_calls = ctx.session_mgr.broadcast_to_room.call_args_list
        rooms_notified = [c[0][0] for c in broadcast_calls]
        self.assertIn(77, rooms_notified)
        msg = next(c[0][1] for c in broadcast_calls if c[0][0] == 77)
        self.assertIn("Corellia", msg)

    def test_fallback_zone_when_orbit_missing(self):
        s = self._hs_ship(ticks_remaining=1, dest="unknown_planet")
        ctx = make_ctx(ships_in_space=[s])
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock(speed=5)
        # ZONES has tatooine_orbit but not unknown_planet_orbit
        zones = {"tatooine_orbit": MagicMock()}
        ctx.db.get_ship_by_bridge = AsyncMock(return_value=s)
        with patch("engine.npc_space_traffic.ZONES", zones), \
             patch("engine.starships.get_ship_registry", return_value=mock_registry), \
             patch("parser.space_commands.get_space_grid", return_value=MagicMock()), \
             patch("parser.space_commands.broadcast_space_state", new=AsyncMock()):
            self._run(ctx)
        saved_sys = json.loads(ctx.db.update_ship.call_args[1]["systems"])
        self.assertEqual(saved_sys["current_zone"], "tatooine_orbit")


# ── space_anomaly_tick ────────────────────────────────────────────────────────

class TestSpaceAnomalyTick(unittest.TestCase):

    def _run(self, ctx):
        from server.tick_handlers_ships import space_anomaly_tick
        run(space_anomaly_tick(ctx))

    def test_no_ships_no_calls(self):
        ctx = make_ctx(ships_in_space=[])
        mock_expiry = MagicMock()
        mock_spawn = MagicMock()
        with patch("engine.space_anomalies.tick_anomaly_expiry", mock_expiry), \
             patch("engine.space_anomalies.spawn_anomalies_for_zone", mock_spawn), \
             patch("engine.npc_space_traffic.ZONES", {}):
            self._run(ctx)
        mock_expiry.assert_not_called()
        mock_spawn.assert_not_called()

    def test_collects_active_zones(self):
        ships = [
            ship(id=1, systems={"current_zone": "tatooine_orbit"}),
            ship(id=2, systems={"current_zone": "corellia_orbit"}),
            ship(id=3, systems={"current_zone": "tatooine_orbit"}),  # duplicate
        ]
        ctx = make_ctx(ships_in_space=ships)
        mock_expiry = MagicMock()
        mock_spawn = MagicMock()
        mock_zone = MagicMock()
        mock_zone.type.value = "nebula"
        zones = {"tatooine_orbit": mock_zone, "corellia_orbit": mock_zone}
        with patch("engine.space_anomalies.tick_anomaly_expiry", mock_expiry), \
             patch("engine.space_anomalies.spawn_anomalies_for_zone", mock_spawn), \
             patch("engine.npc_space_traffic.ZONES", zones):
            self._run(ctx)
        # Only 2 unique zones, expiry called once per unique zone
        self.assertEqual(mock_expiry.call_count, 2)
        self.assertEqual(mock_spawn.call_count, 2)

    def test_expiry_called_for_unknown_zone(self):
        """tick_anomaly_expiry is called even if zone not in ZONES dict."""
        s = ship(systems={"current_zone": "mystery_zone"})
        ctx = make_ctx(ships_in_space=[s])
        mock_expiry = MagicMock()
        mock_spawn = MagicMock()
        with patch("engine.space_anomalies.tick_anomaly_expiry", mock_expiry), \
             patch("engine.space_anomalies.spawn_anomalies_for_zone", mock_spawn), \
             patch("engine.npc_space_traffic.ZONES", {}):
            self._run(ctx)
        mock_expiry.assert_called_once_with("mystery_zone")
        mock_spawn.assert_not_called()  # no zone data → no spawn

    def test_skips_ships_with_no_zone(self):
        s = ship(systems={})
        ctx = make_ctx(ships_in_space=[s])
        mock_expiry = MagicMock()
        with patch("engine.space_anomalies.tick_anomaly_expiry", mock_expiry), \
             patch("engine.space_anomalies.spawn_anomalies_for_zone", MagicMock()), \
             patch("engine.npc_space_traffic.ZONES", {}):
            self._run(ctx)
        mock_expiry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
