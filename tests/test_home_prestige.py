# -*- coding: utf-8 -*-
"""
tests/test_home_prestige.py — Drop 3 B2: home prestige (aspirational sink).

A homeowner spends escalating sums to raise their residence's prestige — pure
cosmetic standing, no payout, no mechanical benefit. It is a load-bearing
high-tier *sink*: it gives veteran credit somewhere to go. Costs escalate
steeply so the top tier is a real money-burn.

Covers: the pure catalog/helpers; `purchase_home_prestige` branches against a
recording stub (buy / insufficient / maxed / refund-on-persist-failure); a real
in-memory `Database` happy path that proves the `prestige_level` column
migration + the `home_prestige` ledger debit + the persisted level; and
structural pins (the sink tag, the schema column, the `+home prestige` switch).
"""

import os
import sys
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.housing import (                                          # noqa: E402
    HOME_PRESTIGE_TIERS, home_prestige_max, prestige_tier,
    next_prestige_tier, prestige_label, prestige_descriptor,
    home_prestige_status_lines, purchase_home_prestige,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pure catalog / helpers
# ─────────────────────────────────────────────────────────────────────────────
class TestPrestigePure(unittest.TestCase):
    def test_costs_escalate_strictly(self):
        costs = [c for _, c, _ in HOME_PRESTIGE_TIERS]
        self.assertEqual(costs, sorted(costs))
        self.assertTrue(all(b > a for a, b in zip(costs, costs[1:])),
                        "prestige costs must strictly increase (it's a sink)")
        self.assertGreaterEqual(costs[-1], 100_000)  # top tier is a real burn

    def test_tier_lookup(self):
        self.assertIsNone(prestige_tier(0))
        t2 = prestige_tier(2)
        self.assertEqual(t2["label"], "Finely Appointed")
        self.assertEqual(t2["cost"], 15_000)
        # out-of-range clamps to max, never raises
        self.assertEqual(prestige_tier(99)["level"], home_prestige_max())

    def test_next_tier(self):
        n0 = next_prestige_tier(0)
        self.assertEqual(n0["level"], 1)
        self.assertEqual(n0["cost"], 5_000)
        self.assertEqual(next_prestige_tier(home_prestige_max() - 1)["level"],
                         home_prestige_max())
        self.assertIsNone(next_prestige_tier(home_prestige_max()))  # maxed

    def test_labels(self):
        self.assertEqual(prestige_label(0), "Unremarkable")
        self.assertEqual(prestige_label(home_prestige_max()),
                         HOME_PRESTIGE_TIERS[-1][0])
        self.assertEqual(prestige_descriptor(0), "")

    def test_status_lines(self):
        at0 = home_prestige_status_lines({"prestige_level": 0})
        self.assertTrue(any("Next:" in l for l in at0))
        maxed = home_prestige_status_lines({"prestige_level": home_prestige_max()})
        self.assertTrue(any("highest prestige" in l for l in maxed))


# ─────────────────────────────────────────────────────────────────────────────
# purchase_home_prestige — branches (recording stub)
# ─────────────────────────────────────────────────────────────────────────────
class _StubDB:
    def __init__(self, fail_persist=False):
        self.credit_log = []      # (delta, source)
        self.updates = []         # (level, housing_id)
        self.fail_persist = fail_persist

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((delta, source))
        return 1_000_000 + delta

    async def execute(self, sql, params=()):
        if self.fail_persist:
            raise RuntimeError("persist boom")
        if "UPDATE player_housing" in sql:
            self.updates.append((params[0], params[2]))

    async def commit(self):
        pass


class TestPurchaseBranches(unittest.TestCase):
    def _char(self, credits=1_000_000):
        return {"id": 7, "credits": credits}

    def _housing(self, level=0):
        return {"id": 42, "prestige_level": level}

    def test_buy_debits_home_prestige_and_persists_level(self):
        db = _StubDB()
        char, housing = self._char(), self._housing(level=0)
        res = _run(purchase_home_prestige(db, char, housing))
        self.assertTrue(res["ok"])
        self.assertEqual(res["new_level"], 1)
        self.assertEqual(db.credit_log, [(-5_000, "home_prestige")])
        self.assertEqual(db.updates, [(1, 42)])
        self.assertEqual(housing["prestige_level"], 1)  # in-memory advanced

    def test_insufficient_funds_no_charge(self):
        db = _StubDB()
        char = self._char(credits=4_999)         # next tier is 5,000
        res = _run(purchase_home_prestige(db, char, self._housing(0)))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "insufficient")
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.updates, [])

    def test_maxed_no_charge(self):
        db = _StubDB()
        res = _run(purchase_home_prestige(
            db, self._char(), self._housing(level=home_prestige_max())))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "max")
        self.assertEqual(db.credit_log, [])

    def test_refund_on_persist_failure(self):
        db = _StubDB(fail_persist=True)
        res = _run(purchase_home_prestige(db, self._char(), self._housing(0)))
        self.assertFalse(res["ok"])
        sources = [s for _, s in db.credit_log]
        self.assertIn("home_prestige", sources)
        self.assertIn("home_prestige_refund", sources)

    def test_no_home(self):
        db = _StubDB()
        res = _run(purchase_home_prestige(db, self._char(), None))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "no_home")
        self.assertEqual(db.credit_log, [])


