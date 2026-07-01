# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_cold_charge.py — T3.24 generalized
quest expansion, thirty-first slice.

Proves the THIRTY-FIRST accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Cold Charge" (mos_eisley_cold_charge) — is shipped correctly and
walks start->graduation through the PRODUCTION dispatcher, the same hooks the
live parser calls. Like the first thirty slices it reuses the live questline
engine (active_questline slot, the existing event types, the four reward
funnels) with NO new engine code, per quest_expansion_postlaunch_path_v1.md.

Firsts for the accessible-questline arc:
  * a THIRTY-FIRST distinct skill spread — GRENADE (Dexterity) + MISSILE
    WEAPONS (Dexterity) — neither of which any prior accessible questline uses.
    It is the FIRST accessible questline to reward the HEAVY-ORDNANCE /
    EXPLOSIVE-ORDNANCE (EOD) build, the FIRST to use GRENADE, and the FIRST to
    use MISSILE WEAPONS. (Honestly BOTH spread skills are Dexterity, so this is
    NOT a cross-attribute spread — it is the THIRD all-Dexterity-weapon-pool
    spread, after The Empty Proof's firearms + thrown weapons (27th) and The
    Paper Death's running + melee combat (30th); and it is NOT the first weapon
    arc — The Empty Proof's marksman came first. What is genuinely first is the
    grenade and missile-weapons skills and the heavy-ordnance /
    prove-the-round-is-live pairing: one hand safes a "destroyed" grenade to
    show it never burned, the other runs a "demilitarized" launcher-round to
    show it still fires.);
  * set on TATOOINE, in the tatooine_mos_eisley zone (mos_eisley_inn /
    lucky_despot_staircase / dimu_monastery_gate / lucky_despot_star_chamber),
    every room of which is FRESH to the entire chain corpus. The Crooked Wheel,
    The Sabotaged Run, The Long Haul, The Short Weight, and The Cut Coil all
    already used tatooine_mos_eisley rooms, so this is honestly the SIXTH arc on
    the Mos Eisley street face (the TENTH Tatooine arc overall), NOT a fresh
    face; what is fresh is the four-room ROOM CLUSTER. Only the step-4 combat
    room must be combat-capable (lucky_despot_star_chamber is contested); the
    giver/return room and the two skill rooms host no fight. The
    Senate/Jedi/Republic war effort have no reach at a fringe demil yard and
    never appear; the racket is run afoul of by the settlers' own supply board,
    the way every prior accessible arc keeps the larger powers offstage;
  * a foil who carries the proven blaster_pistol of the ranged foils, squarely
    in the proven beatable band (the same in-band guarded stat line as The
    Salted Lane's ... The Paper Death's foils), pointedly NOT the melee line of
    The Condemned Hull's out-of-band Houk foil.

The story shape is new too — breaking a DEMILITARIZATION-DIVERSION /
FALSIFIED-DESTRUCTION fraud, the first accessible arc whose racket is faking the
DESTRUCTION of dangerous goods. A licensed ordnance-disposal outfit paid by the
fringe settlers to safely demilitarize and destroy their surplus ordnance
instead logs the live lots "cold" (destroyed) on forged manifests, keeps the
munitions, and sells them to the fringe raiders and underworld, so the same
ordnance the settlers paid to have destroyed comes back at them in raider hands.
So pull a "destroyed" grenade off the crated demil lot and safe it live
(grenade), range-fire a "demilitarized" seismic round into the empty wastes
(missile weapons), stand off the yard's enforcer at the hotel-cafe front
(combat_won), and put a live round the manifest swore was destroyed on the
settlers' supply board. Pointedly DISTINCT from the prior arcs it might be
mistaken for: The Fouled Sump DUMPS hazardous waste to hide a poison; The Empty
Proof SKIPS a proof it was paid to run; The Rigged Issue SUBSTITUTES
counterfeits; The Rolled Log rolls back a CRAFT's history; The Cut Coil DAMAGES
a sound speeder — here the DESTRUCTION of live goods is faked and the goods kept
and sold. It carries a real combat climax (step 4), with a single placed
antagonist NPC and a chain_enemy_template.

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

