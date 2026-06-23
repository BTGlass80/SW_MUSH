# -*- coding: utf-8 -*-
"""
tests/test_contest_anchor_lifecycle.py

Per-drop guard for the 2026-06-14 contest anchor-lifecycle drop (from the engine
defect-hunt — docs/design/HANDOFF_engine_defect_hunt_2026-06-14.md). Four
confirmed defects in engine/contest.py:

  1. anchor_npcs_never_despawned (HIGH): no resolution path deleted the Region
     Anchor NPC + reinforcements (they're created via db.create_npc and never
     registered in region_garrison, so dismiss_region_garrison can't reach them,
     and no reaper exists) — every resolved contest orphaned 1-5 permanent
     hostile NPCs in the landmark room. Fix: _despawn_contest_anchor, called from
     both _resolve_defender_win and _resolve_challenger_win (which between them
     cover every outcome path).
  2. stale_anchor_reuse (MEDIUM): the deterministic anchor name + create_npc's
     (name,room) de-dup handed back a leftover anchor on a later same-landmark
     contest. Fix: per-contest-unique name (`... (#<contest_id>)`).
  3. anchor_spawn_not_idempotent (MEDIUM): on a pin-UPDATE failure the orphan
     anchor was left live + unpinned, so the next tick spawned a SECOND anchor.
     Fix: early-return if already pinned; delete the orphan + bail on pin failure.
  4. resolution_update_missing_active_guard (LOW): both resolution UPDATEs lacked
     an `AND status='active'` compare-and-swap, so a boundary interleave could
     double-resolve + double-apply penalties. Fix: CAS + rowcount check.
"""

import asyncio
import inspect
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


class _Cur:
    def __init__(self, rowcount, lastrowid):
        self.rowcount = rowcount
        self.lastrowid = lastrowid


class _FakeDB:
    """Minimal async DB recording the calls the contest resolution path makes.
    Territory helpers (garrison spawn/dismiss, influence) are real imports; with
    zone_id=None / defender_org=None they short-circuit or are swallowed by the
    resolution functions' own try/except, so the fake never needs them."""

    def __init__(self, rowcount=1):
        self._rowcount = rowcount
        self.executed = []        # (sql, params)
        self.deleted_npcs = []
        self.created = []
        self.commits = 0
        self._next = 5000

    async def execute(self, sql, params=()):
        self.executed.append((sql, params))
        return _Cur(self._rowcount, self._next)

    async def commit(self):
        self.commits += 1

    async def delete_npc(self, npc_id):
        self.deleted_npcs.append(int(npc_id))
        return True

    async def create_npc(self, **kw):
        self._next += 1
        self.created.append(kw)
        return self._next

    async def fetchall(self, sql, params=()):
        return []


def _contest(**over):
    c = {
        "id": 42,
        "region_slug": "outer_dustbelt",
        "challenger_org_code": "czerka",
        "defender_org_code": None,
        "zone_id": None,
        "anchor_npc_id": 777,
    }
    c.update(over)
    return c


class TestDespawnHelper(unittest.TestCase):
    def test_despawns_anchor_and_reinforcements(self):
        async def _t():
            from engine.contest import _despawn_contest_anchor
            db = _FakeDB()
            await _despawn_contest_anchor(db, _contest(id=42, anchor_npc_id=777))
            self.assertIn(777, db.deleted_npcs, "anchor NPC not despawned")
            self.assertTrue(
                any("anchor_reinforcement_for" in sql for sql, _ in db.executed),
                "reinforcements not despawned by tag",
            )
        _run(_t())

    def test_no_anchor_id_is_safe(self):
        async def _t():
            from engine.contest import _despawn_contest_anchor
            db = _FakeDB()
            await _despawn_contest_anchor(db, _contest(anchor_npc_id=None))
            self.assertEqual(db.deleted_npcs, [])
            # still reaps reinforcements by contest id
            self.assertTrue(any("anchor_reinforcement_for" in sql
                                for sql, _ in db.executed))
        _run(_t())


class TestResolutionDespawnsAndCAS(unittest.TestCase):
    def test_defender_win_despawns_anchor(self):
        async def _t():
            from engine.contest import _resolve_defender_win
            db = _FakeDB(rowcount=1)
            await _resolve_defender_win(db, _contest(anchor_npc_id=777))
            self.assertIn(777, db.deleted_npcs,
                          "defender-win must despawn the anchor")
            # CAS clause present
            self.assertTrue(any("status = 'active'" in sql
                                for sql, _ in db.executed
                                if "resolved_defender" in sql))
        _run(_t())

    def test_defender_win_cas_skips_when_already_resolved(self):
        async def _t():
            from engine.contest import _resolve_defender_win
            db = _FakeDB(rowcount=0)   # the CAS flips 0 rows → already resolved
            await _resolve_defender_win(db, _contest(anchor_npc_id=777))
            self.assertEqual(db.deleted_npcs, [],
                             "a no-op CAS must NOT despawn (the other writer owns it)")
            # DELETE (clear stale same-status resolved row) + the CAS UPDATE
            # both run, then the no-op CAS (rowcount 0) bails before any
            # cooldown/penalty/transfer follow-up. The pre-UPDATE DELETE was
            # added by the QA contest-second-resolution fix (2026-06-22); that
            # is the +1 statement vs the old single-UPDATE count.
            self.assertEqual(len(db.executed), 2,
                             "must bail right after the no-op CAS (DELETE + UPDATE)")
        _run(_t())

    def test_challenger_win_despawns_anchor(self):
        async def _t():
            from engine.contest import _resolve_challenger_win
            db = _FakeDB(rowcount=1)
            await _resolve_challenger_win(db, _contest(anchor_npc_id=777), "czerka")
            self.assertIn(777, db.deleted_npcs,
                          "challenger-win must despawn the (dead) anchor row")
        _run(_t())

    def test_challenger_win_cas_skips_when_already_resolved(self):
        async def _t():
            from engine.contest import _resolve_challenger_win
            db = _FakeDB(rowcount=0)
            await _resolve_challenger_win(db, _contest(anchor_npc_id=777), "czerka")
            self.assertEqual(db.deleted_npcs, [])
            # DELETE + CAS UPDATE run, then bail on the no-op CAS (see the
            # defender-win twin above for the QA-2026-06-22 rationale).
            self.assertEqual(len(db.executed), 2)
        _run(_t())


class TestSpawnIdempotency(unittest.TestCase):
    def test_spawn_early_returns_when_already_pinned(self):
        async def _t():
            from engine.contest import _spawn_region_anchor
            db = _FakeDB()
            rv = await _spawn_region_anchor(db, _contest(anchor_npc_id=555))
            self.assertEqual(rv, 555, "must return the existing pinned anchor id")
            self.assertEqual(db.created, [], "must NOT create a second anchor")
        _run(_t())


class TestSourceGuards(unittest.TestCase):
    """Pin the two fixes whose full behavioral path needs heavy world setup."""

    def test_anchor_name_is_per_contest_unique(self):
        from engine import contest
        src = inspect.getsource(contest._spawn_region_anchor)
        self.assertIn("(#{contest_id})", src,
                      "anchor name must carry the contest id to defeat create_npc de-dup")

    def test_pin_failure_removes_orphan_anchor(self):
        from engine import contest
        src = inspect.getsource(contest._spawn_region_anchor)
        # the pin-failure branch must delete the just-created NPC and bail
        self.assertIn("removing orphan", src)
        self.assertIn("delete_npc", src)


if __name__ == "__main__":
    unittest.main()
