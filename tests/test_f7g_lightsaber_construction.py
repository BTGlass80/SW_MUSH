# -*- coding: utf-8 -*-
"""
tests/test_f7g_lightsaber_construction.py — F.7.g — Path A
Apprentice Forge scene.

Validates ``engine/lightsaber_construction.py`` and its wire-up at
``engine/village_choice.py::_commit_path_a``.

Coverage:

  1. Constants and dice-string parsing.
  2. ``ensure_skill_floor`` skill-bump helper:
       - No skill → set to floor
       - Below floor → bumped to floor
       - At floor → no-op
       - Above floor → no-op
       - Pip-fractional comparisons (3D+2 < 4D, 4D+0 == 4D, 4D+1 > 4D)
       - Defensive against malformed JSON / non-string skills field
  3. Marker accessors:
       - is_construction_pending: false default; true with marker;
         false once done
       - is_construction_complete: false default; true with done marker
       - is_construction_failed: false default; true with failed marker
       - Defensive against malformed chargen_notes
  4. ``construct_lightsaber`` runtime:
       - Pending marker absent → False, no side effects
       - Done marker set → False, no side effects (idempotent)
       - Pending + crystal present → full success path
         (crystal removed, lightsaber added, skill floor enforced,
         pending cleared, done set, narration emitted)
       - Pending + missing crystal → False, failure marker set,
         no narration, no skill bump
       - add_to_inventory raises → crystal still consumed, marker
         flipped, scene continues (defensive)
       - skill bump idempotent on second commit
       - Already-4D character: skill not bumped, scene still runs
  5. Wire-up in Path A:
       - source-level: village_choice imports + calls
       - behavioural: with crystal in inventory, Path A commit fires
         the scene (lightsaber added, marker flipped)
       - behavioural: without crystal, Path A still commits
         (failure marker set; teleport happens; flags are still set)
       - behavioural: Path B and Path C do NOT trigger construction
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

from engine.lightsaber_construction import (
    LIGHTSABER_CRAFT_SKILL_FLOOR_DICE,
    CRYSTAL_ITEM_KEY, LIGHTSABER_ITEM_KEY,
    MARKER_PENDING, MARKER_DONE, MARKER_FAILED,
    is_construction_pending, is_construction_complete,
    is_construction_failed,
    ensure_skill_floor,
    construct_lightsaber,
    _parse_dice_str, _format_dice,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_char(*, skills=None, chargen_notes=None, inventory=None):
    """Minimal char dict with a JSON skills field and a chargen_notes
    field that the helpers can read. ``inventory`` is held by
    FakeDB; the char dict itself doesn't carry it."""
    return {
        "id": 1,
        "name": "T",
        "skills": json.dumps(skills) if skills is not None else "{}",
        "chargen_notes": json.dumps(chargen_notes) if chargen_notes is not None else "{}",
    }


class FakeSession:
    def __init__(self, character):
        self.character = character
        self.received: list[str] = []

    async def send_line(self, text):
        self.received.append(text)


class FakeDB:
    """Stub DB exposing remove_from_inventory / add_to_inventory /
    save_character. ``inventory`` is the list of item-key strings;
    add_to_inventory pushes the full item dict in.
    """
    def __init__(self, char, inventory=None):
        self._char = char
        self._inv: list[dict] = []
        if inventory:
            for k in inventory:
                self._inv.append({"key": k, "name": k})
        self.removed: list[str] = []
        self.added: list[dict] = []
        self.saves: list[dict] = []
        self.fail_remove = False
        self.fail_add = False

    async def remove_from_inventory(self, char_id, key):
        if self.fail_remove:
            raise RuntimeError("simulated remove failure")
        for i, item in enumerate(self._inv):
            if item.get("key") == key:
                self._inv.pop(i)
                self.removed.append(key)
                return True
        return False

    async def add_to_inventory(self, char_id, item):
        if self.fail_add:
            raise RuntimeError("simulated add failure")
        self._inv.append(item)
        self.added.append(item)

    async def save_character(self, char_id, **kwargs):
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v

    def has_item(self, key):
        return any(i.get("key") == key for i in self._inv)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Dice-string parser
# ═════════════════════════════════════════════════════════════════════════════


