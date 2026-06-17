# -*- coding: utf-8 -*-
"""tests/test_qa_l1_insight_saro_required.py — QA L1: Insight trial requires Saro dialogue.

Bug: accuse_insight_fragment fell back to correct=2 when
village_trial_insight_correct_fragment was 0 (Saro never consulted),
letting any player trivially bypass the Insight trial.
Fix: block with "speak with Elder Saro Veck" when correct_fragment == 0.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.village_trials import (
    COUNCIL_HUT_ROOM_NAME,
    accuse_insight_fragment,
)
from engine.village_quest import ACT_IN_TRIALS


# ── Minimal fakes ─────────────────────────────────────────────────────────────

class FakeSession:
    def __init__(self, char):
        self.character = char
        self.received: list[str] = []

    async def send_line(self, text: str) -> None:
        self.received.append(text)


class FakeDB:
    def __init__(self, char: dict):
        self._room_name = COUNCIL_HUT_ROOM_NAME
        self.inventory_adds: list[dict] = []
        self._char = char

    def set_room(self, name: str) -> None:
        self._room_name = name

    async def get_room(self, room_id):
        return {"name": self._room_name}

    async def add_to_inventory(self, char_id, item: dict):
        self.inventory_adds.append(item)

    async def save_character(self, char_id, **kwargs):
        self._char.update(kwargs)

    async def record_admin_action(self, *a, **kw):
        pass


def _make_unlocked_char(insight_correct: int = 0) -> dict:
    """All four prereqs done, Insight unlocked, trial not yet passed."""
    return {
        "id": 1,
        "name": "Tester",
        "room_id": 1,
        "village_act": ACT_IN_TRIALS,
        "village_gate_passed": 1,
        "chargen_notes": json.dumps({"village_first_audience_done": True}),
        "village_trial_skill_done": 1,
        "village_trial_skill_step": 3,
        "village_trial_skill_attempts": 0,
        "village_trial_skill_last_at": 0,
        "village_trial_skill_crystal_granted": 1,
        "village_trial_courage_done": 1,
        "village_trial_courage_lockout_until": 0,
        "village_trial_flesh_done": 1,
        "village_trial_flesh_started_at": 0,
        "village_trial_flesh_session_seconds": 0,
        "village_trial_spirit_done": 1,
        "village_trial_spirit_dark_pull": 0,
        "village_trial_spirit_rejections": 0,
        "village_trial_spirit_turn": 0,
        "village_trial_spirit_path_c_locked": 0,
        "village_trial_insight_done": 0,
        "village_trial_insight_attempts": 0,
        "village_trial_insight_correct_fragment": insight_correct,
        "village_trial_insight_pendant_granted": 0,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestInsightRequiresSaro:
    def test_accuse_without_saro_blocked(self):
        """accuse_insight_fragment must be blocked when Saro not yet consulted."""
        async def _check():
            char = _make_unlocked_char(insight_correct=0)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await accuse_insight_fragment(session, db, char, "fragment_2")
            assert ok is True
            assert char["village_trial_insight_done"] == 0
            output = "\n".join(session.received)
            assert "Saro" in output
        asyncio.run(_check())

    def test_correct_fragment_without_saro_does_not_pass(self):
        """Even if the player guesses fragment_2 (the correct answer), without
        Saro the trial must not complete."""
        async def _check():
            char = _make_unlocked_char(insight_correct=0)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await accuse_insight_fragment(session, db, char, "fragment_2")
            assert ok is True
            assert char["village_trial_insight_done"] == 0
            assert len(db.inventory_adds) == 0  # pendant NOT granted
        asyncio.run(_check())

    def test_all_fragments_blocked_without_saro(self):
        """All three fragment choices are blocked before Saro is consulted."""
        async def _check():
            for frag in ("fragment_1", "fragment_2", "fragment_3"):
                char = _make_unlocked_char(insight_correct=0)
                session = FakeSession(char)
                db = FakeDB(char)
                ok = await accuse_insight_fragment(session, db, char, frag)
                assert ok is True, f"{frag} should be blocked"
                assert char["village_trial_insight_done"] == 0
        asyncio.run(_check())

    def test_accuse_after_saro_correct_passes(self):
        """After Saro sets the fragment, a correct accusation passes normally."""
        async def _check():
            char = _make_unlocked_char(insight_correct=2)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await accuse_insight_fragment(session, db, char, "fragment_2")
            assert ok is True
            assert char["village_trial_insight_done"] == 1
            assert len(db.inventory_adds) == 1
            assert db.inventory_adds[0]["key"] == "village_pendant"
        asyncio.run(_check())

    def test_accuse_after_saro_wrong_still_fails(self):
        """After Saro, a wrong accusation still fails (no accidental pass)."""
        async def _check():
            char = _make_unlocked_char(insight_correct=2)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await accuse_insight_fragment(session, db, char, "fragment_1")
            assert ok is True
            assert char["village_trial_insight_done"] == 0
            assert len(db.inventory_adds) == 0
        asyncio.run(_check())

    def test_attempts_not_counted_when_saro_not_consulted(self):
        """Blocked accuse must not increment the attempt counter."""
        async def _check():
            char = _make_unlocked_char(insight_correct=0)
            session = FakeSession(char)
            db = FakeDB(char)
            await accuse_insight_fragment(session, db, char, "fragment_2")
            assert char["village_trial_insight_done"] == 0
            assert char["village_trial_insight_attempts"] == 0  # no wasted count
        asyncio.run(_check())

    def test_fallback_to_2_removed(self):
        """Drift guard: the old 'correct = 2' fallback must not exist in the source."""
        import inspect
        src = inspect.getsource(accuse_insight_fragment)
        assert "correct = 2" not in src, (
            "Old fallback 'correct = 2' still present in accuse_insight_fragment — "
            "QA L1 fix may have been reverted"
        )
