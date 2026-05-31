# -*- coding: utf-8 -*-
"""
tests/test_pg1_death_a_engine_consumers.py — PG.1.death.a (Drop 2c,
May 19 2026 evening).

Pins the engine-consumer half of the death-penalty loop:
  - Corpse object lifecycle (create/get/list/decay/delete/update)
  - wound_state set/get + recovery clock
  - engine/death.on_pc_death orchestration across security levels
  - engine/death.decay_seconds_for_security resolver
  - Character.total_penalty_dice carries the −1D wounded debuff
  - RespawnCommand no-longer-penalizes-credits regression

PG.1.death.b (next drop) covers:
  - `loot <corpse>` parser command
  - Decay scheduler hook
  - Bacta-tank vendor (500cr clears wound_state immediately)
  - Bacta-pack consumable (150cr)
  - Bound-item auto-mail on decay

Test sections:
   1. TestDecayWindowResolver       — security → decay seconds
   2. TestCorpseCRUD                — create/get/list/delete
   3. TestCorpseDecayQuery          — get_decayed_corpses by clock
   4. TestCorpseInventoryUpdate     — update_corpse_inventory shape
   5. TestWoundStateSetGet          — set/get round-trip
   6. TestWoundStateInvalidValue    — bad state string rejected
   7. TestWoundStateRecoveryTick    — clock-expired auto-clears
   8. TestCharacterPenaltyDice      — −1D contribution when wounded
   9. TestCharacterFromDbDict       — wound_state hydrated from row
  10. TestOnPcDeathContested        — full happy path
  11. TestOnPcDeathLawless          — 4h decay window
  12. TestOnPcDeathSecured          — no corpse, no wound_state
  13. TestOnPcDeathInventoryCleared — char inventory empty post-death
  14. TestOnPcDeathCreditsUntouched — credits stay on char per §3.2
  15. TestOnPcDeathFailureTolerance — DB error doesn't crash flow
  16. TestRespawnCommandNoCreditPenalty — credits untouched on respawn
  17. TestRespawnCommandNoWeaponWear    — weapon condition untouched
  18. TestRespawnRoomFromHelper         — uses respawn_destination()
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    """Run a coroutine to completion in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────────────────────────────
# In-memory DB stand-in
# ──────────────────────────────────────────────────────────────────────
#
# The Drop 2c DB methods (create_corpse, set_wound_state, etc.) sit
# on the real Database class and ultimately use ``self._db.execute``
# / ``self._db.execute_fetchall``. To exercise them without a real
# SQLite migration we build a thin wrapper that delegates to a
# real in-memory sqlite3 DB and mimics the async API.

class _SyncAsyncSqlite:
    """aiosqlite-compatible adapter over the stdlib sqlite3 module."""

    def __init__(self):
        import sqlite3
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        self._conn.execute(sql, params)
        return None

    async def execute_fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    async def commit(self):
        self._conn.commit()


class _MiniDB:
    """Minimal `Database`-API surface for tests.

    Implements just enough for engine.death + the new corpse / wound
    methods + RespawnCommand to exercise their full code paths.
    Internally delegates to a real SQLite in-memory DB.
    """

    def __init__(self):
        self._db = _SyncAsyncSqlite()
        # Bootstrap minimal schema. Mirrors db/database.py's
        # PG.1.death schema columns exactly.
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

    # ── Methods copied verbatim from db/database.py ──
    # We instantiate the real Database class for these tests by
    # monkey-binding _MiniDB to use the methods from the real class.
    # This way we exercise the actual method bodies, not test-only
    # reimplementations.

    @classmethod
    def with_real_methods(cls):
        from db.database import Database
        inst = cls()
        # Borrow the writable-columns allowlist (used by save_character
        # to reject unknown kwargs).
        inst._CHARACTER_WRITABLE_COLUMNS = Database._CHARACTER_WRITABLE_COLUMNS
        # Bind the methods we need from Database onto this instance.
        method_names = [
            "create_corpse", "get_corpse", "get_corpses_in_room",
            "get_decayed_corpses", "delete_corpse",
            "update_corpse_inventory",
            "set_wound_state", "get_wound_state",
            "save_character",
            "add_to_inventory", "remove_from_inventory",
            "_get_inventory_raw",
        ]
        for name in method_names:
            method = getattr(Database, name, None)
            if method is None:
                continue
            # Bind as an unbound method calling with `inst` as self.
            setattr(inst, name, method.__get__(inst, cls))
        return inst

    async def seed_character(self, *, char_id=1, name="Testpc",
                              room_id=1, credits=1000,
                              inventory=None, equipment=None,
                              wound_level=0):
        import json as _j
        inv = inventory if inventory is not None else {
            "items": [], "resources": []
        }
        equip = equipment if equipment is not None else {}
        self._db._conn.execute(
            "INSERT INTO characters (id, name, room_id, credits, "
            "wound_level, inventory, equipment) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (char_id, name, room_id, credits, wound_level,
             _j.dumps(inv), _j.dumps(equip)),
        )
        self._db._conn.commit()

    async def get_character(self, char_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE id = ?", (char_id,),
        )
        return rows[0] if rows else None


