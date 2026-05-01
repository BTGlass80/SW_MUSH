"""F.4 (Apr 30 2026) — Per-room exit dict format loader tests.

Covers the loader extension that teaches `_load_planet_file` and
`load_planets` to parse per-room `exits: {direction: target_slug}`
blocks (the format used by clone_wars_era_design_v3.md §6, adopted by
coruscant.yaml / kuat.yaml / kamino.yaml / geonosis.yaml).

Tests cover:
  - The new `_PerRoomExitDirective` staging dataclass exists
  - Per-room exit dicts are collected during file parsing
  - `load_planets` resolves slug targets to integer IDs after all
    files are parsed (so cross-planet exits work)
  - Cardinal-symmetric reverse directions auto-derive when no pair
    is authored on the destination
  - Asymmetric named exits don't auto-derive (the validator flags
    them as missing reverse, which is correct content feedback)
  - Unresolved target slugs are surfaced as soft errors via
    `unresolved_report` (do not crash the load)
  - The legacy top-level `exits:` list format still works
  - A planet file can mix both formats (forward-compat)
  - The empty-string reverse no longer triggers spurious direction
    collision errors
"""

import unittest
import tempfile
import textwrap
from pathlib import Path


class TestPerRoomExitDirectiveStaging(unittest.TestCase):
    """The internal staging dataclass exists and has the right shape."""

    def test_directive_dataclass_present(self):
        from engine import world_loader
        self.assertTrue(hasattr(world_loader, "_PerRoomExitDirective"))

    def test_directive_fields(self):
        from engine.world_loader import _PerRoomExitDirective
        d = _PerRoomExitDirective(
            from_slug="a", direction="north", to_slug="b", planet="p",
        )
        self.assertEqual(d.from_slug, "a")
        self.assertEqual(d.direction, "north")
        self.assertEqual(d.to_slug, "b")
        self.assertEqual(d.planet, "p")
        self.assertFalse(d.locked)
        self.assertFalse(d.hidden)


# ── Fixture helpers ─────────────────────────────────────────────────────────

# Helper to build a self-contained era directory in a tmpdir.
# We only need: era.yaml + zones.yaml + planet files. Nothing else
# is required for the loader path under test.

ERA_YAML_TEMPLATE = """schema_version: 1
era:
  code: testera
  name: Test Era
content_refs:
  zones: zones.yaml
  planets:
{planet_lines}
  wilderness: []
"""

ZONES_YAML_TEMPLATE = """zones:
{zone_blocks}
"""


def _write_era(tmp: Path, planet_files: list[tuple[str, str]],
               zone_codes: list[str]):
    planet_lines = "\n".join(f"    - planets/{name}" for name, _ in planet_files)
    zone_blocks = "\n".join(
        f"  {z}:\n    name_match: {z}\n    narrative_tone: test\n"
        for z in zone_codes
    )
    (tmp / "era.yaml").write_text(
        ERA_YAML_TEMPLATE.format(planet_lines=planet_lines)
    )
    (tmp / "zones.yaml").write_text(
        ZONES_YAML_TEMPLATE.format(zone_blocks=zone_blocks)
    )
    pdir = tmp / "planets"
    pdir.mkdir()
    for name, body in planet_files:
        (pdir / name).write_text(body)


# ── Per-room exit format ────────────────────────────────────────────────────


