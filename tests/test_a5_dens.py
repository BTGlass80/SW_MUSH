# -*- coding: utf-8 -*-
"""
tests/test_a5_dens.py — Drop 3 A5 centerpiece: sabacc dens.

A Hutt-cartel org operates a sabacc den in a cantina room; while a room is a den
the sabacc rake (after the city's slice) flows to the cartel treasury. Per-room
marker (`sabacc_dens`, schema v40) — deliberately NOT the wilderness/region
ownership model (extending ownership into the city was ruled out).

Covers:
  * the pure `check_den_eligibility` (ok + every refusal reason);
  * `establish_den` / `abandon_den` against a FakeDB (happy path debits the
    setup-cost sink + writes the den; refusals spend nothing; abandon gating);
  * the v40 `sabacc_dens` table + `get_room_den` / `get_org_dens` on a real
    in-memory `Database`;
  * structural pins that sabacc routes the den rake (org treasury + `sabacc_rake`
    ledger tag) and that `+den` is registered + the v40 migration exists.
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

from engine.dens import (                                               # noqa: E402
    check_den_eligibility, establish_den, abandon_den,
    get_room_den, get_org_dens,
    DEN_SETUP_COST, DEN_ESTABLISH_MIN_RANK, DEN_SETUP_SOURCE,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pure eligibility
# ─────────────────────────────────────────────────────────────────────────────
class TestEligibility(unittest.TestCase):
    def _ok_args(self, **over):
        args = dict(is_cantina=True,
                    membership={"rank_level": DEN_ESTABLISH_MIN_RANK},
                    existing_den=None, balance=DEN_SETUP_COST)
        args.update(over)
        return args

    def test_ok(self):
        self.assertTrue(check_den_eligibility(**self._ok_args())["ok"])

    def test_not_cantina(self):
        r = check_den_eligibility(**self._ok_args(is_cantina=False))
        self.assertEqual(r["reason"], "not_cantina")

    def test_not_member(self):
        r = check_den_eligibility(**self._ok_args(membership=None))
        self.assertEqual(r["reason"], "not_member")

    def test_rank_too_low(self):
        r = check_den_eligibility(**self._ok_args(
            membership={"rank_level": DEN_ESTABLISH_MIN_RANK - 1}))
        self.assertEqual(r["reason"], "rank")

    def test_already_den(self):
        r = check_den_eligibility(**self._ok_args(existing_den={"org_id": 1}))
        self.assertEqual(r["reason"], "already_den")

    def test_insufficient(self):
        r = check_den_eligibility(**self._ok_args(balance=DEN_SETUP_COST - 1))
        self.assertEqual(r["reason"], "insufficient")
        self.assertEqual(r["short"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# 2. establish / abandon against a FakeDB
# ─────────────────────────────────────────────────────────────────────────────
class _FakeDB:
    def __init__(self, *, cantina=True, member_rank=DEN_ESTABLISH_MIN_RANK,
                 existing_den=None, balance=DEN_SETUP_COST, fail_write=False):
        self.cantina = cantina
        self.member_rank = member_rank
        self.existing_den = existing_den
        self.balance = balance
        self.fail_write = fail_write
        self.credit_log = []
        self.inserted = []
        self.deleted = []
        self.org = {"id": 9, "code": "hutt_cartel", "name": "The Hutt Cartel"}
        self._db = self   # so db._db.execute/commit route here

    async def get_room(self, rid):
        return {"id": rid, "zone_id": 1}

    async def get_zone(self, zid):
        return {"name": "Cantina District" if self.cantina else "Central Streets"}

    async def get_organization(self, code):
        return self.org if code == "hutt_cartel" else None

    async def get_membership(self, cid, oid):
        return {"rank_level": self.member_rank} if self.member_rank is not None else None

    async def fetchall(self, sql, params=()):
        # get_room_den / get_org_dens
        if "WHERE room_id" in sql:
            return [self.existing_den] if self.existing_den else []
        if "WHERE org_id" in sql:
            return [self.existing_den] if self.existing_den else []
        return []

    async def adjust_credits(self, cid, delta, source, **kw):
        self.credit_log.append((cid, delta, source))
        self.balance += delta
        return self.balance

    async def adjust_org_treasury(self, oid, delta):
        return delta

    async def execute(self, sql, params=()):
        if self.fail_write:
            raise RuntimeError("write boom")
        if sql.strip().upper().startswith("INSERT"):
            self.inserted.append(params)
        elif sql.strip().upper().startswith("DELETE"):
            self.deleted.append(params)

    async def commit(self):
        pass


def _char(cid=5, room_id=100, credits=DEN_SETUP_COST):
    return {"id": cid, "room_id": room_id, "credits": credits}


class TestEstablishAbandon(unittest.TestCase):
    def test_establish_happy_debits_and_writes(self):
        db = _FakeDB()
        res = _run(establish_den(db, _char()))
        self.assertTrue(res["ok"])
        self.assertEqual(res["cost"], DEN_SETUP_COST)
        # Setup cost debited as a sink.
        self.assertEqual(db.credit_log, [(5, -DEN_SETUP_COST, DEN_SETUP_SOURCE)])
        # Den row written.
        self.assertEqual(len(db.inserted), 1)

    def test_establish_not_cantina_no_charge(self):
        db = _FakeDB(cantina=False)
        res = _run(establish_den(db, _char()))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_cantina")
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.inserted, [])

    def test_establish_rank_too_low_no_charge(self):
        db = _FakeDB(member_rank=DEN_ESTABLISH_MIN_RANK - 1)
        res = _run(establish_den(db, _char()))
        self.assertEqual(res["reason"], "rank")
        self.assertEqual(db.credit_log, [])

    def test_establish_insufficient_no_charge(self):
        db = _FakeDB(balance=DEN_SETUP_COST - 1)
        res = _run(establish_den(db, _char(credits=DEN_SETUP_COST - 1)))
        self.assertEqual(res["reason"], "insufficient")
        self.assertEqual(db.credit_log, [])

    def test_establish_write_failure_refunds(self):
        db = _FakeDB(fail_write=True)
        res = _run(establish_den(db, _char()))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "write_failed")
        # Debit then refund → net zero.
        self.assertEqual(
            db.credit_log,
            [(5, -DEN_SETUP_COST, DEN_SETUP_SOURCE),
             (5, DEN_SETUP_COST, "sabacc_den_setup_refund")])

    def test_abandon_happy(self):
        db = _FakeDB(existing_den={"room_id": 100, "org_id": 9,
                                   "org_code": "hutt_cartel"})
        res = _run(abandon_den(db, _char()))
        self.assertTrue(res["ok"])
        self.assertEqual(len(db.deleted), 1)

    def test_abandon_no_den(self):
        db = _FakeDB(existing_den=None)
        res = _run(abandon_den(db, _char()))
        self.assertEqual(res["reason"], "no_den")

    def test_abandon_not_yours(self):
        db = _FakeDB(existing_den={"room_id": 100, "org_id": 999,
                                   "org_code": "other"})
        res = _run(abandon_den(db, _char()))
        self.assertEqual(res["reason"], "not_yours")


# ─────────────────────────────────────────────────────────────────────────────
# 3. v40 sabacc_dens table on a real in-memory Database
# ─────────────────────────────────────────────────────────────────────────────
class TestDenTableRealDB(unittest.TestCase):
    def test_table_crud(self):
        async def go():
            import aiosqlite
            conn = await aiosqlite.connect(":memory:")
            conn.row_factory = aiosqlite.Row

            # Apply the real v40 migration SQL (proves it's valid).
            from db.database import MIGRATIONS
            for sql in MIGRATIONS[40]:
                await conn.execute(sql)
            await conn.execute(
                "INSERT INTO sabacc_dens (room_id, org_id, org_code, "
                "established_by, established_at) VALUES (100, 9, 'hutt_cartel', 5, 1.0)")
            await conn.execute(
                "INSERT INTO sabacc_dens (room_id, org_id, org_code, "
                "established_by, established_at) VALUES (101, 9, 'hutt_cartel', 5, 2.0)")
            await conn.commit()

            # Minimal db-shim exposing fetchall() (what the den helpers call).
            class _MiniDB:
                def __init__(self, c):
                    self._db = c
                async def fetchall(self, sql, params=()):
                    rows = await self._db.execute_fetchall(sql, params)
                    return [dict(r) for r in rows]

            mini = _MiniDB(conn)
            den = await get_room_den(mini, 100)
            self.assertIsNotNone(den)
            self.assertEqual(den["org_id"], 9)
            self.assertEqual(den["org_code"], "hutt_cartel")

            self.assertIsNone(await get_room_den(mini, 999))   # no den

            dens = await get_org_dens(mini, 9)
            self.assertEqual(len(dens), 2)

            await conn.close()
        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# 4. Structural pins
# ─────────────────────────────────────────────────────────────────────────────
def _src(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestStructural(unittest.TestCase):
    def test_sabacc_routes_den_rake(self):
        src = _src("parser", "sabacc_commands.py")
        self.assertIn("get_room_den", src)
        self.assertIn("adjust_org_treasury", src)
        self.assertIn('"sabacc_rake"', src)   # rake on the ledger (F15)

    def test_den_command_registered(self):
        gs = _src("server", "game_server.py")
        self.assertIn("register_den_commands", gs)
        cmd = _src("parser", "den_commands.py")
        self.assertIn('key = "+den"', cmd)

    def test_v40_migration_present(self):
        db_src = _src("db", "database.py")
        self.assertIn("SCHEMA_VERSION = 40", db_src)
        self.assertIn("40: [", db_src)
        self.assertIn("CREATE TABLE IF NOT EXISTS sabacc_dens", db_src)


if __name__ == "__main__":
    unittest.main()