# ─────────────────────────────────────────────────────────────────────────────
# Real in-memory Database — proves the column migration + ledger + persistence
# ─────────────────────────────────────────────────────────────────────────────
_OPEN_DBS = []


async def _real_db_with_home(credits=500_000):
    from db.database import Database
    from engine import housing
    db = Database(":memory:")
    await db.connect()
    # Characters + ledger tables so the real adjust_credits runs.
    await db._db.execute(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    # Minimal rooms/exits so housing.ensure_schema's ALTERs + intrusion schema run
    # (production always has these; the column adds are otherwise no-ops here).
    await db._db.execute("CREATE TABLE rooms (id INTEGER PRIMARY KEY, name TEXT)")
    await db._db.execute("CREATE TABLE exits (id INTEGER PRIMARY KEY, name TEXT)")
    await db._db.execute(
        """CREATE TABLE credit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, char_id INTEGER NOT NULL,
            delta INTEGER NOT NULL, source TEXT NOT NULL,
            balance INTEGER NOT NULL, created_at REAL NOT NULL)""")
    await db._db.execute(
        """CREATE TABLE economy_config (
            key TEXT PRIMARY KEY, value REAL NOT NULL, updated_at REAL NOT NULL)""")
    await db._db.commit()
    # Housing schema (creates player_housing + the prestige_level column).
    await housing.ensure_schema(db)
    await db._db.execute("INSERT INTO characters (id, credits) VALUES (1, ?)",
                         (credits,))
    await db._db.execute("INSERT INTO rooms (id, name) VALUES (555, 'Test Home')")
    await db._db.execute(
        "INSERT INTO player_housing (id, char_id, tier, entry_room_id, created_at) "
        "VALUES (100, 1, 3, 555, 0)")
    await db._db.commit()
    _OPEN_DBS.append(db)
    return db


class TestRealDBHappyPath(unittest.TestCase):
    def test_column_exists_and_purchase_persists(self):
        async def go():
            from engine.housing import get_housing, purchase_home_prestige
            db = await _real_db_with_home(credits=500_000)
            # The migration added the column with default 0.
            housing = await get_housing(db, 1)
            self.assertEqual(int(housing.get("prestige_level") or 0), 0)

            char = {"id": 1, "credits": 500_000}
            res = await purchase_home_prestige(db, char, housing)
            self.assertTrue(res["ok"])
            self.assertEqual(res["new_level"], 1)

            # Level persisted to the DB.
            rows = await db._db.execute_fetchall(
                "SELECT prestige_level FROM player_housing WHERE id = 100")
            self.assertEqual(rows[0]["prestige_level"], 1)
            # Credits actually moved, logged under the sink tag.
            crows = await db._db.execute_fetchall(
                "SELECT delta, source FROM credit_log WHERE char_id = 1")
            self.assertEqual(crows[0]["source"], "home_prestige")
            self.assertEqual(crows[0]["delta"], -5_000)
        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# Structural pins
# ─────────────────────────────────────────────────────────────────────────────
class TestStructural(unittest.TestCase):
    def test_sink_tag_and_column(self):
        with open(os.path.join(PROJECT_ROOT, "engine", "housing.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"home_prestige"', src)
        self.assertIn("ADD COLUMN prestige_level", src)
        # the column is wired into the idempotent ensure_schema loop
        self.assertIn("_PRESTIGE_COL", src)

    def test_prestige_switch_registered(self):
        with open(os.path.join(PROJECT_ROOT, "parser", "housing_commands.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"prestige"', src)
        self.assertIn('_HOME_SWITCH_IMPL["prestige"]', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