class TestPerRoomExitParsing(unittest.TestCase):
    """The per-room exits dict format parses correctly."""

    def test_per_room_exits_collected_into_directives(self):
        from engine.world_loader import _load_planet_file
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "x.yaml"
            f.write_text(textwrap.dedent("""\
                planet: x
                rooms:
                  - id: 1
                    slug: a
                    name: A
                    zone: z1
                    exits:
                      north: b
                      east: c
                  - id: 2
                    slug: b
                    name: B
                    zone: z1
                    exits:
                      south: a
                  - id: 3
                    slug: c
                    name: C
                    zone: z1
            """))
            rooms, top_exits, directives = _load_planet_file(f)
            self.assertEqual(len(rooms), 3)
            self.assertEqual(len(top_exits), 0)
            self.assertEqual(len(directives), 3)
            forward_pairs = {(d.from_slug, d.direction, d.to_slug) for d in directives}
            self.assertIn(("a", "north", "b"), forward_pairs)
            self.assertIn(("a", "east", "c"), forward_pairs)
            self.assertIn(("b", "south", "a"), forward_pairs)

    def test_per_room_exits_target_must_be_string(self):
        from engine.world_loader import _load_planet_file, WorldLoadError
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "x.yaml"
            f.write_text(textwrap.dedent("""\
                planet: x
                rooms:
                  - id: 1
                    slug: a
                    zone: z1
                    exits:
                      north: 42
            """))
            with self.assertRaises(WorldLoadError):
                _load_planet_file(f)

    def test_top_level_exits_list_still_works(self):
        """Back-compat: tatooine/nar_shaddaa-style top-level exits list."""
        from engine.world_loader import _load_planet_file
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "x.yaml"
            f.write_text(textwrap.dedent("""\
                planet: x
                rooms:
                  - id: 1
                    slug: a
                    zone: z1
                  - id: 2
                    slug: b
                    zone: z1
                exits:
                  - from: 1
                    to: 2
                    forward: north
                    reverse: south
            """))
            rooms, top_exits, directives = _load_planet_file(f)
            self.assertEqual(len(top_exits), 1)
            self.assertEqual(top_exits[0].from_id, 1)
            self.assertEqual(top_exits[0].to_id, 2)
            self.assertEqual(top_exits[0].forward, "north")
            self.assertEqual(top_exits[0].reverse, "south")
            self.assertEqual(len(directives), 0)

    def test_planet_file_can_mix_both_formats(self):
        """A single file with BOTH per-room dicts AND top-level list."""
        from engine.world_loader import _load_planet_file
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "x.yaml"
            f.write_text(textwrap.dedent("""\
                planet: x
                rooms:
                  - id: 1
                    slug: a
                    zone: z1
                    exits:
                      north: b
                  - id: 2
                    slug: b
                    zone: z1
                  - id: 3
                    slug: c
                    zone: z1
                exits:
                  - from: 2
                    to: 3
                    forward: east
                    reverse: west
            """))
            rooms, top_exits, directives = _load_planet_file(f)
            self.assertEqual(len(top_exits), 1)
            self.assertEqual(len(directives), 1)


# ── Slug → ID resolution ────────────────────────────────────────────────────


class TestSlugResolution(unittest.TestCase):
    """`load_planets` resolves slug targets after parsing all files."""

    def _setup_era(self, planet_files):
        td = tempfile.mkdtemp()
        tmp = Path(td)
        _write_era(tmp, planet_files, ["z1"])
        return tmp

    def test_resolves_within_a_planet(self):
        from engine.world_loader import load_era_manifest, load_planets
        tmp = self._setup_era([
            ("p1.yaml", textwrap.dedent("""\
                planet: p1
                rooms:
                  - id: 1
                    slug: a
                    zone: z1
                    exits:
                      north: b
                  - id: 2
                    slug: b
                    zone: z1
                    exits:
                      south: a
            """)),
        ])
        manifest = load_era_manifest(tmp)
        rooms, exits = load_planets(manifest)
        self.assertEqual(len(rooms), 2)
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].from_id, 1)
        self.assertEqual(exits[0].to_id, 2)
        self.assertEqual(exits[0].forward, "north")
        self.assertEqual(exits[0].reverse, "south")

    def test_resolves_across_planets(self):
        """Cross-planet exits — directive on planet A points at slug on planet B."""
        from engine.world_loader import load_era_manifest, load_planets
        tmp = self._setup_era([
            ("p1.yaml", textwrap.dedent("""\
                planet: p1
                rooms:
                  - id: 1
                    slug: a
                    zone: z1
                    exits:
                      ship: b
            """)),
            ("p2.yaml", textwrap.dedent("""\
                planet: p2
                rooms:
                  - id: 100
                    slug: b
                    zone: z1
                    exits:
                      planet: a
            """)),
        ])
        manifest = load_era_manifest(tmp)
        rooms, exits = load_planets(manifest)
        self.assertEqual(len(exits), 1)
        # Cross-planet exit: from p1 room 1 → p2 room 100
        self.assertEqual(exits[0].from_id, 1)
        self.assertEqual(exits[0].to_id, 100)
        self.assertEqual(exits[0].forward, "ship")
        self.assertEqual(exits[0].reverse, "planet")

    def test_unresolved_target_slug_appended_to_report(self):
        from engine.world_loader import load_era_manifest, load_planets
        tmp = self._setup_era([
            ("p1.yaml", textwrap.dedent("""\
                planet: p1
                rooms:
                  - id: 1
                    slug: a
                    zone: z1
                    exits:
                      north: nonexistent_slug
            """)),
        ])
        manifest = load_era_manifest(tmp)
        unresolved = []
        rooms, exits = load_planets(manifest, unresolved_report=unresolved)
        self.assertEqual(len(unresolved), 1)
        self.assertIn("nonexistent_slug", unresolved[0])
        # The dangling exit should have been dropped, not become an Exit.
        self.assertEqual(len(exits), 0)

    def test_unresolved_target_silent_when_no_report(self):
        """When caller doesn't pass unresolved_report, unresolved
        targets are silently dropped (no crash)."""
        from engine.world_loader import load_era_manifest, load_planets
        tmp = self._setup_era([
            ("p1.yaml", textwrap.dedent("""\
                planet: p1
                rooms:
                  - id: 1
                    slug: a
                    zone: z1
                    exits:
                      north: nope
            """)),
        ])
        manifest = load_era_manifest(tmp)
        # Should not raise.
        rooms, exits = load_planets(manifest)
        self.assertEqual(len(exits), 0)