# ──────────────────────────────────────────────────────────────────────
# 1. Decay-window resolver
# ──────────────────────────────────────────────────────────────────────

class TestDecayWindowResolver(unittest.TestCase):

    def test_contested_two_hours(self):
        from engine.death import decay_seconds_for_security
        self.assertEqual(decay_seconds_for_security("contested"), 7200.0)

    def test_lawless_four_hours(self):
        from engine.death import decay_seconds_for_security
        self.assertEqual(decay_seconds_for_security("lawless"), 14400.0)

    def test_secured_returns_no_corpse_sentinel(self):
        from engine.death import decay_seconds_for_security, NO_CORPSE
        self.assertIs(
            decay_seconds_for_security("secured"), NO_CORPSE,
        )

    def test_accepts_enum_str_form(self):
        # The SecurityLevel enum may stringify as 'SecurityLevel.LAWLESS';
        # the resolver should tolerate that form too.
        from engine.death import decay_seconds_for_security
        self.assertEqual(
            decay_seconds_for_security("SecurityLevel.LAWLESS"),
            14400.0,
        )
        from engine.death import NO_CORPSE
        self.assertIs(
            decay_seconds_for_security("SecurityLevel.SECURED"),
            NO_CORPSE,
        )

    def test_unknown_defaults_to_contested(self):
        # Safer to default to the standard 2h decay than to crash or
        # treat unknown as secured (which would skip the corpse).
        from engine.death import decay_seconds_for_security
        self.assertEqual(
            decay_seconds_for_security("definitely_not_a_real_level"),
            7200.0,
        )


# ──────────────────────────────────────────────────────────────────────
# 2. Corpse CRUD
# ──────────────────────────────────────────────────────────────────────

class TestCorpseCRUD(unittest.TestCase):

    def test_create_and_get_roundtrip(self):
        db = _MiniDB.with_real_methods()
        cid = _run(db.create_corpse(
            char_id=42, room_id=7,
            inventory=[{"key": "blaster_pistol", "quality": 60}],
            credits=120, decay_seconds=3600.0,
        ))
        self.assertTrue(cid > 0)
        row = _run(db.get_corpse(cid))
        self.assertIsNotNone(row)
        self.assertEqual(row["char_id"], 42)
        self.assertEqual(row["room_id"], 7)
        self.assertEqual(row["credits"], 120)
        inv = json.loads(row["inventory"])
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["key"], "blaster_pistol")

    def test_get_corpses_in_room_excludes_decayed(self):
        db = _MiniDB.with_real_methods()
        # One fresh, one already-decayed (decay_seconds negative).
        fresh = _run(db.create_corpse(
            char_id=1, room_id=10, inventory=[], decay_seconds=3600.0,
        ))
        stale = _run(db.create_corpse(
            char_id=2, room_id=10, inventory=[], decay_seconds=-10.0,
        ))
        listed = _run(db.get_corpses_in_room(10))
        ids = {r["id"] for r in listed}
        self.assertIn(fresh, ids)
        self.assertNotIn(
            stale, ids,
            "get_corpses_in_room must filter out corpses whose "
            "decay_at has passed",
        )

    def test_delete_corpse(self):
        db = _MiniDB.with_real_methods()
        cid = _run(db.create_corpse(
            char_id=1, room_id=1, inventory=[], decay_seconds=3600.0,
        ))
        _run(db.delete_corpse(cid))
        self.assertIsNone(_run(db.get_corpse(cid)))


# ──────────────────────────────────────────────────────────────────────
# 3. Decayed-corpse query
# ──────────────────────────────────────────────────────────────────────

