# -*- coding: utf-8 -*-
"""
tests/test_space_caches.py — Space Wildspace Cache System (Drop 1a)

Per docs/design/space_wildspace_design_v1.md §4 + §8 Drop 1.

Test sections
=============
  1. TestSchema         — ensure_schema creates the table idempotently
  2. TestSpawn          — spawn_zone_caches creates instances to density
  3. TestVisibility     — is_cache_visible: universal, faction, hidden
  4. TestHarvestMining  — mine <id> yields resources + sets cooldown;
                          cooldown block; wrong-kind block; not-found block
  5. TestMineCommand    — parser/space_commands MineCommand dispatches;
                          'mine' (no arg) lists caches; 'mine <id>' calls harvest
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os
os.environ.setdefault("SW_ERA", "clone_wars")

# Import the difficulty constant for SkillCheckResult construction in tests.
# Must be imported after path setup.
from engine.space_caches import _MINE_DIFFICULTY  # noqa: E402 (path setup above)


def _run(coro):
    return asyncio.run(coro)


# ── shared fixtures ───────────────────────────────────────────────────────────

async def _fresh_db():
    """In-memory DB with core schema + housing (for FK-safe character inserts)
    + space_caches schema."""
    from db.database import Database
    from engine.housing import ensure_schema as _hs_schema
    from engine.space_caches import ensure_schema as _sc_schema

    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await _hs_schema(db)
    await _sc_schema(db)
    return db


async def _seed_account_and_char(db) -> int:
    """Seed the minimal account + character needed for harvest tests.
    Returns char_id."""
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts (username, password_hash, email) "
        "VALUES ('testuser', 'hash', 't@e.com')"
    )
    await db._db.commit()
    row = await db._db.execute_fetchall(
        "SELECT id FROM accounts WHERE username = 'testuser'"
    )
    acct_id = row[0]["id"]
    await db._db.execute(
        "INSERT INTO characters (account_id, name, attributes, skills, inventory) "
        "VALUES (?, 'TestPilot', '{}', '{}', '[]')",
        (acct_id,),
    )
    await db._db.commit()
    row2 = await db._db.execute_fetchall(
        "SELECT id FROM characters WHERE name = 'TestPilot'"
    )
    return row2[0]["id"]


def _char_dict(char_id: int) -> dict:
    """Minimal character dict for skill-check + add_resource calls.

    inventory is a JSON dict (not list) — engine.crafting._get_resource_list
    expects {"resources": []} as the starting structure.
    """
    return {
        "id": char_id,
        "name": "TestPilot",
        # 3D space transports so the skill check has a reasonable pool
        "skills": json.dumps({"space transports": "3D"}),
        "attributes": json.dumps({"mechanical": "3D"}),
        "inventory": json.dumps({"resources": [], "items": []}),
    }


# ═════════════════════════════════════════════════════════════════════════════
# 1. TestSchema
# ═════════════════════════════════════════════════════════════════════════════

class TestSchema(unittest.TestCase):
    """ensure_schema creates the space_caches table and indexes idempotently."""

    def test_table_exists_after_ensure(self):
        async def _go():
            db = await _fresh_db()
            rows = await db.fetchall(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='space_caches'"
            )
            return rows
        rows = _run(_go())
        self.assertTrue(rows, "space_caches table not created")

    def test_ensure_is_idempotent(self):
        """Calling ensure_schema twice must not raise."""
        from engine.space_caches import ensure_schema
        async def _go():
            db = await _fresh_db()
            await ensure_schema(db)   # second call
            rows = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='space_caches'"
            )
            return rows
        rows = _run(_go())
        self.assertEqual(len(rows), 1)

    def test_indexes_exist(self):
        async def _go():
            db = await _fresh_db()
            rows = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='space_caches'"
            )
            return [r["name"] for r in rows]
        names = _run(_go())
        self.assertIn("idx_space_caches_zone",  names)
        self.assertIn("idx_space_caches_state", names)


# ═════════════════════════════════════════════════════════════════════════════
# 2. TestSpawn
# ═════════════════════════════════════════════════════════════════════════════

class TestSpawn(unittest.TestCase):
    """spawn_zone_caches creates up to density instances; is idempotent."""

    def test_spawn_creates_instances_to_density(self):
        from engine.space_caches import spawn_zone_caches, DEV_TEST_ZONE_KEY, DEV_TEST_CACHE_POOL
        async def _go():
            db = await _fresh_db()
            created = await spawn_zone_caches(db, DEV_TEST_ZONE_KEY)
            return created, db
        created, db = _run(_go())
        # Total density = sum of all def densities in the pool
        expected_total = sum(d.density for d in DEV_TEST_CACHE_POOL.values())
        self.assertEqual(created, expected_total,
                         f"Expected {expected_total} instances, got {created}")

    def test_spawn_idempotent_does_not_overfill(self):
        from engine.space_caches import spawn_zone_caches, get_zone_caches, DEV_TEST_ZONE_KEY, DEV_TEST_CACHE_POOL
        async def _go():
            db = await _fresh_db()
            await spawn_zone_caches(db, DEV_TEST_ZONE_KEY)
            # Second call — no new rows should appear for cache already at density
            created2 = await spawn_zone_caches(db, DEV_TEST_ZONE_KEY)
            rows = await get_zone_caches(db, DEV_TEST_ZONE_KEY)
            return created2, rows
        created2, rows = _run(_go())
        expected_total = sum(d.density for d in DEV_TEST_CACHE_POOL.values())
        self.assertEqual(created2, 0, "Second spawn should create 0 new instances")
        self.assertEqual(len(rows), expected_total)

    def test_spawn_unknown_zone_returns_zero(self):
        from engine.space_caches import spawn_zone_caches
        async def _go():
            db = await _fresh_db()
            return await spawn_zone_caches(db, "nonexistent_zone")
        result = _run(_go())
        self.assertEqual(result, 0)


# ═════════════════════════════════════════════════════════════════════════════
# 3. TestVisibility
# ═════════════════════════════════════════════════════════════════════════════

class TestVisibility(unittest.TestCase):
    """is_cache_visible: universal, faction-gated, hidden."""

    def _row(self, vis_factions):
        return {"visibility_factions": vis_factions}

    def test_universal_visible_to_all(self):
        from engine.space_caches import is_cache_visible
        # NULL = universal
        self.assertTrue(is_cache_visible(self._row(None), {}))
        self.assertTrue(is_cache_visible(self._row(None), {"republic": -100}))

    def test_hidden_never_visible(self):
        from engine.space_caches import is_cache_visible
        self.assertFalse(is_cache_visible(self._row("hidden"), {}))
        self.assertFalse(is_cache_visible(self._row("hidden"), {"republic": 999}))

    def test_faction_visible_when_rep_nonnegative(self):
        from engine.space_caches import is_cache_visible
        vis = json.dumps(["republic"])
        self.assertTrue(is_cache_visible(self._row(vis), {"republic": 0}))
        self.assertTrue(is_cache_visible(self._row(vis), {"republic": 50}))

    def test_faction_hidden_when_rep_negative(self):
        from engine.space_caches import is_cache_visible
        vis = json.dumps(["republic"])
        self.assertFalse(is_cache_visible(self._row(vis), {"republic": -1}))
        self.assertFalse(is_cache_visible(self._row(vis), {}))  # no rep entry → default -1

    def test_faction_visible_if_any_listed_faction_ok(self):
        from engine.space_caches import is_cache_visible
        # Two factions listed; char has rep with the second
        vis = json.dumps(["republic", "jedi_order"])
        char_rep = {"republic": -5, "jedi_order": 10}
        self.assertTrue(is_cache_visible(self._row(vis), char_rep))

    def test_faction_cache_in_dev_pool_visible_to_republic(self):
        """The republic_supply_debris cache in the DEV pool is gated to republic."""
        from engine.space_caches import is_cache_visible, DEV_TEST_CACHE_POOL
        cdef = DEV_TEST_CACHE_POOL["republic_supply_debris"]
        vis_json = json.dumps(cdef.visibility) if isinstance(cdef.visibility, list) else cdef.visibility
        row = {"visibility_factions": vis_json}
        # Republic-friendly PC sees it
        self.assertTrue(is_cache_visible(row, {"republic": 5}))
        # PC with negative rep does not
        self.assertFalse(is_cache_visible(row, {"republic": -3}))

    def test_asteroid_ore_cluster_universal(self):
        """The universal mining cache in the DEV pool is visible to everyone."""
        from engine.space_caches import is_cache_visible, DEV_TEST_CACHE_POOL, _encode_visibility
        cdef = DEV_TEST_CACHE_POOL["asteroid_ore_cluster"]
        row = {"visibility_factions": _encode_visibility(cdef.visibility)}
        self.assertTrue(is_cache_visible(row, {}))
        self.assertTrue(is_cache_visible(row, {"republic": -100}))


# ═════════════════════════════════════════════════════════════════════════════
# 4. TestHarvestMining
# ═════════════════════════════════════════════════════════════════════════════

class TestHarvestMining(unittest.TestCase):
    """harvest_mining: success grants resources + sets cooldown; blocks correctly."""

    def _make_char_and_db(self):
        async def _go():
            db = await _fresh_db()
            char_id = await _seed_account_and_char(db)
            char = _char_dict(char_id)
            return db, char, char_id
        return _run(_go())

    def _spawn_and_get_universal_id(self, db):
        from engine.space_caches import spawn_zone_caches, get_zone_caches, DEV_TEST_ZONE_KEY
        async def _go():
            await spawn_zone_caches(db, DEV_TEST_ZONE_KEY)
            rows = await get_zone_caches(db, DEV_TEST_ZONE_KEY)
            # Find first universal (asteroid_ore_cluster) instance
            for r in rows:
                if r["cache_def_id"] == "asteroid_ore_cluster":
                    return r["cache_instance_id"]
            return None
        return _run(_go())

    def test_mine_not_found(self):
        from engine.space_caches import harvest_mining
        db, char, char_id = self._make_char_and_db()
        result = _run(harvest_mining(db, char, 99999))
        self.assertFalse(result.success)
        self.assertTrue(result.not_found)

    def test_mine_success_yields_resource(self):
        """A successful mine adds a resource to inventory."""
        from engine.space_caches import harvest_mining, DEV_TEST_ZONE_KEY
        db, char, char_id = self._make_char_and_db()
        inst_id = self._spawn_and_get_universal_id(db)
        self.assertIsNotNone(inst_id, "No universal cache spawned")

        # Force the skill check to succeed by patching perform_skill_check.
        from engine.skill_checks import SkillCheckResult
        fake_result = SkillCheckResult(roll=20, difficulty=_MINE_DIFFICULTY,
                                       success=True, margin=10,
                                       critical_success=False, fumble=False,
                                       skill_used="space transports", pool_str="3D")
        with patch("engine.skill_checks.perform_skill_check", return_value=fake_result):
            result = _run(harvest_mining(db, char, inst_id))

        self.assertTrue(result.success, f"Expected success but got: {result.message}")
        self.assertGreater(result.resource_qty, 0)
        self.assertIn(result.resource_type,
                      ("metal", "composite", "rare"),
                      "Resource type not in asteroid_ore_cluster yield table")

        # Confirm inventory in char dict was updated.
        # engine.crafting stores resources in inventory as a JSON dict:
        # {"resources": [{"type": ..., "quantity": ..., "quality": ...}, ...]}
        inv_raw = char.get("inventory") or "{}"
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        resources = inv.get("resources", []) if isinstance(inv, dict) else []
        self.assertTrue(
            any(r.get("type") == result.resource_type for r in resources),
            f"Resource {result.resource_type} not in inventory resources: {resources}",
        )

    def test_mine_sets_cooldown(self):
        """After a successful mine, the cache instance enters cooldown."""
        from engine.space_caches import harvest_mining, get_cache_instance, DEV_TEST_ZONE_KEY
        db, char, char_id = self._make_char_and_db()
        inst_id = self._spawn_and_get_universal_id(db)

        from engine.skill_checks import SkillCheckResult
        fake_result = SkillCheckResult(roll=20, difficulty=_MINE_DIFFICULTY,
                                       success=True, margin=10,
                                       critical_success=False, fumble=False,
                                       skill_used="space transports", pool_str="3D")
        with patch("engine.skill_checks.perform_skill_check", return_value=fake_result):
            result = _run(harvest_mining(db, char, inst_id))

        self.assertTrue(result.success)

        async def _check():
            return await get_cache_instance(db, inst_id)
        row = _run(_check())
        self.assertEqual(row["state"], "cooldown")
        self.assertIsNotNone(row["next_available_at"])
        self.assertGreater(row["next_available_at"], time.time())

    def test_mine_cooldown_block(self):
        """Mining a cooling-down cache returns on_cooldown=True, not success."""
        from engine.space_caches import harvest_mining, set_cache_cooldown, DEV_TEST_ZONE_KEY

        db, char, char_id = self._make_char_and_db()
        inst_id = self._spawn_and_get_universal_id(db)

        # Force into cooldown manually
        async def _force_cool():
            await set_cache_cooldown(db, inst_id, char_id, respawn_minutes=60)
        _run(_force_cool())

        result = _run(harvest_mining(db, char, inst_id))
        self.assertFalse(result.success)
        self.assertTrue(result.on_cooldown)

    def test_mine_wrong_kind_blocked(self):
        """Attempting to mine a non-mining cache returns wrong_kind=True."""
        from engine.space_caches import harvest_mining, DEV_TEST_ZONE_KEY, DEV_TEST_CACHE_POOL

        # Temporarily add a faction_cache kind to the DEV pool for this test
        from engine.space_caches import CacheDef
        fake_def = CacheDef(
            id="test_faction_cache",
            kind="faction_cache",
            visibility="universal",
            respawn_minutes=30,
            density=1,
            yield_table=[],
            rep_reward={},
        )

        async def _go():
            db = await _fresh_db()
            char_id = await _seed_account_and_char(db)
            char = _char_dict(char_id)
            # Insert a row directly with kind=faction_cache via cache_def_id
            # that maps to a patched pool entry
            await db.execute(
                "INSERT INTO space_caches "
                "(zone_key, cache_def_id, state, visibility_factions) "
                "VALUES (?, ?, 'available', NULL)",
                (DEV_TEST_ZONE_KEY, "test_faction_cache"),
            )
            await db.commit()
            rows = await db.fetchall(
                "SELECT cache_instance_id FROM space_caches "
                "WHERE cache_def_id = 'test_faction_cache'"
            )
            inst_id = rows[0]["cache_instance_id"]

            patched_pool = dict(DEV_TEST_CACHE_POOL)
            patched_pool["test_faction_cache"] = fake_def

            with patch("engine.space_caches.get_cache_pool", return_value=patched_pool):
                result = await harvest_mining(db, char, inst_id)
            return result

        result = _run(_go())
        self.assertFalse(result.success)
        self.assertTrue(result.wrong_kind)


# ═════════════════════════════════════════════════════════════════════════════
# 5. TestMineCommand
# ═════════════════════════════════════════════════════════════════════════════

class TestMineCommand(unittest.TestCase):
    """parser/space_commands.MineCommand is registered and dispatches correctly."""

    def test_mine_command_registered(self):
        """MineCommand is in the registry under key 'mine'."""
        from parser.commands import CommandRegistry
        from parser.space_commands import register_space_commands
        reg = CommandRegistry()
        register_space_commands(reg)
        # The registry stores commands; look up 'mine'
        cmd = reg.get("mine")
        self.assertIsNotNone(cmd, "'mine' not found in registry after register_space_commands")

    def test_mine_no_ship_rejects(self):
        """MineCommand with no ship in room sends rejection."""
        from parser.space_commands import MineCommand
        import asyncio

        lines = []

        async def _go():
            cmd = MineCommand()
            ctx = MagicMock()
            ctx.args = ""
            ctx.session.send_line = AsyncMock(side_effect=lambda msg: lines.append(msg))
            ctx.session.character = {"id": 1, "name": "Pilot", "room_id": 5}
            ctx.db.get_ship_by_bridge = AsyncMock(return_value=None)
            await cmd.execute(ctx)

        _run(_go())
        self.assertTrue(
            any("not aboard" in ln for ln in lines),
            f"Expected 'not aboard' message, got: {lines}",
        )

    def test_mine_docked_rejects(self):
        """MineCommand while docked sends rejection."""
        from parser.space_commands import MineCommand

        lines = []

        async def _go():
            cmd = MineCommand()
            ctx = MagicMock()
            ctx.args = ""
            ctx.session.send_line = AsyncMock(side_effect=lambda msg: lines.append(msg))
            ctx.session.character = {"id": 1, "name": "Pilot", "room_id": 5}
            ctx.db.get_ship_by_bridge = AsyncMock(return_value={
                "docked_at": "mos_eisley",
                "systems": "{}",
            })
            await cmd.execute(ctx)

        _run(_go())
        self.assertTrue(
            any("Launch first" in ln or "launch" in ln.lower() for ln in lines),
            f"Expected dock-rejection message, got: {lines}",
        )

    def test_mine_list_no_zone_pool(self):
        """mine (no arg) in a zone with no cache pool shows 'not a wildspace zone'."""
        from parser.space_commands import MineCommand

        lines = []

        async def _go():
            cmd = MineCommand()
            ctx = MagicMock()
            ctx.args = ""
            ctx.session.send_line = AsyncMock(side_effect=lambda msg: lines.append(msg))
            ctx.session.character = {"id": 1, "name": "Pilot", "room_id": 5, "skills": "{}", "attributes": "{}"}
            ctx.db.get_ship_by_bridge = AsyncMock(return_value={
                "docked_at": None,
                "bridge_room_id": 5,
                "systems": json.dumps({"current_zone": "tatooine_orbit"}),
            })
            ctx.db.fetchall = AsyncMock(return_value=[])
            ctx.db.fetchone = AsyncMock(return_value=None)
            ctx.db.execute = AsyncMock(return_value=None)
            ctx.db.commit = AsyncMock(return_value=None)

            # Patch get_all_faction_reps to return empty
            with patch("parser.space_commands.MineCommand.execute",
                       wraps=cmd.execute):
                with patch("engine.organizations.get_all_faction_reps",
                           new=AsyncMock(return_value={})):
                    await cmd.execute(ctx)

        _run(_go())
        self.assertTrue(
            any("wildspace" in ln.lower() or "not registered" in ln.lower()
                or "not a wildspace" in ln.lower() for ln in lines),
            f"Expected wildspace zone message, got: {lines}",
        )

    def test_mine_invalid_id_rejects(self):
        """mine <non-int> shows usage error."""
        from parser.space_commands import MineCommand

        lines = []

        async def _go():
            cmd = MineCommand()
            ctx = MagicMock()
            ctx.args = "not_a_number"
            ctx.session.send_line = AsyncMock(side_effect=lambda msg: lines.append(msg))
            ctx.session.character = {
                "id": 1, "name": "Pilot", "room_id": 5, "skills": "{}", "attributes": "{}"
            }
            ctx.db.get_ship_by_bridge = AsyncMock(return_value={
                "docked_at": None,
                "bridge_room_id": 5,
                "systems": json.dumps({"current_zone": "wildspace_dev_test"}),
            })
            ctx.db.fetchall = AsyncMock(return_value=[])
            ctx.db.execute = AsyncMock(return_value=None)
            ctx.db.commit = AsyncMock(return_value=None)
            with patch("engine.organizations.get_all_faction_reps",
                       new=AsyncMock(return_value={})):
                await cmd.execute(ctx)

        _run(_go())
        self.assertTrue(
            any("Usage" in ln or "usage" in ln or "cache_id" in ln for ln in lines),
            f"Expected usage message, got: {lines}",
        )


if __name__ == "__main__":
    unittest.main()
