# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_sabotaged_run.py — T3.24 generalized
quest expansion, tenth slice.

Proves the TENTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Sabotaged Run" (tatooine_speeder_sabotaged_run) — is shipped
correctly and walks start->graduation through the PRODUCTION dispatcher,
the same hooks the live parser calls. Like the first nine slices (The
Ghost Shipment, The Crooked Wheel, The Lost Courier, The Skimmed Line,
The Dust-Sick, The False Provenance, The Forged Notice, The Warrens Toll,
The Sealed Ledger) it reuses the live questline engine (active_questline
slot, the existing event types, the four reward funnels) with NO new
engine code, per quest_expansion_postlaunch_path_v1.md.

Two firsts for the accessible-questline arc:
  * a TENTH distinct skill spread — SENSORS + REPULSORLIFT OPERATION —
    none of which any prior accessible questline uses (vs search+
    streetwise / investigation+gambling / persuasion+sneak / security+
    bargain / first_aid+survival / value+con / forgery+bureaucracy /
    command+demolitions / pick-pocket+hide+computer-programming);
  * the FIRST accessible questline to lead with a MECHANICAL build. Both
    spread skills (Sensors, Repulsorlift Operation) are Mechanical-
    attribute skills — every prior accessible arc leads with Perception,
    Knowledge, Technical, or combat skills, so none rewards the pilot /
    driver / scanner character at all. The Sabotaged Run is built around
    reading a sensor trace and out-driving a picket on open hardpan.

It also runs a THIRD, vehicle-country face of Tatooine — the Mos Eisley
outskirts speeder circuit (spaceport_speeders / transport_depot /
outskirts_speeder_track / outskirts_wrecked_sandcrawler), reusing NONE of
the prior two Tatooine arcs' rooms (the Crooked Wheel's
market_place_geps_grill / chalmuans_cantina_main_bar /
mos_eisley_market_district / outskirts_abandoned_farm, or the Dust-Sick's
Jundland outskirts_scavenger_market / jundland_hidden_cave /
jundland_dune_sea_edge / jundland_beggars_canyon).

The story shape is new too — breaking a fixed racing circuit: a swoop
gang the locals call the Dust Wheelers spikes honest riders' coils at the
start gates, so trace their rig off the depot scanners (sensors), run the
circuit to pull their outrider off the chop-shop (repulsorlift
operation), stop the enforcer who guards it (combat_won), and bring the
stolen rig and a stranded medical run back. It carries a real combat
climax (step 4), with a single placed antagonist NPC and a
chain_enemy_template — distinct from The Sealed Ledger's no-combat
finesse climax.

The test pins the accessibility (chargen_complete, no rep gate), the
modest reward band (below the tuned rep ceiling, 300-credit graduation),
the registered+linked achievement, real room slugs, the giver + foil NPCs,
the combat-climax structure, the no-prior-Tatooine-arc-rooms claim, the
Mechanical-build-first claim, and that the authored spread skills resolve
to a trained character's real pool at `chain attempt` (not raw Mechanical).

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

QUESTLINE_ID = "tatooine_speeder_sabotaged_run"
ACHIEVEMENT_KEY = "sabotaged_run_won"
GIVER_NPC = "Ria Tann"
ANTAGONIST_NPC = "Drevin Saar"
ENEMY_TEMPLATE = "sabotaged_run_enforcer"
START_ROOM = "spaceport_speeders"
GIVER_ROOM_NAME = "Spaceport Speeders"
ANTAGONIST_ROOM_NAME = "City Outskirts - Wrecked Sandcrawler"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_sabotaged_run.yaml")

