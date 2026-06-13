# -*- coding: utf-8 -*-
"""tests/test_director_bugfixes.py — the 2 verified director.py bugs +
the claude_provider SSL/usage plumbing (2026-06-13, Director multizone prep).

BUG 1 (dead lever / uncaught crash): _apply_influence_delta was CALLED in
_run_api_turn but never DEFINED -> uncaught AttributeError on any influence
adjustment. Now defined, mutating the in-memory ZoneState + persisting.

BUG 2 (cost telemetry logged $0): _run_api_turn hardcoded tok_in/tok_out=0;
the provider now exposes last_usage() so real token counts reach director_log.

SSL: ClaudeProvider built a bare ClientSession (certifi default) which fails on
Brian's box (Norton AV TLS interception); _build_ssl_context now reads the OS
store via truststore.
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


class _StubDB:
    """Captures zone_influence upserts the director writes."""
    def __init__(self):
        self.writes = []

    async def execute(self, sql, params=()):
        if "zone_influence" in sql:
            self.writes.append(params)

    async def commit(self):
        pass

    async def fetchall(self, sql, params=()):
        return []


class TestApplyInfluenceDelta(unittest.TestCase):
    """BUG 1: the lever is defined and actually moves influence."""

    def _director_with_zone(self):
        from engine.director import DirectorAI, ZoneState, VALID_ZONES, VALID_FACTIONS
        d = DirectorAI()
        zone = next(iter(VALID_ZONES))
        faction = next(iter(VALID_FACTIONS))
        d._zones[zone] = ZoneState(zone_key=zone)
        return d, zone, faction

    def test_method_exists_and_is_async(self):
        import inspect
        from engine.director import DirectorAI
        m = getattr(DirectorAI, "_apply_influence_delta", None)
        self.assertIsNotNone(m, "the lever must be DEFINED (was a dead call)")
        self.assertTrue(inspect.iscoroutinefunction(m))

    def test_positive_delta_raises_influence_and_persists(self):
        d, zone, faction = self._director_with_zone()
        before = d._zones[zone].get_faction(faction)
        db = _StubDB()
        _run(d._apply_influence_delta(db, zone, faction, 5))
        after = d._zones[zone].get_faction(faction)
        self.assertEqual(after, before + 5)
        self.assertTrue(db.writes, "must persist to zone_influence")

    def test_negative_delta_lowers_influence(self):
        d, zone, faction = self._director_with_zone()
        d._zones[zone].set_faction(faction, 40)
        db = _StubDB()
        _run(d._apply_influence_delta(db, zone, faction, -10))
        self.assertEqual(d._zones[zone].get_faction(faction), 30)

    def test_delta_clamps_to_bounds(self):
        from engine.director import MAX_INFLUENCE
        d, zone, faction = self._director_with_zone()
        d._zones[zone].set_faction(faction, MAX_INFLUENCE)
        db = _StubDB()
        _run(d._apply_influence_delta(db, zone, faction, 50))  # would overflow
        self.assertEqual(d._zones[zone].get_faction(faction), MAX_INFLUENCE)

    def test_zero_delta_noop(self):
        d, zone, faction = self._director_with_zone()
        before = d._zones[zone].get_faction(faction)
        db = _StubDB()
        _run(d._apply_influence_delta(db, zone, faction, 0))
        self.assertEqual(d._zones[zone].get_faction(faction), before)
        self.assertFalse(db.writes)  # no-op doesn't write

    def test_unknown_zone_safe(self):
        d, _zone, faction = self._director_with_zone()
        db = _StubDB()
        # Must not raise on an unknown zone (the LLM could return junk).
        _run(d._apply_influence_delta(db, "no_such_zone", faction, 5))
        self.assertFalse(db.writes)


class TestProviderUsageAndSSL(unittest.TestCase):
    """BUG 2 plumbing + the SSL context (no live network needed)."""

    def test_last_usage_default_zero(self):
        from ai.claude_provider import ClaudeProvider
        p = ClaudeProvider(api_key="test-key")
        self.assertEqual(p.last_usage(), {"input_tokens": 0, "output_tokens": 0})

    def test_last_usage_accessor_returns_copy(self):
        from ai.claude_provider import ClaudeProvider
        p = ClaudeProvider(api_key="test-key")
        u = p.last_usage()
        u["input_tokens"] = 999          # mutate the copy
        self.assertEqual(p.last_usage()["input_tokens"], 0)  # internal unchanged

    def test_ssl_context_builds(self):
        # truststore is installed in this env; the context must build (and be a
        # real SSLContext), so the Director's aiohttp call trusts the OS store.
        from ai.claude_provider import _build_ssl_context
        import ssl
        ctx = _build_ssl_context()
        self.assertIsNotNone(ctx)
        self.assertIsInstance(ctx, ssl.SSLContext)


if __name__ == "__main__":
    unittest.main()
