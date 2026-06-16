# -*- coding: utf-8 -*-
"""
tests/test_t321_admin_audit.py -- T3.21 Blocker 3 (admin authority hardening)

The security pre-pass closes two related gaps in how elevated authority is
checked and recorded:

  1. **Never-revalidated admin snapshot.** ``BaseCommand.check_access`` used to
     read ``is_admin``/``is_builder`` from ``session.account`` — a snapshot
     frozen at login. A privilege revoked mid-session kept working until the
     player disconnected. The fix re-reads the flag from the DB
     (``Database.get_account_privileges``) on every BUILDER/ADMIN dispatch and
     syncs the in-memory snapshot to match.

  2. **No audit trail.** There was no record of who exercised privilege. The
     fix adds an append-only ``admin_audit`` table (schema v45) written at the
     parser dispatch seam for every elevated command that passes the access
     gate, with secret-bearing arguments (e.g. @newpassword) redacted.

These tests exercise the REAL ``Database`` (full schema + migrations) and the
REAL parser helpers — no mocks of the methods under test.
"""
import asyncio
import os
import sys
import unittest

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


# Lightweight stand-ins so check_access / _audit_privileged can run without a
# real network Session.
class _FakeSession:
    def __init__(self, account=None, character=None, is_in_game=True):
        self.account = account
        self.character = character
        self.is_in_game = is_in_game


def _make_ctx(db, session, command="@x", args=""):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=(command + " " + args).strip(),
        command=command,
        args=args,
        args_list=args.split() if args else [],
        db=db,
    )


def _admin_cmd():
    from parser.commands import BaseCommand, AccessLevel

    class _AdminCmd(BaseCommand):
        key = "@testadmin"
        access_level = AccessLevel.ADMIN
    return _AdminCmd()


def _builder_cmd():
    from parser.commands import BaseCommand, AccessLevel

    class _BuilderCmd(BaseCommand):
        key = "@testbuild"
        access_level = AccessLevel.BUILDER
    return _BuilderCmd()


def _parser(db):
    from parser.commands import CommandParser, CommandRegistry
    return CommandParser(CommandRegistry(), db, None)