class TestDiceParser:

    def test_simple_dice(self):
        assert _parse_dice_str("3D") == (3, 0)
        assert _parse_dice_str("4D") == (4, 0)
        assert _parse_dice_str("0D") == (0, 0)

    def test_dice_with_pips(self):
        assert _parse_dice_str("3D+1") == (3, 1)
        assert _parse_dice_str("3D+2") == (3, 2)
        assert _parse_dice_str("4D+0") == (4, 0)

    def test_lowercase_d(self):
        assert _parse_dice_str("3d") == (3, 0)
        assert _parse_dice_str("3d+1") == (3, 1)

    def test_with_spaces(self):
        assert _parse_dice_str(" 3D+1 ") == (3, 1)

    def test_leading_plus(self):
        assert _parse_dice_str("+3D+2") == (3, 2)

    def test_empty_or_none(self):
        assert _parse_dice_str("") == (0, 0)
        assert _parse_dice_str(None) == (0, 0)

    def test_malformed_returns_zero(self):
        assert _parse_dice_str("not dice") == (0, 0)
        assert _parse_dice_str("XD") == (0, 0)

    def test_bare_integer(self):
        # Some sheets store a bare int — treat as dice count.
        assert _parse_dice_str("3") == (3, 0)


class TestDiceFormat:

    def test_zero_pips_emits_simple_form(self):
        assert _format_dice(4, 0) == "4D"

    def test_with_pips(self):
        assert _format_dice(3, 2) == "3D+2"
        assert _format_dice(4, 1) == "4D+1"


# ═════════════════════════════════════════════════════════════════════════════
# 2. ensure_skill_floor
# ═════════════════════════════════════════════════════════════════════════════


class TestEnsureSkillFloor:

    def test_no_skill_sets_floor(self):
        char = _make_char(skills={})
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is True
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D"

    def test_below_floor_bumped(self):
        char = _make_char(skills={"craft_lightsaber": "3D"})
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is True
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D"

    def test_at_floor_no_change(self):
        char = _make_char(skills={"craft_lightsaber": "4D"})
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is False
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D"

    def test_above_floor_no_change(self):
        char = _make_char(skills={"craft_lightsaber": "5D"})
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is False
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "5D"

    def test_3d_plus_2_below_4d(self):
        # 3D+2 (= 11 pips) is below 4D (= 12 pips); should bump.
        char = _make_char(skills={"craft_lightsaber": "3D+2"})
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is True
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D"

    def test_4d_plus_1_above_4d(self):
        # 4D+1 (= 13 pips) is above 4D (= 12 pips); should NOT bump.
        char = _make_char(skills={"craft_lightsaber": "4D+1"})
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is False
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D+1"

    def test_other_skills_preserved(self):
        char = _make_char(skills={
            "craft_lightsaber": "2D",
            "blaster": "5D+1",
            "lightsaber": "3D",
        })
        ensure_skill_floor(char, "craft_lightsaber", 4)
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D"
        assert skills["blaster"] == "5D+1"
        assert skills["lightsaber"] == "3D"

    def test_malformed_skills_json_treated_empty(self):
        char = {"id": 1, "skills": "{not valid json"}
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is True  # treated as if no skill
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D"

    def test_no_skills_field(self):
        char = {"id": 1}  # no 'skills' key at all
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is True
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D"

    def test_skills_is_dict_not_string(self):
        # Defensive: if char['skills'] is already a dict (not JSON string).
        char = {"id": 1, "skills": {"craft_lightsaber": "3D"}}
        bumped = ensure_skill_floor(char, "craft_lightsaber", 4)
        assert bumped is True
        skills = json.loads(char["skills"])
        assert skills["craft_lightsaber"] == "4D"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Marker accessors
# ═════════════════════════════════════════════════════════════════════════════


class TestMarkerAccessors:

    def test_pending_default_false(self):
        assert is_construction_pending(_make_char()) is False

    def test_pending_true_when_set(self):
        char = _make_char(chargen_notes={MARKER_PENDING: True})
        assert is_construction_pending(char) is True

    def test_pending_false_once_done(self):
        # Even if pending is somehow still set, done supersedes.
        char = _make_char(chargen_notes={
            MARKER_PENDING: True,
            MARKER_DONE: True,
        })
        assert is_construction_pending(char) is False

    def test_complete_default_false(self):
        assert is_construction_complete(_make_char()) is False

    def test_complete_true_when_done(self):
        char = _make_char(chargen_notes={MARKER_DONE: True})
        assert is_construction_complete(char) is True

    def test_failed_default_false(self):
        assert is_construction_failed(_make_char()) is False

    def test_failed_true_when_set(self):
        char = _make_char(chargen_notes={MARKER_FAILED: True})
        assert is_construction_failed(char) is True

    def test_malformed_chargen_notes_defaults_false(self):
        char = {"id": 1, "chargen_notes": "{not valid json"}
        assert is_construction_pending(char) is False
        assert is_construction_complete(char) is False
        assert is_construction_failed(char) is False

    def test_chargen_notes_dict_not_string(self):
        char = {"id": 1, "chargen_notes": {MARKER_PENDING: True}}
        assert is_construction_pending(char) is True


