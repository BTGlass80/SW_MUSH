# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_empty_proof.py — T3.24 generalized
quest expansion, twenty-seventh slice.

Proves the TWENTY-SEVENTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Empty Proof" (tatooine_empty_proof) — is shipped correctly and
walks start->graduation through the PRODUCTION dispatcher, the same hooks the
live parser calls. Like the first twenty-six slices it reuses the live
questline engine (active_questline slot, the existing event types, the four
reward funnels) with NO new engine code, per
quest_expansion_postlaunch_path_v1.md.

Firsts for the accessible-questline arc:
  * a TWENTY-SEVENTH distinct skill spread — FIREARMS (Dexterity) + THROWN
    WEAPONS (Dexterity) — neither of which any prior accessible questline
    uses. It is the FIRST accessible questline to reward the MARKSMAN /
    RANGE-MASTER build, the FIRST to use FIREARMS, the FIRST to use THROWN
    WEAPONS, and the FIRST arc whose spread is drawn entirely from the
    DEXTERITY weapon-skill pool (the first weapon-skill arc of the corpus,
    now that Strength, Knowledge, and Perception are all exhausted);
  * set on TATOOINE, on the Mos Eisley wastes-road / Jundland frontier
    (outskirts_trail_junction / jundland_canyon_mouth / outskirts_checkpoint
    / jundland_tusken_overlook), every room of which is FRESH to the entire
    chain corpus. The Dust-Sick already set an arc on the Tatooine wastes, so
    this is honestly the SECOND arc on that frontier (the EIGHTH Tatooine arc
    overall), NOT a fresh face; what is fresh is the four-room ROOM CLUSTER.
    Only the step-4 combat room must be combat-capable
    (jundland_tusken_overlook is lawless); the giver/return room and the two
    proof rooms host no fight. Hutt-fringe Tatooine has no Republic civic
    authority to keep offstage; the clone troopers at the checkpoint are
    ambient witnesses, and the proof-house is run afoul of by the town's own
    arms-licensing prefect, so the larger powers stay offstage the way every
    prior accessible arc keeps them offstage;
  * a foil who carries the proven blaster_pistol of the ranged foils, squarely
    in the proven beatable band (the same in-band guarded stat line as The
    Salted Lane's ... The Fixed Bout's foils), pointedly NOT the melee line of
    The Condemned Hull's out-of-band Houk foil.

The story shape is new too — breaking an INDEPENDENT WEAPONS-PROOF-HOUSE
CERTIFICATION FRAUD, the FIRST accessible arc whose racket is a corrupt
third-party CERTIFIER rather than a crooked buyer, seller, or service. A
licensed proof-house takes a cut to stamp frontier defense lots
"range-proofed" without ever firing or throwing a piece of them, so untested
arms reach the wastes-road collectives behind a clean independent mark. So
fire a stamped carbine false on the canyon backstop (firearms), throw the
stamped irons false in front of the checkpoint's clone troopers as neutral
witnesses (thrown weapons), stand off the proof-house's enforcer on the
lawless overlook ridge (combat_won), and carry the failed lot and the
skipped-proof log to the arms-licensing prefect. Pointedly DISTINCT from The
Rigged Issue (a crooked SELLER substituting counterfeits, busted by an
ARMORER): here the corrupt actor is the independent CERTIFIER, busted by a
MARKSMAN re-running the proof the bench skipped. It carries a real combat
climax (step 4), with a single placed antagonist NPC and a
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

QUESTLINE_ID = "tatooine_empty_proof"
ACHIEVEMENT_KEY = "empty_proof_cleared"
GIVER_NPC = "Sela Marrenn"
ANTAGONIST_NPC = "Sesko Vahr"
ENEMY_TEMPLATE = "empty_proof_enforcer"
START_ROOM = "outskirts_trail_junction"
GIVER_ROOM_NAME = "City Outskirts - Desert Trail Junction"
ANTAGONIST_ROOM_NAME = "Jundland Wastes - Tusken Camp Overlook"
COMBAT_ROOM_SLUG = "jundland_tusken_overlook"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_empty_proof.yaml")

