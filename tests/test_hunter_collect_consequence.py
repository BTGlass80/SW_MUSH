"""tests/test_hunter_collect_consequence.py — the DSP hunter's PC-death
collect-consequence (Drop 4b, completing T1.3.4).

The inverse of the player-beats-hunter loop (on_dsp_hunter_killed): when the
runtime-spawned hunter DOWNS its quarry, the hunter has collected its bounty —
it despawns and the pursuit resets to a fresh start. Three layers:

  * PURE: the new kill-line decider (distinct from the escape `collected_line`,
    era/Q1-clean).
  * RUNTIME: `on_quarry_collected` over a stub DB — no-op without a live hunter,
    despawn + pursuit-clear + room announce when one is attached.
  * WIRING: `engine.death.on_pc_death` fires the hook on every death path
    (verified via the secured-zone early-return path with the hook monkeypatched).

asyncio.run throughout (3.14-safe).
"""
from __future__ import annotations

import asyncio

import engine.dsp_hunter as H
import engine.dsp_hunter_runtime as RT


_BANNED = ("imperial", "empire", "rebel", "stormtrooper", "x-wing",
           "tie fighter", "star destroyer", "sith", "vader", "palpatine")


def _run(coro):
    return asyncio.run(coro)


# ── stubs ────────────────────────────────────────────────────────────────────
class _StubDB:
    def __init__(self, pursuit=None, npc=None):
        self._pursuit = pursuit
        self._npc = npc
        self.deleted = []
        self.cleared = []

    async def get_dsp_pursuit(self, cid):
        return self._pursuit

    async def get_npc(self, nid):
        return self._npc

    async def delete_npc(self, nid):
        self.deleted.append(nid)

    async def clear_dsp_pursuit(self, cid):
        self.cleared.append(cid)
        return True


class _StubSession:
    def __init__(self):
        self.lines = []

    async def send_line(self, line):
        self.lines.append(line)


class _StubMgr:
    def __init__(self, sess):
        self._sess = [sess]

    def sessions_in_room(self, rid):
        return self._sess


# ── pure ─────────────────────────────────────────────────────────────────────
def test_kill_line_distinct_clean_and_named():
    name = "Vex Korrin"
    kill = H.hunter_collected_line(name)
    escape = H.collected_line(name)
    assert name in kill
    assert kill != escape                     # distinct semantics from the escape line
    assert "collected" in kill.lower()        # it's a collect/kill beat
    for bad in _BANNED:
        assert bad not in kill.lower(), f"banned term {bad!r} in kill line"


# ── runtime ──────────────────────────────────────────────────────────────────
def test_collect_noop_without_pursuit():
    async def go():
        db = _StubDB(pursuit=None)
        out = await RT.on_quarry_collected(db, 42, session_mgr=None, room_id=7)
        assert out is False
        assert db.deleted == [] and db.cleared == []
    _run(go())


def test_collect_noop_without_live_hunter():
    async def go():
        # pursuit exists but no hunter is spawned -> nothing to collect
        db = _StubDB(pursuit={"hunter_name": "Vex", "spawned_npc_id": None})
        out = await RT.on_quarry_collected(db, 42, session_mgr=None, room_id=7)
        assert out is False
        assert db.deleted == [] and db.cleared == []
    _run(go())


def test_collect_despawns_clears_and_announces():
    async def go():
        sess = _StubSession()
        mgr = _StubMgr(sess)
        db = _StubDB(
            pursuit={"hunter_name": "Vex Korrin", "spawned_npc_id": 55},
            npc={"id": 55, "room_id": 7},
        )
        out = await RT.on_quarry_collected(db, 42, session_mgr=mgr, room_id=7)
        assert out is True
        assert db.deleted == [55]             # hunter despawned (contract fulfilled)
        assert db.cleared == [42]             # pursuit reset to a fresh start
        # the collect beat was announced to the room
        assert any("collected" in ln.lower() for ln in sess.lines)
    _run(go())


def test_collect_resolves_room_from_npc_when_unspecified():
    async def go():
        sess = _StubSession()
        mgr = _StubMgr(sess)
        db = _StubDB(
            pursuit={"hunter_name": "Vex", "spawned_npc_id": 55},
            npc={"id": 55, "room_id": 9},
        )
        # room_id omitted -> resolved from the hunter NPC row
        out = await RT.on_quarry_collected(db, 42, session_mgr=mgr, room_id=None)
        assert out is True and db.deleted == [55] and db.cleared == [42]
        assert sess.lines  # announced into the resolved room
    _run(go())


# ── wiring: on_pc_death fires the hook on every death path ────────────────────
def test_on_pc_death_fires_collect_hook(monkeypatch):
    recorded = {}

    async def _fake_collect(db, victim_id, *, session_mgr=None, room_id=None):
        recorded["victim"] = victim_id
        recorded["room"] = room_id
        return True

    monkeypatch.setattr(RT, "on_quarry_collected", _fake_collect, raising=True)

    from engine.death import on_pc_death

    async def go():
        # secured zone -> on_pc_death returns early (no corpse), but the collect
        # hook is placed BEFORE that return, so it must still fire.
        return await on_pc_death(
            object(), char_id=42, room_id=7, security_level="secured",
        )

    _run(go())
    assert recorded == {"victim": 42, "room": 7}
