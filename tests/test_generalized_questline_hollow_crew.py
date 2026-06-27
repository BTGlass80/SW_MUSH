# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_hollow_crew.py — T3.24 generalized
quest expansion, eleventh slice.

Proves the ELEVENTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Hollow Crew" (geonosis_offworld_hollow_crew) — is shipped
correctly and walks start->graduation through the PRODUCTION dispatcher,
the same hooks the live parser calls. Like the first ten slices (The
Ghost Shipment, The Crooked Wheel, The Lost Courier, The Skimmed Line,
The Dust-Sick, The False Provenance, The Forged Notice, The Warrens Toll,
The Sealed Ledger, The Sabotaged Run) it reuses the live questline engine
(active_questline slot, the existing event types, the four reward funnels)
with NO new engine code, per quest_expansion_postlaunch_path_v1.md.

Two firsts for the accessible-questline arc:
  * an ELEVENTH distinct skill spread — ALIEN SPECIES + DROID PROGRAMMING
    — none of which any prior accessible questline uses (vs search+
    streetwise / investigation+gambling / persuasion+sneak / security+
    bargain / first_aid+survival / value+con / forgery+bureaucracy /
    command+demolitions / pick-pocket+hide+computer-programming / sensors+
    repulsorlift-operation). `alien species` is a Knowledge skill and
    `droid programming` a Technical skill — this is the FIRST accessible
    questline to reward the xeno-knowledge / droid-tech build: reading a
    Geonosian hive caste in its own terms and slicing a stolen droid core;
  * the FIRST questline set on GEONOSIS — the Stalgasin offworlder surface
    (stalgasin_offworld_quarter / smugglers_roost_flophouse /
    stalgasin_outsider_compound) plus the deep-hive geonosis_hive_market.
    The CIS droid foundry is kept entirely OFF-STAGE (the trader buys
    decommissioned foundry-OVERRUN labor droids), so the war stays offstage
    the way every prior accessible arc keeps the Republic/CIS conflict
    offstage.

The story shape is new too — breaking a droid-reflash recall racket: a
scrap-gang (the Reclaimers) buries a hidden recall-string in a trader's
rebuilt labor-droid cores so the sold crews walk back stolen, so read the
Geonosian drone-caste broker right and re-open the overrun channel (alien
species), crack a walked droid to pull the gang's string and trace it home
(droid programming), stop the enforcer who comes when his crew goes quiet
(combat_won), and give the offworld quarter back an honest bench. It
carries a real combat climax (step 4), with a single placed antagonist NPC
and a chain_enemy_template — distinct from The Sealed Ledger's no-combat
finesse climax.

The test pins the accessibility (chargen_complete, no rep gate), the
modest reward band (below the tuned rep ceiling, 300-credit graduation),
the registered+linked achievement, real Geonosis room slugs, the giver +
foil NPCs, the combat-climax structure, the all-Geonosis-rooms (first arc
on the planet) claim, the eleventh-distinct-spread + Knowledge/Technical
claim, and that the authored spread skills resolve to a trained character's
real pool at `chain attempt` (not the raw attribute).

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

QUESTLINE_ID = "geonosis_offworld_hollow_crew"
ACHIEVEMENT_KEY = "hollow_crew_freed"
GIVER_NPC = "Nuva Sehl"
ANTAGONIST_NPC = "Vossk Rhal"
ENEMY_TEMPLATE = "hollow_crew_enforcer"
START_ROOM = "stalgasin_offworld_quarter"
GIVER_ROOM_NAME = "Geonosis - Stalgasin Surface - Offworld Quarter"
ANTAGONIST_ROOM_NAME = "Geonosis - Stalgasin Surface - Outsider Compound"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_hollow_crew.yaml")

# The eleventh skill spread, in step order (steps 2/3 are skill_check_passed).
EXPECTED_SKILLS = ["alien species", "droid programming"]

# The skill spreads of the prior ten accessible questlines (each non-combat
# skill that gates a skill_check_passed step). The eleventh spread must share
# NO skill with any of them — the "eleventh DISTINCT spread" claim.
PRIOR_SPREAD_SKILLS = {
    "search", "streetwise", "investigation", "gambling", "persuasion",
    "sneak", "security", "bargain", "first aid", "survival", "value", "con",
    "forgery", "bureaucracy", "command", "demolitions", "pick pocket", "hide",
    "computer programming", "sensors", "repulsorlift operation",
}

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


