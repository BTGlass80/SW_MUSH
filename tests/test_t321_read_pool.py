# -*- coding: utf-8 -*-
"""T3.21 — read-only SELECT connection pool (db/database.py).

SELECT-heavy read endpoints draw a read-only connection from a small pool
(mode=ro + PRAGMA query_only=ON) instead of serializing behind the single
writer connection. WAL lets the pool read concurrently with the writer
(autocommit conns: each read sees the latest committed state).
The pool connections are PHYSICALLY read-only, so this path cannot corrupt the
DB. (Brian decision #3, 2026-06-16 — "do not defer, need it now".)
"""
import asyncio
import os
import pathlib

import pytest

from db.database import Database

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


async def _mkdb(tmp_path) -> Database:
    db = Database(str(tmp_path / "pool.db"))
    await db.connect()
    await db.initialize()
    return db


async def test_read_fetchall_returns_committed_data(tmp_path):
    db = await _mkdb(tmp_path)
    try:
        acct_id = await db.create_account("reader_user", "password123")
        assert acct_id
        rows = await db.read_fetchall(
            "SELECT username FROM accounts WHERE id=?", (acct_id,))
        assert rows and rows[0]["username"] == "reader_user"
        one = await db.read_fetchone("SELECT username FROM accounts WHERE id=?", (acct_id,))
        assert one["username"] == "reader_user"
        assert await db.read_fetchone("SELECT 1 AS x WHERE 1=0") is None
    finally:
        await db.close()


async def test_read_pool_is_physically_read_only(tmp_path):
    db = await _mkdb(tmp_path)
    try:
        with pytest.raises(Exception):
            await db.read_fetchall(
                "INSERT INTO accounts (username, password_hash) VALUES ('x','y')")
        # the rejected write changed nothing
        rows = await db.read_fetchall(
            "SELECT COUNT(*) AS c FROM accounts WHERE username='x'")
        assert rows[0]["c"] == 0
    finally:
        await db.close()


async def test_rejected_write_does_not_poison_pool_conn(tmp_path):
    # verify-fix 2026-06-18: a query_only-rejected write must NOT leave the pooled
    # conn in an open transaction pinning a stale WAL snapshot (which served stale
    # reads + grew the -wal file unbounded). Size-1 pool forces conn reuse so the
    # bug, if present, shows as a stale read.
    prev = os.environ.get("SWMUSH_DB_READ_POOL")
    os.environ["SWMUSH_DB_READ_POOL"] = "1"
    try:
        db = await _mkdb(tmp_path)
        try:
            await db.read_fetchall("SELECT COUNT(*) AS c FROM accounts")  # build + use the conn
            with pytest.raises(Exception):
                await db.read_fetchall(
                    "INSERT INTO accounts (username, password_hash) VALUES ('x','y')")
            # a committed writer change AFTER the rejected write must be visible
            # through the SAME (size-1) pool conn — not a stale pre-write snapshot.
            await db.create_account("freshuser", "password123")
            rows = await db.read_fetchall(
                "SELECT COUNT(*) AS c FROM accounts WHERE username='freshuser'")
            assert rows[0]["c"] == 1, "pool conn served a stale snapshot (poisoned by the rejected write)"
        finally:
            await db.close()
    finally:
        if prev is None:
            os.environ.pop("SWMUSH_DB_READ_POOL", None)
        else:
            os.environ["SWMUSH_DB_READ_POOL"] = prev


async def test_concurrent_reads_exceed_pool_size(tmp_path):
    db = await _mkdb(tmp_path)
    try:
        await db.create_account("u", "password123")

        async def one():
            r = await db.read_fetchall("SELECT COUNT(*) AS c FROM accounts")
            return r[0]["c"]

        # far more concurrent readers than the pool size — exercises the
        # acquire/release queue without deadlock.
        results = await asyncio.gather(*[one() for _ in range(16)])
        assert results and all(x >= 1 for x in results)
    finally:
        await db.close()


async def test_pool_built_lazily_then_closed(tmp_path):
    db = await _mkdb(tmp_path)
    assert db._read_pool is None  # not built until first read
    await db.read_fetchall("SELECT 1 AS one")
    assert db._read_pool is not None
    assert len(db._read_conns) >= 1
    await db.close()
    assert db._read_pool is None and db._read_conns == []


async def test_pool_size_env_var(tmp_path):
    prev = os.environ.get("SWMUSH_DB_READ_POOL")
    os.environ["SWMUSH_DB_READ_POOL"] = "2"
    try:
        db = await _mkdb(tmp_path)
        await db.read_fetchall("SELECT 1 AS one")
        assert len(db._read_conns) == 2
        await db.close()
    finally:
        if prev is None:
            os.environ.pop("SWMUSH_DB_READ_POOL", None)
        else:
            os.environ["SWMUSH_DB_READ_POOL"] = prev


async def test_memory_db_falls_back_to_writer():
    # :memory: is per-connection — a 2nd connection would be a DIFFERENT empty
    # DB, so the pool must NOT be used; reads go to the writer connection.
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    try:
        await db.create_account("memu", "password123")
        rows = await db.read_fetchall(
            "SELECT COUNT(*) AS c FROM accounts WHERE username='memu'")
        assert rows[0]["c"] == 1          # served by the writer, sees the data
        assert db._read_pool is None      # never built a pool for :memory:
    finally:
        await db.close()


async def test_read_after_close_raises_not_rebuilds(tmp_path):
    db = await _mkdb(tmp_path)
    await db.read_fetchall("SELECT 1 AS one")  # build the pool
    await db.close()
    # closed -> must NOT silently rebuild a pool against the closed DB
    with pytest.raises(Exception):
        await db.read_fetchall("SELECT 1 AS one")
    assert db._read_pool is None


async def test_double_close_is_safe(tmp_path):
    db = await _mkdb(tmp_path)
    await db.read_fetchall("SELECT 1 AS one")
    await db.close()
    await db.close()  # idempotent — no exception, writer not double-closed
    assert db._db is None and db._read_conns == []


def test_portal_read_endpoints_routed_to_pool():
    # the read-only portal API must route SELECTs through the read pool
    # (regression guard: a new raw self._db.fetchall would re-serialize reads).
    src = (PROJECT_ROOT / "server" / "web_portal.py").read_text(encoding="utf-8")
    assert "self._db.read_fetchall(" in src
    assert "self._db.fetchall(" not in src
