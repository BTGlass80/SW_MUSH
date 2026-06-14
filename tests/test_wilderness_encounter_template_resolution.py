# -*- coding: utf-8 -*-
"""
tests/test_wilderness_encounter_template_resolution.py

GLOBAL phantom-producer guard for the wilderness encounter -> creature spawn
bridge. Closes the gap that let four templates (dewback, tusken_warrior,
maze_predator, underworld_thug) ship dangling: a hostile/non_hostile encounter
whose ``payload.npc_template`` did not resolve in the creature library fired its
narrative but spawned NOTHING
(engine.wilderness_encounter_runtime.spawn_encounter_creatures returns [] on a
library miss — runtime.py:73-77), so players walked into "Tusken scouts have
seen you" and then... nothing happened.

The pre-existing per-biome contract tests (test_lane_a_creatures_*.py) only
checked their OWN curated id subset (``if tmpl in TATOOINE_IDS`` etc.), so any
template OUTSIDE those subsets slipped through unchecked. This guard checks
EVERY hostile/non_hostile encounter template across ALL live regions, with no
curated allow-list, so a future dangling template fails the suite immediately.

It mirrors the runtime exactly:
  * region discovery via engine.wilderness_loader.load_era_wilderness_regions
    (the SAME entry the world build walks — reads era.yaml content_refs.wilderness,
    so a region added there is auto-covered with no test edit);
  * template resolution via engine.creature_library.get_creature
    (the SAME resolver spawn_encounter_creatures calls).
"""

import os
import sys
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

ERA_DIR = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")

# The encounter types whose runtime path actually spawns a creature from the
# library (mirrors spawn_encounter_creatures' own gate). Other types
# (trader_caravan, weather, ...) never touch npc_template.
SPAWNING_TYPES = ("hostile", "non_hostile")


def _live_regions():
    from engine.wilderness_loader import load_era_wilderness_regions
    reports = load_era_wilderness_regions(ERA_DIR)
    regions = []
    for rep in reports:
        # A region that fails to load is a separate (loader) failure; this guard
        # is about template resolution, so only inspect regions that loaded.
        if getattr(rep, "ok", False) and getattr(rep, "region", None) is not None:
            regions.append(rep.region)
    return regions


def _spawning_encounters():
    """Yield (region_slug, encounter) for every live spawn-capable encounter
    that names a creature template."""
    for region in _live_regions():
        for e in region.encounter_pool.entries:
            if getattr(e, "type", "") not in SPAWNING_TYPES:
                continue
            tmpl = (e.payload or {}).get("npc_template")
            if tmpl:
                yield region.slug, e, tmpl


class TestEncounterTemplateResolution(unittest.TestCase):
    def test_live_regions_actually_load(self):
        """Sanity: the era declares wilderness regions and at least one loads
        (otherwise the resolution guard below would be vacuously green)."""
        regions = _live_regions()
        self.assertTrue(
            regions,
            "no live wilderness regions loaded from era.yaml content_refs.wilderness "
            "— the resolution guard would be vacuous",
        )

    def test_every_spawning_template_resolves(self):
        """The core invariant: every hostile/non_hostile encounter that names a
        template resolves to a real creature via the RUNTIME resolver."""
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)

        dangling = []
        checked = 0
        for slug, e, tmpl in _spawning_encounters():
            checked += 1
            if CL.get_creature(tmpl) is None:
                dangling.append(f"{slug}:{getattr(e, 'id', '?')} -> {tmpl!r}")

        # Anti-vacuous: the live regions DO carry spawning encounters with
        # templates (that's the whole point of this guard). Zero means the pools
        # lost their npc_template refs and this test would otherwise pass empty.
        self.assertGreater(
            checked, 0,
            "no hostile/non_hostile encounter with a npc_template found across "
            "the live regions — the resolution guard is vacuous",
        )
        self.assertEqual(
            dangling, [],
            "dangling npc_template(s) — the encounter fires narrative but "
            "spawn_encounter_creatures returns [] (no creature spawns):\n  "
            + "\n  ".join(dangling),
        )

    def test_resolved_creatures_have_a_usable_attack(self):
        """A spawned creature must come out with a concrete natural-attack damage
        string, or a hostile encounter would spawn a combatant that cannot fight.
        Exercises the same resolve path build_creature_char_sheet uses."""
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)

        broken = []
        checked = 0
        for slug, e, tmpl in _spawning_encounters():
            creature = CL.get_creature(tmpl)
            if creature is None:
                continue  # already reported by the resolution test
            checked += 1
            atk = CL.resolve_natural_attack(creature)
            if not str(atk.get("damage") or "").strip():
                broken.append(f"{slug}:{getattr(e, 'id', '?')} -> {tmpl!r}")

        self.assertGreater(
            checked, 0,
            "no resolvable spawning-encounter creatures found — the usable-attack "
            "guard is vacuous",
        )
        self.assertEqual(
            broken, [],
            "creature template(s) resolve but produce no natural-attack damage:\n  "
            + "\n  ".join(broken),
        )


if __name__ == "__main__":
    unittest.main()
