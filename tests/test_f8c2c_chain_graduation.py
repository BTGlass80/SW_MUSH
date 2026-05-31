# -*- coding: utf-8 -*-
"""
tests/test_f8c2c_chain_graduation.py — F.8.c.2.c chain graduation
teleport + DB rebuild slug backfill.

F.8.c.2.c (May 4 2026) closes the chain runtime loop. When
``tutorial_chains.advance_step`` flips a chain to
``completion_state="graduated"``, the graduation teleport:

1. Resolves the chain's ``graduation.drop_room`` slug to a real
   room id via ``db.get_room_by_slug``.
2. Persists the player's room change via ``save_character``.
3. Stamps a ``pending_drop_room_id`` flag on chain state for the
   parser hook site to deliver session-aware UI work.

This drop adds:
  * ``engine/chain_graduation.py`` — slug resolver, engine-side
    persistence, parser-side teleport finisher
  * ``db/database.py::get_room_by_slug`` — JSON1 ``json_extract``
    lookup on ``properties.slug``
  * ``engine/world_writer.py::backfill_room_slugs`` — idempotent
    legacy-room slug stamper called from ``server/game_server.py``
    on every boot
  * Wires ``apply_graduation`` into ``chain_events._try_advance``'s
    graduated branch
  * Wires ``execute_pending_teleport`` into 6 parser hook sites:
    commands.py, npc_commands.py, builtin_commands.py,
    combat_commands.py (per-survivor session), mission_commands.py
    (accept + complete), bounty_commands.py

Test sections
-------------
   1. TestSlugResolver       — resolve_drop_room_id behavior
   2. TestApplyGraduation    — engine-side persistence
   3. TestPendingTeleport    — parser-side UI finisher
   4. TestGetRoomBySlugDB    — db.get_room_by_slug helper
   5. TestSlugBackfill       — backfill_room_slugs idempotency
   6. TestEndToEnd           — _try_advance triggers graduation
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


class _MockDB:
    """Minimal async DB stand-in. Records save_character calls and
    answers get_room / get_room_by_slug from a small in-memory map."""

    def __init__(self):
        self.rooms = {}                  # id -> dict
        self.slug_to_room = {}           # slug -> room dict
        self.save_calls = []             # list of (char_id, kwargs)
        self.save_should_raise = False

    def add_room(self, room_id: int, name: str, slug: str = ""):
        props = {"slug": slug} if slug else {}
        room = {
            "id": room_id, "name": name,
            "properties": json.dumps(props),
        }
        self.rooms[room_id] = room
        if slug:
            self.slug_to_room[slug] = room

    async def get_room(self, room_id):
        return self.rooms.get(int(room_id))

    async def get_room_by_slug(self, slug):
        if not slug or not slug.strip():
            return None
        return self.slug_to_room.get(slug.strip())

    async def save_character(self, char_id, **kwargs):
        if self.save_should_raise:
            raise RuntimeError("save_character intentional failure")
        self.save_calls.append((char_id, kwargs))


def _char(char_id=1, room_id=10, attrs=None):
    return {
        "id": char_id,
        "name": "TestPC",
        "room_id": room_id,
        "attributes": json.dumps(attrs or {}),
    }


# ─────────────────────────────────────────────────────────────────────
# 1. resolve_drop_room_id
# ─────────────────────────────────────────────────────────────────────


class TestSlugResolver(unittest.TestCase):

    def test_resolves_known_slug(self):
        from engine.chain_graduation import resolve_drop_room_id
        db = _MockDB()
        db.add_room(42, "Coruscant Works LZ", "coruscant_works_landing_zone")
        result = _run(resolve_drop_room_id(
            db, "coruscant_works_landing_zone"))
        self.assertEqual(result, 42)

    def test_returns_none_for_unknown_slug(self):
        from engine.chain_graduation import resolve_drop_room_id
        db = _MockDB()
        result = _run(resolve_drop_room_id(db, "no_such_slug"))
        self.assertIsNone(result)

    def test_returns_none_for_empty_slug(self):
        from engine.chain_graduation import resolve_drop_room_id
        db = _MockDB()
        self.assertIsNone(_run(resolve_drop_room_id(db, "")))
        self.assertIsNone(_run(resolve_drop_room_id(db, "   ")))

    def test_returns_none_when_db_lacks_helper(self):
        from engine.chain_graduation import resolve_drop_room_id
        # Plain object with no get_room_by_slug
        bare_db = types.SimpleNamespace()
        result = _run(resolve_drop_room_id(bare_db, "any_slug"))
        self.assertIsNone(result)

    def test_strips_whitespace(self):
        from engine.chain_graduation import resolve_drop_room_id
        db = _MockDB()
        db.add_room(7, "Bay 94", "mos_eisley_bay_94")
        result = _run(resolve_drop_room_id(
            db, "  mos_eisley_bay_94  "))
        self.assertEqual(result, 7)

    def test_handles_db_exception(self):
        from engine.chain_graduation import resolve_drop_room_id

        class RaisingDB:
            async def get_room_by_slug(self, slug):
                raise RuntimeError("DB on fire")

        result = _run(resolve_drop_room_id(RaisingDB(), "anything"))
        self.assertIsNone(result)


# ─────────────────────────────────────────────────────────────────────
# 2. apply_graduation
# ─────────────────────────────────────────────────────────────────────


class TestApplyGraduation(unittest.TestCase):

    def test_persists_room_and_stamps_pending_flag(self):
        from engine.chain_graduation import apply_graduation
        db = _MockDB()
        db.add_room(99, "Drop Room", "test_drop_room")
        char = _char(char_id=5, room_id=10)
        attrs = {"tutorial_chain": {
            "chain_id": "test", "step": 5,
            "completion_state": "graduated",
        }}
        result = _run(apply_graduation(
            db, char, attrs, "test_drop_room"))

        # Returns the new room id
        self.assertEqual(result, 99)
        # save_character was called with room_id
        self.assertEqual(len(db.save_calls), 1)
        char_id, kwargs = db.save_calls[0]
        self.assertEqual(char_id, 5)
        self.assertEqual(kwargs.get("room_id"), 99)
        # char dict was mutated in place
        self.assertEqual(char["room_id"], 99)
        # Pending flag stamped on chain state
        self.assertEqual(
            attrs["tutorial_chain"]["pending_drop_room_id"], 99)

    def test_returns_none_for_unresolvable_slug(self):
        from engine.chain_graduation import apply_graduation
        db = _MockDB()
        char = _char(room_id=10)
        attrs = {"tutorial_chain": {}}
        result = _run(apply_graduation(
            db, char, attrs, "no_such_room"))
        self.assertIsNone(result)
        # No save_character call
        self.assertEqual(len(db.save_calls), 0)
        # char room unchanged
        self.assertEqual(char["room_id"], 10)
        # No pending flag
        self.assertNotIn(
            "pending_drop_room_id",
            attrs.get("tutorial_chain", {}),
        )

    def test_returns_none_for_empty_slug(self):
        from engine.chain_graduation import apply_graduation
        db = _MockDB()
        char = _char()
        attrs = {}
        self.assertIsNone(_run(apply_graduation(db, char, attrs, "")))
        self.assertIsNone(_run(apply_graduation(db, char, attrs, None)))

    def test_idempotent_when_already_in_drop_room(self):
        from engine.chain_graduation import apply_graduation
        db = _MockDB()
        db.add_room(99, "Drop Room", "test_drop_room")
        char = _char(room_id=99)  # already there
        attrs = {"tutorial_chain": {}}
        result = _run(apply_graduation(
            db, char, attrs, "test_drop_room"))
        self.assertEqual(result, 99)
        # Pending flag still stamped (so flavor line still fires)
        self.assertEqual(
            attrs["tutorial_chain"]["pending_drop_room_id"], 99)
        # No save_character call (no actual move)
        self.assertEqual(len(db.save_calls), 0)
        # char room unchanged
        self.assertEqual(char["room_id"], 99)

    def test_returns_none_when_save_fails(self):
        from engine.chain_graduation import apply_graduation
        db = _MockDB()
        db.add_room(99, "Drop Room", "test_drop_room")
        db.save_should_raise = True
        char = _char(room_id=10)
        attrs = {}
        result = _run(apply_graduation(
            db, char, attrs, "test_drop_room"))
        self.assertIsNone(result)
        # char room unchanged because persist failed
        self.assertEqual(char["room_id"], 10)


# ─────────────────────────────────────────────────────────────────────
# 3. execute_pending_teleport
# ─────────────────────────────────────────────────────────────────────


class _MockSession:
    def __init__(self):
        self.character = None
        self.lines = []

    async def send_line(self, line: str):
        self.lines.append(line)


class _MockSessionMgr:
    def __init__(self):
        self._registry = {}


class _MockCtx:
    """Bare CommandContext stand-in. Mirrors the real shape just
    enough to satisfy execute_pending_teleport. Accepts all kwargs
    that the real CommandContext takes so type(ctx)(...) works."""

    def __init__(self, db=None, session=None, session_mgr=None,
                 raw_input="", command="", args="", args_list=None):
        self.db = db
        self.session = session
        self.session_mgr = session_mgr
        self.raw_input = raw_input
        self.command = command
        self.args = args
        self.args_list = args_list or []


class _MockLookCommand:
    def __init__(self):
        self.calls = 0

    async def execute(self, ctx):
        self.calls += 1
        await ctx.session.send_line("[mock-look output]")


class TestPendingTeleport(unittest.TestCase):

    def _setup(self, char_room_id=10, pending_room_id=99,
               pending_room_exists=True):
        db = _MockDB()
        if pending_room_exists:
            db.add_room(pending_room_id, "Drop Room", "drop_slug")
        db.add_room(char_room_id, "Old Room", "old_slug")
        attrs = {"tutorial_chain": {
            "chain_id": "test", "step": 5,
            "completion_state": "graduated",
            "pending_drop_room_id": pending_room_id,
        }}
        char = _char(char_id=5, room_id=char_room_id, attrs=attrs)
        session = _MockSession()
        session.character = char
        session_mgr = _MockSessionMgr()
        look = _MockLookCommand()
        session_mgr._registry["look"] = look
        ctx = _MockCtx(db, session, session_mgr)
        return db, char, session, session_mgr, ctx, look

    def test_no_op_when_no_pending_flag(self):
        from engine.chain_graduation import execute_pending_teleport
        db, char, session, _, ctx, look = self._setup()
        # Strip the pending flag
        attrs = json.loads(char["attributes"])
        del attrs["tutorial_chain"]["pending_drop_room_id"]
        char["attributes"] = json.dumps(attrs)

        result = _run(execute_pending_teleport(ctx, char))
        self.assertFalse(result)
        # No look executed
        self.assertEqual(look.calls, 0)
        # No flavor lines sent
        self.assertEqual(len(session.lines), 0)

    def test_delivers_ui_and_clears_flag(self):
        from engine.chain_graduation import execute_pending_teleport
        db, char, session, _, ctx, look = self._setup()

        result = _run(execute_pending_teleport(ctx, char))
        self.assertTrue(result)
        # Look was called
        self.assertEqual(look.calls, 1)
        # Flavor lines were sent (graduation message + room arrival)
        self.assertGreater(len(session.lines), 2)
        # Session character room_id synced
        self.assertEqual(ctx.session.character["room_id"], 99)
        # Pending flag cleared
        attrs = json.loads(char["attributes"])
        self.assertNotIn(
            "pending_drop_room_id",
            attrs.get("tutorial_chain", {}),
        )
        # save_character was called to persist the cleared attrs
        self.assertGreaterEqual(len(db.save_calls), 1)

    def test_clears_stale_flag_when_room_missing(self):
        from engine.chain_graduation import execute_pending_teleport
        # pending room doesn't exist in DB
        db, char, session, _, ctx, look = self._setup(
            pending_room_exists=False,
        )

        result = _run(execute_pending_teleport(ctx, char))
        self.assertFalse(result)
        # No look (room missing)
        self.assertEqual(look.calls, 0)
        # Pending flag cleared regardless
        attrs = json.loads(char["attributes"])
        self.assertNotIn(
            "pending_drop_room_id",
            attrs.get("tutorial_chain", {}),
        )

    def test_handles_bad_pending_value(self):
        from engine.chain_graduation import execute_pending_teleport
        db, char, session, _, ctx, look = self._setup()
        # Replace pending_drop_room_id with non-int junk
        attrs = json.loads(char["attributes"])
        attrs["tutorial_chain"]["pending_drop_room_id"] = "not_an_int"
        char["attributes"] = json.dumps(attrs)

        result = _run(execute_pending_teleport(ctx, char))
        self.assertFalse(result)
        # Flag cleared
        attrs2 = json.loads(char["attributes"])
        self.assertNotIn(
            "pending_drop_room_id",
            attrs2.get("tutorial_chain", {}),
        )


# ─────────────────────────────────────────────────────────────────────
# 4. db.get_room_by_slug
# ─────────────────────────────────────────────────────────────────────


class TestGetRoomBySlugDB(unittest.IsolatedAsyncioTestCase):
    """Real Database against an in-memory SQLite — exercises
    SQLite's JSON1 json_extract path."""

    async def asyncSetUp(self):
        from db.database import Database
        self.db = Database(":memory:")
        await self.db.connect()
        await self.db.initialize()

    async def asyncTearDown(self):
        if self.db._db:
            await self.db._db.close()

    async def _make_room(self, name: str, slug: str = "") -> int:
        """Insert a minimal rooms row directly. Avoids depending on
        create_room signature stability."""
        props = json.dumps({"slug": slug}) if slug else "{}"
        cur = await self.db._db.execute(
            "INSERT INTO rooms (name, desc_short, desc_long, "
            "zone_id, properties) VALUES (?, ?, ?, ?, ?)",
            (name, "", "", None, props),
        )
        await self.db._db.commit()
        return cur.lastrowid

    async def test_finds_room_with_slug(self):
        rid = await self._make_room("Test Room", "test_slug_a")
        result = await self.db.get_room_by_slug("test_slug_a")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], rid)
        self.assertEqual(result["name"], "Test Room")

    async def test_returns_none_for_missing_slug(self):
        await self._make_room("Other Room", "other_slug")
        result = await self.db.get_room_by_slug("nonexistent_slug")
        self.assertIsNone(result)

    async def test_returns_none_for_empty_slug(self):
        self.assertIsNone(await self.db.get_room_by_slug(""))
        self.assertIsNone(await self.db.get_room_by_slug("   "))

    async def test_does_not_match_room_without_slug(self):
        # Room with no slug in properties shouldn't match anything
        await self._make_room("No-Slug Room", slug="")
        result = await self.db.get_room_by_slug("")
        self.assertIsNone(result)

    async def test_returns_first_when_multiple_share_slug(self):
        # Edge case — bad data. Function should still return a row,
        # using LIMIT 1 to avoid undefined behavior. We don't assert
        # which row; just that it returns one cleanly without raising.
        rid1 = await self._make_room("Dup A", "dup_slug")
        await self._make_room("Dup B", "dup_slug")
        result = await self.db.get_room_by_slug("dup_slug")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], rid1)


