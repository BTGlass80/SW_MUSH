"""QA L7: space zone anchor rooms — 5 empty space zones now have at least one room.

QA finding L7 (2026-06-16): 5 zone definitions in zones.yaml had no rooms assigned,
generating 'has no rooms' warnings from the world validator:
  space_tatooine / space_coruscant / space_kuat / space_kamino / space_geonosis

Fix: 5 minimal tutorial-zone anchor rooms added to tutorials/rooms.yaml (IDs 624-628),
one per zone. space_nar_shaddaa already had a room (smuggler_ship_cockpit, id 618).

Tests confirm:
  1. Each anchor room exists in the loaded world bundle.
  2. Each room is assigned to its correct space zone.
  3. The world validator emits no "has no rooms" warning for these 5 zones.
"""
from __future__ import annotations

import unittest

SPACE_ZONES = [
    "space_tatooine",
    "space_coruscant",
    "space_kuat",
    "space_kamino",
    "space_geonosis",
]

ANCHOR_SLUGS = {
    "space_tatooine": "tatooine_system_ship_approach",
    "space_coruscant": "coruscant_system_ship_approach",
    "space_kuat": "kuat_system_ship_approach",
    "space_kamino": "kamino_system_ship_approach",
    "space_geonosis": "geonosis_system_ship_approach",
}


def _bundle():
    from engine.world_loader import load_world_dry_run
    return load_world_dry_run("clone_wars")


class TestSpaceZoneAnchorRooms(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.b = _bundle()
        cls.rooms_by_slug = {r.slug: r for r in cls.b.rooms.values()}

    def test_anchor_slugs_exist(self):
        for zone, slug in ANCHOR_SLUGS.items():
            self.assertIn(slug, self.rooms_by_slug,
                          f"Anchor room {slug!r} for zone {zone!r} not found in world")

    def test_anchor_rooms_assigned_to_correct_zone(self):
        for zone, slug in ANCHOR_SLUGS.items():
            room = self.rooms_by_slug.get(slug)
            if room is None:
                continue
            self.assertEqual(room.zone, zone,
                             f"{slug!r} has zone={room.zone!r}, expected {zone!r}")

    def test_all_five_space_zones_have_rooms(self):
        rooms_by_zone: dict[str, list] = {}
        for r in self.b.rooms.values():
            rooms_by_zone.setdefault(r.zone, []).append(r)
        for zone in SPACE_ZONES:
            count = len(rooms_by_zone.get(zone, []))
            self.assertGreater(count, 0,
                               f"Zone {zone!r} still has no rooms in the world bundle")

    def test_no_has_no_rooms_warning_for_space_zones(self):
        warnings = self.b.report.warnings
        for zone in SPACE_ZONES:
            offending = [w for w in warnings if zone in w and "no rooms" in w]
            self.assertEqual(offending, [],
                             f"Still got 'no rooms' warnings for {zone!r}: {offending}")

    def test_anchor_room_tutorial_zone_property(self):
        for slug in ANCHOR_SLUGS.values():
            room = self.rooms_by_slug.get(slug)
            if room is None:
                continue
            props = (room.raw.get("properties") or {})
            self.assertTrue(props.get("tutorial_zone"),
                            f"{slug!r} missing tutorial_zone=true property")

    def test_space_nar_shaddaa_still_has_rooms(self):
        rooms = [r for r in self.b.rooms.values() if r.zone == "space_nar_shaddaa"]
        self.assertGreater(len(rooms), 0,
                           "space_nar_shaddaa lost its room (regression guard)")

    def test_anchor_room_ids_are_unique(self):
        expected_ids = {624, 625, 626, 627, 628}
        actual_ids = {rid for rid in self.b.rooms if rid in expected_ids}
        self.assertEqual(actual_ids, expected_ids,
                         f"Expected room IDs {expected_ids}, found {actual_ids}")


if __name__ == "__main__":
    unittest.main()
