# -*- coding: utf-8 -*-
"""
F.0 Drop 4 Pass A — Integration test for the YAML-driven world build.

Covers the cutover: build_mos_eisley.build() now loads zones/rooms/exits
from data/worlds/gcw/ via engine.world_loader + engine.world_writer instead
of executing the legacy ROOMS / EXITS / ROOM_ZONES / ROOM_OVERRIDES / MAP_COORDS
literals. The literals stay in source as unreachable dead code; Pass B will
remove them.

The invariants that matter:
  - Zone count + parent links preserved (top-level zones have NULL parent_id)
  - Room count includes the 3 schema-seeded rooms + 120 YAML rooms + ship bridges
  - Critical positional anchors (rooms referenced by NPC / ship / seed-link
    code by their `room_ids[i]` index) resolve to the right names in the DB
  - Map coordinates flow through (writer applies map_x/map_y from YAML)
  - Exit count is at minimum (240 yaml pairs + 4 seed defaults + seed-link adds)

This test runs the full build() — including NPCs, hireable crew, ships, and
test character — to verify that downstream code keeps working when the locals
`zones` and `room_ids` come from WriteResult instead of inline literals.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os

import aiosqlite
import pytest

from build_mos_eisley import build


# Module-scoped fixture: build the world once, query many. build() is the
# expensive operation here (~10s); spreading it across N tests would multiply
# total runtime for no extra coverage.
@pytest.fixture(scope="module")
def built_db_path(tmp_path_factory):
    """Run build() once and return the resulting DB path for read-only queries."""
    db_path = str(tmp_path_factory.mktemp("pass_a") / "world.db")

    async def _do_build():
        # Suppress build()'s ~150 lines of progress output so test logs stay clean.
        with contextlib.redirect_stdout(io.StringIO()):
            await build(db_path=db_path)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_do_build())
    return db_path


# Helper: open the built DB read-only and run a single SELECT.
async def _query(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(sql, params)).fetchall()
        return [dict(r) for r in rows]


def _q(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    """Sync wrapper around _query for the test body."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_query(db_path, sql, params))
    finally:
        loop.close()


class TestPassACutover:
    """Verify the YAML-driven build path produces an equivalent DB."""

    def test_zone_count_matches_yaml(self, built_db_path):
        # 20 zones in data/worlds/gcw/zones.yaml. No zones are seeded by
        # Database.initialize(), so the writer-written zones are all of them.
        rows = _q(built_db_path, "SELECT COUNT(*) AS c FROM zones")
        assert rows[0]["c"] == 20

    def test_room_count_at_minimum(self, built_db_path):
        # 3 schema-seeded rooms + 120 YAML rooms = 123 baseline. Ship bridges
        # add 7 more (one per docked ship), giving 130. Be tolerant of future
        # ship additions; assert the floor.
        rows = _q(built_db_path, "SELECT COUNT(*) AS c FROM rooms")
        assert rows[0]["c"] >= 123, (
            f"Expected at least 123 rooms (3 seed + 120 yaml), got {rows[0]['c']}"
        )

    def test_yaml_id_zero_room_present_with_coords(self, built_db_path):
        # The handoff calls out yaml_id=0 -> 'Docking Bay 94 - Entrance' as
        # the canonical positional anchor. Map coords come from the YAML
        # via engine.world_writer (not the legacy MAP_COORDS apply loop,
        # which Pass A removed).
        rows = _q(
            built_db_path,
            "SELECT name, map_x, map_y FROM rooms WHERE name = ?",
            ("Docking Bay 94 - Entrance",),
        )
        assert len(rows) == 1
        r = rows[0]
        assert abs(r["map_x"] - 0.15) < 1e-6, f"map_x: got {r['map_x']}"
        assert abs(r["map_y"] - 0.48) < 1e-6, f"map_y: got {r['map_y']}"

    def test_zone_parent_links_preserved(self, built_db_path):
        # 'Mos Eisley' is top-level; 'Spaceport District' is its child.
        # The writer's topological zone insertion must preserve this.
        me = _q(
            built_db_path,
            "SELECT id, parent_id FROM zones WHERE name = ?",
            ("Mos Eisley",),
        )
        assert len(me) == 1
        assert me[0]["parent_id"] is None, "Top-level zone has unexpected parent"

        sp = _q(
            built_db_path,
            "SELECT parent_id FROM zones WHERE name = ?",
            ("Spaceport District",),
        )
        assert len(sp) == 1
        assert sp[0]["parent_id"] == me[0]["id"], (
            "Spaceport District should be a child of Mos Eisley"
        )

    def test_critical_positional_anchors_present(self, built_db_path):
        # These rooms are referenced positionally by downstream code in
        # build_mos_eisley.py (NPC placement, ship docking, seed-room linking).
        # If any of them are missing, the cutover is broken.
        anchors = [
            ("Mos Eisley Street - Spaceport Row",   "yaml_id=7,  seed-link target"),
            ("Mos Eisley Street - Market District", "yaml_id=8,  seed-link target"),
            ("Chalmun's Cantina - Entrance",        "yaml_id=12, seed-link target"),
            ("Jundland Wastes - Dune Sea Edge",     "yaml_id=53, last Tatooine room"),
            ("Coronet City - Venn Kator's Forge",   "yaml_id=119, last YAML room"),
        ]
        for name, why in anchors:
            rows = _q(built_db_path, "SELECT 1 FROM rooms WHERE name = ?", (name,))
            assert len(rows) == 1, f"Anchor missing: {name!r} ({why})"

    def test_exit_count_at_minimum(self, built_db_path):
        # 120 YAML exits × 2 (forward + reverse) = 240 writer-added rows.
        # 4 seed defaults from Database.initialize() (room 1 north→2, etc.).
        # Plus seed-link extras: build_mos_eisley adds 6 more, but 2 of them
        # collide with existing seed exits and get silently skipped — see
        # db.create_exit dup-detection. So baseline is 240 + 4 + 4 = 248.
        # Ship board/disembark add 2 per docked ship (~14). Be tolerant.
        rows = _q(built_db_path, "SELECT COUNT(*) AS c FROM exits")
        assert rows[0]["c"] >= 244, (
            f"Expected at least 244 exits, got {rows[0]['c']}"
        )

    def test_room_zone_assignments_resolved(self, built_db_path):
        # Every YAML room is assigned to a zone (via writer). Sample-check
        # a known room's zone.
        rows = _q(
            built_db_path,
            """SELECT r.name, z.name AS zone_name
               FROM rooms r
               LEFT JOIN zones z ON r.zone_id = z.id
               WHERE r.name = ?""",
            ("Docking Bay 94 - Entrance",),
        )
        assert len(rows) == 1
        assert rows[0]["zone_name"] == "Spaceport District", (
            f"Expected Spaceport District, got {rows[0]['zone_name']}"
        )

    def test_room_properties_persisted(self, built_db_path):
        # The writer serializes Room.properties to JSON via db.create_room.
        # Spot-check one room with a known cover_max override.
        rows = _q(
            built_db_path,
            "SELECT properties FROM rooms WHERE name = ?",
            ("Docking Bay 94 - Pit Floor",),
        )
        assert len(rows) == 1
        # cover_max for Pit Floor is set in zones.yaml via the spaceport
        # zone defaults; the room may inherit or override. Just confirm the
        # field is non-empty JSON.
        props = rows[0]["properties"]
        assert props and props != "{}" and props != "null", (
            f"Pit Floor properties should be non-empty JSON: {props!r}"
        )
