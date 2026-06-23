# -*- coding: utf-8 -*-
"""
tests/test_qa_vendor_unstock_buy_bare_list_2026_06_22.py — QA break-it regression.

Sibling-gap to the QA M3 bare-list fix. The M3 pass (2026-06-17,
test_qa_m3_shop_bare_list_inventory.py) routed ``stock_droid`` /
``_find_in_inventory`` through ``engine.items.coerce_inventory`` so a bare-list
inventory (``"[]"`` — the column's schema default, carried by every fresh char)
is normalized to the canonical ``{"items": [...], "resources": [...]}`` shape
WITHOUT dropping its items. But two sibling functions in the same file were
missed:

  * ``unstock_droid`` (returning a stocked item to the owner), and
  * ``buy_from_droid`` (a buyer receiving a purchased item),

both parsed the inventory inline as ``json.loads(...)`` then
``if not isinstance(_, dict): _ = {}`` — which silently WIPES a bare list to an
empty dict before appending the one returned/bought item. Net effect: a player
with a bare-list inventory who unstocks an item from their own droid, or buys an
item from someone else's droid, loses every other item they were carrying
(BLOCKER item-integrity; found by the economy break-it sweep 2026-06-22).

Fix: both now use ``coerce_inventory`` (the single source of truth), matching
``stock_droid``. These tests drive the REAL functions with a faked DB and assert
the pre-existing bare-list items SURVIVE.

No aiosqlite — the DB is faked.
Run: ``python -m pytest tests/test_qa_vendor_unstock_buy_bare_list_2026_06_22.py``
"""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

from engine.items import coerce_inventory
from engine import vendor_droids


def _run(coro):
    return asyncio.run(coro)


class _FakeDB:
    """Minimal async DB stub covering unstock_droid + buy_from_droid."""

    def __init__(self, droid_obj, seller=None):
        self._obj = droid_obj
        self._seller = seller or {}
        self.saved_inventory = None
        self.updated_data = None
        self.logged = []

    async def get_object(self, droid_id):
        return self._obj if self._obj["id"] == droid_id else None

    async def get_character(self, char_id):
        # seller lookup for the faction-modifier path; no faction_id => skipped
        return self._seller

    async def save_character(self, char_id, **fields):
        if "inventory" in fields:
            self.saved_inventory = fields["inventory"]

    async def update_object(self, droid_id, **fields):
        if "data" in fields:
            self.updated_data = fields["data"]

    async def adjust_credits(self, char_id, delta, tag, allow_negative=True):
        # happy-path stub: succeed unless it would go negative under the guard
        new_bal = _FAKE_BAL["v"] + delta
        if not allow_negative and new_bal < 0:
            return None
        _FAKE_BAL["v"] = new_bal
        return new_bal

    async def log_shop_transaction(self, *a, **k):
        self.logged.append((a, k))


_FAKE_BAL = {"v": 0}


def _droid_with_slot(owner_id=1, room_id="mos_eisley_street", slot_qty=1):
    return {
        "id": 7,
        "name": "GN-4 Vendor Droid",
        "owner_id": owner_id,
        "room_id": room_id,
        "data": json.dumps({
            "tier_key": "gn4",
            "inventory": [{
                "slot": 1,
                "item_key": "blaster_pistol",
                "item_name": "Blaster Pistol",
                "quality": 50,
                "crafter": "",
                "quantity": slot_qty,
                "price": 500,
            }],
            "escrow_credits": 0,
        }),
    }


# ─── unstock_droid: bare-list inventory must survive ─────────────────────────

