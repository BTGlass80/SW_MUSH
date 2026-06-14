# -*- coding: utf-8 -*-
"""
tests/test_f8c2b_chain_events.py — F.8.c.2.b Phase 1 tests.

F.8.c.2.b Phase 1 (May 5 2026) wires four `completion.type` values
into engine event hooks, dispatching to
``engine.tutorial_chains.advance_step`` from runtime seams:

  * ``command_executed`` — parser/commands.py CommandParser._execute
  * ``talk_to_npc``      — parser/npc_commands.py _post_talk_hooks
  * ``combat_won``       — parser/combat_commands.py _try_auto_resolve
  * ``room_entered``     — parser/builtin_commands.py _post_move_hooks

Phase 1 NON-goals (deferred):
  * ``mission_accepted`` / ``mission_completed`` / ``bounty_accepted``
  * ``item_acquired`` / ``item_used``
  * ``skill_check_passed`` (with ``on_fail`` / ``fallback`` extensions)
  * ``requires_first`` sub-step tracking

Test sections
-------------
  1. TestCorpusCache               — module-level corpus cache hygiene
  2. TestAttrLoadHelpers           — JSON string ↔ dict normalization
  3. TestCommandExecutedMatcher    — _match_command_executed cases
  4. TestTalkToNpcMatcher          — _match_talk_to_npc cases
  5. TestCombatWonMatcher          — _match_combat_won cases
  6. TestRoomEnteredMatcher        — _match_room_entered cases
  7. TestOnCommandExecutedDispatch — end-to-end command_executed
  8. TestOnTalkToNpcDispatch       — end-to-end talk_to_npc
  9. TestOnCombatWonDispatch       — end-to-end combat_won
 10. TestOnRoomEnteredDispatch     — end-to-end room_entered
 11. TestGraduation                — last-step advance graduates chain
 12. TestNoActiveChainNoOp         — without a chain in attrs, all
                                     hooks return False
 13. TestExceptionFailsafe         — buggy DB / corpus is swallowed
 14. TestActiveStepInfoView        — get_active_step_info shape
 15. TestRepublicSoldierE2E        — walk the republic_soldier chain
                                     end-to-end with real chains.yaml
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
# Test isolation: every test case resets the era_state config and
# the chain_events corpus cache at tearDown so cross-file sweeps in
# CI don't bleed CW state into GCW-default tests downstream.
# ─────────────────────────────────────────────────────────────────────


class _F8C2BIsolatedBase(unittest.TestCase):

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


def _async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    """Helper: run a coroutine to completion in a fresh loop."""
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_fake_db():
    """Return a MagicMock with async save_character + get_npc."""
    db = MagicMock()
    db.save_character = AsyncMock()
    db.get_npc = AsyncMock(return_value=None)
    db.get_character = AsyncMock(return_value=None)
    return db


def _char_with_chain(chain_id: str, step: int = 1,
                    completed: list = None) -> dict:
    attrs = {
        "tutorial_chain": {
            "chain_id": chain_id,
            "step": step,
            "started_at": 1000000,
            "completed_steps": list(completed or []),
            "completion_state": "active",
        }
    }
    return {
        "id": 42,
        "name": "Test PC",
        "attributes": json.dumps(attrs),
    }


def _char_no_chain() -> dict:
    return {
        "id": 99,
        "name": "Test PC",
        "attributes": json.dumps({}),
    }


# ─────────────────────────────────────────────────────────────────────
# 1. Corpus cache
# ─────────────────────────────────────────────────────────────────────


class TestCorpusCache(_F8C2BIsolatedBase):

    def test_corpus_loads_for_clone_wars(self):
        from engine.chain_events import _get_corpus
        corpus = _get_corpus("clone_wars")
        self.assertIsNotNone(corpus)
        self.assertGreater(len(corpus.chains), 0)

    def test_corpus_cached_across_calls(self):
        from engine.chain_events import _get_corpus
        c1 = _get_corpus("clone_wars")
        c2 = _get_corpus("clone_wars")
        self.assertIs(c1, c2)

    def test_corpus_returns_none_for_unknown_era(self):
        from engine.chain_events import _get_corpus
        c = _get_corpus("unknown_era_xyz")
        self.assertIsNone(c)

    def test_reset_corpus_cache_drops_entries(self):
        from engine.chain_events import _get_corpus, _reset_corpus_cache
        _get_corpus("clone_wars")
        _reset_corpus_cache()
        # After reset, a fresh load happens — we don't peek at cache
        # internals; just confirm a re-load still works.
        c = _get_corpus("clone_wars")
        self.assertIsNotNone(c)


# ─────────────────────────────────────────────────────────────────────
# 2. Attribute load/save normalization
# ─────────────────────────────────────────────────────────────────────


class TestAttrLoadHelpers(_F8C2BIsolatedBase):

    def test_load_attrs_from_json_string(self):
        from engine.chain_events import _load_attrs
        char = {"attributes": json.dumps({"foo": "bar"})}
        result = _load_attrs(char)
        self.assertEqual(result, {"foo": "bar"})

    def test_load_attrs_from_dict(self):
        from engine.chain_events import _load_attrs
        char = {"attributes": {"foo": "bar"}}
        self.assertEqual(_load_attrs(char), {"foo": "bar"})

    def test_load_attrs_from_empty(self):
        from engine.chain_events import _load_attrs
        self.assertEqual(_load_attrs({"attributes": ""}), {})
        self.assertEqual(_load_attrs({"attributes": "{}"}), {})
        self.assertEqual(_load_attrs({}), {})

    def test_load_attrs_from_malformed_json(self):
        from engine.chain_events import _load_attrs
        char = {"id": 7, "attributes": "{this is not json"}
        # Should NOT raise; returns {} and logs a warning
        self.assertEqual(_load_attrs(char), {})

    def test_persist_attrs_writes_string_back(self):
        from engine.chain_events import _persist_attrs
        db = _make_fake_db()
        char = {"id": 42}
        _run(_persist_attrs(db, char, {"foo": 1}))
        self.assertEqual(json.loads(char["attributes"]), {"foo": 1})
        db.save_character.assert_awaited_once()
        kwargs = db.save_character.await_args.kwargs
        self.assertEqual(kwargs["attributes"], json.dumps({"foo": 1}))


# ─────────────────────────────────────────────────────────────────────
# 3. command_executed matcher
# ─────────────────────────────────────────────────────────────────────


class TestCommandExecutedMatcher(_F8C2BIsolatedBase):

    def test_command_only_matches(self):
        from engine.chain_events import _match_command_executed
        c = {"command": "+factions"}
        self.assertTrue(_match_command_executed(c, "+factions", ""))
        self.assertTrue(_match_command_executed(c, "+FACTIONS", ""))
        self.assertFalse(_match_command_executed(c, "+sheet", ""))

    def test_command_with_target_contains(self):
        from engine.chain_events import _match_command_executed
        c = {"command": "examine", "target_contains": "subsystem"}
        self.assertTrue(_match_command_executed(c, "examine",
                                                "subsystem"))
        self.assertTrue(_match_command_executed(c, "examine",
                                                "the subsystem array"))
        self.assertFalse(_match_command_executed(c, "examine",
                                                 "crate"))
        # Wrong command, even if args match
        self.assertFalse(_match_command_executed(c, "look",
                                                 "subsystem"))

    def test_command_with_contains_any(self):
        from engine.chain_events import _match_command_executed
        c = {"command": "say",
             "contains_any": ["yes", "i'll do it", "agreed"]}
        self.assertTrue(_match_command_executed(c, "say", "yes"))
        self.assertTrue(_match_command_executed(c, "say", "Yes!"))
        self.assertTrue(_match_command_executed(c, "say", "I'll do it"))
        self.assertTrue(_match_command_executed(c, "say", "agreed"))
        self.assertFalse(_match_command_executed(c, "say", "no"))
        self.assertFalse(_match_command_executed(c, "say", ""))

    def test_command_empty_command_field_no_match(self):
        from engine.chain_events import _match_command_executed
        self.assertFalse(_match_command_executed({}, "look", ""))
        self.assertFalse(_match_command_executed({"command": ""},
                                                 "look", ""))


# ─────────────────────────────────────────────────────────────────────
# 4. talk_to_npc matcher
# ─────────────────────────────────────────────────────────────────────


class TestTalkToNpcMatcher(_F8C2BIsolatedBase):

    def test_exact_match_case_insensitive(self):
        from engine.chain_events import _match_talk_to_npc
        c = {"npc": "Major Tarrn"}
        self.assertTrue(_match_talk_to_npc(c, "Major Tarrn"))
        self.assertTrue(_match_talk_to_npc(c, "major tarrn"))
        self.assertTrue(_match_talk_to_npc(c, "  Major Tarrn  "))

    def test_partial_does_not_match(self):
        from engine.chain_events import _match_talk_to_npc
        c = {"npc": "Major Tarrn"}
        self.assertFalse(_match_talk_to_npc(c, "Tarrn"))
        self.assertFalse(_match_talk_to_npc(c, "Major"))
        self.assertFalse(_match_talk_to_npc(c, "Major Tarrn-Smith"))

    def test_empty_inputs_no_match(self):
        from engine.chain_events import _match_talk_to_npc
        self.assertFalse(_match_talk_to_npc({}, "Major Tarrn"))
        self.assertFalse(_match_talk_to_npc({"npc": "Major Tarrn"}, ""))
        self.assertFalse(_match_talk_to_npc({"npc": ""}, "Major Tarrn"))


# ─────────────────────────────────────────────────────────────────────
# 5. combat_won matcher
# ─────────────────────────────────────────────────────────────────────


class TestCombatWonMatcher(_F8C2BIsolatedBase):

    def test_template_match_with_default_count(self):
        from engine.chain_events import _match_combat_won
        c = {"enemy_template": "b1_battle_droid_sim"}
        self.assertTrue(_match_combat_won(c, "b1_battle_droid_sim", 1))
        self.assertTrue(_match_combat_won(c, "b1_battle_droid_sim", 5))

    def test_template_match_with_count_floor(self):
        from engine.chain_events import _match_combat_won
        c = {"enemy_template": "b1_battle_droid_sim", "enemy_count": 2}
        self.assertFalse(_match_combat_won(c, "b1_battle_droid_sim", 1))
        self.assertTrue(_match_combat_won(c, "b1_battle_droid_sim", 2))
        self.assertTrue(_match_combat_won(c, "b1_battle_droid_sim", 3))

    def test_template_mismatch(self):
        from engine.chain_events import _match_combat_won
        c = {"enemy_template": "b1_battle_droid_sim"}
        self.assertFalse(_match_combat_won(c, "republic_clone_sim", 5))
        self.assertFalse(_match_combat_won(c, "", 1))

    def test_extra_step_effect_fields_dont_break_match(self):
        from engine.chain_events import _match_combat_won
        # ally_count and stun_bonus_credits are step-effect fields,
        # not match constraints. Match should succeed regardless.
        c = {"enemy_template": "republic_clone_sim",
             "enemy_count": 2, "ally_count": 2,
             "stun_bonus_credits": 200}
        self.assertTrue(_match_combat_won(c, "republic_clone_sim", 2))


# ─────────────────────────────────────────────────────────────────────
# 6. room_entered matcher
# ─────────────────────────────────────────────────────────────────────


class TestRoomEnteredMatcher(_F8C2BIsolatedBase):

    def test_slug_match_case_insensitive(self):
        from engine.chain_events import _match_room_entered
        c = {"room": "commercial_district_landing_zone"}
        self.assertTrue(_match_room_entered(
            c, "commercial_district_landing_zone"))
        self.assertTrue(_match_room_entered(
            c, "COMMERCIAL_DISTRICT_LANDING_ZONE"))

    def test_slug_mismatch(self):
        from engine.chain_events import _match_room_entered
        c = {"room": "commercial_district_landing_zone"}
        self.assertFalse(_match_room_entered(c, "tipoca_briefing_room"))
        self.assertFalse(_match_room_entered(c, ""))

    def test_empty_completion_room_no_match(self):
        from engine.chain_events import _match_room_entered
        self.assertFalse(_match_room_entered(
            {}, "commercial_district_landing_zone"))


# ─────────────────────────────────────────────────────────────────────
# 7. on_command_executed dispatch
# ─────────────────────────────────────────────────────────────────────


class TestOnCommandExecutedDispatch(_F8C2BIsolatedBase):

    def test_advances_when_command_matches(self):
        # republic_soldier step 5 has completion.command = "+factions"
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=5,
                                completed=[1, 2, 3, 4])
        result = _run(on_command_executed(db, char, "+factions", ""))
        self.assertTrue(result)
        # State persisted
        db.save_character.assert_awaited()
        attrs = json.loads(char["attributes"])
        ch_state = attrs["tutorial_chain"]
        # republic_soldier has 5 steps total → step 5 is the last;
        # advancing past it graduates.
        self.assertEqual(ch_state["completion_state"], "graduated")
        self.assertIn(5, ch_state["completed_steps"])

    def test_does_not_advance_on_wrong_command(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=5,
                                completed=[1, 2, 3, 4])
        result = _run(on_command_executed(db, char, "+sheet", ""))
        self.assertFalse(result)
        db.save_character.assert_not_awaited()

    def test_does_not_advance_on_wrong_event_type(self):
        # republic_soldier step 1 expects talk_to_npc, not
        # command_executed. Even with a matching command, the hook
        # must not advance.
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        result = _run(on_command_executed(db, char, "look", ""))
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────
# 8. on_talk_to_npc dispatch
# ─────────────────────────────────────────────────────────────────────


class TestOnTalkToNpcDispatch(_F8C2BIsolatedBase):

    def test_advances_when_npc_matches(self):
        # republic_soldier step 1: talk Major Tarrn AFTER looking and
        # checking the sheet. F.8.c.2.b₅ (May 5 2026) made
        # `requires_first` gating, not advisory — the talk is now
        # blocked until the prereqs fire.
        from engine.chain_events import on_command_executed, on_talk_to_npc
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        # Satisfy the two prereqs first (look, +sheet). Each call
        # returns False (no advance) but records the prereq.
        self.assertFalse(_run(on_command_executed(db, char, "look", "")))
        self.assertFalse(_run(on_command_executed(db, char, "+sheet", "")))
        # Now the talk fires the main completion and advances.
        result = _run(on_talk_to_npc(db, char, "Major Tarrn"))
        self.assertTrue(result)
        attrs = json.loads(char["attributes"])
        ch_state = attrs["tutorial_chain"]
        self.assertEqual(ch_state["step"], 2)
        self.assertEqual(ch_state["completion_state"], "active")

    def test_does_not_advance_on_wrong_npc(self):
        from engine.chain_events import on_talk_to_npc
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        result = _run(on_talk_to_npc(db, char, "Sergeant Drix"))
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────
# 9. on_combat_won dispatch
# ─────────────────────────────────────────────────────────────────────


class TestOnCombatWonDispatch(_F8C2BIsolatedBase):

    def test_advances_with_template_match(self):
        # republic_soldier step 2: combat_won b1_battle_droid_sim ×2
        from engine.chain_events import on_combat_won
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=2,
                                completed=[1])
        result = _run(on_combat_won(
            db, char, "b1_battle_droid_sim", 2))
        self.assertTrue(result)
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs["tutorial_chain"]["step"], 3)

    def test_does_not_advance_below_count(self):
        from engine.chain_events import on_combat_won
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=2,
                                completed=[1])
        result = _run(on_combat_won(
            db, char, "b1_battle_droid_sim", 1))
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────
# 10. on_room_entered dispatch
# ─────────────────────────────────────────────────────────────────────


class TestOnRoomEnteredDispatch(_F8C2BIsolatedBase):
    """The `on_room_entered` hook is still wired (MoveCommand fires it
    on every move) and the `_match_room_entered` matcher is unit-tested
    separately. But as of F.8.c.2.e NO chain step uses a `room_entered`
    completion: such steps are unreachable in exit-less tutorial rooms
    (the inter-step teleport never fires the move hook), so the two that
    existed (republic_soldier s4, smuggler s3) were re-authored to
    talk_to_npc. The hook is therefore DORMANT — it must safely no-op
    against the live corpus rather than false-advance a non-room_entered
    step. These tests pin that dormant-but-safe behavior. The positive
    advance path is exercised by the matcher unit tests
    (TestMatchRoomEntered) without depending on a corpus step that would
    re-introduce the stranding bug."""

    def test_room_entered_dormant_does_not_false_advance(self):
        # republic_soldier step 4 is now talk_to_npc (was room_entered).
        # Entering its former target room must NOT advance the chain —
        # the hook stays dormant because no step's completion is
        # room_entered.
        from engine.chain_events import on_room_entered
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=4,
                                completed=[1, 2, 3])
        result = _run(on_room_entered(
            db, char, "commercial_district_landing_zone"))
        self.assertFalse(result)
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs["tutorial_chain"]["step"], 4)

    def test_no_chain_step_uses_room_entered(self):
        """Guard: if a future drop re-introduces a room_entered
        completion, this fails — forcing a deliberate decision about
        reachability (the F.8.c.2.e invariant)."""
        import yaml
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        path = (root / "data" / "worlds" / "clone_wars" /
                "tutorials" / "chains.yaml")
        corpus = yaml.safe_load(path.read_text(encoding="utf-8"))
        offenders = []
        for c in corpus["chains"]:
            for s in c.get("steps") or []:
                if (s.get("completion") or {}).get("type") == "room_entered":
                    offenders.append(f"{c['chain_id']} step {s['step']}")
        self.assertEqual(
            offenders, [],
            "room_entered completions are unreachable in exit-less "
            "tutorial rooms (F.8.c.2.e). Re-author to a producible "
            "completion or wire an exit/teleport that fires "
            "on_room_entered. Offenders: " + ", ".join(offenders),
        )

    def test_does_not_advance_on_wrong_slug(self):
        from engine.chain_events import on_room_entered
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=4,
                                completed=[1, 2, 3])
        result = _run(on_room_entered(
            db, char, "tipoca_briefing_room"))
        self.assertFalse(result)

    def test_empty_slug_returns_false(self):
        # legacy rooms without properties.slug — must no-op silently
        from engine.chain_events import on_room_entered
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=4,
                                completed=[1, 2, 3])
        result = _run(on_room_entered(db, char, ""))
        self.assertFalse(result)
        db.save_character.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────
# 11. Graduation
# ─────────────────────────────────────────────────────────────────────


class TestGraduation(_F8C2BIsolatedBase):

    def test_advancing_past_last_step_graduates(self):
        # republic_soldier has exactly 5 steps; step 5 is +factions.
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=5,
                                completed=[1, 2, 3, 4])
        _run(on_command_executed(db, char, "+factions", ""))
        attrs = json.loads(char["attributes"])
        self.assertEqual(
            attrs["tutorial_chain"]["completion_state"], "graduated"
        )

    def test_post_graduation_hooks_no_op(self):
        # After graduation, the active-chain check returns None,
        # so additional hooks must not advance or save.
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=5,
                                completed=[1, 2, 3, 4])
        # First call graduates
        _run(on_command_executed(db, char, "+factions", ""))
        db.save_character.reset_mock()
        # Second call must no-op
        result = _run(on_command_executed(db, char, "+factions", ""))
        self.assertFalse(result)
        db.save_character.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────
# 12. No active chain → no-op
# ─────────────────────────────────────────────────────────────────────


class TestNoActiveChainNoOp(_F8C2BIsolatedBase):

    def test_command_no_chain(self):
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        char = _char_no_chain()
        self.assertFalse(_run(on_command_executed(
            db, char, "+factions", "")))

    def test_talk_no_chain(self):
        from engine.chain_events import on_talk_to_npc
        db = _make_fake_db()
        char = _char_no_chain()
        self.assertFalse(_run(on_talk_to_npc(
            db, char, "Major Tarrn")))

    def test_combat_no_chain(self):
        from engine.chain_events import on_combat_won
        db = _make_fake_db()
        char = _char_no_chain()
        self.assertFalse(_run(on_combat_won(
            db, char, "b1_battle_droid_sim", 5)))

    def test_room_no_chain(self):
        from engine.chain_events import on_room_entered
        db = _make_fake_db()
        char = _char_no_chain()
        self.assertFalse(_run(on_room_entered(
            db, char, "commercial_district_landing_zone")))


# ─────────────────────────────────────────────────────────────────────
# 13. Failure tolerance
# ─────────────────────────────────────────────────────────────────────


class TestExceptionFailsafe(_F8C2BIsolatedBase):

    def test_db_save_failure_is_swallowed(self):
        # If db.save_character raises, the hook must NOT propagate.
        # Player commands always finish; chain advancement is
        # additive UI.
        from engine.chain_events import on_command_executed
        db = _make_fake_db()
        db.save_character = AsyncMock(
            side_effect=RuntimeError("DB exploded")
        )
        char = _char_with_chain("republic_soldier", step=5,
                                completed=[1, 2, 3, 4])
        # Must not raise
        result = _run(on_command_executed(db, char, "+factions", ""))
        # Either succeeded silently (not what we want) or returned
        # False after catching — both are acceptable; what matters
        # is no exception propagates.
        self.assertIsInstance(result, bool)


# ─────────────────────────────────────────────────────────────────────
# 14. Active step info view
# ─────────────────────────────────────────────────────────────────────


class TestActiveStepInfoView(_F8C2BIsolatedBase):

    def test_returns_step_metadata(self):
        from engine.chain_events import get_active_step_info
        char = _char_with_chain("republic_soldier", step=2,
                                completed=[1])
        info = get_active_step_info(char)
        self.assertIsNotNone(info)
        self.assertEqual(info["chain_id"], "republic_soldier")
        self.assertEqual(info["step"], 2)
        self.assertEqual(info["completion_type"], "combat_won")
        self.assertIn("title", info)
        self.assertIn("location", info)

    def test_returns_none_for_no_chain(self):
        from engine.chain_events import get_active_step_info
        info = get_active_step_info(_char_no_chain())
        self.assertIsNone(info)

    def test_returns_none_for_graduated(self):
        from engine.chain_events import get_active_step_info
        attrs = {
            "tutorial_chain": {
                "chain_id": "republic_soldier",
                "step": 5,
                "started_at": 1000000,
                "completed_steps": [1, 2, 3, 4, 5],
                "completion_state": "graduated",
            }
        }
        char = {"id": 5, "attributes": json.dumps(attrs)}
        info = get_active_step_info(char)
        self.assertIsNone(info)


# ─────────────────────────────────────────────────────────────────────
# 15. Republic Soldier chain — full E2E walkthrough
# ─────────────────────────────────────────────────────────────────────


class TestRepublicSoldierE2E(_F8C2BIsolatedBase):
    """Walk a fresh character through every step of the republic_soldier
    chain using the four Phase 1 hooks. Asserts the chain advances
    correctly through all 5 steps and graduates at the end.

    This exercises the actual chains.yaml contents — if a future
    chain refactor changes step semantics, this test will catch it.
    """

    def test_full_walkthrough(self):
        from engine.chain_events import (
            on_command_executed, on_talk_to_npc,
            on_combat_won, on_room_entered,
            get_active_step_info,
        )

        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)

        # Step 1: talk_to_npc Major Tarrn (with Phase 3 prereqs).
        # F.8.c.2.b₅: republic_soldier step 1 has
        # requires_first: [look, +sheet]. Both must fire before the
        # talk advances the step.
        info = get_active_step_info(char)
        self.assertEqual(info["step"], 1)
        self.assertEqual(info["completion_type"], "talk_to_npc")
        self.assertFalse(_run(on_command_executed(db, char, "look", "")))
        self.assertFalse(_run(on_command_executed(db, char, "+sheet", "")))
        self.assertTrue(_run(on_talk_to_npc(db, char, "Major Tarrn")))

        # Step 2: combat_won b1_battle_droid_sim ×2
        info = get_active_step_info(char)
        self.assertEqual(info["step"], 2)
        self.assertEqual(info["completion_type"], "combat_won")
        self.assertTrue(_run(on_combat_won(
            db, char, "b1_battle_droid_sim", 2)))

        # Step 3: mission_accepted (Phase 2 — for now, Phase 1 hooks
        # don't fire on mission_accepted; manually advance via
        # tutorial_chains.advance_step to simulate Phase 2 behavior
        # so we can keep walking the chain.
        info = get_active_step_info(char)
        self.assertEqual(info["step"], 3)
        self.assertEqual(info["completion_type"], "mission_accepted")
        # Manually advance past step 3 using the underlying state
        # machine — Phase 2 will do this from the mission seam.
        from engine.tutorial_chains import (
            advance_step, load_tutorial_chains,
        )
        attrs = json.loads(char["attributes"])
        corpus = load_tutorial_chains("clone_wars")
        advance_step(attrs, corpus)
        char["attributes"] = json.dumps(attrs)

        # Step 4: talk_to_npc Pilot CT-7567 (F.8.c.2.e — was
        # room_entered commercial_district_landing_zone, which is
        # unreachable in exit-less tutorial rooms; re-anchored to
        # talking to the pilot present at the transport pad).
        info = get_active_step_info(char)
        self.assertEqual(info["step"], 4)
        self.assertEqual(info["completion_type"], "talk_to_npc")
        self.assertTrue(_run(on_talk_to_npc(db, char, "Pilot CT-7567")))

        # Step 5: command_executed +factions
        info = get_active_step_info(char)
        self.assertEqual(info["step"], 5)
        self.assertEqual(info["completion_type"], "command_executed")
        self.assertTrue(_run(on_command_executed(
            db, char, "+factions", "")))

        # Graduated
        info = get_active_step_info(char)
        self.assertIsNone(info)
        attrs = json.loads(char["attributes"])
        self.assertEqual(
            attrs["tutorial_chain"]["completion_state"], "graduated"
        )


if __name__ == "__main__":
    unittest.main()