# ═════════════════════════════════════════════════════════════════════════════
# 4. construct_lightsaber runtime
# ═════════════════════════════════════════════════════════════════════════════


class TestConstructLightsaber:

    def test_no_pending_marker_returns_false_no_side_effects(self):
        async def _check():
            char = _make_char(skills={"craft_lightsaber": "2D"})
            session = FakeSession(char)
            db = FakeDB(char, inventory=[CRYSTAL_ITEM_KEY])
            ok = await construct_lightsaber(session, db, char)
            assert ok is False
            assert db.removed == []
            assert db.added == []
            # Crystal still in inventory, skill not bumped, no narration
            assert db.has_item(CRYSTAL_ITEM_KEY)
            skills = json.loads(char["skills"])
            assert skills["craft_lightsaber"] == "2D"
            assert session.received == []
        asyncio.run(_check())

    def test_already_done_returns_false_idempotent(self):
        async def _check():
            char = _make_char(
                skills={"craft_lightsaber": "4D"},
                chargen_notes={MARKER_DONE: True, MARKER_PENDING: True},
            )
            session = FakeSession(char)
            db = FakeDB(char, inventory=[CRYSTAL_ITEM_KEY])
            ok = await construct_lightsaber(session, db, char)
            assert ok is False
            # Crystal NOT consumed (idempotent)
            assert db.has_item(CRYSTAL_ITEM_KEY)
            assert db.removed == []
            assert db.added == []
        asyncio.run(_check())

    def test_full_success_path(self):
        async def _check():
            char = _make_char(
                skills={"craft_lightsaber": "2D"},
                chargen_notes={MARKER_PENDING: True},
            )
            session = FakeSession(char)
            db = FakeDB(char, inventory=[CRYSTAL_ITEM_KEY])
            ok = await construct_lightsaber(session, db, char)
            assert ok is True
            # Crystal consumed
            assert not db.has_item(CRYSTAL_ITEM_KEY)
            assert db.removed == [CRYSTAL_ITEM_KEY]
            # Lightsaber granted
            assert any(
                i.get("key") == LIGHTSABER_ITEM_KEY for i in db.added
            )
            # Skill bumped to 4D
            skills = json.loads(char["skills"])
            assert skills["craft_lightsaber"] == "4D"
            # Markers updated
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_DONE) is True
            assert MARKER_PENDING not in notes
            assert MARKER_FAILED not in notes
            # Narration emitted
            output = "\n".join(session.received)
            assert "Apprentice Forge" in output
            assert "blue" in output.lower()
            assert "Lightsaber constructed" in output
        asyncio.run(_check())

    def test_missing_crystal_records_failure_marker(self):
        async def _check():
            char = _make_char(
                skills={"craft_lightsaber": "2D"},
                chargen_notes={MARKER_PENDING: True},
            )
            session = FakeSession(char)
            db = FakeDB(char, inventory=[])  # no crystal
            ok = await construct_lightsaber(session, db, char)
            assert ok is False
            # No items added (no lightsaber granted)
            assert db.added == []
            # Skill NOT bumped (we bail before that)
            skills = json.loads(char["skills"])
            assert skills["craft_lightsaber"] == "2D"
            # Failure marker set; pending stays (so a future retry
            # can pick it up)
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_FAILED) is True
            assert notes.get(MARKER_PENDING) is True
            assert MARKER_DONE not in notes
            # No narration on the failure path
            assert session.received == []
        asyncio.run(_check())

    def test_remove_from_inventory_raises_treated_as_missing(self):
        async def _check():
            char = _make_char(
                skills={"craft_lightsaber": "2D"},
                chargen_notes={MARKER_PENDING: True},
            )
            session = FakeSession(char)
            db = FakeDB(char, inventory=[CRYSTAL_ITEM_KEY])
            db.fail_remove = True
            ok = await construct_lightsaber(session, db, char)
            assert ok is False
            # Failure marker set
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_FAILED) is True
        asyncio.run(_check())

    def test_add_to_inventory_failure_does_not_block_scene(self):
        # Crystal is consumed before we try to add the lightsaber.
        # If the add fails, we still want the scene to flip to done
        # and bump the skill — losing the item is the cost of a
        # one-off DB anomaly, but the player shouldn't lose forward
        # progress on the path.
        async def _check():
            char = _make_char(
                skills={"craft_lightsaber": "2D"},
                chargen_notes={MARKER_PENDING: True},
            )
            session = FakeSession(char)
            db = FakeDB(char, inventory=[CRYSTAL_ITEM_KEY])
            db.fail_add = True
            ok = await construct_lightsaber(session, db, char)
            assert ok is True
            # Crystal IS consumed
            assert not db.has_item(CRYSTAL_ITEM_KEY)
            # Skill bumped
            skills = json.loads(char["skills"])
            assert skills["craft_lightsaber"] == "4D"
            # Marker flipped
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_DONE) is True
        asyncio.run(_check())

    def test_already_4d_skill_not_re_bumped(self):
        async def _check():
            char = _make_char(
                skills={"craft_lightsaber": "5D+1"},
                chargen_notes={MARKER_PENDING: True},
            )
            session = FakeSession(char)
            db = FakeDB(char, inventory=[CRYSTAL_ITEM_KEY])
            ok = await construct_lightsaber(session, db, char)
            assert ok is True
            # Skill preserved at 5D+1 (no clobber)
            skills = json.loads(char["skills"])
            assert skills["craft_lightsaber"] == "5D+1"
        asyncio.run(_check())

    def test_second_construction_call_is_noop(self):
        # After successful construction, calling again does nothing.
        async def _check():
            char = _make_char(
                skills={"craft_lightsaber": "2D"},
                chargen_notes={MARKER_PENDING: True},
            )
            session = FakeSession(char)
            db = FakeDB(char, inventory=[CRYSTAL_ITEM_KEY])
            ok1 = await construct_lightsaber(session, db, char)
            assert ok1 is True
            ok2 = await construct_lightsaber(session, db, char)
            assert ok2 is False
            # Only one lightsaber added; not two
            count = sum(
                1 for i in db.added
                if i.get("key") == LIGHTSABER_ITEM_KEY
            )
            assert count == 1
        asyncio.run(_check())

    def test_failure_marker_cleared_on_subsequent_success(self):
        async def _check():
            # Char tried earlier, failed (no crystal), then somehow
            # got the crystal back and retried.
            char = _make_char(
                skills={"craft_lightsaber": "2D"},
                chargen_notes={
                    MARKER_PENDING: True,
                    MARKER_FAILED: True,
                },
            )
            session = FakeSession(char)
            db = FakeDB(char, inventory=[CRYSTAL_ITEM_KEY])
            ok = await construct_lightsaber(session, db, char)
            assert ok is True
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_DONE) is True
            assert MARKER_FAILED not in notes
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 5. Path A wire-up
# ═════════════════════════════════════════════════════════════════════════════


