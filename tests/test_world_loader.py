# -*- coding: utf-8 -*-
"""
tests/test_world_loader.py — F.0 Drop 1 tests

Exercises engine/world_loader.py against:
  1. The actual data/worlds/clone_wars/ content (Tatooine + Nar Shaddaa)
     to prove the loader handles real authored YAML.
  2. Synthetic fixtures written to tmp directories for negative cases
     (malformed YAML, missing files, validation failures).

The validation pass is the heart of Drop 1, so it has the most coverage
here — every error condition in §5.5 of world_data_extraction_design_v1.md
gets a dedicated test.
"""
import os
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers — write a synthetic era directory
# ══════════════════════════════════════════════════════════════════════════════


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")


def _make_minimal_era(root: Path, era: str = "test_era") -> Path:
    """Create a minimal but valid era directory under `root`/`era`."""
    era_dir = root / era
    _write(era_dir / "era.yaml", """
        schema_version: 1
        era:
          code: test_era
          name: "Test Era"
        content_refs:
          zones: zones.yaml
          planets:
            - planets/testworld.yaml
          wilderness: []
    """)
    _write(era_dir / "zones.yaml", """
        zones:
          test_zone:
            name_match: "test"
    """)
    _write(era_dir / "planets" / "testworld.yaml", """
        planet: testworld
        planet_display_name: "Test World"
        rooms:
          - id: 0
            slug: room_zero
            name: "Room Zero"
            short_desc: "The starting room."
            description: "A simple room."
            zone: test_zone
            map_x: 0
            map_y: 0
          - id: 1
            slug: room_one
            name: "Room One"
            short_desc: "The second room."
            description: "Another simple room."
            zone: test_zone
            map_x: 1
            map_y: 0
        exits:
          - {from: 0, to: 1, forward: "east", reverse: "west"}
    """)
    return era_dir


# ══════════════════════════════════════════════════════════════════════════════
# 1. Era manifest loader
# ══════════════════════════════════════════════════════════════════════════════


class TestEraManifest(unittest.TestCase):

    def test_load_minimal_era_succeeds(self):
        from engine.world_loader import load_era_manifest
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            m = load_era_manifest(era_dir)
            self.assertEqual(m.era_code, "test_era")
            self.assertEqual(m.era_name, "Test Era")
            self.assertEqual(m.schema_version, 1)
            self.assertEqual(len(m.planet_paths), 1)

    def test_missing_era_yaml_raises(self):
        from engine.world_loader import load_era_manifest, WorldLoadError
        with TemporaryDirectory() as tmp:
            with self.assertRaises(WorldLoadError) as cm:
                load_era_manifest(Path(tmp) / "nonexistent")
            self.assertIn("Missing era manifest", str(cm.exception))

    def test_missing_zones_ref_raises(self):
        from engine.world_loader import load_era_manifest, WorldLoadError
        with TemporaryDirectory() as tmp:
            era_dir = Path(tmp) / "broken"
            _write(era_dir / "era.yaml", """
                schema_version: 1
                era:
                  code: broken
                content_refs:
                  planets: []
            """)
            with self.assertRaises(WorldLoadError) as cm:
                load_era_manifest(era_dir)
            self.assertIn("zones", str(cm.exception))

    def test_malformed_yaml_raises(self):
        from engine.world_loader import load_era_manifest, WorldLoadError
        with TemporaryDirectory() as tmp:
            era_dir = Path(tmp) / "bad"
            era_dir.mkdir()
            (era_dir / "era.yaml").write_text(
                "schema_version: 1\nera: { code: bad\n", encoding="utf-8"
            )  # unterminated mapping
            with self.assertRaises(WorldLoadError) as cm:
                load_era_manifest(era_dir)
            self.assertIn("parse", str(cm.exception).lower())


# ══════════════════════════════════════════════════════════════════════════════
# 2. Zone loader
# ══════════════════════════════════════════════════════════════════════════════


