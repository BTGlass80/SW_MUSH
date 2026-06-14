# -*- coding: utf-8 -*-
"""
tests/test_t2_wenc_wilderness_encounters.py — T2.WENC wilderness
encounter and hazard system.

Per T2.WENC in TODO.json: bring the wilderness encounter selector and
the wilderness path of the hazard tick online for both Dune Sea and
Coruscant Underworld at the minimal-substrate level. The actual
encounter *firing* (NPC spawn, vendor caravan, weather application)
is the T2.WENC.b follow-up; this drop ships the selector + cooldown
+ filters + integration hook + content-authored encounter pools for
both regions.

Test surface
------------

 1. TestEncounterPoolSchemaParse — encounters: block parses; missing
    or malformed entries warn rather than fail; unknown types dropped.

 2. TestRegionsWithoutEncountersAreSilent — a region YAML without an
    encounters: block builds with an EncounterPool whose
    base_chance_per_move is 0 and entries is empty. roll_encounter is
    a no-op on such regions.

 3. TestRollEncounterChanceGate — chance roll honors
    base_chance_per_move (RNG injected).

 4. TestRollEncounterFilters — terrain filter, min_distance_from_edge,
    and faction_gate filter behavior.

 5. TestRollEncounterWeightedPick — weighted selection picks the
    expected entry given a controlled RNG.

 6. TestRollEncounterCooldown — once an encounter fires for a
    character, the next call returns fired=False with reason
    on_cooldown until 60s have elapsed.

 7. TestRollEncounterNoEligibleEntries — chance roll hits but the
    pool filters to empty: returns fired=False with reason
    no_eligible_entries and does NOT mark the cooldown.

 8. TestWildernessHazardTickPath — extending hazards.py: an online
    character in a wilderness tile with a HAZARD_TYPE-mapped
    ambient_hazard runs check_hazard_for_character against a
    synthetic room dict. Aspirational tags (not in HAZARD_TYPES) are
    inert.

 9. TestDuneSeaEncounterPoolAuthored — production Dune Sea YAML now
    has the encounters: block and parses cleanly. Sanity-check on
    the number of entries and key ids.

10. TestCoruscantEncounterPoolAuthored — same for Coruscant
    Underworld.

11. TestRegionAttrEncounterPool — the WildernessRegion dataclass
    carries the encounter_pool attribute on production loads.

12. TestRollEncounterRobustToMissingAttrs — older fixtures or DBs
    that lack encounter_pool entirely (None on the region) don't
    crash the selector.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _write_yaml(tmpdir: str, name: str, content: str) -> str:
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


_MINIMAL_REGION_WITH_ENCOUNTERS = """
schema_version: 1

region:
  slug: test_wenc_region
  name: "Test WENC Region"
  planet: testplanet
  zone: testzone
  default_security: lawless
  narrative_tone_key: test

grid:
  width: 20
  height: 20
  tile_scale_km: 1
  default_terrain: plain

terrains:
  plain:
    move_cost: 1
    sight_radius: 2
    ambient_hazard: none
    hazard_severity: 0
  scrub:
    move_cost: 2
    sight_radius: 1
    ambient_hazard: extreme_heat
    hazard_severity: 1

landmarks: []

encounters:
  base_chance_per_move: 0.10
  pool:
    - id: easy_encounter
      type: non_hostile
      weight: 5
      terrains: [plain]
      narrative: "Something innocuous happens."
    - id: rare_encounter
      type: hostile
      weight: 1
      terrains: [scrub]
      min_distance_from_edge: 3
      narrative: "Something rare and dangerous."
    - id: anywhere_encounter
      type: anomaly
      weight: 1
      terrains: []
      narrative: "An anomaly."