def _geonosis_room_slugs() -> set:
    data = yaml.safe_load(open(
        PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "planets"
        / "geonosis.yaml", encoding="utf-8"))
    rooms = data["rooms"]
    if isinstance(rooms, dict):
        return set(rooms.keys())
    return {r.get("slug") or r.get("id") for r in rooms}


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
            on_combat_won,
        )
        from engine.tutorial_chains import is_chain_complete, _QUESTLINE_KEY

        char = _char()
        db = _make_fake_db()

        ok, msg = _run(start_questline(db, char, QUESTLINE_ID))
        self.assertTrue(ok, msg)
        self.assertEqual(_qstate(char).get("step"), 1)

        # Step 1: talk to Nuva Sehl (the salvage-droid trader)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: read the hive broker (alien species)
        _run(on_skill_check_passed(db, char, "alien species", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: crack a walked droid (droid programming)
        _run(on_skill_check_passed(db, char, "droid programming", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: stop Vossk Rhal at the compound (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Nuva Sehl -> graduate
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
        _run(on_skill_check_passed(db, char, "alien species", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on alien species; a passing droid programming check
        # (this questline's OWN step-3 skill) must NOT advance step 2 — the
        # gate is per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "droid programming", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_enemy_template_does_not_advance(self):
        # Step 4 gates on the foil's chain_enemy_template; defeating an
        # unrelated template must NOT advance the combat step.
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
            on_combat_won,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "alien species", True,
                                   difficulty=11))
        _run(on_skill_check_passed(db, char, "droid programming", True,
                                   difficulty=13))  # ->4
        _run(on_combat_won(db, char, "some_other_template", 1))
        self.assertEqual(_qstate(char).get("step"), 4)  # no advance

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

    def test_skill_spread_is_alien_species_and_droid_programming(self):
        # The eleventh distinct spread: the two skill_check_passed steps gate
        # on alien species then droid programming (no prior accessible
        # questline uses either).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_spread_is_distinct_from_all_prior_arcs(self):
        # The "eleventh DISTINCT spread" claim: neither spread skill is used
        # by any of the prior ten accessible questlines.
        self.assertFalse(
            set(EXPECTED_SKILLS) & PRIOR_SPREAD_SKILLS,
            f"spread shares a skill with a prior arc: "
            f"{set(EXPECTED_SKILLS) & PRIOR_SPREAD_SKILLS}")

    def test_combat_climax_with_single_foil(self):
        # Distinct from The Sealed Ledger's no-combat finesse climax: this
        # questline carries a combat_won step (step 4) gated on a single
        # foil's chain_enemy_template.
        ql = self._questline()
        combat_steps = [s for s in ql.steps
                        if (s.completion or {}).get("type") == "combat_won"]
        self.assertEqual(len(combat_steps), 1)
        comp = combat_steps[0].completion
        self.assertEqual(comp.get("enemy_template"), ENEMY_TEMPLATE)
        self.assertEqual(int(comp.get("enemy_count", 0) or 0), 1)

    def test_xeno_knowledge_and_droid_tech_build(self):
        # The defining first: the spread is a Knowledge skill (alien species)
        # + a Technical skill (droid programming), so this is the first
        # accessible questline to reward the xeno-knowledge / droid-tech
        # build. Grounded against the live skills.yaml.
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))
        knowledge = {s["name"].lower() for s in (skills.get("knowledge") or [])}
        technical = {s["name"].lower() for s in (skills.get("technical") or [])}
        self.assertIn("alien species", knowledge,
                      "'alien species' is not a Knowledge skill — the "
                      "xeno-knowledge claim is false")
        self.assertIn("droid programming", technical,
                      "'droid programming' is not a Technical skill — the "
                      "droid-tech claim is false")

    def test_spread_skills_resolve_to_trained_pools(self):
        # Both spread skills must canonicalize to a registered SkillDef so a
        # character who TRAINED them rolls their real pool at `chain attempt`,
        # not the raw attribute (the drop-24 phantom-skill class).
        from engine.character import canonical_skill_key
        from engine.skill_checks import _get_skill_pool, _get_default_registry
        reg = _get_default_registry()
        for sk in EXPECTED_SKILLS:
            # Neither spread skill is aliased — each canonicalizes to itself.
            self.assertEqual(canonical_skill_key(sk), sk)
            self.assertIsNotNone(reg.get(sk),
                                 f"spread skill {sk!r} does not resolve to a "
                                 f"registered skill")
        trained = {
            "attributes": json.dumps({"technical": "3D"}),
            "skills": json.dumps({"droid programming": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"technical": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "droid programming", reg)
        raw_pool = _get_skill_pool(untrained, "droid programming", reg)
        # A char who trained Droid Programming must roll a STRICTLY larger
        # pool than a char rolling raw Technical — proving the authored skill
        # resolves to the trained skill rather than the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored spread skill 'droid programming' must roll the "
            "trained pool, not raw Technical")

    def test_all_step_rooms_are_geonosis_rooms(self):
        # The "first questline set on Geonosis" claim: every step room (and the
        # drop room) is a real loaded Geonosis room — which also guarantees no
        # overlap with the prior ten arcs (all on other planets).
        geo = _geonosis_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, geo,
                          f"step {step.step} location {step.location!r} is not "
                          f"a Geonosis room — the 'first Geonosis arc' claim "
                          f"is false")
        self.assertIn(ql.graduation.drop_room, geo)


class TestNpcs(_RealCorpusBase):

    def setUp(self):
        super().setUp()
        self.npcs = (yaml.safe_load(open(NPC_FILE, encoding="utf-8"))
                     or {}).get("npcs") or []
        self.by_name = {n["name"]: n for n in self.npcs}

    def test_giver_present_in_start_room(self):
        self.assertIn(GIVER_NPC, self.by_name)
        giver = self.by_name[GIVER_NPC]
        # Display name of stalgasin_offworld_quarter.
        self.assertEqual(giver["room"], GIVER_ROOM_NAME)
        self.assertFalse(giver["ai_config"].get("hostile"),
                         "the questline giver must not be hostile")

    def test_antagonist_carries_chain_enemy_template(self):
        self.assertIn(ANTAGONIST_NPC, self.by_name)
        ant = self.by_name[ANTAGONIST_NPC]
        self.assertEqual(ant["room"], ANTAGONIST_ROOM_NAME)
        self.assertEqual(
            ant["ai_config"].get("chain_enemy_template"), ENEMY_TEMPLATE)
        self.assertTrue(ant["ai_config"].get("hostile"))

    def test_exactly_two_placed_npcs(self):
        # The combat questline ships exactly the giver + the single foil; the
        # gang boss, the hive broker, Vez Garra (existing ambient), the crew,
        # the walked droids, and the robbed offworlders are narrated-only.
        self.assertEqual(len(self.npcs), 2,
                         "The Hollow Crew should place exactly two NPCs "
                         "(the giver + the combat foil)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_hollow_crew.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
