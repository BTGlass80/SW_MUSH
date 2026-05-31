# -*- coding: utf-8 -*-
"""
tests/test_f8c2b5_requires_first.py — F.8.c.2.b Phase 3
(requires_first sub-step tracker).

Phase 3 of F.8.c.2.b is split into two halves:

  * ``requires_first`` — sub-step prerequisite tracking. (THIS DROP.)
  * ``skill_check_passed`` — state-machine extension with on_fail /
    fallback semantics. (DEFERRED — needs per-chain-step seam-decision
    work first; the chains.yaml uses skill_check_passed for narrative
    skills like sneak/con/search that aren't standalone parser
    commands. Wiring requires picking which command's check actually
    fires the chain event per step.)

What ``requires_first`` does
============================

Three chain steps in chains.yaml use ``requires_first``:

  * **republic_soldier step 1:** talk Major Tarrn AFTER ``look`` AND
    ``+sheet``.
  * **smuggler step 5:** ``+factions`` AFTER ``give crate to Dyn``.
  * **shipwright_trader step 2:** ``examine subsystem`` AFTER
    ``scan subsystem``.

Phase 1+2 treated ``requires_first`` as advisory — the main completion
fired regardless of whether prereqs were met. Phase 3 makes prereqs
gating: the main event is silently refused (no advance, no state
change) until every prerequisite descriptor in the list has matched
an event.

Mechanism
---------

State extension on the ``tutorial_chain`` block:

    state["step_progress_satisfied"] = [0, 1]

A list of indices into the current step's ``requires_first`` array.
Cleared whenever the step advances — the next step gets a fresh
empty list (and likely doesn't have requires_first anyway).

Hooks
-----

Today, only ``on_command_executed`` participates in prereq
satisfaction (every requires_first entry in chains.yaml is
command-shaped). The dispatcher passes a ``prereq_matcher`` lambda
to the shared ``_try_advance`` machinery, which:

  1. If the active step has ``requires_first`` and the event matches
     an unsatisfied prereq descriptor → record satisfaction, persist,
     return False (event consumed; no advance).
  2. If the event matches the main completion AND all prereqs are
     satisfied → advance normally.
  3. If the event matches the main completion but prereqs are
     incomplete → silently refuse (return False, no state change).

Other dispatchers (``on_talk_to_npc``, ``on_combat_won``, etc.) don't
pass ``prereq_matcher`` — they can't contribute to requires_first
satisfaction. This is correct because no chain step in chains.yaml
uses non-command prereqs. Adding talk-prereqs later is additive.

Test sections
=============

  1. TestStateHelpers              — get/record/clear progress
  2. TestPrereqMatcher             — _match_prereq_command_executed
  3. TestAllPrereqsSatisfied       — the gating helper
  4. TestAdvanceStepClearsProgress — progress clears on advance
  5. TestSinglePrereq              — shipwright_trader step 2
  6. TestTwoPrereqs                — republic_soldier step 1
  7. TestTargetedPrereq            — smuggler step 5 (give crate Dyn)
  8. TestPrereqIdempotent          — repeating an already-satisfied
                                     event does not double-record
  9. TestMainBlockedWhenIncomplete — main completion silently refused
                                     when prereqs not satisfied
 10. TestUnrelatedCommandsIgnored  — commands that don't match any
                                     prereq descriptor are no-op
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
# Shared fixture pattern (mirrors test_f8c2b_chain_events.py)
# ─────────────────────────────────────────────────────────────────────


class _F8C2B5IsolatedBase(unittest.TestCase):

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
                     completed: list = None,
                     satisfied_prereqs: list = None) -> dict:
    state = {
        "chain_id": chain_id,
        "step": step,
        "started_at": 1000000,
        "completed_steps": list(completed or []),
        "completion_state": "active",
    }
    if satisfied_prereqs is not None:
        state["step_progress_satisfied"] = list(satisfied_prereqs)
    return {
        "id": 42,
        "name": "Test PC",
        "attributes": json.dumps({"tutorial_chain": state}),
    }


def _attrs(char: dict) -> dict:
    return json.loads(char["attributes"])


# ═════════════════════════════════════════════════════════════════════
# 1. State helpers in engine/tutorial_chains.py
# ═════════════════════════════════════════════════════════════════════


class TestStateHelpers(_F8C2B5IsolatedBase):

    def test_get_satisfied_prereqs_empty_when_block_missing(self):
        from engine.tutorial_chains import get_satisfied_prereqs
        attrs = {"tutorial_chain": {
            "chain_id": "x", "step": 1, "completion_state": "active"}}
        self.assertEqual(get_satisfied_prereqs(attrs), [])

    def test_get_satisfied_prereqs_returns_list(self):
        from engine.tutorial_chains import get_satisfied_prereqs
        attrs = {"tutorial_chain": {
            "chain_id": "x", "step": 1, "completion_state": "active",
            "step_progress_satisfied": [0, 2],
        }}
        self.assertEqual(get_satisfied_prereqs(attrs), [0, 2])

    def test_get_satisfied_prereqs_handles_corruption(self):
        # A non-list value should not crash — return empty.
        from engine.tutorial_chains import get_satisfied_prereqs
        attrs = {"tutorial_chain": {
            "chain_id": "x", "step": 1, "completion_state": "active",
            "step_progress_satisfied": "not a list",
        }}
        self.assertEqual(get_satisfied_prereqs(attrs), [])

    def test_record_prereq_satisfied_returns_true_on_first(self):
        from engine.tutorial_chains import record_prereq_satisfied
        attrs = {"tutorial_chain": {
            "chain_id": "x", "step": 1, "completion_state": "active"}}
        self.assertTrue(record_prereq_satisfied(attrs, 0))
        self.assertEqual(
            attrs["tutorial_chain"]["step_progress_satisfied"], [0])

    def test_record_prereq_satisfied_idempotent(self):
        # Re-recording an already-satisfied prereq returns False (no
        # state change).
        from engine.tutorial_chains import record_prereq_satisfied
        attrs = {"tutorial_chain": {
            "chain_id": "x", "step": 1, "completion_state": "active",
            "step_progress_satisfied": [0],
        }}
        self.assertFalse(record_prereq_satisfied(attrs, 0))
        self.assertEqual(
            attrs["tutorial_chain"]["step_progress_satisfied"], [0])

    def test_record_prereq_no_active_chain_no_op(self):
        # If there's no active chain, recording is a no-op (returns
        # False) and no state appears.
        from engine.tutorial_chains import record_prereq_satisfied
        attrs = {}
        self.assertFalse(record_prereq_satisfied(attrs, 0))
        self.assertEqual(attrs, {})

    def test_record_prereq_graduated_chain_no_op(self):
        from engine.tutorial_chains import record_prereq_satisfied
        attrs = {"tutorial_chain": {
            "chain_id": "x", "step": 1,
            "completion_state": "graduated"}}
        self.assertFalse(record_prereq_satisfied(attrs, 0))
        self.assertNotIn(
            "step_progress_satisfied", attrs["tutorial_chain"])

    def test_clear_step_progress_removes_key(self):
        from engine.tutorial_chains import clear_step_progress
        attrs = {"tutorial_chain": {
            "chain_id": "x", "step": 1, "completion_state": "active",
            "step_progress_satisfied": [0, 1],
        }}
        clear_step_progress(attrs)
        self.assertNotIn(
            "step_progress_satisfied", attrs["tutorial_chain"])


# ═════════════════════════════════════════════════════════════════════
# 2. Prereq matcher (_match_prereq_command_executed)
# ═════════════════════════════════════════════════════════════════════


class TestPrereqMatcher(_F8C2B5IsolatedBase):

    def test_bare_command_match(self):
        from engine.chain_events import _match_prereq_command_executed
        prereq = {"command": "look"}
        self.assertTrue(_match_prereq_command_executed(prereq, "look", ""))

    def test_bare_command_mismatch(self):
        from engine.chain_events import _match_prereq_command_executed
        prereq = {"command": "look"}
        self.assertFalse(_match_prereq_command_executed(
            prereq, "+sheet", ""))

    def test_command_match_case_insensitive(self):
        from engine.chain_events import _match_prereq_command_executed
        prereq = {"command": "LOOK"}
        self.assertTrue(_match_prereq_command_executed(prereq, "look", ""))

    def test_target_contains_match(self):
        from engine.chain_events import _match_prereq_command_executed
        prereq = {"command": "scan", "target_contains": "subsystem"}
        self.assertTrue(_match_prereq_command_executed(
            prereq, "scan", "subsystem hyperdrive"))

    def test_target_contains_miss(self):
        from engine.chain_events import _match_prereq_command_executed
        prereq = {"command": "scan", "target_contains": "subsystem"}
        self.assertFalse(_match_prereq_command_executed(
            prereq, "scan", "engine compartment"))

    def test_target_npc_substring_match(self):
        # smuggler step 5 prereq shape: command + target_contains +
        # target_npc. All three constraints must match args.
        from engine.chain_events import _match_prereq_command_executed
        prereq = {"command": "give", "target_contains": "crate",
                  "target_npc": "Dyn"}
        self.assertTrue(_match_prereq_command_executed(
            prereq, "give", "crate to Dyn"))

    def test_target_npc_substring_miss(self):
        from engine.chain_events import _match_prereq_command_executed
        prereq = {"command": "give", "target_contains": "crate",
                  "target_npc": "Dyn"}
        # 'crate' present, but no 'Dyn' in args
        self.assertFalse(_match_prereq_command_executed(
            prereq, "give", "crate to Voss"))

    def test_empty_command_field_no_match(self):
        from engine.chain_events import _match_prereq_command_executed
        prereq = {"command": ""}
        self.assertFalse(_match_prereq_command_executed(prereq, "look", ""))


# ═════════════════════════════════════════════════════════════════════
# 3. _all_prereqs_satisfied gating helper
# ═════════════════════════════════════════════════════════════════════


class TestAllPrereqsSatisfied(_F8C2B5IsolatedBase):

    def test_no_requires_first_returns_true(self):
        from engine.chain_events import _all_prereqs_satisfied
        # No requires_first in completion → trivially satisfied
        self.assertTrue(_all_prereqs_satisfied({"type": "talk_to_npc"}, []))

    def test_empty_requires_first_returns_true(self):
        from engine.chain_events import _all_prereqs_satisfied
        self.assertTrue(_all_prereqs_satisfied(
            {"requires_first": []}, []))

    def test_all_indices_satisfied_returns_true(self):
        from engine.chain_events import _all_prereqs_satisfied
        completion = {"requires_first": [{"command": "a"},
                                         {"command": "b"}]}
        self.assertTrue(_all_prereqs_satisfied(completion, [0, 1]))

    def test_partial_satisfaction_returns_false(self):
        from engine.chain_events import _all_prereqs_satisfied
        completion = {"requires_first": [{"command": "a"},
                                         {"command": "b"}]}
        self.assertFalse(_all_prereqs_satisfied(completion, [0]))

    def test_nothing_satisfied_returns_false(self):
        from engine.chain_events import _all_prereqs_satisfied
        completion = {"requires_first": [{"command": "a"}]}
        self.assertFalse(_all_prereqs_satisfied(completion, []))

    def test_malformed_requires_first_returns_true(self):
        # If requires_first is e.g. a string (typo in YAML), don't
        # block the chain — treat as no prereqs.
        from engine.chain_events import _all_prereqs_satisfied
        self.assertTrue(_all_prereqs_satisfied(
            {"requires_first": "look"}, []))


# ═════════════════════════════════════════════════════════════════════
# 4. advance_step clears step progress
# ═════════════════════════════════════════════════════════════════════


class TestAdvanceStepClearsProgress(_F8C2B5IsolatedBase):

    def test_advance_clears_progress(self):
        # Manually populate progress, then advance — progress key
        # should be gone afterward.
        from engine.tutorial_chains import (
            advance_step, load_tutorial_chains,
        )
        char_attrs = {"tutorial_chain": {
            "chain_id": "republic_soldier", "step": 1,
            "started_at": 1000000, "completed_steps": [],
            "completion_state": "active",
            "step_progress_satisfied": [0, 1],
        }}
        corpus = load_tutorial_chains("clone_wars")
        new_step, graduated = advance_step(char_attrs, corpus)
        self.assertIsNotNone(new_step)
        self.assertFalse(graduated)
        self.assertNotIn(
            "step_progress_satisfied",
            char_attrs["tutorial_chain"],
        )


# ═════════════════════════════════════════════════════════════════════
# 5. Single prereq end-to-end: shipwright_trader step 2
# ═════════════════════════════════════════════════════════════════════


class TestSinglePrereq(_F8C2B5IsolatedBase):
    """shipwright_trader step 2:
        completion:
          type: command_executed
          command: examine
          target_contains: subsystem
          requires_first:
            - command: scan
              target_contains: subsystem
    """

    def test_examine_blocked_until_scan(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("shipwright_trader", step=2,
                                completed=[1])

        # examine subsystem — main completion shape — but no scan yet.
        # Must NOT advance.
        result = _run(on_command_executed(
            db, char, "examine", "subsystem hyperdrive"))
        self.assertFalse(result)
        self.assertEqual(_attrs(char)["tutorial_chain"]["step"], 2)
        # Save_character was not called for this attempt — the main
        # completion silently refused with no state change.
        db.save_character.assert_not_awaited()

    def test_scan_records_prereq_then_examine_advances(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("shipwright_trader", step=2,
                                completed=[1])

        # Step A: scan subsystem records prereq 0; no advance.
        result = _run(on_command_executed(
            db, char, "scan", "subsystem hyperdrive"))
        self.assertFalse(result)
        self.assertEqual(_attrs(char)["tutorial_chain"]["step"], 2)
        self.assertEqual(
            _attrs(char)["tutorial_chain"]["step_progress_satisfied"],
            [0],
        )
        db.save_character.assert_awaited()  # state was persisted
        db.save_character.reset_mock()

        # Step B: examine subsystem now fires main completion, all
        # prereqs satisfied → advance.
        result = _run(on_command_executed(
            db, char, "examine", "subsystem hyperdrive"))
        self.assertTrue(result)
        self.assertEqual(_attrs(char)["tutorial_chain"]["step"], 3)
        # Step advance also clears the progress.
        self.assertNotIn(
            "step_progress_satisfied",
            _attrs(char)["tutorial_chain"],
        )

    def test_scan_wrong_target_does_not_satisfy(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("shipwright_trader", step=2,
                                completed=[1])

        # scan engine — wrong target — does NOT satisfy the prereq.
        result = _run(on_command_executed(
            db, char, "scan", "engine compartment"))
        self.assertFalse(result)
        # Prereq slot 0 is still unfilled.
        self.assertEqual(
            _attrs(char)["tutorial_chain"].get("step_progress_satisfied"),
            None,
        )
        db.save_character.assert_not_awaited()


# ═════════════════════════════════════════════════════════════════════
# 6. Two prereqs end-to-end: republic_soldier step 1
# ═════════════════════════════════════════════════════════════════════


class TestTwoPrereqs(_F8C2B5IsolatedBase):
    """republic_soldier step 1:
        completion:
          type: talk_to_npc
          npc: Major Tarrn
          requires_first:
            - command: look
            - command: +sheet
    """

    def test_talk_blocked_with_no_prereqs(self):
        from engine.chain_events import on_talk_to_npc
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        result = _run(on_talk_to_npc(db, char, "Major Tarrn"))
        self.assertFalse(result)
        self.assertEqual(_attrs(char)["tutorial_chain"]["step"], 1)

    def test_talk_blocked_with_one_prereq(self):
        from engine.chain_events import on_command_executed, on_talk_to_npc
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        # Satisfy only one prereq.
        _run(on_command_executed(db, char, "look", ""))
        # talk should still refuse — `+sheet` unsatisfied.
        result = _run(on_talk_to_npc(db, char, "Major Tarrn"))
        self.assertFalse(result)
        self.assertEqual(_attrs(char)["tutorial_chain"]["step"], 1)

    def test_talk_advances_with_both_prereqs(self):
        from engine.chain_events import on_command_executed, on_talk_to_npc
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        _run(on_command_executed(db, char, "look", ""))
        _run(on_command_executed(db, char, "+sheet", ""))
        # Both satisfied → talk advances.
        result = _run(on_talk_to_npc(db, char, "Major Tarrn"))
        self.assertTrue(result)
        self.assertEqual(_attrs(char)["tutorial_chain"]["step"], 2)
        # Progress cleared on advance.
        self.assertNotIn(
            "step_progress_satisfied",
            _attrs(char)["tutorial_chain"],
        )

    def test_prereqs_can_satisfy_in_either_order(self):
        # +sheet first, then look — also advances.
        from engine.chain_events import on_command_executed, on_talk_to_npc
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        _run(on_command_executed(db, char, "+sheet", ""))
        _run(on_command_executed(db, char, "look", ""))
        result = _run(on_talk_to_npc(db, char, "Major Tarrn"))
        self.assertTrue(result)
        self.assertEqual(_attrs(char)["tutorial_chain"]["step"], 2)


# ═════════════════════════════════════════════════════════════════════
# 7. Targeted prereq end-to-end: smuggler step 5
# ═════════════════════════════════════════════════════════════════════


class TestTargetedPrereq(_F8C2B5IsolatedBase):
    """smuggler step 5:
        completion:
          type: command_executed
          command: +factions
          requires_first:
            - command: give
              target_contains: crate
              target_npc: Dyn

    The command path is `+factions`; the prereq is `give crate to Dyn`.
    """

    def test_factions_blocked_until_give(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("smuggler", step=5,
                                completed=[1, 2, 3, 4])
        result = _run(on_command_executed(db, char, "+factions", ""))
        self.assertFalse(result)
        self.assertEqual(_attrs(char)["tutorial_chain"]["step"], 5)

    def test_give_crate_to_dyn_satisfies_prereq(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("smuggler", step=5,
                                completed=[1, 2, 3, 4])
        result = _run(on_command_executed(
            db, char, "give", "crate to Dyn"))
        self.assertFalse(result)  # prereq, not advance
        self.assertEqual(
            _attrs(char)["tutorial_chain"]["step_progress_satisfied"],
            [0],
        )
        # Main completion now fires.
        result = _run(on_command_executed(db, char, "+factions", ""))
        self.assertTrue(result)
        # smuggler has 5 steps total — advancing past 5 graduates.
        self.assertEqual(
            _attrs(char)["tutorial_chain"]["completion_state"],
            "graduated",
        )

    def test_give_to_wrong_npc_does_not_satisfy(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("smuggler", step=5,
                                completed=[1, 2, 3, 4])
        # Voss is the boss, not the buyer. give crate to Voss does
        # not match target_npc=Dyn.
        result = _run(on_command_executed(
            db, char, "give", "crate to Voss"))
        self.assertFalse(result)
        self.assertEqual(
            _attrs(char)["tutorial_chain"].get("step_progress_satisfied"),
            None,
        )


# ═════════════════════════════════════════════════════════════════════
# 8. Idempotency: repeating an already-satisfied event
# ═════════════════════════════════════════════════════════════════════


class TestPrereqIdempotent(_F8C2B5IsolatedBase):

    def test_repeating_look_is_no_op(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        _run(on_command_executed(db, char, "look", ""))
        first_save_count = db.save_character.await_count

        # Look again. Already satisfied — should not record again
        # and should NOT call save_character a second time.
        result = _run(on_command_executed(db, char, "look", ""))
        self.assertFalse(result)
        self.assertEqual(
            _attrs(char)["tutorial_chain"]["step_progress_satisfied"],
            [0],
        )
        self.assertEqual(db.save_character.await_count, first_save_count)


# ═════════════════════════════════════════════════════════════════════
# 9. Main completion silently refused when prereqs incomplete
# ═════════════════════════════════════════════════════════════════════


class TestMainBlockedWhenIncomplete(_F8C2B5IsolatedBase):

    def test_examine_with_no_prereq_does_not_persist(self):
        # The main event hits but prereqs are incomplete. The
        # contract: silently refuse with no state change.
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("shipwright_trader", step=2,
                                completed=[1])
        before_attrs = json.dumps(_attrs(char), sort_keys=True)
        result = _run(on_command_executed(
            db, char, "examine", "subsystem"))
        self.assertFalse(result)
        # No state change.
        after_attrs = json.dumps(_attrs(char), sort_keys=True)
        self.assertEqual(before_attrs, after_attrs)
        db.save_character.assert_not_awaited()


# ═════════════════════════════════════════════════════════════════════
# 10. Unrelated commands ignored
# ═════════════════════════════════════════════════════════════════════


class TestUnrelatedCommandsIgnored(_F8C2B5IsolatedBase):

    def test_random_command_does_not_record_prereq(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        # `west` is not a prereq of step 1.
        result = _run(on_command_executed(db, char, "west", ""))
        self.assertFalse(result)
        self.assertEqual(
            _attrs(char)["tutorial_chain"].get("step_progress_satisfied"),
            None,
        )
        db.save_character.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
