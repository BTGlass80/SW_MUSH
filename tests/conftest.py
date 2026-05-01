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
# CLI options
# ───────────────────────────────────────────────────────────────────────────

def pytest_addoption(parser):
    """Register custom CLI options for the smoke harness."""
    parser.addoption(
        "--smoke-era",
        action="store",
        default="gcw",
        help=(
            "Active era for smoke scenarios. One of 'gcw', 'clone_wars'. "
            "Default: gcw."
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
