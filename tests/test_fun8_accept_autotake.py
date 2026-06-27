# -*- coding: utf-8 -*-
"""
tests/test_fun8_accept_autotake.py — FUN8 tutorial assignment auto-take.

6th fun re-run #1 kills-it: the Republic-Soldier tutorial soft-locked at STEP
3/5 "Receiving the Assignment". The TRAINING panel said type `accept`, but the
mission board shows opaque hash ids (m-xxxx) and the chain matches on the
abstract `chain_mission_id`, so bare `accept` dead-ended on
"Usage: accept <mission-id>" and the newcomer was stuck one step after the
combat payoff.

Fix: (1) the mission_accepted steps' TRAINING chip points at `accept`; (2) a
bare `accept` while on a `mission_accepted` step auto-resolves the chain's
offered mission and takes it (parser/mission_commands.py::_tutorial_auto_accept_id).
"""
from __future__ import annotations

import asyncio
import os
import sys
import types

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CHAINS_YAML = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "tutorials", "chains.yaml")


def _chains():
    with open(CHAINS_YAML, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc if isinstance(doc, list) else (
        doc.get("chains") or doc.get("tutorial_chains") or [])


def test_mission_accepted_steps_chip_at_accept():
    """Every step that completes on `mission_accepted` must stage `accept` as
    its TYPE chip (so the panel's one-click command actually takes the job),
    not `+missions` (which only opens the board and dead-ends the newcomer)."""
    found = 0
    for ch in _chains():
        if not isinstance(ch, dict):
            continue
        for step in ch.get("steps", []) or []:
            comp = (step.get("completion") or {})
            if comp.get("type") == "mission_accepted":
                found += 1
                cmd = (step.get("command_to_type") or "").strip()
                assert cmd == "accept", (
                    f"chain {ch.get('chain_id')} step {step.get('title')!r} "
                    f"mission_accepted chip is {cmd!r}, expected 'accept'")
    assert found >= 1, "no mission_accepted steps found (corpus drift?)"


def test_auto_accept_returns_none_without_active_tutorial():
    """Fail-safe: a player with no active tutorial chain gets None (the normal
    `Usage: accept <mission-id>` hint), never a crash."""
    from parser.mission_commands import _tutorial_auto_accept_id
    ctx = types.SimpleNamespace(db=None)
    char = {"id": 1, "name": "Nobody", "attributes": "{}"}
    result = asyncio.run(_tutorial_auto_accept_id(ctx, char))
    assert result is None


def test_auto_accept_helper_is_wired_into_bare_accept():
    """The bare-accept branch calls the auto-take resolver (guards against a
    refactor silently dropping the fix)."""
    import inspect
    from parser import mission_commands
    src = inspect.getsource(mission_commands.AcceptMissionCommand.execute)
    assert "_tutorial_auto_accept_id" in src, (
        "bare `accept` no longer routes through the tutorial auto-take resolver")
