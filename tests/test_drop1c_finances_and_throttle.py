# -*- coding: utf-8 -*-
"""
tests/test_drop1c_finances_and_throttle.py — Drop 1.c.

Completes the economy-audit Phase-1 ledger wave with its two user-facing
pieces (the DB layer — economy_config, get/set throttle, adjust_credits
application — already existed at HEAD; this drop wires the commands and
correctly excludes transfers/refunds from the throttle):

  * **Faucet throttle** behaviour in the real ``Database.adjust_credits``
    (against in-memory SQLite): genuine faucets are scaled; sinks, system
    entries, p2p transfers, and refunds are exempt; clamp + persistence.
  * **`@economy throttle`** admin lever (show/set).
  * **`+finances`** player ledger view.
"""

import os
import sys
import asyncio
import unittest

import aiosqlite  # noqa: F401  (used transitively by Database)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from parser.commands import CommandContext               # noqa: E402
from parser.finances_commands import FinancesCommand     # noqa: E402
from parser.director_commands import EconomyCommand       # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fresh_db(start_credits=10000, char_id=1):
    """Real Database on :memory: with the minimal tables adjust_credits +
    the throttle touch (characters, credit_log, economy_config)."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db._db.execute(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    await db._db.execute(
        """CREATE TABLE credit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, char_id INTEGER NOT NULL,
            delta INTEGER NOT NULL, source TEXT NOT NULL,
            balance INTEGER NOT NULL, created_at REAL NOT NULL)""")
    await db._db.execute(
        """CREATE TABLE economy_config (
            key TEXT PRIMARY KEY, value REAL NOT NULL, updated_at REAL NOT NULL)""")
    await db._db.execute(
        "INSERT INTO characters (id, credits) VALUES (?, ?)", (char_id, start_credits))
    await db._db.commit()
    return db


async def _bal(db, char_id=1):
    rows = await db._db.execute_fetchall(
        "SELECT credits FROM characters WHERE id = ?", (char_id,))
    return int(rows[0]["credits"]) if rows else None


# ─────────────────────────────────────────────────────────────────────────────
# Faucet throttle (real adjust_credits)
# ─────────────────────────────────────────────────────────────────────────────
class TestFaucetThrottle(unittest.TestCase):
    def test_default_100_is_noop(self):
        async def go():
            db = await _fresh_db(start_credits=0)
            new = await db.adjust_credits(1, 1000, "mission")
            self.assertEqual(new, 1000)            # unscaled
            self.assertEqual(await _bal(db), 1000)
        _run(go())

    def test_faucet_scaled_at_50(self):
        async def go():
            db = await _fresh_db(start_credits=0)
            await db.set_faucet_throttle_pct(50)
            new = await db.adjust_credits(1, 1000, "mission")
            self.assertEqual(new, 500)             # halved
        _run(go())

    def test_sink_never_throttled(self):
        async def go():
            db = await _fresh_db(start_credits=1000)
            await db.set_faucet_throttle_pct(50)
            new = await db.adjust_credits(1, -400, "docking_fee")
            self.assertEqual(new, 600)             # full -400, not -200
        _run(go())

    def test_p2p_transfer_exempt(self):
        async def go():
            db = await _fresh_db(start_credits=0)
            await db.set_faucet_throttle_pct(50)
            new = await db.adjust_credits(1, 1000, "p2p_transfer")
            self.assertEqual(new, 1000)            # transfer not cooled
        _run(go())

    def test_refund_exempt(self):
        async def go():
            db = await _fresh_db(start_credits=0)
            await db.set_faucet_throttle_pct(50)
            new = await db.adjust_credits(1, 1000, "ship_purchase_refund")
            self.assertEqual(new, 1000)            # refund returns in full
        _run(go())

    def test_system_entry_exempt(self):
        async def go():
            db = await _fresh_db(start_credits=0)
            await db.set_faucet_throttle_pct(50)
            # char_id=0 system faucet: returns 0, touches no character row
            new = await db.adjust_credits(0, 1000, "city_tax")
            self.assertEqual(new, 0)
        _run(go())

    def test_full_suppression_logs_zero(self):
        async def go():
            db = await _fresh_db(start_credits=0)
            await db.set_faucet_throttle_pct(0)
            new = await db.adjust_credits(1, 1000, "mission")
            self.assertEqual(new, 0)               # nothing granted
            self.assertEqual(await _bal(db), 0)
            rows = await db._db.execute_fetchall(
                "SELECT delta FROM credit_log WHERE char_id = 1")
            self.assertTrue(rows and int(rows[0]["delta"]) == 0,
                            "suppressed faucet should log a zero entry")
        _run(go())

    def test_clamp_and_persistence(self):
        async def go():
            db = await _fresh_db()
            self.assertEqual(await db.set_faucet_throttle_pct(150), 100)
            self.assertEqual(await db.set_faucet_throttle_pct(-10), 0)
            self.assertEqual(await db.set_faucet_throttle_pct(70), 70)
            # Persisted: clear the in-process cache and re-read from the table.
            db._faucet_throttle_pct = None
            self.assertEqual(await db.get_faucet_throttle_pct(), 70)
        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# Command stubs
# ─────────────────────────────────────────────────────────────────────────────
class _Sess:
    def __init__(self, char, account=None):
        self.character = char
        self.account = account
        self.lines = []

    async def send_line(self, s):
        self.lines.append(s)

    @property
    def text(self):
        return "\n".join(self.lines)


def _ctx(sess, db, args=""):
    class _Mgr:
        async def broadcast_to_room(self, *a, **k):
            pass
    return CommandContext(session=sess, raw_input="", command="", args=args,
                          args_list=[], db=db, session_mgr=_Mgr())


# ─────────────────────────────────────────────────────────────────────────────
# @economy throttle (admin lever)
# ─────────────────────────────────────────────────────────────────────────────
class _ThrottleDB:
    def __init__(self, pct=100):
        self.pct = pct
        self.set_calls = []

    async def get_faucet_throttle_pct(self):
        return self.pct

    async def set_faucet_throttle_pct(self, p):
        p = max(0, min(100, int(p)))
        self.pct = p
        self.set_calls.append(p)
        return p


class TestEconomyThrottleCommand(unittest.TestCase):
    def test_show_current(self):
        db = _ThrottleDB(pct=80)
        sess = _Sess({"id": 1, "name": "Admin"}, account={"is_admin": 1})
        _run(EconomyCommand().execute(_ctx(sess, db, args="throttle")))
        self.assertIn("80%", sess.text)
        self.assertEqual(db.set_calls, [], "show must not set")

    def test_set_value(self):
        db = _ThrottleDB(pct=100)
        sess = _Sess({"id": 1, "name": "Admin"}, account={"is_admin": 1})
        _run(EconomyCommand().execute(_ctx(sess, db, args="throttle 50")))
        self.assertEqual(db.set_calls, [50])
        self.assertIn("50%", sess.text)

    def test_set_clamped(self):
        db = _ThrottleDB(pct=100)
        sess = _Sess({"id": 1, "name": "Admin"}, account={"is_admin": 1})
        _run(EconomyCommand().execute(_ctx(sess, db, args="throttle 150")))
        self.assertEqual(db.set_calls, [100])  # clamped

    def test_set_non_numeric(self):
        db = _ThrottleDB(pct=100)
        sess = _Sess({"id": 1, "name": "Admin"}, account={"is_admin": 1})
        _run(EconomyCommand().execute(_ctx(sess, db, args="throttle abc")))
        self.assertEqual(db.set_calls, [])
        self.assertIn("number", sess.text.lower())


# ─────────────────────────────────────────────────────────────────────────────
# +finances (player ledger)
# ─────────────────────────────────────────────────────────────────────────────
class _FinancesDB:
    def __init__(self, breakdown):
        self._bd = breakdown

    async def get_char_credit_breakdown(self, char_id, seconds):
        return self._bd


class TestFinancesCommand(unittest.TestCase):
    BREAKDOWN = {
        "faucet_total": 3200, "sink_total": -1150, "net": 2050,
        "txn_count": 8,
        "faucets": [("mission", 2000), ("bounty", 1200)],
        "sinks": [("ship_refuel", -800), ("docking_fee", -350)],
    }

    def test_shows_totals_and_sources(self):
        db = _FinancesDB(self.BREAKDOWN)
        sess = _Sess({"id": 1, "name": "Pilot", "credits": 12345})
        _run(FinancesCommand().execute(_ctx(sess, db)))
        t = sess.text
        self.assertIn("12,345", t)     # balance
        self.assertIn("3,200", t)      # faucets
        self.assertIn("1,150", t)      # sinks
        self.assertIn("2,050", t)      # net
        self.assertIn("Mission", t)    # prettified source
        self.assertIn("Ship Refuel", t)

    def test_empty_window(self):
        db = _FinancesDB({"faucet_total": 0, "sink_total": 0, "net": 0,
                          "txn_count": 0, "faucets": [], "sinks": []})
        sess = _Sess({"id": 1, "name": "Pilot", "credits": 500})
        _run(FinancesCommand().execute(_ctx(sess, db)))
        self.assertIn("no credit activity", sess.text.lower())
        self.assertIn("500", sess.text)


if __name__ == "__main__":
    unittest.main()