class TestZoneLoader(unittest.TestCase):

    def test_load_zones_returns_dict_keyed_by_slug(self):
        from engine.world_loader import load_era_manifest, load_zones
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            zones = load_zones(load_era_manifest(era_dir))
            self.assertIn("test_zone", zones)
            self.assertEqual(zones["test_zone"].slug, "test_zone")
            self.assertEqual(zones["test_zone"].name_match, "test")

    def test_zones_must_be_a_mapping_not_a_list(self):
        from engine.world_loader import load_era_manifest, load_zones, WorldLoadError
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            # Overwrite zones.yaml with list-of-zones (the design doc's
            # original proposal), which is NOT what we accept.
            _write(era_dir / "zones.yaml", """
                zones:
                  - slug: test_zone
                    name_match: test
            """)
            with self.assertRaises(WorldLoadError) as cm:
                load_zones(load_era_manifest(era_dir))
            self.assertIn("mapping", str(cm.exception))


# ══════════════════════════════════════════════════════════════════════════════
# 3. Planet loader
# ══════════════════════════════════════════════════════════════════════════════


class TestPlanetLoader(unittest.TestCase):

    def test_load_planets_returns_rooms_and_exits(self):
        from engine.world_loader import load_era_manifest, load_planets
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            rooms, exits = load_planets(load_era_manifest(era_dir))
            self.assertEqual(len(rooms), 2)
            self.assertEqual(len(exits), 1)
            # Rooms keyed by integer ID
            self.assertEqual(rooms[0].slug, "room_zero")
            self.assertEqual(rooms[0].planet, "testworld")
            self.assertEqual(rooms[0].map_x, 0)
            self.assertEqual(rooms[0].map_y, 0)

    def test_planet_field_stamped_on_rooms_and_exits(self):
        """The planet name from the planet file is propagated to every
        room and exit so cross-planet validation can identify origins.
        """
        from engine.world_loader import load_era_manifest, load_planets
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            rooms, exits = load_planets(load_era_manifest(era_dir))
            for r in rooms.values():
                self.assertEqual(r.planet, "testworld")
            for e in exits:
                self.assertEqual(e.planet, "testworld")

    def test_room_missing_id_raises(self):
        from engine.world_loader import load_era_manifest, load_planets, WorldLoadError
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - slug: no_id_room
                    name: "No ID Room"
                    zone: test_zone
                exits: []
            """)
            with self.assertRaises(WorldLoadError) as cm:
                load_planets(load_era_manifest(era_dir))
            self.assertIn("'id'", str(cm.exception))

    def test_exit_missing_required_field_raises(self):
        from engine.world_loader import load_era_manifest, load_planets, WorldLoadError
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: r0, name: "R0", zone: test_zone}
                  - {id: 1, slug: r1, name: "R1", zone: test_zone}
                exits:
                  - {from: 0, to: 1, forward: "east"}
            """)
            with self.assertRaises(WorldLoadError) as cm:
                load_planets(load_era_manifest(era_dir))
            self.assertIn("reverse", str(cm.exception))

    def test_duplicate_room_id_across_planets_raises(self):
        from engine.world_loader import load_era_manifest, load_planets, WorldLoadError
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            # Add a second planet that re-uses id 0
            _write(era_dir / "era.yaml", """
                schema_version: 1
                era:
                  code: test_era
                  name: "Test Era"
                content_refs:
                  zones: zones.yaml
                  planets:
                    - planets/testworld.yaml
                    - planets/dupeworld.yaml
                  wilderness: []
            """)
            _write(era_dir / "planets" / "dupeworld.yaml", """
                planet: dupeworld
                rooms:
                  - {id: 0, slug: dupe_room, name: "Dupe", zone: test_zone}
                exits: []
            """)
            with self.assertRaises(WorldLoadError) as cm:
                load_planets(load_era_manifest(era_dir))
            self.assertIn("Duplicate room id", str(cm.exception))


# ══════════════════════════════════════════════════════════════════════════════
# 4. Validation pass
# ══════════════════════════════════════════════════════════════════════════════


