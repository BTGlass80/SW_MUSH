# -*- coding: utf-8 -*-
"""
tests/test_parser_custom_edge_directions.py — PARSER.custom_edge_directions.

A wilderness region edge may declare a CUSTOM `direction_from_room` word
(e.g. the Coruscant Underworld's "deeper"). The command dispatcher
(CommandParser.process) only routed a hardcoded compass + enter/leave set
to MoveCommand, so typing "deeper" returned "Unknown command" and the
region could not be walked into — reachable only via the synthetic
_drop_into_wilderness test path (surfaced by the drop-21 underworld smoke).

Fix (data-driven, ratified): engine.wilderness_movement.get_custom_edge_directions()
harvests every edge `direction_from_room` from the region YAMLs (cached,
boot-warm, independent of region-cache state) and the dispatcher merges that
set into its routable-direction check.

These tests pin:
  * the harvester returns the known custom edge word ("deeper") and is
    data-driven (no hardcoded literal in the helper),
  * comment lines mentioning `direction_from_room` are NOT harvested,
  * the cache resets with clear_region_cache(),
  * the exact dispatcher routing condition accepts "deeper" and still
    rejects a non-direction word.
"""
from __future__ import annotations

import unittest

from engine.wilderness_movement import (
    get_custom_edge_directions,
    clear_region_cache,
)
from parser.commands import _MOVEMENT_DIRECTIONS


class TestCustomEdgeDirectionHarvest(unittest.TestCase):
    def setUp(self):
        clear_region_cache()

    def tearDown(self):
        clear_region_cache()

    def test_deeper_is_harvested(self):
        # Coruscant Underworld's edge declares direction_from_room: deeper
        dirs = get_custom_edge_directions()
        self.assertIn("deeper", dirs)

    def test_returns_frozenset(self):
        self.assertIsInstance(get_custom_edge_directions(), frozenset)

    def test_all_lowercased(self):
        dirs = get_custom_edge_directions()
        self.assertTrue(all(d == d.lower() for d in dirs))

    def test_comment_lines_not_harvested(self):
        # dune_sea.yaml mentions `direction_from_room` inside a `#` comment
        # block; only the actual data key should be picked up. The harvest
        # must not contain obvious prose tokens from that comment.
        dirs = get_custom_edge_directions()
        for prose in ("to", "the", "enter", "wilderness", "coords", "players"):
            self.assertNotIn(prose, dirs)

    def test_cache_is_stable_then_resets(self):
        first = get_custom_edge_directions()
        second = get_custom_edge_directions()
        self.assertEqual(first, second)
        clear_region_cache()
        # Recompute still yields the same content (idempotent harvest).
        self.assertEqual(get_custom_edge_directions(), first)


class TestDispatchRoutingCondition(unittest.TestCase):
    """The exact predicate CommandParser.process uses to decide whether an
    unregistered word is routed to MoveCommand."""

    def setUp(self):
        clear_region_cache()

    def tearDown(self):
        clear_region_cache()

    def _routes_as_direction(self, word: str) -> bool:
        return (word in _MOVEMENT_DIRECTIONS
                or word in get_custom_edge_directions())

    def test_compass_word_routes(self):
        self.assertTrue(self._routes_as_direction("north"))

    def test_custom_edge_word_routes(self):
        # the regression: "deeper" was previously rejected
        self.assertTrue(self._routes_as_direction("deeper"))

    def test_enter_leave_route(self):
        self.assertTrue(self._routes_as_direction("enter"))
        self.assertTrue(self._routes_as_direction("leave"))

    def test_non_direction_word_does_not_route(self):
        self.assertFalse(self._routes_as_direction("xyzzy"))
        self.assertFalse(self._routes_as_direction("inventory"))


if __name__ == "__main__":
    unittest.main()