"""


# A deterministic RNG harness — we cycle through a list of values.
class _FakeRNG:
    def __init__(self, randoms=None, randints=None):
        self._randoms = list(randoms or [])
        self._randints = list(randints or [])
        self._r_i = 0
        self._i_i = 0

    def random(self):
        v = self._randoms[self._r_i]
        self._r_i += 1
        return v

    def randint(self, a, b):
        v = self._randints[self._i_i]
        self._i_i += 1
        # Clamp to range
        return max(a, min(b, v))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Schema parse
# ═══════════════════════════════════════════════════════════════════════════


class TestEncounterPoolSchemaParse(unittest.TestCase):

    def test_full_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "region.yaml",
                               _MINIMAL_REGION_WITH_ENCOUNTERS)
            from engine.wilderness_loader import load_wilderness_region
            report = load_wilderness_region(path)
            self.assertTrue(report.ok, msg=str(report.errors))
            region = report.region
            self.assertIsNotNone(region.encounter_pool)
            pool = region.encounter_pool
            self.assertAlmostEqual(pool.base_chance_per_move, 0.10)
            self.assertEqual(len(pool.entries), 3)
            ids = [e.id for e in pool.entries]
            self.assertIn("easy_encounter", ids)
            self.assertIn("rare_encounter", ids)
            self.assertIn("anywhere_encounter", ids)

    def test_missing_block_is_no_op(self):
        # Strip the encounters: block
        yaml = _MINIMAL_REGION_WITH_ENCOUNTERS.split("encounters:")[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "region.yaml", yaml)
            from engine.wilderness_loader import load_wilderness_region
            report = load_wilderness_region(path)
            self.assertTrue(report.ok, msg=str(report.errors))
            pool = report.region.encounter_pool
            self.assertEqual(pool.base_chance_per_move, 0.0)
            self.assertEqual(len(pool.entries), 0)

    def test_unknown_type_dropped(self):
        yaml = _MINIMAL_REGION_WITH_ENCOUNTERS + """
    - id: bogus
      type: not_a_real_type
      narrative: "Should be dropped."
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "region.yaml", yaml)
            from engine.wilderness_loader import load_wilderness_region
            report = load_wilderness_region(path)
            self.assertTrue(report.ok, msg=str(report.errors))
            ids = [e.id for e in report.region.encounter_pool.entries]
            self.assertNotIn("bogus", ids)
            # And a warning was raised
            self.assertTrue(
                any("bogus" in w for w in report.warnings),
                msg=f"Expected warning about bogus type; got {report.warnings}",
            )

    def test_duplicate_id_dropped(self):
        yaml = _MINIMAL_REGION_WITH_ENCOUNTERS + """
    - id: easy_encounter
      type: non_hostile
      narrative: "Duplicate."
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "region.yaml", yaml)
            from engine.wilderness_loader import load_wilderness_region
            report = load_wilderness_region(path)
            self.assertTrue(report.ok)
            # Only one entry with that id
            ids = [e.id for e in report.region.encounter_pool.entries]
            self.assertEqual(ids.count("easy_encounter"), 1)

    def test_clamped_chance_warns(self):
        yaml = _MINIMAL_REGION_WITH_ENCOUNTERS.replace(
            "base_chance_per_move: 0.10", "base_chance_per_move: 5.0"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "region.yaml", yaml)
            from engine.wilderness_loader import load_wilderness_region
            report = load_wilderness_region(path)
            self.assertTrue(report.ok)
            # Clamped to 1.0
            self.assertEqual(report.region.encounter_pool.base_chance_per_move, 1.0)
            self.assertTrue(any("base_chance_per_move" in w for w in report.warnings))

    def test_unknown_terrain_reference_dropped(self):
        yaml = _MINIMAL_REGION_WITH_ENCOUNTERS + """
    - id: bad_terrain_ref
      type: non_hostile
      terrains: [no_such_terrain]
      narrative: "Bad terrain ref."
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_yaml(tmp, "region.yaml", yaml)
            from engine.wilderness_loader import load_wilderness_region
            report = load_wilderness_region(path)
            self.assertTrue(report.ok)
            entry = next(
                (e for e in report.region.encounter_pool.entries if e.id == "bad_terrain_ref"),
                None,
            )
            self.assertIsNotNone(entry)
            # Bad terrain stripped; entry kept (empty terrain list = applies to any)
            self.assertEqual(entry.terrains, [])
            self.assertTrue(any("no_such_terrain" in w for w in report.warnings))


# ═══════════════════════════════════════════════════════════════════════════
# 2. Regions without encounters
# ═══════════════════════════════════════════════════════════════════════════


class TestRegionsWithoutEncountersAreSilent(unittest.TestCase):

    def test_no_op_returns_fired_false(self):
        from engine.wilderness_encounters import (
            roll_encounter, EncounterPool, clear_cooldowns
        )
        # Build a region-shaped object with an empty pool
        clear_cooldowns()

        class _Region:
            grid_width = 10
            grid_height = 10
            default_terrain = "plain"
            terrains = {}
            encounter_pool = EncounterPool()  # default-constructed, empty

        char = {"id": 42}
        result = roll_encounter(
            _Region, new_x=5, new_y=5, terrain="plain", char=char,
        )
        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "no_pool_configured")
        self.assertIsNone(result.entry)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Chance gate
