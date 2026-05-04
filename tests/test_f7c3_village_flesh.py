# -*- coding: utf-8 -*-
"""
tests/test_f7c3_village_flesh.py — F.7.c.3 — Trial of Flesh.

Closes Trial 3 (Flesh — Elder Korvas at the Meditation Caves)
end-to-end. Wall-clock dwell:

  - Trial starts when the player enters the Meditation Caves with
    Courage done. ``village_trial_flesh_started_at`` is anchored
    on first cave-entry.
  - Completion fires (1) the next time the player enters the cave
    after 6 hours have elapsed, (2) when they `talk Korvas` after
    the timer is up, or (3) when they `trial flesh` after the
    timer is up.
  - The trial cannot be failed and cannot be cancelled. Leaving
    the cave does not stop the wall-clock; logout does not stop it.
  - Reward: ``village_trial_flesh_strength_taught`` marker in
    chargen_notes (forward-additive — future learned-Force-power
    consumer reads it).

What this suite validates:

  1. Schema columns from v22 are present and writable
     (village_trial_flesh_done / _started_at / _session_seconds).
  2. Constants (FLESH_DURATION_SECONDS, MEDITATION_CAVES_ROOM_NAME).
  3. Accessors: is_flesh_trial_done / is_flesh_trial_started /
     is_flesh_unlocked / flesh_trial_elapsed_seconds /
     flesh_trial_remaining_seconds.
  4. Cave-entry hook (maybe_start_flesh_trial_on_cave_entry):
        - Wrong room → no-op
        - Locked (no audience / no skill / no courage) → no-op
        - Already done → no-op
        - First entry → anchors started_at, emits Korvas brief
        - Re-entry (in flight) → no-op
        - Re-entry (time up) → fires completion
  5. Completion (maybe_complete_flesh_trial):
        - Already done → no-op
        - Not started → no-op
        - Time remaining → no-op
        - Time up → flips done flag, sets strength_taught marker,
          emits the teaching narration
  6. Korvas hook (maybe_handle_korvas_flesh_trial):
        - Non-Korvas → False
        - No audience → deflect
        - Done → ack
        - Courage not done → deflect (with Skill-or-Courage branch)
        - Unlocked, not started → brief
        - Unlocked, in flight → progress report
        - Unlocked, time up → fires completion
  7. attempt_flesh_trial:
        - No audience → refuse
        - Done → ack
        - Courage not done → refuse
        - Not started → tells player to enter the caves
        - In flight → progress report
        - Time up → fires completion
  8. Insight gate now requires Flesh (regression check).
  9. Talk-dispatch wires Korvas into check_village_quest.
 10. Room-entered dispatch wires the cave-entry hook.
 11. TrialCommand parses 'trial flesh' correctly.
 12. Strength-taught marker reads correctly.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.village_trials import (
    DARO_NAME, MIRA_NAME, KORVAS_NAME, SARO_NAME,
    FORGE_ROOM_NAME, COUNCIL_HUT_ROOM_NAME, COMMON_SQUARE_ROOM_NAME,
    MEDITATION_CAVES_ROOM_NAME,
    FLESH_DURATION_SECONDS,
    has_completed_audience,
    is_skill_trial_done, is_courage_trial_done,
    is_flesh_trial_done, is_flesh_trial_started,
    is_flesh_unlocked,
    flesh_trial_elapsed_seconds, flesh_trial_remaining_seconds,
    has_been_taught_strength,
    maybe_start_flesh_trial_on_cave_entry,
    maybe_complete_flesh_trial,
    maybe_handle_korvas_flesh_trial,
    attempt_flesh_trial,
    is_insight_unlocked,
)
from engine.village_quest import (
    ACT_PRE_INVITATION, ACT_INVITED, ACT_IN_TRIALS,
    HERMIT_NAME, check_village_quest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_char(
    *, id_=1, audience_done=False,
    skill_done=False, courage_done=False,
    flesh_done=False, flesh_started_at=0,
    spirit_done=False,
    insight_done=False,
    strength_taught=False,
    room_id=1,
):
    """Build a minimal char dict for Flesh tests.

    The ``spirit_done`` kwarg was added when F.7.c.4 tightened the
    Insight gate to also require Spirit.
    """
    notes = {}
    if audience_done:
        notes["village_first_audience_done"] = True
    if strength_taught:
        notes["village_trial_flesh_strength_taught"] = True
    return {
        "id": id_,
        "name": f"P{id_}",
        "room_id": room_id,
        "village_act": ACT_IN_TRIALS if audience_done else ACT_INVITED,
        "village_gate_passed": 1 if audience_done else 0,
        "village_trial_skill_done": int(skill_done),
        "village_trial_skill_step": 3 if skill_done else 0,
        "village_trial_skill_attempts": 0,
        "village_trial_skill_last_at": 0,
        "village_trial_skill_crystal_granted": int(skill_done),
        "village_trial_courage_done": int(courage_done),
        "village_trial_courage_lockout_until": 0,
        "village_trial_flesh_done": int(flesh_done),
        "village_trial_flesh_started_at": flesh_started_at,
        "village_trial_flesh_session_seconds": 0,
        "village_trial_spirit_done": int(spirit_done),
        "village_trial_spirit_dark_pull": 0,
        "village_trial_spirit_rejections": 0,
        "village_trial_spirit_turn": 0,
        "village_trial_spirit_path_c_locked": 0,
        "village_trial_insight_done": int(insight_done),
        "village_trial_insight_attempts": 0,
        "village_trial_insight_correct_fragment": 0,
        "village_trial_insight_pendant_granted": 0,
        "chargen_notes": json.dumps(notes),
        "attributes": json.dumps({"dex": "4D", "tec": "4D"}),
        "skills": json.dumps({"craft_lightsaber": "5D"}),
    }


class FakeSession:
    def __init__(self, character):
        self.character = character
        self.received: list[str] = []

    async def send_line(self, text):
        self.received.append(text)


class FakeDB:
    """Minimal DB stub. save_character mutates the in-memory char dict."""
    def __init__(self, char):
        self._char = char
        self.saves: list[dict] = []
        self._room_name = MEDITATION_CAVES_ROOM_NAME

    def set_room(self, name):
        self._room_name = name

    async def save_character(self, char_id, **kwargs):
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v

    async def get_room(self, room_id):
        return {"name": self._room_name, "id": room_id}


# ═════════════════════════════════════════════════════════════════════════════
# 1. Schema columns + constants
# ═════════════════════════════════════════════════════════════════════════════


class TestFleshSchemaAndConstants:

    def test_flesh_columns_in_writable_set(self):
        from db.database import Database
        cols = Database._CHARACTER_WRITABLE_COLUMNS
        assert "village_trial_flesh_done" in cols
        assert "village_trial_flesh_started_at" in cols
        assert "village_trial_flesh_session_seconds" in cols

    def test_flesh_constants(self):
        # Six hours
        assert FLESH_DURATION_SECONDS == 6 * 60 * 60
        assert MEDITATION_CAVES_ROOM_NAME == "Meditation Caves"
        # Korvas name matches the YAML
        assert KORVAS_NAME == "Elder Korvas"


# ═════════════════════════════════════════════════════════════════════════════
# 2. Accessors
# ═════════════════════════════════════════════════════════════════════════════


class TestFleshAccessors:

    def test_done_default_false(self):
        char = _make_char()
        assert is_flesh_trial_done(char) is False

    def test_done_true_when_set(self):
        char = _make_char(flesh_done=True)
        assert is_flesh_trial_done(char) is True

    def test_started_default_false(self):
        char = _make_char()
        assert is_flesh_trial_started(char) is False

    def test_started_true_when_started_at_set(self):
        char = _make_char(flesh_started_at=time.time())
        assert is_flesh_trial_started(char) is True

    def test_started_false_when_started_at_zero(self):
        char = _make_char(flesh_started_at=0)
        assert is_flesh_trial_started(char) is False

    def test_unlocked_requires_audience(self):
        char = _make_char(audience_done=False, skill_done=True, courage_done=True)
        assert is_flesh_unlocked(char) is False

    def test_unlocked_requires_skill(self):
        char = _make_char(audience_done=True, skill_done=False, courage_done=True)
        assert is_flesh_unlocked(char) is False

    def test_unlocked_requires_courage(self):
        char = _make_char(audience_done=True, skill_done=True, courage_done=False)
        assert is_flesh_unlocked(char) is False

    def test_unlocked_when_all_three_done(self):
        char = _make_char(audience_done=True, skill_done=True, courage_done=True)
        assert is_flesh_unlocked(char) is True

    def test_elapsed_zero_when_not_started(self):
        char = _make_char()
        assert flesh_trial_elapsed_seconds(char) == 0.0

    def test_elapsed_positive_when_started(self):
        char = _make_char(flesh_started_at=time.time() - 1800)  # 30 min ago
        e = flesh_trial_elapsed_seconds(char)
        assert 1700 < e < 1900

    def test_remaining_zero_when_complete(self):
        char = _make_char(flesh_started_at=time.time() - FLESH_DURATION_SECONDS - 60)
        assert flesh_trial_remaining_seconds(char) == 0.0

    def test_remaining_positive_when_in_flight(self):
        char = _make_char(flesh_started_at=time.time() - 1800)  # 30 min ago
        r = flesh_trial_remaining_seconds(char)
        assert 0 < r < FLESH_DURATION_SECONDS

    def test_remaining_full_duration_when_just_started(self):
        char = _make_char(flesh_started_at=time.time() - 1)
        r = flesh_trial_remaining_seconds(char)
        assert r > FLESH_DURATION_SECONDS - 5


# ═════════════════════════════════════════════════════════════════════════════
# 3. Strength-taught marker
# ═════════════════════════════════════════════════════════════════════════════


class TestStrengthTaughtMarker:

    def test_default_false(self):
        char = _make_char()
        assert has_been_taught_strength(char) is False

    def test_true_when_marker_present(self):
        char = _make_char(strength_taught=True)
        assert has_been_taught_strength(char) is True

    def test_handles_malformed_chargen_notes(self):
        char = _make_char()
        char["chargen_notes"] = "not valid json {{{"
        # Should return False, not crash
        assert has_been_taught_strength(char) is False

    def test_handles_missing_chargen_notes(self):
        char = _make_char()
        char["chargen_notes"] = None
        assert has_been_taught_strength(char) is False


# ═════════════════════════════════════════════════════════════════════════════
# 4. Cave-entry hook
# ═════════════════════════════════════════════════════════════════════════════


class TestCaveEntryHook:

    def test_wrong_room_no_op(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_start_flesh_trial_on_cave_entry(
                session, db, char, "The Forge",
            )
            assert ok is False
            assert char["village_trial_flesh_started_at"] == 0
        asyncio.run(_check())

    def test_locked_no_audience_no_op(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_start_flesh_trial_on_cave_entry(
                session, db, char, MEDITATION_CAVES_ROOM_NAME,
            )
            assert ok is False
            assert char["village_trial_flesh_started_at"] == 0
        asyncio.run(_check())

    def test_locked_no_skill_no_op(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=False, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_start_flesh_trial_on_cave_entry(
                session, db, char, MEDITATION_CAVES_ROOM_NAME,
            )
            assert ok is False
            assert char["village_trial_flesh_started_at"] == 0
        asyncio.run(_check())

    def test_locked_no_courage_no_op(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_start_flesh_trial_on_cave_entry(
                session, db, char, MEDITATION_CAVES_ROOM_NAME,
            )
            assert ok is False
            assert char["village_trial_flesh_started_at"] == 0
        asyncio.run(_check())

    def test_already_done_no_op(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_start_flesh_trial_on_cave_entry(
                session, db, char, MEDITATION_CAVES_ROOM_NAME,
            )
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_first_entry_anchors_and_emits_brief(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            before = time.time()
            ok = await maybe_start_flesh_trial_on_cave_entry(
                session, db, char, MEDITATION_CAVES_ROOM_NAME,
            )
            after = time.time()
            assert ok is True
            anchored = char["village_trial_flesh_started_at"]
            assert before - 1 <= anchored <= after + 1
            # Save persisted the anchor
            assert any("village_trial_flesh_started_at" in s for s in db.saves)
            # Korvas's voice + the trial command name appear
            output = "\n".join(session.received)
            assert "Korvas" in output
            assert "trial flesh" in output.lower()
        asyncio.run(_check())

    def test_reentry_in_flight_no_op(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - 1800,  # 30 min ago
            )
            session = FakeSession(char)
            db = FakeDB(char)
            anchored_before = char["village_trial_flesh_started_at"]
            ok = await maybe_start_flesh_trial_on_cave_entry(
                session, db, char, MEDITATION_CAVES_ROOM_NAME,
            )
            # Returns False (was already started)
            assert ok is False
            # Anchor not bumped
            assert char["village_trial_flesh_started_at"] == anchored_before
            # No "begins" message — re-entry is silent
            assert session.received == []
        asyncio.run(_check())

    def test_reentry_after_timer_up_fires_completion(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - FLESH_DURATION_SECONDS - 60,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            await maybe_start_flesh_trial_on_cave_entry(
                session, db, char, MEDITATION_CAVES_ROOM_NAME,
            )
            # Trial done now
            assert char["village_trial_flesh_done"] == 1
            output = "\n".join(session.received)
            assert "PASSED" in output
            assert has_been_taught_strength(char) is True
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 5. Completion path
# ═════════════════════════════════════════════════════════════════════════════


class TestMaybeCompleteFleshTrial:

    def test_already_done_no_op(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_complete_flesh_trial(session, db, char)
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_not_started_no_op(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_complete_flesh_trial(session, db, char)
            assert ok is False
            assert char["village_trial_flesh_done"] == 0
        asyncio.run(_check())

    def test_time_remaining_no_op(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - 1800,  # 30 min ago
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_complete_flesh_trial(session, db, char)
            assert ok is False
            assert char["village_trial_flesh_done"] == 0
        asyncio.run(_check())

    def test_time_up_completes_and_grants_strength(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - FLESH_DURATION_SECONDS - 1,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_complete_flesh_trial(session, db, char)
            assert ok is True
            assert char["village_trial_flesh_done"] == 1
            # strength_taught marker set in chargen_notes
            assert has_been_taught_strength(char) is True
            # Save persisted both done flag and chargen_notes
            saves_combined = {}
            for s in db.saves:
                saves_combined.update(s)
            assert saves_combined.get("village_trial_flesh_done") == 1
            assert "chargen_notes" in saves_combined
            # Narration mentions the teaching
            output = "\n".join(session.received)
            assert "PASSED" in output
            assert "enhance" in output.lower() or "Strength" in output
        asyncio.run(_check())

    def test_completion_preserves_existing_chargen_notes(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - FLESH_DURATION_SECONDS - 1,
            )
            # Add an unrelated note that must survive
            existing = json.loads(char["chargen_notes"])
            existing["unrelated_marker"] = "preserve_me"
            char["chargen_notes"] = json.dumps(existing)

            session = FakeSession(char)
            db = FakeDB(char)
            await maybe_complete_flesh_trial(session, db, char)

            updated = json.loads(char["chargen_notes"])
            assert updated.get("unrelated_marker") == "preserve_me"
            assert updated.get("village_trial_flesh_strength_taught") is True
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 6. Korvas hook
# ═════════════════════════════════════════════════════════════════════════════


class TestKorvasHook:

    def test_non_korvas_returns_false(self):
        async def _check():
            char = _make_char()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(session, db, char, "Random")
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_no_audience_deflects(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(session, db, char, KORVAS_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "Master" in output or "welcomed" in output.lower()
        asyncio.run(_check())

    def test_done_acks(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(session, db, char, KORVAS_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "discipline" in output.lower() or "remembers" in output.lower()
        asyncio.run(_check())

    def test_no_skill_deflects_with_forge_branch(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=False, courage_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(session, db, char, KORVAS_NAME)
            assert ok is True
            output = "\n".join(session.received)
            # Forge branch
            assert "forge" in output.lower() or "Daro" in output
        asyncio.run(_check())

    def test_skill_done_no_courage_deflects_with_square_branch(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(session, db, char, KORVAS_NAME)
            assert ok is True
            output = "\n".join(session.received)
            # Square branch
            assert "Square" in output or "Mira" in output
        asyncio.run(_check())

    def test_unlocked_not_started_briefs(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(session, db, char, KORVAS_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "six hours" in output.lower() or "discipline" in output.lower()
            # Briefing tells them to enter the caves
            assert "cave" in output.lower() or "threshold" in output.lower()
            # Briefing alone does NOT start the trial — that's cave-entry
            assert char["village_trial_flesh_started_at"] == 0
        asyncio.run(_check())

    def test_unlocked_in_flight_reports_progress(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - 1800,  # 30 min in
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(session, db, char, KORVAS_NAME)
            assert ok is True
            output = "\n".join(session.received)
            # Mentions remaining time
            assert "remain" in output.lower() or "hour" in output.lower()
            # Trial not complete
            assert char["village_trial_flesh_done"] == 0
        asyncio.run(_check())

    def test_unlocked_time_up_fires_completion(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - FLESH_DURATION_SECONDS - 1,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(session, db, char, KORVAS_NAME)
            assert ok is True
            assert char["village_trial_flesh_done"] == 1
            assert has_been_taught_strength(char) is True
            output = "\n".join(session.received)
            assert "PASSED" in output
        asyncio.run(_check())

    def test_case_insensitive_npc_name(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_korvas_flesh_trial(
                session, db, char, KORVAS_NAME.upper(),
            )
            assert ok is True
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 7. attempt_flesh_trial (`trial flesh`)
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptFleshTrial:

    def test_no_audience_refuses(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_flesh_trial(session, db, char)
            assert ok is False
        asyncio.run(_check())

    def test_already_done_acks(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_flesh_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "already" in output.lower() or "remembers" in output.lower()
        asyncio.run(_check())

    def test_no_skill_refuses_with_forge_message(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=False, courage_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_flesh_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Daro" in output or "Forge" in output
        asyncio.run(_check())

    def test_skill_done_no_courage_refuses_with_mira_message(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_flesh_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Mira" in output or "Square" in output
        asyncio.run(_check())

    def test_not_started_tells_player_to_enter_caves(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_flesh_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Meditation Caves" in output or "Korvas" in output
            assert char["village_trial_flesh_started_at"] == 0
        asyncio.run(_check())

    def test_in_flight_reports_progress(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - 1800,  # 30 min in
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_flesh_trial(session, db, char)
            assert ok is True
            output = "\n".join(session.received)
            assert "Elapsed" in output or "elapsed" in output.lower()
            assert "Remaining" in output or "remaining" in output.lower()
            assert "%" in output  # percentage indicator
            # Trial not complete
            assert char["village_trial_flesh_done"] == 0
        asyncio.run(_check())

    def test_time_up_fires_completion(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - FLESH_DURATION_SECONDS - 1,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_flesh_trial(session, db, char)
            assert ok is True
            assert char["village_trial_flesh_done"] == 1
            assert has_been_taught_strength(char) is True
            output = "\n".join(session.received)
            assert "PASSED" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 8. Insight gate now requires Flesh
# ═════════════════════════════════════════════════════════════════════════════


class TestInsightGateRequiresFlesh:
    """F.7.c.3 tightens is_insight_unlocked to require Flesh."""

    def test_audience_skill_courage_only_locked(self):
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
            flesh_done=False,
        )
        assert is_insight_unlocked(char) is False

    def test_audience_skill_courage_flesh_no_spirit_locked_under_f7c4(self):
        # Under F.7.c.4 the gate also requires Spirit. Flesh alone is
        # no longer enough.
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
            flesh_done=True, spirit_done=False,
        )
        assert is_insight_unlocked(char) is False

    def test_all_five_gates_unlock(self):
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
            flesh_done=True, spirit_done=True,
        )
        assert is_insight_unlocked(char) is True


# ═════════════════════════════════════════════════════════════════════════════
# 9. _handle_talk dispatch
# ═════════════════════════════════════════════════════════════════════════════


class TestHandleTalkDispatchKorvas:

    def test_korvas_dispatched_through_check_village_quest(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            await check_village_quest(
                session, db, "talk", npc_name=KORVAS_NAME,
            )
            output = "\n".join(session.received)
            # Briefing language from Korvas hook (not-started)
            assert "six hours" in output.lower() or "discipline" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 10. _handle_room_entered dispatch (cave-entry hook)
# ═════════════════════════════════════════════════════════════════════════════


class TestHandleRoomEnteredCaveDispatch:
    """Verify check_village_quest('room_entered') routes to the
    cave-entry hook when the room is the Meditation Caves.
    """

    def test_cave_entry_dispatch_anchors_trial(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                room_id=42,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(MEDITATION_CAVES_ROOM_NAME)
            # Call the public hook with room_id; the handler will
            # look up room name via db.get_room.
            await check_village_quest(
                session, db, "room_entered",
                room_id=42, room_slug="village_meditation_caves",
            )
            assert char["village_trial_flesh_started_at"] > 0
            output = "\n".join(session.received)
            assert "Korvas" in output
        asyncio.run(_check())

    def test_other_room_no_op_for_flesh(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                room_id=42,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            await check_village_quest(
                session, db, "room_entered",
                room_id=42, room_slug="village_forge",
            )
            assert char["village_trial_flesh_started_at"] == 0
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 11. TrialCommand wiring
# ═════════════════════════════════════════════════════════════════════════════


class TestTrialCommandFleshWiring:

    def test_trial_flesh_branch_in_source(self):
        path = os.path.join(PROJECT_ROOT, "parser", "village_trial_commands.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "if which == \"flesh\":" in src
        assert "attempt_flesh_trial" in src

    def test_trial_command_help_mentions_flesh(self):
        from parser.village_trial_commands import TrialCommand
        cmd = TrialCommand()
        assert "flesh" in cmd.help_text.lower()
        assert "flesh" in cmd.usage.lower()

    def test_trial_command_dispatch_flesh_not_started(self):
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char(audience_done=True, skill_done=True, courage_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ctx = CommandContext(
                session=session,
                raw_input="trial flesh",
                command="trial",
                args="flesh",
                args_list=["flesh"],
                db=db,
            )
            await TrialCommand().execute(ctx)
            output = "\n".join(session.received)
            # "trial flesh" with no started trial → tells player to enter caves
            assert "Meditation Caves" in output or "Korvas" in output
        asyncio.run(_check())

    def test_trial_command_dispatch_flesh_in_flight(self):
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - 1800,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ctx = CommandContext(
                session=session,
                raw_input="trial flesh",
                command="trial",
                args="flesh",
                args_list=["flesh"],
                db=db,
            )
            await TrialCommand().execute(ctx)
            output = "\n".join(session.received)
            assert "Elapsed" in output or "elapsed" in output.lower()
        asyncio.run(_check())

    def test_trial_command_dispatch_flesh_completes(self):
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_started_at=time.time() - FLESH_DURATION_SECONDS - 1,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ctx = CommandContext(
                session=session,
                raw_input="trial flesh",
                command="trial",
                args="flesh",
                args_list=["flesh"],
                db=db,
            )
            await TrialCommand().execute(ctx)
            assert char["village_trial_flesh_done"] == 1
        asyncio.run(_check())

    def test_trial_command_unknown_trial_lists_flesh(self):
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char()
            session = FakeSession(char)
            db = FakeDB(char)
            ctx = CommandContext(
                session=session,
                raw_input="trial banana",
                command="trial",
                args="banana",
                args_list=["banana"],
                db=db,
            )
            await TrialCommand().execute(ctx)
            output = "\n".join(session.received)
            assert "flesh" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 12. Module wiring
# ═════════════════════════════════════════════════════════════════════════════


class TestModuleWiring:

    def test_village_quest_imports_korvas_hook(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_quest.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "maybe_handle_korvas_flesh_trial" in src

    def test_village_quest_imports_cave_entry_hook(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_quest.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "maybe_start_flesh_trial_on_cave_entry" in src

    def test_village_trials_exposes_flesh_surface(self):
        from engine import village_trials
        assert hasattr(village_trials, "maybe_handle_korvas_flesh_trial")
        assert hasattr(village_trials, "attempt_flesh_trial")
        assert hasattr(village_trials, "maybe_start_flesh_trial_on_cave_entry")
        assert hasattr(village_trials, "maybe_complete_flesh_trial")
        assert hasattr(village_trials, "is_flesh_trial_done")
        assert hasattr(village_trials, "is_flesh_trial_started")
        assert hasattr(village_trials, "is_flesh_unlocked")
        assert hasattr(village_trials, "flesh_trial_elapsed_seconds")
        assert hasattr(village_trials, "flesh_trial_remaining_seconds")
        assert hasattr(village_trials, "has_been_taught_strength")

    def test_meditation_caves_constant_exposed(self):
        assert MEDITATION_CAVES_ROOM_NAME == "Meditation Caves"
