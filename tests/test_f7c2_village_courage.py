# -*- coding: utf-8 -*-
"""
tests/test_f7c2_village_courage.py — F.7.c.2 — Trial of Courage.

Closes Trial 2 (Courage — Elder Mira Delen at the Common Square)
end-to-end. Single-turn 3-choice dialogue:

  [1] "I won't deny it."   → Pass.
  [2] "How did you know?"  → Pass (Mira nods deeper; no mechanical
                             bonus this drop).
  [3] Walk away.           → Fail; 24-hour real-time cooldown.

What this suite validates:

  1. Schema columns from v22 are present and writable
     (village_trial_courage_done / _lockout_until). No new schema.
  2. Accessors: is_courage_trial_done / courage_trial_lockout_remaining /
     is_courage_unlocked respect the audience + skill gates.
  3. Buried-memory composer:
        - Uses +background verbatim when present (truncated if huge)
        - Falls back to faction template when bg empty
        - Uses generic fallback when faction is unknown
  4. Mira hook (talk-to-Mira):
        - Returns False for non-Mira NPC names
        - Deflects without audience
        - Acks completion if done
        - Deflects if Skill not yet done
        - Reports remaining lockout if active
        - Presents the briefing when ready
  5. attempt_courage_trial (no-arg) emits the recital + 3 options.
  6. attempt_courage_trial(choice=1) and (choice=2) flip done flag.
  7. attempt_courage_trial(choice=3) anchors 24h lockout.
  8. attempt_courage_trial guards: no audience / done / no skill /
     in-lockout / wrong room.
  9. Insight gate now requires Courage (regression check; verified
     against patched F.7.c.1 suite separately).
 10. _handle_talk dispatches to Mira hook.
 11. TrialCommand parses 'trial courage [N]' correctly.

Tests use FakeSession / FakeDB stubs — no real DB or network.
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
    COURAGE_FAIL_COOLDOWN_SECONDS,
    COURAGE_CHOICE_ACKNOWLEDGE, COURAGE_CHOICE_QUESTION,
    COURAGE_CHOICE_WALK_AWAY, COURAGE_PASS_CHOICES, COURAGE_VALID_CHOICES,
    has_completed_audience,
    is_skill_trial_done,
    is_courage_trial_done, courage_trial_lockout_remaining,
    is_courage_unlocked,
    _compose_buried_memory,
    maybe_handle_mira_courage_trial,
    attempt_courage_trial,
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
    skill_done=False, courage_done=False, courage_lockout_until=0,
    flesh_done=False, flesh_started_at=0,
    spirit_done=False,
    insight_done=False,
    faction="",
    room_id=1,
):
    """Build a minimal char dict for Courage tests.

    The ``flesh_done`` and ``flesh_started_at`` kwargs were added when
    F.7.c.3 tightened the Insight gate to also require Flesh.
    The ``spirit_done`` kwarg was added when F.7.c.4 tightened the
    Insight gate to also require Spirit.
    """
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
        "village_trial_courage_lockout_until": courage_lockout_until,
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
    """Minimal DB stub. save_character mutates the in-memory char dict.

    Background defaults to empty; tests can override with set_background().
    """
    def __init__(self, char):
        self._char = char
        self.saves: list[dict] = []
        self._room_name = COMMON_SQUARE_ROOM_NAME
        self._background = ""

    def set_room(self, name):
        self._room_name = name

    def set_background(self, text):
        self._background = text

    async def save_character(self, char_id, **kwargs):
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v

    async def get_room(self, room_id):
        return {"name": self._room_name, "id": room_id}

    async def get_narrative(self, char_id):
        # narrative.get_background calls db.get_narrative.
        return {"background": self._background}

    async def add_to_inventory(self, char_id, item):
        # No item grants on Courage in F.7.c.2.
        pass


# ═════════════════════════════════════════════════════════════════════════════
# 1. Schema columns
# ═════════════════════════════════════════════════════════════════════════════


class TestCourageSchemaColumnsExist:
    """Verify the v22 Courage columns are present in the writable set
    and the live schema. Schema is built by build_mos_eisley.
    """

    def test_courage_columns_in_writable_set(self):
        from db.database import Database
        cols = Database._CHARACTER_WRITABLE_COLUMNS
        assert "village_trial_courage_done" in cols
        assert "village_trial_courage_lockout_until" in cols

    def test_v22_migration_text_includes_courage_lockout(self):
        # Light grep — this is a self-document check that the migration
        # we depend on is actually in db/database.py source.
        path = os.path.join(PROJECT_ROOT, "db", "database.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "village_trial_courage_done" in src
        assert "village_trial_courage_lockout_until" in src


# ═════════════════════════════════════════════════════════════════════════════
# 2. Accessors
# ═════════════════════════════════════════════════════════════════════════════


class TestCourageAccessors:

    def test_done_default_false(self):
        char = _make_char()
        assert is_courage_trial_done(char) is False

    def test_done_true_when_set(self):
        char = _make_char(courage_done=True)
        assert is_courage_trial_done(char) is True

    def test_lockout_zero_when_unset(self):
        char = _make_char()
        assert courage_trial_lockout_remaining(char) == 0.0

    def test_lockout_zero_when_in_past(self):
        # Lockout in the past is effectively no lockout.
        char = _make_char(courage_lockout_until=time.time() - 60)
        assert courage_trial_lockout_remaining(char) == 0.0

    def test_lockout_positive_when_in_future(self):
        char = _make_char(courage_lockout_until=time.time() + 3600)
        rem = courage_trial_lockout_remaining(char)
        assert 3500 < rem <= 3600

    def test_unlocked_requires_audience_and_skill(self):
        # No audience: locked
        char = _make_char(audience_done=False, skill_done=True)
        assert is_courage_unlocked(char) is False
        # No skill: locked
        char = _make_char(audience_done=True, skill_done=False)
        assert is_courage_unlocked(char) is False
        # Both: unlocked
        char = _make_char(audience_done=True, skill_done=True)
        assert is_courage_unlocked(char) is True


# ═════════════════════════════════════════════════════════════════════════════
# 3. Buried-memory composer
# ═════════════════════════════════════════════════════════════════════════════


class TestComposeBuriedMemory:

    def test_uses_background_when_present(self):
        char = _make_char()
        bg = "I once stole a starship from a friend and never told them."
        out = _compose_buried_memory(char, bg)
        assert bg in out
        # Mira's framing should wrap the background
        assert "I have heard" in out or "Listen" in out

    def test_truncates_long_background(self):
        char = _make_char()
        bg = "I once stole. " * 200  # ~2,800 chars
        out = _compose_buried_memory(char, bg)
        # Truncated form should be much shorter than full bg
        assert len(out) < len(bg) + 500
        assert "..." in out

    def test_uses_faction_template_when_bg_empty_republic(self):
        char = _make_char(faction="republic")
        out = _compose_buried_memory(char, "")
        assert "regs" in out.lower() or "kill" in out.lower()

    def test_uses_faction_template_when_bg_empty_separatist(self):
        char = _make_char(faction="separatist")
        out = _compose_buried_memory(char, "")
        # Separatist template mentions signing off / numbers
        assert "signed" in out.lower() or "numbers" in out.lower()

    def test_uses_faction_template_when_bg_empty_hutt(self):
        char = _make_char(faction="hutt_cartel")
        out = _compose_buried_memory(char, "")
        assert "person" in out.lower() and "walked" in out.lower()

    def test_uses_generic_fallback_when_unknown_faction(self):
        char = _make_char(faction="some_unknown_faction")
        out = _compose_buried_memory(char, "")
        # Generic fallback mentions hidden moment
        assert "moment" in out.lower() or "hurt" in out.lower()

    def test_uses_generic_fallback_when_no_faction(self):
        char = _make_char(faction="")
        out = _compose_buried_memory(char, "")
        # Should not be empty
        assert len(out) > 30

    def test_none_background_treated_as_empty(self):
        # Defensive: None should not crash.
        char = _make_char(faction="republic")
        out = _compose_buried_memory(char, None)
        assert len(out) > 0


# ═════════════════════════════════════════════════════════════════════════════
# 4. Mira hook
# ═════════════════════════════════════════════════════════════════════════════


class TestMiraHook:

    def test_non_mira_returns_false(self):
        async def _check():
            char = _make_char()
            session = FakeSession(char)
            ok = await maybe_handle_mira_courage_trial(
                session, FakeDB(char), char, "Random NPC",
            )
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_no_audience_deflects(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            ok = await maybe_handle_mira_courage_trial(
                session, FakeDB(char), char, MIRA_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Mira sends them to the Master
            assert "Master" in output

    def test_courage_done_acks(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
            )
            session = FakeSession(char)
            ok = await maybe_handle_mira_courage_trial(
                session, FakeDB(char), char, MIRA_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Acknowledgement language
            assert "stood" in output.lower() or "heard it" in output.lower()
        asyncio.run(_check())

    def test_no_audience_check_runs_first(self):
        # Even if courage is somehow set to done, no audience still
        # blocks. Defense in depth.
        async def _check():
            char = _make_char(audience_done=False, courage_done=True)
            session = FakeSession(char)
            ok = await maybe_handle_mira_courage_trial(
                session, FakeDB(char), char, MIRA_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "Master" in output
        asyncio.run(_check())

    def test_skill_not_done_deflects(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=False)
            session = FakeSession(char)
            ok = await maybe_handle_mira_courage_trial(
                session, FakeDB(char), char, MIRA_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Sends to Daro / Forge
            assert "Daro" in output or "Forge" in output

    def test_lockout_active_states_remaining(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True,
                courage_lockout_until=time.time() + 3600,
            )
            session = FakeSession(char)
            ok = await maybe_handle_mira_courage_trial(
                session, FakeDB(char), char, MIRA_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Mentions waiting
            assert "minute" in output.lower() or "hour" in output.lower()
        asyncio.run(_check())

    def test_ready_presents_briefing(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            ok = await maybe_handle_mira_courage_trial(
                session, FakeDB(char), char, MIRA_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Briefing tells player what command to type
            assert "trial courage" in output.lower()
        asyncio.run(_check())

    def test_case_insensitive_npc_name_match(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            ok = await maybe_handle_mira_courage_trial(
                session, FakeDB(char), char, MIRA_NAME.upper(),
            )
            assert ok is True
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 5. attempt_courage_trial — initiate (no choice arg)
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptCourageInitiate:

    def test_no_audience_refuses(self):
        async def _check():
            char = _make_char(audience_done=False, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char)
            assert ok is False
            assert char["village_trial_courage_done"] == 0
        asyncio.run(_check())

    def test_already_done_refuses(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char)
            assert ok is False
        asyncio.run(_check())

    def test_no_skill_refuses(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char)
            assert ok is False
        asyncio.run(_check())

    def test_in_lockout_refuses(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True,
                courage_lockout_until=time.time() + 3600,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char)
            assert ok is False
        asyncio.run(_check())

    def test_wrong_room_refuses(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            ok = await attempt_courage_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Common Square" in output
        asyncio.run(_check())

    def test_initiate_emits_recital_and_options(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, faction="republic",
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char)
            assert ok is True
            output = "\n".join(session.received)
            # Recital body present (republic template includes "regs"
            # or "kill"; both are matchable)
            assert "kill" in output.lower() or "regs" in output.lower()
            # All three options listed
            assert "trial courage 1" in output.lower()
            assert "trial courage 2" in output.lower()
            assert "trial courage 3" in output.lower()
            # Done flag NOT yet set — initiation is just the recital
            assert char["village_trial_courage_done"] == 0
        asyncio.run(_check())

    def test_initiate_uses_background_if_present(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_background(
                "I had a brother. I let him take the fall for what was mine."
            )
            ok = await attempt_courage_trial(session, db, char)
            assert ok is True
            output = "\n".join(session.received)
            assert "brother" in output
        asyncio.run(_check())

    def test_initiate_handles_get_background_failure(self):
        # If get_background raises (e.g., narrative table missing),
        # initiate must not crash — falls back to template.
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, faction="separatist",
            )
            session = FakeSession(char)

            class BadDB(FakeDB):
                async def get_narrative(self, char_id):
                    raise RuntimeError("simulated narrative fetch failure")

            db = BadDB(char)
            ok = await attempt_courage_trial(session, db, char)
            assert ok is True
            output = "\n".join(session.received)
            # Falls back to faction template
            assert "signed" in output.lower() or "numbers" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 6. attempt_courage_trial — commit (choice arg)
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptCourageCommit:

    def test_choice_1_passes_trial(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(
                session, db, char, choice=COURAGE_CHOICE_ACKNOWLEDGE,
            )
            assert ok is True
            assert char["village_trial_courage_done"] == 1
            output = "\n".join(session.received)
            assert "PASSED" in output
            # Save was called with the done flag
            assert any(s.get("village_trial_courage_done") == 1
                       for s in db.saves)
        asyncio.run(_check())

    def test_choice_2_passes_trial(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(
                session, db, char, choice=COURAGE_CHOICE_QUESTION,
            )
            assert ok is True
            assert char["village_trial_courage_done"] == 1
            output = "\n".join(session.received)
            assert "PASSED" in output
            # The choice-2 narration mentions "lived" / "listened"
            assert "lived" in output.lower() or "listen" in output.lower()
        asyncio.run(_check())

    def test_choice_3_fails_with_lockout(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(
                session, db, char, choice=COURAGE_CHOICE_WALK_AWAY,
            )
            assert ok is True
            # Done flag NOT set
            assert char["village_trial_courage_done"] == 0
            # Lockout anchored ~24h in the future
            until = char["village_trial_courage_lockout_until"]
            now = time.time()
            assert COURAGE_FAIL_COOLDOWN_SECONDS - 10 < (until - now) <= COURAGE_FAIL_COOLDOWN_SECONDS
            # Save included the lockout
            assert any("village_trial_courage_lockout_until" in s
                       for s in db.saves)
            output = "\n".join(session.received)
            assert "walked away" in output.lower() or "24" in output
        asyncio.run(_check())

    def test_invalid_choice_refuses(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char, choice=99)
            assert ok is False
            assert char["village_trial_courage_done"] == 0
            output = "\n".join(session.received)
            assert "1" in output and "2" in output and "3" in output
        asyncio.run(_check())

    def test_commit_with_no_audience_refuses(self):
        async def _check():
            char = _make_char(audience_done=False, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char, choice=1)
            assert ok is False
            assert char["village_trial_courage_done"] == 0
        asyncio.run(_check())

    def test_commit_when_already_done_refuses(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char, choice=1)
            assert ok is False
        asyncio.run(_check())

    def test_commit_when_in_lockout_refuses(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True,
                courage_lockout_until=time.time() + 3600,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_courage_trial(session, db, char, choice=1)
            assert ok is False
            # Should not flip done
            assert char["village_trial_courage_done"] == 0
        asyncio.run(_check())

    def test_commit_in_wrong_room_refuses(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            ok = await attempt_courage_trial(session, db, char, choice=1)
            assert ok is False
            assert char["village_trial_courage_done"] == 0
        asyncio.run(_check())

    def test_pass_choices_constant_correct(self):
        # Defensive test: ensure pass set matches design.
        assert COURAGE_CHOICE_ACKNOWLEDGE in COURAGE_PASS_CHOICES
        assert COURAGE_CHOICE_QUESTION in COURAGE_PASS_CHOICES
        assert COURAGE_CHOICE_WALK_AWAY not in COURAGE_PASS_CHOICES

    def test_valid_choices_complete(self):
        assert set(COURAGE_VALID_CHOICES) == {1, 2, 3}


# ═════════════════════════════════════════════════════════════════════════════
# 7. Lockout retry path
# ═════════════════════════════════════════════════════════════════════════════


class TestCourageLockoutRetryPath:

    def test_walk_away_then_wait_then_retry(self):
        """End-to-end: choice 3 sets lockout, expired lockout permits
        re-attempt, choice 1 then passes."""
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)

            # First attempt: walk away
            ok = await attempt_courage_trial(session, db, char, choice=3)
            assert ok is True
            assert char["village_trial_courage_done"] == 0
            assert char["village_trial_courage_lockout_until"] > time.time()

            # Simulate 24h+ passing — set lockout to past
            char["village_trial_courage_lockout_until"] = time.time() - 1

            # Re-attempt: choice 1
            session2 = FakeSession(char)
            ok = await attempt_courage_trial(session2, db, char, choice=1)
            assert ok is True
            assert char["village_trial_courage_done"] == 1
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 8. Insight gate now requires Courage
# ═════════════════════════════════════════════════════════════════════════════


class TestInsightGateRequiresCourage:
    """F.7.c.2 tightened is_insight_unlocked to require Courage.
    F.7.c.3 further tightened to require Flesh; the "unlocks" test
    therefore must include flesh_done=True as of F.7.c.3.
    """

    def test_audience_skill_only_locked(self):
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=False,
        )
        assert is_insight_unlocked(char) is False

    def test_audience_skill_courage_no_flesh_locked(self):
        # Courage alone is no longer enough under F.7.c.3.
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
            flesh_done=False,
        )
        assert is_insight_unlocked(char) is False

    def test_audience_skill_courage_flesh_no_spirit_locked_under_f7c4(self):
        # Under F.7.c.4 the gate also requires Spirit. Courage+Flesh
        # alone are no longer enough.
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


class TestHandleTalkDispatchMira:
    """Verify check_village_quest('talk') routes to the Mira hook
    when the NPC name is Mira's. Light wiring check; full protocol
    is mocked.
    """

    def test_mira_dispatched_through_check_village_quest(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)

            # check_village_quest's "talk" handler lives in
            # _handle_talk; it's called through the public surface.
            await check_village_quest(
                session, db, "talk", npc_name=MIRA_NAME,
            )
            output = "\n".join(session.received)
            # Briefing language from Mira hook
            assert "trial courage" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 10. Parser command (TrialCommand) — argparse paths
# ═════════════════════════════════════════════════════════════════════════════


class TestTrialCommandCourageWiring:

    def test_trial_courage_parses_no_arg(self):
        # Source-level check: parser/village_trial_commands.py mentions
        # the courage branch.
        path = os.path.join(PROJECT_ROOT, "parser", "village_trial_commands.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "if which == \"courage\":" in src
        assert "attempt_courage_trial" in src

    def test_trial_command_help_mentions_courage(self):
        from parser.village_trial_commands import TrialCommand
        cmd = TrialCommand()
        assert "courage" in cmd.help_text.lower()
        # Usage updated to allow the choice arg
        assert "courage" in cmd.usage.lower()

    def test_trial_command_dispatch_no_arg(self):
        """`trial courage` (no number) should call attempt_courage_trial
        with choice=None."""
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="trial " + 'courage',
                command="trial",
                args='courage',
                args_list=['courage'],
                db=db,
            )
            await TrialCommand().execute(ctx)
            # Recital was emitted (we got the 3-options block)
            output = "\n".join(session.received)
            assert "trial courage 1" in output.lower()
        asyncio.run(_check())

    def test_trial_command_dispatch_with_choice(self):
        """`trial courage 1` should commit choice 1."""
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="trial " + 'courage 1',
                command="trial",
                args='courage 1',
                args_list=['courage', '1'],
                db=db,
            )
            await TrialCommand().execute(ctx)
            assert char["village_trial_courage_done"] == 1
        asyncio.run(_check())

    def test_trial_command_dispatch_with_walk_away(self):
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="trial " + 'courage 3',
                command="trial",
                args='courage 3',
                args_list=['courage', '3'],
                db=db,
            )
            await TrialCommand().execute(ctx)
            assert char["village_trial_courage_done"] == 0
            assert char["village_trial_courage_lockout_until"] > time.time()
        asyncio.run(_check())

    def test_trial_command_dispatch_invalid_subarg(self):
        """`trial courage banana` should be rejected with a usage hint."""
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="trial " + 'courage banana',
                command="trial",
                args='courage banana',
                args_list=['courage', 'banana'],
                db=db,
            )
            await TrialCommand().execute(ctx)
            output = "\n".join(session.received)
            assert "1" in output and "2" in output and "3" in output
            # Done flag not flipped
            assert char["village_trial_courage_done"] == 0
        asyncio.run(_check())

    def test_trial_command_no_arg_unchanged(self):
        """Bare `trial` (no skill/courage) keeps existing behaviour."""
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char()
            session = FakeSession(char)
            db = FakeDB(char)
            ctx = CommandContext(
                session=session,
                raw_input="trial " + '',
                command="trial",
                args='',
                args_list=[],
                db=db,
            )
            await TrialCommand().execute(ctx)
            output = "\n".join(session.received)
            assert "Usage:" in output
        asyncio.run(_check())

    def test_trial_command_unknown_trial_lists_courage(self):
        async def _check():
            from parser.village_trial_commands import TrialCommand
            from parser.commands import CommandContext
            char = _make_char()
            session = FakeSession(char)
            db = FakeDB(char)
            ctx = CommandContext(
                session=session,
                raw_input="trial " + 'banana',
                command="trial",
                args='banana',
                args_list=['banana'],
                db=db,
            )
            await TrialCommand().execute(ctx)
            output = "\n".join(session.received)
            assert "courage" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 11. Module wiring: village_quest imports Mira hook
# ═════════════════════════════════════════════════════════════════════════════


class TestModuleWiring:

    def test_village_quest_imports_mira_hook(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_quest.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "maybe_handle_mira_courage_trial" in src

    def test_village_trials_exposes_mira_hook(self):
        from engine import village_trials
        assert hasattr(village_trials, "maybe_handle_mira_courage_trial")
        assert hasattr(village_trials, "attempt_courage_trial")
        assert hasattr(village_trials, "is_courage_trial_done")
        assert hasattr(village_trials, "courage_trial_lockout_remaining")
        assert hasattr(village_trials, "is_courage_unlocked")

    def test_common_square_room_constant_exposed(self):
        from engine.village_trials import COMMON_SQUARE_ROOM_NAME
        assert COMMON_SQUARE_ROOM_NAME == "Common Square"
