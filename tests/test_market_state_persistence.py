# -*- coding: utf-8 -*-
"""
tests/test_market_state_persistence.py — persist the trade pools (audit v2 §1.5).

Two things ship together here because the second makes the first meaningful:

  1. **Supply/demand pool persistence.** Both pools were process-memory only, so
     a server restart re-seeded every supply pool to full (a windfall for the
     first trader after a bounce) and cleared all demand depression (a windfall
     for the first seller). They now snapshot to the ``market_state`` DB table
     and rehydrate on startup.

  2. **The demand-depression wiring fix (a latent bug found in pre-flight).**
     ``_handle_sell_cargo`` priced sales with the *base* price (no
     ``include_demand_depression``) and never called ``DEMAND_POOL.record_sale``
     — so the depression mechanic (the audit-praised round-trip profit ceiling)
     was entirely inert in production, even though the price-list display
     advertised it. Persisting an always-empty demand pool would be pointless;
     this wires it.

Covers the pure pool serialization, the DB get/set methods + orchestration, the
restart-windfall fix itself, and structural pins on the sell path + migration.
"""

import os
import sys
import json
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import trading                                            # noqa: E402
from engine.trading import (                                         # noqa: E402
    SupplyPool, DemandPool, get_planet_price, TRADE_GOODS,
    load_market_pools, flush_market_pools,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pure pool serialization
# ─────────────────────────────────────────────────────────────────────────────
class TestSupplyPoolSerialize(unittest.TestCase):
    def test_consume_then_roundtrip_preserves_drawdown(self):
        p = SupplyPool()
        full = p.available("tatooine", "raw_ore")
        self.assertTrue(p.consume("tatooine", "raw_ore", 5))
        drawn = p.available("tatooine", "raw_ore")
        self.assertEqual(drawn, full - 5)

        records = p.to_records()
        self.assertEqual(json.loads(json.dumps(records)), records)  # JSON-safe

        q = SupplyPool()
        q.load_records(records)
        self.assertEqual(q.available("tatooine", "raw_ore"), drawn)

    def test_dirty_flag_lifecycle(self):
        p = SupplyPool()
        self.assertFalse(p._dirty)
        p.available("tatooine", "raw_ore")   # first-touch (refresh) does not dirty
        self.assertFalse(p._dirty)
        p.consume("tatooine", "raw_ore", 1)   # consumption dirties
        self.assertTrue(p._dirty)
        p.load_records(p.to_records())        # load clears
        self.assertFalse(p._dirty)

    def test_load_records_tolerates_garbage(self):
        import time as _t
        now = _t.time()
        p = SupplyPool()
        p.load_records([["tatooine", "raw_ore", 7, now],
                        ["bad", "row"],             # too short
                        None,                       # not a row
                        ["x", "y", "notint", 1.0]]) # bad units
        self.assertEqual(p.available("tatooine", "raw_ore"), 7)


class TestDemandPoolSerialize(unittest.TestCase):
    def test_record_sale_roundtrip_preserves_depression(self):
        d = DemandPool()
        d.record_sale("coruscant", "luxury_goods", 40)
        dep = d.get_depression("coruscant", "luxury_goods")
        self.assertGreater(dep, 0.0)

        records = d.to_records()
        self.assertEqual(json.loads(json.dumps(records)), records)

        e = DemandPool()
        e.load_records(records)
        self.assertAlmostEqual(e.get_depression("coruscant", "luxury_goods"), dep)

    def test_dirty_on_record_sale(self):
        d = DemandPool()
        self.assertFalse(d._dirty)
        d.record_sale("coruscant", "luxury_goods", 1)
        self.assertTrue(d._dirty)
        d.load_records(d.to_records())
        self.assertFalse(d._dirty)


# ─────────────────────────────────────────────────────────────────────────────
# The restart-windfall fix (the §1.5 finding itself)
# ─────────────────────────────────────────────────────────────────────────────
class TestRestartWindfallClosed(unittest.TestCase):
    def test_drawn_down_pool_does_not_come_back_full(self):
        """The whole point: a market drawn down before a restart must come back
        drawn down, NOT freshly full."""
        before = SupplyPool()
        full = before.available("kuat", "manufactured_parts")
        before.consume("kuat", "manufactured_parts", full)  # buy it all
        self.assertEqual(before.available("kuat", "manufactured_parts"), 0)

        # Simulate restart: serialize, then hydrate a brand-new pool.
        after = SupplyPool()
        after.load_records(before.to_records())
        self.assertEqual(after.available("kuat", "manufactured_parts"), 0,
                         "a restart must not re-seed the emptied market to full")

        # Control: a pool with NO hydration first-touches back to full (the old
        # broken behaviour we are fixing).
        fresh = SupplyPool()
        self.assertEqual(fresh.available("kuat", "manufactured_parts"), full)


# ─────────────────────────────────────────────────────────────────────────────
# DB layer + orchestration (real in-memory Database)
# ─────────────────────────────────────────────────────────────────────────────
async def _db_with_market_table():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    # Create just the v38 table (mirrors the migration DDL) so the test is fast
    # and deterministic without a full initialize()/world-build.
    await db._db.execute(
        "CREATE TABLE market_state (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
        "updated_at REAL DEFAULT 0)"
    )
    await db._db.commit()
    return db


class TestMarketStateDB(unittest.TestCase):
    def test_get_set_roundtrip(self):
        async def go():
            db = await _db_with_market_table()
            self.assertIsNone(await db.get_market_state("nope"))
            await db.set_market_state("supply_pools", '[["tatooine","raw_ore",3,9.0]]')
            got = await db.get_market_state("supply_pools")
            self.assertEqual(json.loads(got), [["tatooine", "raw_ore", 3, 9.0]])
            # upsert overwrites
            await db.set_market_state("supply_pools", "[]")
            self.assertEqual(await db.get_market_state("supply_pools"), "[]")
        _run(go())

    def test_flush_then_load_roundtrips_through_db(self):
        async def go():
            db = await _db_with_market_table()
            # Drive the module singletons, flush, then hydrate from the DB.
            trading.SUPPLY_POOL = SupplyPool()
            trading.DEMAND_POOL = DemandPool()
            trading.SUPPLY_POOL.consume("geonosis", "raw_ore", 2)
            trading.DEMAND_POOL.record_sale("coruscant", "luxury_goods", 30)
            drawn = trading.SUPPLY_POOL.available("geonosis", "raw_ore")
            dep = trading.DEMAND_POOL.get_depression("coruscant", "luxury_goods")

            await flush_market_pools(db)
            # both pools clean after a successful flush
            self.assertFalse(trading.SUPPLY_POOL._dirty)
            self.assertFalse(trading.DEMAND_POOL._dirty)

            # wipe in-memory state, then rehydrate from DB
            trading.SUPPLY_POOL = SupplyPool()
            trading.DEMAND_POOL = DemandPool()
            await load_market_pools(db)
            self.assertEqual(trading.SUPPLY_POOL.available("geonosis", "raw_ore"), drawn)
            self.assertAlmostEqual(
                trading.DEMAND_POOL.get_depression("coruscant", "luxury_goods"), dep)
        _run(go())

    def test_flush_is_noop_when_clean(self):
        async def go():
            db = await _db_with_market_table()
            trading.SUPPLY_POOL = SupplyPool()
            trading.DEMAND_POOL = DemandPool()
            await flush_market_pools(db)  # nothing dirty
            self.assertIsNone(await db.get_market_state("supply_pools"))
        _run(go())

    def test_load_is_failopen_without_table(self):
        async def go():
            from db.database import Database
            db = Database(":memory:")
            await db.connect()  # no market_state table at all
            trading.SUPPLY_POOL = SupplyPool()
            # must not raise
            await load_market_pools(db)
        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# The demand-depression wiring fix — behaviour + structural pins
# ─────────────────────────────────────────────────────────────────────────────
class TestDemandDepressionWired(unittest.TestCase):
    def test_depression_actually_lowers_a_demand_price(self):
        """A demand-planet sell price must drop after recorded sales."""
        # find a good with a known demand planet
        good = None
        planet = None
        for g in TRADE_GOODS.values():
            if g.demand:
                good, planet = g, list(g.demand)[0]
                break
        self.assertIsNotNone(good, "need a good with a demand planet")

        d = DemandPool()
        # point the module singleton at our fresh pool for a clean read
        trading.DEMAND_POOL = d
        base = get_planet_price(good, planet, include_demand_depression=True)
        d.record_sale(planet, good.key, 100)  # saturate
        depressed = get_planet_price(good, planet, include_demand_depression=True)
        self.assertLess(depressed, base,
                        "recorded sales must depress the demand-planet sell price")


class TestSellPathStructuralPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(PROJECT_ROOT, "parser", "builtin_commands.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        i = src.index("async def _handle_sell_cargo")
        # end at the next top-level def/async def/class, or EOF
        ends = [src.find(tok, i + 10) for tok in ("\nasync def ", "\ndef ", "\nclass ")]
        ends = [e for e in ends if e != -1]
        cls.sell_src = src[i:min(ends)] if ends else src[i:]

    def test_sell_applies_demand_depression(self):
        self.assertIn("include_demand_depression=True", self.sell_src,
                      "sell-cargo must price with demand depression")

    def test_sell_records_the_sale(self):
        self.assertIn("DEMAND_POOL.record_sale", self.sell_src,
                      "sell-cargo must record the sale so depression accumulates")

    def test_sell_persists_pools(self):
        self.assertIn("flush_market_pools", self.sell_src)


class TestMigrationWired(unittest.TestCase):
    def test_schema_version_and_v38_migration(self):
        with open(os.path.join(PROJECT_ROOT, "db", "database.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("SCHEMA_VERSION = 38", src)
        # v38 migration creates the market_state table
        i = src.index("38: [")
        nxt = src.index("\n}", i)
        self.assertIn("CREATE TABLE IF NOT EXISTS market_state", src[i:nxt])


if __name__ == "__main__":
    unittest.main(verbosity=2)
