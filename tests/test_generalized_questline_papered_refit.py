# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_papered_refit.py — T3.24 generalized
quest expansion, thirty-third slice.

Proves the THIRTY-THIRD accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Papered Refit" (kuat_papered_refit) — is shipped correctly and
walks start->graduation through the PRODUCTION dispatcher, the same hooks the
live parser calls. Like the first thirty-two slices it reuses the live
questline engine (active_questline slot, the existing event types, the four
reward funnels) with NO new engine code, per quest_expansion_postlaunch_path_v1.md.

Firsts for the accessible-questline arc:
  * a THIRTY-THIRD distinct skill spread — CAPITAL SHIP REPAIR (Technical) +
    CAPITAL SHIP WEAPON REPAIR (Technical) — neither of which any prior
    accessible questline uses. It is the FIRST accessible questline to reward
    the CAPITAL-SHIP / BIG-SHIP YARD-TECH build, the FIRST to use CAPITAL SHIP
    REPAIR, the FIRST to use CAPITAL SHIP WEAPON REPAIR, and the FIRST accessible
    arc set on the CAPITAL-SHIP (big-ship) class at all. (This is NOT a
    cross-attribute spread — both skills are Technical — so it is the THIRD
    both-Technical spread, after The Rigged Issue's blaster repair + armor repair
    and The Cut Coil's repulsorlift repair + droid repair, and it is NOT the
    first ship arc: The Salted Lane, The Condemned Hull, The Rolled Log, and The
    Hollow Fit worked ship classes before it. What is genuinely first is the two
    CAPITAL-SHIP skills, the big-ship class, and the prove-the-overhaul-never-
    happened pairing: one hand opens the "overhauled" hull to show its mandated
    structural rework was never done, the other cycles the "serviced"
    point-defense to show its armament work was never done. Pointedly distinct
    from The Hollow Fit's SMALL-SHIP starship weapon repair, which works a light
    freighter's hull-mount cannon — this works a CAPITAL-class bulk freighter's
    point-defense array, a distinct skill under a distinct heading in skills.yaml.);
  * set on KUAT, spanning the kuat_main_spaceport and kdy_orbital_ring zones
    (spaceport_concourse_hotel / kuat_arrivals / kdy_main_offices /
    kuat_ring_apartments), every room of which is FRESH to the entire chain
    corpus. The Skimmed Line and The Condemned Hull worked the orbital-ring yard,
    so this is honestly the FIFTH Kuat arc, NEITHER a fresh face NOR a
    single-zone cluster: it is a CROSS-ZONE assembly of four rooms, precedented
    by The Empty Proof's and The Hollow Fit's cross-zone clusters. Only the
    step-4 combat room must be combat-capable (kuat_ring_apartments is
    contested); the giver/return room and the two skill rooms host no fight. The
    Senate/Jedi/Republic war effort have no reach at a civilian merchant-refit
    contractor and never appear; the racket is run afoul of by the shippers' own
    survey board, the way every prior accessible arc keeps the larger powers
    offstage;
  * a foil who carries the proven blaster_pistol of the ranged foils, squarely
    in the proven beatable band (the same in-band guarded stat line as The
    Salted Lane's ... The Hollow Fit's foils), pointedly NOT the melee line of
    The Condemned Hull's out-of-band Houk foil.

The story shape is new too — breaking a PHANTOM-REFIT / SURVEY-COMPLETION fraud,
the first accessible arc whose racket is billing for a mandated capital-ship
overhaul that was never performed and forging the survey that swears it was done.
A civilian merchant-refit contractor paid by the bulk-freight combines to
overhaul their capital freighters' hulls and point-defense instead books each
ship in, does no work, forges the survey, bills the full fee, and returns the
freighter unsound. So open the "overhauled" freighter's hull and read the
mandated rework undone (capital ship repair), cycle its "bench-serviced"
point-defense on the yard's cradle and read it dead (capital ship weapon
repair), stand off the yard's enforcer in the ring residential block
(combat_won), and put the phantom overhaul on the shippers' survey board.
Pointedly DISTINCT from the prior arcs it might be mistaken for: The Hollow Fit
GUTS installed defenses and fences the cores; The Empty Proof's PROOF-HOUSE
certifies third-party arms untested; The Condemned Hull seizes a SOUND ship as
derelict; The Rolled Log rolls back a CRAFT's history; The Cut Coil DAMAGES a
sound speeder — here the contracted repairer bills for an overhaul of the
client's own capital ship it never performed. It carries a real combat climax
(step 4), with a single placed antagonist NPC and a chain_enemy_template.

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

