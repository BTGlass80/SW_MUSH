# -*- coding: utf-8 -*-
"""tests/test_director_economy_eyes.py — DIRECTOR.economy_digest.

Economy eyes (director_scope_and_adaptive_spend_v1.md §3): a PURE-READ
faucet/sink rollup of credit_log (every credit movement funnels through
adjust_credits(..., source)) injected into the Director digest, so the
LLM Director can perceive a smuggling boom / deflation / a player getting
rich. Read-only — no new write seam.
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
    """Stub DB: credit_log queries return supplied rows; all else []."""
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self, sql, params=()):
        if "credit_log" in sql:
            return list(self._rows)
        return []

    async def execute(self, sql, params=()):
        pass

    async def commit(self):
        pass


_ROWS = [
    {"source": "smuggling", "faucet": 800, "sink": 0, "n": 4},
    {"source": "vendor_buy", "faucet": 0, "sink": 300, "n": 6},
    {"source": "bounty_payout", "faucet": 500, "sink": 0, "n": 2},
    {"source": "craft_material", "faucet": 0, "sink": 120, "n": 3},
]


class TestEconomyRollup(unittest.TestCase):
    def test_totals_and_net(self):
        from engine.director import DirectorAI
        eco = _run(DirectorAI()._compile_economy_digest(_EcoDB(_ROWS)))
        self.assertEqual(eco["total_faucet"], 1300)   # 800 + 500
        self.assertEqual(eco["total_sink"], 420)      # 300 + 120
        self.assertEqual(eco["net_flow"], 880)
        self.assertEqual(eco["transactions"], 15)
        self.assertEqual(eco["window_minutes"], 30)

    def test_top_lists_sorted_desc(self):
        from engine.director import DirectorAI
        eco = _run(DirectorAI()._compile_economy_digest(_EcoDB(_ROWS)))
        self.assertEqual(eco["top_faucets"][0], ["smuggling", 800])
        self.assertEqual(eco["top_faucets"][1], ["bounty_payout", 500])
        self.assertEqual(eco["top_sinks"][0], ["vendor_buy", 300])
        # A pure-faucet source never appears as a sink and vice-versa.
        self.assertNotIn("smuggling", dict(eco["top_sinks"]))

    def test_top_lists_capped_at_five(self):
        from engine.director import DirectorAI
        rows = [{"source": f"src{i}", "faucet": i * 10, "sink": 0, "n": 1}
                for i in range(1, 9)]
        eco = _run(DirectorAI()._compile_economy_digest(_EcoDB(rows)))
        self.assertEqual(len(eco["top_faucets"]), 5)
        self.assertEqual(eco["top_faucets"][0], ["src8", 80])  # highest first

    def test_empty_window_returns_empty(self):
        from engine.director import DirectorAI
        self.assertEqual(_run(DirectorAI()._compile_economy_digest(_EcoDB([]))), {})

    def test_zero_movement_rows_return_empty(self):
        from engine.director import DirectorAI
        rows = [{"source": "x", "faucet": 0, "sink": 0, "n": 0}]
        self.assertEqual(_run(DirectorAI()._compile_economy_digest(_EcoDB(rows))), {})

    def test_read_failure_fails_open(self):
        from engine.director import DirectorAI

        class _BadDB:
            async def fetchall(self, sql, params=()):
                raise RuntimeError("no such table: credit_log")
        self.assertEqual(_run(DirectorAI()._compile_economy_digest(_BadDB())), {})


class TestDigestIntegration(unittest.TestCase):
    class _SessionMgr:
        all = []

    def test_compile_digest_includes_economy(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        digest = _run(d.compile_digest(self._SessionMgr(), db=_EcoDB(_ROWS)))
        self.assertIn("economy", digest)
        self.assertEqual(digest["economy"]["net_flow"], 880)

    def test_compile_digest_no_db_no_economy_no_crash(self):
        from engine.director import DirectorAI
        d = DirectorAI()
        digest = _run(d.compile_digest(self._SessionMgr(), db=None))
        self.assertNotIn("economy", digest)  # absent, and no crash


if __name__ == "__main__":
    unittest.main()
