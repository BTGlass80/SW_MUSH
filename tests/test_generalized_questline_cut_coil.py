# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_cut_coil.py — T3.24 generalized
quest expansion, twenty-fourth slice.

Proves the TWENTY-FOURTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Cut Coil" (mos_eisley_cut_coil) — is shipped correctly and walks
start->graduation through the PRODUCTION dispatcher, the same hooks the live
parser calls. Like the first twenty-three slices (The Ghost Shipment, The Crooked
Wheel, The Lost Courier, The Skimmed Line, The Dust-Sick, The False Provenance, The
Forged Notice, The Warrens Toll, The Sealed Ledger, The Sabotaged Run, The Hollow
Crew, The Driven Herd, The Condemned Hull, The Long Haul, The Twisted Word, The
Wasting Ward, The Rigged Issue, The Salted Lane, The Short Weight, The Wreckers'
Light, The Bonded Crew, The Kept Watch, The Buried Block) it reuses the live
questline engine (active_questline slot, the existing event types, the four reward
funnels) with NO new engine code, per quest_expansion_postlaunch_path_v1.md.

Firsts for the accessible-questline arc:
  * a TWENTY-FOURTH distinct skill spread — REPULSORLIFT REPAIR (Technical) + DROID
    REPAIR (Technical) — neither of which any prior accessible questline uses (vs
    search+streetwise / investigation+gambling / persuasion+sneak / security+bargain /
    first_aid+survival / value+con / forgery+bureaucracy / command+demolitions /
    pick-pocket+hide+computer-programming / sensors+repulsorlift-operation /
    alien-species+droid-programming / beast-riding+swimming /
    space-transport-repair+astrogation / ground-vehicle-repair+ground-vehicle-operation /
    languages+cultures / medicine+scholar / blaster-repair+armor-repair /
    space-transports+starship-gunnery / powersuit-operation+lifting /
    communications+planetary-systems / business+intimidation / law-enforcement+tactics /
    climbing-jumping+stamina). It is the FIRST accessible questline to reward the
    GARAGE-MECHANIC / vehicle-and-droid REPAIR build — the speeder-and-droid bench. It
    is the SECOND both-Technical spread (after The Rigged Issue's blaster + armor repair,
    the armorer's bench), but a wholly distinct pair and work, mechanically distinct from
    every prior repair/operation arc: The Rigged Issue (personal arms), The Condemned Hull
    (a starship engineer-navigator), The Long Haul (a wheelman who drives what he fixes),
    The Sabotaged Run (a racer in the cockpit reading telemetry); and where the only prior
    droid work re-flashes a droid's behavior (droid programming, software), this REPAIRS a
    droid the racket physically gutted (hardware) to restore a wiped witness;
  * the SEVENTH questline set on TATOOINE, on the Mos Eisley STREET face
    (mos_eisley_south_end / dowager_queen_corner / mos_eisley_north_end /
    mos_eisley_spaceport_row), every room of which is FRESH to the entire chain corpus —
    reusing NONE of the prior Tatooine arcs' rooms. At 24 arcs and a finite set of
    combat-capable (non-SECURED) rooms no untouched zone with four contested rooms
    remains, so the discipline kept this slice is the honest one still available: a fresh
    ROOM CLUSTER, not a fresh face. Tatooine is Hutt-fringe with no Republic presence to
    keep offstage, and the garage is run afoul of in the end by the town's own Mos Eisley
    vehicle-licensing prefect, so the larger powers stay offstage the way every prior
    accessible arc keeps them offstage;
  * a foil who carries the proven blaster_pistol of the ranged foils, squarely in the
    proven beatable band (the same in-band guarded stat line as The Salted Lane's, The
    Short Weight's, The Wreckers' Light's, The Bonded Crew's, The Kept Watch's, and The
    Buried Block's foils), pointedly NOT the melee line of The Condemned Hull's out-of-band
    Houk foil.

The story shape is new too — breaking a SABOTAGE-FOR-IMPOUND / PRODUCT-TAMPERING
consumer-fraud racket, the FIRST accessible arc in which the racket DAMAGES the very
thing it is paid to fix. A Mos Eisley repulsorlift repair garage nicks a repulsor coil
on the bench so the speeder it tuned fails a week on, tows it in with its own recovery
droid, books a ruinous repair, and strips the speeders the owners must sign over, gutting
the recovery droid's tow log after every rigged job. So get into the garage's scrap corner
and read a towed-in speeder's lift drive for the deliberate cut (repulsorlift repair),
rebuild the gutted recovery droid in its North End yard until it gives up the tow log
(droid repair), stand off the garage's enforcer on Spaceport Row (combat_won), and get the
cut coil and the droid's log to the Mos Eisley vehicle-licensing prefect. It carries a real
combat climax (step 4), with a single placed antagonist NPC and a chain_enemy_template.

The test pins the accessibility (chargen_complete, no rep gate), the modest reward
band (below the tuned rep ceiling, 300-credit graduation), the registered+linked
achievement, real Tatooine room slugs, the giver + foil NPCs, the combat-climax
structure, the all-Mos-Eisley-street-rooms + every-room-fresh-to-corpus claim, the
twenty-fourth-distinct-spread + repulsorlift-repair(Technical)/droid-repair(Technical)
claim + distinctness from the prior both-Technical (armorer) arc, and that the authored
spread skills resolve to a trained character's real pool at `chain attempt` (not the raw
attribute).

Complements (does not replace) the generic data-driven walkability test
(test_t5_questline_content.TestAllQuestlinesWalkable, which auto-covers THIS
questline too) and the static reachability invariant.
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

QUESTLINE_ID = "mos_eisley_cut_coil"
ACHIEVEMENT_KEY = "cut_coil_cleared"
GIVER_NPC = "Nilo Sabb"
ANTAGONIST_NPC = "Vagh Sarko"
ENEMY_TEMPLATE = "cut_coil_enforcer"
START_ROOM = "mos_eisley_south_end"
GIVER_ROOM_NAME = "Mos Eisley Street - South End"
ANTAGONIST_ROOM_NAME = "Mos Eisley Street - Spaceport Row"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_cut_coil.yaml")

# The twenty-fourth skill spread, in step order (steps 2/3 are skill_check_passed).
EXPECTED_SKILLS = ["repulsorlift repair", "droid repair"]

# The skill spreads of the prior TWENTY-THREE accessible questlines (each non-combat
# skill that gates a skill_check_passed step). The twenty-fourth spread must share
# NO skill with any of them — the "twenty-fourth DISTINCT spread" claim.
PRIOR_SPREAD_SKILLS = {
    "search", "streetwise", "investigation", "gambling", "persuasion",
    "sneak", "security", "bargain", "first aid", "survival", "value", "con",
    "forgery", "bureaucracy", "command", "demolitions", "pick pocket", "hide",
    "computer programming", "sensors", "repulsorlift operation",
    "alien species", "droid programming", "beast riding", "swimming",
    "space transport repair", "astrogation",
    "ground vehicle repair", "ground vehicle operation",
    "languages", "cultures", "medicine", "scholar",
    "blaster repair", "armor repair",
    "space transports", "starship gunnery",
    "powersuit operation", "lifting",
    "communications", "planetary systems",
    "business", "intimidation",
    "law enforcement", "tactics",
    "climbing/jumping", "stamina",
}

# The only prior arc that is a both-TECHNICAL spread — The Rigged Issue (blaster repair +
# armor repair, the armorer's bench, PERSONAL ARMS). The twenty-fourth is the second
# both-Technical spread but works MACHINES (a lift drive and a droid), sharing no skill.
RIGGED_ISSUE_SPREAD = {"blaster repair", "armor repair"}

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
        "id": 54, "name": "Freelancer PC", "room_id": 100,
        "attributes": json.dumps(base),
    }


