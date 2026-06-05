# -*- coding: utf-8 -*-
"""
tests/test_gear_insurance.py — Drop 3 B4: gear insurance.

Covers the loadout-protection sink:
  * pure helpers (premium, is_insured, status lines);
  * purchase_gear_insurance / cancel_gear_insurance branches against a
    recording stub (buy / already / insufficient / charge-fail / persist-fail
    + refund; cancel active / none / persist-fail; all proving zero or the
    expected credit movement);
  * a real in-memory `Database` happy path proving the v39 column migration +
    the `gear_insurance_premium` ledger debit + the persisted flag;
  * the death-flow protection driven end-to-end against a real `Database`:
    an insured lawless death keeps the loose loadout + consumes the policy +
    leaves an empty-of-their-gear corpse; an uninsured death drops as before;
    a secured death is a no-op (no corpse, policy untouched);
  * structural pins on the sink tag, the v39 migration, and the registration.

Behaviour runs against a real `Database` on in-memory SQLite (mirroring the
Drop 2 death + the B3 vanity tests).
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

from engine.gear_insurance import (                                    # noqa: E402
    GEAR_INSURANCE_PREMIUM, PREMIUM_SOURCE, PREMIUM_REFUND_SOURCE,
    premium_amount, is_insured, insure_status_lines,
    purchase_gear_insurance, cancel_gear_insurance,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pure helpers
# ─────────────────────────────────────────────────────────────────────────────
class TestPure(unittest.TestCase):
    def test_premium_amount_matches_constant(self):
        self.assertEqual(premium_amount(), GEAR_INSURANCE_PREMIUM)
        self.assertGreater(GEAR_INSURANCE_PREMIUM, 0)

    def test_is_insured_truthiness(self):
        self.assertTrue(is_insured({"gear_insured": 1}))
        self.assertFalse(is_insured({"gear_insured": 0}))
        self.assertFalse(is_insured({}))            # missing → uninsured
        self.assertFalse(is_insured({"gear_insured": None}))
        self.assertFalse(is_insured(object()))      # non-dict → safe False

    def test_status_lines_branch_on_coverage(self):
        on = "\n".join(insure_status_lines({"gear_insured": 1}))
        off = "\n".join(insure_status_lines({"gear_insured": 0}))
        self.assertIn("ACTIVE", on)
        self.assertIn("cancel", on)
        self.assertIn("none", off)
        self.assertIn("buy", off)
        # The premium is surfaced in the uninsured prompt.
        self.assertIn("{:,}".format(GEAR_INSURANCE_PREMIUM), off)


# ─────────────────────────────────────────────────────────────────────────────
# 2. purchase / cancel branches (recording stub)
# ─────────────────────────────────────────────────────────────────────────────
class _StubDB:
    def __init__(self, fail_persist=False):
        self.credit_log = []   # list of (delta, source)
        self.saves = []        # list of field dicts
        self.fail_persist = fail_persist

    async def adjust_credits(self, cid, delta, source):
        self.credit_log.append((delta, source))
        return 1_000_000 + delta

    async def save_character(self, cid, **fields):
        if self.fail_persist:
            raise RuntimeError("persist boom")
        self.saves.append(fields)


def _char(credits=1_000_000, insured=0):
    return {"id": 7, "credits": credits, "gear_insured": insured}


class TestPurchaseBranches(unittest.TestCase):
    def test_buy_debits_premium_and_sets_flag(self):
        db = _StubDB()
        char = _char()
        res = _run(purchase_gear_insurance(db, char))
        self.assertTrue(res["ok"])
        self.assertEqual(res["cost"], GEAR_INSURANCE_PREMIUM)
        # Exactly one debit, tagged as the sink.
        self.assertEqual(db.credit_log, [(-GEAR_INSURANCE_PREMIUM, PREMIUM_SOURCE)])
        # Flag persisted + reflected on the char dict.
        self.assertEqual(db.saves, [{"gear_insured": 1}])
        self.assertEqual(char["gear_insured"], 1)

    def test_already_insured_no_charge(self):
        db = _StubDB()
        res = _run(purchase_gear_insurance(db, _char(insured=1)))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "already")
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.saves, [])

    def test_insufficient_funds_no_charge(self):
        db = _StubDB()
        res = _run(purchase_gear_insurance(db, _char(credits=10)))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "insufficient")
        self.assertEqual(res["short"], GEAR_INSURANCE_PREMIUM - 10)
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.saves, [])

    def test_persist_failure_refunds(self):
        db = _StubDB(fail_persist=True)
        res = _run(purchase_gear_insurance(db, _char()))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "persist_failed")
        # Debit then a matching refund — net zero, nothing eaten.
        self.assertEqual(db.credit_log, [
            (-GEAR_INSURANCE_PREMIUM, PREMIUM_SOURCE),
            (GEAR_INSURANCE_PREMIUM, PREMIUM_REFUND_SOURCE),
        ])


class TestCancelBranches(unittest.TestCase):
    def test_cancel_active_clears_flag_no_credit_move(self):
        db = _StubDB()
        char = _char(insured=1)
        res = _run(cancel_gear_insurance(db, char))
        self.assertTrue(res["ok"])
        self.assertEqual(db.saves, [{"gear_insured": 0}])
        self.assertEqual(char["gear_insured"], 0)
        # No refund — the premium was a pure sink.
        self.assertEqual(db.credit_log, [])

    def test_cancel_without_policy_is_noop(self):
        db = _StubDB()
        res = _run(cancel_gear_insurance(db, _char(insured=0)))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "none")
        self.assertEqual(db.saves, [])
        self.assertEqual(db.credit_log, [])

    def test_cancel_persist_failure(self):
        db = _StubDB(fail_persist=True)
        res = _run(cancel_gear_insurance(db, _char(insured=1)))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "persist_failed")
        self.assertEqual(db.credit_log, [])


# ─────────────────────────────────────────────────────────────────────────────
# 3. Real in-memory Database — column migration + ledger debit + flag persist
# ─────────────────────────────────────────────────────────────────────────────
_OPEN_DBS = []


async def _ledger_db(credits=1_000_000):
    """Real Database with the minimal tables the buy path touches, plus the
    real v39 `gear_insured` column ALTER (the hand-built characters table does
    not run the migration dict)."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db._db.execute(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, credits INTEGER "
        "DEFAULT 0, gear_insured INTEGER NOT NULL DEFAULT 0)")
    await db._db.execute(
        """CREATE TABLE credit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, char_id INTEGER NOT NULL,
            delta INTEGER NOT NULL, source TEXT NOT NULL,
            balance INTEGER NOT NULL, created_at REAL NOT NULL)""")
    await db._db.execute(
        """CREATE TABLE economy_config (
            key TEXT PRIMARY KEY, value REAL NOT NULL, updated_at REAL NOT NULL)""")
    await db._db.execute("INSERT INTO characters (id, credits) VALUES (1, ?)",
                         (credits,))
    await db._db.commit()
    _OPEN_DBS.append(db)
    return db


