# -*- coding: utf-8 -*-
"""
tests/test_t2def_dynamic_hq_handler.py — Drop 16 (2026-06-12)

Covers the dynamic-HQ intel handler hook added to engine/housing.py:
  - purchase_hq spawns a faction-coded handler NPC in room_ids[0]
  - find_handler_in_room locates it for the right faction, returns None for wrong
  - sell_hq removes the handler NPC (no orphan after delete_room)
  - purchase_hq result is {"ok": True, ...} even when the handler is present

Test cases
==========
  1. TestHandlerSpawnedAfterPurchase
     — find_handler_in_room returns non-None; name == "<org_name> Covert Contact"
  2. TestHandlerTagCorrect
     — ai_config_json parses to is_intel_handler==True, faction==org_code (lower)
  3. TestHandlerFactionScoped
     — find_handler_in_room(..., "some_other_faction") returns None
  4. TestHandlerCleanedOnSell
     — after sell_hq, no NPC with is_intel_handler remains; get_npc returns None
  5. TestPurchaseSucceedsWithHandler
     — result["ok"] is True and handler is present simultaneously
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ── Fixtures ──────────────────────────────────────────────────────────────────

ORG_CODE = "test_org"
ORG_NAME = "Test Organization"
ORG_TREASURY = 200_000  # enough for any TIER5_TYPES entry


async def _fresh_db():
    """In-memory DB with full housing + territory schema."""
    from db.database import Database
    from engine.housing import ensure_schema as _hs_schema
    from engine.territory import ensure_territory_schema

    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await _hs_schema(db)
    await ensure_territory_schema(db)
    return db


async def _seed_account(db) -> int:
    cur = await db._db.execute(
        "INSERT OR IGNORE INTO accounts "
        "(username, password_hash, email) VALUES ('tester', 'hash', 't@t.com')"
    )
    await db._db.commit()
    rows = await db.fetchall("SELECT id FROM accounts WHERE username='tester'")
    return rows[0]["id"]


async def _seed_zone(db, name: str = "TestZone") -> int:
    cur = await db._db.execute(
        "INSERT INTO zones (name, properties) VALUES (?, ?)",
        (name, json.dumps({"security": "contested"})),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_room(db, zone_id: int, name: str = "Lot Lobby") -> int:
    cur = await db._db.execute(
        "INSERT INTO rooms (name, zone_id, desc_short, desc_long, properties) "
        "VALUES (?, ?, '', '', ?)",
        (name, zone_id, json.dumps({"security": "contested"})),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_lot(db, room_id: int) -> int:
    """Insert a Tier-5 housing lot that purchase_hq can use."""
    cur = await db._db.execute(
        "INSERT INTO housing_lots "
        "(room_id, planet, label, security, max_homes, current_homes) "
        "VALUES (?, 'Coruscant', 'Test Lot', 'contested', 5, 0)",
        (room_id,),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_org(db, treasury: int = ORG_TREASURY) -> dict:
    await db._db.execute(
        "INSERT INTO organizations "
        "(code, name, org_type, director_managed, leader_id, "
        " hq_room_id, treasury, properties) "
        "VALUES (?, ?, 'faction', 0, NULL, NULL, ?, '{}')",
        (ORG_CODE, ORG_NAME, treasury),
    )
    await db._db.commit()
    return await db.get_organization(ORG_CODE)


async def _seed_leader(db, org: dict, room_id: int) -> dict:
    acct_id = await _seed_account(db)
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(account_id, name, species, room_id, credits, faction_id) "
        "VALUES (?, 'OrgLeader', 'Human', ?, 0, ?)",
        (acct_id, room_id, ORG_CODE),
    )
    await db._db.commit()
    leader_id = cur.lastrowid
    # Set leader on org
    await db._db.execute(
        "UPDATE organizations SET leader_id = ? WHERE code = ?",
        (leader_id, ORG_CODE),
    )
    await db._db.commit()
    return await db.get_character(leader_id)


async def _build_fixture():
    """Return (db, leader_char, lot_id, lot_room_id)."""
    db = await _fresh_db()
    zone_id = await _seed_zone(db)
    lot_room_id = await _seed_room(db, zone_id)
    lot_id = await _seed_lot(db, lot_room_id)
    org = await _seed_org(db)
    leader = await _seed_leader(db, org, lot_room_id)
    return db, leader, lot_id, lot_room_id


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestHandlerSpawnedAfterPurchase(unittest.TestCase):
    """Case 1: find_handler_in_room returns the handler; name is correct."""

    def test_handler_present_and_named(self):
        async def run():
            from engine.housing import purchase_hq
            from engine.intel_handlers import find_handler_in_room

            db, leader, lot_id, _ = await _build_fixture()
            result = await purchase_hq(db, leader, ORG_CODE, "outpost", lot_id)
            self.assertTrue(result.get("ok"), result.get("msg"))

            hq_room_id = result["room_ids"][0]
            handler = await find_handler_in_room(db, hq_room_id, ORG_CODE)
            self.assertIsNotNone(handler, "Handler NPC not found in HQ entrance")
            self.assertEqual(
                handler["name"],
                f"{ORG_NAME} Covert Contact",
            )

        _run(run())


class TestHandlerTagCorrect(unittest.TestCase):
    """Case 2: is_intel_handler True, faction matches org_code (lowercased)."""

    def test_ai_config_tags(self):
        async def run():
            from engine.housing import purchase_hq
            from engine.intel_handlers import INTEL_HANDLER_AI_KEY

            db, leader, lot_id, _ = await _build_fixture()
            result = await purchase_hq(db, leader, ORG_CODE, "outpost", lot_id)
            self.assertTrue(result.get("ok"), result.get("msg"))

            hq_room_id = result["room_ids"][0]
            npcs = await db.get_npcs_in_room(hq_room_id)
            handler_npc = None
            for npc in npcs:
                ai_raw = npc.get("ai_config_json") or "{}"
                ai = json.loads(ai_raw) if isinstance(ai_raw, str) else (ai_raw or {})
                if ai.get(INTEL_HANDLER_AI_KEY):
                    handler_npc = (npc, ai)
                    break
            self.assertIsNotNone(handler_npc, "No handler NPC found in entrance room")
            _, ai = handler_npc
            self.assertTrue(ai[INTEL_HANDLER_AI_KEY])
            self.assertEqual(ai["faction"], ORG_CODE.strip().lower())

        _run(run())


class TestHandlerFactionScoped(unittest.TestCase):
    """Case 3: find_handler_in_room returns None for a different faction."""

    def test_wrong_faction_returns_none(self):
        async def run():
            from engine.housing import purchase_hq
            from engine.intel_handlers import find_handler_in_room

            db, leader, lot_id, _ = await _build_fixture()
            result = await purchase_hq(db, leader, ORG_CODE, "outpost", lot_id)
            self.assertTrue(result.get("ok"), result.get("msg"))

            hq_room_id = result["room_ids"][0]
            handler = await find_handler_in_room(db, hq_room_id, "some_other_faction")
            self.assertIsNone(
                handler,
                "Handler should NOT be reachable by a different faction",
            )

        _run(run())


class TestHandlerCleanedOnSell(unittest.TestCase):
    """Case 4: after sell_hq no orphaned handler NPC; get_npc returns None."""

    def test_no_handler_after_sell(self):
        async def run():
            from engine.housing import purchase_hq, sell_hq
            from engine.intel_handlers import INTEL_HANDLER_AI_KEY

            db, leader, lot_id, _ = await _build_fixture()
            result = await purchase_hq(db, leader, ORG_CODE, "outpost", lot_id)
            self.assertTrue(result.get("ok"), result.get("msg"))

            hq_room_id = result["room_ids"][0]
            # Capture handler NPC id before sale
            npcs = await db.get_npcs_in_room(hq_room_id)
            handler_id = None
            for npc in npcs:
                ai_raw = npc.get("ai_config_json") or "{}"
                ai = json.loads(ai_raw) if isinstance(ai_raw, str) else (ai_raw or {})
                if ai.get(INTEL_HANDLER_AI_KEY):
                    handler_id = npc["id"]
                    break
            self.assertIsNotNone(handler_id, "Handler NPC should exist before sell")

            sell_result = await sell_hq(db, leader, ORG_CODE)
            self.assertTrue(sell_result.get("ok"), sell_result.get("msg"))

            # Handler NPC must be gone
            orphan = await db.get_npc(handler_id)
            self.assertIsNone(
                orphan,
                f"Handler NPC id={handler_id} was not cleaned up by sell_hq",
            )

        _run(run())


class TestPurchaseSucceedsWithHandler(unittest.TestCase):
    """Case 5: purchase result ok==True and handler present simultaneously."""

    def test_purchase_ok_and_handler_present(self):
        async def run():
            from engine.housing import purchase_hq
            from engine.intel_handlers import find_handler_in_room

            db, leader, lot_id, _ = await _build_fixture()
            result = await purchase_hq(db, leader, ORG_CODE, "outpost", lot_id)

            # Purchase must succeed
            self.assertTrue(result.get("ok"), f"purchase_hq failed: {result.get('msg')}")
            self.assertIn("housing_id", result)

            # Handler must also be present (spawn non-fatal)
            hq_room_id = result["room_ids"][0]
            handler = await find_handler_in_room(db, hq_room_id, ORG_CODE)
            self.assertIsNotNone(
                handler,
                "Handler should be present without breaking the purchase",
            )

        _run(run())


if __name__ == "__main__":
    unittest.main()
