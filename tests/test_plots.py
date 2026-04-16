# -*- coding: utf-8 -*-
"""
tests/test_plots.py — Unit tests for Plot / Story Arc Tracker.
"""

import asyncio
import time
import pytest
import aiosqlite

# ── Fixture: in-memory DB with schema ──────────────────────────────────────────

class FakeDB:
    """Mimics Database wrapper with _db attribute pointing to raw connection."""
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

    async def execute_commit(self, sql, params=()):
        await self._db.execute(sql, params)
        await self._db.commit()

@pytest.fixture
def db():
    """Create an in-memory SQLite DB with plots + scenes schema."""
    async def _make():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await conn.executescript("""
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER DEFAULT 1,
                name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
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
            CREATE TABLE plot_scenes (
                plot_id INTEGER NOT NULL,
                scene_id INTEGER NOT NULL,
                linked_at REAL NOT NULL,
                PRIMARY KEY (plot_id, scene_id)
            );
        """)
        await conn.commit()

        # Seed test data
        await conn.execute(
            "INSERT INTO characters (name) VALUES (?)", ("Luke",)
        )
        await conn.execute(
            "INSERT INTO characters (name) VALUES (?)", ("Han",)
        )
        now = time.time()
        await conn.execute(
            "INSERT INTO scenes (title, creator_id, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?)",
            ("Cantina Brawl", 1, "shared", now - 3600, now - 1800)
        )
        await conn.execute(
            "INSERT INTO scenes (title, creator_id, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?)",
            ("Escape from Tatooine", 1, "shared", now - 1800, now - 900)
        )
        await conn.execute(
            "INSERT INTO scenes (title, creator_id, status, started_at) VALUES (?, ?, ?, ?)",
            ("Hyperspace Jump", 2, "active", now)
        )
        # Add participants
        await conn.execute(
            "INSERT INTO scene_participants (scene_id, char_id) VALUES (?, ?)", (1, 1)
        )
        await conn.execute(
            "INSERT INTO scene_participants (scene_id, char_id) VALUES (?, ?)", (1, 2)
        )
        await conn.execute(
            "INSERT INTO scene_participants (scene_id, char_id) VALUES (?, ?)", (2, 1)
        )
        # Add poses
        await conn.execute(
            "INSERT INTO scene_poses (scene_id, char_id, char_name, pose_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (1, 1, "Luke", "draws his blaster", now - 3500)
        )
        await conn.execute(
            "INSERT INTO scene_poses (scene_id, char_id, char_name, pose_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (1, 2, "Han", "ducks behind the bar", now - 3400)
        )
        await conn.commit()

        return FakeDB(conn)

    return asyncio.get_event_loop().run_until_complete(_make())


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_create_plot(db):
    from engine.plots import create_plot
    p = asyncio.get_event_loop().run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Rescue Mission",
                    summary="Rescue the princess from the Death Star")
    )
    assert p["id"] == 1
    assert p["title"] == "Rescue Mission"
    assert p["summary"] == "Rescue the princess from the Death Star"
    assert p["creator_id"] == 1
    assert p["creator_name"] == "Luke"
    assert p["status"] == "open"


def test_get_plot(db):
    from engine.plots import create_plot, get_plot
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Test Plot")
    )
    p = loop.run_until_complete(get_plot(db, 1))
    assert p is not None
    assert p["title"] == "Test Plot"


def test_get_plot_not_found(db):
    from engine.plots import get_plot
    p = asyncio.get_event_loop().run_until_complete(get_plot(db, 999))
    assert p is None


def test_get_open_plots(db):
    from engine.plots import create_plot, get_open_plots, close_plot
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Open Plot")
    )
    loop.run_until_complete(
        create_plot(db, creator_id=2, creator_name="Han", title="Closed Plot")
    )
    loop.run_until_complete(close_plot(db, 2))

    plots = loop.run_until_complete(get_open_plots(db))
    assert len(plots) == 1
    assert plots[0]["title"] == "Open Plot"


def test_get_all_plots(db):
    from engine.plots import create_plot, get_all_plots, close_plot
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Plot A")
    )
    loop.run_until_complete(
        create_plot(db, creator_id=2, creator_name="Han", title="Plot B")
    )
    loop.run_until_complete(close_plot(db, 2))

    all_plots = loop.run_until_complete(get_all_plots(db, include_closed=True))
    assert len(all_plots) == 2

    open_only = loop.run_until_complete(get_all_plots(db, include_closed=False))
    assert len(open_only) == 1


def test_update_plot_summary(db):
    from engine.plots import create_plot, update_plot, get_plot
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Test")
    )
    loop.run_until_complete(
        update_plot(db, 1, summary="Updated summary")
    )
    p = loop.run_until_complete(get_plot(db, 1))
    assert p["summary"] == "Updated summary"


