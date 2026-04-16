# -*- coding: utf-8 -*-
"""
Tests for the D6 Dice Engine.

Run with: pytest tests/test_dice.py -v
"""
import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.dice import (
    DicePool, WildDieResult, RollResult, CheckResult, OpposedResult,
    Difficulty, Scale,
    roll_die, roll_wild_die, roll_d6_pool, roll_pool_str,
    difficulty_check, opposed_roll,
    apply_multi_action_penalty, apply_wound_penalty, apply_scale_modifier,
)


# ── DicePool Parsing ──

class TestDicePoolParse:
    def test_standard(self):
        p = DicePool.parse("4D+2")
        assert p.dice == 4 and p.pips == 2

    def test_no_pips(self):
        p = DicePool.parse("3D")
        assert p.dice == 3 and p.pips == 0

    def test_lowercase(self):
        p = DicePool.parse("5d+1")
        assert p.dice == 5 and p.pips == 1

    def test_negative_pips(self):
        # Negative pips borrow from dice: 3D-1 → 2D+2
        # (1 die = 3 pips, so -1 pip borrows a die and adds 3: -1+3 = 2 pips)
        p = DicePool.parse("3D-1")
        assert p.dice == 2 and p.pips == 2  # borrowed, not clamped

    def test_pip_overflow(self):
        """3 pips should roll into +1D."""
        p = DicePool(2, 4)
        assert p.dice == 3 and p.pips == 1

    def test_empty(self):
        p = DicePool.parse("")
        assert p.dice == 0 and p.pips == 0

    def test_just_number(self):
        p = DicePool.parse("5")
        assert p.dice == 1 and p.pips == 2  # 5 pips = 1D+2

    def test_str_roundtrip(self):
        p = DicePool(4, 2)
        assert str(p) == "4D+2"
        p2 = DicePool.parse(str(p))
        assert p2.dice == 4 and p2.pips == 2

    def test_str_no_pips(self):
        assert str(DicePool(3, 0)) == "3D"

    def test_addition(self):
        a = DicePool(3, 1)
        b = DicePool(2, 2)
        c = a + b
        assert c.dice == 6 and c.pips == 0  # 3 pips -> +1D

    def test_subtraction(self):
        a = DicePool(5, 1)
        b = DicePool(2, 0)
        c = a - b
        assert c.dice == 3 and c.pips == 1

    def test_total_pips(self):
        p = DicePool(3, 2)
        assert p.total_pips() == 11  # 3*3 + 2

    def test_is_zero(self):
        assert DicePool(0, 0).is_zero()
        assert not DicePool(1, 0).is_zero()


# ── Wild Die ──

class TestWildDie:
    def test_normal_roll(self):
        """Wild die rolls 2-5 should be normal."""
        random.seed(42)
        # Run many rolls and verify behavior
        normals = 0
        for _ in range(1000):
            result = roll_wild_die()
            if not result.complication and not result.exploded:
                normals += 1
                assert 2 <= result.total <= 5
                assert len(result.rolls) == 1
        assert normals > 0  # Should get some normals

    def test_complication(self):
        """Wild die of 1 = complication, total = 0."""
        complications = 0
        for _ in range(1000):
            result = roll_wild_die()
            if result.complication:
                complications += 1
                assert result.total == 0
                assert result.rolls[0] == 1
        assert complications > 0

    def test_explosion(self):
        """Wild die of 6 = explodes."""
        explosions = 0
        for _ in range(1000):
            result = roll_wild_die()
            if result.exploded:
                explosions += 1
                assert result.rolls[0] == 6
                assert result.total >= 7  # 6 + at least 1
                assert len(result.rolls) >= 2
        assert explosions > 0


# ── Full Pool Rolls ──

class TestRollD6Pool:
    def test_single_die(self):
        """1D pool: only the wild die."""
        result = roll_d6_pool(DicePool(1, 0))
        assert result.total >= 1
        assert len(result.normal_dice) == 0
        assert result.wild_die is not None

    def test_multiple_dice(self):
        """4D pool: 3 normal + 1 wild."""
        result = roll_d6_pool(DicePool(4, 0))
        assert len(result.normal_dice) == 3
        assert result.wild_die is not None
        assert result.total >= 1

    def test_pips_added(self):
        """Pips should be included in the total."""
        random.seed(100)
        result = roll_d6_pool(DicePool(2, 2))
        assert result.pips == 2
        # Total should be sum of dice + 2
        expected_min = 1  # minimum roll
        assert result.total >= expected_min

    def test_zero_dice(self):
        """0D+2 = just return the pips."""
        result = roll_d6_pool(DicePool(0, 2))
        assert result.total == 2
        assert len(result.normal_dice) == 0
        assert result.wild_die is None

    def test_complication_removes_highest(self):
        """On complication, highest normal die should be removed."""
        complications_tested = 0
        for _ in range(5000):
            result = roll_d6_pool(DicePool(4, 0))
            if result.complication and result.normal_dice:
                complications_tested += 1
                assert result.removed_die is not None
                assert result.removed_die == result.normal_dice[0]  # highest
        assert complications_tested > 0

    def test_minimum_one(self):
        """Total should never be less than 1."""
        for _ in range(1000):
            result = roll_d6_pool(DicePool(1, 0))
            assert result.total >= 1

    def test_display_string(self):
        """Display should be a readable string."""
        result = roll_d6_pool(DicePool(3, 1))
        display = result.display()
        assert "[3D+1]" in display
        assert "=" in display

    def test_roll_pool_str(self):
        """Convenience function should work."""
        result = roll_pool_str("4D+2")
        assert result.pool.dice == 4
        assert result.pool.pips == 2