QUESTLINE_ID = "mos_eisley_cold_charge"
ACHIEVEMENT_KEY = "cold_charge_cleared"
GIVER_NPC = "Dessa Molvar"
ANTAGONIST_NPC = "Hurss Kadag"
ENEMY_TEMPLATE = "cold_charge_enforcer"
START_ROOM = "mos_eisley_inn"
GIVER_ROOM_NAME = "Mos Eisley Inn"
ANTAGONIST_ROOM_NAME = "Lucky Despot - Star Chamber Cafe"
COMBAT_ROOM_SLUG = "lucky_despot_star_chamber"
STARTING_ZONE = "tatooine_mos_eisley"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_cold_charge.yaml")

# The thirty-first skill spread, in step order (steps 2/3 are skill_check_passed).
EXPECTED_SKILLS = ["grenade", "missile weapons"]

# The skill spreads of the prior THIRTY accessible questlines (each non-combat
# skill that gates a skill_check_passed step). The thirty-first spread must
# share NO skill with any of them — the "thirty-first DISTINCT spread" claim.
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
    "swoop operation", "vehicle blasters",
    "starfighter piloting", "starfighter repair",
    "running", "melee combat",
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
            if r.get("zone") == STARTING_ZONE}


def _room_by_slug(slug: str) -> dict:
    for r in _tatooine_rooms():
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

        # Step 1: talk to Dessa Molvar (the ordnance-hand)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: safe a "destroyed" grenade live in the holds (grenade)
        _run(on_skill_check_passed(db, char, "grenade", True, difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: range-fire a "demilitarized" seismic round (missile weapons)
        _run(on_skill_check_passed(db, char, "missile weapons", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: stop Hurss Kadag at the Star Chamber (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Dessa Molvar -> graduate
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
        _run(on_skill_check_passed(db, char, "grenade", False, difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on grenade; a passing missile-weapons check (this
        # questline's OWN step-3 skill) must NOT advance step 2 — the gate is
        # per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "missile weapons", True,
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
        _run(on_skill_check_passed(db, char, "grenade", True, difficulty=11))
        _run(on_skill_check_passed(db, char, "missile weapons", True,
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

    def test_skill_spread_is_grenade_then_missile(self):
        # The thirty-first distinct spread: the two skill_check_passed steps
        # gate on grenade then missile weapons (no prior accessible questline
        # uses either).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_spread_is_distinct_from_all_prior_arcs(self):
        # The "thirty-first DISTINCT spread" claim: neither spread skill is used
        # by any of the prior thirty accessible questlines.
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

    def test_spread_is_all_dexterity_not_a_cross(self):
        # The defining build: the HEAVY-ORDNANCE / EOD hand — grenade (arm and
        # safe a "destroyed" round to show it never burned) + missile weapons
        # (run a "demilitarized" launcher-round to show it still fires).
        # Grounded against the live skills.yaml: BOTH are DEXTERITY skills. This
        # is the HONEST framing — NOT a cross-attribute spread, but the THIRD
        # all-Dexterity-weapon-pool spread (after The Empty Proof's firearms +
        # thrown weapons and The Paper Death's running + melee combat); the
        # genuine firsts are the grenade and missile-weapons skills and the
        # prove-the-round-is-live pairing, asserted elsewhere.
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))
        dexterity = {s["name"].lower()
                     for s in (skills.get("dexterity") or [])}
        for sk in EXPECTED_SKILLS:
            self.assertIn(sk, dexterity,
                          f"spread skill {sk!r} is not a Dexterity skill — the "
                          f"all-Dexterity spread claim is false")
        # Both live under DEXTERITY and NONE of the other five attributes — a
        # genuinely intra-attribute (not cross) spread.
        for attr in ("strength", "knowledge", "perception", "mechanical",
                     "technical"):
            pool = {s["name"].lower() for s in (skills.get(attr) or [])}
            for sk in EXPECTED_SKILLS:
                self.assertNotIn(sk, pool,
                                 f"spread skill {sk!r} also appears under "
                                 f"{attr} — the clean all-Dexterity claim is "
                                 f"false")

    def test_no_prior_arc_used_grenade_or_missile_weapons(self):
        # The "first grenade / first missile-weapons arc" claim: no prior
        # accessible arc used either skill. (The prior Dexterity-weapon arcs,
        # The Empty Proof and The Paper Death, used firearms + thrown weapons
        # and running + melee combat — never grenade or missile weapons.)
        self.assertNotIn("grenade", PRIOR_SPREAD_SKILLS,
                         "a prior arc already used grenade — the 'first "
                         "grenade arc' claim is false")
        self.assertNotIn("missile weapons", PRIOR_SPREAD_SKILLS,
                         "a prior arc already used missile weapons — the 'first "
                         "missile-weapons arc' claim is false")

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
            "attributes": json.dumps({"dexterity": "3D"}),
            "skills": json.dumps({"grenade": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"dexterity": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "grenade", reg)
        raw_pool = _get_skill_pool(untrained, "grenade", reg)
        # A char who trained Grenade must roll a STRICTLY larger pool than a
        # char rolling raw Dexterity — proving the authored skill resolves to
        # the trained skill rather than the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored spread skill 'grenade' must roll the trained pool, not "
            "raw Dexterity")

    def test_all_step_rooms_are_real_tatooine_rooms(self):
        # The "questline set on Tatooine" claim: every step room (and the drop
        # room) is a real loaded Tatooine room (planets/tatooine.yaml).
        tat = _tatooine_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, tat,
                          f"step {step.step} location {step.location!r} is not "
                          f"a Tatooine room — the 'Tatooine arc' claim is "
                          f"false")
        self.assertIn(ql.graduation.drop_room, tat)

    def test_all_step_rooms_in_mos_eisley_zone(self):
        # The "Mos Eisley" claim: every step room (and the drop room) is a real
        # loaded tatooine_mos_eisley-zone room.
        mos_eisley = _mos_eisley_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, mos_eisley,
                          f"step {step.step} location {step.location!r} is not "
                          f"a tatooine_mos_eisley room — the 'Mos Eisley' claim "
                          f"is false")
        self.assertIn(ql.graduation.drop_room, mos_eisley)

    def test_combat_room_is_not_secured(self):
        # The step-4 combat foil must sit in a combat-capable (non-SECURED)
        # room or the fight is gated and the questline cannot be walked: the
        # Lucky Despot's Star Chamber is contested. (The giver/return and skill
        # rooms host no fight, so their security is immaterial.)
        ql = self._questline()
        combat = [s for s in ql.steps
                  if (s.completion or {}).get("type") == "combat_won"][0]
        self.assertEqual(combat.location, COMBAT_ROOM_SLUG)
        room = _room_by_slug(COMBAT_ROOM_SLUG)
        # Only the SECURED level gates NPC combat (_check_security_gate); a room
        # with no explicit security_level defaults to CONTESTED (combat-capable).
        self.assertNotEqual(room.get("security_level"), "secured",
                            f"combat room {COMBAT_ROOM_SLUG!r} is SECURED — the "
                            f"step-4 fight would be gated and unwalkable")

    def test_every_room_is_fresh_to_the_corpus(self):
        # The "every room fresh" claim: none of this arc's four rooms is used
        # by ANY other chain in the corpus (in particular none of The Cut
        # Coil's / The Short Weight's other tatooine_mos_eisley rooms).
        ql = self._questline()
        used = {step.location for step in ql.steps}
        used.add(ql.graduation.drop_room)
        other = _other_chain_rooms()
        overlap = used & other
        self.assertFalse(
            overlap,
            f"The Cold Charge reuses rooms already in the chain corpus "
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
        # Display name of mos_eisley_inn.
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
        # Back in the proven beatable band: Hurss Kadag carries blaster_pistol
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
        # The giver's sheet is skewed to the grenade-and-launcher of a disposal
        # tech — she embodies the two skills the quest sends a hand to use.
        giver = self.by_name[GIVER_NPC]
        sk = (giver.get("char_sheet") or {}).get("skills") or {}
        for s in EXPECTED_SKILLS:
            self.assertIn(s, sk,
                          f"giver should carry the quest skill {s!r}")

    def test_exactly_two_placed_npcs(self):
        # The combat questline ships exactly the giver + the single foil; the
        # yard-master (Vorm Dessek), the manifest-clerk, the fringe raiders and
        # fences, the settler collectives and caravan pools, the crated demil
        # lots, the settlers hit at the frontier, and the supply board are
        # narrated-only.
        self.assertEqual(len(self.npcs), 2,
                         "The Cold Charge should place exactly two NPCs "
                         "(the giver + the combat foil)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_cold_charge.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
