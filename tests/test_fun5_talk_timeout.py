"""
test_fun5_talk_timeout.py — FUN5 de-LLM the critical path.

A hung Ollama call in TalkCommand._generate_and_display used to await until the
30s command timeout cancelled the whole command, which skipped the post-talk
chain advance (the intermittent "talk Major Tarrn did nothing" tutorial stall).
The LLM call is now hard-bounded by NPC_DIALOGUE_TIMEOUT_S → it falls back fast
so the command (and the chain advance after it) always completes.
"""
from __future__ import annotations

import asyncio
import time

import parser.npc_commands as npc


class _Brain:
    def __init__(self, hang_s=0.0, reply="real reply"):
        self._hang_s = hang_s
        self._reply = reply

    async def dialogue(self, **kw):
        if self._hang_s:
            await asyncio.sleep(self._hang_s)
        return self._reply

    def _get_fallback(self):
        return "Major Tarrn nods."


class _AICfg:
    npc_thinking_emote = False


class _AI:
    config = _AICfg()

    async def is_available(self):
        return True


class _Sess:
    def __init__(self):
        self.lines = []
        self._ai_offline_notified = False

    async def send_line(self, s=""):
        self.lines.append(s)


class _DB:
    async def get_room(self, rid):
        return {"id": rid, "name": "Room", "desc_long": "", "desc_short": ""}


class _Mgr:
    def __init__(self):
        self.said = []

    async def broadcast_json_to_room(self, room_id, typ, ev, **kw):
        if typ == "pose_event" and isinstance(ev, dict):
            self.said.append(ev.get("text", ""))

    async def broadcast_chat(self, channel, who, text, **kw):
        self.said.append(text)

    def __getattr__(self, name):
        async def _noop(*a, **k):
            return None
        return _noop


class _Ctx:
    def __init__(self):
        self.session = _Sess()
        self.db = _DB()
        self.session_mgr = _Mgr()


class _NPC:
    name = "Major Tarrn"
    id = 7


_CHAR = {"name": "Recruit", "id": 1, "room_id": 1}


def test_hung_dialogue_is_bounded_and_falls_back(monkeypatch):
    monkeypatch.setattr(npc, "NPC_DIALOGUE_TIMEOUT_S", 0.3)
    ctx = _Ctx()
    brain = _Brain(hang_s=5.0)  # would hang well past the bound

    async def _t():
        t0 = time.monotonic()
        await npc.TalkCommand()._generate_and_display(
            ctx, _CHAR, _NPC(), brain, _AI(), "hello", "")
        return time.monotonic() - t0

    dur = asyncio.run(_t())
    assert dur < 2.0, f"hung dialogue was not bounded ({dur:.2f}s)"
    assert any("nods" in t for t in ctx.session_mgr.said), ctx.session_mgr.said
    assert not any("real reply" in t for t in ctx.session_mgr.said)


def test_normal_dialogue_used(monkeypatch):
    monkeypatch.setattr(npc, "NPC_DIALOGUE_TIMEOUT_S", 5.0)
    ctx = _Ctx()
    brain = _Brain(hang_s=0.0, reply="At ease, trooper.")
    asyncio.run(npc.TalkCommand()._generate_and_display(
        ctx, _CHAR, _NPC(), brain, _AI(), "hello", ""))
    assert any("At ease, trooper." in t for t in ctx.session_mgr.said), ctx.session_mgr.said


def test_timeout_constant_is_well_below_command_budget():
    # Must be comfortably under the 30s dispatcher COMMAND_TIMEOUT so the
    # post-talk chain advance always gets to run.
    assert 1.0 <= npc.NPC_DIALOGUE_TIMEOUT_S <= 20.0
