# -*- coding: utf-8 -*-
"""
tests/test_qa_mail_body_cap.py — QA break-it MED (2026-06-20): in-game mail
had no server-side body size cap.

A single `@mail/quick` persisted a 262 KB body; ten ~2.6 MB — a cheap
storage-DoS. `MailCommand._do_send` (the single chokepoint every player mail
path routes through — compose, @mail/quick, @mail/reply) now truncates the
body to `MAX_MAIL_BODY_LEN` at the storage seam (and notifies the sender).
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from parser.mail_commands import MailCommand, MAX_MAIL_BODY_LEN


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeDB:
    def __init__(self):
        self.inserts = []

    async def execute(self, sql, params=()):
        self.inserts.append((sql, params))
        return types.SimpleNamespace(lastrowid=1)

    async def commit(self):
        pass


class _FakeSess:
    def __init__(self):
        self.character = {"id": 1, "name": "Sender"}
        self.lines = []

    async def send_line(self, t):
        self.lines.append(t)


class _FakeMgr:
    def find_by_character(self, rid):
        return None  # no online recipient


class _FakeCtx:
    def __init__(self):
        self.session = _FakeSess()
        self.db = _FakeDB()
        self.session_mgr = _FakeMgr()


def _send(body):
    cmd = MailCommand.__new__(MailCommand)
    ctx = _FakeCtx()
    state = {"to": [2], "to_names": ["B"], "subject": "Subj", "lines": [body]}
    _run(cmd._do_send(ctx, state))
    mail_inserts = [p for (s, p) in ctx.db.inserts
                    if "INSERT INTO mail (sender_id" in s]
    stored_body = mail_inserts[0][2]  # (sender_id, subject, body, sent_at)
    return stored_body, ctx.session.lines


class TestMailBodyCap(unittest.TestCase):
    def test_oversized_body_is_truncated_and_noticed(self):
        body, lines = _send("X" * 300_000)
        self.assertEqual(len(body), MAX_MAIL_BODY_LEN,
                         "an oversized mail body must be truncated to the cap")
        self.assertTrue(any("truncated" in l.lower() for l in lines),
                        "the sender should be told the message was truncated")

    def test_normal_body_is_unchanged(self):
        msg = "A short letter.\nSecond line."
        body, lines = _send(msg)
        self.assertEqual(body, msg)
        self.assertFalse(any("truncated" in l.lower() for l in lines))

    def test_cap_is_generous_but_bounded(self):
        # Sanity: the cap allows a multi-page letter but blocks abuse.
        self.assertGreaterEqual(MAX_MAIL_BODY_LEN, 4000)
        self.assertLessEqual(MAX_MAIL_BODY_LEN, 50_000)


if __name__ == "__main__":
    unittest.main()
