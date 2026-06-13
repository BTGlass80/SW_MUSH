# -*- coding: utf-8 -*-
"""
tests/conftest.py — Top-level pytest configuration and fixture surface.

Re-exports the ``harness`` fixture from ``tests/harness.py`` so test
files can take it as a parameter.

Adds a ``--smoke-era`` CLI option for per-run era selection of smoke
scenarios.

Adds a session-scoped failure hook that, on any test failure inside
``tests/smoke/``, calls ``harness.dump_for_failure(...)`` for every
client session the harness handed out — so Brian gets the player
transcript, JSON events, and DB rows on disk without needing to
re-run anything.
"""
from __future__ import annotations

import os

import pytest

# Re-export the harness fixture (preserves existing import contract).
from tests.harness import harness  # noqa: F401  (fixture re-export)


# ───────────────────────────────────────────────────────────────────────────
# aiosqlite worker threads -> daemon (2026-06-12 — root fix for the exit hang)
# ───────────────────────────────────────────────────────────────────────────
#
# aiosqlite runs each connection on a dedicated worker thread (a
# threading.Thread blocked on a queue waiting for the next DB op); it only
# stops when the connection is explicitly closed. Any test that opens a
# Database/connection without closing it in teardown leaves that NON-DAEMON
# worker thread alive, which blocks interpreter exit — so `python -m pytest`
# hangs after writing its summary, and orphaned processes pile up. A
# post-pytest thread audit confirmed these ``_connection_worker_thread``
# threads (aiosqlite/core.py) are the SOLE survivors.
#
# Marking the worker threads daemon lets the interpreter exit cleanly even
# when a test leaks a connection — idle worker threads (blocked on the op
# queue) are killed at shutdown, which is safe. This is the real fix; it
# replaces the SW_MUSH_HARD_EXIT os._exit band-aid from drop 22.
try:
    import aiosqlite as _aiosqlite

    _orig_conn_init = _aiosqlite.Connection.__init__

    def _daemon_conn_init(self, *args, **kwargs):
        _orig_conn_init(self, *args, **kwargs)
        try:
            # aiosqlite spawns self._thread = Thread(target=_connection_worker_
            # thread) (core.py:90) with no daemon flag. Mark it daemon so a
            # leaked (unclosed) connection can't block interpreter exit.
            self._thread.daemon = True
        except Exception:
            pass

    _aiosqlite.Connection.__init__ = _daemon_conn_init
except Exception:
    pass


# ───────────────────────────────────────────────────────────────────────────
# Stale-duplicate-tree guard (May 19 2026 packaging-phantom remediation)
# ───────────────────────────────────────────────────────────────────────────
#
# A May 18 [2] drop intended to ship test files at:
#   tests/test_pvf5_schema_seed_collision.py
#   tests/smoke/test_smoke_wilderness_combat.py
#   tests/smoke/scenarios/pvp_flag.py  (update)
#   tests/smoke/scenarios/wilderness_combat.py  (update)
# but the zip was packaged with an extra "tests/" prefix, so the
# files landed at tests/tests/* instead. Pytest then discovered AND
# ran them from that duplicate path, where the harness fixture from
# tests/conftest.py is in scope but the imports resolve to the WRONG
# (stale) scenario modules under tests/tests/smoke/scenarios/.
#
# The correct-path versions of these files are now shipped (this
# drop), and the stale duplicate tree at tests/tests/ should be
# deleted from the working copy. This collect_ignore is a
# belt-and-suspenders measure that prevents the duplicate tree from
# being collected by pytest in case the directory is not yet
# manually removed.
#
# Once the duplicate tree is deleted from disk, this collect_ignore
# becomes a no-op and can be removed in a later cleanup pass.

collect_ignore = [
    "tests",  # stale duplicate tree from May 18 [2] packaging phantom
]


# ───────────────────────────────────────────────────────────────────────────
# CLI options
# ───────────────────────────────────────────────────────────────────────────

def pytest_addoption(parser):
    """Register custom CLI options for the smoke harness."""
    parser.addoption(
        "--smoke-era",
        action="store",
        default="clone_wars",
        help=(
            "Active era for smoke scenarios. One of 'gcw', 'clone_wars'. "
            "Default: clone_wars (the launch target). Pass --smoke-era=gcw "
            "to exercise the legacy GCW seed; era-specific scenarios pin "
            "the era they need via the `smoke_era` class attribute (see "
            "tests/smoke/test_smoke_era_clone_wars.py for the pattern)."
        ),
    )


# ───────────────────────────────────────────────────────────────────────────
# Failure-dump hook (design §9.2 Q5)
# ───────────────────────────────────────────────────────────────────────────
#
# When a smoke scenario fails, dump the per-session transcript, JSON
# events, and key DB rows into ``tests/smoke/_failures/<test_id>/``.
# This is the debug bundle Brian needs to repro manually.
#
# We use the makereport hook (post-call phase) and only act on tests
# under tests/smoke/ that took the harness fixture.

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return
    if not rep.failed:
        return

    # Only act on tests that live under tests/smoke/.
    item_path = str(getattr(item, "fspath", "") or "")
    smoke_root = os.path.join("tests", "smoke")
    if smoke_root not in item_path.replace("\\", "/"):
        return

    # Find the harness in the fixturenames; bail if absent.
    h = None
    try:
        h = item.funcargs.get("harness")
    except Exception:
        return
    if h is None:
        return

    # Where to write the dump.
    failures_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "smoke", "_failures",
    )

    # Sanitize the test ID for use as a directory name.
    safe_id = item.nodeid.replace("/", "_").replace("::", "__")
    safe_id = "".join(c if c.isalnum() or c in "._-" else "_"
                      for c in safe_id)

    # Dump every session the harness handed out. Async — drive via
    # the running loop if any, else create one.
    import asyncio

    async def _dump_all():
        for cs in h._sessions:
            try:
                await h.dump_for_failure(cs, failures_dir, safe_id)
            except Exception:
                # Don't let dump failures mask the real test failure.
                pass

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Called from sync context inside an async test —
            # schedule and let it complete.
            asyncio.ensure_future(_dump_all())
        else:
            loop.run_until_complete(_dump_all())
    except RuntimeError:
        # No loop available (post-teardown). Skip dump.
        pass
