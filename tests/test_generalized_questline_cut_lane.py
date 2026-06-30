# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_cut_lane.py — T3.24 generalized
quest expansion, twenty-eighth slice.

Proves the TWENTY-EIGHTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Cut Lane" (coruscant_cut_lane) — is shipped correctly and walks
start->graduation through the PRODUCTION dispatcher, the same hooks the live
parser calls. Like the first twenty-seven slices it reuses the live questline
engine (active_questline slot, the existing event types, the four reward
funnels) with NO new engine code, per quest_expansion_postlaunch_path_v1.md.

Firsts for the accessible-questline arc:
  * a TWENTY-EIGHTH distinct skill spread — SWOOP OPERATION (Mechanical) +
    VEHICLE BLASTERS (Dexterity) — neither of which any prior accessible
    questline uses. It is the FIRST accessible questline to reward the
    SADDLE-GUNNER / SWOOP-OUTRIDER build, the FIRST to use SWOOP OPERATION,
    the FIRST to use VEHICLE BLASTERS, only the SECOND cross-attribute spread
    of the corpus (after The Fixed Bout's brawling + willpower, a Strength +
    Knowledge pair) and the FIRST to cross MECHANICAL + DEXTERITY. (Honestly
    NOT the first vehicle arc — ground/repulsorlift/walker/hover OPERATION came
    before it — and NOT the first weapon arc — The Empty Proof's marksman came
    first; what is genuinely first is the swoop and vehicle-blasters skills, the
    ride-and-shoot-from-a-mount pairing, and the Mechanical+Dexterity cross);
  * set on CORUSCANT, on the Monumental District's freight skylanes
    (column_commons / western_sea / skydome_gardens / kallarak_amphitheater),
    every room of which is FRESH to the entire chain corpus. The False
    Provenance already set an arc in the Monumental District, so this is
    honestly the SECOND arc on that face (the SEVENTH Coruscant arc overall),
    NOT a fresh face; what is fresh is the four-room ROOM CLUSTER. Only the
    step-4 combat room must be combat-capable (kallarak_amphitheater is
    contested); the giver/return room and the two skill rooms host no fight.
    The Senate/Jedi/Republic war overhead never reach a freight-lane skim over
    the Monumental District; the lane is run afoul of by the bled shippers and
    the skylane freight registry, the way every prior accessible arc keeps the
    larger powers offstage;
  * a foil who carries the proven blaster_pistol of the ranged foils, squarely
    in the proven beatable band (the same in-band guarded stat line as The
    Salted Lane's ... The Empty Proof's foils), pointedly NOT the melee line of
    The Condemned Hull's out-of-band Houk foil.

The story shape is new too — breaking a STAGED-RAID FREIGHT-LOSS / COURIER-SKIM
INSURANCE FRAUD. A licensed skycourier outfit flies its own outriders, masked
and unmarked, as the "skylane raiders" that plague its run, cutting marked
parcels off its own courier swoops, filing them raider-lost to pocket the
shippers' indemnity and keep the goods, and selling the same bled shippers a
costlier "armed escort" against the raiders that are the company itself. So ride
a hired swoop onto the open gap over the Western Sea to shadow a marked run and
catch the skim coming off the company's own lane-house heading (swoop
operation), gun the staged raider down intact off the saddle over the Skydome
Gardens (vehicle blasters), stand off the lane-boss at the impound dock behind
the Kallarak Amphitheater (combat_won), and carry the downed company swoop, its
flight-log, and the cut parcel to the skylane freight registry. Pointedly
DISTINCT from the two prior staged-loss / salvage arcs The Wreckers' Light
(wreck-luring) and The Salted Lane (planted contraband): here nothing is wrecked
and nothing is planted; the company stages raids on its own runs, busted by a
neutral OUTRIDER who rides the lane and guns the staged raider down. It carries a
real combat climax (step 4), with a single placed antagonist NPC and a
chain_enemy_template.

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

QUESTLINE_ID = "coruscant_cut_lane"
ACHIEVEMENT_KEY = "cut_lane_cleared"
GIVER_NPC = "Resa Halix"
ANTAGONIST_NPC = "Drovan Pell"
ENEMY_TEMPLATE = "cut_lane_enforcer"
START_ROOM = "column_commons"
GIVER_ROOM_NAME = "Coruscant - Column Commons District"
ANTAGONIST_ROOM_NAME = "Coruscant - Kallarak Amphitheater"
COMBAT_ROOM_SLUG = "kallarak_amphitheater"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_cut_lane.yaml")

# The twenty-eighth skill spread, in step order (steps 2/3 are skill_check_passed).
EXPECTED_SKILLS = ["swoop operation", "vehicle blasters"]