def _ready_path_a_char(*, with_crystal=True):
    """Char ready to commit Path A (all five trials done)."""
    return {
        "id": 1, "name": "T", "room_id": 100,
        "force_sensitive": 0,
        "village_act": 3, "village_gate_passed": 1,
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
        "village_trial_spirit_rejections": 4,
        "village_trial_spirit_turn": 5,
        "village_trial_spirit_path_c_locked": 0,
        "village_trial_insight_done": 1,
        "village_trial_insight_attempts": 1,
        "village_trial_insight_correct_fragment": 2,
        "village_trial_insight_pendant_granted": 1,
        "village_choice_completed": 0,
        "village_chosen_path": "",
        "village_standing": 12,
        "chargen_notes": json.dumps(
            {"village_first_audience_done": True}),
        "skills": json.dumps({"craft_lightsaber": "2D"}),
        "attributes": json.dumps({"dex": "4D", "tec": "4D"}),
    }


class FakePathADB(FakeDB):
    """Extends FakeDB with the surface engine.village_choice expects:
    get_room, get_organization, join_organization, adjust_rep,
    get_room_by_slug."""
    def __init__(self, char, inventory=None):
        super().__init__(char, inventory=inventory)
        self._room_name = "Master's Chamber"
        self._slug_to_room_id = {
            "jedi_temple_main_gate": 200,
            "village_common_square": 201,
            "dune_sea_anchor_stones": 202,
        }

    def set_room(self, name):
        self._room_name = name

    async def get_room(self, room_id):
        return {"name": self._room_name, "id": room_id}

    async def get_organization(self, code):
        if code == "jedi_order":
            return {"id": 100, "code": "jedi_order"}
        if code == "independent":
            return {"id": 101, "code": "independent"}
        return None

    async def join_organization(self, char_id, org_id, specialization=""):
        return True

    async def adjust_rep(self, char_id, org_code, delta):
        pass

    async def get_room_by_slug(self, slug):
        rid = self._slug_to_room_id.get(slug)
        return {"id": rid, "slug": slug} if rid else None


