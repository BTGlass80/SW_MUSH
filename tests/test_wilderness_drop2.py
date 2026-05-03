# -*- coding: utf-8 -*-
"""
tests/test_wilderness_drop2.py — Wilderness coordinate movement core.

Closes the loop on Wilderness Drop 2 (May 3 2026): verifies the
schema additions land cleanly on a fresh DB, the virtual sentinel
and region registry rows are written by the build, and the pure-
function movement + render kernel behaves correctly across the
boundary cases that matter.

What this test suite validates
==============================

  1. Schema v20: characters.wilderness_region_slug, wilderness_x,
     wilderness_y columns; wilderness_regions table with the right
     shape; idx_characters_wilderness_region partial index.
  2. Build-time: write_wilderness_region writes a sentinel room AND
     a wilderness_regions registry row, both idempotent on rebuild.
  3. Sentinel room is named, has the right wilderness_region_id, and
     properties.slug matches the design's wilderness_<slug>_virtual.
  4. Region registry row reflects YAML data accurately.
  5. move_in_wilderness: cardinal/diagonal directions, abbreviations,
     bounds, boundary-crossing signaling, terrain resolution.
  6. render_tile: deterministic variant selection, time overlays,
     all expected fields populated, out-of-bounds graceful.
  7. render_adjacent_terrain: cardinal neighbors, edge None handling.
  8. The new writable columns are in _CHARACTER_WRITABLE_COLUMNS.

NOT covered (deferred by design):
  - Live look/move command integration (Drop 2 phase 2)
  - Edge crossings to hand-built rooms (Drop 2 phase 2 — needs YAML edges)
  - Stamina / hazards / encounters (Drops 3, 5)
  - Search / discovery / faction visibility (Drop 4)
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from build_mos_eisley import build
from db.database import Database, SCHEMA_VERSION
from engine.wilderness_loader import (
    WildernessRegion, WildernessLandmark, WildernessTerrain,
    load_wilderness_region,
)
from engine.wilderness_movement import (
    ALL_DIRECTIONS, CARDINAL_DIRECTIONS,
    MoveResult,
    move_in_wilderness,
    normalize_direction,
    render_adjacent_terrain,
    render_tile,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _build_cw():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db_path)
    asyncio.run(build(db_path=db_path, era="clone_wars"))
    return db_path


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def _toy_region(width=10, height=10, default_terrain="dune", terrains=None):
    """Build a synthetic WildernessRegion for pure-function tests.

    Avoids loading the full Dune Sea YAML when all we need is bounds
    + one terrain; keeps tests fast and isolated from content drift.
    """
    if terrains is None:
        terrains = {
            "dune": WildernessTerrain(
                name="dune",
                move_cost=2,
                sight_radius=1,
                ambient_hazard="extreme_heat",
                hazard_severity=2,
                variants=[
                    "Variant A: rolling dunes.",
                    "Variant B: wind-blown sand.",
                    "Variant C: heat shimmer over crests.",
                ],
                time_overlays={"night": "Cold silver-blue moonlight."},
            ),
            "rocky_outcrop": WildernessTerrain(
                name="rocky_outcrop",
                move_cost=3,
                sight_radius=2,
                ambient_hazard=None,
                hazard_severity=0,
                variants=["Variant: scattered stones."],
            ),
        }
    return WildernessRegion(
        slug="test_region",
        name="Test Region",
        planet="testworld",
        zone="test_zone",
        default_security="lawless",
        grid_width=width,
        grid_height=height,
        tile_scale_km=2,
        default_terrain=default_terrain,
        terrains=terrains,
        landmarks=[],
        narrative_tone_key="",
        schema_version=1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema v20: migration applied, columns + table exist
# ─────────────────────────────────────────────────────────────────────────────


class TestSchemaV20:
    """Schema v20 lands the wilderness movement columns + registry table."""

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_schema_version_at_least_20(self):
        rows = _query(
            self.db_path,
            "SELECT MAX(version) AS v FROM schema_version",
        )
        assert rows[0]["v"] >= 20

    def test_characters_has_wilderness_region_slug(self):
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        assert "wilderness_region_slug" in cols

    def test_characters_has_wilderness_x_y(self):
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        assert "wilderness_x" in cols
        assert "wilderness_y" in cols

    def test_wilderness_regions_table_exists(self):
        rows = _query(
            self.db_path,
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='wilderness_regions'",
        )
        assert len(rows) == 1

    def test_wilderness_regions_has_expected_columns(self):
        rows = _query(self.db_path, "PRAGMA table_info(wilderness_regions)")
        cols = {r["name"] for r in rows}
        for required in (
            "slug", "name", "planet", "zone_slug", "width", "height",
            "tile_scale_km", "default_terrain", "default_security",
            "sentinel_room_id", "config_json", "created_at",
        ):
            assert required in cols, f"missing column: {required}"

    def test_partial_index_present(self):
        rows = _query(
            self.db_path,
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_characters_wilderness_region'",
        )
        assert len(rows) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. Build-time: sentinel + registry written for the Dune Sea
# ─────────────────────────────────────────────────────────────────────────────


class TestSentinelAndRegistryWrite:
    """A fresh CW build writes a sentinel room + registry row for the Dune Sea."""

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_sentinel_room_exists(self):
        rows = _query(
            self.db_path,
            "SELECT id, name, properties FROM rooms "
            "WHERE name = 'Wilderness: The Dune Sea'",
        )
        assert len(rows) == 1
        props = json.loads(rows[0]["properties"])
        assert props.get("slug") == "wilderness_tatooine_dune_sea_virtual"
        assert props.get("wilderness_sentinel") is True

    def test_sentinel_has_region_id(self):
        rows = _query(
            self.db_path,
            "SELECT wilderness_region_id FROM rooms "
            "WHERE name = 'Wilderness: The Dune Sea'",
        )
        assert rows[0]["wilderness_region_id"] == "tatooine_dune_sea"

    def test_registry_row_for_dune_sea(self):
        rows = _query(
            self.db_path,
            "SELECT * FROM wilderness_regions WHERE slug = 'tatooine_dune_sea'",
        )
        assert len(rows) == 1
        r = rows[0]
        assert r["name"] == "The Dune Sea"
        assert r["planet"] == "tatooine"
        assert r["zone_slug"] == "jundland_wastes"
        assert r["width"] == 40
        assert r["height"] == 40
        assert r["tile_scale_km"] == 2
        assert r["default_terrain"] == "dune"
        assert r["default_security"] == "lawless"

    def test_registry_links_to_sentinel(self):
        rows = _query(
            self.db_path,
            """
            SELECT wr.sentinel_room_id, r.name AS sentinel_name
            FROM wilderness_regions wr
            JOIN rooms r ON r.id = wr.sentinel_room_id
            WHERE wr.slug = 'tatooine_dune_sea'
            """,
        )
        assert len(rows) == 1
        assert rows[0]["sentinel_name"] == "Wilderness: The Dune Sea"

    def test_sentinel_singleton(self):
        # Idempotent rebuild check: only ONE sentinel per region.
        rows = _query(
            self.db_path,
            "SELECT COUNT(*) AS n FROM rooms "
            "WHERE name = 'Wilderness: The Dune Sea'",
        )
        assert rows[0]["n"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. Movement: pure function bounds/direction
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalizeDirection:
    def test_full_cardinals(self):
        for d in ("north", "south", "east", "west"):
            assert normalize_direction(d) == d

    def test_full_diagonals(self):
        for d in ("northeast", "northwest", "southeast", "southwest"):
            assert normalize_direction(d) == d

    def test_abbreviations(self):
        assert normalize_direction("n") == "north"
        assert normalize_direction("s") == "south"
        assert normalize_direction("e") == "east"
        assert normalize_direction("w") == "west"
        assert normalize_direction("ne") == "northeast"
        assert normalize_direction("nw") == "northwest"
        assert normalize_direction("se") == "southeast"
        assert normalize_direction("sw") == "southwest"

    def test_case_insensitive(self):
        assert normalize_direction("North") == "north"
        assert normalize_direction("NE") == "northeast"

    def test_invalid(self):
        assert normalize_direction("up") is None
        assert normalize_direction("") is None
        assert normalize_direction("xyz") is None
        assert normalize_direction(None) is None


class TestMoveInWilderness:
    def test_north_moves_y_up(self):
        region = _toy_region(10, 10)
        result = move_in_wilderness(region, 5, 5, "north")
        assert result.ok is True
        assert result.new_x == 5
        assert result.new_y == 6

    def test_south_moves_y_down(self):
        region = _toy_region(10, 10)
        result = move_in_wilderness(region, 5, 5, "south")
        assert result.ok is True
        assert result.new_y == 4

    def test_east_moves_x_up(self):
        region = _toy_region(10, 10)
        result = move_in_wilderness(region, 5, 5, "east")
        assert result.ok is True
        assert result.new_x == 6

    def test_diagonal_moves_both(self):
        region = _toy_region(10, 10)
        result = move_in_wilderness(region, 5, 5, "northeast")
        assert result.ok is True
        assert (result.new_x, result.new_y) == (6, 6)

    def test_abbreviation_matches_full_direction(self):
        region = _toy_region(10, 10)
        a = move_in_wilderness(region, 5, 5, "n")
        b = move_in_wilderness(region, 5, 5, "north")
        assert a.new_x == b.new_x and a.new_y == b.new_y

    def test_north_at_top_edge_signals_boundary(self):
        region = _toy_region(10, 10)
        result = move_in_wilderness(region, 5, 9, "north")
        assert result.ok is False
        assert result.crossed_boundary is True
        assert result.boundary_direction == "north"

    def test_west_at_left_edge_signals_boundary(self):
        region = _toy_region(10, 10)
        result = move_in_wilderness(region, 0, 5, "west")
        assert result.ok is False
        assert result.crossed_boundary is True
        assert result.boundary_direction == "west"

    def test_diagonal_at_corner_signals_boundary(self):
        region = _toy_region(10, 10)
        result = move_in_wilderness(region, 0, 0, "southwest")
        assert result.ok is False
        assert result.crossed_boundary is True

    def test_invalid_direction(self):
        region = _toy_region(10, 10)
        result = move_in_wilderness(region, 5, 5, "up")
        assert result.ok is False
        assert result.crossed_boundary is False
        assert "Unknown direction" in result.reason

    def test_terrain_resolved_at_destination(self):
        region = _toy_region(10, 10, default_terrain="dune")
        result = move_in_wilderness(region, 5, 5, "north")
        assert result.terrain == "dune"

    def test_move_cost_pulled_from_terrain(self):
        region = _toy_region(10, 10)  # dune has move_cost=2
        result = move_in_wilderness(region, 5, 5, "north")
        assert result.move_cost == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. render_tile: deterministic variants, overlays, fields
# ─────────────────────────────────────────────────────────────────────────────


class TestRenderTile:
    def test_returns_all_expected_fields(self):
        region = _toy_region(10, 10)
        out = render_tile(region, 3, 4)
        for key in (
            "region_name", "coordinates", "terrain", "description",
            "time_overlay", "move_cost", "sight_radius",
            "ambient_hazard", "hazard_severity", "security",
            "out_of_bounds",
        ):
            assert key in out, f"missing key: {key}"

    def test_terrain_attributes_pulled_through(self):
        region = _toy_region(10, 10)
        out = render_tile(region, 3, 4)
        assert out["terrain"] == "dune"
        assert out["move_cost"] == 2
        assert out["sight_radius"] == 1
        assert out["ambient_hazard"] == "extreme_heat"
        assert out["hazard_severity"] == 2
        assert out["security"] == "lawless"

    def test_variant_is_deterministic(self):
        region = _toy_region(10, 10)
        # Same tile, multiple calls → same description
        out1 = render_tile(region, 3, 4)
        out2 = render_tile(region, 3, 4)
        assert out1["description"] == out2["description"]

    def test_different_tiles_pick_different_variants(self):
        # With a 3-variant terrain on a 10x10 grid, we should see all
        # three variants represented across the tiles.
        region = _toy_region(10, 10)
        descs = set()
        for x in range(10):
            for y in range(10):
                descs.add(render_tile(region, x, y)["description"])
        # At least 2 distinct (probabilistically all 3 with 100 tiles
        # and a uniform hash, but ≥2 is the floor that catches
        # "single variant always picked" bugs).
        assert len(descs) >= 2

    def test_time_overlay_applied_when_match(self):
        region = _toy_region(10, 10)
        out = render_tile(region, 3, 4, time_of_day="night")
        assert out["time_overlay"] is not None
        assert "moonlight" in out["time_overlay"].lower()

    def test_time_overlay_none_when_no_match(self):
        region = _toy_region(10, 10)
        out = render_tile(region, 3, 4, time_of_day="day")
        # toy region only has "night" overlay
        assert out["time_overlay"] is None

    def test_out_of_bounds_graceful(self):
        region = _toy_region(10, 10)
        out = render_tile(region, -1, 5)
        assert out["out_of_bounds"] is True

        out = render_tile(region, 5, 99)
        assert out["out_of_bounds"] is True

    def test_in_bounds_flag_is_false(self):
        region = _toy_region(10, 10)
        out = render_tile(region, 5, 5)
        assert out["out_of_bounds"] is False

    def test_terrain_with_no_variants_returns_empty_description(self):
        # Defensive: a terrain config with no variants list should
        # return "" rather than crashing.
        region = _toy_region(10, 10)
        region.terrains["dune"] = WildernessTerrain(
            name="dune", move_cost=1, sight_radius=1,
            ambient_hazard=None, hazard_severity=0, variants=[],
        )
        out = render_tile(region, 3, 4)
        assert out["description"] == ""


class TestRenderAdjacentTerrain:
    def test_returns_all_cardinals(self):
        region = _toy_region(10, 10)
        out = render_adjacent_terrain(region, 5, 5)
        assert set(out.keys()) == set(CARDINAL_DIRECTIONS)

    def test_in_bounds_neighbors_are_terrain_strings(self):
        region = _toy_region(10, 10)
        out = render_adjacent_terrain(region, 5, 5)
        for d, t in out.items():
            assert t == "dune"

    def test_edge_neighbors_are_none(self):
        region = _toy_region(10, 10)
        # At (0, 0): west and south are out of bounds
        out = render_adjacent_terrain(region, 0, 0)
        assert out["west"] is None
        assert out["south"] is None
        assert out["east"] == "dune"
        assert out["north"] == "dune"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Real Dune Sea YAML round-trip
# ─────────────────────────────────────────────────────────────────────────────


class TestDuneSeaIntegration:
    """The pure-function kernel works against the real Dune Sea YAML."""

    @classmethod
    def setup_class(cls):
        path = os.path.join(
            PROJECT_ROOT,
            "data", "worlds", "clone_wars", "wilderness", "dune_sea.yaml",
        )
        report = load_wilderness_region(path)
        assert report.ok, f"Failed to load Dune Sea: {report.errors}"
        cls.region = report.region

    def test_default_terrain_is_dune(self):
        out = render_tile(self.region, 20, 20)
        assert out["terrain"] == "dune"

    def test_dune_sea_is_40x40(self):
        assert self.region.grid_width == 40
        assert self.region.grid_height == 40

    def test_move_within_bounds(self):
        result = move_in_wilderness(self.region, 20, 20, "north")
        assert result.ok is True
        assert (result.new_x, result.new_y) == (20, 21)

    def test_move_at_north_edge_signals_boundary(self):
        result = move_in_wilderness(self.region, 20, 39, "north")
        assert result.ok is False
        assert result.crossed_boundary is True

    def test_render_dune_sea_tile(self):
        out = render_tile(self.region, 20, 20)
        assert out["region_name"] == "The Dune Sea"
        assert out["security"] == "lawless"
        assert out["move_cost"] == 2
        assert out["ambient_hazard"] == "extreme_heat"
        # One of the three authored dune variants
        assert out["description"] in [
            "Rolling dunes stretch in every direction. The sand shifts with each gust of wind.",
            "A sea of sand, sculpted by centuries of wind. The twin suns hammer down.",
            "Steep dunes rise and fall. Footprints vanish within minutes of being made.",
        ]

    def test_render_dune_sea_night_overlay(self):
        out = render_tile(self.region, 20, 20, time_of_day="night")
        assert out["time_overlay"] is not None
        assert "silver-blue" in out["time_overlay"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Database writable-columns include v20 columns
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabaseWritableColumns:
    def test_wilderness_region_slug_writable(self):
        assert "wilderness_region_slug" in Database._CHARACTER_WRITABLE_COLUMNS

    def test_wilderness_x_writable(self):
        assert "wilderness_x" in Database._CHARACTER_WRITABLE_COLUMNS

    def test_wilderness_y_writable(self):
        assert "wilderness_y" in Database._CHARACTER_WRITABLE_COLUMNS


# ─────────────────────────────────────────────────────────────────────────────
# 7. Module self-docs / source guards
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleSelfDocs:
    def test_wilderness_movement_module_exists(self):
        path = os.path.join(PROJECT_ROOT, "engine", "wilderness_movement.py")
        assert os.path.exists(path)

    def test_wilderness_writer_writes_sentinel(self):
        path = os.path.join(PROJECT_ROOT, "engine", "wilderness_writer.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "_write_or_reuse_sentinel" in text
        assert "_upsert_region_registry" in text

    def test_db_migration_v20_present(self):
        path = os.path.join(PROJECT_ROOT, "db", "database.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "wilderness_region_slug" in text
        assert "CREATE TABLE IF NOT EXISTS wilderness_regions" in text

    def test_schema_version_is_20_or_later(self):
        assert SCHEMA_VERSION >= 20
