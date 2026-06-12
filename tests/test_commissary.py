# -*- coding: utf-8 -*-
"""
tests/test_commissary.py — Drop 3 A4 (commissary): the faction requisition sink.

A sworn faction member requisitions rank-appropriate gear from their commissary
for credits — the `commissary_purchase` sink the economy audit (report A4) calls
for, on the existing org-membership/rank machinery. No schema change.

Covers: the pure stock/helpers (well-formed catalog, era-cleanness, rank
filtering, the Jedi-has-no-commissary rule); `purchase_commissary` branches
against a recording stub (buy debits `commissary_purchase` + grants the item;
no-commissary / unknown / rank-locked / insufficient → no charge; refund on
grant failure); a real in-memory `Database` path proving the ledger debit + the
real inventory grant; and structural pins (the sink tag, the registration).
"""

import os
import sys
import json
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.commissary import (                                        # noqa: E402
    COMMISSARY_STOCK, faction_has_commissary, commissary_item,
    commissary_stock_for, commissary_status_lines, purchase_commissary,
    commissary_vendor_payload,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pure stock / helpers
# ─────────────────────────────────────────────────────────────────────────────
class TestCommissaryPure(unittest.TestCase):
    def test_stock_well_formed(self):
        self.assertTrue(COMMISSARY_STOCK)
        for faction, items in COMMISSARY_STOCK.items():
            self.assertEqual(faction, faction.lower())
            self.assertTrue(items, "%s commissary must have stock" % faction)
            keys = [it["key"] for it in items]
            self.assertEqual(len(keys), len(set(keys)),
                             "%s has duplicate keys" % faction)
            for it in items:
                self.assertGreater(int(it["cost"]), 0)        # it's a sink
                self.assertIn(int(it["min_rank"]), (0, 1))
                self.assertEqual(it["key"], it["key"].lower())
                self.assertIn(it["slot"], ("weapon", "armor", "misc"))

    def test_jedi_has_no_commissary(self):
        # The Order is austere — issues, never sells.
        self.assertFalse(faction_has_commissary("jedi_order"))
        self.assertFalse(faction_has_commissary("independent"))
        self.assertFalse(faction_has_commissary(""))
        self.assertTrue(faction_has_commissary("republic"))
        self.assertTrue(faction_has_commissary("CIS"))   # case-insensitive

    def test_era_clean(self):
        blob = ""
        for items in COMMISSARY_STOCK.values():
            for it in items:
                blob += (it["key"] + " " + it["name"] + " "
                         + it.get("desc", "")).lower() + " "
        for banned in ("empire", "imperial", "rebel", "tie ", "x-wing",
                       "stormtrooper", "sith"):
            self.assertNotIn(banned, blob)

    def test_item_lookup_case_insensitive(self):
        self.assertIsNone(commissary_item("republic", "nope"))
        it = commissary_item("republic", "DC17_PISTOL")
        self.assertEqual(it["name"], "DC-17 Hand Blaster")
        self.assertEqual(it["cost"], 500)

    def test_stock_filtered_by_rank(self):
        # republic: 2 rank-0 items, 2 rank-1 items.
        at0 = commissary_stock_for("republic", 0)
        at1 = commissary_stock_for("republic", 1)
        self.assertEqual({it["key"] for it in at0},
                         {"republic_uniform", "dc17_pistol"})
        self.assertEqual(len(at1), 4)
        # Non-commissary faction → empty.
        self.assertEqual(commissary_stock_for("jedi_order", 5), [])

    def test_status_lines_marks(self):
        # No commissary → a single explanatory line.
        st = commissary_status_lines("jedi_order", 2, 10_000)
        self.assertTrue(any(isinstance(l, str) and "does not maintain" in l
                            for l in st))
        # Rank 0, modest funds: rank-1 gear shows 'rank', rank-0 shows buy/short.
        rows = [r for r in commissary_status_lines("republic", 0, 200)
                if not isinstance(r, str)]
        marks = {r["key"]: r["mark"] for r in rows}
        self.assertEqual(marks["republic_uniform"], "buy")     # 150 <= 200, rank 0
        self.assertEqual(marks["dc17_pistol"], "short")        # 500 > 200, rank 0
        self.assertEqual(marks["dc15_blaster_rifle"], "rank")  # min_rank 1 > 0


# ─────────────────────────────────────────────────────────────────────────────
# purchase_commissary — branches (recording stub)
# ─────────────────────────────────────────────────────────────────────────────
class _StubDB:
    def __init__(self, fail_grant=False):
        self.credit_log = []   # (delta, source)
        self.granted = []      # item dicts
        self.fail_grant = fail_grant

    async def adjust_credits(self, cid, delta, source):
        self.credit_log.append((delta, source))
        return 100_000 + delta

    async def add_to_inventory(self, cid, item):
        if self.fail_grant:
            raise RuntimeError("grant boom")
        self.granted.append(item)


class TestPurchaseBranches(unittest.TestCase):
    def _char(self, credits=100_000):
        return {"id": 5, "credits": credits}

    def test_buy_debits_and_grants(self):
        db = _StubDB()
        char = self._char()
        res = _run(purchase_commissary(db, char, "republic", 1, "dc17_pistol"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["name"], "DC-17 Hand Blaster")
        self.assertEqual(db.credit_log, [(-500, "commissary_purchase")])
        self.assertEqual(len(db.granted), 1)
        g = db.granted[0]
        self.assertEqual(g["key"], "dc17_pistol")
        self.assertEqual(g["slot"], "weapon")
        self.assertEqual(g["faction_code"], "republic")
        self.assertTrue(g["commissary"])

    def test_no_commissary_no_charge(self):
        db = _StubDB()
        res = _run(purchase_commissary(db, self._char(), "jedi_order", 3, "anything"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "no_commissary")
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.granted, [])

    def test_unknown_item_no_charge(self):
        db = _StubDB()
        res = _run(purchase_commissary(db, self._char(), "republic", 5, "nope"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "unknown")
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.granted, [])

    def test_rank_locked_no_charge(self):
        db = _StubDB()
        # dc15_blaster_rifle is min_rank 1; a rank-0 member can't requisition it.
        res = _run(purchase_commissary(db, self._char(), "republic", 0,
                                       "dc15_blaster_rifle"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "rank_locked")
        self.assertEqual(res["min_rank"], 1)
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.granted, [])

    def test_insufficient_no_charge(self):
        db = _StubDB()
        char = self._char(credits=499)   # dc17_pistol is 500
        res = _run(purchase_commissary(db, char, "republic", 1, "dc17_pistol"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "insufficient")
        self.assertEqual(res["short"], 1)
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.granted, [])

    def test_refund_on_grant_failure(self):
        db = _StubDB(fail_grant=True)
        res = _run(purchase_commissary(db, self._char(), "republic", 1, "dc17_pistol"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "grant_failed")
        sources = [s for _, s in db.credit_log]
        self.assertIn("commissary_purchase", sources)
        self.assertIn("commissary_purchase_refund", sources)


# ─────────────────────────────────────────────────────────────────────────────
# Real in-memory Database — ledger debit + real inventory grant
# ─────────────────────────────────────────────────────────────────────────────
_OPEN_DBS = []


async def _real_db(credits=100_000):
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db._db.execute(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, credits INTEGER "
        "DEFAULT 0, inventory TEXT DEFAULT '{\"items\": []}')")
    await db._db.execute(
        """CREATE TABLE credit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, char_id INTEGER NOT NULL,
            delta INTEGER NOT NULL, source TEXT NOT NULL,
            balance INTEGER NOT NULL, created_at REAL NOT NULL)""")
    await db._db.execute(
        """CREATE TABLE economy_config (
            key TEXT PRIMARY KEY, value REAL NOT NULL, updated_at REAL NOT NULL)""")
    await db._db.execute(
        "INSERT INTO characters (id, credits, inventory) VALUES (1, ?, ?)",
        (credits, '{"items": []}'))
    await db._db.commit()
    _OPEN_DBS.append(db)
    return db


class TestRealDBHappyPath(unittest.TestCase):
    def test_requisition_debits_ledger_and_grants_item(self):
        async def go():
            db = await _real_db(credits=100_000)
            char = {"id": 1, "credits": 100_000}
            # Rank 1 republic member requisitions a rifle (min_rank 1, 1200 cr).
            res = await purchase_commissary(db, char, "republic", 1,
                                            "dc15_blaster_rifle")
            self.assertTrue(res["ok"])

            # Credits actually moved, logged under the sink tag.
            crows = await db._db.execute_fetchall(
                "SELECT delta, source FROM credit_log WHERE char_id = 1")
            self.assertEqual(crows[0]["source"], "commissary_purchase")
            self.assertEqual(crows[0]["delta"], -1200)

            # The item is really in inventory.
            row = await db._db.execute_fetchall(
                "SELECT inventory FROM characters WHERE id = 1")
            inv = json.loads(row[0]["inventory"])
            keys = [i.get("key") for i in inv["items"]]
            self.assertIn("dc15_blaster_rifle", keys)

            try:
                await db.close()
                _OPEN_DBS.remove(db)
            except Exception:
                pass
        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# commissary_vendor_payload — shape, marks, purity
# ─────────────────────────────────────────────────────────────────────────────
class TestVendorPayload(unittest.TestCase):
    def test_shape_and_constants(self):
        p = commissary_vendor_payload("republic", 1, 5000)
        self.assertEqual(p["mode"], "vendor")
        self.assertEqual(p["vendor_kind"], "commissary")
        self.assertEqual(p["faction_code"], "republic")
        self.assertEqual(p["rank_level"], 1)
        self.assertEqual(p["balance"], 5000)
        self.assertIn("items", p)

    def test_faction_code_normalised_lower(self):
        p = commissary_vendor_payload("CIS", 0, 0)
        self.assertEqual(p["faction_code"], "cis")

    def test_item_keys_present(self):
        p = commissary_vendor_payload("republic", 1, 5000)
        for it in p["items"]:
            for k in ("key", "name", "slot", "cost", "min_rank", "desc", "mark"):
                self.assertIn(k, it, "item missing key %r" % k)

    def test_no_header_strings_in_items(self):
        # commissary_status_lines emits a header string as the first row;
        # commissary_vendor_payload must strip all string rows.
        p = commissary_vendor_payload("republic", 1, 5000)
        for it in p["items"]:
            self.assertIsInstance(it, dict)

    def test_marks_by_rank_and_balance(self):
        # republic: rank-0 items are republic_uniform (150) + dc17_pistol (500);
        # rank-1 items are dc15_blaster_rifle (1200) + republic_light_armor (900).
        # With rank=0, balance=200: uniform→buy, pistol→short, rank-1 items→rank.
        p = commissary_vendor_payload("republic", 0, 200)
        marks = {it["key"]: it["mark"] for it in p["items"]}
        self.assertEqual(marks["republic_uniform"], "buy")      # 150 <= 200, rank 0
        self.assertEqual(marks["dc17_pistol"], "short")         # 500 > 200, rank 0
        self.assertEqual(marks["dc15_blaster_rifle"], "rank")   # min_rank 1 > 0
        self.assertEqual(marks["republic_light_armor"], "rank") # min_rank 1 > 0

    def test_rank_locked_item_has_mark_rank(self):
        # rank-1 item with rank=0 member → mark "rank"
        p = commissary_vendor_payload("republic", 0, 99999)
        marks = {it["key"]: it["mark"] for it in p["items"]}
        self.assertEqual(marks["dc15_blaster_rifle"], "rank")

    def test_affordable_item_has_mark_buy(self):
        p = commissary_vendor_payload("republic", 1, 99999)
        marks = {it["key"]: it["mark"] for it in p["items"]}
        self.assertEqual(marks["dc15_blaster_rifle"], "buy")

    def test_unaffordable_item_has_mark_short(self):
        p = commissary_vendor_payload("republic", 1, 100)  # all items cost > 100
        marks = {it["key"]: it["mark"] for it in p["items"]}
        for mark in marks.values():
            self.assertIn(mark, ("short", "rank"))

    def test_no_commissary_faction_returns_empty_items(self):
        # Jedi Order has no commissary; items must be [].
        p = commissary_vendor_payload("jedi_order", 5, 99999)
        self.assertEqual(p["mode"], "vendor")
        self.assertEqual(p["items"], [])

    def test_independent_returns_empty_items(self):
        p = commissary_vendor_payload("independent", 0, 0)
        self.assertEqual(p["items"], [])

    def test_pure_no_side_effects(self):
        # Calling the function twice with the same args returns equal results
        # and does not mutate COMMISSARY_STOCK or any shared state.
        import copy
        stock_before = copy.deepcopy(COMMISSARY_STOCK)
        commissary_vendor_payload("republic", 1, 5000)
        commissary_vendor_payload("hutt_cartel", 0, 200)
        self.assertEqual(COMMISSARY_STOCK, stock_before)


# ─────────────────────────────────────────────────────────────────────────────
# Structural pins
# ─────────────────────────────────────────────────────────────────────────────
def _read(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestStructural(unittest.TestCase):
    def test_sink_tag(self):
        src = _read("engine", "commissary.py")
        self.assertIn('"commissary_purchase"', src)
        self.assertIn('"commissary_purchase_refund"', src)
        # No schema change — the commissary uses existing tables only.
        self.assertNotIn("ADD COLUMN", src)

    def test_vendor_payload_symbol_exported(self):
        # commissary_vendor_payload must be importable from engine.commissary.
        src = _read("engine", "commissary.py")
        self.assertIn("def commissary_vendor_payload", src)
        # No schema/credit side effects in the payload function.
        # Quick heuristic: it must not call adjust_credits or add_to_inventory.
        import ast
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "commissary_vendor_payload":
                func_src = ast.unparse(node)
                self.assertNotIn("adjust_credits", func_src)
                self.assertNotIn("add_to_inventory", func_src)

    def test_parser_sends_web_panel(self):
        src = _read("parser", "commissary_commands.py")
        self.assertIn("commissary_vendor_payload", src)
        self.assertIn('"shop_state"', src)
        self.assertIn("Protocol.WEBSOCKET", src)

    def test_command_registered(self):
        src = _read("parser", "commissary_commands.py")
        self.assertIn('"+commissary"', src)
        self.assertIn("def register_commissary_commands", src)
        gs = _read("server", "game_server.py")
        self.assertIn("register_commissary_commands(self.registry)", gs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
