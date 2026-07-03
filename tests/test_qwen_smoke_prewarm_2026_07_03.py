# -*- coding: utf-8 -*-
"""Smoke cold-load re-flake fix (Fable §3 last bullet, 2026-07-03).

`tests/smoke/scenarios/chain_walkthrough.py::_drive_talk_to_npc` already polls
out to `NPC_DIALOGUE_TIMEOUT_S + 8.0s` (drop smuggler-chain-step3-fix), which
bounds a *single* cold-model talk call. But
`tests/smoke/test_smoke_chain_walkthrough.py::TestChainWalkthrough` shares one
class-scoped harness across all 7 chains — the FIRST talk_to_npc step in that
class is the one that can hit a genuinely cold 9B load. The
`_prewarm_ollama_for_talk_steps` autouse class-scoped fixture removes that race
outright by reusing the already-shipped `AIManager.warmup()` seam
(ai/providers.py) before any chain walks.

These tests exercise the prewarm helper directly against a stub harness,
without booting a real GameServer:
  - it calls `harness.server.ai_manager.warmup()` exactly once
  - it never raises even if `warmup()` raises (must not fail the test class)
  - the wrapping fixture is wired as `scope="class", autouse=True` so it
    fires once per harness, before the first parametrized chain walks
"""
import inspect

import pytest

from tests.smoke.test_smoke_chain_walkthrough import (
    _prewarm_ollama,
    _prewarm_ollama_for_talk_steps,
)


class _FakeAIManager:
    def __init__(self, raise_on_warmup: bool = False):
        self.warmup_calls = 0
        self._raise = raise_on_warmup

    async def warmup(self):
        self.warmup_calls += 1
        if self._raise:
            raise RuntimeError("Ollama unreachable (simulated)")


class _FakeServer:
    def __init__(self, ai_manager):
        self.ai_manager = ai_manager


class _FakeHarness:
    def __init__(self, ai_manager):
        self.server = _FakeServer(ai_manager)


@pytest.mark.asyncio
async def test_prewarm_calls_ai_manager_warmup_once():
    ai = _FakeAIManager()
    harness = _FakeHarness(ai)
    await _prewarm_ollama(harness)
    assert ai.warmup_calls == 1


@pytest.mark.asyncio
async def test_prewarm_never_raises_when_ollama_unreachable():
    # warmup() itself is documented never to raise, but the helper wraps it
    # in a belt-and-braces try/except anyway — a class-scoped autouse
    # fixture raising would fail every parametrized case in the class, which
    # is strictly worse than the cold-load race it exists to prevent.
    ai = _FakeAIManager(raise_on_warmup=True)
    harness = _FakeHarness(ai)
    await _prewarm_ollama(harness)  # must not raise
    assert ai.warmup_calls == 1


def test_fixture_is_class_scoped_and_autouse():
    # Wiring pin: if this regresses to function-scope or loses autouse, the
    # cold-load race comes back (warmup would fire zero or 7x instead of
    # once-per-harness-before-the-first-talk-step).
    marker = getattr(_prewarm_ollama_for_talk_steps, "_fixture_function_marker", None)
    assert marker is not None, "not a pytest fixture"
    assert marker.scope == "class"
    assert marker.autouse is True


def test_fixture_depends_on_the_harness_fixture():
    # It must resolve AFTER `harness` boots so ai_manager exists to warm.
    sig = inspect.signature(_prewarm_ollama_for_talk_steps.__wrapped__)
    assert "harness" in sig.parameters
