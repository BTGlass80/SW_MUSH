# -*- coding: utf-8 -*-
"""
tests/test_hud_scene_context.py — UX Drop 5: Session._hud_scene_context.

Exercises the engine HUD producer that surfaces the active RP scene onto
`hud['active_scene']`, against a REAL in-memory DB (start_scene / capture_pose),
not a fake. Mirrors the in-memory-DB harness style of tests/test_plots.py.

Asserts:
  · a live scene stamps hud['active_scene'] with the right scene_id/title/type
  · pose_count == total IC poses captured (creator + a second char)
  · per-participant pose_count is correct, and the VIEWER is included even
    though room_contents['players'] excludes self
  · OOC poses are EXCLUDED (is_ooc=1) from the counts
  · the auto-logged system pose (char_id IS NULL) is EXCLUDED
  · the key VANISHES (no 'active_scene') after stop_scene flips status off
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import aiosqlite
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import engine.scenes as scenes_mod
from server.session import Session


# ── Event-loop fixture (Python 3.14: aiosqlite conns are loop-bound) ───────────
@pytest.fixture(scope="module")
def loop():
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


class FakeDB:
    """Database-wrapper stand-in over a raw aiosqlite connection (mirrors
    tests/test_plots.py::FakeDB). _hud_scene_context + engine.scenes only use
    fetchall / execute / commit."""
    def __init__(self, conn):
        self._db = conn

    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def fetchone(self, sql, params=()):
        rows = await self._db.execute_fetchall(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()


@pytest.fixture
def db(loop):
    """In-memory DB with the scenes schema + two seeded characters."""
    async def _make():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await conn.executescript("""
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                scene_type TEXT DEFAULT 'Social',
                location TEXT DEFAULT '',
                room_id INTEGER,
                creator_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                started_at REAL NOT NULL,
                completed_at REAL,
                shared_at REAL
            );
            CREATE TABLE scene_poses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id INTEGER NOT NULL,
                char_id INTEGER,
                char_name TEXT NOT NULL,
                pose_text TEXT NOT NULL,
                pose_type TEXT DEFAULT 'pose',
                is_ooc INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE TABLE scene_participants (
                scene_id INTEGER NOT NULL,
                char_id INTEGER NOT NULL,
                PRIMARY KEY (scene_id, char_id)
            );
        """)
        await conn.execute("INSERT INTO characters (name) VALUES ('Rax')")    # id 1
        await conn.execute("INSERT INTO characters (name) VALUES ('Vesh')")   # id 2
        await conn.commit()
        return FakeDB(conn)

    return loop.run_until_complete(_make())


def _fresh_active_scenes():
    """Isolate the module-level _active_scenes cache around a test."""
    scenes_mod._active_scenes.clear()


def _stub_session(char_id, char_name):
    """A bare object that carries .character and the bound _hud_scene_context.
    We don't construct a full Session (it wants a transport); we only need the
    method + self.character, so call the unbound method with a stub `self`."""
    class _S:
        pass
    s = _S()
    s.character = {"id": char_id, "name": char_name}
    return s


async def _build_hud(db, room_id, viewer_id, viewer_name, other_players):
    """Run _hud_scene_context the way send_hud_update does: room_contents is
    populated first (with self EXCLUDED from players), then the producer runs."""
    hud = {"room_contents": {"npcs": [], "players": other_players,
                             "vendor_droids": []}}
    s = _stub_session(viewer_id, viewer_name)
    # Call the real method against the stub self.
    await Session._hud_scene_context(s, hud, db, room_id)
    return hud


def test_active_scene_block_and_pose_counts(db, loop):
    _fresh_active_scenes()
    ROOM = 42
    rax = {"id": 1, "name": "Rax", "is_admin": 0}
    vesh = {"id": 2, "name": "Vesh", "is_admin": 0}

    async def scenario():
        res = await scenes_mod.start_scene(db, rax, ROOM, title="Cantina standoff")
        assert res["ok"], res
        sid = res["scene_id"]

        # Rax (creator) poses x3 IC, Vesh poses x2 IC, plus one OOC each.
        for _ in range(3):
            await scenes_mod.capture_pose(db, sid, 1, "Rax", "leans in", "pose")
        for _ in range(2):
            await scenes_mod.capture_pose(db, sid, 2, "Vesh", "draws", "pose")
        # OOC poses must NOT count.
        await scenes_mod.capture_pose(db, sid, 1, "Rax", "brb", "pose", is_ooc=True)
        await scenes_mod.capture_pose(db, sid, 2, "Vesh", "lol", "pose", is_ooc=True)

        # Viewer = Rax. room_contents['players'] holds only the OTHER PC (Vesh),
        # since the real builder excludes self.
        hud = await _build_hud(db, ROOM, 1, "Rax",
                               [{"id": 2, "name": "Vesh"}])
        return hud, sid

    hud, sid = loop.run_until_complete(scenario())

    assert "active_scene" in hud, "live scene must stamp hud['active_scene']"
    blk = hud["active_scene"]
    assert blk["scene_id"] == sid
    assert blk["title"] == "Cantina standoff"
    assert blk["type"] == "Social"
    assert blk["creator_name"] == "Rax"          # resolved from the roster
    # 3 (Rax IC) + 2 (Vesh IC) = 5; OOC + system poses excluded.
    assert blk["pose_count"] == 5, blk

    counts = {p["id"]: p["pose_count"] for p in blk["participants"]}
    assert counts == {1: 3, 2: 2}, counts
    # Viewer (Rax, id 1) is present even though they were not in room players.
    names = {p["id"]: p["name"] for p in blk["participants"]}
    assert names[1] == "Rax" and names[2] == "Vesh"


def test_idle_room_has_no_active_scene_key(db, loop):
    _fresh_active_scenes()

    async def scenario():
        return await _build_hud(db, 999, 1, "Rax", [])

    hud = loop.run_until_complete(scenario())
    assert "active_scene" not in hud, "idle room must leave the key absent"


def test_key_vanishes_after_stop(db, loop):
    _fresh_active_scenes()
    ROOM = 77
    rax = {"id": 1, "name": "Rax", "is_admin": 0}

    async def scenario():
        res = await scenes_mod.start_scene(db, rax, ROOM, title="Quiet talk")
        sid = res["scene_id"]
        await scenes_mod.capture_pose(db, sid, 1, "Rax", "nods", "pose")

        hud_live = await _build_hud(db, ROOM, 1, "Rax", [])
        live = "active_scene" in hud_live

        stop = await scenes_mod.stop_scene(db, rax, ROOM)
        assert stop["ok"], stop

        hud_after = await _build_hud(db, ROOM, 1, "Rax", [])
        after = "active_scene" in hud_after
        return live, after

    live, after = loop.run_until_complete(scenario())
    assert live is True, "scene must be present while active"
    assert after is False, "active_scene key must vanish after stop_scene"


def test_system_pose_excluded_from_counts(db, loop):
    """start_scene auto-logs a system pose (char_id IS NULL). It must NOT
    inflate pose_count nor appear as a participant."""
    _fresh_active_scenes()
    ROOM = 55
    rax = {"id": 1, "name": "Rax", "is_admin": 0}

    async def scenario():
        res = await scenes_mod.start_scene(db, rax, ROOM, title="Solo")
        sid = res["scene_id"]
        # No IC poses captured yet — only the auto system pose exists.
        hud = await _build_hud(db, ROOM, 1, "Rax", [])
        return hud, sid

    hud, sid = loop.run_until_complete(scenario())
    blk = hud["active_scene"]
    # System pose (char_id NULL) excluded → zero total.
    assert blk["pose_count"] == 0, blk
    counts = {p["id"]: p["pose_count"] for p in blk["participants"]}
    assert counts == {1: 0}, counts
