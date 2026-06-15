# -*- coding: utf-8 -*-
"""
tests/test_space_caches_hutt_frontier.py — T3.16 Wildspace Drop 3.

Hutt Frontier theater: two flyable wildspace zones (jundland_drift off
tatooine_deep_space, smugglers_run_periphery off nar_shaddaa_deep_space)
carrying mining + faction caches, built on the Drop 1a framework + the
Drop 2/2b mechanics (faction visibility + rep funnel).

Mirrors tests/test_space_caches_sieges.py (Drop 2). Generic on cache-def
ids (iterates the loaded pools) so it doesn't pin specific content names.

Sections:
  1. TestZoneGraph   — zones present, wildspace, lawless, traffic-muted
  2. TestCachePools  — pools load; mining rep-free; faction caches rep-bearing
  3. TestVisibility  — universal vs faction gating
  4. TestEndToEnd    — DB-backed spawn + mine a real jundland_drift node
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

HUTT_ZONES = ("jundland_drift", "smugglers_run_periphery")

# Parent (non-wildspace) deep-space zones each Hutt zone hangs off of.
HUTT_PARENTS = {
    "jundland_drift": "tatooine_deep_space",
    "smugglers_run_periphery": "nar_shaddaa_deep_space",
}

VALID_FACTION_CODES = {
    "republic", "cis", "jedi_order", "hutt_cartel", "bounty_hunters_guild",
}


def _run(coro):
    return asyncio.run(coro)


class TestZoneGraph(unittest.TestCase):
    """The two Hutt Frontier zones are real, flyable, lawless, traffic-muted."""

    def setUp(self):
        from engine.npc_space_traffic import reload_zone_graph
        reload_zone_graph()

    def test_zones_present_with_wildspace_fields(self):
        from engine.npc_space_traffic import ZONES
        for zk in HUTT_ZONES:
            z = ZONES.get(zk)
            self.assertIsNotNone(z, f"{zk} missing from ZONES")
            self.assertTrue(z.wildspace, f"{zk} wildspace flag not set")
            self.assertEqual(z.wildspace_theater, "hutt_frontier",
                             f"{zk} theater")

    def test_bidirectional_adjacency_to_parent(self):
        from engine.npc_space_traffic import ZONES
        for zk, parent in HUTT_PARENTS.items():
            self.assertIn(zk, ZONES[parent].adjacent,
                          f"{parent} not adjacent to {zk}")
            self.assertIn(parent, ZONES[zk].adjacent,
                          f"{zk} not adjacent to {parent}")

    def test_lawless_by_deep_space_default(self):
        from engine.npc_space_traffic import get_space_security
        for zk in HUTT_ZONES:
            self.assertEqual(get_space_security(zk), "lawless", f"{zk} security")

    def test_not_friendly_spawn_zones(self):
        """Design §6.2: no friendly NPC traffic spawns in wildspace."""
        from engine.npc_space_traffic import SPAWN_ZONES
        for zk in HUTT_ZONES:
            self.assertNotIn(zk, SPAWN_ZONES, f"{zk} must not spawn traffic")

    def test_theaters_not_directly_connected(self):
        """Design §3.3: wildspace zones connect only to their parent — the two
        Hutt zones are not directly linked to each other or to a sieges zone."""
        from engine.npc_space_traffic import ZONES
        jd = ZONES["jundland_drift"]
        self.assertNotIn("smugglers_run_periphery", jd.adjacent)
        self.assertNotIn("geonosis_front", jd.adjacent)


class TestCachePools(unittest.TestCase):
    """The YAML cache pools load: mining nodes rep-free, faction caches
    rep-bearing (Hutt Cartel / Bounty Hunters' Guild)."""

    def setUp(self):
        reload_wildspace_pools()

    def test_pools_load_for_both_zones(self):
        for zk in HUTT_ZONES:
            self.assertTrue(get_cache_pool(zk), f"{zk} pool empty")

    def test_mining_nodes_have_no_rep_reward(self):
        for zk in HUTT_ZONES:
            for did, cd in get_cache_pool(zk).items():
                if cd.kind == "mining":
                    self.assertFalse(cd.rep_reward,
                                     f"{zk}/{did} mining node carries rep_reward")

    def test_faction_caches_present_and_rep_bearing(self):
        found = 0
        for zk in HUTT_ZONES:
            for did, cd in get_cache_pool(zk).items():
                if cd.kind != "faction_cache":
                    continue
                found += 1
                self.assertTrue(cd.rep_reward,
                                f"{zk}/{did} faction cache lacks rep_reward")
                self.assertIsInstance(cd.visibility, list,
                                      f"{zk}/{did} faction cache not faction-gated")
                for code, delta in cd.rep_reward.items():
                    self.assertIn(code, VALID_FACTION_CODES,
                                  f"{zk}/{did} bad faction code {code}")
                    self.assertTrue(1 <= int(delta) <= 5,
                                    f"{zk}/{did} rep delta {delta} not in 1-5")
        self.assertGreaterEqual(found, 2,
                                "expected faction caches across the theater")

    def test_yield_tables_are_six_tuples(self):
        for zk in HUTT_ZONES:
            for did, cd in get_cache_pool(zk).items():
                self.assertTrue(cd.yield_table, f"{zk}/{did} empty yield_table")
                for row in cd.yield_table:
                    self.assertIsInstance(row, tuple, f"{zk}/{did} row not tuple")
                    self.assertEqual(len(row), 6, f"{zk}/{did} row len {row}")

    def test_rtypes_registered(self):
        from engine.crafting import RESOURCE_TYPES
        for zk in HUTT_ZONES:
            for did, cd in get_cache_pool(zk).items():
                for row in cd.yield_table:
                    self.assertIn(row[1], RESOURCE_TYPES,
                                  f"{zk}/{did} unregistered rtype {row[1]}")


class TestVisibility(unittest.TestCase):
    """Faction visibility gating against the real Hutt defs."""

    def setUp(self):
        reload_wildspace_pools()
        self.pool = get_cache_pool("jundland_drift")

    def _row(self, def_id):
        cd = self.pool[def_id]
        return {"visibility_factions": _encode_visibility(cd.visibility)}

    def _first(self, predicate):
        for did, cd in self.pool.items():
            if predicate(cd):
                return did
        return None

    def test_universal_visible_to_all(self):
        did = self._first(lambda cd: cd.visibility == "universal")
        self.assertIsNotNone(did, "no universal cache in jundland_drift")
        self.assertTrue(is_cache_visible(self._row(did), {}))

    def test_faction_cache_gated(self):
        did = self._first(lambda cd: isinstance(cd.visibility, list))
        self.assertIsNotNone(did, "no faction-gated cache in jundland_drift")
        cd = self.pool[did]
        faction = cd.visibility[0]
        # Hidden with no rep, visible at rep >= 0.
        self.assertFalse(is_cache_visible(self._row(did), {}))
        self.assertTrue(is_cache_visible(self._row(did), {faction: 0}))
        self.assertFalse(is_cache_visible(self._row(did), {faction: -1}))


class TestEndToEnd(unittest.TestCase):
    """DB-backed proof the loop runs against a real (flyable) Hutt zone."""

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

            created = await spawn_zone_caches(db, "jundland_drift")
            self.assertGreater(created, 0, "no caches spawned for jundland_drift")

            rows = await get_zone_caches(db, "jundland_drift")
            self.assertTrue(rows)

            pool = get_cache_pool("jundland_drift")
            target = next(
                (r for r in rows
                 if r["state"] == "available"
                 and pool.get(r["cache_def_id"])
                 and pool[r["cache_def_id"]].kind == "mining"
                 and pool[r["cache_def_id"]].visibility == "universal"),
                None,
            )
            self.assertIsNotNone(target, "no universal mining node to harvest")

            char = {
                "id": 1,
                "inventory": {},
                "attributes": {"mechanical": {"space transports": "5D"}},
                "skills": {},
            }
            result = await harvest_mining(db, char, target["cache_instance_id"])
            self.assertFalse(result.not_found)
            self.assertFalse(result.wrong_kind)

        _run(_go())


if __name__ == "__main__":
    unittest.main()
