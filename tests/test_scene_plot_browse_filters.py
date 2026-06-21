# -*- coding: utf-8 -*-
"""
tests/test_scene_plot_browse_filters.py — browse filters for +plots / +scenes.

Covers the engine producers behind the Guide_20 documented browse commands:
  * engine.plots.get_closed_plots         (+plots closed)
  * engine.scenes.get_shared_scenes        (+scenes shared)
  * engine.scenes.get_player_shared_scenes (+scenes <player>)

The privacy contract is the load-bearing test: browsing another player's
public archive must NEVER surface their unshared (completed-but-private)
scenes.
"""

import asyncio
import time
import pytest
import aiosqlite


@pytest.fixture(scope="module")
def loop():
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


class FakeDB:
    """Mimics the Database wrapper used by engine.plots / engine.scenes."""
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
    async def _make():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await conn.executescript("""
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT DEFAULT '',
                scene_type TEXT DEFAULT 'Social',
                location TEXT DEFAULT '',
                room_id INTEGER,
                creator_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                started_at REAL NOT NULL,
                completed_at REAL,
                shared_at REAL
            );
            CREATE TABLE scene_participants (
                scene_id INTEGER NOT NULL,
                char_id INTEGER NOT NULL,
                PRIMARY KEY (scene_id, char_id)
            );
            CREATE TABLE plots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                summary TEXT DEFAULT '',
                creator_id INTEGER NOT NULL,
                creator_name TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
        """)
        now = time.time()
        # Characters: Luke (1), Han (2)
        await conn.execute("INSERT INTO characters (name) VALUES ('Luke')")
        await conn.execute("INSERT INTO characters (name) VALUES ('Han')")

        # Scenes:
        #  1 shared (Luke+Han)   — older shared_at
        #  2 shared (Luke only)  — newer shared_at
        #  3 active (Han)        — never shared
        #  4 completed-unshared (Han) — the privacy trap
        await conn.execute(
            "INSERT INTO scenes (title, creator_id, status, started_at, shared_at) "
            "VALUES ('Cantina Brawl', 1, 'shared', ?, ?)", (now - 3600, now - 3000))
        await conn.execute(
            "INSERT INTO scenes (title, creator_id, status, started_at, shared_at) "
            "VALUES ('Escape Run', 1, 'shared', ?, ?)", (now - 1800, now - 1000))
        await conn.execute(
            "INSERT INTO scenes (title, creator_id, status, started_at) "
            "VALUES ('Hyperspace Jump', 2, 'active', ?)", (now,))
        await conn.execute(
            "INSERT INTO scenes (title, creator_id, status, started_at, completed_at) "
            "VALUES ('Hans Secret', 2, 'completed', ?, ?)", (now - 7200, now - 6000))

        # Participants
        for sid, cid in [(1, 1), (1, 2), (2, 1), (4, 2)]:
            await conn.execute(
                "INSERT INTO scene_participants (scene_id, char_id) VALUES (?, ?)",
                (sid, cid))
        await conn.commit()
        return FakeDB(conn)

    return loop.run_until_complete(_make())


# ── +plots closed ──────────────────────────────────────────────────────────

def test_get_closed_plots_returns_only_closed(db, loop):
    from engine.plots import create_plot, close_plot, get_closed_plots
    loop.run_until_complete(create_plot(db, 1, "Luke", "Open Arc"))
    loop.run_until_complete(create_plot(db, 2, "Han", "Done Arc"))
    loop.run_until_complete(close_plot(db, 2))

    closed = loop.run_until_complete(get_closed_plots(db))
    assert len(closed) == 1
    assert closed[0]["title"] == "Done Arc"
    assert closed[0]["status"] == "closed"


def test_get_closed_plots_empty(db, loop):
    from engine.plots import create_plot, get_closed_plots
    loop.run_until_complete(create_plot(db, 1, "Luke", "Still Open"))
    closed = loop.run_until_complete(get_closed_plots(db))
    assert closed == []


# ── +scenes shared ─────────────────────────────────────────────────────────

def test_get_shared_scenes_excludes_unshared(db, loop):
    from engine.scenes import get_shared_scenes
    shared = loop.run_until_complete(get_shared_scenes(db))
    titles = {s["title"] for s in shared}
    assert titles == {"Cantina Brawl", "Escape Run"}
    # active + completed-unshared never appear
    assert "Hyperspace Jump" not in titles
    assert "Hans Secret" not in titles


def test_get_shared_scenes_ordered_newest_shared_first(db, loop):
    from engine.scenes import get_shared_scenes
    shared = loop.run_until_complete(get_shared_scenes(db))
    assert [s["title"] for s in shared] == ["Escape Run", "Cantina Brawl"]


# ── +scenes <player> ───────────────────────────────────────────────────────

def test_player_shared_scenes_by_name(db, loop):
    from engine.scenes import get_player_shared_scenes
    luke = loop.run_until_complete(get_player_shared_scenes(db, "Luke"))
    assert {s["title"] for s in luke} == {"Cantina Brawl", "Escape Run"}


def test_player_shared_scenes_name_is_case_insensitive(db, loop):
    from engine.scenes import get_player_shared_scenes
    han = loop.run_until_complete(get_player_shared_scenes(db, "hAn"))
    # Han only participated in the shared Cantina Brawl
    assert {s["title"] for s in han} == {"Cantina Brawl"}


def test_player_shared_scenes_never_leaks_unshared(db, loop):
    """Privacy contract: Han's completed-but-unshared 'Hans Secret' (scene 4,
    which only Han participated in) must NOT appear when browsing his archive."""
    from engine.scenes import get_player_shared_scenes
    han = loop.run_until_complete(get_player_shared_scenes(db, "Han"))
    titles = {s["title"] for s in han}
    assert "Hans Secret" not in titles


def test_player_shared_scenes_unknown_player(db, loop):
    from engine.scenes import get_player_shared_scenes
    nobody = loop.run_until_complete(get_player_shared_scenes(db, "Grievous"))
    assert nobody == []
