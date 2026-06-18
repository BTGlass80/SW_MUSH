# -*- coding: utf-8 -*-
"""Regression guard for the `sm.sessions` blocker (2026-06-18).

Live code must iterate sessions via ``SessionManager.all`` — the manager exposes
``all`` / ``_sessions`` / ``count`` and NEVER a ``.sessions`` attribute. Four sites
used a nonexistent ``<mgr>.sessions``: ``server/tick_handlers_death.py`` (wound
recovery — a permanent no-op, the blocker), ``engine/debt.py`` (Hutt-debt collection
— AttributeError swallowed per-debtor), and ``engine/achievements.py`` /
``engine/director.py`` (silently degraded). The bug hid because test stubs DID define
``.sessions`` while the real manager doesn't, so the tick bodies were never exercised.

This file pins both ends: (1) a behavioral test that ``wound_recovery_tick`` actually
iterates the live manager and clears an enrolled wounded session, and (2) a static
guard that no runtime module reintroduces ``<mgr>.sessions``.
"""
import asyncio
import glob
import re
import time
from unittest.mock import AsyncMock, MagicMock, patch

from server.session import SessionManager
from server import tick_handlers_death


def _run(coro):
    return asyncio.run(coro)


def _enroll(sm, char_id, *, wound_state, clear_at):
    s = MagicMock()
    s.id = char_id
    s.character = {"id": char_id, "wound_state": wound_state, "wound_clear_at": clear_at}
    s.send_line = AsyncMock()
    sm.add(s)
    return s


class TestWoundRecoveryTickIteratesLiveSessions:
    def test_tick_clears_wound_for_enrolled_session(self):
        sm = SessionManager()
        s = _enroll(sm, 1, wound_state="wounded", clear_at=time.time() - 100)
        ctx = MagicMock(session_mgr=sm, db=MagicMock())
        with patch("engine.death.tick_wound_recovery",
                   new=AsyncMock(return_value=True)) as m:
            _run(tick_handlers_death.wound_recovery_tick(ctx))
        # Proves the session was reached via sm.all and processed end-to-end.
        m.assert_awaited_once_with(ctx.db, 1)
        assert s.character["wound_state"] == "healthy"   # in-memory cache synced
        s.send_line.assert_awaited_once()                # "Your wounds finish knitting."

    def test_tick_skips_healthy_session(self):
        sm = SessionManager()
        _enroll(sm, 2, wound_state="healthy", clear_at=0.0)
        ctx = MagicMock(session_mgr=sm, db=MagicMock())
        with patch("engine.death.tick_wound_recovery",
                   new=AsyncMock(return_value=True)) as m:
            _run(tick_handlers_death.wound_recovery_tick(ctx))
        m.assert_not_awaited()   # healthy → skipped before any DB hit


class TestNoManagerDotSessions:
    def test_session_manager_exposes_all_not_sessions(self):
        sm = SessionManager()
        assert hasattr(sm, "all") and isinstance(sm.all, list)
        assert not hasattr(sm, "sessions"), (
            "use .all — `.sessions` does not exist on SessionManager and silently "
            "no-ops live iteration"
        )

    def test_no_runtime_module_iterates_mgr_dot_sessions(self):
        bad = []
        pat = re.compile(r"(session_mgr|session_manager|\bsm)\.sessions\b")
        for d in ("server", "engine", "parser"):
            for f in glob.glob(f"{d}/**/*.py", recursive=True):
                src = open(f, encoding="utf-8").read()
                for mt in pat.finditer(src):
                    bad.append(f"{f}: {mt.group(0)}")
        assert not bad, "use .all, not .sessions:\n" + "\n".join(bad)
