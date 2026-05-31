# -*- coding: utf-8 -*-
"""
tests/test_f8c2b2_chain_events_phase2.py — F.8.c.2.b Phase 2 tests.

F.8.c.2.b₂ (May 4 2026) extends Phase 1's chain event dispatcher
with four new completion types:

  * ``mission_accepted``   — parser/mission_commands.py post-accept
  * ``mission_completed``  — parser/mission_commands.py post-complete
  * ``bounty_accepted``    — parser/bounty_commands.py post-claim
  * ``item_acquired``      — db/database.py add_to_inventory

Plus seeds combat-template tags onto chain-anchor NPCs so Phase 1's
combat hook starts firing (4 new combat-template seed NPCs in
npcs_drop_f8c2b2_combat_templates.yaml; chain_enemy_template tag
added to Tarko Vinn in npcs_drop_f8c2a_chain_anchors.yaml).

Phase 2 NON-goals (deferred):
  * ``item_used`` is wired but no production trigger point yet —
    Phase 2.5 adds a `use <item>` parser command.
  * ``skill_check_passed`` (with on_fail / fallback) — Phase 3.
  * ``requires_first`` sub-step tracking — Phase 3.

Test sections
-------------
  1. TestMissionAcceptedMatcher    — _match_mission_accepted cases
  2. TestBountyAcceptedMatcher     — _match_bounty_accepted cases
  3. TestItemAcquiredMatcher       — _match_item_acquired cases
  4. TestItemUsedMatcher           — _match_item_used cases
  5. TestOnMissionAccepted         — dispatcher with realistic chain
  6. TestOnMissionCompleted        — dispatcher with realistic chain
  7. TestOnBountyAccepted          — dispatcher with realistic chain
  8. TestOnItemAcquired            — dispatcher with realistic chain
  9. TestOnItemAcquiredByCharId    — char-id variant
 10. TestOnItemUsed                — wired matcher (no production trigger)
 11. TestPhase2NoActiveChainNoOp   — all new hooks no-op without chain
 12. TestPhase2EmptyTagsNoOp       — empty/missing tags no-op silently
 13. TestBountyContractField       — chain_bounty_id field round-trips
                                     through to_dict / from_dict
 14. TestCombatTemplateRosterShape — npcs_drop_f8c2b2 schema + count
 15. TestCombatTemplateNoNameDup   — no name overlap with prior rosters
 16. TestCombatTemplateAnchors     — every NPC sits in a real CW room
 17. TestEraManifestRegistration   — combat-template roster registered
                                     in era.yaml content_refs.npcs
 18. TestTarkoVinnTagged           — F.8.c.2.a Tarko Vinn now has the
                                     chain_enemy_template tag
 19. TestRepublicSoldierE2EPhase2  — full walk including mission_accepted
                                     this time (no Phase-2-simulated
                                     advance_step required)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CW_DIR = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars",
)
COMBAT_ROSTER = os.path.join(
    CW_DIR, "npcs_drop_f8c2b2_combat_templates.yaml",
)
ANCHOR_ROSTER = os.path.join(
    CW_DIR, "npcs_drop_f8c2a_chain_anchors.yaml",
)
ERA_YAML = os.path.join(CW_DIR, "era.yaml")


def _load_yaml(path):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────


class _F8C2B2IsolatedBase(unittest.TestCase):

    def setUp(self):
        from engine.era_state import set_active_config
        from engine.chain_events import _reset_corpus_cache
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        _reset_corpus_cache()

    def tearDown(self):
        from engine.era_state import clear_active_config
        from engine.chain_events import _reset_corpus_cache
        clear_active_config()
        _reset_corpus_cache()


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_fake_db():
    db = MagicMock()
    db.save_character = AsyncMock()
    db.get_npc = AsyncMock(return_value=None)
    db.get_character = AsyncMock(return_value=None)
    return db


def _char_with_chain(chain_id, step=1, completed=None):
    attrs = {
        "tutorial_chain": {
            "chain_id": chain_id,
            "step": step,
            "started_at": 1000000,
            "completed_steps": list(completed or []),
            "completion_state": "active",
        }
    }
    return {
        "id": 42,
        "name": "Test PC",
        "attributes": json.dumps(attrs),
    }


def _char_no_chain():
    return {"id": 99, "attributes": json.dumps({})}


# ─────────────────────────────────────────────────────────────────────
# 1-4. Matchers
# ─────────────────────────────────────────────────────────────────────


class TestMissionAcceptedMatcher(_F8C2B2IsolatedBase):

    def test_exact_match(self):
        from engine.chain_events import _match_mission_accepted
        c = {"mission_id": "tutorial_republic_first_deployment"}
        self.assertTrue(_match_mission_accepted(
            c, "tutorial_republic_first_deployment"))
        self.assertFalse(_match_mission_accepted(
            c, "some_other_mission"))

    def test_empty_mission_id_no_match(self):
        from engine.chain_events import _match_mission_accepted
        self.assertFalse(_match_mission_accepted({}, "x"))
        self.assertFalse(_match_mission_accepted(
            {"mission_id": "x"}, ""))


class TestBountyAcceptedMatcher(_F8C2B2IsolatedBase):

    def test_exact_match(self):
        from engine.chain_events import _match_bounty_accepted
        c = {"bounty_id": "tutorial_bhg_tarko_vinn"}
        self.assertTrue(_match_bounty_accepted(
            c, "tutorial_bhg_tarko_vinn"))
        self.assertFalse(_match_bounty_accepted(c, "other"))

    def test_empty_no_match(self):
        from engine.chain_events import _match_bounty_accepted
        self.assertFalse(_match_bounty_accepted({}, "x"))


class TestItemAcquiredMatcher(_F8C2B2IsolatedBase):

    def test_match_case_insensitive(self):
        from engine.chain_events import _match_item_acquired
        c = {"item": "capacitor_coil_t1"}
        self.assertTrue(_match_item_acquired(c, "capacitor_coil_t1"))
        self.assertTrue(_match_item_acquired(c, "CAPACITOR_COIL_T1"))
        self.assertFalse(_match_item_acquired(c, "capacitor_coil_t2"))

    def test_method_field_is_informational(self):
        from engine.chain_events import _match_item_acquired
        # `method: "+craft fetch"` is teaching text, not a constraint.
        # Matcher ignores it.
        c = {"item": "capacitor_coil_t1", "method": "+craft fetch"}
        self.assertTrue(_match_item_acquired(c, "capacitor_coil_t1"))


class TestItemUsedMatcher(_F8C2B2IsolatedBase):

    def test_exact_match(self):
        from engine.chain_events import _match_item_used
        self.assertTrue(_match_item_used(
            {"item": "sealed_data_packet"}, "sealed_data_packet"))
        self.assertFalse(_match_item_used(
            {"item": "sealed_data_packet"}, "other_item"))


# ─────────────────────────────────────────────────────────────────────
# 5-8. Dispatch
# ─────────────────────────────────────────────────────────────────────


class TestOnMissionAccepted(_F8C2B2IsolatedBase):

    def test_advances_when_chain_mission_id_matches(self):
        # republic_soldier step 3 expects mission_accepted with
        # mission_id = tutorial_republic_first_deployment
        from engine.chain_events import on_mission_accepted
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=3,
                                completed=[1, 2])
        result = _run(on_mission_accepted(
            db, char, "tutorial_republic_first_deployment"))
        self.assertTrue(result)
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs["tutorial_chain"]["step"], 4)

    def test_does_not_advance_on_unrelated_mission(self):
        from engine.chain_events import on_mission_accepted
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=3,
                                completed=[1, 2])
        result = _run(on_mission_accepted(
            db, char, "smuggler_run_to_tatooine"))
        self.assertFalse(result)


class TestOnMissionCompleted(_F8C2B2IsolatedBase):

    def test_advances_when_chain_mission_id_matches(self):
        # republic_intelligence step 4 expects mission_completed
        # with mission_id = tutorial_intel_first_intercept
        from engine.chain_events import on_mission_completed
        db = _make_fake_db()
        char = _char_with_chain("republic_intelligence", step=4,
                                completed=[1, 2, 3])
        result = _run(on_mission_completed(
            db, char, "tutorial_intel_first_intercept"))
        self.assertTrue(result)


class TestOnBountyAccepted(_F8C2B2IsolatedBase):

    def test_advances_when_chain_bounty_id_matches(self):
        # bounty_hunter step 2: bounty_accepted tutorial_bhg_tarko_vinn
        from engine.chain_events import on_bounty_accepted
        db = _make_fake_db()
        char = _char_with_chain("bounty_hunter", step=2,
                                completed=[1])
        result = _run(on_bounty_accepted(
            db, char, "tutorial_bhg_tarko_vinn"))
        self.assertTrue(result)


class TestOnItemAcquired(_F8C2B2IsolatedBase):

    def test_advances_when_item_key_matches(self):
        # shipwright_trader step 3: item_acquired capacitor_coil_t1
        from engine.chain_events import on_item_acquired
        db = _make_fake_db()
        char = _char_with_chain("shipwright_trader", step=3,
                                completed=[1, 2])
        result = _run(on_item_acquired(
            db, char, "capacitor_coil_t1"))
        self.assertTrue(result)

    def test_does_not_advance_on_irrelevant_item(self):
        from engine.chain_events import on_item_acquired
        db = _make_fake_db()
        char = _char_with_chain("shipwright_trader", step=3,
                                completed=[1, 2])
        result = _run(on_item_acquired(db, char, "blaster_pistol"))
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────
# 9. Char-id variant
# ─────────────────────────────────────────────────────────────────────


class TestOnItemAcquiredByCharId(_F8C2B2IsolatedBase):

    def test_fetches_char_and_dispatches(self):
        from engine.chain_events import on_item_acquired_by_char_id
        char = _char_with_chain("shipwright_trader", step=3,
                                completed=[1, 2])
        db = _make_fake_db()
        db.get_character = AsyncMock(return_value=char)
        result = _run(on_item_acquired_by_char_id(
            db, 42, "capacitor_coil_t1"))
        self.assertTrue(result)
        db.get_character.assert_awaited_once_with(42)

    def test_no_char_returns_false(self):
        from engine.chain_events import on_item_acquired_by_char_id
        db = _make_fake_db()
        db.get_character = AsyncMock(return_value=None)
        self.assertFalse(_run(on_item_acquired_by_char_id(
            db, 999, "some_item")))

    def test_get_character_failure_swallowed(self):
        from engine.chain_events import on_item_acquired_by_char_id
        db = _make_fake_db()
        db.get_character = AsyncMock(
            side_effect=RuntimeError("DB exploded"))
        # Must not raise
        result = _run(on_item_acquired_by_char_id(
            db, 42, "some_item"))
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────
# 10. item_used wired but no trigger
# ─────────────────────────────────────────────────────────────────────


class TestOnItemUsed(_F8C2B2IsolatedBase):

    def test_matcher_works(self):
        # The hook is callable and matches correctly — but no
        # production code calls it yet (Phase 2.5).
        from engine.chain_events import on_item_used
        db = _make_fake_db()
        char = _char_with_chain("separatist_agent", step=2,
                                completed=[1])
        result = _run(on_item_used(db, char, "sealed_data_packet"))
        self.assertTrue(result)


# ─────────────────────────────────────────────────────────────────────
# 11. No active chain → no-op for all Phase 2 hooks
# ─────────────────────────────────────────────────────────────────────


class TestPhase2NoActiveChainNoOp(_F8C2B2IsolatedBase):

    def test_mission_accepted(self):
        from engine.chain_events import on_mission_accepted
        self.assertFalse(_run(on_mission_accepted(
            _make_fake_db(), _char_no_chain(),
            "tutorial_republic_first_deployment")))

    def test_mission_completed(self):
        from engine.chain_events import on_mission_completed
        self.assertFalse(_run(on_mission_completed(
            _make_fake_db(), _char_no_chain(), "x")))

    def test_bounty_accepted(self):
        from engine.chain_events import on_bounty_accepted
        self.assertFalse(_run(on_bounty_accepted(
            _make_fake_db(), _char_no_chain(), "x")))

    def test_item_acquired(self):
        from engine.chain_events import on_item_acquired
        self.assertFalse(_run(on_item_acquired(
            _make_fake_db(), _char_no_chain(), "x")))

    def test_item_used(self):
        from engine.chain_events import on_item_used
        self.assertFalse(_run(on_item_used(
            _make_fake_db(), _char_no_chain(), "x")))


# ─────────────────────────────────────────────────────────────────────
# 12. Empty-tag short-circuit
# ─────────────────────────────────────────────────────────────────────


class TestPhase2EmptyTagsNoOp(_F8C2B2IsolatedBase):
    """Empty tags must short-circuit before corpus load. This is
    important: most missions/bounties/items in the world are NOT
    chain-tagged, and dispatching on every accept/claim/add would
    waste work (still cheap — corpus load is one-time — but the
    early return makes the no-op explicit and intentional)."""

    def test_empty_chain_mission_id(self):
        from engine.chain_events import on_mission_accepted
        char = _char_with_chain("republic_soldier", step=3,
                                completed=[1, 2])
        self.assertFalse(_run(on_mission_accepted(
            _make_fake_db(), char, "")))

    def test_empty_chain_bounty_id(self):
        from engine.chain_events import on_bounty_accepted
        char = _char_with_chain("bounty_hunter", step=2,
                                completed=[1])
        self.assertFalse(_run(on_bounty_accepted(
            _make_fake_db(), char, "")))

    def test_empty_item_key(self):
        from engine.chain_events import on_item_acquired
        char = _char_with_chain("shipwright_trader", step=3,
                                completed=[1, 2])
        self.assertFalse(_run(on_item_acquired(
            _make_fake_db(), char, "")))


# ─────────────────────────────────────────────────────────────────────
# 13. BountyContract.chain_bounty_id round-trip
# ─────────────────────────────────────────────────────────────────────


class TestBountyContractField(unittest.TestCase):

    def _make_contract(self, chain_id=""):
        from engine.bounty_board import (
            BountyContract, BountyTier, BountyStatus,
        )
        return BountyContract(
            id="bc_001",
            tier=BountyTier.NOVICE,
            target_name="Test Target",
            target_species="Human",
            target_archetype="petty_smuggler",
            crime_description="evading customs",
            posting_org="BHG",
            tip="Last seen on Nar Shaddaa",
            reward=2000,
            reward_alive_bonus=400,
            target_npc_id=None,
            target_room_id=None,
            chain_bounty_id=chain_id,
        )

    def test_default_empty(self):
        c = self._make_contract()
        self.assertEqual(c.chain_bounty_id, "")

    def test_to_dict_includes_field(self):
        c = self._make_contract("tutorial_bhg_tarko_vinn")
        d = c.to_dict()
        self.assertEqual(d["chain_bounty_id"],
                         "tutorial_bhg_tarko_vinn")

    def test_from_dict_round_trip(self):
        from engine.bounty_board import BountyContract
        c = self._make_contract("tutorial_bhg_tarko_vinn")
        d = c.to_dict()
        c2 = BountyContract.from_dict(d)
        self.assertEqual(c2.chain_bounty_id, c.chain_bounty_id)

    def test_from_dict_missing_field_defaults_empty(self):
        # Forward-compat: rows persisted before this field was added
        # must round-trip cleanly with an empty default.
        from engine.bounty_board import BountyContract
        c = self._make_contract("set_value")
        d = c.to_dict()
        del d["chain_bounty_id"]
        c2 = BountyContract.from_dict(d)
        self.assertEqual(c2.chain_bounty_id, "")


# ─────────────────────────────────────────────────────────────────────
# 14-17. Combat-template roster shape + integration
# ─────────────────────────────────────────────────────────────────────


class TestCombatTemplateRosterShape(unittest.TestCase):

    def test_file_exists(self):
        self.assertTrue(os.path.isfile(COMBAT_ROSTER))

    def test_yaml_parses(self):
        d = _load_yaml(COMBAT_ROSTER)
        self.assertIsNotNone(d)
        self.assertIn("npcs", d)
        self.assertEqual(d.get("schema_version"), 1)

    def test_count_is_4(self):
        d = _load_yaml(COMBAT_ROSTER)
        self.assertEqual(len(d["npcs"]), 4)

    def test_all_have_chain_enemy_template(self):
        d = _load_yaml(COMBAT_ROSTER)
        bad = []
        for n in d["npcs"]:
            tpl = (n.get("ai_config") or {}).get(
                "chain_enemy_template", "")
            if not tpl:
                bad.append(n["name"])
        self.assertEqual(bad, [],
                         f"NPCs missing chain_enemy_template: {bad}")

    def test_all_hostile(self):
        d = _load_yaml(COMBAT_ROSTER)
        bad = [n["name"] for n in d["npcs"]
               if not (n.get("ai_config") or {}).get("hostile")]
        self.assertEqual(bad, [],
                         f"NPCs not flagged hostile: {bad}")

    def test_required_top_level_fields(self):
        d = _load_yaml(COMBAT_ROSTER)
        required = {"name", "room", "species", "description",
                    "char_sheet", "ai_config"}
        for n in d["npcs"]:
            missing = required - set(n.keys())
            self.assertEqual(
                missing, set(),
                f"{n.get('name')} missing fields: {missing}",
            )

    def test_char_sheet_has_attributes_and_skills(self):
        d = _load_yaml(COMBAT_ROSTER)
        for n in d["npcs"]:
            cs = n["char_sheet"]
            self.assertIn("attributes", cs)
            self.assertIn("skills", cs)
            self.assertIn("blaster", cs["skills"])
            self.assertIn("dodge", cs["skills"])


class TestCombatTemplateNoNameDup(unittest.TestCase):

    OTHER_NPC_FILES = (
        "npcs_cw_additions.yaml",
        "npcs_cw_replacements.yaml",
        "npcs_drop_h_combat.yaml",
        "npcs_drop_c1_coruscant.yaml",
        "npcs_drop_def_civilians.yaml",
        "npcs_drop_g1_nar_shaddaa_topside.yaml",
        "npcs_drop_g2_nar_shaddaa_lower.yaml",
        "npcs_drop_b_mos_eisley.yaml",
        "npcs_drop_c2_coruscant_lower.yaml",
        "npcs_drop_f8c2a_chain_anchors.yaml",
    )

    def test_no_name_collision(self):
        my = _load_yaml(COMBAT_ROSTER)
        my_names = {n["name"] for n in my.get("npcs", [])}
        for f in self.OTHER_NPC_FILES:
            other_path = os.path.join(CW_DIR, f)
            if not os.path.exists(other_path):
                continue
            d = _load_yaml(other_path) or {}
            other_names = {n["name"] for n in d.get("npcs", [])}
            overlap = my_names & other_names
            self.assertEqual(overlap, set(),
                             f"Name collision with {f}: {overlap}")


class TestCombatTemplateAnchors(unittest.TestCase):
    """Each combat-template NPC must sit in a real CW room. Match
    via display name across the planet rosters."""

    def test_all_rooms_resolve(self):
        d = _load_yaml(COMBAT_ROSTER)
        # Walk planets/* to gather every known display name
        planets_dir = os.path.join(CW_DIR, "planets")
        all_names = set()
        if os.path.isdir(planets_dir):
            for fname in os.listdir(planets_dir):
                if not fname.endswith(".yaml"):
                    continue
                pdata = _load_yaml(
                    os.path.join(planets_dir, fname)) or {}
                # Planet bundles contain rooms list
                rooms = pdata.get("rooms", []) or []
                for r in rooms:
                    nm = r.get("name", "")
                    if nm:
                        all_names.add(nm)
        # Also include tutorials/rooms.yaml if present (some chain
        # anchors live there).
        tut_rooms_path = os.path.join(
            CW_DIR, "tutorials", "rooms.yaml")
        if os.path.isfile(tut_rooms_path):
            td = _load_yaml(tut_rooms_path) or {}
            for r in td.get("rooms", []) or []:
                nm = r.get("name", "")
                if nm:
                    all_names.add(nm)

        unresolved = []
        for n in d["npcs"]:
            if n["room"] not in all_names:
                unresolved.append((n["name"], n["room"]))

        self.assertEqual(
            unresolved, [],
            f"Combat-template NPCs anchored at unknown rooms: "
            f"{unresolved}",
        )


class TestEraManifestRegistration(unittest.TestCase):

    def test_combat_template_roster_listed(self):
        d = _load_yaml(ERA_YAML)
        npc_files = (d.get("content_refs") or {}).get("npcs") or []
        self.assertIn(
            "npcs_drop_f8c2b2_combat_templates.yaml", npc_files,
            "f8c2b2 combat-template roster must be registered "
            "in era.yaml content_refs.npcs",
        )


# ─────────────────────────────────────────────────────────────────────
# 18. Tarko Vinn tagged
# ─────────────────────────────────────────────────────────────────────


class TestTarkoVinnTagged(unittest.TestCase):

    def test_chain_enemy_template_present(self):
        d = _load_yaml(ANCHOR_ROSTER)
        tarko = next(
            (n for n in d["npcs"] if n["name"] == "Tarko Vinn"),
            None,
        )
        self.assertIsNotNone(tarko, "Tarko Vinn missing from F.8.c.2.a roster")
        tpl = (tarko.get("ai_config") or {}).get(
            "chain_enemy_template", "")
        self.assertEqual(tpl, "tarko_vinn_petty_smuggler")


# ─────────────────────────────────────────────────────────────────────
# 19. Republic Soldier — Phase 2 walk
# ─────────────────────────────────────────────────────────────────────


class TestRepublicSoldierE2EPhase2(_F8C2B2IsolatedBase):
    """Now that mission_accepted is wired, the republic_soldier
    chain walks end-to-end without any Phase-2-simulated
    advance_step calls. The combat_won step is still simulated via
    direct on_combat_won (matching template tag ships in this drop
    too)."""

    def test_full_walk_with_phase2_hooks(self):
        from engine.chain_events import (
            on_command_executed, on_talk_to_npc,
            on_combat_won, on_room_entered,
            on_mission_accepted, get_active_step_info,
        )

        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)

        # Step 1: talk Major Tarrn (Phase 1, with Phase 3 prereqs).
        # F.8.c.2.b₅ (May 5 2026): requires_first is gating now —
        # `look` and `+sheet` must fire before the talk advances.
        self.assertEqual(get_active_step_info(char)["completion_type"],
                         "talk_to_npc")
        self.assertFalse(_run(on_command_executed(db, char, "look", "")))
        self.assertFalse(_run(on_command_executed(db, char, "+sheet", "")))
        self.assertTrue(_run(on_talk_to_npc(db, char, "Major Tarrn")))

        # Step 2: combat_won b1_battle_droid_sim ×2 (Phase 1 hook,
        # Phase 2 data)
        self.assertEqual(get_active_step_info(char)["completion_type"],
                         "combat_won")
        self.assertTrue(_run(on_combat_won(
            db, char, "b1_battle_droid_sim", 2)))

        # Step 3: mission_accepted (Phase 2 — this drop wires it)
        self.assertEqual(get_active_step_info(char)["completion_type"],
                         "mission_accepted")
        self.assertTrue(_run(on_mission_accepted(
            db, char, "tutorial_republic_first_deployment")))

        # Step 4: room_entered coruscant_works_landing_zone (Phase 1)
        self.assertEqual(get_active_step_info(char)["completion_type"],
                         "room_entered")
        self.assertTrue(_run(on_room_entered(
            db, char, "coruscant_works_landing_zone")))

        # Step 5: command_executed +factions (Phase 1) → graduates
        self.assertEqual(get_active_step_info(char)["completion_type"],
                         "command_executed")
        self.assertTrue(_run(on_command_executed(
            db, char, "+factions", "")))

        # Graduated
        self.assertIsNone(get_active_step_info(char))
        attrs = json.loads(char["attributes"])
        self.assertEqual(
            attrs["tutorial_chain"]["completion_state"], "graduated")


# ─────────────────────────────────────────────────────────────────────


class TestDropMarker(unittest.TestCase):
    def test_module_docstring_marks_drop_id(self):
        import tests.test_f8c2b2_chain_events_phase2 as mod
        self.assertIn("F.8.c.2.b₂", mod.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
