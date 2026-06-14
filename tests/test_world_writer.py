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

pytestmark = pytest.mark.slow  # heavy: full world build (build_mos_eisley / load_world_dry_run)

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
def world_bundle():
    return load_world_dry_run("clone_wars")


@pytest.fixture(scope="module")
def write_result(event_loop_for_tests, world_bundle):
    """Connect a fresh in-memory DB, init schema, write the bundle.

    Module-scoped so the writer runs once and all assertions inspect
    the same DB state. Tests must NOT mutate the DB.
    """
    from db.database import Database

    async def _setup():
        db = Database(":memory:")
        await db.connect()
        await db.initialize()
        result = await write_world_bundle(world_bundle, db)
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
    def test_zone_count_matches_bundle(self, write_result, world_bundle):
        _, result = write_result
        assert result.zones_written == len(world_bundle.zones)

    def test_room_count_matches_bundle(self, write_result, world_bundle):
        _, result = write_result
        assert result.rooms_written == len(world_bundle.rooms)

    def test_yaml_to_db_map_covers_all_rooms(self, write_result, world_bundle):
        _, result = write_result
        assert set(result.room_id_for_yaml_id.keys()) == set(world_bundle.rooms.keys())

    def test_room_ids_are_distinct(self, write_result):
        _, result = write_result
        assert len(set(result.room_ids.values())) == len(result.room_ids)

    def test_zone_ids_are_distinct(self, write_result):
        _, result = write_result
        assert len(set(result.zone_ids.values())) == len(result.zone_ids)

    def test_exit_rows_written(self, write_result, world_bundle):
        _, result = write_result
        # Each YAML exit pair should produce 2 DB rows (fwd + rev),
        # except where the reverse string is empty. Assert == 2 ×
        # pair count, derived from the bundle (era-agnostic).
        assert result.exits_written == 2 * len(world_bundle.exits)


# ─────────────────────────────────────────────────────────────────────────────
# DB-level assertions — query the in-memory DB to verify the writes landed
# ─────────────────────────────────────────────────────────────────────────────


class TestDbContent:
    def test_zone_count_in_db(self, write_result, event_loop_for_tests):
        db, result = write_result
        async def _q():
            rows = await db._db.execute_fetchall("SELECT COUNT(*) AS n FROM zones")
            return rows[0]["n"]
        n = event_loop_for_tests.run_until_complete(_q())
        # No seed zones precede the writer, so total == writer-written.
        assert n == result.zones_written

    def test_room_count_in_db(self, write_result, event_loop_for_tests):
        # `Database.initialize()` seeds a few rooms before the writer
        # runs, so the table total exceeds the writer's output. We
        # assert the writer-added count by querying the IDs we tracked,
        # not the table total.
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
        assert n == len(written_ids)

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
        assert n == result.exits_written

    def test_zone_parent_links_resolve(self, write_result, event_loop_for_tests):
        db, _ = write_result
        async def _q():
            return await db._db.execute_fetchall("SELECT id, parent_id FROM zones")
        rows = event_loop_for_tests.run_until_complete(_q())
        ids = {r["id"] for r in rows}
        # Every non-null parent_id must resolve to a real zone row (the
        # writer turns slug parents into DB ids). Era-agnostic: holds
        # whether the world is flat or hierarchical.
        for r in rows:
            if r["parent_id"] is not None:
                assert r["parent_id"] in ids

    def test_top_level_zones_have_no_parent(self, write_result, event_loop_for_tests):
        db, _ = write_result
        async def _q():
            return await db._db.execute_fetchall(
                "SELECT COUNT(*) AS n FROM zones WHERE parent_id IS NULL")
        rows = event_loop_for_tests.run_until_complete(_q())
        # At least one root zone (null parent) must exist.
        assert rows[0]["n"] >= 1

    def test_room_zone_assignment(self, write_result, world_bundle, event_loop_for_tests):
        db, result = write_result
        # Room 0 is the anchor; derive its expected name + zone slug
        # from the bundle (era-agnostic).
        expected_name = world_bundle.rooms[0].name
        expected_zone_slug = world_bundle.rooms[0].zone
        async def _q():
            rid = result.room_id_for_yaml_id[0]
            rows = await db._db.execute_fetchall(
                "SELECT zone_id, name FROM rooms WHERE id = ?", (rid,))
            return rows[0] if rows else None
        row = event_loop_for_tests.run_until_complete(_q())
        assert row is not None
        assert row["name"] == expected_name
        assert row["zone_id"] == result.zone_ids[expected_zone_slug]

    def test_room_map_coords_persisted(self, write_result, world_bundle, event_loop_for_tests):
        db, result = write_result
        expected_x = world_bundle.rooms[0].map_x
        expected_y = world_bundle.rooms[0].map_y
        async def _q():
            rid = result.room_id_for_yaml_id[0]
            rows = await db._db.execute_fetchall(
                "SELECT map_x, map_y FROM rooms WHERE id = ?", (rid,))
            return rows[0] if rows else None
        row = event_loop_for_tests.run_until_complete(_q())
        assert row is not None
        assert row["map_x"] == pytest.approx(expected_x, abs=1e-6)
        assert row["map_y"] == pytest.approx(expected_y, abs=1e-6)

    def test_exit_pairs_bidirectional(self, write_result, world_bundle, event_loop_for_tests):
        db, result = write_result
        # Derive the first exit pair from the bundle (era-agnostic).
        e0 = world_bundle.exits[0]
        rid_a = result.room_id_for_yaml_id[e0.from_id]
        rid_b = result.room_id_for_yaml_id[e0.to_id]
        fwd_dir, _lbl_f = _split_exit(e0.forward)
        rev_dir, _lbl_r = _split_exit(e0.reverse)
        async def _q():
            fwd = await db._db.execute_fetchall(
                "SELECT direction FROM exits WHERE from_room_id = ? AND to_room_id = ?",
                (rid_a, rid_b))
            rev = await db._db.execute_fetchall(
                "SELECT direction FROM exits WHERE from_room_id = ? AND to_room_id = ?",
                (rid_b, rid_a))
            return fwd, rev
        fwd, rev = event_loop_for_tests.run_until_complete(_q())
        assert len(fwd) == 1
        assert fwd[0]["direction"] == fwd_dir
        assert len(rev) == 1
        assert rev[0]["direction"] == rev_dir

    def test_exit_with_label_split_correctly(self, write_result, world_bundle,
                                              event_loop_for_tests):
        # Find an exit in the loaded bundle that has a "to <name>" label
        # in either direction. (Pre-Pass-B this scanned
        # `build_mos_eisley.EXITS`; post-Pass-B that literal is gone, so
        # we use the bundle directly.)
        labeled = [e for e in world_bundle.exits
                   if " to " in e.forward.lower() or " to " in e.reverse.lower()]
        assert labeled, "No labeled exits found in world bundle - test sanity"
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
        # 287 = 280 pre-Lane-D + 7 Geonosis arc rooms (Gladiator Barracks
        # interior zone + E'Y-Akh anchors), 2026-06-07 drop.
        assert len(manifest["rooms"]) == 287
        assert len(manifest["by_id"]) == 287

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
    def test_rejects_bundle_with_errors(self, event_loop_for_tests, world_bundle):
        from db.database import Database
        # Construct a fake-broken bundle by injecting an error.
        bundle = world_bundle
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


