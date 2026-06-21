"""tests/test_communal_telemetry.py — T3.19 telemetry for the communal lane.

The dark-side-cult communal objective (``engine/communal_objective_runtime``)
is one of the named safe-lane Phase-2 telemetry domains. This drop adds three
emitters; this suite proves each fires at a REAL lifecycle transition (over the
actual migration DDL + the actual runtime SQL, via a raw-aiosqlite-shaped
mini-DB), carries the funnel fields the offline analysis needs, fires the
"complete" close EXACTLY once per uprising (the single-writer race guard), and
— the load-bearing contract — never disturbs the lifecycle when telemetry breaks.

  * ``objective`` kind=communal phase=start   → an uprising posted (maybe_post)
  * ``objective`` kind=communal phase=complete → it resolved, ``won`` carries the
    outcome and ``contributors`` the engagement (_finalize, once per uprising)
  * ``communal_strike``                        → one player strike (record_strike),
    the success/total/difficulty signal that tunes strike_difficulty post-launch

Run: python3 -m pytest tests/test_communal_telemetry.py
(asyncio.run, never get_event_loop — Python 3.14-safe.)
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import unittest

import engine.communal_objective as CO
import engine.communal_objective_runtime as COR
from db.database import MIGRATIONS


# ── a raw-aiosqlite-shaped mini-DB over the REAL communal_objective DDL ────────
class _CommDB:
    """In-memory sqlite shaped like the runtime's db handle.

    Uses the REAL migration DDL + the REAL runtime SQL; characters live in a
    dict (just enough for the reward path's get_character, which returns None
    for unseeded ids so the rep payout harmlessly no-ops in these tests).
    """

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for sql in MIGRATIONS[43]:
            self.conn.execute(sql)
        self.conn.commit()
        self.chars: dict[int, dict] = {}

    async def fetchone(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    async def fetchall(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    async def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    async def commit(self):
        self.conn.commit()

    async def get_character(self, cid):
        return self.chars.get(int(cid))

    async def save_character(self, cid, **fields):
        c = self.chars.setdefault(int(cid), {"id": int(cid)})
        c.update(fields)


def _run(coro):
    return asyncio.run(coro)


def _drain(ev=None):
    """Drain the singleton sink; optionally filter to one event type."""
    from engine import telemetry
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if ev is None or r.get("ev") == ev]


class _TelemetryTestBase(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        telemetry.reset()  # fresh buffer-only singleton per test

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()


# ══════════════════════════════════════════════════════════════════════════
# 1. start — maybe_post emits the objective open
# ══════════════════════════════════════════════════════════════════════════
class TestCommunalStartEmit(_TelemetryTestBase):
    def test_post_emits_objective_start(self):
        async def go():
            db = _CommDB()
            row = await COR.maybe_post(db, None, now_ms=1_000_000)
            self.assertIsNotNone(row)
            recs = _drain("objective")
            self.assertEqual(len(recs), 1)
            r = recs[0]
            self.assertEqual(r["kind"], "communal")
            self.assertEqual(r["phase"], "start")
            self.assertEqual(r["char_id"], 0)          # zone event, no actor
            self.assertEqual(r["reward"], 0)           # no credits minted
            self.assertEqual(r["oid"], CO.cult_for_index(0).key)
            self.assertEqual(r["rotation"], 0)
            self.assertEqual(r["zone"], CO.cult_for_index(0).world_key)
        _run(go())

    def test_blocked_post_emits_nothing(self):
        async def go():
            db = _CommDB()
            await COR.maybe_post(db, None, now_ms=1_000_000)
            _drain()  # clear the start from the first post
            # a second post while one is active is a no-op → no telemetry
            again = await COR.maybe_post(db, None, now_ms=1_000_001)
            self.assertIsNone(again)
            self.assertEqual(len(_drain("objective")), 0)
        _run(go())


# ══════════════════════════════════════════════════════════════════════════
# 2. complete — _finalize emits the objective close exactly once
# ══════════════════════════════════════════════════════════════════════════
class TestCommunalCompleteEmit(_TelemetryTestBase):
    def test_loss_at_deadline_emits_complete_not_won(self):
        async def go():
            db = _CommDB()
            await COR.maybe_post(db, None, now_ms=1_000_000)
            _drain()  # discard the start
            active = await COR.get_active(db)
            past = int(float(active["deadline_at"])) + 1
            state = await COR.advance_and_resolve(db, None, now_ms=past)
            self.assertEqual(state, CO.STATE_LOST)
            recs = _drain("objective")
            self.assertEqual(len(recs), 1)
            r = recs[0]
            self.assertEqual(r["kind"], "communal")
            self.assertEqual(r["phase"], "complete")
            self.assertEqual(r["char_id"], 0)
            self.assertFalse(r["won"])
            self.assertEqual(r["contributors"], 0)     # nobody struck
            self.assertEqual(r["oid"], CO.cult_for_index(0).key)
        _run(go())

    def test_win_emits_complete_won_with_contributor_count(self):
        async def go():
            db = _CommDB()
            await COR.maybe_post(db, None, now_ms=1_000_000)
            _drain()
            active = await COR.get_active(db)
            # synthesize two contributors with points, then finalize a WIN
            contribs = {"7": {"points": 5, "last_strike_at": 1.0},
                        "9": {"points": 2, "last_strike_at": 1.0}}
            active = dict(active)
            active["menace"] = 0.0
            await COR._finalize(db, None, active, contribs,
                                won=True, now_ms=1_000_500)
            recs = _drain("objective")
            self.assertEqual(len(recs), 1)
            r = recs[0]
            self.assertEqual(r["phase"], "complete")
            self.assertTrue(r["won"])
            self.assertEqual(r["contributors"], 2)
        _run(go())

    def test_complete_emits_exactly_once_under_double_resolve(self):
        """The state UPDATE ... WHERE state=active race guard means a second
        finalize (tick after an inline strike-win, etc.) emits nothing."""
        async def go():
            db = _CommDB()
            await COR.maybe_post(db, None, now_ms=1_000_000)
            _drain()
            active = await COR.get_active(db)
            active = dict(active)
            active["menace"] = float(CO.MENACE_MAX)
            await COR._finalize(db, None, active, {}, won=False, now_ms=1_000_500)
            # the row is no longer active; a second finalize finds rowcount 0
            await COR._finalize(db, None, active, {}, won=False, now_ms=1_000_600)
            recs = _drain("objective")
            self.assertEqual(len(recs), 1)  # NOT two
        _run(go())


# ══════════════════════════════════════════════════════════════════════════
# 3. strike — record_strike emits the per-strike difficulty signal
# ══════════════════════════════════════════════════════════════════════════
class TestCommunalStrikeEmit(_TelemetryTestBase):
    def test_strike_emits_communal_strike(self):
        async def go():
            db = _CommDB()
            await COR.maybe_post(db, None, now_ms=1_000_000)
            _drain()  # discard the start
            char = {"id": 7, "skills": json.dumps({"blaster": 18}),
                    "attributes": json.dumps({"dexterity": 12})}
            await COR.record_strike(db, None, char, now_ms=1_000_000)
            recs = _drain("communal_strike")
            self.assertEqual(len(recs), 1)
            r = recs[0]
            self.assertEqual(r["char_id"], 7)
            self.assertEqual(r["cult"], CO.cult_for_index(0).key)
            self.assertIn("success", r)
            self.assertIsInstance(r["success"], bool)
            self.assertIn("difficulty", r)
            self.assertIn("total", r)
            self.assertIn("menace_after", r)
            self.assertIn("pips", r)

    def test_cooldown_strike_emits_nothing(self):
        async def go():
            db = _CommDB()
            await COR.maybe_post(db, None, now_ms=1_000_000)
            char = {"id": 7, "skills": json.dumps({"blaster": 18}),
                    "attributes": json.dumps({"dexterity": 12})}
            await COR.record_strike(db, None, char, now_ms=1_000_000)
            _drain()  # clear the first strike's event
            # an immediate second strike is on cooldown → returns early, no emit
            res2 = await COR.record_strike(db, None, char, now_ms=1_000_001)
            self.assertFalse(res2.ok)
            self.assertEqual(res2.reason, "cooldown")
            self.assertEqual(len(_drain("communal_strike")), 0)
        _run(go())

    def test_strike_no_active_emits_nothing(self):
        async def go():
            db = _CommDB()
            char = {"id": 1, "skills": "{}", "attributes": "{}"}
            res = await COR.record_strike(db, None, char, now_ms=1)
            self.assertFalse(res.ok)
            self.assertEqual(len(_drain("communal_strike")), 0)
        _run(go())


# ══════════════════════════════════════════════════════════════════════════
# 4. fail-open — a broken telemetry sink NEVER disturbs the lifecycle
# ══════════════════════════════════════════════════════════════════════════
class TestCommunalTelemetryFailOpen(_TelemetryTestBase):
    def test_post_succeeds_when_emit_objective_raises(self):
        async def go():
            from engine import telemetry
            orig = telemetry.emit_objective

            def _boom(*a, **k):
                raise RuntimeError("sink down")

            telemetry.emit_objective = _boom
            try:
                db = _CommDB()
                # the runtime imports emit_objective from the module namespace,
                # so the monkeypatch is seen at the call site.
                row = await COR.maybe_post(db, None, now_ms=1_000_000)
                self.assertIsNotNone(row)           # post still landed
                self.assertEqual(row["state"], CO.STATE_ACTIVE)
            finally:
                telemetry.emit_objective = orig
        _run(go())

    def test_strike_succeeds_when_emit_raises(self):
        async def go():
            from engine import telemetry
            orig = telemetry.emit

            def _boom(*a, **k):
                raise RuntimeError("sink down")

            telemetry.emit = _boom
            try:
                db = _CommDB()
                await COR.maybe_post(db, None, now_ms=1_000_000)
                char = {"id": 7, "skills": json.dumps({"blaster": 18}),
                        "attributes": json.dumps({"dexterity": 12})}
                res = await COR.record_strike(db, None, char, now_ms=1_000_000)
                # the strike resolved (hit or miss) despite the broken sink
                self.assertIn(res.reason, ("", "miss"))
            finally:
                telemetry.emit = orig
        _run(go())


if __name__ == "__main__":
    unittest.main()