# ─────────────────────────────────────────────────────────────────────
# 5. backfill_room_slugs
# ─────────────────────────────────────────────────────────────────────


class _BundleRoom:
    def __init__(self, name, slug):
        self.name = name
        self.slug = slug


class _Bundle:
    def __init__(self, rooms_dict):
        self.rooms = rooms_dict
        self.report = types.SimpleNamespace(ok=True, errors=[])


class TestSlugBackfill(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        from db.database import Database
        self.db = Database(":memory:")
        await self.db.connect()
        await self.db.initialize()

    async def asyncTearDown(self):
        if self.db._db:
            await self.db._db.close()

    async def _make_room(self, name, slug=""):
        props = json.dumps({"slug": slug}) if slug else "{}"
        cur = await self.db._db.execute(
            "INSERT INTO rooms (name, desc_short, desc_long, "
            "zone_id, properties) VALUES (?, ?, ?, ?, ?)",
            (name, "", "", None, props),
        )
        await self.db._db.commit()
        return cur.lastrowid

    async def test_backfills_legacy_room(self):
        from engine.world_writer import backfill_room_slugs
        # DB has a room with no slug; YAML knows the slug.
        # SCHEMA_SQL seeds 3 default rooms which don't match any YAML
        # entry — they show up as no_yaml_match. We assert only on
        # the deltas our test introduces.
        rid = await self._make_room("Major Tarrn's Briefing", slug="")
        bundle = _Bundle({
            "yaml_id_a": _BundleRoom(
                "Major Tarrn's Briefing", "tipoca_briefing_room"),
        })

        report = await backfill_room_slugs(self.db, bundle)
        self.assertEqual(report["backfilled"], 1)
        self.assertEqual(report["already_stamped"], 0)
        self.assertEqual(report["errors"], 0)

        # Verify slug is now stamped
        result = await self.db.get_room_by_slug("tipoca_briefing_room")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], rid)

    async def test_idempotent_second_run(self):
        from engine.world_writer import backfill_room_slugs
        rid = await self._make_room("Already Stamped", "already_slug")
        bundle = _Bundle({
            "y": _BundleRoom("Already Stamped", "already_slug"),
        })

        # First run — already stamped, no work
        r1 = await backfill_room_slugs(self.db, bundle)
        self.assertEqual(r1["backfilled"], 0)
        self.assertEqual(r1["already_stamped"], 1)

        # Second run — same outcome
        r2 = await backfill_room_slugs(self.db, bundle)
        self.assertEqual(r2["backfilled"], 0)
        self.assertEqual(r2["already_stamped"], 1)

    async def test_skips_db_rooms_with_no_yaml_match(self):
        from engine.world_writer import backfill_room_slugs
        await self._make_room("Test-Created Room", slug="")
        bundle = _Bundle({
            "y": _BundleRoom("Different Name", "some_slug"),
        })

        report = await backfill_room_slugs(self.db, bundle)
        # Our 1 + 3 seed rooms = 4 rooms with no YAML match
        self.assertEqual(report["backfilled"], 0)
        self.assertEqual(report["no_yaml_match"], 4)

    async def test_handles_empty_bundle(self):
        from engine.world_writer import backfill_room_slugs
        await self._make_room("R", slug="")
        bundle = _Bundle({})  # empty
        report = await backfill_room_slugs(self.db, bundle)
        self.assertEqual(report["backfilled"], 0)

    async def test_mixed_run(self):
        from engine.world_writer import backfill_room_slugs
        # Two rooms: one stamped, one not. Both have YAML matches.
        # NOTE: SCHEMA_SQL seeds 3 default rooms (Landing Pad, Mos Eisley
        # Street, Chalmun's Cantina) without slugs — they show up in
        # the scan as no_yaml_match. We assert on our deltas, not totals.
        await self._make_room("Stamped", "stamped_slug")
        await self._make_room("Unstamped", slug="")
        await self._make_room("Lonely", slug="")  # no YAML match
        bundle = _Bundle({
            "a": _BundleRoom("Stamped", "stamped_slug"),
            "b": _BundleRoom("Unstamped", "unstamped_slug"),
        })

        report = await backfill_room_slugs(self.db, bundle)
        # Our 3 + the 3 seed rooms = 6 scanned
        self.assertEqual(report["scanned"], 6)
        # Already stamped: only our "Stamped"
        self.assertEqual(report["already_stamped"], 1)
        # Backfilled: only our "Unstamped"
        self.assertEqual(report["backfilled"], 1)
        # No YAML match: our "Lonely" + 3 seed rooms = 4
        self.assertEqual(report["no_yaml_match"], 4)
        self.assertEqual(report["errors"], 0)


