"""
test_area_map_emits_slug.py — Drop 1 (map click-to-walk) server change.

The web client's click-to-walk bridges the area_map (server DB ids) to the
substrate render cells (map-YAML ids). Room *names* diverge between the two
payloads (short cell names like "Bay 94 Ent" vs long room names like
"Docking Bay 94 - Entrance"), so name-matching resolved nothing and every
cell rendered inert. The fix joins on the stable production *slug*, which is
already what tools/check_map_cardinals.py uses.

This pins that build_area_map() emits ``slug`` on every room dict, and that
the bare command word survives on edges (including vertical exits, which must
remain reachable from the map).

Uses a FakeDB (no real SQLite), mirroring tests/test_fmap2_session_hud.py.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from engine.area_map import build_area_map


class FakeDB:
    """Minimal async DB stub for build_area_map.

    rooms: {room_id: (slug, [exit dicts])}
    Each exit dict: {"to_room_id", "direction", "is_hidden"}.
    """

    def __init__(self, rooms: dict):
        self._rooms = rooms

    async def get_room(self, room_id):
        entry = self._rooms.get(room_id)
        if entry is None:
            return None
        slug, _exits = entry
        return {
            "id": room_id,
            "name": f"Room {room_id} ({slug})",
            "properties": json.dumps({
                "slug": slug,
                # supply env/sec so no zone lookups are needed
                "environment": "urban",
                "security": "secure",
            }),
            "zone_id": None,
            "map_x": float(room_id),     # hand-tuned coords present
            "map_y": 0.0,
        }

    async def get_exits(self, room_id):
        entry = self._rooms.get(room_id)
        if entry is None:
            return []
        return list(entry[1])

    async def get_npcs_in_room(self, room_id):
        return []

    async def get_zone(self, zone_id):
        return {}


def _run(coro):
    """Run a coroutine to completion in a fresh event loop.

    Uses ``asyncio.new_event_loop().run_until_complete`` — the
    ``asyncio.get_event_loop()`` pattern broke in Python 3.14 (see
    BugFix5 / 2026-05-24) and fails in subset runs even on 3.12.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _build():
    db = FakeDB({
        1: ("docking_bay_94_entrance", [
            {"to_room_id": 2, "direction": "north", "is_hidden": 0},
            {"to_room_id": 3, "direction": "down",  "is_hidden": 0},  # vertical
        ]),
        2: ("mos_eisley_street_spaceport_row", []),
        3: ("docking_bay_94_pit", []),
    })
    return _run(build_area_map(1, db, depth=2))


def test_every_room_carries_slug():
    am = _build()
    rooms = {r["id"]: r for r in am["rooms"]}
    assert set(rooms) == {1, 2, 3}, "BFS should discover all three rooms"
    assert rooms[1]["slug"] == "docking_bay_94_entrance"
    assert rooms[2]["slug"] == "mos_eisley_street_spaceport_row"
    assert rooms[3]["slug"] == "docking_bay_94_pit"


def test_slug_key_present_on_all_rooms_even_if_some_lack_it():
    """A room with no slug in properties emits slug=None (never raises),
    so the client can still fall back to name matching for that one cell."""
    db = FakeDB({
        1: ("docking_bay_94_entrance", [
            {"to_room_id": 2, "direction": "east", "is_hidden": 0},
        ]),
        2: ("", []),  # empty slug -> None
    })
    am = _run(build_area_map(1, db, depth=2))
    rooms = {r["id"]: r for r in am["rooms"]}
    assert "slug" in rooms[1] and "slug" in rooms[2]
    assert rooms[1]["slug"] == "docking_bay_94_entrance"
    assert rooms[2]["slug"] in (None, "")  # no slug -> falsy, name fallback


def test_vertical_edge_direction_word_preserved():
    """The 'down' exit must survive as a bare command word so the client
    can make the pit reachable (sendCmd('down'))."""
    am = _build()
    dirs = {(e["from"], e["to"]): e["dir"] for e in am["edges"]}
    # edge between 1 and 3 (dedup may store either orientation)
    pit_dir = dirs.get((1, 3)) or dirs.get((3, 1))
    assert pit_dir is not None, "pit edge missing from area_map"
    assert pit_dir.split()[0] in ("down", "up"), (
        f"expected a vertical command word, got {pit_dir!r}"
    )