# ── Cardinal auto-inverse ────────────────────────────────────────────────────


class TestCardinalAutoInverse(unittest.TestCase):
    """Symmetric cardinals auto-derive their reverse when not authored."""

    def _resolve(self, planet_yaml: str):
        """Helper: parse a single planet file and run resolve."""
        from engine.world_loader import (
            _load_planet_file, _resolve_per_room_directives,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f = tmp / "x.yaml"
            f.write_text(planet_yaml)
            rooms, _, directives = _load_planet_file(f)
            rooms_dict = {r.id: r for r in rooms}
            return _resolve_per_room_directives(directives, rooms_dict)

    def test_north_south_auto_inverse(self):
        exits = self._resolve(textwrap.dedent("""\
            planet: x
            rooms:
              - id: 1
                slug: a
                zone: z1
                exits:
                  north: b
              - id: 2
                slug: b
                zone: z1
                exits:
                  east: c
              - id: 3
                slug: c
                zone: z1
        """))
        # 2 directives → 2 exits (each canonical pair once). Find the
        # north-from-a→b exit; reverse should auto-derive to 'south'.
        ab_exit = next(
            e for e in exits if e.from_id == 1 and e.to_id == 2
        )
        self.assertEqual(ab_exit.forward, "north")
        self.assertEqual(ab_exit.reverse, "south")

    def test_up_down_auto_inverse(self):
        exits = self._resolve(textwrap.dedent("""\
            planet: x
            rooms:
              - id: 1
                slug: a
                zone: z1
                exits:
                  up: b
              - id: 2
                slug: b
                zone: z1
        """))
        e = next(iter(exits))
        self.assertEqual(e.forward, "up")
        self.assertEqual(e.reverse, "down")

    def test_in_out_auto_inverse(self):
        exits = self._resolve(textwrap.dedent("""\
            planet: x
            rooms:
              - id: 1
                slug: a
                zone: z1
                exits:
                  in: b
              - id: 2
                slug: b
                zone: z1
        """))
        e = next(iter(exits))
        self.assertEqual(e.forward, "in")
        self.assertEqual(e.reverse, "out")

    def test_diagonal_auto_inverse(self):
        exits = self._resolve(textwrap.dedent("""\
            planet: x
            rooms:
              - id: 1
                slug: a
                zone: z1
                exits:
                  northeast: b
              - id: 2
                slug: b
                zone: z1
        """))
        e = next(iter(exits))
        self.assertEqual(e.reverse, "southwest")

    def test_authored_pair_overrides_auto_inverse(self):
        """If the destination explicitly authored a different reverse,
        do NOT auto-overwrite it."""
        exits = self._resolve(textwrap.dedent("""\
            planet: x
            rooms:
              - id: 1
                slug: a
                zone: z1
                exits:
                  north: b
              - id: 2
                slug: b
                zone: z1
                exits:
                  vent: a
        """))
        ab_exit = next(e for e in exits if e.from_id == 1 and e.to_id == 2)
        self.assertEqual(ab_exit.forward, "north")
        self.assertEqual(ab_exit.reverse, "vent")

    def test_destination_already_uses_inverse_blocks_auto_derive(self):
        """If the destination room already has the would-be auto-inverse
        direction pointing somewhere else, don't auto-fill (would cause
        a real direction collision)."""
        exits = self._resolve(textwrap.dedent("""\
            planet: x
            rooms:
              - id: 1
                slug: a
                zone: z1
                exits:
                  north: b
              - id: 2
                slug: b
                zone: z1
                exits:
                  south: c
              - id: 3
                slug: c
                zone: z1
        """))
        # b→a forward direction: not 'south' (south is taken by b→c)
        ab_exit = next(e for e in exits if e.from_id == 1 and e.to_id == 2)
        self.assertEqual(ab_exit.reverse, "")  # No auto-derive

    def test_named_exit_does_not_auto_inverse(self):
        """Asymmetric named exits ('hub', 'corridor', 'chamber') don't
        auto-derive — the validator flags them as missing reverse, which
        is correct content feedback."""
        exits = self._resolve(textwrap.dedent("""\
            planet: x
            rooms:
              - id: 1
                slug: a
                zone: z1
                exits:
                  corridor: b
              - id: 2
                slug: b
                zone: z1
        """))
        e = next(iter(exits))
        self.assertEqual(e.forward, "corridor")
        self.assertEqual(e.reverse, "")


# ── Validation — collision check skips empty reverses ───────────────────────


class TestEmptyReverseDoesNotCollide(unittest.TestCase):
    """The validator must not treat empty-string reverses as a direction
    collision when multiple unpaired exits target the same room."""

    def test_multiple_unpaired_exits_to_same_dest_no_spurious_collision(self):
        from engine.world_loader import (
            load_era_manifest, load_planets, load_zones, validate_world,
        )
        td = tempfile.mkdtemp()
        tmp = Path(td)
        # 4 spokes pointing at one hub via named directions; hub has no
        # back exits authored → all 4 reverses come back empty. The
        # validator should produce 4 invalid-reverse errors but NOT a
        # spurious "direction '' claimed by 4 exits" error.
        _write_era(tmp, [
            ("x.yaml", textwrap.dedent("""\
                planet: x
                rooms:
                  - id: 1
                    slug: hub
                    zone: z1
                  - id: 2
                    slug: spoke_a
                    zone: z1
                    exits:
                      hub: hub
                  - id: 3
                    slug: spoke_b
                    zone: z1
                    exits:
                      hub: hub
                  - id: 4
                    slug: spoke_c
                    zone: z1
                    exits:
                      hub: hub
                  - id: 5
                    slug: spoke_d
                    zone: z1
                    exits:
                      hub: hub
            """)),
        ], ["z1"])
        manifest = load_era_manifest(tmp)
        zones = load_zones(manifest)
        rooms, exits = load_planets(manifest)
        report = validate_world(zones, rooms, exits)
        # 4 invalid-reverse errors expected (one per exit)
        invalid_rev = [
            e for e in report.errors if "invalid reverse direction" in e
        ]
        self.assertEqual(len(invalid_rev), 4)
        # Zero collision errors with empty direction
        spurious_collisions = [
            e for e in report.errors
            if "claimed by" in e and "direction ''" in e
        ]
        self.assertEqual(len(spurious_collisions), 0)


# ── Real CW data: F.4 wire-in produces sane numbers ─────────────────────────


class TestF4WireInLiveData(unittest.TestCase):
    """The F.4 manifest wire-in must produce the expected room/zone counts
    against the real CW data."""

    def test_all_six_cw_planets_load(self):
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars")
        # Tatooine (54) + Nar Shaddaa (30) + Coruscant (55) + Kuat (30)
        # + Kamino (25) + Geonosis (35) = 229
        self.assertGreaterEqual(len(b.rooms), 229)

    def test_all_six_planets_present_in_manifest(self):
        from engine.world_loader import load_era_manifest
        from pathlib import Path
        manifest = load_era_manifest(Path("data/worlds/clone_wars"))
        names = [p.name for p in manifest.planet_paths]
        self.assertIn("coruscant.yaml", names)
        self.assertIn("kuat.yaml", names)
        self.assertIn("kamino.yaml", names)
        self.assertIn("geonosis.yaml", names)

    def test_zones_yaml_aligned_to_planet_files(self):
        """The 9 zones renamed in F.4 are all present in zones.yaml AND
        used by at least one room in the planet files."""
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars")
        renamed = [
            "kdy_orbital_ring", "kuat_city_embassy", "kuat_main_spaceport",
            "kamino_tipoca_city", "kamino_cloning_halls", "kamino_ocean_platform",
            "geonosis_petranaki", "geonosis_surface", "geonosis_deep_hive",
        ]
        for z in renamed:
            self.assertIn(z, b.zones, f"Renamed zone {z!r} missing from zones.yaml")
            using = [r for r in b.rooms.values() if r.zone == z]
            self.assertGreater(
                len(using), 0,
                f"Renamed zone {z!r} is in zones.yaml but no room uses it"
            )

    def test_no_loader_class_errors(self):
        """The loader produces only F.4b content-debt errors — never
        loader-class errors. If this fails, the loader regressed."""
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars")
        # Loader-class would be: any zone missing from zones.yaml,
        # any from_id/to_id missing, any duplicate slug, etc.
        loader_class_signatures = (
            "nonexistent zone",
            "nonexistent from_id",
            "nonexistent to_id",
            "Duplicate room slug",
        )
        loader_errors = [
            e for e in b.report.errors
            if any(sig in e for sig in loader_class_signatures)
        ]
        self.assertEqual(
            loader_errors, [],
            f"Loader regressed — saw loader-class error(s): {loader_errors[:2]}"
        )


# ── Source-level guards — F.4 anchor present ────────────────────────────────


class TestSourceLevelGuards(unittest.TestCase):
    def test_f4_anchor_comments_present(self):
        from pathlib import Path
        src = Path("engine/world_loader.py").read_text()
        self.assertIn("F.4 (Apr 30 2026)", src)

    def test_resolve_per_room_directives_function_exists(self):
        from engine import world_loader
        self.assertTrue(hasattr(world_loader, "_resolve_per_room_directives"))


if __name__ == "__main__":
    unittest.main()
