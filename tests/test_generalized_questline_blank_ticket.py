# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_blank_ticket.py — T3.24 generalized
quest expansion, thirty-fourth slice.

Proves the THIRTY-FOURTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Blank Ticket" (coruscant_blank_ticket) — is shipped correctly and
walks start->graduation through the PRODUCTION dispatcher, the same hooks the
live parser calls. Like the first thirty-three slices it reuses the live
questline engine (active_questline slot, the existing event types, the four
reward funnels) with NO new engine code, per quest_expansion_postlaunch_path_v1.md.

Firsts for the accessible-questline arc:
  * a THIRTY-FOURTH distinct skill spread — CAPITAL SHIP PILOTING + CAPITAL SHIP
    GUNNERY + CAPITAL SHIP SHIELDS, all three Mechanical — none of which any
    prior accessible questline uses. It is the FIRST accessible questline to
    reward the CAPITAL-SHIP BRIDGE-CREW / OPERATIONS build (fly it, fight it,
    screen it), the FIRST to use CAPITAL SHIP PILOTING, the FIRST to use CAPITAL
    SHIP GUNNERY, and the FIRST to use CAPITAL SHIP SHIELDS — the big-ship
    OPERATIONS pool, sibling to the 33rd's big-ship REPAIR pool (The Papered
    Refit). This is NOT a cross-attribute spread — all three skills are
    Mechanical — and it is NOT the first ship arc (The Salted Lane, The Condemned
    Hull, The Rolled Log, The Hollow Fit, and The Papered Refit worked ship
    classes before it). What is genuinely first is the three CAPITAL-SHIP
    OPERATIONS skills, the bridge-crew / merchant-marine build, and the RUN-THE-
    THREE-BOARDS pairing: run the helm board, the gunnery board, and the shield
    board to master standard, on the fraud's own rigs, to prove the boards were
    never run on the crews it "certified";
  * only the SECOND accessible questline that resolves on SKILL, not force —
    three skill-check steps and NO combat step, after The Sealed Ledger
    (coruscant_works_sealed_ledger, the ninth). It is the FIRST no-combat arc
    whose three checks are all one attribute's pool (all Mechanical). Because
    there is no combat step there is no antagonist NPC and no chain_enemy_template;
    the only placed NPC is the giver. (The static reachability Class-5 anti-
    vacuous combat check stays satisfied corpus-wide by the tutorial chains and
    the thirty-two combat-climax questlines.);
  * set on CORUSCANT — the fourth Coruscant arc and the SECOND on the mid-city
    commercial_district face (after The Sealed Ledger), on a FRESH four-room
    cluster (coco_town_civic_block / coco_town_loft_district /
    coco_town_market_arcade / outlander_cantina), reusing NONE of The Sealed
    Ledger's rooms. Every room is SECURED, which is fine: with no combat step
    there is no fight to gate, so a certification-fraud arc that resolves on three
    demonstrated boards fits the civilian, secured mid-city cleanly. The big-ship
    OPERATIONS pool would normally hit the civilian-big-ship-ROOM problem; this
    sidesteps it entirely because the boards are run on LEASED SIMULATOR RIGS
    (how bridge crews are certified) rather than on a berth.