def test_close_and_reopen(db):
    from engine.plots import create_plot, close_plot, reopen_plot, get_plot
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    loop.run_until_complete(close_plot(db, 1))
    p = loop.run_until_complete(get_plot(db, 1))
    assert p["status"] == "closed"

    loop.run_until_complete(reopen_plot(db, 1))
    p = loop.run_until_complete(get_plot(db, 1))
    assert p["status"] == "open"


def test_link_scene(db):
    from engine.plots import create_plot, link_scene, get_scene_count
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    ok = loop.run_until_complete(link_scene(db, 1, 1))
    assert ok is True
    count = loop.run_until_complete(get_scene_count(db, 1))
    assert count == 1


def test_link_scene_duplicate(db):
    from engine.plots import create_plot, link_scene
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    loop.run_until_complete(link_scene(db, 1, 1))
    ok = loop.run_until_complete(link_scene(db, 1, 1))
    assert ok is False  # Already linked


def test_unlink_scene(db):
    from engine.plots import create_plot, link_scene, unlink_scene, get_scene_count
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    loop.run_until_complete(link_scene(db, 1, 1))
    ok = loop.run_until_complete(unlink_scene(db, 1, 1))
    assert ok is True
    count = loop.run_until_complete(get_scene_count(db, 1))
    assert count == 0


def test_unlink_not_found(db):
    from engine.plots import create_plot, unlink_scene
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    ok = loop.run_until_complete(unlink_scene(db, 1, 999))
    assert ok is False


def test_get_plot_scenes(db):
    from engine.plots import create_plot, link_scene, get_plot_scenes
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    loop.run_until_complete(link_scene(db, 1, 1))
    loop.run_until_complete(link_scene(db, 1, 2))

    scenes = loop.run_until_complete(get_plot_scenes(db, 1))
    assert len(scenes) == 2
    assert scenes[0]["title"] == "Cantina Brawl"  # Earlier started_at
    assert scenes[1]["title"] == "Escape from Tatooine"


def test_plot_scenes_include_participants(db):
    from engine.plots import create_plot, link_scene, get_plot_scenes
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    loop.run_until_complete(link_scene(db, 1, 1))

    scenes = loop.run_until_complete(get_plot_scenes(db, 1))
    assert len(scenes) == 1
    assert "Luke" in scenes[0]["participants"]
    assert "Han" in scenes[0]["participants"]


def test_plot_scenes_include_pose_count(db):
    from engine.plots import create_plot, link_scene, get_plot_scenes
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    loop.run_until_complete(link_scene(db, 1, 1))

    scenes = loop.run_until_complete(get_plot_scenes(db, 1))
    assert scenes[0]["pose_count"] == 2


def test_link_updates_plot_timestamp(db):
    from engine.plots import create_plot, link_scene, get_plot
    loop = asyncio.get_event_loop()
    p1 = loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Arc")
    )
    original_ts = p1["updated_at"]
    import time as t
    t.sleep(0.05)
    loop.run_until_complete(link_scene(db, 1, 1))
    p2 = loop.run_until_complete(get_plot(db, 1))
    assert p2["updated_at"] > original_ts


def test_get_my_plots_as_creator(db):
    from engine.plots import create_plot, get_my_plots
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Luke's Plot")
    )
    loop.run_until_complete(
        create_plot(db, creator_id=2, creator_name="Han", title="Han's Plot")
    )
    my = loop.run_until_complete(get_my_plots(db, char_id=1))
    assert len(my) == 1
    assert my[0]["title"] == "Luke's Plot"


def test_get_my_plots_as_participant(db):
    from engine.plots import create_plot, link_scene, get_my_plots
    loop = asyncio.get_event_loop()
    # Han creates plot, links scene 1 (which Luke participates in)
    loop.run_until_complete(
        create_plot(db, creator_id=2, creator_name="Han", title="Han's Arc")
    )
    loop.run_until_complete(link_scene(db, 1, 1))

    # Luke should see it via participation
    my = loop.run_until_complete(get_my_plots(db, char_id=1))
    assert len(my) == 1
    assert my[0]["title"] == "Han's Arc"


def test_scene_count_empty(db):
    from engine.plots import create_plot, get_scene_count
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Empty")
    )
    count = loop.run_until_complete(get_scene_count(db, 1))
    assert count == 0


def test_update_no_fields(db):
    from engine.plots import create_plot, update_plot
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        create_plot(db, creator_id=1, creator_name="Luke", title="Test")
    )
    ok = loop.run_until_complete(update_plot(db, 1))
    assert ok is False
