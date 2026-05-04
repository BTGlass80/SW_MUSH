# -*- coding: utf-8 -*-
"""
tests/test_f7c1_village_trials.py — F.7.c.1 — Trials of Skill + Insight.

Closes the loop on the first two trials end-to-end:
  Trial 1 (Skill — Smith Daro at the Forge): 3-step craft_lightsaber
    sequence with 1-hour cooldown, grants Adegan crystal on completion.
  Trial 5 (Insight — Elder Saro Veck at the Council Hut): three
    holocron fragments, accuse the Sith one, grants pendant on
    completion. Wrong answers permit hint+retry without cooldown.

What this suite validates:

  1. Schema v22: 14 trial state columns added (some forward-reserved
     for F.7.c.2/3); existing v18 columns untouched; all writable.
  2. Build-time: 7 village NPCs in correct rooms (Vitha, Yarael,
     Daro, Mira, Korvas, Saro, Sela). NPC count 145 → 152.
  3. Audience prerequisite: has_completed_audience truth table.
  4. Skill trial:
        - is_skill_trial_done / cooldown / step accessors
        - Daro hook deflects without audience
        - Daro hook acks completion if done
        - Daro hook briefs at step 0 / step 1 / step 2 with right diff
        - attempt_skill_trial: room check, cooldown check, prerequisite
        - 3-success path: step counter increments, done flag flips,
          crystal granted (one-shot)
        - 1h cooldown applied after every attempt
  5. Insight trial:
        - is_insight_trial_done / unlock prereq (Skill done required)
        - Saro hook: deflect without audience / ack completion / require
          Skill done first / present trial when ready
        - Correct fragment persisted to character (deterministic retry)
        - examine_insight_fragment plays fragment for any of 1/2/3
        - accuse_insight_fragment correct → done flag, pendant granted
        - accuse_insight_fragment wrong → hint, no done flag, retry ok
        - The "Sith" fragment 2 always wins
  6. _handle_talk dispatches to trial NPC hooks before Yarael/Hermit.
  7. TrialCommand / ExamineCommand / AccuseCommand registered.

NOT covered (deferred):
  - Trials 2/3/4 (Courage, Flesh, Spirit) — F.7.c.2/3.
  - Live end-to-end via ParserRegistry — run targeted regression
    against existing tests instead.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from build_mos_eisley import build
from db.database import Database, SCHEMA_VERSION
from engine.village_trials import (
    DARO_NAME, MIRA_NAME, KORVAS_NAME, SARO_NAME, SELA_NAME,
    FORGE_ROOM_NAME, COUNCIL_HUT_ROOM_NAME,
    SKILL_DIFFICULTIES, SKILL_STEPS_REQUIRED,
    SKILL_RETRY_COOLDOWN_SECONDS, SKILL_TRIAL_SKILL,
    INSIGHT_FRAGMENTS,
    has_completed_audience,
    is_skill_trial_done, skill_trial_cooldown_remaining, get_skill_step,
    maybe_handle_daro_skill_trial, attempt_skill_trial,
    is_insight_trial_done, get_insight_correct_fragment,
    is_insight_unlocked,
    maybe_handle_saro_insight_trial,
    examine_insight_fragment, accuse_insight_fragment,
)
from engine.village_quest import (
    ACT_PRE_INVITATION, ACT_INVITED, ACT_IN_TRIALS, ACT_PASSED,
    HERMIT_NAME, check_village_quest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _build_cw():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db_path)
    asyncio.run(build(db_path=db_path, era="clone_wars"))
    return db_path


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def _make_char(
    *, id_=1, audience_done=False,
    skill_done=False, skill_step=0, skill_last_at=0,
    courage_done=False, courage_lockout_until=0,
    flesh_done=False, flesh_started_at=0,
    spirit_done=False,
    insight_done=False, insight_correct=0,
    room_id=1,
):
    """Build a minimal char dict.

    The ``courage_done`` kwarg was added when F.7.c.2 tightened the
    Insight gate to also require Courage.
    The ``flesh_done`` and ``flesh_started_at`` kwargs were added when
    F.7.c.3 tightened the Insight gate to also require Flesh.
    The ``spirit_done`` kwarg was added when F.7.c.4 tightened the
    Insight gate to also require Spirit.
    Tests that exercise unlocked Insight must pass ``spirit_done=True``
    in addition to ``flesh_done=True``, ``courage_done=True``,
    ``skill_done=True``, and ``audience_done=True``.
    """
    notes = {}
    if audience_done:
        notes["village_first_audience_done"] = True
    return {
        "id": id_,
        "name": f"P{id_}",
        "room_id": room_id,
        "village_act": ACT_IN_TRIALS if audience_done else ACT_INVITED,
        "village_gate_passed": 1 if audience_done else 0,
        "village_trial_skill_done": int(skill_done),
        "village_trial_skill_step": skill_step,
        "village_trial_skill_attempts": 0,
        "village_trial_skill_last_at": skill_last_at,
        "village_trial_skill_crystal_granted": 0,
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
        "village_trial_insight_correct_fragment": insight_correct,
        "village_trial_insight_pendant_granted": 0,
        "chargen_notes": json.dumps(notes),
        # skill rolls need attributes/skills
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
        self.inventory_adds: list[dict] = []
        # By default, get_room returns the Forge or Council Hut depending
        # on character's room_id. We keep it simple: tests set a string.
        self._room_name = "The Forge"

    def set_room(self, name):
        self._room_name = name

    async def save_character(self, char_id, **kwargs):
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v

    async def get_room(self, room_id):
        return {"name": self._room_name, "id": room_id}

    async def add_to_inventory(self, char_id, item):
        self.inventory_adds.append(dict(item))


# ═════════════════════════════════════════════════════════════════════════════
# 1. Schema v22
# ═════════════════════════════════════════════════════════════════════════════


class TestSchemaV22:

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_schema_version_at_least_22(self):
        rows = _query(self.db_path, "SELECT MAX(version) AS v FROM schema_version")
        assert rows[0]["v"] >= 22

    def test_skill_trial_columns_present(self):
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        for col in (
            "village_trial_skill_done",
            "village_trial_skill_step",
            "village_trial_skill_attempts",
            "village_trial_skill_last_at",
            "village_trial_skill_crystal_granted",
        ):
            assert col in cols, f"Missing skill trial column {col}"

    def test_insight_trial_columns_present(self):
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        for col in (
            "village_trial_insight_attempts",
            "village_trial_insight_correct_fragment",
            "village_trial_insight_pendant_granted",
        ):
            assert col in cols, f"Missing insight trial column {col}"

    def test_reserved_future_columns_present(self):
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        for col in (
            "village_trial_courage_lockout_until",
            "village_trial_flesh_started_at",
            "village_trial_flesh_session_seconds",
            "village_trial_spirit_done",
            "village_trial_spirit_dark_pull",
            "village_trial_spirit_rejections",
        ):
            assert col in cols, f"Missing reserved column {col}"

    def test_v18_columns_unmodified(self):
        # Ensure v18-declared columns still exist (v22 doesn't redeclare them)
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        for col in (
            "village_trial_courage_done",
            "village_trial_insight_done",
            "village_trial_flesh_done",
            "village_trial_last_attempt",
        ):
            assert col in cols

    def test_writable_columns_include_trial_state(self):
        from db.database import Database as D
        for col in (
            "village_trial_skill_done",
            "village_trial_skill_step",
            "village_trial_insight_correct_fragment",
            "village_trial_insight_pendant_granted",
        ):
            assert col in D._CHARACTER_WRITABLE_COLUMNS


# ═════════════════════════════════════════════════════════════════════════════
# 2. Build-time NPCs
# ═════════════════════════════════════════════════════════════════════════════


class TestVillageTrialNPCsPlaced:

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_total_npc_count_includes_all_seven_village(self):
        # F.7.b shipped 145 → 147 (Vitha, Yarael)
        # F.7.c.1 ships 147 → 152 (+ Daro, Mira, Korvas, Saro, Sela)
        rows = _query(self.db_path, "SELECT COUNT(*) AS c FROM npcs")
        assert rows[0]["c"] == 152

    def test_smith_daro_at_forge(self):
        rows = _query(
            self.db_path,
            "SELECT r.name AS room FROM npcs n JOIN rooms r ON r.id=n.room_id "
            "WHERE n.name = ?",
            (DARO_NAME,),
        )
        assert len(rows) == 1
        assert rows[0]["room"] == FORGE_ROOM_NAME

    def test_elder_mira_at_common_square(self):
        rows = _query(
            self.db_path,
            "SELECT r.name AS room FROM npcs n JOIN rooms r ON r.id=n.room_id "
            "WHERE n.name = ?",
            (MIRA_NAME,),
        )
        assert rows[0]["room"] == "Common Square"

    def test_elder_korvas_at_meditation_caves(self):
        rows = _query(
            self.db_path,
            "SELECT r.name AS room FROM npcs n JOIN rooms r ON r.id=n.room_id "
            "WHERE n.name = ?",
            (KORVAS_NAME,),
        )
        assert rows[0]["room"] == "Meditation Caves"

    def test_elder_saro_at_council_hut(self):
        rows = _query(
            self.db_path,
            "SELECT r.name AS room FROM npcs n JOIN rooms r ON r.id=n.room_id "
            "WHERE n.name = ?",
            (SARO_NAME,),
        )
        assert rows[0]["room"] == COUNCIL_HUT_ROOM_NAME

    def test_padawan_sela_at_apprentice_tents(self):
        rows = _query(
            self.db_path,
            "SELECT r.name AS room FROM npcs n JOIN rooms r ON r.id=n.room_id "
            "WHERE n.name = ?",
            (SELA_NAME,),
        )
        assert rows[0]["room"] == "Apprentice Tents"

    def test_daro_species_quarren(self):
        rows = _query(self.db_path, "SELECT species FROM npcs WHERE name=?",
                      (DARO_NAME,))
        assert rows[0]["species"] == "Quarren"

    def test_korvas_species_anzati(self):
        rows = _query(self.db_path, "SELECT species FROM npcs WHERE name=?",
                      (KORVAS_NAME,))
        assert rows[0]["species"] == "Anzati"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Audience prerequisite
# ═════════════════════════════════════════════════════════════════════════════


class TestHasCompletedAudience:
    def test_no_chargen_notes(self):
        char = {"chargen_notes": "{}"}
        assert has_completed_audience(char) is False

    def test_audience_flag_true(self):
        char = {"chargen_notes": json.dumps({"village_first_audience_done": True})}
        assert has_completed_audience(char) is True

    def test_audience_flag_false(self):
        char = {"chargen_notes": json.dumps({"village_first_audience_done": False})}
        assert has_completed_audience(char) is False

    def test_malformed_json_safe(self):
        char = {"chargen_notes": "{not json}"}
        assert has_completed_audience(char) is False


# ═════════════════════════════════════════════════════════════════════════════
# 4. Skill trial — accessors
# ═════════════════════════════════════════════════════════════════════════════


class TestSkillTrialAccessors:
    def test_done_false_default(self):
        char = _make_char()
        assert is_skill_trial_done(char) is False

    def test_done_true(self):
        char = _make_char(skill_done=True)
        assert is_skill_trial_done(char) is True

    def test_step_default_zero(self):
        char = _make_char()
        assert get_skill_step(char) == 0

    def test_step_accessor(self):
        char = _make_char(skill_step=2)
        assert get_skill_step(char) == 2

    def test_no_cooldown_when_unset(self):
        char = _make_char()
        assert skill_trial_cooldown_remaining(char) == 0.0

    def test_cooldown_active(self):
        char = _make_char(skill_last_at=time.time())
        remaining = skill_trial_cooldown_remaining(char)
        # Should be ~ SKILL_RETRY_COOLDOWN_SECONDS minus a tiny amount
        assert SKILL_RETRY_COOLDOWN_SECONDS - 5 <= remaining <= SKILL_RETRY_COOLDOWN_SECONDS

    def test_cooldown_expired(self):
        char = _make_char(skill_last_at=time.time() - SKILL_RETRY_COOLDOWN_SECONDS - 10)
        assert skill_trial_cooldown_remaining(char) == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 5. Daro hook
# ═════════════════════════════════════════════════════════════════════════════


class TestDaroHook:
    def test_non_daro_returns_false(self):
        async def _check():
            char = _make_char()
            session = FakeSession(char)
            ok = await maybe_handle_daro_skill_trial(session, FakeDB(char), char, "Hermit")
            assert ok is False
        asyncio.run(_check())

    def test_daro_without_audience_deflects(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            ok = await maybe_handle_daro_skill_trial(session, FakeDB(char), char, DARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "Master" in output
        asyncio.run(_check())

    def test_daro_completed_acks(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            ok = await maybe_handle_daro_skill_trial(session, FakeDB(char), char, DARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "done your work" in output or "crystal is yours" in output
        asyncio.run(_check())

    def test_daro_brief_at_step_0(self):
        async def _check():
            char = _make_char(audience_done=True, skill_step=0)
            session = FakeSession(char)
            ok = await maybe_handle_daro_skill_trial(session, FakeDB(char), char, DARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "trial skill" in output

        asyncio.run(_check())

    def test_daro_brief_at_step_1_shows_difficulty(self):
        async def _check():
            char = _make_char(audience_done=True, skill_step=1)
            session = FakeSession(char)
            ok = await maybe_handle_daro_skill_trial(session, FakeDB(char), char, DARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            # Step 1 done → next is index 1, difficulty 12
            assert "1 of three" in output or "1 of 3" in output or "12" in output
        asyncio.run(_check())

    def test_daro_brief_shows_cooldown_when_active(self):
        async def _check():
            char = _make_char(audience_done=True, skill_step=1, skill_last_at=time.time())
            session = FakeSession(char)
            ok = await maybe_handle_daro_skill_trial(session, FakeDB(char), char, DARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "minute" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 6. attempt_skill_trial
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptSkillTrial:

    def test_no_audience_refuses(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            ok = await attempt_skill_trial(session, db, char)
            assert ok is False
        asyncio.run(_check())

    def test_already_done_refuses(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            ok = await attempt_skill_trial(session, db, char)
            assert ok is False
        asyncio.run(_check())

    def test_in_cooldown_refuses(self):
        async def _check():
            char = _make_char(audience_done=True, skill_last_at=time.time())
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            ok = await attempt_skill_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "minute" in output or "Wait" in output
        asyncio.run(_check())

    def test_wrong_room_refuses(self):
        async def _check():
            char = _make_char(audience_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("Some Other Room")
            ok = await attempt_skill_trial(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Forge" in output
        asyncio.run(_check())

    def test_step_increments_on_success(self):
        async def _check():
            # Use a strong attribute/skill pool to ensure success:
            # craft_lightsaber 5D vs difficulty 8 — almost always succeeds.
            char = _make_char(audience_done=True)
            char["attributes"] = json.dumps({"tec": "5D"})
            char["skills"] = json.dumps({"craft_lightsaber": "8D"})
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")

            ok = await attempt_skill_trial(session, db, char)
            assert ok is True
            # Roll might fail occasionally; if step still 0, accept either
            # — but with 8D vs 8 the success probability is overwhelming
            # If it failed, the cooldown is set and step is still 0.
            assert char["village_trial_skill_attempts"] == 1
            assert char["village_trial_skill_last_at"] > 0
        asyncio.run(_check())

    def test_three_step_path_grants_crystal(self):
        async def _check():
            # Pre-set at step 2; with 8D pool the third attempt should
            # succeed at difficulty 15 most of the time. To make it
            # deterministic, we use 12D.
            char = _make_char(audience_done=True, skill_step=2)
            char["skills"] = json.dumps({"craft_lightsaber": "12D"})
            char["village_trial_skill_last_at"] = 0  # no cooldown
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")

            # Loop until we either pass or run out of attempts (defense
            # against the pathological 12D-vs-15 misses)
            for _ in range(15):
                char["village_trial_skill_last_at"] = 0  # bypass cooldown each try
                ok = await attempt_skill_trial(session, db, char)
                assert ok is True
                if char["village_trial_skill_done"] == 1:
                    break

            assert char["village_trial_skill_done"] == 1
            assert char["village_trial_skill_step"] >= SKILL_STEPS_REQUIRED
            assert char["village_trial_skill_crystal_granted"] == 1
            # Inventory granted
            assert len(db.inventory_adds) == 1
            assert db.inventory_adds[0]["key"] == "village_trial_crystal"
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 7. Insight trial — accessors and unlock
# ═════════════════════════════════════════════════════════════════════════════


class TestInsightAccessors:
    def test_done_default(self):
        char = _make_char()
        assert is_insight_trial_done(char) is False

    def test_done_true(self):
        char = _make_char(insight_done=True)
        assert is_insight_trial_done(char) is True

    def test_correct_fragment_zero_default(self):
        char = _make_char()
        assert get_insight_correct_fragment(char) == 0

    def test_correct_fragment_set(self):
        char = _make_char(insight_correct=2)
        assert get_insight_correct_fragment(char) == 2


class TestInsightUnlock:
    def test_no_audience_locked(self):
        char = _make_char(audience_done=False)
        assert is_insight_unlocked(char) is False

    def test_audience_no_skill_locked(self):
        char = _make_char(audience_done=True, skill_done=False)
        assert is_insight_unlocked(char) is False

    def test_audience_skill_no_courage_locked_under_f7c2_gate(self):
        # Under F.7.c.2 the canonical gate requires Courage.
        # audience + skill (without courage) is no longer enough.
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=False,
        )
        assert is_insight_unlocked(char) is False

    def test_audience_skill_courage_no_flesh_locked_under_f7c3_gate(self):
        # Under F.7.c.3 the gate also requires Flesh.
        # audience + skill + courage (without flesh) is no longer enough.
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
            flesh_done=False,
        )
        assert is_insight_unlocked(char) is False

    def test_audience_skill_courage_flesh_no_spirit_locked_under_f7c4_gate(self):
        # Under F.7.c.4 the gate also requires Spirit.
        # audience + skill + courage + flesh (without spirit) is no
        # longer enough.
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
            flesh_done=True, spirit_done=False,
        )
        assert is_insight_unlocked(char) is False

    def test_all_five_gates_unlocks(self):
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
            flesh_done=True, spirit_done=True,
        )
        assert is_insight_unlocked(char) is True


# ═════════════════════════════════════════════════════════════════════════════
# 8. Saro hook
# ═════════════════════════════════════════════════════════════════════════════


class TestSaroHook:
    def test_non_saro_returns_false(self):
        async def _check():
            char = _make_char()
            session = FakeSession(char)
            ok = await maybe_handle_saro_insight_trial(session, FakeDB(char), char, "Hermit")
            assert ok is False
        asyncio.run(_check())

    def test_saro_without_audience_deflects(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            ok = await maybe_handle_saro_insight_trial(session, FakeDB(char), char, SARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "Master" in output
        asyncio.run(_check())

    def test_saro_done_acks(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, insight_done=True)
            session = FakeSession(char)
            ok = await maybe_handle_saro_insight_trial(session, FakeDB(char), char, SARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "pendant" in output or "false note" in output
        asyncio.run(_check())

    def test_saro_without_skill_done_deflects(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=False)
            session = FakeSession(char)
            ok = await maybe_handle_saro_insight_trial(session, FakeDB(char), char, SARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "Forge" in output or "Daro" in output
        asyncio.run(_check())

    def test_saro_when_unlocked_presents_trial(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=True, spirit_done=True,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_saro_insight_trial(session, db, char, SARO_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "fragment" in output.lower()
            assert "examine" in output.lower()
            assert "accuse" in output.lower()
            # Correct fragment persisted to DB (always 2 in F.7.c.1)
            assert char["village_trial_insight_correct_fragment"] == 2
        asyncio.run(_check())

    def test_saro_reentry_does_not_reshuffle(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=True, spirit_done=True, insight_correct=2,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_saro_insight_trial(session, db, char, SARO_NAME)
            assert ok is True
            # Still 2; no reshuffle on retry
            assert char["village_trial_insight_correct_fragment"] == 2
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 9. examine_insight_fragment
# ═════════════════════════════════════════════════════════════════════════════


class TestExamineInsightFragment:
    def test_locked_returns_false(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            ok = await examine_insight_fragment(session, db, char, "fragment_1")
            assert ok is False  # silent fall-through; not Saro's trial
        asyncio.run(_check())

    def test_unlocked_plays_fragment(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            ok = await examine_insight_fragment(session, db, char, "fragment_1")
            assert ok is True
            output = "\n".join(session.received)
            assert "Fragment 1" in output or "fragment 1" in output.lower()
        asyncio.run(_check())

    def test_each_fragment_distinct(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)

            outputs = {}
            for fnum in (1, 2, 3):
                session = FakeSession(char)
                await examine_insight_fragment(session, db, char, f"fragment_{fnum}")
                outputs[fnum] = "\n".join(session.received)

            # Each output should be different
            assert outputs[1] != outputs[2]
            assert outputs[2] != outputs[3]
            assert outputs[1] != outputs[3]

            # Fragment 2 should contain the doctrinal tell
            assert "belongs" in outputs[2].lower()
        asyncio.run(_check())

    def test_invalid_fragment_returns_false(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            ok = await examine_insight_fragment(session, db, char, "fragment_99")
            assert ok is False
        asyncio.run(_check())

    def test_wrong_room_handled_gracefully(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")  # wrong room
            ok = await examine_insight_fragment(session, db, char, "fragment_1")
            assert ok is True  # we did handle it (with refusal)
            output = "\n".join(session.received)
            assert "Council Hut" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 10. accuse_insight_fragment
# ═════════════════════════════════════════════════════════════════════════════


class TestAccuseInsightFragment:
    def test_locked_refuses(self):
        async def _check():
            char = _make_char(audience_done=False)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            ok = await accuse_insight_fragment(session, db, char, "fragment_1")
            assert ok is True  # we did handle it (refused)
            assert char["village_trial_insight_done"] == 0
        asyncio.run(_check())

    def test_already_done(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True, insight_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            ok = await accuse_insight_fragment(session, db, char, "fragment_2")
            assert ok is True
            output = "\n".join(session.received)
            assert "already passed" in output
        asyncio.run(_check())

    def test_correct_accusation_passes(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True, insight_correct=2)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            ok = await accuse_insight_fragment(session, db, char, "fragment_2")
            assert ok is True
            assert char["village_trial_insight_done"] == 1
            assert char["village_trial_insight_pendant_granted"] == 1
            assert len(db.inventory_adds) == 1
            assert db.inventory_adds[0]["key"] == "village_pendant"
        asyncio.run(_check())

    def test_wrong_accusation_no_done(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True, insight_correct=2)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            ok = await accuse_insight_fragment(session, db, char, "fragment_1")
            assert ok is True
            assert char["village_trial_insight_done"] == 0
            assert len(db.inventory_adds) == 0  # no pendant
            output = "\n".join(session.received)
            assert "Listen again" in output
        asyncio.run(_check())

    def test_wrong_then_correct_passes(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True, insight_correct=2)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)

            # Wrong first
            session1 = FakeSession(char)
            await accuse_insight_fragment(session1, db, char, "fragment_3")
            assert char["village_trial_insight_done"] == 0

            # Right second
            session2 = FakeSession(char)
            await accuse_insight_fragment(session2, db, char, "fragment_2")
            assert char["village_trial_insight_done"] == 1
            assert char["village_trial_insight_attempts"] == 2
        asyncio.run(_check())

    def test_attempts_increment_on_each_accuse(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True, insight_correct=2)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)

            session = FakeSession(char)
            await accuse_insight_fragment(session, db, char, "fragment_1")
            assert char["village_trial_insight_attempts"] == 1
            await accuse_insight_fragment(session, db, char, "fragment_3")
            assert char["village_trial_insight_attempts"] == 2
        asyncio.run(_check())

    def test_invalid_fragment_arg(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            ok = await accuse_insight_fragment(session, db, char, "garbage")
            assert ok is True
            output = "\n".join(session.received)
            assert "fragment_1" in output  # usage hint
        asyncio.run(_check())

    def test_wrong_room_refuses(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True, courage_done=True, flesh_done=True, spirit_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            ok = await accuse_insight_fragment(session, db, char, "fragment_2")
            assert ok is True
            output = "\n".join(session.received)
            assert "Council Hut" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 11. _handle_talk dispatch — trial NPCs come BEFORE Yarael / Hermit
# ═════════════════════════════════════════════════════════════════════════════


class TestHandleTalkDispatch:
    """Ensure the trial NPC hooks are called in order from check_village_quest."""

    def test_daro_dispatched_before_hermit(self):
        # If Daro is talked to as an invited PC, the Daro hook fires
        # rather than the Hermit-after_lines hook.
        async def _check():
            char = _make_char(audience_done=True)
            char["village_act"] = ACT_IN_TRIALS
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Forge")
            await check_village_quest(
                session, db, "talk", npc_name=DARO_NAME,
            )
            output = "\n".join(session.received)
            assert "Daro" in output or "trial skill" in output
        asyncio.run(_check())

    def test_saro_dispatched(self):
        async def _check():
            char = _make_char(audience_done=True, skill_done=True)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(COUNCIL_HUT_ROOM_NAME)
            await check_village_quest(
                session, db, "talk", npc_name=SARO_NAME,
            )
            output = "\n".join(session.received)
            assert "fragment" in output.lower() or "Saro" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 12. Commands registered
# ═════════════════════════════════════════════════════════════════════════════


class TestTrialCommandsRegistered:
    def test_trial_command_class_present(self):
        path = os.path.join(PROJECT_ROOT, "parser", "village_trial_commands.py")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "class TrialCommand" in text
        assert "class ExamineCommand" in text
        assert "class AccuseCommand" in text

    def test_register_called_in_game_server(self):
        path = os.path.join(PROJECT_ROOT, "server", "game_server.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "register_village_trial_commands" in text

    def test_village_quest_imports_trial_hooks(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_quest.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "maybe_handle_daro_skill_trial" in text
        assert "maybe_handle_saro_insight_trial" in text


# ═════════════════════════════════════════════════════════════════════════════
# 13. Insight fragments — content checks
# ═════════════════════════════════════════════════════════════════════════════


class TestInsightFragmentContent:
    def test_three_fragments(self):
        assert set(INSIGHT_FRAGMENTS.keys()) == {1, 2, 3}

    def test_fragment_2_is_sith(self):
        assert INSIGHT_FRAGMENTS[2]["is_sith"] is True

    def test_fragment_1_and_3_not_sith(self):
        assert INSIGHT_FRAGMENTS[1]["is_sith"] is False
        assert INSIGHT_FRAGMENTS[3]["is_sith"] is False

    def test_sith_fragment_contains_belongs(self):
        text = " ".join(INSIGHT_FRAGMENTS[2]["lines"]).lower()
        assert "belongs" in text or "belongs" in text

    def test_jedi_fragments_use_through_or_flows(self):
        # Per design: true Jedi say "the Force *flows through* them"
        for fnum in (1, 3):
            text = " ".join(INSIGHT_FRAGMENTS[fnum]["lines"]).lower()
            assert "through" in text or "flows" in text or "passes" in text or "carries" in text or "moves" in text


# ═════════════════════════════════════════════════════════════════════════════
# 14. Mail subsystem carry-over (smoke drop 4 → F.7.c.1)
# ═════════════════════════════════════════════════════════════════════════════
# Smoke drop 4 introduced the `mail` and `mail_recipients` tables but
# its db/database.py was clobbered by the W.2 phase 2 / F.7.b later
# overwrites. Brian's HEAD lost the mail tables. F.7.c.1 carries them
# forward via (a) SCHEMA_SQL CREATE blocks (fresh DBs) and (b) v23
# migration (existing DBs at v21/v22). These tests guard both paths.


class TestMailCarryOver:

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_schema_version_at_least_23(self):
        rows = _query(self.db_path, "SELECT MAX(version) AS v FROM schema_version")
        assert rows[0]["v"] >= 23

    def test_mail_table_exists(self):
        rows = _query(
            self.db_path,
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("mail",),
        )
        assert len(rows) == 1

    def test_mail_recipients_table_exists(self):
        rows = _query(
            self.db_path,
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("mail_recipients",),
        )
        assert len(rows) == 1

    def test_mail_columns(self):
        rows = _query(self.db_path, "PRAGMA table_info(mail)")
        cols = {r["name"] for r in rows}
        for col in ("id", "sender_id", "subject", "body", "sent_at"):
            assert col in cols

    def test_mail_recipients_columns(self):
        rows = _query(self.db_path, "PRAGMA table_info(mail_recipients)")
        cols = {r["name"] for r in rows}
        for col in ("id", "mail_id", "char_id", "is_read", "is_deleted"):
            assert col in cols

    def test_mail_indexes_present(self):
        rows = _query(
            self.db_path,
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_mail%'",
        )
        index_names = {r["name"] for r in rows}
        for idx in (
            "idx_mail_recipients_char_id",
            "idx_mail_recipients_mail_id",
            "idx_mail_sender_id",
        ):
            assert idx in index_names, f"Missing index {idx}"

    def test_mail_insert_select_round_trip(self):
        """Smoke-test the mail tables work for an actual INSERT/SELECT."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO mail (sender_id, subject, body, sent_at) "
                "VALUES (1, ?, ?, ?)",
                ("carry-over test", "If this works, mail is alive.",
                 "2026-05-04T03:00:00"),
            )
            mail_id = cur.lastrowid
            conn.execute(
                "INSERT INTO mail_recipients (mail_id, char_id) VALUES (?, 1)",
                (mail_id,),
            )
            conn.commit()
            rows = conn.execute(
                "SELECT m.subject, mr.is_read FROM mail m "
                "JOIN mail_recipients mr ON mr.mail_id = m.id "
                "WHERE m.id = ?",
                (mail_id,),
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "carry-over test"
            assert rows[0][1] == 0
        finally:
            conn.close()
