# -*- coding: utf-8 -*-
"""
tests/test_drop_a_realbug_fixes.py — Drop A (2026-06-06)

Guards three fixes triaged from the 2026-06-05 Windows run (tests_output.log):

  A1  SellCommand: a Vendor-V1 dispatch regression sent EVERY `sell <arg>` to
      the carried-item path. The equipped weapon lives in char['equipment'],
      not inventory['items'], so `sell weapon` found no carried item, reported
      "not carrying", and never sold — dropping the sale, its success line, and
      the city-tax hook (the player-cities Phase-4b invariant). Fix: the generic
      words `weapon`/`equipped` route to the equipped-weapon path; specific
      names still go carried-only (Vendor V1 preserved).
      Behavioral coverage: tests/test_cities_phase4b.py (sell paths) +
      tests/test_vendor_sell_carried.py (carried path). This file pins the
      dispatch contract so the routing can't silently regress again.

  A2  sabacc: `get_world_event_manager().is_active("cantina_brawl")` — but
      WorldEventManager has no `is_active` (only the `active_event_types`
      property). Every sabacc play raised AttributeError (caught + logged), so
      the cantina_brawl double-bet ceiling was silently dead. No existing test
      covered it. Fix: membership against `active_event_types`.

  B1  tests/test_lane_a_phase_b_spawner.py `_run` used
      `asyncio.get_event_loop().run_until_complete()`, which raises on
      Python 3.12+/3.14 ("no current event loop"). Fix: `asyncio.run`.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _read(rel):
    with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


# ── A2: WorldEventManager event-active query (behavioral) ──────────────────

class TestSabaccEventQueryApi(unittest.TestCase):
    def test_world_event_manager_has_active_event_types_not_is_active(self):
        from engine.world_events import WorldEventManager
        mgr = WorldEventManager()
        # The property the fixed code calls exists...
        self.assertTrue(hasattr(mgr, "active_event_types"))
        # ...and the membership query the sabacc ceiling does runs cleanly on a
        # fresh (eventless) manager — no AttributeError, returns False.
        self.assertNotIn("cantina_brawl", mgr.active_event_types)
        # The broken method is gone (its presence would mean a silent revert).
        self.assertFalse(hasattr(mgr, "is_active"),
                         "WorldEventManager.is_active reappeared — the sabacc "
                         "call site assumed it; it never existed.")

    def test_sabacc_no_longer_calls_is_active(self):
        src = _read("parser/sabacc_commands.py")
        self.assertNotIn(".is_active(", src,
                         "sabacc still calls the nonexistent is_active()")
        self.assertIn("active_event_types", src,
                      "sabacc cantina_brawl check should use active_event_types")


# ── A1: SellCommand generic-word dispatch (contract pin) ───────────────────

class TestSellCommandGenericWordRouting(unittest.TestCase):
    def test_dispatch_routes_generic_weapon_to_equipped_path(self):
        src = _read("parser/builtin_commands.py")
        # The dispatch must exclude the generic words from the carried-item
        # route, so `sell weapon` / `sell equipped` reach the equipped path.
        self.assertIn('if arg_lower not in ("weapon", "equipped", "equipped weapon"):',
                      src,
                      "SellCommand dispatch lost the generic-word guard — "
                      "`sell weapon` will be swallowed by the carried-item path "
                      "again (no sale, no city tax).")
        # And the carried path is still the route for a specific name.
        self.assertIn("return await self._sell_carried_item(ctx, ctx.args.strip())",
                      src)


# ── B1: spawner test uses asyncio.run (Py 3.14-safe) ───────────────────────

class TestSpawnerHarnessEventLoop(unittest.TestCase):
    def test_spawner_run_helper_uses_asyncio_run(self):
        src = _read("tests/test_lane_a_phase_b_spawner.py")
        self.assertIn("asyncio.run(coro)", src)
        self.assertNotIn("get_event_loop().run_until_complete", src,
                         "spawner _run reverted to get_event_loop() — raises on "
                         "Python 3.12+/3.14.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
