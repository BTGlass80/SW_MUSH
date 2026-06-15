# -*- coding: utf-8 -*-
"""
tests/test_space_faction_cache.py — Space Wildspace Drop 2b
(faction caches + rep-funnel resolution).

Proves:

  1. TestRepFunnel       — cache rep rewards route through
                           engine.organizations.adjust_rep (personal faction
                           standing), NOT engine.territory.adjust_territory_-
                           influence. Resolves the Drop 1a zone_id=0 placeholder.
  2. TestHarvestFaction  — harvest_faction_cache: no skill check, grants the
                           yield resource, applies rep, sets cooldown; wrong-
                           kind / not-found / cooldown guards.
  3. TestSpawnNoInflate  — spawn_zone_caches counts non-depleted against
                           density, so a harvested (cooled-down) cache does NOT
                           trigger an over-spawn.
  4. TestDispatch        — the `harvest` verb routes to space faction caches
                           when aboard a ship (extend, don't add).
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

from engine.space_caches import CacheDef  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ── fixtures ─────────────────────────────────────────────────────────────────

async def _fresh_db():
    from db.database import Database
    from engine.housing import ensure_schema as _hs_schema
    from engine.space_caches import ensure_schema as _sc_schema

    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await _hs_schema(db)
    await _sc_schema(db)
    return db


async def _seed_char(db) -> int:
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts (username, password_hash, email) "
        "VALUES ('fcuser', 'hash', 'f@e.com')"
    )
    await db._db.commit()
    acct = (await db._db.execute_fetchall(
        "SELECT id FROM accounts WHERE username = 'fcuser'"))[0]["id"]
    await db._db.execute(
        "INSERT INTO characters (account_id, name, attributes, skills, inventory) "
        "VALUES (?, 'FCPilot', '{}', '{}', '{}')",
        (acct,),
    )
    await db._db.commit()
    return (await db._db.execute_fetchall(
        "SELECT id FROM characters WHERE name = 'FCPilot'"))[0]["id"]


def _char_dict(char_id: int) -> dict:
    return {
        "id": char_id,
        "name": "FCPilot",
        "skills": json.dumps({}),
        "attributes": json.dumps({}),
        "inventory": json.dumps({"resources": [], "items": []}),
    }


_TEST_ZONE = "wildspace_dev_test"

# A faction_cache def + a mining def, injected via a patched pool so these
# engine tests are independent of YAML content churn.
_FC_DEF = CacheDef(
    id="test_clone_pod",
    kind="faction_cache",
    visibility=["republic"],
    respawn_minutes=90,
    density=2,
    yield_table=[(100, "metal", 2, 2, 60, 60)],  # deterministic
    rep_reward={"republic": 2},
)
_MINE_DEF = CacheDef(
    id="test_ore",
    kind="mining",
    visibility="universal",
    respawn_minutes=45,
    density=2,
    yield_table=[(100, "metal", 2, 2, 50, 50)],
    rep_reward={},
)
_PATCHED_POOL = {"test_clone_pod": _FC_DEF, "test_ore": _MINE_DEF}


async def _insert_cache(db, def_id, state="available"):
    await db.execute(
        "INSERT INTO space_caches (zone_key, cache_def_id, state, visibility_factions) "
        "VALUES (?, ?, ?, NULL)",
        (_TEST_ZONE, def_id, state),
    )
    await db.commit()
    return (await db.fetchall(
        "SELECT cache_instance_id FROM space_caches WHERE cache_def_id = ? "
        "ORDER BY cache_instance_id DESC LIMIT 1", (def_id,)
    ))[0]["cache_instance_id"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. TestRepFunnel
# ═══════════════════════════════════════════════════════════════════════════

class TestRepFunnel(unittest.TestCase):
    """Cache rep goes through adjust_rep, never adjust_territory_influence."""

    def test_faction_cache_calls_adjust_rep_not_territory(self):
        async def _go():
            db = await _fresh_db()
            char = _char_dict(await _seed_char(db))
            inst = await _insert_cache(db, "test_clone_pod")

            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL), \
                 patch("engine.organizations.adjust_rep",
                       new=AsyncMock(return_value=2)) as m_rep, \
                 patch("engine.territory.adjust_territory_influence",
                       new=AsyncMock(return_value=0)) as m_terr:
                result = await sc.harvest_faction_cache(db, char, inst)

            self.assertTrue(result.success)
            # adjust_rep called for the republic reward...
            self.assertTrue(m_rep.called)
            args, kwargs = m_rep.call_args
            self.assertEqual(args[1], "republic")          # faction_code
            self.assertEqual(kwargs.get("delta"), 2)       # delta
            # ...and the phantom zone_id=0 territory path is NEVER used.
            m_terr.assert_not_called()
            await db.close()

        _run(_go())

    def test_mining_rep_also_uses_adjust_rep(self):
        """The mining rep path was the original zone_id=0 site — it now uses
        adjust_rep too."""
        async def _go():
            db = await _fresh_db()
            char = _char_dict(await _seed_char(db))
            # Mining def WITH a rep reward to exercise the funnel.
            mine_rep = CacheDef(
                id="test_ore", kind="mining", visibility="universal",
                respawn_minutes=45, density=1,
                yield_table=[(100, "metal", 1, 1, 50, 50)],
                rep_reward={"republic": 1},
            )
            inst = await _insert_cache(db, "test_ore")
            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value={"test_ore": mine_rep}), \
                 patch("engine.skill_checks.perform_skill_check") as m_chk, \
                 patch("engine.organizations.adjust_rep",
                       new=AsyncMock(return_value=1)) as m_rep, \
                 patch("engine.territory.adjust_territory_influence",
                       new=AsyncMock(return_value=0)) as m_terr:
                m_chk.return_value = MagicMock(
                    fumble=False, critical_success=False, roll=20)
                result = await sc.harvest_mining(db, char, inst)
            self.assertTrue(result.success)
            self.assertTrue(m_rep.called)
            m_terr.assert_not_called()
            await db.close()

        _run(_go())

    def test_rep_actually_lands_on_character(self):
        """End-to-end against a real (seeded) org: a non-member's
        attributes.faction_rep gains the reward and the visibility gate would
        then see it."""
        async def _go():
            db = await _fresh_db()
            await db.create_organization("republic", "Galactic Republic")
            char = _char_dict(await _seed_char(db))
            inst = await _insert_cache(db, "test_clone_pod")
            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL):
                result = await sc.harvest_faction_cache(db, char, inst)
            self.assertTrue(result.success)
            self.assertEqual(result.rep_rewards, {"republic": 2})
            attrs = json.loads(char["attributes"])
            self.assertEqual(attrs.get("faction_rep", {}).get("republic"), 2)
            await db.close()

        _run(_go())


# ═══════════════════════════════════════════════════════════════════════════
# 2. TestHarvestFaction
# ═══════════════════════════════════════════════════════════════════════════

class TestHarvestFaction(unittest.TestCase):

    def test_grants_resource_and_cooldown_no_skillcheck(self):
        async def _go():
            db = await _fresh_db()
            char = _char_dict(await _seed_char(db))
            inst = await _insert_cache(db, "test_clone_pod")
            from engine import space_caches as sc
            # perform_skill_check MUST NOT be called (faction caches are markers).
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL), \
                 patch("engine.skill_checks.perform_skill_check") as m_chk:
                result = await sc.harvest_faction_cache(db, char, inst)
            self.assertFalse(m_chk.called, "faction cache must not roll a skill check")
            self.assertTrue(result.success)
            self.assertEqual(result.resource_type, "metal")
            self.assertEqual(result.resource_qty, 2)
            # Resource persisted.
            inv = json.loads(char["inventory"])
            self.assertTrue(any(r.get("type") == "metal"
                                for r in inv.get("resources", [])))
            # Cooldown set.
            row = await sc.get_cache_instance(db, inst)
            self.assertEqual(row["state"], "cooldown")
            self.assertEqual(row["harvest_count"], 1)
            await db.close()

        _run(_go())

    def test_wrong_kind_blocks_mining_node(self):
        """harvest_faction_cache on a kind=mining cache → wrong_kind."""
        async def _go():
            db = await _fresh_db()
            char = _char_dict(await _seed_char(db))
            inst = await _insert_cache(db, "test_ore")
            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL):
                result = await sc.harvest_faction_cache(db, char, inst)
            self.assertFalse(result.success)
            self.assertTrue(result.wrong_kind)
            await db.close()

        _run(_go())

    def test_mining_wrong_kind_blocks_faction_cache(self):
        """Symmetric guard: harvest_mining on a faction_cache → wrong_kind."""
        async def _go():
            db = await _fresh_db()
            char = _char_dict(await _seed_char(db))
            inst = await _insert_cache(db, "test_clone_pod")
            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL):
                result = await sc.harvest_mining(db, char, inst)
            self.assertFalse(result.success)
            self.assertTrue(result.wrong_kind)
            await db.close()

        _run(_go())

    def test_not_found(self):
        async def _go():
            db = await _fresh_db()
            char = _char_dict(await _seed_char(db))
            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL):
                result = await sc.harvest_faction_cache(db, char, 99999)
            self.assertTrue(result.not_found)
            await db.close()

        _run(_go())

    def test_cooldown_block(self):
        async def _go():
            db = await _fresh_db()
            char = _char_dict(await _seed_char(db))
            inst = await _insert_cache(db, "test_clone_pod")
            # Force cooldown far in the future.
            await db.execute(
                "UPDATE space_caches SET state='cooldown', next_available_at=? "
                "WHERE cache_instance_id=?",
                (int(time.time()) + 9999, inst),
            )
            await db.commit()
            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL):
                result = await sc.harvest_faction_cache(db, char, inst)
            self.assertTrue(result.on_cooldown)
            self.assertFalse(result.success)
            await db.close()

        _run(_go())


# ═══════════════════════════════════════════════════════════════════════════
# 3. TestSpawnNoInflate
# ═══════════════════════════════════════════════════════════════════════════

class TestSpawnNoInflate(unittest.TestCase):
    """spawn_zone_caches counts non-depleted against density: a cooled-down
    cache occupies its slot, so no over-spawn (the Drop 1a inflation bug)."""

    def test_cooldown_counts_against_density(self):
        async def _go():
            db = await _fresh_db()
            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL):
                created1 = await sc.spawn_zone_caches(db, _TEST_ZONE)
                # density: clone_pod 2 + ore 2 = 4.
                self.assertEqual(created1, 4)

                # Send one available clone_pod to cooldown (simulate a harvest).
                row = (await db.fetchall(
                    "SELECT cache_instance_id FROM space_caches "
                    "WHERE cache_def_id='test_clone_pod' AND state='available' LIMIT 1"))[0]
                await db.execute(
                    "UPDATE space_caches SET state='cooldown' WHERE cache_instance_id=?",
                    (row["cache_instance_id"],))
                await db.commit()

                # Re-spawn: the cooled-down node still counts → NO new node.
                created2 = await sc.spawn_zone_caches(db, _TEST_ZONE)
                self.assertEqual(created2, 0, "cooldown node must count against density")

                total = (await db.fetchall(
                    "SELECT COUNT(*) AS c FROM space_caches WHERE zone_key=?",
                    (_TEST_ZONE,)))[0]["c"]
                self.assertEqual(total, 4, "no density inflation")
            await db.close()

        _run(_go())

    def test_depleted_does_not_count(self):
        async def _go():
            db = await _fresh_db()
            from engine import space_caches as sc
            with patch("engine.space_caches.get_cache_pool",
                       return_value=_PATCHED_POOL):
                await sc.spawn_zone_caches(db, _TEST_ZONE)
                row = (await db.fetchall(
                    "SELECT cache_instance_id FROM space_caches "
                    "WHERE cache_def_id='test_ore' AND state='available' LIMIT 1"))[0]
                await db.execute(
                    "UPDATE space_caches SET state='depleted' WHERE cache_instance_id=?",
                    (row["cache_instance_id"],))
                await db.commit()
                # Depleted frees a slot → spawn refills exactly one ore node.
                created = await sc.spawn_zone_caches(db, _TEST_ZONE)
                self.assertEqual(created, 1)
            await db.close()

        _run(_go())


# ═══════════════════════════════════════════════════════════════════════════
# 4. TestDispatch — `harvest` verb routes to space when aboard a ship
# ═══════════════════════════════════════════════════════════════════════════

class TestDispatch(unittest.TestCase):

    def test_handle_space_harvest_false_when_not_aboard(self):
        """No ship → handler declines, ground harvest proceeds."""
        async def _go():
            from parser.space_commands import handle_space_harvest
            ctx = MagicMock()
            ctx.session.character = {"id": 1, "room_id": 5}
            ctx.db.get_ship_by_bridge = AsyncMock(return_value=None)
            handled = await handle_space_harvest(ctx)
            self.assertFalse(handled)

        _run(_go())

    def test_handle_space_harvest_true_when_docked(self):
        """Aboard a docked ship → handler takes it (tells player to launch)."""
        async def _go():
            from parser.space_commands import handle_space_harvest
            ctx = MagicMock()
            ctx.session.character = {"id": 1, "room_id": 5}
            ctx.session.send_line = AsyncMock()
            ctx.db.get_ship_by_bridge = AsyncMock(
                return_value={"docked_at": 7, "systems": "{}"})
            handled = await handle_space_harvest(ctx)
            self.assertTrue(handled)
            ctx.session.send_line.assert_awaited()

        _run(_go())

    def test_ground_harvest_command_still_registered(self):
        from parser.commands import CommandRegistry
        from parser.harvest_command import register_harvest_command
        reg = CommandRegistry()
        register_harvest_command(reg)
        self.assertIsNotNone(reg.get("harvest"))


if __name__ == "__main__":
    unittest.main()
