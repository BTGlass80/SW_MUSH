# -*- coding: utf-8 -*-
"""Regression: the tutorial hint-timer must be cancelled on session teardown
(every disconnect funnels through SessionManager.remove), keyed on the monotonic
session.id — not leaked to spin send_line() on a dead transport, and not keyed on
the reusable id(session) address (verify-fix 2026-06-18)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from server.session import SessionManager
from engine import tutorial_v2


async def test_session_remove_cancels_hint_timer():
    room = next(iter(tutorial_v2.ROOM_HINTS), None)
    assert room, "expected at least one hinted tutorial room"
    s = MagicMock()
    s.id = 919191
    s.send_line = AsyncMock()

    tutorial_v2.start_hint_timer(s, room)
    assert s.id in tutorial_v2._hint_tasks
    task = tutorial_v2._hint_tasks[s.id]

    sm = SessionManager()
    sm.add(s)
    sm.remove(s)                                  # the disconnect funnel

    assert s.id not in tutorial_v2._hint_tasks    # de-registered on teardown
    await asyncio.sleep(0)                         # let the cancel propagate
    assert task.cancelled() or task.done()         # not leaked / spinning


async def test_hint_timer_keyed_on_session_id_not_address():
    s = MagicMock()
    s.id = 727272
    s.send_line = AsyncMock()
    tutorial_v2.start_hint_timer(s, next(iter(tutorial_v2.ROOM_HINTS)))
    try:
        assert s.id in tutorial_v2._hint_tasks        # keyed on session.id
        assert id(s) not in tutorial_v2._hint_tasks   # NOT the memory address
    finally:
        tutorial_v2.cancel_hint_timer(s)