# The tenth skill spread, in step order (steps 2/3 are skill_check_passed).
EXPECTED_SKILLS = ["sensors", "repulsorlift operation"]

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
            on_combat_won,
        )
        from engine.tutorial_chains import is_chain_complete, _QUESTLINE_KEY

        char = _char()
        db = _make_fake_db()

        ok, msg = _run(start_questline(db, char, QUESTLINE_ID))
        self.assertTrue(ok, msg)
        self.assertEqual(_qstate(char).get("step"), 1)

        # Step 1: talk to Ria Tann (the speeder-shop mechanic)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: trace the gang's rig off the gate scanners (sensors)
        _run(on_skill_check_passed(db, char, "sensors", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: run the circuit to pull the picket (repulsorlift operation)
        _run(on_skill_check_passed(db, char, "repulsorlift operation", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: stop Drevin Saar at the chop-shop (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Ria -> graduate
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
        _run(on_skill_check_passed(db, char, "sensors", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on sensors; a passing repulsorlift operation check
        # (this questline's OWN step-3 skill) must NOT advance step 2 — the
        # gate is per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "repulsorlift operation", True,
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
        _run(on_skill_check_passed(db, char, "sensors", True, difficulty=11))
        _run(on_skill_check_passed(db, char, "repulsorlift operation", True,
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

    def test_skill_spread_is_sensors_and_repulsorlift_operation(self):
        # The tenth distinct spread: the two skill_check_passed steps gate on
        # sensors then repulsorlift operation (no prior accessible questline
        # uses either).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

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

    def test_first_mechanical_build_spread(self):
        # The defining first: both spread skills are MECHANICAL-attribute
        # skills, so this is the first accessible questline to reward a pilot/
        # driver/scanner build (every prior arc leads with Perception/
        # Knowledge/Technical/combat). Grounded against the live skills.yaml.
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))
        mech = {s["name"].lower() for s in (skills.get("mechanical") or [])}
        for sk in EXPECTED_SKILLS:
            self.assertIn(sk, mech,
                          f"spread skill {sk!r} is not a Mechanical-attribute "
                          f"skill — the 'first Mechanical build' claim is false")

    def test_spread_skills_resolve_to_trained_pools(self):
        # Both spread skills must canonicalize to a registered SkillDef so a
        # character who TRAINED them rolls their real pool at `chain attempt`,
        # not the raw Mechanical attribute (the drop-24 phantom-skill class).
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
            "attributes": json.dumps({"mechanical": "3D"}),
            "skills": json.dumps({"repulsorlift operation": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"mechanical": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "repulsorlift operation", reg)
        raw_pool = _get_skill_pool(untrained, "repulsorlift operation", reg)
        # A char who trained Repulsorlift Operation must roll a STRICTLY larger
        # pool than a char rolling raw Mechanical — proving the authored skill
        # resolves to the trained skill rather than the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored spread skill 'repulsorlift operation' must roll the "
            "trained pool, not raw Mechanical")

    def test_reuses_no_prior_tatooine_arc_rooms(self):
        # Three questlines are now on Tatooine; this one runs a fresh
        # vehicle-country district, so it must share no step rooms with the
        # Crooked Wheel OR the Dust-Sick (else the "fresh face" claim is false).
        prior_tatooine_rooms = {
            # The Crooked Wheel (Mos Eisley market)
            "market_place_geps_grill", "chalmuans_cantina_main_bar",
            "mos_eisley_market_district", "outskirts_abandoned_farm",
            # The Dust-Sick (Jundland wilderness)
            "outskirts_scavenger_market", "jundland_hidden_cave",
            "jundland_dune_sea_edge", "jundland_beggars_canyon",
        }
        ql = self._questline()
        mine = {step.location for step in ql.steps}
        self.assertFalse(mine & prior_tatooine_rooms,
                         f"overlaps prior Tatooine arc rooms: "
                         f"{mine & prior_tatooine_rooms}")


class TestNpcs(_RealCorpusBase):

    def setUp(self):
        super().setUp()
        self.npcs = (yaml.safe_load(open(NPC_FILE, encoding="utf-8"))
                     or {}).get("npcs") or []
        self.by_name = {n["name"]: n for n in self.npcs}

    def test_giver_present_in_start_room(self):
        self.assertIn(GIVER_NPC, self.by_name)
        giver = self.by_name[GIVER_NPC]
        # Display name of spaceport_speeders.
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
        # The combat questline ships exactly the giver + the single foil;
        # the gang boss, outrider, crew, runner, and rigs are narrated-only.
        self.assertEqual(len(self.npcs), 2,
                         "The Sabotaged Run should place exactly two NPCs "
                         "(the giver + the combat foil)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_sabotaged_run.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