The story shape is new too — breaking a CREW-CERTIFICATION / COMPETENCY-TICKET
fraud, the first accessible arc whose racket forges a PERSON's competency rather
than a ship's, a document's, or a good's. A licensed bridge-crew certification
bureau (Coreward Crew Certification) holds the merchant freight lines' contract
to run the mandatory competency boards a spacer must pass before a line may rate
them to a capital-freighter bridge, and instead of running the boards SELLS the
tickets: a cadet pays, gets a full master's rating stamped, never sits a rig, and
the bureau logs an instant "pass" with no simulator telemetry behind it — so the
lines put "certified" bridge officers who cannot run a bridge onto capital
freighters and the ships founder. Jenra Voll, a retired capital-ship master and
spacers'-board examiner, can't beat it on paper (its tickets over-rule her
marks), so run its master helm board (capital ship piloting), master gunnery
board (capital ship gunnery), and master shield board (capital ship shields) for
real, and put three real boards beside a book of blank ones. Pointedly DISTINCT
from The Sealed Ledger (its no-combat sibling: forges DEBT-RECORDS, busted by a
thief's three hands), The Empty Proof (certifies GOODS untested), The Bonded
Crew (bonds a crew via debt), The Papered Refit (bills for a ship's OVERHAUL, the
REPAIR pool), and The Hollow Fit (guts a ship's real defenses). It resolves on
finesse with NO combat step, a single placed NPC (the giver) and no
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

QUESTLINE_ID = "coruscant_blank_ticket"
ACHIEVEMENT_KEY = "blank_ticket_cleared"
GIVER_NPC = "Jenra Voll"
START_ROOM = "coco_town_civic_block"
GIVER_ROOM_NAME = "Coruscant - Coco Town - Civic Block"
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_blank_ticket.yaml")

# The thirty-fourth skill spread, in step order (steps 2/3/4 are
# skill_check_passed — a THREE-skill, no-combat arc).
EXPECTED_SKILLS = ["capital ship piloting", "capital ship gunnery",
                   "capital ship shields"]

# The four cluster rooms (all commercial_district), and the one prior
# commercial_district arc whose rooms must NOT be reused.
CLUSTER_ROOMS = {"coco_town_civic_block", "coco_town_loft_district",
                 "coco_town_market_arcade", "outlander_cantina"}
CLUSTER_ZONE = "commercial_district"
SEALED_LEDGER_ROOMS = {"dexters_diner", "mid_transit_hub",
                       "commercial_district_main",
                       "commercial_district_atmospheric"}

# The skill spreads of the prior THIRTY-THREE accessible questlines (each
# non-combat skill that gates a skill_check_passed step). The thirty-fourth
# spread must share NO skill with any of them — the "thirty-fourth DISTINCT
# spread" claim.
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
    # The 33rd (The Papered Refit) — the big-ship REPAIR pool.
    "capital ship repair", "capital ship weapon repair",
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
        "id": 56, "name": "Freelancer PC", "room_id": 100,
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
        )
        from engine.tutorial_chains import is_chain_complete, _QUESTLINE_KEY

        char = _char()
        db = _make_fake_db()

        ok, msg = _run(start_questline(db, char, QUESTLINE_ID))
        self.assertTrue(ok, msg)
        self.assertEqual(_qstate(char).get("step"), 1)

        # Step 1: talk to Jenra Voll (the spacers'-board examiner)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: run the master helm board (capital ship piloting)
        _run(on_skill_check_passed(db, char, "capital ship piloting", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: run the master gunnery board (capital ship gunnery)
        _run(on_skill_check_passed(db, char, "capital ship gunnery", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: run the master shield board (capital ship shields) — the
        # CLIMAX is a skill check, not a fight.
        _run(on_skill_check_passed(db, char, "capital ship shields", True,
                                   difficulty=14))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Jenra -> graduate
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
        _run(on_skill_check_passed(db, char, "capital ship piloting", False,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on capital ship piloting; a passing capital-ship-gunnery
        # check (this questline's OWN step-3 skill) must NOT advance step 2 —
        # the gate is per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "capital ship gunnery", True,
                                   difficulty=11))
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

    def test_skill_spread_is_the_three_capital_ship_operations_skills(self):
        # The thirty-fourth distinct spread: the three skill_check_passed steps
        # gate on capital ship piloting -> gunnery -> shields (no prior
        # accessible questline uses any of the three).
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_no_combat_step_board_climax(self):
        # Only the SECOND no-combat arc (after The Sealed Ledger): resolves on
        # demonstrated competence with NO combat_won step anywhere — the climax
        # (step 4) is a skill check (the shield board), not a fight.
        ql = self._questline()
        ctypes = [(s.completion or {}).get("type") for s in ql.steps]
        self.assertNotIn("combat_won", ctypes,
                         "The Blank Ticket is a no-combat questline — it must "
                         "contain no combat_won step")
        self.assertEqual((ql.steps[3].completion or {}).get("type"),
                         "skill_check_passed",
                         "the climax (step 4) must be the shield board (a "
                         "skill-check), not a fight")

    def test_spread_is_distinct_from_all_prior_arcs(self):
        # The "thirty-fourth DISTINCT spread" claim: none of the three spread
        # skills is used by any of the prior thirty-three accessible questlines.
        overlap = set(EXPECTED_SKILLS) & PRIOR_SPREAD_SKILLS
        self.assertFalse(
            overlap,
            f"spread shares a skill with a prior arc: {overlap}")

    def test_spread_is_all_mechanical(self):
        # The defining build: the CAPITAL-SHIP BRIDGE-CREW / OPERATIONS — capital
        # ship piloting (run the helm board) + capital ship gunnery (run the
        # gunnery board) + capital ship shields (run the shield board). Grounded
        # against the live skills.yaml: all three are MECHANICAL — an honestly
        # all-Mechanical spread (NOT a cross-attribute spread, and that claim is
        # not made). Each skill lives under Mechanical and NONE of the other five.
        skills = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8"))

        def pool(attr):
            return {s["name"].lower() for s in (skills.get(attr) or [])}

        for sk in EXPECTED_SKILLS:
            self.assertIn(sk, pool("mechanical"),
                          f"{sk!r} should be a Mechanical skill")
            for attr in ("strength", "knowledge", "perception", "technical",
                         "dexterity"):
                self.assertNotIn(sk, pool(attr),
                                 f"{sk!r} should not also be under {attr}")

    def test_no_prior_arc_used_the_spread_skills(self):
        # The "first capital-ship-piloting / -gunnery / -shields arc" claim: no
        # prior accessible arc used any of the three. (The prior big-ship arc,
        # The Papered Refit, worked the REPAIR pool — capital ship repair +
        # weapon repair — never the OPERATIONS pool.)
        for sk in EXPECTED_SKILLS:
            self.assertNotIn(
                sk, PRIOR_SPREAD_SKILLS,
                f"a prior arc already used {sk!r} — the "
                f"'first {sk} arc' claim is false")

    def test_spread_skills_resolve_to_trained_pools(self):
        # All three spread skills must canonicalize to a registered SkillDef so a
        # character who TRAINED them rolls their real pool at `chain attempt`,
        # not the raw attribute (the drop-24 phantom-skill class).
        from engine.character import canonical_skill_key
        from engine.skill_checks import _get_skill_pool, _get_default_registry
        reg = _get_default_registry()
        for sk in EXPECTED_SKILLS:
            # None of the spread skills is aliased — each canonicalizes to itself.
            self.assertEqual(canonical_skill_key(sk), sk)
            self.assertIsNotNone(reg.get(sk),
                                 f"spread skill {sk!r} does not resolve to a "
                                 f"registered skill")
            trained = {
                "attributes": json.dumps({"mechanical": "3D"}),
                "skills": json.dumps({sk: "5D"}),
            }
            untrained = {
                "attributes": json.dumps({"mechanical": "3D"}),
                "skills": json.dumps({}),
            }
            trained_pool = _get_skill_pool(trained, sk, reg)
            raw_pool = _get_skill_pool(untrained, sk, reg)
            # A char who trained the skill must roll a STRICTLY larger pool than
            # a char rolling raw Mechanical — proving the authored skill resolves
            # to the trained skill rather than the bare attribute.
            self.assertGreater(
                trained_pool, raw_pool,
                f"authored spread skill {sk!r} must roll the trained pool, "
                f"not raw Mechanical")

    def test_all_step_rooms_are_commercial_district(self):
        # The "Coruscant mid-city commercial_district cluster" claim: every step
        # room (and the drop room) is a real loaded Coruscant room in the
        # commercial_district zone.
        ql = self._questline()
        for step in ql.steps:
            room = _room_by_slug(step.location)
            self.assertTrue(room, f"step {step.step} location "
                            f"{step.location!r} is not a Coruscant room")
            self.assertEqual(room.get("zone"), CLUSTER_ZONE,
                             f"step {step.step} location {step.location!r} is "
                             f"not in the {CLUSTER_ZONE} zone")
        drop = _room_by_slug(ql.graduation.drop_room)
        self.assertEqual(drop.get("zone"), CLUSTER_ZONE)

    def test_cluster_is_the_expected_four_rooms(self):
        ql = self._questline()
        used = {step.location for step in ql.steps}
        used.add(ql.graduation.drop_room)
        self.assertEqual(used, CLUSTER_ROOMS,
                         f"the arc's rooms {used} are not the expected fresh "
                         f"cluster {CLUSTER_ROOMS}")

    def test_reuses_no_sealed_ledger_rooms(self):
        # The SECOND arc on the commercial_district face; it must share no step
        # room with The Sealed Ledger (else the "fresh cluster" claim is false).
        ql = self._questline()
        mine = {step.location for step in ql.steps}
        overlap = mine & SEALED_LEDGER_ROOMS
        self.assertFalse(overlap,
                         f"overlaps The Sealed Ledger's rooms: {overlap}")

    def test_every_room_is_fresh_to_the_corpus(self):
        # The "every room fresh" claim: none of this arc's four rooms is used by
        # ANY other chain in the corpus.
        ql = self._questline()
        used = {step.location for step in ql.steps}
        used.add(ql.graduation.drop_room)
        other = _other_chain_rooms()
        overlap = used & other
        self.assertFalse(
            overlap,
            f"The Blank Ticket reuses rooms already in the chain corpus "
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
        # Display name of coco_town_civic_block.
        self.assertEqual(giver["room"], GIVER_ROOM_NAME)
        self.assertFalse(giver["ai_config"].get("hostile"),
                         "the questline giver must not be hostile")

    def test_no_antagonist_and_no_chain_enemy_template(self):
        # The no-combat questline ships ONLY the giver — no antagonist NPC and
        # no chain_enemy_template anywhere in the file.
        self.assertEqual(len(self.npcs), 1,
                         "The Blank Ticket has no combat step, so its NPC file "
                         "should contain exactly one NPC (the giver)")
        for n in self.npcs:
            self.assertNotIn("chain_enemy_template", n.get("ai_config") or {},
                             "no combat step -> no chain_enemy_template")

    def test_giver_spread_embodies_the_quest_skills(self):
        # The giver's sheet is skewed to the capital-ship helm-guns-shields of a
        # master mariner — she embodies the three skills the quest sends a hand
        # to demonstrate.
        giver = self.by_name[GIVER_NPC]
        sk = (giver.get("char_sheet") or {}).get("skills") or {}
        for s in EXPECTED_SKILLS:
            self.assertIn(s, sk,
                          f"giver should carry the quest skill {s!r}")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_blank_ticket.yaml", npc_refs)


if __name__ == "__main__":
    unittest.main()
