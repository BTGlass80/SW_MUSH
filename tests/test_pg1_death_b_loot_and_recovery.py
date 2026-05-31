# -*- coding: utf-8 -*-
"""
tests/test_pg1_death_b_loot_and_recovery.py — PG.1.death.b (Drop 2d,
May 19 2026 evening).

Pins the recovery + decay + loot half of the death-penalty loop:
  - Loot helpers (single-item, bulk, owner-route)
  - Bacta tank + bacta pack helpers (clear wound_state)
  - Decay processing (bound items return to owner, generics destroyed)
  - run_decay_tick batch sweep
  - Tick handler registration (smoke check)
  - LookCommand corpse-listing (byte-grep)
  - LootCommand / BactaTankCommand structural shape
  - get_corpses_by_char DB helper

Test sections:
   1. TestLootSingleItem          — take one item by key
   2. TestLootMissingItem         — bad key returns None
   3. TestLootAll                 — bulk path moves everything
   4. TestLootResourceReroute     — kind=resource → resources blob
   5. TestBactaTankClear          — wounded → healthy
   6. TestBactaTankAlreadyHealthy — returns False
   7. TestBactaPackEquivalence    — same effect as tank
   8. TestDecayBoundReturnsToOwner — bound flag → inventory
   9. TestDecayGenericDestroyed   — non-bound → discarded
  10. TestDecayResourceBound      — resource + bound → resources blob
  11. TestDecayCorpseRowDeleted   — row removed after decay
  12. TestRunDecayTickBatch       — sweep processes all expired
  13. TestRunDecayTickEmpty       — no expired = empty list
  14. TestGetCorpsesByChar        — owner-side lookup
  15. TestTickHandlerImports      — modules import cleanly
  16. TestTickHandlerRegistration — registered in game_server
  17. TestLookCommandShowsCorpses — byte-grep: look path includes corpses
  18. TestLootCommandRegistered   — LootCommand in registry
  19. TestBactaTankCommandRegistered — BactaTankCommand in registry
  20. TestUseCommandHasBactaHook  — byte-grep: UseCommand hooks bacta_pack
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────────────────────────────
# Reuse the _MiniDB pattern from Drop 2c's test suite
# ──────────────────────────────────────────────────────────────────────

class _SyncAsyncSqlite:
    def __init__(self):
        import sqlite3
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        self._conn.execute(sql, params)

    async def execute_fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    async def commit(self):
        self._conn.commit()


class _MiniDB:
    def __init__(self):
        self._db = _SyncAsyncSqlite()
        cur = self._db._conn
        cur.executescript("""
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                room_id INTEGER DEFAULT 1,
                credits INTEGER DEFAULT 1000,
                wound_level INTEGER DEFAULT 0,
                wound_state TEXT DEFAULT 'healthy',
                wound_clear_at REAL DEFAULT 0,
                inventory TEXT DEFAULT '{"items":[],"resources":[]}',
                equipment TEXT DEFAULT '{}',
                wilderness_region_slug TEXT DEFAULT NULL,
                wilderness_x INTEGER DEFAULT NULL,
                wilderness_y INTEGER DEFAULT NULL
            );
            CREATE TABLE corpses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                char_id INTEGER NOT NULL,
                room_id INTEGER NOT NULL,
                died_at REAL NOT NULL,
                decay_at REAL NOT NULL,
                inventory TEXT NOT NULL DEFAULT '[]',
                credits INTEGER DEFAULT 0,
                killer_id INTEGER,
                killer_is_bh INTEGER DEFAULT 0,
                bounty_resolved INTEGER DEFAULT 0
            );
        """)
        self._db._conn.commit()

    @classmethod
    def with_real_methods(cls):
        from db.database import Database
        inst = cls()
        inst._CHARACTER_WRITABLE_COLUMNS = (
            Database._CHARACTER_WRITABLE_COLUMNS
        )
        method_names = [
            "create_corpse", "get_corpse", "get_corpses_in_room",
            "get_corpses_by_char",
            "get_decayed_corpses", "delete_corpse",
            "update_corpse_inventory",
            "set_wound_state", "get_wound_state",
            "save_character",
            "add_to_inventory", "remove_from_inventory",
            "_get_inventory_raw",
        ]
        for name in method_names:
            m = getattr(Database, name, None)
            if m is None:
                continue
            setattr(inst, name, m.__get__(inst, cls))
        return inst

    async def seed_character(self, *, char_id=1, name="Testpc",
                              room_id=1, credits=1000,
                              inventory=None, wound_state="healthy"):
        inv = inventory if inventory is not None else {
            "items": [], "resources": []
        }
        self._db._conn.execute(
            "INSERT INTO characters (id, name, room_id, credits, "
            "wound_state, inventory) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (char_id, name, room_id, credits, wound_state,
             json.dumps(inv)),
        )
        self._db._conn.commit()

    async def get_character(self, char_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE id = ?", (char_id,),
        )
        return rows[0] if rows else None


def _spawn_corpse(db, *, char_id=1, room_id=1, items=None,
                   credits=0, decay_seconds=7200.0):
    return _run(db.create_corpse(
        char_id=char_id, room_id=room_id,
        inventory=items or [],
        credits=credits,
        decay_seconds=decay_seconds,
    ))


# ──────────────────────────────────────────────────────────────────────
# 1-2. Single-item loot
# ──────────────────────────────────────────────────────────────────────

class TestLootSingleItem(unittest.TestCase):

    def test_take_item_moves_to_looter_inventory(self):
        from engine.death import loot_corpse_take_item
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=10))
        cid = _spawn_corpse(db, char_id=42, room_id=1,
                            items=[{"key": "blaster_pistol",
                                    "quality": 60}])
        taken = _run(loot_corpse_take_item(
            db, corpse_id=cid, looter_id=10,
            item_key="blaster_pistol",
        ))
        self.assertIsNotNone(taken)
        self.assertEqual(taken["key"], "blaster_pistol")
        looter = _run(db.get_character(10))
        inv = json.loads(looter["inventory"])
        self.assertEqual(len(inv["items"]), 1)
        self.assertEqual(inv["items"][0]["key"], "blaster_pistol")

    def test_corpse_inventory_updated_after_take(self):
        from engine.death import loot_corpse_take_item
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=10))
        cid = _spawn_corpse(db, char_id=42, items=[
            {"key": "a"}, {"key": "b"},
        ])
        _run(loot_corpse_take_item(
            db, corpse_id=cid, looter_id=10, item_key="a",
        ))
        row = _run(db.get_corpse(cid))
        inv = json.loads(row["inventory"])
        self.assertEqual([i["key"] for i in inv], ["b"])


class TestLootMissingItem(unittest.TestCase):

    def test_returns_none_for_unknown_key(self):
        from engine.death import loot_corpse_take_item
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=10))
        cid = _spawn_corpse(db, char_id=42, items=[{"key": "blaster"}])
        result = _run(loot_corpse_take_item(
            db, corpse_id=cid, looter_id=10, item_key="lightsaber",
        ))
        self.assertIsNone(result)

    def test_returns_none_for_missing_corpse(self):
        from engine.death import loot_corpse_take_item
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=10))
        result = _run(loot_corpse_take_item(
            db, corpse_id=9999, looter_id=10, item_key="x",
        ))
        self.assertIsNone(result)


# ──────────────────────────────────────────────────────────────────────
# 3. Bulk loot
# ──────────────────────────────────────────────────────────────────────

class TestLootAll(unittest.TestCase):

    def test_owner_bulk_loot_moves_everything(self):
        from engine.death import loot_all_from_corpse
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=10))
        cid = _spawn_corpse(db, char_id=42, items=[
            {"key": "blaster"}, {"key": "medpac"}, {"key": "comlink"},
        ])
        moved = _run(loot_all_from_corpse(
            db, corpse_id=cid, looter_id=10,
        ))
        self.assertEqual(len(moved), 3)
        # Corpse is empty
        row = _run(db.get_corpse(cid))
        self.assertEqual(json.loads(row["inventory"]), [])
        # Looter has all three
        looter = _run(db.get_character(10))
        inv = json.loads(looter["inventory"])
        self.assertEqual(len(inv["items"]), 3)


# ──────────────────────────────────────────────────────────────────────
# 4. Resource re-route
# ──────────────────────────────────────────────────────────────────────

class TestLootResourceReroute(unittest.TestCase):

    def test_kind_resource_goes_to_resources_blob(self):
        from engine.death import loot_corpse_take_item
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=10))
        cid = _spawn_corpse(db, char_id=42, items=[
            {"type": "scrap", "quantity": 5, "kind": "resource"},
        ])
        taken = _run(loot_corpse_take_item(
            db, corpse_id=cid, looter_id=10, item_key="scrap",
        ))
        # Note: resource-style item has no 'key' field, so look-up by
        # 'scrap' won't match. Test the bulk path instead.
        self.assertIsNone(taken)

    def test_bulk_loot_routes_resource_to_resources(self):
        from engine.death import loot_all_from_corpse
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=10))
        cid = _spawn_corpse(db, char_id=42, items=[
            {"key": "blaster"},
            {"type": "scrap", "quantity": 5, "kind": "resource"},
        ])
        _run(loot_all_from_corpse(db, corpse_id=cid, looter_id=10))
        looter = _run(db.get_character(10))
        inv = json.loads(looter["inventory"])
        # blaster ended up in items; scrap in resources
        item_keys = [i.get("key") for i in inv["items"]]
        self.assertIn("blaster", item_keys)
        resource_types = [r.get("type") for r in inv["resources"]]
        self.assertIn("scrap", resource_types)
        # kind=resource marker must be stripped on the looter side.
        for r in inv["resources"]:
            self.assertNotIn("kind", r,
                "kind marker must be stripped when resource is "
                "moved back to the resources blob")


# ──────────────────────────────────────────────────────────────────────
# 5-7. Bacta
# ──────────────────────────────────────────────────────────────────────

class TestBactaTankClear(unittest.TestCase):

    def test_wounded_to_healthy(self):
        from engine.death import apply_bacta_tank
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        _run(db.set_wound_state(
            1, state="wounded", clear_at=time.time() + 3600,
        ))
        ok = _run(apply_bacta_tank(db, 1))
        self.assertTrue(ok)
        state, ca = _run(db.get_wound_state(1))
        self.assertEqual(state, "healthy")
        self.assertEqual(ca, 0.0)


class TestBactaTankAlreadyHealthy(unittest.TestCase):

    def test_returns_false_when_no_op(self):
        from engine.death import apply_bacta_tank
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        ok = _run(apply_bacta_tank(db, 1))
        self.assertFalse(ok)


class TestBactaPackEquivalence(unittest.TestCase):

    def test_pack_equivalent_to_tank(self):
        from engine.death import consume_bacta_pack
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        _run(db.set_wound_state(
            1, state="wounded", clear_at=time.time() + 3600,
        ))
        ok = _run(consume_bacta_pack(db, 1))
        self.assertTrue(ok)
        state, _ = _run(db.get_wound_state(1))
        self.assertEqual(state, "healthy")


# ──────────────────────────────────────────────────────────────────────
# 8-11. Decay
# ──────────────────────────────────────────────────────────────────────

class TestDecayBoundReturnsToOwner(unittest.TestCase):

    def test_bound_item_added_to_owner_inventory(self):
        from engine.death import decay_corpse
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=42, name="DeadGuy"))
        cid = _spawn_corpse(db, char_id=42, items=[
            {"key": "signature_lightsaber", "bound": True},
        ])
        row = _run(db.get_corpse(cid))
        summary = _run(decay_corpse(db, row))
        self.assertEqual(summary["bound_delivered"], 1)
        self.assertEqual(summary["destroyed"], 0)
        owner = _run(db.get_character(42))
        inv = json.loads(owner["inventory"])
        keys = [i.get("key") for i in inv["items"]]
        self.assertIn("signature_lightsaber", keys)


class TestDecayGenericDestroyed(unittest.TestCase):

    def test_unbound_item_destroyed(self):
        from engine.death import decay_corpse
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=42))
        cid = _spawn_corpse(db, char_id=42, items=[
            {"key": "blaster_pistol"},  # no bound flag
        ])
        row = _run(db.get_corpse(cid))
        summary = _run(decay_corpse(db, row))
        self.assertEqual(summary["bound_delivered"], 0)
        self.assertEqual(summary["destroyed"], 1)
        owner = _run(db.get_character(42))
        inv = json.loads(owner["inventory"])
        # Nothing returned.
        self.assertEqual(inv["items"], [])


class TestDecayResourceBound(unittest.TestCase):

    def test_bound_resource_goes_to_resources_blob(self):
        from engine.death import decay_corpse
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=42))
        cid = _spawn_corpse(db, char_id=42, items=[
            {"type": "rare_alloy", "quantity": 3,
             "kind": "resource", "bound": True},
        ])
        row = _run(db.get_corpse(cid))
        _run(decay_corpse(db, row))
        owner = _run(db.get_character(42))
        inv = json.loads(owner["inventory"])
        types_in_resources = [r.get("type") for r in inv["resources"]]
        self.assertIn("rare_alloy", types_in_resources)


class TestDecayCorpseRowDeleted(unittest.TestCase):

    def test_corpse_gone_after_decay(self):
        from engine.death import decay_corpse
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=42))
        cid = _spawn_corpse(db, char_id=42, items=[])
        row = _run(db.get_corpse(cid))
        _run(decay_corpse(db, row))
        self.assertIsNone(_run(db.get_corpse(cid)))


# ──────────────────────────────────────────────────────────────────────
# 12-13. run_decay_tick batch
# ──────────────────────────────────────────────────────────────────────

class TestRunDecayTickBatch(unittest.TestCase):

    def test_sweep_processes_all_expired(self):
        from engine.death import run_decay_tick
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        _run(db.seed_character(char_id=2))
        _run(db.seed_character(char_id=3))
        # Two expired, one fresh.
        expired_a = _spawn_corpse(db, char_id=1, decay_seconds=-1.0)
        expired_b = _spawn_corpse(db, char_id=2, decay_seconds=-1.0)
        fresh    = _spawn_corpse(db, char_id=3, decay_seconds=3600.0)
        summaries = _run(run_decay_tick(db))
        self.assertEqual(len(summaries), 2)
        processed_ids = {s["corpse_id"] for s in summaries}
        self.assertIn(expired_a, processed_ids)
        self.assertIn(expired_b, processed_ids)
        # Fresh corpse untouched.
        self.assertIsNotNone(_run(db.get_corpse(fresh)))


class TestRunDecayTickEmpty(unittest.TestCase):

    def test_no_expired_returns_empty(self):
        from engine.death import run_decay_tick
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        _spawn_corpse(db, char_id=1, decay_seconds=3600.0)
        summaries = _run(run_decay_tick(db))
        self.assertEqual(summaries, [])


# ──────────────────────────────────────────────────────────────────────
# 14. get_corpses_by_char DB helper
# ──────────────────────────────────────────────────────────────────────

class TestGetCorpsesByChar(unittest.TestCase):

    def test_owner_lookup_returns_only_their_corpses(self):
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        _run(db.seed_character(char_id=2))
        a = _spawn_corpse(db, char_id=1, room_id=10, decay_seconds=3600.0)
        b = _spawn_corpse(db, char_id=2, room_id=11, decay_seconds=3600.0)
        c = _spawn_corpse(db, char_id=1, room_id=12, decay_seconds=3600.0)
        rows = _run(db.get_corpses_by_char(1))
        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {a, c})
        self.assertNotIn(b, ids)


# ──────────────────────────────────────────────────────────────────────
# 15-16. Tick handler module
# ──────────────────────────────────────────────────────────────────────

class TestTickHandlerImports(unittest.TestCase):

    def test_module_imports_without_error(self):
        from server import tick_handlers_death  # noqa: F401
        self.assertTrue(hasattr(tick_handlers_death, "corpse_decay_tick"))
        self.assertTrue(hasattr(tick_handlers_death, "wound_recovery_tick"))


class TestTickHandlerRegistration(unittest.TestCase):
    """Byte-grep: confirm game_server.py registers both new handlers."""

    def test_corpse_decay_registered(self):
        text = (Path(PROJECT_ROOT) / "server" / "game_server.py").read_text(
            encoding="utf-8"
        )
        # Multi-line tolerant: the register() call may break across
        # lines (it does in production), so check for the handler
        # name in a "corpse_decay" quoted-string followed by the
        # corpse_decay_tick callable somewhere downstream.
        self.assertIn(
            '"corpse_decay"', text,
            'register("corpse_decay", ...) must appear in game_server.py',
        )
        self.assertIn(
            "corpse_decay_tick", text,
            "corpse_decay_tick must be imported and passed to register()",
        )

    def test_wound_recovery_registered(self):
        text = (Path(PROJECT_ROOT) / "server" / "game_server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '"wound_recovery"', text,
            'register("wound_recovery", ...) must appear in game_server.py',
        )
        self.assertIn(
            "wound_recovery_tick", text,
            "wound_recovery_tick must be imported and passed to register()",
        )


# ──────────────────────────────────────────────────────────────────────
# 17. LookCommand corpse display
# ──────────────────────────────────────────────────────────────────────

class TestLookCommandShowsCorpses(unittest.TestCase):

    def test_look_room_contents_lists_corpses(self):
        text = (Path(PROJECT_ROOT) / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8"
        )
        # We want LookCommand's _look_room_contents to call
        # get_corpses_in_room and surface the body. Byte-grep for
        # both: the DB call, and the "body of ... lies here" phrase.
        # Both should appear in the file.
        self.assertIn(
            "get_corpses_in_room(char[\"room_id\"])", text,
            "LookCommand must call get_corpses_in_room in the "
            "room-contents render",
        )
        self.assertIn(
            "lies here", text,
            "LookCommand's corpse-listing must surface a "
            "'lies here' phrase to the player",
        )


# ──────────────────────────────────────────────────────────────────────
# 18-19. Command registration
# ──────────────────────────────────────────────────────────────────────

class TestLootCommandRegistered(unittest.TestCase):

    def test_loot_command_in_registry_list(self):
        text = (Path(PROJECT_ROOT) / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8"
        )
        # Look for the registration list — there's a `commands = [`
        # block near the bottom; the LootCommand() instance must
        # appear in it.
        self.assertIn("LootCommand()", text)
        # And the class must declare key="loot".
        import re
        m = re.search(
            r'class LootCommand\(.*?key\s*=\s*["\']loot["\']',
            text, re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "LootCommand must declare key='loot'",
        )


class TestBactaTankCommandRegistered(unittest.TestCase):

    def test_bacta_tank_command_in_registry_list(self):
        text = (Path(PROJECT_ROOT) / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("BactaTankCommand()", text)
        import re
        m = re.search(
            r'class BactaTankCommand\(.*?key\s*=\s*["\']bacta["\']',
            text, re.DOTALL,
        )
        self.assertIsNotNone(m)


# ──────────────────────────────────────────────────────────────────────
# 20. UseCommand has bacta_pack hook
# ──────────────────────────────────────────────────────────────────────

class TestUseCommandHasBactaHook(unittest.TestCase):
    """The bacta_pack consumable is NOT a separate command; it flows
    through the existing F.8.c.2.b₄ UseCommand. The wound_state
    clearing happens as a side-effect of `use bacta_pack`. Byte-grep
    for the hook so refactoring doesn't silently drop it."""

    def test_use_command_calls_consume_bacta_pack(self):
        text = (Path(PROJECT_ROOT) / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8"
        )
        # Slice to the existing UseCommand class only (we have a
        # legacy stub later in the file, see drop 2d handoff).
        import re
        m = re.search(
            r"class UseCommand\(.*?\n(?=class \w)",
            text, re.DOTALL,
        )
        self.assertIsNotNone(m, "UseCommand class not found")
        body = m.group(0)
        self.assertIn(
            "BACTA_PACK_KEY", body,
            "UseCommand must reference BACTA_PACK_KEY for the "
            "bacta_pack hook",
        )
        self.assertIn(
            "consume_bacta_pack", body,
            "UseCommand must call consume_bacta_pack when "
            "item_key == BACTA_PACK_KEY",
        )


if __name__ == "__main__":
    unittest.main()
