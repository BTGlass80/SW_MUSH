# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_sealed_ledger.py — T3.24 generalized
quest expansion, ninth slice.

Proves the NINTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Sealed Ledger" (coruscant_works_sealed_ledger) — is shipped
correctly and walks start->graduation through the PRODUCTION dispatcher,
the same hooks the live parser calls. Like the first eight slices (The
Ghost Shipment, The Crooked Wheel, The Lost Courier, The Skimmed Line,
The Dust-Sick, The False Provenance, The Forged Notice, The Warrens Toll)
it reuses the live questline engine (active_questline slot, the existing
event types, the four reward funnels) with NO new engine code, per
quest_expansion_postlaunch_path_v1.md.

Distinct from the prior eight — TWO firsts:
  * a NINTH distinct skill spread — PICK POCKET + HIDE + COMPUTER
    PROGRAMMING (slicing) — none of which any prior accessible questline
    uses (vs search+streetwise / investigation+gambling / persuasion+
    sneak / security+bargain / first_aid+survival / value+con / forgery+
    bureaucracy / command+demolitions);
  * a NEW STRUCTURE — the FIRST accessible questline that resolves on
    FINESSE, not force: THREE skill-check steps and NO combat step,
    climaxing on the master slice rather than a blaster fight. It is the
    first side-arc a pure slicer / scoundrel / face build can finish
    entirely on its own terms (every other accessible questline forces a
    combat climax). Because there is no combat step there is no antagonist
    NPC and no chain_enemy_template; the only placed NPC is the giver.

It also runs a FRESH district of Coruscant — the mid-city commercial
district + the Coruscant Works sublevels (dexters_diner /
mid_transit_hub / commercial_district_main /
commercial_district_atmospheric), reusing NONE of the prior two
Coruscant arcs' rooms (the Lost Courier's crystal_jewel_cantina /
lower_refugee_warren / petrax_sublevels / factory_district, or the False
Provenance's petrax_quarter / galactic_museum / calocour_heights /
coruscant_westport_landing).

The test pins the accessibility (chargen_complete, no rep gate), the
modest reward band (below the tuned rep ceiling), the registered+linked
achievement, real room slugs, the giver NPC presence, the no-combat
structure, and — crucially — that the one aliased/multi-word climax
skill ("computer programming") canonicalizes to the registry skill so a
trained character actually rolls their pool at `chain attempt` instead
of raw Perception.

Complements (does not replace) the generic data-driven walkability test
(test_t5_questline_content.TestAllQuestlinesWalkable, which auto-covers
THIS questline too) and the static reachability invariant.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

QUESTLINE_ID = "coruscant_works_sealed_ledger"
ACHIEVEMENT_KEY = "sealed_ledger_recovered"
GIVER_NPC = "Terva Dohl"
START_ROOM = "dexters_diner"
GIVER_ROOM_NAME = "Coruscant - Dexter's Diner"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_sealed_ledger.yaml")

# The ninth skill spread, in step order (steps 2/3/4 are skill_check_passed).
EXPECTED_SKILLS = ["pick pocket", "hide", "computer programming"]

# Reward band guards mirror test_t5_questline_content (the same all-chains
# tests already enforce these; pinned here too so a drift in THIS drop is
# caught by THIS drop's test).
HONORED = 50
CEILING = 22


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _make_fake_db():
    db = MagicMock()
    db.save_character = AsyncMock()
    db.get_npc = AsyncMock(return_value=None)
    db.get_character = AsyncMock(return_value=None)
    db.get_room = AsyncMock(return_value=None)
    # Real planet-room slugs; the teleport resolves them via get_room_by_slug.
    db.get_room_by_slug = AsyncMock(return_value={"id": 999})
    return db


def _char(attrs: dict = None) -> dict:
    base = {"chargen_complete": True}
    base.update(attrs or {})
    return {
        "id": 47, "name": "Freelancer PC", "room_id": 100,
        "attributes": json.dumps(base),
    }


def _attrs(char: dict) -> dict:
    return json.loads(char["attributes"])


def _qstate(char: dict) -> dict:
    from engine.tutorial_chains import _QUESTLINE_KEY
    return _attrs(char).get(_QUESTLINE_KEY) or {}


class _RealCorpusBase(unittest.TestCase):
    def setUp(self):
        from engine.era_state import set_active_config
        import engine.chain_events as ce
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        ce._reset_corpus_cache()

    def tearDown(self):
        from engine.era_state import clear_active_config
        import engine.chain_events as ce
        clear_active_config()
        ce._reset_corpus_cache()

    def _questline(self):
        from engine.chain_events import list_questlines
        qls = {q.chain_id: q for q in list_questlines()}
        self.assertIn(QUESTLINE_ID, qls,
                      "the generalized questline is not in the corpus")
        return qls[QUESTLINE_ID]


