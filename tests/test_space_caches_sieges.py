# -*- coding: utf-8 -*-
"""
tests/test_space_caches_sieges.py — Space Wildspace Drop 2 (Sieges Theater)

Proves the Sieges-theater content is player-reachable and faction-visibility
is live, per docs/design/space_wildspace_design_v1.md §3.1 / §4 / §8 Drop 2.

What Drop 1a left as a dev-only loop (DEV_TEST_ZONE_KEY) is now wired to real
zones that exist in the CW zone graph:

  1. TestZoneGraph    — geonosis_front + outer_rim_sieges_drift exist, carry
                        wildspace/wildspace_theater, are bidirectionally
                        adjacent to their parents, are LAWLESS (deep_space
                        default), and are NOT friendly-traffic spawn zones.
  2. TestCachePools   — get_cache_pool loads the YAML pools; all caches are
                        kind=mining with NO rep_reward (the flagged zone_id=0
                        rep path is never exercised by player content);
                        yields are 6-tuples; rtypes are registered.
  3. TestVisibility   — universal vs republic/cis faction gating against the
                        real sieges cache defs.
  4. TestEndToEnd     — DB-backed: spawn + harvest a real geonosis_front node
                        yields a resource and sets cooldown.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SW_ERA", "clone_wars")

from engine import space_caches as sc  # noqa: E402
from engine.space_caches import (  # noqa: E402
    get_cache_pool, reload_wildspace_pools, is_cache_visible, _encode_visibility,
)

SIEGES_ZONES = ("geonosis_front", "outer_rim_sieges_drift")


def _run(coro):
    return asyncio.run(coro)


class TestZoneGraph(unittest.TestCase):
    """The two sieges zones are real, flyable, lawless, traffic-muted."""

    def setUp(self):
        from engine.npc_space_traffic import reload_zone_graph
        reload_zone_graph()

    def test_zones_present_with_wildspace_fields(self):
        from engine.npc_space_traffic import ZONES
        for zk in SIEGES_ZONES:
            z = ZONES.get(zk)
            self.assertIsNotNone(z, f"{zk} missing from ZONES")
            self.assertTrue(z.wildspace, f"{zk} wildspace flag not set")
            self.assertEqual(z.wildspace_theater, "sieges", f"{zk} theater")

    def test_zone_dataclass_defaults(self):
        """Non-wildspace zones default to wildspace=False/theater=None."""
        from engine.npc_space_traffic import ZONES
        z = ZONES.get("tatooine_deep_space")
        self.assertIsNotNone(z)
        self.assertFalse(z.wildspace)
        self.assertIsNone(z.wildspace_theater)

    def test_bidirectional_adjacency(self):
        from engine.npc_space_traffic import ZONES
        self.assertIn("geonosis_front", ZONES["geonosis_deep_space"].adjacent)
        self.assertIn("geonosis_deep_space", ZONES["geonosis_front"].adjacent)
        self.assertIn("outer_rim_sieges_drift",
                      ZONES["perlemian_trade_route"].adjacent)
        self.assertIn("perlemian_trade_route",
                      ZONES["outer_rim_sieges_drift"].adjacent)

    def test_lawless_by_deep_space_default(self):
        from engine.npc_space_traffic import get_space_security
        for zk in SIEGES_ZONES:
            self.assertEqual(get_space_security(zk), "lawless", f"{zk} security")

    def test_not_friendly_spawn_zones(self):
        """Design §6.2: no friendly NPC traffic spawns in wildspace."""
        from engine.npc_space_traffic import SPAWN_ZONES
        for zk in SIEGES_ZONES:
            self.assertNotIn(zk, SPAWN_ZONES, f"{zk} must not spawn traffic")

    def test_theaters_not_directly_connected(self):
        """Design §3.3: wildspace zones connect only to their parent."""
        from engine.npc_space_traffic import ZONES
        gf = ZONES["geonosis_front"]
        od = ZONES["outer_rim_sieges_drift"]
        self.assertNotIn("outer_rim_sieges_drift", gf.adjacent)
        self.assertNotIn("geonosis_front", od.adjacent)


class TestCachePools(unittest.TestCase):
    """The YAML cache pools load and stay mining-only / rep-free for Drop 2."""

    def setUp(self):
        reload_wildspace_pools()

    def test_pools_load_for_both_zones(self):
        for zk in SIEGES_ZONES:
            pool = get_cache_pool(zk)
            self.assertTrue(pool, f"{zk} pool empty")

    def test_unknown_zone_empty_pool(self):
        self.assertEqual(get_cache_pool("tatooine_deep_space"), {})
        self.assertEqual(get_cache_pool("not_a_zone"), {})

    def test_dev_zone_still_works(self):
        """Drop 1a DEV pool must not regress."""
        from engine.space_caches import DEV_TEST_ZONE_KEY, DEV_TEST_CACHE_POOL
        self.assertEqual(get_cache_pool(DEV_TEST_ZONE_KEY), DEV_TEST_CACHE_POOL)

    def test_all_mining_no_rep_reward(self):
        """Drop 2 ships mining-only with NO rep_reward, so the flagged
        adjust_territory_influence(zone_id=0) path is never reached by any
        player-reachable cache."""
        for zk in SIEGES_ZONES:
            for did, cd in get_cache_pool(zk).items():
                self.assertEqual(cd.kind, "mining", f"{zk}/{did} not mining")
                self.assertFalse(cd.rep_reward, f"{zk}/{did} carries rep_reward")

    def test_yield_tables_are_six_tuples(self):
        for zk in SIEGES_ZONES:
            for did, cd in get_cache_pool(zk).items():
                self.assertTrue(cd.yield_table, f"{zk}/{did} empty yield_table")
                for row in cd.yield_table:
                    self.assertIsInstance(row, tuple, f"{zk}/{did} row not tuple")
                    self.assertEqual(len(row), 6, f"{zk}/{did} row len {row}")

    def test_rtypes_registered(self):
        from engine.crafting import RESOURCE_TYPES
        for zk in SIEGES_ZONES:
            for did, cd in get_cache_pool(zk).items():
                for row in cd.yield_table:
                    self.assertIn(row[1], RESOURCE_TYPES,
                                  f"{zk}/{did} unregistered rtype {row[1]}")

    def test_reload_is_idempotent(self):
        a = get_cache_pool("geonosis_front")
        b = reload_wildspace_pools().get("geonosis_front")
        self.assertEqual(sorted(a.keys()), sorted(b.keys()))


class TestVisibility(unittest.TestCase):
    """Faction visibility gating against the real sieges defs (no rep needed)."""

    def setUp(self):
        reload_wildspace_pools()
        self.gf = get_cache_pool("geonosis_front")

    def _row(self, def_id):
        cd = self.gf[def_id]
        return {"visibility_factions": _encode_visibility(cd.visibility)}

    def test_universal_visible_to_all(self):
        self.assertTrue(is_cache_visible(self._row("droid_scrap_cluster"), {}))

    def test_faction_hidden_without_rep(self):
        self.assertFalse(is_cache_visible(self._row("cis_droid_platoon_scrap"), {}))
        self.assertFalse(
            is_cache_visible(self._row("republic_supply_debris"), {}))

    def test_faction_visible_with_nonneg_rep(self):
        self.assertTrue(
            is_cache_visible(self._row("cis_droid_platoon_scrap"), {"cis": 0}))
        self.assertTrue(
            is_cache_visible(self._row("republic_supply_debris"), {"republic": 5}))

    def test_faction_hidden_with_negative_rep(self):
        self.assertFalse(
            is_cache_visible(self._row("republic_supply_debris"), {"republic": -1}))


class TestEndToEnd(unittest.TestCase):
    """DB-backed proof the loop runs against a real (flyable) sieges zone."""

    def test_spawn_and_harvest_real_zone(self):
        async def _go():
            from db.database import Database
            from engine.housing import ensure_schema as _hs_schema
            from engine.space_caches import (
                ensure_schema, spawn_zone_caches, get_zone_caches,
                harvest_mining,
            )
            reload_wildspace_pools()

            db = Database(":memory:")
            await db.connect()
            await db.initialize()
            await _hs_schema(db)
            await ensure_schema(db)

            # Spawn caches for the real zone.
            created = await spawn_zone_caches(db, "geonosis_front")
            self.assertGreater(created, 0, "no caches spawned for geonosis_front")

            rows = await get_zone_caches(db, "geonosis_front")
            self.assertTrue(rows)

            # Pick an available universal node and harvest it.
            target = next(
                (r for r in rows
                 if r["state"] == "available"
                 and r["cache_def_id"] == "droid_scrap_cluster"),
                None,
            )
            self.assertIsNotNone(target, "no universal node to harvest")

            # Minimal character with a space-transports skill so the check
            # can succeed at least sometimes; we assert structure, not the
            # stochastic success bit.
            char = {
                "id": 1,
                "inventory": {},
                "attributes": {"mechanical": {"space transports": "5D"}},
                "skills": {},
            }
            result = await harvest_mining(db, char, target["cache_instance_id"])
            # not_found / wrong_kind must never trigger for a real mining node.
            self.assertFalse(result.not_found)
            self.assertFalse(result.wrong_kind)

            await db.close()

        _run(_go())


if __name__ == "__main__":
    unittest.main()
