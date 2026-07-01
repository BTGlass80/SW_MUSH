# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_cleared_fault.py — T3.24 generalized
quest expansion, thirty-fifth slice.

Proves the THIRTY-FIFTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Cleared Fault" (coruscant_cleared_fault) — is shipped correctly and
walks start->graduation through the PRODUCTION dispatcher, the same hooks the
live parser calls. Like the first thirty-four slices it reuses the live
questline engine (active_questline slot, the existing event types, the four
reward funnels) with NO new engine code, per quest_expansion_postlaunch_path_v1.md.

Firsts for the accessible-questline arc:
  * a THIRTY-FIFTH distinct skill spread — BLASTER (Dexterity) + BOWCASTER
    (Dexterity) — neither of which any prior accessible questline uses. It is the
    FIRST accessible questline to reward the PERSONAL-WEAPONS RANGE-MASTER /
    GUNSMITH-PROOF build, the FIRST to use BLASTER as a chain skill, and the
    FIRST to use BOWCASTER. (This is NOT a cross-attribute spread — both skills
    are Dexterity — so it is the FOURTH all-Dexterity-weapon-pool spread, after
    The Empty Proof's firearms + thrown weapons, The Paper Death's running +
    melee combat, and The Cold Charge's grenade + missile weapons, and it is NOT
    the first weapon arc. What is genuinely first is the two DEXTERITY personal-
    firearm skills BLASTER and BOWCASTER, and the prove-the-fault-is-live pairing
    on personal weapons: one hand runs a "recall-cleared" production blaster hot
    on the range to trip the chamber/actuator fault the recall swears was fixed,
    the other spans a "recall-cleared" bowcaster to full draw to show the
    riser/limb fault the recall swears was fixed still fractures. Pointedly
    distinct from The Empty Proof's marksman, which RE-RUNS a proof a proof-house
    SKIPPED on un-tested third-party arms — here the marksman TRIPS a specific
    KNOWN defect the seller's own forged recall swears it re-worked out, on the
    seller's own goods. Note blaster and dodge are the FOILS' combat stats across
    the corpus, but neither has ever gated a chain skill_check_passed step —
    blaster is a genuinely fresh CHAIN skill here.);
  * set on CORUSCANT, in the commercial_district zone (outlander_club /
    invisec_main_street / invisec_border / mid_residential_block), every room of
    which is FRESH to the entire chain corpus. The Sealed Ledger and The Blank
    Ticket worked the commercial district, so this is honestly another Coruscant
    arc, NOT a fresh face: what is fresh is the four-room SINGLE-ZONE cluster.
    Only the step-4 combat room must be combat-capable (mid_residential_block is
    contested — no explicit security_level); the giver/return room and the two
    firing-proof rooms host no fight (all three SECURED, which is immaterial to a
    skill check);
  * a foil who carries the proven blaster_pistol of the ranged foils, squarely
    in the proven beatable band (the same in-band guarded stat line as The
    Salted Lane's ... The Papered Refit's foils), pointedly NOT the melee line of
    The Condemned Hull's out-of-band Houk foil.

