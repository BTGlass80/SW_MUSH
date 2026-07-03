# -*- coding: utf-8 -*-
"""
tests/test_generalized_questline_phantom_tonnage.py — T3.24 generalized
quest expansion, thirty-sixth slice.

Proves the THIRTY-SIXTH accessible (non-t5, non-tutorial) `kind: questline`
chain — "The Phantom Tonnage" (kuat_phantom_tonnage) — is shipped correctly
and walks start->graduation through the PRODUCTION dispatcher, the same
hooks the live parser calls. Like the prior thirty-five slices it reuses
the live questline engine (active_questline slot, the existing event
types, the four reward funnels) with NO new engine code, per
quest_expansion_postlaunch_path_v1.md.

THE 36TH-ARC DESIGN FORK (Fork B, resolved): the standing memory flag
(QUEST.t3_24_36th_arc_skill_pool_exhausted) was that every clean skill pool
the loop could reach was spent. There is NO capital-ship-as-combatant seam
(ALLOWED_COMPLETION_TYPES has no ship_destroyed / space_combat_won; the
wilderness-anomaly multi-phase machinery is parallel and unbridged). This
arc realizes "big-ship combat" honestly: PERSON-SCALE ground combat fought
ABOARD a NEW capital-class liner venue (the Ardent Span, a civilian
bulk-freight liner docked at Kuat's Supply Space Station), via the one real
chain combat seam (`combat_won` against a statically-authored NPC tagged
`ai_config.chain_enemy_template`). The capital-ship identity comes from the
VENUE — four new hand-built rooms (kuat_liner_gangway / kuat_liner_gundeck
/ kuat_liner_manifest_core / kuat_liner_bridge, zone kuat_bulk_liner)
appended additively to planets/kuat.yaml and boarded via a single new
`gangway:` exit off the existing kuat_supply_station (room 322) — not from
a ship-vs-ship mechanic. A TRUE ship-vs-ship capital combat step has no
seam and is a separate, non-blocking future design+build (see the arc's
NPC-file header comment and CHANGELOG).

SKILL-UNIQUENESS RELAXATION (Fable addendum §5, 2026-07-03 — record, not a
new rule): every one of the 35 prior accessible questlines documents its
own skill spread in its module docstring as distinct from every other
arc's ("neither of which any prior accessible questline uses" — see e.g.
test_generalized_questline_rigged_issue.py). THIS arc — the 36th, resolving
the very design fork (QUEST.t3_24_36th_arc_skill_pool_exhausted) that
recorded EVERY clean skill pool as spent — deliberately BREAKS that
convention: EXPECTED_SKILLS = ["sensors", "computer programming"] reuses
"sensors" from The Sabotaged Run (tests/test_generalized_questline_
sabotaged_run.py) and "computer programming" from The Sealed Ledger
(tests/test_generalized_questline_sealed_ledger.py). This is Brian's
Fork-B choice ("you pick the concept") superseding the uniqueness
convention for THIS arc alone, because the pool really was exhausted — it
is a SANCTIONED ONE-OFF for the generalized-questline lane's 36th (and, at
present, final accessible) slice, NOT a lifted rule. A hypothetical arc 37+
may NOT cite this file as silent precedent for reusing a skill pair; that
would require its own explicit design call, the same way this one did.

This test complements (does not replace) the generic data-driven walkability
test (test_t5_questline_content.TestAllQuestlinesWalkable, which auto-covers
THIS questline too), the static reachability invariant, the reward-tier
consistency guard, the skill-difficulty winnability guard, and the foil
winnability-band guard (all of which glob/scan the whole corpus and
therefore already cover this arc; this file pins the arc's OWN shape so a
regression in THIS drop is caught by THIS drop's test).
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

QUESTLINE_ID = "kuat_phantom_tonnage"
ACHIEVEMENT_KEY = "phantom_tonnage_cleared"
GIVER_NPC = "Suli Verrin"
ANTAGONIST_NPC = "Hakko Vurm"
STAND_DOWN_NPC = "Renk Talo"
ENEMY_TEMPLATE = "phantom_tonnage_gundeck_boss"
START_ROOM = "kuat_supply_station"
GIVER_ROOM_NAME = "Kuat - Supply Space Station"
ANTAGONIST_ROOM_NAME = "Ardent Span - Rigged Gun-Deck"
STAND_DOWN_ROOM_NAME = "Ardent Span - Command Bridge"
COMBAT_ROOM_SLUG = "kuat_liner_gundeck"
VENUE_ZONE = "kuat_bulk_liner"
VENUE_ROOM_SLUGS = [
    "kuat_liner_gangway", "kuat_liner_gundeck",
    "kuat_liner_manifest_core", "kuat_liner_bridge",
]
NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
            / "npcs_drop_generalized_questline_phantom_tonnage.yaml")

# The arc's skill spread, in step order (steps 2/4 are skill_check_passed).
EXPECTED_SKILLS = ["sensors", "computer programming"]


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


def _room_by_slug(slug: str) -> dict:
    for r in _kuat_rooms():
        if (r.get("slug") or r.get("id")) == slug:
            return r
    return {}


def _kuat_zones() -> dict:
    data = yaml.safe_load(open(
        PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "zones.yaml",
        encoding="utf-8"))
    return data["zones"]


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

    def test_step_shape_is_talk_skill_combat_skill_talk(self):
        # The 5-step talk -> skill_check -> combat -> skill_check -> talk
        # shape that realizes "big-ship combat" as ground combat aboard
        # the venue.
        ql = self._questline()
        types_seen = [s.completion.get("type") for s in ql.steps]
        self.assertEqual(
            types_seen,
            ["talk_to_npc", "skill_check_passed", "combat_won",
             "skill_check_passed", "talk_to_npc"])


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

        # Step 1: talk to Suli Verrin (the auditor / giver)
        _run(on_talk_to_npc(db, char, GIVER_NPC))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: scan the true loaded mass against the declared tonnage (sensors)
        _run(on_skill_check_passed(db, char, "sensors", True, difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: clear the gun-deck (combat_won, count 1)
        _run(on_combat_won(db, char, ENEMY_TEMPLATE, 1))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: slice the doctored manifest core (computer programming)
        _run(on_skill_check_passed(db, char, "computer programming", True,
                                   difficulty=13))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: stand down Renk Talo -> graduate
        _run(on_talk_to_npc(db, char, STAND_DOWN_NPC))
        self.assertTrue(is_chain_complete(_attrs(char), _QUESTLINE_KEY))

    def test_skill_failure_does_not_advance(self):
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "sensors", False, difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_skill_does_not_advance(self):
        # Step 2 gates on sensors; a passing computer-programming check
        # (this questline's OWN step-4 skill) must NOT advance step 2 —
        # the gate is per-step, not "any of the questline's skills."
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "computer programming", True,
                                   difficulty=11))
        self.assertEqual(_qstate(char).get("step"), 2)  # no advance

    def test_wrong_enemy_template_does_not_advance(self):
        # Step 3 gates on the foil's chain_enemy_template; defeating an
        # unrelated template must NOT advance the combat step.
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_skill_check_passed,
            on_combat_won,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, GIVER_NPC))  # ->2
        _run(on_skill_check_passed(db, char, "sensors", True, difficulty=11))  # ->3
        _run(on_combat_won(db, char, "some_other_template", 1))
        self.assertEqual(_qstate(char).get("step"), 3)  # no advance

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

    def _credit_total(self):
        path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "tutorials" / "chains.yaml")
        data = yaml.safe_load(open(path, encoding="utf-8"))
        chain = next(c for c in data["chains"]
                     if c["chain_id"] == QUESTLINE_ID)
        total = int((chain.get("graduation") or {}).get("credits", 0) or 0)
        for s in chain.get("steps") or []:
            total += int((s.get("reward") or {}).get("credits", 0) or 0)
        return total

    def test_matches_papered_refit_reward_band_exactly(self):
        # The spec requires copying kuat_papered_refit's magnitudes VERBATIM
        # (freelance-tier canonical): 450 total credits, 17 independent rep.
        self.assertEqual(self._credit_total(), 450)
        self.assertEqual(self._rep_totals(), {"independent": 17})

    def test_credits_modest_and_graduation_is_300(self):
        ql = self._questline()
        grad_credits = int(getattr(ql.graduation, "credits", 0) or 0)
        self.assertEqual(grad_credits, 300)


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
        allowed = {"talk_to_npc", "command_executed", "skill_check_passed",
                   "combat_won", "mission_accepted", "mission_completed",
                   "bounty_accepted"}
        ql = self._questline()
        for step in ql.steps:
            ctype = (step.completion or {}).get("type")
            self.assertIn(ctype, allowed,
                          f"step {step.step} uses unsupported completion "
                          f"type {ctype!r}")

    def test_skill_spread_is_sensors_then_computer_programming(self):
        ql = self._questline()
        skills = [(s.completion or {}).get("skill") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(skills, EXPECTED_SKILLS)

    def test_difficulties_are_11_then_13_and_non_decreasing(self):
        ql = self._questline()
        diffs = [(s.completion or {}).get("difficulty") for s in ql.steps
                  if (s.completion or {}).get("type") == "skill_check_passed"]
        self.assertEqual(diffs, [11, 13])
        self.assertEqual(diffs, sorted(diffs))

    def test_on_fail_is_retry_allowed_for_both_skill_checks(self):
        ql = self._questline()
        for step in ql.steps:
            comp = step.completion or {}
            if comp.get("type") == "skill_check_passed":
                self.assertEqual(comp.get("on_fail"), "retry_allowed")

    def test_combat_climax_with_single_foil(self):
        # This questline carries a combat_won step (step 3) gated on a
        # single foil's chain_enemy_template, enemy_count 1 (no untested
        # multi-foil wave — conservative balance per the spec).
        ql = self._questline()
        combat_steps = [s for s in ql.steps
                        if (s.completion or {}).get("type") == "combat_won"]
        self.assertEqual(len(combat_steps), 1)
        comp = combat_steps[0].completion
        self.assertEqual(comp.get("enemy_template"), ENEMY_TEMPLATE)
        self.assertEqual(int(comp.get("enemy_count", 0) or 0), 1)

    def test_spread_skills_resolve_to_trained_pools(self):
        from engine.character import canonical_skill_key
        from engine.skill_checks import _get_skill_pool, _get_default_registry
        reg = _get_default_registry()
        for sk in EXPECTED_SKILLS:
            self.assertIsNotNone(reg.get(canonical_skill_key(sk)),
                                 f"spread skill {sk!r} does not resolve to a "
                                 f"registered skill")

    def test_all_step_rooms_are_real_kuat_rooms(self):
        kuat = _kuat_room_slugs()
        ql = self._questline()
        for step in ql.steps:
            self.assertIn(step.location, kuat,
                          f"step {step.step} location {step.location!r} is not "
                          f"a real loaded Kuat room")
        self.assertIn(ql.graduation.drop_room, kuat)

    def test_combat_room_is_not_secured(self):
        # Only the SECURED level gates NPC combat (_check_security_gate); a
        # room with no explicit security_level defaults to CONTESTED
        # (combat-capable). The venue rooms are authored `security_level:
        # contested` explicitly.
        ql = self._questline()
        combat = [s for s in ql.steps
                  if (s.completion or {}).get("type") == "combat_won"][0]
        self.assertEqual(combat.location, COMBAT_ROOM_SLUG)
        room = _room_by_slug(COMBAT_ROOM_SLUG)
        self.assertNotEqual(room.get("security_level"), "secured",
                            f"combat room {COMBAT_ROOM_SLUG!r} is SECURED — the "
                            f"step-3 fight would be gated and unwalkable")


class TestVenue(_RealCorpusBase):
    """The venue: 4 new rooms, new zone, one additive anchor exit."""

    def test_venue_zone_is_registered(self):
        zones = _kuat_zones()
        self.assertIn(VENUE_ZONE, zones)

    def test_four_venue_rooms_exist_in_the_venue_zone(self):
        for slug in VENUE_ROOM_SLUGS:
            room = _room_by_slug(slug)
            self.assertTrue(room, f"venue room {slug!r} not found in kuat.yaml")
            self.assertEqual(room.get("zone"), VENUE_ZONE)

    def test_linear_connectivity_gangway_to_bridge(self):
        rooms = {r["slug"]: r for r in _kuat_rooms() if r.get("slug")}
        gangway = rooms["kuat_liner_gangway"]
        gundeck = rooms["kuat_liner_gundeck"]
        core = rooms["kuat_liner_manifest_core"]
        bridge = rooms["kuat_liner_bridge"]
        self.assertEqual(gangway["exits"].get("out"), "kuat_supply_station")
        self.assertEqual(gangway["exits"].get("in"), "kuat_liner_gundeck")
        self.assertEqual(gundeck["exits"].get("out"), "kuat_liner_gangway")
        self.assertEqual(gundeck["exits"].get("in"), "kuat_liner_manifest_core")
        self.assertEqual(core["exits"].get("out"), "kuat_liner_gundeck")
        self.assertEqual(core["exits"].get("in"), "kuat_liner_bridge")
        self.assertEqual(bridge["exits"].get("out"), "kuat_liner_manifest_core")

    def test_anchor_room_has_additive_gangway_exit(self):
        # Room 322 (kuat_supply_station) must keep its original `hub` exit
        # (additive-only edit) AND carry the new `gangway` exit aboard.
        station = _room_by_slug("kuat_supply_station")
        self.assertEqual(station.get("id"), 322)
        self.assertEqual(station["exits"].get("hub"), "kuat_ring_transit_hub")
        self.assertEqual(station["exits"].get("gangway"), "kuat_liner_gangway")

    def test_anchor_room_is_not_a_pinned_exterior_surface_room(self):
        # Room 322 is an orbital station (kdy_orbital_ring), not a
        # golden-snapshot-pinned exterior planetary-surface room, so the
        # additive exit is coordinate-safe.
        station = _room_by_slug("kuat_supply_station")
        self.assertEqual(station.get("zone"), "kdy_orbital_ring")


class TestNpcs(_RealCorpusBase):

    def setUp(self):
        super().setUp()
        self.npcs = (yaml.safe_load(open(NPC_FILE, encoding="utf-8"))
                     or {}).get("npcs") or []
        self.by_name = {n["name"]: n for n in self.npcs}

    def test_giver_present_in_start_room(self):
        self.assertIn(GIVER_NPC, self.by_name)
        giver = self.by_name[GIVER_NPC]
        self.assertEqual(giver["room"], GIVER_ROOM_NAME)
        self.assertFalse(giver["ai_config"].get("hostile"),
                         "the questline giver must not be hostile")

    def test_antagonist_carries_chain_enemy_template(self):
        # CRITICAL phantom-consumer guard: this is a REAL combat_won chain
        # step, so the gun-deck boss MUST carry chain_enemy_template (unlike
        # the staged-cult bosses, which omit it because they have no chain
        # step) or on_combat_won never credits the kill and step 3 never
        # advances.
        self.assertIn(ANTAGONIST_NPC, self.by_name)
        ant = self.by_name[ANTAGONIST_NPC]
        self.assertEqual(ant["room"], ANTAGONIST_ROOM_NAME)
        self.assertEqual(
            ant["ai_config"].get("chain_enemy_template"), ENEMY_TEMPLATE)
        self.assertTrue(ant["ai_config"].get("hostile"))

    def test_antagonist_carries_proven_ranged_weapon(self):
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

    def test_antagonist_is_stat_clone_of_papered_refit_enforcer(self):
        # The spec requires the gun-deck boss to be stat-cloned VERBATIM
        # from the proven-in-band papered_refit_enforcer (Vodran Sekk) so
        # the foil-winnability guard passes by construction.
        ref_path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                    / "npcs_drop_generalized_questline_papered_refit.yaml")
        ref_npcs = (yaml.safe_load(open(ref_path, encoding="utf-8"))
                    or {}).get("npcs") or []
        ref = next(n for n in ref_npcs if n["name"] == "Vodran Sekk")
        ant = self.by_name[ANTAGONIST_NPC]
        self.assertEqual(
            (ant.get("char_sheet") or {}).get("attributes"),
            (ref.get("char_sheet") or {}).get("attributes"))
        self.assertEqual(
            (ant.get("char_sheet") or {}).get("skills"),
            (ref.get("char_sheet") or {}).get("skills"))
        self.assertEqual(
            (ant.get("char_sheet") or {}).get("weapon"),
            (ref.get("char_sheet") or {}).get("weapon"))

    def test_stand_down_npc_present_and_non_hostile(self):
        # Renk Talo yields once the deck is cleared and the manifest sliced
        # — a talk_to_npc completion requires a present, talkable NPC.
        self.assertIn(STAND_DOWN_NPC, self.by_name)
        talo = self.by_name[STAND_DOWN_NPC]
        self.assertEqual(talo["room"], STAND_DOWN_ROOM_NAME)
        self.assertFalse(talo["ai_config"].get("hostile"),
                         "the stand-down NPC must be non-hostile (talkable, "
                         "not a second combat step)")
        self.assertIsNone(talo["ai_config"].get("chain_enemy_template"))

    def test_exactly_three_placed_npcs(self):
        # The giver + the single combat foil + the stand-down captain; the
        # syndicate, the shippers' survey board, and KSF are narrated-only.
        self.assertEqual(len(self.npcs), 3,
                         "The Phantom Tonnage should place exactly three "
                         "NPCs (giver + combat foil + stand-down captain)")

    def test_npc_file_wired_into_era(self):
        era = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml",
            encoding="utf-8"))
        npc_refs = (era.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_generalized_questline_phantom_tonnage.yaml", npc_refs)


class TestEraCleanness(unittest.TestCase):
    """No Imperial/Empire/Rebel/TIE strings; no canon Clone Wars figures."""

    BANNED = ("imperial", "empire", "rebel", "tie fighter", " tie ")

    def test_npc_file_is_era_clean(self):
        text = NPC_FILE.read_text(encoding="utf-8").lower()
        for term in self.BANNED:
            self.assertNotIn(term, text,
                             f"era-unclean term {term!r} found in NPC file")

    def test_chain_prose_is_era_clean(self):
        data = yaml.safe_load(open(
            PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "tutorials"
            / "chains.yaml", encoding="utf-8"))
        chain = next(c for c in data["chains"]
                     if c["chain_id"] == QUESTLINE_ID)
        blob = yaml.dump(chain).lower()
        for term in self.BANNED:
            self.assertNotIn(term, blob,
                             f"era-unclean term {term!r} found in chain prose")


if __name__ == "__main__":
    unittest.main()
