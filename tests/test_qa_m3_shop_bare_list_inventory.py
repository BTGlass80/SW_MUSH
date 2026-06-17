# -*- coding: utf-8 -*-
"""
tests/test_qa_m3_shop_bare_list_inventory.py — QA M3 regression.

The characters.inventory column's schema default is ``'[]'`` (a bare JSON
list — the legacy/general-items store). The crafting helpers and
``db.add_to_inventory`` instead persist the dict shape
``{"items": [...], "resources": [...]}``. Both shapes are valid and coexist
on disk.

The player-shop code assumed dict-form everywhere: ``_find_in_inventory``
(parser/shop_commands.py) and ``stock_droid`` / ``_is_faction_issued``
(engine/vendor_droids.py) all called ``.get()`` on the parsed inventory. On a
bare-list inventory that raises ``AttributeError``, which the surrounding
``except`` swallowed — so ``shop stock <item>`` reported "not found" for an
item the character was visibly carrying, and even when found the removal step
crashed. Fresh characters (the common case) were the worst hit.

Fix: a single canonical coercion ``engine.items.coerce_inventory`` normalizes
any inventory value (str / dict / bare list / None / garbage) into the dict
shape with two guaranteed list fields. These tests pin:
  1. coerce_inventory across every input shape.
  2. _find_in_inventory finds a general item in a bare-list inventory.
  3. stock_droid removes a general item end-to-end from a bare-list inventory.
  4. stock_droid decrements a resource stack from a dict-form inventory
     (the previously-working path still works — no regression).

No aiosqlite — the DB is faked.
Run: ``python -m pytest tests/test_qa_m3_shop_bare_list_inventory.py``
"""
from __future__ import annotations

import asyncio
import json
import unittest

from engine.items import coerce_inventory
from parser.shop_commands import _find_in_inventory
from engine import vendor_droids


def _run(coro):
    return asyncio.run(coro)


# ─── 1. coerce_inventory shape matrix ────────────────────────────────────────

class TestCoerceInventory(unittest.TestCase):
    def test_bare_list_string_is_items(self):
        out = coerce_inventory("[]")
        self.assertEqual(out, {"items": [], "resources": []})

    def test_bare_list_with_items(self):
        raw = json.dumps([{"key": "rope"}, {"key": "torch"}])
        out = coerce_inventory(raw)
        self.assertEqual(out["items"], [{"key": "rope"}, {"key": "torch"}])
        self.assertEqual(out["resources"], [])

    def test_dict_form_preserved(self):
        raw = json.dumps({"items": [{"key": "rope"}],
                          "resources": [{"type": "metal", "quantity": 3}]})
        out = coerce_inventory(raw)
        self.assertEqual(out["items"], [{"key": "rope"}])
        self.assertEqual(out["resources"], [{"type": "metal", "quantity": 3}])

    def test_actual_dict_object_not_string(self):
        out = coerce_inventory({"items": [1], "resources": [2]})
        self.assertEqual(out, {"items": [1], "resources": [2]})

    def test_actual_list_object_not_string(self):
        out = coerce_inventory([{"key": "rope"}])
        self.assertEqual(out["items"], [{"key": "rope"}])
        self.assertEqual(out["resources"], [])

    def test_none_and_garbage(self):
        self.assertEqual(coerce_inventory(None), {"items": [], "resources": []})
        self.assertEqual(coerce_inventory(""), {"items": [], "resources": []})
        self.assertEqual(coerce_inventory("not json"),
                         {"items": [], "resources": []})
        self.assertEqual(coerce_inventory(42), {"items": [], "resources": []})

    def test_non_list_field_values_coerced(self):
        # A dict whose items/resources are NOT lists must not leak through.
        out = coerce_inventory({"items": "oops", "resources": None})
        self.assertEqual(out, {"items": [], "resources": []})

    def test_missing_keys_default_empty(self):
        out = coerce_inventory({"resources": [{"type": "metal"}]})
        self.assertEqual(out["items"], [])
        self.assertEqual(out["resources"], [{"type": "metal"}])


# ─── 2. _find_in_inventory on a bare-list inventory (the M3 bug) ─────────────

