# -*- coding: utf-8 -*-
"""
tests/test_h11_mail_sidebar_sql.py — H11 fix: mail sidebar SQL was broken.

QA finding H11: _hud_sidebar_mail used wrong table/column names:
  - `mail_messages`  → `mail`
  - `mr.message_id`  → `mr.mail_id`
  - `m.sender_name`  → `c.name` (via LEFT JOIN characters)

The OperationalError was swallowed in send_hud_update → mail sidebar
permanently dark for all players.

Tests:
  1. _hud_sidebar_mail fires a mail_status WS message (no crash).
  2. Unread count is correct.
  3. messages list contains correct id/subject/from_name/is_read.
  4. System-mail (sender_id=0, no character row) → from_name defaults to "".
  5. is_deleted=1 rows are excluded.
  6. is_read ordering: unread (0) before read (1).
  7. LIMIT 5 enforced even with 6 mail rows.
  8. Empty inbox → unread=0, messages=[].
"""
from __future__ import annotations

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from db.database import Database
from server.session import Session


# ── helpers ─────────────────────────────────────────────────────────────────


async def _fresh_db() -> Database:
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _seed_account(db: Database) -> int:
    cur = await db._db.execute(
        "INSERT INTO accounts (username, password_hash, email) "
        "VALUES ('tester', 'hash', 't@e.com')"
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_char(db: Database, account_id: int, name: str = "Tester") -> int:
    cur = await db._db.execute(
        "INSERT INTO characters (account_id, name, is_active, attributes) "
        "VALUES (?, ?, 1, '{}')",
        (account_id, name),
    )
    await db._db.commit()
    return cur.lastrowid


async def _send_mail(
    db: Database,
    sender_id: int,
    recipient_id: int,
    subject: str = "Hello",
    body: str = "Body",
    is_read: int = 0,
    is_deleted: int = 0,
) -> int:
    """Insert a mail + recipient row; return mail_id."""
    cur = await db._db.execute(
        "INSERT INTO mail (sender_id, subject, body, sent_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (sender_id, subject, body),
    )
    mail_id = cur.lastrowid
    await db._db.execute(
        "INSERT INTO mail_recipients (mail_id, char_id, is_read, is_deleted) "
        "VALUES (?, ?, ?, ?)",
        (mail_id, recipient_id, is_read, is_deleted),
    )
    await db._db.commit()
    return mail_id


def _make_session(sent_messages: list) -> Session:
    """Minimal Session with _send captured into sent_messages."""
    s = Session.__new__(Session)

    async def _fake_send(data: str) -> None:
        sent_messages.append(data)

    s._send = _fake_send
    return s


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── tests ────────────────────────────────────────────────────────────────────


class TestMailSidebarSQL:
    """_hud_sidebar_mail must use the correct table/column names."""

    def test_no_crash_and_fires_event(self):
        """Must not raise OperationalError and must send mail_status."""
        sent: list = []
        sess = _make_session(sent)

        async def _run_test():
            db = await _fresh_db()
            acc = await _seed_account(db)
            char = await _seed_char(db, acc)
            sender = await _seed_char(db, acc, name="Sender")
            await _send_mail(db, sender, char, subject="Test sub")
            await sess._hud_sidebar_mail(db, char)

        _run(_run_test())
        assert len(sent) == 1
        payload = json.loads(sent[0])
        assert payload["type"] == "mail_status"

    def test_unread_count(self):
        """unread reflects unread (is_read=0) rows only."""
        sent: list = []
        sess = _make_session(sent)

        async def _run_test():
            db = await _fresh_db()
            acc = await _seed_account(db)
            char = await _seed_char(db, acc)
            sender = await _seed_char(db, acc, name="Sender")
            await _send_mail(db, sender, char, is_read=0)
            await _send_mail(db, sender, char, is_read=1)
            await sess._hud_sidebar_mail(db, char)

        _run(_run_test())
        payload = json.loads(sent[0])
        assert payload["unread"] == 1

    def test_message_fields(self):
        """messages list has id, subject, from_name, is_read."""
        sent: list = []
        sess = _make_session(sent)

        async def _run_test():
            db = await _fresh_db()
            acc = await _seed_account(db)
            char = await _seed_char(db, acc)
            sender = await _seed_char(db, acc, name="SenderChar")
            await _send_mail(db, sender, char, subject="Sub1")
            await sess._hud_sidebar_mail(db, char)

        _run(_run_test())
        payload = json.loads(sent[0])
        msg = payload["messages"][0]
        assert msg["subject"] == "Sub1"
        assert msg["from_name"] == "SenderChar"
        assert msg["is_read"] is False

    def test_system_mail_sender_zero(self):
        """System mail (sender_id=0, no character row) → from_name=""."""
        sent: list = []
        sess = _make_session(sent)

        async def _run_test():
            db = await _fresh_db()
            acc = await _seed_account(db)
            char = await _seed_char(db, acc)
            # sender_id=0 — no matching characters row
            await _send_mail(db, 0, char, subject="SystemMsg")
            await sess._hud_sidebar_mail(db, char)

        _run(_run_test())
        payload = json.loads(sent[0])
        assert payload["messages"][0]["from_name"] == ""

    def test_deleted_excluded(self):
        """is_deleted=1 rows must not appear in messages or unread count."""
        sent: list = []
        sess = _make_session(sent)

        async def _run_test():
            db = await _fresh_db()
            acc = await _seed_account(db)
            char = await _seed_char(db, acc)
            sender = await _seed_char(db, acc, name="S")
            await _send_mail(db, sender, char, is_deleted=1)
            await sess._hud_sidebar_mail(db, char)

        _run(_run_test())
        payload = json.loads(sent[0])
        assert payload["unread"] == 0
        assert payload["messages"] == []

    def test_ordering_unread_first(self):
        """Unread (is_read=0) messages appear before read (is_read=1)."""
        sent: list = []
        sess = _make_session(sent)

        async def _run_test():
            db = await _fresh_db()
            acc = await _seed_account(db)
            char = await _seed_char(db, acc)
            sender = await _seed_char(db, acc, name="S")
            await _send_mail(db, sender, char, subject="ReadMail", is_read=1)
            await _send_mail(db, sender, char, subject="UnreadMail", is_read=0)
            await sess._hud_sidebar_mail(db, char)

        _run(_run_test())
        payload = json.loads(sent[0])
        msgs = payload["messages"]
        assert msgs[0]["subject"] == "UnreadMail"
        assert msgs[1]["subject"] == "ReadMail"

    def test_limit_five(self):
        """At most 5 messages returned even with 6 in the inbox."""
        sent: list = []
        sess = _make_session(sent)

        async def _run_test():
            db = await _fresh_db()
            acc = await _seed_account(db)
            char = await _seed_char(db, acc)
            sender = await _seed_char(db, acc, name="S")
            for i in range(6):
                await _send_mail(db, sender, char, subject=f"Mail{i}")
            await sess._hud_sidebar_mail(db, char)

        _run(_run_test())
        payload = json.loads(sent[0])
        assert len(payload["messages"]) == 5

    def test_empty_inbox(self):
        """Empty inbox → unread=0, messages=[]."""
        sent: list = []
        sess = _make_session(sent)

        async def _run_test():
            db = await _fresh_db()
            acc = await _seed_account(db)
            char = await _seed_char(db, acc)
            await sess._hud_sidebar_mail(db, char)

        _run(_run_test())
        payload = json.loads(sent[0])
        assert payload["unread"] == 0
        assert payload["messages"] == []