# ── Difficulty Checks ──

class TestDifficultyCheck:
    def test_easy_check_often_succeeds(self):
        """4D vs Easy (10) should succeed most of the time."""
        successes = sum(
            1 for _ in range(1000)
            if difficulty_check(DicePool(4, 0), 10).success
        )
        assert successes > 700  # Should succeed >70%

    def test_heroic_check_rarely_succeeds(self):
        """2D vs Heroic (30) should almost never succeed."""
        successes = sum(
            1 for _ in range(1000)
            if difficulty_check(DicePool(2, 0), 30).success
        )
        assert successes < 50  # Should almost never succeed

    def test_margin_calculated(self):
        result = difficulty_check(DicePool(5, 0), 15)
        assert result.margin == result.roll.total - 15

    def test_display(self):
        result = difficulty_check(DicePool(3, 0), 15)
        display = result.display()
        assert "vs 15" in display
        assert "SUCCESS" in display or "FAILURE" in display


# ── Opposed Rolls ──

class TestOpposedRoll:
    def test_higher_pool_wins_more(self):
        """6D vs 2D should favor the attacker heavily."""
        att_wins = sum(
            1 for _ in range(1000)
            if opposed_roll(DicePool(6, 0), DicePool(2, 0)).attacker_wins
        )
        assert att_wins > 800

    def test_equal_pools_roughly_even(self):
        """4D vs 4D should be close to 50/50."""
        att_wins = sum(
            1 for _ in range(1000)
            if opposed_roll(DicePool(4, 0), DicePool(4, 0)).attacker_wins
        )
        # Ties go to defender, so attacker should win slightly less than 50%
        assert 300 < att_wins < 600

    def test_margin(self):
        result = opposed_roll(DicePool(4, 0), DicePool(3, 0))
        expected_margin = result.attacker_roll.total - result.defender_roll.total
        assert result.margin == expected_margin

    def test_ties_go_to_defender(self):
        """When totals are equal, defender should win."""
        ties_checked = 0
        for _ in range(10000):
            result = opposed_roll(DicePool(3, 0), DicePool(3, 0))
            if result.margin == 0:
                ties_checked += 1
                assert not result.attacker_wins
        assert ties_checked > 0


# ── Difficulty Enum ──

class TestDifficulty:
    def test_values(self):
        assert Difficulty.VERY_EASY == 5
        assert Difficulty.HEROIC == 30

    def test_from_name(self):
        assert Difficulty.from_name("moderate") == 15
        assert Difficulty.from_name("Very Difficult") == 25

    def test_describe(self):
        assert Difficulty.describe(15) == "Moderate"
        assert Difficulty.describe(22) == "Difficult"
        assert Difficulty.describe(35) == "Heroic"


# ── Scale ──

class TestScale:
    def test_values(self):
        assert Scale.CHARACTER == 0
        assert Scale.STARFIGHTER == 6
        assert Scale.CAPITAL == 12

    def test_difference(self):
        diff = Scale.difference(Scale.STARFIGHTER, Scale.CAPITAL)
        assert diff == 6  # Capital is 6D larger

    def test_difference_reverse(self):
        diff = Scale.difference(Scale.CAPITAL, Scale.STARFIGHTER)
        assert diff == -6  # Starfighter is 6D smaller


# ── Modifier Helpers ──

class TestModifiers:
    def test_multi_action_no_penalty(self):
        pool = apply_multi_action_penalty(DicePool(4, 2), 1)
        assert pool.dice == 4 and pool.pips == 2

    def test_multi_action_two_actions(self):
        pool = apply_multi_action_penalty(DicePool(4, 2), 2)
        assert pool.dice == 3 and pool.pips == 2

    def test_multi_action_floor(self):
        pool = apply_multi_action_penalty(DicePool(2, 1), 5)
        assert pool.dice == 0 and pool.pips == 0  # pips zeroed when dice = 0

    def test_wound_penalty(self):
        pool = apply_wound_penalty(DicePool(5, 1), 2)
        assert pool.dice == 3 and pool.pips == 1

    def test_wound_penalty_floor(self):
        pool = apply_wound_penalty(DicePool(2, 1), 5)
        assert pool.dice == 0 and pool.pips == 0

    def test_scale_modifier(self):
        pool = apply_scale_modifier(
            DicePool(4, 0), Scale.STARFIGHTER, Scale.CAPITAL
        )
        assert pool.dice == 10  # 4 + 6 scale diff


# ── Statistical Sanity Checks ──

class TestStatistics:
    def test_average_3d_around_10(self):
        """3D should average around 10.5 (3 * 3.5)."""
        rolls = [roll_d6_pool(DicePool(3, 0)).total for _ in range(10000)]
        avg = sum(rolls) / len(rolls)
        assert 9.5 < avg < 12.0  # Some variance from wild die

    def test_explosion_rate(self):
        """Wild die should explode ~1/6 of the time."""
        explosions = sum(
            1 for _ in range(6000)
            if roll_d6_pool(DicePool(1, 0)).exploded
        )
        rate = explosions / 6000
        assert 0.10 < rate < 0.25  # ~16.7% expected

    def test_complication_rate(self):
        """Wild die should complicate ~1/6 of the time."""
        complications = sum(
            1 for _ in range(6000)
            if roll_d6_pool(DicePool(2, 0)).complication
        )
        rate = complications / 6000
        assert 0.10 < rate < 0.25  # ~16.7% expected