# ═══════════════════════════════════════════════════════════════════════════


class TestRollEncounterChanceGate(unittest.TestCase):

    def setUp(self):
        from engine.wilderness_encounters import clear_cooldowns
        clear_cooldowns()
        self._make_region()

    def _make_region(self):
        from engine.wilderness_encounters import (
            EncounterEntry, EncounterPool
        )

        class _Region:
            grid_width = 10
            grid_height = 10
            default_terrain = "plain"
            terrains = {"plain": object(), "scrub": object()}
            encounter_pool = EncounterPool(
                base_chance_per_move=0.10,
                entries=[
                    EncounterEntry(
                        id="any",
                        type="non_hostile",
                        weight=1,
                        terrains=[],
                        narrative="hi",
                    ),
                ],
            )
        self.region = _Region

    def test_chance_miss(self):
        from engine.wilderness_encounters import roll_encounter
        # Random returns 0.9 — way above 0.10 threshold
        rng = _FakeRNG(randoms=[0.9])
        result = roll_encounter(
            self.region, new_x=5, new_y=5, terrain="plain",
            char={"id": 1}, rng=rng,
        )
        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "chance_miss")

    def test_chance_hit(self):
        from engine.wilderness_encounters import roll_encounter
        # Random returns 0.05 — below 0.10 threshold
        rng = _FakeRNG(randoms=[0.05], randints=[1])
        result = roll_encounter(
            self.region, new_x=5, new_y=5, terrain="plain",
            char={"id": 1}, rng=rng,
        )
        self.assertTrue(result.fired)
        self.assertEqual(result.entry.id, "any")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Filters
# ═══════════════════════════════════════════════════════════════════════════


