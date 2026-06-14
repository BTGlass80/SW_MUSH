# -*- coding: utf-8 -*-
"""
tests/test_coruscant_underworld_encounter_depth.py

Per-drop guard for the 2026-06-14 "wilderness encounter depth" drop
(HANDOFF_parallel_defect_hunt_session_2026-06-14.md lane 1): 11 new
sub-region-flavor encounters added to the Coruscant Underworld region pool
(NE smuggler reaches / NW industrial overflow / SE Maze fringe / SW deep warren).

These assertions are SPECIFIC to this drop (the global resolution guard in
test_wilderness_encounter_template_resolution.py auto-covers template
resolution; this file pins the *intent* of the new entries so a later edit
that silently drops one, breaks its gating, or smuggles in an off-era string
fails loudly):

  * all 11 new ids load (loaded via the same loader the world build walks);
  * the region loads with NO warnings (catches a dropped terrain ref / dup id
    / bad band that the loader would otherwise warn-and-continue past);
  * every new entry's type is allowed and every terrain resolves to a defined
    region terrain (no silently-dropped terrain reference);
  * the deep bottom_dark entries are min_band>=3 gated (like maze_ambush) so
    frontier travelers never draw them;
  * phantom-free: the one creature-spawning new entry resolves in the creature
    library and reuses an established creature; any anomaly salvage_table is
    from the established set;
  * era cleanness (B3): no GCW/Empire/Rebel/Sith-org tokens in the new
    player-facing narratives.
"""

import os
import re
import sys
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

ERA_DIR = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")

NEW_IDS = {
    # NE smuggler reaches
    "contraband_courier_passing", "stripped_surveillance_housing", "rival_cargo_crew",
    # NW industrial overflow
    "off_shift_ration_share", "forced_shutter_family", "grid_tap_rumor_runner",
    # SE Maze fringe
    "maze_fringe_apex_sign", "maze_fringe_lost_hunters_cache",
    # SW deep warren
    "stratum_archaeologist_at_work", "pipe_market_cookfire", "null_gallery_transit",
}

# Deep, bottom_dark, band-gated entries (must stay gated out of low-band tiles).
DEEP_BAND_GATED = {"maze_fringe_apex_sign", "maze_fringe_lost_hunters_cache",
                   "null_gallery_transit"}

ALLOWED_TYPES = {"hostile", "non_hostile", "trader_caravan", "anomaly", "weather"}
ESTABLISHED_SALVAGE = {"speeder_wreck_table", "tech_cache_table"}

# B3 forbidden tokens (word-boundary; comment/era-key exempt — these are
# checked only against player-facing narrative strings).
FORBIDDEN = [r"\bimperial\b", r"\bempire\b", r"\bstormtrooper", r"\btie\b",
             r"\brebel\b", r"\brebellion\b", r"\binquisitor", r"\bdeath star\b",
             r"\bgalactic empire\b"]


def _region():
    from engine.wilderness_loader import load_era_wilderness_regions
    reps = load_era_wilderness_regions(ERA_DIR)
    for rep in reps:
        reg = getattr(rep, "region", None)
        if getattr(rep, "ok", False) and reg is not None and reg.slug == "coruscant_underworld":
            return rep, reg
    raise AssertionError("coruscant_underworld region did not load")


class TestCoruscantUnderworldEncounterDepth(unittest.TestCase):
    def setUp(self):
        self.rep, self.region = _region()
        self.by_id = {e.id: e for e in self.region.encounter_pool.entries}
        self.new = {i: self.by_id[i] for i in NEW_IDS if i in self.by_id}

    def test_all_new_entries_present(self):
        missing = sorted(NEW_IDS - set(self.by_id))
        self.assertEqual(missing, [], "new encounter ids missing from the pool: %s" % missing)
        self.assertEqual(len(self.new), 11, "expected exactly 11 new entries")

    def test_region_loads_without_warnings(self):
        # A dropped terrain ref, dup id, or bad band would land here.
        warnings = list(getattr(self.rep, "warnings", []) or [])
        self.assertEqual(warnings, [], "loader warnings for coruscant_underworld: %s" % warnings)

    def test_types_and_terrains_resolve(self):
        defined_terrains = set(getattr(self.region, "terrains", {}) or {})
        self.assertTrue(defined_terrains, "region terrains did not load")
        for i, e in self.new.items():
            self.assertIn(e.type, ALLOWED_TYPES, "%s bad type %r" % (i, e.type))
            for t in (e.terrains or []):
                self.assertIn(t, defined_terrains,
                              "%s references undefined terrain %r" % (i, t))
            self.assertTrue(str(e.narrative or "").strip(), "%s has empty narrative" % i)

    def test_deep_entries_are_band_gated(self):
        for i in DEEP_BAND_GATED:
            e = self.new[i]
            self.assertEqual(e.terrains, ["bottom_dark"],
                             "%s should be bottom_dark only" % i)
            self.assertGreaterEqual(e.min_band, 3,
                                    "%s must be min_band>=3 (deep-only) like maze_ambush" % i)
            self.assertGreaterEqual(e.min_distance_from_edge, 4,
                                    "%s must sit deep (min_distance_from_edge>=4)" % i)

    def test_phantom_free(self):
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)
        for i, e in self.new.items():
            payload = e.payload or {}
            tmpl = payload.get("npc_template")
            if tmpl:
                creature = CL.get_creature(tmpl)
                self.assertIsNotNone(creature, "%s npc_template %r does not resolve" % (i, tmpl))
                atk = CL.resolve_natural_attack(creature)
                self.assertTrue(str(atk.get("damage") or "").strip(),
                                "%s creature %r has no natural-attack damage" % (i, tmpl))
            table = payload.get("salvage_table")
            if table:
                self.assertIn(table, ESTABLISHED_SALVAGE,
                              "%s salvage_table %r is not an established producer" % (i, table))

    def test_new_narratives_are_era_clean(self):
        offenders = []
        for i, e in self.new.items():
            text = str(e.narrative or "").lower()
            for pat in FORBIDDEN:
                if re.search(pat, text):
                    offenders.append("%s :: %s" % (i, pat))
        self.assertEqual(offenders, [], "off-era tokens in new narratives: %s" % offenders)


if __name__ == "__main__":
    unittest.main()
