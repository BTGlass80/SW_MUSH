# -*- coding: utf-8 -*-
"""
tests/test_vendor_sell_carried.py — Vendor V1 Part A: selling a carried
inventory item to an NPC vendor (`sell <item name>`), not just the equipped
weapon.

Two layers:
  1. PURE tests for the extracted helpers in ``parser.builtin_commands``
     (`_npc_salvage_price`, `_find_carried_item_by_name`, `_resolve_carried_sale`).
  2. Integration tests for ``SellCommand._sell_carried_item`` against a fake
     ctx/session/db, with `resolve_bargain_check` + the weapons registry
     patched deterministic. The §1.3 craft-refusal guard runs for real.

Run: ``python3 -m unittest tests.test_vendor_sell_carried``
(No aiosqlite — the DB is faked.)
"""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from parser import builtin_commands as BC


def _run(coro):
    return asyncio.run(coro)


# ─── Pure helper tests ───────────────────────────────────────────────────────

class TestSalvagePrice(unittest.TestCase):
    def _item(self, cond=100, maxc=100, q=50):
        return SimpleNamespace(condition=cond, max_condition=maxc, quality=q)

    def test_condition_scaling(self):
        # 25% at broken → 50% at new, off base cost.
        self.assertEqual(BC._npc_salvage_price(self._item(100, 100, 50), 1000), 500)
        self.assertEqual(BC._npc_salvage_price(self._item(0, 100, 50), 1000), 250)
        self.assertEqual(BC._npc_salvage_price(self._item(50, 100, 50), 1000), 375)

    def test_quality_bonus(self):
        self.assertEqual(BC._npc_salvage_price(self._item(100, 100, 80), 1000), 650)  # ×1.3
        self.assertEqual(BC._npc_salvage_price(self._item(100, 100, 60), 1000), 575)  # ×1.15
        self.assertEqual(BC._npc_salvage_price(self._item(100, 100, 59), 1000), 500)  # none

    def test_floor(self):
        # Never below 10, even for a near-worthless broken item.
        self.assertEqual(BC._npc_salvage_price(self._item(0, 100, 50), 10), 10)


class TestFindCarriedItem(unittest.TestCase):
    def setUp(self):
        self.items = [
            {"key": "blaster_pistol", "name": "Blaster Pistol"},
            {"key": "medpac_1", "name": "Medpac"},
            "not-a-dict",
        ]

    def test_exact_name(self):
        self.assertEqual(BC._find_carried_item_by_name(self.items, "medpac")["key"], "medpac_1")

    def test_exact_key(self):
        self.assertEqual(BC._find_carried_item_by_name(self.items, "blaster_pistol")["key"], "blaster_pistol")

    def test_prefix(self):
        self.assertEqual(BC._find_carried_item_by_name(self.items, "blas")["key"], "blaster_pistol")

    def test_case_insensitive(self):
        self.assertEqual(BC._find_carried_item_by_name(self.items, "BLASTER PISTOL")["key"], "blaster_pistol")

    def test_no_match_and_empty(self):
        self.assertIsNone(BC._find_carried_item_by_name(self.items, "lightsaber"))
        self.assertIsNone(BC._find_carried_item_by_name(self.items, ""))


class _FakeWeaponData:
    def __init__(self, cost, name, weapon_type="ranged"):
        self.cost = cost
        self.name = name
        self.weapon_type = weapon_type


class _FakeWR:
    def __init__(self, table):
        self._t = table

    def get(self, key):
        return self._t.get(key)


class TestResolveCarriedSale(unittest.TestCase):
    def setUp(self):
        self.wr = _FakeWR({
            "blaster_pistol": _FakeWeaponData(500, "Blaster Pistol", "ranged"),
            "combat_armor": _FakeWeaponData(800, "Combat Armor", "armor"),
        })

    def test_registry_weapon(self):
        inst, base, name = BC._resolve_carried_sale(
            {"key": "blaster_pistol", "name": "My Blaster"}, self.wr)
        self.assertIsNotNone(inst)
        self.assertEqual(base, 500)
        self.assertEqual(name, "Blaster Pistol")  # registry display name

    def test_registry_armor(self):
        inst, base, name = BC._resolve_carried_sale({"key": "combat_armor"}, self.wr)
        self.assertEqual(base, 800)
        self.assertEqual(name, "Combat Armor")

    def test_registry_picks_up_condition_quality_crafter(self):
        inst, base, name = BC._resolve_carried_sale(
            {"key": "blaster_pistol", "condition": 40, "quality": 80, "crafter": "Bob"},
            self.wr)
        self.assertEqual(inst.condition, 40)
        self.assertEqual(inst.quality, 80)
        self.assertEqual(inst.crafter, "Bob")

    def test_stored_value_nonregistry(self):
        inst, base, name = BC._resolve_carried_sale(
            {"key": "kyber_gem", "name": "Kyber Gem", "value": 300}, self.wr)
        self.assertIsNotNone(inst)
        self.assertEqual(base, 300)
        self.assertEqual(name, "Kyber Gem")
        self.assertEqual(inst.quality, 50)  # synthetic

    def test_no_value_refused(self):
        inst, base, name = BC._resolve_carried_sale(
            {"key": "quest_holocron", "name": "Mysterious Holocron"}, self.wr)
        self.assertIsNone(inst)
        self.assertIsNone(base)
        self.assertEqual(name, "Mysterious Holocron")


