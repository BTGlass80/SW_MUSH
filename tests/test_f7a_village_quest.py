# -*- coding: utf-8 -*-
"""
tests/test_f7a_village_quest.py — Village quest engine, Acts 1–2 entry.

Closes the loop on Drop F.7.a (May 3 2026): proves the Village quest
state machine fires Step 1 (Hermit invitation) and Step 2 (arrival at
village_outer_watch), the writable-columns set has been extended to
support Village writes, and the wilderness writer now emits
properties.slug on landmark rooms.

What this test suite validates
==============================

  1. Read helpers (get_village_state, current_step, is_in_quest,
     has_completed) reflect the column state correctly.
  2. State transitions (deliver_invitation, enter_trials) are
     idempotent and write through to the DB.
  3. Step 1 trigger: talking to the Hermit when force-sign-eligible
     fires deliver_invitation; talking to him under threshold does
     NOT fire; talking to other NPCs is a no-op; re-talking after
     fire is a no-op.
  4. Step 2 trigger: entering village_outer_watch while at act 1
     fires enter_trials; entering it under any other state is a
     no-op; entering other rooms is a no-op.
  5. The wilderness writer emits properties.slug on landmark rooms
     after a fresh CW build.
  6. The CHARACTER_WRITABLE_COLUMNS set includes the Village columns
     so save_character() works.
  7. Defensive: a fresh post-build DB lookup of village_act on a
     character whose row hasn't been mutated returns 0.
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
from db.database import Database
from engine.force_signs import FORCE_SIGNS_FOR_INVITATION
from engine.village_quest import (
    ACT_PRE_INVITATION, ACT_INVITED, ACT_IN_TRIALS, ACT_PASSED,
    HERMIT_NAME, VILLAGE_OUTER_WATCH_SLUG,
    check_village_quest,
    current_step,
    deliver_invitation,
    enter_trials,
    get_village_state,
    has_completed,
    is_in_quest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles
# ─────────────────────────────────────────────────────────────────────────────


class _FakeSession:
    """Minimal session double for hook tests."""
    def __init__(self, character):
        self.character = character
        self.lines_sent = []

    async def send_line(self, text):
        self.lines_sent.append(text)


class _FakeDb:
    """Minimal Database double — only the methods village_quest uses.

    The real save_character validates against _CHARACTER_WRITABLE_COLUMNS.
    The fake mirrors that contract so tests catch column-name regressions.
    """
    _WRITABLE = frozenset({
        "village_act", "village_act_unlocked_at",
        "village_trial_courage_done", "village_trial_insight_done",
        "village_trial_flesh_done", "village_trial_last_attempt",
        "force_signs_accumulated", "force_predisposition",
        "play_time_seconds", "wound_state", "wound_clear_at",
    })

    def __init__(self):
        self.saved = []  # list of (char_id, fields_dict) tuples
        self.rooms = {}  # room_id -> dict with 'properties' (json string)

    async def save_character(self, char_id: int, **fields):
        bad = set(fields) - self._WRITABLE
        if bad:
            raise ValueError(f"FakeDb.save_character: disallowed columns: {bad}")
        self.saved.append((char_id, dict(fields)))

    class _DbInner:
        def __init__(self, parent):
            self._parent = parent

        async def execute_fetchall(self, sql, params=()):
            # Only stub: SELECT properties FROM rooms WHERE id = ? LIMIT 1
            if "rooms" in sql and "properties" in sql:
                room_id = params[0]
                room = self._parent.rooms.get(room_id)
                if not room:
                    return []
                # Mimic row interface
                return [{"properties": room.get("properties", "{}")}]
            return []

    @property
    def _db(self):
        return _FakeDb._DbInner(self)


def _new_char(act=0, signs=0, char_id=42, name="Test PC"):
    return {
        "id": char_id,
        "name": name,
        "village_act": act,
        "village_act_unlocked_at": 0,
        "village_trial_courage_done": 0,
        "village_trial_insight_done": 0,
        "village_trial_flesh_done": 0,
        "village_trial_last_attempt": 0,
        "force_signs_accumulated": signs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Read helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestReadHelpers:
    def test_get_village_state_pre_invitation(self):
        char = _new_char()
        s = get_village_state(char)
        assert s["act"] == ACT_PRE_INVITATION
        assert s["act_label"] == "pre_invitation"
        assert s["current_step"] == 1
        assert s["trials_completed"] == 0

    def test_get_village_state_invited(self):
        char = _new_char(act=ACT_INVITED)
        s = get_village_state(char)
        assert s["act"] == ACT_INVITED
        assert s["act_label"] == "invited"
        assert s["current_step"] == 2

    def test_get_village_state_in_trials(self):
        char = _new_char(act=ACT_IN_TRIALS)
        s = get_village_state(char)
        assert s["act"] == ACT_IN_TRIALS
        assert s["act_label"] == "in_trials"
        # First unfinished trial step is reported
        assert s["current_step"] in (6, 7, 9, 10)

    def test_get_village_state_passed(self):
        char = _new_char(act=ACT_PASSED)
        s = get_village_state(char)
        assert s["act"] == ACT_PASSED
        assert s["act_label"] == "passed"
        assert s["current_step"] is None

    def test_is_in_quest_pre(self):
        assert is_in_quest(_new_char(act=ACT_PRE_INVITATION)) is False

    def test_is_in_quest_invited(self):
        assert is_in_quest(_new_char(act=ACT_INVITED)) is True

    def test_has_completed_only_at_passed(self):
        assert has_completed(_new_char(act=ACT_PRE_INVITATION)) is False
        assert has_completed(_new_char(act=ACT_INVITED)) is False
        assert has_completed(_new_char(act=ACT_IN_TRIALS)) is False
        assert has_completed(_new_char(act=ACT_PASSED)) is True

    def test_current_step_in_trials_progresses_with_completion(self):
        # All trials done -> current step is 10 (Choice)
        char = _new_char(act=ACT_IN_TRIALS)
        char["village_trial_courage_done"] = 1
        char["village_trial_flesh_done"] = 1
        char["village_trial_insight_done"] = 1
        assert current_step(char) == 10


# ─────────────────────────────────────────────────────────────────────────────
# 2. State transitions
# ─────────────────────────────────────────────────────────────────────────────


class TestDeliverInvitation:
    def test_fires_when_act_zero(self):
        char = _new_char(act=ACT_PRE_INVITATION)
        db = _FakeDb()
        before = time.time()
        result = asyncio.run(deliver_invitation(char, db))
        after = time.time()
        assert result is True
        assert char["village_act"] == ACT_INVITED
        assert before <= char["village_act_unlocked_at"] <= after
        # DB write happened
        assert len(db.saved) == 1
        assert db.saved[0][1]["village_act"] == ACT_INVITED

    def test_idempotent_at_invited(self):
        char = _new_char(act=ACT_INVITED)
        db = _FakeDb()
        result = asyncio.run(deliver_invitation(char, db))
        assert result is False
        assert char["village_act"] == ACT_INVITED  # unchanged
        assert len(db.saved) == 0

    def test_idempotent_at_higher_acts(self):
        for act in (ACT_IN_TRIALS, ACT_PASSED):
            char = _new_char(act=act)
            db = _FakeDb()
            result = asyncio.run(deliver_invitation(char, db))
            assert result is False
            assert char["village_act"] == act

    def test_writes_only_writable_columns(self):
        # The FakeDb's _WRITABLE set is a subset of the real one. If
        # deliver_invitation tries to write a column that's not in the
        # writable set, FakeDb.save_character raises ValueError. This
        # test catches the regression where a new column is added to
        # the engine without being added to the writable set.
        char = _new_char(act=ACT_PRE_INVITATION)
        db = _FakeDb()
        # No exception should be raised
        asyncio.run(deliver_invitation(char, db))


class TestEnterTrials:
    def test_fires_when_invited(self):
        char = _new_char(act=ACT_INVITED)
        db = _FakeDb()
        result = asyncio.run(enter_trials(char, db))
        assert result is True
        assert char["village_act"] == ACT_IN_TRIALS

    def test_no_op_when_pre_invitation(self):
        char = _new_char(act=ACT_PRE_INVITATION)
        db = _FakeDb()
        result = asyncio.run(enter_trials(char, db))
        assert result is False
        assert char["village_act"] == ACT_PRE_INVITATION

    def test_idempotent_at_in_trials(self):
        char = _new_char(act=ACT_IN_TRIALS)
        db = _FakeDb()
        result = asyncio.run(enter_trials(char, db))
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Step 1 trigger (talk-to-Hermit)
# ─────────────────────────────────────────────────────────────────────────────


class TestStep1HermitTalk:
    def test_eligible_player_triggers_invitation(self):
        char = _new_char(act=ACT_PRE_INVITATION, signs=FORCE_SIGNS_FOR_INVITATION)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "talk", npc_name=HERMIT_NAME,
        ))
        assert char["village_act"] == ACT_INVITED
        assert any("invited" in line.lower() or "invitation" in line.lower()
                   for line in session.lines_sent)

    def test_under_threshold_does_not_trigger(self):
        char = _new_char(act=ACT_PRE_INVITATION, signs=FORCE_SIGNS_FOR_INVITATION - 1)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "talk", npc_name=HERMIT_NAME,
        ))
        assert char["village_act"] == ACT_PRE_INVITATION
        assert session.lines_sent == []

    def test_other_npc_does_not_trigger(self):
        char = _new_char(act=ACT_PRE_INVITATION, signs=FORCE_SIGNS_FOR_INVITATION)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "talk", npc_name="Vela Niree",
        ))
        assert char["village_act"] == ACT_PRE_INVITATION

    def test_already_invited_does_not_re_fire(self):
        char = _new_char(act=ACT_INVITED, signs=FORCE_SIGNS_FOR_INVITATION + 5)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "talk", npc_name=HERMIT_NAME,
        ))
        # Already at ACT_INVITED — no further mutation
        assert char["village_act"] == ACT_INVITED
        assert session.lines_sent == []

    def test_case_insensitive_hermit_match(self):
        char = _new_char(act=ACT_PRE_INVITATION, signs=FORCE_SIGNS_FOR_INVITATION)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "talk", npc_name="THE HERMIT",
        ))
        assert char["village_act"] == ACT_INVITED

    def test_missing_npc_name_is_safe(self):
        # Empty string and missing key both are no-ops, not crashes.
        char = _new_char()
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(session, db, "talk"))
        asyncio.run(check_village_quest(session, db, "talk", npc_name=""))
        assert char["village_act"] == ACT_PRE_INVITATION


# ─────────────────────────────────────────────────────────────────────────────
# 4. Step 2 trigger (room_entered village_outer_watch)
# ─────────────────────────────────────────────────────────────────────────────


class TestStep2Arrival:
    def test_arrival_at_outer_watch_when_invited(self):
        char = _new_char(act=ACT_INVITED)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "room_entered",
            room_slug=VILLAGE_OUTER_WATCH_SLUG, room_id=999,
        ))
        assert char["village_act"] == ACT_IN_TRIALS

    def test_arrival_pre_invitation_does_not_fire(self):
        char = _new_char(act=ACT_PRE_INVITATION)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "room_entered",
            room_slug=VILLAGE_OUTER_WATCH_SLUG,
        ))
        assert char["village_act"] == ACT_PRE_INVITATION

    def test_other_room_no_trigger(self):
        char = _new_char(act=ACT_INVITED)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "room_entered",
            room_slug="hermit_hut",
        ))
        assert char["village_act"] == ACT_INVITED

    def test_slug_lookup_via_room_id(self):
        # When caller doesn't pass slug, village_quest looks it up
        # from room_id via the rooms table.
        char = _new_char(act=ACT_INVITED)
        session = _FakeSession(char)
        db = _FakeDb()
        # Fixture: room 555 has slug village_outer_watch
        db.rooms[555] = {"properties": json.dumps({"slug": VILLAGE_OUTER_WATCH_SLUG})}
        asyncio.run(check_village_quest(
            session, db, "room_entered", room_id=555,
        ))
        assert char["village_act"] == ACT_IN_TRIALS

    def test_idempotent_at_in_trials(self):
        char = _new_char(act=ACT_IN_TRIALS)
        session = _FakeSession(char)
        db = _FakeDb()
        asyncio.run(check_village_quest(
            session, db, "room_entered",
            room_slug=VILLAGE_OUTER_WATCH_SLUG,
        ))
        assert char["village_act"] == ACT_IN_TRIALS  # unchanged


# ─────────────────────────────────────────────────────────────────────────────
# 5. Wilderness writer emits properties.slug
# ─────────────────────────────────────────────────────────────────────────────


class TestWildernessWriterEmitsSlug:
    """A fresh CW build must produce wilderness rooms with properties.slug
    set to the YAML landmark id."""

    @classmethod
    def setup_class(cls):
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(cls.db_path)
        asyncio.run(build(db_path=cls.db_path, era="clone_wars"))

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def _slugs(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, properties FROM rooms "
            "WHERE wilderness_region_id IS NOT NULL"
        ).fetchall()
        conn.close()
        out = {}
        for r in rows:
            try:
                props = json.loads(r["properties"])
                out[r["name"]] = props.get("slug")
            except Exception:
                out[r["name"]] = None
        return out

    def test_hermit_hut_has_slug(self):
        slugs = self._slugs()
        assert slugs.get("Hermit's Hut") == "hermit_hut"

    def test_village_outer_watch_has_slug(self):
        slugs = self._slugs()
        # The room name has special chars; key by checking the slug VALUE.
        assert "village_outer_watch" in slugs.values()

    def test_anchor_stones_has_slug(self):
        slugs = self._slugs()
        assert "dune_sea_anchor_stones" in slugs.values()

    def test_all_landmarks_have_slugs(self):
        slugs = self._slugs()
        unset = {name: s for name, s in slugs.items() if not s}
        assert not unset, (
            f"All wilderness landmark rooms must have properties.slug set; "
            f"these don't: {unset}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Database writable-columns set includes Village columns
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabaseWritableColumns:
    """The CHARACTER_WRITABLE_COLUMNS set must include the village_*
    columns or save_character() will raise."""

    def test_village_act_writable(self):
        assert "village_act" in Database._CHARACTER_WRITABLE_COLUMNS

    def test_village_act_unlocked_at_writable(self):
        assert "village_act_unlocked_at" in Database._CHARACTER_WRITABLE_COLUMNS

    def test_all_village_columns_writable(self):
        required = {
            "village_act", "village_act_unlocked_at",
            "village_trial_courage_done", "village_trial_insight_done",
            "village_trial_flesh_done", "village_trial_last_attempt",
        }
        missing = required - Database._CHARACTER_WRITABLE_COLUMNS
        assert not missing, f"Missing from writable set: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. End-to-end DB integration
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndDb:
    """Integration: a real Database, deliver_invitation persisting through."""

    def test_deliver_invitation_persists_to_real_db(self, tmp_path):
        async def _run():
            db = Database(":memory:")
            await db.connect()
            await db.initialize()
            # Create a minimal account+character row to drive the test.
            # Only fields that matter: id (we'll capture from insert),
            # village_act starts at 0 by default.
            await db._db.execute(
                "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                ("test_acct_f7a", "x"),
            )
            await db._db.commit()
            rows = await db._db.execute_fetchall(
                "SELECT id FROM accounts WHERE username = 'test_acct_f7a'"
            )
            account_id = rows[0]["id"]
            await db._db.execute(
                "INSERT INTO characters (account_id, name, room_id, is_active) "
                "VALUES (?, ?, ?, 1)",
                (account_id, "TestPC", 1),
            )
            await db._db.commit()
            rows = await db._db.execute_fetchall(
                "SELECT id, village_act FROM characters WHERE name = 'TestPC'"
            )
            char_id = rows[0]["id"]
            assert rows[0]["village_act"] == 0  # default

            # Build minimal char dict + fire the transition
            char = {"id": char_id, "name": "TestPC", "village_act": 0}
            fired = await deliver_invitation(char, db)
            assert fired is True

            # Read back from DB
            rows = await db._db.execute_fetchall(
                "SELECT village_act, village_act_unlocked_at "
                "FROM characters WHERE id = ?", (char_id,),
            )
            assert rows[0]["village_act"] == ACT_INVITED
            assert rows[0]["village_act_unlocked_at"] > 0

            await db.close()

        asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# 8. Module self-docs / source guards
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleSelfDocs:
    def test_engine_module_exists(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_quest.py")
        assert os.path.exists(path)

    def test_npc_commands_imports_check_village_quest(self):
        path = os.path.join(PROJECT_ROOT, "parser", "npc_commands.py")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "from engine.village_quest import check_village_quest" in text

    def test_builtin_commands_imports_check_village_quest(self):
        path = os.path.join(PROJECT_ROOT, "parser", "builtin_commands.py")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "from engine.village_quest import check_village_quest" in text

    def test_wilderness_writer_emits_slug(self):
        path = os.path.join(PROJECT_ROOT, "engine", "wilderness_writer.py")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "props.setdefault(\"slug\", lm.id)" in text
