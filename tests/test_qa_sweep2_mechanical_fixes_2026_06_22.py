# -*- coding: utf-8 -*-
"""
tests/test_qa_sweep2_mechanical_fixes_2026_06_22.py

Regression tests for the 4 MECHANICAL defects fixed in QA sweep #2
(2026-06-22).  Each test names the bug it pins and documents what the
pre-fix behaviour was so future regressions are self-describing.

B1 — @mail/reply to soft-deleted mail bypasses is_deleted gate
     Pre-fix: _reply SQL had no AND mr.is_deleted = 0 → reply sent from trash.
     Fix: added is_deleted gate to _reply (and _forward, same root-cause).

B2 — Wound-recovery tick skips wounded chars with stale session-cache
     Pre-fix: fast-path `if cached_clear_at <= 0: continue` silently
     skipped chars whose wound_clear_at was never written to the cache
     (on_pc_death syncs wound_state but not wound_clear_at).
     Fix: changed condition to `if cached_clear_at > 0 and cached_clear_at > now`
     so a zero clear_at falls through to the authoritative DB read.

B3 — @mail/reply to mail with nonexistent sender_id crashes with FK error
     Pre-fix: _do_send INSERT mail_recipients.char_id = sender_id where
     sender has no characters row → IntegrityError (FK ON).
     Fix: guard in _reply: if sender_id == 0 or sender_name IS NULL → clean error.

B4 — @mail/reply compose-editor shows 'To: None' when sender is missing
     Pre-fix: line 474 used orig['sender_name'] directly (None repr → "To: None").
     Fix: same guard as B3 bails out before reaching the compose-editor branch.
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── shared DB + helpers ──────────────────────────────────────────────────────

async def _fresh_db():
    """Return a fully-initialised in-memory Database."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


_seed_char_account_id: int | None = None  # lazily seeded per-DB


async def _seed_char(db, name: str = "Player") -> int:
    """Insert a minimal characters row; return char_id.

    All test chars share one account row per DB (created lazily).
    """
    # Ensure we have an account row (characters.account_id NOT NULL)
    cur = await db._db.execute(
        "INSERT INTO accounts (username, password_hash, email) "
        "VALUES (?, 'x', 'x@x.com') "
        "ON CONFLICT DO NOTHING",
        (f"acct_{name}",),
    )
    acc_id = cur.lastrowid
    if not acc_id:
        rows = await db._db.execute(
            "SELECT id FROM accounts WHERE username = ?",
            (f"acct_{name}",),
        )
        acc_row = await rows.fetchone()
        acc_id = acc_row[0]
    await db._db.commit()

    cur = await db._db.execute(
        "INSERT INTO characters (account_id, name, is_active, attributes) "
        "VALUES (?, ?, 1, '{}')",
        (acc_id, name),
    )
    await db._db.commit()
    return cur.lastrowid


async def _insert_mail(db, *, sender_id: int, recipient_id: int,
                       subject: str = "Hi", body: str = "Body") -> int:
    """Insert mail + recipient row; return mail_id."""
    cur = await db._db.execute(
        "INSERT INTO mail (sender_id, subject, body, sent_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (sender_id, subject, body),
    )
    mail_id = cur.lastrowid
    await db._db.execute(
        "INSERT INTO mail_recipients (mail_id, char_id, is_read, is_deleted) "
        "VALUES (?, ?, 0, 0)",
        (mail_id, recipient_id),
    )
    await db._db.commit()
    return mail_id


# ── Fake plumbing for mail command tests ─────────────────────────────────────

class _FakeSess:
    def __init__(self):
        self.lines: list[str] = []
        self._input_intercept = None

    async def send_line(self, t: str):
        self.lines.append(t)


class _FakeMgr:
    def find_by_character(self, rid):
        return None


class _FakeCtx:
    def __init__(self, db, char_id: int, char_name: str = "PC"):
        self.db = db
        self.session = _FakeSess()
        self.session.character = {"id": char_id, "name": char_name}
        self.session_mgr = _FakeMgr()
        self.args = ""
        self.switches = []


# ═══════════════════════════════════════════════════════════════════════════════
# B1 — is_deleted gate on @mail/reply
# ═══════════════════════════════════════════════════════════════════════════════

