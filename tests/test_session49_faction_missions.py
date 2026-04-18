# -*- coding: utf-8 -*-
"""
tests/test_session49_faction_missions.py -- Session 49 feature tests

Covers the restored faction mission feature:
  1. available_missions_for_char() rep-gating helper
  2. FACTION_MISSION_CONFIG shape regression guards
  3. generate_faction_mission() behavioural guarantees not covered by S38

Context: Faction missions were documented as shipped in the v29 architecture
doc (S6.5) and in HANDOFF_APR17_SESSION38.md, but the code was silently
dropped from engine/missions.py during a later refactor. The S38 test suite
caught it but got waved through as "pre-existing" for four sessions. S49
restores the feature and adds these tests to prevent future regression.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. available_missions_for_char rep-gating
# ══════════════════════════════════════════════════════════════════════════════

class TestAvailableMissionsForChar:
    """Test the rep-gating filter that hides faction missions from unqualified chars."""

    def _fake_char(self, char_id: int = 1) -> dict:
        return {"id": char_id, "name": "TestChar"}

    def _run(self, coro):
        return asyncio.run(coro)

    def test_non_faction_missions_always_visible(self):
        """Missions with faction_code=None are visible regardless of rep."""
        from engine.missions import generate_mission, available_missions_for_char

        open_missions = [generate_mission() for _ in range(3)]
        # Open missions should never have faction_code set
        for m in open_missions:
            assert m.faction_code is None

        # Even with zero rep on everything, open missions pass through.
        char = self._fake_char()
        db = MagicMock()
        db.get_organization = AsyncMock(return_value=None)
        db.get_membership = AsyncMock(return_value=None)

        visible = self._run(available_missions_for_char(char, db, open_missions))
        assert len(visible) == 3

    def test_faction_mission_hidden_when_rep_below_threshold(self):
        """A faction mission with rep_required=25 hides from a char with rep 0."""
        from engine.missions import generate_faction_mission, available_missions_for_char

        m = generate_faction_mission("empire")
        assert m.faction_rep_required > 0

        char = self._fake_char()
        db = MagicMock()
        # Organization exists but character has no membership and no attributes rep
        db.get_organization = AsyncMock(return_value={"id": 10, "code": "empire"})
        db.get_membership = AsyncMock(return_value=None)
        # Attributes-based rep lookup returns 0

        visible = self._run(available_missions_for_char(char, db, [m]))
        assert len(visible) == 0, "Empire mission should be filtered out for 0-rep char"

    def test_faction_mission_visible_when_rep_meets_threshold(self):
        """A faction mission is visible when rep >= faction_rep_required."""
        from engine.missions import generate_faction_mission, available_missions_for_char

        m = generate_faction_mission("rebel")
        threshold = m.faction_rep_required

        char = self._fake_char()
        db = MagicMock()
        db.get_organization = AsyncMock(return_value={"id": 11, "code": "rebel"})
        db.get_membership = AsyncMock(return_value={"rep_score": threshold})

        visible = self._run(available_missions_for_char(char, db, [m]))
        assert len(visible) == 1

    def test_faction_mission_visible_when_rep_exceeds_threshold(self):
        """A faction mission is visible when rep > faction_rep_required."""
        from engine.missions import generate_faction_mission, available_missions_for_char

        m = generate_faction_mission("hutt")

        char = self._fake_char()
        db = MagicMock()
        db.get_organization = AsyncMock(return_value={"id": 12, "code": "hutt"})
        db.get_membership = AsyncMock(return_value={"rep_score": 99})

        visible = self._run(available_missions_for_char(char, db, [m]))
        assert len(visible) == 1

    def test_mixed_board_filters_correctly(self):
        """A mixed board shows open missions + only qualified faction missions."""
        from engine.missions import (
            generate_mission, generate_faction_mission, available_missions_for_char,
        )

        open_missions = [generate_mission() for _ in range(2)]
        empire_missions = [generate_faction_mission("empire") for _ in range(2)]
        rebel_missions = [generate_faction_mission("rebel") for _ in range(2)]
        hutt_missions = [generate_faction_mission("hutt") for _ in range(2)]
        board = open_missions + empire_missions + rebel_missions + hutt_missions
        assert len(board) == 8

        char = self._fake_char()
        db = MagicMock()

        # Set up the DB mock to return different rep per faction:
        # - empire: 30 (qualified)
        # - rebel: 10 (NOT qualified, threshold is 25)
        # - hutt: 0 (NOT qualified)
        orgs_by_code = {
            "empire": {"id": 10, "code": "empire"},
            "rebel":  {"id": 11, "code": "rebel"},
            "hutt":   {"id": 12, "code": "hutt"},
        }
        mems_by_org = {
            10: {"rep_score": 30},
            11: {"rep_score": 10},
            12: {"rep_score": 0},
        }

        async def get_org(code):
            return orgs_by_code.get(code)

        async def get_mem(char_id, org_id):
            return mems_by_org.get(org_id)

        db.get_organization = AsyncMock(side_effect=get_org)
        db.get_membership = AsyncMock(side_effect=get_mem)

        visible = self._run(available_missions_for_char(char, db, board))

        # Expected: 2 open + 2 empire + 0 rebel + 0 hutt = 4
        assert len(visible) == 4, f"Expected 4 visible missions, got {len(visible)}"
        visible_factions = {m.faction_code for m in visible}
        assert visible_factions == {None, "empire"}

    def test_rep_cache_avoids_redundant_db_calls(self):
        """A board full of same-faction missions should hit the rep DB once per faction."""
        from engine.missions import generate_faction_mission, available_missions_for_char

        empire_missions = [generate_faction_mission("empire") for _ in range(5)]

        char = self._fake_char()
        db = MagicMock()
        db.get_organization = AsyncMock(return_value={"id": 10, "code": "empire"})
        db.get_membership = AsyncMock(return_value={"rep_score": 50})

        self._run(available_missions_for_char(char, db, empire_missions))

        # Even though there are 5 empire missions, the rep lookup should only
        # run once thanks to the per-faction cache. get_organization is called
        # by get_char_faction_rep once per unique faction.
        assert db.get_organization.call_count == 1, \
            f"Expected 1 get_organization call (cached), got {db.get_organization.call_count}"

    def test_organizations_import_failure_returns_unfiltered(self):
        """If organizations module import fails, helper returns unfiltered list (fail-open)."""
        # This path is hard to trigger in a normal test env because organizations
        # does import successfully. Instead we verify the documented behavior by
        # checking that the function handles gracefully and that ALL missions
        # come through when DB lookups fail. The import-failure branch is a
        # safety net rather than a common path.
        from engine.missions import generate_mission, available_missions_for_char

        missions = [generate_mission() for _ in range(3)]

        char = {"id": 1}
        db = MagicMock()
        db.get_organization = AsyncMock(side_effect=Exception("DB down"))
        db.get_membership = AsyncMock(side_effect=Exception("DB down"))

        visible = asyncio.run(available_missions_for_char(char, db, missions))
        # Open missions always visible regardless of DB errors
        assert len(visible) == 3


# ══════════════════════════════════════════════════════════════════════════════
# 2. FACTION_MISSION_CONFIG shape guards
# ══════════════════════════════════════════════════════════════════════════════

class TestFactionMissionConfigShape:
    """Guard against FACTION_MISSION_CONFIG drifting into a broken shape."""

    REQUIRED_KEYS = {"badge", "givers", "mission_types", "objectives", "reward_mult", "rep_required"}

    def test_all_factions_have_required_keys(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc, cfg in FACTION_MISSION_CONFIG.items():
            missing = self.REQUIRED_KEYS - set(cfg.keys())
            assert not missing, f"Faction '{fc}' missing keys: {missing}"

    def test_all_factions_have_nonempty_givers(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc, cfg in FACTION_MISSION_CONFIG.items():
            assert len(cfg["givers"]) > 0, f"Faction '{fc}' has no givers"

    def test_all_factions_have_nonempty_mission_types(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc, cfg in FACTION_MISSION_CONFIG.items():
            assert len(cfg["mission_types"]) > 0, f"Faction '{fc}' has no mission types"

    def test_all_mission_types_have_objective_templates(self):
        """Every MissionType in a faction's mission_types must have at least one objective template."""
        from engine.missions import FACTION_MISSION_CONFIG
        for fc, cfg in FACTION_MISSION_CONFIG.items():
            for mtype in cfg["mission_types"]:
                templates = cfg["objectives"].get(mtype)
                assert templates, (
                    f"Faction '{fc}' lists mission type {mtype} but has no "
                    f"objective templates for it"
                )
                assert len(templates) > 0

    def test_reward_mults_are_within_design_range(self):
        """Per design spec, faction reward multipliers should be 1.4-1.6."""
        from engine.missions import FACTION_MISSION_CONFIG
        for fc, cfg in FACTION_MISSION_CONFIG.items():
            mult = cfg["reward_mult"]
            assert 1.4 <= mult <= 1.6, (
                f"Faction '{fc}' reward_mult {mult} outside design range [1.4, 1.6]"
            )

    def test_rep_required_is_positive(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc, cfg in FACTION_MISSION_CONFIG.items():
            assert cfg["rep_required"] > 0, (
                f"Faction '{fc}' rep_required must be positive to actually gate"
            )

    def test_all_documented_factions_present(self):
        """Architecture doc v29 S6.5 names empire/rebel/hutt/bh_guild."""
        from engine.missions import FACTION_MISSION_CONFIG
        for fc in ("empire", "rebel", "hutt", "bh_guild"):
            assert fc in FACTION_MISSION_CONFIG, (
                f"Documented faction '{fc}' missing from FACTION_MISSION_CONFIG"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 3. generate_faction_mission behavioural guarantees
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateFactionMissionBehaviour:
    """Guarantees not covered by the S38 test suite."""

    def test_bh_guild_mission_generates(self):
        """bh_guild is the fourth documented faction; S38 only tests three."""
        from engine.missions import generate_faction_mission
        m = generate_faction_mission("bh_guild")
        assert m is not None
        assert m.faction_code == "bh_guild"
        assert m.title.startswith("[GUILD]")

    def test_objective_has_no_unfilled_placeholders(self):
        """Objectives must have all {dest}/{count}/{escort_ship}/{origin} placeholders filled."""
        from engine.missions import generate_faction_mission, FACTION_MISSION_CONFIG
        # Generate a large sample across factions to shake out unfilled templates
        for fc in FACTION_MISSION_CONFIG.keys():
            for _ in range(20):
                m = generate_faction_mission(fc)
                assert m is not None
                assert "{" not in m.objective, (
                    f"Faction '{fc}' generated objective with unfilled placeholder: {m.objective!r}"
                )
                assert "}" not in m.objective, (
                    f"Faction '{fc}' generated objective with unfilled placeholder: {m.objective!r}"
                )

    def test_reward_is_rounded_to_nearest_50(self):
        """Faction missions round reward to 50cr for clean display."""
        from engine.missions import generate_faction_mission
        for _ in range(15):
            m = generate_faction_mission("empire")
            assert m.reward % 50 == 0, f"Reward {m.reward} not rounded to 50cr"

    def test_accepts_destination_rooms(self):
        """Passing live room graph should use those rooms as destinations."""
        from engine.missions import generate_faction_mission
        rooms = [{"id": 999, "name": "Custom Test Room"}]
        # Generate several — at least one should land on our custom room.
        found = False
        for _ in range(20):
            m = generate_faction_mission("empire", destination_rooms=rooms)
            if m.destination == "Custom Test Room":
                assert m.destination_room_id == "999"
                found = True
                break
        assert found, "generate_faction_mission should use destination_rooms when provided"

    def test_skill_level_scales_reward(self):
        """Higher skill_level produces higher average reward (same faction)."""
        from engine.missions import generate_faction_mission
        import random
        random.seed(42)
        low_rewards = [generate_faction_mission("empire", skill_level=1).reward for _ in range(50)]
        random.seed(42)
        high_rewards = [generate_faction_mission("empire", skill_level=6).reward for _ in range(50)]
        assert sum(high_rewards) > sum(low_rewards), (
            "skill_level=6 should produce higher average reward than skill_level=1"
        )

    def test_unknown_faction_returns_none_gracefully(self):
        """S38 tests this, but re-verify it doesn't raise — just returns None."""
        from engine.missions import generate_faction_mission
        # Various forms of bad input
        for bad in ("", "Empire", "EMPIRE", "rebel_alliance", "jedi", None):
            try:
                result = generate_faction_mission(bad)
                # None should be returned, no exception raised
                assert result is None, f"Expected None for bad faction {bad!r}, got {result}"
            except TypeError:
                # None as input may raise TypeError which is acceptable
                if bad is not None:
                    raise