class TestUnstockDroidBareList(unittest.TestCase):
    def test_unstock_preserves_existing_bare_list_items(self):
        # Owner's inventory is a BARE LIST holding two unrelated items.
        char = {
            "id": 1,
            "equipment": "{}",
            "inventory": json.dumps([
                {"key": "medpac", "name": "Medpac", "quality": 50},
                {"key": "clan_token", "name": "Clan Token", "quality": 0},
            ]),
        }
        db = _FakeDB(_droid_with_slot(owner_id=1))
        ok, msg = _run(vendor_droids.unstock_droid(char, 7, 1, 999, db))
        self.assertTrue(ok, msg)
        saved = coerce_inventory(db.saved_inventory)
        keys = [it["key"] for it in saved["items"]]
        # The returned item is present...
        self.assertIn("blaster_pistol", keys)
        # ...AND the two pre-existing items were NOT wiped (the bug).
        self.assertIn("medpac", keys)
        self.assertIn("clan_token", keys)
        self.assertEqual(len(saved["items"]), 3)

    def test_unstock_onto_empty_bare_list_default(self):
        char = {"id": 1, "equipment": "{}", "inventory": "[]"}
        db = _FakeDB(_droid_with_slot(owner_id=1))
        ok, msg = _run(vendor_droids.unstock_droid(char, 7, 1, 1, db))
        self.assertTrue(ok, msg)
        saved = coerce_inventory(db.saved_inventory)
        self.assertEqual([it["key"] for it in saved["items"]], ["blaster_pistol"])

    def test_unstock_preserves_dict_form_items_and_resources(self):
        # Regression guard: the previously-working dict-form path is unchanged.
        char = {
            "id": 1,
            "equipment": "{}",
            "inventory": json.dumps({
                "items": [{"key": "rope", "name": "Rope"}],
                "resources": [{"type": "durasteel", "quantity": 5, "quality": 40}],
            }),
        }
        db = _FakeDB(_droid_with_slot(owner_id=1))
        ok, msg = _run(vendor_droids.unstock_droid(char, 7, 1, 1, db))
        self.assertTrue(ok, msg)
        saved = coerce_inventory(db.saved_inventory)
        keys = [it["key"] for it in saved["items"]]
        self.assertIn("rope", keys)
        self.assertIn("blaster_pistol", keys)
        # resources untouched
        self.assertEqual(saved["resources"][0]["type"], "durasteel")


# ─── buy_from_droid: bare-list inventory must survive ────────────────────────

async def _no_city_tax(*a, **k):
    return (0, None, "")


class TestBuyFromDroidBareList(unittest.TestCase):
    def setUp(self):
        _FAKE_BAL["v"] = 3000  # buyer balance the adjust_credits stub mutates

    def test_buy_preserves_existing_bare_list_items(self):
        buyer = {
            "id": 42,
            "credits": 3000,
            "equipment": "{}",
            "inventory": json.dumps([{"key": "medpac", "name": "Medpac",
                                      "quality": 50}]),
            "skills": "{}",
            "attributes": "{}",
        }
        db = _FakeDB(_droid_with_slot(owner_id=1), seller={})
        with mock.patch("engine.player_cities.apply_city_tax", _no_city_tax):
            ok, msg = _run(vendor_droids.buy_from_droid(buyer, 7, "1", db))
        self.assertTrue(ok, msg)
        saved = coerce_inventory(db.saved_inventory)
        keys = [it["key"] for it in saved["items"]]
        # purchased item present AND the pre-existing medpac NOT wiped (the bug).
        self.assertIn("blaster_pistol", keys)
        self.assertIn("medpac", keys)
        self.assertEqual(len(saved["items"]), 2)

    def test_buy_onto_empty_bare_list_default(self):
        buyer = {
            "id": 42, "credits": 3000, "equipment": "{}",
            "inventory": "[]", "skills": "{}", "attributes": "{}",
        }
        db = _FakeDB(_droid_with_slot(owner_id=1), seller={})
        with mock.patch("engine.player_cities.apply_city_tax", _no_city_tax):
            ok, msg = _run(vendor_droids.buy_from_droid(buyer, 7, "1", db))
        self.assertTrue(ok, msg)
        saved = coerce_inventory(db.saved_inventory)
        self.assertEqual([it["key"] for it in saved["items"]], ["blaster_pistol"])


if __name__ == "__main__":
    unittest.main()
