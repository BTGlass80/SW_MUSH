# -*- coding: utf-8 -*-
"""
tests/test_encounter_count_range.py — regression guard for
TD.ENCOUNTER_COUNT_RANGE_IGNORED (drop encounter-count-range).

Before this drop, ``engine.creature_library.creature_spawn_count`` could not
parse an encounter payload's ``[lo, hi]`` range ``count``: ``int([4, 6])`` raised
``TypeError``, was swallowed, and EVERY ranged wilderness encounter silently
spawned the creature's ``pack_count`` minimum (e.g. the six-rider Tusken war
party fielded 2). The fix rolls the authored range with a deliberate LOW bias
(``min`` of two uniform rolls — Brian ruling: "ship, bias low").

These tests pin: (1) a range now rolls within the inclusive bounds; (2) the roll
is low-biased (mean below the uniform midpoint) yet still spans the full range;
(3) the old always-minimum bug is gone; (4) scalar/edge/malformed inputs are
unchanged; (5) the spawn bridge honors a ranged count end-to-end.
"""
import asyncio
import json
import random
import unittest

import engine.creature_library as CL
from engine.creature_library import creature_spawn_count, _roll_low_biased


class TestRollLowBiased(unittest.TestCase):
    def test_always_within_inclusive_bounds(self):
        random.seed(1234)
        for _ in range(3000):
            r = _roll_low_biased(4, 6)
            self.assertIn(r, (4, 5, 6))

    def test_degenerate_range_returns_lo(self):
        self.assertEqual(_roll_low_biased(5, 5), 5)
        # hi < lo is defensive: never raises, returns lo
        self.assertEqual(_roll_low_biased(6, 4), 6)

    def test_low_biased_mean_below_uniform_midpoint(self):
        random.seed(99)
        lo, hi = 2, 8
        n = 20000
        total = sum(_roll_low_biased(lo, hi) for _ in range(n))
        mean = total / n
        midpoint = (lo + hi) / 2  # 5.0 (a uniform roll's mean)
        # min-of-two-rolls sits ~a third up the range -> ~4.0, clearly below 5.0
        self.assertLess(mean, midpoint - 0.4,
                        f"mean {mean:.3f} not meaningfully below midpoint {midpoint}")
        self.assertGreater(mean, lo,
                           f"mean {mean:.3f} collapsed to the minimum (no roll happening)")

    def test_spans_the_full_range(self):
        random.seed(7)
        seen = {_roll_low_biased(3, 5) for _ in range(2000)}
        self.assertEqual(seen, {3, 4, 5},
                         f"low-biased roll did not span the full range, saw {sorted(seen)}")


class TestCreatureSpawnCountRange(unittest.TestCase):
    def test_range_count_rolls_within_bounds(self):
        random.seed(42)
        for _ in range(2000):
            n = creature_spawn_count({}, {"count": [4, 6]})
            self.assertIn(n, (4, 5, 6))

    def test_range_count_no_longer_always_minimum(self):
        # The exact bug: a [4,6] encounter used to ALWAYS spawn 4.
        random.seed(3)
        results = {creature_spawn_count({}, {"count": [4, 6]}) for _ in range(2000)}
        self.assertTrue(results - {4},
                        "range count still collapses to the minimum (bug not fixed)")

    def test_reversed_range_is_sorted(self):
        random.seed(11)
        for _ in range(500):
            n = creature_spawn_count({}, {"count": [6, 4]})
            self.assertIn(n, (4, 5, 6))

    def test_single_element_list_is_scalar(self):
        self.assertEqual(creature_spawn_count({}, {"count": [3]}), 3)

    def test_malformed_range_falls_back_to_pack(self):
        # non-int elements -> fall through to pack_count low end
        creature = {"pack_count": [2, 5]}
        self.assertEqual(creature_spawn_count(creature, {"count": ["x", "y"]}), 2)
        # empty list -> same fallback
        self.assertEqual(creature_spawn_count(creature, {"count": []}), 2)

    def test_scalar_count_unchanged(self):
        self.assertEqual(creature_spawn_count({}, {"count": 3}), 3)
        self.assertEqual(creature_spawn_count({}, {"count": 0}), 1)  # clamped to >=1

    def test_no_count_uses_pack_minimum(self):
        self.assertEqual(creature_spawn_count({"pack_count": [3, 6]}, {}), 3)

    def test_solo_creature_defaults_to_one(self):
        self.assertEqual(creature_spawn_count({}, {}), 1)


class _FakeDB:
    def __init__(self):
        self.created = []
        self._next = 7000

    async def create_npc(self, *, name, room_id, species, description,
                         char_sheet_json, ai_config_json):
        self._next += 1
        self.created.append({"id": self._next, "name": name})
        return self._next


class _Entry:
    def __init__(self, id, type, payload):
        self.id = id
        self.type = type
        self.payload = payload


class TestSpawnBridgeHonorsRange(unittest.TestCase):
    def test_ranged_encounter_spawns_within_range(self):
        from engine.wilderness_encounter_runtime import spawn_encounter_creatures
        # Use a real library creature so the bridge resolves a template.
        tmpl = None
        for cid, c in CL.load_creature_library().items():
            tmpl = cid
            break
        self.assertIsNotNone(tmpl, "creature library is empty")
        random.seed(55)
        counts = set()
        for _ in range(40):
            db = _FakeDB()
            entry = _Entry("ranged_test", "hostile",
                           {"npc_template": tmpl, "count": [3, 5]})
            ids = asyncio.run(spawn_encounter_creatures(db, entry, room_id=1))
            self.assertEqual(len(ids), len(db.created))
            self.assertIn(len(ids), (3, 4, 5),
                          f"ranged spawn produced {len(ids)} (outside [3,5])")
            counts.add(len(ids))
        # over 40 runs we should see more than just the minimum (bias-low, not always-min)
        self.assertTrue(counts - {3}, f"spawn count never exceeded the minimum: {counts}")


if __name__ == "__main__":
    unittest.main()