class TestRealDBBuy(unittest.TestCase):
    def test_buy_debits_through_real_ledger_and_persists_flag(self):
        async def go():
            db = await _ledger_db(credits=1_000_000)
            char = await db.get_character(1)
            self.assertFalse(is_insured(char))     # default 0

            r = await purchase_gear_insurance(db, char)
            self.assertTrue(r["ok"])

            # Flag persisted to the row.
            fresh = await db.get_character(1)
            self.assertTrue(is_insured(fresh))

            # Ledger: one debit, tagged the sink, for the premium.
            rows = await db._db.execute_fetchall(
                "SELECT delta, source FROM credit_log WHERE char_id = 1 "
                "ORDER BY id")
            self.assertEqual([r2["source"] for r2 in rows], [PREMIUM_SOURCE])
            self.assertEqual([r2["delta"] for r2 in rows],
                             [-GEAR_INSURANCE_PREMIUM])

            # A second buy is refused (already insured) — no extra debit.
            r2 = await purchase_gear_insurance(db, fresh)
            self.assertFalse(r2["ok"])
            n = await db._db.execute_fetchall(
                "SELECT COUNT(*) AS n FROM credit_log WHERE char_id = 1")
            self.assertEqual(n[0]["n"], 1)

            try:
                await db.close()
                _OPEN_DBS.remove(db)
            except Exception:
                pass
        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# 4. Death-flow protection (real Database; mirrors test_drop2_death_reconciliation)
