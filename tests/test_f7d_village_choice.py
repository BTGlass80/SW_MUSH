# -*- coding: utf-8 -*-
"""
tests/test_f7d_village_choice.py — F.7.d — Village quest Step 10:
                                    the Path A/B/C choice.

Closes Step 10 of the Village quest (Act 3): one irreversible commit
between three paths after all five trials are complete.

What this suite validates:

  1. Schema v25: village_choice_completed + village_chosen_path
     present in writable set + migration.
  2. Accessors:
        - is_choice_completed / get_chosen_path
        - is_path_choice_unlocked (= Insight done)
        - is_path_c_locked
        - has_chargen_flag (defensive JSON read)
  3. Path-menu rendering:
        - Normal menu shows A and B (and the "final" warning)
        - Path-C-locked variant shows only C with the design §7.3
          sadness-not-anger framing
  4. Yarael-in-Master's-Chamber hook
     (maybe_handle_yarael_path_choice):
        - Non-Yarael → False
        - Wrong room (not Master's Chamber) → False
        - Choice already committed → distinct ack per path
        - Insight not done → False (audience hook handles)
        - Insight done, choice not yet committed → emit menu
  5. attempt_choose_path guards:
        - Choice already committed → refuse with "road is set"
        - Insight not done → refuse
        - No-arg + unlocked → emit menu
        - Invalid path arg → usage error
        - Path A blocked when Path C locked
        - Path B blocked when Path C locked
        - Path C blocked when not locked
  6. Path commits — side effects:
        Path A:
          - village_choice_completed=1, village_chosen_path='a'
          - force_sensitive=1
          - chargen_notes: jedi_path_unlocked, village_chosen_path_a,
            village_trial_lightsaber_construction_pending
          - jedi_order org join attempted
          - teleport to jedi_temple_main_gate attempted
        Path B:
          - village_choice_completed=1, village_chosen_path='b'
          - force_sensitive=1
          - chargen_notes: jedi_path_unlocked, village_chosen_path_b
          - independent org join + adjust_rep(+50) attempted
          - teleport to village_common_square attempted
        Path C:
          - village_choice_completed=1, village_chosen_path='c'
          - force_sensitive=1
          - chargen_notes: dark_path_unlocked,
            village_chosen_path_c, dark_contact_freq
          - NOT jedi_path_unlocked
          - NO org join
          - teleport to dune_sea_anchor_stones attempted
  7. chargen_notes preservation across commits (existing flags
     survive).
  8. Org/teleport API graceful when missing (best-effort, doesn't
     block the commit).
  9. Parser command (PathCommand):
        - help text mentions all three paths
        - `path` no-arg
        - `path a|b|c` full form
        - just-letter form (`a`, `b`, `c`)
        - invalid sub-arg refuses
  10. _handle_talk dispatch wires Yarael-Path hook in Master's Chamber.
  11. Module wiring: village_quest imports the hook;
      village_choice exports the surface; constants match design.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.village_choice import (
    MASTERS_CHAMBER_ROOM_NAME,
    PATH_A_DROP_SLUG, PATH_B_DROP_SLUG, PATH_C_DROP_SLUG,
    PATH_A, PATH_B, PATH_C, VALID_PATHS,
    is_choice_completed, get_chosen_path,
    is_path_choice_unlocked, is_path_c_locked,
    has_chargen_flag,
    maybe_handle_yarael_path_choice,
    attempt_choose_path,
)
from engine.village_trials import YARAEL_NAME
from engine.village_quest import (
    ACT_PRE_INVITATION, ACT_INVITED, ACT_IN_TRIALS,
    HERMIT_NAME, check_village_quest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_char(
    *, id_=1,
    audience_done=False,
    skill_done=False, courage_done=False, flesh_done=False,
    spirit_done=False, spirit_path_c_locked=False,
    insight_done=False,
    choice_completed=False, chosen_path="",
    chargen_extra=None,
    room_id=1, faction="", force_sensitive=False,
):
    """Build a minimal char dict for Path-choice tests."""
    notes = {}
    if audience_done:
        notes["village_first_audience_done"] = True
    if chargen_extra:
        notes.update(chargen_extra)
    return {
        "id": id_,
        "name": f"P{id_}",
        "faction": faction,
        "room_id": room_id,
        "force_sensitive": int(force_sensitive),
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
        "village_trial_spirit_dark_pull": 0,
        "village_trial_spirit_rejections": 0,
        "village_trial_spirit_turn": 0,
        "village_trial_spirit_path_c_locked": int(spirit_path_c_locked),
        "village_trial_insight_done": int(insight_done),
        "village_trial_insight_attempts": 0,
        "village_trial_insight_correct_fragment": 0,
        "village_trial_insight_pendant_granted": 0,
        "village_choice_completed": int(choice_completed),
        "village_chosen_path": chosen_path,
        "chargen_notes": json.dumps(notes),
        "attributes": json.dumps({"dex": "4D", "tec": "4D"}),
        "skills": json.dumps({"craft_lightsaber": "5D"}),
    }


def _ready_for_choice(**extra):
    """Char with all five trials done — ready to commit a path."""
    return _make_char(
        audience_done=True, skill_done=True, courage_done=True,
        flesh_done=True, spirit_done=True, insight_done=True,
        **extra,
    )


class FakeSession:
    def __init__(self, character):
        self.character = character
        self.received: list[str] = []

    async def send_line(self, text):
        self.received.append(text)


class FakeDB:
    """Minimal DB stub that exposes the parts of the surface
    village_choice.py touches."""
    def __init__(self, char):
        self._char = char
        self.saves: list[dict] = []
        self._room_name = MASTERS_CHAMBER_ROOM_NAME
        self._orgs = {
            "jedi_order": {"id": 100, "code": "jedi_order"},
            "independent": {"id": 101, "code": "independent"},
        }
        self.joined: list[tuple[int, int]] = []
        self.rep_changes: list[tuple[int, str, int]] = []
        # If True, get_room_by_slug resolves the canonical Path slugs;
        # if False, _teleport falls back and emits the engine-note.
        self.slug_resolves: bool = True
        self._slug_to_room_id = {
            PATH_A_DROP_SLUG: 200,
            PATH_B_DROP_SLUG: 201,
            PATH_C_DROP_SLUG: 202,
        }

    def set_room(self, name):
        self._room_name = name

    async def save_character(self, char_id, **kwargs):
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v

    async def get_room(self, room_id):
        return {"name": self._room_name, "id": room_id}

    async def get_organization(self, code):
        return self._orgs.get(code)

    async def join_organization(self, char_id, org_id, specialization=""):
        self.joined.append((char_id, org_id))
        return True

    async def adjust_rep(self, char_id, org_code, delta):
        self.rep_changes.append((char_id, org_code, delta))

    async def get_room_by_slug(self, slug):
        if not self.slug_resolves:
            return None
        rid = self._slug_to_room_id.get(slug)
        if rid is None:
            return None
        return {"id": rid, "slug": slug}


class MinimalFakeDB:
    """Stripped-down DB that omits get_organization / join /
    adjust_rep / get_room_by_slug entirely. Exercises the
    best-effort code paths in village_choice."""
    def __init__(self, char):
        self._char = char
        self.saves: list[dict] = []
        self._room_name = MASTERS_CHAMBER_ROOM_NAME

    def set_room(self, name):
        self._room_name = name

    async def save_character(self, char_id, **kwargs):
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v

    async def get_room(self, room_id):
        return {"name": self._room_name, "id": room_id}


# ═════════════════════════════════════════════════════════════════════════════
# 1. Schema
# ═════════════════════════════════════════════════════════════════════════════


class TestPathChoiceSchema:

    def test_v25_cols_in_writable_set(self):
        from db.database import Database
        cols = Database._CHARACTER_WRITABLE_COLUMNS
        assert "village_choice_completed" in cols
        assert "village_chosen_path" in cols

    def test_v25_migration_text_includes_new_cols(self):
        path = os.path.join(PROJECT_ROOT, "db", "database.py")
        src = open(path, "r", encoding="utf-8").read()
        # The migration block needs both cols
        assert "village_choice_completed" in src
        assert "village_chosen_path" in src

    def test_schema_version_at_least_25(self):
        from db.database import SCHEMA_VERSION
        assert SCHEMA_VERSION >= 25


# ═════════════════════════════════════════════════════════════════════════════
# 2. Accessors
# ═════════════════════════════════════════════════════════════════════════════


class TestPathChoiceAccessors:

    def test_is_choice_completed_default_false(self):
        char = _make_char()
        assert is_choice_completed(char) is False

    def test_is_choice_completed_true(self):
        char = _make_char(choice_completed=True)
        assert is_choice_completed(char) is True

    def test_get_chosen_path_default_empty(self):
        char = _make_char()
        assert get_chosen_path(char) == ""

    def test_get_chosen_path_lowercased(self):
        char = _make_char(chosen_path="A")
        assert get_chosen_path(char) == "a"

    def test_get_chosen_path_strips_whitespace(self):
        char = _make_char(chosen_path="  b  ")
        assert get_chosen_path(char) == "b"

    def test_is_path_choice_unlocked_false_without_insight(self):
        char = _make_char()
        assert is_path_choice_unlocked(char) is False

    def test_is_path_choice_unlocked_true_with_insight(self):
        char = _make_char(insight_done=True)
        assert is_path_choice_unlocked(char) is True

    def test_is_path_c_locked_default_false(self):
        char = _make_char()
        assert is_path_c_locked(char) is False

    def test_is_path_c_locked_true(self):
        char = _make_char(spirit_path_c_locked=True)
        assert is_path_c_locked(char) is True

    def test_has_chargen_flag_present(self):
        char = _make_char(chargen_extra={"foo": True})
        assert has_chargen_flag(char, "foo") is True

    def test_has_chargen_flag_absent(self):
        char = _make_char()
        assert has_chargen_flag(char, "foo") is False

    def test_has_chargen_flag_handles_malformed_json(self):
        char = _make_char()
        char["chargen_notes"] = "{not valid json"
        assert has_chargen_flag(char, "foo") is False

    def test_has_chargen_flag_handles_dict_notes(self):
        char = _make_char()
        char["chargen_notes"] = {"foo": True}
        assert has_chargen_flag(char, "foo") is True


# ═════════════════════════════════════════════════════════════════════════════
# 3. Constants match design
# ═════════════════════════════════════════════════════════════════════════════


class TestPathChoiceConstants:

    def test_path_constants_distinct(self):
        assert PATH_A == "a"
        assert PATH_B == "b"
        assert PATH_C == "c"
        assert set(VALID_PATHS) == {"a", "b", "c"}

    def test_master_chamber_room_name(self):
        assert MASTERS_CHAMBER_ROOM_NAME == "Master's Chamber"

    def test_path_drop_slugs_canonical(self):
        # Per F.4c rename map. Design doc lists pre-rename names; we
        # use the post-rename canonical world-data slugs.
        assert PATH_A_DROP_SLUG == "jedi_temple_main_gate"
        assert PATH_B_DROP_SLUG == "village_common_square"
        assert PATH_C_DROP_SLUG == "dune_sea_anchor_stones"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Yarael-in-Master's-Chamber hook
# ═════════════════════════════════════════════════════════════════════════════


class TestYaraelPathChoiceHook:

    def test_non_yarael_returns_false(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, "Random NPC",
            )
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_wrong_room_returns_false(self):
        # Yarael in the Sealed Sanctum should NOT be intercepted by
        # the Path hook — the Spirit hook handles that.
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room("The Sealed Sanctum")
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, YARAEL_NAME,
            )
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_insight_not_done_returns_false(self):
        # The audience hook handles pre-Insight Yarael talks. The
        # Path hook only intercepts after Insight is complete.
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=True, spirit_done=True, insight_done=False,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, YARAEL_NAME,
            )
            assert ok is False
            assert session.received == []
        asyncio.run(_check())

    def test_choice_completed_path_a_acks_with_coruscant(self):
        async def _check():
            char = _ready_for_choice(
                choice_completed=True, chosen_path=PATH_A,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "Coruscant" in output or "Order" in output
        asyncio.run(_check())

    def test_choice_completed_path_b_acks_with_village(self):
        async def _check():
            char = _ready_for_choice(
                choice_completed=True, chosen_path=PATH_B,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "Village" in output or "Force is yours" in output
        asyncio.run(_check())

    def test_choice_completed_path_c_acks_with_dismissal(self):
        async def _check():
            char = _ready_for_choice(
                choice_completed=True, chosen_path=PATH_C,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Path C ack is the "you should not have come back" framing
            assert "Go" in output or "should not" in output.lower()
        asyncio.run(_check())

    def test_unlocked_uncommitted_emits_menu(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            # Normal menu shows A and B
            assert "path a" in output.lower()
            assert "path b" in output.lower()
            assert "final" in output.lower()
        asyncio.run(_check())

    def test_path_c_locked_emits_only_path_c(self):
        async def _check():
            char = _ready_for_choice(spirit_path_c_locked=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "path c" in output.lower()
            # Path A/B suppressed in menu (but allow ANSI-coloured
            # heading words containing "path" — check for explicit
            # menu rows)
            assert "path a   " not in output.lower()
            assert "path b   " not in output.lower()
            # Sadness-not-anger framing
            assert "sadness" in output.lower() or "not anger" in output.lower()
        asyncio.run(_check())

    def test_case_insensitive_npc_name(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_path_choice(
                session, db, char, YARAEL_NAME.upper(),
            )
            assert ok is True
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 5. attempt_choose_path — guards
# ═════════════════════════════════════════════════════════════════════════════


class TestAttemptChoosePathGuards:

    def test_choice_already_completed_refuses(self):
        async def _check():
            char = _ready_for_choice(
                choice_completed=True, chosen_path=PATH_A,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="b")
            assert ok is False
            output = "\n".join(session.received)
            assert "already chosen" in output.lower() or "set" in output.lower()
        asyncio.run(_check())

    def test_insight_not_done_refuses(self):
        async def _check():
            char = _make_char(
                audience_done=True, skill_done=True, courage_done=True,
                flesh_done=True, spirit_done=True, insight_done=False,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char)
            assert ok is False
            output = "\n".join(session.received)
            assert "Insight" in output or "five trials" in output.lower()
        asyncio.run(_check())

    def test_no_arg_unlocked_emits_menu(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char)
            assert ok is True
            output = "\n".join(session.received)
            assert "path a" in output.lower()
            assert "path b" in output.lower()
        asyncio.run(_check())

    def test_invalid_path_arg_refuses(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="z")
            assert ok is False
            output = "\n".join(session.received)
            assert "Usage" in output or "a|b|c" in output
        asyncio.run(_check())

    def test_path_a_blocked_when_path_c_locked(self):
        async def _check():
            char = _ready_for_choice(spirit_path_c_locked=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="a")
            assert ok is False
            assert is_choice_completed(char) is False
            output = "\n".join(session.received)
            assert "Order will not have you" in output or "closed Path A" in output
        asyncio.run(_check())

    def test_path_b_blocked_when_path_c_locked(self):
        async def _check():
            char = _ready_for_choice(spirit_path_c_locked=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="b")
            assert ok is False
            assert is_choice_completed(char) is False
            output = "\n".join(session.received)
            assert "Village will not keep you" in output or "closed Path B" in output
        asyncio.run(_check())

    def test_path_c_blocked_when_not_locked(self):
        async def _check():
            char = _ready_for_choice(spirit_path_c_locked=False)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="c")
            assert ok is False
            assert is_choice_completed(char) is False
            output = "\n".join(session.received)
            assert "not open" in output.lower() or "dark whispers" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 6. Path A — commit side effects
# ═════════════════════════════════════════════════════════════════════════════


class TestPathACommit:

    def test_path_a_sets_columns_and_force_sensitive(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="a")
            assert ok is True
            assert is_choice_completed(char) is True
            assert get_chosen_path(char) == "a"
            assert int(char.get("force_sensitive") or 0) == 1
        asyncio.run(_check())

    def test_path_a_sets_chargen_flags(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="a")
            assert has_chargen_flag(char, "jedi_path_unlocked")
            assert has_chargen_flag(char, "village_chosen_path_a")
            assert has_chargen_flag(char,
                "village_trial_lightsaber_construction_pending")
            # Path-B/C flags absent
            assert not has_chargen_flag(char, "village_chosen_path_b")
            assert not has_chargen_flag(char, "village_chosen_path_c")
            assert not has_chargen_flag(char, "dark_path_unlocked")
        asyncio.run(_check())

    def test_path_a_joins_jedi_order(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="a")
            # joined list contains (char_id, jedi_order_org_id=100)
            assert (char["id"], 100) in db.joined
        asyncio.run(_check())

    def test_path_a_teleports_when_slug_resolves(self):
        async def _check():
            char = _ready_for_choice(room_id=999)
            session = FakeSession(char)
            db = FakeDB(char)
            db.slug_resolves = True
            await attempt_choose_path(session, db, char, path="a")
            assert char["room_id"] == 200  # PATH_A_DROP_SLUG resolved id
        asyncio.run(_check())

    def test_path_a_engine_note_when_slug_unresolved(self):
        async def _check():
            char = _ready_for_choice(room_id=999)
            session = FakeSession(char)
            db = FakeDB(char)
            db.slug_resolves = False
            ok = await attempt_choose_path(session, db, char, path="a")
            assert ok is True
            # Choice still committed
            assert is_choice_completed(char)
            # Player stays in the original room
            assert char["room_id"] == 999
            output = "\n".join(session.received)
            assert "engine note" in output.lower() or "remain" in output.lower()
        asyncio.run(_check())

    def test_path_a_works_with_minimal_db_no_org_api(self):
        # If org-join API is absent, the commit still succeeds and
        # all flags are set.
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = MinimalFakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="a")
            assert ok is True
            assert is_choice_completed(char)
            assert get_chosen_path(char) == "a"
            assert has_chargen_flag(char, "jedi_path_unlocked")
        asyncio.run(_check())

    def test_path_a_narration_mentions_mace_windu(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="a")
            output = "\n".join(session.received)
            assert "Mace Windu" in output
            assert "Jedi Order" in output or "Path A" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 7. Path B — commit side effects
# ═════════════════════════════════════════════════════════════════════════════


class TestPathBCommit:

    def test_path_b_sets_columns_and_force_sensitive(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="b")
            assert ok is True
            assert is_choice_completed(char)
            assert get_chosen_path(char) == "b"
            assert int(char.get("force_sensitive") or 0) == 1
        asyncio.run(_check())

    def test_path_b_sets_chargen_flags(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="b")
            assert has_chargen_flag(char, "jedi_path_unlocked")
            assert has_chargen_flag(char, "village_chosen_path_b")
            # Path-A/C flags absent
            assert not has_chargen_flag(char, "village_chosen_path_a")
            assert not has_chargen_flag(char, "village_chosen_path_c")
            assert not has_chargen_flag(char,
                "village_trial_lightsaber_construction_pending")
            assert not has_chargen_flag(char, "dark_path_unlocked")
        asyncio.run(_check())

    def test_path_b_joins_independent_with_rep_50(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="b")
            assert (char["id"], 101) in db.joined
            assert (char["id"], "independent", 50) in db.rep_changes
        asyncio.run(_check())

    def test_path_b_teleports_to_common_square(self):
        async def _check():
            char = _ready_for_choice(room_id=999)
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="b")
            assert char["room_id"] == 201  # PATH_B_DROP_SLUG resolved id
        asyncio.run(_check())

    def test_path_b_does_not_consume_crystal(self):
        # Path B keeps the crystal uncommitted. Crystal grant flag is
        # stored on village_trial_skill_crystal_granted column.
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="b")
            # Crystal still granted, not consumed
            assert int(char["village_trial_skill_crystal_granted"]) == 1
            # No "crystal consumed" save
            assert not any(
                "village_trial_skill_crystal_granted" in s and
                s["village_trial_skill_crystal_granted"] == 0
                for s in db.saves
            )
        asyncio.run(_check())

    def test_path_b_narration_mentions_village(self):
        async def _check():
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="b")
            output = "\n".join(session.received)
            assert "Village" in output
            assert "Path B" in output or "Independent" in output
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 8. Path C — commit side effects
# ═════════════════════════════════════════════════════════════════════════════


class TestPathCCommit:

    def test_path_c_sets_columns_and_force_sensitive(self):
        async def _check():
            char = _ready_for_choice(spirit_path_c_locked=True)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await attempt_choose_path(session, db, char, path="c")
            assert ok is True
            assert is_choice_completed(char)
            assert get_chosen_path(char) == "c"
            assert int(char.get("force_sensitive") or 0) == 1
        asyncio.run(_check())

    def test_path_c_sets_dark_flags_not_jedi(self):
        # Per design §7.3: NOT jedi_path_unlocked.
        async def _check():
            char = _ready_for_choice(spirit_path_c_locked=True)
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="c")
            assert has_chargen_flag(char, "dark_path_unlocked")
            assert has_chargen_flag(char, "village_chosen_path_c")
            assert has_chargen_flag(char, "dark_contact_freq")
            # CRITICAL: jedi_path_unlocked NOT set
            assert not has_chargen_flag(char, "jedi_path_unlocked")
            # Other path flags absent
            assert not has_chargen_flag(char, "village_chosen_path_a")
            assert not has_chargen_flag(char, "village_chosen_path_b")
        asyncio.run(_check())

    def test_path_c_does_not_join_any_org(self):
        async def _check():
            char = _ready_for_choice(spirit_path_c_locked=True)
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="c")
            # No org joins — Path C is exiled
            assert db.joined == []
            assert db.rep_changes == []
        asyncio.run(_check())

    def test_path_c_teleports_to_anchor_stones(self):
        async def _check():
            char = _ready_for_choice(
                spirit_path_c_locked=True, room_id=999,
            )
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="c")
            assert char["room_id"] == 202
        asyncio.run(_check())

    def test_path_c_narration_mentions_dark_whispers(self):
        async def _check():
            char = _ready_for_choice(spirit_path_c_locked=True)
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="c")
            output = "\n".join(session.received)
            assert "dark whispers" in output.lower() or "Path C" in output
            # Comlink frequency mentioned
            assert "frequency" in output.lower() or "comlink" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 9. chargen_notes preservation
# ═════════════════════════════════════════════════════════════════════════════


class TestChargenNotesPreservation:

    def test_path_a_preserves_existing_flags(self):
        # If the player already has other chargen_notes keys set,
        # the Path A flags should not clobber them.
        async def _check():
            char = _ready_for_choice(chargen_extra={
                "village_first_audience_done": True,
                "village_trial_flesh_strength_taught": True,
                "some_other_marker": "preserved-value",
            })
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="a")
            notes = json.loads(char["chargen_notes"])
            # Old flags survive
            assert notes.get("village_first_audience_done") is True
            assert notes.get("village_trial_flesh_strength_taught") is True
            assert notes.get("some_other_marker") == "preserved-value"
            # New flags added
            assert notes.get("jedi_path_unlocked") is True
            assert notes.get("village_chosen_path_a") is True
        asyncio.run(_check())

    def test_path_b_preserves_existing_flags(self):
        async def _check():
            char = _ready_for_choice(chargen_extra={
                "village_first_audience_done": True,
                "preexisting": "value",
            })
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="b")
            notes = json.loads(char["chargen_notes"])
            assert notes.get("village_first_audience_done") is True
            assert notes.get("preexisting") == "value"
            assert notes.get("village_chosen_path_b") is True
        asyncio.run(_check())

    def test_path_c_preserves_existing_flags(self):
        async def _check():
            char = _ready_for_choice(
                spirit_path_c_locked=True,
                chargen_extra={
                    "village_first_audience_done": True,
                    "preexisting": "value",
                },
            )
            session = FakeSession(char)
            db = FakeDB(char)
            await attempt_choose_path(session, db, char, path="c")
            notes = json.loads(char["chargen_notes"])
            assert notes.get("village_first_audience_done") is True
            assert notes.get("preexisting") == "value"
            assert notes.get("village_chosen_path_c") is True
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 10. _handle_talk dispatch
# ═════════════════════════════════════════════════════════════════════════════


class TestHandleTalkDispatchPathChoice:

    def test_yarael_in_masters_chamber_after_insight_dispatched(self):
        async def _check():
            char = _ready_for_choice(room_id=42)
            session = FakeSession(char)
            db = FakeDB(char)
            db.set_room(MASTERS_CHAMBER_ROOM_NAME)
            await check_village_quest(
                session, db, "talk", npc_name=YARAEL_NAME,
            )
            output = "\n".join(session.received)
            # Path menu emitted
            assert "path a" in output.lower()
            assert "path b" in output.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 11. Parser command (PathCommand)
# ═════════════════════════════════════════════════════════════════════════════


class TestPathCommandWiring:

    def test_help_text_mentions_all_paths(self):
        from parser.village_trial_commands import PathCommand
        cmd = PathCommand()
        assert "path a" in cmd.help_text.lower()
        assert "path b" in cmd.help_text.lower()
        assert "path c" in cmd.help_text.lower()
        assert "final" in cmd.help_text.lower()

    def test_path_command_registered(self):
        from parser.village_trial_commands import (
            PathCommand, register_village_trial_commands,
        )
        # Build a stub registry
        class _Reg:
            def __init__(self):
                self.added = []
            def register(self, cmd):
                self.added.append(cmd)
        reg = _Reg()
        register_village_trial_commands(reg)
        keys = {c.key for c in reg.added}
        assert "path" in keys
        # And TrialCommand still there
        assert "trial" in keys

    def test_path_no_arg_dispatches_menu(self):
        async def _check():
            from parser.village_trial_commands import PathCommand
            from parser.commands import CommandContext
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="path",
                command="path",
                args="",
                args_list=[],
                db=db,
            )
            await PathCommand().execute(ctx)
            output = "\n".join(session.received)
            assert "path a" in output.lower()
        asyncio.run(_check())

    def test_path_a_full_form_dispatches_commit(self):
        async def _check():
            from parser.village_trial_commands import PathCommand
            from parser.commands import CommandContext
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="path a",
                command="path",
                args="a",
                args_list=["a"],
                db=db,
            )
            await PathCommand().execute(ctx)
            assert is_choice_completed(char)
            assert get_chosen_path(char) == "a"
        asyncio.run(_check())

    def test_path_b_full_form_dispatches_commit(self):
        async def _check():
            from parser.village_trial_commands import PathCommand
            from parser.commands import CommandContext
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="path b",
                command="path",
                args="b",
                args_list=["b"],
                db=db,
            )
            await PathCommand().execute(ctx)
            assert is_choice_completed(char)
            assert get_chosen_path(char) == "b"
        asyncio.run(_check())

    def test_path_c_full_form_dispatches_commit(self):
        async def _check():
            from parser.village_trial_commands import PathCommand
            from parser.commands import CommandContext
            char = _ready_for_choice(spirit_path_c_locked=True)
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="path c",
                command="path",
                args="c",
                args_list=["c"],
                db=db,
            )
            await PathCommand().execute(ctx)
            assert is_choice_completed(char)
            assert get_chosen_path(char) == "c"
        asyncio.run(_check())

    def test_path_uppercase_a_works(self):
        # Casefold via parser sub.lower(); this exercises that path.
        async def _check():
            from parser.village_trial_commands import PathCommand
            from parser.commands import CommandContext
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="path A",
                command="path",
                args="A",
                args_list=["A"],
                db=db,
            )
            await PathCommand().execute(ctx)
            assert is_choice_completed(char)
            assert get_chosen_path(char) == "a"
        asyncio.run(_check())

    def test_path_invalid_subarg_refuses(self):
        async def _check():
            from parser.village_trial_commands import PathCommand
            from parser.commands import CommandContext
            char = _ready_for_choice()
            session = FakeSession(char)
            db = FakeDB(char)

            ctx = CommandContext(
                session=session,
                raw_input="path z",
                command="path",
                args="z",
                args_list=["z"],
                db=db,
            )
            await PathCommand().execute(ctx)
            output = "\n".join(session.received)
            assert "Usage" in output
            assert is_choice_completed(char) is False
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 12. Module wiring
# ═════════════════════════════════════════════════════════════════════════════


class TestModuleWiring:

    def test_village_quest_imports_path_choice_hook(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_quest.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "maybe_handle_yarael_path_choice" in src

    def test_village_choice_exposes_surface(self):
        from engine import village_choice
        assert hasattr(village_choice, "is_choice_completed")
        assert hasattr(village_choice, "get_chosen_path")
        assert hasattr(village_choice, "is_path_choice_unlocked")
        assert hasattr(village_choice, "is_path_c_locked")
        assert hasattr(village_choice, "has_chargen_flag")
        assert hasattr(village_choice, "maybe_handle_yarael_path_choice")
        assert hasattr(village_choice, "attempt_choose_path")

    def test_parser_imports_path_command(self):
        path = os.path.join(PROJECT_ROOT, "parser",
                            "village_trial_commands.py")
        src = open(path, "r", encoding="utf-8").read()
        assert "class PathCommand" in src
        assert "attempt_choose_path" in src

    def test_path_command_in_registration_list(self):
        path = os.path.join(PROJECT_ROOT, "parser",
                            "village_trial_commands.py")
        src = open(path, "r", encoding="utf-8").read()
        # The registrar list should mention PathCommand()
        assert "PathCommand()" in src