class TestCorpseDecayQuery(unittest.TestCase):

    def test_get_decayed_corpses(self):
        db = _MiniDB.with_real_methods()
        # Fresh (won't show), expired (will).
        _run(db.create_corpse(char_id=1, room_id=1, inventory=[],
                              decay_seconds=3600.0))
        expired = _run(db.create_corpse(
            char_id=2, room_id=1, inventory=[],
            decay_seconds=-1.0,
        ))
        decayed = _run(db.get_decayed_corpses())
        ids = {r["id"] for r in decayed}
        self.assertIn(expired, ids)
        self.assertEqual(len(decayed), 1,
                         "only the expired corpse should be returned")


# ──────────────────────────────────────────────────────────────────────
# 4. Corpse-inventory update (looting will use this in PG.1.death.b)
# ──────────────────────────────────────────────────────────────────────

class TestCorpseInventoryUpdate(unittest.TestCase):

    def test_replace_inventory_and_credits(self):
        db = _MiniDB.with_real_methods()
        cid = _run(db.create_corpse(
            char_id=1, room_id=1,
            inventory=[{"key": "a"}, {"key": "b"}], credits=500,
            decay_seconds=3600.0,
        ))
        _run(db.update_corpse_inventory(
            cid, [{"key": "b"}], credits=250,
        ))
        row = _run(db.get_corpse(cid))
        inv = json.loads(row["inventory"])
        self.assertEqual([i["key"] for i in inv], ["b"])
        self.assertEqual(row["credits"], 250)


# ──────────────────────────────────────────────────────────────────────
# 5. wound_state set/get
# ──────────────────────────────────────────────────────────────────────

class TestWoundStateSetGet(unittest.TestCase):

    def test_round_trip_healthy_to_wounded(self):
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        clear_at = time.time() + 3600
        _run(db.set_wound_state(1, state="wounded", clear_at=clear_at))
        state, ca = _run(db.get_wound_state(1))
        self.assertEqual(state, "wounded")
        self.assertAlmostEqual(ca, clear_at, places=2)

    def test_back_to_healthy_clears_clock(self):
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        _run(db.set_wound_state(
            1, state="wounded", clear_at=time.time() + 3600,
        ))
        _run(db.set_wound_state(1, state="healthy", clear_at=0.0))
        state, ca = _run(db.get_wound_state(1))
        self.assertEqual(state, "healthy")
        self.assertEqual(ca, 0.0)

    def test_default_for_missing_row(self):
        db = _MiniDB.with_real_methods()
        state, ca = _run(db.get_wound_state(999))
        self.assertEqual(state, "healthy")
        self.assertEqual(ca, 0.0)


# ──────────────────────────────────────────────────────────────────────
# 6. wound_state input validation
# ──────────────────────────────────────────────────────────────────────

class TestWoundStateInvalidValue(unittest.TestCase):

    def test_bogus_state_raises_value_error(self):
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        with self.assertRaises(ValueError):
            _run(db.set_wound_state(1, state="dying"))


# ──────────────────────────────────────────────────────────────────────
# 7. Wound-recovery tick
# ──────────────────────────────────────────────────────────────────────

class TestWoundStateRecoveryTick(unittest.TestCase):

    def test_unexpired_clock_does_nothing(self):
        from engine.death import tick_wound_recovery
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        _run(db.set_wound_state(
            1, state="wounded", clear_at=time.time() + 3600,
        ))
        cleared = _run(tick_wound_recovery(db, 1))
        self.assertFalse(cleared)
        state, _ = _run(db.get_wound_state(1))
        self.assertEqual(state, "wounded")

    def test_expired_clock_transitions_to_healthy(self):
        from engine.death import tick_wound_recovery
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        _run(db.set_wound_state(
            1, state="wounded", clear_at=time.time() - 1.0,
        ))
        cleared = _run(tick_wound_recovery(db, 1))
        self.assertTrue(cleared)
        state, ca = _run(db.get_wound_state(1))
        self.assertEqual(state, "healthy")
        self.assertEqual(ca, 0.0)

    def test_healthy_char_unchanged(self):
        from engine.death import tick_wound_recovery
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        cleared = _run(tick_wound_recovery(db, 1))
        self.assertFalse(cleared)


# ──────────────────────────────────────────────────────────────────────
# 8. Character total_penalty_dice carries -1D when wounded
# ──────────────────────────────────────────────────────────────────────