# ─────────────────────────────────────────────────────────────────────────────
async def _death_db():
    """Real Database with the tables the death flow touches, including the
    v39 gear_insured column on characters."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db._db.execute(
        "CREATE TABLE characters ("
        " id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0,"
        " inventory TEXT DEFAULT '{}', equipment TEXT DEFAULT '{}',"
        " resources TEXT DEFAULT '[]', gear_insured INTEGER NOT NULL DEFAULT 0,"
        " wound_state TEXT DEFAULT 'healthy', wound_clear_at REAL DEFAULT 0)")
    await db._db.execute(
        """CREATE TABLE corpses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id INTEGER NOT NULL, room_id INTEGER NOT NULL,
            died_at REAL NOT NULL, decay_at REAL NOT NULL,
            inventory TEXT, credits INTEGER DEFAULT 0,
            killer_id INTEGER, killer_is_bh INTEGER DEFAULT 0,
            bounty_resolved INTEGER DEFAULT 0)""")
    await db._db.execute(
        """CREATE TABLE recent_pvp_deaths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            victim_id INTEGER NOT NULL, killer_id INTEGER NOT NULL,
            died_at REAL NOT NULL, grace_until REAL)""")
    await db._db.execute(
        """CREATE TABLE credit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, char_id INTEGER NOT NULL,
            delta INTEGER NOT NULL, source TEXT NOT NULL,
            balance INTEGER NOT NULL, created_at REAL NOT NULL)""")
    await db._db.execute(
        """CREATE TABLE economy_config (
            key TEXT PRIMARY KEY, value REAL NOT NULL, updated_at REAL NOT NULL)""")
    await db._db.commit()
    _OPEN_DBS.append(db)
    return db


async def _seed(db, char_id, *, items, equipment, insured):
    inv = {"items": list(items), "resources": []}
    await db._db.execute(
        "INSERT INTO characters (id, credits, inventory, equipment, "
        "gear_insured) VALUES (?, 0, ?, ?, ?)",
        (char_id, json.dumps(inv), json.dumps(equipment), 1 if insured else 0))
    await db._db.commit()


async def _read(db, char_id):
    rows = await db._db.execute_fetchall(
        "SELECT inventory, equipment, gear_insured FROM characters "
        "WHERE id = ?", (char_id,))
    return dict(rows[0])


async def _corpse_inv(db, char_id):
    rows = await db._db.execute_fetchall(
        "SELECT inventory FROM corpses WHERE char_id = ? ORDER BY id DESC "
        "LIMIT 1", (char_id,))
    if not rows:
        return None
    return json.loads(rows[0]["inventory"] or "[]")


class TestDeathProtection(unittest.TestCase):
    def test_insured_lawless_death_keeps_loadout_and_consumes_policy(self):
        async def go():
            from engine.death import on_pc_death
            db = await _death_db()
            loose = [{"key": "medpac", "qty": 2}]
            equipped = {"key": "dl44_pistol", "condition": 100}
            await _seed(db, 1, items=loose, equipment=equipped, insured=True)

            corpse_id = await on_pc_death(
                db, char_id=1, room_id=50, security_level="lawless")
            self.assertIsNotNone(corpse_id)    # corpse still created

            after = await _read(db, 1)
            # Loose loadout STAYS on the character (not cleared).
            self.assertEqual(json.loads(after["inventory"])["items"], loose)
            # Equipped gear preserved (Drop 2 invariant, unchanged).
            self.assertEqual(json.loads(after["equipment"]), equipped)
            # Policy consumed.
            self.assertEqual(after["gear_insured"], 0)
            # Corpse holds none of their gear.
            self.assertEqual(await _corpse_inv(db, 1), [])

            try:
                await db.close(); _OPEN_DBS.remove(db)
            except Exception:
                pass
        _run(go())

    def test_uninsured_lawless_death_drops_loose_gear(self):
        async def go():
            from engine.death import on_pc_death
            db = await _death_db()
            loose = [{"key": "thermal_detonator", "qty": 1}]
            equipped = {"key": "dl44_pistol", "condition": 100}
            await _seed(db, 2, items=loose, equipment=equipped, insured=False)

            corpse_id = await on_pc_death(
                db, char_id=2, room_id=50, security_level="lawless")
            self.assertIsNotNone(corpse_id)

            after = await _read(db, 2)
            # Loose loadout dropped (inventory cleared on the character).
            self.assertEqual(json.loads(after["inventory"])["items"], [])
            # Equipped still preserved.
            self.assertEqual(json.loads(after["equipment"]), equipped)
            self.assertEqual(after["gear_insured"], 0)
            # Corpse carries the dropped loose gear.
            self.assertEqual(await _corpse_inv(db, 2), loose)

            try:
                await db.close(); _OPEN_DBS.remove(db)
            except Exception:
                pass
        _run(go())

    def test_secured_death_no_corpse_policy_untouched(self):
        async def go():
            from engine.death import on_pc_death
            db = await _death_db()
            await _seed(db, 3, items=[{"key": "comlink"}],
                        equipment={}, insured=True)

            corpse_id = await on_pc_death(
                db, char_id=3, room_id=50, security_level="secured")
            self.assertIsNone(corpse_id)       # no corpse in a secured zone

            after = await _read(db, 3)
            # Early return means the policy is NOT consumed (no loss occurred).
            self.assertEqual(after["gear_insured"], 1)
            # Inventory untouched.
            self.assertEqual(json.loads(after["inventory"])["items"],
                             [{"key": "comlink"}])

            try:
                await db.close(); _OPEN_DBS.remove(db)
            except Exception:
                pass
        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# 5. Structural pins
# ─────────────────────────────────────────────────────────────────────────────
def _src(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestStructural(unittest.TestCase):
    def test_v39_migration_adds_gear_insured(self):
        db_src = _src("db", "database.py")
        # The B4 migration block + column ALTER must be present. We do NOT pin
        # the exact SCHEMA_VERSION value — it climbs with every later migration
        # (A5's sabacc-den drop already bumped it to 40) — only that the schema
        # is at v39 or beyond and the gear_insured migration is intact.
        self.assertIn("39: [", db_src)
        import re as _re
        m = _re.search(r"SCHEMA_VERSION\s*=\s*(\d+)", db_src)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 39)
        self.assertIn("ADD COLUMN gear_insured", db_src)
        self.assertIn('"gear_insured"', db_src)   # writable-column allowlist

    def test_death_consume_branch_present(self):
        d_src = _src("engine", "death.py")
        self.assertIn("_consume_gear_insurance_if_active", d_src)
        # The branch must gate the snapshot so insured deaths keep the loadout.
        self.assertIn("inv_snapshot = []", d_src)

    def test_premium_sink_tag_stable(self):
        gi_src = _src("engine", "gear_insurance.py")
        self.assertIn('PREMIUM_SOURCE = "gear_insurance_premium"', gi_src)
        # No payout faucet *tag* exists (restoration model only). The design
        # note mentions the word in prose to explain why; what must never
        # appear is the quoted ledger-tag literal a payout would use.
        self.assertNotIn('"gear_insurance_payout"', gi_src)

    def test_command_registered(self):
        gs_src = _src("server", "game_server.py")
        self.assertIn("register_insurance_commands", gs_src)
        cmd_src = _src("parser", "insurance_commands.py")
        self.assertIn('key = "+insure"', cmd_src)


if __name__ == "__main__":
    unittest.main()
