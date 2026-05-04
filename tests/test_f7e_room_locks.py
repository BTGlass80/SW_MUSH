# -*- coding: utf-8 -*-
"""
tests/test_f7e_room_locks.py — F.7.e — Conditional room-lock runtime.

Validates ``engine/room_locks.py`` and its wiring into
``parser/builtin_commands.py::MoveCommand._check_exit_gates``.

The Sealed Sanctum on Tatooine is the canonical use-case (and the
only `locked_until_flag` value in CW world data today): the room
is sealed until the player is eligible for the Trial of Spirit, and
remains open after they've completed it (including Path C lock-in
per F.7.c.4 / F.7.d).

Coverage:

  1. Property reading (defensive against malformed/missing JSON).
  2. ``get_locked_until_flag`` accessor.
  3. Flag handler: ``spirit_trial_in_progress``
       - flesh+ all unmet → blocked
       - skill done, courage/flesh/spirit all unmet → blocked
       - skill+courage+flesh done (Spirit unlocked) → allowed
       - Spirit done → allowed
       - Path C locked + done → allowed
  4. Public gate ``can_enter_locked_room``:
       - Room with no properties → allowed
       - Room with no locked_until_flag → allowed
       - Room with unknown flag → allowed (fail-open)
       - Admin bypass
       - Builder bypass
       - get_room raises → allowed (fail-open)
       - Handler raises → allowed (fail-open)
  5. Registry:
       - get_registered_flags includes spirit
       - register_flag_handler new flag works
       - re-registering same name + same handler is no-op
       - re-registering same name + different handler raises
  6. Source wiring: ``_check_exit_gates`` calls
     ``can_enter_locked_room`` with the right shape.
  7. Sealed Sanctum world data carries the flag (regression check).
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

from engine.room_locks import (
    can_enter_locked_room,
    get_locked_until_flag,
    get_registered_flags,
    register_flag_handler,
    _read_room_properties,
    _flag_spirit_trial_in_progress,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_char(
    *, audience_done=False,
    skill_done=False, courage_done=False, flesh_done=False,
    spirit_done=False, spirit_path_c_locked=False,
):
    """Build a minimal char dict with the trial-state columns the
    Spirit handler reads."""
    return {
        "id": 1,
        "name": "Test",
        "village_gate_passed": 1 if audience_done else 0,
        "village_trial_skill_done": int(skill_done),
        "village_trial_courage_done": int(courage_done),
        "village_trial_flesh_done": int(flesh_done),
        "village_trial_spirit_done": int(spirit_done),
        "village_trial_spirit_path_c_locked": int(spirit_path_c_locked),
        # Audience flag lives in chargen_notes (consumed by
        # has_completed_audience). We bypass it here by setting
        # village_gate_passed and putting the flag in chargen_notes.
        "chargen_notes": json.dumps(
            {"village_first_audience_done": True} if audience_done else {}
        ),
    }


class FakeDB:
    """Stub DB exposing only get_room. Tests construct it with the
    room dict they want returned for any room_id."""
    def __init__(self, room=None, raise_on_get=False):
        self._room = room
        self._raise = raise_on_get
        self.calls: list = []

    async def get_room(self, room_id):
        self.calls.append(room_id)
        if self._raise:
            raise RuntimeError("simulated DB failure")
        return self._room


def _room(properties=None):
    """Build a minimal room dict, optionally with a properties JSON."""
    if properties is None:
        return {"id": 1, "name": "Sealed Sanctum"}
    return {
        "id": 1,
        "name": "Sealed Sanctum",
        "properties": (
            json.dumps(properties) if isinstance(properties, dict)
            else properties
        ),
    }


# ═════════════════════════════════════════════════════════════════════════════
# 1. Property reading
# ═════════════════════════════════════════════════════════════════════════════


class TestReadRoomProperties:

    def test_missing_room(self):
        assert _read_room_properties(None) == {}

    def test_no_properties_key(self):
        assert _read_room_properties({"id": 1}) == {}

    def test_properties_is_dict(self):
        room = {"properties": {"foo": "bar"}}
        assert _read_room_properties(room) == {"foo": "bar"}

    def test_properties_is_json_string(self):
        room = {"properties": json.dumps({"foo": "bar"})}
        assert _read_room_properties(room) == {"foo": "bar"}

    def test_properties_is_malformed_json(self):
        room = {"properties": "{not valid json"}
        assert _read_room_properties(room) == {}

    def test_properties_is_json_but_not_dict(self):
        # JSON of a list — our code expects a dict.
        room = {"properties": "[1, 2, 3]"}
        assert _read_room_properties(room) == {}

    def test_properties_is_unexpected_type(self):
        # int instead of str/dict — defensive fallback.
        room = {"properties": 42}
        assert _read_room_properties(room) == {}


class TestGetLockedUntilFlag:

    def test_absent(self):
        assert get_locked_until_flag(_room()) == ""

    def test_present(self):
        room = _room({"locked_until_flag": "spirit_trial_in_progress"})
        assert get_locked_until_flag(room) == "spirit_trial_in_progress"

    def test_strips_whitespace(self):
        room = _room({"locked_until_flag": "  spirit_trial_in_progress  "})
        assert get_locked_until_flag(room) == "spirit_trial_in_progress"

    def test_non_string_value(self):
        # Defensive: if a yaml typo gives us an int, treat as absent
        # rather than crash.
        room = _room({"locked_until_flag": 42})
        assert get_locked_until_flag(room) == ""

    def test_none_room(self):
        assert get_locked_until_flag(None) == ""


# ═════════════════════════════════════════════════════════════════════════════
# 2. spirit_trial_in_progress flag handler
# ═════════════════════════════════════════════════════════════════════════════


class TestSpiritFlagHandler:

    def test_no_audience_blocked(self):
        char = _make_char()
        allowed, reason = _flag_spirit_trial_in_progress(char)
        assert allowed is False
        assert reason  # non-empty reason

    def test_audience_only_blocked(self):
        char = _make_char(audience_done=True)
        allowed, _ = _flag_spirit_trial_in_progress(char)
        assert allowed is False

    def test_audience_skill_blocked(self):
        char = _make_char(audience_done=True, skill_done=True)
        allowed, _ = _flag_spirit_trial_in_progress(char)
        assert allowed is False

    def test_audience_skill_courage_blocked(self):
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
        )
        allowed, _ = _flag_spirit_trial_in_progress(char)
        assert allowed is False

    def test_all_four_prereqs_allowed(self):
        char = _make_char(
            audience_done=True, skill_done=True, courage_done=True,
            flesh_done=True,
        )
        allowed, reason = _flag_spirit_trial_in_progress(char)
        assert allowed is True
        assert reason == ""

    def test_spirit_done_allowed_even_without_other_state(self):
        # Done bypasses the unlocked check (post-quest re-entry).
        char = _make_char(spirit_done=True)
        allowed, _ = _flag_spirit_trial_in_progress(char)
        assert allowed is True

    def test_spirit_done_path_c_locked_allowed(self):
        # Path C lock-in counts as completion — per F.7.c.4 / design §7.3.
        char = _make_char(
            spirit_done=True, spirit_path_c_locked=True,
        )
        allowed, _ = _flag_spirit_trial_in_progress(char)
        assert allowed is True

    def test_blocked_reason_mentions_master_yarael(self):
        char = _make_char()
        _, reason = _flag_spirit_trial_in_progress(char)
        assert "Master" in reason or "Yarael" in reason


# ═════════════════════════════════════════════════════════════════════════════
# 3. Public gate function
# ═════════════════════════════════════════════════════════════════════════════


class TestCanEnterLockedRoom:

    def test_no_room_returned_allowed(self):
        async def _check():
            db = FakeDB(room=None)
            char = _make_char()
            allowed, reason = await can_enter_locked_room(db, char, 1)
            assert allowed is True
            assert reason == ""
        asyncio.run(_check())

    def test_room_with_no_properties_allowed(self):
        async def _check():
            db = FakeDB(room=_room())
            char = _make_char()
            allowed, _ = await can_enter_locked_room(db, char, 1)
            assert allowed is True
        asyncio.run(_check())

    def test_room_with_no_locked_flag_allowed(self):
        async def _check():
            db = FakeDB(room=_room({"some_other": "prop"}))
            char = _make_char()
            allowed, _ = await can_enter_locked_room(db, char, 1)
            assert allowed is True
        asyncio.run(_check())

    def test_unknown_flag_fails_open(self):
        async def _check():
            db = FakeDB(room=_room({
                "locked_until_flag": "no_such_flag_in_registry",
            }))
            char = _make_char()
            allowed, reason = await can_enter_locked_room(db, char, 1)
            assert allowed is True
            assert reason == ""
        asyncio.run(_check())

    def test_get_room_raises_fails_open(self):
        async def _check():
            db = FakeDB(raise_on_get=True)
            char = _make_char()
            allowed, _ = await can_enter_locked_room(db, char, 1)
            assert allowed is True
        asyncio.run(_check())

    def test_spirit_flag_blocks_when_unmet(self):
        async def _check():
            db = FakeDB(room=_room({
                "locked_until_flag": "spirit_trial_in_progress",
            }))
            char = _make_char()  # no prereqs
            allowed, reason = await can_enter_locked_room(db, char, 1)
            assert allowed is False
            assert reason
        asyncio.run(_check())

    def test_spirit_flag_allows_when_unlocked(self):
        async def _check():
            db = FakeDB(room=_room({
                "locked_until_flag": "spirit_trial_in_progress",
            }))
            char = _make_char(
                audience_done=True, skill_done=True,
                courage_done=True, flesh_done=True,
            )
            allowed, _ = await can_enter_locked_room(db, char, 1)
            assert allowed is True
        asyncio.run(_check())

    def test_admin_bypasses_lock(self):
        async def _check():
            db = FakeDB(room=_room({
                "locked_until_flag": "spirit_trial_in_progress",
            }))
            char = _make_char()  # no prereqs
            allowed, _ = await can_enter_locked_room(
                db, char, 1, lock_ctx={"is_admin": True},
            )
            assert allowed is True
        asyncio.run(_check())

    def test_builder_bypasses_lock(self):
        async def _check():
            db = FakeDB(room=_room({
                "locked_until_flag": "spirit_trial_in_progress",
            }))
            char = _make_char()
            allowed, _ = await can_enter_locked_room(
                db, char, 1, lock_ctx={"is_builder": True},
            )
            assert allowed is True
        asyncio.run(_check())

    def test_admin_bypass_does_not_call_get_room(self):
        # Performance: admin bypass should short-circuit before the DB
        # call. Less DB load on staff debugging.
        async def _check():
            db = FakeDB(room=_room({
                "locked_until_flag": "spirit_trial_in_progress",
            }))
            char = _make_char()
            await can_enter_locked_room(
                db, char, 1, lock_ctx={"is_admin": True},
            )
            assert db.calls == []
        asyncio.run(_check())

    def test_no_lock_ctx_does_not_crash(self):
        async def _check():
            db = FakeDB(room=_room())
            char = _make_char()
            # Default arg is None
            allowed, _ = await can_enter_locked_room(db, char, 1)
            assert allowed is True
        asyncio.run(_check())

    def test_handler_raises_fails_open(self):
        # If a registered handler crashes for any reason, the gate
        # fails open — better to leave the door unlocked than to
        # block a legitimate player.
        async def _check():
            from engine import room_locks
            def _bad_handler(char):
                raise RuntimeError("simulated handler failure")
            register_flag_handler("bad_test_flag", _bad_handler)
            try:
                db = FakeDB(room=_room({
                    "locked_until_flag": "bad_test_flag",
                }))
                char = _make_char()
                allowed, _ = await can_enter_locked_room(db, char, 1)
                assert allowed is True
            finally:
                room_locks._FLAG_HANDLERS.pop("bad_test_flag", None)
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 4. Registry
# ═════════════════════════════════════════════════════════════════════════════


class TestFlagRegistry:

    def test_spirit_flag_registered(self):
        assert "spirit_trial_in_progress" in get_registered_flags()

    def test_register_new_flag_works(self):
        from engine import room_locks
        def _h(char):
            return (True, "")
        try:
            register_flag_handler("test_flag_unique_1", _h)
            assert "test_flag_unique_1" in get_registered_flags()
        finally:
            room_locks._FLAG_HANDLERS.pop("test_flag_unique_1", None)

    def test_re_register_same_handler_is_idempotent(self):
        from engine import room_locks
        def _h(char):
            return (True, "")
        try:
            register_flag_handler("test_flag_unique_2", _h)
            # Same handler — no error
            register_flag_handler("test_flag_unique_2", _h)
            assert "test_flag_unique_2" in get_registered_flags()
        finally:
            room_locks._FLAG_HANDLERS.pop("test_flag_unique_2", None)

    def test_re_register_different_handler_raises(self):
        from engine import room_locks
        def _h1(char):
            return (True, "")
        def _h2(char):
            return (True, "")
        try:
            register_flag_handler("test_flag_unique_3", _h1)
            with pytest.raises(ValueError):
                register_flag_handler("test_flag_unique_3", _h2)
        finally:
            room_locks._FLAG_HANDLERS.pop("test_flag_unique_3", None)


# ═════════════════════════════════════════════════════════════════════════════
# 5. Source wiring (MoveCommand._check_exit_gates)
# ═════════════════════════════════════════════════════════════════════════════


class TestMoveCommandWiring:
    """The wiring is integration-tested via the flag's behaviour
    (above); these tests confirm the import and the call site exist
    in the parser source."""

    def _read_source(self):
        path = os.path.join(PROJECT_ROOT, "parser", "builtin_commands.py")
        return open(path, "r", encoding="utf-8").read()

    def test_imports_room_locks(self):
        src = self._read_source()
        assert "from engine.room_locks import can_enter_locked_room" in src

    def test_calls_gate_in_check_exit_gates(self):
        src = self._read_source()
        # Find `_check_exit_gates` and ensure the gate call is inside.
        idx = src.find("async def _check_exit_gates")
        assert idx != -1, "_check_exit_gates not found"
        # Find the next async def or def after this one
        next_def = src.find("async def ", idx + 1)
        # Window: from start of this method to start of the next one
        window = src[idx:next_def] if next_def != -1 else src[idx:]
        assert "can_enter_locked_room" in window
        # And the lock_ctx is passed (admin/builder bypass)
        assert "lock_ctx" in window

    def test_passes_account_admin_builder_bits(self):
        src = self._read_source()
        idx = src.find("async def _check_exit_gates")
        next_def = src.find("async def ", idx + 1)
        window = src[idx:next_def] if next_def != -1 else src[idx:]
        # The integration block reads the account and threads
        # is_admin / is_builder into lock_ctx.
        assert "get_account" in window
        assert "is_admin" in window
        assert "is_builder" in window


# ═════════════════════════════════════════════════════════════════════════════
# 6. Sealed Sanctum world data regression
# ═════════════════════════════════════════════════════════════════════════════


class TestSealedSanctumWorldData:
    """The Sanctum room in dune_sea.yaml carries the flag. Regression
    coverage so future world-data churn doesn't silently strip it."""

    def test_dune_sea_yaml_carries_flag(self):
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "dune_sea.yaml",
        )
        src = open(path, "r", encoding="utf-8").read()
        assert "village_sealed_sanctum" in src
        assert "locked_until_flag: spirit_trial_in_progress" in src

    def test_jedi_village_yaml_carries_flag(self):
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "quests", "jedi_village.yaml",
        )
        if not os.path.exists(path):
            pytest.skip("jedi_village.yaml not present in this tree")
        src = open(path, "r", encoding="utf-8").read()
        assert "village_sealed_sanctum" in src
        assert "locked_until_flag: spirit_trial_in_progress" in src