class TestQuestlineShape(_RealCorpusBase):

    def test_in_corpus_and_is_questline_kind(self):
        ql = self._questline()
        self.assertEqual(ql.kind, "questline")
        self.assertEqual(len(ql.steps), 5)
        # The step-1 NPC is the offer/start NPC (get_questline_offer).
        self.assertEqual(ql.steps[0].npc, GIVER_NPC)
        self.assertEqual(ql.starting_room, START_ROOM)

    def test_excluded_from_chargen_picker(self):
        # kind: questline keeps it out of the chargen chain selection.
        from engine.tutorial_chains import load_tutorial_chains
        corpus = load_tutorial_chains("clone_wars")
        match = [c for c in corpus.chains if c.chain_id == QUESTLINE_ID]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].kind, "questline")

    def test_accessible_no_rep_gate(self):
        # The defining difference from the t5 questlines: a fresh
        # chargen-complete character (no faction rep) is NOT locked out.
        from engine.tutorial_chains import is_chain_locked_for_character
        ql = self._questline()
        char = _char()
        locked, reason = is_chain_locked_for_character(ql, _attrs(char))
        self.assertFalse(locked,
                         f"accessible questline should not be locked: {reason}")


class TestWalkthrough(_RealCorpusBase):

    def test_full_walkthrough_to_graduation(self):
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        from engine.tutorial_chains import is_chain_complete, _QUESTLINE_KEY

        char = _char()
        db = _make_fake_db()

        ok, msg = _run(start_questline(db, char, QUESTLINE_ID))
        self.assertTrue(ok, msg)
        self.assertEqual(_qstate(char).get("step"), 1)

        # Step 1: talk to Terva Dohl (the records-advocate)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: lift the vault fob (pick pocket)
        _run(on_skill_check_passed(db, char, "pick pocket", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: slip past the watchers + sensor sweep (hide)
        _run(on_skill_check_passed(db, char, "hide", True, difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: crack the slicer-gauntlet (computer programming) — the
        # CLIMAX is a skill check, not a fight.
        _run(on_skill_check_passed(db, char, "computer programming", True,
                                   difficulty=14))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Terva -> graduate
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertTrue(is_chain_complete(_attrs(char), _QUESTLINE_KEY))

    def test_skill_failure_does_not_advance(self):
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "pick pocket", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on pick pocket; a passing hide check (this
        # questline's OWN step-3 skill) must NOT advance step 2 — the gate
        # is per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "hide", True, difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_offer_surfaces_for_giver_when_eligible(self):
        from engine.chain_events import get_questline_offer
        char = _char()
        offer = get_questline_offer(char, GIVER_NPC)
        self.assertIsNotNone(offer)
        self.assertEqual(offer["chain_id"], QUESTLINE_ID)
        self.assertFalse(offer["locked"])


class TestAchievement(_RealCorpusBase):

    def test_registered_and_linked(self):
        import engine.achievements as A
        A.load_achievements()
        ach = A.get_achievement(ACHIEVEMENT_KEY)
        self.assertIsNotNone(ach, "achievement not registered in catalog")
        trig = ach.get("trigger") or {}
        self.assertEqual(trig.get("event"), "chain_graduation")
        self.assertEqual(trig.get("chain_id"), QUESTLINE_ID)
        # Accessible questline pays LESS CP than the t5 trainer chains (5).
        self.assertEqual(ach.get("cp_reward"), 3)

    def test_graduation_lists_the_achievement(self):
        ql = self._questline()
        grad = ql.graduation
        ach_list = list(getattr(grad, "achievements", None) or [])
        self.assertIn(ACHIEVEMENT_KEY, ach_list)


class TestRewardBand(_RealCorpusBase):

    def _rep_totals(self):
        from collections import defaultdict
        path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "tutorials" / "chains.yaml")
        data = yaml.safe_load(open(path, encoding="utf-8"))
        chain = next(c for c in data["chains"]
                     if c["chain_id"] == QUESTLINE_ID)
        per = defaultdict(int)
        for s in chain.get("steps") or []:
            for f, v in ((s.get("reward") or {}).get("faction_rep")
                         or {}).items():
                per[f] += int(v)
        for f, v in ((chain.get("graduation") or {}).get("faction_rep")
                     or {}).items():
            per[f] += int(v)
        return dict(per)

    def test_rep_below_honored_and_under_ceiling(self):
        totals = self._rep_totals()
        self.assertTrue(totals, "questline grants no faction rep at all")
        for fac, total in totals.items():
            self.assertLess(total, HONORED,
                            f"{fac} rep {total} >= honored (50)")
            self.assertLessEqual(total, CEILING,
                                 f"{fac} rep {total} > tuned ceiling ({CEILING})")

    def test_credits_modest_and_graduation_is_300(self):
        ql = self._questline()
        grad_credits = int(getattr(ql.graduation, "credits", 0) or 0)
        step_credits = sum(int((getattr(s, "reward", {}) or {}).get(
            "credits", 0) or 0) for s in ql.steps)
        # Guide_16 §15 pins the freelance graduation payout at 300.
        self.assertEqual(grad_credits, 300)
        # Accessible side-content: a modest faucet, not a windfall.
        self.assertLessEqual(grad_credits + step_credits, 1000)


class TestReachabilityBits(_RealCorpusBase):

    def test_all_step_rooms_are_real_slugs(self):
        from tests.test_chain_corpus_reachability_invariant import (
            _all_room_slugs,
        )
        slugs = _all_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, slugs,
                          f"step {step.step} location {step.location!r} "
                          f"is not a real loaded room")
        self.assertIn(ql.graduation.drop_room, slugs)

    def test_only_walker_supported_completion_types(self):
        # Avoid item_used / room_entered / prerequisite (the data-driven
        # walker can't drive them; reachability also bans the latter two).
        allowed = {"talk_to_npc", "command_executed", "skill_check_passed",
                   "combat_won", "mission_accepted", "mission_completed",
                   "bounty_accepted"}
        ql = self._questline()
        for step in ql.steps:
            ctype = (step.completion or {}).get("type")
            self.assertIn(ctype, allowed,
                          f"step {step.step} uses unsupported completion "
                          f"type {ctype!r}")

    def test_skill_spread_is_pickpocket_hide_computerprogramming(self):
        # The ninth distinct spread: the three skill_check_passed steps gate
        # on pick pocket -> hide -> computer programming (no prior accessible
        # questline uses any of the three).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_no_combat_step_finesse_climax(self):
        # The defining structural first: this questline resolves on finesse,
        # with NO combat_won step anywhere — the climax (step 4) is a skill
        # check, not a fight.
        ql = self._questline()
        ctypes = [(s.completion or {}).get("type") for s in ql.steps]
        self.assertNotIn("combat_won", ctypes,
                         "The Sealed Ledger is the no-combat questline — it "
                         "must contain no combat_won step")
        self.assertEqual((ql.steps[3].completion or {}).get("type"),
                         "skill_check_passed",
                         "the climax (step 4) must be a skill-check, not a "
                         "fight")

    def test_climax_skill_aliases_to_a_real_trained_pool(self):
        # 'computer programming' is the one aliased/multi-word skill in the
        # spread (pick pocket + hide are direct registry names). It must
        # canonicalize to the registry skill so a char who trained Computer
        # Programming/Repair rolls their TRAINED pool at `chain attempt`,
        # not raw Perception (the drop-24 phantom-skill class).
        from engine.character import canonical_skill_key
        from engine.skill_checks import _get_skill_pool, _get_default_registry
        self.assertEqual(canonical_skill_key("computer programming"),
                         "computer programming/repair")
        reg = _get_default_registry()
        # All three spread skills resolve to a registered SkillDef.
        for sk in EXPECTED_SKILLS:
            self.assertIsNotNone(reg.get(sk),
                                 f"spread skill {sk!r} does not resolve to a "
                                 f"registered skill")
        trained = {
            "attributes": json.dumps({"technical": "3D"}),
            "skills": json.dumps({"computer programming/repair": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"technical": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "computer programming", reg)
        raw_pool = _get_skill_pool(untrained, "computer programming", reg)
        # A char who trained Computer Programming/Repair must roll a STRICTLY
        # larger pool than a char rolling raw Technical — proving the aliased
        # 'computer programming' authored skill resolves to the trained skill
        # rather than silently falling back to the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored climax skill 'computer programming' must roll the "
            "trained Computer Programming/Repair pool, not raw Technical")

    def test_reuses_no_prior_coruscant_arc_rooms(self):
        # Three questlines are now on Coruscant; this one runs a fresh
        # mid-city district, so it must share no step rooms with the Lost
        # Courier OR the False Provenance (else the "fresh district" claim
        # is false).
        prior_coruscant_rooms = {
            # The Lost Courier (lower city)
            "crystal_jewel_cantina", "lower_refugee_warren",
            "petrax_sublevels", "factory_district",
            # The False Provenance (monumental / cultural)
            "petrax_quarter", "galactic_museum", "calocour_heights",
            "coruscant_westport_landing",
        }
        ql = self._questline()
        mine = {step.location for step in ql.steps}
        self.assertFalse(mine & prior_coruscant_rooms,
                         f"overlaps prior Coruscant arc rooms: "
                         f"{mine & prior_coruscant_rooms}")


class TestNpcs(_RealCorpusBase):

    def setUp(self):
        super().setUp()
        self.npcs = (yaml.safe_load(open(NPC_FILE, encoding="utf-8"))
                     or {}).get("npcs") or []
        self.by_name = {n["name"]: n for n in self.npcs}

    def test_giver_present_in_start_room(self):
        self.assertIn(GIVER_NPC, self.by_name)
        giver = self.by_name[GIVER_NPC]
        # Display name of dexters_diner.
        self.assertEqual(giver["room"], GIVER_ROOM_NAME)
        self.assertFalse(giver["ai_config"].get("hostile"),
                         "the questline giver must not be hostile")

    def test_no_antagonist_and_no_chain_enemy_template(self):
        # The no-combat questline ships ONLY the giver — no antagonist NPC
        # and no chain_enemy_template anywhere in the file.
        self.assertEqual(len(self.npcs), 1,
                         "The Sealed Ledger has no combat step, so its NPC "
                         "file should contain exactly one NPC (the giver)")
        for n in self.npcs:
            self.assertNotIn("chain_enemy_template", n.get("ai_config") or {},
                             "no combat step -> no chain_enemy_template")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_sealed_ledger.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