class TestFindInBareListInventory(unittest.TestCase):
    def test_general_item_found_in_bare_list(self):
        # The headline regression: a fresh char's inventory is a bare list.
        char = {
            "id": 1,
            "equipment": "{}",
            "inventory": json.dumps([
                {"key": "scanner_kit", "name": "Scanner Kit", "quality": 60},
            ]),
        }
        key, name, quality, crafter, src = _find_in_inventory(char, "scanner")
        self.assertEqual(key, "scanner_kit")
        self.assertEqual(name, "Scanner Kit")
        self.assertEqual(src, "item")
        self.assertEqual(quality, 60)

    def test_default_empty_bare_list_finds_nothing_gracefully(self):
        char = {"id": 1, "equipment": "{}", "inventory": "[]"}
        key, name, quality, crafter, src = _find_in_inventory(char, "anything")
        self.assertIsNone(key)
        self.assertIsNone(src)

    def test_resource_found_in_dict_form(self):
        char = {
            "id": 1,
            "equipment": "{}",
            "inventory": json.dumps({
                "items": [],
                "resources": [{"type": "durasteel", "quantity": 5, "quality": 40}],
            }),
        }
        key, name, quality, crafter, src = _find_in_inventory(char, "durasteel")
        self.assertEqual(key, "durasteel")
        self.assertEqual(src, "resource")
        self.assertEqual(quality, 40)

    def test_faction_issued_item_skipped(self):
        char = {
            "id": 1,
            "equipment": "{}",
            "inventory": json.dumps([
                {"key": "issue_rifle", "name": "Issued Rifle",
                 "faction_issued": True},
            ]),
        }
        key, *_ = _find_in_inventory(char, "issued rifle")
        self.assertIsNone(key)


# ─── 3 & 4. stock_droid end-to-end on a bare-list inventory ──────────────────

class _FakeDB:
    """Minimal async DB stub for stock_droid: an object store + a char row."""

    def __init__(self, droid_obj):
        self._obj = droid_obj
        self.saved_inventory = None
        self.updated_data = None

    async def get_object(self, droid_id):
        return self._obj if self._obj["id"] == droid_id else None

    async def save_character(self, char_id, **fields):
        if "inventory" in fields:
            self.saved_inventory = fields["inventory"]

    async def update_object(self, droid_id, **fields):
        if "data" in fields:
            self.updated_data = fields["data"]


def _droid_obj(owner_id=1):
    return {
        "id": 7,
        "owner_id": owner_id,
        "data": json.dumps({"tier_key": "gn4", "inventory": []}),
    }


class TestStockDroidBareList(unittest.TestCase):
    def test_stock_general_item_from_bare_list(self):
        char = {
            "id": 1,
            "equipment": "{}",
            "inventory": json.dumps([
                {"key": "scanner_kit", "name": "Scanner Kit", "quality": 60},
                {"key": "rope", "name": "Rope"},
            ]),
        }
        db = _FakeDB(_droid_obj())
        ok, msg = _run(vendor_droids.stock_droid(
            char, 7, "scanner_kit", "Scanner Kit", 60,
            price=100, quantity=1, crafter="", db=db, source_type="item",
        ))
        self.assertTrue(ok, msg)
        # The item was removed from the char and the char persisted.
        self.assertIsNotNone(db.saved_inventory)
        saved = coerce_inventory(db.saved_inventory)
        keys = [it["key"] for it in saved["items"]]
        self.assertNotIn("scanner_kit", keys)
        self.assertIn("rope", keys)
        # The droid now stocks the item.
        droid_data = json.loads(db.updated_data)
        self.assertEqual(droid_data["inventory"][0]["item_key"], "scanner_kit")

    def test_stock_missing_item_from_bare_list_reports_cleanly(self):
        char = {"id": 1, "equipment": "{}", "inventory": "[]"}
        db = _FakeDB(_droid_obj())
        ok, msg = _run(vendor_droids.stock_droid(
            char, 7, "ghost", "Ghost", 50,
            price=100, quantity=1, crafter="", db=db, source_type="item",
        ))
        self.assertFalse(ok)
        self.assertIn("no longer in your inventory", msg)

    def test_stock_resource_decrements_dict_form(self):
        char = {
            "id": 1,
            "equipment": "{}",
            "inventory": json.dumps({
                "items": [],
                "resources": [{"type": "durasteel", "quantity": 5, "quality": 40}],
            }),
        }
        db = _FakeDB(_droid_obj())
        ok, msg = _run(vendor_droids.stock_droid(
            char, 7, "durasteel", "Durasteel", 40,
            price=50, quantity=2, crafter="", db=db, source_type="resource",
        ))
        self.assertTrue(ok, msg)
        saved = coerce_inventory(db.saved_inventory)
        stack = next(r for r in saved["resources"] if r["type"] == "durasteel")
        self.assertEqual(stack["quantity"], 3)  # 5 - 2


if __name__ == "__main__":
    unittest.main()