# ══════════════════════════════════════════════════════════════════════════
# 1. Schema (v45 admin_audit table)
# ══════════════════════════════════════════════════════════════════════════
class TestSchema(unittest.TestCase):
    def test_schema_version_is_45(self):
        from db.database import SCHEMA_VERSION
        self.assertEqual(SCHEMA_VERSION, 45)

    def test_admin_audit_table_exists_after_init(self):
        async def _go():
            db = await _fresh_db()
            try:
                rows = await db.fetchall(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='admin_audit'")
                cols = await db.fetchall("PRAGMA table_info(admin_audit)")
                idx = await db.fetchall(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='admin_audit'")
                return ([r["name"] for r in rows],
                        {c["name"] for c in cols},
                        {i["name"] for i in idx})
            finally:
                await db.close()

        tables, cols, idx = _run(_go())
        self.assertEqual(tables, ["admin_audit"])
        self.assertEqual(
            cols,
            {"id", "account_id", "username", "char_id", "char_name",
             "access_level", "command", "detail", "created_at"})
        self.assertIn("idx_admin_audit_account", idx)
        self.assertIn("idx_admin_audit_created", idx)


# ══════════════════════════════════════════════════════════════════════════
# 2. Database.get_account_privileges — live privilege re-read
# ══════════════════════════════════════════════════════════════════════════
class TestGetAccountPrivileges(unittest.TestCase):
    def test_first_account_is_admin_and_builder(self):
        async def _go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")
                return await db.get_account_privileges(acct)
            finally:
                await db.close()

        is_admin, is_builder = _run(_go())
        self.assertTrue(is_admin)
        self.assertTrue(is_builder)

    def test_nonexistent_account_has_no_privileges(self):
        async def _go():
            db = await _fresh_db()
            try:
                return await db.get_account_privileges(999999)
            finally:
                await db.close()

        self.assertEqual(_run(_go()), (False, False))

    def test_revocation_is_reflected_live(self):
        async def _go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")
                before = await db.get_account_privileges(acct)
                await db.execute_commit(
                    "UPDATE accounts SET is_admin = 0 WHERE id = ?", (acct,))
                after = await db.get_account_privileges(acct)
                return before, after
            finally:
                await db.close()

        before, after = _run(_go())
        self.assertEqual(before, (True, True))
        self.assertEqual(after, (False, True))  # admin revoked, builder kept


# ══════════════════════════════════════════════════════════════════════════
# 3. Database.record_admin_action — append-only trail
# ══════════════════════════════════════════════════════════════════════════
class TestRecordAdminAction(unittest.TestCase):
    def test_insert_row(self):
        async def _go():
            db = await _fresh_db()
            try:
                await db.record_admin_action(
                    account_id=7, username="boss", char_id=3,
                    char_name="Mace", access_level=3,
                    command="@teleport", detail="Mace = 42")
                rows = await db.fetchall(
                    "SELECT account_id, username, char_id, char_name, "
                    "access_level, command, detail FROM admin_audit")
                return [dict(r) for r in rows]
            finally:
                await db.close()

        rows = _run(_go())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["command"], "@teleport")
        self.assertEqual(rows[0]["username"], "boss")
        self.assertEqual(rows[0]["access_level"], 3)
        self.assertEqual(rows[0]["detail"], "Mace = 42")


# ══════════════════════════════════════════════════════════════════════════
# 4. check_access — DB re-validation, snapshot trust removed
# ══════════════════════════════════════════════════════════════════════════
class TestCheckAccessRevalidation(unittest.TestCase):
    def test_admin_granted_when_db_confirms(self):
        async def _go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")
                row = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (acct,)))[0])
                sess = _FakeSession(account=row)
                ctx = _make_ctx(db, sess)
                return await _admin_cmd().check_access(ctx)
            finally:
                await db.close()

        self.assertTrue(_run(_go()))

    def test_revoked_admin_is_denied_despite_stale_snapshot(self):
        """The snapshot still says is_admin=1, but the DB says 0 → DENY."""
        async def _go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")
                # Snapshot taken at login (still privileged).
                snapshot = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (acct,)))[0])
                self.assertEqual(snapshot["is_admin"], 1)
                # Privilege revoked in the DB after login.
                await db.execute_commit(
                    "UPDATE accounts SET is_admin = 0 WHERE id = ?", (acct,))
                sess = _FakeSession(account=snapshot)
                ctx = _make_ctx(db, sess)
                allowed = await _admin_cmd().check_access(ctx)
                # ...and the in-memory snapshot was synced to the live value.
                return allowed, snapshot["is_admin"]
            finally:
                await db.close()

        allowed, synced_flag = _run(_go())
        self.assertFalse(allowed)
        self.assertEqual(synced_flag, 0)

    def test_both_snapshot_flags_synced_on_revalidation(self):
        """An ADMIN check syncs the WHOLE snapshot (both flags), not just
        the one it was asked about — one DB round-trip already fetched both."""
        async def _go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")
                snapshot = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (acct,)))[0])
                # Revoke BOTH in the DB after the snapshot was taken.
                await db.execute_commit(
                    "UPDATE accounts SET is_admin = 0, is_builder = 0 "
                    "WHERE id = ?", (acct,))
                sess = _FakeSession(account=snapshot)
                ctx = _make_ctx(db, sess)
                # An is_admin check should sync is_builder too.
                await _admin_cmd().check_access(ctx)
                return snapshot["is_admin"], snapshot["is_builder"]
            finally:
                await db.close()

        is_admin, is_builder = _run(_go())
        self.assertEqual(is_admin, 0)
        self.assertEqual(is_builder, 0)

    def test_builder_command_uses_builder_flag(self):
        async def _go():
            db = await _fresh_db()
            try:
                acct = await db.create_account("boss", "pw123456")
                await db.execute_commit(
                    "UPDATE accounts SET is_builder = 0 WHERE id = ?", (acct,))
                snapshot = dict((await db.fetchall(
                    "SELECT * FROM accounts WHERE id = ?", (acct,)))[0])
                sess = _FakeSession(account=snapshot)
                ctx = _make_ctx(db, sess)
                return await _builder_cmd().check_access(ctx)
            finally:
                await db.close()

        self.assertFalse(_run(_go()))

    def test_no_account_is_denied(self):
        async def _go():
            db = await _fresh_db()
            try:
                sess = _FakeSession(account=None)
                ctx = _make_ctx(db, sess)
                return await _admin_cmd().check_access(ctx)
            finally:
                await db.close()

        self.assertFalse(_run(_go()))

    def test_no_db_falls_back_to_snapshot(self):
        """Defensive: with no DB handle, the snapshot value is honored."""
        async def _go():
            sess = _FakeSession(account={"id": 1, "is_admin": 1})
            ctx = _make_ctx(None, sess)
            return await _admin_cmd().check_access(ctx)

        self.assertTrue(_run(_go()))

    def test_player_and_anyone_tiers_unchanged(self):
        from parser.commands import BaseCommand, AccessLevel

        class _PlayerCmd(BaseCommand):
            access_level = AccessLevel.PLAYER

        class _AnyoneCmd(BaseCommand):
            access_level = AccessLevel.ANYONE

        async def _go():
            sess_in = _FakeSession(account=None, is_in_game=True)
            sess_out = _FakeSession(account=None, is_in_game=False)
            ctx_in = _make_ctx(None, sess_in)
            ctx_out = _make_ctx(None, sess_out)
            return (
                await _PlayerCmd().check_access(ctx_in),
                await _PlayerCmd().check_access(ctx_out),
                await _AnyoneCmd().check_access(ctx_out),
            )

        player_in, player_out, anyone = _run(_go())
        self.assertTrue(player_in)
        self.assertFalse(player_out)
        self.assertTrue(anyone)


