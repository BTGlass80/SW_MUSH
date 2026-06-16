# -*- coding: utf-8 -*-
"""
tests/test_t321_umbrella_admin_audit.py -- T3.21 Blocker 3 follow-up

Closes the audit-trail hole in the PLAYER-level admin UMBRELLA forwards.

The dispatcher (``CommandParser._execute``) writes an ``admin_audit`` row for
every BUILDER/ADMIN command that passes its access gate. But ``+home admin ...``
and ``+shop admin ...`` are PLAYER-level umbrellas that call the ADMIN command's
``execute()`` DIRECTLY -- bypassing the dispatcher seam. The privilege re-check
(``check_access``) was already wired in (the ``9ca0692`` escalation fix); this
drop adds the matching audit write so an admin exercising power through the
umbrella leaves the same trail as a direct ``@housing`` / ``@shop``.

The audit-write logic was lifted to module scope
(``parser.commands.audit_privileged_invocation`` + ``_redact_audit_detail``) so
the umbrella forwards and the dispatcher share ONE implementation; the old
instance methods (``parser._audit_privileged`` / ``parser._redact_audit_detail``)
remain as thin shims for back-compat.

Exercises the REAL ``Database`` (full schema + migrations) and the REAL umbrella
commands -- only ``AdminHousingCommand.execute`` / ``AdminShopCommand.execute``
are stubbed, to isolate the audit seam from the heavy housing/shop side effects.
"""
import asyncio
import inspect
import os
import sys
import unittest
from unittest import mock

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