# The skill spreads of the prior TWENTY-SEVEN accessible questlines (each non-combat
# skill that gates a skill_check_passed step). The twenty-eighth spread must share
# NO skill with any of them — the "twenty-eighth DISTINCT spread" claim.
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
    "repulsorlift repair", "droid repair",
    "walker operation", "hover vehicle operation",
    "brawling", "willpower",
    "firearms", "thrown weapons",
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
        "id": 55, "name": "Freelancer PC", "room_id": 100,
        "attributes": json.dumps(base),
    }


def _attrs(char: dict) -> dict:
    return json.loads(char["attributes"])


def _qstate(char: dict) -> dict:
    from engine.tutorial_chains import _QUESTLINE_KEY
    return _attrs(char).get(_QUESTLINE_KEY) or {}


def _coruscant_rooms() -> list:
    data = yaml.safe_load(open(
        PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "planets"
        / "coruscant.yaml", encoding="utf-8"))
    rooms = data["rooms"]
    if isinstance(rooms, dict):
        return [{"slug": k, **(v or {})} for k, v in rooms.items()]
    return rooms


def _coruscant_room_slugs() -> set:
    return {r.get("slug") or r.get("id") for r in _coruscant_rooms()}


def _monumental_slugs() -> set:
    return {r.get("slug") or r.get("id") for r in _coruscant_rooms()
            if r.get("zone") == "monumental_district"}


