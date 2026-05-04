# -*- coding: utf-8 -*-
"""
tests/test_f7c4_village_spirit.py — F.7.c.4 — Trial of Spirit.

Closes Trial 4 (Spirit — Master Yarael in the Sealed Sanctum)
end-to-end. Multi-turn (5–7) dialogue with the dark-future-self.

Outcomes:
  - PASS   : ≥4 rejections at any turn count up to 7
  - PATH C : ≥3 temptations triggers an irreversible Path C lock
             (trial completes as "passed" so Insight gate doesn't block;
              Path C is a path, not a quest-blocker — design §7.3)
  - SOFT FAIL: 7 turns elapse with neither pass nor Path C condition
               met → trial ends without `done=1`; player may re-enter
               Sanctum to start fresh (no real-time cooldown)

What this suite validates:

  1. Schema v24 columns present and writable
     (village_trial_spirit_turn / _path_c_locked).
  2. Accessors:
        - is_spirit_trial_done / is_spirit_unlocked
        - get_spirit_turn / get_spirit_dark_pull / get_spirit_rejections
        - is_path_c_locked / is_spirit_trial_started
        - is_spirit_unlocked respects the audience+skill+courage+flesh chain
  3. Dark-future-self speech composer:
        - Per-faction templates (republic/separatist/hutt/imperial/rebel)
        - Generic fallback for unknown/empty factions
        - Each turn 1..7 has a distinct speech
        - Out-of-range turn falls back to last turn rather than crashing
  4. Yarael-in-Sanctum hook:
        - Non-Yarael name → False
        - Wrong room (not Sanctum) → False (audience hook handles)
        - No audience → deflect (defensive, normally unreachable)
        - Done → ack (path C variant when locked)
        - Flesh not done → sequence guidance to Korvas
        - Not started → opening briefing
        - In flight → progress restate
  5. attempt_spirit_trial:
        - Guards: audience / done / skill / courage / flesh / room
        - No-arg + not started → anchor turn=1, emit prompt
        - No-arg + started → re-emit current turn prompt
        - Choice 1 (rejection) → increments rejections, advances turn
        - Choice 2 (ambivalent) → no counter change, advances turn
        - Choice 3 (temptation) → increments dark_pull, advances turn
        - 4th rejection → trial done, PASSED narration
        - 3rd temptation → trial done, Path C locked, special narration
        - Path C beats rejection (dark_pull≥3 wins over rejections≥4)
        - 7-turn cap with neither → soft fail; counters reset for retry
        - Invalid choice → refuse with usage hint
        - Choice without prior init → refuse
  6. Insight gate now requires Spirit (regression).
  7. _handle_talk routes to Spirit hook when in Sanctum.
  8. Parser dispatches `trial spirit` and `trial spirit N`.
  9. Module wiring: village_quest imports Spirit hook; Sanctum room
     constant exposed; FLESH-style integration check.
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
    DARO_NAME, MIRA_NAME, KORVAS_NAME, SARO_NAME, YARAEL_NAME,
    FORGE_ROOM_NAME, COUNCIL_HUT_ROOM_NAME, COMMON_SQUARE_ROOM_NAME,
    MEDITATION_CAVES_ROOM_NAME, SEALED_SANCTUM_ROOM_NAME,
    SPIRIT_MAX_TURNS, SPIRIT_REJECTIONS_TO_PASS,
    SPIRIT_DARK_PULL_TO_LOCK_C,
    SPIRIT_CHOICE_REJECTION, SPIRIT_CHOICE_AMBIVALENT,
    SPIRIT_CHOICE_TEMPTATION, SPIRIT_VALID_CHOICES,
    has_completed_audience,
    is_skill_trial_done, is_courage_trial_done, is_flesh_trial_done,
    is_spirit_trial_done, is_spirit_unlocked, is_spirit_trial_started,
    get_spirit_turn, get_spirit_dark_pull, get_spirit_rejections,
    is_path_c_locked,
    _compose_dark_future_speech,
    maybe_handle_yarael_spirit_trial,
    attempt_spirit_trial,
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
    skill_done=False, courage_done=False, flesh_done=False,
    spirit_done=False, spirit_turn=0,
    spirit_dark_pull=0, spirit_rejections=0,
    spirit_path_c_locked=False,
    insight_done=False,
    faction="",
    room_id=1,
):
    """Build a minimal char dict for Spirit tests."""
    notes = {}
    if audience_done:
        notes["village_first_audience_done"] = True
    return {
        "id": id_,
        "name": f"P{id_}",
        "faction": faction,
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
        "village_trial_flesh_started_at": 0,
        "village_trial_flesh_session_seconds": 0,
        "village_trial_spirit_done": int(spirit_done),
        "village_trial_spirit_dark_pull": spirit_dark_pull,
        "village_trial_spirit_rejections": spirit_rejections,
        "village_trial_spirit_turn": spirit_turn,
        "village_trial_spirit_path_c_locked": int(spirit_path_c_locked),
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
        self._room_name = SEALED_SANCTUM_ROOM_NAME

    def set_room(self, name):
        self._room_name = name

    async def save_character(self, char_id, **kwargs):
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v

    async def get_room(self, room_id):
        return {"name": self._room_name, "id": room_id}


def _all_prereqs(**extra):
    """Helper: char with audience+skill+courage+flesh done (Spirit unlocked)."""
    return _make_char(
        audience_done=True, skill_done=True, courage_done=True,
        flesh_done=True, **extra,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 1. Schema v24
# ═════════════════════════════════════════════════════════════════════════════


class TestSpiritSchemaColumnsExist:

    def test_v24_cols_in_writable_set(self):
        from db.database import Database
        cols = Database._CHARACTER_WRITABLE_COLUMNS
        assert "village_trial_spirit_turn" in cols
        assert "village_trial_spirit_path_c_locked" in cols

    def test_v24_migration_text_includes_new_cols(self):
        path = os.path.join(PROJECT_ROOT, "db", "database.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "village_trial_spirit_turn" in src
        assert "village_trial_spirit_path_c_locked" in src

    def test_schema_version_at_least_24(self):
        from db.database import SCHEMA_VERSION
        assert SCHEMA_VERSION >= 24


# ═════════════════════════════════════════════════════════════════════════════
# 2. Accessors
# ═════════════════════════════════════════════════════════════════════════════


class TestSpiritAccessors:

    def test_done_default_false(self):
        char = _make_char()
        assert is_spirit_trial_done(char) is False

    def test_done_true_when_set(self):
        char = _make_char(spirit_done=True)
        assert is_spirit_trial_done(char) is True

    def test_started_default_false(self):
        char = _make_char()
        assert is_spirit_trial_started(char) is False

    def test_started_true_when_turn_nonzero(self):
        char = _make_char(spirit_turn=1)
        assert is_spirit_trial_started(char) is True

    def test_get_spirit_turn(self):
        char = _make_char(spirit_turn=3)
        assert get_spirit_turn(char) == 3

    def test_get_spirit_dark_pull(self):
        char = _make_char(spirit_dark_pull=2)
        assert get_spirit_dark_pull(char) == 2

    def test_get_spirit_rejections(self):
        char = _make_char(spirit_rejections=3)
        assert get_spirit_rejections(char) == 3

    def test_is_path_c_locked_default_false(self):
        char = _make_char()
        assert is_path_c_locked(char) is False

    def test_is_path_c_locked_true_when_set(self):
        char = _make_char(spirit_path_c_locked=True)
        assert is_path_c_locked(char) is True


class TestSpiritUnlocked:

    def test_no_audience_locked(self):
        char = _make_char(skill_done=True, courage_done=True, flesh_done=True)
        assert is_spirit_unlocked(char) is False

    def test_no_skill_locked(self):
        char = _make_char(audience_done=True, courage_done=True, flesh_done=True)
        assert is_spirit_unlocked(char) is False

    def test_no_courage_locked(self):
        char = _make_char(audience_done=True, skill_done=True, flesh_done=True)
        assert is_spirit_unlocked(char) is False

    def test_no_flesh_locked(self):
        char = _make_char(audience_done=True, skill_done=True, courage_done=True)
        assert is_spirit_unlocked(char) is False

    def test_all_four_unlocks(self):
        char = _all_prereqs()
        assert is_spirit_unlocked(char) is True


# ═════════════════════════════════════════════════════════════════════════════
# 3. Dark-future-self composer
# ═════════════════════════════════════════════════════════════════════════════


class TestComposeDarkFutureSpeech:

    def test_returns_nonempty_for_each_turn_generic(self):
        char = _make_char(faction="")
        for t in range(1, SPIRIT_MAX_TURNS + 1):
            speech = _compose_dark_future_speech(char, t)
            assert isinstance(speech, str)
            assert len(speech) > 30

    def test_each_turn_distinct_for_generic(self):
        char = _make_char(faction="")
        speeches = [_compose_dark_future_speech(char, t)
                    for t in range(1, SPIRIT_MAX_TURNS + 1)]
        # Every turn produces a different speech
        assert len(set(speeches)) == SPIRIT_MAX_TURNS

    def test_republic_turn_mentions_regs_or_orders(self):
        char = _make_char(faction="republic")
        # Pull all 7 turns; Republic theme should be present somewhere
        all_text = " ".join(_compose_dark_future_speech(char, t)
                            for t in range(1, SPIRIT_MAX_TURNS + 1))
        assert ("reg" in all_text.lower() or
                "order" in all_text.lower() or
                "Republic" in all_text)

    def test_separatist_turn_mentions_cis_or_dooku(self):
        char = _make_char(faction="separatist")
        all_text = " ".join(_compose_dark_future_speech(char, t)
                            for t in range(1, SPIRIT_MAX_TURNS + 1))
        assert ("cis" in all_text.lower() or
                "Confederacy" in all_text or
                "Dooku" in all_text)

    def test_hutt_turn_mentions_cartel(self):
        char = _make_char(faction="hutt_cartel")
        all_text = " ".join(_compose_dark_future_speech(char, t)
                            for t in range(1, SPIRIT_MAX_TURNS + 1))
        assert "Cartel" in all_text or "Hutt" in all_text

    def test_imperial_turn_mentions_empire(self):
        char = _make_char(faction="imperial")
        all_text = " ".join(_compose_dark_future_speech(char, t)
                            for t in range(1, SPIRIT_MAX_TURNS + 1))
        assert "Empire" in all_text or "Emperor" in all_text or "Imperial" in all_text

    def test_rebel_turn_mentions_rebellion(self):
        char = _make_char(faction="rebel")
        all_text = " ".join(_compose_dark_future_speech(char, t)
                            for t in range(1, SPIRIT_MAX_TURNS + 1))
        assert "Rebellion" in all_text

    def test_unknown_faction_falls_back_to_generic(self):
        char_unknown = _make_char(faction="something_unknown")
        char_empty = _make_char(faction="")
        # Same speech for both
        assert (_compose_dark_future_speech(char_unknown, 1)
                == _compose_dark_future_speech(char_empty, 1))

    def test_out_of_range_turn_falls_back_to_last_turn(self):
        char = _make_char(faction="")
        last = _compose_dark_future_speech(char, SPIRIT_MAX_TURNS)
        # Out-of-range turn should not crash; falls back to last turn
        assert _compose_dark_future_speech(char, 99) == last
        assert _compose_dark_future_speech(char, 0) == last
        assert _compose_dark_future_speech(char, -5) == last


# ═════════════════════════════════════════════════════════════════════════════
# 4. Yarael-in-Sanctum hook
# ═════════════════════════════════════════════════════════════════════════════


class TestYaraelSpiritHook:

    def test_non_yarael_returns_false(self):
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            ok = await maybe_handle_yarael_spirit_trial(
                session, FakeDB(char), char, "Random NPC",
            )
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_wrong_room_returns_false(self):
        # Yarael in Master's Chamber should NOT be intercepted by the
        # Spirit hook — the audience hook handles that.
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("Master's Chamber")  # not the Sanctum
            ok = await maybe_handle_yarael_spirit_trial(
                session, db, char, YARAEL_NAME,
            )
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_no_audience_deflects_in_sanctum(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_spirit_trial(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "Master" in output or "Chamber" in output
        asyncio.run(_check())

    def test_no_flesh_directs_to_korvas(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=False,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_spirit_trial(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "Korvas" in output or "body" in output.lower()
        asyncio.run(_check())

    def test_done_passed_acks(self):
        async def _check():
            char = _all_prereqs(spirit_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_spirit_trial(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "stood" in output.lower() or "Council Hut" in output
        asyncio.run(_check())

    def test_done_path_c_locked_ack_is_different(self):
        async def _check():
            char = _all_prereqs(
                spirit_done=True, spirit_path_c_locked=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_spirit_trial(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Path C ack mentions "road you are on is not ours" / sadness
            assert "road" in output.lower() or "sadness" in output.lower()
        asyncio.run(_check())

    def test_unlocked_not_started_emits_briefing(self):
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_spirit_trial(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "trial spirit" in output.lower()
            # Mentions the three response types
            assert "reject" in output.lower() or "yield" in output.lower()
        asyncio.run(_check())

    def test_in_flight_shows_progress(self):
        async def _check():
            char = _all_prereqs(
                spirit_turn=3, spirit_rejections=2, spirit_dark_pull=1,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_spirit_trial(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Mentions current turn / counters
            assert "Rejection" in output or "rejection" in output.lower()
            assert "2" in output  # rejections count
        asyncio.run(_check())

    def test_case_insensitive_npc_name(self):
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_spirit_trial(
                session, db, char, YARAEL_NAME.upper(),
            )
            assert ok is True
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 5. attempt_spirit_trial — guards
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptSpiritGuards:

    def test_no_audience_refuses(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Master" in output
        asyncio.run(_check())

    def test_already_done_refuses(self):
        async def _check():
            char = _all_prereqs(spirit_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "already" in output.lower()
        asyncio.run(_check())

    def test_no_skill_directs_to_forge(self):
        async def _check():
            char = _make_char(audience_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Daro" in output or "Forge" in output
        asyncio.run(_check())

    def test_no_courage_directs_to_square(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Mira" in output or "Square" in output
        asyncio.run(_check())

    def test_no_flesh_directs_to_korvas(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Korvas" in output or "Caves" in output
        asyncio.run(_check())

    def test_wrong_room_refuses(self):
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            ok = await attempt_spirit_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Sealed Sanctum" in output or "Sanctum" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 6. attempt_spirit_trial — initiate / re-emit
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptSpiritInitiate:

    def test_initiate_anchors_turn_1_and_emits_prompt(self):
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char)
            assert ok is True
            assert get_spirit_turn(char) == 1
            output = "\n".join(session.received)
            # Prompt mentions all three trial spirit options
            assert "trial spirit 1" in output.lower()
            assert "trial spirit 2" in output.lower()
            assert "trial spirit 3" in output.lower()
            # Save was called with turn=1
            assert any(s.get("village_trial_spirit_turn") == 1
                       for s in db.saves)
        asyncio.run(_check())

    def test_initiate_when_started_re_emits_current_turn(self):
        async def _check():
            char = _all_prereqs(spirit_turn=4, spirit_rejections=2)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char)
            assert ok is True
            # Turn unchanged
            assert get_spirit_turn(char) == 4
            output = "\n".join(session.received)
            # Prompt mentions current turn 4
            assert "Turn 4" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 7. attempt_spirit_trial — choice handling
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptSpiritChoices:

    def test_choice_without_init_refuses(self):
        async def _check():
            char = _all_prereqs()  # turn=0
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char, choice=1)
            assert ok is False
            output = "\n".join(session.received)
            assert "trial spirit" in output.lower()
            # Counters unchanged
            assert get_spirit_rejections(char) == 0
        asyncio.run(_check())

    def test_invalid_choice_refuses(self):
        async def _check():
            char = _all_prereqs(spirit_turn=1)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char, choice=99)
            assert ok is False
            output = "\n".join(session.received)
            assert "1" in output and "2" in output and "3" in output
        asyncio.run(_check())

    def test_rejection_increments_rejections(self):
        async def _check():
            char = _all_prereqs(spirit_turn=1)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char, choice=1)
            assert ok is True
            assert get_spirit_rejections(char) == 1
            assert get_spirit_dark_pull(char) == 0
            assert get_spirit_turn(char) == 2
            assert is_spirit_trial_done(char) is False
        asyncio.run(_check())

    def test_ambivalent_advances_turn_no_counter_change(self):
        async def _check():
            char = _all_prereqs(spirit_turn=2)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char, choice=2)
            assert ok is True
            assert get_spirit_rejections(char) == 0
            assert get_spirit_dark_pull(char) == 0
            assert get_spirit_turn(char) == 3
        asyncio.run(_check())

    def test_temptation_increments_dark_pull(self):
        async def _check():
            char = _all_prereqs(spirit_turn=1)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char, choice=3)
            assert ok is True
            assert get_spirit_rejections(char) == 0
            assert get_spirit_dark_pull(char) == 1
            assert get_spirit_turn(char) == 2
            assert is_spirit_trial_done(char) is False
            assert is_path_c_locked(char) is False
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 8. attempt_spirit_trial — pass + Path C + soft fail
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptSpiritOutcomes:

    def test_fourth_rejection_passes_trial(self):
        async def _check():
            # Already at 3 rejections, turn 4
            char = _all_prereqs(spirit_turn=4, spirit_rejections=3)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char, choice=1)
            assert ok is True
            assert is_spirit_trial_done(char) is True
            assert is_path_c_locked(char) is False
            output = "\n".join(session.received)
            assert "PASSED" in output
            # Save included done flag
            assert any(s.get("village_trial_spirit_done") == 1
                       for s in db.saves)
        asyncio.run(_check())

    def test_third_temptation_locks_path_c_and_completes(self):
        async def _check():
            char = _all_prereqs(spirit_turn=3, spirit_dark_pull=2)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char, choice=3)
            assert ok is True
            assert is_spirit_trial_done(char) is True
            assert is_path_c_locked(char) is True
            output = "\n".join(session.received)
            assert "PATH C" in output or "Path C" in output
            assert "dark whispers" in output.lower()
            # Save included both flags
            assert any(s.get("village_trial_spirit_done") == 1
                       for s in db.saves)
            assert any(s.get("village_trial_spirit_path_c_locked") == 1
                       for s in db.saves)
        asyncio.run(_check())

    def test_path_c_beats_rejections_when_both_thresholds_met(self):
        # Player has 4 rejections AND 2 dark pulls; one more temptation
        # should still lock Path C even though rejections >= pass.
        async def _check():
            char = _all_prereqs(
                spirit_turn=7, spirit_rejections=4, spirit_dark_pull=2,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_spirit_trial(session, db, char, choice=3)
            assert ok is True
            assert is_spirit_trial_done(char) is True
            # Path C wins
            assert is_path_c_locked(char) is True
            output = "\n".join(session.received)
            assert "PATH C" in output or "Path C" in output
        asyncio.run(_check())

    def test_seven_turns_no_pass_no_lock_soft_fails_and_resets(self):
        async def _check():
            # Turn 7, 3 rejections, 2 dark — neither threshold hit
            char = _all_prereqs(
                spirit_turn=7, spirit_rejections=3, spirit_dark_pull=2,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            # An ambivalent choice on turn 7 → advance to 8 → soft fail
            ok = await attempt_spirit_trial(session, db, char, choice=2)
            assert ok is True
            # Trial NOT done
            assert is_spirit_trial_done(char) is False
            assert is_path_c_locked(char) is False
            # Counters reset for retry
            assert get_spirit_turn(char) == 0
            assert get_spirit_rejections(char) == 0
            assert get_spirit_dark_pull(char) == 0
            output = "\n".join(session.received)
            assert "incomplete" in output.lower() or "Re-enter" in output
        asyncio.run(_check())

    def test_full_pass_arc_via_four_rejections(self):
        """End-to-end: initiate → 4 rejections → PASSED."""
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)
            # Initiate
            await attempt_spirit_trial(session, db, char)
            assert get_spirit_turn(char) == 1
            # 4 rejections in a row
            for _ in range(4):
                await attempt_spirit_trial(session, db, char, choice=1)
            assert is_spirit_trial_done(char)
            assert is_path_c_locked(char) is False
            assert get_spirit_rejections(char) == 4
        asyncio.run(_check())

    def test_full_path_c_arc_via_three_temptations(self):
        """End-to-end: initiate → 3 temptations → PATH C lock."""
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_spirit_trial(session, db, char)
            for _ in range(3):
                await attempt_spirit_trial(session, db, char, choice=3)
            assert is_spirit_trial_done(char)
            assert is_path_c_locked(char) is True
        asyncio.run(_check())

    def test_retry_after_soft_fail_works(self):
        """End-to-end: 7 ambivalent turns → soft fail → re-init →
        4 rejections → PASSED."""
        async def _check():
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_spirit_trial(session, db, char)
            for _ in range(SPIRIT_MAX_TURNS):
                await attempt_spirit_trial(session, db, char, choice=2)
            # Soft failed
            assert is_spirit_trial_done(char) is False
            assert get_spirit_turn(char) == 0
            # Re-init
            await attempt_spirit_trial(session, db, char)
            assert get_spirit_turn(char) == 1
            # Pass cleanly
            for _ in range(4):
                await attempt_spirit_trial(session, db, char, choice=1)
            assert is_spirit_trial_done(char)
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 9. Insight gate now requires Spirit
# ═════════════════════════════════════════════════════════════════════════════


class TestInsightGateRequiresSpirit:
    """F.7.c.4 tightens is_insight_unlocked to require Spirit."""

    def test_audience_skill_courage_flesh_locked_without_spirit(self):
        char = _all_prereqs(spirit_done=False)
        assert is_insight_unlocked(char) is False

    def test_all_five_unlocks(self):
        char = _all_prereqs(spirit_done=True)
        assert is_insight_unlocked(char) is True

    def test_path_c_locked_still_passes_insight_gate(self):
        # Per design §7.3, Path C lock-in completes the trial. The
        # Insight gate should treat that as "spirit done."
        char = _all_prereqs(spirit_done=True, spirit_path_c_locked=True)
        assert is_insight_unlocked(char) is True


# ═════════════════════════════════════════════════════════════════════════════
# 10. _handle_talk dispatch
# ═════════════════════════════════════════════════════════════════════════════


class TestHandleTalkDispatchSpirit:
    """Verify check_village_quest('talk') routes to the Yarael-Spirit
    hook when the player is in the Sealed Sanctum.
    """

    def test_yarael_in_sanctum_dispatched(self):
        async def _check():
            char = _all_prereqs(room_id=42)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(SEALED_SANCTUM_ROOM_NAME)

            await check_village_quest(
                session, db, "talk", npc_name=YARAEL_NAME,
            )
            output = "\n".join(session.received)
            # Briefing mentions trial spirit
            assert "trial spirit" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 11. Parser command (TrialCommand) — `trial spirit`
# ═════════════════════════════════════════════════════════════════════════════


class TestTrialCommandSpiritWiring:

    def test_parser_source_wires_spirit_branch(self):
        path = os.path.join(PROJECT_ROOT, "parser", "village_trial_commands.py")
        src = open(path, "r", encoding="utf-8").read()
        assert 'if which == "spirit":' in src
        assert "attempt_spirit_trial" in src

    def test_help_text_mentions_spirit(self):
        from parser.village_trial_commands import TrialCommand
        cmd = TrialCommand()
        assert "spirit" in cmd.help_text.lower()
        assert "spirit" in cmd.usage.lower()

    def test_unknown_trial_lists_spirit_in_available(self):
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
            assert "spirit" in output.lower()
        asyncio.run(_check())

    def test_trial_spirit_no_arg_dispatches(self):
        """`trial spirit` (no number) initiates the trial."""
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _all_prereqs()
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="trial spirit",
                command="trial",
                args="spirit",
                args_list=["spirit"],
                db=db,
            )
            await TrialCommand().execute(ctx)
            assert get_spirit_turn(char) == 1
        asyncio.run(_check())

    def test_trial_spirit_with_choice_dispatches(self):
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _all_prereqs(spirit_turn=1)
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="trial spirit 1",
                command="trial",
                args="spirit 1",
                args_list=["spirit", "1"],
                db=db,
            )
            await TrialCommand().execute(ctx)
            assert get_spirit_rejections(char) == 1
            assert get_spirit_turn(char) == 2
        asyncio.run(_check())

    def test_trial_spirit_invalid_subarg_rejects(self):
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _all_prereqs(spirit_turn=1)
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="trial spirit banana",
                command="trial",
                args="spirit banana",
                args_list=["spirit", "banana"],
                db=db,
            )
            await TrialCommand().execute(ctx)
            output = "\n".join(session.received)
            assert "Usage" in output or "1" in output
            # Counters unchanged
            assert get_spirit_rejections(char) == 0
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 12. Module wiring
# ═════════════════════════════════════════════════════════════════════════════


class TestModuleWiring:

    def test_village_quest_imports_spirit_hook(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_quest.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "maybe_handle_yarael_spirit_trial" in src

    def test_village_trials_exposes_spirit_surface(self):
        from engine import village_trials
        assert hasattr(village_trials, "is_spirit_trial_done")
        assert hasattr(village_trials, "is_spirit_unlocked")
        assert hasattr(village_trials, "is_spirit_trial_started")
        assert hasattr(village_trials, "get_spirit_turn")
        assert hasattr(village_trials, "get_spirit_dark_pull")
        assert hasattr(village_trials, "get_spirit_rejections")
        assert hasattr(village_trials, "is_path_c_locked")
        assert hasattr(village_trials, "_compose_dark_future_speech")
        assert hasattr(village_trials, "maybe_handle_yarael_spirit_trial")
        assert hasattr(village_trials, "attempt_spirit_trial")

    def test_sealed_sanctum_room_constant_exposed(self):
        assert SEALED_SANCTUM_ROOM_NAME == "The Sealed Sanctum"

    def test_yarael_name_constant_exposed(self):
        assert YARAEL_NAME == "Master Yarael Tinré"

    def test_spirit_constants_match_design(self):
        assert SPIRIT_MAX_TURNS == 7
        assert SPIRIT_REJECTIONS_TO_PASS == 4
        assert SPIRIT_DARK_PULL_TO_LOCK_C == 3

    def test_choice_constants_distinct(self):
        assert SPIRIT_CHOICE_REJECTION != SPIRIT_CHOICE_AMBIVALENT
        assert SPIRIT_CHOICE_AMBIVALENT != SPIRIT_CHOICE_TEMPTATION
        assert SPIRIT_CHOICE_REJECTION != SPIRIT_CHOICE_TEMPTATION
        assert set(SPIRIT_VALID_CHOICES) == {1, 2, 3}
