# -*- coding: utf-8 -*-
"""WS-routing verify-fixes (2026-06-18):
- broadcast_chat's global (room_id=None) branch must iterate the session-dict
  VALUES (Session objects), not its KEYS (ints) — the latter AttributeErrors on
  `.send_json`.
- the client WS dispatch must not carry a duplicate (dead) `case 'pose_event'`.
"""
import os
from unittest.mock import AsyncMock, MagicMock

from server.session import SessionManager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def test_broadcast_chat_global_iterates_session_values():
    sm = SessionManager()
    s1 = MagicMock(); s1.id = 1; s1.character = {"id": 1}; s1.send_json = AsyncMock()
    s2 = MagicMock(); s2.id = 2; s2.character = {"id": 2}; s2.send_json = AsyncMock()
    sm.add(s1); sm.add(s2)

    # room_id=None → the global branch. Before the fix this iterated dict KEYS
    # (ints) and AttributeError'd on int.send_json.
    await sm.broadcast_chat("sys", "System", "hello", room_id=None)

    s1.send_json.assert_awaited_once()
    s2.send_json.assert_awaited_once()
    assert s1.send_json.await_args.args[0] == "chat"


def test_client_ws_dispatch_has_no_duplicate_pose_event_case():
    src = open(os.path.join(ROOT, "static", "client.html"), encoding="utf-8").read()
    assert src.count("case 'pose_event'") == 1, "dead duplicate pose_event dispatch arm"
