# -*- coding: utf-8 -*-
"""
tests/test_drop1a_adjust_credits.py -- Drop 1.a (Economy ledger chokepoint)

Drop 1.a from the audit-remediation plan
(`sw_mush_remediation_and_fun_additions_design_v1.md`, Phase 1 / finding
F1): introduce ``Database.adjust_credits`` as the single sanctioned way to
move credits — an atomic balance change that always records the movement in
``credit_log`` — and route the already-instrumented credit sites through it.

These tests cover two things:

  1. BEHAVIOUR of ``adjust_credits`` directly, against a real ``Database``
     bound to an in-memory SQLite with minimal ``characters`` + ``credit_log``
     tables (so the *real* method, including its call to ``log_credit``, is
     exercised — not a mock). Faucets, sinks, the ``char_id=0`` system path,
     the ``allow_negative`` guard, atomic-increment semantics, the logged-row
     shape, and that movements feed the existing ``get_credit_velocity``
     dashboard.

  2. MIGRATION COMPLETENESS (structural): the files converted in this drop
     (``engine/death.py``, ``parser/mission_commands.py``,
     ``parser/pc_bounty_commands.py``) no longer call ``log_credit`` directly
     — every currently-logged movement in them now routes through
     ``adjust_credits``. This is a structural-negative pin in the project's
     ``Test*MigrationComplete`` style so a future edit can't silently
     reintroduce an un-chokepointed logged write in these files.
"""
import asyncio
import os
import re
import sys
import unittest

import aiosqlite

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fresh_db(start_credits: int = 1000, char_id: int = 1):
    """Real Database on :memory: with minimal characters + credit_log tables.

    Bypasses the full schema/accounts-FK so the test is hermetic, while still
    exercising the real ``Database.adjust_credits`` / ``Database.log_credit``
    methods (which operate on these two tables by name).
    """
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db._db.execute(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 1000)"
    )
    await db._db.execute(
        """CREATE TABLE credit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id     INTEGER NOT NULL,
            delta       INTEGER NOT NULL,
            source      TEXT NOT NULL,
            balance     INTEGER NOT NULL,
            created_at  REAL NOT NULL
        )"""
    )
    await db._db.execute(
        "INSERT INTO characters (id, credits) VALUES (?, ?)",
        (char_id, start_credits),
    )
    await db._db.commit()
    return db


async def _balance(db, char_id: int = 1) -> int:
    rows = await db._db.execute_fetchall(
        "SELECT credits FROM characters WHERE id = ?", (char_id,)
    )
    return int(rows[0]["credits"]) if rows else None


async def _log_rows(db):
    rows = await db._db.execute_fetchall(
        "SELECT char_id, delta, source, balance FROM credit_log ORDER BY id"
    )
    return [dict(r) for r in (rows or [])]


# ══════════════════════════════════════════════════════════════════════════
# 1. adjust_credits behaviour
# ══════════════════════════════════════════════════════════════════════════

class TestAdjustCreditsExists(unittest.TestCase):
    def test_method_present(self):
        from db.database import Database
        self.assertTrue(
            hasattr(Database, "adjust_credits"),
            "Database.adjust_credits must exist — it is the credit chokepoint",
        )


class TestAdjustCreditsFaucet(unittest.TestCase):
    def test_faucet_increments_and_returns_new_balance(self):
        async def go():
            db = await _fresh_db(start_credits=1000)
            new = await db.adjust_credits(1, 500, "mission")
            self.assertEqual(new, 1500)
            self.assertEqual(await _balance(db), 1500)
            return await _log_rows(db)
        rows = _run(go())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {
            "char_id": 1, "delta": 500, "source": "mission", "balance": 1500,
        })

    def test_logged_balance_is_post_change(self):
        async def go():
            db = await _fresh_db(start_credits=200)
            await db.adjust_credits(1, 800, "bounty")
            return await _log_rows(db)
        rows = _run(go())
        self.assertEqual(rows[0]["balance"], 1000)


class TestAdjustCreditsSink(unittest.TestCase):
    def test_sink_decrements_and_logs_negative_delta(self):
        async def go():
            db = await _fresh_db(start_credits=1000)
            new = await db.adjust_credits(1, -300, "docking_fee")
            self.assertEqual(new, 700)
            self.assertEqual(await _balance(db), 700)
            return await _log_rows(db)
        rows = _run(go())
        self.assertEqual(rows[0]["delta"], -300)
        self.assertEqual(rows[0]["balance"], 700)


class TestAdjustCreditsSystemSink(unittest.TestCase):
    """char_id=0 is a system faucet/sink: no character row touched, logged
    with balance=0, returns 0. Used by e.g. the bounty-guild treasury sink
    and the p2p tax."""

    def test_system_sink_touches_no_character_and_logs(self):
        async def go():
            db = await _fresh_db(start_credits=1000)
            ret = await db.adjust_credits(0, -250, "bh_guild_treasury_sink")
            self.assertEqual(ret, 0)
            # The real player's balance is untouched.
            self.assertEqual(await _balance(db, 1), 1000)
            return await _log_rows(db)
        rows = _run(go())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {
            "char_id": 0, "delta": -250,
            "source": "bh_guild_treasury_sink", "balance": 0,
        })