class TestCharacterPenaltyDice(unittest.TestCase):

    def test_healthy_default_contributes_zero(self):
        from engine.character import Character
        c = Character()
        self.assertEqual(c.total_penalty_dice, 0)

    def test_wounded_state_adds_one_die_penalty(self):
        from engine.character import Character
        c = Character()
        c.wound_state = "wounded"
        # Penalty should be exactly +1 (the -1D respawn debuff).
        self.assertEqual(
            c.total_penalty_dice, 1,
            "wound_state='wounded' must contribute +1 to "
            "total_penalty_dice (the −1D PG.1.death debuff)",
        )

    def test_wounded_state_stacks_with_wound_level(self):
        from engine.character import Character, WoundLevel
        c = Character()
        c.wound_state = "wounded"
        c.wound_level = WoundLevel.WOUNDED  # also -1D in WEG ladder
        # Both contribute; stacking is intentional. PG.1.death's
        # design treats them as orthogonal axes (the WEG ladder
        # is per-fight; wound_state is post-respawn).
        expected = 1 + WoundLevel.WOUNDED.penalty_dice
        self.assertEqual(c.total_penalty_dice, expected)


# ──────────────────────────────────────────────────────────────────────
# 9. Character.from_db_dict hydrates wound_state
# ──────────────────────────────────────────────────────────────────────

class TestCharacterFromDbDict(unittest.TestCase):

    def test_wound_state_and_clear_at_hydrated(self):
        from engine.character import Character
        char = Character.from_db_dict({
            "id": 1, "name": "Test", "species": "Human",
            "wound_state": "wounded",
            "wound_clear_at": 1234567890.5,
        })
        self.assertEqual(char.wound_state, "wounded")
        self.assertEqual(char.wound_clear_at, 1234567890.5)

    def test_missing_columns_default_to_healthy(self):
        from engine.character import Character
        char = Character.from_db_dict({
            "id": 1, "name": "Test", "species": "Human",
        })
        self.assertEqual(char.wound_state, "healthy")
        self.assertEqual(char.wound_clear_at, 0.0)

    def test_null_clear_at_coerces_to_zero(self):
        # SQLite returns None for NULL columns. The constructor must
        # not crash on it.
        from engine.character import Character
        char = Character.from_db_dict({
            "id": 1, "name": "Test", "species": "Human",
            "wound_state": None,  # NULL column
            "wound_clear_at": None,
        })
        self.assertEqual(char.wound_state, "healthy")
        self.assertEqual(char.wound_clear_at, 0.0)


# ──────────────────────────────────────────────────────────────────────
# 10. on_pc_death — happy path (contested)
# ──────────────────────────────────────────────────────────────────────

class TestOnPcDeathContested(unittest.TestCase):

    def test_creates_corpse_with_inventory_and_sets_wounded(self):
        from engine.death import on_pc_death
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(
            char_id=42, room_id=7, credits=1500,
            inventory={"items": [
                {"key": "blaster_pistol", "quality": 75},
                {"key": "medpac", "quality": 50},
            ], "resources": []},
        ))
        corpse_id = _run(on_pc_death(
            db, char_id=42, room_id=7,
            security_level="contested",
        ))
        self.assertIsNotNone(corpse_id)
        # Corpse has the gear.
        row = _run(db.get_corpse(corpse_id))
        self.assertEqual(row["char_id"], 42)
        self.assertEqual(row["room_id"], 7)
        inv = json.loads(row["inventory"])
        self.assertEqual(len(inv), 2)
        # Decay window ~2h.
        elapsed_window = row["decay_at"] - row["died_at"]
        self.assertAlmostEqual(elapsed_window, 7200.0, places=0)
        # Char wound_state is now 'wounded' with ~1h clock.
        state, ca = _run(db.get_wound_state(42))
        self.assertEqual(state, "wounded")
        self.assertAlmostEqual(ca - time.time(), 3600.0, delta=5)


# ──────────────────────────────────────────────────────────────────────
# 11. on_pc_death — lawless gets 4h corpse window
# ──────────────────────────────────────────────────────────────────────

class TestOnPcDeathLawless(unittest.TestCase):

    def test_lawless_decay_is_four_hours(self):
        from engine.death import on_pc_death
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1))
        corpse_id = _run(on_pc_death(
            db, char_id=1, room_id=1, security_level="lawless",
        ))
        row = _run(db.get_corpse(corpse_id))
        self.assertAlmostEqual(
            row["decay_at"] - row["died_at"], 14400.0, places=0,
        )


