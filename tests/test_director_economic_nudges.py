# -*- coding: utf-8 -*-
"""tests/test_director_economic_nudges.py — Director soft economic NUDGES.

director_scope_and_adaptive_spend_v1.md §4 step 4, Brian decision A: after the
economy-eyes PERCEPTION layer (_compile_economy_digest), the Director ACTS on
macro economic signals by SEEDING an opportunity players can take or ignore — a
merchant caravan (merchant_arrival / rare_vendor) on a wealth-surge or
trade-boom signal. Decision A = SEEDS, never LEVERS: it never fires the
price/yield events (trade_boom/spice_demand/bounty_surge/intelligence_thaw),
adds no new credit flow, and only reuses an EXISTING event through the
WorldEventManager seam (which has its own cooldown/max-concurrent guards).
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class _EcoDB:
    """Stub DB: credit_log queries return supplied rows; execute is a no-op."""
    def __init__(self, rows):
        self._rows = rows
        self.executed = 0

    async def fetchall(self, sql, params=()):
        if "credit_log" in sql:
            return list(self._rows)
        return []

    async def execute(self, sql, params=()):
        self.executed += 1

    async def commit(self):
        pass


class _BadDB:
    """Any read raises — proves a short-circuit never touched the DB."""
    async def fetchall(self, sql, params=()):
        raise AssertionError("DB must not be read on this path")

    async def execute(self, sql, params=()):
        raise AssertionError("DB must not be written on this path")


class _SessionMgr:
    all = []

    async def broadcast(self, msg):
        pass


# Rows that make _compile_economy_digest produce each condition. Keys match the
# real query columns (source/faucet/sink/n).
_WEALTH_SURGE_ROWS = [{"source": "smuggling", "faucet": 9000, "sink": 0, "n": 10}]
_TRADE_BOOM_ROWS = [
    {"source": "trade_sale", "faucet": 3000, "sink": 0, "n": 8},
    {"source": "vendor_buy", "faucet": 0, "sink": 2000, "n": 7},
]
_BOTH_ROWS = [  # qualifies for wealth_surge AND trade_boom — surge must win
    {"source": "trade_sale", "faucet": 9000, "sink": 0, "n": 8},
    {"source": "vendor_buy", "faucet": 0, "sink": 2000, "n": 7},
]
_NONCOMMERCE_ROWS = [  # busy but the dominant faucet is not commerce
    {"source": "admin_grant", "faucet": 3000, "sink": 0, "n": 8},
    {"source": "death_fee", "faucet": 0, "sink": 2000, "n": 7},
]
_TRIVIAL_ROWS = [{"source": "trade_sale", "faucet": 1000, "sink": 0, "n": 30}]


def _eco(rows):
    from engine.director import DirectorAI
    return _run(DirectorAI()._compile_economy_digest(_EcoDB(rows)))


class TestClassifier(unittest.TestCase):
    """_classify_economic_seed is pure — exercise the threshold logic."""

    def test_empty_eco_is_none(self):
        from engine.director import DirectorAI
        self.assertIsNone(DirectorAI._classify_economic_seed({}))

    def test_sub_floor_faucet_is_none(self):
        # 1000 credits < ECON_MIN_FLOW even with a busy, commerce-flavored window.
        from engine.director import DirectorAI, ECON_MIN_FLOW
        eco = _eco(_TRIVIAL_ROWS)
        self.assertLess(eco["total_faucet"], ECON_MIN_FLOW)
        self.assertIsNone(DirectorAI._classify_economic_seed(eco))

    def test_wealth_surge(self):
        from engine.director import DirectorAI, ECON_SEED_EVENT
        seed = DirectorAI._classify_economic_seed(_eco(_WEALTH_SURGE_ROWS))
        self.assertIsNotNone(seed)
        self.assertEqual(seed["condition"], "wealth_surge")
        self.assertEqual(seed["event_type"], ECON_SEED_EVENT)

    def test_trade_boom(self):
        from engine.director import DirectorAI, ECON_SEED_EVENT
        seed = DirectorAI._classify_economic_seed(_eco(_TRADE_BOOM_ROWS))
        self.assertIsNotNone(seed)
        self.assertEqual(seed["condition"], "trade_boom")
        self.assertEqual(seed["event_type"], ECON_SEED_EVENT)

    def test_busy_but_non_commerce_is_none(self):
        from engine.director import DirectorAI
        eco = _eco(_NONCOMMERCE_ROWS)
        self.assertGreaterEqual(eco["transactions"], 15)   # busy
        self.assertIsNone(DirectorAI._classify_economic_seed(eco))  # but not commerce

    def test_wealth_surge_beats_trade_boom(self):
        from engine.director import DirectorAI
        seed = DirectorAI._classify_economic_seed(_eco(_BOTH_ROWS))
        self.assertEqual(seed["condition"], "wealth_surge")

    def test_classifier_only_ever_seeds_the_safe_event(self):
        # Across every condition, the seeded event is the decision-A-safe one,
        # never a price/yield lever.
        from engine.director import (DirectorAI, ECON_SEED_EVENT,
                                     ECON_FORBIDDEN_LEVER_EVENTS)
        for rows in (_WEALTH_SURGE_ROWS, _TRADE_BOOM_ROWS, _BOTH_ROWS):
            seed = DirectorAI._classify_economic_seed(_eco(rows))
            self.assertEqual(seed["event_type"], ECON_SEED_EVENT)
            self.assertNotIn(seed["event_type"], ECON_FORBIDDEN_LEVER_EVENTS)


class TestDecisionAInvariant(unittest.TestCase):
    """Decision A encoded as a guard: seeds, never the price/yield levers."""

    def test_seed_event_is_the_caravan(self):
        from engine.director import ECON_SEED_EVENT
        self.assertEqual(ECON_SEED_EVENT, "merchant_arrival")

    def test_forbidden_set_names_the_levers(self):
        from engine.director import ECON_FORBIDDEN_LEVER_EVENTS, ECON_SEED_EVENT
        self.assertEqual(
            set(ECON_FORBIDDEN_LEVER_EVENTS),
            {"trade_boom", "spice_demand", "bounty_surge", "intelligence_thaw"},
        )
        self.assertNotIn(ECON_SEED_EVENT, ECON_FORBIDDEN_LEVER_EVENTS)


class TestSeeder(unittest.TestCase):
    """_seed_economic_opportunities — gating, cooldown, firing, fail-open."""

    def _reset_events(self):
        import engine.world_events as we
        we._manager = None

    def test_empty_server_does_not_seed_or_read_db(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        # online below the floor: returns None WITHOUT touching the DB.
        self.assertIsNone(
            _run(d._seed_economic_opportunities(_BadDB(), _SessionMgr(),
                                                online=1, now=10000.0)))

    def test_cooldown_short_circuits_before_db(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        d._last_economic_seed_time = 10000.0
        # 10500 - 10000 = 500s < cooldown: None, and the DB is never read.
        self.assertIsNone(
            _run(d._seed_economic_opportunities(_BadDB(), _SessionMgr(),
                                                online=2, now=10500.0)))

    def test_fires_on_qualifying_window(self):
        from engine.director import DirectorAI
        from engine.world_events import get_world_event_manager
        self._reset_events()
        d = DirectorAI()
        db = _EcoDB(_WEALTH_SURGE_ROWS)
        result = _run(d._seed_economic_opportunities(
            db, _SessionMgr(), online=2, now=10000.0))
        self.assertEqual(result, "wealth_surge")
        # cooldown stamped + the merchant flag is now live (rare_vendor active)
        self.assertEqual(d._last_economic_seed_time, 10000.0)
        self.assertTrue(get_world_event_manager().get_effect("rare_vendor", False))
        self.assertGreaterEqual(db.executed, 1)  # director_log written

    def test_no_seed_when_economy_quiet(self):
        from engine.director import DirectorAI
        self._reset_events()
        d = DirectorAI()
        # Trivial window -> classifier returns None -> no seed, no cooldown burn.
        self.assertIsNone(_run(d._seed_economic_opportunities(
            _EcoDB(_TRIVIAL_ROWS), _SessionMgr(), online=2, now=10000.0)))
        self.assertEqual(d._last_economic_seed_time, 0.0)

    def test_declined_event_does_not_burn_cooldown(self):
        from engine.director import DirectorAI
        from engine.world_events import get_world_event_manager
        self._reset_events()
        wem = get_world_event_manager()
        wem.activate_event = lambda *a, **k: None  # WEM guard declines
        d = DirectorAI()
        result = _run(d._seed_economic_opportunities(
            _EcoDB(_WEALTH_SURGE_ROWS), _SessionMgr(), online=2, now=10000.0))
        self.assertIsNone(result)
        self.assertEqual(d._last_economic_seed_time, 0.0)  # retry next window

    def test_read_failure_fails_open(self):
        from engine.director import DirectorAI

        class _RaiseDigestDB:
            async def fetchall(self, sql, params=()):
                raise RuntimeError("no such table: credit_log")
        self._reset_events()
        d = DirectorAI()
        # _compile_economy_digest fails open to {} -> classifier None -> no crash.
        self.assertIsNone(_run(d._seed_economic_opportunities(
            _RaiseDigestDB(), _SessionMgr(), online=2, now=10000.0)))


if __name__ == "__main__":
    unittest.main()
