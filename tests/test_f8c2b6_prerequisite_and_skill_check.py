# -*- coding: utf-8 -*-
"""
tests/test_f8c2b6_prerequisite_and_skill_check.py — F.8.c.2.b Phase 3
follow-up (May 19 2026).

This drop closes the two `completion.type` values left ⏳/unwired
through Phase 3 of F.8.c.2.b:

  * **`prerequisite`** — gates on a chargen flag stored in
    chargen_notes JSON. Fires whenever the flag is set truthy. Two
    chain steps use this: `jedi_path` step 1 and
    `jedi_path_independent` step 1, both gating on
    `jedi_path_unlocked`.
  * **`skill_check_passed`** — public seam ships, no production
    trigger. Six chain steps in chains.yaml use this; the
    trigger-site decision is deferred per
    `engine/chain_events.py` module docstring "F.8.c.2.b₆ design
    note". The seam is tested from outside so once wire-up is
    chosen, the dispatcher is already validated.

Wire-up
=======

`on_prerequisite_flag_set` is wired into
``engine/village_choice.py::_set_chargen_flags`` — after the
chargen_notes JSON is persisted, every flag in the call's flags
dict with a truthy value is dispatched. Failure-tolerant: the
flag set must never fail because of a chain hook exception.

`on_skill_check_passed` ships as a public seam only. The wire
site is open — see the chain_events module docstring for the
three candidate trigger models.

Test sections
=============

  1. TestPrerequisiteMatcher           — pure matcher unit tests
  2. TestSkillCheckPassedMatcher        — pure matcher unit tests
  3. TestPrerequisiteDispatcher         — on_prerequisite_flag_set
                                          end-to-end through a fake DB
  4. TestSkillCheckPassedDispatcher     — on_skill_check_passed
                                          end-to-end through a fake DB
  5. TestSetChargenFlagsWires           — _set_chargen_flags actually
                                          calls on_prerequisite_flag_set
                                          for each truthy flag
  6. TestSetChargenFlagsFailureTolerant — a dispatcher exception
                                          does not fail the flag set
  7. TestPrereqWrongFlagDoesNotAdvance  — sanity: wrong flag → no-op
  8. TestSkillCheckFailedDoesNotAdvance — sanity: succeeded=False →
                                          no-op
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────
# Shared fixture pattern (mirrors test_f8c2b5_requires_first.py)
# ─────────────────────────────────────────────────────────────────────


class _F8C2B6IsolatedBase(unittest.TestCase):

    def setUp(self):
        from engine.era_state import set_active_config
        from engine.chain_events import _reset_corpus_cache
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        _reset_corpus_cache()

    def tearDown(self):
        from engine.era_state import clear_active_config
        from engine.chain_events import _reset_corpus_cache
        clear_active_config()
        _reset_corpus_cache()


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_fake_db():
    db = MagicMock()
    db.save_character = AsyncMock()
    db.get_npc = AsyncMock(return_value=None)
    db.get_character = AsyncMock(return_value=None)
    return db


def _char_with_chain(chain_id: str, step: int = 1,
                     completed: list = None) -> dict:
    state = {
        "chain_id": chain_id,
        "step": step,
        "started_at": 1000000,
        "completed_steps": list(completed or []),
        "completion_state": "active",
    }
    return {
        "id": 42,
        "name": "Test PC",
        "attributes": json.dumps({"tutorial_chain": state}),
    }


def _attrs(char: dict) -> dict:
    return json.loads(char["attributes"])


# ═════════════════════════════════════════════════════════════════════
# 1. Pure matcher: _match_prerequisite
# ═════════════════════════════════════════════════════════════════════


class TestPrerequisiteMatcher(unittest.TestCase):
    """Pure unit tests for the matcher — no DB, no corpus, no async."""

    def test_match_exact_flag(self):
        from engine.chain_events import _match_prerequisite
        comp = {"type": "prerequisite", "flag": "jedi_path_unlocked"}
        self.assertTrue(_match_prerequisite(comp, "jedi_path_unlocked"))

    def test_match_different_flag_returns_false(self):
        from engine.chain_events import _match_prerequisite
        comp = {"type": "prerequisite", "flag": "jedi_path_unlocked"}
        self.assertFalse(
            _match_prerequisite(comp, "village_chosen_path_a"))

    def test_match_empty_flag_name_returns_false(self):
        from engine.chain_events import _match_prerequisite
        comp = {"type": "prerequisite", "flag": "jedi_path_unlocked"}
        self.assertFalse(_match_prerequisite(comp, ""))

    def test_match_empty_completion_flag_returns_false(self):
        # A completion with no `flag` field shouldn't match anything,
        # even the empty-string flag name. This guards against
        # malformed chain authoring.
        from engine.chain_events import _match_prerequisite
        self.assertFalse(_match_prerequisite({}, "anything"))
        self.assertFalse(
            _match_prerequisite({"type": "prerequisite"}, "anything"))

    def test_match_whitespace_normalized(self):
        # Leading/trailing whitespace on either side is normalized.
        from engine.chain_events import _match_prerequisite
        comp = {"type": "prerequisite", "flag": "  jedi_path_unlocked  "}
        self.assertTrue(_match_prerequisite(comp, "jedi_path_unlocked"))
        comp2 = {"type": "prerequisite", "flag": "jedi_path_unlocked"}
        self.assertTrue(_match_prerequisite(comp2, "  jedi_path_unlocked  "))


# ═════════════════════════════════════════════════════════════════════
# 2. Pure matcher: _match_skill_check_passed
# ═════════════════════════════════════════════════════════════════════


class TestSkillCheckPassedMatcher(unittest.TestCase):
    """Pure unit tests for the matcher — no DB, no corpus, no async."""

    def test_match_when_skill_and_succeeded(self):
        from engine.chain_events import _match_skill_check_passed
        comp = {"type": "skill_check_passed", "skill": "sneak",
                "difficulty": 8}
        self.assertTrue(
            _match_skill_check_passed(comp, "sneak", True))

    def test_no_match_when_failed_even_with_right_skill(self):
        # Failed check is a hard no-match — the dispatcher only
        # fires for the success case. Caller is responsible for
        # dispatching fallback / on_fail consequences.
        from engine.chain_events import _match_skill_check_passed
        comp = {"type": "skill_check_passed", "skill": "sneak",
                "difficulty": 8}
        self.assertFalse(
            _match_skill_check_passed(comp, "sneak", False))

    def test_no_match_when_wrong_skill(self):
        from engine.chain_events import _match_skill_check_passed
        comp = {"type": "skill_check_passed", "skill": "sneak",
                "difficulty": 8}
        self.assertFalse(
            _match_skill_check_passed(comp, "con", True))

    def test_skill_match_case_insensitive(self):
        from engine.chain_events import _match_skill_check_passed
        comp = {"type": "skill_check_passed", "skill": "Sneak",
                "difficulty": 8}
        self.assertTrue(
            _match_skill_check_passed(comp, "SNEAK", True))

    def test_difficulty_field_is_not_re_evaluated(self):
        # The dispatcher trusts the caller's `succeeded` flag — it
        # does NOT compare to `completion.difficulty`. Caller has
        # already rolled at the right difficulty.
        from engine.chain_events import _match_skill_check_passed
        comp = {"type": "skill_check_passed", "skill": "sneak",
                "difficulty": 999}
        # succeeded=True still matches even though difficulty=999
        # — caller (not dispatcher) decided this was a success.
        self.assertTrue(
            _match_skill_check_passed(comp, "sneak", True))

    def test_no_match_when_completion_skill_missing(self):
        from engine.chain_events import _match_skill_check_passed
        self.assertFalse(
            _match_skill_check_passed({}, "sneak", True))
        self.assertFalse(_match_skill_check_passed(
            {"type": "skill_check_passed"}, "sneak", True))


# ═════════════════════════════════════════════════════════════════════
# 3. Dispatcher end-to-end: on_prerequisite_flag_set
# ═════════════════════════════════════════════════════════════════════


class TestPrerequisiteDispatcher(_F8C2B6IsolatedBase):
    """End-to-end through a fake DB. The CW chain corpus is loaded
    (via _F8C2B6IsolatedBase's set_active_config to clone_wars),
    so the dispatcher matches against the real chain steps.

    Note: both `jedi_path` and `jedi_path_independent` are
    single-step chains. Completing step 1 therefore graduates the
    chain (completion_state flips to "graduated") rather than
    advancing the step number. The test asserts on graduation
    state, not step increment.
    """

    def test_jedi_path_step_1_graduates_on_flag(self):
        from engine.chain_events import on_prerequisite_flag_set
        db = _make_fake_db()
        char = _char_with_chain("jedi_path", step=1)
        advanced = _run(
            on_prerequisite_flag_set(db, char, "jedi_path_unlocked"))
        self.assertTrue(advanced)
        state = _attrs(char)["tutorial_chain"]
        self.assertEqual(
            state.get("completion_state"), "graduated",
            f"chain did not graduate: state={state!r}",
        )
        self.assertTrue(db.save_character.called)

    def test_jedi_path_independent_step_1_graduates_on_flag(self):
        from engine.chain_events import on_prerequisite_flag_set
        db = _make_fake_db()
        char = _char_with_chain("jedi_path_independent", step=1)
        advanced = _run(
            on_prerequisite_flag_set(db, char, "jedi_path_unlocked"))
        self.assertTrue(advanced)
        state = _attrs(char)["tutorial_chain"]
        self.assertEqual(state.get("completion_state"), "graduated")

    def test_empty_flag_name_returns_false(self):
        from engine.chain_events import on_prerequisite_flag_set
        db = _make_fake_db()
        char = _char_with_chain("jedi_path", step=1)
        advanced = _run(on_prerequisite_flag_set(db, char, ""))
        self.assertFalse(advanced)
        # Chain remains active.
        state = _attrs(char)["tutorial_chain"]
        self.assertEqual(state.get("completion_state"), "active")
        self.assertEqual(state.get("step"), 1)


# ═════════════════════════════════════════════════════════════════════
# 4. Dispatcher end-to-end: on_skill_check_passed
# ═════════════════════════════════════════════════════════════════════


class TestSkillCheckPassedDispatcher(_F8C2B6IsolatedBase):

    def test_republic_intelligence_step_3_advances_on_sneak_success(self):
        from engine.chain_events import on_skill_check_passed
        db = _make_fake_db()
        char = _char_with_chain("republic_intelligence", step=3)
        advanced = _run(on_skill_check_passed(
            db, char, "sneak", succeeded=True, difficulty=8))
        self.assertTrue(advanced)
        new_step = _attrs(char)["tutorial_chain"]["step"]
        self.assertGreater(new_step, 3,
                           f"step did not advance: {new_step}")

    def test_bounty_hunter_step_3_advances_on_search_success(self):
        from engine.chain_events import on_skill_check_passed
        db = _make_fake_db()
        char = _char_with_chain("bounty_hunter", step=3)
        advanced = _run(on_skill_check_passed(
            db, char, "search", succeeded=True, difficulty=8))
        self.assertTrue(advanced)

    def test_wrong_skill_does_not_advance(self):
        from engine.chain_events import on_skill_check_passed
        db = _make_fake_db()
        char = _char_with_chain("republic_intelligence", step=3)
        # republic_intelligence step 3 wants sneak, not con
        advanced = _run(on_skill_check_passed(
            db, char, "con", succeeded=True, difficulty=8))
        self.assertFalse(advanced)
        self.assertEqual(
            _attrs(char)["tutorial_chain"]["step"], 3)

    def test_difficulty_argument_is_optional(self):
        from engine.chain_events import on_skill_check_passed
        db = _make_fake_db()
        char = _char_with_chain("republic_intelligence", step=3)
        # difficulty=None should still work — it's observability-only
        advanced = _run(on_skill_check_passed(
            db, char, "sneak", succeeded=True))
        self.assertTrue(advanced)

    def test_empty_skill_name_returns_false(self):
        from engine.chain_events import on_skill_check_passed
        db = _make_fake_db()
        char = _char_with_chain("republic_intelligence", step=3)
        advanced = _run(on_skill_check_passed(
            db, char, "", succeeded=True))
        self.assertFalse(advanced)


# ═════════════════════════════════════════════════════════════════════
# 5. Wire-up: _set_chargen_flags actually dispatches
# ═════════════════════════════════════════════════════════════════════


class TestSetChargenFlagsWires(_F8C2B6IsolatedBase):
    """`_set_chargen_flags` must dispatch every truthy flag through
    `on_prerequisite_flag_set`. Skipping falsy flags is correct
    (a `False` flag means the prereq has NOT been satisfied)."""

    def test_truthy_flag_dispatches(self):
        from engine import village_choice
        from unittest.mock import patch
        db = _make_fake_db()
        char = {"id": 7, "name": "Test PC",
                "chargen_notes": "{}",
                "attributes": json.dumps({})}
        # Patch the chain_events dispatcher to count calls.
        dispatcher = AsyncMock(return_value=False)
        with patch("engine.chain_events.on_prerequisite_flag_set",
                   dispatcher):
            _run(village_choice._set_chargen_flags(
                db, char, jedi_path_unlocked=True))
        self.assertEqual(dispatcher.call_count, 1)
        # First positional after (db, char) is the flag name.
        called_args = dispatcher.call_args[0]
        self.assertEqual(called_args[2], "jedi_path_unlocked")

    def test_falsy_flag_does_not_dispatch(self):
        from engine import village_choice
        from unittest.mock import patch
        db = _make_fake_db()
        char = {"id": 7, "name": "Test PC",
                "chargen_notes": "{}",
                "attributes": json.dumps({})}
        dispatcher = AsyncMock(return_value=False)
        with patch("engine.chain_events.on_prerequisite_flag_set",
                   dispatcher):
            _run(village_choice._set_chargen_flags(
                db, char, some_flag=False, other_flag=None))
        self.assertEqual(dispatcher.call_count, 0)

    def test_multiple_truthy_flags_dispatch_in_order(self):
        from engine import village_choice
        from unittest.mock import patch
        db = _make_fake_db()
        char = {"id": 7, "name": "Test PC",
                "chargen_notes": "{}",
                "attributes": json.dumps({})}
        dispatcher = AsyncMock(return_value=False)
        with patch("engine.chain_events.on_prerequisite_flag_set",
                   dispatcher):
            _run(village_choice._set_chargen_flags(
                db, char,
                jedi_path_unlocked=True,
                village_chosen_path_a=True,
                village_trial_lightsaber_construction_pending=True,
            ))
        self.assertEqual(dispatcher.call_count, 3)
        # Insertion order preserved (Python 3.7+ dict guarantee).
        called_flags = [
            c[0][2] for c in dispatcher.call_args_list
        ]
        self.assertEqual(called_flags, [
            "jedi_path_unlocked",
            "village_chosen_path_a",
            "village_trial_lightsaber_construction_pending",
        ])

    def test_persist_happens_before_dispatch(self):
        # If save_character raises, dispatcher should NEVER fire —
        # the persist is the gate. This guards against firing a
        # chain hook for a flag that didn't actually land in DB.
        from engine import village_choice
        from unittest.mock import patch
        db = _make_fake_db()
        db.save_character = AsyncMock(
            side_effect=RuntimeError("simulated DB failure"))
        char = {"id": 7, "name": "Test PC",
                "chargen_notes": "{}",
                "attributes": json.dumps({})}
        dispatcher = AsyncMock(return_value=False)
        with patch("engine.chain_events.on_prerequisite_flag_set",
                   dispatcher):
            with self.assertRaises(RuntimeError):
                _run(village_choice._set_chargen_flags(
                    db, char, jedi_path_unlocked=True))
        self.assertEqual(dispatcher.call_count, 0)


# ═════════════════════════════════════════════════════════════════════
# 6. Wire-up failure-tolerance
# ═════════════════════════════════════════════════════════════════════


class TestSetChargenFlagsFailureTolerant(_F8C2B6IsolatedBase):
    """A dispatcher exception must NOT propagate out of
    `_set_chargen_flags` — the flag set succeeds regardless."""

    def test_dispatcher_exception_swallowed(self):
        from engine import village_choice
        from unittest.mock import patch
        db = _make_fake_db()
        char = {"id": 7, "name": "Test PC",
                "chargen_notes": "{}",
                "attributes": json.dumps({})}
        dispatcher = AsyncMock(
            side_effect=RuntimeError("simulated hook failure"))
        with patch("engine.chain_events.on_prerequisite_flag_set",
                   dispatcher):
            # Must NOT raise.
            _run(village_choice._set_chargen_flags(
                db, char, jedi_path_unlocked=True))
        # The flag was persisted (save_character called once).
        db.save_character.assert_called_once()
        # The dispatcher was called and raised — we wrap-swallow.
        self.assertEqual(dispatcher.call_count, 1)

    def test_one_dispatcher_failure_does_not_block_next_flag(self):
        # Multiple flags: first dispatcher raises, second still fires.
        from engine import village_choice
        from unittest.mock import patch
        db = _make_fake_db()
        char = {"id": 7, "name": "Test PC",
                "chargen_notes": "{}",
                "attributes": json.dumps({})}
        call_log = []

        async def flaky_dispatcher(_db, _ch, flag_name):
            call_log.append(flag_name)
            if flag_name == "jedi_path_unlocked":
                raise RuntimeError("first flag boom")
            return False

        with patch("engine.chain_events.on_prerequisite_flag_set",
                   flaky_dispatcher):
            _run(village_choice._set_chargen_flags(
                db, char,
                jedi_path_unlocked=True,
                village_chosen_path_a=True,
            ))
        self.assertEqual(
            call_log,
            ["jedi_path_unlocked", "village_chosen_path_a"],
        )


# ═════════════════════════════════════════════════════════════════════
# 7. Sanity: wrong flag does not advance jedi_path
# ═════════════════════════════════════════════════════════════════════


class TestPrereqWrongFlagDoesNotAdvance(_F8C2B6IsolatedBase):

    def test_wrong_flag_name_is_silent_no_op(self):
        from engine.chain_events import on_prerequisite_flag_set
        db = _make_fake_db()
        char = _char_with_chain("jedi_path", step=1)
        advanced = _run(
            on_prerequisite_flag_set(
                db, char, "village_chosen_path_a"))
        self.assertFalse(advanced)
        state = _attrs(char)["tutorial_chain"]
        # Chain remains active (not graduated) at step 1.
        self.assertEqual(state.get("step"), 1)
        self.assertEqual(state.get("completion_state"), "active")


# ═════════════════════════════════════════════════════════════════════
# 8. Sanity: failed skill check does not advance
# ═════════════════════════════════════════════════════════════════════


class TestSkillCheckFailedDoesNotAdvance(_F8C2B6IsolatedBase):

    def test_failed_check_is_silent_no_op(self):
        from engine.chain_events import on_skill_check_passed
        db = _make_fake_db()
        char = _char_with_chain("republic_intelligence", step=3)
        advanced = _run(on_skill_check_passed(
            db, char, "sneak", succeeded=False, difficulty=8))
        self.assertFalse(advanced)
        self.assertEqual(
            _attrs(char)["tutorial_chain"]["step"], 3)


if __name__ == "__main__":
    unittest.main()