class TestB1ReplyToSoftDeletedMailBlocked(unittest.TestCase):
    """Replying to a soft-deleted mail must return 'not found', not deliver."""

    def test_reply_to_deleted_mail_is_rejected(self):
        """
        Pre-fix: _reply SQL had no is_deleted filter → mail sent from trash.
        Post-fix: returns 'not found' for is_deleted=1 mail.
        """
        from parser.mail_commands import MailCommand

        async def _go():
            db = await _fresh_db()
            sender_id = await _seed_char(db, "Sender")
            recip_id = await _seed_char(db, "Recip")
            mail_id = await _insert_mail(db, sender_id=sender_id,
                                         recipient_id=recip_id, subject="Original")
            # Soft-delete the mail on the recipient side
            await db._db.execute(
                "UPDATE mail_recipients SET is_deleted = 1 "
                "WHERE mail_id = ? AND char_id = ?",
                (mail_id, recip_id),
            )
            await db._db.commit()

            cmd = MailCommand.__new__(MailCommand)
            ctx = _FakeCtx(db, recip_id, "Recip")
            # @mail/reply <id> = <body> quick-reply form
            ctx.args = f"{mail_id} = hello from trash"
            await cmd._reply(ctx)
            return ctx.session.lines

        lines = _run(_go())
        combined = " ".join(lines).lower()
        # Must see "not found" — must NOT see "[mail sent]"
        self.assertIn("not found", combined,
                      "Deleted mail reply must return not-found")
        self.assertNotIn("mail sent", combined,
                         "Deleted mail must NOT result in a sent message")

    def test_reply_to_active_mail_still_works(self):
        """Active (not deleted) mail must still be reply-able."""
        from parser.mail_commands import MailCommand

        async def _go():
            db = await _fresh_db()
            sender_id = await _seed_char(db, "Alice")
            recip_id = await _seed_char(db, "Bob")
            mail_id = await _insert_mail(db, sender_id=sender_id,
                                         recipient_id=recip_id, subject="Ping")
            cmd = MailCommand.__new__(MailCommand)
            ctx = _FakeCtx(db, recip_id, "Bob")
            ctx.args = f"{mail_id} = Pong"
            await cmd._reply(ctx)
            return ctx.session.lines

        lines = _run(_go())
        combined = " ".join(lines).lower()
        self.assertIn("mail sent", combined,
                      "Active mail reply must succeed with [MAIL SENT]")


class TestB1ForwardToSoftDeletedMailBlocked(unittest.TestCase):
    """_forward shares the same root-cause gap; same fix must hold."""

    def test_forward_deleted_mail_is_rejected(self):
        """Forwarding a deleted mail must return 'not found'."""
        from parser.mail_commands import MailCommand

        async def _go():
            db = await _fresh_db()
            sender_id = await _seed_char(db, "Sender")
            recip_id = await _seed_char(db, "Recip")
            fwd_target_id = await _seed_char(db, "FwdTarget")
            mail_id = await _insert_mail(db, sender_id=sender_id,
                                         recipient_id=recip_id, subject="Fwd me")
            # Soft-delete
            await db._db.execute(
                "UPDATE mail_recipients SET is_deleted = 1 "
                "WHERE mail_id = ? AND char_id = ?",
                (mail_id, recip_id),
            )
            await db._db.commit()

            cmd = MailCommand.__new__(MailCommand)
            ctx = _FakeCtx(db, recip_id, "Recip")
            ctx.args = f"{mail_id} = FwdTarget"
            await cmd._forward(ctx)
            return ctx.session.lines

        lines = _run(_go())
        combined = " ".join(lines).lower()
        self.assertIn("not found", combined,
                      "Forwarding deleted mail must return not-found")


# ═══════════════════════════════════════════════════════════════════════════════
# B2 — Wound-recovery tick with stale session-cache (wound_clear_at=0)
# ═══════════════════════════════════════════════════════════════════════════════

