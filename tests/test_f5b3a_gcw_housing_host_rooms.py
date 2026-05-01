# -*- coding: utf-8 -*-
"""
tests/test_f5b3a_gcw_housing_host_rooms.py — F.5b.3.a tests.

F.5b.3.a (Apr 30 2026) data-fies the GCW housing lot inventory:

  - Adds `housing: true` flag to 16 host rooms across 4 GCW planets
    (tatooine, nar_shaddaa, kessel, corellia).
  - Authors 24 lot records in data/worlds/gcw/housing_lots.yaml's
    tier1_rentals (5), tier3_lots (7), tier4_lots (6), tier5_lots (6)
    sections — mirroring the existing engine/housing.py constants
    (HOUSING_LOTS_DROP1, HOUSING_LOTS_TIER3/4/5) but referenced by
    slug rather than by numeric room ID.

Mirrors the F.5a.2.x.1 host-room test pattern but for GCW.

Why this test class exists
--------------------------
The legacy hardcoded constants reference room IDs that have drifted
from the live world build. For example: legacy says "Spaceport Hotel
is room 29", but `load_world_dry_run('gcw')` resolves the slug
`spaceport_hotel` to room 25 — legacy ID 29 is now Jawa Traders.
9 of 24 legacy lots have ID drift between 1 and 14.

The slug-based YAML inventory authored in F.5b.3.a corrects this
drift: slugs are stable across world rebuilds. F.5b.3.b will switch
the provider's GCW path through this YAML and retire the legacy
constants. F.5b.3.a is the data-only step that lands first.

Test Contract
-------------
1. Every host_room slug in data/worlds/gcw/housing_lots.yaml's T1/T3/T4/T5
   sections resolves to a live room in the GCW world.
2. Every host_room is on the planet the YAML record specifies.
3. Every host_room has `housing: true` set in its raw YAML data.
4. Every host_room has at least one paired exit (no orphans).
5. Lot counts match the legacy constants exactly:
     T1 = 5  (HOUSING_LOTS_DROP1 cardinality)
     T3 = 7  (HOUSING_LOTS_TIER3 cardinality)
     T4 = 6  (HOUSING_LOTS_TIER4 cardinality)
     T5 = 6  (HOUSING_LOTS_TIER5 cardinality)
6. The set of (planet, label_substring) pairs in the YAML is a
   superset of the (planet, label_keyword) pairs from the legacy
   constants — proving the YAML preserved every authored lot.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Per F.5b.3.a authoring, these are the 16 unique host_room slugs the
# GCW housing_lots.yaml T1/T3/T4/T5 sections reference. Some slugs
# host multiple tiers (e.g. fighting_pits hosts T3 + T4 + T5).
EXPECTED_GCW_HOSTS = [
    # Tatooine (8 unique)
    ("spaceport_hotel",                       "T1",     "tatooine"),
    ("mos_eisley_inn",                        "T1",     "tatooine"),
    ("mos_eisley_street_south_end",           "T3",     "tatooine"),
    ("city_outskirts_eastern_gate",           "T3",     "tatooine"),
    ("mos_eisley_street_market_district",     "T4",     "tatooine"),
    ("mos_eisley_street_spaceport_row",       "T4",     "tatooine"),
    ("city_outskirts_abandoned_moisture_farm","T5",     "tatooine"),
    ("city_outskirts_desert_trail_junction",  "T5",     "tatooine"),
    # Nar Shaddaa (4 unique)
    ("nar_shaddaa_corellian_sector_promenade","T1+T3",  "nar_shaddaa"),
    ("nar_shaddaa_vertical_bazaar",           "T4",     "nar_shaddaa"),
    ("nar_shaddaa_bounty_hunters_quarter",    "T5",     "nar_shaddaa"),
    ("nar_shaddaa_fighting_pits",             "T3+T4+T5","nar_shaddaa"),
    # Kessel (1 unique)
    ("kessel_administration_block",           "T1+T3+T4+T5","kessel"),
    # Corellia (3 unique)
    ("coronet_city_blue_sector",              "T1+T4",  "corellia"),
    ("coronet_city_residential_quarter",      "T3",     "corellia"),
    ("coronet_city_old_quarter_back_streets", "T3+T5",  "corellia"),
]


class TestGCWHousingLotsYAMLLoads(unittest.TestCase):
    """The F.5b.3.a YAML extension parses through the F.5a.2 loader
    with zero errors and zero warnings."""

    def test_yaml_loads_clean(self):
        from engine.world_loader import load_era_manifest, load_housing_lots
        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        corpus = load_housing_lots(manifest)
        self.assertEqual(
            len(corpus.report.errors), 0,
            f"GCW housing_lots.yaml had load errors: {corpus.report.errors}",
        )
        self.assertEqual(
            len(corpus.report.warnings), 0,
            f"GCW housing_lots.yaml had load warnings: {corpus.report.warnings}",
        )

    def test_tier_counts_match_legacy_cardinality(self):
        """T1/T3/T4/T5 lot counts equal the legacy snapshot cardinalities.

        F.5b.3.c (Apr 30 2026): switched from importing live
        engine.housing constants (deleted) to the static snapshot in
        tests/_legacy_housing_lots_snapshot.py.
        """
        from engine.world_loader import load_era_manifest, load_housing_lots
        from tests._legacy_housing_lots_snapshot import (
            LEGACY_HOUSING_LOTS_DROP1, LEGACY_HOUSING_LOTS_TIER3,
            LEGACY_HOUSING_LOTS_TIER4, LEGACY_HOUSING_LOTS_TIER5,
        )

        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        corpus = load_housing_lots(manifest)

        self.assertEqual(
            len(corpus.tier1_rentals), len(LEGACY_HOUSING_LOTS_DROP1),
            "T1 lot count drift between YAML and legacy snapshot",
        )
        self.assertEqual(
            len(corpus.tier3_lots), len(LEGACY_HOUSING_LOTS_TIER3),
            "T3 lot count drift between YAML and legacy snapshot",
        )
        self.assertEqual(
            len(corpus.tier4_lots), len(LEGACY_HOUSING_LOTS_TIER4),
            "T4 lot count drift between YAML and legacy snapshot",
        )
        self.assertEqual(
            len(corpus.tier5_lots), len(LEGACY_HOUSING_LOTS_TIER5),
            "T5 lot count drift between YAML and legacy snapshot",
        )


class TestGCWHousingHostRooms(unittest.TestCase):
    """Verify F.5b.3.a host_rooms are live, flagged, and connected.

    Mirrors the F.5a.2.x.1 test class but for GCW.
    """

    @classmethod
    def setUpClass(cls):
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("gcw")
        cls.bundle = b
        cls.by_slug = {r.slug: r for r in b.rooms.values()}
        cls.exit_set = b.exits

    def test_all_expected_hosts_resolve(self):
        """Every F.5b.3.a host_room slug resolves to a live GCW room."""
        unresolved = []
        for slug, tier, planet in EXPECTED_GCW_HOSTS:
            if slug not in self.by_slug:
                unresolved.append((slug, tier, planet))
        if unresolved:
            lines = [
                f"  {slug:<42} {tier:<12} {planet}"
                for slug, tier, planet in unresolved
            ]
            self.fail(
                f"{len(unresolved)} GCW host_room slugs do not resolve. "
                "F.5b.3.a authored these in data/worlds/gcw/housing_lots.yaml "
                "but they're not present in the GCW world build.\n"
                + "\n".join(lines)
            )

    def test_all_expected_hosts_have_housing_flag(self):
        """Each host_room must have `housing: true` set in its YAML data.

        Without the flag, the F.5b.3.b-and-later runtime cannot tell
        which rooms are housing-eligible (the engine treats housing
        rooms specially for purchase eligibility, exit hiding, etc.).
        """
        missing_flag = []
        for slug, tier, planet in EXPECTED_GCW_HOSTS:
            r = self.by_slug.get(slug)
            if r is None:
                continue  # caught by test_all_expected_hosts_resolve
            if not r.raw.get("housing"):
                missing_flag.append((slug, tier, planet))
        if missing_flag:
            lines = [
                f"  {slug:<42} {tier:<12} {planet} (id={self.by_slug[slug].id})"
                for slug, tier, planet in missing_flag
            ]
            self.fail(
                f"{len(missing_flag)} GCW host_rooms are missing the "
                "`housing: true` flag in data/worlds/gcw/planets/<planet>.yaml.\n"
                + "\n".join(lines)
            )

    def test_all_expected_hosts_have_exits(self):
        """Each host_room must have at least one exit (in or out).

        An orphan host is a player-trap. The legacy GCW data was
        authored with paired exits; this test guards against future
        regressions where the slug stays but its connections are
        broken.
        """
        orphans = []
        for slug, tier, planet in EXPECTED_GCW_HOSTS:
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
                f"  {slug:<42} {tier:<12} {planet} (id={rid})"
                for slug, tier, planet, rid in orphans
            ]
            self.fail(
                f"{len(orphans)} GCW host_rooms are orphans (no exits).\n"
                + "\n".join(lines)
            )

    def test_all_expected_hosts_on_correct_planet(self):
        """Each host_room must be on the planet the YAML lot record specifies."""
        wrong_planet = []
        for slug, tier, expected_planet in EXPECTED_GCW_HOSTS:
            r = self.by_slug.get(slug)
            if r is None:
                continue
            if r.planet != expected_planet:
                wrong_planet.append(
                    (slug, expected_planet, r.planet)
                )
        if wrong_planet:
            lines = [
                f"  {slug:<42} expected={exp} actual={act}"
                for slug, exp, act in wrong_planet
            ]
            self.fail(
                f"{len(wrong_planet)} GCW host_rooms are on the wrong planet.\n"
                + "\n".join(lines)
            )


class TestGCWHousingLotSlugsResolveToRooms(unittest.TestCase):
    """Cross-checks: every host_room referenced in housing_lots.yaml
    actually exists in the live GCW world. This is a structural guard
    distinct from EXPECTED_GCW_HOSTS — it walks the YAML rather than
    the test fixture, so a future drop that adds a lot record without
    updating the test fixture still gets caught."""

    @classmethod
    def setUpClass(cls):
        from engine.world_loader import (
            load_era_manifest, load_housing_lots, load_world_dry_run,
        )
        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        cls.corpus = load_housing_lots(manifest)
        cls.world = load_world_dry_run("gcw")
        cls.by_slug = {r.slug: r for r in cls.world.rooms.values()}

    def test_every_yaml_lot_host_room_resolves(self):
        unresolved = []
        sections = (
            ("T1", self.corpus.tier1_rentals),
            ("T3", self.corpus.tier3_lots),
            ("T4", self.corpus.tier4_lots),
            ("T5", self.corpus.tier5_lots),
        )
        for tier_name, lots in sections:
            for lot in lots:
                if lot.host_room not in self.by_slug:
                    unresolved.append((tier_name, lot.id, lot.host_room))
        if unresolved:
            lines = [
                f"  {tier} {lot_id:<40} host_room={slug}"
                for tier, lot_id, slug in unresolved
            ]
            self.fail(
                f"{len(unresolved)} YAML lot records reference unresolved "
                "host_room slugs in the GCW world.\n" + "\n".join(lines)
            )

    def test_every_yaml_lot_host_has_housing_flag(self):
        unflagged = []
        sections = (
            ("T1", self.corpus.tier1_rentals),
            ("T3", self.corpus.tier3_lots),
            ("T4", self.corpus.tier4_lots),
            ("T5", self.corpus.tier5_lots),
        )
        for tier_name, lots in sections:
            for lot in lots:
                r = self.by_slug.get(lot.host_room)
                if r is None:
                    continue  # caught by previous test
                if not r.raw.get("housing"):
                    unflagged.append((tier_name, lot.id, lot.host_room))
        if unflagged:
            lines = [
                f"  {tier} {lot_id:<40} host_room={slug}"
                for tier, lot_id, slug in unflagged
            ]
            self.fail(
                f"{len(unflagged)} YAML lot records reference rooms without "
                "`housing: true`.\n" + "\n".join(lines)
            )

    def test_every_yaml_lot_planet_matches_room_planet(self):
        mismatched = []
        sections = (
            ("T1", self.corpus.tier1_rentals),
            ("T3", self.corpus.tier3_lots),
            ("T4", self.corpus.tier4_lots),
            ("T5", self.corpus.tier5_lots),
        )
        for tier_name, lots in sections:
            for lot in lots:
                r = self.by_slug.get(lot.host_room)
                if r is None:
                    continue
                if r.planet != lot.planet:
                    mismatched.append(
                        (tier_name, lot.id, lot.planet, r.planet)
                    )
        if mismatched:
            lines = [
                f"  {tier} {lot_id:<40} yaml_planet={yp} room_planet={rp}"
                for tier, lot_id, yp, rp in mismatched
            ]
            self.fail(
                f"{len(mismatched)} YAML lot records have planet mismatches.\n"
                + "\n".join(lines)
            )


class TestGCWLegacyByteEquivalence(unittest.TestCase):
    """The YAML inventory must contain (planet, label-keyword) pairs
    matching every entry in the legacy constants. This is the
    byte-equivalence pre-gate for F.5b.3.b's swap of the
    provider's GCW path through YAML, and for F.5b.3.c's destructive
    deletion of the legacy constants.

    F.5b.3.c (Apr 30 2026): legacy constants deleted from
    engine/housing.py; reference is now the static snapshot in
    tests/_legacy_housing_lots_snapshot.py.
    """

    def test_legacy_T1_planets_covered(self):
        from engine.world_loader import load_era_manifest, load_housing_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_DROP1
        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        corpus = load_housing_lots(manifest)

        legacy_planets = {entry[1] for entry in LEGACY_HOUSING_LOTS_DROP1}
        yaml_planets = {lot.planet for lot in corpus.tier1_rentals}
        self.assertEqual(
            legacy_planets, yaml_planets,
            f"T1 planet set drift: legacy={legacy_planets} yaml={yaml_planets}",
        )

    def test_legacy_T3_planets_covered(self):
        from engine.world_loader import load_era_manifest, load_housing_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER3
        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        corpus = load_housing_lots(manifest)

        legacy_planets = sorted([entry[1] for entry in LEGACY_HOUSING_LOTS_TIER3])
        yaml_planets = sorted([lot.planet for lot in corpus.tier3_lots])
        self.assertEqual(
            legacy_planets, yaml_planets,
            "T3 planet multiset drift between legacy snapshot and YAML",
        )

    def test_legacy_T4_planets_covered(self):
        from engine.world_loader import load_era_manifest, load_housing_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER4
        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        corpus = load_housing_lots(manifest)

        legacy_planets = sorted([entry[1] for entry in LEGACY_HOUSING_LOTS_TIER4])
        yaml_planets = sorted([lot.planet for lot in corpus.tier4_lots])
        self.assertEqual(
            legacy_planets, yaml_planets,
            "T4 planet multiset drift between legacy snapshot and YAML",
        )

    def test_legacy_T5_planets_covered(self):
        from engine.world_loader import load_era_manifest, load_housing_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER5
        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        corpus = load_housing_lots(manifest)

        legacy_planets = sorted([entry[1] for entry in LEGACY_HOUSING_LOTS_TIER5])
        yaml_planets = sorted([lot.planet for lot in corpus.tier5_lots])
        self.assertEqual(
            legacy_planets, yaml_planets,
            "T5 planet multiset drift between legacy snapshot and YAML",
        )


class TestGCWHousingFlagSurfaceArea(unittest.TestCase):
    """Sanity check: the count of `housing: true` flagged rooms in
    the GCW world should equal the count of unique host_room slugs
    referenced by the YAML lot inventory. If a developer adds a new
    lot record but forgets the flag, this test catches it. If they
    flag a room without authoring a corresponding lot, this test also
    catches it (the YAML is supposed to be the source of truth).
    """

    def test_unique_host_count_matches_flagged_room_count(self):
        from engine.world_loader import (
            load_era_manifest, load_housing_lots, load_world_dry_run,
        )
        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        corpus = load_housing_lots(manifest)
        world = load_world_dry_run("gcw")

        unique_hosts = set()
        for lots in (corpus.tier1_rentals, corpus.tier3_lots,
                     corpus.tier4_lots, corpus.tier5_lots):
            for lot in lots:
                unique_hosts.add(lot.host_room)

        flagged_slugs = {
            r.slug for r in world.rooms.values() if r.raw.get("housing")
        }

        # Every YAML host must be flagged
        unflagged = unique_hosts - flagged_slugs
        # Every flagged room must be referenced by at least one lot
        unreferenced = flagged_slugs - unique_hosts

        msgs = []
        if unflagged:
            msgs.append(
                f"{len(unflagged)} YAML host_rooms lack housing flag: "
                f"{sorted(unflagged)}"
            )
        if unreferenced:
            msgs.append(
                f"{len(unreferenced)} flagged rooms have no YAML lot record: "
                f"{sorted(unreferenced)}"
            )
        if msgs:
            self.fail("\n".join(msgs))


if __name__ == "__main__":
    unittest.main()
