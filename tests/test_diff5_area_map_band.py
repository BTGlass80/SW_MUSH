"""
test_diff5_area_map_band.py — DIFF.5: threat band field in area_map payload.

Verifies that build_area_map() emits the ``band`` field on each room node:
  - room-level ``threat_band`` in properties wins
  - falls back to zone ``threat_band`` when the room has none
  - defaults to "settled" when neither room nor zone carries the field
  - all four canonical band values pass through unchanged

The band value is used by the web client to add an ``rm-band-{band}``
CSS class for label tinting (frontier=teal, contested-marches=orange,
wilds=red; settled=default amber — no class added).

Uses FakeDB (no real SQLite), mirroring test_area_map_emits_slug.py.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from engine.area_map import build_area_map


class FakeDB:
    """Minimal async DB stub for build_area_map.

    rooms: {room_id: (props_dict, zone_id, [exit dicts])}
    zones: {zone_id: props_dict}
    """

    def __init__(self, rooms: dict, zones: dict | None = None):
        self._rooms = rooms
        self._zones = zones or {}

    async def get_room(self, room_id):
        entry = self._rooms.get(room_id)
        if entry is None:
            return None
        props, zone_id, _exits = entry
        return {
            "id": room_id,
            "name": f"Room {room_id}",
            "properties": json.dumps(props),
            "zone_id": zone_id,
            "map_x": float(room_id),
            "map_y": 0.0,
        }

    async def get_exits(self, room_id):
        entry = self._rooms.get(room_id)
        if entry is None:
            return []
        return list(entry[2])

    async def get_npcs_in_room(self, room_id):
        return []

    async def get_zone(self, zone_id):
        props = self._zones.get(zone_id)
        if props is None:
            return None
        return {
            "id": zone_id,
            "properties": json.dumps(props),
            "parent_id": None,
        }


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _rooms_by_id(am):
    return {r["id"]: r for r in am["rooms"]}


# ─── room-level band ──────────────────────────────────────────────────────────

def test_room_level_frontier():
    db = FakeDB({
        1: ({"threat_band": "frontier", "security": "secure", "environment": "urban"}, None, []),
    })
    am = _run(build_area_map(1, db, depth=1))
    assert _rooms_by_id(am)[1]["band"] == "frontier"


def test_room_level_settled():
    db = FakeDB({
        1: ({"threat_band": "settled", "security": "contested", "environment": "urban"}, None, []),
    })
    am = _run(build_area_map(1, db, depth=1))
    assert _rooms_by_id(am)[1]["band"] == "settled"


def test_room_level_contested_marches():
    db = FakeDB({
        1: ({"threat_band": "contested_marches", "security": "contested", "environment": "wilderness"}, None, []),
    })
    am = _run(build_area_map(1, db, depth=1))
    assert _rooms_by_id(am)[1]["band"] == "contested_marches"


def test_room_level_wilds():
    db = FakeDB({
        1: ({"threat_band": "wilds", "security": "lawless", "environment": "wilderness"}, None, []),
    })
    am = _run(build_area_map(1, db, depth=1))
    assert _rooms_by_id(am)[1]["band"] == "wilds"


# ─── zone fallback ────────────────────────────────────────────────────────────

def test_zone_fallback_when_room_has_no_band():
    db = FakeDB(
        rooms={
            1: ({"security": "contested"}, 10, []),
        },
        zones={
            10: {"threat_band": "wilds"},
        },
    )
    am = _run(build_area_map(1, db, depth=1))
    assert _rooms_by_id(am)[1]["band"] == "wilds"


def test_room_band_wins_over_zone():
    db = FakeDB(
        rooms={
            1: ({"threat_band": "frontier", "security": "secure"}, 10, []),
        },
        zones={
            10: {"threat_band": "wilds"},
        },
    )
    am = _run(build_area_map(1, db, depth=1))
    assert _rooms_by_id(am)[1]["band"] == "frontier"


# ─── default ──────────────────────────────────────────────────────────────────

def test_defaults_to_settled_when_neither_room_nor_zone_has_band():
    db = FakeDB({
        1: ({"security": "contested", "environment": "urban"}, None, []),
    })
    am = _run(build_area_map(1, db, depth=1))
    assert _rooms_by_id(am)[1]["band"] == "settled"


def test_band_field_present_on_all_rooms_in_neighborhood():
    """All rooms in the BFS — current, adj, far — carry the band field."""
    db = FakeDB({
        1: ({"threat_band": "frontier"}, None, [
            {"to_room_id": 2, "direction": "north", "is_hidden": 0},
        ]),
        2: ({"threat_band": "wilds"}, None, [
            {"to_room_id": 3, "direction": "north", "is_hidden": 0},
        ]),
        3: ({"threat_band": "contested_marches"}, None, []),
    })
    am = _run(build_area_map(1, db, depth=2))
    rooms = _rooms_by_id(am)
    assert "band" in rooms[1]
    assert "band" in rooms[2]
    assert "band" in rooms[3]
    assert rooms[1]["band"] == "frontier"
    assert rooms[2]["band"] == "wilds"
    assert rooms[3]["band"] == "contested_marches"