def _attrs(char: dict) -> dict:
    return json.loads(char["attributes"])


def _qstate(char: dict) -> dict:
    from engine.tutorial_chains import _QUESTLINE_KEY
    return _attrs(char).get(_QUESTLINE_KEY) or {}


def _tatooine_rooms() -> list:
    data = yaml.safe_load(open(
        PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "planets"
        / "tatooine.yaml", encoding="utf-8"))
    rooms = data["rooms"]
    if isinstance(rooms, dict):
        return [{"slug": k, **(v or {})} for k, v in rooms.items()]
    return rooms


def _tatooine_room_slugs() -> set:
    return {r.get("slug") or r.get("id") for r in _tatooine_rooms()}


def _mos_eisley_slugs() -> set:
    return {r.get("slug") or r.get("id") for r in _tatooine_rooms()
            if r.get("zone") == "tatooine_mos_eisley"}


def _other_chain_rooms() -> set:
    """Every room slug used by every chain EXCEPT this one."""
    data = yaml.safe_load(open(
        PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "tutorials"
        / "chains.yaml", encoding="utf-8"))
    used = set()
    for c in data.get("chains") or []:
        if c.get("chain_id") == QUESTLINE_ID:
            continue
        for s in c.get("steps") or []:
            if s.get("location"):
                used.add(s["location"])
        if c.get("starting_room"):
            used.add(c["starting_room"])
        grad = c.get("graduation") or {}
        if grad.get("drop_room"):
            used.add(grad["drop_room"])
    return used


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

        # Step 1: talk to Nilo Sabb (the old mechanic)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: read the towed-in speeder's lift drive (repulsorlift repair)
        _run(on_skill_check_passed(db, char, "repulsorlift repair", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: rebuild the gutted recovery droid (droid repair)
        _run(on_skill_check_passed(db, char, "droid repair", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: stop Vagh Sarko on Spaceport Row (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Nilo Sabb -> graduate
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
        _run(on_skill_check_passed(db, char, "repulsorlift repair", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on repulsorlift repair; a passing droid-repair check (this
        # questline's OWN step-3 skill) must NOT advance step 2 — the gate is
        # per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "droid repair", True,
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
        _run(on_skill_check_passed(db, char, "repulsorlift repair", True,
                                   difficulty=11))
        _run(on_skill_check_passed(db, char, "droid repair", True,
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

    def test_skill_spread_is_repulsorlift_then_droid(self):
        # The twenty-fourth distinct spread: the two skill_check_passed steps gate
        # on repulsorlift repair then droid repair (no prior accessible questline
        # uses either).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_spread_is_distinct_from_all_prior_arcs(self):
        # The "twenty-fourth DISTINCT spread" claim: neither spread skill is used
        # by any of the prior twenty-three accessible questlines.
        self.assertFalse(
            set(EXPECTED_SKILLS) & PRIOR_SPREAD_SKILLS,
            f"spread shares a skill with a prior arc: "
            f"{set(EXPECTED_SKILLS) & PRIOR_SPREAD_SKILLS}")

    def test_combat_climax_with_single_foil(self):
        # This questline carries a combat_won step (step 4) gated on a single
        # foil's chain_enemy_template.
        ql = self._questline()
        combat_steps = [s for s in ql.steps
                        if (s.completion or {}).get("type") == "combat_won"]
        self.assertEqual(len(combat_steps), 1)
        comp = combat_steps[0].completion
        self.assertEqual(comp.get("enemy_template"), ENEMY_TEMPLATE)
        self.assertEqual(int(comp.get("enemy_count", 0) or 0), 1)

    def test_spread_is_garage_mechanic_technical_build(self):
        # The defining first: the spread is the GARAGE-MECHANIC / vehicle-and-droid
        # REPAIR build — repulsorlift repair (Technical, the lift drive) + droid
        # repair (Technical, the gutted recovery droid). Grounded against the live
        # skills.yaml: both are Technical repair skills, the second both-Technical
        # spread of the corpus.
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))
        technical = {s["name"].lower()
                     for s in (skills.get("technical") or [])}
        self.assertIn("repulsorlift repair", technical,
                      "'repulsorlift repair' is not a Technical skill — the "
                      "garage-mechanic claim is false")
        self.assertIn("droid repair", technical,
                      "'droid repair' is not a Technical skill — the "
                      "garage-mechanic claim is false")
        # Both spread skills are Technical: the second both-Technical spread.
        self.assertTrue(set(EXPECTED_SKILLS) <= technical,
                        "the twenty-fourth spread is not wholly within Technical")

    def test_distinct_from_prior_both_technical_arc(self):
        # The differentiation from the only prior both-Technical arc: The Rigged
        # Issue (blaster repair + armor repair, the armorer's bench, PERSONAL ARMS).
        # This is the garage-mechanic bench (a lift drive + a droid) and shares NO
        # spread skill with it.
        self.assertFalse(
            set(EXPECTED_SKILLS) & RIGGED_ISSUE_SPREAD,
            "The Cut Coil shares a spread skill with The Rigged Issue — the "
            "'distinct both-Technical pair' claim is false")

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
            "skills": json.dumps({"repulsorlift repair": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"technical": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "repulsorlift repair", reg)
        raw_pool = _get_skill_pool(untrained, "repulsorlift repair", reg)
        # A char who trained Repulsorlift Repair must roll a STRICTLY larger pool
        # than a char rolling raw Technical — proving the authored skill resolves
        # to the trained skill rather than the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored spread skill 'repulsorlift repair' must roll the trained "
            "pool, not raw Technical")

    def test_all_step_rooms_are_real_tatooine_rooms(self):
        # The "seventh questline set on Tatooine / Mos Eisley street face" claim:
        # every step room (and the drop room) is a real loaded Tatooine room
        # (planets/tatooine.yaml).
        tat = _tatooine_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, tat,
                          f"step {step.step} location {step.location!r} is not "
                          f"a Tatooine room — the 'seventh Tatooine arc' claim "
                          f"is false")
        self.assertIn(ql.graduation.drop_room, tat)

    def test_all_step_rooms_are_mos_eisley_street_rooms(self):
        # The "on the Mos Eisley street face" claim: every step room (and the drop
        # room) is a real loaded tatooine_mos_eisley-zone room.
        street = _mos_eisley_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, street,
                          f"step {step.step} location {step.location!r} is not "
                          f"a tatooine_mos_eisley room — the 'Mos Eisley street "
                          f"face' claim is false")
        self.assertIn(ql.graduation.drop_room, street)

    def test_every_room_is_fresh_to_the_corpus(self):
        # The "every room fresh" claim: none of this arc's four rooms is used by
        # ANY other chain in the corpus (in particular none of the prior six
        # Tatooine arcs' rooms).
        ql = self._questline()
        used = {step.location for step in ql.steps}
        used.add(ql.graduation.drop_room)
        other = _other_chain_rooms()
        overlap = used & other
        self.assertFalse(
            overlap,
            f"The Cut Coil reuses rooms already in the chain corpus "
            f"{overlap} — the 'every room fresh' claim is false")


class TestNpcs(_RealCorpusBase):

    def setUp(self):
        super().setUp()
        self.npcs = (yaml.safe_load(open(NPC_FILE, encoding="utf-8"))
                     or {}).get("npcs") or []
        self.by_name = {n["name"]: n for n in self.npcs}

    def test_giver_present_in_start_room(self):
        self.assertIn(GIVER_NPC, self.by_name)
        giver = self.by_name[GIVER_NPC]
        # Display name of mos_eisley_south_end.
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

    def test_antagonist_carries_proven_ranged_weapon(self):
        # Back in the proven beatable band: Vagh Sarko carries blaster_pistol
        # (the ranged foils' weapon) so a fresh post-chargen character has a
        # real, winnable fight with no balance flag.
        ant = self.by_name[ANTAGONIST_NPC]
        weapon = (ant.get("char_sheet") or {}).get("weapon")
        self.assertEqual(weapon, "blaster_pistol")
        weapons = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "weapons.yaml", encoding="utf-8"))
        wkeys = weapons.get("weapons", weapons)
        keys = set(wkeys.keys()) if isinstance(wkeys, dict) else {
            w.get("key") for w in wkeys}
        self.assertIn("blaster_pistol", keys,
                      "the foil's weapon 'blaster_pistol' is not a real weapon "
                      "key")

    def test_foil_is_in_the_winnable_band(self):
        # A fresh post-chargen character must be able to win this fight: the
        # foil's combat stats sit under the same ceilings the corpus-wide
        # winnability-band guard enforces (mirrored here so a drift in THIS
        # drop's foil is caught by THIS drop's test).
        def _pips(code):
            n, _, p = str(code).partition("+")
            return int(n.replace("D", "")) * 3 + (int(p) if p else 0)
        ant = self.by_name[ANTAGONIST_NPC]
        cs = ant.get("char_sheet") or {}
        sk = cs.get("skills") or {}
        at = cs.get("attributes") or {}
        self.assertLessEqual(_pips(sk["blaster"]), _pips("5D"))   # to-hit ceiling
        self.assertGreaterEqual(_pips(sk["blaster"]), _pips("3D+1"))  # non-vacuous
        self.assertLessEqual(_pips(sk["dodge"]), _pips("4D+1"))   # defense ceiling
        self.assertLessEqual(_pips(sk["brawling"]), _pips("5D"))  # melee ceiling
        self.assertLessEqual(_pips(at["strength"]), _pips("4D"))  # soak ceiling

    def test_exactly_two_placed_npcs(self):
        # The combat questline ships exactly the giver + the single foil; the
        # garage boss (Hax Vortassa), the offworld fence, the cut coils and gutted
        # recovery droids and rigged invoices, the recovery crew, the working-folk
        # owners, the Dowager Queen corner's Jawas and con men, the South End
        # neighbors, and the Mos Eisley vehicle-licensing prefect are narrated-only.
        self.assertEqual(len(self.npcs), 2,
                         "The Cut Coil should place exactly two NPCs "
                         "(the giver + the combat foil)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_cut_coil.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