class TestRollEncounterFilters(unittest.TestCase):

    def setUp(self):
        from engine.wilderness_encounters import (
            EncounterEntry, EncounterPool, clear_cooldowns
        )
        clear_cooldowns()

        class _Region:
            grid_width = 20
            grid_height = 20
            default_terrain = "plain"
            terrains = {"plain": object(), "scrub": object()}
            encounter_pool = EncounterPool(
                base_chance_per_move=1.0,  # always rolls
                entries=[
                    EncounterEntry(
                        id="only_plain",
                        type="non_hostile",
                        weight=1,
                        terrains=["plain"],
                        narrative="plain only",
                    ),
                    EncounterEntry(
                        id="only_scrub",
                        type="hostile",
                        weight=1,
                        terrains=["scrub"],
                        narrative="scrub only",
                    ),
                    EncounterEntry(
                        id="needs_deep",
                        type="anomaly",
                        weight=1,
                        terrains=[],
                        min_distance_from_edge=5,
                        narrative="needs deep",
                    ),
                ],
            )
        self.region = _Region

    def test_terrain_filter_picks_plain_at_plain(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()
        rng = _FakeRNG(randoms=[0.0], randints=[1])
        # At edge (x=0, y=10), distance_from_edge = 0 → needs_deep filtered out
        # Terrain = plain → only_plain is eligible (plus anywhere/needs_deep is out by distance)
        result = roll_encounter(
            self.region, new_x=0, new_y=10, terrain="plain",
            char={"id": 100}, rng=rng,
        )
        self.assertTrue(result.fired)
        self.assertEqual(result.entry.id, "only_plain")

    def test_terrain_filter_picks_scrub_at_scrub(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()
        rng = _FakeRNG(randoms=[0.0], randints=[1])
        result = roll_encounter(
            self.region, new_x=0, new_y=10, terrain="scrub",
            char={"id": 101}, rng=rng,
        )
        self.assertTrue(result.fired)
        self.assertEqual(result.entry.id, "only_scrub")

    def test_distance_gates_deep_encounter(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()
        # Tile (10, 10) on a 20x20 grid → distance_from_edge = 9, ≥ 5
        # Should make needs_deep eligible. Terrain "plain" → only_plain
        # and needs_deep both eligible.
        rng = _FakeRNG(randoms=[0.0], randints=[2])  # second entry
        result = roll_encounter(
            self.region, new_x=10, new_y=10, terrain="plain",
            char={"id": 102}, rng=rng,
        )
        self.assertTrue(result.fired)
        # With randint(1, 2) returning 2, the second of two eligibles wins
        self.assertEqual(result.entry.id, "needs_deep")

    def test_faction_gate_runs(self):
        # The stub evaluate_faction_gate returns True; verify a string
        # gate doesn't filter the entry out by default.
        from engine.wilderness_encounters import (
            roll_encounter, EncounterEntry, EncounterPool, clear_cooldowns
        )
        clear_cooldowns()

        class _Region:
            grid_width = 10
            grid_height = 10
            default_terrain = "plain"
            terrains = {"plain": object()}
            encounter_pool = EncounterPool(
                base_chance_per_move=1.0,
                entries=[
                    EncounterEntry(
                        id="gated",
                        type="non_hostile",
                        weight=1,
                        terrains=[],
                        faction_gate="some_gate_string",
                        narrative="gated",
                    ),
                ],
            )

        rng = _FakeRNG(randoms=[0.0], randints=[1])
        result = roll_encounter(
            _Region, new_x=5, new_y=5, terrain="plain",
            char={"id": 103}, rng=rng,
        )
        self.assertTrue(result.fired)
        self.assertEqual(result.entry.id, "gated")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Weighted pick
# ═══════════════════════════════════════════════════════════════════════════


class TestRollEncounterWeightedPick(unittest.TestCase):

    def setUp(self):
        from engine.wilderness_encounters import (
            EncounterEntry, EncounterPool, clear_cooldowns
        )
        clear_cooldowns()

        class _Region:
            grid_width = 10
            grid_height = 10
            default_terrain = "plain"
            terrains = {"plain": object()}
            encounter_pool = EncounterPool(
                base_chance_per_move=1.0,
                entries=[
                    EncounterEntry(id="a", type="non_hostile",
                                    weight=3, terrains=[], narrative="a"),
                    EncounterEntry(id="b", type="non_hostile",
                                    weight=1, terrains=[], narrative="b"),
                    EncounterEntry(id="c", type="non_hostile",
                                    weight=1, terrains=[], narrative="c"),
                ],
            )
        self.region = _Region

    def test_pick_first_when_low(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()
        rng = _FakeRNG(randoms=[0.0], randints=[1])
        r = roll_encounter(self.region, new_x=5, new_y=5, terrain="plain",
                            char={"id": 1}, rng=rng)
        self.assertEqual(r.entry.id, "a")

    def test_pick_mid_when_in_a_range(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()
        rng = _FakeRNG(randoms=[0.0], randints=[3])
        r = roll_encounter(self.region, new_x=5, new_y=5, terrain="plain",
                            char={"id": 2}, rng=rng)
        self.assertEqual(r.entry.id, "a")  # weights 3+1+1; pick=3 still hits a

    def test_pick_b(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()
        rng = _FakeRNG(randoms=[0.0], randints=[4])
        r = roll_encounter(self.region, new_x=5, new_y=5, terrain="plain",
                            char={"id": 3}, rng=rng)
        self.assertEqual(r.entry.id, "b")

    def test_pick_c(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()
        rng = _FakeRNG(randoms=[0.0], randints=[5])
        r = roll_encounter(self.region, new_x=5, new_y=5, terrain="plain",
                            char={"id": 4}, rng=rng)
        self.assertEqual(r.entry.id, "c")


# ═══════════════════════════════════════════════════════════════════════════
# 6. Cooldown
# ═══════════════════════════════════════════════════════════════════════════


class TestRollEncounterCooldown(unittest.TestCase):

    def setUp(self):
        from engine.wilderness_encounters import (
            EncounterEntry, EncounterPool, clear_cooldowns
        )
        clear_cooldowns()

        class _Region:
            grid_width = 10
            grid_height = 10
            default_terrain = "plain"
            terrains = {"plain": object()}
            encounter_pool = EncounterPool(
                base_chance_per_move=1.0,
                entries=[
                    EncounterEntry(id="always", type="non_hostile",
                                    weight=1, terrains=[], narrative="x"),
                ],
            )
        self.region = _Region

    def test_first_fires_then_cools_down(self):
        from engine.wilderness_encounters import roll_encounter
        # First call: t=1000.0
        r1 = roll_encounter(
            self.region, new_x=5, new_y=5, terrain="plain",
            char={"id": 50}, rng=_FakeRNG(randoms=[0.0], randints=[1]),
            now=1000.0,
        )
        self.assertTrue(r1.fired)
        # Second call: t=1010.0, 10s later — should be cooled down
        r2 = roll_encounter(
            self.region, new_x=5, new_y=5, terrain="plain",
            char={"id": 50}, rng=_FakeRNG(randoms=[0.0], randints=[1]),
            now=1010.0,
        )
        self.assertFalse(r2.fired)
        self.assertEqual(r2.reason, "on_cooldown")
        # Third call: t=1100.0, 100s after first — past 60s window
        r3 = roll_encounter(
            self.region, new_x=5, new_y=5, terrain="plain",
            char={"id": 50}, rng=_FakeRNG(randoms=[0.0], randints=[1]),
            now=1100.0,
        )
        self.assertTrue(r3.fired)

    def test_cooldown_is_per_character(self):
        from engine.wilderness_encounters import roll_encounter
        r1 = roll_encounter(
            self.region, new_x=5, new_y=5, terrain="plain",
            char={"id": 60}, rng=_FakeRNG(randoms=[0.0], randints=[1]),
            now=2000.0,
        )
        self.assertTrue(r1.fired)
        # Different character, same time — should fire (independent cooldown)
        r2 = roll_encounter(
            self.region, new_x=5, new_y=5, terrain="plain",
            char={"id": 61}, rng=_FakeRNG(randoms=[0.0], randints=[1]),
            now=2000.0,
        )
        self.assertTrue(r2.fired)


# ═══════════════════════════════════════════════════════════════════════════
# 7. No-eligible-entries doesn't burn cooldown
# ═══════════════════════════════════════════════════════════════════════════


class TestRollEncounterNoEligibleEntries(unittest.TestCase):

    def test_no_eligible_does_not_cooldown(self):
        from engine.wilderness_encounters import (
            roll_encounter, EncounterEntry, EncounterPool, clear_cooldowns
        )
        clear_cooldowns()

        class _Region:
            grid_width = 10
            grid_height = 10
            default_terrain = "plain"
            terrains = {"plain": object(), "rare_terrain": object()}
            encounter_pool = EncounterPool(
                base_chance_per_move=1.0,
                entries=[
                    EncounterEntry(
                        id="only_rare",
                        type="hostile",
                        weight=1,
                        terrains=["rare_terrain"],
                        narrative="rare",
                    ),
                ],
            )

        # Move into plain terrain — pool only matches rare_terrain → no eligible
        r1 = roll_encounter(
            _Region, new_x=5, new_y=5, terrain="plain",
            char={"id": 70}, rng=_FakeRNG(randoms=[0.0], randints=[1]),
            now=3000.0,
        )
        self.assertFalse(r1.fired)
        self.assertEqual(r1.reason, "no_eligible_entries")

        # Immediately re-roll into rare_terrain — should fire because no
        # cooldown was set on the empty-eligibles miss
        r2 = roll_encounter(
            _Region, new_x=5, new_y=5, terrain="rare_terrain",
            char={"id": 70}, rng=_FakeRNG(randoms=[0.0], randints=[1]),
            now=3001.0,
        )
        self.assertTrue(r2.fired)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Wilderness hazard tick path
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow  # heavy: subprocess
class TestWildernessHazardTickPath(unittest.TestCase):
    """Verify that hazards.hazard_tick walks the wilderness path.

    May 24 2026 — Python 3.14 compatibility: the original three test
    methods used ``asyncio.get_event_loop().run_until_complete(...)``,
    which raises ``RuntimeError: There is no current event loop in
    thread 'MainThread'`` on 3.14 (and is deprecated/slated-for-
    removal earlier). Replaced with ``asyncio.run(...)`` — creates a
    fresh event loop per call and closes it cleanly, which is the
    modern idiom and is also what Python 3.10+ documentation
    recommends. No engine code changes.
    """

    def test_known_hazard_type_runs_check(self):
        import asyncio
        from engine import hazards as hazards_mod

        # Fake region with a known HAZARD_TYPE on its default terrain
        class _Terrain:
            ambient_hazard = "extreme_heat"
            hazard_severity = 2

        class _Region:
            slug = "test_wilderness"
            default_terrain = "dune"
            terrains = {"dune": _Terrain()}
            grid_width = 10
            grid_height = 10

        # Patch wilderness_movement helpers to point at our fake region
        async def _fake_load(db, slug):
            return _Region
        from engine import wilderness_movement as wm
        orig_load = wm.get_or_load_region
        wm.get_or_load_region = _fake_load

        # Patch hazards.check_hazard_for_character to record the call
        calls = []

        async def _fake_check(char, room, db, session=None):
            calls.append({"char_id": char.get("id"), "room": room})
            return None

        orig_check = hazards_mod.check_hazard_for_character
        hazards_mod.check_hazard_for_character = _fake_check

        try:
            char = {
                "id": 999,
                "wilderness_region_slug": "test_wilderness",
                "wilderness_x": 5,
                "wilderness_y": 5,
            }

            class _Sess:
                is_in_game = True
                character = char

            class _Mgr:
                all = [_Sess()]

            class _DB:
                async def get_room(self, room_id):
                    return None

            asyncio.run(
                hazards_mod.hazard_tick(_DB(), _Mgr())
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["char_id"], 999)
            # Synthetic room must carry the hazard config
            import json as _j
            props = _j.loads(calls[0]["room"]["properties"])
            self.assertEqual(props["environment_hazard"]["type"], "extreme_heat")
            self.assertEqual(props["environment_hazard"]["severity"], 2)
            # And the pseudo room id is negative
            self.assertLess(calls[0]["room"]["id"], 0)
        finally:
            wm.get_or_load_region = orig_load
            hazards_mod.check_hazard_for_character = orig_check

    def test_aspirational_hazard_is_inert(self):
        import asyncio
        from engine import hazards as hazards_mod

        class _Terrain:
            ambient_hazard = "structural_collapse"  # not in HAZARD_TYPES
            hazard_severity = 1

        class _Region:
            slug = "test_aspirational"
            default_terrain = "ruin"
            terrains = {"ruin": _Terrain()}
            grid_width = 10
            grid_height = 10

        from engine import wilderness_movement as wm

        async def _fake_load(db, slug):
            return _Region

        orig_load = wm.get_or_load_region
        wm.get_or_load_region = _fake_load

        calls = []

        async def _fake_check(char, room, db, session=None):
            calls.append(1)
            return None

        orig_check = hazards_mod.check_hazard_for_character
        hazards_mod.check_hazard_for_character = _fake_check

        try:
            char = {
                "id": 998,
                "wilderness_region_slug": "test_aspirational",
                "wilderness_x": 5,
                "wilderness_y": 5,
            }

            class _Sess:
                is_in_game = True
                character = char

            class _Mgr:
                all = [_Sess()]

            class _DB:
                async def get_room(self, room_id):
                    return None

            asyncio.run(
                hazards_mod.hazard_tick(_DB(), _Mgr())
            )
            # Aspirational tag → no check call
            self.assertEqual(len(calls), 0)
        finally:
            wm.get_or_load_region = orig_load
            hazards_mod.check_hazard_for_character = orig_check

    def test_severity_zero_is_inert(self):
        import asyncio
        from engine import hazards as hazards_mod

        class _Terrain:
            ambient_hazard = "extreme_heat"  # known type
            hazard_severity = 0  # but severity 0

        class _Region:
            slug = "test_zero_sev"
            default_terrain = "oasis"
            terrains = {"oasis": _Terrain()}
            grid_width = 10
            grid_height = 10

        from engine import wilderness_movement as wm

        async def _fake_load(db, slug):
            return _Region

        orig_load = wm.get_or_load_region
        wm.get_or_load_region = _fake_load

        calls = []

        async def _fake_check(char, room, db, session=None):
            calls.append(1)
            return None

        orig_check = hazards_mod.check_hazard_for_character
        hazards_mod.check_hazard_for_character = _fake_check

        try:
            char = {
                "id": 997,
                "wilderness_region_slug": "test_zero_sev",
                "wilderness_x": 5,
                "wilderness_y": 5,
            }

            class _Sess:
                is_in_game = True
                character = char

            class _Mgr:
                all = [_Sess()]

            class _DB:
                async def get_room(self, room_id):
                    return None

            asyncio.run(
                hazards_mod.hazard_tick(_DB(), _Mgr())
            )
            self.assertEqual(len(calls), 0)
        finally:
            wm.get_or_load_region = orig_load
            hazards_mod.check_hazard_for_character = orig_check


# ═══════════════════════════════════════════════════════════════════════════
# 9. Dune Sea production pool
# ═══════════════════════════════════════════════════════════════════════════


class TestDuneSeaEncounterPoolAuthored(unittest.TestCase):

    def test_dune_sea_loads_with_encounters(self):
        from engine.wilderness_loader import load_wilderness_region
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness",
            "dune_sea.yaml",
        )
        report = load_wilderness_region(path)
        self.assertTrue(report.ok, msg=str(report.errors))
        pool = report.region.encounter_pool
        self.assertIsNotNone(pool)
        # base_chance default
        self.assertAlmostEqual(pool.base_chance_per_move, 0.04)
        # ~9 entries authored
        self.assertGreaterEqual(len(pool.entries), 8)
        ids = [e.id for e in pool.entries]
        # Spot-check key ids
        self.assertIn("tusken_scout_party", ids)
        self.assertIn("tusken_war_party", ids)
        self.assertIn("jawa_sandcrawler_stop", ids)
        self.assertIn("sandstorm_approaching", ids)
        # Type distribution covers all 5 design §5.2 types
        types = {e.type for e in pool.entries}
        self.assertIn("hostile", types)
        self.assertIn("non_hostile", types)
        self.assertIn("trader_caravan", types)
        self.assertIn("anomaly", types)
        self.assertIn("weather", types)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Coruscant production pool
# ═══════════════════════════════════════════════════════════════════════════


class TestCoruscantEncounterPoolAuthored(unittest.TestCase):

    def test_coruscant_loads_with_encounters(self):
        from engine.wilderness_loader import load_wilderness_region
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness",
            "coruscant_underworld.yaml",
        )
        report = load_wilderness_region(path)
        self.assertTrue(report.ok, msg=str(report.errors))
        pool = report.region.encounter_pool
        self.assertIsNotNone(pool)
        self.assertAlmostEqual(pool.base_chance_per_move, 0.05)
        self.assertGreaterEqual(len(pool.entries), 9)
        ids = [e.id for e in pool.entries]
        self.assertIn("gang_patrol", ids)
        self.assertIn("maze_ambush", ids)
        self.assertIn("black_market_pop_up", ids)
        self.assertIn("ventilation_failure", ids)
        types = {e.type for e in pool.entries}
        self.assertIn("hostile", types)
        self.assertIn("non_hostile", types)
        self.assertIn("trader_caravan", types)
        self.assertIn("anomaly", types)
        self.assertIn("weather", types)


# ═══════════════════════════════════════════════════════════════════════════
# 11. encounter_pool attribute on the dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestRegionAttrEncounterPool(unittest.TestCase):

    def test_attr_present_on_wilderness_region(self):
        from engine.wilderness_loader import WildernessRegion
        # Default-construct with no encounter_pool → falls back to None
        r = WildernessRegion(
            slug="x", name="x", planet="x", zone="x",
            default_security="lawless",
            grid_width=10, grid_height=10, tile_scale_km=1,
            default_terrain="plain",
            terrains={}, landmarks=[],
        )
        self.assertTrue(hasattr(r, "encounter_pool"))


# ═══════════════════════════════════════════════════════════════════════════
# 12. Defensive: region without encounter_pool doesn't crash selector
# ═══════════════════════════════════════════════════════════════════════════


class TestRollEncounterRobustToMissingAttrs(unittest.TestCase):

    def test_missing_attr_is_no_op(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()

        class _BareRegion:
            grid_width = 10
            grid_height = 10
            default_terrain = "plain"
            terrains = {}
            # No encounter_pool attribute at all

        result = roll_encounter(
            _BareRegion, new_x=5, new_y=5, terrain="plain",
            char={"id": 999},
        )
        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "no_pool_configured")

    def test_none_pool_is_no_op(self):
        from engine.wilderness_encounters import roll_encounter, clear_cooldowns
        clear_cooldowns()

        class _Region:
            grid_width = 10
            grid_height = 10
            default_terrain = "plain"
            terrains = {}
            encounter_pool = None  # explicit None

        result = roll_encounter(
            _Region, new_x=5, new_y=5, terrain="plain",
            char={"id": 999},
        )
        self.assertFalse(result.fired)


if __name__ == "__main__":
    unittest.main()