# ──────────────────────────────────────────────────────────────────────
# 12. on_pc_death — secured skips corpse + wound_state
# ──────────────────────────────────────────────────────────────────────

class TestOnPcDeathSecured(unittest.TestCase):

    def test_secured_zone_no_corpse_no_debuff(self):
        from engine.death import on_pc_death
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(
            char_id=1, room_id=1,
            inventory={"items": [{"key": "blaster"}], "resources": []},
        ))
        corpse_id = _run(on_pc_death(
            db, char_id=1, room_id=1, security_level="secured",
        ))
        self.assertIsNone(
            corpse_id,
            "Secured-zone death must not create a corpse",
        )
        # Wound_state untouched.
        state, _ = _run(db.get_wound_state(1))
        self.assertEqual(state, "healthy")
        # Inventory untouched.
        row = _run(db.get_character(1))
        inv = json.loads(row["inventory"])
        self.assertEqual(
            inv["items"], [{"key": "blaster"}],
            "Secured-zone death must not clear inventory",
        )


# ──────────────────────────────────────────────────────────────────────
# 13. on_pc_death clears live inventory
# ──────────────────────────────────────────────────────────────────────

class TestOnPcDeathInventoryCleared(unittest.TestCase):

    def test_char_inventory_empty_after_death(self):
        from engine.death import on_pc_death
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(
            char_id=1, room_id=1,
            inventory={
                "items": [{"key": "a"}, {"key": "b"}],
                "resources": [{"type": "scrap", "quantity": 5}],
            },
        ))
        _run(on_pc_death(db, char_id=1, room_id=1,
                         security_level="contested"))
        row = _run(db.get_character(1))
        inv = json.loads(row["inventory"])
        self.assertEqual(inv["items"], [])
        self.assertEqual(inv["resources"], [])

    def test_resources_get_snapshotted_onto_corpse(self):
        # Per engine/death._snapshot_and_clear_inventory, resources
        # are tagged with kind=resource and appended to the corpse's
        # items list. Loot in PG.1.death.b will re-route them.
        from engine.death import on_pc_death
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(
            char_id=1, room_id=1,
            inventory={
                "items": [{"key": "blaster"}],
                "resources": [{"type": "scrap", "quantity": 5}],
            },
        ))
        cid = _run(on_pc_death(db, char_id=1, room_id=1,
                               security_level="contested"))
        corpse_inv = json.loads(_run(db.get_corpse(cid))["inventory"])
        self.assertEqual(len(corpse_inv), 2)
        keys_or_types = sorted(
            (i.get("key") or i.get("type") or "") for i in corpse_inv
        )
        self.assertEqual(keys_or_types, ["blaster", "scrap"])
        # Resource marker present.
        resource_marker_present = any(
            i.get("kind") == "resource" for i in corpse_inv
        )
        self.assertTrue(
            resource_marker_present,
            "Resources on the corpse must carry kind='resource' so "
            "PG.1.death.b loot can re-route them.",
        )


# ──────────────────────────────────────────────────────────────────────
# 14. on_pc_death does NOT touch credits (per design §3.2)
# ──────────────────────────────────────────────────────────────────────

class TestOnPcDeathCreditsUntouched(unittest.TestCase):

    def test_credits_remain_on_char(self):
        from engine.death import on_pc_death
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1, room_id=1, credits=2500))
        _run(on_pc_death(db, char_id=1, room_id=1,
                         security_level="contested"))
        row = _run(db.get_character(1))
        self.assertEqual(
            row["credits"], 2500,
            "Credits and bank must be untouched on death per "
            "progression_gates_and_consequences_design §3.2.",
        )

    def test_corpse_credits_zero(self):
        # Credits stay on char, not the corpse.
        from engine.death import on_pc_death
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1, room_id=1, credits=2500))
        cid = _run(on_pc_death(db, char_id=1, room_id=1,
                               security_level="contested"))
        row = _run(db.get_corpse(cid))
        self.assertEqual(row["credits"], 0)


# ──────────────────────────────────────────────────────────────────────
# 15. on_pc_death failure tolerance
# ──────────────────────────────────────────────────────────────────────

class TestOnPcDeathFailureTolerance(unittest.TestCase):

    def test_corpse_failure_still_sets_wound_state(self):
        # If create_corpse raises, the wound_state side-effect should
        # still run — the design treats them as independent.
        from engine.death import on_pc_death
        db = _MiniDB.with_real_methods()
        _run(db.seed_character(char_id=1, room_id=1))

        broken_create = AsyncMock(side_effect=RuntimeError("boom"))
        db.create_corpse = broken_create

        _run(on_pc_death(db, char_id=1, room_id=1,
                         security_level="contested"))
        state, _ = _run(db.get_wound_state(1))
        self.assertEqual(
            state, "wounded",
            "wound_state must still apply when corpse creation fails",
        )