# ─────────────────────────────────────────────────────────────────────
# 6. End-to-end via _try_advance
# ─────────────────────────────────────────────────────────────────────


class TestEndToEndGraduation(unittest.TestCase):
    """Verify _try_advance fires the graduation teleport when
    advance_step flips completion_state."""

    def setUp(self):
        from engine.era_state import set_active_config
        from engine.chain_events import _reset_corpus_cache
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        _reset_corpus_cache()

    def tearDown(self):
        from engine.era_state import clear_active_config
        from engine.chain_events import _reset_corpus_cache
        clear_active_config()
        _reset_corpus_cache()

    def test_graduating_chain_fires_apply_graduation(self):
        # Use republic_soldier — a chain whose graduation drop_room
        # is `coruscant_works_landing_zone`. We stage that room in
        # the mock DB so the slug resolves.
        from engine.chain_events import on_command_executed

        db = _MockDB()
        db.add_room(500, "The Works LZ",
                    "coruscant_works_landing_zone")

        # Build a republic_soldier char one step from graduation:
        # step 5 (final) — completes via `command_executed: +factions`.
        attrs = {
            "tutorial_chain": {
                "chain_id": "republic_soldier",
                "step": 5,
                "started_at": 1000000,
                "completed_steps": [1, 2, 3, 4],
                "completion_state": "active",
            }
        }
        char = {
            "id": 7, "name": "Trooper", "room_id": 100,
            "attributes": json.dumps(attrs),
        }

        result = _run(on_command_executed(
            db, char, "+factions", ""))
        self.assertTrue(result)

        # Char was teleported
        self.assertEqual(char["room_id"], 500)
        # save_character was called at least twice:
        # once for room_id (apply_graduation), once for attributes
        # (chain_events._persist_attrs). Order may vary.
        self.assertGreaterEqual(len(db.save_calls), 2)

        # Verify chain state shows graduated + pending flag
        new_attrs = json.loads(char["attributes"])
        chain_state = new_attrs["tutorial_chain"]
        self.assertEqual(chain_state["completion_state"], "graduated")
        self.assertEqual(chain_state["pending_drop_room_id"], 500)


# ─────────────────────────────────────────────────────────────────────


class TestDropMarker(unittest.TestCase):
    def test_module_docstring_marks_drop_id(self):
        import tests.test_f8c2c_chain_graduation as mod
        self.assertIn("F.8.c.2.c", mod.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