class TestValidation(unittest.TestCase):

    def _bundle(self, era_dir):
        from engine.world_loader import (
            load_era_manifest, load_zones, load_planets, validate_world,
        )
        m = load_era_manifest(era_dir)
        zones = load_zones(m)
        rooms, exits = load_planets(m)
        return zones, rooms, exits, validate_world(zones, rooms, exits)

    def test_minimal_era_passes_with_zero_errors(self):
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _, _, _, report = self._bundle(era_dir)
            self.assertTrue(report.ok)
            self.assertEqual(len(report.errors), 0)

    def test_dangling_exit_from_id_is_error(self):
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: r0, name: "R0", zone: test_zone}
                  - {id: 1, slug: r1, name: "R1", zone: test_zone}
                exits:
                  - {from: 99, to: 1, forward: "east", reverse: "west"}
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertFalse(report.ok)
            self.assertTrue(any("nonexistent from_id" in e for e in report.errors))

    def test_dangling_exit_to_id_is_error(self):
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: r0, name: "R0", zone: test_zone}
                exits:
                  - {from: 0, to: 99, forward: "east", reverse: "west"}
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertFalse(report.ok)
            self.assertTrue(any("nonexistent to_id" in e for e in report.errors))

    def test_invalid_forward_direction_is_error(self):
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: r0, name: "R0", zone: test_zone}
                  - {id: 1, slug: r1, name: "R1", zone: test_zone}
                exits:
                  - {from: 0, to: 1, forward: "BAD!@#", reverse: "west"}
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertFalse(report.ok)
            self.assertTrue(any("invalid forward direction" in e
                                for e in report.errors))

    def test_multi_word_reverse_is_accepted(self):
        """Authors use phrases like 'south to Bay 94' for the reverse
        direction when it's not just the mirror of the forward direction.
        First token must be a valid direction; rest is free text.
        """
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: r0, name: "R0", zone: test_zone}
                  - {id: 1, slug: r1, name: "R1", zone: test_zone}
                exits:
                  - {from: 0, to: 1, forward: "north", reverse: "south to Bay 94"}
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertTrue(report.ok, f"Errors: {report.errors}")

    def test_direction_collision_per_room_is_error(self):
        """A room can't have two outgoing exits in the same direction."""
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: r0, name: "R0", zone: test_zone}
                  - {id: 1, slug: r1, name: "R1", zone: test_zone}
                  - {id: 2, slug: r2, name: "R2", zone: test_zone}
                exits:
                  - {from: 0, to: 1, forward: "east", reverse: "west"}
                  - {from: 0, to: 2, forward: "east", reverse: "west"}
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertFalse(report.ok)
            self.assertTrue(any("'east' is claimed" in e for e in report.errors))

    def test_room_zone_must_resolve(self):
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: r0, name: "R0", zone: ghost_zone}
                exits: []
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertFalse(report.ok)
            self.assertTrue(any("nonexistent zone 'ghost_zone'" in e
                                for e in report.errors))

    def test_orphan_room_is_warning(self):
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: r0, name: "R0", zone: test_zone}
                  - {id: 1, slug: r1, name: "R1", zone: test_zone}
                  - {id: 2, slug: orphan, name: "Orphan", zone: test_zone}
                exits:
                  - {from: 0, to: 1, forward: "east", reverse: "west"}
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertTrue(report.ok)  # warning, not error
            self.assertTrue(any("orphan" in w.lower() and "no exits" in w
                                for w in report.warnings))

    def test_empty_zone_is_warning(self):
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "zones.yaml", """
                zones:
                  test_zone:
                    name_match: "test"
                  empty_zone:
                    name_match: "empty"
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertTrue(report.ok)
            self.assertTrue(any("'empty_zone' has no rooms" in w
                                for w in report.warnings))

    def test_duplicate_room_slug_is_error(self):
        """Two rooms with different IDs but same slug: spec forbids this."""
        with TemporaryDirectory() as tmp:
            era_dir = _make_minimal_era(Path(tmp))
            _write(era_dir / "planets" / "testworld.yaml", """
                planet: testworld
                rooms:
                  - {id: 0, slug: dupe, name: "First", zone: test_zone}
                  - {id: 1, slug: dupe, name: "Second", zone: test_zone}
                exits: []
            """)
            _, _, _, report = self._bundle(era_dir)
            self.assertFalse(report.ok)
            self.assertTrue(any("Duplicate room slug" in e
                                for e in report.errors))


# ══════════════════════════════════════════════════════════════════════════════
# 5. Real Clone Wars data — integration test
# ══════════════════════════════════════════════════════════════════════════════


class TestCloneWarsRealData(unittest.TestCase):
    """Run against the actual data/worlds/clone_wars/ in the repo.

    This is the most important test in the suite: it proves the loader
    handles real authored YAML, not just synthetic fixtures. If the YAML
    schema drifts during content authoring, this test catches it
    immediately.
    """

    def setUp(self):
        self.worlds_root = Path(PROJECT_ROOT) / "data" / "worlds"
        if not (self.worlds_root / "clone_wars").is_dir():
            self.skipTest("data/worlds/clone_wars/ not present")

    def test_clone_wars_parses_without_errors(self):
        """All 6 CW planets are wired in (F.4) AND content-clean (F.4b).

        Pre-F.4b (the F.4 baseline) accepted 35 content errors as known
        authoring debt and only asserted loader-class cleanliness. F.4b
        (Apr 30 2026) walked content debt to zero, so this test now
        asserts the strict invariant: zero errors of any kind.

        If this test fails with f4b_unpaired_exit or
        f4b_unresolved_target_slug or f4b_auto_inverse_collision errors,
        new content was added with new authoring gaps — find the
        offending new room block and add the missing reverse. Loader-class
        errors mean the loader regressed.
        """
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars", worlds_root=self.worlds_root)

        # Categorize for diagnostic output. F.4b reduced all known
        # categories to zero; this categorization remains so a future
        # failure cleanly attributes the error.
        def categorize(msg: str) -> str:
            if "invalid reverse direction ''" in msg:
                return "f4b_unpaired_exit"
            if "not found in any loaded room" in msg:
                return "f4b_unresolved_target_slug"
            if "claimed by" in msg and "exits" in msg:
                return "f4b_auto_inverse_collision"
            return "loader_class"

        if b.report.errors:
            buckets: dict[str, list[str]] = {}
            for e in b.report.errors:
                buckets.setdefault(categorize(e), []).append(e)
            summary = ", ".join(f"{k}={len(v)}" for k, v in buckets.items())
            self.fail(
                f"CW must parse without errors after F.4b. Current: "
                f"{len(b.report.errors)} errors ({summary}). First: "
                f"{b.report.errors[0]}"
            )

    def test_clone_wars_content_debt_is_bounded(self):
        """F.4b content-fix gate: with F.4b landed, the CW content-debt
        floor is ZERO. The bound was walked from 35 (F.4 baseline) to 0
        (F.4b closure) in a single drop.

        This test acts as a regression guard going forward — if any new
        CW content adds an unpaired exit, unresolved slug, or
        auto-inverse collision, this fires.

        If you legitimately need to expand the bound to absorb a known
        new authoring gap, do so explicitly and document why in the
        next handoff.
        """
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars", worlds_root=self.worlds_root)
        # F.4b closure (Apr 30 2026): 0 unpaired exits, 0 collisions,
        # 0 unresolved targets. CW now boots clean.
        self.assertLessEqual(
            len(b.report.errors), 0,
            f"Content debt regressed past F.4b floor of 0. Current: "
            f"{len(b.report.errors)} errors. Investigate new content "
            f"that introduced authoring gaps. First: "
            f"{b.report.errors[0] if b.report.errors else None}"
        )

    def test_clone_wars_loads_expected_planet_count(self):
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars", worlds_root=self.worlds_root)
        # F.4 (Apr 30 2026): all 6 planets now wired in.
        self.assertGreaterEqual(len(b.manifest.planet_paths), 6)

    def test_clone_wars_loads_expected_minimum_rooms(self):
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars", worlds_root=self.worlds_root)
        # F.4b (Apr 30 2026): all 6 planets wired in + underworld
        # surface-entry shim room. Tatooine 54 + Nar Shaddaa 30 +
        # Coruscant 56 (incl. shim) + Kuat 30 + Kamino 25 + Geonosis 35
        # = 230 rooms minimum. Use >= so adding rooms doesn't break.
        self.assertGreaterEqual(len(b.rooms), 230)

    def test_clone_wars_room_zero_is_docking_bay_94(self):
        """ID stability sanity check — room id=0 must be the starting
        room. If this test fails, the chargen flow is broken."""
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars", worlds_root=self.worlds_root)
        self.assertIn(0, b.rooms)
        self.assertEqual(b.rooms[0].slug, "docking_bay_94_entrance")
        self.assertEqual(b.rooms[0].planet, "tatooine")

    def test_clone_wars_every_exit_resolves(self):
        """Belt-and-suspenders: prove every exit's endpoints resolve."""
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars", worlds_root=self.worlds_root)
        for ex in b.exits:
            self.assertIn(ex.from_id, b.rooms,
                f"Exit {ex.from_id}→{ex.to_id} from_id missing")
            self.assertIn(ex.to_id, b.rooms,
                f"Exit {ex.from_id}→{ex.to_id} to_id missing")


if __name__ == "__main__":
    unittest.main()
