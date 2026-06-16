# -*- coding: utf-8 -*-
"""
tests/test_t321_soft_endpoint_throttle.py — T3.21 security tail
(2026-06-16).

The unauthenticated chargen *read* endpoints that perform real work on every
call were unthrottled, while the expensive create/submit writes were already
behind the strict per-IP limiter:

  GET  /api/chargen/check-name/{name}  — one DB round-trip + name-enumeration
                                          oracle
  POST /api/chargen/validate           — registry validation (CPU-bound)

Left unbounded, a single client can flood them to enumerate character names or
amplify load on the shared aiosqlite connection (which serializes every query).
This drop adds a *separate, more lenient* per-IP sliding-window limiter
(`_check_soft_rate_limit`, SOFT_RATE_LIMIT_MAX/SOFT_RATE_LIMIT_WINDOW) keyed on
the spoof-resistant `_get_client_ip`, applied before any DB/CPU work.

Pins:
  1. check-name returns 200 under the limit (normal availability shape).
  2. check-name 429s once SOFT_RATE_LIMIT_MAX is exceeded, and the DB is NOT
     queried on the throttled call.
  3. validate 429s once the soft limit is exceeded, before reading the body.
  4. The 429 check-name body omits a matching `name` (SPA-safe degrade).
  5. The soft bucket is INDEPENDENT of the strict create bucket — heavy
     name-checking does not consume a legitimate user's create budget.
  6. Per-IP isolation: one IP's flood does not throttle another IP.
  7. The generic helper prunes outside the window (admits again after expiry).
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Mock request with controllable client IP ────────────────────────────
class _MockRequest:
    def __init__(self, *, json_body=None, match_name=None, ip="127.0.0.1"):
        self._json_body = json_body if json_body is not None else {}
        self.match_info = {"name": match_name} if match_name is not None else {}
        self.headers = {}
        self.query = {}
        self.transport = MagicMock()
        self.transport.get_extra_info = MagicMock(return_value=(ip, 12345))

    async def json(self):
        if isinstance(self._json_body, Exception):
            raise self._json_body
        return self._json_body


# ── Mock DB that records check-name queries ─────────────────────────────
class _CountingDB:
    def __init__(self, existing_names=None):
        self.existing = set(existing_names or [])
        self.name_queries = []  # records every get_character_by_name call

    async def get_character_by_name(self, name):
        self.name_queries.append(name)
        return {"id": 1, "name": name} if name in self.existing else None


def _resp_json(resp):
    return json.loads(resp.body.decode("utf-8"))


def _build_api(db):
    # Reuse the lightweight registry stubs from the drop2b harness.
    from tests.test_drop2b_chargen_chains_endpoint_and_consumer import (
        _RealSpeciesRegMini,
        _RealSkillRegMini,
    )
    from server.api import ChargenAPI
    return ChargenAPI(
        species_reg=_RealSpeciesRegMini(),
        skill_reg=_RealSkillRegMini(),
        db=db,
    )


def _reset_buckets():
    from server import api as api_mod
    api_mod._rate_limits.clear()
    api_mod._soft_rate_limits.clear()


class SoftThrottleBase(unittest.TestCase):
    def setUp(self):
        _reset_buckets()

    def tearDown(self):
        _reset_buckets()


class TestCheckNameUnderLimit(SoftThrottleBase):
    def test_returns_availability_under_limit(self):
        db = _CountingDB(existing_names={"taken"})
        api = _build_api(db)
        # Free name
        r = _run(api.handle_check_name(
            _MockRequest(match_name="Freshname")))
        self.assertEqual(r.status, 200)
        body = _resp_json(r)
        self.assertTrue(body["available"])
        self.assertEqual(body["name"], "Freshname")
        # Taken name
        r2 = _run(api.handle_check_name(_MockRequest(match_name="taken")))
        self.assertEqual(r2.status, 200)
        self.assertFalse(_resp_json(r2)["available"])


class TestCheckNameThrottle(SoftThrottleBase):
    def test_429_after_soft_limit(self):
        from server.api import SOFT_RATE_LIMIT_MAX
        db = _CountingDB()
        api = _build_api(db)
        # Exhaust the budget — all allowed.
        for _ in range(SOFT_RATE_LIMIT_MAX):
            r = _run(api.handle_check_name(
                _MockRequest(match_name="Probe", ip="9.9.9.9")))
            self.assertEqual(r.status, 200)
        # Next one is throttled.
        r = _run(api.handle_check_name(
            _MockRequest(match_name="Probe", ip="9.9.9.9")))
        self.assertEqual(r.status, 429)

    def test_throttled_call_does_not_query_db(self):
        from server.api import SOFT_RATE_LIMIT_MAX
        db = _CountingDB()
        api = _build_api(db)
        for _ in range(SOFT_RATE_LIMIT_MAX):
            _run(api.handle_check_name(
                _MockRequest(match_name="Probe", ip="8.8.8.8")))
        queries_before = len(db.name_queries)
        r = _run(api.handle_check_name(
            _MockRequest(match_name="Probe", ip="8.8.8.8")))
        self.assertEqual(r.status, 429)
        # The DB must NOT be touched on the throttled call.
        self.assertEqual(len(db.name_queries), queries_before)

    def test_429_body_has_no_matching_name(self):
        from server.api import SOFT_RATE_LIMIT_MAX
        db = _CountingDB()
        api = _build_api(db)
        for _ in range(SOFT_RATE_LIMIT_MAX):
            _run(api.handle_check_name(
                _MockRequest(match_name="Zed", ip="7.7.7.7")))
        r = _run(api.handle_check_name(
            _MockRequest(match_name="Zed", ip="7.7.7.7")))
        body = _resp_json(r)
        # SPA only updates its hint when d.name === typed name → omit it.
        self.assertIsNone(body.get("name"))
        self.assertIn("error", body)


class TestValidateThrottle(SoftThrottleBase):
    def test_validate_429_after_soft_limit(self):
        from server.api import SOFT_RATE_LIMIT_MAX
        db = _CountingDB()
        api = _build_api(db)
        for _ in range(SOFT_RATE_LIMIT_MAX):
            r = _run(api.handle_validate(
                _MockRequest(json_body={}, ip="5.5.5.5")))
            self.assertIn(r.status, (200, 400))
        r = _run(api.handle_validate(
            _MockRequest(json_body={}, ip="5.5.5.5")))
        self.assertEqual(r.status, 429)

    def test_validate_throttle_runs_before_body_read(self):
        # A throttled validate must 429 even if the body would have raised
        # on read (proves the limiter runs first).
        from server.api import SOFT_RATE_LIMIT_MAX
        db = _CountingDB()
        api = _build_api(db)
        for _ in range(SOFT_RATE_LIMIT_MAX):
            _run(api.handle_validate(
                _MockRequest(json_body={}, ip="4.4.4.4")))
        bad = _MockRequest(json_body=ValueError("boom"), ip="4.4.4.4")
        r = _run(api.handle_validate(bad))
        self.assertEqual(r.status, 429)


class TestBucketIsolation(SoftThrottleBase):
    def test_soft_does_not_consume_strict_budget(self):
        from server.api import (
            SOFT_RATE_LIMIT_MAX,
            _check_rate_limit,
            RATE_LIMIT_MAX,
        )
        db = _CountingDB()
        api = _build_api(db)
        # Hammer the soft endpoint well past the strict limit.
        for _ in range(SOFT_RATE_LIMIT_MAX):
            _run(api.handle_check_name(
                _MockRequest(match_name="Probe", ip="3.3.3.3")))
        # The strict create budget for the SAME ip must be untouched.
        for _ in range(RATE_LIMIT_MAX):
            self.assertTrue(_check_rate_limit("3.3.3.3"))
        self.assertFalse(_check_rate_limit("3.3.3.3"))

    def test_per_ip_isolation(self):
        from server.api import SOFT_RATE_LIMIT_MAX
        db = _CountingDB()
        api = _build_api(db)
        for _ in range(SOFT_RATE_LIMIT_MAX + 5):
            _run(api.handle_check_name(
                _MockRequest(match_name="Probe", ip="1.1.1.1")))
        # A different IP is unaffected.
        r = _run(api.handle_check_name(
            _MockRequest(match_name="Probe", ip="2.2.2.2")))
        self.assertEqual(r.status, 200)


class TestWindowPrune(SoftThrottleBase):
    def test_prunes_outside_window(self):
        # The generic helper admits again once timestamps age past the window.
        from server import api as api_mod
        bucket = api_mod.defaultdict(list)
        # Pre-seed with old timestamps (well outside a 1s window).
        import time as _t
        old = _t.time() - 100.0
        bucket["x"] = [old] * 10
        # window=1s, max=2 → the 10 stale entries prune away, request admitted.
        self.assertTrue(
            api_mod._sliding_window_allow(bucket, "x", 2, 1.0))
        self.assertTrue(
            api_mod._sliding_window_allow(bucket, "x", 2, 1.0))
        self.assertFalse(
            api_mod._sliding_window_allow(bucket, "x", 2, 1.0))


if __name__ == "__main__":
    unittest.main()