QUESTLINE_ID = "kuat_papered_refit"
ACHIEVEMENT_KEY = "papered_refit_cleared"
GIVER_NPC = "Ormo Delth"
ANTAGONIST_NPC = "Vodran Sekk"
ENEMY_TEMPLATE = "papered_refit_enforcer"
START_ROOM = "spaceport_concourse_hotel"
GIVER_ROOM_NAME = "Kuat - Spaceport Concourse Hotel"
ANTAGONIST_ROOM_NAME = "Kuat Drive Yards - Ring Residential Block"
COMBAT_ROOM_SLUG = "kuat_ring_apartments"
# A CROSS-ZONE cluster: the four rooms span two Kuat zones.
CLUSTER_ZONES = {"kuat_main_spaceport", "kdy_orbital_ring"}
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_papered_refit.yaml")

# The thirty-third skill spread, in step order (steps 2/3 are skill_check_passed).
EXPECTED_SKILLS = ["capital ship repair", "capital ship weapon repair"]

# The skill spreads of the prior THIRTY-TWO accessible questlines (each non-combat
# skill that gates a skill_check_passed step). The thirty-third spread must
# share NO skill with any of them — the "thirty-third DISTINCT spread" claim.
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


def _kuat_rooms() -> list:
    data = yaml.safe_load(open(
        PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "planets"
        / "kuat.yaml", encoding="utf-8"))
    rooms = data["rooms"]
    if isinstance(rooms, dict):
        return [{"slug": k, **(v or {})} for k, v in rooms.items()]
    return rooms


def _kuat_room_slugs() -> set:
    return {r.get("slug") or r.get("id") for r in _kuat_rooms()}


def _cluster_zone_slugs() -> set:
    return {r.get("slug") or r.get("id") for r in _kuat_rooms()
            if r.get("zone") in CLUSTER_ZONES}