class TestB2WoundRecoveryTickStaleCache(unittest.TestCase):
    """Tick must recover a wounded char whose cache has wound_clear_at=0."""

    def test_stale_cache_char_is_recovered(self):
        """
        Pre-fix: `if cached_clear_at <= 0: continue` skipped the char.
        Post-fix: 0 falls through to DB read → tick_wound_recovery fires.
        """
        async def _go():
            from db.database import Database
            from server.tick_handlers_death import wound_recovery_tick

            db = Database(":memory:")
            await db.connect()
            await db.initialize()

            char_id = await _seed_char(db, "WoundedChar")
            # Set DB wound_state=wounded with an EXPIRED clear_at
            expired_at = time.time() - 1.0  # 1 second in the past
            await db.set_wound_state(char_id, state="wounded",
                                     clear_at=expired_at)

            # Build a fake session whose CACHE has wound_state='wounded'
            # but wound_clear_at=0 (stale — as if on_pc_death wrote the
            # DB but never wrote clear_at into the session dict).
            fake_char = {
                "id": char_id,
                "wound_state": "wounded",
                "wound_clear_at": 0.0,   # <-- the stale-cache condition
            }

            class _FakeSession:
                character = fake_char
                sent: list[str] = []
                async def send_line(self, t: str):
                    _FakeSession.sent.append(t)

            class _FakeSM:
                all = [_FakeSession()]

            class _FakeCtx:
                session_mgr = _FakeSM()
                tick_count = 1

            _FakeCtx.db = db
            await wound_recovery_tick(_FakeCtx())

            # Verify DB was updated to healthy
            rows = await db.fetchall(
                "SELECT wound_state FROM characters WHERE id = ?", (char_id,)
            )
            return rows[0]["wound_state"] if rows else None

        state = _run(_go())
        self.assertEqual(state, "healthy",
                         "Stale-cache char must be recovered by the tick "
                         "(wound_clear_at=0 must fall through to DB read)")

    def test_not_yet_expired_is_still_skipped(self):
        """
        Chars whose cached clear_at is in the future must still be skipped
        (the optimisation must still work for the normal case).
        """
        async def _go():
            from db.database import Database
            from server.tick_handlers_death import wound_recovery_tick

            db = Database(":memory:")
            await db.connect()
            await db.initialize()

            char_id = await _seed_char(db, "NotYetChar")
            future_at = time.time() + 3600.0
            await db.set_wound_state(char_id, state="wounded",
                                     clear_at=future_at)

            # Cache correctly reflects the future timer
            fake_char = {
                "id": char_id,
                "wound_state": "wounded",
                "wound_clear_at": future_at,
            }

            class _FakeSession:
                character = fake_char
                async def send_line(self, t: str): pass

            class _FakeSM:
                all = [_FakeSession()]

            class _FakeCtx:
                session_mgr = _FakeSM()
                tick_count = 1

            _FakeCtx.db = db
            await wound_recovery_tick(_FakeCtx())

            rows = await db.fetchall(
                "SELECT wound_state FROM characters WHERE id = ?", (char_id,)
            )
            return rows[0]["wound_state"] if rows else None

        state = _run(_go())
        self.assertEqual(state, "wounded",
                         "Char with future clear_at must NOT be recovered yet")


# ═══════════════════════════════════════════════════════════════════════════════
# B3 — @mail/reply to mail with nonexistent sender crashes with FK error
# ═══════════════════════════════════════════════════════════════════════════════

