# -*- coding: utf-8 -*-
"""
tests/test_world_writer.py — Drop 3 of Priority F.0.

Exercises engine.world_writer.write_world_bundle against an in-memory
SQLite DB and verifies that:

1. The writer succeeds without raising and returns a WriteResult.
2. Zone count / room count / exit row count match expected values
   (driven off the loaded bundle, which is verified independently
   in tests/test_world_loader_gcw.py).
3. Zones are written with display names matching zones.yaml's
   `name` field, and parent links resolve to the right zone DB id.
4. Rooms are written with the correct zone_id and the YAML id-space
   maps cleanly to the DB id-space via WriteResult.room_id_for_yaml_id.
5. Map coordinates flow through the update_room call.
6. Each exit pair produces two DB rows (forward + reverse) with the
   right (direction, name) split per `_split_exit`.
7. The split helper handles "north" / "north to Foo" / custom keyword
   forms identically to build_mos_eisley._split_exit.
8. build_rooms_manifest produces a stable, sorted slug→id manifest.

Drop 4 (boot wire-up) will gate on this test passing — it's the
contract the cutover code must satisfy before replacing the legacy
build path.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.world_loader import load_world_dry_run
from engine.world_writer import (
    write_world_bundle,
    build_rooms_manifest,
    _split_exit,
)


# ── Event loop fixture (Python 3.14 compatibility) ─────────────────────────────
# Same pattern as tests/test_plots.py — aiosqlite connections are loop-bound,
# so a module-scoped loop keeps the fixture's connection on the same loop as
# the test bodies.

@pytest.fixture(scope="module")
def event_loop_for_tests():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def gcw_bundle():
    return load_world_dry_run("gcw")


@pytest.fixture(scope="module")
def write_result(event_loop_for_tests, gcw_bundle):
    """Connect a fresh in-memory DB, init schema, write the bundle.

    Module-scoped so the writer runs once and all assertions inspect
    the same DB state. Tests must NOT mutate the DB.
    """
    from db.database import Database

    async def _setup():
        db = Database(":memory:")
        await db.connect()
        await db.initialize()
        result = await write_world_bundle(gcw_bundle, db)
        return db, result

    db, result = event_loop_for_tests.run_until_complete(_setup())
    yield (db, result)
    event_loop_for_tests.run_until_complete(db._db.close())


# ─────────────────────────────────────────────────────────────────────────────
# _split_exit unit tests — must match build_mos_eisley._split_exit
# ─────────────────────────────────────────────────────────────────────────────


class TestSplitExit:
    def test_compass_only(self):
        assert _split_exit("north") == ("north", "")

    def test_compass_with_to_label(self):
        assert _split_exit("north to Beggar's Canyon") == ("north", "Beggar's Canyon")

    def test_compass_label_without_to_word(self):
        # If "to " isn't the leading prefix, the rest is the label as-is
        assert _split_exit("south Landing Pad") == ("south", "Landing Pad")

    def test_custom_keyword(self):
        assert _split_exit("board") == ("board", "")

    def test_uppercase_compass_normalized(self):
        assert _split_exit("NORTH") == ("north", "")

    def test_extra_whitespace_stripped(self):
        assert _split_exit("  east  ") == ("east", "")

    def test_empty_string(self):
        assert _split_exit("") == ("", "")

    # NOTE: an earlier `test_match_against_build_script_helper` test
    # pinned parity between this module's `_split_exit` and a copy in
    # `build_mos_eisley.py`. Pass B deleted the build-script copy along
    # with the legacy literals it served, so the parity check has no
    # second side to compare against and was removed in Pass B. The
    # tests above already validate this `_split_exit` independently.


# ─────────────────────────────────────────────────────────────────────────────
# Write succeeds and result counts match the bundle
# ─────────────────────────────────────────────────────────────────────────────


class TestWriteResultShape:
    def test_zone_count_matches_bundle(self, write_result, gcw_bundle):
        _, result = write_result
        assert result.zones_written == len(gcw_bundle.zones)
        assert result.zones_written == 20

    def test_room_count_matches_bundle(self, write_result, gcw_bundle):
        _, result = write_result
        assert result.rooms_written == len(gcw_bundle.rooms)
        assert result.rooms_written == 120

    def test_yaml_to_db_map_covers_all_rooms(self, write_result, gcw_bundle):
        _, result = write_result
        assert set(result.room_id_for_yaml_id.keys()) == set(gcw_bundle.rooms.keys())

    def test_room_ids_are_distinct(self, write_result):
        _, result = write_result
        assert len(set(result.room_ids.values())) == len(result.room_ids)

    def test_zone_ids_are_distinct(self, write_result):
        _, result = write_result
        assert len(set(result.zone_ids.values())) == len(result.zone_ids)

    def test_exit_rows_written(self, write_result, gcw_bundle):
        _, result = write_result
        # Each YAML exit pair should produce 2 DB rows (fwd + rev),
        # except where the reverse string is empty. None of the GCW
        # exits today have empty reverse strings, so 120 pairs → 240
        # rows. Assert == 2 × pair count.
        assert result.exits_written == 2 * len(gcw_bundle.exits)
        assert result.exits_written == 240


# ─────────────────────────────────────────────────────────────────────────────
# DB-level assertions — query the in-memory DB to verify the writes landed
# ─────────────────────────────────────────────────────────────────────────────


class TestDbContent:
    def test_zone_count_in_db(self, write_result, event_loop_for_tests):
        db, _ = write_result
        async def _q():
            rows = await db._db.execute_fetchall("SELECT COUNT(*) AS n FROM zones")
            return rows[0]["n"]
        n = event_loop_for_tests.run_until_complete(_q())
        assert n == 20

    def test_room_count_in_db(self, write_result, event_loop_for_tests):
        # `Database.initialize()` seeds 3 rooms (Landing Pad, Mos Eisley
        # Street, Cantina) before the writer runs, so the total count is
        # 123 = 3 seeds + 120 writer-added. We assert the writer-added
        # count by querying for IDs we tracked, not the table total.
        db, result = write_result
        written_ids = list(result.room_id_for_yaml_id.values())
        placeholders = ",".join("?" * len(written_ids))
        async def _q():
            rows = await db._db.execute_fetchall(
                f"SELECT COUNT(*) AS n FROM rooms WHERE id IN ({placeholders})",
                written_ids,
            )
            return rows[0]["n"]
        n = event_loop_for_tests.run_until_complete(_q())
        assert n == 120

    def test_exit_count_in_db(self, write_result, event_loop_for_tests):
        # Same correction: the seed schema inserts 4 exits before the
        # writer runs. We count writer-added exits by filtering on
        # from_room_id ∈ writer's room set.
        db, result = write_result
        written_room_ids = list(result.room_id_for_yaml_id.values())
        placeholders = ",".join("?" * len(written_room_ids))
        async def _q():
            rows = await db._db.execute_fetchall(
                f"SELECT COUNT(*) AS n FROM exits "
                f"WHERE from_room_id IN ({placeholders})",
                written_room_ids,
            )
            return rows[0]["n"]
        n = event_loop_for_tests.run_until_complete(_q())
        assert n == 240

    def test_zone_parent_links_resolve(self, write_result, event_loop_for_tests):
        db, result = write_result
        async def _q():
            rows = await db._db.execute_fetchall(
                "SELECT name, parent_id FROM zones WHERE name = ?",
                ("Spaceport District",))
            return rows[0] if rows else None
        row = event_loop_for_tests.run_until_complete(_q())
        assert row is not None
        # Spaceport's parent should be Mos Eisley
        assert row["parent_id"] == result.zone_ids["mos_eisley"]

    def test_top_level_zones_have_no_parent(self, write_result, event_loop_for_tests):
        db, _ = write_result
        async def _q():
            return await db._db.execute_fetchall(
                "SELECT name FROM zones WHERE parent_id IS NULL "
                "ORDER BY name")
        rows = event_loop_for_tests.run_until_complete(_q())
        names = {r["name"] for r in rows}
        # Top-level zones per build_mos_eisley:
        # mos_eisley, wastes (Tatooine roots), ns_landing_pad,
        # kessel_station, coronet_port
        assert "Mos Eisley" in names
        assert "Jundland Wastes" in names
        assert "Nar Shaddaa Landing Pads" in names
        assert "Kessel Station" in names
        assert "Coronet Port District" in names

    def test_room_zone_assignment(self, write_result, event_loop_for_tests):
        db, result = write_result
        # Room 0 (Docking Bay 94 - Entrance) is in zone "spaceport".
        async def _q():
            rid = result.room_id_for_yaml_id[0]
            rows = await db._db.execute_fetchall(
                "SELECT zone_id, name FROM rooms WHERE id = ?", (rid,))
            return rows[0] if rows else None
        row = event_loop_for_tests.run_until_complete(_q())
        assert row is not None
        assert row["name"] == "Docking Bay 94 - Entrance"
        assert row["zone_id"] == result.zone_ids["spaceport"]

    def test_room_properties_persisted(self, write_result, event_loop_for_tests):
        db, result = write_result
        # Room 1 (Pit Floor) has `cover_max: 4` from ROOM_OVERRIDES.
        async def _q():
            rid = result.room_id_for_yaml_id[1]
            rows = await db._db.execute_fetchall(
                "SELECT properties FROM rooms WHERE id = ?", (rid,))
            return rows[0]["properties"] if rows else None
        props_str = event_loop_for_tests.run_until_complete(_q())
        assert props_str is not None
        props = json.loads(props_str)
        assert props.get("cover_max") == 4

    def test_room_map_coords_persisted(self, write_result, event_loop_for_tests):
        db, result = write_result
        # Room 0: MAP_COORDS[0] = (0.15, 0.48)
        async def _q():
            rid = result.room_id_for_yaml_id[0]
            rows = await db._db.execute_fetchall(
                "SELECT map_x, map_y FROM rooms WHERE id = ?", (rid,))
            return rows[0] if rows else None
        row = event_loop_for_tests.run_until_complete(_q())
        assert row is not None
        assert row["map_x"] == pytest.approx(0.15, abs=1e-6)
        assert row["map_y"] == pytest.approx(0.48, abs=1e-6)

    def test_exit_pairs_bidirectional(self, write_result, event_loop_for_tests):
        db, result = write_result
        # First EXITS entry: (0, 1, 'down', 'up')
        rid_0 = result.room_id_for_yaml_id[0]
        rid_1 = result.room_id_for_yaml_id[1]
        async def _q():
            fwd = await db._db.execute_fetchall(
                "SELECT direction FROM exits WHERE from_room_id = ? AND to_room_id = ?",
                (rid_0, rid_1))
            rev = await db._db.execute_fetchall(
                "SELECT direction FROM exits WHERE from_room_id = ? AND to_room_id = ?",
                (rid_1, rid_0))
            return fwd, rev
        fwd, rev = event_loop_for_tests.run_until_complete(_q())
        assert len(fwd) == 1
        assert fwd[0]["direction"] == "down"
        assert len(rev) == 1
        assert rev[0]["direction"] == "up"

    def test_exit_with_label_split_correctly(self, write_result, gcw_bundle,
                                              event_loop_for_tests):
        # Find an exit in the loaded bundle that has a "to <name>" label
        # in either direction. (Pre-Pass-B this scanned
        # `build_mos_eisley.EXITS`; post-Pass-B that literal is gone, so
        # we use the bundle directly.)
        labeled = [e for e in gcw_bundle.exits
                   if " to " in e.forward.lower() or " to " in e.reverse.lower()]
        assert labeled, "No labeled exits found in GCW bundle - test sanity"
        e = labeled[0]
        from_idx, to_idx, fwd_raw, rev_raw = e.from_id, e.to_id, e.forward, e.reverse
        db, result = write_result
        rid_from = result.room_id_for_yaml_id[from_idx]
        rid_to = result.room_id_for_yaml_id[to_idx]
        # Resolve which side has the label
        fwd_key, fwd_label = _split_exit(fwd_raw)
        rev_key, rev_label = _split_exit(rev_raw)
        async def _q():
            fwd = await db._db.execute_fetchall(
                "SELECT direction, name FROM exits WHERE from_room_id = ? AND to_room_id = ?",
                (rid_from, rid_to))
            rev = await db._db.execute_fetchall(
                "SELECT direction, name FROM exits WHERE from_room_id = ? AND to_room_id = ?",
                (rid_to, rid_from))
            return fwd, rev
        fwd_rows, rev_rows = event_loop_for_tests.run_until_complete(_q())
        assert len(fwd_rows) == 1
        assert fwd_rows[0]["direction"] == fwd_key
        assert (fwd_rows[0]["name"] or "") == fwd_label
        assert len(rev_rows) == 1
        assert rev_rows[0]["direction"] == rev_key
        assert (rev_rows[0]["name"] or "") == rev_label


# ─────────────────────────────────────────────────────────────────────────────
# rooms_manifest helper
# ─────────────────────────────────────────────────────────────────────────────


class TestRoomsManifest:
    def test_manifest_shape(self, write_result):
        _, result = write_result
        manifest = build_rooms_manifest(result)
        assert manifest["schema_version"] == 1
        assert isinstance(manifest["rooms"], dict)
        assert isinstance(manifest["by_id"], dict)

    def test_manifest_room_count(self, write_result):
        _, result = write_result
        manifest = build_rooms_manifest(result)
        assert len(manifest["rooms"]) == 120
        assert len(manifest["by_id"]) == 120

    def test_manifest_round_trips(self, write_result):
        _, result = write_result
        manifest = build_rooms_manifest(result)
        # Every slug in rooms should round-trip through by_id
        for slug, db_id in manifest["rooms"].items():
            assert manifest["by_id"][str(db_id)] == slug

    def test_manifest_known_anchor(self, write_result):
        _, result = write_result
        manifest = build_rooms_manifest(result)
        # docking_bay_94_entrance is the anchor room (yaml_id 0).
        assert "docking_bay_94_entrance" in manifest["rooms"]
        anchor_db_id = manifest["rooms"]["docking_bay_94_entrance"]
        assert anchor_db_id == result.room_id_for_yaml_id[0]


# ─────────────────────────────────────────────────────────────────────────────
# Defensive: writer refuses unvalidated bundles
# ─────────────────────────────────────────────────────────────────────────────


class TestRefusesUnvalidated:
    def test_rejects_bundle_with_errors(self, event_loop_for_tests, gcw_bundle):
        from db.database import Database
        # Construct a fake-broken bundle by injecting an error.
        bundle = gcw_bundle
        original_errors = list(bundle.report.errors)
        bundle.report.errors.append("synthetic test failure")
        try:
            async def _try():
                db = Database(":memory:")
                await db.connect()
                await db.initialize()
                with pytest.raises(ValueError, match="unvalidated"):
                    await write_world_bundle(bundle, db)
                await db._db.close()
            event_loop_for_tests.run_until_complete(_try())
        finally:
            # Restore for any later test
            bundle.report.errors[:] = original_errors