# ─── Integration tests (fake ctx/db; bargain + registry patched) ─────────────

class _Sess:
    def __init__(self, char):
        self.character = char
        self.sent = []

    async def send_line(self, m):
        self.sent.append(m)

    def text(self):
        return "\n".join(self.sent)


class _FakeDB:
    def __init__(self, items, credits=100):
        self._items = [dict(i) for i in items]
        self._credits = credits
        self.removed = []
        self.adjustments = []

    async def get_inventory(self, cid):
        return [dict(i) for i in self._items]

    async def get_npcs_in_room(self, rid):
        return []

    async def remove_from_inventory(self, cid, key):
        for i, it in enumerate(self._items):
            if it.get("key") == key:
                self._items.pop(i)
                self.removed.append(key)
                return True
        return False

    async def adjust_credits(self, cid, delta, source):
        self.adjustments.append((delta, source))
        self._credits += delta
        return self._credits

    async def fetchall(self, *a, **k):
        # apply_city_tax → get_city_for_room queries this; [] → no city → 0 tax.
        return []


class _Ctx:
    def __init__(self, db, sess, args=""):
        self.db = db
        self.session = sess
        self.args = args


def _patched_bargain(char, price, **kw):
    # No haggle modifier — echo the price so sale math is deterministic.
    return {"adjusted_price": price, "price_modifier_pct": 0,
            "message": "(no haggle)", "player_pool": "3D", "player_roll": 10,
            "npc_pool": "3D", "npc_roll": 10}


_WR = _FakeWR({
    "blaster_pistol": _FakeWeaponData(1000, "Blaster Pistol", "ranged"),
})


def _char():
    return {"id": 7, "name": "Mara", "room_id": 10, "credits": 100}


class TestSellCarriedItem(unittest.TestCase):

    def _run_sale(self, items, name, credits=100):
        db = _FakeDB(items, credits=credits)
        sess = _Sess(_char())
        ctx = _Ctx(db, sess, args=name)
        cmd = BC.SellCommand()
        with patch("engine.weapons.get_weapon_registry", return_value=_WR), \
             patch("engine.skill_checks.resolve_bargain_check", _patched_bargain):
            _run(cmd._sell_carried_item(ctx, name))
        return db, sess

    def test_happy_path_weapon(self):
        db, sess = self._run_sale(
            [{"key": "blaster_pistol", "name": "Blaster Pistol"}], "blaster pistol")
        # q50 full-condition off base 1000 → 500
        self.assertEqual(db.removed, ["blaster_pistol"])
        self.assertEqual(db.adjustments, [(500, "item_sale")])
        self.assertIn("Sold Blaster Pistol for 500 credits", sess.text())
        self.assertIn("Balance: 600 credits", sess.text())

    def test_crafted_good_is_refused(self):
        db, sess = self._run_sale(
            [{"key": "blaster_pistol", "name": "Ace's Blaster",
              "crafter": "Ace", "quality": 85}], "ace")
        self.assertEqual(db.removed, [])          # not sold
        self.assertEqual(db.adjustments, [])      # no credit
        self.assertIn("Too well-made for scrap", sess.text())

    def test_valueless_item_refused(self):
        db, sess = self._run_sale(
            [{"key": "quest_holo", "name": "Mysterious Holocron"}], "mysterious")
        self.assertEqual(db.removed, [])
        self.assertEqual(db.adjustments, [])
        self.assertIn("no use for the Mysterious Holocron", sess.text())

    def test_stored_value_item_sells(self):
        db, sess = self._run_sale(
            [{"key": "kyber_gem", "name": "Kyber Gem", "value": 300}], "kyber gem")
        # q50 full-cond off base 300 → 150
        self.assertEqual(db.removed, ["kyber_gem"])
        self.assertEqual(db.adjustments, [(150, "item_sale")])
        self.assertIn("Sold Kyber Gem for 150 credits", sess.text())

    def test_quantity_stack_sells_whole(self):
        db, sess = self._run_sale(
            [{"key": "kyber_gem", "name": "Kyber Gem", "value": 300, "qty": 3}],
            "kyber gem")
        # 150/unit × 3 = 450
        self.assertEqual(db.adjustments, [(450, "item_sale")])
        self.assertIn("Sold 3x Kyber Gem for 450 credits", sess.text())

    def test_not_carrying_named_item(self):
        db, sess = self._run_sale(
            [{"key": "rope", "name": "Rope"}], "lightsaber")
        self.assertEqual(db.removed, [])
        self.assertEqual(db.adjustments, [])
        self.assertIn('not carrying anything called "lightsaber"', sess.text())

    def test_armor_hint_when_not_carried(self):
        db, sess = self._run_sale([], "armor")
        self.assertEqual(db.adjustments, [])
        self.assertIn("unequip armor", sess.text())


if __name__ == "__main__":
    unittest.main()
