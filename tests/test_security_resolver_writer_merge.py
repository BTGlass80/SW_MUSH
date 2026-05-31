# -*- coding: utf-8 -*-
"""
tests/test_security_resolver_writer_merge.py — Drop S-RES (May 18 2026).

Closes the §6.2 dual-source-drift bug discovered during the May 18
rollup's W-CMB-2/3 development: the room-level ``security_level:`` YAML
field was inert at runtime because ``engine/world_writer.py`` only
persisted ``room.raw["properties"]``, dropping the top-level field.

The fix is a writer-level merge: when ``properties.security`` is
absent and ``security_level`` is set, the top-level field promotes
into properties before the room is written. This test pins the
contract.

Four scenarios:

  1. top-level only       → merged into properties.security
  2. properties only      → unchanged (properties wins)
  3. both set, conflict   → properties wins (the more-specific block
                            is authoritative, mirroring how `slug` is
                            handled at the same write site)
  4. neither set          → no `security` key in the written JSON
                            (rooms default to CONTESTED at the
                            resolver layer)

These tests do not need an aiosqlite DB — they stub the writer's
``db.create_room`` and inspect the JSON payload that would be
written. They drive ``engine.world_writer._write_rooms`` directly so
the harness stays minimal.
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.world_loader import Room  # noqa: E402
from engine.world_writer import _write_rooms  # noqa: E402


class _FakeDB:
    """Minimal stub: records what create_room sees so the test can
    inspect the properties payload."""

    def __init__(self):
        self.rooms_written: list[dict] = []
        self._next_id = 1000

    async def create_room(self, name, desc_short="", desc_long="",
                          zone_id=None, properties="{}"):
        rid = self._next_id
        self._next_id += 1
        self.rooms_written.append({
            "id": rid,
            "name": name,
            "zone_id": zone_id,
            "properties_raw": properties,
            "properties": json.loads(properties),
        })
        return rid

    # _write_rooms also issues an UPDATE for map_x/map_y when set; the
    # test rooms below don't set those, so we don't need to implement
    # `execute`. If a future test sets coords, add it then.


def _make_room(yaml_id: int, slug: str, raw_extra: dict) -> Room:
    raw = {
        "id": yaml_id,
        "slug": slug,
        "name": f"Test Room {yaml_id}",
    }
    raw.update(raw_extra)
    return Room(
        id=yaml_id,
        slug=slug,
        name=raw["name"],
        short_desc="",
        description="A test room.",
        zone="",        # no zone resolution required for these tests
        map_x=None,
        map_y=None,
        planet="test_planet",
        raw=raw,
    )


def _run(coro):
    """Helper to run a coroutine on a fresh event loop. Avoids
    DeprecationWarning from `asyncio.get_event_loop()` in 3.12+."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSecurityLevelWriterMerge(unittest.TestCase):
    """The writer merges top-level ``security_level:`` into
    ``properties.security`` so the engine resolver in
    ``engine/security.py::get_effective_security`` can find it."""

    def _write(self, rooms: list[Room]) -> _FakeDB:
        db = _FakeDB()
        rooms_dict = {r.id: r for r in rooms}
        # No zones map needed: rooms in these tests have zone="" so
        # the zone_ids.get(room.zone) call returns None and zone_id
        # stays None, which create_room accepts.
        _run(_write_rooms(rooms_dict, {}, db))
        return db

    # ─────────────────────────────────────────────────────────────────
    # The four scenarios
    # ─────────────────────────────────────────────────────────────────

    def test_top_level_only_promotes_into_properties(self):
        """Room with `security_level: lawless` and no properties.security
        → written with properties.security == 'lawless'."""
        room = _make_room(
            yaml_id=53,
            slug="jundland_dune_sea_edge",
            raw_extra={"security_level": "lawless"},
        )
        db = self._write([room])
        self.assertEqual(len(db.rooms_written), 1)
        props = db.rooms_written[0]["properties"]
        self.assertEqual(
            props.get("security"),
            "lawless",
            "Top-level security_level: lawless should have been "
            "merged into properties.security. Without this merge "
            "the resolver in engine/security.py defaults the room "
            "to CONTESTED.",
        )

    def test_properties_only_is_passed_through(self):
        """Room with `properties.security: secured` and no top-level
        field → written with properties.security == 'secured'."""
        room = _make_room(
            yaml_id=100,
            slug="jedi_temple_courtyard",
            raw_extra={"properties": {"security": "secured"}},
        )
        db = self._write([room])
        props = db.rooms_written[0]["properties"]
        self.assertEqual(props.get("security"), "secured")

    def test_both_set_properties_wins(self):
        """When both are present (a content authoring artifact),
        properties takes precedence — the more-specific block is
        authoritative. Mirrors how `slug` is handled at the same
        site."""
        room = _make_room(
            yaml_id=200,
            slug="ambiguous_room",
            raw_extra={
                "security_level": "lawless",            # less specific
                "properties": {"security": "secured"},  # wins
            },
        )
        db = self._write([room])
        props = db.rooms_written[0]["properties"]
        self.assertEqual(
            props.get("security"),
            "secured",
            "When both top-level security_level and "
            "properties.security are set, properties wins.",
        )

    def test_neither_set_results_in_no_security_key(self):
        """When a room declares no security at either level, the
        writer must not invent one — the resolver's default
        (CONTESTED) is what should apply."""
        room = _make_room(
            yaml_id=300,
            slug="plain_room",
            raw_extra={},
        )
        db = self._write([room])
        props = db.rooms_written[0]["properties"]
        self.assertNotIn(
            "security",
            props,
            "Writer must not invent a security key for rooms that "
            "declared none. The resolver's default (CONTESTED) is "
            "what should govern.",
        )

    # ─────────────────────────────────────────────────────────────────
    # Coverage of all three documented values
    # ─────────────────────────────────────────────────────────────────

    def test_all_three_values_round_trip(self):
        """lawless, contested, secured all promote correctly."""
        rooms = [
            _make_room(1, "a", {"security_level": "lawless"}),
            _make_room(2, "b", {"security_level": "contested"}),
            _make_room(3, "c", {"security_level": "secured"}),
        ]
        db = self._write(rooms)
        values = sorted(
            r["properties"].get("security") for r in db.rooms_written
        )
        self.assertEqual(values, ["contested", "lawless", "secured"])

    # ─────────────────────────────────────────────────────────────────
    # The slug-coexistence guard: this site already merges `slug`.
    # Make sure the new security merge doesn't clobber that.
    # ─────────────────────────────────────────────────────────────────

    def test_slug_and_security_coexist(self):
        """The pre-existing slug merge and the new security merge
        live in the same block — neither should interfere with the
        other."""
        room = _make_room(
            yaml_id=500,
            slug="my_slug_room",
            raw_extra={"security_level": "secured"},
        )
        db = self._write([room])
        props = db.rooms_written[0]["properties"]
        self.assertEqual(props.get("slug"), "my_slug_room")
        self.assertEqual(props.get("security"), "secured")


if __name__ == "__main__":
    unittest.main()
