# -*- coding: utf-8 -*-
"""
tests/test_t5_questline_engine.py — T5-questline arc Drop A
(multi-slot chain engine + mid-game questline surface).

Drop A generalizes the single-slot chargen-only chain engine to support
a SECOND, mid-game questline slot (`active_questline`) alongside the
onboarding slot (`tutorial_chain`), without changing onboarding
behavior. This file pins:

  1. The `state_key` parameterization of the tutorial_chains state
     helpers — they operate on whichever slot is named, defaulting to
     the onboarding slot (so legacy callers are byte-neutral).
  2. Slot ISOLATION — questline state never leaks into the onboarding
     slot and vice versa (separate step counters, prereq progress,
     combat tallies).
  3. The `kind` field on TutorialChain (default "tutorial"; "questline"
     parses + validates).
  4. The questline-start engine surface: list/eligibility/start/abandon,
     the one-at-a-time rule, the rep/faction gate reuse, and the
     has_completed_chain durable marker.
  5. Behavior-neutrality: an onboarding-only character (no questline
     slot) is completely unaffected by the dispatcher's both-slot walk.

The full 202-test legacy chain suite (test_f8c2b*, test_f8_*,
test_f7j_*) is the companion neutrality gate — this file adds the
NEW-behavior coverage.
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
# Fixtures
# ─────────────────────────────────────────────────────────────────────


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
    db.get_room = AsyncMock(return_value=None)
    return db


def _build_test_corpus():
    """A 2-chain corpus: one onboarding chain + one questline chain.

    The questline gates on faction_rep>=50 with `republic` via a
    prerequisite descriptor we exercise through is_chain_locked.
    """
    from engine.tutorial_chains import (
        TutorialChain, TutorialStep, Graduation, TutorialChainsCorpus,
    )

    def _step(n, step_npc, ctype, **comp):
        return TutorialStep(
            step=n, title=f"Step {n}", location=f"room_{n}", npc=step_npc,
            npc_role="instructor", teaches=[], objective=f"obj {n}",
            npc_intro="", completion={"type": ctype, **comp},
            npc_complete="", reward={}, next_hint="",
        )

    onboarding = TutorialChain(
        chain_id="ob_chain", chain_name="Onboarding",
        description="d", archetype_label="a", faction_alignment="republic",
        starting_zone="z", starting_room="room_1",
        prerequisites=["chargen_complete"], duration_minutes=10,
        locked=False,
        graduation=Graduation(drop_room="drop_ob"),
        steps=[
            _step(1, "Sergeant", "talk_to_npc", npc="Sergeant"),
            _step(2, "Sergeant", "combat_won",
                  enemy_template="droid", enemy_count=2),
        ],
        kind="tutorial",
    )
    questline = TutorialChain(
        chain_id="ql_master", chain_name="Master Trial",
        description="Prove yourself to the Master.",
        archetype_label="a", faction_alignment="republic",
        starting_zone="z", starting_room="room_1",
        # rep gate is authored as a faction_intent prereq here for the
        # locked-check; the real Drop-B gate also rides curriculum rep.
        prerequisites=[{"faction_intent": "republic"}],
        duration_minutes=30, locked=False,
        graduation=Graduation(drop_room="drop_ql",
                              faction_rep={"republic": 60}),
        steps=[
            _step(1, "Master", "talk_to_npc", npc="Master"),
            _step(2, "Master", "combat_won",
                  enemy_template="guardian", enemy_count=2),
            _step(3, "Master", "talk_to_npc", npc="Master"),
        ],
        kind="questline",
    )
    return TutorialChainsCorpus(
        schema_version=1, chains=[onboarding, questline],
    )


class _QuestlineBase(unittest.TestCase):

    def setUp(self):
        from engine.era_state import set_active_config
        import engine.chain_events as ce
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        ce._reset_corpus_cache()
        # Inject our test corpus into the cache so _get_corpus returns it.
        self._corpus = _build_test_corpus()
        ce._CORPUS_CACHE["clone_wars"] = self._corpus

    def tearDown(self):
        from engine.era_state import clear_active_config
        import engine.chain_events as ce
        clear_active_config()
        ce._reset_corpus_cache()


def _char(attrs: dict = None) -> dict:
    return {
        "id": 7, "name": "PC", "room_id": 100,
        "attributes": json.dumps(attrs or {}),
    }


def _attrs(char: dict) -> dict:
    return json.loads(char["attributes"])


# ═════════════════════════════════════════════════════════════════════
# 1. state_key parameterization + slot isolation
# ═════════════════════════════════════════════════════════════════════


class TestSlotParameterization(_QuestlineBase):

    def test_select_chain_writes_named_slot(self):
        from engine.tutorial_chains import (
            select_chain, _QUESTLINE_KEY, _TUTORIAL_CHAIN_KEY,
        )
        attrs = {}
        ql = self._corpus.by_id()["ql_master"]
        select_chain(attrs, ql, now=1.0, state_key=_QUESTLINE_KEY)
        self.assertIn(_QUESTLINE_KEY, attrs)
        self.assertNotIn(_TUTORIAL_CHAIN_KEY, attrs)
        self.assertEqual(attrs[_QUESTLINE_KEY]["chain_id"], "ql_master")

    def test_default_state_key_is_onboarding(self):
        from engine.tutorial_chains import select_chain, _TUTORIAL_CHAIN_KEY
        attrs = {}
        ob = self._corpus.by_id()["ob_chain"]
        select_chain(attrs, ob, now=1.0)  # no state_key
        self.assertIn(_TUTORIAL_CHAIN_KEY, attrs)

    def test_two_slots_independent(self):
        from engine.tutorial_chains import (
            select_chain, advance_step, get_active_chain_id,
            _QUESTLINE_KEY, _TUTORIAL_CHAIN_KEY,
        )
        attrs = {}
        select_chain(attrs, self._corpus.by_id()["ob_chain"], now=1.0)
        select_chain(attrs, self._corpus.by_id()["ql_master"], now=1.0,
                     state_key=_QUESTLINE_KEY)
        # Advancing the questline must not touch the onboarding slot.
        advance_step(attrs, self._corpus, _QUESTLINE_KEY)
        self.assertEqual(attrs[_QUESTLINE_KEY]["step"], 2)
        self.assertEqual(attrs[_TUTORIAL_CHAIN_KEY]["step"], 1)
        self.assertEqual(
            get_active_chain_id(attrs, _TUTORIAL_CHAIN_KEY), "ob_chain")
        self.assertEqual(
            get_active_chain_id(attrs, _QUESTLINE_KEY), "ql_master")

    def test_combat_tally_per_slot(self):
        from engine.tutorial_chains import (
            select_chain, record_combat_kills, get_combat_kills,
            _QUESTLINE_KEY,
        )
        attrs = {}
        select_chain(attrs, self._corpus.by_id()["ob_chain"], now=1.0)
        select_chain(attrs, self._corpus.by_id()["ql_master"], now=1.0,
                     state_key=_QUESTLINE_KEY)
        record_combat_kills(attrs, "droid", 1)  # onboarding slot
        record_combat_kills(attrs, "guardian", 1, _QUESTLINE_KEY)
        self.assertEqual(get_combat_kills(attrs, "droid"), 1)
        self.assertEqual(get_combat_kills(attrs, "droid", _QUESTLINE_KEY), 0)
        self.assertEqual(
            get_combat_kills(attrs, "guardian", _QUESTLINE_KEY), 1)


# ═════════════════════════════════════════════════════════════════════
# 2. The `kind` field
# ═════════════════════════════════════════════════════════════════════


class TestKindField(_QuestlineBase):

    def test_kind_defaults_to_tutorial(self):
        from engine.tutorial_chains import TutorialChain, Graduation
        c = TutorialChain(
            chain_id="x", chain_name="x", description="d",
            archetype_label="a", faction_alignment=None,
            starting_zone="z", starting_room="r", prerequisites=[],
            duration_minutes=1, locked=False,
            graduation=Graduation(drop_room="d"), steps=[],
        )
        self.assertEqual(c.kind, "tutorial")

    def test_questline_kind_parses(self):
        self.assertEqual(
            self._corpus.by_id()["ql_master"].kind, "questline")

    def test_invalid_kind_rejected_by_parser(self):
        from engine.tutorial_chains import _parse_chain
        bad = {
            "chain_id": "bad", "chain_name": "Bad", "description": "d",
            "archetype_label": "a", "faction_alignment": "republic",
            "starting_zone": "z", "starting_room": "r",
            "prerequisites": [], "duration_minutes": 1, "locked": False,
            "kind": "bogus",
            "graduation": {"drop_room": "d"}, "steps": [],
        }
        chain, errors, _w = _parse_chain(bad, 0)
        self.assertIsNone(chain)
        self.assertTrue(any("kind" in e for e in errors))


# ═════════════════════════════════════════════════════════════════════
# 3. Questline start surface
# ═════════════════════════════════════════════════════════════════════


class TestQuestlineSurface(_QuestlineBase):

    def test_list_questlines_filters_by_kind(self):
        from engine.chain_events import list_questlines
        qls = list_questlines()
        self.assertEqual([q.chain_id for q in qls], ["ql_master"])

    def test_offer_surfaces_for_start_npc_when_eligible(self):
        from engine.chain_events import get_questline_offer
        # faction_intent republic => prereq met => unlocked offer.
        char = _char({"faction_intent": "republic"})
        offer = get_questline_offer(char, "Master")
        self.assertIsNotNone(offer)
        self.assertEqual(offer["chain_id"], "ql_master")
        self.assertFalse(offer["locked"])

    def test_offer_locked_when_gate_unmet(self):
        from engine.chain_events import get_questline_offer
        char = _char({"faction_intent": "hutt_cartel"})
        offer = get_questline_offer(char, "Master")
        self.assertIsNotNone(offer)
        self.assertTrue(offer["locked"])

    def test_no_offer_from_unrelated_npc(self):
        from engine.chain_events import get_questline_offer
        char = _char({"faction_intent": "republic"})
        self.assertIsNone(get_questline_offer(char, "Random Bystander"))

    def test_start_questline_happy_path(self):
        from engine.chain_events import start_questline, has_active_questline
        char = _char({"faction_intent": "republic"})
        db = _make_fake_db()
        ok, msg = _run(start_questline(db, char, "ql_master"))
        self.assertTrue(ok, msg)
        self.assertTrue(has_active_questline(char))

    def test_start_questline_blocked_by_gate(self):
        from engine.chain_events import start_questline
        char = _char({"faction_intent": "hutt_cartel"})
        db = _make_fake_db()
        ok, _msg = _run(start_questline(db, char, "ql_master"))
        self.assertFalse(ok)

    def test_cannot_start_two_questlines(self):
        from engine.chain_events import start_questline
        char = _char({"faction_intent": "republic"})
        db = _make_fake_db()
        ok1, _ = _run(start_questline(db, char, "ql_master"))
        self.assertTrue(ok1)
        ok2, msg2 = _run(start_questline(db, char, "ql_master"))
        self.assertFalse(ok2)
        self.assertIn("already", msg2.lower())

    def test_start_rejects_onboarding_chain_id(self):
        # The onboarding chain is kind=tutorial — not startable as a
        # questline even by id.
        from engine.chain_events import start_questline
        char = _char({"faction_intent": "republic"})
        db = _make_fake_db()
        ok, _msg = _run(start_questline(db, char, "ob_chain"))
        self.assertFalse(ok)

    def test_abandon_clears_slot(self):
        from engine.chain_events import (
            start_questline, abandon_questline, has_active_questline,
        )
        char = _char({"faction_intent": "republic"})
        db = _make_fake_db()
        _run(start_questline(db, char, "ql_master"))
        ok, _msg = _run(abandon_questline(db, char))
        self.assertTrue(ok)
        self.assertFalse(has_active_questline(char))

    def test_completed_questline_not_reoffered(self):
        from engine.chain_events import get_questline_offer
        from engine.tutorial_chains import _QUESTLINE_KEY
        char = _char({
            "faction_intent": "republic",
            _QUESTLINE_KEY: {
                "chain_id": "ql_master", "step": 3,
                "completion_state": "graduated", "completed_steps": [1, 2, 3],
            },
        })
        # Graduated questline lives in the slot; offer must be suppressed
        # (both because it's completed AND because active-check passes
        # only for non-graduated — here it's graduated so not "active").
        self.assertIsNone(get_questline_offer(char, "Master"))


# ═════════════════════════════════════════════════════════════════════
# 4. Dispatcher both-slot walk advances the right slot
# ═════════════════════════════════════════════════════════════════════


class TestDispatcherBothSlots(_QuestlineBase):

    def test_talk_advances_questline_slot(self):
        from engine.chain_events import start_questline, on_talk_to_npc
        from engine.tutorial_chains import _QUESTLINE_KEY
        char = _char({"faction_intent": "republic"})
        db = _make_fake_db()
        _run(start_questline(db, char, "ql_master"))
        # Step 1 of the questline completes on talk_to_npc "Master".
        advanced = _run(on_talk_to_npc(db, char, "Master"))
        self.assertTrue(advanced)
        self.assertEqual(_attrs(char)[_QUESTLINE_KEY]["step"], 2)

    def test_onboarding_only_char_unaffected_by_questline_walk(self):
        # A char with ONLY an onboarding chain advances normally; the
        # questline-slot branch of the dispatcher is a clean no-op.
        from engine.chain_events import on_talk_to_npc
        from engine.tutorial_chains import (
            select_chain, _TUTORIAL_CHAIN_KEY, _QUESTLINE_KEY,
        )
        attrs = {}
        select_chain(attrs, self._corpus.by_id()["ob_chain"], now=1.0)
        char = _char(attrs)
        db = _make_fake_db()
        advanced = _run(on_talk_to_npc(db, char, "Sergeant"))
        self.assertTrue(advanced)
        self.assertEqual(_attrs(char)[_TUTORIAL_CHAIN_KEY]["step"], 2)
        self.assertNotIn(_QUESTLINE_KEY, _attrs(char))

    def test_questline_multi_enemy_combat_tally(self):
        # The questline step 2 needs 2 'guardian' kills across separate
        # combats — the per-slot tally must accumulate.
        from engine.chain_events import start_questline, on_talk_to_npc, on_combat_won
        from engine.tutorial_chains import _QUESTLINE_KEY
        char = _char({"faction_intent": "republic"})
        db = _make_fake_db()
        _run(start_questline(db, char, "ql_master"))
        _run(on_talk_to_npc(db, char, "Master"))  # -> step 2
        self.assertEqual(_attrs(char)[_QUESTLINE_KEY]["step"], 2)
        # First kill: tally=1, no advance.
        adv1 = _run(on_combat_won(db, char, "guardian", 1))
        self.assertFalse(adv1)
        self.assertEqual(_attrs(char)[_QUESTLINE_KEY]["step"], 2)
        # Second kill: tally=2 -> advance to step 3.
        adv2 = _run(on_combat_won(db, char, "guardian", 1))
        self.assertTrue(adv2)
        self.assertEqual(_attrs(char)[_QUESTLINE_KEY]["step"], 3)


# ═════════════════════════════════════════════════════════════════════
# 5. Pending-teleport flag isolation (regression for the Drop-A blocker:
#    apply_step_teleport / apply_graduation / _clear_pending must stamp
#    the questline slot, NOT the onboarding slot, for questline advances)
# ═════════════════════════════════════════════════════════════════════


class TestTeleportSlotIsolation(_QuestlineBase):

    def test_questline_step_teleport_stamps_questline_slot(self):
        # A questline step-advance teleport must put pending_step_room_id
        # on the QUESTLINE slot, never on the (possibly graduated)
        # onboarding slot.
        from engine.chain_graduation import apply_step_teleport
        from engine.tutorial_chains import (
            select_chain, _QUESTLINE_KEY, _TUTORIAL_CHAIN_KEY,
        )
        attrs = {}
        # Simulate a veteran: onboarding graduated, questline active.
        attrs[_TUTORIAL_CHAIN_KEY] = {
            "chain_id": "ob_chain", "step": 2,
            "completion_state": "graduated", "completed_steps": [1, 2],
        }
        select_chain(attrs, self._corpus.by_id()["ql_master"], now=1.0,
                     state_key=_QUESTLINE_KEY)
        char = {"id": 7, "room_id": 100,
                "attributes": json.dumps(attrs)}
        db = _make_fake_db()
        db.get_room_by_slug = AsyncMock(return_value={"id": 200})

        _run(apply_step_teleport(db, char, attrs, "room_2",
                                 _QUESTLINE_KEY))
        # The questline slot carries the pending flag; onboarding clean.
        self.assertIn("pending_step_room_id", attrs[_QUESTLINE_KEY])
        self.assertNotIn("pending_step_room_id",
                         attrs[_TUTORIAL_CHAIN_KEY])

    def test_questline_graduation_stamps_questline_slot(self):
        from engine.chain_graduation import apply_graduation
        from engine.tutorial_chains import (
            select_chain, _QUESTLINE_KEY, _TUTORIAL_CHAIN_KEY,
        )
        attrs = {}
        attrs[_TUTORIAL_CHAIN_KEY] = {
            "chain_id": "ob_chain", "step": 2,
            "completion_state": "graduated", "completed_steps": [1, 2],
        }
        select_chain(attrs, self._corpus.by_id()["ql_master"], now=1.0,
                     state_key=_QUESTLINE_KEY)
        char = {"id": 7, "room_id": 100,
                "attributes": json.dumps(attrs)}
        db = _make_fake_db()
        db.get_room_by_slug = AsyncMock(return_value={"id": 300})

        _run(apply_graduation(db, char, attrs, "drop_ql", _QUESTLINE_KEY))
        self.assertIn("pending_drop_room_id", attrs[_QUESTLINE_KEY])
        self.assertNotIn("pending_drop_room_id",
                         attrs[_TUTORIAL_CHAIN_KEY])

    def test_full_questline_graduation_via_dispatcher(self):
        # End-to-end: start the questline, walk all 3 steps via the
        # public hooks, and confirm it graduates in the QUESTLINE slot
        # while the onboarding slot is untouched throughout.
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_combat_won,
        )
        from engine.tutorial_chains import (
            _QUESTLINE_KEY, _TUTORIAL_CHAIN_KEY, is_chain_complete,
        )
        char = _char({"faction_intent": "republic"})
        db = _make_fake_db()
        db.get_room_by_slug = AsyncMock(return_value={"id": 500})
        _run(start_questline(db, char, "ql_master"))
        _run(on_talk_to_npc(db, char, "Master"))      # step 1 -> 2
        _run(on_combat_won(db, char, "guardian", 1))   # tally 1
        _run(on_combat_won(db, char, "guardian", 1))   # tally 2 -> step 3
        _run(on_talk_to_npc(db, char, "Master"))      # step 3 -> graduate
        attrs = _attrs(char)
        self.assertTrue(is_chain_complete(attrs, _QUESTLINE_KEY))
        # Onboarding slot was never created/touched.
        self.assertNotIn(_TUTORIAL_CHAIN_KEY, attrs)


# ═════════════════════════════════════════════════════════════════════
# 6. Offer prefers an unlocked questline over a locked one (same NPC)
# ═════════════════════════════════════════════════════════════════════


class TestOfferUnlockedPreference(_QuestlineBase):

    def test_unlocked_offer_wins_over_locked_same_npc(self):
        # Author a 2nd questline sharing the start-NPC "Master": the
        # first (ql_master) is locked for a hutt PC; a 2nd, unlocked one
        # must still be offered rather than suppressed.
        import engine.chain_events as ce
        from engine.tutorial_chains import (
            TutorialChain, TutorialStep, Graduation,
        )

        def _step(npc):
            return TutorialStep(
                step=1, title="t", location="r", npc=npc,
                npc_role="instructor", teaches=[], objective="o",
                npc_intro="", completion={"type": "talk_to_npc", "npc": npc},
                npc_complete="", reward={}, next_hint="",
            )
        open_ql = TutorialChain(
            chain_id="ql_open", chain_name="Open Trial", description="d",
            archetype_label="a", faction_alignment=None,
            starting_zone="z", starting_room="r",
            prerequisites=[],  # no gate -> always unlocked
            duration_minutes=1, locked=False,
            graduation=Graduation(drop_room="d"), steps=[_step("Master")],
            kind="questline",
        )
        # Append to the cached corpus (ql_master is republic-gated).
        self._corpus.chains.append(open_ql)
        ce._CORPUS_CACHE["clone_wars"] = self._corpus

        from engine.chain_events import get_questline_offer
        char = _char({"faction_intent": "hutt_cartel"})  # locks ql_master
        offer = get_questline_offer(char, "Master")
        self.assertIsNotNone(offer)
        self.assertEqual(offer["chain_id"], "ql_open")
        self.assertFalse(offer["locked"])


if __name__ == "__main__":
    unittest.main()