# ─────────────────────────────────────────────────────────────────────────────
# CRAFT.breaching_obstacle_placement (2026-06-13) — world-seeded breachables
# ─────────────────────────────────────────────────────────────────────────────


class TestBreachables:
    """The `breachables:` world-data seeding path: authored obstacles land
    as `breachable` objects, idempotently."""

    # The 3 obstacles authored across the CW world (Geonosis / Nar Shaddaa
    # / Tatooine). Keyed by room slug -> (object name, breach_difficulty).
    EXPECTED = {
        "barracks_armory": ("Mark-locked armory grate", 22),
        "warrens_collapsed_plaza": ("Rubble-choked Evocii doorway", 18),
        "jundland_hidden_cave": ("Tumbled-boulder screen", 15),
    }

    def test_authored_breachables_in_db(self, write_result,
                                        event_loop_for_tests):
        import json as _j
        db, result = write_result
        for slug, (name, diff) in self.EXPECTED.items():
            room_id = result.room_ids.get(slug)
            assert room_id is not None, f"{slug} not written"
            async def _q(rid=room_id):
                return await db._db.execute_fetchall(
                    "SELECT name, data FROM objects "
                    "WHERE type = 'breachable' AND room_id = ?", (rid,))
            rows = event_loop_for_tests.run_until_complete(_q())
            names = [r["name"] for r in rows]
            assert name in names, f"{slug}: {name!r} not seeded (got {names})"
            row = next(r for r in rows if r["name"] == name)
            data = _j.loads(row["data"])
            assert int(data["breach_difficulty"]) == diff
            assert data.get("reveal")  # has reveal flavor

    def test_seeding_is_idempotent(self, write_result, event_loop_for_tests):
        # Re-running _write_breachables must NOT duplicate obstacles.
        from engine.world_writer import _write_breachables
        db, result = write_result

        async def _count():
            rows = await db._db.execute_fetchall(
                "SELECT COUNT(*) AS n FROM objects WHERE type = 'breachable'")
            return rows[0]["n"]

        before = event_loop_for_tests.run_until_complete(_count())
        # Re-run the seeding against the already-seeded DB.
        from db.database import Database  # noqa: F401 (clarity)
        # We need the same bundle the fixture used; reload (module-cached).
        from engine.world_loader import load_world_dry_run
        bundle = load_world_dry_run("clone_wars")
        written = event_loop_for_tests.run_until_complete(
            _write_breachables(bundle.rooms, result.room_ids, db))
        after = event_loop_for_tests.run_until_complete(_count())
        assert written == 0, "re-seed should write 0 (dedup)"
        assert after == before, "re-seed must not duplicate obstacles"