def _room_by_slug(slug: str) -> dict:
    for r in _coruscant_rooms():
        if (r.get("slug") or r.get("id")) == slug:
            return r
    return {}


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

        # Step 1: talk to Resa Halix (the freight-broker)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: shadow the marked run over the Western Sea (swoop operation)
        _run(on_skill_check_passed(db, char, "swoop operation", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: gun the staged raider down over the gardens (vehicle blasters)
        _run(on_skill_check_passed(db, char, "vehicle blasters", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: stop Drovan Pell at the impound dock (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Resa Halix -> graduate
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
        _run(on_skill_check_passed(db, char, "swoop operation", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on swoop operation; a passing vehicle-blasters check
        # (this questline's OWN step-3 skill) must NOT advance step 2 — the gate
        # is per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "vehicle blasters", True,
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
        _run(on_skill_check_passed(db, char, "swoop operation", True,
                                   difficulty=11))
        _run(on_skill_check_passed(db, char, "vehicle blasters", True,
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

    def test_skill_spread_is_swoop_op_then_vehicle_blasters(self):
        # The twenty-eighth distinct spread: the two skill_check_passed steps
        # gate on swoop operation then vehicle blasters (no prior accessible
        # questline uses either).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_spread_is_distinct_from_all_prior_arcs(self):
        # The "twenty-eighth DISTINCT spread" claim: neither spread skill is
        # used by any of the prior twenty-seven accessible questlines.
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

    def test_spread_crosses_mechanical_and_dexterity(self):
        # The defining first: the spread is the SADDLE-GUNNER / SWOOP-OUTRIDER
        # build — swoop operation (the hands that keep a swoop on the lane) +
        # vehicle blasters (the hand that fires the swoop's mounted gun).
        # Grounded against the live skills.yaml: swoop operation is a MECHANICAL
        # skill and vehicle blasters a DEXTERITY skill — the FIRST accessible
        # arc to cross Mechanical + Dexterity (only the SECOND cross-attribute
        # spread overall, after The Fixed Bout's Strength + Knowledge).
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))
        mechanical = {s["name"].lower()
                      for s in (skills.get("mechanical") or [])}
        dexterity = {s["name"].lower()
                     for s in (skills.get("dexterity") or [])}
        self.assertIn("swoop operation", mechanical,
                      "swoop operation is not a Mechanical skill — the "
                      "Mechanical+Dexterity cross claim is false")
        self.assertIn("vehicle blasters", dexterity,
                      "vehicle blasters is not a Dexterity skill — the "
                      "Mechanical+Dexterity cross claim is false")
        # The two skills live under DIFFERENT attributes (a genuine cross, not a
        # single-attribute pair like the marksman's pure Dexterity).
        for attr in ("strength", "knowledge", "perception", "technical"):
            pool = {s["name"].lower() for s in (skills.get(attr) or [])}
            for sk in EXPECTED_SKILLS:
                self.assertNotIn(sk, pool,
                                 f"spread skill {sk!r} also appears under "
                                 f"{attr} — the clean Mechanical+Dexterity "
                                 f"cross claim is false")
        # swoop operation must NOT be a Dexterity skill nor vehicle blasters a
        # Mechanical one (the cross is genuine, not a same-attribute pair).
        self.assertNotIn("swoop operation", dexterity)
        self.assertNotIn("vehicle blasters", mechanical)

    def test_no_prior_arc_used_swoop_op_or_vehicle_blasters(self):
        # The "first swoop / first vehicle-blasters arc" claim: no prior
        # accessible arc used either skill. (Repulsorlift/ground/walker/hover
        # OPERATION were used before, and firearms/thrown weapons were used by
        # the marksman arc, but neither swoop operation nor vehicle blasters has
        # appeared.)
        self.assertNotIn("swoop operation", PRIOR_SPREAD_SKILLS,
                         "a prior arc already used swoop operation — the "
                         "'first swoop arc' claim is false")
        self.assertNotIn("vehicle blasters", PRIOR_SPREAD_SKILLS,
                         "a prior arc already used vehicle blasters — the "
                         "'first vehicle-blasters arc' claim is false")

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
            "attributes": json.dumps({"mechanical": "3D"}),
            "skills": json.dumps({"swoop operation": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"mechanical": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "swoop operation", reg)
        raw_pool = _get_skill_pool(untrained, "swoop operation", reg)
        # A char who trained Swoop Operation must roll a STRICTLY larger pool
        # than a char rolling raw Mechanical — proving the authored skill
        # resolves to the trained skill rather than the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored spread skill 'swoop operation' must roll the trained "
            "pool, not raw Mechanical")

    def test_all_step_rooms_are_real_coruscant_rooms(self):
        # The "questline set on Coruscant" claim: every step room (and the drop
        # room) is a real loaded Coruscant room (planets/coruscant.yaml).
        cor = _coruscant_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, cor,
                          f"step {step.step} location {step.location!r} is not "
                          f"a Coruscant room — the 'Coruscant arc' claim is false")
        self.assertIn(ql.graduation.drop_room, cor)

    def test_all_step_rooms_in_monumental_district(self):
        # The "Monumental District skylanes" claim: every step room (and the
        # drop room) is a real loaded monumental_district-zone room.
        monumental = _monumental_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, monumental,
                          f"step {step.step} location {step.location!r} is not "
                          f"a Monumental District room — the 'Monumental "
                          f"District' claim is false")
        self.assertIn(ql.graduation.drop_room, monumental)

    def test_combat_room_is_not_secured(self):
        # The step-4 combat foil must sit in a combat-capable (non-SECURED)
        # room or the fight is gated and the questline cannot be walked: the
        # impound dock behind the amphitheater is contested. (The giver/return
        # and skill rooms host no fight, so their security is immaterial.)
        ql = self._questline()
        combat = [s for s in ql.steps
                  if (s.completion or {}).get("type") == "combat_won"][0]
        self.assertEqual(combat.location, COMBAT_ROOM_SLUG)
        room = _room_by_slug(COMBAT_ROOM_SLUG)
        # Only the SECURED level gates NPC combat (_check_security_gate); a room
        # with no explicit security_level defaults to CONTESTED (combat-capable),
        # which is the case for kallarak_amphitheater. So the test is "not
        # secured", not "explicitly contested/lawless".
        self.assertNotEqual(room.get("security_level"), "secured",
                            f"combat room {COMBAT_ROOM_SLUG!r} is SECURED — the "
                            f"step-4 fight would be gated and unwalkable")

    def test_every_room_is_fresh_to_the_corpus(self):
        # The "every room fresh" claim: none of this arc's four rooms is used
        # by ANY other chain in the corpus (in particular none of The False
        # Provenance's Monumental-District rooms).
        ql = self._questline()
        used = {step.location for step in ql.steps}
        used.add(ql.graduation.drop_room)
        other = _other_chain_rooms()
        overlap = used & other
        self.assertFalse(
            overlap,
            f"The Cut Lane reuses rooms already in the chain corpus "
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
        # Display name of column_commons.
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
        # Back in the proven beatable band: Drovan Pell carries blaster_pistol
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

    def test_giver_spread_embodies_the_quest_skills(self):
        # The giver's sheet is skewed to the swoop-and-saddle-gun of an
        # ex-lane-outrider — she embodies the two skills the quest sends a hand
        # to use.
        giver = self.by_name[GIVER_NPC]
        sk = (giver.get("char_sheet") or {}).get("skills") or {}
        for s in EXPECTED_SKILLS:
            self.assertIn(s, sk,
                          f"giver should carry the quest skill {s!r}")

    def test_exactly_two_placed_npcs(self):
        # The combat questline ships exactly the giver + the single foil; the
        # lane-master (Pell Helevin), the off-world fence, the masked company
        # outriders, the cut parcel and the company swoop's flight-log, the bled
        # shippers, the genteel district foot traffic, and the skylane freight
        # registry are narrated-only.
        self.assertEqual(len(self.npcs), 2,
                         "The Cut Lane should place exactly two NPCs "
                         "(the giver + the combat foil)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_cut_lane.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
