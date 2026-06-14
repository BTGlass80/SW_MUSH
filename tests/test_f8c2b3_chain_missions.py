# -*- coding: utf-8 -*-
"""
tests/test_f8c2b3_chain_missions.py — F.8.c.2.b₃ tutorial-mission/bounty
loader + spawner + visibility-filter tests.

F.8.c.2.b₃ (May 4 2026) authors the chain-tagged tutorial mission
and bounty templates that Phase 2's mission_accepted /
mission_completed / bounty_accepted hooks need real data to fire on.

This drop adds:
  * data/worlds/clone_wars/tutorials/tutorial_missions.yaml — 2
    chain-tagged tutorial missions (republic_soldier step 3,
    republic_intelligence step 4)
  * data/worlds/clone_wars/tutorials/tutorial_bounties.yaml — 1
    chain-tagged tutorial bounty (bounty_hunter step 2)
  * engine/chain_missions.py — loader, materializer, spawn-on-step-
    entry hook, visibility filters
  * Wires the spawn hook into engine/chain_events._try_advance
  * Wires the visibility filter into parser/mission_commands.MissionsCommand
    and parser/bounty_commands.BountiesCommand

Test sections
-------------
  1. TestRosterShape         — YAML schema + count
  2. TestRosterCoverage      — every chain step that needs data has data
  3. TestMaterializers       — YAML entries become valid engine objects
  4. TestFindHelpers         — find_mission_for_step / find_bounty_for_step
  5. TestVisibilityFilters   — non-chain visible always; chain-tagged gated
  6. TestSpawnIdempotent     — spawning twice doesn't duplicate
  7. TestSpawnOnStepEntry    — _try_advance hook spawns the mission
  8. TestPreAcceptedFlow     — mission_completed step pre-accepts mission
  9. TestRepublicSoldierE2E  — full chain walk uses real spawned mission
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CW_TUT_DIR = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "tutorials",
)
MISSIONS_YAML = os.path.join(CW_TUT_DIR, "tutorial_missions.yaml")
BOUNTIES_YAML = os.path.join(CW_TUT_DIR, "tutorial_bounties.yaml")
CHAINS_YAML = os.path.join(CW_TUT_DIR, "chains.yaml")


def _load_yaml(path):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
    db.create_mission = AsyncMock(return_value=1)
    db.accept_mission = AsyncMock()
    db.save_mission = AsyncMock()
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


class _IsolatedBase(unittest.TestCase):

    def setUp(self):
        from engine.era_state import set_active_config
        from engine.chain_events import _reset_corpus_cache
        from engine.chain_missions import _reset_caches
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        _reset_corpus_cache()
        _reset_caches()
        # Reset board singletons so we don't pick up state from
        # other test runs in the same process.
        from engine.missions import get_mission_board
        from engine.bounty_board import get_bounty_board
        mb = get_mission_board()
        mb._missions = {}
        bb = get_bounty_board()
        bb._contracts = {}

    def tearDown(self):
        from engine.era_state import clear_active_config
        from engine.chain_events import _reset_corpus_cache
        from engine.chain_missions import _reset_caches
        clear_active_config()
        _reset_corpus_cache()
        _reset_caches()


# ─────────────────────────────────────────────────────────────────────
# 1. Roster shape
# ─────────────────────────────────────────────────────────────────────


class TestRosterShape(unittest.TestCase):

    def test_missions_yaml_exists(self):
        self.assertTrue(os.path.isfile(MISSIONS_YAML))

    def test_bounties_yaml_exists(self):
        self.assertTrue(os.path.isfile(BOUNTIES_YAML))

    def test_missions_yaml_parses(self):
        d = _load_yaml(MISSIONS_YAML)
        self.assertEqual(d.get("schema_version"), 1)
        self.assertIn("missions", d)
        self.assertEqual(len(d["missions"]), 3)

    def test_bounties_yaml_parses(self):
        d = _load_yaml(BOUNTIES_YAML)
        self.assertEqual(d.get("schema_version"), 1)
        self.assertIn("bounties", d)
        self.assertEqual(len(d["bounties"]), 1)

    def test_every_mission_has_chain_id_and_step(self):
        d = _load_yaml(MISSIONS_YAML)
        for m in d["missions"]:
            self.assertIn("chain_mission_id", m)
            self.assertIn("chain_id", m)
            self.assertIn("chain_step", m)

    def test_every_bounty_has_chain_id_and_step(self):
        d = _load_yaml(BOUNTIES_YAML)
        for b in d["bounties"]:
            self.assertIn("chain_bounty_id", b)
            self.assertIn("chain_id", b)
            self.assertIn("chain_step", b)


# ─────────────────────────────────────────────────────────────────────
# 2. Roster coverage — every chain step that needs data has data
# ─────────────────────────────────────────────────────────────────────


class TestRosterCoverage(unittest.TestCase):
    """For every `mission_accepted`, `mission_completed`, and
    `bounty_accepted` step in unlocked CW chains, assert that a
    matching tutorial roster entry exists. This is the regression
    guard that catches an unauthored chain step before the player
    finds it stuck."""

    @classmethod
    def setUpClass(cls):
        cls.chains = _load_yaml(CHAINS_YAML)["chains"]
        cls.missions = _load_yaml(MISSIONS_YAML)["missions"]
        cls.bounties = _load_yaml(BOUNTIES_YAML)["bounties"]

    def test_every_mission_accepted_step_has_template(self):
        unmatched = []
        for chain in self.chains:
            if chain.get("locked"):
                continue
            for step in chain["steps"]:
                c = step["completion"]
                if c["type"] != "mission_accepted":
                    continue
                expected_id = c["mission_id"]
                if not any(m["chain_mission_id"] == expected_id
                           for m in self.missions):
                    unmatched.append((chain["chain_id"],
                                      step["step"], expected_id))
        self.assertEqual(unmatched, [],
                         f"mission_accepted steps with no roster "
                         f"entry: {unmatched}")

    def test_every_mission_completed_step_has_template(self):
        unmatched = []
        for chain in self.chains:
            if chain.get("locked"):
                continue
            for step in chain["steps"]:
                c = step["completion"]
                if c["type"] != "mission_completed":
                    continue
                expected_id = c["mission_id"]
                if not any(m["chain_mission_id"] == expected_id
                           for m in self.missions):
                    unmatched.append((chain["chain_id"],
                                      step["step"], expected_id))
        self.assertEqual(unmatched, [],
                         f"mission_completed steps with no roster "
                         f"entry: {unmatched}")

    def test_every_bounty_accepted_step_has_template(self):
        unmatched = []
        for chain in self.chains:
            if chain.get("locked"):
                continue
            for step in chain["steps"]:
                c = step["completion"]
                if c["type"] != "bounty_accepted":
                    continue
                expected_id = c["bounty_id"]
                if not any(b["chain_bounty_id"] == expected_id
                           for b in self.bounties):
                    unmatched.append((chain["chain_id"],
                                      step["step"], expected_id))
        self.assertEqual(unmatched, [],
                         f"bounty_accepted steps with no roster "
                         f"entry: {unmatched}")


# ─────────────────────────────────────────────────────────────────────
# 3. Materializers
# ─────────────────────────────────────────────────────────────────────


class TestMaterializers(_IsolatedBase):

    def test_mission_materializer_produces_valid_mission(self):
        from engine.chain_missions import _materialize_mission
        d = _load_yaml(MISSIONS_YAML)
        for entry in d["missions"]:
            m = _materialize_mission(entry)
            self.assertIsNotNone(m,
                                 f"materializer failed: {entry.get('chain_mission_id')}")
            self.assertEqual(
                m.mission_data["chain_mission_id"],
                entry["chain_mission_id"],
            )
            self.assertEqual(m.id,
                             f"chain_{entry['chain_mission_id']}")

    def test_bounty_materializer_produces_valid_contract(self):
        from engine.chain_missions import _materialize_bounty
        d = _load_yaml(BOUNTIES_YAML)
        for entry in d["bounties"]:
            c = _materialize_bounty(entry)
            self.assertIsNotNone(c)
            self.assertEqual(c.chain_bounty_id,
                             entry["chain_bounty_id"])

    def test_mission_with_missing_required_returns_none(self):
        from engine.chain_missions import _materialize_mission
        bad = {"chain_mission_id": "x"}  # missing everything else
        self.assertIsNone(_materialize_mission(bad))

    def test_mission_with_unknown_type_returns_none(self):
        from engine.chain_missions import _materialize_mission
        bad = {
            "chain_mission_id": "x", "mission_type": "nope",
            "title": "t", "giver": "g", "objective": "o",
            "destination": "d", "reward": 100,
            "required_skill": "s",
        }
        self.assertIsNone(_materialize_mission(bad))


# ─────────────────────────────────────────────────────────────────────
# 4. find helpers
# ─────────────────────────────────────────────────────────────────────


class TestFindHelpers(_IsolatedBase):

    def test_find_mission_for_step_hits(self):
        from engine.chain_missions import find_mission_for_step
        e = find_mission_for_step("republic_soldier", 3)
        self.assertIsNotNone(e)
        self.assertEqual(e["chain_mission_id"],
                         "tutorial_republic_first_deployment")

    def test_find_mission_for_step_misses(self):
        from engine.chain_missions import find_mission_for_step
        self.assertIsNone(find_mission_for_step("republic_soldier", 1))
        self.assertIsNone(find_mission_for_step("nonexistent", 99))

    def test_find_bounty_for_step_hits(self):
        from engine.chain_missions import find_bounty_for_step
        e = find_bounty_for_step("bounty_hunter", 2)
        self.assertIsNotNone(e)
        self.assertEqual(e["chain_bounty_id"],
                         "tutorial_bhg_tarko_vinn")


# ─────────────────────────────────────────────────────────────────────
# 5. Visibility filters
# ─────────────────────────────────────────────────────────────────────


class TestVisibilityFilters(_IsolatedBase):

    def _make_mission(self, chain_mid="", chain_id="",
                      chain_step=0):
        from engine.missions import (
            Mission, MissionType, MissionStatus,
        )
        return Mission(
            id="m_test",
            mission_type=MissionType.COMBAT,
            title="t", giver="g", objective="o",
            destination="d", destination_room_id=None,
            reward=100, required_skill="blaster",
            mission_data={
                "chain_mission_id": chain_mid,
                "chain_id": chain_id,
                "chain_step": chain_step,
            },
        )

    def _attrs(self, chain_id="", step=0, state="active"):
        return {
            "tutorial_chain": {
                "chain_id": chain_id, "step": step,
                "completion_state": state,
            }
        }

    def test_open_mission_always_visible(self):
        from engine.chain_missions import is_chain_mission_visible_to
        m = self._make_mission()  # no chain tag
        self.assertTrue(is_chain_mission_visible_to(m, {}))
        self.assertTrue(is_chain_mission_visible_to(m, self._attrs()))
        self.assertTrue(is_chain_mission_visible_to(
            m, self._attrs("republic_soldier", 3)))

    def test_chain_mission_visible_at_expected_step(self):
        from engine.chain_missions import is_chain_mission_visible_to
        m = self._make_mission(
            chain_mid="x", chain_id="republic_soldier",
            chain_step=3,
        )
        attrs = self._attrs("republic_soldier", step=3)
        self.assertTrue(is_chain_mission_visible_to(m, attrs))

    def test_chain_mission_visible_one_step_ahead(self):
        from engine.chain_missions import is_chain_mission_visible_to
        # Step 3 mission visible to a player still on step 2 — preview
        m = self._make_mission(
            chain_mid="x", chain_id="republic_soldier",
            chain_step=3,
        )
        attrs = self._attrs("republic_soldier", step=2)
        self.assertTrue(is_chain_mission_visible_to(m, attrs))

    def test_chain_mission_hidden_at_far_step(self):
        from engine.chain_missions import is_chain_mission_visible_to
        m = self._make_mission(
            chain_mid="x", chain_id="republic_soldier",
            chain_step=3,
        )
        # Player on step 5 — chain mission for step 3 is past.
        attrs = self._attrs("republic_soldier", step=5)
        self.assertFalse(is_chain_mission_visible_to(m, attrs))

    def test_chain_mission_hidden_for_other_chain(self):
        from engine.chain_missions import is_chain_mission_visible_to
        m = self._make_mission(
            chain_mid="x", chain_id="republic_soldier",
            chain_step=3,
        )
        attrs = self._attrs("smuggler", step=3)
        self.assertFalse(is_chain_mission_visible_to(m, attrs))

    def test_chain_mission_hidden_for_no_chain_player(self):
        from engine.chain_missions import is_chain_mission_visible_to
        m = self._make_mission(
            chain_mid="x", chain_id="republic_soldier",
            chain_step=3,
        )
        self.assertFalse(is_chain_mission_visible_to(m, {}))

    def test_chain_mission_hidden_for_graduated_player(self):
        from engine.chain_missions import is_chain_mission_visible_to
        m = self._make_mission(
            chain_mid="x", chain_id="republic_soldier",
            chain_step=3,
        )
        attrs = self._attrs(
            "republic_soldier", step=5, state="graduated")
        self.assertFalse(is_chain_mission_visible_to(m, attrs))

    def test_filter_visible_missions_mixed_list(self):
        from engine.chain_missions import filter_visible_missions
        open_m = self._make_mission()
        chain_m = self._make_mission(
            chain_mid="x", chain_id="republic_soldier",
            chain_step=3,
        )
        attrs = self._attrs("republic_soldier", step=3)
        result = filter_visible_missions([open_m, chain_m], attrs)
        self.assertEqual(len(result), 2)

        # Different chain — chain_m hidden
        attrs2 = self._attrs("smuggler", step=2)
        result2 = filter_visible_missions([open_m, chain_m], attrs2)
        self.assertEqual(len(result2), 1)
        self.assertIs(result2[0], open_m)


class TestBountyVisibility(_IsolatedBase):

    def test_chain_bounty_visible_at_expected_step(self):
        from engine.chain_missions import is_chain_bounty_visible_to
        from engine.bounty_board import (
            BountyContract, BountyTier,
        )
        c = BountyContract(
            id="bc", tier=BountyTier.NOVICE,
            target_name="Tarko Vinn", target_species="Zabrak",
            target_archetype="petty_smuggler",
            crime_description="x", posting_org="BHG", tip="x",
            reward=2400, reward_alive_bonus=360,
            target_npc_id=None, target_room_id=None,
            chain_bounty_id="tutorial_bhg_tarko_vinn",
        )
        attrs = {
            "tutorial_chain": {
                "chain_id": "bounty_hunter", "step": 2,
                "completion_state": "active",
            }
        }
        self.assertTrue(is_chain_bounty_visible_to(c, attrs))

    def test_open_bounty_always_visible(self):
        from engine.chain_missions import is_chain_bounty_visible_to
        from engine.bounty_board import (
            BountyContract, BountyTier,
        )
        c = BountyContract(
            id="bc", tier=BountyTier.NOVICE,
            target_name="x", target_species="x",
            target_archetype="x", crime_description="x",
            posting_org="x", tip="x", reward=100,
            reward_alive_bonus=0,
            target_npc_id=None, target_room_id=None,
        )  # no chain_bounty_id
        self.assertTrue(is_chain_bounty_visible_to(c, {}))


# ─────────────────────────────────────────────────────────────────────
# 6. Spawn idempotent
# ─────────────────────────────────────────────────────────────────────


class TestSpawnIdempotent(_IsolatedBase):

    def test_spawn_twice_only_creates_one_mission(self):
        from engine.chain_missions import maybe_spawn_for_step
        from engine.missions import get_mission_board
        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=3,
                                completed=[1, 2])
        # First spawn
        r1 = _run(maybe_spawn_for_step(
            db, char, "republic_soldier", 3))
        # Second spawn (e.g. char re-entering step 3 after restart)
        r2 = _run(maybe_spawn_for_step(
            db, char, "republic_soldier", 3))
        self.assertEqual(r1, "tutorial_republic_first_deployment")
        self.assertEqual(r2, "tutorial_republic_first_deployment")
        # Only one row in the board
        board = get_mission_board()
        chain_missions = [m for m in board._missions.values()
                          if (m.mission_data or {}).get("chain_mission_id")]
        self.assertEqual(len(chain_missions), 1)


# ─────────────────────────────────────────────────────────────────────
# 7. Spawn-on-step-entry hook in _try_advance
# ─────────────────────────────────────────────────────────────────────


class TestSpawnOnStepEntry(_IsolatedBase):

    def test_advancing_into_step_3_spawns_mission(self):
        # republic_soldier step 2 = combat_won; advancing on
        # combat_won fires _try_advance which steps to step 3, and
        # the spawn hook should fire.
        from engine.chain_events import on_combat_won
        from engine.missions import get_mission_board

        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=2,
                                completed=[1])
        # Step 2's chain_enemy_template is b1_battle_droid_sim
        result = _run(on_combat_won(
            db, char, "b1_battle_droid_sim", 2))
        self.assertTrue(result)

        board = get_mission_board()
        # The spawn happened — mission with chain_mission_id =
        # tutorial_republic_first_deployment is now on the board
        spawned = [m for m in board._missions.values()
                   if (m.mission_data or {}).get("chain_mission_id")
                   == "tutorial_republic_first_deployment"]
        self.assertEqual(len(spawned), 1)

    def test_advancing_does_not_spawn_for_non_mission_steps(self):
        # republic_soldier step 1 = talk_to_npc; advance to step 2
        # (combat_won) — no mission spawn expected.
        # F.8.c.2.b₅: step 1 has requires_first [look, +sheet] — must
        # be satisfied before the talk advances.
        from engine.chain_events import on_command_executed, on_talk_to_npc
        from engine.missions import get_mission_board

        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)
        _run(on_command_executed(db, char, "look", ""))
        _run(on_command_executed(db, char, "+sheet", ""))
        result = _run(on_talk_to_npc(db, char, "Major Tarrn"))
        self.assertTrue(result)

        board = get_mission_board()
        chain_missions = [m for m in board._missions.values()
                          if (m.mission_data or {}).get("chain_mission_id")]
        self.assertEqual(len(chain_missions), 0)


# ─────────────────────────────────────────────────────────────────────
# 8. Pre-accepted flow (mission_completed step)
# ─────────────────────────────────────────────────────────────────────


class TestPreAcceptedFlow(_IsolatedBase):

    def test_pre_accepted_mission_lands_in_accepted_slot(self):
        # republic_intelligence step 4: tutorial_intel_first_intercept
        # is pre_accepted=true. Spawning should put it in ACCEPTED
        # status, not AVAILABLE.
        from engine.chain_missions import maybe_spawn_for_step
        from engine.missions import (
            get_mission_board, MissionStatus,
        )
        db = _make_fake_db()
        char = _char_with_chain("republic_intelligence", step=4,
                                completed=[1, 2, 3])
        _run(maybe_spawn_for_step(
            db, char, "republic_intelligence", 4))
        board = get_mission_board()
        spawned = [m for m in board._missions.values()
                   if (m.mission_data or {}).get("chain_mission_id")
                   == "tutorial_intel_first_intercept"]
        self.assertEqual(len(spawned), 1)
        self.assertEqual(spawned[0].status, MissionStatus.ACCEPTED)
        self.assertEqual(spawned[0].accepted_by, str(char["id"]))


# ─────────────────────────────────────────────────────────────────────
# 9. Republic Soldier — full chain walk (Phase 1+2+3)
# ─────────────────────────────────────────────────────────────────────


class TestRepublicSoldierE2EPhase3(_IsolatedBase):
    """Full end-to-end walkthrough using all three phases. No
    Phase-2-simulated-advance_step calls — every step advances via
    its real production hook."""

    def test_full_walk_phase3(self):
        from engine.chain_events import (
            on_command_executed, on_talk_to_npc,
            on_combat_won, on_room_entered,
            on_mission_accepted, get_active_step_info,
        )
        from engine.missions import get_mission_board

        db = _make_fake_db()
        char = _char_with_chain("republic_soldier", step=1)

        # Step 1 → 2: talk Major Tarrn after look + +sheet.
        # F.8.c.2.b₅ added requires_first gating. The class docstring
        # says "every step advances via its real production hook" —
        # that now includes prereq commands.
        self.assertFalse(_run(on_command_executed(db, char, "look", "")))
        self.assertFalse(_run(on_command_executed(db, char, "+sheet", "")))
        self.assertTrue(_run(on_talk_to_npc(db, char, "Major Tarrn")))

        # Step 2 → 3 (combat) — and the spawn hook should fire here
        # because step 3's completion is mission_accepted.
        self.assertTrue(_run(on_combat_won(
            db, char, "b1_battle_droid_sim", 2)))

        # Mission was spawned and is on the board
        board = get_mission_board()
        spawned = [m for m in board._missions.values()
                   if (m.mission_data or {}).get("chain_mission_id")
                   == "tutorial_republic_first_deployment"]
        self.assertEqual(len(spawned), 1)

        # Step 3 → 4: the player's mission_accepted is fed by the
        # parser hook, which reads mission.mission_data.chain_mission_id
        # and passes it to on_mission_accepted. Simulate that here:
        self.assertEqual(
            get_active_step_info(char)["completion_type"],
            "mission_accepted",
        )
        self.assertTrue(_run(on_mission_accepted(
            db, char, "tutorial_republic_first_deployment")))

        # Step 4 → 5 (F.8.c.2.e: talk_to_npc Pilot CT-7567, was the
        # unreachable room_entered commercial_district_landing_zone).
        from engine.chain_events import on_talk_to_npc
        self.assertTrue(_run(on_talk_to_npc(db, char, "Pilot CT-7567")))

        # Step 5 → graduated
        self.assertTrue(_run(on_command_executed(
            db, char, "+factions", "")))

        # Graduated
        attrs = json.loads(char["attributes"])
        self.assertEqual(
            attrs["tutorial_chain"]["completion_state"],
            "graduated",
        )


if __name__ == "__main__":
    unittest.main()