class TestB3ReplyToSystemMailRaisedFKError(unittest.TestCase):
    """Replying to system mail (sender_id=0) must give a clean player error."""

    def test_system_mail_reply_gives_clean_error(self):
        """
        Pre-fix: _do_send inserted mail_recipients.char_id = 0, which has
        no characters row → FK IntegrityError → 'An error occurred'.
        Post-fix: guard detects sender_id=0, returns friendly message, no crash.
        """
        from parser.mail_commands import MailCommand

        async def _go():
            db = await _fresh_db()
            recip_id = await _seed_char(db, "Recipient")
            # System mail: sender_id=0, no characters row for 0
            cur = await db._db.execute(
                "INSERT INTO mail (sender_id, subject, body, sent_at) "
                "VALUES (0, 'Stipend paid', 'You received 500 credits.', datetime('now'))"
            )
            mail_id = cur.lastrowid
            await db._db.execute(
                "INSERT INTO mail_recipients (mail_id, char_id, is_read, is_deleted) "
                "VALUES (?, ?, 0, 0)",
                (mail_id, recip_id),
            )
            await db._db.commit()

            cmd = MailCommand.__new__(MailCommand)
            ctx = _FakeCtx(db, recip_id, "Recipient")
            ctx.args = f"{mail_id} = thanks"
            # Pre-fix this would raise IntegrityError; post-fix it must not
            raised = False
            try:
                await cmd._reply(ctx)
            except Exception:
                raised = True
            return ctx.session.lines, raised

        lines, raised = _run(_go())
        self.assertFalse(raised, "Reply to system mail must not raise an exception")
        combined = " ".join(lines).lower()
        self.assertTrue(
            "system" in combined or "cannot reply" in combined,
            f"Must give a friendly refusal, got: {combined!r}"
        )
        self.assertNotIn("mail sent", combined,
                         "System mail must NOT result in a sent message")

    def test_orphaned_sender_reply_gives_clean_error(self):
        """
        Same guard covers the hard-deleted-sender case.
        sender_id != 0 but sender_name IS NULL (LEFT JOIN found no row).
        """
        from parser.mail_commands import MailCommand

        async def _go():
            db = await _fresh_db()
            recip_id = await _seed_char(db, "Recip2")
            # Insert mail with a sender_id that has no characters row
            # (simulates a hard-deleted character outside FK cascades).
            # FK enforcement is ON, so we have to bypass it for the test
            # setup by temporarily disabling it just for the INSERT.
            await db._db.execute("PRAGMA foreign_keys = OFF")
            cur = await db._db.execute(
                "INSERT INTO mail (sender_id, subject, body, sent_at) "
                "VALUES (9999, 'Old friend', 'Miss you.', datetime('now'))"
            )
            mail_id = cur.lastrowid
            await db._db.execute(
                "INSERT INTO mail_recipients (mail_id, char_id, is_read, is_deleted) "
                "VALUES (?, ?, 0, 0)",
                (mail_id, recip_id),
            )
            await db._db.commit()
            await db._db.execute("PRAGMA foreign_keys = ON")

            cmd = MailCommand.__new__(MailCommand)
            ctx = _FakeCtx(db, recip_id, "Recip2")
            ctx.args = f"{mail_id} = miss you too"
            raised = False
            try:
                await cmd._reply(ctx)
            except Exception:
                raised = True
            return ctx.session.lines, raised

        lines, raised = _run(_go())
        self.assertFalse(raised,
                         "Reply to orphaned-sender mail must not raise")
        combined = " ".join(lines).lower()
        self.assertTrue(
            "longer exists" in combined or "cannot reply" in combined
            or "not found" in combined,
            f"Must give a friendly refusal for orphaned sender, got: {combined!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# B4 — @mail/reply compose-editor shows 'To: None' when sender missing
# ═══════════════════════════════════════════════════════════════════════════════

class TestB4ComposEditorNoNoneDisplay(unittest.TestCase):
    """The compose-editor path must never show 'To: None' to the player."""

    def test_system_mail_compose_path_no_to_none(self):
        """
        Pre-fix: _reply compose-editor branch did:
            f"To: {orig['sender_name']}"   → "To: None"
        Post-fix: the sender-guard bails out before reaching the compose
        branch, so the player sees a clean refusal, not "To: None".
        """
        from parser.mail_commands import MailCommand

        async def _go():
            db = await _fresh_db()
            recip_id = await _seed_char(db, "ReaderPC")
            # System mail (sender_id=0)
            cur = await db._db.execute(
                "INSERT INTO mail (sender_id, subject, body, sent_at) "
                "VALUES (0, 'BH Bounty Payout', 'You earned 1000 credits.', "
                "datetime('now'))"
            )
            mail_id = cur.lastrowid
            await db._db.execute(
                "INSERT INTO mail_recipients (mail_id, char_id, is_read, is_deleted) "
                "VALUES (?, ?, 0, 0)",
                (mail_id, recip_id),
            )
            await db._db.commit()

            cmd = MailCommand.__new__(MailCommand)
            ctx = _FakeCtx(db, recip_id, "ReaderPC")
            # No body — would open the compose editor (pre-fix → "To: None")
            ctx.args = str(mail_id)
            await cmd._reply(ctx)
            return ctx.session.lines

        lines = _run(_go())
        combined = " ".join(lines)
        self.assertNotIn("To: None", combined,
                         "Compose-editor must never show 'To: None'")
        self.assertNotIn("None", combined,
                         "Python None repr must never appear in player output")
        # Must still give a message (not silently do nothing)
        self.assertTrue(len(combined.strip()) > 0,
                        "Must send at least one line of output")


if __name__ == "__main__":
    unittest.main()
