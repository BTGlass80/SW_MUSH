# -*- coding: utf-8 -*-
"""
tests/test_db_proxy.py — Tests for Database proxy methods (fetchall, fetchone,
execute, commit, execute_commit, executescript).

These methods are thin wrappers around the raw aiosqlite connection. The tests
verify that each proxy method works correctly, including edge cases like empty
result sets and multi-statement batches.
"""
import asyncio
import os
import sys
import tempfile
import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Database


@pytest.fixture
def db_path(tmp_path):
    """Return a temp file path for a test database."""
    return str(tmp_path / "test.db")


@pytest.fixture
def event_loop():
    """Create an event loop for tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _make_db(db_path: str) -> Database:
    """Create and connect a Database instance, initialize schema."""
    db = Database(db_path)
    await db.connect()
    await db.initialize()
    return db


# ── fetchall ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetchall_returns_rows(db_path):
    """fetchall returns a list of Row objects for matching rows."""
    db = await _make_db(db_path)
    try:
        # Accounts table exists from schema init
        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("alice", "hash1"))
        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("bob", "hash2"))
        await db.commit()

        rows = await db.fetchall("SELECT username FROM accounts ORDER BY username")
        assert len(rows) == 2
        assert dict(rows[0])["username"] == "alice"
        assert dict(rows[1])["username"] == "bob"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_fetchall_empty(db_path):
    """fetchall returns an empty list when no rows match."""
    db = await _make_db(db_path)
    try:
        rows = await db.fetchall("SELECT * FROM accounts WHERE id = ?", (99999,))
        assert rows == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_fetchall_with_params(db_path):
    """fetchall correctly binds parameters."""
    db = await _make_db(db_path)
    try:
        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("carol", "hash3"))
        await db.commit()

        rows = await db.fetchall("SELECT * FROM accounts WHERE username = ?", ("carol",))
        assert len(rows) == 1
        assert dict(rows[0])["username"] == "carol"
    finally:
        await db.close()


# ── fetchone ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetchone_returns_row(db_path):
    """fetchone returns the first row when results exist."""
    db = await _make_db(db_path)
    try:
        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("dave", "hash4"))
        await db.commit()

        row = await db.fetchone("SELECT * FROM accounts WHERE username = ?", ("dave",))
        assert row is not None
        assert dict(row)["username"] == "dave"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_fetchone_returns_none(db_path):
    """fetchone returns None when no rows match."""
    db = await _make_db(db_path)
    try:
        row = await db.fetchone("SELECT * FROM accounts WHERE id = ?", (99999,))
        assert row is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_fetchone_count(db_path):
    """fetchone works with COUNT(*) queries."""
    db = await _make_db(db_path)
    try:
        row = await db.fetchone("SELECT COUNT(*) as c FROM accounts")
        assert row is not None
        assert dict(row)["c"] == 0  # no accounts yet

        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("eve", "hash5"))
        await db.commit()

        row = await db.fetchone("SELECT COUNT(*) as c FROM accounts")
        assert dict(row)["c"] == 1
    finally:
        await db.close()


# ── execute + commit ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_and_commit(db_path):
    """execute + commit persists data."""
    db = await _make_db(db_path)
    try:
        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("frank", "hash6"))
        await db.commit()

        rows = await db.fetchall("SELECT username FROM accounts")
        assert len(rows) == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_execute_without_commit_not_visible_after_reopen(db_path):
    """Data written without commit may not survive a close/reopen cycle."""
    db = await _make_db(db_path)
    await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                     ("ghost", "hash7"))
    # Intentionally no commit
    await db.close()

    # Reopen — WAL mode may or may not have flushed, but without commit
    # the write is in an incomplete transaction state
    db2 = Database(db_path)
    await db2.connect()
    try:
        rows = await db2.fetchall("SELECT * FROM accounts WHERE username = ?", ("ghost",))
        # The row should not be there (uncommitted data rolled back on close)
        assert len(rows) == 0
    finally:
        await db2.close()


# ── execute_commit ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_commit(db_path):
    """execute_commit bundles execute + commit in one call."""
    db = await _make_db(db_path)
    try:
        await db.execute_commit(
            "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
            ("grace", "hash8"),
        )
        row = await db.fetchone("SELECT username FROM accounts WHERE username = ?",
                                ("grace",))
        assert row is not None
        assert dict(row)["username"] == "grace"
    finally:
        await db.close()


# ── executescript ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_executescript(db_path):
    """executescript runs multi-statement SQL."""
    db = await _make_db(db_path)
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, val TEXT);
            INSERT INTO test_table (val) VALUES ('hello');
            INSERT INTO test_table (val) VALUES ('world');
        """)
        rows = await db.fetchall("SELECT val FROM test_table ORDER BY id")
        assert len(rows) == 2
        assert dict(rows[0])["val"] == "hello"
        assert dict(rows[1])["val"] == "world"
    finally:
        await db.close()


# ── Multi-statement batch (no auto-commit) ───────────────────────────────────

@pytest.mark.asyncio
async def test_batch_writes_single_commit(db_path):
    """Multiple execute() calls share a single commit — atomicity preserved."""
    db = await _make_db(db_path)
    try:
        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("batch1", "h1"))
        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("batch2", "h2"))
        await db.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                         ("batch3", "h3"))
        await db.commit()

        row = await db.fetchone("SELECT COUNT(*) as c FROM accounts")
        assert dict(row)["c"] == 3
    finally:
        await db.close()
