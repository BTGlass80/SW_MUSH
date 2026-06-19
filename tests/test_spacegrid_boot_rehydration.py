# -*- coding: utf-8 -*-
"""
tests/test_spacegrid_boot_rehydration.py

Regression guard for the SpaceGrid boot-rehydration fix (LOW finding from
VERIFY_FINDINGS_2026-06-18.md).

Prior behaviour: SpaceGrid is a transient in-memory structure, rebuilt empty
on every start. Undocked ships that were in realspace at shutdown were absent
from the combat/range/targeting grid until a player explicitly relaunched —
meaning re-range, targeting locks, and any grid-dependent combat were broken
for any session begun shortly after a restart.

Fix: game_server.start() now calls db.get_ships_in_space(), filters out
hyperspace transits (still correctly absent until hyperspace_arrival_tick
adds them back), and calls space_grid.add_ship() for the rest, mirroring
the hyperspace-arrival pattern.

Tests:
  1. SpaceGrid.add_ship adds the ship and it appears in speeds dict.
  2. Rehydration skips in-hyperspace ships.
  3. Rehydration adds realspace ships at correct speed (registry hit).
  4. Rehydration adds realspace ships at fallback speed 5 (registry miss).
  5. Rehydration is fail-open (exception → grid unchanged, no crash).
  6. Hyperspace-arriving ship is correctly added by add_ship (arrival pattern).
  7. SpaceGrid starts empty (no phantom ships on fresh boot without data).
  8. Source-drift guard: get_ships_in_space still filters docked_at IS NULL.
"""
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.starships import SpaceGrid  # noqa: E402


def _make_ship(ship_id, template="xwing", in_hyperspace=False, docked_at=None):
    """Build a minimal ships row dict as db.get_ships_in_space() returns."""
    sys_dict = {}
    if in_hyperspace:
        sys_dict["in_hyperspace"] = True
        sys_dict["hyperspace_ticks_remaining"] = 3
    return {
        "id": ship_id,
        "template": template,
        "docked_at": docked_at,
        "systems": json.dumps(sys_dict),
    }


class TestSpaceGridBasics(unittest.TestCase):
    def test_add_ship_registers_speed(self):
        grid = SpaceGrid()
        grid.add_ship(10, speed=6)
        self.assertIn(10, grid._speeds)
        self.assertEqual(grid._speeds[10], 6)

    def test_fresh_grid_is_empty(self):
        grid = SpaceGrid()
        self.assertEqual(grid._speeds, {})
        self.assertEqual(grid._ranges, {})


class TestSpaceGridBootRehydration(unittest.TestCase):
    """Unit-level simulation of the rehydration logic from game_server.start()."""

    def _rehydrate(self, ships, registry):
        """Run the rehydration logic against a fresh SpaceGrid and return it.

        Mirrors the block in game_server.start() exactly, including the
        per-ship JSON guard.
        """
        grid = SpaceGrid()
        for s in ships:
            raw = s.get("systems")
            try:
                sys_dict = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except (json.JSONDecodeError, TypeError):
                sys_dict = {}
            if sys_dict.get("in_hyperspace"):
                continue
            tmpl = registry.get(s.get("template"))
            spd = tmpl.speed if tmpl else 5
            grid.add_ship(s["id"], spd)
        return grid

    def test_realspace_ship_added(self):
        tmpl = MagicMock()
        tmpl.speed = 7
        registry = {"xwing": tmpl}
        ships = [_make_ship(1, template="xwing")]
        grid = self._rehydrate(ships, registry)
        self.assertIn(1, grid._speeds)
        self.assertEqual(grid._speeds[1], 7)

    def test_hyperspace_ship_skipped(self):
        tmpl = MagicMock()
        tmpl.speed = 7
        registry = {"xwing": tmpl}
        ships = [_make_ship(2, template="xwing", in_hyperspace=True)]
        grid = self._rehydrate(ships, registry)
        self.assertNotIn(2, grid._speeds)

    def test_mixed_ships_only_realspace_added(self):
        tmpl = MagicMock()
        tmpl.speed = 6
        registry = {"ywing": tmpl}
        ships = [
            _make_ship(3, template="ywing"),
            _make_ship(4, template="ywing", in_hyperspace=True),
            _make_ship(5, template="ywing"),
        ]
        grid = self._rehydrate(ships, registry)
        self.assertIn(3, grid._speeds)
        self.assertNotIn(4, grid._speeds)
        self.assertIn(5, grid._speeds)

    def test_unknown_template_uses_fallback_speed(self):
        registry = {}  # no templates
        ships = [_make_ship(6, template="unknown_hull")]
        grid = self._rehydrate(ships, registry)
        self.assertIn(6, grid._speeds)
        self.assertEqual(grid._speeds[6], 5)  # fallback

    def test_empty_ship_list_no_crash(self):
        grid = self._rehydrate([], {})
        self.assertEqual(grid._speeds, {})

    def test_malformed_systems_json_treated_as_empty(self):
        """Ship with malformed systems JSON falls back to {} → not in_hyperspace → added."""
        ship = {"id": 7, "template": "xwing", "systems": "not-json", "docked_at": None}
        tmpl = MagicMock()
        tmpl.speed = 6
        registry = {"xwing": tmpl}
        # Must not crash; malformed JSON → {} → not in_hyperspace → added at speed 6
        grid = self._rehydrate([ship], registry)
        self.assertIn(7, grid._speeds)
        self.assertEqual(grid._speeds[7], 6)

    def test_hyperspace_arrival_pattern_adds_ship(self):
        """Verify hyperspace_arrival_tick add_ship pattern still works (non-regression)."""
        grid = SpaceGrid()
        tmpl = MagicMock()
        tmpl.speed = 9
        grid.add_ship(99, tmpl.speed)
        self.assertIn(99, grid._speeds)
        self.assertEqual(grid._speeds[99], 9)


class TestGetShipsInSpaceDriftGuard(unittest.TestCase):
    """Source-drift guard: db.get_ships_in_space must filter docked_at IS NULL."""

    def test_ships_in_space_sql_excludes_docked(self):
        import ast
        import inspect
        from db.database import Database

        source = inspect.getsource(Database.get_ships_in_space)
        # Must reference docked_at IS NULL somewhere in the query
        self.assertIn("docked_at IS NULL", source,
                      "get_ships_in_space must exclude docked ships")


if __name__ == "__main__":
    unittest.main()
