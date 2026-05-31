# -*- coding: utf-8 -*-
"""
tests/test_security_resolver_runtime.py — Drop S-RES (May 18 2026).

Companion to test_security_resolver_writer_merge.py: that test pins
the JSON the writer hands to ``create_room``; this test pins the
*runtime* round-trip — write a room with top-level ``security_level:
lawless`` through the real ``engine.world_writer._write_rooms`` into
an in-memory aiosqlite DB, then ask ``engine.security.get_effective_security``
what it resolves to and confirm SecurityLevel.LAWLESS.

This is the end-to-end smoke that the resolver bug is closed. The
writer-merge test pins the contract at the JSON layer; this test
pins it at the resolver layer. If a future refactor moves the
merge somewhere else, the writer-merge test may break but this one
should keep working — and vice-versa. Both surfaces matter.

Why a separate file: this test imports aiosqlite and runs migrations,
which costs more than the unit-test file's stubbed harness. Keeping
the unit suite cheap matters for CI iteration speed.
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.database import Database  # noqa: E402
from engine.world_loader import Room  # noqa: E402
from engine.world_writer import _write_rooms  # noqa: E402
from engine.security import (  # noqa: E402
    get_effective_security,
    SecurityLevel,
    clear_all_overrides,
)


def _run(coro):
    """Run a coroutine on a fresh event loop. Avoids 3.12+
    DeprecationWarning from get_event_loop()."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
        zone="",
        map_x=None,
        map_y=None,
        planet="test_planet",
        raw=raw,
    )


async def _setup_db_with_rooms(rooms: list[Room]) -> tuple[Database, dict]:
    """Spin up an in-memory DB, run migrations, and write the rooms
    through ``_write_rooms``. Returns (db, slug→db_id map).

    Director globals (set_security_override, env overrides) are
    cleared so this test is hermetic — without this, a prior test
    that set a transient override could leak into our resolver
    assertions.
    """
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    clear_all_overrides()
    rooms_dict = {r.id: r for r in rooms}
    slug_to_id, _, _ = await _write_rooms(rooms_dict, {}, db)
    return db, slug_to_id


class TestSecurityResolverRuntime(unittest.TestCase):
    """End-to-end: top-level YAML field → writer → DB →
    get_effective_security() → correct SecurityLevel."""

    def setUp(self):
        # Defense-in-depth: clear overrides between tests.
        clear_all_overrides()

    def tearDown(self):
        clear_all_overrides()

    def _check(self, security_level_value: str,
               expected: SecurityLevel) -> None:
        room = _make_room(
            yaml_id=1,
            slug="sentinel_room",
            raw_extra={"security_level": security_level_value},
        )

        async def _go():
            db, slug_to_id = await _setup_db_with_rooms([room])
            room_id = slug_to_id["sentinel_room"]

            # Layer 1: the DB property accessor sees the merged value.
            raw = await db.get_room_property(room_id, "security")
            self.assertEqual(
                raw, security_level_value,
                f"db.get_room_property('security') should return "
                f"{security_level_value!r}; got {raw!r}. "
                f"The writer-level merge did not persist "
                f"security_level into properties.security.",
            )

            # Layer 2: the public resolver returns the right enum.
            sec = await get_effective_security(room_id, db, character=None)
            self.assertEqual(
                sec, expected,
                f"get_effective_security should resolve {security_level_value!r} "
                f"as {expected.value}; got {sec.value}.",
            )

        _run(_go())

    # ─────────────────────────────────────────────────────────────────
    # The three documented values
    # ─────────────────────────────────────────────────────────────────

    def test_lawless_resolves_correctly(self):
        """The sentinel case: CW Tatooine room 53
        (jundland_dune_sea_edge) declares security_level: lawless.
        After the writer fix, it must resolve as LAWLESS at runtime."""
        self._check("lawless", SecurityLevel.LAWLESS)

    def test_secured_resolves_correctly(self):
        self._check("secured", SecurityLevel.SECURED)

    def test_contested_resolves_correctly(self):
        self._check("contested", SecurityLevel.CONTESTED)

    # ─────────────────────────────────────────────────────────────────
    # The undeclared case: default CONTESTED still applies
    # ─────────────────────────────────────────────────────────────────

    def test_undeclared_room_defaults_to_contested(self):
        """A room with no security at either level falls through to
        the resolver's default — CONTESTED. The writer must NOT
        inject a `security` key for these rooms (would break this
        contract by making properties resolution authoritative when
        it shouldn't be)."""
        room = _make_room(
            yaml_id=1,
            slug="no_security_room",
            raw_extra={},
        )

        async def _go():
            db, slug_to_id = await _setup_db_with_rooms([room])
            room_id = slug_to_id["no_security_room"]
            raw = await db.get_room_property(room_id, "security")
            self.assertIsNone(
                raw,
                "Room declared no security — get_room_property "
                "should return None (no zone defaults set in this "
                "test), letting the resolver apply CONTESTED.",
            )
            sec = await get_effective_security(room_id, db, character=None)
            self.assertEqual(sec, SecurityLevel.CONTESTED)

        _run(_go())

    # ─────────────────────────────────────────────────────────────────
    # The explicit-properties wins case (defense against future
    # regressions of the precedence rule)
    # ─────────────────────────────────────────────────────────────────

    def test_explicit_properties_wins_over_top_level(self):
        """If a room declares both (an authoring artifact), the
        explicit properties.security value resolves — top-level
        is ignored."""
        room = _make_room(
            yaml_id=1,
            slug="conflicting_room",
            raw_extra={
                "security_level": "lawless",
                "properties": {"security": "secured"},
            },
        )

        async def _go():
            db, slug_to_id = await _setup_db_with_rooms([room])
            room_id = slug_to_id["conflicting_room"]
            sec = await get_effective_security(room_id, db, character=None)
            self.assertEqual(
                sec, SecurityLevel.SECURED,
                "properties.security: secured should win over "
                "top-level security_level: lawless.",
            )

        _run(_go())


if __name__ == "__main__":
    unittest.main()