# The twenty-seventh skill spread, in step order (steps 2/3 are skill_check_passed).
EXPECTED_SKILLS = ["firearms", "thrown weapons"]

# The skill spreads of the prior TWENTY-SIX accessible questlines (each non-combat
# skill that gates a skill_check_passed step). The twenty-seventh spread must share
# NO skill with any of them — the "twenty-seventh DISTINCT spread" claim.
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


def _wastes_frontier_slugs() -> set:
    return {r.get("slug") or r.get("id") for r in _tatooine_rooms()
            if r.get("zone") in ("tatooine_outskirts", "tatooine_jundland")}


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

        # Step 1: talk to Sela Marrenn (the caravan-guard captain)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: proof-fire the stamped carbine false on the backstop (firearms)
        _run(on_skill_check_passed(db, char, "firearms", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: throw the stamped irons false at the witnessed line (thrown weapons)
        _run(on_skill_check_passed(db, char, "thrown weapons", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: stop Sesko Vahr on the overlook ridge (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Sela Marrenn -> graduate
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
        _run(on_skill_check_passed(db, char, "firearms", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on firearms; a passing thrown-weapons check (this
        # questline's OWN step-3 skill) must NOT advance step 2 — the gate is
        # per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "thrown weapons", True,
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
        _run(on_skill_check_passed(db, char, "firearms", True,
                                   difficulty=11))
        _run(on_skill_check_passed(db, char, "thrown weapons", True,
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

    def test_skill_spread_is_firearms_then_thrown_weapons(self):
        # The twenty-seventh distinct spread: the two skill_check_passed steps
        # gate on firearms then thrown weapons (no prior accessible questline
        # uses either).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_spread_is_distinct_from_all_prior_arcs(self):
        # The "twenty-seventh DISTINCT spread" claim: neither spread skill is
        # used by any of the prior twenty-six accessible questlines.
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

    def test_spread_is_two_dexterity_weapon_skills(self):
        # The defining first: the spread is the MARKSMAN / RANGE-MASTER build —
        # firearms (the eye on a backstop) + thrown weapons (the hand on a
        # witnessed line). Grounded against the live skills.yaml: BOTH are
        # Dexterity skills — the FIRST accessible arc whose spread is drawn
        # entirely from the Dexterity weapon-skill pool, the first weapon-skill
        # arc of the corpus.
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))
        dexterity = {s["name"].lower()
                     for s in (skills.get("dexterity") or [])}
        for sk in EXPECTED_SKILLS:
            self.assertIn(sk, dexterity,
                          f"spread skill {sk!r} is not a Dexterity skill — the "
                          f"marksman / weapon-skill claim is false")
        # Neither spread skill belongs to any OTHER attribute (the spread is
        # purely Dexterity).
        for attr in ("strength", "knowledge", "perception", "mechanical",
                     "technical"):
            pool = {s["name"].lower() for s in (skills.get(attr) or [])}
            for sk in EXPECTED_SKILLS:
                self.assertNotIn(sk, pool,
                                 f"spread skill {sk!r} also appears under "
                                 f"{attr} — the pure-Dexterity claim is false")

    def test_no_prior_arc_used_a_dexterity_weapon_skill(self):
        # The "first WEAPON-skill arc" claim: no prior accessible arc used any
        # of Dexterity's combat/weapon skills. (Pick Pocket is the one prior
        # Dexterity skill used — The Sealed Ledger — but it is a non-combat
        # finesse skill, not a weapon skill, so the marksman claim stands.)
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))
        dexterity = {s["name"].lower()
                     for s in (skills.get("dexterity") or [])}
        weapon_skills = dexterity - {"pick pocket"}
        used_weapon_skills = weapon_skills & PRIOR_SPREAD_SKILLS
        self.assertFalse(
            used_weapon_skills,
            f"a prior arc already used a Dexterity weapon skill "
            f"{used_weapon_skills} — the 'first weapon-skill arc' claim is "
            f"false")

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
            "skills": json.dumps({"firearms": "5D"}),
        }
        untrained = {
            "attributes": json.dumps({"dexterity": "3D"}),
            "skills": json.dumps({}),
        }
        trained_pool = _get_skill_pool(trained, "firearms", reg)
        raw_pool = _get_skill_pool(untrained, "firearms", reg)
        # A char who trained Firearms must roll a STRICTLY larger pool than a
        # char rolling raw Dexterity — proving the authored skill resolves to
        # the trained skill rather than the bare attribute.
        self.assertGreater(
            trained_pool, raw_pool,
            "authored spread skill 'firearms' must roll the trained pool, not "
            "raw Dexterity")

    def test_all_step_rooms_are_real_tatooine_rooms(self):
        # The "questline set on Tatooine" claim: every step room (and the drop
        # room) is a real loaded Tatooine room (planets/tatooine.yaml).
        tat = _tatooine_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, tat,
                          f"step {step.step} location {step.location!r} is not "
                          f"a Tatooine room — the 'Tatooine arc' claim is false")
        self.assertIn(ql.graduation.drop_room, tat)

    def test_all_step_rooms_on_wastes_frontier(self):
        # The "Mos Eisley wastes-road / Jundland frontier" claim: every step
        # room (and the drop room) is a real loaded tatooine_outskirts- or
        # tatooine_jundland-zone room.
        frontier = _wastes_frontier_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, frontier,
                          f"step {step.step} location {step.location!r} is not "
                          f"an outskirts/jundland frontier room — the "
                          f"'wastes-road frontier' claim is false")
        self.assertIn(ql.graduation.drop_room, frontier)

    def test_combat_room_is_not_secured(self):
        # The step-4 combat foil must sit in a combat-capable (non-SECURED)
        # room or the fight is gated and the questline cannot be walked: the
        # overlook ridge is lawless. (The giver/return and proof rooms host no
        # fight, so their security is immaterial.)
        ql = self._questline()
        combat = [s for s in ql.steps
                  if (s.completion or {}).get("type") == "combat_won"][0]
        self.assertEqual(combat.location, COMBAT_ROOM_SLUG)
        room = _room_by_slug(COMBAT_ROOM_SLUG)
        self.assertIn(room.get("security_level"), ("contested", "lawless"),
                      f"combat room {COMBAT_ROOM_SLUG!r} is SECURED — the "
                      f"step-4 fight would be gated and unwalkable")

    def test_every_room_is_fresh_to_the_corpus(self):
        # The "every room fresh" claim: none of this arc's four rooms is used
        # by ANY other chain in the corpus (in particular none of The
        # Dust-Sick's Tatooine-wastes rooms).
        ql = self._questline()
        used = {step.location for step in ql.steps}
        used.add(ql.graduation.drop_room)
        other = _other_chain_rooms()
        overlap = used & other
        self.assertFalse(
            overlap,
            f"The Empty Proof reuses rooms already in the chain corpus "
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
        # Display name of outskirts_trail_junction.
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
        # Back in the proven beatable band: Sesko Vahr carries blaster_pistol
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
        # The giver's sheet is skewed to the firearms-and-thrown of a
        # wastes-road guard captain — she embodies the two skills the quest
        # sends a hand to use.
        giver = self.by_name[GIVER_NPC]
        sk = (giver.get("char_sheet") or {}).get("skills") or {}
        for s in EXPECTED_SKILLS:
            self.assertIn(s, sk,
                          f"giver should carry the quest skill {s!r}")

    def test_exactly_two_placed_npcs(self):
        # The combat questline ships exactly the giver + the single foil; the
        # proof-master (Veth Tannor), his off-world broker, the failed lot and
        # the skipped-proof log, the collectives and caravan outfits, the dead
        # guards, the ambient clone troopers who witness the proof, the rival
        # proof-house, and the arms-licensing prefect are narrated-only.
        self.assertEqual(len(self.npcs), 2,
                         "The Empty Proof should place exactly two NPCs "
                         "(the giver + the combat foil)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_empty_proof.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