# ══════════════════════════════════════════════════════════════════════════
# 5. Audit redaction
# ══════════════════════════════════════════════════════════════════════════
class TestRedaction(unittest.TestCase):
    def setUp(self):
        self.parser = _parser(None)

    def test_password_command_is_redacted(self):
        self.assertEqual(
            self.parser._redact_audit_detail("@newpassword", "Mace = hunter2"),
            "[redacted]")
        self.assertEqual(
            self.parser._redact_audit_detail("@passwd", "Yoda = secret99"),
            "[redacted]")

    def test_password_substring_anywhere_is_redacted(self):
        # e.g. a reset smuggled through @force.
        self.assertEqual(
            self.parser._redact_audit_detail(
                "@force", "Mace = @newpassword Yoda = leak"),
            "[redacted]")

    def test_redact_command_token_anywhere_is_redacted(self):
        # A redact-set alias smuggled through @force that lacks the literal
        # 'password'/'passwd' substring is still caught by the token check.
        self.assertEqual(
            self.parser._redact_audit_detail(
                "@force", "Mace = @newpass Yoda = leakvalue"),
            "[redacted]")

    def test_ordinary_args_preserved(self):
        self.assertEqual(
            self.parser._redact_audit_detail("@teleport", "Mace = 42"),
            "Mace = 42")

    def test_empty_args(self):
        self.assertEqual(self.parser._redact_audit_detail("@boot", ""), "")

    def test_long_args_capped(self):
        long = "x" * 1000
        self.assertEqual(
            len(self.parser._redact_audit_detail("@teleport", long)), 500)


# ══════════════════════════════════════════════════════════════════════════
# 6. _audit_privileged — end-to-end write at the seam
# ══════════════════════════════════════════════════════════════════════════
class TestAuditPrivileged(unittest.TestCase):
    def test_privileged_dispatch_writes_redacted_row(self):
        async def _go():
            db = await _fresh_db()
            try:
                parser = _parser(db)
                sess = _FakeSession(
                    account={"id": 5, "username": "boss"},
                    character={"id": 9, "name": "Mace"})
                from parser.commands import BaseCommand, AccessLevel

                class _PwCmd(BaseCommand):
                    key = "@newpassword"
                    access_level = AccessLevel.ADMIN

                ctx = _make_ctx(db, sess, command="@newpassword",
                                args="Yoda = supersecret")
                await parser._audit_privileged(_PwCmd(), ctx)
                rows = await db.fetchall(
                    "SELECT account_id, username, char_id, char_name, "
                    "access_level, command, detail FROM admin_audit")
                return [dict(r) for r in rows]
            finally:
                await db.close()

        rows = _run(_go())
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["account_id"], 5)
        self.assertEqual(r["username"], "boss")
        self.assertEqual(r["char_id"], 9)
        self.assertEqual(r["char_name"], "Mace")
        self.assertEqual(r["command"], "@newpassword")
        self.assertEqual(r["detail"], "[redacted]")  # password NOT leaked

    def test_audit_failure_never_raises(self):
        """A broken DB handle must not propagate out of the audit path."""
        async def _go():
            parser = _parser(None)
            sess = _FakeSession(account={"id": 1}, character=None)
            from parser.commands import BaseCommand, AccessLevel

            class _C(BaseCommand):
                key = "@boot"
                access_level = AccessLevel.ADMIN

            # db=None on the ctx → _audit_privileged should no-op cleanly.
            ctx = _make_ctx(None, sess, command="@boot", args="someone")
            await parser._audit_privileged(_C(), ctx)
            return True

        self.assertTrue(_run(_go()))


if __name__ == "__main__":
    unittest.main()
