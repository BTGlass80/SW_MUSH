# -*- coding: utf-8 -*-
"""
tests/test_pg2_pl_post_launch.py — PG2.PL (May 22 2026).

PG.2.bounty post-launch follow-ups per HANDOFF_MAY21
§"What's NOT in PG.2 session 2".

Ships:

  PG2.PL.A — Faction stipend interceptor
             engine/organizations.py::faction_payroll_tick now
             intercepts stipend through outstanding insurance debt
             before paying as credits. Sends mail on intercept.

  PG2.PL.B — Mail-to-BH on auto-fulfill
             engine/death.py::_fire_insurance_and_fulfill now sends
             a courtesy mail to the BH after a successful payout.

  PG2.PL.C — Stale-claim warning ping
             parser/pc_bounty_commands.py::bounty_expiry_tick now
             surfaces a courtesy mail when a claim is 6+ days old
             (1 day before expiry). Per-process warned-set prevents
             spam.

  engine/mail_utils.send_system_mail — new shared helper used by
                                       all three above.

Out of scope this drop:
  - BH-tier vendor gate (no such vendor exists at HEAD).

Test sections
=============

  1. TestSendSystemMail            — base helper
  2. TestSendSystemMailFailSoft    — DB error returns None
  3. TestSendSystemMailSenderId    — non-zero sender works
  4. TestStipendInterceptFull      — full intercept, no credits
  5. TestStipendInterceptPartial   — partial intercept, remainder credits
  6. TestStipendNoDebt             — debt-free → no intercept
  7. TestStipendInterceptMail      — mail sent on intercept
  8. TestStipendNoMailNoDebt       — no mail when no debt
  9. TestFulfillMailSent           — BH receives mail on payout
 10. TestPlcWarningWindow          — DB helper finds claims in 6-7d window
 11. TestPlcWarningWindowEdge      — boundary at exactly 6d / 7d
 12. TestPlcReset                  — warned-set test reset works
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ─── shared fixtures ──────────────────────────────────────────────────────


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_char(db, *, name="Test1", credits=0):
    acct_cur = await db._db.execute(
        "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
        (f"acct_{name.lower()}_{id(name)}", "x"),
    )
    await db._db.commit()
    account_id = acct_cur.lastrowid
    attrs = json.dumps({"strength": "3D", "perception": "3D"})
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(name, account_id, room_id, attributes, skills, inventory, "
        " credits, wound_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, account_id, 1, attrs, "{}", '{"items":[]}', credits, 0),
    )
    await db._db.commit()
    cid = cur.lastrowid
    row = await db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (cid,)
    )
    return dict(row[0])


# ──────────────────────────────────────────────────────────────────────
# 1-3. send_system_mail
# ──────────────────────────────────────────────────────────────────────

class TestSendSystemMail(unittest.TestCase):

    def test_basic_send(self):
        from engine.mail_utils import send_system_mail
        async def go():
            db = await _fresh_db()
            ch = await _make_char(db)
            mail_id = await send_system_mail(
                db,
                recipient_id=ch["id"],
                subject="Hello",
                body="World",
            )
            self.assertIsNotNone(mail_id)
            self.assertIsInstance(mail_id, int)
            # Verify rows
            mail_rows = await db._db.execute_fetchall(
                "SELECT * FROM mail WHERE id = ?", (mail_id,)
            )
            self.assertEqual(len(mail_rows), 1)
            self.assertEqual(mail_rows[0]["subject"], "Hello")
            self.assertEqual(mail_rows[0]["body"], "World")
            self.assertEqual(int(mail_rows[0]["sender_id"]), 0)
            # Verify recipient row
            recipient_rows = await db._db.execute_fetchall(
                "SELECT * FROM mail_recipients WHERE mail_id = ?",
                (mail_id,),
            )
            self.assertEqual(len(recipient_rows), 1)
            self.assertEqual(
                int(recipient_rows[0]["char_id"]), ch["id"]
            )
            self.assertEqual(int(recipient_rows[0]["is_read"]), 0)
        _run(go())


class TestSendSystemMailFailSoft(unittest.TestCase):

    def test_db_error_returns_none(self):
        from engine.mail_utils import send_system_mail
        async def go():
            bad_db = MagicMock()
            bad_db.execute = AsyncMock(
                side_effect=RuntimeError("DB exploded")
            )
            result = await send_system_mail(
                bad_db,
                recipient_id=1,
                subject="Won't make it",
                body="...",
            )
            self.assertIsNone(result)
        _run(go())


class TestSendSystemMailSenderId(unittest.TestCase):

    def test_explicit_sender_id_persists(self):
        from engine.mail_utils import send_system_mail
        async def go():
            db = await _fresh_db()
            ch = await _make_char(db, name="Recipient")
            sender = await _make_char(db, name="Sender")
            mail_id = await send_system_mail(
                db,
                recipient_id=ch["id"],
                subject="From Player",
                body="...",
                sender_id=sender["id"],
            )
            self.assertIsNotNone(mail_id)
            rows = await db._db.execute_fetchall(
                "SELECT sender_id FROM mail WHERE id = ?", (mail_id,)
            )
            self.assertEqual(int(rows[0]["sender_id"]), sender["id"])
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 4-8. Stipend interceptor (PG2.PL.A)
# ──────────────────────────────────────────────────────────────────────


async def _setup_stipend_fixture(db, *, stipend_amount: int, debt: int):
    """Build a faction with one member rank that gives `stipend_amount`."""
    from engine.organizations import STIPEND_TABLE

    # Member + treasury fund
    member = await _make_char(db, name="Member1", credits=0)

    # Create an org row (faction)
    org_cur = await db._db.execute(
        "INSERT INTO organizations "
        "(code, name, org_type, treasury, properties) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test_faction", "Test Faction", "faction", 1_000_000, "{}"),
    )
    await db._db.commit()
    org_id = org_cur.lastrowid

    # Insert membership: rank 0, standing 'good'
    await db._db.execute(
        "INSERT INTO org_memberships "
        "(char_id, org_id, rank_level, standing) "
        "VALUES (?, ?, ?, ?)",
        (member["id"], org_id, 0, "good"),
    )
    await db._db.commit()

    # Patch STIPEND_TABLE to give a known amount for this fixture's
    # (code, rank). We monkey-patch at module level — the
    # faction_payroll_tick reads STIPEND_TABLE via attribute lookup
    # each call.
    STIPEND_TABLE[("test_faction", 0)] = stipend_amount

    # Pre-seed insurance debt if any
    if debt > 0:
        await db.add_insurance_debt(member["id"], debt)

    return member, org_id


async def _teardown_stipend_fixture():
    from engine.organizations import STIPEND_TABLE
    STIPEND_TABLE.pop(("test_faction", 0), None)


class TestStipendInterceptFull(unittest.TestCase):

    def test_full_intercept_when_debt_exceeds_stipend(self):
        from engine.organizations import faction_payroll_tick
        async def go():
            db = await _fresh_db()
            member, org_id = await _setup_stipend_fixture(
                db, stipend_amount=100, debt=500,
            )
            try:
                await faction_payroll_tick(db)
                # Credits unchanged (started at 0, stipend fully intercepted)
                row = await db.get_character(member["id"])
                self.assertEqual(int(row["credits"]), 0)
                # Debt reduced by stipend amount: 500 - 100 = 400
                debt = await db.get_insurance_debt(member["id"])
                self.assertEqual(debt, 400)
            finally:
                await _teardown_stipend_fixture()
        _run(go())


class TestStipendInterceptPartial(unittest.TestCase):

    def test_partial_intercept_when_debt_less_than_stipend(self):
        from engine.organizations import faction_payroll_tick
        async def go():
            db = await _fresh_db()
            member, org_id = await _setup_stipend_fixture(
                db, stipend_amount=100, debt=30,
            )
            try:
                await faction_payroll_tick(db)
                # Credits = 100 - 30 = 70
                row = await db.get_character(member["id"])
                self.assertEqual(int(row["credits"]), 70)
                # Debt = 0
                debt = await db.get_insurance_debt(member["id"])
                self.assertEqual(debt, 0)
            finally:
                await _teardown_stipend_fixture()
        _run(go())


class TestStipendNoDebt(unittest.TestCase):

    def test_debt_free_receives_full_stipend(self):
        from engine.organizations import faction_payroll_tick
        async def go():
            db = await _fresh_db()
            member, org_id = await _setup_stipend_fixture(
                db, stipend_amount=100, debt=0,
            )
            try:
                await faction_payroll_tick(db)
                row = await db.get_character(member["id"])
                self.assertEqual(int(row["credits"]), 100)
                debt = await db.get_insurance_debt(member["id"])
                self.assertEqual(debt, 0)
            finally:
                await _teardown_stipend_fixture()
        _run(go())


class TestStipendInterceptMail(unittest.TestCase):

    def test_intercept_sends_mail(self):
        from engine.organizations import faction_payroll_tick
        async def go():
            db = await _fresh_db()
            member, org_id = await _setup_stipend_fixture(
                db, stipend_amount=100, debt=500,
            )
            try:
                await faction_payroll_tick(db)
                # A mail row should exist for the member
                mails = await db._db.execute_fetchall(
                    "SELECT m.subject, m.body "
                    "FROM mail m "
                    "JOIN mail_recipients r ON r.mail_id = m.id "
                    "WHERE r.char_id = ?",
                    (member["id"],),
                )
                self.assertEqual(len(mails), 1)
                self.assertIn("intercepted", mails[0]["subject"].lower())
                self.assertIn("100", mails[0]["body"])  # stipend amount
                self.assertIn("100", mails[0]["body"])  # full intercept
            finally:
                await _teardown_stipend_fixture()
        _run(go())


class TestStipendNoMailNoDebt(unittest.TestCase):

    def test_no_mail_when_paid_in_full(self):
        from engine.organizations import faction_payroll_tick
        async def go():
            db = await _fresh_db()
            member, org_id = await _setup_stipend_fixture(
                db, stipend_amount=100, debt=0,
            )
            try:
                await faction_payroll_tick(db)
                mails = await db._db.execute_fetchall(
                    "SELECT * FROM mail_recipients "
                    "WHERE char_id = ?",
                    (member["id"],),
                )
                self.assertEqual(len(mails), 0)
            finally:
                await _teardown_stipend_fixture()
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 9. PG2.PL.B mail-to-BH on fulfill
# ──────────────────────────────────────────────────────────────────────


class TestFulfillMailSent(unittest.TestCase):

    def test_bh_receives_mail_on_fulfill(self):
        """When _fire_insurance_and_fulfill resolves a bounty, the BH
        should receive a mail describing the payout."""
        from engine.death import _fire_insurance_and_fulfill

        async def go():
            db = await _fresh_db()
            # Create target + BH + bounty schema rows.
            target = await _make_char(db, name="Target", credits=0)
            bh = await _make_char(db, name="Hunter", credits=0)
            # Insert a bounty in ACTIVE state ready to be fulfilled
            # (the auto-fulfill path looks up via
            # get_active_incoming_for_target which filters on state='active')
            await db._db.execute(
                "INSERT INTO pc_bounties "
                "(target_id, poster_id, amount, state, reason, "
                " contributors_json, claimed_by, claimed_at, posted_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    target["id"], 1, 5000, "active", "test",
                    json.dumps([{"poster_id": 1, "amount": 5000}]),
                    bh["id"], time.time(), time.time() - 100,
                    time.time() + 86400 * 30,
                ),
            )
            await db._db.commit()
            # Read back the bounty
            rows = await db._db.execute_fetchall(
                "SELECT id, amount FROM pc_bounties "
                "WHERE target_id = ?",
                (target["id"],),
            )
            bounty_id = int(rows[0]["id"])
            amount = int(rows[0]["amount"])
            # Fire the fulfill path
            await _fire_insurance_and_fulfill(
                db,
                target_id=target["id"],
                killer_id=bh["id"],
                killer_is_bh=True,
            )
            # BH should have a mail
            mails = await db._db.execute_fetchall(
                "SELECT m.subject, m.body "
                "FROM mail m "
                "JOIN mail_recipients r ON r.mail_id = m.id "
                "WHERE r.char_id = ?",
                (bh["id"],),
            )
            self.assertEqual(len(mails), 1)
            self.assertIn(
                "bounty fulfilled", mails[0]["subject"].lower()
            )
            self.assertIn("Target", mails[0]["body"])
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 10-12. PG2.PL.C warning window
# ──────────────────────────────────────────────────────────────────────


class TestPlcWarningWindow(unittest.TestCase):

    def test_finds_claim_in_6_to_7_day_window(self):
        async def go():
            db = await _fresh_db()
            target = await _make_char(db, name="Tgt")
            bh = await _make_char(db, name="BH")
            now = time.time()
            day = 86400
            # Claim from 6.5 days ago — should be in the window
            await db._db.execute(
                "INSERT INTO pc_bounties "
                "(target_id, poster_id, amount, state, reason, "
                " contributors_json, claimed_by, claimed_at, posted_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    target["id"], 1, 1000, "claimed", "test",
                    "[]", bh["id"], now - 6.5 * day, now - 7 * day,
                    now + 30 * day,
                ),
            )
            # Claim from 1 day ago — should NOT be in the window
            await db._db.execute(
                "INSERT INTO pc_bounties "
                "(target_id, poster_id, amount, state, reason, "
                " contributors_json, claimed_by, claimed_at, posted_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    target["id"], 1, 1000, "claimed", "test",
                    "[]", bh["id"], now - 1 * day, now - 2 * day,
                    now + 30 * day,
                ),
            )
            await db._db.commit()
            result = await db.list_claims_in_warning_window(
                warning_lower_seconds=6 * day,
                warning_upper_seconds=7 * day,
            )
            self.assertEqual(len(result), 1)
            # The 6.5-day one
            self.assertAlmostEqual(
                float(result[0]["claimed_at"]),
                now - 6.5 * day, delta=1,
            )
        _run(go())


class TestPlcWarningWindowEdge(unittest.TestCase):

    def test_exactly_seven_days_excluded(self):
        """At exactly 7d, the claim has expired — list_expired_claims
        catches it, not list_claims_in_warning_window."""
        async def go():
            db = await _fresh_db()
            target = await _make_char(db, name="Tgt")
            bh = await _make_char(db, name="BH")
            now = time.time()
            day = 86400
            # claimed_at = now - 7d exactly → cutoff_lower = now - 7d,
            # claimed_at > lower_cutoff is FALSE (not strictly greater)
            # so this row is excluded from the warning window.
            await db._db.execute(
                "INSERT INTO pc_bounties "
                "(target_id, poster_id, amount, state, reason, "
                " contributors_json, claimed_by, claimed_at, posted_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    target["id"], 1, 1000, "claimed", "test",
                    "[]", bh["id"], now - 7 * day, now - 8 * day,
                    now + 30 * day,
                ),
            )
            await db._db.commit()
            result = await db.list_claims_in_warning_window(
                warning_lower_seconds=6 * day,
                warning_upper_seconds=7 * day,
            )
            self.assertEqual(len(result), 0)
        _run(go())


class TestPlcReset(unittest.TestCase):

    def test_reset_clears_warned_set(self):
        from parser.pc_bounty_commands import (
            _PG2PL_WARNED_CLAIMS,
            _reset_pg2pl_warned_claims_for_test,
        )
        _PG2PL_WARNED_CLAIMS.add(42)
        _PG2PL_WARNED_CLAIMS.add(99)
        _reset_pg2pl_warned_claims_for_test()
        self.assertEqual(len(_PG2PL_WARNED_CLAIMS), 0)


if __name__ == "__main__":
    unittest.main()
