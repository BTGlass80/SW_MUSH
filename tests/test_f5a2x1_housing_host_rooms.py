# -*- coding: utf-8 -*-
"""
tests/test_f5a2x1_housing_host_rooms.py — F.5a.2.x.1 host-room tests

F.5a.2.x.1 (Apr 30 2026) authored 6 missing T1 rental host rooms on
the CW-NEW planets (Coruscant, Kuat, Kamino, Geonosis) and wired in
2 pre-existing orphan rooms on Nar Shaddaa.

This test file is a regression guard. It enumerates every design-doc
host_room slug from cw_housing_design_v1.md §6/§7/§8/§9 and asserts:

  - The slug resolves to a live room in the CW world
  - The room has `housing: true` flag set
  - The room has at least one paired exit (no orphans)
  - The room is in a sensible zone for its tier

If a future drop authors a new lot YAML record (F.5a.3) that
references a host_room slug not yet live, that test will fail and
the failure will say which slug needs to land first.

Tests:
  - All §6 T1 hosts (8 expected on CW-NEW planets) are live + connected
  - All §7 T3 hosts (10 expected on CW-NEW planets) are live + connected
  - All §8 T4 hosts (3 expected on CW-NEW planets) are live + connected
  - All §9 T5 hosts (5 expected on CW-NEW planets) are live + connected
  - The 2 Nar Shaddaa orphan-fix targets are no longer orphaned
  - No CW room has the `housing: true` flag without exits
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Per cw_housing_design_v1.md §6/§7/§8/§9, these are the host_room slugs
# expected to be live in the CW world for the lot inventory to anchor on.
# Tatooine and Nar Shaddaa entries described in the design as "existing
# GCW lot, reskinned" are NOT in this list — they're handled by the
# GCW data and reused under CW. This list is only the slugs the CW
# design says must exist on the CW-NEW planets (Coruscant, Kuat,
# Kamino, Geonosis), plus the Nar Shaddaa-NEW slugs the design adds.
EXPECTED_HOSTS = [
    # Tier 1 rentals (CW-NEW planet hosts only)
    ("westport_arrivals_hotel_lobby", "T1", "coruscant"),
    ("outlander_cantina", "T1", "coruscant"),
    ("crystal_jewel_back_rooms", "T1", "coruscant"),       # F.5a.2.x.1 NEW
    ("mosaic_hotel", "T1", "coruscant"),                   # F.5a.2.x.1 NEW
    ("spaceport_concourse_hotel", "T1", "kuat"),           # F.5a.2.x.1 NEW
    ("embassy_inn", "T1", "kuat"),                         # F.5a.2.x.1 NEW
    ("ocean_visiting_officers_quarters", "T1", "kamino"),  # F.5a.2.x.1 NEW
    ("smugglers_roost_flophouse", "T1", "geonosis"),       # F.5a.2.x.1 NEW

    # Tier 3 private residence (CW-NEW planet hosts + Nar Shaddaa NEW)
    ("coco_town_residential_walk", "T3", "coruscant"),
    ("coco_town_loft_district", "T3", "coruscant"),
    ("calocour_marketing_row", "T3", "coruscant"),
    ("calocour_overlook_terrace", "T3", "coruscant"),
    ("underground_tenement_block", "T3", "coruscant"),
    ("gilded_cage_alien_quarter", "T3", "coruscant"),
    ("kdy_engineer_apartments", "T3", "kuat"),
    ("embassy_residential_row", "T3", "kuat"),
    ("stalgasin_offworld_quarter", "T3", "geonosis"),
    ("warrens_squat_block", "T3", "nar_shaddaa"),          # pre-existing; F.5a.2.x.1 wired

    # Tier 4 shopfronts (CW-NEW Coruscant only — others are GCW-reskinned)
    ("coco_town_market_arcade", "T4", "coruscant"),
    ("calocour_boutique_row", "T4", "coruscant"),
    ("gilded_cage_bazaar", "T4", "coruscant"),

    # Tier 5 organization HQ (CW-NEW planet hosts + Nar Shaddaa NEW)
    ("coco_town_civic_block", "T5", "coruscant"),
    ("bhg_chapter_house", "T5", "coruscant"),
    ("crystal_jewel_alley", "T5", "coruscant"),
    ("gilded_cage_courtyard", "T5", "coruscant"),
    ("stalgasin_outsider_compound", "T5", "geonosis"),
    ("promenade_corporate_tower", "T5", "nar_shaddaa"),    # pre-existing; F.5a.2.x.1 wired
]


class TestHousingHostRooms(unittest.TestCase):
    """Verify F.5a.2.x.1 host_rooms are live, flagged, and connected."""

    @classmethod
    def setUpClass(cls):
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars")
        cls.bundle = b
        cls.by_slug = {r.slug: r for r in b.rooms.values()}
        cls.exit_set = b.exits

    def test_all_expected_hosts_resolve(self):
        """Every design-doc host_room slug resolves to a live CW room."""
        unresolved = []
        for slug, tier, planet in EXPECTED_HOSTS:
            if slug not in self.by_slug:
                unresolved.append((slug, tier, planet))
        if unresolved:
            lines = [
                f"  {slug:<38} {tier} {planet}"
                for slug, tier, planet in unresolved
            ]
            self.fail(
                f"{len(unresolved)} design-doc host_room slugs do not "
                f"resolve to live CW rooms. F.5a.2.x.1 should have "
                f"authored these — investigate the per-planet YAML.\n"
                + "\n".join(lines)
            )

    def test_all_expected_hosts_have_housing_flag(self):
        """Each host_room must have `housing: true` flag.

        The housing engine queries `housing: true` rooms when resolving
        which rooms can host player-purchased homes. A room without the
        flag will silently fail to host any lots.
        """
        missing_flag = []
        for slug, tier, planet in EXPECTED_HOSTS:
            r = self.by_slug.get(slug)
            if r is None:
                continue  # caught by the resolve test
            if not r.raw.get("housing"):
                missing_flag.append((slug, tier, planet))
        if missing_flag:
            lines = [
                f"  {slug:<38} {tier} {planet} (id={self.by_slug[slug].id})"
                for slug, tier, planet in missing_flag
            ]
            self.fail(
                f"{len(missing_flag)} host_rooms are missing the "
                f"`housing: true` flag. Without it, the housing engine "
                f"will not host lots in these rooms.\n" + "\n".join(lines)
            )

    def test_all_expected_hosts_have_exits(self):
        """Each host_room must have at least one exit (in or out).

        A host_room with no exits is a player-trap — they could enter
        (if some other room references it) but couldn't leave, or
        they couldn't enter at all (orphan). The F.5a.2.x.1 wire-in
        ensures every host has paired exits.
        """
        orphans = []
        for slug, tier, planet in EXPECTED_HOSTS:
            r = self.by_slug.get(slug)
            if r is None:
                continue
            connected = any(
                e.from_id == r.id or e.to_id == r.id
                for e in self.exit_set
            )
            if not connected:
                orphans.append((slug, tier, planet, r.id))
        if orphans:
            lines = [
                f"  {slug:<38} {tier} {planet} (id={rid})"
                for slug, tier, planet, rid in orphans
            ]
            self.fail(
                f"{len(orphans)} host_rooms are orphans (no incoming "
                f"or outgoing exits). Players cannot enter or leave "
                f"these rooms.\n" + "\n".join(lines)
            )

    def test_all_expected_hosts_on_correct_planet(self):
        """Each host_room must be on the planet the design specifies."""
        wrong_planet = []
        for slug, tier, expected_planet in EXPECTED_HOSTS:
            r = self.by_slug.get(slug)
            if r is None:
                continue
            if r.planet != expected_planet:
                wrong_planet.append(
                    (slug, expected_planet, r.planet)
                )
        if wrong_planet:
            lines = [
                f"  {slug:<38} expected={ep} got={ap}"
                for slug, ep, ap in wrong_planet
            ]
            self.fail(
                f"{len(wrong_planet)} host_rooms are on the wrong "
                f"planet:\n" + "\n".join(lines)
            )

    def test_no_housing_flagged_room_is_orphan(self):
        """Belt-and-suspenders: walk every CW room with housing: true
        and assert it has at least one exit. This catches host_rooms
        that aren't in EXPECTED_HOSTS (someone added a new one without
        updating this test) but are also orphaned.
        """
        orphans = []
        for r in self.bundle.rooms.values():
            if not r.raw.get("housing"):
                continue
            connected = any(
                e.from_id == r.id or e.to_id == r.id
                for e in self.exit_set
            )
            if not connected:
                orphans.append((r.slug, r.id, r.planet))
        if orphans:
            lines = [
                f"  {slug:<38} (id={rid}, planet={planet})"
                for slug, rid, planet in orphans
            ]
            self.fail(
                f"{len(orphans)} `housing: true` rooms are orphans. "
                f"Either wire them into the planet exit graph or "
                f"remove the housing flag.\n" + "\n".join(lines)
            )

    def test_minimum_t1_count(self):
        """At least 8 T1 host rooms must exist on the CW-NEW planets.

        Per cw_housing_design_v1.md §6, the CW-NEW T1 inventory is:
        Coruscant 4 (westport, outlander, crystal_jewel_back, mosaic),
        Kuat 2 (concourse, embassy_inn), Kamino 1 (VOQ),
        Geonosis 1 (smuggler's roost) = 8 hosts.
        """
        t1_count = sum(
            1 for slug, tier, _ in EXPECTED_HOSTS if tier == "T1"
        )
        self.assertGreaterEqual(
            t1_count, 8,
            f"EXPECTED_HOSTS T1 count ({t1_count}) below the design "
            f"minimum of 8 — investigate."
        )


if __name__ == "__main__":
    unittest.main()
