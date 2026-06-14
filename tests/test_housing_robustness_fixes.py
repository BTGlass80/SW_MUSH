# -*- coding: utf-8 -*-
"""
tests/test_housing_robustness_fixes.py

Per-drop guard for the 2026-06-14 housing.py robustness drop (from the engine
defect-hunt — docs/design/HANDOFF_engine_defect_hunt_2026-06-14.md). Four
confirmed defects, all in engine/housing.py:

  1. sell_shopfront() deleted exits with `WHERE from_room = ? OR to_room = ?`
     but the exits columns are from_room_id / to_room_id, so SQLite raised
     OperationalError, the room delete on the next line never ran, and every
     shopfront room + its exits LEAKED while the sale still reported success.
     Fix: route through db.delete_room (correct columns, deletes room + exits).

  2. checkout_room() deleted rooms with a raw `DELETE FROM rooms` that did NOT
     clean up exits, so a multi-room residence's internal room<->room exits were
     left dangling. Fix: route through db.delete_room.

  3. is_on_guest_list() did `char_id in guests`, but the guest list is a list of
     dicts {"id": int, "name": str} — `int in [dict, ...]` is always False, so an
     explicitly-added guest was never recognized. Fix: compare on each entry id.

  4. purchase_home() charged the player BEFORE persisting the housing record with
     no try/except and no refund — an INSERT/commit failure ate the credits. Fix:
     wrap the persist + refund on failure (mirrors purchase_home_prestige). Tested
     here as a source-level guard (reaching the INSERT behaviorally needs full
     lot/rep/cost setup; this pins the refund pattern against a revert).

The curated housing tests never asserted post-sale room/exit deletion (the
coverage gap the defect-hunt exploited), so these are new behavioral guards.
"""

import asyncio
import inspect
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


async def _fresh_housing_db():
    """A real in-memory DB with the housing schema, FK enforcement off so a
    minimal player_housing row needs no characters/accounts setup."""
    from db.database import Database
    from engine.housing import ensure_schema
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await ensure_schema(db)
    await db._db.execute("PRAGMA foreign_keys=OFF")
    await db._db.commit()
    return db


async def _mk_room(db, name):
    return await db.create_room(name=name, desc_short="", desc_long="")


async def _exit_ids_touching(db, rid):
    rows = await db._db.execute_fetchall(
        "SELECT id FROM exits WHERE from_room_id = ? OR to_room_id = ?",
        (rid, rid),
    )
    return [r["id"] for r in rows]


class TestSellShopfrontRoomExitLeak(unittest.TestCase):
    """Defect 1: sell_shopfront must actually delete the rooms + their exits."""

    def test_sell_shopfront_deletes_rooms_and_exits(self):
        async def _t():
            from engine.housing import sell_shopfront
            db = await _fresh_housing_db()
            r1 = await _mk_room(db, "Shopfront Floor")
            r2 = await _mk_room(db, "Shopfront Back")
            await db.create_exit(r1, r2, "in", "back room")
            await db.create_exit(r2, r1, "out", "shop floor")
            now = time.time()
            # purchase_price=0 -> refund=0 -> no adjust_credits (no characters row).
            await db._db.execute(
                "INSERT INTO player_housing "
                "(char_id, tier, housing_type, entry_room_id, room_ids, "
                " purchase_price, deposit, created_at) "
                "VALUES (?, 4, 'shopfront', ?, ?, 0, 0, ?)",
                (1, r1, json.dumps([r1, r2]), now),
            )
            await db._db.commit()

            res = await sell_shopfront(db, {"id": 1})
            self.assertTrue(res.get("ok"), f"sell failed: {res}")
            # The bug left these alive (OperationalError on the bad columns).
            self.assertIsNone(await db.get_room(r1), "shopfront room r1 leaked")
            self.assertIsNone(await db.get_room(r2), "shopfront room r2 leaked")
            self.assertEqual(await _exit_ids_touching(db, r1), [],
                             "exits touching r1 leaked")
            self.assertEqual(await _exit_ids_touching(db, r2), [],
                             "exits touching r2 leaked")
            await db._db.close()
        _run(_t())


class TestCheckoutRoomInternalExitLeak(unittest.TestCase):
    """Defect 2: checkout_room must delete a multi-room home's internal exits."""

    def test_checkout_room_deletes_rooms_and_internal_exits(self):
        async def _t():
            from engine.housing import checkout_room
            db = await _fresh_housing_db()
            r1 = await _mk_room(db, "Residence Foyer")
            r2 = await _mk_room(db, "Residence Hall")
            r3 = await _mk_room(db, "Residence Den")
            # internal room<->room exits (the ones the raw DELETE left dangling)
            for a, b in [(r1, r2), (r2, r1), (r2, r3), (r3, r2)]:
                await db.create_exit(a, b, "in", "through")
            now = time.time()
            # deposit=0 -> refund=0 -> no adjust_credits.
            await db._db.execute(
                "INSERT INTO player_housing "
                "(char_id, tier, housing_type, entry_room_id, room_ids, "
                " deposit, rent_overdue, created_at) "
                "VALUES (?, 3, 'private_residence', ?, ?, 0, 0, ?)",
                (1, r1, json.dumps([r1, r2, r3]), now),
            )
            await db._db.commit()

            res = await checkout_room(db, {"id": 1, "inventory": "{}"})
            self.assertTrue(res.get("ok"), f"checkout failed: {res}")
            for rid in (r1, r2, r3):
                self.assertIsNone(await db.get_room(rid), f"room {rid} leaked")
                self.assertEqual(await _exit_ids_touching(db, rid), [],
                                 f"internal exits touching {rid} leaked")
            await db._db.close()
        _run(_t())


class TestGuestListMembership(unittest.TestCase):
    """Defect 3: is_on_guest_list must recognize dict-shaped guest entries."""

    def test_dict_guest_is_recognized(self):
        from engine.housing import is_on_guest_list
        h = {"guest_list": json.dumps(
            [{"id": 7, "name": "Bron"}, {"id": 9, "name": "Vael"}])}
        self.assertTrue(is_on_guest_list(h, 7))
        self.assertTrue(is_on_guest_list(h, 9))
        self.assertFalse(is_on_guest_list(h, 99))

    def test_legacy_bare_int_entry_tolerated(self):
        from engine.housing import is_on_guest_list
        self.assertTrue(is_on_guest_list({"guest_list": json.dumps([7, 9])}, 7))

    def test_empty_guest_list(self):
        from engine.housing import is_on_guest_list
        self.assertFalse(is_on_guest_list({"guest_list": "[]"}, 7))


class TestPurchaseHomeRefundOnPersistFailure(unittest.TestCase):
    """Defect 4 (source guard): purchase_home must refund if persistence fails
    after the charge. A behavioral test would need full lot/rep/cost setup just
    to reach the INSERT; this pins the refund pattern against a revert."""

    def test_purchase_home_refunds_on_persist_failure(self):
        from engine import housing
        src = inspect.getsource(housing.purchase_home)
        self.assertIn("housing_upgrade_refund", src,
                      "purchase_home must refund via adjust_credits on failure")
        self.assertIn("persist_failed", src,
                      "purchase_home must return a persist_failed result on failure")
        # The charge (housing_upgrade) must precede the refund-guarded persist.
        self.assertLess(src.index("housing_upgrade"),
                        src.index("housing_upgrade_refund"),
                        "charge must come before the refund branch")


if __name__ == "__main__":
    unittest.main()
