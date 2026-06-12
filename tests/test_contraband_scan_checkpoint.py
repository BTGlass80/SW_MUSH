"""tests/test_contraband_scan_checkpoint.py — wiring the dormant SECURITY_CHECKPOINT
`contraband_scan` world-event effect into smuggling patrol resolution
(the "wire the holidays" bonus / T2.E3).

`contraband_scan` mirrors the existing `lockdown_active` boost but lighter, and the
two STACK. These tests pin the pure `resolve_patrol_encounter` behaviour
deterministically (random is monkeypatched for the patrol-chance test).
"""
from __future__ import annotations

import types

import engine.smuggling as S
from engine.smuggling import (
    resolve_patrol_encounter, PATROL_DIFFICULTY,
    CHECKPOINT_PATROL_BOOST, CHECKPOINT_DIFFICULTY_BOOST,
)


def _job(patrol_chance=1.0, tier=2):
    # resolve_patrol_encounter only reads patrol_chance / tier / cargo_type / fine
    return types.SimpleNamespace(
        patrol_chance=patrol_chance, tier=tier,
        cargo_type="ryll spice", fine=5000,
    )


def test_checkpoint_off_by_default():
    # patrol_chance=1.0 -> always intercepts, so we can read the difficulty
    out = resolve_patrol_encounter(_job(), skill_roll=0)
    assert out["intercepted"] is True
    assert out["difficulty"] == PATROL_DIFFICULTY[2]   # no boost when both flags off


def test_checkpoint_raises_difficulty():
    base = PATROL_DIFFICULTY[2]
    out = resolve_patrol_encounter(_job(), skill_roll=0, contraband_scan=True)
    assert out["difficulty"] == base + CHECKPOINT_DIFFICULTY_BOOST


def test_checkpoint_stacks_with_lockdown():
    base = PATROL_DIFFICULTY[2]
    out = resolve_patrol_encounter(
        _job(), skill_roll=0, lockdown_active=True, contraband_scan=True)
    # lockdown +5 AND checkpoint +CHECKPOINT_DIFFICULTY_BOOST
    assert out["difficulty"] == base + 5 + CHECKPOINT_DIFFICULTY_BOOST


def test_checkpoint_raises_patrol_chance(monkeypatch):
    # roll sits between the base chance and the boosted chance: a checkpoint should
    # flip a would-be clean pass into an interception.
    monkeypatch.setattr(S.random, "random", lambda: 0.60)
    job = _job(patrol_chance=0.50)   # 0.60 > 0.50 -> normally NOT intercepted

    clean = resolve_patrol_encounter(job, skill_roll=999)
    assert clean["intercepted"] is False

    # +CHECKPOINT_PATROL_BOOST (0.15) -> 0.65; 0.60 <= 0.65 -> intercepted
    assert CHECKPOINT_PATROL_BOOST >= 0.10
    scanned = resolve_patrol_encounter(job, skill_roll=999, contraband_scan=True)
    assert scanned["intercepted"] is True


def test_checkpoint_message_notes_scan():
    out = resolve_patrol_encounter(_job(), skill_roll=0, contraband_scan=True)
    assert "checkpoint" in out["message"].lower()
    # and the note is absent when the flag is off
    off = resolve_patrol_encounter(_job(), skill_roll=0)
    assert "checkpoint" not in off["message"].lower()


def test_caught_still_decided_by_roll_vs_boosted_difficulty():
    base = PATROL_DIFFICULTY[2]
    # roll exactly clears the base but NOT the checkpoint-boosted difficulty
    out = resolve_patrol_encounter(_job(), skill_roll=base, contraband_scan=True)
    assert out["intercepted"] is True
    assert out["caught"] is True          # base < base + boost -> caught
    # the same roll clears it with no checkpoint
    ok = resolve_patrol_encounter(_job(), skill_roll=base)
    assert ok["caught"] is False