async def _fresh_db():
    """A real Database on :memory: with the full current schema applied."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


class _FakeSession:
    """Minimal stand-in: holds account/character and records sent lines."""

    def __init__(self, account=None, character=None):
        self.account = account
        self.character = character
        self.is_in_game = True
        self.lines = []

    async def send_line(self, text):
        self.lines.append(text)


def _make_ctx(db, session, command="+home", args=""):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=(command + " " + args).strip(),
        command=command,
        args=args,
        args_list=args.split() if args else [],
        db=db,
    )


def _admin_cmd(key="@testadmin"):
    from parser.commands import BaseCommand, AccessLevel

    class _AdminCmd(BaseCommand):
        pass
    _AdminCmd.key = key
    _AdminCmd.access_level = AccessLevel.ADMIN
    return _AdminCmd()


async def _make_admin_account(db, username="boss"):
    """First account is auto admin+builder -> id is usable as an admin acct."""
    acct_id = await db.create_account(username, "pw-long-enough-123")
    return acct_id


async def _make_plain_account(db, username="grunt"):
    """A second (non-first) account is a plain PLAYER (is_admin=0)."""
    acct_id = await db.create_account(username, "pw-long-enough-123")
    return acct_id


async def _audit_rows(db):
    rows = await db.fetchall(
        "SELECT account_id, username, char_id, char_name, access_level, "
        "command, detail FROM admin_audit ORDER BY id")
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════
# 1. The shared helpers exist at module scope and the shims delegate to them
# ══════════════════════════════════════════════════════════════════════════
class TestModuleHelpers(unittest.TestCase):
    def test_module_level_helpers_present(self):
        import parser.commands as pc
        self.assertTrue(callable(getattr(pc, "audit_privileged_invocation", None)))
        self.assertTrue(callable(getattr(pc, "_redact_audit_detail", None)))
        self.assertTrue(inspect.iscoroutinefunction(pc.audit_privileged_invocation))

    def test_redact_parity_module_vs_instance_shim(self):
        import parser.commands as pc
        from parser.commands import CommandParser, CommandRegistry
        parser = CommandParser(CommandRegistry(), None, None)
        cases = [
            ("@newpassword", "Yoda = supersecret"),  # key-based redaction
            ("@force", "Mace = setpassword hunter2"),  # content-based redaction
            ("@teleport", "Mace = 42"),               # passthrough
            ("@boot", ""),                            # empty
            ("@teleport", "x" * 900),                 # length cap
        ]
        for key, args in cases:
            self.assertEqual(
                pc._redact_audit_detail(key, args),
                parser._redact_audit_detail(key, args),
                msg=f"shim/module mismatch for {key!r}")
        # The cap really is 500.
        self.assertEqual(len(pc._redact_audit_detail("@teleport", "x" * 900)), 500)
        # Secret-bearing args are scrubbed.
        self.assertEqual(pc._redact_audit_detail("@newpassword", "a = b"), "[redacted]")

    def test_module_func_writes_row(self):
        async def _go():
            db = await _fresh_db()
            try:
                import parser.commands as pc
                sess = _FakeSession(
                    account={"id": 7, "username": "ozzel"},
                    character={"id": 3, "name": "Veers"})
                ctx = _make_ctx(db, sess, command="@testadmin", args="evict bob")
                await pc.audit_privileged_invocation(_admin_cmd(), ctx)
                return await _audit_rows(db)
            finally:
                await db.close()

        rows = _run(_go())
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["account_id"], 7)
        self.assertEqual(r["username"], "ozzel")
        self.assertEqual(r["char_id"], 3)
        self.assertEqual(r["char_name"], "Veers")
        self.assertEqual(r["command"], "@testadmin")
        self.assertEqual(r["detail"], "evict bob")

    def test_instance_shim_still_writes(self):
        """Back-compat: the old parser._audit_privileged surface still works."""
        async def _go():
            db = await _fresh_db()
            try:
                from parser.commands import CommandParser, CommandRegistry
                parser = CommandParser(CommandRegistry(), db, None)
                sess = _FakeSession(account={"id": 1, "username": "a"},
                                    character=None)
                ctx = _make_ctx(db, sess, command="@testadmin", args="go")
                await parser._audit_privileged(_admin_cmd(), ctx)
                return await _audit_rows(db)
            finally:
                await db.close()

        rows = _run(_go())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["command"], "@testadmin")
        self.assertIsNone(rows[0]["char_id"])

    def test_no_db_handle_is_noop(self):
        """db=None on the ctx -> clean no-op, never raises."""
        async def _go():
            import parser.commands as pc
            sess = _FakeSession(account={"id": 1}, character=None)
            ctx = _make_ctx(None, sess, command="@testadmin", args="x")
            await pc.audit_privileged_invocation(_admin_cmd(), ctx)
            return True

        self.assertTrue(_run(_go()))


# ══════════════════════════════════════════════════════════════════════════
# 2. +home admin umbrella now audits (the gap this drop closes)
# ══════════════════════════════════════════════════════════════════════════
class TestHomeUmbrellaAudit(unittest.TestCase):
    def test_home_admin_as_admin_writes_audit_row(self):
        async def _go():
            db = await _fresh_db()
            try:
                from parser.housing_commands import (
                    HomeUmbrellaCommand, AdminHousingCommand)
                acct_id = await _make_admin_account(db, "boss")
                sess = _FakeSession(
                    account={"id": acct_id, "username": "boss"},
                    character={"id": 11, "name": "Mace"})
                ctx = _make_ctx(db, sess, command="+home", args="admin list")
                # Isolate the audit seam from the real admin housing logic.
                with mock.patch.object(AdminHousingCommand, "execute",
                                       new_callable=mock.AsyncMock) as ex:
                    await HomeUmbrellaCommand().execute(ctx)
                    called = ex.await_count
                return await _audit_rows(db), called
            finally:
                await db.close()

        rows, called = _run(_go())
        self.assertEqual(called, 1, "admin housing execute should have run")
        self.assertEqual(len(rows), 1, "+home admin should leave ONE audit row")
        r = rows[0]
        self.assertEqual(r["command"], "@housing")
        self.assertEqual(r["detail"], "list")
        self.assertEqual(r["account_id"], 1)
        self.assertEqual(r["char_name"], "Mace")

    def test_home_admin_as_nonadmin_blocks_and_no_audit(self):
        async def _go():
            db = await _fresh_db()
            try:
                from parser.housing_commands import (
                    HomeUmbrellaCommand, AdminHousingCommand)
                await _make_admin_account(db, "boss")          # id 1 (admin)
                grunt_id = await _make_plain_account(db, "grunt")  # id 2 (player)
                sess = _FakeSession(
                    account={"id": grunt_id, "username": "grunt"},
                    character={"id": 12, "name": "Nobody"})
                ctx = _make_ctx(db, sess, command="+home",
                                args="admin evict mace")
                with mock.patch.object(AdminHousingCommand, "execute",
                                       new_callable=mock.AsyncMock) as ex:
                    await HomeUmbrellaCommand().execute(ctx)
                    called = ex.await_count
                return await _audit_rows(db), called, sess.lines
            finally:
                await db.close()

        rows, called, lines = _run(_go())
        self.assertEqual(called, 0, "non-admin must NOT reach admin execute")
        self.assertEqual(len(rows), 0, "denied umbrella must NOT audit")
        self.assertTrue(any("permission" in ln.lower() for ln in lines))


# ══════════════════════════════════════════════════════════════════════════
# 3. +shop admin umbrella now audits (mirror)
# ══════════════════════════════════════════════════════════════════════════
class TestShopUmbrellaAudit(unittest.TestCase):
    def test_shop_admin_as_admin_writes_audit_row(self):
        async def _go():
            db = await _fresh_db()
            try:
                from parser.shop_commands import (
                    ShopUmbrellaCommand, AdminShopCommand)
                acct_id = await _make_admin_account(db, "boss")
                sess = _FakeSession(
                    account={"id": acct_id, "username": "boss"},
                    character={"id": 21, "name": "Quartermaster"})
                ctx = _make_ctx(db, sess, command="+shop", args="admin list")
                with mock.patch.object(AdminShopCommand, "execute",
                                       new_callable=mock.AsyncMock) as ex:
                    await ShopUmbrellaCommand().execute(ctx)
                    called = ex.await_count
                return await _audit_rows(db), called
            finally:
                await db.close()

        rows, called = _run(_go())
        self.assertEqual(called, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["command"], "@shop")
        self.assertEqual(rows[0]["detail"], "list")

    def test_shop_admin_as_nonadmin_blocks_and_no_audit(self):
        async def _go():
            db = await _fresh_db()
            try:
                from parser.shop_commands import (
                    ShopUmbrellaCommand, AdminShopCommand)
                await _make_admin_account(db, "boss")              # id 1
                grunt_id = await _make_plain_account(db, "grunt")  # id 2
                sess = _FakeSession(
                    account={"id": grunt_id, "username": "grunt"},
                    character={"id": 22, "name": "Nobody"})
                ctx = _make_ctx(db, sess, command="+shop", args="admin wipe")
                with mock.patch.object(AdminShopCommand, "execute",
                                       new_callable=mock.AsyncMock) as ex:
                    await ShopUmbrellaCommand().execute(ctx)
                    called = ex.await_count
                return await _audit_rows(db), called, sess.lines
            finally:
                await db.close()

        rows, called, lines = _run(_go())
        self.assertEqual(called, 0)
        self.assertEqual(len(rows), 0)
        self.assertTrue(any("permission" in ln.lower() for ln in lines))


if __name__ == "__main__":
    unittest.main()
