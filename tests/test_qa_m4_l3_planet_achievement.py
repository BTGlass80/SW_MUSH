# -*- coding: utf-8 -*-
"""
tests/test_qa_m4_l3_planet_achievement.py — QA M4 + L3 regression.

**M4 (QA_FINDINGS_2026-06-16.md M4):** ``on_planet_visited`` was defined in
engine/achievements.py but never called anywhere — the "Galaxy Traveler"
achievement (visit 4 unique planets) could never fire.  Also, the hook used the
additive ``check_achievement`` path with ``count=planets_count`` (the TOTAL),
which would have accumulated counts multiplicatively (total added on every call),
overshooting the trigger.  Fix: wire the hook in LandCommand after the
``on_planet_land`` call; switch ``on_planet_visited`` to the high-water-mark
pattern (same as ``on_room_visited``) so the count is SET, not incremented.

**L3 (QA_FINDINGS_2026-06-16.md L3):** ``advance_skill`` docstring claimed
"If skill is above attribute, cost is doubled." but the code never doubled —
it contained a dead if-branch (``if current_bonus.dice > 0: cost =
total_pool.dice``) that assigned the same value already set above it.  The WEG
R&E rule is simply total-dice-count as cost; no doubling.  Fix: remove the
dead branch and the misleading docstring claim.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ── L3: advance_skill source guards ─────────────────────────────────────────

class TestL3CpCommandsDocstring:
    """cp_commands.py module docstring must not claim cost doubling (QA L3 artifact)."""

    def test_no_doubled_claim_in_module_docstring(self):
        import parser.cp_commands as cp_mod
        src = cp_mod.__doc__ or ""
        assert "doubled" not in src.lower(), (
            "parser/cp_commands.py module docstring still claims 'doubled if above "
            "attribute' — WEG R&E advance_skill cost is total-dice only, no doubling "
            "(QA L3 artifact)")


class TestL3AdvanceSkillDeadBranchRemoved:
    """advance_skill must not claim doubling or contain the dead if-branch."""

    def test_no_doubled_docstring_claim(self):
        from engine.character import Character
        src = inspect.getsource(Character.advance_skill)
        assert "doubled" not in src.lower(), (
            "advance_skill docstring still claims 'cost is doubled above attribute' "
            "but the code never doubles — remove the misleading claim (QA L3)")

    def test_dead_if_branch_removed(self):
        from engine.character import Character
        src = inspect.getsource(Character.advance_skill)
        assert "Above attribute = full cost per die" not in src, (
            "Dead if-branch comment 'Above attribute = full cost per die' is still "
            "present in advance_skill — the no-op branch should be removed (QA L3)")

    def test_no_double_assignment_of_cost(self):
        from engine.character import Character
        src = inspect.getsource(Character.advance_skill)
        # The dead branch assigned 'cost = total_pool.dice' twice; after the fix
        # only one assignment remains.
        cost_lines = [l.strip() for l in src.splitlines()
                      if "cost = total_pool.dice" in l]
        assert len(cost_lines) == 1, (
            f"advance_skill has {len(cost_lines)} 'cost = total_pool.dice' lines "
            f"(expected 1 after removing the dead if-branch) — (QA L3)")


# ── L3: advance_skill functional cost check ─────────────────────────────────

class TestL3AdvanceSkillCost:
    """advance_skill returns total-dice-count as cost (WEG R&E rule)."""

    def _make_reg_and_char(self, attr_dice=3, bonus_dice=0):
        from engine.character import Character, SkillDef, SkillRegistry
        from engine.dice import DicePool

        reg = SkillRegistry()
        sd = SkillDef.__new__(SkillDef)
        sd.name = "Blaster"
        sd.attribute = "dexterity"
        sd.specializations = []
        reg._skills["blaster"] = sd
        char = Character.__new__(Character)
        char.name = "T"
        char.dexterity = DicePool(attr_dice, 0)
        char.skills = {"blaster": DicePool(bonus_dice, 0)} if bonus_dice else {}
        return char, reg

    def test_cost_at_base_attribute_level(self):
        char, reg = self._make_reg_and_char(attr_dice=3, bonus_dice=0)
        cost = char.advance_skill("blaster", reg)
        # total_pool = 3D+0 = 3 dice, so cost = 3
        assert cost == 3, f"Expected cost 3 at 3D base, got {cost}"

    def test_cost_with_existing_bonus(self):
        char, reg = self._make_reg_and_char(attr_dice=3, bonus_dice=1)
        cost = char.advance_skill("blaster", reg)
        # total_pool = 3D + 1D = 4D, cost = 4
        assert cost == 4, (
            f"Expected cost 4 (total 4D=3D+1D bonus), got {cost} — "
            "cost must equal total dice, not be doubled (QA L3)")

    def test_cost_never_doubled(self):
        char, reg = self._make_reg_and_char(attr_dice=2, bonus_dice=3)
        cost = char.advance_skill("blaster", reg)
        # total_pool = 2D + 3D = 5D; if it were doubled it would be 10
        assert cost == 5, (
            f"Expected cost 5 (total 5D), got {cost} — "
            "if this is 10 the dead doubling branch is still active (QA L3)")


# ── M4: on_planet_visited source guards ─────────────────────────────────────

class TestM4OnPlanetVisitedHighWaterMark:
    """on_planet_visited must use the high-water-mark pattern, not check_achievement."""

    def test_does_not_delegate_to_check_achievement(self):
        from engine import achievements
        src = inspect.getsource(achievements.on_planet_visited)
        # The broken implementation delegated to check_achievement (additive);
        # the fix uses the for-loop pattern like on_room_visited.
        assert "check_achievement" not in src, (
            "on_planet_visited still calls check_achievement (additive increment) — "
            "it should use the high-water-mark for-loop pattern like on_room_visited "
            "so repeated calls with the same total don't double-count (QA M4)")

    def test_uses_for_loop_over_by_event(self):
        from engine import achievements
        src = inspect.getsource(achievements.on_planet_visited)
        assert "_BY_EVENT" in src, (
            "on_planet_visited does not iterate _BY_EVENT — "
            "the high-water-mark pattern is not in place (QA M4)")

    def test_upserts_progress_below_target(self):
        from engine import achievements
        src = inspect.getsource(achievements.on_planet_visited)
        assert "_upsert_progress" in src, (
            "on_planet_visited does not call _upsert_progress — "
            "progress below the target threshold is not persisted (QA M4)")


# ── M4: LandCommand wires the hook ──────────────────────────────────────────

class TestM4LandCommandWiresHook:
    """LandCommand.execute must call on_planet_visited after landing."""

    def test_landcommand_imports_on_planet_visited(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "on_planet_visited" in src, (
            "LandCommand.execute does not reference on_planet_visited — "
            "the 'Galaxy Traveler' achievement can never fire (QA M4)")

    def test_landcommand_reads_planets_visited_list(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "planets_visited" in src, (
            "LandCommand.execute does not read the 'planets_visited' attribute "
            "list for the achievement count (QA M4)")


# ── M4: functional — on_planet_visited awards at correct threshold ────────────

class _FakeRow(dict):
    """dict subclass whose .get() works like a real dict (not sqlite3.Row)."""


class _FakeDB:
    """Minimal async DB stub for achievement tests."""

    def __init__(self):
        self._rows: dict[str, Optional[dict]] = {}
        self._completed: dict[str, bool] = {}
        self._progress: dict[str, int] = {}

    async def fetchone(self, sql, params=()):
        key = params[0] if params else None
        return self._rows.get(key)

    async def fetchall(self, sql, params=()):
        return []

    async def execute(self, sql, params=()):
        pass

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_on_planet_visited_awards_at_target():
    """on_planet_visited at count==4 should complete the Galaxy Traveler achievement."""
    from engine import achievements
    achievements.load_achievements()  # populate _BY_EVENT from data/achievements.yaml

    notified = []
    completed_rows = []

    async def fake_get_progress(db, char_id, key):
        return None  # no prior progress

    async def fake_complete(db, char_id, ach, progress):
        completed_rows.append((ach["key"], progress))

    async def fake_notify(session, ach):
        notified.append(ach["key"])

    async def fake_upsert(db, char_id, key, count, completed=False):
        pass

    fake_session = MagicMock()
    fake_db = MagicMock()

    with (
        patch.object(achievements, "_get_progress_row", fake_get_progress),
        patch.object(achievements, "_complete_achievement", fake_complete),
        patch.object(achievements, "_notify_achievement", fake_notify),
        patch.object(achievements, "_upsert_progress", fake_upsert),
    ):
        result = await achievements.on_planet_visited(
            fake_db, char_id=1, session=fake_session, planets_count=4
        )

    assert result == [], "on_planet_visited should return []"
    assert any("galaxy_traveler" in k or "planets" in k
               for k, _ in completed_rows), (
        f"Galaxy Traveler not completed at count=4; completed_rows={completed_rows}")


@pytest.mark.asyncio
async def test_on_planet_visited_no_award_below_target():
    """on_planet_visited at count<4 should NOT complete the achievement."""
    from engine import achievements
    achievements.load_achievements()

    completed_rows = []
    upserted = []

    async def fake_get_progress(db, char_id, key):
        return None

    async def fake_complete(db, char_id, ach, progress):
        completed_rows.append(ach["key"])

    async def fake_upsert(db, char_id, key, count, completed=False):
        upserted.append((key, count))

    with (
        patch.object(achievements, "_get_progress_row", fake_get_progress),
        patch.object(achievements, "_complete_achievement", fake_complete),
        patch.object(achievements, "_upsert_progress", fake_upsert),
        patch.object(achievements, "_notify_achievement", AsyncMock()),
    ):
        await achievements.on_planet_visited(
            MagicMock(), char_id=1, session=None, planets_count=2
        )

    assert completed_rows == [], (
        f"Achievement completed at count=2 (threshold 4) — should not fire: "
        f"{completed_rows}")
    assert upserted, "Progress should be upserted when below threshold"


@pytest.mark.asyncio
async def test_on_planet_visited_idempotent_on_repeat_calls():
    """Calling on_planet_visited twice with the same count must not double-award."""
    from engine import achievements
    achievements.load_achievements()

    completed_rows = []

    async def fake_get_progress(db, char_id, key):
        if completed_rows:
            return {"progress": 4, "completed": True}
        return None

    async def fake_complete(db, char_id, ach, progress):
        completed_rows.append(ach["key"])

    async def fake_upsert(db, char_id, key, count, completed=False):
        pass

    with (
        patch.object(achievements, "_get_progress_row", fake_get_progress),
        patch.object(achievements, "_complete_achievement", fake_complete),
        patch.object(achievements, "_upsert_progress", fake_upsert),
        patch.object(achievements, "_notify_achievement", AsyncMock()),
    ):
        await achievements.on_planet_visited(
            MagicMock(), char_id=1, session=None, planets_count=4
        )
        await achievements.on_planet_visited(
            MagicMock(), char_id=1, session=None, planets_count=4
        )

    assert len(completed_rows) == 1, (
        f"Achievement completed {len(completed_rows)} times on two identical calls "
        f"(should be 1 — already-completed check must gate re-award) (QA M4)")
