"""Regression: the telnet read loop must be a *tracked* background task.

asyncio holds only a weak reference to tasks created via ``create_task`` —
"a task that isn't referenced elsewhere may get garbage-collected at any
time, even before it's done" (asyncio docs). The telnet read loop in
``GameServer.handle_new_session`` was previously fire-and-forget
(``asyncio.create_task(self._telnet_read_loop(...))`` with the handle
discarded), so the loop feeding a player's telnet input could be collected
mid-flight and silently kill the connection.

These tests pin the fix: ``_spawn_read_loop`` registers the task in
``self._read_tasks`` (strong reference for the task's lifetime) and a
done-callback discards it on completion so the set never grows unbounded.

The tests borrow the real ``_spawn_read_loop`` / ``_telnet_read_loop``
methods onto a lightweight stub so we exercise the actual code path without
paying the full GameServer/world boot.
"""

import asyncio

import pytest

from server.game_server import GameServer
from server.session import SessionState


class _StubSession:
    """Minimal stand-in for Session: just what the read loop touches."""

    def __init__(self):
        self.state = SessionState.CONNECTED
        self.fed: list[str] = []

    def feed_input(self, line):
        self.fed.append(line)


class _StubServer:
    """Borrows the real registration + read-loop methods, no heavy __init__."""

    _spawn_read_loop = GameServer._spawn_read_loop
    _telnet_read_loop = GameServer._telnet_read_loop

    def __init__(self):
        self._read_tasks: set[asyncio.Task] = set()


class _EOFReader:
    """A reader that immediately reports EOF (connection closed)."""

    async def readline(self):
        return b""


class _GatedReader:
    """Blocks on the first readline until released, then reports EOF."""

    def __init__(self, gate: asyncio.Event):
        self._gate = gate

    async def readline(self):
        await self._gate.wait()
        return b""


@pytest.mark.asyncio
async def test_spawn_read_loop_holds_strong_ref_then_discards():
    srv = _StubServer()
    sess = _StubSession()

    task = srv._spawn_read_loop(_EOFReader(), sess)

    # Strong reference held immediately — the whole point of the fix.
    assert task in srv._read_tasks

    await task
    # Done-callbacks are scheduled via call_soon; let them run.
    await asyncio.sleep(0)

    # No leak: the finished task is dropped from the tracking set.
    assert task not in srv._read_tasks
    assert srv._read_tasks == set()
    # EOF on the read loop signals quit so the session can tear down.
    assert "quit" in sess.fed


@pytest.mark.asyncio
async def test_read_task_stays_referenced_while_running():
    srv = _StubServer()
    sess = _StubSession()
    gate = asyncio.Event()

    task = srv._spawn_read_loop(_GatedReader(gate), sess)
    # Yield so the task actually starts and parks on the gate.
    await asyncio.sleep(0)

    assert not task.done()
    assert task in srv._read_tasks  # still strongly referenced mid-flight

    gate.set()
    await task
    await asyncio.sleep(0)
    assert task not in srv._read_tasks


@pytest.mark.asyncio
async def test_disconnecting_state_suppresses_quit_feed():
    """The finally only injects 'quit' when not already disconnecting."""
    srv = _StubServer()
    sess = _StubSession()
    sess.state = SessionState.DISCONNECTING

    await srv._spawn_read_loop(_EOFReader(), sess)
    await asyncio.sleep(0)

    assert "quit" not in sess.fed
