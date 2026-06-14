# -*- coding: utf-8 -*-
"""tests/test_idle_queue_event_rewrite.py — EventRewriteTask persist/broadcast
coupling (TD.IDLE_QUEUE_EVENT_REWRITE_BROADCAST_WITHOUT_PERSIST).

The director-headline rewrite task does two things on the clean path: UPDATE
director_log, then re-broadcast the new headline to web clients. Those must be
coupled — a client that sees a live rewrite which was never written to the DB
gets the ORIGINAL headline back on reconnect/reload (contradictory state). The
fix gates the broadcast on the same `(db and event_id)` condition as the
persist, so broadcast implies persist.

Also re-confirms the era-guard in this path: an off-era rewrite neither
persists nor broadcasts (keeps the original template headline).
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.idle_queue import EventRewriteTask


_CLEAN_REWRITE = "Clone trooper patrols tighten across the spaceport district"
_OFF_ERA_REWRITE = "Imperial stormtroopers seize the docks at gunpoint"


class _FakeProtocol:
    value = "websocket"


class _FakeSession:
    def __init__(self):
        self.is_in_game = True
        self.protocol = _FakeProtocol()
        self.sent = []

    async def _send(self, payload):
        self.sent.append(payload)


class _FakeMgr:
    def __init__(self, sessions):
        self._sessions = sessions

    @property
    def all(self):
        return self._sessions


class _FakeDB:
    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))

    async def commit(self):
        self.commits += 1


class _FakeAI:
    def __init__(self, response):
        self._r = response

    async def generate(self, **kwargs):
        return self._r


class TestEventRewritePersistBroadcastCoupling(unittest.IsolatedAsyncioTestCase):
    def _task(self, session, event_id=5):
        return EventRewriteTask(
            event_id=event_id, headline="Trouble brews in the cantina district",
            zone_name="Mos Eisley", session_mgr=_FakeMgr([session]),
        )

    async def test_clean_path_persists_and_broadcasts(self):
        sess = _FakeSession()
        db = _FakeDB()
        await self._task(sess).execute(_FakeAI(_CLEAN_REWRITE), db)
        # Persisted...
        self.assertEqual(len(db.executed), 1, "expected one director_log UPDATE")
        self.assertIn("UPDATE director_log", db.executed[0][0])
        self.assertEqual(db.commits, 1)
        # ...and broadcast, with the rewrite text.
        self.assertEqual(len(sess.sent), 1, "expected one websocket broadcast")
        payload = json.loads(sess.sent[0])
        self.assertEqual(payload["type"], "news_event")
        self.assertIn("Clone trooper patrols", payload["text"])

    async def test_no_db_means_no_broadcast(self):
        # The fix: with db=None the rewrite can't persist, so it must NOT
        # broadcast (pre-fix it broadcast a headline that was never written).
        sess = _FakeSession()
        await self._task(sess).execute(_FakeAI(_CLEAN_REWRITE), None)
        self.assertEqual(sess.sent, [], "broadcast fired without a DB persist")

    async def test_zero_event_id_means_no_persist_or_broadcast(self):
        sess = _FakeSession()
        db = _FakeDB()
        await self._task(sess, event_id=0).execute(_FakeAI(_CLEAN_REWRITE), db)
        self.assertEqual(db.executed, [], "persisted with no event_id")
        self.assertEqual(sess.sent, [], "broadcast with no event_id")

    async def test_off_era_rewrite_neither_persists_nor_broadcasts(self):
        sess = _FakeSession()
        db = _FakeDB()
        await self._task(sess).execute(_FakeAI(_OFF_ERA_REWRITE), db)
        self.assertEqual(db.executed, [], "off-era rewrite was persisted")
        self.assertEqual(sess.sent, [], "off-era rewrite was broadcast")


if __name__ == "__main__":
    unittest.main(verbosity=2)