The story shape is new too — breaking a SUPPRESSED-DEFECT / FAKED-RECALL
product-safety cover-up on personal weapons, the first accessible arc whose
racket is knowingly selling a lethal manufacturing defect, forging the
recall-compliance record that swears the defect was re-worked out, and burying
the buyers' injury reports. A civilian arms retailer sells personal blasters and
bowcasters, a whole lot of which carries a known burst/fracture fault; instead of
pulling the lot it forges a recall-compliance certificate swearing every unit
re-worked, keeps selling the untouched defective stock as "recall-cleared," and
buries the injury reports. So run a "recall-cleared" blaster hot on the range and
trip its buried chamber fault (blaster), span a "recall-cleared" bowcaster to
full draw and read its buried riser fault fracture (bowcaster), stand off the
retailer's enforcer in the residential block (combat_won), and put the live
defect on the arms-standards board. Pointedly DISTINCT from the prior arcs it
might be mistaken for: The Empty Proof's PROOF-HOUSE certifies third-party arms
untested (a skipped test on others' goods); The Rigged Issue SUBSTITUTES
counterfeits; The Cold Charge fakes DESTRUCTION; The Hollow Fit GUTS a ship's
defenses; The Fouled Sump hides an environmental poison — here the seller knows
the exact defect, fakes the recall that swears it fixed, and buries the victims.
It carries a real combat climax (step 4), with a single placed antagonist NPC and
a chain_enemy_template.

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

QUESTLINE_ID = "coruscant_cleared_fault"
ACHIEVEMENT_KEY = "cleared_fault_cleared"
GIVER_NPC = "Kesh Ordan"
ANTAGONIST_NPC = "Draven Kohl"
ENEMY_TEMPLATE = "cleared_fault_enforcer"
START_ROOM = "outlander_club"
GIVER_ROOM_NAME = "Coruscant - The Outlander Club"
ANTAGONIST_ROOM_NAME = "Coruscant - Mid-Level Residential Block"
COMBAT_ROOM_SLUG = "mid_residential_block"
# A SINGLE-ZONE cluster: all four rooms are in the one commercial_district zone.
CLUSTER_ZONE = "commercial_district"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_cleared_fault.yaml")

# The thirty-fifth skill spread, in step order (steps 2/3 are skill_check_passed).
EXPECTED_SKILLS = ["blaster", "bowcaster"]

# The skill spreads of the prior THIRTY-FOUR accessible questlines (each non-combat
# skill that gates a skill_check_passed step). The thirty-fifth spread must
# share NO skill with any of them — the "thirty-fifth DISTINCT spread" claim.
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
    "grenade", "missile weapons",
    "starship weapon repair", "starship shields",
    "capital ship repair", "capital ship weapon repair",
    "capital ship piloting", "capital ship gunnery", "capital ship shields",
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


def _zone_slugs() -> set:
    return {r.get("slug") or r.get("id") for r in _coruscant_rooms()
            if r.get("zone") == CLUSTER_ZONE}


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

        # Step 1: talk to Kesh Ordan (the range-master)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: run a "recall-cleared" blaster to its burst (blaster)
        _run(on_skill_check_passed(db, char, "blaster", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: span a "recall-cleared" bowcaster to its fracture (bowcaster)
        _run(on_skill_check_passed(db, char, "bowcaster", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: stop Draven Kohl in the residential block (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Kesh Ordan -> graduate
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
        _run(on_skill_check_passed(db, char, "blaster", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on blaster; a passing bowcaster check (this questline's
        # OWN step-3 skill) must NOT advance step 2 — the gate is per-step, not
        # "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "bowcaster", True,
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
        _run(on_skill_check_passed(db, char, "blaster", True,
                                   difficulty=11))
        _run(on_skill_check_passed(db, char, "bowcaster", True,
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

    def test_skill_spread_is_blaster_then_bowcaster(self):
        # The thirty-fifth distinct spread: the two skill_check_passed steps
        # gate on blaster then bowcaster (no prior accessible questline uses
        # either as a chain skill).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_spread_is_distinct_from_all_prior_arcs(self):
        # The "thirty-fifth DISTINCT spread" claim: neither spread skill is used
        # by any of the prior thirty-four accessible questlines.
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

    def test_spread_is_both_dexterity(self):
        # The defining build: the PERSONAL-WEAPONS RANGE-MASTER — blaster (run a
        # "recall-cleared" blaster hot to trip its buried chamber fault) +
        # bowcaster (span a "recall-cleared" bowcaster to full draw to show its
        # buried riser fault fracture). Grounded against the live skills.yaml:
        # BOTH are DEXTERITY — an honestly both-Dexterity spread (the FOURTH,
        # after The Empty Proof, The Paper Death, and The Cold Charge; NOT a
        # cross-attribute spread, and that claim is not made). Each skill lives
        # under Dexterity and NONE of the other five.
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))

        def pool(attr):
            return {s["name"].lower() for s in (skills.get(attr) or [])}

        self.assertIn("blaster", pool("dexterity"))
        self.assertIn("bowcaster", pool("dexterity"))
        for attr in ("strength", "knowledge", "perception", "mechanical",
                     "technical"):
            self.assertNotIn("blaster", pool(attr))
            self.assertNotIn("bowcaster", pool(attr))

    def test_no_prior_arc_used_the_spread_skills(self):
        # The "first blaster-chain / first bowcaster arc" claim: no prior
        # accessible arc used either skill as a chain skill. (Blaster and dodge
        # are the FOILS' combat stats, but never a skill_check_passed gate.)
        self.assertNotIn("blaster", PRIOR_SPREAD_SKILLS,
                         "a prior arc already used blaster as a chain skill — "
                         "the 'first blaster arc' claim is false")
        self.assertNotIn("bowcaster", PRIOR_SPREAD_SKILLS,
                         "a prior arc already used bowcaster — the 'first "
                         "bowcaster arc' claim is false")

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
            "skills": json.dumps({"blaster": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"dexterity": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "blaster", reg)
        raw_pool = _get_skill_pool(untrained, "blaster", reg)
        # A char who trained Blaster must roll a STRICTLY larger pool than a char
        # rolling raw Dexterity — proving the authored skill resolves to the
        # trained skill rather than the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored spread skill 'blaster' must roll the trained pool, not "
            "raw Dexterity")

    def test_all_step_rooms_are_real_coruscant_rooms(self):
        # The "questline set on Coruscant" claim: every step room (and the drop
        # room) is a real loaded Coruscant room (planets/coruscant.yaml).
        cor = _coruscant_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, cor,
                          f"step {step.step} location {step.location!r} is not "
                          f"a Coruscant room — the 'Coruscant arc' claim is "
                          f"false")
        self.assertIn(ql.graduation.drop_room, cor)

    def test_all_step_rooms_in_the_commercial_district(self):
        # The SINGLE-ZONE cluster claim: every step room (and the drop room) is
        # a real loaded room in the commercial_district zone.
        zone = _zone_slugs()
        ql = self._questline()
        used_zones = set()
        for step in ql.steps:
            self.assertIn(step.location, zone,
                          f"step {step.step} location {step.location!r} is not "
                          f"in the commercial_district zone")
            used_zones.add(_room_by_slug(step.location).get("zone"))
        self.assertIn(ql.graduation.drop_room, zone)
        self.assertEqual(used_zones, {CLUSTER_ZONE},
                         f"the cluster is not single-zone: {used_zones}")

    def test_combat_room_is_not_secured(self):
        # The step-4 combat foil must sit in a combat-capable (non-SECURED)
        # room or the fight is gated and the questline cannot be walked: the
        # mid-level residential block is contested (no explicit security_level).
        # (The giver/return and skill rooms host no fight, so their security is
        # immaterial — the three Invisible Sector / Outlander rooms are SECURED
        # and that is fine.)
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
        # by ANY other chain in the corpus (in particular none of The Sealed
        # Ledger's or The Blank Ticket's commercial-district rooms).
        ql = self._questline()
        used = {step.location for step in ql.steps}
        used.add(ql.graduation.drop_room)
        other = _other_chain_rooms()
        overlap = used & other
        self.assertFalse(
            overlap,
            f"The Cleared Fault reuses rooms already in the chain corpus "
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
        # Display name of outlander_club.
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
        # Back in the proven beatable band: Draven Kohl carries blaster_pistol
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
        # The giver's sheet is skewed to the personal-weapons proof-work of a
        # range-safety armorer — he embodies the two skills the quest sends a
        # hand to use.
        giver = self.by_name[GIVER_NPC]
        sk = (giver.get("char_sheet") or {}).get("skills") or {}
        for s in EXPECTED_SKILLS:
            self.assertIn(s, sk,
                          f"giver should carry the quest skill {s!r}")

    def test_exactly_two_placed_npcs(self):
        # The combat questline ships exactly the giver + the single foil; the
        # proprietor (Ostra Vell), the clerks, the manufacturer, the buyers, the
        # maimed and dead, and the arms-standards board are narrated-only.
        self.assertEqual(len(self.npcs), 2,
                         "The Cleared Fault should place exactly two NPCs "
                         "(the giver + the combat foil)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_cleared_fault.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
