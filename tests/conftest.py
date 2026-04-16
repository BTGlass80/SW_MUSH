# -*- coding: utf-8 -*-
"""
tests/conftest.py — Shared pytest fixtures for SW_MUSH integration tests.

Provides:
  - harness:         Full game stack with world build
  - harness_empty:   Game stack without world build (cheap, function-scoped)
  - player_session:  Pre-logged-in session for quick command testing
"""
import asyncio
import os
import shutil
import pytest
import sys

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.harness import TestHarness

# ── Shared DB path for world-build caching ──
# Building the world is expensive (~2s). We build once into a temp dir
# and copy the DB for each test function that needs it.
_BUILT_DB_PATH = None
_BUILD_LOCK = asyncio.Lock()


async def _ensure_built_db(tmp_path_factory):
    """Build world once and cache the DB file for reuse."""
    global _BUILT_DB_PATH
    if _BUILT_DB_PATH and os.path.exists(_BUILT_DB_PATH):
        return _BUILT_DB_PATH

    build_dir = tmp_path_factory.mktemp("sw_mush_build")
    h = TestHarness(build_dir)
    await h.setup(build_world=True)
    await h.teardown()
    _BUILT_DB_PATH = h.db_path
    return _BUILT_DB_PATH


@pytest.fixture
async def harness(tmp_path, tmp_path_factory):
    """
    Full game stack with Mos Eisley + Tutorial zones built.
    Each test gets its own copy of the pre-built DB.
    """
    # Build once, copy for each test
    built_db = await _ensure_built_db(tmp_path_factory)

    # Copy the built DB into this test's tmp dir
    dest_db = str(tmp_path / "test_game.db")
    shutil.copy2(built_db, dest_db)

    h = TestHarness(tmp_path)
    h.db_path = dest_db
    # Setup without world build (DB already has world)
    await h.setup(build_world=False)
    yield h
    await h.teardown()


@pytest.fixture
async def harness_empty(tmp_path):
    """
    Game stack with schema but no world build.
    Function-scoped — each test gets a clean DB.
    """
    h = TestHarness(tmp_path)
    await h.setup(build_world=False)
    yield h
    await h.teardown()


@pytest.fixture
async def player_session(harness):
    """
    A logged-in player session in the full world.

    Returns (session, harness) tuple for convenience.
    """
    session = await harness.login_as(
        f"Player_{id(harness) % 100000}_{len(harness._sessions)}",
        room_id=2,   # Mos Eisley Street
        credits=5000,
    )
    yield session, harness
