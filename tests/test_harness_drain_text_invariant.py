# -*- coding: utf-8 -*-
"""
tests/test_harness_drain_text_invariant.py — Regression guard for the
``_drain_text`` quiet-window flake fixed May 18 [3] 2026.

Background
==========

The CX4 smoke scenario
(``test_smoke_combat_extended.py::test_cx4_combat_status_renders_in_active_combat``)
intermittently failed in the cumulative full-smoke sweep with
``+combat`` producing no output. The failure was flaky — sometimes
the test passed, sometimes the same code under the same pytest
invocation failed. Bisecting "minimal failing file combinations"
never produced a reliable repro, which was the tell that the bug
was a timing race, not a state-pollution issue.

Root cause
==========

The original ``_drain_text`` loop:

    last_len = -1
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        await asyncio.sleep(quiet_window / 2)
        cur_len = sum(len(t) for t in s._text_buf)
        if cur_len != last_len:
            last_len = cur_len
            last_change = time.monotonic()
            continue
        if time.monotonic() - last_change >= quiet_window:
            break

declared "quiet" as soon as the buffer hadn't changed for
``quiet_window`` seconds — including the case where the buffer
never received any text at all. Trace with ``quiet_window=0.1``:

  T0       : last_len=-1, last_change=T0
  T0+50ms  : cur_len=0; 0 != -1, last_len=0, last_change=T0+50ms, continue
  T0+100ms : cur_len=0; 0 == 0; T0+100ms - T0+50ms = 50ms < 100ms, continue
  T0+150ms : cur_len=0; 0 == 0; T0+150ms - T0+50ms = 100ms == 100ms, BREAK

If the server takes >150ms to start writing output (CX4's
``+combat`` queues behind post-attack NPC auto-declare +
initiative + broadcast), the drain returns "" before the server
ever writes anything.

The fix
=======

Track ``ever_nonempty`` and refuse to break on quiet-window until
the buffer has actually received content at some point. If the
buffer stays empty, the loop waits the full ``timeout`` (2.0s
default) — the timeout becomes the safety net rather than the
eager quiet-fire.

What this file guards
=====================

1. ``_drain_text`` must not return an empty string when the
   buffer was empty at the start of the call AND text arrives
   later within ``timeout``.
2. ``_drain_text`` must continue to return promptly (within
   ~150-300ms) when the buffer has text and goes quiet for
   ``quiet_window``.
3. ``_drain_text`` must still respect ``timeout`` even when the
   buffer never receives text.

These three invariants together preserve the original "drain when
quiet" contract while closing the empty-buffer race.
"""
from __future__ import annotations

import asyncio
import time
import types

import pytest


class _FakeSession:
    """Minimal _ClientSession-shaped stand-in for unit testing
    ``_drain_text`` without booting the full harness.

    Mirrors the two attributes the drain loop reads:
      * ``_text_buf`` — list of strings (the harness's text buffer)
      * ``drain_text()`` — returns concatenated text and clears
    """

    def __init__(self):
        self._text_buf: list[str] = []

    def drain_text(self) -> str:
        out = "".join(self._text_buf)
        self._text_buf.clear()
        return out


def _make_harness_with_drain():
    """Build a minimal harness-shaped object exposing only the
    ``_drain_text`` method under test. Avoids importing the full
    harness fixture (which boots a real GameServer)."""
    # Import the actual _drain_text from tests.harness — that's
    # the code under test. We bind it to a bare object so we don't
    # need a fully-instantiated _LiveHarness.
    from tests.harness import _LiveHarness
    h = types.SimpleNamespace()
    h._drain_text = _LiveHarness._drain_text.__get__(h)
    return h


class TestDrainTextQuietWindow:
    """The harness's _drain_text must not fire its quiet-window
    break on an empty buffer that hasn't yet received any output.
    """

    async def test_drain_waits_for_late_arriving_text(self):
        """If text arrives ~250ms after the call (past the original
        150ms eager-fire window), _drain_text must still capture it.

        With the original buggy loop, this returns "" at ~150ms.
        With the fix, the loop keeps waiting until text arrives
        or until timeout (2.0s).
        """
        h = _make_harness_with_drain()
        s = _FakeSession()

        # Schedule "late" text writes that arrive AFTER the
        # original quiet-window fire-time (~150ms) but well before
        # the deadline (2.0s).
        async def _late_writer():
            await asyncio.sleep(0.25)  # 250ms — past the eager-fire
            s._text_buf.append("the server output")

        writer = asyncio.create_task(_late_writer())
        out = await h._drain_text(s, timeout=2.0, quiet_window=0.1)
        await writer

        assert out == "the server output", (
            f"drain returned {out!r}; late-arriving text was lost. "
            f"The empty-buffer eager-fire race is back."
        )

    async def test_drain_returns_promptly_when_text_present_and_quiet(self):
        """Standard case: text present, no further writes within
        quiet_window, drain returns. Should complete in ~150ms,
        well under any reasonable timeout.
        """
        h = _make_harness_with_drain()
        s = _FakeSession()
        s._text_buf.append("immediate output")

        t0 = time.monotonic()
        out = await h._drain_text(s, timeout=2.0, quiet_window=0.1)
        elapsed = time.monotonic() - t0

        assert out == "immediate output"
        assert elapsed < 0.5, (
            f"drain took {elapsed:.3f}s for a buffer that was "
            f"non-empty from the start; quiet-window fire should "
            f"have triggered well before 0.5s."
        )

    async def test_drain_respects_timeout_when_buffer_stays_empty(self):
        """If the buffer never receives anything, the drain still
        returns when ``timeout`` elapses — it doesn't hang. Returns
        empty string. This is the documented safety-net behavior.
        """
        h = _make_harness_with_drain()
        s = _FakeSession()

        t0 = time.monotonic()
        out = await h._drain_text(s, timeout=0.5, quiet_window=0.1)
        elapsed = time.monotonic() - t0

        assert out == "", (
            f"drain returned non-empty {out!r} from a buffer that "
            f"never received text."
        )
        # Should approach timeout (0.5s) but not far exceed it.
        assert 0.4 <= elapsed <= 0.8, (
            f"drain took {elapsed:.3f}s; should have respected "
            f"timeout=0.5s and returned shortly after."
        )

    async def test_drain_captures_multi_burst_text(self):
        """Multiple bursts arriving over time — drain captures all
        bursts that arrive within ``quiet_window`` of each other,
        and returns when the stream goes quiet after the last burst.
        Bursts spaced wider than ``quiet_window`` are correctly split
        across separate drain calls (that's the documented contract).

        This is the canonical multi-burst pattern (NPC auto-declare
        immediately followed by initiative roll immediately followed
        by broadcast — all within ~100ms of each other under normal
        load).
        """
        h = _make_harness_with_drain()
        s = _FakeSession()

        async def _multi_burst():
            # All bursts within quiet_window (0.1s) of each other,
            # mimicking a single command's rapid-fire output.
            await asyncio.sleep(0.2)
            s._text_buf.append("burst 1; ")
            await asyncio.sleep(0.05)
            s._text_buf.append("burst 2; ")
            await asyncio.sleep(0.05)
            s._text_buf.append("burst 3")

        writer = asyncio.create_task(_multi_burst())
        out = await h._drain_text(s, timeout=2.0, quiet_window=0.1)
        await writer

        assert out == "burst 1; burst 2; burst 3", (
            f"multi-burst drain returned {out!r}; one or more "
            f"bursts within the quiet_window were dropped — "
            f"the change-detection didn't reset last_change "
            f"correctly between bursts."
        )