# ──────────────────────────────────────────────────────────────────────
# 16. RespawnCommand no credit penalty (regression vs pre-Drop-2c)
# ──────────────────────────────────────────────────────────────────────
#
# These three tests cover the design-doc requirement (§3.2: "Credits
# and bank untouched"). Pre-Drop-2c, RespawnCommand deducted 10%-of-
# credits (min 100). Static checks against the rewritten source:
#  - No max() call with "credit_penalty" or "credits * 0.10".
#  - No save_character call passing credits=.
#  - No item.condition mutation.

class TestRespawnCommandNoCreditPenalty(unittest.TestCase):

    def _get_respawn_source(self):
        path = Path(PROJECT_ROOT) / "parser" / "builtin_commands.py"
        text = path.read_text(encoding="utf-8")
        # Slice out the RespawnCommand class block.
        import re
        m = re.search(
            r"class RespawnCommand.*?(?=^class \w)",
            text, re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(m, "RespawnCommand class not found")
        return m.group(0)

    def test_no_credit_penalty_calculation(self):
        src = self._get_respawn_source()
        # Old line was: credit_penalty = max(100, int(credits * 0.10))
        self.assertNotIn(
            "credit_penalty", src,
            "RespawnCommand still references credit_penalty; "
            "the credits-untouched design (PG.1.death §3.2) was "
            "not applied.",
        )
        self.assertNotIn(
            "credits * 0.10", src,
            "RespawnCommand still multiplies credits — credits "
            "must be untouched on respawn per design §3.2.",
        )

    def test_save_character_does_not_pass_credits(self):
        src = self._get_respawn_source()
        # The save_character call shouldn't have credits= as a kwarg.
        # Quick lexical check: every save_character call up to its
        # closing paren must not contain 'credits='.
        import re
        for m in re.finditer(
            r"save_character\((.*?)\)", src, re.DOTALL,
        ):
            self.assertNotIn(
                "credits=", m.group(1),
                "save_character(... credits=...) found in "
                "RespawnCommand; credits must not be mutated.",
            )


# ──────────────────────────────────────────────────────────────────────
# 17. RespawnCommand no weapon-condition wear
# ──────────────────────────────────────────────────────────────────────

class TestRespawnCommandNoWeaponWear(unittest.TestCase):

    def test_no_weapon_condition_mutation(self):
        path = Path(PROJECT_ROOT) / "parser" / "builtin_commands.py"
        text = path.read_text(encoding="utf-8")
        import re
        m = re.search(
            r"class RespawnCommand.*?(?=^class \w)",
            text, re.MULTILINE | re.DOTALL,
        )
        src = m.group(0)
        # Pre-Drop-2c had: item.condition = max(0, item.condition - 20)
        self.assertNotIn(
            "item.condition", src,
            "RespawnCommand still mutates weapon condition; "
            "PG.1.death §3.2 makes credits/gear untouched.",
        )
        self.assertNotIn(
            "condition - 20", src,
            "weapon-condition penalty leaked through the rewrite",
        )


# ──────────────────────────────────────────────────────────────────────
# 18. RespawnCommand sources respawn room from helper
# ──────────────────────────────────────────────────────────────────────

class TestRespawnRoomFromHelper(unittest.TestCase):

    def test_uses_respawn_destination_helper(self):
        # The respawn room is now sourced from
        # engine.death.respawn_destination (a chokepoint for the
        # future "nearest safe location" logic). The class should
        # import and call it instead of hardcoding room 1.
        path = Path(PROJECT_ROOT) / "parser" / "builtin_commands.py"
        text = path.read_text(encoding="utf-8")
        import re
        m = re.search(
            r"class RespawnCommand.*?(?=^class \w)",
            text, re.MULTILINE | re.DOTALL,
        )
        src = m.group(0)
        self.assertIn(
            "respawn_destination", src,
            "RespawnCommand must call engine.death.respawn_destination "
            "to pick the respawn room (so PG.1.death.b can swap the "
            "implementation to 'nearest safe location' without "
            "touching the command layer).",
        )


if __name__ == "__main__":
    unittest.main()