def _room_by_slug(slug: str) -> dict:
    for r in _kuat_rooms():
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

        # Step 1: talk to Ormo Delth (the shipwright)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: open an "overhauled" capital hull (capital ship repair)
        _run(on_skill_check_passed(db, char, "capital ship repair", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: cycle a "serviced" point-defense dead (capital ship weapon repair)
        _run(on_skill_check_passed(db, char, "capital ship weapon repair", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: stop Vodran Sekk in the ring residential block (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Ormo Delth -> graduate
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
        _run(on_skill_check_passed(db, char, "capital ship repair", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on capital ship repair; a passing capital-ship-weapon-repair
        # check (this questline's OWN step-3 skill) must NOT advance step 2 —
        # the gate is per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "capital ship weapon repair", True,
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
        _run(on_skill_check_passed(db, char, "capital ship repair", True,
                                   difficulty=11))
        _run(on_skill_check_passed(db, char, "capital ship weapon repair", True,
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

    def test_skill_spread_is_repair_then_weapon_repair(self):
        # The thirty-third distinct spread: the two skill_check_passed steps
        # gate on capital ship repair then capital ship weapon repair (no prior
        # accessible questline uses either).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_spread_is_distinct_from_all_prior_arcs(self):
        # The "thirty-third DISTINCT spread" claim: neither spread skill is used
        # by any of the prior thirty-two accessible questlines.
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

    def test_spread_is_both_technical(self):
        # The defining build: the CAPITAL-SHIP / BIG-SHIP YARD-TECH — capital
        # ship repair (open an "overhauled" hull to read its mandated rework
        # undone) + capital ship weapon repair (cycle a "serviced" point-defense
        # to read it dead). Grounded against the live skills.yaml: BOTH are
        # TECHNICAL — an honestly both-Technical spread (the THIRD, after The
        # Rigged Issue and The Cut Coil; NOT a cross-attribute spread, and that
        # claim is not made). Each skill lives under Technical and NONE of the
        # other five.
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))

        def pool(attr):
            return {s["name"].lower() for s in (skills.get(attr) or [])}

        self.assertIn("capital ship repair", pool("technical"))
        self.assertIn("capital ship weapon repair", pool("technical"))
        for attr in ("strength", "knowledge", "perception", "mechanical",
                     "dexterity"):
            self.assertNotIn("capital ship repair", pool(attr))
            self.assertNotIn("capital ship weapon repair", pool(attr))

    def test_no_prior_arc_used_the_spread_skills(self):
        # The "first capital-ship-repair / first capital-ship-weapon-repair arc"
        # claim: no prior accessible arc used either skill. (The prior ship arcs
        # worked SMALL-SHIP classes — space transports, starfighter, starship —
        # never the CAPITAL-SHIP class.)
        self.assertNotIn("capital ship repair", PRIOR_SPREAD_SKILLS,
                         "a prior arc already used capital ship repair — the "
                         "'first capital-ship-repair arc' claim is false")
        self.assertNotIn("capital ship weapon repair", PRIOR_SPREAD_SKILLS,
                         "a prior arc already used capital ship weapon repair — "
                         "the 'first capital-ship-weapon-repair arc' claim is "
                         "false")

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
            "skills": json.dumps({"capital ship repair": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"technical": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "capital ship repair", reg)
        raw_pool = _get_skill_pool(untrained, "capital ship repair", reg)
        # A char who trained Capital Ship Repair must roll a STRICTLY larger pool
        # than a char rolling raw Technical — proving the authored skill resolves
        # to the trained skill rather than the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored spread skill 'capital ship repair' must roll the trained "
            "pool, not raw Technical")

    def test_all_step_rooms_are_real_kuat_rooms(self):
        # The "questline set on Kuat" claim: every step room (and the drop room)
        # is a real loaded Kuat room (planets/kuat.yaml).
        kuat = _kuat_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, kuat,
                          f"step {step.step} location {step.location!r} is not "
                          f"a Kuat room — the 'Kuat arc' claim is false")
        self.assertIn(ql.graduation.drop_room, kuat)

    def test_all_step_rooms_in_the_cross_zone_cluster(self):
        # The CROSS-ZONE cluster claim: every step room (and the drop room) is a
        # real loaded room in the kuat_main_spaceport OR kdy_orbital_ring zone,
        # and BOTH zones are actually used (a genuine cross-zone assembly, not a
        # single-zone cluster).
        cluster = _cluster_zone_slugs()
        ql = self._questline()
        used_zones = set()
        for step in ql.steps:
            self.assertIn(step.location, cluster,
                          f"step {step.step} location {step.location!r} is not "
                          f"in the kuat_main_spaceport/kdy_orbital_ring cluster")
            used_zones.add(_room_by_slug(step.location).get("zone"))
        self.assertIn(ql.graduation.drop_room, cluster)
        self.assertEqual(used_zones, CLUSTER_ZONES,
                         f"the cluster is not genuinely cross-zone: {used_zones}")

    def test_combat_room_is_not_secured(self):
        # The step-4 combat foil must sit in a combat-capable (non-SECURED)
        # room or the fight is gated and the questline cannot be walked: the ring
        # residential block is contested (no explicit security_level). (The
        # giver/return and skill rooms host no fight, so their security is
        # immaterial — the survey office is SECURED and that is fine.)
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
        # by ANY other chain in the corpus (in particular none of The Skimmed
        # Line's or The Condemned Hull's orbital-ring rooms).
        ql = self._questline()
        used = {step.location for step in ql.steps}
        used.add(ql.graduation.drop_room)
        other = _other_chain_rooms()
        overlap = used & other
        self.assertFalse(
            overlap,
            f"The Papered Refit reuses rooms already in the chain corpus "
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
        # Display name of spaceport_concourse_hotel.
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
        # Back in the proven beatable band: Vodran Sekk carries blaster_pistol
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
        # The giver's sheet is skewed to the capital-ship hull-and-armament of a
        # refit inspector — she embodies the two skills the quest sends a hand to
        # use.
        giver = self.by_name[GIVER_NPC]
        sk = (giver.get("char_sheet") or {}).get("skills") or {}
        for s in EXPECTED_SKILLS:
            self.assertIn(s, sk,
                          f"giver should carry the quest skill {s!r}")

    def test_exactly_two_placed_npcs(self):
        # The combat questline ships exactly the giver + the single foil; the
        # yard-master (Palo Kessin), the survey clerk, the combines and shippers,
        # the underwriters and the survey board, the "overhauled" bulk freighter,
        # and the deep-lane raiders are narrated-only.
        self.assertEqual(len(self.npcs), 2,
                         "The Papered Refit should place exactly two NPCs "
                         "(the giver + the combat foil)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_papered_refit.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