class TestPathAWireUp:
    """The Path A commit handler must call construct_lightsaber
    between Mace's narration and the teleport."""

    def test_village_choice_imports_construction(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_choice.py")
        src = open(path, "r", encoding="utf-8").read()
        assert ("from engine.lightsaber_construction "
                "import construct_lightsaber") in src

    def test_path_a_with_crystal_runs_full_scene(self):
        async def _check():
            from engine.village_choice import attempt_choose_path
            char = _ready_path_a_char()
            session = FakeSession(char)
            db = FakePathADB(char, inventory=[CRYSTAL_ITEM_KEY])
            await attempt_choose_path(session, db, char, path="a")
            # Path A committed
            assert char["village_choice_completed"] == 1
            assert char["village_chosen_path"] == "a"
            # Construction ran: crystal consumed, lightsaber granted
            assert not db.has_item(CRYSTAL_ITEM_KEY)
            assert any(
                i.get("key") == LIGHTSABER_ITEM_KEY for i in db.added
            )
            # Skill bumped
            skills = json.loads(char["skills"])
            assert skills["craft_lightsaber"] == "4D"
            # Done marker set
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_DONE) is True
            assert MARKER_PENDING not in notes
            # Narration includes both the Mace Windu line and the
            # forge scene
            output = "\n".join(session.received)
            assert "Yarael lives" in output
            assert "Apprentice Forge" in output
        asyncio.run(_check())

    def test_path_a_without_crystal_still_commits(self):
        async def _check():
            from engine.village_choice import attempt_choose_path
            char = _ready_path_a_char()
            session = FakeSession(char)
            db = FakePathADB(char, inventory=[])  # no crystal
            await attempt_choose_path(session, db, char, path="a")
            # Path A still committed
            assert char["village_choice_completed"] == 1
            assert char["village_chosen_path"] == "a"
            # No lightsaber granted
            assert not any(
                i.get("key") == LIGHTSABER_ITEM_KEY for i in db.added
            )
            # Failure marker recorded
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_FAILED) is True
            assert notes.get(MARKER_DONE) is None
            # Pending marker still set (so a future retry could
            # pick it up)
            assert notes.get(MARKER_PENDING) is True
            # Teleport still happened (Path A flags are still set)
            assert char.get("force_sensitive") == 1
        asyncio.run(_check())

    def test_path_b_does_not_trigger_construction(self):
        async def _check():
            from engine.village_choice import attempt_choose_path
            char = _ready_path_a_char()
            session = FakeSession(char)
            db = FakePathADB(char, inventory=[CRYSTAL_ITEM_KEY])
            await attempt_choose_path(session, db, char, path="b")
            # Path B committed
            assert char["village_chosen_path"] == "b"
            # Crystal still in inventory (Path B keeps it)
            assert db.has_item(CRYSTAL_ITEM_KEY)
            # No lightsaber added
            assert not any(
                i.get("key") == LIGHTSABER_ITEM_KEY for i in db.added
            )
            # No construction marker flipped
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_DONE) is None
        asyncio.run(_check())

    def test_path_c_does_not_trigger_construction(self):
        async def _check():
            from engine.village_choice import attempt_choose_path
            char = _ready_path_a_char()
            char["village_trial_spirit_path_c_locked"] = 1
            session = FakeSession(char)
            db = FakePathADB(char, inventory=[CRYSTAL_ITEM_KEY])
            await attempt_choose_path(session, db, char, path="c")
            # Path C committed
            assert char["village_chosen_path"] == "c"
            # Crystal still in inventory
            assert db.has_item(CRYSTAL_ITEM_KEY)
            # No lightsaber
            assert not any(
                i.get("key") == LIGHTSABER_ITEM_KEY for i in db.added
            )
            notes = json.loads(char["chargen_notes"])
            assert notes.get(MARKER_DONE) is None
        asyncio.run(_check())
