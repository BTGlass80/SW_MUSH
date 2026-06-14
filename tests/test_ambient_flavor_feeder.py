# -*- coding: utf-8 -*-
"""tests/test_ambient_flavor_feeder.py — Ollama ambient-flavor feeder.

The idle-queue AmbientFlavorTask pre-generates atmospheric room lines per zone
via the local model and feeds them into AmbientEventManager._idle_pool (separate
from the Director's _dynamic_pool, no clobber), era-guarded + capped on ingest by
set_idle_pool. _pick_line draws from the dynamic + idle pools combined. This is
the free local analogue of the Director's paid ambient_pool — useful on a box
where the paid path is gated.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import engine.ambient_events as ae
from engine.ambient_events import AmbientEventManager, MAX_IDLE_LINES_PER_ZONE
from engine.idle_queue import AmbientFlavorTask, IdleQueue


# ── set_idle_pool / refresh ─────────────────────────────────────────────────

class TestSetIdlePool(unittest.TestCase):
    def setUp(self):
        self.mgr = AmbientEventManager()

    def _texts(self, zk):
        return [ln.text for ln in self.mgr._idle_pool.get(zk, [])]

    def test_era_guards_idle_lines(self):
        kept = self.mgr.set_idle_pool("cantina", [
            "Glasses clink as a sabacc game heats up.",   # clean
            "Imperial troopers shove through the crowd.",  # off-era
            "A protocol droid shuffles past, beeping.",    # clean
        ])
        self.assertEqual(kept, 2)
        self.assertEqual(len(self._texts("cantina")), 2)
        self.assertTrue(all("Imperial" not in t for t in self._texts("cantina")))

    def test_separate_from_dynamic_pool_no_clobber(self):
        self.mgr.set_dynamic_pool({"cantina": ["A Director-sourced clean line."]})
        self.mgr.set_idle_pool("cantina", ["An Ollama-sourced clean line."])
        # Both writers coexist.
        self.assertEqual(len(self.mgr._dynamic_pool["cantina"]), 1)
        self.assertEqual(len(self.mgr._idle_pool["cantina"]), 1)

    def test_caps_line_count(self):
        many = [f"Ambient line number {i} hums along quietly." for i in range(20)]
        kept = self.mgr.set_idle_pool("streets", many)
        self.assertEqual(kept, MAX_IDLE_LINES_PER_ZONE)

    def test_all_off_era_leaves_no_pool_but_stamps_ts(self):
        kept = self.mgr.set_idle_pool("docks", [
            "The Empire patrols the docks.",
            "A Rebel spy slips into the shadows.",
        ])
        self.assertEqual(kept, 0)
        self.assertNotIn("docks", self.mgr._idle_pool)
        # ts stamped so we don't immediately re-hammer a garbage-producing zone
        self.assertFalse(self.mgr.idle_pool_needs_refresh("docks", 3600))

    def test_needs_refresh_logic(self):
        self.assertTrue(self.mgr.idle_pool_needs_refresh("cantina", 3600))
        self.mgr.set_idle_pool("cantina", ["A clean ambient line here, friend."])
        self.assertFalse(self.mgr.idle_pool_needs_refresh("cantina", 3600))
        # max_age 0 -> any elapsed time is stale
        self.assertTrue(self.mgr.idle_pool_needs_refresh("cantina", 0))
        # untouched zone always needs refresh
        self.assertTrue(self.mgr.idle_pool_needs_refresh("spaceport", 3600))


# ── _pick_line draws from the idle pool ─────────────────────────────────────

class TestPickLineDrawsIdle(unittest.TestCase):
    def test_pick_line_uses_idle_pool_when_only_idle(self):
        mgr = AmbientEventManager()
        mgr.set_idle_pool("cantina", ["A mournful Bith tune drifts from the band."])
        # Force the "live" branch (30% path) deterministically.
        with mock.patch("engine.ambient_events.random.random", return_value=0.0):
            line = mgr._pick_line("cantina")
        self.assertEqual(line, "A mournful Bith tune drifts from the band.")

    def test_pick_line_combines_dynamic_and_idle(self):
        mgr = AmbientEventManager()
        mgr.set_dynamic_pool({"cantina": ["Director line one."]})
        mgr.set_idle_pool("cantina", ["Ollama line two."])
        seen = set()
        with mock.patch("engine.ambient_events.random.random", return_value=0.0):
            for _ in range(40):
                seen.add(mgr._pick_line("cantina"))
        # Over many draws both pools' lines appear (combined live pool).
        self.assertEqual(seen, {"Director line one.", "Ollama line two."})


# ── AmbientFlavorTask.execute ───────────────────────────────────────────────

class _FakeAI:
    def __init__(self, response):
        self._r = response

    async def generate(self, **kwargs):
        return self._r


class TestAmbientFlavorTask(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ae._manager = None   # singleton reset (CLAUDE.md discipline)

    def tearDown(self):
        ae._manager = None

    async def test_execute_feeds_era_guarded_idle_pool(self):
        payload = json.dumps([
            "Steam hisses from a busted moisture vaporator.",   # clean
            "Stormtroopers kick over a Jawa's scrap pile.",      # off-era
        ])
        task = AmbientFlavorTask(zone_key="streets", zone_tone="dusty frontier")
        await task.execute(_FakeAI(payload), db=None)

        mgr = ae.get_ambient_manager()
        kept = [ln.text for ln in mgr._idle_pool.get("streets", [])]
        self.assertEqual(len(kept), 1, f"off-era line not dropped: {kept}")
        self.assertIn("vaporator", kept[0])

    async def test_execute_bad_json_is_safe(self):
        task = AmbientFlavorTask(zone_key="streets")
        await task.execute(_FakeAI("not json at all"), db=None)
        mgr = ae.get_ambient_manager()
        self.assertNotIn("streets", mgr._idle_pool)


# ── enqueue dedup ───────────────────────────────────────────────────────────

class TestEnqueueAmbientFlavor(unittest.TestCase):
    def test_dedup_one_task_per_zone(self):
        q = IdleQueue(ai_manager=object())
        self.assertTrue(q.enqueue_ambient_flavor("cantina", "seedy", "The Cantina"))
        self.assertFalse(q.enqueue_ambient_flavor("cantina"))  # already pending
        self.assertTrue(q.enqueue_ambient_flavor("spaceport"))
        self.assertEqual(q.pending, 2)

    def test_empty_zone_key_rejected(self):
        q = IdleQueue(ai_manager=object())
        self.assertFalse(q.enqueue_ambient_flavor(""))
        self.assertEqual(q.pending, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