class TestAdjustCreditsAtomicIncrement(unittest.TestCase):
    """Uses an atomic ``credits = credits + ?`` increment, so sequential
    movements compound correctly and don't clobber each other."""

    def test_sequential_movements_compound(self):
        async def go():
            db = await _fresh_db(start_credits=1000)
            b1 = await db.adjust_credits(1, 500, "mission")
            b2 = await db.adjust_credits(1, -200, "docking_fee")
            b3 = await db.adjust_credits(1, 50, "bounty")
            return b1, b2, b3, await _balance(db), await _log_rows(db)
        b1, b2, b3, final, rows = _run(go())
        self.assertEqual((b1, b2, b3, final), (1500, 1300, 1350, 1350))
        self.assertEqual(len(rows), 3)
        # Every logged balance matches the running total at that point.
        self.assertEqual([r["balance"] for r in rows], [1500, 1300, 1350])


class TestAdjustCreditsAllowNegative(unittest.TestCase):
    def test_default_allows_overdraw(self):
        async def go():
            db = await _fresh_db(start_credits=100)
            new = await db.adjust_credits(1, -300, "debt")  # default allow_negative=True
            self.assertEqual(new, -200)
            self.assertEqual(await _balance(db), -200)
            return await _log_rows(db)
        rows = _run(go())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["delta"], -300)

    def test_guard_refuses_overdraw_no_change_no_log(self):
        async def go():
            db = await _fresh_db(start_credits=100)
            ret = await db.adjust_credits(1, -300, "fee", allow_negative=False)
            self.assertIsNone(ret)
            # Nothing applied …
            self.assertEqual(await _balance(db), 100)
            # … and nothing logged.
            return await _log_rows(db)
        rows = _run(go())
        self.assertEqual(rows, [])

    def test_guard_allows_affordable_sink(self):
        async def go():
            db = await _fresh_db(start_credits=500)
            ret = await db.adjust_credits(1, -300, "fee", allow_negative=False)
            self.assertEqual(ret, 200)
            self.assertEqual(await _balance(db), 200)
            return await _log_rows(db)
        rows = _run(go())
        self.assertEqual(len(rows), 1)

    def test_guard_exact_balance_allowed(self):
        async def go():
            db = await _fresh_db(start_credits=300)
            ret = await db.adjust_credits(1, -300, "fee", allow_negative=False)
            self.assertEqual(ret, 0)
            return await _balance(db)
        self.assertEqual(_run(go()), 0)

    def test_guard_missing_character_returns_none(self):
        async def go():
            db = await _fresh_db(start_credits=300)
            ret = await db.adjust_credits(999, -50, "fee", allow_negative=False)
            self.assertIsNone(ret)
            return await _log_rows(db)
        self.assertEqual(_run(go()), [])


class TestAdjustCreditsFeedsVelocityDashboard(unittest.TestCase):
    """End-to-end: movements made via adjust_credits show up in the existing
    S51 ``get_credit_velocity`` dashboard (the whole point of the chokepoint).
    """

    def test_velocity_reflects_faucets_and_sinks(self):
        async def go():
            db = await _fresh_db(start_credits=1000)
            await db.adjust_credits(1, 500, "mission")     # faucet
            await db.adjust_credits(1, 300, "bounty")      # faucet
            await db.adjust_credits(1, -200, "docking_fee")  # sink
            await db.adjust_credits(0, -100, "p2p_tax")    # system sink (excluded)
            return await db.get_credit_velocity(seconds=86400)
        v = _run(go())
        # Player faucets: 500 + 300 = 800; player sink: -200. System sink
        # (char_id=0) is excluded from faucet/sink player totals.
        self.assertEqual(v["faucet_total"], 800)
        self.assertEqual(v["sink_total"], -200)
        faucet_sources = {s for s, _ in v["top_faucets"]}
        self.assertIn("mission", faucet_sources)
        self.assertIn("bounty", faucet_sources)
        sink_sources = {s for s, _ in v["top_sinks"]}
        self.assertIn("docking_fee", sink_sources)


# ══════════════════════════════════════════════════════════════════════════
# 2. Migration completeness (structural-negative pins)
# ══════════════════════════════════════════════════════════════════════════

_CONVERTED_FILES = [
    "engine/death.py",
    "parser/mission_commands.py",
    "parser/pc_bounty_commands.py",
]


def _read(rel):
    with open(os.path.join(PROJECT_ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


class TestDrop1aMigrationComplete(unittest.TestCase):
    """The files converted in 1.a must route every logged credit movement
    through ``adjust_credits`` — i.e. no direct ``log_credit`` calls remain in
    them. (Other files still use ``log_credit`` directly; their conversion is
    Drop 1.b. This pin guards only the files this drop touched.)"""

    def test_no_direct_log_credit_in_converted_files(self):
        offenders = {}
        for rel in _CONVERTED_FILES:
            src = _read(rel)
            # Match a real call: `.log_credit(` (method) or bare `log_credit(`.
            hits = re.findall(r"\blog_credit\s*\(", src)
            if hits:
                offenders[rel] = len(hits)
        self.assertEqual(
            offenders, {},
            "Converted files must call adjust_credits, not log_credit "
            f"directly. Offenders: {offenders}",
        )

    def test_converted_files_use_adjust_credits(self):
        for rel in _CONVERTED_FILES:
            src = _read(rel)
            self.assertIn(
                "adjust_credits(", src,
                f"{rel} should route credit movement through adjust_credits",
            )


if __name__ == "__main__":
    unittest.main()
